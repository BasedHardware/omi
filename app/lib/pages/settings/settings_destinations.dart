import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/announcements.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/announcements/changelog_sheet.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/referral/referral_page.dart';
import 'package:omi/pages/settings/conversation_display_settings.dart';
import 'package:omi/pages/settings/conversation_timeout_dialog.dart';
import 'package:omi/pages/settings/custom_vocabulary_page.dart';
import 'package:omi/pages/settings/data_export.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/delete_account.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/pages/settings/home_screen_settings_page.dart';
import 'package:omi/pages/settings/import_history_page.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/pages/settings/language_settings_page.dart';
import 'package:omi/pages/settings/notifications_settings_page.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/settings/permissions_page.dart';
import 'package:omi/pages/settings/phone_call_settings_page.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/pages/settings/sign_out.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/pages/speech_profile/page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Opens [destination] from Settings (a row or a search result).
///
/// Pages are pushed with the platform route (iOS back swipe intact); actions (export, timeout
/// picker, sign out, What's New) run in place. The switch is exhaustive: every
/// [SettingsDestination] has exactly one way to open it.
Future<void> openSettingsDestination(BuildContext context, SettingsDestination destination) async {
  switch (destination) {
    case SettingsDestination.profile:
      await routeToPage(context, const ProfilePage());
    case SettingsDestination.notifications:
      await routeToPage(context, const NotificationsSettingsPage());
    case SettingsDestination.planAndUsage:
      await routeToPage(context, const UsagePage());
    case SettingsDestination.offlineSync:
      final page = SharedPreferencesUtil().deviceSupportsMultiFileSync ? const AutoSyncPage() : const SyncPage();
      await routeToPage(context, page);
    case SettingsDestination.device:
      await routeToPage(context, const DeviceSettings());
    case SettingsDestination.integrations:
      await routeToPage(context, const IntegrationsPage());
    case SettingsDestination.permissions:
      PlatformManager.instance.analytics.permissionsSettingsOpened();
      await routeToPage(context, const PermissionsPage());
    case SettingsDestination.memories:
      await routeToPage(context, const MemoriesPage());
    case SettingsDestination.language:
      await routeToPage(context, const LanguageSettingsPage());
    case SettingsDestination.customVocabulary:
      await routeToPage(context, const CustomVocabularyPage());
    case SettingsDestination.voiceProfile:
      await openVoiceProfile(context);
    case SettingsDestination.people:
      await routeToPage(context, const UserPeoplePage());
    case SettingsDestination.deleteAccount:
      PlatformManager.instance.analytics.pageOpened('Profile Delete Account Dialog');
      await routeToPage(context, const DeleteAccount());
    case SettingsDestination.transcription:
      await routeToPage(context, const TranscriptionSettingsPage());
    case SettingsDestination.conversationDisplay:
      await routeToPage(context, const ConversationDisplaySettings());
    case SettingsDestination.conversationTimeout:
      await ConversationTimeoutDialog.show(context);
    case SettingsDestination.homeScreen:
      await routeToPage(context, const HomeScreenSettingsPage());
    case SettingsDestination.phoneCalls:
      await routeToPage(context, const PhoneCallSettingsPage());
    case SettingsDestination.dataPrivacy:
      await routeToPage(context, const DataPrivacyPage());
    case SettingsDestination.exportData:
      await DataExport.run(context);
    case SettingsDestination.importData:
      await routeToPage(context, const ImportHistoryPage());
    case SettingsDestination.creatorPayouts:
      await routeToPage(context, const PaymentsPage());
    case SettingsDestination.developer:
      await routeToPage(context, const DeveloperSettingsPage());
    case SettingsDestination.feedback:
      final url = Uri.parse('https://feedback.omi.me/');
      if (await canLaunchUrl(url)) await launchUrl(url, mode: LaunchMode.inAppBrowserView);
    case SettingsDestination.helpCenter:
      await _openHelpCenter(context);
    case SettingsDestination.whatsNew:
      PlatformManager.instance.analytics.whatsNewOpened();
      await ChangelogSheet.showWithLoading(context, () => getAppChangelogs(limit: 5));
    case SettingsDestination.referral:
      await routeToPage(context, const ReferralPage());
    case SettingsDestination.signOut:
      await confirmAndSignOut(context);
  }
}

/// The one Voice Profile entry point (chat-apps-settings #25): the guided voice setup when there is
/// no voice profile yet, otherwise the Voice Profile page (listen, re-record).
Future<void> openVoiceProfile(BuildContext context) async {
  PlatformManager.instance.analytics.pageOpened('Profile Speech Profile');
  if (SharedPreferencesUtil().hasSpeakerProfile) {
    await routeToPage(context, const SpeechProfilePage());
    return;
  }
  await routeToPage(
    context,
    Builder(
      builder: (routeContext) => Scaffold(
        appBar: AppBar(leading: const OmiBackButton()),
        body: SpeechProfileWidget(
          flowSource: 'settings',
          goNext: () => Navigator.of(routeContext).pop(),
          onSkip: () => Navigator.of(routeContext).pop(),
        ),
      ),
    ),
  );
}

Future<void> _openHelpCenter(BuildContext context) async {
  final url = Uri.parse('https://help.omi.me/en/');
  if (!await canLaunchUrl(url)) return;
  try {
    await launchUrl(url, mode: LaunchMode.inAppBrowserView);
  } catch (_) {
    await launchUrl(url, mode: LaunchMode.externalApplication);
  }
}
