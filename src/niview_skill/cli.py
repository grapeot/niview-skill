import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from niview_skill import __version__
from niview_skill.auth import login_and_write, status
from niview_skill.client import NiViewClient
from niview_skill.config import Config
from niview_skill.crypto import decrypt_bytes, jpeg_size
from niview_skill.errors import AuthError, NiViewError
from niview_skill.poller import latest_event, list_events, poll_once, slugify


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="niview")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--env-file", default=".env", help="path to the runtime env file")
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth", help="authentication commands")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login", help="exchange credentials for a token")
    login.add_argument(
        "--mode",
        choices=["interactive", "1password", "token", "env"],
        default="interactive",
    )
    login.add_argument("--token", help="import an existing token")
    login.add_argument("--uid", type=int, help="user id, required with --mode token")
    login.add_argument("--account", help="email or phone")
    login.add_argument("--op-account", help="1Password reference or literal account")
    login.add_argument("--op-password", help="1Password reference for the password")
    login.add_argument("--no-verify", action="store_true", help="skip the device-list check")
    _add_json(login)

    auth_status = auth_sub.add_parser("status", help="show account, host, and devices")
    _add_json(auth_status)

    devices = sub.add_parser("devices", help="list devices")
    _add_json(devices)

    events = sub.add_parser("events", help="list motion events")
    events.add_argument("--device", required=True, help="device name or id")
    events.add_argument("--days", type=int, default=2)
    events.add_argument("--since", type=int, help="Unix seconds; overrides --days")
    events.add_argument("--mess-type", type=int, default=-1)
    events.add_argument("--limit", type=int, default=100)
    _add_json(events)

    snapshot = sub.add_parser("snapshot", help="download the latest snapshot")
    snapshot.add_argument("--device", required=True, help="device name or id")
    snapshot.add_argument("--out", help="output JPEG path")
    snapshot.add_argument("--mess-type", type=int, default=-1)
    _add_json(snapshot)

    poll = sub.add_parser("poll", help="poll events and download new snapshots")
    poll.add_argument("--once", action="store_true", help="run one pass and exit")
    poll.add_argument("--interval", type=int, default=300)
    poll.add_argument("--out", default="data/niview")
    poll.add_argument("--state", help="SQLite state path; defaults to <out>/state.db")
    poll.add_argument("--days", type=int, default=7)
    poll.add_argument("--mess-type", type=int, default=-1)
    poll.add_argument("--limit", type=int, default=100)
    poll.add_argument("--device", action="append", help="limit to a device name or id")
    _add_json(poll)

    decrypt = sub.add_parser("decrypt", help="decrypt an .encrypt image")
    decrypt.add_argument("--in", dest="input", required=True)
    decrypt.add_argument("--out", required=True)
    _add_json(decrypt)

    return parser


def _client(cfg: Config) -> NiViewClient:
    if not cfg.token:
        raise AuthError(None, "no token in env; run `niview auth login`")
    if cfg.uid is None:
        raise AuthError(None, "no NIVIEW_UID in env; run `niview auth login`")
    return NiViewClient(host=cfg.host, token=cfg.token)


