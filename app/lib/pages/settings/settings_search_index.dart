import 'package:omi/l10n/app_localizations.dart';

/// Where a Settings row (or a search result for it) takes the reader.
///
/// `openSettingsDestination` (settings_destinations.dart) routes every value; its switch is
/// exhaustive, so adding a destination without a route does not compile.
enum SettingsDestination {
  profile,
  notifications,
  planAndUsage,
  offlineSync,
  device,
  integrations,
  permissions,
  memories,
  language,
  customVocabulary,
  voiceProfile,
  people,
  deleteAccount,
  transcription,
  conversationDisplay,
  conversationTimeout,
  homeScreen,
  phoneCalls,
  dataPrivacy,
  exportData,
  importData,
  creatorPayouts,
  developer,
  feedback,
  helpCenter,
  whatsNew,
  referral,
  signOut,
}

/// Which conditional rows are on screen right now. A search result only exists while its row does.
class SettingsSearchScope {
  const SettingsSearchScope({required this.deviceConnected, required this.supportLinks, required this.android});

  /// The Device row is shown only while a device is connected.
  final bool deviceConnected;

  /// Feedback and Help Center are shown only where Intercom is supported.
  final bool supportLinks;

  /// Background Mode is an Android-only row.
  final bool android;
}

/// One searchable Settings row.
///
/// Rule (chat-apps-settings #3): every entry is a row that really exists. [rowFile] is the source
/// file that renders the row, and it renders the title with `l10n.<key>`; [destination] opens the
/// page that holds (or is) that row. `test/unit/settings_search_index_test.dart` checks both, so an
/// entry cannot outlive its row.
class SettingsSearchEntry {
  const SettingsSearchEntry(this.key, this.title, this.destination, this.rowFile, {this.visible});

  /// The l10n key of the row's title.
  final String key;
  final String Function(AppLocalizations l10n) title;
  final SettingsDestination destination;

  /// Path of the Dart file that draws the row, relative to `app/`.
  final String rowFile;

  /// Null means always visible.
  final bool Function(SettingsSearchScope scope)? visible;
}

const _drawer = 'lib/pages/settings/settings_drawer.dart';
const _profile = 'lib/pages/settings/profile.dart';
const _notifications = 'lib/pages/settings/notifications_settings_page.dart';
const _device = 'lib/pages/settings/device_settings.dart';
const _deviceInfo = 'lib/pages/settings/device/device_info_groups.dart';
const _permissions = 'lib/pages/settings/permissions_page.dart';
const _developer = 'lib/pages/settings/developer.dart';
const _homeScreen = 'lib/pages/settings/home_screen_settings_page.dart';

bool _whenDeviceConnected(SettingsSearchScope s) => s.deviceConnected;
bool _whenSupportLinks(SettingsSearchScope s) => s.supportLinks;
bool _whenAndroid(SettingsSearchScope s) => s.android;

