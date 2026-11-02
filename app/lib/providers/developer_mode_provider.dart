import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/backend_url_override.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/validators.dart';

class DeveloperModeProvider extends BaseProvider {
  final TextEditingController webhookOnConversationCreated = TextEditingController();
  final TextEditingController webhookOnTranscriptReceived = TextEditingController();
  final TextEditingController webhookAudioBytes = TextEditingController();
  final TextEditingController webhookAudioBytesDelay = TextEditingController();
  final TextEditingController webhookWsAudioBytes = TextEditingController();
  final TextEditingController webhookDaySummary = TextEditingController();
  final TextEditingController customBackendUrl = TextEditingController();

  bool conversationEventsToggled = false;
  bool transcriptsToggled = false;
  bool audioBytesToggled = false;
  bool daySummaryToggled = false;

  bool savingSettingsLoading = false;

  bool loadingExportMemories = false;
  bool loadingImportMemories = false;

  // Experimental switches. Like every switch in Settings they apply and are saved the moment they
  // flip (chat-apps-settings #2); webhook URLs and the custom backend URL wait for Save.
  bool transcriptionDiagnosticEnabled = false;
  bool vadGateEnabled = false;

  /// Webhook field values as last loaded or saved; [hasUnsavedWebhookChanges] compares against them.
  Map<String, String> _savedWebhookText = const {};
  String _savedCustomBackendUrl = '';

  /// Each webhook type and its fields (keys of [_webhookText]).
  static const Map<String, List<String>> _webhookFields = {
    'audio_bytes': ['audio', 'audioDelay'],
    'realtime_transcript': ['transcript'],
    'memory_created': ['conversation'],
    'day_summary': ['daySummary'],
  };

  /// Webhook types whose URL could not be read. Their fields show the cached URL instead.
  final Set<String> _unreadWebhooks = {};

  /// Reads a webhook URL, null when the read failed. Injectable for tests.
  final Future<String?> Function({required String type}) _fetchWebhookUrl;

  /// Saves a webhook URL; an empty URL turns the webhook off. Injectable for tests.
  final Future<bool> Function({required String type, required String url}) _saveWebhookUrl;

  DeveloperModeProvider({
    Future<String?> Function({required String type})? fetchWebhookUrl,
    Future<bool> Function({required String type, required String url})? saveWebhookUrl,
  })  : _fetchWebhookUrl = fetchWebhookUrl ?? getUserWebhookUrl,
        _saveWebhookUrl = saveWebhookUrl ?? setUserWebhookUrl {
    for (final controller in _webhookControllers) {
      controller.addListener(_onWebhookTextChanged);
    }
    customBackendUrl.addListener(_onWebhookTextChanged);
  }

  List<TextEditingController> get _webhookControllers => [
        webhookOnConversationCreated,
        webhookOnTranscriptReceived,
        webhookAudioBytes,
        webhookAudioBytesDelay,
        webhookDaySummary,
      ];

  Map<String, String> _webhookText() => {
        'conversation': webhookOnConversationCreated.text,
        'transcript': webhookOnTranscriptReceived.text,
        'audio': webhookAudioBytes.text,
        'audioDelay': webhookAudioBytesDelay.text,
        'daySummary': webhookDaySummary.text,
      };

  void _markWebhooksSaved() => _savedWebhookText = _webhookText();

  bool _lastDirty = false;

  void _onWebhookTextChanged() {
    final dirty = hasUnsavedWebhookChanges;
    if (dirty != _lastDirty) {
      _lastDirty = dirty;
      notifyListeners();
    }
  }

  /// A webhook URL, the audio interval, or the custom backend URL was edited and not saved yet.
  /// The page guards leaving with a discard confirmation while this is true.
  bool get hasUnsavedWebhookChanges {
    final current = _webhookText();
    return customBackendUrl.text != _savedCustomBackendUrl ||
        current.keys.any((k) => current[k] != (_savedWebhookText[k] ?? ''));
  }

