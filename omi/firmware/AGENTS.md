# Firmware (Omi CV1) — Agent Guide

Component guide for `omi/firmware/`. General engineering rules: root `AGENTS.md`.

## Release Workflow

Firmware releases are manual via `.github/workflows/firmware_release.yml`:

Follow [the CV1 release runbook](docs/cv1-release-safety.md): build-only QA first,
then promote that run's exact artifacts with `qa_run_id` from the same main SHA.
New releases start at 1%; David expands by editing the release body. Versions
3.0.90–3.0.99 require the explicit emergency-revert input.

Build logic lives in `omi/firmware/scripts/ci/`.

## Formatting

C/C++ files: `clang-format -i <files>` (the repo pre-commit hook covers this).
