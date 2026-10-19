---
name: niview
description: >-
  Interoperate with NiView consumer cameras through the vendor cloud API:
  exchange account credentials for a session token, list devices, list motion
  events, download and decrypt event snapshots, and run a low-power event
  poller. Use when the user mentions NiView, NiView cameras, solar camera
  snapshots, or event polling for a NiView account.
---

# NiView Skill

## Goal

Give an agent a reliable, low-power way to read NiView camera events and
snapshots without waking the camera or implementing the vendor's P2P protocol.

## Boundaries

- Use only accounts and cameras the user owns.
- Do not attempt live P2P video or audio.
- Do not attempt cloud-recorded video playback unless a future command
  explicitly supports it.
- Do not store passwords. Only the token is persisted.
- Do not write real account data, device names, tokens, or images into a public
  repository.

## Prerequisites

- Python 3.11+ and the `niview` CLI installed from this repo.
- A NiView account (email or phone) with access to the cameras.
- Optional: 1Password CLI (`op`) for non-interactive authentication.

## Authentication

Interactive:

```bash
niview auth login --mode interactive
```

1Password:

```bash
export NIVIEW_OP_ACCOUNT='op://private/niview/username'
export NIVIEW_OP_PASSWORD='op://private/niview/password'
niview auth login --mode 1password
```

Import a token:

```bash
niview auth login --mode token --token "$NIVIEW_TOKEN"
```

`auth login` writes a `.env` with mode `0600` containing `NIVIEW_ACCOUNT`,
`NIVIEW_HOST`, `NIVIEW_TOKEN`, and `NIVIEW_TOKEN_AT`. It never writes the
password. If the token expires, the CLI exits `2`; run `auth login` again.

## Commands

```bash
niview auth status
niview devices
niview events --device <name-or-id> --days 2
niview snapshot --device <name-or-id> --out latest.jpg
niview poll --once --out data/niview
niview poll --interval 300 --out data/niview
```

Use `--json` for machine-readable output. Use `--env-file` to point at a
non-default env file.

## Output Contract

- `devices`: array of `{id, name, tid, last_login}`.
- `events`: array of `{id, device_id, create_date, mess_type, image_url, video_url, record_length}`.
- `snapshot`: `{ok, path, bytes, width, height}` when valid.
- `poll`: `{ok, scanned, downloaded, skipped, errors}`.

Errors preserve the HTTP status, vendor `code`, and vendor `msg`. Do not
collapse them into a generic failure.

## Event Semantics

Events are motion-driven. A quiet camera produces no new event and no new
snapshot; "latest" can be hours or days old. The observed snapshot size is
640x360, but treat dimensions as data-dependent and validate the JPEG header.

Polling events is cloud-side and does not wake the camera. Live view is a
different path (P2P) and does wake the camera; avoid it for battery-powered
devices unless the user explicitly asks.

## Docker

Authenticate on the host, then:

```bash
docker compose up -d
```

The container reads `.env`, writes to `./data`, runs as non-root, and has a
read-only root filesystem. Do not put credentials in the image.

## Acceptance Criteria

- `niview auth login --mode interactive` and `--mode 1password` both produce a
  working `.env` with mode `0600`.
- `niview devices` lists the account's cameras.
- `niview events --days 2 --json` returns events with an `image_url`.
- `niview snapshot` writes a valid JPEG.
- `niview poll --once` is idempotent: a second run downloads zero new files.
- `docker compose up -d` runs the poller and writes to the mounted volume.
- `ruff check .` and `pytest` pass.

## Known Pitfalls

- The vendor response `data` field is AES-encrypted; decrypt it before parsing.
- Event dates and ranges are Unix seconds; milliseconds return empty results.
- Email login uses `/v1/user/user_e`; phone login uses `/v1/user/user`.
- The client sends `app-version` with a hyphen.
- Event image URLs ending in `.encrypt` must be decrypted.
- A `-401` means the token is invalid; re-authenticate instead of retrying.
- Token is a bearer credential; keep `.env` at mode `0600` and out of git.
