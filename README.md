# Klereo Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/JonBasse/ha-klereo.svg)](https://github.com/JonBasse/ha-klereo/releases)
[![Validate](https://github.com/JonBasse/ha-klereo/actions/workflows/validate.yml/badge.svg)](https://github.com/JonBasse/ha-klereo/actions/workflows/validate.yml)

A Home Assistant custom integration for the [Klereo Connect](https://connect.klereo.fr) pool management system. Monitor water quality parameters and control pool equipment directly from Home Assistant.

This integration is a port of the [Jeedom Klereo plugin](https://github.com/MrWaloo/jeedom-klereo) by MrWaloo.

## Features

- **Probe sensors** — Water temperature, air temperature, pH, redox (ORP), filter pressure, flow rate, chlorine level, container levels, and more.
- **Equipment switches** — Control lighting, filtration, heating, and auxiliary outputs (on/off) with optimistic state updates.
- **Adjustable setpoints** — Water temperature setpoint exposed as a number entity you can adjust directly from the UI.
- **Regulation parameters** — View regulation modes and setpoints as read-only sensors.
- **Automatic discovery** — All pool systems, probes, and outputs are discovered automatically from your Klereo account. New entities are added dynamically without requiring a restart.
- **Cloud polling** — Data refreshed from the Klereo Connect cloud API at a configurable interval (1–60 minutes, default 5).
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
3. Enter your Klereo Connect credentials (the same email and password you use on [connect.klereo.fr](https://connect.klereo.fr)).
4. Click **Submit**.

Your pool systems, sensors, switches, and number entities will be created automatically.

### Options

After setup, you can configure the integration by clicking **Configure** on the integration card:

- **Update interval** — How often to poll the Klereo API (1–60 minutes, default 5).

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
> **Which of them you are offered depends on your heating hardware.** `Auto` and `Cooling` only appear
> on a real heat pump — Klereo's `HeaterMode` 2 or 4. An on/off heater or a heating circuit without a
> setpoint gets `Off` and `Heating` alone, because it has nothing else it can do. If your installation
> reports no heating type at all, all four stay offered rather than silently losing a control you use.

> **Note:** Some outputs (pH Corrector, Disinfectant, Flocculant, Hybrid Disinfectant) may require professional-level access on your Klereo account to control.

### Number Entities

Writable regulation setpoints are exposed as number entities:

| Parameter | Name | Range | Step |
|---|---|---|---|
| ConsigneEau | Water Setpoint | 10–40 °C | 0.5 |

Changing a value sends a `SetParam` command to the Klereo API.

## Troubleshooting

### Authentication errors

Verify your credentials work at [connect.klereo.fr](https://connect.klereo.fr). This integration uses the same login. If the integration shows a re-authentication prompt, click it to re-enter your credentials.

### No entities appear

Check Home Assistant logs for errors from the `klereo` integration: **Settings** > **System** > **Logs**. Ensure your Klereo system is online and accessible.

### Switch commands don't take effect immediately

The Klereo cloud API relays commands to your pool equipment. There may be a delay before the command executes. The integration requests a data refresh after each command, but the equipment state may not change instantly.

### Diagnostics

To download diagnostic data for bug reports, go to **Settings** > **Devices & Services** > **Klereo** > three-dot menu > **Download diagnostics**.

**What is redacted**, so you can decide rather than trust a blanket promise: your password
and session token, your **account username**, the box `pin`, Klereo's customer reference
(`compta`) and the installation address key (`idAddress`).

**What is not**, because it is what the report needs and none of it identifies you: your
system id, your pool's nickname, the account access level, and every probe, output and
parameter reading.

Diagnostics files are safe to attach to a public issue. If you are pasting a **debug log**
rather than a diagnostics export, note that no redaction applies there at all — the raw API
response includes your `pin` and `compta`.

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
