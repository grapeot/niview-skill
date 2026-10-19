# AGENTS.md - niview-skill

## What this repo is

A public, standalone Python CLI and skill for NiView consumer cameras. It logs
in to the vendor cloud API, exchanges credentials for a token, lists devices,
and polls motion-event snapshots. Live P2P video is intentionally out of scope.

## Layout

- `src/niview_skill/` - implementation
- `scripts/niview` - thin executable wrapper
- `skills/niview/SKILL.md` - public skill entry point
- `docs/` - PRD, RFC, test strategy, working notes
- `tests/` - offline unit tests and opt-in integration tests
- `Dockerfile`, `docker-compose.yml` - container runtime

## Rules

1. Never commit secrets. `.env` is gitignored; `.env.example` contains fake
   values only.
2. Do not add real account names, device names, email addresses, phone numbers,
   tokens, or snapshot images to the repo.
3. Keep the public skill free of private routing. Private account/device
   details belong in the user's workspace overlay, not here.
4. Update `docs/working.md` for every meaningful change. One bullet per change,
   no nested bullets.
5. Run `ruff check .` and `pytest` before proposing a merge.
6. Only commit when explicitly asked. Prefer small, reversible commits.
7. Preserve the CLI contract documented in `skills/niview/SKILL.md`; other
   agents depend on it.

## Environment

Python 3.11+ (CI uses 3.12). Use a local `.venv`; install with
`pip install -e '.[dev]'`.

## Compatibility

The vendor API is undocumented and may change. Keep error output faithful:
preserve HTTP status, vendor `code`, and `msg`. Do not collapse failures into a
generic message.
