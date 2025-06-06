import 'dart:io';
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
  final TextEditingController webhookOnConversationCreated =
      TextEditingController();
  final TextEditingController webhookOnTranscriptReceived =
      TextEditingController();
  final TextEditingController webhookAudioBytes = TextEditingController();
  final TextEditingController webhookAudioBytesDelay = TextEditingController();
  final TextEditingController webhookWsAudioBytes = TextEditingController();
  final TextEditingController webhookDaySummary = TextEditingController();
  final TextEditingController customApiUrlController = TextEditingController();
  final TextEditingController newServerUrlController = TextEditingController();

  // STT Server Settings
  final TextEditingController wyomingServerIpController =
      TextEditingController();
  String _sttServerType = 'traditional'; // 'traditional' or 'wyoming'
  bool _wyomingConnectionTested = false;

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

  // STT Server Settings Getters
  String get sttServerType => _sttServerType;
  bool get wyomingConnectionTested => _wyomingConnectionTested;

  // Get the default API base URL from the Env class
  String get defaultApiBaseUrl => Env.apiBaseUrl ?? '';

  // Display a friendly name instead of the actual URL for the default server
  String getDisplayNameForUrl(String url) {
    if (url == defaultApiBaseUrl) {
      return "Omi Official Server";
    }
    return url;
  }

  // Ensure URL always ends with a slash
  String normalizeUrl(String url) {
    url = url.trim();
    if (url.isEmpty) return url;

    if (!url.endsWith('/')) {
      url = '$url/';
    }
    return url;
  }

  // STT Server Methods
  void onSttServerTypeChanged(String newType) {
    _sttServerType = newType;
    notifyListeners();
    // Auto-save STT settings when changed
    _saveSttSettings();
  }

  Future<bool> testWyomingConnection(String ipAddress) async {
    if (ipAddress.trim().isEmpty) return false;

    try {
      // Parse IP address and port
      String host = 'localhost';
      int port = 10300;

      if (ipAddress.contains(':')) {
        final parts = ipAddress.split(':');
        host = parts[0];
        port = int.tryParse(parts[1]) ?? 10300;
      } else {
        host = ipAddress;
      }

      print('Testing Wyoming connection to $host:$port');

      // Test TCP connection to Wyoming server
      final socket =
          await Socket.connect(host, port, timeout: const Duration(seconds: 5));
      await socket.close();

      _wyomingConnectionTested = true;
      notifyListeners();

      print('Wyoming connection successful');
      return true;
    } catch (e) {
      print('Wyoming connection test failed: $e');
      _wyomingConnectionTested = false;
      notifyListeners();
      return false;
    }
  }

// Save STT settings to SharedPreferences
  Future<void> _saveSttSettings() async {
    try {
      final prefs = SharedPreferencesUtil();
      prefs.sttServerType = _sttServerType;
      prefs.wyomingServerIp = wyomingServerIpController.text;
      print(
          'STT settings saved: $_sttServerType, ${wyomingServerIpController.text}');
    } catch (e) {
      print('Failed to save STT settings: $e');
    }
  }

// Load STT settings from SharedPreferences
  Future<void> _loadSttSettings() async {
    try {
      final prefs = SharedPreferencesUtil();
      _sttServerType = prefs.sttServerType;
      wyomingServerIpController.text = prefs.wyomingServerIp;
      print(
          'STT settings loaded: $_sttServerType, ${wyomingServerIpController.text}');
      notifyListeners();
    } catch (e) {
      print('Failed to load STT settings: $e');
    }
  }