  /// Webhook types with an on/off request still running. Another tap on that switch is ignored until
  /// the answer arrives, like a second Save, so two requests for one webhook cannot cross.
  final Set<String> _switchingWebhooks = {};

  Future<void> onConversationEventsToggled(bool value) =>
      _switchWebhook('memory_created', value, (enabled) => conversationEventsToggled = enabled);

  Future<void> onTranscriptsToggled(bool value) =>
      _switchWebhook('realtime_transcript', value, (enabled) => transcriptsToggled = enabled);

  Future<void> onAudioBytesToggled(bool value) =>
      _switchWebhook('audio_bytes', value, (enabled) => audioBytesToggled = enabled);

  Future<void> onDaySummaryToggled(bool value) =>
      _switchWebhook('day_summary', value, (enabled) => daySummaryToggled = enabled);

  /// Shows the [type] webhook's switch at [enabled] and asks the server to turn that webhook on or off.
  /// If the server does not confirm it, the webhook did not change, so the switch goes back and an
  /// error is shown.
  Future<void> _switchWebhook(String type, bool enabled, void Function(bool enabled) showSwitch) async {
    if (!_switchingWebhooks.add(type)) return;
    showSwitch(enabled);
    notifyListeners();
    try {
      final saved = enabled ? await enableWebhook(type: type) : await disableWebhook(type: type);
      if (saved) return;
    } finally {
      _switchingWebhooks.remove(type);
    }
    showSwitch(!enabled);
    notifyListeners();
    AppSnackbar.showSnackbarError(
      globalNavigatorKey.currentContext?.l10n.failedToSaveCheckConnection ??
          'Failed to save. Please check your connection.',
    );
  }

  Future getWebhooksStatus() async {
    var res = await webhooksStatus();
    // A failed read is not "all four are off": keep the last known values instead of
    // reporting the webhooks as disabled and caching that over the good ones.
    if (res == null) return;
    conversationEventsToggled = res['memory_created'];
    transcriptsToggled = res['realtime_transcript'];
    audioBytesToggled = res['audio_bytes'];
    daySummaryToggled = res['day_summary'];
    SharedPreferencesUtil().conversationEventsToggled = conversationEventsToggled;
    SharedPreferencesUtil().transcriptsToggled = transcriptsToggled;
    SharedPreferencesUtil().audioBytesToggled = audioBytesToggled;
    SharedPreferencesUtil().daySummaryToggled = daySummaryToggled;
    notifyListeners();
  }

  Future initialize() async {
    setIsLoading(true);
    webhookOnConversationCreated.text = SharedPreferencesUtil().webhookOnConversationCreated;
    webhookOnTranscriptReceived.text = SharedPreferencesUtil().webhookOnTranscriptReceived;
    webhookAudioBytes.text = SharedPreferencesUtil().webhookAudioBytes;
    webhookAudioBytesDelay.text = SharedPreferencesUtil().webhookAudioBytesDelay;
    webhookDaySummary.text = SharedPreferencesUtil().webhookDaySummary;
    _savedCustomBackendUrl = SharedPreferencesUtil().customBackendUrl;
    customBackendUrl.text = _savedCustomBackendUrl;
    transcriptionDiagnosticEnabled = SharedPreferencesUtil().transcriptionDiagnosticEnabled;
    vadGateEnabled = SharedPreferencesUtil().vadGateEnabled;
    conversationEventsToggled = SharedPreferencesUtil().conversationEventsToggled;
    transcriptsToggled = SharedPreferencesUtil().transcriptsToggled;
    audioBytesToggled = SharedPreferencesUtil().audioBytesToggled;
    daySummaryToggled = SharedPreferencesUtil().daySummaryToggled;

    await Future.wait([
      getWebhooksStatus(),
      _loadWebhookUrl('audio_bytes', (url) {
        List<dynamic> parts = url.split(',');
        if (parts.length == 2) {
          webhookAudioBytes.text = parts[0].toString();
          webhookAudioBytesDelay.text = parts[1].toString();
        } else {
          webhookAudioBytes.text = url;
          webhookAudioBytesDelay.text = '5';
        }
        SharedPreferencesUtil().webhookAudioBytes = webhookAudioBytes.text;
        SharedPreferencesUtil().webhookAudioBytesDelay = webhookAudioBytesDelay.text;
      }),
      _loadWebhookUrl('realtime_transcript', (url) {
        webhookOnTranscriptReceived.text = url;
        SharedPreferencesUtil().webhookOnTranscriptReceived = url;
      }),
      _loadWebhookUrl('memory_created', (url) {
        webhookOnConversationCreated.text = url;
        SharedPreferencesUtil().webhookOnConversationCreated = url;
      }),
      _loadWebhookUrl('day_summary', (url) {
        webhookDaySummary.text = url;
        SharedPreferencesUtil().webhookDaySummary = url;
      }),
    ]);
    // getUserWebhookUrl(type: 'audio_bytes_websocket').then((url) => webhookWsAudioBytes.text = url);
    _markWebhooksSaved();
    _lastDirty = false;
    setIsLoading(false);
    notifyListeners();
  }

