"""Read-only Webex Calling discovery and migration preflight.

No POST/PUT/PATCH/DELETE is implemented. Personal tokens are never persisted.
"""
import getpass
import json
import os
import re
import requests
from urllib.parse import urlparse

BASE = 'https://webexapis.com/v1'

class WebexError(RuntimeError):
    pass


def acquire_token(env=os.environ, prompt=True):
    token = env.get('WEBEX_ACCESS_TOKEN', '').strip()
    if not token and prompt:
        token = getpass.getpass('Webex Personal Access Token (Eingabe verborgen): ').strip()
    token = re.sub(r'^Bearer\s+', '', token, flags=re.I).strip()
    if not token:
        raise WebexError('WEBEX_ACCESS_TOKEN fehlt; interaktive Eingabe nicht moeglich oder leer')
    return token


class WebexClient:
    def __init__(self, token, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})

    def get(self, path, params=None):
        if not path.startswith('/'):
            raise WebexError('Invalid API path')
        response = self.session.get(BASE + path, params=params, timeout=30)
        if response.status_code == 401:
            raise WebexError('Webex 401: Token abgelaufen oder ungueltig (Personal Token: 12 Stunden)')
        if response.status_code == 403:
            raise WebexError('Webex 403: Administratorrolle oder erforderlicher Scope fehlt')
        if response.status_code >= 400:
            raise WebexError(f'Webex API HTTP {response.status_code}: {response.text[:400]}')
        return response.json(), response.links.get('next', {}).get('url')

    def list(self, path, params=None, key=None):
        result = []
        next_url = None
        while True:
            if next_url:
                parsed = urlparse(next_url)
                if parsed.scheme != 'https' or parsed.netloc != 'webexapis.com' or not parsed.path.startswith('/v1/'):
                    raise WebexError('Unsafe Webex pagination URL rejected')
                path_and_query = parsed.path.removeprefix('/v1') + ('?' + parsed.query if parsed.query else '')
                data, next_url = self.get(path_and_query)
            else:
                data, next_url = self.get(path, params=params)
            if isinstance(data, list):
                result.extend(data)
            elif key:
                result.extend(data.get(key) or [])
            else:
                raise WebexError(f'Unexpected response for {path}')
            if not next_url:
                return result

    def identity(self):
        data, _ = self.get('/people/me')
        return {'id': data.get('id'), 'displayName': data.get('displayName')}

    def locations(self):
        return self.list('/locations', key='items')

    def hunt_groups(self, location_id, org_id=None):
        params = {'locationId': location_id}
        if org_id:
            params['orgId'] = org_id
        return self.list('/telephony/config/huntGroups', params=params, key='huntGroups')

    def calling_people(self, location_id=None, org_id=None):
        # Webex directory enumeration; callingData includes calling-specific fields.
        params = {'callingData': 'true', 'max': 100}
        # Directory endpoints use the token's organization. Do not forward a
        # configured location ID or UUID as orgId (Webex expects an encoded ID).
        return self.list('/people', params=params, key='items')

    def calling_workspaces(self, location_id=None, org_id=None):
        # Workspaces collection: omit unsupported/tenant-specific filters.
        return self.list('/workspaces', key='items')

    def calling_person_details(self, person_id):
        from urllib.parse import quote
        return self.get('/telephony/config/people/' + quote(person_id, safe=''))[0]

    def calling_workspace_details(self, workspace_id):
        from urllib.parse import quote
        return self.get('/telephony/config/workspaces/' + quote(workspace_id, safe=''))[0]

    def create_hunt_group(self, location_id, payload):
        from urllib.parse import quote
        path = '/telephony/config/locations/' + quote(location_id, safe='') + '/huntGroups'
        response = self.session.post(BASE + path, json=payload, timeout=30)
        if response.status_code >= 400:
            raise WebexError(f'Webex POST HTTP {response.status_code}: {response.text[:400]}')
        return response.json() if response.content else {}

    def hunt_group_details(self, location_id, group_id):
        from urllib.parse import quote
        path = '/telephony/config/locations/' + quote(location_id, safe='') + '/huntGroups/' + quote(group_id, safe='')
        return self.get(path)[0]

    def numbers(self, org_id=None):
        params = {'orgId': org_id} if org_id else None
        return self.list('/telephony/config/numbers', params=params, key='phoneNumbers')


def preflight(chains, client, location_report, org_id=None):
    """Check each planned group against its resolved destination location."""
    resolutions = {r['sourceKey']: r for r in location_report['resolutions']}
    location_ids = sorted({r['locationId'] for r in resolutions.values() if r['locationId']})
    groups_by_location = {lid: client.hunt_groups(lid, org_id) for lid in location_ids}
    numbers = client.numbers(org_id)
    # Extension uniqueness may depend on location; check all returned assignments
    # conservatively until the exact calling dial-plan semantics are validated.
    assigned = {str(n.get(k)).strip() for n in numbers for k in ('extension', 'phoneNumber') if n.get(k)}
    rows = []
    for chain in chains:
        resolution = resolutions[chain['sourceKey']]
        lid = resolution['locationId']
        by_name = {str(g.get('name', '')).casefold() for g in groups_by_location.get(lid, [])}
        for group in chain['huntGroups']:
            problems = []
            if not lid:
                problems.append('LOCATION_UNRESOLVED')
            if group['name'].casefold() in by_name:
                problems.append('NAME_EXISTS')
            if str(group['extension']) in assigned:
                problems.append('NUMBER_IN_USE_OR_ASSIGNED')
            if group.get('memberResolution') != 'RESOLVED':
                problems.append('MEMBERS_UNRESOLVED')
            if len(chain['huntGroups']) > 1:
                problems.append('MULTISTAGE_ROUTING_UNVERIFIED')
            if chain.get('originalQueueSettings'):
                problems.append('QUEUE_SEMANTICS_UNVERIFIED')
            if any(str(v).strip() for v in chain.get('originalForwardSettings', {}).values()):
                problems.append('CFWD_UNVERIFIED')
            problems.append('WEBEX_PAYLOAD_NOT_VALIDATED')
            rows.append({'sourceKey': chain['sourceKey'], 'name': group['name'],
                         'extension': group['extension'], 'status': 'BLOCKED',
                         'reasons': problems, 'locationId': lid})
    return {'mode': 'READ_ONLY_PREFLIGHT', 'locationMode': location_report['mode'],
            'locationsChecked': location_ids, 'inventoryNumberEntries': len(numbers),
            'inventoryMayNotIncludeAllExtensionReservations': True,
            'checks': rows, 'provisioningPerformed': False}
