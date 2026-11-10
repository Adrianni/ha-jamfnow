# Jamf Now for Home Assistant

Custom integration that logs in to [Jamf Now](https://www.jamf.com/products/jamf-now/) and gives you every managed device as a Home Assistant device, with status sensors and controls.

> **Credits:** this project is a fork of [sp32087/ha-jamfnow](https://github.com/sp32087/ha-jamfnow) (MIT). The original integration and its API client are by sp32087. This fork rewrites the login (Jamf now requires Jamf ID), and adds more sensors and controls.

## Install (HACS / Marketplace)

1. In Home Assistant open **HACS** (also called *Marketplace* in newer versions) → menu (⋮) → **Custom repositories**.
2. Add `https://github.com/Adrianni/ha-jamfnow` with type **Integration**.
3. Find **Jamf Now** in HACS, download it and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Jamf Now** and log in with your Jamf ID (email + password).

Home Assistant logs in to Jamf Now when you add the integration and creates one device per Jamf Now device. New devices are picked up automatically.

Manual install: copy `custom_components/jamfnow` to your `config/custom_components/` folder and restart.

## Login

Jamf Now removed the old username/password form and now uses **Jamf ID**. This integration follows the same login flow as the website, so:

- Use the email and password of your Jamf ID.
- Accounts that **require MFA, SSO or a passkey** at login, or where Jamf shows a captcha, cannot log in. Create a dedicated Jamf Now user with a password for Home Assistant.
- Your password is stored in Home Assistant's config entry (like most integrations) and is only sent to Jamf.
- This is an unofficial interface (Jamf Now has no public API), so it may break if Jamf changes their login.

## Entities (per device)

**Sensors**

| Sensor | Description |
| --- | --- |
| Management status | e.g. `MANAGED` |
| OS version | |
| Blueprint | Name of the assigned blueprint |
| Last check-in / Last inventory | Timestamps |
| Lost Mode status | `DISABLED`, `PENDING`, `ENABLED`, `REMOVING` |
| Lost Mode sound status | `NOT_SENT`, `PENDING`, `SUCCESS`, `ERROR` |
| Supervised | `SUPERVISED` / `UNSUPERVISED` |
| Profiles | Lock screen message, restriction, Wi-Fi (on), app lock, email, security, web clip (off by default) |
| Installed apps | Count, app list in attributes |
| Assigned user, Enrolled | Off by default |

**Controls**

| Entity | What it does |
| --- | --- |
| Switch **Lost Mode** | Turns Lost Mode on/off (supervised devices only) |
| Text **Lock screen message** / **Lock screen phone number** | Text shown on the lock screen the next time Lost Mode is turned on |
| Button **Play sound** | Plays the Lost Mode sound. If Lost Mode is off it is turned on first (using the lock screen message), and the sound is played when the device confirms |
| Button **Restart** | Restarts the device |
| Select **Blueprint** | Moves the device to another blueprint |
| Device tracker **Location** | Last location reported by Lost Mode |

Status changes are polled every 5 minutes, and refreshed again 15 s and 60 s after each command.

## Services

All services target one or more Jamf Now devices (device picker): `jamfnow.enable_lost_mode` (`message`, `phone`, `footnote`, `play_sound`), `jamfnow.disable_lost_mode`, `jamfnow.play_sound`, `jamfnow.restart_device`, `jamfnow.shutdown_device`, `jamfnow.sync_inventory`, `jamfnow.set_blueprint` (`blueprint_id`).

## Notes

- Lost Mode and its sound only work on supervised devices.
- The Lost Mode sound can only be played while Lost Mode is on; the Play sound button handles that for you. The device stays locked until you turn Lost Mode off.
- Not affiliated with Jamf. The Jamf Now name and logo are trademarks of Jamf and are used here only to identify the service.

## License

MIT. Copyright (c) 2025 sp32087, (c) 2026 Adrianni.
