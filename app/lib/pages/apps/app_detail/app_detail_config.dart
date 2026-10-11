import 'package:omi/backend/schema/app.dart';

/// Returns true when [updated] differs from [current] in name, description, or
/// user-visible/editable external integration URL fields shown on the app detail page.
bool hasAppDetailConfigChanged(App current, App updated) {
  if (current.name != updated.name) return true;
  if (current.description != updated.description) return true;
  return hasExternalIntegrationChanged(current.externalIntegration, updated.externalIntegration);
}

/// Returns true when user-visible/editable external integration URL fields differ.
///
/// Compares only fields relevant to app-detail refresh for integration URL updates
/// (#3309): appHomeUrl, setupCompletedUrl, webhookUrl, setupInstructionsFilePath,
/// and auth step names/urls. Hidden fields (triggersOn, actions, chatToolsManifestUrl,
/// mcpServerUrl, isInstructionsUrl) are intentionally ignored.
bool hasExternalIntegrationChanged(ExternalIntegration? current, ExternalIntegration? updated) {
  if (identical(current, updated)) return false;
  if (current == null || updated == null) return current != updated;

  if (current.appHomeUrl != updated.appHomeUrl) return true;
  if (current.setupCompletedUrl != updated.setupCompletedUrl) return true;
  if (current.webhookUrl != updated.webhookUrl) return true;
  if (current.setupInstructionsFilePath != updated.setupInstructionsFilePath) {
    return true;
  }

  if (current.authSteps.length != updated.authSteps.length) return true;
  for (var i = 0; i < current.authSteps.length; i++) {
    if (current.authSteps[i].name != updated.authSteps[i].name) return true;
    if (current.authSteps[i].url != updated.authSteps[i].url) return true;
  }
  return false;
}
