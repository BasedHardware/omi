import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_ja.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale) : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate = _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates = <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[Locale('en'), Locale('ja')];

  /// The app title displayed in various places
  ///
  /// In en, this message translates to:
  /// **'Omi'**
  String get appTitle;

  /// Tab label for conversation summary
  ///
  /// In en, this message translates to:
  /// **'Conversation'**
  String get conversationTab;

  /// Tab label for transcript view
  ///
  /// In en, this message translates to:
  /// **'Transcript'**
  String get transcriptTab;

  /// Tab label for action items
  ///
  /// In en, this message translates to:
  /// **'Action Items'**
  String get actionItemsTab;

  /// Title for delete confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'Delete Conversation?'**
  String get deleteConversationTitle;

  /// Message for delete confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete this conversation? This action cannot be undone.'**
  String get deleteConversationMessage;

  /// Confirm button label
  ///
  /// In en, this message translates to:
  /// **'Confirm'**
  String get confirm;

  /// Cancel button label
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// OK button label
  ///
  /// In en, this message translates to:
  /// **'OK'**
  String get ok;

  /// Delete button/action label
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get delete;

  /// Add button label
  ///
  /// In en, this message translates to:
  /// **'Add'**
  String get add;

  /// Update button label
  ///
  /// In en, this message translates to:
  /// **'Update'**
  String get update;

  /// Save button
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get save;

  /// Edit button/action label
  ///
  /// In en, this message translates to:
  /// **'Edit'**
  String get edit;

  /// Close button label
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get close;

  /// Menu item to copy transcript
  ///
  /// In en, this message translates to:
  /// **'Copy Transcript'**
  String get copyTranscript;

  /// Menu item to copy summary
  ///
  /// In en, this message translates to:
  /// **'Copy Summary'**
  String get copySummary;

  /// Menu item for testing prompts
  ///
  /// In en, this message translates to:
  /// **'Test Prompt'**
  String get testPrompt;

  /// Menu item to reprocess a conversation
  ///
  /// In en, this message translates to:
  /// **'Reprocess Conversation'**
  String get reprocessConversation;

  /// Menu item to delete a conversation
  ///
  /// In en, this message translates to:
  /// **'Delete Conversation'**
  String get deleteConversation;

  /// Snackbar message when content is copied
  ///
  /// In en, this message translates to:
  /// **'Content copied to clipboard'**
  String get contentCopied;

  /// Error message when starring fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update starred status.'**
  String get failedToUpdateStarred;

  /// Error message when sharing fails
  ///
  /// In en, this message translates to:
  /// **'Conversation URL could not be shared.'**
  String get conversationUrlNotShared;

  /// Error message for conversation processing failure
  ///
  /// In en, this message translates to:
  /// **'Error while processing conversation. Please try again later.'**
  String get errorProcessingConversation;

  /// Message shown when there's no internet
  ///
  /// In en, this message translates to:
  /// **'Please check your internet connection and try again.'**
  String get noInternetConnection;

  /// Title for delete error dialog
  ///
  /// In en, this message translates to:
  /// **'Unable to Delete Conversation'**
  String get unableToDeleteConversation;

  /// Generic error message
  ///
  /// In en, this message translates to:
  /// **'Something went wrong! Please try again later.'**
  String get somethingWentWrong;

  /// Button to copy error details
  ///
  /// In en, this message translates to:
  /// **'Copy error message'**
  String get copyErrorMessage;

  /// Snackbar message after copying error
  ///
  /// In en, this message translates to:
  /// **'Error message copied to clipboard'**
  String get errorCopied;

  /// Label for remaining time/items
  ///
  /// In en, this message translates to:
  /// **'Remaining'**
  String get remaining;

  /// Loading indicator text
  ///
  /// In en, this message translates to:
  /// **'Loading...'**
  String get loading;

  /// Loading duration indicator
  ///
  /// In en, this message translates to:
  /// **'Loading duration...'**
  String get loadingDuration;

  /// Duration in seconds
  ///
  /// In en, this message translates to:
  /// **'{count} seconds'**
  String secondsCount(int count);

  /// People section title
  ///
  /// In en, this message translates to:
  /// **'People'**
  String get people;

  /// Title for add person dialog
  ///
  /// In en, this message translates to:
  /// **'Add New Person'**
  String get addNewPerson;

  /// Title for edit person dialog
  ///
  /// In en, this message translates to:
  /// **'Edit Person'**
  String get editPerson;

  /// Hint text for creating a person
  ///
  /// In en, this message translates to:
  /// **'Create a new person and train Omi to recognize their speech too!'**
  String get createPersonHint;

  /// Speech profile setting
  ///
  /// In en, this message translates to:
  /// **'Speech Profile'**
  String get speechProfile;

  /// Label for speech sample
  ///
  /// In en, this message translates to:
  /// **'Sample {number}'**
  String sampleNumber(int number);

  /// Settings page title
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settings;

  /// Language field label
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get language;

  /// Language picker title
  ///
  /// In en, this message translates to:
  /// **'Select Language'**
  String get selectLanguage;

  /// Deleting in progress indicator
  ///
  /// In en, this message translates to:
  /// **'Deleting...'**
  String get deleting;

  /// Message shown during OAuth flow
  ///
  /// In en, this message translates to:
  /// **'Please complete authentication in your browser. Once done, return to the app.'**
  String get pleaseCompleteAuthentication;

  /// Error when OAuth fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start authentication'**
  String get failedToStartAuthentication;

  /// Success message when import begins
  ///
  /// In en, this message translates to:
  /// **'Import started! You\'ll be notified when it\'s complete.'**
  String get importStarted;

  /// Error when import fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start import. Please try again.'**
  String get failedToStartImport;

  /// Error when file access fails
  ///
  /// In en, this message translates to:
  /// **'Could not access the selected file'**
  String get couldNotAccessFile;

  /// Chat button label
  ///
  /// In en, this message translates to:
  /// **'Ask Omi'**
  String get askOmi;

  /// Done button label
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get done;

  /// Device disconnected status
  ///
  /// In en, this message translates to:
  /// **'Disconnected'**
  String get disconnected;

  /// Searching for device status
  ///
  /// In en, this message translates to:
  /// **'Searching'**
  String get searching;

  /// Button to connect a device
  ///
  /// In en, this message translates to:
  /// **'Connect Device'**
  String get connectDevice;

  /// Message when usage limit is reached
  ///
  /// In en, this message translates to:
  /// **'You\'ve reached your monthly limit.'**
  String get monthlyLimitReached;

  /// Button to check usage details
  ///
  /// In en, this message translates to:
  /// **'Check Usage'**
  String get checkUsage;

  /// Title when sync is in progress
  ///
  /// In en, this message translates to:
  /// **'Syncing recordings'**
  String get syncingRecordings;

  /// Title when there are recordings to sync
  ///
  /// In en, this message translates to:
  /// **'Recordings to sync'**
  String get recordingsToSync;

  /// Title when everything is synced
  ///
  /// In en, this message translates to:
  /// **'All caught up'**
  String get allCaughtUp;

  /// Sync button label
  ///
  /// In en, this message translates to:
  /// **'Sync'**
  String get sync;

  /// Status when pendant is synced
  ///
  /// In en, this message translates to:
  /// **'Pendant is up to date'**
  String get pendantUpToDate;

  /// Status text when sync is complete
  ///
  /// In en, this message translates to:
  /// **'All recordings are synced'**
  String get allRecordingsSynced;

  /// Status when sync is happening
  ///
  /// In en, this message translates to:
  /// **'Syncing in progress'**
  String get syncingInProgress;

  /// Status when ready to sync
  ///
  /// In en, this message translates to:
  /// **'Ready to sync'**
  String get readyToSync;

  /// Hint to start sync
  ///
  /// In en, this message translates to:
  /// **'Tap Sync to start'**
  String get tapSyncToStart;

  /// Warning when pendant is not connected
  ///
  /// In en, this message translates to:
  /// **'Pendant not connected. Connect to sync.'**
  String get pendantNotConnected;

  /// Message when all is synced
  ///
  /// In en, this message translates to:
  /// **'Everything is already synced.'**
  String get everythingSynced;

  /// Message when there are unsynced recordings
  ///
  /// In en, this message translates to:
  /// **'You have recordings that aren\'t synced yet.'**
  String get recordingsNotSynced;

  /// Message during background sync
  ///
  /// In en, this message translates to:
  /// **'We\'ll keep syncing your recordings in the background.'**
  String get syncingBackground;

  /// Empty state when no conversations exist
  ///
  /// In en, this message translates to:
  /// **'No conversations yet.'**
  String get noConversationsYet;

  /// Empty state for starred filter
  ///
  /// In en, this message translates to:
  /// **'No starred conversations yet.'**
  String get noStarredConversations;

  /// Hint explaining how to star conversations
  ///
  /// In en, this message translates to:
  /// **'To star a conversation, open it and tap the star icon in the header.'**
  String get starConversationHint;

  /// Search field placeholder
  ///
  /// In en, this message translates to:
  /// **'Search Conversations'**
  String get searchConversations;

  /// Selection count label
  ///
  /// In en, this message translates to:
  /// **'{count} selected'**
  String selectedCount(int count);

  /// Merge button label
  ///
  /// In en, this message translates to:
  /// **'Merge'**
  String get merge;

  /// Merge dialog title
  ///
  /// In en, this message translates to:
  /// **'Merge Conversations'**
  String get mergeConversations;

  /// Merge confirmation message
  ///
  /// In en, this message translates to:
  /// **'This will combine {count} conversations into one. All content will be merged and regenerated.'**
  String mergeConversationsMessage(int count);

  /// Snackbar message during merge
  ///
  /// In en, this message translates to:
  /// **'Merging in background. This may take a moment.'**
  String get mergingInBackground;

  /// Error message when merge fails
  ///
  /// In en, this message translates to:
  /// **'Failed to start merge'**
  String get failedToStartMerge;

  /// Chat input placeholder
  ///
  /// In en, this message translates to:
  /// **'Ask anything'**
  String get askAnything;

  /// Empty chat state message
  ///
  /// In en, this message translates to:
  /// **'No messages yet!\nWhy don\'t you start a conversation?'**
  String get noMessagesYet;

  /// Loading text while clearing chat
  ///
  /// In en, this message translates to:
  /// **'Deleting your messages from Omi\'s memory...'**
  String get deletingMessages;

  /// Snackbar after copying message
  ///
  /// In en, this message translates to:
  /// **'Message copied to clipboard.'**
  String get messageCopied;

  /// Error when trying to report own message
  ///
  /// In en, this message translates to:
  /// **'You cannot report your own messages.'**
  String get cannotReportOwnMessage;

  /// Report message dialog title
  ///
  /// In en, this message translates to:
  /// **'Report Message'**
  String get reportMessage;

  /// Report message confirmation
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to report this message?'**
  String get reportMessageConfirm;

  /// Confirmation after reporting message
  ///
  /// In en, this message translates to:
  /// **'Message reported successfully.'**
  String get messageReported;

  /// After thumbs up/down feedback
  ///
  /// In en, this message translates to:
  /// **'Thank you for your feedback!'**
  String get thankYouFeedback;

  /// Clear chat dialog title
  ///
  /// In en, this message translates to:
  /// **'Clear Chat?'**
  String get clearChat;

  /// Clear chat confirmation message
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to clear the chat? This action cannot be undone.'**
  String get clearChatConfirm;

  /// Max files upload warning
  ///
  /// In en, this message translates to:
  /// **'You can only upload 4 files at a time'**
  String get maxFilesLimit;

  /// Chat share subject
  ///
  /// In en, this message translates to:
  /// **'Chat with Omi'**
  String get chatWithOmi;

  /// Apps page title
  ///
  /// In en, this message translates to:
  /// **'Apps'**
  String get apps;

  /// Empty state when no apps match
  ///
  /// In en, this message translates to:
  /// **'No apps found'**
  String get noAppsFound;

  /// Hint when no apps found
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search or filters'**
  String get tryAdjustingSearch;

  /// Create app button title
  ///
  /// In en, this message translates to:
  /// **'Create Your Own App'**
  String get createYourOwnApp;

  /// Create app button subtitle
  ///
  /// In en, this message translates to:
  /// **'Build and share your custom app'**
  String get buildAndShareApp;

  /// Apps search placeholder
  ///
  /// In en, this message translates to:
  /// **'Search 1500+ Apps'**
  String get searchApps;

  /// My Apps filter button
  ///
  /// In en, this message translates to:
  /// **'My Apps'**
  String get myApps;

  /// Installed Apps filter button
  ///
  /// In en, this message translates to:
  /// **'Installed Apps'**
  String get installedApps;

  /// Error when apps fail to load
  ///
  /// In en, this message translates to:
  /// **'Unable to fetch apps :(\n\nPlease check your internet connection and try again.'**
  String get unableToFetchApps;

  /// About page title
  ///
  /// In en, this message translates to:
  /// **'About Omi'**
  String get aboutOmi;

  /// Privacy policy link
  ///
  /// In en, this message translates to:
  /// **'Privacy Policy'**
  String get privacyPolicy;

  /// Visit website link
  ///
  /// In en, this message translates to:
  /// **'Visit Website'**
  String get visitWebsite;

  /// Help link title
  ///
  /// In en, this message translates to:
  /// **'Help or Inquiries?'**
  String get helpOrInquiries;

  /// Discord community link
  ///
  /// In en, this message translates to:
  /// **'Join the community!'**
  String get joinCommunity;

  /// Discord member count
  ///
  /// In en, this message translates to:
  /// **'8000+ members and counting.'**
  String get membersAndCounting;

  /// Delete account page title
  ///
  /// In en, this message translates to:
  /// **'Delete Account'**
  String get deleteAccountTitle;

  /// Delete account confirmation
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete your account?'**
  String get deleteAccountConfirm;

  /// Warning that action is permanent
  ///
  /// In en, this message translates to:
  /// **'This cannot be undone.'**
  String get cannotBeUndone;

  /// Delete account warning 1
  ///
  /// In en, this message translates to:
  /// **'All of your memories and conversations will be permanently erased.'**
  String get allDataErased;

  /// Delete account warning 2
  ///
  /// In en, this message translates to:
  /// **'Your Apps and Integrations will be disconnected effectively immediately.'**
  String get appsDisconnected;

  /// Delete account warning 3
  ///
  /// In en, this message translates to:
  /// **'You can export your data before deleting your account, but once deleted, it cannot be recovered.'**
  String get exportBeforeDelete;

  /// Delete account checkbox confirmation
  ///
  /// In en, this message translates to:
  /// **'I understand that deleting my account is permanent and all data, including memories and conversations, will be lost and cannot be recovered.'**
  String get deleteAccountCheckbox;

  /// Final confirmation title
  ///
  /// In en, this message translates to:
  /// **'Are you sure?'**
  String get areYouSure;

  /// Final delete confirmation message
  ///
  /// In en, this message translates to:
  /// **'This action is irreversible and will permanently delete your account and all associated data. Are you sure you want to proceed?'**
  String get deleteAccountFinal;

  /// Delete now button
  ///
  /// In en, this message translates to:
  /// **'Delete Now'**
  String get deleteNow;

  /// Go back button
  ///
  /// In en, this message translates to:
  /// **'Go Back'**
  String get goBack;

  /// Checkbox validation error
  ///
  /// In en, this message translates to:
  /// **'Check the box to confirm you understand that deleting your account is permanent and irreversible.'**
  String get checkBoxToConfirm;

  /// Profile page title
  ///
  /// In en, this message translates to:
  /// **'Profile'**
  String get profile;

  /// Name field label
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get name;

  /// Email field label
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get email;

  /// Custom vocabulary setting
  ///
  /// In en, this message translates to:
  /// **'Custom Vocabulary'**
  String get customVocabulary;

  /// People identification setting
  ///
  /// In en, this message translates to:
  /// **'Identifying Others'**
  String get identifyingOthers;

  /// Payment methods setting
  ///
  /// In en, this message translates to:
  /// **'Payment Methods'**
  String get paymentMethods;

  /// Conversation display setting
  ///
  /// In en, this message translates to:
  /// **'Conversation Display'**
  String get conversationDisplay;

  /// Data and privacy setting
  ///
  /// In en, this message translates to:
  /// **'Data & Privacy'**
  String get dataPrivacy;

  /// User ID label
  ///
  /// In en, this message translates to:
  /// **'User ID'**
  String get userId;

  /// Default value when not set
  ///
  /// In en, this message translates to:
  /// **'Not set'**
  String get notSet;

  /// Confirmation when user ID is copied
  ///
  /// In en, this message translates to:
  /// **'User ID copied to clipboard'**
  String get userIdCopied;

  /// System language option
  ///
  /// In en, this message translates to:
  /// **'System Default'**
  String get systemDefault;

  /// Plan and usage menu item
  ///
  /// In en, this message translates to:
  /// **'Plan & Usage'**
  String get planAndUsage;

  /// Offline sync menu item
  ///
  /// In en, this message translates to:
  /// **'Offline Sync'**
  String get offlineSync;

  /// Device settings menu item
  ///
  /// In en, this message translates to:
  /// **'Device Settings'**
  String get deviceSettings;

  /// Chat tools menu item
  ///
  /// In en, this message translates to:
  /// **'Chat Tools'**
  String get chatTools;

  /// Feedback menu item
  ///
  /// In en, this message translates to:
  /// **'Feedback / Bug'**
  String get feedbackBug;

  /// Help center menu item
  ///
  /// In en, this message translates to:
  /// **'Help Center'**
  String get helpCenter;

  /// Developer settings menu item
  ///
  /// In en, this message translates to:
  /// **'Developer Settings'**
  String get developerSettings;

  /// Mac app download link
  ///
  /// In en, this message translates to:
  /// **'Get Omi for Mac'**
  String get getOmiForMac;

  /// Referral program menu item
  ///
  /// In en, this message translates to:
  /// **'Referral Program'**
  String get referralProgram;

  /// Sign out button
  ///
  /// In en, this message translates to:
  /// **'Sign Out'**
  String get signOut;

  /// Confirmation when version info is copied
  ///
  /// In en, this message translates to:
  /// **'App and device details copied'**
  String get appAndDeviceCopied;

  /// Wrapped 2025 menu item
  ///
  /// In en, this message translates to:
  /// **'Wrapped 2025'**
  String get wrapped2025;

  /// Data privacy page heading
  ///
  /// In en, this message translates to:
  /// **'Your Privacy, Your Control'**
  String get yourPrivacyYourControl;

  /// Data privacy page introduction
  ///
  /// In en, this message translates to:
  /// **'At Omi, we are committed to protecting your privacy. This page allows you to control how your data is stored and used.'**
  String get privacyIntro;

  /// Learn more link
  ///
  /// In en, this message translates to:
  /// **'Learn more...'**
  String get learnMore;

  /// Data protection section title
  ///
  /// In en, this message translates to:
  /// **'Data Protection Level'**
  String get dataProtectionLevel;

  /// Data protection section description
  ///
  /// In en, this message translates to:
  /// **'Your data is secured by default with strong encryption. Review your settings and future privacy options below.'**
  String get dataProtectionDesc;

  /// App access section title
  ///
  /// In en, this message translates to:
  /// **'App Access'**
  String get appAccess;

  /// App access section description
  ///
  /// In en, this message translates to:
  /// **'The following apps can access your data. Tap on an app to manage its permissions.'**
  String get appAccessDesc;

  /// Empty state for app access
  ///
  /// In en, this message translates to:
  /// **'No installed apps have external access to your data.'**
  String get noAppsExternalAccess;

  /// Device name label
  ///
  /// In en, this message translates to:
  /// **'Device Name'**
  String get deviceName;

  /// Device ID label
  ///
  /// In en, this message translates to:
  /// **'Device ID'**
  String get deviceId;

  /// Firmware label
  ///
  /// In en, this message translates to:
  /// **'Firmware'**
  String get firmware;

  /// SD Card sync label
  ///
  /// In en, this message translates to:
  /// **'SD Card Sync'**
  String get sdCardSync;

  /// Hardware revision label
  ///
  /// In en, this message translates to:
  /// **'Hardware Revision'**
  String get hardwareRevision;

  /// Model number label
  ///
  /// In en, this message translates to:
  /// **'Model Number'**
  String get modelNumber;

  /// Manufacturer label
  ///
  /// In en, this message translates to:
  /// **'Manufacturer'**
  String get manufacturer;

  /// Double tap action label
  ///
  /// In en, this message translates to:
  /// **'Double Tap'**
  String get doubleTap;

  /// LED brightness setting
  ///
  /// In en, this message translates to:
  /// **'LED Brightness'**
  String get ledBrightness;

  /// Microphone gain setting
  ///
  /// In en, this message translates to:
  /// **'Mic Gain'**
  String get micGain;

  /// Disconnect device button
  ///
  /// In en, this message translates to:
  /// **'Disconnect'**
  String get disconnect;

  /// Forget device button
  ///
  /// In en, this message translates to:
  /// **'Forget Device'**
  String get forgetDevice;

  /// Charging issues help item
  ///
  /// In en, this message translates to:
  /// **'Charging Issues'**
  String get chargingIssues;

  /// Disconnect device button
  ///
  /// In en, this message translates to:
  /// **'Disconnect Device'**
  String get disconnectDevice;

  /// Unpair device button
  ///
  /// In en, this message translates to:
  /// **'Unpair Device'**
  String get unpairDevice;

  /// Unpair and forget device button
  ///
  /// In en, this message translates to:
  /// **'Unpair and Forget Device'**
  String get unpairAndForget;

  /// Message shown when device is disconnected
  ///
  /// In en, this message translates to:
  /// **'Your Omi has been disconnected 😔'**
  String get deviceDisconnectedMessage;

  /// Message shown when device is unpaired
  ///
  /// In en, this message translates to:
  /// **'Device unpaired. Go to Settings > Bluetooth and forget the device to complete unpairing.'**
  String get deviceUnpairedMessage;

  /// Unpair dialog title
  ///
  /// In en, this message translates to:
  /// **'Unpair Device'**
  String get unpairDialogTitle;

  /// Unpair dialog message
  ///
  /// In en, this message translates to:
  /// **'This will unpair the device so it can be connected to another phone. You will need to go to Settings > Bluetooth and forget the device to complete the process.'**
  String get unpairDialogMessage;

  /// Device not connected header
  ///
  /// In en, this message translates to:
  /// **'Device Not Connected'**
  String get deviceNotConnected;

  /// Message encouraging user to connect device
  ///
  /// In en, this message translates to:
  /// **'Connect your Omi device to access\ndevice settings and customization'**
  String get connectDeviceMessage;

  /// Device information section header
  ///
  /// In en, this message translates to:
  /// **'Device Information'**
  String get deviceInfoSection;

  /// Customization section header
  ///
  /// In en, this message translates to:
  /// **'Customization'**
  String get customizationSection;

  /// Hardware section header
  ///
  /// In en, this message translates to:
  /// **'Hardware'**
  String get hardwareSection;

  /// V2 device undeteced dialog title
  ///
  /// In en, this message translates to:
  /// **'V2 undetected'**
  String get v2Undetected;

  /// V2 device undeteced dialog message
  ///
  /// In en, this message translates to:
  /// **'We see that you either have a V1 device or your device is not connected. SD Card functionality is available only for V2 devices.'**
  String get v2UndetectedMessage;

  /// End conversation action
  ///
  /// In en, this message translates to:
  /// **'End Conversation'**
  String get endConversation;

  /// Pause/Resume action
  ///
  /// In en, this message translates to:
  /// **'Pause/Resume'**
  String get pauseResume;

  /// Star conversation action
  ///
  /// In en, this message translates to:
  /// **'Star Conversation'**
  String get starConversation;

  /// Double tap action setting
  ///
  /// In en, this message translates to:
  /// **'Double Tap Action'**
  String get doubleTapAction;

  /// Double tap action description
  ///
  /// In en, this message translates to:
  /// **'Choose what happens when you double tap'**
  String get doubleTapActionDesc;

  /// End and process action
  ///
  /// In en, this message translates to:
  /// **'End & Process Conversation'**
  String get endAndProcess;

  /// Pause/Resume recording action
  ///
  /// In en, this message translates to:
  /// **'Pause/Resume Recording'**
  String get pauseResumeRecording;

  /// Star ongoing conversation action
  ///
  /// In en, this message translates to:
  /// **'Star Ongoing Conversation'**
  String get starOngoing;

  /// Star ongoing conversation description
  ///
  /// In en, this message translates to:
  /// **'Mark to star when conversation ends'**
  String get starOngoingDesc;

  /// Off state
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get off;

  /// Max state
  ///
  /// In en, this message translates to:
  /// **'Max'**
  String get max;

  /// Mute state
  ///
  /// In en, this message translates to:
  /// **'Mute'**
  String get mute;

  /// Quiet preset
  ///
  /// In en, this message translates to:
  /// **'Quiet'**
  String get quiet;

  /// Normal preset
  ///
  /// In en, this message translates to:
  /// **'Normal'**
  String get normal;

  /// High preset
  ///
  /// In en, this message translates to:
  /// **'High'**
  String get high;

  /// Mic gain description: Muted
  ///
  /// In en, this message translates to:
  /// **'Microphone is muted'**
  String get micGainDescMuted;

  /// Mic gain description: Low
  ///
  /// In en, this message translates to:
  /// **'Very quiet - for loud environments'**
  String get micGainDescLow;

  /// Mic gain description: Moderate
  ///
  /// In en, this message translates to:
  /// **'Quiet - for moderate noise'**
  String get micGainDescModerate;

  /// Mic gain description: Neutral
  ///
  /// In en, this message translates to:
  /// **'Neutral - balanced recording'**
  String get micGainDescNeutral;

  /// Mic gain description: Slightly Boosted
  ///
  /// In en, this message translates to:
  /// **'Slightly boosted - normal use'**
  String get micGainDescSlightlyBoosted;

  /// Mic gain description: Boosted
  ///
  /// In en, this message translates to:
  /// **'Boosted - for quiet environments'**
  String get micGainDescBoosted;

  /// Mic gain description: High
  ///
  /// In en, this message translates to:
  /// **'High - for distant or soft voices'**
  String get micGainDescHigh;

  /// Mic gain description: Very High
  ///
  /// In en, this message translates to:
  /// **'Very high - for very quiet sources'**
  String get micGainDescVeryHigh;

  /// Mic gain description: Max
  ///
  /// In en, this message translates to:
  /// **'Maximum - use with caution'**
  String get micGainDescMax;

  /// Developer settings page title
  ///
  /// In en, this message translates to:
  /// **'Developer Settings'**
  String get developerSettingsTitle;

  /// Saving state text
  ///
  /// In en, this message translates to:
  /// **'Saving...'**
  String get saving;

  /// Persona configuration subtitle
  ///
  /// In en, this message translates to:
  /// **'Configure your AI persona'**
  String get personaConfig;

  /// Beta tag
  ///
  /// In en, this message translates to:
  /// **'BETA'**
  String get beta;

  /// Transcription settings title
  ///
  /// In en, this message translates to:
  /// **'Transcription'**
  String get transcription;

  /// Transcription configuration subtitle
  ///
  /// In en, this message translates to:
  /// **'Configure STT provider'**
  String get transcriptionConfig;

  /// Conversation timeout settings title
  ///
  /// In en, this message translates to:
  /// **'Conversation Timeout'**
  String get conversationTimeout;

  /// Conversation timeout configuration subtitle
  ///
  /// In en, this message translates to:
  /// **'Set when conversations auto-end'**
  String get conversationTimeoutConfig;

  /// Import data details title
  ///
  /// In en, this message translates to:
  /// **'Import Data'**
  String get importData;

  /// Import data details subtitle
  ///
  /// In en, this message translates to:
  /// **'Import data from other sources'**
  String get importDataConfig;

  /// Debug & Diagnostics section header
  ///
  /// In en, this message translates to:
  /// **'Debug & Diagnostics'**
  String get debugDiagnostics;

  /// Endpoint URL label
  ///
  /// In en, this message translates to:
  /// **'Endpoint URL'**
  String get endpointUrl;

  /// No API keys message
  ///
  /// In en, this message translates to:
  /// **'No API keys yet'**
  String get noApiKeys;

  /// Create key instruction
  ///
  /// In en, this message translates to:
  /// **'Create a key to get started'**
  String get createKeyToStart;

  /// Create Key button
  ///
  /// In en, this message translates to:
  /// **'Create Key'**
  String get createKey;

  /// Documentation link
  ///
  /// In en, this message translates to:
  /// **'Docs'**
  String get docs;

  /// Usage page title
  ///
  /// In en, this message translates to:
  /// **'Your Omi Insights'**
  String get yourOmiInsights;

  /// Time period: Today
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get today;

  /// Time period: This Month
  ///
  /// In en, this message translates to:
  /// **'This Month'**
  String get thisMonth;

  /// Time period: This Year
  ///
  /// In en, this message translates to:
  /// **'This Year'**
  String get thisYear;

  /// Time period: All Time
  ///
  /// In en, this message translates to:
  /// **'All Time'**
  String get allTime;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No Activity Yet'**
  String get noActivityYet;

  /// Empty state description
  ///
  /// In en, this message translates to:
  /// **'Start a conversation with Omi\nto see your usage insights here.'**
  String get startConversationToSeeInsights;

  /// Listening stat title
  ///
  /// In en, this message translates to:
  /// **'Listening'**
  String get listening;

  /// Listening stat subtitle
  ///
  /// In en, this message translates to:
  /// **'Total time Omi has actively listened.'**
  String get listeningSubtitle;

  /// Understanding stat title
  ///
  /// In en, this message translates to:
  /// **'Understanding'**
  String get understanding;

  /// Understanding stat subtitle
  ///
  /// In en, this message translates to:
  /// **'Words understood from your conversations.'**
  String get understandingSubtitle;

  /// Providing stat title
  ///
  /// In en, this message translates to:
  /// **'Providing'**
  String get providing;

  /// Providing stat subtitle
  ///
  /// In en, this message translates to:
  /// **'Action items, and notes automatically captured.'**
  String get providingSubtitle;

  /// Remembering stat title
  ///
  /// In en, this message translates to:
  /// **'Remembering'**
  String get remembering;

  /// Remembering stat subtitle
  ///
  /// In en, this message translates to:
  /// **'Facts and details remembered for you.'**
  String get rememberingSubtitle;

  /// Unlimited plan name
  ///
  /// In en, this message translates to:
  /// **'Unlimited Plan'**
  String get unlimitedPlan;

  /// Manage plan button
  ///
  /// In en, this message translates to:
  /// **'Manage Plan'**
  String get managePlan;

  /// Cancellation message
  ///
  /// In en, this message translates to:
  /// **'Your plan will cancel on {date}.'**
  String cancelAtPeriodEnd(String date);

  /// Renewal message
  ///
  /// In en, this message translates to:
  /// **'Your plan renews on {date}.'**
  String renewsOn(String date);

  /// Basic plan name
  ///
  /// In en, this message translates to:
  /// **'Basic Plan'**
  String get basicPlan;

  /// Usage limit message
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} mins used'**
  String usageLimitMessage(String used, int limit);

  /// Upgrade button
  ///
  /// In en, this message translates to:
  /// **'Upgrade'**
  String get upgrade;

  /// Upgrade to unlimited button
  ///
  /// In en, this message translates to:
  /// **'Upgrade to Unlimited'**
  String get upgradeToUnlimited;

  /// Basic plan description
  ///
  /// In en, this message translates to:
  /// **'Your plan includes {limit} free minutes per month. Upgrade to go unlimited.'**
  String basicPlanDesc(int limit);

  /// Share stats base message
  ///
  /// In en, this message translates to:
  /// **'Sharing my Omi stats! (omi.me - your always-on AI assistant)'**
  String get shareStatsMessage;

  /// Share stats period: Today
  ///
  /// In en, this message translates to:
  /// **'Today, omi has:'**
  String get sharePeriodToday;

  /// Share stats period: Month
  ///
  /// In en, this message translates to:
  /// **'This month, omi has:'**
  String get sharePeriodMonth;

  /// Share stats period: Year
  ///
  /// In en, this message translates to:
  /// **'This year, omi has:'**
  String get sharePeriodYear;

  /// Share stats period: All Time
  ///
  /// In en, this message translates to:
  /// **'So far, omi has:'**
  String get sharePeriodAllTime;

  /// Share stats: listened
  ///
  /// In en, this message translates to:
  /// **'🎧 Listened for {minutes} minutes'**
  String shareStatsListened(String minutes);

  /// Share stats: words
  ///
  /// In en, this message translates to:
  /// **'🧠 Understood {words} words'**
  String shareStatsWords(String words);

  /// Share stats: insights
  ///
  /// In en, this message translates to:
  /// **'✨ Provided {count} insights'**
  String shareStatsInsights(String count);

  /// Share stats: memories
  ///
  /// In en, this message translates to:
  /// **'📚 Remembered {count} memories'**
  String shareStatsMemories(String count);

  /// No description provided for @debugLogs.
  ///
  /// In en, this message translates to:
  /// **'Debug Logs'**
  String get debugLogs;

  /// No description provided for @debugLogsAutoDelete.
  ///
  /// In en, this message translates to:
  /// **'Auto-deletes after 3 days.'**
  String get debugLogsAutoDelete;

  /// No description provided for @debugLogsDesc.
  ///
  /// In en, this message translates to:
  /// **'Helps diagnose issues'**
  String get debugLogsDesc;

  /// No description provided for @noLogFilesFound.
  ///
  /// In en, this message translates to:
  /// **'No log files found.'**
  String get noLogFilesFound;

  /// No description provided for @omiDebugLog.
  ///
  /// In en, this message translates to:
  /// **'Omi debug log'**
  String get omiDebugLog;

  /// No description provided for @logShared.
  ///
  /// In en, this message translates to:
  /// **'Log shared'**
  String get logShared;

  /// No description provided for @selectLogFile.
  ///
  /// In en, this message translates to:
  /// **'Select Log File'**
  String get selectLogFile;

  /// No description provided for @shareLogs.
  ///
  /// In en, this message translates to:
  /// **'Share Logs'**
  String get shareLogs;

  /// No description provided for @debugLogCleared.
  ///
  /// In en, this message translates to:
  /// **'Debug log cleared'**
  String get debugLogCleared;

  /// No description provided for @clear.
  ///
  /// In en, this message translates to:
  /// **'Clear'**
  String get clear;

  /// No description provided for @exportStarted.
  ///
  /// In en, this message translates to:
  /// **'Export started. This may take a few seconds...'**
  String get exportStarted;

  /// No description provided for @exportAllData.
  ///
  /// In en, this message translates to:
  /// **'Export All Data'**
  String get exportAllData;

  /// No description provided for @exportDataDesc.
  ///
  /// In en, this message translates to:
  /// **'Export conversations to a JSON file'**
  String get exportDataDesc;

  /// No description provided for @exportedConversations.
  ///
  /// In en, this message translates to:
  /// **'Exported Conversations from Omi'**
  String get exportedConversations;

  /// No description provided for @exportShared.
  ///
  /// In en, this message translates to:
  /// **'Export shared'**
  String get exportShared;

  /// No description provided for @deleteKnowledgeGraphTitle.
  ///
  /// In en, this message translates to:
  /// **'Delete Knowledge Graph?'**
  String get deleteKnowledgeGraphTitle;

  /// No description provided for @deleteKnowledgeGraphMessage.
  ///
  /// In en, this message translates to:
  /// **'This will delete all derived knowledge graph data (nodes and connections). Your original memories will remain safe. The graph will be rebuilt over time or upon next request.'**
  String get deleteKnowledgeGraphMessage;

  /// No description provided for @knowledgeGraphDeleted.
  ///
  /// In en, this message translates to:
  /// **'Knowledge Graph deleted successfully'**
  String get knowledgeGraphDeleted;

  /// Error message when deleting graph fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete graph: {error}'**
  String deleteGraphFailed(String error);

  /// No description provided for @deleteKnowledgeGraph.
  ///
  /// In en, this message translates to:
  /// **'Delete Knowledge Graph'**
  String get deleteKnowledgeGraph;

  /// No description provided for @deleteKnowledgeGraphDesc.
  ///
  /// In en, this message translates to:
  /// **'Clear all nodes and connections'**
  String get deleteKnowledgeGraphDesc;

  /// No description provided for @mcp.
  ///
  /// In en, this message translates to:
  /// **'MCP'**
  String get mcp;

  /// No description provided for @mcpServer.
  ///
  /// In en, this message translates to:
  /// **'MCP Server'**
  String get mcpServer;

  /// No description provided for @mcpServerDesc.
  ///
  /// In en, this message translates to:
  /// **'Connect AI assistants to your data'**
  String get mcpServerDesc;

  /// No description provided for @serverUrl.
  ///
  /// In en, this message translates to:
  /// **'Server URL'**
  String get serverUrl;

  /// No description provided for @urlCopied.
  ///
  /// In en, this message translates to:
  /// **'URL copied'**
  String get urlCopied;

  /// No description provided for @apiKeyAuth.
  ///
  /// In en, this message translates to:
  /// **'API Key Auth'**
  String get apiKeyAuth;

  /// No description provided for @header.
  ///
  /// In en, this message translates to:
  /// **'Header'**
  String get header;

  /// No description provided for @authorizationBearer.
  ///
  /// In en, this message translates to:
  /// **'Authorization: Bearer <key>'**
  String get authorizationBearer;

  /// No description provided for @oauth.
  ///
  /// In en, this message translates to:
  /// **'OAuth'**
  String get oauth;

  /// No description provided for @clientId.
  ///
  /// In en, this message translates to:
  /// **'Client ID'**
  String get clientId;

  /// No description provided for @clientSecret.
  ///
  /// In en, this message translates to:
  /// **'Client Secret'**
  String get clientSecret;

  /// No description provided for @useMcpApiKey.
  ///
  /// In en, this message translates to:
  /// **'Use your MCP API key'**
  String get useMcpApiKey;

  /// No description provided for @webhooks.
  ///
  /// In en, this message translates to:
  /// **'Webhooks'**
  String get webhooks;

  /// No description provided for @conversationEvents.
  ///
  /// In en, this message translates to:
  /// **'Conversation Events'**
  String get conversationEvents;

  /// No description provided for @newConversationCreated.
  ///
  /// In en, this message translates to:
  /// **'New conversation created'**
  String get newConversationCreated;

  /// No description provided for @realtimeTranscript.
  ///
  /// In en, this message translates to:
  /// **'Real-time Transcript'**
  String get realtimeTranscript;

  /// No description provided for @transcriptReceived.
  ///
  /// In en, this message translates to:
  /// **'Transcript received'**
  String get transcriptReceived;

  /// No description provided for @audioBytes.
  ///
  /// In en, this message translates to:
  /// **'Audio Bytes'**
  String get audioBytes;

  /// No description provided for @audioDataReceived.
  ///
  /// In en, this message translates to:
  /// **'Audio data received'**
  String get audioDataReceived;

  /// No description provided for @intervalSeconds.
  ///
  /// In en, this message translates to:
  /// **'Interval (seconds)'**
  String get intervalSeconds;

  /// No description provided for @daySummary.
  ///
  /// In en, this message translates to:
  /// **'Day Summary'**
  String get daySummary;

  /// No description provided for @summaryGenerated.
  ///
  /// In en, this message translates to:
  /// **'Summary generated'**
  String get summaryGenerated;

  /// No description provided for @claudeDesktop.
  ///
  /// In en, this message translates to:
  /// **'Claude Desktop'**
  String get claudeDesktop;

  /// No description provided for @addToClaudeConfig.
  ///
  /// In en, this message translates to:
  /// **'Add to claude_desktop_config.json'**
  String get addToClaudeConfig;

  /// No description provided for @copyConfig.
  ///
  /// In en, this message translates to:
  /// **'Copy Config'**
  String get copyConfig;

  /// No description provided for @configCopied.
  ///
  /// In en, this message translates to:
  /// **'Config copied to clipboard'**
  String get configCopied;

  /// No description provided for @listeningMins.
  ///
  /// In en, this message translates to:
  /// **'Listening (mins)'**
  String get listeningMins;

  /// No description provided for @understandingWords.
  ///
  /// In en, this message translates to:
  /// **'Understanding (words)'**
  String get understandingWords;

  /// No description provided for @insights.
  ///
  /// In en, this message translates to:
  /// **'Insights'**
  String get insights;

  /// No description provided for @memories.
  ///
  /// In en, this message translates to:
  /// **'Memories'**
  String get memories;

  /// No description provided for @minsUsedThisMonth.
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} min used this month'**
  String minsUsedThisMonth(String used, int limit);

  /// No description provided for @wordsUsedThisMonth.
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} words used this month'**
  String wordsUsedThisMonth(String used, String limit);

  /// No description provided for @insightsUsedThisMonth.
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} insights gained this month'**
  String insightsUsedThisMonth(String used, String limit);

  /// No description provided for @memoriesUsedThisMonth.
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} memories created this month'**
  String memoriesUsedThisMonth(String used, String limit);
}

class _AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) => <String>['en', 'ja'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'ja':
      return AppLocalizationsJa();
  }

  throw FlutterError('AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
