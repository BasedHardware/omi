import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/messaging_channels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/messaging_wire.g.dart' as wire;
import 'package:omi/services/experiments/chat_apps_gate.dart';

export 'package:omi/services/experiments/chat_apps_gate.dart';

/// One linked chat-app identity, as the app shows it.
@immutable
class ChannelLink {
  const ChannelLink({
    required this.id,
    required this.channelId,
    required this.provider,
    required this.externalId,
    required this.linkedAt,
    this.visibleInApp = false,
    this.voiceNotes = true,
    this.keepPrivateMemoriesInApp = true,
    this.insights = false,
    this.displayHandle,
  });

  factory ChannelLink.fromGenerated(wire.GeneratedChannelLink link) => ChannelLink(
        id: link.id,
        channelId: link.channel,
        provider: link.provider,
        externalId: link.externalId,
        linkedAt: link.linkedAt,
        visibleInApp: link.visibleInApp,
        voiceNotes: link.voiceNotes,
        keepPrivateMemoriesInApp: link.keepPrivateMemoriesInApp,
        insights: link.insights,
        displayHandle: link.displayHandle,
      );

  final String id;
  final String channelId;
  final String provider;
  final String externalId;
  final DateTime linkedAt;
  final bool visibleInApp;
  final bool voiceNotes;
  final bool keepPrivateMemoriesInApp;
  final bool insights;
  final String? displayHandle;

  ChatChannel? get channel => ChatChannel.fromWire(channelId);

  /// What the person recognizes the link by, or null when the backend only knows an opaque id.
  ///
  /// A Telegram username from the link is shown when we have one. Otherwise a numeric Telegram
  /// user id, which nobody knows, shows no handle.
  String? get handle {
    final stored = displayHandle?.trim();
    if (stored != null && stored.isNotEmpty) {
      if (channel == ChatChannel.telegram) return stored.startsWith('@') ? stored : '@$stored';
      return stored;
    }
    final id = externalId.trim();
    if (id.isEmpty) return null;
    if (channel == ChatChannel.telegram) {
      if (RegExp(r'^\d+$').hasMatch(id)) return null;
      return id.startsWith('@') ? id : '@$id';
    }
    return id;
  }

  ChannelLink copyWith({
    bool? visibleInApp,
    bool? voiceNotes,
    bool? keepPrivateMemoriesInApp,
  }) =>
      ChannelLink(
        id: id,
        channelId: channelId,
        provider: provider,
        externalId: externalId,
        linkedAt: linkedAt,
        visibleInApp: visibleInApp ?? this.visibleInApp,
        voiceNotes: voiceNotes ?? this.voiceNotes,
        keepPrivateMemoriesInApp: keepPrivateMemoriesInApp ?? this.keepPrivateMemoriesInApp,
        insights: insights,
        displayHandle: displayHandle,
      );
}

/// Chat-app links for the signed-in account: the gate, the list, and the actions on it.
///
/// Every server call returns its [ApiResult] so a page can tell "not allowed" (403), "gone" (404)
/// and "try again" apart. The list is never blanked by a failed refresh.
class MessagingChannelsProvider extends ChangeNotifier {
  MessagingChannelsProvider({
    MessagingChannelsApi api = const MessagingChannelsApi(),
    Future<ChatAppsConfig> Function()? readConfig,
    bool Function(String key)? readLocalFlag,
    Future<bool> Function(String key, bool value)? writeLocalFlag,
  })  : _api = api,
        _readConfig = readConfig ?? ChatAppsGate.read,
        _readLocalFlag = readLocalFlag ?? ((key) => SharedPreferencesUtil().getBool(key)),
        _writeLocalFlag = writeLocalFlag ?? ((key, value) => SharedPreferencesUtil().saveBool(key, value));

  final MessagingChannelsApi _api;
  final Future<ChatAppsConfig> Function() _readConfig;
  final bool Function(String key) _readLocalFlag;
  final Future<bool> Function(String key, bool value) _writeLocalFlag;

  static const _whatsAppWaitlistKey = 'chatAppsWhatsAppWaitlist';

  ChatAppsConfig _config = ChatAppsConfig.off;
  bool _configLoaded = false;
  List<ChannelLink> _links = const [];
  bool _linksLoaded = false;
  bool _loadingLinks = false;
  ApiProblem? _linksProblem;
  Future<void>? _loadInFlight;

  ChatAppsConfig get config => _config;
  bool get configLoaded => _configLoaded;
  List<ChannelLink> get links => _links;
  bool get linksLoaded => _linksLoaded;
  bool get isLoadingLinks => _loadingLinks;

  /// The last list refresh's failure; known links stay listed beside it.
  ApiProblem? get linksProblem => _linksProblem;

  /// Show the Integrations entry when the surface is on, or when links exist so a person can
  /// always reach Disconnect even after the rollout or their plan changes.
  bool get showEntry => _config.enabled || _links.isNotEmpty;

