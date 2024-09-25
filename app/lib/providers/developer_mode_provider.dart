import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class DeveloperModeProvider extends BaseProvider {
  final TextEditingController gcpCredentialsController = TextEditingController();
  final TextEditingController gcpBucketNameController = TextEditingController();
  final TextEditingController webhookOnMemoryCreated = TextEditingController();
  final TextEditingController webhookOnTranscriptReceived = TextEditingController();

  bool savingSettingsLoading = false;

  bool loadingExportMemories = false;
  bool loadingImportMemories = false;

  void initialize() {
    gcpCredentialsController.text = SharedPreferencesUtil().gcpCredentials;
    gcpBucketNameController.text = SharedPreferencesUtil().gcpBucketName;
    webhookOnMemoryCreated.text = SharedPreferencesUtil().webhookOnMemoryCreated;
    webhookOnTranscriptReceived.text = SharedPreferencesUtil().webhookOnTranscriptReceived;
  }

  void saveSettings() async {
    if (savingSettingsLoading) return;
    savingSettingsLoading = true;
    notifyListeners();
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

    // TODO: test openai + deepgram keys + bucket existence, before saving

    prefs.gcpCredentials = gcpCredentialsController.text.trim();
    prefs.gcpBucketName = gcpBucketNameController.text.trim();
    prefs.webhookOnMemoryCreated = webhookOnMemoryCreated.text.trim();
    prefs.webhookOnTranscriptReceived = webhookOnTranscriptReceived.text.trim();

    MixpanelManager().settingsSaved(
      hasGCPCredentials: prefs.gcpCredentials.isNotEmpty,
      hasGCPBucketName: prefs.gcpBucketName.isNotEmpty,
      hasWebhookMemoryCreated: prefs.webhookOnMemoryCreated.isNotEmpty,
      hasWebhookTranscriptReceived: prefs.webhookOnTranscriptReceived.isNotEmpty,
    );
    savingSettingsLoading = false;
    notifyListeners();
    AppSnackbar.showSnackbarError(
      'Settings saved!',
    );
  }
}
