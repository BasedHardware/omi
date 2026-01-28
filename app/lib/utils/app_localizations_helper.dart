import 'package:flutter/widgets.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';

/// Helper extension to get localized titles for app schema classes.
/// Falls back to the API-provided title if no localization key exists.

extension CategoryLocalization on Category {
  /// Returns the localized title for this category, with fallback to API title.
  String getLocalizedTitle(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _categoryLocalizations[id]?.call(l10n) ?? title;
  }
}

extension AppCapabilityLocalization on AppCapability {
  /// Returns the localized title for this capability, with fallback to API title.
  String getLocalizedTitle(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _capabilityLocalizations[id]?.call(l10n) ?? title;
  }
}

extension TriggerEventLocalization on TriggerEvent {
  /// Returns the localized title for this trigger event, with fallback to API title.
  String getLocalizedTitle(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _triggerLocalizations[id]?.call(l10n) ?? title;
  }
}

extension CapacityActionLocalization on CapacityAction {
  /// Returns the localized title for this action, with fallback to API title.
  String getLocalizedTitle(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _actionLocalizations[id]?.call(l10n) ?? title;
  }
}

extension NotificationScopeLocalization on NotificationScope {
  /// Returns the localized title for this scope, with fallback to API title.
  String getLocalizedTitle(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _scopeLocalizations[id]?.call(l10n) ?? title;
  }
}

// Mapping from category IDs to localization getters
final Map<String, String Function(AppLocalizations)> _categoryLocalizations = {
  'conversation-analysis': (l10n) => l10n.categoryConversationAnalysis,
  'personality-emulation': (l10n) => l10n.categoryPersonalityClone,
  'health-and-wellness': (l10n) => l10n.categoryHealth,
  'education-and-learning': (l10n) => l10n.categoryEducation,
  'communication-improvement': (l10n) => l10n.categoryCommunication,
  'emotional-and-mental-support': (l10n) => l10n.categoryEmotionalSupport,
  'productivity-and-organization': (l10n) => l10n.categoryProductivity,
  'entertainment-and-fun': (l10n) => l10n.categoryEntertainment,
  'financial': (l10n) => l10n.categoryFinancial,
  'travel-and-exploration': (l10n) => l10n.categoryTravel,
  'safety-and-security': (l10n) => l10n.categorySafety,
  'shopping-and-commerce': (l10n) => l10n.categoryShopping,
  'social-and-relationships': (l10n) => l10n.categorySocial,
  'news-and-information': (l10n) => l10n.categoryNews,
  'utilities-and-tools': (l10n) => l10n.categoryUtilities,
  'other': (l10n) => l10n.categoryOther,
  // Master categories for grouped views
  'personality-clone': (l10n) => l10n.categoryPersonalityClones,
  'productivity-lifestyle': (l10n) => l10n.categoryProductivityLifestyle,
  'social-entertainment': (l10n) => l10n.categorySocialEntertainment,
  'productivity-tools': (l10n) => l10n.categoryProductivityTools,
  'personal-wellness': (l10n) => l10n.categoryPersonalWellness,
};

// Mapping from capability IDs to localization getters
final Map<String, String Function(AppLocalizations)> _capabilityLocalizations = {
  'chat': (l10n) => l10n.capabilityChat,
  'memories': (l10n) => l10n.capabilityConversations,
  'external_integration': (l10n) => l10n.capabilityExternalIntegration,
  'proactive_notification': (l10n) => l10n.capabilityNotification,
  'popular': (l10n) => l10n.capabilityFeatured,
  'tasks': (l10n) => l10n.capabilityTasks,
  // Section title variant (API sometimes sends "integrations" as ID)
  'integrations': (l10n) => l10n.capabilityIntegrations,
};

// Mapping from trigger IDs to localization getters
final Map<String, String Function(AppLocalizations)> _triggerLocalizations = {
  'audio_bytes': (l10n) => l10n.triggerAudioBytes,
  'memory_creation': (l10n) => l10n.triggerConversationCreation,
  'transcript_processed': (l10n) => l10n.triggerTranscriptProcessed,
};

// Mapping from action IDs to localization getters
final Map<String, String Function(AppLocalizations)> _actionLocalizations = {
  'create_conversation': (l10n) => l10n.actionCreateConversations,
  'create_facts': (l10n) => l10n.actionCreateMemories,
  'read_conversations': (l10n) => l10n.actionReadConversations,
  'read_memories': (l10n) => l10n.actionReadMemories,
  'read_tasks': (l10n) => l10n.actionReadTasks,
};

// Mapping from scope IDs to localization getters
final Map<String, String Function(AppLocalizations)> _scopeLocalizations = {
  'user_name': (l10n) => l10n.scopeUserName,
  'user_facts': (l10n) => l10n.scopeUserFacts,
  'user_context': (l10n) => l10n.scopeUserConversations,
  'user_chat': (l10n) => l10n.scopeUserChat,
};
