
from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp

LOGIN_TIMEOUT = aiohttp.ClientTimeout(total=30)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
DEFAULT_LOST_MESSAGE = "Lost mode enabled via Home Assistant"

_HIDDEN_INPUT_RE = re.compile(r'<input\b[^>]*>', re.I)
_CAPTCHA_RE = re.compile(r'<div[^>]*\sdata-captcha-sitekey="[^"]+"', re.I)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _hidden_inputs(page: str) -> dict[str, str]:
    """Return name -> value of all hidden <input> fields in an HTML page."""
    result: dict[str, str] = {}
    for tag in _HIDDEN_INPUT_RE.findall(page):
        attrs = {k.lower(): html.unescape(v) for k, v in _ATTR_RE.findall(tag)}
        if attrs.get("type") == "hidden" and "name" in attrs:
            result[attrs["name"]] = attrs.get("value", "")
    return result


class JamfNowError(Exception):
    pass


class JamfNowAuthError(JamfNowError):
    pass


class JamfNowApiError(JamfNowError):
    pass


@dataclass
class JamfNowBlueprint:

    id: str
    name: str
    description: str | None = None


@dataclass
class JamfNowApp:

    name: str
    version: str | None = None


@dataclass
class JamfNowDevice:

    id: str
    name: str
    serial_number: str
    model: str | None
    os_version: str | None
    status: str | None
    blueprint_id: str | None
    last_check_in: datetime | None
    lost_mode: str | None
    supervised: bool | None = None
    model_name: str | None = None
    os_build: str | None = None
    assigned_user: str | None = None
    enrolled: datetime | None = None
    last_inventory: datetime | None = None
    lost_mode_sound: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_time: datetime | None = None
    profiles: dict[str, str] = field(default_factory=dict)
    apps: list[JamfNowApp] = field(default_factory=list)


