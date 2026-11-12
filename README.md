# CUCM Hunt Migration Analyzer v0.2

Read-only CUCM BAT or AXL discovery. Produces a **review plan**, not production Webex payloads. Source configurations, hunt options, queue settings, forwarding, and ordered multi-line-group topology are preserved. A single Webex Hunt Group must NOT be assumed equivalent to multiple sequential CUCM line groups.

## Setup (PowerShell)

```powershell
py -m pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in CUCM_USERNAME, CUCM_PASSWORD, CUCM_AXL_WSDL in .env
python .\migrate.py --source axl --env .env --out .\migration-output
```

The Cisco AXL Toolkit for the **installed CUCM release** supplies `AXLAPI.wsdl` and imported XSDs; put them together in `./axl/`. AXL connects to `https://198.18.133.33:8443/axl/` by default and requires AXL read access. Verify TLS using your trusted CA; do not disable verification in production. No CUCM changes are performed. `CUCM_AXL_VERSION` is informational; the WSDL controls SOAP schema compatibility.

## BAT mode

```powershell
python .\migrate.py --source bat .\MyHunt_11122026094342.tar --out .\migration-output
```

## Output

- `migration-plan.json`: full CUCM source values (including CFWD/CSS, hunt treatment, queue values, ordered hunt lists and line groups) and conservative target recommendations.
- `review.csv`: per-pilot review summary.

**Limitations:** AXL schema nesting and fields vary by CUCM version. Validate against your release-specific WSDL; `getHuntPilot`/`getHuntList`/`getLineGroup` shapes may require adjustment. No Webex write API is called. Webex agents and locations require explicit mapping; sequential group routing, distinct hunt options and forwarding may need redesign. Credentials in `.env` must be protected. AXL requests are read-only but require network reachability and suitable permissions.

## Version 0.3 – Multi-Line-Group Chain Planner

Version 0.3 adds a **read-only, non-provisioning** chain proposal. Existing AXL and BAT commands remain unchanged. Run, for example:

```powershell
python .\migrate.py --source axl --env .env --out .\migration-output
```

New files:

- `webex-chain-plan.json`: One proposed Webex Calling Hunt Group per ordered CUCM Line Group, with source hunt options, original CFWD and queue settings, and review-only transitions.
- `chain-review.csv`: concise stage-by-stage overview.
- `extension-allocations.json`: persistent candidate extension assignments; **keep this file across runs**.

Names follow `HG-<pilot>-01`, `HG-<pilot>-02`, etc. A short stable hash is inserted for duplicate pilot numbers in different partitions. Original CUCM names remain only as source references in the JSON. The first stage retains the original pilot as a *proposed* extension. Additional stages draw from the `.env` pool. This pool is **not checked against Webex inventory**; do not use it for provisioning until availability and numbering plans have been validated.

**No Webex objects are created.** Transitions and final CFWD are deliberately marked `REVIEW_REQUIRED`. CUCM `Try next group`, busy, no-answer and not-available behaviors do not necessarily map to the Webex Hunt Group forwarding triggers. Native CUCM queue settings may require a Call Queue or a redesigned architecture. All members require identity resolution to Webex users/workspaces/virtual lines, and the target Location must be validated.

**Safety:** AXL access is read-only. TLS verification defaults to true; for a lab with self-signed certificates, `CUCM_VERIFY_TLS=false` is a temporary workaround. Never commit `.env`. Keep extension allocation manifests and migration reports in a protected directory because they can contain sensitive configuration information.


## v0.4: Hunt Pilot line-prefix selection

Select a migration batch by the *beginning of the Hunt Pilot directory number*, not by the name of the Hunt List or Line Group. Set `CUCM_HUNT_PILOT_PREFIXES=98` in `.env`, or override with `--pilot-prefix 98`. Multiple literal prefixes are comma-separated, e.g. `--pilot-prefix 98,99`. `--exclude-prefix 987` excludes a more specific subrange. Matching is literal and case-sensitive, not regex; blank include means all.

```powershell
python .\migrate.py --source axl --env .env --pilot-prefix 98 --list-only
python .\migrate.py --source axl --env .env --pilot-prefix 98 --out .\migration-output
python .\migrate.py --source axl --env .env --pilot-prefix 98,99 --exclude-prefix 987 --out .\migration-output
```

AXL first lists Hunt Pilots, then only fetches matching Hunt Pilots and their dependent Hunt Lists/Line Groups. BAT mode filters after reading the archive. Each run writes a **batch-specific** plan: when using the same output folder, prior plan/review files are overwritten. Use a separate `--out` folder per batch, e.g. `migration-output-98`. The allocation manifest is preserved across runs in the same output folder, but separate output folders do not share reservations. Candidate extensions are not checked against Webex Calling. `--list-only` does not write output.

## v0.5 – Webex API connection (read-only preflight)

