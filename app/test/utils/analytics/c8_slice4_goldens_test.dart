import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter, emissionPayloads;

/// Adapter payloads captured from leftover nothing-block public methods at
/// `bb5d5fe56715b5b60c18c6fa91e60f3ab3be1bcd`, the C8 slice 3 tip, before those methods called [TypedEvents.emit].
const c8Slice4PreMigrationSha = 'bb5d5fe56715b5b60c18c6fa91e60f3ab3be1bcd';

void fireC8Slice4(AnalyticsManager analytics) {
  analytics.memoriesPageEditedMemory();
  analytics.memoriesPageCreateMemoryBtn();
  analytics.memoriesManagementSheetOpened();
  analytics.conversationMergeSelectionModeEntered();
  analytics.conversationMergeSelectionModeExited();
  analytics.addManualConversationClicked();
  analytics.userIDCopied();
  analytics.exportMemories();
  analytics.importMemories();
  analytics.importedMemories();
  analytics.supportContacted();
  analytics.upgradeSucceeded(previousPlan: 'free', newPlan: 'plus', billingInterval: 'monthly');
  analytics.upgradeCancelled();
  analytics.upgradeModalDismissed();
  analytics.upgradeModalClicked();
  analytics.subscriptionCancelFlowStarted();
  analytics.connectFriendClicked();
  analytics.disconnectFriendClicked();
  analytics.batteryIndicatorClicked();
  analytics.addedPerson();
  analytics.removedPerson();
  analytics.tagSheetOpened();
  analytics.untaggedSegment();
  analytics.editSegmentTextStarted();
  analytics.editSegmentTextSaved();
  analytics.editSegmentTextCancelled();
  analytics.editSummaryStarted();
  analytics.editSummarySaved();
  analytics.editSummaryCancelled();
  analytics.deleteAccountClicked();
  analytics.deleteAccountConfirmed();
  analytics.deleteAccountCancelled();
  analytics.deleteAccountFlowStarted();
  analytics.appsFilterOpened();
  analytics.appsFilterApplied();
  analytics.appsClearFilters();
  analytics.brainMapOpened();
  analytics.brainMapShareClicked();
  analytics.actionItemsPageOpened();
  analytics.actionItemsDateFilterCleared();
  analytics.trainingDataOptInSubmitted();
  analytics.trainingDataOptInApproved();
  analytics.calendarFilterCleared();
  analytics.searchBarFocused();
  analytics.searchQueryCleared();
  analytics.exportTasksBannerClicked();
  analytics.createFolderButtonClicked();
  analytics.liveTranscriptCardClicked(hasSegments: false, hasPhotos: false, segmentCount: 0, photoCount: 0);
  analytics.liveTranscriptCardClicked(hasSegments: true, hasPhotos: false, segmentCount: 1, photoCount: 0);
  analytics.liveTranscriptCardClicked(hasSegments: false, hasPhotos: true, segmentCount: 0, photoCount: 1);
  analytics.liveTranscriptCardClicked(hasSegments: true, hasPhotos: true, segmentCount: 3, photoCount: 2);
  analytics.appleRemindersSyncCompleted(
      pendingExported: 0,
      syncedChecked: 0,
      completionsPulled: 0,
      completionsPushed: 0,
      titleDuePulled: 0,
      titleDuePushed: 0,
      remindersUnlinked: 0);
  analytics.appleRemindersSyncCompleted(
      pendingExported: 1,
      syncedChecked: 2,
      completionsPulled: 3,
      completionsPushed: 4,
      titleDuePulled: 5,
      titleDuePushed: 6,
      remindersUnlinked: 7);
  analytics.wrappedPageOpened();
  analytics.wrappedBannerClicked();
  analytics.wrappedGenerationCompleted(totalConversations: 0, totalMinutes: 0, daysActive: 0);
  analytics.wrappedGenerationCompleted(totalConversations: 12, totalMinutes: 345, daysActive: 30);
  analytics.wrappedGenerationStarted();
  analytics.dailySummarySettingsOpened();
  analytics.permissionsSettingsOpened();
  analytics.permissionsInterstitialShown();
  analytics.permissionsInterstitialCompleted();
  analytics.permissionsInterstitialSkipped();
  analytics.recapTabOpened();
  analytics.whatsNewOpened();
  analytics.dailyScoreHelpTapped();
  analytics.integrationsPageOpened();
  analytics.paymentsPageOpened();
  analytics.connectDevicePageOpened();
  analytics.getOmiDeviceClicked();
  analytics.connectionGuideOpened();
  analytics.dataPrivacyPageOpened();
  analytics.aiAppGeneratorPageOpened();
  analytics.importHistoryPageOpened();
}

