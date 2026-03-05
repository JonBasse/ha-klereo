# Changelog

All notable changes to this project will be documented in this file.

## [1.5.0] — 2026-03-05

### Changed

- Extracted `hash_password()` helper in `const.py` — replaces 3 duplicated SHA-1 hashing call sites ([#29](https://github.com/JonBasse/ha-klereo/issues/29)).
- Moved API wire constants (`API_URL_*`, `OUT_MODE_*`, `OUT_STATE_*`, `API_VERSION`, `API_COM_MODE`) from `const.py` to `api.py` where they belong ([#43](https://github.com/JonBasse/ha-klereo/issues/43)).
- Extracted `setup_discovery()` helper in `entity.py` — replaces triplicated discovery boilerplate across sensor, switch, and number platforms ([#31](https://github.com/JonBasse/ha-klereo/issues/31)).
- Config entry migration now uses HA's formal `async_migrate_entry` with `VERSION = 2` instead of inline migration in `async_setup_entry` ([#32](https://github.com/JonBasse/ha-klereo/issues/32)).

## [1.4.0] — 2026-03-05

### Fixed

- Entities now correctly become **unavailable** when their data disappears from the API (all entity types) ([#34](https://github.com/JonBasse/ha-klereo/issues/34)).
- `SensorStateClass.MEASUREMENT` is now applied per probe type — Cover Position and Generic sensors no longer produce misleading long-term statistics ([#26](https://github.com/JonBasse/ha-klereo/issues/26)).
- `KlereoParamSensor` now shows human-readable names (e.g. "Filtration Mode") instead of raw API keys ([#27](https://github.com/JonBasse/ha-klereo/issues/27)).
- `KlereoParamSensor` no longer applies `state_class: MEASUREMENT` indiscriminately.

### Changed

- Switch and number commands now route through `KlereoCoordinator` methods (`async_set_output`, `async_set_param`) instead of calling the API client directly — centralizes error handling and post-command refresh ([#30](https://github.com/JonBasse/ha-klereo/issues/30)).

## [1.3.1] — 2026-03-05

### Fixed

- Removed broad `except Exception` in coordinator that swallowed programming errors — unexpected exceptions now propagate with full tracebacks ([#46](https://github.com/JonBasse/ha-klereo/issues/46)).
- Guarded `int(status)` in switch against `ValueError` for non-numeric API responses — logs a warning and defaults to off ([#25](https://github.com/JonBasse/ha-klereo/issues/25)).
- Excluded `PARAM_TYPES` keys from sensor discovery to prevent duplicate entities (e.g. `ConsigneEau` appearing as both sensor and number) ([#28](https://github.com/JonBasse/ha-klereo/issues/28)).
- Fixed early return in `_handle_coordinator_update` for `KlereoParamSensor` and `KlereoNumber` — entities now correctly become unavailable when their system disappears from the API instead of keeping stale state ([#24](https://github.com/JonBasse/ha-klereo/issues/24)).

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
