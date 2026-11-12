"""Deterministic, read-only multi-stage Webex Calling migration planning.

No Webex API calls, no CUCM modifications. Candidate extensions are NOT
verified as free in Webex Calling and must never be provisioned blindly.
"""
import hashlib
import json
import re
from pathlib import Path


def _value(v):
    if v is None:
        return ''
    if isinstance(v, dict):
        return str(v.get('_value_1') or v.get('name') or v.get('pattern') or '')
    return str(v).strip()


def _nonempty(v):
    return bool(_value(v)) and _value(v).upper() not in ('NULL', 'NONE')


def _number(v):
    try:
        return int(v)
    except (ValueError, TypeError):
        return 999999


def _source_key(plan):
    s = plan['source']
    return json.dumps([s['huntPilot'], s['partition']], ensure_ascii=False, separators=(',', ':'))


def _source_id(plan):
    return hashlib.sha256(_source_key(plan).encode('utf-8')).hexdigest()[:10].upper()


def _slug(value):
    result = re.sub(r'[^A-Za-z0-9]+', '-', str(value)).strip('-')
    return result[:30] or 'UNKNOWN'


def _algorithm(settings):
    for key in ('TYPE DISTRIBUTION ALGORITHM', 'distributionAlgorithm'):
        if _nonempty(settings.get(key)):
            return _value(settings[key])
    return ''


def _hunt_options(settings):
    return {k: v for k, v in settings.items() if any(term in k.lower().replace(' ', '') for term in (
        'huntoption', 'noanswer', 'busy', 'notavailable', 'rna', 'timeout', 'distribution', 'algorithm', 'logouthunt', 'logoffhunt'))}


def _order(stages):
    # Preserve original source order on ties; never sort by group name.
    return [s for _, s in sorted(enumerate(stages), key=lambda t: (_number(t[1].get('order')), t[0]))]


def _load_allocations(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('allocations'), dict):
        raise ValueError('Invalid allocation manifest; refusing to overwrite')
    return data['allocations']


def _validate_allocations(allocations, start, end):
    used = {}
    for key, value in allocations.items():
        number = str(value)
        if not number.isdecimal() or not start <= int(number) <= end:
            raise ValueError(f'Allocation outside configured pool: {key}={value}')
        if number in used:
            raise ValueError(f'Duplicate allocation {number}: {used[number]} and {key}')
        used[number] = key
    return used


def build_chains(plans, *, start=89000, end=89999, prefix='HG', allocation_file=None):
    """Return plans with proposed HG stages and stable candidate extensions.

    This function does NOT verify extension availability in Webex.
    """
    if start < 1 or end < start:
        raise ValueError('Invalid WEBEX_HG_EXTENSION_START/END')
    if not re.fullmatch(r'[A-Za-z0-9-]+', prefix):
        raise ValueError('WEBEX_HG_PREFIX must contain only letters, digits, hyphens')
    allocation_file = Path(allocation_file) if allocation_file else None
    allocations = _load_allocations(allocation_file) if allocation_file else {}
    used = _validate_allocations(allocations, start, end)
    # Duplicate pilot numbers across partitions require distinct Webex object names.
    counts = {}
    for plan in plans:
        pilot = plan['source']['huntPilot']
        counts[pilot] = counts.get(pilot, 0) + 1
    chains = []
    object_names = set()
    for plan in sorted(plans, key=_source_key):
        src = plan['source']
        pilot = src['huntPilot']
        key = _source_key(plan)
        ident = _source_id(plan)
        stages = _order(src.get('orderedStages', []))
        if not stages:
            chains.append({'sourceKey': key, 'sourceId': ident, 'status': 'BLOCKED',
                           'warnings': ['No Line Groups resolved'], 'huntGroups': [], 'transitions': [],
                           'originalForwardSettings': src.get('forwardSettings', {}),
                           'originalHuntOptions': src.get('huntOptions', {})})
            continue
        base = f'{prefix}-{_slug(pilot)}'
        if counts[pilot] > 1:
            base += f'-{ident[:6]}'
        objects = []
        warnings = []
        for index, stage in enumerate(stages, 1):
            name = f'{base}-{index:02d}'
            if name in object_names:
                raise ValueError(f'Webex name collision: {name}')
            object_names.add(name)
            if index == 1:
                extension = pilot
                extension_status = 'SOURCE_NUMBER_REQUIRES_VALIDATION'
            else:
                alloc_key = f'{ident}:{index:02d}'
                if alloc_key not in allocations:
                    candidate = next((str(n) for n in range(start, end + 1) if str(n) not in used), None)
                    if candidate is None:
                        raise ValueError('Extension candidate pool exhausted')
                    allocations[alloc_key] = candidate
                    used[candidate] = alloc_key
                extension = allocations[alloc_key]
                extension_status = 'UNVERIFIED_CANDIDATE'
            raw = stage.get('rawLineGroup') or {}
            obj = {
                'position': index, 'name': name, 'extension': extension,
                'extensionStatus': extension_status,
                'sourceHuntList': stage.get('huntList'),
                'sourceLineGroup': stage.get('lineGroup'),
                'sourceSelectionOrder': stage.get('order'),
                'distributionAlgorithm': stage.get('algorithm') or _algorithm(raw),
                'huntOptions': _hunt_options(raw),
                'members': stage.get('members', []),
                'memberResolution': 'REQUIRED', 'locationResolution': 'REQUIRED',
                'provisioningAllowed': False,
            }
            objects.append(obj)
            if not obj['members']:
                warnings.append(f'{name}: no members resolved')
        transitions = []
        for current, following in zip(objects, objects[1:]):
            transitions.append({
                'from': current['name'], 'to': following['name'],
                'targetExtension': following['extension'],
                'status': 'REVIEW_REQUIRED',
                'trigger': None,
                'reason': 'CUCM Hunt Options cannot be assumed equivalent to Webex forwarding triggers',
                'sourceHuntOptions': current['huntOptions'],
                'provisioningAllowed': False,
            })
        forwards = src.get('forwardSettings') or {}
        if any(_nonempty(v) for v in forwards.values()):
            warnings.append('Original CFWD settings retained; final forwarding requires semantic validation')
        if src.get('queueSettings'):
            warnings.append('CUCM native queuing detected; Webex Call Queue architecture must be reviewed')
        if len(stages) > 1:
            warnings.append('Sequential chaining is a proposal, not an equivalent CUCM hunt-list implementation')
        warnings.append('Candidate extensions must be checked against Webex Calling inventory before provisioning')
        chains.append({
            'sourceKey': key, 'sourceId': ident, 'status': 'REVIEW_REQUIRED',
            'huntGroups': objects, 'transitions': transitions,
            'originalForwardSettings': forwards,
            'originalHuntOptions': src.get('huntOptions', {}),
            'originalQueueSettings': src.get('queueSettings', {}),
            'finalForwarding': {'status': 'REVIEW_REQUIRED', 'sourceSettings': forwards,
                                'provisioningAllowed': False},
            'warnings': warnings,
        })
    # Write only after all plans have been validated; stable allocations on repeated runs.
    if allocation_file:
        allocation_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = allocation_file.with_suffix(allocation_file.suffix + '.tmp')
        tmp.write_text(json.dumps({'schemaVersion': 1, 'allocations': allocations}, indent=2), encoding='utf-8')
        tmp.replace(allocation_file)
    return chains
