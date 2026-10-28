# Changelog

[🇬🇧 English](CHANGELOG.md) | [🇳🇱 Nederlands](CHANGELOG.nl.md)

All notable changes to this integration are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.4.0]

### Added

- Parking alert: a critical notification when a vehicle is parked but not secured (reliable lock status not `LOCKED`, doors not `CLOSED`, doors locked not `YES`, locked not `YES`, or windows not `CLOSED`; unknown values count as not secured, windows `UNSUPPORTED` is skipped). The notify services that receive it are chosen in the options (several are possible); Companion app targets get it as a critical alert. One alert per incident; costs no API requests.
- Number "Parking alert grace period" per vehicle (slider, 0-30 minutes, default 5): how long a vehicle may stay unsecured before the alert is sent.
- Binary sensor "Parked unsecured" with the failing checks in the attribute `reasons`.
- Sensors "Doors locked", "Reliable lock status" and "Parking state", showing the values reported by the API.

### Changed

- Diagnostics redact the parking alert notification targets.

## [0.3.0]

### Added

- Sensor "Last vehicle data": when the vehicle itself last reported data to the Škoda servers (newest `carCapturedTimestamp`), with the timestamp of each section as attributes. Unlike "Last poll" it shows when the connection between car and servers was interrupted.
- Button "Wake vehicle": the API has no wake-up call, so it re-sends the current charge mode (a command that changes nothing but has to reach the vehicle), which makes a sleeping vehicle report. Costs two requests of the API quota.
- Number "Wake charging vehicle after (0 = off)" (configuration category, off by default): while a vehicle is charging and has not reported data for this many minutes (5-minute steps, minimum 10), it is woken the same way. Skipped during a rate limit pause and when fewer than 6 requests of the hourly quota are left; never more often than the configured time.

## [0.2.1]

### Fixed

- Diagnostics no longer contain VINs (per-vehicle polling options are now listed as `vehicle_1`, `vehicle_2`, ...) or the vehicle name.

## [0.2.0]

### Added

- Binary sensor "Charging cable lock" for the new `plugLockState` field of API 1.1.0 (on = unlocked).

## [0.1.0]

### Added

- Initial release.
