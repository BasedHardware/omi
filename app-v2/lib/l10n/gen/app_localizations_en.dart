// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appName => 'Nooto';

  @override
  String welcomeBrandLine(String brand) {
    return 'Welcome to $brand';
  }

  @override
  String get welcomeTaglinePrefix => 'Personal intelligence that turns ';

  @override
  String get welcomeTaglineEmphasis => 'thought to action.';

  @override
  String get welcomeContinueWithApple => 'Continue with Apple';

  @override
  String get welcomeContinueWithGoogle => 'Continue with Google';

  @override
  String get welcomeWaitingForBrowser => 'Waiting for browser…';

  @override
  String get welcomeAgreeFooter =>
      'By continuing you agree to our Terms and Privacy Policy.';

  @override
  String get onboardingPromptHintTyped => 'Type your answer…';

  @override
  String get onboardingPromptHintTap => 'Tap an option above to continue';

  @override
  String get onboardingOpenerName => 'Hey — what should I call you?';

  @override
  String onboardingOpenerLanguage(String name) {
    return 'Nice to meet you, $name. What language do you want me to use?';
  }

  @override
  String get onboardingOpenerMicrophone =>
      'I\'ll need your mic to listen for what matters.';

  @override
  String get onboardingOpenerNotifications =>
      'Mind if I ping you when something needs your attention?';

  @override
  String get onboardingOpenerBackground =>
      'I work best if I can keep listening in the background.';

  @override
  String get onboardingOpenerLocation =>
      'Want me to tag where things happen? Optional — feel free to skip.';

  @override
  String get onboardingOpenerDevice =>
      'Have a Nooto device on you? We can wire it up later — pairing arrives in the next phase.';

  @override
  String get onboardingOpenerSpeechProfile =>
      'Let me learn your voice so I can tell you apart from the rest of the world.';

  @override
  String get onboardingOpenerAcknowledge => 'All set. Let\'s go.';

  @override
  String get onboardingSkipped => 'Sure, we can do that later.';

  @override
  String get onboardingChipMoreLanguages => 'More languages…';

  @override
  String get onboardingChipSkipForNow => 'Skip for now';

  @override
  String get onboardingChipPairLater => 'I\'ll pair it later';

  @override
  String get onboardingAckLetsGo => 'Let\'s go';

  @override
  String get onboardingAckGotIt => 'Got it';

  @override
  String get onboardingPermissionAllow => 'Allow';

  @override
  String get onboardingPermissionPending => 'Pending';

  @override
  String get onboardingPermissionGranted => 'Granted';

  @override
  String get onboardingPermissionDenied => 'Denied';

  @override
  String get onboardingPermissionDeniedAction => 'Open settings';

  @override
  String get onboardingPermissionLabelMicrophone => 'Microphone access';

  @override
  String get onboardingPermissionLabelMicrophoneHelper =>
      'Audio is processed on your device; only the transcript leaves.';

  @override
  String get onboardingPermissionLabelNotifications => 'Notification access';

  @override
  String get onboardingPermissionLabelNotificationsHelper =>
      'Quiet, useful nudges only — never noise.';

  @override
  String get onboardingPermissionLabelBackground => 'Background activity';

  @override
  String get onboardingPermissionLabelBackgroundHelper =>
      'Lets Nooto stay alive while you\'re using other apps.';

  @override
  String get onboardingPermissionLabelLocation => 'Location';

  @override
  String get onboardingPermissionLabelLocationHelper =>
      'Tags conversations with where they happened. Optional.';

  @override
  String get onboardingSpeechCardTitle => 'Read this aloud';

  @override
  String get onboardingSpeechCardBody =>
      'Whenever you\'re ready, hold the button and read this in a normal voice for about five seconds.';

  @override
  String get onboardingSpeechCardSample =>
      'Hi, I\'m getting Nooto set up. This is what my voice sounds like in a normal room.';

  @override
  String get onboardingSpeechRecording => 'Listening…';

  @override
  String get onboardingSpeechCaptured => 'Voice captured ✓';

  @override
  String get onboardingSpeechSkip => 'Skip for now';

  @override
  String get shellTabHome => 'Home';

  @override
  String get shellTabChat => 'Chat';

  @override
  String get shellTabLibrary => 'Library';

  @override
  String get shellTabPlan => 'Plan';

  @override
  String get shellTabApps => 'Apps';

  @override
  String shellComingSoonTitle(String tab) {
    return '$tab arrives next';
  }

  @override
  String get shellComingSoonBody =>
      'This screen lands in a future phase. For now, the morning brief and today\'s commitments are on Home.';

  @override
  String get todayCardHeader => 'Today';

  @override
  String todayCardCountPartial(int visible, int total) {
    return '$visible of $total';
  }

  @override
  String todayCardCountFull(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count items',
      one: '1 item',
    );
    return '$_temp0';
  }

  @override
  String get todayCardSeeAll => 'See all';

  @override
  String get todayCardSeeAllSemantics => 'See all action items, opens Plan tab';

  @override
  String get summaryTemplate => 'Summary template';

  @override
  String summarizedBy(String name) {
    return 'Summarized by $name';
  }

  @override
  String get noSummaryForApp =>
      'No summary available — tap to choose another app';

  @override
  String get reprocessingConversation => 'Reprocessing…';

  @override
  String get reprocessFailed => 'Couldn\'t reprocess. Try again.';

  @override
  String get chooseSummarizationApp => 'Choose a summarization app';

  @override
  String get currentlyUsing => 'Currently using';

  @override
  String get suggestedForThisConversation => 'Suggested for this conversation';

  @override
  String get summarizedAppsSuggestedSection => 'Suggested';

  @override
  String get summarizedAppsAvailableSection => 'Installed';

  @override
  String get summarizedAppsEmpty => 'No apps installed yet';
}
