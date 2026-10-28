# Škoda API Connect for Home Assistant

[🇬🇧 English](README.md) | [🇩🇪 Deutsch](README.de.md) | [🇳🇱 Nederlands](README.nl.md)

A multi-language [Home Assistant](https://www.home-assistant.io/) custom integration for
Škoda vehicles, built on the official
[MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs). It talks to the API
directly with an **API key** - no username/password and no third-party client library.

> **Unofficial project.** This integration is not affiliated with, endorsed by, or associated
> with Škoda Auto. Use at your own risk.

## Features

Built following Home Assistant's current integration best practices: a UI-only config flow,
a `DataUpdateCoordinator` for efficient polling, entity descriptions, per-entity translations,
an options flow, reauthentication support, and a diagnostics download.

| Platform | Entities |
|---|---|
| `sensor` | Battery level, charging power, charge limit (read-only), charging rate, remaining charging time, battery/total range, fuel level, AdBlue range, mileage, target temperature, address of the parking position, name of the charging location profile currently active, API status (result of the last poll, diagnostic), last poll (date and time of the last successful poll, diagnostic), last vehicle data (when the vehicle itself last reported data to the Škoda servers, diagnostic), rate limit until (when the request quota is available again after a rate limit, diagnostic), API requests remaining (left of the hourly quota according to the last response, with the attributes `limit` and `reset_at`, diagnostic) |
| `binary_sensor` | Doors, windows, trunk, bonnet, lights, central locking, charging, charging cable plugged in, charging cable lock, vehicle at saved charging location |
| `device_tracker` | Parking position (shows on the Map dashboard; unknown while driving) |
| `climate` | Remote air conditioning (on/off, active ventilation, target temperature) |
| `switch` | Start/stop charging |
| `button` | Poll API now (queries the MyŠkoda API for the vehicle immediately; costs one request of the API quota and is refused while the API is rate limited), Wake vehicle (see below) |
| `number` | Charge limit (target state of charge), per-vehicle polling intervals (normal / while charging), automatic wake-up of a charging vehicle |
| `select` | Charge mode |

Sensors and controls are only created for the data and remote operations your specific vehicle
reports, so the entity list adapts to your car (EV, PHEV, or combustion).

A **read-only mode** can be enabled in the integration options to disable all remote controls
while keeping all sensors active.

### What the public API does not offer

This integration uses only the public MyŠkoda API. The following are therefore not possible,
because the public API has no endpoint for them: locking/unlocking, honk & flash, waking up the
vehicle, window heating, battery care mode, reduced charging current, outside temperature and
software version. The lock is a read-only `binary_sensor`.

## Supported languages

The integration ships translations for its config flow, options flow, and entity names in:

- English (`en`)
- Nederlands (`nl`)
- Deutsch (`de`)
- Français (`fr`)
- Čeština (`cs`)
- Slovenčina (`sk`)

Home Assistant automatically picks the translation matching your instance's language setting,
falling back to English. Contributions for additional languages are welcome — add a new file
under `custom_components/skoda_api_connect/translations/`.

This documentation itself is available in [English](README.md),
[Deutsch](README.de.md) and [Nederlands](README.nl.md).

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=olafkenfenheuer&repository=Skoda-api-HA-Integration&category=integration)

1. In HACS, search for "Škoda API Connect", click **Download**, and install it.
2. Restart Home Assistant.

If it does not show up in the search (e.g. your HACS has not refreshed the default list yet, or you
want to try a pre-release), add it as a custom repository instead:

1. In HACS, go to **Integrations** → menu (⋮) → **Custom repositories**.
2. Add this repository URL (`https://github.com/olafkenfenheuer/Skoda-api-HA-Integration`) with
   category **Integration**.
