from pathlib import Path
from typing import ClassVar

import pytest
from conftest import fake_jpeg

from niview_skill.errors import AuthError, NiViewError
from niview_skill.poller import latest_event, list_events, poll_once, slugify


class FakeClient:
    EVENTS: ClassVar[list[dict]] = [
        {
            "id": "event-1",
            "createDate": 1700000000,
            "imgUrl": "https://example.com/a.jpg.encrypt",
        },
        {
            "id": "event-2",
            "createDate": 1700000100,
            "imgUrl": "https://example.com/b.jpg.encrypt",
        },
    ]

    def device_id(self, user_device):
        return user_device["device"]["id"]

    def device_name(self, user_device):
        return user_device["device"]["devName"]

    def event_dates(self, uid, did, mess_type=-1):
        return [1700000000]

    def events(self, uid, did, start, end, mess_type=-1, page=1, limit=100):
        start_index = (page - 1) * limit
        return self.EVENTS[start_index : start_index + limit]

    def iter_events(self, uid, did, start, end, *, mess_type=-1, page_size=100, max_pages=100):
        page = 1
        while page <= max_pages:
            batch = self.events(
                uid, did, start, end, mess_type=mess_type, page=page, limit=page_size
            )
            if not batch:
                return
            yield from batch
            if len(batch) < page_size:
                return
            page += 1

    def download_image(self, url):
        data = fake_jpeg(640, 360)
        return data, (640, 360)


DEVICES = [{"device": {"id": 1, "devName": "Garden"}}]


class PaginatedClient(FakeClient):
    EVENTS: ClassVar[list[dict]] = [
        {"id": f"event-{i}", "createDate": 1700000000 + i, "imgUrl": "https://example.com/a.jpg"}
        for i in range(3)
    ]


class FailingImageClient(FakeClient):
    def download_image(self, url):
        raise NiViewError(None, "bad image")


class ExpiredClient(FakeClient):
    def event_dates(self, uid, did, mess_type=-1):
        raise AuthError(-401, "Unauthorized", 200)


def test_slugify_sanitizes_names():
    assert slugify("Front Yard / North") == "front-yard-north"
    assert slugify("") == "device"


def test_poll_once_is_idempotent(tmp_path):
    client = FakeClient()
    out = tmp_path / "out"
    state = tmp_path / "state.db"

    first = poll_once(client, 7, DEVICES, out_dir=out, state_path=state, days=3650)
    assert first.downloaded == 2
    assert first.skipped == 0
    assert len(first.files) == 2
    assert all(Path(path).exists() for path in first.files)

    second = poll_once(client, 7, DEVICES, out_dir=out, state_path=state, days=3650)
    assert second.downloaded == 0
    assert second.skipped == 2


def test_iter_events_paginates():
    client = PaginatedClient()
    events = list(client.iter_events(7, 1, 0, 86400, page_size=2))
    assert [event["id"] for event in events] == ["event-0", "event-1", "event-2"]


def test_poll_does_not_stop_at_first_page(tmp_path):
    client = PaginatedClient()
    result = poll_once(
        client,
        7,
        DEVICES,
        out_dir=tmp_path / "out",
        state_path=tmp_path / "state.db",
        days=3650,
        limit=2,
    )
    assert result.downloaded == 3


def test_list_events_sorted():
    client = FakeClient()
    events = list_events(client, 7, DEVICES[0], days=3650)
    assert [event["id"] for event in events] == ["event-1", "event-2"]
    assert events[0]["device_name"] == "Garden"


def test_latest_event_is_newest():
    client = FakeClient()
    event = latest_event(client, 7, DEVICES[0])
    assert event["id"] == "event-2"


def test_auth_error_propagates(tmp_path):
    with pytest.raises(AuthError):
        poll_once(
            ExpiredClient(),
            7,
            DEVICES,
            out_dir=tmp_path / "out",
            state_path=tmp_path / "state.db",
        )


def test_failed_image_is_not_marked_seen(tmp_path):
    result = poll_once(
        FailingImageClient(),
        7,
        DEVICES,
        out_dir=tmp_path / "out",
        state_path=tmp_path / "state.db",
        days=3650,
    )
    assert result.downloaded == 0
    assert result.errors
    second = poll_once(
        FailingImageClient(),
        7,
        DEVICES,
        out_dir=tmp_path / "out",
        state_path=tmp_path / "state.db",
        days=3650,
    )
    assert second.skipped == 0
