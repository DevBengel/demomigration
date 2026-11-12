# v0.7.7 — Hunt semantics data preservation

- Fixed CUCM `autoLogOffHunt` being silently dropped in both AXL extraction and chain planning (previous filters matched `logout`, not `logoff`).
- Explicit boolean `false` is recognized; missing/null/true/unrecognized values remain BLOCK.
- Hunt option review includes exact source values; no assumed equivalence with Webex.
- Semantics BLOCK is now an explicit creation blocker. REVIEW also remains a blocker.
- No API payload timing fields are fabricated; no live provisioning performed.

## Windows PowerShell
Extract ZIP into a temporary directory and copy the Python files into the project root; keep `.env` and mapping files. Then:

```powershell
python -m unittest discover -p 'test_*.py'
python .\migrate.py --source axl --env .env --pilot-prefix 971 --webex-check --resolve-members --out .\migration-output-98
(Get-Content .\migration-output-98\webex-create-plan.json -Raw | ConvertFrom-Json).objects | Where-Object name -eq 'HG-9711002-01' | Select-Object name,status,reasons,huntSemantics,rnaTiming | ConvertTo-Json -Depth 15
```

Do not run `--apply` yet. Live Webex API support, RNA and busy/no-answer/not-available equivalence still require verification.
