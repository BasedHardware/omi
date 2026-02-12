import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_ar.dart';
import 'app_localizations_bg.dart';
import 'app_localizations_ca.dart';
import 'app_localizations_cs.dart';
import 'app_localizations_da.dart';
import 'app_localizations_de.dart';
import 'app_localizations_el.dart';
import 'app_localizations_en.dart';
import 'app_localizations_es.dart';
import 'app_localizations_et.dart';
import 'app_localizations_fi.dart';
import 'app_localizations_fr.dart';
import 'app_localizations_hi.dart';
import 'app_localizations_hu.dart';
import 'app_localizations_id.dart';
import 'app_localizations_it.dart';
import 'app_localizations_ja.dart';
import 'app_localizations_ko.dart';
import 'app_localizations_lt.dart';
import 'app_localizations_lv.dart';
import 'app_localizations_ms.dart';
import 'app_localizations_nl.dart';
import 'app_localizations_no.dart';
import 'app_localizations_pl.dart';
import 'app_localizations_pt.dart';
import 'app_localizations_ro.dart';
import 'app_localizations_ru.dart';
import 'app_localizations_sk.dart';
import 'app_localizations_sv.dart';
import 'app_localizations_th.dart';
import 'app_localizations_tr.dart';
import 'app_localizations_uk.dart';
import 'app_localizations_vi.dart';
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
    Locale('ar'),
    Locale('bg'),
    Locale('ca'),
    Locale('cs'),
    Locale('da'),
    Locale('de'),
    Locale('el'),
    Locale('en'),
    Locale('es'),
    Locale('et'),
    Locale('fi'),
    Locale('fr'),
    Locale('hi'),
    Locale('hu'),
    Locale('id'),
    Locale('it'),
    Locale('ja'),
    Locale('ko'),
    Locale('lt'),
    Locale('lv'),
    Locale('ms'),
    Locale('nl'),
    Locale('no'),
    Locale('pl'),
    Locale('pt'),
    Locale('ro'),
    Locale('ru'),
    Locale('sk'),
    Locale('sv'),
    Locale('th'),
    Locale('tr'),
    Locale('uk'),
    Locale('vi'),
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

  /// Generic cancel button label
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// Generic OK button text
  ///
  /// In en, this message translates to:
  /// **'Ok'**
  String get ok;

  /// Delete button
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get delete;

  /// Add button label
  ///
  /// In en, this message translates to:
  /// **'Add'**
  String get add;

  /// Button label to update action item
  ///
  /// In en, this message translates to:
  /// **'Update'**
  String get update;

  /// Save button label
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get save;

  /// Edit menu item label
  ///
  /// In en, this message translates to:
  /// **'Edit'**
  String get edit;

  /// Close button label
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get close;

  /// Clear button
  ///
  /// In en, this message translates to:
  /// **'Clear'**
  String get clear;

  /// Option to copy transcript to clipboard
  ///
  /// In en, this message translates to:
  /// **'Copy Transcript'**
  String get copyTranscript;

  /// Option to copy summary to clipboard
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

  /// Error message shown when there is no internet connection
  ///
  /// In en, this message translates to:
  /// **'No internet connection'**
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

  /// Label showing time remaining for SD card transfer
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

  /// Settings dialog title
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settings;

  /// Label for language selector
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

  /// Shortcut to ask Omi a question
  ///
  /// In en, this message translates to:
  /// **'Ask Omi'**
  String get askOmi;

  /// Status when download is done
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get done;

  /// Status text when device is disconnected
  ///
  /// In en, this message translates to:
  /// **'Disconnected'**
  String get disconnected;

  /// Loading text displayed while search is in progress
  ///
  /// In en, this message translates to:
  /// **'Searching...'**
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

  /// Title shown when user has no conversations
  ///
  /// In en, this message translates to:
  /// **'No conversations yet'**
  String get noConversationsYet;

  /// Empty state title when no starred conversations
  ///
  /// In en, this message translates to:
  /// **'No starred conversations'**
  String get noStarredConversations;

  /// Hint explaining how to star conversations
  ///
  /// In en, this message translates to:
  /// **'To star a conversation, open it and tap the star icon in the header.'**
  String get starConversationHint;

  /// Placeholder text for conversation search field
  ///
  /// In en, this message translates to:
  /// **'Search conversations...'**
  String get searchConversations;

  /// Selection count label
  ///
  /// In en, this message translates to:
  /// **'{count} selected'**
  String selectedCount(int count, Object s);

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

  /// Loading text when clearing chat
  ///
  /// In en, this message translates to:
  /// **'Deleting your messages from Omi\'s memory...'**
  String get deletingMessages;

  /// Snackbar message for copied text
  ///
  /// In en, this message translates to:
  /// **'✨ Message copied to clipboard'**
  String get messageCopied;

  /// Error when trying to report own message
  ///
  /// In en, this message translates to:
  /// **'You cannot report your own messages.'**
  String get cannotReportOwnMessage;

  /// Report dialog title
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

  /// Button/menu item to clear chat
  ///
  /// In en, this message translates to:
  /// **'Clear Chat'**
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

  /// Navigation label for apps page
  ///
  /// In en, this message translates to:
  /// **'Apps'**
  String get apps;

  /// Empty state title when no apps match search
  ///
  /// In en, this message translates to:
  /// **'No apps found'**
  String get noAppsFound;

  /// Hint when no apps found
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search or filters'**
  String get tryAdjustingSearch;

  /// Button title for creating custom apps
  ///
  /// In en, this message translates to:
  /// **'Create Your Own App'**
  String get createYourOwnApp;

  /// Create app button subtitle
  ///
  /// In en, this message translates to:
  /// **'Build and share your custom app'**
  String get buildAndShareApp;

  /// Placeholder text for search input
  ///
  /// In en, this message translates to:
  /// **'Search apps...'**
  String get searchApps;

  /// Filter button for user's own apps
  ///
  /// In en, this message translates to:
  /// **'My Apps'**
  String get myApps;

  /// Filter button for installed apps
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

  /// Custom vocabulary section
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

  /// Data privacy setting
  ///
  /// In en, this message translates to:
  /// **'Data Privacy'**
  String get dataPrivacy;

  /// User ID field
  ///
  /// In en, this message translates to:
  /// **'User ID'**
  String get userId;

  /// Value not set placeholder
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

  /// Page title for offline sync
  ///
  /// In en, this message translates to:
  /// **'Offline Sync'**
  String get offlineSync;

  /// Device settings menu item
  ///
  /// In en, this message translates to:
  /// **'Device Settings'**
  String get deviceSettings;

  /// Integrations menu item
  ///
  /// In en, this message translates to:
  /// **'Integrations'**
  String get integrations;

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

  /// Title for developer settings page
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

  /// Label for device ID field
  ///
  /// In en, this message translates to:
  /// **'Device ID'**
  String get deviceId;

  /// Label for firmware version
  ///
  /// In en, this message translates to:
  /// **'Firmware'**
  String get firmware;

  /// Menu item for SD card synchronization
  ///
  /// In en, this message translates to:
  /// **'SD Card Sync'**
  String get sdCardSync;

  /// Hardware revision label
  ///
  /// In en, this message translates to:
  /// **'Hardware Revision'**
  String get hardwareRevision;

  /// Label for model number field
  ///
  /// In en, this message translates to:
  /// **'Model Number'**
  String get modelNumber;

  /// Label for manufacturer field
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

  /// Menu item for charging help
  ///
  /// In en, this message translates to:
  /// **'Charging Issues'**
  String get chargingIssues;

  /// Action to disconnect device
  ///
  /// In en, this message translates to:
  /// **'Disconnect Device'**
  String get disconnectDevice;

  /// Action to unpair device
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

  /// Message shown after device is unpaired
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

  /// Toggle state label when disabled
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

  /// Text shown while saving settings
  ///
  /// In en, this message translates to:
  /// **'Saving...'**
  String get saving;

  /// Persona configuration subtitle
  ///
  /// In en, this message translates to:
  /// **'Configure your AI persona'**
  String get personaConfig;

  /// Beta label for experimental features
  ///
  /// In en, this message translates to:
  /// **'BETA'**
  String get beta;

  /// Transcription feature name
  ///
  /// In en, this message translates to:
  /// **'Transcription'**
  String get transcription;

  /// Transcription configuration subtitle
  ///
  /// In en, this message translates to:
  /// **'Configure STT provider'**
  String get transcriptionConfig;

  /// Conversation timeout feature name
  ///
  /// In en, this message translates to:
  /// **'Conversation Timeout'**
  String get conversationTimeout;

  /// Conversation timeout configuration subtitle
  ///
  /// In en, this message translates to:
  /// **'Set when conversations auto-end'**
  String get conversationTimeoutConfig;

  /// Import data feature name
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

  /// Label for webhook endpoint URL field
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

  /// Button text to create API key
  ///
  /// In en, this message translates to:
  /// **'Create Key'**
  String get createKey;

  /// Documentation button text
  ///
  /// In en, this message translates to:
  /// **'Docs'**
  String get docs;

  /// Usage page title
  ///
  /// In en, this message translates to:
  /// **'Your Omi Insights'**
  String get yourOmiInsights;

  /// Label for today date
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

  /// Message shown on locked memory items
  ///
  /// In en, this message translates to:
  /// **'Upgrade to unlimited'**
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

  /// Debug logs feature name
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

  /// Message when no debug log files exist
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

  /// Title for log file selection dialog
  ///
  /// In en, this message translates to:
  /// **'Select Log File'**
  String get selectLogFile;

  /// Button text to share debug logs
  ///
  /// In en, this message translates to:
  /// **'Share Logs'**
  String get shareLogs;

  /// Confirmation message after clearing debug logs
  ///
  /// In en, this message translates to:
  /// **'Debug log cleared'**
  String get debugLogCleared;

  /// No description provided for @exportStarted.
  ///
  /// In en, this message translates to:
  /// **'Export started. This may take a few seconds...'**
  String get exportStarted;

  /// Export all data feature name
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

  /// Dialog title for delete knowledge graph confirmation
  ///
  /// In en, this message translates to:
  /// **'Delete Knowledge Graph?'**
  String get deleteKnowledgeGraphTitle;

  /// Dialog message explaining delete knowledge graph action
  ///
  /// In en, this message translates to:
  /// **'This will delete all derived knowledge graph data (nodes and connections). Your original memories will remain safe. The graph will be rebuilt over time or upon next request.'**
  String get deleteKnowledgeGraphMessage;

  /// Success message when knowledge graph deleted
  ///
  /// In en, this message translates to:
  /// **'Knowledge Graph deleted'**
  String get knowledgeGraphDeleted;

  /// Error message when deleting graph fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete graph: {error}'**
  String deleteGraphFailed(String error);

  /// Delete knowledge graph feature name
  ///
  /// In en, this message translates to:
  /// **'Delete Knowledge Graph'**
  String get deleteKnowledgeGraph;

  /// No description provided for @deleteKnowledgeGraphDesc.
  ///
  /// In en, this message translates to:
  /// **'Clear all nodes and connections'**
  String get deleteKnowledgeGraphDesc;

  /// MCP (Model Context Protocol) section header
  ///
  /// In en, this message translates to:
  /// **'MCP'**
  String get mcp;

  /// MCP Server section header
  ///
  /// In en, this message translates to:
  /// **'MCP Server'**
  String get mcpServer;

  /// No description provided for @mcpServerDesc.
  ///
  /// In en, this message translates to:
  /// **'Connect AI assistants to your data'**
  String get mcpServerDesc;

  /// Server URL label
  ///
  /// In en, this message translates to:
  /// **'Server URL'**
  String get serverUrl;

  /// Confirmation when URL is copied
  ///
  /// In en, this message translates to:
  /// **'URL copied'**
  String get urlCopied;

  /// API Key authentication section header
  ///
  /// In en, this message translates to:
  /// **'API Key Auth'**
  String get apiKeyAuth;

  /// HTTP header label
  ///
  /// In en, this message translates to:
  /// **'Header'**
  String get header;

  /// No description provided for @authorizationBearer.
  ///
  /// In en, this message translates to:
  /// **'Authorization: Bearer <key>'**
  String get authorizationBearer;

  /// Label for OAuth section
  ///
  /// In en, this message translates to:
  /// **'OAuth'**
  String get oauth;

  /// OAuth client ID label
  ///
  /// In en, this message translates to:
  /// **'Client ID'**
  String get clientId;

  /// OAuth client secret label
  ///
  /// In en, this message translates to:
  /// **'Client Secret'**
  String get clientSecret;

  /// No description provided for @useMcpApiKey.
  ///
  /// In en, this message translates to:
  /// **'Use your MCP API key'**
  String get useMcpApiKey;

  /// Webhooks section header
  ///
  /// In en, this message translates to:
  /// **'Webhooks'**
  String get webhooks;

  /// Webhook type for conversation events
  ///
  /// In en, this message translates to:
  /// **'Conversation Events'**
  String get conversationEvents;

  /// Description for conversation webhook
  ///
  /// In en, this message translates to:
  /// **'New conversation created'**
  String get newConversationCreated;

  /// No description provided for @realtimeTranscript.
  ///
  /// In en, this message translates to:
  /// **'Real-time Transcript'**
  String get realtimeTranscript;

  /// Description for transcript webhook
  ///
  /// In en, this message translates to:
  /// **'Transcript received'**
  String get transcriptReceived;

  /// Webhook type for audio bytes
  ///
  /// In en, this message translates to:
  /// **'Audio Bytes'**
  String get audioBytes;

  /// Description for audio bytes webhook
  ///
  /// In en, this message translates to:
  /// **'Audio data received'**
  String get audioDataReceived;

  /// Label for interval input in seconds
  ///
  /// In en, this message translates to:
  /// **'Interval (seconds)'**
  String get intervalSeconds;

  /// Webhook type for day summary
  ///
  /// In en, this message translates to:
  /// **'Day Summary'**
  String get daySummary;

  /// Description for day summary webhook
  ///
  /// In en, this message translates to:
  /// **'Summary generated'**
  String get summaryGenerated;

  /// Claude Desktop integration section
  ///
  /// In en, this message translates to:
  /// **'Claude Desktop'**
  String get claudeDesktop;

  /// No description provided for @addToClaudeConfig.
  ///
  /// In en, this message translates to:
  /// **'Add to claude_desktop_config.json'**
  String get addToClaudeConfig;

  /// Button text to copy configuration
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

  /// Filter option for interesting memories
  ///
  /// In en, this message translates to:
  /// **'Insights'**
  String get insights;

  /// Navigation label for memories page
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

  /// Label for memory visibility selection section
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

  /// No description provided for @integrationsFooter.
  ///
  /// In en, this message translates to:
  /// **'Connect your apps to view data and metrics in chat.'**
  String get integrationsFooter;

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

  /// Refresh button
  ///
  /// In en, this message translates to:
  /// **'Refresh'**
  String get refresh;

  /// Empty state when no meetings scheduled
  ///
  /// In en, this message translates to:
  /// **'No upcoming meetings'**
  String get noUpcomingMeetings;

  /// No description provided for @checkingNextDays.
  ///
  /// In en, this message translates to:
  /// **'Checking next 30 days'**
  String get checkingNextDays;

  /// Label for tomorrow in date headers
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

  /// Account section label
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

  /// Option for private memory visibility
  ///
  /// In en, this message translates to:
  /// **'Private'**
  String get private;

  /// No description provided for @updatedDate.
  ///
  /// In en, this message translates to:
  /// **'Updated {date}'**
  String updatedDate(String date);

  /// Label for yesterday date
  ///
  /// In en, this message translates to:
  /// **'Yesterday'**
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

  /// Continue button label
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

  /// Button to dismiss explanation
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

  /// Confirmation when config is copied
  ///
  /// In en, this message translates to:
  /// **'Config copied to clipboard'**
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

  /// Label for API key (used for clipboard notification)
  ///
  /// In en, this message translates to:
  /// **'API key'**
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

  /// Warning about device codec compatibility
  ///
  /// In en, this message translates to:
  /// **'{device} uses {reason}. Omi will be used.'**
  String deviceUsesCodec(String device, String reason);

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

  /// Button text to save edited memory
  ///
  /// In en, this message translates to:
  /// **'Save Changes'**
  String get saveChanges;

  /// Reset keyboard shortcut to default value
  ///
  /// In en, this message translates to:
  /// **'Reset to default'**
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

  /// Label for description field
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

  /// Menu option to change memory visibility to public
  ///
  /// In en, this message translates to:
  /// **'Make Public'**
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

  /// Button label to create a new app
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

  /// Checkbox text to prevent showing dialog again
  ///
  /// In en, this message translates to:
  /// **'Don\'t show it again'**
  String get dontShowAgain;

  /// Button to acknowledge warning
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

  /// AppBar title for notifications settings page
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

  /// Button text to defer action
  ///
  /// In en, this message translates to:
  /// **'Maybe Later'**
  String get maybeLater;

  /// Introduction text for speech profile setup
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

  /// Button text to skip current question
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

  /// Subtitle describing Omi on auth screen
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

  /// Dialog title for delete confirmation
  ///
  /// In en, this message translates to:
  /// **'Delete Action Item'**
  String get deleteActionItemTitle;

  /// Dialog message for delete confirmation
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

  /// Search input hint text
  ///
  /// In en, this message translates to:
  /// **'Search memories...'**
  String get searchMemories;

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

  /// Empty state title when no memories
  ///
  /// In en, this message translates to:
  /// **'🧠 No memories yet'**
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

  /// Empty state title when search/filter has no results
  ///
  /// In en, this message translates to:
  /// **'🔍 No memories found'**
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

  /// Button text to confirm clearing all memories
  ///
  /// In en, this message translates to:
  /// **'Clear Memory'**
  String get clearMemoryButton;

  /// Snackbar success message
  ///
  /// In en, this message translates to:
  /// **'Omi\'s memory about you has been cleared'**
  String get memoryClearedSuccess;

  /// Info message when there are no memories to delete
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

  /// Title for memory management dialog
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

  /// Action to delete all memories
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

  /// Dialog title when creating a new memory
  ///
  /// In en, this message translates to:
  /// **'✨ New Memory'**
  String get newMemory;

  /// Dialog title when editing a memory
  ///
  /// In en, this message translates to:
  /// **'✏️ Edit Memory'**
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

  /// Button label to retry an action
  ///
  /// In en, this message translates to:
  /// **'Retry'**
  String get retry;

  /// Dialog title for creating action item
  ///
  /// In en, this message translates to:
  /// **'Create Action Item'**
  String get createActionItem;

  /// Dialog title for editing action item
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

  /// Error message when updating action item fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update action item'**
  String get failedToUpdateActionItem;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Action item created'**
  String get actionItemCreated;

  /// Error message when creating action item fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create action item'**
  String get failedToCreateActionItem;

  /// Label for due date field
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

  /// Badge label indicating setup is completed
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get completed;

  /// Menu item to mark action item as complete
  ///
  /// In en, this message translates to:
  /// **'Mark Complete'**
  String get markComplete;

  /// Message shown when action item is deleted
  ///
  /// In en, this message translates to:
  /// **'Action item deleted'**
  String get actionItemDeleted;

  /// Error message when deleting action item fails
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

  /// Section title for app interface language settings
  ///
  /// In en, this message translates to:
  /// **'APP INTERFACE'**
  String get appInterfaceSectionTitle;

  /// Section title for speech and transcription language settings
  ///
  /// In en, this message translates to:
  /// **'SPEECH & TRANSCRIPTION'**
  String get speechTranscriptionSectionTitle;

  /// Helper text explaining the difference between app language and speech language
  ///
  /// In en, this message translates to:
  /// **'App Language changes menus and buttons. Speech Language affects how your recordings are transcribed.'**
  String get languageSettingsHelperText;

  /// Title for dialog explaining that conversations are translated
  ///
  /// In en, this message translates to:
  /// **'Translation Notice'**
  String get translationNotice;

  /// Message explaining how translation works and where to change language settings
  ///
  /// In en, this message translates to:
  /// **'Omi translates conversations into your primary language. Update it anytime in Settings → Profiles.'**
  String get translationNoticeMessage;

  /// Error message shown when network request fails
  ///
  /// In en, this message translates to:
  /// **'Please check your internet connection and try again'**
  String get pleaseCheckInternetConnection;

  /// Validation message prompting user to select a reason for their feedback
  ///
  /// In en, this message translates to:
  /// **'Please select a reason'**
  String get pleaseSelectReason;

  /// Hint text for feedback textarea asking user to provide more details
  ///
  /// In en, this message translates to:
  /// **'Tell us more about what went wrong...'**
  String get tellUsMoreWhatWentWrong;

  /// Button to select text from message
  ///
  /// In en, this message translates to:
  /// **'Select Text'**
  String get selectText;

  /// Error message for goal limit
  ///
  /// In en, this message translates to:
  /// **'Maximum {count} goals allowed'**
  String maximumGoalsAllowed(int count);

  /// Error message shown when user tries to merge a conversation that is locked or already being merged
  ///
  /// In en, this message translates to:
  /// **'This conversation cannot be merged (locked or already merging)'**
  String get conversationCannotBeMerged;

  /// Validation message when user tries to create folder without a name
  ///
  /// In en, this message translates to:
  /// **'Please enter a folder name'**
  String get pleaseEnterFolderName;

  /// Error message when folder creation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create folder'**
  String get failedToCreateFolder;

  /// Error message when folder update fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update folder'**
  String get failedToUpdateFolder;

  /// Hint text for folder name input field
  ///
  /// In en, this message translates to:
  /// **'Folder name'**
  String get folderName;

  /// Hint text for optional folder description field
  ///
  /// In en, this message translates to:
  /// **'Description (optional)'**
  String get descriptionOptional;

  /// Error message when folder deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete folder'**
  String get failedToDeleteFolder;

  /// Menu option to edit a folder
  ///
  /// In en, this message translates to:
  /// **'Edit Folder'**
  String get editFolder;

  /// Menu option to delete a folder
  ///
  /// In en, this message translates to:
  /// **'Delete Folder'**
  String get deleteFolder;

  /// Success message when transcript is copied
  ///
  /// In en, this message translates to:
  /// **'Transcript copied to clipboard'**
  String get transcriptCopiedToClipboard;

  /// Success message when summary is copied
  ///
  /// In en, this message translates to:
  /// **'Summary copied to clipboard'**
  String get summaryCopiedToClipboard;

  /// Error when sharing URL fails
  ///
  /// In en, this message translates to:
  /// **'Conversation URL could not be shared.'**
  String get conversationUrlCouldNotBeShared;

  /// Success message when URL is copied
  ///
  /// In en, this message translates to:
  /// **'URL Copied to Clipboard'**
  String get urlCopiedToClipboard;

  /// Button/section label for exporting transcript
  ///
  /// In en, this message translates to:
  /// **'Export Transcript'**
  String get exportTranscript;

  /// Button/section label for exporting summary
  ///
  /// In en, this message translates to:
  /// **'Export Summary'**
  String get exportSummary;

  /// Export button text
  ///
  /// In en, this message translates to:
  /// **'Export'**
  String get exportButton;

  /// Success message when action items are copied
  ///
  /// In en, this message translates to:
  /// **'Action items copied to clipboard'**
  String get actionItemsCopiedToClipboard;

  /// Button text to generate a summary
  ///
  /// In en, this message translates to:
  /// **'Summarize'**
  String get summarize;

  /// Menu item to generate a summary
  ///
  /// In en, this message translates to:
  /// **'Generate Summary'**
  String get generateSummary;

  /// Error message when conversation cannot be found
  ///
  /// In en, this message translates to:
  /// **'Conversation not found or has been deleted'**
  String get conversationNotFoundOrDeleted;

  /// Confirmation dialog title for deleting memory
  ///
  /// In en, this message translates to:
  /// **'Delete Memory'**
  String get deleteMemory;

  /// Warning message in delete confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'This action cannot be undone.'**
  String get thisActionCannotBeUndone;

  /// Count of memories in category
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{0 memories} =1{1 memory} other{{count} memories}}'**
  String memoriesCount(int count);

  /// Empty state message when category has no memories
  ///
  /// In en, this message translates to:
  /// **'No memories in this category yet'**
  String get noMemoriesInCategory;

  /// Button text in empty state
  ///
  /// In en, this message translates to:
  /// **'Add your first memory'**
  String get addYourFirstMemory;

  /// Firmware update step title about disconnecting USB
  ///
  /// In en, this message translates to:
  /// **'Disconnect USB'**
  String get firmwareDisconnectUsb;

  /// Warning about USB connection during firmware update
  ///
  /// In en, this message translates to:
  /// **'USB connection during updates may damage your device.'**
  String get firmwareUsbWarning;

  /// Firmware update step title about battery level
  ///
  /// In en, this message translates to:
  /// **'Battery Above 15%'**
  String get firmwareBatteryAbove15;

  /// Description for battery requirement during firmware update
  ///
  /// In en, this message translates to:
  /// **'Ensure your device has 15% battery.'**
  String get firmwareEnsureBattery;

  /// Firmware update step title about internet connection
  ///
  /// In en, this message translates to:
  /// **'Stable Connection'**
  String get firmwareStableConnection;

  /// Description for connection requirement during firmware update
  ///
  /// In en, this message translates to:
  /// **'Connect to WiFi or cellular.'**
  String get firmwareConnectWifi;

  /// Error message when firmware update fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start update: {error}'**
  String failedToStartUpdate(String error);

  /// Header text for firmware update checklist
  ///
  /// In en, this message translates to:
  /// **'Before Update, Make Sure:'**
  String get beforeUpdateMakeSure;

  /// Text shown when user confirms firmware update
  ///
  /// In en, this message translates to:
  /// **'Confirmed!'**
  String get confirmed;

  /// Text shown when user drags the swipe button
  ///
  /// In en, this message translates to:
  /// **'Release'**
  String get release;

  /// Text on swipe-to-confirm button for firmware update
  ///
  /// In en, this message translates to:
  /// **'Slide to Update'**
  String get slideToUpdate;

  /// Message shown when something is copied to clipboard
  ///
  /// In en, this message translates to:
  /// **'{title} copied to clipboard'**
  String copiedToClipboard(String title);

  /// Battery level label
  ///
  /// In en, this message translates to:
  /// **'Battery Level'**
  String get batteryLevel;

  /// Menu item for product/firmware update
  ///
  /// In en, this message translates to:
  /// **'Product Update'**
  String get productUpdate;

  /// Status when device is offline
  ///
  /// In en, this message translates to:
  /// **'Offline'**
  String get offline;

  /// Status when update is available
  ///
  /// In en, this message translates to:
  /// **'Available'**
  String get available;

  /// Dialog title for unpair device confirmation
  ///
  /// In en, this message translates to:
  /// **'Unpair Device'**
  String get unpairDeviceDialogTitle;

  /// Dialog message explaining unpair process
  ///
  /// In en, this message translates to:
  /// **'This will unpair the device so it can be connected to another phone. You will need to go to Settings > Bluetooth and forget the device to complete the process.'**
  String get unpairDeviceDialogMessage;

  /// Button text to confirm unpair action
  ///
  /// In en, this message translates to:
  /// **'Unpair'**
  String get unpair;

  /// Action to unpair and forget device
  ///
  /// In en, this message translates to:
  /// **'Unpair and Forget Device'**
  String get unpairAndForgetDevice;

  /// Default text for unknown device model
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get unknownDevice;

  /// Placeholder for unknown value
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get unknown;

  /// Label for product name field
  ///
  /// In en, this message translates to:
  /// **'Product Name'**
  String get productName;

  /// Label for serial number field
  ///
  /// In en, this message translates to:
  /// **'Serial Number'**
  String get serialNumber;

  /// Status when device is connected
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get connected;

  /// Title for privacy policy page
  ///
  /// In en, this message translates to:
  /// **'Privacy Policy'**
  String get privacyPolicyTitle;

  /// Label for default Omi STT provider
  ///
  /// In en, this message translates to:
  /// **'Omi'**
  String get omiSttProvider;

  /// Message shown when a value is copied
  ///
  /// In en, this message translates to:
  /// **'{label} copied'**
  String labelCopied(String label);

  /// Message when no API keys exist
  ///
  /// In en, this message translates to:
  /// **'No API keys yet'**
  String get noApiKeysYet;

  /// Hint to create first API key
  ///
  /// In en, this message translates to:
  /// **'Create a key to get started'**
  String get createKeyToGetStarted;

  /// Persona feature name
  ///
  /// In en, this message translates to:
  /// **'Persona'**
  String get persona;

  /// Description for persona settings
  ///
  /// In en, this message translates to:
  /// **'Configure your AI persona'**
  String get configureYourAiPersona;

  /// Description for transcription settings
  ///
  /// In en, this message translates to:
  /// **'Configure STT provider'**
  String get configureSttProvider;

  /// Description for conversation timeout setting
  ///
  /// In en, this message translates to:
  /// **'Set when conversations auto-end'**
  String get setWhenConversationsAutoEnd;

  /// Description for import data feature
  ///
  /// In en, this message translates to:
  /// **'Import data from other sources'**
  String get importDataFromOtherSources;

  /// Section header for debug features
  ///
  /// In en, this message translates to:
  /// **'Debug & Diagnostics'**
  String get debugAndDiagnostics;

  /// Description for debug logs auto-delete
  ///
  /// In en, this message translates to:
  /// **'Auto-deletes after 3 days.'**
  String get autoDeletesAfter3Days;

  /// Description for debug logs purpose
  ///
  /// In en, this message translates to:
  /// **'Helps diagnose issues'**
  String get helpsDiagnoseIssues;

  /// Snackbar message when export starts
  ///
  /// In en, this message translates to:
  /// **'Export started. This may take a few seconds...'**
  String get exportStartedMessage;

  /// Description for export feature
  ///
  /// In en, this message translates to:
  /// **'Export conversations to a JSON file'**
  String get exportConversationsToJson;

  /// Success message after deleting knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Knowledge Graph deleted successfully'**
  String get knowledgeGraphDeletedSuccess;

  /// Error message when knowledge graph deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete graph: {error}'**
  String failedToDeleteGraph(String error);

  /// Description for delete knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Clear all nodes and connections'**
  String get clearAllNodesAndConnections;

  /// Description for Claude Desktop config
  ///
  /// In en, this message translates to:
  /// **'Add to claude_desktop_config.json'**
  String get addToClaudeDesktopConfig;

  /// Description for MCP Server feature
  ///
  /// In en, this message translates to:
  /// **'Connect AI assistants to your data'**
  String get connectAiAssistantsToData;

  /// Hint for client secret value
  ///
  /// In en, this message translates to:
  /// **'Use your MCP API key'**
  String get useYourMcpApiKey;

  /// Webhook type for real-time transcript
  ///
  /// In en, this message translates to:
  /// **'Real-time Transcript'**
  String get realTimeTranscript;

  /// Section header for experimental features
  ///
  /// In en, this message translates to:
  /// **'Experimental'**
  String get experimental;

  /// Experimental feature name
  ///
  /// In en, this message translates to:
  /// **'Transcription Diagnostics'**
  String get transcriptionDiagnostics;

  /// Description for transcription diagnostics
  ///
  /// In en, this message translates to:
  /// **'Detailed diagnostic messages'**
  String get detailedDiagnosticMessages;

  /// Experimental feature name
  ///
  /// In en, this message translates to:
  /// **'Auto-create Speakers'**
  String get autoCreateSpeakers;

  /// Description for auto-create speakers
  ///
  /// In en, this message translates to:
  /// **'Auto-create when name detected'**
  String get autoCreateWhenNameDetected;

  /// Experimental feature name
  ///
  /// In en, this message translates to:
  /// **'Follow-up Questions'**
  String get followUpQuestions;

  /// Description for follow-up questions
  ///
  /// In en, this message translates to:
  /// **'Suggest questions after conversations'**
  String get suggestQuestionsAfterConversations;

  /// Experimental feature name
  ///
  /// In en, this message translates to:
  /// **'Goal Tracker'**
  String get goalTracker;

  /// Description for goal tracker
  ///
  /// In en, this message translates to:
  /// **'Track your personal goals on homepage'**
  String get trackPersonalGoalsOnHomepage;

  /// Section header for daily reflection settings
  ///
  /// In en, this message translates to:
  /// **'Daily Reflection'**
  String get dailyReflection;

  /// Description for daily reflection
  ///
  /// In en, this message translates to:
  /// **'Get a 9 PM reminder to reflect on your day'**
  String get get9PmReminderToReflect;

  /// Error message when action item description is empty
  ///
  /// In en, this message translates to:
  /// **'Action item description cannot be empty'**
  String get actionItemDescriptionCannotBeEmpty;

  /// Message shown when changes are saved
  ///
  /// In en, this message translates to:
  /// **'Saved'**
  String get saved;

  /// Label for overdue tasks
  ///
  /// In en, this message translates to:
  /// **'Overdue'**
  String get overdue;

  /// Error message when due date update fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update due date'**
  String get failedToUpdateDueDate;

  /// Menu item to mark action item as incomplete
  ///
  /// In en, this message translates to:
  /// **'Mark Incomplete'**
  String get markIncomplete;

  /// Menu item to edit due date
  ///
  /// In en, this message translates to:
  /// **'Edit Due Date'**
  String get editDueDate;

  /// Title for date picker sheet
  ///
  /// In en, this message translates to:
  /// **'Set Due Date'**
  String get setDueDate;

  /// Menu item to clear due date
  ///
  /// In en, this message translates to:
  /// **'Clear Due Date'**
  String get clearDueDate;

  /// Error message when clearing due date fails
  ///
  /// In en, this message translates to:
  /// **'Failed to clear due date'**
  String get failedToClearDueDate;

  /// Abbreviation for Monday
  ///
  /// In en, this message translates to:
  /// **'Mon'**
  String get mondayAbbr;

  /// Abbreviation for Tuesday
  ///
  /// In en, this message translates to:
  /// **'Tue'**
  String get tuesdayAbbr;

  /// Abbreviation for Wednesday
  ///
  /// In en, this message translates to:
  /// **'Wed'**
  String get wednesdayAbbr;

  /// Abbreviation for Thursday
  ///
  /// In en, this message translates to:
  /// **'Thu'**
  String get thursdayAbbr;

  /// Abbreviation for Friday
  ///
  /// In en, this message translates to:
  /// **'Fri'**
  String get fridayAbbr;

  /// Abbreviation for Saturday
  ///
  /// In en, this message translates to:
  /// **'Sat'**
  String get saturdayAbbr;

  /// Abbreviation for Sunday
  ///
  /// In en, this message translates to:
  /// **'Sun'**
  String get sundayAbbr;

  /// Title asking how SD Card Sync works
  ///
  /// In en, this message translates to:
  /// **'How does it work?'**
  String get howDoesItWork;

  /// Description of SD Card Sync feature
  ///
  /// In en, this message translates to:
  /// **'SD Card Sync will import your memories from the SD Card to the app'**
  String get sdCardSyncDescription;

  /// Step 1: Checking for audio files
  ///
  /// In en, this message translates to:
  /// **'Checks for audio files on the SD Card'**
  String get checksForAudioFiles;

  /// Step 2: Syncing audio files
  ///
  /// In en, this message translates to:
  /// **'Omi then syncs the audio files with the server'**
  String get omiSyncsAudioFiles;

  /// Step 3: Server processing
  ///
  /// In en, this message translates to:
  /// **'The server processes the audio files and creates memories'**
  String get serverProcessesAudio;

  /// Completion message when onboarding is finished
  ///
  /// In en, this message translates to:
  /// **'You\'re all set!'**
  String get youreAllSet;

  /// Welcome message on completion screen
  ///
  /// In en, this message translates to:
  /// **'Welcome to Omi! Your AI companion is ready to assist you with conversations, tasks, and more.'**
  String get welcomeToOmiDescription;

  /// Button to complete onboarding and start using the app
  ///
  /// In en, this message translates to:
  /// **'Start Using Omi'**
  String get startUsingOmi;

  /// Back button label
  ///
  /// In en, this message translates to:
  /// **'Back'**
  String get back;

  /// Keyboard shortcuts section
  ///
  /// In en, this message translates to:
  /// **'Keyboard Shortcuts'**
  String get keyboardShortcuts;

  /// Shortcut to toggle control bar visibility
  ///
  /// In en, this message translates to:
  /// **'Toggle Control Bar'**
  String get toggleControlBar;

  /// Placeholder text when recording keyboard shortcut
  ///
  /// In en, this message translates to:
  /// **'Press keys...'**
  String get pressKeys;

  /// Error message when command key is not pressed
  ///
  /// In en, this message translates to:
  /// **'⌘ required'**
  String get cmdRequired;

  /// Error message when invalid key is pressed for shortcut
  ///
  /// In en, this message translates to:
  /// **'Invalid key'**
  String get invalidKey;

  /// Space key label
  ///
  /// In en, this message translates to:
  /// **'Space'**
  String get space;

  /// Search button and label
  ///
  /// In en, this message translates to:
  /// **'Search'**
  String get search;

  /// Search input placeholder text
  ///
  /// In en, this message translates to:
  /// **'Search...'**
  String get searchPlaceholder;

  /// Title for a conversation without a title
  ///
  /// In en, this message translates to:
  /// **'Untitled Conversation'**
  String get untitledConversation;

  /// Shows number of remaining items
  ///
  /// In en, this message translates to:
  /// **'{count} remaining'**
  String countRemaining(String count);

  /// Menu option to add a new goal
  ///
  /// In en, this message translates to:
  /// **'Add Goal'**
  String get addGoal;

  /// Title for editing an existing goal
  ///
  /// In en, this message translates to:
  /// **'Edit Goal'**
  String get editGoal;

  /// Field label for icon selector
  ///
  /// In en, this message translates to:
  /// **'Icon'**
  String get icon;

  /// Field label for goal title input
  ///
  /// In en, this message translates to:
  /// **'Goal title'**
  String get goalTitle;

  /// Label for current value field
  ///
  /// In en, this message translates to:
  /// **'Current'**
  String get current;

  /// Label for target value field
  ///
  /// In en, this message translates to:
  /// **'Target'**
  String get target;

  /// Save button for goal
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get saveGoal;

  /// Header for goals section
  ///
  /// In en, this message translates to:
  /// **'Goals'**
  String get goals;

  /// Empty state text for goals widget
  ///
  /// In en, this message translates to:
  /// **'Tap to add a goal'**
  String get tapToAddGoal;

  /// Welcome message with user name
  ///
  /// In en, this message translates to:
  /// **'Welcome back, {name}'**
  String welcomeBack(String name);

  /// Title for the conversations page
  ///
  /// In en, this message translates to:
  /// **'Your Conversations'**
  String get yourConversations;

  /// Subtitle explaining what users can do on conversations page
  ///
  /// In en, this message translates to:
  /// **'Review and manage your captured conversations'**
  String get reviewAndManageConversations;

  /// Message explaining how to get started with conversations
  ///
  /// In en, this message translates to:
  /// **'Start capturing conversations with your Omi device to see them here.'**
  String get startCapturingConversations;

  /// Tip about using mobile app for audio capture
  ///
  /// In en, this message translates to:
  /// **'Use your mobile app to capture audio'**
  String get useMobileAppToCapture;

  /// Tip about automatic conversation processing
  ///
  /// In en, this message translates to:
  /// **'Conversations are processed automatically'**
  String get conversationsProcessedAutomatically;

  /// Tip about instant insights feature
  ///
  /// In en, this message translates to:
  /// **'Get insights and summaries instantly'**
  String get getInsightsInstantly;

  /// Button text to show all items
  ///
  /// In en, this message translates to:
  /// **'Show All'**
  String get showAll;

  /// Message shown when there are no tasks due today
  ///
  /// In en, this message translates to:
  /// **'No tasks for today.\\nAsk Omi for more tasks or create manually.'**
  String get noTasksForToday;

  /// Header for daily score widget
  ///
  /// In en, this message translates to:
  /// **'DAILY SCORE'**
  String get dailyScore;

  /// Description text for daily score widget
  ///
  /// In en, this message translates to:
  /// **'A score to help you better\nfocus on execution.'**
  String get dailyScoreDescription;

  /// Badge label for search results section
  ///
  /// In en, this message translates to:
  /// **'Search results'**
  String get searchResults;

  /// Section header for action items
  ///
  /// In en, this message translates to:
  /// **'Action Items'**
  String get actionItems;

  /// Category label for tasks due today
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get tasksToday;

  /// Category label for tasks due tomorrow
  ///
  /// In en, this message translates to:
  /// **'Tomorrow'**
  String get tasksTomorrow;

  /// Category label for tasks without a deadline
  ///
  /// In en, this message translates to:
  /// **'No Deadline'**
  String get tasksNoDeadline;

  /// Category label for tasks due later
  ///
  /// In en, this message translates to:
  /// **'Later'**
  String get tasksLater;

  /// Message shown while tasks are being loaded
  ///
  /// In en, this message translates to:
  /// **'Loading tasks...'**
  String get loadingTasks;

  /// Title for the tasks page
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get tasks;

  /// Instructions for task management gestures
  ///
  /// In en, this message translates to:
  /// **'Swipe tasks to indent, drag between categories'**
  String get swipeTasksToIndent;

  /// Button label to create a new task
  ///
  /// In en, this message translates to:
  /// **'Create'**
  String get create;

  /// Empty state title when there are no tasks
  ///
  /// In en, this message translates to:
  /// **'No Tasks Yet'**
  String get noTasksYet;

  /// Empty state description for tasks page
  ///
  /// In en, this message translates to:
  /// **'Tasks from your conversations will appear here.\nClick Create to add one manually.'**
  String get tasksFromConversationsWillAppear;

  /// January month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Jan'**
  String get monthJan;

  /// February month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Feb'**
  String get monthFeb;

  /// March month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Mar'**
  String get monthMar;

  /// April month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Apr'**
  String get monthApr;

  /// May month abbreviation
  ///
  /// In en, this message translates to:
  /// **'May'**
  String get monthMay;

  /// June month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Jun'**
  String get monthJun;

  /// July month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Jul'**
  String get monthJul;

  /// August month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Aug'**
  String get monthAug;

  /// September month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Sep'**
  String get monthSep;

  /// October month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Oct'**
  String get monthOct;

  /// November month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Nov'**
  String get monthNov;

  /// December month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Dec'**
  String get monthDec;

  /// PM time indicator
  ///
  /// In en, this message translates to:
  /// **'PM'**
  String get timePM;

  /// AM time indicator
  ///
  /// In en, this message translates to:
  /// **'AM'**
  String get timeAM;

  /// Success message when action item is updated
  ///
  /// In en, this message translates to:
  /// **'Action item updated successfully'**
  String get actionItemUpdatedSuccessfully;

  /// Success message when action item is created
  ///
  /// In en, this message translates to:
  /// **'Action item created successfully'**
  String get actionItemCreatedSuccessfully;

  /// Success message when action item is deleted
  ///
  /// In en, this message translates to:
  /// **'Action item deleted successfully'**
  String get actionItemDeletedSuccessfully;

  /// Dialog title for delete confirmation
  ///
  /// In en, this message translates to:
  /// **'Delete Action Item'**
  String get deleteActionItem;

  /// Confirmation message for deleting action item
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete this action item? This action cannot be undone.'**
  String get deleteActionItemConfirmation;

  /// Placeholder text for action item description field
  ///
  /// In en, this message translates to:
  /// **'Enter action item description...'**
  String get enterActionItemDescription;

  /// Label for completion checkbox
  ///
  /// In en, this message translates to:
  /// **'Mark as completed'**
  String get markAsCompleted;

  /// Placeholder for due date picker button
  ///
  /// In en, this message translates to:
  /// **'Set due date and time'**
  String get setDueDateAndTime;

  /// Loading message shown when reloading apps list
  ///
  /// In en, this message translates to:
  /// **'Reloading apps...'**
  String get reloadingApps;

  /// Loading message shown when apps are being loaded
  ///
  /// In en, this message translates to:
  /// **'Loading apps...'**
  String get loadingApps;

  /// Subtitle describing app page functionality
  ///
  /// In en, this message translates to:
  /// **'Browse, install, and create apps'**
  String get browseInstallCreateApps;

  /// Filter label to show all items
  ///
  /// In en, this message translates to:
  /// **'All'**
  String get all;

  /// Button label to open an installed app
  ///
  /// In en, this message translates to:
  /// **'Open'**
  String get open;

  /// Button label to install an app
  ///
  /// In en, this message translates to:
  /// **'Install'**
  String get install;

  /// Empty state title when no apps are available
  ///
  /// In en, this message translates to:
  /// **'No apps available'**
  String get noAppsAvailable;

  /// Empty state title when apps cannot be loaded due to connectivity
  ///
  /// In en, this message translates to:
  /// **'Unable to load apps'**
  String get unableToLoadApps;

  /// Empty state message suggesting to adjust search or filters
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search terms or filters'**
  String get tryAdjustingSearchTermsOrFilters;

  /// Empty state message when no apps are available
  ///
  /// In en, this message translates to:
  /// **'Check back later for new apps'**
  String get checkBackLaterForNewApps;

  /// Empty state message for connectivity issues
  ///
  /// In en, this message translates to:
  /// **'Please check your internet connection and try again'**
  String get pleaseCheckInternetConnectionAndTryAgain;

  /// Title for the create new app page
  ///
  /// In en, this message translates to:
  /// **'Create New App'**
  String get createNewApp;

  /// Subtitle describing the purpose of the create app page
  ///
  /// In en, this message translates to:
  /// **'Build and submit your custom Omi app'**
  String get buildSubmitCustomOmiApp;

  /// Loading message shown while app is being submitted
  ///
  /// In en, this message translates to:
  /// **'Submitting your app...'**
  String get submittingYourApp;

  /// Loading message shown while form is being prepared
  ///
  /// In en, this message translates to:
  /// **'Preparing the form for you...'**
  String get preparingFormForYou;

  /// Section title for app metadata information
  ///
  /// In en, this message translates to:
  /// **'App Details'**
  String get appDetails;

  /// Section title for payment information for paid apps
  ///
  /// In en, this message translates to:
  /// **'Payment Details'**
  String get paymentDetails;

  /// Section title for app preview images
  ///
  /// In en, this message translates to:
  /// **'Preview and Screenshots'**
  String get previewAndScreenshots;

  /// Section title for app capabilities selection
  ///
  /// In en, this message translates to:
  /// **'App Capabilities'**
  String get appCapabilities;

  /// Section title for AI prompt configuration
  ///
  /// In en, this message translates to:
  /// **'AI Prompts'**
  String get aiPrompts;

  /// Label for chat prompt text field
  ///
  /// In en, this message translates to:
  /// **'Chat Prompt'**
  String get chatPrompt;

  /// Placeholder text for chat prompt field
  ///
  /// In en, this message translates to:
  /// **'You are an awesome app, your job is to respond to the user queries and make them feel good...'**
  String get chatPromptPlaceholder;

  /// Section title for conversation prompt
  ///
  /// In en, this message translates to:
  /// **'Conversation Prompt'**
  String get conversationPrompt;

  /// Placeholder text for conversation prompt field
  ///
  /// In en, this message translates to:
  /// **'You are an awesome app, you will be given transcript and summary of a conversation...'**
  String get conversationPromptPlaceholder;

  /// Section title for notification scope configuration
  ///
  /// In en, this message translates to:
  /// **'Notification Scopes'**
  String get notificationScopes;

  /// Section title for privacy and terms agreement
  ///
  /// In en, this message translates to:
  /// **'App Privacy & Terms'**
  String get appPrivacyAndTerms;

  /// Checkbox label for making app publicly available
  ///
  /// In en, this message translates to:
  /// **'Make my app public'**
  String get makeMyAppPublic;

  /// Terms and conditions agreement checkbox text
  ///
  /// In en, this message translates to:
  /// **'By submitting this app, I agree to the Omi AI Terms of Service and Privacy Policy'**
  String get submitAppTermsAgreement;

  /// Button text to submit the app
  ///
  /// In en, this message translates to:
  /// **'Submit App'**
  String get submitApp;

  /// Help banner title
  ///
  /// In en, this message translates to:
  /// **'Need help getting started?'**
  String get needHelpGettingStarted;

  /// Help banner description with link to documentation
  ///
  /// In en, this message translates to:
  /// **'Click here for app building guides and documentation'**
  String get clickHereForAppBuildingGuides;

  /// Confirmation dialog title
  ///
  /// In en, this message translates to:
  /// **'Submit App?'**
  String get submitAppQuestion;

  /// Dialog description for public app submission
  ///
  /// In en, this message translates to:
  /// **'Your app will be reviewed and made public. You can start using it immediately, even during the review!'**
  String get submitAppPublicDescription;

  /// Dialog description for private app submission
  ///
  /// In en, this message translates to:
  /// **'Your app will be reviewed and made available to you privately. You can start using it immediately, even during the review!'**
  String get submitAppPrivateDescription;

  /// Payment setup modal title
  ///
  /// In en, this message translates to:
  /// **'Start Earning! 💰'**
  String get startEarning;

  /// Payment setup modal description
  ///
  /// In en, this message translates to:
  /// **'Connect Stripe or PayPal to receive payments for your app.'**
  String get connectStripeOrPayPal;

  /// Button text to connect payment method
  ///
  /// In en, this message translates to:
  /// **'Connect Now'**
  String get connectNow;

  /// Label for number of app installs
  ///
  /// In en, this message translates to:
  /// **'Installs'**
  String get installsCount;

  /// Button label to uninstall an installed app
  ///
  /// In en, this message translates to:
  /// **'Uninstall App'**
  String get uninstallApp;

  /// Button label to subscribe to a paid app
  ///
  /// In en, this message translates to:
  /// **'Subscribe'**
  String get subscribe;

  /// Dialog title warning about app data access
  ///
  /// In en, this message translates to:
  /// **'Data Access Notice'**
  String get dataAccessNotice;

  /// Warning message about app data access in confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app'**
  String get dataAccessWarning;

  /// Button label to install an app
  ///
  /// In en, this message translates to:
  /// **'Install App'**
  String get installApp;

  /// Notice shown to beta testers of private apps
  ///
  /// In en, this message translates to:
  /// **'You are a beta tester for this app. It is not public yet. It will be public once approved.'**
  String get betaTesterNotice;

  /// Notice shown to app owner when app is under review
  ///
  /// In en, this message translates to:
  /// **'Your app is under review and visible only to you. It will be public once approved.'**
  String get appUnderReviewOwner;

  /// Notice shown when app submission is rejected
  ///
  /// In en, this message translates to:
  /// **'Your app has been rejected. Please update the app details and resubmit for review.'**
  String get appRejectedNotice;

  /// Section title for integration setup steps
  ///
  /// In en, this message translates to:
  /// **'Setup Steps'**
  String get setupSteps;

  /// Title for setup instructions page
  ///
  /// In en, this message translates to:
  /// **'Setup Instructions'**
  String get setupInstructions;

  /// Link label for integration instructions
  ///
  /// In en, this message translates to:
  /// **'Integration Instructions'**
  String get integrationInstructions;

  /// Section title for app preview images
  ///
  /// In en, this message translates to:
  /// **'Preview'**
  String get preview;

  /// Section title for app description
  ///
  /// In en, this message translates to:
  /// **'About the App'**
  String get aboutTheApp;

  /// Section title for persona description
  ///
  /// In en, this message translates to:
  /// **'About the Persona'**
  String get aboutThePersona;

  /// Title for chat personality section
  ///
  /// In en, this message translates to:
  /// **'Chat Personality'**
  String get chatPersonality;

  /// Section title for ratings and reviews
  ///
  /// In en, this message translates to:
  /// **'Ratings & Reviews'**
  String get ratingsAndReviews;

  /// Text shown when app has no ratings
  ///
  /// In en, this message translates to:
  /// **'no ratings'**
  String get noRatings;

  /// Number of ratings for an app
  ///
  /// In en, this message translates to:
  /// **'{count}+ ratings'**
  String ratingsCount(String count);

  /// Dialog title when app activation fails
  ///
  /// In en, this message translates to:
  /// **'Error activating the app'**
  String get errorActivatingApp;

  /// Error message explaining integration setup requirement
  ///
  /// In en, this message translates to:
  /// **'If this is an integration app, make sure the setup is completed.'**
  String get integrationSetupRequired;

  /// Shortened version for installed apps filter
  ///
  /// In en, this message translates to:
  /// **'Installed'**
  String get installed;

  /// Label for the app ID field
  ///
  /// In en, this message translates to:
  /// **'App ID'**
  String get appIdLabel;

  /// Label for the app name field
  ///
  /// In en, this message translates to:
  /// **'App Name'**
  String get appNameLabel;

  /// Placeholder text for app name input
  ///
  /// In en, this message translates to:
  /// **'My Awesome App'**
  String get appNamePlaceholder;

  /// Validation error when app name is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter app name'**
  String get pleaseEnterAppName;

  /// Label for the category field
  ///
  /// In en, this message translates to:
  /// **'Category'**
  String get categoryLabel;

  /// Placeholder text for category dropdown
  ///
  /// In en, this message translates to:
  /// **'Select Category'**
  String get selectCategory;

  /// Label for the description field
  ///
  /// In en, this message translates to:
  /// **'Description'**
  String get descriptionLabel;

  /// Placeholder text for app description input
  ///
  /// In en, this message translates to:
  /// **'My Awesome App is a great app that does amazing things. It is the best app ever!'**
  String get appDescriptionPlaceholder;

  /// Validation error when description is empty
  ///
  /// In en, this message translates to:
  /// **'Please provide a valid description'**
  String get pleaseProvideValidDescription;

  /// Label for the app pricing field
  ///
  /// In en, this message translates to:
  /// **'App Pricing'**
  String get appPricingLabel;

  /// Placeholder text when no pricing option is selected
  ///
  /// In en, this message translates to:
  /// **'None Selected'**
  String get noneSelected;

  /// Success message when app ID is copied
  ///
  /// In en, this message translates to:
  /// **'App ID copied to clipboard'**
  String get appIdCopiedToClipboard;

  /// Title for the category selection modal
  ///
  /// In en, this message translates to:
  /// **'App Category'**
  String get appCategoryModalTitle;

  /// Free pricing option
  ///
  /// In en, this message translates to:
  /// **'Free'**
  String get pricingFree;

  /// Paid pricing option
  ///
  /// In en, this message translates to:
  /// **'Paid'**
  String get pricingPaid;

  /// Loading state message while fetching app capabilities
  ///
  /// In en, this message translates to:
  /// **'Loading capabilities...'**
  String get loadingCapabilities;

  /// Filter option for installed apps
  ///
  /// In en, this message translates to:
  /// **'Installed'**
  String get filterInstalled;

  /// Filter option for user's own apps
  ///
  /// In en, this message translates to:
  /// **'My Apps'**
  String get filterMyApps;

  /// Option to clear the current filter selection
  ///
  /// In en, this message translates to:
  /// **'Clear selection'**
  String get clearSelection;

  /// Category filter dropdown label
  ///
  /// In en, this message translates to:
  /// **'Category'**
  String get filterCategory;

  /// Filter for apps with 4 or more stars
  ///
  /// In en, this message translates to:
  /// **'4+ Stars'**
  String get rating4PlusStars;

  /// Filter for apps with 3 or more stars
  ///
  /// In en, this message translates to:
  /// **'3+ Stars'**
  String get rating3PlusStars;

  /// Filter for apps with 2 or more stars
  ///
  /// In en, this message translates to:
  /// **'2+ Stars'**
  String get rating2PlusStars;

  /// Filter for apps with 1 or more stars
  ///
  /// In en, this message translates to:
  /// **'1+ Stars'**
  String get rating1PlusStars;

  /// Rating filter dropdown label
  ///
  /// In en, this message translates to:
  /// **'Rating'**
  String get filterRating;

  /// Capabilities filter dropdown label
  ///
  /// In en, this message translates to:
  /// **'Capabilities'**
  String get filterCapabilities;

  /// Message shown when no notification scopes are available
  ///
  /// In en, this message translates to:
  /// **'No notification scopes available'**
  String get noNotificationScopesAvailable;

  /// Section title for popular apps
  ///
  /// In en, this message translates to:
  /// **'Popular Apps'**
  String get popularApps;

  /// Validation error when prompt text field is empty
  ///
  /// In en, this message translates to:
  /// **'Please provide a prompt'**
  String get pleaseProvidePrompt;

  /// Chat subtitle with app name
  ///
  /// In en, this message translates to:
  /// **'Chat with {appName}'**
  String chatWithAppName(String appName);

  /// Label for default AI assistant
  ///
  /// In en, this message translates to:
  /// **'Default AI Assistant'**
  String get defaultAiAssistant;

  /// Empty state title when connected
  ///
  /// In en, this message translates to:
  /// **'✨ Ready to chat!'**
  String get readyToChat;

  /// Empty state title when not connected
  ///
  /// In en, this message translates to:
  /// **'🌐 Connection needed'**
  String get connectionNeeded;

  /// Empty state subtitle when connected
  ///
  /// In en, this message translates to:
  /// **'Start a conversation and let the magic begin'**
  String get startConversation;

  /// Empty state subtitle when not connected
  ///
  /// In en, this message translates to:
  /// **'Please check your internet connection'**
  String get checkInternetConnection;

  /// NPS feedback prompt
  ///
  /// In en, this message translates to:
  /// **'Was this helpful?'**
  String get wasThisHelpful;

  /// Feedback confirmation message
  ///
  /// In en, this message translates to:
  /// **'Thank you for your feedback!'**
  String get thankYouForFeedback;

  /// Error message for file upload limit
  ///
  /// In en, this message translates to:
  /// **'You can only upload 4 files at a time'**
  String get maxFilesUploadError;

  /// Label for attached files section
  ///
  /// In en, this message translates to:
  /// **'📎 Attached Files'**
  String get attachedFiles;

  /// Action sheet option to take a photo
  ///
  /// In en, this message translates to:
  /// **'Take Photo'**
  String get takePhoto;

  /// File option: capture with camera subtitle
  ///
  /// In en, this message translates to:
  /// **'Capture with camera'**
  String get captureWithCamera;

  /// File option: select images
  ///
  /// In en, this message translates to:
  /// **'Select Images'**
  String get selectImages;

  /// File option: choose from gallery subtitle
  ///
  /// In en, this message translates to:
  /// **'Choose from gallery'**
  String get chooseFromGallery;

  /// File option: select file
  ///
  /// In en, this message translates to:
  /// **'Select a File'**
  String get selectFile;

  /// File option: choose any file type subtitle
  ///
  /// In en, this message translates to:
  /// **'Choose any file type'**
  String get chooseAnyFileType;

  /// Error when trying to report own message
  ///
  /// In en, this message translates to:
  /// **'You cannot report your own messages'**
  String get cannotReportOwnMessages;

  /// Success message for reported message
  ///
  /// In en, this message translates to:
  /// **'✅ Message reported successfully'**
  String get messageReportedSuccessfully;

  /// Report dialog confirmation text
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to report this message?'**
  String get confirmReportMessage;

  /// App selection modal title
  ///
  /// In en, this message translates to:
  /// **'Select Chat Assistant'**
  String get selectChatAssistant;

  /// Link to enable more apps
  ///
  /// In en, this message translates to:
  /// **'Enable More Apps'**
  String get enableMoreApps;

  /// Snackbar message for cleared chat
  ///
  /// In en, this message translates to:
  /// **'Chat cleared'**
  String get chatCleared;

  /// Clear chat dialog title
  ///
  /// In en, this message translates to:
  /// **'Clear Chat?'**
  String get clearChatTitle;

  /// Clear chat confirmation text
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to clear the chat? This action cannot be undone.'**
  String get confirmClearChat;

  /// Button to copy message text
  ///
  /// In en, this message translates to:
  /// **'Copy'**
  String get copy;

  /// Button to share message
  ///
  /// In en, this message translates to:
  /// **'Share'**
  String get share;

  /// Button to report message
  ///
  /// In en, this message translates to:
  /// **'Report'**
  String get report;

  /// Error message when microphone permission is not granted
  ///
  /// In en, this message translates to:
  /// **'Microphone permission is required for voice recording.'**
  String get microphonePermissionRequired;

  /// Error message when microphone permission is denied
  ///
  /// In en, this message translates to:
  /// **'Microphone permission denied. Please grant permission in System Preferences > Privacy & Security > Microphone.'**
  String get microphonePermissionDenied;

  /// Error message when permission check fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Microphone permission: {error}'**
  String failedToCheckMicrophonePermission(String error);

  /// Error message when audio transcription fails
  ///
  /// In en, this message translates to:
  /// **'Failed to transcribe audio'**
  String get failedToTranscribeAudio;

  /// Loading message while transcribing audio
  ///
  /// In en, this message translates to:
  /// **'Transcribing...'**
  String get transcribing;

  /// Error message when transcription fails
  ///
  /// In en, this message translates to:
  /// **'Transcription failed'**
  String get transcriptionFailed;

  /// Label for a discarded conversation
  ///
  /// In en, this message translates to:
  /// **'Discarded Conversation'**
  String get discardedConversation;

  /// Preposition for time when conversation has no start time
  ///
  /// In en, this message translates to:
  /// **'at'**
  String get at;

  /// Preposition for time range in conversation
  ///
  /// In en, this message translates to:
  /// **'from'**
  String get from;

  /// Button label after copying link
  ///
  /// In en, this message translates to:
  /// **'Copied!'**
  String get copied;

  /// Button label to copy conversation link
  ///
  /// In en, this message translates to:
  /// **'Copy link'**
  String get copyLink;

  /// Button label to hide transcript
  ///
  /// In en, this message translates to:
  /// **'Hide Transcript'**
  String get hideTranscript;

  /// Button label to view transcript
  ///
  /// In en, this message translates to:
  /// **'View Transcript'**
  String get viewTranscript;

  /// Section header for conversation details
  ///
  /// In en, this message translates to:
  /// **'Conversation Details'**
  String get conversationDetails;

  /// Transcript panel title
  ///
  /// In en, this message translates to:
  /// **'Transcript'**
  String get transcript;

  /// Badge showing number of transcript segments
  ///
  /// In en, this message translates to:
  /// **'{count} segments'**
  String segmentsCount(int count);

  /// Empty state title when no transcript
  ///
  /// In en, this message translates to:
  /// **'No Transcript Available'**
  String get noTranscriptAvailable;

  /// Empty state message when no transcript
  ///
  /// In en, this message translates to:
  /// **'This conversation doesn\'t have a transcript.'**
  String get noTranscriptMessage;

  /// Error when URL generation fails
  ///
  /// In en, this message translates to:
  /// **'Conversation URL could not be generated.'**
  String get conversationUrlCouldNotBeGenerated;

  /// Error when link generation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to generate conversation link'**
  String get failedToGenerateConversationLink;

  /// Error when share link generation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to generate share link'**
  String get failedToGenerateShareLink;

  /// Loading message when refreshing conversations
  ///
  /// In en, this message translates to:
  /// **'Reloading conversations...'**
  String get reloadingConversations;

  /// Default fallback name when user name is empty
  ///
  /// In en, this message translates to:
  /// **'User'**
  String get user;

  /// Label for starred folder tab
  ///
  /// In en, this message translates to:
  /// **'Starred'**
  String get starred;

  /// Label for date filter button
  ///
  /// In en, this message translates to:
  /// **'Date'**
  String get date;

  /// Empty state title when search has no results
  ///
  /// In en, this message translates to:
  /// **'No results found'**
  String get noResultsFound;

  /// Empty state message for search with no results
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search terms'**
  String get tryAdjustingSearchTerms;

  /// Empty state message for starred filter
  ///
  /// In en, this message translates to:
  /// **'Star conversations to find them quickly here'**
  String get starConversationsToFindQuickly;

  /// Empty state title when no conversations on selected date
  ///
  /// In en, this message translates to:
  /// **'No conversations on {date}'**
  String noConversationsOnDate(String date);

  /// Empty state message for date filter
  ///
  /// In en, this message translates to:
  /// **'Try selecting a different date'**
  String get trySelectingDifferentDate;

  /// Navigation label for conversations page
  ///
  /// In en, this message translates to:
  /// **'Conversations'**
  String get conversations;

  /// Navigation label for chat page
  ///
  /// In en, this message translates to:
  /// **'Chat'**
  String get chat;

  /// Navigation label for actions page
  ///
  /// In en, this message translates to:
  /// **'Actions'**
  String get actions;

  /// Label for sync notification
  ///
  /// In en, this message translates to:
  /// **'Sync Available'**
  String get syncAvailable;

  /// Bottom navigation label for referral program
  ///
  /// In en, this message translates to:
  /// **'Refer a Friend'**
  String get referAFriend;

  /// Bottom navigation label for help
  ///
  /// In en, this message translates to:
  /// **'Help'**
  String get help;

  /// Badge label for pro/unlimited users
  ///
  /// In en, this message translates to:
  /// **'Pro'**
  String get pro;

  /// Subscription banner button text
  ///
  /// In en, this message translates to:
  /// **'Upgrade to Pro'**
  String get upgradeToPro;

  /// Widget title for device promotion
  ///
  /// In en, this message translates to:
  /// **'Get Omi Device'**
  String get getOmiDevice;

  /// Widget subtitle for device promotion
  ///
  /// In en, this message translates to:
  /// **'Wearable AI companion'**
  String get wearableAiCompanion;

  /// Loading overlay message when reloading memories
  ///
  /// In en, this message translates to:
  /// **'Loading memories...'**
  String get loadingMemories;

  /// Filter option to show all memories
  ///
  /// In en, this message translates to:
  /// **'All Memories'**
  String get allMemories;

  /// Filter option for system memories
  ///
  /// In en, this message translates to:
  /// **'About You'**
  String get aboutYou;

  /// Filter option for manual memories
  ///
  /// In en, this message translates to:
  /// **'Manual'**
  String get manual;

  /// Loading state message
  ///
  /// In en, this message translates to:
  /// **'Loading your memories...'**
  String get loadingYourMemories;

  /// Empty state message when no memories
  ///
  /// In en, this message translates to:
  /// **'Create your first memory to get started'**
  String get createYourFirstMemory;

  /// Empty state message when filter has no results
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search or filter'**
  String get tryAdjustingFilter;

  /// Hint text for memory content input field
  ///
  /// In en, this message translates to:
  /// **'What would you like to remember?'**
  String get whatWouldYouLikeToRemember;

  /// Label for memory category selection section
  ///
  /// In en, this message translates to:
  /// **'Category'**
  String get category;

  /// Option for public memory visibility
  ///
  /// In en, this message translates to:
  /// **'Public'**
  String get public;

  /// Error message when saving memory fails
  ///
  /// In en, this message translates to:
  /// **'Failed to save. Please check your connection.'**
  String get failedToSaveCheckConnection;

  /// Button text to create new memory
  ///
  /// In en, this message translates to:
  /// **'Create Memory'**
  String get createMemory;

  /// Confirmation message for deleting memory
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete this memory? This action cannot be undone.'**
  String get deleteMemoryConfirmation;

  /// Menu option to change memory visibility to private
  ///
  /// In en, this message translates to:
  /// **'Make Private'**
  String get makePrivate;

  /// Subtitle for memory management dialog
  ///
  /// In en, this message translates to:
  /// **'Organize and control your memories'**
  String get organizeAndControlMemories;

  /// Label for total memory count statistic
  ///
  /// In en, this message translates to:
  /// **'Total'**
  String get total;

  /// Action to make all memories private
  ///
  /// In en, this message translates to:
  /// **'Make All Memories Private'**
  String get makeAllMemoriesPrivate;

  /// Description for making all memories private
  ///
  /// In en, this message translates to:
  /// **'Set all memories to private visibility'**
  String get setAllMemoriesToPrivate;

  /// Action to make all memories public
  ///
  /// In en, this message translates to:
  /// **'Make All Memories Public'**
  String get makeAllMemoriesPublic;

  /// Description for making all memories public
  ///
  /// In en, this message translates to:
  /// **'Set all memories to public visibility'**
  String get setAllMemoriesToPublic;

  /// Description for deleting all memories
  ///
  /// In en, this message translates to:
  /// **'Permanently remove all memories from Omi'**
  String get permanentlyRemoveAllMemories;

  /// Success message after making all memories private
  ///
  /// In en, this message translates to:
  /// **'All memories are now private'**
  String get allMemoriesAreNowPrivate;

  /// Success message after making all memories public
  ///
  /// In en, this message translates to:
  /// **'All memories are now public'**
  String get allMemoriesAreNowPublic;

  /// Confirmation dialog title for clearing all memories
  ///
  /// In en, this message translates to:
  /// **'Clear Omi\'s Memory'**
  String get clearOmisMemory;

  /// Confirmation message for clearing all memories
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to clear Omi\'s memory? This action cannot be undone and will permanently delete all {count} memories.'**
  String clearMemoryConfirmation(int count);

  /// Success message after clearing all memories
  ///
  /// In en, this message translates to:
  /// **'Omi\'s memory about you has been cleared'**
  String get omisMemoryCleared;

  /// Welcome message on auth screen
  ///
  /// In en, this message translates to:
  /// **'Welcome to Omi'**
  String get welcomeToOmi;

  /// Button to sign in with Apple
  ///
  /// In en, this message translates to:
  /// **'Continue with Apple'**
  String get continueWithApple;

  /// Button to sign in with Google
  ///
  /// In en, this message translates to:
  /// **'Continue with Google'**
  String get continueWithGoogle;

  /// First part of terms agreement text
  ///
  /// In en, this message translates to:
  /// **'By continuing, you agree to our '**
  String get byContinuingYouAgree;

  /// Terms of Service link text
  ///
  /// In en, this message translates to:
  /// **'Terms of Service'**
  String get termsOfService;

  /// Conjunction between terms and privacy
  ///
  /// In en, this message translates to:
  /// **' and '**
  String get and;

  /// Consent dialog title
  ///
  /// In en, this message translates to:
  /// **'Data & Privacy'**
  String get dataAndPrivacy;

  /// Description for Apple authentication
  ///
  /// In en, this message translates to:
  /// **'Secure authentication via Apple ID'**
  String get secureAuthViaAppleId;

  /// Description for Google authentication
  ///
  /// In en, this message translates to:
  /// **'Secure authentication via Google Account'**
  String get secureAuthViaGoogleAccount;

  /// Section title in consent dialog
  ///
  /// In en, this message translates to:
  /// **'What we collect'**
  String get whatWeCollect;

  /// Explanation of data collection in consent dialog
  ///
  /// In en, this message translates to:
  /// **'By continuing, your conversations, recordings, and personal information will be securely stored on our servers to provide AI-powered insights and enable all app features.'**
  String get dataCollectionMessage;

  /// Section title for data protection info
  ///
  /// In en, this message translates to:
  /// **'Data Protection'**
  String get dataProtection;

  /// First part of data protection text
  ///
  /// In en, this message translates to:
  /// **'Your data is protected and governed by our '**
  String get yourDataIsProtected;

  /// No description provided for @pleaseSelectYourPrimaryLanguage.
  ///
  /// In en, this message translates to:
  /// **'Please select your primary language'**
  String get pleaseSelectYourPrimaryLanguage;

  /// No description provided for @chooseYourLanguage.
  ///
  /// In en, this message translates to:
  /// **'Choose your language'**
  String get chooseYourLanguage;

  /// No description provided for @selectPreferredLanguageForBestExperience.
  ///
  /// In en, this message translates to:
  /// **'Select your preferred language for the best Omi experience'**
  String get selectPreferredLanguageForBestExperience;

  /// No description provided for @searchLanguages.
  ///
  /// In en, this message translates to:
  /// **'Search languages...'**
  String get searchLanguages;

  /// No description provided for @selectALanguage.
  ///
  /// In en, this message translates to:
  /// **'Select a language'**
  String get selectALanguage;

  /// No description provided for @tryDifferentSearchTerm.
  ///
  /// In en, this message translates to:
  /// **'Try a different search term'**
  String get tryDifferentSearchTerm;

  /// No description provided for @pleaseEnterYourName.
  ///
  /// In en, this message translates to:
  /// **'Please enter your name'**
  String get pleaseEnterYourName;

  /// No description provided for @nameMustBeAtLeast2Characters.
  ///
  /// In en, this message translates to:
  /// **'Name must be at least 2 characters'**
  String get nameMustBeAtLeast2Characters;

  /// No description provided for @tellUsHowYouWouldLikeToBeAddressed.
  ///
  /// In en, this message translates to:
  /// **'Tell us how you\'d like to be addressed. This helps personalize your Omi experience.'**
  String get tellUsHowYouWouldLikeToBeAddressed;

  /// No description provided for @charactersCount.
  ///
  /// In en, this message translates to:
  /// **'{count} characters'**
  String charactersCount(int count);

  /// No description provided for @enableFeaturesForBestExperience.
  ///
  /// In en, this message translates to:
  /// **'Enable features for the best Omi experience on your device.'**
  String get enableFeaturesForBestExperience;

  /// No description provided for @microphoneAccess.
  ///
  /// In en, this message translates to:
  /// **'Microphone Access'**
  String get microphoneAccess;

  /// No description provided for @recordAudioConversations.
  ///
  /// In en, this message translates to:
  /// **'Record audio conversations'**
  String get recordAudioConversations;

  /// No description provided for @microphoneAccessDescription.
  ///
  /// In en, this message translates to:
  /// **'Omi needs microphone access to record your conversations and provide transcriptions.'**
  String get microphoneAccessDescription;

  /// No description provided for @screenRecording.
  ///
  /// In en, this message translates to:
  /// **'Screen Recording'**
  String get screenRecording;

  /// No description provided for @captureSystemAudioFromMeetings.
  ///
  /// In en, this message translates to:
  /// **'Capture system audio from meetings'**
  String get captureSystemAudioFromMeetings;

  /// No description provided for @screenRecordingDescription.
  ///
  /// In en, this message translates to:
  /// **'Omi needs screen recording permission to capture system audio from your browser-based meetings.'**
  String get screenRecordingDescription;

  /// No description provided for @accessibility.
  ///
  /// In en, this message translates to:
  /// **'Accessibility'**
  String get accessibility;

  /// No description provided for @detectBrowserBasedMeetings.
  ///
  /// In en, this message translates to:
  /// **'Detect browser-based meetings'**
  String get detectBrowserBasedMeetings;

  /// No description provided for @accessibilityDescription.
  ///
  /// In en, this message translates to:
  /// **'Omi needs accessibility permission to detect when you join Zoom, Meet, or Teams meetings in your browser.'**
  String get accessibilityDescription;

  /// No description provided for @pleaseWait.
  ///
  /// In en, this message translates to:
  /// **'Please wait...'**
  String get pleaseWait;

  /// No description provided for @joinTheCommunity.
  ///
  /// In en, this message translates to:
  /// **'Join the community!'**
  String get joinTheCommunity;

  /// No description provided for @loadingProfile.
  ///
  /// In en, this message translates to:
  /// **'Loading profile...'**
  String get loadingProfile;

  /// No description provided for @profileSettings.
  ///
  /// In en, this message translates to:
  /// **'Profile Settings'**
  String get profileSettings;

  /// No description provided for @noEmailSet.
  ///
  /// In en, this message translates to:
  /// **'No email set'**
  String get noEmailSet;

  /// Success message for User ID copy
  ///
  /// In en, this message translates to:
  /// **'User ID copied to clipboard'**
  String get userIdCopiedToClipboard;

  /// Account information section title
  ///
  /// In en, this message translates to:
  /// **'Your Information'**
  String get yourInformation;

  /// No description provided for @setYourName.
  ///
  /// In en, this message translates to:
  /// **'Set Your Name'**
  String get setYourName;

  /// No description provided for @changeYourName.
  ///
  /// In en, this message translates to:
  /// **'Change Your Name'**
  String get changeYourName;

  /// No description provided for @manageYourOmiPersona.
  ///
  /// In en, this message translates to:
  /// **'Manage your Omi persona'**
  String get manageYourOmiPersona;

  /// Voice and people section title
  ///
  /// In en, this message translates to:
  /// **'Voice & People'**
  String get voiceAndPeople;

  /// No description provided for @teachOmiYourVoice.
  ///
  /// In en, this message translates to:
  /// **'Teach Omi your voice'**
  String get teachOmiYourVoice;

  /// No description provided for @tellOmiWhoSaidIt.
  ///
  /// In en, this message translates to:
  /// **'Tell Omi who said it 🗣️'**
  String get tellOmiWhoSaidIt;

  /// No description provided for @payment.
  ///
  /// In en, this message translates to:
  /// **'Payment'**
  String get payment;

  /// No description provided for @addOrChangeYourPaymentMethod.
  ///
  /// In en, this message translates to:
  /// **'Add or change your payment method'**
  String get addOrChangeYourPaymentMethod;

  /// Preferences section title
  ///
  /// In en, this message translates to:
  /// **'Preferences'**
  String get preferences;

  /// No description provided for @helpImproveOmiBySharing.
  ///
  /// In en, this message translates to:
  /// **'Help improve Omi by sharing anonymized analytics data'**
  String get helpImproveOmiBySharing;

  /// Delete account button
  ///
  /// In en, this message translates to:
  /// **'Delete Account'**
  String get deleteAccount;

  /// No description provided for @deleteYourAccountAndAllData.
  ///
  /// In en, this message translates to:
  /// **'Delete your account and all data'**
  String get deleteYourAccountAndAllData;

  /// No description provided for @clearLogs.
  ///
  /// In en, this message translates to:
  /// **'Clear logs'**
  String get clearLogs;

  /// Success message when logs cleared
  ///
  /// In en, this message translates to:
  /// **'Debug logs cleared'**
  String get debugLogsCleared;

  /// No description provided for @exportConversations.
  ///
  /// In en, this message translates to:
  /// **'Export Conversations'**
  String get exportConversations;

  /// No description provided for @exportAllConversationsToJson.
  ///
  /// In en, this message translates to:
  /// **'Export all your conversations to a JSON file.'**
  String get exportAllConversationsToJson;

  /// No description provided for @conversationsExportStarted.
  ///
  /// In en, this message translates to:
  /// **'Conversations Export Started. This may take a few seconds, please wait.'**
  String get conversationsExportStarted;

  /// No description provided for @mcpDescription.
  ///
  /// In en, this message translates to:
  /// **'To connect Omi with other applications to read, search, and manage your memories and conversations. Create a key to get started.'**
  String get mcpDescription;

  /// No description provided for @apiKeys.
  ///
  /// In en, this message translates to:
  /// **'API Keys'**
  String get apiKeys;

  /// No description provided for @errorLabel.
  ///
  /// In en, this message translates to:
  /// **'Error: {error}'**
  String errorLabel(String error);

  /// No description provided for @noApiKeysFound.
  ///
  /// In en, this message translates to:
  /// **'No API keys found. Create one to get started.'**
  String get noApiKeysFound;

  /// No description provided for @advancedSettings.
  ///
  /// In en, this message translates to:
  /// **'Advanced Settings'**
  String get advancedSettings;

  /// No description provided for @triggersWhenNewConversationCreated.
  ///
  /// In en, this message translates to:
  /// **'Triggers when a new conversation is created.'**
  String get triggersWhenNewConversationCreated;

  /// No description provided for @triggersWhenNewTranscriptReceived.
  ///
  /// In en, this message translates to:
  /// **'Triggers when a new transcript is received.'**
  String get triggersWhenNewTranscriptReceived;

  /// No description provided for @realtimeAudioBytes.
  ///
  /// In en, this message translates to:
  /// **'Realtime Audio Bytes'**
  String get realtimeAudioBytes;

  /// No description provided for @triggersWhenAudioBytesReceived.
  ///
  /// In en, this message translates to:
  /// **'Triggers when audio bytes are received.'**
  String get triggersWhenAudioBytesReceived;

  /// No description provided for @everyXSeconds.
  ///
  /// In en, this message translates to:
  /// **'Every x seconds'**
  String get everyXSeconds;

  /// No description provided for @triggersWhenDaySummaryGenerated.
  ///
  /// In en, this message translates to:
  /// **'Triggers when day summary is generated.'**
  String get triggersWhenDaySummaryGenerated;

  /// No description provided for @tryLatestExperimentalFeatures.
  ///
  /// In en, this message translates to:
  /// **'Try the latest experimental features from Omi Team.'**
  String get tryLatestExperimentalFeatures;

  /// No description provided for @transcriptionServiceDiagnosticStatus.
  ///
  /// In en, this message translates to:
  /// **'Transcription service diagnostic status'**
  String get transcriptionServiceDiagnosticStatus;

  /// No description provided for @enableDetailedDiagnosticMessages.
  ///
  /// In en, this message translates to:
  /// **'Enable detailed diagnostic messages from the transcription service'**
  String get enableDetailedDiagnosticMessages;

  /// No description provided for @autoCreateAndTagNewSpeakers.
  ///
  /// In en, this message translates to:
  /// **'Auto-create and tag new speakers'**
  String get autoCreateAndTagNewSpeakers;

  /// No description provided for @automaticallyCreateNewPerson.
  ///
  /// In en, this message translates to:
  /// **'Automatically create a new person when a name is detected in the transcript.'**
  String get automaticallyCreateNewPerson;

  /// No description provided for @pilotFeatures.
  ///
  /// In en, this message translates to:
  /// **'Pilot Features'**
  String get pilotFeatures;

  /// No description provided for @pilotFeaturesDescription.
  ///
  /// In en, this message translates to:
  /// **'These features are tests and no support is guaranteed.'**
  String get pilotFeaturesDescription;

  /// No description provided for @suggestFollowUpQuestion.
  ///
  /// In en, this message translates to:
  /// **'Suggest follow up question'**
  String get suggestFollowUpQuestion;

  /// Save settings button
  ///
  /// In en, this message translates to:
  /// **'Save Settings'**
  String get saveSettings;

  /// No description provided for @syncingDeveloperSettings.
  ///
  /// In en, this message translates to:
  /// **'Syncing Developer Settings...'**
  String get syncingDeveloperSettings;

  /// No description provided for @summary.
  ///
  /// In en, this message translates to:
  /// **'Summary'**
  String get summary;

  /// No description provided for @auto.
  ///
  /// In en, this message translates to:
  /// **'Auto'**
  String get auto;

  /// Message when app has no summary
  ///
  /// In en, this message translates to:
  /// **'No summary available for this app. Try another app for better results.'**
  String get noSummaryForApp;

  /// No description provided for @tryAnotherApp.
  ///
  /// In en, this message translates to:
  /// **'Try Another App'**
  String get tryAnotherApp;

  /// No description provided for @generatedBy.
  ///
  /// In en, this message translates to:
  /// **'Generated by {appName}'**
  String generatedBy(String appName);

  /// No description provided for @overview.
  ///
  /// In en, this message translates to:
  /// **'Overview'**
  String get overview;

  /// No description provided for @otherAppResults.
  ///
  /// In en, this message translates to:
  /// **'Other App Results'**
  String get otherAppResults;

  /// Fallback name for unknown app
  ///
  /// In en, this message translates to:
  /// **'Unknown App'**
  String get unknownApp;

  /// No description provided for @noSummaryAvailable.
  ///
  /// In en, this message translates to:
  /// **'No Summary Available'**
  String get noSummaryAvailable;

  /// No description provided for @conversationNoSummaryYet.
  ///
  /// In en, this message translates to:
  /// **'This conversation doesn\'t have a summary yet.'**
  String get conversationNoSummaryYet;

  /// No description provided for @chooseSummarizationApp.
  ///
  /// In en, this message translates to:
  /// **'Choose Summarization App'**
  String get chooseSummarizationApp;

  /// No description provided for @setAsDefaultSummarizationApp.
  ///
  /// In en, this message translates to:
  /// **'{appName} set as default summarization app'**
  String setAsDefaultSummarizationApp(String appName);

  /// No description provided for @letOmiChooseAutomatically.
  ///
  /// In en, this message translates to:
  /// **'Let Omi choose the best app automatically'**
  String get letOmiChooseAutomatically;

  /// No description provided for @deleteConversationConfirmation.
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete this conversation? This action cannot be undone.'**
  String get deleteConversationConfirmation;

  /// No description provided for @conversationDeleted.
  ///
  /// In en, this message translates to:
  /// **'Conversation deleted'**
  String get conversationDeleted;

  /// No description provided for @generatingLink.
  ///
  /// In en, this message translates to:
  /// **'Generating link...'**
  String get generatingLink;

  /// No description provided for @editConversation.
  ///
  /// In en, this message translates to:
  /// **'Edit conversation'**
  String get editConversation;

  /// No description provided for @conversationLinkCopiedToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Conversation link copied to clipboard'**
  String get conversationLinkCopiedToClipboard;

  /// No description provided for @conversationTranscriptCopiedToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Conversation transcript copied to clipboard'**
  String get conversationTranscriptCopiedToClipboard;

  /// No description provided for @editConversationDialogTitle.
  ///
  /// In en, this message translates to:
  /// **'Edit Conversation'**
  String get editConversationDialogTitle;

  /// No description provided for @changeTheConversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Change the conversation title'**
  String get changeTheConversationTitle;

  /// No description provided for @conversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Conversation Title'**
  String get conversationTitle;

  /// No description provided for @enterConversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Enter conversation title...'**
  String get enterConversationTitle;

  /// No description provided for @conversationTitleUpdatedSuccessfully.
  ///
  /// In en, this message translates to:
  /// **'Conversation title updated successfully'**
  String get conversationTitleUpdatedSuccessfully;

  /// No description provided for @failedToUpdateConversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Failed to update conversation title'**
  String get failedToUpdateConversationTitle;

  /// No description provided for @errorUpdatingConversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Error updating conversation title'**
  String get errorUpdatingConversationTitle;

  /// Status message when initializing recording
  ///
  /// In en, this message translates to:
  /// **'Setting up...'**
  String get settingUp;

  /// Call-to-action text for first recording
  ///
  /// In en, this message translates to:
  /// **'Start Your First Recording'**
  String get startYourFirstRecording;

  /// Status when preparing audio capture
  ///
  /// In en, this message translates to:
  /// **'Preparing system audio capture'**
  String get preparingSystemAudioCapture;

  /// Instructions for starting recording
  ///
  /// In en, this message translates to:
  /// **'Click the button to capture audio for live transcripts, AI insights, and automatic saving.'**
  String get clickTheButtonToCaptureAudio;

  /// Status when reconnecting to audio
  ///
  /// In en, this message translates to:
  /// **'Reconnecting...'**
  String get reconnecting;

  /// Status when recording is paused
  ///
  /// In en, this message translates to:
  /// **'Recording Paused'**
  String get recordingPaused;

  /// Status when recording is active
  ///
  /// In en, this message translates to:
  /// **'Recording Active'**
  String get recordingActive;

  /// Button text to start recording
  ///
  /// In en, this message translates to:
  /// **'Start Recording'**
  String get startRecording;

  /// Status when auto-resuming with countdown
  ///
  /// In en, this message translates to:
  /// **'Resuming in {countdown}s...'**
  String resumingInCountdown(String countdown);

  /// Instruction when paused
  ///
  /// In en, this message translates to:
  /// **'Tap play to resume'**
  String get tapPlayToResume;

  /// Status when listening for audio
  ///
  /// In en, this message translates to:
  /// **'Listening for audio...'**
  String get listeningForAudio;

  /// Status when preparing to capture
  ///
  /// In en, this message translates to:
  /// **'Preparing audio capture'**
  String get preparingAudioCapture;

  /// Instruction to start recording
  ///
  /// In en, this message translates to:
  /// **'Click to begin recording'**
  String get clickToBeginRecording;

  /// Label for translated text
  ///
  /// In en, this message translates to:
  /// **'translated'**
  String get translated;

  /// Header for live transcript section
  ///
  /// In en, this message translates to:
  /// **'Live Transcript'**
  String get liveTranscript;

  /// Segment count (singular)
  ///
  /// In en, this message translates to:
  /// **'{count} segment'**
  String segmentsSingular(String count);

  /// Segment count (plural)
  ///
  /// In en, this message translates to:
  /// **'{count} segments'**
  String segmentsPlural(String count);

  /// Empty state message for transcript
  ///
  /// In en, this message translates to:
  /// **'Start recording to see live transcript'**
  String get startRecordingToSeeTranscript;

  /// Recording status: paused
  ///
  /// In en, this message translates to:
  /// **'Paused'**
  String get paused;

  /// Recording status: initializing
  ///
  /// In en, this message translates to:
  /// **'Initializing...'**
  String get initializing;

  /// Recording status: recording
  ///
  /// In en, this message translates to:
  /// **'Recording'**
  String get recording;

  /// Status when microphone changed and auto-resuming
  ///
  /// In en, this message translates to:
  /// **'Microphone changed. Resuming in {countdown}s'**
  String microphoneChangedResumingIn(String countdown);

  /// Instruction when paused
  ///
  /// In en, this message translates to:
  /// **'Click play to resume or stop to finish'**
  String get clickPlayToResumeOrStop;

  /// Status when setting up audio capture
  ///
  /// In en, this message translates to:
  /// **'Setting up system audio capture'**
  String get settingUpSystemAudioCapture;

  /// Status when actively recording
  ///
  /// In en, this message translates to:
  /// **'Capturing audio and generating transcript'**
  String get capturingAudioAndGeneratingTranscript;

  /// Instruction to start system audio recording
  ///
  /// In en, this message translates to:
  /// **'Click to begin recording system audio'**
  String get clickToBeginRecordingSystemAudio;

  /// Label for current user in transcript
  ///
  /// In en, this message translates to:
  /// **'You'**
  String get you;

  /// Label for speaker in transcript
  ///
  /// In en, this message translates to:
  /// **'Speaker {speakerId}'**
  String speakerWithId(String speakerId);

  /// Credit line for translations
  ///
  /// In en, this message translates to:
  /// **'translated by omi'**
  String get translatedByOmi;

  /// Back button text
  ///
  /// In en, this message translates to:
  /// **'Back to Conversations'**
  String get backToConversations;

  /// Label for system audio
  ///
  /// In en, this message translates to:
  /// **'System'**
  String get systemAudio;

  /// Label for microphone
  ///
  /// In en, this message translates to:
  /// **'Mic'**
  String get mic;

  /// Success message when audio device changed
  ///
  /// In en, this message translates to:
  /// **'Audio input set to {deviceName}'**
  String audioInputSetTo(String deviceName);

  /// Error message when device switch fails
  ///
  /// In en, this message translates to:
  /// **'Error switching audio device: {error}'**
  String errorSwitchingAudioDevice(String error);

  /// Dropdown header for audio device selection
  ///
  /// In en, this message translates to:
  /// **'Select Audio Input'**
  String get selectAudioInput;

  /// Status when loading audio devices
  ///
  /// In en, this message translates to:
  /// **'Loading devices...'**
  String get loadingDevices;

  /// Settings navigation header
  ///
  /// In en, this message translates to:
  /// **'SETTINGS'**
  String get settingsHeader;

  /// Plans and billing section
  ///
  /// In en, this message translates to:
  /// **'Plans & Billing'**
  String get plansAndBilling;

  /// Calendar integration section
  ///
  /// In en, this message translates to:
  /// **'Calendar Integration'**
  String get calendarIntegration;

  /// Section header for daily summary settings
  ///
  /// In en, this message translates to:
  /// **'Daily Summary'**
  String get dailySummary;

  /// Developer section
  ///
  /// In en, this message translates to:
  /// **'Developer'**
  String get developer;

  /// About section
  ///
  /// In en, this message translates to:
  /// **'About'**
  String get about;

  /// Title for time picker dialog
  ///
  /// In en, this message translates to:
  /// **'Select Time'**
  String get selectTime;

  /// Account group title
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get accountGroup;

  /// Dialog title asking user to confirm sign out
  ///
  /// In en, this message translates to:
  /// **'Sign Out?'**
  String get signOutQuestion;

  /// Confirmation message in sign out dialog
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to sign out?'**
  String get signOutConfirmation;

  /// Custom vocabulary section header
  ///
  /// In en, this message translates to:
  /// **'CUSTOM VOCABULARY'**
  String get customVocabularyHeader;

  /// Custom vocabulary description
  ///
  /// In en, this message translates to:
  /// **'Add words that Omi should recognize during transcription.'**
  String get addWordsDescription;

  /// Text field hint for vocabulary input
  ///
  /// In en, this message translates to:
  /// **'Enter words (comma separated)'**
  String get enterWordsHint;

  /// Daily summary section header
  ///
  /// In en, this message translates to:
  /// **'DAILY SUMMARY'**
  String get dailySummaryHeader;

  /// Daily summary toggle title
  ///
  /// In en, this message translates to:
  /// **'Daily Summary'**
  String get dailySummaryTitle;

  /// Description text for daily summary section
  ///
  /// In en, this message translates to:
  /// **'Get a personalized summary of your day\'s conversations delivered as a notification.'**
  String get dailySummaryDescription;

  /// Label for delivery time setting
  ///
  /// In en, this message translates to:
  /// **'Delivery Time'**
  String get deliveryTime;

  /// Delivery time description
  ///
  /// In en, this message translates to:
  /// **'When to receive your daily summary'**
  String get deliveryTimeDescription;

  /// Subscription section title
  ///
  /// In en, this message translates to:
  /// **'Subscription'**
  String get subscription;

  /// View plans button
  ///
  /// In en, this message translates to:
  /// **'View Plans & Usage'**
  String get viewPlansAndUsage;

  /// View plans description
  ///
  /// In en, this message translates to:
  /// **'Manage your subscription and see usage stats'**
  String get viewPlansDescription;

  /// Payment method description
  ///
  /// In en, this message translates to:
  /// **'Add or change your payment method'**
  String get addOrChangePaymentMethod;

  /// No description provided for @displayOptions.
  ///
  /// In en, this message translates to:
  /// **'Display Options'**
  String get displayOptions;

  /// No description provided for @showMeetingsInMenuBar.
  ///
  /// In en, this message translates to:
  /// **'Show Meetings in Menu Bar'**
  String get showMeetingsInMenuBar;

  /// No description provided for @displayUpcomingMeetingsDescription.
  ///
  /// In en, this message translates to:
  /// **'Display upcoming meetings in the menu bar'**
  String get displayUpcomingMeetingsDescription;

  /// No description provided for @showEventsWithoutParticipants.
  ///
  /// In en, this message translates to:
  /// **'Show Events Without Participants'**
  String get showEventsWithoutParticipants;

  /// No description provided for @includePersonalEventsDescription.
  ///
  /// In en, this message translates to:
  /// **'Include personal events with no attendees'**
  String get includePersonalEventsDescription;

  /// Section header for upcoming meetings in calendar
  ///
  /// In en, this message translates to:
  /// **'Upcoming Meetings'**
  String get upcomingMeetings;

  /// No description provided for @checkingNext7Days.
  ///
  /// In en, this message translates to:
  /// **'Checking the next 7 days'**
  String get checkingNext7Days;

  /// No description provided for @shortcuts.
  ///
  /// In en, this message translates to:
  /// **'Shortcuts'**
  String get shortcuts;

  /// No description provided for @shortcutChangeInstruction.
  ///
  /// In en, this message translates to:
  /// **'Click on a shortcut to change it. Press Escape to cancel.'**
  String get shortcutChangeInstruction;

  /// No description provided for @configurePersonaDescription.
  ///
  /// In en, this message translates to:
  /// **'Configure your AI persona'**
  String get configurePersonaDescription;

  /// No description provided for @configureSTTProvider.
  ///
  /// In en, this message translates to:
  /// **'Configure STT provider'**
  String get configureSTTProvider;

  /// No description provided for @setConversationEndDescription.
  ///
  /// In en, this message translates to:
  /// **'Set when conversations auto-end'**
  String get setConversationEndDescription;

  /// No description provided for @importDataDescription.
  ///
  /// In en, this message translates to:
  /// **'Import data from other sources'**
  String get importDataDescription;

  /// No description provided for @exportConversationsDescription.
  ///
  /// In en, this message translates to:
  /// **'Export conversations to JSON'**
  String get exportConversationsDescription;

  /// Snackbar message when exporting conversations
  ///
  /// In en, this message translates to:
  /// **'Exporting conversations...'**
  String get exportingConversations;

  /// No description provided for @clearNodesDescription.
  ///
  /// In en, this message translates to:
  /// **'Clear all nodes and connections'**
  String get clearNodesDescription;

  /// No description provided for @deleteKnowledgeGraphQuestion.
  ///
  /// In en, this message translates to:
  /// **'Delete Knowledge Graph?'**
  String get deleteKnowledgeGraphQuestion;

  /// No description provided for @deleteKnowledgeGraphWarning.
  ///
  /// In en, this message translates to:
  /// **'This will delete all derived knowledge graph data. Your original memories remain safe.'**
  String get deleteKnowledgeGraphWarning;

  /// No description provided for @connectOmiWithAI.
  ///
  /// In en, this message translates to:
  /// **'Connect Omi with AI assistants'**
  String get connectOmiWithAI;

  /// No description provided for @noAPIKeys.
  ///
  /// In en, this message translates to:
  /// **'No API keys. Create one to get started.'**
  String get noAPIKeys;

  /// No description provided for @autoCreateWhenDetected.
  ///
  /// In en, this message translates to:
  /// **'Auto-create when name detected'**
  String get autoCreateWhenDetected;

  /// No description provided for @trackPersonalGoals.
  ///
  /// In en, this message translates to:
  /// **'Track personal goals on homepage'**
  String get trackPersonalGoals;

  /// Description text for daily reflection section
  ///
  /// In en, this message translates to:
  /// **'Get a reminder at 9 PM to reflect on your day and capture your thoughts.'**
  String get dailyReflectionDescription;

  /// No description provided for @endpointURL.
  ///
  /// In en, this message translates to:
  /// **'Endpoint URL'**
  String get endpointURL;

  /// No description provided for @links.
  ///
  /// In en, this message translates to:
  /// **'Links'**
  String get links;

  /// No description provided for @discordMemberCount.
  ///
  /// In en, this message translates to:
  /// **'8000+ members on Discord'**
  String get discordMemberCount;

  /// No description provided for @userInformation.
  ///
  /// In en, this message translates to:
  /// **'User Information'**
  String get userInformation;

  /// Section title for app capabilities
  ///
  /// In en, this message translates to:
  /// **'Capabilities'**
  String get capabilities;

  /// Section title for preview screenshots
  ///
  /// In en, this message translates to:
  /// **'Preview Screenshots'**
  String get previewScreenshots;

  /// Loading message while preparing form
  ///
  /// In en, this message translates to:
  /// **'Hold on, we are preparing the form for you'**
  String get holdOnPreparingForm;

  /// Text before Terms & Privacy Policy link
  ///
  /// In en, this message translates to:
  /// **'By submitting, you agree to Omi '**
  String get bySubmittingYouAgreeToOmi;

  /// Terms and Privacy Policy link text
  ///
  /// In en, this message translates to:
  /// **'Terms & Privacy Policy'**
  String get termsAndPrivacyPolicy;

  /// No description provided for @helpsDiagnoseIssuesAutoDeletes.
  ///
  /// In en, this message translates to:
  /// **'Helps diagnose issues. Auto-deletes after 3 days.'**
  String get helpsDiagnoseIssuesAutoDeletes;

  /// Title for app management page
  ///
  /// In en, this message translates to:
  /// **'Manage Your App'**
  String get manageYourApp;

  /// Loading message when updating app
  ///
  /// In en, this message translates to:
  /// **'Updating your app'**
  String get updatingYourApp;

  /// Loading message when fetching app details
  ///
  /// In en, this message translates to:
  /// **'Fetching your app details'**
  String get fetchingYourAppDetails;

  /// Dialog title asking to confirm app update
  ///
  /// In en, this message translates to:
  /// **'Update App?'**
  String get updateAppQuestion;

  /// Dialog description explaining app update will be reviewed
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to update your app? The changes will reflect once reviewed by our team.'**
  String get updateAppConfirmation;

  /// Button text to update app
  ///
  /// In en, this message translates to:
  /// **'Update App'**
  String get updateApp;

  /// Button text to create and submit a new app
  ///
  /// In en, this message translates to:
  /// **'Create and submit a new app'**
  String get createAndSubmitNewApp;

  /// Label showing number of installed apps
  ///
  /// In en, this message translates to:
  /// **'Apps ({count})'**
  String appsCount(String count);

  /// Label showing number of private apps
  ///
  /// In en, this message translates to:
  /// **'Private Apps ({count})'**
  String privateAppsCount(String count);

  /// Label showing number of public apps
  ///
  /// In en, this message translates to:
  /// **'Public Apps ({count})'**
  String publicAppsCount(String count);

  /// Dialog title when a new app version is available
  ///
  /// In en, this message translates to:
  /// **'New Version Available  🎉'**
  String get newVersionAvailable;

  /// Button text to decline or dismiss
  ///
  /// In en, this message translates to:
  /// **'No'**
  String get no;

  /// Success message when subscription is cancelled
  ///
  /// In en, this message translates to:
  /// **'Subscription cancelled successfully. It will remain active until the end of the current billing period.'**
  String get subscriptionCancelledSuccessfully;

  /// Error message when subscription cancellation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to cancel subscription. Please try again.'**
  String get failedToCancelSubscription;

  /// Error message for invalid payment URL
  ///
  /// In en, this message translates to:
  /// **'Invalid payment URL'**
  String get invalidPaymentUrl;

  /// Section title for permissions and triggers
  ///
  /// In en, this message translates to:
  /// **'Permissions & Triggers'**
  String get permissionsAndTriggers;

  /// Section title for chat features
  ///
  /// In en, this message translates to:
  /// **'Chat Features'**
  String get chatFeatures;

  /// Button text to uninstall app
  ///
  /// In en, this message translates to:
  /// **'Uninstall'**
  String get uninstall;

  /// Label for install count
  ///
  /// In en, this message translates to:
  /// **'INSTALLS'**
  String get installs;

  /// Label for price
  ///
  /// In en, this message translates to:
  /// **'PRICE'**
  String get priceLabel;

  /// Label for updated date
  ///
  /// In en, this message translates to:
  /// **'UPDATED'**
  String get updatedLabel;

  /// Label for created date
  ///
  /// In en, this message translates to:
  /// **'CREATED'**
  String get createdLabel;

  /// Label for featured status
  ///
  /// In en, this message translates to:
  /// **'FEATURED'**
  String get featuredLabel;

  /// Dialog title for cancel subscription
  ///
  /// In en, this message translates to:
  /// **'Cancel Subscription?'**
  String get cancelSubscriptionQuestion;

  /// Dialog description for cancel subscription
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to cancel your subscription? You will continue to have access until the end of your current billing period.'**
  String get cancelSubscriptionConfirmation;

  /// Button text to cancel subscription
  ///
  /// In en, this message translates to:
  /// **'Cancel Subscription'**
  String get cancelSubscriptionButton;

  /// Loading text while cancelling
  ///
  /// In en, this message translates to:
  /// **'Cancelling...'**
  String get cancelling;

  /// Message shown to beta testers
  ///
  /// In en, this message translates to:
  /// **'You are a beta tester for this app. It is not public yet. It will be public once approved.'**
  String get betaTesterMessage;

  /// Message shown when app is under review
  ///
  /// In en, this message translates to:
  /// **'Your app is under review and visible only to you. It will be public once approved.'**
  String get appUnderReviewMessage;

  /// Message shown when app is rejected
  ///
  /// In en, this message translates to:
  /// **'Your app has been rejected. Please update the app details and resubmit for review.'**
  String get appRejectedMessage;

  /// Error message for invalid integration URL
  ///
  /// In en, this message translates to:
  /// **'Invalid integration URL'**
  String get invalidIntegrationUrl;

  /// Instruction to tap to complete setup
  ///
  /// In en, this message translates to:
  /// **'Tap to complete'**
  String get tapToComplete;

  /// Error message for invalid setup instructions URL
  ///
  /// In en, this message translates to:
  /// **'Invalid setup instructions URL'**
  String get invalidSetupInstructionsUrl;

  /// Capability label for push to talk feature
  ///
  /// In en, this message translates to:
  /// **'Push to Talk'**
  String get pushToTalk;

  /// Title for summary prompt section
  ///
  /// In en, this message translates to:
  /// **'Summary Prompt'**
  String get summaryPrompt;

  /// Error message when no rating selected
  ///
  /// In en, this message translates to:
  /// **'Please select a rating'**
  String get pleaseSelectARating;

  /// Success message when review is added
  ///
  /// In en, this message translates to:
  /// **'Review added successfully 🚀'**
  String get reviewAddedSuccessfully;

  /// Success message when review is updated
  ///
  /// In en, this message translates to:
  /// **'Review updated successfully 🚀'**
  String get reviewUpdatedSuccessfully;

  /// Error message when review submission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to submit review. Please try again.'**
  String get failedToSubmitReview;

  /// Dialog title for adding review
  ///
  /// In en, this message translates to:
  /// **'Add Your Review'**
  String get addYourReview;

  /// Dialog title for editing review
  ///
  /// In en, this message translates to:
  /// **'Edit Your Review'**
  String get editYourReview;

  /// Placeholder text for review input
  ///
  /// In en, this message translates to:
  /// **'Write a review (optional)'**
  String get writeAReviewOptional;

  /// Button text to submit review
  ///
  /// In en, this message translates to:
  /// **'Submit Review'**
  String get submitReview;

  /// Button text to update review
  ///
  /// In en, this message translates to:
  /// **'Update Review'**
  String get updateReview;

  /// Label for user's own review
  ///
  /// In en, this message translates to:
  /// **'Your Review'**
  String get yourReview;

  /// Display name for anonymous users
  ///
  /// In en, this message translates to:
  /// **'Anonymous User'**
  String get anonymousUser;

  /// Dialog description for activation error
  ///
  /// In en, this message translates to:
  /// **'There was an issue activating this app. Please try again.'**
  String get issueActivatingApp;

  /// Description for data access notice dialog
  ///
  /// In en, this message translates to:
  /// **'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app'**
  String get dataAccessNoticeDescription;

  /// Button to copy conversation URL to clipboard
  ///
  /// In en, this message translates to:
  /// **'Copy URL'**
  String get copyUrl;

  /// TXT file format label
  ///
  /// In en, this message translates to:
  /// **'TXT'**
  String get txtFormat;

  /// PDF file format label
  ///
  /// In en, this message translates to:
  /// **'PDF'**
  String get pdfFormat;

  /// Abbreviated Monday
  ///
  /// In en, this message translates to:
  /// **'Mon'**
  String get weekdayMon;

  /// Abbreviated Tuesday
  ///
  /// In en, this message translates to:
  /// **'Tue'**
  String get weekdayTue;

  /// Abbreviated Wednesday
  ///
  /// In en, this message translates to:
  /// **'Wed'**
  String get weekdayWed;

  /// Abbreviated Thursday
  ///
  /// In en, this message translates to:
  /// **'Thu'**
  String get weekdayThu;

  /// Abbreviated Friday
  ///
  /// In en, this message translates to:
  /// **'Fri'**
  String get weekdayFri;

  /// Abbreviated Saturday
  ///
  /// In en, this message translates to:
  /// **'Sat'**
  String get weekdaySat;

  /// Abbreviated Sunday
  ///
  /// In en, this message translates to:
  /// **'Sun'**
  String get weekdaySun;

  /// Message shown when task integration is not yet available
  ///
  /// In en, this message translates to:
  /// **'{serviceName} integration coming soon'**
  String serviceIntegrationComingSoon(String serviceName);

  /// Message shown when task was already exported to a platform
  ///
  /// In en, this message translates to:
  /// **'Already exported to {platform}'**
  String alreadyExportedTo(String platform);

  /// Fallback text for unknown export platform
  ///
  /// In en, this message translates to:
  /// **'another platform'**
  String get anotherPlatform;

  /// Message prompting user to authenticate with a task service
  ///
  /// In en, this message translates to:
  /// **'Please authenticate with {serviceName} in Settings > Task Integrations'**
  String pleaseAuthenticateWithService(String serviceName);

  /// Loading message when adding task to a service
  ///
  /// In en, this message translates to:
  /// **'Adding to {serviceName}...'**
  String addingToService(String serviceName);

  /// Success message when task was added to a service
  ///
  /// In en, this message translates to:
  /// **'Added to {serviceName}'**
  String addedToService(String serviceName);

  /// Error message when task could not be added to a service
  ///
  /// In en, this message translates to:
  /// **'Failed to add to {serviceName}'**
  String failedToAddToService(String serviceName);

  /// Error when Apple Reminders permission is denied
  ///
  /// In en, this message translates to:
  /// **'Permission denied for Apple Reminders'**
  String get permissionDeniedForAppleReminders;

  /// Error message when API key creation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create provider API key: {error}'**
  String failedToCreateApiKey(String error);

  /// Dialog title for creating a new API key
  ///
  /// In en, this message translates to:
  /// **'Create a Key'**
  String get createAKey;

  /// Success message when API key is revoked
  ///
  /// In en, this message translates to:
  /// **'API key revoked successfully'**
  String get apiKeyRevokedSuccessfully;

  /// Error message when API key revocation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to revoke API key: {error}'**
  String failedToRevokeApiKey(String error);

  /// Dialog title for API keys info
  ///
  /// In en, this message translates to:
  /// **'Omi API Keys'**
  String get omiApiKeys;

  /// Description of what API keys are used for
  ///
  /// In en, this message translates to:
  /// **'API Keys are used for authentication when your app communicates with the OMI server. They allow your application to create memories and access other OMI services securely.'**
  String get apiKeysDescription;

  /// Tooltip for API keys info button
  ///
  /// In en, this message translates to:
  /// **'About Omi API Keys'**
  String get aboutOmiApiKeys;

  /// Label shown above newly created API key
  ///
  /// In en, this message translates to:
  /// **'Your new key:'**
  String get yourNewKey;

  /// Tooltip for copy button
  ///
  /// In en, this message translates to:
  /// **'Copy to clipboard'**
  String get copyToClipboard;

  /// Warning to copy key immediately
  ///
  /// In en, this message translates to:
  /// **'Please copy it now and write it down somewhere safe. '**
  String get pleaseCopyKeyNow;

  /// Warning that key won't be shown again
  ///
  /// In en, this message translates to:
  /// **'You will not be able to see it again.'**
  String get willNotSeeAgain;

  /// Tooltip for revoke button
  ///
  /// In en, this message translates to:
  /// **'Revoke key'**
  String get revokeKey;

  /// Confirmation dialog title for revoking API key
  ///
  /// In en, this message translates to:
  /// **'Revoke API Key?'**
  String get revokeApiKeyQuestion;

  /// Warning message about revoking API key
  ///
  /// In en, this message translates to:
  /// **'This action cannot be undone. Any applications using this key will no longer be able to access the API.'**
  String get revokeApiKeyWarning;

  /// Button text to confirm revocation
  ///
  /// In en, this message translates to:
  /// **'Revoke'**
  String get revoke;

  /// Title asking user what they want to create
  ///
  /// In en, this message translates to:
  /// **'What would you like to create?'**
  String get whatWouldYouLikeToCreate;

  /// Option to create an app
  ///
  /// In en, this message translates to:
  /// **'Create an App'**
  String get createAnApp;

  /// Subtitle for create app option
  ///
  /// In en, this message translates to:
  /// **'Create and share your app'**
  String get createAndShareYourApp;

  /// Option to create digital clone
  ///
  /// In en, this message translates to:
  /// **'Create my Clone'**
  String get createMyClone;

  /// Subtitle for create clone option
  ///
  /// In en, this message translates to:
  /// **'Create your digital clone'**
  String get createYourDigitalClone;

  /// The word 'App' used as parameter in other strings
  ///
  /// In en, this message translates to:
  /// **'App'**
  String get itemApp;

  /// The word 'Persona' used as parameter in other strings
  ///
  /// In en, this message translates to:
  /// **'Persona'**
  String get itemPersona;

  /// Toggle label to keep app or persona public
  ///
  /// In en, this message translates to:
  /// **'Keep {item} Public'**
  String keepItemPublic(String item);

  /// Dialog title asking to make app or persona public
  ///
  /// In en, this message translates to:
  /// **'Make {item} Public?'**
  String makeItemPublicQuestion(String item);

  /// Dialog title asking to make app or persona private
  ///
  /// In en, this message translates to:
  /// **'Make {item} Private?'**
  String makeItemPrivateQuestion(String item);

  /// Explanation of what happens when making public
  ///
  /// In en, this message translates to:
  /// **'If you make the {item} public, it can be used by everyone'**
  String makeItemPublicExplanation(String item);

  /// Explanation of what happens when making private
  ///
  /// In en, this message translates to:
  /// **'If you make the {item} private now, it will stop working for everyone and will be visible only to you'**
  String makeItemPrivateExplanation(String item);

  /// Menu item to manage app settings
  ///
  /// In en, this message translates to:
  /// **'Manage App'**
  String get manageApp;

  /// Menu item to update persona details
  ///
  /// In en, this message translates to:
  /// **'Update Persona Details'**
  String get updatePersonaDetails;

  /// Menu item to delete app or persona
  ///
  /// In en, this message translates to:
  /// **'Delete {item}'**
  String deleteItemTitle(String item);

  /// Dialog title asking to confirm deletion
  ///
  /// In en, this message translates to:
  /// **'Delete {item}?'**
  String deleteItemQuestion(String item);

  /// Dialog message explaining deletion is permanent
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete this {item}? This action cannot be undone.'**
  String deleteItemConfirmation(String item);

  /// Dialog title asking to confirm key revocation
  ///
  /// In en, this message translates to:
  /// **'Revoke Key?'**
  String get revokeKeyQuestion;

  /// Dialog message explaining key revocation is permanent
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to revoke the key \"{keyName}\"? This action cannot be undone.'**
  String revokeKeyConfirmation(String keyName);

  /// Dialog title for creating a new API key
  ///
  /// In en, this message translates to:
  /// **'Create New Key'**
  String get createNewKey;

  /// Hint text showing example key name
  ///
  /// In en, this message translates to:
  /// **'e.g., Claude Desktop'**
  String get keyNameHint;

  /// Validation error when name is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter a name.'**
  String get pleaseEnterAName;

  /// Error message with specific error details
  ///
  /// In en, this message translates to:
  /// **'Failed to create key: {error}'**
  String failedToCreateKeyWithError(String error);

  /// Generic error message for key creation failure
  ///
  /// In en, this message translates to:
  /// **'Failed to create key. Please try again.'**
  String get failedToCreateKeyTryAgain;

  /// Dialog title when API key is successfully created
  ///
  /// In en, this message translates to:
  /// **'Key Created'**
  String get keyCreated;

  /// Message explaining to copy the key now as it won't be shown again
  ///
  /// In en, this message translates to:
  /// **'Your new key has been created. Please copy it now. You will not be able to see it again.'**
  String get keyCreatedMessage;

  /// The word 'Key' for use in parameterized strings
  ///
  /// In en, this message translates to:
  /// **'Key'**
  String get keyWord;

  /// Section title for external app access settings
  ///
  /// In en, this message translates to:
  /// **'External App Access'**
  String get externalAppAccess;

  /// Description explaining which apps can access user data
  ///
  /// In en, this message translates to:
  /// **'The following installed apps have external integrations and can access your data, such as conversations and memories.'**
  String get externalAppAccessDescription;

  /// Message shown when no external apps have data access
  ///
  /// In en, this message translates to:
  /// **'No external apps have access to your data.'**
  String get noExternalAppsHaveAccess;

  /// Title for End-to-End Encryption dialog
  ///
  /// In en, this message translates to:
  /// **'Maximum Security (E2EE)'**
  String get maximumSecurityE2ee;

  /// Description of E2EE encryption explaining its benefits
  ///
  /// In en, this message translates to:
  /// **'End-to-end encryption is the gold standard for privacy. When enabled, your data is encrypted on your device before it\'s sent to our servers. This means no one, not even Omi, can access your content.'**
  String get e2eeDescription;

  /// Header for trade-offs section in E2EE dialog
  ///
  /// In en, this message translates to:
  /// **'Important Trade-offs:'**
  String get importantTradeoffs;

  /// First trade-off bullet point for E2EE
  ///
  /// In en, this message translates to:
  /// **'• Some features like external app integrations may be disabled.'**
  String get e2eeTradeoff1;

  /// Second trade-off bullet point for E2EE
  ///
  /// In en, this message translates to:
  /// **'• If you lose your password, your data cannot be recovered.'**
  String get e2eeTradeoff2;

  /// Message indicating a feature is coming soon
  ///
  /// In en, this message translates to:
  /// **'This feature is coming soon!'**
  String get featureComingSoon;

  /// Message shown when data migration is in progress
  ///
  /// In en, this message translates to:
  /// **'Migration in progress. You cannot change the protection level until it is complete.'**
  String get migrationInProgressMessage;

  /// Title shown when data migration fails
  ///
  /// In en, this message translates to:
  /// **'Migration Failed'**
  String get migrationFailed;

  /// Message showing migration progress between protection levels
  ///
  /// In en, this message translates to:
  /// **'Migrating from {source} to {target}'**
  String migratingFromTo(String source, String target);

  /// Shows number of processed objects out of total during migration
  ///
  /// In en, this message translates to:
  /// **'{processed} / {total} objects'**
  String objectsCount(String processed, String total);

  /// Title for secure encryption card
  ///
  /// In en, this message translates to:
  /// **'Secure Encryption'**
  String get secureEncryption;

  /// Description of secure encryption explaining how data is protected
  ///
  /// In en, this message translates to:
  /// **'Your data is encrypted with a key unique to you on our servers, hosted on Google Cloud. This means your raw content is inaccessible to anyone, including Omi staff or Google, directly from the database.'**
  String get secureEncryptionDescription;

  /// Title for E2EE card
  ///
  /// In en, this message translates to:
  /// **'End-to-End Encryption'**
  String get endToEndEncryption;

  /// Description for E2EE card explaining its benefit
  ///
  /// In en, this message translates to:
  /// **'Enable for maximum security where only you can access your data. Tap to learn more.'**
  String get e2eeCardDescription;

  /// Info message explaining data is always encrypted
  ///
  /// In en, this message translates to:
  /// **'Regardless of the level, your data is always encrypted at rest and in transit.'**
  String get dataAlwaysEncrypted;

  /// Label for read-only API key scope
  ///
  /// In en, this message translates to:
  /// **'Read Only'**
  String get readOnlyScope;

  /// Label for full access API key scope
  ///
  /// In en, this message translates to:
  /// **'Full Access'**
  String get fullAccessScope;

  /// Label for read API key scope
  ///
  /// In en, this message translates to:
  /// **'Read'**
  String get readScope;

  /// Label for write API key scope
  ///
  /// In en, this message translates to:
  /// **'Write'**
  String get writeScope;

  /// Title shown when API key is successfully created
  ///
  /// In en, this message translates to:
  /// **'API Key Created!'**
  String get apiKeyCreated;

  /// Warning message when API key is created
  ///
  /// In en, this message translates to:
  /// **'Save this key now! You won\'t be able to see it again.'**
  String get saveKeyWarning;

  /// Label for API key display section
  ///
  /// In en, this message translates to:
  /// **'YOUR API KEY'**
  String get yourApiKey;

  /// Hint text for tap to copy action
  ///
  /// In en, this message translates to:
  /// **'Tap to copy'**
  String get tapToCopy;

  /// Button label to copy API key
  ///
  /// In en, this message translates to:
  /// **'Copy Key'**
  String get copyKey;

  /// Title for create API key sheet
  ///
  /// In en, this message translates to:
  /// **'Create API Key'**
  String get createApiKey;

  /// Subtitle for create API key sheet
  ///
  /// In en, this message translates to:
  /// **'Access your data programmatically'**
  String get accessDataProgrammatically;

  /// Label for key name input field
  ///
  /// In en, this message translates to:
  /// **'KEY NAME'**
  String get keyNameLabel;

  /// Placeholder text for key name input
  ///
  /// In en, this message translates to:
  /// **'e.g., My App Integration'**
  String get keyNamePlaceholder;

  /// Label for permissions section
  ///
  /// In en, this message translates to:
  /// **'PERMISSIONS'**
  String get permissionsLabel;

  /// Info note explaining permission toggles
  ///
  /// In en, this message translates to:
  /// **'R = Read, W = Write. Defaults to read-only if nothing selected.'**
  String get permissionsInfoNote;

  /// Section header for developer API keys
  ///
  /// In en, this message translates to:
  /// **'Developer API'**
  String get developerApi;

  /// Hint text when no API keys exist
  ///
  /// In en, this message translates to:
  /// **'Create a key to get started'**
  String get createAKeyToGetStarted;

  /// Error message with details
  ///
  /// In en, this message translates to:
  /// **'Error: {error}'**
  String errorWithMessage(String error);

  /// Title for the Omi Training page/section
  ///
  /// In en, this message translates to:
  /// **'Omi Training'**
  String get omiTraining;

  /// Label for training data program
  ///
  /// In en, this message translates to:
  /// **'Training Data Program'**
  String get trainingDataProgram;

  /// Description for getting Omi Unlimited free by contributing data
  ///
  /// In en, this message translates to:
  /// **'Get Omi Unlimited for free by contributing your data to train AI models.'**
  String get getOmiUnlimitedFree;

  /// Bullet points explaining training data program benefits
  ///
  /// In en, this message translates to:
  /// **'• Your data helps improve AI models\n• Only non-sensitive data is shared\n• Fully transparent process'**
  String get trainingDataBullets;

  /// Link text to learn more about training
  ///
  /// In en, this message translates to:
  /// **'Learn more at omi.me/training'**
  String get learnMoreAtOmiTraining;

  /// Checkbox label for agreeing to contribute data
  ///
  /// In en, this message translates to:
  /// **'I understand and agree to contribute my data for AI training'**
  String get agreeToContributeData;

  /// Button text to submit request
  ///
  /// In en, this message translates to:
  /// **'Submit Request'**
  String get submitRequest;

  /// Success message after submitting training data request
  ///
  /// In en, this message translates to:
  /// **'Thank you! Your request is under review. We will notify you once approved.'**
  String get thankYouRequestUnderReview;

  /// Message explaining plan remains active until date
  ///
  /// In en, this message translates to:
  /// **'Your plan will remain active until {date}. After that, you will lose access to your unlimited features. Are you sure?'**
  String planRemainsActiveUntil(String date);

  /// Button text to confirm cancellation
  ///
  /// In en, this message translates to:
  /// **'Confirm Cancellation'**
  String get confirmCancellation;

  /// Button text to keep current plan
  ///
  /// In en, this message translates to:
  /// **'Keep My Plan'**
  String get keepMyPlan;

  /// Message that subscription is set to cancel
  ///
  /// In en, this message translates to:
  /// **'Your subscription is set to cancel at the end of the period.'**
  String get subscriptionSetToCancel;

  /// Success message when switched to on-device transcription
  ///
  /// In en, this message translates to:
  /// **'Switched to on-device transcription'**
  String get switchedToOnDevice;

  /// Error message when switching to free plan fails
  ///
  /// In en, this message translates to:
  /// **'Could not switch to free plan. Please try again.'**
  String get couldNotSwitchToFreePlan;

  /// Error message when plans cannot be loaded
  ///
  /// In en, this message translates to:
  /// **'Could not load available plans. Please try again.'**
  String get couldNotLoadPlans;

  /// Error message when selected plan is not available
  ///
  /// In en, this message translates to:
  /// **'Selected plan is not available. Please try again.'**
  String get selectedPlanNotAvailable;

  /// Dialog title for upgrading to annual plan
  ///
  /// In en, this message translates to:
  /// **'Upgrade to Annual Plan'**
  String get upgradeToAnnualPlan;

  /// Header for billing information section
  ///
  /// In en, this message translates to:
  /// **'Important Billing Information:'**
  String get importantBillingInfo;

  /// Info about monthly plan continuing
  ///
  /// In en, this message translates to:
  /// **'Your current monthly plan will continue until the end of your billing period'**
  String get monthlyPlanContinues;

  /// Info about payment method being charged
  ///
  /// In en, this message translates to:
  /// **'Your existing payment method will be charged automatically when your monthly plan ends'**
  String get paymentMethodCharged;

  /// Info about annual subscription starting
  ///
  /// In en, this message translates to:
  /// **'Your 12-month annual subscription will start automatically after the charge'**
  String get annualSubscriptionStarts;

  /// Info about total coverage period
  ///
  /// In en, this message translates to:
  /// **'You\'ll get 13 months of coverage total (current month + 12 months annual)'**
  String get thirteenMonthsCoverage;

  /// Button text to confirm upgrade
  ///
  /// In en, this message translates to:
  /// **'Confirm Upgrade'**
  String get confirmUpgrade;

  /// Dialog title for confirming plan change
  ///
  /// In en, this message translates to:
  /// **'Confirm Plan Change'**
  String get confirmPlanChange;

  /// Button text to confirm and proceed
  ///
  /// In en, this message translates to:
  /// **'Confirm & Proceed'**
  String get confirmAndProceed;

  /// Label when upgrade is scheduled
  ///
  /// In en, this message translates to:
  /// **'Upgrade Scheduled'**
  String get upgradeScheduled;

  /// Button text to change plan
  ///
  /// In en, this message translates to:
  /// **'Change Plan'**
  String get changePlan;

  /// Message when upgrade is already scheduled
  ///
  /// In en, this message translates to:
  /// **'Your upgrade to the annual plan is already scheduled'**
  String get upgradeAlreadyScheduled;

  /// Message showing user is on unlimited plan
  ///
  /// In en, this message translates to:
  /// **'You are on the Unlimited Plan.'**
  String get youAreOnUnlimitedPlan;

  /// Marketing text for unlimited plan
  ///
  /// In en, this message translates to:
  /// **'Your Omi, unleashed. Go unlimited for endless possibilities.'**
  String get yourOmiUnleashed;

  /// Message when plan has ended
  ///
  /// In en, this message translates to:
  /// **'Your plan ended on {date}.\\nResubscribe now - you\'ll be charged immediately for a new billing period.'**
  String planEndedOn(String date);

  /// Message when plan is set to cancel
  ///
  /// In en, this message translates to:
  /// **'Your plan is set to cancel on {date}.\\nResubscribe now to keep your benefits - no charge until {date}.'**
  String planSetToCancelOn(String date);

  /// Info that annual plan starts automatically
  ///
  /// In en, this message translates to:
  /// **'Your annual plan will start automatically when your monthly plan ends.'**
  String get annualPlanStartsAutomatically;

  /// Message showing plan renewal date
  ///
  /// In en, this message translates to:
  /// **'Your plan renews on {date}.'**
  String planRenewsOn(String date);

  /// Feature: unlimited conversations
  ///
  /// In en, this message translates to:
  /// **'Unlimited conversations'**
  String get unlimitedConversations;

  /// Feature: ask Omi anything
  ///
  /// In en, this message translates to:
  /// **'Ask Omi anything about your life'**
  String get askOmiAnything;

  /// Feature: unlock infinite memory
  ///
  /// In en, this message translates to:
  /// **'Unlock Omi\'s infinite memory'**
  String get unlockOmiInfiniteMemory;

  /// Message showing user is on annual plan
  ///
  /// In en, this message translates to:
  /// **'You\'re on the Annual Plan'**
  String get youreOnAnnualPlan;

  /// Message when user already has best plan
  ///
  /// In en, this message translates to:
  /// **'You already have the best value plan. No changes needed.'**
  String get alreadyBestValuePlan;

  /// Error message when plans cannot load
  ///
  /// In en, this message translates to:
  /// **'Unable to load plans'**
  String get unableToLoadPlans;

  /// Message to check connection
  ///
  /// In en, this message translates to:
  /// **'Please check your connection and try again'**
  String get checkConnectionTryAgain;

  /// Button to use free plan
  ///
  /// In en, this message translates to:
  /// **'Use Free Plan'**
  String get useFreePlan;

  /// Continue button text
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get continueText;

  /// Button to resubscribe
  ///
  /// In en, this message translates to:
  /// **'Resubscribe'**
  String get resubscribe;

  /// Error when payment settings cannot open
  ///
  /// In en, this message translates to:
  /// **'Could not open payment settings. Please try again.'**
  String get couldNotOpenPaymentSettings;

  /// Button to manage payment method
  ///
  /// In en, this message translates to:
  /// **'Manage Payment Method'**
  String get managePaymentMethod;

  /// Button text to cancel a subscription
  ///
  /// In en, this message translates to:
  /// **'Cancel Subscription'**
  String get cancelSubscription;

  /// Shows end date
  ///
  /// In en, this message translates to:
  /// **'Ends on {date}'**
  String endsOnDate(String date);

  /// Status label for active
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get active;

  /// Label for free plan
  ///
  /// In en, this message translates to:
  /// **'Free Plan'**
  String get freePlan;

  /// Button to configure settings
  ///
  /// In en, this message translates to:
  /// **'Configure'**
  String get configure;

  /// Privacy page - privacyInformation
  ///
  /// In en, this message translates to:
  /// **'Privacy Information'**
  String get privacyInformation;

  /// Privacy page - yourPrivacyMattersToUs
  ///
  /// In en, this message translates to:
  /// **'Your Privacy Matters to Us'**
  String get yourPrivacyMattersToUs;

  /// Privacy page - privacyIntroText
  ///
  /// In en, this message translates to:
  /// **'At Omi, we take your privacy very seriously. We want to be transparent about the data we collect and how we use it to improve our product for you. Here\'s what you need to know:'**
  String get privacyIntroText;

  /// Privacy page - whatWeTrack
  ///
  /// In en, this message translates to:
  /// **'What We Track'**
  String get whatWeTrack;

  /// Privacy page - anonymityAndPrivacy
  ///
  /// In en, this message translates to:
  /// **'Anonymity and Privacy'**
  String get anonymityAndPrivacy;

  /// Privacy page - optInAndOptOutOptions
  ///
  /// In en, this message translates to:
  /// **'Opt-In and Opt-Out Options'**
  String get optInAndOptOutOptions;

  /// Privacy page - ourCommitment
  ///
  /// In en, this message translates to:
  /// **'Our Commitment'**
  String get ourCommitment;

  /// Privacy page - commitmentText
  ///
  /// In en, this message translates to:
  /// **'We are committed to using the data we collect only to make Omi a better product for you. Your privacy and trust are paramount to us.'**
  String get commitmentText;

  /// Privacy page - thankYouText
  ///
  /// In en, this message translates to:
  /// **'Thank you for being a valued user of Omi. If you have any questions or concerns, feel free to reach out to us to team@basedhardware.com.'**
  String get thankYouText;

  /// WiFi sync settings - wifiSyncSettings
  ///
  /// In en, this message translates to:
  /// **'WiFi Sync Settings'**
  String get wifiSyncSettings;

  /// WiFi sync settings - enterHotspotCredentials
  ///
  /// In en, this message translates to:
  /// **'Enter your phone\'s hotspot credentials'**
  String get enterHotspotCredentials;

  /// WiFi sync settings - wifiSyncUsesHotspot
  ///
  /// In en, this message translates to:
  /// **'WiFi sync uses your phone as a hotspot. Find your hotspot name and password in Settings > Personal Hotspot.'**
  String get wifiSyncUsesHotspot;

  /// WiFi sync settings - hotspotNameSsid
  ///
  /// In en, this message translates to:
  /// **'Hotspot Name (SSID)'**
  String get hotspotNameSsid;

  /// WiFi sync settings - exampleIphoneHotspot
  ///
  /// In en, this message translates to:
  /// **'e.g. iPhone Hotspot'**
  String get exampleIphoneHotspot;

  /// WiFi sync settings - password
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get password;

  /// WiFi sync settings - enterHotspotPassword
  ///
  /// In en, this message translates to:
  /// **'Enter hotspot password'**
  String get enterHotspotPassword;

  /// WiFi sync settings - saveCredentials
  ///
  /// In en, this message translates to:
  /// **'Save Credentials'**
  String get saveCredentials;

  /// WiFi sync settings - clearCredentials
  ///
  /// In en, this message translates to:
  /// **'Clear Credentials'**
  String get clearCredentials;

  /// WiFi sync settings - pleaseEnterHotspotName
  ///
  /// In en, this message translates to:
  /// **'Please enter a hotspot name'**
  String get pleaseEnterHotspotName;

  /// WiFi sync settings - wifiCredentialsSaved
  ///
  /// In en, this message translates to:
  /// **'WiFi credentials saved'**
  String get wifiCredentialsSaved;

  /// WiFi sync settings - wifiCredentialsCleared
  ///
  /// In en, this message translates to:
  /// **'WiFi credentials cleared'**
  String get wifiCredentialsCleared;

  /// Daily summary settings - summaryGeneratedForDate
  ///
  /// In en, this message translates to:
  /// **'Summary generated for {date}'**
  String summaryGeneratedForDate(String date);

  /// Daily summary settings - failedToGenerateSummaryCheckConversations
  ///
  /// In en, this message translates to:
  /// **'Failed to generate summary. Make sure you have conversations for that day.'**
  String get failedToGenerateSummaryCheckConversations;

  /// Daily summary detail - summaryNotFound
  ///
  /// In en, this message translates to:
  /// **'Summary not found'**
  String get summaryNotFound;

  /// Daily summary detail - yourDaysJourney
  ///
  /// In en, this message translates to:
  /// **'Your Day\'s Journey'**
  String get yourDaysJourney;

  /// Daily summary detail - highlights
  ///
  /// In en, this message translates to:
  /// **'Highlights'**
  String get highlights;

  /// Daily summary detail - unresolvedQuestions
  ///
  /// In en, this message translates to:
  /// **'Unresolved Questions'**
  String get unresolvedQuestions;

  /// Daily summary detail - decisions
  ///
  /// In en, this message translates to:
  /// **'Decisions'**
  String get decisions;

  /// Daily summary detail - learnings
  ///
  /// In en, this message translates to:
  /// **'Learnings'**
  String get learnings;

  /// Developer settings - autoDeletesAfterThreeDays
  ///
  /// In en, this message translates to:
  /// **'Auto-deletes after 3 days.'**
  String get autoDeletesAfterThreeDays;

  /// Developer settings - knowledgeGraphDeletedSuccessfully
  ///
  /// In en, this message translates to:
  /// **'Knowledge Graph deleted successfully'**
  String get knowledgeGraphDeletedSuccessfully;

  /// Developer settings - exportStartedMayTakeFewSeconds
  ///
  /// In en, this message translates to:
  /// **'Export started. This may take a few seconds...'**
  String get exportStartedMayTakeFewSeconds;

  /// Developer settings - knowledgeGraphDeleteDescription
  ///
  /// In en, this message translates to:
  /// **'This will delete all derived knowledge graph data (nodes and connections). Your original memories will remain safe. The graph will be rebuilt over time or upon next request.'**
  String get knowledgeGraphDeleteDescription;

  /// Subtitle for Daily Summary menu item in profile settings
  ///
  /// In en, this message translates to:
  /// **'Configure your daily action items digest'**
  String get configureDailySummaryDigest;

  /// Description showing what data types an app accesses, e.g. 'Accesses Conversations & Memories'
  ///
  /// In en, this message translates to:
  /// **'Accesses {dataTypes}'**
  String accessesDataTypes(String dataTypes);

  /// Description showing what triggers an app, e.g. 'triggered by conversation end'
  ///
  /// In en, this message translates to:
  /// **'triggered by {triggerType}'**
  String triggeredByType(String triggerType);

  /// Combined description of app access and trigger
  ///
  /// In en, this message translates to:
  /// **'{accessDescription} and is {triggerDescription}.'**
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription);

  /// Sentence starting with 'Is' for trigger description
  ///
  /// In en, this message translates to:
  /// **'Is {triggerDescription}.'**
  String isTriggeredBy(String triggerDescription);

  /// Message shown when app has no specific data access
  ///
  /// In en, this message translates to:
  /// **'No specific data access configured.'**
  String get noSpecificDataAccessConfigured;

  /// Description of basic plan features in usage page
  ///
  /// In en, this message translates to:
  /// **'1,200 premium mins + unlimited on-device'**
  String get basicPlanDescription;

  /// Unit label for minutes
  ///
  /// In en, this message translates to:
  /// **'minutes'**
  String get minutes;

  /// Fallback text for share stats when period is unknown
  ///
  /// In en, this message translates to:
  /// **'Omi has:'**
  String get omiHas;

  /// Message shown when all premium minutes are used
  ///
  /// In en, this message translates to:
  /// **'Premium minutes used.'**
  String get premiumMinutesUsed;

  /// Link text to setup on-device transcription
  ///
  /// In en, this message translates to:
  /// **'Setup on-device'**
  String get setupOnDevice;

  /// Continuation of premium minutes message
  ///
  /// In en, this message translates to:
  /// **'for unlimited free transcription.'**
  String get forUnlimitedFreeTranscription;

  /// Message showing remaining premium minutes
  ///
  /// In en, this message translates to:
  /// **'{count} premium mins left.'**
  String premiumMinsLeft(int count);

  /// Text indicating on-device is always available
  ///
  /// In en, this message translates to:
  /// **'always available.'**
  String get alwaysAvailable;

  /// Section header for import history
  ///
  /// In en, this message translates to:
  /// **'Import History'**
  String get importHistory;

  /// Message when no imports exist
  ///
  /// In en, this message translates to:
  /// **'No imports yet'**
  String get noImportsYet;

  /// Description for Limitless import option
  ///
  /// In en, this message translates to:
  /// **'Select the .zip file to import!'**
  String get selectZipFileToImport;

  /// Text for other devices placeholder
  ///
  /// In en, this message translates to:
  /// **'Other devices coming soon'**
  String get otherDevicesComingSoon;

  /// Dialog title for deleting Limitless data
  ///
  /// In en, this message translates to:
  /// **'Delete All Limitless Conversations?'**
  String get deleteAllLimitlessConversations;

  /// Warning message in delete dialog
  ///
  /// In en, this message translates to:
  /// **'This will permanently delete all conversations imported from Limitless. This action cannot be undone.'**
  String get deleteAllLimitlessWarning;

  /// Success message after deleting conversations
  ///
  /// In en, this message translates to:
  /// **'Deleted {count} Limitless conversations'**
  String deletedLimitlessConversations(int count);

  /// Error message when delete fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete conversations'**
  String get failedToDeleteConversations;

  /// Menu item to delete imported data
  ///
  /// In en, this message translates to:
  /// **'Delete Imported Data'**
  String get deleteImportedData;

  /// Import job status - pending
  ///
  /// In en, this message translates to:
  /// **'Pending'**
  String get statusPending;

  /// Import job status - processing
  ///
  /// In en, this message translates to:
  /// **'Processing'**
  String get statusProcessing;

  /// Import job status - completed
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get statusCompleted;

  /// Import job status - failed
  ///
  /// In en, this message translates to:
  /// **'Failed'**
  String get statusFailed;

  /// Number of conversations created
  ///
  /// In en, this message translates to:
  /// **'{count} conversations'**
  String nConversations(int count);

  /// Validation message when name field is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter a name'**
  String get pleaseEnterName;

  /// Validation message for name length
  ///
  /// In en, this message translates to:
  /// **'Name must be between 2 and 40 characters'**
  String get nameMustBeBetweenCharacters;

  /// Dialog title for deleting a speech sample
  ///
  /// In en, this message translates to:
  /// **'Delete Sample?'**
  String get deleteSampleQuestion;

  /// Confirmation message for deleting a speech sample
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete {name}\'s sample?'**
  String deleteSampleConfirmation(String name);

  /// Dialog title for confirming deletion
  ///
  /// In en, this message translates to:
  /// **'Confirm Deletion'**
  String get confirmDeletion;

  /// Confirmation message for deleting a person
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete {name}? This will also remove all associated speech samples.'**
  String deletePersonConfirmation(String name);

  /// Help dialog title
  ///
  /// In en, this message translates to:
  /// **'How it works?'**
  String get howItWorksTitle;

  /// Explanation of how people/speech recognition works
  ///
  /// In en, this message translates to:
  /// **'Once a person is created, you can go to a conversation transcript, and assign them their corresponding segments, that way Omi will be able to recognize their speech too!'**
  String get howPeopleWorks;

  /// Hint text for tap to delete action
  ///
  /// In en, this message translates to:
  /// **'Tap to delete'**
  String get tapToDelete;

  /// newTag label
  ///
  /// In en, this message translates to:
  /// **'NEW'**
  String get newTag;

  /// needHelpChatWithUs label
  ///
  /// In en, this message translates to:
  /// **'Need Help? Chat with us'**
  String get needHelpChatWithUs;

  /// localStorageEnabled label
  ///
  /// In en, this message translates to:
  /// **'Local storage enabled'**
  String get localStorageEnabled;

  /// localStorageDisabled label
  ///
  /// In en, this message translates to:
  /// **'Local storage disabled'**
  String get localStorageDisabled;

  /// failedToUpdateSettings message
  ///
  /// In en, this message translates to:
  /// **'Failed to update settings: {error}'**
  String failedToUpdateSettings(String error);

  /// privacyNotice label
  ///
  /// In en, this message translates to:
  /// **'Privacy Notice'**
  String get privacyNotice;

  /// recordingsMayCaptureOthers label
  ///
  /// In en, this message translates to:
  /// **'Recordings may capture others\' voices. Ensure you have consent from all participants before enabling.'**
  String get recordingsMayCaptureOthers;

  /// Label for enable toggle setting
  ///
  /// In en, this message translates to:
  /// **'Enable'**
  String get enable;

  /// Settings label for storing audio locally on phone
  ///
  /// In en, this message translates to:
  /// **'Store Audio on Phone'**
  String get storeAudioOnPhone;

  /// Toggle state label when enabled
  ///
  /// In en, this message translates to:
  /// **'On'**
  String get on;

  /// storeAudioDescription label
  ///
  /// In en, this message translates to:
  /// **'Keep all audio recordings stored locally on your phone. When disabled, only failed uploads are kept to save storage space.'**
  String get storeAudioDescription;

  /// enableLocalStorage label
  ///
  /// In en, this message translates to:
  /// **'Enable Local Storage'**
  String get enableLocalStorage;

  /// cloudStorageEnabled label
  ///
  /// In en, this message translates to:
  /// **'Cloud storage enabled'**
  String get cloudStorageEnabled;

  /// cloudStorageDisabled label
  ///
  /// In en, this message translates to:
  /// **'Cloud storage disabled'**
  String get cloudStorageDisabled;

  /// enableCloudStorage label
  ///
  /// In en, this message translates to:
  /// **'Enable Cloud Storage'**
  String get enableCloudStorage;

  /// Settings label for storing audio on cloud
  ///
  /// In en, this message translates to:
  /// **'Store Audio on Cloud'**
  String get storeAudioOnCloud;

  /// cloudStorageDialogMessage label
  ///
  /// In en, this message translates to:
  /// **'Your real-time recordings will be stored in private cloud storage as you speak.'**
  String get cloudStorageDialogMessage;

  /// storeAudioCloudDescription label
  ///
  /// In en, this message translates to:
  /// **'Store your real-time recordings in private cloud storage as you speak. Audio is captured and saved securely in real-time.'**
  String get storeAudioCloudDescription;

  /// Status text shown while downloading firmware
  ///
  /// In en, this message translates to:
  /// **'Downloading Firmware'**
  String get downloadingFirmware;

  /// Status text shown while installing firmware
  ///
  /// In en, this message translates to:
  /// **'Installing Firmware'**
  String get installingFirmware;

  /// Warning message during firmware update
  ///
  /// In en, this message translates to:
  /// **'Do not close the app or turn off the device. This could corrupt your device.'**
  String get firmwareUpdateWarning;

  /// Success message when firmware update is complete
  ///
  /// In en, this message translates to:
  /// **'Firmware Updated'**
  String get firmwareUpdated;

  /// Message asking user to restart device after update. {deviceName} is the device name.
  ///
  /// In en, this message translates to:
  /// **'Please restart your {deviceName} to complete the update.'**
  String restartDeviceToComplete(Object deviceName);

  /// Message shown when device firmware is current
  ///
  /// In en, this message translates to:
  /// **'Your device is up to date'**
  String get yourDeviceIsUpToDate;

  /// Label for current firmware version
  ///
  /// In en, this message translates to:
  /// **'Current Version'**
  String get currentVersion;

  /// Label for latest available firmware version
  ///
  /// In en, this message translates to:
  /// **'Latest Version'**
  String get latestVersion;

  /// Section header for changelog
  ///
  /// In en, this message translates to:
  /// **'What\'s New'**
  String get whatsNew;

  /// Button text to install firmware update
  ///
  /// In en, this message translates to:
  /// **'Install Update'**
  String get installUpdate;

  /// Button text to start firmware update
  ///
  /// In en, this message translates to:
  /// **'Update Now'**
  String get updateNow;

  /// Link text to firmware update help
  ///
  /// In en, this message translates to:
  /// **'Update Guide'**
  String get updateGuide;

  /// Title shown while checking for updates
  ///
  /// In en, this message translates to:
  /// **'Checking for Updates'**
  String get checkingForUpdates;

  /// Status text while checking firmware version
  ///
  /// In en, this message translates to:
  /// **'Checking firmware version...'**
  String get checkingFirmwareVersion;

  /// Page title for firmware update screen
  ///
  /// In en, this message translates to:
  /// **'Firmware Update'**
  String get firmwareUpdate;

  /// Page title for payments settings
  ///
  /// In en, this message translates to:
  /// **'Payments'**
  String get payments;

  /// Info message explaining how to connect payment method
  ///
  /// In en, this message translates to:
  /// **'Connect a payment method below to start receiving payouts for your apps.'**
  String get connectPaymentMethodInfo;

  /// Section header for selected payment method
  ///
  /// In en, this message translates to:
  /// **'Selected Payment Method'**
  String get selectedPaymentMethod;

  /// Section header for available payment methods
  ///
  /// In en, this message translates to:
  /// **'Available Payment Methods'**
  String get availablePaymentMethods;

  /// Status label when payment method is active
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get activeStatus;

  /// Status label when payment method is connected
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get connectedStatus;

  /// Status label when payment method is not connected
  ///
  /// In en, this message translates to:
  /// **'Not Connected'**
  String get notConnectedStatus;

  /// Button to set payment method as active
  ///
  /// In en, this message translates to:
  /// **'Set Active'**
  String get setActive;

  /// Title for Stripe setup page
  ///
  /// In en, this message translates to:
  /// **'Get paid for your app sales through Stripe'**
  String get getPaidThroughStripe;

  /// Feature title for monthly payouts
  ///
  /// In en, this message translates to:
  /// **'Monthly payouts'**
  String get monthlyPayouts;

  /// Description of monthly payout feature
  ///
  /// In en, this message translates to:
  /// **'Receive monthly payments directly to your account when you reach \$10 in earnings'**
  String get monthlyPayoutsDescription;

  /// Feature title for security
  ///
  /// In en, this message translates to:
  /// **'Secure and reliable'**
  String get secureAndReliable;

  /// Description of Stripe security feature
  ///
  /// In en, this message translates to:
  /// **'Stripe ensures safe and timely transfers of your app revenue'**
  String get stripeSecureDescription;

  /// Placeholder for country selector
  ///
  /// In en, this message translates to:
  /// **'Select your country'**
  String get selectYourCountry;

  /// Warning that country selection cannot be changed
  ///
  /// In en, this message translates to:
  /// **'Your country selection is permanent and cannot be changed later.'**
  String get countrySelectionPermanent;

  /// Legal agreement intro text
  ///
  /// In en, this message translates to:
  /// **'By clicking on \"Connect Now\" you agree to the'**
  String get byClickingConnectNow;

  /// Link text for Stripe agreement
  ///
  /// In en, this message translates to:
  /// **'Stripe Connected Account Agreement'**
  String get stripeConnectedAccountAgreement;

  /// Error message when Stripe connection fails
  ///
  /// In en, this message translates to:
  /// **'Error connecting to Stripe! Please try again later.'**
  String get errorConnectingToStripe;

  /// Title during Stripe connection process
  ///
  /// In en, this message translates to:
  /// **'Connecting your Stripe account'**
  String get connectingYourStripeAccount;

  /// Instructions for completing Stripe onboarding
  ///
  /// In en, this message translates to:
  /// **'Please complete the Stripe onboarding process in your browser. This page will automatically update once completed.'**
  String get stripeOnboardingInstructions;

  /// Button to retry failed connection
  ///
  /// In en, this message translates to:
  /// **'Failed? Try Again'**
  String get failedTryAgain;

  /// Button to defer connection
  ///
  /// In en, this message translates to:
  /// **'I\'ll do it later'**
  String get illDoItLater;

  /// Title when connection succeeds
  ///
  /// In en, this message translates to:
  /// **'Successfully Connected!'**
  String get successfullyConnected;

  /// Description after successful connection
  ///
  /// In en, this message translates to:
  /// **'Your Stripe account is now ready to receive payments. You can start earning from your app sales right away.'**
  String get stripeReadyForPayments;

  /// Button to update Stripe details
  ///
  /// In en, this message translates to:
  /// **'Update Stripe Details'**
  String get updateStripeDetails;

  /// Error message when Stripe update fails
  ///
  /// In en, this message translates to:
  /// **'Error updating Stripe details! Please try again later.'**
  String get errorUpdatingStripeDetails;

  /// App bar title when updating PayPal
  ///
  /// In en, this message translates to:
  /// **'Update PayPal'**
  String get updatePayPal;

  /// App bar title when setting up PayPal
  ///
  /// In en, this message translates to:
  /// **'Set Up PayPal'**
  String get setUpPayPal;

  /// Description when updating PayPal account
  ///
  /// In en, this message translates to:
  /// **'Update your PayPal account details'**
  String get updatePayPalAccountDetails;

  /// Description when connecting PayPal account
  ///
  /// In en, this message translates to:
  /// **'Connect your PayPal account to start receiving payments for your apps'**
  String get connectPayPalToReceivePayments;

  /// Label for PayPal email field
  ///
  /// In en, this message translates to:
  /// **'PayPal Email'**
  String get paypalEmail;

  /// Label for PayPal.me link field
  ///
  /// In en, this message translates to:
  /// **'PayPal.me Link'**
  String get paypalMeLink;

  /// Info message recommending Stripe over PayPal
  ///
  /// In en, this message translates to:
  /// **'If Stripe is available in your country, we highly recommend using it for faster and easier payouts.'**
  String get stripeRecommendation;

  /// Button text to update PayPal details
  ///
  /// In en, this message translates to:
  /// **'Update PayPal Details'**
  String get updatePayPalDetails;

  /// Button text to save PayPal details
  ///
  /// In en, this message translates to:
  /// **'Save PayPal Details'**
  String get savePayPalDetails;

  /// Validation error for empty PayPal email
  ///
  /// In en, this message translates to:
  /// **'Please enter your PayPal email'**
  String get pleaseEnterPayPalEmail;

  /// Validation error for empty PayPal.me link
  ///
  /// In en, this message translates to:
  /// **'Please enter your PayPal.me link'**
  String get pleaseEnterPayPalMeLink;

  /// Validation error for http/https/www in link
  ///
  /// In en, this message translates to:
  /// **'Do not include http or https or www in the link'**
  String get doNotIncludeHttpInLink;

  /// Validation error for invalid PayPal.me link
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid PayPal.me link'**
  String get pleaseEnterValidPayPalMeLink;

  /// No description provided for @pleaseEnterValidEmail.
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid email address'**
  String get pleaseEnterValidEmail;

  /// Status message shown while recordings are being synced
  ///
  /// In en, this message translates to:
  /// **'Syncing your recordings'**
  String get syncingYourRecordings;

  /// Label prompting user to sync their recordings
  ///
  /// In en, this message translates to:
  /// **'Sync your recordings'**
  String get syncYourRecordings;

  /// Button text to start syncing recordings immediately
  ///
  /// In en, this message translates to:
  /// **'Sync Now'**
  String get syncNow;

  /// Generic error label shown when an operation fails
  ///
  /// In en, this message translates to:
  /// **'Error'**
  String get error;

  /// Title for the speech samples page
  ///
  /// In en, this message translates to:
  /// **'Speech Samples'**
  String get speechSamples;

  /// Title for additional speech samples with index number
  ///
  /// In en, this message translates to:
  /// **'Additional Sample {index}'**
  String additionalSampleIndex(String index);

  /// Shows the duration of a speech sample in seconds
  ///
  /// In en, this message translates to:
  /// **'Duration: {seconds} seconds'**
  String durationSeconds(String seconds);

  /// Confirmation message when an additional speech sample is deleted
  ///
  /// In en, this message translates to:
  /// **'Additional Speech Sample Removed'**
  String get additionalSpeechSampleRemoved;

  /// Consent message explaining how user data will be stored and used
  ///
  /// In en, this message translates to:
  /// **'By continuing, all data you share with this app (including your conversations, recordings, and personal information) will be securely stored on our servers to provide you with AI-powered insights and enable all app features.'**
  String get consentDataMessage;

  /// Empty state message shown when there are no tasks, with instruction to tap + button
  ///
  /// In en, this message translates to:
  /// **'Tasks from your conversations will appear here.\nTap + to create one manually.'**
  String get tasksEmptyStateMessage;

  /// Menu item text for clearing chat history
  ///
  /// In en, this message translates to:
  /// **'Clear Chat'**
  String get clearChatAction;

  /// Menu item text to navigate to apps page and enable more chat apps
  ///
  /// In en, this message translates to:
  /// **'Enable Apps'**
  String get enableApps;

  /// The Omi app/assistant name shown in chat app selection
  ///
  /// In en, this message translates to:
  /// **'Omi'**
  String get omiAppName;

  /// Text shown to expand collapsed content, with down arrow
  ///
  /// In en, this message translates to:
  /// **'show more ↓'**
  String get showMore;

  /// Text shown to collapse expanded content, with up arrow
  ///
  /// In en, this message translates to:
  /// **'show less ↑'**
  String get showLess;

  /// Loading message shown while audio waveform is being processed
  ///
  /// In en, this message translates to:
  /// **'Loading your recording...'**
  String get loadingYourRecording;

  /// Message shown when a photo was discarded as not significant
  ///
  /// In en, this message translates to:
  /// **'This photo was discarded as it was not significant.'**
  String get photoDiscardedMessage;

  /// Loading text shown while analyzing a photo
  ///
  /// In en, this message translates to:
  /// **'Analyzing...'**
  String get analyzing;

  /// Placeholder text for country search field
  ///
  /// In en, this message translates to:
  /// **'Search countries...'**
  String get searchCountries;

  /// Loading text while checking Apple Watch status
  ///
  /// In en, this message translates to:
  /// **'Checking Apple Watch...'**
  String get checkingAppleWatch;

  /// Title prompting user to install Omi on Apple Watch
  ///
  /// In en, this message translates to:
  /// **'Install Omi on your\nApple Watch'**
  String get installOmiOnAppleWatch;

  /// Description explaining need to install Omi app on watch
  ///
  /// In en, this message translates to:
  /// **'To use your Apple Watch with Omi, you need to install the Omi app on your watch first.'**
  String get installOmiOnAppleWatchDescription;

  /// Title prompting user to open Omi on Apple Watch
  ///
  /// In en, this message translates to:
  /// **'Open Omi on your\nApple Watch'**
  String get openOmiOnAppleWatch;

  /// Description explaining Omi is installed and user should open it
  ///
  /// In en, this message translates to:
  /// **'The Omi app is installed on your Apple Watch. Open it and tap Start to begin.'**
  String get openOmiOnAppleWatchDescription;

  /// Button text to open Watch app on iPhone
  ///
  /// In en, this message translates to:
  /// **'Open Watch App'**
  String get openWatchApp;

  /// Button text confirming user has installed and opened the app
  ///
  /// In en, this message translates to:
  /// **'I\'ve Installed & Opened the App'**
  String get iveInstalledAndOpenedTheApp;

  /// Error message when Watch app cannot be opened automatically
  ///
  /// In en, this message translates to:
  /// **'Unable to open Apple Watch app. Please manually open the Watch app on your Apple Watch and install Omi from the \"Available Apps\" section.'**
  String get unableToOpenWatchApp;

  /// Success message when Apple Watch connects
  ///
  /// In en, this message translates to:
  /// **'Apple Watch connected successfully!'**
  String get appleWatchConnectedSuccessfully;

  /// Error message when Apple Watch is not reachable
  ///
  /// In en, this message translates to:
  /// **'Apple Watch still not reachable. Please make sure the Omi app is open on your watch.'**
  String get appleWatchNotReachable;

  /// Error message with error details when connection check fails
  ///
  /// In en, this message translates to:
  /// **'Error checking connection: {error}'**
  String errorCheckingConnection(String error);

  /// Status text shown when microphone is muted
  ///
  /// In en, this message translates to:
  /// **'Muted'**
  String get muted;

  /// Button text to process/summarize the conversation immediately
  ///
  /// In en, this message translates to:
  /// **'Process Now'**
  String get processNow;

  /// Dialog title asking if user wants to end conversation
  ///
  /// In en, this message translates to:
  /// **'Finished Conversation?'**
  String get finishedConversation;

  /// Confirmation message for stopping recording and summarizing
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to stop recording and summarize the conversation now?'**
  String get stopRecordingConfirmation;

  /// Hint text explaining conversation only ends manually
  ///
  /// In en, this message translates to:
  /// **'Conversation will only end manually.'**
  String get conversationEndsManually;

  /// Hint text showing how many minutes of silence before auto-summary
  ///
  /// In en, this message translates to:
  /// **'Conversation is summarized after {minutes} minute{suffix} of no speech.'**
  String conversationSummarizedAfterMinutes(int minutes, String suffix);

  /// Checkbox label to not show confirmation dialog again
  ///
  /// In en, this message translates to:
  /// **'Don\'t ask me again'**
  String get dontAskAgain;

  /// Placeholder text shown while waiting for content
  ///
  /// In en, this message translates to:
  /// **'Waiting for transcript or photos...'**
  String get waitingForTranscriptOrPhotos;

  /// Text shown when no summary is available yet
  ///
  /// In en, this message translates to:
  /// **'No summary yet'**
  String get noSummaryYet;

  /// Label for hints section with dynamic text
  ///
  /// In en, this message translates to:
  /// **'Hints: {text}'**
  String hints(String text);

  /// Developer option to test prompts
  ///
  /// In en, this message translates to:
  /// **'Test a Conversation Prompt'**
  String get testConversationPrompt;

  /// Label for prompt input field
  ///
  /// In en, this message translates to:
  /// **'Prompt'**
  String get prompt;

  /// Label for result output
  ///
  /// In en, this message translates to:
  /// **'Result:'**
  String get result;

  /// App bar title for comparing transcripts from different services
  ///
  /// In en, this message translates to:
  /// **'Compare Transcripts'**
  String get compareTranscripts;

  /// Label for thumbs down button to indicate response was not helpful
  ///
  /// In en, this message translates to:
  /// **'Not Helpful'**
  String get notHelpful;

  /// Banner message promoting task export integration feature
  ///
  /// In en, this message translates to:
  /// **'Export tasks with one tap!'**
  String get exportTasksWithOneTap;

  /// Title for conversation being processed
  ///
  /// In en, this message translates to:
  /// **'In progress'**
  String get inProgress;

  /// Tab label for photos content
  ///
  /// In en, this message translates to:
  /// **'Photos'**
  String get photos;

  /// Tab label for raw data content
  ///
  /// In en, this message translates to:
  /// **'Raw Data'**
  String get rawData;

  /// Tab label for content
  ///
  /// In en, this message translates to:
  /// **'Content'**
  String get content;

  /// Message when there is no content available
  ///
  /// In en, this message translates to:
  /// **'No content to display'**
  String get noContentToDisplay;

  /// Message when no summary is available
  ///
  /// In en, this message translates to:
  /// **'No summary'**
  String get noSummary;

  /// Button text to update Omi device firmware
  ///
  /// In en, this message translates to:
  /// **'Update omi firmware'**
  String get updateOmiFirmware;

  /// Generic error message asking user to try again
  ///
  /// In en, this message translates to:
  /// **'An error occurred. Please try again.'**
  String get anErrorOccurredTryAgain;

  /// Simple welcome message without user name
  ///
  /// In en, this message translates to:
  /// **'Welcome back'**
  String get welcomeBackSimple;

  /// Description for custom vocabulary section
  ///
  /// In en, this message translates to:
  /// **'Add words that Omi should recognize during transcription.'**
  String get addVocabularyDescription;

  /// Placeholder hint for vocabulary input field
  ///
  /// In en, this message translates to:
  /// **'Enter words (comma separated)'**
  String get enterWordsCommaSeparated;

  /// Description for delivery time setting
  ///
  /// In en, this message translates to:
  /// **'When to receive your daily summary'**
  String get whenToReceiveDailySummary;

  /// Subtitle for no upcoming meetings state
  ///
  /// In en, this message translates to:
  /// **'Checking the next 7 days'**
  String get checkingNextSevenDays;

  /// Error message when deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete: {error}'**
  String failedToDeleteError(String error);

  /// Section header for developer API keys
  ///
  /// In en, this message translates to:
  /// **'Developer API Keys'**
  String get developerApiKeys;

  /// Empty state for MCP API keys section
  ///
  /// In en, this message translates to:
  /// **'No API keys. Create one to get started.'**
  String get noApiKeysCreateOne;

  /// Error message when command key is not pressed for shortcut
  ///
  /// In en, this message translates to:
  /// **'⌘ required'**
  String get commandRequired;

  /// Display name for the space key in shortcuts
  ///
  /// In en, this message translates to:
  /// **'Space'**
  String get spaceKey;

  /// Button text showing number of items remaining to load
  ///
  /// In en, this message translates to:
  /// **'Load More ({count} remaining)'**
  String loadMoreRemaining(String count);

  /// Badge showing user percentile ranking in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Top {percentile}% User'**
  String wrappedTopPercentUser(String percentile);

  /// Label for minutes stat in Wrapped
  ///
  /// In en, this message translates to:
  /// **'minutes'**
  String get wrappedMinutes;

  /// Label for conversations stat in Wrapped
  ///
  /// In en, this message translates to:
  /// **'conversations'**
  String get wrappedConversations;

  /// Label for days active stat in Wrapped
  ///
  /// In en, this message translates to:
  /// **'days active'**
  String get wrappedDaysActive;

  /// Badge for top categories in Wrapped
  ///
  /// In en, this message translates to:
  /// **'You Talked About'**
  String get wrappedYouTalkedAbout;

  /// Badge for action items in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Action Items'**
  String get wrappedActionItems;

  /// Label for tasks created in Wrapped
  ///
  /// In en, this message translates to:
  /// **'tasks created'**
  String get wrappedTasksCreated;

  /// Label for completed tasks in Wrapped
  ///
  /// In en, this message translates to:
  /// **'completed'**
  String get wrappedCompleted;

  /// Completion rate badge in Wrapped
  ///
  /// In en, this message translates to:
  /// **'{rate}% completion rate'**
  String wrappedCompletionRate(String rate);

  /// Badge for top days in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Your Top Days'**
  String get wrappedYourTopDays;

  /// Badge for best moments in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Best Moments'**
  String get wrappedBestMoments;

  /// Badge for buddies in Wrapped
  ///
  /// In en, this message translates to:
  /// **'My Buddies'**
  String get wrappedMyBuddies;

  /// Badge for obsessions in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t Stop Talking About'**
  String get wrappedCouldntStopTalkingAbout;

  /// Label for show obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'SHOW'**
  String get wrappedShow;

  /// Label for movie obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'MOVIE'**
  String get wrappedMovie;

  /// Label for book obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'BOOK'**
  String get wrappedBook;

  /// Label for celebrity obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'CELEBRITY'**
  String get wrappedCelebrity;

  /// Label for food obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'FOOD'**
  String get wrappedFood;

  /// Badge for movie recommendations in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Movie Recs For Friends'**
  String get wrappedMovieRecs;

  /// Word Biggest in struggle/win templates
  ///
  /// In en, this message translates to:
  /// **'Biggest'**
  String get wrappedBiggest;

  /// Word Struggle in Wrapped template
  ///
  /// In en, this message translates to:
  /// **'Struggle'**
  String get wrappedStruggle;

  /// Encouragement message in struggle template
  ///
  /// In en, this message translates to:
  /// **'But you pushed through 💪'**
  String get wrappedButYouPushedThrough;

  /// Word Win in Wrapped template
  ///
  /// In en, this message translates to:
  /// **'Win'**
  String get wrappedWin;

  /// Celebration message in win template
  ///
  /// In en, this message translates to:
  /// **'You did it! 🎉'**
  String get wrappedYouDidIt;

  /// Badge for top phrases in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Top 5 Phrases'**
  String get wrappedTopPhrases;

  /// Abbreviated minutes label in Wrapped collage
  ///
  /// In en, this message translates to:
  /// **'mins'**
  String get wrappedMins;

  /// Short label for conversations
  ///
  /// In en, this message translates to:
  /// **'convos'**
  String get wrappedConvos;

  /// Abbreviated days label in Wrapped collage
  ///
  /// In en, this message translates to:
  /// **'days'**
  String get wrappedDays;

  /// Uppercase label for buddies tile in collage
  ///
  /// In en, this message translates to:
  /// **'MY BUDDIES'**
  String get wrappedMyBuddiesLabel;

  /// Uppercase label for obsessions tile in collage
  ///
  /// In en, this message translates to:
  /// **'OBSESSIONS'**
  String get wrappedObsessionsLabel;

  /// Uppercase label for struggle tile in collage
  ///
  /// In en, this message translates to:
  /// **'STRUGGLE'**
  String get wrappedStruggleLabel;

  /// Uppercase label for win tile in collage
  ///
  /// In en, this message translates to:
  /// **'WIN'**
  String get wrappedWinLabel;

  /// Uppercase label for top phrases tile in collage
  ///
  /// In en, this message translates to:
  /// **'TOP PHRASES'**
  String get wrappedTopPhrasesLabel;

  /// Intro text on wrapped generate screen before the year 2025
  ///
  /// In en, this message translates to:
  /// **'Let\'s hit rewind on your'**
  String get wrappedLetsHitRewind;

  /// Button text to start generating the 2025 wrapped
  ///
  /// In en, this message translates to:
  /// **'Generate My Wrapped'**
  String get wrappedGenerateMyWrapped;

  /// Default processing status text
  ///
  /// In en, this message translates to:
  /// **'Processing...'**
  String get wrappedProcessingDefault;

  /// Text shown while generating the wrapped, includes newline
  ///
  /// In en, this message translates to:
  /// **'Creating your\n2025 story...'**
  String get wrappedCreatingYourStory;

  /// Error header text, includes newline
  ///
  /// In en, this message translates to:
  /// **'Something\nwent wrong'**
  String get wrappedSomethingWentWrong;

  /// Generic error message fallback
  ///
  /// In en, this message translates to:
  /// **'An error occurred'**
  String get wrappedAnErrorOccurred;

  /// Button text to retry generating wrapped
  ///
  /// In en, this message translates to:
  /// **'Try Again'**
  String get wrappedTryAgain;

  /// Shown when wrapped result is null
  ///
  /// In en, this message translates to:
  /// **'No data available'**
  String get wrappedNoDataAvailable;

  /// Subtitle on the intro card
  ///
  /// In en, this message translates to:
  /// **'Omi Life Recap'**
  String get wrappedOmiLifeRecap;

  /// Instruction text on intro card
  ///
  /// In en, this message translates to:
  /// **'Swipe up to begin'**
  String get wrappedSwipeUpToBegin;

  /// Text shared when sharing wrapped images
  ///
  /// In en, this message translates to:
  /// **'My 2025, remembered by Omi ✨ omi.me/wrapped'**
  String get wrappedShareText;

  /// Error message when sharing fails
  ///
  /// In en, this message translates to:
  /// **'Failed to share. Please try again.'**
  String get wrappedFailedToShare;

  /// Error message when generation fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start generation. Please try again.'**
  String get wrappedFailedToStartGeneration;

  /// Initial processing step text
  ///
  /// In en, this message translates to:
  /// **'Starting...'**
  String get wrappedStarting;

  /// Share button label
  ///
  /// In en, this message translates to:
  /// **'Share'**
  String get wrappedShare;

  /// Button text for sharing wrapped on final card
  ///
  /// In en, this message translates to:
  /// **'Share Your Wrapped'**
  String get wrappedShareYourWrapped;

  /// Title text for shareable image
  ///
  /// In en, this message translates to:
  /// **'My 2025'**
  String get wrappedMy2025;

  /// Subtitle text for shareable image
  ///
  /// In en, this message translates to:
  /// **'remembered by Omi'**
  String get wrappedRememberedByOmi;

  /// Label for the most fun day in memorable days
  ///
  /// In en, this message translates to:
  /// **'Most Fun'**
  String get wrappedMostFunDay;

  /// Label for the most productive day
  ///
  /// In en, this message translates to:
  /// **'Most Productive'**
  String get wrappedMostProductiveDay;

  /// Label for the most intense/stressful day
  ///
  /// In en, this message translates to:
  /// **'Most Intense'**
  String get wrappedMostIntenseDay;

  /// Label for funniest moment
  ///
  /// In en, this message translates to:
  /// **'Funniest'**
  String get wrappedFunniestMoment;

  /// Label for most embarrassing/cringe moment
  ///
  /// In en, this message translates to:
  /// **'Most Cringe'**
  String get wrappedMostCringeMoment;

  /// Label under minutes count
  ///
  /// In en, this message translates to:
  /// **'minutes'**
  String get wrappedMinutesLabel;

  /// Label under conversations count
  ///
  /// In en, this message translates to:
  /// **'conversations'**
  String get wrappedConversationsLabel;

  /// Label under days active count
  ///
  /// In en, this message translates to:
  /// **'days active'**
  String get wrappedDaysActiveLabel;

  /// Label under total tasks count
  ///
  /// In en, this message translates to:
  /// **'tasks generated'**
  String get wrappedTasksGenerated;

  /// Label under completed tasks count
  ///
  /// In en, this message translates to:
  /// **'tasks completed'**
  String get wrappedTasksCompleted;

  /// Badge text for top phrases card
  ///
  /// In en, this message translates to:
  /// **'Top 5 Phrases'**
  String get wrappedTopFivePhrases;

  /// Default title for most fun day
  ///
  /// In en, this message translates to:
  /// **'A Great Day'**
  String get wrappedAGreatDay;

  /// Default title for most productive day
  ///
  /// In en, this message translates to:
  /// **'Getting It Done'**
  String get wrappedGettingItDone;

  /// Default title for most intense day
  ///
  /// In en, this message translates to:
  /// **'A Challenge'**
  String get wrappedAChallenge;

  /// Default title for funniest moment
  ///
  /// In en, this message translates to:
  /// **'A Hilarious Moment'**
  String get wrappedAHilariousMoment;

  /// Default title for most cringe moment
  ///
  /// In en, this message translates to:
  /// **'That Awkward Moment'**
  String get wrappedThatAwkwardMoment;

  /// Default description for funniest moment
  ///
  /// In en, this message translates to:
  /// **'You had some funny moments this year!'**
  String get wrappedYouHadFunnyMoments;

  /// Default description for cringe moment
  ///
  /// In en, this message translates to:
  /// **'We\'ve all been there!'**
  String get wrappedWeveAllBeenThere;

  /// Default name/relationship for buddy
  ///
  /// In en, this message translates to:
  /// **'Friend'**
  String get wrappedFriend;

  /// Default context for buddy
  ///
  /// In en, this message translates to:
  /// **'Your buddy!'**
  String get wrappedYourBuddy;

  /// Default value when obsession not found
  ///
  /// In en, this message translates to:
  /// **'Not mentioned'**
  String get wrappedNotMentioned;

  /// Default title for struggle
  ///
  /// In en, this message translates to:
  /// **'The Hard Part'**
  String get wrappedTheHardPart;

  /// Default title for personal win
  ///
  /// In en, this message translates to:
  /// **'Personal Growth'**
  String get wrappedPersonalGrowth;

  /// Short label for fun day in summary
  ///
  /// In en, this message translates to:
  /// **'Fun'**
  String get wrappedFunDay;

  /// Short label for productive day in summary
  ///
  /// In en, this message translates to:
  /// **'Productive'**
  String get wrappedProductiveDay;

  /// Short label for intense day in summary
  ///
  /// In en, this message translates to:
  /// **'Intense'**
  String get wrappedIntenseDay;

  /// Default title for funny moment in collage
  ///
  /// In en, this message translates to:
  /// **'Funny Moment'**
  String get wrappedFunnyMomentTitle;

  /// Default title for cringe moment in collage
  ///
  /// In en, this message translates to:
  /// **'Cringe Moment'**
  String get wrappedCringeMomentTitle;

  /// Badge text for category chart card
  ///
  /// In en, this message translates to:
  /// **'You Talked About'**
  String get wrappedYouTalkedAboutBadge;

  /// Completed label in actions card
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get wrappedCompletedLabel;

  /// Badge text for my buddies card
  ///
  /// In en, this message translates to:
  /// **'My Buddies'**
  String get wrappedMyBuddiesCard;

  /// Section title in summary collage
  ///
  /// In en, this message translates to:
  /// **'BUDDIES'**
  String get wrappedBuddiesLabel;

  /// Section title in summary collage (uppercase)
  ///
  /// In en, this message translates to:
  /// **'OBSESSIONS'**
  String get wrappedObsessionsLabelUpper;

  /// Section title in summary collage (uppercase)
  ///
  /// In en, this message translates to:
  /// **'STRUGGLE'**
  String get wrappedStruggleLabelUpper;

  /// Section title in summary collage (uppercase)
  ///
  /// In en, this message translates to:
  /// **'WIN'**
  String get wrappedWinLabelUpper;

  /// Section title in summary collage (uppercase)
  ///
  /// In en, this message translates to:
  /// **'TOP PHRASES'**
  String get wrappedTopPhrasesLabelUpper;

  /// First line of header for top days card
  ///
  /// In en, this message translates to:
  /// **'Your'**
  String get wrappedYourHeader;

  /// Second line of header for top days card
  ///
  /// In en, this message translates to:
  /// **'Top Days'**
  String get wrappedTopDaysHeader;

  /// Badge text for top days summary
  ///
  /// In en, this message translates to:
  /// **'Your Top Days'**
  String get wrappedYourTopDaysBadge;

  /// First line of header for best moments card
  ///
  /// In en, this message translates to:
  /// **'Best'**
  String get wrappedBestHeader;

  /// Second line of header for best moments card
  ///
  /// In en, this message translates to:
  /// **'Moments'**
  String get wrappedMomentsHeader;

  /// Badge text for best moments summary
  ///
  /// In en, this message translates to:
  /// **'Best Moments'**
  String get wrappedBestMomentsBadge;

  /// Header line for struggle/win cards
  ///
  /// In en, this message translates to:
  /// **'Biggest'**
  String get wrappedBiggestHeader;

  /// Second line of struggle card header
  ///
  /// In en, this message translates to:
  /// **'Struggle'**
  String get wrappedStruggleHeader;

  /// Second line of win card header
  ///
  /// In en, this message translates to:
  /// **'Win'**
  String get wrappedWinHeader;

  /// Subtitle on struggle card with emoji
  ///
  /// In en, this message translates to:
  /// **'But you pushed through 💪'**
  String get wrappedButYouPushedThroughEmoji;

  /// Subtitle on win card with emoji
  ///
  /// In en, this message translates to:
  /// **'You did it! 🎉'**
  String get wrappedYouDidItEmoji;

  /// Label for hours stat
  ///
  /// In en, this message translates to:
  /// **'hours'**
  String get wrappedHours;

  /// Label for actions stat
  ///
  /// In en, this message translates to:
  /// **'actions'**
  String get wrappedActions;

  /// Dialog title when multiple speakers are detected in speech profile recording
  ///
  /// In en, this message translates to:
  /// **'Multiple speakers detected'**
  String get multipleSpeakersDetected;

  /// Dialog message explaining multiple speakers issue
  ///
  /// In en, this message translates to:
  /// **'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.'**
  String get multipleSpeakersDescription;

  /// Dialog title for invalid recording
  ///
  /// In en, this message translates to:
  /// **'Invalid recording detected'**
  String get invalidRecordingDetected;

  /// Dialog message when speech recording is too short
  ///
  /// In en, this message translates to:
  /// **'There is not enough speech detected. Please speak more and try again.'**
  String get notEnoughSpeechDescription;

  /// Dialog message about speech duration requirements
  ///
  /// In en, this message translates to:
  /// **'Please make sure you speak for at least 5 seconds and not more than 90.'**
  String get speechDurationDescription;

  /// Dialog message when connection is lost
  ///
  /// In en, this message translates to:
  /// **'The connection was interrupted. Please check your internet connection and try again.'**
  String get connectionLostDescription;

  /// Dialog title for speech sample instructions
  ///
  /// In en, this message translates to:
  /// **'How to take a good sample?'**
  String get howToTakeGoodSample;

  /// Instructions for taking a good speech sample
  ///
  /// In en, this message translates to:
  /// **'1. Make sure you are in a quiet place.\n2. Speak clearly and naturally.\n3. Make sure your device is in its natural position, on your neck.\n\nOnce it\'s created, you can always improve it or do it again.'**
  String get goodSampleInstructions;

  /// Message when no device is connected and phone mic will be used
  ///
  /// In en, this message translates to:
  /// **'No device connected. Will use phone microphone.'**
  String get noDeviceConnectedUseMic;

  /// Button text to redo speech profile
  ///
  /// In en, this message translates to:
  /// **'Do it again'**
  String get doItAgain;

  /// Button text to listen to speech profile
  ///
  /// In en, this message translates to:
  /// **'Listen to my speech profile ➡️'**
  String get listenToSpeechProfile;

  /// Button text to recognize other people
  ///
  /// In en, this message translates to:
  /// **'Recognizing others 👀'**
  String get recognizingOthers;

  /// Encouragement message during speech recording
  ///
  /// In en, this message translates to:
  /// **'Keep going, you are doing great'**
  String get keepGoingGreat;

  /// Generic error message shown in snackbar when an error occurs
  ///
  /// In en, this message translates to:
  /// **'Something went wrong! Please try again later.'**
  String get somethingWentWrongTryAgain;

  /// Loading message shown while uploading voice profile
  ///
  /// In en, this message translates to:
  /// **'Uploading your voice profile....'**
  String get uploadingVoiceProfile;

  /// Loading message shown while processing voice profile
  ///
  /// In en, this message translates to:
  /// **'Memorizing your voice...'**
  String get memorizingYourVoice;

  /// Loading message shown while personalizing user experience
  ///
  /// In en, this message translates to:
  /// **'Personalizing your experience...'**
  String get personalizingExperience;

  /// Instruction to user during speech profile recording
  ///
  /// In en, this message translates to:
  /// **'Keep speaking until you get 100%.'**
  String get keepSpeakingUntil100;

  /// Encouragement message during speech profile recording
  ///
  /// In en, this message translates to:
  /// **'Great job, you are almost there'**
  String get greatJobAlmostThere;

  /// Encouragement message when speech profile is nearly complete
  ///
  /// In en, this message translates to:
  /// **'So close, just a little more'**
  String get soCloseJustLittleMore;

  /// Section header for notification frequency settings
  ///
  /// In en, this message translates to:
  /// **'Notification Frequency'**
  String get notificationFrequency;

  /// Description for notification frequency control
  ///
  /// In en, this message translates to:
  /// **'Control how often Omi sends you proactive notifications.'**
  String get controlNotificationFrequency;

  /// Label for your score button
  ///
  /// In en, this message translates to:
  /// **'Your score'**
  String get yourScore;

  /// Title for score breakdown modal
  ///
  /// In en, this message translates to:
  /// **'Daily Score Breakdown'**
  String get dailyScoreBreakdown;

  /// Label for today score in breakdown
  ///
  /// In en, this message translates to:
  /// **'Today\'s Score'**
  String get todaysScore;

  /// Label for tasks completed count
  ///
  /// In en, this message translates to:
  /// **'Tasks Completed'**
  String get tasksCompleted;

  /// Label for completion percentage
  ///
  /// In en, this message translates to:
  /// **'Completion Rate'**
  String get completionRate;

  /// Section title explaining how scoring works
  ///
  /// In en, this message translates to:
  /// **'How it works'**
  String get howItWorks;

  /// Explanation of how daily score is calculated
  ///
  /// In en, this message translates to:
  /// **'Your daily score is based on task completion. Complete your tasks to improve your score!'**
  String get dailyScoreExplanation;

  /// Description text for notification frequency section
  ///
  /// In en, this message translates to:
  /// **'Control how often Omi sends you proactive notifications and reminders.'**
  String get notificationFrequencyDescription;

  /// Label for slider minimum value
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get sliderOff;

  /// Label for slider maximum value
  ///
  /// In en, this message translates to:
  /// **'Max'**
  String get sliderMax;

  /// Success message when summary is generated
  ///
  /// In en, this message translates to:
  /// **'Summary generated for {date}'**
  String summaryGeneratedFor(String date);

  /// Error message when summary generation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to generate summary. Make sure you have conversations for that day.'**
  String get failedToGenerateSummary;

  /// Label for recap/daily summaries tab
  ///
  /// In en, this message translates to:
  /// **'Recap'**
  String get recap;

  /// Dialog title for deleting an item
  ///
  /// In en, this message translates to:
  /// **'Delete \"{name}\"'**
  String deleteQuoted(String name);

  /// Dialog subtitle when deleting folder
  ///
  /// In en, this message translates to:
  /// **'Move {count} conversations to:'**
  String moveConversationsTo(int count);

  /// Label when no folder is assigned
  ///
  /// In en, this message translates to:
  /// **'No Folder'**
  String get noFolder;

  /// Description for no folder option
  ///
  /// In en, this message translates to:
  /// **'Remove from all folders'**
  String get removeFromAllFolders;

  /// Subtitle for create app button
  ///
  /// In en, this message translates to:
  /// **'Build and share your custom app'**
  String get buildAndShareYourCustomApp;

  /// Search bar placeholder text
  ///
  /// In en, this message translates to:
  /// **'Search 1500+ Apps'**
  String get searchAppsPlaceholder;

  /// Filter button label
  ///
  /// In en, this message translates to:
  /// **'Filters'**
  String get filters;

  /// Notification frequency level - off
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get frequencyOff;

  /// Notification frequency level - minimal
  ///
  /// In en, this message translates to:
  /// **'Minimal'**
  String get frequencyMinimal;

  /// Notification frequency level - low
  ///
  /// In en, this message translates to:
  /// **'Low'**
  String get frequencyLow;

  /// Notification frequency level - balanced
  ///
  /// In en, this message translates to:
  /// **'Balanced'**
  String get frequencyBalanced;

  /// Notification frequency level - high
  ///
  /// In en, this message translates to:
  /// **'High'**
  String get frequencyHigh;

  /// Notification frequency level - maximum
  ///
  /// In en, this message translates to:
  /// **'Maximum'**
  String get frequencyMaximum;

  /// Description for off notification frequency
  ///
  /// In en, this message translates to:
  /// **'No proactive notifications'**
  String get frequencyDescOff;

  /// Description for minimal notification frequency
  ///
  /// In en, this message translates to:
  /// **'Only critical reminders'**
  String get frequencyDescMinimal;

  /// Description for low notification frequency
  ///
  /// In en, this message translates to:
  /// **'Important updates only'**
  String get frequencyDescLow;

  /// Description for balanced notification frequency
  ///
  /// In en, this message translates to:
  /// **'Regular helpful nudges'**
  String get frequencyDescBalanced;

  /// Description for high notification frequency
  ///
  /// In en, this message translates to:
  /// **'Frequent check-ins'**
  String get frequencyDescHigh;

  /// Description for maximum notification frequency
  ///
  /// In en, this message translates to:
  /// **'Stay constantly engaged'**
  String get frequencyDescMaximum;

  /// Dialog title asking to clear chat
  ///
  /// In en, this message translates to:
  /// **'Clear Chat?'**
  String get clearChatQuestion;

  /// Loading text when syncing messages
  ///
  /// In en, this message translates to:
  /// **'Syncing messages with server...'**
  String get syncingMessages;

  /// Title for chat apps drawer/section
  ///
  /// In en, this message translates to:
  /// **'Chat Apps'**
  String get chatAppsTitle;

  /// Section header for selecting an app
  ///
  /// In en, this message translates to:
  /// **'Select App'**
  String get selectApp;

  /// Empty state message when no chat apps are enabled
  ///
  /// In en, this message translates to:
  /// **'No chat apps enabled.\nTap \"Enable Apps\" to add some.'**
  String get noChatAppsEnabled;

  /// Button to disable/remove an app
  ///
  /// In en, this message translates to:
  /// **'Disable'**
  String get disable;

  /// Action sheet option to select from photo library
  ///
  /// In en, this message translates to:
  /// **'Photo Library'**
  String get photoLibrary;

  /// Action sheet option to choose a file
  ///
  /// In en, this message translates to:
  /// **'Choose File'**
  String get chooseFile;

  /// Description for persona settings
  ///
  /// In en, this message translates to:
  /// **'Configure your AI persona'**
  String get configureAiPersona;

  /// Description for MCP server feature
  ///
  /// In en, this message translates to:
  /// **'Connect AI assistants to your data'**
  String get connectAiAssistantsToYourData;

  /// OAuth section header
  ///
  /// In en, this message translates to:
  /// **'OAuth'**
  String get oAuth;

  /// Description for goal tracker feature
  ///
  /// In en, this message translates to:
  /// **'Track your personal goals on homepage'**
  String get trackYourGoalsOnHomepage;

  /// Menu item and dialog title for deleting recording
  ///
  /// In en, this message translates to:
  /// **'Delete Recording'**
  String get deleteRecording;

  /// Warning message for irreversible actions
  ///
  /// In en, this message translates to:
  /// **'This cannot be undone.'**
  String get thisCannotBeUndone;

  /// Label for SD card storage
  ///
  /// In en, this message translates to:
  /// **'SD Card'**
  String get sdCard;

  /// Label indicating content originated from SD card
  ///
  /// In en, this message translates to:
  /// **'From SD'**
  String get fromSd;

  /// Label for Limitless device storage
  ///
  /// In en, this message translates to:
  /// **'Limitless'**
  String get limitless;

  /// Name of the fast transfer method
  ///
  /// In en, this message translates to:
  /// **'Fast Transfer'**
  String get fastTransfer;

  /// Status label when syncing is in progress
  ///
  /// In en, this message translates to:
  /// **'Syncing'**
  String get syncingStatus;

  /// Status label when sync has failed
  ///
  /// In en, this message translates to:
  /// **'Failed'**
  String get failedStatus;

  /// Estimated time remaining label
  ///
  /// In en, this message translates to:
  /// **'ETA: {time}'**
  String etaLabel(String time);

  /// Page title for transfer method settings
  ///
  /// In en, this message translates to:
  /// **'Transfer Method'**
  String get transferMethod;

  /// Label for fast WiFi transfer method
  ///
  /// In en, this message translates to:
  /// **'Fast'**
  String get fast;

  /// Label for Bluetooth Low Energy transfer method
  ///
  /// In en, this message translates to:
  /// **'BLE'**
  String get ble;

  /// Filter label for phone storage
  ///
  /// In en, this message translates to:
  /// **'Phone'**
  String get phone;

  /// Dialog title and button to cancel sync
  ///
  /// In en, this message translates to:
  /// **'Cancel Sync'**
  String get cancelSync;

  /// Message explaining what happens when sync is cancelled
  ///
  /// In en, this message translates to:
  /// **'Data already downloaded will be saved. You can resume later.'**
  String get cancelSyncMessage;

  /// Snackbar message when sync is cancelled
  ///
  /// In en, this message translates to:
  /// **'Sync cancelled'**
  String get syncCancelled;

  /// Dialog title for deleting processed files
  ///
  /// In en, this message translates to:
  /// **'Delete Processed Files'**
  String get deleteProcessedFiles;

  /// Snackbar message when processed files are deleted
  ///
  /// In en, this message translates to:
  /// **'Processed files deleted'**
  String get processedFilesDeleted;

  /// Error message when WiFi fails to enable on device
  ///
  /// In en, this message translates to:
  /// **'Failed to enable WiFi on device. Please try again.'**
  String get wifiEnableFailed;

  /// Error message when device does not support fast transfer
  ///
  /// In en, this message translates to:
  /// **'Your device does not support Fast Transfer. Use Bluetooth instead.'**
  String get deviceNoFastTransfer;

  /// Error message asking user to enable hotspot
  ///
  /// In en, this message translates to:
  /// **'Please enable your phone\'s hotspot and try again.'**
  String get enableHotspotMessage;

  /// Error message when transfer fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start transfer. Please try again.'**
  String get transferStartFailed;

  /// Error message when device times out
  ///
  /// In en, this message translates to:
  /// **'Device did not respond. Please try again.'**
  String get deviceNotResponding;

  /// Error message for invalid WiFi credentials
  ///
  /// In en, this message translates to:
  /// **'Invalid WiFi credentials. Check your hotspot settings.'**
  String get invalidWifiCredentials;

  /// Error message when WiFi connection fails
  ///
  /// In en, this message translates to:
  /// **'WiFi connection failed. Please try again.'**
  String get wifiConnectionFailed;

  /// Dialog title for SD card processing
  ///
  /// In en, this message translates to:
  /// **'SD Card Processing'**
  String get sdCardProcessing;

  /// Message explaining SD card processing
  ///
  /// In en, this message translates to:
  /// **'Processing {count} recording(s). Files will be removed from SD card after.'**
  String sdCardProcessingMessage(int count);

  /// Button label to start processing
  ///
  /// In en, this message translates to:
  /// **'Process'**
  String get process;

  /// Error title when WiFi sync fails
  ///
  /// In en, this message translates to:
  /// **'WiFi Sync Failed'**
  String get wifiSyncFailed;

  /// Error title when processing fails
  ///
  /// In en, this message translates to:
  /// **'Processing Failed'**
  String get processingFailed;

  /// Progress label when downloading from SD card
  ///
  /// In en, this message translates to:
  /// **'Downloading from SD Card'**
  String get downloadingFromSdCard;

  /// Progress label showing current/total items
  ///
  /// In en, this message translates to:
  /// **'Processing {current}/{total}'**
  String processingProgress(int current, int total);

  /// Success message showing number of conversations created
  ///
  /// In en, this message translates to:
  /// **'{count} conversations created'**
  String conversationsCreated(int count);

  /// Error message when internet connection is needed
  ///
  /// In en, this message translates to:
  /// **'Internet required'**
  String get internetRequired;

  /// Button label to process audio recordings
  ///
  /// In en, this message translates to:
  /// **'Process Audio'**
  String get processAudio;

  /// Button label to start an action
  ///
  /// In en, this message translates to:
  /// **'Start'**
  String get start;

  /// Empty state title when there are no recordings
  ///
  /// In en, this message translates to:
  /// **'No Recordings'**
  String get noRecordings;

  /// Empty state description for recordings
  ///
  /// In en, this message translates to:
  /// **'Audio from your Omi device will appear here'**
  String get audioFromOmiWillAppearHere;

  /// Menu item to delete processed files
  ///
  /// In en, this message translates to:
  /// **'Delete Processed'**
  String get deleteProcessed;

  /// Hint when no recordings match current filter
  ///
  /// In en, this message translates to:
  /// **'Try a different filter'**
  String get tryDifferentFilter;

  /// Section header for recordings list
  ///
  /// In en, this message translates to:
  /// **'Recordings'**
  String get recordings;

  /// Message shown when Apple Reminders permission is denied
  ///
  /// In en, this message translates to:
  /// **'Please enable Reminders access in Settings to use Apple Reminders'**
  String get enableRemindersAccess;

  /// Date format showing today with time
  ///
  /// In en, this message translates to:
  /// **'Today at {time}'**
  String todayAtTime(String time);

  /// Date format showing yesterday with time
  ///
  /// In en, this message translates to:
  /// **'Yesterday at {time}'**
  String yesterdayAtTime(String time);

  /// Time estimate for very short durations
  ///
  /// In en, this message translates to:
  /// **'Less than a minute'**
  String get lessThanAMinute;

  /// Estimated time in minutes
  ///
  /// In en, this message translates to:
  /// **'~{count} minute(s)'**
  String estimatedMinutes(int count);

  /// Estimated time in hours
  ///
  /// In en, this message translates to:
  /// **'~{count} hour(s)'**
  String estimatedHours(int count);

  /// Shows estimated remaining time for processing
  ///
  /// In en, this message translates to:
  /// **'Estimated: {time} remaining'**
  String estimatedTimeRemaining(String time);

  /// Loading text while summarizing a conversation
  ///
  /// In en, this message translates to:
  /// **'Summarizing conversation...\nThis may take a few seconds'**
  String get summarizingConversation;

  /// Loading text while re-summarizing a conversation
  ///
  /// In en, this message translates to:
  /// **'Re-summarizing conversation...\nThis may take a few seconds'**
  String get resummarizingConversation;

  /// Message when no interesting content found
  ///
  /// In en, this message translates to:
  /// **'Nothing interesting found,\nwant to retry?'**
  String get nothingInterestingRetry;

  /// Message when conversation has no summary
  ///
  /// In en, this message translates to:
  /// **'No summary available\nfor this conversation.'**
  String get noSummaryForConversation;

  /// Fallback for unknown location
  ///
  /// In en, this message translates to:
  /// **'Unknown location'**
  String get unknownLocation;

  /// Error message when map fails to load
  ///
  /// In en, this message translates to:
  /// **'Could not load map'**
  String get couldNotLoadMap;

  /// Developer option to trigger webhook
  ///
  /// In en, this message translates to:
  /// **'Trigger Conversation Created Integration'**
  String get triggerConversationIntegration;

  /// Dialog title when webhook URL is missing
  ///
  /// In en, this message translates to:
  /// **'Webhook URL not set'**
  String get webhookUrlNotSet;

  /// Dialog message prompting to set webhook URL
  ///
  /// In en, this message translates to:
  /// **'Please set the webhook URL in developer settings to use this feature.'**
  String get setWebhookUrlInSettings;

  /// Option to share conversation via web URL
  ///
  /// In en, this message translates to:
  /// **'Send web url'**
  String get sendWebUrl;

  /// Option to share transcript
  ///
  /// In en, this message translates to:
  /// **'Send Transcript'**
  String get sendTranscript;

  /// Option to share summary
  ///
  /// In en, this message translates to:
  /// **'Send Summary'**
  String get sendSummary;

  /// Warning title for debug mode
  ///
  /// In en, this message translates to:
  /// **'Debug Mode Detected'**
  String get debugModeDetected;

  /// Warning about debug mode performance
  ///
  /// In en, this message translates to:
  /// **'Performance reduced 5-10x. Use Release mode.'**
  String get performanceReduced;

  /// Countdown for auto-closing snackbar
  ///
  /// In en, this message translates to:
  /// **'Auto-closing in {seconds}s'**
  String autoClosingInSeconds(int seconds);

  /// Dialog title when model is not downloaded
  ///
  /// In en, this message translates to:
  /// **'Model Required'**
  String get modelRequired;

  /// Message prompting to download Whisper model
  ///
  /// In en, this message translates to:
  /// **'Please download a Whisper model before saving.'**
  String get downloadWhisperModel;

  /// Dialog title for incompatible device
  ///
  /// In en, this message translates to:
  /// **'Device Not Compatible'**
  String get deviceNotCompatible;

  /// Message about device requirements
  ///
  /// In en, this message translates to:
  /// **'Your device does not meet the requirements for On-Device transcription.'**
  String get deviceRequirements;

  /// Warning about enabling on incompatible device
  ///
  /// In en, this message translates to:
  /// **'Enabling this will likely cause the app to crash or freeze.'**
  String get willLikelyCrash;

  /// Warning about transcription quality
  ///
  /// In en, this message translates to:
  /// **'Transcription will be significantly slower and less accurate.'**
  String get transcriptionSlowerLessAccurate;

  /// Button to proceed despite warnings
  ///
  /// In en, this message translates to:
  /// **'Proceed anyway'**
  String get proceedAnyway;

  /// Title for older device warning dialog
  ///
  /// In en, this message translates to:
  /// **'Older Device Detected'**
  String get olderDeviceDetected;

  /// Warning about slower transcription
  ///
  /// In en, this message translates to:
  /// **'On-device transcription may be slower on this device.'**
  String get onDeviceSlower;

  /// Warning about battery usage
  ///
  /// In en, this message translates to:
  /// **'Battery usage will be higher than cloud transcription.'**
  String get batteryUsageHigher;

  /// Suggestion to use cloud transcription
  ///
  /// In en, this message translates to:
  /// **'Consider using Omi Cloud for better performance.'**
  String get considerOmiCloud;

  /// Title for high resource usage dialog
  ///
  /// In en, this message translates to:
  /// **'High Resource Usage'**
  String get highResourceUsage;

  /// Message about computational intensity
  ///
  /// In en, this message translates to:
  /// **'On-Device transcription is computationally intensive.'**
  String get onDeviceIntensive;

  /// Warning about battery drain
  ///
  /// In en, this message translates to:
  /// **'Battery drain will increase significantly.'**
  String get batteryDrainIncrease;

  /// Warning about device temperature
  ///
  /// In en, this message translates to:
  /// **'Device may warm up during extended use.'**
  String get deviceMayWarmUp;

  /// Warning about on-device vs cloud quality
  ///
  /// In en, this message translates to:
  /// **'Speed and accuracy may be lower than Cloud models.'**
  String get speedAccuracyLower;

  /// Tab label for cloud provider option
  ///
  /// In en, this message translates to:
  /// **'Cloud Provider'**
  String get cloudProvider;

  /// Info about premium minutes
  ///
  /// In en, this message translates to:
  /// **'1,200 premium minutes/month. On-Device tab offers unlimited free transcription.'**
  String get premiumMinutesInfo;

  /// Link to view usage
  ///
  /// In en, this message translates to:
  /// **'View usage'**
  String get viewUsage;

  /// Info about local processing
  ///
  /// In en, this message translates to:
  /// **'Audio is processed locally. Works offline, more private, but uses more battery.'**
  String get localProcessingInfo;

  /// Label for model selector
  ///
  /// In en, this message translates to:
  /// **'Model'**
  String get model;

  /// Title for performance warning dialog
  ///
  /// In en, this message translates to:
  /// **'Performance Warning'**
  String get performanceWarning;

  /// Warning about large model sizes
  ///
  /// In en, this message translates to:
  /// **'This model is large and may crash the app or run very slowly on mobile devices.\n\n\"small\" or \"base\" is recommended.'**
  String get largeModelWarning;

  /// Label for iOS native speech recognition
  ///
  /// In en, this message translates to:
  /// **'Using Native iOS Speech Recognition'**
  String get usingNativeIosSpeech;

  /// Info about iOS native speech
  ///
  /// In en, this message translates to:
  /// **'Your device\'s native speech engine will be used. No model download required.'**
  String get noModelDownloadRequired;

  /// Status when model is downloaded
  ///
  /// In en, this message translates to:
  /// **'Model Ready'**
  String get modelReady;

  /// Button to re-download model
  ///
  /// In en, this message translates to:
  /// **'Re-download'**
  String get redownload;

  /// Warning during download
  ///
  /// In en, this message translates to:
  /// **'Please do not close the app.'**
  String get doNotCloseApp;

  /// Status during download
  ///
  /// In en, this message translates to:
  /// **'Downloading...'**
  String get downloading;

  /// Dialog title for model download
  ///
  /// In en, this message translates to:
  /// **'Download Model'**
  String get downloadModel;

  /// Shows estimated file size
  ///
  /// In en, this message translates to:
  /// **'Estimated Size: ~{size} MB'**
  String estimatedSize(String size);

  /// Shows available disk space
  ///
  /// In en, this message translates to:
  /// **'Available Space: {space}'**
  String availableSpace(String space);

  /// Warning when not enough disk space
  ///
  /// In en, this message translates to:
  /// **'Warning: Not enough space!'**
  String get notEnoughSpace;

  /// Download button
  ///
  /// In en, this message translates to:
  /// **'Download'**
  String get download;

  /// Error message during download
  ///
  /// In en, this message translates to:
  /// **'Download error: {error}'**
  String downloadError(String error);

  /// Status when download is cancelled
  ///
  /// In en, this message translates to:
  /// **'Cancelled'**
  String get cancelled;

  /// Title for device compatibility error dialog
  ///
  /// In en, this message translates to:
  /// **'Device Not Compatible'**
  String get deviceNotCompatibleTitle;

  /// Message when device does not meet requirements
  ///
  /// In en, this message translates to:
  /// **'Your device does not meet the requirements for On-Device transcription.'**
  String get deviceNotMeetRequirements;

  /// Warning about transcription speed on older devices
  ///
  /// In en, this message translates to:
  /// **'On-device transcription may be slower on this device.'**
  String get transcriptionSlowerOnDevice;

  /// Description of on-device transcription resource usage
  ///
  /// In en, this message translates to:
  /// **'On-Device transcription is computationally intensive.'**
  String get computationallyIntensive;

  /// Warning about battery drain
  ///
  /// In en, this message translates to:
  /// **'Battery drain will increase significantly.'**
  String get batteryDrainSignificantly;

  /// Description of premium minutes quota
  ///
  /// In en, this message translates to:
  /// **'1,200 premium minutes/month. On-Device tab offers unlimited free transcription. '**
  String get premiumMinutesMonth;

  /// Description of on-device processing
  ///
  /// In en, this message translates to:
  /// **'Audio is processed locally. Works offline, more private, but uses more battery.'**
  String get audioProcessedLocally;

  /// Label for language selector
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get languageLabel;

  /// Label for model selector
  ///
  /// In en, this message translates to:
  /// **'Model'**
  String get modelLabel;

  /// Warning about large model sizes
  ///
  /// In en, this message translates to:
  /// **'This model is large and may crash the app or run very slowly on mobile devices.\n\n\"small\" or \"base\" is recommended.'**
  String get modelTooLargeWarning;

  /// Description of iOS native speech recognition
  ///
  /// In en, this message translates to:
  /// **'Your devices native speech engine will be used. No model download required.'**
  String get nativeEngineNoDownload;

  /// Status when model is ready
  ///
  /// In en, this message translates to:
  /// **'Model Ready ({model})'**
  String modelReadyWithName(String model);

  /// Button to re-download model
  ///
  /// In en, this message translates to:
  /// **'Re-download'**
  String get reDownload;

  /// Download progress status
  ///
  /// In en, this message translates to:
  /// **'Downloading {model}: {received} / {total} MB'**
  String downloadingModelProgress(String model, String received, String total);

  /// Status when preparing model
  ///
  /// In en, this message translates to:
  /// **'Preparing {model}...'**
  String preparingModel(String model);

  /// Download error message
  ///
  /// In en, this message translates to:
  /// **'Download error: {error}'**
  String downloadErrorWithMessage(String error);

  /// Estimated model size
  ///
  /// In en, this message translates to:
  /// **'Estimated Size: ~{size} MB'**
  String estimatedSizeWithValue(String size);

  /// Available disk space
  ///
  /// In en, this message translates to:
  /// **'Available Space: {space}'**
  String availableSpaceWithValue(String space);

  /// Description of Omi transcription features
  ///
  /// In en, this message translates to:
  /// **'Omis built-in live transcription is optimized for real-time conversations with automatic speaker detection and diarization.'**
  String get omiTranscriptionOptimized;

  /// Reset button label
  ///
  /// In en, this message translates to:
  /// **'Reset'**
  String get reset;

  /// Label for template selector
  ///
  /// In en, this message translates to:
  /// **'Use template from'**
  String get useTemplateFrom;

  /// Placeholder for template dropdown
  ///
  /// In en, this message translates to:
  /// **'Select a provider template...'**
  String get selectProviderTemplate;

  /// Description for response template selector
  ///
  /// In en, this message translates to:
  /// **'Quickly populate with a known providers response format'**
  String get quicklyPopulateResponse;

  /// Description for request template selector
  ///
  /// In en, this message translates to:
  /// **'Quickly populate with a known providers request format'**
  String get quicklyPopulateRequest;

  /// Error message for invalid JSON
  ///
  /// In en, this message translates to:
  /// **'Invalid JSON'**
  String get invalidJsonError;

  /// Button to download model
  ///
  /// In en, this message translates to:
  /// **'Download Model ({model})'**
  String downloadModelWithName(String model);

  /// Model filename label
  ///
  /// In en, this message translates to:
  /// **'Model: {model}'**
  String modelNameWithFile(String model);

  /// Fallback text for device name
  ///
  /// In en, this message translates to:
  /// **'Device'**
  String get device;

  /// Title for chat assistants capability page
  ///
  /// In en, this message translates to:
  /// **'Chat Assistants'**
  String get chatAssistantsTitle;

  /// Permission title for reading conversations
  ///
  /// In en, this message translates to:
  /// **'Read Conversations'**
  String get permissionReadConversations;

  /// Permission title for reading memories
  ///
  /// In en, this message translates to:
  /// **'Read Memories'**
  String get permissionReadMemories;

  /// Permission title for reading tasks
  ///
  /// In en, this message translates to:
  /// **'Read Tasks'**
  String get permissionReadTasks;

  /// Permission title for creating conversations
  ///
  /// In en, this message translates to:
  /// **'Create Conversations'**
  String get permissionCreateConversations;

  /// Permission title for creating memories
  ///
  /// In en, this message translates to:
  /// **'Create Memories'**
  String get permissionCreateMemories;

  /// Permission type label for access permissions
  ///
  /// In en, this message translates to:
  /// **'Access'**
  String get permissionTypeAccess;

  /// Permission type label for create permissions
  ///
  /// In en, this message translates to:
  /// **'Create'**
  String get permissionTypeCreate;

  /// Permission type label for trigger permissions
  ///
  /// In en, this message translates to:
  /// **'Trigger'**
  String get permissionTypeTrigger;

  /// Description for read conversations permission
  ///
  /// In en, this message translates to:
  /// **'This app can access your conversations.'**
  String get permissionDescReadConversations;

  /// Description for read memories permission
  ///
  /// In en, this message translates to:
  /// **'This app can access your memories.'**
  String get permissionDescReadMemories;

  /// Description for read tasks permission
  ///
  /// In en, this message translates to:
  /// **'This app can access your tasks.'**
  String get permissionDescReadTasks;

  /// Description for create conversations permission
  ///
  /// In en, this message translates to:
  /// **'This app can create new conversations.'**
  String get permissionDescCreateConversations;

  /// Description for create memories permission
  ///
  /// In en, this message translates to:
  /// **'This app can create new memories.'**
  String get permissionDescCreateMemories;

  /// Label for realtime listening trigger
  ///
  /// In en, this message translates to:
  /// **'Realtime Listening'**
  String get realtimeListening;

  /// Status text when setup is completed
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get setupCompleted;

  /// Validation message to select a rating
  ///
  /// In en, this message translates to:
  /// **'Please select a rating'**
  String get pleaseSelectRating;

  /// Hint text for review input field
  ///
  /// In en, this message translates to:
  /// **'Write a review (optional)'**
  String get writeReviewOptional;

  /// Intro text for setup questions page
  ///
  /// In en, this message translates to:
  /// **'Help us improve Omi by answering a few questions.  🫶 💜'**
  String get setupQuestionsIntro;

  /// Question about profession
  ///
  /// In en, this message translates to:
  /// **'1. What do you do?'**
  String get setupQuestionProfession;

  /// Question about Omi usage location
  ///
  /// In en, this message translates to:
  /// **'2. Where do you plan to use your Omi?'**
  String get setupQuestionUsage;

  /// Question about age range
  ///
  /// In en, this message translates to:
  /// **'3. What\'s your age range?'**
  String get setupQuestionAge;

  /// Error message when not all questions are answered
  ///
  /// In en, this message translates to:
  /// **'You haven\'t answered all the questions yet! 🥺'**
  String get setupAnswerAllQuestions;

  /// Skip button text for setup questions
  ///
  /// In en, this message translates to:
  /// **'Skip, I don\'t want to help :C'**
  String get setupSkipHelp;

  /// Profession option: Entrepreneur
  ///
  /// In en, this message translates to:
  /// **'Entrepreneur'**
  String get professionEntrepreneur;

  /// Profession option: Software Engineer
  ///
  /// In en, this message translates to:
  /// **'Software Engineer'**
  String get professionSoftwareEngineer;

  /// Profession option: Product Manager
  ///
  /// In en, this message translates to:
  /// **'Product Manager'**
  String get professionProductManager;

  /// Profession option: Executive
  ///
  /// In en, this message translates to:
  /// **'Executive'**
  String get professionExecutive;

  /// Profession option: Sales
  ///
  /// In en, this message translates to:
  /// **'Sales'**
  String get professionSales;

  /// Profession option: Student
  ///
  /// In en, this message translates to:
  /// **'Student'**
  String get professionStudent;

  /// Usage location option: At work
  ///
  /// In en, this message translates to:
  /// **'At work'**
  String get usageAtWork;

  /// Usage location option: IRL Events
  ///
  /// In en, this message translates to:
  /// **'IRL Events'**
  String get usageIrlEvents;

  /// Usage location option: Online
  ///
  /// In en, this message translates to:
  /// **'Online'**
  String get usageOnline;

  /// Usage location option: In Social Settings
  ///
  /// In en, this message translates to:
  /// **'In Social Settings'**
  String get usageSocialSettings;

  /// Usage location option: Everywhere
  ///
  /// In en, this message translates to:
  /// **'Everywhere'**
  String get usageEverywhere;

  /// Title for custom backend URL page
  ///
  /// In en, this message translates to:
  /// **'Custom Backend URL'**
  String get customBackendUrlTitle;

  /// Label for backend URL input field
  ///
  /// In en, this message translates to:
  /// **'Backend URL'**
  String get backendUrlLabel;

  /// Button text to save the backend URL
  ///
  /// In en, this message translates to:
  /// **'Save URL'**
  String get saveUrlButton;

  /// Error when backend URL is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter the backend URL'**
  String get enterBackendUrlError;

  /// Error when URL does not end with slash
  ///
  /// In en, this message translates to:
  /// **'URL must end with \"/\"'**
  String get urlMustEndWithSlashError;

  /// Error when URL format is invalid
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid URL'**
  String get invalidUrlError;

  /// Success message when backend URL is saved
  ///
  /// In en, this message translates to:
  /// **'Backend URL saved successfully!'**
  String get backendUrlSavedSuccess;

  /// Title for sign in page
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get signInTitle;

  /// Sign in button text
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get signInButton;

  /// Error when email field is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter your email'**
  String get enterEmailError;

  /// Error when email format is invalid
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid email'**
  String get invalidEmailError;

  /// Error when password field is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter your password'**
  String get enterPasswordError;

  /// Error when password is too short
  ///
  /// In en, this message translates to:
  /// **'Password must be at least 8 characters long'**
  String get passwordMinLengthError;

  /// Success message after signing in
  ///
  /// In en, this message translates to:
  /// **'Sign In Successful!'**
  String get signInSuccess;

  /// Link text to go to login page
  ///
  /// In en, this message translates to:
  /// **'Already have an account? Log In'**
  String get alreadyHaveAccountLogin;

  /// Label for email input field
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get emailLabel;

  /// Label for password input field
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get passwordLabel;

  /// Title for create account page
  ///
  /// In en, this message translates to:
  /// **'Create Account'**
  String get createAccountTitle;

  /// Label for name input field
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get nameLabel;

  /// Label for repeat password input field
  ///
  /// In en, this message translates to:
  /// **'Repeat Password'**
  String get repeatPasswordLabel;

  /// Sign up button text
  ///
  /// In en, this message translates to:
  /// **'Sign Up'**
  String get signUpButton;

  /// Error when name field is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter your name'**
  String get enterNameError;

  /// Error when passwords do not match
  ///
  /// In en, this message translates to:
  /// **'Passwords do not match'**
  String get passwordsDoNotMatch;

  /// Success message after signing up
  ///
  /// In en, this message translates to:
  /// **'Signup Successful!'**
  String get signUpSuccess;

  /// Loading text for knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Loading Knowledge Graph...'**
  String get loadingKnowledgeGraph;

  /// Title when knowledge graph is empty
  ///
  /// In en, this message translates to:
  /// **'No knowledge graph yet'**
  String get noKnowledgeGraphYet;

  /// Message while building knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Building your knowledge graph from memories...'**
  String get buildingKnowledgeGraphFromMemories;

  /// Info message about automatic graph building
  ///
  /// In en, this message translates to:
  /// **'Your knowledge graph will be built automatically as you create new memories.'**
  String get knowledgeGraphWillBuildAutomatically;

  /// Button to build knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Build Graph'**
  String get buildGraphButton;

  /// Share text for memory graph
  ///
  /// In en, this message translates to:
  /// **'Check out my memory graph!'**
  String get checkOutMyMemoryGraph;

  /// Button text to get/install an app
  ///
  /// In en, this message translates to:
  /// **'Get'**
  String get getButton;

  /// Snackbar message when opening an app
  ///
  /// In en, this message translates to:
  /// **'Opening {appName}...'**
  String openingApp(String appName);

  /// Hint text for reply text field
  ///
  /// In en, this message translates to:
  /// **'Write something'**
  String get writeSomething;

  /// Button text to submit a reply
  ///
  /// In en, this message translates to:
  /// **'Submit Reply'**
  String get submitReply;

  /// Button text to edit an existing reply
  ///
  /// In en, this message translates to:
  /// **'Edit Your Reply'**
  String get editYourReply;

  /// Button text to reply to a review
  ///
  /// In en, this message translates to:
  /// **'Reply To Review'**
  String get replyToReview;

  /// Title prompting user to rate and review an app
  ///
  /// In en, this message translates to:
  /// **'Rate and Review this App'**
  String get rateAndReviewThisApp;

  /// Message when user tries to submit an unchanged review
  ///
  /// In en, this message translates to:
  /// **'No changes in review to update.'**
  String get noChangesInReview;

  /// Error message when trying to rate without internet
  ///
  /// In en, this message translates to:
  /// **'Can\'t rate app without internet connection.'**
  String get cantRateWithoutInternet;

  /// Title for app analytics section
  ///
  /// In en, this message translates to:
  /// **'App Analytics'**
  String get appAnalytics;

  /// Link text to learn more (lowercase)
  ///
  /// In en, this message translates to:
  /// **'learn more'**
  String get learnMoreLink;

  /// Label for money earned from app
  ///
  /// In en, this message translates to:
  /// **'Money Earned'**
  String get moneyEarned;

  /// Hint text for reply input field
  ///
  /// In en, this message translates to:
  /// **'Write your reply...'**
  String get writeYourReply;

  /// Success message after sending a reply
  ///
  /// In en, this message translates to:
  /// **'Reply sent successfully'**
  String get replySentSuccessfully;

  /// Error message when reply fails
  ///
  /// In en, this message translates to:
  /// **'Failed to send reply: {error}'**
  String failedToSendReply(String error);

  /// Button text to send a message or reply
  ///
  /// In en, this message translates to:
  /// **'Send'**
  String get send;

  /// Filter chip for star rating
  ///
  /// In en, this message translates to:
  /// **'{count} Star'**
  String starFilter(int count);

  /// Empty state message when no reviews match filter
  ///
  /// In en, this message translates to:
  /// **'No Reviews Found'**
  String get noReviewsFound;

  /// Button text to edit an existing reply
  ///
  /// In en, this message translates to:
  /// **'Edit Reply'**
  String get editReply;

  /// Button text to reply to something
  ///
  /// In en, this message translates to:
  /// **'Reply'**
  String get reply;

  /// Filter chip label for star rating
  ///
  /// In en, this message translates to:
  /// **'{count} Star'**
  String starFilterLabel(int count);

  /// No description provided for @sharePublicLink.
  ///
  /// In en, this message translates to:
  /// **'Share Public Link'**
  String get sharePublicLink;

  /// No description provided for @makePersonaPublic.
  ///
  /// In en, this message translates to:
  /// **'Make Persona Public'**
  String get makePersonaPublic;

  /// No description provided for @connectedKnowledgeData.
  ///
  /// In en, this message translates to:
  /// **'Connected Knowledge Data'**
  String get connectedKnowledgeData;

  /// No description provided for @enterName.
  ///
  /// In en, this message translates to:
  /// **'Enter name'**
  String get enterName;

  /// No description provided for @disconnectTwitter.
  ///
  /// In en, this message translates to:
  /// **'Disconnect Twitter'**
  String get disconnectTwitter;

  /// No description provided for @disconnectTwitterConfirmation.
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to disconnect your Twitter account? Your persona will no longer have access to your Twitter data.'**
  String get disconnectTwitterConfirmation;

  /// No description provided for @getOmiDeviceDescription.
  ///
  /// In en, this message translates to:
  /// **'Create a more accurate clone with your personal conversations'**
  String get getOmiDeviceDescription;

  /// No description provided for @getOmi.
  ///
  /// In en, this message translates to:
  /// **'Get Omi'**
  String get getOmi;

  /// No description provided for @iHaveOmiDevice.
  ///
  /// In en, this message translates to:
  /// **'I have Omi device'**
  String get iHaveOmiDevice;

  /// No description provided for @goal.
  ///
  /// In en, this message translates to:
  /// **'GOAL'**
  String get goal;

  /// No description provided for @tapToTrackThisGoal.
  ///
  /// In en, this message translates to:
  /// **'Tap to track this goal'**
  String get tapToTrackThisGoal;

  /// No description provided for @tapToSetAGoal.
  ///
  /// In en, this message translates to:
  /// **'Tap to set a goal'**
  String get tapToSetAGoal;

  /// No description provided for @processedConversations.
  ///
  /// In en, this message translates to:
  /// **'Processed Conversations'**
  String get processedConversations;

  /// No description provided for @updatedConversations.
  ///
  /// In en, this message translates to:
  /// **'Updated Conversations'**
  String get updatedConversations;

  /// No description provided for @newConversations.
  ///
  /// In en, this message translates to:
  /// **'New Conversations'**
  String get newConversations;

  /// No description provided for @summaryTemplate.
  ///
  /// In en, this message translates to:
  /// **'Summary Template'**
  String get summaryTemplate;

  /// No description provided for @suggestedTemplates.
  ///
  /// In en, this message translates to:
  /// **'Suggested Templates'**
  String get suggestedTemplates;

  /// No description provided for @otherTemplates.
  ///
  /// In en, this message translates to:
  /// **'Other Templates'**
  String get otherTemplates;

  /// No description provided for @availableTemplates.
  ///
  /// In en, this message translates to:
  /// **'Available Templates'**
  String get availableTemplates;

  /// No description provided for @getCreative.
  ///
  /// In en, this message translates to:
  /// **'Get Creative'**
  String get getCreative;

  /// No description provided for @defaultLabel.
  ///
  /// In en, this message translates to:
  /// **'Default'**
  String get defaultLabel;

  /// No description provided for @lastUsedLabel.
  ///
  /// In en, this message translates to:
  /// **'Last Used'**
  String get lastUsedLabel;

  /// No description provided for @setDefaultApp.
  ///
  /// In en, this message translates to:
  /// **'Set Default App'**
  String get setDefaultApp;

  /// No description provided for @setDefaultAppContent.
  ///
  /// In en, this message translates to:
  /// **'Set {appName} as your default summarization app?\\n\\nThis app will be automatically used for all future conversation summaries.'**
  String setDefaultAppContent(String appName);

  /// No description provided for @setDefaultButton.
  ///
  /// In en, this message translates to:
  /// **'Set Default'**
  String get setDefaultButton;

  /// No description provided for @setAsDefaultSuccess.
  ///
  /// In en, this message translates to:
  /// **'{appName} set as default summarization app'**
  String setAsDefaultSuccess(String appName);

  /// No description provided for @createCustomTemplate.
  ///
  /// In en, this message translates to:
  /// **'Create Custom Template'**
  String get createCustomTemplate;

  /// No description provided for @allTemplates.
  ///
  /// In en, this message translates to:
  /// **'All Templates'**
  String get allTemplates;

  /// No description provided for @failedToInstallApp.
  ///
  /// In en, this message translates to:
  /// **'Failed to install {appName}. Please try again.'**
  String failedToInstallApp(String appName);

  /// No description provided for @errorInstallingApp.
  ///
  /// In en, this message translates to:
  /// **'Error installing {appName}: {error}'**
  String errorInstallingApp(String appName, String error);

  /// No description provided for @tagSpeaker.
  ///
  /// In en, this message translates to:
  /// **'Tag Speaker {speakerId}'**
  String tagSpeaker(int speakerId);

  /// No description provided for @personNameAlreadyExists.
  ///
  /// In en, this message translates to:
  /// **'A person with this name already exists.'**
  String get personNameAlreadyExists;

  /// No description provided for @selectYouFromList.
  ///
  /// In en, this message translates to:
  /// **'To tag yourself, please select \"You\" from the list.'**
  String get selectYouFromList;

  /// No description provided for @enterPersonsName.
  ///
  /// In en, this message translates to:
  /// **'Enter Person\'s Name'**
  String get enterPersonsName;

  /// No description provided for @addPerson.
  ///
  /// In en, this message translates to:
  /// **'Add Person'**
  String get addPerson;

  /// No description provided for @tagOtherSegmentsFromSpeaker.
  ///
  /// In en, this message translates to:
  /// **'Tag other segments from this speaker ({selected}/{total})'**
  String tagOtherSegmentsFromSpeaker(int selected, int total);

  /// No description provided for @tagOtherSegments.
  ///
  /// In en, this message translates to:
  /// **'Tag other segments'**
  String get tagOtherSegments;

  /// No description provided for @managePeople.
  ///
  /// In en, this message translates to:
  /// **'Manage People'**
  String get managePeople;

  /// Title for share to contacts sheet
  ///
  /// In en, this message translates to:
  /// **'Share via SMS'**
  String get shareViaSms;

  /// Subtitle for share to contacts sheet
  ///
  /// In en, this message translates to:
  /// **'Select contacts to share your conversation summary'**
  String get selectContactsToShareSummary;

  /// Hint text for contacts search field
  ///
  /// In en, this message translates to:
  /// **'Search contacts...'**
  String get searchContactsHint;

  /// Shows count of selected contacts
  ///
  /// In en, this message translates to:
  /// **'{count} selected'**
  String contactsSelectedCount(int count);

  /// Button to clear all selected contacts
  ///
  /// In en, this message translates to:
  /// **'Clear all'**
  String get clearAllSelection;

  /// Button text when no contacts are selected
  ///
  /// In en, this message translates to:
  /// **'Select contacts to share'**
  String get selectContactsToShare;

  /// Button text when 1 contact selected
  ///
  /// In en, this message translates to:
  /// **'Share with {count} contact'**
  String shareWithContactCount(int count);

  /// Button text when multiple contacts selected
  ///
  /// In en, this message translates to:
  /// **'Share with {count} contacts'**
  String shareWithContactsCount(int count);

  /// Title when contacts permission is denied
  ///
  /// In en, this message translates to:
  /// **'Contacts permission required'**
  String get contactsPermissionRequired;

  /// Error message when contacts permission is denied
  ///
  /// In en, this message translates to:
  /// **'Contacts permission is required to share via SMS'**
  String get contactsPermissionRequiredForSms;

  /// Message asking user to grant contacts permission
  ///
  /// In en, this message translates to:
  /// **'Please grant contacts permission to share via SMS'**
  String get grantContactsPermissionForSms;

  /// Message when no contacts have phone numbers
  ///
  /// In en, this message translates to:
  /// **'No contacts with phone numbers found'**
  String get noContactsWithPhoneNumbers;

  /// Message when search returns no results
  ///
  /// In en, this message translates to:
  /// **'No contacts match your search'**
  String get noContactsMatchSearch;

  /// Error message when contacts fail to load
  ///
  /// In en, this message translates to:
  /// **'Failed to load contacts'**
  String get failedToLoadContacts;

  /// Error when sharing preparation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to prepare conversation for sharing. Please try again.'**
  String get failedToPrepareConversationForSharing;

  /// Error when SMS app cannot be opened
  ///
  /// In en, this message translates to:
  /// **'Could not open SMS app. Please try again.'**
  String get couldNotOpenSmsApp;

  /// SMS message body with share link
  ///
  /// In en, this message translates to:
  /// **'Here\'s what we just discussed: {link}'**
  String heresWhatWeDiscussed(String link);

  /// WiFi sync feature label
  ///
  /// In en, this message translates to:
  /// **'WiFi Sync'**
  String get wifiSync;

  /// Message when item is copied to clipboard
  ///
  /// In en, this message translates to:
  /// **'{item} copied to clipboard'**
  String itemCopiedToClipboard(String item);

  /// Title shown when WiFi connection to device fails
  ///
  /// In en, this message translates to:
  /// **'Connection Failed'**
  String get wifiConnectionFailedTitle;

  /// Title shown while connecting to device WiFi
  ///
  /// In en, this message translates to:
  /// **'Connecting to {deviceName}'**
  String connectingToDeviceName(String deviceName);

  /// Step text for enabling device WiFi
  ///
  /// In en, this message translates to:
  /// **'Enable {deviceName}\'s WiFi'**
  String enableDeviceWifi(String deviceName);

  /// Step text for connecting to device
  ///
  /// In en, this message translates to:
  /// **'Connect to {deviceName}'**
  String connectToDeviceName(String deviceName);

  /// AppBar title for recording detail page
  ///
  /// In en, this message translates to:
  /// **'Recording Details'**
  String get recordingDetails;

  /// Storage location label for SD card
  ///
  /// In en, this message translates to:
  /// **'SD Card'**
  String get storageLocationSdCard;

  /// Storage location label for Limitless Pendant
  ///
  /// In en, this message translates to:
  /// **'Limitless Pendant'**
  String get storageLocationLimitlessPendant;

  /// Storage location label for phone
  ///
  /// In en, this message translates to:
  /// **'Phone'**
  String get storageLocationPhone;

  /// Storage location label for phone memory
  ///
  /// In en, this message translates to:
  /// **'Phone (Memory)'**
  String get storageLocationPhoneMemory;

  /// Storage notice showing where recording is stored
  ///
  /// In en, this message translates to:
  /// **'Stored on {deviceName}'**
  String storedOnDevice(String deviceName);

  /// Status text shown during file transfer
  ///
  /// In en, this message translates to:
  /// **'Transferring...'**
  String get transferring;

  /// Title when transfer is needed
  ///
  /// In en, this message translates to:
  /// **'Transfer Required'**
  String get transferRequired;

  /// Description shown during SD card transfer
  ///
  /// In en, this message translates to:
  /// **'Downloading audio from your device\'s SD card'**
  String get downloadingAudioFromSdCard;

  /// Description explaining why transfer is needed
  ///
  /// In en, this message translates to:
  /// **'This recording is stored on your device\'s SD card. Transfer it to your phone to play or share.'**
  String get transferRequiredDescription;

  /// Button to cancel ongoing transfer
  ///
  /// In en, this message translates to:
  /// **'Cancel Transfer'**
  String get cancelTransfer;

  /// Button to start transfer to phone
  ///
  /// In en, this message translates to:
  /// **'Transfer to Phone'**
  String get transferToPhone;

  /// Privacy notice for local recordings
  ///
  /// In en, this message translates to:
  /// **'Private & secure on your device'**
  String get privateAndSecureOnDevice;

  /// Menu item to view recording information
  ///
  /// In en, this message translates to:
  /// **'Recording Info'**
  String get recordingInfo;

  /// Menu item text when transfer is ongoing
  ///
  /// In en, this message translates to:
  /// **'Transfer in progress...'**
  String get transferInProgress;

  /// Menu item to share a recording
  ///
  /// In en, this message translates to:
  /// **'Share Recording'**
  String get shareRecording;

  /// Confirmation message for deleting a recording
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to permanently delete this recording? This can\'t be undone.'**
  String get deleteRecordingConfirmation;

  /// Label for recording ID in details
  ///
  /// In en, this message translates to:
  /// **'Recording ID'**
  String get recordingIdLabel;

  /// Label for date and time in details
  ///
  /// In en, this message translates to:
  /// **'Date & Time'**
  String get dateTimeLabel;

  /// Label for duration in details
  ///
  /// In en, this message translates to:
  /// **'Duration'**
  String get durationLabel;

  /// Label for audio format in details
  ///
  /// In en, this message translates to:
  /// **'Audio Format'**
  String get audioFormatLabel;

  /// Label for storage location in details
  ///
  /// In en, this message translates to:
  /// **'Storage Location'**
  String get storageLocationLabel;

  /// Label for estimated file size
  ///
  /// In en, this message translates to:
  /// **'Estimated Size'**
  String get estimatedSizeLabel;

  /// Label for device model in details
  ///
  /// In en, this message translates to:
  /// **'Device Model'**
  String get deviceModelLabel;

  /// Label for device ID in details
  ///
  /// In en, this message translates to:
  /// **'Device ID'**
  String get deviceIdLabel;

  /// Label for status in details
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get statusLabel;

  /// Status value for processed recording
  ///
  /// In en, this message translates to:
  /// **'Processed'**
  String get statusProcessed;

  /// Status value for unprocessed recording
  ///
  /// In en, this message translates to:
  /// **'Unprocessed'**
  String get statusUnprocessed;

  /// Snackbar message when switching to fast transfer mode
  ///
  /// In en, this message translates to:
  /// **'Switched to Fast Transfer'**
  String get switchedToFastTransfer;

  /// Success message when transfer completes
  ///
  /// In en, this message translates to:
  /// **'Transfer complete! You can now play this recording.'**
  String get transferCompleteMessage;

  /// Error message when transfer fails
  ///
  /// In en, this message translates to:
  /// **'Transfer failed: {error}'**
  String transferFailedMessage(String error);

  /// Snackbar message when transfer is cancelled
  ///
  /// In en, this message translates to:
  /// **'Transfer cancelled'**
  String get transferCancelled;

  /// Snackbar message when fast transfer is enabled
  ///
  /// In en, this message translates to:
  /// **'Fast Transfer enabled'**
  String get fastTransferEnabled;

  /// Snackbar message when bluetooth sync is enabled
  ///
  /// In en, this message translates to:
  /// **'Bluetooth sync enabled'**
  String get bluetoothSyncEnabled;

  /// Dialog title for enabling fast transfer
  ///
  /// In en, this message translates to:
  /// **'Enable Fast Transfer'**
  String get enableFastTransfer;

  /// Description of fast transfer feature in dialog
  ///
  /// In en, this message translates to:
  /// **'Fast Transfer uses WiFi for ~5x faster speeds. Your phone will temporarily connect to your Omi device\'s WiFi network during transfer.'**
  String get fastTransferDescription;

  /// Warning that internet is paused during transfer
  ///
  /// In en, this message translates to:
  /// **'Internet access is paused during transfer'**
  String get internetAccessPausedDuringTransfer;

  /// Description text on transfer method page
  ///
  /// In en, this message translates to:
  /// **'Choose how recordings are transferred from your Omi device to your phone.'**
  String get chooseTransferMethodDescription;

  /// Speed description for WiFi transfer
  ///
  /// In en, this message translates to:
  /// **'~150 KB/s via WiFi'**
  String get wifiSpeed;

  /// Badge label for faster transfer method
  ///
  /// In en, this message translates to:
  /// **'5X FASTER'**
  String get fiveTimesFaster;

  /// Description of fast transfer method card
  ///
  /// In en, this message translates to:
  /// **'Creates a direct WiFi connection to your Omi device. Your phone temporarily disconnects from your regular WiFi during transfer.'**
  String get fastTransferMethodDescription;

  /// Name of bluetooth transfer method
  ///
  /// In en, this message translates to:
  /// **'Bluetooth'**
  String get bluetooth;

  /// Speed description for BLE transfer
  ///
  /// In en, this message translates to:
  /// **'~30 KB/s via BLE'**
  String get bleSpeed;

  /// Description of bluetooth transfer method card
  ///
  /// In en, this message translates to:
  /// **'Uses standard Bluetooth Low Energy connection. Slower but doesn\'t affect your WiFi connection.'**
  String get bluetoothMethodDescription;

  /// Label for selected option
  ///
  /// In en, this message translates to:
  /// **'Selected'**
  String get selected;

  /// Label for selectable option
  ///
  /// In en, this message translates to:
  /// **'Select'**
  String get selectOption;

  /// Title for low battery notification
  ///
  /// In en, this message translates to:
  /// **'Low Battery Alert'**
  String get lowBatteryAlertTitle;

  /// Body text for low battery notification
  ///
  /// In en, this message translates to:
  /// **'Your device is running low on battery. Time for a recharge! 🔋'**
  String get lowBatteryAlertBody;

  /// Title for device disconnected notification
  ///
  /// In en, this message translates to:
  /// **'Your Omi Device Disconnected'**
  String get deviceDisconnectedNotificationTitle;

  /// Body text for device disconnected notification
  ///
  /// In en, this message translates to:
  /// **'Please reconnect to continue using your Omi.'**
  String get deviceDisconnectedNotificationBody;

  /// Title for firmware update available dialog
  ///
  /// In en, this message translates to:
  /// **'Firmware Update Available'**
  String get firmwareUpdateAvailable;

  /// Description for firmware update dialog with version parameter
  ///
  /// In en, this message translates to:
  /// **'A new firmware update ({version}) is available for your Omi device. Would you like to update now?'**
  String firmwareUpdateAvailableDescription(String version);

  /// Button text to postpone an action
  ///
  /// In en, this message translates to:
  /// **'Later'**
  String get later;

  /// Success message when an app is deleted
  ///
  /// In en, this message translates to:
  /// **'App deleted successfully'**
  String get appDeletedSuccessfully;

  /// Error message when app deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete app. Please try again later.'**
  String get appDeleteFailed;

  /// Success message when app visibility is changed
  ///
  /// In en, this message translates to:
  /// **'App visibility changed successfully. It may take a few minutes to reflect.'**
  String get appVisibilityChangedSuccessfully;

  /// Error message when app activation fails, possibly due to incomplete integration setup
  ///
  /// In en, this message translates to:
  /// **'Error activating the app. If this is an integration app, make sure the setup is completed.'**
  String get errorActivatingAppIntegration;

  /// Error message when updating app status fails
  ///
  /// In en, this message translates to:
  /// **'An error occurred while updating the app status.'**
  String get errorUpdatingAppStatus;

  /// Migration ETA calculation in progress message
  ///
  /// In en, this message translates to:
  /// **'Calculating...'**
  String get calculatingETA;

  /// Migration time remaining in minutes
  ///
  /// In en, this message translates to:
  /// **'About {minutes} minutes remaining'**
  String aboutMinutesRemaining(int minutes);

  /// Migration time remaining is about a minute
  ///
  /// In en, this message translates to:
  /// **'About a minute remaining'**
  String get aboutAMinuteRemaining;

  /// Migration is almost complete
  ///
  /// In en, this message translates to:
  /// **'Almost done...'**
  String get almostDone;

  /// Notification title for omi app messages
  ///
  /// In en, this message translates to:
  /// **'omi says'**
  String get omiSays;

  /// Migration start message when analyzing data
  ///
  /// In en, this message translates to:
  /// **'Analyzing your data...'**
  String get analyzingYourData;

  /// Notification body when migration starts
  ///
  /// In en, this message translates to:
  /// **'Migrating to {level} protection...'**
  String migratingToProtection(String level);

  /// Migration message when no data needs to be migrated
  ///
  /// In en, this message translates to:
  /// **'No data to migrate. Finalizing...'**
  String get noDataToMigrateFinalizing;

  /// Migration progress message with item type and percentage
  ///
  /// In en, this message translates to:
  /// **'Migrating {itemType}... {percentage}%'**
  String migratingItemsProgress(String itemType, int percentage);

  /// Migration message when all objects have been migrated
  ///
  /// In en, this message translates to:
  /// **'All objects migrated. Finalizing...'**
  String get allObjectsMigratedFinalizing;

  /// Error message when data migration fails
  ///
  /// In en, this message translates to:
  /// **'An error occurred during migration. Please try again.'**
  String get migrationErrorOccurred;

  /// Message shown when migration finishes successfully
  ///
  /// In en, this message translates to:
  /// **'Migration complete!'**
  String get migrationComplete;

  /// Success notification after migration completes
  ///
  /// In en, this message translates to:
  /// **'Your data is now protected with the new {level} settings.'**
  String dataProtectedWithSettings(String level);

  /// Lowercase plural of chat for migration item type
  ///
  /// In en, this message translates to:
  /// **'chats'**
  String get chatsLowercase;

  /// Lowercase word for data in migration context
  ///
  /// In en, this message translates to:
  /// **'data'**
  String get dataLowercase;

  /// Title for notification shown when device detects a fall
  ///
  /// In en, this message translates to:
  /// **'Ouch'**
  String get fallNotificationTitle;

  /// Body text for notification shown when device detects a fall
  ///
  /// In en, this message translates to:
  /// **'Did you fall?'**
  String get fallNotificationBody;

  /// Notification title for important conversation (>30 min) completion
  ///
  /// In en, this message translates to:
  /// **'Important Conversation'**
  String get importantConversationTitle;

  /// Notification body prompting user to share conversation summary
  ///
  /// In en, this message translates to:
  /// **'You just had an important convo. Tap to share the summary with others.'**
  String get importantConversationBody;

  /// Label for template name field
  ///
  /// In en, this message translates to:
  /// **'Template Name'**
  String get templateName;

  /// Hint text for template name field
  ///
  /// In en, this message translates to:
  /// **'e.g., Meeting Action Items Extractor'**
  String get templateNameHint;

  /// Validation error when name is too short
  ///
  /// In en, this message translates to:
  /// **'Name must be at least 3 characters'**
  String get nameMustBeAtLeast3Characters;

  /// Hint text for conversation prompt field
  ///
  /// In en, this message translates to:
  /// **'e.g., Extract action items, decisions made, and key takeaways from the provided conversation.'**
  String get conversationPromptHint;

  /// Validation error when prompt is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter a prompt for your app'**
  String get pleaseEnterAppPrompt;

  /// Validation error when prompt is too short
  ///
  /// In en, this message translates to:
  /// **'Prompt must be at least 10 characters'**
  String get promptMustBeAtLeast10Characters;

  /// Description when template is public
  ///
  /// In en, this message translates to:
  /// **'Anyone can discover your template'**
  String get anyoneCanDiscoverTemplate;

  /// Description when template is private
  ///
  /// In en, this message translates to:
  /// **'Only you can use this template'**
  String get onlyYouCanUseTemplate;

  /// Status message during app creation
  ///
  /// In en, this message translates to:
  /// **'Generating description...'**
  String get generatingDescription;

  /// Status message during app creation
  ///
  /// In en, this message translates to:
  /// **'Creating app icon...'**
  String get creatingAppIcon;

  /// Status message during app creation
  ///
  /// In en, this message translates to:
  /// **'Installing app...'**
  String get installingApp;

  /// Success message after app is created and installed
  ///
  /// In en, this message translates to:
  /// **'App created and installed!'**
  String get appCreatedAndInstalled;

  /// Success message after app is created
  ///
  /// In en, this message translates to:
  /// **'App created successfully!'**
  String get appCreatedSuccessfully;

  /// Error message when app creation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create app. Please try again.'**
  String get failedToCreateApp;

  /// Validation error when only proactive notification capability is selected
  ///
  /// In en, this message translates to:
  /// **'Please select one more core capability for your app to proceed'**
  String get addAppSelectCoreCapability;

  /// Validation error when paid app has no payment plan or price
  ///
  /// In en, this message translates to:
  /// **'Please select a payment plan and enter a price for your app'**
  String get addAppSelectPaymentPlan;

  /// Validation error when no capability is selected
  ///
  /// In en, this message translates to:
  /// **'Please select at least one capability for your app'**
  String get addAppSelectCapability;

  /// Validation error when no app logo is selected
  ///
  /// In en, this message translates to:
  /// **'Please select a logo for your app'**
  String get addAppSelectLogo;

  /// Validation error when chat capability selected but no prompt entered
  ///
  /// In en, this message translates to:
  /// **'Please enter a chat prompt for your app'**
  String get addAppEnterChatPrompt;

  /// Validation error when memories capability selected but no prompt entered
  ///
  /// In en, this message translates to:
  /// **'Please enter a conversation prompt for your app'**
  String get addAppEnterConversationPrompt;

  /// Validation error when external integration selected but no trigger event
  ///
  /// In en, this message translates to:
  /// **'Please select a trigger event for your app'**
  String get addAppSelectTriggerEvent;

  /// Validation error when external integration selected but no webhook URL
  ///
  /// In en, this message translates to:
  /// **'Please enter a webhook URL for your app'**
  String get addAppEnterWebhookUrl;

  /// Validation error when no app category selected
  ///
  /// In en, this message translates to:
  /// **'Please select a category for your app'**
  String get addAppSelectCategory;

  /// Generic validation error for incomplete form
  ///
  /// In en, this message translates to:
  /// **'Please fill in all the required fields correctly'**
  String get addAppFillRequiredFields;

  /// Success message after app update
  ///
  /// In en, this message translates to:
  /// **'App updated successfully 🚀'**
  String get addAppUpdatedSuccess;

  /// Error message when app update fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update app. Please try again later'**
  String get addAppUpdateFailed;

  /// Success message after app submission
  ///
  /// In en, this message translates to:
  /// **'App submitted successfully 🚀'**
  String get addAppSubmittedSuccess;

  /// Error when file picker fails to open
  ///
  /// In en, this message translates to:
  /// **'Error opening file picker: {message}'**
  String addAppErrorOpeningFilePicker(String message);

  /// Error when image selection fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting image: {error}'**
  String addAppErrorSelectingImage(String error);

  /// Error when photos permission is denied
  ///
  /// In en, this message translates to:
  /// **'Photos permission denied. Please allow access to photos to select an image'**
  String get addAppPhotosPermissionDenied;

  /// Generic error when image selection fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting image. Please try again.'**
  String get addAppErrorSelectingImageRetry;

  /// Error when thumbnail selection fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting thumbnail: {error}'**
  String addAppErrorSelectingThumbnail(String error);

  /// Generic error when thumbnail selection fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting thumbnail. Please try again.'**
  String get addAppErrorSelectingThumbnailRetry;

  /// Error when trying to select capabilities alongside Persona
  ///
  /// In en, this message translates to:
  /// **'Other capabilities cannot be selected with Persona'**
  String get addAppCapabilityConflictWithPersona;

  /// Error when trying to select Persona alongside other capabilities
  ///
  /// In en, this message translates to:
  /// **'Persona cannot be selected with other capabilities'**
  String get addAppPersonaConflictWithCapabilities;

  /// Error shown when Twitter handle is not found
  ///
  /// In en, this message translates to:
  /// **'Twitter handle not found'**
  String get personaTwitterHandleNotFound;

  /// Error shown when Twitter handle is suspended
  ///
  /// In en, this message translates to:
  /// **'Twitter handle is suspended'**
  String get personaTwitterHandleSuspended;

  /// Error shown when Twitter handle verification fails
  ///
  /// In en, this message translates to:
  /// **'Failed to verify Twitter handle'**
  String get personaFailedToVerifyTwitter;

  /// Error shown when fetching persona fails
  ///
  /// In en, this message translates to:
  /// **'Failed to fetch your persona'**
  String get personaFailedToFetch;

  /// Error shown when creating persona fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create your persona'**
  String get personaFailedToCreate;

  /// Error shown when no knowledge source is connected
  ///
  /// In en, this message translates to:
  /// **'Please connect at least one knowledge data source (Omi or Twitter)'**
  String get personaConnectKnowledgeSource;

  /// Success message when persona is updated
  ///
  /// In en, this message translates to:
  /// **'Persona updated successfully'**
  String get personaUpdatedSuccessfully;

  /// Error shown when updating persona fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update persona'**
  String get personaFailedToUpdate;

  /// Error shown when no image is selected for persona
  ///
  /// In en, this message translates to:
  /// **'Please select an image'**
  String get personaPleaseSelectImage;

  /// Error shown when creating persona fails with retry suggestion
  ///
  /// In en, this message translates to:
  /// **'Failed to create your persona. Please try again later.'**
  String get personaFailedToCreateTryLater;

  /// Error shown when creating persona fails with error details
  ///
  /// In en, this message translates to:
  /// **'Failed to create persona: {error}'**
  String personaFailedToCreateWithError(String error);

  /// Error shown when enabling persona fails
  ///
  /// In en, this message translates to:
  /// **'Failed to enable persona'**
  String get personaFailedToEnable;

  /// Error shown when enabling persona fails with error details
  ///
  /// In en, this message translates to:
  /// **'Error enabling persona: {error}'**
  String personaErrorEnablingWithError(String error);

  /// Error message when fetching supported countries fails
  ///
  /// In en, this message translates to:
  /// **'Failed to fetch supported countries. Please try again later.'**
  String get paymentFailedToFetchCountries;

  /// Error message when setting default payment method fails
  ///
  /// In en, this message translates to:
  /// **'Failed to set default payment method. Please try again later.'**
  String get paymentFailedToSetDefault;

  /// Error message when saving PayPal details fails
  ///
  /// In en, this message translates to:
  /// **'Failed to save PayPal details. Please try again later.'**
  String get paymentFailedToSavePaypal;

  /// Placeholder example email for PayPal email input field
  ///
  /// In en, this message translates to:
  /// **'nik@example.com'**
  String get paypalEmailHint;

  /// Placeholder example PayPal.me link for input field
  ///
  /// In en, this message translates to:
  /// **'paypal.me/nik'**
  String get paypalMeLinkHint;

  /// Payment method name for Stripe
  ///
  /// In en, this message translates to:
  /// **'Stripe'**
  String get paymentMethodStripe;

  /// Payment method name for PayPal
  ///
  /// In en, this message translates to:
  /// **'PayPal'**
  String get paymentMethodPayPal;

  /// Status label when payment method is active
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get paymentStatusActive;

  /// Status label when payment method is connected but not active
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get paymentStatusConnected;

  /// Status label when payment method is not connected
  ///
  /// In en, this message translates to:
  /// **'Not Connected'**
  String get paymentStatusNotConnected;

  /// Label for app cost input field
  ///
  /// In en, this message translates to:
  /// **'App Cost'**
  String get paymentAppCost;

  /// Validation error when amount is not a valid number
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid amount'**
  String get paymentEnterValidAmount;

  /// Validation error when app cost is less than 1
  ///
  /// In en, this message translates to:
  /// **'Please enter an amount greater than 0'**
  String get paymentEnterAmountGreaterThanZero;

  /// Label for payment plan selection
  ///
  /// In en, this message translates to:
  /// **'Payment Plan'**
  String get paymentPlan;

  /// Placeholder when no payment plan is selected
  ///
  /// In en, this message translates to:
  /// **'None Selected'**
  String get paymentNoneSelected;

  /// Validation error when app description is empty in AI app generator
  ///
  /// In en, this message translates to:
  /// **'Please enter a description for your app'**
  String get aiGenPleaseEnterDescription;

  /// Status message shown while generating app icon
  ///
  /// In en, this message translates to:
  /// **'Creating app icon...'**
  String get aiGenCreatingAppIcon;

  /// Error message with details in AI app generator
  ///
  /// In en, this message translates to:
  /// **'An error occurred: {message}'**
  String aiGenErrorOccurredWithDetails(String message);

  /// Success message when AI-generated app is created
  ///
  /// In en, this message translates to:
  /// **'App created successfully!'**
  String get aiGenAppCreatedSuccessfully;

  /// Error message when app creation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create app'**
  String get aiGenFailedToCreateApp;

  /// Error message when exception occurs during app creation
  ///
  /// In en, this message translates to:
  /// **'An error occurred while creating the app'**
  String get aiGenErrorWhileCreatingApp;

  /// Error message when AI app generation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to generate app. Please try again.'**
  String get aiGenFailedToGenerateApp;

  /// Error message when icon regeneration fails
  ///
  /// In en, this message translates to:
  /// **'Failed to regenerate icon'**
  String get aiGenFailedToRegenerateIcon;

  /// Validation error when trying to submit without generating app first
  ///
  /// In en, this message translates to:
  /// **'Please generate an app first'**
  String get aiGenPleaseGenerateAppFirst;

  /// Title asking user for their X (Twitter) handle
  ///
  /// In en, this message translates to:
  /// **'What\'s your X handle?'**
  String get xHandleTitle;

  /// Description explaining why X handle is needed
  ///
  /// In en, this message translates to:
  /// **'We will pre-train your Omi clone\nbased on your account\'s activity'**
  String get xHandleDescription;

  /// Placeholder hint for X handle input field
  ///
  /// In en, this message translates to:
  /// **'@nikshevchenko'**
  String get xHandleHint;

  /// Validation error when X handle is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter your X handle'**
  String get xHandlePleaseEnter;

  /// Validation error when X handle is invalid
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid X handle'**
  String get xHandlePleaseEnterValid;

  /// Button text to proceed to next step
  ///
  /// In en, this message translates to:
  /// **'Next'**
  String get nextButton;

  /// Button text to connect Omi device
  ///
  /// In en, this message translates to:
  /// **'Connect Omi Device'**
  String get connectOmiDevice;

  /// Dialog description when switching from unlimited plan
  ///
  /// In en, this message translates to:
  /// **'You\'re switching your Unlimited Plan to the {title}. Are you sure you want to proceed?'**
  String planSwitchingDescriptionWithTitle(String title);

  /// Success message when plan upgrade is scheduled
  ///
  /// In en, this message translates to:
  /// **'Upgrade scheduled! Your monthly plan continues until the end of your billing period, then automatically switches to annual.'**
  String get planUpgradeScheduledMessage;

  /// Error when plan change cannot be scheduled
  ///
  /// In en, this message translates to:
  /// **'Could not schedule plan change. Please try again.'**
  String get couldNotSchedulePlanChange;

  /// Default message when subscription is reactivated
  ///
  /// In en, this message translates to:
  /// **'Your subscription has been reactivated! No charge now - you\'ll be billed at the end of your current period.'**
  String get subscriptionReactivatedDefault;

  /// Success message after subscription checkout
  ///
  /// In en, this message translates to:
  /// **'Subscription successful! You\'ve been charged for the new billing period.'**
  String get subscriptionSuccessfulCharged;

  /// Error when subscription cannot be processed
  ///
  /// In en, this message translates to:
  /// **'Could not process subscription. Please try again.'**
  String get couldNotProcessSubscription;

  /// Error when upgrade page cannot be launched
  ///
  /// In en, this message translates to:
  /// **'Could not launch upgrade page. Please try again.'**
  String get couldNotLaunchUpgradePage;

  /// JSON configuration placeholder hint text in transcription settings
  ///
  /// In en, this message translates to:
  /// **'Paste your JSON configuration here...'**
  String get transcriptionJsonPlaceholder;

  /// Tab title for Omi transcription source option
  ///
  /// In en, this message translates to:
  /// **'Omi'**
  String get transcriptionSourceOmi;

  /// Placeholder text for the price input field showing a sample price format
  ///
  /// In en, this message translates to:
  /// **'0.00'**
  String get pricePlaceholder;

  /// Error message when file picker fails to open
  ///
  /// In en, this message translates to:
  /// **'Error opening file picker: {message}'**
  String importErrorOpeningFilePicker(String message);

  /// Generic error message with error details
  ///
  /// In en, this message translates to:
  /// **'Error: {error}'**
  String importErrorGeneric(String error);

  /// Notification title shown when conversations are merged successfully
  ///
  /// In en, this message translates to:
  /// **'Conversations Merged Successfully'**
  String get mergeConversationsSuccessTitle;

  /// Notification body shown when conversations are merged successfully
  ///
  /// In en, this message translates to:
  /// **'{count} conversations have been merged successfully'**
  String mergeConversationsSuccessBody(int count);

  /// Title for the daily reflection notification shown at 9 PM
  ///
  /// In en, this message translates to:
  /// **'Time for Daily Reflection'**
  String get dailyReflectionNotificationTitle;

  /// Body text for the daily reflection notification
  ///
  /// In en, this message translates to:
  /// **'Tell me about your day'**
  String get dailyReflectionNotificationBody;

  /// Title for action item reminder notifications
  ///
  /// In en, this message translates to:
  /// **'Omi Reminder'**
  String get actionItemReminderTitle;

  /// Notification title when a device disconnects
  ///
  /// In en, this message translates to:
  /// **'{deviceName} Disconnected'**
  String deviceDisconnectedTitle(String deviceName);

  /// Notification body when a device disconnects
  ///
  /// In en, this message translates to:
  /// **'Please reconnect to continue using your {deviceName}.'**
  String deviceDisconnectedBody(String deviceName);

  /// Onboarding step title for sign in
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get onboardingSignIn;

  /// Onboarding step title for name entry
  ///
  /// In en, this message translates to:
  /// **'Your Name'**
  String get onboardingYourName;

  /// Onboarding step title for language selection
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get onboardingLanguage;

  /// Onboarding step title for permissions
  ///
  /// In en, this message translates to:
  /// **'Permissions'**
  String get onboardingPermissions;

  /// Onboarding step title for completion
  ///
  /// In en, this message translates to:
  /// **'Complete'**
  String get onboardingComplete;

  /// Onboarding step description for sign in
  ///
  /// In en, this message translates to:
  /// **'Welcome to Omi'**
  String get onboardingWelcomeToOmi;

  /// Onboarding step description for name entry
  ///
  /// In en, this message translates to:
  /// **'Tell us about yourself'**
  String get onboardingTellUsAboutYourself;

  /// Onboarding step description for language selection
  ///
  /// In en, this message translates to:
  /// **'Choose your preference'**
  String get onboardingChooseYourPreference;

  /// Onboarding step description for permissions
  ///
  /// In en, this message translates to:
  /// **'Grant required access'**
  String get onboardingGrantRequiredAccess;

  /// Onboarding step description for completion
  ///
  /// In en, this message translates to:
  /// **'You\'re all set'**
  String get onboardingYoureAllSet;

  /// Placeholder text for search field in conversation detail page
  ///
  /// In en, this message translates to:
  /// **'Search transcript or summary...'**
  String get searchTranscriptOrSummary;

  /// Default title for a new goal in the goal tracker widget
  ///
  /// In en, this message translates to:
  /// **'My goal'**
  String get myGoal;

  /// Error message shown when a deep-linked app cannot be found
  ///
  /// In en, this message translates to:
  /// **'Oops! Looks like the app you are looking for is not available.'**
  String get appNotAvailable;

  /// Error message when Todoist OAuth fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Todoist'**
  String get failedToConnectTodoist;

  /// Error message when Asana OAuth fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Asana'**
  String get failedToConnectAsana;

  /// Error message when Google Tasks OAuth fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Google Tasks'**
  String get failedToConnectGoogleTasks;

  /// Error message when ClickUp OAuth fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to ClickUp'**
  String get failedToConnectClickUp;

  /// Error message when OAuth fails with specific error details
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to {serviceName}: {error}'**
  String failedToConnectServiceWithError(String serviceName, String error);

  /// Success message when Todoist OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Todoist!'**
  String get successfullyConnectedTodoist;

  /// Error message when Todoist authentication fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Todoist. Please try again.'**
  String get failedToConnectTodoistRetry;

  /// Success message when Asana OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Asana!'**
  String get successfullyConnectedAsana;

  /// Error message when Asana authentication fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Asana. Please try again.'**
  String get failedToConnectAsanaRetry;

  /// Success message when Google Tasks OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Google Tasks!'**
  String get successfullyConnectedGoogleTasks;

  /// Error message when Google Tasks authentication fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Google Tasks. Please try again.'**
  String get failedToConnectGoogleTasksRetry;

  /// Success message when ClickUp OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to ClickUp!'**
  String get successfullyConnectedClickUp;

  /// Error message when ClickUp authentication fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to ClickUp. Please try again.'**
  String get failedToConnectClickUpRetry;

  /// Success message when Notion OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Notion!'**
  String get successfullyConnectedNotion;

  /// Error message when Notion status refresh fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh Notion connection status.'**
  String get failedToRefreshNotionStatus;

  /// Success message when Google Calendar OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Google!'**
  String get successfullyConnectedGoogle;

  /// Error message when Google status refresh fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh Google connection status.'**
  String get failedToRefreshGoogleStatus;

  /// Success message when Whoop OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Whoop!'**
  String get successfullyConnectedWhoop;

  /// Error message when Whoop status refresh fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh Whoop connection status.'**
  String get failedToRefreshWhoopStatus;

  /// Success message when GitHub OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to GitHub!'**
  String get successfullyConnectedGitHub;

  /// Error message when GitHub status refresh fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh GitHub connection status.'**
  String get failedToRefreshGitHubStatus;

  /// Error message when Google sign-in fails
  ///
  /// In en, this message translates to:
  /// **'Failed to sign in with Google, please try again.'**
  String get authFailedToSignInWithGoogle;

  /// Error message when authentication fails
  ///
  /// In en, this message translates to:
  /// **'Authentication failed. Please try again.'**
  String get authenticationFailed;

  /// Error message when Apple sign-in fails
  ///
  /// In en, this message translates to:
  /// **'Failed to sign in with Apple, please try again.'**
  String get authFailedToSignInWithApple;

  /// Error message when retrieving Firebase token fails
  ///
  /// In en, this message translates to:
  /// **'Failed to retrieve firebase token, please try again.'**
  String get authFailedToRetrieveToken;

  /// Error message for unexpected Firebase error during sign-in
  ///
  /// In en, this message translates to:
  /// **'Unexpected error signing in, Firebase error, please try again.'**
  String get authUnexpectedErrorFirebase;

  /// Error message for unexpected error during sign-in
  ///
  /// In en, this message translates to:
  /// **'Unexpected error signing in, please try again'**
  String get authUnexpectedError;

  /// Error message when linking Google account fails
  ///
  /// In en, this message translates to:
  /// **'Failed to link with Google, please try again.'**
  String get authFailedToLinkGoogle;

  /// Error message when linking Apple account fails
  ///
  /// In en, this message translates to:
  /// **'Failed to link with Apple, please try again.'**
  String get authFailedToLinkApple;

  /// Error message when Bluetooth permission is needed
  ///
  /// In en, this message translates to:
  /// **'Bluetooth permission is required to connect to your device.'**
  String get onboardingBluetoothRequired;

  /// Error when Bluetooth permission is denied on macOS
  ///
  /// In en, this message translates to:
  /// **'Bluetooth permission denied. Please grant permission in System Preferences.'**
  String get onboardingBluetoothDeniedSystemPrefs;

  /// Error showing Bluetooth permission status
  ///
  /// In en, this message translates to:
  /// **'Bluetooth permission status: {status}. Please check System Preferences.'**
  String onboardingBluetoothStatusCheckPrefs(String status);

  /// Error when checking Bluetooth permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Bluetooth permission: {error}'**
  String onboardingFailedCheckBluetooth(String error);

  /// Error when notification permission is denied
  ///
  /// In en, this message translates to:
  /// **'Notification permission denied. Please grant permission in System Preferences.'**
  String get onboardingNotificationDeniedSystemPrefs;

  /// Error when notification permission is denied with specific path
  ///
  /// In en, this message translates to:
  /// **'Notification permission denied. Please grant permission in System Preferences > Notifications.'**
  String get onboardingNotificationDeniedNotifications;

  /// Error showing notification permission status
  ///
  /// In en, this message translates to:
  /// **'Notification permission status: {status}. Please check System Preferences.'**
  String onboardingNotificationStatusCheckPrefs(String status);

  /// Error when checking notification permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Notification permission: {error}'**
  String onboardingFailedCheckNotification(String error);

  /// Instructions to grant location permission
  ///
  /// In en, this message translates to:
  /// **'Please grant location permission in Settings > Privacy & Security > Location Services'**
  String get onboardingLocationGrantInSettings;

  /// Error when microphone permission is needed
  ///
  /// In en, this message translates to:
  /// **'Microphone permission is required for recording.'**
  String get onboardingMicrophoneRequired;

  /// Error when microphone permission is denied
  ///
  /// In en, this message translates to:
  /// **'Microphone permission denied. Please grant permission in System Preferences > Privacy & Security > Microphone.'**
  String get onboardingMicrophoneDenied;

  /// Error showing microphone permission status
  ///
  /// In en, this message translates to:
  /// **'Microphone permission status: {status}. Please check System Preferences.'**
  String onboardingMicrophoneStatusCheckPrefs(String status);

  /// Error when checking microphone permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Microphone permission: {error}'**
  String onboardingFailedCheckMicrophone(String error);

  /// Error when screen capture permission is needed
  ///
  /// In en, this message translates to:
  /// **'Screen capture permission is required for system audio recording.'**
  String get onboardingScreenCaptureRequired;

  /// Error when screen capture permission is denied
  ///
  /// In en, this message translates to:
  /// **'Screen capture permission denied. Please grant permission in System Preferences > Privacy & Security > Screen Recording.'**
  String get onboardingScreenCaptureDenied;

  /// Error showing screen capture permission status
  ///
  /// In en, this message translates to:
  /// **'Screen capture permission status: {status}. Please check System Preferences.'**
  String onboardingScreenCaptureStatusCheckPrefs(String status);

  /// Error when checking screen capture permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Screen Capture permission: {error}'**
  String onboardingFailedCheckScreenCapture(String error);

  /// Error when accessibility permission is needed
  ///
  /// In en, this message translates to:
  /// **'Accessibility permission is required for detecting browser meetings.'**
  String get onboardingAccessibilityRequired;

  /// Error showing accessibility permission status
  ///
  /// In en, this message translates to:
  /// **'Accessibility permission status: {status}. Please check System Preferences.'**
  String onboardingAccessibilityStatusCheckPrefs(String status);

  /// Error when checking accessibility permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Accessibility permission: {error}'**
  String onboardingFailedCheckAccessibility(String error);

  /// Error when camera is not available on desktop
  ///
  /// In en, this message translates to:
  /// **'Camera capture is not available on this platform'**
  String get msgCameraNotAvailable;

  /// Error when camera permission is denied
  ///
  /// In en, this message translates to:
  /// **'Camera permission denied. Please allow access to camera'**
  String get msgCameraPermissionDenied;

  /// Error when camera access fails
  ///
  /// In en, this message translates to:
  /// **'Error accessing camera: {error}'**
  String msgCameraAccessError(String error);

  /// Generic error when taking photo fails
  ///
  /// In en, this message translates to:
  /// **'Error taking photo. Please try again.'**
  String get msgPhotoError;

  /// Error when user tries to select more than 4 images
  ///
  /// In en, this message translates to:
  /// **'You can only select up to 4 images'**
  String get msgMaxImagesLimit;

  /// Error when file picker fails to open
  ///
  /// In en, this message translates to:
  /// **'Error opening file picker: {error}'**
  String msgFilePickerError(String error);

  /// Error when selecting images fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting images: {error}'**
  String msgSelectImagesError(String error);

  /// Error when photos permission is denied
  ///
  /// In en, this message translates to:
  /// **'Photos permission denied. Please allow access to photos to select images'**
  String get msgPhotosPermissionDenied;

  /// Generic error when selecting images fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting images. Please try again.'**
  String get msgSelectImagesGenericError;

  /// Error when user tries to select more than 4 files
  ///
  /// In en, this message translates to:
  /// **'You can only select up to 4 files'**
  String get msgMaxFilesLimit;

  /// Error when selecting files fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting files: {error}'**
  String msgSelectFilesError(String error);

  /// Generic error when selecting files fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting files. Please try again.'**
  String get msgSelectFilesGenericError;

  /// Error when file upload fails
  ///
  /// In en, this message translates to:
  /// **'Failed to upload file, please try again later'**
  String get msgUploadFileFailed;

  /// Loading text while reading memories
  ///
  /// In en, this message translates to:
  /// **'Reading your memories...'**
  String get msgReadingMemories;

  /// Loading text while learning from memories
  ///
  /// In en, this message translates to:
  /// **'Learning from your memories...'**
  String get msgLearningMemories;

  /// Error when attached file upload fails
  ///
  /// In en, this message translates to:
  /// **'Failed to upload the attached file.'**
  String get msgUploadAttachedFileFailed;

  /// No description provided for @captureRecordingError.
  ///
  /// In en, this message translates to:
  /// **'An error occurred during recording: {error}'**
  String captureRecordingError(String error);

  /// No description provided for @captureRecordingStoppedDisplayIssue.
  ///
  /// In en, this message translates to:
  /// **'Recording stopped: {reason}. You may need to reconnect external displays or restart recording.'**
  String captureRecordingStoppedDisplayIssue(String reason);

  /// No description provided for @captureMicrophonePermissionRequired.
  ///
  /// In en, this message translates to:
  /// **'Microphone permission required'**
  String get captureMicrophonePermissionRequired;

  /// No description provided for @captureMicrophonePermissionInSystemPreferences.
  ///
  /// In en, this message translates to:
  /// **'Grant microphone permission in System Preferences'**
  String get captureMicrophonePermissionInSystemPreferences;

  /// No description provided for @captureScreenRecordingPermissionRequired.
  ///
  /// In en, this message translates to:
  /// **'Screen recording permission required'**
  String get captureScreenRecordingPermissionRequired;

  /// No description provided for @captureDisplayDetectionFailed.
  ///
  /// In en, this message translates to:
  /// **'Display detection failed. Recording stopped.'**
  String get captureDisplayDetectionFailed;

  /// Error message when audio bytes webhook URL is invalid in developer settings
  ///
  /// In en, this message translates to:
  /// **'Invalid audio bytes webhook URL'**
  String get devModeInvalidAudioBytesWebhookUrl;

  /// Error message when realtime transcript webhook URL is invalid in developer settings
  ///
  /// In en, this message translates to:
  /// **'Invalid realtime transcript webhook URL'**
  String get devModeInvalidRealtimeTranscriptWebhookUrl;

  /// Error message when conversation created webhook URL is invalid in developer settings
  ///
  /// In en, this message translates to:
  /// **'Invalid conversation created webhook URL'**
  String get devModeInvalidConversationCreatedWebhookUrl;

  /// Error message when day summary webhook URL is invalid in developer settings
  ///
  /// In en, this message translates to:
  /// **'Invalid day summary webhook URL'**
  String get devModeInvalidDaySummaryWebhookUrl;

  /// Success message shown when developer mode settings are saved
  ///
  /// In en, this message translates to:
  /// **'Settings saved!'**
  String get devModeSettingsSaved;

  /// Error message when voice transcription fails
  ///
  /// In en, this message translates to:
  /// **'Failed to transcribe audio'**
  String get voiceFailedToTranscribe;

  /// Title for dialog requesting location permission
  ///
  /// In en, this message translates to:
  /// **'Location Permission Required'**
  String get locationPermissionRequired;

  /// Explanation text for location permission dialog
  ///
  /// In en, this message translates to:
  /// **'Fast Transfer requires location permission to verify WiFi connection. Please grant location permission to continue.'**
  String get locationPermissionContent;

  /// Title for PDF transcript export document
  ///
  /// In en, this message translates to:
  /// **'Transcript Export'**
  String get pdfTranscriptExport;

  /// Title for PDF conversation export document
  ///
  /// In en, this message translates to:
  /// **'Conversation Export'**
  String get pdfConversationExport;

  /// Label showing the conversation title in PDF export
  ///
  /// In en, this message translates to:
  /// **'Title: {title}'**
  String pdfTitleLabel(String title);

  /// Indicator shown when a conversation is newly created
  ///
  /// In en, this message translates to:
  /// **'New 🚀'**
  String get conversationNewIndicator;

  /// Count of photos in a conversation
  ///
  /// In en, this message translates to:
  /// **'{count} photos'**
  String conversationPhotosCount(int count);

  /// Status indicator shown when conversations are being merged
  ///
  /// In en, this message translates to:
  /// **'Merging...'**
  String get mergingStatus;

  /// Duration in singular second
  ///
  /// In en, this message translates to:
  /// **'{count} sec'**
  String timeSecsSingular(int count);

  /// Duration in plural seconds
  ///
  /// In en, this message translates to:
  /// **'{count} secs'**
  String timeSecsPlural(int count);

  /// Duration in singular minute
  ///
  /// In en, this message translates to:
  /// **'{count} min'**
  String timeMinSingular(int count);

  /// Duration in plural minutes
  ///
  /// In en, this message translates to:
  /// **'{count} mins'**
  String timeMinsPlural(int count);

  /// Duration in minutes and seconds
  ///
  /// In en, this message translates to:
  /// **'{mins} mins {secs} secs'**
  String timeMinsAndSecs(int mins, int secs);

  /// Duration in singular hour
  ///
  /// In en, this message translates to:
  /// **'{count} hour'**
  String timeHourSingular(int count);

  /// Duration in plural hours
  ///
  /// In en, this message translates to:
  /// **'{count} hours'**
  String timeHoursPlural(int count);

  /// Duration in hours and minutes
  ///
  /// In en, this message translates to:
  /// **'{hours} hours {mins} mins'**
  String timeHoursAndMins(int hours, int mins);

  /// Duration in singular day
  ///
  /// In en, this message translates to:
  /// **'{count} day'**
  String timeDaySingular(int count);

  /// Duration in plural days
  ///
  /// In en, this message translates to:
  /// **'{count} days'**
  String timeDaysPlural(int count);

  /// Duration in days and hours
  ///
  /// In en, this message translates to:
  /// **'{days} days {hours} hours'**
  String timeDaysAndHours(int days, int hours);

  /// Compact duration in seconds
  ///
  /// In en, this message translates to:
  /// **'{count}s'**
  String timeCompactSecs(int count);

  /// Compact duration in minutes
  ///
  /// In en, this message translates to:
  /// **'{count}m'**
  String timeCompactMins(int count);

  /// Compact duration in minutes and seconds
  ///
  /// In en, this message translates to:
  /// **'{mins}m {secs}s'**
  String timeCompactMinsAndSecs(int mins, int secs);

  /// Compact duration in hours
  ///
  /// In en, this message translates to:
  /// **'{count}h'**
  String timeCompactHours(int count);

  /// Compact duration in hours and minutes
  ///
  /// In en, this message translates to:
  /// **'{hours}h {mins}m'**
  String timeCompactHoursAndMins(int hours, int mins);

  /// Title for the move to folder bottom sheet
  ///
  /// In en, this message translates to:
  /// **'Move to Folder'**
  String get moveToFolder;

  /// Message shown when there are no folders to move a conversation to
  ///
  /// In en, this message translates to:
  /// **'No folders available'**
  String get noFoldersAvailable;

  /// No description provided for @newFolder.
  ///
  /// In en, this message translates to:
  /// **'New Folder'**
  String get newFolder;

  /// No description provided for @color.
  ///
  /// In en, this message translates to:
  /// **'Color'**
  String get color;

  /// Status message while waiting for device connection
  ///
  /// In en, this message translates to:
  /// **'Waiting for device...'**
  String get waitingForDevice;

  /// Prompt for user to start speaking
  ///
  /// In en, this message translates to:
  /// **'Say something...'**
  String get saySomething;

  /// Status message during system audio initialization on desktop
  ///
  /// In en, this message translates to:
  /// **'Initialising System Audio'**
  String get initialisingSystemAudio;

  /// Button label to stop recording
  ///
  /// In en, this message translates to:
  /// **'Stop Recording'**
  String get stopRecording;

  /// Button label to continue recording
  ///
  /// In en, this message translates to:
  /// **'Continue Recording'**
  String get continueRecording;

  /// Status message during recorder initialization on mobile
  ///
  /// In en, this message translates to:
  /// **'Initialising Recorder'**
  String get initialisingRecorder;

  /// Button label to pause recording
  ///
  /// In en, this message translates to:
  /// **'Pause Recording'**
  String get pauseRecording;

  /// Button label to resume recording
  ///
  /// In en, this message translates to:
  /// **'Resume Recording'**
  String get resumeRecording;

  /// No description provided for @noDailyRecapsYet.
  ///
  /// In en, this message translates to:
  /// **'No daily recaps yet'**
  String get noDailyRecapsYet;

  /// No description provided for @dailyRecapsDescription.
  ///
  /// In en, this message translates to:
  /// **'Your daily recaps will appear here once generated'**
  String get dailyRecapsDescription;

  /// Title for transfer method selection dialog
  ///
  /// In en, this message translates to:
  /// **'Choose Transfer Method'**
  String get chooseTransferMethod;

  /// Speed description for fast transfer via WiFi
  ///
  /// In en, this message translates to:
  /// **'~150 KB/s via WiFi'**
  String get fastTransferSpeed;

  /// No description provided for @largeTimeGapDetected.
  ///
  /// In en, this message translates to:
  /// **'Large time gap detected ({gap})'**
  String largeTimeGapDetected(String gap);

  /// No description provided for @largeTimeGapsDetected.
  ///
  /// In en, this message translates to:
  /// **'Large time gaps detected ({gaps})'**
  String largeTimeGapsDetected(String gaps);

  /// Message shown when WiFi sync fails because device hardware does not support WiFi, automatically falling back to Bluetooth transfer
  ///
  /// In en, this message translates to:
  /// **'Device does not support WiFi sync, switching to Bluetooth'**
  String get deviceDoesNotSupportWifiSwitchingToBle;

  /// No description provided for @appleHealthNotAvailable.
  ///
  /// In en, this message translates to:
  /// **'Apple Health is not available on this device'**
  String get appleHealthNotAvailable;

  /// No description provided for @downloadAudio.
  ///
  /// In en, this message translates to:
  /// **'Download Audio'**
  String get downloadAudio;

  /// No description provided for @audioDownloadSuccess.
  ///
  /// In en, this message translates to:
  /// **'Audio downloaded successfully'**
  String get audioDownloadSuccess;

  /// No description provided for @audioDownloadFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to download audio'**
  String get audioDownloadFailed;

  /// No description provided for @downloadingAudio.
  ///
  /// In en, this message translates to:
  /// **'Downloading audio...'**
  String get downloadingAudio;

  /// No description provided for @shareAudio.
  ///
  /// In en, this message translates to:
  /// **'Share Audio'**
  String get shareAudio;

  /// No description provided for @preparingAudio.
  ///
  /// In en, this message translates to:
  /// **'Preparing Audio'**
  String get preparingAudio;

  /// No description provided for @gettingAudioFiles.
  ///
  /// In en, this message translates to:
  /// **'Getting audio files...'**
  String get gettingAudioFiles;

  /// No description provided for @downloadingAudioProgress.
  ///
  /// In en, this message translates to:
  /// **'Downloading Audio'**
  String get downloadingAudioProgress;

  /// No description provided for @processingAudio.
  ///
  /// In en, this message translates to:
  /// **'Processing Audio'**
  String get processingAudio;

  /// No description provided for @combiningAudioFiles.
  ///
  /// In en, this message translates to:
  /// **'Combining audio files...'**
  String get combiningAudioFiles;

  /// No description provided for @audioReady.
  ///
  /// In en, this message translates to:
  /// **'Audio Ready'**
  String get audioReady;

  /// No description provided for @openingShareSheet.
  ///
  /// In en, this message translates to:
  /// **'Opening share sheet...'**
  String get openingShareSheet;

  /// No description provided for @audioShareFailed.
  ///
  /// In en, this message translates to:
  /// **'Share Failed'**
  String get audioShareFailed;

  /// No description provided for @dailyRecaps.
  ///
  /// In en, this message translates to:
  /// **'Daily Recaps'**
  String get dailyRecaps;

  /// No description provided for @removeFilter.
  ///
  /// In en, this message translates to:
  /// **'Remove Filter'**
  String get removeFilter;

  /// No description provided for @categoryConversationAnalysis.
  ///
  /// In en, this message translates to:
  /// **'Conversation Analysis'**
  String get categoryConversationAnalysis;

  /// No description provided for @categoryPersonalityClone.
  ///
  /// In en, this message translates to:
  /// **'Personality Clone'**
  String get categoryPersonalityClone;

  /// No description provided for @categoryHealth.
  ///
  /// In en, this message translates to:
  /// **'Health'**
  String get categoryHealth;

  /// No description provided for @categoryEducation.
  ///
  /// In en, this message translates to:
  /// **'Education'**
  String get categoryEducation;

  /// No description provided for @categoryCommunication.
  ///
  /// In en, this message translates to:
  /// **'Communication'**
  String get categoryCommunication;

  /// No description provided for @categoryEmotionalSupport.
  ///
  /// In en, this message translates to:
  /// **'Emotional Support'**
  String get categoryEmotionalSupport;

  /// No description provided for @categoryProductivity.
  ///
  /// In en, this message translates to:
  /// **'Productivity'**
  String get categoryProductivity;

  /// No description provided for @categoryEntertainment.
  ///
  /// In en, this message translates to:
  /// **'Entertainment'**
  String get categoryEntertainment;

  /// No description provided for @categoryFinancial.
  ///
  /// In en, this message translates to:
  /// **'Financial'**
  String get categoryFinancial;

  /// No description provided for @categoryTravel.
  ///
  /// In en, this message translates to:
  /// **'Travel'**
  String get categoryTravel;

  /// No description provided for @categorySafety.
  ///
  /// In en, this message translates to:
  /// **'Safety'**
  String get categorySafety;

  /// No description provided for @categoryShopping.
  ///
  /// In en, this message translates to:
  /// **'Shopping'**
  String get categoryShopping;

  /// No description provided for @categorySocial.
  ///
  /// In en, this message translates to:
  /// **'Social'**
  String get categorySocial;

  /// No description provided for @categoryNews.
  ///
  /// In en, this message translates to:
  /// **'News'**
  String get categoryNews;

  /// No description provided for @categoryUtilities.
  ///
  /// In en, this message translates to:
  /// **'Utilities'**
  String get categoryUtilities;

  /// No description provided for @categoryOther.
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get categoryOther;

  /// No description provided for @capabilityChat.
  ///
  /// In en, this message translates to:
  /// **'Chat'**
  String get capabilityChat;

  /// No description provided for @capabilityConversations.
  ///
  /// In en, this message translates to:
  /// **'Conversations'**
  String get capabilityConversations;

  /// No description provided for @capabilityExternalIntegration.
  ///
  /// In en, this message translates to:
  /// **'External Integration'**
  String get capabilityExternalIntegration;

  /// No description provided for @capabilityNotification.
  ///
  /// In en, this message translates to:
  /// **'Notification'**
  String get capabilityNotification;

  /// No description provided for @triggerAudioBytes.
  ///
  /// In en, this message translates to:
  /// **'Audio Bytes'**
  String get triggerAudioBytes;

  /// No description provided for @triggerConversationCreation.
  ///
  /// In en, this message translates to:
  /// **'Conversation Creation'**
  String get triggerConversationCreation;

  /// No description provided for @triggerTranscriptProcessed.
  ///
  /// In en, this message translates to:
  /// **'Transcript Processed'**
  String get triggerTranscriptProcessed;

  /// No description provided for @actionCreateConversations.
  ///
  /// In en, this message translates to:
  /// **'Create conversations'**
  String get actionCreateConversations;

  /// No description provided for @actionCreateMemories.
  ///
  /// In en, this message translates to:
  /// **'Create memories'**
  String get actionCreateMemories;

  /// No description provided for @actionReadConversations.
  ///
  /// In en, this message translates to:
  /// **'Read conversations'**
  String get actionReadConversations;

  /// No description provided for @actionReadMemories.
  ///
  /// In en, this message translates to:
  /// **'Read memories'**
  String get actionReadMemories;

  /// No description provided for @actionReadTasks.
  ///
  /// In en, this message translates to:
  /// **'Read tasks'**
  String get actionReadTasks;

  /// No description provided for @scopeUserName.
  ///
  /// In en, this message translates to:
  /// **'User Name'**
  String get scopeUserName;

  /// No description provided for @scopeUserFacts.
  ///
  /// In en, this message translates to:
  /// **'User Facts'**
  String get scopeUserFacts;

  /// No description provided for @scopeUserConversations.
  ///
  /// In en, this message translates to:
  /// **'User Conversations'**
  String get scopeUserConversations;

  /// No description provided for @scopeUserChat.
  ///
  /// In en, this message translates to:
  /// **'User Chat'**
  String get scopeUserChat;

  /// No description provided for @capabilitySummary.
  ///
  /// In en, this message translates to:
  /// **'Summary'**
  String get capabilitySummary;

  /// No description provided for @capabilityFeatured.
  ///
  /// In en, this message translates to:
  /// **'Featured'**
  String get capabilityFeatured;

  /// No description provided for @capabilityTasks.
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get capabilityTasks;

  /// No description provided for @capabilityIntegrations.
  ///
  /// In en, this message translates to:
  /// **'Integrations'**
  String get capabilityIntegrations;

  /// No description provided for @categoryPersonalityClones.
  ///
  /// In en, this message translates to:
  /// **'Personality Clones'**
  String get categoryPersonalityClones;

  /// No description provided for @categoryProductivityLifestyle.
  ///
  /// In en, this message translates to:
  /// **'Productivity & Lifestyle'**
  String get categoryProductivityLifestyle;

  /// No description provided for @categorySocialEntertainment.
  ///
  /// In en, this message translates to:
  /// **'Social & Entertainment'**
  String get categorySocialEntertainment;

  /// No description provided for @categoryProductivityTools.
  ///
  /// In en, this message translates to:
  /// **'Productivity & Tools'**
  String get categoryProductivityTools;

  /// No description provided for @categoryPersonalWellness.
  ///
  /// In en, this message translates to:
  /// **'Personal & Lifestyle'**
  String get categoryPersonalWellness;

  /// No description provided for @rating.
  ///
  /// In en, this message translates to:
  /// **'Rating'**
  String get rating;

  /// No description provided for @categories.
  ///
  /// In en, this message translates to:
  /// **'Categories'**
  String get categories;

  /// No description provided for @sortBy.
  ///
  /// In en, this message translates to:
  /// **'Sort'**
  String get sortBy;

  /// No description provided for @highestRating.
  ///
  /// In en, this message translates to:
  /// **'Highest Rating'**
  String get highestRating;

  /// No description provided for @lowestRating.
  ///
  /// In en, this message translates to:
  /// **'Lowest Rating'**
  String get lowestRating;

  /// No description provided for @resetFilters.
  ///
  /// In en, this message translates to:
  /// **'Reset filters'**
  String get resetFilters;

  /// No description provided for @applyFilters.
  ///
  /// In en, this message translates to:
  /// **'Apply filters'**
  String get applyFilters;

  /// No description provided for @mostInstalls.
  ///
  /// In en, this message translates to:
  /// **'Most Installs'**
  String get mostInstalls;

  /// No description provided for @couldNotOpenUrl.
  ///
  /// In en, this message translates to:
  /// **'Could not open URL. Please try again.'**
  String get couldNotOpenUrl;

  /// Button text for creating a new task
  ///
  /// In en, this message translates to:
  /// **'New Task'**
  String get newTask;

  /// Button text to view all items
  ///
  /// In en, this message translates to:
  /// **'View All'**
  String get viewAll;

  /// Menu option to add a new task
  ///
  /// In en, this message translates to:
  /// **'Add Task'**
  String get addTask;

  /// No description provided for @addMcpServer.
  ///
  /// In en, this message translates to:
  /// **'Add MCP Server'**
  String get addMcpServer;

  /// No description provided for @connectExternalAiTools.
  ///
  /// In en, this message translates to:
  /// **'Connect external AI tools'**
  String get connectExternalAiTools;

  /// No description provided for @mcpServerUrl.
  ///
  /// In en, this message translates to:
  /// **'MCP Server URL'**
  String get mcpServerUrl;

  /// No description provided for @mcpServerConnected.
  ///
  /// In en, this message translates to:
  /// **'{count} tools connected successfully'**
  String mcpServerConnected(int count);

  /// No description provided for @mcpConnectionFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to MCP server'**
  String get mcpConnectionFailed;

  /// No description provided for @authorizingMcpServer.
  ///
  /// In en, this message translates to:
  /// **'Authorizing...'**
  String get authorizingMcpServer;

  /// No description provided for @whereDidYouHearAboutOmi.
  ///
  /// In en, this message translates to:
  /// **'How did you find us?'**
  String get whereDidYouHearAboutOmi;

  /// No description provided for @tiktok.
  ///
  /// In en, this message translates to:
  /// **'TikTok'**
  String get tiktok;

  /// No description provided for @youtube.
  ///
  /// In en, this message translates to:
  /// **'YouTube'**
  String get youtube;

  /// No description provided for @instagram.
  ///
  /// In en, this message translates to:
  /// **'Instagram'**
  String get instagram;

  /// No description provided for @xTwitter.
  ///
  /// In en, this message translates to:
  /// **'X (Twitter)'**
  String get xTwitter;

  /// No description provided for @reddit.
  ///
  /// In en, this message translates to:
  /// **'Reddit'**
  String get reddit;

  /// No description provided for @friendWordOfMouth.
  ///
  /// In en, this message translates to:
  /// **'Friend'**
  String get friendWordOfMouth;

  /// No description provided for @otherSource.
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get otherSource;

  /// No description provided for @pleaseSpecify.
  ///
  /// In en, this message translates to:
  /// **'Please specify'**
  String get pleaseSpecify;

  /// No description provided for @event.
  ///
  /// In en, this message translates to:
  /// **'Event'**
  String get event;

  /// No description provided for @coworker.
  ///
  /// In en, this message translates to:
  /// **'Coworker'**
  String get coworker;

  /// No description provided for @linkedIn.
  ///
  /// In en, this message translates to:
  /// **'LinkedIn'**
  String get linkedIn;

  /// No description provided for @appStore.
  ///
  /// In en, this message translates to:
  /// **'App Store'**
  String get appStore;

  /// No description provided for @googleSearch.
  ///
  /// In en, this message translates to:
  /// **'Google Search'**
  String get googleSearch;

  /// No description provided for @audioPlaybackUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Audio file is not available for playback'**
  String get audioPlaybackUnavailable;

  /// No description provided for @audioPlaybackFailed.
  ///
  /// In en, this message translates to:
  /// **'Unable to play audio. The file may be corrupted or missing.'**
  String get audioPlaybackFailed;

  /// No description provided for @connectionGuide.
  ///
  /// In en, this message translates to:
  /// **'Connection Guide'**
  String get connectionGuide;

  /// No description provided for @iveDoneThis.
  ///
  /// In en, this message translates to:
  /// **'I\'ve done this'**
  String get iveDoneThis;

  /// No description provided for @pairNewDevice.
  ///
  /// In en, this message translates to:
  /// **'Pair new device'**
  String get pairNewDevice;

  /// No description provided for @dontSeeYourDevice.
  ///
  /// In en, this message translates to:
  /// **'Don\'t see your device?'**
  String get dontSeeYourDevice;

  /// No description provided for @reportAnIssue.
  ///
  /// In en, this message translates to:
  /// **'Report an issue'**
  String get reportAnIssue;

  /// Pairing title for Omi device
  ///
  /// In en, this message translates to:
  /// **'Turn On Omi'**
  String get pairingTitleOmi;

  /// Pairing description for Omi device
  ///
  /// In en, this message translates to:
  /// **'Press and hold the device until it vibrates to turn it on.'**
  String get pairingDescOmi;

  /// Pairing title for Omi DevKit
  ///
  /// In en, this message translates to:
  /// **'Put Omi DevKit in Pairing Mode'**
  String get pairingTitleOmiDevkit;

  /// Pairing description for Omi DevKit
  ///
  /// In en, this message translates to:
  /// **'Press the button once to turn on. The LED will blink purple when in pairing mode.'**
  String get pairingDescOmiDevkit;

  /// Pairing title for Omi Glass
  ///
  /// In en, this message translates to:
  /// **'Turn On Omi Glass'**
  String get pairingTitleOmiGlass;

  /// Pairing description for Omi Glass
  ///
  /// In en, this message translates to:
  /// **'Power on by pressing the side button for 3 seconds.'**
  String get pairingDescOmiGlass;

  /// Pairing title for Plaud Note
  ///
  /// In en, this message translates to:
  /// **'Put Plaud Note in Pairing Mode'**
  String get pairingTitlePlaudNote;

  /// Pairing description for Plaud Note
  ///
  /// In en, this message translates to:
  /// **'Press and hold the side button for 2 seconds. The red LED will blink when ready to pair.'**
  String get pairingDescPlaudNote;

  /// Pairing title for Bee device
  ///
  /// In en, this message translates to:
  /// **'Put Bee in Pairing Mode'**
  String get pairingTitleBee;

  /// Pairing description for Bee device
  ///
  /// In en, this message translates to:
  /// **'Press the button 5 times continuously. The light will start blinking blue and green.'**
  String get pairingDescBee;

  /// Pairing title for Limitless device
  ///
  /// In en, this message translates to:
  /// **'Put Limitless in Pairing Mode'**
  String get pairingTitleLimitless;

  /// Pairing description for Limitless device
  ///
  /// In en, this message translates to:
  /// **'When any light is visible, press once and then press and hold until the device shows a pink light, then release.'**
  String get pairingDescLimitless;

  /// Pairing title for Friend Pendant
  ///
  /// In en, this message translates to:
  /// **'Put Friend Pendant in Pairing Mode'**
  String get pairingTitleFriendPendant;

  /// Pairing description for Friend Pendant
  ///
  /// In en, this message translates to:
  /// **'Press the button on the pendant to turn it on. It will enter pairing mode automatically.'**
  String get pairingDescFriendPendant;

  /// Pairing title for Fieldy device
  ///
  /// In en, this message translates to:
  /// **'Put Fieldy in Pairing Mode'**
  String get pairingTitleFieldy;

  /// Pairing description for Fieldy device
  ///
  /// In en, this message translates to:
  /// **'Press and hold the device until the light appears to turn it on.'**
  String get pairingDescFieldy;

  /// Pairing title for Apple Watch
  ///
  /// In en, this message translates to:
  /// **'Connect Apple Watch'**
  String get pairingTitleAppleWatch;

  /// Pairing description for Apple Watch
  ///
  /// In en, this message translates to:
  /// **'Install and open the Omi app on your Apple Watch, then tap Connect in the app.'**
  String get pairingDescAppleWatch;

  /// Pairing title for Neo One device
  ///
  /// In en, this message translates to:
  /// **'Put Neo One in Pairing Mode'**
  String get pairingTitleNeoOne;

  /// Pairing description for Neo One device
  ///
  /// In en, this message translates to:
  /// **'Press and hold the power button until the LED blinks. The device will be discoverable.'**
  String get pairingDescNeoOne;
}

