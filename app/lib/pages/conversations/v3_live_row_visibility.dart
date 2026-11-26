enum V3HomeLiveRow { none, server, placeholder }

V3HomeLiveRow v3HomeLiveRow({
  required bool v3Home,
  required bool streaming,
  required bool serverUsable,
  required bool liveRemoved,
  required bool callActive,
  required bool listeningSuppressed,
}) {
  if (!v3Home || !streaming || liveRemoved || callActive) return V3HomeLiveRow.none;
  if (serverUsable) return V3HomeLiveRow.server;
  return listeningSuppressed ? V3HomeLiveRow.none : V3HomeLiveRow.placeholder;
}