// Also update your saveSettings method to include STT settings
  void saveSettings() async {
    if (savingSettingsLoading) return;
    setIsLoading(true);
    final prefs = SharedPreferencesUtil();

    try {
      final customApiUrl = customApiUrlController.text.trim();
      if (customApiUrl.isNotEmpty && !isValidUrl(customApiUrl)) {
        AppSnackbar.showSnackbarError('Invalid Custom Backend URL');
        return;
      }

      if (webhookAudioBytes.text.isNotEmpty &&
          !isValidUrl(webhookAudioBytes.text)) {
        AppSnackbar.showSnackbarError('Invalid audio bytes webhook URL');
        return;
      }
      if (webhookAudioBytes.text.isNotEmpty &&
          webhookAudioBytesDelay.text.isEmpty) {
        webhookAudioBytesDelay.text = '5';
      }
      if (webhookOnTranscriptReceived.text.isNotEmpty &&
          !isValidUrl(webhookOnTranscriptReceived.text)) {
        AppSnackbar.showSnackbarError(
            'Invalid realtime transcript webhook URL');
        return;
      }
      if (webhookOnConversationCreated.text.isNotEmpty &&
          !isValidUrl(webhookOnConversationCreated.text)) {
        AppSnackbar.showSnackbarError(
            'Invalid conversation created webhook URL');
        return;
      }
      if (webhookDaySummary.text.isNotEmpty &&
          !isValidUrl(webhookDaySummary.text)) {
        AppSnackbar.showSnackbarError('Invalid day summary webhook URL');
        return;
      }

      // Validate Wyoming IP if Wyoming is selected
      if (_sttServerType == 'wyoming' &&
          wyomingServerIpController.text.trim().isEmpty) {
        AppSnackbar.showSnackbarError(
            'Wyoming server IP address is required when Wyoming is selected');
        return;
      }

      // Update webhook URLs
      await Future.wait([
        setUserWebhookUrl(
          type: 'audio_bytes',
          url:
              '${webhookAudioBytes.text.trim()},${webhookAudioBytesDelay.text.trim()}',
        ),
        setUserWebhookUrl(
          type: 'realtime_transcript',
          url: webhookOnTranscriptReceived.text.trim(),
        ),
        setUserWebhookUrl(
          type: 'memory_created',
          url: webhookOnConversationCreated.text.trim(),
        ),
        setUserWebhookUrl(
          type: 'day_summary',
          url: webhookDaySummary.text.trim(),
        ),
      ]);

      // Save webhook URLs to preferences
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

      await _saveSttSettings();

      prefs.localSyncEnabled = localSyncEnabled;
      prefs.devModeJoanFollowUpEnabled = followUpQuestionEnabled;
      prefs.transcriptionDiagnosticEnabled = transcriptionDiagnosticEnabled;

      MixpanelManager().settingsSaved(
        hasWebhookConversationCreated: conversationEventsToggled,
        hasWebhookTranscriptReceived: transcriptsToggled,
      );

      AppDialog.show(
        title: 'Settings Saved',
        content:
            'Your settings have been saved. Please restart the app for changes to take effect.',
        singleButton: true,
        okButtonText: 'OK',
      );
    } catch (e) {
      Logger.error('Error occurred while saving settings: $e');
      AppSnackbar.showSnackbarError(
          'Failed to save settings. Please try again.');
    } finally {
      setIsLoading(false);
      notifyListeners();
    }
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
    SharedPreferencesUtil().conversationEventsToggled =
        conversationEventsToggled;
    SharedPreferencesUtil().transcriptsToggled = transcriptsToggled;
    SharedPreferencesUtil().audioBytesToggled = audioBytesToggled;
    SharedPreferencesUtil().daySummaryToggled = daySummaryToggled;
    notifyListeners();
  }

  Future initialize() async {
    if (savingSettingsLoading) return;
    setIsLoading(true);

    try {
      // Only load from SharedPreferences if values are empty
      if (webhookOnConversationCreated.text.isEmpty) {
        webhookOnConversationCreated.text =
            SharedPreferencesUtil().webhookOnConversationCreated;
      }
      if (webhookOnTranscriptReceived.text.isEmpty) {
        webhookOnTranscriptReceived.text =
            SharedPreferencesUtil().webhookOnTranscriptReceived;
      }
      if (webhookAudioBytes.text.isEmpty) {
        webhookAudioBytes.text = SharedPreferencesUtil().webhookAudioBytes;
      }
      if (webhookAudioBytesDelay.text.isEmpty) {
        webhookAudioBytesDelay.text =
            SharedPreferencesUtil().webhookAudioBytesDelay;
      }

      // Load other settings only if not already set
      if (!followUpQuestionEnabled) {
        followUpQuestionEnabled =
            SharedPreferencesUtil().devModeJoanFollowUpEnabled;
      }
      if (!transcriptionDiagnosticEnabled) {
        transcriptionDiagnosticEnabled =
            SharedPreferencesUtil().transcriptionDiagnosticEnabled;
      }
      if (!localSyncEnabled) {
        localSyncEnabled = SharedPreferencesUtil().localSyncEnabled;
      }

      final prefs = SharedPreferencesUtil();

      if (originalApiUrl.isEmpty) {
        originalApiUrl = defaultApiBaseUrl;
      }
      if (currentCustomApiUrl.isEmpty) {
        currentCustomApiUrl = prefs.getString(Env.customApiBaseUrlKey) ?? '';
        customApiUrlController.text = currentCustomApiUrl;
      }

      // Load saved custom API URLs
      loadCustomApiUrls();

      await _loadSttSettings();

      // Only fetch webhook status if toggles are not set
      if (!conversationEventsToggled &&
          !transcriptsToggled &&
          !audioBytesToggled &&
          !daySummaryToggled) {
        await getWebhooksStatus();
      }

      // Only fetch webhook URLs if they're empty
      if (webhookAudioBytes.text.isEmpty ||
          webhookOnTranscriptReceived.text.isEmpty ||
          webhookOnConversationCreated.text.isEmpty ||
          webhookDaySummary.text.isEmpty) {
        await Future.wait([
          getUserWebhookUrl(type: 'audio_bytes').then((url) {
            if (webhookAudioBytes.text.isEmpty) {
              List<dynamic> parts = url.split(',');
              if (parts.length == 2) {
                webhookAudioBytes.text = parts[0].toString();
                webhookAudioBytesDelay.text = parts[1].toString();
              } else {
                webhookAudioBytes.text = url;
                webhookAudioBytesDelay.text = '5';
              }
              SharedPreferencesUtil().webhookAudioBytes =
                  webhookAudioBytes.text;
              SharedPreferencesUtil().webhookAudioBytesDelay =
                  webhookAudioBytesDelay.text;
            }
          }),
          getUserWebhookUrl(type: 'realtime_transcript').then((url) {
            if (webhookOnTranscriptReceived.text.isEmpty) {
              webhookOnTranscriptReceived.text = url;
              SharedPreferencesUtil().webhookOnTranscriptReceived = url;
            }
          }),
          getUserWebhookUrl(type: 'memory_created').then((url) {
            if (webhookOnConversationCreated.text.isEmpty) {
              webhookOnConversationCreated.text = url;
              SharedPreferencesUtil().webhookOnConversationCreated = url;
            }
          }),
          getUserWebhookUrl(type: 'day_summary').then((url) {
            if (webhookDaySummary.text.isEmpty) {
              webhookDaySummary.text = url;
              SharedPreferencesUtil().webhookDaySummary = url;
            }
          }),
        ]);
      }
    } catch (e) {
      Logger.error('Error occurred while initializing settings: $e');
    } finally {
      setIsLoading(false);
      notifyListeners();
    }
  }

  void loadCustomApiUrls() {
    final prefs = SharedPreferencesUtil();
    final savedUrls = prefs.getStringList('custom_api_urls') ?? [];
    customApiUrls = savedUrls.toSet().toList(); // Remove duplicates

    // Add current URL if it's not in the list and it's not empty
    if (currentCustomApiUrl.isNotEmpty &&
        !customApiUrls.contains(currentCustomApiUrl)) {
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
    url = normalizeUrl(url.trim());
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
      currentCustomApiUrl = normalizeUrl(url);
      await Env.setCustomApiBaseUrl(currentCustomApiUrl);
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
    if (currentCustomApiUrl.isNotEmpty) {
      return currentCustomApiUrl;
    }
    return "Omi Official Server";
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

  @override
  void dispose() {
    webhookOnConversationCreated.dispose();
    webhookOnTranscriptReceived.dispose();
    webhookAudioBytes.dispose();
    webhookAudioBytesDelay.dispose();
    webhookWsAudioBytes.dispose();
    webhookDaySummary.dispose();
    customApiUrlController.dispose();
    newServerUrlController.dispose();
    wyomingServerIpController.dispose();
    super.dispose();
  }
}