3. Search for "Škoda API Connect" in HACS, click **Download**, and install it.
4. Restart Home Assistant.

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/skoda_api_connect` folder into your Home Assistant
   `config/custom_components/` directory, so you end up with
   `config/custom_components/skoda_api_connect/manifest.json`.
3. Restart Home Assistant.

## Configuration

1. In the MyŠkoda app, create an API key at <https://go.skoda.eu/api-keys> and select the
   vehicle(s) it should be valid for. Keys are bound to those vehicles and expire.
2. Go to **Settings → Devices & Services → Add Integration** and search for "Škoda API Connect".
3. Enter the API key and the VIN of each vehicle (several VINs separated by commas). The API
   has no vehicle list endpoint, so the VINs have to be entered manually.
4. Home Assistant validates the key and creates one device per vehicle with all applicable
   entities.
5. After setup, open the integration's **Configure** dialog to change:
   - the polling interval (3-1440 minutes, default 10),
   - the shorter polling interval used **while charging** (default 5),
   - whether that charging interval is **also used while the cable is plugged in** (default off),
   - read-only mode.

You can replace the API key (or change the VINs) at any time - before it expires, or after creating a
new one - via **Settings → Devices & Services → Škoda API Connect → ⋮ → Reconfigure**. The entry is reloaded
and keeps its entities, history and options.

When the key expires (the API reports `api-key-expired`) Home Assistant shows a
"reauthenticate" notification - create a new key and enter it to restore the connection
without losing entity history.

## Notes on the API

The integration only uses the documented endpoints under
`https://public.api.connect.skoda-auto.cz/api/v1/vehicles/{vin}` and authenticates with the
`X-API-Key` header. Data is refreshed by polling.

### Waking a vehicle

The vehicle only reports to the Škoda servers from time to time. While charging it can stay silent for
an hour, and the polls then return old values although they succeed. The sensor **Last vehicle data**
shows when the car last reported; **Last poll** only shows when the integration last fetched data.

The API has no wake-up call. The button **Wake vehicle** therefore re-sends the current charge mode,
a command that changes nothing but has to reach the vehicle; the vehicle usually reports within a minute.
The number **Wake charging vehicle after (0 = off)** does this automatically while a vehicle is charging
and has not reported for the given number of minutes (off by default, minimum 10). Each wake-up uses two
requests of the quota; it is skipped during a rate limit pause and when fewer than 6 requests are left.
Both are unavailable in read-only mode.

### Per-vehicle polling intervals

Every vehicle has two `number` entities (configuration category): **Polling interval** and
**Polling interval while charging**. They override the defaults from the integration options for
that vehicle, apply immediately without reloading, and can be set from automations
(`number.set_value`). A vehicle is polled at its charging interval as soon as the last fetched
state is `CHARGING`. With the option "Use the charging interval while the cable is plugged in" it
is also used as soon as the charging cable is plugged in - useful to catch the start of a
timer-controlled charge, but the faster interval then stays active for as long as the car remains
plugged in. After a charge starts it can take up to one normal interval until the faster polling kicks
in; starting charging from Home Assistant refreshes the vehicle after 30 seconds, so it switches over
right away.

The switch **Fast polling while plugged in** (configuration category) does the same per vehicle:
it overrides the global option for that vehicle.

### Rate limits

The API currently allows **20 requests per hour per VIN** (documented as not final). A poll
costs one request per vehicle, and every remote command costs one more. Therefore this
integration:

- Defaults to a 10-minute polling interval (6 requests/hour) with a 3-minute minimum (3 minutes alone use the whole quota of 20 requests/hour, leaving no room for
  commands), and to 5 minutes
  while a vehicle is charging, or plugged in if you enable that option (12 requests/hour - leave room
  for commands).
- Does not refresh after every command; commands are accepted asynchronously (HTTP 202), so
  it schedules a single refresh 30 seconds after the last command.
- Detects HTTP 429 responses and pauses polling, for the wait time reported by the API (`Retry-After`, `RateLimit-Reset` or the error
  message, plus 30 seconds; at most 1 hour, 15 minutes if the API gives no wait time), and logs a warning when this happens.
- Keeps the last known state of a vehicle if only its request failed.

Parts of the vehicle the API cannot report (for example because the vehicle is asleep) are
simply omitted from its response; the corresponding entities are created once the data is
available, which can require reloading the integration.

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```

See [CLAUDE.md](CLAUDE.md) for an overview of the code layout and conventions.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Disclaimer

Provided as-is, without warranty. Škoda Auto may change its API at any time, which can break
this integration. Use of the MyŠkoda Public API is subject to Škoda's own terms of service.
