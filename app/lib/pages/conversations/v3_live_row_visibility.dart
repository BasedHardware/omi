// Removed live windows stay hidden, and usable server windows take precedence.
// Otherwise, streaming shows the placeholder outside calls and post-Finish suppression.
enum V3HomeLiveRow { none, server, placeholder }

V3HomeLiveRow v3HomeLiveRow({
  required bool v3Home,
  required bool streaming,
  required bool serverUsable,
  required bool liveRemoved,
  required bool callActive,
  required bool listeningSuppressed,
}) {
  if (!v3Home || liveRemoved) return V3HomeLiveRow.none;
  if (serverUsable) return V3HomeLiveRow.server;
  if (streaming && !callActive && !listeningSuppressed) return V3HomeLiveRow.placeholder;
  return V3HomeLiveRow.none;
}
