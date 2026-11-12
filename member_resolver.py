"""Read-only, conservative extension-to-Webex-identity matching.

Never matches by display name. Never silently picks among duplicates.
A candidate is accepted only when the API supplies an explicit extension.
"""
import json


def _normal(value):
    value = str(value or '').strip()
    return value if value.isdecimal() else ''


def _location(obj):
    value = obj.get('locationId') or obj.get('callingLocationId') or obj.get('location')
    return value.get('id') if isinstance(value, dict) else value


def _extension(obj):
    for key in ('extension', 'callingExtension'):
        if _normal(obj.get(key)):
            return _normal(obj[key])
    numbers = obj.get('numbers') or obj.get('phoneNumbers') or []
    if isinstance(numbers, dict):
        numbers = numbers.get('numbers') or numbers.get('phoneNumbers') or []
    for number in numbers:
        if isinstance(number, dict) and _normal(number.get('extension')):
            return _normal(number['extension'])
    return ''


def _collect(client, location_id, org_id):
    inventory, failures = [], []
    for kind, method, detail_name in [
        ('PEOPLE', client.calling_people, 'calling_person_details'),
        ('WORKSPACE', client.calling_workspaces, 'calling_workspace_details')]:
        try:
            entries = method(location_id=location_id, org_id=org_id)
        except Exception as exc:
            failures.append({'type': kind, 'error': str(exc)[:240]})
            continue
        for obj in entries:
            if not obj.get('id'):
                continue
            loc = _location(obj)
            ext = _extension(obj)
            # Only fetch details when the list did not include an extension or location.
            if (not ext or not loc) and hasattr(client, detail_name):
                try:
                    detail = getattr(client, detail_name)(obj['id'])
                    ext = ext or _extension(detail)
                    loc = loc or _location(detail)
                except Exception as exc:
                    failures.append({'type': kind, 'id': obj['id'], 'error': str(exc)[:240]})
                    continue
            # Never attribute a directory entry to the requested location by assumption.
            if ext and loc == location_id:
                inventory.append({'type': kind, 'id': obj['id'], 'extension': ext,
                                  'name': obj.get('displayName') or obj.get('name') or '',
                                  'locationId': loc})
            elif ext and not loc:
                failures.append({'type': kind, 'id': obj['id'], 'error': 'LOCATION_UNKNOWN'})
    return inventory, failures


def resolve_members(chains, client, location_report, org_id=None):
    locations = {r['sourceKey']: r.get('locationId') for r in location_report['resolutions']}
    inventory_by_location = {}
    reports = []
    for chain in chains:
        lid = locations.get(chain['sourceKey'])
        if lid and lid not in inventory_by_location:
            inventory_by_location[lid] = _collect(client, lid, org_id)
        inventory, errors = inventory_by_location.get(lid, ([], []))
        for group in chain['huntGroups']:
            members = []
            for member in group.get('members', []):
                extension = _normal(member.get('extension'))
                matches = [x for x in inventory if x['extension'] == extension] if extension else []
                # An API failure means we cannot claim uniqueness, even if one source matched.
                status = ('LOCATION_UNRESOLVED' if not lid else
                          'INVENTORY_INCOMPLETE' if errors else
                          'INVALID_EXTENSION' if not extension else
                          'MISSING' if not matches else
                          'AMBIGUOUS' if len(matches) > 1 else 'RESOLVED')
                members.append({'extension': member.get('extension'), 'status': status,
                                'candidates': matches})
            resolved = bool(members) and all(x['status'] == 'RESOLVED' for x in members)
            group['memberResolution'] = 'RESOLVED' if resolved else 'REQUIRED'
            group['resolvedMembers'] = [m['candidates'][0] for m in members] if resolved else []
            reports.append({'sourceKey': chain['sourceKey'], 'huntGroup': group['name'],
                            'locationId': lid, 'status': 'RESOLVED' if resolved else 'REVIEW_REQUIRED',
                            'inventoryErrors': errors, 'members': members})
    return {'schemaVersion': 1, 'mode': 'READ_ONLY', 'reports': reports,
            'resolvedGroups': sum(r['status']=='RESOLVED' for r in reports),
            'reviewRequired': sum(r['status']!='RESOLVED' for r in reports)}
