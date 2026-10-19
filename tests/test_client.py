import pytest
import requests
from conftest import FakeResponse, FakeSession, envelope, fake_jpeg
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from niview_skill.client import NiViewClient
from niview_skill.crypto import AES_KEY, decrypt_query
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


def test_vendor_error_raises():
    session = FakeSession([FakeResponse({"code": -500, "msg": "synthetic", "data": None})])
    client = NiViewClient(session=session)
    with pytest.raises(NiViewError) as exc:
        client.devices(7)
    assert exc.value.code == -500
    assert exc.value.msg == "synthetic"


def test_http_error_with_vendor_code_raises():
    session = FakeSession(
        [FakeResponse({"code": -500, "msg": "synthetic", "data": None}, status_code=500)]
    )
    client = NiViewClient(session=session)
    with pytest.raises(NiViewError) as exc:
        client.devices(7)
    assert exc.value.http_status == 500


def test_wrong_payload_shape_raises():
    session = FakeSession([FakeResponse(envelope({"not": "a list"}))])
    client = NiViewClient(session=session)
    with pytest.raises(NiViewError):
        client.devices(7)


def test_http_401_without_json_is_auth_error():
    session = FakeSession([FakeResponse(payload=None, status_code=401, text="no")])
    client = NiViewClient(session=session)
    with pytest.raises(AuthError):
        client.devices(7)


class RaisingSession:
    def __init__(self, exc):
        self.exc = exc

    def request(self, *args, **kwargs):
        raise self.exc

    def get(self, *args, **kwargs):
        raise self.exc


def test_transport_error_does_not_echo_url():
    exc = requests.ConnectionError("https://cloud.example/v1/user/user_e?pass=secret")
    client = NiViewClient(session=RaisingSession(exc))
    with pytest.raises(NiViewError) as caught:
        client.login("alice@example.com", "secret")
    assert "secret" not in caught.value.msg
    assert "https://" not in caught.value.msg


def test_encrypted_image_with_query_string_is_decrypted():
    payload = fake_jpeg(640, 360)
    encrypted = AES.new(AES_KEY, AES.MODE_ECB).encrypt(pad(payload, 16))
    session = FakeSession([FakeResponse(content=encrypted)])
    client = NiViewClient(session=session)
    data, size = client.download_image("https://example.com/a.jpg.encrypt?sig=1")
    assert data == payload
    assert size == (640, 360)


def test_truncated_jpeg_is_rejected():
    session = FakeSession([FakeResponse(content=b"\xff\xd8")])
    client = NiViewClient(session=session)
    with pytest.raises(NiViewError):
        client.download_image("https://example.com/a.jpg")


def test_image_transport_error_does_not_echo_url():
    exc = requests.ConnectionError("https://example.com/a.jpg?signature=secret")
    client = NiViewClient(session=RaisingSession(exc))
    with pytest.raises(NiViewError) as caught:
        client.download_image("https://example.com/a.jpg?signature=secret")
    assert "signature" not in caught.value.msg
