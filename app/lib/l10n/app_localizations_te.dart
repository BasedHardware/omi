// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Telugu (`te`).
class AppLocalizationsTe extends AppLocalizations {
  AppLocalizationsTe([String locale = 'te']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'సంభాషణ';

  @override
  String get transcriptTab => 'ట్రాన్‌స్క్రిప్ట్';

  @override
  String get actionItemsTab => 'చేసిన పనులు';

  @override
  String get deleteConversationTitle => 'సంభాషణను తొలగించాలా?';

  @override
  String get deleteConversationMessage =>
      'ఇది సంబంధిత జ్ఞాపకాలు, పనులు మరియు ఆడియో ఫైల్‌లను కూడా తొలగిస్తుంది. ఈ చర్య రద్దు చేయబడదు.';

  @override
  String get confirm => 'ఖచ్చితం చేయండి';

  @override
  String get cancel => 'రద్దు చేయండి';

  @override
  String get ok => 'సరే';

  @override
  String get delete => 'తొలగించు';

  @override
  String get add => 'జోడించు';

  @override
  String get update => 'నవీకరించు';

  @override
  String get save => 'సేవ్ చేయండి';

  @override
  String get edit => 'సవరించు';

  @override
  String get close => 'మూయు';

  @override
  String get clear => 'పరిష్కరించు';

  @override
  String get copyTranscript => 'ట్రాన్‌స్క్రిప్ట్‌ను కాపీ చేయండి';

  @override
  String get copySummary => 'సారాంశాన్ని కాపీ చేయండి';

  @override
  String get testPrompt => 'ప్రాంప్ట్‌ను పరీక్షించండి';

  @override
  String get reprocessConversation => 'సంభాషణను తిరిగి ప్రక్రియ చేయండి';

  @override
  String get deleteConversation => 'సంభాషణను తొలగించు';

  @override
  String get contentCopied => 'కంటెంట్ క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get failedToUpdateStarred => 'స్టార్ చేసిన స్థితిని నవీకరించడంలో విఫలమైంది.';

  @override
  String get conversationUrlNotShared => 'సంభాషణ URL భాగస్వామ్యం చేయబడలేదు.';

  @override
  String get errorProcessingConversation => 'సంభాషణను ప్రక్రియ చేసేటప్పుడు ত్రుटి. దయచేసి తరువాత మళ్లీ ప్రయత్నించండి.';

  @override
  String get noInternetConnection => 'ఇంటర్నెట్ కనెక్షన్ లేదు';

  @override
  String get unableToDeleteConversation => 'సంభాషణను తొలగించలేకపోయాము';

  @override
  String get somethingWentWrong => 'ఏదో తప్పు జరిగింది! దయచేసి తరువాత మళ్లీ ప్రయత్నించండి.';

  @override
  String get copyErrorMessage => 'ఎర్రర్ సందేశాన్ని కాపీ చేయండి';

  @override
  String get errorCopied => 'ఎర్రర్ సందేశం క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get remaining => 'మిగిలినవి';

  @override
  String get loading => 'లోడ్ చేస్తోంది...';

  @override
  String get loadingDuration => 'సమయ వ్యవధిని లోడ్ చేస్తోంది...';

  @override
  String secondsCount(int count) {
    return '$count సెకన్లు';
  }

  @override
  String get people => 'ప్రజలు';

  @override
  String get addNewPerson => 'కొత్త వ్యక్తిని జోడించండి';

  @override
  String get editPerson => 'వ్యక్తిని సవరించండి';

  @override
  String get createPersonHint =>
      'కొత్త వ్యక్తిని సృష్టించండి మరియు వారి ఉపన్యాసాన్ని గుర్తించడానికి Omiని శిక్షణ ఇవ్వండి!';

  @override
  String get speechProfile => 'ఉపన్యాస ప్రొఫైల్';

  @override
  String sampleNumber(int number) {
    return 'నమూనా $number';
  }

  @override
  String get settings => 'సెట్టింగ్‌లు';

  @override
  String get language => 'భాష';

  @override
  String get selectLanguage => 'భాషను ఎంచుకోండి';

  @override
  String get deleting => 'తొలగిస్తోంది...';

  @override
  String get pleaseCompleteAuthentication =>
      'దయచేసి మీ బ్రౌజర్‌లో ప్రామాణీకరణను పూర్తి చేయండి. పూర్తి చేసిన తర్వాత, అనువర్తనానికి తిరిగి వెళ్లండి.';

  @override
  String get failedToStartAuthentication => 'ప్రామాణీకరణను ప్రారంభించడంలో విఫలమైంది';

  @override
  String get importStarted => 'దిగుమతి ప్రారంభమైంది! ఇది పూర్తిగా ఉన్నప్పుడు మీకు సం告్ఞ చేయబడుతుంది.';

  @override
  String get failedToStartImport => 'దిగుమతిని ప్రారంభించడంలో విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get couldNotAccessFile => 'ఎంచుకున్న ఫైల్‌ను యాక్సెస్ చేయలేకపోయాము';

  @override
  String get askOmi => 'Omiని అడగండి';

  @override
  String get done => 'పూర్తి';

  @override
  String get disconnected => 'డిస్‌కనెక్ట్ చేయబడింది';

  @override
  String get searching => 'శోధిస్తోంది...';

  @override
  String get connectDevice => 'డివైస్‌ను కనెక్ట్ చేయండి';

  @override
  String get monthlyLimitReached => 'మీరు మీ నెలసరి సীమకు చేరుకున్నారు.';

  @override
  String get checkUsage => 'ఉపయోగాన్ని చెక్ చేయండి';

  @override
  String get syncingRecordings => 'రికార్డింగ్‌లను సమకాలీకరిస్తోంది';

  @override
  String get recordingsToSync => 'సమకాలీకరించాల్సిన రికార్డింగ్‌లు';

  @override
  String get allCaughtUp => 'అన్నీ పూర్తి';

  @override
  String get sync => 'సమకాలీకరణ';

  @override
  String get pendantUpToDate => 'పెండెంట్ తాజా నవీకరణకు సిద్ధం';

  @override
  String get allRecordingsSynced => 'అన్ని రికార్డింగ్‌లు సమకాలీకరించబడ్డాయి';

  @override
  String get syncingInProgress => 'సమకాలీకరణ ప్రగతిలో ఉంది';

  @override
  String get readyToSync => 'సమకాలీకరణకు సిద్ధం';

  @override
  String get tapSyncToStart => 'ప్రారంభించడానికి సమకాలీకరణను నొక్కండి';

  @override
  String get pendantNotConnected => 'పెండెంట్ కనెక్ట్ చేయబడలేదు. సమకాలీకరణ చేయడానికి కనెక్ట్ చేయండి.';

  @override
  String get everythingSynced => 'ప్రతిదీ ఇప్పటికే సమకాలీకరించబడ్డాయి.';

  @override
  String get recordingsNotSynced => 'మీకు ఇంకా సమకాలీకరించని రికార్డింగ్‌లు ఉన్నాయి.';

  @override
  String get syncingBackground => 'మేము మీ రికార్డింగ్‌లను నేపథ్యంలో సమకాలీకరించ్ఖాల్చాము.';

  @override
  String get noConversationsYet => 'ఇంకా సంభాషణలు లేవు';

  @override
  String get noStarredConversations => 'స్టార్ చేసిన సంభాషణలు లేవు';

  @override
  String get starConversationHint => 'సంభాషణను స్టార్ చేయడానికి, దాన్ని తెరిచి శీర్షికలో స్టార్ చిహ్నాన్ని నొక్కండి.';

  @override
  String get searchConversations => 'సంభాషణలను శోధించండి...';

  @override
  String selectedCount(int count, Object s) {
    return '$count ఎంచుకోబడింది';
  }

  @override
  String get merge => 'విలీనం చేయండి';

  @override
  String get mergeConversations => 'సంభాషణలను విలీనం చేయండి';

  @override
  String mergeConversationsMessage(int count) {
    return 'ఇది $count సంభాషణలను ఒకటిగా కలిపిస్తుంది. అన్ని కంటెంట్ విలీనం చేయబడుతుంది మరియు పునర్నిర్మించబడుతుంది.';
  }

  @override
  String get mergingInBackground => 'నేపథ్యంలో విలీనం చేస్తోంది. ఇది ఒక క్షణం పట్టవచ్చు.';

  @override
  String get failedToStartMerge => 'విలీనాన్ని ప్రారంభించడంలో విఫలమైంది';

  @override
  String get askAnything => 'ఏదైనా అడగండి';

  @override
  String get noMessagesYet => 'ఇంకా సందేశాలు లేవు!\nసంభాషణను ప్రారంభించడానికి ఎందుకు?';

  @override
  String get deletingMessages => 'Omiના జ్ఞాపకం నుండి మీ సందేశాలను తొలగిస్తోంది...';

  @override
  String get messageCopied => '✨ సందేశం క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get cannotReportOwnMessage => 'మీరు మీ స్వంత సందేశాలను నివేదించలేరు.';

  @override
  String get reportMessage => 'సందేశాన్ని నివేదించండి';

  @override
  String get reportMessageConfirm => 'మీరు ఈ సందేశాన్ని నివేదించాలనుకుంటున్నారని మీరు ఖచ్చితమైనారా?';

  @override
  String get messageReported => 'సందేశం విజయవంతంగా నివేదించబడింది.';

  @override
  String get thankYouFeedback => 'మీ ఫీడ్‌బ్యాక్ కోసం ధన్యవాదాలు!';

  @override
  String get clearChat => 'చ్యాట్‌ను సరిచేయండి';

  @override
  String get clearChatConfirm => 'మీరు చ్యాట్‌ను సరిచేయాలనుకుంటున్నారని మీరు ఖచ్చితమైనారా? ఈ చర్య రద్దు చేయబడదు.';

  @override
  String get maxFilesLimit => 'మీరు ఒక సమయంలో 4 ఫైల్‌లను మాత్రమే అప్‌లోడ్ చేయవచ్చు';

  @override
  String get chatWithOmi => 'Omiతో చ్యాట్ చేయండి';

  @override
  String get apps => 'అనువర్తనాలు';

  @override
  String get noAppsFound => 'అనువర్తనాలు కనుగొనబడలేదు';

  @override
  String get tryAdjustingSearch => 'మీ శోధన లేదా ఫిల్టర్‌ను సరిచేయడానికి ప్రయత్నించండి';

  @override
  String get createYourOwnApp => 'మీ స్వంత అనువర్తనాన్ని సృష్టించండి';

  @override
  String get buildAndShareApp => 'మీ ఆచిన అనువర్తనాన్ని నిర్మించండి మరియు భాగస్వామ్యం చేయండి';

  @override
  String get searchApps => 'అనువర్తనాలను శోధించండి...';

  @override
  String get myApps => 'నా అనువర్తనాలు';

  @override
  String get installedApps => 'ఇన్‌స్టాల్ చేసిన అనువర్తనాలు';

  @override
  String get unableToFetchApps =>
      'అనువర్తనాలను పొందలేకపోయాము :(\n\nదయచేసి మీ ఇంటర్నెట్ కనెక్షన్‌ను తనిఖీ చేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get aboutOmi => 'Omiని గురించి';

  @override
  String get privacyPolicy => 'గోప్యతా విధానం';

  @override
  String get visitWebsite => 'వెబ్‌సైట్‌ను సందర్శించండి';

  @override
  String get helpOrInquiries => 'సహాయం లేదా విచారణలు?';

  @override
  String get joinCommunity => 'సమాజంలో చేరండి!';

  @override
  String get membersAndCounting => '8000+ సభ్యులు మరియు లెక్కలు.';

  @override
  String get deleteAccountTitle => 'ఖాతాను తొలగించు';

  @override
  String get deleteAccountConfirm => 'మీరు మీ ఖాతాను తొలగించాలనుకుంటున్నారని మీరు ఖచ్చితమైనారా?';

  @override
  String get cannotBeUndone => 'ఇది రద్దు చేయబడదు.';

  @override
  String get allDataErased => 'మీ అన్ని జ్ఞాపకాలు మరియు సంభాషణలు శాశ్వతంగా తొలగించబడుతుంది.';

  @override
  String get appsDisconnected => 'మీ అనువర్తనాలు మరియు ఇంటిగ్రేషన్‌లు వెంటనే డిస్‌కనెక్ట్ చేయబడుతుంది.';

  @override
  String get exportBeforeDelete =>
      'మీరు మీ ఖాతాను తొలగించడానికి ముందు మీ డేటాను ఎగుమతి చేయవచ్చు, కానీ ఒకసారి తొలగించిన తర్వాత, దానిని పునరుద్ధరించలేము.';

  @override
  String get deleteAccountCheckbox =>
      'మీ ఖాతాను తొలగించడం శాశ్వతం మరియు జ్ఞాపకాలు మరియు సంభాషణలతో సహా అన్ని డేటా కోల్పోతుందని మరియు పునరుద్ధరించలేమని నేను అర్థం చేసుకున్నాను.';

  @override
  String get areYouSure => 'మీరు ఖచ్చితమైనారా?';

  @override
  String get deleteAccountFinal =>
      'ఈ చర్య చేయలేనిది మరియు మీ ఖాతా మరియు సమస్త సంబంధిత డేటాను శాశ్వతంగా తొలగిస్తుంది. మీరు ముందుకు సాగాలనుకుంటున్నారని మీరు ఖచ్చితమైనారా?';

  @override
  String get deleteNow => 'ఇప్పుడు తొలగించు';

  @override
  String get goBack => 'వెనుక చెంది';

  @override
  String get checkBoxToConfirm =>
      'మీ ఖాతాను తొలగించడం శాశ్వతం మరియు చేయలేనిది అని మీరు అర్థం చేసుకున్నారని నిర్ధారించడానికి పెట్టెను తనిఖీ చేయండి.';

  @override
  String get profile => 'ప్రొఫైల్';

  @override
  String get name => 'పేరు';

  @override
  String get email => 'ఇమెయిల్';

  @override
  String get customVocabulary => 'కస్టమ్ పదాలు';

  @override
  String get identifyingOthers => 'ఇతరులను గుర్తించడం';

  @override
  String get paymentMethods => 'చెల్లింపు పద్ధతులు';

  @override
  String get conversationDisplay => 'సంభాషణ ప్రదర్శన';

  @override
  String get dataPrivacy => 'ডేటా గోప్యత';

  @override
  String get userId => 'వినియోగదారు ID';

  @override
  String get notSet => 'సెట్ చేయబడలేదు';

  @override
  String get userIdCopied => 'వినియోగదారు ID క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get systemDefault => 'సిస్టమ్ డిఫాల్ట్';

  @override
  String get planAndUsage => 'ప్లాన్ & ఉపయోగం';

  @override
  String get offlineSync => 'ఆఫ్‌లైన్ సమకాలీకరణ';

  @override
  String get deviceSettings => 'ডివైస్ సెట్టింగ్‌లు';

  @override
  String get integrations => 'ఇంటిగ్రేషన్‌లు';

  @override
  String get feedbackBug => 'ఫీడ్‌బ్యాక్ / బగ్';

  @override
  String get helpCenter => 'సహాయ కేంద్రం';

  @override
  String get developerSettings => 'డెవలపర్ సెట్టింగ్‌లు';

  @override
  String get getOmiForMac => 'Mac కోసం Omi పొందండి';

  @override
  String get referralProgram => 'సూచన కార్యక్రమం';

  @override
  String get signOut => 'సైన్ అవుట్ చేయండి';

  @override
  String get appAndDeviceCopied => 'అనువర్తనం మరియు డివైస్ వివరాలు కాపీ చేయబడ్డాయి';

  @override
  String get wrapped2025 => '2025 రాప్‌డ్';

  @override
  String get yourPrivacyYourControl => 'మీ గోప్యత, మీ నియంత్రణ';

  @override
  String get privacyIntro =>
      'Omiలో, మేము మీ గోప్యతను రక్షించడానికి ప్రతిబద్ధులు. ఈ పేజీ మీ డేటా ఎలా నిల్వ చేయబడుతుందో మరియు ఎలా ఉపయోగించబడుతుందో నియంత్రించడానికి మిమ్మల్ని అనుమతిస్తుంది.';

  @override
  String get learnMore => 'మరింత తెలుసుకోండి...';

  @override
  String get dataProtectionLevel => 'డేటా సంరక్షణ స్థాయి';

  @override
  String get dataProtectionDesc =>
      'మీ డేటా బలమైన ఎన్‌క్రిప్షన్‌తో డిఫాల్ట్‌గా సురక్షితంగా ఉంది. క్రింద మీ సెట్టింగ్‌లు మరియు భవిష్యత్ గోప్యతా ఎంపికలను సమీక్షించండి.';

  @override
  String get appAccess => 'అనువర్తన ప్రాప్తి';

  @override
  String get appAccessDesc =>
      'ఈ క్రింది అనువర్తనాలు మీ డేటాను యాక్సెస్ చేయవచ్చు. దాని అనుమతులను నిర్వహించడానికి అనువర్తనంపై నొక్కండి.';

  @override
  String get noAppsExternalAccess => 'ఇన్‌స్టాల్ చేసిన అనువర్తనాలకు మీ డేటాకు బాహ్య ప్రాప్తి లేదు.';

  @override
  String get deviceName => 'డివైస్ పేరు';

  @override
  String get deviceId => 'డివైస్ ID';

  @override
  String get firmware => 'ఫర్మ్‌వేర్';

  @override
  String get sdCardSync => 'SD కార్డ్ సమకాలీకరణ';

  @override
  String get hardwareRevision => 'హార్డ్‌వేర్ సంస్కరణ';

  @override
  String get modelNumber => 'మోడల్ సంఖ్య';

  @override
  String get manufacturer => 'తయారీదారు';

  @override
  String get doubleTap => 'డబల్ నొక్కండి';

  @override
  String get ledBrightness => 'LED ప్రకాశం';

  @override
  String get micGain => 'మైక్రోఫోన్ లాభం';

  @override
  String get disconnect => 'డిస్‌కనెక్ట్ చేయండి';

  @override
  String get forgetDevice => 'డివైస్‌ను మర్చిపోండి';

  @override
  String get chargingIssues => 'ఛార్జింగ్ సమస్యలు';

  @override
  String get disconnectDevice => 'డివైస్‌ను డిస్‌కనెక్ట్ చేయండి';

  @override
  String get unpairDevice => 'డివైస్‌ను అన్‌పెయిర్ చేయండి';

  @override
  String get unpairAndForget => 'డివైస్‌ను అన్‌పెయిర్ చేసి మర్చిపోండి';

  @override
  String get deviceDisconnectedMessage => 'మీ Omi డిస్‌కనెక్ట్ చేయబడింది 😔';

  @override
  String get deviceUnpairedMessage =>
      'డివైస్ అన్‌పెయిర్ చేయబడింది. అన్‌పేరింగ్‌ను పూర్తి చేయడానికి సెట్టింగ్‌లు > బ్లూటూత్‌కు వెళ్లి డివైస్‌ను మర్చిపోండి.';

  @override
  String get unpairDialogTitle => 'డివైస్‌ను అన్‌పెయిర్ చేయండి';

  @override
  String get unpairDialogMessage =>
      'ఇది డివైస్‌ను విచ్ఛిన్నం చేస్తుంది కాబట్టి దానిని మరొక ఫోన్‌కు కనెక్ట్ చేయవచ్చు. ప్రక్రియను పూర్తి చేయడానికి మీరు సెట్టింగ్‌లు > బ్లూటూత్‌కు వెళ్లి డివైస్‌ను మర్చిపోవాలి.';

  @override
  String get deviceNotConnected => 'డివైస్ కనెక్ట్ చేయబడలేదు';

  @override
  String get connectDeviceMessage =>
      'ఆచిన సెట్టింగ్‌లు మరియు ఆచిన సెట్టింగ్‌లను యాక్సెస్ చేయడానికి మీ Omi ডివైస్‌ను కనెక్ట్ చేయండి';

  @override
  String get deviceInfoSection => 'ডివైస్ సమాచారం';

  @override
  String get customizationSection => 'ఆచిన సెట్టింగ్';

  @override
  String get hardwareSection => 'హార్డ్‌వేర్';

  @override
  String get v2Undetected => 'V2 గుర్తించబడలేదు';

  @override
  String get v2UndetectedMessage =>
      'V1 డివైస్ ఉందని లేదా మీ డివైస్ కనెక్ట్ చేయబడలేదని మేము చూస్తున్నాము. SD కార్డ్ కార్యకలాపం V2 డివైసెస్‌కు మాత్రమే అందుబాటులో ఉంది.';

  @override
  String get endConversation => 'సంభాషణను ముగించండి';

  @override
  String get pauseResume => 'పాజ్/రీస్యూమ్';

  @override
  String get starConversation => 'సంభాషణను స్టార్ చేయండి';

  @override
  String get doubleTapAction => 'డబల్ ట్యాప్ చర్య';

  @override
  String get endAndProcess => 'సంభాషణను ముగించండి & ప్రక్రియ చేయండి';

  @override
  String get pauseResumeRecording => 'రికార్డింగ్‌ను పాజ్/రీస్యూమ్ చేయండి';

  @override
  String get starOngoing => 'పురోగతిలో ఉన్న సంభాషణను స్టార్ చేయండి';

  @override
  String get off => 'ఆఫ్';

  @override
  String get max => 'గరిష్టం';

  @override
  String get mute => 'మ్యూట్';

  @override
  String get quiet => 'నిశ్శబ్ద';

  @override
  String get normal => 'సాధారణ';

  @override
  String get high => 'ఎక్కువ';

  @override
  String get micGainDescMuted => 'మైక్రోఫోన్ మ్యూట్ చేయబడింది';

  @override
  String get micGainDescLow => 'చాలా నిశ్శబ్ద - బిగ్గరగా ఉన్న నిర్లిష్టల కోసం';

  @override
  String get micGainDescModerate => 'నిశ్శబ్ద - మధ్యమ శబ్దం కోసం';

  @override
  String get micGainDescNeutral => 'నిరపేక్ష - సంతులిత రికార్డింగ్';

  @override
  String get micGainDescSlightlyBoosted => 'కొద్దిగా బూస్ట్ చేయబడిన - సాధారణ ఉపయోగం';

  @override
  String get micGainDescBoosted => 'బూస్ట్ చేయబడిన - నిశ్శబ్ద నిర్లిష్టల కోసం';

  @override
  String get micGainDescHigh => 'ఎక్కువ - దూర లేదా మృదువైన కంఠాలకు';

  @override
  String get micGainDescVeryHigh => 'చాలా ఎక్కువ - చాలా నిశ్శబ్ద వనరుల కోసం';

  @override
  String get micGainDescMax => 'గరిష్టం - జాగ్రత్తగా ఉపయోగించండి';

  @override
  String get developerSettingsTitle => 'డెవలపర్ సెట్టింగ్‌లు';

  @override
  String get saving => 'సేవ్ చేస్తోంది...';

  @override
  String get beta => 'బీటా';

  @override
  String get transcription => 'ట్రాన్‌స్క్రిప్షన్';

  @override
  String get transcriptionConfig => 'STT ప్రదాతను కాన్ఫిగర్ చేయండి';

  @override
  String get conversationTimeout => 'సంభాషణ సమయం అక్కా';

  @override
  String get conversationTimeoutConfig => 'సంభాషణలు ఎప్పుడు స్వయంచాలకంగా ముగుస్తాయో సెట్ చేయండి';

  @override
  String get importData => 'డేటాను దిగుమతి చేయండి';

  @override
  String get importDataConfig => 'ఇతర వనరుల నుండి డేటాను దిగుమతి చేయండి';

  @override
  String get debugDiagnostics => 'డీబగ్ & నిర్ధారణలు';

  @override
  String get endpointUrl => 'ఎండ్‌పాయింట్ URL';

  @override
  String get noApiKeys => 'ఇంకా API కీలు లేవు';

  @override
  String get createKeyToStart => 'ప్రారంభించడానికి కీని సృష్టించండి';

  @override
  String get createKey => 'కీని సృష్టించండి';

  @override
  String get docs => 'డాక్‌లు';

  @override
  String get yourOmiInsights => 'మీ Omi అంతర్దృష్టులు';

  @override
  String get today => 'ఈ రోజు';

  @override
  String get thisMonth => 'ఈ నెల';

  @override
  String get thisYear => 'ఈ సంవత్సరం';

  @override
  String get allTime => 'అన్ని సమయం';

  @override
  String get noActivityYet => 'ఇంకా చర్య లేదు';

  @override
  String get startConversationToSeeInsights => 'మీ ఉపయోగ అంతర్దృష్టులను ఇక్కడ చూడటానికి Omiతో సంభాషణను ప్రారంభించండి.';

  @override
  String get listening => 'వినుట';

  @override
  String get listeningSubtitle => 'Omi సక్రియంగా వినిన మొత్తం సమయం.';

  @override
  String get understanding => 'అర్థం చేసుకోవడం';

  @override
  String get understandingSubtitle => 'మీ సంభాషణల నుండి అర్థం చేసిన పదాలు.';

  @override
  String get providing => 'అందించటం';

  @override
  String get providingSubtitle => 'చర్య అంశాలు మరియు స్వయంచాలకంగా సంగ్రహించిన నోట్‌లు.';

  @override
  String get remembering => 'గుర్తుంచుకోవడం';

  @override
  String get rememberingSubtitle => 'మీ కోసం గుర్తుంచుకున్న వాస్తవాలు మరియు వివరాలు.';

  @override
  String get unlimitedPlan => 'అపరిమిత ప్లాన్';

  @override
  String get managePlan => 'ప్లాన్‌ను నిర్వహించండి';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'మీ ప్లాన్ $dateన రద్దు చేయబడుతుంది.';
  }

  @override
  String renewsOn(String date) {
    return 'మీ ప్లాన్ $dateన పునరుద్ధరించబడుతుంది.';
  }

  @override
  String get basicPlan => 'ఉచిత ప్లాన్';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used of $limit నిమిషాలు ఉపయోగించబడ్డాయి';
  }

  @override
  String get upgrade => 'అప్‌గ్రేడ్ చేయండి';

  @override
  String get upgradeToUnlimited => 'అపరిమితానికి అప్‌గ్రేడ్ చేయండి';

  @override
  String basicPlanDesc(int limit) {
    return 'మీ ప్లాన్ నెలకు $limit ఉచిత నిమిషాలను కలిగి ఉంది. అపరిమితానికి అప్‌గ్రేడ్ చేయండి.';
  }

  @override
  String get shareStatsMessage => 'నా Omi గణాంకాలు భాగస్వామ్యం చేస్తోంది! (omi.me - మీ ఎల్లప్పుడు ఆన్ AI సహాయకుడు)';

  @override
  String get sharePeriodToday => 'ఈ రోజు, omi చేసింది:';

  @override
  String get sharePeriodMonth => 'ఈ నెల, omi చేసింది:';

  @override
  String get sharePeriodYear => 'ఈ సంవత్సరం, omi చేసింది:';

  @override
  String get sharePeriodAllTime => 'ఇప్పటి వరకు, omi చేసింది:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes నిమిషాల పాటు వినిన';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words పదాలను అర్థం చేసుకున్నాను';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count అంతర్దృష్టులను అందించాము';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count జ్ఞాపకాలను గుర్తుంచుకున్నాము';
  }

  @override
  String get debugLogs => 'డీబగ్ లాగ్‌లు';

  @override
  String get debugLogsAutoDelete => '3 రోజుల తర్వాత స్వయంచాలకంగా తొలగించబడుతుంది.';

  @override
  String get debugLogsDesc => 'సమస్యల నిర్ధారణకు సహాయం చేస్తుంది';

  @override
  String get noLogFilesFound => 'లాగ్ ఫైల్‌లు కనుగొనబడలేదు.';

  @override
  String get omiDebugLog => 'Omi డీబగ్ లాగ్';

  @override
  String get logShared => 'లాగ్ భాగస్వామ్యం చేయబడింది';

  @override
  String get selectLogFile => 'లాగ్ ఫైల్‌ను ఎంచుకోండి';

  @override
  String get shareLogs => 'లాగ్‌లను భాగస్వామ్యం చేయండి';

  @override
  String get debugLogCleared => 'డీబగ్ లాగ్ సరిచేయబడింది';

  @override
  String get exportStarted => 'ఎగుమతి ప్రారంభమైంది. ఇది కొన్ని సెకన్లు పట్టవచ్చు...';

  @override
  String get exportAllData => 'అన్ని డేటాను ఎగుమతి చేయండి';

  @override
  String get exportDataDesc => 'సంభాషణలను JSON ఫైల్‌కు ఎగుమతి చేయండి';

  @override
  String get exportedConversations => 'Omiలో నిర్గమం చేసిన సంభాషణలు';

  @override
  String get exportShared => 'ఎగుమతి భాగస్వామ్యం చేయబడింది';

  @override
  String get deleteKnowledgeGraphTitle => 'జ్ఞాన గ్రాఫ్‌ను తొలగించాలా?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'ఇది అన్ని ఉత్పన్న జ్ఞాన గ్రాఫ్ డేటా (నోడ్‌లు మరియు కనెక్షన్‌లు) తొలగిస్తుంది. మీ అసలు జ్ఞాపకాలు సురక్షితంగా ఉంటాయి. గ్రాఫ్ కాలక్రమేణ లేదా తర్వాత అభ్యర్థనపై పునర్నిర్మించబడుతుంది.';

  @override
  String get knowledgeGraphDeleted => 'జ్ఞాన గ్రాఫ్ తొలగించబడింది';

  @override
  String deleteGraphFailed(String error) {
    return 'గ్రాఫ్‌ను తొలగించడంలో విఫలమైంది: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'జ్ఞాన గ్రాఫ్‌ను తొలగించు';

  @override
  String get deleteKnowledgeGraphDesc => 'అన్ని నోడ్‌లు మరియు కనెక్షన్‌లను క్లియర్ చేయండి';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP సర్వర్';

  @override
  String get mcpServerDesc => 'AI సహాయకులను మీ డేటాకు కనెక్ట్ చేయండి';

  @override
  String get serverUrl => 'సర్వర్ URL';

  @override
  String get urlCopied => 'URL కాపీ చేయబడింది';

  @override
  String get apiKeyAuth => 'API కీ ప్రామాణీకరణ';

  @override
  String get header => 'హెడర్';

  @override
  String get authorizationBearer => 'ప్రామాణీకరణ: వాహక <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'క్లায়েంట్ ID';

  @override
  String get clientSecret => 'క్లయంట్ సీక్రెట్';

  @override
  String get useMcpApiKey => 'మీ MCP API కీని ఉపయోగించండి';

  @override
  String get webhooks => 'వెబ్‌హుక్‌లు';

  @override
  String get conversationEvents => 'సంభాషణ ఈవెంట్‌లు';

  @override
  String get newConversationCreated => 'కొత్త సంభాషణ సృష్టించబడింది';

  @override
  String get realtimeTranscript => 'రియల్-టైమ్ ట్రాన్‌స్క్రిప్ట్';

  @override
  String get transcriptReceived => 'ట్రాన్‌స్క్రిప్ట్ అందుకోబడింది';

  @override
  String get audioBytes => 'ఆడియో బైట్‌లు';

  @override
  String get audioDataReceived => 'ఆడియో డేటా అందుకోబడింది';

  @override
  String get intervalSeconds => 'విరామం (సెకన్లు)';

  @override
  String get daySummary => 'రోజు సారాంశం';

  @override
  String get summaryGenerated => 'సారాంశం రూపొందించబడింది';

  @override
  String get claudeDesktop => 'Claude డెస్క్‌టాప్';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.json కు జోడించండి';

  @override
  String get copyConfig => 'కాన్ఫిగ్ కాపీ చేయండి';

  @override
  String get configCopied => 'కాన్ఫిగ్ క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get listeningMins => 'వినుట (నిమిషాలు)';

  @override
  String get understandingWords => 'అర్థం చేసుకోవడం (పదాలు)';

  @override
  String get insights => 'అంతర్దృష్టులు';

  @override
  String get memories => 'జ్ఞాపకాలు';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used యొక్క $limit నిమిషం ఈ నెలలో ఉపయోగించబడింది';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used యొక్క $limit పదాలు ఈ నెలలో ఉపయోగించబడ్డాయి';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used యొక్క $limit అంతర్దృష్టులు ఈ నెలలో పొందబడ్డాయి';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used యొక్క $limit జ్ఞాపకాలు ఈ నెలలో సృష్టించబడ్డాయి';
  }

  @override
  String get visibility => 'దృశ్యమానత';

  @override
  String get visibilitySubtitle => 'ఎటువంటి సంభాషణలు మీ జాబితాలో కనిపించాలో నియంత్రించండి';

  @override
  String get showShortConversations => 'చిన్న సంభాషణలను చూపండి';

  @override
  String get showShortConversationsDesc => 'థ్రెషోల్డ్‌కు కంటే చిన్న సంభాషణలను ప్రదర్శించండి';

  @override
  String get showDiscardedConversations => 'విస్మరించిన సంభాషణలను చూపండి';

  @override
  String get showDiscardedConversationsDesc => 'విస్మరించిన సంభాషణలను చేర్చండి';

  @override
  String get shortConversationThreshold => 'చిన్న సంభాషణ థ్రెషోల్డ్';

  @override
  String get shortConversationThresholdSubtitle => 'ఇటువంటి సంభాషణలు దానిలో సంపూర్ణ సమయం విస్మరించబడుతుంది';

  @override
  String get durationThreshold => 'సమయ వ్యవధి థ్రెషోల్డ్';

  @override
  String get durationThresholdDesc => 'ఇటువంటి సంభాషణలను దానిలో చిన్నవిస్మరించండి';

  @override
  String minLabel(int count) {
    return '$count నిమిషం';
  }

  @override
  String get customVocabularyTitle => 'కస్టమ్ పదాలు';

  @override
  String get addWords => 'పదాలను జోడించండి';

  @override
  String get addWordsDesc => 'పేరు, నిబంధనలు, లేదా అసాధారణ పదాలు';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'కనెక్ట్ చేయండి';

  @override
  String get comingSoon => 'త్వరలో రానున్నది';

  @override
  String get integrationsFooter => 'చ్యాట్‌లో డేటా మరియు మెట్రిక్‌లను చూడటానికి మీ అనువర్తనాలను కనెక్ట్ చేయండి.';

  @override
  String get completeAuthInBrowser =>
      'దయచేసి మీ బ్రౌజర్‌లో ప్రామాణీకరణను పూర్తి చేయండి. పూర్తి చేసిన తర్వాత, అనువర్తనానికి తిరిగి వెళ్లండి.';

  @override
  String failedToStartAuth(String appName) {
    return '$appName ప్రామాణీకరణను ప్రారంభించడంలో విఫలమైంది';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName నుండి డిస్‌కనెక్ట్ చేయాలా?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return '$appName నుండి డిస్‌కనెక్ట్ చేయాలనుకుంటున్నారని మీరు ఖచ్చితమైనారా? మీరు ఎప్పుడైనా తిరిగి కనెక్ట్ చేయవచ్చు.';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName నుండి డిస్‌కనెక్ట్ చేయబడింది';
  }

  @override
  String get failedToDisconnect => 'డిస్‌కనెక్ట్ చేయడంలో విఫలమైంది';

  @override
  String connectTo(String appName) {
    return '$appNameకు కనెక్ట్ చేయండి';
  }

  @override
  String authAccessMessage(String appName) {
    return 'మీరు Omiని $appName డేటాను యాక్సెస్ చేయడానికి అధికరించాలి. ఇది ప్రామాణీకరణ కోసం మీ బ్రౌజర్‌ను తెరుస్తుంది.';
  }

  @override
  String get continueAction => 'కొనసాగించండి';

  @override
  String get languageTitle => 'భాష';

  @override
  String get primaryLanguage => 'ప్రధాన భాష';

  @override
  String get automaticTranslation => 'స్వయంచాలక అనువాదం';

  @override
  String get detectLanguages => '10+ భాషలను గుర్తించండి';

  @override
  String get authorizeSavingRecordings => 'రికార్డింగ్‌లను సేవ్ చేయడానికి అధికారం ఇవ్వండి';

  @override
  String get thanksForAuthorizing => 'అధికారం ఇచ్చినందుకు ధన్యవాదాలు!';

  @override
  String get needYourPermission => 'మాకు మీ అనుమతి కావాలి';

  @override
  String get alreadyGavePermission =>
      'మీరు ఇప్పటికే మీ రికార్డింగ్‌లను సేవ్ చేయడానికి మాకు అనుమతి ఇచ్చారు. మాకు దీని కారణం గుర్తించాయి:';

  @override
  String get wouldLikePermission => 'మీ గ్రంథిత్వ రికార్డింగ్‌లను సేవ్ చేయడానికి మాకు మీ అనుమతి కావాలి. ఇక్కడ ఎందుకు:';

  @override
  String get improveSpeechProfile => 'మీ ఉపన్యాస ప్రొఫైల్‌ను మెరుగుపరచండి';

  @override
  String get improveSpeechProfileDesc =>
      'మీ వ్యక్తిగత ఉపన్యాస ప్రొఫైల్‌ను శిక్షణ ఇవ్వడానికి మరియు మెరుగుపరచడానికి మేము రికార్డింగ్‌లను ఉపయోగిస్తాము.';

  @override
  String get trainFamilyProfiles => 'స్నేహితుల మరియు కుటుంబ సభ్యుల ప్రొఫైల్‌లను శిక్షణ ఇవ్వండి';

  @override
  String get trainFamilyProfilesDesc =>
      'మీ రికార్డింగ్‌లు మీ స్నేహితులు మరియు కుటుంబ సభ్యులను గుర్తించడానికి మరియు ప్రొఫైల్‌లను సృష్టించడానికి సహాయ చేస్తాయి.';

  @override
  String get enhanceTranscriptAccuracy => 'ట్రాన్‌స్క్రిప్ట్ ఖచ్చితత్వాన్ని మెరుగుపరచండి';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'మా నమూనా మెరుగుపడుతున్నందున, మేము మీ రికార్డింగ్‌ల కోసం మెరుగైన ట్రాన్‌స్క్రిప్షన్ ఫలితాలను అందించవచ్చు.';

  @override
  String get legalNotice =>
      'చట్టపరమైన నోటీస్: వాయిస్ డేటాను రికార్డింగ్ మరియు నిల్వ చేయడం యొక్క చట్టబద్ధత మీ స్థానం మరియు ఎలా ఈ లక్షణాన్ని ఉపయోగిస్తున్నారో బట్టి భిన్నంగా ఉండవచ్చు. స్థానిక చట్టాలు మరియు నియమాలకు అనుగుణంగా ఉండటం మీ బాధ్యత.';

  @override
  String get alreadyAuthorized => 'ఇప్పటికే అధికరించబడింది';

  @override
  String get authorize => 'అధికారం ఇవ్వండి';

  @override
  String get revokeAuthorization => 'అధికారాన్ని రద్దు చేయండి';

  @override
  String get authorizationSuccessful => 'అధికారం విజయవంతమైంది!';

  @override
  String get failedToAuthorize => 'ఆధికారం పొందడానికి విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get authorizationRevoked => 'ఆధికారం రద్దు చేయబడింది.';

  @override
  String get recordingsDeleted => 'రికార్డింగ్‌లు తొలగించబడ్డాయి.';

  @override
  String get failedToRevoke => 'ఆధికారం రద్దు చేయడానికి విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get permissionRevokedTitle => 'అనుమతి రద్దు చేయబడింది';

  @override
  String get permissionRevokedMessage => 'మీ ఆ విషయానికి సంబంధించిన రికార్డింగ్‌లను కూడా తీసివేయాలనుకుంటున్నారా?';

  @override
  String get yes => 'అవును';

  @override
  String get editName => 'పేరు సవరించండి';

  @override
  String get howShouldOmiCallYou => 'Omi మిమ్మల్ని ఎలా పిలవాలి?';

  @override
  String get enterYourName => 'మీ పేరు నమోదు చేయండి';

  @override
  String get nameCannotBeEmpty => 'పేరు ఖాళీగా ఉండకూడదు';

  @override
  String get nameUpdatedSuccessfully => 'పేరు విజయవంతంగా నవీకరించబడింది!';

  @override
  String get calendarSettings => 'క్యాలెండర్ సెట్టింగ్‌లు';

  @override
  String get calendarProviders => 'క్యాలెండర్ ప్రదాతలు';

  @override
  String get macOsCalendar => 'macOS క్యాలెండర్';

  @override
  String get connectMacOsCalendar => 'మీ స్థానిక macOS క్యాలెండర్‌ను కనెక్ట్ చేయండి';

  @override
  String get googleCalendar => 'Google క్యాలెండర్';

  @override
  String get syncGoogleAccount => 'మీ Google ఖాతాతో సింక్ చేయండి';

  @override
  String get showMeetingsMenuBar => 'మెనూ బార్‌లో రాబోయే సమావేశాలను చూపించండి';

  @override
  String get showMeetingsMenuBarDesc =>
      'macOS మెనూ బార్‌లో మీ తదుపరి సమావేశ మరియు దానిని ప్రారంభించే వరకు సమయాన్ని ప్రదర్శించండి';

  @override
  String get showEventsNoParticipants => 'పాల్గొనేవారు లేని ఈవెంట్‌లను చూపించండి';

  @override
  String get showEventsNoParticipantsDesc =>
      'ప్రారంభించినప్పుడు, రాబోయేది పాల్గొనేవారు లేదా వీడియో లింక్ లేని ఈవెంట్‌లను చూపుస్తుంది.';

  @override
  String get yourMeetings => 'మీ సమావేశాలు';

  @override
  String get refresh => 'రిఫ్రెష్';

  @override
  String get noUpcomingMeetings => 'రాబోయే సమావేశాలు లేవు';

  @override
  String get checkingNextDays => 'తదుపరి 30 రోజులను తనిఖీ చేస్తుంది';

  @override
  String get tomorrow => 'రేపు';

  @override
  String get googleCalendarComingSoon => 'Google క్యాలెండర్ ఏకీకరణ త్వరలో వస్తుంది!';

  @override
  String connectedAsUser(String userId) {
    return 'ఉపయోగకర్త వలె కనెక్ట్ చేయబడింది: $userId';
  }

  @override
  String get defaultWorkspace => 'డిఫాల్ట్ కార్యక్షేత్రం';

  @override
  String get tasksCreatedInWorkspace => 'టాస్క్‌లు ఈ కార్యక్షేత్రంలో సృష్టించబడతాయి';

  @override
  String get defaultProjectOptional => 'డిఫాల్ట్ ప్రాజెక్ట్ (ఐచ్ఛికం)';

  @override
  String get leaveUnselectedTasks => 'ప్రాజెక్ట్ లేకుండా టాస్క్‌లను సృష్టించడానికి ఎంచుకోకుండా వదిలివేయండి';

  @override
  String get noProjectsInWorkspace => 'ఈ కార్యక్షేత్రంలో ప్రాజెక్ట్‌లు కనుగొనబడలేదు';

  @override
  String get conversationTimeoutDesc =>
      'సంభాషణను స్వయంచాలకంగా ముగించడానికి ముందు నిశ్శబ్దంలో ఎంతకాలం వేచి ఉండాలో ఎంచుకోండి:';

  @override
  String get timeout2Minutes => '2 నిమిషాలు';

  @override
  String get timeout2MinutesDesc => '2 నిమిషాల నిశ్శబ్దం తర్వాత సంభాషణను ముగించండి';

  @override
  String get timeout5Minutes => '5 నిమిషాలు';

  @override
  String get timeout5MinutesDesc => '5 నిమిషాల నిశ్శబ్దం తర్వాత సంభాషణను ముగించండి';

  @override
  String get timeout10Minutes => '10 నిమిషాలు';

  @override
  String get timeout10MinutesDesc => '10 నిమిషాల నిశ్శబ్దం తర్వాత సంభాషణను ముగించండి';

  @override
  String get timeout30Minutes => '30 నిమిషాలు';

  @override
  String get timeout30MinutesDesc => '30 నిమిషాల నిశ్శబ్దం తర్వాత సంభాషణను ముగించండి';

  @override
  String get timeout4Hours => '4 గంటలు';

  @override
  String get timeout4HoursDesc => '4 గంటల నిశ్శబ్దం తర్వాత సంభాషణను ముగించండి';

  @override
  String get conversationEndAfterHours => 'సంభాషణలు ఇప్పుడు 4 గంటల నిశ్శబ్దం తర్వాత ముగుస్తాయి';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'సంభాషణలు ఇప్పుడు $minutes నిమిషం(లు) నిశ్శబ్దం తర్వాత ముగుస్తాయి';
  }

  @override
  String get tellUsPrimaryLanguage => 'మీ ప్రాధమిక భాషను మాకు చెప్పండి';

  @override
  String get languageForTranscription =>
      'మరింత ఖచ్చితమైన ట్రాన్‌స్క్రిప్షన్‌లు మరియు ব్యక్తిగతకృత అనుభవం కోసం మీ భాష సెట్ చేయండి.';

  @override
  String get singleLanguageModeInfo => 'ఏకీ భాష మోడ్ ప్రారంభించబడింది. అధిక ఖచ్చితత్వం కోసం అనువాదం నిలిపివేయబడింది.';

  @override
  String get searchLanguageHint => 'పేరు లేదా కోడ్‌ద్వారా భాష చేరండి';

  @override
  String get noLanguagesFound => 'భాషలు కనుగొనబడలేదు';

  @override
  String get skip => 'దాటవేయండి';

  @override
  String languageSetTo(String language) {
    return 'భాష $languageకు సెట్ చేయబడింది';
  }

  @override
  String get failedToSetLanguage => 'భాష సెట్ చేయడానికి విఫలమైంది';

  @override
  String appSettings(String appName) {
    return '$appName సెట్టింగ్‌లు';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName నుండి డిస్‌కనెక్ట్ చేయాలా?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'ఇది మీ $appName ఆధికారాన్ని తీసివేస్తుంది. దీన్ని మళ్లీ ఉపయోగించడానికి మీరు తిరిగి కనెక్ట్ చేయవలసి ఉంటుంది.';
  }

  @override
  String connectedToApp(String appName) {
    return '$appNameకు కనెక్ట్ చేయబడింది';
  }

  @override
  String get account => 'ఖాతా';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'మీ చర్య పరిమాణాలు $appName ఖాతాకు సింక్ చేయబడతాయి';
  }

  @override
  String get defaultSpace => 'డిఫాల్ట్ స్పేస్';

  @override
  String get selectSpaceInWorkspace => 'మీ కార్యక్షేత్రంలో స్పేస్ ఎంచుకోండి';

  @override
  String get noSpacesInWorkspace => 'ఈ కార్యక్షేత్రంలో స్పేస్‌లు కనుగొనబడలేదు';

  @override
  String get defaultList => 'డిఫాల్ట్ జాబితా';

  @override
  String get tasksAddedToList => 'టాస్క్‌లు ఈ జాబితాకు జోడించబడతాయి';

  @override
  String get noListsInSpace => 'ఈ స్పేస్‌లో జాబితాలు కనుగొనబడలేదు';

  @override
  String failedToLoadRepos(String error) {
    return 'రిపోజిటరీలను లోడ్ చేయడానికి విఫలమైంది: $error';
  }

  @override
  String get defaultRepoSaved => 'డిఫాల్ట్ రిపోజిటరీ సేవ్ చేయబడింది';

  @override
  String get failedToSaveDefaultRepo => 'డిఫాల్ట్ రిపోజిటరీ సేవ్ చేయడానికి విఫలమైంది';

  @override
  String get defaultRepository => 'డిఫాల్ట్ రిపోజిటరీ';

  @override
  String get selectDefaultRepoDesc =>
      'సమస్యలను సృష్టించడానికి డిఫాల్ట్ రిపోజిటరీని ఎంచుకోండి. సమస్యలను సృష్టించేటప్పుడు మీరు ఇప్పటికీ వేరేవ రిపోజిటరీని నిర్దేశించవచ్చు.';

  @override
  String get noReposFound => 'రిపోజిటరీలు కనుగొనబడలేదు';

  @override
  String get private => 'ప్రైవేట్';

  @override
  String updatedDate(String date) {
    return '$date నవీకరించబడింది';
  }

  @override
  String get yesterday => 'నిన్న';

  @override
  String daysAgo(int count) {
    return '$count రోజుల క్రితం';
  }

  @override
  String get oneWeekAgo => '1 వారం క్రితం';

  @override
  String weeksAgo(int count) {
    return '$count వారాల క్రితం';
  }

  @override
  String get oneMonthAgo => '1 నెల క్రితం';

  @override
  String monthsAgo(int count) {
    return '$count నెలల క్రితం';
  }

  @override
  String get issuesCreatedInRepo => 'సమస్యలు మీ డిఫాల్ట్ రిపోజిటరీలో సృష్టించబడతాయి';

  @override
  String get taskIntegrations => 'టాస్క్ ఏకీకరణలు';

  @override
  String get configureSettings => 'సెట్టింగ్‌లను కాన్ఫిగర్ చేయండి';

  @override
  String get completeAuthBrowser =>
      'దయచేసి మీ బ్రౌజర్‌లో ఆధికారాన్ని పూర్తి చేయండి. ఆ తర్వాత అనువర్తనానికి తిరిగి వెళ్లండి.';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName ఆధికారాన్ని ప్రారంభించడానికి విఫలమైంది';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appNameకు కనెక్ట్ చేయండి';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Omi మీ $appName ఖాతాలో టాస్క్‌లను సృష్టించడానికి ఆధికారం ఇవ్వాలి. ఇది ఆధికారం కోసం మీ బ్రౌజర్‌ను తెరుస్తుంది.';
  }

  @override
  String get continueButton => 'కొనసాగించండి';

  @override
  String appIntegration(String appName) {
    return '$appName ఏకీకరణ';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName సహ ఏకీకరణ త్వరలో వస్తుంది! మీకు ఎక్కువ టాస్క్ నిర్వహణ ఎంపికలను తీసుకురావడానికి మేము కठిన పని చేస్తున్నాము.';
  }

  @override
  String get gotIt => 'సరిగ్గా ఉంది';

  @override
  String get tasksExportedOneApp => 'టాస్క్‌లను ఒక సమయంలో ఒక ఆ విషయానికి ఎగుమతి చేయవచ్చు.';

  @override
  String get completeYourUpgrade => 'మీ అపగ్రేడ్‌ను పూర్తి చేయండి';

  @override
  String get importConfiguration => 'ఆకృతిని దిగుమతి చేయండి';

  @override
  String get exportConfiguration => 'ఆకృతిని ఎగుమతి చేయండి';

  @override
  String get bringYourOwn => 'మీ స్వంతమైనవాటిని తీసుకువెళ్లండి';

  @override
  String get payYourSttProvider => 'Omi ను స్వేచ్ఛగా ఉపయోగించండి. మీరు మీ STT ప్రదాతకు నేరుగా చెల్లించండి.';

  @override
  String get freeMinutesMonth => '1,200 ఉచిత నిమిషాలు/నెల చేర్చబడ్డాయి. అসীమితమైన ';

  @override
  String get omiUnlimited => 'Omi అసీమితం';

  @override
  String get hostRequired => 'హోస్ట్ అవసరం';

  @override
  String get validPortRequired => 'చెల్లుబాటు అయ్యే పోర్ట్ అవసరం';

  @override
  String get validWebsocketUrlRequired => 'చెల్లుబాటు అయ్యే WebSocket URL అవసరం (wss://)';

  @override
  String get apiUrlRequired => 'API URL అవసరం';

  @override
  String get apiKeyRequired => 'API కీ అవసరం';

  @override
  String get invalidJsonConfig => 'చెల్లని JSON ఆకృతి';

  @override
  String errorSaving(String error) {
    return 'సేవ చేయడానికి ఎర్రర్: $error';
  }

  @override
  String get configCopiedToClipboard => 'ఆకృతి క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get pasteJsonConfig => 'దయచేసి మీ JSON ఆకృతిని దిగువ పేస్ట్ చేయండి:';

  @override
  String get addApiKeyAfterImport => 'దిగుమతి చేసిన తర్వాత మీరు మీ స్వంత API కీని జోడించాల్సి ఉంటుంది';

  @override
  String get paste => 'పేస్ట్';

  @override
  String get import => 'దిగుమతి';

  @override
  String get invalidProviderInConfig => 'ఆకృతిలో చెల్లని ప్రదాత';

  @override
  String importedConfig(String providerName) {
    return '$providerName ఆకృతిని దిగుమతి చేయబడింది';
  }

  @override
  String invalidJson(String error) {
    return 'చెల్లని JSON: $error';
  }

  @override
  String get provider => 'ప్రదాత';

  @override
  String get live => 'లైవ్';

  @override
  String get onDevice => 'పరికరంపై';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'మీ STT HTTP ఎండ్‌పాయింట్‌ను నమోదు చేయండి';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'మీ లైవ్ STT WebSocket ఎండ్‌పాయింట్‌ను నమోదు చేయండి';

  @override
  String get apiKey => 'API కీ';

  @override
  String get enterApiKey => 'మీ API కీని నమోదు చేయండి';

  @override
  String get storedLocallyNeverShared => 'స్థానికంగా నిల్వ చేయబడిన, ఎప్పుడూ పంచుకోలేదు';

  @override
  String get host => 'హోస్ట్';

  @override
  String get port => 'పోర్ట్';

  @override
  String get advanced => 'అధునాతన';

  @override
  String get configuration => 'ఆకృతి';

  @override
  String get requestConfiguration => 'ఆకృతిని అభ్యర్థించండి';

  @override
  String get responseSchema => 'ప్రతిస్పందన స్కీమా';

  @override
  String get modified => 'సవరించబడింది';

  @override
  String get resetRequestConfig => 'అభ్యర్థన ఆకృతిని డిఫాల్ట్‌కు రీసెట్ చేయండి';

  @override
  String get logs => 'లాగ్‌లు';

  @override
  String get logsCopied => 'లాగ్‌లు కాపీ చేయబడ్డాయి';

  @override
  String get noLogsYet => 'ఇంకా లాగ్‌లు లేవు. కస్టమ్ STT కార్యకలాపాన్ని చూడటానికి రికార్డింగ్ ప్రారంభించండి.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device $reason ఉపయోగిస్తుంది. Omi ఉపయోగించబడుతుంది.';
  }

  @override
  String get omiTranscription => 'Omi ట్రాన్‌స్క్రిప్షన్';

  @override
  String get bestInClassTranscription => 'సున్నా సెట‌అప్‌తో సేల్యులర-గ్రేడ్ ట్రాన్‌స్క్రిప్షన్';

  @override
  String get instantSpeakerLabels => 'తక్షణ స్పీకర్ లేబుల్‌లు';

  @override
  String get languageTranslation => '100+ భాష అనువాదం';

  @override
  String get optimizedForConversation => 'సంభాషణ కోసం ఆప్టిమైజ్ చేయబడింది';

  @override
  String get autoLanguageDetection => 'స్వయంచాలక భాష గుర్తింపు';

  @override
  String get highAccuracy => 'అధిక ఖచ్చితత్వం';

  @override
  String get privacyFirst => 'ప్రైవేసీ మొదట';

  @override
  String get saveChanges => 'మార్పులను సేవ చేయండి';

  @override
  String get resetToDefault => 'డిఫాల్ట్‌కు రీసెట్ చేయండి';

  @override
  String get viewTemplate => 'టెంప్లేట్‌ను చూసుకోండి';

  @override
  String get trySomethingLike => 'ఇలాంటివి ప్రయత్నించండి...';

  @override
  String get tryIt => 'దీన్ని ప్రయత్నించండి';

  @override
  String get creatingPlan => 'ప్లాన్‌ను సృష్టిస్తుంది';

  @override
  String get developingLogic => 'లాజిక్‌ను అభివృద్ధి చేస్తుంది';

  @override
  String get designingApp => 'అనువర్తనాన్ని డిజైన్ చేస్తుంది';

  @override
  String get generatingIconStep => 'చిహ్నాన్ని ఉత్పత్తి చేస్తుంది';

  @override
  String get finalTouches => 'చివరి స్పర్శ';

  @override
  String get processing => 'ప్రక్రియ చేస్తుంది...';

  @override
  String get features => 'లక్షణాలు';

  @override
  String get creatingYourApp => 'మీ అనువర్తనాన్ని సృష్టిస్తుంది...';

  @override
  String get generatingIcon => 'చిహ్నాన్ని ఉత్పత్తి చేస్తుంది...';

  @override
  String get whatShouldWeMake => 'మేము ఏమి తయారు చేయాలి?';

  @override
  String get appName => 'అనువర్తన పేరు';

  @override
  String get description => 'వివరణ';

  @override
  String get publicLabel => 'ప్రజా';

  @override
  String get privateLabel => 'ప్రైవేట్';

  @override
  String get free => 'ఉచితం';

  @override
  String get perMonth => '/ నెల';

  @override
  String get tailoredConversationSummaries => 'రూపొందించిన సంభాషణ సారాంశాలు';

  @override
  String get customChatbotPersonality => 'కస్టమ్ చాట్‌బాట్ వ్యక్తిత్వం';

  @override
  String get makePublic => 'పబ్లిక్ చేయండి';

  @override
  String get anyoneCanDiscover => 'ఎవరైనా మీ అనువర్తనాన్ని కనుగొనవచ్చు';

  @override
  String get onlyYouCanUse => 'మీరు మాత్రమే ఈ అనువర్తనాన్ని ఉపయోగించవచ్చు';

  @override
  String get paidApp => 'చెల్లింపు అనువర్తనం';

  @override
  String get usersPayToUse => 'ఉపయోగకర్తలు మీ అనువర్తనాన్ని ఉపయోగించడానికి చెల్లిస్తారు';

  @override
  String get freeForEveryone => 'ప్రతిఒక్కరి కోసం ఉచితం';

  @override
  String get perMonthLabel => '/ నెల';

  @override
  String get creating => 'సృష్టిస్తుంది...';

  @override
  String get createApp => 'అనువర్తనాన్ని సృష్టించండి';

  @override
  String get searchingForDevices => 'పరికరాల కోసం చేరుస్తుంది...';

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
  String get pairingSuccessful => 'పేరింగ్ విజయవంతం';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch కు కనెక్ట్ చేయడంలో ఎర్రర్: $error';
  }

  @override
  String get dontShowAgain => 'మళ్లీ చూపవద్దు';

  @override
  String get iUnderstand => 'నాకు అర్థమైంది';

  @override
  String get enableBluetooth => 'బ్లూటూత్ ప్రారంభించండి';

  @override
  String get bluetoothNeeded =>
      'మీ ధరించదగిన పరికరానికి కనెక్ట్ చేయడానికి Omi కు బ్లూటూత్ అవసరం. దయచేసి బ్లూటూత్‌ను ప్రారంభించి మళ్లీ ప్రయత్నించండి.';

  @override
  String get contactSupport => 'సపోర్టుకు సంబంధం?';

  @override
  String get connectLater => 'తరువాత కనెక్ట్ చేయండి';

  @override
  String get grantPermissions => 'అనుమతులను ఇవ్వండి';

  @override
  String get backgroundActivity => 'నేపథ్య కార్యకలాపం';

  @override
  String get backgroundActivityDesc => 'Omi ను మెరుగైన స్థిరత్వ కోసం నేపథ్యంలో నడవనివ్వండి';

  @override
  String get locationAccess => 'స్థానం యాక్సెస్';

  @override
  String get locationAccessDesc => 'పూర్ణ అనుభవం కోసం నేపథ్య స్థానాన్ని ప్రారంభించండి';

  @override
  String get notifications => 'నోటిఫికేషన్‌లు';

  @override
  String get notificationsDesc => 'సమాచారం పొందడానికి నోటిఫికేషన్‌లను ప్రారంభించండి';

  @override
  String get locationServiceDisabled => 'స్థానం సేవ నిలిపివేయబడింది';

  @override
  String get locationServiceDisabledDesc =>
      'స్థానం సేవ నిలిపివేయబడింది. దయచేసి సెట్టింగ్‌లు > గోప్యతా & నిరాపత్త > స్థానం సేవలకు వెళ్లి దీన్ని ప్రారంభించండి';

  @override
  String get backgroundLocationDenied => 'నేపథ్య స్థానం యాక్సెస్ నిరాకరించబడింది';

  @override
  String get backgroundLocationDeniedDesc =>
      'దయచేసి పరికరం సెట్టింగ్‌లకు వెళ్లి స్థానం అనుమతిని \"ఎల్లప్పుడూ అనుమతించు\" కు సెట్ చేయండి';

  @override
  String get lovingOmi => 'Omi ని ఇష్టపడుతున్నారా?';

  @override
  String get leaveReviewIos =>
      'App Store లో సమీక్ష ఇవ్వడం ద్వారా మాకు మరిన్ని ప్రజలకు చేరుకోవడానికి సహాయం చేయండి. మీ ఫీడ్‌బ్యాక్ మాకు ప్రపంచానికి అర్థమైనది!';

  @override
  String get leaveReviewAndroid =>
      'Google Play Store లో సమీక్ష ఇవ్వడం ద్వారా మాకు మరిన్ని ప్రజలకు చేరుకోవడానికి సహాయం చేయండి. మీ ఫీడ్‌బ్యాక్ మాకు ప్రపంచానికి అర్థమైనది!';

  @override
  String get rateOnAppStore => 'App Store లో రేట్ చేయండి';

  @override
  String get rateOnGooglePlay => 'Google Play లో రేట్ చేయండి';

  @override
  String get maybeLater => 'బహుశా తర్వాత';

  @override
  String get speechProfileIntro => 'Omi మీ లక్ష్యాలు మరియు మీ గతిని నేర్చుకోవాలి. మీరు దీన్ని తరువాత సవరించగలరు.';

  @override
  String get getStarted => 'ప్రారంభించండి';

  @override
  String get allDone => 'అంతా చేయబడింది!';

  @override
  String get keepGoing => 'కొనసాగండి, మీరు గొప్పగా చేస్తున్నారు';

  @override
  String get skipThisQuestion => 'ఈ ప్రశ్నను దాటవేయండి';

  @override
  String get skipForNow => 'ఈ సమయానికి దాటవేయండి';

  @override
  String get connectionError => 'కనెక్షన్ ఎర్రర్';

  @override
  String get connectionErrorDesc =>
      'సర్వర్‌కు కనెక్ట్ చేయడానికి విఫలమైంది. దయచేసి మీ ఇంటర్నెట్ కనెక్షన్‌ను తనిఖీ చేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get invalidRecordingMultipleSpeakers => 'చెల్లని రికార్డింగ్ గుర్తించబడింది';

  @override
  String get multipleSpeakersDesc =>
      'రికార్డింగ్‌లో బహుళ స్పీకర్‌లు ఉన్నట్లు కనిపిస్తుంది. దయచేసి మీరు నిశ్శబ్ద ప్రదేశంలో ఉన్నారని నిర్ధారించుకోండి మరియు మళ్లీ ప్రయత్నించండి.';

  @override
  String get tooShortDesc => 'తగినంత ఉచ్చారణ గుర్తించబడలేదు. దయచేసి మరిన్ని మాట్లాడండి మరియు మళ్లీ ప్రయత్నించండి.';

  @override
  String get invalidRecordingDesc =>
      'దయచేసి మీరు కనీసం 5 సెకన్లు మరియు 90 కంటే ఎక్కువ కాకుండా మాట్లాడిన నిర్ధారించుకోండి.';

  @override
  String get areYouThere => 'మీరు ఉన్నారా?';

  @override
  String get noSpeechDesc =>
      'మేము ఏ ఉచ్చారణను గుర్తించలేము. దయచేసి కనీసం 10 సెకన్లు మరియు 3 నిమిషాల కంటే ఎక్కువ కాకుండా మాట్లాడిన నిర్ధారించుకోండి.';

  @override
  String get connectionLost => 'కనెక్షన్ కోల్పోయారు';

  @override
  String get connectionLostDesc =>
      'కనెక్షన్ అంతరాయం కలిగింది. దయచేసి మీ ఇంటర్నెట్ కనెక్షన్‌ను తనిఖీ చేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get tryAgain => 'మళ్లీ ప్రయత్నించండి';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass కు కనెక్ట్ చేయండి';

  @override
  String get continueWithoutDevice => 'పరికరం లేకుండా కొనసాగండి';

  @override
  String get permissionsRequired => 'అనుమతులు అవసరం';

  @override
  String get permissionsRequiredDesc =>
      'ఈ అనువర్తనానికి సరిగ్గా పని చేయడానికి బ్లూటూత్ మరియు స్థానం అనుమతులు అవసరం. దయచేసి సెట్టింగ్‌లలో వాటిని ప్రారంభించండి.';

  @override
  String get openSettings => 'సెట్టింగ్‌లను తెరండి';

  @override
  String get wantDifferentName => 'వేరే పేరుతో వెళ్లాలనుకుంటున్నారా?';

  @override
  String get whatsYourName => 'మీ పేరు ఏమిటి?';

  @override
  String get speakTranscribeSummarize => 'మాట్లాడండి. ట్రాన్‌స్క్రిప్ట్ చేయండి. సారాంశం చేయండి.';

  @override
  String get signInWithApple => 'Apple తో సైన్ ఇన్ చేయండి';

  @override
  String get signInWithGoogle => 'Google తో సైన్ ఇన్ చేయండి';

  @override
  String get byContinuingAgree => 'కొనసాగడం ద్వారా, మీరు మా ';

  @override
  String get termsOfUse => 'ఉపయోగ నిబంధనలు';

  @override
  String get omiYourAiCompanion => 'Omi – మీ AI సహచరి';

  @override
  String get captureEveryMoment =>
      'ప్రతి క్షణాన్ని చేపట్టండి. AI ఆధారిత\nసారాంశాలను పొందండి. ఎప్పుడూ నోట్‌లు తీసుకోవద్దు.';

  @override
  String get appleWatchSetup => 'Apple Watch సెటప్';

  @override
  String get permissionRequestedExclaim => 'అనుమతి అభ్యర్థించారు!';

  @override
  String get microphonePermission => 'మైక్రోఫోన్ అనుమతి';

  @override
  String get permissionGrantedNow =>
      'అనుమతి ఇవ్వబడింది! ఇప్పుడు:\n\nమీ గడియారంపై Omi అనువర్తనాన్ని తెరిచి దిగువ \"కొనసాగించండి\" ని నొక్కండి';

  @override
  String get needMicrophonePermission =>
      'మాకు మైక్రోఫోన్ అనుమతి అవసరం.\n\n1. \"అనుమతి ఇవ్వండి\" నొక్కండి\n2. మీ iPhone లో అనుమతించండి\n3. గడియారం అనువర్తనం మూసిపోతుంది\n4. మళ్లీ తెరిచి \"కొనసాగించండి\" నొక్కండి';

  @override
  String get grantPermissionButton => 'అనుమతి ఇవ్వండి';

  @override
  String get needHelp => 'సహాయం అవసరమా?';

  @override
  String get troubleshootingSteps =>
      'సమస్య పరిష్కారం:\n\n1. Omi మీ గడియారంపై ఇన్‌స్టాల్ చేయబడిందని నిర్ధారించుకోండి\n2. మీ గడియారంపై Omi అనువర్తనాన్ని తెరిచి\n3. అనుమతి పాపప్ కోసం చూడండి\n4. అడిగినప్పుడు \"అనుమతించు\" నొక్కండి\n5. మీ గడియారంపై అనువర్తనం మూసిపోతుంది - దీన్ని తిరిగి తెరిచండి\n6. మీ iPhone లో ఫిరి కమ్మండి మరియు \"కొనసాగించండి\" నొక్కండి';

  @override
  String get recordingStartedSuccessfully => 'రికార్డింగ్ విజయవంతంగా ప్రారంభమైంది!';

  @override
  String get permissionNotGrantedYet =>
      'ఇంకా అనుమతి ఇవ్వలేదు. దయచేసి మీరు మీ గడియారంపై మైక్రోఫోన్ ప్రాప్యతను అనుమతించారని మరియు అనువర్తనాన్ని తిరిగి తెరిచారని నిర్ధారించుకోండి.';

  @override
  String errorRequestingPermission(String error) {
    return 'అనుమతిని అభ్యర్థించడంలో ఎర్రర్: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'రికార్డింగ్ ప్రారంభించడంలో ఎర్రర్: $error';
  }

  @override
  String get selectPrimaryLanguage => 'మీ ప్రాధమిక భాషను ఎంచుకోండి';

  @override
  String get languageBenefits =>
      'మరింత ఖచ్చితమైన ట్రాన్‌స్క్రిప్షన్‌లు మరియు ఎంపిక చేసిన అనుభవం కోసం మీ భాష సెట్ చేయండి';

  @override
  String get whatsYourPrimaryLanguage => 'మీ ప్రాధమిక భాష ఏమిటి?';

  @override
  String get selectYourLanguage => 'మీ భాషను ఎంచుకోండి';

  @override
  String get personalGrowthJourney => 'AI తో మీ ఏకస్వ వృద్ధి ఉపయోగం ఇది మీ ప్రతిదాన్ని విని నిర్ణయిస్తుంది.';

  @override
  String get actionItemsTitle => 'చేయవలసిన పనులు';

  @override
  String get actionItemsDescription =>
      'సవరించడానికి నొక్కండి • ఎంచుకోవటానికి ఎక్కువ సమయం నొక్కండి • చర్యలకు స్వైప్ చేయండి';

  @override
  String get tabToDo => 'చేయవలసిన పని';

  @override
  String get tabDone => 'సంపూర్ణమైంది';

  @override
  String get tabOld => 'పాతది';

  @override
  String get emptyTodoMessage => '🎉 పూర్తి సమీకరణ!\nఎటువంటి ఆగిపోయిన చర్య సరిపోలేదు';

  @override
  String get emptyDoneMessage => 'ఇంకా పూర్తి చేసిన అంశాలు లేవు';

  @override
  String get emptyOldMessage => '✅ పాత పనులు లేవు';

  @override
  String get noItems => 'అంశాలు లేవు';

  @override
  String get actionItemMarkedIncomplete => 'చర్య చర్య అసంపూర్ణంగా గుర్తించబడింది';

  @override
  String get actionItemCompleted => 'చర్య సంపూర్ణమైంది';

  @override
  String get deleteActionItemTitle => 'చర్య చర్యను తొలగించండి';

  @override
  String get deleteActionItemMessage => 'మీరు ఈ చర్య చర్యను తొలగించాలని నిర్ణయం చేసారా?';

  @override
  String get deleteSelectedItemsTitle => 'ఎంచుకున్న అంశాలను తొలగించండి';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'మీరు $count ఎంచుకున్న చర్య చర్య$sను తొలగించాలని నిర్ణయం చేసారా?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'చర్య చర్య \"$description\" తొలగించబడింది';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count చర్య చర్య$s తొలగించబడ్డాయి';
  }

  @override
  String get failedToDeleteItem => 'చర్య చర్యను తొలగించడానికి విఫలమైంది';

  @override
  String get failedToDeleteItems => 'అంశాలను తొలగించడానికి విఫలమైంది';

  @override
  String get failedToDeleteSomeItems => 'కొన్ని అంశాలను తొలగించడానికి విఫలమైంది';

  @override
  String get welcomeActionItemsTitle => 'చర్య చర్యల కోసం సిద్ధమైంది';

  @override
  String get welcomeActionItemsDescription =>
      'మీ AI స్వయంచాలకంగా మీ సంభాషణల నుండి పనులను మరియు చేయవలసిన పనులను సంగ్రహిస్తుంది. సృష్టించినప్పుడు వారు ఇక్కడ కనిపిస్తారు.';

  @override
  String get autoExtractionFeature => 'సంభాషణల నుండి స్వయంచాలకంగా సంగ్రహించబడింది';

  @override
  String get editSwipeFeature => 'సవరించడానికి నొక్కండి, పూర్తి చేయడానికి లేదా తొలగించడానికి స్వైప్ చేయండి';

  @override
  String itemsSelected(int count) {
    return '$count ఎంచుకున్నవి';
  }

  @override
  String get selectAll => 'అన్నిటిని ఎంచుకోండి';

  @override
  String get deleteSelected => 'ఎంచుకున్నవిటిని తొలగించండి';

  @override
  String get searchMemories => 'జ్ఞాపకాలను చేరండి...';

  @override
  String get memoryDeleted => 'జ్ఞాపకం తొలగించబడింది.';

  @override
  String get undo => 'మరలుచేయండి';

  @override
  String get noMemoriesYet => '🧠 ఇంకా జ్ఞాపకాలు లేవు';

  @override
  String get noAutoMemories => 'ఇంకా స్వయంచాలక-సంగ్రహించిన జ్ఞాపకాలు లేవు';

  @override
  String get noManualMemories => 'ఇంకా సానుకూల జ్ఞాపకాలు లేవు';

  @override
  String get noMemoriesInCategories => 'ఈ వర్గాలలో జ్ఞాపకాలు లేవు';

  @override
  String get noMemoriesFound => '🔍 జ్ఞాపకాలు కనుగొనబడలేదు';

  @override
  String get addFirstMemory => 'మీ మొదటి జ్ఞాపకాన్ని జోడించండి';

  @override
  String get clearMemoryTitle => 'Omi యొక్క జ్ఞాపకాన్ని సరిచేయండి';

  @override
  String get clearMemoryMessage => 'మీరు Omi యొక్క జ్ఞాపకాన్ని సరిచేయాలని నిర్ణయం చేసారా? ఈ చర్య చేయబడదు.';

  @override
  String get clearMemoryButton => 'జ్ఞాపకాన్ని సరిచేయండి';

  @override
  String get memoryClearedSuccess => 'మీ గురించిన Omi యొక్క జ్ఞాపకం సరిచేయబడింది';

  @override
  String get noMemoriesToDelete => 'తొలగించడానికి జ్ఞాపకాలు లేవు';

  @override
  String get createMemoryTooltip => 'కొత్త జ్ఞాపకం సృష్టించండి';

  @override
  String get createActionItemTooltip => 'కొత్త చర్య చర్యను సృష్టించండి';

  @override
  String get memoryManagement => 'జ్ఞాపక నిర్వహణ';

  @override
  String get filterMemories => 'జ్ఞాపకాలను ఫిల్టర్ చేయండి';

  @override
  String totalMemoriesCount(int count) {
    return 'మీకు $count సర్వ జ్ఞాపకాలు ఉన్నాయి';
  }

  @override
  String get publicMemories => 'ప్రజా జ్ఞాపకాలు';

  @override
  String get privateMemories => 'ప్రైవేట్ జ్ఞాపకాలు';

  @override
  String get makeAllPrivate => 'అన్ని జ్ఞాపకాలను ప్రైవేట్ చేయండి';

  @override
  String get makeAllPublic => 'అన్ని జ్ఞాపకాలను ప్రజా చేయండి';

  @override
  String get deleteAllMemories => 'అన్ని జ్ఞాపకాలను తొలగించండి';

  @override
  String get allMemoriesPrivateResult => 'అన్ని జ్ఞాపకాలు ఇప్పుడు ప్రైవేట్';

  @override
  String get allMemoriesPublicResult => 'అన్ని జ్ఞాపకాలు ఇప్పుడు ప్రజా';

  @override
  String get newMemory => '✨ కొత్త జ్ఞాపకం';

  @override
  String get editMemory => '✏️ జ్ఞాపకం సవరించండి';

  @override
  String get memoryContentHint => 'నేను ice cream తినడానికి ఇష్టపడతాను...';

  @override
  String get failedToSaveMemory => 'సేవ చేయడానికి విఫలమైంది. దయచేసి మీ కనెక్షన్‌ను తనిఖీ చేయండి.';

  @override
  String get saveMemory => 'జ్ఞాపకాన్ని సేవ చేయండి';

  @override
  String get retry => 'మళ్లీ ప్రయత్నించండి';

  @override
  String get createActionItem => 'చర్య చర్యను సృష్టించండి';

  @override
  String get editActionItem => 'చర్య చర్య సవరించండి';

  @override
  String get actionItemDescriptionHint => 'ఏమి చేయవలసి ఉంది?';

  @override
  String get actionItemDescriptionEmpty => 'చర్య చర్య వివరణ ఖాళీగా ఉండకూడదు.';

  @override
  String get actionItemUpdated => 'చర్య చర్య నవీకరించబడింది';

  @override
  String get failedToUpdateActionItem => 'చర్య చర్యను నవీకరించడానికి విఫలమైంది';

  @override
  String get actionItemCreated => 'చర్య చర్య సృష్టించబడింది';

  @override
  String get failedToCreateActionItem => 'చర్య చర్యను సృష్టించడానికి విఫలమైంది';

  @override
  String get dueDate => 'నిర్ణితమైన తేదీ';

  @override
  String get time => 'సమయం';

  @override
  String get addDueDate => 'నిర్ణితమైన తేదీని జోడించండి';

  @override
  String get pressDoneToSave => 'సేవ చేయడానికి చేయబడినది నొక్కండి';

  @override
  String get pressDoneToCreate => 'సృష్టించడానికి చేయబడినది నొక్కండి';

  @override
  String get filterAll => 'అన్నీ';

  @override
  String get filterSystem => 'మీ గురించి';

  @override
  String get filterInteresting => 'అంతర్దృష్టులు';

  @override
  String get filterManual => 'సానుకూల';

  @override
  String get completed => 'సంపూర్ణమైంది';

  @override
  String get markComplete => 'సంపూర్ణ గా గుర్తించండి';

  @override
  String get actionItemDeleted => 'చర్య చర్య తొలగించబడింది';

  @override
  String get failedToDeleteActionItem => 'చర్య చర్యను తొలగించడానికి విఫలమైంది';

  @override
  String get deleteActionItemConfirmTitle => 'చర్య చర్యను తొలగించండి';

  @override
  String get deleteActionItemConfirmMessage => 'మీరు ఈ చర్య చర్యను తొలగించాలని నిర్ణయం చేసారా?';

  @override
  String get appLanguage => 'ఆ విషయానికి సంబంధించిన భాష';

  @override
  String get appInterfaceSectionTitle => 'ఆ విషయానికి సంబంధించిన ఇంటర్ఫేస్';

  @override
  String get speechTranscriptionSectionTitle => 'ఉచ్చారణ & ట్రాన్‌స్క్రిప్షన్';

  @override
  String get languageSettingsHelperText =>
      'ఆ విషయానికి సంబంధించిన భాష మెనూలు మరియు బటన్‌లను మార్చుతుంది. ఉచ్చారణ భాష మీ రికార్డింగ్‌లను ఎలా ట్రాన్‌స్క్రిప్ట్ చేయాలో ప్రభావితం చేస్తుంది.';

  @override
  String get translationNotice => 'అనువాద సూచన';

  @override
  String get translationNoticeMessage =>
      'Omi సంభాషణలను మీ ప్రాధమిక భాషకు అనువదిస్తుంది. సెట్టింగ్‌లు → ప్రొఫైల్‌లలో ఏ సమయానికీ దీన్ని నవీకరించండి.';

  @override
  String get pleaseCheckInternetConnection => 'దయచేసి మీ ఇంటర్నెట్ కనెక్షన్‌ను తనిఖీ చేసి మళ్లీ ప్రయత్నించండి';

  @override
  String get pleaseSelectReason => 'దయచేసి కారణం ఎంచుకోండి';

  @override
  String get tellUsMoreWhatWentWrong => 'విపరీతమైనది గురించి మాకు మరిన్ని చెప్పండి...';

  @override
  String get selectText => 'టెక్ష్ట్‌ను ఎంచుకోండి';

  @override
  String maximumGoalsAllowed(int count) {
    return 'గరిష్ట $count లక్ష్యాలు అనుమతించబడ్డాయి';
  }

  @override
  String get conversationCannotBeMerged => 'ఈ సంభాషణ విలీనం చేయబడదు (లాక్ చేయబడిన లేదా ఇప్పటికే విలీనం చేస్తుంది)';

  @override
  String get pleaseEnterFolderName => 'దయచేసి ఫోల్డర్ పేరు నమోదు చేయండి';

  @override
  String get failedToCreateFolder => 'ఫోల్డర్ సృష్టించడానికి విఫలమైంది';

  @override
  String get failedToUpdateFolder => 'ఫోల్డర్ నవీకరించడానికి విఫలమైంది';

  @override
  String get folderName => 'ఫోల్డర్ పేరు';

  @override
  String get descriptionOptional => 'వివరణ (ఐచ్ఛికం)';

  @override
  String get failedToDeleteFolder => 'ఫోల్డర్‌ను తొలగించడం విఫలమైంది';

  @override
  String get editFolder => 'ఫోల్డర్‌ను సవరించండి';

  @override
  String get deleteFolder => 'ఫోల్డర్‌ను తొలగించండి';

  @override
  String get transcriptCopiedToClipboard => 'ట్రాన్‌స్క్రిప్ట్ క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get summaryCopiedToClipboard => 'సారాంశం క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get conversationUrlCouldNotBeShared => 'సంభాషణ URL షేర్ చేయబడలేదు.';

  @override
  String get urlCopiedToClipboard => 'URL క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get exportTranscript => 'ట్రాన్‌స్క్రిప్ట్ ఎగుమతి చేయండి';

  @override
  String get exportSummary => 'సారాంశం ఎగుమతి చేయండి';

  @override
  String get exportButton => 'ఎగుమతి';

  @override
  String get actionItemsCopiedToClipboard => 'కార్యాచరణ అంశాలు క్లిప్‌బోర్డ్‌కు కాపీ చేయబడ్డాయి';

  @override
  String get summarize => 'సంక్ష్ప్తీకరించండి';

  @override
  String get generateSummary => 'సారాంశం ఉత్పత్తి చేయండి';

  @override
  String get conversationNotFoundOrDeleted => 'సంభాషణ కనుగొనబడలేదు లేదా తొలగించబడింది';

  @override
  String get deleteMemory => 'స్మృతి తొలగించండి';

  @override
  String get thisActionCannotBeUndone => 'ఈ చర్యను రద్దు చేయలేము.';

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
  String get noMemoriesInCategory => 'ఈ వర్గంలో ఇంకా స్మృతులు లేవు';

  @override
  String get addYourFirstMemory => 'మీ మొదటి స్మృతిని జోడించండి';

  @override
  String get firmwareDisconnectUsb => 'USB సংযోగం తెంచండి';

  @override
  String get firmwareUsbWarning => 'అపడేట్‌ల సమయంలో USB కనెక్션్ మీ డివైస్‌ను నష్టపరచవచ్చు.';

  @override
  String get firmwareBatteryAbove15 => '15% కంటే ఎక్కువ బ్యాటరీ';

  @override
  String get firmwareEnsureBattery => 'మీ డివైస్‌కు 15% బ్యాటరీ ఉందని నిర్ధారించుకోండి.';

  @override
  String get firmwareStableConnection => 'స్థిర కనెక్షన్';

  @override
  String get firmwareConnectWifi => 'WiFi లేదా సెల్యులార్‌కి కనెక్ట్ చేయండి.';

  @override
  String failedToStartUpdate(String error) {
    return 'అపడేట్ ప్రారంభించడం విఫలమైంది: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'అపడేట్ ముందు, నిశ్చయం చేయుకోండి:';

  @override
  String get confirmed => 'నిర్ధారిత!';

  @override
  String get release => 'విడుదల';

  @override
  String get slideToUpdate => 'అపడేట్ చేయడానికి స్లైడ్ చేయండి';

  @override
  String copiedToClipboard(String title) {
    return '$title క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';
  }

  @override
  String get batteryLevel => 'బ్యాటరీ స్థాయి';

  @override
  String get charging => 'ఛార్జ్ అవుతోంది';

  @override
  String get productUpdate => 'ఉత్పత్తి అపడేట్';

  @override
  String get offline => 'ఆఫ్‌లైన్';

  @override
  String get available => 'అందుబాటులో ఉంది';

  @override
  String get unpairDeviceDialogTitle => 'డివైస్ జత తెంచండి';

  @override
  String get unpairDeviceDialogMessage =>
      'ఇది డివైస్‌ను జత తీసి మరొక ఫోన్‌కు కనెక్ట్ చేయవచ్చు. ప్రక్రియను పూర్తి చేయడానికి మీరు సెట్టింగ్‌లు > బ్లూటూత్‌కు వెళ్లి డివైస్‌ను మర్చిపోవాలి.';

  @override
  String get unpair => 'జత తెంచండి';

  @override
  String get unpairAndForgetDevice => 'డివైస్‌ను జత తీసి మర్చిపోండి';

  @override
  String get unknownDevice => 'తెలియని';

  @override
  String get unknown => 'తెలియనిది';

  @override
  String get productName => 'ఉత్పత్తి పేరు';

  @override
  String get serialNumber => 'సీరియల్ నంబర్';

  @override
  String get connected => 'సংయుక్త';

  @override
  String get privacyPolicyTitle => 'గోప్యతా విధానం';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label కాపీ చేయబడింది';
  }

  @override
  String get noApiKeysYet => 'ఇంకా API కీలు లేవు';

  @override
  String get createKeyToGetStarted => 'ప్రారంభించడానికి కీ సృష్టించండి';

  @override
  String get configureSttProvider => 'STT ప్రదాతను కాన్ఫిగర్ చేయండి';

  @override
  String get setWhenConversationsAutoEnd => 'సంభాషణలు స్వయంచాలకంగా ఎప్పుడు ముగియాలో సెట్ చేయండి';

  @override
  String get importDataFromOtherSources => 'ఇతర మూలాల నుండి డేటా దిగుమతి చేయండి';

  @override
  String get debugAndDiagnostics => 'డీబగ్ & నిర్ధారణ';

  @override
  String get autoDeletesAfter3Days => '3 రోజుల తర్వాత స్వయంచాలకంగా తొలగించబడుతుంది.';

  @override
  String get helpsDiagnoseIssues => 'సమస్యలను నిర్ధారించడానికి సహాయం చేస్తుంది';

  @override
  String get exportStartedMessage => 'ఎగుమతి ప్రారంభమైంది. ఇది కొన్ని సెకన్లు పట్టవచ్చు...';

  @override
  String get exportConversationsToJson => 'సంభాషణలను JSON ఫైల్‌కు ఎగుమతి చేయండి';

  @override
  String get knowledgeGraphDeletedSuccess => 'నాలెడ్జ్ గ్రాఫ్ విజయవంతంగా తొలగించబడింది';

  @override
  String failedToDeleteGraph(String error) {
    return 'గ్రాఫ్ తొలగించడం విఫలమైంది: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'సమస్త నోడ్‌లు మరియు కనెక్షన్‌లను క్లియర్ చేయండి';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.json కు జోడించండి';

  @override
  String get connectAiAssistantsToData => 'AI సహాయకులను మీ డేటాకు కనెక్ట్ చేయండి';

  @override
  String get useYourMcpApiKey => 'మీ MCP API కీని ఉపయోగించండి';

  @override
  String get realTimeTranscript => 'రియల్-టైమ్ ట్రాన్‌స్క్రిప్ట్';

  @override
  String get experimental => 'ప్రయోగమూలక';

  @override
  String get transcriptionDiagnostics => 'ట్రాన్‌స్క్రిప్షన్ నిర్ధారణ';

  @override
  String get detailedDiagnosticMessages => 'వివరణాత్మక నిర్ధారణ సందేశాలు';

  @override
  String get autoCreateSpeakers => 'స్పీకర్‌లను స్వయంచాలకంగా సృష్టించండి';

  @override
  String get autoCreateWhenNameDetected => 'పేరు కనుగొనబడినప్పుడు స్వయంచాలకంగా సృష్టించండి';

  @override
  String get followUpQuestions => 'అనుసరణ ప్రశ్నలు';

  @override
  String get suggestQuestionsAfterConversations => 'సంభాషణల తర్వాత ప్రశ్నలను సూచించండి';

  @override
  String get goalTracker => 'లక్ష్య ట్రాకర్';

  @override
  String get trackPersonalGoalsOnHomepage => 'హోమ్‌పేజ్‌లో వ్యక్తిగత లక్ష్యాలను ట్రాక్ చేయండి';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'కార్యాచరణ అంశం వివరణ ఖాళీగా ఉండకూడదు';

  @override
  String get saved => 'సేవ్ చేయబడింది';

  @override
  String get overdue => 'మెరుగుపరచాల్సిన';

  @override
  String get failedToUpdateDueDate => 'డ్యూ డేట్ అపडేట్ చేయడం విఫలమైంది';

  @override
  String get markIncomplete => 'అసంపూర్ణగా గుర్తించండి';

  @override
  String get editDueDate => 'డ్యూ డేట్‌ను సవరించండి';

  @override
  String get setDueDate => 'డ్యూ డేట్‌ను సెట్ చేయండి';

  @override
  String get clearDueDate => 'డ్యూ డేట్‌ను క్లియర్ చేయండి';

  @override
  String get failedToClearDueDate => 'డ్యూ డేట్ క్లియర్ చేయడం విఫలమైంది';

  @override
  String get mondayAbbr => 'సోమ';

  @override
  String get tuesdayAbbr => 'మంగళ';

  @override
  String get wednesdayAbbr => 'బుధ';

  @override
  String get thursdayAbbr => 'గురు';

  @override
  String get fridayAbbr => 'శుక్ర';

  @override
  String get saturdayAbbr => 'శని';

  @override
  String get sundayAbbr => 'ఆది';

  @override
  String get howDoesItWork => 'ఇది ఎలా పనిచేస్తుంది?';

  @override
  String get sdCardSyncDescription => 'SD కార్డ్ సింక్ మీ SD కార్డ్‌ నుండి మీ స్మృతులను అ్యాప్‌కు దిగుమతి చేస్తుంది';

  @override
  String get checksForAudioFiles => 'SD కార్డ్‌లో ఆడియో ఫైల్‌ల కోసం చేకూడుతుంది';

  @override
  String get omiSyncsAudioFiles => 'Omi అప్పుడు ఆడియో ఫైల్‌లను సర్వర్‌తో సింక్ చేస్తుంది';

  @override
  String get serverProcessesAudio => 'సర్వర్ ఆడియో ఫైల్‌లను ప్రక్రియ చేస్తుంది మరియు స్మృతులను సృష్టిస్తుంది';

  @override
  String get youreAllSet => 'మీరు సిద్ధంగా ఉన్నారు!';

  @override
  String get welcomeToOmiDescription =>
      'Omi కు స్వాగతం! మీ AI సঙ్గి సంభాషణలు, పనులు మరియు మరిన్నింటితో మీకు సహాయ చేయడానికి సిద్ధంగా ఉంది.';

  @override
  String get startUsingOmi => 'Omi ఉపయోగం ప్రారంభించండి';

  @override
  String get back => 'వెనుక';

  @override
  String get keyboardShortcuts => 'కీబోర్డ్ సత్వరమార్గాలు';

  @override
  String get toggleControlBar => 'నియంత్రణ బార్‌ను టోగల్ చేయండి';

  @override
  String get pressKeys => 'కీలను నొక్కండి...';

  @override
  String get cmdRequired => '⌘ అవసరం';

  @override
  String get invalidKey => 'చెల్లని కీ';

  @override
  String get space => 'స్థలం';

  @override
  String get search => 'శోధించండి';

  @override
  String get searchPlaceholder => 'శోధించండి...';

  @override
  String get untitledConversation => 'శీర్షిక లేని సంభాషణ';

  @override
  String countRemaining(String count) {
    return '$count మిగిలి ఉన్నాయి';
  }

  @override
  String get addGoal => 'లక్ష్యం జోడించండి';

  @override
  String get editGoal => 'లక్ష్యం సవరించండి';

  @override
  String get icon => 'చిహ్నం';

  @override
  String get goalTitle => 'లక్ష్య శీర్షిక';

  @override
  String get current => 'ప్రస్తుతం';

  @override
  String get target => 'లక్ష్యం';

  @override
  String get saveGoal => 'సేవ్ చేయండి';

  @override
  String get goals => 'లక్ష్యాలు';

  @override
  String get tapToAddGoal => 'లక్ష్యం జోడించడానికి నొక్కండి';

  @override
  String welcomeBack(String name) {
    return '$name, స్వాగతం';
  }

  @override
  String get yourConversations => 'మీ సంభాషణలు';

  @override
  String get reviewAndManageConversations => 'మీ సంపాదించిన సంభాషణలను సమీక్షించండి మరియు నిర్వహించండి';

  @override
  String get startCapturingConversations =>
      'మీ Omi డివైస్‌తో సంభాషణలను సంపాదించడం ప్రారంభించండి వాటిని ఇక్కడ చూడటానికి.';

  @override
  String get useMobileAppToCapture => 'ఆడియో సంపాదించడానికి మీ మొబైల్ అ్యాప్ ఉపయోగించండి';

  @override
  String get conversationsProcessedAutomatically => 'సంభాషణలు స్వయంచాలకంగా ప్రక్రియ చేయబడతాయి';

  @override
  String get getInsightsInstantly => 'తక్షణమే అంతర్దృష్టులు మరియు సారాంశాలను పొందండి';

  @override
  String get showAll => 'అందరూ చూపించు';

  @override
  String get noTasksForToday => 'ఈ రోజుకు పనులు లేవు.\nOmi నుండి మరిన్ని పనులను అడగండి లేదా మానవీయంగా సృష్టించండి.';

  @override
  String get dailyScore => 'రోజువారీ స్కోర్';

  @override
  String get dailyScoreDescription => 'నిర్వాహణపై మీకు ভালోভాবে\nఫోకస్ చేయడానికి స్కోర్.';

  @override
  String get searchResults => 'శోధన ఫలితాలు';

  @override
  String get actionItems => 'కార్యాచరణ అంశాలు';

  @override
  String get tasksToday => 'ఈ రోజు';

  @override
  String get tasksTomorrow => 'రేపు';

  @override
  String get tasksNoDeadline => 'డెడ్‌లైన్ లేదు';

  @override
  String get tasksLater => 'తరువాత';

  @override
  String get loadingTasks => 'పనులు లోడ్ చేస్తున్నాయి...';

  @override
  String get tasks => 'పనులు';

  @override
  String get swipeTasksToIndent => 'పనులను ఇన్‌డెంట్ చేయడానికి స్వైప్ చేయండి, వర్గాల మధ్య లాగండి';

  @override
  String get create => 'సృష్టించండి';

  @override
  String get noTasksYet => 'ఇంకా పనులు లేవు';

  @override
  String get tasksFromConversationsWillAppear =>
      'మీ సంభాషణల నుండి పనులు ఇక్కడ కనిపిస్తాయి.\nఒకటిని మానవీయంగా జోడించడానికి సృష్టించుకు నొక్కండి.';

  @override
  String get monthJan => 'జన';

  @override
  String get monthFeb => 'ఫిబ్ర';

  @override
  String get monthMar => 'మార్చ';

  @override
  String get monthApr => 'ఏప్రిల';

  @override
  String get monthMay => 'మే';

  @override
  String get monthJun => 'జూన';

  @override
  String get monthJul => 'జూలై';

  @override
  String get monthAug => 'ఆగ';

  @override
  String get monthSep => 'సెప్ట';

  @override
  String get monthOct => 'అక్టో';

  @override
  String get monthNov => 'నవ';

  @override
  String get monthDec => 'డిసెం';

  @override
  String get timePM => 'సాయంత్రం';

  @override
  String get timeAM => 'ఉదయం';

  @override
  String get actionItemUpdatedSuccessfully => 'కార్యాచరణ అంశం విజయవంతంగా అపડేట్ చేయబడింది';

  @override
  String get actionItemCreatedSuccessfully => 'కార్యాచరణ అంశం విజయవంతంగా సృష్టించబడింది';

  @override
  String get actionItemDeletedSuccessfully => 'కార్యాచరణ అంశం విజయవంతంగా తొలగించబడింది';

  @override
  String get deleteActionItem => 'కార్యాచరణ అంశం తొలగించండి';

  @override
  String get deleteActionItemConfirmation =>
      'ఈ కార్యాచరణ అంశాన్ని తొలగించాలని మీరు నిశ్చితమైనారా? ఈ చర్యను రద్దు చేయలేము.';

  @override
  String get enterActionItemDescription => 'కార్యాచరణ అంశం వివరణ ప్రవేశించండి...';

  @override
  String get markAsCompleted => 'పూర్తిగా గుర్తించండి';

  @override
  String get setDueDateAndTime => 'డ్యూ తేదీ మరియు సమయం సెట్ చేయండి';

  @override
  String get reloadingApps => 'అ్యాప్‌లు తిరిగి లోడ్ చేస్తున్నాయి...';

  @override
  String get loadingApps => 'అ్యాప్‌లు లోడ్ చేస్తున్నాయి...';

  @override
  String get browseInstallCreateApps => 'అ్యాప్‌లను బ్రౌజ్ చేయండి, ఇన్‌స్టాల్ చేయండి మరియు సృష్టించండి';

  @override
  String get all => 'అందరూ';

  @override
  String get open => 'తెరవండి';

  @override
  String get install => 'ఇన్‌స్టాల్ చేయండి';

  @override
  String get noAppsAvailable => 'అ్యాప్‌లు అందుబాటులో లేవు';

  @override
  String get unableToLoadApps => 'అ్యాప్‌లను లోడ్ చేయడానికి సక్షమం కాదు';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'మీ శోధన నిబంధనలు లేదా ఫిల్టర్‌లను సర్దబmylni చేయడానికి ప్రయత్నించండి';

  @override
  String get checkBackLaterForNewApps => 'నতून అ్యాప్‌ల కోసం తర్వాత తిరిగి చెక్ చేయండి';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'మీ ఇంటర్నెట్ కనెక్షన్‌ను చెక్ చేయండి మరియు మళ్లీ ప్రయత్నించండి';

  @override
  String get createNewApp => 'నూతన అ్యాప్ సృష్టించండి';

  @override
  String get buildSubmitCustomOmiApp => 'మీ కస్టమ్ Omi అ్యాప్‌ని నిర్మించండి మరియు సమర్పించండి';

  @override
  String get submittingYourApp => 'మీ అ్యాప్‌ను సమర్పిస్తున్నాయి...';

  @override
  String get preparingFormForYou => 'మీ కోసం ఫారమ్‌ను సిద్ధం చేస్తున్నాయి...';

  @override
  String get appDetails => 'అ్యాప్ వివరాలు';

  @override
  String get paymentDetails => 'చెల్లింపు వివరాలు';

  @override
  String get previewAndScreenshots => 'ప్రివ్యూ మరియు స్క్రీన్‌షాట్‌లు';

  @override
  String get appCapabilities => 'అ్యాప్ సామర్థ్యాలు';

  @override
  String get aiPrompts => 'AI సూచనలు';

  @override
  String get chatPrompt => 'చాట్ సూచన';

  @override
  String get chatPromptPlaceholder =>
      'మీరు అద్భుత అ్యాప్‌ ఉన్నారు, మీ ఉద్యోగం వినియోగదారు ప్రశ్నలకు ప్రతిస్పందించడం మరియు వారిని మంచిదనిపిస్తూ చేయడం...';

  @override
  String get conversationPrompt => 'సంభాషణ సూచన';

  @override
  String get conversationPromptPlaceholder =>
      'మీరు అద్భుత అ్యాప్‌ ఉన్నారు, మీకు సంభాషణ ట్రాన్‌స్క్రిప్ట్ మరియు సారాంశం ఇవ్వబడుతుంది...';

  @override
  String get notificationScopes => 'నోటిఫికేషన్ స్కోప్‌లు';

  @override
  String get appPrivacyAndTerms => 'అ్యాప్ గోప్యతా మరియు నిబంధనలు';

  @override
  String get makeMyAppPublic => 'నా అ్యాప్‌ను సార్వजనిక చేయండి';

  @override
  String get submitAppTermsAgreement =>
      'ఈ అ్యాప్‌ను సమర్పించడం ద్వారా, నేను Omi AI సేవా నిబంధనలు మరియు గోప్యతా విధానానికి అంగీకరిస్తున్నాను';

  @override
  String get submitApp => 'అ్యాప్ సమర్పించండి';

  @override
  String get needHelpGettingStarted => 'ప్రారంభించడానికి సహాయం అవసరమేనా?';

  @override
  String get clickHereForAppBuildingGuides => 'అ్యాప్ నిర్మాణ గైడ్‌లు మరియు డాక్యుమెంటేషన్ కోసం ఇక్కడ నొక్కండి';

  @override
  String get submitAppQuestion => 'అ్యాప్ సమర్పించాలా?';

  @override
  String get submitAppPublicDescription =>
      'మీ అ్యాప్ సమీక్షించబడుతుంది మరియు సార్వజనికంగా చేయబడుతుంది. సమీక్ష సమయంలో కూడా మీరు దీనిని తక్షణమే ఉపయోగించడం ప్రారంభించవచ్చు!';

  @override
  String get submitAppPrivateDescription =>
      'మీ అ్యాప్ సమీక్షించబడుతుంది మరియు మీకు ఖాగితిగా అందుబాటులోకి వస్తుంది. సమీక్ష సమయంలో కూడా మీరు దీనిని తక్షణమే ఉపయోగించడం ప్రారంభించవచ్చు!';

  @override
  String get startEarning => 'సంపాదించడం ప్రారంభించండి! 💰';

  @override
  String get connectStripeOrPayPal => 'మీ అ్యాప్ కోసం చెల్లింపులను అందుకోవడానికి Stripe లేదా PayPal కనెక్ట్ చేయండి.';

  @override
  String get connectNow => 'ఇప్పుడు కనెక్ట్ చేయండి';

  @override
  String get installsCount => 'ఇన్‌స్టాల్‌లు';

  @override
  String get uninstallApp => 'అ్యాప్ అన్‌ఇన్‌స్టాల్ చేయండి';

  @override
  String get subscribe => 'సభ్యత్వం';

  @override
  String get dataAccessNotice => 'డేటా యాక్సెస్ నోటిస్';

  @override
  String get dataAccessWarning =>
      'ఈ అ్యాప్ మీ డేటాకు ప్రాప్యత కలిగి ఉంటుంది. Omi AI ఈ అ్యాప్ ద్వారా మీ డేటా ఎలా ఉపయోగించబడుతుంది, సవరించబడుతుంది లేదా తొలగించబడుతుంది చేత్వం కోసం బాధ్యత వహించదు';

  @override
  String get installApp => 'అ్యాప్ ఇన్‌స్టాల్ చేయండి';

  @override
  String get betaTesterNotice =>
      'మీరు ఈ అ్యాప్ కోసం బీటా టెస్టర్. ఇది ఇంకా సార్వజనిక కాదు. ఇది ఆమోదించినపుడు సార్వజనికం అవుతుంది.';

  @override
  String get appUnderReviewOwner =>
      'మీ అ్యాప్ సమీక్షలో ఉంది మరియు మీకు మాత్రమే కనిపిస్తుంది. ఇది ఆమోదించినపుడు సార్వజనికం అవుతుంది.';

  @override
  String get appRejectedNotice =>
      'మీ అ్యాప్ తిరస్కరించబడింది. దయచేసి అ్యాప్ వివరాలను నవీకరించండి మరియు సమీక్ష కోసం మళ్లీ సమర్పించండి.';

  @override
  String get setupSteps => 'సెటప్ దశలు';

  @override
  String get setupInstructions => 'సెటప్ సూచనలు';

  @override
  String get integrationInstructions => 'ఏకీకరణ సూచనలు';

  @override
  String get preview => 'ప్రివ్యూ';

  @override
  String get aboutTheApp => 'అ్యాప్ గురించి';

  @override
  String get chatPersonality => 'చాట్ వ్యక్తిత్వం';

  @override
  String get ratingsAndReviews => 'రేటింగ్‌లు & సమీక్షలు';

  @override
  String get noRatings => 'రేటింగ్‌లు లేవు';

  @override
  String ratingsCount(String count) {
    return '$count+ రేటింగ్‌లు';
  }

  @override
  String get errorActivatingApp => 'అ్యాప్ సక్రియం చేయడంలో లోపం';

  @override
  String get integrationSetupRequired => 'ఇది ఏకీకరణ అ్యాప్‌ అయితే, సెటప్ పూర్తిగా ఉందని నిర్ధారించుకోండి.';

  @override
  String get installed => 'ఇన్‌స్టాల్ చేయబడింది';

  @override
  String get appIdLabel => 'అ్యాప్ ID';

  @override
  String get appNameLabel => 'అ్యాప్ పేరు';

  @override
  String get appNamePlaceholder => 'నా అద్భుత అ్యాప్';

  @override
  String get pleaseEnterAppName => 'దయచేసి అ్యాప్ పేరును ప్రవేశించండి';

  @override
  String get categoryLabel => 'వర్గం';

  @override
  String get selectCategory => 'వర్గం ఎంచుకోండి';

  @override
  String get descriptionLabel => 'వివరణ';

  @override
  String get appDescriptionPlaceholder =>
      'నా అద్భుత అ్యాప్ అద్భుత విషయాలు చేసే గొప్ప అ్యాప్. ఇది ఎప్పుడూ గొప్ప అ్యాప్!';

  @override
  String get pleaseProvideValidDescription => 'దయచేసి చెల్లుబాటుయొక్క వివరణ ఇవ్వండి';

  @override
  String get appPricingLabel => 'అ్యాప్ ధర';

  @override
  String get noneSelected => 'ఏదీ ఎంచుకోబడలేదు';

  @override
  String get appIdCopiedToClipboard => 'అ్యాప్ ID క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get appCategoryModalTitle => 'అ్యాప్ వర్గం';

  @override
  String get pricingFree => 'ఉచితం';

  @override
  String get pricingPaid => 'చెల్లింపు';

  @override
  String get loadingCapabilities => 'సామర్థ్యాలు లోడ్ చేస్తున్నాయి...';

  @override
  String get filterInstalled => 'ఇన్‌స్టాల్ చేయబడింది';

  @override
  String get filterMyApps => 'నా అ్యాప్‌లు';

  @override
  String get clearSelection => 'ఎంపిక క్లియర్ చేయండి';

  @override
  String get filterCategory => 'వర్గం';

  @override
  String get rating4PlusStars => '4+ నక్షత్రాలు';

  @override
  String get rating3PlusStars => '3+ నక్షత్రాలు';

  @override
  String get rating2PlusStars => '2+ నక్షత్రాలు';

  @override
  String get rating1PlusStars => '1+ నక్షత్రాలు';

  @override
  String get filterRating => 'రేటింగ్';

  @override
  String get filterCapabilities => 'సామర్థ్యాలు';

  @override
  String get noNotificationScopesAvailable => 'నోటిఫికేషన్ స్కోప్‌లు అందుబాటులో లేవు';

  @override
  String get popularApps => 'ప్రజాదరణ పొందిన అ్యాప్‌లు';

  @override
  String get pleaseProvidePrompt => 'దయచేసి సూచన ఇవ్వండి';

  @override
  String chatWithAppName(String appName) {
    return '$appName తో చాట్ చేయండి';
  }

  @override
  String get defaultAiAssistant => 'డిఫాల్ట్ AI సహాయక';

  @override
  String get readyToChat => '✨ చాట్ కు సిద్ధం!';

  @override
  String get connectionNeeded => '🌐 కనెక్షన్ అవసరం';

  @override
  String get startConversation => 'సంభాషణ ప్రారంభించండి మరియు మ్యాజిక్ ప్రారంభ చేయండి';

  @override
  String get checkInternetConnection => 'దయచేసి మీ ఇంటర్నెట్ కనెక్షన్‌ను చెక్ చేయండి';

  @override
  String get wasThisHelpful => 'ఇది సహాయకరమైనదేనా?';

  @override
  String get thankYouForFeedback => 'మీ ప్రతిస్పందన కోసం ధన్యవాదాలు!';

  @override
  String get maxFilesUploadError => 'మీరు ఒక సమయంలో 4 ఫైల్‌లను మాత్రమే అప్‌లోడ్ చేయవచ్చు';

  @override
  String get attachedFiles => '📎 జత చేసిన ఫైల్‌లు';

  @override
  String get takePhoto => 'ఫోటో తీయండి';

  @override
  String get captureWithCamera => 'కెమెరాతో సంపాదించండి';

  @override
  String get selectImages => 'ఇమేజీలు ఎంచుకోండి';

  @override
  String get chooseFromGallery => 'గ్యాలరీ నుండి ఎంచుకోండి';

  @override
  String get selectFile => 'ఫైల్ ఎంచుకోండి';

  @override
  String get chooseAnyFileType => 'ఏదైనా ఫైల్ రకాన్ని ఎంచుకోండి';

  @override
  String get cannotReportOwnMessages => 'మీరు మీ స్వంత సందేశాలను నివేదించలేరు';

  @override
  String get messageReportedSuccessfully => '✅ సందేశం విజయవంతంగా నివేదించబడింది';

  @override
  String get confirmReportMessage => 'ఈ సందేశాన్ని నివేదించాలని మీరు నిశ్చితమైనారా?';

  @override
  String get selectChatAssistant => 'చాట్ సహాయకను ఎంచుకోండి';

  @override
  String get enableMoreApps => 'మరిన్ని అ్యాప్‌లను ప్రారంభించండి';

  @override
  String get chatCleared => 'చాట్ క్లియర్ చేయబడింది';

  @override
  String get clearChatTitle => 'చాట్ క్లియర్ చేయాలా?';

  @override
  String get confirmClearChat => 'చాట్ క్లియర్ చేయాలని మీరు నిశ్చితమైనారా? ఈ చర్యను రద్దు చేయలేము.';

  @override
  String get copy => 'కాపీ';

  @override
  String get share => 'షేర్ చేయండి';

  @override
  String get report => 'నివేదించండి';

  @override
  String get microphonePermissionRequired => 'కాల్‌లు చేయడానికి మైక్రోఫోన్ అనుమతి అవసరం';

  @override
  String get microphonePermissionDenied =>
      'మైక్రోఫోన్ అనుమతి నిరాకరించబడింది. దయచేసి సిస్టమ్ ప్రిఫరెన్సెస్ > గోప్యత & భద్రత > మైక్రోఫోన్‌లో అనుమతిని మంజూరు చేయండి.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'మైక్రోఫోన్ అనుమతిని చెక్ చేయడం విఫలమైంది: $error';
  }

  @override
  String get failedToTranscribeAudio => 'ఆడియో ట్రాన్‌స్క్రిప్ట్ చేయడం విఫలమైంది';

  @override
  String get transcribing => 'ట్రాన్‌స్క్రిప్ట్ చేస్తున్నాయి...';

  @override
  String get transcriptionFailed => 'ట్రాన్‌స్క్రిప్షన్ విఫలమైంది';

  @override
  String get discardedConversation => 'విస్మరించిన సంభాషణ';

  @override
  String get at => 'వద్ద';

  @override
  String get from => 'నుండి';

  @override
  String get copied => 'కాపీ చేయబడింది!';

  @override
  String get copyLink => 'లింక్ కాపీ చేయండి';

  @override
  String get hideTranscript => 'ట్రాన్‌స్క్రిప్ట్ దాచండి';

  @override
  String get viewTranscript => 'ట్రాన్‌స్క్రిప్ట్ చూడండి';

  @override
  String get conversationDetails => 'సంభాషణ వివరాలు';

  @override
  String get transcript => 'ట్రాన్‌స్క్రిప్ట్';

  @override
  String segmentsCount(int count) {
    return '$count సెగ్మెంట్‌లు';
  }

  @override
  String get noTranscriptAvailable => 'ట్రాన్‌స్క్రిప్ట్ అందుబాటులో లేదు';

  @override
  String get noTranscriptMessage => 'ఈ సంభాషణకు ట్రాన్‌స్క్రిప్ట్ లేదు.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'సంభాషణ URL ఉత్పత్తి చేయబడలేదు.';

  @override
  String get failedToGenerateConversationLink => 'సంభాషణ లింక్ ఉత్పత్తి చేయడం విఫలమైంది';

  @override
  String get failedToGenerateShareLink => 'షేర్ లింక్ ఉత్పత్తి చేయడం విఫలమైంది';

  @override
  String get reloadingConversations => 'సంభాషణలు తిరిగి లోడ్ చేస్తున్నాయి...';

  @override
  String get user => 'వినియోగదారు';

  @override
  String get starred => 'స్టార్ చేయబడింది';

  @override
  String get date => 'తేదీ';

  @override
  String get noResultsFound => 'ఫలితాలు కనుగొనబడలేదు';

  @override
  String get tryAdjustingSearchTerms => 'మీ శోధన నిబంధనలను సర్దబmylni చేయడానికి ప్రయత్నించండి';

  @override
  String get starConversationsToFindQuickly => 'త్వరితంగా కనుగొనడానికి సంభాషణలను స్టార్ చేయండి';

  @override
  String noConversationsOnDate(String date) {
    return '$date న సంభాషణలు లేవు';
  }

  @override
  String get trySelectingDifferentDate => 'వేరు తేదీని ఎంచుకోవడానికి ప్రయత్నించండి';

  @override
  String get conversations => 'సంభాషణలు';

  @override
  String get chat => 'చాట్';

  @override
  String get actions => 'చర్యలు';

  @override
  String get syncAvailable => 'సింక్ అందుబాటులో ఉంది';

  @override
  String get referAFriend => 'స్నేహితుడిని సూచించండి';

  @override
  String get help => 'సహాయం';

  @override
  String get pro => 'ప్రో';

  @override
  String get upgradeToPro => 'ప్రోకు అపగ్రేడ్ చేయండి';

  @override
  String get getOmiDevice => 'Omi డివైస్ పొందండి';

  @override
  String get wearableAiCompanion => 'ధరించదగిన AI సఙ్గి';

  @override
  String get loadingMemories => 'స్మృతులు లోడ్ చేస్తున్నాయి...';

  @override
  String get allMemories => 'సమస్త స్మృతులు';

  @override
  String get aboutYou => 'మీ గురించి';

  @override
  String get manual => 'మానవీయ';

  @override
  String get loadingYourMemories => 'మీ స్మృతులు లోడ్ చేస్తున్నాయి...';

  @override
  String get createYourFirstMemory => 'ప్రారంభించడానికి మీ మొదటి స్మృతిని సృష్టించండి';

  @override
  String get tryAdjustingFilter => 'మీ శోధన లేదా ఫిల్టర్‌ను సర్దబmlni చేయడానికి ప్రయత్నించండి';

  @override
  String get whatWouldYouLikeToRemember => 'మీరు ఎమ్‌ను గుర్తుంచుకోవాలనుకుంటారు?';

  @override
  String get category => 'వర్గం';

  @override
  String get public => 'సార్వజనిక';

  @override
  String get failedToSaveCheckConnection => 'సేవ్ చేయడం విఫలమైంది. దయచేసి మీ కనెక్షన్‌ను చెక్ చేయండి.';

  @override
  String get createMemory => 'స్మృతి సృష్టించండి';

  @override
  String get deleteMemoryConfirmation => 'ఈ స్మృతిని తొలగించాలని మీరు నిశ్చితమైనారా? ఈ చర్యను రద్దు చేయలేము.';

  @override
  String get makePrivate => 'ఖాగితి చేయండి';

  @override
  String get organizeAndControlMemories => 'మీ స్మృతులను సంఘటించండి మరియు నియంత్రించండి';

  @override
  String get total => 'మొత్తం';

  @override
  String get makeAllMemoriesPrivate => 'సమస్త స్మృతులను ఖాగితి చేయండి';

  @override
  String get setAllMemoriesToPrivate => 'సమస్త స్మృతులను ఖాగితి దృశ్యమానతకు సెట్ చేయండి';

  @override
  String get makeAllMemoriesPublic => 'సమస్త స్మృతులను సార్వజనిక చేయండి';

  @override
  String get setAllMemoriesToPublic => 'సమస్త స్మృతులను సార్వజనిక దృశ్యమానతకు సెట్ చేయండి';

  @override
  String get permanentlyRemoveAllMemories => 'Omi నుండి సమస్త స్మృతులను శాశ్వతంగా తీసివేయండి';

  @override
  String get allMemoriesAreNowPrivate => 'సమస్త స్మృతులు ఇప్పుడు ఖాగితం';

  @override
  String get allMemoriesAreNowPublic => 'సమస్త స్మృతులు ఇప్పుడు సార్వజనిక';

  @override
  String get clearOmisMemory => 'Omi స్మృతిని క్లియర్ చేయండి';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Omi స్మృతిని క్లియర్ చేయాలని మీరు నిశ్చితమైనారా? ఈ చర్యను రద్దు చేయలేము మరియు $count స్మృతులన్నింటిని శాశ్వతంగా తొలగిస్తుంది.';
  }

  @override
  String get omisMemoryCleared => 'మీ గురించి Omi స్మృతి క్లియర్ చేయబడింది';

  @override
  String get welcomeToOmi => 'Omi కు స్వాగతం';

  @override
  String get continueWithApple => 'Apple తో కొనసాగండి';

  @override
  String get continueWithGoogle => 'Google తో కొనసాగించండి';

  @override
  String get byContinuingYouAgree => 'కొనసాగించడం ద్వారా, మీరు మా ';

  @override
  String get termsOfService => 'సేవా నిబంధనలు';

  @override
  String get and => ' మరియు ';

  @override
  String get dataAndPrivacy => 'డేటా & గోప్యత';

  @override
  String get secureAuthViaAppleId => 'Apple ID ద్వారా సురక్షితమైన ప్రమాణీకరణ';

  @override
  String get secureAuthViaGoogleAccount => 'Google ఖాతా ద్వారా సురక్షితమైన ప్రమాణీకరణ';

  @override
  String get whatWeCollect => 'మేము సేకరించేది';

  @override
  String get dataCollectionMessage =>
      'కొనసాగించడం ద్వారా, మీ సంభాషణలు, రికార్డింగ్‌లు మరియు వ్యక్తిగత సమాచారం AI-శక్తిమైన అంతర్దృష్టులను అందించడానికి మరియు అన్ని అ్యాప్ ఫీచర్‌లను ప్రారంభించడానికి మా సర్వర్‌లలో సురక్షితంగా నిల్వ చేయబడుతుంది.';

  @override
  String get dataProtection => 'డేటా సంరక్షణ';

  @override
  String get yourDataIsProtected => 'మీ డేటా సంరక్షించబడుతుంది మరియు మా ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'దయచేసి మీ ప్రాథమిక భాషను ఎంచుకోండి';

  @override
  String get chooseYourLanguage => 'మీ భాషను ఎంచుకోండి';

  @override
  String get selectPreferredLanguageForBestExperience => 'ఉత్తమ Omi అనుభవం కోసం మీ ఇష్ట భాషను ఎంచుకోండి';

  @override
  String get searchLanguages => 'భాషలను శోధించండి...';

  @override
  String get selectALanguage => 'భాషను ఎంచుకోండి';

  @override
  String get tryDifferentSearchTerm => 'వేరే శోధన పదాన్ని ప్రయత్నించండి';

  @override
  String get pleaseEnterYourName => 'దయచేసి మీ పేరు నమోదు చేయండి';

  @override
  String get nameMustBeAtLeast2Characters => 'పేరు కనీసం 2 అక్షరాలు ఉండాలి';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'మీరు ఎలా సంబోధించాలనుకుంటున్నారో చెప్పండి. ఇది మీ Omi అనుభవాన్ని వ్యక్తిగతీకరించడానికి సహాయపడుతుంది.';

  @override
  String charactersCount(int count) {
    return '$count అక్షరాలు';
  }

  @override
  String get enableFeaturesForBestExperience => 'మీ పరికరంలో ఉత్తమ Omi అనుభవం కోసం ఫీచర్‌లను ప్రారంభించండి.';

  @override
  String get microphoneAccess => 'మైక్రోఫోన్ యాక్సెస్';

  @override
  String get recordAudioConversations => 'ఆడియో సంభాషణలను రికార్డ్ చేయండి';

  @override
  String get microphoneAccessDescription =>
      'మీ సంభాషణలను రికార్డ్ చేయడానికి మరియు ట్రాన్‌స్‌క్రిప్షన్‌లను అందించడానికి Omi కు మైక్రోఫోన్ యాక్సెస్ అవసరం.';

  @override
  String get screenRecording => 'స్క్రీన్ రికార్డింగ్';

  @override
  String get captureSystemAudioFromMeetings => 'సమావేశాల నుండి సిస్టమ్ ఆడియోను సంగ్రహించండి';

  @override
  String get screenRecordingDescription =>
      'మీ బ్రౌజర్-ఆధారిత సమావేశాల నుండి సిస్టమ్ ఆడియోను సంగ్రహించడానికి Omi కు స్క్రీన్ రికార్డింగ్ అనుమతి అవసరం.';

  @override
  String get accessibility => 'యాక్సెసిబిలిటీ';

  @override
  String get detectBrowserBasedMeetings => 'బ్రౌజర్-ఆధారిత సమావేశాలను గుర్తించండి';

  @override
  String get accessibilityDescription =>
      'మీ బ్రౌజర్‌లో Zoom, Meet లేదా Teams సమావేశాలకు చేరిక చేసినప్పుడు గుర్తించడానికి Omi కు యాక్సెసిబిలిటీ అనుమతి అవసరం.';

  @override
  String get pleaseWait => 'దయచేసి ఆగండి...';

  @override
  String get joinTheCommunity => 'కమ్యూనిటీకి చేరండి!';

  @override
  String get loadingProfile => 'ప్రొఫైల్ లోడ్ చేయబడుతోంది...';

  @override
  String get profileSettings => 'ప్రొఫైల్ సెట్టింగ్‌లు';

  @override
  String get noEmailSet => 'ఈమెయిల్ సెట్ చేయబడలేదు';

  @override
  String get userIdCopiedToClipboard => 'ఉపయోగకర్త ID క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get yourInformation => 'మీ సమాచారం';

  @override
  String get setYourName => 'మీ పేరు సెట్ చేయండి';

  @override
  String get changeYourName => 'మీ పేరు మార్చండి';

  @override
  String get voiceAndPeople => 'వాయిస్ & ప్రజలు';

  @override
  String get teachOmiYourVoice => 'Omi కు మీ వాయిస్ నేర్పండి';

  @override
  String get tellOmiWhoSaidIt => 'Omi కు ఎవరు చెప్పారో చెప్పండి 🗣️';

  @override
  String get payment => 'చెల్లింపు';

  @override
  String get addOrChangeYourPaymentMethod => 'మీ చెల్లింపు పద్ధతిని జోడించండి లేదా మార్చండి';

  @override
  String get preferences => 'ప్రాధాన్యతలు';

  @override
  String get helpImproveOmiBySharing =>
      'నామరూప విశ్లేషణ డేటాను భాగస్వామ్యం చేయడం ద్వారా Omi ను మెరుగుపరచడానికి సహాయ చేయండి';

  @override
  String get deleteAccount => 'ఖాతాను తొలగించండి';

  @override
  String get deleteYourAccountAndAllData => 'మీ ఖాతా మరియు అన్ని డేటాను తొలగించండి';

  @override
  String get clearLogs => 'లాగ్‌లను క్లియర్ చేయండి';

  @override
  String get debugLogsCleared => 'డీబగ్ లాగ్‌లు క్లియర్ చేయబడ్డాయి';

  @override
  String get exportConversations => 'సంభాషణలను ఎగుమతి చేయండి';

  @override
  String get exportAllConversationsToJson => 'మీ సంభాషణలన్నిటిని JSON ఫైల్‌కు ఎగుమతి చేయండి.';

  @override
  String get conversationsExportStarted =>
      'సంభాషణల ఎగుమతి ప్రారంభమైంది. ఇది కొన్ని సెకన్ల పాటు తీసుకోవచ్చు, దయచేసి ఆగండి.';

  @override
  String get mcpDescription =>
      'Omi ను ఇతర అ్యాప్లికేషన్‌లతో కనెక్ట్ చేయడానికి మీ జ్ఞాపనలు మరియు సంభాషణలను చదవడానికి, శోధించడానికి మరియు నిర్వహించడానికి. ప్రారంభించడానికి కీని సృష్టించండి.';

  @override
  String get apiKeys => 'API కీలు';

  @override
  String errorLabel(String error) {
    return 'ఎర్రర్: $error';
  }

  @override
  String get noApiKeysFound => 'API కీలు కనుగొనబడలేదు. ప్రారంభించడానికి ఒకటి సృష్టించండి.';

  @override
  String get advancedSettings => 'అందరికీ సెట్టింగ్‌లు';

  @override
  String get triggersWhenNewConversationCreated => 'కొత్త సంభాషణ సృష్టించినప్పుడు ట్రిగర్ చేస్తుంది.';

  @override
  String get triggersWhenNewTranscriptReceived => 'కొత్త ట్రాన్‌స్‌క్రిప్ట్ అందించినప్పుడు ట్రిగర్ చేస్తుంది.';

  @override
  String get realtimeAudioBytes => 'రియల్‌టైమ్ ఆడియో బైట్‌లు';

  @override
  String get triggersWhenAudioBytesReceived => 'ఆడియో బైట్‌లు అందించినప్పుడు ట్రిగర్ చేస్తుంది.';

  @override
  String get everyXSeconds => 'ప్రతి x సెకన్ల';

  @override
  String get triggersWhenDaySummaryGenerated => 'రోజు సారాంశం ఉత్పత్తి చేయబడినప్పుడు ట్రిగర్ చేస్తుంది.';

  @override
  String get tryLatestExperimentalFeatures => 'Omi టీమ్ నుండి సరికొత్త ప్రయోగాత్మక ఫీచర్‌లను ప్రయత్నించండి.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'ట్రాన్‌స్‌క్రిప్షన్ సేవ నిర్ధారణ స్థితి';

  @override
  String get enableDetailedDiagnosticMessages =>
      'ట్రాన్‌స్‌క్రిప్షన్ సేవ నుండి వివరణాత్మక నిర్ధారణ సందేశాలను ప్రారంభించండి';

  @override
  String get autoCreateAndTagNewSpeakers => 'కొత్త స్పీకర్‌లను స్వయంచాలకంగా సృష్టించండి మరియు ట్యాగ్ చేయండి';

  @override
  String get automaticallyCreateNewPerson =>
      'ట్రాన్‌స్‌క్రిప్ట్‌లో పేరు గుర్తించినప్పుడు కొత్త వ్యక్తిని స్వయంచాలకంగా సృష్టించండి.';

  @override
  String get pilotFeatures => 'పైలట్ ఫీచర్‌లు';

  @override
  String get pilotFeaturesDescription => 'ఈ ఫీచర్‌లు పరీక్షలు మరియు సపోర్టు కguaranteed లేదు.';

  @override
  String get suggestFollowUpQuestion => 'ఫాలో-అప్ ప్రశ్న సూచించండి';

  @override
  String get saveSettings => 'సెట్టింగ్‌లను సేవ చేయండి';

  @override
  String get syncingDeveloperSettings => 'డెవలపర్ సెట్టింగ్‌లను సమకాలీకరిస్తోంది...';

  @override
  String get summary => 'సారాంశం';

  @override
  String get auto => 'స్వయంచాలక';

  @override
  String get noSummaryForApp => 'ఈ అ్యాప్‌కు సారాంశం లేనిది. మెరుగైన ఫలితాల కోసం మరొక అ్యాప్ ప్రయత్నించండి.';

  @override
  String get tryAnotherApp => 'మరొక అ్యాప్ ప్రయత్నించండి';

  @override
  String generatedBy(String appName) {
    return '$appName ద్వారా జనరేట్ చేయబడింది';
  }

  @override
  String get overview => 'సారాంశం';

  @override
  String get otherAppResults => 'ఇతర అ్యాప్ ఫలితాలు';

  @override
  String get unknownApp => 'తెలియని అ్యాప్';

  @override
  String get noSummaryAvailable => 'సారాంశం లేనిది';

  @override
  String get conversationNoSummaryYet => 'ఈ సంభాషణకు ఇంకా సారాంశం లేనిది.';

  @override
  String get chooseSummarizationApp => 'సారాంశ అ్యాప్ ఎంచుకోండి';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName డిఫాల్ట్ సారాంశ అ్యాప్‌గా సెట్ చేయబడింది';
  }

  @override
  String get letOmiChooseAutomatically => 'Omi ఉత్తమ అ్యాప్‌ను స్వయంచాలకంగా ఎంచుకోనివ్వండి';

  @override
  String get deleteConversationConfirmation =>
      'ఈ సంభాషణను తొలగించాలనుకుంటున్నారని మీరు నిశ్చితమైనారా? ఈ చర్య చేసి విషయాన్ని తిరిగి సరిచేయలేము.';

  @override
  String get conversationDeleted => 'సంభాషణ తొలగించబడింది';

  @override
  String get generatingLink => 'లింక్ జనరేట్ చేయబడుతోంది...';

  @override
  String get editConversation => 'సంభాషణను సవరించండి';

  @override
  String get conversationLinkCopiedToClipboard => 'సంభాషణ లింక్ క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get conversationTranscriptCopiedToClipboard => 'సంభాషణ ట్రాన్‌స్‌క్రిప్ట్ క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';

  @override
  String get editConversationDialogTitle => 'సంభాషణను సవరించండి';

  @override
  String get changeTheConversationTitle => 'సంభాషణ శీర్షికను మార్చండి';

  @override
  String get conversationTitle => 'సంభాషణ శీర్షిక';

  @override
  String get enterConversationTitle => 'సంభాషణ శీర్షిక నమోదు చేయండి...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'సంభాషణ శీర్షిక విజయవంతంగా నవీకరించబడింది';

  @override
  String get failedToUpdateConversationTitle => 'సంభాషణ శీర్షిక నవీకరణ విఫలమైంది';

  @override
  String get errorUpdatingConversationTitle => 'సంభాషణ శీర్షిక నవీకరణలో ఎర్రర్';

  @override
  String get settingUp => 'సెట్ అప్ చేయబడుతోంది...';

  @override
  String get startYourFirstRecording => 'మీ మొదటి రికార్డింగ్ ప్రారంభించండి';

  @override
  String get preparingSystemAudioCapture => 'సిస్టమ్ ఆడియో సంగ్రహణ ప్రস్తుత చేయబడుతోంది';

  @override
  String get clickTheButtonToCaptureAudio =>
      'లైవ్ ట్రాన్‌స్‌క్రిప్ట్‌లు, AI అంతర్దృష్టులు మరియు స్వయంచాలక సేవ కోసం ఆడియోను సంగ్రహించడానికి బటన్‌ను క్లిక్ చేయండి.';

  @override
  String get reconnecting => 'తిరిగి కనెక్ట్ చేయబడుతోంది...';

  @override
  String get recordingPaused => 'రికార్డింగ్ నిలిపివేయబడింది';

  @override
  String get recordingActive => 'రికార్డింగ్ సక్రియం';

  @override
  String get startRecording => 'రికార్డింగ్ ప్రారంభించండి';

  @override
  String resumingInCountdown(String countdown) {
    return '$countdownలో స్థిరమైనది...';
  }

  @override
  String get tapPlayToResume => 'స్థిరతకు ప్లే నొక్కండి';

  @override
  String get listeningForAudio => 'ఆడియోను వింటోంది...';

  @override
  String get preparingAudioCapture => 'ఆడియో సంగ్రహణ ప్రస్తుత చేయబడుతోంది';

  @override
  String get clickToBeginRecording => 'రికార్డింగ్ ప్రారంభించడానికి క్లిక్ చేయండి';

  @override
  String get translated => 'అనువదించబడింది';

  @override
  String get liveTranscript => 'లైవ్ ట్రాన్‌స్‌క్రిప్ట్';

  @override
  String segmentsSingular(String count) {
    return '$count సెగ్మెంట్';
  }

  @override
  String segmentsPlural(String count) {
    return '$count సెగ్‌మెంట్‌లు';
  }

  @override
  String get startRecordingToSeeTranscript => 'లైవ్ ట్రాన్‌స్‌క్రిప్ట్ చూడటానికి రికార్డింగ్ ప్రారంభించండి';

  @override
  String get paused => 'నిలిపివేయబడింది';

  @override
  String get initializing => 'ప్రారంభించబడుతోంది...';

  @override
  String get recording => 'రికార్డింగ్';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'మైక్రోఫోన్ మార్చబడింది. $countdownలో స్థిరమైనది';
  }

  @override
  String get clickPlayToResumeOrStop => 'స్థిరతకు ప్లే నొక్కండి లేదా పూర్తి చేయటానికి నిలిపివేయండి';

  @override
  String get settingUpSystemAudioCapture => 'సిస్టమ్ ఆడియో సంగ్రహణ సెట్ అప్ చేయబడుతోంది';

  @override
  String get capturingAudioAndGeneratingTranscript =>
      'ఆడియోను సంగ్రహిస్తోంది మరియు ట్రాన్‌స్‌క్రిప్ట్ జనరేట్ చేస్తోంది';

  @override
  String get clickToBeginRecordingSystemAudio => 'సిస్టమ్ ఆడియో రికార్డింగ్ ప్రారంభించడానికి క్లిక్ చేయండి';

  @override
  String get you => 'మీరు';

  @override
  String speakerWithId(String speakerId) {
    return 'స్పీకర్ $speakerId';
  }

  @override
  String get translatedByOmi => 'omi ద్వారా అనువదించబడింది';

  @override
  String get backToConversations => 'సంభాషణలకు తిరిగి వెళ్లండి';

  @override
  String get systemAudio => 'సిస్టమ్';

  @override
  String get mic => 'మైక్';

  @override
  String audioInputSetTo(String deviceName) {
    return 'ఆడియో ఇన్‌పుట్ $deviceNameకు సెట్ చేయబడింది';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'ఆడియో పరికరం స్విచ్ చేయడంలో ఎర్రర్: $error';
  }

  @override
  String get selectAudioInput => 'ఆడియో ఇన్‌పుట్ ఎంచుకోండి';

  @override
  String get loadingDevices => 'పరికరాలను లోడ్ చేయబడుతోంది...';

  @override
  String get settingsHeader => 'సెట్టింగ్‌లు';

  @override
  String get plansAndBilling => 'ప్లాన్‌లు & బిలింగ్';

  @override
  String get calendarIntegration => 'క్యాలెండర్ ఇంటిగ్రేషన్';

  @override
  String get dailySummary => 'దైనిక సారాంశం';

  @override
  String get developer => 'డెవలపర్';

  @override
  String get about => 'గురించి';

  @override
  String get selectTime => 'సమయం ఎంచుకోండి';

  @override
  String get accountGroup => 'ఖాతా';

  @override
  String get signOutQuestion => 'సైన్ అవుట్ చేయాలా?';

  @override
  String get signOutConfirmation => 'సైన్ అవుట్ చేయాలనుకుంటున్నారని మీరు నిశ్చితమైనారా?';

  @override
  String get customVocabularyHeader => 'CUSTOM VOCABULARY';

  @override
  String get addWordsDescription => 'Omi ట్రాన్‌స్‌క్రిప్షన్ సమయంలో గుర్తించాలని కోరుకునే పదాలను జోడించండి.';

  @override
  String get enterWordsHint => 'పదాలను నమోదు చేయండి (కామా ద్వారా వేరు చేయబడింది)';

  @override
  String get dailySummaryHeader => 'DAILY SUMMARY';

  @override
  String get dailySummaryTitle => 'దైనిక సారాంశం';

  @override
  String get dailySummaryDescription => 'మీ రోజు యొక్క సంభాషణల యొక్క ఇష్టమైన సారాంశం నోటిఫికేషన్‌గా డెలివరీ చేయబడింది.';

  @override
  String get deliveryTime => 'డెలివరీ సమయం';

  @override
  String get deliveryTimeDescription => 'మీ దైనిక సారాంశం పొందటానికి ఎప్పుడు';

  @override
  String get subscription => 'సభ్యత';

  @override
  String get viewPlansAndUsage => 'ప్లాన్‌లు & ఉపయోగాన్ని చూడండి';

  @override
  String get viewPlansDescription => 'మీ సభ్యత నిర్వహించండి మరియు ఉపయోగ గణాంకాలను చూడండి';

  @override
  String get addOrChangePaymentMethod => 'మీ చెల్లింపు పద్ధతిని జోడించండి లేదా మార్చండి';

  @override
  String get displayOptions => 'ఆప్షన్‌లను ప్రదర్శించండి';

  @override
  String get showMeetingsInMenuBar => 'మెనూ బార్‌లో సమావేశాలను చూపండి';

  @override
  String get displayUpcomingMeetingsDescription => 'మెనూ బార్‌లో రాబోయే సమావేశాలను ప్రదర్శించండి';

  @override
  String get showEventsWithoutParticipants => 'పాల్గొనేవారు లేని ఈవెంట్‌లను చూపండి';

  @override
  String get includePersonalEventsDescription => 'హాజరు లేని వ్యక్తిగత ఈవెంట్‌లను చేర్చండి';

  @override
  String get upcomingMeetings => 'రాబోయే సమావేశాలు';

  @override
  String get checkingNext7Days => 'తరువాత 7 రోజులను పరిశీలిస్తోంది';

  @override
  String get shortcuts => 'షార్టকట్‌లు';

  @override
  String get shortcutChangeInstruction =>
      'షార్టకట్‌ను మార్చడానికి దానిపై క్లిక్ చేయండి. రద్దు చేయడానికి Escape నొక్కండి.';

  @override
  String get configureSTTProvider => 'STT ప్రొవైడర్ కాన్ఫిగర్ చేయండి';

  @override
  String get setConversationEndDescription => 'సంభాషణలు స్వయంచాలకంగా ఎప్పుడు ముగియాలో సెట్ చేయండి';

  @override
  String get importDataDescription => 'ఇతర వనరుల నుండి డేటాను దిగుమతి చేయండి';

  @override
  String get exportConversationsDescription => 'సంభాషణలను JSONకు ఎగుమతి చేయండి';

  @override
  String get exportingConversations => 'సంభాషణలను ఎగుమతి చేస్తోంది...';

  @override
  String get clearNodesDescription => 'అన్ని నోడ్‌లు మరియు కనెక్షన్‌లను క్లియర్ చేయండి';

  @override
  String get deleteKnowledgeGraphQuestion => 'జ్ఞానం గ్రాఫ్ తొలగించాలా?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'ఇది అన్ని ఉత్పత్తి కంపిల్ జ్ఞానం గ్రాఫ్ డేటాను తొలగిస్తుంది. మీ అసలు జ్ఞాపనలు సురక్షితమైనవిగా ఉంటాయి.';

  @override
  String get connectOmiWithAI => 'Omi ను AI సహాయకులతో కనెక్ట్ చేయండి';

  @override
  String get noAPIKeys => 'API కీలు లేనివి. ప్రారంభించడానికి ఒకటి సృష్టించండి.';

  @override
  String get autoCreateWhenDetected => 'పేరు గుర్తించినప్పుడు స్వయంచాలకంగా సృష్టించండి';

  @override
  String get trackPersonalGoals => 'హోమ్‌పేజీలో వ్యక్తిగత లక్ష్యాలను ట్రాక్ చేయండి';

  @override
  String get endpointURL => 'ఎండ్‌పాయింట్ URL';

  @override
  String get links => 'లింకులు';

  @override
  String get discordMemberCount => 'Discord లో 8000+ సభ్యులు';

  @override
  String get userInformation => 'ఉపయోగకర్త సమాచారం';

  @override
  String get capabilities => 'సామర్థ్యాలు';

  @override
  String get previewScreenshots => 'స్క్రీన్‌షాట్‌లను ప్రిభూ చేయండి';

  @override
  String get holdOnPreparingForm => 'సరిసరి, మేము మీ కోసం ఫారమ్‌ను ప్రస్తుత చేస్తోంది';

  @override
  String get bySubmittingYouAgreeToOmi => 'సమర్పణ ద్వారా, మీరు Omi ';

  @override
  String get termsAndPrivacyPolicy => 'నిబంధనలు & గోప్యత విధానం';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'సమస్యలను నిర్ధారణ చేయటానికి సహాయపడుతుంది. 3 రోజుల తర్వాత స్వయంచాలకంగా తొలగించబడుతుంది.';

  @override
  String get manageYourApp => 'మీ అ్యాప్ నిర్వహించండి';

  @override
  String get updatingYourApp => 'మీ అ్యాప్ నవీకరించబడుతోంది';

  @override
  String get fetchingYourAppDetails => 'మీ అ్యాప్ వివరాలను గుర్తించటోంది';

  @override
  String get updateAppQuestion => 'అ్యాప్‌ను నవీకరించాలా?';

  @override
  String get updateAppConfirmation =>
      'మీ అ్యాప్‌ను నవీకరించాలనుకుంటున్నారని మీరు నిశ్చితమైనారా? మార్పులు మా టీమ్ ద్వారా సమీక్ష చేసిన తర్వాత ప్రతిబింబిస్తాయి.';

  @override
  String get updateApp => 'అ్యాప్‌ను నవీకరించండి';

  @override
  String get createAndSubmitNewApp => 'కొత్త అ్యాప్‌ను సృష్టించండి మరియు సమర్పించండి';

  @override
  String appsCount(String count) {
    return 'అ్యాప్‌లు ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'ప్రైవేట్ అ్యాప్‌లు ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'పబ్లిక్ అ్యాప్‌లు ($count)';
  }

  @override
  String get newVersionAvailable => 'కొత్త సంస్కరణ లభ్యమైంది 🎉';

  @override
  String get no => 'లేదు';

  @override
  String get subscriptionCancelledSuccessfully =>
      'సభ్యత విజయవంతంగా రద్దు చేయబడింది. ఇది ప్రస్తుత బిలింగ్ కాలం చివర వరకు సక్రియంగా ఉంటుంది.';

  @override
  String get failedToCancelSubscription => 'సభ్యత రద్దు చేయటానికి విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get invalidPaymentUrl => 'చెల్లని చెల్లింపు URL';

  @override
  String get permissionsAndTriggers => 'అనుమతులు & ట్రిగర్‌లు';

  @override
  String get chatFeatures => 'చాట్ ఫీచర్‌లు';

  @override
  String get uninstall => 'అన్ఇన్‌స్టాల్ చేయండి';

  @override
  String get installs => 'ఇన్‌స్టాల్‌లు';

  @override
  String get priceLabel => 'ధర';

  @override
  String get updatedLabel => 'నవీకరించబడింది';

  @override
  String get createdLabel => 'సృష్టించబడింది';

  @override
  String get featuredLabel => 'ఫీచర్ చేయబడింది';

  @override
  String get cancelSubscriptionQuestion => 'సభ్యత రద్దు చేయాలా?';

  @override
  String get cancelSubscriptionConfirmation =>
      'సభ్యత రద్దు చేయాలనుకుంటున్నారని మీరు నిశ్చితమైనారా? మీ ప్రస్తుత బిలింగ్ కాలం చివర వరకు మీరు యాక్సెస్‌ను కలిగి ఉంటారు.';

  @override
  String get cancelSubscriptionButton => 'సభ్యత రద్దు చేయండి';

  @override
  String get cancelling => 'రద్దు చేయబడుతోంది...';

  @override
  String get betaTesterMessage =>
      'ఈ అ్యాప్ కోసం మీరు బీటా టెస్టర్. ఇది ఇంకా పబ్లిక్‌కు కాదు. ఇది ఆమోదించిన తర్వాత పబ్లిక్‌గా ఉంటుంది.';

  @override
  String get appUnderReviewMessage =>
      'మీ అ్యాప్ సమీక్ష క్రింద ఉంది మరియు కేవలం మీకు కనిపిస్తుంది. ఇది ఆమోదించిన తర్వాత పబ్లిక్‌గా ఉంటుంది.';

  @override
  String get appRejectedMessage =>
      'మీ అ్యాప్ తిరస్కరించబడింది. దయచేసి అ్యాప్ వివరాలను నవీకరించండి మరియు సమీక్ష కోసం తిరిగి సమర్పించండి.';

  @override
  String get invalidIntegrationUrl => 'చెల్లని ఇంటిగ్రేషన్ URL';

  @override
  String get tapToComplete => 'పూర్తి చేయడానికి నొక్కండి';

  @override
  String get invalidSetupInstructionsUrl => 'చెల్లని సెట్ అప్ సూచనల URL';

  @override
  String get pushToTalk => 'చెప్పటానికి నెట్టండి';

  @override
  String get summaryPrompt => 'సారాంశ ప్రాంప్ట్';

  @override
  String get pleaseSelectARating => 'దయచేసి రేటింగ్ ఎంచుకోండి';

  @override
  String get reviewAddedSuccessfully => 'సమీక్ష విజయవంతంగా జోడించబడింది 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'సమీక్ష విజయవంతంగా నవీకరించబడింది 🚀';

  @override
  String get failedToSubmitReview => 'సమీక్ష సమర్పించటానికి విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get addYourReview => 'మీ సమీక్ష జోడించండి';

  @override
  String get editYourReview => 'మీ సమీక్ష సవరించండి';

  @override
  String get writeAReviewOptional => 'సమీక్ష వ్రాయండి (ఐచ్చికం)';

  @override
  String get submitReview => 'సమీక్ష సమర్పించండి';

  @override
  String get updateReview => 'సమీక్ష నవీకరించండి';

  @override
  String get yourReview => 'మీ సమీక్ష';

  @override
  String get anonymousUser => 'అనామక ఉపయోగకర్త';

  @override
  String get issueActivatingApp => 'ఈ అ్యాప్‌ను సక్రియం చేయడంలో సమస్య ఉంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get dataAccessNoticeDescription =>
      'ఈ అ్యాప్ మీ డేటాను యాక్సెస్ చేస్తుంది. Omi AI ఈ అ్యాప్ ద్వారా మీ డేటా ఎలా ఉపయోగించబడుతుంది, సవరించబడుతుంది లేదా తొలగించబడుతుందో వానికి బాధ్యత లేనిది';

  @override
  String get copyUrl => 'URL కాపీ చేయండి';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'సోమవారం';

  @override
  String get weekdayTue => 'మంగళవారం';

  @override
  String get weekdayWed => 'బుధవారం';

  @override
  String get weekdayThu => 'గురువారం';

  @override
  String get weekdayFri => 'శుక్రవారం';

  @override
  String get weekdaySat => 'శనివారం';

  @override
  String get weekdaySun => 'ఆదివారం';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName ఇంటిగ్రేషన్ త్వరలో వస్తోంది';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'ఇప్పటికే $platformకు ఎగుమతి చేయబడింది';
  }

  @override
  String get anotherPlatform => 'మరొక ప్లాట్‌ఫారమ్';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'సెట్టింగ్‌లు > టాస్క్ ఇంటిగ్రేషన్‌లలో $serviceName తో ప్రామాణిక చేయండి';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceNameకు జోడిస్తోంది...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceNameకు జోడించబడింది';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceNameకు జోడించటానికి విఫలమైంది';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple రిమైండర్‌లకు అనుమతి నిరాకరించబడింది';

  @override
  String failedToCreateApiKey(String error) {
    return 'ప్రొవైడర్ API కీని సృష్టించటానికి విఫలమైంది: $error';
  }

  @override
  String get createAKey => 'కీని సృష్టించండి';

  @override
  String get apiKeyRevokedSuccessfully => 'API కీ విజయవంతంగా రిభోక్ చేయబడింది';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API కీని రిభోక్ చేయటానికి విఫలమైంది: $error';
  }

  @override
  String get omiApiKeys => 'Omi API కీలు';

  @override
  String get apiKeysDescription =>
      'API కీలు మీ అ్యాప్ OMI సర్వర్‌తో సంభాషణ చేసినప్పుడు ప్రామాణీకరణ కోసం ఉపయోగించబడతాయి. అవి మీ అ్యాప్‌కు జ్ఞాపనలను సృష్టించడానికి మరియు ఇతర OMI సేవలను సురక్షితంగా యాక్సెస్ చేయడానికి అనుమతిస్తాయి.';

  @override
  String get aboutOmiApiKeys => 'Omi API కీల గురించి';

  @override
  String get yourNewKey => 'మీ కొత్త కీ:';

  @override
  String get copyToClipboard => 'క్లిప్‌బోర్డ్‌కు కాపీ చేయండి';

  @override
  String get pleaseCopyKeyNow => 'దయచేసి ఇప్పుడు కాపీ చేయండి మరియు దానిని నిరాপదమైన స్థానంలో వ్రాసుకోండి. ';

  @override
  String get willNotSeeAgain => 'మీరు దానిని మళ్లీ చూడలేరు.';

  @override
  String get revokeKey => 'కీని రిభోక్ చేయండి';

  @override
  String get revokeApiKeyQuestion => 'API కీని రిభోక్ చేయాలా?';

  @override
  String get revokeApiKeyWarning =>
      'ఈ చర్య చేసి విషయాన్ని తిరిగి సరిచేయలేము. ఈ కీని ఉపయోగించే ఏదైనా అ్యాప్లికేషన్‌లు API కు యాక్సెస్ చేయలేరు.';

  @override
  String get revoke => 'రిభోక్ చేయండి';

  @override
  String get whatWouldYouLikeToCreate => 'మీరు ఏమి సృష్టించాలనుకుంటున్నారు?';

  @override
  String get createAnApp => 'ఒక అ్యాప్ సృష్టించండి';

  @override
  String get createAndShareYourApp => 'మీ అ్యాప్‌ను సృష్టించండి మరియు భాగస్వామ్యం చేయండి';

  @override
  String get itemApp => 'అ్యాప్';

  @override
  String keepItemPublic(String item) {
    return '$item ను పబ్లిక్‌గా ఉంచండి';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item ను పబ్లిక్ చేయాలా?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item ను ప్రైవేట్ చేయాలా?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'మీరు $item ను పబ్లిక్ చేస్తే, దానిని ప్రతి ఒక్కరూ ఉపయోగించవచ్చు';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'మీరు $item ను ఇప్పుడు ప్రైవేట్ చేస్తే, ఇది ప్రతి ఒక్కరి కోసం పనిచేయటం ఆపివేస్తుంది మరియు కేవలం మీకు కనిపిస్తుంది';
  }

  @override
  String get manageApp => 'అ్యాప్ నిర్వహించండి';

  @override
  String deleteItemTitle(String item) {
    return '$item ను తొలగించండి';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item ను తొలగించాలా?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'ఈ $item ను తొలగించాలనుకుంటున్నారని మీరు నిశ్చితమైనారా? ఈ చర్య చేసి విషయాన్ని తిరిగి సరిచేయలేము.';
  }

  @override
  String get revokeKeyQuestion => 'కీని రిభోక్ చేయాలా?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'కీ \"$keyName\" ను రిభోక్ చేయాలనుకుంటున్నారని మీరు నిశ్చితమైనారా? ఈ చర్య చేసి విషయాన్ని తిరిగి సరిచేయలేము.';
  }

  @override
  String get createNewKey => 'కొత్త కీని సృష్టించండి';

  @override
  String get keyNameHint => 'ఉ.దా., Claude డెస్కటాప్';

  @override
  String get pleaseEnterAName => 'దయచేసి పేరు నమోదు చేయండి.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'కీని సృష్టించటానికి విఫలమైంది: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'కీని సృష్టించటానికి విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get keyCreated => 'కీ సృష్టించబడింది';

  @override
  String get keyCreatedMessage => 'మీ కొత్త కీ సృష్టించబడింది. దయచేసి ఇప్పుడు కాపీ చేయండి. మీరు దానిని మళ్లీ చూడలేరు.';

  @override
  String get keyWord => 'కీ';

  @override
  String get externalAppAccess => 'బాహ్య అ్యాప్ యాక్సెస్';

  @override
  String get externalAppAccessDescription =>
      'కింది ఇన్‌స్టాల్ చేయబడిన అ్యాప్‌లకు బాహ్య ఇంటిగ్రేషన్‌లు ఉన్నాయి మరియు సంభాషణలు మరియు జ్ఞాపనల వంటి మీ డేటాను యాక్సెస్ చేయవచ్చు.';

  @override
  String get noExternalAppsHaveAccess => 'బాహ్య అ్యాప్‌లకు మీ డేటాకు యాక్సెస్ లేనిది.';

  @override
  String get maximumSecurityE2ee => 'గరిష్ట సురక్ష (E2EE)';

  @override
  String get e2eeDescription =>
      'చివర నుండి చివర ఎన్‌క్రిప్షన్ గోప్యతకు పేద ప్రమాణం. ఈనాబిల్ చేసినప్పుడు, మీ డేటా మీ పరికరంపై ఎన్‌క్రిప్ట్ చేయబడుతుంది అది మా సర్వర్‌లకు పంపబడుముందు. అంటే, ఎవరూ కాదు, Omi కూడా మీ విషయవస్తువను యాక్సెస్ చేయలేరు.';

  @override
  String get importantTradeoffs => 'ముఖ్యమైన నష్టాలు:';

  @override
  String get e2eeTradeoff1 => '• బాహ్య అ్యాప్ ఇంటిగ్రేషన్‌ల వంటి కొన్ని ఫీచర్‌లు నిలిపివేయబడవచ్చు.';

  @override
  String get e2eeTradeoff2 => '• మీరు మీ పాస్‌వర్డ్‌ను కోలిపోయితే, మీ డేటాను పునరుద్ధరించలేము.';

  @override
  String get featureComingSoon => 'ఈ ఫీచర్ త్వరలో వస్తోంది!';

  @override
  String get migrationInProgressMessage => 'విస్థాపన చేస్తోంది. ఇది పూర్తిగా కాకూడా సంరక్షణ స్థితిని మార్చలేరు.';

  @override
  String get migrationFailed => 'విస్థాపన విఫలమైంది';

  @override
  String migratingFromTo(String source, String target) {
    return '$source నుండి $target కు విస్థాపన చేస్తోంది';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objects';
  }

  @override
  String get secureEncryption => 'సురక్షిత ఎన్‌క్రిప్షన్';

  @override
  String get secureEncryptionDescription =>
      'మీ డేటా Google క్లౌడ్‌లో హోస్ట్ చేయబడిన మీ సర్వర్‌లలో మీకు సంబంధించిన కీ ద్వారా ఎన్‌క్రిప్ట్ చేయబడుతుంది. అంటే, మీ ముడి విషయవస్తువు డేటాబేస్ నుండి ఎవరికీ సమర్థించలేమని, Omi సిబ్బందికీ లేదా Google కీ.';

  @override
  String get endToEndEncryption => 'చివర నుండి చివర ఎన్‌క్రిప్షన్';

  @override
  String get e2eeCardDescription =>
      'కేవలం మీరు మీ డేటాను యాక్సెస్ చేయగలిగే గరిష్ట సురక్ష కోసం ఈనాబిల్ చేయండి. మరిన్ని తెలుసుకోవటానికి నొక్కండి.';

  @override
  String get dataAlwaysEncrypted =>
      'స్థాయితో సంబంధం లేకుండా, మీ డేటా ఎల్లప్పుడు విశ్రాంతి సమయంలో మరియు రవాణా సమయంలో ఎన్‌క్రిప్ట్ చేయబడుతుంది.';

  @override
  String get readOnlyScope => 'చదువు చేయడానికి మాత్రమే';

  @override
  String get fullAccessScope => 'పూర్తి యాక్సెస్';

  @override
  String get readScope => 'చదువు';

  @override
  String get writeScope => 'వ్రాయండి';

  @override
  String get apiKeyCreated => 'API కీ సృష్టించబడింది!';

  @override
  String get saveKeyWarning => 'ఈ కీని ఇప్పుడే సేవ చేయండి! మీరు దానిని మళ్లీ చూడలేరు.';

  @override
  String get yourApiKey => 'మీ API కీ';

  @override
  String get tapToCopy => 'కాపీ చేయటానికి నొక్కండి';

  @override
  String get copyKey => 'కీ కాపీ చేయండి';

  @override
  String get createApiKey => 'API కీని సృష్టించండి';

  @override
  String get accessDataProgrammatically => 'మీ డేటాను ప్రోగ్రామ్ కంగా యాక్సెస్ చేయండి';

  @override
  String get keyNameLabel => 'కీ పేరు';

  @override
  String get keyNamePlaceholder => 'ఉ.దా., నా అ్యాప్ ఇంటిగ్రేషన్';

  @override
  String get permissionsLabel => 'అనుమతులు';

  @override
  String get permissionsInfoNote => 'R = చదువు, W = వ్రాయండి. ఏమీ ఎంచుకోకపోతే చదువు-మాత్రమే డిఫాల్ట్‌లకు.';

  @override
  String get developerApi => 'డెవలపర్ API';

  @override
  String get createAKeyToGetStarted => 'ప్రారంభించడానికి కీని సృష్టించండి';

  @override
  String errorWithMessage(String error) {
    return 'ఎర్రర్: $error';
  }

  @override
  String get omiTraining => 'Omi శిక్షణ';

  @override
  String get trainingDataProgram => 'శిక్షణ డేటా కార్యక్రమం';

  @override
  String get getOmiUnlimitedFree =>
      'AI నమూనాలను శిక్షణ ఇవ్వటానికి మీ డేటాకు సహకరించడం ద్వారా Omi అనీమితాన్ని ఉచితంగా పొందండి.';

  @override
  String get trainingDataBullets =>
      '• మీ డేటా AI నమూనాలను మెరుగుపరచడానికి సహాయపడుతుంది\n• కేవలం సున్నితమైన డేటా మాత్రమే భాగస్వామ్యం చేయబడుతుంది\n• పూర్తిగా పారదర్శక ప్రక్రియ';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training లో మరిన్ని తెలుసుకోండి';

  @override
  String get agreeToContributeData => 'నేను AI శిక్షణ కోసం నా డేటాకు సహకరించటానికి అర్థమైనవి మరియు అంగీకరిస్తున్నాను';

  @override
  String get submitRequest => 'అభ్యర్థనను సమర్పించండి';

  @override
  String get thankYouRequestUnderReview =>
      'ధన్యవాదాలు! మీ అభ్యర్థన సమీక్ష క్రింద ఉంది. ఆమోదించినప్పుడు మేము మీకు తెలియజేస్తాము.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'మీ ప్లాన్ $date వరకు సక్రియంగా ఉంటుంది. దీని తర్వాత, మీ అనీమిత ఫీచర్‌లకు యాక్సెస్ కోల్పోతారు. మీరు చేసిన చేసిన నిశ్చితమైనారా?';
  }

  @override
  String get confirmCancellation => 'రద్దుకరణని ఖచ్చితపరచండి';

  @override
  String get keepMyPlan => 'నా ప్లాన్‌ను ఉంచండి';

  @override
  String get subscriptionSetToCancel => 'మీ సభ్యత కాలం చివరిలో రద్దు చేయటానికి సెట్ చేయబడింది.';

  @override
  String get switchedToOnDevice => 'ఆన్-డివైస్ ట్రాన్‌స్‌క్రిప్షన్‌కు మార్చారు';

  @override
  String get couldNotSwitchToFreePlan => 'ఉచిత ప్లాన్‌కు మారలేకపోయాను. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get couldNotLoadPlans => 'అందుబాటులో ఉన్న ప్లాన్‌లను లోడ్ చేయలేకపోయాను. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get selectedPlanNotAvailable => 'ఎంచుకున్న ప్లాన్ అందుబాటులో లేదు. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get upgradeToAnnualPlan => 'వార్షిక ప్లాన్‌కు అప్‌గ్రేడ్ చేయండి';

  @override
  String get importantBillingInfo => 'ముఖ్యమైన బిల్లింగ్ సమాచారం:';

  @override
  String get monthlyPlanContinues => 'మీ ప్రస్తుత నెలవారీ ప్లాన్ మీ బిల్లింగ్ వ్యవధి ముగిసే వరకు కొనసాగుతుంది';

  @override
  String get paymentMethodCharged =>
      'మీ ఇప్పటికే ఉన్న చెల్లింపు పద్ధతి మీ నెలవారీ ప్లాన్ ముగిసినప్పుడు స్వయంచాలకంగా ఛార్జ్ చేయబడుతుంది';

  @override
  String get annualSubscriptionStarts =>
      'చెల్లింపు తరువాత మీ 12-నెల వార్షిక సబ్‌స్క్రిప్షన్ స్వయంచాలకంగా ప్రారంభమవుతుంది';

  @override
  String get thirteenMonthsCoverage => 'మీకు మొత్తం 13 నెలల కవరేజీ లభిస్తుంది (ప్రస్తుత నెల + 12 నెల వార్షిక)';

  @override
  String get confirmUpgrade => 'అప్‌గ్రేడ్‌ను నిర్ధారించండి';

  @override
  String get confirmPlanChange => 'ప్లాన్ మార్పును నిర్ధారించండి';

  @override
  String get confirmAndProceed => 'నిర్ధారించండి & కొనసాగండి';

  @override
  String get upgradeScheduled => 'అప్‌గ్రేడ్ షెడ్యూల్ చేయబడింది';

  @override
  String get changePlan => 'ప్లాన్‌ను మార్చండి';

  @override
  String get upgradeAlreadyScheduled => 'మీ వార్షిక ప్లాన్‌కు అప్‌గ్రేడ్ ఇప్పటికే షెడ్యూల్ చేయబడింది';

  @override
  String get youAreOnUnlimitedPlan => 'మీరు అన్‌లిమిటెడ్ ప్లాన్‌లో ఉన్నారు.';

  @override
  String get yourOmiUnleashed => 'మీ Omi, విడుదల చేయబడింది. అన్‌లిమిటెడ్‌కు వెళ్లండి అంతులేని సম్ভావ్యతల కోసం.';

  @override
  String planEndedOn(String date) {
    return 'మీ ప్లాన్ $date న ముగిసింది.\\nఇప్పుడే సబ్‌స్క్రిప్ట్ చేయండి - కొత్త బిల్లింగ్ వ్యవధి కోసం ఛార్జ్ చేయబడుతారు.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'మీ ప్లాన్ $date న రద్దు చేయడానికి సెట్ చేయబడింది.\\nమీ ప్రయోజనాలను ఉంచడానికి ఇప్పుడే సబ్‌స్క్రిప్ట్ చేయండి - $date వరకు ఛార్జ్ లేదు.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'మీ నెలవారీ ప్లాన్ ముగిసినప్పుడు మీ వార్షిక ప్లాన్ స్వయంచాలకంగా ప్రారంభమవుతుంది.';

  @override
  String planRenewsOn(String date) {
    return 'మీ ప్లాన్ $date న పునరుద్ధరించబడుతుంది.';
  }

  @override
  String get unlimitedConversations => 'అన్‌లిమిటెడ్ సంభాషణలు';

  @override
  String get askOmiAnything => 'మీ జీవితం గురించి Omi కి ఏదైనా అడగండి';

  @override
  String get unlockOmiInfiniteMemory => 'Omi యొక్క అనంత జ్ఞాపకం అన్‌లాక్ చేయండి';

  @override
  String get youreOnAnnualPlan => 'మీరు వార్షిక ప్లాన్‌లో ఉన్నారు';

  @override
  String get alreadyBestValuePlan => 'మీరు ఇప్పటికే ఉత్తమ విలువ ప్లాన్‌ను కలిగి ఉన్నారు. ఎటువంటి మార్పులు అవసరం లేవు.';

  @override
  String get unableToLoadPlans => 'ప్లాన్‌లు లోడ్ చేయలేకపోయాము';

  @override
  String get checkConnectionTryAgain => 'కనెక్షన్ తనిఖీ చేసి మళ్ళీ ప్రయత్నించండి';

  @override
  String get useFreePlan => 'ఉచిత ప్లాన్‌ను ఉపయోగించండి';

  @override
  String get continueText => 'కొనసాగండి';

  @override
  String get resubscribe => 'మళ్లీ సబ్‌స్క్రిప్ట్ చేయండి';

  @override
  String get couldNotOpenPaymentSettings => 'చెల్లింపు సెట్టింగ్‌లను తెరవలేకపోయాను. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get managePaymentMethod => 'చెల్లింపు పద్ధతిని నిర్వహించండి';

  @override
  String get cancelSubscription => 'సబ్‌స్క్రిప్షన్‌ను రద్దు చేయండి';

  @override
  String endsOnDate(String date) {
    return '$date న ముగుస్తుంది';
  }

  @override
  String get active => 'క్రియాశీల';

  @override
  String get freePlan => 'ఉచిత ప్లాన్';

  @override
  String get configure => 'కాన్ఫిగర్ చేయండి';

  @override
  String get privacyInformation => 'గోప్యతా సమాచారం';

  @override
  String get yourPrivacyMattersToUs => 'మీ గోప్యత మాకు ముఖ్యమైనది';

  @override
  String get privacyIntroText =>
      'Omi లో, మేము మీ గోప్యతను చాలా జరుపుకుంటాము. మేము మీ కోసం ఉత్పన్నమైన డేటా గురించి పారదర్శకంగా ఉండాలనుకుంటాము మరియు దానిని ఎలా ఉపయోగిస్తున్నాము. మీరు తెలుసుకోవలసిన విషయం ఇది:';

  @override
  String get whatWeTrack => 'మేము ఏమి ట్రాక్ చేస్తాము';

  @override
  String get anonymityAndPrivacy => 'నిరాపత్తা మరియు గోప్యత';

  @override
  String get optInAndOptOutOptions => 'ఆప్ట్-ఇన్ మరియు ఆప్ట్-అవుట్ ఆప్షన్‌లు';

  @override
  String get ourCommitment => 'మా ప్రతిశ్రుతి';

  @override
  String get commitmentText =>
      'మేము సేకరించిన డేటాను Omi ను మీ కోసం మెరుగైన ఉత్పన్నం చేయడానికి మాత్రమే ఉపయోగించాలని ప్రతిశ్రుతిబద్ధులు. మీ గోప్యత మరియు నమ్మకం మాకు అత్యంత ముఖ్యమైనవి.';

  @override
  String get thankYouText =>
      'Omi యొక్క విలువైన వినియోగదారుగా ఉన్నందుకు ధన్యవాదాలు. మీకు ఏవైనా ప్రశ్నలు లేదా ఆందోళనలు ఉంటే, team@basedhardware.com కు సంప్రదించడానికి సంకోచించకండి.';

  @override
  String get wifiSyncSettings => 'WiFi సమకాలీకరణ సెట్టింగ్‌లు';

  @override
  String get enterHotspotCredentials => 'మీ ఫోన్ యొక్క హాట్‌స్పాట్ సంలग్నాలను నమోదు చేయండి';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi సమకాలీకరణ మీ ఫోన్‌ను హాట్‌స్పాట్‌గా ఉపయోగిస్తుంది. సెట్టింగ్‌లు > ఖ్యాతిమත్తర హాట్‌స్పాట్‌లో మీ హాట్‌స్పాట్ పేరు మరియు పాస్‌వర్డ్ కనుగొనండి.';

  @override
  String get hotspotNameSsid => 'హాట్‌స్పాట్ పేరు (SSID)';

  @override
  String get exampleIphoneHotspot => 'ఉదా. iPhone హాట్‌స్పాట్';

  @override
  String get password => 'పాస్‌వర్డ్';

  @override
  String get enterHotspotPassword => 'హాట్‌స్పాట్ పాస్‌వర్డ్ నమోదు చేయండి';

  @override
  String get saveCredentials => 'సంలग్నాలను సేవ చేయండి';

  @override
  String get clearCredentials => 'సంలग్నాలను క్లియర్ చేయండి';

  @override
  String get pleaseEnterHotspotName => 'దయచేసి హాట్‌స్పాట్ పేరు నమోదు చేయండి';

  @override
  String get wifiCredentialsSaved => 'WiFi సంలग్నాలు సేవ చేయబడ్డాయి';

  @override
  String get wifiCredentialsCleared => 'WiFi సంలग్నాలు క్లియర్ చేయబడ్డాయి';

  @override
  String summaryGeneratedForDate(String date) {
    return '$date కోసం సారాంశం రూపొందించబడింది';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'సారాంశం రూపొందించడం విఫలమైంది. ఆ రోజున మీకు సంభాషణలు ఉన్నాయని నిర్ధారించుకోండి.';

  @override
  String get summaryNotFound => 'సారాంశం కనుగొనబడలేదు';

  @override
  String get yourDaysJourney => 'మీ రోజు యొక్క ప్రయాణం';

  @override
  String get highlights => 'హైలైట్‌లు';

  @override
  String get unresolvedQuestions => 'సమాధానం చేయని ప్రశ్నలు';

  @override
  String get decisions => 'నిర్ణయాలు';

  @override
  String get learnings => 'నేర్పులు';

  @override
  String get autoDeletesAfterThreeDays => '3 రోజుల తరువాత స్వయంచాలకంగా తొలగిస్తుంది.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'జ్ఞానం గ్రాఫ్ విజయవంతంగా తొలగించబడింది';

  @override
  String get exportStartedMayTakeFewSeconds => 'ఎగుమతి ప్రారంభమైంది. ఇది కొన్ని సెకన్లు పట్టవచ్చు...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'ఇది అన్ని ఉత్పన్నమైన జ్ఞానం గ్రాఫ్ డేటా (నోడ్‌లు మరియు కనెక్షన్‌లు) తొలగిస్తుంది. మీ అసలు జ్ఞాపకాలు సురక్షితంగా ఉంటాయి. గ్రాఫ్ కాలక్రమేణా లేదా తరువాతి అభ్యర్థన యొక్క నిమిషాల్లో పునర్నిర్మించబడుతుంది.';

  @override
  String get configureDailySummaryDigest => 'మీ నిత్య చర్య సమితులను సంగ్రహం చేయండి';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes అందిస్తుంది';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType చేత ట్రిగర్ చేయబడింది';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription మరియు $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'నిర్దిష్ట డేటా ప్రాప్తి కాన్ఫిగర్ చేయబడలేదు.';

  @override
  String get basicPlanDescription => '1,200 ప్రీమియం నిమిషాలు + ఆన్-డివైస్‌లో అన్‌లిమిటెడ్';

  @override
  String get minutes => 'నిమిషాలు';

  @override
  String get omiHas => 'Omi ఉన్నది:';

  @override
  String get premiumMinutesUsed => 'ప్రీమియం నిమిషాలు ఉపయోగించారు.';

  @override
  String get setupOnDevice => 'ఆన్-డివైస్‌లో సెటప్ చేయండి';

  @override
  String get forUnlimitedFreeTranscription => 'అన్‌లిమిటెడ్ ఉచిత ట్రాన్‌స్క్రిప్షన్ కోసం.';

  @override
  String premiumMinsLeft(int count) {
    return '$count ప్రీమియం నిమిషాలు మిగిలి ఉన్నాయి.';
  }

  @override
  String get alwaysAvailable => 'ఎల్లప్పుడు అందుబాటులో ఉంది.';

  @override
  String get importHistory => 'ఇతిహాసాన్ని దిగుమతి చేయండి';

  @override
  String get noImportsYet => 'ఇంకా దిగుమతులు లేవు';

  @override
  String get selectZipFileToImport => 'దిగుమతి చేయడానికి .zip ఫైల్‌ను ఎంచుకోండి!';

  @override
  String get otherDevicesComingSoon => 'ఇతర పరికరాలు త్వరలో రానున్నాయి';

  @override
  String get deleteAllLimitlessConversations => 'అన్ని Limitless సంభాషణలను తొలగించాలా?';

  @override
  String get deleteAllLimitlessWarning =>
      'ఇది Limitless నుండి దిగుమతి చేసిన అన్ని సంభాషణలను శాశ్వతంగా తొలగిస్తుంది. ఈ చర్యను తిరిగి చేయలేము.';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless సంభాషణలు తొలగించబడ్డాయి';
  }

  @override
  String get failedToDeleteConversations => 'సంభాషణలను తొలగించడం విఫలమైంది';

  @override
  String get deleteImportedData => 'దిగుమతి చేసిన డేటాను తొలగించండి';

  @override
  String get statusPending => 'పెండింగ్';

  @override
  String get statusProcessing => 'ప్రక్రియ చేయడం';

  @override
  String get statusCompleted => 'పూర్తయింది';

  @override
  String get statusFailed => 'విఫలమైంది';

  @override
  String nConversations(int count) {
    return '$count సంభాషణలు';
  }

  @override
  String get pleaseEnterName => 'దయచేసి పేరు నమోదు చేయండి';

  @override
  String get nameMustBeBetweenCharacters => 'పేరు 2 నుండి 40 అక్షరాల మధ్య ఉండాలి';

  @override
  String get deleteSampleQuestion => 'నమూనాను తొలగించాలా?';

  @override
  String deleteSampleConfirmation(String name) {
    return '$name యొక్క నమూనాను తొలగించాలని మీరు చెప్పుకుంటున్నారా?';
  }

  @override
  String get confirmDeletion => 'తొలగింపును నిర్ధారించండి';

  @override
  String deletePersonConfirmation(String name) {
    return '$name ను తొలగించాలని మీరు చెప్పుకుంటున్నారా? ఇది సంబంధిత అన్ని ప్రసంగ నమూనాలను కూడా తీసివేస్తుంది.';
  }

  @override
  String get howItWorksTitle => 'ఇది ఎలా పనిచేస్తుంది?';

  @override
  String get howPeopleWorks =>
      'ఒక వ్యక్తి సృష్టించిన తర్వాత, మీరు సంభాషణ ట్రాన్‌స్క్రిప్ట్‌కు వెళ్లవచ్చు మరియు వారిని తమ సంబంధిత సెగ్మెంట్‌లకు కేటాయించవచ్చు, ఈ విధంగా Omi వారి ప్రసంగాన్ని కూడా గుర్తించగలుగుతుంది!';

  @override
  String get tapToDelete => 'తొలగించడానికి ట్యాప్ చేయండి';

  @override
  String get newTag => 'NEW';

  @override
  String get needHelpChatWithUs => 'సహాయం అవసరమైనా? మేతో చాట్ చేయండి';

  @override
  String get localStorageEnabled => 'స్థానిక నిల్వ సక్షమం చేయబడింది';

  @override
  String get localStorageDisabled => 'స్థానిక నిల్వ నిలిపివేయబడింది';

  @override
  String failedToUpdateSettings(String error) {
    return 'సెట్టింగ్‌లను అప్‌డేట్ చేయడం విఫలమైంది: $error';
  }

  @override
  String get privacyNotice => 'గోప్యతా నోటిసు';

  @override
  String get recordingsMayCaptureOthers =>
      'రికార్డింగ్‌లు ఇతరుల గొంతులను సంగ్రహించవచ్చు. ఎనబుల్ చేయడానికి ముందు అన్ని భాగస్వాములకు సమ్మతి ఉందని నిర్ధారించుకోండి.';

  @override
  String get enable => 'సక్షమం చేయండి';

  @override
  String get storeAudioOnPhone => 'ఆడియోను ఫోన్‌లో నిల్వ చేయండి';

  @override
  String get on => 'ఆన్';

  @override
  String get storeAudioDescription =>
      'అన్ని ఆడియో రికార్డింగ్‌లను మీ ఫోన్‌లో స్థానికంగా నిల్వ చేయండి. నిలిపివేయబడినప్పుడు, నిల్వ స్థలాన్ని సేవ చేయడానికి విఫల అప్‌లోడ్‌లు మాత్రమే ఉంటాయి.';

  @override
  String get enableLocalStorage => 'స్థానిక నిల్వను సక్షమం చేయండి';

  @override
  String get cloudStorageEnabled => 'క్లౌడ్ నిల్వ సక్షమం చేయబడింది';

  @override
  String get cloudStorageDisabled => 'క్లౌడ్ నిల్వ నిలిపివేయబడింది';

  @override
  String get enableCloudStorage => 'క్లౌడ్ నిల్వను సక్షమం చేయండి';

  @override
  String get storeAudioOnCloud => 'ఆడియోను క్లౌడ్‌లో నిల్వ చేయండి';

  @override
  String get cloudStorageDialogMessage =>
      'మీ రియల్-టైమ్ రికార్డింగ్‌లు మీరు మాట్లాడేటప్పుడు ఖాతగత క్లౌడ్ నిల్వలో నిల్వ చేయబడుతాయి.';

  @override
  String get storeAudioCloudDescription =>
      'మీ రియల్-టైమ్ రికార్డింగ్‌లను ఖాతగత క్లౌడ్ నిల్వలో నిల్వ చేయండి మీరు మాట్లాడేటప్పుడు. ఆడియో రియల్-టైమ్‌లో సురక్షితంగా సంగ్రహించబడి సేవ చేయబడుతుంది.';

  @override
  String get downloadingFirmware => 'ఫర్మ్‌వేర్‌ను డౌన్‌లోడ్ చేస్తోంది';

  @override
  String get installingFirmware => 'ఫర్మ్‌వేర్‌ను ఇన్‌స్టాల్ చేస్తోంది';

  @override
  String get firmwareUpdateWarning =>
      'అనువర్తనాన్ని మూసివేయవద్దు లేదా పరికరాన్ని ఆపివేయవద్దు. ఇది మీ పరికరాన్ని నష్టపరిచేవచ్చు.';

  @override
  String get firmwareUpdated => 'ఫర్మ్‌వేర్ అప్‌డేట్ చేయబడింది';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'అప్‌డేట్‌ను పూర్తి చేయడానికి దయచేసి మీ $deviceName ను పునరారంభించండి.';
  }

  @override
  String get yourDeviceIsUpToDate => 'మీ పరికరం నవీనమైనది';

  @override
  String get currentVersion => 'ప్రస్తుత సంస్కరణ';

  @override
  String get latestVersion => 'సర్వశేష సంస్కరణ';

  @override
  String get whatsNew => 'ఇది ఏమిటి?';

  @override
  String get installUpdate => 'అప్‌డేట్‌ను ఇన్‌స్టాల్ చేయండి';

  @override
  String get updateNow => 'ఇప్పుడు అప్‌డేట్ చేయండి';

  @override
  String get updateGuide => 'అప్‌డేట్ గైడ్';

  @override
  String get checkingForUpdates => 'అప్‌డేట్‌ల కోసం తనిఖీ చేస్తోంది';

  @override
  String get checkingFirmwareVersion => 'ఫర్మ్‌వేర్ సంస్కరణను తనిఖీ చేస్తోంది...';

  @override
  String get firmwareUpdate => 'ఫర్మ్‌వేర్ అప్‌డేట్';

  @override
  String get payments => 'చెల్లింపులు';

  @override
  String get connectPaymentMethodInfo =>
      'మీ అనువర్తనాల కోసం చెల్లింపులను స్వీకరించడం ప్రారంభించడానికి దిగువ చెల్లింపు పద్ధతిని కనెక్ట్ చేయండి.';

  @override
  String get selectedPaymentMethod => 'ఎంచుకున్న చెల్లింపు పద్ధతి';

  @override
  String get availablePaymentMethods => 'అందుబాటులో ఉన్న చెల్లింపు పద్ధతులు';

  @override
  String get activeStatus => 'క్రియాశీల';

  @override
  String get connectedStatus => 'అనుసంధానించబడింది';

  @override
  String get notConnectedStatus => 'అనుసంధానించబడలేదు';

  @override
  String get setActive => 'క్రియాశీలం చేయండి';

  @override
  String get getPaidThroughStripe => 'Stripe ద్వారా మీ అనువర్తన విక్రయాలకు చెల్లింపు పొందండి';

  @override
  String get monthlyPayouts => 'నెలవారీ చెల్లింపులు';

  @override
  String get monthlyPayoutsDescription =>
      'మీ ఖాతాకు నేరుగా నెలవారీ చెల్లింపులను స్వీకరించండి మీరు \$ 10 లో సంపాదన చేసినప్పుడు';

  @override
  String get secureAndReliable => 'సురక్షితమైన మరియు నమ్మకమైన';

  @override
  String get stripeSecureDescription =>
      'Stripe మీ అనువర్తన రాజస్వ యొక్క సురక్షితమైన మరియు సమయోచిత బదిలీలను నిర్ధారిస్తుంది';

  @override
  String get selectYourCountry => 'మీ దేశాన్ని ఎంచుకోండి';

  @override
  String get countrySelectionPermanent => 'మీ దేశ ఎంపిక శాశ్వతమైనది మరియు తరువాత మార్చలేము.';

  @override
  String get byClickingConnectNow => '\"ఇప్పుడే కనెక్ట్ చేయండి\" చేయడం ద్వారా మీరు సమ్మతి చెప్పుకుంటున్నారు';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe కనెక్ట్‌ఫలితం ఖాతా ఒప్పందం';

  @override
  String get errorConnectingToStripe => 'Stripe కు కనెక్ట్ చేయడంలో ఎర్రర్! దయచేసి తరువాత మళ్లీ ప్రయత్నించండి.';

  @override
  String get connectingYourStripeAccount => 'మీ Stripe ఖాతాను కనెక్ట్ చేస్తోంది';

  @override
  String get stripeOnboardingInstructions =>
      'దయచేసి మీ బ్రౌజర్‌లో Stripe ఆన్‌బోర్డింగ్ ప్రక్రియను పూర్తి చేయండి. ఈ పేజీ పూర్తయిన తర్వాత స్వయంచాలకంగా అప్‌డేట్ చేయబడుతుంది.';

  @override
  String get failedTryAgain => 'విఫలమైనా? మళ్లీ ప్రయత్నించండి';

  @override
  String get illDoItLater => 'నేను తరువాత చేస్తాను';

  @override
  String get successfullyConnected => 'విజయవంతంగా కనెక్ట్ చేయబడింది!';

  @override
  String get stripeReadyForPayments =>
      'మీ Stripe ఖాతా ఇప్పుడు చెల్లింపులను స్వీకరించడానికి సిద్ధంగా ఉంది. మీరు వెంటనే మీ అనువర్తన విక్రయాల నుండి సంపాదించడం ప్రారంభించవచ్చు.';

  @override
  String get updateStripeDetails => 'Stripe విశ్లేషణలను అప్‌డేట్ చేయండి';

  @override
  String get errorUpdatingStripeDetails =>
      'Stripe విశ్లేషణలను అప్‌డేట్ చేయడంలో ఎర్రర్! దయచేసి తరువాత మళ్లీ ప్రయత్నించండి.';

  @override
  String get updatePayPal => 'PayPal ను అప్‌డేట్ చేయండి';

  @override
  String get setUpPayPal => 'PayPal ను సెటప్ చేయండి';

  @override
  String get updatePayPalAccountDetails => 'మీ PayPal ఖాతా విశ్లేషణలను అప్‌డేట్ చేయండి';

  @override
  String get connectPayPalToReceivePayments =>
      'మీ అనువర్తనాల కోసం చెల్లింపులను స్వీకరించడం ప్రారంభించడానికి మీ PayPal ఖాతాను కనెక్ట్ చేయండి';

  @override
  String get paypalEmail => 'PayPal ఇమెయిల్';

  @override
  String get paypalMeLink => 'PayPal.me లింక్';

  @override
  String get stripeRecommendation =>
      'Stripe మీ దేశంలో అందుబాటులో ఉంటే, వేగవంతమైన మరియు సులభమైన చెల్లింపుల కోసం దానిని ఉపయోగించమని మేము ఆsusan్నిగా సిఫారసు చేస్తాము.';

  @override
  String get updatePayPalDetails => 'PayPal విశ్లేషణలను అప్‌డేట్ చేయండి';

  @override
  String get savePayPalDetails => 'PayPal విశ్లేషణలను సేవ చేయండి';

  @override
  String get pleaseEnterPayPalEmail => 'దయచేసి మీ PayPal ఇమెయిల్ నమోదు చేయండి';

  @override
  String get pleaseEnterPayPalMeLink => 'దయచేసి మీ PayPal.me లింక్ నమోదు చేయండి';

  @override
  String get doNotIncludeHttpInLink => 'లింక్‌లో http లేదా https లేదా www చేర్చవద్దు';

  @override
  String get pleaseEnterValidPayPalMeLink => 'దయచేసి చెల్లుబాటు PayPal.me లింక్ నమోదు చేయండి';

  @override
  String get pleaseEnterValidEmail => 'దయచేసి చెల్లుబాటు ఇమెయిల్ చిరునామా నమోదు చేయండి';

  @override
  String get syncingYourRecordings => 'మీ రికార్డింగ్‌లను సమకాలీకరిస్తోంది';

  @override
  String get syncYourRecordings => 'మీ రికార్డింగ్‌లను సమకాలీకరించండి';

  @override
  String get syncNow => 'ఇప్పుడు సమకాలీకరించండి';

  @override
  String get error => 'ఎర్రర్';

  @override
  String get speechSamples => 'ప్రసంగ నమూనాలు';

  @override
  String additionalSampleIndex(String index) {
    return 'అదనపు నమూనా $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'వ్యవధి: $seconds సెకన్లు';
  }

  @override
  String get additionalSpeechSampleRemoved => 'అదనపు ప్రసంగ నమూనా తీసివేయబడింది';

  @override
  String get consentDataMessage =>
      'కొనసాగించడం ద్వారా, మీ సంభాషణలు, రికార్డింగ్‌లు మరియు వ్యక్తిగత సమాచారం మా సర్వర్‌లలో సురక్షితంగా నిల్వ చేయబడతాయి. మీ ఆడియో రికార్డింగ్‌లు మరియు ట్రాన్‌స్క్రిప్ట్‌లు థర్డ్-పార్టీ AI సేవల ద్వారా ప్రాసెస్ చేయబడతాయి (ట్రాన్‌స్క్రిప్షన్ కోసం Deepgram మరియు విశ్లేషణ కోసం OpenAI సహా) AI-ఆధారిత అంతర్దృష్టులను అందించడానికి మరియు అన్ని యాప్ ఫీచర్‌లను ప్రారంభించడానికి.';

  @override
  String get tasksEmptyStateMessage =>
      'మీ సంభాషణల నుండి చర్యలు ఇక్కడ కనిపిస్తాయి.\\n+ నిర్ణయం చేయడానికి ట్యాప్ చేయండి.';

  @override
  String get clearChatAction => 'చాట్‌ను క్లియర్ చేయండి';

  @override
  String get enableApps => 'అనువర్తనాలను సక్షమం చేయండి';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'మరిన్ని చూపించు ↓';

  @override
  String get showLess => 'తక్కువ చూపించు ↑';

  @override
  String get loadingYourRecording => 'మీ రికార్డింగ్‌ను లోడ్ చేస్తోంది...';

  @override
  String get photoDiscardedMessage => 'ఈ ఫోటో ముఖ్యమైనది కానందున విస్మరించబడింది.';

  @override
  String get analyzing => 'విశ్లేషించిస్తోంది...';

  @override
  String get searchCountries => 'దేశాలను శోధించండి';

  @override
  String get checkingAppleWatch => 'Apple Watch ని తనిఖీ చేస్తోంది...';

  @override
  String get installOmiOnAppleWatch => 'Omi ని మీ\\nApple Watch లో ఇన్‌స్టాల్ చేయండి';

  @override
  String get installOmiOnAppleWatchDescription =>
      'మీ Apple Watch ని Omi ఉపయోగించడానికి, మీరు ముందుగా మీ గడియారం మీద Omi అనువర్తనాన్ని ఇన్‌స్టాల్ చేయాలి.';

  @override
  String get openOmiOnAppleWatch => 'Omi ని మీ\\nApple Watch లో తెరవండి';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi అనువర్తనం మీ Apple Watch న ఇన్‌స్టాల్ చేయబడింది. దానిని తెరవండి మరియు ప్రారంభించడానికి ట్యాప్ చేయండి.';

  @override
  String get openWatchApp => 'గడియార అనువర్తనాన్ని తెరవండి';

  @override
  String get iveInstalledAndOpenedTheApp => 'నేను దానిని ఇన్‌స్టాల్ చేసాను మరియు అనువర్తనాన్ని తెరిచాను';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch అనువర్తనాన్ని తెరవలేకపోయాను. దయచేసి మీ Apple Watch పై గడియార అనువర్తనాన్ని నిర్ణయం చేసి \"అందుబాటులో ఉన్న అనువర్తనాలు\" విభాగం నుండి Omi ని ఇన్‌స్టాల్ చేయండి.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch విజయవంతంగా కనెక్ట్ చేయబడింది!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ఇప్పటికీ నిరన్తరం కనబడటం లేదు. దయచేసి Omi అనువర్తనం మీ గడియారం మీద తెరిచి ఉందని నిర్ధారించుకోండి.';

  @override
  String errorCheckingConnection(String error) {
    return 'కనెక్షన్‌ను తనిఖీ చేయడంలో ఎర్రర్: $error';
  }

  @override
  String get muted => 'మిటమిటించింది';

  @override
  String get processNow => 'ఇప్పుడు ప్రక్రియ చేయండి';

  @override
  String get finishedConversation => 'సంభాషణ పూర్తయిందా?';

  @override
  String get stopRecordingConfirmation =>
      'రికార్డింగ్‌ను ఆపివేసి సంభాషణను ఇప్పుడే సారాంశం చేయాలని మీరు చెప్పుకుంటున్నారా?';

  @override
  String get conversationEndsManually => 'సంభాషణ కేవలం నిర్ణయం చేయడం ద్వారా ముగుస్తుంది.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'సంభాషణ $minutes నిమిషం$suffix యొక్క ప్రసంగం లేని తరువాత సారాంశం చేయబడుతుంది.';
  }

  @override
  String get dontAskAgain => 'నన్ను మళ్లీ అడగవద్దు';

  @override
  String get waitingForTranscriptOrPhotos => 'ట్రాన్‌స్క్రిప్ట్ లేదా ఫోటోల కోసం ఎదురుచూస్తోంది...';

  @override
  String get noSummaryYet => 'ఇంకా సారాంశం లేదు';

  @override
  String hints(String text) {
    return 'సూచనలు: $text';
  }

  @override
  String get testConversationPrompt => 'సంభాషణ ప్రాంప్ట్‌ను పరీక్షించండి';

  @override
  String get prompt => 'ప్రాంప్ట్';

  @override
  String get result => 'ఫలితం:';

  @override
  String get compareTranscripts => 'ట్రాన్‌స్క్రిప్ట్‌లను పోల్చండి';

  @override
  String get notHelpful => 'సహాయకరం కాదు';

  @override
  String get exportTasksWithOneTap => 'ఒక ట్యాప్‌తో చర్యలను ఎగుమతి చేయండి!';

  @override
  String get inProgress => 'సిద్ధతలో ఉంది';

  @override
  String get photos => 'ఫోటోలు';

  @override
  String get rawData => 'ముడి డేటా';

  @override
  String get content => 'సামగ్రి';

  @override
  String get noContentToDisplay => 'చూపించడానికి సామగ్రి లేదు';

  @override
  String get noSummary => 'సారాంశం లేదు';

  @override
  String get updateOmiFirmware => 'Omi ఫర్మ్‌వేర్‌ను అప్‌డేట్ చేయండి';

  @override
  String get anErrorOccurredTryAgain => 'ఎర్రర్ సంభవించింది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get welcomeBackSimple => 'తిరిగి స్వాగతం';

  @override
  String get addVocabularyDescription => 'Omi ట్రాన్‌స్క్రిప్షన్ సమయంలో గుర్తించాల్సిన పదాలను జోడించండి.';

  @override
  String get enterWordsCommaSeparated => 'పదాలను నమోదు చేయండి (కామా విభజించినవి)';

  @override
  String get whenToReceiveDailySummary => 'మీ నిత్య సారాంశం ఎప్పుడు స్వీకరించాలి';

  @override
  String get checkingNextSevenDays => 'తరువాతి 7 రోజులను తనిఖీ చేస్తోంది';

  @override
  String failedToDeleteError(String error) {
    return 'తొలగించడం విఫలమైంది: $error';
  }

  @override
  String get developerApiKeys => 'డెవలపర్ API కీలు';

  @override
  String get noApiKeysCreateOne => 'API కీలు లేవు. ప్రారంభించడానికి ఒక సృష్టించండి.';

  @override
  String get commandRequired => '⌘ అవసరం';

  @override
  String get spaceKey => 'స్థలం';

  @override
  String loadMoreRemaining(String count) {
    return 'మరిన్ని లోడ్ చేయండి ($count మిగిలి ఉన్నాయి)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'టాప్ $percentile% యూజర్';
  }

  @override
  String get wrappedMinutes => 'నిమిషాలు';

  @override
  String get wrappedConversations => 'సంభాషణలు';

  @override
  String get wrappedDaysActive => 'రోజులు సక్రియమైనవి';

  @override
  String get wrappedYouTalkedAbout => 'మీరు చెప్పుకున్నవి';

  @override
  String get wrappedActionItems => 'చర్య అంశాలు';

  @override
  String get wrappedTasksCreated => 'సృష్టించిన చర్యలు';

  @override
  String get wrappedCompleted => 'పూర్తయింది';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% పూర్తతర రేటు';
  }

  @override
  String get wrappedYourTopDays => 'మీ టాప్ రోజులు';

  @override
  String get wrappedBestMoments => 'ఉత్తమ క్షణాలు';

  @override
  String get wrappedMyBuddies => 'నా మిత్రులు';

  @override
  String get wrappedCouldntStopTalkingAbout => 'మాట్లాడటం ఆపివేయలేకపోయాను';

  @override
  String get wrappedShow => 'SHOW';

  @override
  String get wrappedMovie => 'MOVIE';

  @override
  String get wrappedBook => 'BOOK';

  @override
  String get wrappedCelebrity => 'CELEBRITY';

  @override
  String get wrappedFood => 'FOOD';

  @override
  String get wrappedMovieRecs => '친구లకు చలన చిత్రం సిఫారసులు';

  @override
  String get wrappedBiggest => 'అతిపెద్ద';

  @override
  String get wrappedStruggle => 'సంఘర్షణ';

  @override
  String get wrappedButYouPushedThrough => 'కానీ మీరు చేసుకున్నారు 💪';

  @override
  String get wrappedWin => 'గెలుపు';

  @override
  String get wrappedYouDidIt => 'మీరు చేసారు! 🎉';

  @override
  String get wrappedTopPhrases => 'టాప్ 5 పదబంధాలు';

  @override
  String get wrappedMins => 'నిమిషాలు';

  @override
  String get wrappedConvos => 'సంభాషణలు';

  @override
  String get wrappedDays => 'రోజులు';

  @override
  String get wrappedMyBuddiesLabel => 'నా మిత్రులు';

  @override
  String get wrappedObsessionsLabel => 'అబిష్టాలు';

  @override
  String get wrappedStruggleLabel => 'సంఘర్షణ';

  @override
  String get wrappedWinLabel => 'గెలుపు';

  @override
  String get wrappedTopPhrasesLabel => 'టాప్ పదబంధాలు';

  @override
  String get wrappedLetsHitRewind => 'మీ విషయానికి రీవైండ్ వేయండి';

  @override
  String get wrappedGenerateMyWrapped => 'నా Wrapped రూపొందించండి';

  @override
  String get wrappedProcessingDefault => 'ప్రక్రియ చేయడం...';

  @override
  String get wrappedCreatingYourStory => 'మీ\\n2025 కథను సృష్టిస్తోంది...';

  @override
  String get wrappedSomethingWentWrong => 'ఏదో\\nపొరపాటు జరిగింది';

  @override
  String get wrappedAnErrorOccurred => 'ఎర్రర్ సంభవించింది';

  @override
  String get wrappedTryAgain => 'మళ్లీ ప్రయత్నించండి';

  @override
  String get wrappedNoDataAvailable => 'డేటా అందుబాటులో లేదు';

  @override
  String get wrappedOmiLifeRecap => 'Omi జీవితం పునర్బడ్డ';

  @override
  String get wrappedSwipeUpToBegin => 'ప్రారంభించడానికి పైకి స్వైప్ చేయండి';

  @override
  String get wrappedShareText => 'నా 2025, Omi చేత గుర్తుచేసుకోబడింది ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'భాగస్వామ్యం చేయడం విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get wrappedFailedToStartGeneration => 'రూపొందించడం ప్రారంభించడం విఫలమైంది. దయచేసి మళ్లీ ప్రయత్నించండి.';

  @override
  String get wrappedStarting => 'ప్రారంభం...';

  @override
  String get wrappedShare => 'భాగస్వామ్యం చేయండి';

  @override
  String get wrappedShareYourWrapped => 'మీ Wrapped భాగస్వామ్యం చేయండి';

  @override
  String get wrappedMy2025 => 'నా 2025';

  @override
  String get wrappedRememberedByOmi => 'Omi చేత గుర్తుచేసుకోబడింది';

  @override
  String get wrappedMostFunDay => 'చాలా సరదా';

  @override
  String get wrappedMostProductiveDay => 'చాలా ఉత్పాదక';

  @override
  String get wrappedMostIntenseDay => 'చాలా తీవ్రమైన';

  @override
  String get wrappedFunniestMoment => 'చాలా వినోదభరితమైన';

  @override
  String get wrappedMostCringeMoment => 'చాలా గజగజా';

  @override
  String get wrappedMinutesLabel => 'నిమిషాలు';

  @override
  String get wrappedConversationsLabel => 'సంభాషణలు';

  @override
  String get wrappedDaysActiveLabel => 'రోజులు సక్రియమైనవి';

  @override
  String get wrappedTasksGenerated => 'రూపొందించిన చర్యలు';

  @override
  String get wrappedTasksCompleted => 'పూర్తి చేసిన చర్యలు';

  @override
  String get wrappedTopFivePhrases => 'టాప్ 5 పదబంధాలు';

  @override
  String get wrappedAGreatDay => 'గొప్ప రోజు';

  @override
  String get wrappedGettingItDone => 'దానిని పూర్తి చేయడం';

  @override
  String get wrappedAChallenge => 'ఒక సవాలు';

  @override
  String get wrappedAHilariousMoment => 'ఒక వినోదభరితమైన క్షణం';

  @override
  String get wrappedThatAwkwardMoment => 'ఆ ఓపెన్‌క్లోయ్‌ క్షణం';

  @override
  String get wrappedYouHadFunnyMoments => 'ఈ సంవత్సరం మీకు కొన్ని వినోదభరితమైన క్షణాలు ఉన్నాయి!';

  @override
  String get wrappedWeveAllBeenThere => 'మేము ప్రతిఒక్కరు అక్కడ ఉన్నాము!';

  @override
  String get wrappedFriend => 'మిత్రుడు';

  @override
  String get wrappedYourBuddy => 'మీ సహచరుడు!';

  @override
  String get wrappedNotMentioned => 'ప్రస్తావించని';

  @override
  String get wrappedTheHardPart => 'కష్ట భాగం';

  @override
  String get wrappedPersonalGrowth => 'వ్యక్తిగత వృద్ధి';

  @override
  String get wrappedFunDay => 'సరదా';

  @override
  String get wrappedProductiveDay => 'ఉత్పాదక';

  @override
  String get wrappedIntenseDay => 'తీవ్రమైన';

  @override
  String get wrappedFunnyMomentTitle => 'వినోదభరితమైన క్షణం';

  @override
  String get wrappedCringeMomentTitle => 'గజగజా క్షణం';

  @override
  String get wrappedYouTalkedAboutBadge => 'మీరు చెప్పుకున్నవి';

  @override
  String get wrappedCompletedLabel => 'పూర్తయింది';

  @override
  String get wrappedMyBuddiesCard => 'నా మిత్రులు';

  @override
  String get wrappedBuddiesLabel => 'మిత్రులు';

  @override
  String get wrappedObsessionsLabelUpper => 'అబిష్టాలు';

  @override
  String get wrappedStruggleLabelUpper => 'సంఘర్షణ';

  @override
  String get wrappedWinLabelUpper => 'గెలుపు';

  @override
  String get wrappedTopPhrasesLabelUpper => 'టాప్ పదబంధాలు';

  @override
  String get wrappedYourHeader => 'మీ';

  @override
  String get wrappedTopDaysHeader => 'టాప్ రోజులు';

  @override
  String get wrappedYourTopDaysBadge => 'మీ టాప్ రోజులు';

  @override
  String get wrappedBestHeader => 'ఉత్తమ';

  @override
  String get wrappedMomentsHeader => 'క్షణాలు';

  @override
  String get wrappedBestMomentsBadge => 'ఉత్తమ క్షణాలు';

  @override
  String get wrappedBiggestHeader => 'అతిపెద్ద';

  @override
  String get wrappedStruggleHeader => 'సంఘర్షణ';

  @override
  String get wrappedWinHeader => 'గెలుపు';

  @override
  String get wrappedButYouPushedThroughEmoji => 'కానీ మీరు చేసుకున్నారు 💪';

  @override
  String get wrappedYouDidItEmoji => 'మీరు చేసారు! 🎉';

  @override
  String get wrappedHours => 'గంటలు';

  @override
  String get wrappedActions => 'చర్యలు';

  @override
  String get multipleSpeakersDetected => 'బహుళ సంభాషణదారులు గుర్తించబడ్డారు';

  @override
  String get multipleSpeakersDescription =>
      'రికార్డింగ్‌లో బహుళ సంభాషణదారులు ఉన్నట్లు కనిపిస్తుంది. దయచేసి మీరు నిశ్శబ్దమైన ప్రదేశంలో ఉన్నారని నిర్ధారించుకోండి మరియు మళ్లీ ప్రయత్నించండి.';

  @override
  String get invalidRecordingDetected => 'చెల్లని రికార్డింగ్ గుర్తించబడింది';

  @override
  String get notEnoughSpeechDescription =>
      'తగినంత ప్రసంగం గుర్తించబడలేదు. దయచేసి మరిన్ని మాట్లాడండి మరియు మళ్లీ ప్రయత్నించండి.';

  @override
  String get speechDurationDescription =>
      'దయచేసి కనీసం 5 సెకన్లు మరియు 90 కంటే ఎక్కువ లేకుండా మీరు నిశ్చయంగా మాట్లాడండి.';

  @override
  String get connectionLostDescription =>
      'సংযోగం విచ్ఛిన్నమైంది. దయచేసి మీ ఇంటర్నెట్ సংయోగాన్ని తనిఖీ చేసి మరలా ప్రయత్నించండి.';

  @override
  String get howToTakeGoodSample => 'మంచి నమూనాను ఎలా తీసుకోవాలి?';

  @override
  String get goodSampleInstructions =>
      '1. మీరు నిశ్చితంగా నిశ్చుప్త స్థలంలో ఉన్నారని నిర్ధారించుకోండి.\n2. స్పష్టంగా మరియు సహజంగా మాట్లాడండి.\n3. మీ పరికరం దాని సహజ స్థితిలో, మీ మెడపై ఉందని నిర్ధారించుకోండి.\n\nఇది సృష్టించబడిన తర్వాత, మీరు ఎల్లప్పుడు దానిని మెరుగుపర్చవచ్చు లేదా మరలా చేయవచ్చు.';

  @override
  String get noDeviceConnectedUseMic => 'ఏ పరికరం కనెక్ట్ చేయబడలేదు. ఫోన్ మైక్రోఫోన్ను ఉపయోగిస్తుంది.';

  @override
  String get doItAgain => 'మరలా చేయండి';

  @override
  String get listenToSpeechProfile => 'నా చెప్పటిని వినండి ➡️';

  @override
  String get recognizingOthers => 'ఇతరులను గుర్తిస్తున్నాను 👀';

  @override
  String get keepGoingGreat => 'చేస్తూ ఉండండి, మీరు చక్కగా చేస్తున్నారు';

  @override
  String get somethingWentWrongTryAgain => 'ఏదో తప్పు జరిగింది! దయచేసి తరువాత మరలా ప్రయత్నించండి.';

  @override
  String get uploadingVoiceProfile => 'మీ వాయిస్ ప్రొఫైల్ అప్‌లోడ్ చేస్తున్నాను....';

  @override
  String get memorizingYourVoice => 'మీ వాయిస్ను గుర్తుంచుకుంటున్నాను...';

  @override
  String get personalizingExperience => 'మీ అనుభవాన్ని వ్యక్తిగతీకరిస్తున్నాను...';

  @override
  String get keepSpeakingUntil100 => 'మీరు 100% వరకు మాట్లాడుతూ ఉండండి.';

  @override
  String get greatJobAlmostThere => 'గొప్ప పని, మీరు దాదాపు అక్కడ ఉన్నారు';

  @override
  String get soCloseJustLittleMore => 'చాలా దగ్గర, కొంచెం మరిన్ని';

  @override
  String get notificationFrequency => 'నోటిఫికేషన్ ఫ్రీక్వెన్సీ';

  @override
  String get controlNotificationFrequency => 'Omi మీకు సక్రియ నోటిఫికేషన్‌లను ఎంత తరచుగా పంపుతుందో నియంత్రించండి.';

  @override
  String get yourScore => 'మీ స్కోర్';

  @override
  String get dailyScoreBreakdown => 'రోజువారీ స్కోర్ విభజన';

  @override
  String get todaysScore => 'ఈ రోజు స్కోర్';

  @override
  String get tasksCompleted => 'పూర్తిచేసిన పనులు';

  @override
  String get completionRate => 'పూర్తి రేటు';

  @override
  String get howItWorks => 'ఇది ఎలా పనిచేస్తుంది';

  @override
  String get dailyScoreExplanation =>
      'మీ రోజువారీ స్కోర్ టాస్క్ పూర్తికి ఆధారపడి ఉంటుంది. మీ స్కోర్ మెరుగుపర్చడానికి మీ పనులను పూర్తిచేయండి!';

  @override
  String get notificationFrequencyDescription =>
      'Omi మీకు సక్రియ నోటిఫికేషన్‌లు మరియు రిమైండర్‌లను ఎంత తరచుగా పంపుతుందో నియంత్రించండి.';

  @override
  String get sliderOff => 'ఆఫ్';

  @override
  String get sliderMax => 'గరిష్టం';

  @override
  String summaryGeneratedFor(String date) {
    return '$date కోసం సారాంశం రూపొందించబడింది';
  }

  @override
  String get failedToGenerateSummary =>
      'సారాంశం రూపొందించడంలో విఫలమైంది. ఆ రోజుకు మీకు సంభాషణలు ఉన్నాయని నిర్ధారించుకోండి.';

  @override
  String get recap => 'పరిశీలన';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" తొలగించండి';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count సంభాషణలను లోకి తరలించండి:';
  }

  @override
  String get noFolder => 'ఫోల్డర్ లేదు';

  @override
  String get removeFromAllFolders => 'అన్ని ఫోల్డర్‌ల నుండి తీసివేయండి';

  @override
  String get buildAndShareYourCustomApp => 'మీ కస్టమ్ అ్యాప్‌ను నిర్మించండి మరియు షేర్ చేయండి';

  @override
  String get searchAppsPlaceholder => '1500+ ఆప్‌ల కోసం శోధించండి';

  @override
  String get filters => 'ఫిల్టర్‌లు';

  @override
  String get frequencyOff => 'ఆఫ్';

  @override
  String get frequencyMinimal => 'కనిష్ట';

  @override
  String get frequencyLow => 'తక్కువ';

  @override
  String get frequencyBalanced => 'సమతుల్యమైన';

  @override
  String get frequencyHigh => 'ఎక్కువ';

  @override
  String get frequencyMaximum => 'గరిష్టం';

  @override
  String get frequencyDescOff => 'సక్రియ నోటిఫికేషన్‌లు లేదు';

  @override
  String get frequencyDescMinimal => 'కేవలం క్లిష్ట రిమైండర్‌లు';

  @override
  String get frequencyDescLow => 'ముఖ్యమైన నవీకరణలు మాత్రమే';

  @override
  String get frequencyDescBalanced => 'సాధారణ సహాయకర నట్టలు';

  @override
  String get frequencyDescHigh => 'తరచుగా చेకిన్‌లు';

  @override
  String get frequencyDescMaximum => 'నిరంతరం నిమగ్న ఉండండి';

  @override
  String get clearChatQuestion => 'చాట్ క్లియర్ చేయాలా?';

  @override
  String get syncingMessages => 'సర్వర్ తో సందేశాలను సమన్వయం చేస్తున్నాను...';

  @override
  String get chatAppsTitle => 'చాట్ ఆప్‌లు';

  @override
  String get selectApp => 'ఆ్యాప్ ఎంచుకోండి';

  @override
  String get noChatAppsEnabled =>
      'ఏ చాట్ ఆప్‌లు ప్రారంభం కాలేదు.\n\"ఆప్‌లను ప్రారంభించండి\" నొక్కండి కొన్నింటిని జోడించటానికి.';

  @override
  String get disable => 'నిలిపివేయండి';

  @override
  String get photoLibrary => 'ఫోటో లైబ్రరీ';

  @override
  String get chooseFile => 'ఫైల్ ఎంచుకోండి';

  @override
  String get connectAiAssistantsToYourData => 'AI సహాయకులను మీ డేటాకు కనెక్ట్ చేయండి';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'హోమ్‌పేజ్‌లో మీ వ్యక్తిగత లక్ష్యాలను ట్రాక్ చేయండి';

  @override
  String get deleteRecording => 'రికార్డింగ్ తొలగించండి';

  @override
  String get thisCannotBeUndone => 'ఇది రిసెట్ చేయబడదు.';

  @override
  String get sdCard => 'SD కార్డ్';

  @override
  String get fromSd => 'SD నుండి';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'ఫాస్ట్ ట్రాన్స్ఫర్';

  @override
  String get syncingStatus => 'సమన్వయం చేస్తున్నాను';

  @override
  String get failedStatus => 'విఫలమైంది';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'ట్రాన్స్ఫర్ పద్ధతి';

  @override
  String get fast => 'ఫాస్ట్';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'ఫోన్';

  @override
  String get cancelSync => 'సమన్వయం రద్దు చేయండి';

  @override
  String get cancelSyncMessage => 'ఇప్పటికే డౌన్‌లోడ్ చేసిన డేటా సేవ్ చేయబడుతుంది. మీరు తరువాత తిరిగి ప్రారంభించవచ్చు.';

  @override
  String get syncCancelled => 'సమన్వయం రద్దు చేయబడింది';

  @override
  String get deleteProcessedFiles => 'ప్రక్రియ చేసిన ఫైల్‌లను తొలగించండి';

  @override
  String get processedFilesDeleted => 'ప్రక్రియ చేసిన ఫైల్‌లు తొలగించబడ్డాయి';

  @override
  String get wifiEnableFailed => 'పరికరంపై WiFi ప్రారంభించడంలో విఫలమైంది. దయచేసి మరలా ప్రయత్నించండి.';

  @override
  String get deviceNoFastTransfer => 'మీ పరికరం ఫాస్ట్ ట్రాన్స్ఫర్ సపోర్ట్ చేయదు. బదులుగా బ్లూటూత్ ఉపయోగించండి.';

  @override
  String get enableHotspotMessage => 'దయచేసి మీ ఫోన్ యొక్క హాట్‌స్పాట్ ప్రారంభించండి మరియు మరలా ప్రయత్నించండి.';

  @override
  String get transferStartFailed => 'ట్రాన్స్ఫర్ ప్రారంభించడంలో విఫలమైంది. దయచేసి మరలా ప్రయత్నించండి.';

  @override
  String get deviceNotResponding => 'పరికరం ప్రతిస్పందించలేదు. దయచేసి మరలా ప్రయత్నించండి.';

  @override
  String get invalidWifiCredentials => 'చెల్లని WiFi నిఖర్చన. మీ హాట్‌స్పాట్ సెట్టింగ్‌లను తనిఖీ చేయండి.';

  @override
  String get wifiConnectionFailed => 'WiFi సంయోగం విఫలమైంది. దయచేసి మరలా ప్రయత్నించండి.';

  @override
  String get sdCardProcessing => 'SD కార్డ్ ప్రసంస్కరణ';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count రికార్డింగ్(ల) ప్రక్రియ చేస్తున్నాను. ఫైల్‌లు తరువాత SD కార్డ్ నుండి తీసివేయబడతాయి.';
  }

  @override
  String get process => 'ప్రక్రియ';

  @override
  String get wifiSyncFailed => 'WiFi సమన్వయం విఫలమైంది';

  @override
  String get processingFailed => 'ప్రసంస్కరణ విఫలమైంది';

  @override
  String get downloadingFromSdCard => 'SD కార్డ్ నుండి డౌన్‌లోడ్ చేస్తున్నాను';

  @override
  String processingProgress(int current, int total) {
    return '$current/$total ప్రక్రియ చేస్తున్నాను';
  }

  @override
  String conversationsCreated(int count) {
    return '$count సంభాషణలు సృష్టించబడ్డాయి';
  }

  @override
  String get internetRequired => 'ఇంటర్నెట్ అవసరం';

  @override
  String get processAudio => 'ఆడియో ప్రక్రియ చేయండి';

  @override
  String get start => 'ప్రారంభించండి';

  @override
  String get noRecordings => 'రికార్డింగ్‌లు లేవు';

  @override
  String get audioFromOmiWillAppearHere => 'మీ Omi పరికరం నుండి ఆడియో ఇక్కడ కనిపిస్తుంది';

  @override
  String get deleteProcessed => 'ప్రక్రియ చేసిన వాటిని తొలగించండి';

  @override
  String get tryDifferentFilter => 'వేరే ఫిల్టర్‌ను ప్రయత్నించండి';

  @override
  String get recordings => 'రికార్డింగ్‌లు';

  @override
  String get enableRemindersAccess =>
      'Apple రిమైండర్‌లను ఉపయోగించటానికి సెట్టింగ్‌లలో రిమైండర్‌ల యాక్సెస్‌ను ప్రారంభించండి';

  @override
  String todayAtTime(String time) {
    return '$time న ఈ రోజు';
  }

  @override
  String yesterdayAtTime(String time) {
    return '$time న నిన్న';
  }

  @override
  String get lessThanAMinute => 'ఒక నిమిషానికి తక్కువ';

  @override
  String estimatedMinutes(int count) {
    return '~$count నిమిషం(లు)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count గంట(లు)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'అంచనా: $time మిగిలి ఉంది';
  }

  @override
  String get summarizingConversation => 'సంభాషణను సంక్షిప్తీకరిస్తున్నాను...\nఇది కొన్ని సెకన్లు తీసుకోవచ్చు';

  @override
  String get resummarizingConversation => 'సంభాషణను తిరిగి సంక్షిప్తీకరిస్తున్నాను...\nఇది కొన్ని సెకన్లు తీసుకోవచ్చు';

  @override
  String get nothingInterestingRetry => 'ఏదీ ఆసక్తికరంగా లేనిది కనుగొనబడలేదు,\nమరలా ప్రయత్నించాలనుకుంటున్నారా?';

  @override
  String get noSummaryForConversation => 'ఈ సంభాషణకు\nసారాంశం లేదు.';

  @override
  String get unknownLocation => 'తెలియని స్థానం';

  @override
  String get couldNotLoadMap => 'మ్యాప్ లోడ్ చేయలేకపోయాను';

  @override
  String get triggerConversationIntegration => 'సంభాషణ సృష్టించిన ఇంటిగ్రేషన్‌ను ట్రిగ్గర్ చేయండి';

  @override
  String get webhookUrlNotSet => 'వెబ్‌హుక్ URL సెట్ చేయబడలేదు';

  @override
  String get setWebhookUrlInSettings =>
      'ఈ ఫీచర్‌ను ఉపయోగించటానికి దయచేసి డెవలపర్ సెట్టింగ్‌లలో వెబ్‌హుక్ URL సెట్ చేయండి.';

  @override
  String get sendWebUrl => 'వెబ్ url పంపండి';

  @override
  String get sendTranscript => 'ట్రాన్‌స్క్రిప్ట్ పంపండి';

  @override
  String get sendSummary => 'సారాంశం పంపండి';

  @override
  String get debugModeDetected => 'డీబగ్ మోడ్ గుర్తించబడింది';

  @override
  String get performanceReduced => 'పనితీరు 5-10x తగ్గించబడింది. రిలీజ్ మోడ్ ఉపయోగించండి.';

  @override
  String autoClosingInSeconds(int seconds) {
    return '${seconds}s లో స్వయంచాలకంగా ముగుస్తుంది';
  }

  @override
  String get modelRequired => 'మోడల్ అవసరం';

  @override
  String get downloadWhisperModel => 'దయచేసి సేవ్ చేయటానికి ముందు Whisper మోడల్ డౌన్‌లోడ్ చేయండి.';

  @override
  String get deviceNotCompatible => 'పరికరం సంబంధితమైనది కాదు';

  @override
  String get deviceRequirements => 'మీ పరికరం ఆన్-డివైస్ ట్రాన్‌స్క్రిప్షన్ కోసం అవసరాలను తీర్చట్లేదు.';

  @override
  String get willLikelyCrash => 'ఇది ప్రారంభం చేస్తే, ఆ్యాప్ క్రాష్ లేదా ఫ్రీజ్ కావచ్చు.';

  @override
  String get transcriptionSlowerLessAccurate =>
      'ట్రాన్‌స్క్రిప్షన్ గణనీయంగా నెమ్మదిగా మరియు తక్కువ ఖచ్చితమైనది ఉంటుంది.';

  @override
  String get proceedAnyway => 'ఏదేమైనా కొనసాగండి';

  @override
  String get olderDeviceDetected => 'పాతైన పరికరం గుర్తించబడింది';

  @override
  String get onDeviceSlower => 'ఆన్-డివైస్ ట్రాన్‌స్క్రిప్షన్ ఈ పరికరంపై నెమ్మదిగా ఉండవచ్చు.';

  @override
  String get batteryUsageHigher => 'బ్యాటరీ వినియోగం క్లౌడ్ ట్రాన్‌స్క్రిప్షన్ కంటే ఎక్కువ ఉంటుంది.';

  @override
  String get considerOmiCloud => 'మెరుగైన పనితీరు కోసం Omi క్లౌడ్ ఉపయోగించటను పరిగణించండి.';

  @override
  String get highResourceUsage => 'అధిక వనరు వినియోగం';

  @override
  String get onDeviceIntensive => 'ఆన్-డివైస్ ట్రాన్‌స్క్రిప్షన్ గణితశాస్త్రపరంగా సాధారణ.';

  @override
  String get batteryDrainIncrease => 'బ్యాటరీ డ్రెయిన్ గణనీయంగా పెరుగుతుంది.';

  @override
  String get deviceMayWarmUp => 'విస్తృత వినియోగ సమయంలో పరికరం వెచ్చగా ఉండవచ్చు.';

  @override
  String get speedAccuracyLower => 'క్లౌడ్ మోడల్‌ల కంటే వేగం మరియు ఖచ్చితత్వం తక్కువ ఉండవచ్చు.';

  @override
  String get cloudProvider => 'క్లౌడ్ ప్రదాత';

  @override
  String get premiumMinutesInfo =>
      'నెలకు 1,200 ప్రిమియం నిమిషాలు. ఆన్-డివైస్ ట్యాబ్ అపరిమిత ఉచిత ట్రాన్‌స్క్రిప్షన్ అందిస్తుంది.';

  @override
  String get viewUsage => 'వినియోగాన్ని చూడండి';

  @override
  String get localProcessingInfo =>
      'ఆడియో స్థానికంగా ప్రక్రియ చేయబడుతుంది. ఆఫ్‌లైన్‌లో పనిచేస్తుంది, మరింత ప్రైవేట్, కానీ ఎక్కువ బ్యాటరీని ఉపయోగిస్తుంది.';

  @override
  String get model => 'మోడల్';

  @override
  String get performanceWarning => 'పనితీరు హెచ్చరిక';

  @override
  String get largeModelWarning =>
      'ఈ మోడల్ పెద్దదిగా ఉంది మరియు మొబైల్ పరికరాలపై ఆ్యాప్ క్రాష్ లేదా చాలా నెమ్మదిగా అమలు చేయవచ్చు.\n\n\"small\" లేదా \"base\" సిఫారసు చేయబడుతుంది.';

  @override
  String get usingNativeIosSpeech => 'నేటివ్ iOS స్పీచ్ రికగ్నిషన్ ఉపయోగిస్తున్నాను';

  @override
  String get noModelDownloadRequired =>
      'మీ పరికరం యొక్క నేటివ్ స్పీచ్ ఇంజిన్ ఉపయోగించబడుతుంది. మోడల్ డౌన్‌లోడ్ అవసరం లేదు.';

  @override
  String get modelReady => 'మోడల్ సిద్ధం';

  @override
  String get redownload => 'తిరిగి డౌన్‌లోడ్ చేయండి';

  @override
  String get doNotCloseApp => 'దయచేసి ఆ్యాప్ ఆపివేయవద్దు.';

  @override
  String get downloading => 'డౌన్‌లోడ్ చేస్తున్నాను...';

  @override
  String get downloadModel => 'మోడల్ డౌన్‌లోడ్ చేయండి';

  @override
  String estimatedSize(String size) {
    return 'అంచనా పరిమాణం: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'అందుబాటులో ఉన్న స్థలం: $space';
  }

  @override
  String get notEnoughSpace => 'హెచ్చరిక: తగినంత స్థలం లేదు!';

  @override
  String get download => 'డౌన్‌లోడ్ చేయండి';

  @override
  String downloadError(String error) {
    return 'డౌన్‌లోడ్ ఎర్రర్: $error';
  }

  @override
  String get cancelled => 'రద్దు చేయబడింది';

  @override
  String get deviceNotCompatibleTitle => 'పరికరం సంబంధితమైనది కాదు';

  @override
  String get deviceNotMeetRequirements => 'మీ పరికరం ఆన్-డివైస్ ట్రాన్‌స్క్రిప్షన్ కోసం అవసరాలను తీర్చట్లేదు.';

  @override
  String get transcriptionSlowerOnDevice => 'ఆన్-డివైస్ ట్రాన్‌స్క్రిప్షన్ ఈ పరికరంపై నెమ్మదిగా ఉండవచ్చు.';

  @override
  String get computationallyIntensive => 'ఆన్-డివైస్ ట్రాన్‌స్క్రిప్షన్ గణితశాస్త్రపరంగా సాధారణ.';

  @override
  String get batteryDrainSignificantly => 'బ్యాటరీ డ్రెయిన్ గణనీయంగా పెరుగుతుంది.';

  @override
  String get premiumMinutesMonth =>
      'నెలకు 1,200 ప్రిమియం నిమిషాలు. ఆన్-డివైస్ ట్యాబ్ అపరిమిత ఉచిత ట్రాన్‌స్క్రిప్షన్ అందిస్తుంది. ';

  @override
  String get audioProcessedLocally =>
      'ఆడియో స్థానికంగా ప్రక్రియ చేయబడుతుంది. ఆఫ్‌లైన్‌లో పనిచేస్తుంది, మరింత ప్రైవేట్, కానీ ఎక్కువ బ్యాటరీని ఉపయోగిస్తుంది.';

  @override
  String get languageLabel => 'భాష';

  @override
  String get modelLabel => 'మోడల్';

  @override
  String get modelTooLargeWarning =>
      'ఈ మోడల్ పెద్దదిగా ఉంది మరియు మొబైల్ పరికరాలపై ఆ్యాప్ క్రాష్ లేదా చాలా నెమ్మదిగా అమలు చేయవచ్చు.\n\n\"small\" లేదా \"base\" సిఫారసు చేయబడుతుంది.';

  @override
  String get nativeEngineNoDownload =>
      'మీ పరికరం యొక్క నేటివ్ స్పీచ్ ఇంజిన్ ఉపయోగించబడుతుంది. మోడల్ డౌన్‌లోడ్ అవసరం లేదు.';

  @override
  String modelReadyWithName(String model) {
    return 'మోడల్ సిద్ధం ($model)';
  }

  @override
  String get reDownload => 'తిరిగి డౌన్‌లోడ్ చేయండి';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model డౌన్‌లోడ్ చేస్తున్నాను: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model ను సిద్ధం చేస్తున్నాను...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'డౌన్‌లోడ్ ఎర్రర్: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'అంచనా పరిమాణం: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'అందుబాటులో ఉన్న స్థలం: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omi యొక్క అంతర్నిర్మిత లైవ్ ట్రాన్‌స్క్రిప్షన్ స్వయంచాలక స్పీకర్ గుర్తింపు మరియు డయారిజేషన్‌తో రియల్-టైమ్ సంభాషణల కోసం ఆప్టిమైజ్ చేయబడింది.';

  @override
  String get reset => 'రీసెట్';

  @override
  String get useTemplateFrom => 'ఎక్కడ నుండి టెంప్లేట్ ఉపయోగించండి';

  @override
  String get selectProviderTemplate => 'ప్రదాత టెంప్లేట్ ఎంచుకోండి...';

  @override
  String get quicklyPopulateResponse => 'తెలిసిన ప్రదాత ప్రతిస్పందన ఫార్మాట్‌తో త్వరగా నింపండి';

  @override
  String get quicklyPopulateRequest => 'తెలిసిన ప్రదాత అభ్యర్థన ఫార్మాట్‌తో త్వరగా నింపండి';

  @override
  String get invalidJsonError => 'చెల్లని JSON';

  @override
  String downloadModelWithName(String model) {
    return 'మోడల్ డౌన్‌లోడ్ చేయండి ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'మోడల్: $model';
  }

  @override
  String get device => 'పరికరం';

  @override
  String get chatAssistantsTitle => 'చాట్ సహాయకులు';

  @override
  String get permissionReadConversations => 'సంభాషణలను చదవండి';

  @override
  String get permissionReadMemories => 'జ్ఞాపకాలను చదవండి';

  @override
  String get permissionReadTasks => 'పనులను చదవండి';

  @override
  String get permissionCreateConversations => 'సంభాషణలను సృష్టించండి';

  @override
  String get permissionCreateMemories => 'జ్ఞాపకాలను సృష్టించండి';

  @override
  String get permissionTypeAccess => 'యాక్సెస్';

  @override
  String get permissionTypeCreate => 'సృష్టించండి';

  @override
  String get permissionTypeTrigger => 'ట్రిగ్గర్';

  @override
  String get permissionDescReadConversations => 'ఈ ఆ్యాప్ మీ సంభాషణలకు యాక్సెస్ చేయగలదు.';

  @override
  String get permissionDescReadMemories => 'ఈ ఆ్యాప్ మీ జ్ఞాపకాలకు యాక్సెస్ చేయగలదు.';

  @override
  String get permissionDescReadTasks => 'ఈ ఆ్యాప్ మీ పనులకు యాక్సెస్ చేయగలదు.';

  @override
  String get permissionDescCreateConversations => 'ఈ ఆ్యాప్ కొత్త సంభాషణలను సృష్టించగలదు.';

  @override
  String get permissionDescCreateMemories => 'ఈ ఆ్యాప్ కొత్త జ్ఞాపకాలను సృష్టించగలదు.';

  @override
  String get realtimeListening => 'రియల్-టైమ్ వినడం';

  @override
  String get setupCompleted => 'పూర్తిచేయబడింది';

  @override
  String get pleaseSelectRating => 'దయచేసి రేటింగ్ ఎంచుకోండి';

  @override
  String get writeReviewOptional => 'రివ్యూ రాయండి (ఐచ్ఛికం)';

  @override
  String get setupQuestionsIntro =>
      'కొన్ని ప్రశ్నలకు సమాధానం ఇవ్వడం ద్వారా Omi మెరుగుపరచటానికి మాకు సహాయం చేయండి.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. మీరు ఏ పనిలో ఉన్నారు?';

  @override
  String get setupQuestionUsage => '2. మీరు మీ Omi ఎక్కడ ఉపయోగించటానికి ప్రణాళిక చేస్తున్నారు?';

  @override
  String get setupQuestionAge => '3. మీ వయస్సు పరిధి ఎంత?';

  @override
  String get setupAnswerAllQuestions => 'మీరు ఇంకా అన్ని ప్రశ్నలకు సమాధానం ఇవ్వలేదు! 🥺';

  @override
  String get setupSkipHelp => 'దానిని స్కిప్ చేయండి, నేను సహాయం చేయదలుకోవడం లేదు :C';

  @override
  String get professionEntrepreneur => 'ఉద్యోగస్థుడు';

  @override
  String get professionSoftwareEngineer => 'సాఫ్టువేర్ ఇంజనీర్';

  @override
  String get professionProductManager => 'ఉత్పత్తి నిర్వాహకుడు';

  @override
  String get professionExecutive => 'నిర్వాహకుడు';

  @override
  String get professionSales => 'విక్రయాలు';

  @override
  String get professionStudent => 'విద్యార్థి';

  @override
  String get usageAtWork => 'పని వద్ద';

  @override
  String get usageIrlEvents => 'IRL ఈవెంట్‌లు';

  @override
  String get usageOnline => 'ఆన్‌లైన్';

  @override
  String get usageSocialSettings => 'సామాజిక సెట్టింగ్‌లలో';

  @override
  String get usageEverywhere => 'ఎక్కడైనా';

  @override
  String get customBackendUrlTitle => 'కస్టమ్ బ్యాకెండ్ URL';

  @override
  String get backendUrlLabel => 'బ్యాకెండ్ URL';

  @override
  String get saveUrlButton => 'URL సేవ్ చేయండి';

  @override
  String get enterBackendUrlError => 'దయచేసి బ్యాకెండ్ URL నమోదు చేయండి';

  @override
  String get urlMustEndWithSlashError => 'URL \"/\" తో ముగియాలి';

  @override
  String get invalidUrlError => 'దయచేసి చెల్లుబాటు అయిన URL నమోదు చేయండి';

  @override
  String get backendUrlSavedSuccess => 'బ్యాకెండ్ URL విజయవంతంగా సేవ్ చేయబడింది!';

  @override
  String get signInTitle => 'సైన్ ఇన్';

  @override
  String get signInButton => 'సైన్ ఇన్';

  @override
  String get enterEmailError => 'దయచేసి మీ ఇమెయిల్ నమోదు చేయండి';

  @override
  String get invalidEmailError => 'దయచేసి చెల్లుబాటు అయిన ఇమెయిల్ నమోదు చేయండి';

  @override
  String get enterPasswordError => 'దయచేసి మీ పాస్‌వర్డ్ నమోదు చేయండి';

  @override
  String get passwordMinLengthError => 'పాస్‌వర్డ్ కనీసం 8 అక్షరాలుగా ఉండాలి';

  @override
  String get signInSuccess => 'సైన్ ఇన్ విజయవంతమైంది!';

  @override
  String get alreadyHaveAccountLogin => 'ఇప్పటికే ఖాతా ఉందా? లాగిన్ చేయండి';

  @override
  String get emailLabel => 'ఇమెయిల్';

  @override
  String get passwordLabel => 'పాస్‌వర్డ్';

  @override
  String get createAccountTitle => 'ఖాతా సృష్టించండి';

  @override
  String get nameLabel => 'పేరు';

  @override
  String get repeatPasswordLabel => 'పాస్‌వర్డ్ కోసం పునరావృత్తి చేయండి';

  @override
  String get signUpButton => 'సైన్ అప్';

  @override
  String get enterNameError => 'దయచేసి మీ పేరు నమోదు చేయండి';

  @override
  String get passwordsDoNotMatch => 'పాస్‌వర్డ్‌లు సరిపోలడం లేదు';

  @override
  String get signUpSuccess => 'సైన్ అప్ విజయవంతమైంది!';

  @override
  String get loadingKnowledgeGraph => 'జ్ఞాన గ్రాఫ్ లోడ్ చేస్తున్నాను...';

  @override
  String get noKnowledgeGraphYet => 'ఇంకా ఎటువంటి జ్ఞాన గ్రాఫ్ లేదు';

  @override
  String get buildingKnowledgeGraphFromMemories => 'జ్ఞాపకాల నుండి మీ జ్ఞాన గ్రాఫ్ నిర్మిస్తున్నాను...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'మీరు కొత్త జ్ఞాపకాలను సృష్టించినప్పుడు మీ జ్ఞాన గ్రాఫ్ స్వయంచాలకంగా నిర్మిస్తారు.';

  @override
  String get buildGraphButton => 'గ్రాఫ్ నిర్మించండి';

  @override
  String get checkOutMyMemoryGraph => 'నా జ్ఞాపక గ్రాఫ్ చూడండి!';

  @override
  String get getButton => 'పొందండి';

  @override
  String openingApp(String appName) {
    return '$appName ఆపరు చేస్తున్నాను...';
  }

  @override
  String get writeSomething => 'ఏదైనా రాయండి';

  @override
  String get submitReply => 'సమాధానం సమర్పించండి';

  @override
  String get editYourReply => 'మీ సమాధానాన్ని సవరించండి';

  @override
  String get replyToReview => 'రివ్యూకు సమాధానం ఇవ్వండి';

  @override
  String get rateAndReviewThisApp => 'ఈ ఆ్యాప్‌ను రేట్ చేయండి మరియు రివ్యూ చేయండి';

  @override
  String get noChangesInReview => 'రివ్యూలో ఏ మార్పులు లేదు.';

  @override
  String get cantRateWithoutInternet => 'ఇంటర్నెట్ సంయోగం లేకుండా ఆ్యాప్ రేట్ చేయలేరు.';

  @override
  String get appAnalytics => 'ఆ్యాప్ విశ్లేషణలు';

  @override
  String get learnMoreLink => 'మరిన్ని తెలుసుకోండి';

  @override
  String get moneyEarned => 'ఉపార్జించిన డబ్బు';

  @override
  String get writeYourReply => 'మీ సమాధానం రాయండి...';

  @override
  String get replySentSuccessfully => 'సమాధానం విజయవంతంగా పంపబడింది';

  @override
  String failedToSendReply(String error) {
    return 'సమాధానం పంపడంలో విఫలమైంది: $error';
  }

  @override
  String get send => 'పంపండి';

  @override
  String starFilter(int count) {
    return '$count స్టార్';
  }

  @override
  String get noReviewsFound => 'రివ్యూలు కనుగొనబడలేదు';

  @override
  String get editReply => 'సమాధానాన్ని సవరించండి';

  @override
  String get reply => 'సమాధానం';

  @override
  String starFilterLabel(int count) {
    return '$count స్టార్';
  }

  @override
  String get sharePublicLink => 'పబ్లిక్ లింక్ షేర్ చేయండి';

  @override
  String get connectedKnowledgeData => 'కనెక్ట్ చేసిన జ్ఞాన డేటా';

  @override
  String get enterName => 'పేరు నమోదు చేయండి';

  @override
  String get goal => 'లక్ష్యం';

  @override
  String get tapToTrackThisGoal => 'ఈ లక్ష్యం ట్రాక్ చేయటానికి నొక్కండి';

  @override
  String get tapToSetAGoal => 'లక్ష్యం సెట్ చేయటానికి నొక్కండి';

  @override
  String get processedConversations => 'ప్రక్రియ చేసిన సంభాషణలు';

  @override
  String get updatedConversations => 'నవీకరించిన సంభాషణలు';

  @override
  String get newConversations => 'కొత్త సంభాషణలు';

  @override
  String get summaryTemplate => 'సారాంశ టెంప్లేట్';

  @override
  String get suggestedTemplates => 'సూచించిన టెంప్లేట్‌లు';

  @override
  String get otherTemplates => 'ఇతర టెంప్లేట్‌లు';

  @override
  String get availableTemplates => 'అందుబాటులో ఉన్న టెంప్లేట్‌లు';

  @override
  String get getCreative => 'సృజనాత్మకంగా ఉండండి';

  @override
  String get defaultLabel => 'డిఫాల్ట్';

  @override
  String get lastUsedLabel => 'చివరిగా ఉపయోగించిన';

  @override
  String get setDefaultApp => 'డిఫాల్ట్ ఆ్యాప్ సెట్ చేయండి';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName ను మీ డిఫాల్ట్ సంక్షేపణ ఆ్యాప్‌గా సెట్ చేయాలా?\\n\\nఈ ఆ్యాప్ అన్ని భవిష్యత్ సంభాషణ సారాంశాల కోసం స్వయంచాలకంగా ఉపయోగించబడుతుంది.';
  }

  @override
  String get setDefaultButton => 'డిఫాల్ట్ సెట్ చేయండి';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName డిఫాల్ట్ సంక్షేపణ ఆ్యాప్ గా సెట్ చేయబడింది';
  }

  @override
  String get createCustomTemplate => 'కస్టమ్ టెంప్లేట్ సృష్టించండి';

  @override
  String get allTemplates => 'అన్ని టెంప్లేట్‌లు';

  @override
  String failedToInstallApp(String appName) {
    return '$appName ఇన్‌స్టాల్ చేయడంలో విఫలమైంది. దయచేసి మరలా ప్రయత్నించండి.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appName ఇన్‌స్టాల్ చేయటలో ఎర్రర్: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'స్పీకర్ $speakerId నిర్దేశించండి';
  }

  @override
  String get personNameAlreadyExists => 'ఈ పేరుతో ఇప్పటికే ఒక వ్యక్తి ఉంది.';

  @override
  String get selectYouFromList => 'మిమ్మల్నిని నిర్దేశించటానికి, దయచేసి జాబితా నుండి \"మీరు\" ఎంచుకోండి.';

  @override
  String get enterPersonsName => 'వ్యక్తి పేరు నమోదు చేయండి';

  @override
  String get addPerson => 'వ్యక్తిని జోడించండి';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'ఈ స్పీకర్ నుండి ఇతర విభాగాలను నిర్దేశించండి ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'ఇతర విభాగాలను నిర్దేశించండి';

  @override
  String get managePeople => 'ప్రజలను నిర్వహించండి';

  @override
  String get shareViaSms => 'SMS ద్వారా షేర్ చేయండి';

  @override
  String get selectContactsToShareSummary => 'మీ సంభాషణ సారాంశం షేర్ చేయటానికి సంప్రదాయాలను ఎంచుకోండి';

  @override
  String get searchContactsHint => 'సంప్రదాయాలను శోధించండి...';

  @override
  String contactsSelectedCount(int count) {
    return '$count ఎంపిక చేయబడిన';
  }

  @override
  String get clearAllSelection => 'అన్నింటిని క్లియర్ చేయండి';

  @override
  String get selectContactsToShare => 'షేర్ చేయటానికి సంప్రదాయాలను ఎంచుకోండి';

  @override
  String shareWithContactCount(int count) {
    return '$count సంప్రదాయతో షేర్ చేయండి';
  }

  @override
  String shareWithContactsCount(int count) {
    return '$count సంప్రదాయాలతో షేర్ చేయండి';
  }

  @override
  String get contactsPermissionRequired => 'సంప్రదాయాల అనుమతి అవసరం';

  @override
  String get contactsPermissionRequiredForSms => 'SMS ద్వారా షేర్ చేయటానికి సంప్రదాయాల అనుమతి అవసరం';

  @override
  String get grantContactsPermissionForSms => 'SMS ద్వారా షేర్ చేయటానికి దయచేసి సంప్రదాయాల అనుమతిని ఇవ్వండి';

  @override
  String get noContactsWithPhoneNumbers => 'ఫోన్ నంబర్‌లతో సంప్రదాయాలు కనుగొనబడలేదు';

  @override
  String get noContactsMatchSearch => 'మీ శోధనకు సరిపోలుతున్న సంప్రదాయాలు లేవు';

  @override
  String get failedToLoadContacts => 'సంప్రదాయాలను లోడ్ చేయడంలో విఫలమైంది';

  @override
  String get failedToPrepareConversationForSharing =>
      'షేరింగ్ కోసం సంభాషణను సిద్ధం చేయడంలో విఫలమైంది. దయచేసి మరలా ప్రయత్నించండి.';

  @override
  String get couldNotOpenSmsApp => 'SMS అ్యాప్ ఆపరు చేయలేకపోయాను. దయచేసి మరలా ప్రయత్నించండి.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'ఇది మేము ఇప్పటిగా చర్చించినది: $link';
  }

  @override
  String get wifiSync => 'WiFi సమన్వయం';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item క్లిప్‌బోర్డ్‌కు కాపీ చేయబడింది';
  }

  @override
  String get wifiConnectionFailedTitle => 'సంయోగం విఫలమైంది';

  @override
  String connectingToDeviceName(String deviceName) {
    return '$deviceName కు కనెక్ట్ చేస్తున్నాను';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '$deviceName యొక్క WiFi ప్రారంభించండి';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return '$deviceName కు కనెక్ట్ చేయండి';
  }

  @override
  String get recordingDetails => 'రికార్డింగ్ వివరాలు';

  @override
  String get storageLocationSdCard => 'SD కార్డ్';

  @override
  String get storageLocationLimitlessPendant => 'Limitless పెండాంట్';

  @override
  String get storageLocationPhone => 'ఫోన్';

  @override
  String get storageLocationPhoneMemory => 'ఫోన్ (మెమరీ)';

  @override
  String storedOnDevice(String deviceName) {
    return '$deviceName పై నిల్వ చేయబడింది';
  }

  @override
  String get transferring => 'బదిలీ చేస్తున్నాను...';

  @override
  String get transferRequired => 'బదిలీ అవసరం';

  @override
  String get downloadingAudioFromSdCard => 'మీ పరికరం యొక్క SD కార్డ్ నుండి ఆడియో డౌన్‌లోడ్ చేస్తున్నాను';

  @override
  String get transferRequiredDescription =>
      'ఈ రికార్డింగ్ మీ పరికరం యొక్క SD కార్డ్‌లో నిల్వ చేయబడింది. ఆటోపై చేయటానికి లేదా షేర్ చేయటానికి దీన్ని మీ ఫోన్‌కు బదిలీ చేయండి.';

  @override
  String get cancelTransfer => 'బదిలీ రద్దు చేయండి';

  @override
  String get transferToPhone => 'ఫోన్‌కు బదిలీ చేయండి';

  @override
  String get privateAndSecureOnDevice => 'మీ పరికరంపై ప్రైవేట్ మరియు సురక్షితమైన';

  @override
  String get recordingInfo => 'రికార్డింగ్ సమాచారం';

  @override
  String get transferInProgress => 'బదిలీ జరుస్తోంది...';

  @override
  String get shareRecording => 'రికార్డింగ్‌ను భాగస్వామ్యం చేయండి';

  @override
  String get deleteRecordingConfirmation => 'మీరు ఈ రికార్డింగ్‌ను శాశ్వతంగా తొలగించాలనుకుంటున్నారా? ఇది చేయలేము.';

  @override
  String get recordingIdLabel => 'రికార్డింగ్ ID';

  @override
  String get dateTimeLabel => 'తేదీ & సమయం';

  @override
  String get durationLabel => 'వ్యవధి';

  @override
  String get audioFormatLabel => 'ఆడియో ఫార్మాట్';

  @override
  String get storageLocationLabel => 'నిల్వ స్థానం';

  @override
  String get estimatedSizeLabel => 'అంచనా పరిమాణం';

  @override
  String get deviceModelLabel => 'పరికర మॉడల్';

  @override
  String get deviceIdLabel => 'పరికర ID';

  @override
  String get statusLabel => 'స్థితి';

  @override
  String get statusProcessed => 'ప్రక్రియ చేయబడింది';

  @override
  String get statusUnprocessed => 'ప్రక్రియ చేయబడనిది';

  @override
  String get switchedToFastTransfer => 'ఫాస్ట్ ట్రాన్‌సర్కు మారారు';

  @override
  String get transferCompleteMessage => 'బదిలీ సంపూర్ణం! మీరు ఇప్పుడు ఈ రికార్డింగ్‌ను ప్లే చేయవచ్చు.';

  @override
  String transferFailedMessage(String error) {
    return 'బదిలీ విफలమైంది: $error';
  }

  @override
  String get transferCancelled => 'బదిలీ రద్దు చేయబడింది';

  @override
  String get fastTransferEnabled => 'ఫాస్ట్ ట్రాన్‌సర్ సక్రియం చేయబడింది';

  @override
  String get bluetoothSyncEnabled => 'బ్లూటూత్ సింక్ సక్రియం చేయబడింది';

  @override
  String get enableFastTransfer => 'ఫాస్ట్ ట్రాన్‌సర్‌ను సక్రియం చేయండి';

  @override
  String get fastTransferDescription =>
      'ఫాస్ట్ ట్రాన్‌సర్ WiFi ను ఉపయోగించి ~5x వేగవంతమైన వేగం. బదిలీ సమయంలో మీ ఫోన్잠시Omi పరికరం యొక్క WiFi నెట్‌వర్క్‌కు అనుసంధానం అవుతుంది.';

  @override
  String get internetAccessPausedDuringTransfer => 'బదిలీ సమయంలో ఇంటర్నెట్ యాక్సెస్ పాజ్ చేయబడింది';

  @override
  String get chooseTransferMethodDescription =>
      'మీ Omi పరికరం నుండి మీ ఫోన్‌కు రికార్డింగ్‌లు ఎలా బదిలీ చేయాలో ఎంచుకోండి.';

  @override
  String get wifiSpeed => 'WiFi ద్వారా ~150 KB/s';

  @override
  String get fiveTimesFaster => '5X వేగవంతమైనది';

  @override
  String get fastTransferMethodDescription =>
      'మీ Omi పరికరానికి నేరుగా WiFi కనెక్షన్ సృష్టిస్తుంది. బదిలీ సమయంలో మీ ఫోన్잠ిக్కా మీ సాధారణ WiFi నుండి డిస్‌కనెక్ట్ చేయబడుతుంది.';

  @override
  String get bluetooth => 'బ్లూటూత్';

  @override
  String get bleSpeed => 'BLE ద్వారా ~30 KB/s';

  @override
  String get bluetoothMethodDescription =>
      'ప్రామాణిక బ్లూటూత్ లో ఎనర్జీ సంযోగం ఉపయోగిస్తుంది. నెమ్మదిగా ఉంటుందిగా ఉంది కానీ మీ WiFi కనెక్షన్‌ను ప్రభావితం చేయదు.';

  @override
  String get selected => 'ఎంచుకోబడింది';

  @override
  String get selectOption => 'ఎంచుకోండి';

  @override
  String get lowBatteryAlertTitle => 'తక్కువ బ్యాటరీ సতর్కత';

  @override
  String get lowBatteryAlertBody => 'మీ పరికరం తక్కువ బ్యాటరీలో ఉంది. రీఛార్జ్ చేయడానికి సమయం! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'మీ Omi పరికరం డిస్‌కనెక్ట్ చేయబడింది';

  @override
  String get deviceDisconnectedNotificationBody =>
      'మీ Omi ను ఉపయోగించిన్న కొనసాగించడానికి దయచేసి తిరిగి కనెక్ట్ చేయండి.';

  @override
  String get firmwareUpdateAvailable => 'ఫర్మ్‌వేర్ అపడేట్ అందుబాటులో ఉంది';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'మీ Omi పరికరం కోసం కొత్త ఫర్మ్‌వేర్ అపడేట్ ($version) అందుబాటులో ఉంది. ఇప్పుడు అపడేట్ చేయాలనుకుంటున్నారా?';
  }

  @override
  String get later => 'తరువాత';

  @override
  String get appDeletedSuccessfully => 'యాప్ విజయవంతంగా తొలగించబడింది';

  @override
  String get appDeleteFailed => 'యాప్‌ను తొలగించడానికి విఫలమైంది. దయచేసి తరువాత ప్రయత్నించండి.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'యాప్ దృశ్యమానత విజయవంతంగా మార్చబడింది. ప్రతిబింబిత చేయడానికి కొన్ని నిమిషాలు పట్టవచ్చు.';

  @override
  String get errorActivatingAppIntegration =>
      'యాప్‌ను సక్రియం చేసేటప్పుడు లోపం. ఇది ఇంటిగ్రేషన్ యాప్ అయితే, సెటప్ పూర్తి చేయబడిందని నిర్ధారించుకోండి.';

  @override
  String get errorUpdatingAppStatus => 'యాప్ స్థితి నవీకరించేటప్పుడు ఒక లోపం సంభవించింది.';

  @override
  String get calculatingETA => 'లెక్కిస్తోంది...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return '$minutes నిమిషాల సుమారు మిగిలి ఉన్నాయి';
  }

  @override
  String get aboutAMinuteRemaining => 'సుమారు ఒక నిమిషం మిగిలి ఉంది';

  @override
  String get almostDone => 'దాదాపు పూర్తియైంది...';

  @override
  String get omiSays => 'omi చెప్పింది';

  @override
  String get analyzingYourData => 'మీ డేటాను విశ్లేషించుచున్నారు...';

  @override
  String migratingToProtection(String level) {
    return '$level సంరక్షణకు మార్పిస్తోంది...';
  }

  @override
  String get noDataToMigrateFinalizing => 'మార్పించడానికి డేటా లేదు. చివరకు...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType మార్పిస్తోంది... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'అన్ని వస్తువులు మార్చబడ్డాయి. చివరకు...';

  @override
  String get migrationErrorOccurred => 'మార్పిస్తున్న సమయంలో ఒక లోపం సంభవించింది. దయచేసి ప్రయత్నించండి.';

  @override
  String get migrationComplete => 'మార్పిస్తోంది పూర్తయింది!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'మీ డేటా ఇప్పుడు కొత్త $level సెట్టింగ్‌లతో సంరక్షించబడింది.';
  }

  @override
  String get chatsLowercase => 'చాట్‌లు';

  @override
  String get dataLowercase => 'డేటా';

  @override
  String get fallNotificationTitle => 'అవ్వ';

  @override
  String get fallNotificationBody => 'మీరు పడిపోయారా?';

  @override
  String get importantConversationTitle => 'ముఖ్యమైన సంభాషణ';

  @override
  String get importantConversationBody =>
      'మీరు ఒక ముఖ్యమైన సంభాషణ ఉన్నారు. ఇతరులకు సారాంశం భాగస్వామ్యం చేయడానికి నొక్కండి.';

  @override
  String get templateName => 'టెంప్లేట్ పేరు';

  @override
  String get templateNameHint => 'ఉదా., మీటింగ్ యాక్షన్ ఐటమ్‌ల ఎక్సట్రాక్టర్';

  @override
  String get nameMustBeAtLeast3Characters => 'పేరు కనీసం 3 అక్షరాలు ఉండాలి';

  @override
  String get conversationPromptHint =>
      'ఉదా., సంభాషణ నుండి చర్య చేసిన ఐటమ్‌లు, నిర్ణయాలు మరియు కీ టేక్‌అవేలను సంగ్రహించండి.';

  @override
  String get pleaseEnterAppPrompt => 'దయచేసి మీ యాప్‌కు ఒక సూచనను నమోదు చేయండి';

  @override
  String get promptMustBeAtLeast10Characters => 'సూచన కనీసం 10 అక్షరాలు ఉండాలి';

  @override
  String get anyoneCanDiscoverTemplate => 'ఎవరైనా మీ టెంప్లేట్‌ను కనుగొనవచ్చు';

  @override
  String get onlyYouCanUseTemplate => 'మీరు మాత్రమే ఈ టెంప్లేట్‌ను ఉపయోగించవచ్చు';

  @override
  String get generatingDescription => 'వర్ణనను జన్మిస్తోంది...';

  @override
  String get creatingAppIcon => 'యాప్ చిహ్నాన్ని సృష్టిస్తోంది...';

  @override
  String get installingApp => 'యాప్‌ను ఇన్‌స్టాల్ చేస్తోంది...';

  @override
  String get appCreatedAndInstalled => 'యాప్ సృష్టించబడిన మరియు ఇన్‌స్టాల్ చేయబడింది!';

  @override
  String get appCreatedSuccessfully => 'యాప్ విజయవంతంగా సృష్టించబడింది!';

  @override
  String get failedToCreateApp => 'యాప్‌ను సృష్టించడానికి విఫలమైంది. దయచేసి ప్రయత్నించండి.';

  @override
  String get addAppSelectCoreCapability => 'దయచేసి కొనసాగించడానికి మీ యాప్‌కు ఒక కోర్ సామర్థ్యాన్ని ఎంచుకోండి';

  @override
  String get addAppSelectPaymentPlan => 'దయచేసి మీ యాప్‌కు ఒక చెల్లింపు ప్రణాళికను ఎంచుకోండి మరియు ఖరీదు నమోదు చేయండి';

  @override
  String get addAppSelectCapability => 'దయచేసి మీ యాప్‌కు కనీసం ఒక సామర్థ్యాన్ని ఎంచుకోండి';

  @override
  String get addAppSelectLogo => 'దయచేసి మీ యాప్‌కు లోగో ఎంచుకోండి';

  @override
  String get addAppEnterChatPrompt => 'దయచేసి మీ యాప్‌కు చాట్ సూచనను నమోదు చేయండి';

  @override
  String get addAppEnterConversationPrompt => 'దయచేసి మీ యాప్‌కు సంభాషణ సూచనను నమోదు చేయండి';

  @override
  String get addAppSelectTriggerEvent => 'దయచేసి మీ యాప్‌కు ట్రిగర్ ఈవెంట్‌ను ఎంచుకోండి';

  @override
  String get addAppEnterWebhookUrl => 'దయచేసి మీ యాప్‌కు వెబ్‌హూక్ URL నమోదు చేయండి';

  @override
  String get addAppSelectCategory => 'దయచేసి మీ యాప్‌కు ఒక వర్గం ఎంచుకోండి';

  @override
  String get addAppFillRequiredFields => 'దయచేసి అన్ని అవసరమైన ఫీల్డ్‌లను సరిగ్గా నిండిపెట్టండి';

  @override
  String get addAppUpdatedSuccess => 'యాప్ విజయవంతంగా నవీకరించబడింది 🚀';

  @override
  String get addAppUpdateFailed => 'యాప్‌ను నవీకరించడానికి విఫలమైంది. దయచేసి తరువాత ప్రయత్నించండి';

  @override
  String get addAppSubmittedSuccess => 'యాప్ విజయవంతంగా సమర్పించబడింది 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'ఫైల్ పిక్కర్‌ని తెరవడానికి లోపం: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'చిత్రం ఎంచుకోవడంలో లోపం: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'ఫోటోలు అనుమతి నిరాకరించబడింది. చిత్రం ఎంచుకోవడానికి ఫోటోలకు యాక్సెస్‌ను అనుమతించండి';

  @override
  String get addAppErrorSelectingImageRetry => 'చిత్రం ఎంచుకోవడంలో లోపం. దయచేసి ప్రయత్నించండి.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'థంబ్‌నెయిల్‌ను ఎంచుకోవడంలో లోపం: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'థంబ్‌నెయిల్‌ను ఎంచుకోవడంలో లోపం. దయచేసి ప్రయత్నించండి.';

  @override
  String get addAppCapabilityConflictWithPersona => 'ఇతర సామర్థ్యాలు పర్సోనా సાথે ఎంచుకోవలేము';

  @override
  String get addAppPersonaConflictWithCapabilities => 'పర్సోనా ఇతర సామర్థ్యాలతో ఎంచుకోవలేము';

  @override
  String get paymentFailedToFetchCountries => 'సమర్థిత దేశాలను పొందడానికి విఫలమైంది. దయచేసి తరువాత ప్రయత్నించండి.';

  @override
  String get paymentFailedToSetDefault =>
      'డిఫాల్ట్ చెల్లింపు పద్ధతిని సెట్ చేయడానికి విఫలమైంది. దయచేసి తరువాత ప్రయత్నించండి.';

  @override
  String get paymentFailedToSavePaypal => 'PayPal వివరాలను సేవ్ చేయడానికి విఫలమైంది. దయచేసి తరువాత ప్రయత్నించండి.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'సక్రియం';

  @override
  String get paymentStatusConnected => 'సంయుక్త';

  @override
  String get paymentStatusNotConnected => 'సంయుక్త కాదు';

  @override
  String get paymentAppCost => 'యాప్ ఖరీదు';

  @override
  String get paymentEnterValidAmount => 'దయచేసి చెల్లుబాటు అయిన మొత్తం నమోదు చేయండి';

  @override
  String get paymentEnterAmountGreaterThanZero => 'దయచేసి 0 కంటే ఎక్కువ మొత్తం నమోదు చేయండి';

  @override
  String get paymentPlan => 'చెల్లింపు ప్రణాళిక';

  @override
  String get paymentNoneSelected => 'ఎవరూ ఎంచుకోబడలేదు';

  @override
  String get aiGenPleaseEnterDescription => 'దయచేసి మీ యాప్‌కు వర్ణనను నమోదు చేయండి';

  @override
  String get aiGenCreatingAppIcon => 'యాప్ చిహ్నాన్ని సృష్టిస్తోంది...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'ఒక లోపం సంభవించింది: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'యాప్ విజయవంతంగా సృష్టించబడింది!';

  @override
  String get aiGenFailedToCreateApp => 'యాప్‌ను సృష్టించడానికి విఫలమైంది';

  @override
  String get aiGenErrorWhileCreatingApp => 'యాప్‌ను సృష్టించేటప్పుడు ఒక లోపం సంభవించింది';

  @override
  String get aiGenFailedToGenerateApp => 'యాప్‌ను జన్మిస్తో విఫలమైంది. దయచేసి ప్రయత్నించండి.';

  @override
  String get aiGenFailedToRegenerateIcon => 'చిహ్నాన్ని పునర్సృష్టించడానికి విఫలమైంది';

  @override
  String get aiGenPleaseGenerateAppFirst => 'దయచేసి మొదటిసారి యాప్‌ను జన్మిస్తోండి';

  @override
  String get nextButton => 'తరువాత';

  @override
  String get connectOmiDevice => 'Omi పరికరం కనెక్ట్ చేయండి';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'మీరు మీ Unlimited ప్రణాళికను $title కు మారుస్తున్నారు. మీరు కొనసాగించాలనుకుంటున్నారా?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'అప్‌గ్రేడ్ షెడ్యూల్ చేయబడింది! మీ నెలవారీ ప్రణాళిక మీ బిల్లింగ్ వ్యవధి ముగింపు వరకు కొనసాగుతుంది, తరువాత స్వయంచాలకంగా వార్షికకు మారుతుంది.';

  @override
  String get couldNotSchedulePlanChange => 'ప్రణాళిక మార్పును షెడ్యూల్ చేయలేకపోయారు. దయచేసి ప్రయత్నించండి.';

  @override
  String get subscriptionReactivatedDefault =>
      'మీ సభ్యత్వం పునరీక్రియాజనకరణ చేయబడింది! ఇప్పుడు ఛార్జ్ లేదు - మీ ప్రస్తుత వ్యవధి ముగింపులో బిల్లు చేయబడతారు.';

  @override
  String get subscriptionSuccessfulCharged => 'సభ్యత్వం విజయవంతం! కొత్త బిల్లింగ్ వ్యవధికి మీకు బిల్లు చేయబడింది.';

  @override
  String get couldNotProcessSubscription => 'సభ్యత్వాన్ని ప్రక్రియ చేయలేకపోయారు. దయచేసి ప్రయత్నించండి.';

  @override
  String get couldNotLaunchUpgradePage => 'అప్‌గ్రేడ్ పేజీని చালించలేకపోయారు. దయచేసి ప్రయత్నించండి.';

  @override
  String get transcriptionJsonPlaceholder => 'మీ JSON కాన్ఫిగరేషన్‌ను ఇక్కడ సంచిక చేయండి...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'ఫైల్ పిక్కర్‌ని తెరవడానికి లోపం: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'లోపం: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'సంభాషణలను విజయవంతంగా విలీనం చేయబడింది';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count సంభాషణలను విజయవంతంగా విలీనం చేయబడింది';
  }

  @override
  String get actionItemReminderTitle => 'Omi రిమైండర్';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName డిస్‌కనెక్ట్ చేయబడింది';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'మీ $deviceName ను ఉపయోగించిన్న కొనసాగించడానికి దయచేసి తిరిగి కనెక్ట్ చేయండి.';
  }

  @override
  String get onboardingSignIn => 'సైన్ ఇన్';

  @override
  String get onboardingYourName => 'మీ నామం';

  @override
  String get onboardingLanguage => 'భాష';

  @override
  String get onboardingPermissions => 'అనుమతులు';

  @override
  String get onboardingComplete => 'పూర్తయింది';

  @override
  String get onboardingWelcomeToOmi => 'Omi కు స్వాగతం';

  @override
  String get onboardingTellUsAboutYourself => 'మీ గురించి మాకు చెప్పండి';

  @override
  String get onboardingChooseYourPreference => 'మీ ప్రాధాన్యతను ఎంచుకోండి';

  @override
  String get onboardingGrantRequiredAccess => 'అవసరమైన ప్రాప్తిని మంజూరు చేయండి';

  @override
  String get onboardingYoureAllSet => 'మీరు అన్నీ సెట్ చేసారు';

  @override
  String get searchTranscriptOrSummary => 'ట్రాన్‌స్క్రిప్ట్ లేదా సారాంశం చేయండి...';

  @override
  String get myGoal => 'నా లక్ష్యం';

  @override
  String get appNotAvailable => 'అయ్యో! మీరు చేస్తున్న యాప్ అందుబాటులో లేదు.';

  @override
  String get failedToConnectTodoist => 'Todoist కు సంయోగం చేయడానికి విఫలమైంది';

  @override
  String get failedToConnectAsana => 'Asana కు సంయోగం చేయడానికి విఫలమైంది';

  @override
  String get failedToConnectGoogleTasks => 'Google టాస్‌కులకు సంయోగం చేయడానికి విఫలమైంది';

  @override
  String get failedToConnectClickUp => 'ClickUp కు సంయోగం చేయడానికి విఫలమైంది';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName కు సంయోగం చేయడానికి విఫలమైంది: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Todoist కు విజయవంతంగా సంయుక్త!';

  @override
  String get failedToConnectTodoistRetry => 'Todoist కు సంయోగం చేయడానికి విఫలమైంది. దయచేసి ప్రయత్నించండి.';

  @override
  String get successfullyConnectedAsana => 'Asana కు విజయవంతంగా సంయుక్త!';

  @override
  String get failedToConnectAsanaRetry => 'Asana కు సంయోగం చేయడానికి విఫలమైంది. దయచేసి ప్రయత్నించండి.';

  @override
  String get successfullyConnectedGoogleTasks => 'Google టాస్‌కులకు విజయవంతంగా సంయుక్త!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google టాస్‌కులకు సంయోగం చేయడానికి విఫలమైంది. దయచేసి ప్రయత్నించండి.';

  @override
  String get successfullyConnectedClickUp => 'ClickUp కు విజయవంతంగా సంయుక్త!';

  @override
  String get failedToConnectClickUpRetry => 'ClickUp కు సంయోగం చేయడానికి విఫలమైంది. దయచేసి ప్రయత్నించండి.';

  @override
  String get successfullyConnectedNotion => 'Notion కు విజయవంతంగా సంయుక్త!';

  @override
  String get failedToRefreshNotionStatus => 'Notion సంయోగ స్థితిని తాజా చేయడానికి విఫలమైంది.';

  @override
  String get successfullyConnectedGoogle => 'Google కు విజయవంతంగా సంయుక్త!';

  @override
  String get failedToRefreshGoogleStatus => 'Google సంయోగ స్థితిని తాజా చేయడానికి విఫలమైంది.';

  @override
  String get successfullyConnectedWhoop => 'Whoop కు విజయవంతంగా సంయుక్త!';

  @override
  String get failedToRefreshWhoopStatus => 'Whoop సంయోగ స్థితిని తాజా చేయడానికి విఫలమైంది.';

  @override
  String get successfullyConnectedGitHub => 'GitHub కు విజయవంతంగా సంయుక్త!';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub సంయోగ స్థితిని తాజా చేయడానికి విఫలమైంది.';

  @override
  String get authFailedToSignInWithGoogle => 'Google సાથે సైన్ ఇన్ చేయడానికి విఫలమైంది, దయచేసి ప్రయత్నించండి.';

  @override
  String get authenticationFailed => 'ప్రమాణీకరణ విఫలమైంది. దయచేసి ప్రయత్నించండి.';

  @override
  String get authFailedToSignInWithApple => 'Apple సాથে సైన్ ఇన్ చేయడానికి విఫలమైంది, దయచేసి ప్రయత్నించండి.';

  @override
  String get authFailedToRetrieveToken => 'firebase టోకెన్‌ను పొందడానికి విఫలమైంది, దయచేసి ప్రయత్నించండి.';

  @override
  String get authUnexpectedErrorFirebase =>
      'సైన్ ఇన్ చేసేటప్పుడు అనిర్దేశ్య లోపం, Firebase లోపం, దయచేసి ప్రయత్నించండి.';

  @override
  String get authUnexpectedError => 'సైన్ ఇన్ చేసేటప్పుడు అనిర్దేశ్య లోపం, దయచేసి ప్రయత్నించండి';

  @override
  String get authFailedToLinkGoogle => 'Google సાથে లింక్ చేయడానికి విఫలమైంది, దయచేసి ప్రయత్నించండి.';

  @override
  String get authFailedToLinkApple => 'Apple సాथে లింక్ చేయడానికి విఫలమైంది, దయచేసి ప్రయత్నించండి.';

  @override
  String get onboardingBluetoothRequired => 'మీ పరికరానికి కనెక్ట్ చేయడానికి బ్లూటూత్ అనుమతి అవసరం.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'బ్లూటూత్ అనుమతి నిరాకరించబడింది. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్‌లో అనుమతిని మంజూరు చేయండి.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'బ్లూటూత్ అనుమతి స్థితి: $status. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్‌లను చెక్ చేయండి.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'బ్లూటూత్ అనుమతిని చెక్ చేయడానికి విఫలమైంది: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'ఆంటిఫిकేషన్ అనుమతి నిరాకరించబడింది. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్‌లో అనుమతిని మంజూరు చేయండి.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'ఆంటిఫిकేషన్ అనుమతి నిరాకరించబడింది. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్ > ఆంటిఫికేషన్‌లలో అనుమతిని మంజూరు చేయండి.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'ఆంటిఫిকేషన్ అనుమతి స్థితి: $status. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్‌లను చెక్ చేయండి.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'ఆంటిఫికేషన్ అనుమతిని చెక్ చేయడానికి విఫలమైంది: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'దయచేసి సెట్టింగ్‌లు > గోపనీయత & సంరక్షణ > స్థానం సేవలలో స్థానం అనుమతిని మంజూరు చేయండి';

  @override
  String get onboardingMicrophoneRequired => 'రికార్డింగ్‌కు మైక్రోఫోన్ అనుమతి అవసరం.';

  @override
  String get onboardingMicrophoneDenied =>
      'మైక్రోఫోన్ అనుమతి నిరాకరించబడింది. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్ > గోపనీయత & సంరక్షణ > మైక్రోఫోన్‌లో అనుమతిని మంజూరు చేయండి.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'మైక్రోఫోన్ అనుమతి స్థితి: $status. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్‌లను చెక్ చేయండి.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'మైక్రోఫోన్ అనుమతిని చెక్ చేయడానికి విఫలమైంది: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'సిస్టమ్ ఆడియో రికార్డింగ్‌కు స్క్రీన్ క్యాప్చర్ అనుమతి అవసరం.';

  @override
  String get onboardingScreenCaptureDenied =>
      'స్క్రీన్ క్యాప్చర్ అనుమతి నిరాకరించబడింది. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్ > గోపనీయత & సంరక్షణ > స్క్రీన్ రికార్డింగ్‌లో అనుమతిని మంజూరు చేయండి.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'స్క్రీన్ క్యాప్చర్ అనుమతి స్థితి: $status. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్‌లను చెక్ చేయండి.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'స్క్రీన్ క్యాప్చర్ అనుమతిని చెక్ చేయడానికి విఫలమైంది: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'బ్రౌజర్ సమావేశాలను సంప్రదించడానికి ప్రాప్తిత్వ అనుమతి అవసరం.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'ప్రాప్తిత్వ అనుమతి స్థితి: $status. దయచేసి సిస్టమ్ ప్రిఫరెన్‌సెస్‌లను చెక్ చేయండి.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'ప్రాప్తిత్వ అనుమతిని చెక్ చేయడానికి విఫలమైంది: $error';
  }

  @override
  String get msgCameraNotAvailable => 'కెమెరా క్యాప్చర్ ఈ ప్ల్యాట్‌ఫారమ్‌లో అందుబాటులో లేదు';

  @override
  String get msgCameraPermissionDenied => 'కెమెరా అనుమతి నిరాకరించబడింది. దయచేసి కెమెరాకు యాక్సెస్‌ను అనుమతించండి';

  @override
  String msgCameraAccessError(String error) {
    return 'కెమెరాను ప్రాప్త చేసేటప్పుడు లోపం: $error';
  }

  @override
  String get msgPhotoError => 'ఫోటో తీసుకోవడంలో లోపం. దయచేసి ప్రయత్నించండి.';

  @override
  String get msgMaxImagesLimit => 'మీరు కేవలం 4 చిత్రాలను ఎంచుకోవచ్చు';

  @override
  String msgFilePickerError(String error) {
    return 'ఫైల్ పిక్కర్‌ని తెరవడంలో లోపం: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'చిత్రాలను ఎంచుకోవడంలో లోపం: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'ఫోటోలు అనుమతి నిరాకరించబడింది. చిత్రాలను ఎంచుకోవడానికి ఫోటోలకు యాక్సెస్‌ను అనుమతించండి';

  @override
  String get msgSelectImagesGenericError => 'చిత్రాలను ఎంచుకోవడంలో లోపం. దయచేసి ప్రయత్నించండి.';

  @override
  String get msgMaxFilesLimit => 'మీరు కేవలం 4 ఫైల్‌లను ఎంచుకోవచ్చు';

  @override
  String msgSelectFilesError(String error) {
    return 'ఫైల్‌లను ఎంచుకోవడంలో లోపం: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'ఫైల్‌లను ఎంచుకోవడంలో లోపం. దయచేసి ప్రయత్నించండి.';

  @override
  String get msgUploadFileFailed => 'ఫైల్‌ను ఎక్సచేంజ్ చేయడానికి విఫలమైంది, దయచేసి తరువాత ప్రయత్నించండి';

  @override
  String get msgReadingMemories => 'మీ జ్ఞాపకాలను చదువుతోంది...';

  @override
  String get msgLearningMemories => 'మీ జ్ఞాపకాల నుండి నేర్చుకుంటోంది...';

  @override
  String get msgUploadAttachedFileFailed => 'అనుబంధ ఫైల్‌ను ఎక్సచేంజ్ చేయడానికి విఫలమైంది.';

  @override
  String captureRecordingError(String error) {
    return 'రికార్డింగ్ సమయంలో ఒక లోపం సంభవించింది: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'రికార్డింగ్ ఆపివేయబడింది: $reason. మీరు బాహ్య డిస్‌ప్లేలను తిరిగి కనెక్ట్ చేయవలసి ఉండవచ్చు లేదా రికార్డింగ్‌ను పునరారంభించవలసి ఉండవచ్చు.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'మైక్రోఫోన్ అనుమతి అవసరం';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'సిస్టమ్ ప్రిఫరెన్‌సెస్‌లలో మైక్రోఫోన్ అనుమతిని ఇవ్వండి';

  @override
  String get captureScreenRecordingPermissionRequired => 'స్క్రీన్ రికార్డింగ్ అనుమతి అవసరం';

  @override
  String get captureDisplayDetectionFailed => 'డిస్‌ప్లే సంప్రదించడం విఫలమైంది. రికార్డింగ్ ఆపివేయబడింది.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'చెల్లని ఆడియో బైట్‌ల వెబ్‌హూక్ URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'చెల్లని రియల్‌టైమ్ ట్రాన్‌స్క్రిప్ట్ వెబ్‌హూక్ URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'చెల్లని సంభాషణ సృష్టించిన వెబ్‌హూక్ URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'చెల్లని రోజు సారాంశ వెబ్‌హూక్ URL';

  @override
  String get devModeSettingsSaved => 'సెట్టింగ్‌లు సేవ్ చేయబడింది!';

  @override
  String get voiceFailedToTranscribe => 'ఆడియోను ట్రాన్‌స్‌క్రిబ్ చేయడానికి విఫలమైంది';

  @override
  String get locationPermissionRequired => 'స్థానం అనుమతి అవసరం';

  @override
  String get locationPermissionContent =>
      'ఫాస్ట్ ట్రాన్‌సర్‌కు WiFi సంయోగం ధృవీకరించడానికి స్థానం అనుమతి అవసరం. దయచేసి కొనసాగించడానికి స్థానం అనుమతిని ఇవ్వండి.';

  @override
  String get pdfTranscriptExport => 'ట్రాన్‌స్క్రిప్ట్ ఎక్సపోర్ట్';

  @override
  String get pdfConversationExport => 'సంభాషణ ఎక్సపోర్ట్';

  @override
  String pdfTitleLabel(String title) {
    return 'శీర్షిక: $title';
  }

  @override
  String get conversationNewIndicator => 'కొత్త 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count ఫోటోలు';
  }

  @override
  String get mergingStatus => 'విలీనం చేస్తోంది...';

  @override
  String timeSecsSingular(int count) {
    return '$count సెక';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count సెక్‌లు';
  }

  @override
  String timeMinSingular(int count) {
    return '$count నిమి';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count నిమిషాలు';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins నిమిషాలు $secs సెక్‌లు';
  }

  @override
  String timeHourSingular(int count) {
    return '$count గంట';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count గంటలు';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours గంటలు $mins నిమిషాలు';
  }

  @override
  String timeDaySingular(int count) {
    return '$count రోజు';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count రోజులు';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days రోజులు $hours గంటలు';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countసె';
  }

  @override
  String timeCompactMins(int count) {
    return '$countని';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsని $secsసె';
  }

  @override
  String timeCompactHours(int count) {
    return '$countగం';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursగం $minsని';
  }

  @override
  String get moveToFolder => 'ఫోల్డర్‌కు తరలించండి';

  @override
  String get noFoldersAvailable => 'ఫోల్డర్‌లు అందుబాటులో లేవు';

  @override
  String get newFolder => 'కొత్త ఫోల్డర్';

  @override
  String get color => 'రంగు';

  @override
  String get waitingForDevice => 'పరికరం కోసం ఎదురుచూస్తోంది...';

  @override
  String get saySomething => 'ఏదైనా చెప్పండి...';

  @override
  String get initialisingSystemAudio => 'సిస్టమ్ ఆడియోను ప్రారంభించుచున్నారు';

  @override
  String get stopRecording => 'రికార్డింగ్ ఆపండి';

  @override
  String get continueRecording => 'రికార్డింగ్ కొనసాగించండి';

  @override
  String get initialisingRecorder => 'రికార్డర్‌ను ప్రారంభించుచున్నారు';

  @override
  String get pauseRecording => 'రికార్డింగ్ పాజ్ చేయండి';

  @override
  String get resumeRecording => 'రికార్డింగ్ తిరిగి ప్రారంభించండి';

  @override
  String get noDailyRecapsYet => 'ఇంకా రోజువారీ రీక్యాప్‌లు లేవు';

  @override
  String get dailyRecapsDescription => 'మీ రోజువారీ రీక్యాప్‌లు అందాయ్‌తో ఇక్కడ కనిపిస్తాయి';

  @override
  String get chooseTransferMethod => 'బదిలీ పద్ధతిని ఎంచుకోండి';

  @override
  String get fastTransferSpeed => 'WiFi ద్వారా ~150 KB/s';

  @override
  String largeTimeGapDetected(String gap) {
    return 'పెద్ద సమయ విరామం సంప్రదించబడింది ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'పెద్ద సమయ విరామాలు సంప్రదించబడ్డాయి ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'పరికరం WiFi సింక్‌కు సమర్థనీయం కాదు, బ్లూటూత్‌కు మారుస్తోంది';

  @override
  String get appleHealthNotAvailable => 'Apple ఆరోగ్యం ఈ పరికరంలో అందుబాటులో లేదు';

  @override
  String get downloadAudio => 'ఆడియోను డౌన్‌లోడ్ చేయండి';

  @override
  String get audioDownloadSuccess => 'ఆడియో విజయవంతంగా డౌన్‌లోడ్ చేయబడింది';

  @override
  String get audioDownloadFailed => 'ఆడియోను డౌన్‌లోడ్ చేయడానికి విఫలమైంది';

  @override
  String get downloadingAudio => 'ఆడియోను డౌన్‌లోడ్ చేస్తోంది...';

  @override
  String get shareAudio => 'ఆడియోను భాగస్వామ్యం చేయండి';

  @override
  String get preparingAudio => 'ఆడియోను సిద్ధం చేస్తోంది';

  @override
  String get gettingAudioFiles => 'ఆడియో ఫైల్‌లను పొందుతోంది...';

  @override
  String get downloadingAudioProgress => 'ఆడియోను డౌన్‌లోడ్ చేస్తోంది';

  @override
  String get processingAudio => 'ఆడియోను ప్రక్రియ చేస్తోంది';

  @override
  String get combiningAudioFiles => 'ఆడియో ఫైల్‌లను జత చేస్తోంది...';

  @override
  String get audioReady => 'ఆడియో సిద్ధం';

  @override
  String get openingShareSheet => 'భాగస్వామ్య పత్రాన్ని తెరుస్తోంది...';

  @override
  String get audioShareFailed => 'భాగస్వామ్య విఫలమైంది';

  @override
  String get dailyRecaps => 'రోజువారీ రీక్యాప్‌లు';

  @override
  String get removeFilter => 'ఫిల్టర్‌ను తీసివేయండి';

  @override
  String get categoryConversationAnalysis => 'సంభాషణ విశ్లేషణ';

  @override
  String get categoryHealth => 'ఆరోగ్యం';

  @override
  String get categoryEducation => 'విద్య';

  @override
  String get categoryCommunication => 'సంప్రదായం';

  @override
  String get categoryEmotionalSupport => 'భావాభిమానపూర్ణ సమర్థన';

  @override
  String get categoryProductivity => 'ఉత్పాదకత';

  @override
  String get categoryEntertainment => 'వినోదం';

  @override
  String get categoryFinancial => 'ఆర్థిక';

  @override
  String get categoryTravel => 'ভ్రమణ';

  @override
  String get categorySafety => 'భద్రత';

  @override
  String get categoryShopping => 'కొనుగోలు';

  @override
  String get categorySocial => 'సామాజిక';

  @override
  String get categoryNews => 'వార్తలు';

  @override
  String get categoryUtilities => 'సూత్రాలు';

  @override
  String get categoryOther => 'ఇతర';

  @override
  String get capabilityChat => 'చాట్';

  @override
  String get capabilityConversations => 'సంభాషణలు';

  @override
  String get capabilityExternalIntegration => 'బాహ్య ఇంటిగ్రేషన్';

  @override
  String get capabilityNotification => 'ఆంటిఫికేషన్';

  @override
  String get triggerAudioBytes => 'ఆడియో బైట్‌లు';

  @override
  String get triggerConversationCreation => 'సంభాషణ సృష్టి';

  @override
  String get triggerTranscriptProcessed => 'ట్రాన్‌స్క్రిప్ట్ ప్రక్రియ చేయబడింది';

  @override
  String get actionCreateConversations => 'సంభాషణలను సృష్టించండి';

  @override
  String get actionCreateMemories => 'జ్ఞాపకాలను సృష్టించండి';

  @override
  String get actionReadConversations => 'సంభాషణలను చదవండి';

  @override
  String get actionReadMemories => 'జ్ఞాపకాలను చదవండి';

  @override
  String get actionReadTasks => 'పనులను చదవండి';

  @override
  String get scopeUserName => 'ఉపయోగకర్త నామం';

  @override
  String get scopeUserFacts => 'ఉపయోగకర్త విషయాలు';

  @override
  String get scopeUserConversations => 'ఉపయోగకర్త సంభాషణలు';

  @override
  String get scopeUserChat => 'ఉపయోగకర్త చాట్';

  @override
  String get capabilitySummary => 'సారాంశం';

  @override
  String get capabilityFeatured => 'చిత్రీకరించిన';

  @override
  String get capabilityTasks => 'పనులు';

  @override
  String get capabilityIntegrations => 'ఇంటిగ్రేషన్‌లు';

  @override
  String get categoryProductivityLifestyle => 'ఉత్పాదకత & జీవనశైలి';

  @override
  String get categorySocialEntertainment => 'సామాజిక & వినోదం';

  @override
  String get categoryProductivityTools => 'ఉత్పాదకత & సాధనాలు';

  @override
  String get categoryPersonalWellness => 'వ్యక్తిగత & జీవనశైలి';

  @override
  String get rating => 'రేటింగ్';

  @override
  String get categories => 'వర్గాలు';

  @override
  String get sortBy => 'క్రమబద్ధీకరించు';

  @override
  String get highestRating => 'అతిపెద్ద రేటింగ్';

  @override
  String get lowestRating => 'అతిచిన్న రేటింగ్';

  @override
  String get resetFilters => 'ఫిల్టర్‌లను రీసెట్ చేయండి';

  @override
  String get applyFilters => 'ఫిల్టర్‌లను వర్తించండి';

  @override
  String get mostInstalls => 'చాలా ఇన్‌స్టాలేషన్‌లు';

  @override
  String get couldNotOpenUrl => 'URLని తెరవలేము. దయచేసి మరవసి ప్రయత్నించండి.';

  @override
  String get newTask => 'కొత్త కार్యం';

  @override
  String get viewAll => 'అన్నీ చూడండి';

  @override
  String get addTask => 'కార్యం జోడించండి';

  @override
  String get addMcpServer => 'MCP సర్వర్ జోడించండి';

  @override
  String get connectExternalAiTools => 'బాహ్య AI సాధనాలను కనెక్ట్ చేయండి';

  @override
  String get mcpServerUrl => 'MCP సర్వర్ URL';

  @override
  String mcpServerConnected(int count) {
    return '$count సాధనాలు విజయవంతంగా కనెక్ట్ చేయబడ్డాయి';
  }

  @override
  String get mcpConnectionFailed => 'MCP సర్వర్‌కు కనెక్ట్ చేయడం విఫలమైంది';

  @override
  String get authorizingMcpServer => 'అధికారం ఇస్తోంది...';

  @override
  String get whereDidYouHearAboutOmi => 'మీరు amin గురించి ఎలా తెలుసుకున్నారు?';

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
  String get friendWordOfMouth => 'స్నేహితుడు';

  @override
  String get otherSource => 'ఇతర';

  @override
  String get pleaseSpecify => 'దయచేసి నిర్దేశించండి';

  @override
  String get event => 'ఈవెంట్';

  @override
  String get coworker => 'సహకర్మચారి';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google శోధన';

  @override
  String get audioPlaybackUnavailable => 'ఆడియో ఫైల్ ప్లేబ్యాక్ కోసం అందుబాటులో లేదు';

  @override
  String get audioPlaybackFailed => 'ఆడియోని ప్లే చేయలేము. ఫైల్ చెడిపోయిన లేదా తప్పిపోయి ఉండవచ్చు.';

  @override
  String get connectionGuide => 'కనెక్షన్ గైడ్';

  @override
  String get iveDoneThis => 'నేను ఇది చేసాను';

  @override
  String get pairNewDevice => 'కొత్త పరికరాన్ని జత చేయండి';

  @override
  String get dontSeeYourDevice => 'మీ పరికరం చూడటం లేదు?';

  @override
  String get reportAnIssue => 'సమస్యను నివేదించండి';

  @override
  String get pairingTitleOmi => 'Omi ను ఆన్ చేయండి';

  @override
  String get pairingDescOmi => 'పరికరం కంపించే వరకు బటన్‌ను నొక్కి ఉంచండి.';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit ను జత చేయడానికి మోడ్‌లో ఉంచండి';

  @override
  String get pairingDescOmiDevkit =>
      'ఆన్ చేయడానికి బటన్‌ను ఒక్కసారి నొక్కండి. జత చేయడం మోడ్‌లో ఉన్నప్పుడు LED ఊదా రంగులో చెమ్ముతుంది.';

  @override
  String get pairingTitleOmiGlass => 'Omi Glass ను ఆన్ చేయండి';

  @override
  String get pairingDescOmiGlass => 'సైడ్ బటన్‌ను 3 సెకన్ల పాటు నొక్కి పవర్ ఆన్ చేయండి.';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note ను జత చేయడానికి మోడ్‌లో ఉంచండి';

  @override
  String get pairingDescPlaudNote =>
      'సైడ్ బటన్‌ను 2 సెకన్ల పాటు నొక్కి ఉంచండి. ఎరుపు LED జత చేయడానికి సిద్ధంగా ఉన్నప్పుడు చెమ్ముతుంది.';

  @override
  String get pairingTitleBee => 'Bee ను జత చేయడానికి మోడ్‌లో ఉంచండి';

  @override
  String get pairingDescBee =>
      'బటన్‌ను 5 సార్లు నిరంతరం నొక్కండి. లైట్ నీలం మరియు ఆకుపచ్చ రంగులో చెమ్మడం ప్రారంభిస్తుంది.';

  @override
  String get pairingTitleLimitless => 'Limitless ను జత చేయడానికి మోడ్‌లో ఉంచండి';

  @override
  String get pairingDescLimitless =>
      'ఎటువంటి కాంతి కనిపించినప్పుడు, ఒక్కసారి నొక్కి, తర్వాత పరికరం గులాబీ కాంతిని చూపిస్తుంది, ఆపై విడుదల చేయండి.';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant ను జత చేయడానికి మోడ్‌లో ఉంచండి';

  @override
  String get pairingDescFriendPendant =>
      'పెండెంట్‌పై బటన్‌ను నొక్కి ఆన్ చేయండి. ఇది స్వయంచాలకంగా జత చేయడం మోడ్‌లోకి ప్రవేశిస్తుంది.';

  @override
  String get pairingTitleFieldy => 'Fieldy ను జత చేయడానికి మోడ్‌లో ఉంచండి';

  @override
  String get pairingDescFieldy => 'కాంతి కనిపించే వరకు పరికరాన్ని నొక్కి ఉంచండి.';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch కనెక్ట్ చేయండి';

  @override
  String get pairingDescAppleWatch =>
      'మీ Apple Watch లో Omi యాప్‌ను ఇన్‌స్టాల్ చేసి, తెరవండి, ఆపై యాప్‌లో కనెక్ట్‌ను నొక్కండి.';

  @override
  String get pairingTitleNeoOne => 'Neo One ను జత చేయడానికి మోడ్‌లో ఉంచండి';

  @override
  String get pairingDescNeoOne =>
      'LED చెమ్మడం ప్రారంభం చేయడం వరకు విద్యుత్ బటన్‌ను నొక్కి ఉంచండి. పరికరం కనుగొనదగినదిగా ఉంటుంది.';

  @override
  String get downloadingFromDevice => 'పరికరం నుండి డౌన్‌లోడ్ చేస్తోంది';

  @override
  String get reconnectingToInternet => 'ఇంటర్నెట్‌కు మరోసారి కనెక్ట్ చేస్తోంది...';

  @override
  String uploadingToCloud(int current, int total) {
    return '$current నుండి $total ను అప్‌లోడ్ చేస్తోంది';
  }

  @override
  String get processingOnServer => 'సర్వర్‌లో ప్రక్రియ చేస్తోంది...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'ప్రక్రియ చేస్తోంది... $current/$total విభాగాలు';
  }

  @override
  String get processedStatus => 'ప్రక్రియ చేయబడింది';

  @override
  String get corruptedStatus => 'చెడిపోయింది';

  @override
  String nPending(int count) {
    return '$count పెండింగ్';
  }

  @override
  String nProcessed(int count) {
    return '$count ప్రక్రియ చేయబడింది';
  }

  @override
  String get synced => 'సమకాలీకరించబడింది';

  @override
  String get noPendingRecordings => 'పెండింగ్ రికార్డింగ్‌లు లేవు';

  @override
  String get noProcessedRecordings => 'ఇంకా ప్రక్రియ చేయబడిన రికార్డింగ్‌లు లేవు';

  @override
  String get pending => 'పెండింగ్';

  @override
  String whatsNewInVersion(String version) {
    return '$version లో కొత్త ఏమిటి';
  }

  @override
  String get addToYourTaskList => 'మీ టాస్క్ లిస్ట్‌కు జోడించాలా?';

  @override
  String get failedToCreateShareLink => 'షేర్ లింక్‌ను సృష్టించడం విఫలమైంది';

  @override
  String get deleteGoal => 'లక్ష్యాన్ని తొలగించండి';

  @override
  String get deviceUpToDate => 'మీ పరికరం అప్‌ටు-డేట్ ఉంది';

  @override
  String get wifiConfiguration => 'WiFi కాన్ఫిగరేషన్';

  @override
  String get wifiConfigurationSubtitle =>
      'ఫర్మ్‌వేర్‌ను డౌన్‌లోడ్ చేయడానికి అనుమతించడానికి మీ WiFi ఆధారపడిన సమాచారం నమోదు చేయండి.';

  @override
  String get networkNameSsid => 'నెట్‌వర్క్ పేరు (SSID)';

  @override
  String get enterWifiNetworkName => 'WiFi నెట్‌వర్క్ పేరు నమోదు చేయండి';

  @override
  String get enterWifiPassword => 'WiFi పాస్‌వర్డ్ నమోదు చేయండి';

  @override
  String get appIconLabel => 'యాప్ చిహ్నం';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'ఇది నేను మీ గురించి తెలుసుకున్న';

  @override
  String get onboardingWhatIKnowAboutYouDescription =>
      'Omi మీ సంభాషణల నుండి నేర్చుకున్నందున ఈ మ్యాప్ నవీకరించబడుతుంది.';

  @override
  String get apiEnvironment => 'API పరిసర';

  @override
  String get apiEnvironmentDescription => 'ఏ బ్యాకెండ్‌కు కనెక్ట్ చేయాలో ఎంచుకోండి';

  @override
  String get production => 'ఉత్పత్తి';

  @override
  String get staging => 'స్టేజింగ్';

  @override
  String get switchRequiresRestart => 'స్విచ్ చేయడానికి యాప్ రీస్టార్ట్ అవసరం';

  @override
  String get switchApiConfirmTitle => 'API పరిసరాన్ని స్విచ్ చేయండి';

  @override
  String switchApiConfirmBody(String environment) {
    return '$environment కు స్విచ్ చేయాలా? మార్పులు ప్రభావవంతం చేయడానికి మీరు యాప్‌ను మూసి, మరోసారి తెరవాలి.';
  }

  @override
  String get switchAndRestart => 'స్విచ్ చేయండి';

  @override
  String get stagingDisclaimer =>
      'స్టేజింగ్ బగ్‌లను కలిగి ఉండవచ్చు, అసమానమైన పనితీరుకు మరియు డేటా కోల్పోయే అవకాశం ఉంది. పరీక్షణ కోసం మాత్రమే ఉపయోగించండి.';

  @override
  String get apiEnvSavedRestartRequired => 'సేవ్ చేయబడింది. యాప్‌ను వర్తించడానికి మూసి, మరోసారి తెరవండి.';

  @override
  String get shared => 'భాగస్వామ్యం చేయబడింది';

  @override
  String get onlyYouCanSeeConversation => 'ఈ సంభాషణను మీరు మాత్రమే చూడవచ్చు';

  @override
  String get anyoneWithLinkCanView => 'లింక్‌ని కలిగిన ఎవరైనా చూడవచ్చు';

  @override
  String get tasksCleanTodayTitle => 'ఈ రోజు టాస్క్‌లను శుభ్రపరచాలా?';

  @override
  String get tasksCleanTodayMessage => 'ఇది కేవలం సమయపాలనలను తీసివేస్తుంది';

  @override
  String get tasksOverdue => 'గడువు ఆలస్యమైనది';

  @override
  String get phoneCallsWithOmi => 'Omi తో ఫోన్ కాల్‌లు';

  @override
  String get phoneCallsSubtitle => 'రియల్-టైమ్ ట్రాన్‌స్క్రిప్షన్ తో కాల్‌లు చేయండి';

  @override
  String get phoneSetupStep1Title => 'మీ ఫోన్ నంబర్ ధృవీకరించండి';

  @override
  String get phoneSetupStep1Subtitle => 'ఇది మీది అని నిర్ధారించడానికి మేము మీకు కాల్ చేస్తాము';

  @override
  String get phoneSetupStep2Title => 'ధృవీకరణ కోడ్‌ను నమోదు చేయండి';

  @override
  String get phoneSetupStep2Subtitle => 'కాల్‌పై మీరు టైప్ చేసే చిన్న కోడ్';

  @override
  String get phoneSetupStep3Title => 'మీ సంప్రదాయాలకు కాల్‌ చేయడం ప్రారంభించండి';

  @override
  String get phoneSetupStep3Subtitle => 'నిర్మిత లైవ్ ట్రాన్‌స్క్రిప్షన్ తో';

  @override
  String get phoneGetStarted => 'ప్రారంభించండి';

  @override
  String get callRecordingConsentDisclaimer => 'కాల్ రికార్డింగ్ మీ న్యాయక్షేత్రంలో సమ్మతి కావాలి';

  @override
  String get enterYourNumber => 'మీ నంబర్‌ను నమోదు చేయండి';

  @override
  String get phoneNumberCallerIdHint => 'ధృవీకరించిన తర్వాత, ఇది మీ కాల్‌లర్ ID గా ఉంటుంది';

  @override
  String get phoneNumberHint => 'ఫోన్ నంబర్';

  @override
  String get failedToStartVerification => 'ధృవీకరణను ప్రారంభించడం విఫలమైంది';

  @override
  String get phoneContinue => 'కొనసాగించు';

  @override
  String get verifyYourNumber => 'మీ నంబర్‌ను ధృవీకరించండి';

  @override
  String get answerTheCallFrom => 'నుండి కాల్‌కు సమాధానం ఇవ్వండి';

  @override
  String get onTheCallEnterThisCode => 'కాల్‌లో, ఈ కోడ్‌ను నమోదు చేయండి';

  @override
  String get followTheVoiceInstructions => 'వాయిస్ సూచనలను అనుసరించండి';

  @override
  String get statusCalling => 'కాల్ చేస్తోంది...';

  @override
  String get statusCallInProgress => 'కాల్ పురోగతిలో ఉంది';

  @override
  String get statusVerifiedLabel => 'ధృవీకరించబడింది';

  @override
  String get statusCallMissed => 'కాల్ తప్పిపోయింది';

  @override
  String get statusTimedOut => 'సమయం ముగిసింది';

  @override
  String get phoneTryAgain => 'మరవసి ప్రయత్నించండి';

  @override
  String get phonePageTitle => 'ఫోన్';

  @override
  String get phoneContactsTab => 'సంప్రదాయాలు';

  @override
  String get phoneKeypadTab => 'కీపాడ్';

  @override
  String get grantContactsAccess => 'మీ సంప్రదాయాలకు ప్రవేశ ఇవ్వండి';

  @override
  String get phoneAllow => 'అనుమతించు';

  @override
  String get phoneSearchHint => 'శోధన';

  @override
  String get phoneNoContactsFound => 'సంప్రదాయాలు కనుగొనబడలేదు';

  @override
  String get phoneEnterNumber => 'నంబర్‌ను నమోదు చేయండి';

  @override
  String get failedToStartCall => 'కాల్ ప్రారంభించడం విఫలమైంది';

  @override
  String get callStateConnecting => 'కనెక్ట్ చేస్తోంది...';

  @override
  String get callStateRinging => 'రింగ్ చేస్తోంది...';

  @override
  String get callStateEnded => 'కాల్ ముగిసింది';

  @override
  String get callStateFailed => 'కాల్ విఫలమైంది';

  @override
  String get transcriptPlaceholder => 'ట్రాన్‌స్క్రిప్ట్ ఇక్కడ కనిపిస్తుంది...';

  @override
  String get phoneUnmute => 'మ్యూట్ చేయవద్దు';

  @override
  String get phoneMute => 'మ్యూట్ చేయండి';

  @override
  String get phoneSpeaker => 'స్పీకర్';

  @override
  String get phoneEndCall => 'ముగించు';

  @override
  String get phoneCallSettingsTitle => 'ఫోన్ కాల్ సెట్టింగ్‌లు';

  @override
  String get showPhoneCallButtonTitle => 'ఫోన్ కాల్ బటన్ చూపించు';

  @override
  String get showPhoneCallButtonDesc => 'హోమ్ స్క్రీన్‌లో ఫోన్ కాల్ బటన్ చూపించు';

  @override
  String get yourVerifiedNumbers => 'మీ ధృవీకరించిన సంఖ్యలు';

  @override
  String get verifiedNumbersDescription => 'మీరు ఎవరికైనా కాల్ చేసినప్పుడు, వారు తమ ఫోన్‌లో ఈ నంబర్‌ను చూస్తారు';

  @override
  String get noVerifiedNumbers => 'ధృవీకరించిన సంఖ్యలు లేవు';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber ను తొలగించాలా?';
  }

  @override
  String get deletePhoneNumberWarning => 'కాల్‌లు చేయడానికి మీరు మరోసారి ధృవీకరించాలి';

  @override
  String get phoneDeleteButton => 'తొలగించు';

  @override
  String verifiedMinutesAgo(int minutes) {
    return '${minutes}m క్రితం ధృవీకరించబడింది';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return '${hours}h క్రితం ధృవీకరించబడింది';
  }

  @override
  String verifiedDaysAgo(int days) {
    return '${days}d క్రితం ధృవీకరించబడింది';
  }

  @override
  String verifiedOnDate(String date) {
    return '$date న ధృవీకరించబడింది';
  }

  @override
  String get verifiedFallback => 'ధృవీకరించబడింది';

  @override
  String get callAlreadyInProgress => 'ఇప్పటికే కాల్ పురోగతిలో ఉంది';

  @override
  String get failedToGetCallToken => 'కాల్ టోకెన్‌ను పొందడం విఫలమైంది. ముందుగా మీ ఫోన్ నంబర్‌ను ధృవీకరించండి.';

  @override
  String get failedToInitializeCallService => 'కాల్ సేవను ప్రారంభించడం విఫలమైంది';

  @override
  String get speakerLabelYou => 'మీరు';

  @override
  String get speakerLabelUnknown => 'తెలియనివారు';

  @override
  String get showDailyScoreOnHomepage => 'హోమ్‌పేజ్‌లో దిన్నంక స్కోర్ చూపించండి';

  @override
  String get showTasksOnHomepage => 'హోమ్‌పేజ్‌లో కార్యాలను చూపించండి';

  @override
  String get phoneCallsUnlimitedOnly => 'Omi ద్వారా ఫోన్ కాల్‌లు';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Omi ద్వారా కాల్‌లు చేయండి మరియు రియల్-టైమ్ ట్రాన్‌స్క్రిప్షన్, స్వయంచాలక సారాంశాలు మరియు మరిన్నిటిని పొందండి. అన్‌లిమిటెడ్ ప్లాన్ సబ్‌స్క్రైబర్‌ల కోసం ప్రత్యేకంగా అందుబాటులో ఉంది.';

  @override
  String get phoneCallsUpsellFeature1 => 'ప్రతి కాల్ రియల్-టైమ్ ట్రాన్‌స్క్రిప్షన్';

  @override
  String get phoneCallsUpsellFeature2 => 'స్వయంచాలక కాల్ సారాంశాలు మరియు కార్య అంశాలు';

  @override
  String get phoneCallsUpsellFeature3 => 'గ్రహీతలు మీ నిజమైన నంబర్‌ను చూస్తారు, యాదృచ్ఛిక సంఖ్య కాదు';

  @override
  String get phoneCallsUpsellFeature4 => 'మీ కాల్‌లు ఖాజా మరియు సురక్షితమైనవి';

  @override
  String get phoneCallsUpgradeButton => 'అన్‌లిమిటెడ్‌కు అప్‌గ్రేడ్ చేయండి';

  @override
  String get phoneCallsMaybeLater => 'బహుశా తరువాత';

  @override
  String get deleteSynced => 'సమకాలీకరించిన తొలగించు';

  @override
  String get deleteSyncedFiles => 'సమకాలీకరించిన రికార్డింగ్‌లను తొలగించండి';

  @override
  String get deleteSyncedFilesMessage => 'ఈ రికార్డింగ్‌లు ఇప్పటికే మీ ఫోన్‌కు సమకాలీకరించబడ్డాయి. ఇది రద్దు చేయబడదు.';

  @override
  String get syncedFilesDeleted => 'సమకాలీకరించిన రికార్డింగ్‌లు తొలగించబడ్డాయి';

  @override
  String get deletePending => 'పెండింగ్ తొలగించు';

  @override
  String get deletePendingFiles => 'పెండింగ్ రికార్డింగ్‌లను తొలగించండి';

  @override
  String get deletePendingFilesWarning =>
      'ఈ రికార్డింగ్‌లు మీ ఫోన్‌కు సమకాలీకరించబడలేదు మరియు శాశ్వతంగా కోల్పోతాయి. ఇది రద్దు చేయబడదు.';

  @override
  String get pendingFilesDeleted => 'పెండింగ్ రికార్డింగ్‌లు తొలగించబడ్డాయి';

  @override
  String get deleteAllFiles => 'అన్ని రికార్డింగ్‌లను తొలగించండి';

  @override
  String get deleteAll => 'అన్నీ తొలగించు';

  @override
  String get deleteAllFilesWarning =>
      'ఇది సమకాలీకరించిన మరియు పెండింగ్ రికార్డింగ్‌లను తొలగిస్తుంది. పెండింగ్ రికార్డింగ్‌లు సమకాలీకరించబడలేదు మరియు శాశ్వతంగా కోల్పోతాయి. ఇది రద్దు చేయబడదు.';

  @override
  String get allFilesDeleted => 'అన్ని రికార్డింగ్‌లు తొలగించబడ్డాయి';

  @override
  String nFiles(int count) {
    return '$count రికార్డింగ్‌లు';
  }

  @override
  String get manageStorage => 'నిల్వను నిర్వహించండి';

  @override
  String get safelyBackedUp => 'మీ ఫోన్‌కు సురక్షితంగా బ్యాకప్ చేయబడింది';

  @override
  String get notYetSynced => 'ఇంకా మీ ఫోన్‌కు సమకాలీకరించబడలేదు';

  @override
  String get clearAll => 'అన్నీ క్లియర్ చేయండి';

  @override
  String get phoneKeypad => 'కీపాడ్';

  @override
  String get phoneHideKeypad => 'కీపాడ్ను దాచండి';

  @override
  String get fairUsePolicy => 'న్యాయమైన ఉపయోగం';

  @override
  String get fairUseLoadError => 'న్యాయమైన ఉపయోగ స్థితిని లోడ్ చేయలేము. దయచేసి మరవసి ప్రయత్నించండి.';

  @override
  String get fairUseStatusNormal => 'మీ ఉపయోగం సాధారణ పరిమితులలో ఉంది.';

  @override
  String get fairUseStageNormal => 'సాధారణ';

  @override
  String get fairUseStageWarning => 'హెచ్చరిక';

  @override
  String get fairUseStageThrottle => 'థ్రోట్‌లెడ్';

  @override
  String get fairUseStageRestrict => 'నిర్బంధితం';

  @override
  String get fairUseSpeechUsage => 'స్పీచ్ ఉపయోగం';

  @override
  String get fairUseToday => 'ఈ రోజు';

  @override
  String get fairUse3Day => '3-రోజు రోలింగ్';

  @override
  String get fairUseWeekly => 'వారానికి రోలింగ్';

  @override
  String get fairUseAboutTitle => 'న్యాయమైన ఉపయోగం గురించి';

  @override
  String get fairUseAboutBody =>
      'Omi వ్యక్తిగత సంభాషణలు, సమావేశాలు మరియు జీవంత పరిస్థితుల కోసం డిజైన్ చేయబడింది. ఉపయోగం కనెక్షన్ సమయం కాకుండా కనుగొనబడిన నిజమైన స్పీచ్ సమయం ద్వారా కొలుస్తారు. ఉపయోగం నిజమైన కాని నిజమైన కాని విషయవస్తువుల కోసం సాధారణ నమూనాలను గణనీయంగా మించిపోయినట్లయితే, సమన్వయాలు వర్తించవచ్చు.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef కాపీ చేయబడింది';
  }

  @override
  String get fairUseDailyTranscription => 'రోజువారీ ట్రాన్‌స్క్రిప్షన్';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'రోజువారీ ట్రాన్‌స్క్రిప్షన్ పరిమితి చేరుకుంది';

  @override
  String fairUseBudgetResetsAt(String time) {
    return '$time వద్ద రీసెట్‌లు';
  }

  @override
  String get transcriptionPaused => 'రికార్డింగ్, మరోసారి కనెక్ట్ చేస్తోంది';

  @override
  String get transcriptionPausedReconnecting =>
      'ఇంకా రికార్డింగ్ చేస్తోంది — ట్రాన్‌స్క్రిప్షన్‌కు మరోసారి కనెక్ట్ చేస్తోంది...';

  @override
  String fairUseBannerStatus(String status) {
    return 'న్యాయమైన ఉపయోగం: $status';
  }

  @override
  String get improveConnectionTitle => 'కనెక్షన్ మెరుగుపరచండి';

  @override
  String get improveConnectionContent =>
      'Omi మీ పరికరానికి కనెక్ట్ చేయబడిన విధానాన్ని మేము మెరుగుపరచాము. ఇది సక్రియం చేయడానికి, దయచేసి పరికరం సమాచారం పేజీకి వెళ్లండి, \"పరికరం డిస్‌కనెక్ట్ చేయండి\" నొక్కండి మరియు అప్పుడు మీ పరికరాన్ని మరోసారి జత చేయండి.';

  @override
  String get improveConnectionAction => 'నిర్థారణ';

  @override
  String clockSkewWarning(int minutes) {
    return 'మీ పరికరం గడియారం ~$minutes నిమిషాల ద్వారా ఆఫ్ ఉంది. మీ తేదీ & సమయ సెట్టింగ్‌లను తనిఖీ చేయండి.';
  }

  @override
  String get omisStorage => 'Omi యొక్క నిల్వ';

  @override
  String get phoneStorage => 'ఫోన్ నిల్వ';

  @override
  String get cloudStorage => 'క్లౌడ్ నిల్వ';

  @override
  String get howSyncingWorks => 'సమకాలీకరణ ఎలా పని చేస్తుంది';

  @override
  String get noSyncedRecordings => 'ఇంకా సమకాలీకరించిన రికార్డింగ్‌లు లేవు';

  @override
  String get recordingsSyncAutomatically => 'రికార్డింగ్‌లు స్వయంచాలకంగా సమకాలీకరించబడతాయి — ఎటువంటి చర్య అవసరం లేదు.';

  @override
  String get filesDownloadedUploadedNextTime => 'ఇప్పటికే డౌన్‌లోడ్ చేయబడిన ఫైల్‌లు తర్వాత అప్‌లోడ్ చేయబడతాయి.';

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
  String get tapToView => 'చూడటానికి నొక్కండి';

  @override
  String get syncFailed => 'సమకాలీకరణ విఫలమైంది';

  @override
  String get keepSyncing => 'సమకాలీకరణ కొనసాగించండి';

  @override
  String get cancelSyncQuestion => 'సమకాలీకరణ రద్దు చేయాలా?';

  @override
  String get omisStorageDesc =>
      'మీ Omi మీ ఫోన్‌కు కనెక్ట్ చేయనప్పుడు, ఇది నిర్మిత మెమరీపై స్థానికంగా ఆడియోను నిల్వ చేస్తుంది. మీరు ఎప్పటికీ రికార్డింగ్‌ను కోల్పోరు.';

  @override
  String get phoneStorageDesc =>
      'Omi మరోసారి కనెక్ట్ చేసినప్పుడు, రికార్డింగ్‌లు స్వయంచాలకంగా మీ ఫోన్‌కు అప్‌లోడ్ చేయడానికి ముందు తాత్కాలిక హోల్డింగ్ ఆ రూపంగా బదిలీ చేయబడతాయి.';

  @override
  String get cloudStorageDesc =>
      'అప్‌లోడ్ చేసిన తర్వాత, మీ రికార్డింగ్‌లు ప్రక్రియ చేయబడతాయి మరియు ట్రాన్‌స్క్రిబ్ చేయబడతాయి. సంభాషణలు ఒక నిమిషంలో అందుబాటులో ఉంటాయి.';

  @override
  String get tipKeepPhoneNearby => 'వేగవంతమైన సమకాలీకరణ కోసం మీ ఫోన్‌ను దగ్గరగా ఉంచండి';

  @override
  String get tipStableInternet => 'స్థిరమైన ఇంటర్నెట్ క్లౌడ్ అప్‌లోడ్‌లను వేగవంతం చేస్తుంది';

  @override
  String get tipAutoSync => 'రికార్డింగ్‌లు స్వయంచాలకంగా సమకాలీకరించబడతాయి';

  @override
  String get storageSection => 'నిల్వ';

  @override
  String get permissions => 'అనుమతులు';

  @override
  String get permissionEnabled => 'ప్రారంభించబడింది';

  @override
  String get permissionEnable => 'ప్రారంభించండి';

  @override
  String get permissionsPageDescription =>
      'ఈ అనుమతులు Omi ఎలా పని చేస్తుంది అనేటువంటి ప్రధానమైనవి. అవి నోటిఫికేషన్‌లు, స్థానం-ఆధారిత అనుభవాలు మరియు ఆడియో సంగ్రహణ వంటి ముఖ్య లక్షణాలను ఎనేబుల్ చేస్తాయి.';

  @override
  String get permissionsRequiredDescription =>
      'Omi సరిగ్గా పని చేయడానికి కొన్ని అనుమతులు అవసరం. దయచేసి కొనసాగించటానికి వాటిని ఇవ్వండి.';

  @override
  String get permissionsSetupTitle => 'ఉత్తమ అనుభవం పొందండి';

  @override
  String get permissionsSetupDescription => 'Omi తన మేజిక్ పని చేయడానికి కొన్ని అనుమతులను ప్రారంభించండి.';

  @override
  String get permissionsChangeAnytime => 'మీరు ఈ అనుమతులను ఎప్పటికీ సెట్టింగ్‌లు > అనుమతులలో మార్చవచ్చు';

  @override
  String get location => 'స్థానం';

  @override
  String get microphone => 'మైక్రోఫోన్';

  @override
  String get whyAreYouCanceling => 'మీరు ఎందుకు రద్దు చేస్తున్నారు?';

  @override
  String get cancelReasonSubtitle => 'మీరు ఎందుకు నిష్క్రమిస్తున్నారో మాకు చెప్పగలరా?';

  @override
  String get cancelReasonTooExpensive => 'చాలా ఖరీదైనది';

  @override
  String get cancelReasonNotUsing => 'చాలా ఉపయోగించటం లేదు';

  @override
  String get cancelReasonMissingFeatures => 'లక్షణాలు లేవు';

  @override
  String get cancelReasonAudioQuality => 'ఆడియో/ట్రాన్‌స్క్రిప్షన్ గుణం';

  @override
  String get cancelReasonBatteryDrain => 'బ్యాటరీ డ్రైన్ ఆందోళనలు';

  @override
  String get cancelReasonFoundAlternative => 'ప్రత్యామ్నాయాన్ని కనుగొన్నారు';

  @override
  String get cancelReasonOther => 'ఇతర';

  @override
  String get tellUsMore => 'మరిన్ని చెప్పండి (ఐచ్ఛికం)';

  @override
  String get cancelReasonDetailHint => 'మేము ఎటువంటి ప్రతిస్పందనకు ప్రశంసిస్తున్నాము...';

  @override
  String get justAMoment => 'క్షణానికి మరోసారి, దయచేసి';

  @override
  String get cancelConsequencesSubtitle =>
      'మేము రద్దు చేయకుండా మీ ఇతర ఎంపికలను అన్వేషించమని సంప్రదాయవశంగా సిఫార్సు చేస్తున్నాము.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'మీ ప్లాన్ $date వరకు క్రియాశీలంగా ఉంటుంది. దాని తర్వాత, మీరు సీమితమైన లక్షణాలతో ఉచిత సంస్కరణకు బదిలీ చేయబడతారు.';
  }

  @override
  String get ifYouCancel => 'మీరు రద్దు చేసినట్లయితే:';

  @override
  String get cancelConsequenceNoAccess => 'మీ బిల్లింగ్ కాలం చివరిలో అన్‌లిమిటెడ్ ప్రవేశకు చేరుకోలేరు.';

  @override
  String get cancelConsequenceBattery => '7x మరిన్ని బ్యాటరీ ఉపయోగం (ఆన్-పరికరం ప్రక్రియ)';

  @override
  String get cancelConsequenceQuality => '30% తక్కువ ట్రాన్‌స్క్రిప్షన్ గుణం (ఆన్-పరికరం నమూనాలు)';

  @override
  String get cancelConsequenceDelay => '5-7 రెండవ ప్రక్రియ ఆలస్యం (ఆన్-పరికరం నమూనాలు)';

  @override
  String get cancelConsequenceSpeakers => 'స్పీకర్‌లను గుర్తించలేరు.';

  @override
  String get confirmAndCancel => 'నిర్థారణ & రద్దు చేయండి';

  @override
  String get cancelConsequencePhoneCalls => 'రియల్-టైమ్ ఫోన్ కాల్ ట్రాన్‌స్క్రిప్షన్ లేదు';

  @override
  String get feedbackTitleTooExpensive => 'మీ కోసం ఏ ధర పని చేస్తుంది?';

  @override
  String get feedbackTitleMissingFeatures => 'మీరు ఏ లక్షణాలను కోల్పోతున్నారు?';

  @override
  String get feedbackTitleAudioQuality => 'మీరు ఏ సమస్యలను ఎదుర్కొన్నారు?';

  @override
  String get feedbackTitleBatteryDrain => 'బ్యాటరీ సమస్యల గురించి చెప్పండి';

  @override
  String get feedbackTitleFoundAlternative => 'మీరు ఎకు మారుతున్నారు?';

  @override
  String get feedbackTitleNotUsing => 'Omi ను మరింత ఉపయోగించడానికి ఏ చేస్తుంది?';

  @override
  String get feedbackSubtitleTooExpensive => 'మీ ప్రతిస్పందన సరైన సమతుల్యతను కనుగొనటానికి సహాయపడుతుంది.';

  @override
  String get feedbackSubtitleMissingFeatures => 'మేము ఎల్లప్పుడూ నిర్మిస్తున్నాము — ఇది ప్రాధాన్యతీకరణలో సహాయపడుతుంది.';

  @override
  String get feedbackSubtitleAudioQuality => 'ఏమి తప్పుకుందో అర్థం చేసుకోవాలనుకుంటున్నాము.';

  @override
  String get feedbackSubtitleBatteryDrain => 'ఇది మాల హార్డ్‌వేర్ టీమ్ మెరుగుపరచటానికి సహాయపడుతుంది.';

  @override
  String get feedbackSubtitleFoundAlternative => 'మీ దృష్టిని ఆకర్షించిన విషయాన్ని తెలుసుకోవాలనుకుంటున్నాము.';

  @override
  String get feedbackSubtitleNotUsing => 'Omi కు మీకు మరింత ఉపయోగకరంగా చేయాలనుకుంటున్నాము.';

  @override
  String get deviceDiagnostics => 'పరికరం రోగనిర్ధారణ';

  @override
  String get signalStrength => 'సిగ్నల్ శక్తి';

  @override
  String get connectionUptime => 'అప్‌టైమ్';

  @override
  String get reconnections => 'మరోసారి కనెక్షన్‌లు';

  @override
  String get disconnectHistory => 'డిస్‌కనెక్ట్ చరిత్ర';

  @override
  String get noDisconnectsRecorded => 'ఎటువంటి డిస్‌కనెక్ట్‌లు రికార్డ్ చేయబడలేదు';

  @override
  String get diagnostics => 'రోగనిర్ధారణ';

  @override
  String get waitingForData => 'డేటా కోసం ఎదురుచూస్తోంది...';

  @override
  String get liveRssiOverTime => 'సమయం తర్వాత లైవ్ RSSI';

  @override
  String get noRssiDataYet => 'ఇంకా RSSI డేటా లేదు';

  @override
  String get collectingData => 'డేటా సేకరిస్తోంది...';

  @override
  String get cleanDisconnect => 'శుభ్ర డిస్‌కనెక్ట్';

  @override
  String get connectionTimeout => 'కనెక్షన్ సమయం ముగిసింది';

  @override
  String get remoteDeviceTerminated => 'రిమోట్ పరికరం ముగిసింది';

  @override
  String get pairedToAnotherPhone => 'మరొక ఫోన్‌కు జత చేయబడింది';

  @override
  String get linkKeyMismatch => 'లింక్ కీ విషమతలు';

  @override
  String get connectionFailed => 'కనెక్షన్ విఫలమైంది';

  @override
  String get appClosed => 'యాప్ మూసుకుపోయింది';

  @override
  String get manualDisconnect => 'మానవ డిస్‌కనెక్ట్';

  @override
  String lastNEvents(int count) {
    return 'చివరి $count ఈవెంట్‌లు';
  }

  @override
  String get signal => 'సిగ్నల్';

  @override
  String get battery => 'బ్యాటరీ';

  @override
  String get excellent => 'ఉత్తమ';

  @override
  String get good => 'మంచి';

  @override
  String get fair => 'న్యాయమైన';

  @override
  String get weak => 'బలహీనమైన';

  @override
  String gattError(String code) {
    return 'GATT లోపం ($code)';
  }

  @override
  String get batteryHistory => 'బ్యాటరీ';

  @override
  String get noBatteryDataYet => 'ఇంకా బ్యాటరీ డేటా లేదు';

  @override
  String get day => 'రోజు';

  @override
  String get week => 'వారం';

  @override
  String get rollbackToStableFirmware => 'స్థిర ఫర్మ్‌వేర్‌కు రిటర్న్ చేయండి';

  @override
  String get rollbackConfirmTitle => 'ఫర్మ్‌వేర్ రిటర్న్ చేయాలా?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'ఇది మీ ప్రస్తుత ఫర్మ్‌వేర్‌ను సరికొత్త స్థిర సంస్కరణ ($version)ను మార్చుతుంది. మీ పరికరం అప్‌డేట్ తర్వాత రీస్టార్ట్ చేయబడుతుంది.';
  }

  @override
  String get stableFirmware => 'స్థిర ఫర్మ్‌వేర్';

  @override
  String get fetchingStableFirmware => 'సరికొత్త స్థిర ఫర్మ్‌వేర్‌ను పొందుస్తోంది...';

  @override
  String get noStableFirmwareFound => 'మీ పరికరం కోసం స్థిర ఫర్మ్‌వేర్ సంస్కరణను కనుగొనలేము.';

  @override
  String get installStableFirmware => 'స్థిర ఫర్మ్‌వేర్‌ను ఇన్‌స్టాల్ చేయండి';

  @override
  String get alreadyOnStableFirmware => 'మీరు ఇప్పటికే సరికొత్త స్థిర సంస్కరణలో ఉన్నారు.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration ఆడియో స్థానికంగా సేవ చేయబడింది';
  }

  @override
  String get willSyncAutomatically => 'స్వయంచాలకంగా సమకాలీకరించబడుతుంది';

  @override
  String get enableLocationTitle => 'స్థానం ప్రారంభించండి';

  @override
  String get enableLocationDescription => 'సమీపవర్తీ బ్లూటూత్ పరికరాలను కనుగొనటానికి స్థానం అనుమతి అవసరం.';

  @override
  String get voiceRecordingFound => 'రికార్డింగ్ కనుగొనబడింది';

  @override
  String get transcriptionConnecting => 'ట్రాన్‌స్క్రిప్షన్ కనెక్ట్ చేస్తోంది...';

  @override
  String get transcriptionReconnecting => 'ట్రాన్‌స్క్రిప్షన్ మరోసారి కనెక్ట్ చేస్తోంది...';

  @override
  String get transcriptionUnavailable => 'ట్రాన్‌స్క్రిప్షన్ అందుబాటులో లేదు';

  @override
  String get audioOutput => 'ఆడియో నిర్గమం';

  @override
  String get firmwareWarningTitle => 'ముఖ్యం: అప్‌డేట్ చేయడానికి ముందు చదవండి';

  @override
  String get firmwareFormatWarning =>
      'ఈ ఫర్మ్‌వేర్ SD కార్డ్‌ను ఫార్మాట్ చేస్తుంది. అప్‌గ్రేడ్ చేయడానికి ముందు అన్ని ఆఫ్‌లైన్ డేటా సింక్ అయిందని నిర్ధారించుకోండి.\n\nఈ వెర్షన్ ఇన్‌స్టాల్ చేసిన తర్వాత ఎరుపు లైట్ మినుకుమినుకుమంటే ఆందోళన చెందకండి. పరికరాన్ని యాప్‌కి కనెక్ట్ చేయండి, అది నీలం రంగులోకి మారాలి. ఎరుపు లైట్ అంటే పరికరం యొక్క గడియారం ఇంకా సింక్ కాలేదు.';

  @override
  String get continueAnyway => 'కొనసాగించు';

  @override
  String get tasksClearCompleted => 'పూర్తయినవి తీసివేయి';

  @override
  String get tasksSelectAll => 'అన్నీ ఎంచుకో';

  @override
  String tasksDeleteSelected(int count) {
    return '$count పని(లు) తొలగించు';
  }

  @override
  String get tasksMarkComplete => 'పూర్తయినట్లు గుర్తించబడింది';

  @override
  String get appleHealthManageNote =>
      'Omi Apple యొక్క HealthKit ఫ్రేమ్‌వర్క్ ద్వారా Apple Health ను యాక్సెస్ చేస్తుంది. మీరు ఎప్పుడైనా iOS సెట్టింగ్‌ల నుండి యాక్సెస్‌ను ఉపసంహరించుకోవచ్చు.';

  @override
  String get appleHealthConnectCta => 'Apple Health కి కనెక్ట్ చేయండి';

  @override
  String get appleHealthDisconnectCta => 'Apple Health డిస్కనెక్ట్ చేయండి';

  @override
  String get appleHealthConnectedBadge => 'కనెక్ట్ అయింది';

  @override
  String get appleHealthFeatureChatTitle => 'మీ ఆరోగ్యం గురించి చాట్ చేయండి';

  @override
  String get appleHealthFeatureChatDesc => 'Omi ను మీ అడుగులు, నిద్ర, గుండె రేటు మరియు వర్కవుట్‌ల గురించి అడగండి.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'చదవడానికి మాత్రమే యాక్సెస్';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi Apple Health కు ఎప్పుడూ వ్రాయదు లేదా మీ డేటాను మార్చదు.';

  @override
  String get appleHealthFeatureSecureTitle => 'సురక్షిత సమకాలీకరణ';

  @override
  String get appleHealthFeatureSecureDesc => 'మీ Apple Health డేటా ప్రైవేట్‌గా మీ Omi ఖాతాకు సమకాలీకరించబడుతుంది.';

  @override
  String get appleHealthDeniedTitle => 'Apple Health యాక్సెస్ తిరస్కరించబడింది';

  @override
  String get appleHealthDeniedBody =>
      'Omi కి మీ Apple Health డేటాను చదవడానికి అనుమతి లేదు. iOS సెట్టింగ్‌లు → గోప్యత & భద్రత → Health → Omi లో దీన్ని ప్రారంభించండి.';

  @override
  String get deleteFlowReasonTitle => 'మీరు ఎందుకు వెళ్తున్నారు?';

  @override
  String get deleteFlowReasonSubtitle => 'మీ అభిప్రాయం అందరికీ Omi-ని మెరుగుపరచడంలో మాకు సహాయపడుతుంది.';

  @override
  String get deleteReasonPrivacy => 'గోప్యత ఆందోళనలు';

  @override
  String get deleteReasonNotUsing => 'తగినంతగా ఉపయోగించడం లేదు';

  @override
  String get deleteReasonMissingFeatures => 'నాకు కావలసిన ఫీచర్లు లేవు';

  @override
  String get deleteReasonTechnicalIssues => 'చాలా సాంకేతిక సమస్యలు';

  @override
  String get deleteReasonFoundAlternative => 'మరొకటి ఉపయోగిస్తున్నాను';

  @override
  String get deleteReasonTakingBreak => 'కేవలం విరామం తీసుకుంటున్నాను';

  @override
  String get deleteReasonOther => 'ఇతరత్రా';

  @override
  String get deleteFlowFeedbackTitle => 'మరింత చెప్పండి';

  @override
  String get deleteFlowFeedbackSubtitle => 'Omi మీకు ఎలా పని చేసేది?';

  @override
  String get deleteFlowFeedbackHint => 'ఐచ్ఛికం — మీ ఆలోచనలు మెరుగైన ఉత్పత్తిని తయారు చేయడంలో మాకు సహాయపడతాయి.';

  @override
  String get deleteFlowConfirmTitle => 'ఇది శాశ్వతం';

  @override
  String get deleteFlowConfirmSubtitle => 'మీరు ఖాతాను తొలగించిన తర్వాత, దాన్ని పునరుద్ధరించే మార్గం లేదు.';

  @override
  String get deleteConsequenceSubscription => 'ఏదైనా క్రియాశీల సబ్‌స్క్రిప్షన్ రద్దు చేయబడుతుంది.';

  @override
  String get deleteConsequenceNoRecovery => 'మీ ఖాతాను పునరుద్ధరించలేరు — సపోర్ట్ కూడా చేయలేదు.';

  @override
  String get deleteTypeToConfirm => 'నిర్ధారించడానికి DELETE టైప్ చేయండి';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'ఖాతాను శాశ్వతంగా తొలగించండి';

  @override
  String get keepMyAccount => 'నా ఖాతాను ఉంచండి';

  @override
  String get deleteAccountFailed => 'మీ ఖాతాను తొలగించలేకపోయాము. దయచేసి మళ్ళీ ప్రయత్నించండి.';

  @override
  String get planUpdate => 'ప్లాన్ అప్‌డేట్';

  @override
  String get planDeprecationMessage =>
      'మీ Unlimited ప్లాన్ ఆపివేయబడుతోంది. Operator ప్లాన్‌కి మారండి — అదే అద్భుతమైన ఫీచర్లు \$49/నెలకు. మీ ప్రస్తుత ప్లాన్ ఈలోగా పని చేస్తూనే ఉంటుంది.';

  @override
  String get upgradeYourPlan => 'మీ ప్లాన్‌ను అప్‌గ్రేడ్ చేయండి';

  @override
  String get youAreOnAPaidPlan => 'మీరు చెల్లింపు ప్లాన్‌లో ఉన్నారు.';

  @override
  String get chatTitle => 'చాట్';

  @override
  String get chatMessages => 'సందేశాలు';

  @override
  String get unlimitedChatThisMonth => 'ఈ నెల అపరిమిత చాట్ సందేశాలు';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used / $limit కంప్యూట్ బడ్జెట్ వాడారు';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return 'ఈ నెల $used / $limit సందేశాలు వాడారు';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit వాడారు';
  }

  @override
  String get chatLimitReachedUpgrade => 'చాట్ పరిమితి చేరుకుంది. మరిన్ని సందేశాల కోసం అప్‌గ్రేడ్ చేయండి.';

  @override
  String get chatLimitReachedTitle => 'చాట్ పరిమితి చేరుకుంది';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return '$plan ప్లాన్‌లో $limitDisplay నుండి $used వాడారు.';
  }

  @override
  String resetsInDays(int count) {
    return '$count రోజుల్లో రీసెట్ అవుతుంది';
  }

  @override
  String resetsInHours(int count) {
    return '$count గంటల్లో రీసెట్ అవుతుంది';
  }

  @override
  String get resetsSoon => 'త్వరలో రీసెట్ అవుతుంది';

  @override
  String get upgradePlan => 'ప్లాన్ అప్‌గ్రేడ్';

  @override
  String get billingMonthly => 'నెలవారీ';

  @override
  String get billingYearly => 'సంవత్సరానికి';

  @override
  String get savePercent => '~17% ఆదా చేయండి';

  @override
  String get popular => 'ప్రజాదరణ';

  @override
  String get currentPlan => 'ప్రస్తుత';

  @override
  String neoSubtitle(int count) {
    return 'నెలకు $count ప్రశ్నలు';
  }

  @override
  String operatorSubtitle(int count) {
    return 'నెలకు $count ప్రశ్నలు';
  }

  @override
  String get architectSubtitle => 'పవర్-యూజర్ AI — వేల చాట్‌లు + ఏజెంటిక్ ఆటోమేషన్';

  @override
  String chatUsageCost(String used, String limit) {
    return 'చాట్: \$$used / \$$limit ఈ నెల ఉపయోగించబడింది';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'చాట్: \$$used ఈ నెల ఉపయోగించబడింది';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'చాట్: $used / $limit సందేశాలు ఈ నెల';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'చాట్: $used సందేశాలు ఈ నెల';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'మీరు మీ నెలవారీ పరిమితిని చేరుకున్నారు. పరిమితులు లేకుండా Omi తో చాట్ కొనసాగించడానికి అప్‌గ్రేడ్ చేయండి.';

  @override
  String get voiceResponseAudio => 'Omi ప్రతిస్పందనను బిగ్గరగా చదవండి';

  @override
  String get voiceResponseMode => 'వాయిస్ ప్రతిస్పందన';

  @override
  String get voiceResponseModeTitle => 'ప్రతిస్పందనలను ఎప్పుడు చదవాలి';

  @override
  String get voiceResponseOff => 'ఆఫ్';

  @override
  String get voiceResponseHeadphonesOnly => 'హెడ్‌ఫోన్‌లు మాత్రమే';

  @override
  String get voiceResponseAlways => 'ఎల్లప్పుడూ';

  @override
  String get agreeAndContinue => 'అంగీకరించి కొనసాగించండి';

  @override
  String get startVoiceRecording => 'వాయిస్ రికార్డింగ్ ప్రారంభించండి';

  @override
  String get startCallRecording => 'కాల్ రికార్డింగ్ ప్రారంభించండి';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'వాయిస్ మోడ్';

  @override
  String get quickActionAskOmi => 'Omi ని ఏమైనా అడగండి';

  @override
  String get record => 'రికార్డ్';

  @override
  String get stop => 'ఆపు';

  @override
  String get recordWithPhoneMic => 'ఫోన్ మైక్‌తో రికార్డ్ చేయండి';

  @override
  String get recordWithPhoneMicSubtitle => 'మీ చుట్టూ ఉన్న ఆడియోను క్యాప్చర్ చేయండి';

  @override
  String get phoneCall => 'ఫోన్ కాల్';

  @override
  String get phoneCallSubtitle => 'లైవ్ ట్రాన్స్‌క్రిప్షన్‌తో కాల్‌ను రికార్డ్ చేయండి';

  @override
  String get searchActionItems => 'చర్య అంశాలను వెతకండి';

  @override
  String get selectActionItems => 'బహుళ ఎంపిక';

  @override
  String chooseExportDestination(int count) {
    return '$count అంశం(ాలను) ఎగుమతి చేయండి…';
  }

  @override
  String get bulkExportInProgress => 'ఎగుమతి చేస్తోంది…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$count ని $platform కు ఎగుమతి చేయబడింది';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$total లో $success ని $platform కు ఎగుమతి చేయబడింది';
  }

  @override
  String get showCompletedTasks => 'పూర్తయినవి చూపించు';

  @override
  String get hideCompletedTasks => 'పూర్తయినవి దాచు';

  @override
  String get selectAllTasksMenu => 'అన్నీ ఎంచుకోండి';

  @override
  String get connectTaskAppToExport => 'ఎగుమతి చేయడానికి సెట్టింగ్‌లలో టాస్క్ యాప్‌ను కనెక్ట్ చేయండి';

  @override
  String get connectAction => 'కనెక్ట్ చేయండి';

  @override
  String get deselectAllTasksMenu => 'అన్ని ఎంపికలు తొలగించు';
}
