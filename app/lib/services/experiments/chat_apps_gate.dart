import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// The chat apps Omi can be reached from. [wireId] is the backend's `channel` value.
enum ChatChannel {
  telegram('telegram', 'Telegram'),
  imessage('imessage', 'iMessage'),
  whatsapp('whatsapp', 'WhatsApp');

  const ChatChannel(this.wireId, this.displayName);

  final String wireId;

  /// Brand name; never translated.
  final String displayName;

  static ChatChannel? fromWire(String id) {
    for (final channel in values) {
      if (channel.wireId == id) return channel;
    }
    return null;
  }
}

/// Where Omi answers on one channel: the backend provider id the link proof is minted for and the
/// address a person opens (Telegram bot username, iMessage phone number or address).
@immutable
class ChatChannelEndpoint {
  const ChatChannelEndpoint({required this.provider, required this.address});

  final String provider;
  final String address;
}

/// Client gate for the chat apps surface. The backend stays the authority (cohort, Pro entitlement
/// and the kill switch); this only decides whether to show the entry and which addresses to open.
///
/// The link-proof response carries `deep_link` and `address` when the server is configured.
/// The PostHog flag payload is only the fallback, and it still names the provider used to mint:
/// `{"telegram": {"provider": "telegram", "address": "<bot username>"},
/// "imessage": {"provider": "<provider>", "address": "+1..."}}`. A channel without an address
/// is not offered. Fail-closed: no analytics identity, a slow read or a malformed payload all mean
/// off.
@immutable
class ChatAppsConfig {
  const ChatAppsConfig({required this.enabled, this.endpoints = const {}});

  static const off = ChatAppsConfig(enabled: false);

  final bool enabled;
  final Map<ChatChannel, ChatChannelEndpoint> endpoints;

  ChatChannelEndpoint? endpoint(ChatChannel channel) => enabled ? endpoints[channel] : null;

  /// Parses a flag payload, which PostHog returns as a decoded map or as a JSON string.
  static ChatAppsConfig fromPayload({required bool enabled, Object? payload}) {
    if (!enabled) return off;
    Object? value = payload;
    if (value is String) {
      try {
        value = jsonDecode(value);
      } on FormatException {
        value = null;
      }
    }
    final endpoints = <ChatChannel, ChatChannelEndpoint>{};
    if (value is Map) {
      for (final channel in [ChatChannel.telegram, ChatChannel.imessage]) {
        final row = value[channel.wireId];
        if (row is! Map) continue;
        final provider = row['provider'];
        final address = row['address'];
        if (provider is String && _wireId.hasMatch(provider) && address is String && address.trim().isNotEmpty) {
          endpoints[channel] = ChatChannelEndpoint(
            provider: provider,
            address: address.trim(),
          );
        }
      }
    }
    return ChatAppsConfig(enabled: true, endpoints: endpoints);
  }

  static final _wireId = RegExp(r'^[a-z0-9_-]{1,80}$');
}

abstract final class ChatAppsGate {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'mobile-chat-apps';

  /// Debug builds only: `--dart-define=OMI_CHAT_APPS_CONFIG='<payload json>'` turns the surface on
  /// with that payload. `kDebugMode` excludes every store build.
  static const _debugPayload = String.fromEnvironment('OMI_CHAT_APPS_CONFIG');

  static Future<ChatAppsConfig> read({
    Future<bool> Function(String key)? readFlag,
    Future<Object?> Function(String key)? readPayload,
  }) async {
    if (kDebugMode && _debugPayload.isNotEmpty) {
      return ChatAppsConfig.fromPayload(enabled: true, payload: _debugPayload);
    }
    try {
      final enabled = await (readFlag ?? AnalyticsManager().isFeatureEnabled)(
        enabledFlag,
      );
      if (!enabled) return ChatAppsConfig.off;
      return ChatAppsConfig.fromPayload(
        enabled: true,
        payload: await (readPayload ?? AnalyticsManager().getFeatureFlagPayload)(
          enabledFlag,
        ),
      );
    } catch (_) {
      return ChatAppsConfig.off;
    }
  }
}
