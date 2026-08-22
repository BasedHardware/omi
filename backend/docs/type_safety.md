# Backend Type Safety

Backend Python type checking uses **ty** (Astral) on an enrolled path surface
defined in `typecheck-paths.json`. The typecheck must report **0 errors**.

## Run It

```bash
cd backend
bash scripts/typecheck.sh
```

The script expands `typecheck-paths.json` includes, subtracts excludes, and runs
`ty check` with Python 3.13.

## Coverage

`typecheck-paths.json` uses **directory-level includes** for production code
(`config/`, `database/`, `models/`, `routers/`, `utils/`, services, jobs, gateway,
pusher, parakeet, diarizer, modal, `main.py`) plus selected scripts. Matching
excludes keep legacy/unenrolled modules out of the gate.

## Policy For New Backend Code

New production modules should be enrolled in `typecheck-paths.json` once they
typecheck clean under ty. Prefer fixing types over adding `ty: ignore`; when an
ignore is required, keep it scoped to the specific rule.

## Pre-push

The `scripts/pre-push` hook runs `bash scripts/typecheck.sh` whenever any
`backend/**/*.py` file, `typecheck-paths.json`, `pyproject.toml`, `uv.lock`, or
`typecheck.sh` changes. Skip with `PRE_PUSH_SKIP_BACKEND_TYPECHECK=1`.