The official Webex Calling Hunt Group API requires an administrator token with
`spark-admin:telephony_config_read` for reading, and
`spark-admin:telephony_config_write` for modifying. A Personal Access Token
expires after 12 hours and is intended for interactive testing, not production.

If `WEBEX_ACCESS_TOKEN` is empty/missing, the CLI prompts with `getpass` (hidden
input). The token is not stored in `.env` or in output files.

```powershell
python .\migrate.py --webex-locations --env .env
# Set WEBEX_LOCATION_ID in .env using the returned ID.
python .\migrate.py --source axl --env .env --pilot-prefix 98 --webex-check --out .\migration-output-98
```

`webex-preflight.json` compares proposed Hunt Group names and extensions with
Webex Calling inventory, and reports blockers. A number absent from inventory
is **not** proof that it can be assigned; extension validation and reservation
remain required. Member IDs, multi-stage transitions, original CFWD, Hunt
Options, queue semantics and Webex write payloads remain unresolved.

**This release intentionally performs no Webex writes.** Provisioning will
require an explicit opt-in after the schema, membership mapping, forwarding,
location and extension validation are verified. Never automatically chain
multi-stage groups using a guessed forwarding trigger.

References:
- https://developer.webex.com/calling/docs/api/v1/features-hunt-group
- https://developer.webex.com/calling/docs/api/guides/webex-calling-provisioning-apis
- https://developer.webex.com/calling/docs/getting-started

## v0.6: Multiple Webex Calling Locations

The Webex preflight now supports `WEBEX_LOCATION_MODE=fixed|prefix|auto`.

- `fixed`: use `WEBEX_LOCATION_ID` for every selected CUCM Hunt Pilot (explicit test mode).
- `prefix`: longest matching *literal* Hunt Pilot number prefix from `WEBEX_LOCATION_MAPPING` JSON, e.g. `{"98":"<Frankfurt-location-id>","73":"<Hamburg-location-id>"}`. If no rule matches, the explicitly configured `WEBEX_LOCATION_ID` is used as fallback; otherwise the pilot is flagged `REVIEW_REQUIRED`.
- `auto`: conservative evidence from Webex number inventory (matching source pilot extension and its location ID). It never guesses when there is no evidence or more than one candidate. Member-based inference is supported by the resolver only when a separate verified DN-to-location mapping is supplied; the CLI does not invent one.

`--location-mode` and `--location-mapping` override `.env`. Run:

```powershell
python .\migrate.py --source axl --env .env --pilot-prefix 98,73 --webex-check --out .\migration-output
```

Results: `location-resolution.json` (per-pilot location and evidence) and `webex-preflight.json` (per-stage checks at the selected location). All stages of a source Hunt List use the same target location. Unknown or ambiguous locations are explicitly blocked, never provisioned.

Use `WEBEX_ALLOCATION_FILE=./migration-state/extension-allocations.json` for a **shared, persistent allocation manifest across batches**. This version uses a single globally unique candidate extension pool, not separate per-location pools; the actual availability and dialing semantics must still be checked before any provisioning. The application remains read-only to CUCM and Webex.

**Migration caveat:** A CUCM Hunt List with multiple Line Groups and its hunt/forwarding options cannot be assumed equivalent to a chain of Webex Hunt Groups. No create/update/delete APIs are enabled.


## Location mapping export (v0.6.1)

Run `python .\migrate.py --env .env --export-location-mapping .\location-mapping.json` to fetch live Webex locations. The command refuses to overwrite an existing file. Remove or rename the bundled empty `location-mapping.json` first. Each location has `id`, `name` and `extensionPrefix: "__SET_PREFIX__"`. Replace the placeholder with a digit string (e.g. `"98"`). Unset placeholders are ignored in prefix matching. Names are informational.


## v0.7 – Mitgliederauflösung (read-only)

```powershell
python .\migrate.py --source axl --env .env --pilot-prefix 98 --webex-check --resolve-members --out .\migration-output-98
```

`member-resolution.json` enthält je Line-Group-Mitglied den Status `RESOLVED`, `MISSING`, `AMBIGUOUS`, `INVENTORY_INCOMPLETE` oder `LOCATION_UNRESOLVED`. Nur explizit von der Webex Calling API gelieferte Extensions werden abgeglichen; Anzeigenamen sind keine Identitätsnachweise. Fehler beim Lesen eines API-Inventars verhindern eine automatische Freigabe. Ein Standort muss vorher eindeutig aufgelöst sein.

**Wichtig:** Version 0.7 erzeugt weiterhin **keine** Objekte in Webex. `--apply` ist nicht implementiert. Virtual Lines und cross-location agents sind nicht automatisch aufgelöst. Für die produktive Erstellung sind zudem API-Payload, Routing-/Queue-Semantik und CFWD zu validieren.
