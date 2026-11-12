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
            add(key, 'REVIEW', f'CUCM value={value!r}; next-member/fallthrough behavior and last-agent handling require Webex live test')
        else:
            add(key, 'BLOCK', f'Unexpected or missing CUCM option: {value!r}')
    # Preserve explicit False; missing, null, or unexpected values must fail closed.
    raw_auto = options.get('autoLogOffHunt')
    auto_disabled = raw_auto is False or (isinstance(raw_auto, str) and raw_auto.strip().lower() == 'false')
    add('autoLogOffHunt', 'REVIEW' if auto_disabled else 'BLOCK',
        f'CUCM auto-logoff explicitly disabled ({raw_auto!r}); confirm target availability semantics' if auto_disabled else f'CUCM auto-logoff enabled, missing, or unknown ({raw_auto!r})')
    if any(isinstance(v,dict) and (v.get('destination') or str(v.get('usePersonalPreferences','')).lower()=='true') for v in (forward_settings or {}).values()):
        add('forwarding','BLOCK','Configured CUCM forwarding needs explicit mapping')
    else:
        add('forwarding','PASS','No configured CUCM hunt forwarding detected')
    return {'status':'BLOCKED' if any(x['status']=='BLOCK' for x in checks) else 'REVIEW_REQUIRED', 'checks':checks,
            'note':'REVIEW is not API validation. Do not auto-approve based on this assessment.'}