  ChannelLink? linkFor(ChatChannel channel) {
    for (final link in _links) {
      if (link.channel == channel) return link;
    }
    return null;
  }

  ChannelLink? linkById(String id) {
    for (final link in _links) {
      if (link.id == id) return link;
    }
    return null;
  }

  bool get whatsAppWaitlisted => _readLocalFlag(_whatsAppWaitlistKey);

  /// Remembers the request on this device. There is no waitlist API yet.
  Future<void> joinWhatsAppWaitlist() async {
    await _writeLocalFlag(_whatsAppWaitlistKey, true);
    notifyListeners();
  }

  /// Reads the gate and the links. Concurrent callers share one load.
  Future<void> load() => _loadInFlight ??= _load().whenComplete(() => _loadInFlight = null);

  Future<void> _load() async {
    final configFuture = _readConfig();
    await refreshLinks();
    _config = await configFuture;
    _configLoaded = true;
    notifyListeners();
  }

  /// Re-reads the links. Returns the result so a waiting flow can react to a failure.
  Future<ApiResult<List<ChannelLink>>> refreshLinks() async {
    _loadingLinks = true;
    notifyListeners();
    final result = await _api.listLinks();
    _loadingLinks = false;
    switch (result) {
      case ApiSuccess(:final data):
        _links = [for (final link in data) ChannelLink.fromGenerated(link)];
        _linksLoaded = true;
        _linksProblem = null;
        notifyListeners();
        return ApiSuccess(_links);
      case ApiFailure(:final problem):
        _linksProblem = problem;
        notifyListeners();
        return ApiFailure(problem);
    }
  }

  /// Mints a one-time proof for [channel]: `token` for a deep link, `code` for the person to
  /// text. Fails with `forbidden` outside the cohort or without Pro.
  Future<ApiResult<wire.GeneratedChannelLinkProof>> mintProof(
    ChatChannel channel, {
    required String kind,
  }) {
    final endpoint = _config.endpoint(channel);
    if (endpoint == null)
      return Future.value(
        const ApiFailure(ApiProblem(ApiProblemKind.forbidden)),
      );
    return _api.mintProof(
      channel: channel.wireId,
      provider: endpoint.provider,
      kind: kind,
    );
  }

  /// Unlinks and forgets the link locally; a 404 means it was already gone.
  Future<ApiResult<void>> unlink(ChannelLink link) async {
    final result = await _api.unlink(link.id);
    final gone = switch (result) {
      ApiSuccess() => true,
      ApiFailure(:final problem) => problem.kind == ApiProblemKind.notFound,
    };
    if (gone) {
      _links = [
        for (final l in _links)
          if (l.id != link.id) l,
      ];
      notifyListeners();
      return const ApiSuccess(null);
    }
    return result;
  }

  /// Applies the switch at once and reverts it if the server refuses.
  Future<ApiResult<void>> setVisibleInApp(ChannelLink link, bool visible) => _patch(
        link,
        visible,
        (l, value) => l.copyWith(visibleInApp: value),
        _api.setVisibleInApp,
      );

  Future<ApiResult<void>> setVoiceNotes(ChannelLink link, bool enabled) => _patch(
        link,
        enabled,
        (l, value) => l.copyWith(voiceNotes: value),
        _api.setVoiceNotes,
      );

  Future<ApiResult<void>> setKeepPrivateMemoriesInApp(
    ChannelLink link,
    bool enabled,
  ) =>
      _patch(
        link,
        enabled,
        (l, value) => l.copyWith(keepPrivateMemoriesInApp: value),
        _api.setKeepPrivateMemoriesInApp,
      );

  Future<ApiResult<void>> _patch(
    ChannelLink link,
    bool value,
    ChannelLink Function(ChannelLink link, bool value) apply,
    Future<ApiResult<void>> Function(String linkId, bool value) send,
  ) async {
    _replace(link.id, (l) => apply(l, value));
    final result = await send(link.id, value);
    if (result case ApiFailure(:final problem)) {
      if (problem.kind == ApiProblemKind.notFound) {
        _links = [
          for (final l in _links)
            if (l.id != link.id) l,
        ];
        notifyListeners();
      } else {
        _replace(link.id, (l) => apply(l, !value));
      }
    }
    return result;
  }

  void _replace(String id, ChannelLink Function(ChannelLink) change) {
    _links = [for (final l in _links) l.id == id ? change(l) : l];
    notifyListeners();
  }

  @visibleForTesting
  void debugSet({ChatAppsConfig? config, List<ChannelLink>? links}) {
    if (config != null) {
      _config = config;
      _configLoaded = true;
    }
    if (links != null) {
      _links = links;
      _linksLoaded = true;
    }
    notifyListeners();
  }
}
