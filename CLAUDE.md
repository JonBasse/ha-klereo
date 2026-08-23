# CLAUDE.md — ha-klereo

Home Assistant custom integration for the [Klereo Connect](https://connect.klereo.fr) pool
management system. Cloud-polling, no local API. Ported from MrWaloo's
[Jeedom plugin](https://github.com/MrWaloo/jeedom-klereo). User-facing docs: [`README.md`](README.md).

## Memory (Hindsight) — ALWAYS FIRST

**Before any task**, `mcp__hindsight__recall` with a task-specific query (full rule + MCP endpoint
in the global CLAUDE.md). Bank is `fizbot`, shared across runtimes. Never call `retain` manually.

---

## Hosting — read this before touching any issue, PR or branch

> ⚠️ **The default branch is `master`, not `main`.** This is the only repo in the constellation
> where that holds. Every fleet recipe hard-coded on `main` — a `--base`, a `git diff main…`, a
> comparison point — is wrong here, and most of them fail on the wrong ref rather than loudly.

> ⚠️ **GitHub is NOT a locked tombstone here — it is the distribution channel, and it is live.**
> The fleet-wide rule ("Forgejo canonical, GitHub demoted to a push-mirror whose issues are locked
> tombstones") holds for hosting but **not** for this repo's GitHub issues. Measured 2026-08-10:
> `JonBasse/ha-klereo` on GitHub is public, unarchived, `has_issues: true`, last pushed
> 2026-08-08, and carries **53 issues — one of them open (#58) and filed by an external user**.
> That is not drift: `custom_components/klereo/manifest.json` advertises
> `issue_tracker: https://github.com/JonBasse/ha-klereo/issues` to every HACS install, so that is
> where users legitimately report bugs. **Reading GitHub issues here is correct**; blanket-applying
> "never `gh`" silently discards the only inbound channel this integration has.

| | Forgejo (canonical) | GitHub |
|---|---|---|
| URL | `forgejo.dragonlance.xyz/JonBasse/ha-klereo` | `github.com/JonBasse/ha-klereo` |
| Registered as | `backend: forgejo` in fizbot `src/fizbot_data/repos.yaml` | — |
| Issues | the owner's backlog — `fb-issue backlog ha-klereo`, `fb-issue new` | **inbound user bug reports**, read them |
| Releases | tags | **releases HACS installs from** |
| CI | `.forgejo/workflows/` | none — `.github/` was deleted (`e402f36`) |

> ⚠️ **Issue numbers DIVERGE between the two — a bare `#38` is ambiguous.** Forgejo is at #83 and
> GitHub at #58 (2026-08-10); they were the same repo before the migration, so low numbers collide
> and resolve to *different* issues. Always qualify: `JonBasse/ha-klereo#38 (Forgejo)` or a full
> URL. `CHANGELOG.md` links Forgejo throughout.

Backend routing (which CLI, which token, never guess): load the `managing-forgejo` skill. Short
version — `tea` for everything issue/PR, **read and write** · `fj` when the body is Markdown-heavy
(`--body-file`) · `gh` **only** to read the GitHub-side user reports and releases.

---

## HACS status — custom repository, NOT the default catalogue

Users install by adding `https://github.com/JonBasse/ha-klereo` as a **custom repository**
(procedure in `README.md`). The default-catalogue submission
[hacs/default#6025](https://github.com/hacs/default/pull/6025) was **closed as stale on
2026-08-01** by frenck and never merged; it is re-openable if the work is picked up again.
Anything claiming "submitted, awaiting acceptance" is stale — that state ended 2026-08-01.

> ⚠️ **The `hacs` and `hassfest` validation jobs currently run NOWHERE.** They were GitHub-only by
> nature (`hacs/action` validates against github.com's API view of the repo; hassfest's
> workspace-mount convention doesn't hold on the self-hosted runner), so they were deliberately
> omitted from `.forgejo/workflows/validate.yml` — whose header comment still says they "remain in
> `.github/workflows/validate.yml`". **That comment is stale:** `.github/` was deleted in
> `e402f36`. Re-run them on GitHub before any renewed HACS-catalogue attempt; nothing here
> currently checks HACS conformance.

---

## Architecture

API base `https://connect.klereo.fr/php`. Everything lives under `custom_components/klereo/`.

- **`models.py`** — typed dataclasses (`KlereoProbe`, `KlereoOutput`, `KlereoSystemData`, …).
  The coordinator returns `dict[str, KlereoSystemData]`, **never raw API dicts** — keep it that way.
- **`coordinator.py`** — `KlereoCoordinator`. **Commands route through coordinator methods, never
  `coordinator.api` directly** from a platform module.
- **`api.py`** — auth is SHA-1 password hash + JWT, with an `asyncio.Lock` on re-auth and automatic
  retry on 401/transient errors. Wire constants (`API_URL_*`, `OUT_MODE_*`, `OUT_STATE_*`) live
  here, not in `const.py`.
- **`entity.py`** — `KlereoEntity` base (DeviceInfo) + `setup_discovery()`, the shared helper for
  dynamic entity creation. Entities appear without a restart.

Six platforms: `sensor` (probes + regulation params) · `binary_sensor` · `switch` (always forces
Manual mode) · `select` (output mode) · `number` (writable setpoints) · `diagnostics` (redacted).

> ⚠️ **Setpoints live in TWO containers and which one your API returns is unmeasured.** `RegulModes`
> was guessed (the introducing commit says so in its own comment) and appears nowhere upstream, which
> reads every setpoint from `params`. Both are read, `RegulModes` winning on conflict so the read can
> only add. `params` reaches `sensor` only through the curated `PARAM_NAMES` list — it carries dozens
> of counters and bounds, and taking every key would flood each install with entities. See #94.

---

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/ -v     # 77 tests / 9 files, all green 2026-08-10
.venv/bin/ruff check .
```

- **Always `.venv/bin/pip`, never the system pip.**
- ⚠️ **A fresh worktree gets an EMPTY `.venv` here.** Anything that provisions via `uv sync`
  finds nothing to install: this `pyproject.toml` declares no `[project]` — only `[tool.pytest]`
  and `[tool.ruff]`. Dev deps live in `requirements-dev.txt` (pinned, Renovate-tracked). Install
  them yourself in the worktree, or run the main checkout's
  `~/Projects/ha-klereo/.venv/bin/pytest` against it.
- ruff: `target-version = "py314"`, `line-length = 120`, `select = ["E","F","W","I","UP"]`.
- `docs/plans/` is **gitignored** — internal scratch, never committed.
- Dependencies are bumped by Renovate against the shared `local>platform/renovate` preset.

**Releasing** — three places must agree, and nothing enforces it: the `version` field in
`custom_components/klereo/manifest.json`, a `## [X.Y.Z]` section in `CHANGELOG.md`, and a `vX.Y.Z`
tag. HACS reads the **GitHub release**, so a tag that never reaches GitHub ships to nobody.

---

## Conventions

Cross-repo rules are canonical in fizbot — **edit them there, not here**:

- **Worktrees** — every non-default branch lives in `.worktrees/<issue>-<topic>/`; direct commits to
  `master` stay allowed for one-offs and docs. fizbot `docs/development-conventions.md`
  § *One branch = one worktree*.
- **Plan/spec lifecycle** — delete `docs/superpowers/{plans,specs}` in the merging PR; git history is
  the archive. Same file, § *Plan/spec lifecycle*.
- **Commits** — `git add <paths>` naming every path, then `git commit`. Never `git add .`, never
  `git commit -am`, never a bare `git commit` with implicit staging: a concurrent session shares
  the index.
- **Secrets** — none in this repo (public). CI runs `gitleaks` on every push and PR with
  pre-existing findings baselined in `.gitleaksignore`; diagnostics redact credentials via
  `TO_REDACT`. Never add a real Klereo credential to a test fixture.
- **`.claude/` layout** — `.claude/settings.local.json` and `.worktrees/` are gitignored (both
  present in `.gitignore`); this file is committed; there is no `.claude/settings.json`.
