# Test Strategy

## Unit Tests (offline, default)

- `test_crypto.py`
  - AES query round-trip.
  - Response decryption round-trip.
  - `.encrypt` byte decryption.
- `test_client.py`
  - Region lookup parses `serverDomain`.
  - Email login uses `/v1/user/user_e`; phone login uses `/v1/user/user`.
  - Device list parsing.
  - Event date parsing returns seconds.
  - Event query sends seconds, not milliseconds.
  - HTTP errors preserve vendor `code` and `msg`.
- `test_auth.py`
  - `.env` writer creates mode `0600`.
  - Password is not written.
  - Existing unrelated keys are preserved.
- `test_poller.py`
  - First pass writes new images.
  - Second pass writes nothing (dedupe by event id).
  - Output path is stable and device names are sanitized.
  - Invalid image bytes fail loudly.

All unit tests use monkeypatched HTTP and synthetic fixtures. No network.

## Integration Tests (opt-in)

Enable with:

```bash
NIVIEW_INTEGRATION=1 NIVIEW_TOKEN=... pytest -m integration
```

Coverage:

- `auth status` / `devices` against the live account.
- `events` for a device with recent activity.
- `snapshot` produces a file whose first bytes are a JPEG SOI marker.
- Poller `--once` against a live account, with a temporary output directory.

Integration tests are skipped by default so CI never needs credentials.

## End-to-End

- `docker compose run --rm niview auth status` with a mounted `.env`.
- `docker compose run --rm niview poll --once --out /data/niview`.
- Verify the output volume contains a JPEG and the container runs as non-root.

## Manual Verification

- Open the downloaded JPEG and confirm it matches the event timestamp.
- Confirm `.env` mode is `600`.
- Confirm `git status` does not show `.env`.
- Run the privacy scan described in `project_scaffold` before publishing.

## Definition of Done

- `ruff check .` passes.
- `pytest` passes offline.
- Integration test passes with a real token (manually run, not committed).
- Privacy scan returns zero matches.
- CI is green on the pull request.
