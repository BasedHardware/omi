import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/utils/alerts/app_dialog.dart';
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
  final TextEditingController customApiUrlController = TextEditingController();
  final TextEditingController newServerUrlController = TextEditingController();

  bool conversationEventsToggled = false;
  bool transcriptsToggled = false;
  bool audioBytesToggled = false;
  bool daySummaryToggled = false;

  bool savingSettingsLoading = false;
  bool serverOperationLoading = false;

  bool loadingExportMemories = false;
  bool loadingImportMemories = false;

  bool localSyncEnabled = false;
  bool followUpQuestionEnabled = false;
  bool transcriptionDiagnosticEnabled = false;

  // Server URL list management
  List<String> customApiUrls = [];
  String currentCustomApiUrl = '';
  String originalApiUrl = '';

  // Get the default API base URL from the Env class
  String get defaultApiBaseUrl => Env.apiBaseUrl ?? '';

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
    if (res == null) {
      conversationEventsToggled = false;
      transcriptsToggled = false;
      audioBytesToggled = false;
      daySummaryToggled = false;
    } else {
      conversationEventsToggled = res['memory_created'];
      transcriptsToggled = res['realtime_transcript'];
      audioBytesToggled = res['audio_bytes'];
      daySummaryToggled = res['day_summary'];
    }
    SharedPreferencesUtil().conversationEventsToggled = conversationEventsToggled;
    SharedPreferencesUtil().transcriptsToggled = transcriptsToggled;
    SharedPreferencesUtil().audioBytesToggled = audioBytesToggled;
    SharedPreferencesUtil().daySummaryToggled = daySummaryToggled;
    notifyListeners();
  }

  Future initialize() async {
    setIsLoading(true);
    localSyncEnabled = SharedPreferencesUtil().localSyncEnabled;
    webhookOnConversationCreated.text = SharedPreferencesUtil().webhookOnConversationCreated;
    webhookOnTranscriptReceived.text = SharedPreferencesUtil().webhookOnTranscriptReceived;
    webhookAudioBytes.text = SharedPreferencesUtil().webhookAudioBytes;
    webhookAudioBytesDelay.text = SharedPreferencesUtil().webhookAudioBytesDelay;
    followUpQuestionEnabled = SharedPreferencesUtil().devModeJoanFollowUpEnabled;
    transcriptionDiagnosticEnabled = SharedPreferencesUtil().transcriptionDiagnosticEnabled;
    conversationEventsToggled = SharedPreferencesUtil().conversationEventsToggled;
    transcriptsToggled = SharedPreferencesUtil().transcriptsToggled;
    audioBytesToggled = SharedPreferencesUtil().audioBytesToggled;
    daySummaryToggled = SharedPreferencesUtil().daySummaryToggled;

    final prefs = SharedPreferencesUtil();

    // Initialize server URL management
    originalApiUrl = defaultApiBaseUrl;
    currentCustomApiUrl = prefs.getString(Env.customApiBaseUrlKey) ?? '';
    customApiUrlController.text = currentCustomApiUrl;

    // Load saved custom API URLs
    loadCustomApiUrls();

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
    setIsLoading(false);
    notifyListeners();
  }

  void loadCustomApiUrls() {
    final prefs = SharedPreferencesUtil();
    final savedUrls = prefs.getStringList('custom_api_urls') ?? [];
    customApiUrls = savedUrls.toSet().toList(); // Remove duplicates

    // Add current URL if it's not in the list and it's not empty
    if (currentCustomApiUrl.isNotEmpty && !customApiUrls.contains(currentCustomApiUrl)) {
      customApiUrls.add(currentCustomApiUrl);
      saveCustomApiUrls();
    }

    notifyListeners();
  }

  void saveCustomApiUrls() {
    final prefs = SharedPreferencesUtil();
    prefs.saveStringList('custom_api_urls', customApiUrls);
  }

  Future<bool> addNewCustomApiUrl(String url) async {
    url = url.trim();
    if (url.isEmpty || !isValidUrl(url)) return false;

    if (!customApiUrls.contains(url)) {
      customApiUrls.add(url);
      saveCustomApiUrls();
      notifyListeners();
      return true;
    }
    return false;
  }

  Future<void> removeCustomApiUrl(String url) async {
    serverOperationLoading = true;
    notifyListeners();

    try {
      customApiUrls.remove(url);
      saveCustomApiUrls();

      // If current URL was removed, reset to original
      if (currentCustomApiUrl == url) {
        currentCustomApiUrl = '';
        customApiUrlController.text = '';
        await Env.setCustomApiBaseUrl('');
      }
    } finally {
      serverOperationLoading = false;
      notifyListeners();
    }
  }

  Future<void> selectCustomApiUrl(String url) async {
    serverOperationLoading = true;
    notifyListeners();

    try {
      // Don't update customApiUrlController, only update current URL
      currentCustomApiUrl = url;
      await Env.setCustomApiBaseUrl(url);
    } finally {
      serverOperationLoading = false;
      notifyListeners();
    }
  }

  Future<void> resetToOriginalUrl() async {
    serverOperationLoading = true;
    notifyListeners();

    try {
      customApiUrlController.text = '';
      currentCustomApiUrl = '';
      await Env.setCustomApiBaseUrl('');
      originalApiUrl = defaultApiBaseUrl; // Refresh the original URL
    } finally {
      serverOperationLoading = false;
      notifyListeners();
    }
  }

  String getCurrentActiveUrl() {
    return currentCustomApiUrl.isNotEmpty ? currentCustomApiUrl : originalApiUrl;
  }

  void saveSettings() async {
    if (savingSettingsLoading) return;
    setIsLoading(true);
    final prefs = SharedPreferencesUtil();

    final customApiUrl = customApiUrlController.text.trim();
    if (customApiUrl.isNotEmpty && !isValidUrl(customApiUrl)) {
      AppSnackbar.showSnackbarError('Invalid Custom Backend URL');
      setIsLoading(false);
      return;
    }

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

    var w1 = setUserWebhookUrl(
      type: 'audio_bytes',
      url: '${webhookAudioBytes.text.trim()},${webhookAudioBytesDelay.text.trim()}',
    );
    var w2 = setUserWebhookUrl(type: 'realtime_transcript', url: webhookOnTranscriptReceived.text.trim());
    var w3 = setUserWebhookUrl(type: 'memory_created', url: webhookOnConversationCreated.text.trim());
    var w4 = setUserWebhookUrl(type: 'day_summary', url: webhookDaySummary.text.trim());
    try {
      Future.wait([w1, w2, w3, w4]);
      prefs.webhookAudioBytes = webhookAudioBytes.text;
      prefs.webhookAudioBytesDelay = webhookAudioBytesDelay.text;
      prefs.webhookOnTranscriptReceived = webhookOnTranscriptReceived.text;
      prefs.webhookOnConversationCreated = webhookOnConversationCreated.text;
      prefs.webhookDaySummary = webhookDaySummary.text;

      // Save new custom API URL and add to list if not empty
      await Env.setCustomApiBaseUrl(customApiUrl);
      currentCustomApiUrl = customApiUrl;
      if (customApiUrl.isNotEmpty) {
        await addNewCustomApiUrl(customApiUrl);
      }
    } catch (e) {
      Logger.error('Error occurred while updating endpoints: $e');
    }
    prefs.localSyncEnabled = localSyncEnabled;
    prefs.devModeJoanFollowUpEnabled = followUpQuestionEnabled;
    prefs.transcriptionDiagnosticEnabled = transcriptionDiagnosticEnabled;

    MixpanelManager().settingsSaved(
      hasWebhookConversationCreated: conversationEventsToggled,
      hasWebhookTranscriptReceived: transcriptsToggled,
    );
    setIsLoading(false);
    notifyListeners();
    AppDialog.show(
      title: 'Settings Saved',
      content: 'Your settings have been saved. Please restart the app for the backend URL change to take effect.',
      singleButton: true,
      okButtonText: 'OK',
    );
  }

  void setIsLoading(bool value) {
    savingSettingsLoading = value;
    notifyListeners();
  }

  void onLocalSyncEnabledChanged(var value) {
    localSyncEnabled = value;
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
}
