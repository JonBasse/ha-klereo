# Klereo Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/JonBasse/ha-klereo.svg)](https://github.com/JonBasse/ha-klereo/releases)

A Home Assistant custom integration for the [Klereo Connect](https://connect.klereo.fr) pool management system. Monitor water quality parameters and control pool equipment directly from Home Assistant.

This integration is a port of the [Jeedom Klereo plugin](https://github.com/MrWaloo/jeedom-klereo) by MrWaloo.

## Features

- **Probe sensors** — Water temperature, air temperature, pH, redox (ORP), filter pressure, flow rate, chlorine level, container levels, and more.
- **Equipment switches** — Control lighting, filtration, heating, and auxiliary outputs (on/off).
- **Regulation parameters** — View regulation modes and setpoints as read-only sensors.
- **Automatic discovery** — All pool systems, probes, and outputs are discovered automatically from your Klereo account.
- **Cloud polling** — Data is refreshed every 5 minutes from the Klereo Connect cloud API.

## Prerequisites

- A [Klereo Connect](https://connect.klereo.fr) account with at least one pool system.
- Home Assistant 2024.1 or later.

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

Your pool systems, sensors, and switches will be created automatically.

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

Additionally, regulation parameters from the `RegulModes` section of your pool data are exposed as read-only sensors.

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

Turning a switch on or off sends a **Manual mode** command to the Klereo system. The switch state reflects the current output status as reported by the API.

> **Note:** Some outputs (pH Corrector, Disinfectant, Flocculant, Hybrid Disinfectant) may require professional-level access on your Klereo account to control.

## Troubleshooting

### Authentication errors

Verify your credentials work at [connect.klereo.fr](https://connect.klereo.fr). This integration uses the same login.

### No entities appear

Check Home Assistant logs for errors from the `klereo` integration: **Settings** > **System** > **Logs**. Ensure your Klereo system is online and accessible.

### Switch commands don't take effect immediately

The Klereo cloud API relays commands to your pool equipment. There may be a delay before the command executes. The integration requests a data refresh after each command, but the equipment state may not change instantly.

### Debug logging

Add the following to your `configuration.yaml` to enable debug logs:

```yaml
logger:
  logs:
    custom_components.klereo: debug
```

## Credits

- **Author:** [JonBasse](https://github.com/JonBasse)
- **Original Jeedom plugin:** [MrWaloo/jeedom-klereo](https://github.com/MrWaloo/jeedom-klereo)
- **API:** [Klereo Connect](https://connect.klereo.fr)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Disclaimer

This is a community integration and is not affiliated with or endorsed by Klereo. Use at your own risk.
