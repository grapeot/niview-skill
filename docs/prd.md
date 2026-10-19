# PRD - NiView Skill

## Problem

NiView solar cameras are cloud-first devices. Their mobile app can show live
video and motion events, but there is no documented API or SDK. Live view uses
a proprietary P2P stack and wakes the camera, which is expensive for a
battery/solar device. Event snapshots, however, are already stored in the
vendor cloud and can be fetched without waking the camera.

Users who run a local monitoring stack need a small, scriptable way to:

- authenticate without copying browser cookies
- keep a session token in a local `.env`
- list cameras
- poll motion events
- download and decrypt event snapshots
- run the poller continuously in Docker

## Users

- A developer or agent integrating a NiView camera into a local NVR or
  notification pipeline.
- A user who wants event snapshots without live-streaming and without draining
  a solar battery.

## Requirements

1. `auth login` supports interactive input, 1Password references, and importing
   an existing token.
2. `auth login` resolves the account region, logs in, verifies the token, and
   writes a `.env` file with mode `0600`.
3. The password is never persisted; only the token is written.
4. `devices`, `events`, `snapshot`, and `poll` read configuration from `.env`
   and environment variables.
5. On authentication failure, exit with code `2` and print the vendor `code`
   and `msg`; do not silently retry.
6. `poll` de-duplicates events by event id and writes only new snapshots.
7. Event images ending in `.encrypt` are decrypted before writing.
8. Docker runtime is non-root, reads `.env` at runtime, and writes snapshots to
   a mounted volume. Credentials are never baked into the image.
9. Offline tests cover crypto, request/response handling, `.env` writing, and
   poller de-duplication. Live integration tests are opt-in.

## Non-goals

- Live P2P video or audio.
- Cloud-recorded video playback.
- Mobile-app UI automation.
- Bypassing account authentication or device ownership.
- Supporting cameras or accounts the user does not own.

## Success Criteria

- A new user can install the package and run `niview auth login --mode
  interactive` followed by `niview devices`.
- `niview snapshot --device <name>` produces a valid JPEG.
- `niview poll --once` run twice writes zero new files on the second run.
- `docker compose up -d` starts a poller that writes to `./data`.
- `ruff check .` and `pytest` pass in CI.
- A privacy scan finds no real email, phone, token, or `op://` reference in the
  public repo.
