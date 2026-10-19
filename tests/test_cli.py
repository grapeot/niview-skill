import json

import pytest

from niview_skill.cli import main


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_missing_token_is_auth_error(tmp_path, monkeypatch, capsys):
    for key in ("NIVIEW_TOKEN", "NIVIEW_UID", "NIVIEW_ACCOUNT"):
        monkeypatch.delenv(key, raising=False)
    code = main(["--env-file", str(tmp_path / ".env"), "devices", "--json"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "token" in payload["error"]["msg"]


def test_auth_status_missing_token_is_auth_error(tmp_path, monkeypatch, capsys):
    for key in ("NIVIEW_TOKEN", "NIVIEW_UID", "NIVIEW_ACCOUNT"):
        monkeypatch.delenv(key, raising=False)
    code = main(["--env-file", str(tmp_path / ".env"), "auth", "status", "--json"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


def test_invalid_decrypt_fails_without_writing(tmp_path, capsys):
    source = tmp_path / "bad.encrypt"
    source.write_bytes(b"not ciphertext")
    target = tmp_path / "out.jpg"
    code = main(["decrypt", "--in", str(source), "--out", str(target), "--json"])
    assert code == 1
    assert not target.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


def test_snapshot_default_path_is_under_data(tmp_path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NIVIEW_ACCOUNT=alice@example.com\n"
        "NIVIEW_UID=7\n"
        "NIVIEW_HOST=cloud-us1.example.com\n"
        "NIVIEW_TOKEN=token\n"
    )
    monkeypatch.chdir(tmp_path)

    class FakeClient:
        def __init__(self, host, token):
            pass

        def resolve_device(self, uid, target):
            return {"device": {"id": 1, "devName": "Garden"}}

        def device_name(self, device):
            return "Garden"

        def download_image(self, url):
            from conftest import fake_jpeg

            return fake_jpeg(640, 360), (640, 360)

    monkeypatch.setattr("niview_skill.cli.NiViewClient", FakeClient)
    monkeypatch.setattr(
        "niview_skill.cli.latest_event",
        lambda *args, **kwargs: {
            "id": "event-1",
            "createDate": 1700000000,
            "imgUrl": "https://example.com/a.jpg",
        },
    )
    code = main(["--env-file", str(env_file), "snapshot", "--device", "Garden", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["path"].startswith("data/snapshots/")
    assert (tmp_path / payload["path"]).exists()
