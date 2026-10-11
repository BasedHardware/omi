import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';

/// The chat-apps funnel (`contracts/analytics/consumers/chat-apps-funnel.json`). Properties are
/// the closed channel enum only: no handles, numbers, codes or link ids.
abstract final class ChatAppsAnalytics {
  static void connectStarted(ChatChannel channel) {
    final value = switch (channel) {
      ChatChannel.telegram => ChatAppConnectStartedChannel.telegram,
      ChatChannel.imessage => ChatAppConnectStartedChannel.imessage,
      ChatChannel.whatsapp => null,
    };
    if (value != null) const TypedEvents().emit(ChatAppConnectStarted(channel: value));
  }

  static void connected(ChatChannel channel) {
    final value = switch (channel) {
      ChatChannel.telegram => ChatAppConnectedChannel.telegram,
      ChatChannel.imessage => ChatAppConnectedChannel.imessage,
      ChatChannel.whatsapp => null,
    };
    if (value != null) const TypedEvents().emit(ChatAppConnected(channel: value));
  }

  static void disconnected(ChatChannel channel) {
    final value = switch (channel) {
      ChatChannel.telegram => ChatAppDisconnectedChannel.telegram,
      ChatChannel.imessage => ChatAppDisconnectedChannel.imessage,
      ChatChannel.whatsapp => null,
    };
    if (value != null) const TypedEvents().emit(ChatAppDisconnected(channel: value));
  }

  static void waitlistJoined() => const TypedEvents().emit(const ChatAppWaitlistJoined());
}
