// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Conversation';

  @override
  String get transcriptTab => 'Transcript';

  @override
  String get actionItemsTab => 'Action Items';

  @override
  String get deleteConversationTitle => 'Delete Conversation?';

  @override
  String get deleteConversationMessage =>
      'Are you sure you want to delete this conversation? This action cannot be undone.';

  @override
  String get confirm => 'Confirm';

  @override
  String get cancel => 'Cancel';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Delete';

  @override
  String get add => 'Add';

  @override
  String get update => 'Update';

  @override
  String get save => 'Save';

  @override
  String get edit => 'Edit';

  @override
  String get close => 'Close';

  @override
  String get copyTranscript => 'Copy Transcript';

  @override
  String get copySummary => 'Copy Summary';

  @override
  String get testPrompt => 'Test Prompt';

  @override
  String get reprocessConversation => 'Reprocess Conversation';

  @override
  String get deleteConversation => 'Delete Conversation';

  @override
  String get contentCopied => 'Content copied to clipboard';

  @override
  String get failedToUpdateStarred => 'Failed to update starred status.';

  @override
  String get conversationUrlNotShared => 'Conversation URL could not be shared.';

  @override
  String get errorProcessingConversation => 'Error while processing conversation. Please try again later.';

  @override
  String get noInternetConnection => 'Please check your internet connection and try again.';

  @override
  String get unableToDeleteConversation => 'Unable to Delete Conversation';

  @override
  String get somethingWentWrong => 'Something went wrong! Please try again later.';

  @override
  String get copyErrorMessage => 'Copy error message';

  @override
  String get errorCopied => 'Error message copied to clipboard';

  @override
  String get remaining => 'Remaining';

  @override
  String get loading => 'Loading...';

  @override
  String get loadingDuration => 'Loading duration...';

  @override
  String secondsCount(int count) {
    return '$count seconds';
  }

  @override
  String get people => 'People';

  @override
  String get addNewPerson => 'Add New Person';

  @override
  String get editPerson => 'Edit Person';

  @override
  String get createPersonHint => 'Create a new person and train Omi to recognize their speech too!';

  @override
  String get speechProfile => 'Speech Profile';

  @override
  String sampleNumber(int number) {
    return 'Sample $number';
  }

  @override
  String get settings => 'Settings';

  @override
  String get language => 'Language';

  @override
  String get selectLanguage => 'Select Language';

  @override
  String get deleting => 'Deleting...';

  @override
  String get pleaseCompleteAuthentication =>
      'Please complete authentication in your browser. Once done, return to the app.';

  @override
  String get failedToStartAuthentication => 'Failed to start authentication';

  @override
  String get importStarted => 'Import started! You\'ll be notified when it\'s complete.';

  @override
  String get failedToStartImport => 'Failed to start import. Please try again.';

  @override
  String get couldNotAccessFile => 'Could not access the selected file';

  @override
  String get askOmi => 'Ask Omi';

  @override
  String get done => 'Done';

  @override
  String get disconnected => 'Disconnected';

  @override
  String get searching => 'Searching';

  @override
  String get connectDevice => 'Connect Device';

  @override
  String get monthlyLimitReached => 'You\'ve reached your monthly limit.';

  @override
  String get checkUsage => 'Check Usage';

  @override
  String get syncingRecordings => 'Syncing recordings';

  @override
  String get recordingsToSync => 'Recordings to sync';

  @override
  String get allCaughtUp => 'All caught up';

  @override
  String get sync => 'Sync';

  @override
  String get pendantUpToDate => 'Pendant is up to date';

  @override
  String get allRecordingsSynced => 'All recordings are synced';

  @override
  String get syncingInProgress => 'Syncing in progress';

  @override
  String get readyToSync => 'Ready to sync';

  @override
  String get tapSyncToStart => 'Tap Sync to start';

  @override
  String get pendantNotConnected => 'Pendant not connected. Connect to sync.';

  @override
  String get everythingSynced => 'Everything is already synced.';

  @override
  String get recordingsNotSynced => 'You have recordings that aren\'t synced yet.';

  @override
  String get syncingBackground => 'We\'ll keep syncing your recordings in the background.';

  @override
  String get noConversationsYet => 'No conversations yet.';

  @override
  String get noStarredConversations => 'No starred conversations yet.';

  @override
  String get starConversationHint => 'To star a conversation, open it and tap the star icon in the header.';

  @override
  String get searchConversations => 'Search Conversations';

  @override
  String selectedCount(int count) {
    return '$count selected';
  }

  @override
  String get merge => 'Merge';

  @override
  String get mergeConversations => 'Merge Conversations';

  @override
  String mergeConversationsMessage(int count) {
    return 'This will combine $count conversations into one. All content will be merged and regenerated.';
  }

  @override
  String get mergingInBackground => 'Merging in background. This may take a moment.';

  @override
  String get failedToStartMerge => 'Failed to start merge';

  @override
  String get askAnything => 'Ask anything';

  @override
  String get noMessagesYet => 'No messages yet!\nWhy don\'t you start a conversation?';

  @override
  String get deletingMessages => 'Deleting your messages from Omi\'s memory...';

  @override
  String get messageCopied => 'Message copied to clipboard.';

  @override
  String get cannotReportOwnMessage => 'You cannot report your own messages.';

  @override
  String get reportMessage => 'Report Message';

  @override
  String get reportMessageConfirm => 'Are you sure you want to report this message?';

  @override
  String get messageReported => 'Message reported successfully.';

  @override
  String get thankYouFeedback => 'Thank you for your feedback!';

  @override
  String get clearChat => 'Clear Chat?';

  @override
  String get clearChatConfirm => 'Are you sure you want to clear the chat? This action cannot be undone.';

  @override
  String get maxFilesLimit => 'You can only upload 4 files at a time';

  @override
  String get chatWithOmi => 'Chat with Omi';

  @override
  String get apps => 'Apps';

  @override
  String get noAppsFound => 'No apps found';

  @override
  String get tryAdjustingSearch => 'Try adjusting your search or filters';

  @override
  String get createYourOwnApp => 'Create Your Own App';

  @override
  String get buildAndShareApp => 'Build and share your custom app';

  @override
  String get searchApps => 'Search 1500+ Apps';

  @override
  String get myApps => 'My Apps';

  @override
  String get installedApps => 'Installed Apps';

  @override
  String get unableToFetchApps => 'Unable to fetch apps :(\n\nPlease check your internet connection and try again.';

  @override
  String get aboutOmi => 'About Omi';

  @override
  String get privacyPolicy => 'Privacy Policy';

  @override
  String get visitWebsite => 'Visit Website';

  @override
  String get helpOrInquiries => 'Help or Inquiries?';

  @override
  String get joinCommunity => 'Join the community!';

  @override
  String get membersAndCounting => '8000+ members and counting.';

  @override
  String get deleteAccountTitle => 'Delete Account';

  @override
  String get deleteAccountConfirm => 'Are you sure you want to delete your account?';

  @override
  String get cannotBeUndone => 'This cannot be undone.';

  @override
  String get allDataErased => 'All of your memories and conversations will be permanently erased.';

  @override
  String get appsDisconnected => 'Your Apps and Integrations will be disconnected effectively immediately.';

  @override
  String get exportBeforeDelete =>
      'You can export your data before deleting your account, but once deleted, it cannot be recovered.';

  @override
  String get deleteAccountCheckbox =>
      'I understand that deleting my account is permanent and all data, including memories and conversations, will be lost and cannot be recovered.';

  @override
  String get areYouSure => 'Are you sure?';

  @override
  String get deleteAccountFinal =>
      'This action is irreversible and will permanently delete your account and all associated data. Are you sure you want to proceed?';

  @override
  String get deleteNow => 'Delete Now';

  @override
  String get goBack => 'Go Back';

  @override
  String get checkBoxToConfirm =>
      'Check the box to confirm you understand that deleting your account is permanent and irreversible.';

  @override
  String get profile => 'Profile';

  @override
  String get name => 'Name';

  @override
  String get email => 'Email';

  @override
  String get customVocabulary => 'Custom Vocabulary';

  @override
  String get identifyingOthers => 'Identifying Others';

  @override
  String get paymentMethods => 'Payment Methods';

  @override
  String get conversationDisplay => 'Conversation Display';

  @override
  String get dataPrivacy => 'Data & Privacy';

  @override
  String get userId => 'User ID';

  @override
  String get notSet => 'Not set';

  @override
  String get userIdCopied => 'User ID copied to clipboard';

  @override
  String get systemDefault => 'System Default';

  @override
  String get planAndUsage => 'Plan & Usage';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'Device Settings';

  @override
  String get chatTools => 'Chat Tools';

  @override
  String get feedbackBug => 'Feedback / Bug';

  @override
  String get helpCenter => 'Help Center';

  @override
  String get developerSettings => 'Developer Settings';

  @override
  String get getOmiForMac => 'Get Omi for Mac';

  @override
  String get referralProgram => 'Referral Program';

  @override
  String get signOut => 'Sign Out';

  @override
  String get appAndDeviceCopied => 'App and device details copied';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Your Privacy, Your Control';

  @override
  String get privacyIntro =>
      'At Omi, we are committed to protecting your privacy. This page allows you to control how your data is stored and used.';

  @override
  String get learnMore => 'Learn more...';

  @override
  String get dataProtectionLevel => 'Data Protection Level';

  @override
  String get dataProtectionDesc =>
      'Your data is secured by default with strong encryption. Review your settings and future privacy options below.';

  @override
  String get appAccess => 'App Access';

  @override
  String get appAccessDesc => 'The following apps can access your data. Tap on an app to manage its permissions.';

  @override
  String get noAppsExternalAccess => 'No installed apps have external access to your data.';

  @override
  String get deviceName => 'Device Name';

  @override
  String get deviceId => 'Device ID';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'SD Card Sync';

  @override
  String get hardwareRevision => 'Hardware Revision';

  @override
  String get modelNumber => 'Model Number';

  @override
  String get manufacturer => 'Manufacturer';

  @override
  String get doubleTap => 'Double Tap';

  @override
  String get ledBrightness => 'LED Brightness';

  @override
  String get micGain => 'Mic Gain';

  @override
  String get disconnect => 'Disconnect';

  @override
  String get forgetDevice => 'Forget Device';

  @override
  String get chargingIssues => 'Charging Issues';

  @override
  String get disconnectDevice => 'Disconnect Device';

  @override
  String get unpairDevice => 'Unpair Device';

  @override
  String get unpairAndForget => 'Unpair and Forget Device';

  @override
  String get deviceDisconnectedMessage => 'Your Omi has been disconnected 😔';

  @override
  String get deviceUnpairedMessage =>
      'Device unpaired. Go to Settings > Bluetooth and forget the device to complete unpairing.';

  @override
  String get unpairDialogTitle => 'Unpair Device';

  @override
  String get unpairDialogMessage =>
      'This will unpair the device so it can be connected to another phone. You will need to go to Settings > Bluetooth and forget the device to complete the process.';

  @override
  String get deviceNotConnected => 'Device Not Connected';

  @override
  String get connectDeviceMessage => 'Connect your Omi device to access\ndevice settings and customization';

  @override
  String get deviceInfoSection => 'Device Information';

  @override
  String get customizationSection => 'Customization';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 undetected';

  @override
  String get v2UndetectedMessage =>
      'We see that you either have a V1 device or your device is not connected. SD Card functionality is available only for V2 devices.';

  @override
  String get endConversation => 'End Conversation';

  @override
  String get pauseResume => 'Pause/Resume';

  @override
  String get starConversation => 'Star Conversation';

  @override
  String get doubleTapAction => 'Double Tap Action';

  @override
  String get doubleTapActionDesc => 'Choose what happens when you double tap';

  @override
  String get endAndProcess => 'End & Process Conversation';

  @override
  String get pauseResumeRecording => 'Pause/Resume Recording';

  @override
  String get starOngoing => 'Star Ongoing Conversation';

  @override
  String get starOngoingDesc => 'Mark to star when conversation ends';

  @override
  String get off => 'Off';

  @override
  String get max => 'Max';

  @override
  String get mute => 'Mute';

  @override
  String get quiet => 'Quiet';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'High';

  @override
  String get micGainDescMuted => 'Microphone is muted';

  @override
  String get micGainDescLow => 'Very quiet - for loud environments';

  @override
  String get micGainDescModerate => 'Quiet - for moderate noise';

  @override
  String get micGainDescNeutral => 'Neutral - balanced recording';

  @override
  String get micGainDescSlightlyBoosted => 'Slightly boosted - normal use';

  @override
  String get micGainDescBoosted => 'Boosted - for quiet environments';

  @override
  String get micGainDescHigh => 'High - for distant or soft voices';

  @override
  String get micGainDescVeryHigh => 'Very high - for very quiet sources';

  @override
  String get micGainDescMax => 'Maximum - use with caution';

  @override
  String get developerSettingsTitle => 'Developer Settings';

  @override
  String get saving => 'Saving...';

  @override
  String get personaConfig => 'Configure your AI persona';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transcription';

  @override
  String get transcriptionConfig => 'Configure STT provider';

  @override
  String get conversationTimeout => 'Conversation Timeout';

  @override
  String get conversationTimeoutConfig => 'Set when conversations auto-end';

  @override
  String get importData => 'Import Data';

  @override
  String get importDataConfig => 'Import data from other sources';

  @override
  String get debugDiagnostics => 'Debug & Diagnostics';

  @override
  String get endpointUrl => 'Endpoint URL';

  @override
  String get noApiKeys => 'No API keys yet';

  @override
  String get createKeyToStart => 'Create a key to get started';

  @override
  String get createKey => 'Create Key';

  @override
  String get docs => 'Docs';

  @override
  String get yourOmiInsights => 'Your Omi Insights';

  @override
  String get today => 'Today';

  @override
  String get thisMonth => 'This Month';

  @override
  String get thisYear => 'This Year';

  @override
  String get allTime => 'All Time';

  @override
  String get noActivityYet => 'No Activity Yet';

  @override
  String get startConversationToSeeInsights => 'Start a conversation with Omi\nto see your usage insights here.';

  @override
  String get listening => 'Listening';

  @override
  String get listeningSubtitle => 'Total time Omi has actively listened.';

  @override
  String get understanding => 'Understanding';

  @override
  String get understandingSubtitle => 'Words understood from your conversations.';

  @override
  String get providing => 'Providing';

  @override
  String get providingSubtitle => 'Action items, and notes automatically captured.';

  @override
  String get remembering => 'Remembering';

  @override
  String get rememberingSubtitle => 'Facts and details remembered for you.';

  @override
  String get unlimitedPlan => 'Unlimited Plan';

  @override
  String get managePlan => 'Manage Plan';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Your plan will cancel on $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Your plan renews on $date.';
  }

  @override
  String get basicPlan => 'Basic Plan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used of $limit mins used';
  }

  @override
  String get upgrade => 'Upgrade';

  @override
  String get upgradeToUnlimited => 'Upgrade to Unlimited';

  @override
  String basicPlanDesc(int limit) {
    return 'Your plan includes $limit free minutes per month. Upgrade to go unlimited.';
  }

  @override
  String get shareStatsMessage => 'Sharing my Omi stats! (omi.me - your always-on AI assistant)';

  @override
  String get sharePeriodToday => 'Today, omi has:';

  @override
  String get sharePeriodMonth => 'This month, omi has:';

  @override
  String get sharePeriodYear => 'This year, omi has:';

  @override
  String get sharePeriodAllTime => 'So far, omi has:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Listened for $minutes minutes';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Understood $words words';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Provided $count insights';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Remembered $count memories';
  }

  @override
  String get debugLogs => 'Debug Logs';

  @override
  String get debugLogsAutoDelete => 'Auto-deletes after 3 days.';

  @override
  String get debugLogsDesc => 'Helps diagnose issues';

  @override
  String get noLogFilesFound => 'No log files found.';

  @override
  String get omiDebugLog => 'Omi debug log';

  @override
  String get logShared => 'Log shared';

  @override
  String get selectLogFile => 'Select Log File';

  @override
  String get shareLogs => 'Share Logs';

  @override
  String get debugLogCleared => 'Debug log cleared';

  @override
  String get clear => 'Clear';

  @override
  String get exportStarted => 'Export started. This may take a few seconds...';

  @override
  String get exportAllData => 'Export All Data';

  @override
  String get exportDataDesc => 'Export conversations to a JSON file';

  @override
  String get exportedConversations => 'Exported Conversations from Omi';

  @override
  String get exportShared => 'Export shared';

  @override
  String get deleteKnowledgeGraphTitle => 'Delete Knowledge Graph?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'This will delete all derived knowledge graph data (nodes and connections). Your original memories will remain safe. The graph will be rebuilt over time or upon next request.';

  @override
  String get knowledgeGraphDeleted => 'Knowledge Graph deleted successfully';

  @override
  String deleteGraphFailed(String error) {
    return 'Failed to delete graph: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Delete Knowledge Graph';

  @override
  String get deleteKnowledgeGraphDesc => 'Clear all nodes and connections';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP Server';

  @override
  String get mcpServerDesc => 'Connect AI assistants to your data';

  @override
  String get serverUrl => 'Server URL';

  @override
  String get urlCopied => 'URL copied';

  @override
  String get apiKeyAuth => 'API Key Auth';

  @override
  String get header => 'Header';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => 'Use your MCP API key';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Conversation Events';

  @override
  String get newConversationCreated => 'New conversation created';

  @override
  String get realtimeTranscript => 'Real-time Transcript';

  @override
  String get transcriptReceived => 'Transcript received';

  @override
  String get audioBytes => 'Audio Bytes';

  @override
  String get audioDataReceived => 'Audio data received';

  @override
  String get intervalSeconds => 'Interval (seconds)';

  @override
  String get daySummary => 'Day Summary';

  @override
  String get summaryGenerated => 'Summary generated';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Add to claude_desktop_config.json';

  @override
  String get copyConfig => 'Copy Config';

  @override
  String get configCopied => 'Config copied to clipboard';

  @override
  String get listeningMins => 'Listening (mins)';

  @override
  String get understandingWords => 'Understanding (words)';

  @override
  String get insights => 'Insights';

  @override
  String get memories => 'Memories';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used of $limit min used this month';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used of $limit words used this month';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used of $limit insights gained this month';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used of $limit memories created this month';
  }
}
