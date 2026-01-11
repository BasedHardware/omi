import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_de.dart';
import 'app_localizations_en.dart';
import 'app_localizations_es.dart';
import 'app_localizations_hi.dart';
import 'app_localizations_ja.dart';
import 'app_localizations_pt.dart';
import 'app_localizations_zh.dart';

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
  static const List<Locale> supportedLocales = <Locale>[
    Locale('de'),
    Locale('en'),
    Locale('es'),
    Locale('hi'),
    Locale('ja'),
    Locale('pt'),
    Locale('zh')
  ];

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

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// Generic OK button text
  ///
  /// In en, this message translates to:
  /// **'Ok'**
  String get ok;

  /// Button label
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

  /// Save button label
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

  /// Clear button label
  ///
  /// In en, this message translates to:
  /// **'Clear'**
  String get clear;

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

  /// Speech profile label
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

  /// Language setting label
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get language;

  /// Title for language selection
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

  /// Button label
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

  /// Link text for Privacy Policy
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
  /// **'Free Plan'**
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

  /// No description provided for @visibility.
  ///
  /// In en, this message translates to:
  /// **'Visibility'**
  String get visibility;

  /// No description provided for @visibilitySubtitle.
  ///
  /// In en, this message translates to:
  /// **'Control which conversations appear in your list'**
  String get visibilitySubtitle;

  /// No description provided for @showShortConversations.
  ///
  /// In en, this message translates to:
  /// **'Show Short Conversations'**
  String get showShortConversations;

  /// No description provided for @showShortConversationsDesc.
  ///
  /// In en, this message translates to:
  /// **'Display conversations shorter than the threshold'**
  String get showShortConversationsDesc;

  /// No description provided for @showDiscardedConversations.
  ///
  /// In en, this message translates to:
  /// **'Show Discarded Conversations'**
  String get showDiscardedConversations;

  /// No description provided for @showDiscardedConversationsDesc.
  ///
  /// In en, this message translates to:
  /// **'Include conversations marked as discarded'**
  String get showDiscardedConversationsDesc;

  /// No description provided for @shortConversationThreshold.
  ///
  /// In en, this message translates to:
  /// **'Short Conversation Threshold'**
  String get shortConversationThreshold;

  /// No description provided for @shortConversationThresholdSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Conversations shorter than this will be hidden unless enabled above'**
  String get shortConversationThresholdSubtitle;

  /// No description provided for @durationThreshold.
  ///
  /// In en, this message translates to:
  /// **'Duration Threshold'**
  String get durationThreshold;

  /// No description provided for @durationThresholdDesc.
  ///
  /// In en, this message translates to:
  /// **'Hide conversations shorter than this'**
  String get durationThresholdDesc;

  /// No description provided for @minLabel.
  ///
  /// In en, this message translates to:
  /// **'{count} min'**
  String minLabel(int count);

  /// No description provided for @customVocabularyTitle.
  ///
  /// In en, this message translates to:
  /// **'Custom Vocabulary'**
  String get customVocabularyTitle;

  /// No description provided for @addWords.
  ///
  /// In en, this message translates to:
  /// **'Add Words'**
  String get addWords;

  /// No description provided for @addWordsDesc.
  ///
  /// In en, this message translates to:
  /// **'Names, terms, or uncommon words'**
  String get addWordsDesc;

  /// No description provided for @vocabularyHint.
  ///
  /// In en, this message translates to:
  /// **'Omi, Callie, OpenAI'**
  String get vocabularyHint;

  /// Title for device connection page
  ///
  /// In en, this message translates to:
  /// **'Connect'**
  String get connect;

  /// No description provided for @comingSoon.
  ///
  /// In en, this message translates to:
  /// **'Coming Soon'**
  String get comingSoon;

  /// No description provided for @chatToolsFooter.
  ///
  /// In en, this message translates to:
  /// **'Connect your apps to view data and metrics in chat.'**
  String get chatToolsFooter;

  /// No description provided for @completeAuthInBrowser.
  ///
  /// In en, this message translates to:
  /// **'Please complete authentication in your browser. Once done, return to the app.'**
  String get completeAuthInBrowser;

  /// No description provided for @failedToStartAuth.
  ///
  /// In en, this message translates to:
  /// **'Failed to start {appName} authentication'**
  String failedToStartAuth(String appName);

  /// No description provided for @disconnectAppTitle.
  ///
  /// In en, this message translates to:
  /// **'Disconnect {appName}?'**
  String disconnectAppTitle(String appName);

  /// No description provided for @disconnectAppMessage.
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to disconnect from {appName}? You can reconnect anytime.'**
  String disconnectAppMessage(String appName);

  /// No description provided for @disconnectedFrom.
  ///
  /// In en, this message translates to:
  /// **'Disconnected from {appName}'**
  String disconnectedFrom(String appName);

  /// No description provided for @failedToDisconnect.
  ///
  /// In en, this message translates to:
  /// **'Failed to disconnect'**
  String get failedToDisconnect;

  /// No description provided for @connectTo.
  ///
  /// In en, this message translates to:
  /// **'Connect to {appName}'**
  String connectTo(String appName);

  /// No description provided for @authAccessMessage.
  ///
  /// In en, this message translates to:
  /// **'You\'ll need to authorize Omi to access your {appName} data. This will open your browser for authentication.'**
  String authAccessMessage(String appName);

  /// No description provided for @continueAction.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get continueAction;

  /// No description provided for @languageTitle.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get languageTitle;

  /// No description provided for @primaryLanguage.
  ///
  /// In en, this message translates to:
  /// **'Primary Language'**
  String get primaryLanguage;

  /// No description provided for @automaticTranslation.
  ///
  /// In en, this message translates to:
  /// **'Automatic Translation'**
  String get automaticTranslation;

  /// No description provided for @detectLanguages.
  ///
  /// In en, this message translates to:
  /// **'Detect 10+ languages'**
  String get detectLanguages;

  /// No description provided for @authorizeSavingRecordings.
  ///
  /// In en, this message translates to:
  /// **'Authorize Saving Recordings'**
  String get authorizeSavingRecordings;

  /// No description provided for @thanksForAuthorizing.
  ///
  /// In en, this message translates to:
  /// **'Thanks for authorizing!'**
  String get thanksForAuthorizing;

  /// No description provided for @needYourPermission.
  ///
  /// In en, this message translates to:
  /// **'We need your permission'**
  String get needYourPermission;

  /// No description provided for @alreadyGavePermission.
  ///
  /// In en, this message translates to:
  /// **'You\'ve already given us permission to save your recordings. Here\'s a reminder of why we need it:'**
  String get alreadyGavePermission;

  /// No description provided for @wouldLikePermission.
  ///
  /// In en, this message translates to:
  /// **'We\'d like your permission to save your voice recordings. Here\'s why:'**
  String get wouldLikePermission;

  /// No description provided for @improveSpeechProfile.
  ///
  /// In en, this message translates to:
  /// **'Improve Your Speech Profile'**
  String get improveSpeechProfile;

  /// No description provided for @improveSpeechProfileDesc.
  ///
  /// In en, this message translates to:
  /// **'We use recordings to further train and enhance your personal speech profile.'**
  String get improveSpeechProfileDesc;

  /// No description provided for @trainFamilyProfiles.
  ///
  /// In en, this message translates to:
  /// **'Train Profiles for Friends and Family'**
  String get trainFamilyProfiles;

  /// No description provided for @trainFamilyProfilesDesc.
  ///
  /// In en, this message translates to:
  /// **'Your recordings help us recognize and create profiles for your friends and family.'**
  String get trainFamilyProfilesDesc;

  /// No description provided for @enhanceTranscriptAccuracy.
  ///
  /// In en, this message translates to:
  /// **'Enhance Transcript Accuracy'**
  String get enhanceTranscriptAccuracy;

  /// No description provided for @enhanceTranscriptAccuracyDesc.
  ///
  /// In en, this message translates to:
  /// **'As our model improves, we can provide better transcription results for your recordings.'**
  String get enhanceTranscriptAccuracyDesc;

  /// No description provided for @legalNotice.
  ///
  /// In en, this message translates to:
  /// **'Legal Notice: The legality of recording and storing voice data may vary depending on your location and how you use this feature. It\'s your responsibility to ensure compliance with local laws and regulations.'**
  String get legalNotice;

  /// No description provided for @alreadyAuthorized.
  ///
  /// In en, this message translates to:
  /// **'Already Authorized'**
  String get alreadyAuthorized;

  /// No description provided for @authorize.
  ///
  /// In en, this message translates to:
  /// **'Authorize'**
  String get authorize;

  /// No description provided for @revokeAuthorization.
  ///
  /// In en, this message translates to:
  /// **'Revoke Authorization'**
  String get revokeAuthorization;

  /// No description provided for @authorizationSuccessful.
  ///
  /// In en, this message translates to:
  /// **'Authorization successful!'**
  String get authorizationSuccessful;

  /// No description provided for @failedToAuthorize.
  ///
  /// In en, this message translates to:
  /// **'Failed to authorize. Please try again.'**
  String get failedToAuthorize;

  /// No description provided for @authorizationRevoked.
  ///
  /// In en, this message translates to:
  /// **'Authorization revoked.'**
  String get authorizationRevoked;

  /// No description provided for @recordingsDeleted.
  ///
  /// In en, this message translates to:
  /// **'Recordings deleted.'**
  String get recordingsDeleted;

  /// No description provided for @failedToRevoke.
  ///
  /// In en, this message translates to:
  /// **'Failed to revoke authorization. Please try again.'**
  String get failedToRevoke;

  /// No description provided for @permissionRevokedTitle.
  ///
  /// In en, this message translates to:
  /// **'Permission Revoked'**
  String get permissionRevokedTitle;

  /// No description provided for @permissionRevokedMessage.
  ///
  /// In en, this message translates to:
  /// **'Do you want us to remove all your existing recordings too?'**
  String get permissionRevokedMessage;

  /// No description provided for @yes.
  ///
  /// In en, this message translates to:
  /// **'Yes'**
  String get yes;

  /// No description provided for @editName.
  ///
  /// In en, this message translates to:
  /// **'Edit Name'**
  String get editName;

  /// No description provided for @howShouldOmiCallYou.
  ///
  /// In en, this message translates to:
  /// **'How should Omi call you?'**
  String get howShouldOmiCallYou;

  /// Hint text for name input field
  ///
  /// In en, this message translates to:
  /// **'Enter your name'**
  String get enterYourName;

  /// No description provided for @nameCannotBeEmpty.
  ///
  /// In en, this message translates to:
  /// **'Name cannot be empty'**
  String get nameCannotBeEmpty;

  /// No description provided for @nameUpdatedSuccessfully.
  ///
  /// In en, this message translates to:
  /// **'Name updated successfully!'**
  String get nameUpdatedSuccessfully;

  /// No description provided for @calendarSettings.
  ///
  /// In en, this message translates to:
  /// **'Calendar settings'**
  String get calendarSettings;

  /// No description provided for @calendarProviders.
  ///
  /// In en, this message translates to:
  /// **'Calendar Providers'**
  String get calendarProviders;

  /// No description provided for @macOsCalendar.
  ///
  /// In en, this message translates to:
  /// **'macOS Calendar'**
  String get macOsCalendar;

  /// No description provided for @connectMacOsCalendar.
  ///
  /// In en, this message translates to:
  /// **'Connect your local macOS calendar'**
  String get connectMacOsCalendar;

  /// No description provided for @googleCalendar.
  ///
  /// In en, this message translates to:
  /// **'Google Calendar'**
  String get googleCalendar;

  /// No description provided for @syncGoogleAccount.
  ///
  /// In en, this message translates to:
  /// **'Sync with your Google account'**
  String get syncGoogleAccount;

  /// No description provided for @showMeetingsMenuBar.
  ///
  /// In en, this message translates to:
  /// **'Show upcoming meetings in menu bar'**
  String get showMeetingsMenuBar;

  /// No description provided for @showMeetingsMenuBarDesc.
  ///
  /// In en, this message translates to:
  /// **'Display your next meeting and time until it starts in the macOS menu bar'**
  String get showMeetingsMenuBarDesc;

  /// No description provided for @showEventsNoParticipants.
  ///
  /// In en, this message translates to:
  /// **'Show events with no participants'**
  String get showEventsNoParticipants;

  /// No description provided for @showEventsNoParticipantsDesc.
  ///
  /// In en, this message translates to:
  /// **'When enabled, Coming Up shows events without participants or a video link.'**
  String get showEventsNoParticipantsDesc;

  /// No description provided for @yourMeetings.
  ///
  /// In en, this message translates to:
  /// **'Your Meetings'**
  String get yourMeetings;

  /// No description provided for @refresh.
  ///
  /// In en, this message translates to:
  /// **'Refresh'**
  String get refresh;

  /// No description provided for @noUpcomingMeetings.
  ///
  /// In en, this message translates to:
  /// **'No upcoming meetings found'**
  String get noUpcomingMeetings;

  /// No description provided for @checkingNextDays.
  ///
  /// In en, this message translates to:
  /// **'Checking next 30 days'**
  String get checkingNextDays;

  /// No description provided for @tomorrow.
  ///
  /// In en, this message translates to:
  /// **'Tomorrow'**
  String get tomorrow;

  /// No description provided for @googleCalendarComingSoon.
  ///
  /// In en, this message translates to:
  /// **'Google Calendar integration coming soon!'**
  String get googleCalendarComingSoon;

  /// No description provided for @connectedAsUser.
  ///
  /// In en, this message translates to:
  /// **'Connected as user: {userId}'**
  String connectedAsUser(String userId);

  /// No description provided for @defaultWorkspace.
  ///
  /// In en, this message translates to:
  /// **'Default Workspace'**
  String get defaultWorkspace;

  /// No description provided for @tasksCreatedInWorkspace.
  ///
  /// In en, this message translates to:
  /// **'Tasks will be created in this workspace'**
  String get tasksCreatedInWorkspace;

  /// No description provided for @defaultProjectOptional.
  ///
  /// In en, this message translates to:
  /// **'Default Project (Optional)'**
  String get defaultProjectOptional;

  /// No description provided for @leaveUnselectedTasks.
  ///
  /// In en, this message translates to:
  /// **'Leave unselected to create tasks without a project'**
  String get leaveUnselectedTasks;

  /// No description provided for @noProjectsInWorkspace.
  ///
  /// In en, this message translates to:
  /// **'No projects found in this workspace'**
  String get noProjectsInWorkspace;

  /// No description provided for @conversationTimeoutDesc.
  ///
  /// In en, this message translates to:
  /// **'Choose how long to wait in silence before automatically ending a conversation:'**
  String get conversationTimeoutDesc;

  /// No description provided for @timeout2Minutes.
  ///
  /// In en, this message translates to:
  /// **'2 minutes'**
  String get timeout2Minutes;

  /// No description provided for @timeout2MinutesDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 2 minutes of silence'**
  String get timeout2MinutesDesc;

  /// No description provided for @timeout5Minutes.
  ///
  /// In en, this message translates to:
  /// **'5 minutes'**
  String get timeout5Minutes;

  /// No description provided for @timeout5MinutesDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 5 minutes of silence'**
  String get timeout5MinutesDesc;

  /// No description provided for @timeout10Minutes.
  ///
  /// In en, this message translates to:
  /// **'10 minutes'**
  String get timeout10Minutes;

  /// No description provided for @timeout10MinutesDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 10 minutes of silence'**
  String get timeout10MinutesDesc;

  /// No description provided for @timeout30Minutes.
  ///
  /// In en, this message translates to:
  /// **'30 minutes'**
  String get timeout30Minutes;

  /// No description provided for @timeout30MinutesDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 30 minutes of silence'**
  String get timeout30MinutesDesc;

  /// No description provided for @timeout4Hours.
  ///
  /// In en, this message translates to:
  /// **'4 hours'**
  String get timeout4Hours;

  /// No description provided for @timeout4HoursDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 4 hours of silence'**
  String get timeout4HoursDesc;

  /// No description provided for @conversationEndAfterHours.
  ///
  /// In en, this message translates to:
  /// **'Conversations will now end after 4 hours of silence'**
  String get conversationEndAfterHours;

  /// No description provided for @conversationEndAfterMinutes.
  ///
  /// In en, this message translates to:
  /// **'Conversations will now end after {minutes} minute(s) of silence'**
  String conversationEndAfterMinutes(int minutes);

  /// No description provided for @tellUsPrimaryLanguage.
  ///
  /// In en, this message translates to:
  /// **'Tell us your primary language'**
  String get tellUsPrimaryLanguage;

  /// No description provided for @languageForTranscription.
  ///
  /// In en, this message translates to:
  /// **'Set your language for sharper transcriptions and a personalized experience.'**
  String get languageForTranscription;

  /// No description provided for @singleLanguageModeInfo.
  ///
  /// In en, this message translates to:
  /// **'Single Language Mode is enabled. Translation is disabled for higher accuracy.'**
  String get singleLanguageModeInfo;

  /// Hint text for language search
  ///
  /// In en, this message translates to:
  /// **'Search language by name or code'**
  String get searchLanguageHint;

  /// Text when search returns no results
  ///
  /// In en, this message translates to:
  /// **'No languages found'**
  String get noLanguagesFound;

  /// No description provided for @skip.
  ///
  /// In en, this message translates to:
  /// **'Skip'**
  String get skip;

  /// No description provided for @languageSetTo.
  ///
  /// In en, this message translates to:
  /// **'Language set to {language}'**
  String languageSetTo(String language);

  /// No description provided for @failedToSetLanguage.
  ///
  /// In en, this message translates to:
  /// **'Failed to set language'**
  String get failedToSetLanguage;

  /// No description provided for @appSettings.
  ///
  /// In en, this message translates to:
  /// **'{appName} Settings'**
  String appSettings(String appName);

  /// No description provided for @disconnectFromApp.
  ///
  /// In en, this message translates to:
  /// **'Disconnect from {appName}?'**
  String disconnectFromApp(String appName);

  /// No description provided for @disconnectFromAppDesc.
  ///
  /// In en, this message translates to:
  /// **'This will remove your {appName} authentication. You\'ll need to reconnect to use it again.'**
  String disconnectFromAppDesc(String appName);

  /// No description provided for @connectedToApp.
  ///
  /// In en, this message translates to:
  /// **'Connected to {appName}'**
  String connectedToApp(String appName);

  /// No description provided for @account.
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get account;

  /// No description provided for @actionItemsSyncedTo.
  ///
  /// In en, this message translates to:
  /// **'Your action items will be synced to your {appName} account'**
  String actionItemsSyncedTo(String appName);

  /// No description provided for @defaultSpace.
  ///
  /// In en, this message translates to:
  /// **'Default Space'**
  String get defaultSpace;

  /// No description provided for @selectSpaceInWorkspace.
  ///
  /// In en, this message translates to:
  /// **'Select a space in your workspace'**
  String get selectSpaceInWorkspace;

  /// No description provided for @noSpacesInWorkspace.
  ///
  /// In en, this message translates to:
  /// **'No spaces found in this workspace'**
  String get noSpacesInWorkspace;

  /// No description provided for @defaultList.
  ///
  /// In en, this message translates to:
  /// **'Default List'**
  String get defaultList;

  /// No description provided for @tasksAddedToList.
  ///
  /// In en, this message translates to:
  /// **'Tasks will be added to this list'**
  String get tasksAddedToList;

  /// No description provided for @noListsInSpace.
  ///
  /// In en, this message translates to:
  /// **'No lists found in this space'**
  String get noListsInSpace;

  /// No description provided for @failedToLoadRepos.
  ///
  /// In en, this message translates to:
  /// **'Failed to load repositories: {error}'**
  String failedToLoadRepos(String error);

  /// No description provided for @defaultRepoSaved.
  ///
  /// In en, this message translates to:
  /// **'Default repository saved'**
  String get defaultRepoSaved;

  /// No description provided for @failedToSaveDefaultRepo.
  ///
  /// In en, this message translates to:
  /// **'Failed to save default repository'**
  String get failedToSaveDefaultRepo;

  /// No description provided for @defaultRepository.
  ///
  /// In en, this message translates to:
  /// **'Default Repository'**
  String get defaultRepository;

  /// No description provided for @selectDefaultRepoDesc.
  ///
  /// In en, this message translates to:
  /// **'Select a default repository for creating issues. You can still specify a different repository when creating issues.'**
  String get selectDefaultRepoDesc;

  /// No description provided for @noReposFound.
  ///
  /// In en, this message translates to:
  /// **'No repositories found'**
  String get noReposFound;

  /// No description provided for @private.
  ///
  /// In en, this message translates to:
  /// **'Private'**
  String get private;

  /// No description provided for @updatedDate.
  ///
  /// In en, this message translates to:
  /// **'Updated {date}'**
  String updatedDate(String date);

  /// No description provided for @yesterday.
  ///
  /// In en, this message translates to:
  /// **'yesterday'**
  String get yesterday;

  /// No description provided for @daysAgo.
  ///
  /// In en, this message translates to:
  /// **'{count} days ago'**
  String daysAgo(int count);

  /// No description provided for @oneWeekAgo.
  ///
  /// In en, this message translates to:
  /// **'1 week ago'**
  String get oneWeekAgo;

  /// No description provided for @weeksAgo.
  ///
  /// In en, this message translates to:
  /// **'{count} weeks ago'**
  String weeksAgo(int count);

  /// No description provided for @oneMonthAgo.
  ///
  /// In en, this message translates to:
  /// **'1 month ago'**
  String get oneMonthAgo;

  /// No description provided for @monthsAgo.
  ///
  /// In en, this message translates to:
  /// **'{count} months ago'**
  String monthsAgo(int count);

  /// No description provided for @issuesCreatedInRepo.
  ///
  /// In en, this message translates to:
  /// **'Issues will be created in your default repository'**
  String get issuesCreatedInRepo;

  /// No description provided for @taskIntegrations.
  ///
  /// In en, this message translates to:
  /// **'Task Integrations'**
  String get taskIntegrations;

  /// No description provided for @configureSettings.
  ///
  /// In en, this message translates to:
  /// **'Configure Settings'**
  String get configureSettings;

  /// No description provided for @completeAuthBrowser.
  ///
  /// In en, this message translates to:
  /// **'Please complete authentication in your browser. Once done, return to the app.'**
  String get completeAuthBrowser;

  /// No description provided for @failedToStartAppAuth.
  ///
  /// In en, this message translates to:
  /// **'Failed to start {appName} authentication'**
  String failedToStartAppAuth(String appName);

  /// No description provided for @connectToAppTitle.
  ///
  /// In en, this message translates to:
  /// **'Connect to {appName}'**
  String connectToAppTitle(String appName);

  /// No description provided for @authorizeOmiForTasks.
  ///
  /// In en, this message translates to:
  /// **'You\'ll need to authorize Omi to create tasks in your {appName} account. This will open your browser for authentication.'**
  String authorizeOmiForTasks(String appName);

  /// Generic continue button text
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get continueButton;

  /// No description provided for @appIntegration.
  ///
  /// In en, this message translates to:
  /// **'{appName} Integration'**
  String appIntegration(String appName);

  /// No description provided for @integrationComingSoon.
  ///
  /// In en, this message translates to:
  /// **'Integration with {appName} is coming soon! We\'re working hard to bring you more task management options.'**
  String integrationComingSoon(String appName);

  /// Button to dismiss dialog
  ///
  /// In en, this message translates to:
  /// **'Got it'**
  String get gotIt;

  /// No description provided for @tasksExportedOneApp.
  ///
  /// In en, this message translates to:
  /// **'Tasks can be exported to one app at a time.'**
  String get tasksExportedOneApp;

  /// No description provided for @completeYourUpgrade.
  ///
  /// In en, this message translates to:
  /// **'Complete Your Upgrade'**
  String get completeYourUpgrade;

  /// No description provided for @importConfiguration.
  ///
  /// In en, this message translates to:
  /// **'Import Configuration'**
  String get importConfiguration;

  /// No description provided for @exportConfiguration.
  ///
  /// In en, this message translates to:
  /// **'Export configuration'**
  String get exportConfiguration;

  /// No description provided for @bringYourOwn.
  ///
  /// In en, this message translates to:
  /// **'Bring your own'**
  String get bringYourOwn;

  /// No description provided for @payYourSttProvider.
  ///
  /// In en, this message translates to:
  /// **'Freely use omi. You only pay your STT provider directly.'**
  String get payYourSttProvider;

  /// No description provided for @freeMinutesMonth.
  ///
  /// In en, this message translates to:
  /// **'1,200 free minutes/month included. Unlimited with '**
  String get freeMinutesMonth;

  /// No description provided for @omiUnlimited.
  ///
  /// In en, this message translates to:
  /// **'Omi Unlimited'**
  String get omiUnlimited;

  /// No description provided for @hostRequired.
  ///
  /// In en, this message translates to:
  /// **'Host is required'**
  String get hostRequired;

  /// No description provided for @validPortRequired.
  ///
  /// In en, this message translates to:
  /// **'Valid port is required'**
  String get validPortRequired;

  /// No description provided for @validWebsocketUrlRequired.
  ///
  /// In en, this message translates to:
  /// **'Valid WebSocket URL is required (wss://)'**
  String get validWebsocketUrlRequired;

  /// No description provided for @apiUrlRequired.
  ///
  /// In en, this message translates to:
  /// **'API URL is required'**
  String get apiUrlRequired;

  /// No description provided for @apiKeyRequired.
  ///
  /// In en, this message translates to:
  /// **'API key is required'**
  String get apiKeyRequired;

  /// No description provided for @invalidJsonConfig.
  ///
  /// In en, this message translates to:
  /// **'Invalid JSON configuration'**
  String get invalidJsonConfig;

  /// No description provided for @errorSaving.
  ///
  /// In en, this message translates to:
  /// **'Error saving: {error}'**
  String errorSaving(String error);

  /// No description provided for @configCopiedToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Configuration copied to clipboard'**
  String get configCopiedToClipboard;

  /// No description provided for @pasteJsonConfig.
  ///
  /// In en, this message translates to:
  /// **'Paste your JSON configuration below:'**
  String get pasteJsonConfig;

  /// No description provided for @addApiKeyAfterImport.
  ///
  /// In en, this message translates to:
  /// **'You\'ll need to add your own API key after importing'**
  String get addApiKeyAfterImport;

  /// No description provided for @paste.
  ///
  /// In en, this message translates to:
  /// **'Paste'**
  String get paste;

  /// No description provided for @import.
  ///
  /// In en, this message translates to:
  /// **'Import'**
  String get import;

  /// No description provided for @invalidProviderInConfig.
  ///
  /// In en, this message translates to:
  /// **'Invalid provider in configuration'**
  String get invalidProviderInConfig;

  /// No description provided for @importedConfig.
  ///
  /// In en, this message translates to:
  /// **'Imported {providerName} configuration'**
  String importedConfig(String providerName);

  /// No description provided for @invalidJson.
  ///
  /// In en, this message translates to:
  /// **'Invalid JSON: {error}'**
  String invalidJson(String error);

  /// No description provided for @provider.
  ///
  /// In en, this message translates to:
  /// **'Provider'**
  String get provider;

  /// No description provided for @live.
  ///
  /// In en, this message translates to:
  /// **'Live'**
  String get live;

  /// No description provided for @onDevice.
  ///
  /// In en, this message translates to:
  /// **'On Device'**
  String get onDevice;

  /// No description provided for @apiUrl.
  ///
  /// In en, this message translates to:
  /// **'API URL'**
  String get apiUrl;

  /// No description provided for @enterSttHttpEndpoint.
  ///
  /// In en, this message translates to:
  /// **'Enter your STT HTTP endpoint'**
  String get enterSttHttpEndpoint;

  /// No description provided for @websocketUrl.
  ///
  /// In en, this message translates to:
  /// **'WebSocket URL'**
  String get websocketUrl;

  /// No description provided for @enterLiveSttWebsocket.
  ///
  /// In en, this message translates to:
  /// **'Enter your live STT WebSocket endpoint'**
  String get enterLiveSttWebsocket;

  /// No description provided for @apiKey.
  ///
  /// In en, this message translates to:
  /// **'API Key'**
  String get apiKey;

  /// No description provided for @enterApiKey.
  ///
  /// In en, this message translates to:
  /// **'Enter your API key'**
  String get enterApiKey;

  /// No description provided for @storedLocallyNeverShared.
  ///
  /// In en, this message translates to:
  /// **'Stored locally, never shared'**
  String get storedLocallyNeverShared;

  /// No description provided for @host.
  ///
  /// In en, this message translates to:
  /// **'Host'**
  String get host;

  /// No description provided for @port.
  ///
  /// In en, this message translates to:
  /// **'Port'**
  String get port;

  /// No description provided for @advanced.
  ///
  /// In en, this message translates to:
  /// **'Advanced'**
  String get advanced;

  /// No description provided for @configuration.
  ///
  /// In en, this message translates to:
  /// **'Configuration'**
  String get configuration;

  /// No description provided for @requestConfiguration.
  ///
  /// In en, this message translates to:
  /// **'Request Configuration'**
  String get requestConfiguration;

  /// No description provided for @responseSchema.
  ///
  /// In en, this message translates to:
  /// **'Response Schema'**
  String get responseSchema;

  /// No description provided for @modified.
  ///
  /// In en, this message translates to:
  /// **'Modified'**
  String get modified;

  /// No description provided for @resetRequestConfig.
  ///
  /// In en, this message translates to:
  /// **'Reset request config to default'**
  String get resetRequestConfig;

  /// No description provided for @logs.
  ///
  /// In en, this message translates to:
  /// **'Logs'**
  String get logs;

  /// No description provided for @logsCopied.
  ///
  /// In en, this message translates to:
  /// **'Logs copied'**
  String get logsCopied;

  /// No description provided for @noLogsYet.
  ///
  /// In en, this message translates to:
  /// **'No logs yet. Start recording to see custom STT activity.'**
  String get noLogsYet;

  /// No description provided for @deviceUsesCodec.
  ///
  /// In en, this message translates to:
  /// **'{deviceName} uses {codecReason}. Omi will be used.'**
  String deviceUsesCodec(String deviceName, String codecReason);

  /// No description provided for @omiTranscription.
  ///
  /// In en, this message translates to:
  /// **'Omi Transcription'**
  String get omiTranscription;

  /// No description provided for @bestInClassTranscription.
  ///
  /// In en, this message translates to:
  /// **'Best in class transcription with zero setup'**
  String get bestInClassTranscription;

  /// No description provided for @instantSpeakerLabels.
  ///
  /// In en, this message translates to:
  /// **'Instant speaker labels'**
  String get instantSpeakerLabels;

  /// No description provided for @languageTranslation.
  ///
  /// In en, this message translates to:
  /// **'100+ language translation'**
  String get languageTranslation;

  /// No description provided for @optimizedForConversation.
  ///
  /// In en, this message translates to:
  /// **'Optimized for conversation'**
  String get optimizedForConversation;

  /// No description provided for @autoLanguageDetection.
  ///
  /// In en, this message translates to:
  /// **'Auto language detection'**
  String get autoLanguageDetection;

  /// No description provided for @highAccuracy.
  ///
  /// In en, this message translates to:
  /// **'High accuracy'**
  String get highAccuracy;

  /// No description provided for @privacyFirst.
  ///
  /// In en, this message translates to:
  /// **'Privacy first'**
  String get privacyFirst;

  /// No description provided for @saveChanges.
  ///
  /// In en, this message translates to:
  /// **'Save Changes'**
  String get saveChanges;

  /// No description provided for @resetToDefault.
  ///
  /// In en, this message translates to:
  /// **'Reset to Default'**
  String get resetToDefault;

  /// No description provided for @viewTemplate.
  ///
  /// In en, this message translates to:
  /// **'View Template'**
  String get viewTemplate;

  /// No description provided for @trySomethingLike.
  ///
  /// In en, this message translates to:
  /// **'Try something like...'**
  String get trySomethingLike;

  /// No description provided for @tryIt.
  ///
  /// In en, this message translates to:
  /// **'Try it'**
  String get tryIt;

  /// No description provided for @creatingPlan.
  ///
  /// In en, this message translates to:
  /// **'Creating plan'**
  String get creatingPlan;

  /// No description provided for @developingLogic.
  ///
  /// In en, this message translates to:
  /// **'Developing logic'**
  String get developingLogic;

  /// No description provided for @designingApp.
  ///
  /// In en, this message translates to:
  /// **'Designing app'**
  String get designingApp;

  /// No description provided for @generatingIconStep.
  ///
  /// In en, this message translates to:
  /// **'Generating icon'**
  String get generatingIconStep;

  /// No description provided for @finalTouches.
  ///
  /// In en, this message translates to:
  /// **'Final touches'**
  String get finalTouches;

  /// No description provided for @processing.
  ///
  /// In en, this message translates to:
  /// **'Processing...'**
  String get processing;

  /// No description provided for @features.
  ///
  /// In en, this message translates to:
  /// **'Features'**
  String get features;

  /// No description provided for @creatingYourApp.
  ///
  /// In en, this message translates to:
  /// **'Creating your app...'**
  String get creatingYourApp;

  /// No description provided for @generatingIcon.
  ///
  /// In en, this message translates to:
  /// **'Generating icon...'**
  String get generatingIcon;

  /// No description provided for @whatShouldWeMake.
  ///
  /// In en, this message translates to:
  /// **'What should we make?'**
  String get whatShouldWeMake;

  /// No description provided for @appName.
  ///
  /// In en, this message translates to:
  /// **'App Name'**
  String get appName;

  /// No description provided for @description.
  ///
  /// In en, this message translates to:
  /// **'Description'**
  String get description;

  /// No description provided for @publicLabel.
  ///
  /// In en, this message translates to:
  /// **'Public'**
  String get publicLabel;

  /// No description provided for @privateLabel.
  ///
  /// In en, this message translates to:
  /// **'Private'**
  String get privateLabel;

  /// No description provided for @free.
  ///
  /// In en, this message translates to:
  /// **'Free'**
  String get free;

  /// No description provided for @perMonth.
  ///
  /// In en, this message translates to:
  /// **'/ Month'**
  String get perMonth;

  /// No description provided for @tailoredConversationSummaries.
  ///
  /// In en, this message translates to:
  /// **'Tailored Conversation Summaries'**
  String get tailoredConversationSummaries;

  /// No description provided for @customChatbotPersonality.
  ///
  /// In en, this message translates to:
  /// **'Custom Chatbot Personality'**
  String get customChatbotPersonality;

  /// No description provided for @makePublic.
  ///
  /// In en, this message translates to:
  /// **'Make public'**
  String get makePublic;

  /// No description provided for @anyoneCanDiscover.
  ///
  /// In en, this message translates to:
  /// **'Anyone can discover your app'**
  String get anyoneCanDiscover;

  /// No description provided for @onlyYouCanUse.
  ///
  /// In en, this message translates to:
  /// **'Only you can use this app'**
  String get onlyYouCanUse;

  /// No description provided for @paidApp.
  ///
  /// In en, this message translates to:
  /// **'Paid app'**
  String get paidApp;

  /// No description provided for @usersPayToUse.
  ///
  /// In en, this message translates to:
  /// **'Users pay to use your app'**
  String get usersPayToUse;

  /// No description provided for @freeForEveryone.
  ///
  /// In en, this message translates to:
  /// **'Free for everyone'**
  String get freeForEveryone;

  /// No description provided for @perMonthLabel.
  ///
  /// In en, this message translates to:
  /// **'/ month'**
  String get perMonthLabel;

  /// Loading state text when app generation is in progress
  ///
  /// In en, this message translates to:
  /// **'Creating...'**
  String get creating;

  /// Button text to initiate app creation
  ///
  /// In en, this message translates to:
  /// **'Create App'**
  String get createApp;

  /// Status text while scanning for Bluetooth devices
  ///
  /// In en, this message translates to:
  /// **'Searching for devices...'**
  String get searchingForDevices;

  /// No description provided for @devicesFoundNearby.
  ///
  /// In en, this message translates to:
  /// **'{count} {count, plural, =1{DEVICE} other{DEVICES}} FOUND NEARBY'**
  String devicesFoundNearby(int count);

  /// No description provided for @pairingSuccessful.
  ///
  /// In en, this message translates to:
  /// **'PAIRING SUCCESSFUL'**
  String get pairingSuccessful;

  /// No description provided for @errorConnectingAppleWatch.
  ///
  /// In en, this message translates to:
  /// **'Error connecting to Apple Watch: {error}'**
  String errorConnectingAppleWatch(String error);

  /// Checkbox text to suppress future connection confirmations
  ///
  /// In en, this message translates to:
  /// **'Don\'t show it again'**
  String get dontShowAgain;

  /// Button text to acknowledge connection warnings
  ///
  /// In en, this message translates to:
  /// **'I Understand'**
  String get iUnderstand;

  /// Title for dialog prompting user to enable Bluetooth
  ///
  /// In en, this message translates to:
  /// **'Enable Bluetooth'**
  String get enableBluetooth;

  /// Explanation text for why Bluetooth is required
  ///
  /// In en, this message translates to:
  /// **'Omi needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.'**
  String get bluetoothNeeded;

  /// Link text to contact support
  ///
  /// In en, this message translates to:
  /// **'Contact Support?'**
  String get contactSupport;

  /// Button text to skip immediate device connection
  ///
  /// In en, this message translates to:
  /// **'Connect Later'**
  String get connectLater;

  /// Title for the permissions request page
  ///
  /// In en, this message translates to:
  /// **'Grant permissions'**
  String get grantPermissions;

  /// Title for background activity permission
  ///
  /// In en, this message translates to:
  /// **'Background activity'**
  String get backgroundActivity;

  /// Description for background activity permission
  ///
  /// In en, this message translates to:
  /// **'Let Omi run in the background for better stability'**
  String get backgroundActivityDesc;

  /// Title for location access permission
  ///
  /// In en, this message translates to:
  /// **'Location access'**
  String get locationAccess;

  /// Description for location access permission
  ///
  /// In en, this message translates to:
  /// **'Enable background location for the full experience'**
  String get locationAccessDesc;

  /// Title for notifications permission
  ///
  /// In en, this message translates to:
  /// **'Notifications'**
  String get notifications;

  /// Description for notifications permission
  ///
  /// In en, this message translates to:
  /// **'Enable notifications to stay informed'**
  String get notificationsDesc;

  /// Title for dialog when location services are off
  ///
  /// In en, this message translates to:
  /// **'Location Service Disabled'**
  String get locationServiceDisabled;

  /// Instructions to enable location services
  ///
  /// In en, this message translates to:
  /// **'Location Service is Disabled. Please go to Settings > Privacy & Security > Location Services and enable it'**
  String get locationServiceDisabledDesc;

  /// Title for dialog when background location is denied
  ///
  /// In en, this message translates to:
  /// **'Background Location Access Denied'**
  String get backgroundLocationDenied;

  /// Instructions to grant background location permission
  ///
  /// In en, this message translates to:
  /// **'Please go to device settings and set location permission to \"Always Allow\"'**
  String get backgroundLocationDeniedDesc;

  /// Title for the app review prompt
  ///
  /// In en, this message translates to:
  /// **'Loving Omi?'**
  String get lovingOmi;

  /// App review prompt text for iOS users
  ///
  /// In en, this message translates to:
  /// **'Help us reach more people by leaving a review in the App Store. Your feedback means the world to us!'**
  String get leaveReviewIos;

  /// App review prompt text for Android users
  ///
  /// In en, this message translates to:
  /// **'Help us reach more people by leaving a review in the Google Play Store. Your feedback means the world to us!'**
  String get leaveReviewAndroid;

  /// Button text to rate on Apple App Store
  ///
  /// In en, this message translates to:
  /// **'Rate on App Store'**
  String get rateOnAppStore;

  /// Button text to rate on Google Play Store
  ///
  /// In en, this message translates to:
  /// **'Rate on Google Play'**
  String get rateOnGooglePlay;

  /// Button text to dismiss the review prompt
  ///
  /// In en, this message translates to:
  /// **'Maybe later'**
  String get maybeLater;

  /// Introduction text for speech profile creation
  ///
  /// In en, this message translates to:
  /// **'Omi needs to learn your goals and your voice. You\'ll be able to modify it later.'**
  String get speechProfileIntro;

  /// Button text to begin a process
  ///
  /// In en, this message translates to:
  /// **'Get Started'**
  String get getStarted;

  /// Success message after completing a task
  ///
  /// In en, this message translates to:
  /// **'All done!'**
  String get allDone;

  /// Encouragement text during a multi-step process
  ///
  /// In en, this message translates to:
  /// **'Keep going, you are doing great'**
  String get keepGoing;

  /// Button text to skip the current question
  ///
  /// In en, this message translates to:
  /// **'Skip this question'**
  String get skipThisQuestion;

  /// Button text to skip the entire process temporarily
  ///
  /// In en, this message translates to:
  /// **'Skip for now'**
  String get skipForNow;

  /// Title for connection error dialog
  ///
  /// In en, this message translates to:
  /// **'Connection Error'**
  String get connectionError;

  /// Description of connection error
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to the server. Please check your internet connection and try again.'**
  String get connectionErrorDesc;

  /// Error title when multiple speakers are detected
  ///
  /// In en, this message translates to:
  /// **'Invalid recording detected'**
  String get invalidRecordingMultipleSpeakers;

  /// Error description for multiple speakers
  ///
  /// In en, this message translates to:
  /// **'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.'**
  String get multipleSpeakersDesc;

  /// Error description for recording being too short
  ///
  /// In en, this message translates to:
  /// **'There is not enough speech detected. Please speak more and try again.'**
  String get tooShortDesc;

  /// Error description for invalid recording duration
  ///
  /// In en, this message translates to:
  /// **'Please make sure you speak for at least 5 seconds and not more than 90.'**
  String get invalidRecordingDesc;

  /// Timeout warning title
  ///
  /// In en, this message translates to:
  /// **'Are you there?'**
  String get areYouThere;

  /// Error description when no speech is detected
  ///
  /// In en, this message translates to:
  /// **'We could not detect any speech. Please make sure to speak for at least 10 seconds and not more than 3 minutes.'**
  String get noSpeechDesc;

  /// Title for lost connection dialog
  ///
  /// In en, this message translates to:
  /// **'Connection Lost'**
  String get connectionLost;

  /// Description for lost connection
  ///
  /// In en, this message translates to:
  /// **'The connection was interrupted. Please check your internet connection and try again.'**
  String get connectionLostDesc;

  /// Button text to retry an action
  ///
  /// In en, this message translates to:
  /// **'Try Again'**
  String get tryAgain;

  /// Button text to connect specific device models
  ///
  /// In en, this message translates to:
  /// **'Connect Omi / OmiGlass'**
  String get connectOmiOmiGlass;

  /// Button text to proceed without connecting a hardware device
  ///
  /// In en, this message translates to:
  /// **'Continue Without Device'**
  String get continueWithoutDevice;

  /// Title for permissions required dialog
  ///
  /// In en, this message translates to:
  /// **'Permissions Required'**
  String get permissionsRequired;

  /// Explanation of why permissions are needed
  ///
  /// In en, this message translates to:
  /// **'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.'**
  String get permissionsRequiredDesc;

  /// Button text to open app settings
  ///
  /// In en, this message translates to:
  /// **'Open Settings'**
  String get openSettings;

  /// Question asking if user wants to change their display name
  ///
  /// In en, this message translates to:
  /// **'Want to go by something else?'**
  String get wantDifferentName;

  /// Question asking for user's name
  ///
  /// In en, this message translates to:
  /// **'What\'s your name?'**
  String get whatsYourName;

  /// Tagline or slogan on the welcome/auth screen
  ///
  /// In en, this message translates to:
  /// **'Speak. Transcribe. Summarize.'**
  String get speakTranscribeSummarize;

  /// Button text for Apple Sign In
  ///
  /// In en, this message translates to:
  /// **'Sign in with Apple'**
  String get signInWithApple;

  /// Button text for Google Sign In
  ///
  /// In en, this message translates to:
  /// **'Sign in with Google'**
  String get signInWithGoogle;

  /// Legal disclaimer prefix text
  ///
  /// In en, this message translates to:
  /// **'By continuing, you agree to our '**
  String get byContinuingAgree;

  /// Link text for Terms of Use
  ///
  /// In en, this message translates to:
  /// **'Terms of Use'**
  String get termsOfUse;

  /// App title or branding on onboarding screen
  ///
  /// In en, this message translates to:
  /// **'Omi – Your AI Companion'**
  String get omiYourAiCompanion;

  /// App value proposition or description
  ///
  /// In en, this message translates to:
  /// **'Capture every moment. Get AI-powered\nsummaries. Never take notes again.'**
  String get captureEveryMoment;

  /// Title for Apple Watch setup page
  ///
  /// In en, this message translates to:
  /// **'Apple Watch Setup'**
  String get appleWatchSetup;

  /// Title when permission has been requested
  ///
  /// In en, this message translates to:
  /// **'Permission Requested!'**
  String get permissionRequestedExclaim;

  /// Title for microphone permission section
  ///
  /// In en, this message translates to:
  /// **'Microphone Permission'**
  String get microphonePermission;

  /// Instructions after permission is granted
  ///
  /// In en, this message translates to:
  /// **'Permission granted! Now:\n\nOpen the Omi app on your watch and tap \"Continue\" below'**
  String get permissionGrantedNow;

  /// Instructions for granting microphone permission
  ///
  /// In en, this message translates to:
  /// **'We need microphone permission.\n\n1. Tap \"Grant Permission\"\n2. Allow on your iPhone\n3. Watch app will close\n4. Reopen and tap \"Continue\"'**
  String get needMicrophonePermission;

  /// Button to request permission
  ///
  /// In en, this message translates to:
  /// **'Grant Permission'**
  String get grantPermissionButton;

  /// Link to help dialog
  ///
  /// In en, this message translates to:
  /// **'Need Help?'**
  String get needHelp;

  /// Troubleshooting instructions for watch setup
  ///
  /// In en, this message translates to:
  /// **'Troubleshooting:\n\n1. Ensure Omi is installed on your watch\n2. Open the Omi app on your watch\n3. Look for the permission popup\n4. Tap \"Allow\" when prompted\n5. App on your watch will close - reopen it\n6. Come back and tap \"Continue\" on your iPhone'**
  String get troubleshootingSteps;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Recording started successfully!'**
  String get recordingStartedSuccessfully;

  /// Error message when permission is missing
  ///
  /// In en, this message translates to:
  /// **'Permission not granted yet. Please make sure you allowed microphone access and reopened the app on your watch.'**
  String get permissionNotGrantedYet;

  /// Error message for permission request failure
  ///
  /// In en, this message translates to:
  /// **'Error requesting permission: {error}'**
  String errorRequestingPermission(String error);

  /// Error message for recording start failure
  ///
  /// In en, this message translates to:
  /// **'Error starting recording: {error}'**
  String errorStartingRecording(String error);

  /// Title for language selection dialog
  ///
  /// In en, this message translates to:
  /// **'Select your primary language'**
  String get selectPrimaryLanguage;

  /// Explanation of why language selection matters
  ///
  /// In en, this message translates to:
  /// **'Set your language for sharper transcriptions and a personalized experience'**
  String get languageBenefits;

  /// Question asking for primary language
  ///
  /// In en, this message translates to:
  /// **'What\'s your primary language?'**
  String get whatsYourPrimaryLanguage;

  /// Placeholder for selected language name
  ///
  /// In en, this message translates to:
  /// **'Select your language'**
  String get selectYourLanguage;

  /// Tagline on onboarding wrapper
  ///
  /// In en, this message translates to:
  /// **'Your personal growth journey with AI that listens to your every word.'**
  String get personalGrowthJourney;

  /// Title for the Action Items page
  ///
  /// In en, this message translates to:
  /// **'To-Do\'s'**
  String get actionItemsTitle;

  /// Instruction text for Action Items interactions
  ///
  /// In en, this message translates to:
  /// **'Tap to edit • Long press to select • Swipe for actions'**
  String get actionItemsDescription;

  /// Label for To Do tab
  ///
  /// In en, this message translates to:
  /// **'To Do'**
  String get tabToDo;

  /// Label for Done tab
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get tabDone;

  /// Label for Old tab
  ///
  /// In en, this message translates to:
  /// **'Old'**
  String get tabOld;

  /// Message when To Do list is empty
  ///
  /// In en, this message translates to:
  /// **'🎉 All caught up!\nNo pending action items'**
  String get emptyTodoMessage;

  /// Message when Done list is empty
  ///
  /// In en, this message translates to:
  /// **'No completed items yet'**
  String get emptyDoneMessage;

  /// Message when Old list is empty
  ///
  /// In en, this message translates to:
  /// **'✅ No old tasks'**
  String get emptyOldMessage;

  /// Generic no items message
  ///
  /// In en, this message translates to:
  /// **'No items'**
  String get noItems;

  /// Snackbar message when item marked incomplete
  ///
  /// In en, this message translates to:
  /// **'Action item marked as incomplete'**
  String get actionItemMarkedIncomplete;

  /// Snackbar message when item completed
  ///
  /// In en, this message translates to:
  /// **'Action item completed'**
  String get actionItemCompleted;

  /// Title for delete item dialog
  ///
  /// In en, this message translates to:
  /// **'Delete Action Item'**
  String get deleteActionItemTitle;

  /// Confirmation message for deleting single item
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete this action item?'**
  String get deleteActionItemMessage;

  /// Title for bulk delete dialog
  ///
  /// In en, this message translates to:
  /// **'Delete Selected Items'**
  String get deleteSelectedItemsTitle;

  /// Confirmation message for bulk delete
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete {count} selected action item{s}?'**
  String deleteSelectedItemsMessage(int count, String s);

  /// Snackbar message after deleting single item
  ///
  /// In en, this message translates to:
  /// **'Action item \"{description}\" deleted'**
  String actionItemDeletedResult(String description);

  /// Snackbar message after bulk delete
  ///
  /// In en, this message translates to:
  /// **'{count} action item{s} deleted'**
  String itemsDeletedResult(int count, String s);

  /// Error message when deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete action item'**
  String get failedToDeleteItem;

  /// Error message when bulk deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete items'**
  String get failedToDeleteItems;

  /// Error message when partial deletion failure
  ///
  /// In en, this message translates to:
  /// **'Failed to delete some items'**
  String get failedToDeleteSomeItems;

  /// Heading for empty state welcome
  ///
  /// In en, this message translates to:
  /// **'Ready for Action Items'**
  String get welcomeActionItemsTitle;

  /// Description for empty state welcome
  ///
  /// In en, this message translates to:
  /// **'Your AI will automatically extract tasks and to-dos from your conversations. They\'ll appear here when created.'**
  String get welcomeActionItemsDescription;

  /// Feature point description
  ///
  /// In en, this message translates to:
  /// **'Automatically extracted from conversations'**
  String get autoExtractionFeature;

  /// Feature point description
  ///
  /// In en, this message translates to:
  /// **'Tap to edit, swipe to complete or delete'**
  String get editSwipeFeature;

  /// Selection count in app bar
  ///
  /// In en, this message translates to:
  /// **'{count} selected'**
  String itemsSelected(int count);

  /// Tooltip for select all
  ///
  /// In en, this message translates to:
  /// **'Select all'**
  String get selectAll;

  /// Tooltip for delete selected
  ///
  /// In en, this message translates to:
  /// **'Delete selected'**
  String get deleteSelected;

  /// Hint text for memories search bar
  ///
  /// In en, this message translates to:
  /// **'Search {count} Memories'**
  String searchMemories(int count);

  /// Notification when memory deleted
  ///
  /// In en, this message translates to:
  /// **'Memory Deleted.'**
  String get memoryDeleted;

  /// Undo button text
  ///
  /// In en, this message translates to:
  /// **'Undo'**
  String get undo;

  /// Empty state text
  ///
  /// In en, this message translates to:
  /// **'No memories yet'**
  String get noMemoriesYet;

  /// Empty state text for auto category
  ///
  /// In en, this message translates to:
  /// **'No auto-extracted memories yet'**
  String get noAutoMemories;

  /// Empty state text for manual category
  ///
  /// In en, this message translates to:
  /// **'No manual memories yet'**
  String get noManualMemories;

  /// Empty state text for filtered categories
  ///
  /// In en, this message translates to:
  /// **'No memories in these categories'**
  String get noMemoriesInCategories;

  /// Empty state text for search results
  ///
  /// In en, this message translates to:
  /// **'No memories found'**
  String get noMemoriesFound;

  /// Button to add first memory
  ///
  /// In en, this message translates to:
  /// **'Add your first memory'**
  String get addFirstMemory;

  /// Dialog title for clearing memory
  ///
  /// In en, this message translates to:
  /// **'Clear Omi\'s Memory'**
  String get clearMemoryTitle;

  /// Dialog content for clearing memory
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to clear Omi\'s memory? This action cannot be undone.'**
  String get clearMemoryMessage;

  /// Button text to confirm clear
  ///
  /// In en, this message translates to:
  /// **'Clear Memory'**
  String get clearMemoryButton;

  /// Snackbar success message
  ///
  /// In en, this message translates to:
  /// **'Omi\'s memory about you has been cleared'**
  String get memoryClearedSuccess;

  /// Snackbar message
  ///
  /// In en, this message translates to:
  /// **'No memories to delete'**
  String get noMemoriesToDelete;

  /// Tooltip for create memory FAB
  ///
  /// In en, this message translates to:
  /// **'Create new memory'**
  String get createMemoryTooltip;

  /// Tooltip for create action item FAB
  ///
  /// In en, this message translates to:
  /// **'Create new action item'**
  String get createActionItemTooltip;

  /// Title for memory management sheet
  ///
  /// In en, this message translates to:
  /// **'Memory Management'**
  String get memoryManagement;

  /// Section header
  ///
  /// In en, this message translates to:
  /// **'Filter Memories'**
  String get filterMemories;

  /// Count display
  ///
  /// In en, this message translates to:
  /// **'You have {count} total memories'**
  String totalMemoriesCount(int count);

  /// Label
  ///
  /// In en, this message translates to:
  /// **'Public memories'**
  String get publicMemories;

  /// Label
  ///
  /// In en, this message translates to:
  /// **'Private memories'**
  String get privateMemories;

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Make All Memories Private'**
  String get makeAllPrivate;

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Make All Memories Public'**
  String get makeAllPublic;

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Delete All Memories'**
  String get deleteAllMemories;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'All memories are now private'**
  String get allMemoriesPrivateResult;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'All memories are now public'**
  String get allMemoriesPublicResult;

  /// Dialog title
  ///
  /// In en, this message translates to:
  /// **'New Memory'**
  String get newMemory;

  /// Dialog title
  ///
  /// In en, this message translates to:
  /// **'Edit Memory'**
  String get editMemory;

  /// Input hint
  ///
  /// In en, this message translates to:
  /// **'I like to eat ice cream...'**
  String get memoryContentHint;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'Failed to save. Please check your connection.'**
  String get failedToSaveMemory;

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Save Memory'**
  String get saveMemory;

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Retry'**
  String get retry;

  /// Sheet title
  ///
  /// In en, this message translates to:
  /// **'Create Action Item'**
  String get createActionItem;

  /// Sheet title
  ///
  /// In en, this message translates to:
  /// **'Edit Action Item'**
  String get editActionItem;

  /// Input hint
  ///
  /// In en, this message translates to:
  /// **'What needs to be done?'**
  String get actionItemDescriptionHint;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'Action item description cannot be empty.'**
  String get actionItemDescriptionEmpty;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Action item updated'**
  String get actionItemUpdated;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Failed to update action item'**
  String get failedToUpdateActionItem;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Action item created'**
  String get actionItemCreated;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Failed to create action item'**
  String get failedToCreateActionItem;

  /// Label
  ///
  /// In en, this message translates to:
  /// **'Due Date'**
  String get dueDate;

  /// Label
  ///
  /// In en, this message translates to:
  /// **'Time'**
  String get time;

  /// Placeholder
  ///
  /// In en, this message translates to:
  /// **'Add due date'**
  String get addDueDate;

  /// Instruction
  ///
  /// In en, this message translates to:
  /// **'Press done to save'**
  String get pressDoneToSave;

  /// Instruction
  ///
  /// In en, this message translates to:
  /// **'Press done to create'**
  String get pressDoneToCreate;

  /// Filter option
  ///
  /// In en, this message translates to:
  /// **'All'**
  String get filterAll;

  /// Filter option for facts about the user
  ///
  /// In en, this message translates to:
  /// **'About You'**
  String get filterSystem;

  /// Filter option for external wisdom/advice
  ///
  /// In en, this message translates to:
  /// **'Insights'**
  String get filterInteresting;

  /// Filter option
  ///
  /// In en, this message translates to:
  /// **'Manual'**
  String get filterManual;

  /// Status label
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get completed;

  /// Action label
  ///
  /// In en, this message translates to:
  /// **'Mark complete'**
  String get markComplete;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Action item deleted'**
  String get actionItemDeleted;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Failed to delete action item'**
  String get failedToDeleteActionItem;

  /// Dialog title
  ///
  /// In en, this message translates to:
  /// **'Delete Action Item'**
  String get deleteActionItemConfirmTitle;

  /// Dialog message
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete this action item?'**
  String get deleteActionItemConfirmMessage;

  /// Label for app language selector
  ///
  /// In en, this message translates to:
  /// **'App Language'**
  String get appLanguage;
}

class _AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) => <String>['de', 'en', 'es', 'hi', 'ja', 'pt', 'zh'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'de':
      return AppLocalizationsDe();
    case 'en':
      return AppLocalizationsEn();
    case 'es':
      return AppLocalizationsEs();
    case 'hi':
      return AppLocalizationsHi();
    case 'ja':
      return AppLocalizationsJa();
    case 'pt':
      return AppLocalizationsPt();
    case 'zh':
      return AppLocalizationsZh();
  }

  throw FlutterError('AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
