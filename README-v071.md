# v0.7.1 – Webex Member API correction and apply safety gate

Corrected collection endpoints: `GET /v1/people?callingData=true` and `GET /v1/workspaces`.
Individual calling configuration can be queried with `/v1/telephony/config/people/{personId}` and `/v1/telephony/config/workspaces/{workspaceId}` when necessary.

Member matching requires explicit extension and matching location; unresolved location, API errors, duplicates, and incomplete inventory remain blocked. Virtual lines are **not yet enumerated**, so this version must not be used to certify a complete inventory where virtual lines may be present.

`--apply` is a deliberately non-operational safety gate in v0.7.1. A future release must validate API schema, permissions, destination extension availability, hunt algorithm mapping, CFWD, queue behavior, multistage routing, idempotency, and read-back verification before permitting writes.

Run: `python migrate.py --source axl --env .env --webex-check --resolve-members --out migration-output`
