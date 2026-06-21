---
ticket_id: "tkt_dev_cloud_preview_bridge"
agent: "codex"
done: false
title: "Post-MVP: design optional branch preview bridge for dev-cloud proof"
goal: "After the local emulator MVP, there is a safe handoff path from local iteration to deployed branch proof without weakening V17 Gate 2."
context:
  - path: "docs/runbooks/v17-v3-dev-cloud-proof.md"
    required: true
    max_bytes: 22000
  - path: ".github/workflows/gcp_backend_auto_dev.yml"
    required: true
    max_bytes: 12000
---

## Tasks

- Treat this as post-MVP cloud-promotion infrastructure, not part of the local emulator critical path.
- Document how branch backend revisions can be deployed to a non-production preview target.
- Define required identity, project, index, and fixture-writer constraints.
- Ensure preview deployment cannot target production projects by default or ambient credentials.
- Decide whether this is a GitHub Actions workflow, manual `gcloud` script, or external platform workflow.

## Acceptance criteria

- The bridge produces candidate metadata needed by `docs/runbooks/v17-v3-dev-cloud-proof.md`.
- The design preserves separate runtime and fixture-writer identities.
- The design has explicit production project ID/number hard-stops.

## Tests

- Dry-run the preview metadata generation without network calls.
- Review the design against the dev-cloud proof runbook blockers.
