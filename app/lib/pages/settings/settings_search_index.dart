import 'package:omi/l10n/app_localizations.dart';

/// Where a Settings row (or a search result for it) takes the reader.
///
/// `openSettingsDestination` (settings_destinations.dart) routes every value; its switch is
/// exhaustive, so adding a destination without a route does not compile.
enum SettingsDestination {
  /// The Account page (`ProfilePage`, titled Account).
  profile,
  // The group pages the Settings sheet opens (settings_groups.dart).
  deviceGroup,
  recordingGroup,
  notificationsGroup,
  privacyGroup,
  helpGroup,
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
  const SettingsSearchEntry(this.key, this.title, this.destination, this.rowFile, {this.visible, this.aliases});

  /// The l10n key of the row's title.
  final String key;
  final String Function(AppLocalizations l10n) title;
  final SettingsDestination destination;

  /// Path of the Dart file that draws the row, relative to `app/`.
  final String rowFile;

  /// Null means always visible.
  final bool Function(SettingsSearchScope scope)? visible;

  /// Other words people search for this row by (for example the name a row had before a rename).
  /// A query that matches an alias finds the row; the result still shows [title].
  final List<String> Function(AppLocalizations l10n)? aliases;
}

const _drawer = 'lib/pages/settings/settings_drawer.dart';
const _account = 'lib/pages/settings/profile.dart';
const _groups = 'lib/pages/settings/settings_groups.dart';
const _notifications = 'lib/pages/settings/notifications_settings_page.dart';
const _device = 'lib/pages/settings/device_settings.dart';
const _deviceInfo = 'lib/pages/settings/device/device_info_groups.dart';
const _permissions = 'lib/pages/settings/permissions_page.dart';
const _developer = 'lib/pages/settings/developer.dart';
const _homeScreen = 'lib/pages/settings/home_screen_settings_page.dart';

bool _whenDeviceConnected(SettingsSearchScope s) => s.deviceConnected;
bool _whenSupportLinks(SettingsSearchScope s) => s.supportLinks;
bool _whenAndroid(SettingsSearchScope s) => s.android;

