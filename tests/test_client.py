import pytest
from conftest import FakeResponse, FakeSession, envelope

from niview_skill.client import NiViewClient
from niview_skill.crypto import decrypt_query
from niview_skill.errors import AuthError, NiViewError


def test_region_returns_server_domain():
    session = FakeSession(
        [FakeResponse(envelope({"serverDomain": "cloud-us1.example.com"}))]
    )
    client = NiViewClient(session=session)
    assert client.region("alice@example.com")["serverDomain"] == "cloud-us1.example.com"
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url.endswith("/v1/user/userRegion")
    assert decrypt_query(kwargs["params"]["account"]) == "alice@example.com"


def test_email_login_uses_user_e():
    session = FakeSession([FakeResponse(envelope({"id": 7, "token": "tok"}))])
    client = NiViewClient(session=session)
    user = client.login("alice@example.com", "secret")
    assert user["token"] == "tok"
    _method, url, kwargs = session.calls[0]
    assert url.endswith("/v1/user/user_e")
    assert decrypt_query(kwargs["params"]["email"]) == "alice@example.com"
    assert decrypt_query(kwargs["params"]["pass"]) == "secret"


def test_phone_login_uses_user():
    session = FakeSession([FakeResponse(envelope({"id": 7, "token": "tok"}))])
    client = NiViewClient(session=session)
    client.login("+15555550123", "secret")
    _, url, kwargs = session.calls[0]
    assert url.endswith("/v1/user/user")
    assert decrypt_query(kwargs["params"]["phone"]) == "+15555550123"


def test_devices_parses_list():
    devices = [{"device": {"id": 1, "devName": "Garden", "tid": "tid-1"}}]
    session = FakeSession([FakeResponse(envelope(devices))])
    client = NiViewClient(session=session)
    assert client.devices(7)[0]["device"]["devName"] == "Garden"


def test_events_use_seconds():
    session = FakeSession([FakeResponse(envelope([{"id": "e1"}]))])
    client = NiViewClient(session=session)
    client.events(7, 1, 1700000000, 1700086400)
    _, _, kwargs = session.calls[0]
    assert decrypt_query(kwargs["params"]["startDate"]) == "1700000000"
    assert decrypt_query(kwargs["params"]["endDate"]) == "1700086400"


def test_auth_error_is_raised():
    session = FakeSession([FakeResponse({"code": -401, "msg": "Unauthorized", "data": None})])
    client = NiViewClient(session=session)
    with pytest.raises(AuthError):
        client.devices(7)


def test_non_json_response_is_an_error():
    session = FakeSession([FakeResponse(payload=None, status_code=502, text="bad gateway")])
    client = NiViewClient(session=session)
    with pytest.raises(NiViewError) as exc:
        client.devices(7)
    assert exc.value.http_status == 502


def test_download_image_rejects_non_jpeg():
    session = FakeSession([FakeResponse(content=b"<html>")])
    client = NiViewClient(session=session)
    with pytest.raises(NiViewError):
        client.download_image("https://example.com/a.jpg")
