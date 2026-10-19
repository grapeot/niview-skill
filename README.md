# NiView Skill

A small, agent-friendly CLI for NiView consumer cameras. It logs in to the
vendor cloud API, exchanges the account credentials for a session token, and
then polls motion events and downloads the event snapshots.

The CLI is intentionally narrow:

- account login and token exchange
- device listing
- event listing
- latest-snapshot download and decryption
- a long-running event poller with de-duplication
- Docker and Docker Compose examples

It does **not** implement live video. Live view uses the vendor's proprietary
P2P stack and wakes the camera; this tool is designed for low-power, cloud-side
event polling instead.

This project is not affiliated with NiView or Tencent. It is an interoperability
tool built from observed client behavior. Use it only with cameras and accounts
you own.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

The package exposes the `niview` command.

## Authentication

The CLI supports three ways to obtain a session token.

Interactive:

```bash
niview auth login --mode interactive
```

1Password (recommended for automation):

```bash
export NIVIEW_OP_ACCOUNT='op://private/niview/username'
export NIVIEW_OP_PASSWORD='op://private/niview/password'
niview auth login --mode 1password
```

The CLI uses `op read` and never writes the password to disk.

Import an existing token:

```bash
niview auth login --mode token --token "$NIVIEW_TOKEN"
```

`auth login` resolves the account region, logs in, verifies the token by
listing devices, and writes a `.env` file atomically with mode `0600`:

```dotenv
NIVIEW_ACCOUNT=alice@example.com
NIVIEW_HOST=cloud-us1.niceviewer.com
NIVIEW_TOKEN=...
NIVIEW_TOKEN_AT=0
```

Only the token is persisted. Re-run `auth login` when the token expires; the
CLI exits with status `2` on an authentication failure and never retries
silently.

## Commands

```bash
niview auth status
niview devices
niview events --device Garden --days 2
niview snapshot --device Garden --out latest.jpg
niview poll --interval 300 --out data/niview
niview poll --once --out data/niview
```

All commands accept `--json` where the output is useful to another program.
The default env file is `./.env`; use `--env-file` to point elsewhere.

## Docker

Authenticate on the host, then run the poller in a container:

```bash
niview auth login --mode 1password
docker compose up -d
```

The container reads `.env`, writes snapshots to `./data`, runs as a non-root
user, and has a read-only root filesystem. Do not bake credentials into the
image.

## Event snapshots

Event snapshots are event-driven, not periodic. A motion event produces one
image; a quiet camera produces no new image. The vendor stores the image on
object storage and returns a URL ending in `.encrypt`. The CLI downloads and
decrypts it with the same AES key used by the mobile client.

The observed event snapshots are 640x360 JPEGs. Treat the dimensions as
data-dependent; the CLI validates the decrypted bytes as a JPEG rather than
assuming a fixed size.

## Development

```bash
ruff check .
pytest
```

Unit tests run offline. Integration tests are opt-in:

```bash
NIVIEW_INTEGRATION=1 NIVIEW_TOKEN=... pytest -m integration
```

See `docs/` for the product requirements, design, test strategy, and working
notes. The public skill entry point is `skills/niview/SKILL.md`.
