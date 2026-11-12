# v0.7.3 – Calling directory reconciliation

- Webex directory entries returning `404 User not found` or `404 Workspace not found` from the *Calling detail* endpoint are treated as stale directory identities and recorded as `inventoryWarnings` with `STALE_DIRECTORY_IDENTITY`. They do not block a unique, explicit location+extension match from other Calling-enabled records.
- Other errors (403, 429, 5xx, generic 404, unknown location) remain blocking `inventoryErrors`.
- A matching record must have explicit extension AND location. Ambiguous and missing matches remain unapproved.
- `member-resolution.json` schemaVersion is now 2. The existing CLI is unchanged.
- `--apply` intentionally remains disabled. This release fixes inventory resolution, **not** Webex provisioning; a complete validated payload and routing/queue equivalence review are still necessary.

Run (PowerShell):

```powershell
python .\migrate.py --source axl --env .env --webex-check --resolve-members --out .\migration-output-98
```

The warning about CUCM HTTPS certificate verification is unrelated; do not disable TLS verification in production.
