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
| CI | `.forgejo/workflows/` — `lint`, `test`, `gitleaks` | `.github/workflows/validate.yml` — `hacs`, `hassfest` (#89) |

> ⚠️ **Issue numbers DIVERGE between the two — a bare `#38` is ambiguous.** Forgejo is at #83 and
> GitHub at #58 (2026-08-10); they were the same repo before the migration, so low numbers collide
> and resolve to *different* issues. Always qualify: `JonBasse/ha-klereo#38 (Forgejo)` or a full
> URL. `CHANGELOG.md` links Forgejo throughout.

Backend routing (which CLI, which token, never guess): load the `managing-forgejo` skill. Short
version — `tea` for everything issue/PR, **read and write** · `fj` when the body is Markdown-heavy
(`--body-file`) · `gh` **only** to read the GitHub-side user reports and releases.

---

## HACS status — custom repository today, default-catalogue submission OPEN

Users install by adding `https://github.com/JonBasse/ha-klereo` as a **custom repository**
(procedure in `README.md`). That is how every current user got it, and it keeps working whatever
happens to the submission below.

**Default-catalogue submission: [hacs/default#10263](https://github.com/hacs/default/pull/10263)**,
opened 2026-08-23, **12/12 checks green**, tracked in #102. Expect **months**, not weeks — the queue
is ~720 PRs deep and sorts oldest-first.

⚠️ It replaces `hacs/default#6025` (2026-03-07, closed as stale 2026-08-01 with an invitation to
reopen). **#6025 is NOT re-openable** — its branch had to be rebased and GitHub refuses to reopen a
PR whose branch was force-pushed, permanently. Anything saying otherwise is stale.

🔴 **Never delete `.github/workflows/validate.yml` while a submission is in the queue.** HACS
requires the actions to be passing **at review time**, not at submission time. Deleting that file on
2026-07-15 silently voided the requirement for the last six weeks of #6025's wait, with no signal
anywhere. See #89 and #102.

> **The `hacs` and `hassfest` jobs run on GitHub, and only there.** `hacs/action` validates
> github.com's API view of the repository, so it cannot validate a repo it sees only through
> Forgejo. The split is disjoint on purpose — `lint` + `test` + `gitleaks` on Forgejo,
> `hacs` + `hassfest` in `.github/workflows/validate.yml` — so Renovate has nothing to bump twice,
> which was the objection that deleted the file in `e402f36`.
>
> ⚠️ **There is deliberately NO `pull_request:` trigger in the GitHub workflow.** Pull requests live
> on Forgejo; github.com never sees one, so a `pull_request` trigger there would describe a check
> that cannot run. The trigger is an unfiltered `push:` — every branch is mirrored, so the verdict
> arrives before a Forgejo merge, just not as a Forgejo check.
>
> 🔴 **Two things gate this, and both are credentials, not CI config** — measured 2026-08-23 (#89):
> the push-mirror had to move off the classic `pat_git_mirror` (scope `repo`, **no** `workflow`,
> so GitHub rejected the *entire ref*, freezing HACS distribution) onto **SSH + a per-repo deploy
> key**; and repo-level GitHub Actions had to be re-enabled — `actions/permissions.enabled` was
> `false` from the 2026-06-25 minutes sweep. ⚠️ `repos/{o}/{r}.disabled` is **not** that field and
> reading it says nothing; probe `GET repos/{o}/{r}/actions/permissions`. Re-enabling costs zero
> minutes: `ha-klereo` is the fleet's only **public** repo, and Actions minutes are free there.

---

## Architecture

API base `https://connect.klereo.fr/php`. Everything lives under `custom_components/klereo/`.

> 📘 **Klereo's own API documentation is committed at [`docs/klereo-api.md`](docs/klereo-api.md)**
> — obtained 2026-08-24 from the reporter of GitHub #58, and the only official source this project
> has. Read it before inferring anything about the wire from the Jeedom plugin. ⚠️ Its field lists
> for `GetIndex` / `GetPoolsDetails` are **elided in the source**, so it does **not** settle the
> setpoint-container question below — that file's header names what it leaves open.

- **`models.py`** — typed dataclasses (`KlereoProbe`, `KlereoOutput`, `KlereoSystemData`, …).
  The coordinator returns `dict[str, KlereoSystemData]`, **never raw API dicts** — keep it that way.
- **`coordinator.py`** — `KlereoCoordinator`. **Commands route through coordinator methods, never
  `coordinator.api` directly** from a platform module.
- **`api.py`** — auth is SHA-1 password hash + JWT, with an `asyncio.Lock` on re-auth and automatic
  retry on 401/transient errors. Wire constants (`API_URL_*`, `OUT_MODE_*`, `OUT_STATE_*`) live
  here, not in `const.py`.

  > ⚠️ **Every write is a TWO-step protocol.** `SetOut` / `SetParam` only *queue* a command and
  > return a cmdID; `WaitCommand` says what actually happened. An HTTP 200 on step one is not a
  > result — status `13` (insufficient rights) reads identically to success on the wire. Route
  > writes through `KlereoCoordinator._async_confirm_command`, never straight at `api.set_*`. See
  > #95.
- **`entity.py`** — `KlereoEntity` base (DeviceInfo) + `setup_discovery()`, the shared helper for
  dynamic entity creation. Entities appear without a restart.
- **`diagnostics.py`** — the **only remote instrument this project has**, and reporters are asked
  to paste it into **public** issues. It exports the typed models *and* the raw `GetPoolDetails`
  payload (`details.raw`, #145), because an export limited to the models is blind to every field
  the parser drops — seven of the eleven on each `outs[]` element, `realStatus` among them.

  > 🔴 `TO_REDACT` is a **security claim**, not a convenience, and the raw payload publishes an
  > object whose key list comes from the server. **A key nobody has judged is not a safe key** —
  > that was the fault of #122. Every key of that payload carries a written verdict in the file;
  > `register` and `podinfo` are redacted to their **key names only**, never blanked, so the next
  > export anyone pastes can still settle what they contain without the owner's credentials.

Six platforms: `sensor` (probes + regulation params) · `binary_sensor` · `switch` (always forces
Manual mode) · `select` (output mode) · `number` (writable setpoints) · `diagnostics` (redacted).

> ⚠️ **Setpoints live in THREE containers, and which one your API returns is still unmeasured.**
> `RegulModes` was guessed (the introducing commit says so in its own comment) and appears nowhere
> upstream, which reads every setpoint from `params`; `ExtraParams` was named by an external
> reporter reading their own diagnostic export (GH #54, 2026-06-17) — the only real payload anyone
> has measured here. All three are read, precedence `RegulModes` > `params` > `ExtraParams`, so the
> read can only *add*, never alter a value an install already shows.
>
> `params` and `ExtraParams` reach `sensor` only through the curated `PARAM_NAMES` list — they carry
> dozens of counters and bounds, and taking every key would flood each install with entities.
> `regul_modes` stays unfiltered: narrowing it would **delete** entities users have. See #94.

---

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/ -v     # 128 tests / 10 files, all green 2026-08-23
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

**Releasing** — three places must agree: the `version` field in
`custom_components/klereo/manifest.json`, a `## [X.Y.Z]` section in `CHANGELOG.md`, and a `vX.Y.Z`
tag. HACS reads the **GitHub release**, so a tag that never reaches GitHub ships to nobody.

`scripts/check_release_agreement.py` is the instrument — read it rather than this paragraph, and
run it rather than checking by hand (#101):

```bash
.venv/bin/python scripts/check_release_agreement.py              # CI runs this on every push
.venv/bin/python scripts/check_release_agreement.py --published 1.8.1   # AFTER the GitHub release
```

The first half runs as the `Validate / release-agreement` job. The second is **not** a job and is
not one by measurement, not by omission: this repo has **zero Forgejo releases** — only tags — so a
`release: [published]` trigger would never fire, and a `push: tags` one races both the mirror and
the human who creates the GitHub release afterwards. Run it by hand as the last step of the ritual.

⚠️ Convention between releases: a fix PR writes `## [Unreleased]`, and the `chore(release):` commit
renames that heading **and** bumps `manifest.json` in the same commit. `[Unreleased]` is deliberately
not read as a version, so a release that never stamped its number fails the check.

⚠️ **v1.5.2 is tagged and published with no CHANGELOG section**, and its content is lost. It is
allowlisted in `KNOWN_MISSING_CHANGELOG`. Do **not** invent that section — a plausible one would
turn a visible hole into a false certainty. The allowlist is what keeps the check able to fail on a
new hole instead of being permanently red.

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
