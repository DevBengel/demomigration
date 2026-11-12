# v0.7.4 – Safe Webex Hunt Group provisioning

Webex documentation: https://developer.webex.com/calling/docs/api/v1/features-hunt-group

The tool now produces `webex-create-plan.json` with validated request payloads and explicit blockers.

## Dry run

```powershell
python .\migrate.py --source axl --env .env --pilot-prefix 971 --webex-check --resolve-members --out .\migration-output-971
```

Inspect `webex-create-plan.json`. `READY` means eligible for the narrow creation path, not that routing behavior is proven equivalent.

## Apply (only one single-stage pilot)

```powershell
python .\migrate.py --source axl --env .env --pilot-prefix 1234 --webex-check --resolve-members --apply --confirm-create HG-1234-01 --out .\migration-output-1234
```

`--apply` creates **only one** eligible Hunt Group, **disabled**, and reads it back. It never enables a Hunt Group, creates multi-stage forwarding chains, changes CUCM, or silently maps queueing. It refuses all known CUCM RNA seconds/hunt-option/queue/forwarding semantic mismatches. Do not use an unreviewed production prefix. `apply-result.json` is a journal; if a POST fails ambiguously, check Control Hub before retrying. The POST requires `spark-admin:telephony_config_write` and full administrator rights.

Supported algorithms: `Longest Idle Time` -> `UNIFORM`, `Top Down` -> `REGULAR`, `Circular` -> `CIRCULAR`, `Broadcast` -> `SIMULTANEOUS`. All others blocked. Agent types: PEOPLE/WORKSPACE. No public phone number is assigned. Calling extensions must be 2–10 digits. API may reject reserved numbers not visible in inventory.

Note: The old `webex-preflight.json` retains legacy `BLOCKED` checks; `webex-create-plan.json` is the authoritative new creation gate. Webex live API POST not tested; test against a non-production organization first.
