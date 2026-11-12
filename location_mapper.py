"""Conservative location resolution for CUCM hunt pilot chains.

No guesses are treated as verified. Auto mode uses location-specific Webex
number assignments and member evidence only; ambiguous cases are blocked.
"""
import json
from pathlib import Path


class MappingError(ValueError):
    pass


def load_mapping(path):
    if not path:
        return {}
    file = Path(path)
    if not file.is_file():
        raise MappingError(f'Location mapping file not found: {file}')
    data = json.loads(file.read_text(encoding='utf-8-sig'))
    if isinstance(data, dict) and 'locations' in data:
        entries = data['locations']
        if not isinstance(entries, list):
            raise MappingError('locations must be an array')
        mapping = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('id'), str):
                raise MappingError('Each location requires an id')
            prefix = entry.get('extensionPrefix', '__SET_PREFIX__')
            if prefix == '__SET_PREFIX__' or prefix == '':
                continue  # Valid placeholder: unmapped location, never an implicit match
            if not isinstance(prefix, str) or not prefix.isdigit():
                raise MappingError(f'Invalid extensionPrefix for {entry.get("name", entry["id"])}: {prefix!r}')
            if prefix in mapping and mapping[prefix] != entry['id']:
                raise MappingError(f'Duplicate extensionPrefix across locations: {prefix}')
            mapping[prefix] = entry['id']
        return mapping
    if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v for k, v in data.items()):
        raise MappingError('location-mapping.json must be a JSON object of nonempty prefix: locationId entries')
    return data


def _candidate_from_inventory(pilot, numbers):
    matches = set()
    for n in numbers:
        if str(n.get('extension') or '').strip() != str(pilot):
            continue
        location = n.get('location') or {}
        lid = n.get('locationId') or (location.get('id') if isinstance(location, dict) else None)
        if lid:
            matches.add(lid)
    return matches


def resolve_locations(chains, locations, *, mode='prefix', mapping=None, default_location='', numbers=None, member_locations=None):
    """Return a separate resolution report; never mutate source chains.

    member_locations maps source DN to location IDs, if explicitly supplied by
    a verified external resolver. No CUCM DN -> Webex user inference is made.
    """
    if mode not in ('fixed', 'prefix', 'auto'):
        raise MappingError(f'Unsupported WEBEX_LOCATION_MODE: {mode}')
    mapping = mapping or {}
    numbers = numbers or []
    member_locations = member_locations or {}
    known = {x['id']: x.get('name', '') for x in locations if x.get('id')}
    if mode == 'fixed' and default_location not in known:
        raise MappingError('Fixed location ID is missing or not present in Webex locations')
    unknown = set(mapping.values()) - set(known)
    if unknown and mode == 'prefix':
        raise MappingError(f'Mapping refers to unknown location IDs: {sorted(unknown)}')
    result = []
    for chain in chains:
        groups = chain.get('huntGroups') or []
        pilot = str(groups[0]['extension']) if groups else ''
        candidates = set()
        evidence = []
        selected = None
        if mode == 'fixed':
            selected = default_location
            evidence = ['EXPLICIT_FIXED_LOCATION']
        elif mode == 'prefix':
            prefixes = [p for p in mapping if pilot.startswith(p)]
            if prefixes:
                longest = max(map(len, prefixes))
                best = [p for p in prefixes if len(p) == longest]
                ids = {mapping[p] for p in best}
                if len(ids) == 1:
                    selected = next(iter(ids))
                    evidence = ['PREFIX:' + ','.join(sorted(best))]
                else:
                    evidence = ['CONFLICTING_PREFIX_RULES']
            elif default_location and default_location in known:
                selected = default_location
                evidence = ['EXPLICIT_DEFAULT_FALLBACK']
            else:
                evidence = ['NO_PREFIX_MATCH']
        else:
            inventory = _candidate_from_inventory(pilot, numbers) & known.keys()
            if inventory:
                candidates = inventory
                evidence.append('WEBEX_EXTENSION_INVENTORY')
            member_ids = set()
            for group in groups:
                for m in group.get('members', []):
                    member_ids.update(x for x in member_locations.get(str(m.get('extension')), []) if x in known)
            if member_ids:
                evidence.append('VERIFIED_MEMBER_LOCATION')
                candidates = candidates & member_ids if candidates else member_ids
            if len(candidates) == 1:
                selected = next(iter(candidates))
            elif len(candidates) > 1:
                evidence.append('AMBIGUOUS_MULTIPLE_LOCATIONS')
            else:
                evidence.append('INSUFFICIENT_OR_CONFLICTING_EVIDENCE')
        status = 'RESOLVED' if selected else 'REVIEW_REQUIRED'
        result.append({'sourceKey': chain['sourceKey'], 'huntPilot': pilot, 'mode': mode,
                       'status': status, 'locationId': selected,
                       'locationName': known.get(selected) if selected else None,
                       'evidence': evidence, 'candidateLocationIds': sorted(candidates),
                       'huntGroups': [g['name'] for g in groups]})
    return {'schemaVersion': 1, 'mode': mode, 'provisioningPerformed': False,
            'resolutions': result, 'resolved': sum(x['status'] == 'RESOLVED' for x in result),
            'reviewRequired': sum(x['status'] != 'RESOLVED' for x in result)}
