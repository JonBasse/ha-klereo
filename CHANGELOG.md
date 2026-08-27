# Changelog

All notable changes to this project will be documented in this file.

## [1.9.0] — 2026-08-27

### Added

- **A `climate` entity for the heat pump** ([#118](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/118) / [GH #59](https://github.com/JonBasse/ha-klereo/issues/59)). It aggregates what was already exposed separately — the water probe, the `ConsigneEau` setpoint, the KlereoTherm mode and the on/off write — in the form Home Assistant's thermostat card expects. The four KlereoTherm modes map one for one onto Home Assistant's `off` / `auto` / `cool` / `heat`, which is a rename rather than an adaptation.
  - **The existing switch, select and number entities are not replaced.** They are what people have already wired into automations; this one is added beside them.
  - **`hvac_modes` is the same table as the mode select**, shared in one place rather than copied. A thermostat offering `cool` on an on/off heater would be the defect fixed below, more visible — and a second copy of that table is a drift waiting to happen.
  - **Created only where a heating output is actually reported**, and the current temperature is read from the probe Klereo says it regulates on, not from whichever probe happens to report °C first.
  - 🔴 **A disabled water setpoint keeps the entity and drops the target.** Both measured installations report `ConsigneEau: -2000`. The thermostat still shows the water temperature and still switches the pump, rather than pinning a control to -2000 °C or vanishing; a temperature write is refused outright, since a service call can reach an entity that does not advertise the feature.
  - **Turning it on sends *Heating*, never *Auto*** — the 1.5.3 fix carried over rather than re-decided, and right for every heating type including those that cannot do Auto at all.
  - ⚠️ **What this could not be verified against:** the one installation this repository has direct access to has no heating output at all, so no test proves a command reaches a real heat pump. [GitHub #55](https://github.com/JonBasse/ha-klereo/issues/55) is open on exactly that.
  - 26 tests. Six negative controls, each reddening its own witness: copying the mode table instead of sharing it, reading the wrong probe, creating the entity without a heat pump, exposing a sentinel setpoint, turning on into Auto, and setting availability as an attribute.

- **Probe sensors now say which regulation they drive** ([#107](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/107)). A pool often carries two probes reading °C and only one of them is the one the box heats on; Klereo names it, in four fields (`EauCapteur`, `pHCapteur`, `TraitCapteur`, `PressionCapteur`) this integration had never read. They now surface as a `regulation_reference` attribute on the designated probe sensors — an attribute rather than a new entity, since the reading was already exposed and it was its **role** that was missing.
  - Confirmed on a live payload (GitHub [#57](https://github.com/JonBasse/ha-klereo/issues/57), 2026-08-26): `EauCapteur: 16`, `pHCapteur: 17`, `TraitCapteur: 18`, and all three resolve to probes of the matching type.
  - 🔴 **`-1` means "this regulation has no reference probe", not "unknown".** The same payload carries `PressionCapteur: -1` on a pool with no pressure sensor. Both cases end up creating no attribute, so only the log tells them apart: a regulation with no probe stays at debug, while an index naming a probe the payload does not carry is a self-contradicting payload and earns a warning. Confusing the two would cry wolf on every pool without a pressure sensor.
  - It is deliberately **not** `PARAM_SENTINELS`. Those mark a disabled or unknown *setpoint*, and a setpoint of `-1` is a real value — reusing them here would be a false friend that happens to work.
  - The attribute is a list, and **absent** rather than empty on a probe that drives nothing: an empty list reads as a claim that we looked and found none, which is not what an installation sending no reference fields is saying.
  - 10 tests. Four negative controls, each reddening its own witness: treating `-1` as unresolved, emitting the attribute when empty, defaulting an absent field to `0` (a valid probe index), and freezing the attribute at creation instead of re-reading it.

- **Consumption counters and product consumption** — the oldest request on the tracker, open since March and asked by three reporters ([#54](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/54) / [GH #54](https://github.com/JonBasse/ha-klereo/issues/54)).
  - **Run time**, as sensors: filtration, pH- pump, liquid chlorine pump, hybrid chlorine pump and heating, each as *Today* and *Total*, plus chlorine produced by electrolysis. Exposed in the API's own units — **seconds**, and milligrams for the electrolysis — rather than divided down to hours the way the Jeedom plugin does: Home Assistant renders a duration by itself, and a sensor whose value equals the payload is one a bug report can quote.
  - 🔴 **Product consumption in millilitres and litres**, which is what was actually asked for — litres of pH-, not hours of pump. Klereo does not send a volume: it sends a run time and a dosing-pump flow rate, and the app multiplies them. This is the one figure here the API does not carry, and it is the rule the platform now follows: **we compute only what is not on the wire.**
  - **Each sensor appears only if the payload carries its keys**, so an installation shows the equipment it has and nothing else. A consumption sensor additionally needs the flow rate: no flow rate, no consumption entity — and the run-time sensor stays, because it never needed one. That gate is a reading, not a guess.
  - It is also what keeps the two chlorine pumps exclusive. Upstream branches on a `HybrideMode` flag to choose between the liquid and the hybrid pump; the payload already says which one exists, and a second source for a fact we can read directly is a drift waiting to happen.
  - **The keys are admitted by name, never by a `*_TodayTime` suffix rule.** A suffix rule would look identical on all three measured payloads and then admit whatever Klereo adds next, sight unseen — the mistake [#94](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/94) exists to record. Every name comes from the upstream plugin, and every one is now confirmed on a live payload — the flow-rate keys included, read in [GitHub #55](https://github.com/JonBasse/ha-klereo/issues/55) on 2026-08-26.
  - ⚠️ **No pH+ counter exists.** The original report asked for pH+ alongside pH- and chlorine; neither the upstream plugin nor any measured payload carries one.
  - 17 tests. Five negative controls, each reddening its own witness: removing the flow-rate gate, dropping the counter units, removing the curated list, swapping the daily and total divisors, and turning an unreadable reading into `0` instead of unknown.

### Fixed

- 🔴 **The heating output offered `Auto` and `Cooling` to hardware that has neither.** Output 4's mode select handed out all four KlereoTherm modes regardless of the heating type installed, so an on/off heater was offered *Cooling* ([#124](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/124)). Upstream has never done this: `klereo.class.php` l.929 builds the list from `HeaterMode`, and only 2 (KlereoTherm heat pump) and 4 (other heat pump) get Auto and Cooling. Type 1 — a heat pump *or* an on/off heater — is what the measured installation has.
  - 🔴 **Nothing signalled it, and nothing could have.** Picking the inert option gets `{"status":"ok"}` and a box status of 9. There is no refusal to catch: it is a command the hardware accepts and does not execute. ⚠️ The two-step confirmation repaired in 1.8.0 ([#115](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/115)) reads that 9 and **confirms** it — verification proves transmission, never effect. Third occurrence of the same shape, after [#104](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/104) and [#105](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/105).
  - **An unknown heating type still gets all four modes.** The gate is written as a positive list of the types *known* to be heat-only — 0, 1 and 3 — which is the inverse of upstream's "everything that is not 2 or 4". The two differ exactly on a value we cannot read, and there over-filtering is the dangerous direction: it would delete a control an installation uses today, to fix an option that is merely inert. Same rule as [#94](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/94) and #104, biting the other way round.
  - **Offering is narrowed; reading is not.** A heat-only installation that nevertheless *reports* Cooling is still shown as Cooling. Refusing to read a mode we chose not to offer would turn "our gate is wrong here" into "unknown" — the #105 failure, one level up — and that report is the only signal that the gate is mis-typed.
  - The gate is re-read on every refresh, not only at discovery: an entity is created once, so a `HeaterMode` arriving in a later payload would otherwise never take effect.
  - It does **not** touch output 4's switch. Turning an on/off heater on with `HEAT_MODE_HEATING` stays correct for every type — that is the 1.5.3 fix. It does not guess `aqPACType` either; no measured payload carries it.
  - 16 tests. Two negative controls, one per direction, and they discriminate: neutralising the filter reddens the three heat-only types and nothing else; treating an *unknown* type as heat-only reddens the "unknown never bars" arms **and two pre-existing tests** — which is the harm made visible, since those fixtures are installations carrying no `HeaterMode` at all.

- **A release's three places can no longer diverge in silence** ([#101](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/101)). Publishing correctly requires `manifest.json`, a `CHANGELOG.md` section and a `vX.Y.Z` tag to say the same number, and nothing verified it. `scripts/check_release_agreement.py` now does, as a CI job on every push.
  - **It checks every tag, not only the current version.** Checking the manifest alone would not have caught **v1.5.2 — tagged and published with no CHANGELOG section at all**, because by the time anyone looked the manifest had moved on. ⚠️ That section is **not** invented retroactively: its content is lost, a plausible one would turn a visible hole into a false certainty, and it is allowlisted instead — which keeps the check able to fail on a *new* hole rather than being permanently red.
  - 🔴 **No tags found is a failure, never a pass.** A shallow checkout leaves nothing to disagree, so the check would otherwise report success having verified nothing.
  - **The published half is a ritual step, not a CI job, and that is measured rather than chosen.** The issue proposed a `release: [published]` trigger; this repository has **zero** Forgejo releases — only tags — so that trigger would never fire, and a check that cannot fire is worse than none.
  - 🔴 **Its first version reported a correctly-published release as broken.** It compared a local *commit* sha against GitHub's *tag object* sha, which differ on an annotated tag — every tag here is one. Both unit-test fixtures agreed with whatever the code asked them for; only running it against the real v1.8.1 showed it. The check now resolves the ref to a commit on both sides.
  - `CLAUDE.md` points at the script instead of describing it — prose describing a control is what #89 already cost this repository once.
  - ⚠️ **Its first CI run went red, and the guard was right.** `actions/checkout` fetches no tags by default, so a test that swept them found none and the "no tags" guard fired in the `test` job. The lesson is about the test, not the guard: a unit test must not depend on how the job running it checks out the repository. The tag sweep is covered by fixtures and by the job whose checkout sets `fetch-depth: 0` for exactly this reason.
  - 19 tests, plus the negative control the issue asked for, run against the real tree: bumping `manifest.json` without touching `CHANGELOG.md` fails the check, removing v1.5.2 from the allowlist fails it, and both real published releases pass.

- **The new `climate` entity reports availability through a property, not `_attr_available`.** `CoordinatorEntity.available` is itself a property, so it shadows that attribute entirely and assigning to it changes nothing an entity ever reports. 🔴 **The integration's other five platforms all do exactly that**, so their entities never go unavailable when their probe or output disappears from the payload — and nine tests assert the attribute the code just assigned, staying green over a mechanism that does nothing. Measured 2026-08-26 with a positive control, and filed as [#130](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/130) rather than repaired here: fixing it changes what five platforms report, which deserves its own release note and not a line in a feature PR.

### Changed

- **The README explains what to do when an entity's ID does not match its name** ([#121](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/121)). Home Assistant derives an entity ID from its name once, at creation, and never revisits it — so an installation set up before v1.5.2, when two probe types were mapped to each other's names, still carries `sensor.klereo_water_temperature` on its **air** probe. The displayed name has been right since the fix; the ID is frozen wrong for good.
  - 🔴 **Nothing looks wrong.** Both entities exist, carry plausible readings in the right unit, and the UI shows the name, which is correct. It only bites someone who writes the entity ID into a template or an automation and quietly gets the other probe — a pool reading 23.7 °C instead of 28.3 °C is credible in any season.
  - The note **explains how to tell the two readings apart from the values themselves**, rather than asking anyone to take a name on trust: water has a large thermal mass and barely moves, air swings several degrees across a day. The steadier one is the water. Being the warmer one is *not* a reliable test — an unheated pool on a hot afternoon is the cooler of the two.
  - **A note, not a `repairs` entry.** Renaming entity IDs from code would break the automations the freeze exists to protect, and nothing distinguishes an ID frozen wrong from one the user chose. A repair flow firing on someone who renamed their entities deliberately would be a new nuisance in exchange for a defect nobody has reported.
  - A test now pins the two probe-type names explicitly, so the inversion cannot come back: it would be invisible on screen for existing users and permanent for new ones. An entity name is a public API from the first install onwards.
- The README no longer says which settings container an installation returns "has never been measured". It has been, three times, and installations differ: `RegulModes` and `params` are always present, `ExtraParams` on some installations only.

## [1.8.1] — 2026-08-26

### Security

- 🔴 **Diagnostics exports leaked the account username, the box `pin` and Klereo's customer reference.** Redaction covered the password and the session token and nothing else — so an export contained `username` in clear, which is the half of the credential the password is not ([#122](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/122)).
  - This is not theoretical exposure: the project **asks reporters to paste diagnostics into public issues** on the strength of "credentials are redacted automatically". Anyone who did as they were told published their login.
  - ⚠️ **A user had already judged this correctly.** Pasting a payload in GitHub [#57](https://github.com/JonBasse/ha-klereo/issues/57), the reporter hand-redacted `pin`, `compta` and the pool nickname to `XXX` rather than trust the promise. `TO_REDACT` now encodes his judgement.
  - `username`, `pin`, `compta`, `idAddress`, `podSerial`, `Address` and `emailNotify` are now redacted. The system id, pool nickname, access level and every probe/output/parameter reading are deliberately **not** — an export redacted into uselessness is one nobody pastes, and the export is what unblocks these reports.
  - The README now **lists** what is and is not redacted instead of promising "sensitive data", and warns that a raw **debug log** carries no redaction at all.
  - 🔴 **Exports already published are not repaired by this.** Redaction happens at generation time; a file pasted yesterday still reads as it did.
  - 6 tests, one per field rather than one batch — a batch that loses a field to a typo still passes on the others, which is how a redaction set comes to cover less than it claims. The negative control is that over-redacting the system id or pool nickname reddens its own test: breaking the export would not be a fix.

## [1.8.0] — 2026-08-26

### Fixed

- 🔴 **Command confirmation never fired — on any install, since 1.6.0.** 1.7.0 fixed `_command_id` to read the `response` shapes `docs/klereo-api.md` documents, and left `_command_status` reading only the bare integer and the JSON array. The first payload anyone has **measured** (GitHub [#55](https://github.com/JonBasse/ha-klereo/issues/55), 2026-08-26, four samples) is neither: `response` is a single **object**, `{"cmdID": …, "status": 9, "startTime": …, "updateTime": …, "detail": "Ok"}`. It fell through to "no status", so every write logged `unreadable command status` and returned unconfirmed ([#115](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/115)).
  - The cost is not the log line: a **status 13 (insufficient rights) never raised**, which is the exact silent failure `#95` built this mechanism to remove, and `#104` later had to work around at the gating level. Statuses 10, 11, 17 and 19 were equally mute.
  - **The object form is now read**, matched on `cmdID` the way the array branch already was. A `cmdID` naming a *different* command disqualifies the verdict; a missing one does not, since no install has been measured to always send it.
  - Reading a third shape cannot regress the two already read — the same property that made 1.7.0's change safe without hardware.
- 🔴 **Why 11 passing tests proved nothing.** Every test in `TestCommandConfirmation` and `TestDocumentedListShape` builds its own fixture from the two *assumed* shapes, so all of them stayed green while the mechanism was inert. A test whose fixture is the assumption it should be controlling discriminates nothing. The 6 new tests quote the reported payload **verbatim**, and the negative control is that removing the `cmdID` guard reddens exactly the one test written for it.
- This does **not** explain the heat pump that still fails to start on a status 9, also reported in GH #55. The verdict becomes readable; it does not become different.

### Changed

- **The debug line that records the payload shape now logs what each setting container CARRIES**, not only that it is present. Its first real reading (GitHub [#57](https://github.com/JonBasse/ha-klereo/issues/57), 2026-08-26) showed `RegulModes`, `params` and `ExtraParams` **all three present in the same response** — which retires the "which container does this installation return?" framing of [#94](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/94) and leaves the question that actually blocks [#54](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/54) untouched: which *keys* each of them carries.
  - 🔴 An instrument one level too shallow reads as an answer. This line was added in 1.6.0 precisely so the next report would be a measurement rather than a guess; it cost a second round-trip to a reporter anyway, because top-level names cannot say where `ConsigneEau` or the consumption counters live.
  - A container the payload **omits** is not logged, rather than logged as empty — "not sent" and "sent empty" are different facts about the API, and telling them apart is the whole point of the line.
  - The three container names are now one constant, pinned by a test to the merge order `settings` implements. Nothing else stopped a comment from asserting the opposite of the code beside it, which this project has shipped once already.

### Added

- **Klereo's alerts are now a sensor.** `state` is the number of active alerts, and the full list — code, label, the meaning of its parameter, `level`, timestamp — is in its attributes, so `> 0` is a trigger and the attributes say what is wrong ([#57](https://forgejo.dragonlance.xyz/JonBasse/ha-klereo/issues/57), requested by an external reporter who also chose this shape over one entity per alert code).
  - ~50 alert labels ported from the upstream Jeedom plugin. `docs/klereo-api.md` does not document alerts at all — its field lists are elided — so upstream is the only source, cross-checked against the one payload anyone has measured (GitHub [#57](https://github.com/JonBasse/ha-klereo/issues/57), 2026-08-26).
  - 🔴 **The state is `len(alerts)`, never Klereo's `alertCount`.** The measured payload carries `alertCount: 0` beside one active alert — the reporter noticed it himself. Reading that field would show a healthy `0` over a real alert, on the entity whose whole job is to not be a false green. Upstream computes the count the same way; the reported figure is exposed as an attribute so a divergence stays visible instead of silent.
  - 🔴 **`param` means a different thing per code**, and rendering it raw would be wrong for most: a probe index for 1, 7, 8, 10 and 36; a flow id for 13 and 14; an output index for 35; an error code for 50-52, 54 and 61; a pump id for 53. Probe and output params resolve against **this installation's own** payload rather than a ported lookup table. A code with no documented `param` meaning gets no description rather than a plausible one.
  - **The entity exists even when nothing is wrong.** The `alerts` key is *absent* from a healthy payload, not present and empty, so keying the entity on it would create a sensor that appears only during a fault and takes its history away on recovery.
  - An alert code absent from the table is counted and shown by its number. The upstream table has real gaps and Klereo can add codes; dropping an unknown alert would hide a real one.
- 6 tests for the measured object shape, 25 for the alert sensor and 4 for the payload instrument (**191 total**, up from 156).

## [1.7.0] — 2026-08-25

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

### Added

- **Klereo's own API documentation is now committed** at [`docs/klereo-api.md`](docs/klereo-api.md) — supplied by the reporter of [GH #58](https://github.com/JonBasse/ha-klereo/issues/58) on 2026-08-24 and, until then, held only in a tracker comment. Everything this integration knew about the wire format came from re-implementing the Jeedom plugin or from guessing; this is the first primary source. Its header states what it leaves open, including the setpoint-container question it does **not** settle.
- 28 tests across the three fixes (**156 total**, up from 128).

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
