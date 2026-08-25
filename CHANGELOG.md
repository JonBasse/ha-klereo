# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed

- **The command confirmation added in 1.6.0 was shaped against a guess, and probably never fired.** `#95` was written without documentation and said so — `_command_id`'s comment declared *"The response shape is NOT measured"*. Klereo's own API documentation arrived on 2026-08-24 ([`docs/klereo-api.md`](docs/klereo-api.md), supplied by the reporter of [GH #58](https://github.com/JonBasse/ha-klereo/issues/58)) and describes `response` as a **JSON ARRAY** whose elements carry `cmdID`, `status`, `startTime`, `updateTime` and `detail` — while the code required `response` to be a **bare integer**. On the documented shape that check is false always, so the "rejected by Klereo" error was unreachable and 1.6.0 degraded to the pre-`#95` behaviour: write, do not verify ([#106](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/106)).
  - **Both shapes are now read**, in `_command_id` and in the new `_command_status`. Which one is live is still unmeasured; reading both cannot regress whichever it turns out to be, and that property is what made this safe to change without hardware.
  - The status is matched on **`cmdID`**, not on position — the documentation says each element represents a command, so a multi-element response is well-formed and taking `[0]` would report another command's verdict as ours.
  - Klereo's free-text **`detail`** is now surfaced in the error, since it is the only part of a rejection that can name the actual cause.
  - An empty `response: []` is treated as "no verdict yet", never as a rejection.
- 🔴 **Why no existing test caught this:** all eight of them mocked `{"status": "ok", "response": 9}`, the same integer form the code assumed. They were measuring the code's agreement with its own assumption rather than with the API — no quantity of tests of that family would have found it. The 7 new tests are written against the documented shape, and the negative control is that reintroducing the bare-integer read reddens exactly those and leaves the 8 original ones green.
- **An output in a mode the integration did not know was reported as "Manual".** `OUTPUT_MODES` carried four modes; Klereo's API documentation lists **ten** ([`docs/klereo-api.md`](docs/klereo-api.md)). Anything outside the four fell through to `self._modes[0]` — so an output genuinely in *Synchro filtration* appeared in Manual, a plausible value indistinguishable from the real thing, with nothing logged ([#105](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/105)).
  - **Four modes are now exposed and selectable**: Filtration Sync (4), Maintenance (6), Pulse (8) and Automatic (9), alongside the existing Manual, Time Slots, Timer and Regulation.
  - Modes **5 and 7 are deliberately never offered** — the documentation marks both *"USAGE INTERNE !! Ne pas utiliser"*. An output reporting one now reads as unknown rather than as Manual.
  - **The fallback is gone, and that is the actual fix.** Widening the table alone would have left the next undocumented mode reading as Manual. An unknown, unreadable or missing mode now reports nothing at all, which Home Assistant renders as unknown.
  - The heating output (4) is untouched and keeps its four KlereoTherm modes — upstream validates `{0,1,2,3}` there on the same line that validates the eight elsewhere.
- Two existing tests asserted the old behaviour and are superseded rather than adapted: one pinned "all four options", the other asserted that a *missing* mode reads as Manual — the defect itself, written down as an expectation.
- **The four "Pro" outputs offered controls that could never work.** Klereo's documentation says `newMode` is *"NON VALABLE POUR LES SORTIES 2,3,4,8,15"* ([`docs/klereo-api.md`](docs/klereo-api.md)). 1.5.3 fixed output 4, whose meaning there **is** known (the KlereoTherm mode); outputs **2, 3, 8 and 15** — pH corrector, disinfectant, flocculant, hybrid disinfectant — were never handled, and the integration built a `switch` and a `select` for every output without ever reading `access` ([#104](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/104)).
  - They are now **not offered below professional access (20)**, which is what upstream does rather than guessing the semantics (`klereo.class.php:1188`).
  - 🔴 **An unknown `access` never gates.** The field is optional, and "we do not know" must not remove an entity a working installation already has — the same rule, and the same reason, as the setpoint gate added in 1.6.0.
  - This does not guess what `newMode` means on those outputs for an account that *does* have access 20. The documentation says the value differs, never what it is; that stays unknown and unimplemented.
- Note that `#95` made this **visible** without fixing it: since 1.6.0 a write to one of these outputs surfaces status 13 (insufficient rights) instead of failing silently, so non-professional accounts started seeing errors on entities that should never have been offered.

### Changed
- Widening the table was safe without hardware because two independently written sources agree on the exact set Klereo accepts for writes — the documentation's ten minus its two internal-use entries, and the upstream plugin's `{0,1,2,3,4,6,8,9}` (`klereo.class.php:1198`).

## [1.6.0] — 2026-08-23

### Fixed

- **The water setpoint was read from a guessed container, so it appeared for nobody.** `ConsigneEau` is the only entry in `PARAM_TYPES` and therefore the integration's only `number` entity; it was read from `RegulModes`, a container the introducing commit declares guessed in its own comment and whose name appears nowhere in the upstream Jeedom plugin — which reads every setpoint from `params`. **Three** containers are now read — `RegulModes`, `params` and `ExtraParams` — in that order of precedence, so the change can only add a value, never alter one an existing install already shows ([#94](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/94)).
  - `ExtraParams` comes from an external reporter who read their own diagnostic export and named it alongside `params` ([GH #54](https://github.com/JonBasse/ha-klereo/issues/54), 2026-06-17) — the first real payload measured here, and independent confirmation that `params` is what the integration actually receives.
- **Setpoint bounds came from a hard-coded 10-40.** They now come from the `EauMin` / `EauMax` the API sends for your installation; the hard-coded pair is only a fallback.
- **Sentinel values were displayed as readings.** `-2000` (setpoint disabled) and `-1000` (unknown) no longer create an entity.
- **A rejected command looked exactly like a successful one.** `SetOut` and `SetParam` do not execute — they *queue*, and return a cmdID immediately, so their HTTP 200 means "accepted for execution", never "executed". The integration took that reply for a result, discarded the cmdID and refreshed. Every write is now confirmed through `WaitCommand`, and a status other than 9 raises an error in Home Assistant carrying the status label ([#95](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/95)).
  - The costly one is **13, insufficient rights**: upstream bars outputs 2, 3, 8 and 15 below access level 20, so a non-professional account commanding its pH corrector got a silent success.
  - Statuses 0 (pending) and 1 (running) are not failures and do not raise.
  - A command whose outcome cannot be read — no cmdID in the reply, which is what an expired JWT returns — logs a warning and behaves as before. The reply's shape is not measured, and turning a guess into a hard failure would break every write on an assumption.
  - A rejected command no longer triggers a data refresh; upstream refreshes only on status 9.

### Added

- The water setpoint is now gated the way upstream gates it, so it stops being offered where the hardware or the account does not have it: account `access` below 10, and `HeaterMode` 0 (no heat pump) or 3 (on/off heat pump, no setpoint). An **unknown** value never gates — a payload carrying neither field keeps the entity it has today.
- Keys from `params` and `ExtraParams` are exposed as read-only sensors only through the curated `PARAM_NAMES` list; upstream reads those containers at 40+ sites, so taking every key would create dozens of entities in every install.
- A `debug` trace of the detail payload's top-level keys on each refresh — the instrument that stops the container from being a guess at the next report.
- `API_URL_COMMAND_STATUS`, `CMD_STATUS_OK`, `CMD_STATUS_IN_FLIGHT` and `CMD_STATUS_LABELS` in `api.py`, plus `KlereoApi.command_status()`.
- 38 tests across the three fixes (**128 total**, up from 90).
- **HACS and `hassfest` validation run again**, on GitHub, where `hacs/action` can see the repository it is validating ([#89](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/89)). They had run nowhere since 2026-07-15. Two locks had to be lifted, neither of them CI configuration: the push-mirror moved to SSH + a per-repo deploy key (the classic PAT lacks the `workflow` scope, and GitHub rejects the *entire ref*), and repository-level GitHub Actions were re-enabled.

## [1.5.3] — 2026-08-23

### Fixed

- **The Heating switch turned the heat pump off instead of on.** On output 4, `SetOut`'s `newMode` carries the KlereoTherm mode, not the output mode — so the `OUT_MODE_MAN` (= 0) that every other output needs means **Off** there. The API answered `{"status":"ok"}` either way, so the command failed silently. `switch.turn_on` now sends `HEAT_MODE_HEATING`/`OUT_STATE_AUTO` and `turn_off` sends `HEAT_MODE_STOP`/`OUT_STATE_OFF` ([#55](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/55), [GH #58](https://github.com/JonBasse/ha-klereo/issues/58)).
- **The Heating mode select offered the wrong options.** Output 4 now lists `Off` / `Auto` / `Cooling` / `Heating` instead of Manual / Time Slots / Timer / Regulation, reads its current option from the same table, and pairs a non-Off mode with `newState = 2` (Automatic).
- **Every non-Manual mode change sent the wrong `newState`.** The select reused the output's current ON/OFF status; only Manual carries an ON/OFF state, while Time Slots, Timer and Regulation all expect `OUT_STATE_AUTO` (2). Manual now clamps a non-ON status to OFF rather than forwarding a meaningless `2`.
- The Heating switch reports **on** for status `2` (Automatic); on that output only `Off` means off.

### Added

- `OUT_STATE_AUTO`, `OUT_IDX_HEATING`, `HEAT_MODE_*` and `HEAT_MODES` in `api.py`, each carrying its upstream citation (`klereo.class.php` l.1377-1380 and the `outIndex === 4` branch at l.1525+).
- 13 tests covering the heating output's switch and select, plus the AUTO-state rule on ordinary outputs (90 tests total, up from 77).

## [1.5.1] — 2026-03-05

### Added

- **test_config_flow.py** — 10 tests covering `validate_input` (success, API errors, HTTP errors, timeout, password hashing) and `hash_password` utility ([#36](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/36)).
- **test_diagnostics.py** — 3 tests covering diagnostics output structure, sensitive field redaction, and `TO_REDACT` contents ([#37](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/37)).
- **test_number.py** — 6 tests covering `KlereoNumber` creation, initial value, `async_set_native_value`, coordinator update, availability, and device info ([#38](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/38)).
- **test_api.py** — 6 new tests for `_request_with_retry` (transient error retry, retry exhaustion, non-401 propagation) and `_parse_response` (valid JSON, invalid JSON, HTTP errors).
- Test suite now covers **56 tests** across 6 files (up from 31).

## [1.5.0] — 2026-03-05

### Changed

- Extracted `hash_password()` helper in `const.py` — replaces 3 duplicated SHA-1 hashing call sites ([#29](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/29)).
- Moved API wire constants (`API_URL_*`, `OUT_MODE_*`, `OUT_STATE_*`, `API_VERSION`, `API_COM_MODE`) from `const.py` to `api.py` where they belong ([#43](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/43)).
- Extracted `setup_discovery()` helper in `entity.py` — replaces triplicated discovery boilerplate across sensor, switch, and number platforms ([#31](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/31)).
- Config entry migration now uses HA's formal `async_migrate_entry` with `VERSION = 2` instead of inline migration in `async_setup_entry` ([#32](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/32)).

## [1.4.0] — 2026-03-05

### Fixed

- Entities now correctly become **unavailable** when their data disappears from the API (all entity types) ([#34](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/34)).
- `SensorStateClass.MEASUREMENT` is now applied per probe type — Cover Position and Generic sensors no longer produce misleading long-term statistics ([#26](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/26)).
- `KlereoParamSensor` now shows human-readable names (e.g. "Filtration Mode") instead of raw API keys ([#27](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/27)).
- `KlereoParamSensor` no longer applies `state_class: MEASUREMENT` indiscriminately.

### Changed

- Switch and number commands now route through `KlereoCoordinator` methods (`async_set_output`, `async_set_param`) instead of calling the API client directly — centralizes error handling and post-command refresh ([#30](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/30)).

## [1.3.1] — 2026-03-05

### Fixed

- Removed broad `except Exception` in coordinator that swallowed programming errors — unexpected exceptions now propagate with full tracebacks ([#46](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/46)).
- Guarded `int(status)` in switch against `ValueError` for non-numeric API responses — logs a warning and defaults to off ([#25](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/25)).
- Excluded `PARAM_TYPES` keys from sensor discovery to prevent duplicate entities (e.g. `ConsigneEau` appearing as both sensor and number) ([#28](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/28)).
- Fixed early return in `_handle_coordinator_update` for `KlereoParamSensor` and `KlereoNumber` — entities now correctly become unavailable when their system disappears from the API instead of keeping stale state ([#24](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/24)).

## [1.3.0] — 2026-02-23

### Added

- **Number entities** — Water temperature setpoint (`ConsigneEau`) as an adjustable number entity (10–40 °C).
- **Diagnostics platform** — Download redacted diagnostic data for troubleshooting.
- **Re-authentication flow** — Expired credentials prompt re-entry instead of requiring removal.
- **Configurable scan interval** — Options flow to set polling interval (1–60 minutes).
- **Dynamic entity discovery** — New probes/outputs are added automatically without restart.
- **CI/CD pipeline** — GitHub Actions for linting (ruff), testing (pytest), and HACS validation.
- **Test suite** — 31 tests covering API client, coordinator, sensors, and switches.
- **KlereoCoordinator** — Dedicated coordinator subclass with parallel API fetching.
- **KlereoEntity base class** — Shared base with DeviceInfo and `has_entity_name`.
- **Type annotations** — Added throughout the codebase.

### Fixed

- Switch status comparison now handles string values from the API (`"1"` / `"0"`).
- `KlereoApiError` (JSON parse errors) no longer incorrectly triggers re-authentication.
- `device_info` uses safe `.get()` to prevent `KeyError` on partial API data.
- `KlereoParamSensor` now has `state_class` for long-term statistics support.
- Narrowed bare `except Exception` to specific error types.
- Normalized config entry `unique_id` to prevent duplicate entries.

### Security

- Credentials stored as SHA-1 hash instead of plaintext, with automatic migration.
- `firebase-debug.log` removed from repository.
- Diagnostics redacts sensitive data from both config entry and coordinator data.

### Changed

- Minimum Home Assistant version bumped to **2024.4** (from 2024.1).
- API client uses `asyncio.Lock` for re-authentication to prevent concurrent login storms.
- API client retries on transient errors (`ClientConnectionError`, `TimeoutError`) with 2s backoff.
- Switch commands wrapped with `HomeAssistantError` and use optimistic state updates.
- O(1) entity lookup via index dicts instead of linear scans.
- Extracted `_parse_response` helper to DRY up JSON parsing in API client.

## [1.2.0] — 2026-02-02

### Fixed

- Fixed broken switch commands — API parameter names were wrong.
- Fixed switch mode value — was sending mode=1 (Time Slots) instead of mode=0 (Manual).
- Fixed stale entities — sensors and switches never updated after initial load.
- Fixed sensor type mapping — types 1 (Air Temp) and 5 (Water Temp) were swapped.

### Added

- Proper error differentiation in config flow (`CannotConnect` vs `InvalidAuth`).
- Unique ID on config entries to prevent duplicate setups.
- Named constants for output modes and states.
- `SensorStateClass.MEASUREMENT` for long-term statistics.
- Config flow translations.

### Removed

- Dead `binary_sensor.py` that never created entities.

## [1.1.0] — Initial HACS Release

### Added

- Probe sensors for water quality monitoring.
- Output switches for pool equipment control.
- Regulation parameter sensors.
- Config flow for credential setup.
