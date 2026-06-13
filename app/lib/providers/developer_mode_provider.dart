import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/agents.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/services/agent_chat_service.dart';
import 'package:omi/services/local_vision/object_announcement_service.dart';
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

  bool followUpQuestionEnabled = false;
  bool transcriptionDiagnosticEnabled = false;
  bool autoCreateSpeakersEnabled = false;
  bool showGoalTrackerEnabled = true; // Default to true
  bool showDailyScoreEnabled = true;
  bool showTasksEnabled = true;
  bool showPhoneCallButton = true;

  // VAD Gate (experimental)
  bool vadGateEnabled = false;

  // Local YOLOE object announcements (experimental)
  bool localYoloeEnabled = true;
  bool localYoloeVoiceEnabled = true;
  bool localYoloeInterruptSpeech = true;
  double localYoloeSpeechRate = 0.5;
  double localYoloeMinSecondsBetweenAnnouncements = 2.0;
  double localYoloeObjectAbsenceSeconds = 8.0;
  double localYoloeRepeatCooldownSeconds = 45.0;
  int localYoloeMaxObjectsPerAnnouncement = 3;
  double localYoloeConfidenceThreshold = 0.4;
  int localYoloeMaxObjectsPerFrame = 20;
  double localYoloeMaxFps = 0.0;
  bool localYoloeAdaptiveThrottlingEnabled = true;
  String localYoloeAnnouncementMode = 'allObjects';
  double localYoloeHandObjectIouThreshold = 0.10;
  String localYoloeDetectorImplementation = 'yoloe';

  // Claude Agent (experimental)
  bool claudeAgentEnabled = false;
  bool claudeAgentLoading = false;
  final AgentChatService agentChatService = AgentChatService();

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
    webhookOnConversationCreated.text = SharedPreferencesUtil().webhookOnConversationCreated;
    webhookOnTranscriptReceived.text = SharedPreferencesUtil().webhookOnTranscriptReceived;
    webhookAudioBytes.text = SharedPreferencesUtil().webhookAudioBytes;
    webhookAudioBytesDelay.text = SharedPreferencesUtil().webhookAudioBytesDelay;
    followUpQuestionEnabled = SharedPreferencesUtil().devModeJoanFollowUpEnabled;
    transcriptionDiagnosticEnabled = SharedPreferencesUtil().transcriptionDiagnosticEnabled;
    autoCreateSpeakersEnabled = SharedPreferencesUtil().autoCreateSpeakersEnabled;
    showGoalTrackerEnabled = SharedPreferencesUtil().showGoalTrackerEnabled;
    showDailyScoreEnabled = SharedPreferencesUtil().showDailyScoreEnabled;
    showTasksEnabled = SharedPreferencesUtil().showTasksEnabled;
    showPhoneCallButton = SharedPreferencesUtil().showPhoneCallButton;
    vadGateEnabled = SharedPreferencesUtil().vadGateEnabled;
    localYoloeEnabled = SharedPreferencesUtil().localYoloeEnabled;
    localYoloeVoiceEnabled = SharedPreferencesUtil().localYoloeVoiceEnabled;
    localYoloeInterruptSpeech = SharedPreferencesUtil().localYoloeInterruptSpeech;
    localYoloeSpeechRate = SharedPreferencesUtil().localYoloeSpeechRate;
    localYoloeMinSecondsBetweenAnnouncements = SharedPreferencesUtil().localYoloeMinSecondsBetweenAnnouncements;
    localYoloeObjectAbsenceSeconds = SharedPreferencesUtil().localYoloeObjectAbsenceSeconds;
    localYoloeRepeatCooldownSeconds = SharedPreferencesUtil().localYoloeRepeatCooldownSeconds;
    localYoloeMaxObjectsPerAnnouncement = SharedPreferencesUtil().localYoloeMaxObjectsPerAnnouncement;
    localYoloeConfidenceThreshold = SharedPreferencesUtil().localYoloeConfidenceThreshold;
    localYoloeMaxObjectsPerFrame = SharedPreferencesUtil().localYoloeMaxObjectsPerFrame;
    localYoloeMaxFps = SharedPreferencesUtil().localYoloeMaxFps;
    localYoloeAdaptiveThrottlingEnabled = SharedPreferencesUtil().localYoloeAdaptiveThrottlingEnabled;
    localYoloeAnnouncementMode = SharedPreferencesUtil().localYoloeAnnouncementMode;
    localYoloeHandObjectIouThreshold = SharedPreferencesUtil().localYoloeHandObjectIouThreshold;
    localYoloeDetectorImplementation = SharedPreferencesUtil().localYoloeDetectorImplementation;
    claudeAgentEnabled = SharedPreferencesUtil().claudeAgentEnabled;
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
    setIsLoading(false);
    notifyListeners();
  }

  void saveSettings() async {
    if (savingSettingsLoading) return;
    setIsLoading(true);
    final prefs = SharedPreferencesUtil();

    if (webhookAudioBytes.text.isNotEmpty && !isValidUrl(webhookAudioBytes.text)) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.devModeInvalidAudioBytesWebhookUrl ?? 'Invalid audio bytes webhook URL',
      );
      setIsLoading(false);
      return;
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
      return;
    }
    if (webhookOnConversationCreated.text.isNotEmpty && !isValidUrl(webhookOnConversationCreated.text)) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.devModeInvalidConversationCreatedWebhookUrl ??
            'Invalid conversation created webhook URL',
      );
      setIsLoading(false);
      return;
    }
    if (webhookDaySummary.text.isNotEmpty && !isValidUrl(webhookDaySummary.text)) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.devModeInvalidDaySummaryWebhookUrl ?? 'Invalid day summary webhook URL',
      );
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
      Future.wait([w1, w2, w3, w4]);
      prefs.webhookAudioBytes = webhookAudioBytes.text;
      prefs.webhookAudioBytesDelay = webhookAudioBytesDelay.text;
      prefs.webhookOnTranscriptReceived = webhookOnTranscriptReceived.text;
      prefs.webhookOnConversationCreated = webhookOnConversationCreated.text;
      prefs.webhookDaySummary = webhookDaySummary.text;
    } catch (e) {
      Logger.error('Error occurred while updating endpoints: $e');
    }
    // Experimental
    prefs.devModeJoanFollowUpEnabled = followUpQuestionEnabled;
    prefs.transcriptionDiagnosticEnabled = transcriptionDiagnosticEnabled;
    prefs.autoCreateSpeakersEnabled = autoCreateSpeakersEnabled;
    prefs.showGoalTrackerEnabled = showGoalTrackerEnabled;
    prefs.showDailyScoreEnabled = showDailyScoreEnabled;
    prefs.showTasksEnabled = showTasksEnabled;

    PlatformManager.instance.analytics.settingsSaved(
      hasWebhookConversationCreated: conversationEventsToggled,
      hasWebhookTranscriptReceived: transcriptsToggled,
    );
    setIsLoading(false);
    notifyListeners();
    AppSnackbar.showSnackbar(globalNavigatorKey.currentContext?.l10n.devModeSettingsSaved ?? 'Settings saved!');
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

  void onShowGoalTrackerChanged(var value) {
    showGoalTrackerEnabled = value;
    SharedPreferencesUtil().showGoalTrackerEnabled = value; // Save immediately
    notifyListeners();
  }

  void onShowDailyScoreChanged(var value) {
    showDailyScoreEnabled = value;
    SharedPreferencesUtil().showDailyScoreEnabled = value;
    notifyListeners();
  }

  void onShowTasksChanged(var value) {
    showTasksEnabled = value;
    SharedPreferencesUtil().showTasksEnabled = value;
    notifyListeners();
  }

  void onShowPhoneCallButtonChanged(var value) {
    showPhoneCallButton = value;
    SharedPreferencesUtil().showPhoneCallButton = value;
    notifyListeners();
  }

  void onVadGateChanged(bool value) {
    vadGateEnabled = value;
    SharedPreferencesUtil().vadGateEnabled = value;
    notifyListeners();
  }

  void onLocalYoloeChanged(bool value) {
    localYoloeEnabled = value;
    SharedPreferencesUtil().localYoloeEnabled = value;
    if (!value) unawaited(ObjectAnnouncementService.instance.stop());
    Logger.debug('Local YOLOE object announcements ${value ? 'enabled' : 'disabled'}');
    notifyListeners();
  }

  void onLocalYoloeVoiceChanged(bool value) {
    localYoloeVoiceEnabled = value;
    SharedPreferencesUtil().localYoloeVoiceEnabled = value;
    if (!value) unawaited(ObjectAnnouncementService.instance.stop());
    notifyListeners();
  }

  void onLocalYoloeInterruptSpeechChanged(bool value) {
    localYoloeInterruptSpeech = value;
    SharedPreferencesUtil().localYoloeInterruptSpeech = value;
    notifyListeners();
  }

  void onLocalYoloeSpeechRateChanged(double value) {
    localYoloeSpeechRate = value;
    SharedPreferencesUtil().localYoloeSpeechRate = value;
    notifyListeners();
  }

  void onLocalYoloeMinSecondsBetweenAnnouncementsChanged(double value) {
    localYoloeMinSecondsBetweenAnnouncements = value;
    SharedPreferencesUtil().localYoloeMinSecondsBetweenAnnouncements = value;
    notifyListeners();
  }

  void onLocalYoloeObjectAbsenceSecondsChanged(double value) {
    localYoloeObjectAbsenceSeconds = value;
    SharedPreferencesUtil().localYoloeObjectAbsenceSeconds = value;
    notifyListeners();
  }

  void onLocalYoloeRepeatCooldownSecondsChanged(double value) {
    localYoloeRepeatCooldownSeconds = value;
    SharedPreferencesUtil().localYoloeRepeatCooldownSeconds = value;
    notifyListeners();
  }

  void onLocalYoloeMaxObjectsPerAnnouncementChanged(double value) {
    localYoloeMaxObjectsPerAnnouncement = value.round();
    SharedPreferencesUtil().localYoloeMaxObjectsPerAnnouncement = localYoloeMaxObjectsPerAnnouncement;
    notifyListeners();
  }

  void onLocalYoloeConfidenceThresholdChanged(double value) {
    localYoloeConfidenceThreshold = value;
    SharedPreferencesUtil().localYoloeConfidenceThreshold = value;
    notifyListeners();
  }

  void onLocalYoloeMaxObjectsPerFrameChanged(double value) {
    localYoloeMaxObjectsPerFrame = value.round();
    SharedPreferencesUtil().localYoloeMaxObjectsPerFrame = localYoloeMaxObjectsPerFrame;
    notifyListeners();
  }

  void onLocalYoloeMaxFpsChanged(double value) {
    localYoloeMaxFps = value;
    SharedPreferencesUtil().localYoloeMaxFps = value;
    notifyListeners();
  }

  void onLocalYoloeAdaptiveThrottlingChanged(bool value) {
    localYoloeAdaptiveThrottlingEnabled = value;
    SharedPreferencesUtil().localYoloeAdaptiveThrottlingEnabled = value;
    notifyListeners();
  }

  void onLocalYoloeAnnouncementModeChanged(String value) {
    localYoloeAnnouncementMode = value;
    SharedPreferencesUtil().localYoloeAnnouncementMode = value;
    notifyListeners();
  }

  void onLocalYoloeHandObjectIouThresholdChanged(double value) {
    localYoloeHandObjectIouThreshold = value;
    SharedPreferencesUtil().localYoloeHandObjectIouThreshold = value;
    notifyListeners();
  }

  void onLocalYoloeDetectorImplementationChanged(String value) {
    localYoloeDetectorImplementation = value;
    SharedPreferencesUtil().localYoloeDetectorImplementation = value;
    Logger.debug('Local YOLOE detector implementation set to $value');
    notifyListeners();
  }

  Future<void> onClaudeAgentChanged(bool value) async {
    await initAgentLog();
    agentLog('onClaudeAgentChanged($value)');

    if (value) {
      claudeAgentLoading = true;
      notifyListeners();

      try {
        agentLog('Calling getAgentVmStatus()...');
        final vmInfo = await getAgentVmStatus();
        agentLog('getAgentVmStatus() returned: hasVm=${vmInfo?.hasVm}, status=${vmInfo?.status}');
        if (vmInfo == null || !vmInfo.hasVm) {
          agentLog('No VM found, aborting enable');
          AppSnackbar.showSnackbarError('Requires OMI Desktop with agent enabled');
          claudeAgentLoading = false;
          notifyListeners();
          return;
        }

        claudeAgentEnabled = true;
        SharedPreferencesUtil().claudeAgentEnabled = true;
        agentLog('Claude agent ENABLED successfully');
      } catch (e) {
        agentLog('ERROR in onClaudeAgentChanged: $e');
        Logger.error('Failed to check agent VM status: $e');
        AppSnackbar.showSnackbarError('Failed to check agent VM status');
      }

      claudeAgentLoading = false;
    } else {
      claudeAgentEnabled = false;
      SharedPreferencesUtil().claudeAgentEnabled = false;
      await agentChatService.disconnect();
      agentLog('Claude agent DISABLED');
    }

    notifyListeners();
  }
}