  /// Hands the [type] webhook's URL to [apply]. A failed read is not an empty URL: the fields keep
  /// their cached text, the cache is left alone, and the webhook is marked unread for Save.
  Future<void> _loadWebhookUrl(String type, void Function(String url) apply) async {
    final url = await _fetchWebhookUrl(type: type);
    if (url == null) {
      _unreadWebhooks.add(type);
      return;
    }
    apply(url);
  }

  /// Whether Save writes the [type] webhook. One whose URL could not be read is written only once one
  /// of its fields is edited: its cached text may be stale or empty, and an empty URL turns it off.
  bool _savesWebhook(String type) {
    if (!_unreadWebhooks.contains(type)) return true;
    final current = _webhookText();
    return _webhookFields[type]!.any((field) => current[field] != (_savedWebhookText[field] ?? ''));
  }

  /// Saves webhook URLs and, outside release builds, the custom backend URL. Resolves whether
  /// they were saved.
  Future<bool> saveSettings() async {
    if (savingSettingsLoading) return false;
    setIsLoading(true);
    final prefs = SharedPreferencesUtil();
    // Decided before the audio interval default below, which is not an edit.
    final webhooksToSave = _webhookFields.keys.where(_savesWebhook).toSet();

    if (!kReleaseMode) {
      try {
        final rawBackendUrl = customBackendUrl.text.trim();
        final normalizedBackendUrl = rawBackendUrl.isEmpty ? '' : BackendUrlOverride.parse(rawBackendUrl).url;
        prefs.customBackendUrl = normalizedBackendUrl;
        _savedCustomBackendUrl = normalizedBackendUrl;
        customBackendUrl.text = normalizedBackendUrl;
        BackendUrlOverride.restore(normalizedBackendUrl);
      } on FormatException catch (error) {
        AppSnackbar.showSnackbarError(error.message);
        setIsLoading(false);
        return false;
      }
    }

    if (webhookAudioBytes.text.isNotEmpty && !isValidUrl(webhookAudioBytes.text)) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.devModeInvalidAudioBytesWebhookUrl ?? 'Invalid audio bytes webhook URL',
      );
      setIsLoading(false);
      return false;
    }
    if (webhookAudioBytes.text.isNotEmpty && webhookAudioBytesDelay.text.isEmpty) {
      webhookAudioBytesDelay.text = '5';
    }
    if (webhookOnTranscriptReceived.text.isNotEmpty && !isValidUrl(webhookOnTranscriptReceived.text)) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.devModeInvalidRealtimeTranscriptWebhookUrl ??
            'Invalid realtime transcript webhook URL',
      );
      setIsLoading(false);
      return false;
    }
    if (webhookOnConversationCreated.text.isNotEmpty && !isValidUrl(webhookOnConversationCreated.text)) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.devModeInvalidConversationCreatedWebhookUrl ??
            'Invalid conversation created webhook URL',
      );
      setIsLoading(false);
      return false;
    }
    if (webhookDaySummary.text.isNotEmpty && !isValidUrl(webhookDaySummary.text)) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.devModeInvalidDaySummaryWebhookUrl ?? 'Invalid day summary webhook URL',
      );
      setIsLoading(false);
      return false;
    }

    // if (webhookWsAudioBytes.text.isNotEmpty && !isValidWebSocketUrl(webhookWsAudioBytes.text)) {
    //   AppSnackbar.showSnackbarError('Invalid audio bytes websocket URL');
    //   savingSettingsLoading = false;
    //   notifyListeners();
    //   return;
    // }
    Future<bool> saveWebhook(String type, String url) =>
        webhooksToSave.contains(type) ? _saveWebhookUrl(type: type, url: url) : Future.value(true);
    var w1 = saveWebhook('audio_bytes', '${webhookAudioBytes.text.trim()},${webhookAudioBytesDelay.text.trim()}');
    var w2 = saveWebhook('realtime_transcript', webhookOnTranscriptReceived.text.trim());
    var w3 = saveWebhook('memory_created', webhookOnConversationCreated.text.trim());
    var w4 = saveWebhook('day_summary', webhookDaySummary.text.trim());
    // var w4 = setUserWebhookUrl(type: 'audio_bytes_websocket', url: webhookWsAudioBytes.text.trim());
    var webhooksSaved = false;
    try {
      webhooksSaved = !(await Future.wait([w1, w2, w3, w4])).contains(false);
      if (webhooksSaved) {
        prefs.webhookAudioBytes = webhookAudioBytes.text;
        prefs.webhookAudioBytesDelay = webhookAudioBytesDelay.text;
        prefs.webhookOnTranscriptReceived = webhookOnTranscriptReceived.text;
        prefs.webhookOnConversationCreated = webhookOnConversationCreated.text;
        prefs.webhookDaySummary = webhookDaySummary.text;
        _markWebhooksSaved();
        _lastDirty = false;
      }
    } catch (e) {
      Logger.error('Error occurred while updating endpoints: $e');
    }
    PlatformManager.instance.analytics.settingsSaved(
      hasWebhookConversationCreated: conversationEventsToggled,
      hasWebhookTranscriptReceived: transcriptsToggled,
    );
    setIsLoading(false);
    notifyListeners();
    if (!webhooksSaved) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.failedToSaveCheckConnection ??
            'Failed to save. Please check your connection.',
      );
      return false;
    }
    AppSnackbar.showSnackbar(globalNavigatorKey.currentContext?.l10n.devModeSettingsSaved ?? 'Settings saved!');
    return true;
  }

  /// Puts the webhook fields back to their last saved values (the "Discard" answer).
  void discardWebhookChanges() {
    webhookOnConversationCreated.text = _savedWebhookText['conversation'] ?? '';
    webhookOnTranscriptReceived.text = _savedWebhookText['transcript'] ?? '';
    webhookAudioBytes.text = _savedWebhookText['audio'] ?? '';
    webhookAudioBytesDelay.text = _savedWebhookText['audioDelay'] ?? '';
    webhookDaySummary.text = _savedWebhookText['daySummary'] ?? '';
    customBackendUrl.text = _savedCustomBackendUrl;
  }

  void setIsLoading(bool value) {
    savingSettingsLoading = value;
    notifyListeners();
  }

  void onTranscriptionDiagnosticChanged(bool value) {
    transcriptionDiagnosticEnabled = value;
    SharedPreferencesUtil().transcriptionDiagnosticEnabled = value;
    notifyListeners();
  }

  void onVadGateChanged(bool value) {
    vadGateEnabled = value;
    SharedPreferencesUtil().vadGateEnabled = value;
    notifyListeners();
  }

  /// Developer Settings disposes this provider when the page closes, which can happen while a load or a
  /// save is still waiting on the server. When that request finishes there is nothing left to update,
  /// and notifying a disposed notifier is an error.
  bool _disposed = false;

  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    for (final controller in _webhookControllers) {
      controller.removeListener(_onWebhookTextChanged);
    }
    customBackendUrl.removeListener(_onWebhookTextChanged);
    super.dispose();
  }
}