class _AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) => <String>[
        'ar',
        'bg',
        'ca',
        'cs',
        'da',
        'de',
        'el',
        'en',
        'es',
        'et',
        'fi',
        'fr',
        'hi',
        'hu',
        'id',
        'it',
        'ja',
        'ko',
        'lt',
        'lv',
        'ms',
        'nl',
        'no',
        'pl',
        'pt',
        'ro',
        'ru',
        'sk',
        'sv',
        'th',
        'tr',
        'uk',
        'vi',
        'zh'
      ].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'ar':
      return AppLocalizationsAr();
    case 'bg':
      return AppLocalizationsBg();
    case 'ca':
      return AppLocalizationsCa();
    case 'cs':
      return AppLocalizationsCs();
    case 'da':
      return AppLocalizationsDa();
    case 'de':
      return AppLocalizationsDe();
    case 'el':
      return AppLocalizationsEl();
    case 'en':
      return AppLocalizationsEn();
    case 'es':
      return AppLocalizationsEs();
    case 'et':
      return AppLocalizationsEt();
    case 'fi':
      return AppLocalizationsFi();
    case 'fr':
      return AppLocalizationsFr();
    case 'hi':
      return AppLocalizationsHi();
    case 'hu':
      return AppLocalizationsHu();
    case 'id':
      return AppLocalizationsId();
    case 'it':
      return AppLocalizationsIt();
    case 'ja':
      return AppLocalizationsJa();
    case 'ko':
      return AppLocalizationsKo();
    case 'lt':
      return AppLocalizationsLt();
    case 'lv':
      return AppLocalizationsLv();
    case 'ms':
      return AppLocalizationsMs();
    case 'nl':
      return AppLocalizationsNl();
    case 'no':
      return AppLocalizationsNo();
    case 'pl':
      return AppLocalizationsPl();
    case 'pt':
      return AppLocalizationsPt();
    case 'ro':
      return AppLocalizationsRo();
    case 'ru':
      return AppLocalizationsRu();
    case 'sk':
      return AppLocalizationsSk();
    case 'sv':
      return AppLocalizationsSv();
    case 'th':
      return AppLocalizationsTh();
    case 'tr':
      return AppLocalizationsTr();
    case 'uk':
      return AppLocalizationsUk();
    case 'vi':
      return AppLocalizationsVi();
    case 'zh':
      return AppLocalizationsZh();
  }

  throw FlutterError('AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
