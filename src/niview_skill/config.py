import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "cloud-nc.niceviewer.com"
DEFAULT_PORT = 8463

RUNTIME_KEYS = [
    "NIVIEW_ACCOUNT",
    "NIVIEW_UID",
    "NIVIEW_HOST",
    "NIVIEW_TOKEN",
    "NIVIEW_TOKEN_AT",
]
OPTIONAL_KEYS = [
    "NIVIEW_OP_ACCOUNT",
    "NIVIEW_OP_PASSWORD",
]


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass
class Config:
    account: str = ""
    uid: int | None = None
    host: str = DEFAULT_HOST
    token: str = ""
    token_at: int = 0
    op_account: str = ""
    op_password: str = ""
    port: int = DEFAULT_PORT

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> "Config":
        values = _read_env_file(Path(env_file))

        def get(key: str, default: str = "") -> str:
            return os.environ.get(key, values.get(key, default))

        uid_raw = get("NIVIEW_UID").strip()
        token_at_raw = get("NIVIEW_TOKEN_AT", "0").strip()
        try:
            uid = int(uid_raw) if uid_raw else None
        except ValueError:
            uid = None
        try:
            token_at = int(token_at_raw) if token_at_raw else 0
        except ValueError:
            token_at = 0
        return cls(
            account=get("NIVIEW_ACCOUNT").strip(),
            uid=uid,
            host=get("NIVIEW_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST,
            token=get("NIVIEW_TOKEN").strip(),
            token_at=token_at,
            op_account=get("NIVIEW_OP_ACCOUNT").strip(),
            op_password=get("NIVIEW_OP_PASSWORD").strip(),
        )

    def masked_token(self) -> str:
        if not self.token:
            return "(missing)"
        if len(self.token) <= 8:
            return "***"
        return f"{self.token[:4]}...{self.token[-4:]}"


def write_env(
    env_file: str | Path,
    *,
    account: str,
    uid: int,
    host: str,
    token: str,
    token_at: int,
) -> Path:
    """Write the runtime env file atomically with mode 0600.

    The password is never part of the output, even if an older file contained
    one.
    """
    path = Path(env_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_env_file(path)
    existing.pop("NIVIEW_PASSWORD", None)

    updates = {
        "NIVIEW_ACCOUNT": account,
        "NIVIEW_UID": str(uid),
        "NIVIEW_HOST": host,
        "NIVIEW_TOKEN": token,
        "NIVIEW_TOKEN_AT": str(token_at),
    }
    existing.update(updates)

    ordered_keys = RUNTIME_KEYS + [k for k in OPTIONAL_KEYS if k in existing]
    ordered_keys += [k for k in existing if k not in ordered_keys]

    lines = [f"{key}={existing[key]}" for key in ordered_keys if key in existing]
    lines.append("")

    fd, tmp_name = tempfile.mkstemp(prefix=".env.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return path