def _ts(value: Any) -> datetime | None:
    """Convert a Jamf epoch-milliseconds value to an aware datetime."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


class JamfNowClient:

    def __init__(self, session: aiohttp.ClientSession, base_url: str, username: str, password: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._logged_in = False
        self._login_lock = asyncio.Lock()

    async def _ensure_login(self) -> None:
        async with self._login_lock:
            if self._logged_in:
                return
            await self.async_login()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        for attempt in range(2):
            if not self._logged_in:
                await self._ensure_login()
            try:
                async with self._session.request(
                    method, url, timeout=REQUEST_TIMEOUT, **kwargs
                ) as resp:
                    # An expired session answers 401/403 or redirects to the login page.
                    expired = resp.status in (401, 403) or "/u/login" in str(resp.url)
                    if expired:
                        if attempt == 0:
                            self._logged_in = False
                            continue
                        if resp.status == 401 or "/u/login" in str(resp.url):
                            raise JamfNowAuthError("Invalid credentials for Jamf Now")
                    if resp.status >= 400:
                        text = await resp.text()
                        raise JamfNowApiError(f"Jamf Now API error {resp.status}: {text}")
                    if "application/json" in resp.headers.get("Content-Type", ""):
                        return await resp.json()
                    return await resp.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise JamfNowApiError(f"Connection error: {err}") from err
        raise JamfNowAuthError("Authentication failed after retry")

    async def _login_step(self, method: str, url: str, **kwargs: Any) -> tuple[int, str | None, str]:
        """Do one HTTP step of the login flow without following redirects."""
        async with self._session.request(
            method, url, allow_redirects=False, timeout=LOGIN_TIMEOUT, **kwargs
        ) as resp:
            location = resp.headers.get("Location")
            if location:
                location = urljoin(str(resp.url), location)
            return resp.status, location, await resp.text()

    async def async_login(self) -> None:
        """Log in with Jamf ID (Auth0 Universal Login, identifier-first).

        Jamf Now removed the old username/password form (/login/auth). The flow is now:
        Jamf Now /login/oauth2/authorization/okta -> us.auth.jamf.com/authorize ->
        /u/login/identifier (username) -> /u/login/password (password) ->
        /authorize/resume -> Jamf Now /login/login/oauth2/code/okta, which sets the
        SESSION cookie used by the REST API.
        """
        self._logged_in = False
        self._session.cookie_jar.clear()
        try:
            await self._async_login_flow()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise JamfNowApiError(f"Connection error during login: {err}") from err
        self._logged_in = True

    async def _async_login_flow(self) -> None:
        start_url = f"{self._base_url}/login/oauth2/authorization/okta?lang=en-US"
        status, location, _ = await self._login_step("GET", start_url)
        if not location or "/authorize" not in location:
            raise JamfNowApiError(f"Login failed: unexpected start response {status}")

        # Auth0 /authorize -> /u/login/identifier?state=...
        status, location, _ = await self._login_step("GET", location)
        if not location or "/u/login/identifier" not in location:
            raise JamfNowApiError(f"Login failed: unexpected authorize response {status}")
        identifier_url = location

        status, _, page = await self._login_step("GET", identifier_url)
        self._raise_if_blocked(page)
        state = _hidden_inputs(page).get("state")
        if not state:
            raise JamfNowApiError("Login failed: no state in identifier page")
        data = {"state": state}
        data.update(
            {
                "username": self._username,
                "js-available": "true",
                "webauthn-available": "false",
                "is-brave": "false",
                "webauthn-platform-available": "false",
                "action": "default",
            }
        )
        status, location, page = await self._login_step("POST", identifier_url, data=data)
        if status not in (302, 303) or not location:
            self._raise_if_blocked(page)
            raise JamfNowAuthError("Login failed: Jamf ID did not accept the username")
        if "/u/login/password" not in location:
            raise JamfNowAuthError(
                "Login failed: this Jamf ID needs another login method (SSO/passkey/MFA)"
            )
        password_url = location

        status, _, page = await self._login_step("GET", password_url)
        self._raise_if_blocked(page)
        state = _hidden_inputs(page).get("state")
        if not state:
            raise JamfNowApiError("Login failed: no state in password page")
        data = {"state": state}
        data.update(
            {
                "username": self._username,
                "password": self._password,
                "action": "default",
            }
        )
        status, location, page = await self._login_step("POST", password_url, data=data)
        if status not in (302, 303) or not location:
            self._raise_if_blocked(page)
            raise JamfNowAuthError("Invalid credentials for Jamf Now (Jamf ID)")
        if "/authorize/resume" not in location:
            # e.g. /u/mfa-*, /u/reset-password, /u/consent
            raise JamfNowAuthError(
                f"Login needs an extra step that cannot be automated ({urlparse(location).path})"
            )

        # Follow the remaining redirects back to Jamf Now (sets the SESSION cookie)
        for _ in range(10):
            status, location, _ = await self._login_step("GET", location)
            if status not in (301, 302, 303, 307, 308) or not location:
                break
            if urlparse(location).path.startswith("/u/"):
                raise JamfNowAuthError(
                    f"Login needs an extra step that cannot be automated ({urlparse(location).path})"
                )
        else:
            raise JamfNowApiError("Login failed: too many redirects")

        await self._verify_session()

    def _raise_if_blocked(self, page: str) -> None:
        if _CAPTCHA_RE.search(page):
            raise JamfNowAuthError("Login blocked: Jamf ID requires a captcha")

    async def _verify_session(self) -> None:
        async with self._session.get(
            f"{self._base_url}/device-status/devices", timeout=LOGIN_TIMEOUT
        ) as resp:
            if resp.status in (401, 403) or "/u/login" in str(resp.url):
                raise JamfNowAuthError("Login failed: no valid session after Jamf ID login")
            if resp.status >= 400:
                raise JamfNowApiError(f"Login failed {resp.status}")

    async def async_get_blueprints(self) -> list[JamfNowBlueprint]:
        data = await self._request("GET", "/frontend/rest/blueprints")
        blueprints: list[JamfNowBlueprint] = []
        for item in data if isinstance(data, list) else data.get("blueprints", []):
            blueprints.append(
                JamfNowBlueprint(
                    id=str(item.get("blueprintId") or item.get("id")),
                    name=item.get("name") or "Unknown",
                    description=item.get("description") or item.get("openEnrollmentSlug"),
                )
            )
        return blueprints

    async def async_get_devices(self) -> list[JamfNowDevice]:
        data = await self._request("GET", "/device-status/devices")
        devices: list[JamfNowDevice] = []
        for item in data if isinstance(data, list) else data.get("devices", []):
            blueprint = item.get("blueprint") or {}
            devices.append(
                JamfNowDevice(
                    id=str(item.get("deviceId") or item.get("id")),
                    name=item.get("inventoryName") or item.get("deviceName") or item.get("name") or "Unknown",
                    serial_number=item.get("serialNumber") or item.get("serial_number") or "unknown",
                    model=item.get("modelIdentifier") or item.get("model"),
                    os_version=item.get("osVersion") or item.get("os_version"),
                    os_build=item.get("osBuild"),
                    status=item.get("managementStatus") or item.get("status"),
                    blueprint_id=str(blueprint["blueprintId"])
                    if blueprint.get("blueprintId")
                    else (str(item["blueprintId"]) if item.get("blueprintId") else None),
                    last_check_in=_ts(item.get("lastCheckinTime")),
                    last_inventory=_ts(item.get("lastInventoryTime")),
                    enrolled=_ts(item.get("enrolledTime")),
                    assigned_user=item.get("fullName") or None,
                    lost_mode=None,
                    supervised=item.get("supervised"),
                )
            )
        results = await asyncio.gather(
            *(self.async_get_device(device.id) for device in devices),
            return_exceptions=True,
        )
        for device, detail in zip(devices, results):
            if isinstance(detail, JamfNowAuthError):
                raise detail
            if isinstance(detail, Exception):
                continue
            self._apply_detail(device, detail)
        return devices

    @staticmethod
    def _apply_detail(device: JamfNowDevice, detail: Dict[str, Any]) -> None:
        status = detail.get("status") or {}
        lost = status.get("lostModeInfo") or {}
        device.lost_mode = lost.get("status") or device.lost_mode
        device.lost_mode_sound = lost.get("lostModePlaySoundStatus")
        location = lost.get("lastLocation") or {}
        if location.get("latitude") is not None and location.get("longitude") is not None:
            device.latitude = location["latitude"]
            device.longitude = location["longitude"]
            device.location_time = _ts(location.get("time"))
        device.profiles = {
            key: value for key, value in (status.get("profiles") or {}).items() if isinstance(value, str)
        }
        device.apps = [
            JamfNowApp(name=app.get("name") or app.get("appId") or "Unknown", version=app.get("version"))
            for app in detail.get("applications") or []
        ]
        device.model_name = (detail.get("modelInformation") or {}).get("modelName")
        if detail.get("supervised") is not None:
            device.supervised = detail["supervised"]

    async def async_get_device_state(self, device_id: str) -> JamfNowDevice | None:
        """Return only the lost mode related state of one device (cheap, one request)."""
        detail = await self.async_get_device(device_id)
        device = JamfNowDevice(
            id=device_id, name="", serial_number="", model=None, os_version=None,
            status=None, blueprint_id=None, last_check_in=None, lost_mode=None,
        )
        self._apply_detail(device, detail)
        return device

    async def async_get_device(self, device_id: str) -> Dict[str, Any]:
        data = await self._request("GET", f"/frontend/rest/devices/{device_id}")
        if isinstance(data, dict):
            return data
        raise JamfNowApiError("Unexpected device response structure")

    async def async_set_blueprint(self, device_id: str, blueprint_id: str) -> None:
        payload = {"deviceIds": [device_id], "depSerialNumbers": []}
        await self._request("POST", f"/frontend/rest/blueprints/{blueprint_id}/devices", json=payload)

    async def async_enable_lost_mode(
        self,
        device_id: str,
        message: str | None = None,
        phone: str | None = None,
        footnote: str | None = None,
        play_sound: bool | None = None,
    ) -> None:
        payload: Dict[str, Any] = {}
        payload["message"] = message or DEFAULT_LOST_MESSAGE
        payload["phoneNumber"] = phone or ""
        if footnote:
            payload["footNote"] = footnote
        if play_sound is not None:
            payload["playSoundImmediately"] = play_sound
        await self._request("POST", f"/frontend/rest/devices/{device_id}/lost", json=payload)

    async def async_disable_lost_mode(self, device_id: str) -> None:
        await self._request("DELETE", f"/frontend/rest/devices/{device_id}/lost")

    async def async_play_lost_mode_sound(self, device_id: str) -> None:
        """Play the lost-mode sound (only works while Lost Mode is enabled)."""
        await self._request("POST", f"/frontend/rest/devices/{device_id}/lost/playsound")

    async def async_restart_device(self, device_id: str) -> None:
        await self._request("POST", f"/frontend/rest/devices/{device_id}/restart")

    async def async_shutdown_device(self, device_id: str) -> None:
        await self._request("POST", f"/frontend/rest/devices/{device_id}/shutdown")

    async def async_sync_inventory(self, device_id: str) -> None:
        await self._request("POST", f"/frontend/rest/devices/{device_id}/sync/inventory")

    async def async_assign_blueprint(self, device_id: str, blueprint_id: str) -> None:
        payload = {"deviceIds": [device_id], "depSerialNumbers": []}
        await self._request("POST", f"/frontend/rest/blueprints/{blueprint_id}/devices", json=payload)
