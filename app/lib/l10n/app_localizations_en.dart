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
  String get ok => 'Ok';

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
  String get clear => 'Clear';

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
  String get endAndProcess => 'End & Process Conversation';

  @override
  String get pauseResumeRecording => 'Pause/Resume Recording';

  @override
  String get starOngoing => 'Star Ongoing Conversation';

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

  @override
  String get visibility => 'Visibility';

  @override
  String get visibilitySubtitle => 'Control which conversations appear in your list';

  @override
  String get showShortConversations => 'Show Short Conversations';

  @override
  String get showShortConversationsDesc => 'Display conversations shorter than the threshold';

  @override
  String get showDiscardedConversations => 'Show Discarded Conversations';

  @override
  String get showDiscardedConversationsDesc => 'Include conversations marked as discarded';

  @override
  String get shortConversationThreshold => 'Short Conversation Threshold';

  @override
  String get shortConversationThresholdSubtitle =>
      'Conversations shorter than this will be hidden unless enabled above';

  @override
  String get durationThreshold => 'Duration Threshold';

  @override
  String get durationThresholdDesc => 'Hide conversations shorter than this';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Custom Vocabulary';

  @override
  String get addWords => 'Add Words';

  @override
  String get addWordsDesc => 'Names, terms, or uncommon words';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Coming Soon';

  @override
  String get chatToolsFooter => 'Connect your apps to view data and metrics in chat.';

  @override
  String get completeAuthInBrowser => 'Please complete authentication in your browser. Once done, return to the app.';

  @override
  String failedToStartAuth(String appName) {
    return 'Failed to start $appName authentication';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Disconnect $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Are you sure you want to disconnect from $appName? You can reconnect anytime.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Disconnected from $appName';
  }

  @override
  String get failedToDisconnect => 'Failed to disconnect';

  @override
  String connectTo(String appName) {
    return 'Connect to $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'You\'ll need to authorize Omi to access your $appName data. This will open your browser for authentication.';
  }

  @override
  String get continueAction => 'Continue';

  @override
  String get languageTitle => 'Language';

  @override
  String get primaryLanguage => 'Primary Language';

  @override
  String get automaticTranslation => 'Automatic Translation';

  @override
  String get detectLanguages => 'Detect 10+ languages';

  @override
  String get authorizeSavingRecordings => 'Authorize Saving Recordings';

  @override
  String get thanksForAuthorizing => 'Thanks for authorizing!';

  @override
  String get needYourPermission => 'We need your permission';

  @override
  String get alreadyGavePermission =>
      'You\'ve already given us permission to save your recordings. Here\'s a reminder of why we need it:';

  @override
  String get wouldLikePermission => 'We\'d like your permission to save your voice recordings. Here\'s why:';

  @override
  String get improveSpeechProfile => 'Improve Your Speech Profile';

  @override
  String get improveSpeechProfileDesc => 'We use recordings to further train and enhance your personal speech profile.';

  @override
  String get trainFamilyProfiles => 'Train Profiles for Friends and Family';

  @override
  String get trainFamilyProfilesDesc =>
      'Your recordings help us recognize and create profiles for your friends and family.';

  @override
  String get enhanceTranscriptAccuracy => 'Enhance Transcript Accuracy';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'As our model improves, we can provide better transcription results for your recordings.';

  @override
  String get legalNotice =>
      'Legal Notice: The legality of recording and storing voice data may vary depending on your location and how you use this feature. It\'s your responsibility to ensure compliance with local laws and regulations.';

  @override
  String get alreadyAuthorized => 'Already Authorized';

  @override
  String get authorize => 'Authorize';

  @override
  String get revokeAuthorization => 'Revoke Authorization';

  @override
  String get authorizationSuccessful => 'Authorization successful!';

  @override
  String get failedToAuthorize => 'Failed to authorize. Please try again.';

  @override
  String get authorizationRevoked => 'Authorization revoked.';

  @override
  String get recordingsDeleted => 'Recordings deleted.';

  @override
  String get failedToRevoke => 'Failed to revoke authorization. Please try again.';

  @override
  String get permissionRevokedTitle => 'Permission Revoked';

  @override
  String get permissionRevokedMessage => 'Do you want us to remove all your existing recordings too?';

  @override
  String get yes => 'Yes';

  @override
  String get editName => 'Edit Name';

  @override
  String get howShouldOmiCallYou => 'How should Omi call you?';

  @override
  String get enterYourName => 'Enter your name';

  @override
  String get nameCannotBeEmpty => 'Name cannot be empty';

  @override
  String get nameUpdatedSuccessfully => 'Name updated successfully!';

  @override
  String get calendarSettings => 'Calendar settings';

  @override
  String get calendarProviders => 'Calendar Providers';

  @override
  String get macOsCalendar => 'macOS Calendar';

  @override
  String get connectMacOsCalendar => 'Connect your local macOS calendar';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sync with your Google account';

  @override
  String get showMeetingsMenuBar => 'Show upcoming meetings in menu bar';

  @override
  String get showMeetingsMenuBarDesc => 'Display your next meeting and time until it starts in the macOS menu bar';

  @override
  String get showEventsNoParticipants => 'Show events with no participants';

  @override
  String get showEventsNoParticipantsDesc =>
      'When enabled, Coming Up shows events without participants or a video link.';

  @override
  String get yourMeetings => 'Your Meetings';

  @override
  String get refresh => 'Refresh';

  @override
  String get noUpcomingMeetings => 'No upcoming meetings found';

  @override
  String get checkingNextDays => 'Checking next 30 days';

  @override
  String get tomorrow => 'Tomorrow';

  @override
  String get googleCalendarComingSoon => 'Google Calendar integration coming soon!';

  @override
  String connectedAsUser(String userId) {
    return 'Connected as user: $userId';
  }

  @override
  String get defaultWorkspace => 'Default Workspace';

  @override
  String get tasksCreatedInWorkspace => 'Tasks will be created in this workspace';

  @override
  String get defaultProjectOptional => 'Default Project (Optional)';

  @override
  String get leaveUnselectedTasks => 'Leave unselected to create tasks without a project';

  @override
  String get noProjectsInWorkspace => 'No projects found in this workspace';

  @override
  String get conversationTimeoutDesc =>
      'Choose how long to wait in silence before automatically ending a conversation:';

  @override
  String get timeout2Minutes => '2 minutes';

  @override
  String get timeout2MinutesDesc => 'End conversation after 2 minutes of silence';

  @override
  String get timeout5Minutes => '5 minutes';

  @override
  String get timeout5MinutesDesc => 'End conversation after 5 minutes of silence';

  @override
  String get timeout10Minutes => '10 minutes';

  @override
  String get timeout10MinutesDesc => 'End conversation after 10 minutes of silence';

  @override
  String get timeout30Minutes => '30 minutes';

  @override
  String get timeout30MinutesDesc => 'End conversation after 30 minutes of silence';

  @override
  String get timeout4Hours => '4 hours';

  @override
  String get timeout4HoursDesc => 'End conversation after 4 hours of silence';

  @override
  String get conversationEndAfterHours => 'Conversations will now end after 4 hours of silence';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Conversations will now end after $minutes minute(s) of silence';
  }

  @override
  String get tellUsPrimaryLanguage => 'Tell us your primary language';

  @override
  String get languageForTranscription => 'Set your language for sharper transcriptions and a personalized experience.';

  @override
  String get singleLanguageModeInfo => 'Single Language Mode is enabled. Translation is disabled for higher accuracy.';

  @override
  String get searchLanguageHint => 'Search language by name or code';

  @override
  String get noLanguagesFound => 'No languages found';

  @override
  String get skip => 'Skip';

  @override
  String languageSetTo(String language) {
    return 'Language set to $language';
  }

  @override
  String get failedToSetLanguage => 'Failed to set language';

  @override
  String appSettings(String appName) {
    return '$appName Settings';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Disconnect from $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'This will remove your $appName authentication. You\'ll need to reconnect to use it again.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Connected to $appName';
  }

  @override
  String get account => 'Account';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Your action items will be synced to your $appName account';
  }

  @override
  String get defaultSpace => 'Default Space';

  @override
  String get selectSpaceInWorkspace => 'Select a space in your workspace';

  @override
  String get noSpacesInWorkspace => 'No spaces found in this workspace';

  @override
  String get defaultList => 'Default List';

  @override
  String get tasksAddedToList => 'Tasks will be added to this list';

  @override
  String get noListsInSpace => 'No lists found in this space';

  @override
  String failedToLoadRepos(String error) {
    return 'Failed to load repositories: $error';
  }

  @override
  String get defaultRepoSaved => 'Default repository saved';

  @override
  String get failedToSaveDefaultRepo => 'Failed to save default repository';

  @override
  String get defaultRepository => 'Default Repository';

  @override
  String get selectDefaultRepoDesc =>
      'Select a default repository for creating issues. You can still specify a different repository when creating issues.';

  @override
  String get noReposFound => 'No repositories found';

  @override
  String get private => 'Private';

  @override
  String updatedDate(String date) {
    return 'Updated $date';
  }

  @override
  String get yesterday => 'yesterday';

  @override
  String daysAgo(int count) {
    return '$count days ago';
  }

  @override
  String get oneWeekAgo => '1 week ago';

  @override
  String weeksAgo(int count) {
    return '$count weeks ago';
  }

  @override
  String get oneMonthAgo => '1 month ago';

  @override
  String monthsAgo(int count) {
    return '$count months ago';
  }

  @override
  String get issuesCreatedInRepo => 'Issues will be created in your default repository';

  @override
  String get taskIntegrations => 'Task Integrations';

  @override
  String get configureSettings => 'Configure Settings';

  @override
  String get completeAuthBrowser => 'Please complete authentication in your browser. Once done, return to the app.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Failed to start $appName authentication';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Connect to $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'You\'ll need to authorize Omi to create tasks in your $appName account. This will open your browser for authentication.';
  }

  @override
  String get continueButton => 'Continue';

  @override
  String appIntegration(String appName) {
    return '$appName Integration';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integration with $appName is coming soon! We\'re working hard to bring you more task management options.';
  }

  @override
  String get gotIt => 'Got it';

  @override
  String get tasksExportedOneApp => 'Tasks can be exported to one app at a time.';

  @override
  String get completeYourUpgrade => 'Complete Your Upgrade';

  @override
  String get importConfiguration => 'Import Configuration';

  @override
  String get exportConfiguration => 'Export configuration';

  @override
  String get bringYourOwn => 'Bring your own';

  @override
  String get payYourSttProvider => 'Freely use omi. You only pay your STT provider directly.';

  @override
  String get freeMinutesMonth => '1,200 free minutes/month included. Unlimited with ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host is required';

  @override
  String get validPortRequired => 'Valid port is required';

  @override
  String get validWebsocketUrlRequired => 'Valid WebSocket URL is required (wss://)';

  @override
  String get apiUrlRequired => 'API URL is required';

  @override
  String get apiKeyRequired => 'API key is required';

  @override
  String get invalidJsonConfig => 'Invalid JSON configuration';

  @override
  String errorSaving(String error) {
    return 'Error saving: $error';
  }

  @override
  String get configCopiedToClipboard => 'Configuration copied to clipboard';

  @override
  String get pasteJsonConfig => 'Paste your JSON configuration below:';

  @override
  String get addApiKeyAfterImport => 'You\'ll need to add your own API key after importing';

  @override
  String get paste => 'Paste';

  @override
  String get import => 'Import';

  @override
  String get invalidProviderInConfig => 'Invalid provider in configuration';

  @override
  String importedConfig(String providerName) {
    return 'Imported $providerName configuration';
  }

  @override
  String invalidJson(String error) {
    return 'Invalid JSON: $error';
  }

  @override
  String get provider => 'Provider';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'On Device';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Enter your STT HTTP endpoint';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Enter your live STT WebSocket endpoint';

  @override
  String get apiKey => 'API Key';

  @override
  String get enterApiKey => 'Enter your API key';

  @override
  String get storedLocallyNeverShared => 'Stored locally, never shared';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Advanced';

  @override
  String get configuration => 'Configuration';

  @override
  String get requestConfiguration => 'Request Configuration';

  @override
  String get responseSchema => 'Response Schema';

  @override
  String get modified => 'Modified';

  @override
  String get resetRequestConfig => 'Reset request config to default';

  @override
  String get logs => 'Logs';

  @override
  String get logsCopied => 'Logs copied';

  @override
  String get noLogsYet => 'No logs yet. Start recording to see custom STT activity.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName uses $codecReason. Omi will be used.';
  }

  @override
  String get omiTranscription => 'Omi Transcription';

  @override
  String get bestInClassTranscription => 'Best in class transcription with zero setup';

  @override
  String get instantSpeakerLabels => 'Instant speaker labels';

  @override
  String get languageTranslation => '100+ language translation';

  @override
  String get optimizedForConversation => 'Optimized for conversation';

  @override
  String get autoLanguageDetection => 'Auto language detection';

  @override
  String get highAccuracy => 'High accuracy';

  @override
  String get privacyFirst => 'Privacy first';

  @override
  String get saveChanges => 'Save Changes';

  @override
  String get resetToDefault => 'Reset to Default';

  @override
  String get viewTemplate => 'View Template';

  @override
  String get trySomethingLike => 'Try something like...';

  @override
  String get tryIt => 'Try it';

  @override
  String get creatingPlan => 'Creating plan';

  @override
  String get developingLogic => 'Developing logic';

  @override
  String get designingApp => 'Designing app';

  @override
  String get generatingIconStep => 'Generating icon';

  @override
  String get finalTouches => 'Final touches';

  @override
  String get processing => 'Processing...';

  @override
  String get features => 'Features';

  @override
  String get creatingYourApp => 'Creating your app...';

  @override
  String get generatingIcon => 'Generating icon...';

  @override
  String get whatShouldWeMake => 'What should we make?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Description';

  @override
  String get publicLabel => 'Public';

  @override
  String get privateLabel => 'Private';

  @override
  String get free => 'Free';

  @override
  String get perMonth => '/ Month';

  @override
  String get tailoredConversationSummaries => 'Tailored Conversation Summaries';

  @override
  String get customChatbotPersonality => 'Custom Chatbot Personality';

  @override
  String get makePublic => 'Make public';

  @override
  String get anyoneCanDiscover => 'Anyone can discover your app';

  @override
  String get onlyYouCanUse => 'Only you can use this app';

  @override
  String get paidApp => 'Paid app';

  @override
  String get usersPayToUse => 'Users pay to use your app';

  @override
  String get freeForEveryone => 'Free for everyone';

  @override
  String get perMonthLabel => '/ month';

  @override
  String get creating => 'Creating...';

  @override
  String get createApp => 'Create App';

  @override
  String get searchingForDevices => 'Searching for devices...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'DEVICES',
      one: 'DEVICE',
    );
    return '$count $_temp0 FOUND NEARBY';
  }

  @override
  String get pairingSuccessful => 'PAIRING SUCCESSFUL';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Error connecting to Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Don\'t show it again';

  @override
  String get iUnderstand => 'I Understand';

  @override
  String get enableBluetooth => 'Enable Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.';

  @override
  String get contactSupport => 'Contact Support?';

  @override
  String get connectLater => 'Connect Later';

  @override
  String get grantPermissions => 'Grant permissions';

  @override
  String get backgroundActivity => 'Background activity';

  @override
  String get backgroundActivityDesc => 'Let Omi run in the background for better stability';

  @override
  String get locationAccess => 'Location access';

  @override
  String get locationAccessDesc => 'Enable background location for the full experience';

  @override
  String get notifications => 'Notifications';

  @override
  String get notificationsDesc => 'Enable notifications to stay informed';

  @override
  String get locationServiceDisabled => 'Location Service Disabled';

  @override
  String get locationServiceDisabledDesc =>
      'Location Service is Disabled. Please go to Settings > Privacy & Security > Location Services and enable it';

  @override
  String get backgroundLocationDenied => 'Background Location Access Denied';

  @override
  String get backgroundLocationDeniedDesc =>
      'Please go to device settings and set location permission to \"Always Allow\"';

  @override
  String get lovingOmi => 'Loving Omi?';

  @override
  String get leaveReviewIos =>
      'Help us reach more people by leaving a review in the App Store. Your feedback means the world to us!';

  @override
  String get leaveReviewAndroid =>
      'Help us reach more people by leaving a review in the Google Play Store. Your feedback means the world to us!';

  @override
  String get rateOnAppStore => 'Rate on App Store';

  @override
  String get rateOnGooglePlay => 'Rate on Google Play';

  @override
  String get maybeLater => 'Maybe later';

  @override
  String get speechProfileIntro => 'Omi needs to learn your goals and your voice. You\'ll be able to modify it later.';

  @override
  String get getStarted => 'Get Started';

  @override
  String get allDone => 'All done!';

  @override
  String get keepGoing => 'Keep going, you are doing great';

  @override
  String get skipThisQuestion => 'Skip this question';

  @override
  String get skipForNow => 'Skip for now';

  @override
  String get connectionError => 'Connection Error';

  @override
  String get connectionErrorDesc =>
      'Failed to connect to the server. Please check your internet connection and try again.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Invalid recording detected';

  @override
  String get multipleSpeakersDesc =>
      'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.';

  @override
  String get tooShortDesc => 'There is not enough speech detected. Please speak more and try again.';

  @override
  String get invalidRecordingDesc => 'Please make sure you speak for at least 5 seconds and not more than 90.';

  @override
  String get areYouThere => 'Are you there?';

  @override
  String get noSpeechDesc =>
      'We could not detect any speech. Please make sure to speak for at least 10 seconds and not more than 3 minutes.';

  @override
  String get connectionLost => 'Connection Lost';

  @override
  String get connectionLostDesc =>
      'The connection was interrupted. Please check your internet connection and try again.';

  @override
  String get tryAgain => 'Try Again';

  @override
  String get connectOmiOmiGlass => 'Connect Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continue Without Device';

  @override
  String get permissionsRequired => 'Permissions Required';

  @override
  String get permissionsRequiredDesc =>
      'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.';

  @override
  String get openSettings => 'Open Settings';

  @override
  String get wantDifferentName => 'Want to go by something else?';

  @override
  String get whatsYourName => 'What\'s your name?';

  @override
  String get speakTranscribeSummarize => 'Speak. Transcribe. Summarize.';

  @override
  String get signInWithApple => 'Sign in with Apple';

  @override
  String get signInWithGoogle => 'Sign in with Google';

  @override
  String get byContinuingAgree => 'By continuing, you agree to our ';

  @override
  String get termsOfUse => 'Terms of Use';

  @override
  String get omiYourAiCompanion => 'Omi – Your AI Companion';

  @override
  String get captureEveryMoment => 'Capture every moment. Get AI-powered\nsummaries. Never take notes again.';

  @override
  String get appleWatchSetup => 'Apple Watch Setup';

  @override
  String get permissionRequestedExclaim => 'Permission Requested!';

  @override
  String get microphonePermission => 'Microphone Permission';

  @override
  String get permissionGrantedNow =>
      'Permission granted! Now:\n\nOpen the Omi app on your watch and tap \"Continue\" below';

  @override
  String get needMicrophonePermission =>
      'We need microphone permission.\n\n1. Tap \"Grant Permission\"\n2. Allow on your iPhone\n3. Watch app will close\n4. Reopen and tap \"Continue\"';

  @override
  String get grantPermissionButton => 'Grant Permission';

  @override
  String get needHelp => 'Need Help?';

  @override
  String get troubleshootingSteps =>
      'Troubleshooting:\n\n1. Ensure Omi is installed on your watch\n2. Open the Omi app on your watch\n3. Look for the permission popup\n4. Tap \"Allow\" when prompted\n5. App on your watch will close - reopen it\n6. Come back and tap \"Continue\" on your iPhone';

  @override
  String get recordingStartedSuccessfully => 'Recording started successfully!';

  @override
  String get permissionNotGrantedYet =>
      'Permission not granted yet. Please make sure you allowed microphone access and reopened the app on your watch.';

  @override
  String errorRequestingPermission(String error) {
    return 'Error requesting permission: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Error starting recording: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Select your primary language';

  @override
  String get languageBenefits => 'Set your language for sharper transcriptions and a personalized experience';

  @override
  String get whatsYourPrimaryLanguage => 'What\'s your primary language?';

  @override
  String get selectYourLanguage => 'Select your language';

  @override
  String get personalGrowthJourney => 'Your personal growth journey with AI that listens to your every word.';

  @override
  String get actionItemsTitle => 'To-Do\'s';

  @override
  String get actionItemsDescription => 'Tap to edit • Long press to select • Swipe for actions';

  @override
  String get tabToDo => 'To Do';

  @override
  String get tabDone => 'Done';

  @override
  String get tabOld => 'Old';

  @override
  String get emptyTodoMessage => '🎉 All caught up!\nNo pending action items';

  @override
  String get emptyDoneMessage => 'No completed items yet';

  @override
  String get emptyOldMessage => '✅ No old tasks';

  @override
  String get noItems => 'No items';

  @override
  String get actionItemMarkedIncomplete => 'Action item marked as incomplete';

  @override
  String get actionItemCompleted => 'Action item completed';

  @override
  String get deleteActionItemTitle => 'Delete Action Item';

  @override
  String get deleteActionItemMessage => 'Are you sure you want to delete this action item?';

  @override
  String get deleteSelectedItemsTitle => 'Delete Selected Items';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Action item \"$description\" deleted';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'Failed to delete action item';

  @override
  String get failedToDeleteItems => 'Failed to delete items';

  @override
  String get failedToDeleteSomeItems => 'Failed to delete some items';

  @override
  String get welcomeActionItemsTitle => 'Ready for Action Items';

  @override
  String get welcomeActionItemsDescription =>
      'Your AI will automatically extract tasks and to-dos from your conversations. They\'ll appear here when created.';

  @override
  String get autoExtractionFeature => 'Automatically extracted from conversations';

  @override
  String get editSwipeFeature => 'Tap to edit, swipe to complete or delete';

  @override
  String itemsSelected(int count) {
    return '$count selected';
  }

  @override
  String get selectAll => 'Select all';

  @override
  String get deleteSelected => 'Delete selected';

  @override
  String searchMemories(int count) {
    return 'Search $count Memories';
  }

  @override
  String get memoryDeleted => 'Memory Deleted.';

  @override
  String get undo => 'Undo';

  @override
  String get noMemoriesYet => 'No memories yet';

  @override
  String get noInterestingMemories => 'No interesting memories yet';

  @override
  String get noSystemMemories => 'No system memories yet';

  @override
  String get noMemoriesInCategories => 'No memories in these categories';

  @override
  String get noMemoriesFound => 'No memories found';

  @override
  String get addFirstMemory => 'Add your first memory';

  @override
  String get clearMemoryTitle => 'Clear Omi\'s Memory';

  @override
  String get clearMemoryMessage => 'Are you sure you want to clear Omi\'s memory? This action cannot be undone.';

  @override
  String get clearMemoryButton => 'Clear Memory';

  @override
  String get memoryClearedSuccess => 'Omi\'s memory about you has been cleared';

  @override
  String get noMemoriesToDelete => 'No memories to delete';

  @override
  String get createMemoryTooltip => 'Create new memory';

  @override
  String get createActionItemTooltip => 'Create new action item';

  @override
  String get memoryManagement => 'Memory Management';

  @override
  String get filterMemories => 'Filter Memories';

  @override
  String totalMemoriesCount(int count) {
    return 'You have $count total memories';
  }

  @override
  String get publicMemories => 'Public memories';

  @override
  String get privateMemories => 'Private memories';

  @override
  String get makeAllPrivate => 'Make All Memories Private';

  @override
  String get makeAllPublic => 'Make All Memories Public';

  @override
  String get deleteAllMemories => 'Delete All Memories';

  @override
  String get allMemoriesPrivateResult => 'All memories are now private';

  @override
  String get allMemoriesPublicResult => 'All memories are now public';

  @override
  String get newMemory => 'New Memory';

  @override
  String get editMemory => 'Edit Memory';

  @override
  String get memoryContentHint => 'I like to eat ice cream...';

  @override
  String get failedToSaveMemory => 'Failed to save. Please check your connection.';

  @override
  String get saveMemory => 'Save Memory';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Create Action Item';

  @override
  String get editActionItem => 'Edit Action Item';

  @override
  String get actionItemDescriptionHint => 'What needs to be done?';

  @override
  String get actionItemDescriptionEmpty => 'Action item description cannot be empty.';

  @override
  String get actionItemUpdated => 'Action item updated';

  @override
  String get failedToUpdateActionItem => 'Failed to update action item';

  @override
  String get actionItemCreated => 'Action item created';

  @override
  String get failedToCreateActionItem => 'Failed to create action item';

  @override
  String get dueDate => 'Due Date';

  @override
  String get time => 'Time';

  @override
  String get addDueDate => 'Add due date';

  @override
  String get pressDoneToSave => 'Press done to save';

  @override
  String get pressDoneToCreate => 'Press done to create';

  @override
  String get filterAll => 'All';

  @override
  String get filterInteresting => 'Interesting';

  @override
  String get filterManual => 'Manual';

  @override
  String get filterSystem => 'System';

  @override
  String get completed => 'Completed';

  @override
  String get markComplete => 'Mark complete';

  @override
  String get actionItemDeleted => 'Action item deleted';

  @override
  String get failedToDeleteActionItem => 'Failed to delete action item';

  @override
  String get deleteActionItemConfirmTitle => 'Delete Action Item';

  @override
  String get deleteActionItemConfirmMessage => 'Are you sure you want to delete this action item?';

  @override
  String get appLanguage => 'App Language';
}