/// Every searchable Settings row, in the order Settings shows them: the sheet's rows, each group
/// page's rows followed by the group's own title (so a search for "Transcription" lists the
/// Transcription row before the group that holds it), then the rows inside other pages.
final List<SettingsSearchEntry> settingsSearchEntries = [
  // Account (the sheet's first row, then the Account page)
  // The Account row was called Profile until 2026-09; people still search for it by that name.
  SettingsSearchEntry('account', (l) => l.account, SettingsDestination.profile, _drawer, aliases: (l) => [l.profile]),
  SettingsSearchEntry('name', (l) => l.name, SettingsDestination.profile, _account),
  SettingsSearchEntry('email', (l) => l.email, SettingsDestination.profile, _account),
  SettingsSearchEntry('userId', (l) => l.userId, SettingsDestination.profile, _account),
  SettingsSearchEntry('signOut', (l) => l.signOut, SettingsDestination.signOut, _account),
  SettingsSearchEntry('deleteAccountTitle', (l) => l.deleteAccountTitle, SettingsDestination.deleteAccount, _account),

  // Plan, referrals (on the sheet)
  SettingsSearchEntry('planAndUsage', (l) => l.planAndUsage, SettingsDestination.planAndUsage, _drawer),
  SettingsSearchEntry('referralProgram', (l) => l.referralProgram, SettingsDestination.referral, _drawer),

  // Device group
  SettingsSearchEntry('deviceSettings', (l) => l.deviceSettings, SettingsDestination.device, _groups,
      visible: _whenDeviceConnected),
  SettingsSearchEntry('offlineSync', (l) => l.offlineSync, SettingsDestination.offlineSync, _groups),
  SettingsSearchEntry('phoneCalls', (l) => l.phoneCalls, SettingsDestination.phoneCalls, _groups),
  SettingsSearchEntry('permissions', (l) => l.permissions, SettingsDestination.permissions, _groups),
  SettingsSearchEntry('device', (l) => l.device, SettingsDestination.deviceGroup, _drawer),

  // Recording & Transcription group
  SettingsSearchEntry('transcription', (l) => l.transcription, SettingsDestination.transcription, _groups),
  SettingsSearchEntry('language', (l) => l.language, SettingsDestination.language, _groups),
  SettingsSearchEntry('customVocabulary', (l) => l.customVocabulary, SettingsDestination.customVocabulary, _groups),
  SettingsSearchEntry('speechProfile', (l) => l.speechProfile, SettingsDestination.voiceProfile, _groups),
  SettingsSearchEntry('identifyingOthers', (l) => l.identifyingOthers, SettingsDestination.people, _groups),
  SettingsSearchEntry('voiceResponseMode', (l) => l.voiceResponseMode, SettingsDestination.recordingGroup, _groups),
  SettingsSearchEntry(
      'conversationTimeout', (l) => l.conversationTimeout, SettingsDestination.conversationTimeout, _groups),
  SettingsSearchEntry(
      'transcribeLaterTitle', (l) => l.transcribeLaterTitle, SettingsDestination.recordingGroup, _groups),
  SettingsSearchEntry('backgroundModeTitle', (l) => l.backgroundModeTitle, SettingsDestination.recordingGroup, _groups,
      visible: _whenAndroid),
  SettingsSearchEntry(
      'recordingAndTranscription', (l) => l.recordingAndTranscription, SettingsDestination.recordingGroup, _drawer),

  // Notifications & Display group
  SettingsSearchEntry('notifications', (l) => l.notifications, SettingsDestination.notifications, _groups),
  SettingsSearchEntry('homeScreen', (l) => l.homeScreen, SettingsDestination.homeScreen, _groups),
  SettingsSearchEntry(
      'conversationDisplay', (l) => l.conversationDisplay, SettingsDestination.conversationDisplay, _groups),
  SettingsSearchEntry(
      'notificationsAndDisplay', (l) => l.notificationsAndDisplay, SettingsDestination.notificationsGroup, _drawer),

  // Integrations (opens the Integrations page directly)
  SettingsSearchEntry('integrations', (l) => l.integrations, SettingsDestination.integrations, _drawer),

  // Data & Privacy group
  SettingsSearchEntry('dataProtection', (l) => l.dataProtection, SettingsDestination.dataPrivacy, _groups),
  SettingsSearchEntry('memories', (l) => l.memories, SettingsDestination.memories, _groups),
  SettingsSearchEntry('exportAllData', (l) => l.exportAllData, SettingsDestination.exportData, _groups),
  SettingsSearchEntry('importData', (l) => l.importData, SettingsDestination.importData, _groups),
  SettingsSearchEntry('dataAndPrivacy', (l) => l.dataAndPrivacy, SettingsDestination.privacyGroup, _drawer),

  // Help & About group
  SettingsSearchEntry('helpCenter', (l) => l.helpCenter, SettingsDestination.helpCenter, _groups,
      visible: _whenSupportLinks),
  SettingsSearchEntry('whatsNew', (l) => l.whatsNew, SettingsDestination.whatsNew, _groups),
  SettingsSearchEntry('helpAndAbout', (l) => l.helpAndAbout, SettingsDestination.helpGroup, _drawer),

  // Feedback (on the sheet, where Intercom is supported)
  SettingsSearchEntry('feedbackBug', (l) => l.feedbackBug, SettingsDestination.feedback, _drawer,
      visible: _whenSupportLinks),

  // Developer Settings (opens the page directly)
  SettingsSearchEntry('developerSettings', (l) => l.developerSettings, SettingsDestination.developer, _drawer),

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
    final aliases = entry.aliases?.call(l10n) ?? const <String>[];
    if (!title.toLowerCase().contains(q) && !aliases.any((a) => a.toLowerCase().contains(q))) continue;
    // Two rows with the same visible title and destination are one result.
    if (!seen.add('$title|${entry.destination.name}')) continue;
    results.add(entry);
  }
  return results;
}
