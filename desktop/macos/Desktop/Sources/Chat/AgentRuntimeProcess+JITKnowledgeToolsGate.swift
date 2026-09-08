extension AgentRuntimeProcess {
  /// Client-side UX gate for the desktop's JIT knowledge-ledger tools
  /// (search_knowledge, save_playbook, close_fact, etc.): admits only the
  /// server's own `effective` verdict. `unknown` — the fail-closed result of
  /// any transport, decode, or authorization-race failure in
  /// `ProactiveLaneClient.jitProactivityFlags` — and `disabled` both resolve
  /// to `false` here, same as `JITProactivityFlags.permitsNewLane` refuses to
  /// re-derive a looser verdict from raw flags. The backend independently
  /// re-checks entitlement on every `/v1/agent/execute-tool` call, so a stale
  /// or wrong value here only changes which tools the model is offered.
  static func jitKnowledgeToolsEnabled(from flags: JITProactivityFlags) -> Bool {
    flags.effective == .enabled
  }

  /// Resolve the gate for one outgoing query. `jitProactivityFlags` caches
  /// per-owner against the server's own `cache_ttl_seconds` (15s-15min), so
  /// this is a cache hit on every query except the first after login/TTL
  /// expiry — the same signal `JITProactivityRuntime` reads for the
  /// ambient/planned proactive lanes.
  static func resolvedJitKnowledgeToolsEnabled(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async -> Bool {
    let flags = await ProactiveLaneClient.shared.jitProactivityFlags(
      authorizationSnapshot: authorizationSnapshot)
    return jitKnowledgeToolsEnabled(from: flags)
  }
}
