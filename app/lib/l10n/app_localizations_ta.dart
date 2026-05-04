// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Tamil (`ta`).
class AppLocalizationsTa extends AppLocalizations {
  AppLocalizationsTa([String locale = 'ta']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'உரையாடல்';

  @override
  String get transcriptTab => 'வேண்டுகோள் பெயர்';

  @override
  String get actionItemsTab => 'கர்ம பணிகள்';

  @override
  String get deleteConversationTitle => 'உரையாடலை நீக்கவா?';

  @override
  String get deleteConversationMessage =>
      'இது தொடர்புடைய நினைவுகள், பணிகள் மற்றும் ஆடியோ ফাইல்களையும் நீக்கும். இந்த நடவடிக்கையை மாற்ற முடியாது.';

  @override
  String get confirm => 'உறுதிப்படுத்து';

  @override
  String get cancel => 'ரத்துசெய்';

  @override
  String get ok => 'சரி';

  @override
  String get delete => 'நீக்கு';

  @override
  String get add => 'சேர்';

  @override
  String get update => 'புதுப்பிக்க';

  @override
  String get save => 'சேமிக்கவும்';

  @override
  String get edit => 'திருத்து';

  @override
  String get close => 'மூடு';

  @override
  String get clear => 'துடைக்கவும்';

  @override
  String get copyTranscript => 'வேண்டுகோள் நகலெடுக்கவும்';

  @override
  String get copySummary => 'சாரம் நகலெடுக்கவும்';

  @override
  String get testPrompt => 'தேர்வு கேட்டுகோள்';

  @override
  String get reprocessConversation => 'உரையாடலை மீண்டும் செயல்படுத்தவும்';

  @override
  String get deleteConversation => 'உரையாடலை நீக்கவும்';

  @override
  String get contentCopied => 'உள்ளடக்கம் கிளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get failedToUpdateStarred => 'நட்சத்திர நிலைமாற்றம் செய்ய முடியவில்லை.';

  @override
  String get conversationUrlNotShared => 'உரையாடல் URL பகிர முடியவில்லை.';

  @override
  String get errorProcessingConversation => 'உரையாடல் செயல்படுத்தும் போது பிழை. பின்னர் மீண்டும் முயலுங்கள்.';

  @override
  String get noInternetConnection => 'இணையம் இணைப்பு இல்லை';

  @override
  String get unableToDeleteConversation => 'உரையாடலை நீக்க முடியவில்லை';

  @override
  String get somethingWentWrong => 'ஏதோ தவறு ஏற்பட்டது! பின்னர் மீண்டும் முயலுங்கள்.';

  @override
  String get copyErrorMessage => 'பிழை செய்தி நகலெடுக்கவும்';

  @override
  String get errorCopied => 'பிழை செய்தி கிளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get remaining => 'மீதமுள்ள';

  @override
  String get loading => 'ஏற்றுகிறது...';

  @override
  String get loadingDuration => 'கால அளவு ஏற்றுகிறது...';

  @override
  String secondsCount(int count) {
    return '$count வினாடிகள்';
  }

  @override
  String get people => 'மக்கள்';

  @override
  String get addNewPerson => 'புதிய ஆள் சேர்க்கவும்';

  @override
  String get editPerson => 'ஆளைத் திருத்து';

  @override
  String get createPersonHint => 'ஒரு புதிய ஆளை உருவாக்கி Omi அவர்களின் பேச்சை அங்கீகரிக்க பயிற்சி!';

  @override
  String get speechProfile => 'பேச்சு சுயவிவரம்';

  @override
  String sampleNumber(int number) {
    return 'மாதிரி $number';
  }

  @override
  String get settings => 'அமைப்புகள்';

  @override
  String get language => 'மொழி';

  @override
  String get selectLanguage => 'மொழியைத் தேர்ந்தெடுக்கவும்';

  @override
  String get deleting => 'நீக்குகிறது...';

  @override
  String get pleaseCompleteAuthentication =>
      'உங்கள் உலாவியில் அங்கீகாரத்தை முடிக்கவும். முடிந்ததும், பயன்பாட்டுக்குத் திரும்பவும்.';

  @override
  String get failedToStartAuthentication => 'அங்கீகாரத்தைத் தொடங்க முடியவில்லை';

  @override
  String get importStarted => 'இறக்குமதி தொடங்கியது! முடிந்தால் உங்களுக்குத் தெரிவிக்கப்படும்.';

  @override
  String get failedToStartImport => 'இறக்குமதியைத் தொடங்க முடியவில்லை. மீண்டும் முயலுங்கள்.';

  @override
  String get couldNotAccessFile => 'தேர்ந்தெடுக்கப்பட்ட ஆவணத்தை அணுக முடியவில்லை';

  @override
  String get askOmi => 'Omi-க்குக் கேளுங்கள்';

  @override
  String get done => 'முடிந்தது';

  @override
  String get disconnected => 'துண்டிக்கப்பட்டது';

  @override
  String get searching => 'தேடுகிறது...';

  @override
  String get connectDevice => 'சாதனத்தை இணைக்கவும்';

  @override
  String get monthlyLimitReached => 'நீங்கள் உங்கள் மாத வரம்பை அடைந்துவிட்டீர்கள்.';

  @override
  String get checkUsage => 'பயன்பாட்டைப் பரிசோதிக்கவும்';

  @override
  String get syncingRecordings => 'பதிவுகள் ஒத்திசைக்கிறது';

  @override
  String get recordingsToSync => 'ஒத்திசைக்க பதிவுகள்';

  @override
  String get allCaughtUp => 'எல்லாம் பிடிபட்டது';

  @override
  String get sync => 'ஒத்திசை';

  @override
  String get pendantUpToDate => 'பதக்கம் தற்போதைய';

  @override
  String get allRecordingsSynced => 'அனைத்து பதிவுகளும் ஒத்திசைக்கப்பட்டுள்ளன';

  @override
  String get syncingInProgress => 'ஒத்திசையல் நடந்துகொண்டிருக்கிறது';

  @override
  String get readyToSync => 'ஒத்திசைக்கத் தயாரா';

  @override
  String get tapSyncToStart => 'தொடங்குவதற்கு Sync ஐ தட்டவும்';

  @override
  String get pendantNotConnected => 'பதக்கம் இணைக்கப்படாது. ஒத்திசைப்பதற்கு இணைக்கவும்.';

  @override
  String get everythingSynced => 'எல்லாம் ஏற்கனவே ஒத்திசைக்கப்பட்டுள்ளன.';

  @override
  String get recordingsNotSynced => 'நீங்கள் இன்னும் ஒத்திசைக்கப்படாத பதிவுகளைக் கொண்டுள்ளீர்கள்.';

  @override
  String get syncingBackground => 'நாங்கள் உங்கள் பதிவுகளை நেருப்பில் ஒத்திசைத்துக் கொண்டிருப்போம்.';

  @override
  String get noConversationsYet => 'இன்னும் உரையாடல் இல்லை';

  @override
  String get noStarredConversations => 'நட்சத்திரம் சூட்ட உரையாடல் இல்லை';

  @override
  String get starConversationHint =>
      'உரையாடலுக்கு நட்சத்திரம் சூட்ட, அதைத் திறந்து தலைப்பில் உள்ள நட்சத்திரக் குறியை தட்டவும்.';

  @override
  String get searchConversations => 'உரையாடல்களைத் தேடுங்கள்...';

  @override
  String selectedCount(int count, Object s) {
    return '$count தேர்ந்தெடுக்கப்பட்ட';
  }

  @override
  String get merge => 'ஒருங்கிணையு';

  @override
  String get mergeConversations => 'உரையாடல்களை ஒருங்கிணையவும்';

  @override
  String mergeConversationsMessage(int count) {
    return 'இது $count உரையாடல்களை ஒன்றாக ஒருங்கிணைக்கும். அனைத்து உள்ளடக்கம் ஒருங்கிணைக்கப்பட்டு மீண்டும் உருவாக்கப்படும்.';
  }

  @override
  String get mergingInBackground => 'பின்னணியில் ஒருங்கிணைக்கப்பட்டு. இது சிறிது நேரம் எடுக்கக்கூடும்.';

  @override
  String get failedToStartMerge => 'ஒருங்கிணையல் தொடங்க முடியவில்லை';

  @override
  String get askAnything => 'எதையும் கேளுங்கள்';

  @override
  String get noMessagesYet => 'இன்னும் செய்திகள் இல்லை!\nநீங்கள் ஒரு உரையாடலைத் தொடங்க ஏன் வேண்டாம்?';

  @override
  String get deletingMessages => 'Omi இன் நினைவலிருந்து உங்கள் செய்திகளை நீக்குகிறது...';

  @override
  String get messageCopied => '✨ செய்தி கிளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get cannotReportOwnMessage => 'நீங்கள் உங்கள் சொந்த செய்திகளைப் புகாரளிக்க முடியாது.';

  @override
  String get reportMessage => 'செய்திக்கு புகாரளிக்கவும்';

  @override
  String get reportMessageConfirm => 'இந்த செய்தியைப் புகாரளிக்க விரும்புகிறீர்களா?';

  @override
  String get messageReported => 'செய்தி வெற்றிகரமாக புகாரளிக்கப்பட்டது.';

  @override
  String get thankYouFeedback => 'உங்கள் கருத்துக்கு நன்றி!';

  @override
  String get clearChat => 'சாட் துடைக்கவும்';

  @override
  String get clearChatConfirm => 'சாட்டைத் துடைக்கவெண்டுமா? இந்த நடவடிக்கையை மாற்ற முடியாது.';

  @override
  String get maxFilesLimit => 'ஒரு முறையில் 4 கோப்புகளை மட்டுமே பதிவேற்றலாம்';

  @override
  String get chatWithOmi => 'Omi உடன் சாட்';

  @override
  String get apps => 'பயன்பாடுகள்';

  @override
  String get noAppsFound => 'எந்த பயன்பாடும் கண்டுபிடிக்கப்படவில்லை';

  @override
  String get tryAdjustingSearch => 'உங்கள் தேடலை அல்லது வடிப்பாளிகளை சரிசெய்ய முயலுங்கள்';

  @override
  String get createYourOwnApp => 'உங்கள் சொந்த பயன்பாடு உருவாக்குங்கள்';

  @override
  String get buildAndShareApp => 'உங்கள் தனிப்பயன பயன்பாடு உருவாக்கி பகிர்ந்து கொள்ளுங்கள்';

  @override
  String get searchApps => 'பயன்பாடுகளைத் தேடுங்கள்...';

  @override
  String get myApps => 'என் பயன்பாடுகள்';

  @override
  String get installedApps => 'நிறுவப்பட்ட பயன்பாடுகள்';

  @override
  String get unableToFetchApps =>
      'பயன்பாடுகளைப் பெற முடியவில்லை :(\n\nআপনার இணையம் இணைப்பைப் பரிசோதிக்கவும் மற்றும் மீண்டும் முயலுங்கள்.';

  @override
  String get aboutOmi => 'Omi பற்றி';

  @override
  String get privacyPolicy => 'தனியுரிமை கொள்கை';

  @override
  String get visitWebsite => 'வலைப்பதிவுக்குச் செல்லவும்';

  @override
  String get helpOrInquiries => 'உதவி அல்லது ஆராய்ச்சி?';

  @override
  String get joinCommunity => 'சமூகத்தில் சேரவும்!';

  @override
  String get membersAndCounting => '8000+ உறுப்பினர்கள் மற்றும் எண்ணுதல்.';

  @override
  String get deleteAccountTitle => 'கணக்கை நீக்கவும்';

  @override
  String get deleteAccountConfirm => 'உங்கள் கணக்கை நீக்க விரும்புகிறீர்களா?';

  @override
  String get cannotBeUndone => 'இதை மாற்ற முடியாது.';

  @override
  String get allDataErased => 'உங்கள் அனைத்து நினைவுகள் மற்றும் உரையாடல்கள் நிரந்தரமாக நீக்கப்படும்.';

  @override
  String get appsDisconnected => 'உங்கள் பயன்பாடுகள் மற்றும் ஒருங்கிணைப்புகள் உடனடியாக துண்டிக்கப்படும்.';

  @override
  String get exportBeforeDelete =>
      'உங்கள் கணக்கை நீக்குவதற்கு முன் உங்கள் தரவை ஏற்றுமதி செய்யலாம், ஆனால் நீக்கப்பட்டபின், அதை மீட்டெடுக்க முடியாது.';

  @override
  String get deleteAccountCheckbox =>
      'உங்கள் கணக்கை நீக்குவது நிரந்தரம் என்றும் அனைத்து தரவு, நினைவுகள் மற்றும் உரையாடல்கள் உட்பட நிரந்தரமாக நீக்கப்பட்டு மீட்டெடுக்க முடியாது என்பது நான் புரிந்துகொள்கிறேன்.';

  @override
  String get areYouSure => 'நிச்சயமாக?';

  @override
  String get deleteAccountFinal =>
      'இந்த நடவடிக்கை மாற்றியமைக்க முடியாது மற்றும் உங்கள் கணக்கு மற்றும் சம்பந்தப்பட்ட அனைத்து தரவுகளையும் நிரந்தரமாக நீக்கும். நீங்கள் தொடர விரும்புகிறீர்களா?';

  @override
  String get deleteNow => 'இப்போது நீக்கவும்';

  @override
  String get goBack => 'பின்னால் செல்வோம்';

  @override
  String get checkBoxToConfirm =>
      'உங்கள் கணக்கை நீக்குவது நிரந்தரம் மற்றும் மாற்றியமைக்க முடியாது என்பதை நீங்கள் புரிந்துகொள்கிறீர்கள் என்பதை உறுதிப்படுத்த பெட்டியைச் சரிபார்க்கவும்.';

  @override
  String get profile => 'சுயவிவரம்';

  @override
  String get name => 'பெயர்';

  @override
  String get email => 'மின்னஞ்சல்';

  @override
  String get customVocabulary => 'தனிப்பயன் சொல்லடை';

  @override
  String get identifyingOthers => 'மற்றவர்களைக் கண்டறிதல்';

  @override
  String get paymentMethods => 'பணம் செலுத்தும் முறைகள்';

  @override
  String get conversationDisplay => 'உரையாடல் காட்சி';

  @override
  String get dataPrivacy => 'தரவு தனியுரிமை';

  @override
  String get userId => 'பயனர் ID';

  @override
  String get notSet => 'அமைக்கப்படவில்லை';

  @override
  String get userIdCopied => 'பயனர் ID கிளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get systemDefault => 'கணினி முறை';

  @override
  String get planAndUsage => 'திட்டம் & பயன்பாடு';

  @override
  String get offlineSync => 'ஆப்லைன் ஒத்திசை';

  @override
  String get deviceSettings => 'சாதன அமைப்புகள்';

  @override
  String get integrations => 'ஒருங்கிணைப்புகள்';

  @override
  String get feedbackBug => 'கருத்து / பிழை';

  @override
  String get helpCenter => 'உதவி மையம்';

  @override
  String get developerSettings => 'உருவாக்குநர் அமைப்புகள்';

  @override
  String get getOmiForMac => 'Mac க்கு Omi பெறுங்கள்';

  @override
  String get referralProgram => 'நிபந்தனா திட்டம்';

  @override
  String get signOut => 'வெளியேறவும்';

  @override
  String get appAndDeviceCopied => 'பயன்பாடு மற்றும் சாதன விவரங்கள் நகலெடுக்கப்பட்டது';

  @override
  String get wrapped2025 => 'சுற்றுப்பட்ட 2025';

  @override
  String get yourPrivacyYourControl => 'உங்கள் தனியுரிமை, உங்கள் கட்டுப்பாடு';

  @override
  String get privacyIntro =>
      'Omi இல், நாங்கள் உங்கள் தனியுரிமையைக் காப்பாற்ற உறுதிபட்டுள்ளோம். இந்தப் பக்கம் உங்கள் தரவை எவ்வாறு சேமிக்கப்பட்டு பயன்படுத்தப்படுகிறது என்பதை கட்டுப்படுத்த அनुमति கொடுக்கிறது.';

  @override
  String get learnMore => 'மேலும் அறியவும்...';

  @override
  String get dataProtectionLevel => 'தரவு பாதுகாப்பு நிலை';

  @override
  String get dataProtectionDesc =>
      'உங்கள் தரவு வலுவான என்ற்িப்ட்ஸனுடன் இயல்பாக பாதுகாக்கப்படுகிறது. உங்கள் அமைப்புகளைப் பரிசோதிக்கவும் மற்றும் கீழே உள்ள எதிர்கால தனியுரிமை விருப்பங்களைப் பரிசோதிக்கவும்.';

  @override
  String get appAccess => 'பயன்பாடு அணுகல்';

  @override
  String get appAccessDesc =>
      'பின்வரும் பயன்பாடுகள் உங்கள் தரவை அணுக முடியும். ஒரு பயன்பாடு பகிர்ந்து கொள்ள நிர்வாகித்துக் கொள்ள தட்டவும்.';

  @override
  String get noAppsExternalAccess =>
      'நிறுவப்பட்ட பயன்பாடுகள் எதுவும் உங்கள் தரவுக்கு வெளிப்புற அணுகலைக் கொண்டிருக்கவில்லை.';

  @override
  String get deviceName => 'சாதன பெயர்';

  @override
  String get deviceId => 'சாதன ID';

  @override
  String get firmware => 'ফার்মওয়্যার';

  @override
  String get sdCardSync => 'SD கார்ட் ஒத்திசை';

  @override
  String get hardwareRevision => 'ஹার்ডওয়்যெர் திருத்தம்';

  @override
  String get modelNumber => 'மாதிரி எண்';

  @override
  String get manufacturer => 'உற்பादক';

  @override
  String get doubleTap => 'இரட்டை தட்டு';

  @override
  String get ledBrightness => 'LED பிரகாசம்';

  @override
  String get micGain => 'மைக் লாभ';

  @override
  String get disconnect => 'இணைப்பை நீக்கவும்';

  @override
  String get forgetDevice => 'சாதனத்தை மறந்துவிடு';

  @override
  String get chargingIssues => 'சார்ஜ செய்தல் சிக்கல்கள்';

  @override
  String get disconnectDevice => 'சாதனத்தை இணைப்பை நீக்கவும்';

  @override
  String get unpairDevice => 'சாதனத்தை பொருத்தம் நீக்கவும்';

  @override
  String get unpairAndForget => 'சாதனத்தைப் பொருத்தம் நீக்கி மறந்துவிடு';

  @override
  String get deviceDisconnectedMessage => 'உங்கள் Omi இணைப்பு நீக்கப்பட்டுள்ளது 😔';

  @override
  String get deviceUnpairedMessage =>
      'சாதனம் பொருத்தம் நீக்கப்பட்டது. அமைப்புகள் > Bluetooth க்குச் சென்று சாதனத்தை மறந்துவிடவும் பொருத்தம் முடிக்க.';

  @override
  String get unpairDialogTitle => 'சாதனத்தை பொருத்தம் நீக்கவும்';

  @override
  String get unpairDialogMessage =>
      'இது சாதனத்தைப் பொருத்தம் நீக்கும் பதவியை மற்றொரு ஃபோனுக்கு இணைக்க முடியும். நீங்கள் அமைப்புகள் > Bluetooth க்குச் சென்று சாதனத்தை மறந்துவிட வேண்டிய செயல்முறையை முடிக்க வேண்டும்.';

  @override
  String get deviceNotConnected => 'சாதனம் இணைக்கப்படவில்லை';

  @override
  String get connectDeviceMessage =>
      'உங்கள் Omi சாதனத்தை இணைக்கவும் அணுகல் மற்றும் தனிப்பயனாக்கல் என்ற சாதன அமைப்புகள்';

  @override
  String get deviceInfoSection => 'சாதன தகவல்';

  @override
  String get customizationSection => 'தனிப்பயனாக்கல்';

  @override
  String get hardwareSection => 'ஹார்ட்வேர்';

  @override
  String get v2Undetected => 'V2 கண்டுபிடிக்கப்படவில்லை';

  @override
  String get v2UndetectedMessage =>
      'உங்களுக்கு V1 சாதனம் அல்லது உங்கள் சாதனம் இணைக்கப்படவில்லை என்பதைக் கண்டோம். SD கார்ட் செயல்பாடு V2 சாதனங்களுக்கு மட்டுமே கிடைக்கிறது.';

  @override
  String get endConversation => 'உரையாடல் முடிக்கவும்';

  @override
  String get pauseResume => 'நிறுத்தி / மீண்டும் ஆரம்பிக்கவும்';

  @override
  String get starConversation => 'நட்சத்திரம் உரையாடல்';

  @override
  String get doubleTapAction => 'இரட்டை தட்டு நடவடிக்கை';

  @override
  String get endAndProcess => 'முடிக்கவும் & உரையாடல் செயல்படுத்தவும்';

  @override
  String get pauseResumeRecording => 'பதிவை நிறுத்தி / மீண்டும் ஆரம்பிக்கவும்';

  @override
  String get starOngoing => 'செயல்படும் உரையாடல் நட்சத்திரம்';

  @override
  String get off => 'அணைப்பு';

  @override
  String get max => 'அधिकतम';

  @override
  String get mute => 'குரல் நீக்கவும்';

  @override
  String get quiet => 'அமைதி';

  @override
  String get normal => 'சாதாரணம்';

  @override
  String get high => 'அதிக';

  @override
  String get micGainDescMuted => 'மைக்ரோஃபோன் குரல் நீக்கப்பட்டுள்ளது';

  @override
  String get micGainDescLow => 'மிகவும் அமைதியாக - உரத்த சூழ்நிலையில்';

  @override
  String get micGainDescModerate => 'அமைதியாக - மிதமான சத்தத்திற்காக';

  @override
  String get micGainDescNeutral => 'நடுநிலை - சமநிலை பதிவு';

  @override
  String get micGainDescSlightlyBoosted => 'சற்றே அதிகரிக்கப்பட்டது - சாதாரண பயன்பாடு';

  @override
  String get micGainDescBoosted => 'அதிகரிக்கப்பட்டது - அமைதியான சூழ்நிலைக்கு';

  @override
  String get micGainDescHigh => 'அதிக - தொலைதூர அல்லது மென்மையான குரல்களுக்கு';

  @override
  String get micGainDescVeryHigh => 'மிக உচ்சம் - மிக அமைதியான ஆதாரங்களுக்கு';

  @override
  String get micGainDescMax => 'அधिकतम - எச்சரிக்கையுடன் பயன்படுத்தவும்';

  @override
  String get developerSettingsTitle => 'உருவாக்குநர் அமைப்புகள்';

  @override
  String get saving => 'சேமிக்கிறது...';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'பேச்சு';

  @override
  String get transcriptionConfig => 'STT வழங்குநரைக் கட்டமைக்கவும்';

  @override
  String get conversationTimeout => 'உரையாடல் நேர வெளியேற்றம்';

  @override
  String get conversationTimeoutConfig => 'உரையாடல்கள் தன்னாக முடிவுக்கு போகும் போது அமைக்கவும்';

  @override
  String get importData => 'தரவு இறக்குமதி';

  @override
  String get importDataConfig => 'மற்ற ஆதாரங்களிலிருந்து தரவை இறக்குமதி';

  @override
  String get debugDiagnostics => 'பிழைத்திருத்தம் & நோயறிதல்';

  @override
  String get endpointUrl => 'முடிவுபுள்ளி URL';

  @override
  String get noApiKeys => 'API விசைகள் இல்லை';

  @override
  String get createKeyToStart => 'தொடங்குவதற்கு ஒரு விசை உருவாக்கவும்';

  @override
  String get createKey => 'விசை உருவாக்கவும்';

  @override
  String get docs => 'ஆவணங்கள்';

  @override
  String get yourOmiInsights => 'உங்கள் Omi அंतर्दृष्टि';

  @override
  String get today => 'இன்று';

  @override
  String get thisMonth => 'இந்த மாதம்';

  @override
  String get thisYear => 'இந்த ஆண்டு';

  @override
  String get allTime => 'எல்லா நேரம்';

  @override
  String get noActivityYet => 'இன்னும் செயல்பாடு இல்லை';

  @override
  String get startConversationToSeeInsights =>
      'Omi உடன் ஒரு உரையாடல் தொடங்கவும் உங்கள் பயன்பாட்டு அंতর्दृष्टি இங்கே பார்க்கவும்.';

  @override
  String get listening => 'கேட்கிறது';

  @override
  String get listeningSubtitle => 'Omi சுறுசுறுப்பாக கேட்ட மொத்த நேரம்.';

  @override
  String get understanding => 'புரிந்துகொள்ளல்';

  @override
  String get understandingSubtitle => 'உங்கள் உரையாடல்களில் இருந்து புரிந்துகொள்ளப்பட்ட சொற்கள்.';

  @override
  String get providing => 'வழங்குதல்';

  @override
  String get providingSubtitle => 'நடவடிக்கை பணிகள் மற்றும் குறிப்புகள் தன்னாக பிடிபடுந்த.';

  @override
  String get remembering => 'நினைவு';

  @override
  String get rememberingSubtitle => 'உங்களுக்கு நினைவுபடுத்தப்பட்ட உண்மைகள் மற்றும் விவரங்கள்.';

  @override
  String get unlimitedPlan => 'வரம்பற்ற திட்டம்';

  @override
  String get managePlan => 'திட்டத்தை நிர்வகிக்கவும்';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'உங்கள் திட்டம் $date இல் ரத்துசெய்யப்படும்.';
  }

  @override
  String renewsOn(String date) {
    return 'உங்கள் திட்டம் $date இல் புதுப்பிக்கப்படும்.';
  }

  @override
  String get basicPlan => 'இலவச திட்டம்';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used / $limit நிமிடங்கள் பயன்படுத்தப்பட்டுள்ளன';
  }

  @override
  String get upgrade => 'மேம்படுத்தவும்';

  @override
  String get upgradeToUnlimited => 'வரம்பற்ற மேம்படுத்தவும்';

  @override
  String basicPlanDesc(int limit) {
    return 'உங்கள் திட்டம் மாதத்திற்கு $limit இலவச நிமிடங்களை உள்ளடக்கியுள்ளது. வரம்பற்ற செல்ல மேம்படுத்தவும்.';
  }

  @override
  String get shareStatsMessage => 'என் Omi புள்ளிவிவரங்கள் பகிர்ந்து! (omi.me - உங்கள் எப்போதும் AI সहায়ক)';

  @override
  String get sharePeriodToday => 'இன்று, omi::';

  @override
  String get sharePeriodMonth => 'இந்த மாதம், omi::';

  @override
  String get sharePeriodYear => 'இந்த ஆண்டு, omi::';

  @override
  String get sharePeriodAllTime => 'இதுவரை, omi::';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes நிமிடங்களுக்கு கேட்டுள்ளேன்';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words சொற்களை புரிந்துகொண்டேன்';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count அंतर्दृष्टি வழங்கியுள்ளேன்';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count நினைவுகளை நினைவுபடுத்தியுள்ளேன்';
  }

  @override
  String get debugLogs => 'பிழைத்திருத்தம் பதிவுகள்';

  @override
  String get debugLogsAutoDelete => '3 நாட்களுக்குப் பிறகு தன்னாக நீக்கப்படுகிறது.';

  @override
  String get debugLogsDesc => 'சிக்கல்களைக் கண்டறிய உதவுங்கள்';

  @override
  String get noLogFilesFound => 'எந்த பதிவு கோப்புகளும் கண்டுபிடிக்கப்படவில்லை.';

  @override
  String get omiDebugLog => 'Omi பிழைத்திருத்தம் பதிவு';

  @override
  String get logShared => 'பதிவு பகிர்ந்து';

  @override
  String get selectLogFile => 'பதிவு கோப்பு தேர்ந்தெடுக்கவும்';

  @override
  String get shareLogs => 'பதிவுகள் பகிர்ந்து';

  @override
  String get debugLogCleared => 'பிழைத்திருத்தம் பதிவு துடைக்கப்பட்டது';

  @override
  String get exportStarted => 'ஏற்றுமதி தொடங்கியது. இது சில வினாடிகள் ஆனலாம்...';

  @override
  String get exportAllData => 'அனைத்து தரவு ஏற்றுமதி';

  @override
  String get exportDataDesc => 'உரையாடல்களை JSON கோப்பிற்கு ஏற்றுமதி';

  @override
  String get exportedConversations => 'Omi இலிருந்து ஏற்றுமதி செய்யப்பட்ட உரையாடல்கள்';

  @override
  String get exportShared => 'ஏற்றுமதி பகிர்ந்து';

  @override
  String get deleteKnowledgeGraphTitle => 'அறிவு வரைபடத்தை நீக்கவா?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'இது அனைத்து பெறப்பட்ட அறிவு வரைபட தரவையும் நீக்கும் (முனைப்புகள் மற்றும் இணைப்புகள்). உங்கள் அசல் நினைவுகள் பாதுகாப்பாக இருக்கும். வரைபடம் கால மற்றும் அல்லது அடுத்த கோரிக்கை மீது மீண்டும் உருவாக்கப்படும்.';

  @override
  String get knowledgeGraphDeleted => 'அறிவு வரைபடம் நீக்கப்பட்டது';

  @override
  String deleteGraphFailed(String error) {
    return 'வரைபடம் நீக்க முடியவில்லை: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'அறிவு வரைபடம் நீக்கவும்';

  @override
  String get deleteKnowledgeGraphDesc => 'அனைத்து முனைप்புகள் மற்றும் இணைப்புகள் அழிக்கவும்';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP சேவையகம்';

  @override
  String get mcpServerDesc => 'AI உதவிகளை உங்கள் தரவுடன் இணைக்கவும்';

  @override
  String get serverUrl => 'சேவையக URL';

  @override
  String get urlCopied => 'URL நகலெடுக்கப்பட்டது';

  @override
  String get apiKeyAuth => 'API விசை அனुमति';

  @override
  String get header => 'தலைப்பு';

  @override
  String get authorizationBearer => 'அनुमति: वाहक <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ग्राहक ID';

  @override
  String get clientSecret => 'ग्राहक ரகசியம்';

  @override
  String get useMcpApiKey => 'உங்கள் MCP API விசை பயன்படுத்தவும்';

  @override
  String get webhooks => 'வலைப்பிணைப்பு';

  @override
  String get conversationEvents => 'உரையாடல் நிகழ்வுகள்';

  @override
  String get newConversationCreated => 'புதிய உரையாடல் உருவாக்கப்பட்டது';

  @override
  String get realtimeTranscript => 'நிஜ நேர வேண்டுகோள்';

  @override
  String get transcriptReceived => 'வேண்டுகோள் பெறப்பட்டது';

  @override
  String get audioBytes => 'ஆடியோ பைட்டுகள்';

  @override
  String get audioDataReceived => 'ஆடியோ தரவு பெறப்பட்டது';

  @override
  String get intervalSeconds => 'இடைவெளி (வினாடிகள்)';

  @override
  String get daySummary => 'நாள் சாரம்';

  @override
  String get summaryGenerated => 'சாரம் உருவாக்கப்பட்டது';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.json க்கு சேர்க்கவும்';

  @override
  String get copyConfig => 'ஆட்டு நகலெடுக்கவும்';

  @override
  String get configCopied => 'ஆட்டு கிளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get listeningMins => 'கேட்கிறது (நிமிடங்கள்)';

  @override
  String get understandingWords => 'புரிந்துகொள்ளல் (சொற்கள்)';

  @override
  String get insights => 'அंतर्दृष्टि';

  @override
  String get memories => 'நினைவுகள்';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used / $limit நிமிடம் இந்த மாதம் பயன்படுத்தப்பட்டுள்ளন';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used / $limit சொற்கள் இந்த மாதம் பயன்படுத்தப்பட்டுள்ளன';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used / $limit அंतर्दृष्टि இந்த மாதம் பெறப்பட்டுள்ளன';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used / $limit நினைவுகள் இந்த மாதம் உருவாக்கப்பட்டுள்ளன';
  }

  @override
  String get visibility => 'দৃশ்যমानতা';

  @override
  String get visibilitySubtitle => 'உங்கள் பட்டியலில் எந்த உரையாடல்கள் தோன்றுகிறது என்பதைக் கட்டுப்படுத்தவும்';

  @override
  String get showShortConversations => 'குறு உரையாடல்களைக் காட்டவும்';

  @override
  String get showShortConversationsDesc => 'வாளிப்பு குறைவான உரையாடல்களைக் காட்டவும்';

  @override
  String get showDiscardedConversations => 'தள்ளப்பட்ட உரையாடல்களைக் காட்டவும்';

  @override
  String get showDiscardedConversationsDesc => 'தள்ளப்பட்ட பிற உரையாடல்களை அடக்கவும்';

  @override
  String get shortConversationThreshold => 'குறு உரையாடல் வாளிப்பு';

  @override
  String get shortConversationThresholdSubtitle => 'இந்த வாளிப்பு குறைவான உரையாடல்கள் மேலே இயல்பாக மறைக்கப்படும்';

  @override
  String get durationThreshold => 'வாளிப்பு வாளிப்பு';

  @override
  String get durationThresholdDesc => 'இந்த வாளிப்பு குறைவான உரையாடல்களை மறைக்கவும்';

  @override
  String minLabel(int count) {
    return '$count நிமி';
  }

  @override
  String get customVocabularyTitle => 'தனிப்பயன் சொல்லடை';

  @override
  String get addWords => 'சொற்கள் சேர்க்கவும்';

  @override
  String get addWordsDesc => 'பெயர்கள், சொற்கள், அல்லது அசாதாரண சொற்கள்';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'இணைக்கவும்';

  @override
  String get comingSoon => 'விரைவில் வருகிறது';

  @override
  String get integrationsFooter => 'சாட்டில் தரவு மற்றும் மெட்ரிக்ஸ் பார்க்க உங்கள் பயன்பாடுகளை இணைக்கவும்.';

  @override
  String get completeAuthInBrowser =>
      'உங்கள் உலாவியில் அங்கீகாரத்தை முடிக்கவும். முடிந்ததும், பயன்பாட்டுக்குத் திரும்பவும்.';

  @override
  String failedToStartAuth(String appName) {
    return '$appName அங்கீகாரத்தைத் தொடங்க முடியவில்லை';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName இலிருந்து இணைப்பை நீக்கவா?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return '$appName இலிருந்து இணைப்பை நீக்க விரும்புகிறீர்களா? நீங்கள் எப்போதும் மீண்டும் இணைக்கலாம்.';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName இலிருந்து துண்டிக்கப்பட்டது';
  }

  @override
  String get failedToDisconnect => 'இணைப்பை நீக்க முடியவில்லை';

  @override
  String connectTo(String appName) {
    return '$appName இற்கு இணைக்கவும்';
  }

  @override
  String authAccessMessage(String appName) {
    return 'உங்கள் $appName தரவை அணுக Omi க்கு அங்கீகாரம் தேவை. இது அங்கீகாரத்திற்கு உங்கள் உலாவியைத் திறக்கும்.';
  }

  @override
  String get continueAction => 'தொடரவும்';

  @override
  String get languageTitle => 'மொழி';

  @override
  String get primaryLanguage => 'முதன்மை மொழி';

  @override
  String get automaticTranslation => 'தன்னாக மொழிபெயர்ப்பு';

  @override
  String get detectLanguages => '10+ மொழிகளை கண்டறியவும்';

  @override
  String get authorizeSavingRecordings => 'பதிவுகள் சேமிப்பதற்கு அங்கீகாரம் கொடுக்கவும்';

  @override
  String get thanksForAuthorizing => 'அங்கீகாரம் கொடுத்ததற்கு நன்றி!';

  @override
  String get needYourPermission => 'நாங்கள் உங்கள் அனுமதி தேவை';

  @override
  String get alreadyGavePermission =>
      'உங்கள் பதிவுகளை சேமிக்க உங்களுக்கு ஏற்கனவே அனுமதி கொடுத்துள்ளீர்கள். நாங்கள் ஏன் தேவை என்பதற்கு இங்கே ஒரு நினைவூட்டல்:';

  @override
  String get wouldLikePermission => 'உங்கள் குரல் பதிவுகளை சேமிக்க நாங்கள் உங்கள் அனுமதி விரும்புகிறோம். ஏன்:';

  @override
  String get improveSpeechProfile => 'உங்கள் பேச்சு சுயவிவரம் மேம்படுத்தவும்';

  @override
  String get improveSpeechProfileDesc =>
      'உங்கள் ব্যক்তिगत பேச்சு சுயவிவரத்தைப் பயிற்சி மற்றும் மேம்படுத்த நாங்கள் பதிவுகள் பயன்படுத்துகிறோம்.';

  @override
  String get trainFamilyProfiles => 'நண்பர்கள் மற்றும் குடும்ப சுயவிவரங்களைப் பயிற்சி';

  @override
  String get trainFamilyProfilesDesc =>
      'உங்கள் நண்பர்கள் மற்றும் குடும்ப உறுப்பினர்களை அங்கீகரிக்கவும் சுயவிவரங்களை உருவாக்க உங்கள் பதிவுகள் நாங்கள் உதவுகிறது.';

  @override
  String get enhanceTranscriptAccuracy => 'வேண்டுகோள் நির்ভুलத்தை மேம்படுத்தவும்';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'எங்கள் மாதிரி উন்নত, நாங்கள் உங்கள் பதிவுகளுக்கு சிறந்த வேண்டுகோள் முடிவுகள் வழங்க முடியும்.';

  @override
  String get legalNotice =>
      'சட்ட மாற்றம்: குரல் தரவு பதிவு மற்றும் சேமிப்பு சட்டம் உங்கள் இடத்தைப் பொறுத்து மாறுவது சட்ட முறை மாறுவது சாத்தியமுள்ளது. உங்கள் உள்ளூர் சட்டங்கள் மற்றும் விதிமுறைகளுடன் இணங்கக் உறுதி செய்வது உங்கள் பொறுப்பு.';

  @override
  String get alreadyAuthorized => 'ஏற்கனவே அங்கீகரிக்கப்பட்ட';

  @override
  String get authorize => 'அங்கீகாரம் கொடுக்கவும்';

  @override
  String get revokeAuthorization => 'அங்கீகாரத்தை ரத்துசெய்';

  @override
  String get authorizationSuccessful => 'அங்கீகாரம் வெற்றிகரமாக!';

  @override
  String get failedToAuthorize => 'அங்கீகாரம் அளிக்க முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get authorizationRevoked => 'அங்கீகாரம் ரத்து செய்யப்பட்டது.';

  @override
  String get recordingsDeleted => 'பதிவுகள் நீக்கப்பட்டுவிட்டன.';

  @override
  String get failedToRevoke => 'அங்கீகாரத்தை ரத்து செய்ய முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get permissionRevokedTitle => 'அனுமதி ரத்து செய்யப்பட்டது';

  @override
  String get permissionRevokedMessage => 'உங்கள் பழைய பதிவுகளையும் நீக்க விரும்புகிறீர்களா?';

  @override
  String get yes => 'ஆம்';

  @override
  String get editName => 'பெயரைத் திருத்தவும்';

  @override
  String get howShouldOmiCallYou => 'Omi உங்களை எப்படி அழைக்க வேண்டும்?';

  @override
  String get enterYourName => 'உங்கள் பெயரை உள்ளிடவும்';

  @override
  String get nameCannotBeEmpty => 'பெயர் வெற்றிடமாக இருக்க முடியாது';

  @override
  String get nameUpdatedSuccessfully => 'பெயர் வெற்றிகரமாக புதுப்பிக்கப்பட்டது!';

  @override
  String get calendarSettings => 'நாட்காட்டி அமைப்புகள்';

  @override
  String get calendarProviders => 'நாட்காட்டி வழங்குநர்கள்';

  @override
  String get macOsCalendar => 'macOS நாட்காட்டி';

  @override
  String get connectMacOsCalendar => 'உங்கள் உள்ளூர் macOS நாட்காட்டியை இணைக்கவும்';

  @override
  String get googleCalendar => 'Google நாட்காட்டி';

  @override
  String get syncGoogleAccount => 'உங்கள் Google অ்‌ काउண்ট்டுடன் ஒத்திசைக்கவும்';

  @override
  String get showMeetingsMenuBar => 'மெனு பட்டியில் வரவிருக்கும் சந்திப்புகளைக் காட்டவும்';

  @override
  String get showMeetingsMenuBarDesc =>
      'macOS மெனு பட்டியில் உங்கள் அடுத்த சந்திப்பு மற்றும் தொடங்குவதற்கான நேரத்தைக் காட்டவும்';

  @override
  String get showEventsNoParticipants => 'பங்கேற்பாளர்கள் இல்லாத நிகழ்வுகளைக் காட்டவும்';

  @override
  String get showEventsNoParticipantsDesc =>
      'இயக்கப்பட்டுள்ளபோது, வரவிருப்பவை பங்கேற்பாளர்கள் இல்லாத அல்லது வீடியோ இணைப்பு இல்லாத நிகழ்வுகளைக் காட்டுகிறது.';

  @override
  String get yourMeetings => 'உங்கள் சந்திப்புகள்';

  @override
  String get refresh => 'புதுப்பிக்கவும்';

  @override
  String get noUpcomingMeetings => 'வரவிருக்கும் சந்திப்புகள் இல்லை';

  @override
  String get checkingNextDays => 'அடுத்த 30 நாட்களை சரிபார்க்கிறது';

  @override
  String get tomorrow => 'நாளை';

  @override
  String get googleCalendarComingSoon => 'Google நாட்காட்டி ஒருங்கிணைப்பு விரைவில் வரும்!';

  @override
  String connectedAsUser(String userId) {
    return 'இணைக்கப்பட்ட பயனர்: $userId';
  }

  @override
  String get defaultWorkspace => 'இயல்புநிலை பணிப்பெருங்களம்';

  @override
  String get tasksCreatedInWorkspace => 'பணிகள் இந்த பணிப்பெருங்களத்தில் உருவாக்கப்படும்';

  @override
  String get defaultProjectOptional => 'இயல்புநிலை திட்டம் (விரும்பினால்)';

  @override
  String get leaveUnselectedTasks => 'திட்டம் இல்லாத பணிகளை உருவாக்க தேர்வாக வைக்கவும்';

  @override
  String get noProjectsInWorkspace => 'இந்த பணிப்பெருங்களத்தில் திட்டங்கள் கிடைக்கவில்லை';

  @override
  String get conversationTimeoutDesc =>
      'கிறுக்களத்தை தானாக முடிக்க முன்பாக எத்தனை நேரம் மிஞ்சே தென்பதைத் தேர்ந்தெடுக்கவும்:';

  @override
  String get timeout2Minutes => '2 நிமிடங்கள்';

  @override
  String get timeout2MinutesDesc => '2 நிமிடங்கள் மூச்சின்மையের பிறகு உரையாடலைத் முடிக்கவும்';

  @override
  String get timeout5Minutes => '5 நிமிடங்கள்';

  @override
  String get timeout5MinutesDesc => '5 நிமிடங்கள் மூச்சின்மையின் பிறகு உரையாடலைத் முடிக்கவும்';

  @override
  String get timeout10Minutes => '10 நிமிடங்கள்';

  @override
  String get timeout10MinutesDesc => '10 நிமிடங்கள் மூச்சின்மையின் பிறகு உரையாடலைத் முடிக்கவும்';

  @override
  String get timeout30Minutes => '30 நிமிடங்கள்';

  @override
  String get timeout30MinutesDesc => '30 நிமிடங்கள் மூச்சின்மையின் பிறகு உரையாடலைத் முடிக்கவும்';

  @override
  String get timeout4Hours => '4 மணிநேரங்கள்';

  @override
  String get timeout4HoursDesc => '4 மணிநேரங்கள் மூச்சின்மையின் பிறகு உரையாடலைத் முடிக்கவும்';

  @override
  String get conversationEndAfterHours => 'உரையாடல்கள் இப்போது 4 மணிநேரங்கள் மூச்சின்மையின் பிறகு முடிவடையும்';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'உரையாடல்கள் இப்போது $minutes நிமிடத்தின் மூச்சின்மையின் பிறகு முடிவடையும்';
  }

  @override
  String get tellUsPrimaryLanguage => 'உங்கள் முதன்மை மொழி என்ன என்று சொல்லுங்கள்';

  @override
  String get languageForTranscription =>
      'தட்டச்சுக்கு உங்கள் மொழியைத் தேர்ந்தெடுக்கவும் மேலும் ஒரு தனிப்பட்ட அভিজ்ஞதைக்கு.';

  @override
  String get singleLanguageModeInfo =>
      'ஒற்றை மொழி பயன்முறை இயக்கப்பட்டுள்ளது. மொழிபெயர்ப்பு அதிக নির்ভুலமாக்க முடக்கப்பட்டுள்ளது.';

  @override
  String get searchLanguageHint => 'பெயர் அல்லது குறியீட்டின் மூலம் மொழியைத் தேடவும்';

  @override
  String get noLanguagesFound => 'மொழிகள் கிடைக்கவில்லை';

  @override
  String get skip => 'தவிர்க்கவும்';

  @override
  String languageSetTo(String language) {
    return 'மொழி $language க்கு அமைக்கப்பட்டுள்ளது';
  }

  @override
  String get failedToSetLanguage => 'மொழியை அமைக்க முடியவில்லை';

  @override
  String appSettings(String appName) {
    return '$appName அமைப்புகள்';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName இலிருந்து நீக்க விரும்புகிறீர்களா?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'இது உங்கள் $appName அங்கீகாரத்தை நீக்கும். மீண்டும் பயன்படுத்த நீங்கள் மீண்டும் இணைக்க வேண்டும்.';
  }

  @override
  String connectedToApp(String appName) {
    return '$appName க்கு இணைக்கப்பட்டுள்ளது';
  }

  @override
  String get account => 'கணக்கு';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'உங்கள் செயல் பணிகள் உங்கள் $appName கணக்குக்கு ஒத்திசைக்கப்படும்';
  }

  @override
  String get defaultSpace => 'இயல்புநிலை இடம்';

  @override
  String get selectSpaceInWorkspace => 'உங்கள் பணிப்பெருங்களத்தில் ஒரு இடத்தைத் தேர்ந்தெடுக்கவும்';

  @override
  String get noSpacesInWorkspace => 'இந்த பணிப்பெருங்களத்தில் இடங்கள் கிடைக்கவில்லை';

  @override
  String get defaultList => 'இயல்புநிலை பட்டியல்';

  @override
  String get tasksAddedToList => 'பணிகள் இந்த பட்டியலில் சேர்க்கப்படும்';

  @override
  String get noListsInSpace => 'இந்த இடத்தில் பட்டியல்கள் கிடைக்கவில்லை';

  @override
  String failedToLoadRepos(String error) {
    return 'களஞ்சியங்களை ஏற்ற முடியவில்லை: $error';
  }

  @override
  String get defaultRepoSaved => 'இயல்புநிலை களஞ்சியம் சேமிக்கப்பட்டுள்ளது';

  @override
  String get failedToSaveDefaultRepo => 'இயல்புநிலை களஞ்சியத்தைச் சேமிக்க முடியவில்லை';

  @override
  String get defaultRepository => 'இயல்புநிலை களஞ்சியம்';

  @override
  String get selectDefaultRepoDesc =>
      'சிக்கல்களை உருவாக்குவதற்கான ஒரு இயல்புநிலை களஞ்சியத்தைத் தேர்ந்தெடுக்கவும். நீங்கள் சிக்கல்களை உருவாக்கும்போது வேறு ஒரு களஞ்சியத்தைக் குறிப்பிடலாம்.';

  @override
  String get noReposFound => 'களஞ்சியங்கள் கிடைக்கவில்லை';

  @override
  String get private => 'தனிப்பட்டது';

  @override
  String updatedDate(String date) {
    return '$date புதுப்பிக்கப்பட்டது';
  }

  @override
  String get yesterday => 'நேற்று';

  @override
  String daysAgo(int count) {
    return '$count நாட்கள் முன்';
  }

  @override
  String get oneWeekAgo => '1 வாரம் முன்';

  @override
  String weeksAgo(int count) {
    return '$count வாரங்கள் முன்';
  }

  @override
  String get oneMonthAgo => '1 மாதம் முன்';

  @override
  String monthsAgo(int count) {
    return '$count மாதங்கள் முன்';
  }

  @override
  String get issuesCreatedInRepo => 'சிக்கல்கள் உங்கள் இயல்புநிலை களஞ்சியத்தில் உருவாக்கப்படும்';

  @override
  String get taskIntegrations => 'பணி ஒருங்கிணைப்புகள்';

  @override
  String get configureSettings => 'அமைப்புகளை உள்ளமைக்கவும்';

  @override
  String get completeAuthBrowser =>
      'உங்கள் உலாவியில் அங்கீகாரத்தை முடிக்கவும். முடிந்ததும், பயன்பாட்டுக்குத் திரும்பவும்.';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName அங்கீகாரத்தைத் தொடங்க முடியவில்லை';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appName க்கு இணைக்கவும்';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'உங்கள் $appName கணக்கில் பணிகளை உருவாக்க Omi ஐ அங்கீகரிக்க வேண்டும். இது அங்கீகாரத்திற்கான உங்கள் உலாவியைத் திறக்கும்.';
  }

  @override
  String get continueButton => 'தொடரவும்';

  @override
  String appIntegration(String appName) {
    return '$appName ஒருங்கிணைப்பு';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName உடனான ஒருங்கிணைப்பு விரைவில் வரும்! நாங்கள் உங்களுக்கு மேலும் பணி மேலாண்மை விருப்பங்களைக் கொண்டு வர கடினமாக உழைக்கிறோம்.';
  }

  @override
  String get gotIt => 'சரி';

  @override
  String get tasksExportedOneApp => 'பணிகள் ஒரு நேரத்தில் ஒரு பயன்பாட்டிற்கு ஏற்றுமதி செய்யப்படலாம்.';

  @override
  String get completeYourUpgrade => 'உங்கள் மேம்பாட்டை முடிக்கவும்';

  @override
  String get importConfiguration => 'உள்ளமைப்பைக் கொண்டு வாருங்கள்';

  @override
  String get exportConfiguration => 'உள்ளமைப்பை ஏற்றுமதி செய்யவும்';

  @override
  String get bringYourOwn => 'உங்களையே கொண்டு வாருங்கள்';

  @override
  String get payYourSttProvider =>
      'Omi ஐ சுதந்திரமாகப் பயன்படுத்தவும். நீங்கள் உங்கள் STT வழங்குநரிடம் நேரடியாக பணம் செலுத்துங்கள்.';

  @override
  String get freeMinutesMonth => 'மாதத்திற்கு 1,200 இலவச நிமிடங்கள் அடங்கியுள்ளது. ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'ஹோஸ்ட் தேவை';

  @override
  String get validPortRequired => 'சரியான போர்ட் தேவை';

  @override
  String get validWebsocketUrlRequired => 'சரியான WebSocket URL தேவை (wss://)';

  @override
  String get apiUrlRequired => 'API URL தேவை';

  @override
  String get apiKeyRequired => 'API விசை தேவை';

  @override
  String get invalidJsonConfig => 'செல்லாத JSON உள்ளமைப்பு';

  @override
  String errorSaving(String error) {
    return 'சேமிக்கும்போது பிழை: $error';
  }

  @override
  String get configCopiedToClipboard => 'உள்ளமைப்பு கிளிப்போர்டிற்குக் கொpiए\'d';

  @override
  String get pasteJsonConfig => 'உங்கள் JSON உள்ளமைப்பைக் கீழே ஒட்டவும்:';

  @override
  String get addApiKeyAfterImport => 'நீங்கள் இறக்குமதি செய்ய வேண்டிய பிறகு உங்களுடைய API விசையைச் சேர்க்க வேண்டும்';

  @override
  String get paste => 'ஒட்டவும்';

  @override
  String get import => 'இறக்குமதி செய்யவும்';

  @override
  String get invalidProviderInConfig => 'உள்ளமைப்பில் செல்லாத வழங்குநர்';

  @override
  String importedConfig(String providerName) {
    return '$providerName உள்ளமைப்பைக் கொண்டு வந்தது';
  }

  @override
  String invalidJson(String error) {
    return 'செல்லாத JSON: $error';
  }

  @override
  String get provider => 'வழங்குநர்';

  @override
  String get live => 'நேரலை';

  @override
  String get onDevice => 'சாதனத்தில்';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'உங்கள் STT HTTP முனைப்பை உள்ளிடவும்';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'உங்கள் நேரலை STT WebSocket முனைப்பை உள்ளிடவும்';

  @override
  String get apiKey => 'API விசை';

  @override
  String get enterApiKey => 'உங்கள் API விசையை உள்ளிடவும்';

  @override
  String get storedLocallyNeverShared => 'உள்ளூராக சேமிக்கப்பட்ட, ஒருபோதும் பகிரப்படவில்லை';

  @override
  String get host => 'ஹோஸ்ட்';

  @override
  String get port => 'போர்ட்';

  @override
  String get advanced => 'மேம்பட்ட';

  @override
  String get configuration => 'உள்ளமைப்பு';

  @override
  String get requestConfiguration => 'கோரிக்கை உள்ளமைப்பு';

  @override
  String get responseSchema => 'பதிலுக்கான திட்டம்';

  @override
  String get modified => 'மாற்றப்பட்ட';

  @override
  String get resetRequestConfig => 'கோரிக்கை உள்ளமைப்பைக் இயல்புநிலைக்கு மீட்டமை';

  @override
  String get logs => 'பதிவுகள்';

  @override
  String get logsCopied => 'பதிவுகள் நகல் செய்யப்பட்டுள்ளன';

  @override
  String get noLogsYet => 'இன்னும் பதிவுகள் இல்லை. தனிப்பட்ட STT செயல்பாட்டைக் காண பதிவை உருவாக்கத் தொடங்கவும்.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device $reason ஐப் பயன்படுத்துகிறது. Omi பயன்படுத்தப்படும்.';
  }

  @override
  String get omiTranscription => 'Omi தட்டச்சு';

  @override
  String get bestInClassTranscription => 'பூஜ்ய அமைப்பின் சிறந்த தட்டச்சு';

  @override
  String get instantSpeakerLabels => 'உடனடி பேச்சாளர் பெயர்கள்';

  @override
  String get languageTranslation => '100+ மொழி மொழிபெயர்ப்பு';

  @override
  String get optimizedForConversation => 'உரையாடலுக்கு உகந்த';

  @override
  String get autoLanguageDetection => 'தானியங்கி மொழி கண்டறிதல்';

  @override
  String get highAccuracy => 'உচ்ச நிர்ভুலத்தன்மை';

  @override
  String get privacyFirst => 'தனிமை முதல்';

  @override
  String get saveChanges => 'மாற்றங்களைச் சேமிக்கவும்';

  @override
  String get resetToDefault => 'இயல்புநிலைக்கு மீட்டமை';

  @override
  String get viewTemplate => 'வார்ப்பை பாருங்கள்';

  @override
  String get trySomethingLike => 'போன்ற ஒன்றை முயற்சி செய்யவும்...';

  @override
  String get tryIt => 'இதை முயற்சி செய்யவும்';

  @override
  String get creatingPlan => 'திட்டம் உருவாக்குகிறது';

  @override
  String get developingLogic => 'தர்க்கத்தை வளர்த்து வருகிறது';

  @override
  String get designingApp => 'பயன்பாட்டை வடிவமைத்து வருகிறது';

  @override
  String get generatingIconStep => 'சின்னம் உருவாக்குகிறது';

  @override
  String get finalTouches => 'চূড়ান்த தொடர்பு';

  @override
  String get processing => 'செயல்பாட்டு மாற்றம்...';

  @override
  String get features => 'பண்புகள்';

  @override
  String get creatingYourApp => 'உங்கள் பயன்பாட்டை உருவாக்கிறது...';

  @override
  String get generatingIcon => 'சின்னம் உருவாக்குகிறது...';

  @override
  String get whatShouldWeMake => 'நாம் என்ன உருவாக்க வேண்டும்?';

  @override
  String get appName => 'பயன்பாட்டின் பெயர்';

  @override
  String get description => 'விளக்கம்';

  @override
  String get publicLabel => 'பொது';

  @override
  String get privateLabel => 'தனிப்பட்டது';

  @override
  String get free => 'இலவசம்';

  @override
  String get perMonth => '/ மாதம்';

  @override
  String get tailoredConversationSummaries => 'தனிப்பாக்கப்பட்ட உரையாடல் சுருக்கங்கள்';

  @override
  String get customChatbotPersonality => 'தனிப்பாக்கப்பட்ட சேட்போட் ஆளுமை';

  @override
  String get makePublic => 'பொதுவாக்க';

  @override
  String get anyoneCanDiscover => 'யாரும் உங்கள் பயன்பாட்டைக் கண்டுபிடிக்க முடியும்';

  @override
  String get onlyYouCanUse => 'நீங்கள் மட்டும் இந்தப் பயன்பாட்டைப் பயன்படுத்த முடியும்';

  @override
  String get paidApp => 'கொடுப்பனவு பயன்பாடு';

  @override
  String get usersPayToUse => 'பயனர்கள் உங்கள் பயன்பாட்டைப் பயன்படுத்த பணம் செலுத்துகிறார்கள்';

  @override
  String get freeForEveryone => 'அனைவருக்கும் இலவசம்';

  @override
  String get perMonthLabel => '/ மாதம்';

  @override
  String get creating => 'உருவாக்குகிறது...';

  @override
  String get createApp => 'பயன்பாட்டை உருவாக்கவும்';

  @override
  String get searchingForDevices => 'சாதனங்களைத் தேடிக்கொண்டிருக்கிறது...';

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
  String get pairingSuccessful => 'ஜோடியாக்கம் வெற்றிகரமாக முடிந்துவிட்டது';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch க்கு இணைக்கப் பிழை: $error';
  }

  @override
  String get dontShowAgain => 'மீண்டும் காட்டாதே';

  @override
  String get iUnderstand => 'நான் புரிந்து கொண்டேன்';

  @override
  String get enableBluetooth => 'Bluetooth ஐ இயக்கவும்';

  @override
  String get bluetoothNeeded =>
      'Omi உங்கள் உணர்வுமான சாதனத்துடன் இணைக்க Bluetooth தேவை. Bluetooth ஐ இயக்கவும் மற்றும் மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get contactSupport => 'ஆதரவுடன் যোগாசையை கொள்ளவா?';

  @override
  String get connectLater => 'பிறகு இணையுங்கள்';

  @override
  String get grantPermissions => 'அனுமதிகளை வழங்கவும்';

  @override
  String get backgroundActivity => 'பின்னணி செயல்பாடு';

  @override
  String get backgroundActivityDesc => 'Omi ஐ பின்னணிയில் இயங்க விடுங்கள் சிறந்த நிலைத்தன்மைக்கு';

  @override
  String get locationAccess => 'இட அணுகல்';

  @override
  String get locationAccessDesc => 'முழு அভிজ்ஞதைக்கு பின்னணி இட অணுகல் ஐ இயக்கவும்';

  @override
  String get notifications => 'அறிவிப்புகள்';

  @override
  String get notificationsDesc => 'தகவல் உள்வாங்குவதற்கு அறிவிப்புகளை இயக்கவும்';

  @override
  String get locationServiceDisabled => 'இட சேவை முடக்கப்பட்டுள்ளது';

  @override
  String get locationServiceDisabledDesc =>
      'இட சேவை முடக்கப்பட்டுள்ளது. அமைப்புகளுக்கு செல்லவும் > தனிமை & பாதுகாப்பு > இட சேவைகள் மற்றும் இதை இயக்கவும்';

  @override
  String get backgroundLocationDenied => 'பின்னணி இட அணுகல் மறுக்கப்பட்டுள்ளது';

  @override
  String get backgroundLocationDeniedDesc =>
      'சாதன அமைப்புகளுக்கு செல்லவும் மற்றும் இட அனுமதியை \"எப்போதும் அனுமதிக்க\" அமைக்கவும்';

  @override
  String get lovingOmi => 'Omi ஐ விரும்புகிறீர்களா?';

  @override
  String get leaveReviewIos =>
      'App Store இல் ஒரு மதிப்பாய்வு விட்டு மேலும் நபர்களை அடைய எங்களுக்கு உதவவும். உங்கள் பதிப்பு எங்களுக்கு உலகத்தைக் குறிக்கிறது!';

  @override
  String get leaveReviewAndroid =>
      'Google Play Store இல் ஒரு மதிப்பாய்வு விட்டு மேலும் நபர்களை அடைய எங்களுக்கு உதவவும். உங்கள் பதிப்பு எங்களுக்கு உலகத்தைக் குறிக்கிறது!';

  @override
  String get rateOnAppStore => 'App Store இல் மதிப்பிடவும்';

  @override
  String get rateOnGooglePlay => 'Google Play இல் மதிப்பிடவும்';

  @override
  String get maybeLater => 'ஒருவேளை பிறகு';

  @override
  String get speechProfileIntro =>
      'Omi உங்கள் இலக்குகள் மற்றும் உங்கள் குரலைக் கற்க வேண்டும். நீங்கள் இதை பிறகு மாற்ற முடிந்தது.';

  @override
  String get getStarted => 'தொடங்குங்கள்';

  @override
  String get allDone => 'அனைத்தும் முடிந்துவிட்டது!';

  @override
  String get keepGoing => 'தொடர்ந்து செல்லவும், நீங்கள் நன்றாக செய்கிறீர்கள்';

  @override
  String get skipThisQuestion => 'இந்தக் கேள்வியை தவிர்க்கவும்';

  @override
  String get skipForNow => 'இப்போதை தவிர்க்கவும்';

  @override
  String get connectionError => 'இணைப்பு பிழை';

  @override
  String get connectionErrorDesc =>
      'சேவையகத்துடன் இணைக்க முடியவில்லை. உங்கள் இணைய இணைப்பை சரிபார்க்கவும் மற்றும் மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get invalidRecordingMultipleSpeakers => 'செல்லாத பதிவு கண்டுபிடிக்கப்பட்டுள்ளது';

  @override
  String get multipleSpeakersDesc =>
      'பதிவில் பல பேச்சாளர்கள் உள்ளனர் என்று தோன்றுகிறது. நீங்கள் ஒரு조용한் இடத்தில் இருக்கிறீர்கள் என்பதை உறுதிசெய்து மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get tooShortDesc => 'போதுமான பேச்சு கண்டறிக்கப்படவில்லை. மேலும் பேச மற்றும் மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get invalidRecordingDesc =>
      'நீங்கள் குறைந்தபட்சம் 5 நொடிகளாவது பேசினர் என்பதை உறுதிசெய்து 90 நொடிகளுக்கு மேல் பேசவில்லை என்பதை உறுதிசெய்யவும்.';

  @override
  String get areYouThere => 'நீங்கள் இருக்கிறீர்களா?';

  @override
  String get noSpeechDesc =>
      'நாங்கள் எந்த பேச்சையும் கண்டறிய முடியவில்லை. நீங்கள் குறைந்தபட்சம் 10 நொடிகளாவது பேசினர் என்பதை உறுதிசெய்து 3 நிமிடங்களுக்கு மேல் பேசவில்லை.';

  @override
  String get connectionLost => 'இணைப்பு இழக்கப்பட்டுள்ளது';

  @override
  String get connectionLostDesc =>
      'இணைப்பு தடுக்கப்பட்டுள்ளது. உங்கள் இணைய இணைப்பை சரிபார்க்கவும் மற்றும் மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get tryAgain => 'மீண்டும் முயற்சி செய்யவும்';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass ஐ இணையுங்கள்';

  @override
  String get continueWithoutDevice => 'சாதனம் இல்லாமல் தொடரவும்';

  @override
  String get permissionsRequired => 'அனுமதிகள் தேவை';

  @override
  String get permissionsRequiredDesc =>
      'இந்தப் பயன்பாடு சரியாக வேலைக்கு Bluetooth மற்றும் இட அனுமதிகள் தேவை. கருவி அமைப்புகளில் அவற்றை இயக்கவும்.';

  @override
  String get openSettings => 'அமைப்புகளைத் திறக்கவும்';

  @override
  String get wantDifferentName => 'வேறு ஒன்றால் செல்ல விரும்புகிறீர்களா?';

  @override
  String get whatsYourName => 'உங்கள் பெயர் என்ன?';

  @override
  String get speakTranscribeSummarize => 'பேசவும். தட்டச்சு. சுருக்கியுங்கள்.';

  @override
  String get signInWithApple => 'Apple உடன் உள்நுழையவும்';

  @override
  String get signInWithGoogle => 'Google உடன் உள்நுழையவும்';

  @override
  String get byContinuingAgree => 'தொடர்ந்து செல்வதன் மூலம், நீங்கள் எங்கள் ';

  @override
  String get termsOfUse => 'பயன்பாட்டு விதிமுறைகளை';

  @override
  String get omiYourAiCompanion => 'Omi – உங்கள் AI சாங்கี';

  @override
  String get captureEveryMoment =>
      'ஒவ்வொரு தருணத்தையும் ஆட்டவும். AI-உயர்ந்த\nசுருக்கங்களைப் பெற்றுக் கொள்ளவும். பதிப்புகளை உருவாக்க வேண்டாம்.';

  @override
  String get appleWatchSetup => 'Apple Watch அமைப்பு';

  @override
  String get permissionRequestedExclaim => 'அனுமதி கோரப்பட்டுள்ளது!';

  @override
  String get microphonePermission => 'மைக்ரோபோன் அனுமதி';

  @override
  String get permissionGrantedNow =>
      'அனுமதி வழங்கப்பட்டுள்ளது! இப்போது:\n\nஉங்கள் கடிகாரத்தில் Omi பயன்பாட்டை திறந்து கீழே \"தொடரவும்\" ஐ தட்டவும்';

  @override
  String get needMicrophonePermission =>
      'நங்கள் மைக்ரோபோன் அனுமதி தேவை.\n\n1. \"அனுமதி வழங்குங்கள்\" தட்டவும்\n2. உங்கள் iPhone இல் அனுமதி அளிக்கவும்\n3. கடிகார பயன்பாடு மூடும்\n4. மீண்டும் திறந்து \"தொடரவும்\" ஐ தட்டவும்';

  @override
  String get grantPermissionButton => 'அனுமதி வழங்குங்கள்';

  @override
  String get needHelp => 'உதவி தேவை?';

  @override
  String get troubleshootingSteps =>
      'சிக்கலைத் தீர்க்க:\n\n1. Omi உங்கள் கடிகாரத்தில் நிறுவப்பட்டுள்ளதை உறுதிசெய்யவும்\n2. உங்கள் கடிகாரத்தில் Omi பயன்பாட்டை திறக்கவும்\n3. அனுமதி பாப்அப்பைத் தேடவும்\n4. பணிக்குறிப்பு செய்யப்பட்டு \"அனுமதி\" ஐ தட்டவும்\n5. உங்கள் கடிகாரத்தில் பயன்பாடு மூடும் - மீண்டும் திறக்கவும்\n6. உங்கள் iPhone இல் திரும்பி \"தொடரவும்\" ஐ தட்டவும்';

  @override
  String get recordingStartedSuccessfully => 'பதிவு வெற்றிகரமாக தொடங்கியுள்ளது!';

  @override
  String get permissionNotGrantedYet =>
      'அனுமதி இன்னும் வழங்கப்படவில்லை. உங்கள் கடிகாரத்தில் மைக்ரோபோன் அணுகல் அனுமதி செய்தீர்கள் என்பதை உறுதிசெய்து மீண்டும் திறந்துவிட்டீர்கள்.';

  @override
  String errorRequestingPermission(String error) {
    return 'அனுமதி கோரும்போது பிழை: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'பதிவைத் தொடங்கும்போது பிழை: $error';
  }

  @override
  String get selectPrimaryLanguage => 'உங்கள் முதன்மை மொழியைத் தேர்ந்தெடுக்கவும்';

  @override
  String get languageBenefits => 'তীக்ஷ்ணமான தட்டச்சு மற்றும் தனிப்பாக்கப்பட்ட அভிज்ஞதைக்கு உங்கள் மொழியை அமைக்கவும்';

  @override
  String get whatsYourPrimaryLanguage => 'உங்கள் முதன்மை மொழி என்ன?';

  @override
  String get selectYourLanguage => 'உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்';

  @override
  String get personalGrowthJourney => 'உங்கள் ஒவ்வொரு வார்த்தைக்கும் கேட்கும் AI உடன் உங்கள் தனிப்பட்ட வளர்ச்சி பயணம்.';

  @override
  String get actionItemsTitle => 'செய்ய வேண்டிய பணிகள்';

  @override
  String get actionItemsDescription => 'தட்ட திருத்தி • நீண்ட அழுத்தம் தேர்ந்தெடுக்க • செயல்களுக்கு சுழட்டவும்';

  @override
  String get tabToDo => 'செய்ய வேண்டியவை';

  @override
  String get tabDone => 'முடிந்தவை';

  @override
  String get tabOld => 'பழையவை';

  @override
  String get emptyTodoMessage => '🎉 அனைத்தும் சரியாக உள்ளன!\nபண்பில் செயல் பணிகள் இல்லை';

  @override
  String get emptyDoneMessage => 'இன்னும் முடிந்த பணிகள் இல்லை';

  @override
  String get emptyOldMessage => '✅ பழைய பணிகள் இல்லை';

  @override
  String get noItems => 'பணிகள் இல்லை';

  @override
  String get actionItemMarkedIncomplete => 'செயல் பணி முழுமையற்றதாக குறிக்கப்பட்டுள்ளது';

  @override
  String get actionItemCompleted => 'செயல் பணி முடிந்துவிட்டது';

  @override
  String get deleteActionItemTitle => 'செயல் பணியைத் நீக்கவும்';

  @override
  String get deleteActionItemMessage => 'இந்த செயல் பணியை நீக்க விரும்புகிறீர்களா?';

  @override
  String get deleteSelectedItemsTitle => 'தேர்ந்தெடுக்கப்பட்ட பணிகளை நீக்கவும்';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '$count தேர்ந்தெடுக்கப்பட்ட செயல் பணி$s நீக்க விரும்புகிறீர்களா?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'செயல் பணி \"$description\" நீக்கப்பட்டுள்ளது';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count செயல் பணி$s நீக்கப்பட்டுள்ளது';
  }

  @override
  String get failedToDeleteItem => 'செயல் பணியை நீக்க முடியவில்லை';

  @override
  String get failedToDeleteItems => 'பணிகளை நீக்க முடியவில்லை';

  @override
  String get failedToDeleteSomeItems => 'சில பணிகளை நீக்க முடியவில்லை';

  @override
  String get welcomeActionItemsTitle => 'செயல் பணிகளுக்கு தயாரிக்கப்பட்டுள்ளது';

  @override
  String get welcomeActionItemsDescription =>
      'உங்கள் AI தானாகவே உரையாடல்களிலிருந்து பணிகள் மற்றும் செய்ய வேண்டிய பணிகளை எழுப்பும். அவை உருவாக்கப்பட்டுள்ளபோது இங்கே தோன்றும்.';

  @override
  String get autoExtractionFeature => 'உரையாடல்களிலிருந்து தானாகவே எழுப்பப்பட்ட';

  @override
  String get editSwipeFeature => 'தட்ட திருத்தி, முடிக்க அல்லது நீக்க சுழட்டவும்';

  @override
  String itemsSelected(int count) {
    return '$count தேர்ந்தெடுக்கப்பட்ட';
  }

  @override
  String get selectAll => 'அனைத்தையும் தேர்ந்தெடுக்கவும்';

  @override
  String get deleteSelected => 'தேர்ந்தெடுக்கப்பட்டவற்றை நீக்கவும்';

  @override
  String get searchMemories => 'பதிவுகளைத் தேடவும்...';

  @override
  String get memoryDeleted => 'பதிவு நீக்கப்பட்டுள்ளது.';

  @override
  String get undo => 'மறுசெய்க';

  @override
  String get noMemoriesYet => '🧠 இன்னும் பதிவுகள் இல்லை';

  @override
  String get noAutoMemories => 'இன்னும் தானாக எழுப்பப்பட்ட பதிவுகள் இல்லை';

  @override
  String get noManualMemories => 'இன்னும் கைமுறையாக உருவாக்கப்பட்ட பதிவுகள் இல்லை';

  @override
  String get noMemoriesInCategories => 'இந்த வகைகளில் பதிவுகள் இல்லை';

  @override
  String get noMemoriesFound => '🔍 பதிவுகள் கிடைக்கவில்லை';

  @override
  String get addFirstMemory => 'உங்கள் முதல் பதிவைச் சேர்க்கவும்';

  @override
  String get clearMemoryTitle => 'Omi இன் பதிவை அழிக்கவும்';

  @override
  String get clearMemoryMessage => 'Omi இன் உங்கள் பற்றிய பதிவை அழிக்க விரும்புகிறீர்களா? இந்தச் செயல் மாற்றமுடியாது.';

  @override
  String get clearMemoryButton => 'பதிவு அழிக்கவும்';

  @override
  String get memoryClearedSuccess => 'Omi இன் உங்கள் பற்றிய பதிவு அழிக்கப்பட்டுள்ளது';

  @override
  String get noMemoriesToDelete => 'நீக்க பதிவுகள் இல்லை';

  @override
  String get createMemoryTooltip => 'புதிய பதிவை உருவாக்கவும்';

  @override
  String get createActionItemTooltip => 'புதிய செயல் பணியை உருவாக்கவும்';

  @override
  String get memoryManagement => 'பதிவு மேலாண்மை';

  @override
  String get filterMemories => 'பதிவுகளை வடிகட்டவும்';

  @override
  String totalMemoriesCount(int count) {
    return 'உங்களுக்கு $count மொத்த பதிவுகள் உள்ளன';
  }

  @override
  String get publicMemories => 'பொது பதிவுகள்';

  @override
  String get privateMemories => 'தனிப்பட்ட பதிவுகள்';

  @override
  String get makeAllPrivate => 'அனைத்து பதிவுகளையும் தனிப்பட்டாக்குங்கள்';

  @override
  String get makeAllPublic => 'அனைத்து பதிவுகளையும் பொதுவாக்குங்கள்';

  @override
  String get deleteAllMemories => 'அனைத்து பதிவுகளையும் நீக்கவும்';

  @override
  String get allMemoriesPrivateResult => 'அனைத்து பதிவுகளும் இப்போது தனிப்பட்டவை';

  @override
  String get allMemoriesPublicResult => 'அனைத்து பதிவுகளும் இப்போது பொதுவை';

  @override
  String get newMemory => '✨ புதிய பதிவு';

  @override
  String get editMemory => '✏️ பதிவை திருத்தவும்';

  @override
  String get memoryContentHint => 'நான் ஐஸ் கிரீம் சாப்பிட விரும்புவேன்...';

  @override
  String get failedToSaveMemory => 'சேமிக்க முடியவில்லை. உங்கள் இணைப்பை சரிபார்க்கவும்.';

  @override
  String get saveMemory => 'பதிவை சேமிக்கவும்';

  @override
  String get retry => 'மீண்டும் முயற்சி செய்யவும்';

  @override
  String get createActionItem => 'செயல் பணியை உருவாக்கவும்';

  @override
  String get editActionItem => 'செயல் பணியை திருத்தவும்';

  @override
  String get actionItemDescriptionHint => 'என்ன செய்ய வேண்டும்?';

  @override
  String get actionItemDescriptionEmpty => 'செயல் பணி விளக்கம் வெற்றிடமாக இருக்க முடியாது.';

  @override
  String get actionItemUpdated => 'செயல் பணி புதுப்பிக்கப்பட்டுள்ளது';

  @override
  String get failedToUpdateActionItem => 'செயல் பணியைப் புதுப்பிக்க முடியவில்லை';

  @override
  String get actionItemCreated => 'செயல் பணி உருவாக்கப்பட்டுள்ளது';

  @override
  String get failedToCreateActionItem => 'செயல் பணியை உருவாக்க முடியவில்லை';

  @override
  String get dueDate => 'காலக்கெடு';

  @override
  String get time => 'நேரம்';

  @override
  String get addDueDate => 'காலக்கெடு சேர்க்கவும்';

  @override
  String get pressDoneToSave => 'சேமிக்க முடிந்தது அழுத்தவும்';

  @override
  String get pressDoneToCreate => 'உருவாக்க முடிந்தது அழுத்தவும்';

  @override
  String get filterAll => 'அனைத்து';

  @override
  String get filterSystem => 'உங்களைப் பற்றி';

  @override
  String get filterInteresting => 'உள்ளறிவுகள்';

  @override
  String get filterManual => 'கைமுறை';

  @override
  String get completed => 'முடிந்தவை';

  @override
  String get markComplete => 'முடிந்ததாக குறிக்கவும்';

  @override
  String get actionItemDeleted => 'செயல் பணி நீக்கப்பட்டுள்ளது';

  @override
  String get failedToDeleteActionItem => 'செயல் பணியை நீக்க முடியவில்லை';

  @override
  String get deleteActionItemConfirmTitle => 'செயல் பணியைத் நீக்கவும்';

  @override
  String get deleteActionItemConfirmMessage => 'இந்த செயல் பணியை நீக்க விரும்புகிறீர்களா?';

  @override
  String get appLanguage => 'பயன்பாட்டு மொழி';

  @override
  String get appInterfaceSectionTitle => 'பயன்பாட்டு இடைமுகம்';

  @override
  String get speechTranscriptionSectionTitle => 'பேச்சு & தட்டச்சு';

  @override
  String get languageSettingsHelperText =>
      'பயன்பாட்டு மொழி மெனுக்கள் மற்றும் பொத்தான்கள் மாற்றுகிறது. பேச்சு மொழி உங்கள் பதிவுகளை எவ்வாறு தட்டச்சு செய்யப்படுகிறது என்பதைப் பாதிக்கிறது.';

  @override
  String get translationNotice => 'மொழிபெயர்ப்பு குறிப்பு';

  @override
  String get translationNoticeMessage =>
      'Omi உங்கள் முதன்மை மொழிতে உரையாடல்களை மொழிபெயர்க்கிறது. அমைப்புகளில் -> சுயவிவரங்களில் ஏதேனும் நேரம் அதைப் புதுப்பிக்கவும்.';

  @override
  String get pleaseCheckInternetConnection => 'உங்கள் இணைய இணைப்பை சரிபார்க்கவும் மற்றும் மீண்டும் முயற்சி செய்யவும்';

  @override
  String get pleaseSelectReason => 'ஒரு காரணத்தைத் தேர்ந்தெடுக்கவும்';

  @override
  String get tellUsMoreWhatWentWrong => 'என்ன தவறு நேற்றது என்பதுமாக மேலும் சொல்லுங்கள்...';

  @override
  String get selectText => 'உரையைத் தேர்ந்தெடுக்கவும்';

  @override
  String maximumGoalsAllowed(int count) {
    return 'அதிகபட்சம் $count இலக்குகள் அனுமதிக்கப்பட்டுள்ளன';
  }

  @override
  String get conversationCannotBeMerged => 'இந்த உரையாடல் ஒன்றிணைக்க முடியாது (பூட்டப்பட்ட அல்லது ஏற்கனவே ஒன்றிணைய)';

  @override
  String get pleaseEnterFolderName => 'ஒரு கோப்பெளின் பெயரை உள்ளிடவும்';

  @override
  String get failedToCreateFolder => 'கோப்பெளை உருவாக்க முடியவில்லை';

  @override
  String get failedToUpdateFolder => 'கோப்பெளைப் புதுப்பிக்க முடியவில்லை';

  @override
  String get folderName => 'கோப்பெளின் பெயர்';

  @override
  String get descriptionOptional => 'விளக்கம் (விரும்பினால்)';

  @override
  String get failedToDeleteFolder => 'கோப்பு அழிக்க முடியவில்லை';

  @override
  String get editFolder => 'கோப்பை திருத்து';

  @override
  String get deleteFolder => 'கோப்பை அழி';

  @override
  String get transcriptCopiedToClipboard => 'மொழிபெயர்ப்பு ক்ளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get summaryCopiedToClipboard => 'சுருக்கம் க்ளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get conversationUrlCouldNotBeShared => 'உரையாடல் URL பகிர முடியவில்லை.';

  @override
  String get urlCopiedToClipboard => 'URL ক்ளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get exportTranscript => 'மொழிபெயர்ப்பை ஏற்றுமதி செய்';

  @override
  String get exportSummary => 'சுருக்கத்தை ஏற்றுமதி செய்';

  @override
  String get exportButton => 'ஏற்றுமதி';

  @override
  String get actionItemsCopiedToClipboard => 'செயல் உருப்படிகள் க்ளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get summarize => 'சுருக்கு';

  @override
  String get generateSummary => 'சுருக்கம் உருவாக்கு';

  @override
  String get conversationNotFoundOrDeleted => 'உரையாடல் கண்டுபிடிக்கப்படவில்லை அல்லது நீக்கப்பட்டது';

  @override
  String get deleteMemory => 'நினைவகத்தை நீக்கு';

  @override
  String get thisActionCannotBeUndone => 'இந்த செயலை செயல்நீக்கம் செய்ய முடியாது.';

  @override
  String memoriesCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count memories',
      one: '1 memory',
      zero: '0 memories',
    );
    return '$_temp0';
  }

  @override
  String get noMemoriesInCategory => 'இந்த வகையில் இன்னும் நினைவுகள் இல்லை';

  @override
  String get addYourFirstMemory => 'உங்கள் முதல் நினைவை சேர்க்கவும்';

  @override
  String get firmwareDisconnectUsb => 'USB வழியை துண்டிக்கவும்';

  @override
  String get firmwareUsbWarning => 'புதுப்பிப்புகளின் போது USB இணைப்பு உங்கள் சாதனத்தை சேதமடையச் செய்யும்.';

  @override
  String get firmwareBatteryAbove15 => 'பேட்டரி 15% க்கு மேல்';

  @override
  String get firmwareEnsureBattery => 'உங்கள் சாதனத்தில் 15% பேட்டரி உள்ளதை உறுதிசெய்க.';

  @override
  String get firmwareStableConnection => 'நிலையான இணைப்பு';

  @override
  String get firmwareConnectWifi => 'WiFi அல்லது செல்லுலார் இணைப்புக்கு இணைக்கவும்.';

  @override
  String failedToStartUpdate(String error) {
    return 'புதுப்பிப்பை தொடங்க முடியவில்லை: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'புதுப்பிப்பிற்கு முன், உறுதிசெய்க:';

  @override
  String get confirmed => 'உறுதியான!';

  @override
  String get release => 'வெளியீடு';

  @override
  String get slideToUpdate => 'புதுப்பிக்க滑動';

  @override
  String copiedToClipboard(String title) {
    return '$title க்ளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';
  }

  @override
  String get batteryLevel => 'பேட்டரி நிலை';

  @override
  String get charging => 'சார்ஜ் ஆகிறது';

  @override
  String get productUpdate => 'பொருள் புதுப்பிப்பு';

  @override
  String get offline => 'இணைக்கப்படாதது';

  @override
  String get available => 'கிடைக்கிறது';

  @override
  String get unpairDeviceDialogTitle => 'சாதனத்தை இணையாக்கவும்';

  @override
  String get unpairDeviceDialogMessage =>
      'இது சாதனத்தை வேறு ஃபோனுக்கு இணைக்க இணையாக்கும். Settings > Bluetooth க்கு சென்று சாதனத்தை மறந்து செயல்முறையை முடிக்க வேண்டும்.';

  @override
  String get unpair => 'இணையாக்கு';

  @override
  String get unpairAndForgetDevice => 'சாதனத்தை இணையாக்கி மறந்துவிடு';

  @override
  String get unknownDevice => 'தெரியாதது';

  @override
  String get unknown => 'தெரியாதது';

  @override
  String get productName => 'பொருளின் பெயர்';

  @override
  String get serialNumber => 'தொடர் இலக்கம்';

  @override
  String get connected => 'இணைக்கப்பட்டுள்ளது';

  @override
  String get privacyPolicyTitle => 'தனியுரிமை கொள்கை';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label நகலெடுக்கப்பட்டது';
  }

  @override
  String get noApiKeysYet => 'இன்னும் API விசைகள் இல்லை';

  @override
  String get createKeyToGetStarted => 'தொடங்க விசை உருவாக்கவும்';

  @override
  String get configureSttProvider => 'STT வழங்குநரைக் கட்டமைக்கவும்';

  @override
  String get setWhenConversationsAutoEnd => 'உரையாடல்கள் தானாக முடிய சரிசெய்யவும்';

  @override
  String get importDataFromOtherSources => 'வேறு மூலங்களிலிருந்து தரவு இறக்குமதி செய்';

  @override
  String get debugAndDiagnostics => 'பிழையகற்றல் & நோயறிதல்';

  @override
  String get autoDeletesAfter3Days => '3 நாட்களுக்குப் பிறகு தானாக நீக்கப்படும்.';

  @override
  String get helpsDiagnoseIssues => 'சிக்கல்களைக் கண்டறிய உதவுகிறது';

  @override
  String get exportStartedMessage => 'ஏற்றுமதி தொடங்கியுள்ளது. இது சில வினாடிகளை எடுக்கலாம்...';

  @override
  String get exportConversationsToJson => 'உரையாடல்களை JSON கோப்புக்கு ஏற்றுமதி செய்';

  @override
  String get knowledgeGraphDeletedSuccess => 'அறிவு வரைபடம் வெற்றிகரமாக நீக்கப்பட்டது';

  @override
  String failedToDeleteGraph(String error) {
    return 'வரைபடத்தை நீக்க முடியவில்லை: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'அனைத்து முனைகள் மற்றும் இணைப்புகளைத் தெளிவு செய்';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.json இல் சேர்க்கவும்';

  @override
  String get connectAiAssistantsToData => 'AI உதவிக்காரர்களை உங்கள் தரவுக்கு இணைக்கவும்';

  @override
  String get useYourMcpApiKey => 'உங்கள் MCP API விசையைப் பயன்படுத்தவும்';

  @override
  String get realTimeTranscript => 'நிகழ்நேர மொழிபெயர்ப்பு';

  @override
  String get experimental => 'சோதனামூலக்';

  @override
  String get transcriptionDiagnostics => 'மொழிபெயர்ப்பு நோயறிதல்';

  @override
  String get detailedDiagnosticMessages => 'விস்தாரமான நோயறிதல் செய்திகள்';

  @override
  String get autoCreateSpeakers => 'தானாக பேசுநர்களை உருவாக்கு';

  @override
  String get autoCreateWhenNameDetected => 'பெயர் கண்டறியப்படும் போது தானாக உருவாக்கு';

  @override
  String get followUpQuestions => 'தொடர்ந்த கேள்விகள்';

  @override
  String get suggestQuestionsAfterConversations => 'உரையாடல்களுக்குப் பிறகு கேள்விகளைப் பரிந்துரைக்கவும்';

  @override
  String get goalTracker => 'இலக்கு ট்র்যாக்கர்';

  @override
  String get trackPersonalGoalsOnHomepage => 'முதற்பக்கத்தில் உங்கள் ব்যক்திগত இலக்குகளை ট்র்যாக் செய்';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'செயல் உருப்படி விளக்கம் காலியாக இருக்க முடியாது';

  @override
  String get saved => 'சேமிக்கப்பட்டது';

  @override
  String get overdue => 'தாமதமான';

  @override
  String get failedToUpdateDueDate => 'நிலுவையில் உள்ள தேதியை புதுப்பிக்க முடியவில்லை';

  @override
  String get markIncomplete => 'முடிக்கப்படாத என குறிக்கவும்';

  @override
  String get editDueDate => 'நிলவையில் உள்ள தேதியை திருத்து';

  @override
  String get setDueDate => 'நிலுவையில் உள்ள தேதி சரிசெய்';

  @override
  String get clearDueDate => 'நிலுவையில் உள்ள தேதியைத் தெளிவு செய்';

  @override
  String get failedToClearDueDate => 'நிலுவையில் உள்ள தேதியைத் தெளிவு செய்ய முடியவில்லை';

  @override
  String get mondayAbbr => 'திங்';

  @override
  String get tuesdayAbbr => 'செவ்';

  @override
  String get wednesdayAbbr => 'புத';

  @override
  String get thursdayAbbr => 'வியா';

  @override
  String get fridayAbbr => 'வெள்';

  @override
  String get saturdayAbbr => 'சனி';

  @override
  String get sundayAbbr => 'ஞாயி';

  @override
  String get howDoesItWork => 'இது எப்படி வேலை செய்கிறது?';

  @override
  String get sdCardSyncDescription =>
      'SD கார்டு ஒத்திசைவு உங்கள் நினைவுகளை SD கார்டிலிருந்து ஆப்பிற்கு இறக்குமதி செய்யும்';

  @override
  String get checksForAudioFiles => 'SD கார்டில் ஆடியோ கோப்புகளை சரிபார்க்கிறது';

  @override
  String get omiSyncsAudioFiles => 'Omi பின்னர் ஆடியோ கோப்புகளை சার்வரின் সাথে ஒத்திசைக்கிறது';

  @override
  String get serverProcessesAudio => 'சேவையகம் ஆடியோ கோப்புகளை செயலாக்கி நினைவுகளை உருவாக்குகிறது';

  @override
  String get youreAllSet => 'நீங்கள் அனைத்து தயாரிக்கப்பட்டுள்ளீர்கள்!';

  @override
  String get welcomeToOmiDescription =>
      'Omi க்கு வரவேற்கிறோம்! உங்கள் AI தோழி உரையாடல், பணிகள் மற்றும் பலவற்றை உங்களுக்கு உதவ தயாரிக்கப்பட்டுள்ளார்.';

  @override
  String get startUsingOmi => 'Omi ஐ பயன்படுத்த தொடங்கவும்';

  @override
  String get back => 'திரும்பவும்';

  @override
  String get keyboardShortcuts => 'விசைப்பலகை குறுக்குவழிகள்';

  @override
  String get toggleControlBar => 'கட்டுப்பாட்டு பட்டி மாற்று';

  @override
  String get pressKeys => 'விசைகளை அழுத்தவும்...';

  @override
  String get cmdRequired => '⌘ தேவை';

  @override
  String get invalidKey => 'தவறான விசை';

  @override
  String get space => 'உறுதி';

  @override
  String get search => 'தேடல்';

  @override
  String get searchPlaceholder => 'தேடவும்...';

  @override
  String get untitledConversation => 'தலைப்பற்ற உரையாடல்';

  @override
  String countRemaining(String count) {
    return '$count மீதமுள்ளது';
  }

  @override
  String get addGoal => 'இலக்கு சேர்க்கவும்';

  @override
  String get editGoal => 'இலக்கை திருத்து';

  @override
  String get icon => 'சின்னம்';

  @override
  String get goalTitle => 'இலக்கு தலைப்பு';

  @override
  String get current => 'தற்போதைய';

  @override
  String get target => 'লட்சியம்';

  @override
  String get saveGoal => 'சேமிக்கவும்';

  @override
  String get goals => 'இலக்குகள்';

  @override
  String get tapToAddGoal => 'இலக்கு சேர்க்க தட்டவும்';

  @override
  String welcomeBack(String name) {
    return 'மீண்டும் வரவேற்கிறோம், $name';
  }

  @override
  String get yourConversations => 'உங்கள் உரையாடல்கள்';

  @override
  String get reviewAndManageConversations => 'உங்கள் கைப்பற்றிய உரையாடல்களை மீளாய்வு செய்க மற்றும் நிர்வகிக்கவும்';

  @override
  String get startCapturingConversations => 'உங்கள் Omi சாதனம் உடன் உரையாடல்களை கைப்பற்ற தொடங்கவும் அவற்றை இங்கே காண.';

  @override
  String get useMobileAppToCapture => 'ஆடியோ கைப்பற்ற உங்கள் மொபைல் ஆப்பைப் பயன்படுத்தவும்';

  @override
  String get conversationsProcessedAutomatically => 'உரையாடல்கள் தானாக செயலாக்கப்படுகின்றன';

  @override
  String get getInsightsInstantly => 'உடனடியாக நுண்ணறிவு மற்றும் சுருக்கங்களைப் பெறவும்';

  @override
  String get showAll => 'அனைத்தும் காட்டு';

  @override
  String get noTasksForToday => 'இன்றைக்கு பணிகள் இல்லை.\nவேலைகள் அல்லது கையால் உருவாக்க Omi ஐ கேட்கவும்.';

  @override
  String get dailyScore => 'தினசரி மதிப்பெண்';

  @override
  String get dailyScoreDescription => 'செயல்படுத்தலில் நீங்கள் நன்கு\nமையாமவில்லை மதிப்பெண்.';

  @override
  String get searchResults => 'தேடல் முடிவுகள்';

  @override
  String get actionItems => 'செயல் உருப்படிகள்';

  @override
  String get tasksToday => 'இன்று';

  @override
  String get tasksTomorrow => 'நாளை';

  @override
  String get tasksNoDeadline => 'நিலுவையில் இல்லை';

  @override
  String get tasksLater => 'பிற்பாடு';

  @override
  String get loadingTasks => 'பணிகள் ஏற்றுகிறது...';

  @override
  String get tasks => 'பணிகள்';

  @override
  String get swipeTasksToIndent => 'பணிகளை உள்தள்ளுவதற்கு நெருக்கி இழுக்கவும், பிரிவுகளுக்கு இடையில் இழுக்கவும்';

  @override
  String get create => 'உருவாக்கு';

  @override
  String get noTasksYet => 'இன்னும் பணிகள் இல்லை';

  @override
  String get tasksFromConversationsWillAppear =>
      'உங்கள் உரையாடல்களிலிருந்து பணிகள் இங்கே தோன்றும்.\nகையால் சேர்க்க உருவாக்கவும் தட்டவும்.';

  @override
  String get monthJan => 'ஜனவரி';

  @override
  String get monthFeb => 'பிப்ரவரி';

  @override
  String get monthMar => 'மார்ச்';

  @override
  String get monthApr => 'ஏப்ரல்';

  @override
  String get monthMay => 'மே';

  @override
  String get monthJun => 'ஜூன்';

  @override
  String get monthJul => 'ஜூலை';

  @override
  String get monthAug => 'ஆகஸ்ட்';

  @override
  String get monthSep => 'செப்டம்பர்';

  @override
  String get monthOct => 'அக்டோபர்';

  @override
  String get monthNov => 'நவம்பர்';

  @override
  String get monthDec => 'டிசம்பர்';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'செயல் உருப்படி வெற்றிகரமாக புதுப்பிக்கப்பட்டது';

  @override
  String get actionItemCreatedSuccessfully => 'செயல் உருப்படி வெற்றிகரமாக உருவாக்கப்பட்டது';

  @override
  String get actionItemDeletedSuccessfully => 'செயல் உருப்படி வெற்றிகரமாக நீக்கப்பட்டது';

  @override
  String get deleteActionItem => 'செயல் உருப்படியை நீக்கு';

  @override
  String get deleteActionItemConfirmation =>
      'இந்த செயல் உருப்படியை நீக்க விரும்புகிறீர்களா? இந்த செயலை செயல்நீக்கம் செய்ய முடியாது.';

  @override
  String get enterActionItemDescription => 'செயல் உருப்படி விளக்கம் உள்ளிடவும்...';

  @override
  String get markAsCompleted => 'முடிந்தது என குறிக்கவும்';

  @override
  String get setDueDateAndTime => 'நிলுவையில் உள்ள தேதி மற்றும் நேரத்தை சரிசெய்';

  @override
  String get reloadingApps => 'பயன்பாடுகளை மீண்டும் ஏற்றுகிறது...';

  @override
  String get loadingApps => 'பயன்பாடுகள் ஏற்றுகிறது...';

  @override
  String get browseInstallCreateApps => 'பயன்பாடுகளை தேடுக, நிறுவ, மற்றும் உருவாக்குக';

  @override
  String get all => 'அனைத்து';

  @override
  String get open => 'திற';

  @override
  String get install => 'நிறுவ';

  @override
  String get noAppsAvailable => 'பயன்பாடுகள் கிடைக்கவில்லை';

  @override
  String get unableToLoadApps => 'பயன்பாடுகளை ஏற்ற முடியாது';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'உங்கள் தேடல் விதிமுறைகள் அல்லது வடிப்பிகளை சரிசெய்ய முயற்சி செய்க';

  @override
  String get checkBackLaterForNewApps => 'புதிய பயன்பாடுகளுக்கு பிற்பாடு திரும்பச் சரிபார்க்கவும்';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'உங்கள் இணைய இணைப்பை சரிபார்க்கவும் மற்றும் மீண்டும் முயற்சி செய்க';

  @override
  String get createNewApp => 'புதிய பயன்பாட்டை உருவாக்கு';

  @override
  String get buildSubmitCustomOmiApp => 'உங்கள் தனிப்பயன் Omi பயன்பாட்டை உருவாக்கி சமர்ப்பிக்கவும்';

  @override
  String get submittingYourApp => 'உங்கள் பயன்பாடு சமர்ப்பிக்கப்படுகிறது...';

  @override
  String get preparingFormForYou => 'உங்களுக்கான படிவம் தயாரிக்கப்படுகிறது...';

  @override
  String get appDetails => 'பயன்பாடு விவரங்கள்';

  @override
  String get paymentDetails => 'பணம் செலுத்துவது விவரங்கள்';

  @override
  String get previewAndScreenshots => 'முன்நோக்கு மற்றும் திரைப்பிடிப்புகள்';

  @override
  String get appCapabilities => 'பயன்பாடு திறன்கள்';

  @override
  String get aiPrompts => 'AI வசன குறிப்புகள்';

  @override
  String get chatPrompt => 'சட்டப்பூர்வ வசன குறிப்பு';

  @override
  String get chatPromptPlaceholder =>
      'நீங்கள் ஒரு அற்புத பயன்பாடு உள்ளீர், உபயோகி வினாக்களுக்கு பதிலளிப்பது மற்றும் அவர்களை நன்றாக உணர்வது உங்கள் வேலை...';

  @override
  String get conversationPrompt => 'உரையாடல் வசன குறிப்பு';

  @override
  String get conversationPromptPlaceholder =>
      'நீங்கள் ஒரு அற்புத பயன்பாடு உள்ளீர், உரையாடலின் மொழிபெயர்ப்பு மற்றும் சுருக்கம் உங்களுக்கு கொடுக்கப்படும்...';

  @override
  String get notificationScopes => 'அறிவிப்பு கணை';

  @override
  String get appPrivacyAndTerms => 'பயன்பாடு தனியுரிமை மற்றும் நிபந்தனைகள்';

  @override
  String get makeMyAppPublic => 'என் பயன்பாடு பொதுவாக்கு';

  @override
  String get submitAppTermsAgreement =>
      'இந்த பயன்பாட்டைச் சமர்ப்பிப்பதன் மூலம், நான் Omi AI சேவை விதிமுறைகள் மற்றும் தனியுரிமை கொள்கைக்கு ஒப்புக்கொள்ளுகிறேன்';

  @override
  String get submitApp => 'பயன்பாடு சமர்ப்பிக்கவும்';

  @override
  String get needHelpGettingStarted => 'தொடங்குவதற்கு உதவி தேவையா?';

  @override
  String get clickHereForAppBuildingGuides =>
      'பயன்பாடு உருவாக்கும் வழிகாட்டிகள் மற்றும் ஆவணங்களுக்கு இங்கே கிளிக் செய்க';

  @override
  String get submitAppQuestion => 'பயன்பாடு சமர்ப்பிக்கவுமா?';

  @override
  String get submitAppPublicDescription =>
      'உங்கள் பயன்பாடு மீளாய்வு செய்யப்பட்டு பொதுவாக்கப்படும். மீளாய்வின் போது கூட நீங்கள் உடனே இதைப் பயன்படுத்தத் தொடங்கலாம்!';

  @override
  String get submitAppPrivateDescription =>
      'உங்கள் பயன்பாடு மீளாய்வு செய்யப்பட்டு தனிப்பட்ட முறையில் உங்களுக்கு கிடைக்கும். மீளாய்வின் போது கூட நீங்கள் உடனே இதைப் பயன்படுத்தத் தொடங்கலாம்!';

  @override
  String get startEarning => 'சம்பாதிக்க தொடங்கவும்! 💰';

  @override
  String get connectStripeOrPayPal => 'உங்கள் பயன்பாடுக்கான பணம் பெற Stripe அல்லது PayPal ஐ இணைக்கவும்.';

  @override
  String get connectNow => 'இப்பொழுது இணைக்கவும்';

  @override
  String get installsCount => 'நிறுவல்கள்';

  @override
  String get uninstallApp => 'பயன்பாட்டை நீக்கவும்';

  @override
  String get subscribe => 'குsubscription்';

  @override
  String get dataAccessNotice => 'தரவு அணுகல் அறிவிப்பு';

  @override
  String get dataAccessWarning =>
      'இந்த பயன்பாடு உங்கள் தரவை அணுகும். Omi AI இந்த பயன்பாட்டால் உங்கள் தரவு எப்படி பயன்படுத்தப்படுகிறது, மாற்றப்படுகிறது அல்லது நீக்கப்படுகிறது என்பதற்கு பொறுப்பல்ல';

  @override
  String get installApp => 'பயன்பாடு நிறுவ';

  @override
  String get betaTesterNotice =>
      'நீங்கள் இந்த பயன்பாட்டின் பீட்டா சோதனையாளர்ஆக இருந்துள்ளீர்கள். இது இன்னும் பொதுவாக இல்லை. அது அங்கீகৃத முடிந்தவுடன் பொதுவாக இருக்கும்.';

  @override
  String get appUnderReviewOwner =>
      'உங்கள் பயன்பாடு மீளாய்வின் கீழ் உள்ளது மற்றும் கூ உங்களுக்கு மட்டுமே பார்வையாக இருக்கும். அது அங்கீகৃத முடிந்தவுடன் பொதுவாக இருக்கும்.';

  @override
  String get appRejectedNotice =>
      'உங்கள் பயன்பாடு நிராகரிக்கப்பட்டது. பயன்பாடு விவரங்களைப் புதுப்பிக்க மற்றும் மீளாய்வுக்கு மீண்டும் சமர்ப்பிக்க வேண்டும்.';

  @override
  String get setupSteps => 'நிறுவப்பட்ட படிகள்';

  @override
  String get setupInstructions => 'அமைப்பு வழிமுறைகள்';

  @override
  String get integrationInstructions => 'ஒருங்கிணைப்பு வழிமுறைகள்';

  @override
  String get preview => 'முன்நோக்கு';

  @override
  String get aboutTheApp => 'பயன்பாட்டைப் பற்றி';

  @override
  String get chatPersonality => 'சட்டப்பூர்வ ஆளுமை';

  @override
  String get ratingsAndReviews => 'রেटिङ्कुरु & மீளாய்வுகள்';

  @override
  String get noRatings => 'மதிப்பெண்கள் இல்லை';

  @override
  String ratingsCount(String count) {
    return '$count+ मतलब';
  }

  @override
  String get errorActivatingApp => 'பயன்பாடு செயல்படுத்துவதில் பிழை';

  @override
  String get integrationSetupRequired => 'இது ஒரு ஒருங்கிணைப்பு பயன்பாடு என்றால், அமைப்பு முடிந்துவிட்டதை உறுதிசெய்க.';

  @override
  String get installed => 'நிறுவப்பட்டுள்ளது';

  @override
  String get appIdLabel => 'பயன்பாடு ஐடி';

  @override
  String get appNameLabel => 'பயன்பாடு பெயர்';

  @override
  String get appNamePlaceholder => 'என் அற்புத பயன்பாடு';

  @override
  String get pleaseEnterAppName => 'பயன்பாடு பெயர் உள்ளிடவும்';

  @override
  String get categoryLabel => 'வகை';

  @override
  String get selectCategory => 'வகை தேர்ந்தெடுக்கவும்';

  @override
  String get descriptionLabel => 'விளக்கம்';

  @override
  String get appDescriptionPlaceholder =>
      'என் அற்புத பயன்பாடு ஒரு சிறந்த பயன்பாடு ஆகும் அதிசயமான விஷயங்களைச் செய்கிறது. இது சாவதை சிறந்த பயன்பாடு!';

  @override
  String get pleaseProvideValidDescription => 'செல்லுபடியாகும் விளக்கம் வழங்கவும்';

  @override
  String get appPricingLabel => 'பயன்பாடு விலை';

  @override
  String get noneSelected => 'எதுவுமே தேர்ந்தெடுக்கப்படவில்லை';

  @override
  String get appIdCopiedToClipboard => 'பயன்பாடு ஐடி ক்ளிப்போர்டுக்கு நகலெடுக்கப்பட்டது';

  @override
  String get appCategoryModalTitle => 'பயன்பாடு வகை';

  @override
  String get pricingFree => 'இலவசம்';

  @override
  String get pricingPaid => 'செலுத்தப்பட்ட';

  @override
  String get loadingCapabilities => 'திறன்கள் ஏற்றுகிறது...';

  @override
  String get filterInstalled => 'நிறுவப்பட்டுள்ளது';

  @override
  String get filterMyApps => 'என் பயன்பாடுகள்';

  @override
  String get clearSelection => 'தேர்வு தெளிவு செய்';

  @override
  String get filterCategory => 'வகை';

  @override
  String get rating4PlusStars => '4+ விண்மீன்';

  @override
  String get rating3PlusStars => '3+ விண்மீன்';

  @override
  String get rating2PlusStars => '2+ விண்மீன்';

  @override
  String get rating1PlusStars => '1+ விண்மீன்';

  @override
  String get filterRating => 'மதிப்பெண்';

  @override
  String get filterCapabilities => 'திறன்கள்';

  @override
  String get noNotificationScopesAvailable => 'அறிவிப்பு கணை கிடைக்கவில்லை';

  @override
  String get popularApps => 'நபர்கள் பயன்பாடுகள்';

  @override
  String get pleaseProvidePrompt => 'வசன குறிப்பு வழங்கவும்';

  @override
  String chatWithAppName(String appName) {
    return '$appName உடன் சட்டம் செய்க';
  }

  @override
  String get defaultAiAssistant => 'முன்னிருப்பு AI உதவிக்கார';

  @override
  String get readyToChat => '✨ சட்டம் செய்ய தயாரிக்கப்பட்டுள்ளது!';

  @override
  String get connectionNeeded => '🌐 இணைப்பு தேவை';

  @override
  String get startConversation => 'ஒரு உரையாடல் தொடங்கி மந்திரம் தொடங்கட்டும்';

  @override
  String get checkInternetConnection => 'உங்கள் இணைய இணைப்பை சரிபார்க்கவும்';

  @override
  String get wasThisHelpful => 'இது உதவிகரமாக இருந்ததா?';

  @override
  String get thankYouForFeedback => 'உங்கள் கருத்துக்கு நன்றி!';

  @override
  String get maxFilesUploadError => 'நீங்கள் ஒரு முறையில் 4 கோப்புகள் மட்டுமே அப்லோட் செய்யலாம்';

  @override
  String get attachedFiles => '📎 இணைக்கப்பட்ட கோப்புகள்';

  @override
  String get takePhoto => 'புகைப்படம் எடுக்கவும்';

  @override
  String get captureWithCamera => 'கேமரா உடன் பிடிக்கவும்';

  @override
  String get selectImages => 'படங்களைத் தேர்ந்தெடுக்கவும்';

  @override
  String get chooseFromGallery => 'கலைக்கூடத்திலிருந்து தேர்ந்தெடுக்கவும்';

  @override
  String get selectFile => 'ஒரு கோப்பைத் தேர்ந்தெடுக்கவும்';

  @override
  String get chooseAnyFileType => 'எந்த கோப்பு வகைத்தையும் தேர்ந்தெடுக்கவும்';

  @override
  String get cannotReportOwnMessages => 'நீங்கள் உங்கள் சொந்த செய்திகளைப் புகாரளிக்க முடியாது';

  @override
  String get messageReportedSuccessfully => '✅ செய்தி வெற்றிகரமாக புகாரளிக்கப்பட்டது';

  @override
  String get confirmReportMessage => 'இந்த செய்தியை புகாரளிக்க விரும்புகிறீர்களா?';

  @override
  String get selectChatAssistant => 'சட்ட உதவிக்கார் தேர்ந்தெடுக்கவும்';

  @override
  String get enableMoreApps => 'மேலும் பயன்பாடுகளை செயல்படுத்து';

  @override
  String get chatCleared => 'சட்டம் தெளிவு செய்கப்பட்டது';

  @override
  String get clearChatTitle => 'சட்டம் தெளிவு செய்யவுமா?';

  @override
  String get confirmClearChat => 'சட்டத்தைத் தெளிவு செய்ய விரும்புகிறீர்களா? இந்த செயலை செயல்நீக்கம் செய்ய முடியாது.';

  @override
  String get copy => 'நকல்';

  @override
  String get share => 'பகிர்';

  @override
  String get report => 'புகாரளி';

  @override
  String get microphonePermissionRequired => 'அழைப்பு செய்ய மைக்ரோஃபோன் அனுமতி தேவை';

  @override
  String get microphonePermissionDenied =>
      'மைக்ரோஃபோன் அனுமதி நிராகரிக்கப்பட்டது. System Preferences > Privacy & Security > Microphone இல் அனுமதி வழங்கவும்.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'மைக்ரோஃபோன் அனுமதி சரிபார்க்க முடியவில்லை: $error';
  }

  @override
  String get failedToTranscribeAudio => 'ஆடியோ மொழிபெயர்க்க முடியவில்லை';

  @override
  String get transcribing => 'மொழிபெயர்க்கிறது...';

  @override
  String get transcriptionFailed => 'மொழிபெயர்ப்பு தோல்வியுற்றது';

  @override
  String get discardedConversation => 'கைவிடப்பட்ட உரையாடல்';

  @override
  String get at => 'இல';

  @override
  String get from => 'இலிருந்து';

  @override
  String get copied => 'நகলெடுக்கப்பட்டது!';

  @override
  String get copyLink => 'இணைப்பு நகல்';

  @override
  String get hideTranscript => 'மொழிபெயர்ப்பு மறை';

  @override
  String get viewTranscript => 'மொழிபெயர்ப்பு பார்வை';

  @override
  String get conversationDetails => 'உரையாடல் விவரங்கள்';

  @override
  String get transcript => 'மொழிபெயர்ப்பு';

  @override
  String segmentsCount(int count) {
    return '$count தண்டங்கள்';
  }

  @override
  String get noTranscriptAvailable => 'மொழிபெயர்ப்பு கிடைக்கவில்லை';

  @override
  String get noTranscriptMessage => 'இந்த உரையாடலுக்கு மொழிபெயர்ப்பு இல்லை.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'உரையாடல் URL உருவாக்க முடியவில்லை.';

  @override
  String get failedToGenerateConversationLink => 'உரையாடல் இணைப்பு உருவாக்க முடியவில்லை';

  @override
  String get failedToGenerateShareLink => 'பகிர்வு இணைப்பு உருவாக்க முடியவில்லை';

  @override
  String get reloadingConversations => 'உரையாடல்கள் மீண்டும் ஏற்றுகிறது...';

  @override
  String get user => 'பயனர்';

  @override
  String get starred => 'நட்சத்திரங்கள் குறிப்பிட்டுள்ளது';

  @override
  String get date => 'தேதி';

  @override
  String get noResultsFound => 'முடிவுகள் கண்டுபிடிக்கப்படவில்லை';

  @override
  String get tryAdjustingSearchTerms => 'உங்கள் தேடல் விதிமுறைகளை சரிசெய்ய முயற்சி செய்க';

  @override
  String get starConversationsToFindQuickly => 'அவற்றை விரைவாகக் கண்டுபிடிக்க நட்சத்திரமுள்ள உரையாடல்கள்';

  @override
  String noConversationsOnDate(String date) {
    return '$date இல் உரையாடல்கள் இல்லை';
  }

  @override
  String get trySelectingDifferentDate => 'வேறு தேதியை தேர்ந்தெடுக்க முயற்சி செய்க';

  @override
  String get conversations => 'உரையாடல்கள்';

  @override
  String get chat => 'சட்டம்';

  @override
  String get actions => 'செயல்';

  @override
  String get syncAvailable => 'ஒத்திசைவு கிடைக்கிறது';

  @override
  String get referAFriend => 'நண்பரைக் குறிப்பிடவும்';

  @override
  String get help => 'உதவி';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Pro க்கு மேம்படுத்து';

  @override
  String get getOmiDevice => 'Omi சாதனத்தைப் பெறுக';

  @override
  String get wearableAiCompanion => 'அணிந்துகொள்ள AI தோழி';

  @override
  String get loadingMemories => 'நினைவுகள் ஏற்றுகிறது...';

  @override
  String get allMemories => 'அனைத்து நினைவுகள்';

  @override
  String get aboutYou => 'உங்களைப் பற்றி';

  @override
  String get manual => 'கையேடு';

  @override
  String get loadingYourMemories => 'உங்கள் நினைவுகள் ஏற்றுகிறது...';

  @override
  String get createYourFirstMemory => 'தொடங்குவதற்கு உங்கள் முதல் நினைவை உருவாக்கவும்';

  @override
  String get tryAdjustingFilter => 'உங்கள் தேடல் அல்லது வடிப்பை சரிசெய்ய முயற்சி செய்க';

  @override
  String get whatWouldYouLikeToRemember => 'நீங்கள் என்ன நினைவில் கொள்ள விரும்புகிறீர்கள்?';

  @override
  String get category => 'வகை';

  @override
  String get public => 'பொது';

  @override
  String get failedToSaveCheckConnection => 'சேமிக்க முடியவில்லை. உங்கள் இணைப்பை சரிபார்க்கவும்.';

  @override
  String get createMemory => 'நினைவு உருவாக்கு';

  @override
  String get deleteMemoryConfirmation => 'இந்த நினைவை நீக்க விரும்புகிறீர்களா? இந்த செயலை செயல்நீக்கம் செய்ய முடியாது.';

  @override
  String get makePrivate => 'தனிப்பட்ட செய்க';

  @override
  String get organizeAndControlMemories => 'உங்கள் நினைவுகளை ஒழுங்கு செய்க மற்றும் கட்டுப்பாட்டு';

  @override
  String get total => 'மொத்த';

  @override
  String get makeAllMemoriesPrivate => 'அனைத்து நினைவுகளை தனிப்பட்ட செய்க';

  @override
  String get setAllMemoriesToPrivate => 'அனைத்து நினைவுகளை தனிப்பட்ட பார்வையாக அமைக்கவும்';

  @override
  String get makeAllMemoriesPublic => 'அனைத்து நினைவுகளை பொது செய்க';

  @override
  String get setAllMemoriesToPublic => 'அனைத்து நினைவுகளை பொது பார்வையாக அமைக்கவும்';

  @override
  String get permanentlyRemoveAllMemories => 'Omi இலிருந்து அனைத்து நினைவுகளை நிரந்தரமாக நீக்கவும்';

  @override
  String get allMemoriesAreNowPrivate => 'அனைத்து நினைவுகள் இப்போது தனிப்பட்டவை';

  @override
  String get allMemoriesAreNowPublic => 'அனைத்து நினைவுகள் இப்போது பொது';

  @override
  String get clearOmisMemory => 'Omi ன் நினைவகம் தெளிவு செய்';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Omi ன் நினைவகம் தெளிவு செய்ய விரும்புகிறீர்களா? இந்த செயல் செயல்நீக்கம் செய்ய முடியாது மற்றும் அனைத்து $count நினைவுகளை நிரந்தரமாக நீக்கும்.';
  }

  @override
  String get omisMemoryCleared => 'உங்களைப் பற்றிய Omi ன் நினைவகம் தெளிவு செய்யப்பட்டது';

  @override
  String get welcomeToOmi => 'Omi க்கு வரவேற்கிறோம்';

  @override
  String get continueWithApple => 'Apple உடன் தொடரவும்';

  @override
  String get continueWithGoogle => 'Google மூலம் தொடரவும்';

  @override
  String get byContinuingYouAgree => 'தொடர்வதன் மூலம், நீங்கள் எங்கள் ';

  @override
  String get termsOfService => 'சேவை விதிகள்';

  @override
  String get and => ' மற்றும் ';

  @override
  String get dataAndPrivacy => 'தரவு மற்றும் இரகசியતை';

  @override
  String get secureAuthViaAppleId => 'Apple ID மூலம் பாதுகாப்பான அங்கீகாரம்';

  @override
  String get secureAuthViaGoogleAccount => 'Google கணக்கு மூலம் பாதுகாப்பான அங்கீகாரம்';

  @override
  String get whatWeCollect => 'நாங்கள் எதை சேகரிக்கிறோம்';

  @override
  String get dataCollectionMessage =>
      'தொடர்வதன் மூலம், உங்கள் உரையாடல்கள், பதிவுகள் மற்றும் ব்যக்তிগத தகவல்கள் நம் சர்வரில் பாதுகாப்பாகச் சேமிக்கப்படும், AI-இயக்கிய நுண்ணறிவுகளை வழங்க மற்றும் அனைத்து பயன்பாட்டு அம்சங்களை செயல்படுத்த.';

  @override
  String get dataProtection => 'தரவு பாதுகாப்பு';

  @override
  String get yourDataIsProtected => 'உங்கள் தரவு பாதுகாக்கப்பட்டுள்ளது மற்றும் நமது ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'உங்கள் முதன்மை மொழியைத் தேர்ந்தெடுக்கவும்';

  @override
  String get chooseYourLanguage => 'உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'சிறந்த Omi அভிজ্ঞதைக்கான உங்கள் விரும்பிய மொழியைத் தேர்ந்தெடுக்கவும்';

  @override
  String get searchLanguages => 'மொழிகளைத் தேடவும்...';

  @override
  String get selectALanguage => 'ஒரு மொழியைத் தேர்ந்தெடுக்கவும்';

  @override
  String get tryDifferentSearchTerm => 'வேறு தேடல் சொல்லை முயற்சி செய்யவும்';

  @override
  String get pleaseEnterYourName => 'உங்கள் பெயரை உள்ளிடவும்';

  @override
  String get nameMustBeAtLeast2Characters => 'பெயர் குறைந்தது 2 எழுத்துக்கள் இருக்க வேண்டும்';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'உங்களை எப்படி சম்போதிக்க வேண்டுமென்று சொல்லவும். இது உங்கள் Omi அভிজ்ஞதையை நபர்மயமாக்க உதவுகிறது.';

  @override
  String charactersCount(int count) {
    return '$count எழுத்துக்கள்';
  }

  @override
  String get enableFeaturesForBestExperience => 'உங்கள் சாதனத்தில் சிறந்த Omi அভிজ்ஞதைக்கான அம்சங்களை செயல்படுத்தவும்.';

  @override
  String get microphoneAccess => 'மைக்ரோஃபோன் அணுக்கம்';

  @override
  String get recordAudioConversations => 'ஆடியோ உரையாடல்களைப் பதிவு செய்யவும்';

  @override
  String get microphoneAccessDescription =>
      'உங்கள் உரையாடல்களைப் பதிவு செய்து எழுத்தாக்க வழங்க Omi மைக்ரோஃபோன் அணுக்கம் தேவை.';

  @override
  String get screenRecording => 'திரை பதிவு';

  @override
  String get captureSystemAudioFromMeetings => 'சந்திப்புகளிலிருந்து கணினி ஆடியோவைப் பிடிக்கவும்';

  @override
  String get screenRecordingDescription =>
      'உங்கள் உலாவி-அடிப்படையிலான சந்திப்புகளிலிருந்து கணினி ஆடியோவைப் பிடிக்க Omi திரை பதிவு அনுமதி தேவை.';

  @override
  String get accessibility => 'அணுகல்தன்மை';

  @override
  String get detectBrowserBasedMeetings => 'உலாவி-அடிப்படையிலான சந்திப்புகளைக் கண்டறியவும்';

  @override
  String get accessibilityDescription =>
      'நீங்கள் உங்கள் உலாவியில் Zoom, Meet அல்லது Teams சந்திப்புகளில் சேரும்போது கண்டறிய Omi அணுகல்தன்மை அனுமதி தேவை.';

  @override
  String get pleaseWait => 'தயவு செய்து காத்திருங்கள்...';

  @override
  String get joinTheCommunity => 'சமூகத்தில் சேரவும்!';

  @override
  String get loadingProfile => 'சுயவிவரம் ஏற்றப்படுகிறது...';

  @override
  String get profileSettings => 'சுயவிவர அமைப்புகள்';

  @override
  String get noEmailSet => 'மின்னஞ்சல் அமைக்கப்படவில்லை';

  @override
  String get userIdCopiedToClipboard => 'பயனர் ID கிளிப்போர்டில் நகல் செய்யப்பட்டது';

  @override
  String get yourInformation => 'உங்கள் தகவல்';

  @override
  String get setYourName => 'உங்கள் பெயரை அமைக்கவும்';

  @override
  String get changeYourName => 'உங்கள் பெயரை மாற்றவும்';

  @override
  String get voiceAndPeople => 'குரல் மற்றும் மக்கள்';

  @override
  String get teachOmiYourVoice => 'Omi-க்கு உங்கள் குரலைக் கற்பிக்கவும்';

  @override
  String get tellOmiWhoSaidIt => 'Omi-க்கு யார் சொன்னது என்று சொல்லவும் 🗣️';

  @override
  String get payment => 'பணம் செலுத்துதல்';

  @override
  String get addOrChangeYourPaymentMethod => 'உங்கள் பணம் செலுத்தும் முறையைச் சேர்க்கவும் அல்லது மாற்றவும்';

  @override
  String get preferences => 'விருப்பங்கள்';

  @override
  String get helpImproveOmiBySharing => 'அனாமத மூல பகுப்பாய்வு தரவுகளைப் பகிர்ந்து Omi மேம்படுத்த உதவுங்கள்';

  @override
  String get deleteAccount => 'கணக்கை நீக்கவும்';

  @override
  String get deleteYourAccountAndAllData => 'உங்கள் கணக்கு மற்றும் அனைத்து தரவையும் நீக்கவும்';

  @override
  String get clearLogs => 'பதிவுகளைத் துடைக்கவும்';

  @override
  String get debugLogsCleared => 'பிழைதிருத்த பதிவுகள் துடைக்கப்பட்டுள்ளது';

  @override
  String get exportConversations => 'உரையாடல்களை ஏற்றுமதி செய்யவும்';

  @override
  String get exportAllConversationsToJson => 'உங்கள் அனைத்து உரையாடல்களை JSON ফাইலுக்கு ஏற்றுமதி செய்யவும்.';

  @override
  String get conversationsExportStarted =>
      'உரையாடல்கள் ஏற்றுமதி தொடங்கியுள்ளது. இது சில வினாடிகள் எடுக்கலாம், தயவு செய்து காத்திருங்கள்.';

  @override
  String get mcpDescription =>
      'Omi ஐ மற்ற பயன்பாடுகளுடன் இணைக்க உங்கள் நினைவுகள் மற்றும் உரையாடல்களைப் படிக்க, தேட மற்றும் நிர்வகிக்க. ஒரு முக்கியத்தை உருவாக்கவும் தொடங்க.';

  @override
  String get apiKeys => 'API விசைகள்';

  @override
  String errorLabel(String error) {
    return 'பிழை: $error';
  }

  @override
  String get noApiKeysFound => 'API விசைகள் கிடைக்கவில்லை. தொடங்க ஒன்றை உருவாக்கவும்.';

  @override
  String get advancedSettings => 'மேம்பட்ட அமைப்புகள்';

  @override
  String get triggersWhenNewConversationCreated => 'புதிய உரையாடல் உருவாக்கப்பட்டபோது தூண்டப்படுகிறது.';

  @override
  String get triggersWhenNewTranscriptReceived => 'புதிய எழுத்தாக்கம் பெறப்பட்டபோது தூண்டப்படுகிறது.';

  @override
  String get realtimeAudioBytes => 'நிகழ் நேர ஆடியோ பைட்குகள்';

  @override
  String get triggersWhenAudioBytesReceived => 'ஆடியோ பைட்குகள் பெறப்பட்டபோது தூண்டப்படுகிறது.';

  @override
  String get everyXSeconds => 'ஒவ்வொரு x வினாடிக்கும்';

  @override
  String get triggersWhenDaySummaryGenerated => 'நாள் சுருக்கம் உருவாக்கப்பட்டபோது தூண்டப்படுகிறது.';

  @override
  String get tryLatestExperimentalFeatures => 'Omi குழுவின் சமீபத்திய சோதனামূலக அம்சங்களை முயற்சி செய்யவும்.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'எழுத்தாக்க சேவை நோயறிதல் நிலை';

  @override
  String get enableDetailedDiagnosticMessages =>
      'எழுத்தாக்க சேவையிலிருந்து விস்தரிக்கப்பட்ட நோயறிதல் செய்திகளை செயல்படுத்தவும்';

  @override
  String get autoCreateAndTagNewSpeakers => 'புதிய பேச்சாளர்களை தானாக உருவாக்கவும் மற்றும் குறியிடவும்';

  @override
  String get automaticallyCreateNewPerson => 'எழுத்தாக்கத்தில் பெயர் கண்டறியப்பட்டபோது தானாக புதிய நபரை உருவாக்கவும்.';

  @override
  String get pilotFeatures => 'பைலட் அம்சங்கள்';

  @override
  String get pilotFeaturesDescription => 'இந்த அம்சங்கள் சோதனைகள் மற்றும் உதவி உத்தரவாதம் இல்லை.';

  @override
  String get suggestFollowUpQuestion => 'பின்தொடர்ந்து கேள்வியை பரிந்துரைக்கவும்';

  @override
  String get saveSettings => 'அமைப்புகளைச் சேமிக்கவும்';

  @override
  String get syncingDeveloperSettings => 'டெவலப்பர் அமைப்புகளை ஒத்திசைக்கிறது...';

  @override
  String get summary => 'சுருக்கம்';

  @override
  String get auto => 'தானாக';

  @override
  String get noSummaryForApp =>
      'இந்த பயன்பாட்டிற்கு சுருக்கம் கிடைக்கவில்லை. சிறந்த முடிவுக்கு மற்றொரு பயன்பாட்டை முயற்சி செய்யவும்.';

  @override
  String get tryAnotherApp => 'மற்றொரு பயன்பாட்டை முயற்சி செய்யவும்';

  @override
  String generatedBy(String appName) {
    return '$appName மூலம் உருவாக்கப்பட்டது';
  }

  @override
  String get overview => 'மேலோட்டம்';

  @override
  String get otherAppResults => 'மற்ற பயன்பாட்டு முடிவுகள்';

  @override
  String get unknownApp => 'தெரியாத பயன்பாடு';

  @override
  String get noSummaryAvailable => 'சுருக்கம் கிடைக்கவில்லை';

  @override
  String get conversationNoSummaryYet => 'இந்த உரையாடலுக்கு இன்னும் சுருக்கம் இல்லை.';

  @override
  String get chooseSummarizationApp => 'சுருக்க பயன்பாட்டைத் தேர்ந்தெடுக்கவும்';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName இயல்புநிலை சுருக்க பயன்பாடாக அமைக்கப்பட்டது';
  }

  @override
  String get letOmiChooseAutomatically => 'Omi சிறந்த பயன்பாட்டைத் தானாக தேர்ந்தெடுக்க அனுமதிக்கவும்';

  @override
  String get deleteConversationConfirmation =>
      'இந்த உரையாடலை நீக்க விரும்புகிறீர்களா? இந்த செயலை செயல்தவிர்க்க முடியாது.';

  @override
  String get conversationDeleted => 'உரையாடல் நீக்கப்பட்டது';

  @override
  String get generatingLink => 'இணைப்பை உருவாக்கிறது...';

  @override
  String get editConversation => 'உரையாடலை திருத்தவும்';

  @override
  String get conversationLinkCopiedToClipboard => 'உரையாடல் இணைப்பு கிளிப்போர்டில் நகல் செய்யப்பட்டது';

  @override
  String get conversationTranscriptCopiedToClipboard => 'உரையாடல் எழுத்தாக்கம் கிளிப்போர்டில் நகல் செய்யப்பட்டது';

  @override
  String get editConversationDialogTitle => 'உரையாடலை திருத்தவும்';

  @override
  String get changeTheConversationTitle => 'உரையாடல் பெயரை மாற்றவும்';

  @override
  String get conversationTitle => 'உரையாடல் பெயர்';

  @override
  String get enterConversationTitle => 'உரையாடல் பெயரை உள்ளிடவும்...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'உரையாடல் பெயர் வெற்றிகரமாக புதுப்பிக்கப்பட்டது';

  @override
  String get failedToUpdateConversationTitle => 'உரையாடல் பெயரைப் புதுப்பிக்க தவறிவிட்டது';

  @override
  String get errorUpdatingConversationTitle => 'உரையாடல் பெயரைப் புதுப்பிப்பதில் பிழை';

  @override
  String get settingUp => 'அமைக்கப்படுகிறது...';

  @override
  String get startYourFirstRecording => 'உங்கள் முதல் பதிவைத் தொடங்கவும்';

  @override
  String get preparingSystemAudioCapture => 'கணினி ஆடியோ பிடிப்பைத் தயாரிக்கிறது';

  @override
  String get clickTheButtonToCaptureAudio =>
      'நிகழ்நேர எழுத்தாக்கம், AI நுண்ணறிவுகள் மற்றும் தானாக சேமிக்கத்திற்கான ஆடியோவைப் பிடிக்க பொத்தானைக் கிளிக் செய்யவும்.';

  @override
  String get reconnecting => 'மீண்டும் இணைக்கிறது...';

  @override
  String get recordingPaused => 'பதிவு இடைநிறுத்தப்பட்டுள்ளது';

  @override
  String get recordingActive => 'பதிவு সক்திய';

  @override
  String get startRecording => 'பதிவைத் தொடங்கவும்';

  @override
  String resumingInCountdown(String countdown) {
    return '${countdown}s இல் மீண்டும் தொடங்குகிறது...';
  }

  @override
  String get tapPlayToResume => 'மீண்டும் தொடர்ந்து செயல்பட பிளே செய்யவும்';

  @override
  String get listeningForAudio => 'ஆடியோவுக்கு கேட்டறிதல் செய்யப்படுகிறது...';

  @override
  String get preparingAudioCapture => 'ஆடியோ பிடிப்பைத் தயாரிக்கிறது';

  @override
  String get clickToBeginRecording => 'பதிவை தொடங்க கிளிக் செய்யவும்';

  @override
  String get translated => 'மொழிபெயர்க்கப்பட்டது';

  @override
  String get liveTranscript => 'நிகழ்நேர எழுத்தாக்கம்';

  @override
  String segmentsSingular(String count) {
    return '$count பகுதி';
  }

  @override
  String segmentsPlural(String count) {
    return '$count பகுதிகள்';
  }

  @override
  String get startRecordingToSeeTranscript => 'நிகழ்நேர எழுத்தாக்கம் பார்க்க பதிவை தொடங்கவும்';

  @override
  String get paused => 'இடைநிறுத்தப்பட்டுள்ளது';

  @override
  String get initializing => 'தொடக்கம் செய்யப்படுகிறது...';

  @override
  String get recording => 'பதிவு';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'மைக்ரோஃபோன் மாற்றப்பட்டது. ${countdown}s இல் மீண்டும் தொடங்குகிறது';
  }

  @override
  String get clickPlayToResumeOrStop => 'மீண்டும் தொடர்ந்து செயல்பட பிளே அல்லது நிறுத்த கிளிக் செய்யவும்';

  @override
  String get settingUpSystemAudioCapture => 'கணினி ஆடியோ பிடிப்பை அமைக்கிறது';

  @override
  String get capturingAudioAndGeneratingTranscript => 'ஆடியோவைப் பிடித்து எழுத்தாக்கத்தை உருவாக்கிறது';

  @override
  String get clickToBeginRecordingSystemAudio => 'கணினி ஆடியோவைப் பதிவு செய்ய தொடங்க கிளிக் செய்யவும்';

  @override
  String get you => 'நீங்கள்';

  @override
  String speakerWithId(String speakerId) {
    return 'பேச்சாளர் $speakerId';
  }

  @override
  String get translatedByOmi => 'omi மூலம் மொழிபெயர்க்கப்பட்டது';

  @override
  String get backToConversations => 'உரையாடல்களுக்குத் திரும்பவும்';

  @override
  String get systemAudio => 'கணினி';

  @override
  String get mic => 'மைக்';

  @override
  String audioInputSetTo(String deviceName) {
    return 'ஆடியோ உள்ளீடு $deviceName க்கு அமைக்கப்பட்டது';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'ஆடியோ சாதனத்தை மாற்றுவதில் பிழை: $error';
  }

  @override
  String get selectAudioInput => 'ஆடியோ உள்ளீட்டைத் தேர்ந்தெடுக்கவும்';

  @override
  String get loadingDevices => 'சாதனங்கள் ஏற்றப்படுகிறது...';

  @override
  String get settingsHeader => 'அமைப்புகள்';

  @override
  String get plansAndBilling => 'திட்டங்கள் மற்றும் பில்லிங்';

  @override
  String get calendarIntegration => 'நாட்காட்டி ஒருங்கிணைப்பு';

  @override
  String get dailySummary => 'தினசரி சுருக்கம்';

  @override
  String get developer => 'டெவலப்பர்';

  @override
  String get about => 'பற்றி';

  @override
  String get selectTime => 'நேரத்தைத் தேர்ந்தெடுக்கவும்';

  @override
  String get accountGroup => 'கணக்கு';

  @override
  String get signOutQuestion => 'வெளியேற?';

  @override
  String get signOutConfirmation => 'வெளியேற விரும்புகிறீர்களா?';

  @override
  String get customVocabularyHeader => 'தனிப்பயன் சொல்தொகுப்பு';

  @override
  String get addWordsDescription => 'Omi எழுத்தாக்கத்தின் போது கண்டுபிடிக்க வேண்டிய சொற்களைச் சேர்க்கவும்.';

  @override
  String get enterWordsHint => 'சொற்களை உள்ளிடவும் (காற்புள்ளியால் பிரிக்கப்பட்டது)';

  @override
  String get dailySummaryHeader => 'தினசரி சுருக்கம்';

  @override
  String get dailySummaryTitle => 'தினசரி சுருக்கம்';

  @override
  String get dailySummaryDescription =>
      'உங்கள் நாளின் உரையாடல்களின் நபர்மயமான சுருக்கத்தைப் பெற்று அறிவிப்பாக வழங்கப்படுகிறது.';

  @override
  String get deliveryTime => 'விநியோக நேரம்';

  @override
  String get deliveryTimeDescription => 'உங்கள் தினசரி சுருக்கத்தைப் பெற வேண்டிய நேரம்';

  @override
  String get subscription => 'சந்தா';

  @override
  String get viewPlansAndUsage => 'திட்டங்கள் மற்றும் பயன்பாட்டைப் பார்க்கவும்';

  @override
  String get viewPlansDescription => 'உங்கள் சந்தாவை நிர்வகிக்கவும் மற்றும் பயன்பாட்டு புள்ளிவிவரங்களைக் காணவும்';

  @override
  String get addOrChangePaymentMethod => 'உங்கள் பணம் செலுத்தும் முறையைச் சேர்க்கவும் அல்லது மாற்றவும்';

  @override
  String get displayOptions => 'காட்சி விருப்பங்கள்';

  @override
  String get showMeetingsInMenuBar => 'மெனு பட்டையில் சந்திப்புகளைக் காட்டவும்';

  @override
  String get displayUpcomingMeetingsDescription => 'மெனு பட்டையில் வரவிருக்கும் சந்திப்புகளைக் காட்டவும்';

  @override
  String get showEventsWithoutParticipants => 'பங்கேற்றாளர்கள் இல்லாத நிகழ்வுகளைக் காட்டவும்';

  @override
  String get includePersonalEventsDescription => 'பங்கேற்றாளர்கள் இல்லாத ব்যক்তிগத நிகழ்வுகளைச் சேர்க்கவும்';

  @override
  String get upcomingMeetings => 'வரவிருக்கும் சந்திப்புகள்';

  @override
  String get checkingNext7Days => 'அடுத்த 7 நாட்களைச் சரிபார்க்கிறது';

  @override
  String get shortcuts => 'குறுக்குவழிகள்';

  @override
  String get shortcutChangeInstruction => 'மாற்ற குறுக்குவழியைக் கிளிக் செய்யவும். ரத்து செய்ய Escape ஐ அழுத்தவும்.';

  @override
  String get configureSTTProvider => 'STT வழங்குநரை கட்டமைக்கவும்';

  @override
  String get setConversationEndDescription => 'உரையாடல்கள் தானாக முடியும் நேரத்தை அமைக்கவும்';

  @override
  String get importDataDescription => 'மற்ற மூலங்களிலிருந்து தரவை இறக்குமதி செய்யவும்';

  @override
  String get exportConversationsDescription => 'உரையாடல்களை JSON இல் ஏற்றுமதி செய்யவும்';

  @override
  String get exportingConversations => 'உரையாடல்களை ஏற்றுமதி செய்கிறது...';

  @override
  String get clearNodesDescription => 'அனைத்து முனைகள் மற்றும் இணைப்புகளைத் துடைக்கவும்';

  @override
  String get deleteKnowledgeGraphQuestion => 'அறிவு வரைபடத்தை நீக்கவா?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'இது அனைத்து பெறப்பட்ட அறிவு வரைபட தரவையும் நீக்கும். உங்கள் அசல் நினைவுகள் பாதுகாப்பாக இருக்கும்.';

  @override
  String get connectOmiWithAI => 'Omi ஐ AI உதவியாளர்களுடன் இணைக்கவும்';

  @override
  String get noAPIKeys => 'API விசைகள் இல்லை. தொடங்க ஒன்றை உருவாக்கவும்.';

  @override
  String get autoCreateWhenDetected => 'பெயர் கண்டறியப்பட்டபோது தானாக உருவாக்கவும்';

  @override
  String get trackPersonalGoals => 'முகப்பில் ব்যக்তிगத இலக்குகளைக் கண்காணிக்கவும்';

  @override
  String get endpointURL => 'இறுதிப்புள்ளி URL';

  @override
  String get links => 'இணைப்புகள்';

  @override
  String get discordMemberCount => 'Discord இல் 8000+ உறுப்பினர்கள்';

  @override
  String get userInformation => 'பயனர் தகவல்';

  @override
  String get capabilities => 'திறன்கள்';

  @override
  String get previewScreenshots => 'பதிவுகளின் முன்னோட்டத்தைக் காணவும்';

  @override
  String get holdOnPreparingForm => 'பொறுங்கள், நாங்கள் உங்களுக்காக படிவத்தைத் தயாரிக்கிறோம்';

  @override
  String get bySubmittingYouAgreeToOmi => 'சமர்ப்பிப்பதன் மூலம், நீங்கள் Omi ';

  @override
  String get termsAndPrivacyPolicy => 'விதிகள் மற்றும் இரகசியத கொள்கை';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'சிக்கல்களை நோயறிய உதவுகிறது. 3 நாட்களுக்குப் பிறகு தானாக நீக்கப்படுகிறது.';

  @override
  String get manageYourApp => 'உங்கள் பயன்பாட்டை நிர்வகிக்கவும்';

  @override
  String get updatingYourApp => 'உங்கள் பயன்பாட்டை புதுப்பிக்கிறது';

  @override
  String get fetchingYourAppDetails => 'உங்கள் பயன்பாட்டு விவரங்களைப் பெறுகிறது';

  @override
  String get updateAppQuestion => 'பயன்பாட்டை புதுப்பிக்கவா?';

  @override
  String get updateAppConfirmation =>
      'உங்கள் பயன்பாட்டை புதுப்பிக்க விரும்புகிறீர்களா? நமது குழு மதிப்பாய்வு செய்த பிறகு மாற்றங்கள் பிரதிபலிக்கும்.';

  @override
  String get updateApp => 'பயன்பாட்டை புதுப்பிக்கவும்';

  @override
  String get createAndSubmitNewApp => 'புதிய பயன்பாட்டை உருவாக்கி சமர்ப்பிக்கவும்';

  @override
  String appsCount(String count) {
    return 'பயன்பாடுகள் ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'தனிப்பட்ட பயன்பாடுகள் ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'பொதுப் பயன்பாடுகள் ($count)';
  }

  @override
  String get newVersionAvailable => 'புதிய பதிப்பு கிடைக்கிறது 🎉';

  @override
  String get no => 'இல்லை';

  @override
  String get subscriptionCancelledSuccessfully =>
      'சந்தா வெற்றிகரமாக ரத்து செய்யப்பட்டது. இது தற்போதைய பில்லிங் காலத்தின் முடிவு வரை சক்திய நிலையில் இருக்கும்.';

  @override
  String get failedToCancelSubscription => 'சந்தாவை ரத்து செய்ய தவறிவிட்டது. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get invalidPaymentUrl => 'தவறான பணம் செலுத்தும் URL';

  @override
  String get permissionsAndTriggers => 'அனுமதிகள் மற்றும் ট்রிகர்கள்';

  @override
  String get chatFeatures => 'சாட் அம்சங்கள்';

  @override
  String get uninstall => 'நிறுவுதல் நீக்கவும்';

  @override
  String get installs => 'நிறுவல்கள்';

  @override
  String get priceLabel => 'விலை';

  @override
  String get updatedLabel => 'புதுப்பிக்கப்பட்டது';

  @override
  String get createdLabel => 'உருவாக்கப்பட்டது';

  @override
  String get featuredLabel => 'சிறப்பிடப்பட்டது';

  @override
  String get cancelSubscriptionQuestion => 'சந்தாவை ரத்து செய்யவா?';

  @override
  String get cancelSubscriptionConfirmation =>
      'உங்கள் சந்தாவை ரத்து செய்ய விரும்புகிறீர்களா? உங்கள் தற்போதைய பில்லிங் காலத்தின் முடிவு வரை நீங்கள் அணுக்கத்தைப் பெற்றிருப்பீர்கள்.';

  @override
  String get cancelSubscriptionButton => 'சந்தாவை ரத்து செய்யவும்';

  @override
  String get cancelling => 'ரத்து செய்யப்படுகிறது...';

  @override
  String get betaTesterMessage =>
      'இந்த பயன்பாட்டிற்குப் பீடா சோதனையாளர் நீங்கள். இது இன்னும் பொதுவாக இல்லை. அনுமதிக்கப்பட்ட பிறகு இது பொதுவாக இருக்கும்.';

  @override
  String get appUnderReviewMessage =>
      'உங்கள் பயன்பாடு மதிப்பாய்விற்கு கீழ் உள்ளது மற்றும் உங்களுக்கு மட்டுமே புலப்படும். அனுமதிக்கப்பட்ட பிறகு இது பொதுவாக இருக்கும்.';

  @override
  String get appRejectedMessage =>
      'உங்கள் பயன்பாடு நிராகரிக்கப்பட்டுள்ளது. பயன்பாட்டு விவரங்களைப் புதுப்பிக்கவும் மற்றும் மீண்டும் மதிப்பாய்வுக்கு சமர்ப்பிக்கவும்.';

  @override
  String get invalidIntegrationUrl => 'தவறான ஒருங்கிணைப்பு URL';

  @override
  String get tapToComplete => 'முடிக்க தட்டவும்';

  @override
  String get invalidSetupInstructionsUrl => 'தவறான அமைப்பு அறிவுரைகள் URL';

  @override
  String get pushToTalk => 'பேச பொத்தானை அழுத்தவும்';

  @override
  String get summaryPrompt => 'சுருக்க தூண்டுதல்';

  @override
  String get pleaseSelectARating => 'தர பகுதியைத் தேர்ந்தெடுக்கவும்';

  @override
  String get reviewAddedSuccessfully => 'மதிப்பாய்வு வெற்றிகரமாக சேர்க்கப்பட்டது 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'மதிப்பாய்வு வெற்றிகரமாக புதுப்பிக்கப்பட்டது 🚀';

  @override
  String get failedToSubmitReview => 'மதிப்பாய்வைச் சமர்ப்பிக்க தவறிவிட்டது. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get addYourReview => 'உங்கள் மதிப்பாய்வைச் சேர்க்கவும்';

  @override
  String get editYourReview => 'உங்கள் மதிப்பாய்வைத் திருத்தவும்';

  @override
  String get writeAReviewOptional => 'மதிப்பாய்வை எழுதவும் (விரும்பினால்)';

  @override
  String get submitReview => 'மதிப்பாய்வைச் சமர்ப்பிக்கவும்';

  @override
  String get updateReview => 'மதிப்பாய்வை புதுப்பிக்கவும்';

  @override
  String get yourReview => 'உங்கள் மதிப்பாய்வு';

  @override
  String get anonymousUser => 'அநாமதேய பயனர்';

  @override
  String get issueActivatingApp =>
      'இந்த பயன்பாட்டை செயல்படுத்துவதில் ஒரு சிக்கல் ஏற்பட்டது. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get dataAccessNoticeDescription =>
      'இந்த பயன்பாடு உங்கள் தரவை அணுகும். Omi AI இந்த பயன்பாடு உங்கள் தரவை எவ்வாறு பயன்படுத்துகிறது, மாற்றுகிறது அல்லது நீக்குகிறது என்பதற்கு பொறுப்பாகாது';

  @override
  String get copyUrl => 'URL ஐ நகल் செய்யவும்';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'திங்';

  @override
  String get weekdayTue => 'செவ்';

  @override
  String get weekdayWed => 'புத';

  @override
  String get weekdayThu => 'வியா';

  @override
  String get weekdayFri => 'வெள்';

  @override
  String get weekdaySat => 'சனி';

  @override
  String get weekdaySun => 'ஞாயி';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName ஒருங்கிணைப்பு விரைவில் வரவிருக்கிறது';
  }

  @override
  String alreadyExportedTo(String platform) {
    return '$platform உக்கு ஏற்கனவே ஏற்றுமதி செய்யப்பட்டது';
  }

  @override
  String get anotherPlatform => 'மற்றொரு தளம்';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'அமைப்புகள் > பணி ஒருங்கிணைப்புகளில் $serviceName மூலம் உறுதிப்படுத்தவும்';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceName உக்கு சேர்க்கிறது...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceName உக்கு சேர்க்கப்பட்டது';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceName உக்கு சேர்க்க தவறிவிட்டது';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple நினைவூட்டல்களுக்கு அனுமதி மறுக்கப்பட்டது';

  @override
  String failedToCreateApiKey(String error) {
    return 'வழங்குநர் API விசையை உருவாக்க தவறிவிட்டது: $error';
  }

  @override
  String get createAKey => 'விசையை உருவாக்கவும்';

  @override
  String get apiKeyRevokedSuccessfully => 'API விசை வெற்றிகரமாக மறுக்கப்பட்டது';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API விசையை மறுக்க தவறிவிட்டது: $error';
  }

  @override
  String get omiApiKeys => 'Omi API விசைகள்';

  @override
  String get apiKeysDescription =>
      'API விசைகள் உங்கள் பயன்பாடு OMI சர்வருடன் தொடர்பு கொள்ளும்போது அங்கீகாரத்திற்கு பயன்படுத்தப்படுகிறது. அவை உங்கள் பயன்பாடு நினைவுகளை உருவாக்கவும் மற்ற OMI சேவைகளுக்கு அணுக வாய்ப்பளிக்கிறது.';

  @override
  String get aboutOmiApiKeys => 'Omi API விசைகளைப் பற்றி';

  @override
  String get yourNewKey => 'உங்கள் புதிய விசை:';

  @override
  String get copyToClipboard => 'கிளிப்போர்டிற்கு நகல் செய்யவும்';

  @override
  String get pleaseCopyKeyNow => 'இப்போது நகல் செய்யவும் மற்றும் பாதுகாப்பான இடத்தில் எழுதவும்.';

  @override
  String get willNotSeeAgain => 'நீங்கள் இதை மீண்டும் பார்க்க முடியாது.';

  @override
  String get revokeKey => 'விசையை மறுக்கவும்';

  @override
  String get revokeApiKeyQuestion => 'API விசையை மறுக்கவா?';

  @override
  String get revokeApiKeyWarning =>
      'இந்த செயலை செயல்தவிர்க்க முடியாது. இந்த விசையைப் பயன்படுத்தும் எந்த பயன்பாடுகளும் API க்கு மீண்டும் அணுக முடியாது.';

  @override
  String get revoke => 'மறுக்கவும்';

  @override
  String get whatWouldYouLikeToCreate => 'நீங்கள் என்ன உருவாக்க விரும்புகிறீர்கள்?';

  @override
  String get createAnApp => 'பயன்பாட்டை உருவாக்கவும்';

  @override
  String get createAndShareYourApp => 'உங்கள் பயன்பாட்டை உருவாக்கி பகிரவும்';

  @override
  String get itemApp => 'பயன்பாடு';

  @override
  String keepItemPublic(String item) {
    return '$item பொதுவாக வைக்கவும்';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item பொதுவாக செய்யவா?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item தனிப்பட்டதாக செய்யவா?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'நீங்கள் $item பொதுவாக செய்தால், அதை அனைவரும் பயன்படுத்தலாம்';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'நீங்கள் $item இப்போது தனிப்பட்டதாக செய்தால், அது அனைவருக்கும் வேலை செய்ய நிறுத்தப்படும் மற்றும் உங்களுக்கு மட்டுமே புலப்படும்';
  }

  @override
  String get manageApp => 'பயன்பாட்டை நிர்வகிக்கவும்';

  @override
  String deleteItemTitle(String item) {
    return '$item ஐ நீக்கவும்';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item ஐ நீக்கவா?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'இந்த $item ஐ நீக்க விரும்புகிறீர்களா? இந்த செயலை செயல்தவிர்க்க முடியாது.';
  }

  @override
  String get revokeKeyQuestion => 'விசையை மறுக்கவா?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return '\"$keyName\" விசையை மறுக்க விரும்புகிறீர்களா? இந்த செயலை செயல்தவிர்க்க முடியாது.';
  }

  @override
  String get createNewKey => 'புதிய விசையை உருவாக்கவும்';

  @override
  String get keyNameHint => 'உதாரணமாக, Claude Desktop';

  @override
  String get pleaseEnterAName => 'பெயரை உள்ளிடவும்.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'விசையை உருவாக்க தவறிவிட்டது: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'விசையை உருவாக்க தவறிவிட்டது. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get keyCreated => 'விசை உருவாக்கப்பட்டது';

  @override
  String get keyCreatedMessage =>
      'உங்கள் புதிய விசை உருவாக்கப்பட்டுள்ளது. தயவு செய்து இப்போது நகல் செய்யவும். நீங்கள் இதை மீண்டும் பார்க்க முடியாது.';

  @override
  String get keyWord => 'விசை';

  @override
  String get externalAppAccess => 'வெளிப்புற பயன்பாட்டு அணுக்கம்';

  @override
  String get externalAppAccessDescription =>
      'பின்வரும் நிறுவப்பட்ட பயன்பாடுகள் வெளிப்புற ஒருங்கிணைப்புகளைக் கொண்டுள்ளது மற்றும் உங்கள் தரவு, உரையாடல்கள் மற்றும் நினைவுகளை அணுக முடியும்.';

  @override
  String get noExternalAppsHaveAccess => 'வெளிப்புற பயன்பாடுகள் உங்கள் தரவை அணுக முடியாது.';

  @override
  String get maximumSecurityE2ee => 'அதிகம் பாதுகாப்பு (E2EE)';

  @override
  String get e2eeDescription =>
      'End-to-end encryption இரகசியதைக்கான தங்கம் தரமாகும். செயல்படுத்தப்பட்டபோது, உங்கள் தரவு நம் சர்வரிற்கு அனுப்பப்படுவதற்கு முன் உங்கள் சாதனத்தில் குறியாக்கம் செய்யப்படுகிறது. இதன் பொருள் யாரும், Omi கூட, உங்கள் உள்ளடக்கத்தை அணுக முடியாது.';

  @override
  String get importantTradeoffs => 'முக்கியமான வாணிக்க:';

  @override
  String get e2eeTradeoff1 => '• வெளிப்புற பயன்பாட்டு ஒருங்கிணைப்புகள் போன்ற சில அம்சங்கள் செயல்தவிர்க்கப்படக்கூடும்.';

  @override
  String get e2eeTradeoff2 => '• நீங்கள் உங்கள் கடவுச்சொல் இழந்தால், உங்கள் தரவை மீட்க முடியாது.';

  @override
  String get featureComingSoon => 'இந்த அம்சம் விரைவில் வரவிருக்கிறது!';

  @override
  String get migrationInProgressMessage =>
      'இடப்பெயர்ப்பு நடந்து கொண்டிருக்கிறது. இது முடியாத வரை பாதுகாப்பு நிலையை மாற்ற முடியாது.';

  @override
  String get migrationFailed => 'இடப்பெயர்ப்பு ব்যর்థ';

  @override
  String migratingFromTo(String source, String target) {
    return '$source இலிருந்து $target க்கு இடப்பெயர்க்கப்படுகிறது';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total பொருள்கள்';
  }

  @override
  String get secureEncryption => 'பாதுகாப்பான குறியாக்கம்';

  @override
  String get secureEncryptionDescription =>
      'உங்கள் தரவு Google Cloud இல் புலனாய்வு செய்யப்பட்ட சர்வரில் உங்களுக்கு தனிப்பட்ட விசையுடன் குறியாக்கம் செய்யப்படுகிறது. இதன் பொருள் உங்கள் மூல உள்ளடக்கம் Omi ஊழியர்கள் அல்லது Google உட்பட, தரவுதளத்திலிருந்து நேரடியாக அணுக முடியாது.';

  @override
  String get endToEndEncryption => 'End-to-End குறியாக்கம்';

  @override
  String get e2eeCardDescription => 'அதிகம் பாதுகாப்புக்கு செயல்படுத்தவும். தட்டவும் மேலும் அறிய.';

  @override
  String get dataAlwaysEncrypted =>
      'பகுதி குறித்தில் இல்லாமல், உங்கள் தரவு எப்போதுமே ஓய்வில் மற்றும் போக்குவரத்தில் குறியாக்கம் செய்யப்படுகிறது.';

  @override
  String get readOnlyScope => 'படிக்க மட்டுமே';

  @override
  String get fullAccessScope => 'முழு அணுக்கம்';

  @override
  String get readScope => 'படிக்க';

  @override
  String get writeScope => 'எழுதவும்';

  @override
  String get apiKeyCreated => 'API விசை உருவாக்கப்பட்டது!';

  @override
  String get saveKeyWarning => 'இந்த விசையைச் சேமிக்கவும்! நீங்கள் இதை மீண்டும் பார்க்க முடியாது.';

  @override
  String get yourApiKey => 'உங்கள் API விசை';

  @override
  String get tapToCopy => 'நகल் செய்ய தட்டவும்';

  @override
  String get copyKey => 'விசையை நகல் செய்யவும்';

  @override
  String get createApiKey => 'API விசையை உருவாக்கவும்';

  @override
  String get accessDataProgrammatically => 'உங்கள் தரவை நிரலாக்கமாக அணுகவும்';

  @override
  String get keyNameLabel => 'விசை பெயர்';

  @override
  String get keyNamePlaceholder => 'உதாரணமாக, My App Integration';

  @override
  String get permissionsLabel => 'அனுமதிகள்';

  @override
  String get permissionsInfoNote =>
      'R = படிக்க, W = எழுதவும். எதுவும் தேர்ந்தெடுக்கப்படாவிட்டால் படிக்க-மட்டுமே இயல்புநிலை.';

  @override
  String get developerApi => 'டெவலப்பர் API';

  @override
  String get createAKeyToGetStarted => 'தொடங்க விசையை உருவாக்கவும்';

  @override
  String errorWithMessage(String error) {
    return 'பிழை: $error';
  }

  @override
  String get omiTraining => 'Omi பயிற்சி';

  @override
  String get trainingDataProgram => 'பயிற்சி தரவு திட்டம்';

  @override
  String get getOmiUnlimitedFree =>
      'AI மாதிரികளை பயிற்சி செய்ய உங்கள் தரவு பங்களிப்பதன் மூலம் Omi Unlimited ஐ இலவசமாகப் பெறவும்.';

  @override
  String get trainingDataBullets =>
      '• உங்கள் தரவு AI மாதிரிகளை மேம்படுத்த உதவுகிறது\n• இரகசியமற்ற தரவு மட்டுமே பகிரப்படுகிறது\n• முழுமையாக வெளிப்படையான செயல்முறை';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training இல் மேலும் அறிந்து கொள்ளவும்';

  @override
  String get agreeToContributeData => 'AI பயிற்சிக்கு பங்களிக்க நான் புரிந்து கொள்கிறேன் மற்றும் ஒப்புக் கொள்கிறேன்';

  @override
  String get submitRequest => 'கோரிக்கையை சமர்ப்பிக்கவும்';

  @override
  String get thankYouRequestUnderReview =>
      'நன்றி! உங்கள் கோரிக்கை மதிப்பாய்வு கீழ் உள்ளது. அனுமதிக்கப்பட்ட பிறகு நாங்கள் உங்களுக்கு தெரிவிப்போம்.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'உங்கள் திட்டம் $date வரை சக்திய நிலையில் இருக்கும். அதன் பிறகு, நீங்கள் உங்கள் வரம்பற்ற அம்சங்களுக்கான அணுக்கம் இழக்கும். நீங்கள் உறுதியாக உள்ளீர்களா?';
  }

  @override
  String get confirmCancellation => 'ரத்துசெய்ம் உறுதிப்படுத்தவும்';

  @override
  String get keepMyPlan => 'என் திட்டத்தை வைத்திருக்கவும்';

  @override
  String get subscriptionSetToCancel => 'உங்கள் சந்தா காலத்தின் முடிவில் ரத்து செய்ய அமைக்கப்பட்டுள்ளது.';

  @override
  String get switchedToOnDevice => 'சாதனத்தில் எழுத்தாக்கத்திற்கு மாற்றப்பட்டது';

  @override
  String get couldNotSwitchToFreePlan => 'இலவச திட்டத்திற்கு மாற முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get couldNotLoadPlans => 'கிடைக்கும் திட்டங்களைச் சரிசெய்ய முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get selectedPlanNotAvailable => 'தேர்ந்தெடுக்கப்பட்ட திட்டம் கிடைக்கவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get upgradeToAnnualPlan => 'ஆண்டு திட்டத்திற்கு அப்கிரேட் செய்யவும்';

  @override
  String get importantBillingInfo => 'முக்கிய பணம் செலுத்தும் தகவல்:';

  @override
  String get monthlyPlanContinues =>
      'உங்கள் தற்போதைய மாসிக திட்டம் உங்கள் பணம் செலுத்தும் காலத்தின் முடிவு வரை தொடர்ந்து இருக்கும்';

  @override
  String get paymentMethodCharged =>
      'உங்கள் বিদ்யமான பணம் செலுத்தும் முறை உங்கள் மாசிக திட்டம் முடிந்தவுடன் தானாக கட்டணம் செலுத்தப்படும்';

  @override
  String get annualSubscriptionStarts => 'உங்கள் 12 மாস ஆண்டு சந்தா கட்டணத்தின் பிறகு தானாக தொடங்கும்';

  @override
  String get thirteenMonthsCoverage => 'மொத்தமாக 13 மாதத்திற்கான கவரேஜ் கிடைக்கும் (தற்போதைய மாதம் + 12 மாத ஆண்டு)';

  @override
  String get confirmUpgrade => 'அப்கிரேட் உறுதிப்படுத்தவும்';

  @override
  String get confirmPlanChange => 'திட்ட மாற்றம் உறுதிப்படுத்தவும்';

  @override
  String get confirmAndProceed => 'உறுதிப்படுத்தவும் & தொடரவும்';

  @override
  String get upgradeScheduled => 'அப்கிரேட் திட்டமிடப்பட்டுவிட்டது';

  @override
  String get changePlan => 'திட்டத்தை மாற்றவும்';

  @override
  String get upgradeAlreadyScheduled => 'ஆண்டு திட்டத்திற்கான உங்கள் அப்கிரேட் ஏற்கனவே திட்டமிடப்பட்டுவிட்டது';

  @override
  String get youAreOnUnlimitedPlan => 'நீங்கள் வரம்பற்ற திட்டத்தில் இருக்கிறீர்கள்.';

  @override
  String get yourOmiUnleashed => 'உங்கள் Omi, வெளியிடப்பட்டது. வரம்பிலா வாய்ப்புகளுக்கு வரம்பற்றதாக செல்லவும்.';

  @override
  String planEndedOn(String date) {
    return 'உங்கள் திட்டம் $date இல் முடிந்துவிட்டது।\\nअब மீண்டும் சந்தா செய்யவும் - புதிய பணம் செலுத்தும் காலத்திற்கு உடனே கட்டணம் செலுத்தப்படும்.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'உங்கள் திட்டம் $date இல் ரத்து செய்ய திட்டமிடப்பட்டுள்ளது।\\nஉங்கள் சலுகைகளை தொடர்ந்து வைக்க இப்போது மீண்டும் சந்தா செய்யவும் - $date வரை எந்த கட்டணமும் இல்லை.';
  }

  @override
  String get annualPlanStartsAutomatically => 'உங்கள் மாசிக திட்டம் முடிந்தவுடன் உங்கள் ஆண்டு திட்டம் தானாக தொடங்கும்.';

  @override
  String planRenewsOn(String date) {
    return 'உங்கள் திட்டம் $date இல் புதுப்பிக்கப்படும்.';
  }

  @override
  String get unlimitedConversations => 'வரம்பிலா உரையாடல்கள்';

  @override
  String get askOmiAnything => 'உங்கள் வாழ்க்கையைப் பற்றி Omi-ஐ எதையும் கேளுங்கள்';

  @override
  String get unlockOmiInfiniteMemory => 'Omi இன் எல்லையற்ற நினைவை திறக்கவும்';

  @override
  String get youreOnAnnualPlan => 'நீங்கள் ஆண்டு திட்டத்தில் இருக்கிறீர்கள்';

  @override
  String get alreadyBestValuePlan => 'உங்களிடம் ஏற்கனவே சிறந்த மதிப்பு திட்டம் உள்ளது. எந்த மாற்றமும் தேவையில்லை.';

  @override
  String get unableToLoadPlans => 'திட்டங்களை ஏற்ற முடியவில்லை';

  @override
  String get checkConnectionTryAgain => 'இணைப்பைச் சரிபார்த்து மீண்டும் முயற்சிக்கவும்';

  @override
  String get useFreePlan => 'இலவச திட்டத்தைப் பயன்படுத்தவும்';

  @override
  String get continueText => 'தொடரவும்';

  @override
  String get resubscribe => 'மீண்டும் சந்தா செய்யவும்';

  @override
  String get couldNotOpenPaymentSettings =>
      'பணம் செலுத்தும் அமைப்புகளைத் திறக்க முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get managePaymentMethod => 'பணம் செலுத்தும் முறையை நிர்வகிக்கவும்';

  @override
  String get cancelSubscription => 'சந்தாவை ரத்து செய்யவும்';

  @override
  String endsOnDate(String date) {
    return '$date இல் முடிகிறது';
  }

  @override
  String get active => 'செயலில்';

  @override
  String get freePlan => 'இலவச திட்டம்';

  @override
  String get configure => 'கட்டமைக்கவும்';

  @override
  String get privacyInformation => 'தனியுரிமை தகவல்';

  @override
  String get yourPrivacyMattersToUs => 'உங்கள் தனியுரிமை எங்களுக்கு முக்கியம்';

  @override
  String get privacyIntroText =>
      'Omi இல், நாங்கள் உங்கள் தனியுரிமையை மிகவும் தீவிரமாக எடுத்துக்கொள்கிறோம். நாம் சேகரிக்கும் தரவு மற்றும் அதை உங்களுக்கான எங்கள் தயாரிப்பை மேம்படுத்த எவ்வாறு பயன்படுத்துகிறோம் என்பது பற்றி நாங்கள் வெளிப்படையாக இருக்க விரும்புகிறோம். நீங்கள் தெரிந்து கொள்ள வேண்டிய விஷயங்கள் இங்கே உள்ளன:';

  @override
  String get whatWeTrack => 'நாங்கள் என்ன ட்র্যাக் செய்கிறோம்';

  @override
  String get anonymityAndPrivacy => 'நிরாமய குறியாக்கம் மற்றும் தனியுரிமை';

  @override
  String get optInAndOptOutOptions => 'விருப்ப மற்றும் விலக்கு விருப்பங்கள்';

  @override
  String get ourCommitment => 'எங்கள் சேவையுறவு';

  @override
  String get commitmentText =>
      'நாங்கள் சேகரிக்கும் தரவை Omi ஐ உங்களுக்கு சிறந்த தயாரிப்பாக செய்ய பயன்படுத்த பிரতிசெரிக்கப் பட்டுள்ளோம். உங்கள் தனியுரிமை மற்றும் நம்பிக்கை எங்களுக்கு மிக முக்கியம்.';

  @override
  String get thankYouText =>
      'Omi இன் மதிப்புள்ள ব்যবহারকாரராக இருந்தமைக்கு நன்றி. உங்களுக்கு ஏதேனும் கேள்விகள் அல்லது கவலைகள் இருந்தால், team@basedhardware.com ஐக்கு தொடர்பு கொள்ளவும்.';

  @override
  String get wifiSyncSettings => 'WiFi ஒத்திசைவு அமைப்புகள்';

  @override
  String get enterHotspotCredentials => 'உங்கள் ஃபோனின் ஹாட்ஸ்பாட் நற்சான்றுகளை உள்ளிடவும்';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi ஒத்திசைவு உங்கள் ஃபோனைப் பயன்படுத்தி ஹாட்ஸ்பாட்டாக பயன்படுத்துகிறது. அமைப்புகள் > தனிப்பட்ட ஹாட்ஸ்பாட்டில் உங்கள் ஹாட்ஸ்பாட் பெயர் மற்றும் கடவுச்சொல்லைக் கண்டறியவும்.';

  @override
  String get hotspotNameSsid => 'ஹாட்ஸ்பாட் பெயர் (SSID)';

  @override
  String get exampleIphoneHotspot => 'உதாரணமாக iPhone ஹாட்ஸ்பாட்';

  @override
  String get password => 'கடவுச்சொல்';

  @override
  String get enterHotspotPassword => 'ஹாட்ஸ்பாட் கடவுச்சொல்லை உள்ளிடவும்';

  @override
  String get saveCredentials => 'நற்சான்றுகளைச் சேமிக்கவும்';

  @override
  String get clearCredentials => 'நற்சான்றுகளைத் தெளிக்கவும்';

  @override
  String get pleaseEnterHotspotName => 'தயவுசெய்து ஹாட்ஸ்பாட் பெயரை உள்ளிடவும்';

  @override
  String get wifiCredentialsSaved => 'WiFi நற்சான்றுகள் சேமிக்கப்பட்டது';

  @override
  String get wifiCredentialsCleared => 'WiFi நற்சான்றுகள் தெளிக்கப்பட்டது';

  @override
  String summaryGeneratedForDate(String date) {
    return '$date க்கான சுருக்கம் உருவாக்கப்பட்டது';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'சுருக்கம் உருவாக்க முடியவில்லை. அந்த நாளுக்கான உரையாடல்கள் உள்ளதா என்பதைச் சரிபார்க்கவும்.';

  @override
  String get summaryNotFound => 'சுருக்கம் கிடைக்கவில்லை';

  @override
  String get yourDaysJourney => 'உங்கள் நாளின் பயணம்';

  @override
  String get highlights => 'முக்கியமான அம்சங்கள்';

  @override
  String get unresolvedQuestions => 'தீர்க்கப்படாத கேள்விகள்';

  @override
  String get decisions => 'முடிவுகள்';

  @override
  String get learnings => 'கற்றுக்கொண்டவை';

  @override
  String get autoDeletesAfterThreeDays => '3 நாட்களுக்குப் பிறகு தானாக நீக்கப்படும்.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'அறிவு வரைபடம் வெற்றிகரமாக நீக்கப்பட்டது';

  @override
  String get exportStartedMayTakeFewSeconds => 'ஏற்றுமதி தொடங்கியது. இது சில நொடிகள் ஆகலாம்...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'இது அனைத்து பெறப்பட்ட அறிவு வரைபட தரவு (முனைகள் மற்றும் இணைப்புகள்) நீக்கும். உங்கள் அசல் நினைவுகள் பாதுகாப்பாக இருக்கும். வரைபடம் সময়ের சாக்கில் அல்லது அடுத்த요request இல் மறுபடியும் உருவாக்கப்படும்.';

  @override
  String get configureDailySummaryDigest => 'உங்கள் தினசரி செயல்பாட்டு உருப்பொறிப்பு செய்திகளை கட்டமைக்கவும்';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes ஐ அணுகுகிறது';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType மூலம் தூண்டப்படும்';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription மற்றும் $triggerDescription।';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription।';
  }

  @override
  String get noSpecificDataAccessConfigured => 'குறிப்பிட்ட தரவு அணுக கட்டமைக்கப்படவில்லை.';

  @override
  String get basicPlanDescription => '1,200 பிரீமியம் நிமிषங்கள் + சாதனத்தில் வரம்பிலாவை';

  @override
  String get minutes => 'நிமிషங்கள்';

  @override
  String get omiHas => 'Omi உள்ளது:';

  @override
  String get premiumMinutesUsed => 'பிரீமியம் நிமிషங்கள் பயன்படுத்தப்பட்டது.';

  @override
  String get setupOnDevice => 'சாதனத்தில் அமைக்கவும்';

  @override
  String get forUnlimitedFreeTranscription => 'வரம்பிலா இலவச உச்சரிப்புக்கு.';

  @override
  String premiumMinsLeft(int count) {
    return '$count பிரீமியம் நிமிషங்கள் மீதமுள்ளது.';
  }

  @override
  String get alwaysAvailable => 'எப்போதும் கிடைக்கும்.';

  @override
  String get importHistory => 'ஏற்றுமதி வரலாறு';

  @override
  String get noImportsYet => 'இதுவரை எந்த ஏற்றுமதியும் இல்லை';

  @override
  String get selectZipFileToImport => 'ஏற்றுமதி செய்ய .zip கோப்பைத் தேர்ந்தெடுக்கவும்!';

  @override
  String get otherDevicesComingSoon => 'பிற சாधনங்கள் விரைவில் வருக';

  @override
  String get deleteAllLimitlessConversations => 'அனைத்து Limitless உரையாடல்களையும் நீக்கவா?';

  @override
  String get deleteAllLimitlessWarning =>
      'இது Limitless இலிருந்து ஏற்றுமதி செய்யப்பட்ட அனைத்து உரையாடல்களையும் நிரந்தரமாக நீக்கும். இந்த வினை செய்ய முடியாது.';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless உரையாடல்கள் நீக்கப்பட்டது';
  }

  @override
  String get failedToDeleteConversations => 'உரையாடல்களை நீக்க முடியவில்லை';

  @override
  String get deleteImportedData => 'ஏற்றுமதி செய்யப்பட்ட தரவை நீக்கவும்';

  @override
  String get statusPending => 'நிலுவையில் உள்ளது';

  @override
  String get statusProcessing => 'செயலாக்கம் செய்யப்படுகிறது';

  @override
  String get statusCompleted => 'முடிந்தது';

  @override
  String get statusFailed => 'தோல்வியுற்றது';

  @override
  String nConversations(int count) {
    return '$count உரையாடல்கள்';
  }

  @override
  String get pleaseEnterName => 'தயவுசெய்து பெயரை உள்ளிடவும்';

  @override
  String get nameMustBeBetweenCharacters => 'பெயர் 2 முதல் 40 எழுத்துக்களுக்கு இடையில் இருக்க வேண்டும்';

  @override
  String get deleteSampleQuestion => 'மாதிரியைத் திரைப்படம் செய்யவா?';

  @override
  String deleteSampleConfirmation(String name) {
    return '$name இன் மாதிரியை நீக்க விரும்பிறீர்களா?';
  }

  @override
  String get confirmDeletion => 'நீக்குதல் உறுதிப்படுத்தவும்';

  @override
  String deletePersonConfirmation(String name) {
    return '$name ஐ நீக்க விரும்பிறீர்களா? இது அனைத்து தொடர்புடைய பேச்சு மாதிரிகளையும் அகற்றும்.';
  }

  @override
  String get howItWorksTitle => 'இது எவ்வாறு செயல்படுகிறது?';

  @override
  String get howPeopleWorks =>
      'ஒரு ব்যக்தி உருவாக்கப்பட்டவுடன், நீங்கள் ஒரு உரையாடல் பதிவுக்குச் சென்று அவர்களை அவர்களின் தொடர்புடைய பிரிவுகளுக்கு நியமித்து, Omi அவர்களின் பேச்சை உணர்ந்து கொள்ள முடியும்!';

  @override
  String get tapToDelete => 'நீக்க தட்டவும்';

  @override
  String get newTag => 'புதிய';

  @override
  String get needHelpChatWithUs => 'உதவி தேவையா? எங்களுடன் உரையாடவும்';

  @override
  String get localStorageEnabled => 'உள்ளூர் சேமிப்பு இயக்கப்பட்டது';

  @override
  String get localStorageDisabled => 'உள்ளூர் சேமிப்பு முடக்கப்பட்டது';

  @override
  String failedToUpdateSettings(String error) {
    return 'அமைப்புகளைப் புதுப்பிக்க முடியவில்லை: $error';
  }

  @override
  String get privacyNotice => 'தனியுரிமை அறிவிப்பு';

  @override
  String get recordingsMayCaptureOthers =>
      'பதிவுகள் மற்றவர்களின் குரல்களைப் பெறலாம். இயக்குவதற்கு முன் அனைத்து பங்கேற்றவர்களிடமிருந்து ஒப்புதல் பெறவும்.';

  @override
  String get enable => 'இயக்கவும்';

  @override
  String get storeAudioOnPhone => 'ஆடியோவை ஫ோனில் சேமிக்கவும்';

  @override
  String get on => 'இயக்கம்';

  @override
  String get storeAudioDescription =>
      'அனைத்து ஆடியோ பதிவுகளையும் உங்கள் ஃபோனில் உள்ளூரில் சேமிக்கவும். முடக்கப்பட்டால், சேமிப்பு இடத்தைச் சேமிக்க தோல்வியுற்ற பதிவுகள் மட்டுமே வைக்கப்படுகிறது.';

  @override
  String get enableLocalStorage => 'உள்ளூர் சேமிப்பை இயக்கவும்';

  @override
  String get cloudStorageEnabled => 'கிளவுட் சேமிப்பு இயக்கப்பட்டது';

  @override
  String get cloudStorageDisabled => 'கிளவுட் சேமிப்பு முடக்கப்பட்டது';

  @override
  String get enableCloudStorage => 'கிளவுட் சேமிப்பை இயக்கவும்';

  @override
  String get storeAudioOnCloud => 'ஆடியோவை கிளவுடில் சேமிக்கவும்';

  @override
  String get cloudStorageDialogMessage =>
      'உங்கள் நிகழ்நேர பதிவுகள் நீங்கள் பேசும்போது தனிப்பட்ட கிளவுட் சேமிப்பில் சேமிக்கப்படும்.';

  @override
  String get storeAudioCloudDescription =>
      'உங்கள் நிகழ்நேர பதிவுகளை நீங்கள் பேசும்போது தனிப்பட்ட கிளவுட் சேமிப்பில் சேமிக்கவும். ஆடியோ நிகழ்நேரத்தில் பெறப்பட்டு பாதுகாப்பாக சேமிக்கப்படுகிறது.';

  @override
  String get downloadingFirmware => 'ஃபার்மওয়்যேர் பதிவிறக்கம் செய்யப்படுகிறது';

  @override
  String get installingFirmware => 'ஃபார்மூவேர் நிறுவப்படுகிறது';

  @override
  String get firmwareUpdateWarning =>
      'பயன்பாட்டைப் பூட்டாதீர்கள் அல்லது சாதனத்தை முடக்காதீர்கள். இது உங்கள் சாதனத்தை பாதிக்கலாம்।';

  @override
  String get firmwareUpdated => 'ஃபार்மூவேர் புதுப்பிக்கப்பட்டது';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'புதுப்பித்தலை முடிப்பதற்கு உங்கள் $deviceName ஐ மறுதொடக்கம் செய்யவும்.';
  }

  @override
  String get yourDeviceIsUpToDate => 'உங்கள் சாதனம் புதிய நிலையில் உள்ளது';

  @override
  String get currentVersion => 'தற்போதைய பதிப்பு';

  @override
  String get latestVersion => 'சமீபத்திய பதிப்பு';

  @override
  String get whatsNew => 'பிரவுஸ் பயன்பாடு என்ன';

  @override
  String get installUpdate => 'புதுப்பித்தலை நிறுவவும்';

  @override
  String get updateNow => 'இப்போது புதுப்பிக்கவும்';

  @override
  String get updateGuide => 'நிறுவல் வழிகாட்டி';

  @override
  String get checkingForUpdates => 'புதுப்பித்தல்களுக்கான சரிபார்ப்பு';

  @override
  String get checkingFirmwareVersion => 'ஃபார்மூவேர் பதிப்பைச் சரிபார்க்கப்படுகிறது...';

  @override
  String get firmwareUpdate => 'ஃபார்மூவேர் புதுப்பித்தல்';

  @override
  String get payments => 'பணப் பரிமாற்றங்கள்';

  @override
  String get connectPaymentMethodInfo =>
      'உங்கள் பயன்பாடுகளுக்கான பணம் பெற ஒரு பணம் செலுத்தும் முறையைக் கீழே இணைக்கவும்.';

  @override
  String get selectedPaymentMethod => 'தேர்ந்தெடுக்கப்பட்ட பணம் செலுத்தும் முறை';

  @override
  String get availablePaymentMethods => 'கிடைக்கும் பணம் செலுத்தும் முறைகள்';

  @override
  String get activeStatus => 'செயலில்';

  @override
  String get connectedStatus => 'இணைக்கப்பட்ட';

  @override
  String get notConnectedStatus => 'இணைக்கப்படாத';

  @override
  String get setActive => 'சக்রீயமாக அமைக்கவும்';

  @override
  String get getPaidThroughStripe => 'Stripe வாயிலாக உங்கள் பயன்பாட்டு விற்பனைக்கான பணம் பெறவும்';

  @override
  String get monthlyPayouts => 'மாசிக வெளியாதல்';

  @override
  String get monthlyPayoutsDescription =>
      'நீங்கள் \$10 இல் வருவாயை அடையும்போது உங்கள் கணக்குக்கு நேரடியாக மাசிக பணம் பெறவும்';

  @override
  String get secureAndReliable => 'பாதுகாப்பற்ற மற்றும் நம்பகமான';

  @override
  String get stripeSecureDescription =>
      'Stripe உங்கள் பயன்பாட்டு வருவாய் பாதுகாப்பற்ற மற்றும் சময மாறுதல் உறுதி செய்கிறது';

  @override
  String get selectYourCountry => 'உங்கள் நாட்டைத் தேர்ந்தெடுக்கவும்';

  @override
  String get countrySelectionPermanent => 'உங்கள் நாட்டு தேர்வு நிரந்தரம் மற்றும் பிற்பாக மாற்ற முடியாது.';

  @override
  String get byClickingConnectNow => '\"இப்போது இணைக்கவும்\" ஐக் கிளிக் செய்வதன் மூலம் நீங்கள் ஒப்புக்கொள்கிறீர்கள்';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe இணைக்கப்பட்ட கணக்கு ஒப்பந்தம்';

  @override
  String get errorConnectingToStripe => 'Stripe க்கு இணைப்பதில் பிழை! பிற்பாக மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get connectingYourStripeAccount => 'உங்கள் Stripe கணக்கை இணைக்கப்படுகிறது';

  @override
  String get stripeOnboardingInstructions =>
      'தயவுசெய்து உங்கள் உலாவியில் Stripe onboarding செயல்முறையை முடிக்கவும். இந்த பக்கம் முடிந்தவுடன் தானாக புதுப்பிக்கப்படும்.';

  @override
  String get failedTryAgain => 'தோல்வி? மீண்டும் முயற்சி செய்யவும்';

  @override
  String get illDoItLater => 'நான் இதை பிற்பாக செய்யும்';

  @override
  String get successfullyConnected => 'வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get stripeReadyForPayments =>
      'உங்கள் Stripe கணக்கு இப்போது பணம் பெற தயாரிடமாக உள்ளது. நீங்கள் உங்கள் பயன்பாட்டு விற்பனைகளிலிருந்து உடனே பணம் அர்ப்பணிக்க தொடங்கலாம்।';

  @override
  String get updateStripeDetails => 'Stripe விவரங்களைப் புதுப்பிக்கவும்';

  @override
  String get errorUpdatingStripeDetails =>
      'Stripe விவரங்களைப் புதுப்பிப்பதில் பிழை! பிற்பாக மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get updatePayPal => 'PayPal ஐ புதுப்பிக்கவும்';

  @override
  String get setUpPayPal => 'PayPal ஐ அமைக்கவும்';

  @override
  String get updatePayPalAccountDetails => 'உங்கள் PayPal கணக்கு விவரங்களைப் புதுப்பிக்கவும்';

  @override
  String get connectPayPalToReceivePayments => 'உங்கள் பயன்பாடுகளுக்கான பணம் பெற உங்கள் PayPal கணக்கை இணைக்கவும்';

  @override
  String get paypalEmail => 'PayPal மின்னஞ்சல்';

  @override
  String get paypalMeLink => 'PayPal.me இணைப்பு';

  @override
  String get stripeRecommendation =>
      'Stripe உங்கள் நாட்டில் கிடைக்குமாறு, வேகமான மற்றும் எளிய வெளியாதலுக்கு இதைப் பயன்படுத்த மிக உயர்ந்த பரிந்துரை செய்கிறோம்.';

  @override
  String get updatePayPalDetails => 'PayPal விவரங்களைப் புதுப்பிக்கவும்';

  @override
  String get savePayPalDetails => 'PayPal விவரங்களைச் சேமிக்கவும்';

  @override
  String get pleaseEnterPayPalEmail => 'PayPal மின்னஞ்சலை உள்ளிடவும்';

  @override
  String get pleaseEnterPayPalMeLink => 'PayPal.me இணைப்பை உள்ளிடவும்';

  @override
  String get doNotIncludeHttpInLink => 'இணைப்பில் http அல்லது https அல்லது www ஐ சேர்க்க வேண்டாம்';

  @override
  String get pleaseEnterValidPayPalMeLink => 'சரியான PayPal.me இணைப்பை உள்ளிடவும்';

  @override
  String get pleaseEnterValidEmail => 'சரியான மின்னஞ்சல் முகவரியை உள்ளிடவும்';

  @override
  String get syncingYourRecordings => 'உங்கள் பதிவுகளை ஒத்திசைக்கப்படுகிறது';

  @override
  String get syncYourRecordings => 'உங்கள் பதிவுகளை ஒத்திசைக்கவும்';

  @override
  String get syncNow => 'இப்போது ஒத்திசைக்கவும்';

  @override
  String get error => 'பிழை';

  @override
  String get speechSamples => 'பேச்சு மாதிரிகள்';

  @override
  String additionalSampleIndex(String index) {
    return 'கூடுதல் மாதிரி $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'கால அளவு: $seconds விநாடிகள்';
  }

  @override
  String get additionalSpeechSampleRemoved => 'கூடுதல் பேச்சு மாதிரி அகற்றப்பட்டது';

  @override
  String get consentDataMessage =>
      'தொடர்வதன் மூலம், உங்கள் உரையாடல்கள், பதிவுகள் மற்றும் தனிப்பட்ட தகவல்கள் எங்கள் சேவையகங்களில் பாதுகாப்பாக சேமிக்கப்படும். உங்கள் ஆடியோ பதிவுகள் மற்றும் படியெடுப்புகள் மூன்றாம் தரப்பு AI சேவைகளால் செயலாக்கப்படுகின்றன (படியெடுப்பிற்கு Deepgram மற்றும் பகுப்பாய்விற்கு OpenAI உட்பட) AI இயக்கும் நுண்ணறிவுகளை உங்களுக்கு வழங்கவும் அனைத்து பயன்பாட்டு அம்சங்களையும் இயக்கவும்.';

  @override
  String get tasksEmptyStateMessage =>
      'உங்கள் உரையாடல்களிலிருந்து பணிகள் இங்கே தோன்றும்।\\n+ தட்டி கைமுறை ஒன்றை உருவாக்கவும்।';

  @override
  String get clearChatAction => 'உரையாடலைத் தெளிக்கவும்';

  @override
  String get enableApps => 'பயன்பாடுகளை இயக்கவும்';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'மேலும் காட்டவும் ↓';

  @override
  String get showLess => 'குறைவாக காட்டவும் ↑';

  @override
  String get loadingYourRecording => 'உங்கள் பதிவைச் சரிசெய்கப்படுகிறது...';

  @override
  String get photoDiscardedMessage => 'இந்த புகைப்படம் குறிப்பிடத் தகுந்தவற்றாக இல்லாததால் நிராகரிக்கப்பட்டது.';

  @override
  String get analyzing => 'பகுப்பாய்வு செய்யப்படுகிறது...';

  @override
  String get searchCountries => 'நாடுகளைத் தேடவும்';

  @override
  String get checkingAppleWatch => 'Apple Watch சரிபார்க்கப்படுகிறது...';

  @override
  String get installOmiOnAppleWatch => 'உங்கள் Apple Watch இல் Omi ஐ நிறுவவும்';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Omi உடன் உங்கள் Apple Watch ஐப் பயன்படுத்த, நீங்கள் முதலில் Omi பயன்பாட்டை உங்கள் கடிகாரத்தில் நிறுவ வேண்டும்.';

  @override
  String get openOmiOnAppleWatch => 'உங்கள் Apple Watch இல் Omi ஐத் திறக்கவும்';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi பயன்பாடு உங்கள் Apple Watch இல் நிறுவப்பட்டுள்ளது. அதைத் திறந்து தொடங்க தட்டவும்.';

  @override
  String get openWatchApp => 'Watch பயன்பாட்டைத் திறக்கவும்';

  @override
  String get iveInstalledAndOpenedTheApp => 'நான் பயன்பாட்டை நிறுவ மற்றும் திறந்துவிட்டேன்';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch பயன்பாட்டைத் திறக்க முடியவில்லை. உங்கள் Apple Watch இல் Watch பயன்பாட்டை கைமுறையாக திறந்து \"Available Apps\" பிரிவிலிருந்து Omi ஐ நிறுவவும்.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch இன்னும் அடையாளவாக இல்லை. Omi பயன்பாடு உங்கள் கடிகாரத்தில் திறந்திருக்கிறதா என்பதை உறுதிப்படுத்தவும்।';

  @override
  String errorCheckingConnection(String error) {
    return 'இணைப்பைச் சரிபார்ப்பதில் பிழை: $error';
  }

  @override
  String get muted => 'முடக்கப்பட்ட';

  @override
  String get processNow => 'இப்போது செயலாக்கம் செய்யவும்';

  @override
  String get finishedConversation => 'உரையாடலை முடித்துவிட்டீர்களா?';

  @override
  String get stopRecordingConfirmation => 'பதிவை நிறுத்தி உரையாடலைத் தொகுக்க விரும்பிறீர்களா?';

  @override
  String get conversationEndsManually => 'உரையாடல் கைமுறையாக மட்டுமே முடிந்துவிடும்।';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'பேச்சு இல்லாமல் $minutes நிமிஷத்திற்கு$suffix பிறகு உரையாடல் சுருக்கப்படுகிறது।';
  }

  @override
  String get dontAskAgain => 'மீண்டும் என்னைக் கேளாதீர்கள்';

  @override
  String get waitingForTranscriptOrPhotos => 'பதிவுமுறை அல்லது புகைப்படங்களுக்கு பொறுத்து வைக்கப்படுகிறது...';

  @override
  String get noSummaryYet => 'இதுவரை சுருக்கம் இல்லை';

  @override
  String hints(String text) {
    return 'குறிப்புகள்: $text';
  }

  @override
  String get testConversationPrompt => 'உரையாடல் প்ரமாணத்தை சோதிக்கவும்';

  @override
  String get prompt => 'உரை விரிவு';

  @override
  String get result => 'பின்னொட்டம்:';

  @override
  String get compareTranscripts => 'பதிவுறு তুலனை செய்யவும்';

  @override
  String get notHelpful => 'உதவிக்கமாக இல்லை';

  @override
  String get exportTasksWithOneTap => 'ஒரு தட்டுவிற்கு பணிகளை ஏற்றுமதி செய்யவும்!';

  @override
  String get inProgress => 'செயல்பாட்டில் உள்ளது';

  @override
  String get photos => 'புகைப்படங்கள்';

  @override
  String get rawData => 'முறையான தரவு';

  @override
  String get content => 'உள்ளடக்கம்';

  @override
  String get noContentToDisplay => 'காட்ட உள்ளடக்கம் இல்லை';

  @override
  String get noSummary => 'சுருக்கம் இல்லை';

  @override
  String get updateOmiFirmware => 'omi ஃபார்மூவேர் புதுப்பிக்கவும்';

  @override
  String get anErrorOccurredTryAgain => 'ஒரு பிழை ஏற்பட்டது. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get welcomeBackSimple => 'மீண்டும் வரவேற்கிறோம்';

  @override
  String get addVocabularyDescription => 'Omi பேச்சு மாற்றத்தின் போது அங்கீகரிக்க வேண்டிய சொற்களைச் சேர்க்கவும்.';

  @override
  String get enterWordsCommaSeparated => 'சொற்களை உள்ளிடவும் (குறுங்கணுக்களாக பிரிந்தவை)';

  @override
  String get whenToReceiveDailySummary => 'உங்கள் தினசரி சுருக்கம் எப்போது பெற வேண்டும்';

  @override
  String get checkingNextSevenDays => 'அடுத்த 7 நாட்கள் சரிபார்க்கப்படுகிறது';

  @override
  String failedToDeleteError(String error) {
    return 'நீக்குவதில் தோல்வி: $error';
  }

  @override
  String get developerApiKeys => 'டெவலபர் API விசைகள்';

  @override
  String get noApiKeysCreateOne => 'API விசை இல்லை. தொடங்க ஒன்றை உருவாக்கவும்.';

  @override
  String get commandRequired => '⌘ தேவைபட்டது';

  @override
  String get spaceKey => 'விண்வளி';

  @override
  String loadMoreRemaining(String count) {
    return 'மேலும் சரிசெய்யவும் ($count மீதமுள்ளது)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% ব্যবহারকারী';
  }

  @override
  String get wrappedMinutes => 'நிமிషங்கள்';

  @override
  String get wrappedConversations => 'உரையாடல்கள்';

  @override
  String get wrappedDaysActive => 'நாட்கள் செயலில் உள்ளது';

  @override
  String get wrappedYouTalkedAbout => 'நீங்கள் பேசினீர்கள்';

  @override
  String get wrappedActionItems => 'செயல் பொருட்கள்';

  @override
  String get wrappedTasksCreated => 'உருவாக்கப்பட்ட பணிகள்';

  @override
  String get wrappedCompleted => 'பூர்திசெய்யப்பட்ட';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% முடிப்புக்கு விகிதம்';
  }

  @override
  String get wrappedYourTopDays => 'உங்கள் சிறந்த நாட்கள்';

  @override
  String get wrappedBestMoments => 'சிறந்த தருணங்கள்';

  @override
  String get wrappedMyBuddies => 'என் நண்பர்கள்';

  @override
  String get wrappedCouldntStopTalkingAbout => 'பேசுவதை நிறுத்த முடியவில்லை';

  @override
  String get wrappedShow => 'நிகழ்ச்சி';

  @override
  String get wrappedMovie => 'திரைப்படம்';

  @override
  String get wrappedBook => 'புத்தகம்';

  @override
  String get wrappedCelebrity => 'பிரபலம்';

  @override
  String get wrappedFood => 'உணவு';

  @override
  String get wrappedMovieRecs => 'நண்பர்களுக்கான திரைப்படம் Recs';

  @override
  String get wrappedBiggest => 'மிகப்பெரிய';

  @override
  String get wrappedStruggle => 'பாடுபாடு';

  @override
  String get wrappedButYouPushedThrough => 'ஆனால் நீங்கள் தள்ளி விட்டுவிட்டீர்கள் 💪';

  @override
  String get wrappedWin => 'வெற்றி';

  @override
  String get wrappedYouDidIt => 'நீங்கள் செய்துவிட்டீர்கள்! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 சொற்றொடர்கள்';

  @override
  String get wrappedMins => 'நிமிஷங்கள்';

  @override
  String get wrappedConvos => 'உரையாடல்கள்';

  @override
  String get wrappedDays => 'நாட்கள்';

  @override
  String get wrappedMyBuddiesLabel => 'என் நண்பர்கள்';

  @override
  String get wrappedObsessionsLabel => 'ஆசை வாசனைகள்';

  @override
  String get wrappedStruggleLabel => 'பாடுபாடு';

  @override
  String get wrappedWinLabel => 'வெற்றி';

  @override
  String get wrappedTopPhrasesLabel => 'TOP சொற்றொடர்கள்';

  @override
  String get wrappedLetsHitRewind => 'உங்கள் தலைக்கு கொண்டு போ';

  @override
  String get wrappedGenerateMyWrapped => 'என் Wrapped ஐ உருவாக்கவும்';

  @override
  String get wrappedProcessingDefault => 'செயலாக்கம் செய்யப்படுகிறது...';

  @override
  String get wrappedCreatingYourStory => 'உங்கள் உருவாக்கம்\\n2025 கதை...';

  @override
  String get wrappedSomethingWentWrong => 'ஏதோ\\nத் தவறாக நடந்தது';

  @override
  String get wrappedAnErrorOccurred => 'ஒரு பிழை ஏற்பட்டது';

  @override
  String get wrappedTryAgain => 'மீண்டும் முயற்சி செய்யவும்';

  @override
  String get wrappedNoDataAvailable => 'தரவு கிடைக்கவில்லை';

  @override
  String get wrappedOmiLifeRecap => 'Omi வாழ்க்கை Recap';

  @override
  String get wrappedSwipeUpToBegin => 'தொடங்க மேலே இழுக்கவும்';

  @override
  String get wrappedShareText => 'என் 2025, Omi ✨ omi.me/wrapped இல் நினைவு வைக்கப்பட்டது';

  @override
  String get wrappedFailedToShare => 'பகிர்வதில் தோல்வி. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get wrappedFailedToStartGeneration => 'உருவாக்கம் தொடங்குவதில் தோல்வி. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get wrappedStarting => 'தொடங்குகிறது...';

  @override
  String get wrappedShare => 'பகிரவும்';

  @override
  String get wrappedShareYourWrapped => 'உங்கள் Wrapped ஐ பகிரவும்';

  @override
  String get wrappedMy2025 => 'என் 2025';

  @override
  String get wrappedRememberedByOmi => 'Omi இல் நினைவு வைக்கப்பட்டது';

  @override
  String get wrappedMostFunDay => 'மிக재मजेदार';

  @override
  String get wrappedMostProductiveDay => 'மிக உৎপাদक';

  @override
  String get wrappedMostIntenseDay => 'மிக தীவ்ரமான';

  @override
  String get wrappedFunniestMoment => 'சிரிப்பான';

  @override
  String get wrappedMostCringeMoment => 'மிக Cringe';

  @override
  String get wrappedMinutesLabel => 'நிமிషங்கள்';

  @override
  String get wrappedConversationsLabel => 'உரையாடல்கள்';

  @override
  String get wrappedDaysActiveLabel => 'நாட்கள் செயலில் உள்ளது';

  @override
  String get wrappedTasksGenerated => 'உருவாக்கப்பட்ட பணிகள்';

  @override
  String get wrappedTasksCompleted => 'பூர்திசெய்யப்பட்ட பணிகள்';

  @override
  String get wrappedTopFivePhrases => 'Top 5 சொற்றொடர்கள்';

  @override
  String get wrappedAGreatDay => 'ஒரு சிறந்த நாள்';

  @override
  String get wrappedGettingItDone => 'அதை செய்து முடிக்கப்படுகிறது';

  @override
  String get wrappedAChallenge => 'ஒரு சவால்';

  @override
  String get wrappedAHilariousMoment => 'ஒரு மஹா சிரிப்பான தருணம்';

  @override
  String get wrappedThatAwkwardMoment => 'அந்த கெஸ்ट தருணம்';

  @override
  String get wrappedYouHadFunnyMoments => 'இந்த ஆண்டு உங்களுக்கு சிரிப்பான தருணங்கள் இருந்தன!';

  @override
  String get wrappedWeveAllBeenThere => 'நாம் அனைவரும் அங்கே இருந்திருக்கிறோம்!';

  @override
  String get wrappedFriend => 'நண்பன்';

  @override
  String get wrappedYourBuddy => 'உங்கள் நண்பன்!';

  @override
  String get wrappedNotMentioned => 'குறிப்பிடப்படவில்லை';

  @override
  String get wrappedTheHardPart => 'கடினமான பகுதி';

  @override
  String get wrappedPersonalGrowth => 'ব்যக்திगत வளர்ச்சி';

  @override
  String get wrappedFunDay => '재மজेदार';

  @override
  String get wrappedProductiveDay => 'உৎপாదக';

  @override
  String get wrappedIntenseDay => 'தீவ்ரமான';

  @override
  String get wrappedFunnyMomentTitle => 'சிரிப்பான தருணம்';

  @override
  String get wrappedCringeMomentTitle => 'Cringe தருணம்';

  @override
  String get wrappedYouTalkedAboutBadge => 'நீங்கள் பேசினீர்கள்';

  @override
  String get wrappedCompletedLabel => 'பூர்திசெய்யப்பட்ட';

  @override
  String get wrappedMyBuddiesCard => 'என் நண்பர்கள்';

  @override
  String get wrappedBuddiesLabel => 'நண்பர்கள்';

  @override
  String get wrappedObsessionsLabelUpper => 'ஆசை வாசனைகள்';

  @override
  String get wrappedStruggleLabelUpper => 'பாடுபாடு';

  @override
  String get wrappedWinLabelUpper => 'வெற்றி';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP சொற்றொடர்கள்';

  @override
  String get wrappedYourHeader => 'உங்கள்';

  @override
  String get wrappedTopDaysHeader => 'சிறந்த நாட்கள்';

  @override
  String get wrappedYourTopDaysBadge => 'உங்கள் சிறந்த நாட்கள்';

  @override
  String get wrappedBestHeader => 'சிறந்த';

  @override
  String get wrappedMomentsHeader => 'தருணங்கள்';

  @override
  String get wrappedBestMomentsBadge => 'சிறந்த தருணங்கள்';

  @override
  String get wrappedBiggestHeader => 'மிகப்பெரிய';

  @override
  String get wrappedStruggleHeader => 'பாடுபாடு';

  @override
  String get wrappedWinHeader => 'வெற்றி';

  @override
  String get wrappedButYouPushedThroughEmoji => 'ஆனால் நீங்கள் தள்ளி விட்டுவிட்டீர்கள் 💪';

  @override
  String get wrappedYouDidItEmoji => 'நீங்கள் செய்துவிட்டீர்கள்! 🎉';

  @override
  String get wrappedHours => 'மணிநேரங்கள்';

  @override
  String get wrappedActions => 'செயல்கள்';

  @override
  String get multipleSpeakersDetected => 'பல பேச்சாளர்கள் கண்டறியப்பட்டனர்';

  @override
  String get multipleSpeakersDescription =>
      'பதிவில் பல பேச்சாளர்கள் இருக்கிறார்களாக தோன்றுகிறது. நீங்கள் அமைதியான இடத்தில் உள்ளீர்களா என்பதைத் திறக்கவும் மற்றும் மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get invalidRecordingDetected => 'தவறான பதிவு கண்டறியப்பட்டது';

  @override
  String get notEnoughSpeechDescription =>
      'போதுமான பேச்சு கண்டறியப்படவில்லை. மேலும் பேசவும் மற்றும் மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get speechDurationDescription =>
      'குறைந்தபட்சம் 5 விநாடிகளுக்கு பேச வேண்டும், 90 விநாடிகளுக்கு மேல் பேசக்கூடாது.';

  @override
  String get connectionLostDescription =>
      'இணைப்பு துண்டிக்கப்பட்டுவிட்டது. உங்கள் இணைய இணைப்பை சரிபார்த்து மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get howToTakeGoodSample => 'ஒரு நல்ல மாதிரி எப்படி பதிவுசெய்வது?';

  @override
  String get goodSampleInstructions =>
      '1. நீங்கள் ஒரு조용한அமைப்பில் இருக்கிறீர்கள் என்பதை உறுதிசெய்யவும்.\n2. தெளிவாக மற்றும் இயல்பாக பேசுங்கள்.\n3. உங்கள் சாதனம் உங்கள் கழுத்தில் இயல்பான நிலையில் இருக்கிறது என்பதை உறுதிசெய்யவும்.\n\nஒருமுறை உருவாக்கிய பின், நீங்கள் எப்போதும் அதை மேம்படுத்தலாம் அல்லது மீண்டும் செய்யலாம்.';

  @override
  String get noDeviceConnectedUseMic => 'சாதனம் இணைக்கப்படவில்லை. தொலைபேசி மைக்ரோஃபோனைப் பயன்படுத்தப்படும்.';

  @override
  String get doItAgain => 'மீண்டும் செய்யவும்';

  @override
  String get listenToSpeechProfile => 'எனது பேச்சு சுயவிவரத்தைக் கேளுங்கள் ➡️';

  @override
  String get recognizingOthers => 'மற்றவர்களை அடையாளம் காணுதல் 👀';

  @override
  String get keepGoingGreat => 'தொடர்ந்து செல்லுங்கள், நீங்கள் அருமையாக செயல்பட்டுக்கொண்டிருக்கிறீர்கள்';

  @override
  String get somethingWentWrongTryAgain => 'ஏதோ தவறு ஆனது! பின்னர் மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get uploadingVoiceProfile => 'உங்கள் குரல் சுயவிவரத்தை பதிவேற்றுகிறது....';

  @override
  String get memorizingYourVoice => 'உங்கள் குரலை நினைவில் வைத்துக்கொள்ளுதல்...';

  @override
  String get personalizingExperience => 'உங்கள் அனுபவத்தை தனிப்பட்டதாக்குதல்...';

  @override
  String get keepSpeakingUntil100 => '100% வரை பேச்சுத் தொடரவும்.';

  @override
  String get greatJobAlmostThere => 'அருமையான வேலை, நீங்கள் கிட்டத்தட்ட முடிந்துவிட்டீர்கள்';

  @override
  String get soCloseJustLittleMore => 'மிக நெருக்கமாக உள்ளது, சிறிது கூடுதல்';

  @override
  String get notificationFrequency => 'அறிவிப்பு அதிர்வெண்';

  @override
  String get controlNotificationFrequency =>
      'Omi உங்களுக்கு தீவிர அறிவிப்புகளை எவ்வளவு அடிக்கடி அனுப்புகிறது என்பதை নিয়ந்திரணம் செய்யுங்கள்.';

  @override
  String get yourScore => 'உங்கள் மதிப்பெண்';

  @override
  String get dailyScoreBreakdown => 'தினசரி மதிப்பெண் பிரிப்பு';

  @override
  String get todaysScore => 'இன்றைய மதிப்பெண்';

  @override
  String get tasksCompleted => 'நிறைவு செய்யப்பட்ட பணிகள்';

  @override
  String get completionRate => 'நிறைவு விகிதம்';

  @override
  String get howItWorks => 'இது எவ்வாறு செயல்படுகிறது';

  @override
  String get dailyScoreExplanation =>
      'உங்கள் தினசரி மதிப்பெண் பணி நிறைவுக்கு அடிப்படையாக உள்ளது. உங்கள் மதிப்பெண்ணை மேம்படுத்த உங்கள் பணிகளை நிறைவு செய்யவும்!';

  @override
  String get notificationFrequencyDescription =>
      'Omi உங்களுக்கு தீவிர அறிவிப்புகள் மற்றும் நினைவூட்டல்களை எவ்வளவு அடிக்கடி அனுப்புகிறது என்பதை நிய்ந்திரணம் செய்யுங்கள்.';

  @override
  String get sliderOff => 'முடக்கவும்';

  @override
  String get sliderMax => 'அதிகபட்சம்';

  @override
  String summaryGeneratedFor(String date) {
    return '$date க்கான சுருக்கம் உருவாக்கப்பட்டது';
  }

  @override
  String get failedToGenerateSummary =>
      'சுருக்கம் உருவாக்க தவறிவிட்டது. அந்த நாளில் உரையாடல்கள் உள்ளன என்பதை உறுதிசெய்யவும்.';

  @override
  String get recap => 'மறுபார்வை';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" ஐ நீக்கவும்';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count உரையாடல்களை இவற்றுக்கு நகர்த்தவும்:';
  }

  @override
  String get noFolder => 'கோப்புறை இல்லை';

  @override
  String get removeFromAllFolders => 'அனைத்து கோப்புறைகளிலிருந்து அகற்றவும்';

  @override
  String get buildAndShareYourCustomApp => 'உங்கள் கூறப்பட்ட பயன்பாட்டை உருவாக்கி பகிர்ந்து கொள்ளுங்கள்';

  @override
  String get searchAppsPlaceholder => '1500+ பயன்பாடுகளைத் தேடவும்';

  @override
  String get filters => 'வடிப்படிகள்';

  @override
  String get frequencyOff => 'முடக்கவும்';

  @override
  String get frequencyMinimal => 'குறைந்தபட்சம்';

  @override
  String get frequencyLow => 'குறைவு';

  @override
  String get frequencyBalanced => 'சமநிலையான';

  @override
  String get frequencyHigh => 'அதிகம்';

  @override
  String get frequencyMaximum => 'அதிகபட்சம்';

  @override
  String get frequencyDescOff => 'தீவிர அறிவிப்புகள் இல்லை';

  @override
  String get frequencyDescMinimal => 'முக்கியமான நினைவூட்டல்களை மட்டுமே';

  @override
  String get frequencyDescLow => 'முக்கியமான புதல்வருகள் மட்டுமே';

  @override
  String get frequencyDescBalanced => 'வழக்கமான உதவிகரமான தொடுதல்கள்';

  @override
  String get frequencyDescHigh => 'அடிக்கடி செக்-இன்கள்';

  @override
  String get frequencyDescMaximum => 'தொடர்ந்து நியூக்தமாக நீடிக்கும்';

  @override
  String get clearChatQuestion => 'உரையாடலைத் தீர்க்கவும்?';

  @override
  String get syncingMessages => 'செய்திகளை சர்வரின் ஒத்திசைப்பு செய்கிறது...';

  @override
  String get chatAppsTitle => 'உரையாடல் பயன்பாடுகள்';

  @override
  String get selectApp => 'பயன்பாட்டைத் தேர்ந்தெடுக்கவும்';

  @override
  String get noChatAppsEnabled =>
      'எந்த உரையாடல் பயன்பாடுகளும் இயக்கப்பட்டிருக்கவில்லை.\n\"பயன்பாடுகளை இயக்கு\" என்பதற்கு தட்டவும் சிலவற்றைச் சேர்க்க.';

  @override
  String get disable => 'முடக்கவும்';

  @override
  String get photoLibrary => 'புகைப்பட நூலகம்';

  @override
  String get chooseFile => 'கோப்பைத் தேர்ந்தெடுக்கவும்';

  @override
  String get connectAiAssistantsToYourData => 'AI உதவியாளர்களை உங்கள் தரவுக்கு இணைக்கவும்';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'முகப்புப் பக்கத்தில் உங்கள் ব்যক்তிगত লக்ষ்যங்களைக் கண்காணிக்கவும்';

  @override
  String get deleteRecording => 'பதிவுசெய்தலை நீக்கவும்';

  @override
  String get thisCannotBeUndone => 'இதை செயல்ரத்து செய்ய முடியாது.';

  @override
  String get sdCard => 'SD கார்டு';

  @override
  String get fromSd => 'SD இலிருந்து';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'வேகமான பரிமாற்றம்';

  @override
  String get syncingStatus => 'ஒத்திசைப்பு செய்கிறது';

  @override
  String get failedStatus => 'தவறிவிட்டது';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'பரிமாற்ற முறை';

  @override
  String get fast => 'வேகமான';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'தொலைபேசி';

  @override
  String get cancelSync => 'ஒத்திசைப்பு ரத்து செய்யவும்';

  @override
  String get cancelSyncMessage => 'ஏற்கனவே பதிவிறக்கப்பட்ட தரவு சேமிக்கப்படும். பின்னர் மீண்டும் தொடரலாம்.';

  @override
  String get syncCancelled => 'ஒத்திசைப்பு ரத்து செய்யப்பட்டது';

  @override
  String get deleteProcessedFiles => 'செயலாக்கப்பட்ட கோப்புகளை நீக்கவும்';

  @override
  String get processedFilesDeleted => 'செயலாக்கப்பட்ட கோப்புகள் நீக்கப்பட்டன';

  @override
  String get wifiEnableFailed => 'சாதனத்தில் WiFi இயக்க முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get deviceNoFastTransfer =>
      'உங்கள் சாதனம் வேகமான பரிமாற்றம் ஆதரிக்காது. அதற்கு பதிலாக Bluetooth பயன்படுத்தவும்.';

  @override
  String get enableHotspotMessage => 'உங்கள் தொலைபேசியின் ஹாட்ஸ்பாட்டை இயக்கவும் மற்றும் மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get transferStartFailed => 'பரிமாற்றத்தைத் தொடங்க முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get deviceNotResponding => 'சாதனம் பதிலளிக்கவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get invalidWifiCredentials => 'செல்லுபடியாகாத WiFi நற்சான்றுகள். உங்கள் ஹாட்ஸ்பாட் அமைப்புகளை சரிபார்க்கவும்.';

  @override
  String get wifiConnectionFailed => 'WiFi இணைப்பு தவறிவிட்டது. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get sdCardProcessing => 'SD கார்டு செயலாக்கம்';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count பதிவுசெய்தல்(களை) செயலாக்குகிறது. கோப்புகள் பின்னரில் SD கார்டிலிருந்து அகற்றப்படும்.';
  }

  @override
  String get process => 'செயலாக்குங்கள்';

  @override
  String get wifiSyncFailed => 'WiFi ஒத்திசைப்பு தவறிவிட்டது';

  @override
  String get processingFailed => 'செயலாக்கம் தவறிவிட்டது';

  @override
  String get downloadingFromSdCard => 'SD கார்டிலிருந்து பதிவிறக்குகிறது';

  @override
  String processingProgress(int current, int total) {
    return 'செயலாக்குகிறது $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count உரையாடல்கள் உருவாக்கப்பட்டன';
  }

  @override
  String get internetRequired => 'இணையம் தேவை';

  @override
  String get processAudio => 'ஆடியோ செயலாக்கு';

  @override
  String get start => 'தொடங்கவும்';

  @override
  String get noRecordings => 'பதிவுசெய்தல் இல்லை';

  @override
  String get audioFromOmiWillAppearHere => 'உங்கள் Omi சாதனத்திலிருந்து ஆடியோ இங்கே தோன்றும்';

  @override
  String get deleteProcessed => 'செயலாக்கப்பட்டவற்றை நீக்கவும்';

  @override
  String get tryDifferentFilter => 'வேறு வடிப்படி முயற்சி செய்யவும்';

  @override
  String get recordings => 'பதிவுசெய்தல்கள்';

  @override
  String get enableRemindersAccess => 'Apple நினைவூட்டல்களைப் பயன்படுத்த அமைப்புகளில் நினைவூட்டல் அணுகலை இயக்கவும்';

  @override
  String todayAtTime(String time) {
    return 'இன்று $time க்குள்';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'நேற்று $time க்குள்';
  }

  @override
  String get lessThanAMinute => 'ஒரு நிமிடத்திற்கு குறைவு';

  @override
  String estimatedMinutes(int count) {
    return '~$count நிமிடம்(மணிக்கூறு)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count மணிநேரம்(மணிக்கூறு)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'மதிப்பிடப்பட்டவை: $time மீதமுள்ளவை';
  }

  @override
  String get summarizingConversation => 'உரையாடலை சுருக்குகிறது...\nஇது சில நொடிகள் ஆகலாம்';

  @override
  String get resummarizingConversation => 'உரையாடலை மீண்டும் சுருக்குகிறது...\nஇது சில நொடிகள் ஆகலாம்';

  @override
  String get nothingInterestingRetry => 'சுவையெதுவும் கண்டுபிடிக்கப்படவில்லை,\nமீண்டும் முயற்சி செய்ய வேண்டுமா?';

  @override
  String get noSummaryForConversation => 'இந்த உரையாடலுக்கு சுருக்கம் கிடைக்கவில்லை।';

  @override
  String get unknownLocation => 'அறியப்படாத இடம்';

  @override
  String get couldNotLoadMap => 'வரைபடத்தைலோடுசெய்ய முடியவில்லை';

  @override
  String get triggerConversationIntegration => 'உரையாடல் உருவாக்க ஒருங்கிணைப்பைத் தூண்டவும்';

  @override
  String get webhookUrlNotSet => 'Webhook URL அமைக்கப்படவில்லை';

  @override
  String get setWebhookUrlInSettings =>
      'இந்த அம்சத்தைப் பயன்படுத்த மேம்பாட்டாளர் அமைப்புகளில் webhook URL ஐ அமைக்கவும்.';

  @override
  String get sendWebUrl => 'வலை URL அனுப்பவும்';

  @override
  String get sendTranscript => 'டிரான்ஸ்கிரிப்ட் அனுப்பவும்';

  @override
  String get sendSummary => 'சுருக்கம் அனுப்பவும்';

  @override
  String get debugModeDetected => 'பிழைத்திருத்த பாங்கு கண்டறியப்பட்டது';

  @override
  String get performanceReduced => 'செயல்திறன் 5-10x குறைந்துவிட்டது. விடுப்பு பாங்கைப் பயன்படுத்தவும்.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'தானாக மூடுகிறது ${seconds}s இல்';
  }

  @override
  String get modelRequired => 'மாதிரி தேவை';

  @override
  String get downloadWhisperModel => 'சேமிப்பதற்கு முன் Whisper மாதிரியைப் பதிவிறக்கவும்.';

  @override
  String get deviceNotCompatible => 'சாதனம் பொருந்தாது';

  @override
  String get deviceRequirements => 'உங்கள் சாதனம்온-சாதன உபாய கேட்டுபேரலுக்கான தேவைகளை பூர்த்திசெய்யாது।';

  @override
  String get willLikelyCrash => 'இதை இயக்குவது பயன்பாட்டை செயலிழக்க அல்லது முடக்க வாய்ப்புள்ளது.';

  @override
  String get transcriptionSlowerLessAccurate =>
      'உபாய கேட்டுபேரல் கணிசமாக மெதுவாக இருக்கும் மற்றும் குறைவாக துல்லியமாக இருக்கும்.';

  @override
  String get proceedAnyway => 'எதிர்பாராக தொடரவும்';

  @override
  String get olderDeviceDetected => 'பழைய சாதனம் கண்டறியப்பட்டது';

  @override
  String get onDeviceSlower => '온-சாதன உபாய கேட்டுபேரல் இந்த சாதனத்தில் மெதுவாக இருக்கக்கூடும்.';

  @override
  String get batteryUsageHigher => 'பேட்டரி பயன்பாடு மேக்லெவ் உபாய கேட்டுபேரலை விட அதிகமாக இருக்கும்।';

  @override
  String get considerOmiCloud => 'சிறந்த செயல்திறனுக்கு Omi மேக்லெவ பயன்படுத்த கருத்தில் கொள்ளவும்.';

  @override
  String get highResourceUsage => 'அதிக ஆதாரப் பயன்பாடு';

  @override
  String get onDeviceIntensive => '온-சாதன உபாய கேட்டுபேரல் கணக்கீட்டு முறையில் தீவிரமாக உள்ளது।';

  @override
  String get batteryDrainIncrease => 'பேட்டரி வெளியேற்றம் கணிசமாக அதிகரிக்கும்।';

  @override
  String get deviceMayWarmUp => 'நீட்டிய பயன்பாட்டின் போது சாதனம் வெப்பமாகலாம்।';

  @override
  String get speedAccuracyLower => 'வேகம் மற்றும் துல்லியம் மேக்லெவ மாதிரிகளை விட குறைவாக இருக்கலாம்.';

  @override
  String get cloudProvider => 'மேக்லெவ பின்தொடரக்காரர்';

  @override
  String get premiumMinutesInfo =>
      'மாத மாதம் 1,200 பிரீமியம் நிமிடங்கள்.온-சாதன ট্যাब সীमाहीन இலவச உபாய கேட்டுபேரல் வழங்குகிறது।';

  @override
  String get viewUsage => 'பயன்பாட்டைக் கவனிக்கவும்';

  @override
  String get localProcessingInfo =>
      'ஆடியோ உள்ளூரிலேயே செயலாக்கப்படுகிறது। অফலைனில் செயல்படுகிறது, மேலும் தனியுரிமை இருக்கிறது, ஆனால் அதிக பேட்டரி பயன்படுத்துகிறது।';

  @override
  String get model => 'மாதிரி';

  @override
  String get performanceWarning => 'செயல்திறன் எச்சரிக்கை';

  @override
  String get largeModelWarning =>
      'இந்த மாதிரி பெரியதாக உள்ளது மற்றும் மொபைல் சாதனங்களில் பயன்பாட்டை செயலிழக்க அல்லது மிக மெதுவாக இயங்கக்கூடும்.\n\n\"சிறியவை\" அல்லது \"அடிப்படை\" பரிந்துரைக்கப்படுகிறது.';

  @override
  String get usingNativeIosSpeech => 'பூர்வீக iOS பேச்சு அங்கீகாரத்தைப் பயன்படுத்துகிறது';

  @override
  String get noModelDownloadRequired =>
      'உங்கள் சாதனத்தின் பூர்வீக பேச்சு ஞ்சனം பயன்படுத்தப்படும். மாதிரி பதிவிறக்கம் தேவையில்லை।';

  @override
  String get modelReady => 'மாதிரி தயாரம்';

  @override
  String get redownload => 'மீண்டும் பதிவிறக்கவும்';

  @override
  String get doNotCloseApp => 'பயன்பாட்டை மூடாதீர்கள்.';

  @override
  String get downloading => 'பதிவிறக்குகிறது...';

  @override
  String get downloadModel => 'மாதிரி பதிவிறக்கவும்';

  @override
  String estimatedSize(String size) {
    return 'மதிப்பிடப்பட்ட அளவு: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'கிடைக்கக்கூடிய இடம்: $space';
  }

  @override
  String get notEnoughSpace => 'எச்சரிக்கை: போதுமான இடம் இல்லை!';

  @override
  String get download => 'பதிவிறக்கவும்';

  @override
  String downloadError(String error) {
    return 'பதிவிறக்கம் பிழை: $error';
  }

  @override
  String get cancelled => 'ரத்து செய்யப்பட்டது';

  @override
  String get deviceNotCompatibleTitle => 'சாதனம் பொருந்தாது';

  @override
  String get deviceNotMeetRequirements => 'உங்கள் சாதனம்온-சாதன உபாய கேட்டுபேரலுக்கான தேவைகளை பூர்த்திசெய்யாது।';

  @override
  String get transcriptionSlowerOnDevice => '온-சாதன உபாய கேட்டுபேரல் இந்த சாதனத்தில் மெதுவாக இருக்கக்கூடும்।';

  @override
  String get computationallyIntensive => '온-சாதன உபாய கேட்டுபேரல் கணக்கீட்டு முறையில் தீவிரமாக உள்ளது।';

  @override
  String get batteryDrainSignificantly => 'பேட்டரி வெளியேற்றம் கணிசமாக அதிகரிக்கும்।';

  @override
  String get premiumMinutesMonth =>
      'மாத மாதம் 1,200 பிரீமியம் நிமிடங்கள்.온-சாதன ট்যாब சீமाहीन இலவச உபாய கேட்டுபேரல் வழங்குகிறது।';

  @override
  String get audioProcessedLocally =>
      'ஆடியோ உள்ளூரிலேயே செயலாக்கப்படுகிறது। அफ்லைனில் செயல்படுகிறது, மேலும் தனியுரிமை இருக்கிறது, ஆனால் அதிக பேட்டரி பயன்படுத்துகிறது।';

  @override
  String get languageLabel => 'மொழி';

  @override
  String get modelLabel => 'மாதிரி';

  @override
  String get modelTooLargeWarning =>
      'இந்த மாதிரி பெரியதாக உள்ளது மற்றும் மொபைல் சாதனங்களில் பயன்பாட்டை செயலிழக்க அல்லது மிக மெதுவாக இயங்கக்கூடும்.\n\n\"சிறியவை\" அல்லது \"அடிப்படை\" பரிந்துரைக்கப்படுகிறது.';

  @override
  String get nativeEngineNoDownload =>
      'உங்கள் சாதனத்தின் பூர்வீக பேச்சு ஞ்சனம் பயன்படுத்தப்படும்। மாதிரி பதிவிறக்கம் தேவையில்லை।';

  @override
  String modelReadyWithName(String model) {
    return 'மாதிரி தயாரம் ($model)';
  }

  @override
  String get reDownload => 'மீண்டும் பதிவிறக்கவும்';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model பதிவிறக்குகிறது: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model தயாரிக்கிறது...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'பதிவிறக்கம் பிழை: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'மதிப்பிடப்பட்ட அளவு: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'கிடைக்கக்கூடிய இடம்: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omi இன் உள்ளமைந்த நேரடி உபாய கேட்டுபேரல் உரையாடல் பற்றிய ஒத்திசைப்பு மற்றும் தற்போதைய பேச்சாளர் கண்டறிதலுக்கு தெளிவு செய்யப்பட்டுள்ளது।';

  @override
  String get reset => 'மீட்டமைக்கவும்';

  @override
  String get useTemplateFrom => 'வடிவமாக பயன்படுத்தவும்';

  @override
  String get selectProviderTemplate => 'ஒரு சேவை வழங்குநர் வடிவமாக தேர்ந்தெடுக்கவும்...';

  @override
  String get quicklyPopulateResponse => 'இந்த சேவை வழங்குநர்ஸ் பதில் வடிவூட்டம் உடன் வெகுவாக நிரப்பு';

  @override
  String get quicklyPopulateRequest => 'இந்த சேவை வழங்குநர்ஸ் கோரிக்கை வடிவூட்டம் உடன் வெகுவாக நிரப்பு';

  @override
  String get invalidJsonError => 'செல்லுபடியாகாத JSON';

  @override
  String downloadModelWithName(String model) {
    return 'மாதிரி பதிவிறக்கவும் ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'மாதிரி: $model';
  }

  @override
  String get device => 'சாதனம்';

  @override
  String get chatAssistantsTitle => 'உரையாடல் உதவியாளர்கள்';

  @override
  String get permissionReadConversations => 'உரையாடல்களைப் படிக்கவும்';

  @override
  String get permissionReadMemories => 'நினைவுகளைப் படிக்கவும்';

  @override
  String get permissionReadTasks => 'பணிகளைப் படிக்கவும்';

  @override
  String get permissionCreateConversations => 'உரையாடல்களை உருவாக்கவும்';

  @override
  String get permissionCreateMemories => 'நினைவுகளை உருவாக்கவும்';

  @override
  String get permissionTypeAccess => 'அணுகல்';

  @override
  String get permissionTypeCreate => 'உருவாக்கு';

  @override
  String get permissionTypeTrigger => 'தூண்டு';

  @override
  String get permissionDescReadConversations => 'இந்த பயன்பாடு உங்கள் உரையாடல்களை அணுகக்கூடும்.';

  @override
  String get permissionDescReadMemories => 'இந்த பயன்பாடு உங்கள் நினைவுகளை அணுகக்கூடும்.';

  @override
  String get permissionDescReadTasks => 'இந்த பயன்பாடு உங்கள் பணிகளை அணுகக்கூடும்.';

  @override
  String get permissionDescCreateConversations => 'இந்த பயன்பாடு புதிய உரையாடல்களை உருவாக்கலாம்.';

  @override
  String get permissionDescCreateMemories => 'இந்த பயன்பாடு புதிய நினைவுகளை உருவாக்கலாம்.';

  @override
  String get realtimeListening => 'உடனடி கேட்பு';

  @override
  String get setupCompleted => 'நிறைவு செய்யப்பட்டது';

  @override
  String get pleaseSelectRating => 'தயவுசெய்து மதிப்பையீட்டைத் தேர்ந்தெடுக்கவும்';

  @override
  String get writeReviewOptional => 'விமர்சனத்தை எழுதவும் (விரும்பினால்)';

  @override
  String get setupQuestionsIntro => 'சில கேள்விகளுக்கு பதிலளித்து Omi ஐ மேம்படுத்த உதவுங்கள். 🫶 💜';

  @override
  String get setupQuestionProfession => '1. நீங்கள் என்ன செய்கிறீர்கள்?';

  @override
  String get setupQuestionUsage => '2. உங்கள் Omi ஐ எங்கு பயன்படுத்த திட்டமிடுகிறீர்கள்?';

  @override
  String get setupQuestionAge => '3. உங்கள் வயது வரம்பு என்ன?';

  @override
  String get setupAnswerAllQuestions => 'நீங்கள் இன்னும் அனைத்து கேள்விகளுக்கும் பதிலளிக்கவில்லை! 🥺';

  @override
  String get setupSkipHelp => 'தவிர்க்கவும், நான் உதவ விரும்பவில்லை :C';

  @override
  String get professionEntrepreneur => 'விஞ்சை';

  @override
  String get professionSoftwareEngineer => 'மென்பொருள் பொறியாளர்';

  @override
  String get professionProductManager => 'பொருள் ব்যவস்థாபक';

  @override
  String get professionExecutive => 'நிர்வாகி';

  @override
  String get professionSales => 'விற்பனை';

  @override
  String get professionStudent => 'மாணவர்';

  @override
  String get usageAtWork => 'பணியில்';

  @override
  String get usageIrlEvents => 'வாழ்க்கை நிலைக்கு நிலை நிக்षேபணம் நிக்ஷேபணம்';

  @override
  String get usageOnline => 'ஆன்லைনுக்கு';

  @override
  String get usageSocialSettings => 'சामூக முறை சூழ்நிலைகளில்';

  @override
  String get usageEverywhere => 'எங்கும்';

  @override
  String get customBackendUrlTitle => 'கூறப்பட்ட பின்தொடரக் URL';

  @override
  String get backendUrlLabel => 'பின்தொடரக் URL';

  @override
  String get saveUrlButton => 'URL சேமிக்கவும்';

  @override
  String get enterBackendUrlError => 'பின்தொடரக் URL ஐ உள்ளிடவும்';

  @override
  String get urlMustEndWithSlashError => 'URL ஒரு \"/\" உடன் முடிய வேண்டும்';

  @override
  String get invalidUrlError => 'தயவுசெய்து செல்லுபடியாகான URL ஐ உள்ளிடவும்';

  @override
  String get backendUrlSavedSuccess => 'பின்தொடரக் URL வெற்றிகரமாக சேமிக்கப்பட்டது!';

  @override
  String get signInTitle => 'உள்நுழைவு';

  @override
  String get signInButton => 'உள்நுழைக';

  @override
  String get enterEmailError => 'உங்கள் மின்னஞ்சலை உள்ளிடவும்';

  @override
  String get invalidEmailError => 'தயவுசெய்து செல்லுபடியாகான மின்னஞ்சலை உள்ளிடவும்';

  @override
  String get enterPasswordError => 'உங்கள் கடவுளை உள்ளிடவும்';

  @override
  String get passwordMinLengthError => 'கடவுள் குறைந்தபட்சம் 8 வளர்பு நீண்டதாக இருக்க வேண்டும்';

  @override
  String get signInSuccess => 'உள்நுழைவு வெற்றிகரமாக நிறைவு!';

  @override
  String get alreadyHaveAccountLogin => 'ஏற்கனவே ஒரு ખाता உள்ளதா? நுழையவும்';

  @override
  String get emailLabel => 'மின்னஞ்சல்';

  @override
  String get passwordLabel => 'கடவுள்';

  @override
  String get createAccountTitle => 'கணக்கை உருவாக்கவும்';

  @override
  String get nameLabel => 'பெயர்';

  @override
  String get repeatPasswordLabel => 'கடவுளை மீண்டும்';

  @override
  String get signUpButton => 'பதிவுசெய்';

  @override
  String get enterNameError => 'உங்கள் பெயரை உள்ளிடவும்';

  @override
  String get passwordsDoNotMatch => 'கடவுள்கள் பொருந்தவில்லை';

  @override
  String get signUpSuccess => 'பதிவுசெய்தல் வெற்றிகரமாக!';

  @override
  String get loadingKnowledgeGraph => 'ஞ்ஞான வரைபடத்தை லோடுசெய்கிறது...';

  @override
  String get noKnowledgeGraphYet => 'இன்னும் ஞ்ஞான வரைபடம் இல்லை';

  @override
  String get buildingKnowledgeGraphFromMemories => 'நினைவுகளிலிருந்து உங்கள் ஞ்ஞான வரைபடத்தை உருவாக்குகிறது...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'நீங்கள் புதிய நினைவுகளை உருவாக்கும்போது உங்கள் ஞ்ஞான வரைபடம் தானாகவே உருவாக்கப்படும்.';

  @override
  String get buildGraphButton => 'வரைபடம் உருவாக்குங்கள்';

  @override
  String get checkOutMyMemoryGraph => 'என் நினைவு வரைபடத்தை சரிபார்க்கவும்!';

  @override
  String get getButton => 'பெறவும்';

  @override
  String openingApp(String appName) {
    return '$appName ஐ திறக்கிறது...';
  }

  @override
  String get writeSomething => 'ஏதாவது எழுதவும்';

  @override
  String get submitReply => 'பதிலை சமர்ப்பிக்கவும்';

  @override
  String get editYourReply => 'உங்கள் பதிலை தொகுப்பு';

  @override
  String get replyToReview => 'விமர்சனத்திற்குப் பதிலளிக்கவும்';

  @override
  String get rateAndReviewThisApp => 'இந்த பயன்பாட்டை மதிப்பிடுங்கள் மற்றும் விமர்சனம் செய்யுங்கள்';

  @override
  String get noChangesInReview => 'விமர்சனத்தில் எந்த மாற்றமும் இல்லை புதுப்பிக்க.';

  @override
  String get cantRateWithoutInternet => 'இணைய இணைப்பு இல்லாமல் பயன்பாட்டை மதிப்பிட முடியாது.';

  @override
  String get appAnalytics => 'பயன்பாடு பகுப்பாய்வு';

  @override
  String get learnMoreLink => 'மேலும் கற்று';

  @override
  String get moneyEarned => 'சம்பாதிக்க வேண்டிய பணம்';

  @override
  String get writeYourReply => 'உங்கள் பதிலை எழுதவும்...';

  @override
  String get replySentSuccessfully => 'பதில் வெற்றிகரமாக அனுப்பப்பட்டது';

  @override
  String failedToSendReply(String error) {
    return 'பதிலை அனுப்ப முடியவில்லை: $error';
  }

  @override
  String get send => 'அனுப்பவும்';

  @override
  String starFilter(int count) {
    return '$count நட்சத்திரம்';
  }

  @override
  String get noReviewsFound => 'விமர்சனம் கிடைக்கவில்லை';

  @override
  String get editReply => 'பதிலை தொகுப்பு';

  @override
  String get reply => 'பதிலளிக்கவும்';

  @override
  String starFilterLabel(int count) {
    return '$count நட்சத்திரம்';
  }

  @override
  String get sharePublicLink => 'பொதுவான இணைப்பைப் பகிர்ந்து கொள்ளுங்கள்';

  @override
  String get connectedKnowledgeData => 'இணைக்கப்பட்ட ஞ்ஞான தரவு';

  @override
  String get enterName => 'பெயரை உள்ளிடவும்';

  @override
  String get goal => 'லக்ష्य';

  @override
  String get tapToTrackThisGoal => 'இந்த লக்ష்யத்தைக் கண்காணிக்க தட்டவும்';

  @override
  String get tapToSetAGoal => 'ஒரு லக்ష்யம் அமைக்க தட்டவும்';

  @override
  String get processedConversations => 'செயலாக்கப்பட்ட உரையாடல்கள்';

  @override
  String get updatedConversations => 'புதுப்பிக்கப்பட்ட உரையாடல்கள்';

  @override
  String get newConversations => 'புதிய உரையாடல்கள்';

  @override
  String get summaryTemplate => 'சுருக்கம் வடிவமாக';

  @override
  String get suggestedTemplates => 'பரிந்துரைக்கப்பட்ட வடிவமாக';

  @override
  String get otherTemplates => 'மற்ற வடிவமாக';

  @override
  String get availableTemplates => 'கிடைக்கக்கூடிய வடிவமாக';

  @override
  String get getCreative => 'படைப்பாற்றல் பெறவும்';

  @override
  String get defaultLabel => 'இயல்பு';

  @override
  String get lastUsedLabel => 'கடைசியில் பயன்படுத்திய';

  @override
  String get setDefaultApp => 'இயல்பு பயன்பாட்டை அமைக்கவும்';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName ஐ உங்கள் இயல்பு சுருக்க பயன்பாட்டாக அமைக்கவும்?\\n\\nஇந்த பயன்பாடு அனைத்து வருங்கால உரையாடல் சுருக்கத்திற்கு தானாகவே பயன்படுத்தப்படும்.';
  }

  @override
  String get setDefaultButton => 'இயல்பு அமைக்கவும்';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName இயல்பு சுருக்க பயன்பாட்டாக அமைக்கப்பட்டது';
  }

  @override
  String get createCustomTemplate => 'கூறப்பட்ட வடிவமாக உருவாக்கவும்';

  @override
  String get allTemplates => 'அனைத்து வடிவமாக';

  @override
  String failedToInstallApp(String appName) {
    return '$appName ஐ நிறுவ முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appName நிறுவுவதில் பிழை: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'பேச்சாளர் $speakerId ஐ குறிப்பிடவும்';
  }

  @override
  String get personNameAlreadyExists => 'இந்த பெயரைக் கொண்ட ஒரு நபர் ஏற்கனவே உள்ளது।';

  @override
  String get selectYouFromList =>
      'உங்களைக் குறிப்பிட, பயன்படுத்தாதவர்கள் பட்டியலிலிருந்து \"நீங்கள்\" என்பதைத் தேர்ந்தெடுக்கவும்।';

  @override
  String get enterPersonsName => 'நபரின் பெயரை உள்ளிடவும்';

  @override
  String get addPerson => 'நபர் சேர்க்கவும்';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'இந்த பேச்சாளர்களிலிருந்து மற்ற பிரிவுகளைக் குறிப்பிடவும் ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'மற்ற பிரிவுகளைக் குறிப்பிடவும்';

  @override
  String get managePeople => 'மக்களை நிர்வகிக்கவும்';

  @override
  String get shareViaSms => 'SMS வழியாக பகிர்ந்து கொள்ளுங்கள்';

  @override
  String get selectContactsToShareSummary =>
      'உங்கள் உரையாடல் சுருக்கம் பகிர்ந்து கொள்ள பொருத்தப்பட்ட தொடர்பைத் தேர்ந்தெடுக்கவும்';

  @override
  String get searchContactsHint => 'பொருத்தப்பட்ட தொடர்பைத் தேடவும்...';

  @override
  String contactsSelectedCount(int count) {
    return '$count தேர்ந்தெடுக்கப்பட்ட';
  }

  @override
  String get clearAllSelection => 'அனைத்தையும் அழிக்கவும்';

  @override
  String get selectContactsToShare => 'பகிர்ந்து கொள்ள பொருத்தப்பட்ட தொடர்பைத் தேர்ந்தெடுக்கவும்';

  @override
  String shareWithContactCount(int count) {
    return '$count பொருத்தப்பட்ட தொடர்பிடன் பகிர்ந்து கொள்ளுங்கள்';
  }

  @override
  String shareWithContactsCount(int count) {
    return '$count பொருத்தப்பட்ட தொடர்புடன் பகிர்ந்து கொள்ளுங்கள்';
  }

  @override
  String get contactsPermissionRequired => 'பொருத்தப்பட்ட தொடர்பு நுழைவு தேவை';

  @override
  String get contactsPermissionRequiredForSms => 'SMS வழியாக பகிர்ந்து கொள்ள பொருத்தப்பட்ட தொடர்பு நுழைவு தேவை';

  @override
  String get grantContactsPermissionForSms => 'SMS வழியாக பகிர்ந்து கொள்ள பொருத்தப்பட்ட தொடர்பு அனுமதி வழங்கவும்';

  @override
  String get noContactsWithPhoneNumbers => 'தொலைபேசி எண்ணிருந்த பொருத்தப்பட்ட தொடர்பு கிடைக்கவில்லை';

  @override
  String get noContactsMatchSearch => 'உங்கள் தேடல்தொடக்கம் பொருத்தப்பட்ட தொடர்பு இல்லை';

  @override
  String get failedToLoadContacts => 'பொருத்தப்பட்ட தொடர்பை லோடுசெய்ய முடியவில்லை';

  @override
  String get failedToPrepareConversationForSharing =>
      'பகிர்ந்து கொள்ள உரையாடலைத் தயாரிக்க முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get couldNotOpenSmsApp => 'SMS பயன்பாட்டைத் திறக்க முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'இதோ நாம் விவாதித்தது: $link';
  }

  @override
  String get wifiSync => 'WiFi ஒத்திசைப்பு';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item கிளிப்பிங் பலகையில் நகலெடுக்கப்பட்டது';
  }

  @override
  String get wifiConnectionFailedTitle => 'இணைப்பு தவறிவிட்டது';

  @override
  String connectingToDeviceName(String deviceName) {
    return '$deviceName க்கு இணைக்கிறது';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '$deviceName का WiFi இயக்கவும்';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return '$deviceName க்கு இணைக்கவும்';
  }

  @override
  String get recordingDetails => 'பதிவுசெய்திய விவரணை';

  @override
  String get storageLocationSdCard => 'SD கார்டு';

  @override
  String get storageLocationLimitlessPendant => 'Limitless பதக';

  @override
  String get storageLocationPhone => 'தொலைபேசி';

  @override
  String get storageLocationPhoneMemory => 'தொலைபேசி (நினைவகம்)';

  @override
  String storedOnDevice(String deviceName) {
    return '$deviceName உள் சேமிக்கப்பட்டு';
  }

  @override
  String get transferring => 'பரிமாற்றுகிறது...';

  @override
  String get transferRequired => 'பரிமாற்றம் தேவை';

  @override
  String get downloadingAudioFromSdCard => 'உங்கள் சாதனத்தின் SD கார்டிலிருந்து ஆடியோ பதிவிறக்குகிறது';

  @override
  String get transferRequiredDescription =>
      'இந்த பதிவுசெய்தல் உங்கள் சாதனத்தின் SD கார்டில் சேமிக்கப்பட்டுள்ளது. இதை விளையாட அல்லது பகிர்ந்து கொள்ள உங்கள் தொலைபேசியில் மாற்றவும்.';

  @override
  String get cancelTransfer => 'பரிமாற்றம் ரத்து செய்யவும்';

  @override
  String get transferToPhone => 'தொலைபேசிக்கு பரிமாற்றவும்';

  @override
  String get privateAndSecureOnDevice => 'உங்கள் சாதனத்தில் தனிப்பட்டது மற்றும் உறுதியாக';

  @override
  String get recordingInfo => 'பதிவுசெய்திய தகவல்';

  @override
  String get transferInProgress => 'பரிமாற்றம் நடந்து கொண்டிருக்கிறது...';

  @override
  String get shareRecording => 'பதிவை பகிரவும்';

  @override
  String get deleteRecordingConfirmation =>
      'இந்த பதிவை நிரந்தரமாக நீக்க விரும்புகிறீர்களா? இதை செயல்தவிர்க்க முடியாது.';

  @override
  String get recordingIdLabel => 'பதிவு ID';

  @override
  String get dateTimeLabel => 'தேதி & நேரம்';

  @override
  String get durationLabel => 'கால அவதி';

  @override
  String get audioFormatLabel => 'ஆடியோ வடிவம்';

  @override
  String get storageLocationLabel => 'சேமிப்பு இடம்';

  @override
  String get estimatedSizeLabel => 'மதிப்பிடப்பட்ட அளவு';

  @override
  String get deviceModelLabel => 'சாதன மாதிரி';

  @override
  String get deviceIdLabel => 'சாதன ID';

  @override
  String get statusLabel => 'நிலை';

  @override
  String get statusProcessed => 'செயல்படுத்தப்பட்டது';

  @override
  String get statusUnprocessed => 'செயல்படுத்தப்படாதது';

  @override
  String get switchedToFastTransfer => 'விரைவு பரிமாற்றத்திற்கு மாற்றப்பட்டது';

  @override
  String get transferCompleteMessage => 'பரிமாற்றம் முடிந்தது! இப்போது இந்த பதிவை இயக்க முடியும்.';

  @override
  String transferFailedMessage(String error) {
    return 'பரிமாற்றம் தோல்வியுற்றது: $error';
  }

  @override
  String get transferCancelled => 'பரிமாற்றம் ரத்து செய்யப்பட்டது';

  @override
  String get fastTransferEnabled => 'விரைவு பரிமாற்றம் இயக்கப்பட்டது';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth ஒத்திசைவு இயக்கப்பட்டது';

  @override
  String get enableFastTransfer => 'விரைவு பரிமாற்றம் இயக்கவும்';

  @override
  String get fastTransferDescription =>
      'விரைவு பரிமாற்றம் WiFi ஐ பயன்படுத்தி ~5 மடங்கு வேகமாக பரிமாற்றம் செய்கிறது. பரிமாற்றத்தின் போது உங்கள் ஃபோன் தற்காலிகமாக உங்கள் Omi சாதனத்தின் WiFi நெட்வொர்க்குடன் இணைக்கப்படும்.';

  @override
  String get internetAccessPausedDuringTransfer => 'பரிமாற்றத்தின் போது இணைய அணுகல் நிறுத்தப்பட்டது';

  @override
  String get chooseTransferMethodDescription =>
      'உங்கள் Omi சாதனத்தில் இருந்து உங்கள் ஃபோனுக்கு பதிவுகளை எவ்வாறு பரிமாற்ற வேண்டும் என்பதைத் தேர்ந்தெடுக்கவும்.';

  @override
  String get wifiSpeed => 'WiFi வழியாக ~150 KB/s';

  @override
  String get fiveTimesFaster => '5 மடங்கு வேகமாக';

  @override
  String get fastTransferMethodDescription =>
      'உங்கள் Omi சாதனத்திற்கு நேரடி WiFi இணைப்பை உருவாக்குகிறது. பரிமாற்றத்தின் போது உங்கள் ஃபோன் உங்கள் வழக்கமான WiFi இல் இருந்து தற்காலிகமாக துண்டிக்கப்படும்.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => 'BLE வழியாக ~30 KB/s';

  @override
  String get bluetoothMethodDescription =>
      'நிலையான Bluetooth குறைந்த ஆற்றல் இணைப்பைப் பயன்படுத்துகிறது. மெதுவாக இருந்தாலும் உங்கள் WiFi இணைப்பை பாதிக்காது.';

  @override
  String get selected => 'தேர்ந்தெடுக்கப்பட்டது';

  @override
  String get selectOption => 'தேர்ந்தெடுக்கவும்';

  @override
  String get lowBatteryAlertTitle => 'குறைந்த பேட்டரி எச்சரிக்கை';

  @override
  String get lowBatteryAlertBody =>
      'உங்கள் சாதனத்தின் பேட்டரி குறைந்து விட்டது. மீண்டும் சார்ஜ் செய்ய வேண்டிய நேரம்! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'உங்கள் Omi சாதனம் துண்டிக்கப்பட்டது';

  @override
  String get deviceDisconnectedNotificationBody => 'உங்கள் Omi ஐ பயன்படுத்த மீண்டும் இணைக்கவும்.';

  @override
  String get firmwareUpdateAvailable => 'ஃபர்ம்வேர் புதுப்பிப்பு கிடைக்கிறது';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'உங்கள் Omi சாதனத்திற்கு ஒரு புதிய ஃபர்ம்வேர் புதுப்பிப்பு ($version) கிடைக்கிறது. இப்போது புதுப்பிக்க விரும்புகிறீர்களா?';
  }

  @override
  String get later => 'பிறகு';

  @override
  String get appDeletedSuccessfully => 'பயன்பாடு வெற்றிகரமாக நீக்கப்பட்டது';

  @override
  String get appDeleteFailed => 'பயன்பாடு நீக்க தோல்வியுற்றது. பின்னர் மீண்டும் முயற்சிக்கவும்.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'பயன்பாட்டு கண்ணியத் திறன் வெற்றிகரமாக மாற்றப்பட்டது. இது பிரதிபலிக்க சில நிமிடங்கள் ஆகலாம்.';

  @override
  String get errorActivatingAppIntegration =>
      'பயன்பாட்டைச் செயல்படுத்தும் போது பிழை. இது ஒரு ஒருங்கிணைப்பு பயன்பாடாக இருந்தால், அமைப்பு முடிந்துவிட்டதுதா என்பதை உறுதிசெய்யவும்.';

  @override
  String get errorUpdatingAppStatus => 'பயன்பாட்டு நிலை புதுப்பிக்கும் போது பிழை ஏற்பட்டது.';

  @override
  String get calculatingETA => 'கணக்கிடப்படுகிறது...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'சுமார் $minutes நிமிடங்கள் மீதமுள்ளது';
  }

  @override
  String get aboutAMinuteRemaining => 'சுமார் ஒரு நிமிடம் மீதமுள்ளது';

  @override
  String get almostDone => 'கிட்டத்தட்ட முடிந்துவிட்டது...';

  @override
  String get omiSays => 'omi கூறுகிறது';

  @override
  String get analyzingYourData => 'உங்கள் தரவை பகுப்பாய்வு செய்யப்படுகிறது...';

  @override
  String migratingToProtection(String level) {
    return '$level பாதுகாப்பிற்கு இடம்பெயர்ப்பு செய்யப்படுகிறது...';
  }

  @override
  String get noDataToMigrateFinalizing => 'இடம்பெயர்ப்பு செய்ய தரவு இல்லை. இறுதிசெய்யப்படுகிறது...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType இடம்பெயர்ப்பு செய்யப்படுகிறது... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing =>
      'அனைத்து பொருட்கள் இடம்பெயர்ப்பு செய்யப்பட்டுள்ளன. இறுதிசெய்யப்படுகிறது...';

  @override
  String get migrationErrorOccurred => 'இடம்பெயர்ப்பு செய்யும் போது பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get migrationComplete => 'இடம்பெயர்ப்பு முடிந்துவிட்டது!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'உங்கள் தரவு இப்போது புதிய $level அமைப்புகளுடன் பாதுகாக்கப்பட்டுள்ளது.';
  }

  @override
  String get chatsLowercase => 'சாட்கள்';

  @override
  String get dataLowercase => 'தரவு';

  @override
  String get fallNotificationTitle => 'ஐயோ';

  @override
  String get fallNotificationBody => 'நீங்கள் விழுந்தீர்களா?';

  @override
  String get importantConversationTitle => 'முக்கியமான உரையாடல்';

  @override
  String get importantConversationBody =>
      'நீங்கள் ஒரு முக்கியமான உரையாடல் கொண்டிருந்தீர்கள். சுருக்கத்தை மற்றவர்களுடன் பகிர்ந்தெடுக்க தொடவும்.';

  @override
  String get templateName => 'டெம்பிளேட் பெயர்';

  @override
  String get templateNameHint => 'எ.கா., மீட்டிங் செயல் பணிகள் சேகரிப்பான்';

  @override
  String get nameMustBeAtLeast3Characters => 'பெயர் குறைந்தபட்சம் 3 எழுத்துக்கள் இருக்க வேண்டும்';

  @override
  String get conversationPromptHint =>
      'எ.கா., வழங்கப்பட்ட உரையாடலிலிருந்து செயல் பணிகள், சிদ்ധாந்த முடிவுகள் மற்றும் முக்கிய கருத்துக்களை பிரித்தெடுக்கவும்.';

  @override
  String get pleaseEnterAppPrompt => 'உங்கள் பயன்பாட்டிற்கான ஒரு உத்தரவு உள்ளிடவும்';

  @override
  String get promptMustBeAtLeast10Characters => 'உத்தரவு குறைந்தபட்சம் 10 எழுத்துக்கள் இருக்க வேண்டும்';

  @override
  String get anyoneCanDiscoverTemplate => 'யாரும் உங்கள் டெம்பிளேட்டை கண்டறிய முடியும்';

  @override
  String get onlyYouCanUseTemplate => 'உங்கள் டெம்பிளேட்டை முடியும் பயன்படுத்த';

  @override
  String get generatingDescription => 'விளக்கம் உருவாக்கப்படுகிறது...';

  @override
  String get creatingAppIcon => 'பயன்பாட்டு ஐகான் உருவாக்கப்படுகிறது...';

  @override
  String get installingApp => 'பயன்பாடு நிறுவப்படுகிறது...';

  @override
  String get appCreatedAndInstalled => 'பயன்பாடு உருவாக்கப்பட்டு நிறுவப்பட்டது!';

  @override
  String get appCreatedSuccessfully => 'பயன்பாடு வெற்றிகரமாக உருவாக்கப்பட்டது!';

  @override
  String get failedToCreateApp => 'பயன்பாடு உருவாக்க தோல்வியுற்றது. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get addAppSelectCoreCapability =>
      'தொடர்ந்து செல்ல உங்கள் பயன்பாட்டிற்கு ஒன்று அல்லது அதற்கு மேல் முக்கிய திறன்களைத் தேர்ந்தெடுக்கவும்';

  @override
  String get addAppSelectPaymentPlan =>
      'உங்கள் பயன்பாட்டிற்கான பணம் செலுத்துதல் திட்டம் மற்றும் விலையை தேர்ந்தெடுக்கவும் மற்றும் உள்ளிடவும்';

  @override
  String get addAppSelectCapability => 'உங்கள் பயன்பாட்டிற்கு குறைந்தபட்சம் ஒரு திறன்களைத் தேர்ந்தெடுக்கவும்';

  @override
  String get addAppSelectLogo => 'உங்கள் பயன்பாட்டிற்கான ஒரு லோகோ தேர்ந்தெடுக்கவும்';

  @override
  String get addAppEnterChatPrompt => 'உங்கள் பயன்பாட்டிற்கான சாட் உத்தரவு உள்ளிடவும்';

  @override
  String get addAppEnterConversationPrompt => 'உங்கள் பயன்பாட்டிற்கான உரையாடல் உத்தரவு உள்ளிடவும்';

  @override
  String get addAppSelectTriggerEvent => 'உங்கள் பயன்பாட்டிற்கான ஒரு ட்ரிகர் நிகழ்வு தேர்ந்தெடுக்கவும்';

  @override
  String get addAppEnterWebhookUrl => 'உங்கள் பயன்பாட்டிற்கான webhook URL உள்ளிடவும்';

  @override
  String get addAppSelectCategory => 'உங்கள் பயன்பாட்டிற்கான ஒரு வகை தேர்ந்தெடுக்கவும்';

  @override
  String get addAppFillRequiredFields => 'அனைத்து தேவையான புலங்களை சரியாக நிரப்பவும்';

  @override
  String get addAppUpdatedSuccess => 'பயன்பாடு வெற்றிகரமாக புதுப்பிக்கப்பட்டது 🚀';

  @override
  String get addAppUpdateFailed => 'பயன்பாடு புதுப்பிக்க தோல்வியுற்றது. பின்னர் மீண்டும் முயற்சிக்கவும்';

  @override
  String get addAppSubmittedSuccess => 'பயன்பாடு வெற்றிகரமாக சமர்ப்பிக்கப்பட்டது 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'கோப்பு தேர்வாளரைத் திறக்க பிழை: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'படத்தைத் தேர்ந்தெடுக்கும் போது பிழை: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'புகைப்படங்கள் அனுமதி மறுக்கப்பட்டது. படத்தைத் தேர்ந்தெடுக்க புகைப்படங்களுக்கான அணுகலை அனுமதிக்கவும்';

  @override
  String get addAppErrorSelectingImageRetry => 'படத்தைத் தேர்ந்தெடுக்கும் போது பிழை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'சிறுபடத்தைத் தேர்ந்தெடுக்கும் போது பிழை: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'சிறுபடத்தைத் தேர்ந்தெடுக்கும் போது பிழை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get addAppCapabilityConflictWithPersona => 'விஷயங்கள் Persona உடன் தேர்ந்தெடுக்க முடியாது';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona மற்ற திறன்களுடன் தேர்ந்தெடுக்க முடியாது';

  @override
  String get paymentFailedToFetchCountries =>
      'ஆதரிக்கப்படும் நாடுகளை கொண்டு வர தோல்வியுற்றது. பின்னர் மீண்டும் முயற்சிக்கவும்.';

  @override
  String get paymentFailedToSetDefault =>
      'இயல்பு பணம் செலுத்துதல் முறையை அமைக்க தோல்வியுற்றது. பின்னர் மீண்டும் முயற்சிக்கவும்.';

  @override
  String get paymentFailedToSavePaypal => 'PayPal விவரங்களைச் சேமிக்க தோல்வியுற்றது. பின்னர் மீண்டும் முயற்சிக்கவும்.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'செயல்படும்';

  @override
  String get paymentStatusConnected => 'இணைக்கப்பட்டது';

  @override
  String get paymentStatusNotConnected => 'இணைக்கப்படாதது';

  @override
  String get paymentAppCost => 'பயன்பாட்டின் செலவு';

  @override
  String get paymentEnterValidAmount => 'ஒரு செல்லுபடியான அளவை உள்ளிடவும்';

  @override
  String get paymentEnterAmountGreaterThanZero => '0 ஐ விட அதிகமான அளவை உள்ளிடவும்';

  @override
  String get paymentPlan => 'பணம் செலுத்துதல் திட்டம்';

  @override
  String get paymentNoneSelected => 'எதுவும் தேர்ந்தெடுக்கப்படவில்லை';

  @override
  String get aiGenPleaseEnterDescription => 'உங்கள் பயன்பாட்டிற்கான விளக்கம் உள்ளிடவும்';

  @override
  String get aiGenCreatingAppIcon => 'பயன்பாட்டு ஐகான் உருவாக்கப்படுகிறது...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'பிழை ஏற்பட்டது: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'பயன்பாடு வெற்றிகரமாக உருவாக்கப்பட்டது!';

  @override
  String get aiGenFailedToCreateApp => 'பயன்பாடு உருவாக்க தோல்வியுற்றது';

  @override
  String get aiGenErrorWhileCreatingApp => 'பயன்பாடு உருவாக்கும் போது பிழை ஏற்பட்டது';

  @override
  String get aiGenFailedToGenerateApp => 'பயன்பாடு உருவாக்க தோல்வியுற்றது. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get aiGenFailedToRegenerateIcon => 'ஐகான் மீண்டும் உருவாக்க தோல்வியுற்றது';

  @override
  String get aiGenPleaseGenerateAppFirst => 'முதலில் பயன்பாட்டை உருவாக்கவும்';

  @override
  String get nextButton => 'அடுத்தது';

  @override
  String get connectOmiDevice => 'Omi சாதனத்தை இணைக்கவும்';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'நீங்கள் உங்கள் எல்லையற்ற திட்டத்தை $title ஆக மாற்றுகிறீர்கள். நீங்கள் தொடர்ந்து செல்ல விரும்புகிறீர்களா?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'அபிவிருத்தி திட்டமிடப்பட்டுள்ளது! உங்கள் மாதாந்திர திட்டம் உங்கள் பிற்படிக்கும் காலத்தின் முடிவு வரை தொடர்ந்து, பின்னர் தானாக வாராந்திரத்தாக மாற்றப்படும்.';

  @override
  String get couldNotSchedulePlanChange => 'திட்டம் மாற்றத்தை திட்டமிட முடியவில்லை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get subscriptionReactivatedDefault =>
      'உங்கள் சந்தா மீண்டும் செயல்படுத்தப்பட்டுள்ளது! இப்போது கட்டணம் இல்லை - உங்கள் தற்போதைய காலத்தின் முடிவে பிற்படிக்க வேண்டிய வரை பாக்கியுள்ளது.';

  @override
  String get subscriptionSuccessfulCharged =>
      'சந்தா வெற்றிகரமாக! நতுங்கள் புதிய பிற்படிக்கும் காலத்திற்கு பாக்கியுள்ளது.';

  @override
  String get couldNotProcessSubscription => 'சந்தா செயல்படுத்த முடியவில்லை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get couldNotLaunchUpgradePage => 'அபிவிருத்தி பக்கத்தைத் திறக்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get transcriptionJsonPlaceholder => 'உங்கள் JSON கட்டமைப்பை இங்கே ஒட்டவும்...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'கோப்பு தேர்வாளரைத் திறக்க பிழை: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'பிழை: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'உரையாடல்கள் வெற்றிகரமாக இணைக்கப்பட்டது';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count உரையாடல்கள் வெற்றிகரமாக இணைக்கப்பட்டுள்ளன';
  }

  @override
  String get actionItemReminderTitle => 'Omi நினைவூட்டல்';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName துண்டிக்கப்பட்டது';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'உங்கள் $deviceName ஐப் பயன்படுத்த மீண்டும் இணைக்கவும்.';
  }

  @override
  String get onboardingSignIn => 'உள்நுழைக';

  @override
  String get onboardingYourName => 'உங்கள் பெயர்';

  @override
  String get onboardingLanguage => 'மொழி';

  @override
  String get onboardingPermissions => 'அনுமதிகள்';

  @override
  String get onboardingComplete => 'முடிவு';

  @override
  String get onboardingWelcomeToOmi => 'Omi க்கு வரவேற்கிறோம்';

  @override
  String get onboardingTellUsAboutYourself => 'உங்களைப் பற்றி சொல்லுங்கள்';

  @override
  String get onboardingChooseYourPreference => 'உங்கள் விருப்பத்தைத் தேர்ந்தெடுக்கவும்';

  @override
  String get onboardingGrantRequiredAccess => 'தேவையான அணுகலை வழங்கவும்';

  @override
  String get onboardingYoureAllSet => 'நீங்கள் அனைத்தும் தயாராகிவிட்டீர்கள்';

  @override
  String get searchTranscriptOrSummary => 'மாற்றுரையை அல்லது சுருக்கத்தைத் தேடவும்...';

  @override
  String get myGoal => 'என் இலக்கு';

  @override
  String get appNotAvailable => 'ஐயோ! நீங்கள் தேடும் பயன்பாடு கிடைக்கவில்லை.';

  @override
  String get failedToConnectTodoist => 'Todoist ஐ இணைக்க தோல்வியுற்றது';

  @override
  String get failedToConnectAsana => 'Asana ஐ இணைக்க தோல்வியுற்றது';

  @override
  String get failedToConnectGoogleTasks => 'Google Tasks ஐ இணைக்க தோல்வியுற்றது';

  @override
  String get failedToConnectClickUp => 'ClickUp ஐ இணைக்க தோல்வியுற்றது';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName ஐ இணைக்க தோல்வியுற்றது: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Todoist ஆக வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get failedToConnectTodoistRetry => 'Todoist ஐ இணைக்க தோல்வியுற்றது. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get successfullyConnectedAsana => 'Asana ஆக வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get failedToConnectAsanaRetry => 'Asana ஐ இணைக்க தோல்வியுற்றது. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get successfullyConnectedGoogleTasks => 'Google Tasks ஆக வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google Tasks ஐ இணைக்க தோல்வியுற்றது. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get successfullyConnectedClickUp => 'ClickUp ஆக வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get failedToConnectClickUpRetry => 'ClickUp ஐ இணைக்க தோல்வியுற்றது. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get successfullyConnectedNotion => 'Notion ஆக வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get failedToRefreshNotionStatus => 'Notion இணைப்பு நிலையை புதுப்பிக்க தோல்வியுற்றது.';

  @override
  String get successfullyConnectedGoogle => 'Google ஆக வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get failedToRefreshGoogleStatus => 'Google இணைப்பு நிலையை புதுப்பிக்க தோல்வியுற்றது.';

  @override
  String get successfullyConnectedWhoop => 'Whoop ஆக வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get failedToRefreshWhoopStatus => 'Whoop இணைப்பு நிலையை புதுப்பிக்க தோல்வியுற்றது.';

  @override
  String get successfullyConnectedGitHub => 'GitHub ஆக வெற்றிகரமாக இணைக்கப்பட்டது!';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub இணைப்பு நிலையை புதுப்பிக்க தோல்வியுற்றது.';

  @override
  String get authFailedToSignInWithGoogle => 'Google ஆக உள்நுழைக தோல்வியுற்றது, மீண்டும் முயற்சிக்கவும்.';

  @override
  String get authenticationFailed => 'அங்கீகாரம் தோல்வியுற்றது. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get authFailedToSignInWithApple => 'Apple ஆக உள்நுழைக தோல்வியுற்றது, மீண்டும் முயற்சிக்கவும்.';

  @override
  String get authFailedToRetrieveToken => 'Firebase டோகனை பெற தோல்வியுற்றது, மீண்டும் முயற்சிக்கவும்.';

  @override
  String get authUnexpectedErrorFirebase => 'உள்நுழைய அপ்பாவமற்ற பிழை, Firebase பிழை, மீண்டும் முயற்சிக்கவும்.';

  @override
  String get authUnexpectedError => 'உள்நுழைய அப்பாவமற்ற பிழை, மீண்டும் முயற்சிக்கவும்';

  @override
  String get authFailedToLinkGoogle => 'Google உடன் இணைக்க தோல்வியுற்றது, மீண்டும் முயற்சிக்கவும்.';

  @override
  String get authFailedToLinkApple => 'Apple உடன் இணைக்க தோல்வியுற்றது, மீண்டும் முயற்சிக்கவும்.';

  @override
  String get onboardingBluetoothRequired => 'உங்கள் சாதனத்துடன் இணைக்க Bluetooth அனுமதி தேவை.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth அனுமதி மறுக்கப்பட்டது. সিஸ்டம் விருப்பங்களில் அனுமதி வழங்கவும்.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth அனுமதி நிலை: $status. சிஸ்டம் விருப்பங்களைச் சரிசெய்யவும்.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth அனுமதி சரிசெய்ய தோல்வியுற்றது: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'அறிவிப்பு அனுமதி மறுக்கப்பட்டது. சிஸ்டம் விருப்பங்களில் அனுமதி வழங்கவும்.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'அறிவிப்பு அனுமதி மறுக்கப்பட்டது. சிஸ்டம் விருப்பங்கள் > அறிவிப்புகளில் அனுமதி வழங்கவும்.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'அறிவிப்பு அனுமதி நிலை: $status. சிஸ்டம் விருப்பங்களைச் சரிசெய்யவும்.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'அறிவிப்பு அனுமதி சரிசெய்ய தோல்வியுற்றது: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'அமைப்புகள் > தனியுரிமை & பாதுகாப்பு > இருப்பிடம் சேவைகளில் இருப்பிடம் அனுமதி வழங்கவும்';

  @override
  String get onboardingMicrophoneRequired => 'ஒலிபதிவுக்கு மைக்ரோஃபோன் அனுமதி தேவை.';

  @override
  String get onboardingMicrophoneDenied =>
      'மைக்ரோஃபோன் அனுமதி மறுக்கப்பட்டது. சிஸ்டம் விருப்பங்கள் > தனியுரிமை & பாதுகாப்பு > மைக்ரோஃபோனில் அனுமதி வழங்கவும்.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'மைக்ரோஃபோன் அனுமதி நிலை: $status. சிஸ்டம் விருப்பங்களைச் சரிசெய்யவும்.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'மைக்ரோஃபோன் அனுமதி சரிசெய்ய தோல்வியுற்றது: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'கணினி ஆடியோ ஒலிபதிவுக்கு திரை பிடிப்பு அனுமதி தேவை.';

  @override
  String get onboardingScreenCaptureDenied =>
      'திரை பிடிப்பு அனுமதி மறுக்கப்பட்டது. சிஸ்டம் விருப்பங்கள் > தனியுரிமை & பாதுகாப்பு > திரை ஒலிபதிவுகளில் அனுமதி வழங்கவும்.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'திரை பிடிப்பு அனுமதி நிலை: $status. சிஸ்டம் விருப்பங்களைச் சரிசெய்யவும்.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'திரை பிடிப்பு அனுமதி சரிசெய்ய தோல்வியுற்றது: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'உலாவி சந்திப்புகளைக் கண்டறிய அணுகல் அனுமதி தேவை.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'அணுகல் அனுமதி நிலை: $status. சிஸ்டம் விருப்பங்களைச் சரிசெய்யவும்.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'அணுகல் அனுமதி சரிசெய்ய தோல்வியுற்றது: $error';
  }

  @override
  String get msgCameraNotAvailable => 'கேமரா பிடிப்பு இந்த தளத்தில் கிடைக்கவில்லை';

  @override
  String get msgCameraPermissionDenied => 'கேமரா அனுமதி மறுக்கப்பட்டது. கேமரா அணுகல் அனுமதிக்கவும்';

  @override
  String msgCameraAccessError(String error) {
    return 'கேமரா அணுகும் போது பிழை: $error';
  }

  @override
  String get msgPhotoError => 'புகைப்படம் எடுக்கும் போது பிழை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get msgMaxImagesLimit => 'நீங்கள் 4 புகைப்படங்கள் வரை தேர்ந்தெடுக்க முடியும்';

  @override
  String msgFilePickerError(String error) {
    return 'கோப்பு தேர்வாளரைத் திறக்க பிழை: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'புகைப்படங்களைத் தேர்ந்தெடுக்கும் போது பிழை: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'புகைப்படங்கள் அனுமதி மறுக்கப்பட்டது. புகைப்படங்களைத் தேர்ந்தெடுக்க புகைப்படங்களுக்கான அணுகலை அனுமதிக்கவும்';

  @override
  String get msgSelectImagesGenericError => 'புகைப்படங்களைத் தேர்ந்தெடுக்கும் போது பிழை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get msgMaxFilesLimit => 'நீங்கள் 4 கோப்புகள் வரை தேர்ந்தெடுக்க முடியும்';

  @override
  String msgSelectFilesError(String error) {
    return 'கோப்புகளைத் தேர்ந்தெடுக்கும் போது பிழை: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'கோப்புகளைத் தேர்ந்தெடுக்கும் போது பிழை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get msgUploadFileFailed => 'கோப்பு பதிவேற்ற தோல்வியுற்றது, பின்னர் மீண்டும் முயற்சிக்கவும்';

  @override
  String get msgReadingMemories => 'உங்கள் நினைவுகளை வாசிப்பது...';

  @override
  String get msgLearningMemories => 'உங்கள் நினைவுகளிலிருந்து கற்றல்...';

  @override
  String get msgUploadAttachedFileFailed => 'இணைக்கப்பட்ட கோப்பை பதிவேற்ற தோல்வியுற்றது.';

  @override
  String captureRecordingError(String error) {
    return 'ஒலிபதிவு செய்யும் போது பிழை ஏற்பட்டது: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'ஒலிபதிவு நிறுத்தப்பட்டது: $reason. நீங்கள் வெளிப்புற காட்சிகளை மீண்டும் இணைக்க அல்லது ஒலிபதிவை மீண்டும் தொடங்க வேண்டியிருக்கலாம்.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'மைக்ரோஃபோன் அனுமதி தேவை';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'சிஸ்டம் விருப்பங்களில் மைக்ரோஃபோன் அனுமதி வழங்கவும்';

  @override
  String get captureScreenRecordingPermissionRequired => 'திரை ஒலிபதிவு அனுமதி தேவை';

  @override
  String get captureDisplayDetectionFailed => 'காட்சி கண்டறிதல் தோல்வியுற்றது. ஒலிபதிவு நிறுத்தப்பட்டது.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'செல்லுபடியற்ற ஆடியோ பைட்டுகள் webhook URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'செல்லுபடியற்ற ரியல் நேர மாற்றுரை webhook URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'செல்லுபடியற்ற உரையாடல் உருவாக்கப்பட்ட webhook URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'செல்லுபடியற்ற நாள் சுருக்கம் webhook URL';

  @override
  String get devModeSettingsSaved => 'அமைப்புகள் சேமிக்கப்பட்டது!';

  @override
  String get voiceFailedToTranscribe => 'ஆடியோ மாற்றுவதில் தோல்வி';

  @override
  String get locationPermissionRequired => 'இருப்பிடம் அனுமதி தேவை';

  @override
  String get locationPermissionContent =>
      'விரைவு பரிமாற்றம் WiFi இணைப்பை சரிசெய்ய இருப்பிடம் அனுமதி தேவை. தொடர்ந்து செல்ல இருப்பிடம் அனுமதி வழங்கவும்.';

  @override
  String get pdfTranscriptExport => 'மாற்றுரை ஏற்றுமதி';

  @override
  String get pdfConversationExport => 'உரையாடல் ஏற்றுமதி';

  @override
  String pdfTitleLabel(String title) {
    return 'தலைப்பு: $title';
  }

  @override
  String get conversationNewIndicator => 'புதிய 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count புகைப்படங்கள்';
  }

  @override
  String get mergingStatus => 'இணைக்கப்படுகிறது...';

  @override
  String timeSecsSingular(int count) {
    return '$count நிலை';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count நிலைகள்';
  }

  @override
  String timeMinSingular(int count) {
    return '$count நிமி';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count நிமி';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins நிமி $secs நிலை';
  }

  @override
  String timeHourSingular(int count) {
    return '$count மணி';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count மணி';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours மணி $mins நிமி';
  }

  @override
  String timeDaySingular(int count) {
    return '$count நாள்';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count நாள்';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days நாள் $hours மணி';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countநி';
  }

  @override
  String timeCompactMins(int count) {
    return '$countநி';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsநி $secsநி';
  }

  @override
  String timeCompactHours(int count) {
    return '$countம';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursம $minsநி';
  }

  @override
  String get moveToFolder => 'கோப்புறைக்கு நகர்த்தவும்';

  @override
  String get noFoldersAvailable => 'கோப்புறைகள் இல்லை';

  @override
  String get newFolder => 'புதிய கோப்புறை';

  @override
  String get color => 'நிறம்';

  @override
  String get waitingForDevice => 'சாதனத்திற்காக காத்திருக்கிறது...';

  @override
  String get saySomething => 'ஒன்று சொல்லவும்...';

  @override
  String get initialisingSystemAudio => 'கணினி ஆடியோ இயக்கப்படுகிறது';

  @override
  String get stopRecording => 'ஒலிபதிவு நிறுத்தவும்';

  @override
  String get continueRecording => 'ஒலிபதிவு தொடரவும்';

  @override
  String get initialisingRecorder => 'ஒலிபதிவாளர் இயக்கப்படுகிறது';

  @override
  String get pauseRecording => 'ஒலிபதிவு இடைநிறுத்தவும்';

  @override
  String get resumeRecording => 'ஒலிபதிவு மீண்டும் தொடரவும்';

  @override
  String get noDailyRecapsYet => 'இதுவரை தினசரி சுருக்கங்கள் இல்லை';

  @override
  String get dailyRecapsDescription => 'உங்கள் தினசரி சுருக்கங்கள் உருவாக்கப்பட்ட பிறகு இங்கே தோன்றும்';

  @override
  String get chooseTransferMethod => 'பரிமாற்ற முறையைத் தேர்ந்தெடுக்கவும்';

  @override
  String get fastTransferSpeed => 'WiFi வழியாக ~150 KB/s';

  @override
  String largeTimeGapDetected(String gap) {
    return 'பெரிய நேர இடைவெளி கண்டறியப்பட்டது ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'பெரிய நேர இடைவெளிகள் கண்டறியப்பட்டுள்ளன ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'சாதனம் WiFi ஒத்திசைவை ஆதரிக்கவில்லை, Bluetooth இற்கு மாற்றப்படுகிறது';

  @override
  String get appleHealthNotAvailable => 'Apple Health இந்த சாதனத்தில் கிடைக்கவில்லை';

  @override
  String get downloadAudio => 'ஆடியோ பதிவிறக்கவும்';

  @override
  String get audioDownloadSuccess => 'ஆடியோ வெற்றிகரமாக பதிவிறக்கப்பட்டது';

  @override
  String get audioDownloadFailed => 'ஆடியோ பதிவிறக்க தோல்வியுற்றது';

  @override
  String get downloadingAudio => 'ஆடியோ பதிவிறக்கப்படுகிறது...';

  @override
  String get shareAudio => 'ஆடியோ பகிரவும்';

  @override
  String get preparingAudio => 'ஆடியோ தயாரிக்கப்படுகிறது';

  @override
  String get gettingAudioFiles => 'ஆடியோ கோப்புகள் கொண்டு வரப்படுகிறது...';

  @override
  String get downloadingAudioProgress => 'ஆடியோ பதிவிறக்கப்படுகிறது';

  @override
  String get processingAudio => 'ஆடியோ செயல்படுத்தப்படுகிறது';

  @override
  String get combiningAudioFiles => 'ஆடியோ கோப்புகள் இணைக்கப்படுகிறது...';

  @override
  String get audioReady => 'ஆடியோ தயாரம்';

  @override
  String get openingShareSheet => 'பகிர்ந்தெடுக்குதல் பத்திரிகை திறக்கப்படுகிறது...';

  @override
  String get audioShareFailed => 'பகிர்ந்தெடுக்குதல் தோல்வியுற்றது';

  @override
  String get dailyRecaps => 'தினசரி சுருக்கங்கள்';

  @override
  String get removeFilter => 'வடிப்பிலை நீக்கவும்';

  @override
  String get categoryConversationAnalysis => 'உரையாடல் பகுப்பாய்வு';

  @override
  String get categoryHealth => 'ஆரோக்கியம்';

  @override
  String get categoryEducation => 'கல்வி';

  @override
  String get categoryCommunication => 'தொடர்பாடல்';

  @override
  String get categoryEmotionalSupport => 'உணர்வு ஆதரவு';

  @override
  String get categoryProductivity => 'உற்பादকத்வம்';

  @override
  String get categoryEntertainment => 'பொழுதுபோக்கு';

  @override
  String get categoryFinancial => 'நிதி';

  @override
  String get categoryTravel => 'பயணம்';

  @override
  String get categorySafety => 'பாதுகாப்பு';

  @override
  String get categoryShopping => 'வாங்குதல்';

  @override
  String get categorySocial => 'சமூக';

  @override
  String get categoryNews => 'செய்திகள்';

  @override
  String get categoryUtilities => 'பயன்பாடுகள்';

  @override
  String get categoryOther => 'பிற';

  @override
  String get capabilityChat => 'சாட்';

  @override
  String get capabilityConversations => 'உரையாடல்கள்';

  @override
  String get capabilityExternalIntegration => 'வெளிப்புற ஒருங்கிணைப்பு';

  @override
  String get capabilityNotification => 'அறிவிப்பு';

  @override
  String get triggerAudioBytes => 'ஆடியோ பைட்டுகள்';

  @override
  String get triggerConversationCreation => 'உரையாடல் உருவாக்கம்';

  @override
  String get triggerTranscriptProcessed => 'மாற்றுரை செயல்படுத்தப்பட்டது';

  @override
  String get actionCreateConversations => 'உரையாடல்களை உருவாக்கவும்';

  @override
  String get actionCreateMemories => 'நினைவுகளை உருவாக்கவும்';

  @override
  String get actionReadConversations => 'உரையாடல்களை வாசிக்கவும்';

  @override
  String get actionReadMemories => 'நினைவுகளை வாசிக்கவும்';

  @override
  String get actionReadTasks => 'பணிகளை வாசிக்கவும்';

  @override
  String get scopeUserName => 'பயனர் பெயர்';

  @override
  String get scopeUserFacts => 'பயனர் உண்மைகள்';

  @override
  String get scopeUserConversations => 'பயனர் உரையாடல்கள்';

  @override
  String get scopeUserChat => 'பயனர் சாட்';

  @override
  String get capabilitySummary => 'சுருக்கம்';

  @override
  String get capabilityFeatured => 'சிறப்பு';

  @override
  String get capabilityTasks => 'பணிகள்';

  @override
  String get capabilityIntegrations => 'ஒருங்கிணைப்புகள்';

  @override
  String get categoryProductivityLifestyle => 'உற்பादகத்வம் & வாழ்க்கைப் பாணி';

  @override
  String get categorySocialEntertainment => 'சமூக & பொழுதுபோக்கு';

  @override
  String get categoryProductivityTools => 'உற்பादகத்வம் & கருவிகள்';

  @override
  String get categoryPersonalWellness => 'தனிப்பட்ட & வாழ்க்கை முறை';

  @override
  String get rating => 'மதிப்பீடு';

  @override
  String get categories => 'பிரிவுகள்';

  @override
  String get sortBy => 'வரிசைப்படுத்து';

  @override
  String get highestRating => 'மிக உயர்ந்த மதிப்பீடு';

  @override
  String get lowestRating => 'மிக குறைந்த மதிப்பீடு';

  @override
  String get resetFilters => 'வடிப்பான்களை மீட்டமை';

  @override
  String get applyFilters => 'வடிப்பான்களைப் பயன்படுத்து';

  @override
  String get mostInstalls => 'அதிகம் நிறுவப்பட்ட';

  @override
  String get couldNotOpenUrl => 'URL ஐ திறக்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get newTask => 'புதிய பணி';

  @override
  String get viewAll => 'அனைத்தையும் பார்';

  @override
  String get addTask => 'பணியைச் சேர்க்க';

  @override
  String get addMcpServer => 'MCP சேவையகத்தைச் சேர்க்க';

  @override
  String get connectExternalAiTools => 'வெளிப்புற AI கருவிகளைத் தொடர்புபடுத்து';

  @override
  String get mcpServerUrl => 'MCP சேவையக URL';

  @override
  String mcpServerConnected(int count) {
    return '$count கருவிகள் வெற்றிகரமாக இணைக்கப்பட்டுள்ளன';
  }

  @override
  String get mcpConnectionFailed => 'MCP சேவையகத்துடன் இணைக்க முடியவில்லை';

  @override
  String get authorizingMcpServer => 'அங்கீகாரம் கொடுக்கப்படுகிறது...';

  @override
  String get whereDidYouHearAboutOmi => 'நீங்கள் எங்களை எப்படிக் கண்டுபிடித்தீர்கள்?';

  @override
  String get tiktok => 'TikTok';

  @override
  String get youtube => 'YouTube';

  @override
  String get instagram => 'Instagram';

  @override
  String get xTwitter => 'X (Twitter)';

  @override
  String get reddit => 'Reddit';

  @override
  String get friendWordOfMouth => 'நண்பர்';

  @override
  String get otherSource => 'பிற';

  @override
  String get pleaseSpecify => 'தயவுசெய்து குறிப்பிடவும்';

  @override
  String get event => 'நிகழ்வு';

  @override
  String get coworker => 'சக-கர்மचारி';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google தேடல்';

  @override
  String get audioPlaybackUnavailable => 'ஆடியோ கோப்பு இயக்கத்திற்கு उपलब्ध அல்ல';

  @override
  String get audioPlaybackFailed => 'ஆடியோவை இயக்க முடியவில்லை. கோப்பு சிதைந்திருக்கலாம் அல்லது காணவில்லை.';

  @override
  String get connectionGuide => 'இணைப்பு வழிகாட்டி';

  @override
  String get iveDoneThis => 'நான் இதை செய்துவிட்டேன்';

  @override
  String get pairNewDevice => 'புதிய சாதனத்தை இணைக்க';

  @override
  String get dontSeeYourDevice => 'உங்கள் சாதனம் தெரியவில்லையா?';

  @override
  String get reportAnIssue => 'ஒரு சிக்கலைப் பிரதிবेदन செய்யுங்கள்';

  @override
  String get pairingTitleOmi => 'Omi ஐ இயக்கவும்';

  @override
  String get pairingDescOmi => 'சாதனம் நடுங்கும் வரை பொத்தானை அழுத்திப் பிடித்திருக்கவும்.';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit ஐ ஜோடி மோடில் வைக்கவும்';

  @override
  String get pairingDescOmiDevkit =>
      'இயக்கப் பொத்தானை ஒரு முறை அழுத்தவும். LED ஜோடி மோடில் இருக்கும்போது இளஞ்சிவப்பு நிறத்தில் மின்னும்.';

  @override
  String get pairingTitleOmiGlass => 'Omi Glass ஐ இயக்கவும்';

  @override
  String get pairingDescOmiGlass => 'பக்க பொத்தானை 3 வினாடிகளுக்கு அழுத்தி இயக்கவும்.';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note ஐ ஜோடி மோடில் வைக்கவும்';

  @override
  String get pairingDescPlaudNote =>
      'பக்க பொத்தானை 2 வினாடிகளுக்கு அழுத்திப் பிடித்திருக்கவும். சிவப்பு LED ஜோடியாக்க தயாரிக்கும்போது மின்னும்.';

  @override
  String get pairingTitleBee => 'Bee ஐ ஜோடி மோடில் வைக்கவும்';

  @override
  String get pairingDescBee =>
      'பொத்தானை 5 முறை தொடர்ந்து அழுத்தவும். விளக்கு நீல மற்றும் பச்சை நிறத்தில் மின்ன ஆரம்பிக்கும்.';

  @override
  String get pairingTitleLimitless => 'Limitless ஐ ஜோடி மோடில் வைக்கவும்';

  @override
  String get pairingDescLimitless =>
      'ஏதேனும் விளக்கு தெரியும்போது, ஒரு முறை அழுத்தவும் பின்னர் சாதனம் இளஞ்சிவப்பு விளக்கைக் காட்டும் வரை அழுத்திப் பிடித்திருக்கவும்.';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant ஐ ஜோடி மோடில் வைக்கவும்';

  @override
  String get pairingDescFriendPendant => 'பதக்கத்தில் உள்ள பொத்தானை அழுத்தவும். இது தானாகவே ஜோடி மோடிற்குள் நுழையும்.';

  @override
  String get pairingTitleFieldy => 'Fieldy ஐ ஜோடி மோடில் வைக்கவும்';

  @override
  String get pairingDescFieldy => 'சாதனம் இயக்க விளக்கு தோன்றும் வரை அழுத்திப் பிடித்திருக்கவும்.';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch ஐ இணைக்கவும்';

  @override
  String get pairingDescAppleWatch =>
      'உங்கள் Apple Watch ல் Omi பயன்பாட்டை நிறுவி திறக்கவும், பின்னர் பயன்பாட்டில் இணைக்கவும்.';

  @override
  String get pairingTitleNeoOne => 'Neo One ஐ ஜோடி மோடில் வைக்கவும்';

  @override
  String get pairingDescNeoOne =>
      'LED மின்னும் வரை power பொத்தானை அழுத்திப் பிடித்திருக்கவும். சாதனம் கண்டறியக்கூடியதாக இருக்கும்.';

  @override
  String get downloadingFromDevice => 'சாதனத்தில் இருந்து பதிவிறக்குகிறது';

  @override
  String get reconnectingToInternet => 'இணையத்துடன் மீண்டும் இணைக்கிறது...';

  @override
  String uploadingToCloud(int current, int total) {
    return '$current / $total ஐ பதிவேற்றுகிறது';
  }

  @override
  String get processingOnServer => 'சேவையகத்தில் செயல்படுத்துகிறது...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'செயல்படுத்துகிறது... $current/$total பிரிவுகள்';
  }

  @override
  String get processedStatus => 'செயல்படுத்தப்பட்டது';

  @override
  String get corruptedStatus => 'சிதைந்தது';

  @override
  String nPending(int count) {
    return '$count நிலுவையில் உள்ளது';
  }

  @override
  String nProcessed(int count) {
    return '$count செயல்படுத்தப்பட்டது';
  }

  @override
  String get synced => 'ஒத்திசைக்கப்பட்டது';

  @override
  String get noPendingRecordings => 'நிலுவையில் உள்ள பதிவுகள் இல்லை';

  @override
  String get noProcessedRecordings => 'இன்னும் செயல்படுத்தப்பட்ட பதிவுகள் இல்லை';

  @override
  String get pending => 'நிலுவையில் உள்ளது';

  @override
  String whatsNewInVersion(String version) {
    return 'பதிப்பு $version இல் புதியவை';
  }

  @override
  String get addToYourTaskList => 'உங்கள் பணிப்பட்டியலில் சேர்க்கலாமா?';

  @override
  String get failedToCreateShareLink => 'பகிர்வு இணைப்பை உருவாக்க முடியவில்லை';

  @override
  String get deleteGoal => 'இலக்கை நீக்கு';

  @override
  String get deviceUpToDate => 'உங்கள் சாதனம் தற்போதைய பதிப்பில் உள்ளது';

  @override
  String get wifiConfiguration => 'WiFi அமைப்பாடு';

  @override
  String get wifiConfigurationSubtitle => 'நீக்ஸ்மெয়ர் பதிவிறக்குவதற்கு நீங்கள் உங்கள் WiFi நிலைமங்களைf உள்ளிடவும்.';

  @override
  String get networkNameSsid => 'நெட்வொர்க் பெயர் (SSID)';

  @override
  String get enterWifiNetworkName => 'WiFi நெட்வொர்க் பெயரைச் சொல்லவும்';

  @override
  String get enterWifiPassword => 'WiFi கடவுச்சொல்லை உள்ளிடவும்';

  @override
  String get appIconLabel => 'பயன்பாட்டு ஐகான்';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'இதை நான் உங்களைப் பற்றி அறிந்துள்ளேன்';

  @override
  String get onboardingWhatIKnowAboutYouDescription =>
      'Omi உங்கள் உரையாடல்களிலிருந்து கற்கும்போது இந்தக் கட்டம் புதுப்பிக்கப்படுகிறது.';

  @override
  String get apiEnvironment => 'API சூழல்';

  @override
  String get apiEnvironmentDescription => 'எந்த பின்தளத்துடன் இணைக்க வேண்டுமென்பதை தேர்வு செய்யவும்';

  @override
  String get production => 'உৎপादन';

  @override
  String get staging => 'Staging';

  @override
  String get switchRequiresRestart => 'மாற்றம் பயன்பாட்டை மீண்டு தொடங்க தேவைப்படுகிறது';

  @override
  String get switchApiConfirmTitle => 'API சூழலை மாற்று';

  @override
  String switchApiConfirmBody(String environment) {
    return '$environment க்கு மாற்றலாமா? மாற்றங்கள் நடைமுறையில் வர பயன்பாட்டை மூடி மீண்டு திறக்க வேண்டும்.';
  }

  @override
  String get switchAndRestart => 'மாற்று';

  @override
  String get stagingDisclaimer =>
      'Staging சேதமாக இருக்கலாம், நிலையற்ற செயல்திறன் இருக்கலாம், மற்றும் தரவு இழப்பதற்குக் கூடியது. சோதனைக்கு மாத்திரமே பயன்படுத்தவும்.';

  @override
  String get apiEnvSavedRestartRequired => 'சேமிக்கப்பட்டது. பயன்பாட்டை மூடி மீண்டு திறந்து பயன்படுத்த.';

  @override
  String get shared => 'பகிரப்பட்ட';

  @override
  String get onlyYouCanSeeConversation => 'இந்த உரையாடலை நீங்கள் மாத்திரமே பார்க்கலாம்';

  @override
  String get anyoneWithLinkCanView => 'இணைப்பு உள்ளவர் அனைவரும் பார்க்கலாம்';

  @override
  String get tasksCleanTodayTitle => 'இன்றையப் பணிகளை தூய்மை செய்யலாமா?';

  @override
  String get tasksCleanTodayMessage => 'இது வெறும் deadlines ஐ மாத்திரமே நீக்கும்';

  @override
  String get tasksOverdue => 'தவணை தாண்டிய';

  @override
  String get phoneCallsWithOmi => 'Omi உடன் தொலைபேசி அழைப்புகள்';

  @override
  String get phoneCallsSubtitle => 'நேரலை மொழிபெயர்ப்பு மூலம் அழைப்புகளை செய்யவும்';

  @override
  String get phoneSetupStep1Title => 'உங்கள் தொலைபேசி எண்ணை சரிபார்க்கவும்';

  @override
  String get phoneSetupStep1Subtitle => 'இது உங்கள் என்பதை உறுதிசெய்ய நாங்கள் உங்களைக் கூப்பிடுவோம்';

  @override
  String get phoneSetupStep2Title => 'சரிபார்ப்பு குறியீட்டை உள்ளிடவும்';

  @override
  String get phoneSetupStep2Subtitle => 'அழைப்பின் போது நீங்கள் வகை செய்யும் ஒரு குறுகிய குறியீடு';

  @override
  String get phoneSetupStep3Title => 'உங்கள் தொடர்புகளை அழைக்க ஆரம்பிக்கவும்';

  @override
  String get phoneSetupStep3Subtitle => 'உள்ளமைக்கப்பட்ட நேரலை மொழிபெயர்ப்புடன்';

  @override
  String get phoneGetStarted => 'தொடங்க';

  @override
  String get callRecordingConsentDisclaimer => 'அழைப்பு பதிவுக்கு உங்கள் அதிகார வரம்பில் சம்மதம் தேவைப்படலாம்';

  @override
  String get enterYourNumber => 'உங்கள் எண்ணை உள்ளிடவும்';

  @override
  String get phoneNumberCallerIdHint => 'சரிபார்க்கப்பட்டால், இது உங்கள் caller ID ஆக மாறும்';

  @override
  String get phoneNumberHint => 'தொலைபேசி எண்';

  @override
  String get failedToStartVerification => 'சரிபார்ப்பு தொடங்க முடியவில்லை';

  @override
  String get phoneContinue => 'தொடர்';

  @override
  String get verifyYourNumber => 'உங்கள் எண்ணை சரிபார்க்கவும்';

  @override
  String get answerTheCallFrom => 'இலிருந்து அழைப்பைப் பதிலளிக்கவும்';

  @override
  String get onTheCallEnterThisCode => 'அழைப்பில், இந்த குறியீட்டை உள்ளிடவும்';

  @override
  String get followTheVoiceInstructions => 'ஆவாஸ் வழிமுறைகளை பின்பற்றவும்';

  @override
  String get statusCalling => 'அழைக்கிறது...';

  @override
  String get statusCallInProgress => 'அழைப்பு நடைபெற்றுக் கொண்டிருக்கிறது';

  @override
  String get statusVerifiedLabel => 'சரிபார்க்கப்பட்ட';

  @override
  String get statusCallMissed => 'அழைப்பு தவறிவிட்ட';

  @override
  String get statusTimedOut => 'நேர வரம்பு கடந்து';

  @override
  String get phoneTryAgain => 'மீண்டும் முயற்சி';

  @override
  String get phonePageTitle => 'தொலைபேசி';

  @override
  String get phoneContactsTab => 'தொடர்புகள்';

  @override
  String get phoneKeypadTab => 'விசைப்பலகை';

  @override
  String get grantContactsAccess => 'உங்கள் தொடர்புகளுக்கான அணுகல் வழங்கவும்';

  @override
  String get phoneAllow => 'அனுமதி';

  @override
  String get phoneSearchHint => 'தேடல்';

  @override
  String get phoneNoContactsFound => 'தொடர்புகள் கண்டறியப்படவில்லை';

  @override
  String get phoneEnterNumber => 'எண்ணை உள்ளிடவும்';

  @override
  String get failedToStartCall => 'அழைப்பு தொடங்க முடியவில்லை';

  @override
  String get callStateConnecting => 'இணைக்கிறது...';

  @override
  String get callStateRinging => 'அழைக்கிறது...';

  @override
  String get callStateEnded => 'அழைப்பு முடிந்தது';

  @override
  String get callStateFailed => 'அழைப்பு தோல்வி';

  @override
  String get transcriptPlaceholder => 'மொழிபெயர்ப்பு இங்கு தோன்றும்...';

  @override
  String get phoneUnmute => 'மீண்டும் ஒலி செய்';

  @override
  String get phoneMute => 'ஒலி நீக்கு';

  @override
  String get phoneSpeaker => 'ஸ்பீக்கர்';

  @override
  String get phoneEndCall => 'முடி';

  @override
  String get phoneCallSettingsTitle => 'தொலைபேசி அழைப்பு அமைப்பாடுகள்';

  @override
  String get showPhoneCallButtonTitle => 'ஃபோன் அழைப்பு பொத்தானை காட்டு';

  @override
  String get showPhoneCallButtonDesc => 'முகப்பு திரையில் ஃபோன் அழைப்பு பொத்தானை காட்டு';

  @override
  String get yourVerifiedNumbers => 'உங்கள் சரிபார்க்கப்பட்ட எண்கள்';

  @override
  String get verifiedNumbersDescription =>
      'நீங்கள் யாரையாவது அழைக்கும்போது, அவர்கள் தங்கள் தொலைபேசிகளில் இந்த எண்ணைக் காண்பார்கள்';

  @override
  String get noVerifiedNumbers => 'சரிபார்க்கப்பட்ட எண்கள் இல்லை';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber ஐ நீக்கலாமா?';
  }

  @override
  String get deletePhoneNumberWarning => 'அழைப்புகளைச் செய்ய நீங்கள் மீண்டும் சரிபார்க்க வேண்டியிருக்கும்';

  @override
  String get phoneDeleteButton => 'நீக்கு';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'சரிபார்க்கப்பட்ட ${minutes}m முன்';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'சரிபார்க்கப்பட்ட ${hours}h முன்';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'சரிபார்க்கப்பட்ட ${days}d முன்';
  }

  @override
  String verifiedOnDate(String date) {
    return 'சரிபார்க்கப்பட்ட $date இல்';
  }

  @override
  String get verifiedFallback => 'சரிபார்க்கப்பட்ட';

  @override
  String get callAlreadyInProgress => 'ஒரு அழைப்பு ஏற்கனவே நடைபெற்றுக் கொண்டிருக்கிறது';

  @override
  String get failedToGetCallToken => 'அழைப்பு token பெற முடியவில்லை. முதலில் உங்கள் தொலைபேசி எண்ணை சரிபார்க்கவும்.';

  @override
  String get failedToInitializeCallService => 'அழைப்பு சேவையை தொடங்க முடியவில்லை';

  @override
  String get speakerLabelYou => 'நீங்கள்';

  @override
  String get speakerLabelUnknown => 'தெரியாத';

  @override
  String get showDailyScoreOnHomepage => 'முகப்பில் தினசரி மதிப்பெண்ணைக் காட்டு';

  @override
  String get showTasksOnHomepage => 'முகப்பில் பணிகளை காட்டு';

  @override
  String get phoneCallsUnlimitedOnly => 'Omi மூலம் தொலைபேசி அழைப்புகள்';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Omi மூலம் அழைப்புகளை செய்து நேரலை மொழிபெயர்ப்பு, தானாக மொழிபெயர்ப்பு, மற்றும் மேலும் பெறவும். Unlimited திட்ட வாடிக்கையாளர்களுக்கு மாத்திரமே கிடைக்கும்.';

  @override
  String get phoneCallsUpsellFeature1 => 'ஒவ்வொரு அழைப்பின் நேரலை மொழிபெயர்ப்பு';

  @override
  String get phoneCallsUpsellFeature2 => 'தொலைபேசி மொழிபெயர்ப்பு மற்றும் செயல் உருபணுகள்';

  @override
  String get phoneCallsUpsellFeature3 => 'பெறுநர் உங்கள் வாஸ்தவ எண்ணைக் காணுவார், அநேக எண் அல்ல';

  @override
  String get phoneCallsUpsellFeature4 => 'உங்கள் அழைப்புகள் தனிப்பட்ட மற்றும் பாதுகாப்பாக இருக்கும்';

  @override
  String get phoneCallsUpgradeButton => 'Unlimited க்கு மேம்படுத்து';

  @override
  String get phoneCallsMaybeLater => 'பின்னர் மாயபே';

  @override
  String get deleteSynced => 'ஒத்திசைக்கப்பட்டவற்றை நீக்கு';

  @override
  String get deleteSyncedFiles => 'ஒத்திசைக்கப்பட்ட பதிவுகளை நீக்கு';

  @override
  String get deleteSyncedFilesMessage =>
      'இந்த பதிவுகள் ஏற்கனவே உங்கள் தொலைபேசிக்கு ஒத்திசைக்கப்பட்டுள்ளன. இதை செய்ய முடியாது.';

  @override
  String get syncedFilesDeleted => 'ஒத்திசைக்கப்பட்ட பதிவுகள் நீக்கப்பட்டுள்ளன';

  @override
  String get deletePending => 'நிலுவையில் உள்ளவற்றை நீக்கு';

  @override
  String get deletePendingFiles => 'நிலுவையில் உள்ள பதிவுகளை நீக்கு';

  @override
  String get deletePendingFilesWarning =>
      'இந்த பதிவுகள் உங்கள் தொலைபேசிக்கு ஒத்திசைக்கப்படவில்லை மற்றும் நிரந்தரமாக இழக்கப்படும். இதை செய்ய முடியாது.';

  @override
  String get pendingFilesDeleted => 'நிலுவையில் உள்ள பதிவுகள் நீக்கப்பட்டுள்ளன';

  @override
  String get deleteAllFiles => 'அனைத்துப் பதிவுகளையும் நீக்கு';

  @override
  String get deleteAll => 'அனைத்தையும் நீக்கு';

  @override
  String get deleteAllFilesWarning =>
      'இது ஒத்திசைக்கப்பட்ட மற்றும் நிலுவையில் உள்ள பதிவுகளை நீக்கும். நிலுவையில் உள்ள பதிவுகள் ஒத்திசைக்கப்படவில்லை மற்றும் நிரந்தரமாக இழக்கப்படும். இதை செய்ய முடியாது.';

  @override
  String get allFilesDeleted => 'அனைத்துப் பதிவுகளும் நீக்கப்பட்டுள்ளன';

  @override
  String nFiles(int count) {
    return '$count பதிவுகள்';
  }

  @override
  String get manageStorage => 'சேமிப்பகத்தை நிர்வகிக்கவும்';

  @override
  String get safelyBackedUp => 'உங்கள் தொலைபேசিக்கு பாதுகாப்பாக வெச்சிவைக்கப்பட்டுள்ளது';

  @override
  String get notYetSynced => 'இன்னும் உங்கள் தொலைபேசிக்கு ஒத்திசைக்கப்படவில்லை';

  @override
  String get clearAll => 'அனைத்தையும் நீக்கவும்';

  @override
  String get phoneKeypad => 'விசைப்பலகை';

  @override
  String get phoneHideKeypad => 'விசைப்பலகையை மறை';

  @override
  String get fairUsePolicy => 'நியாய பயன்பாடு';

  @override
  String get fairUseLoadError => 'நியாய பயன்பாட்டு நிலையை ஏற்ற முடியவில்லை. மீண்டும் முயற்சி செய்யவும்.';

  @override
  String get fairUseStatusNormal => 'உங்கள் பயன்பாடு சாதாரண வரம்பிற்குள் உள்ளது.';

  @override
  String get fairUseStageNormal => 'சாதாரணம்';

  @override
  String get fairUseStageWarning => 'எச்சரிக்கை';

  @override
  String get fairUseStageThrottle => 'நிയுக்தம்';

  @override
  String get fairUseStageRestrict => 'தடைசெய்யப்பட்ட';

  @override
  String get fairUseSpeechUsage => 'ஆவாஸ் பயன்பாடு';

  @override
  String get fairUseToday => 'இன்று';

  @override
  String get fairUse3Day => '3-நாள் Rolling';

  @override
  String get fairUseWeekly => 'வாரம் Rolling';

  @override
  String get fairUseAboutTitle => 'நியாய பயன்பாட்டு பற்றி';

  @override
  String get fairUseAboutBody =>
      'Omi தனிப்பட்ட உரையாடல்கள், கூட்டங்கள், மற்றும் நேரடி தொடர்பினை நோக்கமாகக் கொண்டுள்ளது. பயன்பாடு கண்டறியப்பட்ட உண்மையான ஆவாஸ் நேரத்தால் அளவிடப்படுகிறது, இணைப்பு நேரம் அல்ல. பயன்பாடு தனிப்பட்ட உள்ளடக்கம் அல்ல வழக்கமான வடிவங்கலை கணிசமாக கடக்க நிலைமாறினால், சரிசெய்தல் பயன்படுத்தப்படலாம்.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef நகლாக்கப்பட்டது';
  }

  @override
  String get fairUseDailyTranscription => 'தினசரி மொழிபெயர்ப்பு';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'தினசரி மொழிபெயர்ப்பு வரம்பு அடையப்பட்டுள்ளது';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'மீட்டமை $time';
  }

  @override
  String get transcriptionPaused => 'பதிவு, மீண்டு இணையப்படுகிறது';

  @override
  String get transcriptionPausedReconnecting =>
      'இன்னும் பதிவு செய்யப்படுகிறது — மொழிபெயர்ப்புக்கு மீண்டு இணையப்படுகிறது...';

  @override
  String fairUseBannerStatus(String status) {
    return 'நியாய பயன்பாடு: $status';
  }

  @override
  String get improveConnectionTitle => 'இணைப்பை மேம்படுத்து';

  @override
  String get improveConnectionContent =>
      'Omi உங்கள் சாதனத்துடன் இணைக்கப்பட்டுள்ளதாக இருப்பதற்கான முறையை நாங்கள் மேம்படுத்தியுள்ளோம். இதைத் தூண்டப் சாதனம் தகவல் பக்கத்திற்குச் செல்லவும், \"சாதனத்தை விலக்கவும்\" வெற்றியடையவும், பின்னர் உங்கள் சாதனத்தை மீண்டு ஜோடியாக்கவும்.';

  @override
  String get improveConnectionAction => 'புரிந்து கொண்டேன்';

  @override
  String clockSkewWarning(int minutes) {
    return 'உங்கள் சாதனம் கடிகாரம் தவறாகப் பதிவு உள்ளது ~$minutes நிமிஷம். உங்கள் தேதி & நேர அமைப்பாடுகளை சரிசெய்யவும்.';
  }

  @override
  String get omisStorage => 'Omi இன் சேமிப்பகம்';

  @override
  String get phoneStorage => 'தொலைபேசி சேமிப்பகம்';

  @override
  String get cloudStorage => 'Cloud சேமிப்பகம்';

  @override
  String get howSyncingWorks => 'ஒத்திசைப்பு எவ்வாறு செயல்படுகிறது';

  @override
  String get noSyncedRecordings => 'இன்னும் ஒத்திசைக்கப்பட்ட பதிவுகள் இல்லை';

  @override
  String get recordingsSyncAutomatically => 'பதிவுகள் தானாகவே ஒத்திசைக்கப்படுகின்றன — செயல் தேவையில்லை.';

  @override
  String get filesDownloadedUploadedNextTime => 'ஏற்கனவே பதிவிறக்கிய கோப்புகள் அடுத்த முறை பதிவேற்றப்படும்.';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 's',
      one: '',
    );
    return '$count conversation$_temp0 created';
  }

  @override
  String get tapToView => 'பார்க்க தட்டவும்';

  @override
  String get syncFailed => 'ஒத்திசைப்பு தோல்வி';

  @override
  String get keepSyncing => 'ஒத்திசைப்பைத் தொடரவும்';

  @override
  String get cancelSyncQuestion => 'ஒத்திசைப்பை ரத்து செய்யலாமா?';

  @override
  String get omisStorageDesc =>
      'உங்கள் Omi உங்கள் தொலைபேசிக்குத் தொடர்புபடாமல் இருக்கும்போது, அது ஆடியோவை அதன் உள்ளமைக்கப்பட்ட நினைவகத்தில் உள்ளூரில் சேமிக்கிறது। நீங்கள் ஒருபோதும் ஒரு பதிவை இழக்கமாட்டீர்கள்.';

  @override
  String get phoneStorageDesc =>
      'Omi மீண்டு இணையப்படும்போது, பதிவுகள் தானாகவே உங்கள் தொலைபேசிக்கு அப்ளோட் செய்ய முன் தற்காலிக நிலையீடாக மாற்றப்படுகிறது.';

  @override
  String get cloudStorageDesc =>
      'பதிவேற்றப்பட்டபின், உங்கள் பதிவுகள் செயல்படுத்தப்பட்டு மொழிபெயர்க்கப்படுகிறது. உரையாடல்கள் ஒரு நிமிஷத்தில் கிடைப்பாயிற்று.';

  @override
  String get tipKeepPhoneNearby => 'வேகமான ஒத்திசைப்புக்கு உங்கள் தொலைபேசியை அருகாமையில் வைக்கவும்';

  @override
  String get tipStableInternet => 'நிலையான இணையம் cloud பதிவேற்றத்தை வேகமாக்குகிறது';

  @override
  String get tipAutoSync => 'பதிவுகள் தானாகவே ஒத்திசைக்கப்படுகின்றன';

  @override
  String get storageSection => 'சேமிப்பகம்';

  @override
  String get permissions => 'அனுமதிகள்';

  @override
  String get permissionEnabled => 'இயக்கப்பட்ட';

  @override
  String get permissionEnable => 'இயக்கவும்';

  @override
  String get permissionsPageDescription =>
      'இந்த அனுமதிகள் Omi எவ்வாறு செயல்படுகிறது என்பதற்கு மூலமுள்ளவை. அவை அறிவிப்புகள், தொடர்பிலான அভিজ্ঞதங்கள், மற்றும் ஆடியோ பிடிப்பு போன்ற முக்கிய வசதিகளை இயக்குகிறது.';

  @override
  String get permissionsRequiredDescription =>
      'Omi சரிந்து செயல்பாட்ட சில அனுமதிகள் தேவைப்படுகிறது. தொடர செய்ய தயவுசெய்து அவற்றை வழங்கவும்.';

  @override
  String get permissionsSetupTitle => 'சிறந்த அভிজ்ঞதம் பெறவும்';

  @override
  String get permissionsSetupDescription => 'Omi தன் மாயாவிற்கு பணிய சில அனுமதிகளை இயக்கவும்.';

  @override
  String get permissionsChangeAnytime => 'நீங்கள் இந்த அனுமதிகளை எந்நேரம் அமைப்பாடுகளில் மாற்றலாம் > அனுமதிகள்';

  @override
  String get location => 'தொடர்பிலை';

  @override
  String get microphone => 'மைக்ரோப்ஹோன்';

  @override
  String get whyAreYouCanceling => 'நீங்கள் ஏன் ரத்து செய்கிறீர்கள்?';

  @override
  String get cancelReasonSubtitle => 'நீங்கள் ஏன் கிளம்ப முயற்சிக்கிறீர்கள் என்பதைக் கூற முடியுமா?';

  @override
  String get cancelReasonTooExpensive => 'மிக விலை';

  @override
  String get cancelReasonNotUsing => 'போதுமாக பயன்படுத்தாதல்';

  @override
  String get cancelReasonMissingFeatures => 'விடுபட்ட வசதிகள்';

  @override
  String get cancelReasonAudioQuality => 'ஆடியோ/மொழிபெயர்ப்பு தரம்';

  @override
  String get cancelReasonBatteryDrain => 'பேட்டரி draining கவலைகள்';

  @override
  String get cancelReasonFoundAlternative => 'மாற்றுத் தேடிய';

  @override
  String get cancelReasonOther => 'பிற';

  @override
  String get tellUsMore => 'விரித்துக் கூறவும் (விருப்பத்தின் பேரில்)';

  @override
  String get cancelReasonDetailHint => 'நாங்கள் மற்றும் கருத்து பாராட்டுகிறோம்...';

  @override
  String get justAMoment => 'கொஞ்சம் நேரம் தயவுசெய்து';

  @override
  String get cancelConsequencesSubtitle =>
      'ரத்து செய்யுவதற்கு பதிலாக உங்கள் பிற தெரிவுகளை ஆய்வு செய்ய நாங்கள் உயர்ந்தமாக பரிந்துரைக்கிறோம்.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'உங்கள் திட்டம் $date வரை செயல்பாட்டில் இருக்கும். அதன் பின், நீங்கள் محدود வசதிகளைக் கொண்ட இலவச பதிப்புக்கு மாற்றப்படுவீர்கள்.';
  }

  @override
  String get ifYouCancel => 'நீங்கள் ரத்து செய்யினால்:';

  @override
  String get cancelConsequenceNoAccess =>
      'உங்கள் பிள் கொணை முடிவிற்கு வரும் வரை unlimited அணுகலை நீங்கள் இனி பெறமாட்டீர்கள்.';

  @override
  String get cancelConsequenceBattery => '7 மடங்கு அधिक பேட்டரி பயன்பாடு (சாதன செயல்பாட்டு)';

  @override
  String get cancelConsequenceQuality => '30% குறைந்த மொழிபெயர்ப்பு தரம் (சாதன மாதிரிகள்)';

  @override
  String get cancelConsequenceDelay => '5-7 விநாடி செயல்பாட்டு தாமதம் (சாதன மாதிரிகள்)';

  @override
  String get cancelConsequenceSpeakers => 'ஆவாஸ் பேசுபவர்களை அடையாளம் செய்ய முடியாது.';

  @override
  String get confirmAndCancel => 'உறுதிப்படுத்தவும் & ரத்து செய்யவும்';

  @override
  String get cancelConsequencePhoneCalls => 'நேரலை தொலைபேசி அழைப்பு மொழிபெயர்ப்பு இல்லை';

  @override
  String get feedbackTitleTooExpensive => 'உங்களுக்கு எந்த விலை வேலை செய்யும்?';

  @override
  String get feedbackTitleMissingFeatures => 'நீங்கள் எந்த வசதிகள் விடுபட்டுள்ளீர்கள்?';

  @override
  String get feedbackTitleAudioQuality => 'நீங்கள் எந்த சிக்கல்களை அனுபவித்தீர்கள்?';

  @override
  String get feedbackTitleBatteryDrain => 'பேட்டரி சிக்கல்களைப் பற்றி மாக் சொல்லவும்';

  @override
  String get feedbackTitleFoundAlternative => 'நீங்கள் எதற்கு மாற்றிக் கொண்டிருக்கிறீர்கள்?';

  @override
  String get feedbackTitleNotUsing => 'Omi ஐ நீங்கள் அधिक பயன்படுத்த விரும்பினால் என்ன?';

  @override
  String get feedbackSubtitleTooExpensive => 'உங்கள் கருத்து சரியான சமநிலை கண்டுபிடிக்க உதவுகிறது.';

  @override
  String get feedbackSubtitleMissingFeatures =>
      'நாங்கள் எப்போதும் கட்டுவதை செய்கிறோம் — இது முன்னுரிமை கொடுக்க உதவுகிறது.';

  @override
  String get feedbackSubtitleAudioQuality => 'எவ்வாறு தவறு விட்டிருந்தவை என்பதை புரிந்து கொள்ள நாங்கள் விரும்புகிறோம்.';

  @override
  String get feedbackSubtitleBatteryDrain => 'இது எங்கள் hardware குழுவை மேம்படுத்த உதவுகிறது.';

  @override
  String get feedbackSubtitleFoundAlternative =>
      'உங்கள் கண்ணை எவ்வாறு நிறுத்தினவை என்பதை நாங்கள் கற்றுக் கொள்ள விரும்புகிறோம்.';

  @override
  String get feedbackSubtitleNotUsing => 'Omi ஐ நீங்கள் மேலும் பயனுள்ளதாக்க நாங்கள் விரும்புகிறோம்.';

  @override
  String get deviceDiagnostics => 'சாதன கண்டறியக்கூடியம்';

  @override
  String get signalStrength => 'Signal சக்தி';

  @override
  String get connectionUptime => 'Uptime';

  @override
  String get reconnections => 'மீண்டு இணைப்புகள்';

  @override
  String get disconnectHistory => 'விலக்கும் வரலாற்று';

  @override
  String get noDisconnectsRecorded => 'விலக்குவதை பிற் பதிவு செய்யப்படவில்லை';

  @override
  String get diagnostics => 'கண்டறியக்கூடியம்';

  @override
  String get waitingForData => 'தரவுக்குக் காத்திருக்கிறது...';

  @override
  String get liveRssiOverTime => 'நேரலை RSSI நேரத்தின் மீது';

  @override
  String get noRssiDataYet => 'இன்னும் RSSI தரவு இல்லை';

  @override
  String get collectingData => 'தரவு சேகரிக்கப்படுகிறது...';

  @override
  String get cleanDisconnect => 'சுத்த விலக்குதல்';

  @override
  String get connectionTimeout => 'இணைப்பு நேர முடிய';

  @override
  String get remoteDeviceTerminated => 'தொலை சாதனம் முடிவாக்கப்பட்ட';

  @override
  String get pairedToAnotherPhone => 'மற்றொரு தொலைபேசிக்கு ஜோடியாக்கப்பட்ட';

  @override
  String get linkKeyMismatch => 'Link விசை பொருத்தம் இல்லாதல்';

  @override
  String get connectionFailed => 'இணைப்பு தோல்வி';

  @override
  String get appClosed => 'பயன்பாடு மூடப்பட்ட';

  @override
  String get manualDisconnect => 'Manual விலக்குதல்';

  @override
  String lastNEvents(int count) {
    return 'கடைசி $count நிகழ்வுகள்';
  }

  @override
  String get signal => 'Signal';

  @override
  String get battery => 'பேட்டரி';

  @override
  String get excellent => 'சிறந்த';

  @override
  String get good => 'நல்ல';

  @override
  String get fair => 'நியாய';

  @override
  String get weak => 'பலவீன';

  @override
  String gattError(String code) {
    return 'GATT பிழை ($code)';
  }

  @override
  String get batteryHistory => 'பேட்டரி';

  @override
  String get noBatteryDataYet => 'இன்னும் பேட்டரி தரவு இல்லை';

  @override
  String get day => 'நாள்';

  @override
  String get week => 'வாரம்';

  @override
  String get rollbackToStableFirmware => 'நிலையான Firmware க்கு மீண்டு திரும்பு';

  @override
  String get rollbackConfirmTitle => 'Firmware ஐ மீண்டு திரும்பலாமா?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'இது உங்கள் தற்போதைய firmware ஐ கடைசி நிலையான பதிப்பு ($version) உடன் மாற்றும். உங்கள் சாதனம் மேம்படுத்தப்பட்ட பின் மீண்டு தொடங்கும்.';
  }

  @override
  String get stableFirmware => 'நிலையான Firmware';

  @override
  String get fetchingStableFirmware => 'கடைசி நிலையான firmware பெறப்படுகிறது...';

  @override
  String get noStableFirmwareFound => 'உங்கள் சாதனத்துக்கு நிலையான firmware பதிப்பு கண்டறியப்படவில்லை.';

  @override
  String get installStableFirmware => 'நிலையான Firmware நிறுவு';

  @override
  String get alreadyOnStableFirmware => 'நீங்கள் ஏற்கனவே கடைசி நிலையான பதிப்பில் உள்ளீர்கள்.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration ஆடியோ உள்ளூரில் சேமிக்கப்பட்ட';
  }

  @override
  String get willSyncAutomatically => 'தானாகவே ஒத்திசைக்கப்படும்';

  @override
  String get enableLocationTitle => 'தொடர்பிலையை இயக்கவும்';

  @override
  String get enableLocationDescription => 'Bluetooth சாதனங்களை கண்டறிய தொடர்பிலை அனுமதி தேவைப்படுகிறது.';

  @override
  String get voiceRecordingFound => 'பதிவு கண்டறியப்பட்ட';

  @override
  String get transcriptionConnecting => 'மொழிபெயர்ப்பு இணைக்கப்படுகிறது...';

  @override
  String get transcriptionReconnecting => 'மொழிபெயர்ப்பு மீண்டு இணைக்கப்படுகிறது...';

  @override
  String get transcriptionUnavailable => 'மொழிபெயர்ப்பு கிடைக்கக்கூடியது அல்ல';

  @override
  String get audioOutput => 'ஆடியோ வெளியீடு';

  @override
  String get firmwareWarningTitle => 'முக்கியம்: புதுப்பிக்கும் முன் படிக்கவும்';

  @override
  String get firmwareFormatWarning =>
      'இந்த firmware SD கார்டை வடிவமைக்கும். மேம்படுத்துவதற்கு முன் அனைத்து ஆஃப்லைன் தரவும் ஒத்திசைக்கப்பட்டிருப்பதை உறுதிசெய்யவும்.\n\nஇந்த பதிப்பை நிறுவிய பிறகு சிவப்பு விளக்கு ஒளிர்ந்தால் கவலைப்பட வேண்டாம். சாதனத்தை செயலியுடன் இணைக்கவும், அது நீல நிறமாக மாற வேண்டும். சிவப்பு விளக்கு என்பது சாதனத்தின் கடிகாரம் இன்னும் ஒத்திசைக்கப்படவில்லை என்று அர்த்தம்.';

  @override
  String get continueAnyway => 'தொடரவும்';

  @override
  String get tasksClearCompleted => 'முடிந்தவற்றை அழி';

  @override
  String get tasksSelectAll => 'அனைத்தையும் தேர்ந்தெடு';

  @override
  String tasksDeleteSelected(int count) {
    return '$count பணி(களை) நீக்கு';
  }

  @override
  String get tasksMarkComplete => 'முடிந்தது என குறிக்கப்பட்டது';

  @override
  String get appleHealthManageNote =>
      'Omi, Apple இன் HealthKit கட்டமைப்பின் மூலம் Apple Health-ஐ அணுகுகிறது. iOS அமைப்புகளில் எந்த நேரத்திலும் அணுகலை ரத்து செய்யலாம்.';

  @override
  String get appleHealthConnectCta => 'Apple Health-உடன் இணை';

  @override
  String get appleHealthDisconnectCta => 'Apple Health-ஐ துண்டி';

  @override
  String get appleHealthConnectedBadge => 'இணைக்கப்பட்டது';

  @override
  String get appleHealthFeatureChatTitle => 'உங்கள் ஆரோக்கியம் பற்றி அரட்டை';

  @override
  String get appleHealthFeatureChatDesc =>
      'Omi இடம் உங்கள் படிகள், தூக்கம், இதயத் துடிப்பு, உடற்பயிற்சிகள் பற்றி கேளுங்கள்.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'படிக்க மட்டுமே அணுகல்';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi ஒருபோதும் Apple Health-இல் எழுதாது அல்லது உங்கள் தரவை மாற்றாது.';

  @override
  String get appleHealthFeatureSecureTitle => 'பாதுகாப்பான ஒத்திசைவு';

  @override
  String get appleHealthFeatureSecureDesc =>
      'உங்கள் Apple Health தரவு உங்கள் Omi கணக்குடன் தனிப்பட்ட முறையில் ஒத்திசைக்கப்படுகிறது.';

  @override
  String get appleHealthDeniedTitle => 'Apple Health அணுகல் மறுக்கப்பட்டது';

  @override
  String get appleHealthDeniedBody =>
      'உங்கள் Apple Health தரவைப் படிக்க Omi க்கு அனுமதி இல்லை. iOS அமைப்புகள் → தனியுரிமை & பாதுகாப்பு → Health → Omi இல் இதை இயக்கவும்.';

  @override
  String get deleteFlowReasonTitle => 'நீங்கள் ஏன் வெளியேறுகிறீர்கள்?';

  @override
  String get deleteFlowReasonSubtitle => 'உங்கள் கருத்து அனைவருக்கும் Omi-ஐ சிறப்பாக்க எங்களுக்கு உதவுகிறது.';

  @override
  String get deleteReasonPrivacy => 'தனியுரிமை கவலைகள்';

  @override
  String get deleteReasonNotUsing => 'போதுமான அளவு பயன்படுத்தவில்லை';

  @override
  String get deleteReasonMissingFeatures => 'எனக்குத் தேவையான அம்சங்கள் இல்லை';

  @override
  String get deleteReasonTechnicalIssues => 'பல தொழில்நுட்பச் சிக்கல்கள்';

  @override
  String get deleteReasonFoundAlternative => 'வேறு ஒன்றைப் பயன்படுத்துகிறேன்';

  @override
  String get deleteReasonTakingBreak => 'சற்று இடைவேளை எடுக்கிறேன்';

  @override
  String get deleteReasonOther => 'மற்றவை';

  @override
  String get deleteFlowFeedbackTitle => 'மேலும் சொல்லுங்கள்';

  @override
  String get deleteFlowFeedbackSubtitle => 'Omi உங்களுக்கு எவ்வாறு பயனுள்ளதாக இருந்திருக்கும்?';

  @override
  String get deleteFlowFeedbackHint =>
      'விருப்பத்தேர்வு — உங்கள் எண்ணங்கள் சிறந்த தயாரிப்பை உருவாக்க எங்களுக்கு உதவுகின்றன.';

  @override
  String get deleteFlowConfirmTitle => 'இது நிரந்தரமானது';

  @override
  String get deleteFlowConfirmSubtitle => 'கணக்கை நீக்கியதும், அதை மீட்க வழி இல்லை.';

  @override
  String get deleteConsequenceSubscription => 'செயலில் உள்ள சந்தா ரத்து செய்யப்படும்.';

  @override
  String get deleteConsequenceNoRecovery => 'உங்கள் கணக்கை மீட்டெடுக்க முடியாது — ஆதரவுக் குழுவாலும் முடியாது.';

  @override
  String get deleteTypeToConfirm => 'உறுதிப்படுத்த DELETE என தட்டச்சு செய்யவும்';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'கணக்கை நிரந்தரமாக நீக்கு';

  @override
  String get keepMyAccount => 'என் கணக்கை வைத்திரு';

  @override
  String get deleteAccountFailed => 'உங்கள் கணக்கை நீக்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்.';

  @override
  String get planUpdate => 'திட்ட புதுப்பிப்பு';

  @override
  String get planDeprecationMessage =>
      'உங்கள் Unlimited திட்டம் நிறுத்தப்படுகிறது. Operator திட்டத்திற்கு மாறுங்கள் — அதே சிறந்த அம்சங்கள் \$49/மாதம். உங்கள் தற்போதைய திட்டம் இதற்கிடையில் தொடர்ந்து செயல்படும்.';

  @override
  String get upgradeYourPlan => 'உங்கள் திட்டத்தை மேம்படுத்தவும்';

  @override
  String get youAreOnAPaidPlan => 'நீங்கள் கட்டண திட்டத்தில் உள்ளீர்கள்.';

  @override
  String get chatTitle => 'அரட்டை';

  @override
  String get chatMessages => 'செய்திகள்';

  @override
  String get unlimitedChatThisMonth => 'இந்த மாதம் வரம்பற்ற அரட்டை செய்திகள்';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used / $limit கணக்கீடு பட்ஜெட் பயன்படுத்தப்பட்டது';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return 'இந்த மாதம் $used / $limit செய்திகள் பயன்படுத்தப்பட்டன';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit பயன்படுத்தப்பட்டது';
  }

  @override
  String get chatLimitReachedUpgrade => 'அரட்டை வரம்பு எட்டியது. மேலும் செய்திகளுக்கு மேம்படுத்தவும்.';

  @override
  String get chatLimitReachedTitle => 'அரட்டை வரம்பு எட்டியது';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return '$plan திட்டத்தில் $limitDisplay இல் $used பயன்படுத்தியுள்ளீர்கள்.';
  }

  @override
  String resetsInDays(int count) {
    return '$count நாட்களில் மீட்டமைக்கப்படும்';
  }

  @override
  String resetsInHours(int count) {
    return '$count மணி நேரத்தில் மீட்டமைக்கப்படும்';
  }

  @override
  String get resetsSoon => 'விரைவில் மீட்டமைக்கப்படும்';

  @override
  String get upgradePlan => 'திட்டத்தை மேம்படுத்து';

  @override
  String get billingMonthly => 'மாதாந்திர';

  @override
  String get billingYearly => 'ஆண்டு';

  @override
  String get savePercent => '~17% சேமிக்கவும்';

  @override
  String get popular => 'பிரபலம்';

  @override
  String get currentPlan => 'தற்போதைய';

  @override
  String neoSubtitle(int count) {
    return 'மாதத்திற்கு $count கேள்விகள்';
  }

  @override
  String operatorSubtitle(int count) {
    return 'மாதத்திற்கு $count கேள்விகள்';
  }

  @override
  String get architectSubtitle => 'பவர் AI — ஆயிரக்கணக்கான உரையாடல்கள் + ஏஜென்ட் ஆட்டோமேஷன்';

  @override
  String chatUsageCost(String used, String limit) {
    return 'அரட்டை: \$$used / \$$limit இந்த மாதம் பயன்படுத்தப்பட்டது';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'அரட்டை: \$$used இந்த மாதம் பயன்படுத்தப்பட்டது';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'அரட்டை: $used / $limit செய்திகள் இந்த மாதம்';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'அரட்டை: $used செய்திகள் இந்த மாதம்';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'நீங்கள் உங்கள் மாதாந்திர வரம்பை அடைந்துவிட்டீர்கள். கட்டுப்பாடுகள் இல்லாமல் Omi உடன் அரட்டையைத் தொடர மேம்படுத்தவும்.';

  @override
  String get voiceResponseAudio => 'Omi பதிலை சத்தமாக படிக்கவும்';

  @override
  String get voiceResponseMode => 'குரல் பதில்';

  @override
  String get voiceResponseModeTitle => 'பதில்களை எப்போது பேசுவது';

  @override
  String get voiceResponseOff => 'முடக்கம்';

  @override
  String get voiceResponseHeadphonesOnly => 'ஹெட்ஃபோன் மட்டும்';

  @override
  String get voiceResponseAlways => 'எப்போதும்';

  @override
  String get agreeAndContinue => 'ஒப்புக்கொள் & தொடரவும்';

  @override
  String get startVoiceRecording => 'குரல் பதிவைத் தொடங்கு';

  @override
  String get startCallRecording => 'அழைப்பு பதிவைத் தொடங்கு';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'குரல் பயன்முறை';

  @override
  String get quickActionAskOmi => 'Omi ஐ எதையும் கேளுங்கள்';

  @override
  String get record => 'பதிவு';

  @override
  String get stop => 'நிறுத்து';

  @override
  String get recordWithPhoneMic => 'போன் மைக்கில் பதிவு செய்யவும்';

  @override
  String get recordWithPhoneMicSubtitle => 'உங்களைச் சுற்றியுள்ள ஒலியைப் பதிவு செய்யவும்';

  @override
  String get phoneCall => 'தொலைபேசி அழைப்பு';

  @override
  String get phoneCallSubtitle => 'நேரடி படியெடுத்தலுடன் அழைப்பைப் பதிவு செய்யவும்';

  @override
  String get searchActionItems => 'செயல் உருப்படிகளைத் தேடு';

  @override
  String get selectActionItems => 'பலவற்றைத் தேர்ந்தெடு';

  @override
  String chooseExportDestination(int count) {
    return '$count உருப்படி(களை) ஏற்றுமதி செய்…';
  }

  @override
  String get bulkExportInProgress => 'ஏற்றுமதி செய்கிறது…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$count ஐ $platform க்கு ஏற்றுமதி செய்யப்பட்டது';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$total இல் $success ஐ $platform க்கு ஏற்றுமதி செய்யப்பட்டது';
  }

  @override
  String get showCompletedTasks => 'முடிந்தவற்றைக் காட்டு';

  @override
  String get hideCompletedTasks => 'முடிந்தவற்றை மறை';

  @override
  String get selectAllTasksMenu => 'அனைத்தையும் தேர்ந்தெடு';

  @override
  String get connectTaskAppToExport => 'ஏற்றுமதி செய்ய அமைப்புகளில் ஒரு பணி செயலியை இணைக்கவும்';

  @override
  String get connectAction => 'இணைக்கவும்';

  @override
  String get deselectAllTasksMenu => 'அனைத்தையும் தேர்வு நீக்கு';
}
