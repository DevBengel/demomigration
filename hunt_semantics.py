"""Conservative CUCM Hunt Group semantics inspection, no unsupported API assumptions."""
EXPECTED = 'Try next member; then, try next group in Hunt List'

def assess(options, stage_count, forward_settings):
    options = options or {}
    checks = []
    def add(name, state, detail):
        checks.append({'check':name,'status':state,'detail':detail})
    add('single_stage', 'PASS' if stage_count == 1 else 'BLOCK',
        'One CUCM line group' if stage_count == 1 else 'Sequential line-group fallthrough is not represented by independent Webex hunt groups')
    for key in ('huntAlgorithmNoAnswer','huntAlgorithmBusy','huntAlgorithmNotAvailable'):
        value = options.get(key)
        if value == EXPECTED:
            add(key, 'REVIEW', 'CUCM advances to next member; Webex equivalence and behavior on last agent require live test')
        else:
            add(key, 'BLOCK', f'Unexpected or missing CUCM option: {value!r}')
    auto = str(options.get('autoLogOffHunt','')).lower()
    add('autoLogOffHunt', 'REVIEW' if auto == 'false' else 'BLOCK',
        'CUCM auto-logoff disabled; confirm target agent availability semantics' if auto == 'false' else 'Auto-logoff enabled or unknown')
    if any(isinstance(v,dict) and (v.get('destination') or str(v.get('usePersonalPreferences','')).lower()=='true') for v in (forward_settings or {}).values()):
        add('forwarding','BLOCK','Configured CUCM forwarding needs explicit mapping')
    else:
        add('forwarding','PASS','No configured CUCM hunt forwarding detected')
    return {'status':'BLOCKED' if any(x['status']=='BLOCK' for x in checks) else 'REVIEW_REQUIRED', 'checks':checks,
            'note':'REVIEW is not API validation. Do not auto-approve based on this assessment.'}
