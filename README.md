# Klereo Home Assistant Integration

A custom component for Home Assistant to control Klereo pool systems.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

## Features
- **Sensors**: Monitor pH, ORP, Water Temperature, Air Temperature.
- **Binary Sensors**: Status flags (Flow, Alarms).
- **Control**: Toggle outputs like Lights, Filtration (Manual Override).

## Installation via HACS

1.  Make sure [HACS](https://hacs.xyz/) is installed.
2.  Go to **HACS** -> **Integrations**.
3.  Click the 3 dots in the top right corner -> **Custom repositories**.
4.  Add the URL of this repository.
5.  Select **Integration** as the category.
6.  Click **Add**.
7.  Search for **Klereo** and install it.
8.  Restart Home Assistant.

## Configuration

1.  Go to **Settings** -> **Devices & Services**.
2.  Click **Add Integration**.
3.  Search for **Klereo**.
4.  Enter your Klereo **Username** and **Password**.

## Notes
- This integration uses the Klereo Cloud API (`https://connect.klereo.fr`).
- Polling interval is set to 5 minutes by default.
