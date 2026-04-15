## Purpose
This delivery implements a deterministic RL environment modeled on Anthropic's signed-in Claude workflow. The scope covers sidebar navigation, conversation detail, composer draft state, prompt submission, artifact open state, feedback capture, seeded history, and reset semantics.

## Layout
- `app.py`: zero-dependency HTTP server, static host, and environment state transitions
- `data/seed.json`: seeded signed-in Claude workspace state
- `static/index.html`: local UI for interactive validation
- `api/openapi.yaml`: OpenAPI source of truth for evaluator integrations
- `tests/test_app.py`: targeted environment tests

## Local Commands
- Start server: `python3 app.py`
- Run tests: `python3 -m unittest discover -s tests -p 'test_*.py'`
- View app: open `http://127.0.0.1:8000`

## OpenAPI Ownership
`api/openapi.yaml` is the contract of record for all environment endpoints. Any new action must be added there before or with implementation changes.

## Restore And Reset
`POST /api/reset` restores the seeded workspace state. Every mutable action in the environment updates in-memory state derived from `data/seed.json` and can be replayed from that reset point.
