import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
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

  bool followUpQuestionEnabled = false;
  bool transcriptionDiagnosticEnabled = false;
  bool autoCreateSpeakersEnabled = false;

  Future<void> onConversationEventsToggled(bool value) async {
    conversationEventsToggled = value;
    SharedPreferencesUtil().conversationEventsToggled = value;
    notifyListeners();

    try {
      if (!value) {
        await disableWebhook(type: 'memory_created');
      } else {
        await enableWebhook(type: 'memory_created');
      }
    } catch (e) {
      Logger.error('Failed to toggle conversation events webhook: $e');
      conversationEventsToggled = !value;
      SharedPreferencesUtil().conversationEventsToggled = !value;
      notifyListeners();
    }
  }

  Future<void> onTranscriptsToggled(bool value) async {
    transcriptsToggled = value;
    SharedPreferencesUtil().transcriptsToggled = value;
    notifyListeners();

    try {
      if (!value) {
        await disableWebhook(type: 'realtime_transcript');
      } else {
        await enableWebhook(type: 'realtime_transcript');
      }
    } catch (e) {
      Logger.error('Failed to toggle transcripts webhook: $e');
      transcriptsToggled = !value;
      SharedPreferencesUtil().transcriptsToggled = !value;
      notifyListeners();
    }
  }

  Future<void> onAudioBytesToggled(bool value) async {
    audioBytesToggled = value;
    SharedPreferencesUtil().audioBytesToggled = value;
    notifyListeners();

    try {
      if (!value) {
        await disableWebhook(type: 'audio_bytes');
      } else {
        await enableWebhook(type: 'audio_bytes');
      }
    } catch (e) {
      Logger.error('Failed to toggle audio bytes webhook: $e');
      audioBytesToggled = !value;
      SharedPreferencesUtil().audioBytesToggled = !value;
      notifyListeners();
    }
  }

  Future<void> onDaySummaryToggled(bool value) async {
    daySummaryToggled = value;
    SharedPreferencesUtil().daySummaryToggled = value;
    notifyListeners();

    try {
      if (!value) {
        await disableWebhook(type: 'day_summary');
      } else {
        await enableWebhook(type: 'day_summary');
      }
    } catch (e) {
      Logger.error('Failed to toggle day summary webhook: $e');
      daySummaryToggled = !value;
      SharedPreferencesUtil().daySummaryToggled = !value;
      notifyListeners();
    }
  }

  Future getWebhooksStatus() async {
    var res = await webhooksStatus();
    if (res == null) {
      return;
    }
    conversationEventsToggled = res['memory_created'] ?? false;
    transcriptsToggled = res['realtime_transcript'] ?? false;
    audioBytesToggled = res['audio_bytes'] ?? false;
    daySummaryToggled = res['day_summary'] ?? false;

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
    followUpQuestionEnabled = SharedPreferencesUtil().devModeJoanFollowUpEnabled;
    transcriptionDiagnosticEnabled = SharedPreferencesUtil().transcriptionDiagnosticEnabled;
    autoCreateSpeakersEnabled = SharedPreferencesUtil().autoCreateSpeakersEnabled;
    conversationEventsToggled = SharedPreferencesUtil().conversationEventsToggled;
    transcriptsToggled = SharedPreferencesUtil().transcriptsToggled;
    audioBytesToggled = SharedPreferencesUtil().audioBytesToggled;
    daySummaryToggled = SharedPreferencesUtil().daySummaryToggled;

    await Future.wait([
      getUserWebhookUrl(type: 'audio_bytes').then((url) {
        if (url.isNotEmpty) {
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
        }
      }),
      getUserWebhookUrl(type: 'realtime_transcript').then((url) {
        if (url.isNotEmpty) {
          webhookOnTranscriptReceived.text = url;
          SharedPreferencesUtil().webhookOnTranscriptReceived = url;
        }
      }),
      getUserWebhookUrl(type: 'memory_created').then((url) {
        if (url.isNotEmpty) {
          webhookOnConversationCreated.text = url;
          SharedPreferencesUtil().webhookOnConversationCreated = url;
        }
      }),
      getUserWebhookUrl(type: 'day_summary').then((url) {
        if (url.isNotEmpty) {
          webhookDaySummary.text = url;
          SharedPreferencesUtil().webhookDaySummary = url;
        }
      }),
    ]);

    await getWebhooksStatus();

    setIsLoading(false);
    notifyListeners();
  }

  Future<void> saveSettings() async {
    if (savingSettingsLoading) return;
    setIsLoading(true);
    final prefs = SharedPreferencesUtil();

    if (webhookAudioBytes.text.isNotEmpty && !isValidUrl(webhookAudioBytes.text)) {
      AppSnackbar.showSnackbarError('Invalid audio bytes webhook URL');
      setIsLoading(false);
      return;
    }
    if (webhookAudioBytes.text.isNotEmpty && webhookAudioBytesDelay.text.isEmpty) {
      webhookAudioBytesDelay.text = '5';
    }
    if (webhookOnTranscriptReceived.text.isNotEmpty && !isValidUrl(webhookOnTranscriptReceived.text)) {
      AppSnackbar.showSnackbarError('Invalid realtime transcript webhook URL');
      setIsLoading(false);
      return;
    }
    if (webhookOnConversationCreated.text.isNotEmpty && !isValidUrl(webhookOnConversationCreated.text)) {
      AppSnackbar.showSnackbarError('Invalid conversation created webhook URL');
      setIsLoading(false);
      return;
    }
    if (webhookDaySummary.text.isNotEmpty && !isValidUrl(webhookDaySummary.text)) {
      AppSnackbar.showSnackbarError('Invalid day summary webhook URL');
      setIsLoading(false);
      return;
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
    try {
      await Future.wait([w1, w2, w3, w4]);
      prefs.webhookAudioBytes = webhookAudioBytes.text;
      prefs.webhookAudioBytesDelay = webhookAudioBytesDelay.text;
      prefs.webhookOnTranscriptReceived = webhookOnTranscriptReceived.text;
      prefs.webhookOnConversationCreated = webhookOnConversationCreated.text;
      prefs.webhookDaySummary = webhookDaySummary.text;
    } catch (e) {
      Logger.error('Error occurred while updating endpoints: $e');
      setIsLoading(false);
      AppSnackbar.showSnackbarError('Failed to save webhook settings. Please try again.');
      return;
    }
    // Experimental
    prefs.devModeJoanFollowUpEnabled = followUpQuestionEnabled;
    prefs.transcriptionDiagnosticEnabled = transcriptionDiagnosticEnabled;
    prefs.autoCreateSpeakersEnabled = autoCreateSpeakersEnabled;

    MixpanelManager().settingsSaved(
      hasWebhookConversationCreated: conversationEventsToggled,
      hasWebhookTranscriptReceived: transcriptsToggled,
    );
    setIsLoading(false);
    notifyListeners();
    AppSnackbar.showSnackbar('Settings saved!');
  }

  void setIsLoading(bool value) {
    savingSettingsLoading = value;
    notifyListeners();
  }

  void onFollowUpQuestionChanged(var value) {
    followUpQuestionEnabled = value;
    notifyListeners();
  }

  void onTranscriptionDiagnosticChanged(var value) {
    transcriptionDiagnosticEnabled = value;
    notifyListeners();
  }

  void onAutoCreateSpeakersChanged(var value) {
    autoCreateSpeakersEnabled = value;
    notifyListeners();
  }

  @override
  void dispose() {
    webhookOnConversationCreated.dispose();
    webhookOnTranscriptReceived.dispose();
    webhookAudioBytes.dispose();
    webhookAudioBytesDelay.dispose();
    webhookWsAudioBytes.dispose();
    webhookDaySummary.dispose();
    super.dispose();
  }
}
