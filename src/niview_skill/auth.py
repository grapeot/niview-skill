import getpass
import os
import subprocess
import time
from dataclasses import dataclass

from .client import NiViewClient
from .config import Config, write_env
from .errors import AuthError, NiViewError


@dataclass
class AuthResult:
    account: str
    uid: int
    host: str
    token: str
    user: dict
    env_file: str


def op_read(reference: str) -> str:
    if not reference:
        raise NiViewError(None, "missing 1Password reference")
    try:
        completed = subprocess.run(
            ["op", "read", reference],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise NiViewError(None, "1Password CLI (op) not found") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise NiViewError(None, f"op read failed: {detail}") from exc
    return completed.stdout.strip()


def _credentials(
    mode: str,
    cfg: Config,
    account: str | None,
    password: str | None,
    op_account: str | None,
) -> tuple[str, str]:
    if mode == "interactive":
        resolved_account = account or cfg.account or input("Account (email or phone): ").strip()
        resolved_password = password or getpass.getpass("Password: ")
        return resolved_account, resolved_password
    if mode == "env":
        resolved_account = account or os.environ.get("NIVIEW_ACCOUNT", "") or cfg.account
        resolved_password = password or os.environ.get("NIVIEW_PASSWORD", "")
        if not resolved_account or not resolved_password:
            raise NiViewError(None, "NIVIEW_ACCOUNT and NIVIEW_PASSWORD are required for --mode env")
        return resolved_account.strip(), resolved_password
    if mode == "1password":
        resolved_account = account or os.environ.get("NIVIEW_ACCOUNT") or cfg.account
        if not resolved_account:
            account_ref = (
                op_account
                or os.environ.get("NIVIEW_OP_ACCOUNT")
                or cfg.op_account
            )
            resolved_account = op_read(account_ref)
        password_ref = (
            password
            or os.environ.get("NIVIEW_OP_PASSWORD")
            or cfg.op_password
        )
        if not resolved_account or not password_ref:
            raise NiViewError(
                None,
                "an account plus NIVIEW_OP_PASSWORD is required for --mode 1password",
            )
        return resolved_account.strip(), op_read(password_ref)
    raise NiViewError(None, f"unsupported auth mode: {mode}")


def login_and_write(
    cfg: Config,
    *,
    mode: str,
    env_file: str,
    account: str | None = None,
    password: str | None = None,
    token: str | None = None,
    uid: int | None = None,
    op_account: str | None = None,
    no_verify: bool = False,
) -> AuthResult:
    if mode == "token":
        if not token:
            raise NiViewError(None, "--token is required for --mode token")
        resolved_uid = uid or cfg.uid
        if resolved_uid is None:
            raise NiViewError(None, "--uid is required with --mode token")
        client = NiViewClient(host=cfg.host, token=token)
        if not no_verify:
            client.devices(resolved_uid)
        write_env(
            env_file,
            account=account or cfg.account,
            uid=resolved_uid,
            host=cfg.host,
            token=token,
            token_at=int(time.time()),
        )
        return AuthResult(cfg.account, resolved_uid, cfg.host, token, {}, env_file)

    resolved_account, resolved_password = _credentials(
        mode, cfg, account, password, op_account
    )
    client = NiViewClient(host=cfg.host)
    region = client.region(resolved_account)
    host = region.get("serverDomain") or cfg.host
    client.host = host
    user = client.login(resolved_account, resolved_password)
    token = user.get("token", "")
    resolved_uid = int(user.get("id", 0))
    if not token or not resolved_uid:
        raise NiViewError(None, "login response did not contain a token and user id")
    client.token = token
    if not no_verify:
        client.devices(resolved_uid)
    write_env(
        env_file,
        account=resolved_account,
        uid=resolved_uid,
        host=host,
        token=token,
        token_at=int(time.time()),
    )
    return AuthResult(resolved_account, resolved_uid, host, token, user, env_file)


def status(cfg: Config) -> dict:
    if not cfg.token:
        raise AuthError(None, "no token in env; run `niview auth login`")
    if cfg.uid is None:
        raise AuthError(None, "no NIVIEW_UID in env; run `niview auth login`")
    client = NiViewClient(host=cfg.host, token=cfg.token)
    devices = client.devices(cfg.uid)
    return {
        "ok": True,
        "account": cfg.account,
        "uid": cfg.uid,
        "host": cfg.host,
        "token": cfg.masked_token(),
        "token_at": cfg.token_at,
        "devices": [
            {
                "id": client.device_id(item),
                "name": client.device_name(item),
                "tid": item["device"].get("tid", ""),
                "last_login": item["device"].get("lastLoginTime", 0),
            }
            for item in devices
        ],
    }
