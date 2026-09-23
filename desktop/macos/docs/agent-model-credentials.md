# Managed model credentials

AuthService owns the managed session. Each pi-mono HTTP request asks Swift for
current Authorization and usable BYOK headers through the existing Unix socket
relay. The runtime retains reply routing identities only, with a 30-second timeout.
The kernel validates the run capability before dispatch and after reply; Swift
validates the owner session generation around asynchronous credential acquisition.
The environment and startup configuration contain no managed credential.

The installed pi SDK catches errors in before_provider_headers, so that hook
continues to supply correlation/context only. The fetch boundary acquires headers
and fails closed before network I/O if acquisition fails. A managed 401 cancels
its unread body and replays once with forced refresh. Other origins are untouched;
redirects from the managed endpoint are refused. A BYOK LLM 401 is conservatively
provider_setup_needed because the current gateway does not distinguish its origin.
The next successful request clears the typed failure carried over pi's JSONL RPC.

This stepping stone deliberately still sends request-scoped credentials over IPC
and holds them in the provider's request memory. It is not a security boundary
against hostile same-user code. The remaining isolation work is a Swift-owned
loopback HTTP relay with SSE/backpressure, cancellation, header fidelity, owner
revocation, and one pre-stream 401 retry. That relay will replace model_headers IPC.

Hermetic coverage: agent and extension package tests; AgentModelCredentialsTests;
AuthRefreshResilienceTests.testLongLivedModelRequestsRecoverAfterExpiryAndOfflineRefresh.
The static check-agent-credentials.py tripwire is registered in both manifest lanes.
The chat-fault-5xx flow covers the new request credential source in the existing
com.omi.omi-fault bundle; it is not evidence that a live app flow was exercised.
