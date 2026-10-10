import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_ar.dart';
import 'app_localizations_be.dart';
import 'app_localizations_bg.dart';
import 'app_localizations_bn.dart';
import 'app_localizations_bs.dart';
import 'app_localizations_ca.dart';
import 'app_localizations_cs.dart';
import 'app_localizations_da.dart';
import 'app_localizations_de.dart';
import 'app_localizations_el.dart';
import 'app_localizations_en.dart';
import 'app_localizations_es.dart';
import 'app_localizations_et.dart';
import 'app_localizations_fa.dart';
import 'app_localizations_fi.dart';
import 'app_localizations_fr.dart';
import 'app_localizations_he.dart';
import 'app_localizations_hi.dart';
import 'app_localizations_hr.dart';
import 'app_localizations_hu.dart';
import 'app_localizations_id.dart';
import 'app_localizations_it.dart';
import 'app_localizations_ja.dart';
import 'app_localizations_kn.dart';
import 'app_localizations_ko.dart';
import 'app_localizations_lt.dart';
import 'app_localizations_lv.dart';
import 'app_localizations_mk.dart';
import 'app_localizations_mr.dart';
import 'app_localizations_ms.dart';
import 'app_localizations_nl.dart';
import 'app_localizations_no.dart';
import 'app_localizations_pl.dart';
import 'app_localizations_pt.dart';
import 'app_localizations_ro.dart';
import 'app_localizations_ru.dart';
import 'app_localizations_sk.dart';
import 'app_localizations_sl.dart';
import 'app_localizations_sr.dart';
import 'app_localizations_sv.dart';
import 'app_localizations_ta.dart';
import 'app_localizations_te.dart';
import 'app_localizations_th.dart';
import 'app_localizations_tl.dart';
import 'app_localizations_tr.dart';
import 'app_localizations_uk.dart';
import 'app_localizations_ur.dart';
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
    Locale('be'),
    Locale('bg'),
    Locale('bn'),
    Locale('bs'),
    Locale('ca'),
    Locale('cs'),
    Locale('da'),
    Locale('de'),
    Locale('el'),
    Locale('en'),
    Locale('es'),
    Locale('et'),
    Locale('fa'),
    Locale('fi'),
    Locale('fr'),
    Locale('he'),
    Locale('hi'),
    Locale('hr'),
    Locale('hu'),
    Locale('id'),
    Locale('it'),
    Locale('ja'),
    Locale('kn'),
    Locale('ko'),
    Locale('lt'),
    Locale('lv'),
    Locale('mk'),
    Locale('mr'),
    Locale('ms'),
    Locale('nl'),
    Locale('no'),
    Locale('pl'),
    Locale('pt'),
    Locale('ro'),
    Locale('ru'),
    Locale('sk'),
    Locale('sl'),
    Locale('sr'),
    Locale('sv'),
    Locale('ta'),
    Locale('te'),
    Locale('th'),
    Locale('tl'),
    Locale('tr'),
    Locale('uk'),
    Locale('ur'),
    Locale('vi'),
    Locale('zh')
  ];

  /// Description for empty state welcome
  ///
  /// In en, this message translates to:
  /// **'Your AI will automatically pull tasks out of your conversations. They\'ll appear here when created.'**
  String get welcomeActionItemsDescription;

  /// Generic retryable error
  ///
  /// In en, this message translates to:
  /// **'Something went wrong. Try again.'**
  String get chatAppsProblemFailed;

  /// Tutorial step 4 double-tap option title — star the ongoing conversation
  ///
  /// In en, this message translates to:
  /// **'Star Ongoing Conversation'**
  String get deviceOnboardingStarConversation;

  /// Menu option to delete all recordings
  ///
  /// In en, this message translates to:
  /// **'Delete All'**
  String get deleteAll;

  /// Option to copy summary to clipboard
  ///
  /// In en, this message translates to:
  /// **'Copy Summary'**
  String get copySummary;

  /// Description for location access permission
  ///
  /// In en, this message translates to:
  /// **'So Omi can note where your conversations happened.'**
  String get locationAccessDesc;

  /// Page title for firmware update screen
  ///
  /// In en, this message translates to:
  /// **'Firmware Update'**
  String get firmwareUpdate;

  /// No description provided for @chatMessages.
  ///
  /// In en, this message translates to:
  /// **'messages'**
  String get chatMessages;

  /// No description provided for @showEventsNoParticipants.
  ///
  /// In en, this message translates to:
  /// **'Show events with no participants'**
  String get showEventsNoParticipants;

  /// Share stats period: Year
  ///
  /// In en, this message translates to:
  /// **'This year, Omi has:'**
  String get sharePeriodYear;

  /// Generic error when starting a run fails. Keep 'Dream' untranslated.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t run Dream. Try again.'**
  String get dreamReportRunFailed;

  /// Label for accuracy metric of an on-device transcription model
  ///
  /// In en, this message translates to:
  /// **'Accuracy'**
  String get sttModelAccuracy;

  /// Section title in app submission: the permissions an app requests
  ///
  /// In en, this message translates to:
  /// **'Scopes'**
  String get scopes;

  /// Subtitle on delete-account flow feedback step
  ///
  /// In en, this message translates to:
  /// **'What would have made Omi work for you?'**
  String get deleteFlowFeedbackSubtitle;

  /// Title of the consent dialog before enabling an app that works outside Omi
  ///
  /// In en, this message translates to:
  /// **'Allow {appName} Access?'**
  String appDataAccessTitle(String appName);

  /// No description provided for @pendantStorageAlmostFull.
  ///
  /// In en, this message translates to:
  /// **'Pendant storage is almost full — keep the app open to sync.'**
  String get pendantStorageAlmostFull;

  /// No description provided for @deviceOnboardingAllSetDoublePressBadge.
  ///
  /// In en, this message translates to:
  /// **'2×'**
  String get deviceOnboardingAllSetDoublePressBadge;

  /// Button to copy error details
  ///
  /// In en, this message translates to:
  /// **'Copy Error Message'**
  String get copyErrorMessage;

  /// Section header
  ///
  /// In en, this message translates to:
  /// **'Filter Memories'**
  String get filterMemories;

  /// No description provided for @helpsDiagnoseIssuesAutoDeletes.
  ///
  /// In en, this message translates to:
  /// **'Helps diagnose issues. Auto-deletes after 3 days.'**
  String get helpsDiagnoseIssuesAutoDeletes;

  /// Instructions to enable location services
  ///
  /// In en, this message translates to:
  /// **'Location Services are off on this device. Turn them on in Settings.'**
  String get locationServiceDisabledDesc;

  /// Success banner title after linking; app is Telegram or iMessage
  ///
  /// In en, this message translates to:
  /// **'{app} is connected'**
  String chatAppsIsConnected(String app);

  /// Payment method name for Stripe
  ///
  /// In en, this message translates to:
  /// **'Stripe'**
  String get paymentMethodStripe;

  /// Delete reason option
  ///
  /// In en, this message translates to:
  /// **'Too many technical issues'**
  String get deleteReasonTechnicalIssues;

  /// Page title for payments settings
  ///
  /// In en, this message translates to:
  /// **'Payments'**
  String get payments;

  /// No description provided for @verifiedFallback.
  ///
  /// In en, this message translates to:
  /// **'Verified'**
  String get verifiedFallback;

  /// No description provided for @pleaseWait.
  ///
  /// In en, this message translates to:
  /// **'Please wait…'**
  String get pleaseWait;

  /// Label for app language selector
  ///
  /// In en, this message translates to:
  /// **'App Language'**
  String get appLanguage;

  /// Fallback name for unknown app
  ///
  /// In en, this message translates to:
  /// **'Unknown App'**
  String get unknownApp;

  /// Body of the dialog shown when re-enabling fails and the server gave no reason
  ///
  /// In en, this message translates to:
  /// **'This app could not be re-enabled. Please try again.'**
  String get appReEnableFailedBody;

  /// Generic error message shown in snackbar when an error occurs
  ///
  /// In en, this message translates to:
  /// **'Something went wrong! Please try again later.'**
  String get somethingWentWrongTryAgain;

  /// Label when upgrade is scheduled
  ///
  /// In en, this message translates to:
  /// **'Upgrade Scheduled'**
  String get upgradeScheduled;

  /// Section title in summary collage
  ///
  /// In en, this message translates to:
  /// **'BUDDIES'**
  String get wrappedBuddiesLabel;

  /// Button on a chat discovery card that expands it to its full text
  ///
  /// In en, this message translates to:
  /// **'Show More'**
  String get chatBlockShowMore;

  /// Success message after subscription checkout
  ///
  /// In en, this message translates to:
  /// **'Subscription successful! You\'ve been charged for the new billing period.'**
  String get subscriptionSuccessfulCharged;

  /// Title of the phone-call option in the record-options sheet
  ///
  /// In en, this message translates to:
  /// **'Phone Call'**
  String get phoneCall;

  /// Notice when a refresh failed but earlier data is still shown
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t refresh. Showing what we last saw.'**
  String get chatAppsRefreshFailed;

  /// Plan card row: this tier does not include the desktop app
  ///
  /// In en, this message translates to:
  /// **'Doesn\'t work on Desktop'**
  String get noDesktopAccess;

  /// Final confirmation title
  ///
  /// In en, this message translates to:
  /// **'Are you sure?'**
  String get areYouSure;

  /// Button to resubscribe
  ///
  /// In en, this message translates to:
  /// **'Resubscribe'**
  String get resubscribe;

  /// Screen-reader label for the voice match meter; level is Close match, Possible match or Weak match.
  ///
  /// In en, this message translates to:
  /// **'Voice match: {level}'**
  String voiceMatchMeterLabel(String level);

  /// Message during background sync
  ///
  /// In en, this message translates to:
  /// **'We\'ll keep syncing your recordings in the background.'**
  String get syncingBackground;

  /// Dialog title asking user to confirm sign out
  ///
  /// In en, this message translates to:
  /// **'Sign Out?'**
  String get signOutQuestion;

  /// Banner above a chat app transcript
  ///
  /// In en, this message translates to:
  /// **'Read-only. Reply to Omi in {app}.'**
  String chatAppsReadOnlyBanner(String app);

  /// Status when device is connected
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get connected;

  /// Share stats base message
  ///
  /// In en, this message translates to:
  /// **'Sharing my Omi stats! (omi.me - your always-on AI assistant)'**
  String get shareStatsMessage;

  /// Notification frequency level - minimal
  ///
  /// In en, this message translates to:
  /// **'Minimal'**
  String get frequencyMinimal;

  /// Validation error when no app logo is selected
  ///
  /// In en, this message translates to:
  /// **'Please select a logo for your app'**
  String get addAppSelectLogo;

  /// Link label for integration instructions
  ///
  /// In en, this message translates to:
  /// **'Integration Instructions'**
  String get integrationInstructions;

  /// Error showing accessibility permission status
  ///
  /// In en, this message translates to:
  /// **'Accessibility permission status: {status}. Please check System Preferences.'**
  String onboardingAccessibilityStatusCheckPrefs(String status);

  /// Label for completed tasks in Wrapped
  ///
  /// In en, this message translates to:
  /// **'completed'**
  String get wrappedCompleted;

  /// Label showing time remaining for SD card transfer
  ///
  /// In en, this message translates to:
  /// **'Remaining'**
  String get remaining;

  /// Message about computational intensity
  ///
  /// In en, this message translates to:
  /// **'On-Device transcription is computationally intensive.'**
  String get onDeviceIntensive;

  /// Device Diagnostics verdict when a connection attempt failed in the last 24 hours
  ///
  /// In en, this message translates to:
  /// **'Having trouble connecting'**
  String get diagnosticsVerdictTrouble;

  /// Voice preview output route when headphones are connected
  ///
  /// In en, this message translates to:
  /// **'Through {device}'**
  String deviceOnboardingVoiceReplyPreviewThroughDevice(String device);

  /// Button text to copy configuration
  ///
  /// In en, this message translates to:
  /// **'Copy Config'**
  String get copyConfig;

  /// Description showing what data types an app accesses, e.g. 'Accesses Conversations & Memories'
  ///
  /// In en, this message translates to:
  /// **'Accesses {dataTypes}'**
  String accessesDataTypes(String dataTypes);

  /// Confirmation after tapping Notify Me
  ///
  /// In en, this message translates to:
  /// **'Thanks. WhatsApp will show up here when it\'s ready.'**
  String get chatAppsWaitlistConfirmed;

  /// Undo button text
  ///
  /// In en, this message translates to:
  /// **'Undo'**
  String get undo;

  /// No description provided for @phoneContactsAccessTitle.
  ///
  /// In en, this message translates to:
  /// **'Allow Contacts Access'**
  String get phoneContactsAccessTitle;

  /// Shown in the confidence sheet for a Confirmed person instead of next steps.
  ///
  /// In en, this message translates to:
  /// **'{name} is Confirmed. There\'s nothing else you need to do.'**
  String confidenceIsConfirmed(String name);

  /// Label for movie obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'MOVIE'**
  String get wrappedMovie;

  /// Section title in summary collage (uppercase)
  ///
  /// In en, this message translates to:
  /// **'STRUGGLE'**
  String get wrappedStruggleLabelUpper;

  /// No description provided for @appleHealthFeatureChatDesc.
  ///
  /// In en, this message translates to:
  /// **'Ask Omi about your steps, sleep, heart rate, and workouts.'**
  String get appleHealthFeatureChatDesc;

  /// Hint text for review input field
  ///
  /// In en, this message translates to:
  /// **'Write a review (optional)'**
  String get writeReviewOptional;

  /// No description provided for @pairNewDevice.
  ///
  /// In en, this message translates to:
  /// **'Pair new device'**
  String get pairNewDevice;

  /// No description provided for @chatUsedOfLimitCompute.
  ///
  /// In en, this message translates to:
  /// **'\${used} of \${limit} compute budget used'**
  String chatUsedOfLimitCompute(String used, String limit);

  /// Section header for daily summary settings
  ///
  /// In en, this message translates to:
  /// **'Daily Summary'**
  String get dailySummary;

  /// No description provided for @pleaseEnterYourName.
  ///
  /// In en, this message translates to:
  /// **'Please enter your name'**
  String get pleaseEnterYourName;

  /// Button text to proceed without connecting a hardware device
  ///
  /// In en, this message translates to:
  /// **'Continue Without Device'**
  String get continueWithoutDevice;

  /// Button to configure settings
  ///
  /// In en, this message translates to:
  /// **'Configure'**
  String get configure;

  /// Button label to create a new app
  ///
  /// In en, this message translates to:
  /// **'Create App'**
  String get createApp;

  /// Error when URL format is invalid
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid URL'**
  String get invalidUrlError;

  /// No description provided for @appClosed.
  ///
  /// In en, this message translates to:
  /// **'App closed'**
  String get appClosed;

  /// Button that moves the user from a paid plan to the free tier
  ///
  /// In en, this message translates to:
  /// **'Downgrade to Freemium'**
  String get downgradeToFreemiumAction;

  /// Button that starts connecting Telegram instead
  ///
  /// In en, this message translates to:
  /// **'Use Telegram for Now'**
  String get chatAppsUseTelegramForNow;

  /// Badge text for best moments summary
  ///
  /// In en, this message translates to:
  /// **'Best Moments'**
  String get wrappedBestMomentsBadge;

  /// Section header for storage settings
  ///
  /// In en, this message translates to:
  /// **'Storage'**
  String get storageSection;

  /// Pause/Resume recording action
  ///
  /// In en, this message translates to:
  /// **'Pause/Resume Recording'**
  String get pauseResumeRecording;

  /// No description provided for @phoneUnmute.
  ///
  /// In en, this message translates to:
  /// **'Unmute'**
  String get phoneUnmute;

  /// Completion message when onboarding is finished
  ///
  /// In en, this message translates to:
  /// **'You\'re all set!'**
  String get youreAllSet;

  /// Message shown when migration finishes successfully
  ///
  /// In en, this message translates to:
  /// **'Migration complete!'**
  String get migrationComplete;

  /// Label for app cost input field
  ///
  /// In en, this message translates to:
  /// **'App Cost'**
  String get paymentAppCost;

  /// Onboarding tutorial final button label to complete the tutorial
  ///
  /// In en, this message translates to:
  /// **'Finish'**
  String get deviceOnboardingFinish;

  /// No description provided for @noVerifiedNumbers.
  ///
  /// In en, this message translates to:
  /// **'No verified numbers'**
  String get noVerifiedNumbers;

  /// Description for MCP Server feature
  ///
  /// In en, this message translates to:
  /// **'Connect AI assistants to your data'**
  String get connectAiAssistantsToData;

  /// Hint text showing example key name
  ///
  /// In en, this message translates to:
  /// **'e.g., Claude Desktop'**
  String get keyNameHint;

  /// Payment methods setting
  ///
  /// In en, this message translates to:
  /// **'Payment Methods'**
  String get paymentMethods;

  /// Error when checking accessibility permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Accessibility permission: {error}'**
  String onboardingFailedCheckAccessibility(String error);

  /// Reason line under a person's name: Omi matched this voice automatically but the user never confirmed it.
  ///
  /// In en, this message translates to:
  /// **'Labeled automatically, not confirmed yet'**
  String get confidenceReasonAutoOnly;

  /// Title for changelog with version number
  ///
  /// In en, this message translates to:
  /// **'What\'s New in {version}'**
  String whatsNewInVersion(String version);

  /// Placeholder for selected language name
  ///
  /// In en, this message translates to:
  /// **'Select your language'**
  String get selectYourLanguage;

  /// Snackbar success message
  ///
  /// In en, this message translates to:
  /// **'Omi\'s memory about you has been cleared'**
  String get memoryClearedSuccess;

  /// Example of a useful personal preference to remember.
  ///
  /// In en, this message translates to:
  /// **'I prefer morning meetings.'**
  String get memoryContentHint;

  /// Title of the dogfood screen showing what the background 'Dream' agent looked at and proposed. 'Dream' is a product name; keep it untranslated.
  ///
  /// In en, this message translates to:
  /// **'Dream Report'**
  String get dreamReportTitle;

  /// Generic error message with error details
  ///
  /// In en, this message translates to:
  /// **'Error: {error}'**
  String importErrorGeneric(String error);

  /// Label for completion percentage
  ///
  /// In en, this message translates to:
  /// **'Completion Rate'**
  String get completionRate;

  /// No description provided for @trackPersonalGoals.
  ///
  /// In en, this message translates to:
  /// **'Track personal goals on homepage'**
  String get trackPersonalGoals;

  /// Button text to retry generating wrapped
  ///
  /// In en, this message translates to:
  /// **'Try Again'**
  String get wrappedTryAgain;

  /// Section title for data protection info
  ///
  /// In en, this message translates to:
  /// **'Data Protection'**
  String get dataProtection;

  /// Title for the conversations page
  ///
  /// In en, this message translates to:
  /// **'Your Conversations'**
  String get yourConversations;

  /// Label showing the conversation title in PDF export
  ///
  /// In en, this message translates to:
  /// **'Title: {title}'**
  String pdfTitleLabel(String title);

  /// Explains that disabling raw audio forwarding preserves transcript-based cloud features
  ///
  /// In en, this message translates to:
  /// **'Turn off to prevent raw audio from being sent to Omi. Transcripts and data needed by cloud features may still be sent to Omi.'**
  String get sendRawAudioToOmiDescription;

  /// Error state
  ///
  /// In en, this message translates to:
  /// **'Couldn’t load this page.'**
  String get entityLoadFailed;

  /// No description provided for @networkNameSsid.
  ///
  /// In en, this message translates to:
  /// **'Network Name (SSID)'**
  String get networkNameSsid;

  /// Eyebrow label of a chat card that shows something Omi discovered
  ///
  /// In en, this message translates to:
  /// **'Discovery'**
  String get discovery;

  /// Error shown when the selected Bluetooth HFP microphone cannot connect
  ///
  /// In en, this message translates to:
  /// **'Could not connect to that microphone. Make sure it is connected in iPhone Settings.'**
  String get rayBanMetaMicPickerConnectError;

  /// No description provided for @fairUseAboutTitle.
  ///
  /// In en, this message translates to:
  /// **'About Fair Use'**
  String get fairUseAboutTitle;

  /// Badge for top categories in Wrapped
  ///
  /// In en, this message translates to:
  /// **'You Talked About'**
  String get wrappedYouTalkedAbout;

  /// Free-plan limitation: lower transcription quality
  ///
  /// In en, this message translates to:
  /// **'30% less transcription quality'**
  String get downgradeLimitQuality;

  /// Sender name when a shared-tasks link has no sender name
  ///
  /// In en, this message translates to:
  /// **'Someone'**
  String get sharedTasksUnknownSender;

  /// Label above the reasons in the chat feedback sheet
  ///
  /// In en, this message translates to:
  /// **'Select a reason'**
  String get selectAReason;

  /// Uppercase label for win tile in collage
  ///
  /// In en, this message translates to:
  /// **'WIN'**
  String get wrappedWinLabel;

  /// No description provided for @configuration.
  ///
  /// In en, this message translates to:
  /// **'Configuration'**
  String get configuration;

  /// Label when no folder is assigned
  ///
  /// In en, this message translates to:
  /// **'No Folder'**
  String get noFolder;

  /// Success toast after manually refreshing an MCP app's manifest
  ///
  /// In en, this message translates to:
  /// **'Manifest refreshed successfully'**
  String get manifestRefreshedSuccess;

  /// Status label when payment method is active
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get paymentStatusActive;

  /// No description provided for @linkKeyMismatch.
  ///
  /// In en, this message translates to:
  /// **'Link key mismatch'**
  String get linkKeyMismatch;

  /// Progress indicator, e.g. 2 of 4
  ///
  /// In en, this message translates to:
  /// **'{current} of {total}'**
  String speakerTagPromptProgress(int current, int total);

  /// Message of the pop-up when this app version is no longer supported and must be updated
  ///
  /// In en, this message translates to:
  /// **'This version of Omi is no longer supported. Update to keep recording and syncing.'**
  String get updateRequiredMessage;

  /// Share stats period: Month
  ///
  /// In en, this message translates to:
  /// **'This month, Omi has:'**
  String get sharePeriodMonth;

  /// Action item title for rolling back to the latest stable firmware version
  ///
  /// In en, this message translates to:
  /// **'Roll Back to Stable Firmware'**
  String get rollbackToStableFirmware;

  /// Status label when payment method is connected but not active
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get paymentStatusConnected;

  /// Title of the find-device screen after a scan ended with nothing found (Title Case).
  ///
  /// In en, this message translates to:
  /// **'No Omi Found'**
  String get findDeviceNoneTitle;

  /// Success message when app ID is copied
  ///
  /// In en, this message translates to:
  /// **'App ID copied to clipboard'**
  String get appIdCopiedToClipboard;

  /// Text before Terms & Privacy Policy link
  ///
  /// In en, this message translates to:
  /// **'By submitting, you agree to Omi '**
  String get bySubmittingYouAgreeToOmi;

  /// Rating filter dropdown label
  ///
  /// In en, this message translates to:
  /// **'Rating'**
  String get filterRating;

  /// Usage location option: At work
  ///
  /// In en, this message translates to:
  /// **'At work'**
  String get usageAtWork;

  /// Confirmation dialog message for cleaning today task deadlines
  ///
  /// In en, this message translates to:
  /// **'This will only remove deadlines'**
  String get tasksCleanTodayMessage;

  /// Subtitle of the Ignored Voices row.
  ///
  /// In en, this message translates to:
  /// **'TV, podcasts and other voices you marked Not a Person'**
  String get ignoredVoicesSubtitle;

  /// Action text to enable a permission
  ///
  /// In en, this message translates to:
  /// **'Enable'**
  String get permissionEnable;

  /// No description provided for @integrationComingSoon.
  ///
  /// In en, this message translates to:
  /// **'{appName} isn\'t supported yet.'**
  String integrationComingSoon(String appName);

  /// Relative quality/accuracy indicator: lower
  ///
  /// In en, this message translates to:
  /// **'Lower'**
  String get sttModelLower;

  /// Loading state message
  ///
  /// In en, this message translates to:
  /// **'Loading your memories…'**
  String get loadingYourMemories;

  /// Experimental feature name
  ///
  /// In en, this message translates to:
  /// **'Follow-up Questions'**
  String get followUpQuestions;

  /// Day page navigation: go to the day before
  ///
  /// In en, this message translates to:
  /// **'Previous day'**
  String get previousDay;

  /// Snackbar message when case reference is copied to clipboard
  ///
  /// In en, this message translates to:
  /// **'{caseRef} copied'**
  String fairUseCaseRefCopied(String caseRef);

  /// Claude Desktop integration section
  ///
  /// In en, this message translates to:
  /// **'Claude Desktop'**
  String get claudeDesktop;

  /// Status when recording is paused
  ///
  /// In en, this message translates to:
  /// **'Recording Paused'**
  String get recordingPaused;

  /// Error when trying to report own message
  ///
  /// In en, this message translates to:
  /// **'You cannot report your own messages'**
  String get cannotReportOwnMessages;

  /// Text field hint for vocabulary input
  ///
  /// In en, this message translates to:
  /// **'Enter words (comma separated)'**
  String get enterWordsHint;

  /// No description provided for @audioDownloadFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to download audio'**
  String get audioDownloadFailed;

  /// Dialog content for clearing memory
  ///
  /// In en, this message translates to:
  /// **'All your memories are deleted. This can\'t be undone.'**
  String get clearMemoryMessage;

  /// Hint text for template name field
  ///
  /// In en, this message translates to:
  /// **'e.g., Meeting Task Extractor'**
  String get templateNameHint;

  /// How long an unnamed voice spoke in an earlier conversation; duration is already formatted (14m)
  ///
  /// In en, this message translates to:
  /// **'{duration} of this voice'**
  String speakerLabelTalkTime(String duration);

  /// Title of the bottom sheet for choosing between Live and Transcribe Later recording modes
  ///
  /// In en, this message translates to:
  /// **'Recording mode'**
  String get recordingMode;

  /// Cancel reason option
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get cancelReasonOther;

  /// Relative quality/accuracy indicator: higher
  ///
  /// In en, this message translates to:
  /// **'Higher'**
  String get sttModelHigher;

  /// Status when setting up audio capture
  ///
  /// In en, this message translates to:
  /// **'Setting up system audio capture'**
  String get settingUpSystemAudioCapture;

  /// Count of memories in category
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{0 memories} =1{1 memory} other{{count} memories}}'**
  String memoriesCount(int count);

  /// Message shown when app has no specific data access
  ///
  /// In en, this message translates to:
  /// **'No specific data access configured.'**
  String get noSpecificDataAccessConfigured;

  /// Label for recording ID in details
  ///
  /// In en, this message translates to:
  /// **'Recording ID'**
  String get recordingIdLabel;

  /// Daily summary detail - highlights
  ///
  /// In en, this message translates to:
  /// **'Highlights'**
  String get highlights;

  /// No description provided for @phoneTryAgain.
  ///
  /// In en, this message translates to:
  /// **'Try Again'**
  String get phoneTryAgain;

  /// Error when a chat app could not be opened
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t open {app}. Make sure it\'s installed and try again.'**
  String chatAppsCouldNotOpen(String app);

  /// Description of on-device transcription behavior
  ///
  /// In en, this message translates to:
  /// **'Transcription is processed locally on your device'**
  String get onDeviceTranscriptionDesc;

  /// Example question to send Omi; Sam is a person's name
  ///
  /// In en, this message translates to:
  /// **'What did I promise Sam yesterday?'**
  String get chatAppsTryPromise;

  /// Status label when payment method is not connected
  ///
  /// In en, this message translates to:
  /// **'Not Connected'**
  String get paymentStatusNotConnected;

  /// Label for interval input in seconds
  ///
  /// In en, this message translates to:
  /// **'Interval (seconds)'**
  String get intervalSeconds;

  /// No description provided for @authorize.
  ///
  /// In en, this message translates to:
  /// **'Authorize'**
  String get authorize;

  /// Settings navigation header
  ///
  /// In en, this message translates to:
  /// **'SETTINGS'**
  String get settingsHeader;

  /// No description provided for @personNameAlreadyExists.
  ///
  /// In en, this message translates to:
  /// **'A person with this name already exists.'**
  String get personNameAlreadyExists;

  /// Voice preview output route while the system route is not yet known
  ///
  /// In en, this message translates to:
  /// **'Through the current audio output'**
  String get deviceOnboardingVoiceReplyPreviewThroughCurrentOutput;

  /// June month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Jun'**
  String get monthJun;

  /// Selection count label
  ///
  /// In en, this message translates to:
  /// **'{count} selected'**
  String selectedCount(int count);

  /// No description provided for @batteryHistory.
  ///
  /// In en, this message translates to:
  /// **'Battery'**
  String get batteryHistory;

  /// Ask: Past chats when there are none
  ///
  /// In en, this message translates to:
  /// **'Your chats with Omi show up here.'**
  String get noPastChats;

  /// Capability bullet
  ///
  /// In en, this message translates to:
  /// **'Saves memories and manages your tasks'**
  String get chatAppsDoesSave;

  /// Label for API key (used for clipboard notification)
  ///
  /// In en, this message translates to:
  /// **'API key'**
  String get apiKey;

  /// Error message when linking Google account fails
  ///
  /// In en, this message translates to:
  /// **'Failed to link with Google, please try again.'**
  String get authFailedToLinkGoogle;

  /// Live-capture WAL indicator when the recording can no longer be uploaded (corrupted or past the recovery window)
  ///
  /// In en, this message translates to:
  /// **'Upload failed — {duration} of audio kept on your phone.'**
  String audioUploadFailedKeptLocal(String duration);

  /// No description provided for @free.
  ///
  /// In en, this message translates to:
  /// **'Free'**
  String get free;

  /// Action menu entry that clears any current task selection while staying in selection mode
  ///
  /// In en, this message translates to:
  /// **'Deselect All'**
  String get deselectAllTasksMenu;

  /// Error state when the report cannot be loaded.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load the Dream report.'**
  String get dreamReportLoadFailed;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'Recent conversations'**
  String get entityRecentConversations;

  /// No description provided for @pendantRecordingNote.
  ///
  /// In en, this message translates to:
  /// **'Your pendant is recording on its own. Recordings sync to your phone while the app is open.'**
  String get pendantRecordingNote;

  /// Menu option and sheet title for managing recording storage
  ///
  /// In en, this message translates to:
  /// **'Manage Storage'**
  String get manageStorage;

  /// Filter option for facts about the user
  ///
  /// In en, this message translates to:
  /// **'About You'**
  String get filterSystem;

  /// Delete consequence bullet
  ///
  /// In en, this message translates to:
  /// **'Any active subscription will be cancelled.'**
  String get deleteConsequenceSubscription;

  /// No description provided for @defaultList.
  ///
  /// In en, this message translates to:
  /// **'Default List'**
  String get defaultList;

  /// No description provided for @shared.
  ///
  /// In en, this message translates to:
  /// **'Shared'**
  String get shared;

  /// Custom vocabulary section
  ///
  /// In en, this message translates to:
  /// **'Custom Vocabulary'**
  String get customVocabulary;

  /// Feedback title when cancel reason is audio quality
  ///
  /// In en, this message translates to:
  /// **'What issues did you experience?'**
  String get feedbackTitleAudioQuality;

  /// Warning message in delete confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'This can\'t be undone.'**
  String get thisActionCannotBeUndone;

  /// Error message for permission request failure
  ///
  /// In en, this message translates to:
  /// **'Error requesting permission: {error}'**
  String errorRequestingPermission(String error);

  /// No description provided for @recapRegenerateFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t regenerate the recap. Try again later.'**
  String get recapRegenerateFailed;

  /// Label for result output
  ///
  /// In en, this message translates to:
  /// **'Result:'**
  String get result;

  /// No description provided for @statusCallMissed.
  ///
  /// In en, this message translates to:
  /// **'Call missed'**
  String get statusCallMissed;

  /// Device Diagnostics row title: the longest time the device took to reconnect
  ///
  /// In en, this message translates to:
  /// **'Longest gap'**
  String get diagnosticsLongestGap;

  /// Message when no debug log files exist
  ///
  /// In en, this message translates to:
  /// **'No log files found.'**
  String get noLogFilesFound;

  /// Section title for speech and transcription language settings
  ///
  /// In en, this message translates to:
  /// **'Speech & Transcription'**
  String get speechTranscriptionSectionTitle;

  /// Button text to start syncing recordings immediately
  ///
  /// In en, this message translates to:
  /// **'Sync Now'**
  String get syncNow;

  /// Button: drop the Custom STT language override
  ///
  /// In en, this message translates to:
  /// **'Use Primary Language'**
  String get sttUsePrimaryLanguage;

  /// Error when the file picked for an import has an extension the importer does not accept
  ///
  /// In en, this message translates to:
  /// **'This file type can\'t be imported.'**
  String get importUnsupportedFileType;

  /// Screen-reader label and tooltip of the chat Send button
  ///
  /// In en, this message translates to:
  /// **'Send message'**
  String get chatSendMessage;

  /// No description provided for @syncCardAllBackedUp.
  ///
  /// In en, this message translates to:
  /// **'All recordings synced'**
  String get syncCardAllBackedUp;

  /// Settings dialog title
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settings;

  /// Instructions to grant background location permission
  ///
  /// In en, this message translates to:
  /// **'Please go to device settings and set location permission to \"Always Allow\"'**
  String get backgroundLocationDeniedDesc;

  /// Description of on-device transcription resource usage
  ///
  /// In en, this message translates to:
  /// **'On-Device transcription is computationally intensive.'**
  String get computationallyIntensive;

  /// Conjunction between terms and privacy
  ///
  /// In en, this message translates to:
  /// **' and '**
  String get and;

  /// No description provided for @yourVerifiedNumbers.
  ///
  /// In en, this message translates to:
  /// **'Your Verified Numbers'**
  String get yourVerifiedNumbers;

  /// Confirmation dialog title for cleaning today task deadlines
  ///
  /// In en, this message translates to:
  /// **'Clean today\'s tasks?'**
  String get tasksCleanTodayTitle;

  /// Title for microphone permission section
  ///
  /// In en, this message translates to:
  /// **'Microphone Permission'**
  String get microphonePermission;

  /// No description provided for @failedToUpdateConversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Failed to update conversation title'**
  String get failedToUpdateConversationTitle;

  /// Delete account warning 2
  ///
  /// In en, this message translates to:
  /// **'Your apps and integrations will be disconnected.'**
  String get appsDisconnected;

  /// No description provided for @live.
  ///
  /// In en, this message translates to:
  /// **'Live'**
  String get live;

  /// No description provided for @connectionFailed.
  ///
  /// In en, this message translates to:
  /// **'Connection failed'**
  String get connectionFailed;

  /// File option: select images
  ///
  /// In en, this message translates to:
  /// **'Select Images'**
  String get selectImages;

  /// Inline label when fetching the audio URLs fails on transport
  ///
  /// In en, this message translates to:
  /// **'Check Connection'**
  String get playbackAudioNetworkFailed;

  /// Label for PayPal email field
  ///
  /// In en, this message translates to:
  /// **'PayPal Email'**
  String get paypalEmail;

  /// Chip/button after the person asked to be notified about WhatsApp
  ///
  /// In en, this message translates to:
  /// **'On the List'**
  String get chatAppsOnTheList;

  /// Menu item to generate a summary
  ///
  /// In en, this message translates to:
  /// **'Generate Summary'**
  String get generateSummary;

  /// No description provided for @categoryHealth.
  ///
  /// In en, this message translates to:
  /// **'Health'**
  String get categoryHealth;

  /// Warning shown when storage is too low to keep recording in Transcribe Later mode
  ///
  /// In en, this message translates to:
  /// **'Your phone is low on storage, so recording is paused. Free up space or upload your recordings, then it will resume automatically.'**
  String get transcribeLaterStorageFull;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No chats yet'**
  String get chatAppsNoChatsTitle;

  /// Onboarding setup checklist step
  ///
  /// In en, this message translates to:
  /// **'Personalizing your experience'**
  String get onboardingSetupStepPersonalize;

  /// No description provided for @leaveUnselectedTasks.
  ///
  /// In en, this message translates to:
  /// **'Leave unselected to create tasks without a project'**
  String get leaveUnselectedTasks;

  /// Subtitle on struggle card with emoji
  ///
  /// In en, this message translates to:
  /// **'But you pushed through 💪'**
  String get wrappedButYouPushedThroughEmoji;

  /// Link to help dialog
  ///
  /// In en, this message translates to:
  /// **'Need Help?'**
  String get needHelp;

  /// Confirm cancellation button text
  ///
  /// In en, this message translates to:
  /// **'Confirm & Cancel'**
  String get confirmAndCancel;

  /// Description for high notification frequency
  ///
  /// In en, this message translates to:
  /// **'More suggestions, about 6–9 a day'**
  String get frequencyDescHigh;

  /// Button label to copy conversation link
  ///
  /// In en, this message translates to:
  /// **'Copy link'**
  String get copyLink;

  /// Banner when the agent applies edits. 'Recent Changes' is the name of another screen.
  ///
  /// In en, this message translates to:
  /// **'Dream applies these changes on its own. Undo any of them in Recent Changes.'**
  String get dreamReportLiveBanner;

  /// Placeholder text for action item description field
  ///
  /// In en, this message translates to:
  /// **'Enter task description'**
  String get enterActionItemDescription;

  /// Settings section header; app is Telegram or iMessage
  ///
  /// In en, this message translates to:
  /// **'In {app}'**
  String chatAppsInChannel(String app);

  /// No description provided for @links.
  ///
  /// In en, this message translates to:
  /// **'Links'**
  String get links;

  /// Empty state title when the agent has not run yet.
  ///
  /// In en, this message translates to:
  /// **'No passes yet'**
  String get dreamReportEmptyTitle;

  /// January month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Jan'**
  String get monthJan;

  /// Label for the most productive day
  ///
  /// In en, this message translates to:
  /// **'Most Productive'**
  String get wrappedMostProductiveDay;

  /// Menu item for product/firmware update
  ///
  /// In en, this message translates to:
  /// **'Product Update'**
  String get productUpdate;

  /// Dialog title for adding review
  ///
  /// In en, this message translates to:
  /// **'Add Your Review'**
  String get addYourReview;

  /// No description provided for @raybanMetaImageCaptureReady.
  ///
  /// In en, this message translates to:
  /// **'Image capture ready'**
  String get raybanMetaImageCaptureReady;

  /// No description provided for @displayUpcomingMeetingsDescription.
  ///
  /// In en, this message translates to:
  /// **'Display upcoming meetings in the menu bar'**
  String get displayUpcomingMeetingsDescription;

  /// Section title in consent dialog
  ///
  /// In en, this message translates to:
  /// **'What we collect'**
  String get whatWeCollect;

  /// Description when connecting PayPal account
  ///
  /// In en, this message translates to:
  /// **'Connect your PayPal account to start receiving payments for your apps'**
  String get connectPayPalToReceivePayments;

  /// Title for cancel consequences page
  ///
  /// In en, this message translates to:
  /// **'Just a moment, please'**
  String get justAMoment;

  /// Shown when a chat reply fails with a server error
  ///
  /// In en, this message translates to:
  /// **'Something went wrong on our side. Please try again.'**
  String get chatReplyServerError;

  /// Menu item text when transfer is ongoing
  ///
  /// In en, this message translates to:
  /// **'Transfer in progress…'**
  String get transferInProgress;

  /// Plan and Usage period selector
  ///
  /// In en, this message translates to:
  /// **'All time'**
  String get usageAll;

  /// Error message when contacts fail to load
  ///
  /// In en, this message translates to:
  /// **'Failed to load contacts'**
  String get failedToLoadContacts;

  /// Rounded number of people using an app, under its name on the app page
  ///
  /// In en, this message translates to:
  /// **'{count}+ users'**
  String appUsersCount(int count);

  /// Button to report message
  ///
  /// In en, this message translates to:
  /// **'Report'**
  String get report;

  /// Label for language selector
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get languageLabel;

  /// No description provided for @verifiedOnDate.
  ///
  /// In en, this message translates to:
  /// **'Verified on {date}'**
  String verifiedOnDate(String date);

  /// Custom vocabulary section header
  ///
  /// In en, this message translates to:
  /// **'CUSTOM VOCABULARY'**
  String get customVocabularyHeader;

  /// OmiGlass OTA installed, device rebooting
  ///
  /// In en, this message translates to:
  /// **'{deviceName} is restarting with the new firmware.'**
  String otaRebooting(String deviceName);

  /// MCP Server section header
  ///
  /// In en, this message translates to:
  /// **'MCP Server'**
  String get mcpServer;

  /// Action that makes a nearby connected Omi pendant vibrate so the user can locate it
  ///
  /// In en, this message translates to:
  /// **'Find'**
  String get findDevice;

  /// Error when attached file upload fails
  ///
  /// In en, this message translates to:
  /// **'Failed to upload the attached file.'**
  String get msgUploadAttachedFileFailed;

  /// No description provided for @appName.
  ///
  /// In en, this message translates to:
  /// **'App Name'**
  String get appName;

  /// Pairing title for Plaud Note
  ///
  /// In en, this message translates to:
  /// **'Put Plaud Note in Pairing Mode'**
  String get pairingTitlePlaudNote;

  /// Accessible name for the conversation-detail overflow menu
  ///
  /// In en, this message translates to:
  /// **'More options'**
  String get moreOptions;

  /// Empty state message on the Conversations tab for a new user
  ///
  /// In en, this message translates to:
  /// **'Conversations you record show up here. Tap the record button on Home to record your first one.'**
  String get noConversationsHeroMessage;

  /// Button that ends the live recording and processes the conversation.
  ///
  /// In en, this message translates to:
  /// **'Finish'**
  String get finish;

  /// Go back button
  ///
  /// In en, this message translates to:
  /// **'Go Back'**
  String get goBack;

  /// Description of what API keys are used for
  ///
  /// In en, this message translates to:
  /// **'API Keys are used for authentication when your app communicates with the Omi server. They allow your application to create memories and access other Omi services securely.'**
  String get apiKeysDescription;

  /// Brand name for the Speechmatics speech-to-text provider
  ///
  /// In en, this message translates to:
  /// **'Speechmatics'**
  String get sttProviderSpeechmatics;

  /// Dialog message prompting to set webhook URL
  ///
  /// In en, this message translates to:
  /// **'Please set the webhook URL in developer settings to use this feature.'**
  String get setWebhookUrlInSettings;

  /// Title for score breakdown modal
  ///
  /// In en, this message translates to:
  /// **'Daily Score Breakdown'**
  String get dailyScoreBreakdown;

  /// No description provided for @showMeetingsMenuBarDesc.
  ///
  /// In en, this message translates to:
  /// **'Display your next meeting and time until it starts in the macOS menu bar'**
  String get showMeetingsMenuBarDesc;

  /// No description provided for @tapToTrackThisGoal.
  ///
  /// In en, this message translates to:
  /// **'Tap to track this goal'**
  String get tapToTrackThisGoal;

  /// Loading text while summarizing a conversation
  ///
  /// In en, this message translates to:
  /// **'Summarizing conversation…\nThis may take a few seconds'**
  String get summarizingConversation;

  /// Error message shown when there is no internet connection
  ///
  /// In en, this message translates to:
  /// **'No internet connection'**
  String get noInternetConnection;

  /// Lifetime counter shown as secondary context under a 7-day window value
  ///
  /// In en, this message translates to:
  /// **'{count} since pairing'**
  String diagnosticsCountSincePairing(int count);

  /// Label for tasks created in Wrapped
  ///
  /// In en, this message translates to:
  /// **'tasks created'**
  String get wrappedTasksCreated;

  /// Delete consequence bullet
  ///
  /// In en, this message translates to:
  /// **'Your account cannot be restored — not even by support.'**
  String get deleteConsequenceNoRecovery;

  /// Toast when the reader tries to edit the transcript or a speaker while the conversation is being reprocessed.
  ///
  /// In en, this message translates to:
  /// **'Wait for reprocessing to finish.'**
  String get waitForReprocessing;

  /// No description provided for @needYourPermission.
  ///
  /// In en, this message translates to:
  /// **'We need your permission'**
  String get needYourPermission;

  /// Free-plan limitation: speaker identification disabled
  ///
  /// In en, this message translates to:
  /// **'Cannot identify speakers'**
  String get downgradeLimitSpeakers;

  /// Chat greeting: number of non-discarded conversations created today.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{No conversations today.} =1{1 conversation today.} other{{count} conversations today.}}'**
  String conversationsTodayCount(int count);

  /// Header for daily score widget
  ///
  /// In en, this message translates to:
  /// **'DAILY SCORE'**
  String get dailyScore;

  /// No description provided for @reportAnIssue.
  ///
  /// In en, this message translates to:
  /// **'Report an Issue'**
  String get reportAnIssue;

  /// Error message when invalid key is pressed for shortcut
  ///
  /// In en, this message translates to:
  /// **'Invalid key'**
  String get invalidKey;

  /// Section title for app preview images
  ///
  /// In en, this message translates to:
  /// **'Preview'**
  String get preview;

  /// Task due-date shortcut: seven days from today.
  ///
  /// In en, this message translates to:
  /// **'Next week'**
  String get nextWeek;

  /// Confidence level for a person's voice: nothing the user did backs it up yet. Short label.
  ///
  /// In en, this message translates to:
  /// **'Unverified'**
  String get confidenceUnverified;

  /// Section title for preview screenshots
  ///
  /// In en, this message translates to:
  /// **'Preview Screenshots'**
  String get previewScreenshots;

  /// LED brightness setting
  ///
  /// In en, this message translates to:
  /// **'LED Brightness'**
  String get ledBrightness;

  /// Firmware update failed while installing
  ///
  /// In en, this message translates to:
  /// **'The update didn\'t finish. Your device is still on its current firmware and safe to use. Keep it charged and close to your phone, then try again.'**
  String get firmwareUpdateFailedMessage;

  /// No description provided for @loadingProfile.
  ///
  /// In en, this message translates to:
  /// **'Loading profile…'**
  String get loadingProfile;

  /// Title of the confirm dialog when deleting a daily recap.
  ///
  /// In en, this message translates to:
  /// **'Delete this recap?'**
  String get deleteRecapConfirmTitle;

  /// Section header for notification frequency settings
  ///
  /// In en, this message translates to:
  /// **'Notification Frequency'**
  String get notificationFrequency;

  /// No description provided for @captureSystemAudioFromMeetings.
  ///
  /// In en, this message translates to:
  /// **'Capture system audio from meetings'**
  String get captureSystemAudioFromMeetings;

  /// storeAudioCloudDescription label
  ///
  /// In en, this message translates to:
  /// **'Uploads your recordings as you speak so you can play them back later.'**
  String get storeAudioCloudDescription;

  /// No description provided for @color.
  ///
  /// In en, this message translates to:
  /// **'Color'**
  String get color;

  /// Button label to open an installed app
  ///
  /// In en, this message translates to:
  /// **'Open'**
  String get open;

  /// Device Diagnostics verdict detail when nothing disconnected in the window
  ///
  /// In en, this message translates to:
  /// **'No drops this week'**
  String get diagnosticsVerdictNoDrops;

  /// Feature point description
  ///
  /// In en, this message translates to:
  /// **'Automatically extracted from conversations'**
  String get autoExtractionFeature;

  /// Badge label for search results section
  ///
  /// In en, this message translates to:
  /// **'Search results'**
  String get searchResults;

  /// Dialog message when the connected device has no SD-card offline sync
  ///
  /// In en, this message translates to:
  /// **'Offline Sync needs a connected Omi device with SD-card storage. Your current device doesn\'t support it.'**
  String get v2UndetectedMessage;

  /// End and process action
  ///
  /// In en, this message translates to:
  /// **'End & Process Conversation'**
  String get endAndProcess;

  /// Empty state for synced recordings list
  ///
  /// In en, this message translates to:
  /// **'No synced recordings yet'**
  String get noSyncedRecordings;

  /// No description provided for @coworker.
  ///
  /// In en, this message translates to:
  /// **'Coworker'**
  String get coworker;

  /// Question about Omi usage location
  ///
  /// In en, this message translates to:
  /// **'2. Where do you plan to use your Omi?'**
  String get setupQuestionUsage;

  /// Screen-reader label for a pinned person's row in select mode.
  ///
  /// In en, this message translates to:
  /// **'Pinned, not selectable'**
  String get pinnedNotSelectable;

  /// Text shown to expand collapsed content, with down arrow
  ///
  /// In en, this message translates to:
  /// **'show more ↓'**
  String get showMore;

  /// Empty state message when no memories
  ///
  /// In en, this message translates to:
  /// **'Create your first memory to get started'**
  String get createYourFirstMemory;

  /// Label for a discarded conversation
  ///
  /// In en, this message translates to:
  /// **'Discarded Conversation'**
  String get discardedConversation;

  /// Menu item text to navigate to apps page and enable more chat apps
  ///
  /// In en, this message translates to:
  /// **'Enable Apps'**
  String get enableApps;

  /// Label for today date
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get today;

  /// No description provided for @showEventsNoParticipantsDesc.
  ///
  /// In en, this message translates to:
  /// **'When enabled, Coming Up shows events without participants or a video link.'**
  String get showEventsNoParticipantsDesc;

  /// Error shown in an in-app web page (referral, app home) that failed to load
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load this page. Check your connection and try again.'**
  String get couldNotLoadPage;

  /// Snackbar message after deleting single item
  ///
  /// In en, this message translates to:
  /// **'Task \"{description}\" deleted'**
  String actionItemDeletedResult(String description);

  /// Dialog title for deleting a speech sample
  ///
  /// In en, this message translates to:
  /// **'Delete Sample?'**
  String get deleteSampleQuestion;

  /// Subtitle for paid plan users on plans sheet
  ///
  /// In en, this message translates to:
  /// **'You are on a paid plan.'**
  String get youAreOnAPaidPlan;

  /// OmiGlass OTA status
  ///
  /// In en, this message translates to:
  /// **'Installation failed. Your device is still on its current firmware.'**
  String get otaInstallFailed;

  /// Button to add first memory
  ///
  /// In en, this message translates to:
  /// **'Add Your First Memory'**
  String get addFirstMemory;

  /// Success message when an app is deleted
  ///
  /// In en, this message translates to:
  /// **'App deleted successfully'**
  String get appDeletedSuccessfully;

  /// Description on the Telegram connect sheet
  ///
  /// In en, this message translates to:
  /// **'Omi will open Telegram with a private link that\'s only for you.'**
  String get chatAppsConnectTelegramMessage;

  /// No description provided for @phoneSetupStep1Title.
  ///
  /// In en, this message translates to:
  /// **'Verify your phone number'**
  String get phoneSetupStep1Title;

  /// Message about device requirements
  ///
  /// In en, this message translates to:
  /// **'Your device does not meet the requirements for On-Device transcription.'**
  String get deviceRequirements;

  /// Section header in the confidence sheet listing what Omi's confidence is based on (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Evidence'**
  String get confidenceEvidenceHeader;

  /// Validation error when name is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter a name.'**
  String get pleaseEnterAName;

  /// The literal word users type to confirm deletion. Keep uppercase.
  ///
  /// In en, this message translates to:
  /// **'DELETE'**
  String get deleteConfirmationWord;

  /// Answer button: the clip is the user's own voice
  ///
  /// In en, this message translates to:
  /// **'That\'s me'**
  String get speakerTagPromptThatsMe;

  /// Privacy page - ourCommitment
  ///
  /// In en, this message translates to:
  /// **'Our Commitment'**
  String get ourCommitment;

  /// Section title for notification scope configuration
  ///
  /// In en, this message translates to:
  /// **'Notification Scopes'**
  String get notificationScopes;

  /// Description for debug logs auto-delete
  ///
  /// In en, this message translates to:
  /// **'Auto-deletes after 3 days.'**
  String get autoDeletesAfter3Days;

  /// Status message during recorder initialization on mobile
  ///
  /// In en, this message translates to:
  /// **'Initialising Recorder'**
  String get initialisingRecorder;

  /// Status of a recording that is stored on the phone (list row and recording detail).
  ///
  /// In en, this message translates to:
  /// **'Saved on this phone'**
  String get privateAndSecureOnDevice;

  /// Migration message when all objects have been migrated
  ///
  /// In en, this message translates to:
  /// **'All objects migrated. Finalizing…'**
  String get allObjectsMigratedFinalizing;

  /// Button that opens Apple's Messages app
  ///
  /// In en, this message translates to:
  /// **'Open Messages'**
  String get chatAppsOpenMessages;

  /// Subscription banner button text
  ///
  /// In en, this message translates to:
  /// **'Upgrade to Pro'**
  String get upgradeToPro;

  /// OAuth client ID label
  ///
  /// In en, this message translates to:
  /// **'Client ID'**
  String get clientId;

  /// Title for background activity permission
  ///
  /// In en, this message translates to:
  /// **'Background activity'**
  String get backgroundActivity;

  /// No description provided for @noSummaryAvailable.
  ///
  /// In en, this message translates to:
  /// **'No Summary Available'**
  String get noSummaryAvailable;

  /// Error message when starring fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update starred status.'**
  String get failedToUpdateStarred;

  /// App title or branding on onboarding screen
  ///
  /// In en, this message translates to:
  /// **'Omi – Your AI Companion'**
  String get omiYourAiCompanion;

  /// Validation message prompting user to select a reason for their feedback
  ///
  /// In en, this message translates to:
  /// **'Please select a reason'**
  String get pleaseSelectReason;

  /// Confirmation message for clearing all memories
  ///
  /// In en, this message translates to:
  /// **'All {count} memories are deleted. This can\'t be undone.'**
  String clearMemoryConfirmation(int count);

  /// Button text to connect payment method
  ///
  /// In en, this message translates to:
  /// **'Connect Now'**
  String get connectNow;

  /// Confirmation dialog title
  ///
  /// In en, this message translates to:
  /// **'Disconnect {app}?'**
  String chatAppsDisconnectTitle(String app);

  /// WiFi sync settings - clearCredentials
  ///
  /// In en, this message translates to:
  /// **'Clear Credentials'**
  String get clearCredentials;

  /// Message asking user to grant contacts permission
  ///
  /// In en, this message translates to:
  /// **'Please grant contacts permission to share via SMS'**
  String get grantContactsPermissionForSms;

  /// Section title for cloud-based transcription providers
  ///
  /// In en, this message translates to:
  /// **'Cloud Transcription'**
  String get cloudTranscription;

  /// Filter option for retained memory history
  ///
  /// In en, this message translates to:
  /// **'History'**
  String get memoryHistory;

  /// Title for the speech samples page
  ///
  /// In en, this message translates to:
  /// **'Speech Samples'**
  String get speechSamples;

  /// Word Biggest in struggle/win templates
  ///
  /// In en, this message translates to:
  /// **'Biggest'**
  String get wrappedBiggest;

  /// Button (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Show More'**
  String get reviewShowMore;

  /// No description provided for @triggersWhenDaySummaryGenerated.
  ///
  /// In en, this message translates to:
  /// **'Triggers when day summary is generated.'**
  String get triggersWhenDaySummaryGenerated;

  /// After thumbs up/down feedback
  ///
  /// In en, this message translates to:
  /// **'Thank you for your feedback!'**
  String get thankYouFeedback;

  /// Button that shows the system permission prompt
  ///
  /// In en, this message translates to:
  /// **'Allow'**
  String get allow;

  /// Description showing what triggers an app, e.g. 'triggered by conversation end'
  ///
  /// In en, this message translates to:
  /// **'triggered by {triggerType}'**
  String triggeredByType(String triggerType);

  /// Button: opens the connection guide
  ///
  /// In en, this message translates to:
  /// **'How to Pair'**
  String get howToPair;

  /// Developer Settings switch that shows developer actions in a conversation's menu
  ///
  /// In en, this message translates to:
  /// **'Conversation Developer Tools'**
  String get conversationDeveloperTools;

  /// Provenance label for an iPhone capture device
  ///
  /// In en, this message translates to:
  /// **'iPhone'**
  String get memoryProvenanceIphone;

  /// Filter option for system memories
  ///
  /// In en, this message translates to:
  /// **'About You'**
  String get aboutYou;

  /// Provenance label for a Mac capture device
  ///
  /// In en, this message translates to:
  /// **'Mac'**
  String get memoryProvenanceMac;

  /// How much one kind of evidence raises confidence: moderately.
  ///
  /// In en, this message translates to:
  /// **'Helps'**
  String get effectCounts;

  /// No description provided for @tagSpeakerIncludingLaterSpeech.
  ///
  /// In en, this message translates to:
  /// **'Also tag later speech from this speaker'**
  String get tagSpeakerIncludingLaterSpeech;

  /// Settings label for storing audio locally on phone
  ///
  /// In en, this message translates to:
  /// **'Store Audio on Phone'**
  String get storeAudioOnPhone;

  /// Section header for developer API keys
  ///
  /// In en, this message translates to:
  /// **'Developer API Keys'**
  String get developerApiKeys;

  /// Badge text for my buddies card
  ///
  /// In en, this message translates to:
  /// **'My Buddies'**
  String get wrappedMyBuddiesCard;

  /// Snackbar shown when every selected task is already exported and Export is tapped
  ///
  /// In en, this message translates to:
  /// **'All selected tasks already exported'**
  String get bulkExportAlreadyExported;

  /// Badge shown on the most popular plan card
  ///
  /// In en, this message translates to:
  /// **'POPULAR'**
  String get popularBadge;

  /// No description provided for @enableLocationTitle.
  ///
  /// In en, this message translates to:
  /// **'Enable Location'**
  String get enableLocationTitle;

  /// Feedback menu item
  ///
  /// In en, this message translates to:
  /// **'Feedback / Bug'**
  String get feedbackBug;

  /// No description provided for @good.
  ///
  /// In en, this message translates to:
  /// **'Good'**
  String get good;

  /// Header for plan upgrade screen for non-paid users
  ///
  /// In en, this message translates to:
  /// **'Upgrade Your Plan'**
  String get upgradeYourPlan;

  /// Data export progress sheet - status text while the account export downloads
  ///
  /// In en, this message translates to:
  /// **'Exporting your data… Keep Omi open; large accounts can take several minutes.'**
  String get exportingAllData;

  /// Button label to confirm API environment switch
  ///
  /// In en, this message translates to:
  /// **'Switch'**
  String get switchAndRestart;

  /// No description provided for @noReposFound.
  ///
  /// In en, this message translates to:
  /// **'No repositories found'**
  String get noReposFound;

  /// Visible label for the jump-to-latest button in chat
  ///
  /// In en, this message translates to:
  /// **'Latest'**
  String get latest;

  /// No description provided for @failedToRevoke.
  ///
  /// In en, this message translates to:
  /// **'Failed to revoke authorization. Please try again.'**
  String get failedToRevoke;

  /// No description provided for @appleHealthDisconnectCta.
  ///
  /// In en, this message translates to:
  /// **'Disconnect Apple Health'**
  String get appleHealthDisconnectCta;

  /// Setting subtitle
  ///
  /// In en, this message translates to:
  /// **'Health, money, and anything you marked private stay out of chat apps.'**
  String get chatAppsPrivateMemoriesSubtitle;

  /// Title on delete-account flow feedback step
  ///
  /// In en, this message translates to:
  /// **'Tell us more'**
  String get deleteFlowFeedbackTitle;

  /// Error message when Todoist authentication fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Todoist. Please try again.'**
  String get failedToConnectTodoistRetry;

  /// Transcribe Later card, line 2 after the timer: recording paused because the phone is out of storage.
  ///
  /// In en, this message translates to:
  /// **'Phone storage full'**
  String get capturePhoneStorageFull;

  /// Delete people dialog title
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Delete 1 Person?} other{Delete {count} People?}}'**
  String deletePeopleTitle(int count);

  /// Empty state message when no one is unsure.
  ///
  /// In en, this message translates to:
  /// **'Omi isn\'t unsure about anyone right now.'**
  String get cleanUpNothingMessage;

  /// Placeholder text for review input
  ///
  /// In en, this message translates to:
  /// **'Write a review (optional)'**
  String get writeAReviewOptional;

  /// Error state text when sync fails
  ///
  /// In en, this message translates to:
  /// **'Sync failed'**
  String get syncFailed;

  /// No description provided for @audioShareFailed.
  ///
  /// In en, this message translates to:
  /// **'Share Failed'**
  String get audioShareFailed;

  /// Button text showing number of items remaining to load
  ///
  /// In en, this message translates to:
  /// **'Load More ({count} remaining)'**
  String loadMoreRemaining(String count);

  /// No description provided for @phoneDeleteNumberFailed.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t delete this number'**
  String get phoneDeleteNumberFailed;

  /// Warning about device codec compatibility
  ///
  /// In en, this message translates to:
  /// **'{device} records in a format this provider can\'t read ({reason}), so Omi\'s transcription will be used instead.'**
  String deviceUsesCodec(String device, String reason);

  /// Description on the iMessage connect sheet
  ///
  /// In en, this message translates to:
  /// **'Send Omi one message from the number you want to use. The code in it links that number to your account.'**
  String get chatAppsConnectIMessageMessage;

  /// Error dialog body when neither the server transcriber nor on-device speech recognition is available for the speech profile recording
  ///
  /// In en, this message translates to:
  /// **'Speech-to-text isn\'t available right now. Check your internet connection and your device\'s speech recognition settings, then try again.'**
  String get speechToTextUnavailableDesc;

  /// Shown when a chat reply times out
  ///
  /// In en, this message translates to:
  /// **'The response took too long. Please try again.'**
  String get chatReplyTimeout;

  /// Error when password is too short
  ///
  /// In en, this message translates to:
  /// **'Password must be at least 8 characters long'**
  String get passwordMinLengthError;

  /// Description on the WhatsApp sheet
  ///
  /// In en, this message translates to:
  /// **'We\'re working on bringing Omi to WhatsApp. It will show up here when it\'s ready.'**
  String get chatAppsWhatsAppMessage;

  /// Delete account checkbox confirmation
  ///
  /// In en, this message translates to:
  /// **'I understand that deleting my account is permanent and all data, including memories and conversations, will be lost and cannot be recovered.'**
  String get deleteAccountCheckbox;

  /// Description for connection requirement during firmware update
  ///
  /// In en, this message translates to:
  /// **'Connect to WiFi or cellular.'**
  String get firmwareConnectWifi;

  /// Consequence of forgetting a paired device
  ///
  /// In en, this message translates to:
  /// **'Omi will stop connecting to this device.'**
  String get forgetDeviceConfirmMessage;

  /// Feature point description
  ///
  /// In en, this message translates to:
  /// **'Tap to edit, swipe to complete or delete'**
  String get editSwipeFeature;

  /// Title for memory management dialog
  ///
  /// In en, this message translates to:
  /// **'Memory Management'**
  String get memoryManagement;

  /// Transcript tab when fetching the conversation's lines failed; shown above Try Again.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load the transcript.'**
  String get transcriptLoadFailed;

  /// Title and subject of the shared device diagnostics file
  ///
  /// In en, this message translates to:
  /// **'Omi Device Diagnostics'**
  String get diagnosticsExportTitle;

  /// Button text to update Omi device firmware
  ///
  /// In en, this message translates to:
  /// **'Update Omi firmware'**
  String get updateOmiFirmware;

  /// Error when an import is refused because the user started too many imports in a short time (HTTP 429)
  ///
  /// In en, this message translates to:
  /// **'Too many imports right now. Try again later.'**
  String get importTooManyAttempts;

  /// Empty state title when no apps match search
  ///
  /// In en, this message translates to:
  /// **'No apps found'**
  String get noAppsFound;

  /// No description provided for @phoneSetupStep1Subtitle.
  ///
  /// In en, this message translates to:
  /// **'We\'ll call you to confirm it\'s yours'**
  String get phoneSetupStep1Subtitle;

  /// Dialog title for deleting synced files
  ///
  /// In en, this message translates to:
  /// **'Delete Synced Recordings'**
  String get deleteSyncedFiles;

  /// After tagging a person: whether Omi has learned to recognize their voice (server voice_learning_state)
  ///
  /// In en, this message translates to:
  /// **'{state, select, learned{Voice learned} pending{Learning voice…} disabled{Voice saving is off} other{Voice not learned yet}}'**
  String speakerLabelVoiceStatus(String state);

  /// recordingsMayCaptureOthers label
  ///
  /// In en, this message translates to:
  /// **'Recordings may capture others\' voices. Ensure you have consent from all participants before enabling.'**
  String get recordingsMayCaptureOthers;

  /// Label of the thumbs-up under a chat reply (pairs with 'Not Helpful')
  ///
  /// In en, this message translates to:
  /// **'Helpful'**
  String get helpful;

  /// Download progress status
  ///
  /// In en, this message translates to:
  /// **'Downloading {model}: {received} / {total} MB'**
  String downloadingModelProgress(String model, String received, String total);

  /// Title for the permissions settings page
  ///
  /// In en, this message translates to:
  /// **'Permissions'**
  String get permissions;

  /// No description provided for @audioDownloadSuccess.
  ///
  /// In en, this message translates to:
  /// **'Audio downloaded successfully'**
  String get audioDownloadSuccess;

  /// Dialog title for confirming plan change
  ///
  /// In en, this message translates to:
  /// **'Confirm Plan Change'**
  String get confirmPlanChange;

  /// Default title for most cringe moment
  ///
  /// In en, this message translates to:
  /// **'That Awkward Moment'**
  String get wrappedThatAwkwardMoment;

  /// No description provided for @calendarProviders.
  ///
  /// In en, this message translates to:
  /// **'Calendar Providers'**
  String get calendarProviders;

  /// Evidence row: conversations where Omi matched this person automatically and nobody confirmed it.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 automatic label not confirmed yet} other{{count} automatic labels not confirmed yet}}'**
  String evidenceAutoUnconfirmed(int count);

  /// Import data feature name
  ///
  /// In en, this message translates to:
  /// **'Import Data'**
  String get importData;

  /// Abbreviated Monday
  ///
  /// In en, this message translates to:
  /// **'Mon'**
  String get weekdayMon;

  /// Title of the on-device storage usage card on the Auto Sync page
  ///
  /// In en, this message translates to:
  /// **'Device Storage'**
  String get deviceStorageTitle;

  /// Section title for external app access settings
  ///
  /// In en, this message translates to:
  /// **'External App Access'**
  String get externalAppAccess;

  /// Status when transcription WebSocket failed after max retries
  ///
  /// In en, this message translates to:
  /// **'Transcription unavailable'**
  String get transcriptionUnavailable;

  /// Terms and Privacy Policy link text
  ///
  /// In en, this message translates to:
  /// **'Terms & Privacy Policy'**
  String get termsAndPrivacyPolicy;

  /// Message when no imports exist
  ///
  /// In en, this message translates to:
  /// **'No imports yet'**
  String get noImportsYet;

  /// Description explaining Omi is installed and user should open it
  ///
  /// In en, this message translates to:
  /// **'The Omi app is installed on your Apple Watch. Open it and tap Start to begin.'**
  String get openOmiOnAppleWatchDescription;

  /// Run summary when the pass failed; error is a technical error type name.
  ///
  /// In en, this message translates to:
  /// **'Failed ({error})'**
  String dreamReportFailed(String error);

  /// Option to share summary
  ///
  /// In en, this message translates to:
  /// **'Send Summary'**
  String get sendSummary;

  /// Filter option
  ///
  /// In en, this message translates to:
  /// **'All'**
  String get filterAll;

  /// Ask: what deleting a past chat means
  ///
  /// In en, this message translates to:
  /// **'It’s gone from Past chats for good.'**
  String get deleteChatMessage;

  /// No description provided for @timeout10Minutes.
  ///
  /// In en, this message translates to:
  /// **'10 minutes'**
  String get timeout10Minutes;

  /// Empty state of the link-event sheet
  ///
  /// In en, this message translates to:
  /// **'No calendar events found around this time.'**
  String get noCalendarEventsNearby;

  /// Title for cancel sync confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'Cancel sync?'**
  String get cancelSyncQuestion;

  /// No description provided for @whatShouldWeMake.
  ///
  /// In en, this message translates to:
  /// **'What should we make?'**
  String get whatShouldWeMake;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Listened'**
  String get usageListened;

  /// Error message when Stripe update fails
  ///
  /// In en, this message translates to:
  /// **'Error updating Stripe details! Please try again later.'**
  String get errorUpdatingStripeDetails;

  /// No description provided for @conversationEndAfterHours.
  ///
  /// In en, this message translates to:
  /// **'Conversations will now end after 4 hours of silence'**
  String get conversationEndAfterHours;

  /// Dialog description for activation error
  ///
  /// In en, this message translates to:
  /// **'There was an issue activating this app. Please try again.'**
  String get issueActivatingApp;

  /// Success message after app is created
  ///
  /// In en, this message translates to:
  /// **'App created successfully!'**
  String get appCreatedSuccessfully;

  /// No description provided for @categoryNews.
  ///
  /// In en, this message translates to:
  /// **'News'**
  String get categoryNews;

  /// No description provided for @phoneSearchHint.
  ///
  /// In en, this message translates to:
  /// **'Search'**
  String get phoneSearchHint;

  /// Small count beside the Pinned group header.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 pinned} other{{count} pinned}}'**
  String peoplePinnedCount(int count);

  /// Label for hours stat
  ///
  /// In en, this message translates to:
  /// **'hours'**
  String get wrappedHours;

  /// Label for the keypad/dialpad button during an active phone call
  ///
  /// In en, this message translates to:
  /// **'Keypad'**
  String get phoneKeypad;

  /// Filter chip over the People list: people Omi is unsure about (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Low Confidence'**
  String get peopleFilterLowConfidence;

  /// Checkbox label for agreeing to contribute data
  ///
  /// In en, this message translates to:
  /// **'I understand and agree to contribute my data for AI training'**
  String get agreeToContributeData;

  /// Menu option to add a new goal
  ///
  /// In en, this message translates to:
  /// **'Add Goal'**
  String get addGoal;

  /// Error when a run is already in progress.
  ///
  /// In en, this message translates to:
  /// **'A pass is already running. Try again in a minute.'**
  String get dreamReportRunInProgress;

  /// No description provided for @importedConfig.
  ///
  /// In en, this message translates to:
  /// **'Imported {providerName} configuration'**
  String importedConfig(String providerName);

  /// No description provided for @monthsAgo.
  ///
  /// In en, this message translates to:
  /// **'{count} months ago'**
  String monthsAgo(int count);

  /// Heading shown above the list of free-plan limitations in the downgrade dialog
  ///
  /// In en, this message translates to:
  /// **'You will experience these limitations:'**
  String get downgradeLimitationsHeading;

  /// Screen-reader label of the X on the quoted text the next chat message asks about
  ///
  /// In en, this message translates to:
  /// **'Remove quoted text'**
  String get chatRemoveSelectedText;

  /// Firmware update step title about battery level
  ///
  /// In en, this message translates to:
  /// **'Battery Above 15%'**
  String get firmwareBatteryAbove15;

  /// Question card: are two contact profiles the same person
  ///
  /// In en, this message translates to:
  /// **'Same person as “{name}”?'**
  String reviewQuestionSamePerson(String name);

  /// How much one kind of evidence raises confidence: strongly.
  ///
  /// In en, this message translates to:
  /// **'Helps a lot'**
  String get effectCountsALot;

  /// Label for SD card storage
  ///
  /// In en, this message translates to:
  /// **'SD Card'**
  String get sdCard;

  /// Action in the linked calendar event sheet
  ///
  /// In en, this message translates to:
  /// **'Open in Google Calendar'**
  String get openInGoogleCalendar;

  /// No description provided for @appleHealthFeatureSecureTitle.
  ///
  /// In en, this message translates to:
  /// **'Secure sync'**
  String get appleHealthFeatureSecureTitle;

  /// Subtitle of the Conversation Developer Tools switch
  ///
  /// In en, this message translates to:
  /// **'Show Copy Conversation ID and Test Prompt in a conversation\'s menu'**
  String get conversationDeveloperToolsDescription;

  /// No description provided for @host.
  ///
  /// In en, this message translates to:
  /// **'Host'**
  String get host;

  /// Delete reason option
  ///
  /// In en, this message translates to:
  /// **'Missing features I need'**
  String get deleteReasonMissingFeatures;

  /// Status when sync is happening
  ///
  /// In en, this message translates to:
  /// **'Syncing in progress'**
  String get syncingInProgress;

  /// Label for Done tab
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get tabDone;

  /// Button text to confirm revocation
  ///
  /// In en, this message translates to:
  /// **'Revoke'**
  String get revoke;

  /// MCP (Model Context Protocol) section header
  ///
  /// In en, this message translates to:
  /// **'MCP'**
  String get mcp;

  /// Description when template is public
  ///
  /// In en, this message translates to:
  /// **'Anyone can discover your template'**
  String get anyoneCanDiscoverTemplate;

  /// No description provided for @mcpDescription.
  ///
  /// In en, this message translates to:
  /// **'To connect Omi with other applications to read, search, and manage your memories and conversations. Create a key to get started.'**
  String get mcpDescription;

  /// Dialog message when connection is lost
  ///
  /// In en, this message translates to:
  /// **'The connection was interrupted. Please check your internet connection and try again.'**
  String get connectionLostDescription;

  /// Empty state message
  ///
  /// In en, this message translates to:
  /// **'Chats you have with Omi in {app} show up here.'**
  String chatAppsNoChatsMessage(String app);

  /// No description provided for @storedLocallyNeverShared.
  ///
  /// In en, this message translates to:
  /// **'Saved on this phone. Only sent to your transcription provider.'**
  String get storedLocallyNeverShared;

  /// Placeholder card text shown under available payment methods
  ///
  /// In en, this message translates to:
  /// **'More payment methods coming soon'**
  String get morePaymentMethodsComingSoon;

  /// Title when everything is synced
  ///
  /// In en, this message translates to:
  /// **'All caught up'**
  String get allCaughtUp;

  /// Screen-reader label of an app screenshot in the store
  ///
  /// In en, this message translates to:
  /// **'Screenshot {index} of {total}'**
  String previewImageLabel(int index, int total);

  /// Button to disable/remove an app
  ///
  /// In en, this message translates to:
  /// **'Disable'**
  String get disable;

  /// Section header for recordings list
  ///
  /// In en, this message translates to:
  /// **'Recordings'**
  String get recordings;

  /// No description provided for @enterPersonsName.
  ///
  /// In en, this message translates to:
  /// **'Enter Person\'s Name'**
  String get enterPersonsName;

  /// Description for conversation webhook
  ///
  /// In en, this message translates to:
  /// **'New conversation created'**
  String get newConversationCreated;

  /// No description provided for @resetsInDays.
  ///
  /// In en, this message translates to:
  /// **'Resets in {count} day(s)'**
  String resetsInDays(int count);

  /// Confidence level for a person's voice: the user has confirmed it many times. Short label.
  ///
  /// In en, this message translates to:
  /// **'Confirmed'**
  String get confidenceConfirmed;

  /// Snackbar shown while a bulk export is running
  ///
  /// In en, this message translates to:
  /// **'Exporting…'**
  String get bulkExportInProgress;

  /// No description provided for @detectLanguages.
  ///
  /// In en, this message translates to:
  /// **'Detect 10+ languages'**
  String get detectLanguages;

  /// No description provided for @phoneSpeaker.
  ///
  /// In en, this message translates to:
  /// **'Speaker'**
  String get phoneSpeaker;

  /// Visit website link
  ///
  /// In en, this message translates to:
  /// **'Visit Website'**
  String get visitWebsite;

  /// Dialog title for speech sample instructions
  ///
  /// In en, this message translates to:
  /// **'How to take a good sample?'**
  String get howToTakeGoodSample;

  /// Button/menu item to clear chat
  ///
  /// In en, this message translates to:
  /// **'Clear Chat'**
  String get clearChat;

  /// No description provided for @languageSetTo.
  ///
  /// In en, this message translates to:
  /// **'Language set to {language}'**
  String languageSetTo(String language);

  /// Description of the Headphones only voice response mode
  ///
  /// In en, this message translates to:
  /// **'Private. Speaks only through AirPods, Bluetooth or wired headphones.'**
  String get deviceOnboardingVoiceReplyHeadphonesDescription;

  /// Message explaining plan remains active until date
  ///
  /// In en, this message translates to:
  /// **'Your plan stays active until {date}. After that, you lose your unlimited features.'**
  String planRemainsActiveUntil(String date);

  /// OAuth client secret label
  ///
  /// In en, this message translates to:
  /// **'Client Secret'**
  String get clientSecret;

  /// Pairing title for Apple Watch
  ///
  /// In en, this message translates to:
  /// **'Connect Apple Watch'**
  String get pairingTitleAppleWatch;

  /// Button to share message
  ///
  /// In en, this message translates to:
  /// **'Share'**
  String get share;

  /// Data privacy page heading
  ///
  /// In en, this message translates to:
  /// **'Your Privacy, Your Control'**
  String get yourPrivacyYourControl;

  /// Hint text for tap to copy action
  ///
  /// In en, this message translates to:
  /// **'Tap to copy'**
  String get tapToCopy;

  /// Feedback title when cancel reason is found alternative
  ///
  /// In en, this message translates to:
  /// **'What are you switching to?'**
  String get feedbackTitleFoundAlternative;

  /// Filter label to show all items
  ///
  /// In en, this message translates to:
  /// **'All'**
  String get all;

  /// Capabilities filter dropdown label
  ///
  /// In en, this message translates to:
  /// **'Capabilities'**
  String get filterCapabilities;

  /// No description provided for @tagOtherSegments.
  ///
  /// In en, this message translates to:
  /// **'Tag other segments'**
  String get tagOtherSegments;

  /// Section label: decisions made in a project
  ///
  /// In en, this message translates to:
  /// **'Decisions'**
  String get entityDecisions;

  /// No description provided for @tasksCreatedInWorkspace.
  ///
  /// In en, this message translates to:
  /// **'Tasks will be created in this workspace'**
  String get tasksCreatedInWorkspace;

  /// No description provided for @fairUseDailyTranscription.
  ///
  /// In en, this message translates to:
  /// **'Daily Transcription'**
  String get fairUseDailyTranscription;

  /// Pause playback of an audio sample (button label)
  ///
  /// In en, this message translates to:
  /// **'Pause'**
  String get pausePlayback;

  /// Toast when a shared-tasks link cannot be opened
  ///
  /// In en, this message translates to:
  /// **'These shared tasks weren\'t found, or the link has expired.'**
  String get sharedTasksLinkExpired;

  /// No description provided for @editConversationDialogTitle.
  ///
  /// In en, this message translates to:
  /// **'Edit Conversation'**
  String get editConversationDialogTitle;

  /// Confirmation message for deleting memory
  ///
  /// In en, this message translates to:
  /// **'Delete this memory? This can\'t be undone.'**
  String get deleteMemoryConfirmation;

  /// Message shown when app is under review
  ///
  /// In en, this message translates to:
  /// **'Your app is under review and visible only to you. It will be public once approved.'**
  String get appUnderReviewMessage;

  /// Button to defer connection
  ///
  /// In en, this message translates to:
  /// **'I\'ll Do It Later'**
  String get illDoItLater;

  /// Home live capture card, line 2 after the timer while the transcription connection is being restored: recording has not stopped.
  ///
  /// In en, this message translates to:
  /// **'Still recording'**
  String get captureStillRecording;

  /// Confidence sheet: what the user can do to reach Confirmed; "them" is the person.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Label them in 1 more conversation.} other{Label them in {count} more conversations.}}'**
  String confidenceNextLabels(int count);

  /// Error when saving an answer fails
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t save that. Please try again.'**
  String get speakerTagPromptAnswerFailed;

  /// Quick reason chip: the summary was incomplete.
  ///
  /// In en, this message translates to:
  /// **'Incomplete'**
  String get feedbackReasonSummaryIncomplete;

  /// Dialog title when app activation fails
  ///
  /// In en, this message translates to:
  /// **'Error activating the app'**
  String get errorActivatingApp;

  /// Label for tasks completed count
  ///
  /// In en, this message translates to:
  /// **'Tasks Completed'**
  String get tasksCompleted;

  /// Screen-reader label of the onboarding progress dots
  ///
  /// In en, this message translates to:
  /// **'Step {current} of {total}'**
  String onboardingStepOf(int current, int total);

  /// Destructive confirm button on the downgrade dialog
  ///
  /// In en, this message translates to:
  /// **'Downgrade Anyway'**
  String get downgradeAnyway;

  /// Hint for an intentionally empty field (e.g. OAuth client secret)
  ///
  /// In en, this message translates to:
  /// **'Leave blank'**
  String get leaveBlank;

  /// Row that opens the list of this chat app's chats
  ///
  /// In en, this message translates to:
  /// **'View Chats'**
  String get chatAppsViewChats;

  /// No description provided for @captureScreenRecordingPermissionRequired.
  ///
  /// In en, this message translates to:
  /// **'Screen recording permission required'**
  String get captureScreenRecordingPermissionRequired;

  /// Title for account cutover force-upgrade blocking screen
  ///
  /// In en, this message translates to:
  /// **'Update Required'**
  String get accountCutoverUpdateRequiredTitle;

  /// No description provided for @weeksAgo.
  ///
  /// In en, this message translates to:
  /// **'{count} weeks ago'**
  String weeksAgo(int count);

  /// No description provided for @phoneEndCall.
  ///
  /// In en, this message translates to:
  /// **'End'**
  String get phoneEndCall;

  /// Launch failure screen, runtime failure
  ///
  /// In en, this message translates to:
  /// **'Something went wrong while Omi was starting. Check your connection, then try again.'**
  String get startupFailedMessage;

  /// No description provided for @permissionRevokedTitle.
  ///
  /// In en, this message translates to:
  /// **'Permission Revoked'**
  String get permissionRevokedTitle;

  /// Section title for chat features
  ///
  /// In en, this message translates to:
  /// **'Chat Features'**
  String get chatFeatures;

  /// Error message when map fails to load
  ///
  /// In en, this message translates to:
  /// **'Could not load map'**
  String get couldNotLoadMap;

  /// Button text when no contacts are selected
  ///
  /// In en, this message translates to:
  /// **'Select contacts to share'**
  String get selectContactsToShare;

  /// Generic OK button text
  ///
  /// In en, this message translates to:
  /// **'OK'**
  String get ok;

  /// Status after the user confirms a learned memory
  ///
  /// In en, this message translates to:
  /// **'Confirmed.'**
  String get memoryReviewConfirmed;

  /// Delete knowledge graph feature name
  ///
  /// In en, this message translates to:
  /// **'Delete Knowledge Graph'**
  String get deleteKnowledgeGraph;

  /// Error toast
  ///
  /// In en, this message translates to:
  /// **'Couldn’t update this change. Try again.'**
  String get reviewChangeFailed;

  /// Label for Limitless device storage
  ///
  /// In en, this message translates to:
  /// **'Limitless'**
  String get limitless;

  /// No description provided for @uploadingToCloud.
  ///
  /// In en, this message translates to:
  /// **'Uploading {current} of {total}'**
  String uploadingToCloud(int current, int total);

  /// No description provided for @dontSeeYourDevice.
  ///
  /// In en, this message translates to:
  /// **'Don\'t see your device?'**
  String get dontSeeYourDevice;

  /// No description provided for @actionItemsSyncedTo.
  ///
  /// In en, this message translates to:
  /// **'Your tasks will be synced to your {appName} account'**
  String actionItemsSyncedTo(String appName);

  /// Label of the gear button on an app's page that opens the app's own settings page
  ///
  /// In en, this message translates to:
  /// **'{appName} settings'**
  String appSettingsLabel(String appName);

  /// Button on an expanded chat discovery card that collapses it back to its summary
  ///
  /// In en, this message translates to:
  /// **'Show Less'**
  String get chatBlockShowLess;

  /// Section header for memory knowledge graph on home page
  ///
  /// In en, this message translates to:
  /// **'Mind Map'**
  String get mindMap;

  /// No description provided for @authorizationBearer.
  ///
  /// In en, this message translates to:
  /// **'Authorization: Bearer <key>'**
  String get authorizationBearer;

  /// Section label for tasks the agent would suggest.
  ///
  /// In en, this message translates to:
  /// **'Would suggest tasks'**
  String get dreamReportWouldSuggestTasks;

  /// Section label for questions the agent would ask the user.
  ///
  /// In en, this message translates to:
  /// **'Would ask you'**
  String get dreamReportWouldAsk;

  /// Title of the training-data opt-in card offering free unlimited access
  ///
  /// In en, this message translates to:
  /// **'Get Free Unlimited Access'**
  String get getFreeUnlimitedAccess;

  /// Daily summary detail - yourDaysJourney
  ///
  /// In en, this message translates to:
  /// **'Your Day\'s Journey'**
  String get yourDaysJourney;

  /// Description for transcript webhook
  ///
  /// In en, this message translates to:
  /// **'Transcript received'**
  String get transcriptReceived;

  /// Button text to expand/open a section such as the mind map preview
  ///
  /// In en, this message translates to:
  /// **'Expand'**
  String get expand;

  /// Completion screen at the end of first-run onboarding
  ///
  /// In en, this message translates to:
  /// **'Keep Omi running for a couple of days. Your conversations, memories, and to-dos will start filling in.'**
  String get onboardingCompleteMessage;

  /// No description provided for @trainFamilyProfiles.
  ///
  /// In en, this message translates to:
  /// **'Train Profiles for Friends and Family'**
  String get trainFamilyProfiles;

  /// Button to select text from message
  ///
  /// In en, this message translates to:
  /// **'Select Text'**
  String get selectText;

  /// Status message during app creation
  ///
  /// In en, this message translates to:
  /// **'Generating description…'**
  String get generatingDescription;

  /// Tutorial step 4 double-tap option description for Star Conversation
  ///
  /// In en, this message translates to:
  /// **'Mark conversation as important'**
  String get deviceOnboardingStarConversationDesc;

  /// Screen-reader label and tooltip of the control in the chat apps drawer that disables an app
  ///
  /// In en, this message translates to:
  /// **'Disable {appName}'**
  String disableAppNamed(String appName);

  /// No description provided for @deleteConversationConfirmation.
  ///
  /// In en, this message translates to:
  /// **'Delete this conversation? This can\'t be undone.'**
  String get deleteConversationConfirmation;

  /// Snackbar message when content is copied
  ///
  /// In en, this message translates to:
  /// **'Content copied to clipboard'**
  String get contentCopied;

  /// No description provided for @joinTheCommunity.
  ///
  /// In en, this message translates to:
  /// **'Join the community!'**
  String get joinTheCommunity;

  /// Message when no contacts have phone numbers
  ///
  /// In en, this message translates to:
  /// **'No contacts with phone numbers found'**
  String get noContactsWithPhoneNumbers;

  /// Screen-reader label of the X on a file picked for the next chat message
  ///
  /// In en, this message translates to:
  /// **'Remove attachment'**
  String get removeAttachment;

  /// No description provided for @followTheVoiceInstructions.
  ///
  /// In en, this message translates to:
  /// **'Follow the voice instructions'**
  String get followTheVoiceInstructions;

  /// Button title for creating custom apps
  ///
  /// In en, this message translates to:
  /// **'Create Your Own App'**
  String get createYourOwnApp;

  /// Section title for payment information for paid apps
  ///
  /// In en, this message translates to:
  /// **'Payment Details'**
  String get paymentDetails;

  /// No description provided for @tellOmiWhoSaidIt.
  ///
  /// In en, this message translates to:
  /// **'Tell Omi who said it 🗣️'**
  String get tellOmiWhoSaidIt;

  /// Success message when audio device changed
  ///
  /// In en, this message translates to:
  /// **'Audio input set to {deviceName}'**
  String audioInputSetTo(String deviceName);

  /// No description provided for @pleaseEnterValidEmail.
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid email address'**
  String get pleaseEnterValidEmail;

  /// Time period: This Year
  ///
  /// In en, this message translates to:
  /// **'This Year'**
  String get thisYear;

  /// Empty state message when no transcript
  ///
  /// In en, this message translates to:
  /// **'This conversation doesn\'t have a transcript.'**
  String get noTranscriptMessage;

  /// No description provided for @appearanceDark.
  ///
  /// In en, this message translates to:
  /// **'Dark'**
  String get appearanceDark;

  /// No description provided for @createCustomTemplate.
  ///
  /// In en, this message translates to:
  /// **'Create Custom Template'**
  String get createCustomTemplate;

  /// May month abbreviation
  ///
  /// In en, this message translates to:
  /// **'May'**
  String get monthMay;

  /// No description provided for @tasksAddedToList.
  ///
  /// In en, this message translates to:
  /// **'Tasks will be added to this list'**
  String get tasksAddedToList;

  /// Sentence starting with 'Is' for trigger description
  ///
  /// In en, this message translates to:
  /// **'Is {triggerDescription}.'**
  String isTriggeredBy(String triggerDescription);

  /// Title for delete confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'Delete Conversation?'**
  String get deleteConversationTitle;

  /// Body for account cutover force-upgrade blocking screen
  ///
  /// In en, this message translates to:
  /// **'Install the latest Omi app to continue after account migration.'**
  String get accountCutoverUpdateRequiredMessage;

  /// TXT file format label
  ///
  /// In en, this message translates to:
  /// **'TXT'**
  String get txtFormat;

  /// Confirmation dialog message
  ///
  /// In en, this message translates to:
  /// **'Omi will stop replying in {app} and delete the chat history it keeps for it. Messages already in {app} stay there.'**
  String chatAppsDisconnectMessage(String app);

  /// File option: capture with camera subtitle
  ///
  /// In en, this message translates to:
  /// **'Capture with camera'**
  String get captureWithCamera;

  /// Label for the app ID field
  ///
  /// In en, this message translates to:
  /// **'App ID'**
  String get appIdLabel;

  /// Label for webhook endpoint URL field
  ///
  /// In en, this message translates to:
  /// **'Endpoint URL'**
  String get endpointUrl;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Task updated'**
  String get actionItemUpdated;

  /// Selection count in app bar
  ///
  /// In en, this message translates to:
  /// **'{count} selected'**
  String itemsSelected(int count);

  /// Description for onboarding memory graph preview step
  ///
  /// In en, this message translates to:
  /// **'This map updates as Omi learns from your conversations.'**
  String get onboardingWhatIKnowAboutYouDescription;

  /// Caption beside the live signal chart title; duration is the chart window, e.g. 60s
  ///
  /// In en, this message translates to:
  /// **'Last {duration}'**
  String diagnosticsLastDuration(String duration);

  /// Pairing description for Limitless device
  ///
  /// In en, this message translates to:
  /// **'When any light is visible, press once and then press and hold until the device shows a pink light, then release.'**
  String get pairingDescLimitless;

  /// Action on a chat conversation link block
  ///
  /// In en, this message translates to:
  /// **'Open Conversation'**
  String get chatBlockOpenConversation;

  /// No description provided for @insightsUsedThisMonth.
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} insights gained this month'**
  String insightsUsedThisMonth(String used, String limit);

  /// Description of connection error
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to the server. Please check your internet connection and try again.'**
  String get connectionErrorDesc;

  /// Placeholder hint for vocabulary input field
  ///
  /// In en, this message translates to:
  /// **'Enter words (comma separated)'**
  String get enterWordsCommaSeparated;

  /// Text for other devices placeholder
  ///
  /// In en, this message translates to:
  /// **'Other devices coming soon'**
  String get otherDevicesComingSoon;

  /// Compact chip on a transcript speaker asking whether the voice is this person.
  ///
  /// In en, this message translates to:
  /// **'{name}?'**
  String speakerSuggestionChip(String name);

  /// Undo toast after answering Not a Person.
  ///
  /// In en, this message translates to:
  /// **'Marked as not a person'**
  String get speakerTagPromptNotAPersonToast;

  /// Hint to create first API key
  ///
  /// In en, this message translates to:
  /// **'Create a key to get started'**
  String get createKeyToGetStarted;

  /// Confirm button that splits a recording out of a grouped conversation
  ///
  /// In en, this message translates to:
  /// **'Separate'**
  String get captureRecordingSeparateConfirm;

  /// Device Diagnostics row title: how many times the connection dropped and recovered
  ///
  /// In en, this message translates to:
  /// **'Drops'**
  String get diagnosticsDrops;

  /// Body text for low battery notification
  ///
  /// In en, this message translates to:
  /// **'Your battery is at {level}%. Time for a recharge! 🔋'**
  String lowBatteryAlertBody(int level);

  /// Tutorial step 3 instruction to long-press the button to turn the device off
  ///
  /// In en, this message translates to:
  /// **'Hold the button for 3 seconds'**
  String get deviceOnboardingTurnOffSubtitle;

  /// Status when download is done
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get done;

  /// No description provided for @wifiConfigurationSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Enter your WiFi credentials to allow the device to download the firmware.'**
  String get wifiConfigurationSubtitle;

  /// Instructions after permission is granted
  ///
  /// In en, this message translates to:
  /// **'Permission granted! Now:\n\nOpen the Omi app on your watch and tap \"Continue\" below'**
  String get permissionGrantedNow;

  /// App bar title when setting up PayPal
  ///
  /// In en, this message translates to:
  /// **'Set Up PayPal'**
  String get setUpPayPal;

  /// Status value for processed recording
  ///
  /// In en, this message translates to:
  /// **'Processed'**
  String get statusProcessed;

  /// No description provided for @phoneFreeCallsRemaining.
  ///
  /// In en, this message translates to:
  /// **'{remaining} of {limit} free calls remaining this month'**
  String phoneFreeCallsRemaining(int remaining, int limit);

  /// No description provided for @event.
  ///
  /// In en, this message translates to:
  /// **'Event'**
  String get event;

  /// Webhook type for conversation events
  ///
  /// In en, this message translates to:
  /// **'Conversation Events'**
  String get conversationEvents;

  /// Button text to uninstall app
  ///
  /// In en, this message translates to:
  /// **'Uninstall'**
  String get uninstall;

  /// No description provided for @appCreators.
  ///
  /// In en, this message translates to:
  /// **'App Creators'**
  String get appCreators;

  /// Status text shown when microphone is muted
  ///
  /// In en, this message translates to:
  /// **'Muted'**
  String get muted;

  /// Confirm action button on the delete-recap dialog.
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get deleteRecapAction;

  /// Generic error when thumbnail selection fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting thumbnail. Please try again.'**
  String get addAppErrorSelectingThumbnailRetry;

  /// Description of basic plan features in usage page
  ///
  /// In en, this message translates to:
  /// **'300 premium mins + unlimited on-device'**
  String get basicPlanDescription;

  /// Warning that country selection cannot be changed
  ///
  /// In en, this message translates to:
  /// **'Your country selection is permanent and cannot be changed later.'**
  String get countrySelectionPermanent;

  /// Status when transcription WebSocket is connecting
  ///
  /// In en, this message translates to:
  /// **'Connecting transcription…'**
  String get transcriptionConnecting;

  /// Queued recordings still waiting for transcription (pending) out of the session total, on the live-capture WAL indicator.
  ///
  /// In en, this message translates to:
  /// **'Transcriptions pending {pending}/{total}'**
  String transcriptionsPendingFraction(int pending, int total);

  /// API Key authentication section header
  ///
  /// In en, this message translates to:
  /// **'API Key Auth'**
  String get apiKeyAuth;

  /// Button to download model
  ///
  /// In en, this message translates to:
  /// **'Download Model ({model})'**
  String downloadModelWithName(String model);

  /// Error message when day summary webhook URL is invalid in developer settings
  ///
  /// In en, this message translates to:
  /// **'Invalid day summary webhook URL'**
  String get devModeInvalidDaySummaryWebhookUrl;

  /// Shown when a verdict or correction on a learned memory failed
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t save, try again'**
  String get memoryReviewSaveFailed;

  /// No description provided for @payYourSttProvider.
  ///
  /// In en, this message translates to:
  /// **'Free in Omi. You pay your transcription provider directly.'**
  String get payYourSttProvider;

  /// Daily summary section header
  ///
  /// In en, this message translates to:
  /// **'DAILY SUMMARY'**
  String get dailySummaryHeader;

  /// No description provided for @fairUseStageWarning.
  ///
  /// In en, this message translates to:
  /// **'Warning'**
  String get fairUseStageWarning;

  /// Error description for multiple speakers
  ///
  /// In en, this message translates to:
  /// **'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.'**
  String get multipleSpeakersDesc;

  /// Ask: the history page title and button
  ///
  /// In en, this message translates to:
  /// **'Past chats'**
  String get pastChats;

  /// No description provided for @listeningMins.
  ///
  /// In en, this message translates to:
  /// **'Listening (mins)'**
  String get listeningMins;

  /// Pairing description for Omi device
  ///
  /// In en, this message translates to:
  /// **'Press and hold the device until it vibrates to turn it on.'**
  String get pairingDescOmi;

  /// Onboarding intro screen subtitle explaining the tutorial
  ///
  /// In en, this message translates to:
  /// **'Try live transcription, asking a question, and the double-tap shortcut.'**
  String get deviceOnboardingIntroSubtitle;

  /// Settings row title: automatically remove synced phone-local recording copies
  ///
  /// In en, this message translates to:
  /// **'Auto-Remove Synced Copies'**
  String get autoRemoveSyncedCopiesTitle;

  /// Footer under the chat list
  ///
  /// In en, this message translates to:
  /// **'These chats are read-only here. Reply in {app}.'**
  String chatAppsReadOnlyFooter(String app);

  /// Status when microphone changed and auto-resuming
  ///
  /// In en, this message translates to:
  /// **'Microphone changed. Resuming in {countdown}s'**
  String microphoneChangedResumingIn(String countdown);

  /// Action sheet option to take a photo
  ///
  /// In en, this message translates to:
  /// **'Take Photo'**
  String get takePhoto;

  /// Dialog title and button to cancel sync
  ///
  /// In en, this message translates to:
  /// **'Cancel Sync'**
  String get cancelSync;

  /// No description provided for @appSettings.
  ///
  /// In en, this message translates to:
  /// **'{appName} Settings'**
  String appSettings(String appName);

  /// Error when checking microphone permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Microphone permission: {error}'**
  String onboardingFailedCheckMicrophone(String error);

  /// Microphone gain setting
  ///
  /// In en, this message translates to:
  /// **'Mic Gain'**
  String get micGain;

  /// No description provided for @collectingData.
  ///
  /// In en, this message translates to:
  /// **'Collecting data…'**
  String get collectingData;

  /// Shown under a read-only (historical or superseded) memory
  ///
  /// In en, this message translates to:
  /// **'This memory is kept as history and can\'t be edited.'**
  String get memoryReadOnlyHint;

  /// Notice shown to app owner when app is under review
  ///
  /// In en, this message translates to:
  /// **'Your app is under review and visible only to you. It will be public once approved.'**
  String get appUnderReviewOwner;

  /// Title for add person dialog
  ///
  /// In en, this message translates to:
  /// **'Add New Person'**
  String get addNewPerson;

  /// Title of the name-speaker sheet when the speaker has no resolvable number
  ///
  /// In en, this message translates to:
  /// **'Name Speaker'**
  String get nameSpeakerTitle;

  /// Description shown during SD card transfer
  ///
  /// In en, this message translates to:
  /// **'Downloading audio from your device\'s SD card'**
  String get downloadingAudioFromSdCard;

  /// No description provided for @pendantSyncingRecordings.
  ///
  /// In en, this message translates to:
  /// **'Syncing recordings from your pendant…'**
  String get pendantSyncingRecordings;

  /// OmiGlass OTA not supported on current firmware
  ///
  /// In en, this message translates to:
  /// **'This firmware can\'t be updated over Wi-Fi.'**
  String get otaNotSupported;

  /// Error header text, includes newline
  ///
  /// In en, this message translates to:
  /// **'Something\nwent wrong'**
  String get wrappedSomethingWentWrong;

  /// No description provided for @screenRecording.
  ///
  /// In en, this message translates to:
  /// **'Screen Recording'**
  String get screenRecording;

  /// Description of on-device processing
  ///
  /// In en, this message translates to:
  /// **'Audio is processed locally. Works offline, more private, but uses more battery.'**
  String get audioProcessedLocally;

  /// Onboarding step title for sign in
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get onboardingSignIn;

  /// Duration in plural days
  ///
  /// In en, this message translates to:
  /// **'{count} days'**
  String timeDaysPlural(int count);

  /// Heading of the card listing memories Omi learned today
  ///
  /// In en, this message translates to:
  /// **'Things I learned today'**
  String get memoryReviewTitle;

  /// Tooltip on the password visibility toggle
  ///
  /// In en, this message translates to:
  /// **'Hide password'**
  String get hidePassword;

  /// Tab title for Omi transcription source option
  ///
  /// In en, this message translates to:
  /// **'Omi'**
  String get transcriptionSourceOmi;

  /// Status text when device is disconnected
  ///
  /// In en, this message translates to:
  /// **'Disconnected'**
  String get disconnected;

  /// Confirmation dialog title for revoking API key
  ///
  /// In en, this message translates to:
  /// **'Revoke API Key?'**
  String get revokeApiKeyQuestion;

  /// No description provided for @detectBrowserBasedMeetings.
  ///
  /// In en, this message translates to:
  /// **'Detect browser-based meetings'**
  String get detectBrowserBasedMeetings;

  /// Error message when delete fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete conversations'**
  String get failedToDeleteConversations;

  /// No description provided for @raybanMetaCapturePhoto.
  ///
  /// In en, this message translates to:
  /// **'Capture Photo'**
  String get raybanMetaCapturePhoto;

  /// Speed description for BLE transfer
  ///
  /// In en, this message translates to:
  /// **'~30 KB/s via BLE'**
  String get bleSpeed;

  /// Placeholder text for conversation prompt field
  ///
  /// In en, this message translates to:
  /// **'You are an awesome app, you will be given transcript and summary of a conversation…'**
  String get conversationPromptPlaceholder;

  /// Description for Google authentication
  ///
  /// In en, this message translates to:
  /// **'Secure authentication via Google Account'**
  String get secureAuthViaGoogleAccount;

  /// Fallback text for share stats when period is unknown
  ///
  /// In en, this message translates to:
  /// **'Omi has:'**
  String get omiHas;

  /// No description provided for @raybanMetaContinue.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get raybanMetaContinue;

  /// Button label to pause recording
  ///
  /// In en, this message translates to:
  /// **'Pause Recording'**
  String get pauseRecording;

  /// Evidence row when there is no evidence from the user at all.
  ///
  /// In en, this message translates to:
  /// **'You haven\'t labeled or confirmed them yet'**
  String get evidenceNothing;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No Activity Yet'**
  String get noActivityYet;

  /// Error when password field is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter your password'**
  String get enterPasswordError;

  /// Title of the confirmation before forgetting a paired device
  ///
  /// In en, this message translates to:
  /// **'Forget Device?'**
  String get forgetDeviceConfirmTitle;

  /// Section title for ratings and reviews
  ///
  /// In en, this message translates to:
  /// **'Ratings & Reviews'**
  String get ratingsAndReviews;

  /// No description provided for @addApiKeyAfterImport.
  ///
  /// In en, this message translates to:
  /// **'You\'ll need to add your own API key after importing'**
  String get addApiKeyAfterImport;

  /// Message when device is already on the latest stable firmware
  ///
  /// In en, this message translates to:
  /// **'You are already on the latest stable version.'**
  String get alreadyOnStableFirmware;

  /// Delete account confirmation
  ///
  /// In en, this message translates to:
  /// **'Are you sure you want to delete your account?'**
  String get deleteAccountConfirm;

  /// Menu item to view recording information
  ///
  /// In en, this message translates to:
  /// **'Recording Info'**
  String get recordingInfo;

  /// Quick reason chip: the summary was inaccurate.
  ///
  /// In en, this message translates to:
  /// **'Inaccurate'**
  String get feedbackReasonSummaryInaccurate;

  /// No description provided for @pendantRecordingTitle.
  ///
  /// In en, this message translates to:
  /// **'Recording on Pendant'**
  String get pendantRecordingTitle;

  /// No description provided for @deleteWhileProcessingMessage.
  ///
  /// In en, this message translates to:
  /// **'This recording is uploaded but Omi is still creating the conversation. If you delete it now and processing fails, it can\'t be recovered. Delete anyway?'**
  String get deleteWhileProcessingMessage;

  /// Dialog title for creating a new API key
  ///
  /// In en, this message translates to:
  /// **'Create New Key'**
  String get createNewKey;

  /// Firmware download failed
  ///
  /// In en, this message translates to:
  /// **'The update couldn\'t be downloaded, and your device wasn\'t changed. Check your internet connection, then try again.'**
  String get firmwareDownloadFailedMessage;

  /// Message shown while tasks are being loaded
  ///
  /// In en, this message translates to:
  /// **'Loading tasks…'**
  String get loadingTasks;

  /// Accessibility label of the up arrow in conversation search
  ///
  /// In en, this message translates to:
  /// **'Previous result'**
  String get previousResult;

  /// Error state
  ///
  /// In en, this message translates to:
  /// **'Couldn’t load your questions.'**
  String get reviewLoadFailed;

  /// No description provided for @onDevice.
  ///
  /// In en, this message translates to:
  /// **'On Device'**
  String get onDevice;

  /// Snackbar message when bluetooth sync is enabled
  ///
  /// In en, this message translates to:
  /// **'Bluetooth sync enabled'**
  String get bluetoothSyncEnabled;

  /// No description provided for @categorySafety.
  ///
  /// In en, this message translates to:
  /// **'Safety'**
  String get categorySafety;

  /// Fallback for unknown location
  ///
  /// In en, this message translates to:
  /// **'Unknown location'**
  String get unknownLocation;

  /// Title of the new-memory sheet
  ///
  /// In en, this message translates to:
  /// **'New Memory'**
  String get newMemoryTitle;

  /// Error message shown when user tries to merge a conversation that is locked or already being merged
  ///
  /// In en, this message translates to:
  /// **'This conversation cannot be merged (locked or already merging)'**
  String get conversationCannotBeMerged;

  /// Description for day summary webhook
  ///
  /// In en, this message translates to:
  /// **'Summary generated'**
  String get summaryGenerated;

  /// Button text to create API key
  ///
  /// In en, this message translates to:
  /// **'Create Key'**
  String get createKey;

  /// No description provided for @letOmiChooseAutomatically.
  ///
  /// In en, this message translates to:
  /// **'Let Omi choose the best app automatically'**
  String get letOmiChooseAutomatically;

  /// Message asking user to restart device after update. {deviceName} is the device name.
  ///
  /// In en, this message translates to:
  /// **'Please restart your {deviceName} to complete the update.'**
  String restartDeviceToComplete(Object deviceName);

  /// Header for goals section
  ///
  /// In en, this message translates to:
  /// **'Goals'**
  String get goals;

  /// Generic error message fallback
  ///
  /// In en, this message translates to:
  /// **'An error occurred'**
  String get wrappedAnErrorOccurred;

  /// Error message when permission check fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Microphone permission: {error}'**
  String failedToCheckMicrophonePermission(String error);

  /// Button text to skip immediate device connection
  ///
  /// In en, this message translates to:
  /// **'Connect Later'**
  String get connectLater;

  /// Subtitle text for shareable image
  ///
  /// In en, this message translates to:
  /// **'remembered by Omi'**
  String get wrappedRememberedByOmi;

  /// No description provided for @fairUseStatusNormal.
  ///
  /// In en, this message translates to:
  /// **'Your usage is within normal limits.'**
  String get fairUseStatusNormal;

  /// No description provided for @includePersonalEventsDescription.
  ///
  /// In en, this message translates to:
  /// **'Include personal events with no attendees'**
  String get includePersonalEventsDescription;

  /// No description provided for @week.
  ///
  /// In en, this message translates to:
  /// **'Week'**
  String get week;

  /// Warning about enabling on incompatible device
  ///
  /// In en, this message translates to:
  /// **'Enabling this will likely cause the app to crash or freeze.'**
  String get willLikelyCrash;

  /// Title for language selection dialog
  ///
  /// In en, this message translates to:
  /// **'Select your primary language'**
  String get selectPrimaryLanguage;

  /// No description provided for @pilotFeaturesDescription.
  ///
  /// In en, this message translates to:
  /// **'These features are tests and no support is guaranteed.'**
  String get pilotFeaturesDescription;

  /// Shortcut to ask Omi a question
  ///
  /// In en, this message translates to:
  /// **'Ask Omi'**
  String get askOmi;

  /// Header for consequences list
  ///
  /// In en, this message translates to:
  /// **'If you cancel:'**
  String get ifYouCancel;

  /// Title for audio route picker bottom sheet
  ///
  /// In en, this message translates to:
  /// **'Audio Output'**
  String get audioOutput;

  /// Marks a learned memory as incorrect (button)
  ///
  /// In en, this message translates to:
  /// **'Wrong'**
  String get memoryReviewWrong;

  /// Error when plan change cannot be scheduled
  ///
  /// In en, this message translates to:
  /// **'Could not schedule plan change. Please try again.'**
  String get couldNotSchedulePlanChange;

  /// The tagged person's voice was found, unnamed, in this many earlier conversations
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Found in 1 earlier conversation} other{Found in {count} earlier conversations}}'**
  String speakerLabelEarlierMatches(int count);

  /// Tutorial step 2 status chip while Omi is actively listening to the question
  ///
  /// In en, this message translates to:
  /// **'Listening…'**
  String get deviceOnboardingListening;

  /// First-run onboarding instruction: why Omi needs a short voice sample and the approximate duration.
  ///
  /// In en, this message translates to:
  /// **'So Omi knows which voice is yours — talk for about 5 seconds about anything.'**
  String get speechProfileEnrollmentPrompt;

  /// No description provided for @mcpServerUrl.
  ///
  /// In en, this message translates to:
  /// **'MCP Server URL'**
  String get mcpServerUrl;

  /// Eyebrow label on a chat memory link block
  ///
  /// In en, this message translates to:
  /// **'Memory'**
  String get chatBlockMemory;

  /// Empty state title when no starred conversations
  ///
  /// In en, this message translates to:
  /// **'No starred conversations'**
  String get noStarredConversations;

  /// No description provided for @syncStatusTooOld.
  ///
  /// In en, this message translates to:
  /// **'Too old to sync — Omi can\'t accept it'**
  String get syncStatusTooOld;

  /// No description provided for @connectedAsUser.
  ///
  /// In en, this message translates to:
  /// **'Connected as user: {userId}'**
  String connectedAsUser(String userId);

  /// No description provided for @phonePageTitle.
  ///
  /// In en, this message translates to:
  /// **'Phone'**
  String get phonePageTitle;

  /// Button to build knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Build Graph'**
  String get buildGraphButton;

  /// No description provided for @issuesCreatedInRepo.
  ///
  /// In en, this message translates to:
  /// **'Issues will be created in your default repository'**
  String get issuesCreatedInRepo;

  /// No description provided for @scopeUserFacts.
  ///
  /// In en, this message translates to:
  /// **'User Facts'**
  String get scopeUserFacts;

  /// Error message when plans cannot load
  ///
  /// In en, this message translates to:
  /// **'Unable to load plans'**
  String get unableToLoadPlans;

  /// Menu item and dialog title for deleting recording
  ///
  /// In en, this message translates to:
  /// **'Delete Recording'**
  String get deleteRecording;

  /// Error message when app deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete app. Please try again later.'**
  String get appDeleteFailed;

  /// Success message after app update
  ///
  /// In en, this message translates to:
  /// **'App updated successfully 🚀'**
  String get addAppUpdatedSuccess;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'Nothing to answer'**
  String get reviewCaughtUpTitle;

  /// Menu item to copy conversation ID to clipboard
  ///
  /// In en, this message translates to:
  /// **'Copy Conversation ID'**
  String get copyConversationId;

  /// No description provided for @helpImproveOmiBySharing.
  ///
  /// In en, this message translates to:
  /// **'Help improve Omi by sharing anonymized analytics data'**
  String get helpImproveOmiBySharing;

  /// Data privacy page banner summarizing encryption and user control
  ///
  /// In en, this message translates to:
  /// **'Your data is secured by default with strong encryption, and you stay in control of how it\'s stored and used.'**
  String get dataEncryptedBanner;

  /// Label for the redo/re-record button on the speech profile page
  ///
  /// In en, this message translates to:
  /// **'Redo'**
  String get redo;

  /// Card on the capture screen opening the OmiGlass update
  ///
  /// In en, this message translates to:
  /// **'Update OmiGlass Firmware'**
  String get updateOmiGlassFirmware;

  /// Message shown after device is unpaired
  ///
  /// In en, this message translates to:
  /// **'Device unpaired. Go to Settings > Bluetooth and forget the device to complete unpairing.'**
  String get deviceUnpairedMessage;

  /// Short speaker-label texts: likely badge, sounds-like question, reject button, carried-over banner, change button, earlier-voice card title and body, confirmed check label, and the Review button (other)
  ///
  /// In en, this message translates to:
  /// **'{part, select, likely{Likely} soundsLike{Sounds like {name}} notPerson{Not {name}} carried{Still {name}. Carried over from your last conversation.} change{Change} alsoTitle{Is this also {name}?} alsoBody{Omi found the same voice in earlier conversations.} confirmed{You confirmed this label} other{Review}}'**
  String speakerLabelText(String part, String name);

  /// Button to sign in with Apple
  ///
  /// In en, this message translates to:
  /// **'Continue with Apple'**
  String get continueWithApple;

  /// Button to acknowledge warning
  ///
  /// In en, this message translates to:
  /// **'I Understand'**
  String get iUnderstand;

  /// Provenance label for an Android capture device
  ///
  /// In en, this message translates to:
  /// **'Android'**
  String get memoryProvenanceAndroid;

  /// Text shown while saving settings
  ///
  /// In en, this message translates to:
  /// **'Saving…'**
  String get saving;

  /// Tutorial step 4 title — configure the device double-tap action
  ///
  /// In en, this message translates to:
  /// **'Customize Double Tap'**
  String get deviceOnboardingDoubleTapTitle;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'All memories are now public'**
  String get allMemoriesPublicResult;

  /// Button that opens the system new-contact form for Omi's number
  ///
  /// In en, this message translates to:
  /// **'Add Omi to Contacts'**
  String get chatAppsAddToContacts;

  /// Abbreviated days label in Wrapped collage
  ///
  /// In en, this message translates to:
  /// **'days'**
  String get wrappedDays;

  /// Error message for invalid JSON
  ///
  /// In en, this message translates to:
  /// **'Invalid JSON'**
  String get invalidJsonError;

  /// Status card: items that need user attention
  ///
  /// In en, this message translates to:
  /// **'{count} recording{count, plural, =1{} other{s}} need attention'**
  String syncCardNeedsAttention(int count);

  /// Instruction text on intro card
  ///
  /// In en, this message translates to:
  /// **'Swipe up to begin'**
  String get wrappedSwipeUpToBegin;

  /// Success message when task was added to a service
  ///
  /// In en, this message translates to:
  /// **'Added to {serviceName}'**
  String addedToService(String serviceName);

  /// No description provided for @advanced.
  ///
  /// In en, this message translates to:
  /// **'Advanced'**
  String get advanced;

  /// No description provided for @autoCreateAndTagNewSpeakers.
  ///
  /// In en, this message translates to:
  /// **'Auto-create and tag new speakers'**
  String get autoCreateAndTagNewSpeakers;

  /// Section title for app capabilities selection
  ///
  /// In en, this message translates to:
  /// **'App Capabilities'**
  String get appCapabilities;

  /// Error when microphone permission is denied
  ///
  /// In en, this message translates to:
  /// **'Microphone permission denied. Please grant permission in System Preferences > Privacy & Security > Microphone.'**
  String get onboardingMicrophoneDenied;

  /// Validation message when user tries to create folder without a name
  ///
  /// In en, this message translates to:
  /// **'Please enter a folder name'**
  String get pleaseEnterFolderName;

  /// Error when checking Bluetooth permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Bluetooth permission: {error}'**
  String onboardingFailedCheckBluetooth(String error);

  /// Dialog title for invalid recording
  ///
  /// In en, this message translates to:
  /// **'Invalid recording detected'**
  String get invalidRecordingDetected;

  /// Title for app analytics section
  ///
  /// In en, this message translates to:
  /// **'App Analytics'**
  String get appAnalytics;

  /// Title of the sheet listing each device recording of one conversation
  ///
  /// In en, this message translates to:
  /// **'Recordings of this conversation'**
  String get captureRecordingsSheetTitle;

  /// Success message after deleting conversations
  ///
  /// In en, this message translates to:
  /// **'Deleted {count} Limitless conversations'**
  String deletedLimitlessConversations(int count);

  /// Error when image selection fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting image: {error}'**
  String addAppErrorSelectingImage(String error);

  /// Neutral label for an unnamed voice when cross-recording speaker resolution is unavailable
  ///
  /// In en, this message translates to:
  /// **'Speaker'**
  String get unnamedSpeakerLabel;

  /// Error message when app creation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create app. Please try again.'**
  String get failedToCreateApp;

  /// Header for plan deprecation notice
  ///
  /// In en, this message translates to:
  /// **'Plan Update'**
  String get planUpdate;

  /// No description provided for @timeout5Minutes.
  ///
  /// In en, this message translates to:
  /// **'5 minutes'**
  String get timeout5Minutes;

  /// Accessibility label for deleting a person's voice sample
  ///
  /// In en, this message translates to:
  /// **'Delete sample'**
  String get deleteSample;

  /// Warning that key won't be shown again
  ///
  /// In en, this message translates to:
  /// **'You will not be able to see it again.'**
  String get willNotSeeAgain;

  /// Time period: This Month
  ///
  /// In en, this message translates to:
  /// **'This Month'**
  String get thisMonth;

  /// No description provided for @enterName.
  ///
  /// In en, this message translates to:
  /// **'Enter name'**
  String get enterName;

  /// Filter chip and provenance label for the current device
  ///
  /// In en, this message translates to:
  /// **'This device'**
  String get memoryThisDevice;

  /// No description provided for @verifiedNumbersDescription.
  ///
  /// In en, this message translates to:
  /// **'When you call someone, they\'ll see this number on their phone'**
  String get verifiedNumbersDescription;

  /// Tutorial step 4 hint shown when the user single-taps instead of double-tapping
  ///
  /// In en, this message translates to:
  /// **'That was a single tap — try tapping twice quickly!'**
  String get deviceOnboardingSingleTapHint;

  /// Countdown for auto-closing snackbar
  ///
  /// In en, this message translates to:
  /// **'Auto-closing in {seconds}s'**
  String autoClosingInSeconds(int seconds);

  /// Pro benefit bullet
  ///
  /// In en, this message translates to:
  /// **'Omi remembers context across every app'**
  String get chatAppsProPerkContext;

  /// Error message for conversation processing failure
  ///
  /// In en, this message translates to:
  /// **'Error while processing conversation. Please try again later.'**
  String get errorProcessingConversation;

  /// No description provided for @profileSettings.
  ///
  /// In en, this message translates to:
  /// **'Profile Settings'**
  String get profileSettings;

  /// Status value for unprocessed recording
  ///
  /// In en, this message translates to:
  /// **'Unprocessed'**
  String get statusUnprocessed;

  /// Message for delete confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'This also deletes its memories, tasks, and audio files.'**
  String get deleteConversationMessage;

  /// Dialog title for cancel subscription
  ///
  /// In en, this message translates to:
  /// **'Cancel Subscription?'**
  String get cancelSubscriptionQuestion;

  /// Continuation of premium minutes message
  ///
  /// In en, this message translates to:
  /// **'for unlimited free transcription.'**
  String get forUnlimitedFreeTranscription;

  /// Usage limit message
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} mins used'**
  String usageLimitMessage(String used, int limit);

  /// No description provided for @categoryPersonalWellness.
  ///
  /// In en, this message translates to:
  /// **'Personal & Lifestyle'**
  String get categoryPersonalWellness;

  /// No description provided for @automaticTranslation.
  ///
  /// In en, this message translates to:
  /// **'Automatic Translation'**
  String get automaticTranslation;

  /// Label for default AI assistant
  ///
  /// In en, this message translates to:
  /// **'Default AI Assistant'**
  String get defaultAiAssistant;

  /// Delete account warning 1
  ///
  /// In en, this message translates to:
  /// **'Your memories and conversations will be erased.'**
  String get allDataErased;

  /// Task due date
  ///
  /// In en, this message translates to:
  /// **'Due {date}'**
  String entityDue(String date);

  /// Secondary row in the feedback sheet that opens the support chat.
  ///
  /// In en, this message translates to:
  /// **'More detail? Chat with us'**
  String get feedbackChatWithUs;

  /// Answer button that opens a field to type a new person's name
  ///
  /// In en, this message translates to:
  /// **'Someone new'**
  String get speakerTagPromptSomeoneNew;

  /// Title for conversation being processed
  ///
  /// In en, this message translates to:
  /// **'In progress'**
  String get inProgress;

  /// No description provided for @raybanMetaCheckAgain.
  ///
  /// In en, this message translates to:
  /// **'Check Again'**
  String get raybanMetaCheckAgain;

  /// No description provided for @fairUseStageNormal.
  ///
  /// In en, this message translates to:
  /// **'Normal'**
  String get fairUseStageNormal;

  /// Pairing title for Limitless device
  ///
  /// In en, this message translates to:
  /// **'Put Limitless in Pairing Mode'**
  String get pairingTitleLimitless;

  /// Label for iOS native speech recognition
  ///
  /// In en, this message translates to:
  /// **'Using Native iOS Speech Recognition'**
  String get usingNativeIosSpeech;

  /// Success message when action item is deleted
  ///
  /// In en, this message translates to:
  /// **'Task deleted successfully'**
  String get actionItemDeletedSuccessfully;

  /// No description provided for @failedToSetLanguage.
  ///
  /// In en, this message translates to:
  /// **'Failed to set language'**
  String get failedToSetLanguage;

  /// Label of the app home URL field when submitting an app with external integration
  ///
  /// In en, this message translates to:
  /// **'App Home URL'**
  String get appHomeUrl;

  /// Label for the app name field
  ///
  /// In en, this message translates to:
  /// **'App Name'**
  String get appNameLabel;

  /// localStorageDisabled label
  ///
  /// In en, this message translates to:
  /// **'Local storage disabled'**
  String get localStorageDisabled;

  /// Button that clears the disabled flag on an app the owner has repaired
  ///
  /// In en, this message translates to:
  /// **'Re-enable'**
  String get appReEnable;

  /// Title shown when data migration fails
  ///
  /// In en, this message translates to:
  /// **'Migration Failed'**
  String get migrationFailed;

  /// Menu item to mark action item as complete
  ///
  /// In en, this message translates to:
  /// **'Mark Complete'**
  String get markComplete;

  /// No description provided for @lastUsedLabel.
  ///
  /// In en, this message translates to:
  /// **'Last Used'**
  String get lastUsedLabel;

  /// Snackbar message for cleared chat
  ///
  /// In en, this message translates to:
  /// **'Chat cleared'**
  String get chatCleared;

  /// Warning message about revoking API key
  ///
  /// In en, this message translates to:
  /// **'Apps using this key lose API access. This can\'t be undone.'**
  String get revokeApiKeyWarning;

  /// Error when checking screen capture permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Screen Capture permission: {error}'**
  String onboardingFailedCheckScreenCapture(String error);

  /// Troubleshooting instructions for watch setup
  ///
  /// In en, this message translates to:
  /// **'Troubleshooting:\n\n1. Ensure Omi is installed on your watch\n2. Open the Omi app on your watch\n3. Look for the permission popup\n4. Tap \"Allow\" when prompted\n5. App on your watch will close - reopen it\n6. Come back and tap \"Continue\" on your iPhone'**
  String get troubleshootingSteps;

  /// Label for location permission
  ///
  /// In en, this message translates to:
  /// **'Location'**
  String get location;

  /// Tip on the WhatsApp sheet
  ///
  /// In en, this message translates to:
  /// **'Telegram and iMessage work today, with the same memories and tasks.'**
  String get chatAppsWhatsAppMeantime;

  /// Label for slider minimum value
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get sliderOff;

  /// Status text while checking firmware version
  ///
  /// In en, this message translates to:
  /// **'Checking firmware version…'**
  String get checkingFirmwareVersion;

  /// Label for the speaker being asked about
  ///
  /// In en, this message translates to:
  /// **'Unknown speaker'**
  String get reviewUnknownSpeaker;

  /// Profession option: Sales
  ///
  /// In en, this message translates to:
  /// **'Sales'**
  String get professionSales;

  /// No description provided for @noRssiDataYet.
  ///
  /// In en, this message translates to:
  /// **'No RSSI data yet'**
  String get noRssiDataYet;

  /// Message when Old list is empty
  ///
  /// In en, this message translates to:
  /// **'✅ No old tasks'**
  String get emptyOldMessage;

  /// Confirmation message for deleting a speech sample
  ///
  /// In en, this message translates to:
  /// **'{name}\'s voice sample is removed. This can\'t be undone.'**
  String deleteSampleConfirmation(String name);

  /// Button text to save the backend URL
  ///
  /// In en, this message translates to:
  /// **'Save URL'**
  String get saveUrlButton;

  /// Error when notification permission is denied
  ///
  /// In en, this message translates to:
  /// **'Notification permission denied. Please grant permission in System Preferences.'**
  String get onboardingNotificationDeniedSystemPrefs;

  /// No description provided for @languageForTranscription.
  ///
  /// In en, this message translates to:
  /// **'Omi uses this language for transcription, summaries, and memories.'**
  String get languageForTranscription;

  /// Label for updated date
  ///
  /// In en, this message translates to:
  /// **'UPDATED'**
  String get updatedLabel;

  /// Tab label for content
  ///
  /// In en, this message translates to:
  /// **'Content'**
  String get content;

  /// No description provided for @phoneCallButton.
  ///
  /// In en, this message translates to:
  /// **'Call'**
  String get phoneCallButton;

  /// Developer settings - exportStartedMayTakeFewSeconds
  ///
  /// In en, this message translates to:
  /// **'Export started. This may take a few seconds…'**
  String get exportStartedMayTakeFewSeconds;

  /// Diagnostics the privacy filter refused to send.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 report held back for privacy} other{{count} reports held back for privacy}}'**
  String dreamReportPrivacyHeld(int count);

  /// Firmware update blocked by low battery
  ///
  /// In en, this message translates to:
  /// **'Battery is at {level}%. Charge your device to at least 15% before updating.'**
  String firmwareBatteryTooLow(int level);

  /// No description provided for @appearance.
  ///
  /// In en, this message translates to:
  /// **'Appearance'**
  String get appearance;

  /// Empty state on the single-day tasks page
  ///
  /// In en, this message translates to:
  /// **'No tasks on {date}'**
  String noTasksOnDate(Object date);

  /// TextField hint on delete feedback step
  ///
  /// In en, this message translates to:
  /// **'Optional — your thoughts help us build a better product.'**
  String get deleteFlowFeedbackHint;

  /// Name of bluetooth transfer method
  ///
  /// In en, this message translates to:
  /// **'Bluetooth'**
  String get bluetooth;

  /// Button that stops an OmiGlass update
  ///
  /// In en, this message translates to:
  /// **'Cancel Update'**
  String get cancelUpdate;

  /// Row subtitle on the sync page for a fully synced recording: emphasises that processing succeeded and a conversation now exists.
  ///
  /// In en, this message translates to:
  /// **'Conversation created'**
  String get syncStatusConversationCreated;

  /// Status when reconnecting to audio
  ///
  /// In en, this message translates to:
  /// **'Reconnecting…'**
  String get reconnecting;

  /// Category label for tasks due today
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get tasksToday;

  /// A count of tasks (recap cards)
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 task} other{{count} tasks}}'**
  String taskCount(int count);

  /// Empty state when no meetings scheduled
  ///
  /// In en, this message translates to:
  /// **'No upcoming meetings'**
  String get noUpcomingMeetings;

  /// Error title when multiple speakers are detected
  ///
  /// In en, this message translates to:
  /// **'Invalid recording detected'**
  String get invalidRecordingMultipleSpeakers;

  /// Title of the screen shown when the app fails to launch
  ///
  /// In en, this message translates to:
  /// **'Omi couldn’t start'**
  String get startupFailedTitle;

  /// Shows count of selected contacts
  ///
  /// In en, this message translates to:
  /// **'{count} selected'**
  String contactsSelectedCount(int count);

  /// Accessibility label of the playback control that jumps forward 10 seconds
  ///
  /// In en, this message translates to:
  /// **'Forward 10 seconds'**
  String get skipForward10Seconds;

  /// Generic no items message
  ///
  /// In en, this message translates to:
  /// **'No items'**
  String get noItems;

  /// No description provided for @timeout30Minutes.
  ///
  /// In en, this message translates to:
  /// **'30 minutes'**
  String get timeout30Minutes;

  /// Success message after signing in
  ///
  /// In en, this message translates to:
  /// **'Sign In Successful!'**
  String get signInSuccess;

  /// Row subtitle for a recording currently being transferred from the Omi device to the phone.
  ///
  /// In en, this message translates to:
  /// **'Downloading from your device'**
  String get syncStatusDownloadingFromDevice;

  /// Menu option to change memory visibility to private
  ///
  /// In en, this message translates to:
  /// **'Make Private'**
  String get makePrivate;

  /// Button label to update action item
  ///
  /// In en, this message translates to:
  /// **'Update'**
  String get update;

  /// Status message shown while generating app icon
  ///
  /// In en, this message translates to:
  /// **'Creating app icon…'**
  String get aiGenCreatingAppIcon;

  /// Short label for intense day in summary
  ///
  /// In en, this message translates to:
  /// **'Intense'**
  String get wrappedIntenseDay;

  /// No description provided for @raybanMetaSkipForNow.
  ///
  /// In en, this message translates to:
  /// **'Skip for Now'**
  String get raybanMetaSkipForNow;

  /// Detail fragment in a disconnect event row: how long reconnecting took (joined with ' · ')
  ///
  /// In en, this message translates to:
  /// **'reconnected in {duration}'**
  String diagnosticsReconnectedIn(String duration);

  /// Dialog description when switching from unlimited plan
  ///
  /// In en, this message translates to:
  /// **'You\'re switching your Unlimited Plan to the {title}.'**
  String planSwitchingDescriptionWithTitle(String title);

  /// Apps: group of chat apps
  ///
  /// In en, this message translates to:
  /// **'Ask Omi with'**
  String get appsAskWith;

  /// Empty state title when search/filter has no results
  ///
  /// In en, this message translates to:
  /// **'No Memories Found'**
  String get noMemoriesFound;

  /// Empty state title when no memories
  ///
  /// In en, this message translates to:
  /// **'No Memories Yet'**
  String get noMemoriesYet;

  /// Error after splitting a recording out of a grouped conversation failed
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t separate. Try again.'**
  String get captureRecordingSeparateFailed;

  /// Label for pinning a memory as baseline
  ///
  /// In en, this message translates to:
  /// **'Pin as Baseline'**
  String get pinAsBaseline;

  /// Section header above the voice-learning switches on the People page
  ///
  /// In en, this message translates to:
  /// **'Voice Recognition'**
  String get voiceRecognitionSettings;

  /// Value shown on a setting that is not available yet
  ///
  /// In en, this message translates to:
  /// **'Coming later'**
  String get chatAppsComingLater;

  /// Label for slider maximum value
  ///
  /// In en, this message translates to:
  /// **'Max'**
  String get sliderMax;

  /// No description provided for @deleteWhileProcessingTitle.
  ///
  /// In en, this message translates to:
  /// **'Still Processing'**
  String get deleteWhileProcessingTitle;

  /// Success message shown when developer mode settings are saved
  ///
  /// In en, this message translates to:
  /// **'Settings saved!'**
  String get devModeSettingsSaved;

  /// No description provided for @fairUseToday.
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get fairUseToday;

  /// No description provided for @exportDataDesc.
  ///
  /// In en, this message translates to:
  /// **'Export conversations to a JSON file'**
  String get exportDataDesc;

  /// Question asking for user's name
  ///
  /// In en, this message translates to:
  /// **'What\'s your name?'**
  String get whatsYourName;

  /// Warning about slower transcription
  ///
  /// In en, this message translates to:
  /// **'On-device transcription may be slower on this device.'**
  String get onDeviceSlower;

  /// No description provided for @categoryProductivityLifestyle.
  ///
  /// In en, this message translates to:
  /// **'Productivity & Lifestyle'**
  String get categoryProductivityLifestyle;

  /// No description provided for @addToYourTaskList.
  ///
  /// In en, this message translates to:
  /// **'Add to your task list?'**
  String get addToYourTaskList;

  /// Caption and accessibility label for a meeting screenshot that has no caption
  ///
  /// In en, this message translates to:
  /// **'Screenshot from this meeting'**
  String get meetingScreenshotFallbackCaption;

  /// How much one kind of evidence raises confidence: slightly.
  ///
  /// In en, this message translates to:
  /// **'Helps a little'**
  String get effectCountsALittle;

  /// Pairing title for Friend Pendant
  ///
  /// In en, this message translates to:
  /// **'Put Friend Pendant in Pairing Mode'**
  String get pairingTitleFriendPendant;

  /// No description provided for @peopleStatsIncomplete.
  ///
  /// In en, this message translates to:
  /// **'Counts may be incomplete.'**
  String get peopleStatsIncomplete;

  /// Empty state text for goals widget
  ///
  /// In en, this message translates to:
  /// **'Tap to add a goal'**
  String get tapToAddGoal;

  /// No description provided for @payment.
  ///
  /// In en, this message translates to:
  /// **'Payment'**
  String get payment;

  /// No description provided for @omiDebugLog.
  ///
  /// In en, this message translates to:
  /// **'Omi debug log'**
  String get omiDebugLog;

  /// No description provided for @showMeetingsMenuBar.
  ///
  /// In en, this message translates to:
  /// **'Show upcoming meetings in menu bar'**
  String get showMeetingsMenuBar;

  /// No description provided for @mostInstalls.
  ///
  /// In en, this message translates to:
  /// **'Most Installs'**
  String get mostInstalls;

  /// No description provided for @chatUsageMessages.
  ///
  /// In en, this message translates to:
  /// **'Chat: {used} / {limit} messages this month'**
  String chatUsageMessages(String used, String limit);

  /// Navigation label for chat page
  ///
  /// In en, this message translates to:
  /// **'Chat'**
  String get chat;

  /// Timeout warning title
  ///
  /// In en, this message translates to:
  /// **'Are you there?'**
  String get areYouThere;

  /// No description provided for @highestRating.
  ///
  /// In en, this message translates to:
  /// **'Highest Rating'**
  String get highestRating;

  /// No description provided for @pleaseSpecify.
  ///
  /// In en, this message translates to:
  /// **'Please specify'**
  String get pleaseSpecify;

  /// Label for staging API environment
  ///
  /// In en, this message translates to:
  /// **'Staging'**
  String get staging;

  /// Cancel reason option
  ///
  /// In en, this message translates to:
  /// **'Battery drain concerns'**
  String get cancelReasonBatteryDrain;

  /// No description provided for @apiKeys.
  ///
  /// In en, this message translates to:
  /// **'API Keys'**
  String get apiKeys;

  /// Success message showing number of conversations created
  ///
  /// In en, this message translates to:
  /// **'{count} conversations created'**
  String conversationsCreated(int count);

  /// Label for training data program
  ///
  /// In en, this message translates to:
  /// **'Training Data Program'**
  String get trainingDataProgram;

  /// Title for custom backend URL page
  ///
  /// In en, this message translates to:
  /// **'Custom Backend URL'**
  String get customBackendUrlTitle;

  /// Step 2: Syncing audio files
  ///
  /// In en, this message translates to:
  /// **'Omi then syncs the audio files with the server'**
  String get omiSyncsAudioFiles;

  /// Answer: the speaker is the user themself
  ///
  /// In en, this message translates to:
  /// **'Me'**
  String get reviewAnswerMe;

  /// Debug & Diagnostics section header
  ///
  /// In en, this message translates to:
  /// **'Debug & Diagnostics'**
  String get debugDiagnostics;

  /// Second half of a reason line, after a middle dot: this person has not appeared in a conversation yet. Lowercase.
  ///
  /// In en, this message translates to:
  /// **'not heard yet'**
  String get confidenceReasonNotHeard;

  /// Double tap action setting
  ///
  /// In en, this message translates to:
  /// **'Double Tap Action'**
  String get doubleTapAction;

  /// Description for show tasks toggle in developer settings
  ///
  /// In en, this message translates to:
  /// **'Show Tasks on homepage'**
  String get showTasksOnHomepage;

  /// Error message when firmware update fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start update: {error}'**
  String failedToStartUpdate(String error);

  /// Quick reason chip: the summary mixed up context.
  ///
  /// In en, this message translates to:
  /// **'Wrong context'**
  String get feedbackReasonSummaryWrongContext;

  /// Validation error when description is empty
  ///
  /// In en, this message translates to:
  /// **'Please provide a valid description'**
  String get pleaseProvideValidDescription;

  /// Notice shown when app submission is rejected
  ///
  /// In en, this message translates to:
  /// **'Your app has been rejected. Please update the app details and resubmit for review.'**
  String get appRejectedNotice;

  /// Action label to delete a downloaded on-device transcription model
  ///
  /// In en, this message translates to:
  /// **'Delete Model'**
  String get deleteOnDeviceModel;

  /// Helper text explaining the difference between app language and speech language
  ///
  /// In en, this message translates to:
  /// **'App Language changes menus and buttons. Primary Language affects how your recordings are transcribed.'**
  String get languageSettingsHelperText;

  /// Message of the confirm dialog for deleting several selected conversations
  ///
  /// In en, this message translates to:
  /// **'This also deletes their memories, tasks, and audio files.'**
  String get deleteConversationsMessage;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Best month'**
  String get usageBestMonth;

  /// Loading state text when app generation is in progress
  ///
  /// In en, this message translates to:
  /// **'Creating…'**
  String get creating;

  /// No description provided for @microphoneAccessDescription.
  ///
  /// In en, this message translates to:
  /// **'Omi needs microphone access to record your conversations and provide transcriptions.'**
  String get microphoneAccessDescription;

  /// Cancel reason option
  ///
  /// In en, this message translates to:
  /// **'Not using it enough'**
  String get cancelReasonNotUsing;

  /// Default description for cringe moment
  ///
  /// In en, this message translates to:
  /// **'We\'ve all been there!'**
  String get wrappedWeveAllBeenThere;

  /// Error when the person tried too often
  ///
  /// In en, this message translates to:
  /// **'Too many tries. Wait a minute and try again.'**
  String get chatAppsProblemRateLimited;

  /// Label for selectable option
  ///
  /// In en, this message translates to:
  /// **'Select'**
  String get selectOption;

  /// Explanation of why language selection matters
  ///
  /// In en, this message translates to:
  /// **'Omi uses this language for transcription, summaries, and memories.'**
  String get languageBenefits;

  /// Developer option to trigger webhook
  ///
  /// In en, this message translates to:
  /// **'Trigger Conversation Created Integration'**
  String get triggerConversationIntegration;

  /// Error message explaining integration setup requirement
  ///
  /// In en, this message translates to:
  /// **'If this is an integration app, make sure the setup is completed.'**
  String get integrationSetupRequired;

  /// Instruction when paused
  ///
  /// In en, this message translates to:
  /// **'Click play to resume or stop to finish'**
  String get clickPlayToResumeOrStop;

  /// No description provided for @disconnectedFrom.
  ///
  /// In en, this message translates to:
  /// **'Disconnected from {appName}'**
  String disconnectedFrom(String appName);

  /// Button label to subscribe to a paid app
  ///
  /// In en, this message translates to:
  /// **'Subscribe'**
  String get subscribe;

  /// Reassurance note on the permissions interstitial
  ///
  /// In en, this message translates to:
  /// **'You can change these anytime in Settings > Permissions'**
  String get permissionsChangeAnytime;

  /// Message shown when Apple Reminders permission is denied
  ///
  /// In en, this message translates to:
  /// **'Please enable Reminders access in Settings to use Apple Reminders'**
  String get enableRemindersAccess;

  /// Placeholder for template dropdown
  ///
  /// In en, this message translates to:
  /// **'Select a provider template…'**
  String get selectProviderTemplate;

  /// Status message during system audio initialization on desktop
  ///
  /// In en, this message translates to:
  /// **'Initialising System Audio'**
  String get initialisingSystemAudio;

  /// No description provided for @excellent.
  ///
  /// In en, this message translates to:
  /// **'Excellent'**
  String get excellent;

  /// Eyebrow label on a chat goal link block
  ///
  /// In en, this message translates to:
  /// **'Goal'**
  String get chatBlockGoal;

  /// Menu option to delete a folder
  ///
  /// In en, this message translates to:
  /// **'Delete Folder'**
  String get deleteFolder;

  /// Error message with specific error details
  ///
  /// In en, this message translates to:
  /// **'Failed to create key: {error}'**
  String failedToCreateKeyWithError(String error);

  /// Whisper model size: small
  ///
  /// In en, this message translates to:
  /// **'Small'**
  String get whisperModelSizeSmall;

  /// Warning to copy key immediately
  ///
  /// In en, this message translates to:
  /// **'Please copy it now and write it down somewhere safe. '**
  String get pleaseCopyKeyNow;

  /// Quiet line under the transcript heading: speaker labels may be inconsistent across the merged recordings of this conversation.
  ///
  /// In en, this message translates to:
  /// **'Speaker labels may not match across the recordings in this conversation.'**
  String get unresolvedSpeakersNotice;

  /// Success message after clearing all memories
  ///
  /// In en, this message translates to:
  /// **'Omi\'s memory about you has been cleared'**
  String get omisMemoryCleared;

  /// Menu item to manage app settings
  ///
  /// In en, this message translates to:
  /// **'Manage App'**
  String get manageApp;

  /// Error showing screen capture permission status
  ///
  /// In en, this message translates to:
  /// **'Screen capture permission status: {status}. Please check System Preferences.'**
  String onboardingScreenCaptureStatusCheckPrefs(String status);

  /// Edit menu item label
  ///
  /// In en, this message translates to:
  /// **'Edit'**
  String get edit;

  /// Button to re-download model
  ///
  /// In en, this message translates to:
  /// **'Re-download'**
  String get redownload;

  /// Eyebrow label on a chat conversation/capture link block
  ///
  /// In en, this message translates to:
  /// **'Conversation'**
  String get chatBlockConversation;

  /// Loading message shown when apps are being loaded
  ///
  /// In en, this message translates to:
  /// **'Loading apps…'**
  String get loadingApps;

  /// Placeholder text for chat prompt field
  ///
  /// In en, this message translates to:
  /// **'You are an awesome app, your job is to respond to the user queries and make them feel good…'**
  String get chatPromptPlaceholder;

  /// Link text for Stripe agreement
  ///
  /// In en, this message translates to:
  /// **'Stripe Connected Account Agreement'**
  String get stripeConnectedAccountAgreement;

  /// Title of the toggle in device settings that controls automatic syncing of offline recordings
  ///
  /// In en, this message translates to:
  /// **'Auto-Sync'**
  String get autoSync;

  /// Developer settings - knowledgeGraphDeletedSuccessfully
  ///
  /// In en, this message translates to:
  /// **'Knowledge Graph deleted successfully'**
  String get knowledgeGraphDeletedSuccessfully;

  /// Privacy page - optInAndOptOutOptions
  ///
  /// In en, this message translates to:
  /// **'Opt-In and Opt-Out Options'**
  String get optInAndOptOutOptions;

  /// Permission title for reading memories
  ///
  /// In en, this message translates to:
  /// **'Read Memories'**
  String get permissionReadMemories;

  /// No description provided for @noSpacesInWorkspace.
  ///
  /// In en, this message translates to:
  /// **'No spaces found in this workspace'**
  String get noSpacesInWorkspace;

  /// Button: merge two profiles into one person (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Yes, Merge'**
  String get reviewYesMerge;

  /// iOS home screen quick action: opens chat in voice mode
  ///
  /// In en, this message translates to:
  /// **'Voice Mode'**
  String get voiceMode;

  /// No description provided for @fairUseStageThrottle.
  ///
  /// In en, this message translates to:
  /// **'Throttled'**
  String get fairUseStageThrottle;

  /// Ask: confirm before deleting a past chat
  ///
  /// In en, this message translates to:
  /// **'Delete this chat?'**
  String get deleteChatQuestion;

  /// No description provided for @failedToGetCallToken.
  ///
  /// In en, this message translates to:
  /// **'Failed to get call token. Verify your phone number first.'**
  String get failedToGetCallToken;

  /// Title for time picker dialog
  ///
  /// In en, this message translates to:
  /// **'Select Time'**
  String get selectTime;

  /// Dialog title for SD card processing
  ///
  /// In en, this message translates to:
  /// **'SD Card Processing'**
  String get sdCardProcessing;

  /// No description provided for @errorConnectingRayBanMeta.
  ///
  /// In en, this message translates to:
  /// **'Error connecting to Ray-Ban Meta: {error}'**
  String errorConnectingRayBanMeta(String error);

  /// No description provided for @couldNotLoadImportHistory.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load import history'**
  String get couldNotLoadImportHistory;

  /// No description provided for @noApiKeysFound.
  ///
  /// In en, this message translates to:
  /// **'No API keys found. Create one to get started.'**
  String get noApiKeysFound;

  /// Heading of the notice shown on an app the backend has automatically disabled
  ///
  /// In en, this message translates to:
  /// **'This app is disabled and cannot be installed.'**
  String get appDisabledTitle;

  /// No description provided for @syncStatusBackedUp.
  ///
  /// In en, this message translates to:
  /// **'Backed up'**
  String get syncStatusBackedUp;

  /// Answer chip on the voice suggestion card: the voice is the user (Title Case).
  ///
  /// In en, this message translates to:
  /// **'That\'s Me'**
  String get speakerTagPromptThatsMeAction;

  /// Compact duration in hours and minutes
  ///
  /// In en, this message translates to:
  /// **'{hours}h {mins}m'**
  String timeCompactHoursAndMins(int hours, int mins);

  /// Label for chat prompt text field
  ///
  /// In en, this message translates to:
  /// **'Chat Prompt'**
  String get chatPrompt;

  /// Sample text synthesized when previewing an assistant voice
  ///
  /// In en, this message translates to:
  /// **'Hi, I\'m Omi. This is my voice.'**
  String get voicePreviewSample;

  /// Message shown when changes are saved
  ///
  /// In en, this message translates to:
  /// **'Saved'**
  String get saved;

  /// Button to request permission
  ///
  /// In en, this message translates to:
  /// **'Grant Permission'**
  String get grantPermissionButton;

  /// Subscription section title
  ///
  /// In en, this message translates to:
  /// **'Subscription'**
  String get subscription;

  /// No description provided for @capabilityFeatured.
  ///
  /// In en, this message translates to:
  /// **'Featured'**
  String get capabilityFeatured;

  /// Title for PDF conversation export document
  ///
  /// In en, this message translates to:
  /// **'Conversation Export'**
  String get pdfConversationExport;

  /// Placeholder for unknown value
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get unknown;

  /// No description provided for @yourMeetings.
  ///
  /// In en, this message translates to:
  /// **'Your Meetings'**
  String get yourMeetings;

  /// Loading message shown while uploading voice profile
  ///
  /// In en, this message translates to:
  /// **'Uploading your voice profile…'**
  String get uploadingVoiceProfile;

  /// No description provided for @apiUrl.
  ///
  /// In en, this message translates to:
  /// **'API URL'**
  String get apiUrl;

  /// Report dialog title
  ///
  /// In en, this message translates to:
  /// **'Report Message'**
  String get reportMessage;

  /// Label for password input field
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get passwordLabel;

  /// Description for deleting all memories
  ///
  /// In en, this message translates to:
  /// **'Permanently remove all memories from Omi'**
  String get permanentlyRemoveAllMemories;

  /// Warning about transcription quality
  ///
  /// In en, this message translates to:
  /// **'Transcription will be significantly slower and less accurate.'**
  String get transcriptionSlowerLessAccurate;

  /// Filter option
  ///
  /// In en, this message translates to:
  /// **'Manual'**
  String get filterManual;

  /// Button text to keep current plan
  ///
  /// In en, this message translates to:
  /// **'Keep My Plan'**
  String get keepMyPlan;

  /// Question about age range
  ///
  /// In en, this message translates to:
  /// **'3. What\'s your age range?'**
  String get setupQuestionAge;

  /// Validation error when external integration selected but no trigger event
  ///
  /// In en, this message translates to:
  /// **'Please select a trigger event for your app'**
  String get addAppSelectTriggerEvent;

  /// No description provided for @defaultWorkspace.
  ///
  /// In en, this message translates to:
  /// **'Default Workspace'**
  String get defaultWorkspace;

  /// Error message when updating app status fails
  ///
  /// In en, this message translates to:
  /// **'An error occurred while updating the app status.'**
  String get errorUpdatingAppStatus;

  /// No description provided for @invalidJsonConfig.
  ///
  /// In en, this message translates to:
  /// **'Invalid JSON configuration'**
  String get invalidJsonConfig;

  /// Description for transcription diagnostics
  ///
  /// In en, this message translates to:
  /// **'Detailed diagnostic messages'**
  String get detailedDiagnosticMessages;

  /// Snackbar message during merge
  ///
  /// In en, this message translates to:
  /// **'Merging in background. This may take a moment.'**
  String get mergingInBackground;

  /// No description provided for @setDefaultApp.
  ///
  /// In en, this message translates to:
  /// **'Set Default App'**
  String get setDefaultApp;

  /// No description provided for @authorizeOmiForTasks.
  ///
  /// In en, this message translates to:
  /// **'You\'ll need to authorize Omi to create tasks in your {appName} account. This will open your browser for authentication.'**
  String authorizeOmiForTasks(String appName);

  /// Menu item that reviews people Omi is unsure about for deletion (Title Case, one-character ellipsis because it opens a review).
  ///
  /// In en, this message translates to:
  /// **'Clean Up…'**
  String get cleanUpEllipsis;

  /// Menu option to add a new task
  ///
  /// In en, this message translates to:
  /// **'Add Task'**
  String get addTask;

  /// No description provided for @getCreative.
  ///
  /// In en, this message translates to:
  /// **'Get Creative'**
  String get getCreative;

  /// Error when another device recording of the conversation could not be loaded
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t open this recording.'**
  String get captureRecordingOpenFailed;

  /// Message when To Do list is empty
  ///
  /// In en, this message translates to:
  /// **'🎉 All caught up!\nNo pending tasks'**
  String get emptyTodoMessage;

  /// Onboarding setup page title
  ///
  /// In en, this message translates to:
  /// **'Setting up your Omi'**
  String get onboardingSetupTitle;

  /// Share stats period: All Time
  ///
  /// In en, this message translates to:
  /// **'So far, Omi has:'**
  String get sharePeriodAllTime;

  /// Title for dialog explaining that conversations are translated
  ///
  /// In en, this message translates to:
  /// **'Translation Notice'**
  String get translationNotice;

  /// No description provided for @captureRecordingError.
  ///
  /// In en, this message translates to:
  /// **'An error occurred during recording: {error}'**
  String captureRecordingError(String error);

  /// No description provided for @downloadAudio.
  ///
  /// In en, this message translates to:
  /// **'Download Audio'**
  String get downloadAudio;

  /// Accessibility label of a speaker avatar/name in a transcript; opens the sheet to name the speaker
  ///
  /// In en, this message translates to:
  /// **'Identify speaker'**
  String get identifySpeaker;

  /// Button label to view transcript
  ///
  /// In en, this message translates to:
  /// **'View Transcript'**
  String get viewTranscript;

  /// Action to make all memories public
  ///
  /// In en, this message translates to:
  /// **'Make All Memories Public'**
  String get makeAllMemoriesPublic;

  /// No description provided for @xTwitter.
  ///
  /// In en, this message translates to:
  /// **'X (Twitter)'**
  String get xTwitter;

  /// Notification frequency level - off
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get frequencyOff;

  /// Title for the API environment switcher in developer settings
  ///
  /// In en, this message translates to:
  /// **'API Environment'**
  String get apiEnvironment;

  /// Shown on the homepage processing card after ~2 minutes with a Retry action (#5481).
  ///
  /// In en, this message translates to:
  /// **'Still working — this is taking longer than usual.'**
  String get processingTakingLonger;

  /// Title of the firmware update failed state
  ///
  /// In en, this message translates to:
  /// **'Update Failed'**
  String get firmwareUpdateFailedTitle;

  /// Daily summary detail - unresolvedQuestions
  ///
  /// In en, this message translates to:
  /// **'Unresolved Questions'**
  String get unresolvedQuestions;

  /// Noun used in the copy confirmation, e.g. 'Message copied'
  ///
  /// In en, this message translates to:
  /// **'Message'**
  String get chatAppsMessage;

  /// Label for a run the user started with Run Now.
  ///
  /// In en, this message translates to:
  /// **'Manual'**
  String get dreamReportManual;

  /// No description provided for @enterSttHttpEndpoint.
  ///
  /// In en, this message translates to:
  /// **'Enter your STT HTTP endpoint'**
  String get enterSttHttpEndpoint;

  /// Header text for firmware update checklist
  ///
  /// In en, this message translates to:
  /// **'Before Update, Make Sure:'**
  String get beforeUpdateMakeSure;

  /// Status when transcription WebSocket is reconnecting
  ///
  /// In en, this message translates to:
  /// **'Reconnecting transcription…'**
  String get transcriptionReconnecting;

  /// Device name label
  ///
  /// In en, this message translates to:
  /// **'Device Name'**
  String get deviceName;

  /// No description provided for @neoSubtitle.
  ///
  /// In en, this message translates to:
  /// **'{count} questions per month'**
  String neoSubtitle(int count);

  /// No description provided for @chatUsageProgress.
  ///
  /// In en, this message translates to:
  /// **'{used} / {limit} used'**
  String chatUsageProgress(String used, String limit);

  /// Message when user tries to submit an unchanged review
  ///
  /// In en, this message translates to:
  /// **'No changes in review to update.'**
  String get noChangesInReview;

  /// Filter option to show all memories
  ///
  /// In en, this message translates to:
  /// **'All Memories'**
  String get allMemories;

  /// Instructions for granting microphone permission
  ///
  /// In en, this message translates to:
  /// **'We need microphone permission.\n\n1. Tap \"Grant Permission\"\n2. Allow on your iPhone\n3. Watch app will close\n4. Reopen and tap \"Continue\"'**
  String get needMicrophonePermission;

  /// Instruction to user during speech profile recording
  ///
  /// In en, this message translates to:
  /// **'Keep speaking until you get 100%.'**
  String get keepSpeakingUntil100;

  /// No description provided for @singleLanguageModeInfo.
  ///
  /// In en, this message translates to:
  /// **'Single Language Mode is enabled. Translation is disabled for higher accuracy.'**
  String get singleLanguageModeInfo;

  /// Warning message for irreversible actions
  ///
  /// In en, this message translates to:
  /// **'This cannot be undone.'**
  String get thisCannotBeUndone;

  /// Skip button text for setup questions
  ///
  /// In en, this message translates to:
  /// **'Skip, I don\'t want to help :C'**
  String get setupSkipHelp;

  /// Voice card answer to 'Is this <name>?': no, and opens the picker to say who it is (or That's Me / Not a Person).
  ///
  /// In en, this message translates to:
  /// **'No…'**
  String get speakerTagPromptNoAction;

  /// Message shown when a value is copied
  ///
  /// In en, this message translates to:
  /// **'{label} copied'**
  String labelCopied(String label);

  /// Error message when device switch fails
  ///
  /// In en, this message translates to:
  /// **'Error switching audio device: {error}'**
  String errorSwitchingAudioDevice(String error);

  /// Remembering stat title
  ///
  /// In en, this message translates to:
  /// **'Remembering'**
  String get remembering;

  /// Description explaining which apps can access user data
  ///
  /// In en, this message translates to:
  /// **'The following installed apps have external integrations and can access your data, such as conversations and memories.'**
  String get externalAppAccessDescription;

  /// Preferences section title
  ///
  /// In en, this message translates to:
  /// **'Preferences'**
  String get preferences;

  /// Short label for fun day in summary
  ///
  /// In en, this message translates to:
  /// **'Fun'**
  String get wrappedFunDay;

  /// A missing piece of evidence (a voice sample) is required to reach the Confirmed level.
  ///
  /// In en, this message translates to:
  /// **'Needed for Confirmed'**
  String get effectNeeded;

  /// Notification body prompting user to share conversation summary
  ///
  /// In en, this message translates to:
  /// **'You just had an important convo. Tap to share the summary with others.'**
  String get importantConversationBody;

  /// Row menu item that explains a person's confidence level; level is Confirmed, Likely or Unverified (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Why {level}?'**
  String whyConfidenceMenu(String level);

  /// Error message when command key is not pressed
  ///
  /// In en, this message translates to:
  /// **'⌘ required'**
  String get cmdRequired;

  /// Badge label indicating setup is completed
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get completed;

  /// Output consequence for Always mode without connected headphones
  ///
  /// In en, this message translates to:
  /// **'Plays out loud through the phone speaker.'**
  String get deviceOnboardingVoiceReplyStatusAlwaysSpeaker;

  /// This kind of evidence lowers confidence.
  ///
  /// In en, this message translates to:
  /// **'Hurts'**
  String get effectCountsAgainst;

  /// Search tile and result section for daily recaps
  ///
  /// In en, this message translates to:
  /// **'Recaps'**
  String get recaps;

  /// Title of the confirm shown before a private conversation is made shareable by link
  ///
  /// In en, this message translates to:
  /// **'Share Conversation?'**
  String get shareConversationQuestion;

  /// Success message when action items are copied
  ///
  /// In en, this message translates to:
  /// **'Tasks copied to clipboard'**
  String get actionItemsCopiedToClipboard;

  /// No description provided for @appleHealthManageNote.
  ///
  /// In en, this message translates to:
  /// **'Omi accesses Apple Health through Apple\'s HealthKit framework. You can revoke access anytime in iOS Settings.'**
  String get appleHealthManageNote;

  /// Loading message when adding task to a service
  ///
  /// In en, this message translates to:
  /// **'Adding to {serviceName}…'**
  String addingToService(String serviceName);

  /// Help banner title
  ///
  /// In en, this message translates to:
  /// **'Need help getting started?'**
  String get needHelpGettingStarted;

  /// No description provided for @thanksForAuthorizing.
  ///
  /// In en, this message translates to:
  /// **'Thanks for authorizing!'**
  String get thanksForAuthorizing;

  /// Settings section title for assistant voice
  ///
  /// In en, this message translates to:
  /// **'Voice'**
  String get assistantVoiceSettingsTitle;

  /// cloudStorageDisabled label
  ///
  /// In en, this message translates to:
  /// **'Cloud storage disabled'**
  String get cloudStorageDisabled;

  /// Accessibility label of the play button for a voice clip
  ///
  /// In en, this message translates to:
  /// **'Play clip'**
  String get reviewPlayClip;

  /// Settings label for storing audio on cloud
  ///
  /// In en, this message translates to:
  /// **'Store Audio on Cloud'**
  String get storeAudioOnCloud;

  /// No description provided for @syncStatusBackingUp.
  ///
  /// In en, this message translates to:
  /// **'Syncing…'**
  String get syncStatusBackingUp;

  /// Filter chip and group header on the People list: people the user pinned (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Pinned'**
  String get peopleFilterPinned;

  /// No description provided for @setAsDefaultSuccess.
  ///
  /// In en, this message translates to:
  /// **'{appName} set as default summarization app'**
  String setAsDefaultSuccess(String appName);

  /// Validation error when the GitHub repository field is empty while submitting an app
  ///
  /// In en, this message translates to:
  /// **'GitHub repository URL is required'**
  String get githubRepositoryUrlRequired;

  /// No description provided for @microphoneAccess.
  ///
  /// In en, this message translates to:
  /// **'Microphone Access'**
  String get microphoneAccess;

  /// Button text to cancel subscription
  ///
  /// In en, this message translates to:
  /// **'Cancel Subscription'**
  String get cancelSubscriptionButton;

  /// No description provided for @signal.
  ///
  /// In en, this message translates to:
  /// **'Signal'**
  String get signal;

  /// Error message when Asana authentication fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Asana. Please try again.'**
  String get failedToConnectAsanaRetry;

  /// Message explaining to copy the key now as it won't be shown again
  ///
  /// In en, this message translates to:
  /// **'Your new key has been created. Please copy it now. You will not be able to see it again.'**
  String get keyCreatedMessage;

  /// Subtitle for the auto-remove toggle showing the retention window
  ///
  /// In en, this message translates to:
  /// **'Synced copies deleted after {days} days'**
  String autoRemoveSyncedCopiesDays(int days);

  /// Label for most embarrassing/cringe moment
  ///
  /// In en, this message translates to:
  /// **'Most Cringe'**
  String get wrappedMostCringeMoment;

  /// Title of the sheet listing the steps Omi took to answer a chat message
  ///
  /// In en, this message translates to:
  /// **'Activity'**
  String get activity;

  /// No description provided for @calendarSettings.
  ///
  /// In en, this message translates to:
  /// **'Calendar settings'**
  String get calendarSettings;

  /// Label above the comment field in the chat feedback sheet
  ///
  /// In en, this message translates to:
  /// **'Additional feedback (optional)'**
  String get additionalFeedbackOptional;

  /// No description provided for @phoneAllow.
  ///
  /// In en, this message translates to:
  /// **'Allow'**
  String get phoneAllow;

  /// Message when no device is connected and phone mic will be used
  ///
  /// In en, this message translates to:
  /// **'No device connected. Will use phone microphone.'**
  String get noDeviceConnectedUseMic;

  /// Instructions for completing Stripe onboarding
  ///
  /// In en, this message translates to:
  /// **'Please complete the Stripe onboarding process in your browser. This page will automatically update once completed.'**
  String get stripeOnboardingInstructions;

  /// Available disk space
  ///
  /// In en, this message translates to:
  /// **'Available Space: {space}'**
  String availableSpaceWithValue(String space);

  /// Section header for conversation details
  ///
  /// In en, this message translates to:
  /// **'Conversation Details'**
  String get conversationDetails;

  /// Default description for funniest moment
  ///
  /// In en, this message translates to:
  /// **'You had some funny moments this year!'**
  String get wrappedYouHadFunnyMoments;

  /// No description provided for @actionReadConversations.
  ///
  /// In en, this message translates to:
  /// **'Read conversations'**
  String get actionReadConversations;

  /// Question under an audio clip; {name} is a person's name
  ///
  /// In en, this message translates to:
  /// **'Is this {name}?'**
  String speakerTagPromptIsThisPerson(String name);

  /// Button text to open app settings
  ///
  /// In en, this message translates to:
  /// **'Open Settings'**
  String get openSettings;

  /// Text indicating on-device is always available
  ///
  /// In en, this message translates to:
  /// **'always available.'**
  String get alwaysAvailable;

  /// Filter for apps with 1 or more stars
  ///
  /// In en, this message translates to:
  /// **'1+ Stars'**
  String get rating1PlusStars;

  /// Pause/Resume action
  ///
  /// In en, this message translates to:
  /// **'Pause/Resume'**
  String get pauseResume;

  /// No description provided for @conversationDeleted.
  ///
  /// In en, this message translates to:
  /// **'Conversation deleted'**
  String get conversationDeleted;

  /// Confirms a learned memory is correct (button)
  ///
  /// In en, this message translates to:
  /// **'Right'**
  String get memoryReviewRight;

  /// No description provided for @deleteGoal.
  ///
  /// In en, this message translates to:
  /// **'Delete Goal'**
  String get deleteGoal;

  /// No description provided for @youtube.
  ///
  /// In en, this message translates to:
  /// **'YouTube'**
  String get youtube;

  /// Title for a conversation without a title
  ///
  /// In en, this message translates to:
  /// **'Untitled Conversation'**
  String get untitledConversation;

  /// Usage page title
  ///
  /// In en, this message translates to:
  /// **'Your Omi Insights'**
  String get yourOmiInsights;

  /// App bar title for comparing transcripts from different services
  ///
  /// In en, this message translates to:
  /// **'Compare Transcripts'**
  String get compareTranscripts;

  /// Button label that pauses audio playback
  ///
  /// In en, this message translates to:
  /// **'Pause'**
  String get pause;

  /// Success message when Google Calendar OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Google!'**
  String get successfullyConnectedGoogle;

  /// Message showing plan renewal date
  ///
  /// In en, this message translates to:
  /// **'Your plan renews on {date}.'**
  String planRenewsOn(String date);

  /// Button that opens a chat app; app is a brand name
  ///
  /// In en, this message translates to:
  /// **'Open {app}'**
  String chatAppsOpenApp(String app);

  /// Description text for daily summary section
  ///
  /// In en, this message translates to:
  /// **'Get a personalized summary of your day\'s conversations delivered as a notification.'**
  String get dailySummaryDescription;

  /// Count of photos in a conversation
  ///
  /// In en, this message translates to:
  /// **'{count} photos'**
  String conversationPhotosCount(int count);

  /// Title shown when an audio recording fails to load in the conversation player
  ///
  /// In en, this message translates to:
  /// **'Error loading audio'**
  String get errorLoadingAudio;

  /// Error when file access fails
  ///
  /// In en, this message translates to:
  /// **'Could not access the selected file'**
  String get couldNotAccessFile;

  /// Error message when deleting graph fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete graph: {error}'**
  String deleteGraphFailed(String error);

  /// Accessibility hint: tapping the card opens more context
  ///
  /// In en, this message translates to:
  /// **'Opens details'**
  String get reviewOpenDetailsHint;

  /// No description provided for @conversationTimeoutDesc.
  ///
  /// In en, this message translates to:
  /// **'Choose how long to wait in silence before automatically ending a conversation:'**
  String get conversationTimeoutDesc;

  /// JSON configuration placeholder hint text in transcription settings
  ///
  /// In en, this message translates to:
  /// **'Paste your JSON configuration here…'**
  String get transcriptionJsonPlaceholder;

  /// Loading state message while fetching app capabilities
  ///
  /// In en, this message translates to:
  /// **'Loading capabilities…'**
  String get loadingCapabilities;

  /// Status label when payment method is active
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get activeStatus;

  /// No description provided for @noDailyRecapsYet.
  ///
  /// In en, this message translates to:
  /// **'No daily recaps yet'**
  String get noDailyRecapsYet;

  /// No description provided for @wouldLikePermission.
  ///
  /// In en, this message translates to:
  /// **'We\'d like your permission to save your voice recordings. Here\'s why:'**
  String get wouldLikePermission;

  /// Header above recommended action items on a chat conversation link block
  ///
  /// In en, this message translates to:
  /// **'Recommended next steps'**
  String get chatBlockRecommendedNextSteps;

  /// Empty state message for search with no results
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search terms'**
  String get tryAdjustingSearchTerms;

  /// No description provided for @connectOmiWithAI.
  ///
  /// In en, this message translates to:
  /// **'Connect Omi with AI assistants'**
  String get connectOmiWithAI;

  /// Description for delivery time setting
  ///
  /// In en, this message translates to:
  /// **'When to receive your daily summary'**
  String get whenToReceiveDailySummary;

  /// Status card: pending recordings count
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 recording ready to sync} other{{count} recordings ready to sync}}'**
  String syncCardReadyCount(int count);

  /// Label for API key display section
  ///
  /// In en, this message translates to:
  /// **'YOUR API KEY'**
  String get yourApiKey;

  /// No description provided for @failedToLoadRepos.
  ///
  /// In en, this message translates to:
  /// **'Failed to load repositories: {error}'**
  String failedToLoadRepos(String error);

  /// Loading text when syncing messages
  ///
  /// In en, this message translates to:
  /// **'Syncing messages with server…'**
  String get syncingMessages;

  /// Error message when no rating selected
  ///
  /// In en, this message translates to:
  /// **'Please select a rating'**
  String get pleaseSelectARating;

  /// No description provided for @suggestedTemplates.
  ///
  /// In en, this message translates to:
  /// **'Suggested Templates'**
  String get suggestedTemplates;

  /// Dialog title asking to confirm app update
  ///
  /// In en, this message translates to:
  /// **'Update App?'**
  String get updateAppQuestion;

  /// Description for off notification frequency
  ///
  /// In en, this message translates to:
  /// **'No proactive notifications'**
  String get frequencyDescOff;

  /// No description provided for @triggerAudioBytes.
  ///
  /// In en, this message translates to:
  /// **'Audio Bytes'**
  String get triggerAudioBytes;

  /// Clear chat confirmation text
  ///
  /// In en, this message translates to:
  /// **'Clear this chat? This can\'t be undone.'**
  String get confirmClearChat;

  /// Data privacy setting
  ///
  /// In en, this message translates to:
  /// **'Data Privacy'**
  String get dataPrivacy;

  /// Empty state description for recordings
  ///
  /// In en, this message translates to:
  /// **'Audio from your Omi device will appear here'**
  String get audioFromOmiWillAppearHere;

  /// Label for duration in details
  ///
  /// In en, this message translates to:
  /// **'Duration'**
  String get durationLabel;

  /// No description provided for @deviceOnboardingAllSetTitle.
  ///
  /// In en, this message translates to:
  /// **'You\'re All Set'**
  String get deviceOnboardingAllSetTitle;

  /// Error when selecting images fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting images: {error}'**
  String msgSelectImagesError(String error);

  /// Evidence row: the user picked this person on a suggestion card.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Picked in 1 suggestion} other{Picked in {count} suggestions}}'**
  String evidenceCardPicks(int count);

  /// Description for lost connection
  ///
  /// In en, this message translates to:
  /// **'The connection was interrupted. Please check your internet connection and try again.'**
  String get connectionLostDesc;

  /// No description provided for @defaultLabel.
  ///
  /// In en, this message translates to:
  /// **'Default'**
  String get defaultLabel;

  /// No description provided for @raybanMetaAllowCamera.
  ///
  /// In en, this message translates to:
  /// **'Allow Camera on Glasses'**
  String get raybanMetaAllowCamera;

  /// Validation error when only proactive notification capability is selected
  ///
  /// In en, this message translates to:
  /// **'Please select one more core capability for your app to proceed'**
  String get addAppSelectCoreCapability;

  /// Empty state text for manual category
  ///
  /// In en, this message translates to:
  /// **'No manual memories yet'**
  String get noManualMemories;

  /// Label for delivery time setting
  ///
  /// In en, this message translates to:
  /// **'Delivery Time'**
  String get deliveryTime;

  /// No description provided for @defaultProjectOptional.
  ///
  /// In en, this message translates to:
  /// **'Default Project (Optional)'**
  String get defaultProjectOptional;

  /// Error message when audio bytes webhook URL is invalid in developer settings
  ///
  /// In en, this message translates to:
  /// **'Invalid audio bytes webhook URL'**
  String get devModeInvalidAudioBytesWebhookUrl;

  /// Settings row and sheet title: voices the user marked Not a Person (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Ignored Voices'**
  String get ignoredVoicesTitle;

  /// Tooltip of the button that reloads an MCP app's manifest
  ///
  /// In en, this message translates to:
  /// **'Refresh manifest'**
  String get refreshManifest;

  /// Device Diagnostics section title for the live connection rows
  ///
  /// In en, this message translates to:
  /// **'Right Now'**
  String get diagnosticsRightNow;

  /// Row label: due date
  ///
  /// In en, this message translates to:
  /// **'Due'**
  String get reviewDue;

  /// Button to resume Transcribe Later capture after muting
  ///
  /// In en, this message translates to:
  /// **'Unmute'**
  String get unmute;

  /// No description provided for @recordingsDeleted.
  ///
  /// In en, this message translates to:
  /// **'Recordings deleted.'**
  String get recordingsDeleted;

  /// Error message when folder deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete folder'**
  String get failedToDeleteFolder;

  /// Answer chip that opens the full list of choices
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get reviewAnswerOther;

  /// No description provided for @exportedConversations.
  ///
  /// In en, this message translates to:
  /// **'Exported Conversations from Omi'**
  String get exportedConversations;

  /// Link text for Privacy Policy
  ///
  /// In en, this message translates to:
  /// **'Privacy Policy'**
  String get privacyPolicy;

  /// Button text to edit an existing reply
  ///
  /// In en, this message translates to:
  /// **'Edit Reply'**
  String get editReply;

  /// Combined description of app access and trigger
  ///
  /// In en, this message translates to:
  /// **'{accessDescription} and is {triggerDescription}.'**
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription);

  /// No description provided for @errorSaving.
  ///
  /// In en, this message translates to:
  /// **'Error saving: {error}'**
  String errorSaving(String error);

  /// Device Diagnostics row title; the value is how long the device has been connected
  ///
  /// In en, this message translates to:
  /// **'Connected for'**
  String get diagnosticsConnectedFor;

  /// No description provided for @callStateConnecting.
  ///
  /// In en, this message translates to:
  /// **'Connecting…'**
  String get callStateConnecting;

  /// Error message when sharing fails
  ///
  /// In en, this message translates to:
  /// **'Conversation URL could not be shared.'**
  String get conversationUrlNotShared;

  /// Error description for recording being too short
  ///
  /// In en, this message translates to:
  /// **'There is not enough speech detected. Please speak more and try again.'**
  String get tooShortDesc;

  /// Error toast when sharing a daily recap fails
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t share the recap'**
  String get failedToShareRecap;

  /// No description provided for @billingMonthly.
  ///
  /// In en, this message translates to:
  /// **'Monthly'**
  String get billingMonthly;

  /// No description provided for @developingLogic.
  ///
  /// In en, this message translates to:
  /// **'Developing logic'**
  String get developingLogic;

  /// No description provided for @phoneContinue.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get phoneContinue;

  /// Success message when GitHub OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to GitHub!'**
  String get successfullyConnectedGitHub;

  /// Error message when review submission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to submit review. Please try again.'**
  String get failedToSubmitReview;

  /// No description provided for @anyoneCanDiscover.
  ///
  /// In en, this message translates to:
  /// **'Anyone can discover your app'**
  String get anyoneCanDiscover;

  /// Dialog title when the connected device has no SD-card offline sync
  ///
  /// In en, this message translates to:
  /// **'Offline Sync unavailable'**
  String get v2Undetected;

  /// Usage location option: IRL Events
  ///
  /// In en, this message translates to:
  /// **'IRL Events'**
  String get usageIrlEvents;

  /// Hint text for conversation prompt field
  ///
  /// In en, this message translates to:
  /// **'e.g., Extract tasks, decisions made, and key takeaways from the provided conversation.'**
  String get conversationPromptHint;

  /// No description provided for @openProviderDocs.
  ///
  /// In en, this message translates to:
  /// **'Open Documentation'**
  String get openProviderDocs;

  /// No description provided for @showMeetingsInMenuBar.
  ///
  /// In en, this message translates to:
  /// **'Show Meetings in Menu Bar'**
  String get showMeetingsInMenuBar;

  /// View plans button
  ///
  /// In en, this message translates to:
  /// **'View Plans & Usage'**
  String get viewPlansAndUsage;

  /// Subtitle describing the purpose of the create app page
  ///
  /// In en, this message translates to:
  /// **'Build and submit your custom Omi app'**
  String get buildSubmitCustomOmiApp;

  /// Error message when Google status refresh fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh Google connection status.'**
  String get failedToRefreshGoogleStatus;

  /// Feedback subtitle for too expensive
  ///
  /// In en, this message translates to:
  /// **'Your feedback helps us find the right balance.'**
  String get feedbackSubtitleTooExpensive;

  /// Button to complete onboarding and start using the app
  ///
  /// In en, this message translates to:
  /// **'Start Using Omi'**
  String get startUsingOmi;

  /// Section label for names and terms the agent added to the user's vocabulary.
  ///
  /// In en, this message translates to:
  /// **'Words it learned'**
  String get dreamReportLearnedWords;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'Task created'**
  String get actionItemCreated;

  /// No description provided for @exportAllConversationsToJson.
  ///
  /// In en, this message translates to:
  /// **'Export all your conversations to a JSON file.'**
  String get exportAllConversationsToJson;

  /// Empty state message for connectivity issues
  ///
  /// In en, this message translates to:
  /// **'Please check your internet connection and try again'**
  String get pleaseCheckInternetConnectionAndTryAgain;

  /// No description provided for @callStateEnded.
  ///
  /// In en, this message translates to:
  /// **'Call Ended'**
  String get callStateEnded;

  /// No description provided for @phoneNumberHint.
  ///
  /// In en, this message translates to:
  /// **'Phone number'**
  String get phoneNumberHint;

  /// Menu item (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Group by Project'**
  String get tasksGroupByProject;

  /// Title for the phone calls upsell sheet shown to non-unlimited users
  ///
  /// In en, this message translates to:
  /// **'Phone Calls via Omi'**
  String get phoneCallsUnlimitedOnly;

  /// Description for minimal notification frequency
  ///
  /// In en, this message translates to:
  /// **'Only urgent things, about 1–3 a day'**
  String get frequencyDescMinimal;

  /// No description provided for @changeYourName.
  ///
  /// In en, this message translates to:
  /// **'Change Your Name'**
  String get changeYourName;

  /// Button text to edit an existing reply
  ///
  /// In en, this message translates to:
  /// **'Edit Your Reply'**
  String get editYourReply;

  /// Label
  ///
  /// In en, this message translates to:
  /// **'Public memories'**
  String get publicMemories;

  /// December month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Dec'**
  String get monthDec;

  /// Text field label to name a new person
  ///
  /// In en, this message translates to:
  /// **'Their name'**
  String get reviewNewPersonName;

  /// Dialog body for the Google-Calendar-not-connected dialog
  ///
  /// In en, this message translates to:
  /// **'Connect your Google Calendar to link conversations to calendar events.'**
  String get googleCalendarConnectPrompt;

  /// No description provided for @realtimeAudioBytes.
  ///
  /// In en, this message translates to:
  /// **'Realtime Audio Bytes'**
  String get realtimeAudioBytes;

  /// Description for goal tracker feature
  ///
  /// In en, this message translates to:
  /// **'Track your personal goals on homepage'**
  String get trackYourGoalsOnHomepage;

  /// Screen-reader label and tooltip of the chat + button (photo, library, file)
  ///
  /// In en, this message translates to:
  /// **'Add attachment'**
  String get chatAddAttachment;

  /// Beta label for experimental features
  ///
  /// In en, this message translates to:
  /// **'BETA'**
  String get beta;

  /// Button text to create new memory
  ///
  /// In en, this message translates to:
  /// **'Create Memory'**
  String get createMemory;

  /// Description for the permissions interstitial screen
  ///
  /// In en, this message translates to:
  /// **'Omi needs a few permissions to work properly. Please grant them to continue.'**
  String get permissionsRequiredDescription;

  /// Explanation of data collection in consent dialog
  ///
  /// In en, this message translates to:
  /// **'By continuing, your conversations, recordings, and personal information will be securely stored on our servers to provide AI-powered insights and enable all app features.'**
  String get dataCollectionMessage;

  /// Battery level label
  ///
  /// In en, this message translates to:
  /// **'Battery Level'**
  String get batteryLevel;

  /// Placeholder text for country search field
  ///
  /// In en, this message translates to:
  /// **'Search countries'**
  String get searchCountries;

  /// Title of the sheet that explains how sure Omi is about a person's voice (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Confidence'**
  String get confidenceSheetTitle;

  /// Label for device model in details
  ///
  /// In en, this message translates to:
  /// **'Device Model'**
  String get deviceModelLabel;

  /// Error message when no stable firmware is available
  ///
  /// In en, this message translates to:
  /// **'Could not find a stable firmware version for your device.'**
  String get noStableFirmwareFound;

  /// Empty state title when search has no results
  ///
  /// In en, this message translates to:
  /// **'No results found'**
  String get noResultsFound;

  /// Abbreviated minutes label in Wrapped collage
  ///
  /// In en, this message translates to:
  /// **'mins'**
  String get wrappedMins;

  /// Telegram row subtitle before connecting
  ///
  /// In en, this message translates to:
  /// **'Set up in two taps'**
  String get chatAppsTelegramSubtitle;

  /// No description provided for @categoryConversationAnalysis.
  ///
  /// In en, this message translates to:
  /// **'Conversation Analysis'**
  String get categoryConversationAnalysis;

  /// Label for target value field
  ///
  /// In en, this message translates to:
  /// **'Target'**
  String get target;

  /// No description provided for @apiKeyRequired.
  ///
  /// In en, this message translates to:
  /// **'API key is required'**
  String get apiKeyRequired;

  /// OmiGlass OTA success message
  ///
  /// In en, this message translates to:
  /// **'{deviceName} is updated and will restart on its own.'**
  String otaUpdatedMessage(String deviceName);

  /// No description provided for @reconnections.
  ///
  /// In en, this message translates to:
  /// **'Reconnections'**
  String get reconnections;

  /// Error message with error details when connection check fails
  ///
  /// In en, this message translates to:
  /// **'Error checking connection: {error}'**
  String errorCheckingConnection(String error);

  /// Plan and Usage period selector
  ///
  /// In en, this message translates to:
  /// **'Month'**
  String get usageMonth;

  /// Confirmation message when an additional speech sample is deleted
  ///
  /// In en, this message translates to:
  /// **'Additional Speech Sample Removed'**
  String get additionalSpeechSampleRemoved;

  /// No description provided for @speakerTagPromptExcerptSaved.
  ///
  /// In en, this message translates to:
  /// **'Answer saved for this excerpt.'**
  String get speakerTagPromptExcerptSaved;

  /// Label for device storage tier in sync pipeline
  ///
  /// In en, this message translates to:
  /// **'Omi\'s Storage'**
  String get omisStorage;

  /// Settings group: transcription, language, voice and capture settings
  ///
  /// In en, this message translates to:
  /// **'Recording & Transcription'**
  String get recordingAndTranscription;

  /// No description provided for @categoryCommunication.
  ///
  /// In en, this message translates to:
  /// **'Communication'**
  String get categoryCommunication;

  /// Celebration message in win template
  ///
  /// In en, this message translates to:
  /// **'You did it! 🎉'**
  String get wrappedYouDidIt;

  /// Error message when bulk deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete items'**
  String get failedToDeleteItems;

  /// After tagging a speaker: how many transcript lines received the name
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Labeled 1 line} other{Labeled {count} lines}}'**
  String speakerLabelLinesLabeled(int count);

  /// No description provided for @generatingLink.
  ///
  /// In en, this message translates to:
  /// **'Generating link…'**
  String get generatingLink;

  /// Help banner description with link to documentation
  ///
  /// In en, this message translates to:
  /// **'Click here for app building guides and documentation'**
  String get clickHereForAppBuildingGuides;

  /// Label of the authentication URL field when submitting an app with external integration
  ///
  /// In en, this message translates to:
  /// **'Auth URL'**
  String get authUrl;

  /// Error when trying to select capabilities alongside Persona
  ///
  /// In en, this message translates to:
  /// **'Other capabilities cannot be selected with Persona'**
  String get addAppCapabilityConflictWithPersona;

  /// Generic fallback name for connected headphones when the system does not provide a device name
  ///
  /// In en, this message translates to:
  /// **'Headphones'**
  String get deviceOnboardingVoiceReplyGenericHeadphones;

  /// Button label to clear all files
  ///
  /// In en, this message translates to:
  /// **'Clear All'**
  String get clearAll;

  /// Title when knowledge graph is empty
  ///
  /// In en, this message translates to:
  /// **'No knowledge graph yet'**
  String get noKnowledgeGraphYet;

  /// Success message for reported message
  ///
  /// In en, this message translates to:
  /// **'✅ Message reported successfully'**
  String get messageReportedSuccessfully;

  /// Error message when setting default payment method fails
  ///
  /// In en, this message translates to:
  /// **'Failed to set default payment method. Please try again later.'**
  String get paymentFailedToSetDefault;

  /// Status after the user corrects a learned memory
  ///
  /// In en, this message translates to:
  /// **'Updated.'**
  String get memoryReviewUpdated;

  /// Cancellation message
  ///
  /// In en, this message translates to:
  /// **'Your plan will cancel on {date}.'**
  String cancelAtPeriodEnd(String date);

  /// Welcome message on auth screen
  ///
  /// In en, this message translates to:
  /// **'Welcome to Omi'**
  String get welcomeToOmi;

  /// No description provided for @phoneFreeCallLimitReached.
  ///
  /// In en, this message translates to:
  /// **'Monthly free call limit reached. It resets next month.'**
  String get phoneFreeCallLimitReached;

  /// Description of Omi transcription features
  ///
  /// In en, this message translates to:
  /// **'Omi\'s live transcription is built for real-time conversations and labels who said what.'**
  String get omiTranscriptionOptimized;

  /// Title of the error state on the Chat apps page
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load chat apps'**
  String get chatAppsLoadFailedTitle;

  /// Button to sign in with Google
  ///
  /// In en, this message translates to:
  /// **'Continue with Google'**
  String get continueWithGoogle;

  /// Section title for integration setup steps
  ///
  /// In en, this message translates to:
  /// **'Setup Steps'**
  String get setupSteps;

  /// Count display
  ///
  /// In en, this message translates to:
  /// **'You have {count} total memories'**
  String totalMemoriesCount(int count);

  /// Feedback subtitle for battery drain
  ///
  /// In en, this message translates to:
  /// **'This helps our hardware team improve.'**
  String get feedbackSubtitleBatteryDrain;

  /// No description provided for @tryIt.
  ///
  /// In en, this message translates to:
  /// **'Try It'**
  String get tryIt;

  /// Setting title
  ///
  /// In en, this message translates to:
  /// **'Insights from Omi'**
  String get chatAppsInsights;

  /// Count of files
  ///
  /// In en, this message translates to:
  /// **'{count} recordings'**
  String nFiles(int count);

  /// Clear chat dialog title
  ///
  /// In en, this message translates to:
  /// **'Clear Chat?'**
  String get clearChatTitle;

  /// Description when template is private
  ///
  /// In en, this message translates to:
  /// **'Only you can use this template'**
  String get onlyYouCanUseTemplate;

  /// No description provided for @raybanMetaCameraExplanation.
  ///
  /// In en, this message translates to:
  /// **'Omi uses your glasses camera to add photos to your conversations. You can skip this and use audio only.'**
  String get raybanMetaCameraExplanation;

  /// Device diagnostics support upload
  ///
  /// In en, this message translates to:
  /// **'Support ticket code'**
  String get deviceDiagnosticsTicket;

  /// No description provided for @capabilityTasks.
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get capabilityTasks;

  /// Button to copy conversation URL to clipboard
  ///
  /// In en, this message translates to:
  /// **'Copy URL'**
  String get copyUrl;

  /// Toggle label to keep app or persona public
  ///
  /// In en, this message translates to:
  /// **'Keep {item} Public'**
  String keepItemPublic(String item);

  /// Suggested first question in a new chat
  ///
  /// In en, this message translates to:
  /// **'Can you teach me something new?'**
  String get chatStarterTeachMe;

  /// Hint for cancel reason detail text field
  ///
  /// In en, this message translates to:
  /// **'We appreciate any feedback…'**
  String get cancelReasonDetailHint;

  /// Message to check connection
  ///
  /// In en, this message translates to:
  /// **'Check your connection and try again.'**
  String get checkConnectionTryAgain;

  /// Back button text
  ///
  /// In en, this message translates to:
  /// **'Back to Conversations'**
  String get backToConversations;

  /// Merge button label
  ///
  /// In en, this message translates to:
  /// **'Merge'**
  String get merge;

  /// Error when upgrade page cannot be launched
  ///
  /// In en, this message translates to:
  /// **'Could not launch upgrade page. Please try again.'**
  String get couldNotLaunchUpgradePage;

  /// Tutorial step 1 subtitle — explains that spoken words appear in real time
  ///
  /// In en, this message translates to:
  /// **'Say a few words and watch them appear in real-time'**
  String get deviceOnboardingTranscriptionSubtitle;

  /// Confirmation prompt shown before deleting a downloaded model
  ///
  /// In en, this message translates to:
  /// **'Delete this model?'**
  String get deleteOnDeviceModelConfirm;

  /// Question card: identify the speaker of a short voice clip
  ///
  /// In en, this message translates to:
  /// **'Who said this?'**
  String get reviewQuestionSpeaker;

  /// No description provided for @updatedDate.
  ///
  /// In en, this message translates to:
  /// **'Updated {date}'**
  String updatedDate(String date);

  /// Save settings button
  ///
  /// In en, this message translates to:
  /// **'Save Settings'**
  String get saveSettings;

  /// No description provided for @alreadyGavePermission.
  ///
  /// In en, this message translates to:
  /// **'You\'ve already given us permission to save your recordings. Here\'s a reminder of why we need it:'**
  String get alreadyGavePermission;

  /// Success message after app is created and installed
  ///
  /// In en, this message translates to:
  /// **'App created and installed!'**
  String get appCreatedAndInstalled;

  /// Error message when Notion status refresh fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh Notion connection status.'**
  String get failedToRefreshNotionStatus;

  /// Tutorial step 2 status while the spoken question is processed by the AI
  ///
  /// In en, this message translates to:
  /// **'Processing your question…'**
  String get deviceOnboardingProcessingQuestion;

  /// Eyebrow label on a chat task card block
  ///
  /// In en, this message translates to:
  /// **'Task'**
  String get chatBlockTask;

  /// Warning when pendant is not connected
  ///
  /// In en, this message translates to:
  /// **'Pendant not connected. Connect to sync.'**
  String get pendantNotConnected;

  /// Dialog title for creating action item
  ///
  /// In en, this message translates to:
  /// **'Create Task'**
  String get createActionItem;

  /// No description provided for @logsCopied.
  ///
  /// In en, this message translates to:
  /// **'Logs copied'**
  String get logsCopied;

  /// No description provided for @timeout5MinutesDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 5 minutes of silence'**
  String get timeout5MinutesDesc;

  /// Error when file upload fails
  ///
  /// In en, this message translates to:
  /// **'Failed to upload file, please try again later'**
  String get msgUploadFileFailed;

  /// Report message confirmation
  ///
  /// In en, this message translates to:
  /// **'Report this message?'**
  String get reportMessageConfirm;

  /// Confirmation message for deleting a person
  ///
  /// In en, this message translates to:
  /// **'This removes {name}\'s voice samples and can\'t be undone. Their lines in past conversations become unnamed speakers.'**
  String deletePersonConfirmation(String name);

  /// Abbreviated Tuesday
  ///
  /// In en, this message translates to:
  /// **'Tue'**
  String get weekdayTue;

  /// Header for live transcript section
  ///
  /// In en, this message translates to:
  /// **'Live Transcript'**
  String get liveTranscript;

  /// Duration in days and hours
  ///
  /// In en, this message translates to:
  /// **'{days} days {hours} hours'**
  String timeDaysAndHours(int days, int hours);

  /// Heading of a version's page in the What's New sheet
  ///
  /// In en, this message translates to:
  /// **'Version {version}'**
  String versionLabel(String version);

  /// Cancel consequence
  ///
  /// In en, this message translates to:
  /// **'5-7 second processing delay (on-device models)'**
  String get cancelConsequenceDelay;

  /// Confirmation body; recording is a device name and time range such as Desktop · 1:57 PM
  ///
  /// In en, this message translates to:
  /// **'{recording} will show as its own conversation and won\'t be grouped with this event again.'**
  String captureRecordingSeparateMessage(String recording);

  /// Title of the pop-up that offers a newer version of the app
  ///
  /// In en, this message translates to:
  /// **'Update available'**
  String get updateAvailableTitle;

  /// Banner when the agent runs in shadow mode. Keep 'Dream' untranslated.
  ///
  /// In en, this message translates to:
  /// **'Preview mode: Dream shows what it would change, but nothing in your account changes yet.'**
  String get dreamReportShadowBanner;

  /// Error when accepting shared tasks fails
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t accept these tasks. You may have already accepted this share.'**
  String get sharedTasksAcceptFailed;

  /// Label for the app pricing field
  ///
  /// In en, this message translates to:
  /// **'App Pricing'**
  String get appPricingLabel;

  /// Button to re-download model
  ///
  /// In en, this message translates to:
  /// **'Re-download'**
  String get reDownload;

  /// Title of the phone-mic option in the record-options sheet
  ///
  /// In en, this message translates to:
  /// **'Record with Phone Mic'**
  String get recordWithPhoneMic;

  /// States the date an app was automatically disabled
  ///
  /// In en, this message translates to:
  /// **'Disabled on {date}.'**
  String appDisabledOn(String date);

  /// Label for the play/listen button on the speech profile page
  ///
  /// In en, this message translates to:
  /// **'Play'**
  String get play;

  /// Option for private memory visibility
  ///
  /// In en, this message translates to:
  /// **'Private'**
  String get private;

  /// Answer chip on the voice suggestion card: skip this voice (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Not Sure'**
  String get speakerTagPromptNotSureAction;

  /// No description provided for @showDiscardedConversationsDesc.
  ///
  /// In en, this message translates to:
  /// **'Include conversations marked as discarded'**
  String get showDiscardedConversationsDesc;

  /// Subtitle for the Live option in the recording mode picker
  ///
  /// In en, this message translates to:
  /// **'Transcribe in real time as you speak.'**
  String get captureModeLiveDescription;

  /// Success message when subscription is cancelled
  ///
  /// In en, this message translates to:
  /// **'Subscription cancelled successfully. It will remain active until the end of the current billing period.'**
  String get subscriptionCancelledSuccessfully;

  /// No description provided for @tapToSetAGoal.
  ///
  /// In en, this message translates to:
  /// **'Tap to set a goal'**
  String get tapToSetAGoal;

  /// Hint text for feedback textarea asking user to provide more details
  ///
  /// In en, this message translates to:
  /// **'Tell us more about what went wrong…'**
  String get tellUsMoreWhatWentWrong;

  /// Title of the confirmation dialog before downgrading to the free plan
  ///
  /// In en, this message translates to:
  /// **'Downgrade to Freemium?'**
  String get downgradeToFreemiumTitle;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get usageTasks;

  /// Shown when a chat reply fails because the device has no connectivity
  ///
  /// In en, this message translates to:
  /// **'Unable to connect. Check your connection and try again.'**
  String get chatReplyOffline;

  /// Menu option to change memory visibility to public
  ///
  /// In en, this message translates to:
  /// **'Make Public'**
  String get makePublic;

  /// Error message for unexpected Firebase error during sign-in
  ///
  /// In en, this message translates to:
  /// **'Unexpected error signing in, Firebase error, please try again.'**
  String get authUnexpectedErrorFirebase;

  /// Feature: unlimited conversations
  ///
  /// In en, this message translates to:
  /// **'Unlimited conversations'**
  String get unlimitedConversations;

  /// No description provided for @stagingDisclaimer.
  ///
  /// In en, this message translates to:
  /// **'Staging may be buggy, have inconsistent performance, and data might be lost. Use for testing only.'**
  String get stagingDisclaimer;

  /// No description provided for @captureMicrophonePermissionRequired.
  ///
  /// In en, this message translates to:
  /// **'Microphone permission required'**
  String get captureMicrophonePermissionRequired;

  /// Share stats: insights
  ///
  /// In en, this message translates to:
  /// **'✨ Provided {count} insights'**
  String shareStatsInsights(String count);

  /// Quick reason chip: the summary was not relevant.
  ///
  /// In en, this message translates to:
  /// **'Not relevant'**
  String get feedbackReasonSummaryIrrelevant;

  /// Success message for User ID copy
  ///
  /// In en, this message translates to:
  /// **'User ID copied to clipboard'**
  String get userIdCopiedToClipboard;

  /// Success message when URL is copied
  ///
  /// In en, this message translates to:
  /// **'URL Copied to Clipboard'**
  String get urlCopiedToClipboard;

  /// Annual plan card subtitle showing the billing term and total price
  ///
  /// In en, this message translates to:
  /// **'{months} months / {price}'**
  String annualBillingSummary(int months, String price);

  /// Switch subtitle when off
  ///
  /// In en, this message translates to:
  /// **'Off: you only see them in {app}.'**
  String chatAppsShowInAppOff(String app);

  /// Success message after sending a reply
  ///
  /// In en, this message translates to:
  /// **'Reply sent successfully'**
  String get replySentSuccessfully;

  /// Tutorial step 3 title while waiting for the user to power the device off
  ///
  /// In en, this message translates to:
  /// **'Turn Off'**
  String get deviceOnboardingTurnOffTitle;

  /// Description of phone storage in sync info sheet
  ///
  /// In en, this message translates to:
  /// **'When Omi reconnects, recordings are automatically transferred to your phone as a temporary holding area before uploading.'**
  String get phoneStorageDesc;

  /// No description provided for @callRecordingConsentDisclaimer.
  ///
  /// In en, this message translates to:
  /// **'Call recording may require consent in your jurisdiction'**
  String get callRecordingConsentDisclaimer;

  /// No description provided for @showDiscardedConversations.
  ///
  /// In en, this message translates to:
  /// **'Show Discarded Conversations'**
  String get showDiscardedConversations;

  /// Calendar integration section
  ///
  /// In en, this message translates to:
  /// **'Calendar Integration'**
  String get calendarIntegration;

  /// Whisper model size: base
  ///
  /// In en, this message translates to:
  /// **'Base'**
  String get whisperModelSizeBase;

  /// Title for share to contacts sheet
  ///
  /// In en, this message translates to:
  /// **'Share via SMS'**
  String get shareViaSms;

  /// Validation error when name is too short
  ///
  /// In en, this message translates to:
  /// **'Name must be at least 3 characters'**
  String get nameMustBeAtLeast3Characters;

  /// Discard the current chat voice recording without transcription
  ///
  /// In en, this message translates to:
  /// **'Discard'**
  String get chatDiscardRecording;

  /// Pro benefit bullet
  ///
  /// In en, this message translates to:
  /// **'Text Omi from Telegram and iMessage'**
  String get chatAppsProPerkText;

  /// Status when ready to sync
  ///
  /// In en, this message translates to:
  /// **'Ready to sync'**
  String get readyToSync;

  /// Empty-state title of an app category with no apps
  ///
  /// In en, this message translates to:
  /// **'No Apps in This Category Yet'**
  String get noAppsInCategoryYet;

  /// Title for firmware update available dialog
  ///
  /// In en, this message translates to:
  /// **'Firmware Update Available'**
  String get firmwareUpdateAvailable;

  /// Label for model number field
  ///
  /// In en, this message translates to:
  /// **'Model Number'**
  String get modelNumber;

  /// No description provided for @sortBy.
  ///
  /// In en, this message translates to:
  /// **'Sort'**
  String get sortBy;

  /// Text on swipe-to-confirm button for firmware update
  ///
  /// In en, this message translates to:
  /// **'Slide to Update'**
  String get slideToUpdate;

  /// How much one kind of evidence raises confidence: almost not at all.
  ///
  /// In en, this message translates to:
  /// **'Barely helps'**
  String get effectBarelyCounts;

  /// No description provided for @onlyYouCanUse.
  ///
  /// In en, this message translates to:
  /// **'Only you can use this app'**
  String get onlyYouCanUse;

  /// No description provided for @triggersWhenNewConversationCreated.
  ///
  /// In en, this message translates to:
  /// **'Triggers when a new conversation is created.'**
  String get triggersWhenNewConversationCreated;

  /// Label for payment plan selection
  ///
  /// In en, this message translates to:
  /// **'Payment Plan'**
  String get paymentPlan;

  /// Description for the Whisper on-device transcription model selector
  ///
  /// In en, this message translates to:
  /// **'Choose the model for on-device transcription'**
  String get whisperModelDesc;

  /// Ask suggestion
  ///
  /// In en, this message translates to:
  /// **'What do I still owe people?'**
  String get askSuggestOwe;

  /// Star conversation action
  ///
  /// In en, this message translates to:
  /// **'Star Conversation'**
  String get starConversation;

  /// Hardware section header
  ///
  /// In en, this message translates to:
  /// **'Hardware'**
  String get hardwareSection;

  /// Loading message while transcribing audio
  ///
  /// In en, this message translates to:
  /// **'Transcribing…'**
  String get transcribing;

  /// Setting subtitle
  ///
  /// In en, this message translates to:
  /// **'Send a voice note and Omi will answer it.'**
  String get chatAppsVoiceNotesSubtitle;

  /// What the user can do to reach Confirmed when a voice sample is missing. 'Remember voices' refers to the setting 'Remember voices of people you name'.
  ///
  /// In en, this message translates to:
  /// **'Omi also needs a voice sample of {name}. Label them with Remember voices on.'**
  String confidenceNextVoice(String name);

  /// Filter for apps with 3 or more stars
  ///
  /// In en, this message translates to:
  /// **'3+ Stars'**
  String get rating3PlusStars;

  /// Status when recording is active
  ///
  /// In en, this message translates to:
  /// **'Recording Active'**
  String get recordingActive;

  /// Filter chip for star rating
  ///
  /// In en, this message translates to:
  /// **'{count} Star'**
  String starFilter(int count);

  /// Label for storage location in details
  ///
  /// In en, this message translates to:
  /// **'Storage Location'**
  String get storageLocationLabel;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'When Omi tidies your notes, the changes appear here.'**
  String get reviewNoChangesBody;

  /// Menu item for testing prompts
  ///
  /// In en, this message translates to:
  /// **'Test Prompt'**
  String get testPrompt;

  /// OmiGlass OTA has no download URL
  ///
  /// In en, this message translates to:
  /// **'This update isn\'t available right now. Try again later.'**
  String get otaUpdateUnavailable;

  /// Status during download
  ///
  /// In en, this message translates to:
  /// **'Downloading…'**
  String get downloading;

  /// Simple welcome message without user name
  ///
  /// In en, this message translates to:
  /// **'Welcome back'**
  String get welcomeBackSimple;

  /// Brand name for the Soniox speech-to-text provider
  ///
  /// In en, this message translates to:
  /// **'Soniox'**
  String get sttProviderSoniox;

  /// Button to clear all selected contacts
  ///
  /// In en, this message translates to:
  /// **'Clear All'**
  String get clearAllSelection;

  /// Reason line under a person's name: the user never labeled or confirmed this person.
  ///
  /// In en, this message translates to:
  /// **'Never confirmed'**
  String get confidenceReasonNeverConfirmed;

  /// Label for write API key scope
  ///
  /// In en, this message translates to:
  /// **'Write'**
  String get writeScope;

  /// Evidence row: Omi has a usable voice sample for this person.
  ///
  /// In en, this message translates to:
  /// **'Voice sample ready'**
  String get evidenceVoiceReady;

  /// Button text to update app
  ///
  /// In en, this message translates to:
  /// **'Update App'**
  String get updateApp;

  /// Abbreviated Thursday
  ///
  /// In en, this message translates to:
  /// **'Thu'**
  String get weekdayThu;

  /// No description provided for @chatUsageCostNoLimit.
  ///
  /// In en, this message translates to:
  /// **'Chat: \${used} used this month'**
  String chatUsageCostNoLimit(String used);

  /// No description provided for @configCopied.
  ///
  /// In en, this message translates to:
  /// **'Config copied to clipboard'**
  String get configCopied;

  /// Launch failure screen, rejected build configuration
  ///
  /// In en, this message translates to:
  /// **'This build of Omi has a configuration problem. It is not a problem with your device. Contact support and include the details below.'**
  String get startupFailedConfigMessage;

  /// Mac app download link
  ///
  /// In en, this message translates to:
  /// **'Get Omi for Mac'**
  String get getOmiForMac;

  /// No description provided for @appleHealthConnectedBadge.
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get appleHealthConnectedBadge;

  /// Error when camera is not available on desktop
  ///
  /// In en, this message translates to:
  /// **'Camera capture is not available on this platform'**
  String get msgCameraNotAvailable;

  /// Instruction text for Action Items interactions
  ///
  /// In en, this message translates to:
  /// **'Tap to edit • Long press to select • Swipe for actions'**
  String get actionItemsDescription;

  /// Description for notifications permission
  ///
  /// In en, this message translates to:
  /// **'So Omi can send you conversation summaries, task reminders and replies from your apps.'**
  String get notificationsDesc;

  /// Live-capture WAL indicator after a failed upload attempt that will be retried automatically
  ///
  /// In en, this message translates to:
  /// **'Retrying upload… {duration} of audio kept on your phone'**
  String audioUploadRetrying(String duration);

  /// Success message when import begins
  ///
  /// In en, this message translates to:
  /// **'Import started! You\'ll be notified when it\'s complete.'**
  String get importStarted;

  /// Toast title when a model download fails
  ///
  /// In en, this message translates to:
  /// **'Model download failed'**
  String get onDeviceModelDownloadFailed;

  /// No description provided for @noProjectsInWorkspace.
  ///
  /// In en, this message translates to:
  /// **'No projects found in this workspace'**
  String get noProjectsInWorkspace;

  /// Help center menu item
  ///
  /// In en, this message translates to:
  /// **'Help Center'**
  String get helpCenter;

  /// Bullet points explaining training data program benefits
  ///
  /// In en, this message translates to:
  /// **'• Your data helps improve AI models\n• Only non-sensitive data is shared'**
  String get trainingDataBullets;

  /// No description provided for @invalidPromotionCode.
  ///
  /// In en, this message translates to:
  /// **'Invalid promotion code.'**
  String get invalidPromotionCode;

  /// No description provided for @battery.
  ///
  /// In en, this message translates to:
  /// **'Battery'**
  String get battery;

  /// Option to clear the current filter selection
  ///
  /// In en, this message translates to:
  /// **'Clear selection'**
  String get clearSelection;

  /// No description provided for @phoneSetupStep2Subtitle.
  ///
  /// In en, this message translates to:
  /// **'A short code you\'ll type on the call'**
  String get phoneSetupStep2Subtitle;

  /// No description provided for @googleSearch.
  ///
  /// In en, this message translates to:
  /// **'Google Search'**
  String get googleSearch;

  /// No description provided for @charging.
  ///
  /// In en, this message translates to:
  /// **'Charging'**
  String get charging;

  /// Destructive dialog button that names the person being deleted (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Delete {name}'**
  String deleteNamedPerson(String name);

  /// Heading of the upgrade card for free users
  ///
  /// In en, this message translates to:
  /// **'Chat apps are part of Pro'**
  String get chatAppsPartOfPro;

  /// Validation error under the webhook URL field when submitting an app
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid webhook URL'**
  String get invalidWebhookUrlError;

  /// Empty state message for starred filter
  ///
  /// In en, this message translates to:
  /// **'Star conversations to find them quickly here'**
  String get starConversationsToFindQuickly;

  /// Permission title for creating memories
  ///
  /// In en, this message translates to:
  /// **'Create Memories'**
  String get permissionCreateMemories;

  /// Snackbar message when conversation ID is copied
  ///
  /// In en, this message translates to:
  /// **'Conversation ID copied to clipboard'**
  String get conversationIdCopied;

  /// Name of Apple's Messages app, as shown on the device in this language
  ///
  /// In en, this message translates to:
  /// **'Messages'**
  String get chatAppsMessagesApp;

  /// No description provided for @understandingWords.
  ///
  /// In en, this message translates to:
  /// **'Understanding (words)'**
  String get understandingWords;

  /// Device Diagnostics verdict detail under 'Having trouble connecting'
  ///
  /// In en, this message translates to:
  /// **'Failed connections in the last 24 hours: {count}'**
  String diagnosticsVerdictTroubleDetail(int count);

  /// No description provided for @editName.
  ///
  /// In en, this message translates to:
  /// **'Edit Name'**
  String get editName;

  /// Tooltip for Ask button on conversation detail
  ///
  /// In en, this message translates to:
  /// **'Ask about this'**
  String get askAboutThisConversation;

  /// Label for template selector
  ///
  /// In en, this message translates to:
  /// **'Use template from'**
  String get useTemplateFrom;

  /// Error showing microphone permission status
  ///
  /// In en, this message translates to:
  /// **'Microphone permission status: {status}. Please check System Preferences.'**
  String onboardingMicrophoneStatusCheckPrefs(String status);

  /// Label for completion checkbox
  ///
  /// In en, this message translates to:
  /// **'Mark as completed'**
  String get markAsCompleted;

  /// Error when URL does not end with slash
  ///
  /// In en, this message translates to:
  /// **'URL must end with \"/\"'**
  String get urlMustEndWithSlashError;

  /// Onboarding intro screen title shown before the device tutorial steps
  ///
  /// In en, this message translates to:
  /// **'Get to Know Your Omi'**
  String get deviceOnboardingIntroTitle;

  /// No description provided for @nPending.
  ///
  /// In en, this message translates to:
  /// **'{count} pending'**
  String nPending(int count);

  /// No description provided for @howShouldOmiCallYou.
  ///
  /// In en, this message translates to:
  /// **'How should Omi call you?'**
  String get howShouldOmiCallYou;

  /// Loading message shown while form is being prepared
  ///
  /// In en, this message translates to:
  /// **'Preparing the form for you…'**
  String get preparingFormForYou;

  /// Ask: the confirm button
  ///
  /// In en, this message translates to:
  /// **'Delete chat'**
  String get deleteChat;

  /// Error when photos permission is denied
  ///
  /// In en, this message translates to:
  /// **'Photos permission denied. Please allow access to photos to select images'**
  String get msgPhotosPermissionDenied;

  /// Accessibility label of the small arrow badge on the record button that opens the 'Record with' sheet.
  ///
  /// In en, this message translates to:
  /// **'More ways to record'**
  String get moreWaysToRecord;

  /// No description provided for @creatingPlan.
  ///
  /// In en, this message translates to:
  /// **'Creating plan'**
  String get creatingPlan;

  /// Confirmation when config is copied
  ///
  /// In en, this message translates to:
  /// **'Config copied to clipboard'**
  String get configCopiedToClipboard;

  /// Subtitle explaining the transcribe-later mode toggle
  ///
  /// In en, this message translates to:
  /// **'Record now, transcribe when you choose. Audio stays on your phone until then.'**
  String get transcribeLaterDescription;

  /// Error message when switching to free plan fails
  ///
  /// In en, this message translates to:
  /// **'Could not switch to free plan. Please try again.'**
  String get couldNotSwitchToFreePlan;

  /// Label under completed tasks count
  ///
  /// In en, this message translates to:
  /// **'tasks completed'**
  String get wrappedTasksCompleted;

  /// Tutorial step 1 title — prompts the user to speak into the Omi device for the live-transcription demo
  ///
  /// In en, this message translates to:
  /// **'Speak Into Your Omi'**
  String get deviceOnboardingTranscriptionTitle;

  /// Success message after submitting training data request
  ///
  /// In en, this message translates to:
  /// **'Thank you! Your request is under review. We will notify you once approved.'**
  String get thankYouRequestUnderReview;

  /// Action to unpair and forget device
  ///
  /// In en, this message translates to:
  /// **'Unpair and Forget Device'**
  String get unpairAndForgetDevice;

  /// Option to share conversation via web URL
  ///
  /// In en, this message translates to:
  /// **'Send web url'**
  String get sendWebUrl;

  /// Message shown when there are no tasks due today
  ///
  /// In en, this message translates to:
  /// **'No tasks for today.\nAsk Omi for more tasks or create manually.'**
  String get noTasksForToday;

  /// Conversation list row chip: the server could not summarize this conversation after its retries, and retrying can still succeed. Shown next to a Retry button.
  ///
  /// In en, this message translates to:
  /// **'Summary failed'**
  String get conversationSummaryFailed;

  /// No description provided for @realtimeTranscript.
  ///
  /// In en, this message translates to:
  /// **'Real-time Transcript'**
  String get realtimeTranscript;

  /// Shows number of conversations created after sync
  ///
  /// In en, this message translates to:
  /// **'{count} conversation{count, plural, =1{} other{s}} created'**
  String nConversationsCreated(int count);

  /// No description provided for @noEmailSet.
  ///
  /// In en, this message translates to:
  /// **'No email set'**
  String get noEmailSet;

  /// Placeholder for due date picker button
  ///
  /// In en, this message translates to:
  /// **'Set due date and time'**
  String get setDueDateAndTime;

  /// Pairing description for Fieldy device
  ///
  /// In en, this message translates to:
  /// **'Press and hold the device until the light appears to turn it on.'**
  String get pairingDescFieldy;

  /// Title for End-to-End Encryption dialog
  ///
  /// In en, this message translates to:
  /// **'Maximum Security (E2EE)'**
  String get maximumSecurityE2ee;

  /// No description provided for @instantSpeakerLabels.
  ///
  /// In en, this message translates to:
  /// **'Instant speaker labels'**
  String get instantSpeakerLabels;

  /// No description provided for @resetRequestConfig.
  ///
  /// In en, this message translates to:
  /// **'Reset request config to default'**
  String get resetRequestConfig;

  /// Dialog title when webhook URL is missing
  ///
  /// In en, this message translates to:
  /// **'Webhook URL not set'**
  String get webhookUrlNotSet;

  /// Quick reason chip: some other recording problem.
  ///
  /// In en, this message translates to:
  /// **'Something else'**
  String get feedbackReasonRecordingOther;

  /// Body when cutover rollback stranded newer data
  ///
  /// In en, this message translates to:
  /// **'Your account is in maintenance after a migration rollback. Some newer data may be stranded.'**
  String get accountCutoverMigrationRollbackMessage;

  /// Cancel consequence
  ///
  /// In en, this message translates to:
  /// **'30% lower transcription quality (on-device models)'**
  String get cancelConsequenceQuality;

  /// Pairing description for Plaud Note
  ///
  /// In en, this message translates to:
  /// **'Press and hold the side button for 2 seconds. The red LED will blink when ready to pair.'**
  String get pairingDescPlaudNote;

  /// Plans and billing section
  ///
  /// In en, this message translates to:
  /// **'Plans & Billing'**
  String get plansAndBilling;

  /// No description provided for @deviceOnboardingVoiceReplyTitle.
  ///
  /// In en, this message translates to:
  /// **'Hear Omi\'s Answers'**
  String get deviceOnboardingVoiceReplyTitle;

  /// No description provided for @generatingIcon.
  ///
  /// In en, this message translates to:
  /// **'Generating icon…'**
  String get generatingIcon;

  /// Banner body on the People list offering to clean up unsure people.
  ///
  /// In en, this message translates to:
  /// **'Mostly misheard names. Review them and remove the ones that aren\'t real.'**
  String get cleanUpBannerBody;

  /// Answered state of the voice card after the user said the voice is theirs.
  ///
  /// In en, this message translates to:
  /// **'Saved as you'**
  String get speakerTagPromptSavedAsYou;

  /// Button text to connect specific device models
  ///
  /// In en, this message translates to:
  /// **'Connect Omi / OmiGlass'**
  String get connectOmiOmiGlass;

  /// No description provided for @capabilityConversations.
  ///
  /// In en, this message translates to:
  /// **'Conversations'**
  String get capabilityConversations;

  /// Description text for notification frequency section
  ///
  /// In en, this message translates to:
  /// **'Control how often Omi sends you proactive notifications and reminders.'**
  String get notificationFrequencyDescription;

  /// Chat scope chip when asking about a specific conversation
  ///
  /// In en, this message translates to:
  /// **'About: {title}'**
  String chatScopeAbout(String title);

  /// Section header for import history
  ///
  /// In en, this message translates to:
  /// **'Import History'**
  String get importHistory;

  /// No description provided for @getApiKey.
  ///
  /// In en, this message translates to:
  /// **'Get API Key'**
  String get getApiKey;

  /// Message when no interesting content found
  ///
  /// In en, this message translates to:
  /// **'Nothing interesting found,\nwant to retry?'**
  String get nothingInterestingRetry;

  /// Title asking user what they want to create
  ///
  /// In en, this message translates to:
  /// **'What would you like to create?'**
  String get whatWouldYouLikeToCreate;

  /// Free pricing option
  ///
  /// In en, this message translates to:
  /// **'Free'**
  String get pricingFree;

  /// Hint at the bottom of the 'Who is this?' card.
  ///
  /// In en, this message translates to:
  /// **'Your answer helps Omi recognize this voice next time.'**
  String get speakerTagPromptHintIdentify;

  /// Title shown when user has no conversations
  ///
  /// In en, this message translates to:
  /// **'No conversations yet'**
  String get noConversationsYet;

  /// Message when device does not meet requirements
  ///
  /// In en, this message translates to:
  /// **'Your device does not meet the requirements for On-Device transcription.'**
  String get deviceNotMeetRequirements;

  /// Placeholder text when recording keyboard shortcut
  ///
  /// In en, this message translates to:
  /// **'Press keys…'**
  String get pressKeys;

  /// Free-tier limitation: transcription is delayed rather than live
  ///
  /// In en, this message translates to:
  /// **'5-7 second delay (not real-time)'**
  String get downgradeLimitDelayNotRealTime;

  /// No description provided for @conversationLinkCopiedToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Conversation link copied to clipboard'**
  String get conversationLinkCopiedToClipboard;

  /// Onboarding setup checklist step
  ///
  /// In en, this message translates to:
  /// **'Setting up your memory'**
  String get onboardingSetupStepMemory;

  /// Shown before a Copy link button on the Telegram connect sheet
  ///
  /// In en, this message translates to:
  /// **'Telegram on another device?'**
  String get chatAppsTelegramOtherDevice;

  /// Toast when a link opens an app that was removed from the store
  ///
  /// In en, this message translates to:
  /// **'This app is no longer available'**
  String get appNotFoundOrRemoved;

  /// Label showing number of installed apps
  ///
  /// In en, this message translates to:
  /// **'Apps ({count})'**
  String appsCount(String count);

  /// Title for E2EE card
  ///
  /// In en, this message translates to:
  /// **'End-to-End Encryption'**
  String get endToEndEncryption;

  /// OmiGlass OTA could not reach the device
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t connect to {deviceName}. Keep it on and nearby, then try again.'**
  String otaConnectFailed(String deviceName);

  /// Continue button label
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get continueButton;

  /// Error when sharing preparation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to prepare conversation for sharing. Please try again.'**
  String get failedToPrepareConversationForSharing;

  /// Button text to show all items
  ///
  /// In en, this message translates to:
  /// **'Show All'**
  String get showAll;

  /// No description provided for @speakerLabelYou.
  ///
  /// In en, this message translates to:
  /// **'You'**
  String get speakerLabelYou;

  /// Badge for action items in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get wrappedActionItems;

  /// No description provided for @failedToInstallApp.
  ///
  /// In en, this message translates to:
  /// **'Failed to install {appName}. Please try again.'**
  String failedToInstallApp(String appName);

  /// Loading text displayed while search is in progress
  ///
  /// In en, this message translates to:
  /// **'Searching'**
  String get searching;

  /// Title for device compatibility error dialog
  ///
  /// In en, this message translates to:
  /// **'Device Not Compatible'**
  String get deviceNotCompatibleTitle;

  /// Button text to generate a summary
  ///
  /// In en, this message translates to:
  /// **'Summarize'**
  String get summarize;

  /// Description for export feature
  ///
  /// In en, this message translates to:
  /// **'Export conversations to a JSON file'**
  String get exportConversationsToJson;

  /// Explanation of what happens when making private
  ///
  /// In en, this message translates to:
  /// **'If you make the {item} private now, it will stop working for everyone and will be visible only to you'**
  String makeItemPrivateExplanation(String item);

  /// Error message when sharing fails
  ///
  /// In en, this message translates to:
  /// **'Failed to share. Please try again.'**
  String get wrappedFailedToShare;

  /// Dialog description for cancel subscription
  ///
  /// In en, this message translates to:
  /// **'You keep access until the end of your current billing period.'**
  String get cancelSubscriptionConfirmation;

  /// Label for the button to dismiss the in-call keypad
  ///
  /// In en, this message translates to:
  /// **'Hide Keypad'**
  String get phoneHideKeypad;

  /// No description provided for @vadGate.
  ///
  /// In en, this message translates to:
  /// **'VAD Gate'**
  String get vadGate;

  /// No description provided for @nameUpdatedSuccessfully.
  ///
  /// In en, this message translates to:
  /// **'Name updated successfully!'**
  String get nameUpdatedSuccessfully;

  /// Action sheet option to select from photo library
  ///
  /// In en, this message translates to:
  /// **'Photo Library'**
  String get photoLibrary;

  /// Description under the Chat apps heading
  ///
  /// In en, this message translates to:
  /// **'Ask about your day, save memories, and manage tasks from Telegram or iMessage. Your chats stay in the app you use, and Omi remembers what you talked about everywhere.'**
  String get chatAppsHeroMessage;

  /// Dialog title for upgrading to annual plan
  ///
  /// In en, this message translates to:
  /// **'Upgrade to Annual Plan'**
  String get upgradeToAnnualPlan;

  /// No description provided for @completeAuthInBrowser.
  ///
  /// In en, this message translates to:
  /// **'Please complete authentication in your browser. Once done, return to the app.'**
  String get completeAuthInBrowser;

  /// No description provided for @errorLabel.
  ///
  /// In en, this message translates to:
  /// **'Error: {error}'**
  String errorLabel(String error);

  /// No description provided for @durationThresholdDesc.
  ///
  /// In en, this message translates to:
  /// **'Hide conversations shorter than this'**
  String get durationThresholdDesc;

  /// Phone-local recordings still waiting to be uploaded for transcription, on the conversations list banner.
  ///
  /// In en, this message translates to:
  /// **'Transcriptions pending {count}'**
  String transcriptionsPendingCount(int count);

  /// Caveat note shown in the Transcribe Later sheet
  ///
  /// In en, this message translates to:
  /// **'Works with the phone microphone and Omi or Limitless wearables. Audio stays on your phone until you choose to upload it.'**
  String get transcribeLaterNote;

  /// Fallback text for device name
  ///
  /// In en, this message translates to:
  /// **'Device'**
  String get device;

  /// Success message after signing up
  ///
  /// In en, this message translates to:
  /// **'Signup Successful!'**
  String get signUpSuccess;

  /// Onboarding step title for permissions
  ///
  /// In en, this message translates to:
  /// **'Permissions'**
  String get onboardingPermissions;

  /// Warning about large model sizes
  ///
  /// In en, this message translates to:
  /// **'This model is large and may crash the app or run very slowly on mobile devices.\n\n\"small\" or \"base\" is recommended.'**
  String get modelTooLargeWarning;

  /// Description for show daily score toggle in developer settings
  ///
  /// In en, this message translates to:
  /// **'Show Daily Score on homepage'**
  String get showDailyScoreOnHomepage;

  /// Sheet summary for an Unverified person: the user never labeled or confirmed them.
  ///
  /// In en, this message translates to:
  /// **'You haven\'t labeled or confirmed {name} yet, so Omi isn\'t sure it knows their voice.'**
  String confidenceSummaryUnverified(String name);

  /// End conversation action
  ///
  /// In en, this message translates to:
  /// **'End Conversation'**
  String get endConversation;

  /// Label for unpinning a memory from baseline
  ///
  /// In en, this message translates to:
  /// **'Unpin from Baseline'**
  String get unpinAsBaseline;

  /// No description provided for @audioSavedLocally.
  ///
  /// In en, this message translates to:
  /// **'{duration} audio saved locally'**
  String audioSavedLocally(String duration);

  /// Dialog title when editing a memory
  ///
  /// In en, this message translates to:
  /// **'✏️ Edit Memory'**
  String get editMemory;

  /// Shown after answering all speaker questions
  ///
  /// In en, this message translates to:
  /// **'Thanks! Omi will get better at recognizing voices.'**
  String get speakerTagPromptThanks;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'Task description cannot be empty.'**
  String get actionItemDescriptionEmpty;

  /// Button text to defer action
  ///
  /// In en, this message translates to:
  /// **'Not Now'**
  String get maybeLater;

  /// Webhook type for day summary
  ///
  /// In en, this message translates to:
  /// **'Day Summary'**
  String get daySummary;

  /// Report dialog confirmation text
  ///
  /// In en, this message translates to:
  /// **'Report this message?'**
  String get confirmReportMessage;

  /// Dialog title for deleting Limitless data
  ///
  /// In en, this message translates to:
  /// **'Delete All Limitless Conversations?'**
  String get deleteAllLimitlessConversations;

  /// Action menu entry to select every task in the action items list
  ///
  /// In en, this message translates to:
  /// **'Select All'**
  String get selectAllTasksMenu;

  /// No description provided for @syncStatusRetrying.
  ///
  /// In en, this message translates to:
  /// **'Couldn’t process — retrying'**
  String get syncStatusRetrying;

  /// Export button text
  ///
  /// In en, this message translates to:
  /// **'Export'**
  String get exportButton;

  /// Badge text for category chart card
  ///
  /// In en, this message translates to:
  /// **'You Talked About'**
  String get wrappedYouTalkedAboutBadge;

  /// No description provided for @firmwareWarningTitle.
  ///
  /// In en, this message translates to:
  /// **'Important: Read Before Updating'**
  String get firmwareWarningTitle;

  /// Permission type label for create permissions
  ///
  /// In en, this message translates to:
  /// **'Create'**
  String get permissionTypeCreate;

  /// Link to view usage
  ///
  /// In en, this message translates to:
  /// **'View Usage'**
  String get viewUsage;

  /// Onboarding intro screen estimated duration hint
  ///
  /// In en, this message translates to:
  /// **'About 1 minute'**
  String get deviceOnboardingIntroDuration;

  /// No description provided for @import.
  ///
  /// In en, this message translates to:
  /// **'Import'**
  String get import;

  /// No description provided for @conversationsExportStarted.
  ///
  /// In en, this message translates to:
  /// **'Conversations Export Started. This may take a few seconds, please wait.'**
  String get conversationsExportStarted;

  /// Label for the speech-to-text provider selector
  ///
  /// In en, this message translates to:
  /// **'Speech-to-Text Provider'**
  String get speechToTextProvider;

  /// No description provided for @languageTranslation.
  ///
  /// In en, this message translates to:
  /// **'100+ language translation'**
  String get languageTranslation;

  /// No description provided for @primaryLanguage.
  ///
  /// In en, this message translates to:
  /// **'Primary Language'**
  String get primaryLanguage;

  /// Shows the duration of a speech sample in seconds
  ///
  /// In en, this message translates to:
  /// **'Duration: {seconds} seconds'**
  String durationSeconds(String seconds);

  /// Subtitle explaining the Auto-Sync toggle in device settings
  ///
  /// In en, this message translates to:
  /// **'Automatically sync offline recordings when your device connects'**
  String get autoSyncDescription;

  /// Debug logs feature name
  ///
  /// In en, this message translates to:
  /// **'Debug Logs'**
  String get debugLogs;

  /// No description provided for @authorizationRevoked.
  ///
  /// In en, this message translates to:
  /// **'Authorization revoked.'**
  String get authorizationRevoked;

  /// Empty state title when no transcript
  ///
  /// In en, this message translates to:
  /// **'No Transcript Available'**
  String get noTranscriptAvailable;

  /// Status when update is available
  ///
  /// In en, this message translates to:
  /// **'Available'**
  String get available;

  /// Section title in summary collage (uppercase)
  ///
  /// In en, this message translates to:
  /// **'OBSESSIONS'**
  String get wrappedObsessionsLabelUpper;

  /// Profession option: Student
  ///
  /// In en, this message translates to:
  /// **'Student'**
  String get professionStudent;

  /// Example request to send Omi
  ///
  /// In en, this message translates to:
  /// **'Remind me to call Mom on Sunday'**
  String get chatAppsTryRemind;

  /// No description provided for @failedToStartVerification.
  ///
  /// In en, this message translates to:
  /// **'Failed to start verification'**
  String get failedToStartVerification;

  /// Error message when folder creation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create folder'**
  String get failedToCreateFolder;

  /// Duration in singular minute
  ///
  /// In en, this message translates to:
  /// **'{count} min'**
  String timeMinSingular(int count);

  /// Filter option for interesting memories
  ///
  /// In en, this message translates to:
  /// **'Insights'**
  String get insights;

  /// Privacy page - privacyInformation
  ///
  /// In en, this message translates to:
  /// **'Privacy Information'**
  String get privacyInformation;

  /// Dialog title asking if user wants to end conversation
  ///
  /// In en, this message translates to:
  /// **'Finished Conversation?'**
  String get finishedConversation;

  /// No description provided for @syncGoogleAccount.
  ///
  /// In en, this message translates to:
  /// **'Sync with your Google account'**
  String get syncGoogleAccount;

  /// Pairing title for Neo One device
  ///
  /// In en, this message translates to:
  /// **'Put Neo One in Pairing Mode'**
  String get pairingTitleNeoOne;

  /// Credit line for translations
  ///
  /// In en, this message translates to:
  /// **'translated by Omi'**
  String get translatedByOmi;

  /// Label of the field for an app's source repository when submitting an app
  ///
  /// In en, this message translates to:
  /// **'GitHub Repository URL'**
  String get githubRepositoryUrl;

  /// Label for read-only API key scope
  ///
  /// In en, this message translates to:
  /// **'Read Only'**
  String get readOnlyScope;

  /// Title of the Chat apps section and page, where people connect Telegram or iMessage to chat with Omi
  ///
  /// In en, this message translates to:
  /// **'Chat apps'**
  String get chatAppsChannelsTitle;

  /// Capability bullet
  ///
  /// In en, this message translates to:
  /// **'Answers questions about your conversations and memories'**
  String get chatAppsDoesAnswer;

  /// Error message when generation fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start generation. Please try again.'**
  String get wrappedFailedToStartGeneration;

  /// Storage location label for SD card
  ///
  /// In en, this message translates to:
  /// **'SD Card'**
  String get storageLocationSdCard;

  /// Ask suggestion
  ///
  /// In en, this message translates to:
  /// **'What did I decide today?'**
  String get askSuggestDecide;

  /// Close button text
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get close;

  /// Payment method name for PayPal
  ///
  /// In en, this message translates to:
  /// **'PayPal'**
  String get paymentMethodPayPal;

  /// Number of apps listed on a category page in the app store, above the list
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 app} other{{count} apps}}'**
  String categoryAppCount(int count);

  /// Label above suggested people when Omi has no voice comparison.
  ///
  /// In en, this message translates to:
  /// **'People you talked to recently'**
  String get speakerTagPromptRecentPeople;

  /// No description provided for @actionCreateMemories.
  ///
  /// In en, this message translates to:
  /// **'Create memories'**
  String get actionCreateMemories;

  /// Instructions for task management gestures
  ///
  /// In en, this message translates to:
  /// **'Swipe tasks to indent, drag between categories'**
  String get swipeTasksToIndent;

  /// Title for create account page
  ///
  /// In en, this message translates to:
  /// **'Create Account'**
  String get createAccountTitle;

  /// Dialog title when model is not downloaded
  ///
  /// In en, this message translates to:
  /// **'Model Required'**
  String get modelRequired;

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Save Memory'**
  String get saveMemory;

  /// Success message when ClickUp OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to ClickUp!'**
  String get successfullyConnectedClickUp;

  /// Description for pending files in manage storage sheet
  ///
  /// In en, this message translates to:
  /// **'Not yet synced to your phone'**
  String get notYetSynced;

  /// Status when pendant is synced
  ///
  /// In en, this message translates to:
  /// **'Pendant is up to date'**
  String get pendantUpToDate;

  /// No description provided for @categoryProductivityTools.
  ///
  /// In en, this message translates to:
  /// **'Productivity & Tools'**
  String get categoryProductivityTools;

  /// Refresh button
  ///
  /// In en, this message translates to:
  /// **'Refresh'**
  String get refresh;

  /// Message explaining what happens when sync is cancelled
  ///
  /// In en, this message translates to:
  /// **'Data already downloaded will be saved. You can resume later.'**
  String get cancelSyncMessage;

  /// Native file-picker dialog title when choosing an app icon or thumbnail image on web
  ///
  /// In en, this message translates to:
  /// **'Select an Image File'**
  String get selectImageFileTitle;

  /// Error message when file picker fails to open
  ///
  /// In en, this message translates to:
  /// **'Error opening file picker: {message}'**
  String importErrorOpeningFilePicker(String message);

  /// Error when link generation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to generate conversation link'**
  String get failedToGenerateConversationLink;

  /// Error message when voice transcription fails
  ///
  /// In en, this message translates to:
  /// **'Failed to transcribe audio'**
  String get voiceFailedToTranscribe;

  /// Button text to view all items
  ///
  /// In en, this message translates to:
  /// **'View All'**
  String get viewAll;

  /// Label shown above newly created API key
  ///
  /// In en, this message translates to:
  /// **'Your new key:'**
  String get yourNewKey;

  /// Title of the page (and the button label) that shows conversations on a map
  ///
  /// In en, this message translates to:
  /// **'Conversation Map'**
  String get conversationMap;

  /// Button that opens support
  ///
  /// In en, this message translates to:
  /// **'Contact Support'**
  String get contactSupportAction;

  /// Abbreviated Sunday
  ///
  /// In en, this message translates to:
  /// **'Sun'**
  String get weekdaySun;

  /// Daily summary detail - summaryNotFound
  ///
  /// In en, this message translates to:
  /// **'Summary not found'**
  String get summaryNotFound;

  /// No description provided for @shortConversationThreshold.
  ///
  /// In en, this message translates to:
  /// **'Short Conversation Threshold'**
  String get shortConversationThreshold;

  /// No description provided for @dailyRecapsDescription.
  ///
  /// In en, this message translates to:
  /// **'Your daily recaps will appear here once generated'**
  String get dailyRecapsDescription;

  /// No description provided for @phoneCallsWithOmi.
  ///
  /// In en, this message translates to:
  /// **'Phone Calls with Omi'**
  String get phoneCallsWithOmi;

  /// Validation error when paid app has no payment plan or price
  ///
  /// In en, this message translates to:
  /// **'Please select a payment plan and enter a price for your app'**
  String get addAppSelectPaymentPlan;

  /// Final delete confirmation message
  ///
  /// In en, this message translates to:
  /// **'This action is irreversible and will permanently delete your account and all associated data. Are you sure you want to proceed?'**
  String get deleteAccountFinal;

  /// No description provided for @gettingAudioFiles.
  ///
  /// In en, this message translates to:
  /// **'Getting audio files…'**
  String get gettingAudioFiles;

  /// Label for default Omi STT provider
  ///
  /// In en, this message translates to:
  /// **'Omi'**
  String get omiSttProvider;

  /// No description provided for @port.
  ///
  /// In en, this message translates to:
  /// **'Port'**
  String get port;

  /// Toast after pinning a person.
  ///
  /// In en, this message translates to:
  /// **'{name} pinned'**
  String personPinnedToast(String name);

  /// Label for conversations stat in Wrapped
  ///
  /// In en, this message translates to:
  /// **'conversations'**
  String get wrappedConversations;

  /// Plans sheet highlight: which platforms Omi runs on
  ///
  /// In en, this message translates to:
  /// **'Available on Mac, mobile, and web'**
  String get availableOnMacMobileWeb;

  /// August month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Aug'**
  String get monthAug;

  /// Error message when summary generation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to generate summary. Make sure you have conversations for that day.'**
  String get failedToGenerateSummary;

  /// Message when plan has ended
  ///
  /// In en, this message translates to:
  /// **'Your plan ended on {date}.\nResubscribe now - you\'ll be charged immediately for a new billing period.'**
  String planEndedOn(String date);

  /// Option to create an app
  ///
  /// In en, this message translates to:
  /// **'Create an App'**
  String get createAnApp;

  /// Loading text while cancelling
  ///
  /// In en, this message translates to:
  /// **'Cancelling…'**
  String get cancelling;

  /// Second line of header for top days card
  ///
  /// In en, this message translates to:
  /// **'Top Days'**
  String get wrappedTopDaysHeader;

  /// Cancel button of the discard-changes dialog; returns to the editor
  ///
  /// In en, this message translates to:
  /// **'Keep Editing'**
  String get keepEditing;

  /// Shown in the Ignored Voices sheet when there are none.
  ///
  /// In en, this message translates to:
  /// **'No ignored voices'**
  String get ignoredVoicesEmpty;

  /// Warning that action is permanent
  ///
  /// In en, this message translates to:
  /// **'This cannot be undone.'**
  String get cannotBeUndone;

  /// No description provided for @usersPayToUse.
  ///
  /// In en, this message translates to:
  /// **'Users pay to use your app'**
  String get usersPayToUse;

  /// Error message for file upload limit
  ///
  /// In en, this message translates to:
  /// **'You can only upload 4 files at a time'**
  String get maxFilesUploadError;

  /// Message shown when device firmware is current
  ///
  /// In en, this message translates to:
  /// **'Your device is up to date'**
  String get yourDeviceIsUpToDate;

  /// Error when apps fail to load
  ///
  /// In en, this message translates to:
  /// **'Unable to fetch apps :(\n\nPlease check your internet connection and try again.'**
  String get unableToFetchApps;

  /// Error toast
  ///
  /// In en, this message translates to:
  /// **'Couldn’t send your correction. Try again.'**
  String get entityCorrectionFailed;

  /// No description provided for @alreadyAuthorized.
  ///
  /// In en, this message translates to:
  /// **'Already Authorized'**
  String get alreadyAuthorized;

  /// Warning about on-device vs cloud quality
  ///
  /// In en, this message translates to:
  /// **'Speed and accuracy may be lower than Cloud models.'**
  String get speedAccuracyLower;

  /// Optional iOS 27 search phrase guidance appended to the Shortcuts setup hint; searchPhrase is a literal English Siri phrase
  ///
  /// In en, this message translates to:
  /// **' You can also say “{searchPhrase} for what I did today.”'**
  String siriShortcutsSearchHint(String searchPhrase);

  /// Unlimited plan name
  ///
  /// In en, this message translates to:
  /// **'Unlimited Plan'**
  String get unlimitedPlan;

  /// Link text to contact support
  ///
  /// In en, this message translates to:
  /// **'Contact Support?'**
  String get contactSupport;

  /// Error message for goal limit
  ///
  /// In en, this message translates to:
  /// **'Maximum {count} goals allowed'**
  String maximumGoalsAllowed(int count);

  /// Warning shown when on-device storage is 95% or more full
  ///
  /// In en, this message translates to:
  /// **'Device nearly full — sync to free space.'**
  String get deviceStorageNearlyFull;

  /// Title for date picker sheet
  ///
  /// In en, this message translates to:
  /// **'Set Due Date'**
  String get setDueDate;

  /// Label showing number of private apps
  ///
  /// In en, this message translates to:
  /// **'Private Apps ({count})'**
  String privateAppsCount(String count);

  /// Menu item that starts picking people to delete (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Select People'**
  String get selectPeople;

  /// No description provided for @capabilityChat.
  ///
  /// In en, this message translates to:
  /// **'Chat'**
  String get capabilityChat;

  /// Page title listing a chat app's chats
  ///
  /// In en, this message translates to:
  /// **'{app} chats'**
  String chatAppsChannelChats(String app);

  /// Title for the 'transcribe later' capture-mode toggle in device settings
  ///
  /// In en, this message translates to:
  /// **'Transcribe Later'**
  String get transcribeLaterTitle;

  /// Error message when Asana OAuth fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Asana'**
  String get failedToConnectAsana;

  /// Message showing user is on unlimited plan
  ///
  /// In en, this message translates to:
  /// **'You are on the Unlimited Plan.'**
  String get youAreOnUnlimitedPlan;

  /// Small all-caps tag: chat apps come with the Omi Pro plan
  ///
  /// In en, this message translates to:
  /// **'INCLUDED WITH OMI PRO'**
  String get chatAppsIncludedWithPro;

  /// Generic error message for key creation failure
  ///
  /// In en, this message translates to:
  /// **'Failed to create key. Please try again.'**
  String get failedToCreateKeyTryAgain;

  /// Title for the background connection mode toggle in device settings (Android only)
  ///
  /// In en, this message translates to:
  /// **'Background Mode'**
  String get backgroundModeTitle;

  /// Message of the dialog shown when leaving an editor with unsaved changes
  ///
  /// In en, this message translates to:
  /// **'Your unsaved changes will be lost.'**
  String get discardChangesMessage;

  /// Name of the Omi wearable pendant as a capture source (which device recorded a conversation)
  ///
  /// In en, this message translates to:
  /// **'Pendant'**
  String get captureSourcePendant;

  /// Banner message promoting task export integration feature
  ///
  /// In en, this message translates to:
  /// **'Export tasks with one tap!'**
  String get exportTasksWithOneTap;

  /// Abbreviation for Sunday
  ///
  /// In en, this message translates to:
  /// **'Sun'**
  String get sundayAbbr;

  /// Validation error when prompt is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter a prompt for your app'**
  String get pleaseEnterAppPrompt;

  /// Percentage of on-device storage used
  ///
  /// In en, this message translates to:
  /// **'{percent}% full'**
  String deviceStoragePercentFull(int percent);

  /// Title for developer settings page
  ///
  /// In en, this message translates to:
  /// **'Developer Settings'**
  String get developerSettings;

  /// No description provided for @selectYouFromList.
  ///
  /// In en, this message translates to:
  /// **'To tag yourself, please select \"You\" from the list.'**
  String get selectYouFromList;

  /// Delete now button
  ///
  /// In en, this message translates to:
  /// **'Delete Now'**
  String get deleteNow;

  /// Button text to install firmware update
  ///
  /// In en, this message translates to:
  /// **'Install Update'**
  String get installUpdate;

  /// Action to unpair device
  ///
  /// In en, this message translates to:
  /// **'Unpair Device'**
  String get unpairDevice;

  /// Row label for the assistant voice picker
  ///
  /// In en, this message translates to:
  /// **'Assistant Voice'**
  String get assistantVoice;

  /// Status message during app creation
  ///
  /// In en, this message translates to:
  /// **'Installing app…'**
  String get installingApp;

  /// Default title for funny moment in collage
  ///
  /// In en, this message translates to:
  /// **'Funny Moment'**
  String get wrappedFunnyMomentTitle;

  /// Error when checking notification permission fails
  ///
  /// In en, this message translates to:
  /// **'Failed to check Notification permission: {error}'**
  String onboardingFailedCheckNotification(String error);

  /// Button that starts an agent pass immediately. Title Case.
  ///
  /// In en, this message translates to:
  /// **'Run Now'**
  String get dreamReportRunNow;

  /// Value not set placeholder
  ///
  /// In en, this message translates to:
  /// **'Not set'**
  String get notSet;

  /// No description provided for @startVoiceRecording.
  ///
  /// In en, this message translates to:
  /// **'Start voice recording'**
  String get startVoiceRecording;

  /// No description provided for @userInformation.
  ///
  /// In en, this message translates to:
  /// **'User Information'**
  String get userInformation;

  /// Uppercase label for struggle tile in collage
  ///
  /// In en, this message translates to:
  /// **'STRUGGLE'**
  String get wrappedStruggleLabel;

  /// Filter option for external wisdom/advice
  ///
  /// In en, this message translates to:
  /// **'Insights'**
  String get filterInteresting;

  /// How many devices recorded this conversation, on the conversation header
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 recording} other{{count} recordings}}'**
  String captureRecordingsCount(int count);

  /// No description provided for @addOrChangeYourPaymentMethod.
  ///
  /// In en, this message translates to:
  /// **'Add or change your payment method'**
  String get addOrChangeYourPaymentMethod;

  /// Empty state title when apps cannot be loaded due to connectivity
  ///
  /// In en, this message translates to:
  /// **'Unable to load apps'**
  String get unableToLoadApps;

  /// Description for firmware update dialog with version parameter
  ///
  /// In en, this message translates to:
  /// **'A new firmware update ({version}) is available for your Omi device. Would you like to update now?'**
  String firmwareUpdateAvailableDescription(String version);

  /// Cancel reason option
  ///
  /// In en, this message translates to:
  /// **'Too expensive'**
  String get cancelReasonTooExpensive;

  /// Warning about USB connection during firmware update
  ///
  /// In en, this message translates to:
  /// **'USB connection during updates may damage your device.'**
  String get firmwareUsbWarning;

  /// No description provided for @authAccessMessage.
  ///
  /// In en, this message translates to:
  /// **'You\'ll need to authorize Omi to access your {appName} data. This will open your browser for authentication.'**
  String authAccessMessage(String appName);

  /// Hint text explaining conversation only ends manually
  ///
  /// In en, this message translates to:
  /// **'Conversation will only end manually.'**
  String get conversationEndsManually;

  /// Conversation detail badge shown when capture evidence says the recording is incomplete.
  ///
  /// In en, this message translates to:
  /// **'Partial recording'**
  String get partialRecording;

  /// Section label for anonymous diagnostics sent to developers. 'Omi' is a product name.
  ///
  /// In en, this message translates to:
  /// **'Reported to the Omi team'**
  String get dreamReportFeedback;

  /// No description provided for @shareAudio.
  ///
  /// In en, this message translates to:
  /// **'Share Audio'**
  String get shareAudio;

  /// Description for import data feature
  ///
  /// In en, this message translates to:
  /// **'Import data from other sources'**
  String get importDataFromOtherSources;

  /// Message shown when all premium minutes are used
  ///
  /// In en, this message translates to:
  /// **'Premium minutes used.'**
  String get premiumMinutesUsed;

  /// Button text to upgrade to unlimited plan from phone calls upsell
  ///
  /// In en, this message translates to:
  /// **'Upgrade to Unlimited'**
  String get phoneCallsUpgradeButton;

  /// No description provided for @omiUnlimited.
  ///
  /// In en, this message translates to:
  /// **'Omi Unlimited'**
  String get omiUnlimited;

  /// Default text for unknown device model
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get unknownDevice;

  /// Error when import fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start import. Please try again.'**
  String get failedToStartImport;

  /// Hint text for the action items search field
  ///
  /// In en, this message translates to:
  /// **'Search tasks'**
  String get searchActionItems;

  /// Label for the Whisper on-device transcription model selector
  ///
  /// In en, this message translates to:
  /// **'Whisper Model'**
  String get whisperModel;

  /// No description provided for @searchContacts.
  ///
  /// In en, this message translates to:
  /// **'Search contacts'**
  String get searchContacts;

  /// Footnote in select mode under the Pinned group.
  ///
  /// In en, this message translates to:
  /// **'Select All skips pinned people. Delete them one at a time from their page.'**
  String get selectAllSkipsPinned;

  /// Introduction text for speech profile setup
  ///
  /// In en, this message translates to:
  /// **'Let\'s set up your speech profile. You can always change it later'**
  String get speechProfileIntro;

  /// Label for realtime listening trigger
  ///
  /// In en, this message translates to:
  /// **'Realtime Listening'**
  String get realtimeListening;

  /// Error message shown when a deep-linked app cannot be found
  ///
  /// In en, this message translates to:
  /// **'Oops! Looks like the app you are looking for is not available.'**
  String get appNotAvailable;

  /// Hint text for name input field
  ///
  /// In en, this message translates to:
  /// **'Enter your name'**
  String get enterYourName;

  /// Permission type label for trigger permissions
  ///
  /// In en, this message translates to:
  /// **'Trigger'**
  String get permissionTypeTrigger;

  /// Info message about automatic graph building
  ///
  /// In en, this message translates to:
  /// **'Your knowledge graph will be built automatically as you create new memories.'**
  String get knowledgeGraphWillBuildAutomatically;

  /// Noun used in the copy confirmation, e.g. 'Link copied'
  ///
  /// In en, this message translates to:
  /// **'Link'**
  String get chatAppsLink;

  /// Unit label for minutes
  ///
  /// In en, this message translates to:
  /// **'minutes'**
  String get minutes;

  /// Navigation label for actions page
  ///
  /// In en, this message translates to:
  /// **'Actions'**
  String get actions;

  /// No description provided for @connectRayBanMeta.
  ///
  /// In en, this message translates to:
  /// **'Connect Ray-Ban Meta'**
  String get connectRayBanMeta;

  /// September month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Sep'**
  String get monthSep;

  /// Subtitle for share to contacts sheet
  ///
  /// In en, this message translates to:
  /// **'Select contacts to share your conversation summary'**
  String get selectContactsToShareSummary;

  /// Placeholder when no payment plan is selected
  ///
  /// In en, this message translates to:
  /// **'None Selected'**
  String get paymentNoneSelected;

  /// Swipe action and menu item: pin this person (Title Case verb).
  ///
  /// In en, this message translates to:
  /// **'Pin'**
  String get pinAction;

  /// October month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Oct'**
  String get monthOct;

  /// Button text to start recording
  ///
  /// In en, this message translates to:
  /// **'Start Recording'**
  String get startRecording;

  /// Generic error message
  ///
  /// In en, this message translates to:
  /// **'Something went wrong! Please try again later.'**
  String get somethingWentWrong;

  /// No description provided for @largeTimeGapsDetected.
  ///
  /// In en, this message translates to:
  /// **'Large time gaps detected ({gaps})'**
  String largeTimeGapsDetected(String gaps);

  /// No description provided for @phoneEnterNumber.
  ///
  /// In en, this message translates to:
  /// **'Enter number'**
  String get phoneEnterNumber;

  /// Cancel consequence
  ///
  /// In en, this message translates to:
  /// **'No longer have unlimited access at the end of your billing period.'**
  String get cancelConsequenceNoAccess;

  /// No description provided for @appleHealthDeniedTitle.
  ///
  /// In en, this message translates to:
  /// **'Apple Health access denied'**
  String get appleHealthDeniedTitle;

  /// Menu item to delete app or persona
  ///
  /// In en, this message translates to:
  /// **'Delete {item}'**
  String deleteItemTitle(String item);

  /// Error message for invalid integration URL
  ///
  /// In en, this message translates to:
  /// **'Invalid integration URL'**
  String get invalidIntegrationUrl;

  /// Heading for empty state welcome
  ///
  /// In en, this message translates to:
  /// **'Ready for Tasks'**
  String get welcomeActionItemsTitle;

  /// Dialog description explaining app update will be reviewed
  ///
  /// In en, this message translates to:
  /// **'Your changes go live after our team reviews them.'**
  String get updateAppConfirmation;

  /// No description provided for @corruptedStatus.
  ///
  /// In en, this message translates to:
  /// **'Corrupted'**
  String get corruptedStatus;

  /// Error message when trying to rate without internet
  ///
  /// In en, this message translates to:
  /// **'Can\'t rate app without internet connection.'**
  String get cantRateWithoutInternet;

  /// Checkbox text to prevent showing dialog again
  ///
  /// In en, this message translates to:
  /// **'Don\'t show again'**
  String get dontShowAgain;

  /// Hardware revision label
  ///
  /// In en, this message translates to:
  /// **'Hardware Revision'**
  String get hardwareRevision;

  /// Empty state message for date filter
  ///
  /// In en, this message translates to:
  /// **'Try selecting a different date'**
  String get trySelectingDifferentDate;

  /// Daily summary detail - learnings
  ///
  /// In en, this message translates to:
  /// **'Learnings'**
  String get learnings;

  /// Error message when Todoist OAuth fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Todoist'**
  String get failedToConnectTodoist;

  /// Subtitle for create API key sheet
  ///
  /// In en, this message translates to:
  /// **'Access your data programmatically'**
  String get accessDataProgrammatically;

  /// Progress label showing current/total items
  ///
  /// In en, this message translates to:
  /// **'Processing {current}/{total}'**
  String processingProgress(int current, int total);

  /// Snackbar message after saving API environment preference
  ///
  /// In en, this message translates to:
  /// **'Saved. Close and reopen the app to apply.'**
  String get apiEnvSavedRestartRequired;

  /// No description provided for @syncCardWaitingInternet.
  ///
  /// In en, this message translates to:
  /// **'Waiting for internet'**
  String get syncCardWaitingInternet;

  /// Button that opens the app store for a required cutover upgrade
  ///
  /// In en, this message translates to:
  /// **'Open Store'**
  String get accountCutoverOpenStore;

  /// No description provided for @processedConversations.
  ///
  /// In en, this message translates to:
  /// **'Processed Conversations'**
  String get processedConversations;

  /// Loading message while preparing form
  ///
  /// In en, this message translates to:
  /// **'Hold on, we are preparing the form for you'**
  String get holdOnPreparingForm;

  /// Status message while waiting for device connection
  ///
  /// In en, this message translates to:
  /// **'Waiting for device…'**
  String get waitingForDevice;

  /// Learn more link
  ///
  /// In en, this message translates to:
  /// **'Learn more…'**
  String get learnMore;

  /// Error message when exception occurs during app creation
  ///
  /// In en, this message translates to:
  /// **'An error occurred while creating the app'**
  String get aiGenErrorWhileCreatingApp;

  /// Warning message for deleting all files
  ///
  /// In en, this message translates to:
  /// **'This will delete both synced and pending recordings. Pending recordings have NOT been synced and will be permanently lost. This can\'t be undone.'**
  String get deleteAllFilesWarning;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Words heard'**
  String get usageWordsHeard;

  /// No description provided for @importDataDescription.
  ///
  /// In en, this message translates to:
  /// **'Import data from other sources'**
  String get importDataDescription;

  /// No description provided for @raybanMetaImageCaptureUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Unavailable in audio-only mode'**
  String get raybanMetaImageCaptureUnavailable;

  /// Message shown when app is rejected
  ///
  /// In en, this message translates to:
  /// **'Your app has been rejected. Please update the app details and resubmit for review.'**
  String get appRejectedMessage;

  /// Listening pill, after the status, when the pendant dropped and is not reconnecting yet: the one-line reassurance. The details sheet has the full explanation.
  ///
  /// In en, this message translates to:
  /// **'Omi reconnects on its own'**
  String get capturePendantDisconnectedShort;

  /// No description provided for @improveSpeechProfileDesc.
  ///
  /// In en, this message translates to:
  /// **'We use recordings to further train and enhance your personal speech profile.'**
  String get improveSpeechProfileDesc;

  /// Bottom sheet title for voice response mode selector
  ///
  /// In en, this message translates to:
  /// **'When to speak responses'**
  String get voiceResponseModeTitle;

  /// Error message when deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete task'**
  String get failedToDeleteItem;

  /// Label for firmware version
  ///
  /// In en, this message translates to:
  /// **'Firmware'**
  String get firmware;

  /// Error message when task could not be added to a service
  ///
  /// In en, this message translates to:
  /// **'Failed to add to {serviceName}'**
  String failedToAddToService(String serviceName);

  /// Feature: ask Omi anything
  ///
  /// In en, this message translates to:
  /// **'Ask Omi anything about your life'**
  String get askOmiAnything;

  /// No description provided for @integrationsFooter.
  ///
  /// In en, this message translates to:
  /// **'Connect your apps to view data and metrics in chat.'**
  String get integrationsFooter;

  /// Loading indicator text
  ///
  /// In en, this message translates to:
  /// **'Loading…'**
  String get loading;

  /// Text shown to collapse expanded content, with up arrow
  ///
  /// In en, this message translates to:
  /// **'show less ↑'**
  String get showLess;

  /// Capability bullet with a cross: something Omi never does
  ///
  /// In en, this message translates to:
  /// **'Never messages other people for you'**
  String get chatAppsNeverMessagesOthers;

  /// No description provided for @scopeUserName.
  ///
  /// In en, this message translates to:
  /// **'User Name'**
  String get scopeUserName;

  /// Mute state
  ///
  /// In en, this message translates to:
  /// **'Mute'**
  String get mute;

  /// Step 3: Server processing
  ///
  /// In en, this message translates to:
  /// **'The server processes the audio files and creates memories'**
  String get serverProcessesAudio;

  /// Notification body shown when conversations are merged successfully
  ///
  /// In en, this message translates to:
  /// **'{count} conversations have been merged successfully'**
  String mergeConversationsSuccessBody(int count);

  /// No description provided for @pairingSuccessful.
  ///
  /// In en, this message translates to:
  /// **'PAIRING SUCCESSFUL'**
  String get pairingSuccessful;

  /// No description provided for @websocketUrl.
  ///
  /// In en, this message translates to:
  /// **'WebSocket URL'**
  String get websocketUrl;

  /// Default name/relationship for buddy
  ///
  /// In en, this message translates to:
  /// **'Friend'**
  String get wrappedFriend;

  /// Notification frequency level - high
  ///
  /// In en, this message translates to:
  /// **'High'**
  String get frequencyHigh;

  /// Error title when processing fails
  ///
  /// In en, this message translates to:
  /// **'Processing Failed'**
  String get processingFailed;

  /// Lowercase word for data in migration context
  ///
  /// In en, this message translates to:
  /// **'data'**
  String get dataLowercase;

  /// Tapping a saved device that is not advertising
  ///
  /// In en, this message translates to:
  /// **'{deviceName} is offline. Press its button to wake it, then try again.'**
  String deviceOfflineWakeHint(String deviceName);

  /// No description provided for @updatedConversations.
  ///
  /// In en, this message translates to:
  /// **'Updated Conversations'**
  String get updatedConversations;

  /// No description provided for @phoneGetStarted.
  ///
  /// In en, this message translates to:
  /// **'Get Started'**
  String get phoneGetStarted;

  /// AppBar title for recording detail page
  ///
  /// In en, this message translates to:
  /// **'Recording Details'**
  String get recordingDetails;

  /// Title for create API key sheet
  ///
  /// In en, this message translates to:
  /// **'Create API Key'**
  String get createApiKey;

  /// No description provided for @anyoneWithLinkCanView.
  ///
  /// In en, this message translates to:
  /// **'Anyone with the link can view'**
  String get anyoneWithLinkCanView;

  /// Placeholder row when every task of a conversation is done
  ///
  /// In en, this message translates to:
  /// **'No pending tasks'**
  String get noPendingTasks;

  /// Message indicating a feature is coming soon
  ///
  /// In en, this message translates to:
  /// **'This feature is coming soon!'**
  String get featureComingSoon;

  /// Description of bluetooth transfer method card
  ///
  /// In en, this message translates to:
  /// **'Uses standard Bluetooth Low Energy connection. Slower but doesn\'t affect your WiFi connection.'**
  String get bluetoothMethodDescription;

  /// Empty state when the link no longer exists
  ///
  /// In en, this message translates to:
  /// **'Not connected'**
  String get chatAppsNotConnectedTitle;

  /// Label for the most intense/stressful day
  ///
  /// In en, this message translates to:
  /// **'Most Intense'**
  String get wrappedMostIntenseDay;

  /// Label for yesterday date
  ///
  /// In en, this message translates to:
  /// **'Yesterday'**
  String get yesterday;

  /// No description provided for @requestConfiguration.
  ///
  /// In en, this message translates to:
  /// **'Request Configuration'**
  String get requestConfiguration;

  /// AM time indicator
  ///
  /// In en, this message translates to:
  /// **'AM'**
  String get timeAM;

  /// Footer description for the auto-remove synced copies setting
  ///
  /// In en, this message translates to:
  /// **'Deletes local copies {days} days after sync. Cloud copies are kept.'**
  String autoRemoveSyncedCopiesDescription(int days);

  /// Privacy note on the Telegram connect sheet
  ///
  /// In en, this message translates to:
  /// **'Your chats with Omi are also stored by Telegram. Omi only answers you, never other people, and you can disconnect anytime.'**
  String get chatAppsTelegramPrivacyNote;

  /// Label for speaker in transcript
  ///
  /// In en, this message translates to:
  /// **'Speaker {speakerId}'**
  String speakerWithId(String speakerId);

  /// Value when a task has no due date
  ///
  /// In en, this message translates to:
  /// **'None'**
  String get reviewNoDate;

  /// Transcript panel title
  ///
  /// In en, this message translates to:
  /// **'Transcript'**
  String get transcript;

  /// Device diagnostics support upload
  ///
  /// In en, this message translates to:
  /// **'Could not send diagnostics to support. Please try again.'**
  String get deviceDiagnosticsUploadFailed;

  /// Message shown when there are no folders to move a conversation to
  ///
  /// In en, this message translates to:
  /// **'No folders available'**
  String get noFoldersAvailable;

  /// Validation error when no app category selected
  ///
  /// In en, this message translates to:
  /// **'Please select a category for your app'**
  String get addAppSelectCategory;

  /// Navigation label for conversations page
  ///
  /// In en, this message translates to:
  /// **'Conversations'**
  String get conversations;

  /// Message shown on locked memory items
  ///
  /// In en, this message translates to:
  /// **'Upgrade to Unlimited'**
  String get upgradeToUnlimited;

  /// Title on final delete confirmation step
  ///
  /// In en, this message translates to:
  /// **'Delete Your Account?'**
  String get deleteFlowConfirmTitle;

  /// Body for account cutover migration-maintenance blocking screen
  ///
  /// In en, this message translates to:
  /// **'Your account is migrating. Product features are paused until migration finishes.'**
  String get accountCutoverMigrationInProgressMessage;

  /// Status shown next to a permission the user has granted
  ///
  /// In en, this message translates to:
  /// **'Allowed'**
  String get permissionAllowed;

  /// Instruction
  ///
  /// In en, this message translates to:
  /// **'Press done to save'**
  String get pressDoneToSave;

  /// Listening stat title
  ///
  /// In en, this message translates to:
  /// **'Listening'**
  String get listening;

  /// No description provided for @audioReady.
  ///
  /// In en, this message translates to:
  /// **'Audio Ready'**
  String get audioReady;

  /// No description provided for @freeForEveryone.
  ///
  /// In en, this message translates to:
  /// **'Free for everyone'**
  String get freeForEveryone;

  /// Message while building knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Building your knowledge graph from memories…'**
  String get buildingKnowledgeGraphFromMemories;

  /// Section title for on-device transcription settings
  ///
  /// In en, this message translates to:
  /// **'On-Device Transcription'**
  String get onDeviceTranscription;

  /// Error message with details
  ///
  /// In en, this message translates to:
  /// **'Error: {error}'**
  String errorWithMessage(String error);

  /// Error shown when there is no internet connection
  ///
  /// In en, this message translates to:
  /// **'You\'re offline. Check your connection and try again.'**
  String get chatAppsProblemOffline;

  /// No description provided for @callAlreadyInProgress.
  ///
  /// In en, this message translates to:
  /// **'A call is already in progress'**
  String get callAlreadyInProgress;

  /// Question card: confirm the spelling of a name or term
  ///
  /// In en, this message translates to:
  /// **'How is this spelled?'**
  String get reviewQuestionSpelling;

  /// Firmware update step title about internet connection
  ///
  /// In en, this message translates to:
  /// **'Stable Connection'**
  String get firmwareStableConnection;

  /// No description provided for @categoryOther.
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get categoryOther;

  /// No description provided for @perMonthLabel.
  ///
  /// In en, this message translates to:
  /// **'/ month'**
  String get perMonthLabel;

  /// Onboarding step description for completion
  ///
  /// In en, this message translates to:
  /// **'You\'re all set'**
  String get onboardingYoureAllSet;

  /// Button label to resume recording
  ///
  /// In en, this message translates to:
  /// **'Resume Recording'**
  String get resumeRecording;

  /// Feedback subtitle for audio quality
  ///
  /// In en, this message translates to:
  /// **'We\'d love to understand what went wrong.'**
  String get feedbackSubtitleAudioQuality;

  /// Accessibility label for the play button of the audio clip
  ///
  /// In en, this message translates to:
  /// **'Play clip'**
  String get speakerTagPromptPlayClip;

  /// Privacy page - anonymityAndPrivacy
  ///
  /// In en, this message translates to:
  /// **'Anonymity and Privacy'**
  String get anonymityAndPrivacy;

  /// Info message when there are no memories to delete
  ///
  /// In en, this message translates to:
  /// **'No memories to delete'**
  String get noMemoriesToDelete;

  /// No description provided for @syncStepProcess.
  ///
  /// In en, this message translates to:
  /// **'Transcribe'**
  String get syncStepProcess;

  /// No description provided for @callStateRinging.
  ///
  /// In en, this message translates to:
  /// **'Ringing…'**
  String get callStateRinging;

  /// Link text to setup on-device transcription
  ///
  /// In en, this message translates to:
  /// **'Setup on-device'**
  String get setupOnDevice;

  /// No description provided for @creatorPayouts.
  ///
  /// In en, this message translates to:
  /// **'Creator Payouts'**
  String get creatorPayouts;

  /// Title for older device warning dialog
  ///
  /// In en, this message translates to:
  /// **'Older Device Detected'**
  String get olderDeviceDetected;

  /// No description provided for @deletePhoneNumberWarning.
  ///
  /// In en, this message translates to:
  /// **'You\'ll need to verify again to make calls'**
  String get deletePhoneNumberWarning;

  /// Success message when app visibility is changed
  ///
  /// In en, this message translates to:
  /// **'App visibility changed successfully. It may take a few minutes to reflect.'**
  String get appVisibilityChangedSuccessfully;

  /// Error message when creating action item fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create task'**
  String get failedToCreateActionItem;

  /// Generic error when selecting files fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting files. Please try again.'**
  String get msgSelectFilesGenericError;

  /// Shown when offline sync stalls because the Limitless Pendant is actively recording; it cannot serve stored audio until recording stops
  ///
  /// In en, this message translates to:
  /// **'Your Pendant is still recording, so its stored audio can\'t be transferred. Press the Pendant\'s button to stop recording, then sync again.'**
  String get pendantRecordingSyncBlocked;

  /// Error message when merge fails
  ///
  /// In en, this message translates to:
  /// **'Failed to start merge'**
  String get failedToStartMerge;

  /// No description provided for @shortcutChangeInstruction.
  ///
  /// In en, this message translates to:
  /// **'Click on a shortcut to change it. Press Escape to cancel.'**
  String get shortcutChangeInstruction;

  /// Settings group: notifications, home screen and conversation display
  ///
  /// In en, this message translates to:
  /// **'Notifications & Display'**
  String get notificationsAndDisplay;

  /// Title for Stripe setup page
  ///
  /// In en, this message translates to:
  /// **'Get paid for your app sales through Stripe'**
  String get getPaidThroughStripe;

  /// Abbreviated Wednesday
  ///
  /// In en, this message translates to:
  /// **'Wed'**
  String get weekdayWed;

  /// Button text to send a message or reply
  ///
  /// In en, this message translates to:
  /// **'Send'**
  String get send;

  /// Description of iOS native speech recognition
  ///
  /// In en, this message translates to:
  /// **'Your devices native speech engine will be used. No model download required.'**
  String get nativeEngineNoDownload;

  /// Label for actions stat
  ///
  /// In en, this message translates to:
  /// **'actions'**
  String get wrappedActions;

  /// Conversation timeout configuration subtitle
  ///
  /// In en, this message translates to:
  /// **'How long Omi waits in silence before ending a conversation'**
  String get conversationTimeoutConfig;

  /// Label for microphone
  ///
  /// In en, this message translates to:
  /// **'Mic'**
  String get mic;

  /// Output consequence for Always mode with connected headphones
  ///
  /// In en, this message translates to:
  /// **'Plays through {device}.'**
  String deviceOnboardingVoiceReplyStatusAlwaysHeadphones(String device);

  /// Error message when reply fails
  ///
  /// In en, this message translates to:
  /// **'Failed to send reply: {error}'**
  String failedToSendReply(String error);

  /// Whisper model size: tiny
  ///
  /// In en, this message translates to:
  /// **'Tiny'**
  String get whisperModelSizeTiny;

  /// Answer chip on the "Is this you?" voice card: the voice is not the user (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Not Me'**
  String get speakerTagPromptNotMeAction;

  /// Title for setup instructions page
  ///
  /// In en, this message translates to:
  /// **'Setup Instructions'**
  String get setupInstructions;

  /// Text when search returns no results
  ///
  /// In en, this message translates to:
  /// **'No languages found'**
  String get noLanguagesFound;

  /// Section header for experimental features
  ///
  /// In en, this message translates to:
  /// **'Experimental'**
  String get experimental;

  /// Button label to continue recording
  ///
  /// In en, this message translates to:
  /// **'Continue Recording'**
  String get continueRecording;

  /// No description provided for @selectDefaultRepoDesc.
  ///
  /// In en, this message translates to:
  /// **'Select a default repository for creating issues. You can still specify a different repository when creating issues.'**
  String get selectDefaultRepoDesc;

  /// Title of the sheet showing tasks someone shared with the user
  ///
  /// In en, this message translates to:
  /// **'{name} shared {count, plural, =1{1 task} other{{count} tasks}}'**
  String sharedTasksTitle(String name, int count);

  /// Explanation of why permissions are needed
  ///
  /// In en, this message translates to:
  /// **'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.'**
  String get permissionsRequiredDesc;

  /// Device Diagnostics verdict detail; duration is the median reconnect time, e.g. 2s
  ///
  /// In en, this message translates to:
  /// **'Brief drops, back in about {duration} each time'**
  String diagnosticsVerdictReconnectsDetail(String duration);

  /// Status text shown during file transfer
  ///
  /// In en, this message translates to:
  /// **'Transferring…'**
  String get transferring;

  /// No description provided for @wordsUsedThisMonth.
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} words used this month'**
  String wordsUsedThisMonth(String used, String limit);

  /// Empty state message when no chat apps are enabled
  ///
  /// In en, this message translates to:
  /// **'No chat apps enabled.\nTap \"Enable Apps\" to add some.'**
  String get noChatAppsEnabled;

  /// Tip in sync info sheet
  ///
  /// In en, this message translates to:
  /// **'Keep your phone nearby for faster syncing'**
  String get tipKeepPhoneNearby;

  /// Error message when Google sign-in fails
  ///
  /// In en, this message translates to:
  /// **'Failed to sign in with Google, please try again.'**
  String get authFailedToSignInWithGoogle;

  /// Description for low notification frequency
  ///
  /// In en, this message translates to:
  /// **'Important things only, about 3–5 a day'**
  String get frequencyDescLow;

  /// No description provided for @availableTemplates.
  ///
  /// In en, this message translates to:
  /// **'Available Templates'**
  String get availableTemplates;

  /// App value proposition or description
  ///
  /// In en, this message translates to:
  /// **'Omi records your conversations and writes\nthe summary and to-dos for you.'**
  String get captureEveryMoment;

  /// Error message when data migration fails
  ///
  /// In en, this message translates to:
  /// **'An error occurred during migration. Please try again.'**
  String get migrationErrorOccurred;

  /// Completed label in actions card
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get wrappedCompletedLabel;

  /// Undo toast after answering the voice card with a person.
  ///
  /// In en, this message translates to:
  /// **'Labeled as {name}'**
  String speakerTagPromptLabeledToast(String name);

  /// Documentation button text
  ///
  /// In en, this message translates to:
  /// **'Docs'**
  String get docs;

  /// Label for date and time in details
  ///
  /// In en, this message translates to:
  /// **'Date & Time'**
  String get dateTimeLabel;

  /// Menu option to edit a folder
  ///
  /// In en, this message translates to:
  /// **'Edit Folder'**
  String get editFolder;

  /// Navigation label for apps page
  ///
  /// In en, this message translates to:
  /// **'Apps'**
  String get apps;

  /// Segment count (singular)
  ///
  /// In en, this message translates to:
  /// **'{count} segment'**
  String segmentsSingular(String count);

  /// Device settings menu item
  ///
  /// In en, this message translates to:
  /// **'Device Settings'**
  String get deviceSettings;

  /// Status when device is offline
  ///
  /// In en, this message translates to:
  /// **'Offline'**
  String get offline;

  /// Tooltip for create action item FAB
  ///
  /// In en, this message translates to:
  /// **'Create new task'**
  String get createActionItemTooltip;

  /// Forget device button
  ///
  /// In en, this message translates to:
  /// **'Forget Device'**
  String get forgetDevice;

  /// Home card that opens Review; a count badge sits beside it
  ///
  /// In en, this message translates to:
  /// **'Questions for you'**
  String get reviewEntryTitle;

  /// Error when email field is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter your email'**
  String get enterEmailError;

  /// Hint telling the app owner to repair their endpoint before re-enabling the app
  ///
  /// In en, this message translates to:
  /// **'Fix the endpoint first — re-enabling re-checks every configured URL.'**
  String get appDisabledOwnerHint;

  /// iMessage row subtitle before connecting
  ///
  /// In en, this message translates to:
  /// **'Text Omi from your phone number'**
  String get chatAppsIMessageSubtitle;

  /// No description provided for @tasksExportedOneApp.
  ///
  /// In en, this message translates to:
  /// **'Tasks can be exported to one app at a time.'**
  String get tasksExportedOneApp;

  /// How many people spoke, after the length in the transcript's heading: Transcript · 14 min · 2 speakers
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 speaker} other{{count} speakers}}'**
  String transcriptSpeakerCount(int count);

  /// Save button for goal
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get saveGoal;

  /// No description provided for @noBatteryDataYet.
  ///
  /// In en, this message translates to:
  /// **'No battery data yet'**
  String get noBatteryDataYet;

  /// No description provided for @chatUsedOfLimitMessages.
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} messages used this month'**
  String chatUsedOfLimitMessages(String used, String limit);

  /// Description for background activity permission
  ///
  /// In en, this message translates to:
  /// **'So Omi keeps capturing when the screen is off or you switch apps.'**
  String get backgroundActivityDesc;

  /// Error message when app update fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update app. Please try again later'**
  String get addAppUpdateFailed;

  /// Empty state title when the People search or filter matches nobody
  ///
  /// In en, this message translates to:
  /// **'No Matching People'**
  String get noMatchingPeople;

  /// Action in the linked calendar event sheet
  ///
  /// In en, this message translates to:
  /// **'Unlink Calendar Event'**
  String get unlinkCalendarEvent;

  /// No description provided for @regenerateRecap.
  ///
  /// In en, this message translates to:
  /// **'Regenerate Recap'**
  String get regenerateRecap;

  /// Menu option to delete synced recordings
  ///
  /// In en, this message translates to:
  /// **'Delete Synced'**
  String get deleteSynced;

  /// Placeholder text in a name input field
  ///
  /// In en, this message translates to:
  /// **'Their name'**
  String get speakerTagPromptNameHint;

  /// Label for free plan
  ///
  /// In en, this message translates to:
  /// **'Free Plan'**
  String get freePlan;

  /// Label for install count
  ///
  /// In en, this message translates to:
  /// **'INSTALLS'**
  String get installs;

  /// No description provided for @publicLabel.
  ///
  /// In en, this message translates to:
  /// **'Public'**
  String get publicLabel;

  /// Loading text when clearing chat
  ///
  /// In en, this message translates to:
  /// **'Deleting your messages from Omi\'s memory…'**
  String get deletingMessages;

  /// Snackbar message after pending files deleted
  ///
  /// In en, this message translates to:
  /// **'Pending recordings deleted'**
  String get pendingFilesDeleted;

  /// Button to check usage details
  ///
  /// In en, this message translates to:
  /// **'Check Usage'**
  String get checkUsage;

  /// No description provided for @addWordsDesc.
  ///
  /// In en, this message translates to:
  /// **'Names, terms, or uncommon words'**
  String get addWordsDesc;

  /// Confirmation toast
  ///
  /// In en, this message translates to:
  /// **'Thanks. Omi will fix it.'**
  String get entityCorrectionSaved;

  /// No description provided for @categoryEducation.
  ///
  /// In en, this message translates to:
  /// **'Education'**
  String get categoryEducation;

  /// Plan and usage menu item
  ///
  /// In en, this message translates to:
  /// **'Plan & Usage'**
  String get planAndUsage;

  /// Confirmation dialog title for deleting memory
  ///
  /// In en, this message translates to:
  /// **'Delete Memory'**
  String get deleteMemory;

  /// Data protection section title
  ///
  /// In en, this message translates to:
  /// **'Data Protection Level'**
  String get dataProtectionLevel;

  /// Duration in singular day
  ///
  /// In en, this message translates to:
  /// **'{count} day'**
  String timeDaySingular(int count);

  /// Dialog title when API key is successfully created
  ///
  /// In en, this message translates to:
  /// **'Key Created'**
  String get keyCreated;

  /// Label for date filter button
  ///
  /// In en, this message translates to:
  /// **'Date'**
  String get date;

  /// Migration progress message with item type and percentage
  ///
  /// In en, this message translates to:
  /// **'Migrating {itemType}… {percentage}%'**
  String migratingItemsProgress(String itemType, int percentage);

  /// enableLocalStorage label
  ///
  /// In en, this message translates to:
  /// **'Enable Local Storage'**
  String get enableLocalStorage;

  /// Notification title for omi app messages
  ///
  /// In en, this message translates to:
  /// **'Omi says'**
  String get omiSays;

  /// Section title for app metadata information
  ///
  /// In en, this message translates to:
  /// **'App Details'**
  String get appDetails;

  /// Loading message shown while audio waveform is being processed
  ///
  /// In en, this message translates to:
  /// **'Loading your recording…'**
  String get loadingYourRecording;

  /// Warning message in delete dialog
  ///
  /// In en, this message translates to:
  /// **'All conversations imported from Limitless are deleted. This can\'t be undone.'**
  String get deleteAllLimitlessWarning;

  /// No description provided for @combiningAudioFiles.
  ///
  /// In en, this message translates to:
  /// **'Combining audio files…'**
  String get combiningAudioFiles;

  /// No description provided for @suggestFollowUpQuestion.
  ///
  /// In en, this message translates to:
  /// **'Suggest follow up question'**
  String get suggestFollowUpQuestion;

  /// Editable empty-chat starter; use capabilities/goal without personal data, activity/improve with saved data.
  ///
  /// In en, this message translates to:
  /// **'{kind, select, capabilities{What can you do for me?} goal{Help me set a goal} activity{Summarize my recent activity} improve{How can I improve?} other{}}'**
  String chatStarterPrompt(String kind);

  /// Answered state after Not a Person.
  ///
  /// In en, this message translates to:
  /// **'Omi won\'t ask about this voice again'**
  String get speakerTagPromptIgnoredNote;

  /// Option in the 'Your pendant is listening' sheet that switches recording to the phone microphone.
  ///
  /// In en, this message translates to:
  /// **'Record with phone instead'**
  String get recordWithPhoneInstead;

  /// Placeholder of the trigger-event picker field when submitting an app with external integration
  ///
  /// In en, this message translates to:
  /// **'Trigger Event'**
  String get triggerEvent;

  /// Placeholder text shown while waiting for content
  ///
  /// In en, this message translates to:
  /// **'Waiting for transcript or photos…'**
  String get waitingForTranscriptOrPhotos;

  /// Dialog title for API keys info
  ///
  /// In en, this message translates to:
  /// **'Omi API Keys'**
  String get omiApiKeys;

  /// Row in the picker that creates a new person with the typed name.
  ///
  /// In en, this message translates to:
  /// **'Add “{name}”'**
  String addNamedPersonAction(String name);

  /// No description provided for @enableDetailedDiagnosticMessages.
  ///
  /// In en, this message translates to:
  /// **'Enable detailed diagnostic messages from the transcription service'**
  String get enableDetailedDiagnosticMessages;

  /// No description provided for @nameCannotBeEmpty.
  ///
  /// In en, this message translates to:
  /// **'Name cannot be empty'**
  String get nameCannotBeEmpty;

  /// Empty state title when there are no tasks
  ///
  /// In en, this message translates to:
  /// **'No Tasks Yet'**
  String get noTasksYet;

  /// Empty state message suggesting to adjust search or filters
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search terms or filters'**
  String get tryAdjustingSearchTermsOrFilters;

  /// Heading of a day summary message in chat; date is already formatted for the locale
  ///
  /// In en, this message translates to:
  /// **'Day Summary · {date}'**
  String daySummaryForDate(String date);

  /// No description provided for @statusTimedOut.
  ///
  /// In en, this message translates to:
  /// **'Timed out'**
  String get statusTimedOut;

  /// No description provided for @chatUsageDescription.
  ///
  /// In en, this message translates to:
  /// **'You\'ve used {used} of your {limitDisplay} on the {plan} plan.'**
  String chatUsageDescription(String used, String limitDisplay, String plan);

  /// Label for PayPal.me link field
  ///
  /// In en, this message translates to:
  /// **'PayPal.me Link'**
  String get paypalMeLink;

  /// Snackbar
  ///
  /// In en, this message translates to:
  /// **'All memories are now private'**
  String get allMemoriesPrivateResult;

  /// Button: restart the Bluetooth device search
  ///
  /// In en, this message translates to:
  /// **'Scan Again'**
  String get scanAgain;

  /// Button text to redo speech profile
  ///
  /// In en, this message translates to:
  /// **'Do it again'**
  String get doItAgain;

  /// Title of the Review page: a few questions the app asks the user to answer
  ///
  /// In en, this message translates to:
  /// **'Review'**
  String get reviewTitle;

  /// Tab label for photos content
  ///
  /// In en, this message translates to:
  /// **'Photos'**
  String get photos;

  /// No description provided for @phoneNoVerifiedNumbersMessage.
  ///
  /// In en, this message translates to:
  /// **'Verify your number to make calls through Omi.'**
  String get phoneNoVerifiedNumbersMessage;

  /// Save button label
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get save;

  /// Delete account button
  ///
  /// In en, this message translates to:
  /// **'Delete Account'**
  String get deleteAccount;

  /// Button to manage payment method
  ///
  /// In en, this message translates to:
  /// **'Manage Payment Method'**
  String get managePaymentMethod;

  /// Native file-picker dialog title when choosing an app screenshot thumbnail on web
  ///
  /// In en, this message translates to:
  /// **'Select a Thumbnail Image'**
  String get selectThumbnailImageTitle;

  /// Pairing title for Omi device
  ///
  /// In en, this message translates to:
  /// **'Turn On Omi'**
  String get pairingTitleOmi;

  /// Question asking for primary language
  ///
  /// In en, this message translates to:
  /// **'What\'s your primary language?'**
  String get whatsYourPrimaryLanguage;

  /// Button text to reply to a review
  ///
  /// In en, this message translates to:
  /// **'Reply To Review'**
  String get replyToReview;

  /// Error message when deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete: {error}'**
  String failedToDeleteError(String error);

  /// Subtle sort-order indicator next to the recordings list header so the user knows the newest items are at the top.
  ///
  /// In en, this message translates to:
  /// **'Newest first'**
  String get newestFirst;

  /// Text shown while generating the wrapped, includes newline
  ///
  /// In en, this message translates to:
  /// **'Creating your\n2025 story…'**
  String get wrappedCreatingYourStory;

  /// Setting title
  ///
  /// In en, this message translates to:
  /// **'Keep private memories in the app'**
  String get chatAppsPrivateMemories;

  /// Validation error for empty PayPal email
  ///
  /// In en, this message translates to:
  /// **'Please enter your PayPal email'**
  String get pleaseEnterPayPalEmail;

  /// Transcription feature name
  ///
  /// In en, this message translates to:
  /// **'Transcription'**
  String get transcription;

  /// Label for user's own review
  ///
  /// In en, this message translates to:
  /// **'Your Review'**
  String get yourReview;

  /// Cancel sync confirmation message
  ///
  /// In en, this message translates to:
  /// **'Files already downloaded will be uploaded next time.'**
  String get filesDownloadedUploadedNextTime;

  /// No description provided for @phoneSetupStep3Subtitle.
  ///
  /// In en, this message translates to:
  /// **'With live transcription built in'**
  String get phoneSetupStep3Subtitle;

  /// No description provided for @mcpConnectionFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to MCP server'**
  String get mcpConnectionFailed;

  /// Heading of the Telegram connect sheet
  ///
  /// In en, this message translates to:
  /// **'Connect Telegram'**
  String get chatAppsConnectTelegramTitle;

  /// Tooltip for create memory FAB
  ///
  /// In en, this message translates to:
  /// **'Create new memory'**
  String get createMemoryTooltip;

  /// Message encouraging user to connect device
  ///
  /// In en, this message translates to:
  /// **'Connect your Omi device to access\ndevice settings and customization'**
  String get connectDeviceMessage;

  /// No description provided for @authorizingMcpServer.
  ///
  /// In en, this message translates to:
  /// **'Authorizing…'**
  String get authorizingMcpServer;

  /// No description provided for @charactersCount.
  ///
  /// In en, this message translates to:
  /// **'{count} characters'**
  String charactersCount(int count);

  /// No description provided for @syncStatusUploaded.
  ///
  /// In en, this message translates to:
  /// **'Uploaded · processing on Omi'**
  String get syncStatusUploaded;

  /// Message prompting user to authenticate with a task service
  ///
  /// In en, this message translates to:
  /// **'Please authenticate with {serviceName} in Settings > Task Integrations'**
  String pleaseAuthenticateWithService(String serviceName);

  /// No description provided for @setDefaultButton.
  ///
  /// In en, this message translates to:
  /// **'Set Default'**
  String get setDefaultButton;

  /// Loading text while re-summarizing a conversation
  ///
  /// In en, this message translates to:
  /// **'Re-summarizing conversation…\nThis may take a few seconds'**
  String get resummarizingConversation;

  /// Estimated time in hours
  ///
  /// In en, this message translates to:
  /// **'~{count} hour(s)'**
  String estimatedHours(int count);

  /// Setting subtitle
  ///
  /// In en, this message translates to:
  /// **'Let Omi send you a recap or an insight here.'**
  String get chatAppsInsightsSubtitle;

  /// Button that clears suppression so this memory may be used
  ///
  /// In en, this message translates to:
  /// **'Allow Use'**
  String get memoryAllowUse;

  /// Label for model selector
  ///
  /// In en, this message translates to:
  /// **'Model'**
  String get model;

  /// Navigation title of the memory graph page
  ///
  /// In en, this message translates to:
  /// **'Memory Graph'**
  String get memoryGraphTitle;

  /// No description provided for @endpointURL.
  ///
  /// In en, this message translates to:
  /// **'Endpoint URL'**
  String get endpointURL;

  /// Button text for sharing wrapped on final card
  ///
  /// In en, this message translates to:
  /// **'Share Your Wrapped'**
  String get wrappedShareYourWrapped;

  /// Mic gain description: Boosted
  ///
  /// In en, this message translates to:
  /// **'Boosted - for quiet environments'**
  String get micGainDescBoosted;

  /// Label for minutes stat in Wrapped
  ///
  /// In en, this message translates to:
  /// **'minutes'**
  String get wrappedMinutes;

  /// Label for language selector
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get language;

  /// Download error message
  ///
  /// In en, this message translates to:
  /// **'Download error: {error}'**
  String downloadErrorWithMessage(String error);

  /// Store rating pre-prompt: decline
  ///
  /// In en, this message translates to:
  /// **'No'**
  String get onboardingRatingPromptNo;

  /// Hint text for memory content input field
  ///
  /// In en, this message translates to:
  /// **'What would you like to remember?'**
  String get whatWouldYouLikeToRemember;

  /// Tutorial step 4 double-tap option description for Mute/Unmute
  ///
  /// In en, this message translates to:
  /// **'Toggle microphone on or off'**
  String get deviceOnboardingMuteUnmuteDesc;

  /// Duration in seconds
  ///
  /// In en, this message translates to:
  /// **'{count} seconds'**
  String secondsCount(int count);

  /// Field label for icon selector
  ///
  /// In en, this message translates to:
  /// **'Icon'**
  String get icon;

  /// Webhook type for real-time transcript
  ///
  /// In en, this message translates to:
  /// **'Real-time Transcript'**
  String get realTimeTranscript;

  /// No description provided for @deviceOnboardingVoiceReplySample.
  ///
  /// In en, this message translates to:
  /// **'I\'ve got it. Your next meeting starts in twenty minutes.'**
  String get deviceOnboardingVoiceReplySample;

  /// No description provided for @noDisconnectsRecorded.
  ///
  /// In en, this message translates to:
  /// **'No disconnects recorded'**
  String get noDisconnectsRecorded;

  /// Filter option for user's own apps
  ///
  /// In en, this message translates to:
  /// **'My Apps'**
  String get filterMyApps;

  /// No description provided for @recapRegenerateCooldown.
  ///
  /// In en, this message translates to:
  /// **'Please wait a few seconds before regenerating again.'**
  String get recapRegenerateCooldown;

  /// Label for template name field
  ///
  /// In en, this message translates to:
  /// **'Template Name'**
  String get templateName;

  /// Button label to retry an action
  ///
  /// In en, this message translates to:
  /// **'Try Again'**
  String get retry;

  /// Description of SD Card Sync feature
  ///
  /// In en, this message translates to:
  /// **'SD Card Sync will import your memories from the SD Card to the app'**
  String get sdCardSyncDescription;

  /// Row label that opens the interactive Omi device tutorial (Settings and the connected-device page)
  ///
  /// In en, this message translates to:
  /// **'How to Use Your Omi'**
  String get deviceTutorial;

  /// Empty state for MCP API keys section
  ///
  /// In en, this message translates to:
  /// **'No API keys. Create one to get started.'**
  String get noApiKeysCreateOne;

  /// Guidance for enabling Ask Omi in the iOS Shortcuts app; askPhrase/questionPhrase are literal English Siri phrases
  ///
  /// In en, this message translates to:
  /// **'Turn on Omi in Shortcuts → Siri. Say “{askPhrase}” or “{questionPhrase},” then speak your question.'**
  String siriShortcutsSetupHint(String askPhrase, String questionPhrase);

  /// Error message when partial deletion failure
  ///
  /// In en, this message translates to:
  /// **'Failed to delete some items'**
  String get failedToDeleteSomeItems;

  /// No description provided for @raybanMetaSetupDescription.
  ///
  /// In en, this message translates to:
  /// **'Use your Ray-Ban Meta glasses as your Omi capture device for conversations and visual context. Omi will open the Meta AI app to link your glasses.'**
  String get raybanMetaSetupDescription;

  /// Label for To Do tab
  ///
  /// In en, this message translates to:
  /// **'To Do'**
  String get tabToDo;

  /// OmiGlass OTA status
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t join Wi-Fi. Check the network name and password.'**
  String get otaWifiFailed;

  /// Button text to change plan
  ///
  /// In en, this message translates to:
  /// **'Change Plan'**
  String get changePlan;

  /// Message shown when something is copied to clipboard
  ///
  /// In en, this message translates to:
  /// **'{title} copied to clipboard'**
  String copiedToClipboard(String title);

  /// No description provided for @completeAuthBrowser.
  ///
  /// In en, this message translates to:
  /// **'Please complete authentication in your browser. Once done, return to the app.'**
  String get completeAuthBrowser;

  /// Message shown when data migration is in progress
  ///
  /// In en, this message translates to:
  /// **'Migration in progress. You cannot change the protection level until it is complete.'**
  String get migrationInProgressMessage;

  /// Cancel button of the dialog that confirms cancelling an app subscription
  ///
  /// In en, this message translates to:
  /// **'Keep Subscription'**
  String get keepSubscription;

  /// Inline label on the detail audio player while playback is still being prepared
  ///
  /// In en, this message translates to:
  /// **'Preparing Audio…'**
  String get playbackPreparingAudio;

  /// cloudStorageDialogMessage label
  ///
  /// In en, this message translates to:
  /// **'Your real-time recordings will be stored in private cloud storage as you speak.'**
  String get cloudStorageDialogMessage;

  /// Ask: the first row of Past chats
  ///
  /// In en, this message translates to:
  /// **'New chat'**
  String get newChat;

  /// Validation error when app cost is less than 1
  ///
  /// In en, this message translates to:
  /// **'Please enter an amount greater than 0'**
  String get paymentEnterAmountGreaterThanZero;

  /// Expander chip in the tag-speaker sheet that reveals the capped person grid
  ///
  /// In en, this message translates to:
  /// **'Show all {count} people'**
  String showAllPeople(int count);

  /// Dialog title when deleting one pinned person (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Delete {name}?'**
  String deletePersonNamedTitle(String name);

  /// Import source card title for SRT, VTT or TXT transcripts exported from other apps
  ///
  /// In en, this message translates to:
  /// **'Transcript files'**
  String get importTranscriptFiles;

  /// No description provided for @transcriptPlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Transcript will appear here…'**
  String get transcriptPlaceholder;

  /// No description provided for @logShared.
  ///
  /// In en, this message translates to:
  /// **'Log shared'**
  String get logShared;

  /// Delete reason option
  ///
  /// In en, this message translates to:
  /// **'Not using it enough'**
  String get deleteReasonNotUsing;

  /// Device Diagnostics secondary text under the drop count: average drops per hour
  ///
  /// In en, this message translates to:
  /// **'about {count} an hour'**
  String diagnosticsDropsPerHour(int count);

  /// Default processing status text
  ///
  /// In en, this message translates to:
  /// **'Processing…'**
  String get wrappedProcessingDefault;

  /// Error message when Google Tasks authentication fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Google Tasks. Please try again.'**
  String get failedToConnectGoogleTasksRetry;

  /// Progress label when downloading from SD card
  ///
  /// In en, this message translates to:
  /// **'Downloading from SD Card'**
  String get downloadingFromSdCard;

  /// No description provided for @firmwareFormatWarning.
  ///
  /// In en, this message translates to:
  /// **'This firmware will format the SD card. Please ensure all offline data is synced before upgrading.\n\nIf you see a flashing red light after flashing this version, do not worry. Simply connect the device to the app and it should turn blue. The red light means the device\'s clock hasn\'t been synced yet.'**
  String get firmwareFormatWarning;

  /// Validation error when prompt text field is empty
  ///
  /// In en, this message translates to:
  /// **'Please provide a prompt'**
  String get pleaseProvidePrompt;

  /// Voice response mode: always, including phone speaker
  ///
  /// In en, this message translates to:
  /// **'Always'**
  String get voiceResponseAlways;

  /// Label for status in details
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get statusLabel;

  /// Button text to share debug logs
  ///
  /// In en, this message translates to:
  /// **'Share Logs'**
  String get shareLogs;

  /// No description provided for @continueAnyway.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get continueAnyway;

  /// Success message when transfer completes
  ///
  /// In en, this message translates to:
  /// **'Transfer complete! You can now play this recording.'**
  String get transferCompleteMessage;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Omi will ask here only when it needs you.'**
  String get reviewCaughtUpBody;

  /// Migration ETA calculation in progress message
  ///
  /// In en, this message translates to:
  /// **'Calculating…'**
  String get calculatingETA;

  /// Second speech profile topic prompt; must match the backend onboarding question
  ///
  /// In en, this message translates to:
  /// **'What do you do for work?'**
  String get speechProfileTopicWork;

  /// Suggestion to use cloud transcription
  ///
  /// In en, this message translates to:
  /// **'Consider using Omi Cloud for better performance.'**
  String get considerOmiCloud;

  /// Developer option to test prompts
  ///
  /// In en, this message translates to:
  /// **'Test a Conversation Prompt'**
  String get testConversationPrompt;

  /// Menu option to delete pending recordings
  ///
  /// In en, this message translates to:
  /// **'Delete Pending'**
  String get deletePending;

  /// Menu item that edits the conversation title
  ///
  /// In en, this message translates to:
  /// **'Rename'**
  String get renameConversation;

  /// Warning about battery drain
  ///
  /// In en, this message translates to:
  /// **'Battery drain will increase significantly.'**
  String get batteryDrainSignificantly;

  /// Button label to clear files
  ///
  /// In en, this message translates to:
  /// **'Clear'**
  String get clear;

  /// Validation error when external integration selected but no webhook URL
  ///
  /// In en, this message translates to:
  /// **'Please enter a webhook URL for your app'**
  String get addAppEnterWebhookUrl;

  /// Status label for active
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get active;

  /// Snackbar message when export starts
  ///
  /// In en, this message translates to:
  /// **'Export started. This may take a few seconds…'**
  String get exportStartedMessage;

  /// Description for data access notice dialog
  ///
  /// In en, this message translates to:
  /// **'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app'**
  String get dataAccessNoticeDescription;

  /// Subtitle shown while a training-data access request is pending
  ///
  /// In en, this message translates to:
  /// **'Your request is under review'**
  String get yourRequestUnderReview;

  /// Body of the About Speaker Labels sheet
  ///
  /// In en, this message translates to:
  /// **'Omi could not tell the other voices apart across the recordings. Tap a speaker label to name who is speaking.'**
  String get unresolvedSpeakersMessage;

  /// Error message during download
  ///
  /// In en, this message translates to:
  /// **'Download error: {error}'**
  String downloadError(String error);

  /// Page title for offline sync
  ///
  /// In en, this message translates to:
  /// **'Offline Sync'**
  String get offlineSync;

  /// Button text to cancel a subscription
  ///
  /// In en, this message translates to:
  /// **'Cancel Subscription'**
  String get cancelSubscription;

  /// Claude Desktop connector setup instructions for the hosted MCP server
  ///
  /// In en, this message translates to:
  /// **'On Claude Desktop → Settings → Connectors, add a custom connector and paste the server URL. If Claude asks for an advanced OAuth Client ID, use the value below and leave the secret blank — never use your MCP API key as an OAuth secret.'**
  String get claudeDesktopConnectorSetup;

  /// Status line while waiting for the link to complete
  ///
  /// In en, this message translates to:
  /// **'Waiting for you to tap Start in Telegram…'**
  String get chatAppsTelegramWaiting;

  /// Button text to retry an action
  ///
  /// In en, this message translates to:
  /// **'Try Again'**
  String get tryAgain;

  /// Row subtitle for a recording still on the Omi device (SD-card or flash page) that has not been downloaded to the phone yet.
  ///
  /// In en, this message translates to:
  /// **'On your device'**
  String get syncStatusOnDevice;

  /// Sheet title for correcting a person, organization or project page
  ///
  /// In en, this message translates to:
  /// **'What’s not right?'**
  String get entityCorrectionTitle;

  /// Toast after deleting people.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 person deleted} other{{count} people deleted}}'**
  String peopleDeletedToast(int count);

  /// No description provided for @features.
  ///
  /// In en, this message translates to:
  /// **'Features'**
  String get features;

  /// Payment setup modal title
  ///
  /// In en, this message translates to:
  /// **'Start Earning! 💰'**
  String get startEarning;

  /// No description provided for @enterYourNumber.
  ///
  /// In en, this message translates to:
  /// **'Enter your number'**
  String get enterYourNumber;

  /// Subtitle under the Claude Code section: add the snippet to ~/.claude.json
  ///
  /// In en, this message translates to:
  /// **'Add to ~/.claude.json'**
  String get addToClaudeCodeConfig;

  /// No description provided for @cleanDisconnect.
  ///
  /// In en, this message translates to:
  /// **'Clean disconnect'**
  String get cleanDisconnect;

  /// No description provided for @grantContactsAccess.
  ///
  /// In en, this message translates to:
  /// **'Grant access to your contacts'**
  String get grantContactsAccess;

  /// Reason a chat reply was rated down
  ///
  /// In en, this message translates to:
  /// **'Incorrect or made up'**
  String get feedbackReasonIncorrect;

  /// Generic error when image selection fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting image. Please try again.'**
  String get addAppErrorSelectingImageRetry;

  /// Feedback title when cancel reason is not using enough
  ///
  /// In en, this message translates to:
  /// **'What would make you use Omi more?'**
  String get feedbackTitleNotUsing;

  /// Navigation label for memories page
  ///
  /// In en, this message translates to:
  /// **'Memories'**
  String get memories;

  /// Live-capture app bar title while only photos are being captured
  ///
  /// In en, this message translates to:
  /// **'Capturing photos'**
  String get capturingPhotos;

  /// No description provided for @hideApiKey.
  ///
  /// In en, this message translates to:
  /// **'Hide API Key'**
  String get hideApiKey;

  /// Sign up button text
  ///
  /// In en, this message translates to:
  /// **'Sign Up'**
  String get signUpButton;

  /// Abbreviation for Tuesday
  ///
  /// In en, this message translates to:
  /// **'Tue'**
  String get tuesdayAbbr;

  /// No API keys message
  ///
  /// In en, this message translates to:
  /// **'No API keys yet'**
  String get noApiKeys;

  /// The word 'Key' for use in parameterized strings
  ///
  /// In en, this message translates to:
  /// **'Key'**
  String get keyWord;

  /// Shown only when count is 2 or more
  ///
  /// In en, this message translates to:
  /// **'This answer labels {count} conversations'**
  String reviewAnswersConversations(int count);

  /// Import job status - failed
  ///
  /// In en, this message translates to:
  /// **'Failed'**
  String get statusFailed;

  /// Filter button for installed apps
  ///
  /// In en, this message translates to:
  /// **'Installed Apps'**
  String get installedApps;

  /// Button on the manual firmware flash page (developer settings)
  ///
  /// In en, this message translates to:
  /// **'Flash Firmware'**
  String get flashFirmware;

  /// Error when URL generation fails
  ///
  /// In en, this message translates to:
  /// **'Conversation URL could not be generated.'**
  String get conversationUrlCouldNotBeGenerated;

  /// Loading message shown when reloading apps list
  ///
  /// In en, this message translates to:
  /// **'Reloading apps…'**
  String get reloadingApps;

  /// Field label for goal title input
  ///
  /// In en, this message translates to:
  /// **'Goal title'**
  String get goalTitle;

  /// Notification title for important conversation (>30 min) completion
  ///
  /// In en, this message translates to:
  /// **'Important Conversation'**
  String get importantConversationTitle;

  /// Legal disclaimer prefix text
  ///
  /// In en, this message translates to:
  /// **'By continuing, you agree to our '**
  String get byContinuingAgree;

  /// Abbreviation for Saturday
  ///
  /// In en, this message translates to:
  /// **'Sat'**
  String get saturdayAbbr;

  /// Default message when subscription is reactivated
  ///
  /// In en, this message translates to:
  /// **'Your subscription has been reactivated! No charge now - you\'ll be billed at the end of your current period.'**
  String get subscriptionReactivatedDefault;

  /// No description provided for @tryLatestExperimentalFeatures.
  ///
  /// In en, this message translates to:
  /// **'Try the latest experimental features from Omi Team.'**
  String get tryLatestExperimentalFeatures;

  /// Subtitle under the Chat apps section header on Integrations
  ///
  /// In en, this message translates to:
  /// **'Talk to Omi from the apps you already use every day.'**
  String get chatAppsEntrySubtitle;

  /// No description provided for @transcriptionPaused.
  ///
  /// In en, this message translates to:
  /// **'Recording, reconnecting'**
  String get transcriptionPaused;

  /// No description provided for @appleHealthFeatureReadOnlyTitle.
  ///
  /// In en, this message translates to:
  /// **'Read-only access'**
  String get appleHealthFeatureReadOnlyTitle;

  /// Subtitle of the training-data opt-in card
  ///
  /// In en, this message translates to:
  /// **'Share data for training'**
  String get shareDataForTraining;

  /// Message shown when no notification scopes are available
  ///
  /// In en, this message translates to:
  /// **'No notification scopes available'**
  String get noNotificationScopesAvailable;

  /// No description provided for @disconnectFromApp.
  ///
  /// In en, this message translates to:
  /// **'Disconnect from {appName}?'**
  String disconnectFromApp(String appName);

  /// Error message when Google Tasks OAuth fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to Google Tasks'**
  String get failedToConnectGoogleTasks;

  /// Tooltip for copy button
  ///
  /// In en, this message translates to:
  /// **'Copy to clipboard'**
  String get copyToClipboard;

  /// Confirmation message for stopping recording and summarizing
  ///
  /// In en, this message translates to:
  /// **'Stop recording and summarize the conversation now?'**
  String get stopRecordingConfirmation;

  /// Daily summary settings - failedToGenerateSummaryCheckConversations
  ///
  /// In en, this message translates to:
  /// **'Failed to generate summary. Make sure you have conversations for that day.'**
  String get failedToGenerateSummaryCheckConversations;

  /// Message when usage limit is reached
  ///
  /// In en, this message translates to:
  /// **'You\'ve reached your monthly limit.'**
  String get monthlyLimitReached;

  /// Description text shown at the bottom of the permissions page
  ///
  /// In en, this message translates to:
  /// **'Omi uses these to connect to your device, record audio, keep working in the background, send reminders, and note where conversations happened.'**
  String get permissionsPageDescription;

  /// Onboarding step description for name entry
  ///
  /// In en, this message translates to:
  /// **'Tell us about yourself'**
  String get onboardingTellUsAboutYourself;

  /// Tutorial step 2 subtitle — instructions for the single-press ask-a-question flow
  ///
  /// In en, this message translates to:
  /// **'Press the button once, speak your question, then press again when done'**
  String get deviceOnboardingAskQuestionSubtitle;

  /// Filter button label
  ///
  /// In en, this message translates to:
  /// **'Filters'**
  String get filters;

  /// Warning message during firmware update
  ///
  /// In en, this message translates to:
  /// **'Do not close the app or turn off the device. This could corrupt your device.'**
  String get firmwareUpdateWarning;

  /// Explanation line under the 'Your pendant is listening' sheet title.
  ///
  /// In en, this message translates to:
  /// **'Omi records from one source at a time.'**
  String get oneSourceAtATime;

  /// Row subtitle for a connected chat app; handle is a Telegram username or phone number
  ///
  /// In en, this message translates to:
  /// **'Connected as {handle}'**
  String chatAppsConnectedAs(String handle);

  /// No description provided for @pilotFeatures.
  ///
  /// In en, this message translates to:
  /// **'Pilot Features'**
  String get pilotFeatures;

  /// No description provided for @selectFirmwareZip.
  ///
  /// In en, this message translates to:
  /// **'Select firmware ZIP file'**
  String get selectFirmwareZip;

  /// Quick reason chip: the transcription was poor.
  ///
  /// In en, this message translates to:
  /// **'Poor transcription'**
  String get feedbackReasonRecordingPoorTranscription;

  /// Error shown when deletion API fails
  ///
  /// In en, this message translates to:
  /// **'Could not delete your account. Please try again.'**
  String get deleteAccountFailed;

  /// Placeholder text for conversation search field
  ///
  /// In en, this message translates to:
  /// **'Search conversations'**
  String get searchConversations;

  /// Notification frequency level - balanced
  ///
  /// In en, this message translates to:
  /// **'Balanced'**
  String get frequencyBalanced;

  /// No description provided for @auto.
  ///
  /// In en, this message translates to:
  /// **'Auto'**
  String get auto;

  /// Success message when action item is updated
  ///
  /// In en, this message translates to:
  /// **'Task updated successfully'**
  String get actionItemUpdatedSuccessfully;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'Projects'**
  String get entityProjects;

  /// Button text for Apple Sign In
  ///
  /// In en, this message translates to:
  /// **'Sign in with Apple'**
  String get signInWithApple;

  /// Label for backend URL input field
  ///
  /// In en, this message translates to:
  /// **'Backend URL'**
  String get backendUrlLabel;

  /// Sheet summary for a Likely person.
  ///
  /// In en, this message translates to:
  /// **'Omi usually recognizes {name}\'s voice, but you\'ve only confirmed it a few times.'**
  String confidenceSummaryLikely(String name);

  /// Section label: unresolved items involving this person or organization
  ///
  /// In en, this message translates to:
  /// **'Open threads'**
  String get entityOpenThreads;

  /// Dialog message for delete confirmation
  ///
  /// In en, this message translates to:
  /// **'Delete this task?'**
  String get deleteActionItemMessage;

  /// Label of the chat button on an app's page
  ///
  /// In en, this message translates to:
  /// **'Chat with {appName}'**
  String chatWithApp(String appName);

  /// Dialog title for editing action item
  ///
  /// In en, this message translates to:
  /// **'Edit Task'**
  String get editActionItem;

  /// cloudStorageEnabled label
  ///
  /// In en, this message translates to:
  /// **'Cloud storage enabled'**
  String get cloudStorageEnabled;

  /// Default title for personal win
  ///
  /// In en, this message translates to:
  /// **'Personal Growth'**
  String get wrappedPersonalGrowth;

  /// Pro benefit bullet
  ///
  /// In en, this message translates to:
  /// **'Save memories and manage tasks right from the chat'**
  String get chatAppsProPerkSave;

  /// Link text to go to login page
  ///
  /// In en, this message translates to:
  /// **'Already have an account? Log In'**
  String get alreadyHaveAccountLogin;

  /// Dialog title asking to make app or persona public
  ///
  /// In en, this message translates to:
  /// **'Make {item} Public?'**
  String makeItemPublicQuestion(String item);

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Peak hour'**
  String get usagePeakHour;

  /// No description provided for @addWords.
  ///
  /// In en, this message translates to:
  /// **'Add Words'**
  String get addWords;

  /// Current hour marker on Plan and Usage chart
  ///
  /// In en, this message translates to:
  /// **'now'**
  String get usageNow;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Minutes'**
  String get usageMinutes;

  /// Shows available disk space
  ///
  /// In en, this message translates to:
  /// **'Available Space: {space}'**
  String availableSpace(String space);

  /// Providing stat subtitle
  ///
  /// In en, this message translates to:
  /// **'Tasks and notes, captured automatically.'**
  String get providingSubtitle;

  /// Completion rate badge in Wrapped
  ///
  /// In en, this message translates to:
  /// **'{rate}% completion rate'**
  String wrappedCompletionRate(String rate);

  /// Success message when summary is generated
  ///
  /// In en, this message translates to:
  /// **'Summary generated for {date}'**
  String summaryGeneratedFor(String date);

  /// Placeholder text for category dropdown
  ///
  /// In en, this message translates to:
  /// **'Select Category'**
  String get selectCategory;

  /// No description provided for @nProcessed.
  ///
  /// In en, this message translates to:
  /// **'{count} processed'**
  String nProcessed(int count);

  /// Title for privacy policy page
  ///
  /// In en, this message translates to:
  /// **'Privacy Policy'**
  String get privacyPolicyTitle;

  /// Warning about device temperature
  ///
  /// In en, this message translates to:
  /// **'Device may warm up during extended use.'**
  String get deviceMayWarmUp;

  /// No description provided for @designingApp.
  ///
  /// In en, this message translates to:
  /// **'Designing app'**
  String get designingApp;

  /// Error in the What's New sheet when the changelog fails to load
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load what\'s new'**
  String get couldNotLoadWhatsNew;

  /// Warning during download
  ///
  /// In en, this message translates to:
  /// **'Please do not close the app.'**
  String get doNotCloseApp;

  /// Voice response audio feature title
  ///
  /// In en, this message translates to:
  /// **'Speak Omi responses aloud'**
  String get voiceResponseAudio;

  /// Time period: All Time
  ///
  /// In en, this message translates to:
  /// **'All Time'**
  String get allTime;

  /// Developer settings page title
  ///
  /// In en, this message translates to:
  /// **'Developer Settings'**
  String get developerSettingsTitle;

  /// Button that undoes Not a Person for a voice so Omi may ask about it again (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Restore'**
  String get restoreAction;

  /// No description provided for @phoneSetupStep3Title.
  ///
  /// In en, this message translates to:
  /// **'Start calling your contacts'**
  String get phoneSetupStep3Title;

  /// Generic error message asking user to try again
  ///
  /// In en, this message translates to:
  /// **'An error occurred. Please try again.'**
  String get anErrorOccurredTryAgain;

  /// SMS message body with share link
  ///
  /// In en, this message translates to:
  /// **'Here\'s what we just discussed: {link}'**
  String heresWhatWeDiscussed(String link);

  /// Inline label when loading the audio stream fails
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t Load Audio'**
  String get playbackAudioLoadFailed;

  /// No description provided for @phoneMute.
  ///
  /// In en, this message translates to:
  /// **'Mute'**
  String get phoneMute;

  /// Home live capture card, line 1: live transcription is not running (server said it cannot); audio keeps recording. Must stay short (one line on a small phone).
  ///
  /// In en, this message translates to:
  /// **'Not transcribing'**
  String get captureNotTranscribing;

  /// No description provided for @captureRecordingStoppedDisplayIssue.
  ///
  /// In en, this message translates to:
  /// **'Recording stopped: {reason}. You may need to reconnect external displays or restart recording.'**
  String captureRecordingStoppedDisplayIssue(String reason);

  /// Brand name for the Deepgram speech-to-text provider
  ///
  /// In en, this message translates to:
  /// **'Deepgram'**
  String get sttProviderDeepgram;

  /// Display name for the space key in shortcuts
  ///
  /// In en, this message translates to:
  /// **'Space'**
  String get spaceKey;

  /// No description provided for @raybanMetaOpenMetaAI.
  ///
  /// In en, this message translates to:
  /// **'Connect through Meta AI'**
  String get raybanMetaOpenMetaAI;

  /// Menu item and sheet title: link this conversation to a calendar event
  ///
  /// In en, this message translates to:
  /// **'Link Event'**
  String get linkEvent;

  /// No description provided for @fairUse3Day.
  ///
  /// In en, this message translates to:
  /// **'3-Day Rolling'**
  String get fairUse3Day;

  /// No description provided for @failedToStartAppAuth.
  ///
  /// In en, this message translates to:
  /// **'Failed to start {appName} authentication'**
  String failedToStartAppAuth(String appName);

  /// No description provided for @processingOnServer.
  ///
  /// In en, this message translates to:
  /// **'Processing on server…'**
  String get processingOnServer;

  /// Error message for recording start failure
  ///
  /// In en, this message translates to:
  /// **'Error starting recording: {error}'**
  String errorStartingRecording(String error);

  /// Quiet preset
  ///
  /// In en, this message translates to:
  /// **'Quiet'**
  String get quiet;

  /// Empty state description
  ///
  /// In en, this message translates to:
  /// **'Start a conversation with Omi\nto see your usage insights here.'**
  String get startConversationToSeeInsights;

  /// Button label to process audio recordings
  ///
  /// In en, this message translates to:
  /// **'Process Audio'**
  String get processAudio;

  /// Heading of the iMessage connect sheet
  ///
  /// In en, this message translates to:
  /// **'Text Omi to connect'**
  String get chatAppsConnectIMessageTitle;

  /// Chat share subject
  ///
  /// In en, this message translates to:
  /// **'Chat with Omi'**
  String get chatWithOmi;

  /// Instruction to start recording
  ///
  /// In en, this message translates to:
  /// **'Click to begin recording'**
  String get clickToBeginRecording;

  /// Button text to confirm and proceed
  ///
  /// In en, this message translates to:
  /// **'Confirm & Proceed'**
  String get confirmAndProceed;

  /// Abbreviation for Monday
  ///
  /// In en, this message translates to:
  /// **'Mon'**
  String get mondayAbbr;

  /// Message explaining SD card processing
  ///
  /// In en, this message translates to:
  /// **'Processing {count} recording(s). Files will be removed from SD card after.'**
  String sdCardProcessingMessage(int count);

  /// Shown when a chat reply fails because the user is not signed in
  ///
  /// In en, this message translates to:
  /// **'You\'re not signed in. Sign in and try again.'**
  String get chatReplyNotSignedIn;

  /// Footer explaining where to change voice response settings
  ///
  /// In en, this message translates to:
  /// **'You can change this anytime in {settings} › {voiceResponse}'**
  String deviceOnboardingVoiceReplySettingsHint(String settings, String voiceResponse);

  /// Button text to start generating the 2025 wrapped
  ///
  /// In en, this message translates to:
  /// **'Generate My Wrapped'**
  String get wrappedGenerateMyWrapped;

  /// Intro line on Recent Changes
  ///
  /// In en, this message translates to:
  /// **'What Omi changed on its own in the last 30 days. Undo anything that looks wrong.'**
  String get reviewChangesIntro;

  /// Description after successful connection
  ///
  /// In en, this message translates to:
  /// **'Your Stripe account is now ready to receive payments. You can start earning from your app sales right away.'**
  String get stripeReadyForPayments;

  /// Title for Apple Watch setup page
  ///
  /// In en, this message translates to:
  /// **'Apple Watch Setup'**
  String get appleWatchSetup;

  /// No description provided for @failedToDisconnect.
  ///
  /// In en, this message translates to:
  /// **'Failed to disconnect'**
  String get failedToDisconnect;

  /// localStorageEnabled label
  ///
  /// In en, this message translates to:
  /// **'Local storage enabled'**
  String get localStorageEnabled;

  /// The Omi desktop app as the device that recorded a conversation
  ///
  /// In en, this message translates to:
  /// **'Desktop'**
  String get captureSourceDesktop;

  /// Label for serial number field
  ///
  /// In en, this message translates to:
  /// **'Serial Number'**
  String get serialNumber;

  /// No description provided for @appleHealthFeatureSecureDesc.
  ///
  /// In en, this message translates to:
  /// **'Your Apple Health data syncs privately to your Omi account.'**
  String get appleHealthFeatureSecureDesc;

  /// Hint when no apps found
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search or filters'**
  String get tryAdjustingSearch;

  /// No description provided for @connectTo.
  ///
  /// In en, this message translates to:
  /// **'Connect to {appName}'**
  String connectTo(String appName);

  /// No description provided for @exportConversationsDescription.
  ///
  /// In en, this message translates to:
  /// **'Export conversations to JSON'**
  String get exportConversationsDescription;

  /// Label for featured status
  ///
  /// In en, this message translates to:
  /// **'FEATURED'**
  String get featuredLabel;

  /// Speech profile setting
  ///
  /// In en, this message translates to:
  /// **'Voice Profile'**
  String get speechProfile;

  /// Integrations menu item
  ///
  /// In en, this message translates to:
  /// **'Integrations'**
  String get integrations;

  /// Action menu entry to hide completed tasks on the action items page
  ///
  /// In en, this message translates to:
  /// **'Hide Completed'**
  String get hideCompletedTasks;

  /// Toggle label controlling whether Custom STT raw audio is also sent to Omi
  ///
  /// In en, this message translates to:
  /// **'Send raw audio to Omi'**
  String get sendRawAudioToOmi;

  /// Number of ratings for an app
  ///
  /// In en, this message translates to:
  /// **'{count}+ ratings'**
  String ratingsCount(String count);

  /// No description provided for @exportShared.
  ///
  /// In en, this message translates to:
  /// **'Export shared'**
  String get exportShared;

  /// Conversation timeout feature name
  ///
  /// In en, this message translates to:
  /// **'Conversation Timeout'**
  String get conversationTimeout;

  /// Button text to install the stable firmware
  ///
  /// In en, this message translates to:
  /// **'Install Stable Firmware'**
  String get installStableFirmware;

  /// Feature title for security
  ///
  /// In en, this message translates to:
  /// **'Secure and reliable'**
  String get secureAndReliable;

  /// Snackbar message when exporting conversations
  ///
  /// In en, this message translates to:
  /// **'Exporting conversations…'**
  String get exportingConversations;

  /// Quick reason chip: the recording was fragmented or duplicated.
  ///
  /// In en, this message translates to:
  /// **'Fragmented or duplicated'**
  String get feedbackReasonRecordingFragmentedOrDuplicated;

  /// Description while waiting
  ///
  /// In en, this message translates to:
  /// **'Send the message in Messages. This screen updates as soon as Omi gets it.'**
  String get chatAppsWaitingMessage;

  /// Onboarding setup checklist step
  ///
  /// In en, this message translates to:
  /// **'Preparing your workspace'**
  String get onboardingSetupStepWorkspace;

  /// Label for recap/daily summaries tab
  ///
  /// In en, this message translates to:
  /// **'Recap'**
  String get recap;

  /// Time estimate for very short durations
  ///
  /// In en, this message translates to:
  /// **'Less than a minute'**
  String get lessThanAMinute;

  /// Title for the tasks page
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get tasks;

  /// Onboarding setup checklist step
  ///
  /// In en, this message translates to:
  /// **'Connecting your devices'**
  String get onboardingSetupStepDevices;

  /// Switch row title on a person's page.
  ///
  /// In en, this message translates to:
  /// **'Pin {name}'**
  String pinPersonTitle(String name);

  /// Encouragement message in struggle template
  ///
  /// In en, this message translates to:
  /// **'But you pushed through 💪'**
  String get wrappedButYouPushedThrough;

  /// Loading message when fetching app details
  ///
  /// In en, this message translates to:
  /// **'Fetching your app details'**
  String get fetchingYourAppDetails;

  /// No description provided for @timeout2MinutesDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 2 minutes of silence'**
  String get timeout2MinutesDesc;

  /// Toast after cancelling an OmiGlass update
  ///
  /// In en, this message translates to:
  /// **'Update cancelled'**
  String get otaUpdateCancelled;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Tasks & notes'**
  String get usageTasksNotes;

  /// Device not connected header
  ///
  /// In en, this message translates to:
  /// **'Device Not Connected'**
  String get deviceNotConnected;

  /// Empty state when iOS reports no Bluetooth HFP microphone inputs
  ///
  /// In en, this message translates to:
  /// **'No Bluetooth microphones found. Connect your glasses in iPhone Settings, then try again.'**
  String get rayBanMetaMicPickerEmpty;

  /// Snackbar message when item completed
  ///
  /// In en, this message translates to:
  /// **'Task completed'**
  String get actionItemCompleted;

  /// Usage location option: In Social Settings
  ///
  /// In en, this message translates to:
  /// **'In Social Settings'**
  String get usageSocialSettings;

  /// Preposition for time range in conversation
  ///
  /// In en, this message translates to:
  /// **'from'**
  String get from;

  /// No description provided for @siriIndexSetting.
  ///
  /// In en, this message translates to:
  /// **'Use Omi with Siri & Apple Intelligence'**
  String get siriIndexSetting;

  /// Dismiss reason chip (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Not Mine'**
  String get reviewReasonNotMine;

  /// Step text for connecting to device
  ///
  /// In en, this message translates to:
  /// **'Connect to {deviceName}'**
  String connectToDeviceName(String deviceName);

  /// Onboarding step title for completion
  ///
  /// In en, this message translates to:
  /// **'Complete'**
  String get onboardingComplete;

  /// Switch title
  ///
  /// In en, this message translates to:
  /// **'Show these chats in the Omi app'**
  String get chatAppsShowInApp;

  /// Accessibility label of the completed-count pill on a conversation's Tasks tab
  ///
  /// In en, this message translates to:
  /// **'{count} completed'**
  String nCompleted(int count);

  /// Chip in the feedback sheet for a positive answer; submits helpful feedback.
  ///
  /// In en, this message translates to:
  /// **'All good'**
  String get feedbackAllGood;

  /// Top status card: phase title when uploading audio batches to Omi (sub-line shows X of Y)
  ///
  /// In en, this message translates to:
  /// **'Uploading to Omi'**
  String get syncCardUploadingTitle;

  /// Label for baseline memory
  ///
  /// In en, this message translates to:
  /// **'Baseline Memory'**
  String get baselineMemory;

  /// No description provided for @trainFamilyProfilesDesc.
  ///
  /// In en, this message translates to:
  /// **'Your recordings help us recognize and create profiles for your friends and family.'**
  String get trainFamilyProfilesDesc;

  /// Error when share link generation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to generate share link'**
  String get failedToGenerateShareLink;

  /// No description provided for @onlyYouCanSeeConversation.
  ///
  /// In en, this message translates to:
  /// **'Only you can see this conversation'**
  String get onlyYouCanSeeConversation;

  /// No description provided for @popular.
  ///
  /// In en, this message translates to:
  /// **'Popular'**
  String get popular;

  /// Button that splits one device recording out of a grouped conversation
  ///
  /// In en, this message translates to:
  /// **'Separate…'**
  String get captureRecordingSeparate;

  /// No description provided for @allTemplates.
  ///
  /// In en, this message translates to:
  /// **'All Templates'**
  String get allTemplates;

  /// No description provided for @devicesFoundNearby.
  ///
  /// In en, this message translates to:
  /// **'{count} {count, plural, =1{DEVICE} other{DEVICES}} FOUND NEARBY'**
  String devicesFoundNearby(int count);

  /// Answered state of the voice card after the user named the voice.
  ///
  /// In en, this message translates to:
  /// **'Saved as {name}'**
  String speakerTagPromptSavedAs(String name);

  /// No description provided for @configureSettings.
  ///
  /// In en, this message translates to:
  /// **'Configure Settings'**
  String get configureSettings;

  /// Text shown when app has no ratings
  ///
  /// In en, this message translates to:
  /// **'no ratings'**
  String get noRatings;

  /// Status when auto-resuming with countdown
  ///
  /// In en, this message translates to:
  /// **'Resuming in {countdown}s…'**
  String resumingInCountdown(String countdown);

  /// Share stats: memories
  ///
  /// In en, this message translates to:
  /// **'📚 Remembered {count} memories'**
  String shareStatsMemories(String count);

  /// Menu item to clear due date
  ///
  /// In en, this message translates to:
  /// **'Clear Due Date'**
  String get clearDueDate;

  /// Button to copy message text
  ///
  /// In en, this message translates to:
  /// **'Copy'**
  String get copy;

  /// No description provided for @showPhoneCallButtonDesc.
  ///
  /// In en, this message translates to:
  /// **'Display phone call button on home screen'**
  String get showPhoneCallButtonDesc;

  /// No description provided for @appleHealthFeatureReadOnlyDesc.
  ///
  /// In en, this message translates to:
  /// **'Omi never writes to Apple Health or modifies your data.'**
  String get appleHealthFeatureReadOnlyDesc;

  /// Dialog message explaining multiple speakers issue
  ///
  /// In en, this message translates to:
  /// **'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.'**
  String get multipleSpeakersDescription;

  /// Error message when due date update fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update due date'**
  String get failedToUpdateDueDate;

  /// Success message when Whoop OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Whoop!'**
  String get successfullyConnectedWhoop;

  /// No description provided for @categories.
  ///
  /// In en, this message translates to:
  /// **'Categories'**
  String get categories;

  /// Transcript tab while the conversation's lines are being fetched.
  ///
  /// In en, this message translates to:
  /// **'Loading transcript…'**
  String get loadingTranscript;

  /// Body warning that syncing transcribes on Omi servers and counts toward the plan limit
  ///
  /// In en, this message translates to:
  /// **'You use your own transcription provider. Syncing these recordings transcribes them on Omi\'s servers instead, and they count toward your plan\'s transcription limit.'**
  String get syncCustomSttWarningMessage;

  /// Button to finalize the current recording and start a new one
  ///
  /// In en, this message translates to:
  /// **'New recording'**
  String get newRecording;

  /// Live-capture empty state when the plan is out of transcription credits
  ///
  /// In en, this message translates to:
  /// **'Transcription is unavailable — recording continues and your audio is saved.'**
  String get transcriptionUnavailableRecordingSaved;

  /// Loading message shown while app is being submitted
  ///
  /// In en, this message translates to:
  /// **'Submitting your app…'**
  String get submittingYourApp;

  /// Snackbar shown when linking a conversation to a calendar event fails
  ///
  /// In en, this message translates to:
  /// **'Failed to link calendar event'**
  String get failedToLinkCalendarEvent;

  /// Placeholder example PayPal.me link for input field
  ///
  /// In en, this message translates to:
  /// **'paypal.me/nik'**
  String get paypalMeLinkHint;

  /// Account information section title
  ///
  /// In en, this message translates to:
  /// **'Your Information'**
  String get yourInformation;

  /// Shown on the sign-in screen after the backend refused every request because the account's deletion is still in progress
  ///
  /// In en, this message translates to:
  /// **'This account is being deleted. Sign in with another account, or wait a few minutes and try again.'**
  String get accountDeletionInProgressSignInAgain;

  /// Toggle state label when enabled
  ///
  /// In en, this message translates to:
  /// **'On'**
  String get on;

  /// No description provided for @diagnostics.
  ///
  /// In en, this message translates to:
  /// **'Diagnostics'**
  String get diagnostics;

  /// Snackbar message after copying error
  ///
  /// In en, this message translates to:
  /// **'Error message copied to clipboard'**
  String get errorCopied;

  /// Title for the app review prompt
  ///
  /// In en, this message translates to:
  /// **'Loving Omi?'**
  String get lovingOmi;

  /// Description for read memories permission
  ///
  /// In en, this message translates to:
  /// **'This app can access your memories.'**
  String get permissionDescReadMemories;

  /// Validation error for http/https/www in link
  ///
  /// In en, this message translates to:
  /// **'Do not include http or https or www in the link'**
  String get doNotIncludeHttpInLink;

  /// Menu item to share a recording
  ///
  /// In en, this message translates to:
  /// **'Share Recording'**
  String get shareRecording;

  /// Opens an inline editor to correct a learned memory (button)
  ///
  /// In en, this message translates to:
  /// **'Fix'**
  String get memoryReviewFix;

  /// Error message when selected plan is not available
  ///
  /// In en, this message translates to:
  /// **'Selected plan is not available. Please try again.'**
  String get selectedPlanNotAvailable;

  /// No description provided for @autoCreateWhenDetected.
  ///
  /// In en, this message translates to:
  /// **'Auto-create when name detected'**
  String get autoCreateWhenDetected;

  /// Validation error when no capability is selected
  ///
  /// In en, this message translates to:
  /// **'Please select at least one capability for your app'**
  String get addAppSelectCapability;

  /// Tooltip on the password visibility toggle
  ///
  /// In en, this message translates to:
  /// **'Show password'**
  String get showPassword;

  /// No description provided for @conversationEndAfterMinutes.
  ///
  /// In en, this message translates to:
  /// **'Conversations will now end after {minutes} minute(s) of silence'**
  String conversationEndAfterMinutes(int minutes);

  /// Message of the pop-up that offers a newer version of the app
  ///
  /// In en, this message translates to:
  /// **'A new version of Omi is ready, with fixes and improvements.'**
  String get updateAvailableMessage;

  /// Validation message for name length
  ///
  /// In en, this message translates to:
  /// **'Name must be between 2 and 40 characters'**
  String get nameMustBeBetweenCharacters;

  /// No description provided for @operatorSubtitle.
  ///
  /// In en, this message translates to:
  /// **'{count} questions per month'**
  String operatorSubtitle(int count);

  /// Undo toast after deleting several conversations
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 conversation deleted} other{{count} conversations deleted}}'**
  String conversationsDeletedCount(int count);

  /// Description of monthly payout feature
  ///
  /// In en, this message translates to:
  /// **'Receive monthly payments directly to your account when you reach \$10 in earnings'**
  String get monthlyPayoutsDescription;

  /// Explanation of how daily score is calculated
  ///
  /// In en, this message translates to:
  /// **'Your daily score is based on task completion. Complete your tasks to improve your score!'**
  String get dailyScoreExplanation;

  /// No description provided for @improveConnectionContent.
  ///
  /// In en, this message translates to:
  /// **'We\'ve improved how Omi stays connected to your device. To activate this, please go to the Device Info page, tap \"Disconnect Device\", and then pair your device again.'**
  String get improveConnectionContent;

  /// Title when sync is in progress
  ///
  /// In en, this message translates to:
  /// **'Syncing recordings'**
  String get syncingRecordings;

  /// Profession option: Product Manager
  ///
  /// In en, this message translates to:
  /// **'Product Manager'**
  String get professionProductManager;

  /// No description provided for @nameMustBeAtLeast2Characters.
  ///
  /// In en, this message translates to:
  /// **'Name must be at least 2 characters'**
  String get nameMustBeAtLeast2Characters;

  /// No description provided for @conversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Conversation Title'**
  String get conversationTitle;

  /// No description provided for @mcpServerConnected.
  ///
  /// In en, this message translates to:
  /// **'{count} tools connected successfully'**
  String mcpServerConnected(int count);

  /// Feedback subtitle for not using enough
  ///
  /// In en, this message translates to:
  /// **'We want to make Omi more useful for you.'**
  String get feedbackSubtitleNotUsing;

  /// Delete account warning 3
  ///
  /// In en, this message translates to:
  /// **'You can export your data before deleting your account, but once deleted, it cannot be recovered.'**
  String get exportBeforeDelete;

  /// Title of the confirmation before deleting several tasks at once
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Delete 1 Task?} other{Delete {count} Tasks?}}'**
  String deleteTasksTitle(int count);

  /// Notification frequency level - maximum
  ///
  /// In en, this message translates to:
  /// **'Maximum'**
  String get frequencyMaximum;

  /// Subtitle for cancel reason page
  ///
  /// In en, this message translates to:
  /// **'Can you tell us why you\'re leaving?'**
  String get cancelReasonSubtitle;

  /// No description provided for @generatingIconStep.
  ///
  /// In en, this message translates to:
  /// **'Generating icon'**
  String get generatingIconStep;

  /// storeAudioDescription label
  ///
  /// In en, this message translates to:
  /// **'Keep all audio recordings stored locally on your phone. When disabled, only failed uploads are kept to save storage space.'**
  String get storeAudioDescription;

  /// Title of the confirmation before unpairing a Limitless device
  ///
  /// In en, this message translates to:
  /// **'Unpair Device?'**
  String get unpairDeviceConfirmTitle;

  /// Dismiss button text on phone calls upsell sheet
  ///
  /// In en, this message translates to:
  /// **'Maybe later'**
  String get phoneCallsMaybeLater;

  /// Error message with details in AI app generator
  ///
  /// In en, this message translates to:
  /// **'An error occurred: {message}'**
  String aiGenErrorOccurredWithDetails(String message);

  /// Privacy page - yourPrivacyMattersToUs
  ///
  /// In en, this message translates to:
  /// **'Your Privacy Matters to Us'**
  String get yourPrivacyMattersToUs;

  /// Screen-reader label for the button that folds the transcript suggestion back into a chip.
  ///
  /// In en, this message translates to:
  /// **'Collapse'**
  String get collapseAction;

  /// No description provided for @friendWordOfMouth.
  ///
  /// In en, this message translates to:
  /// **'Friend'**
  String get friendWordOfMouth;

  /// Output consequence for Headphones only mode without connected headphones
  ///
  /// In en, this message translates to:
  /// **'No headphones connected. Omi stays silent until you connect some.'**
  String get deviceOnboardingVoiceReplyStatusHeadphonesDisconnected;

  /// Button to connect a device
  ///
  /// In en, this message translates to:
  /// **'Connect Device'**
  String get connectDevice;

  /// Label for device ID field
  ///
  /// In en, this message translates to:
  /// **'Device ID'**
  String get deviceId;

  /// Custom vocabulary description
  ///
  /// In en, this message translates to:
  /// **'Add words that Omi should recognize during transcription.'**
  String get addWordsDescription;

  /// User ID field
  ///
  /// In en, this message translates to:
  /// **'User ID'**
  String get userId;

  /// Evidence row: the user answered Yes when a suggestion card asked about this person.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Yes on 1 suggestion} other{Yes on {count} suggestions}}'**
  String evidenceCardConfirms(int count);

  /// Badge showing number of transcript segments
  ///
  /// In en, this message translates to:
  /// **'{count} segments'**
  String segmentsCount(int count);

  /// Title for the permissions interstitial screen
  ///
  /// In en, this message translates to:
  /// **'Get the best experience'**
  String get permissionsSetupTitle;

  /// Permission type label for access permissions
  ///
  /// In en, this message translates to:
  /// **'Access'**
  String get permissionTypeAccess;

  /// Explanation under the remember-voices switch
  ///
  /// In en, this message translates to:
  /// **'Omi keeps a short voice sample so it can recognize them next time. You can change this anytime in Settings.'**
  String get speakerTagPromptSaveVoicesBody;

  /// Section header for developer API keys
  ///
  /// In en, this message translates to:
  /// **'Developer API'**
  String get developerApi;

  /// Menu item for charging help
  ///
  /// In en, this message translates to:
  /// **'Charging Issues'**
  String get chargingIssues;

  /// Section header for debug features
  ///
  /// In en, this message translates to:
  /// **'Debug & Diagnostics'**
  String get debugAndDiagnostics;

  /// Lifetime count of connect attempts that never established a connection
  ///
  /// In en, this message translates to:
  /// **'Failed connections'**
  String get failedConnections;

  /// Confirmation when user ID is copied
  ///
  /// In en, this message translates to:
  /// **'User ID copied to clipboard'**
  String get userIdCopied;

  /// Error when trying to report own message
  ///
  /// In en, this message translates to:
  /// **'You cannot report your own messages.'**
  String get cannotReportOwnMessage;

  /// Label for latest available firmware version
  ///
  /// In en, this message translates to:
  /// **'Latest Version'**
  String get latestVersion;

  /// Reason a chat reply was rated down
  ///
  /// In en, this message translates to:
  /// **'Not helpful or irrelevant'**
  String get feedbackReasonNotHelpful;

  /// Delete people dialog body
  ///
  /// In en, this message translates to:
  /// **'This removes their voice samples and can\'t be undone. Their lines in past conversations become unnamed speakers.'**
  String get deletePeopleMessage;

  /// No description provided for @deviceOnboardingAllSetSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Tap a row to review or change it.'**
  String get deviceOnboardingAllSetSubtitle;

  /// Merge dialog title
  ///
  /// In en, this message translates to:
  /// **'Merge Conversations'**
  String get mergeConversations;

  /// Recording status: paused
  ///
  /// In en, this message translates to:
  /// **'Paused'**
  String get paused;

  /// Link text to firmware update help
  ///
  /// In en, this message translates to:
  /// **'Update Guide'**
  String get updateGuide;

  /// Info about billing period end
  ///
  /// In en, this message translates to:
  /// **'Your plan will remain active until {date}. After that, you\'ll be moved to the free version with limited features.'**
  String cancelBillingPeriodInfo(String date);

  /// No description provided for @reconnectingToInternet.
  ///
  /// In en, this message translates to:
  /// **'Reconnecting to internet…'**
  String get reconnectingToInternet;

  /// Snackbar message after all files deleted
  ///
  /// In en, this message translates to:
  /// **'All recordings deleted'**
  String get allFilesDeleted;

  /// Placeholder example email for PayPal email input field
  ///
  /// In en, this message translates to:
  /// **'nik@example.com'**
  String get paypalEmailHint;

  /// No description provided for @oneWeekAgo.
  ///
  /// In en, this message translates to:
  /// **'1 week ago'**
  String get oneWeekAgo;

  /// No description provided for @deviceOnboardingAllSetSinglePressBadge.
  ///
  /// In en, this message translates to:
  /// **'1×'**
  String get deviceOnboardingAllSetSinglePressBadge;

  /// Inline label when the conversation's audio cannot be played at all
  ///
  /// In en, this message translates to:
  /// **'Audio Unavailable'**
  String get playbackAudioUnavailable;

  /// Tutorial step 4 prompt encouraging the user to double-tap the device
  ///
  /// In en, this message translates to:
  /// **'Try it now! Double tap your Omi'**
  String get deviceOnboardingTryDoubleTap;

  /// Delete reason option
  ///
  /// In en, this message translates to:
  /// **'Privacy concerns'**
  String get deleteReasonPrivacy;

  /// Footnote under the clean-up review list.
  ///
  /// In en, this message translates to:
  /// **'Pinned people are never included in Clean Up.'**
  String get cleanUpPinnedNote;

  /// Short label for productive day in summary
  ///
  /// In en, this message translates to:
  /// **'Productive'**
  String get wrappedProductiveDay;

  /// Support line under the assistant voice picker
  ///
  /// In en, this message translates to:
  /// **'Your voice choice is shared across mobile and desktop.'**
  String get voiceSharedAcrossDevices;

  /// Success message when knowledge graph deleted
  ///
  /// In en, this message translates to:
  /// **'Knowledge Graph deleted'**
  String get knowledgeGraphDeleted;

  /// Instruction
  ///
  /// In en, this message translates to:
  /// **'Press done to create'**
  String get pressDoneToCreate;

  /// Label for cloud storage tier in sync pipeline
  ///
  /// In en, this message translates to:
  /// **'Cloud Storage'**
  String get cloudStorage;

  /// Title asking how SD Card Sync works
  ///
  /// In en, this message translates to:
  /// **'How does it work?'**
  String get howDoesItWork;

  /// Button text to submit the app
  ///
  /// In en, this message translates to:
  /// **'Submit App'**
  String get submitApp;

  /// Search input hint text
  ///
  /// In en, this message translates to:
  /// **'Search memories'**
  String get searchMemories;

  /// Title for notification shown when device detects a fall
  ///
  /// In en, this message translates to:
  /// **'Ouch'**
  String get fallNotificationTitle;

  /// Storage notice showing where recording is stored
  ///
  /// In en, this message translates to:
  /// **'Stored on {deviceName}'**
  String storedOnDevice(String deviceName);

  /// Title when contacts permission is denied
  ///
  /// In en, this message translates to:
  /// **'Contacts permission required'**
  String get contactsPermissionRequired;

  /// Success message when review is updated
  ///
  /// In en, this message translates to:
  /// **'Review updated successfully 🚀'**
  String get reviewUpdatedSuccessfully;

  /// Validation error for empty PayPal.me link
  ///
  /// In en, this message translates to:
  /// **'Please enter your PayPal.me link'**
  String get pleaseEnterPayPalMeLink;

  /// Label for thumbs down button to indicate response was not helpful
  ///
  /// In en, this message translates to:
  /// **'Not Helpful'**
  String get notHelpful;

  /// Title when there are recordings to sync
  ///
  /// In en, this message translates to:
  /// **'Recordings to sync'**
  String get recordingsToSync;

  /// No description provided for @categoryUtilities.
  ///
  /// In en, this message translates to:
  /// **'Utilities'**
  String get categoryUtilities;

  /// No description provided for @exportStarted.
  ///
  /// In en, this message translates to:
  /// **'Export started. This may take a few seconds…'**
  String get exportStarted;

  /// Output consequence when voice responses are off
  ///
  /// In en, this message translates to:
  /// **'Omi will stay silent. Answers still appear in the app.'**
  String get deviceOnboardingVoiceReplyStatusOff;

  /// Default title for a new goal in the goal tracker widget
  ///
  /// In en, this message translates to:
  /// **'My goal'**
  String get myGoal;

  /// Duration in singular hour
  ///
  /// In en, this message translates to:
  /// **'{count} hour'**
  String timeHourSingular(int count);

  /// Label of the chat tools manifest URL field when submitting an app with external integration
  ///
  /// In en, this message translates to:
  /// **'Chat Tools Manifest URL'**
  String get chatToolsManifestUrl;

  /// Error when selecting files fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting files: {error}'**
  String msgSelectFilesError(String error);

  /// No description provided for @connectedToApp.
  ///
  /// In en, this message translates to:
  /// **'Connected to {appName}'**
  String connectedToApp(String appName);

  /// Text field hint
  ///
  /// In en, this message translates to:
  /// **'Tell Omi what to fix'**
  String get entityCorrectionHint;

  /// Success message when Apple Watch connects
  ///
  /// In en, this message translates to:
  /// **'Apple Watch connected successfully!'**
  String get appleWatchConnectedSuccessfully;

  /// No description provided for @appIntegration.
  ///
  /// In en, this message translates to:
  /// **'{appName} Integration'**
  String appIntegration(String appName);

  /// Cancel reason option
  ///
  /// In en, this message translates to:
  /// **'Audio/transcription quality'**
  String get cancelReasonAudioQuality;

  /// No description provided for @invalidProviderInConfig.
  ///
  /// In en, this message translates to:
  /// **'Invalid provider in configuration'**
  String get invalidProviderInConfig;

  /// Toolbar button in select mode when every visible row is selected
  ///
  /// In en, this message translates to:
  /// **'Deselect All'**
  String get deselectAll;

  /// Description when the code expired
  ///
  /// In en, this message translates to:
  /// **'Get a new code and send it from Messages.'**
  String get chatAppsCodeExpiredMessage;

  /// Error toast
  ///
  /// In en, this message translates to:
  /// **'Couldn’t save your answer. Try again.'**
  String get reviewAnswerFailed;

  /// No description provided for @categorySocial.
  ///
  /// In en, this message translates to:
  /// **'Social'**
  String get categorySocial;

  /// Filter for apps with 4 or more stars
  ///
  /// In en, this message translates to:
  /// **'4+ Stars'**
  String get rating4PlusStars;

  /// Error when SMS app cannot be opened
  ///
  /// In en, this message translates to:
  /// **'Could not open SMS app. Please try again.'**
  String get couldNotOpenSmsApp;

  /// Empty transcript
  ///
  /// In en, this message translates to:
  /// **'No messages'**
  String get chatAppsNoMessages;

  /// Label for celebrity obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'CELEBRITY'**
  String get wrappedCelebrity;

  /// Dialog title asking to confirm key revocation
  ///
  /// In en, this message translates to:
  /// **'Revoke Key?'**
  String get revokeKeyQuestion;

  /// Duration in minutes and seconds
  ///
  /// In en, this message translates to:
  /// **'{mins} mins {secs} secs'**
  String timeMinsAndSecs(int mins, int secs);

  /// Hint text for contacts search field
  ///
  /// In en, this message translates to:
  /// **'Search contacts'**
  String get searchContactsHint;

  /// No description provided for @showEventsWithoutParticipants.
  ///
  /// In en, this message translates to:
  /// **'Show Events Without Participants'**
  String get showEventsWithoutParticipants;

  /// No description provided for @fair.
  ///
  /// In en, this message translates to:
  /// **'Fair'**
  String get fair;

  /// Tip in sync info sheet
  ///
  /// In en, this message translates to:
  /// **'Recordings sync automatically'**
  String get tipAutoSync;

  /// Success message when summary is copied
  ///
  /// In en, this message translates to:
  /// **'Summary copied to clipboard'**
  String get summaryCopiedToClipboard;

  /// Clear the current search query.
  ///
  /// In en, this message translates to:
  /// **'Clear Search'**
  String get clearSearch;

  /// Answer chip on the voice suggestion card: the voice is a TV, podcast or music, not a person (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Not a Person'**
  String get speakerTagPromptNotAPerson;

  /// Label for model selector
  ///
  /// In en, this message translates to:
  /// **'Model'**
  String get modelLabel;

  /// Dialog title asking to confirm deletion
  ///
  /// In en, this message translates to:
  /// **'Delete {item}?'**
  String deleteItemQuestion(String item);

  /// No description provided for @enterPromoCode.
  ///
  /// In en, this message translates to:
  /// **'Enter promo code'**
  String get enterPromoCode;

  /// No description provided for @phoneNoContactsFound.
  ///
  /// In en, this message translates to:
  /// **'No contacts found'**
  String get phoneNoContactsFound;

  /// Shows number of remaining items
  ///
  /// In en, this message translates to:
  /// **'{count} remaining'**
  String countRemaining(String count);

  /// Title for app management page
  ///
  /// In en, this message translates to:
  /// **'Manage Your App'**
  String get manageYourApp;

  /// No description provided for @willSyncAutomatically.
  ///
  /// In en, this message translates to:
  /// **'will sync automatically'**
  String get willSyncAutomatically;

  /// No description provided for @promoCode.
  ///
  /// In en, this message translates to:
  /// **'Promo code'**
  String get promoCode;

  /// Description for goal tracker
  ///
  /// In en, this message translates to:
  /// **'Track your personal goals on homepage'**
  String get trackPersonalGoalsOnHomepage;

  /// Notice shown when the memory history response is truncated
  ///
  /// In en, this message translates to:
  /// **'Some memory history is unavailable. Showing the history received so far.'**
  String get memoryHistoryPartial;

  /// No description provided for @sharePublicLink.
  ///
  /// In en, this message translates to:
  /// **'Share Public Link'**
  String get sharePublicLink;

  /// Tab label for conversation summary
  ///
  /// In en, this message translates to:
  /// **'Conversation'**
  String get conversationTab;

  /// Subtitle explaining the background mode toggle
  ///
  /// In en, this message translates to:
  /// **'Keep your Omi recording even when the app is fully closed.'**
  String get backgroundModeDescription;

  /// Pairing description for Omi DevKit
  ///
  /// In en, this message translates to:
  /// **'Press the button once to turn on. The LED will blink purple when in pairing mode.'**
  String get pairingDescOmiDevkit;

  /// No description provided for @callStateFailed.
  ///
  /// In en, this message translates to:
  /// **'Call Failed'**
  String get callStateFailed;

  /// Helper text under the GitHub repository field when submitting an app
  ///
  /// In en, this message translates to:
  /// **'Link to your app\'s source code repository'**
  String get githubRepositoryUrlHint;

  /// No description provided for @appIconLabel.
  ///
  /// In en, this message translates to:
  /// **'App Icon'**
  String get appIconLabel;

  /// Button label to uninstall an installed app
  ///
  /// In en, this message translates to:
  /// **'Uninstall App'**
  String get uninstallApp;

  /// Second half of a reason line, after a middle dot: Omi has no voice sample for this person yet. Lowercase.
  ///
  /// In en, this message translates to:
  /// **'no voice sample yet'**
  String get confidenceReasonNeedsVoice;

  /// Developer Settings: the API key or MCP key list failed to load
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load API keys.'**
  String get couldNotLoadApiKeys;

  /// Loading text while fetching stable firmware version
  ///
  /// In en, this message translates to:
  /// **'Fetching latest stable firmware…'**
  String get fetchingStableFirmware;

  /// Status label indicating an on-device model has been downloaded
  ///
  /// In en, this message translates to:
  /// **'Downloaded'**
  String get onDeviceModelDownloaded;

  /// No description provided for @noAPIKeys.
  ///
  /// In en, this message translates to:
  /// **'No API keys. Create one to get started.'**
  String get noAPIKeys;

  /// Phone calls upsell feature 3
  ///
  /// In en, this message translates to:
  /// **'Recipients see your real number, not a random one'**
  String get phoneCallsUpsellFeature3;

  /// Badge for movie recommendations in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Movie Recs For Friends'**
  String get wrappedMovieRecs;

  /// Error when file picker fails to open
  ///
  /// In en, this message translates to:
  /// **'Error opening file picker: {error}'**
  String msgFilePickerError(String error);

  /// Profession option: Entrepreneur
  ///
  /// In en, this message translates to:
  /// **'Entrepreneur'**
  String get professionEntrepreneur;

  /// Heading above recent search queries
  ///
  /// In en, this message translates to:
  /// **'Recent'**
  String get recent;

  /// Description for create memories permission
  ///
  /// In en, this message translates to:
  /// **'This app can create new memories.'**
  String get permissionDescCreateMemories;

  /// Instruction to tap to complete setup
  ///
  /// In en, this message translates to:
  /// **'Tap to complete'**
  String get tapToComplete;

  /// No description provided for @vocabularyWordCount.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 word} other{{count} words}}'**
  String vocabularyWordCount(int count);

  /// Confirmation message for deleting synced files
  ///
  /// In en, this message translates to:
  /// **'These recordings have already been synced to your phone. This can\'t be undone.'**
  String get deleteSyncedFilesMessage;

  /// Cancel consequence
  ///
  /// In en, this message translates to:
  /// **'Cannot identify speakers.'**
  String get cancelConsequenceSpeakers;

  /// Error message when AI app generation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to generate app. Please try again.'**
  String get aiGenFailedToGenerateApp;

  /// Account section label
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get account;

  /// No description provided for @capabilityIntegrations.
  ///
  /// In en, this message translates to:
  /// **'Integrations'**
  String get capabilityIntegrations;

  /// Settings switch label for periodic speaker tagging prompts
  ///
  /// In en, this message translates to:
  /// **'Ask me to tag voices'**
  String get voiceSettingsAskToTag;

  /// Large heading on the Chat apps page
  ///
  /// In en, this message translates to:
  /// **'Chat with Omi where you already chat'**
  String get chatAppsHeroTitle;

  /// Filter button for user's own apps
  ///
  /// In en, this message translates to:
  /// **'Created by me'**
  String get myApps;

  /// Menu / button label to delete a daily recap. Used on the detail page action sheet and the swipe-to-delete background.
  ///
  /// In en, this message translates to:
  /// **'Delete Recap'**
  String get deleteRecap;

  /// Label for production API environment
  ///
  /// In en, this message translates to:
  /// **'Production'**
  String get production;

  /// No description provided for @phoneRecordingBlockedByPendantBatch.
  ///
  /// In en, this message translates to:
  /// **'Stop Transcribe Later on your pendant before recording with your phone.'**
  String get phoneRecordingBlockedByPendantBatch;

  /// A data rate in kilobits per second
  ///
  /// In en, this message translates to:
  /// **'{rate} kbps'**
  String dataRateKbps(String rate);

  /// Hint text when no API keys exist
  ///
  /// In en, this message translates to:
  /// **'Create a key to get started'**
  String get createAKeyToGetStarted;

  /// Validation message to select a rating
  ///
  /// In en, this message translates to:
  /// **'Please select a rating'**
  String get pleaseSelectRating;

  /// Title for PDF transcript export document
  ///
  /// In en, this message translates to:
  /// **'Transcript Export'**
  String get pdfTranscriptExport;

  /// No description provided for @newFolder.
  ///
  /// In en, this message translates to:
  /// **'New Folder'**
  String get newFolder;

  /// Body text for notification shown when device detects a fall
  ///
  /// In en, this message translates to:
  /// **'Did you fall?'**
  String get fallNotificationBody;

  /// No description provided for @scopeUserChat.
  ///
  /// In en, this message translates to:
  /// **'User Chat'**
  String get scopeUserChat;

  /// No description provided for @tryDifferentSearchTerm.
  ///
  /// In en, this message translates to:
  /// **'Try a different search term'**
  String get tryDifferentSearchTerm;

  /// Button that sends the chat feedback
  ///
  /// In en, this message translates to:
  /// **'Submit'**
  String get submit;

  /// Teaching subtitle for the voice reply onboarding step
  ///
  /// In en, this message translates to:
  /// **'When you ask with the button, Omi can read its answer out loud.'**
  String get deviceOnboardingVoiceReplySubtitle;

  /// Setting for recording Live Activities on the lock screen and Dynamic Island
  ///
  /// In en, this message translates to:
  /// **'Show on Lock Screen'**
  String get showOnLockScreen;

  /// Error when user tries to select more than 4 images
  ///
  /// In en, this message translates to:
  /// **'You can only select up to 4 images'**
  String get msgMaxImagesLimit;

  /// Subtitle on the intro card
  ///
  /// In en, this message translates to:
  /// **'Omi Life Recap'**
  String get wrappedOmiLifeRecap;

  /// Button text to proceed to next step
  ///
  /// In en, this message translates to:
  /// **'Next'**
  String get nextButton;

  /// No description provided for @disconnectAppTitle.
  ///
  /// In en, this message translates to:
  /// **'Disconnect {appName}?'**
  String disconnectAppTitle(String appName);

  /// Button text to update review
  ///
  /// In en, this message translates to:
  /// **'Update Review'**
  String get updateReview;

  /// Empty state message when category has no memories
  ///
  /// In en, this message translates to:
  /// **'No memories in this category yet'**
  String get noMemoriesInCategory;

  /// Notification when memory deleted
  ///
  /// In en, this message translates to:
  /// **'Memory deleted'**
  String get memoryDeleted;

  /// Button text to connect Omi device
  ///
  /// In en, this message translates to:
  /// **'Connect Omi Device'**
  String get connectOmiDevice;

  /// Profession option: Software Engineer
  ///
  /// In en, this message translates to:
  /// **'Software Engineer'**
  String get professionSoftwareEngineer;

  /// No description provided for @tagOtherSegmentsFromSpeaker.
  ///
  /// In en, this message translates to:
  /// **'Tag other segments from this speaker ({selected}/{total})'**
  String tagOtherSegmentsFromSpeaker(int selected, int total);

  /// Label for product name field
  ///
  /// In en, this message translates to:
  /// **'Product Name'**
  String get productName;

  /// Error when Apple Reminders permission is denied
  ///
  /// In en, this message translates to:
  /// **'Permission denied for Apple Reminders'**
  String get permissionDeniedForAppleReminders;

  /// Success message after making all memories private
  ///
  /// In en, this message translates to:
  /// **'All memories are now private'**
  String get allMemoriesAreNowPrivate;

  /// Message when plan is set to cancel
  ///
  /// In en, this message translates to:
  /// **'Your plan is set to cancel on {date}.\nResubscribe now to keep your benefits - no charge until {date}.'**
  String planSetToCancelOn(String date);

  /// Title of the confirmation before deleting a person
  ///
  /// In en, this message translates to:
  /// **'Delete Person?'**
  String get deletePersonTitle;

  /// Dialog message explaining deletion is permanent
  ///
  /// In en, this message translates to:
  /// **'Deleting this {item} can\'t be undone.'**
  String deleteItemConfirmation(String item);

  /// No description provided for @appleHealthConnectCta.
  ///
  /// In en, this message translates to:
  /// **'Connect to Apple Health'**
  String get appleHealthConnectCta;

  /// Segment count (plural)
  ///
  /// In en, this message translates to:
  /// **'{count} segments'**
  String segmentsPlural(String count);

  /// Top status card: phase title when downloading recordings from the Omi device over BLE/Wi-Fi
  ///
  /// In en, this message translates to:
  /// **'Downloading from your device'**
  String get syncCardDownloadingTitle;

  /// Title for additional speech samples with index number
  ///
  /// In en, this message translates to:
  /// **'Additional Sample {index}'**
  String additionalSampleIndex(String index);

  /// Label for the description field
  ///
  /// In en, this message translates to:
  /// **'Description'**
  String get descriptionLabel;

  /// Error message when clearing due date fails
  ///
  /// In en, this message translates to:
  /// **'Failed to clear due date'**
  String get failedToClearDueDate;

  /// No description provided for @timeout4HoursDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 4 hours of silence'**
  String get timeout4HoursDesc;

  /// Empty-state message when the Synced filter is active but no recording has finished backing up.
  ///
  /// In en, this message translates to:
  /// **'No synced recordings yet'**
  String get noSyncedRecordingsYet;

  /// How many old queued changes were dropped because the queue was full.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 older change skipped} other{{count} older changes skipped}}'**
  String dreamReportDropped(int count);

  /// Claude Code (CLI) integration section
  ///
  /// In en, this message translates to:
  /// **'Claude Code'**
  String get claudeCode;

  /// Empty state when no pending recordings
  ///
  /// In en, this message translates to:
  /// **'No pending recordings'**
  String get noPendingRecordings;

  /// No description provided for @tellUsHowYouWouldLikeToBeAddressed.
  ///
  /// In en, this message translates to:
  /// **'Tell us how you\'d like to be addressed. This helps personalize your Omi experience.'**
  String get tellUsHowYouWouldLikeToBeAddressed;

  /// No description provided for @updateSummaryWithNewNames.
  ///
  /// In en, this message translates to:
  /// **'Update summary with new names'**
  String get updateSummaryWithNewNames;

  /// Description for conversation timeout setting
  ///
  /// In en, this message translates to:
  /// **'How long Omi waits in silence before ending a conversation'**
  String get setWhenConversationsAutoEnd;

  /// Success message when Google Tasks OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Google Tasks!'**
  String get successfullyConnectedGoogleTasks;

  /// Button text to confirm upgrade
  ///
  /// In en, this message translates to:
  /// **'Confirm Upgrade'**
  String get confirmUpgrade;

  /// Description for the speech-to-text provider selector
  ///
  /// In en, this message translates to:
  /// **'Choose the service used for transcription'**
  String get speechToTextProviderDesc;

  /// No description provided for @errorConnectingAppleWatch.
  ///
  /// In en, this message translates to:
  /// **'Error connecting to Apple Watch: {error}'**
  String errorConnectingAppleWatch(String error);

  /// No description provided for @instagram.
  ///
  /// In en, this message translates to:
  /// **'Instagram'**
  String get instagram;

  /// Label for speech sample
  ///
  /// In en, this message translates to:
  /// **'Sample {number}'**
  String sampleNumber(int number);

  /// Section title for popular apps
  ///
  /// In en, this message translates to:
  /// **'Popular Apps'**
  String get popularApps;

  /// Mic gain description: Slightly Boosted
  ///
  /// In en, this message translates to:
  /// **'Slightly boosted - normal use'**
  String get micGainDescSlightlyBoosted;

  /// Validation error when prompt is too short
  ///
  /// In en, this message translates to:
  /// **'Prompt must be at least 10 characters'**
  String get promptMustBeAtLeast10Characters;

  /// Row subtitle listing chat apps (brand names stay as-is)
  ///
  /// In en, this message translates to:
  /// **'Telegram, iMessage, and more'**
  String get chatAppsEntryRowSubtitle;

  /// Label for estimated file size
  ///
  /// In en, this message translates to:
  /// **'Estimated Size'**
  String get estimatedSizeLabel;

  /// No description provided for @mcpServerDesc.
  ///
  /// In en, this message translates to:
  /// **'Connect AI assistants to your data'**
  String get mcpServerDesc;

  /// No description provided for @disconnectHistory.
  ///
  /// In en, this message translates to:
  /// **'Disconnect History'**
  String get disconnectHistory;

  /// Free-plan limitation: noticeable transcription delay
  ///
  /// In en, this message translates to:
  /// **'5-7 second delay'**
  String get downgradeLimitDelay;

  /// Generic error when selecting images fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting images. Please try again.'**
  String get msgSelectImagesGenericError;

  /// No description provided for @audioPlaybackUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Audio file is not available for playback'**
  String get audioPlaybackUnavailable;

  /// Legal agreement intro text
  ///
  /// In en, this message translates to:
  /// **'By clicking on \"Connect Now\" you agree to the'**
  String get byClickingConnectNow;

  /// No description provided for @signalStrength.
  ///
  /// In en, this message translates to:
  /// **'Signal Strength'**
  String get signalStrength;

  /// No description provided for @tellUsPrimaryLanguage.
  ///
  /// In en, this message translates to:
  /// **'Tell us your primary language'**
  String get tellUsPrimaryLanguage;

  /// Snackbar shown when exporting device diagnostics to the share sheet fails
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t share diagnostics. Please try again.'**
  String get diagnosticsShareFailed;

  /// Create key instruction
  ///
  /// In en, this message translates to:
  /// **'Create a key to get started'**
  String get createKeyToStart;

  /// No description provided for @generatedBy.
  ///
  /// In en, this message translates to:
  /// **'Generated by {appName}'**
  String generatedBy(String appName);

  /// Share stats: listened
  ///
  /// In en, this message translates to:
  /// **'🎧 Listened for {minutes} minutes'**
  String shareStatsListened(String minutes);

  /// Widget title for device promotion
  ///
  /// In en, this message translates to:
  /// **'Get Omi Device'**
  String get getOmiDevice;

  /// Button text for creating a new task
  ///
  /// In en, this message translates to:
  /// **'New Task'**
  String get newTask;

  /// Section title for conversation prompt
  ///
  /// In en, this message translates to:
  /// **'Conversation Prompt'**
  String get conversationPrompt;

  /// OmiGlass OTA status
  ///
  /// In en, this message translates to:
  /// **'Connected to Wi-Fi'**
  String get otaWifiConnected;

  /// Hide a For You card
  ///
  /// In en, this message translates to:
  /// **'Dismiss'**
  String get dismiss;

  /// Webhooks section header
  ///
  /// In en, this message translates to:
  /// **'Webhooks'**
  String get webhooks;

  /// No description provided for @raybanMetaCamera.
  ///
  /// In en, this message translates to:
  /// **'Camera'**
  String get raybanMetaCamera;

  /// No description provided for @recapRegenerateNoConversations.
  ///
  /// In en, this message translates to:
  /// **'No conversations to summarize for this day.'**
  String get recapRegenerateNoConversations;

  /// No description provided for @pendantMinutesStored.
  ///
  /// In en, this message translates to:
  /// **'~{minutes} min stored'**
  String pendantMinutesStored(int minutes);

  /// Notification title when a device disconnects
  ///
  /// In en, this message translates to:
  /// **'{deviceName} Disconnected'**
  String deviceDisconnectedTitle(String deviceName);

  /// Normal preset
  ///
  /// In en, this message translates to:
  /// **'Normal'**
  String get normal;

  /// Error message when Apple Watch is not reachable
  ///
  /// In en, this message translates to:
  /// **'Apple Watch still not reachable. Please make sure the Omi app is open on your watch.'**
  String get appleWatchNotReachable;

  /// No description provided for @connectionGuide.
  ///
  /// In en, this message translates to:
  /// **'Connection Guide'**
  String get connectionGuide;

  /// No description provided for @syncStepProcessDesc.
  ///
  /// In en, this message translates to:
  /// **'Omi turns the audio into a conversation'**
  String get syncStepProcessDesc;

  /// Error message when plans cannot be loaded
  ///
  /// In en, this message translates to:
  /// **'Could not load available plans. Please try again.'**
  String get couldNotLoadPlans;

  /// No description provided for @minsUsedThisMonth.
  ///
  /// In en, this message translates to:
  /// **'{used} of {limit} min used this month'**
  String minsUsedThisMonth(String used, int limit);

  /// Link text to learn more (lowercase)
  ///
  /// In en, this message translates to:
  /// **'learn more'**
  String get learnMoreLink;

  /// Dialog message explaining unpair process
  ///
  /// In en, this message translates to:
  /// **'This will unpair the device so it can be connected to another phone. You will need to go to Settings > Bluetooth and forget the device to complete the process.'**
  String get unpairDeviceDialogMessage;

  /// Error message when retrieving Firebase token fails
  ///
  /// In en, this message translates to:
  /// **'Failed to retrieve firebase token, please try again.'**
  String get authFailedToRetrieveToken;

  /// Error message when app creation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create app'**
  String get aiGenFailedToCreateApp;

  /// Confirmation when version info is copied
  ///
  /// In en, this message translates to:
  /// **'App and device details copied'**
  String get appAndDeviceCopied;

  /// Empty state when no processed recordings
  ///
  /// In en, this message translates to:
  /// **'No processed recordings yet'**
  String get noProcessedRecordings;

  /// Tab label for transcript view
  ///
  /// In en, this message translates to:
  /// **'Transcript'**
  String get transcriptTab;

  /// Description for read conversations permission
  ///
  /// In en, this message translates to:
  /// **'This app can access your conversations.'**
  String get permissionDescReadConversations;

  /// No description provided for @tryAnotherApp.
  ///
  /// In en, this message translates to:
  /// **'Try Another App'**
  String get tryAnotherApp;

  /// Message that subscription is set to cancel
  ///
  /// In en, this message translates to:
  /// **'Your subscription is set to cancel at the end of the period.'**
  String get subscriptionSetToCancel;

  /// Countdown; time is like 9:12
  ///
  /// In en, this message translates to:
  /// **'Code expires in {time}'**
  String chatAppsCodeExpiresIn(String time);

  /// Error message when Apple sign-in fails
  ///
  /// In en, this message translates to:
  /// **'Failed to sign in with Apple, please try again.'**
  String get authFailedToSignInWithApple;

  /// Reason a chat reply was rated down
  ///
  /// In en, this message translates to:
  /// **'Didn\'t follow instructions'**
  String get feedbackReasonIgnoredInstructions;

  /// Disclosure on the start-up failure screen that reveals the raw technical error for support.
  ///
  /// In en, this message translates to:
  /// **'Details'**
  String get startupFailedDetails;

  /// Title of the dialog confirming deletion of one meeting screenshot
  ///
  /// In en, this message translates to:
  /// **'Delete Screenshot?'**
  String get deleteMeetingScreenshotTitle;

  /// Empty state message
  ///
  /// In en, this message translates to:
  /// **'This chat app was disconnected.'**
  String get chatAppsNotConnectedMessage;

  /// Tooltip for API keys info button
  ///
  /// In en, this message translates to:
  /// **'About Omi API Keys'**
  String get aboutOmiApiKeys;

  /// No description provided for @tiktok.
  ///
  /// In en, this message translates to:
  /// **'TikTok'**
  String get tiktok;

  /// Max files upload warning
  ///
  /// In en, this message translates to:
  /// **'You can only upload 4 files at a time'**
  String get maxFilesLimit;

  /// No description provided for @legalNotice.
  ///
  /// In en, this message translates to:
  /// **'Legal Notice: The legality of recording and storing voice data may vary depending on your location and how you use this feature. It\'s your responsibility to ensure compliance with local laws and regulations.'**
  String get legalNotice;

  /// Badge for top days in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Your Top Days'**
  String get wrappedYourTopDays;

  /// No description provided for @addMcpServer.
  ///
  /// In en, this message translates to:
  /// **'Add MCP Server'**
  String get addMcpServer;

  /// Label showing number of public apps
  ///
  /// In en, this message translates to:
  /// **'Public Apps ({count})'**
  String publicAppsCount(String count);

  /// Message shown when no external apps have data access
  ///
  /// In en, this message translates to:
  /// **'No external apps have access to your data.'**
  String get noExternalAppsHaveAccess;

  /// Home live capture card, line 1: the phone microphone recording is starting and audio is not flowing yet.
  ///
  /// In en, this message translates to:
  /// **'Starting…'**
  String get captureStarting;

  /// No description provided for @downloadingAudioProgress.
  ///
  /// In en, this message translates to:
  /// **'Downloading Audio'**
  String get downloadingAudioProgress;

  /// Webhook type for audio bytes
  ///
  /// In en, this message translates to:
  /// **'Audio Bytes'**
  String get audioBytes;

  /// Screen-reader label for a device battery level
  ///
  /// In en, this message translates to:
  /// **'Battery {level}%'**
  String batteryLevelSemantics(int level);

  /// Accessibility label for the device icons on a conversation recorded by several devices
  ///
  /// In en, this message translates to:
  /// **'Recorded by {devices}'**
  String captureRecordedBy(String devices);

  /// Note that Omi does not start conversations
  ///
  /// In en, this message translates to:
  /// **'Omi only replies to you. It never texts first.'**
  String get chatAppsRepliesOnlyNote;

  /// Button label to hide transcript
  ///
  /// In en, this message translates to:
  /// **'Hide Transcript'**
  String get hideTranscript;

  /// Permission title for reading conversations
  ///
  /// In en, this message translates to:
  /// **'Read Conversations'**
  String get permissionReadConversations;

  /// Shortened version for installed apps filter
  ///
  /// In en, this message translates to:
  /// **'Installed'**
  String get installed;

  /// Validation error when amount is not a valid number
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid amount'**
  String get paymentEnterValidAmount;

  /// Button: choose a Custom STT language different from the primary language
  ///
  /// In en, this message translates to:
  /// **'Override'**
  String get sttLanguageOverride;

  /// Section title for app interface language settings
  ///
  /// In en, this message translates to:
  /// **'App Interface'**
  String get appInterfaceSectionTitle;

  /// No description provided for @searchLanguages.
  ///
  /// In en, this message translates to:
  /// **'Search languages'**
  String get searchLanguages;

  /// No description provided for @otherSource.
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get otherSource;

  /// Pairing description for Omi Glass
  ///
  /// In en, this message translates to:
  /// **'Power on by pressing the side button for 3 seconds.'**
  String get pairingDescOmiGlass;

  /// Sign out button
  ///
  /// In en, this message translates to:
  /// **'Sign Out'**
  String get signOut;

  /// Share stats: words
  ///
  /// In en, this message translates to:
  /// **'🧠 Understood {words} words'**
  String shareStatsWords(String words);

  /// No description provided for @verifiedDaysAgo.
  ///
  /// In en, this message translates to:
  /// **'Verified {days}d ago'**
  String verifiedDaysAgo(int days);

  /// Short label for the Transcribe Later mode shown on the home app-bar mode chip
  ///
  /// In en, this message translates to:
  /// **'Later'**
  String get captureModeLater;

  /// Link to enable more apps
  ///
  /// In en, this message translates to:
  /// **'Enable More Apps'**
  String get enableMoreApps;

  /// Description for balanced notification frequency
  ///
  /// In en, this message translates to:
  /// **'Useful suggestions, about 5–8 a day'**
  String get frequencyDescBalanced;

  /// Call-to-action text for first recording
  ///
  /// In en, this message translates to:
  /// **'Start Your First Recording'**
  String get startYourFirstRecording;

  /// No description provided for @transcriptionPausedReconnecting.
  ///
  /// In en, this message translates to:
  /// **'Still recording — reconnecting to transcription…'**
  String get transcriptionPausedReconnecting;

  /// Basic plan name
  ///
  /// In en, this message translates to:
  /// **'Free Plan'**
  String get basicPlan;

  /// Default fallback name when user name is empty
  ///
  /// In en, this message translates to:
  /// **'User'**
  String get user;

  /// Subtitle under the Pin switch on a person's page: what pinning does.
  ///
  /// In en, this message translates to:
  /// **'Pinned people stay at the top of your People list and aren\'t removed by Clean Up.'**
  String get pinPersonDescription;

  /// Row label: the project a task belongs to
  ///
  /// In en, this message translates to:
  /// **'Project'**
  String get reviewProject;

  /// Keyboard shortcuts section
  ///
  /// In en, this message translates to:
  /// **'Keyboard Shortcuts'**
  String get keyboardShortcuts;

  /// Badge on a device diagnostics event where the device failed to connect
  ///
  /// In en, this message translates to:
  /// **'Failed'**
  String get diagnosticsFailBadge;

  /// Confirmation message after clearing debug logs
  ///
  /// In en, this message translates to:
  /// **'Debug log cleared'**
  String get debugLogCleared;

  /// Error message when Stripe connection fails
  ///
  /// In en, this message translates to:
  /// **'Error connecting to Stripe! Please try again later.'**
  String get errorConnectingToStripe;

  /// Empty-home hint pointing at the round record button
  ///
  /// In en, this message translates to:
  /// **'Tap the record button to start recording'**
  String get tapPlusToStartRecording;

  /// Shown under a permission the system will no longer ask for
  ///
  /// In en, this message translates to:
  /// **'Turned off in Settings. Allow it there to use this.'**
  String get permissionBlockedHint;

  /// No description provided for @downloadingAudio.
  ///
  /// In en, this message translates to:
  /// **'Downloading audio…'**
  String get downloadingAudio;

  /// Error message when API key revocation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to revoke API key: {error}'**
  String failedToRevokeApiKey(String error);

  /// No description provided for @largeTimeGapDetected.
  ///
  /// In en, this message translates to:
  /// **'Large time gap detected ({gap})'**
  String largeTimeGapDetected(String gap);

  /// No description provided for @customFirmwareWarning.
  ///
  /// In en, this message translates to:
  /// **'Flashing custom firmware can brick your device. Make sure this is a valid Omi firmware build. Do not disconnect during the update.'**
  String get customFirmwareWarning;

  /// Wrapped 2025 menu item
  ///
  /// In en, this message translates to:
  /// **'Wrapped 2025'**
  String get wrapped2025;

  /// No description provided for @showApiKey.
  ///
  /// In en, this message translates to:
  /// **'Show API Key'**
  String get showApiKey;

  /// Button label on the data and AI consent screen — explicit consent action.
  ///
  /// In en, this message translates to:
  /// **'Agree & Continue'**
  String get agreeAndContinue;

  /// No description provided for @connectExternalAiTools.
  ///
  /// In en, this message translates to:
  /// **'Connect external AI tools'**
  String get connectExternalAiTools;

  /// No description provided for @batteryFullyChargedTitle.
  ///
  /// In en, this message translates to:
  /// **'Omi is fully charged'**
  String get batteryFullyChargedTitle;

  /// Title of the dialog shown when re-enabling a disabled app is rejected
  ///
  /// In en, this message translates to:
  /// **'Could not re-enable'**
  String get appReEnableFailedTitle;

  /// Onboarding step title for name entry
  ///
  /// In en, this message translates to:
  /// **'Your Name'**
  String get onboardingYourName;

  /// Placeholder text for search input
  ///
  /// In en, this message translates to:
  /// **'Search apps'**
  String get searchApps;

  /// No description provided for @weak.
  ///
  /// In en, this message translates to:
  /// **'Weak'**
  String get weak;

  /// Label for optional details text field
  ///
  /// In en, this message translates to:
  /// **'Tell us more (optional)'**
  String get tellUsMore;

  /// Reason line under a person's name: how many voice suggestion cards the user answered with this person.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Picked in 1 suggestion} other{Picked in {count} suggestions}}'**
  String confidenceReasonPicked(int count);

  /// Footer under the disconnect row
  ///
  /// In en, this message translates to:
  /// **'Disconnecting deletes the history Omi keeps for {app}.'**
  String chatAppsDisconnectFooter(String app);

  /// Tooltip for select all
  ///
  /// In en, this message translates to:
  /// **'Select All'**
  String get selectAll;

  /// Confirmation message for deleting action item
  ///
  /// In en, this message translates to:
  /// **'Delete this task? This can\'t be undone.'**
  String get deleteActionItemConfirmation;

  /// No description provided for @categoryTravel.
  ///
  /// In en, this message translates to:
  /// **'Travel'**
  String get categoryTravel;

  /// No description provided for @lowestRating.
  ///
  /// In en, this message translates to:
  /// **'Lowest Rating'**
  String get lowestRating;

  /// Guidance on the empty Tasks tab: start a conversation to create a task.
  ///
  /// In en, this message translates to:
  /// **'Start a conversation to create a task.'**
  String get tasksEmptyStateMessage;

  /// Unpair and forget device button
  ///
  /// In en, this message translates to:
  /// **'Unpair and Forget Device'**
  String get unpairAndForget;

  /// Status when listening for audio
  ///
  /// In en, this message translates to:
  /// **'Listening for audio…'**
  String get listeningForAudio;

  /// No description provided for @processedStatus.
  ///
  /// In en, this message translates to:
  /// **'Processed'**
  String get processedStatus;

  /// Default title for struggle
  ///
  /// In en, this message translates to:
  /// **'The Hard Part'**
  String get wrappedTheHardPart;

  /// Success banner subtitle; app is Telegram or Messages
  ///
  /// In en, this message translates to:
  /// **'Message Omi in {app} anytime.'**
  String chatAppsReplyThereAnytime(String app);

  /// No description provided for @upgradePlan.
  ///
  /// In en, this message translates to:
  /// **'Upgrade Plan'**
  String get upgradePlan;

  /// Store rating pre-prompt: open the store review sheet
  ///
  /// In en, this message translates to:
  /// **'Yes'**
  String get onboardingRatingPromptYes;

  /// Compact duration in minutes
  ///
  /// In en, this message translates to:
  /// **'{count}m'**
  String timeCompactMins(int count);

  /// No description provided for @changeTheConversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Change the conversation title'**
  String get changeTheConversationTitle;

  /// Account group title
  ///
  /// In en, this message translates to:
  /// **'Account'**
  String get accountGroup;

  /// Loading message when updating app
  ///
  /// In en, this message translates to:
  /// **'Updating your app'**
  String get updatingYourApp;

  /// Label for microphone permission
  ///
  /// In en, this message translates to:
  /// **'Microphone'**
  String get microphone;

  /// Description for follow-up questions
  ///
  /// In en, this message translates to:
  /// **'Suggest questions after conversations'**
  String get suggestQuestionsAfterConversations;

  /// Error message when audio transcription fails
  ///
  /// In en, this message translates to:
  /// **'Failed to transcribe audio'**
  String get failedToTranscribeAudio;

  /// Accessible name for the conversation-detail star button when the conversation is already starred
  ///
  /// In en, this message translates to:
  /// **'Unstar Conversation'**
  String get unstarConversation;

  /// Answer button: the clip is not the user's voice
  ///
  /// In en, this message translates to:
  /// **'Not me'**
  String get speakerTagPromptNotMe;

  /// Reason line under a person's name: the user moved an automatic match for this person to someone else.
  ///
  /// In en, this message translates to:
  /// **'You corrected its match'**
  String get confidenceReasonCorrected;

  /// Search field placeholder on the People list
  ///
  /// In en, this message translates to:
  /// **'Search people'**
  String get peopleSearchPlaceholder;

  /// Sync row status when the server's transcription job permanently rejected the recording's audio, so retrying cannot help.
  ///
  /// In en, this message translates to:
  /// **'Audio couldn\'t be read — can\'t be synced'**
  String get syncStatusUnsupportedAudio;

  /// Menu action: nest a task one level under the task above it
  ///
  /// In en, this message translates to:
  /// **'Indent'**
  String get indentTask;

  /// Section header for selecting an app
  ///
  /// In en, this message translates to:
  /// **'Select App'**
  String get selectApp;

  /// App bar title when updating PayPal
  ///
  /// In en, this message translates to:
  /// **'Update PayPal'**
  String get updatePayPal;

  /// Error when name field is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter your name'**
  String get enterNameError;

  /// Export all data feature name
  ///
  /// In en, this message translates to:
  /// **'Export All Data'**
  String get exportAllData;

  /// Message showing remaining premium minutes
  ///
  /// In en, this message translates to:
  /// **'{count} premium mins left.'**
  String premiumMinsLeft(int count);

  /// No description provided for @setAsDefaultSummarizationApp.
  ///
  /// In en, this message translates to:
  /// **'{appName} set as default summarization app'**
  String setAsDefaultSummarizationApp(String appName);

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Recording started successfully!'**
  String get recordingStartedSuccessfully;

  /// No description provided for @trySomethingLike.
  ///
  /// In en, this message translates to:
  /// **'Try something like…'**
  String get trySomethingLike;

  /// Section header above example questions to send Omi
  ///
  /// In en, this message translates to:
  /// **'Try asking'**
  String get chatAppsTryAsking;

  /// No description provided for @categoryEntertainment.
  ///
  /// In en, this message translates to:
  /// **'Entertainment'**
  String get categoryEntertainment;

  /// Step 1: Checking for audio files
  ///
  /// In en, this message translates to:
  /// **'Checks for audio files on the SD Card'**
  String get checksForAudioFiles;

  /// Section header in the picker listing all people A to Z (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Everyone'**
  String get everyoneHeader;

  /// Button text to confirm clearing all memories
  ///
  /// In en, this message translates to:
  /// **'Clear Memory'**
  String get clearMemoryButton;

  /// Reason line under a person's name: how many conversations the user labeled them in by hand.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{You labeled once} other{You labeled {count} times}}'**
  String confidenceReasonLabeled(int count);

  /// Title for log file selection dialog
  ///
  /// In en, this message translates to:
  /// **'Select Log File'**
  String get selectLogFile;

  /// Step 3
  ///
  /// In en, this message translates to:
  /// **'Come back here. We\'ll confirm it worked.'**
  String get chatAppsTelegramStepReturn;

  /// No description provided for @discordMemberCount.
  ///
  /// In en, this message translates to:
  /// **'8000+ members on Discord'**
  String get discordMemberCount;

  /// Option for public memory visibility
  ///
  /// In en, this message translates to:
  /// **'Public'**
  String get public;

  /// Menu action: move a nested task one level back out
  ///
  /// In en, this message translates to:
  /// **'Outdent'**
  String get outdentTask;

  /// Import job status - processing
  ///
  /// In en, this message translates to:
  /// **'Processing'**
  String get statusProcessing;

  /// Button to use free plan
  ///
  /// In en, this message translates to:
  /// **'Use Free Plan'**
  String get useFreePlan;

  /// Label for email input field
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get emailLabel;

  /// No description provided for @statusCallInProgress.
  ///
  /// In en, this message translates to:
  /// **'Call in progress'**
  String get statusCallInProgress;

  /// No description provided for @shortcuts.
  ///
  /// In en, this message translates to:
  /// **'Shortcuts'**
  String get shortcuts;

  /// Link and page title: changes the app made on its own (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Recent Changes'**
  String get reviewRecentChanges;

  /// No description provided for @raybanMetaAudioOnlyExplanation.
  ///
  /// In en, this message translates to:
  /// **'This version of Omi can use your glasses microphone over Bluetooth. Photo capture needs the Meta developer build of Omi.'**
  String get raybanMetaAudioOnlyExplanation;

  /// Label under days active count
  ///
  /// In en, this message translates to:
  /// **'days active'**
  String get wrappedDaysActiveLabel;

  /// Title prompting user to install Omi on Apple Watch
  ///
  /// In en, this message translates to:
  /// **'Install Omi on your\nApple Watch'**
  String get installOmiOnAppleWatch;

  /// Screen-reader label for the task count beside a section header
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 task} other{{count} tasks}}'**
  String tasksCountLabel(int count);

  /// Second half of a reason line, after a middle dot: Omi has a voice sample for this person. Lowercase because it follows a separator.
  ///
  /// In en, this message translates to:
  /// **'voice saved'**
  String get confidenceReasonVoiceReady;

  /// Confirmation message for bulk delete
  ///
  /// In en, this message translates to:
  /// **'Delete {count} selected task{s}?'**
  String deleteSelectedItemsMessage(int count, String s);

  /// Menu item for SD card synchronization
  ///
  /// In en, this message translates to:
  /// **'SD Card Sync'**
  String get sdCardSync;

  /// No description provided for @timeout4Hours.
  ///
  /// In en, this message translates to:
  /// **'4 hours'**
  String get timeout4Hours;

  /// Title for chat apps drawer/section
  ///
  /// In en, this message translates to:
  /// **'Chat Apps'**
  String get chatAppsTitle;

  /// Label for repeat password input field
  ///
  /// In en, this message translates to:
  /// **'Repeat Password'**
  String get repeatPasswordLabel;

  /// No description provided for @skip.
  ///
  /// In en, this message translates to:
  /// **'Skip'**
  String get skip;

  /// No description provided for @phoneNoVerifiedNumbersTitle.
  ///
  /// In en, this message translates to:
  /// **'No Verified Numbers'**
  String get phoneNoVerifiedNumbersTitle;

  /// Title for lost connection dialog
  ///
  /// In en, this message translates to:
  /// **'Connection Lost'**
  String get connectionLost;

  /// Message shown when a photo was discarded as not significant
  ///
  /// In en, this message translates to:
  /// **'This photo was discarded as it was not significant.'**
  String get photoDiscardedMessage;

  /// Abbreviated Friday
  ///
  /// In en, this message translates to:
  /// **'Fri'**
  String get weekdayFri;

  /// Title for the move to folder bottom sheet
  ///
  /// In en, this message translates to:
  /// **'Move to Folder'**
  String get moveToFolder;

  /// Button text to start firmware update
  ///
  /// In en, this message translates to:
  /// **'Update Now'**
  String get updateNow;

  /// Error message when updating action item fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update task'**
  String get failedToUpdateActionItem;

  /// Description explaining why transfer is needed
  ///
  /// In en, this message translates to:
  /// **'This recording is stored on your device\'s SD card. Transfer it to your phone to play or share.'**
  String get transferRequiredDescription;

  /// Title shown while checking for updates
  ///
  /// In en, this message translates to:
  /// **'Checking for Updates'**
  String get checkingForUpdates;

  /// Subtitle on the transcript-files import card
  ///
  /// In en, this message translates to:
  /// **'Select SRT, VTT or TXT transcripts, or a ZIP of them'**
  String get importTranscriptFilesDescription;

  /// Button text to listen to speech profile
  ///
  /// In en, this message translates to:
  /// **'Listen to my speech profile'**
  String get listenToSpeechProfile;

  /// Body of the confirm dialog clarifying that conversations are not deleted with the recap.
  ///
  /// In en, this message translates to:
  /// **'This recap will be permanently removed. The original conversations from that day are not affected.'**
  String get deleteRecapConfirmBody;

  /// No description provided for @copyLogs.
  ///
  /// In en, this message translates to:
  /// **'Copy Logs'**
  String get copyLogs;

  /// Label for funniest moment
  ///
  /// In en, this message translates to:
  /// **'Funniest'**
  String get wrappedFunniestMoment;

  /// Error when microphone permission is needed
  ///
  /// In en, this message translates to:
  /// **'Microphone permission is required for recording.'**
  String get onboardingMicrophoneRequired;

  /// Title of the picker sheet opened from Someone Else… (Title Case question).
  ///
  /// In en, this message translates to:
  /// **'Who Is It?'**
  String get whoIsItTitle;

  /// Remaining manual runs today.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 manual run left today} other{{count} manual runs left today}}'**
  String dreamReportRunsLeft(int count);

  /// No description provided for @modified.
  ///
  /// In en, this message translates to:
  /// **'Modified'**
  String get modified;

  /// No description provided for @actionCreateConversations.
  ///
  /// In en, this message translates to:
  /// **'Create conversations'**
  String get actionCreateConversations;

  /// Title for chat assistants capability page
  ///
  /// In en, this message translates to:
  /// **'Chat Assistants'**
  String get chatAssistantsTitle;

  /// Title for connection error dialog
  ///
  /// In en, this message translates to:
  /// **'Connection Error'**
  String get connectionError;

  /// File option: choose from gallery subtitle
  ///
  /// In en, this message translates to:
  /// **'Choose from gallery'**
  String get chooseFromGallery;

  /// Title for summary prompt section
  ///
  /// In en, this message translates to:
  /// **'Summary Prompt'**
  String get summaryPrompt;

  /// Title of the sheet that asks why a chat reply was rated down
  ///
  /// In en, this message translates to:
  /// **'What Went Wrong?'**
  String get whatWentWrong;

  /// Encouragement message during speech recording
  ///
  /// In en, this message translates to:
  /// **'Keep going, you are doing great'**
  String get keepGoingGreat;

  /// Header device pill while a paired device reconnects
  ///
  /// In en, this message translates to:
  /// **'Connecting…'**
  String get deviceConnecting;

  /// Free-plan limitation: 7x battery consumption
  ///
  /// In en, this message translates to:
  /// **'7x battery consumption'**
  String get downgradeLimitBattery;

  /// Label
  ///
  /// In en, this message translates to:
  /// **'Private memories'**
  String get privateMemories;

  /// No description provided for @vocabularyHint.
  ///
  /// In en, this message translates to:
  /// **'Omi, Callie, OpenAI'**
  String get vocabularyHint;

  /// Validation error when app description is empty in AI app generator
  ///
  /// In en, this message translates to:
  /// **'Please enter a description for your app'**
  String get aiGenPleaseEnterDescription;

  /// No description provided for @enterLiveSttWebsocket.
  ///
  /// In en, this message translates to:
  /// **'Enter your live STT WebSocket endpoint'**
  String get enterLiveSttWebsocket;

  /// No description provided for @processingOnServerProgress.
  ///
  /// In en, this message translates to:
  /// **'Processing… {current}/{total} segments'**
  String processingOnServerProgress(int current, int total);

  /// Snackbar shown after a conversation is linked to a calendar event
  ///
  /// In en, this message translates to:
  /// **'Linked to \"{title}\"'**
  String linkedToEvent(String title);

  /// Error message when saving memory fails
  ///
  /// In en, this message translates to:
  /// **'Failed to save. Please check your connection.'**
  String get failedToSaveCheckConnection;

  /// Onboarding tutorial primary button label to advance to the next step
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get deviceOnboardingContinue;

  /// No description provided for @pairedToAnotherPhone.
  ///
  /// In en, this message translates to:
  /// **'Paired to another phone'**
  String get pairedToAnotherPhone;

  /// Status message shown while recordings are being synced
  ///
  /// In en, this message translates to:
  /// **'Syncing your recordings'**
  String get syncingYourRecordings;

  /// Filter option for manual memories
  ///
  /// In en, this message translates to:
  /// **'Manual'**
  String get manual;

  /// No description provided for @oneMonthAgo.
  ///
  /// In en, this message translates to:
  /// **'1 month ago'**
  String get oneMonthAgo;

  /// Clear chat confirmation message
  ///
  /// In en, this message translates to:
  /// **'All messages in this chat are deleted. This can\'t be undone.'**
  String get clearChatConfirm;

  /// Dialog message explaining key revocation is permanent
  ///
  /// In en, this message translates to:
  /// **'Anything using \"{keyName}\" loses access. This can\'t be undone.'**
  String revokeKeyConfirmation(String keyName);

  /// No description provided for @vadGateDescription.
  ///
  /// In en, this message translates to:
  /// **'Skips silent audio before transcription to cut cost.'**
  String get vadGateDescription;

  /// Label for a run started by the hourly schedule.
  ///
  /// In en, this message translates to:
  /// **'Scheduled'**
  String get dreamReportScheduled;

  /// Description for audio bytes webhook
  ///
  /// In en, this message translates to:
  /// **'Audio data received'**
  String get audioDataReceived;

  /// Badge label for pro/unlimited users
  ///
  /// In en, this message translates to:
  /// **'Pro'**
  String get pro;

  /// Mic gain description: Muted
  ///
  /// In en, this message translates to:
  /// **'Microphone is muted'**
  String get micGainDescMuted;

  /// No description provided for @enableLocationDescription.
  ///
  /// In en, this message translates to:
  /// **'Location permission is needed to find nearby Bluetooth devices.'**
  String get enableLocationDescription;

  /// No description provided for @conversationTitleUpdatedSuccessfully.
  ///
  /// In en, this message translates to:
  /// **'Conversation title updated successfully'**
  String get conversationTitleUpdatedSuccessfully;

  /// No description provided for @syncStepUpload.
  ///
  /// In en, this message translates to:
  /// **'Sync'**
  String get syncStepUpload;

  /// Accessibility label and tooltip of the X on an app screenshot in the submit/update app form
  ///
  /// In en, this message translates to:
  /// **'Remove screenshot'**
  String get removeScreenshot;

  /// No description provided for @failedToStartCall.
  ///
  /// In en, this message translates to:
  /// **'Failed to start call'**
  String get failedToStartCall;

  /// Device diagnostics support upload
  ///
  /// In en, this message translates to:
  /// **'Review the diagnostics JSON below. It includes your device identifier, connection history, battery readings, firmware diagnostics, and BLE events. No audio or transcripts are included.'**
  String get deviceDiagnosticsUploadDescription;

  /// Pairing title for Fieldy device
  ///
  /// In en, this message translates to:
  /// **'Put Fieldy in Pairing Mode'**
  String get pairingTitleFieldy;

  /// Developer settings - autoDeletesAfterThreeDays
  ///
  /// In en, this message translates to:
  /// **'Auto-deletes after 3 days.'**
  String get autoDeletesAfterThreeDays;

  /// Label for days active stat in Wrapped
  ///
  /// In en, this message translates to:
  /// **'days active'**
  String get wrappedDaysActive;

  /// Error message when deleting action item fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete task'**
  String get failedToDeleteActionItem;

  /// Title for device connection page
  ///
  /// In en, this message translates to:
  /// **'Connect'**
  String get connect;

  /// Title for delete error dialog
  ///
  /// In en, this message translates to:
  /// **'Unable to Delete Conversation'**
  String get unableToDeleteConversation;

  /// Menu item text for clearing chat history
  ///
  /// In en, this message translates to:
  /// **'Clear Chat'**
  String get clearChatAction;

  /// Provenance label when capture device is this iPhone
  ///
  /// In en, this message translates to:
  /// **'This iPhone'**
  String get memoryThisIphone;

  /// Details sheet opened from the Home live capture card when the user's custom speech-to-text endpoint cannot be reached; audio is buffered on the phone.
  ///
  /// In en, this message translates to:
  /// **'Your custom speech-to-text service can\'t be reached. Omi keeps your audio on this phone and sends it when the service is back. Nothing is lost.'**
  String get captureCustomSttUnreachableDetail;

  /// Button on the summary/recording feedback prompt that opens the quick feedback sheet.
  ///
  /// In en, this message translates to:
  /// **'Give feedback'**
  String get feedbackGiveFeedback;

  /// failedToUpdateSettings message
  ///
  /// In en, this message translates to:
  /// **'Failed to update settings: {error}'**
  String failedToUpdateSettings(String error);

  /// Confirmation message for deleting a recording
  ///
  /// In en, this message translates to:
  /// **'This can\'t be undone.'**
  String get deleteRecordingConfirmation;

  /// No description provided for @advancedSettings.
  ///
  /// In en, this message translates to:
  /// **'Advanced Settings'**
  String get advancedSettings;

  /// Status when an active call transcription socket receives no audio frames
  ///
  /// In en, this message translates to:
  /// **'Transcription not receiving audio'**
  String get transcriptionNoAudio;

  /// Destructive button at the bottom of the clean-up review (Title Case).
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Delete 1 Person} other{Delete {count} People}}'**
  String deletePeopleCountAction(int count);

  /// Note in the expanded transcript suggestion: the answer labels the whole speaker.
  ///
  /// In en, this message translates to:
  /// **'Applies to every line from this speaker'**
  String get speakerSuggestionAppliesToSpeaker;

  /// Error message when device times out
  ///
  /// In en, this message translates to:
  /// **'Device did not respond. Please try again.'**
  String get deviceNotResponding;

  /// Message when all is synced
  ///
  /// In en, this message translates to:
  /// **'Everything is already synced.'**
  String get everythingSynced;

  /// Toast body when a Whisper model download fails
  ///
  /// In en, this message translates to:
  /// **'Failed to download Whisper model. Please try again.'**
  String get onDeviceModelDownloadFailedDesc;

  /// No description provided for @fairUseBannerStatus.
  ///
  /// In en, this message translates to:
  /// **'Fair Use: {status}'**
  String fairUseBannerStatus(String status);

  /// No description provided for @tasksDeleteSelected.
  ///
  /// In en, this message translates to:
  /// **'Delete {count} task(s)'**
  String tasksDeleteSelected(int count);

  /// Info message explaining how to connect payment method
  ///
  /// In en, this message translates to:
  /// **'Connect a payment method below to start receiving payouts for your apps.'**
  String get connectPaymentMethodInfo;

  /// Error message when conversation cannot be found
  ///
  /// In en, this message translates to:
  /// **'Conversation not found or has been deleted'**
  String get conversationNotFoundOrDeleted;

  /// No description provided for @leaveFlowStepOf.
  ///
  /// In en, this message translates to:
  /// **'Step {current} of {total}'**
  String leaveFlowStepOf(int current, int total);

  /// Instruction to type DELETE to confirm
  ///
  /// In en, this message translates to:
  /// **'Type DELETE to confirm'**
  String get deleteTypeToConfirm;

  /// Dialog title for clearing memory
  ///
  /// In en, this message translates to:
  /// **'Clear Omi\'s Memory'**
  String get clearMemoryTitle;

  /// No description provided for @triggerConversationCreation.
  ///
  /// In en, this message translates to:
  /// **'Conversation Creation'**
  String get triggerConversationCreation;

  /// No description provided for @flashCustomFirmware.
  ///
  /// In en, this message translates to:
  /// **'Flash Custom Firmware'**
  String get flashCustomFirmware;

  /// Button text when 1 contact selected
  ///
  /// In en, this message translates to:
  /// **'Share with {count} contact'**
  String shareWithContactCount(int count);

  /// No description provided for @customChatbotPersonality.
  ///
  /// In en, this message translates to:
  /// **'Custom Chatbot Personality'**
  String get customChatbotPersonality;

  /// Notice shown to beta testers of private apps
  ///
  /// In en, this message translates to:
  /// **'You are a beta tester for this app. It is not public yet. It will be public once approved.'**
  String get betaTesterNotice;

  /// Label for tomorrow in date headers
  ///
  /// In en, this message translates to:
  /// **'Tomorrow'**
  String get tomorrow;

  /// Label for created date
  ///
  /// In en, this message translates to:
  /// **'CREATED'**
  String get createdLabel;

  /// Hint for the person search field in the tag-speaker sheet
  ///
  /// In en, this message translates to:
  /// **'Search people'**
  String get searchPeople;

  /// Status when download is cancelled
  ///
  /// In en, this message translates to:
  /// **'Cancelled'**
  String get cancelled;

  /// Basic plan description
  ///
  /// In en, this message translates to:
  /// **'Your plan includes {limit} free minutes per month. Upgrade to go unlimited.'**
  String basicPlanDesc(int limit);

  /// Title of the memory edit sheet
  ///
  /// In en, this message translates to:
  /// **'Edit Memory'**
  String get editMemoryTitle;

  /// Ask: under the greeting
  ///
  /// In en, this message translates to:
  /// **'What do you want to know?'**
  String get whatDoYouWantToKnow;

  /// Footnote at the bottom of the confidence sheet.
  ///
  /// In en, this message translates to:
  /// **'Labels and confirmations from you count most. Automatic labels count for little until you confirm them.'**
  String get confidenceFootnote;

  /// No description provided for @exportFailedTryAgain.
  ///
  /// In en, this message translates to:
  /// **'Export failed. Please try again.'**
  String get exportFailedTryAgain;

  /// Error when photos permission is denied
  ///
  /// In en, this message translates to:
  /// **'Photos permission denied. Please allow access to photos to select an image'**
  String get addAppPhotosPermissionDenied;

  /// Accessible name for the conversations calendar filter button
  ///
  /// In en, this message translates to:
  /// **'Filter by date'**
  String get filterByDate;

  /// Capability bullet
  ///
  /// In en, this message translates to:
  /// **'Sends and receives files, photos, and voice notes'**
  String get chatAppsDoesFiles;

  /// Dialog title for delete knowledge graph confirmation
  ///
  /// In en, this message translates to:
  /// **'Delete Knowledge Graph?'**
  String get deleteKnowledgeGraphTitle;

  /// Loading message when refreshing conversations
  ///
  /// In en, this message translates to:
  /// **'Reloading conversations…'**
  String get reloadingConversations;

  /// Validation error when trying to submit without generating app first
  ///
  /// In en, this message translates to:
  /// **'Please generate an app first'**
  String get aiGenPleaseGenerateAppFirst;

  /// No description provided for @completeYourUpgrade.
  ///
  /// In en, this message translates to:
  /// **'Complete Your Upgrade'**
  String get completeYourUpgrade;

  /// Details sheet from the Home live capture card when the pendant disconnected in the middle of a capture.
  ///
  /// In en, this message translates to:
  /// **'Your pendant lost its connection to this phone. Omi reconnects on its own when the pendant is on and nearby. Everything recorded before this is safe.'**
  String get capturePendantDisconnectedDetail;

  /// Home greeting (large title) for 8 AM to 10 AM; keep it short so the first name fits after it on one line
  ///
  /// In en, this message translates to:
  /// **'Morning'**
  String get greetingMorning;

  /// Snackbar shown after the user gives feedback on an AI chat message
  ///
  /// In en, this message translates to:
  /// **'Thanks for your feedback!'**
  String get thanksForYourFeedback;

  /// Dialog message
  ///
  /// In en, this message translates to:
  /// **'Delete this task?'**
  String get deleteActionItemConfirmMessage;

  /// No description provided for @syncCardProcessing.
  ///
  /// In en, this message translates to:
  /// **'Processing on Omi…'**
  String get syncCardProcessing;

  /// Example request to send Omi
  ///
  /// In en, this message translates to:
  /// **'Summarize my week in three lines'**
  String get chatAppsTryWeek;

  /// Subtitle for the phone-mic option in the record-options sheet
  ///
  /// In en, this message translates to:
  /// **'Record and transcribe with this phone\'s microphone'**
  String get recordWithPhoneMicSubtitle;

  /// AppBar title for notifications settings page
  ///
  /// In en, this message translates to:
  /// **'Notifications'**
  String get notifications;

  /// Info that annual plan starts automatically
  ///
  /// In en, this message translates to:
  /// **'Your annual plan will start automatically when your monthly plan ends.'**
  String get annualPlanStartsAutomatically;

  /// Unpair dialog message
  ///
  /// In en, this message translates to:
  /// **'This will unpair the device so it can be connected to another phone. You will need to go to Settings > Bluetooth and forget the device to complete the process.'**
  String get unpairDialogMessage;

  /// Pairing title for Bee device
  ///
  /// In en, this message translates to:
  /// **'Put Bee in Pairing Mode'**
  String get pairingTitleBee;

  /// A count of conversations (recap cards, map places)
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 conversation} other{{count} conversations}}'**
  String conversationCount(int count);

  /// No description provided for @syncStatusWaiting.
  ///
  /// In en, this message translates to:
  /// **'Waiting to sync'**
  String get syncStatusWaiting;

  /// No description provided for @validWebsocketUrlRequired.
  ///
  /// In en, this message translates to:
  /// **'Valid WebSocket URL is required (wss://)'**
  String get validWebsocketUrlRequired;

  /// No description provided for @improveSpeechProfile.
  ///
  /// In en, this message translates to:
  /// **'Improve Your Speech Profile'**
  String get improveSpeechProfile;

  /// A task blocked on someone
  ///
  /// In en, this message translates to:
  /// **'Waiting on {name}'**
  String entityWaitingOn(String name);

  /// Reason a chat reply was rated down
  ///
  /// In en, this message translates to:
  /// **'Too verbose'**
  String get feedbackReasonTooVerbose;

  /// Footer under a chat app's settings
  ///
  /// In en, this message translates to:
  /// **'Your {app} chats stay in {app}. Omi still knows what you talked about in the app and your other chat apps.'**
  String chatAppsChannelFooter(String app);

  /// Shown when wrapped result is null
  ///
  /// In en, this message translates to:
  /// **'No data available'**
  String get wrappedNoDataAvailable;

  /// Footer explaining the complete Settings menu path for replaying the device tutorial
  ///
  /// In en, this message translates to:
  /// **'Replay this tour anytime in {settings} › {deviceSettings} › {deviceTutorial}'**
  String deviceOnboardingAllSetReplayHint(String settings, String deviceSettings, String deviceTutorial);

  /// Dialog title for creating a new API key
  ///
  /// In en, this message translates to:
  /// **'Create a Key'**
  String get createAKey;

  /// Success message when Notion OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Notion!'**
  String get successfullyConnectedNotion;

  /// Details sheet opened from the Home live capture card when a call or another app took the microphone. Explains the pause and that it resumes by itself.
  ///
  /// In en, this message translates to:
  /// **'A call or another app took the microphone, so Omi can\'t hear right now. Omi resumes on its own when the microphone is free. Everything recorded before this is safe.'**
  String get captureMicInterruptedDetail;

  /// Error when screen capture permission is denied
  ///
  /// In en, this message translates to:
  /// **'Screen capture permission denied. Please grant permission in System Preferences > Privacy & Security > Screen Recording.'**
  String get onboardingScreenCaptureDenied;

  /// Status message when initializing recording
  ///
  /// In en, this message translates to:
  /// **'Setting up…'**
  String get settingUp;

  /// Notification frequency level - low
  ///
  /// In en, this message translates to:
  /// **'Low'**
  String get frequencyLow;

  /// Filter option label meaning "automatic"
  ///
  /// In en, this message translates to:
  /// **'Auto'**
  String get sttFilterAuto;

  /// Shown in chat when a pendant voice question contains no detectable speech.
  ///
  /// In en, this message translates to:
  /// **'Didn\'t catch that — try again'**
  String get voiceQuestionNoSpeech;

  /// Info message recommending Stripe over PayPal
  ///
  /// In en, this message translates to:
  /// **'If Stripe is available in your country, we highly recommend using it for faster and easier payouts.'**
  String get stripeRecommendation;

  /// Text shown when user confirms firmware update
  ///
  /// In en, this message translates to:
  /// **'Confirmed!'**
  String get confirmed;

  /// Warning message for deleting pending files
  ///
  /// In en, this message translates to:
  /// **'These recordings have NOT been synced to your phone and will be permanently lost. This can\'t be undone.'**
  String get deletePendingFilesWarning;

  /// No description provided for @removeFilter.
  ///
  /// In en, this message translates to:
  /// **'Remove Filter'**
  String get removeFilter;

  /// Dialog title for model download
  ///
  /// In en, this message translates to:
  /// **'Download Model'**
  String get downloadModel;

  /// Warning about debug mode performance
  ///
  /// In en, this message translates to:
  /// **'Performance reduced 5-10x. Use Release mode.'**
  String get performanceReduced;

  /// No description provided for @hostRequired.
  ///
  /// In en, this message translates to:
  /// **'Host is required'**
  String get hostRequired;

  /// Message when user already has best plan
  ///
  /// In en, this message translates to:
  /// **'You already have the best value plan. No changes needed.'**
  String get alreadyBestValuePlan;

  /// Status when preparing model
  ///
  /// In en, this message translates to:
  /// **'Preparing {model}…'**
  String preparingModel(String model);

  /// Option to share transcript
  ///
  /// In en, this message translates to:
  /// **'Send Transcript'**
  String get sendTranscript;

  /// Help dialog title
  ///
  /// In en, this message translates to:
  /// **'How it works?'**
  String get howItWorksTitle;

  /// Tooltip and sheet title for filtering conversations by who spoke (a person, not a loudspeaker)
  ///
  /// In en, this message translates to:
  /// **'Filter by speaker'**
  String get filterBySpeaker;

  /// Success message after app submission
  ///
  /// In en, this message translates to:
  /// **'App submitted successfully 🚀'**
  String get addAppSubmittedSuccess;

  /// No description provided for @olderIphoneModelDetected.
  ///
  /// In en, this message translates to:
  /// **'Detected model: {model} (older than iPhone XS). On-device recognition may be slower.'**
  String olderIphoneModelDetected(String model);

  /// Heading of the WhatsApp sheet
  ///
  /// In en, this message translates to:
  /// **'WhatsApp is coming'**
  String get chatAppsWhatsAppTitle;

  /// No description provided for @syncingDeveloperSettings.
  ///
  /// In en, this message translates to:
  /// **'Syncing Developer Settings…'**
  String get syncingDeveloperSettings;

  /// No description provided for @enterWifiPassword.
  ///
  /// In en, this message translates to:
  /// **'Enter WiFi password'**
  String get enterWifiPassword;

  /// Snackbar when toggling a memory's baseline flag fails
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t update this memory. Try again.'**
  String get failedToUpdateBaselineStatus;

  /// Discord community link
  ///
  /// In en, this message translates to:
  /// **'Join the community!'**
  String get joinCommunity;

  /// Help link title
  ///
  /// In en, this message translates to:
  /// **'Help or Inquiries?'**
  String get helpOrInquiries;

  /// Label for enable toggle setting
  ///
  /// In en, this message translates to:
  /// **'Enable'**
  String get enable;

  /// Toast after the device was forgotten
  ///
  /// In en, this message translates to:
  /// **'Device forgotten'**
  String get deviceForgottenMessage;

  /// Device Diagnostics footnote under the 7-day summary with lifetime counts
  ///
  /// In en, this message translates to:
  /// **'Since pairing: {drops} drops, {failed} failed connections.'**
  String diagnosticsSincePairingSummary(int drops, int failed);

  /// Sheet summary for a Confirmed person.
  ///
  /// In en, this message translates to:
  /// **'Omi recognizes {name}\'s voice, and you\'ve confirmed it.'**
  String confidenceSummaryConfirmed(String name);

  /// Notification body when migration starts
  ///
  /// In en, this message translates to:
  /// **'Migrating to {level} protection…'**
  String migratingToProtection(String level);

  /// Manage plan button
  ///
  /// In en, this message translates to:
  /// **'Manage Plan'**
  String get managePlan;

  /// Label for synced/processed recordings tab
  ///
  /// In en, this message translates to:
  /// **'Synced'**
  String get synced;

  /// Error toast when moving selected conversations into a folder fails
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t move the conversations'**
  String get failedToMoveConversations;

  /// March month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Mar'**
  String get monthMar;

  /// PM time indicator
  ///
  /// In en, this message translates to:
  /// **'PM'**
  String get timePM;

  /// No description provided for @debugLogsAutoDelete.
  ///
  /// In en, this message translates to:
  /// **'Auto-deletes after 3 days.'**
  String get debugLogsAutoDelete;

  /// No description provided for @linkedIn.
  ///
  /// In en, this message translates to:
  /// **'LinkedIn'**
  String get linkedIn;

  /// One sentence under speakerLabelVoiceStatus; name is the tagged person
  ///
  /// In en, this message translates to:
  /// **'{state, select, learned{Omi will recognize {name} next time.} pending{This takes a few seconds.} disabled{Turn on saving voices in Settings so Omi can recognize {name}.} other{Omi needs more clear speech from {name} and will keep trying.}}'**
  String speakerLabelVoiceDetail(String state, String name);

  /// Error message for unexpected error during sign-in
  ///
  /// In en, this message translates to:
  /// **'Unexpected error signing in, please try again'**
  String get authUnexpectedError;

  /// No description provided for @disconnectAppMessage.
  ///
  /// In en, this message translates to:
  /// **'You can reconnect {appName} anytime.'**
  String disconnectAppMessage(String appName);

  /// Small note on the live card while the phone records instead of the pendant.
  ///
  /// In en, this message translates to:
  /// **'Pendant paused · resumes when you finish'**
  String get pendantPausedResumesWhenYouFinish;

  /// Device diagnostics support upload
  ///
  /// In en, this message translates to:
  /// **'Send to support'**
  String get sendToSupport;

  /// No description provided for @fairUseBudgetExhausted.
  ///
  /// In en, this message translates to:
  /// **'Daily transcription limit reached'**
  String get fairUseBudgetExhausted;

  /// Evidence row: automatic matches the user confirmed by hand.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{You confirmed 1 automatic label} other{You confirmed {count} automatic labels}}'**
  String evidenceAutoConfirmed(int count);

  /// OmiGlass OTA status
  ///
  /// In en, this message translates to:
  /// **'Connecting to Wi-Fi…'**
  String get otaWifiConnecting;

  /// Filter chip label for star rating
  ///
  /// In en, this message translates to:
  /// **'{count} Star'**
  String starFilterLabel(int count);

  /// Action to disconnect device
  ///
  /// In en, this message translates to:
  /// **'Disconnect Device'**
  String get disconnectDevice;

  /// Label for number of app installs
  ///
  /// In en, this message translates to:
  /// **'Installs'**
  String get installsCount;

  /// Live page title: recording status followed by the capture source, e.g. 'Listening · Pendant'.
  ///
  /// In en, this message translates to:
  /// **'{status} · {source}'**
  String captureStatusWithSource(String status, String source);

  /// Pairing title for Omi Glass
  ///
  /// In en, this message translates to:
  /// **'Turn On Omi Glass'**
  String get pairingTitleOmiGlass;

  /// Button to set payment method as active
  ///
  /// In en, this message translates to:
  /// **'Set Active'**
  String get setActive;

  /// No description provided for @showShortConversations.
  ///
  /// In en, this message translates to:
  /// **'Show Short Conversations'**
  String get showShortConversations;

  /// Button (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Not Sure'**
  String get reviewNotSure;

  /// Error when camera access fails
  ///
  /// In en, this message translates to:
  /// **'Error accessing camera: {error}'**
  String msgCameraAccessError(String error);

  /// iOS home screen quick action: opens chat page
  ///
  /// In en, this message translates to:
  /// **'Ask Omi Anything'**
  String get quickActionAskOmi;

  /// Run summary when the pass hit its time limit.
  ///
  /// In en, this message translates to:
  /// **'Stopped at its time limit'**
  String get dreamReportTimedOut;

  /// No description provided for @chooseYourLanguage.
  ///
  /// In en, this message translates to:
  /// **'Choose your language'**
  String get chooseYourLanguage;

  /// Shown when the device firmware revision cannot be read over BLE, so an OTA update offer would be unreliable.
  ///
  /// In en, this message translates to:
  /// **'Unable to determine current firmware version'**
  String get unableToDetermineFirmwareVersion;

  /// Validation error when memories capability selected but no prompt entered
  ///
  /// In en, this message translates to:
  /// **'Please enter a conversation prompt for your app'**
  String get addAppEnterConversationPrompt;

  /// Label for read API key scope
  ///
  /// In en, this message translates to:
  /// **'Read'**
  String get readScope;

  /// No description provided for @selectALanguage.
  ///
  /// In en, this message translates to:
  /// **'Select a language'**
  String get selectALanguage;

  /// No description provided for @otherTemplates.
  ///
  /// In en, this message translates to:
  /// **'Other Templates'**
  String get otherTemplates;

  /// Third speech profile topic prompt; must match the backend onboarding question
  ///
  /// In en, this message translates to:
  /// **'What is your long-term goal?'**
  String get speechProfileTopicGoal;

  /// Title for the Bluetooth microphone picker used to connect Ray-Ban Meta glasses
  ///
  /// In en, this message translates to:
  /// **'Choose your Ray-Ban Meta microphone'**
  String get rayBanMetaMicPickerTitle;

  /// Email subject when sharing conversation notes with meeting attendees
  ///
  /// In en, this message translates to:
  /// **'Notes: {title}'**
  String meetingNotesSubject(String title);

  /// Feedback title when cancel reason is missing features
  ///
  /// In en, this message translates to:
  /// **'What features are you missing?'**
  String get feedbackTitleMissingFeatures;

  /// Status when model is downloaded
  ///
  /// In en, this message translates to:
  /// **'Model Ready'**
  String get modelReady;

  /// Date format showing today with time
  ///
  /// In en, this message translates to:
  /// **'Today at {time}'**
  String todayAtTime(String time);

  /// Primary destructive action label
  ///
  /// In en, this message translates to:
  /// **'Delete Account Permanently'**
  String get deleteAccountPermanently;

  /// Button to update Stripe details
  ///
  /// In en, this message translates to:
  /// **'Update Stripe Details'**
  String get updateStripeDetails;

  /// Voice response mode: only when headphones connected
  ///
  /// In en, this message translates to:
  /// **'Headphones only'**
  String get voiceResponseHeadphonesOnly;

  /// Tutorial step 4 double-tap option title — end the current conversation
  ///
  /// In en, this message translates to:
  /// **'End Conversation'**
  String get deviceOnboardingEndConversation;

  /// Snackbar message when opening an app
  ///
  /// In en, this message translates to:
  /// **'Opening {appName}…'**
  String openingApp(String appName);

  /// Dialog description for public app submission
  ///
  /// In en, this message translates to:
  /// **'Your app will be reviewed and made public. You can start using it immediately, even during the review!'**
  String get submitAppPublicDescription;

  /// No description provided for @connectToAppTitle.
  ///
  /// In en, this message translates to:
  /// **'Connect to {appName}'**
  String connectToAppTitle(String appName);

  /// No description provided for @timeout10MinutesDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 10 minutes of silence'**
  String get timeout10MinutesDesc;

  /// No description provided for @googleCalendar.
  ///
  /// In en, this message translates to:
  /// **'Google Calendar'**
  String get googleCalendar;

  /// Recording status: initializing
  ///
  /// In en, this message translates to:
  /// **'Initializing…'**
  String get initializing;

  /// Empty chat state message
  ///
  /// In en, this message translates to:
  /// **'No messages yet!\nWhy don\'t you start a conversation?'**
  String get noMessagesYet;

  /// Shown in the chat apps drawer when loading installed chat apps fails
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load chat apps. Please try again.'**
  String get chatAppsLoadFailed;

  /// Category label for tasks due later
  ///
  /// In en, this message translates to:
  /// **'Later'**
  String get tasksLater;

  /// No description provided for @speakerLabelUnknown.
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get speakerLabelUnknown;

  /// The app title displayed in various places
  ///
  /// In en, this message translates to:
  /// **'Omi'**
  String get appTitle;

  /// Info about iOS native speech
  ///
  /// In en, this message translates to:
  /// **'Your device\'s native speech engine will be used. No model download required.'**
  String get noModelDownloadRequired;

  /// Error message when authentication fails
  ///
  /// In en, this message translates to:
  /// **'Authentication failed. Please try again.'**
  String get authenticationFailed;

  /// No description provided for @defaultRepoSaved.
  ///
  /// In en, this message translates to:
  /// **'Default repository saved'**
  String get defaultRepoSaved;

  /// Error when thumbnail selection fails
  ///
  /// In en, this message translates to:
  /// **'Error selecting thumbnail: {error}'**
  String addAppErrorSelectingThumbnail(String error);

  /// Confirmation title before splitting a recording out of a grouped conversation
  ///
  /// In en, this message translates to:
  /// **'Separate this recording?'**
  String get captureRecordingSeparateTitle;

  /// Back button text
  ///
  /// In en, this message translates to:
  /// **'Back'**
  String get back;

  /// No description provided for @preparingAudio.
  ///
  /// In en, this message translates to:
  /// **'Preparing Audio'**
  String get preparingAudio;

  /// Empty state text for auto category
  ///
  /// In en, this message translates to:
  /// **'No auto-extracted memories yet'**
  String get noAutoMemories;

  /// Success message after completing a task
  ///
  /// In en, this message translates to:
  /// **'All done!'**
  String get allDone;

  /// Loading text while reading memories
  ///
  /// In en, this message translates to:
  /// **'Reading your memories…'**
  String get msgReadingMemories;

  /// Plan card row: this tier includes the desktop app
  ///
  /// In en, this message translates to:
  /// **'Works on Desktop'**
  String get worksOnDesktop;

  /// No description provided for @displayOptions.
  ///
  /// In en, this message translates to:
  /// **'Display Options'**
  String get displayOptions;

  /// Button label to install an app
  ///
  /// In en, this message translates to:
  /// **'Install App'**
  String get installApp;

  /// Label shown on the Record button while a recording is in progress
  ///
  /// In en, this message translates to:
  /// **'Stop'**
  String get stop;

  /// Title for the permissions request page
  ///
  /// In en, this message translates to:
  /// **'Grant Permissions'**
  String get grantPermissions;

  /// Preposition for time when conversation has no start time
  ///
  /// In en, this message translates to:
  /// **'at'**
  String get at;

  /// Empty state subtitle when not connected
  ///
  /// In en, this message translates to:
  /// **'Please check your internet connection'**
  String get checkInternetConnection;

  /// Section header for action items
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get actionItems;

  /// Day page navigation: go to the day after
  ///
  /// In en, this message translates to:
  /// **'Next day'**
  String get nextDay;

  /// No description provided for @syncStatusFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed — tap Retry'**
  String get syncStatusFailed;

  /// WiFi sync settings - saveCredentials
  ///
  /// In en, this message translates to:
  /// **'Save Credentials'**
  String get saveCredentials;

  /// Section header for people heard recently
  ///
  /// In en, this message translates to:
  /// **'Recent'**
  String get peopleRecent;

  /// No description provided for @bringYourOwn.
  ///
  /// In en, this message translates to:
  /// **'Bring your own'**
  String get bringYourOwn;

  /// Cancel consequence
  ///
  /// In en, this message translates to:
  /// **'7x more battery usage (on-device processing)'**
  String get cancelConsequenceBattery;

  /// Label of the copy-message action on an AI chat message
  ///
  /// In en, this message translates to:
  /// **'Copy Message'**
  String get copyMessage;

  /// Info about annual subscription starting
  ///
  /// In en, this message translates to:
  /// **'Your 12-month annual subscription will start automatically after the charge'**
  String get annualSubscriptionStarts;

  /// Menu item to delete imported data
  ///
  /// In en, this message translates to:
  /// **'Delete Imported Data'**
  String get deleteImportedData;

  /// No description provided for @chatLimitReachedUpgrade.
  ///
  /// In en, this message translates to:
  /// **'Chat limit reached. Upgrade for more messages.'**
  String get chatLimitReachedUpgrade;

  /// Section header for changelog
  ///
  /// In en, this message translates to:
  /// **'What\'s New'**
  String get whatsNew;

  /// Title for the Omi Training page/section
  ///
  /// In en, this message translates to:
  /// **'Omi Training'**
  String get omiTraining;

  /// Badge for buddies in Wrapped
  ///
  /// In en, this message translates to:
  /// **'My Buddies'**
  String get wrappedMyBuddies;

  /// Button that dismisses the discard-recording dialog and continues
  ///
  /// In en, this message translates to:
  /// **'Keep Recording'**
  String get keepRecording;

  /// Badge on the calendar event that best matches the conversation time
  ///
  /// In en, this message translates to:
  /// **'Suggested'**
  String get suggestedEvent;

  /// Name field label
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get name;

  /// No description provided for @screenRecordingDescription.
  ///
  /// In en, this message translates to:
  /// **'Omi needs screen recording permission to capture system audio from your browser-based meetings.'**
  String get screenRecordingDescription;

  /// No description provided for @improveConnectionTitle.
  ///
  /// In en, this message translates to:
  /// **'Improve Connection'**
  String get improveConnectionTitle;

  /// Reassurance line on the manual sync status card during the cloud-processing phase, so users do not think sync is stuck when there is no visible progress.
  ///
  /// In en, this message translates to:
  /// **'This continues in the background — you can leave this screen.'**
  String get syncProcessingBackgroundHint;

  /// Badge text for top days summary
  ///
  /// In en, this message translates to:
  /// **'Your Top Days'**
  String get wrappedYourTopDaysBadge;

  /// Empty state title on the People page
  ///
  /// In en, this message translates to:
  /// **'No People Yet'**
  String get noPeopleYet;

  /// Daily summary settings - summaryGeneratedForDate
  ///
  /// In en, this message translates to:
  /// **'Summary generated for {date}'**
  String summaryGeneratedForDate(String date);

  /// Placeholder text for search field in conversation detail page
  ///
  /// In en, this message translates to:
  /// **'Search transcript or summary'**
  String get searchTranscriptOrSummary;

  /// Title of the sheet that shows one memory read-only
  ///
  /// In en, this message translates to:
  /// **'Memory'**
  String get memoryDetailsTitle;

  /// Title for chat personality section
  ///
  /// In en, this message translates to:
  /// **'Chat Personality'**
  String get chatPersonality;

  /// Text shown when user drags the swipe button
  ///
  /// In en, this message translates to:
  /// **'Release'**
  String get release;

  /// No description provided for @removeVocabularyWord.
  ///
  /// In en, this message translates to:
  /// **'Remove {word}'**
  String removeVocabularyWord(String word);

  /// Onboarding step title for language selection
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get onboardingLanguage;

  /// Subtitle on win card with emoji
  ///
  /// In en, this message translates to:
  /// **'You did it! 🎉'**
  String get wrappedYouDidItEmoji;

  /// No description provided for @syncInProgress.
  ///
  /// In en, this message translates to:
  /// **'Sync in progress'**
  String get syncInProgress;

  /// Badge for obsessions in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t Stop Talking About'**
  String get wrappedCouldntStopTalkingAbout;

  /// No description provided for @chooseSummarizationApp.
  ///
  /// In en, this message translates to:
  /// **'Choose Summarization App'**
  String get chooseSummarizationApp;

  /// Estimated time remaining label
  ///
  /// In en, this message translates to:
  /// **'ETA: {time}'**
  String etaLabel(String time);

  /// Explanation of what happens when making public
  ///
  /// In en, this message translates to:
  /// **'If you make the {item} public, it can be used by everyone'**
  String makeItemPublicExplanation(String item);

  /// Phone calls upsell feature 2
  ///
  /// In en, this message translates to:
  /// **'Automatic call summaries and tasks'**
  String get phoneCallsUpsellFeature2;

  /// Intro line above the list of free-tier limitations
  ///
  /// In en, this message translates to:
  /// **'Omi is free, but freemium has limits that affect your experience:'**
  String get freemiumLimitsIntro;

  /// Label for name input field
  ///
  /// In en, this message translates to:
  /// **'Name'**
  String get nameLabel;

  /// No description provided for @shortConversationThresholdSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Conversations shorter than this will be hidden unless enabled above'**
  String get shortConversationThresholdSubtitle;

  /// Home live capture card, line 2 after the timer when the OS or another app (a call, another audio app) took the microphone and capture is paused.
  ///
  /// In en, this message translates to:
  /// **'Mic in use by another app'**
  String get captureMicInUseElsewhere;

  /// App selection modal title
  ///
  /// In en, this message translates to:
  /// **'Select Chat Assistant'**
  String get selectChatAssistant;

  /// Title when transfer is needed
  ///
  /// In en, this message translates to:
  /// **'Transfer Required'**
  String get transferRequired;

  /// No description provided for @unlimitedChatThisMonth.
  ///
  /// In en, this message translates to:
  /// **'Unlimited chat messages this month'**
  String get unlimitedChatThisMonth;

  /// Warning shown in Background Mode sheet when no device with a native BLE audio route is connected
  ///
  /// In en, this message translates to:
  /// **'Background Mode is not available because no compatible device is connected. Connect an Omi, OpenGlass, or Friend Pendant device to use this feature.'**
  String get backgroundModeUnavailable;

  /// No description provided for @importConfiguration.
  ///
  /// In en, this message translates to:
  /// **'Import Configuration'**
  String get importConfiguration;

  /// First trade-off bullet point for E2EE
  ///
  /// In en, this message translates to:
  /// **'• Some features like external app integrations may be disabled.'**
  String get e2eeTradeoff1;

  /// Heading when the one-time code expired
  ///
  /// In en, this message translates to:
  /// **'This code expired'**
  String get chatAppsCodeExpiredTitle;

  /// No description provided for @responseSchema.
  ///
  /// In en, this message translates to:
  /// **'Response Schema'**
  String get responseSchema;

  /// Badge for best moments in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Best Moments'**
  String get wrappedBestMoments;

  /// Empty state for app access
  ///
  /// In en, this message translates to:
  /// **'No installed apps have external access to your data.'**
  String get noAppsExternalAccess;

  /// Status when model is ready
  ///
  /// In en, this message translates to:
  /// **'Model Ready ({model})'**
  String modelReadyWithName(String model);

  /// Explains that an app was auto-disabled because its webhook endpoint kept failing
  ///
  /// In en, this message translates to:
  /// **'Its endpoint failed for 72 hours in a row, so deliveries were stopped.'**
  String get appDisabledWebhookFailures;

  /// How many conversations a profile appears in
  ///
  /// In en, this message translates to:
  /// **'Conversations: {count}'**
  String reviewConversationCount(int count);

  /// Error state
  ///
  /// In en, this message translates to:
  /// **'Couldn’t load recent changes.'**
  String get reviewChangesLoadFailed;

  /// Chip that opens the source conversation when it has no title
  ///
  /// In en, this message translates to:
  /// **'Conversation'**
  String get reviewOpenConversation;

  /// No description provided for @voiceRecordingFound.
  ///
  /// In en, this message translates to:
  /// **'Recording found'**
  String get voiceRecordingFound;

  /// A compact duration in the past, e.g. '2h 5m ago'
  ///
  /// In en, this message translates to:
  /// **'{duration} ago'**
  String durationAgo(String duration);

  /// Onboarding step description for sign in
  ///
  /// In en, this message translates to:
  /// **'Welcome to Omi'**
  String get onboardingWelcomeToOmi;

  /// Dialog title
  ///
  /// In en, this message translates to:
  /// **'Delete Task'**
  String get deleteActionItemConfirmTitle;

  /// Header for billing information section
  ///
  /// In en, this message translates to:
  /// **'Important Billing Information:'**
  String get importantBillingInfo;

  /// Pending tab label for sync page
  ///
  /// In en, this message translates to:
  /// **'Pending'**
  String get pending;

  /// Store rating pre-prompt title shown on the onboarding setup page
  ///
  /// In en, this message translates to:
  /// **'Are you enjoying Omi?'**
  String get onboardingRatingPromptTitle;

  /// Button text to save PayPal details
  ///
  /// In en, this message translates to:
  /// **'Save PayPal Details'**
  String get savePayPalDetails;

  /// States the last error recorded from the app's endpoint before it was disabled
  ///
  /// In en, this message translates to:
  /// **'Last error: {error}.'**
  String appDisabledLastError(String error);

  /// Button text confirming user has installed and opened the app
  ///
  /// In en, this message translates to:
  /// **'I\'ve Installed & Opened the App'**
  String get iveInstalledAndOpenedTheApp;

  /// Placeholder text for the price input field showing a sample price format
  ///
  /// In en, this message translates to:
  /// **'0.00'**
  String get pricePlaceholder;

  /// No description provided for @triggerTranscriptProcessed.
  ///
  /// In en, this message translates to:
  /// **'Transcript Processed'**
  String get triggerTranscriptProcessed;

  /// Daily summary detail - decisions
  ///
  /// In en, this message translates to:
  /// **'Decisions'**
  String get decisions;

  /// Transcript tab when the server marked the conversation as failed; shown above Try Again.
  ///
  /// In en, this message translates to:
  /// **'This conversation couldn\'t be processed.'**
  String get conversationProcessingFailedMessage;

  /// Continue button text
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get continueText;

  /// Button text for Google Sign In
  ///
  /// In en, this message translates to:
  /// **'Sign in with Google'**
  String get signInWithGoogle;

  /// No description provided for @firmwareFlashTarget.
  ///
  /// In en, this message translates to:
  /// **'Device: {deviceName}'**
  String firmwareFlashTarget(String deviceName);

  /// No description provided for @deleteYourAccountAndAllData.
  ///
  /// In en, this message translates to:
  /// **'Delete your account and all data'**
  String get deleteYourAccountAndAllData;

  /// No description provided for @provider.
  ///
  /// In en, this message translates to:
  /// **'Provider'**
  String get provider;

  /// People section title
  ///
  /// In en, this message translates to:
  /// **'People'**
  String get people;

  /// No description provided for @perMonth.
  ///
  /// In en, this message translates to:
  /// **'/ Month'**
  String get perMonth;

  /// February month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Feb'**
  String get monthFeb;

  /// Abbreviation for Friday
  ///
  /// In en, this message translates to:
  /// **'Fri'**
  String get fridayAbbr;

  /// Feedback confirmation message
  ///
  /// In en, this message translates to:
  /// **'Thank you for your feedback!'**
  String get thankYouForFeedback;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Best year'**
  String get usageBestYear;

  /// Generic validation error for incomplete form
  ///
  /// In en, this message translates to:
  /// **'Please fill in all the required fields correctly'**
  String get addAppFillRequiredFields;

  /// Description of the Off voice response mode
  ///
  /// In en, this message translates to:
  /// **'Answers stay on screen. Nothing is spoken.'**
  String get deviceOnboardingVoiceReplyOffDescription;

  /// No description provided for @logs.
  ///
  /// In en, this message translates to:
  /// **'Logs'**
  String get logs;

  /// No description provided for @exportConversations.
  ///
  /// In en, this message translates to:
  /// **'Export Conversations'**
  String get exportConversations;

  /// Status after the user marks a learned memory wrong; the memory is hidden.
  ///
  /// In en, this message translates to:
  /// **'Removed from your memories.'**
  String get memoryReviewDropped;

  /// No description provided for @appearanceLight.
  ///
  /// In en, this message translates to:
  /// **'Light'**
  String get appearanceLight;

  /// Label for money earned from app
  ///
  /// In en, this message translates to:
  /// **'Money Earned'**
  String get moneyEarned;

  /// Section title for permissions and triggers
  ///
  /// In en, this message translates to:
  /// **'Permissions & Triggers'**
  String get permissionsAndTriggers;

  /// Dialog title when leaving the voice-sample recording mid-recording
  ///
  /// In en, this message translates to:
  /// **'Discard Recording?'**
  String get discardRecordingTitle;

  /// Label under minutes count
  ///
  /// In en, this message translates to:
  /// **'minutes'**
  String get wrappedMinutesLabel;

  /// Toast after restoring an ignored voice.
  ///
  /// In en, this message translates to:
  /// **'Omi may ask about this voice again'**
  String get voiceRestoredToast;

  /// Title for location access permission
  ///
  /// In en, this message translates to:
  /// **'Location access'**
  String get locationAccess;

  /// Action to delete all memories
  ///
  /// In en, this message translates to:
  /// **'Delete All Memories'**
  String get deleteAllMemories;

  /// Delete account page title
  ///
  /// In en, this message translates to:
  /// **'Delete Account'**
  String get deleteAccountTitle;

  /// File option: select file
  ///
  /// In en, this message translates to:
  /// **'Select a File'**
  String get selectFile;

  /// No description provided for @answerTheCallFrom.
  ///
  /// In en, this message translates to:
  /// **'Answer the call from'**
  String get answerTheCallFrom;

  /// Dialog title for unpair device confirmation
  ///
  /// In en, this message translates to:
  /// **'Unpair Device'**
  String get unpairDeviceDialogTitle;

  /// Caption on a task that was exported to another app, e.g. 'Exported to Todoist'
  ///
  /// In en, this message translates to:
  /// **'Exported to {platform}'**
  String exportedToPlatform(String platform);

  /// Offline Sync status card: overall device-download percent. Not shown on recording rows.
  ///
  /// In en, this message translates to:
  /// **'{percent}%'**
  String syncCardDownloadPercent(int percent);

  /// Title of the voice answer preview card while audio is playing
  ///
  /// In en, this message translates to:
  /// **'Playing your last answer...'**
  String get deviceOnboardingVoiceReplyPreviewPlaying;

  /// Label indicating content originated from SD card
  ///
  /// In en, this message translates to:
  /// **'From SD'**
  String get fromSd;

  /// Instructions for taking a good speech sample
  ///
  /// In en, this message translates to:
  /// **'1. Make sure you are in a quiet place.\n2. Speak clearly and naturally.\n3. Make sure your device is in its natural position, on your neck.\n\nOnce it\'s created, you can always improve it or do it again.'**
  String get goodSampleInstructions;

  /// Guided voice introduction copy. English source fallback pending translation review.
  ///
  /// In en, this message translates to:
  /// **'{part, select, title{Let Omi get to know you} intro{Finish four short sentences out loud. This helps Omi recognize your voice and remember what matters to you. Share only what you want.} hint{Say the whole sentence and finish it in your own words.} name{My name is ___, and I spend most of my time ___.} work{Right now, I am working on ___.} enjoy{Outside of that, I really enjoy ___.} food{My favorite food is ___.} remember{Something I would like help remembering is ___.} day{A good day for me includes ___.} another{Try Another Prompt} start{Start Speaking} skipPrompt{Skip Question} captured{Voice sample captured} silence{Take your time. Speak toward your phone microphone.} audio{Audio detected} review{Here is what I heard} reviewHint{Uncheck anything you don\'t want saved.} saveVoice{Save Voice Profile} savingVoice{Saving your voice profile…} savedVoice{Voice profile saved} voiceLater{Set Up My Voice Later} keep{Save Selected Answers} without{Continue Without Saving Answers} savedMemories{Your memories are saved} short{We need a little more audio. Add one more sentence; your earlier answers are safe.} addSample{Add Another Sentence} uploadError{Your voice profile could not be saved. Retry with the same recording, or set it up later.} memoryError{Some answers could not be saved. Saved items are safe; retry to save the rest.} transcriptionError{We could not transcribe that answer. Try again, keep speaking, or skip this question.} noMemories{You can tell Omi more about yourself whenever you like.} voiceOnlyHint{You can skip any personal prompt and talk about something else.} goalPrompt{Right now my number one goal is to ___.} savedGoal{Your goal is saved} goalError{Your goal could not be saved. Retry to save the same goal without duplicating it. Any memories already saved are safe.} goalLong{Shorten your goal to 500 characters or fewer, then try again.} voiceUnavailable{Voice setup is temporarily unavailable. Saved answers are safe. Retry, or continue and set up your voice later.} saveFinish{Save and Finish} retryRemaining{Retry Remaining} saveHint{Saves your voice profile and checked answers.} savedAll{Your introduction is saved.} continueSaved{Continue With What Is Saved} reviewAnswers{Review Answers} originalGoal{Use Original Wording} savingAnswers{Saving your answers…} other{}}'**
  String voiceIntroduction(String part);

  /// Hint explaining how to star conversations
  ///
  /// In en, this message translates to:
  /// **'To star a conversation, open it and tap the star icon in the header.'**
  String get starConversationHint;

  /// Pairing title for Omi DevKit
  ///
  /// In en, this message translates to:
  /// **'Put Omi DevKit in Pairing Mode'**
  String get pairingTitleOmiDevkit;

  /// No description provided for @sttPrimaryLanguageUnsupported.
  ///
  /// In en, this message translates to:
  /// **'{language} isn\'t supported by this provider, so it uses {fallback}.'**
  String sttPrimaryLanguageUnsupported(String language, String fallback);

  /// Description of premium minutes quota
  ///
  /// In en, this message translates to:
  /// **'300 premium minutes a month. Choose On Device for unlimited free transcription. '**
  String get premiumMinutesMonth;

  /// Description for battery requirement during firmware update
  ///
  /// In en, this message translates to:
  /// **'Ensure your device has 15% battery.'**
  String get firmwareEnsureBattery;

  /// Input hint
  ///
  /// In en, this message translates to:
  /// **'What needs to be done?'**
  String get actionItemDescriptionHint;

  /// Label for your score button
  ///
  /// In en, this message translates to:
  /// **'Your score'**
  String get yourScore;

  /// No description provided for @failedToStartAuth.
  ///
  /// In en, this message translates to:
  /// **'Failed to start {appName} authentication'**
  String failedToStartAuth(String appName);

  /// No description provided for @actionReadTasks.
  ///
  /// In en, this message translates to:
  /// **'Read tasks'**
  String get actionReadTasks;

  /// Button label to dismiss cancel dialog and continue syncing
  ///
  /// In en, this message translates to:
  /// **'Keep Syncing'**
  String get keepSyncing;

  /// Label for overdue tasks
  ///
  /// In en, this message translates to:
  /// **'Overdue'**
  String get overdue;

  /// Error when the server refuses to start linking
  ///
  /// In en, this message translates to:
  /// **'Chat apps aren\'t available for your account yet.'**
  String get chatAppsProblemUnavailable;

  /// Hint to start sync
  ///
  /// In en, this message translates to:
  /// **'Tap Sync to start'**
  String get tapSyncToStart;

  /// Message when Done list is empty
  ///
  /// In en, this message translates to:
  /// **'No completed items yet'**
  String get emptyDoneMessage;

  /// One-time hint after the first phone-mic recording
  ///
  /// In en, this message translates to:
  /// **'Tip: tap the arrow on the record button to record a phone call.'**
  String get recordOptionsTip;

  /// Question about profession
  ///
  /// In en, this message translates to:
  /// **'1. What do you do?'**
  String get setupQuestionProfession;

  /// Device information section header
  ///
  /// In en, this message translates to:
  /// **'Device Information'**
  String get deviceInfoSection;

  /// No description provided for @teachOmiYourVoice.
  ///
  /// In en, this message translates to:
  /// **'Teach Omi your voice'**
  String get teachOmiYourVoice;

  /// Button text in empty state
  ///
  /// In en, this message translates to:
  /// **'Add your first memory'**
  String get addYourFirstMemory;

  /// Label for price
  ///
  /// In en, this message translates to:
  /// **'PRICE'**
  String get priceLabel;

  /// High preset
  ///
  /// In en, this message translates to:
  /// **'High'**
  String get high;

  /// Estimated model size
  ///
  /// In en, this message translates to:
  /// **'Estimated Size: ~{size} MB'**
  String estimatedSizeWithValue(String size);

  /// Banner title and menu subtitle: how many people have Unverified confidence.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 person Omi is unsure about} other{{count} people Omi is unsure about}}'**
  String cleanUpUnsureCount(int count);

  /// Action to make all memories private
  ///
  /// In en, this message translates to:
  /// **'Make All Memories Private'**
  String get makeAllMemoriesPrivate;

  /// No description provided for @raybanMetaWaitingForMetaAI.
  ///
  /// In en, this message translates to:
  /// **'Finish connecting in the Meta AI app, then come back here.'**
  String get raybanMetaWaitingForMetaAI;

  /// No description provided for @revokeAuthorization.
  ///
  /// In en, this message translates to:
  /// **'Revoke Authorization'**
  String get revokeAuthorization;

  /// Section header in the confidence sheet: what would raise this person to Confirmed (Title Case).
  ///
  /// In en, this message translates to:
  /// **'To Reach Confirmed'**
  String get confidenceToReachConfirmed;

  /// Status card line when uploads are paused due to a fair-use/rate-limit (HTTP 429) cooldown. Reassures the user this is not an error and will resume on its own.
  ///
  /// In en, this message translates to:
  /// **'Fair-use limit reached — syncing will resume automatically'**
  String get syncCardRateLimited;

  /// Accessibility label of the stop button for a voice clip
  ///
  /// In en, this message translates to:
  /// **'Stop clip'**
  String get reviewStopClip;

  /// Heading of a card listing what Omi can do in chat apps
  ///
  /// In en, this message translates to:
  /// **'What Omi does in chat apps'**
  String get chatAppsWhatOmiDoes;

  /// Button that resumes a paused recording.
  ///
  /// In en, this message translates to:
  /// **'Resume'**
  String get resume;

  /// No description provided for @defaultSpace.
  ///
  /// In en, this message translates to:
  /// **'Default Space'**
  String get defaultSpace;

  /// Dialog title when multiple speakers are detected in speech profile recording
  ///
  /// In en, this message translates to:
  /// **'Multiple speakers detected'**
  String get multipleSpeakersDetected;

  /// Evidence row: automatic matches to this person that the user corrected to someone else.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{You changed 1 automatic label to someone else} other{You changed {count} automatic labels to someone else}}'**
  String evidenceAutoCorrected(int count);

  /// How close a voice is to a person: somewhat close.
  ///
  /// In en, this message translates to:
  /// **'Possible match'**
  String get voiceMatchPossible;

  /// Checkbox validation error
  ///
  /// In en, this message translates to:
  /// **'Check the box to confirm you understand that deleting your account is permanent and irreversible.'**
  String get checkBoxToConfirm;

  /// Description for response template selector
  ///
  /// In en, this message translates to:
  /// **'Quickly populate with a known providers response format'**
  String get quicklyPopulateResponse;

  /// July month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Jul'**
  String get monthJul;

  /// No description provided for @failedToInitializeCallService.
  ///
  /// In en, this message translates to:
  /// **'Failed to initialize call service'**
  String get failedToInitializeCallService;

  /// Snackbar action label that opens the Task Integrations settings page
  ///
  /// In en, this message translates to:
  /// **'Connect'**
  String get connectAction;

  /// Toast shown after an on-device model is deleted
  ///
  /// In en, this message translates to:
  /// **'Model deleted'**
  String get onDeviceModelDeleted;

  /// Mic gain description: Neutral
  ///
  /// In en, this message translates to:
  /// **'Neutral - balanced recording'**
  String get micGainDescNeutral;

  /// Shown above the chat composer while the phone is offline; Send is disabled
  ///
  /// In en, this message translates to:
  /// **'You\'re offline. Reconnect to send messages.'**
  String get chatOfflineHint;

  /// Instructions to grant location permission
  ///
  /// In en, this message translates to:
  /// **'Please grant location permission in Settings > Privacy & Security > Location Services'**
  String get onboardingLocationGrantInSettings;

  /// Error message for invalid setup instructions URL
  ///
  /// In en, this message translates to:
  /// **'Invalid setup instructions URL'**
  String get invalidSetupInstructionsUrl;

  /// Error when camera permission is denied
  ///
  /// In en, this message translates to:
  /// **'Camera permission denied. Please allow access to camera'**
  String get msgCameraPermissionDenied;

  /// Consent dialog title
  ///
  /// In en, this message translates to:
  /// **'Data & Privacy'**
  String get dataAndPrivacy;

  /// Dialog title for incompatible device
  ///
  /// In en, this message translates to:
  /// **'Device Not Compatible'**
  String get deviceNotCompatible;

  /// Pairing description for Apple Watch
  ///
  /// In en, this message translates to:
  /// **'Install and open the Omi app on your Apple Watch, then tap Connect in the app.'**
  String get pairingDescAppleWatch;

  /// First speech profile topic prompt; must match the backend onboarding question
  ///
  /// In en, this message translates to:
  /// **'Where do you live?'**
  String get speechProfileTopicLocation;

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Make All Memories Private'**
  String get makeAllPrivate;

  /// No description provided for @capabilityNotification.
  ///
  /// In en, this message translates to:
  /// **'Smart Notifications'**
  String get capabilityNotification;

  /// Home live capture card, line 2 after the timer (e.g. "0:14 · Audio saved, transcribes later"): recording continues on the phone and will be transcribed later.
  ///
  /// In en, this message translates to:
  /// **'Audio saved, transcribes later'**
  String get captureAudioSavedTranscribesLater;

  /// Badge for top phrases in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Top 5 Phrases'**
  String get wrappedTopPhrases;

  /// Capture-card subtitle shown while Transcribe Later capture is muted/paused
  ///
  /// In en, this message translates to:
  /// **'Paused — audio isn\'t being recorded'**
  String get transcribeLaterPaused;

  /// Tutorial step 3 title while waiting for the user to power the device back on
  ///
  /// In en, this message translates to:
  /// **'Turn On'**
  String get deviceOnboardingTurnOnTitle;

  /// Placeholder text for key name input
  ///
  /// In en, this message translates to:
  /// **'e.g., My App Integration'**
  String get keyNamePlaceholder;

  /// No description provided for @languageTitle.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get languageTitle;

  /// No description provided for @statusVerifiedLabel.
  ///
  /// In en, this message translates to:
  /// **'Verified'**
  String get statusVerifiedLabel;

  /// Storage location label for phone memory
  ///
  /// In en, this message translates to:
  /// **'Phone (Memory)'**
  String get storageLocationPhoneMemory;

  /// Label for current user in transcript
  ///
  /// In en, this message translates to:
  /// **'You'**
  String get you;

  /// Live-capture empty state on audio-only setups (no photo capture source)
  ///
  /// In en, this message translates to:
  /// **'Listening… a transcript will appear here.'**
  String get listeningTranscriptWillAppear;

  /// Ask suggestion
  ///
  /// In en, this message translates to:
  /// **'What did Omi notice?'**
  String get askSuggestNotice;

  /// Description for synced files in manage storage sheet
  ///
  /// In en, this message translates to:
  /// **'Conversations created'**
  String get safelyBackedUp;

  /// Hint text for folder name input field
  ///
  /// In en, this message translates to:
  /// **'Folder name'**
  String get folderName;

  /// No description provided for @categorySocialEntertainment.
  ///
  /// In en, this message translates to:
  /// **'Social & Entertainment'**
  String get categorySocialEntertainment;

  /// Title shown on the speech profile page when the user already has a speech profile set up
  ///
  /// In en, this message translates to:
  /// **'{name}\'s Speech Profile'**
  String speechProfileOwnerTitle(String name);

  /// Success message when review is added
  ///
  /// In en, this message translates to:
  /// **'Review added successfully 🚀'**
  String get reviewAddedSuccessfully;

  /// No description provided for @fairUseSpeechUsage.
  ///
  /// In en, this message translates to:
  /// **'Speech Usage'**
  String get fairUseSpeechUsage;

  /// No description provided for @visibilitySubtitle.
  ///
  /// In en, this message translates to:
  /// **'Control which conversations appear in your list'**
  String get visibilitySubtitle;

  /// Section title in summary collage (uppercase)
  ///
  /// In en, this message translates to:
  /// **'WIN'**
  String get wrappedWinLabelUpper;

  /// Compact duration in minutes and seconds
  ///
  /// In en, this message translates to:
  /// **'{mins}m {secs}s'**
  String timeCompactMinsAndSecs(int mins, int secs);

  /// Subtitle explaining phone calls feature on upsell sheet
  ///
  /// In en, this message translates to:
  /// **'Make calls through Omi and get real-time transcription, automatic summaries, and more. Available exclusively for Unlimited plan subscribers.'**
  String get phoneCallsUpsellSubtitle;

  /// Message shown after an expired authenticated session returns the user to sign-in
  ///
  /// In en, this message translates to:
  /// **'Session expired — sign in again.'**
  String get sessionExpiredSignInAgain;

  /// Row in the picker that creates a new person (Title Case, one-character ellipsis).
  ///
  /// In en, this message translates to:
  /// **'New Person…'**
  String get newPersonEllipsis;

  /// Share stats period: Today
  ///
  /// In en, this message translates to:
  /// **'Today, Omi has:'**
  String get sharePeriodToday;

  /// Info about premium minutes
  ///
  /// In en, this message translates to:
  /// **'300 premium minutes a month. Choose On Device for unlimited free transcription.'**
  String get premiumMinutesInfo;

  /// Status label when payment method is not connected
  ///
  /// In en, this message translates to:
  /// **'Not Connected'**
  String get notConnectedStatus;

  /// No description provided for @authorizeSavingRecordings.
  ///
  /// In en, this message translates to:
  /// **'Authorize Saving Recordings'**
  String get authorizeSavingRecordings;

  /// Shown while Omi prepares a chat reply, before it names a step
  ///
  /// In en, this message translates to:
  /// **'Thinking'**
  String get thinking;

  /// Unpair dialog title
  ///
  /// In en, this message translates to:
  /// **'Unpair Device'**
  String get unpairDialogTitle;

  /// No description provided for @batteryFullyChargedBody.
  ///
  /// In en, this message translates to:
  /// **'Your Omi device is fully charged. Feel free to unplug!'**
  String get batteryFullyChargedBody;

  /// Undo toast after saying an automatic label was wrong without naming anyone.
  ///
  /// In en, this message translates to:
  /// **'Label removed'**
  String get speakerTagPromptRejectedToast;

  /// Filter label for phone storage
  ///
  /// In en, this message translates to:
  /// **'Phone'**
  String get phone;

  /// Setting title
  ///
  /// In en, this message translates to:
  /// **'Voice notes'**
  String get chatAppsVoiceNotes;

  /// Tutorial step 3 status chip — device disconnected/off
  ///
  /// In en, this message translates to:
  /// **'Disconnected'**
  String get deviceOnboardingStatusDisconnected;

  /// Warning title for debug mode
  ///
  /// In en, this message translates to:
  /// **'Debug Mode Detected'**
  String get debugModeDetected;

  /// No description provided for @failedToSaveDefaultRepo.
  ///
  /// In en, this message translates to:
  /// **'Failed to save default repository'**
  String get failedToSaveDefaultRepo;

  /// Action menu entry to reveal completed tasks on the action items page
  ///
  /// In en, this message translates to:
  /// **'Show Completed'**
  String get showCompletedTasks;

  /// Used vs total on-device storage, e.g. 338 MB of 469 MB used
  ///
  /// In en, this message translates to:
  /// **'{used} of {total} used'**
  String deviceStorageUsedOfTotal(String used, String total);

  /// Message when there are unsynced recordings
  ///
  /// In en, this message translates to:
  /// **'You have recordings that aren\'t synced yet.'**
  String get recordingsNotSynced;

  /// Title for performance warning dialog
  ///
  /// In en, this message translates to:
  /// **'Performance Warning'**
  String get performanceWarning;

  /// Dialog description for private app submission
  ///
  /// In en, this message translates to:
  /// **'Your app will be reviewed and made available to you privately. You can start using it immediately, even during the review!'**
  String get submitAppPrivateDescription;

  /// Option to copy transcript to clipboard
  ///
  /// In en, this message translates to:
  /// **'Copy Transcript'**
  String get copyTranscript;

  /// Providing stat title
  ///
  /// In en, this message translates to:
  /// **'Providing'**
  String get providing;

  /// One-line hint under 'No Omi Found' on the find-device screen.
  ///
  /// In en, this message translates to:
  /// **'Turn it on and hold it near your phone.'**
  String get findDeviceNoneMessage;

  /// Intro text on wrapped generate screen before the year 2025
  ///
  /// In en, this message translates to:
  /// **'Let\'s hit rewind on your'**
  String get wrappedLetsHitRewind;

  /// No description provided for @deviceRamBelowMinimum.
  ///
  /// In en, this message translates to:
  /// **'Detected RAM: {ram} GB. Minimum recommended: 4 GB.'**
  String deviceRamBelowMinimum(String ram);

  /// Payment method description
  ///
  /// In en, this message translates to:
  /// **'Add or change your payment method'**
  String get addOrChangePaymentMethod;

  /// The Omi app/assistant name shown in chat app selection
  ///
  /// In en, this message translates to:
  /// **'Omi'**
  String get omiAppName;

  /// Title for dialog prompting user to enable Bluetooth
  ///
  /// In en, this message translates to:
  /// **'Enable Bluetooth'**
  String get enableBluetooth;

  /// privacyNotice label
  ///
  /// In en, this message translates to:
  /// **'Privacy Notice'**
  String get privacyNotice;

  /// Label for manufacturer field
  ///
  /// In en, this message translates to:
  /// **'Manufacturer'**
  String get manufacturer;

  /// First part of terms agreement text
  ///
  /// In en, this message translates to:
  /// **'By continuing, you agree to our '**
  String get byContinuingYouAgree;

  /// Success notification after migration completes
  ///
  /// In en, this message translates to:
  /// **'Your data is now protected with the new {level} settings.'**
  String dataProtectedWithSettings(String level);

  /// No description provided for @selectSpaceInWorkspace.
  ///
  /// In en, this message translates to:
  /// **'Select a space in your workspace'**
  String get selectSpaceInWorkspace;

  /// Button label to copy API key
  ///
  /// In en, this message translates to:
  /// **'Copy Key'**
  String get copyKey;

  /// WiFi sync settings - password
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get password;

  /// Shows estimated file size
  ///
  /// In en, this message translates to:
  /// **'Estimated Size: ~{size} MB'**
  String estimatedSize(String size);

  /// Badge on an annual plan card showing how many months the annual price saves
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 Month Free} other{{count} Months Free}}'**
  String monthsFreeBadge(int count);

  /// Row subtitle for a chat app that cannot be connected yet
  ///
  /// In en, this message translates to:
  /// **'Not available yet'**
  String get chatAppsNotAvailableYet;

  /// Shows estimated remaining time for processing
  ///
  /// In en, this message translates to:
  /// **'Estimated: {time} remaining'**
  String estimatedTimeRemaining(String time);

  /// Status card line when the backend stale-guard has flagged queued jobs (i.e. workers are saturated, not the user being rate-limited). Distinct from the 429 fair-use case.
  ///
  /// In en, this message translates to:
  /// **'Omi servers are busy — your recordings will sync once capacity returns'**
  String get syncCardBackendBusy;

  /// Card title asking the user to label speakers from recent conversations
  ///
  /// In en, this message translates to:
  /// **'Help Omi recognize voices'**
  String get speakerTagPromptTitle;

  /// Accessibility label of the play button on a transcript line
  ///
  /// In en, this message translates to:
  /// **'Play from here'**
  String get playFromHere;

  /// Label above a project page title
  ///
  /// In en, this message translates to:
  /// **'Project'**
  String get entityProject;

  /// Error message when permission is missing
  ///
  /// In en, this message translates to:
  /// **'Permission not granted yet. Please make sure you allowed microphone access and reopened the app on your watch.'**
  String get permissionNotGrantedYet;

  /// Second trade-off bullet point for E2EE
  ///
  /// In en, this message translates to:
  /// **'• If you lose your password, your data cannot be recovered.'**
  String get e2eeTradeoff2;

  /// No description provided for @exportConfiguration.
  ///
  /// In en, this message translates to:
  /// **'Export configuration'**
  String get exportConfiguration;

  /// Title of the sheet listing ways to record (Phone mic, Phone call).
  ///
  /// In en, this message translates to:
  /// **'Record with'**
  String get recordWith;

  /// Home greeting (large title) for 6 PM to 8 PM; keep it short so the first name fits after it on one line
  ///
  /// In en, this message translates to:
  /// **'Evening'**
  String get greetingEvening;

  /// No description provided for @deletePhoneNumberConfirm.
  ///
  /// In en, this message translates to:
  /// **'Delete {phoneNumber}?'**
  String deletePhoneNumberConfirm(String phoneNumber);

  /// Tutorial step 2 title — prompts the user to ask Omi a voice question with a single button press
  ///
  /// In en, this message translates to:
  /// **'Ask Omi a Question'**
  String get deviceOnboardingAskQuestionTitle;

  /// Placeholder text for app name input
  ///
  /// In en, this message translates to:
  /// **'My Awesome App'**
  String get appNamePlaceholder;

  /// Instruction when paused
  ///
  /// In en, this message translates to:
  /// **'Tap play to resume'**
  String get tapPlayToResume;

  /// Label for due date field
  ///
  /// In en, this message translates to:
  /// **'Due Date'**
  String get dueDate;

  /// No description provided for @appearanceSystem.
  ///
  /// In en, this message translates to:
  /// **'System'**
  String get appearanceSystem;

  /// Error when email format is invalid
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid email'**
  String get invalidEmailError;

  /// Title for high resource usage dialog
  ///
  /// In en, this message translates to:
  /// **'High Resource Usage'**
  String get highResourceUsage;

  /// Voice and people section title
  ///
  /// In en, this message translates to:
  /// **'Voice & People'**
  String get voiceAndPeople;

  /// Customization section header
  ///
  /// In en, this message translates to:
  /// **'Customization'**
  String get customizationSection;

  /// Error message when subscription cancellation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to cancel subscription. Please try again.'**
  String get failedToCancelSubscription;

  /// Button text to postpone an action
  ///
  /// In en, this message translates to:
  /// **'Not Now'**
  String get later;

  /// Label under total tasks count
  ///
  /// In en, this message translates to:
  /// **'tasks generated'**
  String get wrappedTasksGenerated;

  /// Loading message shown while personalizing user experience
  ///
  /// In en, this message translates to:
  /// **'Personalizing your experience…'**
  String get personalizingExperience;

  /// Label for sync notification
  ///
  /// In en, this message translates to:
  /// **'Sync Available'**
  String get syncAvailable;

  /// Greeting at the top of an empty chat; name is the user's first name
  ///
  /// In en, this message translates to:
  /// **'Hi {name}, ask anything'**
  String chatGreeting(String name);

  /// No description provided for @phoneCallSettingsTitle.
  ///
  /// In en, this message translates to:
  /// **'Phone Call Settings'**
  String get phoneCallSettingsTitle;

  /// No description provided for @remoteDeviceTerminated.
  ///
  /// In en, this message translates to:
  /// **'Remote device terminated'**
  String get remoteDeviceTerminated;

  /// Error when file picker fails to open
  ///
  /// In en, this message translates to:
  /// **'Error opening file picker: {message}'**
  String addAppErrorOpeningFilePicker(String message);

  /// Message shown when action item is deleted
  ///
  /// In en, this message translates to:
  /// **'Task deleted'**
  String get actionItemDeleted;

  /// Retryable error when fetching memories failed instead of returning an empty list
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load memories'**
  String get couldNotLoadMemories;

  /// Tooltip of the icon button that AI-generates the app description in the submit/update app forms
  ///
  /// In en, this message translates to:
  /// **'Generate description'**
  String get generateDescription;

  /// No description provided for @privateLabel.
  ///
  /// In en, this message translates to:
  /// **'Private'**
  String get privateLabel;

  /// Tutorial step 4 double-tap option title — mute or unmute the microphone
  ///
  /// In en, this message translates to:
  /// **'Mute / Unmute'**
  String get deviceOnboardingMuteUnmute;

  /// No description provided for @day.
  ///
  /// In en, this message translates to:
  /// **'Day'**
  String get day;

  /// Confirmation dialog title
  ///
  /// In en, this message translates to:
  /// **'Submit App?'**
  String get submitAppQuestion;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Words'**
  String get usageWords;

  /// Error message when ClickUp OAuth fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to ClickUp'**
  String get failedToConnectClickUp;

  /// Description for Limitless import option
  ///
  /// In en, this message translates to:
  /// **'Select the .zip file to import!'**
  String get selectZipFileToImport;

  /// Duration in plural seconds
  ///
  /// In en, this message translates to:
  /// **'{count} secs'**
  String timeSecsPlural(int count);

  /// NPS feedback prompt
  ///
  /// In en, this message translates to:
  /// **'Was this helpful?'**
  String get wasThisHelpful;

  /// Loading text while learning from memories
  ///
  /// In en, this message translates to:
  /// **'Learning from your memories…'**
  String get msgLearningMemories;

  /// Error when screen capture permission is needed
  ///
  /// In en, this message translates to:
  /// **'Screen capture permission is required for system audio recording.'**
  String get onboardingScreenCaptureRequired;

  /// Evidence row: the user labeled this person by hand.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Labeled by you in 1 conversation} other{Labeled by you in {count} conversations}}'**
  String evidenceManualLabels(int count);

  /// Snackbar message when transfer is cancelled
  ///
  /// In en, this message translates to:
  /// **'Transfer cancelled'**
  String get transferCancelled;

  /// Label for speed metric of an on-device transcription model
  ///
  /// In en, this message translates to:
  /// **'Speed'**
  String get sttModelSpeed;

  /// No description provided for @fairUsePolicy.
  ///
  /// In en, this message translates to:
  /// **'Fair Use'**
  String get fairUsePolicy;

  /// Label for phone storage tier in sync pipeline
  ///
  /// In en, this message translates to:
  /// **'Phone Storage'**
  String get phoneStorage;

  /// Tutorial step 4 double-tap option description for End Conversation
  ///
  /// In en, this message translates to:
  /// **'Save and end current conversation'**
  String get deviceOnboardingEndConversationDesc;

  /// Button to proceed despite warnings
  ///
  /// In en, this message translates to:
  /// **'Proceed Anyway'**
  String get proceedAnyway;

  /// No description provided for @overview.
  ///
  /// In en, this message translates to:
  /// **'Overview'**
  String get overview;

  /// Tutorial step 1 success message after the user speaks enough words
  ///
  /// In en, this message translates to:
  /// **'Good job!'**
  String get deviceOnboardingGoodJob;

  /// Delete button
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get delete;

  /// Description for MCP server feature
  ///
  /// In en, this message translates to:
  /// **'Connect AI assistants to your data'**
  String get connectAiAssistantsToYourData;

  /// Ask: under New chat
  ///
  /// In en, this message translates to:
  /// **'Start fresh'**
  String get startFresh;

  /// Tutorial step 3 status chip — device reconnected after the power cycle
  ///
  /// In en, this message translates to:
  /// **'Connected!'**
  String get deviceOnboardingStatusConnectedDone;

  /// Filter option for installed apps
  ///
  /// In en, this message translates to:
  /// **'Installed'**
  String get filterInstalled;

  /// Status indicator shown when conversations are being merged
  ///
  /// In en, this message translates to:
  /// **'Merging…'**
  String get mergingStatus;

  /// Title when connection succeeds
  ///
  /// In en, this message translates to:
  /// **'Successfully Connected!'**
  String get successfullyConnected;

  /// Permission title for creating conversations
  ///
  /// In en, this message translates to:
  /// **'Create Conversations'**
  String get permissionCreateConversations;

  /// Cancel consequence - phone calls
  ///
  /// In en, this message translates to:
  /// **'No real-time phone call transcription'**
  String get cancelConsequencePhoneCalls;

  /// Quick reason chip: some other summary problem.
  ///
  /// In en, this message translates to:
  /// **'Something else'**
  String get feedbackReasonSummaryOther;

  /// OAuth section header
  ///
  /// In en, this message translates to:
  /// **'OAuth'**
  String get oAuth;

  /// Warning when not enough disk space
  ///
  /// In en, this message translates to:
  /// **'Warning: Not enough space!'**
  String get notEnoughSpace;

  /// Feedback title when cancel reason is too expensive
  ///
  /// In en, this message translates to:
  /// **'What price would work for you?'**
  String get feedbackTitleTooExpensive;

  /// Title for secure encryption card
  ///
  /// In en, this message translates to:
  /// **'Secure Encryption'**
  String get secureEncryption;

  /// Filter for apps with 2 or more stars
  ///
  /// In en, this message translates to:
  /// **'2+ Stars'**
  String get rating2PlusStars;

  /// Button that reopens Apple's Messages app
  ///
  /// In en, this message translates to:
  /// **'Open Messages Again'**
  String get chatAppsOpenMessagesAgain;

  /// No description provided for @fairUseBudgetResetsAt.
  ///
  /// In en, this message translates to:
  /// **'Resets {time}'**
  String fairUseBudgetResetsAt(String time);

  /// Description for custom vocabulary section
  ///
  /// In en, this message translates to:
  /// **'Add words that Omi should recognize during transcription.'**
  String get addVocabularyDescription;

  /// Whisper model size: medium
  ///
  /// In en, this message translates to:
  /// **'Medium'**
  String get whisperModelSizeMedium;

  /// Uppercase label for buddies tile in collage
  ///
  /// In en, this message translates to:
  /// **'MY BUDDIES'**
  String get wrappedMyBuddiesLabel;

  /// Accessible name for the memories graph button
  ///
  /// In en, this message translates to:
  /// **'Memory graph'**
  String get memoryGraph;

  /// No description provided for @paste.
  ///
  /// In en, this message translates to:
  /// **'Paste'**
  String get paste;

  /// Error message when GitHub status refresh fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh GitHub connection status.'**
  String get failedToRefreshGitHubStatus;

  /// Feedback subtitle for missing features
  ///
  /// In en, this message translates to:
  /// **'We\'re always building — this helps us prioritize.'**
  String get feedbackSubtitleMissingFeatures;

  /// The word 'App' used as parameter in other strings
  ///
  /// In en, this message translates to:
  /// **'App'**
  String get itemApp;

  /// Pairing description for Friend Pendant
  ///
  /// In en, this message translates to:
  /// **'Press the button on the pendant to turn it on. It will enter pairing mode automatically.'**
  String get pairingDescFriendPendant;

  /// Explains that an app was disabled for a reason other than webhook failures
  ///
  /// In en, this message translates to:
  /// **'It was disabled by Omi.'**
  String get appDisabledGeneric;

  /// Message when app has no summary
  ///
  /// In en, this message translates to:
  /// **'No summary available for this app. Try another app for better results.'**
  String get noSummaryForApp;

  /// Menu item to delete processed files
  ///
  /// In en, this message translates to:
  /// **'Delete Processed'**
  String get deleteProcessed;

  /// Action on a chat goal link block
  ///
  /// In en, this message translates to:
  /// **'Open in Goals'**
  String get chatBlockOpenInGoals;

  /// Mic gain description: Moderate
  ///
  /// In en, this message translates to:
  /// **'Quiet - for moderate noise'**
  String get micGainDescModerate;

  /// No description provided for @defaultRepository.
  ///
  /// In en, this message translates to:
  /// **'Default Repository'**
  String get defaultRepository;

  /// Import job status - pending
  ///
  /// In en, this message translates to:
  /// **'Pending'**
  String get statusPending;

  /// Referral program menu item
  ///
  /// In en, this message translates to:
  /// **'Referral Program'**
  String get referralProgram;

  /// Error message when linking Apple account fails
  ///
  /// In en, this message translates to:
  /// **'Failed to link with Apple, please try again.'**
  String get authFailedToLinkApple;

  /// Model filename label
  ///
  /// In en, this message translates to:
  /// **'Model: {model}'**
  String modelNameWithFile(String model);

  /// Tutorial step 3 instruction to press the button to turn the device back on
  ///
  /// In en, this message translates to:
  /// **'Press the button to turn it back on'**
  String get deviceOnboardingTurnOnSubtitle;

  /// Section title for app preview images
  ///
  /// In en, this message translates to:
  /// **'Preview and Screenshots'**
  String get previewAndScreenshots;

  /// Live-capture empty state while the device has no internet connection
  ///
  /// In en, this message translates to:
  /// **'Recording offline — the transcript will catch up when you\'re back online.'**
  String get recordingOfflineTranscriptWillCatchUp;

  /// No description provided for @accessibilityDescription.
  ///
  /// In en, this message translates to:
  /// **'Omi needs accessibility permission to detect when you join Zoom, Meet, or Teams meetings in your browser.'**
  String get accessibilityDescription;

  /// No description provided for @setDefaultAppContent.
  ///
  /// In en, this message translates to:
  /// **'Set {appName} as your default summarization app?\n\nThis app will be automatically used for all future conversation summaries.'**
  String setDefaultAppContent(String appName);

  /// Hint that switching API environment requires restart
  ///
  /// In en, this message translates to:
  /// **'Switching requires app restart'**
  String get switchRequiresRestart;

  /// Second line of win card header
  ///
  /// In en, this message translates to:
  /// **'Win'**
  String get wrappedWinHeader;

  /// Home proactivity feed section title
  ///
  /// In en, this message translates to:
  /// **'For You'**
  String get forYou;

  /// Category filter dropdown label
  ///
  /// In en, this message translates to:
  /// **'Category'**
  String get filterCategory;

  /// Hint text for creating a person
  ///
  /// In en, this message translates to:
  /// **'Create a new person and train Omi to recognize their speech too!'**
  String get createPersonHint;

  /// Loading overlay message when reloading memories
  ///
  /// In en, this message translates to:
  /// **'Loading memories…'**
  String get loadingMemories;

  /// Section header for selected payment method
  ///
  /// In en, this message translates to:
  /// **'Selected Payment Method'**
  String get selectedPaymentMethod;

  /// Email field label
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get email;

  /// Live capture status while the transcription service is down; audio keeps recording locally.
  ///
  /// In en, this message translates to:
  /// **'Transcriptions are unavailable, recording continues on device and will process later'**
  String get transcriptionUnavailableRecordingContinues;

  /// No description provided for @noLogsYet.
  ///
  /// In en, this message translates to:
  /// **'No logs yet. Record something to see requests to your transcription provider.'**
  String get noLogsYet;

  /// Error when OAuth fails to start
  ///
  /// In en, this message translates to:
  /// **'Failed to start authentication'**
  String get failedToStartAuthentication;

  /// A count of people (People list filters and summary)
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 person} other{{count} people}}'**
  String peopleCount(int count);

  /// Error when backend URL is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter the backend URL'**
  String get enterBackendUrlError;

  /// Pill above the player that scrolls the transcript back to the currently playing line
  ///
  /// In en, this message translates to:
  /// **'Back to Current'**
  String get playbackBackToCurrent;

  /// No description provided for @clockSkewWarning.
  ///
  /// In en, this message translates to:
  /// **'Your device clock is off by ~{minutes} min. Check your date & time settings.'**
  String clockSkewWarning(int minutes);

  /// Disable the producer of a For You card
  ///
  /// In en, this message translates to:
  /// **'Stop These'**
  String get stopThese;

  /// No description provided for @yes.
  ///
  /// In en, this message translates to:
  /// **'Yes'**
  String get yes;

  /// Button text to recognize other people
  ///
  /// In en, this message translates to:
  /// **'Recognizing others 👀'**
  String get recognizingOthers;

  /// Description for the transcription language selector
  ///
  /// In en, this message translates to:
  /// **'Choose the language for speech transcription'**
  String get transcriptionLanguageDesc;

  /// Migration time remaining in minutes
  ///
  /// In en, this message translates to:
  /// **'About {minutes} minutes remaining'**
  String aboutMinutesRemaining(int minutes);

  /// Subtitle on delete-account flow reason step
  ///
  /// In en, this message translates to:
  /// **'Your feedback helps us improve Omi for everyone.'**
  String get deleteFlowReasonSubtitle;

  /// Snackbar message when processed files are deleted
  ///
  /// In en, this message translates to:
  /// **'Processed files deleted'**
  String get processedFilesDeleted;

  /// No description provided for @autoLanguageDetection.
  ///
  /// In en, this message translates to:
  /// **'Auto language detection'**
  String get autoLanguageDetection;

  /// Snackbar shown when only some items in a bulk export succeeded
  ///
  /// In en, this message translates to:
  /// **'Exported {success} of {total} to {platform}'**
  String bulkExportPartial(int success, int total, String platform);

  /// Error message when action item description is empty
  ///
  /// In en, this message translates to:
  /// **'Task description cannot be empty'**
  String get actionItemDescriptionCannotBeEmpty;

  /// Delete reason option
  ///
  /// In en, this message translates to:
  /// **'Using something else'**
  String get deleteReasonFoundAlternative;

  /// Message when there is no content available
  ///
  /// In en, this message translates to:
  /// **'No content to display'**
  String get noContentToDisplay;

  /// Quick reason chip: the speaker attribution was wrong.
  ///
  /// In en, this message translates to:
  /// **'Wrong speaker'**
  String get feedbackReasonRecordingWrongSpeaker;

  /// Button label to create a new task
  ///
  /// In en, this message translates to:
  /// **'Create'**
  String get create;

  /// Encouragement message during speech profile recording
  ///
  /// In en, this message translates to:
  /// **'Great job, you are almost there'**
  String get greatJobAlmostThere;

  /// Transcribe Later card for a pendant, line 2: the pendant's own storage is almost full.
  ///
  /// In en, this message translates to:
  /// **'Storage almost full'**
  String get captureStorageAlmostFull;

  /// Header subtitle; date is like 'Oct 10, 2026'
  ///
  /// In en, this message translates to:
  /// **'Connected {date}'**
  String chatAppsConnectedOn(String date);

  /// Default title for most fun day
  ///
  /// In en, this message translates to:
  /// **'A Great Day'**
  String get wrappedAGreatDay;

  /// Success message when backend URL is saved
  ///
  /// In en, this message translates to:
  /// **'Backend URL saved successfully!'**
  String get backendUrlSavedSuccess;

  /// Question shown under a short audio clip of a speaker
  ///
  /// In en, this message translates to:
  /// **'Was this you?'**
  String get speakerTagPromptIsThisYou;

  /// Success message after deleting knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Knowledge Graph deleted successfully'**
  String get knowledgeGraphDeletedSuccess;

  /// Duration in plural minutes
  ///
  /// In en, this message translates to:
  /// **'{count} mins'**
  String timeMinsPlural(int count);

  /// Section header and row subtitle for a person with zero conversations
  ///
  /// In en, this message translates to:
  /// **'Not Heard Yet'**
  String get peopleNotHeardYet;

  /// Suggested first question in a new chat
  ///
  /// In en, this message translates to:
  /// **'What could I do differently today?'**
  String get chatStarterDoDifferently;

  /// No description provided for @fairUseAboutBody.
  ///
  /// In en, this message translates to:
  /// **'Omi is designed for personal conversations, meetings, and live interactions. Usage is measured by time spent speaking, not time connected. If your usage is far above normal personal use, you\'ll get a warning first. Continued heavy use can slow down or limit transcription.'**
  String get fairUseAboutBody;

  /// No description provided for @pleaseSelectYourPrimaryLanguage.
  ///
  /// In en, this message translates to:
  /// **'Please select your primary language'**
  String get pleaseSelectYourPrimaryLanguage;

  /// No description provided for @manualDisconnect.
  ///
  /// In en, this message translates to:
  /// **'Manual disconnect'**
  String get manualDisconnect;

  /// Dialog title shown when trying to link a conversation to a calendar event without Google Calendar connected
  ///
  /// In en, this message translates to:
  /// **'Google Calendar Not Connected'**
  String get googleCalendarNotConnected;

  /// Encouragement message when speech profile is nearly complete
  ///
  /// In en, this message translates to:
  /// **'So close, just a little more'**
  String get soCloseJustLittleMore;

  /// Body of the consent dialog before enabling an app that works outside Omi: what leaves Omi and where it goes
  ///
  /// In en, this message translates to:
  /// **'{appName} will receive your conversations, memories and recordings on its developer\'s server. Omi isn\'t responsible for how that data is used there.'**
  String appDataAccessMessage(String appName);

  /// No description provided for @savePercent.
  ///
  /// In en, this message translates to:
  /// **'Save ~{percent}%'**
  String savePercent(int percent);

  /// Body text for device disconnected notification
  ///
  /// In en, this message translates to:
  /// **'Please reconnect to continue using your Omi.'**
  String get deviceDisconnectedNotificationBody;

  /// Accessibility label for the button that opens the conversation a memory came from
  ///
  /// In en, this message translates to:
  /// **'Open conversation'**
  String get openConversation;

  /// Description for maximum notification frequency
  ///
  /// In en, this message translates to:
  /// **'Every useful connection, up to 9 a day'**
  String get frequencyDescMaximum;

  /// Toggle label for reading chat replies aloud
  ///
  /// In en, this message translates to:
  /// **'Read chat replies aloud'**
  String get readChatRepliesAloud;

  /// Error message when microphone permission is not granted
  ///
  /// In en, this message translates to:
  /// **'Microphone permission is required to make calls'**
  String get microphonePermissionRequired;

  /// Description when updating PayPal account
  ///
  /// In en, this message translates to:
  /// **'Update your PayPal account details'**
  String get updatePayPalAccountDetails;

  /// No description provided for @connectionTimeout.
  ///
  /// In en, this message translates to:
  /// **'Connection timeout'**
  String get connectionTimeout;

  /// Mic gain description: High
  ///
  /// In en, this message translates to:
  /// **'High - for distant or soft voices'**
  String get micGainDescHigh;

  /// Info note explaining permission toggles
  ///
  /// In en, this message translates to:
  /// **'R = Read, W = Write. Defaults to read-only if nothing selected.'**
  String get permissionsInfoNote;

  /// Duration in hours and minutes
  ///
  /// In en, this message translates to:
  /// **'{hours} hours {mins} mins'**
  String timeHoursAndMins(int hours, int mins);

  /// Secondary action to back out of deletion
  ///
  /// In en, this message translates to:
  /// **'Keep My Account'**
  String get keepMyAccount;

  /// Label for the transcription language selector
  ///
  /// In en, this message translates to:
  /// **'Transcription Language'**
  String get transcriptionLanguage;

  /// Technical stats for a run: items read and model tokens used.
  ///
  /// In en, this message translates to:
  /// **'Read {records} items · {tokens} tokens'**
  String dreamReportStats(int records, int tokens);

  /// Title for edit person dialog
  ///
  /// In en, this message translates to:
  /// **'Edit Person'**
  String get editPerson;

  /// Privacy page - whatWeTrack
  ///
  /// In en, this message translates to:
  /// **'What We Track'**
  String get whatWeTrack;

  /// Mic gain description: Very High
  ///
  /// In en, this message translates to:
  /// **'Very high - for very quiet sources'**
  String get micGainDescVeryHigh;

  /// Compact duration in days (chart axis)
  ///
  /// In en, this message translates to:
  /// **'{count}d'**
  String timeCompactDays(int count);

  /// Text field label for the task text
  ///
  /// In en, this message translates to:
  /// **'Task'**
  String get reviewTaskField;

  /// Button: confirm the chosen person
  ///
  /// In en, this message translates to:
  /// **'Confirm {name}'**
  String reviewConfirmPerson(String name);

  /// No description provided for @downloadingFromDevice.
  ///
  /// In en, this message translates to:
  /// **'Downloading from device'**
  String get downloadingFromDevice;

  /// No description provided for @conversationTranscriptCopiedToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Conversation transcript copied to clipboard'**
  String get conversationTranscriptCopiedToClipboard;

  /// No description provided for @continueAction.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get continueAction;

  /// Confirmation after moving selected conversations into a folder
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Moved 1 conversation} other{Moved {count} conversations}}'**
  String conversationsMovedCount(int count);

  /// Sign in button text
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get signInButton;

  /// Pre-flight sheet button that starts a firmware update
  ///
  /// In en, this message translates to:
  /// **'Start Update'**
  String get startUpdate;

  /// Section title in summary collage (uppercase)
  ///
  /// In en, this message translates to:
  /// **'TOP PHRASES'**
  String get wrappedTopPhrasesLabelUpper;

  /// Label for total memory count statistic
  ///
  /// In en, this message translates to:
  /// **'Total'**
  String get total;

  /// Deleting in progress indicator
  ///
  /// In en, this message translates to:
  /// **'Deleting…'**
  String get deleting;

  /// Accessibility label of the playback control that jumps back 10 seconds
  ///
  /// In en, this message translates to:
  /// **'Back 10 seconds'**
  String get skipBack10Seconds;

  /// Error message when not all questions are answered
  ///
  /// In en, this message translates to:
  /// **'You haven\'t answered all the questions yet! 🥺'**
  String get setupAnswerAllQuestions;

  /// Success message when plan upgrade is scheduled
  ///
  /// In en, this message translates to:
  /// **'Upgrade scheduled! Your monthly plan continues until the end of your billing period, then automatically switches to annual.'**
  String get planUpgradeScheduledMessage;

  /// needHelpChatWithUs label
  ///
  /// In en, this message translates to:
  /// **'Need Help? Chat with us'**
  String get needHelpChatWithUs;

  /// Status shown when a chat block's entity no longer exists
  ///
  /// In en, this message translates to:
  /// **'No longer available'**
  String get chatBlockUnavailable;

  /// Estimated time in minutes
  ///
  /// In en, this message translates to:
  /// **'~{count} minute(s)'**
  String estimatedMinutes(int count);

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'Failed to save. Please check your connection.'**
  String get failedToSaveMemory;

  /// Delete reason option
  ///
  /// In en, this message translates to:
  /// **'Just taking a break'**
  String get deleteReasonTakingBreak;

  /// Subtitle explaining what users can do on conversations page
  ///
  /// In en, this message translates to:
  /// **'Review and manage your captured conversations'**
  String get reviewAndManageConversations;

  /// No description provided for @actionReadMemories.
  ///
  /// In en, this message translates to:
  /// **'Read memories'**
  String get actionReadMemories;

  /// Dialog message when deleting a pinned person.
  ///
  /// In en, this message translates to:
  /// **'{name} is pinned. Their voice samples are removed, Omi stops recognizing them, and past transcripts show them as an unnamed speaker. This can\'t be undone.'**
  String deletePinnedPersonMessage(String name);

  /// Hint at the bottom of the 'Is this you?' card.
  ///
  /// In en, this message translates to:
  /// **'Your answer labels only the played excerpt.'**
  String get speakerTagPromptHintOwner;

  /// Error when notification permission is denied with specific path
  ///
  /// In en, this message translates to:
  /// **'Notification permission denied. Please grant permission in System Preferences > Notifications.'**
  String get onboardingNotificationDeniedNotifications;

  /// Undo toast after disabling an app
  ///
  /// In en, this message translates to:
  /// **'{appName} disabled'**
  String appDisabledNamed(String appName);

  /// Label for Old tab
  ///
  /// In en, this message translates to:
  /// **'Old'**
  String get tabOld;

  /// Output consequence for Headphones only mode with connected headphones
  ///
  /// In en, this message translates to:
  /// **'{device} connected. Omi will speak here.'**
  String deviceOnboardingVoiceReplyStatusHeadphonesConnected(String device);

  /// Dialog title for deleting pending files
  ///
  /// In en, this message translates to:
  /// **'Delete Pending Recordings'**
  String get deletePendingFiles;

  /// Word Win in Wrapped template
  ///
  /// In en, this message translates to:
  /// **'Win'**
  String get wrappedWin;

  /// Description for no folder option
  ///
  /// In en, this message translates to:
  /// **'Remove from all folders'**
  String get removeFromAllFolders;

  /// Label for device ID in details
  ///
  /// In en, this message translates to:
  /// **'Device ID'**
  String get deviceIdLabel;

  /// Message when upgrade is already scheduled
  ///
  /// In en, this message translates to:
  /// **'Your upgrade to the annual plan is already scheduled'**
  String get upgradeAlreadyScheduled;

  /// Accessibility hint on the live card during a call; tapping opens the call screen.
  ///
  /// In en, this message translates to:
  /// **'Open call'**
  String get openCall;

  /// Title prompting user to rate and review an app
  ///
  /// In en, this message translates to:
  /// **'Rate and Review this App'**
  String get rateAndReviewThisApp;

  /// Button text to begin a process
  ///
  /// In en, this message translates to:
  /// **'Get Started'**
  String get getStarted;

  /// Description of the Always voice response mode
  ///
  /// In en, this message translates to:
  /// **'Uses the phone speaker when no headphones are connected.'**
  String get deviceOnboardingVoiceReplyAlwaysDescription;

  /// Title of the bottom sheet listing platforms to bulk-export selected action items to
  ///
  /// In en, this message translates to:
  /// **'Export {count} item(s) to…'**
  String chooseExportDestination(int count);

  /// Onboarding setup page subtitle
  ///
  /// In en, this message translates to:
  /// **'Give Omi a moment to personalize'**
  String get onboardingSetupSubtitle;

  /// Welcome message with user name
  ///
  /// In en, this message translates to:
  /// **'Welcome back, {name}'**
  String welcomeBack(String name);

  /// Toast when a manual run finds no changed items.
  ///
  /// In en, this message translates to:
  /// **'Nothing new to look at yet.'**
  String get dreamReportIdle;

  /// Title of the page that reviews unsure people before deleting them (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Clean Up'**
  String get cleanUpTitle;

  /// Dialog title for deleting processed files
  ///
  /// In en, this message translates to:
  /// **'Delete Processed Files'**
  String get deleteProcessedFiles;

  /// Button text to decline or dismiss
  ///
  /// In en, this message translates to:
  /// **'No'**
  String get no;

  /// Generic error when taking photo fails
  ///
  /// In en, this message translates to:
  /// **'Error taking photo. Please try again.'**
  String get msgPhotoError;

  /// Search button and label
  ///
  /// In en, this message translates to:
  /// **'Search'**
  String get search;

  /// Status text shown while downloading firmware
  ///
  /// In en, this message translates to:
  /// **'Downloading Firmware'**
  String get downloadingFirmware;

  /// No description provided for @phoneKeypadTab.
  ///
  /// In en, this message translates to:
  /// **'Keypad'**
  String get phoneKeypadTab;

  /// Shown when offline sync stalls because the Limitless Pendant's flash storage is full; a full pendant stays armed in recording mode and serves no stored audio until recording is stopped
  ///
  /// In en, this message translates to:
  /// **'Your Pendant\'s storage is full and it\'s still in recording mode, so its stored audio can\'t be transferred. Press the Pendant\'s button to stop recording, then sync again.'**
  String get pendantFullSyncBlocked;

  /// Title for bulk delete dialog
  ///
  /// In en, this message translates to:
  /// **'Delete Selected Items'**
  String get deleteSelectedItemsTitle;

  /// Section title for privacy and terms agreement
  ///
  /// In en, this message translates to:
  /// **'App Privacy & Terms'**
  String get appPrivacyAndTerms;

  /// No description provided for @omiTranscription.
  ///
  /// In en, this message translates to:
  /// **'Omi Transcription'**
  String get omiTranscription;

  /// No description provided for @editConversation.
  ///
  /// In en, this message translates to:
  /// **'Edit conversation'**
  String get editConversation;

  /// Dialog subtitle when deleting folder
  ///
  /// In en, this message translates to:
  /// **'Move {count} conversations to:'**
  String moveConversationsTo(int count);

  /// Confirmation message in sign out dialog
  ///
  /// In en, this message translates to:
  /// **'You\'ll need to sign in again to see your conversations. Your paired device and app preferences stay on this phone.'**
  String get signOutConfirmation;

  /// Uppercase label for obsessions tile in collage
  ///
  /// In en, this message translates to:
  /// **'OBSESSIONS'**
  String get wrappedObsessionsLabel;

  /// Accessibility label and tooltip for the jump-to-latest button in chat
  ///
  /// In en, this message translates to:
  /// **'Jump to latest message'**
  String get jumpToLatestMessage;

  /// Status label when sync has failed
  ///
  /// In en, this message translates to:
  /// **'Failed'**
  String get failedStatus;

  /// Button that postpones a prompt without dismissing it forever (iOS "Not Now")
  ///
  /// In en, this message translates to:
  /// **'Not Now'**
  String get notNow;

  /// Error message when transfer fails
  ///
  /// In en, this message translates to:
  /// **'Transfer failed: {error}'**
  String transferFailedMessage(String error);

  /// No description provided for @customVocabularyTitle.
  ///
  /// In en, this message translates to:
  /// **'Custom Vocabulary'**
  String get customVocabularyTitle;

  /// Error message when internet connection is needed
  ///
  /// In en, this message translates to:
  /// **'Internet required'**
  String get internetRequired;

  /// No description provided for @waitingForData.
  ///
  /// In en, this message translates to:
  /// **'Waiting for data…'**
  String get waitingForData;

  /// No description provided for @noRecordingsYet.
  ///
  /// In en, this message translates to:
  /// **'No recordings yet'**
  String get noRecordingsYet;

  /// Heading of the compact card listing the topics to speak about while recording the speech profile
  ///
  /// In en, this message translates to:
  /// **'Answer with your voice:'**
  String get answerWithYourVoice;

  /// Toast after unpinning a person.
  ///
  /// In en, this message translates to:
  /// **'{name} unpinned'**
  String personUnpinnedToast(String name);

  /// Button label to stop recording
  ///
  /// In en, this message translates to:
  /// **'Stop Recording'**
  String get stopRecording;

  /// Toggle state label when disabled
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get off;

  /// Provenance label when capture device is this Android phone
  ///
  /// In en, this message translates to:
  /// **'This phone'**
  String get memoryThisPhone;

  /// Info about total coverage period
  ///
  /// In en, this message translates to:
  /// **'You\'ll get 13 months of coverage total (current month + 12 months annual)'**
  String get thirteenMonthsCoverage;

  /// Error message when API key creation fails
  ///
  /// In en, this message translates to:
  /// **'Failed to create provider API key: {error}'**
  String failedToCreateApiKey(String error);

  /// Tip in sync info sheet
  ///
  /// In en, this message translates to:
  /// **'Stable internet speeds up cloud uploads'**
  String get tipStableInternet;

  /// No description provided for @tasksMarkComplete.
  ///
  /// In en, this message translates to:
  /// **'Marked as complete'**
  String get tasksMarkComplete;

  /// Button: accept a suggested task (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Add Task'**
  String get reviewAddTask;

  /// Button text to submit a reply
  ///
  /// In en, this message translates to:
  /// **'Submit Reply'**
  String get submitReply;

  /// Reconnect banner shown after automatic BLE recovery has not restored pendant audio; tapping opens device settings
  ///
  /// In en, this message translates to:
  /// **'Omi isn\'t sending audio — tap to reconnect'**
  String get captureRecoveryBanner;

  /// Loading text shown while analyzing a photo
  ///
  /// In en, this message translates to:
  /// **'Analyzing…'**
  String get analyzing;

  /// Relative speed indicator: faster
  ///
  /// In en, this message translates to:
  /// **'Faster'**
  String get sttModelFaster;

  /// No description provided for @fairUseLoadError.
  ///
  /// In en, this message translates to:
  /// **'Unable to load fair use status. Please try again.'**
  String get fairUseLoadError;

  /// Search tile that opens conversations on a map
  ///
  /// In en, this message translates to:
  /// **'Places'**
  String get places;

  /// How close a voice is to a person: not very close.
  ///
  /// In en, this message translates to:
  /// **'Weak match'**
  String get voiceMatchWeak;

  /// Live capture status with how many minutes audio has been kept on the phone
  ///
  /// In en, this message translates to:
  /// **'Offline, buffering · {minutes} min'**
  String captureOfflineBufferingFor(int minutes);

  /// Title for onboarding step that previews the memory graph
  ///
  /// In en, this message translates to:
  /// **'Here is what I know about you'**
  String get onboardingWhatIKnowAboutYouTitle;

  /// No description provided for @raybanMetaPhotoRequested.
  ///
  /// In en, this message translates to:
  /// **'Photo requested — it will appear in your conversation.'**
  String get raybanMetaPhotoRequested;

  /// No description provided for @verifyYourNumber.
  ///
  /// In en, this message translates to:
  /// **'Verify your number'**
  String get verifyYourNumber;

  /// Subtitle on final delete confirmation step
  ///
  /// In en, this message translates to:
  /// **'This can\'t be undone, even by support.'**
  String get deleteFlowConfirmSubtitle;

  /// Terms and conditions agreement checkbox text
  ///
  /// In en, this message translates to:
  /// **'By submitting this app, I agree to the Omi AI Terms of Service and Privacy Policy'**
  String get submitAppTermsAgreement;

  /// Description of Stripe security feature
  ///
  /// In en, this message translates to:
  /// **'Stripe ensures safe and timely transfers of your app revenue'**
  String get stripeSecureDescription;

  /// No description provided for @categoryProductivity.
  ///
  /// In en, this message translates to:
  /// **'Productivity'**
  String get categoryProductivity;

  /// Chat subtitle with app name
  ///
  /// In en, this message translates to:
  /// **'Chat with {appName}'**
  String chatWithAppName(String appName);

  /// enableCloudStorage label
  ///
  /// In en, this message translates to:
  /// **'Enable Cloud Storage'**
  String get enableCloudStorage;

  /// Error message when realtime transcript webhook URL is invalid in developer settings
  ///
  /// In en, this message translates to:
  /// **'Invalid realtime transcript webhook URL'**
  String get devModeInvalidRealtimeTranscriptWebhookUrl;

  /// Label for show obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'SHOW'**
  String get wrappedShow;

  /// Tagline or slogan on the welcome/auth screen
  ///
  /// In en, this message translates to:
  /// **'Speak. Transcribe. Summarize.'**
  String get speakTranscribeSummarize;

  /// Paid pricing option
  ///
  /// In en, this message translates to:
  /// **'Paid'**
  String get pricingPaid;

  /// Success message when Asana OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Asana!'**
  String get successfullyConnectedAsana;

  /// No description provided for @rating.
  ///
  /// In en, this message translates to:
  /// **'Rating'**
  String get rating;

  /// AI reply message shown when user exceeds chat quota
  ///
  /// In en, this message translates to:
  /// **'You\'ve hit your monthly limit. Upgrade to keep chatting with Omi without restrictions.'**
  String get chatQuotaExceededReply;

  /// Sheet title shown when the user taps the phone record button while the pendant is recording.
  ///
  /// In en, this message translates to:
  /// **'Your pendant is listening'**
  String get pendantIsListeningTitle;

  /// Plan and Usage dashboard label
  ///
  /// In en, this message translates to:
  /// **'Best day'**
  String get usageBestDay;

  /// Link beside a person's confidence level that opens an explanation.
  ///
  /// In en, this message translates to:
  /// **'Why?'**
  String get personWhyConfidence;

  /// Description for create conversations permission
  ///
  /// In en, this message translates to:
  /// **'This app can create new conversations.'**
  String get permissionDescCreateConversations;

  /// Text field label to type a different spelling
  ///
  /// In en, this message translates to:
  /// **'Type it'**
  String get reviewSpellingCustom;

  /// No description provided for @resetsInHours.
  ///
  /// In en, this message translates to:
  /// **'Resets in {count} hour(s)'**
  String resetsInHours(int count);

  /// Button that opens the clean-up review (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Review'**
  String get reviewAction;

  /// Button text to submit request
  ///
  /// In en, this message translates to:
  /// **'Submit Request'**
  String get submitRequest;

  /// No description provided for @phoneCalls.
  ///
  /// In en, this message translates to:
  /// **'Phone Calls'**
  String get phoneCalls;

  /// Tab label for action items
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get actionItemsTab;

  /// Label for the Record button on the home page app bar
  ///
  /// In en, this message translates to:
  /// **'Record'**
  String get record;

  /// Empty state message when no reviews match filter
  ///
  /// In en, this message translates to:
  /// **'No Reviews Found'**
  String get noReviewsFound;

  /// Label for OAuth section
  ///
  /// In en, this message translates to:
  /// **'OAuth'**
  String get oauth;

  /// Confirmation when URL is copied
  ///
  /// In en, this message translates to:
  /// **'URL copied'**
  String get urlCopied;

  /// Title for action item reminder notifications
  ///
  /// In en, this message translates to:
  /// **'Omi Reminder'**
  String get actionItemReminderTitle;

  /// Toast after accepting shared tasks
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Added 1 task to your list} other{Added {count} tasks to your list}}'**
  String sharedTasksAdded(int count);

  /// Error message when contacts permission is denied
  ///
  /// In en, this message translates to:
  /// **'Contacts permission is required to share via SMS'**
  String get contactsPermissionRequiredForSms;

  /// Success message when API key is revoked
  ///
  /// In en, this message translates to:
  /// **'API key revoked successfully'**
  String get apiKeyRevokedSuccessfully;

  /// No description provided for @authorizationSuccessful.
  ///
  /// In en, this message translates to:
  /// **'Authorization successful!'**
  String get authorizationSuccessful;

  /// Swipe action and menu item: unpin this person (Title Case verb).
  ///
  /// In en, this message translates to:
  /// **'Unpin'**
  String get unpinAction;

  /// Status label when syncing is in progress
  ///
  /// In en, this message translates to:
  /// **'Syncing'**
  String get syncingStatus;

  /// Label for audio format in details
  ///
  /// In en, this message translates to:
  /// **'Audio Format'**
  String get audioFormatLabel;

  /// No description provided for @phoneSelectCountryTitle.
  ///
  /// In en, this message translates to:
  /// **'Select Country'**
  String get phoneSelectCountryTitle;

  /// Badge showing user percentile ranking in Wrapped
  ///
  /// In en, this message translates to:
  /// **'Top {percentile}% User'**
  String wrappedTopPercentUser(String percentile);

  /// No description provided for @phoneContactsTab.
  ///
  /// In en, this message translates to:
  /// **'Contacts'**
  String get phoneContactsTab;

  /// Button text to reply to something
  ///
  /// In en, this message translates to:
  /// **'Reply'**
  String get reply;

  /// No description provided for @openingShareSheet.
  ///
  /// In en, this message translates to:
  /// **'Opening share sheet…'**
  String get openingShareSheet;

  /// Status message during app creation
  ///
  /// In en, this message translates to:
  /// **'Creating app icon…'**
  String get creatingAppIcon;

  /// Tutorial step 1 placeholder in the live transcript area before any speech is detected
  ///
  /// In en, this message translates to:
  /// **'Start speaking…'**
  String get deviceOnboardingStartSpeaking;

  /// Default title for funniest moment
  ///
  /// In en, this message translates to:
  /// **'A Hilarious Moment'**
  String get wrappedAHilariousMoment;

  /// No description provided for @paidApp.
  ///
  /// In en, this message translates to:
  /// **'Paid app'**
  String get paidApp;

  /// Second line of struggle card header
  ///
  /// In en, this message translates to:
  /// **'Struggle'**
  String get wrappedStruggleHeader;

  /// Answer button: the speaker is a stranger
  ///
  /// In en, this message translates to:
  /// **'Someone I don\'t know'**
  String get speakerTagPromptDontKnow;

  /// Initial processing step text
  ///
  /// In en, this message translates to:
  /// **'Starting…'**
  String get wrappedStarting;

  /// Button text to get/install an app
  ///
  /// In en, this message translates to:
  /// **'Get'**
  String get getButton;

  /// Title of the dialog shown when a third-party (custom) STT user manually syncs offline recordings
  ///
  /// In en, this message translates to:
  /// **'Sync uses Omi transcription'**
  String get syncCustomSttWarningTitle;

  /// Download button
  ///
  /// In en, this message translates to:
  /// **'Download'**
  String get download;

  /// Accessibility label and tooltip of the control that adds an app screenshot in the submit/update app form
  ///
  /// In en, this message translates to:
  /// **'Add screenshot'**
  String get addScreenshot;

  /// Error message when OAuth fails with specific error details
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to {serviceName}: {error}'**
  String failedToConnectServiceWithError(String serviceName, String error);

  /// Notification body when a device disconnects
  ///
  /// In en, this message translates to:
  /// **'Please reconnect to continue using your {deviceName}.'**
  String deviceDisconnectedBody(String deviceName);

  /// Subtitle for Daily Summary menu item in profile settings
  ///
  /// In en, this message translates to:
  /// **'Configure your daily tasks digest'**
  String get configureDailySummaryDigest;

  /// No description provided for @showShortConversationsDesc.
  ///
  /// In en, this message translates to:
  /// **'Display conversations shorter than the threshold'**
  String get showShortConversationsDesc;

  /// Conversation header people chip when other voices spoke but could not be counted reliably, e.g. 'David + others'
  ///
  /// In en, this message translates to:
  /// **'{name} + others'**
  String participantsSummaryUncounted(String name);

  /// No description provided for @fairUseBudgetUsed.
  ///
  /// In en, this message translates to:
  /// **'{used}m / {limit}m'**
  String fairUseBudgetUsed(String used, String limit);

  /// Add button label
  ///
  /// In en, this message translates to:
  /// **'Add'**
  String get add;

  /// Disconnect device button
  ///
  /// In en, this message translates to:
  /// **'Disconnect'**
  String get disconnect;

  /// No description provided for @enterApiKey.
  ///
  /// In en, this message translates to:
  /// **'Enter your API key'**
  String get enterApiKey;

  /// Error when user tries to select more than 4 files
  ///
  /// In en, this message translates to:
  /// **'You can only select up to 4 files'**
  String get msgMaxFilesLimit;

  /// Space key label
  ///
  /// In en, this message translates to:
  /// **'Space'**
  String get space;

  /// Upgrade button
  ///
  /// In en, this message translates to:
  /// **'Upgrade'**
  String get upgrade;

  /// Subtitle hint for tappable items
  ///
  /// In en, this message translates to:
  /// **'Tap to view'**
  String get tapToView;

  /// No description provided for @summaryTemplate.
  ///
  /// In en, this message translates to:
  /// **'Summary Template'**
  String get summaryTemplate;

  /// Heading while waiting for the person's text to arrive
  ///
  /// In en, this message translates to:
  /// **'Waiting for your text'**
  String get chatAppsWaitingTitle;

  /// Date format showing yesterday with time
  ///
  /// In en, this message translates to:
  /// **'Yesterday at {time}'**
  String yesterdayAtTime(String time);

  /// Generic cancel button label
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// Loading text while checking Apple Watch status
  ///
  /// In en, this message translates to:
  /// **'Checking Apple Watch…'**
  String get checkingAppleWatch;

  /// Offline Sync status card: overall device-download percent and speed. Not shown on recording rows.
  ///
  /// In en, this message translates to:
  /// **'{percent}% · {speed} KB/s'**
  String syncCardDownloadPercentSpeed(int percent, String speed);

  /// No description provided for @finalTouches.
  ///
  /// In en, this message translates to:
  /// **'Final touches'**
  String get finalTouches;

  /// Abbreviated Saturday
  ///
  /// In en, this message translates to:
  /// **'Sat'**
  String get weekdaySat;

  /// No description provided for @fairUseWeekly.
  ///
  /// In en, this message translates to:
  /// **'Weekly Rolling'**
  String get fairUseWeekly;

  /// Error message for invalid payment URL
  ///
  /// In en, this message translates to:
  /// **'Invalid payment URL'**
  String get invalidPaymentUrl;

  /// Warning about transcription speed on older devices
  ///
  /// In en, this message translates to:
  /// **'On-device transcription may be slower on this device.'**
  String get transcriptionSlowerOnDevice;

  /// No description provided for @noListsInSpace.
  ///
  /// In en, this message translates to:
  /// **'No lists found in this space'**
  String get noListsInSpace;

  /// No description provided for @deviceDiagnostics.
  ///
  /// In en, this message translates to:
  /// **'Device Diagnostics'**
  String get deviceDiagnostics;

  /// Chat input placeholder
  ///
  /// In en, this message translates to:
  /// **'Ask anything'**
  String get askAnything;

  /// Screen-reader label for the three-step confidence meter; level is Confirmed, Likely or Unverified.
  ///
  /// In en, this message translates to:
  /// **'Confidence: {level}'**
  String confidenceMeterLabel(String level);

  /// Permission title for reading tasks
  ///
  /// In en, this message translates to:
  /// **'Read Tasks'**
  String get permissionReadTasks;

  /// Link text to skip the permissions screen
  ///
  /// In en, this message translates to:
  /// **'Skip for Now'**
  String get skipForNow;

  /// Label of the setup-completed URL field when submitting an app with external integration
  ///
  /// In en, this message translates to:
  /// **'Setup Completed URL'**
  String get setupCompletedUrl;

  /// Prompt for user to start speaking
  ///
  /// In en, this message translates to:
  /// **'Say something…'**
  String get saySomething;

  /// PDF file format label
  ///
  /// In en, this message translates to:
  /// **'PDF'**
  String get pdfFormat;

  /// Row title on Integrations that opens the Chat apps page
  ///
  /// In en, this message translates to:
  /// **'Chat with Omi'**
  String get chatAppsEntryTitle;

  /// Step 1; 'Open Telegram' refers to the button label
  ///
  /// In en, this message translates to:
  /// **'Tap Open Telegram below'**
  String get chatAppsTelegramStepOpen;

  /// Validation error for invalid PayPal.me link
  ///
  /// In en, this message translates to:
  /// **'Please enter a valid PayPal.me link'**
  String get pleaseEnterValidPayPalMeLink;

  /// No description provided for @syncFlowIntro.
  ///
  /// In en, this message translates to:
  /// **'Recordings are transferred from your device to this phone and stored locally, then uploaded to Omi\'s server where they\'re transcribed and turned into conversations.'**
  String get syncFlowIntro;

  /// Shown when no device was found after scanning for a while
  ///
  /// In en, this message translates to:
  /// **'Can\'t find your device? Make sure it\'s turned on and close to your phone, then scan again.'**
  String get cantFindDeviceHint;

  /// Empty state message when filter has no results
  ///
  /// In en, this message translates to:
  /// **'Try adjusting your search or filter'**
  String get tryAdjustingFilter;

  /// Connect attempts that never established a connection, within the retained 7-day diagnostics window
  ///
  /// In en, this message translates to:
  /// **'Failed connections (last 7 days)'**
  String get failedConnectionsRecent;

  /// Capture source label when an Omi phone call is being recorded, on the live card (e.g. 'Call · Listening · 3:10'). A noun.
  ///
  /// In en, this message translates to:
  /// **'Call'**
  String get captureSourceCall;

  /// Storage location label for phone
  ///
  /// In en, this message translates to:
  /// **'Phone'**
  String get storageLocationPhone;

  /// How close a voice is to a person: very close.
  ///
  /// In en, this message translates to:
  /// **'Close match'**
  String get voiceMatchClose;

  /// Shown under a change the user undid
  ///
  /// In en, this message translates to:
  /// **'Undone. Omi won’t redo this on its own.'**
  String get reviewChangeUndone;

  /// Group header for tasks without a project
  ///
  /// In en, this message translates to:
  /// **'No project'**
  String get tasksNoProject;

  /// Dialog title warning about app data access
  ///
  /// In en, this message translates to:
  /// **'Data Access Notice'**
  String get dataAccessNotice;

  /// Amount of free on-device storage, e.g. 131 MB free
  ///
  /// In en, this message translates to:
  /// **'{free} free'**
  String deviceStorageFree(String free);

  /// Message shown when task was already exported to a platform
  ///
  /// In en, this message translates to:
  /// **'Already exported to {platform}'**
  String alreadyExportedTo(String platform);

  /// Snackbar shown after a recap was successfully deleted.
  ///
  /// In en, this message translates to:
  /// **'Recap deleted'**
  String get recapDeletedSnackbar;

  /// No description provided for @apiUrlRequired.
  ///
  /// In en, this message translates to:
  /// **'API URL is required'**
  String get apiUrlRequired;

  /// Description for getting Omi Unlimited free by contributing data
  ///
  /// In en, this message translates to:
  /// **'Get Omi Unlimited for free by contributing your data to train AI models.'**
  String get getOmiUnlimitedFree;

  /// Share button label
  ///
  /// In en, this message translates to:
  /// **'Share'**
  String get wrappedShare;

  /// Category label for tasks due tomorrow
  ///
  /// In en, this message translates to:
  /// **'Tomorrow'**
  String get tasksTomorrow;

  /// Switch subtitle when on
  ///
  /// In en, this message translates to:
  /// **'On: they appear in the Omi app as read-only chats.'**
  String get chatAppsShowInAppOn;

  /// Error message when app activation fails, possibly due to incomplete integration setup
  ///
  /// In en, this message translates to:
  /// **'Error activating the app. If this is an integration app, make sure the setup is completed.'**
  String get errorActivatingAppIntegration;

  /// Toggle helper text explaining replies are only spoken when Voice response mode allows it
  ///
  /// In en, this message translates to:
  /// **'Only speaks when Voice response allows it.'**
  String get readChatRepliesAloudDescription;

  /// Placeholder
  ///
  /// In en, this message translates to:
  /// **'Add Due Date'**
  String get addDueDate;

  /// Label for translated text
  ///
  /// In en, this message translates to:
  /// **'translated'**
  String get translated;

  /// Checkbox label to not show confirmation dialog again
  ///
  /// In en, this message translates to:
  /// **'Don\'t ask me again'**
  String get dontAskAgain;

  /// Label for full access API key scope
  ///
  /// In en, this message translates to:
  /// **'Full Access'**
  String get fullAccessScope;

  /// Success message when firmware update is complete
  ///
  /// In en, this message translates to:
  /// **'Firmware Updated'**
  String get firmwareUpdated;

  /// Voice preview output route when using the phone speaker
  ///
  /// In en, this message translates to:
  /// **'Through the phone speaker'**
  String get deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker;

  /// Label for prompt input field
  ///
  /// In en, this message translates to:
  /// **'Prompt'**
  String get prompt;

  /// Label for an edit whose target no longer exists.
  ///
  /// In en, this message translates to:
  /// **'Deleted item'**
  String get dreamReportDeletedItem;

  /// Destructive row title
  ///
  /// In en, this message translates to:
  /// **'Disconnect {app}'**
  String chatAppsDisconnectChannel(String app);

  /// No description provided for @appleHealthDeniedBody.
  ///
  /// In en, this message translates to:
  /// **'Omi doesn\'t have permission to read your Apple Health data. Enable it in iOS Settings → Privacy & Security → Health → Omi.'**
  String get appleHealthDeniedBody;

  /// No description provided for @endsOnDate.
  ///
  /// In en, this message translates to:
  /// **'Ends {date}'**
  String endsOnDate(String date);

  /// Placeholder of the search input in the settings drawer
  ///
  /// In en, this message translates to:
  /// **'Search settings'**
  String get searchSettings;

  /// Pairing description for Neo One device
  ///
  /// In en, this message translates to:
  /// **'Press and hold the power button until the LED blinks. The device will be discoverable.'**
  String get pairingDescNeoOne;

  /// Subtitle for no upcoming meetings state
  ///
  /// In en, this message translates to:
  /// **'Checking the next 7 days'**
  String get checkingNextSevenDays;

  /// Confidence level for a person's voice: the user answered for it at least once. Short label.
  ///
  /// In en, this message translates to:
  /// **'Likely'**
  String get confidenceLikely;

  /// No description provided for @appleHealthFeatureChatTitle.
  ///
  /// In en, this message translates to:
  /// **'Chat about your health'**
  String get appleHealthFeatureChatTitle;

  /// Status when loading audio devices
  ///
  /// In en, this message translates to:
  /// **'Loading devices…'**
  String get loadingDevices;

  /// Hint text for reply text field
  ///
  /// In en, this message translates to:
  /// **'Write something'**
  String get writeSomething;

  /// Top status card: secondary progress line under the phase title.
  ///
  /// In en, this message translates to:
  /// **'{current} of {total}'**
  String syncCardProgressOf(int current, int total);

  /// Error message when Watch app cannot be opened automatically
  ///
  /// In en, this message translates to:
  /// **'Unable to open Apple Watch app. Please manually open the Watch app on your Apple Watch and install Omi from the \"Available Apps\" section.'**
  String get unableToOpenWatchApp;

  /// Section label for edits proposed in preview mode.
  ///
  /// In en, this message translates to:
  /// **'Would fix'**
  String get dreamReportWouldFix;

  /// Double tap action label
  ///
  /// In en, this message translates to:
  /// **'Double Tap'**
  String get doubleTap;

  /// Answer chip on the voice suggestion card that opens a picker to choose who it is (Title Case, one-character ellipsis).
  ///
  /// In en, this message translates to:
  /// **'Someone Else…'**
  String get speakerTagPromptSomeoneElse;

  /// Button to cancel ongoing transfer
  ///
  /// In en, this message translates to:
  /// **'Cancel Transfer'**
  String get cancelTransfer;

  /// No description provided for @capabilityExternalIntegration.
  ///
  /// In en, this message translates to:
  /// **'External Integration'**
  String get capabilityExternalIntegration;

  /// Subtitle of the Custom STT language row when it uses the app's primary language
  ///
  /// In en, this message translates to:
  /// **'Follows your primary language'**
  String get sttLanguageFollowsPrimary;

  /// Default title for cringe moment in collage
  ///
  /// In en, this message translates to:
  /// **'Cringe Moment'**
  String get wrappedCringeMomentTitle;

  /// Status text when sync is complete
  ///
  /// In en, this message translates to:
  /// **'All recordings are synced'**
  String get allRecordingsSynced;

  /// Button
  ///
  /// In en, this message translates to:
  /// **'Confirm'**
  String get reviewConfirm;

  /// Empty state message when no apps are available
  ///
  /// In en, this message translates to:
  /// **'Check back later for new apps'**
  String get checkBackLaterForNewApps;

  /// Bottom navigation label for referral program
  ///
  /// In en, this message translates to:
  /// **'Refer a Friend'**
  String get referAFriend;

  /// Explanation at the top of the clean-up review.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Omi is unsure about this person. Untick them to keep them.} other{Omi is unsure about these {count} people. Most are names misheard from transcripts. Untick anyone you want to keep.}}'**
  String cleanUpLead(int count);

  /// Dialog title asking to make app or persona private
  ///
  /// In en, this message translates to:
  /// **'Make {item} Private?'**
  String makeItemPrivateQuestion(String item);

  /// No description provided for @chatQuotaSubtitle.
  ///
  /// In en, this message translates to:
  /// **'AI chat messages used with Omi this month.'**
  String get chatQuotaSubtitle;

  /// Button to retry failed connection
  ///
  /// In en, this message translates to:
  /// **'Failed? Try Again'**
  String get failedTryAgain;

  /// Dialog title for deleting all files
  ///
  /// In en, this message translates to:
  /// **'Delete All Recordings'**
  String get deleteAllFiles;

  /// Toast shown after an on-device model is downloaded
  ///
  /// In en, this message translates to:
  /// **'Model downloaded'**
  String get onDeviceModelDownloadSuccess;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No changes yet'**
  String get reviewNoChangesTitle;

  /// Tip about using mobile app for audio capture
  ///
  /// In en, this message translates to:
  /// **'Use your mobile app to capture audio'**
  String get useMobileAppToCapture;

  /// No description provided for @setYourName.
  ///
  /// In en, this message translates to:
  /// **'Set Your Name'**
  String get setYourName;

  /// Menu item (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Group by Date'**
  String get tasksGroupByDate;

  /// Device Diagnostics section title for the 7-day connection summary
  ///
  /// In en, this message translates to:
  /// **'Last 7 Days'**
  String get diagnosticsLast7Days;

  /// Tutorial step 3 status chip — device connected (before power-off)
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get deviceOnboardingStatusConnected;

  /// Success message when action item is created
  ///
  /// In en, this message translates to:
  /// **'Task created successfully'**
  String get actionItemCreatedSuccessfully;

  /// Abbreviation for Thursday
  ///
  /// In en, this message translates to:
  /// **'Thu'**
  String get thursdayAbbr;

  /// No description provided for @wifiConfiguration.
  ///
  /// In en, this message translates to:
  /// **'WiFi Configuration'**
  String get wifiConfiguration;

  /// Cancel reason option
  ///
  /// In en, this message translates to:
  /// **'Found an alternative'**
  String get cancelReasonFoundAlternative;

  /// Button label to start processing
  ///
  /// In en, this message translates to:
  /// **'Process'**
  String get process;

  /// Bottom navigation label for help
  ///
  /// In en, this message translates to:
  /// **'Help'**
  String get help;

  /// Confirmation dialog title for firmware rollback
  ///
  /// In en, this message translates to:
  /// **'Roll Back Firmware?'**
  String get rollbackConfirmTitle;

  /// Label for memory visibility selection section
  ///
  /// In en, this message translates to:
  /// **'Visibility'**
  String get visibility;

  /// Evidence row: this person has not appeared in any conversation.
  ///
  /// In en, this message translates to:
  /// **'Not heard in a conversation yet'**
  String get evidenceNotHeard;

  /// Confirmation after reporting message
  ///
  /// In en, this message translates to:
  /// **'Message reported successfully.'**
  String get messageReported;

  /// Empty state title when connected
  ///
  /// In en, this message translates to:
  /// **'✨ Ready to chat!'**
  String get readyToChat;

  /// Hint when no recordings match current filter
  ///
  /// In en, this message translates to:
  /// **'Try a different filter'**
  String get tryDifferentFilter;

  /// HTTP header label
  ///
  /// In en, this message translates to:
  /// **'Header'**
  String get header;

  /// First line of header for best moments card
  ///
  /// In en, this message translates to:
  /// **'Best'**
  String get wrappedBestHeader;

  /// Button that suppresses this memory from future use
  ///
  /// In en, this message translates to:
  /// **'Don\'t Use'**
  String get memoryDontUse;

  /// No description provided for @appStore.
  ///
  /// In en, this message translates to:
  /// **'App Store'**
  String get appStore;

  /// Body of the dialog confirming deletion of one meeting screenshot
  ///
  /// In en, this message translates to:
  /// **'This removes the screenshot from this meeting\'s note. It can\'t be undone.'**
  String get deleteMeetingScreenshotMessage;

  /// No description provided for @categoryShopping.
  ///
  /// In en, this message translates to:
  /// **'Shopping'**
  String get categoryShopping;

  /// Voice response mode: off
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get voiceResponseOff;

  /// Explanation text for why Bluetooth is required
  ///
  /// In en, this message translates to:
  /// **'Omi needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.'**
  String get bluetoothNeeded;

  /// No description provided for @googleCalendarComingSoon.
  ///
  /// In en, this message translates to:
  /// **'Google Calendar integration coming soon!'**
  String get googleCalendarComingSoon;

  /// Max state
  ///
  /// In en, this message translates to:
  /// **'Max'**
  String get max;

  /// No description provided for @homeScreen.
  ///
  /// In en, this message translates to:
  /// **'Home Screen'**
  String get homeScreen;

  /// Step 2; 'Start' is Telegram's own button label
  ///
  /// In en, this message translates to:
  /// **'Tap Start in your chat with Omi'**
  String get chatAppsTelegramStepStart;

  /// Home greeting (large title) for 2 PM to 4 PM; keep it short so the first name fits after it on one line
  ///
  /// In en, this message translates to:
  /// **'Afternoon'**
  String get greetingAfternoon;

  /// Button text to confirm unpair action
  ///
  /// In en, this message translates to:
  /// **'Unpair'**
  String get unpair;

  /// Device Diagnostics weekly verdict when every drop recovered automatically
  ///
  /// In en, this message translates to:
  /// **'Reconnects on its own'**
  String get diagnosticsVerdictReconnects;

  /// No description provided for @macOsCalendar.
  ///
  /// In en, this message translates to:
  /// **'macOS Calendar'**
  String get macOsCalendar;

  /// Onboarding setup checklist step
  ///
  /// In en, this message translates to:
  /// **'Tuning transcription to your language'**
  String get onboardingSetupStepLanguage;

  /// OAuth connector setup instructions for the hosted MCP server
  ///
  /// In en, this message translates to:
  /// **'On claude.ai, add a custom connector and paste the server URL. If Claude asks for an advanced OAuth Client ID, use the value below and leave the secret blank — never use your MCP API key as an OAuth secret.'**
  String get mcpOAuthSetup;

  /// Abbreviation for Wednesday
  ///
  /// In en, this message translates to:
  /// **'Wed'**
  String get wednesdayAbbr;

  /// Dropdown header for audio device selection
  ///
  /// In en, this message translates to:
  /// **'Select Audio Input'**
  String get selectAudioInput;

  /// Message shown when device is disconnected
  ///
  /// In en, this message translates to:
  /// **'Your Omi has been disconnected 😔'**
  String get deviceDisconnectedMessage;

  /// Menu item to reprocess a conversation
  ///
  /// In en, this message translates to:
  /// **'Reprocess Conversation'**
  String get reprocessConversation;

  /// No description provided for @goal.
  ///
  /// In en, this message translates to:
  /// **'GOAL'**
  String get goal;

  /// Merge confirmation message
  ///
  /// In en, this message translates to:
  /// **'This will combine {count} conversations into one. All content will be merged and regenerated.'**
  String mergeConversationsMessage(int count);

  /// No description provided for @everyXSeconds.
  ///
  /// In en, this message translates to:
  /// **'Every x seconds'**
  String get everyXSeconds;

  /// Accessibility label for the lock icon on a chat app row for free users
  ///
  /// In en, this message translates to:
  /// **'Requires Omi Pro'**
  String get chatAppsLocked;

  /// Error message when conversation created webhook URL is invalid in developer settings
  ///
  /// In en, this message translates to:
  /// **'Invalid conversation created webhook URL'**
  String get devModeInvalidConversationCreatedWebhookUrl;

  /// Description for Apple authentication
  ///
  /// In en, this message translates to:
  /// **'Secure authentication via Apple ID'**
  String get secureAuthViaAppleId;

  /// Title shown while connecting to device WiFi
  ///
  /// In en, this message translates to:
  /// **'Connecting to {deviceName}'**
  String connectingToDeviceName(String deviceName);

  /// Listening stat subtitle
  ///
  /// In en, this message translates to:
  /// **'Total time Omi has actively listened.'**
  String get listeningSubtitle;

  /// Live-capture app bar title while both audio and photos are being captured
  ///
  /// In en, this message translates to:
  /// **'Capturing'**
  String get capturing;

  /// No description provided for @enterWifiNetworkName.
  ///
  /// In en, this message translates to:
  /// **'Enter WiFi network name'**
  String get enterWifiNetworkName;

  /// Empty state title when no apps are available
  ///
  /// In en, this message translates to:
  /// **'No apps available'**
  String get noAppsAvailable;

  /// Status text shown while installing firmware
  ///
  /// In en, this message translates to:
  /// **'Installing Firmware'**
  String get installingFirmware;

  /// Button to start transfer to phone
  ///
  /// In en, this message translates to:
  /// **'Transfer to Phone'**
  String get transferToPhone;

  /// Voice response mode setting row title
  ///
  /// In en, this message translates to:
  /// **'Voice Response'**
  String get voiceResponseMode;

  /// Snackbar message for copied text
  ///
  /// In en, this message translates to:
  /// **'✨ Message copied to clipboard'**
  String get messageCopied;

  /// Dialog message when leaving the voice-sample recording mid-recording
  ///
  /// In en, this message translates to:
  /// **'Your voice sample isn’t saved yet. If you leave now, it will be discarded.'**
  String get discardRecordingMessage;

  /// The text message the person sends to Omi. Keep {code} exactly; it is a one-time code
  ///
  /// In en, this message translates to:
  /// **'Hi Omi, link code {code}'**
  String chatAppsIMessageBody(String code);

  /// Error message when Whoop status refresh fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh Whoop connection status.'**
  String get failedToRefreshWhoopStatus;

  /// Message showing user is on annual plan
  ///
  /// In en, this message translates to:
  /// **'You\'re on the Annual Plan'**
  String get youreOnAnnualPlan;

  /// Duration in plural hours
  ///
  /// In en, this message translates to:
  /// **'{count} hours'**
  String timeHoursPlural(int count);

  /// Usage location option: Online
  ///
  /// In en, this message translates to:
  /// **'Online'**
  String get usageOnline;

  /// No description provided for @validPortRequired.
  ///
  /// In en, this message translates to:
  /// **'Valid port is required'**
  String get validPortRequired;

  /// Section title explaining how scoring works
  ///
  /// In en, this message translates to:
  /// **'How it works'**
  String get howItWorks;

  /// No description provided for @viewTemplate.
  ///
  /// In en, this message translates to:
  /// **'View Template'**
  String get viewTemplate;

  /// Run summary when the pass found nothing to change.
  ///
  /// In en, this message translates to:
  /// **'Nothing to fix'**
  String get dreamReportNothingFound;

  /// Stat label on a person's page: total time this person spoke
  ///
  /// In en, this message translates to:
  /// **'Talk time'**
  String get personTalkTime;

  /// Evidence row: Omi has no usable voice sample for this person.
  ///
  /// In en, this message translates to:
  /// **'No voice sample yet'**
  String get evidenceNoVoice;

  /// Checkbox label for making app publicly available
  ///
  /// In en, this message translates to:
  /// **'Make my app public'**
  String get makeMyAppPublic;

  /// Error showing Bluetooth permission status
  ///
  /// In en, this message translates to:
  /// **'Bluetooth permission status: {status}. Please check System Preferences.'**
  String onboardingBluetoothStatusCheckPrefs(String status);

  /// Empty state title when there are no recordings
  ///
  /// In en, this message translates to:
  /// **'No Recordings'**
  String get noRecordings;

  /// Label for monthly chat usage meter
  ///
  /// In en, this message translates to:
  /// **'Chat this month'**
  String get usageChatThisMonth;

  /// Validation error when chat capability selected but no prompt entered
  ///
  /// In en, this message translates to:
  /// **'Please enter a chat prompt for your app'**
  String get addAppEnterChatPrompt;

  /// No description provided for @daysAgo.
  ///
  /// In en, this message translates to:
  /// **'{count} days ago'**
  String daysAgo(int count);

  /// No description provided for @processing.
  ///
  /// In en, this message translates to:
  /// **'Processing'**
  String get processing;

  /// Tutorial step 3 status chip while the device is powering off
  ///
  /// In en, this message translates to:
  /// **'Turning off…'**
  String get deviceOnboardingStatusTurningOff;

  /// newTag label
  ///
  /// In en, this message translates to:
  /// **'NEW'**
  String get newTag;

  /// Description for read tasks permission
  ///
  /// In en, this message translates to:
  /// **'This app can access your tasks.'**
  String get permissionDescReadTasks;

  /// Label
  ///
  /// In en, this message translates to:
  /// **'Time'**
  String get time;

  /// Recording status: recording
  ///
  /// In en, this message translates to:
  /// **'Recording'**
  String get recording;

  /// Question under an audio clip of an unknown speaker
  ///
  /// In en, this message translates to:
  /// **'Who is this?'**
  String get speakerTagPromptWhoIsThis;

  /// No description provided for @chatUsageMessagesNoLimit.
  ///
  /// In en, this message translates to:
  /// **'Chat: {used} messages this month'**
  String chatUsageMessagesNoLimit(String used);

  /// Header for trade-offs section in E2EE dialog
  ///
  /// In en, this message translates to:
  /// **'Important Trade-offs:'**
  String get importantTradeoffs;

  /// Button label
  ///
  /// In en, this message translates to:
  /// **'Make All Memories Public'**
  String get makeAllPublic;

  /// Error description when no speech is detected
  ///
  /// In en, this message translates to:
  /// **'We could not detect any speech. Please make sure to speak for at least 10 seconds and not more than 3 minutes.'**
  String get noSpeechDesc;

  /// Shown under global search results when one kind of result (conversations, recaps, tasks or memories) failed to load
  ///
  /// In en, this message translates to:
  /// **'Some results couldn\'t load'**
  String get searchPartialFailure;

  /// Tab label for the prerecorded conversation transcript
  ///
  /// In en, this message translates to:
  /// **'Prerecorded'**
  String get prerecordedTranscript;

  /// Confirm button label
  ///
  /// In en, this message translates to:
  /// **'Confirm'**
  String get confirm;

  /// No description provided for @statusCalling.
  ///
  /// In en, this message translates to:
  /// **'Calling…'**
  String get statusCalling;

  /// Short label for conversations
  ///
  /// In en, this message translates to:
  /// **'convos'**
  String get wrappedConvos;

  /// Title of the sheet explaining unresolved speaker labels
  ///
  /// In en, this message translates to:
  /// **'About Speaker Labels'**
  String get unresolvedSpeakersTitle;

  /// Hint text for reply input field
  ///
  /// In en, this message translates to:
  /// **'Write your reply…'**
  String get writeYourReply;

  /// Section header above the auto-remove synced copies setting
  ///
  /// In en, this message translates to:
  /// **'Local Copies'**
  String get localCopiesSection;

  /// Text shown when no summary is available yet
  ///
  /// In en, this message translates to:
  /// **'No summary yet'**
  String get noSummaryYet;

  /// Header line for struggle/win cards
  ///
  /// In en, this message translates to:
  /// **'Biggest'**
  String get wrappedBiggestHeader;

  /// Generic error label shown when an operation fails
  ///
  /// In en, this message translates to:
  /// **'Error'**
  String get error;

  /// No description provided for @deviceWillRestart.
  ///
  /// In en, this message translates to:
  /// **'Your device will restart.'**
  String get deviceWillRestart;

  /// Consent message explaining how user data will be stored and used
  ///
  /// In en, this message translates to:
  /// **'By continuing, your conversations, recordings, and personal information will be securely stored on our servers. Your audio recordings and transcripts are processed by third-party AI services — Deepgram for transcription and OpenAI for analysis — to provide you with AI-powered insights and enable all app features.'**
  String get consentDataMessage;

  /// No description provided for @connectMacOsCalendar.
  ///
  /// In en, this message translates to:
  /// **'Connect your local macOS calendar'**
  String get connectMacOsCalendar;

  /// The phone's microphone as a capture source: live page title ('Listening · Phone mic') and the first row of the 'Record with' sheet.
  ///
  /// In en, this message translates to:
  /// **'Phone mic'**
  String get captureSourcePhoneMic;

  /// Status text when setup is completed
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get setupCompleted;

  /// Description explaining need to install Omi app on watch
  ///
  /// In en, this message translates to:
  /// **'To use your Apple Watch with Omi, you need to install the Omi app on your watch first.'**
  String get installOmiOnAppleWatchDescription;

  /// Shortcut to toggle control bar visibility
  ///
  /// In en, this message translates to:
  /// **'Toggle Control Bar'**
  String get toggleControlBar;

  /// Error when Bluetooth permission is denied on macOS
  ///
  /// In en, this message translates to:
  /// **'Bluetooth permission denied. Please grant permission in System Preferences.'**
  String get onboardingBluetoothDeniedSystemPrefs;

  /// Snackbar message when sync is cancelled
  ///
  /// In en, this message translates to:
  /// **'Sync cancelled'**
  String get syncCancelled;

  /// Firmware update step title about disconnecting USB
  ///
  /// In en, this message translates to:
  /// **'Disconnect USB'**
  String get firmwareDisconnectUsb;

  /// Button text to process/summarize the conversation immediately
  ///
  /// In en, this message translates to:
  /// **'Process Now'**
  String get processNow;

  /// Error toast when refreshing an app's manifest without a known app id
  ///
  /// In en, this message translates to:
  /// **'App ID not found'**
  String get appIdNotFoundError;

  /// Menu item to edit due date
  ///
  /// In en, this message translates to:
  /// **'Edit Due Date'**
  String get editDueDate;

  /// Screen-reader label for the Home tab in the bottom navigation bar.
  ///
  /// In en, this message translates to:
  /// **'Home'**
  String get home;

  /// No description provided for @tasksOverdue.
  ///
  /// In en, this message translates to:
  /// **'Overdue'**
  String get tasksOverdue;

  /// Import job status - completed
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get statusCompleted;

  /// OmiGlass OTA starting
  ///
  /// In en, this message translates to:
  /// **'Starting update…'**
  String get otaStarting;

  /// April month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Apr'**
  String get monthApr;

  /// Empty state message of a conversation's Tasks tab
  ///
  /// In en, this message translates to:
  /// **'Tasks from this conversation will appear here.'**
  String get conversationTasksEmptyMessage;

  /// Consent step: signs out and returns to sign-in
  ///
  /// In en, this message translates to:
  /// **'Use a Different Account'**
  String get useDifferentAccount;

  /// Dismiss reason chip (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Not Useful'**
  String get reviewReasonNotUseful;

  /// Display name for anonymous users
  ///
  /// In en, this message translates to:
  /// **'Anonymous User'**
  String get anonymousUser;

  /// View plans description
  ///
  /// In en, this message translates to:
  /// **'Manage your subscription and see usage stats'**
  String get viewPlansDescription;

  /// No description provided for @invalidJson.
  ///
  /// In en, this message translates to:
  /// **'Invalid JSON: {error}'**
  String invalidJson(String error);

  /// Dialog title for delete confirmation
  ///
  /// In en, this message translates to:
  /// **'Delete Task'**
  String get deleteActionItem;

  /// Button text to confirm cancellation
  ///
  /// In en, this message translates to:
  /// **'Confirm Cancellation'**
  String get confirmCancellation;

  /// Hint text for tap to delete action
  ///
  /// In en, this message translates to:
  /// **'Tap to delete'**
  String get tapToDelete;

  /// No description provided for @onTheCallEnterThisCode.
  ///
  /// In en, this message translates to:
  /// **'On the call, enter this code'**
  String get onTheCallEnterThisCode;

  /// Title for the stable firmware rollback page
  ///
  /// In en, this message translates to:
  /// **'Stable Firmware'**
  String get stableFirmware;

  /// Section title in app submission: which events start an external integration
  ///
  /// In en, this message translates to:
  /// **'Trigger Events'**
  String get triggerEvents;

  /// Label of an on/off switch to remember voices of people the user names
  ///
  /// In en, this message translates to:
  /// **'Remember voices of people you name'**
  String get speakerTagPromptSaveVoicesTitle;

  /// Snackbar message after synced files deleted
  ///
  /// In en, this message translates to:
  /// **'Synced recordings deleted'**
  String get syncedFilesDeleted;

  /// Description of cloud storage in sync info sheet
  ///
  /// In en, this message translates to:
  /// **'Once uploaded, your recordings are processed and transcribed. Conversations will be available within a minute.'**
  String get cloudStorageDesc;

  /// Error message when folder update fails
  ///
  /// In en, this message translates to:
  /// **'Failed to update folder'**
  String get failedToUpdateFolder;

  /// Run summary: number of proposed fixes and of questions/tasks it would suggest.
  ///
  /// In en, this message translates to:
  /// **'{fixes, plural, =1{1 fix} other{{fixes} fixes}} · {asks, plural, =1{1 suggestion} other{{asks} suggestions}}'**
  String dreamReportFound(int fixes, int asks);

  /// Fallback text for unknown export platform
  ///
  /// In en, this message translates to:
  /// **'another platform'**
  String get anotherPlatform;

  /// Uppercase label for top phrases tile in collage
  ///
  /// In en, this message translates to:
  /// **'TOP PHRASES'**
  String get wrappedTopPhrasesLabel;

  /// Warning message about app data access in confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app'**
  String get dataAccessWarning;

  /// Message shown during OAuth flow
  ///
  /// In en, this message translates to:
  /// **'Please complete authentication in your browser. Once done, return to the app.'**
  String get pleaseCompleteAuthentication;

  /// Daily summary toggle title
  ///
  /// In en, this message translates to:
  /// **'Daily Summary'**
  String get dailySummaryTitle;

  /// No description provided for @managePeople.
  ///
  /// In en, this message translates to:
  /// **'Manage People'**
  String get managePeople;

  /// Empty state body.
  ///
  /// In en, this message translates to:
  /// **'Dream looks at what changed in your account about once an hour.'**
  String get dreamReportEmptyBody;

  /// Error when payment settings cannot open
  ///
  /// In en, this message translates to:
  /// **'Could not open payment settings. Please try again.'**
  String get couldNotOpenPaymentSettings;

  /// Title for dialog when location services are off
  ///
  /// In en, this message translates to:
  /// **'Location Service Disabled'**
  String get locationServiceDisabled;

  /// Understanding stat title
  ///
  /// In en, this message translates to:
  /// **'Understanding'**
  String get understanding;

  /// Snackbar shown when the recap delete API fails.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t delete the recap. Try again later.'**
  String get recapDeleteFailed;

  /// No description provided for @deleteKnowledgeGraphQuestion.
  ///
  /// In en, this message translates to:
  /// **'Delete Knowledge Graph?'**
  String get deleteKnowledgeGraphQuestion;

  /// Default context for buddy
  ///
  /// In en, this message translates to:
  /// **'Your buddy!'**
  String get wrappedYourBuddy;

  /// Fallback title for an untitled chat
  ///
  /// In en, this message translates to:
  /// **'Chat in {app}'**
  String chatAppsChatIn(String app);

  /// Dialog message about speech duration requirements
  ///
  /// In en, this message translates to:
  /// **'Please make sure you speak for at least 5 seconds and not more than 90.'**
  String get speechDurationDescription;

  /// Dismiss reason chip (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Already Done'**
  String get reviewReasonAlreadyDone;

  /// No description provided for @phoneSetupStep2Title.
  ///
  /// In en, this message translates to:
  /// **'Enter a verification code'**
  String get phoneSetupStep2Title;

  /// No description provided for @tasksClearCompleted.
  ///
  /// In en, this message translates to:
  /// **'Clear Completed'**
  String get tasksClearCompleted;

  /// Status text while scanning for Bluetooth devices
  ///
  /// In en, this message translates to:
  /// **'Searching for devices'**
  String get searchingForDevices;

  /// No description provided for @siriIndexSettingDescription.
  ///
  /// In en, this message translates to:
  /// **'Allow Siri to find your conversations, memories, and tasks on this device. Turning this off removes them from Apple search.'**
  String get siriIndexSettingDescription;

  /// Menu item to mark action item as incomplete
  ///
  /// In en, this message translates to:
  /// **'Mark Incomplete'**
  String get markIncomplete;

  /// Error message when Bluetooth permission is needed
  ///
  /// In en, this message translates to:
  /// **'Bluetooth permission is required to connect to your device.'**
  String get onboardingBluetoothRequired;

  /// Search bar placeholder text
  ///
  /// In en, this message translates to:
  /// **'Search 1500+ Apps'**
  String get searchAppsPlaceholder;

  /// Validation message when name field is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter a name'**
  String get pleaseEnterName;

  /// Info about payment method being charged
  ///
  /// In en, this message translates to:
  /// **'Your existing payment method will be charged automatically when your monthly plan ends'**
  String get paymentMethodCharged;

  /// Success message after making all memories public
  ///
  /// In en, this message translates to:
  /// **'All memories are now public'**
  String get allMemoriesAreNowPublic;

  /// A task's due date, e.g. 'Due Sep 23, 2026'
  ///
  /// In en, this message translates to:
  /// **'Due {date}'**
  String taskDueDate(String date);

  /// Subtitle of the 'Record with phone instead' option.
  ///
  /// In en, this message translates to:
  /// **'Pendant pauses until you finish'**
  String get pendantPausesUntilYouFinish;

  /// No description provided for @failedToAuthorize.
  ///
  /// In en, this message translates to:
  /// **'Failed to authorize. Please try again.'**
  String get failedToAuthorize;

  /// Notification title shown when conversations are merged successfully
  ///
  /// In en, this message translates to:
  /// **'Conversations Merged Successfully'**
  String get mergeConversationsSuccessTitle;

  /// Filter chip on the People list: people whose voice Omi has not learned yet
  ///
  /// In en, this message translates to:
  /// **'Needs Voice'**
  String get peopleFilterNeedsVoice;

  /// Instruction to start system audio recording
  ///
  /// In en, this message translates to:
  /// **'Click to begin recording system audio'**
  String get clickToBeginRecordingSystemAudio;

  /// No description provided for @fairUseStageRestrict.
  ///
  /// In en, this message translates to:
  /// **'Restricted'**
  String get fairUseStageRestrict;

  /// Accessibility label of the down arrow in conversation search
  ///
  /// In en, this message translates to:
  /// **'Next result'**
  String get nextResult;

  /// Name of the system Contacts app
  ///
  /// In en, this message translates to:
  /// **'Contacts'**
  String get chatAppsContactsApp;

  /// No description provided for @categoryEmotionalSupport.
  ///
  /// In en, this message translates to:
  /// **'Emotional Support'**
  String get categoryEmotionalSupport;

  /// First line of header for top days card
  ///
  /// In en, this message translates to:
  /// **'Your'**
  String get wrappedYourHeader;

  /// Subtitle of the Phone call option in the 'Your pendant is listening' sheet.
  ///
  /// In en, this message translates to:
  /// **'Pendant pauses during the call'**
  String get pendantPausesDuringCall;

  /// Empty state title when no conversations on selected date
  ///
  /// In en, this message translates to:
  /// **'No conversations on {date}'**
  String noConversationsOnDate(String date);

  /// Suggested first question in a new chat
  ///
  /// In en, this message translates to:
  /// **'What did I do yesterday?'**
  String get chatStarterYesterday;

  /// Button that opens a correction form
  ///
  /// In en, this message translates to:
  /// **'Not right?'**
  String get entityNotRight;

  /// No description provided for @failedToCreateShareLink.
  ///
  /// In en, this message translates to:
  /// **'Failed to create share link'**
  String get failedToCreateShareLink;

  /// Sync button label
  ///
  /// In en, this message translates to:
  /// **'Sync'**
  String get sync;

  /// Mic gain description: Max
  ///
  /// In en, this message translates to:
  /// **'Maximum - use with caution'**
  String get micGainDescMax;

  /// Generic "none" option label
  ///
  /// In en, this message translates to:
  /// **'None'**
  String get sttNone;

  /// Note about the one-time code
  ///
  /// In en, this message translates to:
  /// **'The code works once and expires in 10 minutes.'**
  String get chatAppsCodeNote;

  /// Success message when AI-generated app is created
  ///
  /// In en, this message translates to:
  /// **'App created successfully!'**
  String get aiGenAppCreatedSuccessfully;

  /// No description provided for @lastNEvents.
  ///
  /// In en, this message translates to:
  /// **'Last {count} events'**
  String lastNEvents(int count);

  /// No description provided for @phoneDeleteButton.
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get phoneDeleteButton;

  /// Label for system audio
  ///
  /// In en, this message translates to:
  /// **'System'**
  String get systemAudio;

  /// Share text for memory graph
  ///
  /// In en, this message translates to:
  /// **'Check out my memory graph!'**
  String get checkOutMyMemoryGraph;

  /// Feedback title when cancel reason is battery drain
  ///
  /// In en, this message translates to:
  /// **'Tell us about the battery issues'**
  String get feedbackTitleBatteryDrain;

  /// No description provided for @startCallRecording.
  ///
  /// In en, this message translates to:
  /// **'Start call recording'**
  String get startCallRecording;

  /// Info about monthly plan continuing
  ///
  /// In en, this message translates to:
  /// **'Your current monthly plan will continue until the end of your billing period'**
  String get monthlyPlanContinues;

  /// No description provided for @syncStepUploadDesc.
  ///
  /// In en, this message translates to:
  /// **'Your recording is sent to Omi\'s server'**
  String get syncStepUploadDesc;

  /// Shown before an OmiGlass update starts
  ///
  /// In en, this message translates to:
  /// **'Keep your device on and nearby during the update, and don\'t close the app.'**
  String get otaKeepNearby;

  /// Button text to update PayPal details
  ///
  /// In en, this message translates to:
  /// **'Update PayPal Details'**
  String get updatePayPalDetails;

  /// Link text for Terms of Use
  ///
  /// In en, this message translates to:
  /// **'Terms of Use'**
  String get termsOfUse;

  /// Title shown when API key is successfully created
  ///
  /// In en, this message translates to:
  /// **'API Key Created!'**
  String get apiKeyCreated;

  /// Title of the idle voice answer preview card
  ///
  /// In en, this message translates to:
  /// **'Hear your last answer'**
  String get deviceOnboardingVoiceReplyPreviewIdle;

  /// Star ongoing conversation action
  ///
  /// In en, this message translates to:
  /// **'Star Ongoing Conversation'**
  String get starOngoing;

  /// Warning about large model sizes
  ///
  /// In en, this message translates to:
  /// **'This model is large and may crash the app or run very slowly on mobile devices.\n\n\"small\" or \"base\" is recommended.'**
  String get largeModelWarning;

  /// Title for language selection
  ///
  /// In en, this message translates to:
  /// **'Select Language'**
  String get selectLanguage;

  /// Profession option: Executive
  ///
  /// In en, this message translates to:
  /// **'Executive'**
  String get professionExecutive;

  /// Error when the selected import file is over the upload size limit
  ///
  /// In en, this message translates to:
  /// **'This file is too large to import.'**
  String get importFileTooLarge;

  /// Title of the pop-up when this app version is no longer supported and must be updated
  ///
  /// In en, this message translates to:
  /// **'Update required'**
  String get updateRequiredTitle;

  /// No description provided for @syncStepBackedUp.
  ///
  /// In en, this message translates to:
  /// **'Conversation ready'**
  String get syncStepBackedUp;

  /// Button text to open Watch app on iPhone
  ///
  /// In en, this message translates to:
  /// **'Open Watch App'**
  String get openWatchApp;

  /// Label for key name input field
  ///
  /// In en, this message translates to:
  /// **'KEY NAME'**
  String get keyNameLabel;

  /// Snackbar shown when a bulk export completes for all items
  ///
  /// In en, this message translates to:
  /// **'Exported {count} to {platform}'**
  String bulkExportSuccess(int count, String platform);

  /// Error when subscription cannot be processed
  ///
  /// In en, this message translates to:
  /// **'Could not process subscription. Please try again.'**
  String get couldNotProcessSubscription;

  /// Loading message shown while processing voice profile
  ///
  /// In en, this message translates to:
  /// **'Memorizing your voice…'**
  String get memorizingYourVoice;

  /// No description provided for @processingAudio.
  ///
  /// In en, this message translates to:
  /// **'Processing Audio'**
  String get processingAudio;

  /// Label prompting user to sync their recordings
  ///
  /// In en, this message translates to:
  /// **'Sync your recordings'**
  String get syncYourRecordings;

  /// Reset keyboard shortcut to default value
  ///
  /// In en, this message translates to:
  /// **'Reset to default'**
  String get resetToDefault;

  /// Menu item to delete a conversation
  ///
  /// In en, this message translates to:
  /// **'Delete Conversation'**
  String get deleteConversation;

  /// No description provided for @flashCustomFirmwareDescription.
  ///
  /// In en, this message translates to:
  /// **'Flash custom firmware builds'**
  String get flashCustomFirmwareDescription;

  /// No description provided for @deviceUpToDate.
  ///
  /// In en, this message translates to:
  /// **'Your device is up to date'**
  String get deviceUpToDate;

  /// No description provided for @raybanMetaMusicPauseNote.
  ///
  /// In en, this message translates to:
  /// **'Music on your phone pauses while the glasses microphone is in use.'**
  String get raybanMetaMusicPauseNote;

  /// No description provided for @appleHealthNotAvailable.
  ///
  /// In en, this message translates to:
  /// **'Apple Health is not available on this device'**
  String get appleHealthNotAvailable;

  /// Label for hints section with dynamic text
  ///
  /// In en, this message translates to:
  /// **'Hints: {text}'**
  String hints(String text);

  /// Tab label for cloud provider option
  ///
  /// In en, this message translates to:
  /// **'Cloud Provider'**
  String get cloudProvider;

  /// File option: choose any file type subtitle
  ///
  /// In en, this message translates to:
  /// **'Choose any file type'**
  String get chooseAnyFileType;

  /// Reset button label
  ///
  /// In en, this message translates to:
  /// **'Reset'**
  String get reset;

  /// No description provided for @automaticallyCreateNewPerson.
  ///
  /// In en, this message translates to:
  /// **'Automatically create a new person when a name is detected in the transcript.'**
  String get automaticallyCreateNewPerson;

  /// No description provided for @timeout2Minutes.
  ///
  /// In en, this message translates to:
  /// **'2 minutes'**
  String get timeout2Minutes;

  /// Dialog title when creating a new memory
  ///
  /// In en, this message translates to:
  /// **'✨ New Memory'**
  String get newMemory;

  /// Footnote under the list of chat apps
  ///
  /// In en, this message translates to:
  /// **'More apps are coming.'**
  String get chatAppsMoreComing;

  /// Short user-facing error when the knowledge graph request is non-200; must not include the response body
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load knowledge graph'**
  String get couldNotLoadKnowledgeGraph;

  /// Settings switch explanation for periodic speaker tagging prompts
  ///
  /// In en, this message translates to:
  /// **'Once in a while, Omi asks who was speaking in your recent conversations'**
  String get voiceSettingsAskToTagSubtitle;

  /// Developer section
  ///
  /// In en, this message translates to:
  /// **'Developer'**
  String get developer;

  /// Empty state title when not connected
  ///
  /// In en, this message translates to:
  /// **'🌐 Connection needed'**
  String get connectionNeeded;

  /// Settings group: feedback, help center, what's new and the app version
  ///
  /// In en, this message translates to:
  /// **'Help & About'**
  String get helpAndAbout;

  /// Category label for tasks without a deadline
  ///
  /// In en, this message translates to:
  /// **'No Deadline'**
  String get tasksNoDeadline;

  /// First part of data protection text
  ///
  /// In en, this message translates to:
  /// **'Your data is protected and governed by our '**
  String get yourDataIsProtected;

  /// Dialog title for confirming deletion
  ///
  /// In en, this message translates to:
  /// **'Confirm Deletion'**
  String get confirmDeletion;

  /// Label above people ranked by how close their voice is to the clip.
  ///
  /// In en, this message translates to:
  /// **'Closest voices'**
  String get speakerTagPromptClosestVoices;

  /// Description for request template selector
  ///
  /// In en, this message translates to:
  /// **'Quickly populate with a known providers request format'**
  String get quicklyPopulateRequest;

  /// Button/section label for exporting transcript
  ///
  /// In en, this message translates to:
  /// **'Export Transcript'**
  String get exportTranscript;

  /// No description provided for @resetsSoon.
  ///
  /// In en, this message translates to:
  /// **'Resets soon'**
  String get resetsSoon;

  /// No description provided for @showPhoneCallButtonTitle.
  ///
  /// In en, this message translates to:
  /// **'Show Phone Call Button'**
  String get showPhoneCallButtonTitle;

  /// Default title for most intense day
  ///
  /// In en, this message translates to:
  /// **'A Challenge'**
  String get wrappedAChallenge;

  /// Tooltip for revoke button
  ///
  /// In en, this message translates to:
  /// **'Revoke key'**
  String get revokeKey;

  /// No description provided for @dailyRecaps.
  ///
  /// In en, this message translates to:
  /// **'Daily Recaps'**
  String get dailyRecaps;

  /// Shown while the server is still processing the conversation (transcript, summary).
  ///
  /// In en, this message translates to:
  /// **'Processing conversation…'**
  String get processingConversationProgress;

  /// No description provided for @freeMinutesMonth.
  ///
  /// In en, this message translates to:
  /// **'300 free minutes/month included. Unlimited with '**
  String get freeMinutesMonth;

  /// Message prompting to download Whisper model
  ///
  /// In en, this message translates to:
  /// **'Please download a Whisper model before saving.'**
  String get downloadWhisperModel;

  /// Empty state text for filtered categories
  ///
  /// In en, this message translates to:
  /// **'No memories in these categories'**
  String get noMemoriesInCategories;

  /// No description provided for @checkingNextDays.
  ///
  /// In en, this message translates to:
  /// **'Checking next 30 days'**
  String get checkingNextDays;

  /// Button text to create and submit a new app
  ///
  /// In en, this message translates to:
  /// **'Create and submit a new app'**
  String get createAndSubmitNewApp;

  /// Title of a tip
  ///
  /// In en, this message translates to:
  /// **'In the meantime'**
  String get chatAppsInTheMeantime;

  /// Title on delete-account flow reason step
  ///
  /// In en, this message translates to:
  /// **'Why are you leaving?'**
  String get deleteFlowReasonTitle;

  /// No description provided for @tasksSelectAll.
  ///
  /// In en, this message translates to:
  /// **'Select All'**
  String get tasksSelectAll;

  /// Label of the webhook URL field when submitting an app with external integration
  ///
  /// In en, this message translates to:
  /// **'Webhook URL'**
  String get webhookUrl;

  /// Label for selected option
  ///
  /// In en, this message translates to:
  /// **'Selected'**
  String get selected;

  /// Warning about battery drain
  ///
  /// In en, this message translates to:
  /// **'Battery drain will increase significantly.'**
  String get batteryDrainIncrease;

  /// Section label for edits that were applied.
  ///
  /// In en, this message translates to:
  /// **'Fixed'**
  String get dreamReportFixed;

  /// Error message when ClickUp authentication fails
  ///
  /// In en, this message translates to:
  /// **'Failed to connect to ClickUp. Please try again.'**
  String get failedToConnectClickUpRetry;

  /// Server URL label
  ///
  /// In en, this message translates to:
  /// **'Server URL'**
  String get serverUrl;

  /// Label for starred folder tab
  ///
  /// In en, this message translates to:
  /// **'Starred'**
  String get starred;

  /// Error when the audio clip fails to load
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t play this clip'**
  String get speakerTagPromptClipUnavailable;

  /// Feedback subtitle for found alternative
  ///
  /// In en, this message translates to:
  /// **'We\'d love to learn what caught your eye.'**
  String get feedbackSubtitleFoundAlternative;

  /// Toggle in device settings that controls whether the mobile app responds to Omi button actions
  ///
  /// In en, this message translates to:
  /// **'Omi Button Actions'**
  String get omiButtonActions;

  /// Error description for invalid recording duration
  ///
  /// In en, this message translates to:
  /// **'Please make sure you speak for at least 5 seconds and not more than 90.'**
  String get invalidRecordingDesc;

  /// Title for the API switch confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'Switch API Environment'**
  String get switchApiConfirmTitle;

  /// No description provided for @gattError.
  ///
  /// In en, this message translates to:
  /// **'GATT error ({code})'**
  String gattError(String code);

  /// Tooltip and accessibility label of the icon-only button that regenerates the app icon on the AI app generator preview card
  ///
  /// In en, this message translates to:
  /// **'Regenerate icon'**
  String get aiGenRegenerateIcon;

  /// Snackbar shown when the user taps Export but no third-party task integration is connected
  ///
  /// In en, this message translates to:
  /// **'Connect a task app in Settings to export'**
  String get connectTaskAppToExport;

  /// No description provided for @firmwareFlashed.
  ///
  /// In en, this message translates to:
  /// **'Firmware flashed'**
  String get firmwareFlashed;

  /// No description provided for @addPerson.
  ///
  /// In en, this message translates to:
  /// **'Add Person'**
  String get addPerson;

  /// Subtitle for cancel consequences page
  ///
  /// In en, this message translates to:
  /// **'We highly recommend exploring your other options instead of canceling.'**
  String get cancelConsequencesSubtitle;

  /// Success message when transcript is copied
  ///
  /// In en, this message translates to:
  /// **'Transcript copied to clipboard'**
  String get transcriptCopiedToClipboard;

  /// November month abbreviation
  ///
  /// In en, this message translates to:
  /// **'Nov'**
  String get monthNov;

  /// Success message when switched to on-device transcription
  ///
  /// In en, this message translates to:
  /// **'Switched to on-device transcription'**
  String get switchedToOnDevice;

  /// Snackbar shown when phone-mic recording auto-switches to local (batch) capture because the device is offline
  ///
  /// In en, this message translates to:
  /// **'No connection — recording locally. It will be transcribed when you\'re back online.'**
  String get phoneMicOfflineFallbackMessage;

  /// No description provided for @scopeUserConversations.
  ///
  /// In en, this message translates to:
  /// **'User Conversations'**
  String get scopeUserConversations;

  /// No description provided for @otherAppResults.
  ///
  /// In en, this message translates to:
  /// **'Other App Results'**
  String get otherAppResults;

  /// Button to create a new one-time code
  ///
  /// In en, this message translates to:
  /// **'Get New Code'**
  String get chatAppsGetNewCode;

  /// Title for dialog when background location is denied
  ///
  /// In en, this message translates to:
  /// **'Background Location Access Denied'**
  String get backgroundLocationDenied;

  /// No description provided for @syncFailureFootnote.
  ///
  /// In en, this message translates to:
  /// **'If processing fails, your recording is retried automatically on the next sync.'**
  String get syncFailureFootnote;

  /// No description provided for @checkingNext7Days.
  ///
  /// In en, this message translates to:
  /// **'Checking the next 7 days'**
  String get checkingNext7Days;

  /// Feature title for monthly payouts
  ///
  /// In en, this message translates to:
  /// **'Monthly payouts'**
  String get monthlyPayouts;

  /// Hint text for language search
  ///
  /// In en, this message translates to:
  /// **'Search language by name or code'**
  String get searchLanguageHint;

  /// Button to dismiss explanation
  ///
  /// In en, this message translates to:
  /// **'Got It'**
  String get gotIt;

  /// Validation error when app name is empty
  ///
  /// In en, this message translates to:
  /// **'Please enter app name'**
  String get pleaseEnterAppName;

  /// No description provided for @newConversations.
  ///
  /// In en, this message translates to:
  /// **'New Conversations'**
  String get newConversations;

  /// Link text to learn more about training
  ///
  /// In en, this message translates to:
  /// **'Learn more at omi.me/training'**
  String get learnMoreAtOmiTraining;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'Open tasks'**
  String get entityOpenTasks;

  /// No description provided for @summary.
  ///
  /// In en, this message translates to:
  /// **'Summary'**
  String get summary;

  /// Button label after copying link
  ///
  /// In en, this message translates to:
  /// **'Copied'**
  String get copied;

  /// Quick reason chip: processing was delayed or stuck.
  ///
  /// In en, this message translates to:
  /// **'Delayed or stuck'**
  String get feedbackReasonRecordingDelayedOrStuck;

  /// No description provided for @taskIntegrations.
  ///
  /// In en, this message translates to:
  /// **'Task Integrations'**
  String get taskIntegrations;

  /// No description provided for @tailoredConversationSummaries.
  ///
  /// In en, this message translates to:
  /// **'Tailored Conversation Summaries'**
  String get tailoredConversationSummaries;

  /// Button text to skip current question
  ///
  /// In en, this message translates to:
  /// **'Skip this question'**
  String get skipThisQuestion;

  /// Hint text for optional folder description field
  ///
  /// In en, this message translates to:
  /// **'Description (optional)'**
  String get descriptionOptional;

  /// About section
  ///
  /// In en, this message translates to:
  /// **'About'**
  String get about;

  /// Button text when multiple contacts selected
  ///
  /// In en, this message translates to:
  /// **'Share with {count} contacts'**
  String shareWithContactsCount(int count);

  /// Title of the dialog shown when leaving an editor with unsaved changes
  ///
  /// In en, this message translates to:
  /// **'Discard Changes?'**
  String get discardChangesTitle;

  /// Experimental feature name
  ///
  /// In en, this message translates to:
  /// **'Transcription Diagnostics'**
  String get transcriptionDiagnostics;

  /// No description provided for @syncStatusFileUnavailable.
  ///
  /// In en, this message translates to:
  /// **'File unavailable'**
  String get syncStatusFileUnavailable;

  /// Title for the create new app page
  ///
  /// In en, this message translates to:
  /// **'Create New App'**
  String get createNewApp;

  /// No description provided for @verifiedHoursAgo.
  ///
  /// In en, this message translates to:
  /// **'Verified {hours}h ago'**
  String verifiedHoursAgo(int hours);

  /// No description provided for @chatLimitReachedTitle.
  ///
  /// In en, this message translates to:
  /// **'Chat Limit Reached'**
  String get chatLimitReachedTitle;

  /// Text shared when sharing wrapped images
  ///
  /// In en, this message translates to:
  /// **'My 2025, remembered by Omi ✨ omi.me/wrapped'**
  String get wrappedShareText;

  /// Reconnect count within the retained 7-day diagnostics window; headline value on Device Diagnostics
  ///
  /// In en, this message translates to:
  /// **'Reconnections (last 7 days)'**
  String get reconnectionsRecent;

  /// App access section title
  ///
  /// In en, this message translates to:
  /// **'App Access'**
  String get appAccess;

  /// Label for description field
  ///
  /// In en, this message translates to:
  /// **'Description'**
  String get description;

  /// No description provided for @phoneFreeCallsRemainingWithMax.
  ///
  /// In en, this message translates to:
  /// **'{remaining} of {limit} free calls remaining this month · up to {minutes} min each'**
  String phoneFreeCallsRemainingWithMax(int remaining, int limit, int minutes);

  /// Confirmation dialog title for clearing all memories
  ///
  /// In en, this message translates to:
  /// **'Clear Omi\'s Memory'**
  String get clearOmisMemory;

  /// Button/section label for exporting summary
  ///
  /// In en, this message translates to:
  /// **'Export Summary'**
  String get exportSummary;

  /// Button label to install an app
  ///
  /// In en, this message translates to:
  /// **'Install'**
  String get install;

  /// No description provided for @syncStepBackedUpDesc.
  ///
  /// In en, this message translates to:
  /// **'Find it under Conversations'**
  String get syncStepBackedUpDesc;

  /// Info about local processing
  ///
  /// In en, this message translates to:
  /// **'Audio is processed locally. Works offline, more private, but uses more battery.'**
  String get localProcessingInfo;

  /// Payment setup modal description
  ///
  /// In en, this message translates to:
  /// **'Connect Stripe or PayPal to receive payments for your app.'**
  String get connectStripeOrPayPal;

  /// Second line of header for best moments card
  ///
  /// In en, this message translates to:
  /// **'Moments'**
  String get wrappedMomentsHeader;

  /// System language option
  ///
  /// In en, this message translates to:
  /// **'System Default'**
  String get systemDefault;

  /// Button that dismisses the 'Your pendant is listening' sheet and keeps the pendant recording.
  ///
  /// In en, this message translates to:
  /// **'Keep using pendant'**
  String get keepUsingPendant;

  /// Error message when fetching supported countries fails
  ///
  /// In en, this message translates to:
  /// **'Failed to fetch supported countries. Please try again later.'**
  String get paymentFailedToFetchCountries;

  /// Mic gain description: Low
  ///
  /// In en, this message translates to:
  /// **'Very quiet - for loud environments'**
  String get micGainDescLow;

  /// No description provided for @errorUpdatingConversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Error updating conversation title'**
  String get errorUpdatingConversationTitle;

  /// Duration in singular second
  ///
  /// In en, this message translates to:
  /// **'{count} sec'**
  String timeSecsSingular(int count);

  /// Compact duration in hours
  ///
  /// In en, this message translates to:
  /// **'{count}h'**
  String timeCompactHours(int count);

  /// Subtitle describing app page functionality
  ///
  /// In en, this message translates to:
  /// **'Browse, install, and create apps'**
  String get browseInstallCreateApps;

  /// No description provided for @reddit.
  ///
  /// In en, this message translates to:
  /// **'Reddit'**
  String get reddit;

  /// Action sheet option to choose a file
  ///
  /// In en, this message translates to:
  /// **'Choose File'**
  String get chooseFile;

  /// Conversation header people chip: the first named participant and how many others took part, e.g. 'David + 3 others'
  ///
  /// In en, this message translates to:
  /// **'{name} + {count, plural, =1{1 other} few{{count} others} many{{count} others} other{{count} others}}'**
  String participantsSummary(String name, int count);

  /// Title during Stripe connection process
  ///
  /// In en, this message translates to:
  /// **'Connecting your Stripe account'**
  String get connectingYourStripeAccount;

  /// Cancel reason option
  ///
  /// In en, this message translates to:
  /// **'Missing features'**
  String get cancelReasonMissingFeatures;

  /// No description provided for @chatTitle.
  ///
  /// In en, this message translates to:
  /// **'Chat'**
  String get chatTitle;

  /// Button/chip: ask to be told when WhatsApp is available
  ///
  /// In en, this message translates to:
  /// **'Notify Me'**
  String get chatAppsNotifyMe;

  /// App access section description
  ///
  /// In en, this message translates to:
  /// **'The following apps can access your data. Tap on an app to manage its permissions.'**
  String get appAccessDesc;

  /// No description provided for @captureDisplayDetectionFailed.
  ///
  /// In en, this message translates to:
  /// **'Display detection failed. Recording stopped.'**
  String get captureDisplayDetectionFailed;

  /// No description provided for @recapRegeneratedSnackbar.
  ///
  /// In en, this message translates to:
  /// **'Recap regenerated'**
  String get recapRegeneratedSnackbar;

  /// Undo toast after answering the voice card with That's Me.
  ///
  /// In en, this message translates to:
  /// **'Labeled as you'**
  String get speakerTagPromptLabeledYouToast;

  /// No description provided for @categoryFinancial.
  ///
  /// In en, this message translates to:
  /// **'Financial'**
  String get categoryFinancial;

  /// Label: the message text is already filled in
  ///
  /// In en, this message translates to:
  /// **'Prefilled'**
  String get chatAppsPrefilled;

  /// Message when conversation has no summary
  ///
  /// In en, this message translates to:
  /// **'No summary available\nfor this conversation.'**
  String get noSummaryForConversation;

  /// Section title for AI prompt configuration
  ///
  /// In en, this message translates to:
  /// **'AI Prompts'**
  String get aiPrompts;

  /// Button on an app row that opens the app's page (for apps that need payment or setup before they can be enabled)
  ///
  /// In en, this message translates to:
  /// **'View'**
  String get view;

  /// Info message explaining data is always encrypted
  ///
  /// In en, this message translates to:
  /// **'Regardless of the level, your data is always encrypted at rest and in transit.'**
  String get dataAlwaysEncrypted;

  /// Message when item is copied to clipboard
  ///
  /// In en, this message translates to:
  /// **'{item} copied to clipboard'**
  String itemCopiedToClipboard(String item);

  /// No description provided for @currentPlan.
  ///
  /// In en, this message translates to:
  /// **'Current'**
  String get currentPlan;

  /// Phone calls upsell feature 1
  ///
  /// In en, this message translates to:
  /// **'Real-time transcription of every call'**
  String get phoneCallsUpsellFeature1;

  /// Title for low battery notification
  ///
  /// In en, this message translates to:
  /// **'Low Battery Alert'**
  String get lowBatteryAlertTitle;

  /// No description provided for @enterConversationTitle.
  ///
  /// In en, this message translates to:
  /// **'Enter conversation title…'**
  String get enterConversationTitle;

  /// No description provided for @pasteJsonConfig.
  ///
  /// In en, this message translates to:
  /// **'Paste your JSON configuration below:'**
  String get pasteJsonConfig;

  /// Shown when the daily manual-run allowance is used up.
  ///
  /// In en, this message translates to:
  /// **'No manual runs left today'**
  String get dreamReportRunLimit;

  /// Message explaining how translation works and where to change language settings
  ///
  /// In en, this message translates to:
  /// **'Omi translates conversations into your primary language. Update it anytime in Settings → Profiles.'**
  String get translationNoticeMessage;

  /// Error message when icon regeneration fails
  ///
  /// In en, this message translates to:
  /// **'Failed to regenerate icon'**
  String get aiGenFailedToRegenerateIcon;

  /// Pairing description for Bee device
  ///
  /// In en, this message translates to:
  /// **'Press the button 5 times continuously. The light will start blinking blue and green.'**
  String get pairingDescBee;

  /// Button that accepts tasks someone shared
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Add 1 Task} other{Add {count} Tasks}}'**
  String sharedTasksAddButton(int count);

  /// Error message when saving PayPal details fails
  ///
  /// In en, this message translates to:
  /// **'Failed to save PayPal details. Please try again later.'**
  String get paymentFailedToSavePaypal;

  /// No description provided for @couldNotLoadCheckout.
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t load the checkout page. Check your connection and try again.'**
  String get couldNotLoadCheckout;

  /// No description provided for @capabilitySummary.
  ///
  /// In en, this message translates to:
  /// **'Summary'**
  String get capabilitySummary;

  /// Placeholder for country selector
  ///
  /// In en, this message translates to:
  /// **'Select your country'**
  String get selectYourCountry;

  /// Live-capture WAL indicator while unsynced audio is uploading
  ///
  /// In en, this message translates to:
  /// **'Uploading {duration} of audio for transcription…'**
  String uploadingAudioForTranscription(String duration);

  /// Error when sharing URL fails
  ///
  /// In en, this message translates to:
  /// **'Conversation URL could not be shared.'**
  String get conversationUrlCouldNotBeShared;

  /// OmiGlass OTA failed to start
  ///
  /// In en, this message translates to:
  /// **'Couldn\'t start the update. Check the Wi-Fi name and password, then try again.'**
  String get otaStartFailed;

  /// No description provided for @triggersWhenAudioBytesReceived.
  ///
  /// In en, this message translates to:
  /// **'Triggers when audio bytes are received.'**
  String get triggersWhenAudioBytesReceived;

  /// Title text for shareable image
  ///
  /// In en, this message translates to:
  /// **'My 2025'**
  String get wrappedMy2025;

  /// Compact duration in seconds
  ///
  /// In en, this message translates to:
  /// **'{count}s'**
  String timeCompactSecs(int count);

  /// Action in the linked calendar event sheet: email the meeting attendees
  ///
  /// In en, this message translates to:
  /// **'Share with Attendees'**
  String get shareWithAttendees;

  /// Tip in sync info sheet
  ///
  /// In en, this message translates to:
  /// **'Recordings sync automatically — no action needed.'**
  String get recordingsSyncAutomatically;

  /// No description provided for @whereDidYouHearAboutOmi.
  ///
  /// In en, this message translates to:
  /// **'How did you find us?'**
  String get whereDidYouHearAboutOmi;

  /// No description provided for @captureMicrophonePermissionInSystemPreferences.
  ///
  /// In en, this message translates to:
  /// **'Grant microphone permission in System Preferences'**
  String get captureMicrophonePermissionInSystemPreferences;

  /// Live-capture WAL indicator when auto-retries are exhausted and a manual retry is available
  ///
  /// In en, this message translates to:
  /// **'Upload failed — {duration} of audio kept on your phone. Tap to retry.'**
  String audioUploadFailedTapRetry(String duration);

  /// Subtitle for the Transcribe Later option in the recording mode picker
  ///
  /// In en, this message translates to:
  /// **'Save audio now and transcribe whenever you want.'**
  String get captureModeLaterDescription;

  /// Empty state title when no one is unsure (Title Case).
  ///
  /// In en, this message translates to:
  /// **'Nothing to Clean Up'**
  String get cleanUpNothingTitle;

  /// Accessibility label for the delete control on a person row
  ///
  /// In en, this message translates to:
  /// **'Delete person'**
  String get deletePersonLabel;

  /// Label for attached files section
  ///
  /// In en, this message translates to:
  /// **'📎 Attached Files'**
  String get attachedFiles;

  /// Title for editing an existing goal
  ///
  /// In en, this message translates to:
  /// **'Edit Goal'**
  String get editGoal;

  /// Description for debug logs purpose
  ///
  /// In en, this message translates to:
  /// **'Helps diagnose issues'**
  String get helpsDiagnoseIssues;

  /// Snackbar shown when the bulk delete request fails and the local list is restored
  ///
  /// In en, this message translates to:
  /// **'Could not delete tasks. Please try again.'**
  String get bulkDeleteFailed;

  /// Error toast when manually refreshing an MCP app's manifest fails
  ///
  /// In en, this message translates to:
  /// **'Failed to refresh manifest'**
  String get manifestRefreshFailed;

  /// Search input placeholder text
  ///
  /// In en, this message translates to:
  /// **'Search'**
  String get searchPlaceholder;

  /// Label of the button on an app's page that opens the owner's options (visibility, edit, delete)
  ///
  /// In en, this message translates to:
  /// **'App options'**
  String get appOptions;

  /// Shown with a progress bar while the open conversation is reprocessed.
  ///
  /// In en, this message translates to:
  /// **'Reprocessing conversation…'**
  String get reprocessingConversationProgress;

  /// Section label: facts with their sources
  ///
  /// In en, this message translates to:
  /// **'What Omi knows'**
  String get entityWhatOmiKnows;

  /// Hint text showing how many minutes of silence before auto-summary
  ///
  /// In en, this message translates to:
  /// **'Conversation is summarized after {minutes} minute{suffix} of no speech.'**
  String conversationSummarizedAfterMinutes(int minutes, String suffix);

  /// No description provided for @permissionRevokedMessage.
  ///
  /// In en, this message translates to:
  /// **'Do you want us to remove all your existing recordings too?'**
  String get permissionRevokedMessage;

  /// No description provided for @phoneNumberCallerIdHint.
  ///
  /// In en, this message translates to:
  /// **'Once verified, this becomes your caller ID'**
  String get phoneNumberCallerIdHint;

  /// Label above the code; address is Omi's phone number
  ///
  /// In en, this message translates to:
  /// **'Didn\'t open? Text this to {address}'**
  String chatAppsTextThisTo(String address);

  /// Section header for upcoming meetings in calendar
  ///
  /// In en, this message translates to:
  /// **'Upcoming Meetings'**
  String get upcomingMeetings;

  /// Status when preparing audio capture
  ///
  /// In en, this message translates to:
  /// **'Preparing system audio capture'**
  String get preparingSystemAudioCapture;

  /// How many changed items are queued for the agent to look at.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{No changes waiting} =1{1 change waiting} other{{count} changes waiting}}'**
  String dreamReportQueued(int count);

  /// Shown in place of a chat reply that failed, next to Try Again
  ///
  /// In en, this message translates to:
  /// **'Omi couldn\'t reply. Check your connection and try again.'**
  String get chatReplyFailed;

  /// Migration message when no data needs to be migrated
  ///
  /// In en, this message translates to:
  /// **'No data to migrate. Finalizing…'**
  String get noDataToMigrateFinalizing;

  /// No description provided for @accessibility.
  ///
  /// In en, this message translates to:
  /// **'Accessibility'**
  String get accessibility;

  /// Title prompting user to open Omi on Apple Watch
  ///
  /// In en, this message translates to:
  /// **'Open Omi on your\nApple Watch'**
  String get openOmiOnAppleWatch;

  /// Default title for most productive day
  ///
  /// In en, this message translates to:
  /// **'Getting It Done'**
  String get wrappedGettingItDone;

  /// Tab label for raw data content
  ///
  /// In en, this message translates to:
  /// **'Raw Data'**
  String get rawData;

  /// Error when passwords do not match
  ///
  /// In en, this message translates to:
  /// **'Passwords do not match'**
  String get passwordsDoNotMatch;

  /// No description provided for @errorInstallingApp.
  ///
  /// In en, this message translates to:
  /// **'Error installing {appName}: {error}'**
  String errorInstallingApp(String appName, String error);

  /// Dialog title for deleting an item
  ///
  /// In en, this message translates to:
  /// **'Delete \"{name}\"'**
  String deleteQuoted(String name);

  /// Badge text for top phrases card
  ///
  /// In en, this message translates to:
  /// **'Top 5 Phrases'**
  String get wrappedTopFivePhrases;

  /// Tutorial step 3 hint shown if the device has not turned off after a while
  ///
  /// In en, this message translates to:
  /// **'Hold the button firmly until the light turns off'**
  String get deviceOnboardingHoldButtonHint;

  /// Section title for app capabilities
  ///
  /// In en, this message translates to:
  /// **'Capabilities'**
  String get capabilities;

  /// No description provided for @useMcpApiKey.
  ///
  /// In en, this message translates to:
  /// **'Use your MCP API key'**
  String get useMcpApiKey;

  /// Message shown when task integration is not yet available
  ///
  /// In en, this message translates to:
  /// **'{serviceName} integration coming soon'**
  String serviceIntegrationComingSoon(String serviceName);

  /// Word Struggle in Wrapped template
  ///
  /// In en, this message translates to:
  /// **'Struggle'**
  String get wrappedStruggle;

  /// Error showing notification permission status
  ///
  /// In en, this message translates to:
  /// **'Notification permission status: {status}. Please check System Preferences.'**
  String onboardingNotificationStatusCheckPrefs(String status);

  /// Heading of the strip of meeting screenshots in a conversation summary
  ///
  /// In en, this message translates to:
  /// **'What was on screen'**
  String get meetingScreenshotsTitle;

  /// No description provided for @verifiedMinutesAgo.
  ///
  /// In en, this message translates to:
  /// **'Verified {minutes}m ago'**
  String verifiedMinutesAgo(int minutes);

  /// Title for the permissions interstitial screen shown when permissions are missing
  ///
  /// In en, this message translates to:
  /// **'Permissions Required'**
  String get permissionsRequired;

  /// Answer button to skip this question
  ///
  /// In en, this message translates to:
  /// **'Not sure'**
  String get speakerTagPromptNotSure;

  /// Label for current value field
  ///
  /// In en, this message translates to:
  /// **'Current'**
  String get current;

  /// No description provided for @improveConnectionAction.
  ///
  /// In en, this message translates to:
  /// **'Got It'**
  String get improveConnectionAction;

  /// Profile page title
  ///
  /// In en, this message translates to:
  /// **'Profile'**
  String get profile;

  /// No description provided for @audioPlaybackFailed.
  ///
  /// In en, this message translates to:
  /// **'Unable to play audio. The file may be corrupted or missing.'**
  String get audioPlaybackFailed;

  /// No description provided for @billingYearly.
  ///
  /// In en, this message translates to:
  /// **'Yearly'**
  String get billingYearly;

  /// Warning about battery usage
  ///
  /// In en, this message translates to:
  /// **'Battery usage will be higher than cloud transcription.'**
  String get batteryUsageHigher;

  /// Label for permissions section
  ///
  /// In en, this message translates to:
  /// **'PERMISSIONS'**
  String get permissionsLabel;

  /// No description provided for @enhanceTranscriptAccuracy.
  ///
  /// In en, this message translates to:
  /// **'Enhance Transcript Accuracy'**
  String get enhanceTranscriptAccuracy;

  /// Status label when payment method is connected
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get connectedStatus;

  /// Error message when microphone permission is denied
  ///
  /// In en, this message translates to:
  /// **'Microphone permission denied. Please grant permission in System Preferences > Privacy & Security > Microphone.'**
  String get microphonePermissionDenied;

  /// Toast body when a Whisper model is downloaded successfully
  ///
  /// In en, this message translates to:
  /// **'Whisper model downloaded successfully'**
  String get onDeviceModelDownloadSuccessDesc;

  /// Storage location label for Limitless Pendant
  ///
  /// In en, this message translates to:
  /// **'Limitless Pendant'**
  String get storageLocationLimitlessPendant;

  /// Shown when the one-time Telegram link expired
  ///
  /// In en, this message translates to:
  /// **'That link expired. Tap Open Telegram for a new one.'**
  String get chatAppsLinkExpired;

  /// Live capture status: the speech endpoint is unreachable and audio is kept on the phone
  ///
  /// In en, this message translates to:
  /// **'Offline, buffering'**
  String get captureOfflineBuffering;

  /// Error message shown when network request fails
  ///
  /// In en, this message translates to:
  /// **'Please check your internet connection and try again'**
  String get pleaseCheckInternetConnection;

  /// Label for today score in breakdown
  ///
  /// In en, this message translates to:
  /// **'Today\'s Score'**
  String get todaysScore;

  /// Toast after a reprocess finished and replaced the conversation.
  ///
  /// In en, this message translates to:
  /// **'Conversation updated'**
  String get conversationReprocessed;

  /// Loading duration indicator
  ///
  /// In en, this message translates to:
  /// **'Loading duration…'**
  String get loadingDuration;

  /// Message when no summary is available
  ///
  /// In en, this message translates to:
  /// **'No summary'**
  String get noSummary;

  /// No description provided for @raybanMetaMicrophoneReady.
  ///
  /// In en, this message translates to:
  /// **'Microphone ready'**
  String get raybanMetaMicrophoneReady;

  /// No description provided for @applyFilters.
  ///
  /// In en, this message translates to:
  /// **'Apply Filters'**
  String get applyFilters;

  /// Placeholder text for app description input
  ///
  /// In en, this message translates to:
  /// **'My Awesome App is a great app that does amazing things. It is the best app ever!'**
  String get appDescriptionPlaceholder;

  /// Message of the dialog that confirms cancelling an app subscription
  ///
  /// In en, this message translates to:
  /// **'You\'ll keep access until the end of your current billing period.'**
  String get cancelSubscriptionKeepAccessMessage;

  /// Dialog title for editing review
  ///
  /// In en, this message translates to:
  /// **'Edit Your Review'**
  String get editYourReview;

  /// Title for the Action Items page
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get actionItemsTitle;

  /// No description provided for @raybanMetaAudioOnlyTitle.
  ///
  /// In en, this message translates to:
  /// **'Ray-Ban Meta audio-only mode'**
  String get raybanMetaAudioOnlyTitle;

  /// Button: the speaker is someone not listed (Title Case)
  ///
  /// In en, this message translates to:
  /// **'Someone Else…'**
  String get reviewSomeoneElse;

  /// Message shown to beta testers
  ///
  /// In en, this message translates to:
  /// **'You are a beta tester for this app. It is not public yet. It will be public once approved.'**
  String get betaTesterMessage;

  /// Recipient line of the message preview; address is Omi's phone number
  ///
  /// In en, this message translates to:
  /// **'To: Omi · {address}'**
  String chatAppsIMessageTo(String address);

  /// No description provided for @comingSoon.
  ///
  /// In en, this message translates to:
  /// **'Coming Soon'**
  String get comingSoon;

  /// Confirmation dialog message for firmware rollback
  ///
  /// In en, this message translates to:
  /// **'This will replace your current firmware with the latest stable version ({version}). Your device will restart after the update.'**
  String rollbackConfirmMessage(String version);

  /// Terms of Service link text
  ///
  /// In en, this message translates to:
  /// **'Terms of Service'**
  String get termsOfService;

  /// Default value when obsession not found
  ///
  /// In en, this message translates to:
  /// **'Not mentioned'**
  String get wrappedNotMentioned;

  /// Title for device disconnected notification
  ///
  /// In en, this message translates to:
  /// **'Your Omi Device Disconnected'**
  String get deviceDisconnectedNotificationTitle;

  /// Explains how to choose the glasses microphone and the Bluetooth HFP music tradeoff
  ///
  /// In en, this message translates to:
  /// **'Select the Bluetooth microphone for your glasses. Music pauses while Omi uses it.'**
  String get rayBanMetaMicPickerDescription;

  /// Eyebrow label on a chat question card block
  ///
  /// In en, this message translates to:
  /// **'Question'**
  String get chatBlockQuestion;

  /// Success message when Todoist OAuth completes
  ///
  /// In en, this message translates to:
  /// **'Successfully connected to Todoist!'**
  String get successfullyConnectedTodoist;

  /// Stored voice readiness only; no guarantee of a queued learning job.
  ///
  /// In en, this message translates to:
  /// **'{status, select, ready{Voice ready for recognition} saved_sample_awaiting_embedding{Sample saved; voice processing still needed} not_learned{Voice not learned} other{Voice status unknown}}'**
  String voiceRecognitionStatus(String status);

  /// Row shown in the tag-speaker sheet when no existing person matches the search query
  ///
  /// In en, this message translates to:
  /// **'Add \"{query}\" as a new person'**
  String addQueryAsNewPerson(String query);

  /// Reason line under a person's name: automatic voice matches the user confirmed by hand.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{You confirmed 1 automatic label} other{You confirmed {count} automatic labels}}'**
  String confidenceReasonAutoConfirmed(int count);

  /// No description provided for @recordAudioConversations.
  ///
  /// In en, this message translates to:
  /// **'Record audio conversations'**
  String get recordAudioConversations;

  /// Warning message when API key is created
  ///
  /// In en, this message translates to:
  /// **'Save this key now! You won\'t be able to see it again.'**
  String get saveKeyWarning;

  /// Button text to save edited memory
  ///
  /// In en, this message translates to:
  /// **'Save Changes'**
  String get saveChanges;

  /// Relative speed indicator: slower
  ///
  /// In en, this message translates to:
  /// **'Slower'**
  String get sttModelSlower;

  /// OmiGlass OTA status
  ///
  /// In en, this message translates to:
  /// **'The firmware download failed. Check the Wi-Fi connection and try again.'**
  String get otaDownloadFailed;

  /// Accessibility label for the check mark on the recording currently open
  ///
  /// In en, this message translates to:
  /// **'You\'re viewing this recording'**
  String get captureRecordingViewing;

  /// No description provided for @resetFilters.
  ///
  /// In en, this message translates to:
  /// **'Reset Filters'**
  String get resetFilters;

  /// Settings switch explanation for remembering voices of people the user names
  ///
  /// In en, this message translates to:
  /// **'When you name someone, Omi keeps a short voice sample so it can recognize them next time'**
  String get voiceSettingsSaveOthersSubtitle;

  /// No description provided for @iveDoneThis.
  ///
  /// In en, this message translates to:
  /// **'I\'ve Done This'**
  String get iveDoneThis;

  /// Title for sync info bottom sheet
  ///
  /// In en, this message translates to:
  /// **'How syncing works'**
  String get howSyncingWorks;

  /// Home's greeting with the reader's first name after it, when it fits one line
  ///
  /// In en, this message translates to:
  /// **'{greeting}, {name}'**
  String greetingWithName(String greeting, String name);

  /// Header counter: questions left to answer today
  ///
  /// In en, this message translates to:
  /// **'{count} left'**
  String reviewRemaining(int count);

  /// Quick reason chip: the recording is missing audio.
  ///
  /// In en, this message translates to:
  /// **'Missing audio'**
  String get feedbackReasonRecordingMissingAudio;

  /// Title for the category selection modal
  ///
  /// In en, this message translates to:
  /// **'App Category'**
  String get appCategoryModalTitle;

  /// Capability label for push to talk feature
  ///
  /// In en, this message translates to:
  /// **'Push to Talk'**
  String get pushToTalk;

  /// Message when no API keys exist
  ///
  /// In en, this message translates to:
  /// **'No API keys yet'**
  String get noApiKeysYet;

  /// No description provided for @minLabel.
  ///
  /// In en, this message translates to:
  /// **'{count} min'**
  String minLabel(int count);

  /// Number of ratings an app has, under its name in the store
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 rating} other{{count} ratings}}'**
  String appRatingCount(int count);

  /// Label for food obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'FOOD'**
  String get wrappedFood;

  /// Migration time remaining is about a minute
  ///
  /// In en, this message translates to:
  /// **'About a minute remaining'**
  String get aboutAMinuteRemaining;

  /// No description provided for @clearLogs.
  ///
  /// In en, this message translates to:
  /// **'Clear logs'**
  String get clearLogs;

  /// Label for book obsession in Wrapped
  ///
  /// In en, this message translates to:
  /// **'BOOK'**
  String get wrappedBook;

  /// Subtitle for the phone-call option in the record-options sheet
  ///
  /// In en, this message translates to:
  /// **'Record a call with live transcription'**
  String get phoneCallSubtitle;

  /// Title of the confirm dialog for deleting several selected conversations
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{Delete 1 Conversation?} other{Delete {count} Conversations?}}'**
  String deleteConversationsTitle(int count);

  /// Tooltip for delete selected
  ///
  /// In en, this message translates to:
  /// **'Delete selected'**
  String get deleteSelected;

  /// Error message when knowledge graph deletion fails
  ///
  /// In en, this message translates to:
  /// **'Failed to delete graph: {error}'**
  String failedToDeleteGraph(String error);

  /// Intro text for setup questions page
  ///
  /// In en, this message translates to:
  /// **'Help us improve Omi by answering a few questions.  🫶 💜'**
  String get setupQuestionsIntro;

  /// Label for memory category selection section
  ///
  /// In en, this message translates to:
  /// **'Category'**
  String get category;

  /// No description provided for @timeout30MinutesDesc.
  ///
  /// In en, this message translates to:
  /// **'End conversation after 30 minutes of silence'**
  String get timeout30MinutesDesc;

  /// Undo toast after deleting a goal
  ///
  /// In en, this message translates to:
  /// **'Goal deleted'**
  String get goalDeleted;

  /// Conversation display setting
  ///
  /// In en, this message translates to:
  /// **'Conversation Display'**
  String get conversationDisplay;

  /// No description provided for @conversationNoSummaryYet.
  ///
  /// In en, this message translates to:
  /// **'This conversation doesn\'t have a summary yet.'**
  String get conversationNoSummaryYet;

  /// Lowercase plural of chat for migration item type
  ///
  /// In en, this message translates to:
  /// **'chats'**
  String get chatsLowercase;

  /// Dialog title asking to clear chat
  ///
  /// In en, this message translates to:
  /// **'Clear Chat?'**
  String get clearChatQuestion;

  /// Title for sign in page
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get signInTitle;

  /// Loading text for knowledge graph
  ///
  /// In en, this message translates to:
  /// **'Loading Knowledge Graph…'**
  String get loadingKnowledgeGraph;

  /// Experimental feature name
  ///
  /// In en, this message translates to:
  /// **'Goal Tracker'**
  String get goalTracker;

  /// Error message when command key is not pressed for shortcut
  ///
  /// In en, this message translates to:
  /// **'⌘ required'**
  String get commandRequired;

  /// Status text when a permission is enabled
  ///
  /// In en, this message translates to:
  /// **'Enabled'**
  String get permissionEnabled;

  /// Button text to submit review
  ///
  /// In en, this message translates to:
  /// **'Submit Review'**
  String get submitReview;

  /// No description provided for @chatUsageCost.
  ///
  /// In en, this message translates to:
  /// **'Chat: \${used} / \${limit} used this month'**
  String chatUsageCost(String used, String limit);

  /// Destructive button that throws away unsaved edits
  ///
  /// In en, this message translates to:
  /// **'Discard'**
  String get discard;

  /// How many scheduled agent passes ran today out of the daily limit.
  ///
  /// In en, this message translates to:
  /// **'{count} of {limit} passes today'**
  String dreamReportPasses(int count, int limit);

  /// Feature: unlock infinite memory
  ///
  /// In en, this message translates to:
  /// **'Unlimited memories'**
  String get unlockOmiInfiniteMemory;

  /// Error when trying to select Persona alongside other capabilities
  ///
  /// In en, this message translates to:
  /// **'Persona cannot be selected with other capabilities'**
  String get addAppPersonaConflictWithCapabilities;

  /// Title for cancel subscription reason page
  ///
  /// In en, this message translates to:
  /// **'Why are you canceling?'**
  String get whyAreYouCanceling;

  /// Title when permission has been requested
  ///
  /// In en, this message translates to:
  /// **'Permission Requested!'**
  String get permissionRequestedExclaim;

  /// Action on a chat memory link block
  ///
  /// In en, this message translates to:
  /// **'Open in Memories'**
  String get chatBlockOpenInMemories;

  /// Shows number of processed objects out of total during migration
  ///
  /// In en, this message translates to:
  /// **'{processed} / {total} objects'**
  String objectsCount(String processed, String total);

  /// Dialog title for delete confirmation
  ///
  /// In en, this message translates to:
  /// **'Delete Task'**
  String get deleteActionItemTitle;

  /// Confirm button: roll the firmware back to the stable version
  ///
  /// In en, this message translates to:
  /// **'Roll Back'**
  String get rollBack;

  /// Small all-caps plan tag
  ///
  /// In en, this message translates to:
  /// **'OMI PRO'**
  String get chatAppsOmiPro;

  /// No description provided for @disconnectFromAppDesc.
  ///
  /// In en, this message translates to:
  /// **'This will remove your {appName} authentication. You\'ll need to reconnect to use it again.'**
  String disconnectFromAppDesc(String appName);

  /// Label for the size of an on-device transcription model
  ///
  /// In en, this message translates to:
  /// **'Model Size'**
  String get onDeviceModelSize;

  /// No description provided for @tagSpeaker.
  ///
  /// In en, this message translates to:
  /// **'Tag Speaker {speakerId}'**
  String tagSpeaker(int speakerId);

  /// No description provided for @couldNotOpenUrl.
  ///
  /// In en, this message translates to:
  /// **'Could not open URL. Please try again.'**
  String get couldNotOpenUrl;

  /// Indicator shown when a conversation is newly created
  ///
  /// In en, this message translates to:
  /// **'New'**
  String get conversationNewIndicator;

  /// Dialog message when speech recording is too short
  ///
  /// In en, this message translates to:
  /// **'There is not enough speech detected. Please speak more and try again.'**
  String get notEnoughSpeechDescription;

  /// No description provided for @liveRssiOverTime.
  ///
  /// In en, this message translates to:
  /// **'Live RSSI over time'**
  String get liveRssiOverTime;

  /// Usage location option: Everywhere
  ///
  /// In en, this message translates to:
  /// **'Everywhere'**
  String get usageEverywhere;

  /// Number of conversations created
  ///
  /// In en, this message translates to:
  /// **'{count} conversations'**
  String nConversations(int count);

  /// Label under conversations count
  ///
  /// In en, this message translates to:
  /// **'conversations'**
  String get wrappedConversationsLabel;

  /// Plan and Usage period selector
  ///
  /// In en, this message translates to:
  /// **'Year'**
  String get usageYear;

  /// Message when search returns no results
  ///
  /// In en, this message translates to:
  /// **'No contacts match your search'**
  String get noContactsMatchSearch;

  /// Snackbar message after bulk delete
  ///
  /// In en, this message translates to:
  /// **'{count} task{s} deleted'**
  String itemsDeletedResult(int count, String s);

  /// Snackbar message when item marked incomplete
  ///
  /// In en, this message translates to:
  /// **'Task marked as incomplete'**
  String get actionItemMarkedIncomplete;

  /// Button label to start an action
  ///
  /// In en, this message translates to:
  /// **'Start'**
  String get start;

  /// Row title for a discarded conversation, with its length (e.g. 'Discarded · 12s')
  ///
  /// In en, this message translates to:
  /// **'Discarded · {duration}'**
  String discardedConversationTitle(String duration);

  /// Success message when logs cleared
  ///
  /// In en, this message translates to:
  /// **'Debug logs cleared'**
  String get debugLogsCleared;

  /// Status when preparing to capture
  ///
  /// In en, this message translates to:
  /// **'Preparing audio capture'**
  String get preparingAudioCapture;

  /// Section header for available payment methods
  ///
  /// In en, this message translates to:
  /// **'Available Payment Methods'**
  String get availablePaymentMethods;

  /// Delete reason option
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get deleteReasonOther;

  /// Title for account cutover migration-maintenance blocking screen
  ///
  /// In en, this message translates to:
  /// **'Migration in Progress'**
  String get accountCutoverMigrationInProgressTitle;

  /// No description provided for @connectedKnowledgeData.
  ///
  /// In en, this message translates to:
  /// **'Connected Knowledge Data'**
  String get connectedKnowledgeData;

  /// Label for the most fun day in memorable days
  ///
  /// In en, this message translates to:
  /// **'Most Fun'**
  String get wrappedMostFunDay;

  /// Error when accessibility permission is needed
  ///
  /// In en, this message translates to:
  /// **'Accessibility permission is required for detecting browser meetings.'**
  String get onboardingAccessibilityRequired;

  /// Top-bar button to enter selection mode on the action items page
  ///
  /// In en, this message translates to:
  /// **'Select Multiple'**
  String get selectActionItems;

  /// Body for the API switch confirmation dialog
  ///
  /// In en, this message translates to:
  /// **'Switch to {environment}? You will need to close and reopen the app for changes to take effect.'**
  String switchApiConfirmBody(String environment);

  /// Whisper model size: large
  ///
  /// In en, this message translates to:
  /// **'Large'**
  String get whisperModelSizeLarge;

  /// Label for current firmware version
  ///
  /// In en, this message translates to:
  /// **'Current Version'**
  String get currentVersion;

  /// Title of the banner in the app store that opens the AI app generator
  ///
  /// In en, this message translates to:
  /// **'Build an app with AI in one tap'**
  String get aiAppGeneratorBannerTitle;

  /// Error state when available Bluetooth HFP inputs cannot be read
  ///
  /// In en, this message translates to:
  /// **'Bluetooth microphones could not be loaded. Check that Bluetooth is on, then try again.'**
  String get rayBanMetaMicPickerLoadError;

  /// Placeholder text when no pricing option is selected
  ///
  /// In en, this message translates to:
  /// **'None Selected'**
  String get noneSelected;

  /// Footnote under a summary the app maintains
  ///
  /// In en, this message translates to:
  /// **'Kept current by Omi'**
  String get entityKeptCurrent;

  /// Message showing migration progress between protection levels
  ///
  /// In en, this message translates to:
  /// **'Migrating from {source} to {target}'**
  String migratingFromTo(String source, String target);

  /// Description for notification frequency control
  ///
  /// In en, this message translates to:
  /// **'Control how often Omi sends you proactive notifications.'**
  String get controlNotificationFrequency;

  /// No description provided for @connectionUptime.
  ///
  /// In en, this message translates to:
  /// **'Uptime'**
  String get connectionUptime;

  /// Label for the category field
  ///
  /// In en, this message translates to:
  /// **'Category'**
  String get categoryLabel;

  /// Section title for app description
  ///
  /// In en, this message translates to:
  /// **'About the App'**
  String get aboutTheApp;

  /// Plans sheet subtitle prompting a free user to pick a paid plan
  ///
  /// In en, this message translates to:
  /// **'Choose the plan that fits you.'**
  String get planSheetChooseYourPlan;

  /// Migration is almost complete
  ///
  /// In en, this message translates to:
  /// **'Almost done…'**
  String get almostDone;

  /// Empty state description for tasks page
  ///
  /// In en, this message translates to:
  /// **'Tasks from your conversations will appear here.\nClick Create to add one manually.'**
  String get tasksFromConversationsWillAppear;

  /// Stat label on a person's page: most recent conversation date
  ///
  /// In en, this message translates to:
  /// **'Last heard'**
  String get personLastHeard;

  /// No description provided for @durationThreshold.
  ///
  /// In en, this message translates to:
  /// **'Duration Threshold'**
  String get durationThreshold;

  /// No description provided for @transcriptionServiceDiagnosticStatus.
  ///
  /// In en, this message translates to:
  /// **'Transcription service diagnostic status'**
  String get transcriptionServiceDiagnosticStatus;

  /// No description provided for @triggersWhenNewTranscriptReceived.
  ///
  /// In en, this message translates to:
  /// **'Triggers when a new transcript is received.'**
  String get triggersWhenNewTranscriptReceived;

  /// About page title
  ///
  /// In en, this message translates to:
  /// **'About Omi'**
  String get aboutOmi;

  /// People identification setting
  ///
  /// In en, this message translates to:
  /// **'Identifying Others'**
  String get identifyingOthers;

  /// No description provided for @phoneCallsSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Make calls with real-time transcription'**
  String get phoneCallsSubtitle;

  /// No description provided for @creatingYourApp.
  ///
  /// In en, this message translates to:
  /// **'Creating your app…'**
  String get creatingYourApp;

  /// Migration start message when analyzing data
  ///
  /// In en, this message translates to:
  /// **'Analyzing your data…'**
  String get analyzingYourData;
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
        'be',
        'bg',
        'bn',
        'bs',
        'ca',
        'cs',
        'da',
        'de',
        'el',
        'en',
        'es',
        'et',
        'fa',
        'fi',
        'fr',
        'he',
        'hi',
        'hr',
        'hu',
        'id',
        'it',
        'ja',
        'kn',
        'ko',
        'lt',
        'lv',
        'mk',
        'mr',
        'ms',
        'nl',
        'no',
        'pl',
        'pt',
        'ro',
        'ru',
        'sk',
        'sl',
        'sr',
        'sv',
        'ta',
        'te',
        'th',
        'tl',
        'tr',
        'uk',
        'ur',
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
    case 'be':
      return AppLocalizationsBe();
    case 'bg':
      return AppLocalizationsBg();
    case 'bn':
      return AppLocalizationsBn();
    case 'bs':
      return AppLocalizationsBs();
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
    case 'fa':
      return AppLocalizationsFa();
    case 'fi':
      return AppLocalizationsFi();
    case 'fr':
      return AppLocalizationsFr();
    case 'he':
      return AppLocalizationsHe();
    case 'hi':
      return AppLocalizationsHi();
    case 'hr':
      return AppLocalizationsHr();
    case 'hu':
      return AppLocalizationsHu();
    case 'id':
      return AppLocalizationsId();
    case 'it':
      return AppLocalizationsIt();
    case 'ja':
      return AppLocalizationsJa();
    case 'kn':
      return AppLocalizationsKn();
    case 'ko':
      return AppLocalizationsKo();
    case 'lt':
      return AppLocalizationsLt();
    case 'lv':
      return AppLocalizationsLv();
    case 'mk':
      return AppLocalizationsMk();
    case 'mr':
      return AppLocalizationsMr();
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
    case 'sl':
      return AppLocalizationsSl();
    case 'sr':
      return AppLocalizationsSr();
    case 'sv':
      return AppLocalizationsSv();
    case 'ta':
      return AppLocalizationsTa();
    case 'te':
      return AppLocalizationsTe();
    case 'th':
      return AppLocalizationsTh();
    case 'tl':
      return AppLocalizationsTl();
    case 'tr':
      return AppLocalizationsTr();
    case 'uk':
      return AppLocalizationsUk();
    case 'ur':
      return AppLocalizationsUr();
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
