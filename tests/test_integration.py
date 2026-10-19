import os
from pathlib import Path

import pytest

from niview_skill.auth import status
from niview_skill.client import NiViewClient
from niview_skill.config import Config
from niview_skill.crypto import jpeg_size
from niview_skill.poller import latest_event, poll_once

pytestmark = pytest.mark.integration

requires_live = pytest.mark.skipif(
    os.environ.get("NIVIEW_INTEGRATION") != "1",
    reason="set NIVIEW_INTEGRATION=1 to run live tests",
)


@requires_live
def test_live_devices():
    cfg = Config.load()
    if not cfg.token or cfg.uid is None:
        pytest.skip("no live token in .env")
    result = status(cfg)
    assert result["devices"]


@requires_live
def test_live_latest_snapshot(tmp_path):
    cfg = Config.load()
    if not cfg.token or cfg.uid is None:
        pytest.skip("no live token in .env")
    client = NiViewClient(host=cfg.host, token=cfg.token)
    devices = client.devices(cfg.uid)
    if not devices:
        pytest.skip("no devices on the live account")
    event = latest_event(client, cfg.uid, devices[0])
    data, size = client.download_image(event["imgUrl"])
    assert data.startswith(b"\xff\xd8")
    assert size is not None
    target = tmp_path / "latest.jpg"
    target.write_bytes(data)
    assert jpeg_size(target.read_bytes()) == size


@requires_live
def test_live_poll_once(tmp_path):
    cfg = Config.load()
    if not cfg.token or cfg.uid is None:
        pytest.skip("no live token in .env")
    client = NiViewClient(host=cfg.host, token=cfg.token)
    devices = client.devices(cfg.uid)
    if not devices:
        pytest.skip("no devices on the live account")
    result = poll_once(
        client,
        cfg.uid,
        devices,
        out_dir=tmp_path / "out",
        state_path=tmp_path / "state.db",
        days=7,
    )
    assert not result.errors
    assert result.downloaded == len(result.files)
    assert all(Path(path).exists() for path in result.files)
