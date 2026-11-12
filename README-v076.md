# v0.7.6 – conservative hunt semantics report

Run (PowerShell):

    python .\migrate.py --source axl --env .env --pilot-prefix 971 --webex-check --resolve-members --out .\migration-output-98

New: each object in `webex-create-plan.json` includes `huntSemantics.checks` for CUCM busy, no-answer, unavailable, auto-logoff, forwarding, and multistage routing. PASS is a source-level check; REVIEW means Webex equivalence is not yet demonstrated.

**Important:** This version deliberately does not promote HG-9711002-01 to READY. Cisco's public Hunt Group API reference is available, but the exact POST timing fields and the live target tenant behavior have not been verified here. A fabricated create payload would risk a wrong call flow. RNA calibration is advisory only, including 5 seconds/ring example values. No Webex writes occur without --apply, and blocked objects cannot be applied.

Next evidence required: supported Hunt Group create/update JSON schema and readback from target tenant; test call measurements for busy, unavailable, no-answer, and last agent; confirmation that POST supports disabled creation and desired ring policy. Once verified, wire the exact fields and release the single-stage candidate. Do not bypass blocking reasons.
