```text
### Summary
Proposed $25 bounty for adding the official Thai (th) agent-focused quickstart guide for LLM harnesses (Claude Code, Cursor, custom bots) to `sdks/python-cli/examples/` and updating the index.

### Scope of Work
- Added `sdks/python-cli/examples/agent_quickstart.th.md`
  - 100% structural parity with `agent_quickstart.md`: all 16 headings (same levels and order), 10 code fences.
  - Byte-identical executable commands, flags (`--json`, `--yes`, `--profile`), environment variables (`OMI_API_KEY`, `OMI_LOCAL_API_URL`, `OMI_LOCAL_TOKEN`), exit codes (`0-5`), and rate-limit constants.
  - Natural, idiomatically accurate Thai translation for all explanatory prose, docstrings, and comments.
  - Verified clean Python AST parsing for all embedded code blocks.
- Registered discovery link in `sdks/python-cli/examples/README.md`.
- No runtime dependencies altered, pure documentation addition.

### Payout Details
- **Claimant**: @huyhoang2k5
- **PR**: #19194
- **Base (USDC)**: `0xa57a66df3c7053FDAb5fD1d72040bc0c5b3455F8`
- **PayPal**: `lnhhoang2k5@gmail.com`
```