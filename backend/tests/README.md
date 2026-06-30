# Backend Tests

## Unit Tests

`bash test.sh` is the CI source of truth for backend unit tests. It gets its file list from
`scripts/select_backend_unit_tests.py --all`, which covers:

- `tests/unit/test_*.py`
- `tests/services/**/test_*.py`
- `tests/routers/**/test_*.py`
- top-level `tests/test_*.py` files that are still part of the unit suite

For changed-file runs, use:

```bash
python scripts/select_backend_unit_tests.py --changed-files /tmp/changed-files --output /tmp/backend-tests
BACKEND_UNIT_TEST_FILE_LIST=/tmp/backend-tests bash test.sh
```

`BACKEND_PYTEST_TIMING_SUMMARY=1` is enabled by default for multi-file unit pytest sessions and prints the top
slow test files. `test.sh` currently runs one pytest process per file, so it stays quiet there.

Set `BACKEND_FAST_UNIT_MAX_SECONDS=<seconds>` to fail unit test files whose pytest runtime exceeds the limit.
Intentional exceptions must be listed in `tests/fast_unit_duration_allowlist.txt`.

## Integration Tests

Integration tests live under `tests/integration/` and are not run by `bash test.sh`. They may require Redis,
Firebase credentials, API keys, or live external services. Run them explicitly with pytest after reading
`tests/integration/README.md`.

Use `bash test-preflight.sh` before test runs. It validates dependencies and verifies that the selected Python
interpreter matches `.python-version`.
