import json
import time
import urllib.parse

import requests

from .crypto import decrypt_bytes, decrypt_query, encrypt_query, jpeg_size
from .errors import AuthError, NiViewError


class NiViewClient:
    def __init__(
        self,
        host: str = "cloud-nc.niceviewer.com",
        token: str = "",
        port: int = 8463,
        timeout: int = 30,
        session: requests.Session | None = None,
        app_version: str = "2.1.7",
        app_name: str = "niview",
        app_lang: str = "en",
    ):
        self.host = host
        self.token = token
        self.port = port
        self.timeout = timeout
        self.session = session or requests.Session()
        self.app_version = app_version
        self.app_name = app_name
        self.app_lang = app_lang

    @property
    def base(self) -> str:
        return f"https://{self.host}:{self.port}/"

    def headers(self) -> dict[str, str]:
        return {
            "timestamp": encrypt_query(str(int(time.time() * 1000))),
            "token": encrypt_query(self.token),
            "app-name": self.app_name,
            "app-version": self.app_version,
            "app-lang": self.app_lang,
        }

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = self.base + path.lstrip("/")
        try:
            response = self.session.request(
                method,
                url,
                headers=self.headers(),
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            # Do not include the URL: login query values are recoverable
            # credentials, and signed image URLs are bearer-like.
            raise NiViewError(None, f"request failed ({type(exc).__name__})") from exc

        status = response.status_code
        if status == 401:
            code = None
            msg = "HTTP 401"
            try:
                body = response.json()
                if isinstance(body, dict):
                    code = body.get("code")
                    msg = body.get("msg") or msg
            except ValueError:
                pass
            raise AuthError(code, msg, status)

        try:
            body = response.json()
        except ValueError as exc:
            raise NiViewError(
                None,
                f"non-JSON response (HTTP {status})",
                status,
            ) from exc

        if not isinstance(body, dict):
            raise NiViewError(None, "unexpected response shape", status)

        code = body.get("code")
        msg = body.get("msg") or ""
        body["http_status"] = status
        if status >= 400:
            raise NiViewError(code, msg or f"HTTP {status}", status)
        if code is not None and code != 0:
            if code == -401:
                raise AuthError(code, msg, status)
            raise NiViewError(code, msg, status)

        data = body.get("data")
        if isinstance(data, str) and data:
            try:
                body["data_decrypted"] = decrypt_query(data)
            except Exception as exc:
                raise NiViewError(
                    code,
                    f"response decryption failed: {exc}",
                    status,
                ) from exc
        return body

    def get(self, path: str, **params) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, payload: dict) -> dict:
        return self._request("POST", path, json=payload)

    @staticmethod
    def _payload(body: dict, expected_type: type | None = None):
        raw = body.get("data_decrypted")
        if not raw:
            raise NiViewError(
                body.get("code"),
                "empty response payload",
                body.get("http_status"),
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NiViewError(
                body.get("code"),
                f"invalid JSON payload: {exc}",
                body.get("http_status"),
            ) from exc
        if expected_type is not None and not isinstance(parsed, expected_type):
            raise NiViewError(
                body.get("code"),
                f"unexpected payload type: {type(parsed).__name__}",
                body.get("http_status"),
            )
        return parsed

    def region(self, account: str) -> dict:
        body = self.get("v1/user/userRegion", account=encrypt_query(account))
        return self._payload(body, dict)

    def login(self, account: str, password: str) -> dict:
        if "@" in account:
            body = self.get(
                "v1/user/user_e",
                email=encrypt_query(account),
                **{"pass": encrypt_query(password)},
            )
        else:
            body = self.get(
                "v1/user/user",
                phone=encrypt_query(account),
                **{"pass": encrypt_query(password)},
            )
        return self._payload(body, dict)

    def devices(self, uid: int) -> list[dict]:
        body = self.get("v1/device/devices", uid=encrypt_query(str(uid)))
        return self._payload(body, list)

    def device_info(self, did: int) -> dict:
        body = self.get("v1/device/getDeviceInfo", did=encrypt_query(str(did)))
        return self._payload(body, dict)

    def event_dates(self, uid: int, did: int, mess_type: int = -1) -> list[int]:
        body = self.get(
            "v1/devMess/devMessDates",
            uid=encrypt_query(str(uid)),
            did=encrypt_query(str(did)),
            messType=encrypt_query(str(mess_type)),
        )
        return self._payload(body, list)

    def events(
        self,
        uid: int,
        did: int,
        start: int,
        end: int,
        mess_type: int = -1,
        page: int = 1,
        limit: int = 100,
    ) -> list[dict]:
        body = self.get(
            "v1/devMess/devMess",
            uid=encrypt_query(str(uid)),
            did=encrypt_query(str(did)),
            messType=encrypt_query(str(mess_type)),
            startDate=encrypt_query(str(int(start))),
            endDate=encrypt_query(str(int(end))),
            page=encrypt_query(str(page)),
            limit=encrypt_query(str(limit)),
        )
        return self._payload(body, list)

    def iter_events(
        self,
        uid: int,
        did: int,
        start: int,
        end: int,
        *,
        mess_type: int = -1,
        page_size: int = 100,
        max_pages: int = 100,
    ):
        seen: set[str] = set()
        page = 1
        while page <= max_pages:
            batch = self.events(
                uid,
                did,
                start,
                end,
                mess_type=mess_type,
                page=page,
                limit=page_size,
            )
            if not batch:
                return
            new_items = 0
            for event in batch:
                event_id = str(event.get("id") or "")
                if event_id and event_id in seen:
                    continue
                if event_id:
                    seen.add(event_id)
                new_items += 1
                yield event
            if len(batch) < page_size or new_items == 0:
                return
            page += 1

    def download_image(self, url: str) -> tuple[bytes, tuple[int, int] | None]:
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NiViewError(
                None,
                f"image download failed ({type(exc).__name__})",
            ) from exc
        if response.status_code != 200:
            raise NiViewError(None, f"image download HTTP {response.status_code}")
        data = response.content
        if urllib.parse.urlsplit(url).path.endswith(".encrypt"):
            try:
                data = decrypt_bytes(data)
            except Exception as exc:
                raise NiViewError(None, f"image decryption failed: {exc}") from exc
        if not data.startswith(b"\xff\xd8") or b"\xff\xd9" not in data[-1024:]:
            raise NiViewError(None, "downloaded payload is not a complete JPEG")
        size = jpeg_size(data)
        if size is None:
            raise NiViewError(None, "downloaded JPEG has no readable dimensions")
        return data, size

    @staticmethod
    def device_name(user_device: dict) -> str:
        return user_device.get("device", {}).get("devName", "")

    @staticmethod
    def device_id(user_device: dict) -> int:
        return int(user_device["device"]["id"])

    def resolve_device(self, uid: int, name_or_id: str) -> dict:
        devices = self.devices(uid)
        target = name_or_id.strip()
        matches = [
            item
            for item in devices
            if str(self.device_id(item)) == target
            or self.device_name(item).lower() == target.lower()
        ]
        if len(matches) == 1:
            return matches[0]
        names = ", ".join(
            f"{self.device_name(item)} ({self.device_id(item)})" for item in devices
        )
        if not matches:
            raise NiViewError(None, f"device not found: {target}. Known: {names}")
        raise NiViewError(None, f"ambiguous device: {target}. Known: {names}")
