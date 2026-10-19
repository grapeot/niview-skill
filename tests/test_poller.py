from pathlib import Path

from conftest import fake_jpeg

from niview_skill.poller import latest_event, list_events, poll_once, slugify


class FakeClient:
    def __init__(self):
        self.images = {
            "https://example.com/a.jpg.encrypt": fake_jpeg(640, 360),
            "https://example.com/b.jpg.encrypt": fake_jpeg(320, 180),
        }

    def device_id(self, user_device):
        return user_device["device"]["id"]

    def device_name(self, user_device):
        return user_device["device"]["devName"]

    def event_dates(self, uid, did, mess_type=-1):
        return [1700000000]

    def events(self, uid, did, start, end, mess_type=-1, page=1, limit=100):
        return [
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

    def download_image(self, url):
        data = self.images[url]
        return data, (640, 360)


DEVICES = [{"device": {"id": 1, "devName": "Garden"}}]


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


def test_list_events_sorted(tmp_path):
    client = FakeClient()
    events = list_events(client, 7, DEVICES[0], days=3650)
    assert [event["id"] for event in events] == ["event-1", "event-2"]
    assert events[0]["device_name"] == "Garden"


def test_latest_event_is_newest():
    client = FakeClient()
    event = latest_event(client, 7, DEVICES[0])
    assert event["id"] == "event-2"