/// Every searchable Settings row, in the order Settings shows them.
final List<SettingsSearchEntry> settingsSearchEntries = [
  // Settings (top level)
  SettingsSearchEntry('profile', (l) => l.profile, SettingsDestination.profile, _drawer),
  SettingsSearchEntry('notifications', (l) => l.notifications, SettingsDestination.notifications, _drawer),
  SettingsSearchEntry('planAndUsage', (l) => l.planAndUsage, SettingsDestination.planAndUsage, _drawer),
  SettingsSearchEntry('deviceSettings', (l) => l.deviceSettings, SettingsDestination.device, _drawer,
      visible: _whenDeviceConnected),
  SettingsSearchEntry('transcription', (l) => l.transcription, SettingsDestination.transcription, _drawer),
  SettingsSearchEntry(
      'conversationDisplay', (l) => l.conversationDisplay, SettingsDestination.conversationDisplay, _drawer),
  SettingsSearchEntry(
      'conversationTimeout', (l) => l.conversationTimeout, SettingsDestination.conversationTimeout, _drawer),
  SettingsSearchEntry('offlineSync', (l) => l.offlineSync, SettingsDestination.offlineSync, _drawer),
  SettingsSearchEntry('phoneCalls', (l) => l.phoneCalls, SettingsDestination.phoneCalls, _drawer),
  SettingsSearchEntry('homeScreen', (l) => l.homeScreen, SettingsDestination.homeScreen, _drawer),
  SettingsSearchEntry('dataProtection', (l) => l.dataProtection, SettingsDestination.dataPrivacy, _drawer),
  SettingsSearchEntry('exportAllData', (l) => l.exportAllData, SettingsDestination.exportData, _drawer),
  SettingsSearchEntry('importData', (l) => l.importData, SettingsDestination.importData, _drawer),
  SettingsSearchEntry('integrations', (l) => l.integrations, SettingsDestination.integrations, _drawer),
  SettingsSearchEntry('permissions', (l) => l.permissions, SettingsDestination.permissions, _drawer),
  SettingsSearchEntry('feedbackBug', (l) => l.feedbackBug, SettingsDestination.feedback, _drawer,
      visible: _whenSupportLinks),
  SettingsSearchEntry('helpCenter', (l) => l.helpCenter, SettingsDestination.helpCenter, _drawer,
      visible: _whenSupportLinks),
  SettingsSearchEntry('whatsNew', (l) => l.whatsNew, SettingsDestination.whatsNew, _drawer),
  SettingsSearchEntry('referralProgram', (l) => l.referralProgram, SettingsDestination.referral, _drawer),
  SettingsSearchEntry('developerSettings', (l) => l.developerSettings, SettingsDestination.developer, _drawer),
  SettingsSearchEntry('signOut', (l) => l.signOut, SettingsDestination.signOut, _drawer),

  // Profile
  SettingsSearchEntry('name', (l) => l.name, SettingsDestination.profile, _profile),
  SettingsSearchEntry('email', (l) => l.email, SettingsDestination.profile, _profile),
  SettingsSearchEntry('language', (l) => l.language, SettingsDestination.language, _profile),
  SettingsSearchEntry('customVocabulary', (l) => l.customVocabulary, SettingsDestination.customVocabulary, _profile),
  SettingsSearchEntry('memories', (l) => l.memories, SettingsDestination.memories, _profile),
  SettingsSearchEntry('speechProfile', (l) => l.speechProfile, SettingsDestination.voiceProfile, _profile),
  SettingsSearchEntry('identifyingOthers', (l) => l.identifyingOthers, SettingsDestination.people, _profile),
  SettingsSearchEntry('voiceResponseMode', (l) => l.voiceResponseMode, SettingsDestination.profile, _profile),
  SettingsSearchEntry('backgroundModeTitle', (l) => l.backgroundModeTitle, SettingsDestination.profile, _profile,
      visible: _whenAndroid),
  SettingsSearchEntry('transcribeLaterTitle', (l) => l.transcribeLaterTitle, SettingsDestination.profile, _profile),
  SettingsSearchEntry('userId', (l) => l.userId, SettingsDestination.profile, _profile),
  SettingsSearchEntry('deleteAccountTitle', (l) => l.deleteAccountTitle, SettingsDestination.deleteAccount, _profile),

  // Notifications
  SettingsSearchEntry(
      'notificationFrequency', (l) => l.notificationFrequency, SettingsDestination.notifications, _notifications),
  SettingsSearchEntry('dailySummary', (l) => l.dailySummary, SettingsDestination.notifications, _notifications),
  SettingsSearchEntry('deliveryTime', (l) => l.deliveryTime, SettingsDestination.notifications, _notifications),

  // Device (only while connected)
  SettingsSearchEntry('firmware', (l) => l.firmware, SettingsDestination.device, _deviceInfo,
      visible: _whenDeviceConnected),
  SettingsSearchEntry('doubleTap', (l) => l.doubleTap, SettingsDestination.device, _device,
      visible: _whenDeviceConnected),
  SettingsSearchEntry('ledBrightness', (l) => l.ledBrightness, SettingsDestination.device, _device,
      visible: _whenDeviceConnected),
  SettingsSearchEntry('micGain', (l) => l.micGain, SettingsDestination.device, _device, visible: _whenDeviceConnected),
  SettingsSearchEntry('findDevice', (l) => l.findDevice, SettingsDestination.device, _device,
      visible: _whenDeviceConnected),

  // Permissions
  SettingsSearchEntry('microphone', (l) => l.microphone, SettingsDestination.permissions, _permissions),
  SettingsSearchEntry('bluetooth', (l) => l.bluetooth, SettingsDestination.permissions, _permissions),
  SettingsSearchEntry('location', (l) => l.location, SettingsDestination.permissions, _permissions),
  SettingsSearchEntry('backgroundActivity', (l) => l.backgroundActivity, SettingsDestination.permissions, _permissions),

  // Home screen
  SettingsSearchEntry('goalTracker', (l) => l.goalTracker, SettingsDestination.homeScreen, _homeScreen),
  SettingsSearchEntry('dailyScore', (l) => l.dailyScore, SettingsDestination.homeScreen, _homeScreen),
  SettingsSearchEntry(
      'showPhoneCallButtonTitle', (l) => l.showPhoneCallButtonTitle, SettingsDestination.homeScreen, _homeScreen),

  // Developer settings
  SettingsSearchEntry('creatorPayouts', (l) => l.creatorPayouts, SettingsDestination.creatorPayouts, _developer),
  SettingsSearchEntry('debugLogs', (l) => l.debugLogs, SettingsDestination.developer, _developer),
  SettingsSearchEntry('developerApi', (l) => l.developerApi, SettingsDestination.developer,
      'lib/pages/settings/widgets/developer_api_keys_section.dart'),
  SettingsSearchEntry(
      'mcp', (l) => l.mcp, SettingsDestination.developer, 'lib/pages/settings/developer_mcp_section.dart'),
  SettingsSearchEntry('webhooks', (l) => l.webhooks, SettingsDestination.developer, _developer),
  SettingsSearchEntry('conversationEvents', (l) => l.conversationEvents, SettingsDestination.developer, _developer),
  SettingsSearchEntry('realTimeTranscript', (l) => l.realTimeTranscript, SettingsDestination.developer, _developer),
  SettingsSearchEntry('audioBytes', (l) => l.audioBytes, SettingsDestination.developer, _developer),
  SettingsSearchEntry('daySummary', (l) => l.daySummary, SettingsDestination.developer, _developer),
  SettingsSearchEntry(
      'transcriptionDiagnostics', (l) => l.transcriptionDiagnostics, SettingsDestination.developer, _developer),
  SettingsSearchEntry('autoCreateSpeakers', (l) => l.autoCreateSpeakers, SettingsDestination.developer, _developer),
];

/// The entries whose rows are on screen for [scope] and whose title contains [query]
/// (case-insensitive). An empty query matches nothing.
List<SettingsSearchEntry> searchSettings(AppLocalizations l10n, String query, SettingsSearchScope scope) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return const [];
  final seen = <String>{};
  final results = <SettingsSearchEntry>[];
  for (final entry in settingsSearchEntries) {
    if (entry.visible != null && !entry.visible!(scope)) continue;
    final title = entry.title(l10n);
    if (!title.toLowerCase().contains(q)) continue;
    // Two rows with the same visible title and destination are one result.
    if (!seen.add('$title|${entry.destination.name}')) continue;
    results.add(entry);
  }
  return results;
}
