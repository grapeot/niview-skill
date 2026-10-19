# RFC - NiView Skill

## Scope

A Python CLI and long-running poller for NiView consumer cameras. The tool uses
the vendor's cloud HTTP API for account, device, and event data. It does not
implement live P2P video.

## Observed API Flow

1. Resolve region:
   `GET /v1/user/userRegion?account=<encrypted account>`
   returns `serverDomain`.
2. Set the base URL to `https://<serverDomain>:8463/`.
3. Log in:
   - email: `GET /v1/user/user_e?email=<encrypted>&pass=<encrypted>`
   - phone: `GET /v1/user/user?phone=<encrypted>&pass=<encrypted>`
   returns a user object with `id`, `token`, `tAccessId`, `tAccessToken`.
4. List devices: `GET /v1/device/devices?uid=<encrypted user id>`.
5. List event dates: `GET /v1/devMess/devMessDates?uid=&did=&messType=`.
   The response is a list of Unix **seconds**.
6. List events: `GET /v1/devMess/devMess?uid=&did=&messType=&startDate=&endDate=&page=&limit=`.
   `startDate` and `endDate` are Unix **seconds**. Each event has `imgUrl`,
   `m3u8Url`, `messType`, `recordLength`, and `createDate`.
7. Download the event image. URLs ending in `.encrypt` are AES-encrypted and
   must be decrypted before use.

## Request Signing

Every request carries:

- `timestamp`: AES-128-ECB + PKCS5 + Base64 + URL-encode of the current
  millisecond timestamp.
- `token`: the same encoding of the session token (empty before login).
- `app-name`: the vendor app name.
- `app-version`: the client version.
- `app-lang`: language tag.

The AES key is embedded in the mobile client's native library. This project
uses the extracted key only for interoperability with an account the user owns.

Response bodies use the same AES key: `{"code":0,"data":"<encrypted>"}`. The
`data` string is URL-decoded, Base64-decoded, and AES-decrypted before JSON
parsing.

## Authentication and Token Lifecycle

- `auth login` is the only command that accepts a password.
- Modes: interactive prompt, 1Password references (`op read`), importing an
  existing token, or reading `NIVIEW_ACCOUNT`/`NIVIEW_PASSWORD` from the
  environment for CI (`--mode env`).
- The password is never written to disk.
- The token is written to `.env` atomically with mode `0600`, together with
  `NIVIEW_ACCOUNT`, `NIVIEW_HOST`, and `NIVIEW_TOKEN_AT`.
- All other commands load `.env`, then let environment variables override it.
- A `-401` response raises `AuthError`; the CLI exits `2` with a hint to run
  `auth login` again. There is no silent retry loop.

## CLI Contract

```text
niview auth login --mode interactive|1password|token [--token TOKEN]
niview auth status [--json]
niview devices [--json]
niview events --device NAME|ID [--days N] [--since EPOCH] [--json]
niview snapshot --device NAME|ID [--out FILE] [--json]
niview poll [--once] [--interval SECONDS] [--out DIR] [--state PATH] [--json]
niview decrypt --in FILE --out FILE
```

Errors preserve the HTTP status, vendor `code`, and vendor `msg`. The success
shapes are:

- `devices` and `events`: a JSON array.
- `auth login`, `auth status`, `snapshot`, and `poll`: an object with `ok: true`.
- errors: `{"ok": false, "error": {"http_status": ..., "code": ..., "msg": ...}}`.

`--env-file` is a root-parser option: `niview --env-file PATH devices --json`.
JSON error handling covers runtime errors, not argparse usage errors.

## Poller

- State is stored in SQLite (`state.db` by default) with `event_id` as the
  primary key.
- For each device, fetch event dates whose day interval intersects the lookback
  window, then page through events until exhaustion. Events are filtered by
  `createDate` against the exact cutoff.
- Skip events already in the state table.
- Download, decrypt, and write snapshots under
  `<out>/<device-slug>/<YYYY-MM-DD>/<createDate>-<event_id>.jpg`.
- `--once` performs one pass and exits; the default runs until interrupted.
- The poller only uses cloud APIs; it does not wake the camera.

## Docker

- Multi-stage-free `python:3.12-slim` image.
- Non-root user.
- `docker-compose.yml` mounts the named volume `niview-data`, reads `.env`, and
  runs `poll --interval 300`. For a host bind mount, provision the directory for
  UID 10001 first.
- Authentication is a host-side operation. The container only consumes the
  token. For 1Password, run `auth login` on the host (or inside a one-off
  container with a TTY) and let Compose read the resulting `.env`.

## Security and Privacy

- The public repo contains no real accounts, device names, tokens, or images.
- `.env` is gitignored; `.env.example` contains fake values.
- The token is a bearer credential. Treat it like a password; store `.env` with
  mode `0600`.
- Snapshot images are user data. The repo ships only synthetic fixtures.

## Failure Modes

- Region lookup returns no domain: fall back to the default host.
- Login returns `-4014 Invalid Mobile` for an email: use the email endpoint.
- Event query returns empty with millisecond timestamps: use seconds.
- Image download returns HTML or a truncated body: fail loudly and do not write
  a `.jpg`.
- Token expired: exit `2`; re-run `auth login`.
- Vendor API changes: keep raw `code`/`msg` visible; do not hide them.

## Compatibility

The API is undocumented and may change. The implementation favors explicit
endpoint paths and small parsing functions so a future change is a localized
fix. The CLI contract is the stable interface for agents.
