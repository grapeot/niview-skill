import json

import pytest

from niview_skill.crypto import encrypt_query


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    if request.node.get_closest_marker("integration"):
        return

    def deny(*args, **kwargs):
        raise AssertionError("network access in an offline test")

    monkeypatch.setattr("requests.sessions.Session.request", deny)
    monkeypatch.setattr("requests.sessions.Session.get", deny)


def fake_jpeg(width: int = 640, height: int = 360) -> bytes:
    app0 = (
        b"\xff\xe0"
        + (16).to_bytes(2, "big")
        + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    )
    sof0 = (
        b"\xff\xc0"
        + (17).to_bytes(2, "big")
        + bytes([8])
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + bytes([3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1])
    )
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


def envelope(payload, code: int = 0, msg: str = "Success") -> dict:
    if isinstance(payload, str):
        raw = payload
    else:
        raw = json.dumps(payload)
    return {"code": code, "msg": msg, "data": encrypt_query(raw)}


class FakeResponse:
    def __init__(
        self,
        payload=None,
        status_code: int = 200,
        content: bytes = b"",
        text: str = "",
        reason: str = "OK",
    ):
        self._payload = payload
        self.status_code = status_code
        self.content = content
        self.text = text or (json.dumps(payload) if payload is not None else "")
        self.reason = reason

    def json(self):
        if self._payload is None:
            raise ValueError("response is not JSON")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self):
        if not self.responses:
            raise AssertionError("no fake response left")
        return self.responses.pop(0)

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self._next()

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._next()
