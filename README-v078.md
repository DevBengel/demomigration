# v0.7.8 — read-only Webex API readback validation

This release adds `webex_validation.py`, a deliberately read-only tool to compare a **separately existing** Webex test Hunt Group against a planned object. It never creates, modifies or deletes anything. A comparison MATCH is **not** migration approval: CUCM hunt semantics, RNA duration, and call behavior still require live testing. Blocked plans remain blocked.

Run standard migration discovery first, then for an already existing, isolated test Hunt Group (not a production group):

```powershell
python .\webex_validation.py --plan .\migration-output-98\webex-create-plan.json --name HG-9711002-01 --existing-test-id YOUR_EXISTING_TEST_GROUP_ID --out .\migration-output-98\webex-test-readback.json
```

**Important:** This compares expected production name/extension, so a separately named/numbered test object will intentionally show mismatches. That is useful to inspect differences, but does not authorize provisioning. No production creation command is added. The current migration CLI's `--apply` still fails closed while the plan is blocked.

Next: introduce an explicit isolated test payload with configurable safe test extension, validate against the live API and only then implement optional, explicitly confirmed test creation.
