# v0.7.5 — RNA timing assessment (safe, advisory)

`webex-create-plan.json` now contains `rnaTiming` for each group: `cucmSeconds`, `webexRings`, `estimatedWebexSeconds`, `estimatedDeviationSeconds`, status, and measurement notes.

Without calibration, the report shows `MEASUREMENT_REQUIRED` and does not guess rings. Optionally provide `--rna-calibration .\rna-calibration.json` with a *measured* seconds-per-ring value, `validatedByTestCalls: true` and measurement notes. The included example is **not** a validated measurement and must not be used unchanged.

Example:

```powershell
python .\migrate.py --source axl --env .env --pilot-prefix 971 --webex-check --resolve-members --out .\migration-output-98
```

With measured calibration:

```powershell
python .\migrate.py --source axl --env .env --pilot-prefix 971 --webex-check --resolve-members --rna-calibration .\rna-calibration.json --out .\migration-output-98
```

**Fail-closed:** timing is advisory only, not inserted into Webex create payloads. Hunt option, RNA, and multistage blockers remain. Before implementing a writable mapping, verify the exact Hunt Group API schema and measure call behavior and readback in the target org. No automatic seconds-to-rings assumption is made.
