# Contributing to Pulse

Thanks for your interest. Pulse is a small, readable codebase and contributions are welcome.

## Development setup

```bash
# backend
uv sync
cp .env.example .env          # add an API key
uv run pulse                  # http://127.0.0.1:8787

# frontend
cd web && npm install && npm run dev   # http://localhost:3030
```

## Before you open a PR

- **Backend:** keep it import-clean (`uv run python -c "from pulse.server import create_app"`). If you touch the agent loop or tools, run a real first dive against a test URL — don't mock the LLM.
- **Frontend:** `npx tsc --noEmit` must pass. Match the existing design tokens in `web/src/app/tokens.css`; don't hardcode hex colors.
- Keep changes focused. One feature or fix per PR, with a clear description of what it does for whoever merges it.

## Good first contributions

- **A new tool** — see "Adding a tool" in the README. A self-contained async function + docstring is all it takes.
- **A new launch archetype** — extend the `ARCHETYPES` table in `src/pulse/launch.py` with its growth engine, north-star metric, channel sequence, and anti-patterns.
- **A new traction platform classifier** — add a rule in `src/pulse/traction.py`.
- **Drafting voice improvements** — the founder-voice rules live in `src/pulse/tools/drafting.py` and `reddit.py`.

## Conventions

- Python: type hints everywhere, Google-style docstrings on tools (they become the LLM's function schemas), `ruff` for lint (`line-length = 100`).
- TypeScript: typed API client in `web/src/lib/api.ts`; components colocated by feature.
- Commits: feature-scoped, imperative subject, a body explaining the "what" and "why" for the merger.

## Reporting issues

Include the run log (the console output), your `config.yaml` provider block (redact keys), and steps to reproduce.
