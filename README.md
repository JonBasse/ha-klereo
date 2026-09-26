# Klereo Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/JonBasse/ha-klereo.svg)](https://github.com/JonBasse/ha-klereo/releases)
[![Validate](https://github.com/JonBasse/ha-klereo/actions/workflows/validate.yml/badge.svg)](https://github.com/JonBasse/ha-klereo/actions/workflows/validate.yml)

A Home Assistant custom integration for the [Klereo Connect](https://connect.klereo.fr) pool management system. Monitor water quality parameters and control pool equipment directly from Home Assistant.

This integration is a port of the [Jeedom Klereo plugin](https://github.com/MrWaloo/jeedom-klereo) by MrWaloo.

## Features

- **Probe sensors** — Water temperature, air temperature, pH, redox (ORP), filter pressure, flow rate, chlorine level, container levels, and more.
- **Equipment switches** — Control lighting, filtration, heating, and auxiliary outputs (on/off) with optimistic state updates.
- **Variable-speed ("analogue") Filtration pump control** — A speed slider bounded to your own pump's maximum, for pools whose box reports one, plus optional read-only telemetry sensors (power, RPM, flow, and more). See [below](#pump-speed-filtration-output).
- **Adjustable setpoints** — Water temperature setpoint exposed as a number entity you can adjust directly from the UI.
- **Auto-off timers** — Each output's *Temps minuterie* exposed as a number entity in minutes, adjustable from the UI.
- **Regulation parameters** — View regulation modes and setpoints as read-only sensors.
- **Manual refresh** — A **Refresh from Klereo** button per pool re-reads the cloud on demand, exactly as the button in Klereo's own web interface does.
- **Automatic discovery** — All pool systems, probes, and outputs are discovered automatically from your Klereo account. New entities are added dynamically without requiring a restart.
- **Cloud polling** — Data refreshed from the Klereo Connect cloud API at a configurable interval (10–60 minutes, default 10).
- **Diagnostics** — Built-in diagnostics support for troubleshooting, with automatic redaction of sensitive data.
- **Re-authentication** — If your credentials expire, the integration prompts you to re-enter them instead of requiring a full removal and re-setup.

## Prerequisites

- A [Klereo Connect](https://connect.klereo.fr) account with at least one pool system.
- Home Assistant 2024.4 or later.

## Installation

### HACS (Recommended)

1. Open **HACS** in your Home Assistant sidebar.
2. Go to **Integrations**.
3. Click the three-dot menu in the top right and select **Custom repositories**.
4. Add the URL `https://github.com/JonBasse/ha-klereo` and select **Integration** as the category.
5. Search for **Klereo** in the HACS integrations list and install it.
6. Restart Home Assistant.

### Manual

1. Download the [latest release](https://github.com/JonBasse/ha-klereo/releases).
2. Copy the `custom_components/klereo` directory into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration

1. Go to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **Klereo**.
3. Enter your Klereo Connect **username** and password — the same ones you use on [connect.klereo.fr](https://connect.klereo.fr).

   ⚠️ **This is the username, not your e-mail address.** Klereo's own app accepts either at
   sign-in, but this API only matches the username: an e-mail address logs in successfully and
   then returns **no pools at all**. If setup reports that no pool is attached to your account,
   this is why.
4. Click **Submit**.

Your pool systems, sensors, switches, and number entities will be created automatically.

### Options

After setup, you can configure the integration by clicking **Configure** on the integration card:

- **Update interval** — How often to poll the Klereo API (10–60 minutes, default 10).
- **Equipment power (W)** — One field per piece of equipment (filtration pump, heating, dosing pumps). Klereo
  sends no power reading at all, so this figure is yours: read it off the equipment's rating plate, or measure
  it. Filling one in creates the matching **energy** sensors below. Leaving one empty creates none — the
  integration never invents a power, because a plausible default would put a credible kWh figure, in a unit that
  has a price, into the dashboard you use to decide.

## Entities

### Sensors

Probe sensors are created for each probe reported by your Klereo system. The following probe types are recognized:

| Probe Type | Name | Unit |
|---|---|---|
| 0 | Technical Room Temperature | °C |
| 1 | Air Temperature | °C |
| 2 | Water Level | % |
| 3 | pH | — |
| 4 | Redox (ORP) | mV |
| 5 | Water Temperature | °C |
| 6 | Filter Pressure | mbar |
| 10 | Generic | % |
| 11 | Flow | m³/h |
| 12 | Container Level | % |
| 13 | Cover Position | % |
| 14 | Chlorine | mg/L |

Probes with unrecognized types are still created with a generic name (e.g. "Sensor 3").

#### Which probe drives which regulation

A pool often carries more than one probe of the same kind — a water temperature probe and an air
temperature probe both read °C — and only one of them is the one your Klereo box actually regulates
on. The box says which, and probe sensors carry it as a `regulation_reference` attribute:

| Value | Meaning |
|---|---|
| `water_temperature` | this probe is the reference for heating regulation |
| `ph` | this probe is the reference for pH regulation |
| `disinfectant` | this probe is the reference for chlorine / redox regulation |
| `pressure` | this probe is the reference for pressure regulation |

The attribute is a **list**, because in principle one probe could drive more than one loop, and it is
**absent** on any probe that drives none — which is most of them. In a template:

```jinja
{{ 'water_temperature' in (state_attr('sensor.klereo_water_temperature', 'regulation_reference') or []) }}
```

Not every installation reports these fields, and a regulation your pool does not have — pressure, on a
pool with no pressure sensor — simply names no probe. In both cases the attribute is absent, and no
sensor changes.

Additionally, regulation parameters from your pool data are exposed as read-only sensors. They are read from all
three containers the API is known to use — `RegulModes`, `params` and `ExtraParams` — because installations differ
in which ones they send: measured payloads carry `RegulModes` and `params` always, and `ExtraParams` on some
installations only. Keys from `params` and `ExtraParams` are limited to a curated list, since `params` alone
carries over a hundred keys on a measured installation.

#### Consumption counters

Klereo counts how long each piece of equipment has run, and those counters are exposed as sensors:

| Sensor | Unit |
|---|---|
| Filtration Time Today / Total | seconds |
| pH- Time Today / Total | seconds |
| Liquid Chlorine Time Today / Total | seconds |
| Hybrid Chlorine Time Today / Total | seconds |
| Heating Time Today / Total | seconds |
| Electrolysis Chlorine Produced Today | mg |

They are reported in the API's own units — Home Assistant renders seconds as a duration and converts them in
cards and statistics, so nothing is lost by not rounding them to hours here.

**Product consumption** — how much pH- and chlorine your pool has actually used — is derived from those run times
and the dosing pump's flow rate, which is how the Klereo Connect app computes it too:

| Sensor | Unit |
|---|---|
| pH- Consumption Today / Total | mL / L |
| Liquid Chlorine Consumption Today / Total | mL / L |
| Hybrid Chlorine Consumption Today / Total | mL / L |

Each counter only appears if your installation reports it, so you see the equipment you have and nothing else. A
consumption sensor additionally needs the pump's flow rate (`PHMinus_Debit` / `Chlore_Debit`); if your box does not
send it, the run-time sensor still appears and the consumption one does not, rather than showing a computed
figure with a guessed flow rate.

**Energy consumption** — for the Home Assistant **Energy dashboard** — is the same idea one step further: a run
time multiplied by a power. Klereo sends no power, so you enter it once per equipment in **Options** (see above),
and the sensors appear:

| Sensor | Unit |
|---|---|
| Filtration Energy Today / Total | kWh |
| Heating Energy Today / Total | kWh |
| pH- Energy Today / Total | kWh |
| Liquid Chlorine Energy Today / Total | kWh |
| Hybrid Chlorine Energy Today / Total | kWh |

The same rule applies in both directions: **no power entered, no energy sensor**, and **no run-time counter, no
energy sensor** — never a sensor stuck at `0`, which Home Assistant would read as a counter reset rather than as
"unknown". Clearing a power (or setting it to 0) removes its energy sensors again; the run-time sensors above are
untouched either way.

A constant power approximates an on/off pump or heater well — the user who asked for this compared a day against
his utility meter and read a 751 W delta for a 750 W pump. An inverter heat pump modulates its draw, so the
figure there is an upper bound rather than a measurement, which is why the power is yours to choose per
equipment rather than ours to assume.

### Switches

Each output on your Klereo system is exposed as a switch:

| Index | Default Name |
|---|---|
| 0 | Lighting |
| 1 | Filtration |
| 2 | pH Corrector |
| 3 | Disinfectant |
| 4 | Heating |
| 5–7 | Aux 1–3 |
| 8 | Flocculant |
| 9–14 | Aux 4–9 |
| 15 | Hybrid Disinfectant |

Turning a switch on or off sends a **Manual mode** command to the Klereo system. The switch state updates optimistically and is confirmed on the next data refresh.

> **Heating (output 4) is the exception.** That output drives a KlereoTherm, whose mode field carries
> `Off` / `Auto` / `Cooling` / `Heating` instead of the usual output modes. Turning the switch on sends
> **Heating**, turning it off sends **Off**, and its mode select offers those options rather than
> Manual / Time Slots / Timer / Regulation.
>
> **On a new installation, the Heating switch is created disabled.** "On" is not a complete command for
> a KlereoTherm: the switch has to pick a mode for you, and nothing on it says which. The mode select
> and the thermostat cover the same equipment and show the mode, so they are what you get by default.
> You can still enable the switch under *Settings → Devices & services → Entities*. An installation
> that already had it keeps it, enabled and unchanged. Note that it reads *on* whenever the heat pump
> is not stopped — including while a reversible pump is **cooling**.
>
> **Which of them you are offered depends on your heating hardware.** `Auto` and `Cooling` only appear
> on a real heat pump — Klereo's `HeaterMode` 2 or 4. An on/off heater or a heating circuit without a
> setpoint gets `Off` and `Heating` alone, because it has nothing else it can do. If your installation
> reports no heating type at all, all four stay offered rather than silently losing a control you use.

> **Note:** Some outputs (pH Corrector, Disinfectant, Flocculant, Hybrid Disinfectant) may require professional-level access on your Klereo account to control.

### Pump Speed (Filtration output)

If your installation has a **variable-speed ("analogue")** Filtration pump, a `number.filtration_speed` entity offers a slider from 0 up to your pump's own maximum speed, always in Manual mode.

> **Source: the upstream Jeedom plugin.** Klereo's API sends a `PumpMaxSpeed` field that its own documentation never names, but that [MrWaloo's Jeedom plugin](https://github.com/MrWaloo/jeedom-klereo) reads: `PumpMaxSpeed > 1` means your pump is variable-speed, and the box accepts a speed step (from 0 to `PumpMaxSpeed`) directly as the output's state in Manual mode. This entity ports that mechanism.
>
> **The entity only appears if your box actually reports `PumpMaxSpeed` above 1** — nothing is invented for a fixed-speed pump, which keeps working through the plain Filtration switch below exactly as before. ✅ Confirmed on a real installation via a Home Assistant diagnostics export (`"PumpMaxSpeed": 3`). If you have a variable-speed pump and can confirm what a given speed step on the slider actually does on your hardware, please say so on the issue tracker.

The existing Filtration switch keeps working alongside it exactly as before: turning it on sends Manual/On, and under Manual mode it still only reads *on* at plain `status == 1` — it does **not** follow the speed entity, on purpose, so a pump running at speed step 2 or 3 shows the switch as off. Use the speed entity to see and set the actual step; the switch stays a simple Manual on/off control. The Output Mode select is unaffected and still owns switching this output between Manual, Time Slots, Timer and Regulation; leaving and returning to Manual through it preserves whatever speed was last set rather than resetting the pump to Off.

> ✅ **Under Regulation, the switch reads *on* — confirmed on a live installation.** The Filtration switch approximates Regulation as always on rather than risking an incorrect off — verified in practice: switching from Manual to Régulé in the Klereo app, the switch followed to on after the next refresh.
>
> ✅ **Under Regulation, the speed entity now shows a value too — `realStatus`, confirmed across five diagnostics exports.** The first capture looked like `status` was pinned to a constant "automatic" flag under Regulation and carried no usable speed; further captures from the same installation, following intentional speed changes (raising, then lowering, a regulation setpoint), showed that `realStatus` tracks the pump's actual target speed instead — agreeing with a separate live telemetry field (`PmpRunningSpeed`) and with a real, externally measured change in the pump's power draw, where `status` agreed with neither. The speed entity reads `realStatus` under Regulation now; it still shows nothing on an installation whose payload carries no `realStatus` at all, rather than guessing.
>
> ⚠️ **`realStatus` reacts faster than the pump telemetry below does.** Right after a setpoint change, `realStatus` (the box's target) updated immediately while `PmpRunningSpeed`/`PmpWatts`/`PmpRPM` (the pump's own physically measured reading) briefly still showed the old value, catching up a couple of minutes later. If the speed entity and the telemetry sensors disagree right after you change something, that is this lag, not a bug — give it a minute.

**Pump telemetry sensors.** If your box's `ExtraParams` payload carries them, you also get a handful of read-only sensors straight from the pump's own controller, alongside your other sensors like every other reading in this integration. These are undocumented by Klereo and unread by the upstream Jeedom plugin — sourced entirely from one reporter's diagnostics exports — so units are only shown where actually confirmed; the rest are exposed as raw numbers, and they lag the speed entity during a transition (see above).

| Sensor | What it shows |
|---|---|
| **Filtration Pump Power** | Instantaneous electrical power, in watts. Cross-checked against an independent power meter — confirmed. |
| **Filtration Pump Running Speed** | The pump's own physically measured running speed, in **%** — confirmed by the reporter directly. Lags `realStatus` during a transition, then settles to match it. |
| **Filtration Pump Speed Setpoint** | The speed the pump's local controller is currently trying to reach, in **%** — confirmed by the reporter directly. In every capture so far it moves together with Running Speed rather than ahead of it. |
| **Filtration Pump RPM** | Motor speed — plausibly revolutions per minute (the field's name), unconfirmed, no unit shown. |
| **Filtration Pump Flow** | A flow reading — plausibly related to the `DebitPompe` value you declared for your installation, unconfirmed, no unit shown. |
| **Filtration Pump Status** | The reporter's own reading is "presumably on/off" — offered as a guess, not confirmed anywhere in the Klereo app. Read `1` in every capture seen so far, at every speed; never observed at `0`. |
| **Filtration Pump Error Code** | `0` in every capture so far. What a non-zero value means is not documented anywhere — if you ever see one, please report it on the issue tracker. |
| **Filtration Pump Timeout** | Briefly went to `1` after a regulation setpoint change, stayed there through the speed transition, then returned to `0` on its own a few minutes later, confirmed in Home Assistant's own history. Nothing about it is visible anywhere in the Klereo app — no alert, no indicator. Reads as a genuine but self-clearing transient rather than a fault; what specifically triggers it is still unknown. |

⚠️ Every description above marked "plausibly" or "unconfirmed" is exactly that — read on one installation, not documented by Klereo or by the upstream Jeedom plugin. Treat the numbers as informative, not as ground truth, until more installations confirm them.

### Climate

If your installation reports a heating output, a single `climate` entity is created for the
KlereoTherm heat pump. It aggregates what the other entities already expose, in the form Home
Assistant's thermostat card expects:

| | Source |
|---|---|
| Current temperature | the water probe your box regulates on (see [above](#which-probe-drives-which-regulation)) |
| Target temperature | the `ConsigneEau` setpoint, with the API's own `EauMin` / `EauMax` bounds |
| Mode | the KlereoTherm mode — `off`, `auto`, `cool`, `heat` |

**Which modes you are offered depends on your heating hardware**, exactly as for the mode select:
`auto` and `cool` only appear on a real heat pump. A thermostat offering "cool" on an on/off heater
would accept the command and change nothing.

**If your box reports the water setpoint as disabled**, the entity is still created and still
switches the heat pump — it simply offers no target temperature, rather than showing you a control
whose every write the box discards. You will see this if the setpoint is turned off at the box.

The existing switch, mode select and setpoint number entities are **not** replaced; this one is
added beside them, so nothing you have already automated changes.

### Number Entities

Writable regulation setpoints are exposed as number entities:

| Parameter | Name | Range | Step |
|---|---|---|---|
| ConsigneEau | Water Setpoint | 10–40 °C | 0.5 |

Changing a value sends a `SetParam` command to the Klereo API.

> The Filtration pump's speed is also a `number` entity, but it writes `SetOut` rather than `SetParam` — see [Pump Speed](#pump-speed-filtration-output) above.

#### Auto-Off Timers

Every output whose data carries a timer also gets a **‹name› Auto-Off Timer**, in **minutes**,
adjustable from 1 to 600 (10 hours). It is Klereo's *Temps minuterie* — how long the output runs
before it switches itself off — and changing it sends a `SetAutoOff` command.

An output whose data carries **no** timer gets **no entity**: nothing is invented, and nothing is
shown as `0`.

Two things about this timer are not documented anywhere and have not been measured, so the
integration does not pretend to know them:

- **What it does on an output that is not in Manual mode.** An output running under regulation or a
  time slot still reports a timer; whether that timer applies there is unknown. The entity shows the
  value the box reports either way.
- **What `0` means.** The lowest value offered here is 1, which is the lowest Klereo itself declares.
  Whether `0` would switch the timer off or simply be refused has never been tried.

### Refresh Button

Each pool gets a **Refresh from Klereo** button that re-reads your data immediately instead of
waiting for the next poll.

It reads; it writes nothing. Klereo's own web interface (both v1 and v3) has the same button, and a
network capture of it shows a single `GetPoolDetails` call and no command sent to your pool
controller — so this button does exactly what that one does, and pressing it can never change
anything at the poolside.

**It refuses more than one refresh once every 10 minutes**, and says so when it does. That is not an
arbitrary limit: Klereo refreshes its servers every 10 minutes and asks that clients do not poll
faster, on pain of banning the account — *your* account. Pressing more often would return the same
data anyway, so the button is held to the same pace as the update interval. The first press after a
restart is always served.

## Troubleshooting

### Authentication errors

Verify your credentials work at [connect.klereo.fr](https://connect.klereo.fr). This integration uses the same login. If the integration shows a re-authentication prompt, click it to re-enter your credentials.

### No entities appear

Check Home Assistant logs for errors from the `klereo` integration: **Settings** > **System** > **Logs**. Ensure your Klereo system is online and accessible.

### An entity's ID does not match its name

**This only affects installations set up before v1.5.2.** If you installed the integration after that,
skip this section.

Home Assistant builds an entity's ID from its name **once, when the entity is first created**, and then
never changes it — deliberately, so that renaming something does not break your automations. An early
release of this integration had two probe types mapped to each other's names, and although the mapping
was corrected before v1.5.2, the IDs created under it are frozen. On an installation from that era you
can see:

| Entity ID | Name shown in the UI | What the value actually is |
|---|---|---|
| `sensor.klereo_water_temperature` | Air Temperature | the **air** temperature |
| `sensor.klereo_air_temperature` | Water Temperature | the **water** temperature |

**The name shown in the UI is always the correct one.** It is recomputed from the probe's type every
time Home Assistant starts; the entity ID is not. Nothing looks wrong on a dashboard, which is what
makes this easy to miss — it only bites if you write the entity ID into a template, an automation or a
card, and then quietly get the wrong reading.

#### Telling the two apart from the values

You do not have to take the names on trust. The two readings are measured in different places and behave
differently, so the values themselves tell you which is which:

- **Water temperature** comes from a probe in the pool. Water has a large thermal mass, so this reading
  moves slowly — a fraction of a degree over an hour, and only a degree or two between day and night.
- **Air temperature** comes from a probe in the technical room. Air has almost no thermal mass, so this
  reading swings by several degrees over a single day and reacts within minutes to a door being opened.

**The steadier of the two is the water**, whatever the entity ID says. In a heated pool it is usually
also the higher one — on the installation this was measured on, the air probe read 23.7 °C while the
water probe read 28.3 °C — but do not rely on that alone: an unheated pool on a hot afternoon can easily
be the cooler of the two. **The one that barely moves is the water.**

To confirm it directly, open **Developer Tools** > **States**, filter on `klereo`, and compare each
entity's ID with its `friendly_name` attribute. The [Sensors](#sensors) table above lists which probe
type produces which name, and a [diagnostics download](#diagnostics) shows each probe's `type` — `1` is
air, `5` is water.

#### Fixing it

Rename the entity yourself: **Settings** > **Devices & Services** > **Klereo** > the entity > the gear
icon > **Entity ID**. Then update anything that referenced the old ID.

The integration will not do this for you. Renaming entity IDs from code would break exactly the
automations the freeze exists to protect — including any you may already have written to work around
this — and there is no way for the code to tell an ID frozen wrong from one you chose on purpose.

⚠️ This is not limited to the temperature probes. **Any** entity whose name changed in a later release
keeps the ID it was born with, so an entity now labelled *Cover Position* may still be called
`sensor.klereo_unknown_sensor_13_index_8`. The same rule applies: trust the name, rename the ID if it
bothers you.

### Switch commands don't take effect immediately

The Klereo cloud API relays commands to your pool equipment. There may be a delay before the command executes. The integration requests a data refresh after each command, but the equipment state may not change instantly.

### Diagnostics

To download diagnostic data for bug reports, go to **Settings** > **Devices & Services** > **Klereo** > three-dot menu > **Download diagnostics**.

The export contains the integration's parsed view of your pool **and the raw API response
it was parsed from**, so that a field the integration does not read yet is still visible in
a bug report. That raw copy goes through exactly the same redaction.

**What is redacted**, so you can decide rather than trust a blanket promise: your password
and session token, your **account username**, the box `pin` and serial (`podSerial`),
Klereo's customer reference (`compta`), your installation address (`Address`) and its key
(`idAddress`), and the notification e-mail address (`emailNotify`).

Your account username is stored in **three** places, and all three are redacted: the
credential itself, the name Home Assistant gives the integration entry (`title`), and the
key it uses to recognise the account (`unique_id`). ⚠️ **Versions 1.13.0 and 1.13.1
published the last two in clear** — if you attached an export from either, it contains your
Klereo username. Upgrade before sending another, and consider the older one as carrying it.

**One more is blanked for a different reason**: `register`. Its **key names** are kept and
its values removed, so a report can still tell us what is in there without publishing it.
It holds your Klereo customer reference and the box `pin` — both redacted by name anyway —
but also the installer id, which is **the final segment of that same pin**. Blanking the
pin while publishing the installer id would hand out a piece of the value just hidden, so
the whole container stays summarised.

`podinfo` used to be blanked for the same "nobody has measured it" reason, and since 1.15.0
it is **not**: measured on two installations it holds four integers — an application number
and three ping counters — none of which identifies a person or a box.

**What is not redacted**, because it is what the report needs and none of it identifies you:
your system id, your pool's nickname, the account access level, the pool's index in the box,
your equipment schedules, and every probe, output and parameter reading.

Diagnostics files are safe to attach to a public issue. ⚠️ **Attach the file rather than
pasting its contents** if your account has several pools — one pool is around 20 KB and three
approach GitHub's per-comment limit. If you are pasting a **debug log** rather than a
diagnostics export, note that no redaction applies there at all — the raw API response
includes your `pin` and `compta`.

### Debug logging

Add the following to your `configuration.yaml` to enable debug logs:

```yaml
logger:
  logs:
    custom_components.klereo: debug
```

## Development

### Setup

```bash
git clone https://github.com/JonBasse/ha-klereo.git
cd ha-klereo
python -m venv .venv
source .venv/bin/activate
pip install pytest pytest-asyncio pytest-homeassistant-custom-component ruff
```

### Run tests

```bash
pytest tests/ -v
```

### Lint

```bash
ruff check .
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes per version.

## Credits

- **Author:** [JonBasse](https://github.com/JonBasse)
- **Original Jeedom plugin:** [MrWaloo/jeedom-klereo](https://github.com/MrWaloo/jeedom-klereo)
- **API:** [Klereo Connect](https://connect.klereo.fr)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Disclaimer

This is a community integration and is not affiliated with or endorsed by Klereo. Use at your own risk.
