# Working Notes

## Changelog

### 2026-10-18

- Scaffolded the public repo with docs, CI, Docker files, and a public skill entry point.
- Implemented the cloud client, token exchange, event polling, and snapshot decryption.
- Added offline unit tests and opt-in integration tests.
- Ran the independent review and addressed its findings.
- Merged the implementation pull request.

## Lessons Learned

- Vendor responses are AES-encrypted, including the `data` field. Do not assume plaintext JSON.
- Event date and event queries use Unix seconds, not milliseconds.
- Event images ending in `.encrypt` must be decrypted with the same AES key as request signing.
- Email accounts use `/v1/user/user_e`; phone accounts use `/v1/user/user`.
- The current client sends `app-version` with a hyphen, not `app-version` with an underscore.
- `devMess` events are motion-driven. A quiet camera produces no new snapshot, so "latest" can be old.
- The event snapshot observed during development was 640x360. Treat size as data-dependent.
- Live view is P2P and wakes the camera. Event polling is cloud-side and is the low-power path.
