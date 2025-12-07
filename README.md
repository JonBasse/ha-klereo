# Klereo Integration for Home Assistant 🏊‍♂️

**Status:** [![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration) [![GitHub Release](https://img.shields.io/github/release/JonBasse/ha-klereo.svg)](https://github.com/JonBasse/ha-klereo/releases)

---

### **Make a Splash with your Pool Automation!** 🤽‍♀️

Tired of walking all the way to the pool shed just to see if the water is warm enough for a cannonball? Want to turn on the pool lights from your couch because you forgot to do it before the movie started?

**Dive into the Klereo integration!** 🏖️

This custom component connects your **Klereo Connect** system to Home Assistant, letting you monitor your water quality and control your pool equipment without getting your feet wet (unless you want to).

---

## 🌊 Features

*   **Monitor Everything:** Keep an eye on your Water Temperature, Air Temperature, pH levels, Redox, and more.
*   **Total Control:** Turn on your lights, filter, heating, and auxiliary equipment directly from your dashboard.
*   **Detailed Insights:** Get data on multiple "probes" and "parameters" specific to your Klereo setup.
*   **Automatic Discovery:** We poll your system setup so you don't have to guess what's plugged in where.

*Re-fresh rate: Data is updated every 5 minutes by default. It's not quite "instant gratification," but it's faster than swimming a lap!*

---

## 🛠️ Installation

### Option 1: HACS (Recommended - The "No-Splash" Zone)
This is the easiest way to get started.

1.  Open **HACS** in your Home Assistant sidebar.
2.  Go to **Integrations**.
3.  Click the **three dots** in the top right corner and select **Custom repositories**.
4.  Add the URL: `https://github.com/JonBasse/ha-klereo`
5.  Select **Integration** as the category and click **Add**.
6.  Close the dialog, search for **"Klereo"** in the HACS integrations list, and install it.
7.  **Restart Home Assistant** to let the magic settle.

### Option 2: Manual Installation (The "Deep End")
For those who like to get their hands dirty.

1.  Download the latest release.
2.  Unzip the file.
3.  Copy the `custom_components/klereo` directory into your Home Assistant's `custom_components` directory.
4.  **Restart Home Assistant**.

---

## ⚙️ Configuration

No complex boolean logic or YAML gymnastics required here!

1.  Go to **Settings** -> **Devices & Services** in Home Assistant.
2.  Click the **Add Integration** button.
3.  Search for **Klereo**.
4.  Enter your **Klereo Connect** credentials:
    *   **Username:** (The one you use on klereo.fr)
    *   **Password:** (Shhh, it's a secret)
5.  Click **Submit**.

*Et voilà!* Your pool is now smart(er).

---

## 📝 Credits & Sources

A huge shout-out to the folks who made this possible:

*   **Concept & Development:** [JonBasse](https://github.com/JonBasse)
*   **API Magic:** This integration communicates with the `connect.klereo.fr` API (specifically the `php/*` endpoints).
*   **Inspiration:** Built with love for the Home Assistant community.

---

*Disclaimer: This is a custom integration and is not officially affiliated with Klereo. Use at your own risk, but mostly, use it for fun! Always supervise children around the pool, but feel free to let Home Assistant supervise the pump.* 🛟
