import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .client import NiViewClient
from .errors import NiViewError
from .state import EventStore


@dataclass
class PollResult:
    scanned: int = 0
    downloaded: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": not self.errors,
            "scanned": self.scanned,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "errors": self.errors,
            "files": self.files,
        }


def slugify(value: str, fallback: str = "device") -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = value.strip("-._")
    return value or fallback


def _date_dir(create_date: int) -> str:
    return datetime.fromtimestamp(create_date, tz=UTC).strftime("%Y-%m-%d")


def list_events(
    client: NiViewClient,
    uid: int,
    device: dict,
    *,
    days: int = 2,
    since: int | None = None,
    mess_type: int = -1,
    limit: int = 100,
) -> list[dict]:
    did = client.device_id(device)
    now = int(time.time())
    cutoff = since if since is not None else now - max(days, 1) * 86400
    dates = client.event_dates(uid, did, mess_type)
    if not isinstance(dates, list):
        raise NiViewError(None, f"invalid event dates for {client.device_name(device)}")
    events: list[dict] = []
    for day in sorted(dates):
        if day < cutoff:
            continue
        for event in client.events(
            uid, did, day, day + 86400, mess_type=mess_type, page=1, limit=limit
        ):
            event["device_id"] = did
            event["device_name"] = client.device_name(device)
            events.append(event)
    events.sort(key=lambda item: item.get("createDate", 0))
    return events


def latest_event(
    client: NiViewClient,
    uid: int,
    device: dict,
    *,
    mess_type: int = -1,
    limit: int = 100,
) -> dict:
    did = client.device_id(device)
    dates = client.event_dates(uid, did, mess_type)
    if not isinstance(dates, list) or not dates:
        raise NiViewError(None, f"no events for device {client.device_name(device)}")
    for day in sorted(dates, reverse=True):
        events = client.events(
            uid, did, day, day + 86400, mess_type=mess_type, page=1, limit=limit
        )
        if events:
            event = max(events, key=lambda item: item.get("createDate", 0))
            event["device_id"] = did
            event["device_name"] = client.device_name(device)
            return event
    raise NiViewError(None, f"no events for device {client.device_name(device)}")


def poll_once(
    client: NiViewClient,
    uid: int,
    devices: list[dict],
    *,
    out_dir: str | Path,
    state_path: str | Path,
    days: int = 7,
    mess_type: int = -1,
    limit: int = 100,
    now: int | None = None,
) -> PollResult:
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    result = PollResult()
    cutoff = (now if now is not None else int(time.time())) - max(days, 1) * 86400

    with EventStore(state_path) as store:
        for device in devices:
            did = client.device_id(device)
            device_dir = out_root / slugify(client.device_name(device), f"device-{did}")
            try:
                dates = client.event_dates(uid, did, mess_type)
            except NiViewError as exc:
                result.errors.append(f"{client.device_name(device)}: {exc.msg}")
                continue
            if not isinstance(dates, list):
                result.errors.append(f"{client.device_name(device)}: invalid event dates")
                continue
            for day in sorted(dates):
                if day < cutoff:
                    continue
                try:
                    events = client.events(
                        uid,
                        did,
                        day,
                        day + 86400,
                        mess_type=mess_type,
                        page=1,
                        limit=limit,
                    )
                except NiViewError as exc:
                    result.errors.append(f"{client.device_name(device)} {day}: {exc.msg}")
                    continue
                if not isinstance(events, list):
                    result.errors.append(f"{client.device_name(device)} {day}: invalid events")
                    continue
                for event in events:
                    result.scanned += 1
                    event_id = str(event.get("id") or "")
                    if not event_id:
                        result.errors.append(
                            f"{client.device_name(device)}: event without id"
                        )
                        continue
                    if store.seen(event_id):
                        result.skipped += 1
                        continue
                    image_url = event.get("imgUrl") or ""
                    if not image_url:
                        result.errors.append(f"{event_id}: no imgUrl")
                        continue
                    create_date = int(event.get("createDate") or 0)
                    try:
                        data, _ = client.download_image(image_url)
                    except NiViewError as exc:
                        result.errors.append(f"{event_id}: {exc.msg}")
                        continue
                    target = (
                        device_dir
                        / _date_dir(create_date)
                        / f"{create_date}-{slugify(event_id, 'event')}.jpg"
                    )
                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                    except OSError as exc:
                        result.errors.append(f"{event_id}: write failed: {exc}")
                        continue
                    store.add(event_id, did, create_date, str(target))
                    result.downloaded += 1
                    result.files.append(str(target))
    return result
