enum V3HomeLiveRow { none, server, placeholder }

V3HomeLiveRow v3HomeLiveRow({
  required bool v3Home,
  required bool streaming,
  required bool serverUsable,
  required bool liveRemoved,
  required bool callActive,
  required bool listeningSuppressed,
}) {
  if (!v3Home || liveRemoved || callActive) return V3HomeLiveRow.none;
  // During Finish suppression the provider hides the finished window. Preserve
  // any other usable window it exposes, and keep the Listening placeholder suppressed.
  if (listeningSuppressed) return serverUsable ? V3HomeLiveRow.server : V3HomeLiveRow.none;
  if (!streaming) return V3HomeLiveRow.none;
  return serverUsable ? V3HomeLiveRow.server : V3HomeLiveRow.placeholder;
}
