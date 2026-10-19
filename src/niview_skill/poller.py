import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .client import NiViewClient
from .errors import AuthError, NiViewError
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


def _event_time(event: dict) -> int:
    try:
        return int(event.get("createDate") or 0)
    except (TypeError, ValueError):
        return 0


def _error_text(exc: NiViewError) -> str:
    return f"http={exc.http_status} code={exc.code} msg={exc.msg}"


def _day_intersects(day: int, cutoff: int, upper: int) -> bool:
    return day + 86400 > cutoff and day <= upper


def _dates(values: list) -> list[int]:
    try:
        return sorted(int(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise NiViewError(None, f"invalid event date list: {exc}") from exc


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
    dates = _dates(client.event_dates(uid, did, mess_type))
    events: list[dict] = []
    for day in dates:
        if not _day_intersects(day, cutoff, now):
            continue
        for event in client.iter_events(
            uid,
            did,
            day,
            day + 86400,
            mess_type=mess_type,
            page_size=limit,
        ):
            timestamp = _event_time(event)
            if timestamp < cutoff or timestamp > now:
                continue
            event["device_id"] = did
            event["device_name"] = client.device_name(device)
            events.append(event)
    events.sort(key=_event_time)
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
    dates = _dates(client.event_dates(uid, did, mess_type))
    if not dates:
        raise NiViewError(None, f"no events for device {client.device_name(device)}")
    for day in reversed(dates):
        events = list(
            client.iter_events(
                uid,
                did,
                day,
                day + 86400,
                mess_type=mess_type,
                page_size=limit,
            )
        )
        if events:
            event = max(events, key=_event_time)
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
    upper = now if now is not None else int(time.time())
    cutoff = upper - max(days, 1) * 86400

    with EventStore(state_path) as store:
        for device in devices:
            did = client.device_id(device)
            name = client.device_name(device)
            device_dir = out_root / slugify(name, f"device-{did}")
            try:
                dates = _dates(client.event_dates(uid, did, mess_type))
            except AuthError:
                raise
            except NiViewError as exc:
                result.errors.append(f"{name}: {_error_text(exc)}")
                continue
            for day in dates:
                if not _day_intersects(day, cutoff, upper):
                    continue
                try:
                    events = list(
                        client.iter_events(
                            uid,
                            did,
                            day,
                            day + 86400,
                            mess_type=mess_type,
                            page_size=limit,
                        )
                    )
                except AuthError:
                    raise
                except NiViewError as exc:
                    result.errors.append(f"{name} {day}: {_error_text(exc)}")
                    continue
                for event in events:
                    result.scanned += 1
                    event_id = str(event.get("id") or "")
                    if not event_id:
                        result.errors.append(f"{name}: event without id")
                        continue
                    create_date = _event_time(event)
                    if create_date <= 0:
                        result.errors.append(f"{event_id}: invalid createDate")
                        continue
                    if create_date < cutoff or create_date > upper:
                        continue
                    if store.seen(event_id):
                        result.skipped += 1
                        continue
                    image_url = event.get("imgUrl") or ""
                    if not image_url:
                        result.errors.append(f"{event_id}: no imgUrl")
                        continue
                    try:
                        data, _ = client.download_image(image_url)
                    except AuthError:
                        raise
                    except NiViewError as exc:
                        result.errors.append(f"{event_id}: {_error_text(exc)}")
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
