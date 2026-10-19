import os
import stat

from niview_skill.config import Config, write_env


def test_write_env_is_private_and_has_no_password(tmp_path):
    path = tmp_path / ".env"
    write_env(
        path,
        account="alice@example.com",
        uid=7,
        host="cloud-us1.example.com",
        token="token-value",
        token_at=1700000000,
    )
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    text = path.read_text()
    assert "NIVIEW_TOKEN=token-value" in text
    assert "NIVIEW_UID=7" in text
    assert "NIVIEW_PASSWORD" not in text


def test_write_env_removes_existing_password(tmp_path):
    path = tmp_path / ".env"
    path.write_text("NIVIEW_PASSWORD=old\nNIVIEW_OP_ACCOUNT=op://fake/item/user\n")
    write_env(
        path,
        account="alice@example.com",
        uid=7,
        host="cloud-us1.example.com",
        token="token-value",
        token_at=1,
    )
    text = path.read_text()
    assert "NIVIEW_PASSWORD" not in text
    assert "NIVIEW_OP_ACCOUNT=op://fake/item/user" in text


def test_config_env_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "NIVIEW_ACCOUNT=alice@example.com\n"
        "NIVIEW_UID=7\n"
        "NIVIEW_HOST=cloud-us1.example.com\n"
        "NIVIEW_TOKEN=file-token\n"
    )
    monkeypatch.setenv("NIVIEW_TOKEN", "env-token")
    cfg = Config.load(path)
    assert cfg.account == "alice@example.com"
    assert cfg.uid == 7
    assert cfg.token == "env-token"
    assert cfg.masked_token() == "env-...oken"
