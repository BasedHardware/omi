import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/http/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/utils/other/validators.dart';

class DeveloperModeProvider extends BaseProvider {
  final TextEditingController gcpCredentialsController = TextEditingController();
  final TextEditingController gcpBucketNameController = TextEditingController();
  final TextEditingController webhookOnMemoryCreated = TextEditingController();
  final TextEditingController webhookOnTranscriptReceived = TextEditingController();
  final TextEditingController webhookAudioBytes = TextEditingController();
  final TextEditingController webhookAudioBytesDelay = TextEditingController();
  final TextEditingController webhookWsAudioBytes = TextEditingController();
  final TextEditingController webhookDaySummary = TextEditingController();

  bool memoryEventsToggled = false;
  bool transcriptsToggled = false;
  bool audioBytesToggled = false;
  bool daySummaryToggled = false;

  bool savingSettingsLoading = false;

  bool loadingExportMemories = false;
  bool loadingImportMemories = false;

  bool localSyncEnabled = false;
  bool followUpQuestionEnabled = false;

  void onMemoryEventsToggled(bool value) {
    memoryEventsToggled = value;
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
      memoryEventsToggled = false;
      transcriptsToggled = false;
      audioBytesToggled = false;
      daySummaryToggled = false;
    } else {
      memoryEventsToggled = res['memory_created'];
      transcriptsToggled = res['realtime_transcript'];
      audioBytesToggled = res['audio_bytes'];
      daySummaryToggled = res['day_summary'];
    }
    SharedPreferencesUtil().memoryEventsToggled = memoryEventsToggled;
    SharedPreferencesUtil().transcriptsToggled = transcriptsToggled;
    SharedPreferencesUtil().audioBytesToggled = audioBytesToggled;
    SharedPreferencesUtil().daySummaryToggled = daySummaryToggled;
    notifyListeners();
  }

  Future initialize() async {
    setIsLoading(true);
    gcpCredentialsController.text = SharedPreferencesUtil().gcpCredentials;
    gcpBucketNameController.text = SharedPreferencesUtil().gcpBucketName;
    localSyncEnabled = SharedPreferencesUtil().localSyncEnabled;
    webhookOnMemoryCreated.text = SharedPreferencesUtil().webhookOnMemoryCreated;
    webhookOnTranscriptReceived.text = SharedPreferencesUtil().webhookOnTranscriptReceived;
    webhookAudioBytes.text = SharedPreferencesUtil().webhookAudioBytes;
    webhookAudioBytesDelay.text = SharedPreferencesUtil().webhookAudioBytesDelay;
    followUpQuestionEnabled = SharedPreferencesUtil().devModeJoanFollowUpEnabled;
    memoryEventsToggled = SharedPreferencesUtil().memoryEventsToggled;
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
        webhookOnMemoryCreated.text = url;
        SharedPreferencesUtil().webhookOnMemoryCreated = url;
      }),
      getUserWebhookUrl(type: 'day_summary').then((url) {
        webhookDaySummary.text = url;
        SharedPreferencesUtil().webhookDaySummary = url;
      }),
    ]);
    // getUserWebhookUrl(type: 'audio_bytes_websocket').then((url) => webhookWsAudioBytes.text = url);
    setIsLoading(false);
    notifyListeners();
  }

  void saveSettings() async {
    if (savingSettingsLoading) return;
    setIsLoading(true);
    final prefs = SharedPreferencesUtil();

    if (gcpCredentialsController.text.isNotEmpty && gcpBucketNameController.text.isNotEmpty) {
      try {
        await authenticateGCP(base64: gcpCredentialsController.text.trim());
      } catch (e) {
        AppSnackbar.showSnackbarError(
          'Invalid GCP credentials or bucket name. Please check and try again.',
        );

        savingSettingsLoading = false;
        notifyListeners();

        return;
      }
    }

    prefs.gcpCredentials = gcpCredentialsController.text.trim();
    prefs.gcpBucketName = gcpBucketNameController.text.trim();

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
    if (webhookOnMemoryCreated.text.isNotEmpty && !isValidUrl(webhookOnMemoryCreated.text)) {
      AppSnackbar.showSnackbarError('Invalid memory created webhook URL');
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
    var w3 = setUserWebhookUrl(type: 'memory_created', url: webhookOnMemoryCreated.text.trim());
    var w4 = setUserWebhookUrl(type: 'day_summary', url: webhookDaySummary.text.trim());
    // var w4 = setUserWebhookUrl(type: 'audio_bytes_websocket', url: webhookWsAudioBytes.text.trim());
    try {
      Future.wait([w1, w2, w3, w4]);
      prefs.webhookAudioBytes = webhookAudioBytes.text;
      prefs.webhookAudioBytesDelay = webhookAudioBytesDelay.text;
      prefs.webhookOnTranscriptReceived = webhookOnTranscriptReceived.text;
      prefs.webhookOnMemoryCreated = webhookOnMemoryCreated.text;
      prefs.webhookDaySummary = webhookDaySummary.text;
    } catch (e) {
      Logger.error('Error occurred while updating endpoints: $e');
    }
    // Experimental
    prefs.localSyncEnabled = localSyncEnabled;
    prefs.devModeJoanFollowUpEnabled = followUpQuestionEnabled;

    MixpanelManager().settingsSaved(
      hasGCPCredentials: prefs.gcpCredentials.isNotEmpty,
      hasGCPBucketName: prefs.gcpBucketName.isNotEmpty,
    );
    setIsLoading(false);
    notifyListeners();
    AppSnackbar.showSnackbar('Settings saved!');
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
}
