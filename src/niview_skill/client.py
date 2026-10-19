import json

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
        import time

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
            raise NiViewError(None, f"request failed: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise NiViewError(
                None,
                f"non-JSON response ({response.status_code}): {response.text[:200]}",
                response.status_code,
            ) from exc

        if not isinstance(body, dict):
            raise NiViewError(None, "unexpected response shape", response.status_code)

        code = body.get("code")
        msg = body.get("msg") or ""
        if code == -401:
            raise AuthError(code, msg, response.status_code)
        if response.status_code >= 400 and code is None:
            raise NiViewError(code, msg or response.reason, response.status_code)

        data = body.get("data")
        if isinstance(data, str) and data:
            try:
                body["data_decrypted"] = decrypt_query(data)
            except Exception as exc:
                raise NiViewError(
                    code,
                    f"response decryption failed: {exc}",
                    response.status_code,
                ) from exc
        return body

    def get(self, path: str, **params) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, payload: dict) -> dict:
        return self._request("POST", path, json=payload)

    @staticmethod
    def _payload(body: dict):
        raw = body.get("data_decrypted")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NiViewError(
                body.get("code"),
                f"invalid JSON payload: {exc}",
            ) from exc

    def region(self, account: str) -> dict:
        return self._payload(
            self.get("v1/user/userRegion", account=encrypt_query(account))
        ) or {}

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
        payload = self._payload(body)
        if payload is None:
            raise NiViewError(body.get("code"), body.get("msg") or "login failed")
        return payload

    def devices(self, uid: int) -> list[dict]:
        payload = self._payload(
            self.get("v1/device/devices", uid=encrypt_query(str(uid)))
        )
        return payload if isinstance(payload, list) else []

    def device_info(self, did: int) -> dict:
        return self._payload(
            self.get("v1/device/getDeviceInfo", did=encrypt_query(str(did)))
        ) or {}

    def event_dates(self, uid: int, did: int, mess_type: int = -1) -> list[int]:
        payload = self._payload(
            self.get(
                "v1/devMess/devMessDates",
                uid=encrypt_query(str(uid)),
                did=encrypt_query(str(did)),
                messType=encrypt_query(str(mess_type)),
            )
        )
        return payload if isinstance(payload, list) else []

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
        payload = self._payload(
            self.get(
                "v1/devMess/devMess",
                uid=encrypt_query(str(uid)),
                did=encrypt_query(str(did)),
                messType=encrypt_query(str(mess_type)),
                startDate=encrypt_query(str(int(start))),
                endDate=encrypt_query(str(int(end))),
                page=encrypt_query(str(page)),
                limit=encrypt_query(str(limit)),
            )
        )
        return payload if isinstance(payload, list) else []

    def download_image(self, url: str) -> tuple[bytes, tuple[int, int] | None]:
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NiViewError(None, f"image download failed: {exc}") from exc
        if response.status_code != 200:
            raise NiViewError(None, f"image download HTTP {response.status_code}")
        data = response.content
        if url.endswith(".encrypt"):
            data = decrypt_bytes(data)
        if not data.startswith(b"\xff\xd8"):
            raise NiViewError(None, "downloaded payload is not a JPEG")
        return data, jpeg_size(data)

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
