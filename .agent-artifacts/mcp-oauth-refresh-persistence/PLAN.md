# Durable MCP OAuth refresh

A normal MCP tool call refreshes expired credentials only in its loaded dictionary. A later tool reconstruction reloads the original rotating refresh token and can lose authorization after the server replay grace expires.

Scope: preserve rotated credentials durably before tool execution resumes, coordinate concurrent workers against the authoritative app record, and prevent a delayed refresh from overwriting a reconnected or deleted integration. Cover HTTP and SSE tool calls plus the explicit tool-refresh route. Keep existing OAuth consent/audience behavior and token rotation intact; never log credentials.

Related work: upstream PR #21991 addresses basic tool-call persistence and refresh errors. This contribution will distinguish its concurrency and storage behavior and cite that PR, without assuming it is deployed.

Verification plan: regression for later reconstructed tools beyond rotation grace; sibling and concurrent callers; reconnect/delete fencing; failed or revoked refresh; persistence failure; both transports; focused backend selectors, formatting, async/import checks and repository preflight. Exercise a disposable local MCP/OAuth peer with real HTTP. No production account or cloud deployment is part of this contribution.

Status: kickoff only; implementation and verification pending. Keep the PR draft until code and required local/CI evidence are complete. Deployment and the real pendant/headphone retest remain external follow-up gates.