def _print(payload, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, list):
        for item in payload:
            print(json.dumps(item, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def _device_summary(client: NiViewClient, item: dict) -> dict:
    device = item.get("device", {})
    return {
        "id": client.device_id(item),
        "name": client.device_name(item),
        "tid": device.get("tid", ""),
        "last_login": device.get("lastLoginTime", 0),
    }


def _event_summary(event: dict) -> dict:
    return {
        "id": event.get("id"),
        "device_id": event.get("device_id"),
        "device_name": event.get("device_name"),
        "create_date": event.get("createDate"),
        "mess_type": event.get("messType"),
        "image_url": event.get("imgUrl"),
        "video_url": event.get("m3u8Url"),
        "record_length": event.get("recordLength"),
    }


def _run_auth(args, cfg: Config) -> int:
    if args.auth_command == "status":
        _print(status(cfg), args.json)
        return 0
    result = login_and_write(
        cfg,
        mode=args.mode,
        env_file=args.env_file,
        account=args.account,
        password=args.op_password,
        token=args.token,
        uid=args.uid,
        op_account=args.op_account,
        no_verify=args.no_verify,
    )
    payload = {
        "ok": True,
        "account": result.account,
        "uid": result.uid,
        "host": result.host,
        "env_file": result.env_file,
    }
    _print(payload, args.json)
    return 0


def _run_devices(args, cfg: Config) -> int:
    client = _client(cfg)
    devices = [_device_summary(client, item) for item in client.devices(cfg.uid)]
    _print(devices, args.json)
    return 0


def _run_events(args, cfg: Config) -> int:
    client = _client(cfg)
    device = client.resolve_device(cfg.uid, args.device)
    events = list_events(
        client,
        cfg.uid,
        device,
        days=args.days,
        since=args.since,
        mess_type=args.mess_type,
        limit=args.limit,
    )
    _print([_event_summary(event) for event in events], args.json)
    return 0


def _run_snapshot(args, cfg: Config) -> int:
    client = _client(cfg)
    device = client.resolve_device(cfg.uid, args.device)
    event = latest_event(client, cfg.uid, device, mess_type=args.mess_type)
    image_url = event.get("imgUrl")
    if not image_url:
        raise NiViewError(None, f"event {event.get('id')} has no image")
    data, size = client.download_image(image_url)
    try:
        create_date = int(event.get("createDate") or 0)
    except (TypeError, ValueError) as exc:
        raise NiViewError(None, f"invalid event timestamp: {exc}") from exc
    if create_date <= 0:
        raise NiViewError(None, "invalid event timestamp")
    if args.out:
        target = Path(args.out)
    else:
        target = Path(
            "data/snapshots/"
            f"snapshot-{slugify(client.device_name(device))}-{create_date}.jpg"
        )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError as exc:
        raise NiViewError(None, f"snapshot write failed: {exc}") from exc
    payload = {
        "ok": True,
        "path": str(target),
        "bytes": len(data),
        "width": size[0] if size else None,
        "height": size[1] if size else None,
        "create_date": event.get("createDate"),
        "event_id": event.get("id"),
        "device": client.device_name(device),
    }
    _print(payload, args.json)
    return 0


def _run_poll(args, cfg: Config) -> int:
    client = _client(cfg)
    all_devices = client.devices(cfg.uid)
    if args.device:
        devices = [client.resolve_device(cfg.uid, name) for name in args.device]
    else:
        devices = all_devices
    out_dir = Path(args.out)
    state_path = Path(args.state) if args.state else out_dir / "state.db"
    while True:
        result = poll_once(
            client,
            cfg.uid,
            devices,
            out_dir=out_dir,
            state_path=state_path,
            days=args.days,
            mess_type=args.mess_type,
            limit=args.limit,
        )
        _print(result.as_dict(), args.json)
        if args.once:
            return 0 if not result.errors else 1
        time.sleep(max(args.interval, 30))


def _run_decrypt(args) -> int:
    source = Path(args.input)
    try:
        data = decrypt_bytes(source.read_bytes())
    except Exception as exc:
        raise NiViewError(None, f"decryption failed: {exc}") from exc
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    size = jpeg_size(data)
    _print(
        {
            "ok": data.startswith(b"\xff\xd8"),
            "path": str(target),
            "bytes": len(data),
            "width": size[0] if size else None,
            "height": size[1] if size else None,
        },
        args.json,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = getattr(args, "json", False)
    try:
        cfg = Config.load(args.env_file)
        if args.command == "auth":
            return _run_auth(args, cfg)
        if args.command == "devices":
            return _run_devices(args, cfg)
        if args.command == "events":
            return _run_events(args, cfg)
        if args.command == "snapshot":
            return _run_snapshot(args, cfg)
        if args.command == "poll":
            return _run_poll(args, cfg)
        if args.command == "decrypt":
            return _run_decrypt(args)
        parser.error(f"unknown command: {args.command}")
    except AuthError as exc:
        if as_json:
            print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        else:
            print(
                f"auth error: code={exc.code} msg={exc.msg}; run `niview auth login`",
                file=sys.stderr,
            )
        return 2
    except NiViewError as exc:
        if as_json:
            print(json.dumps({"ok": False, "error": exc.as_dict()}, ensure_ascii=False))
        else:
            print(f"error: http={exc.http_status} code={exc.code} msg={exc.msg}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error) as exc:
        error = {"http_status": None, "code": None, "msg": str(exc)}
        if as_json:
            print(json.dumps({"ok": False, "error": error}, ensure_ascii=False))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