List<List<Object>> c8Slice4Goldens(Map<String, Object> globals) => [
      [
        'Fact Page Edited Fact',
        {...globals}
      ],
      [
        'Fact Page Create Fact Button Pressed',
        {...globals}
      ],
      [
        'Facts Management Sheet Opened',
        {...globals}
      ],
      [
        'Conversation Merge Selection Mode Entered',
        {...globals}
      ],
      [
        'Conversation Merge Selection Mode Exited',
        {...globals}
      ],
      [
        'Add Manual Memory Clicked',
        {...globals}
      ],
      [
        'User ID Copied',
        {...globals}
      ],
      [
        'Dev Mode Export Memories',
        {...globals}
      ],
      [
        'Dev Mode Import Memories',
        {...globals}
      ],
      [
        'Dev Mode Imported Memories',
        {...globals}
      ],
      [
        'Support Contacted',
        {...globals}
      ],
      [
        'Subscription Plan Changed',
        {
          ...globals,
          'previous_plan': 'free',
          'new_plan': 'plus',
          'billing_interval': 'monthly',
          'change_source': 'mobile_checkout'
        }
      ],
      [
        'Upgrade Succeeded',
        {...globals}
      ],
      [
        'Upgrade Cancelled',
        {...globals}
      ],
      [
        'Upgrade Modal Dismissed',
        {...globals}
      ],
      [
        'Upgrade Modal Clicked',
        {...globals}
      ],
      [
        'Subscription Cancel Flow Started',
        {...globals}
      ],
      [
        'Connect Friend Clicked',
        {...globals}
      ],
      [
        'Disconnect Friend Clicked',
        {...globals}
      ],
      [
        'Battery Indicator Clicked',
        {...globals}
      ],
      [
        'Added Person',
        {...globals}
      ],
      [
        'Removed Person',
        {...globals}
      ],
      [
        'Tag Sheet Opened',
        {...globals}
      ],
      [
        'Untagged Segment',
        {...globals}
      ],
      [
        'Edit Segment Text Started',
        {...globals}
      ],
      [
        'Edit Segment Text Saved',
        {...globals}
      ],
      [
        'Edit Segment Text Cancelled',
        {...globals}
      ],
      [
        'Edit Summary Started',
        {...globals}
      ],
      [
        'Edit Summary Saved',
        {...globals}
      ],
      [
        'Edit Summary Cancelled',
        {...globals}
      ],
      [
        'Delete Account Clicked',
        {...globals}
      ],
      [
        'Delete Account Confirmed',
        {...globals}
      ],
      [
        'Delete Account Cancelled',
        {...globals}
      ],
      [
        'Delete Account Flow Started',
        {...globals}
      ],
      [
        'Apps Filter Opened',
        {...globals}
      ],
      [
        'Apps Filter Applied',
        {...globals}
      ],
      [
        'Apps Clear Filters',
        {...globals}
      ],
      [
        'Brain Map Opened',
        {...globals}
      ],
      [
        'Brain Map Share Clicked',
        {...globals}
      ],
      [
        'Action Items Page Opened',
        {...globals}
      ],
      [
        'Action Items Date Filter Cleared',
        {...globals}
      ],
      [
        'Training Data Opt-In Submitted',
        {...globals}
      ],
      [
        'Training Data Opt-In Approved',
        {...globals}
      ],
      [
        'Calendar Filter Cleared',
        {...globals}
      ],
      [
        'Search Bar Focused',
        {...globals}
      ],
      [
        'Search Query Cleared',
        {...globals}
      ],
      [
        'Export Tasks Banner Clicked',
        {...globals}
      ],
      [
        'Create Folder Button Clicked',
        {...globals}
      ],
      [
        'Live Transcript Card Clicked',
        {...globals, 'has_segments': false, 'has_photos': false, 'segment_count': 0, 'photo_count': 0}
      ],
      [
        'Live Transcript Card Clicked',
        {...globals, 'has_segments': true, 'has_photos': false, 'segment_count': 1, 'photo_count': 0}
      ],
      [
        'Live Transcript Card Clicked',
        {...globals, 'has_segments': false, 'has_photos': true, 'segment_count': 0, 'photo_count': 1}
      ],
      [
        'Live Transcript Card Clicked',
        {...globals, 'has_segments': true, 'has_photos': true, 'segment_count': 3, 'photo_count': 2}
      ],
      [
        'Apple Reminders Sync Completed',
        {
          ...globals,
          'pending_exported': 0,
          'synced_checked': 0,
          'completions_pulled': 0,
          'completions_pushed': 0,
          'title_due_pulled': 0,
          'title_due_pushed': 0,
          'reminders_unlinked': 0
        }
      ],
      [
        'Apple Reminders Sync Completed',
        {
          ...globals,
          'pending_exported': 1,
          'synced_checked': 2,
          'completions_pulled': 3,
          'completions_pushed': 4,
          'title_due_pulled': 5,
          'title_due_pushed': 6,
          'reminders_unlinked': 7
        }
      ],
      [
        'Wrapped Page Opened',
        {...globals}
      ],
      [
        'Wrapped Banner Clicked',
        {...globals}
      ],
      [
        'Wrapped Generation Completed',
        {...globals, 'total_conversations': 0, 'total_minutes': 0, 'days_active': 0}
      ],
      [
        'Wrapped Generation Completed',
        {...globals, 'total_conversations': 12, 'total_minutes': 345, 'days_active': 30}
      ],
      [
        'Wrapped Generation Started',
        {...globals}
      ],
      [
        'Daily Summary Settings Opened',
        {...globals}
      ],
      [
        'Permissions Settings Opened',
        {...globals}
      ],
      [
        'Permissions Interstitial Shown',
        {...globals}
      ],
      [
        'Permissions Interstitial Completed',
        {...globals}
      ],
      [
        'Permissions Interstitial Skipped',
        {...globals}
      ],
      [
        'Recap Tab Opened',
        {...globals}
      ],
      [
        'Whats New Opened',
        {...globals}
      ],
      [
        'Daily Score Help Tapped',
        {...globals}
      ],
      [
        'Integrations Page Opened',
        {...globals}
      ],
      [
        'Payments Page Opened',
        {...globals}
      ],
      [
        'Connect Device Page Opened',
        {...globals}
      ],
      [
        'Get Omi Device Clicked',
        {...globals}
      ],
      [
        'Connection Guide Opened',
        {...globals}
      ],
      [
        'Data Privacy Page Opened',
        {...globals}
      ],
      [
        'AI App Generator Page Opened',
        {...globals}
      ],
      [
        'Import History Page Opened',
        {...globals}
      ],
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.543', buildNumber: '992', buildSignature: '');
    await SharedPreferencesUtil.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  test('C8 slice 4 public methods match goldens pinned at $c8Slice4PreMigrationSha', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    fireC8Slice4(AnalyticsManager());
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    final globals = <String, Object>{
      'app_platform': PlatformService.isIOS ? 'ios' : (PlatformService.isAndroid ? 'android' : 'unknown'),
      'app_version': '1.0.543',
      'app_build': '992',
    };
    expect(emissionPayloads(adapter.events), c8Slice4Goldens(globals));
    expect(adapter.events.every((event) => !event.$2.containsKey('correlation_id')), isTrue);
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });
}
