import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
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

  bool conversationEventsToggled = false;
  bool transcriptsToggled = false;
  bool audioBytesToggled = false;
  bool daySummaryToggled = false;

  bool savingSettingsLoading = false;

  bool loadingExportMemories = false;
  bool loadingImportMemories = false;

  // Experimental switches. Like every switch in Settings they apply and are saved the moment they
  // flip (chat-apps-settings #2); only the webhook URL fields wait for Save.
  bool followUpQuestionEnabled = false;
  bool transcriptionDiagnosticEnabled = false;
  bool autoCreateSpeakersEnabled = false;
  bool vadGateEnabled = false;

  /// Webhook field values as last loaded or saved; [hasUnsavedWebhookChanges] compares against them.
  Map<String, String> _savedWebhookText = const {};

  DeveloperModeProvider() {
    for (final controller in _webhookControllers) {
      controller.addListener(_onWebhookTextChanged);
    }
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

  /// A webhook URL (or the audio interval) was edited and not saved yet. The page guards leaving
  /// with a discard confirmation while this is true.
  bool get hasUnsavedWebhookChanges {
    final current = _webhookText();
    return current.keys.any((k) => current[k] != (_savedWebhookText[k] ?? ''));
  }

  void onConversationEventsToggled(bool value) {
    conversationEventsToggled = value;
    if (!value) {
      disableWebhook(type: 'memory_created');
    } else {
      enableWebhook(type: 'memory_created');
    }
    notifyListeners();
  }

  void onTranscriptsToggled(bool value) {
    transcriptsToggled = value;
    if (!value) {
      disableWebhook(type: 'realtime_transcript');
    } else {
      enableWebhook(type: 'realtime_transcript');
    }
    notifyListeners();
  }

  void onAudioBytesToggled(bool value) {
    audioBytesToggled = value;
    if (!value) {
      disableWebhook(type: 'audio_bytes');
    } else {
      enableWebhook(type: 'audio_bytes');
    }
    notifyListeners();
  }

  void onDaySummaryToggled(bool value) {
    daySummaryToggled = value;
    if (!value) {
      disableWebhook(type: 'day_summary');
    } else {
      enableWebhook(type: 'day_summary');
    }
    notifyListeners();
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
    followUpQuestionEnabled = SharedPreferencesUtil().devModeJoanFollowUpEnabled;
    transcriptionDiagnosticEnabled = SharedPreferencesUtil().transcriptionDiagnosticEnabled;
    autoCreateSpeakersEnabled = SharedPreferencesUtil().autoCreateSpeakersEnabled;
    vadGateEnabled = SharedPreferencesUtil().vadGateEnabled;
    conversationEventsToggled = SharedPreferencesUtil().conversationEventsToggled;
    transcriptsToggled = SharedPreferencesUtil().transcriptsToggled;
    audioBytesToggled = SharedPreferencesUtil().audioBytesToggled;
    daySummaryToggled = SharedPreferencesUtil().daySummaryToggled;

    await Future.wait([
      getWebhooksStatus(),
      getUserWebhookUrl(type: 'audio_bytes').then((url) {
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
      getUserWebhookUrl(type: 'realtime_transcript').then((url) {
        webhookOnTranscriptReceived.text = url;
        SharedPreferencesUtil().webhookOnTranscriptReceived = url;
      }),
      getUserWebhookUrl(type: 'memory_created').then((url) {
        webhookOnConversationCreated.text = url;
        SharedPreferencesUtil().webhookOnConversationCreated = url;
      }),
      getUserWebhookUrl(type: 'day_summary').then((url) {
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

  /// Saves the webhook URLs (the only fields on Developer Settings that wait for Save). Resolves
  /// whether they were saved.
  Future<bool> saveSettings() async {
    if (savingSettingsLoading) return false;
    setIsLoading(true);
    final prefs = SharedPreferencesUtil();

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
    var w1 = setUserWebhookUrl(
      type: 'audio_bytes',
      url: '${webhookAudioBytes.text.trim()},${webhookAudioBytesDelay.text.trim()}',
    );
    var w2 = setUserWebhookUrl(type: 'realtime_transcript', url: webhookOnTranscriptReceived.text.trim());
    var w3 = setUserWebhookUrl(type: 'memory_created', url: webhookOnConversationCreated.text.trim());
    var w4 = setUserWebhookUrl(type: 'day_summary', url: webhookDaySummary.text.trim());
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
  }

  void setIsLoading(bool value) {
    savingSettingsLoading = value;
    notifyListeners();
  }

  void onFollowUpQuestionChanged(bool value) {
    followUpQuestionEnabled = value;
    SharedPreferencesUtil().devModeJoanFollowUpEnabled = value;
    notifyListeners();
  }

  void onTranscriptionDiagnosticChanged(bool value) {
    transcriptionDiagnosticEnabled = value;
    SharedPreferencesUtil().transcriptionDiagnosticEnabled = value;
    notifyListeners();
  }

  void onAutoCreateSpeakersChanged(bool value) {
    autoCreateSpeakersEnabled = value;
    SharedPreferencesUtil().autoCreateSpeakersEnabled = value;
    notifyListeners();
  }

  void onVadGateChanged(bool value) {
    vadGateEnabled = value;
    SharedPreferencesUtil().vadGateEnabled = value;
    notifyListeners();
  }

  @override
  void dispose() {
    for (final controller in _webhookControllers) {
      controller.removeListener(_onWebhookTextChanged);
    }
    super.dispose();
  }
}
