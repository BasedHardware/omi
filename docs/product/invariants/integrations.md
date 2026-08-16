# INV-INT-1: Integrations harness over heuristics

**Status:** locked
**Statement:** For connectors and data sources on surfaces we do not own, the
harness is the product and the automation is disposable. Code owns contracts;
agents only drive what code cannot reach; “Connected” means verified recently
via a functional probe.

## MUST NOT

- Add another hardcoded element-anchoring heuristic to
  `CloudConnectorFormAutomation`.
- Gate “Connected” on a timestamp latch or a one-time success.
- Send an agent to do a job a deterministic file write or API/CLI could do.
- Perceive a web flow through Vision/OCR when a DOM is available.
- Compile volatile provider knowledge into the Swift binary.
- Ship a setup flow with no functional probe at the end.
- Upload a connector trace without stripping cookies, tokens, and PII.

## Surfaces

- Desktop “Connect data” sources and “Connect your AI” connectors
- Memory export / MCP connector setup
- Cloud connector form automation and assisted overlays

## Guard tests

- Philosophy + checklist are the contract. Prefer functional-probe and harness
  tests when adding connectors.
- Checklist: [`desktop/macos/docs/connector-checklist.md`](../../../desktop/macos/docs/connector-checklist.md)

## Path globs

- `desktop/macos/docs/integrations-philosophy.md`
- `desktop/macos/docs/connector-checklist.md`
- `desktop/macos/docs/cloud-connectors-roadmap.md`
- `desktop/macos/Desktop/Sources/**/*Connector*`
- `desktop/macos/Desktop/Sources/**/*CloudConnector*`
- `desktop/macos/Desktop/Sources/**/MemoryExport*`
- `desktop/macos/Desktop/Sources/**/MemoryBank*`
- `desktop/macos/Desktop/Sources/**/*ReaderService*`

## PR rule

Name `INV-INT-1` in the PR body if you touch the path globs above.

## Canonical docs (do not duplicate)

- [`desktop/macos/docs/integrations-philosophy.md`](../../../desktop/macos/docs/integrations-philosophy.md)
