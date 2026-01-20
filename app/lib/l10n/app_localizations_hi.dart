// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Hindi (`hi`).
class AppLocalizationsHi extends AppLocalizations {
  AppLocalizationsHi([String locale = 'hi']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'बातचीत';

  @override
  String get transcriptTab => 'प्रतिलेख';

  @override
  String get actionItemsTab => 'कार्य';

  @override
  String get deleteConversationTitle => 'बातचीत हटाएं?';

  @override
  String get deleteConversationMessage =>
      'क्या आप वाकई इस बातचीत को हटाना चाहते हैं? यह क्रिया पूर्ववत नहीं की जा सकती।';

  @override
  String get confirm => 'पुष्टि करें';

  @override
  String get cancel => 'Cancel';

  @override
  String get ok => 'ठीक है';

  @override
  String get delete => 'हटाएं';

  @override
  String get add => 'जोड़ें';

  @override
  String get update => 'अपडेट करें';

  @override
  String get save => 'सहेजें';

  @override
  String get edit => 'संपादित करें';

  @override
  String get close => 'बंद करें';

  @override
  String get clear => 'साफ़ करें';

  @override
  String get copyTranscript => 'प्रतिलिपि कॉपी करें';

  @override
  String get copySummary => 'सारांश कॉपी करें';

  @override
  String get testPrompt => 'टेस्ट प्रॉम्प्ट';

  @override
  String get reprocessConversation => 'बातचीत को पुनः संसाधित करें';

  @override
  String get deleteConversation => 'बातचीत हटाएं';

  @override
  String get contentCopied => 'सामग्री क्लिपबोर्ड पर कॉपी की गई';

  @override
  String get failedToUpdateStarred => 'तारांकित स्थिति अपडेट करने में विफल।';

  @override
  String get conversationUrlNotShared => 'बातचीत URL साझा नहीं किया गया।';

  @override
  String get errorProcessingConversation => 'बातचीत संसाधित करने में त्रुटि। कृपया बाद में पुनः प्रयास करें।';

  @override
  String get noInternetConnection => 'कोई इंटरनेट कनेक्शन नहीं';

  @override
  String get unableToDeleteConversation => 'बातचीत हटाने में असमर्थ';

  @override
  String get somethingWentWrong => 'कुछ गलत हो गया! कृपया बाद में पुनः प्रयास करें।';

  @override
  String get copyErrorMessage => 'त्रुटि संदेश कॉपी करें';

  @override
  String get errorCopied => 'त्रुटि संदेश कॉपी किया गया';

  @override
  String get remaining => 'शेष';

  @override
  String get loading => 'लोड हो रहा है...';

  @override
  String get loadingDuration => 'अवधि लोड हो रही है...';

  @override
  String secondsCount(int count) {
    return '$count सेकंड';
  }

  @override
  String get people => 'लोग';

  @override
  String get addNewPerson => 'नया व्यक्ति जोड़ें';

  @override
  String get editPerson => 'व्यक्ति संपादित करें';

  @override
  String get createPersonHint => 'एक नया व्यक्ति बनाएं और Omi को उनकी आवाज़ पहचानने के लिए प्रशिक्षित करें!';

  @override
  String get speechProfile => 'भाषण प्रोफ़ाइल';

  @override
  String sampleNumber(int number) {
    return 'नमूना $number';
  }

  @override
  String get settings => 'सेटिंग्स';

  @override
  String get language => 'भाषा';

  @override
  String get selectLanguage => 'भाषा चुनें';

  @override
  String get deleting => 'हटा रहा है...';

  @override
  String get pleaseCompleteAuthentication => 'कृपया अपने ब्राउज़र में प्रमाणीकरण पूरा करें। हो जाने पर ऐप पर वापस आएं।';

  @override
  String get failedToStartAuthentication => 'प्रमाणीकरण शुरू करने में विफल';

  @override
  String get importStarted => 'आयात शुरू हुआ! पूरा होने पर हम आपको सूचित करेंगे।';

  @override
  String get failedToStartImport => 'आयात शुरू करने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get couldNotAccessFile => 'चयनित फ़ाइल नहीं खोल सके';

  @override
  String get askOmi => 'Omi से पूछें';

  @override
  String get done => 'हो गया';

  @override
  String get disconnected => 'डिस्कनेक्ट किया गया';

  @override
  String get searching => 'खोज रहे हैं...';

  @override
  String get connectDevice => 'डिवाइस कनेक्ट करें';

  @override
  String get monthlyLimitReached => 'आप अपनी मासिक सीमा तक पहुँच गए हैं।';

  @override
  String get checkUsage => 'उपयोग जांचें';

  @override
  String get syncingRecordings => 'रिकॉर्डिंग सिंक हो रही है';

  @override
  String get recordingsToSync => 'सिंक करने के लिए रिकॉर्डिंग';

  @override
  String get allCaughtUp => 'सब कुछ सिंक हो गया';

  @override
  String get sync => 'सिंक';

  @override
  String get pendantUpToDate => 'पेंडेंट अद्यतित है';

  @override
  String get allRecordingsSynced => 'सभी रिकॉर्डिंग सिंक हो गईं';

  @override
  String get syncingInProgress => 'सिंक जारी है';

  @override
  String get readyToSync => 'सिंक करने के लिए तैयार';

  @override
  String get tapSyncToStart => 'शुरू करने के लिए सिंक टैप करें';

  @override
  String get pendantNotConnected => 'पेंडेंट कनेक्ट नहीं है। सिंक करने के लिए कनेक्ट करें।';

  @override
  String get everythingSynced => 'सब कुछ सिंक है।';

  @override
  String get recordingsNotSynced => 'आपकी कुछ रिकॉर्डिंग अभी सिंक नहीं हुई हैं।';

  @override
  String get syncingBackground => 'हम बैकग्राउंड में आपकी रिकॉर्डिंग सिंक करते रहेंगे।';

  @override
  String get noConversationsYet => 'अभी तक कोई बातचीत नहीं';

  @override
  String get noStarredConversations => 'कोई तारांकित बातचीत नहीं';

  @override
  String get starConversationHint => 'बातचीत को तारांकित करने के लिए, उसे खोलें और शीर्ष पर तारे के आइकन को टैप करें।';

  @override
  String get searchConversations => 'बातचीत खोजें...';

  @override
  String selectedCount(int count, Object s) {
    return '$count चयनित';
  }

  @override
  String get merge => 'विलय करें';

  @override
  String get mergeConversations => 'बातचीत का विलय करें';

  @override
  String mergeConversationsMessage(int count) {
    return 'यह $count बातचीतों को एक में मिला देगा। सभी सामग्री विलय और पुन: उत्पन्न की जाएगी।';
  }

  @override
  String get mergingInBackground => 'बैकग्राउंड में विलय हो रहा है। इसमें थोड़ा समय लग सकता है।';

  @override
  String get failedToStartMerge => 'विलय शुरू करने में विफल';

  @override
  String get askAnything => 'कुछ भी पूछें';

  @override
  String get noMessagesYet => 'अभी तक कोई संदेश नहीं!\nबातचीत क्यों नहीं शुरू करते?';

  @override
  String get deletingMessages => 'Omi की मेमोरी से आपके संदेशों को हटा रहा है...';

  @override
  String get messageCopied => '✨ संदेश क्लिपबोर्ड पर कॉपी किया गया';

  @override
  String get cannotReportOwnMessage => 'आप अपने खुद के संदेशों की रिपोर्ट नहीं कर सकते।';

  @override
  String get reportMessage => 'संदेश रिपोर्ट करें';

  @override
  String get reportMessageConfirm => 'क्या आप वाकई इस संदेश की रिपोर्ट करना चाहते हैं?';

  @override
  String get messageReported => 'संदेश सफलतापूर्वक रिपोर्ट किया गया।';

  @override
  String get thankYouFeedback => 'आपकी प्रतिक्रिया के लिए धन्यवाद!';

  @override
  String get clearChat => 'चैट साफ करें';

  @override
  String get clearChatConfirm => 'क्या आप वाकई चैट साफ़ करना चाहते हैं? यह पूर्ववत नहीं किया जा सकता।';

  @override
  String get maxFilesLimit => 'आप एक बार में केवल 4 फ़ाइलें अपलोड कर सकते हैं';

  @override
  String get chatWithOmi => 'Omi के साथ चैट करें';

  @override
  String get apps => 'ऐप्स';

  @override
  String get noAppsFound => 'कोई ऐप नहीं मिला';

  @override
  String get tryAdjustingSearch => 'अपनी खोज या फ़िल्टर समायोजित करने का प्रयास करें';

  @override
  String get createYourOwnApp => 'अपना खुद का ऐप बनाएं';

  @override
  String get buildAndShareApp => 'अपना खुद का ऐप बनाएं और साझा करें';

  @override
  String get searchApps => 'ऐप्स खोजें...';

  @override
  String get myApps => 'मेरे ऐप्स';

  @override
  String get installedApps => 'इंस्टॉल किए गए ऐप्स';

  @override
  String get unableToFetchApps => 'ऐप्स लोड करने में असमर्थ :(\n\nकृपया अपना इंटरनेट कनेक्शन जांचें।';

  @override
  String get aboutOmi => 'Omi के बारे में';

  @override
  String get privacyPolicy => 'गोपनीयता नीति';

  @override
  String get visitWebsite => 'वेबसाइट पर जाएं';

  @override
  String get helpOrInquiries => 'मदद या पूछताछ?';

  @override
  String get joinCommunity => 'समुदाय में शामिल हों!';

  @override
  String get membersAndCounting => '8000+ सदस्य और गिनती जारी है।';

  @override
  String get deleteAccountTitle => 'खाता हटाएं';

  @override
  String get deleteAccountConfirm => 'क्या आप वाकई अपना खाता हटाना चाहते हैं?';

  @override
  String get cannotBeUndone => 'यह पूर्ववत नहीं किया जा सकता।';

  @override
  String get allDataErased => 'आपकी सभी यादें और बातचीत स्थायी रूप से हटा दी जाएंगी।';

  @override
  String get appsDisconnected => 'आपके ऐप्स और एकीकरण तुरंत डिस्कनेक्ट हो जाएंगे।';

  @override
  String get exportBeforeDelete =>
      'अपना खाता हटाने से पहले आप अपना डेटा निर्यात कर सकते हैं। एक बार हटाए जाने के बाद, इसे पुनर्प्राप्त नहीं किया जा सकता है।';

  @override
  String get deleteAccountCheckbox =>
      'मैं समझता/समझती हूं कि अपना खाता हटाना स्थायी है और यादों और बातचीत सहित सभी डेटा हमेशा के लिए खो जाएंगे।';

  @override
  String get areYouSure => 'क्या आप सुनिश्चित हैं?';

  @override
  String get deleteAccountFinal =>
      'यह क्रिया अपरिवर्तनीय है और आपके खाते और उससे जुड़े सभी डेटा को स्थायी रूप से हटा देगी। क्या आप जारी रखना चाहते हैं?';

  @override
  String get deleteNow => 'अभी हटाएं';

  @override
  String get goBack => 'वापस जाएं';

  @override
  String get checkBoxToConfirm =>
      'पुष्टि करने के लिए चेकबॉक्स चेक करें कि आप समझते हैं कि आपका खाता हटाना स्थायी और अपरिवर्तनीय है।';

  @override
  String get profile => 'प्रोफ़ाइल';

  @override
  String get name => 'नाम';

  @override
  String get email => 'ईमेल';

  @override
  String get customVocabulary => 'कस्टम शब्दावली';

  @override
  String get identifyingOthers => 'दूसरों की पहचान';

  @override
  String get paymentMethods => 'भुगतान विधियाँ';

  @override
  String get conversationDisplay => 'बातचीत प्रदर्शन';

  @override
  String get dataPrivacy => 'डेटा गोपनीयता';

  @override
  String get userId => 'उपयोगकर्ता ID';

  @override
  String get notSet => 'सेट नहीं';

  @override
  String get userIdCopied => 'उपयोगकर्ता ID कॉपी किया गया';

  @override
  String get systemDefault => 'सिस्टम डिफ़ॉल्ट';

  @override
  String get planAndUsage => 'योजना और उपयोग';

  @override
  String get offlineSync => 'Offline Sync';

  @override
  String get deviceSettings => 'डिवाइस सेटिंग्स';

  @override
  String get chatTools => 'चैट टूल्स';

  @override
  String get feedbackBug => 'प्रतिक्रिया / बग';

  @override
  String get helpCenter => 'सहायता केंद्र';

  @override
  String get developerSettings => 'डेवलपर सेटिंग्स';

  @override
  String get getOmiForMac => 'Mac के लिए Omi प्राप्त करें';

  @override
  String get referralProgram => 'रेफ़रल कार्यक्रम';

  @override
  String get signOut => 'साइन आउट';

  @override
  String get appAndDeviceCopied => 'ऐप और डिवाइस विवरण कॉपी किए गए';

  @override
  String get wrapped2025 => '2025 रैप्ड';

  @override
  String get yourPrivacyYourControl => 'आपकी गोपनीयता, आपका नियंत्रण';

  @override
  String get privacyIntro =>
      'Omi में, हम आपकी गोपनीयता की रक्षा के लिए प्रतिबद्ध हैं। यह पृष्ठ आपको यह नियंत्रित करने की अनुमति देता है कि आपका डेटा कैसे सहेजा और उपयोग किया जाता है।';

  @override
  String get learnMore => 'और जानें...';

  @override
  String get dataProtectionLevel => 'डेटा सुरक्षा स्तर';

  @override
  String get dataProtectionDesc => 'डिफ़ॉल्ट रूप से, आपका डेटा मजबूत एन्क्रिप्शन द्वारा सुरक्षित है।';

  @override
  String get appAccess => 'ऐप एक्सेस';

  @override
  String get appAccessDesc =>
      'निम्नलिखित ऐप्स के पास आपके डेटा तक पहुंच है। अनुमतियाँ प्रबंधित करने के लिए किसी ऐप पर टैप करें।';

  @override
  String get noAppsExternalAccess => 'किसी भी इंस्टॉल किए गए ऐप के पास आपके डेटा तक बाहरी पहुंच नहीं है।';

  @override
  String get deviceName => 'डिवाइस का नाम';

  @override
  String get deviceId => 'डिवाइस आईडी';

  @override
  String get firmware => 'फर्मवेयर';

  @override
  String get sdCardSync => 'SD कार्ड सिंक';

  @override
  String get hardwareRevision => 'हार्डवेयर संशोधन';

  @override
  String get modelNumber => 'मॉडल संख्या';

  @override
  String get manufacturer => 'निर्माता';

  @override
  String get doubleTap => 'डबल टैप';

  @override
  String get ledBrightness => 'LED चमक';

  @override
  String get micGain => 'माइक गेन';

  @override
  String get disconnect => 'डिस्कनेक्ट करें';

  @override
  String get forgetDevice => 'डिवाइस भूल जाएं';

  @override
  String get chargingIssues => 'चार्जिंग समस्याएं';

  @override
  String get disconnectDevice => 'डिवाइस डिस्कनेक्ट करें';

  @override
  String get unpairDevice => 'डिवाइस को अनपेयर करें';

  @override
  String get unpairAndForget => 'अनपेयर करें और डिवाइस भूल जाएं';

  @override
  String get deviceDisconnectedMessage => 'आपका Omi डिस्कनेक्ट हो गया 😔';

  @override
  String get deviceUnpairedMessage =>
      'डिवाइस अनपेयर किया गया। अनपेयरिंग पूरी करने के लिए सेटिंग्स > ब्लूटूथ पर जाएं और डिवाइस को भूल जाएं।';

  @override
  String get unpairDialogTitle => 'डिवाइस अनपेयर करें';

  @override
  String get unpairDialogMessage =>
      'यह डिवाइस को अनपेयर कर देगा ताकि इसे दूसरे फोन पर इस्तेमाल किया जा सके। प्रक्रिया पूरी करने के लिए आपको सेटिंग्स > ब्लूटूथ पर जाना होगा और डिवाइस को भूलना होगा।';

  @override
  String get deviceNotConnected => 'डिवाइस कनेक्ट नहीं है';

  @override
  String get connectDeviceMessage => 'सेटिंग्स और अनुकूलन तक पहुँचने के लिए अपने Omi डिवाइस को कनेक्ट करें।';

  @override
  String get deviceInfoSection => 'डिवाइस जानकारी';

  @override
  String get customizationSection => 'अनुकूलन';

  @override
  String get hardwareSection => 'हार्डवेयर';

  @override
  String get v2Undetected => 'V2 का पता नहीं चला';

  @override
  String get v2UndetectedMessage =>
      'हमें लगता है कि आप V1 डिवाइस का उपयोग कर रहे हैं या यह कनेक्ट नहीं है। SD कार्ड कार्यक्षमता केवल V2 उपकरणों के लिए है।';

  @override
  String get endConversation => 'बातचीत समाप्त करें';

  @override
  String get pauseResume => 'रोकें/दोबारा शुरू करें';

  @override
  String get starConversation => 'बातचीत को तारांकित करें';

  @override
  String get doubleTapAction => 'डबल टैप क्रिया';

  @override
  String get endAndProcess => 'समाप्त करें और संसाधित करें';

  @override
  String get pauseResumeRecording => 'रिकॉर्डिंग रोकें/दोबारा शुरू करें';

  @override
  String get starOngoing => 'चल रही बातचीत को तारांकित करें';

  @override
  String get off => 'Off';

  @override
  String get max => 'अधिकतम';

  @override
  String get mute => 'म्यूट';

  @override
  String get quiet => 'शांत';

  @override
  String get normal => 'सामान्य';

  @override
  String get high => 'उच्च';

  @override
  String get micGainDescMuted => 'माइक्रोफ़ोन म्यूट है';

  @override
  String get micGainDescLow => 'बहुत कम - बहुत शोर वाले वातावरण के लिए';

  @override
  String get micGainDescModerate => 'कम - मध्यम शोर के लिए';

  @override
  String get micGainDescNeutral => 'तटस्थ - संतुलित रिकॉर्डिंग';

  @override
  String get micGainDescSlightlyBoosted => 'थोड़ा बढ़ाया हुआ - सामान्य उपयोग';

  @override
  String get micGainDescBoosted => 'बढ़ाया हुआ - शांत वातावरण के लिए';

  @override
  String get micGainDescHigh => 'उच्च - दूर या शांत आवाज़ों के लिए';

  @override
  String get micGainDescVeryHigh => 'बहुत उच्च - बहुत शांत स्रोतों के लिए';

  @override
  String get micGainDescMax => 'अधिकतम - सावधानी के साथ प्रयोग करें';

  @override
  String get developerSettingsTitle => 'डेवलपर सेटिंग्स';

  @override
  String get saving => 'सहेजा जा रहा है...';

  @override
  String get personaConfig => 'अपना AI व्यक्तित्व कॉन्फ़िगर करें';

  @override
  String get beta => 'बीटा';

  @override
  String get transcription => 'प्रतिलेखन';

  @override
  String get transcriptionConfig => 'STT प्रदाता कॉन्फ़िगर करें';

  @override
  String get conversationTimeout => 'बातचीत समय समाप्त';

  @override
  String get conversationTimeoutConfig => 'स्वचालित रूप से बातचीत समाप्त होने का समय सेट करें';

  @override
  String get importData => 'डेटा आयात करें';

  @override
  String get importDataConfig => 'अन्य स्रोतों से डेटा आयात करें';

  @override
  String get debugDiagnostics => 'डीबग और डायग्नोस्टिक्स';

  @override
  String get endpointUrl => 'एंडपॉइंट URL';

  @override
  String get noApiKeys => 'अभी तक कोई API कुंजी नहीं';

  @override
  String get createKeyToStart => 'शुरू करने के लिए एक कुंजी बनाएं';

  @override
  String get createKey => 'कुंजी बनाएं';

  @override
  String get docs => 'दस्तावेज़';

  @override
  String get yourOmiInsights => 'आपकी Omi अंतर्दृष्टि';

  @override
  String get today => 'आज';

  @override
  String get thisMonth => 'इस महीने';

  @override
  String get thisYear => 'इस साल';

  @override
  String get allTime => 'अब तक';

  @override
  String get noActivityYet => 'अभी तक कोई गतिविधि नहीं';

  @override
  String get startConversationToSeeInsights => 'अपनी अंतर्दृष्टि यहां देखने के लिए\nOmi के साथ बातचीत शुरू करें।';

  @override
  String get listening => 'सुन रहा है';

  @override
  String get listeningSubtitle => 'Omi द्वारा सक्रिय रूप से सुनी गई कुल अवधि।';

  @override
  String get understanding => 'समझ रहा है';

  @override
  String get understandingSubtitle => 'आपकी बातचीत से समझे गए शब्द।';

  @override
  String get providing => 'प्रदान कर रहा है';

  @override
  String get providingSubtitle => 'स्वचालित रूप से कैप्चर किए गए कार्य और नोट्स।';

  @override
  String get remembering => 'याद रख रहा है';

  @override
  String get rememberingSubtitle => 'तथ्य और विवरण आपके लिए याद रखे गए।';

  @override
  String get unlimitedPlan => 'असीमित योजना';

  @override
  String get managePlan => 'योजना प्रबंधित करें';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'आपकी योजना $date को समाप्त हो रही है।';
  }

  @override
  String renewsOn(String date) {
    return 'आपकी योजना $date को नवीनीकृत होती है।';
  }

  @override
  String get basicPlan => 'निःशुल्क योजना';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used / $limit मिनट उपयोग किए गए';
  }

  @override
  String get upgrade => 'अपग्रेड करें';

  @override
  String get upgradeToUnlimited => 'असीमित में अपग्रेड करें';

  @override
  String basicPlanDesc(int limit) {
    return 'आपकी योजना में $limit मुफ़्त मिनट/माह शामिल हैं।';
  }

  @override
  String get shareStatsMessage => 'मेरे Omi आँकड़े साझा कर रहा हूँ! (omi.me - मेरा हमेशा चालू रहने वाला AI साथी)';

  @override
  String get sharePeriodToday => 'आज Omi:';

  @override
  String get sharePeriodMonth => 'इस महीने Omi:';

  @override
  String get sharePeriodYear => 'इस साल Omi:';

  @override
  String get sharePeriodAllTime => 'अब तक Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes मिनट सुना';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words शब्द समझे';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count अंतर्दृष्टि प्रदान कीं';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count यादें सहेजीं';
  }

  @override
  String get debugLogs => 'डिबग लॉग';

  @override
  String get debugLogsAutoDelete => '3 दिनों के बाद स्वचालित रूप से हटा दिया जाता है।';

  @override
  String get debugLogsDesc => 'समस्याओं का निदान करने में मदद करता है';

  @override
  String get noLogFilesFound => 'कोई लॉग फ़ाइल नहीं मिली।';

  @override
  String get omiDebugLog => 'Omi डीबग लॉग';

  @override
  String get logShared => 'लॉग साझा किया गया';

  @override
  String get selectLogFile => 'लॉग फ़ाइल चुनें';

  @override
  String get shareLogs => 'लॉग साझा करें';

  @override
  String get debugLogCleared => 'डीबग लॉग साफ़ किया गया';

  @override
  String get exportStarted => 'निर्यात शुरू हुआ। इसमें कुछ सेकंड लग सकते हैं...';

  @override
  String get exportAllData => 'सारा डेटा निर्यात करें';

  @override
  String get exportDataDesc => 'बातचीत को JSON फ़ाइल में निर्यात करें';

  @override
  String get exportedConversations => 'Omi निर्यातित बातचीत';

  @override
  String get exportShared => 'निर्यात साझा किया गया';

  @override
  String get deleteKnowledgeGraphTitle => 'नॉलेज ग्राफ़ हटाएं?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'यह सभी व्युत्पन्न ग्राफ़ डेटा (नोड्स और कनेक्शन) को हटा देगा। आपकी मूल यादें सुरक्षित रहती हैं।';

  @override
  String get knowledgeGraphDeleted => 'ज्ञान ग्राफ़ हटाया गया';

  @override
  String deleteGraphFailed(String error) {
    return 'ग्राफ़ हटाने में विफल: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'नॉलेज ग्राफ़ हटाएं';

  @override
  String get deleteKnowledgeGraphDesc => 'सभी नोड्स और कनेक्शन हटा दें';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP सर्वर';

  @override
  String get mcpServerDesc => 'AI सहायकों को अपने डेटा से कनेक्ट करें';

  @override
  String get serverUrl => 'सर्वर URL';

  @override
  String get urlCopied => 'URL कॉपी किया गया';

  @override
  String get apiKeyAuth => 'API कुंजी प्रमाणीकरण';

  @override
  String get header => 'हेडर';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => 'अपनी MCP API कुंजी का उपयोग करें';

  @override
  String get webhooks => 'वेबहुक';

  @override
  String get conversationEvents => 'बातचीत इवेंट';

  @override
  String get newConversationCreated => 'नई बातचीत बनाई गई';

  @override
  String get realtimeTranscript => 'रियल-टाइम ट्रांसक्रिप्ट';

  @override
  String get transcriptReceived => 'ट्रांसक्रिप्ट प्राप्त';

  @override
  String get audioBytes => 'ऑडियो बाइट्स';

  @override
  String get audioDataReceived => 'ऑडियो डेटा प्राप्त';

  @override
  String get intervalSeconds => 'अंतराल (सेकंड)';

  @override
  String get daySummary => 'दिन का सारांश';

  @override
  String get summaryGenerated => 'सारांश उत्पन्न हुआ';

  @override
  String get claudeDesktop => 'Claude डेस्कटॉप';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.json में जोड़ें';

  @override
  String get copyConfig => 'कॉन्फ़िगरेशन कॉपी करें';

  @override
  String get configCopied => 'कॉन्फ़िगरेशन कॉपी किया गया';

  @override
  String get listeningMins => 'सुनना (मिनट)';

  @override
  String get understandingWords => 'समझना (शब्द)';

  @override
  String get insights => 'अंतर्दृष्टि';

  @override
  String get memories => 'यादें';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'इस महीने $used/$limit मिनट उपयोग किए गए';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'इस महीने $used/$limit शब्द उपयोग किए गए';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'इस महीने $used/$limit अंतर्दृष्टि प्राप्त कीं';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'इस महीने $used/$limit यादें बनाईं';
  }

  @override
  String get visibility => 'दृश्यता';

  @override
  String get visibilitySubtitle => 'नियंत्रित करें कि आपकी सूची में कौन सी बातचीत दिखाई दे';

  @override
  String get showShortConversations => 'छोटी बातचीत दिखाएं';

  @override
  String get showShortConversationsDesc => 'थ्रेसहोल्ड से छोटी बातचीत दिखाएं';

  @override
  String get showDiscardedConversations => 'रद्द की गई बातचीत दिखाएं';

  @override
  String get showDiscardedConversationsDesc => 'रद्द के रूप में चिह्नित बातचीत शामिल करें';

  @override
  String get shortConversationThreshold => 'लघु वार्तालाप थ्रेसहोल्ड';

  @override
  String get shortConversationThresholdSubtitle => 'इससे छोटी बातचीत छिपाई जाएगी (जब तक कि ऊपर सक्षम न हो)';

  @override
  String get durationThreshold => 'अवधि थ्रेसहोल्ड';

  @override
  String get durationThresholdDesc => 'इससे छोटी बातचीत छिपाएं';

  @override
  String minLabel(int count) {
    return '$count मिनट';
  }

  @override
  String get customVocabularyTitle => 'कस्टम शब्दावली';

  @override
  String get addWords => 'शब्द जोड़ें';

  @override
  String get addWordsDesc => 'नाम, शब्दशब्दावली, या असामान्य शब्द';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'कनेक्ट करें';

  @override
  String get comingSoon => 'जल्द आ रहा है';

  @override
  String get chatToolsFooter => 'चैट में डेटा और मेट्रिक्स देखने के लिए अपने ऐप्स कनेक्ट करें।';

  @override
  String get completeAuthInBrowser => 'कृपया अपने ब्राउज़र में प्रमाणीकरण पूरा करें।';

  @override
  String failedToStartAuth(String appName) {
    return '$appName के लिए प्रमाणीकरण शुरू करने में विफल';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName डिस्कनेक्ट करें?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'क्या आप वाकई $appName को डिस्कनेक्ट करना चाहते हैं? आप कभी भी फिर से कनेक्ट कर सकते हैं।';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName से डिस्कनेक्ट हो गया';
  }

  @override
  String get failedToDisconnect => 'डिस्कनेक्ट करने में विफल';

  @override
  String connectTo(String appName) {
    return '$appName से कनेक्ट करें';
  }

  @override
  String authAccessMessage(String appName) {
    return 'आपको अपने $appName डेटा तक पहुँचने के लिए Omi को अधिकृत करने की आवश्यकता है।';
  }

  @override
  String get continueAction => 'जारी रखें';

  @override
  String get languageTitle => 'भाषा';

  @override
  String get primaryLanguage => 'प्राथमिक भाषा';

  @override
  String get automaticTranslation => 'स्वचालित अनुवाद';

  @override
  String get detectLanguages => '10+ भाषाओं का पता लगाएं';

  @override
  String get authorizeSavingRecordings => 'रिकॉर्डिंग सहेजने को अधिकृत करें';

  @override
  String get thanksForAuthorizing => 'अधिकृत करने के लिए धन्यवाद!';

  @override
  String get needYourPermission => 'हमें आपकी अनुमति चाहिए';

  @override
  String get alreadyGavePermission =>
      'आपने हमें अपनी रिकॉर्डिंग सहेजने की अनुमति पहले ही दे दी है। हमें इसकी आवश्यकता क्यों है, इसका एक अनुस्मारक:';

  @override
  String get wouldLikePermission => 'हम आपकी वॉयस रिकॉर्डिंग सहेजने के लिए आपकी अनुमति चाहते हैं। यहाँ क्यों है:';

  @override
  String get improveSpeechProfile => 'अपनी वाक् प्रोफ़ाइल सुधारें';

  @override
  String get improveSpeechProfileDesc =>
      'हम आपकी व्यक्तिगत वाक् प्रोफ़ाइल को आगे प्रशिक्षित करने और सुधारने के लिए रिकॉर्डिंग का उपयोग करते हैं।';

  @override
  String get trainFamilyProfiles => 'दोस्तों और परिवार की प्रोफ़ाइल प्रशिक्षित करें';

  @override
  String get trainFamilyProfilesDesc =>
      'आपकी रिकॉर्डिंग हमें आपके दोस्तों और परिवार के सदस्यों को पहचानने और उनके लिए प्रोफ़ाइल बनाने में मदद करती हैं।';

  @override
  String get enhanceTranscriptAccuracy => 'ट्रांसक्रिप्ट सटीकता बढ़ाएं';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'जैसे-जैसे हमारा मॉडल सुधरता है, हम आपकी रिकॉर्डिंग के लिए बेहतर ट्रांसक्रिप्ट प्रदान कर सकते हैं।';

  @override
  String get legalNotice => 'कानूनी नोटिस: रिकॉर्डिंग की वैधता आपके स्थान के आधार पर भिन्न हो सकती है।';

  @override
  String get alreadyAuthorized => 'पहले ही अधिकृत';

  @override
  String get authorize => 'अधिकृत करें';

  @override
  String get revokeAuthorization => 'प्राधिकरण रद्द करें';

  @override
  String get authorizationSuccessful => 'प्राधिकरण सफल!';

  @override
  String get failedToAuthorize => 'अधिकृत करने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get authorizationRevoked => 'प्राधिकरण रद्द कर दिया गया।';

  @override
  String get recordingsDeleted => 'रिकॉर्डिंग हटा दी गईं।';

  @override
  String get failedToRevoke => 'प्राधिकरण रद्द करने में विफल।';

  @override
  String get permissionRevokedTitle => 'अनुमति रद्द कर दी गई';

  @override
  String get permissionRevokedMessage => 'क्या आप चाहते हैं कि हम आपकी सभी मौजूदा रिकॉर्डिंग भी हटा दें?';

  @override
  String get yes => 'हाँ';

  @override
  String get editName => 'Edit Name';

  @override
  String get howShouldOmiCallYou => 'Omi आपको क्या कहकर बुलाए?';

  @override
  String get enterYourName => 'अपना नाम दर्ज करें';

  @override
  String get nameCannotBeEmpty => 'नाम खाली नहीं हो सकता';

  @override
  String get nameUpdatedSuccessfully => 'नाम सफलतापूर्वक अपडेट किया गया!';

  @override
  String get calendarSettings => 'कैलेंडर सेटिंग्स';

  @override
  String get calendarProviders => 'कैलेंडर प्रदाता';

  @override
  String get macOsCalendar => 'macOS कैलेंडर';

  @override
  String get connectMacOsCalendar => 'अपने स्थानीय macOS कैलेंडर को कनेक्ट करें';

  @override
  String get googleCalendar => 'Google कैलेंडर';

  @override
  String get syncGoogleAccount => 'अपने Google खाते के साथ सिंक करें';

  @override
  String get showMeetingsMenuBar => 'मेनू बार में बैठकें दिखाएं';

  @override
  String get showMeetingsMenuBarDesc => 'macOS मेनू बार में अपनी अगली बैठक और शेष समय दिखाएं';

  @override
  String get showEventsNoParticipants => 'बिना प्रतिभागियों वाले ईवेंट दिखाएं';

  @override
  String get showEventsNoParticipantsDesc =>
      'यदि सक्षम किया गया, तो \'आगामी\' बिना प्रतिभागियों या वीडियो लिंक वाले ईवेंट दिखाएगा।';

  @override
  String get yourMeetings => 'आपकी बैठकें';

  @override
  String get refresh => 'रीफ्रेश करें';

  @override
  String get noUpcomingMeetings => 'कोई आगामी बैठक नहीं';

  @override
  String get checkingNextDays => 'अगले 30 दिनों की जाँच की जा रही है';

  @override
  String get tomorrow => 'कल';

  @override
  String get googleCalendarComingSoon => 'Google कैलेंडर एकीकरण जल्द आ रहा है!';

  @override
  String connectedAsUser(String userId) {
    return 'उपयोगकर्ता के रूप में कनेक्टेड: $userId';
  }

  @override
  String get defaultWorkspace => 'डिफ़ॉल्ट कार्यक्षेत्र';

  @override
  String get tasksCreatedInWorkspace => 'कार्य इस कार्यक्षेत्र में बनाए जाएंगे';

  @override
  String get defaultProjectOptional => 'डिफ़ॉल्ट प्रोजेक्ट (वैकल्पिक)';

  @override
  String get leaveUnselectedTasks => 'बिना प्रोजेक्ट वाले कार्यों के लिए चयनित न छोड़ें';

  @override
  String get noProjectsInWorkspace => 'इस कार्यक्षेत्र में कोई प्रोजेक्ट नहीं मिला';

  @override
  String get conversationTimeoutDesc => 'स्वचालित रूप से समाप्त होने से पहले कितनी देर तक मौन रहना है, यह चुनें:';

  @override
  String get timeout2Minutes => '2 मिनट';

  @override
  String get timeout2MinutesDesc => '2 मिनट के मौन के बाद समाप्त';

  @override
  String get timeout5Minutes => '5 मिनट';

  @override
  String get timeout5MinutesDesc => '5 मिनट के मौन के बाद समाप्त';

  @override
  String get timeout10Minutes => '10 मिनट';

  @override
  String get timeout10MinutesDesc => '10 मिनट के मौन के बाद समाप्त';

  @override
  String get timeout30Minutes => '30 मिनट';

  @override
  String get timeout30MinutesDesc => '30 मिनट के मौन के बाद समाप्त';

  @override
  String get timeout4Hours => '4 घंटे';

  @override
  String get timeout4HoursDesc => '4 घंटे के मौन के बाद समाप्त';

  @override
  String get conversationEndAfterHours => 'बातचीत 4 घंटे के मौन के बाद समाप्त हो जाएगी';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'बातचीत $minutes मिनट के मौन के बाद समाप्त हो जाएगी';
  }

  @override
  String get tellUsPrimaryLanguage => 'हमें अपनी प्राथमिक भाषा बताएं';

  @override
  String get languageForTranscription => 'स्पष्ट प्रतिलेखन के लिए अपनी भाषा सेट करें।';

  @override
  String get singleLanguageModeInfo => 'एकल भाषा मोड चालू है।';

  @override
  String get searchLanguageHint => 'नाम या कोड द्वारा भाषा खोजें';

  @override
  String get noLanguagesFound => 'कोई भाषा नहीं मिली';

  @override
  String get skip => 'छोड़ें';

  @override
  String languageSetTo(String language) {
    return 'भाषा $language पर सेट की गई';
  }

  @override
  String get failedToSetLanguage => 'भाषा सेट करने में विफल';

  @override
  String appSettings(String appName) {
    return '$appName सेटिंग्स';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName से डिस्कनेक्ट करें?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'यह आपके $appName प्रमाणीकरण को हटा देगा।';
  }

  @override
  String connectedToApp(String appName) {
    return '$appName से कनेक्टेड';
  }

  @override
  String get account => 'खाता';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'आपके कार्य आपके $appName खाते में सिंक हो जाते हैं';
  }

  @override
  String get defaultSpace => 'डिफ़ॉल्ट स्थान';

  @override
  String get selectSpaceInWorkspace => 'कार्यक्षेत्र में एक स्थान चुनें';

  @override
  String get noSpacesInWorkspace => 'कोई स्थान नहीं मिला';

  @override
  String get defaultList => 'डिफ़ॉल्ट सूची';

  @override
  String get tasksAddedToList => 'कार्य इस सूची में जोड़े जाएंगे';

  @override
  String get noListsInSpace => 'कोई सूची नहीं मिली';

  @override
  String failedToLoadRepos(String error) {
    return 'रिपॉजिटरी लोड करने में विफल: $error';
  }

  @override
  String get defaultRepoSaved => 'डिफ़ॉल्ट रिपॉजिटरी सहेजी गई';

  @override
  String get failedToSaveDefaultRepo => 'डिफ़ॉल्ट रिपॉजिटरी सहेजने में विफल';

  @override
  String get defaultRepository => 'डिफ़ॉल्ट रिपॉजिटरी';

  @override
  String get selectDefaultRepoDesc => 'समस्याएं बनाने के लिए एक डिफ़ॉल्ट रिपो चुनें।';

  @override
  String get noReposFound => 'कोई रिपॉजिटरी नहीं मिली';

  @override
  String get private => 'निजी';

  @override
  String updatedDate(String date) {
    return '$date को अपडेट किया गया';
  }

  @override
  String get yesterday => 'कल';

  @override
  String daysAgo(int count) {
    return '$count दिन पहले';
  }

  @override
  String get oneWeekAgo => '1 सप्ताह पहले';

  @override
  String weeksAgo(int count) {
    return '$count सप्ताह पहले';
  }

  @override
  String get oneMonthAgo => '1 महीने पहले';

  @override
  String monthsAgo(int count) {
    return '$count महीने पहले';
  }

  @override
  String get issuesCreatedInRepo => 'समस्याएं आपके डिफ़ॉल्ट रिपो में बनाई जाएंगी';

  @override
  String get taskIntegrations => 'कार्य एकीकरण';

  @override
  String get configureSettings => 'सेटिंग्स कॉन्फ़िगर करें';

  @override
  String get completeAuthBrowser => 'कृपया अपने ब्राउज़र में प्रमाणीकरण पूरा करें। हो जाने पर, ऐप पर वापस आएं।';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName प्रमाणीकरण शुरू करने में विफल';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appName से कनेक्ट करें';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'आपको अपने $appName खाते में कार्य बनाने के लिए Omi को अधिकृत करना होगा। यह प्रमाणीकरण के लिए आपका ब्राउज़र खोलेगा।';
  }

  @override
  String get continueButton => 'जारी रखें';

  @override
  String appIntegration(String appName) {
    return '$appName एकीकरण';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName एकीकरण जल्द आ रहा है!';
  }

  @override
  String get gotIt => 'समझ गया';

  @override
  String get tasksExportedOneApp => 'कार्यों को एक समय में केवल एक ऐप में निर्यात किया जा सकता है।';

  @override
  String get completeYourUpgrade => 'अपना अपग्रेड पूरा करें';

  @override
  String get importConfiguration => 'कॉन्फ़िगरेशन आयात करें';

  @override
  String get exportConfiguration => 'कॉन्फ़िगरेशन निर्यात करें';

  @override
  String get bringYourOwn => 'अपना खुद का लाएं';

  @override
  String get payYourSttProvider => 'Omi का मुफ्त उपयोग करें। आप केवल सीधे STT प्रदाता को भुगतान करते हैं।';

  @override
  String get freeMinutesMonth => '1,200 मुफ़्त मिनट/माह शामिल हैं।';

  @override
  String get omiUnlimited => 'Omi असीमित';

  @override
  String get hostRequired => 'होस्ट आवश्यक है';

  @override
  String get validPortRequired => 'मान्य पोर्ट आवश्यक है';

  @override
  String get validWebsocketUrlRequired => 'मान्य वेबसॉकेट URL आवश्यक है (wss://)';

  @override
  String get apiUrlRequired => 'API URL आवश्यक है';

  @override
  String get apiKeyRequired => 'API कुंजी आवश्यक है';

  @override
  String get invalidJsonConfig => 'अमान्य JSON कॉन्फ़िग';

  @override
  String errorSaving(String error) {
    return 'सहेजते समय त्रुटि: $error';
  }

  @override
  String get configCopiedToClipboard => 'कॉन्फ़िगरेशन क्लिपबोर्ड पर कॉपी किया गया';

  @override
  String get pasteJsonConfig => 'अपना JSON कॉन्फ़िग नीचे पेस्ट करें:';

  @override
  String get addApiKeyAfterImport => 'आयात करने के बाद आपको अपनी खुद की API कुंजी जोड़नी होगी';

  @override
  String get paste => 'पेस्ट';

  @override
  String get import => 'आयात';

  @override
  String get invalidProviderInConfig => 'कॉन्फ़िग में अमान्य प्रदाता';

  @override
  String importedConfig(String providerName) {
    return '$providerName कॉन्फ़िग आयात किया गया';
  }

  @override
  String invalidJson(String error) {
    return 'अमान्य JSON: $error';
  }

  @override
  String get provider => 'प्रदाता';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'ऑन-डिवाइस';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'अपना STT HTTP एंडपॉइंट दर्ज करें';

  @override
  String get websocketUrl => 'वेबसॉकेट URL';

  @override
  String get enterLiveSttWebsocket => 'अपना लाइव STT वेबसॉकेट एंडपॉइंट दर्ज करें';

  @override
  String get apiKey => 'API कुंजी';

  @override
  String get enterApiKey => 'अपनी API कुंजी दर्ज करें';

  @override
  String get storedLocallyNeverShared => 'स्थानीय रूप से संग्रहीत, कभी साझा नहीं किया गया';

  @override
  String get host => 'होस्ट';

  @override
  String get port => 'पोर्ट';

  @override
  String get advanced => 'उन्नत';

  @override
  String get configuration => 'कॉन्फ़िगरेशन';

  @override
  String get requestConfiguration => 'अनुरोध कॉन्फ़िगरेशन';

  @override
  String get responseSchema => 'प्रतिक्रिया स्कीमा';

  @override
  String get modified => 'संशोधित';

  @override
  String get resetRequestConfig => 'अनुरोध कॉन्फ़िगरेशन रीसेट करें';

  @override
  String get logs => 'लॉग';

  @override
  String get logsCopied => 'लॉग कॉपी किए गए';

  @override
  String get noLogsYet => 'अभी तक कोई लॉग नहीं। गतिविधि देखने के लिए रिकॉर्ड करें।';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device $reason का उपयोग करता है। Omi का उपयोग किया जाएगा।';
  }

  @override
  String get omiTranscription => 'Omi प्रतिलेखन';

  @override
  String get bestInClassTranscription => 'सर्वोत्तम श्रेणी का प्रतिलेखन';

  @override
  String get instantSpeakerLabels => 'तत्काल स्पीकर लेबल';

  @override
  String get languageTranslation => '100+ भाषा अनुवाद';

  @override
  String get optimizedForConversation => 'बातचीत के लिए अनुकूलित';

  @override
  String get autoLanguageDetection => 'स्वचालित भाषा पहचान';

  @override
  String get highAccuracy => 'उच्च सटीकता';

  @override
  String get privacyFirst => 'गोपनीयता पहले';

  @override
  String get saveChanges => 'परिवर्तन सहेजें';

  @override
  String get resetToDefault => 'डिफ़ॉल्ट पर रीसेट करें';

  @override
  String get viewTemplate => 'टेम्पलेट देखें';

  @override
  String get trySomethingLike => 'कुछ इस तरह आज़माएँ...';

  @override
  String get tryIt => 'इसे आज़माएं';

  @override
  String get creatingPlan => 'योजना बनाई जा रही है';

  @override
  String get developingLogic => 'तर्क विकसित किया जा रहा है';

  @override
  String get designingApp => 'ऐप डिज़ाइन किया जा रहा है';

  @override
  String get generatingIconStep => 'आइकन बनाया जा रहा है';

  @override
  String get finalTouches => 'अंतिम स्पर्श';

  @override
  String get processing => 'प्रक्रिया चल रही है...';

  @override
  String get features => 'विशेषताएं';

  @override
  String get creatingYourApp => 'आपका ऐप बनाया जा रहा है...';

  @override
  String get generatingIcon => 'आइकन बनाया जा रहा है...';

  @override
  String get whatShouldWeMake => 'हमें क्या बनाना चाहिए?';

  @override
  String get appName => 'ऐप का नाम';

  @override
  String get description => 'विवरण';

  @override
  String get publicLabel => 'सार्वजनिक';

  @override
  String get privateLabel => 'निजी';

  @override
  String get free => 'निःशुल्क';

  @override
  String get perMonth => '/ माह';

  @override
  String get tailoredConversationSummaries => 'अनुकूलित वार्तालाप सारांश';

  @override
  String get customChatbotPersonality => 'कस्टम चैटबॉट व्यक्तित्व';

  @override
  String get makePublic => 'सार्वजनिक बनाएं';

  @override
  String get anyoneCanDiscover => 'कोई भी आपका ऐप खोज सकता है';

  @override
  String get onlyYouCanUse => 'केवल आप इस ऐप का उपयोग कर सकते हैं';

  @override
  String get paidApp => 'सशुल्क ऐप';

  @override
  String get usersPayToUse => 'उपयोगकर्ता आपके ऐप का उपयोग करने के लिए भुगतान करते हैं';

  @override
  String get freeForEveryone => 'सभी के लिए मुफ़्त';

  @override
  String get perMonthLabel => '/ माह';

  @override
  String get creating => 'बना रहा है...';

  @override
  String get createApp => 'ऐप बनाएं';

  @override
  String get searchingForDevices => 'डिवाइस खोज रहा है...';

  @override
  String devicesFoundNearby(int count) {
    return '$count डिवाइस आस-पास मिले';
  }

  @override
  String get pairingSuccessful => 'पेयरिंग सफल';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch कनेक्ट करने में त्रुटि: $error';
  }

  @override
  String get dontShowAgain => 'फिर से न दिखाएं';

  @override
  String get iUnderstand => 'मैं समझता हूं';

  @override
  String get enableBluetooth => 'ब्लूटूथ सक्षम करें';

  @override
  String get bluetoothNeeded => 'आपके वियरेबल से कनेक्ट करने के लिए Omi को ब्लूटूथ की आवश्यकता है।';

  @override
  String get contactSupport => 'संपर्क करें?';

  @override
  String get connectLater => 'बाद में कनेक्ट करें';

  @override
  String get grantPermissions => 'अनुमतियां दें';

  @override
  String get backgroundActivity => 'बैकग्राउंड गतिविधि';

  @override
  String get backgroundActivityDesc => 'बेहतर स्थिरता के लिए Omi को बैकग्राउंड में चलने दें';

  @override
  String get locationAccess => 'स्थान पहुंच';

  @override
  String get locationAccessDesc => 'पूर्ण अनुभव के लिए बैकग्राउंड स्थान सक्षम करें';

  @override
  String get notifications => 'सूचनाएं';

  @override
  String get notificationsDesc => 'सूचित रहने के लिए सूचनाएं सक्षम करें';

  @override
  String get locationServiceDisabled => 'स्थान सेवा अक्षम है';

  @override
  String get locationServiceDisabledDesc => 'कृपया स्थान सेवा सक्षम करें';

  @override
  String get backgroundLocationDenied => 'बैकग्राउंड स्थान अस्वीकृत';

  @override
  String get backgroundLocationDeniedDesc => 'कृपया सेटिंग में \'हमेशा\' की अनुमति दें';

  @override
  String get lovingOmi => 'Omi पसंद आ रहा है?';

  @override
  String get leaveReviewIos => 'ऐप स्टोर पर समीक्षा छोड़ कर अधिक लोगों तक पहुँचने में हमारी मदद करें।';

  @override
  String get leaveReviewAndroid => 'Google Play पर समीक्षा छोड़ कर अधिक लोगों तक पहुँचने में हमारी मदद करें।';

  @override
  String get rateOnAppStore => 'ऐप स्टोर पर रेट करें';

  @override
  String get rateOnGooglePlay => 'Google Play पर रेट करें';

  @override
  String get maybeLater => 'शायद बाद में';

  @override
  String get speechProfileIntro => 'Omi को आपके लक्ष्यों और आपकी आवाज़ सीखनी होगी। आप इसे बाद में संशोधित कर सकते हैं।';

  @override
  String get getStarted => 'शुरू करें';

  @override
  String get allDone => 'सब हो गया!';

  @override
  String get keepGoing => 'जारी रखें';

  @override
  String get skipThisQuestion => 'इस प्रश्न को छोड़ें';

  @override
  String get skipForNow => 'अभी के लिए छोड़ें';

  @override
  String get connectionError => 'कनेक्शन त्रुटि';

  @override
  String get connectionErrorDesc => 'सर्वर से कनेक्ट करने में विफल।';

  @override
  String get invalidRecordingMultipleSpeakers => 'अमान्य रिकॉर्डिंग';

  @override
  String get multipleSpeakersDesc => 'ऐसा लगता है कि कई स्पीकर हैं।';

  @override
  String get tooShortDesc => 'पर्याप्त भाषण नहीं मिला।';

  @override
  String get invalidRecordingDesc => 'कृपया सुनिश्चित करें कि आप कम से कम 5 सेकंड बोलें।';

  @override
  String get areYouThere => 'क्या आप वहां हैं?';

  @override
  String get noSpeechDesc => 'हम भाषण का पता नहीं लगा सके।';

  @override
  String get connectionLost => 'कनेक्शन टूट गया';

  @override
  String get connectionLostDesc => 'कनेक्शन खो गया था।';

  @override
  String get tryAgain => 'पुनः प्रयास करें';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass कनेक्ट करें';

  @override
  String get continueWithoutDevice => 'डिवाइस के बिना जारी रखें';

  @override
  String get permissionsRequired => 'अनुमतियां आवश्यक';

  @override
  String get permissionsRequiredDesc => 'ब्लूटूथ और स्थान की अनुमति आवश्यक है।';

  @override
  String get openSettings => 'सेटिंग्स खोलें';

  @override
  String get wantDifferentName => 'क्या आप कोई दूसरा नाम इस्तेमाल करना चाहते हैं?';

  @override
  String get whatsYourName => 'आपका नाम क्या है?';

  @override
  String get speakTranscribeSummarize => 'बोलें। ट्रांसक्राइब करें। संक्षेप करें।';

  @override
  String get signInWithApple => 'Apple के साथ साइन इन करें';

  @override
  String get signInWithGoogle => 'Google के साथ साइन इन करें';

  @override
  String get byContinuingAgree => 'जारी रखकर, आप हमारी शर्तों से सहमत होते हैं ';

  @override
  String get termsOfUse => 'उपयोग की शर्तें';

  @override
  String get omiYourAiCompanion => 'Omi – आपका AI साथी';

  @override
  String get captureEveryMoment => 'हर पल को कैप्चर करें। AI सारांश प्राप्त करें।';

  @override
  String get appleWatchSetup => 'Apple Watch सेटअप';

  @override
  String get permissionRequestedExclaim => 'अनुमति मांगी गई!';

  @override
  String get microphonePermission => 'माइक्रोफ़ोन अनुमति';

  @override
  String get permissionGrantedNow => 'अनुमति अब दी गई!';

  @override
  String get needMicrophonePermission => 'हमें माइक्रोफोन अनुमति की आवश्यकता है।';

  @override
  String get grantPermissionButton => 'अनुमति दें';

  @override
  String get needHelp => 'मदद चाहिए?';

  @override
  String get troubleshootingSteps => 'समस्या निवारण चरण...';

  @override
  String get recordingStartedSuccessfully => 'रिकॉर्डिंग सफलतापूर्वक शुरू हुई!';

  @override
  String get permissionNotGrantedYet => 'अनुमति अभी तक नहीं दी गई।';

  @override
  String errorRequestingPermission(String error) {
    return 'अनुमति मांगते समय त्रुटि: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'रिकॉर्डिंग शुरू करते समय त्रुटि: $error';
  }

  @override
  String get selectPrimaryLanguage => 'अपनी प्राथमिक भाषा चुनें';

  @override
  String get languageBenefits => 'स्पष्ट प्रतिलेखन के लिए अपनी भाषा निर्धारित करें';

  @override
  String get whatsYourPrimaryLanguage => 'आपकी प्राथमिक भाषा क्या है?';

  @override
  String get selectYourLanguage => 'अपनी भाषा चुनें';

  @override
  String get personalGrowthJourney => 'आपकी व्यक्तिगत विकास यात्रा AI के साथ जो आपके हर शब्द को सुनता है।';

  @override
  String get actionItemsTitle => 'कार्य';

  @override
  String get actionItemsDescription =>
      'संपादित करने के लिए टैप करें • चुनने के लिए होल्ड करें • कार्रवाई के लिए स्वाइप करें';

  @override
  String get tabToDo => 'करने के लिए';

  @override
  String get tabDone => 'पूर्ण';

  @override
  String get tabOld => 'पुराना';

  @override
  String get emptyTodoMessage => '🎉 सब हो गया!\nकोई लंबित कार्य नहीं';

  @override
  String get emptyDoneMessage => 'अभी तक कोई पूर्ण आइटम नहीं';

  @override
  String get emptyOldMessage => '✅ कोई पुराने कार्य नहीं';

  @override
  String get noItems => 'कोई आइटम नहीं';

  @override
  String get actionItemMarkedIncomplete => 'अपूर्ण चिह्नित';

  @override
  String get actionItemCompleted => 'कार्य पूर्ण';

  @override
  String get deleteActionItemTitle => 'कार्य आइटम हटाएं';

  @override
  String get deleteActionItemMessage => 'क्या आप वाकई इस कार्य आइटम को हटाना चाहते हैं?';

  @override
  String get deleteSelectedItemsTitle => 'चयनित हटाएं';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'क्या आप वाकई $count चयनित कार्यों को हटाना चाहते हैं?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'कार्य \"$description\" हटाया गया';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count कार्य हटाए गए';
  }

  @override
  String get failedToDeleteItem => 'आइटम हटाने में विफल';

  @override
  String get failedToDeleteItems => 'आइटम हटाने में विफल';

  @override
  String get failedToDeleteSomeItems => 'कुछ आइटम हटाने में विफल';

  @override
  String get welcomeActionItemsTitle => 'कार्रवाई के लिए तैयार';

  @override
  String get welcomeActionItemsDescription => 'आपका AI स्वचालित रूप से कार्य निकालता है।';

  @override
  String get autoExtractionFeature => 'बातचीत से स्वचालित रूप से निकाला गया';

  @override
  String get editSwipeFeature => 'टैप करें, स्वाइप करें, प्रबंधित करें';

  @override
  String itemsSelected(int count) {
    return '$count चयनित';
  }

  @override
  String get selectAll => 'सभी चुनें';

  @override
  String get deleteSelected => 'चयनित हटाएं';

  @override
  String get searchMemories => 'यादें खोजें...';

  @override
  String get memoryDeleted => 'याद हटा दी गई।';

  @override
  String get undo => 'पूर्ववत करें';

  @override
  String get noMemoriesYet => '🧠 अभी कोई यादें नहीं';

  @override
  String get noAutoMemories => 'कोई स्वतः यादें नहीं';

  @override
  String get noManualMemories => 'कोई मैनुअल यादें नहीं';

  @override
  String get noMemoriesInCategories => 'इन श्रेणियों में कोई यादें नहीं';

  @override
  String get noMemoriesFound => '🔍 कोई यादें नहीं मिलीं';

  @override
  String get addFirstMemory => 'अपनी पहली याद जोड़ें';

  @override
  String get clearMemoryTitle => 'Omi मेमोरी साफ़ करें?';

  @override
  String get clearMemoryMessage => 'क्या आप वाकई Omi मेमोरी साफ़ करना चाहते हैं? यह पूर्ववत नहीं किया जा सकता।';

  @override
  String get clearMemoryButton => 'स्मृति साफ़ करें';

  @override
  String get memoryClearedSuccess => 'मेमोरी साफ़ हो गई';

  @override
  String get noMemoriesToDelete => 'हटाने के लिए कोई यादें नहीं';

  @override
  String get createMemoryTooltip => 'नई याद बनाएं';

  @override
  String get createActionItemTooltip => 'नया कार्य बनाएं';

  @override
  String get memoryManagement => 'स्मृति प्रबंधन';

  @override
  String get filterMemories => 'यादें फ़िल्टर करें';

  @override
  String totalMemoriesCount(int count) {
    return 'आपके पास $count यादें हैं';
  }

  @override
  String get publicMemories => 'सार्वजनिक यादें';

  @override
  String get privateMemories => 'निजी यादें';

  @override
  String get makeAllPrivate => 'सभी निजी बनाएं';

  @override
  String get makeAllPublic => 'सभी सार्वजनिक बनाएं';

  @override
  String get deleteAllMemories => 'सभी यादें हटाएं';

  @override
  String get allMemoriesPrivateResult => 'सभी यादें अब निजी हैं';

  @override
  String get allMemoriesPublicResult => 'सभी यादें अब सार्वजनिक हैं';

  @override
  String get newMemory => '✨ नई स्मृति';

  @override
  String get editMemory => '✏️ स्मृति संपादित करें';

  @override
  String get memoryContentHint => 'मुझे आइसक्रीम पसंद है...';

  @override
  String get failedToSaveMemory => 'सहेजने में विफल।';

  @override
  String get saveMemory => 'याद सहेजें';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'कार्य आइटम बनाएं';

  @override
  String get editActionItem => 'कार्य आइटम संपादित करें';

  @override
  String get actionItemDescriptionHint => 'क्या करने की आवश्यकता है?';

  @override
  String get actionItemDescriptionEmpty => 'विवरण खाली नहीं हो सकता।';

  @override
  String get actionItemUpdated => 'कार्य अपडेट किया गया';

  @override
  String get failedToUpdateActionItem => 'कार्य आइटम अपडेट करने में विफल';

  @override
  String get actionItemCreated => 'कार्य बनाया गया';

  @override
  String get failedToCreateActionItem => 'कार्य आइटम बनाने में विफल';

  @override
  String get dueDate => 'नियत तारीख';

  @override
  String get time => 'समय';

  @override
  String get addDueDate => 'नियत तारीख जोड़ें';

  @override
  String get pressDoneToSave => 'सहेजने के लिए पूर्ण दबाएं';

  @override
  String get pressDoneToCreate => 'बनाने के लिए पूर्ण दबाएं';

  @override
  String get filterAll => 'सभी';

  @override
  String get filterSystem => 'आपके बारे में';

  @override
  String get filterInteresting => 'अंतर्दृष्टि';

  @override
  String get filterManual => 'मैनुअल';

  @override
  String get completed => 'पूर्ण';

  @override
  String get markComplete => 'पूर्ण के रूप में चिह्नित करें';

  @override
  String get actionItemDeleted => 'कार्य आइटम हटाया गया';

  @override
  String get failedToDeleteActionItem => 'कार्य आइटम हटाने में विफल';

  @override
  String get deleteActionItemConfirmTitle => 'कार्य हटाएं';

  @override
  String get deleteActionItemConfirmMessage => 'क्या आप वाकई इस कार्य को हटाना चाहते हैं?';

  @override
  String get appLanguage => 'ऐप भाषा';

  @override
  String get appInterfaceSectionTitle => 'ऐप इंटरफ़ेस';

  @override
  String get speechTranscriptionSectionTitle => 'वाणी और ट्रांसक्रिप्शन';

  @override
  String get languageSettingsHelperText =>
      'ऐप भाषा मेनू और बटन बदलती है। वाणी भाषा आपकी रिकॉर्डिंग के ट्रांसक्रिप्शन को प्रभावित करती है।';

  @override
  String get translationNotice => 'अनुवाद सूचना';

  @override
  String get translationNoticeMessage =>
      'Omi बातचीत को आपकी मुख्य भाषा में अनुवाद करता है। इसे सेटिंग्स → प्रोफाइल में कभी भी अपडेट करें।';

  @override
  String get pleaseCheckInternetConnection => 'कृपया अपना इंटरनेट कनेक्शन जांचें और पुनः प्रयास करें';

  @override
  String get pleaseSelectReason => 'कृपया एक कारण चुनें';

  @override
  String get tellUsMoreWhatWentWrong => 'हमें बताएं कि क्या गलत हुआ...';

  @override
  String get selectText => 'टेक्स्ट चुनें';

  @override
  String maximumGoalsAllowed(int count) {
    return 'अधिकतम $count लक्ष्य अनुमत';
  }

  @override
  String get conversationCannotBeMerged => 'यह बातचीत मर्ज नहीं की जा सकती (लॉक या पहले से मर्ज हो रही है)';

  @override
  String get pleaseEnterFolderName => 'कृपया एक फ़ोल्डर नाम दर्ज करें';

  @override
  String get failedToCreateFolder => 'फ़ोल्डर बनाने में विफल';

  @override
  String get failedToUpdateFolder => 'फ़ोल्डर अपडेट करने में विफल';

  @override
  String get folderName => 'फ़ोल्डर नाम';

  @override
  String get descriptionOptional => 'विवरण (वैकल्पिक)';

  @override
  String get failedToDeleteFolder => 'फ़ोल्डर हटाने में विफल';

  @override
  String get editFolder => 'फ़ोल्डर संपादित करें';

  @override
  String get deleteFolder => 'फ़ोल्डर हटाएं';

  @override
  String get transcriptCopiedToClipboard => 'ट्रांसक्रिप्ट क्लिपबोर्ड पर कॉपी किया गया';

  @override
  String get summaryCopiedToClipboard => 'सारांश क्लिपबोर्ड पर कॉपी किया गया';

  @override
  String get conversationUrlCouldNotBeShared => 'बातचीत URL साझा नहीं किया जा सका।';

  @override
  String get urlCopiedToClipboard => 'URL क्लिपबोर्ड पर कॉपी किया गया';

  @override
  String get exportTranscript => 'ट्रांसक्रिप्ट निर्यात करें';

  @override
  String get exportSummary => 'सारांश निर्यात करें';

  @override
  String get exportButton => 'निर्यात करें';

  @override
  String get actionItemsCopiedToClipboard => 'कार्रवाई आइटम क्लिपबोर्ड पर कॉपी किए गए';

  @override
  String get summarize => 'सारांश';

  @override
  String get generateSummary => 'सारांश बनाएं';

  @override
  String get conversationNotFoundOrDeleted => 'बातचीत नहीं मिली या हटा दी गई है';

  @override
  String get deleteMemory => 'स्मृति हटाएं';

  @override
  String get thisActionCannotBeUndone => 'इस क्रिया को पूर्ववत नहीं किया जा सकता।';

  @override
  String memoriesCount(int count) {
    return '$count यादें';
  }

  @override
  String get noMemoriesInCategory => 'इस श्रेणी में अभी तक कोई यादें नहीं हैं';

  @override
  String get addYourFirstMemory => 'अपनी पहली याद जोड़ें';

  @override
  String get firmwareDisconnectUsb => 'USB डिस्कनेक्ट करें';

  @override
  String get firmwareUsbWarning => 'अपडेट के दौरान USB कनेक्शन आपके डिवाइस को नुकसान पहुंचा सकता है।';

  @override
  String get firmwareBatteryAbove15 => 'बैटरी 15% से अधिक';

  @override
  String get firmwareEnsureBattery => 'सुनिश्चित करें कि आपके डिवाइस में 15% बैटरी है।';

  @override
  String get firmwareStableConnection => 'स्थिर कनेक्शन';

  @override
  String get firmwareConnectWifi => 'WiFi या सेलुलर से कनेक्ट करें।';

  @override
  String failedToStartUpdate(String error) {
    return 'अपडेट शुरू करने में विफल: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'अपडेट से पहले, सुनिश्चित करें:';

  @override
  String get confirmed => 'पुष्टि की गई!';

  @override
  String get release => 'छोड़ें';

  @override
  String get slideToUpdate => 'अपडेट के लिए स्लाइड करें';

  @override
  String copiedToClipboard(String title) {
    return '$title क्लिपबोर्ड में कॉपी किया गया';
  }

  @override
  String get batteryLevel => 'बैटरी स्तर';

  @override
  String get productUpdate => 'उत्पाद अपडेट';

  @override
  String get offline => 'ऑफ़लाइन';

  @override
  String get available => 'उपलब्ध';

  @override
  String get unpairDeviceDialogTitle => 'डिवाइस को अनपेयर करें';

  @override
  String get unpairDeviceDialogMessage =>
      'यह डिवाइस को अनपेयर कर देगा ताकि इसे किसी अन्य फोन से कनेक्ट किया जा सके। प्रक्रिया पूरी करने के लिए आपको सेटिंग्स > ब्लूटूथ पर जाना होगा और डिवाइस को भूलना होगा।';

  @override
  String get unpair => 'अनपेयर करें';

  @override
  String get unpairAndForgetDevice => 'अनपेयर करें और डिवाइस भूल जाएं';

  @override
  String get unknownDevice => 'Unknown';

  @override
  String get unknown => 'अज्ञात';

  @override
  String get productName => 'उत्पाद का नाम';

  @override
  String get serialNumber => 'क्रम संख्या';

  @override
  String get connected => 'कनेक्ट किया गया';

  @override
  String get privacyPolicyTitle => 'गोपनीयता नीति';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label कॉपी किया गया';
  }

  @override
  String get noApiKeysYet => 'अभी तक कोई API कुंजी नहीं है। अपने ऐप के साथ एकीकृत करने के लिए एक बनाएं।';

  @override
  String get createKeyToGetStarted => 'शुरू करने के लिए एक कुंजी बनाएं';

  @override
  String get persona => 'व्यक्तित्व';

  @override
  String get configureYourAiPersona => 'अपना AI व्यक्तित्व कॉन्फ़िगर करें';

  @override
  String get configureSttProvider => 'STT प्रदाता कॉन्फ़िगर करें';

  @override
  String get setWhenConversationsAutoEnd => 'सेट करें कि बातचीत कब स्वचालित रूप से समाप्त हो';

  @override
  String get importDataFromOtherSources => 'अन्य स्रोतों से डेटा आयात करें';

  @override
  String get debugAndDiagnostics => 'डीबग और डायग्नोस्टिक्स';

  @override
  String get autoDeletesAfter3Days => '3 दिनों के बाद स्वतः हट जाता है';

  @override
  String get helpsDiagnoseIssues => 'समस्याओं का निदान करने में मदद करता है';

  @override
  String get exportStartedMessage => 'निर्यात शुरू हो गया। इसमें कुछ सेकंड लग सकते हैं...';

  @override
  String get exportConversationsToJson => 'बातचीत को JSON फ़ाइल में निर्यात करें';

  @override
  String get knowledgeGraphDeletedSuccess => 'ज्ञान ग्राफ सफलतापूर्वक हटा दिया गया';

  @override
  String failedToDeleteGraph(String error) {
    return 'ग्राफ हटाने में विफल: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'सभी नोड्स और कनेक्शन साफ़ करें';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.json में जोड़ें';

  @override
  String get connectAiAssistantsToData => 'AI सहायकों को अपने डेटा से कनेक्ट करें';

  @override
  String get useYourMcpApiKey => 'अपनी MCP API कुंजी का उपयोग करें';

  @override
  String get realTimeTranscript => 'रीयल-टाइम ट्रांसक्रिप्ट';

  @override
  String get experimental => 'प्रायोगिक';

  @override
  String get transcriptionDiagnostics => 'ट्रांसक्रिप्शन डायग्नोस्टिक्स';

  @override
  String get detailedDiagnosticMessages => 'विस्तृत नैदानिक संदेश';

  @override
  String get autoCreateSpeakers => 'स्पीकर स्वतः बनाएं';

  @override
  String get autoCreateWhenNameDetected => 'नाम पता चलने पर स्वचालित रूप से बनाएं';

  @override
  String get followUpQuestions => 'फॉलो-अप प्रश्न';

  @override
  String get suggestQuestionsAfterConversations => 'बातचीत के बाद प्रश्न सुझाएं';

  @override
  String get goalTracker => 'लक्ष्य ट्रैकर';

  @override
  String get trackPersonalGoalsOnHomepage => 'होमपेज पर अपने व्यक्तिगत लक्ष्यों को ट्रैक करें';

  @override
  String get dailyReflection => 'दैनिक चिंतन';

  @override
  String get get9PmReminderToReflect => 'अपने दिन पर विचार करने के लिए रात 9 बजे रिमाइंडर प्राप्त करें';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'कार्य आइटम विवरण खाली नहीं हो सकता';

  @override
  String get saved => 'सहेजा गया';

  @override
  String get overdue => 'विलंबित';

  @override
  String get failedToUpdateDueDate => 'नियत तिथि अपडेट करने में विफल';

  @override
  String get markIncomplete => 'अपूर्ण के रूप में चिह्नित करें';

  @override
  String get editDueDate => 'नियत तिथि संपादित करें';

  @override
  String get setDueDate => 'नियत तारीख सेट करें';

  @override
  String get clearDueDate => 'नियत तिथि साफ़ करें';

  @override
  String get failedToClearDueDate => 'नियत तिथि साफ़ करने में विफल';

  @override
  String get mondayAbbr => 'सोम';

  @override
  String get tuesdayAbbr => 'मंगल';

  @override
  String get wednesdayAbbr => 'बुध';

  @override
  String get thursdayAbbr => 'गुरु';

  @override
  String get fridayAbbr => 'शुक्र';

  @override
  String get saturdayAbbr => 'शनि';

  @override
  String get sundayAbbr => 'रवि';

  @override
  String get howDoesItWork => 'यह कैसे काम करता है?';

  @override
  String get sdCardSyncDescription => 'SD कार्ड सिंक आपकी यादों को SD कार्ड से ऐप में आयात करेगा';

  @override
  String get checksForAudioFiles => 'SD कार्ड पर ऑडियो फाइलों की जांच करता है';

  @override
  String get omiSyncsAudioFiles => 'Omi फिर ऑडियो फाइलों को सर्वर के साथ सिंक करता है';

  @override
  String get serverProcessesAudio => 'सर्वर ऑडियो फाइलों को प्रोसेस करता है और यादें बनाता है';

  @override
  String get youreAllSet => 'आप तैयार हैं!';

  @override
  String get welcomeToOmiDescription =>
      'Omi में आपका स्वागत है! आपका AI साथी बातचीत, कार्यों और अधिक में आपकी सहायता के लिए तैयार है।';

  @override
  String get startUsingOmi => 'Omi उपयोग शुरू करें';

  @override
  String get back => 'पीछे';

  @override
  String get keyboardShortcuts => 'कीबोर्ड शॉर्टकट';

  @override
  String get toggleControlBar => 'नियंत्रण पट्टी टॉगल करें';

  @override
  String get pressKeys => 'कुंजियाँ दबाएं...';

  @override
  String get cmdRequired => '⌘ आवश्यक';

  @override
  String get invalidKey => 'अमान्य कुंजी';

  @override
  String get space => 'स्पेस';

  @override
  String get search => 'खोजें';

  @override
  String get searchPlaceholder => 'खोजें...';

  @override
  String get untitledConversation => 'शीर्षक रहित बातचीत';

  @override
  String countRemaining(String count) {
    return '$count शेष';
  }

  @override
  String get addGoal => 'लक्ष्य जोड़ें';

  @override
  String get editGoal => 'लक्ष्य संपादित करें';

  @override
  String get icon => 'आइकन';

  @override
  String get goalTitle => 'लक्ष्य शीर्षक';

  @override
  String get current => 'वर्तमान';

  @override
  String get target => 'लक्ष्य';

  @override
  String get saveGoal => 'सहेजें';

  @override
  String get goals => 'लक्ष्य';

  @override
  String get tapToAddGoal => 'लक्ष्य जोड़ने के लिए टैप करें';

  @override
  String welcomeBack(String name) {
    return 'वापसी पर स्वागत है, $name';
  }

  @override
  String get yourConversations => 'आपकी बातचीत';

  @override
  String get reviewAndManageConversations => 'अपनी रिकॉर्ड की गई बातचीत की समीक्षा करें और प्रबंधित करें';

  @override
  String get startCapturingConversations => 'उन्हें यहां देखने के लिए अपने Omi डिवाइस से बातचीत कैप्चर करना शुरू करें।';

  @override
  String get useMobileAppToCapture => 'ऑडियो कैप्चर करने के लिए अपने मोबाइल ऐप का उपयोग करें';

  @override
  String get conversationsProcessedAutomatically => 'बातचीत स्वचालित रूप से प्रोसेस की जाती है';

  @override
  String get getInsightsInstantly => 'तुरंत जानकारी और सारांश प्राप्त करें';

  @override
  String get showAll => 'सभी दिखाएं →';

  @override
  String get noTasksForToday =>
      'आज के लिए कोई कार्य नहीं।\\nअधिक कार्यों के लिए Omi से पूछें या मैन्युअल रूप से बनाएं।';

  @override
  String get dailyScore => 'दैनिक स्कोर';

  @override
  String get dailyScoreDescription =>
      'एक स्कोर जो आपको बेहतर तरीके से\nनिष्पादन पर ध्यान केंद्रित करने में मदद करता है।';

  @override
  String get searchResults => 'खोज परिणाम';

  @override
  String get actionItems => 'कार्य आइटम';

  @override
  String get tasksToday => 'आज';

  @override
  String get tasksTomorrow => 'कल';

  @override
  String get tasksNoDeadline => 'कोई समय सीमा नहीं';

  @override
  String get tasksLater => 'बाद में';

  @override
  String get loadingTasks => 'कार्य लोड हो रहे हैं...';

  @override
  String get tasks => 'कार्य';

  @override
  String get swipeTasksToIndent => 'इंडेंट करने के लिए कार्यों को स्वाइप करें, श्रेणियों के बीच खींचें';

  @override
  String get create => 'बनाएं';

  @override
  String get noTasksYet => 'अभी तक कोई कार्य नहीं';

  @override
  String get tasksFromConversationsWillAppear =>
      'आपकी बातचीत से कार्य यहां दिखाई देंगे।\nमैन्युअल रूप से एक जोड़ने के लिए बनाएं पर क्लिक करें।';

  @override
  String get monthJan => 'जन';

  @override
  String get monthFeb => 'फ़र';

  @override
  String get monthMar => 'मार्च';

  @override
  String get monthApr => 'अप्रै';

  @override
  String get monthMay => 'मई';

  @override
  String get monthJun => 'जून';

  @override
  String get monthJul => 'जुल';

  @override
  String get monthAug => 'अग';

  @override
  String get monthSep => 'सित';

  @override
  String get monthOct => 'अक्टू';

  @override
  String get monthNov => 'नव';

  @override
  String get monthDec => 'दिस';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'कार्य आइटम सफलतापूर्वक अपडेट किया गया';

  @override
  String get actionItemCreatedSuccessfully => 'कार्य आइटम सफलतापूर्वक बनाया गया';

  @override
  String get actionItemDeletedSuccessfully => 'कार्य आइटम सफलतापूर्वक हटाया गया';

  @override
  String get deleteActionItem => 'कार्य आइटम हटाएं';

  @override
  String get deleteActionItemConfirmation =>
      'क्या आप वाकई इस कार्य आइटम को हटाना चाहते हैं? इस क्रिया को पूर्ववत नहीं किया जा सकता।';

  @override
  String get enterActionItemDescription => 'कार्य आइटम विवरण दर्ज करें...';

  @override
  String get markAsCompleted => 'पूर्ण के रूप में चिह्नित करें';

  @override
  String get setDueDateAndTime => 'नियत तारीख और समय सेट करें';

  @override
  String get reloadingApps => 'ऐप्स फिर से लोड हो रहे हैं...';

  @override
  String get loadingApps => 'ऐप्स लोड हो रहे हैं...';

  @override
  String get browseInstallCreateApps => 'ऐप्स ब्राउज़, इंस्टॉल और बनाएं';

  @override
  String get all => 'All';

  @override
  String get open => 'खोलें';

  @override
  String get install => 'इंस्टॉल करें';

  @override
  String get noAppsAvailable => 'कोई ऐप उपलब्ध नहीं';

  @override
  String get unableToLoadApps => 'ऐप्स लोड करने में असमर्थ';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'अपनी खोज शर्तों या फ़िल्टर को समायोजित करने का प्रयास करें';

  @override
  String get checkBackLaterForNewApps => 'नए ऐप्स के लिए बाद में जांचें';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'कृपया अपना इंटरनेट कनेक्शन जांचें और फिर से प्रयास करें';

  @override
  String get createNewApp => 'नया ऐप बनाएं';

  @override
  String get buildSubmitCustomOmiApp => 'अपना कस्टम Omi ऐप बनाएं और सबमिट करें';

  @override
  String get submittingYourApp => 'आपका ऐप सबमिट किया जा रहा है...';

  @override
  String get preparingFormForYou => 'आपके लिए फॉर्म तैयार किया जा रहा है...';

  @override
  String get appDetails => 'ऐप विवरण';

  @override
  String get paymentDetails => 'भुगतान विवरण';

  @override
  String get previewAndScreenshots => 'पूर्वावलोकन और स्क्रीनशॉट';

  @override
  String get appCapabilities => 'ऐप क्षमताएं';

  @override
  String get aiPrompts => 'AI संकेत';

  @override
  String get chatPrompt => 'चैट संकेत';

  @override
  String get chatPromptPlaceholder =>
      'आप एक शानदार ऐप हैं, आपका काम उपयोगकर्ता के प्रश्नों का उत्तर देना और उन्हें अच्छा महसूस कराना है...';

  @override
  String get conversationPrompt => 'बातचीत प्रॉम्प्ट';

  @override
  String get conversationPromptPlaceholder => 'आप एक शानदार ऐप हैं, आपको बातचीत का प्रतिलेख और सारांश दिया जाएगा...';

  @override
  String get notificationScopes => 'सूचना श्रेणियां';

  @override
  String get appPrivacyAndTerms => 'ऐप गोपनीयता और शर्तें';

  @override
  String get makeMyAppPublic => 'मेरे ऐप को सार्वजनिक बनाएं';

  @override
  String get submitAppTermsAgreement =>
      'इस ऐप को सबमिट करके, मैं Omi AI की सेवा की शर्तों और गोपनीयता नीति से सहमत हूं';

  @override
  String get submitApp => 'ऐप सबमिट करें';

  @override
  String get needHelpGettingStarted => 'शुरू करने में मदद चाहिए?';

  @override
  String get clickHereForAppBuildingGuides => 'ऐप निर्माण गाइड और दस्तावेज़ीकरण के लिए यहां क्लिक करें';

  @override
  String get submitAppQuestion => 'ऐप सबमिट करें?';

  @override
  String get submitAppPublicDescription =>
      'आपके ऐप की समीक्षा की जाएगी और इसे सार्वजनिक किया जाएगा। आप इसे तुरंत उपयोग करना शुरू कर सकते हैं, यहां तक कि समीक्षा के दौरान भी!';

  @override
  String get submitAppPrivateDescription =>
      'आपके ऐप की समीक्षा की जाएगी और इसे आपके लिए निजी तौर पर उपलब्ध कराया जाएगा। आप इसे तुरंत उपयोग करना शुरू कर सकते हैं, यहां तक कि समीक्षा के दौरान भी!';

  @override
  String get startEarning => 'कमाई शुरू करें! 💰';

  @override
  String get connectStripeOrPayPal => 'अपने ऐप के लिए भुगतान प्राप्त करने के लिए Stripe या PayPal कनेक्ट करें।';

  @override
  String get connectNow => 'अभी कनेक्ट करें';

  @override
  String get installsCount => 'इंस्टॉल';

  @override
  String get uninstallApp => 'ऐप अनइंस्टॉल करें';

  @override
  String get subscribe => 'सदस्यता लें';

  @override
  String get dataAccessNotice => 'डेटा एक्सेस सूचना';

  @override
  String get dataAccessWarning =>
      'यह ऐप आपके डेटा तक पहुंच बनाएगा। Omi AI इस बात के लिए जिम्मेदार नहीं है कि इस ऐप द्वारा आपके डेटा का उपयोग, संशोधन या हटाया कैसे जाता है';

  @override
  String get installApp => 'ऐप इंस्टॉल करें';

  @override
  String get betaTesterNotice =>
      'आप इस ऐप के लिए बीटा परीक्षक हैं। यह अभी तक सार्वजनिक नहीं है। स्वीकृत होने के बाद यह सार्वजनिक हो जाएगा।';

  @override
  String get appUnderReviewOwner =>
      'आपका ऐप समीक्षाधीन है और केवल आपके लिए दृश्यमान है। स्वीकृत होने के बाद यह सार्वजनिक हो जाएगा।';

  @override
  String get appRejectedNotice =>
      'आपका ऐप अस्वीकार कर दिया गया है। कृपया ऐप विवरण अपडेट करें और समीक्षा के लिए पुनः सबमिट करें।';

  @override
  String get setupSteps => 'सेटअप चरण';

  @override
  String get setupInstructions => 'सेटअप निर्देश';

  @override
  String get integrationInstructions => 'एकीकरण निर्देश';

  @override
  String get preview => 'पूर्वावलोकन';

  @override
  String get aboutTheApp => 'ऐप के बारे में';

  @override
  String get aboutThePersona => 'पर्सोना के बारे में';

  @override
  String get chatPersonality => 'चैट व्यक्तित्व';

  @override
  String get ratingsAndReviews => 'रेटिंग और समीक्षाएं';

  @override
  String get noRatings => 'कोई रेटिंग नहीं';

  @override
  String ratingsCount(String count) {
    return '$count+ रेटिंग';
  }

  @override
  String get errorActivatingApp => 'ऐप सक्रिय करने में त्रुटि';

  @override
  String get integrationSetupRequired => 'यदि यह एक एकीकरण ऐप है, तो सुनिश्चित करें कि सेटअप पूर्ण हो गया है।';

  @override
  String get installed => 'इंस्टॉल';

  @override
  String get appIdLabel => 'ऐप ID';

  @override
  String get appNameLabel => 'ऐप का नाम';

  @override
  String get appNamePlaceholder => 'मेरा शानदार ऐप';

  @override
  String get pleaseEnterAppName => 'कृपया ऐप का नाम दर्ज करें';

  @override
  String get categoryLabel => 'श्रेणी';

  @override
  String get selectCategory => 'श्रेणी चुनें';

  @override
  String get descriptionLabel => 'विवरण';

  @override
  String get appDescriptionPlaceholder => 'मेरा शानदार ऐप एक बेहतरीन ऐप है जो अद्भुत काम करता है। यह सबसे अच्छा ऐप है!';

  @override
  String get pleaseProvideValidDescription => 'कृपया एक मान्य विवरण प्रदान करें';

  @override
  String get appPricingLabel => 'ऐप मूल्य निर्धारण';

  @override
  String get noneSelected => 'कुछ नहीं चुना गया';

  @override
  String get appIdCopiedToClipboard => 'ऐप ID क्लिपबोर्ड पर कॉपी की गई';

  @override
  String get appCategoryModalTitle => 'ऐप श्रेणी';

  @override
  String get pricingFree => 'मुफ़्त';

  @override
  String get pricingPaid => 'सशुल्क';

  @override
  String get loadingCapabilities => 'क्षमताएं लोड हो रही हैं...';

  @override
  String get filterInstalled => 'इंस्टॉल किया गया';

  @override
  String get filterMyApps => 'मेरे ऐप्स';

  @override
  String get clearSelection => 'चयन साफ़ करें';

  @override
  String get filterCategory => 'श्रेणी';

  @override
  String get rating4PlusStars => '4+ सितारे';

  @override
  String get rating3PlusStars => '3+ सितारे';

  @override
  String get rating2PlusStars => '2+ सितारे';

  @override
  String get rating1PlusStars => '1+ सितारा';

  @override
  String get filterRating => 'रेटिंग';

  @override
  String get filterCapabilities => 'क्षमताएं';

  @override
  String get noNotificationScopesAvailable => 'कोई सूचना स्कोप उपलब्ध नहीं हैं';

  @override
  String get popularApps => 'लोकप्रिय ऐप्स';

  @override
  String get pleaseProvidePrompt => 'कृपया एक प्रॉम्प्ट प्रदान करें';

  @override
  String chatWithAppName(String appName) {
    return '$appName के साथ चैट';
  }

  @override
  String get defaultAiAssistant => 'डिफ़ॉल्ट AI सहायक';

  @override
  String get readyToChat => '✨ चैट के लिए तैयार!';

  @override
  String get connectionNeeded => '🌐 कनेक्शन की आवश्यकता है';

  @override
  String get startConversation => 'बातचीत शुरू करें और जादू शुरू होने दें';

  @override
  String get checkInternetConnection => 'कृपया अपना इंटरनेट कनेक्शन जांचें';

  @override
  String get wasThisHelpful => 'क्या यह सहायक था?';

  @override
  String get thankYouForFeedback => 'आपकी प्रतिक्रिया के लिए धन्यवाद!';

  @override
  String get maxFilesUploadError => 'आप एक बार में केवल 4 फ़ाइलें अपलोड कर सकते हैं';

  @override
  String get attachedFiles => '📎 संलग्न फ़ाइलें';

  @override
  String get takePhoto => 'फोटो लें';

  @override
  String get captureWithCamera => 'कैमरे से कैप्चर करें';

  @override
  String get selectImages => 'छवियाँ चुनें';

  @override
  String get chooseFromGallery => 'गैलरी से चुनें';

  @override
  String get selectFile => 'एक फ़ाइल चुनें';

  @override
  String get chooseAnyFileType => 'कोई भी फ़ाइल प्रकार चुनें';

  @override
  String get cannotReportOwnMessages => 'आप अपने स्वयं के संदेश रिपोर्ट नहीं कर सकते';

  @override
  String get messageReportedSuccessfully => '✅ संदेश सफलतापूर्वक रिपोर्ट किया गया';

  @override
  String get confirmReportMessage => 'क्या आप निश्चित रूप से इस संदेश की रिपोर्ट करना चाहते हैं?';

  @override
  String get selectChatAssistant => 'चैट सहायक चुनें';

  @override
  String get enableMoreApps => 'अधिक ऐप्स सक्षम करें';

  @override
  String get chatCleared => 'चैट साफ़ की गई';

  @override
  String get clearChatTitle => 'चैट साफ़ करें?';

  @override
  String get confirmClearChat =>
      'क्या आप निश्चित रूप से चैट साफ़ करना चाहते हैं? इस क्रिया को पूर्ववत नहीं किया जा सकता।';

  @override
  String get copy => 'कॉपी करें';

  @override
  String get share => 'शेयर करें';

  @override
  String get report => 'रिपोर्ट करें';

  @override
  String get microphonePermissionRequired => 'वॉयस रिकॉर्डिंग के लिए माइक्रोफ़ोन अनुमति आवश्यक है।';

  @override
  String get microphonePermissionDenied =>
      'माइक्रोफ़ोन अनुमति अस्वीकार। कृपया सिस्टम प्राथमिकताएं > गोपनीयता और सुरक्षा > माइक्रोफ़ोन में अनुमति दें।';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'माइक्रोफ़ोन अनुमति जांचने में विफल: $error';
  }

  @override
  String get failedToTranscribeAudio => 'ऑडियो ट्रांसक्राइब करने में विफल';

  @override
  String get transcribing => 'ट्रांसक्राइब कर रहा है...';

  @override
  String get transcriptionFailed => 'ट्रांसक्रिप्शन विफल';

  @override
  String get discardedConversation => 'रद्द की गई बातचीत';

  @override
  String get at => 'पर';

  @override
  String get from => 'से';

  @override
  String get copied => 'कॉपी किया गया!';

  @override
  String get copyLink => 'लिंक कॉपी करें';

  @override
  String get hideTranscript => 'ट्रांसक्रिप्ट छुपाएं';

  @override
  String get viewTranscript => 'ट्रांसक्रिप्ट देखें';

  @override
  String get conversationDetails => 'बातचीत विवरण';

  @override
  String get transcript => 'ट्रांसक्रिप्ट';

  @override
  String segmentsCount(int count) {
    return '$count खंड';
  }

  @override
  String get noTranscriptAvailable => 'कोई ट्रांसक्रिप्ट उपलब्ध नहीं';

  @override
  String get noTranscriptMessage => 'इस बातचीत में ट्रांसक्रिप्ट नहीं है।';

  @override
  String get conversationUrlCouldNotBeGenerated => 'बातचीत URL बनाया नहीं जा सका।';

  @override
  String get failedToGenerateConversationLink => 'बातचीत लिंक बनाने में विफल';

  @override
  String get failedToGenerateShareLink => 'साझा करने का लिंक बनाने में विफल';

  @override
  String get reloadingConversations => 'बातचीत को फिर से लोड किया जा रहा है...';

  @override
  String get user => 'उपयोगकर्ता';

  @override
  String get starred => 'तारांकित';

  @override
  String get date => 'तारीख';

  @override
  String get noResultsFound => 'कोई परिणाम नहीं मिला';

  @override
  String get tryAdjustingSearchTerms => 'अपने खोज शब्दों को समायोजित करने का प्रयास करें';

  @override
  String get starConversationsToFindQuickly => 'बातचीत को तारांकित करें ताकि उन्हें यहां जल्दी से खोज सकें';

  @override
  String noConversationsOnDate(String date) {
    return '$date को कोई बातचीत नहीं';
  }

  @override
  String get trySelectingDifferentDate => 'एक अलग तारीख चुनने का प्रयास करें';

  @override
  String get conversations => 'बातचीत';

  @override
  String get chat => 'चैट';

  @override
  String get actions => 'क्रियाएं';

  @override
  String get syncAvailable => 'सिंक उपलब्ध है';

  @override
  String get referAFriend => 'किसी मित्र को संदर्भित करें';

  @override
  String get help => 'सहायता';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Pro में अपग्रेड करें';

  @override
  String get getOmiDevice => 'Get Omi Device';

  @override
  String get wearableAiCompanion => 'पहनने योग्य AI साथी';

  @override
  String get loadingMemories => 'यादें लोड हो रही हैं...';

  @override
  String get allMemories => 'सभी यादें';

  @override
  String get aboutYou => 'आपके बारे में';

  @override
  String get manual => 'मैनुअल';

  @override
  String get loadingYourMemories => 'आपकी यादें लोड हो रही हैं...';

  @override
  String get createYourFirstMemory => 'शुरू करने के लिए अपनी पहली याद बनाएं';

  @override
  String get tryAdjustingFilter => 'अपनी खोज या फ़िल्टर समायोजित करने का प्रयास करें';

  @override
  String get whatWouldYouLikeToRemember => 'आप क्या याद रखना चाहेंगे?';

  @override
  String get category => 'श्रेणी';

  @override
  String get public => 'सार्वजनिक';

  @override
  String get failedToSaveCheckConnection => 'सहेजने में विफल। कृपया अपना कनेक्शन जांचें।';

  @override
  String get createMemory => 'स्मृति बनाएं';

  @override
  String get deleteMemoryConfirmation =>
      'क्या आप वाकई इस स्मृति को हटाना चाहते हैं? यह क्रिया पूर्ववत नहीं की जा सकती।';

  @override
  String get makePrivate => 'निजी बनाएं';

  @override
  String get organizeAndControlMemories => 'अपनी यादों को व्यवस्थित और नियंत्रित करें';

  @override
  String get total => 'कुल';

  @override
  String get makeAllMemoriesPrivate => 'सभी यादों को निजी बनाएं';

  @override
  String get setAllMemoriesToPrivate => 'सभी यादों को निजी दृश्यता पर सेट करें';

  @override
  String get makeAllMemoriesPublic => 'सभी यादों को सार्वजनिक बनाएं';

  @override
  String get setAllMemoriesToPublic => 'सभी यादों को सार्वजनिक दृश्यता पर सेट करें';

  @override
  String get permanentlyRemoveAllMemories => 'Omi से सभी यादों को स्थायी रूप से हटाएं';

  @override
  String get allMemoriesAreNowPrivate => 'सभी यादें अब निजी हैं';

  @override
  String get allMemoriesAreNowPublic => 'सभी यादें अब सार्वजनिक हैं';

  @override
  String get clearOmisMemory => 'Omi की स्मृति साफ़ करें';

  @override
  String clearMemoryConfirmation(int count) {
    return 'क्या आप वाकई Omi की स्मृति साफ़ करना चाहते हैं? यह क्रिया पूर्ववत नहीं की जा सकती और सभी $count यादों को स्थायी रूप से हटा देगी।';
  }

  @override
  String get omisMemoryCleared => 'आपके बारे में Omi की स्मृति साफ़ कर दी गई है';

  @override
  String get welcomeToOmi => 'Omi में आपका स्वागत है';

  @override
  String get continueWithApple => 'Apple के साथ जारी रखें';

  @override
  String get continueWithGoogle => 'Google के साथ जारी रखें';

  @override
  String get byContinuingYouAgree => 'जारी रखने से, आप हमारी ';

  @override
  String get termsOfService => 'सेवा की शर्तों';

  @override
  String get and => ' और ';

  @override
  String get dataAndPrivacy => 'डेटा और गोपनीयता';

  @override
  String get secureAuthViaAppleId => 'Apple ID के माध्यम से सुरक्षित प्रमाणीकरण';

  @override
  String get secureAuthViaGoogleAccount => 'Google खाते के माध्यम से सुरक्षित प्रमाणीकरण';

  @override
  String get whatWeCollect => 'हम क्या एकत्र करते हैं';

  @override
  String get dataCollectionMessage =>
      'जारी रखने से, आपकी बातचीत, रिकॉर्डिंग और व्यक्तिगत जानकारी AI-संचालित अंतर्दृष्टि प्रदान करने और सभी ऐप सुविधाओं को सक्षम करने के लिए हमारे सर्वर पर सुरक्षित रूप से संग्रहीत की जाएगी।';

  @override
  String get dataProtection => 'डेटा सुरक्षा';

  @override
  String get yourDataIsProtected => 'आपका डेटा सुरक्षित है और हमारी ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'कृपया अपनी प्राथमिक भाषा चुनें';

  @override
  String get chooseYourLanguage => 'अपनी भाषा चुनें';

  @override
  String get selectPreferredLanguageForBestExperience => 'सर्वोत्तम Omi अनुभव के लिए अपनी पसंदीदा भाषा चुनें';

  @override
  String get searchLanguages => 'भाषाएं खोजें...';

  @override
  String get selectALanguage => 'एक भाषा चुनें';

  @override
  String get tryDifferentSearchTerm => 'एक अलग खोज शब्द आज़माएं';

  @override
  String get pleaseEnterYourName => 'कृपया अपना नाम दर्ज करें';

  @override
  String get nameMustBeAtLeast2Characters => 'नाम कम से कम 2 वर्णों का होना चाहिए';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'हमें बताएं कि आप कैसे संबोधित होना पसंद करेंगे। यह आपके Omi अनुभव को वैयक्तिकृत करने में मदद करता है।';

  @override
  String charactersCount(int count) {
    return '$count वर्ण';
  }

  @override
  String get enableFeaturesForBestExperience => 'अपने डिवाइस पर सर्वोत्तम Omi अनुभव के लिए सुविधाएं सक्षम करें।';

  @override
  String get microphoneAccess => 'माइक्रोफ़ोन एक्सेस';

  @override
  String get recordAudioConversations => 'ऑडियो वार्तालाप रिकॉर्ड करें';

  @override
  String get microphoneAccessDescription =>
      'Omi को आपकी बातचीत रिकॉर्ड करने और ट्रांसक्रिप्शन प्रदान करने के लिए माइक्रोफ़ोन एक्सेस की आवश्यकता है।';

  @override
  String get screenRecording => 'स्क्रीन रिकॉर्डिंग';

  @override
  String get captureSystemAudioFromMeetings => 'मीटिंग से सिस्टम ऑडियो कैप्चर करें';

  @override
  String get screenRecordingDescription =>
      'Omi को आपके ब्राउज़र-आधारित मीटिंग से सिस्टम ऑडियो कैप्चर करने के लिए स्क्रीन रिकॉर्डिंग अनुमति की आवश्यकता है।';

  @override
  String get accessibility => 'पहुंच-योग्यता';

  @override
  String get detectBrowserBasedMeetings => 'ब्राउज़र-आधारित मीटिंग का पता लगाएं';

  @override
  String get accessibilityDescription =>
      'Omi को यह पता लगाने के लिए पहुंच-योग्यता अनुमति की आवश्यकता है कि आप अपने ब्राउज़र में Zoom, Meet, या Teams मीटिंग में कब शामिल होते हैं।';

  @override
  String get pleaseWait => 'कृपया प्रतीक्षा करें...';

  @override
  String get joinTheCommunity => 'समुदाय में शामिल हों!';

  @override
  String get loadingProfile => 'प्रोफ़ाइल लोड हो रही है...';

  @override
  String get profileSettings => 'प्रोफ़ाइल सेटिंग्स';

  @override
  String get noEmailSet => 'कोई ईमेल सेट नहीं है';

  @override
  String get userIdCopiedToClipboard => 'उपयोगकर्ता ID कॉपी की गई';

  @override
  String get yourInformation => 'आपकी जानकारी';

  @override
  String get setYourName => 'अपना नाम सेट करें';

  @override
  String get changeYourName => 'अपना नाम बदलें';

  @override
  String get manageYourOmiPersona => 'अपने Omi व्यक्तित्व को प्रबंधित करें';

  @override
  String get voiceAndPeople => 'आवाज़ और लोग';

  @override
  String get teachOmiYourVoice => 'Omi को अपनी आवाज सिखाएं';

  @override
  String get tellOmiWhoSaidIt => 'Omi को बताएं कि किसने कहा 🗣️';

  @override
  String get payment => 'भुगतान';

  @override
  String get addOrChangeYourPaymentMethod => 'भुगतान विधि जोड़ें या बदलें';

  @override
  String get preferences => 'प्राथमिकताएँ';

  @override
  String get helpImproveOmiBySharing => 'गुमनाम विश्लेषण डेटा साझा करके Omi को बेहतर बनाने में मदद करें';

  @override
  String get deleteAccount => 'खाता हटाएं';

  @override
  String get deleteYourAccountAndAllData => 'अपना खाता और सभी डेटा हटाएं';

  @override
  String get clearLogs => 'लॉग साफ़ करें';

  @override
  String get debugLogsCleared => 'डीबग लॉग साफ़ किए गए';

  @override
  String get exportConversations => 'बातचीत निर्यात करें';

  @override
  String get exportAllConversationsToJson => 'अपनी सभी बातचीत को JSON फ़ाइल में निर्यात करें।';

  @override
  String get conversationsExportStarted =>
      'बातचीत निर्यात शुरू हुआ। इसमें कुछ सेकंड लग सकते हैं, कृपया प्रतीक्षा करें।';

  @override
  String get mcpDescription =>
      'अपनी यादों और बातचीत को पढ़ने, खोजने और प्रबंधित करने के लिए Omi को अन्य अनुप्रयोगों से कनेक्ट करने के लिए। शुरू करने के लिए एक कुंजी बनाएं।';

  @override
  String get apiKeys => 'API कुंजियाँ';

  @override
  String errorLabel(String error) {
    return 'त्रुटि: $error';
  }

  @override
  String get noApiKeysFound => 'कोई API कुंजी नहीं मिली। शुरू करने के लिए एक बनाएं।';

  @override
  String get advancedSettings => 'उन्नत सेटिंग्स';

  @override
  String get triggersWhenNewConversationCreated => 'जब एक नई बातचीत बनाई जाती है तो ट्रिगर होता है।';

  @override
  String get triggersWhenNewTranscriptReceived => 'जब एक नया ट्रांसक्रिप्ट प्राप्त होता है तो ट्रिगर होता है।';

  @override
  String get realtimeAudioBytes => 'रियल-टाइम ऑडियो बाइट्स';

  @override
  String get triggersWhenAudioBytesReceived => 'जब ऑडियो बाइट्स प्राप्त होते हैं तो ट्रिगर होता है।';

  @override
  String get everyXSeconds => 'हर x सेकंड';

  @override
  String get triggersWhenDaySummaryGenerated => 'जब दिन का सारांश जेनरेट होता है तो ट्रिगर होता है।';

  @override
  String get tryLatestExperimentalFeatures => 'Omi टीम की नवीनतम प्रायोगिक सुविधाएं आज़माएं।';

  @override
  String get transcriptionServiceDiagnosticStatus => 'ट्रांसक्रिप्शन सेवा डायग्नोस्टिक स्थिति';

  @override
  String get enableDetailedDiagnosticMessages => 'ट्रांसक्रिप्शन सेवा से विस्तृत डायग्नोस्टिक संदेश सक्षम करें';

  @override
  String get autoCreateAndTagNewSpeakers => 'नए वक्ताओं को स्वचालित रूप से बनाएं और टैग करें';

  @override
  String get automaticallyCreateNewPerson =>
      'जब ट्रांसक्रिप्ट में एक नाम का पता चलता है तो स्वचालित रूप से एक नया व्यक्ति बनाएं।';

  @override
  String get pilotFeatures => 'पायलट सुविधाएं';

  @override
  String get pilotFeaturesDescription => 'ये सुविधाएं परीक्षण हैं और समर्थन की गारंटी नहीं है।';

  @override
  String get suggestFollowUpQuestion => 'फॉलो-अप प्रश्न सुझाएं';

  @override
  String get saveSettings => 'सेटिंग्स सहेजें';

  @override
  String get syncingDeveloperSettings => 'डेवलपर सेटिंग्स सिंक हो रही हैं...';

  @override
  String get summary => 'सारांश';

  @override
  String get auto => 'स्वचालित';

  @override
  String get noSummaryForApp => 'इस ऐप के लिए कोई सारांश उपलब्ध नहीं है। बेहतर परिणामों के लिए कोई अन्य ऐप आज़माएं।';

  @override
  String get tryAnotherApp => 'दूसरा ऐप आज़माएं';

  @override
  String generatedBy(String appName) {
    return '$appName द्वारा उत्पन्न';
  }

  @override
  String get overview => 'अवलोकन';

  @override
  String get otherAppResults => 'अन्य ऐप परिणाम';

  @override
  String get unknownApp => 'अज्ञात ऐप';

  @override
  String get noSummaryAvailable => 'कोई सारांश उपलब्ध नहीं';

  @override
  String get conversationNoSummaryYet => 'इस बातचीत का अभी तक कोई सारांश नहीं है।';

  @override
  String get chooseSummarizationApp => 'सारांश ऐप चुनें';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName को डिफ़ॉल्ट सारांश ऐप के रूप में सेट किया गया';
  }

  @override
  String get letOmiChooseAutomatically => 'Omi को स्वचालित रूप से सर्वोत्तम ऐप चुनने दें';

  @override
  String get deleteConversationConfirmation =>
      'क्या आप वाकई इस बातचीत को हटाना चाहते हैं? इस क्रिया को पूर्ववत नहीं किया जा सकता।';

  @override
  String get conversationDeleted => 'बातचीत हटा दी गई';

  @override
  String get generatingLink => 'लिंक बनाया जा रहा है...';

  @override
  String get editConversation => 'बातचीत संपादित करें';

  @override
  String get conversationLinkCopiedToClipboard => 'बातचीत लिंक क्लिपबोर्ड पर कॉपी किया गया';

  @override
  String get conversationTranscriptCopiedToClipboard => 'बातचीत प्रतिलेख क्लिपबोर्ड पर कॉपी किया गया';

  @override
  String get editConversationDialogTitle => 'बातचीत संपादित करें';

  @override
  String get changeTheConversationTitle => 'बातचीत शीर्षक बदलें';

  @override
  String get conversationTitle => 'बातचीत शीर्षक';

  @override
  String get enterConversationTitle => 'बातचीत शीर्षक दर्ज करें...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'बातचीत शीर्षक सफलतापूर्वक अपडेट किया गया';

  @override
  String get failedToUpdateConversationTitle => 'बातचीत शीर्षक अपडेट करने में विफल';

  @override
  String get errorUpdatingConversationTitle => 'बातचीत शीर्षक अपडेट करने में त्रुटि';

  @override
  String get settingUp => 'सेट अप हो रहा है...';

  @override
  String get startYourFirstRecording => 'अपनी पहली रिकॉर्डिंग शुरू करें';

  @override
  String get preparingSystemAudioCapture => 'सिस्टम ऑडियो कैप्चर तैयार हो रहा है';

  @override
  String get clickTheButtonToCaptureAudio =>
      'लाइव ट्रांसक्रिप्ट, AI जानकारी और स्वचालित सहेजने के लिए ऑडियो कैप्चर करने के लिए बटन पर क्लिक करें।';

  @override
  String get reconnecting => 'फिर से कनेक्ट हो रहा है...';

  @override
  String get recordingPaused => 'रिकॉर्डिंग रोकी गई';

  @override
  String get recordingActive => 'रिकॉर्डिंग सक्रिय';

  @override
  String get startRecording => 'रिकॉर्डिंग शुरू करें';

  @override
  String resumingInCountdown(String countdown) {
    return '${countdown}s में फिर से शुरू हो रहा है...';
  }

  @override
  String get tapPlayToResume => 'फिर से शुरू करने के लिए प्ले पर टैप करें';

  @override
  String get listeningForAudio => 'ऑडियो सुन रहे हैं...';

  @override
  String get preparingAudioCapture => 'ऑडियो कैप्चर तैयार हो रहा है';

  @override
  String get clickToBeginRecording => 'रिकॉर्डिंग शुरू करने के लिए क्लिक करें';

  @override
  String get translated => 'अनुवादित';

  @override
  String get liveTranscript => 'लाइव ट्रांसक्रिप्ट';

  @override
  String segmentsSingular(String count) {
    return '$count खंड';
  }

  @override
  String segmentsPlural(String count) {
    return '$count खंड';
  }

  @override
  String get startRecordingToSeeTranscript => 'लाइव ट्रांसक्रिप्ट देखने के लिए रिकॉर्डिंग शुरू करें';

  @override
  String get paused => 'रोका गया';

  @override
  String get initializing => 'आरंभ हो रहा है...';

  @override
  String get recording => 'रिकॉर्ड कर रहे हैं';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'माइक्रोफ़ोन बदला गया। ${countdown}s में फिर से शुरू हो रहा है';
  }

  @override
  String get clickPlayToResumeOrStop => 'फिर से शुरू करने के लिए प्ले पर या समाप्त करने के लिए स्टॉप पर क्लिक करें';

  @override
  String get settingUpSystemAudioCapture => 'सिस्टम ऑडियो कैप्चर सेट अप हो रहा है';

  @override
  String get capturingAudioAndGeneratingTranscript => 'ऑडियो कैप्चर और ट्रांसक्रिप्ट बनाना';

  @override
  String get clickToBeginRecordingSystemAudio => 'सिस्टम ऑडियो रिकॉर्डिंग शुरू करने के लिए क्लिक करें';

  @override
  String get you => 'आप';

  @override
  String speakerWithId(String speakerId) {
    return 'स्पीकर $speakerId';
  }

  @override
  String get translatedByOmi => 'omi द्वारा अनुवादित';

  @override
  String get backToConversations => 'बातचीत पर वापस जाएं';

  @override
  String get systemAudio => 'सिस्टम';

  @override
  String get mic => 'माइक';

  @override
  String audioInputSetTo(String deviceName) {
    return 'ऑडियो इनपुट $deviceName पर सेट किया गया';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'ऑडियो डिवाइस बदलने में त्रुटि: $error';
  }

  @override
  String get selectAudioInput => 'ऑडियो इनपुट चुनें';

  @override
  String get loadingDevices => 'डिवाइस लोड हो रहे हैं...';

  @override
  String get settingsHeader => 'सेटिंग्स';

  @override
  String get plansAndBilling => 'योजनाएं और बिलिंग';

  @override
  String get calendarIntegration => 'कैलेंडर एकीकरण';

  @override
  String get dailySummary => 'दैनिक सारांश';

  @override
  String get developer => 'डेवलपर';

  @override
  String get about => 'के बारे में';

  @override
  String get selectTime => 'समय चुनें';

  @override
  String get accountGroup => 'खाता';

  @override
  String get signOutQuestion => 'साइन आउट करें?';

  @override
  String get signOutConfirmation => 'Are you sure you want to sign out?';

  @override
  String get customVocabularyHeader => 'कस्टम शब्दावली';

  @override
  String get addWordsDescription => 'ऐसे शब्द जोड़ें जिन्हें Omi ट्रांसक्रिप्शन के दौरान पहचाननी चाहिए।';

  @override
  String get enterWordsHint => 'शब्द दर्ज करें (कॉमा से अलग)';

  @override
  String get dailySummaryHeader => 'दैनिक सारांश';

  @override
  String get dailySummaryTitle => 'दैनिक सारांश';

  @override
  String get dailySummaryDescription => 'अपने दिन की बातचीत का एक व्यक्तिगत सारांश सूचना के रूप में प्राप्त करें।';

  @override
  String get deliveryTime => 'डिलीवरी समय';

  @override
  String get deliveryTimeDescription => 'अपना दैनिक सारांश कब प्राप्त करें';

  @override
  String get subscription => 'सदस्यता';

  @override
  String get viewPlansAndUsage => 'योजनाएं और उपयोग देखें';

  @override
  String get viewPlansDescription => 'अपनी सदस्यता प्रबंधित करें और उपयोग आँकड़े देखें';

  @override
  String get addOrChangePaymentMethod => 'अपनी भुगतान विधि जोड़ें या बदलें';

  @override
  String get displayOptions => 'प्रदर्शन विकल्प';

  @override
  String get showMeetingsInMenuBar => 'मेनू बार में मीटिंग दिखाएं';

  @override
  String get displayUpcomingMeetingsDescription => 'मेनू बार में आगामी मीटिंग दिखाएं';

  @override
  String get showEventsWithoutParticipants => 'प्रतिभागियों के बिना इवेंट दिखाएं';

  @override
  String get includePersonalEventsDescription => 'उपस्थित लोगों के बिना व्यक्तिगत इवेंट शामिल करें';

  @override
  String get upcomingMeetings => 'आगामी बैठकें';

  @override
  String get checkingNext7Days => 'अगले 7 दिनों की जांच';

  @override
  String get shortcuts => 'शॉर्टकट';

  @override
  String get shortcutChangeInstruction => 'इसे बदलने के लिए शॉर्टकट पर क्लिक करें। रद्द करने के लिए Escape दबाएं।';

  @override
  String get configurePersonaDescription => 'अपना AI व्यक्तित्व कॉन्फ़िगर करें';

  @override
  String get configureSTTProvider => 'STT प्रदाता कॉन्फ़िगर करें';

  @override
  String get setConversationEndDescription => 'सेट करें कि बातचीत कब स्वतः समाप्त होती है';

  @override
  String get importDataDescription => 'अन्य स्रोतों से डेटा आयात करें';

  @override
  String get exportConversationsDescription => 'वार्तालाप JSON में निर्यात करें';

  @override
  String get exportingConversations => 'बातचीत निर्यात हो रही है...';

  @override
  String get clearNodesDescription => 'सभी नोड्स और कनेक्शन साफ़ करें';

  @override
  String get deleteKnowledgeGraphQuestion => 'ज्ञान ग्राफ हटाएं?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'यह सभी व्युत्पन्न ज्ञान ग्राफ डेटा हटा देगा। आपकी मूल यादें सुरक्षित रहती हैं।';

  @override
  String get connectOmiWithAI => 'Omi को AI सहायकों से कनेक्ट करें';

  @override
  String get noAPIKeys => 'कोई API कुंजी नहीं। शुरू करने के लिए एक बनाएं।';

  @override
  String get autoCreateWhenDetected => 'नाम का पता चलने पर स्वतः बनाएं';

  @override
  String get trackPersonalGoals => 'होमपेज पर व्यक्तिगत लक्ष्यों को ट्रैक करें';

  @override
  String get dailyReflectionDescription =>
      'रात 9 बजे अपने दिन पर विचार करने और अपने विचारों को कैप्चर करने के लिए एक अनुस्मारक प्राप्त करें।';

  @override
  String get endpointURL => 'एंडपॉइंट URL';

  @override
  String get links => 'लिंक';

  @override
  String get discordMemberCount => 'Discord पर 8000+ सदस्य';

  @override
  String get userInformation => 'उपयोगकर्ता जानकारी';

  @override
  String get capabilities => 'क्षमताएं';

  @override
  String get previewScreenshots => 'स्क्रीनशॉट पूर्वावलोकन';

  @override
  String get holdOnPreparingForm => 'रुकिए, हम आपके लिए फॉर्म तैयार कर रहे हैं';

  @override
  String get bySubmittingYouAgreeToOmi => 'सबमिट करके, आप Omi की ';

  @override
  String get termsAndPrivacyPolicy => 'शर्तें और गोपनीयता नीति';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'समस्याओं का निदान करने में मदद करता है। 3 दिनों के बाद स्वचालित रूप से हटा दिया जाता है।';

  @override
  String get manageYourApp => 'अपना ऐप प्रबंधित करें';

  @override
  String get updatingYourApp => 'आपका ऐप अपडेट हो रहा है';

  @override
  String get fetchingYourAppDetails => 'आपके ऐप का विवरण प्राप्त हो रहा है';

  @override
  String get updateAppQuestion => 'ऐप अपडेट करें?';

  @override
  String get updateAppConfirmation =>
      'क्या आप वाकई अपना ऐप अपडेट करना चाहते हैं? परिवर्तन हमारी टीम द्वारा समीक्षा के बाद दिखाई देंगे।';

  @override
  String get updateApp => 'ऐप अपडेट करें';

  @override
  String get createAndSubmitNewApp => 'नया ऐप बनाएं और सबमिट करें';

  @override
  String appsCount(String count) {
    return 'ऐप्स ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'निजी ऐप्स ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'सार्वजनिक ऐप्स ($count)';
  }

  @override
  String get newVersionAvailable => 'नया संस्करण उपलब्ध  🎉';

  @override
  String get no => 'नहीं';

  @override
  String get subscriptionCancelledSuccessfully =>
      'सदस्यता सफलतापूर्वक रद्द हो गई। यह वर्तमान बिलिंग अवधि के अंत तक सक्रिय रहेगी।';

  @override
  String get failedToCancelSubscription => 'सदस्यता रद्द करने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get invalidPaymentUrl => 'अमान्य भुगतान URL';

  @override
  String get permissionsAndTriggers => 'अनुमतियाँ और ट्रिगर';

  @override
  String get chatFeatures => 'चैट सुविधाएं';

  @override
  String get uninstall => 'अनइंस्टॉल करें';

  @override
  String get installs => 'इंस्टॉल';

  @override
  String get priceLabel => 'मूल्य';

  @override
  String get updatedLabel => 'अपडेट किया गया';

  @override
  String get createdLabel => 'बनाया गया';

  @override
  String get featuredLabel => 'विशेष';

  @override
  String get cancelSubscriptionQuestion => 'सदस्यता रद्द करें?';

  @override
  String get cancelSubscriptionConfirmation =>
      'क्या आप वाकई अपनी सदस्यता रद्द करना चाहते हैं? आपकी वर्तमान बिलिंग अवधि के अंत तक पहुंच जारी रहेगी।';

  @override
  String get cancelSubscriptionButton => 'सदस्यता रद्द करें';

  @override
  String get cancelling => 'रद्द हो रहा है...';

  @override
  String get betaTesterMessage =>
      'आप इस ऐप के बीटा टेस्टर हैं। यह अभी सार्वजनिक नहीं है। अनुमोदित होने के बाद सार्वजनिक होगा।';

  @override
  String get appUnderReviewMessage =>
      'आपका ऐप समीक्षाधीन है और केवल आपको दिखाई दे रहा है। अनुमोदित होने के बाद सार्वजनिक होगा।';

  @override
  String get appRejectedMessage => 'आपका ऐप अस्वीकृत हो गया। कृपया विवरण अपडेट करें और समीक्षा के लिए पुनः सबमिट करें।';

  @override
  String get invalidIntegrationUrl => 'अमान्य इंटीग्रेशन URL';

  @override
  String get tapToComplete => 'पूरा करने के लिए टैप करें';

  @override
  String get invalidSetupInstructionsUrl => 'अमान्य सेटअप निर्देश URL';

  @override
  String get pushToTalk => 'बोलने के लिए दबाएं';

  @override
  String get summaryPrompt => 'सारांश प्रॉम्प्ट';

  @override
  String get pleaseSelectARating => 'कृपया एक रेटिंग चुनें';

  @override
  String get reviewAddedSuccessfully => 'समीक्षा सफलतापूर्वक जोड़ी गई 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'समीक्षा सफलतापूर्वक अपडेट की गई 🚀';

  @override
  String get failedToSubmitReview => 'समीक्षा सबमिट करने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get addYourReview => 'अपनी समीक्षा जोड़ें';

  @override
  String get editYourReview => 'अपनी समीक्षा संपादित करें';

  @override
  String get writeAReviewOptional => 'समीक्षा लिखें (वैकल्पिक)';

  @override
  String get submitReview => 'समीक्षा सबमिट करें';

  @override
  String get updateReview => 'समीक्षा अपडेट करें';

  @override
  String get yourReview => 'आपकी समीक्षा';

  @override
  String get anonymousUser => 'अनाम उपयोगकर्ता';

  @override
  String get issueActivatingApp => 'इस ऐप को सक्रिय करने में समस्या हुई। कृपया पुनः प्रयास करें।';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'URL कॉपी करें';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'सोम';

  @override
  String get weekdayTue => 'मंगल';

  @override
  String get weekdayWed => 'बुध';

  @override
  String get weekdayThu => 'गुरु';

  @override
  String get weekdayFri => 'शुक्र';

  @override
  String get weekdaySat => 'शनि';

  @override
  String get weekdaySun => 'रवि';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName एकीकरण जल्द आ रहा है';
  }

  @override
  String alreadyExportedTo(String platform) {
    return '$platform में पहले ही निर्यात किया गया';
  }

  @override
  String get anotherPlatform => 'किसी अन्य प्लेटफ़ॉर्म';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'कृपया सेटिंग्स > टास्क इंटीग्रेशन में $serviceName से प्रमाणित करें';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceName में जोड़ा जा रहा है...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceName में जोड़ा गया';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceName में जोड़ने में विफल';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple Reminders के लिए अनुमति अस्वीकृत';

  @override
  String failedToCreateApiKey(String error) {
    return 'प्रदाता API कुंजी बनाने में विफल: $error';
  }

  @override
  String get createAKey => 'एक कुंजी बनाएं';

  @override
  String get apiKeyRevokedSuccessfully => 'API कुंजी सफलतापूर्वक रद्द की गई';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API कुंजी रद्द करने में विफल: $error';
  }

  @override
  String get omiApiKeys => 'Omi API कुंजियाँ';

  @override
  String get apiKeysDescription =>
      'API कुंजियाँ प्रमाणीकरण के लिए उपयोग की जाती हैं जब आपका ऐप OMI सर्वर के साथ संवाद करता है। वे आपके एप्लिकेशन को यादें बनाने और अन्य OMI सेवाओं तक सुरक्षित रूप से पहुंचने की अनुमति देती हैं।';

  @override
  String get aboutOmiApiKeys => 'Omi API कुंजियों के बारे में';

  @override
  String get yourNewKey => 'आपकी नई कुंजी:';

  @override
  String get copyToClipboard => 'क्लिपबोर्ड पर कॉपी करें';

  @override
  String get pleaseCopyKeyNow => 'कृपया इसे अभी कॉपी करें और कहीं सुरक्षित जगह लिख लें। ';

  @override
  String get willNotSeeAgain => 'आप इसे फिर से नहीं देख पाएंगे।';

  @override
  String get revokeKey => 'कुंजी रद्द करें';

  @override
  String get revokeApiKeyQuestion => 'API कुंजी रद्द करें?';

  @override
  String get revokeApiKeyWarning =>
      'यह क्रिया वापस नहीं की जा सकती। इस कुंजी का उपयोग करने वाले कोई भी एप्लिकेशन अब API तक नहीं पहुंच पाएंगे।';

  @override
  String get revoke => 'रद्द करें';

  @override
  String get whatWouldYouLikeToCreate => 'आप क्या बनाना चाहेंगे?';

  @override
  String get createAnApp => 'एक ऐप बनाएं';

  @override
  String get createAndShareYourApp => 'अपना ऐप बनाएं और साझा करें';

  @override
  String get createMyClone => 'मेरा क्लोन बनाएं';

  @override
  String get createYourDigitalClone => 'अपना डिजिटल क्लोन बनाएं';

  @override
  String get itemApp => 'ऐप';

  @override
  String get itemPersona => 'पर्सोना';

  @override
  String keepItemPublic(String item) {
    return '$item को सार्वजनिक रखें';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item को सार्वजनिक करें?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item को निजी करें?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'यदि आप $item को सार्वजनिक करते हैं, तो इसे सभी द्वारा उपयोग किया जा सकता है';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'यदि आप अभी $item को निजी करते हैं, तो यह सभी के लिए काम करना बंद कर देगा और केवल आपको दिखाई देगा';
  }

  @override
  String get manageApp => 'ऐप प्रबंधित करें';

  @override
  String get updatePersonaDetails => 'पर्सोना विवरण अपडेट करें';

  @override
  String deleteItemTitle(String item) {
    return '$item हटाएं';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item हटाएं?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'क्या आप वाकई इस $item को हटाना चाहते हैं? इस क्रिया को पूर्ववत नहीं किया जा सकता।';
  }

  @override
  String get revokeKeyQuestion => 'कुंजी रद्द करें?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'क्या आप वाकई कुंजी \"$keyName\" को रद्द करना चाहते हैं? इस क्रिया को पूर्ववत नहीं किया जा सकता।';
  }

  @override
  String get createNewKey => 'नई कुंजी बनाएं';

  @override
  String get keyNameHint => 'जैसे, Claude Desktop';

  @override
  String get pleaseEnterAName => 'कृपया एक नाम दर्ज करें।';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'कुंजी बनाने में विफल: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'कुंजी बनाने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get keyCreated => 'कुंजी बनाई गई';

  @override
  String get keyCreatedMessage => 'आपकी नई कुंजी बना दी गई है। कृपया इसे अभी कॉपी करें। आप इसे दोबारा नहीं देख पाएंगे।';

  @override
  String get keyWord => 'कुंजी';

  @override
  String get externalAppAccess => 'बाहरी ऐप एक्सेस';

  @override
  String get externalAppAccessDescription =>
      'निम्नलिखित इंस्टॉल किए गए ऐप्स में बाहरी एकीकरण हैं और वे आपके डेटा तक पहुंच सकते हैं, जैसे बातचीत और यादें।';

  @override
  String get noExternalAppsHaveAccess => 'किसी भी बाहरी ऐप के पास आपके डेटा तक पहुंच नहीं है।';

  @override
  String get maximumSecurityE2ee => 'अधिकतम सुरक्षा (E2EE)';

  @override
  String get e2eeDescription =>
      'एंड-टू-एंड एन्क्रिप्शन गोपनीयता का स्वर्ण मानक है। सक्षम होने पर, आपका डेटा हमारे सर्वर पर भेजे जाने से पहले आपके डिवाइस पर एन्क्रिप्ट किया जाता है। इसका मतलब है कि कोई भी, यहां तक कि Omi भी, आपकी सामग्री तक नहीं पहुंच सकता।';

  @override
  String get importantTradeoffs => 'महत्वपूर्ण समझौते:';

  @override
  String get e2eeTradeoff1 => '• बाहरी ऐप इंटीग्रेशन जैसी कुछ सुविधाएं अक्षम हो सकती हैं।';

  @override
  String get e2eeTradeoff2 => '• यदि आप अपना पासवर्ड खो देते हैं, तो आपका डेटा पुनर्प्राप्त नहीं किया जा सकता।';

  @override
  String get featureComingSoon => 'यह सुविधा जल्द आ रही है!';

  @override
  String get migrationInProgressMessage => 'माइग्रेशन प्रगति में है। पूरा होने तक आप सुरक्षा स्तर नहीं बदल सकते।';

  @override
  String get migrationFailed => 'माइग्रेशन विफल';

  @override
  String migratingFromTo(String source, String target) {
    return '$source से $target में माइग्रेट हो रहा है';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total ऑब्जेक्ट';
  }

  @override
  String get secureEncryption => 'सुरक्षित एन्क्रिप्शन';

  @override
  String get secureEncryptionDescription =>
      'आपका डेटा हमारे सर्वर पर आपके लिए एक अद्वितीय कुंजी के साथ एन्क्रिप्ट किया गया है, जो Google Cloud पर होस्ट किया गया है। इसका मतलब है कि आपकी कच्ची सामग्री किसी के लिए भी अप्राप्य है, जिसमें Omi स्टाफ या Google शामिल हैं, सीधे डेटाबेस से।';

  @override
  String get endToEndEncryption => 'एंड-टू-एंड एन्क्रिप्शन';

  @override
  String get e2eeCardDescription =>
      'अधिकतम सुरक्षा के लिए सक्षम करें जहां केवल आप अपना डेटा एक्सेस कर सकते हैं। अधिक जानने के लिए टैप करें।';

  @override
  String get dataAlwaysEncrypted => 'स्तर के बावजूद, आपका डेटा हमेशा आराम और पारगमन में एन्क्रिप्टेड रहता है।';

  @override
  String get readOnlyScope => 'केवल पढ़ने के लिए';

  @override
  String get fullAccessScope => 'पूर्ण पहुंच';

  @override
  String get readScope => 'पढ़ें';

  @override
  String get writeScope => 'लिखें';

  @override
  String get apiKeyCreated => 'API कुंजी बनाई गई!';

  @override
  String get saveKeyWarning => 'इस कुंजी को अभी सहेजें! आप इसे दोबारा नहीं देख पाएंगे।';

  @override
  String get yourApiKey => 'आपकी API कुंजी';

  @override
  String get tapToCopy => 'कॉपी करने के लिए टैप करें';

  @override
  String get copyKey => 'कुंजी कॉपी करें';

  @override
  String get createApiKey => 'API कुंजी बनाएं';

  @override
  String get accessDataProgrammatically => 'अपने डेटा को प्रोग्रामेटिक रूप से एक्सेस करें';

  @override
  String get keyNameLabel => 'कुंजी नाम';

  @override
  String get keyNamePlaceholder => 'उदा., मेरा ऐप इंटीग्रेशन';

  @override
  String get permissionsLabel => 'अनुमतियाँ';

  @override
  String get permissionsInfoNote => 'R = पढ़ें, W = लिखें। कुछ भी चयनित न होने पर डिफ़ॉल्ट केवल पढ़ने के लिए।';

  @override
  String get developerApi => 'डेवलपर API';

  @override
  String get createAKeyToGetStarted => 'शुरू करने के लिए एक कुंजी बनाएं';

  @override
  String errorWithMessage(String error) {
    return 'त्रुटि: $error';
  }

  @override
  String get omiTraining => 'ओमी प्रशिक्षण';

  @override
  String get trainingDataProgram => 'प्रशिक्षण डेटा कार्यक्रम';

  @override
  String get getOmiUnlimitedFree =>
      'AI मॉडल को प्रशिक्षित करने के लिए अपना डेटा योगदान करके मुफ्त में Omi अनलिमिटेड प्राप्त करें।';

  @override
  String get trainingDataBullets =>
      '• आपका डेटा AI मॉडल को बेहतर बनाने में मदद करता है\n• केवल गैर-संवेदनशील डेटा साझा किया जाता है\n• पूरी तरह से पारदर्शी प्रक्रिया';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training पर और जानें';

  @override
  String get agreeToContributeData => 'मैं AI प्रशिक्षण के लिए अपना डेटा योगदान करने को समझता/समझती हूं और सहमत हूं';

  @override
  String get submitRequest => 'अनुरोध सबमिट करें';

  @override
  String get thankYouRequestUnderReview => 'धन्यवाद! आपका अनुरोध समीक्षाधीन है। स्वीकृति के बाद हम आपको सूचित करेंगे।';

  @override
  String planRemainsActiveUntil(String date) {
    return 'आपकी योजना $date तक सक्रिय रहेगी। उसके बाद, आप अपनी असीमित सुविधाओं तक पहुंच खो देंगे। क्या आप सुनिश्चित हैं?';
  }

  @override
  String get confirmCancellation => 'रद्दीकरण की पुष्टि करें';

  @override
  String get keepMyPlan => 'मेरी योजना रखें';

  @override
  String get subscriptionSetToCancel => 'आपकी सदस्यता अवधि के अंत में रद्द होने के लिए सेट है।';

  @override
  String get switchedToOnDevice => 'डिवाइस पर ट्रांसक्रिप्शन पर स्विच किया गया';

  @override
  String get couldNotSwitchToFreePlan => 'मुफ्त योजना पर स्विच नहीं कर सका। कृपया पुनः प्रयास करें।';

  @override
  String get couldNotLoadPlans => 'उपलब्ध योजनाएं लोड नहीं हो सकीं। कृपया पुनः प्रयास करें।';

  @override
  String get selectedPlanNotAvailable => 'चयनित योजना उपलब्ध नहीं है। कृपया पुनः प्रयास करें।';

  @override
  String get upgradeToAnnualPlan => 'वार्षिक योजना में अपग्रेड करें';

  @override
  String get importantBillingInfo => 'महत्वपूर्ण बिलिंग जानकारी:';

  @override
  String get monthlyPlanContinues => 'आपकी वर्तमान मासिक योजना आपके बिलिंग अवधि के अंत तक जारी रहेगी';

  @override
  String get paymentMethodCharged =>
      'जब आपकी मासिक योजना समाप्त होगी तो आपकी मौजूदा भुगतान विधि से स्वचालित रूप से शुल्क लिया जाएगा';

  @override
  String get annualSubscriptionStarts => 'आपकी 12 महीने की वार्षिक सदस्यता शुल्क के बाद स्वचालित रूप से शुरू हो जाएगी';

  @override
  String get thirteenMonthsCoverage => 'आपको कुल 13 महीने की कवरेज मिलेगी (वर्तमान महीना + 12 महीने वार्षिक)';

  @override
  String get confirmUpgrade => 'अपग्रेड की पुष्टि करें';

  @override
  String get confirmPlanChange => 'योजना परिवर्तन की पुष्टि करें';

  @override
  String get confirmAndProceed => 'पुष्टि करें और आगे बढ़ें';

  @override
  String get upgradeScheduled => 'अपग्रेड निर्धारित';

  @override
  String get changePlan => 'योजना बदलें';

  @override
  String get upgradeAlreadyScheduled => 'आपका वार्षिक योजना में अपग्रेड पहले से निर्धारित है';

  @override
  String get youAreOnUnlimitedPlan => 'आप अनलिमिटेड प्लान पर हैं।';

  @override
  String get yourOmiUnleashed => 'आपका Omi, मुक्त। असीमित संभावनाओं के लिए अनलिमिटेड हो जाएं।';

  @override
  String planEndedOn(String date) {
    return 'आपकी योजना $date को समाप्त हो गई।\\nअभी पुनः सदस्यता लें - नई बिलिंग अवधि के लिए तुरंत शुल्क लिया जाएगा।';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'आपकी योजना $date को रद्द होने के लिए सेट है।\\nअपने लाभ बनाए रखने के लिए अभी पुनः सदस्यता लें - $date तक कोई शुल्क नहीं।';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'जब आपकी मासिक योजना समाप्त होगी तो आपकी वार्षिक योजना स्वचालित रूप से शुरू हो जाएगी।';

  @override
  String planRenewsOn(String date) {
    return 'आपकी योजना $date को नवीनीकृत होती है।';
  }

  @override
  String get unlimitedConversations => 'असीमित बातचीत';

  @override
  String get askOmiAnything => 'अपने जीवन के बारे में Omi से कुछ भी पूछें';

  @override
  String get unlockOmiInfiniteMemory => 'Omi की अनंत स्मृति अनलॉक करें';

  @override
  String get youreOnAnnualPlan => 'आप वार्षिक योजना पर हैं';

  @override
  String get alreadyBestValuePlan => 'आपके पास पहले से सबसे अच्छी मूल्य योजना है। किसी बदलाव की जरूरत नहीं।';

  @override
  String get unableToLoadPlans => 'योजनाएं लोड नहीं हो पाईं';

  @override
  String get checkConnectionTryAgain => 'कृपया अपना कनेक्शन जांचें और पुनः प्रयास करें';

  @override
  String get useFreePlan => 'मुफ्त योजना का उपयोग करें';

  @override
  String get continueText => 'जारी रखें';

  @override
  String get resubscribe => 'पुनः सदस्यता लें';

  @override
  String get couldNotOpenPaymentSettings => 'भुगतान सेटिंग्स नहीं खुल सकीं। कृपया पुनः प्रयास करें।';

  @override
  String get managePaymentMethod => 'भुगतान विधि प्रबंधित करें';

  @override
  String get cancelSubscription => 'सदस्यता रद्द करें';

  @override
  String endsOnDate(String date) {
    return '$date को समाप्त होता है';
  }

  @override
  String get active => 'सक्रिय';

  @override
  String get freePlan => 'मुफ्त योजना';

  @override
  String get configure => 'कॉन्फ़िगर करें';

  @override
  String get privacyInformation => 'गोपनीयता जानकारी';

  @override
  String get yourPrivacyMattersToUs => 'आपकी गोपनीयता हमारे लिए महत्वपूर्ण है';

  @override
  String get privacyIntroText =>
      'Omi में, हम आपकी गोपनीयता को बहुत गंभीरता से लेते हैं। हम उन डेटा के बारे में पारदर्शी रहना चाहते हैं जो हम एकत्र करते हैं और उनका उपयोग कैसे करते हैं। यहाँ आपको क्या जानना चाहिए:';

  @override
  String get whatWeTrack => 'हम क्या ट्रैक करते हैं';

  @override
  String get anonymityAndPrivacy => 'गुमनामी और गोपनीयता';

  @override
  String get optInAndOptOutOptions => 'ऑप्ट-इन और ऑप्ट-आउट विकल्प';

  @override
  String get ourCommitment => 'हमारी प्रतिबद्धता';

  @override
  String get commitmentText =>
      'हम केवल Omi को आपके लिए बेहतर उत्पाद बनाने के लिए एकत्र किए गए डेटा का उपयोग करने के लिए प्रतिबद्ध हैं। आपकी गोपनीयता और विश्वास हमारे लिए सर्वोपरि हैं।';

  @override
  String get thankYouText =>
      'Omi के एक मूल्यवान उपयोगकर्ता होने के लिए धन्यवाद। यदि आपके कोई प्रश्न या चिंताएं हैं, तो team@basedhardware.com पर हमसे संपर्क करें।';

  @override
  String get wifiSyncSettings => 'WiFi सिंक सेटिंग्स';

  @override
  String get enterHotspotCredentials => 'अपने फोन के हॉटस्पॉट क्रेडेंशियल दर्ज करें';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi सिंक आपके फोन को हॉटस्पॉट के रूप में उपयोग करता है। सेटिंग्स > पर्सनल हॉटस्पॉट में नाम और पासवर्ड खोजें।';

  @override
  String get hotspotNameSsid => 'हॉटस्पॉट नाम (SSID)';

  @override
  String get exampleIphoneHotspot => 'उदा. iPhone हॉटस्पॉट';

  @override
  String get password => 'पासवर्ड';

  @override
  String get enterHotspotPassword => 'हॉटस्पॉट पासवर्ड दर्ज करें';

  @override
  String get saveCredentials => 'क्रेडेंशियल सहेजें';

  @override
  String get clearCredentials => 'क्रेडेंशियल साफ़ करें';

  @override
  String get pleaseEnterHotspotName => 'कृपया हॉटस्पॉट नाम दर्ज करें';

  @override
  String get wifiCredentialsSaved => 'WiFi क्रेडेंशियल सहेजे गए';

  @override
  String get wifiCredentialsCleared => 'WiFi क्रेडेंशियल साफ़ किए गए';

  @override
  String summaryGeneratedForDate(String date) {
    return 'सारांश $date के लिए बनाया गया';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'सारांश बनाने में विफल। सुनिश्चित करें कि उस दिन की बातचीत हो।';

  @override
  String get summaryNotFound => 'सारांश नहीं मिला';

  @override
  String get yourDaysJourney => 'आपके दिन की यात्रा';

  @override
  String get highlights => 'मुख्य बातें';

  @override
  String get unresolvedQuestions => 'अनसुलझे प्रश्न';

  @override
  String get decisions => 'निर्णय';

  @override
  String get learnings => 'सीखें';

  @override
  String get autoDeletesAfterThreeDays => '3 दिनों के बाद स्वचालित रूप से हटा दिया जाता है।';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'नॉलेज ग्राफ सफलतापूर्वक हटाया गया';

  @override
  String get exportStartedMayTakeFewSeconds => 'निर्यात शुरू हुआ। इसमें कुछ सेकंड लग सकते हैं...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'यह सभी व्युत्पन्न नॉलेज ग्राफ डेटा (नोड्स और कनेक्शन) को हटा देगा। आपकी मूल यादें सुरक्षित रहेंगी। ग्राफ समय के साथ या अगले अनुरोध पर पुनर्निर्मित होगा।';

  @override
  String get configureDailySummaryDigest => 'अपना दैनिक कार्य सारांश कॉन्फ़िगर करें';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes तक पहुंच';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType द्वारा ट्रिगर';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription और $triggerDescription।';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription।';
  }

  @override
  String get noSpecificDataAccessConfigured => 'कोई विशिष्ट डेटा एक्सेस कॉन्फ़िगर नहीं किया गया।';

  @override
  String get basicPlanDescription => '1,200 प्रीमियम मिनट + डिवाइस पर असीमित';

  @override
  String get minutes => 'मिनट';

  @override
  String get omiHas => 'Omi के पास है:';

  @override
  String get premiumMinutesUsed => 'प्रीमियम मिनट उपयोग किए गए।';

  @override
  String get setupOnDevice => 'डिवाइस पर सेटअप करें';

  @override
  String get forUnlimitedFreeTranscription => 'असीमित मुफ्त ट्रांसक्रिप्शन के लिए।';

  @override
  String premiumMinsLeft(int count) {
    return '$count प्रीमियम मिनट शेष।';
  }

  @override
  String get alwaysAvailable => 'हमेशा उपलब्ध।';

  @override
  String get importHistory => 'आयात इतिहास';

  @override
  String get noImportsYet => 'अभी तक कोई आयात नहीं';

  @override
  String get selectZipFileToImport => 'आयात करने के लिए .zip फ़ाइल चुनें!';

  @override
  String get otherDevicesComingSoon => 'अन्य डिवाइस जल्द आ रहे हैं';

  @override
  String get deleteAllLimitlessConversations => 'सभी Limitless वार्तालाप हटाएं?';

  @override
  String get deleteAllLimitlessWarning =>
      'यह Limitless से आयातित सभी वार्तालापों को स्थायी रूप से हटा देगा। यह क्रिया पूर्ववत नहीं की जा सकती।';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless वार्तालाप हटाए गए';
  }

  @override
  String get failedToDeleteConversations => 'वार्तालाप हटाने में विफल';

  @override
  String get deleteImportedData => 'आयातित डेटा हटाएं';

  @override
  String get statusPending => 'लंबित';

  @override
  String get statusProcessing => 'प्रसंस्करण';

  @override
  String get statusCompleted => 'पूर्ण';

  @override
  String get statusFailed => 'विफल';

  @override
  String nConversations(int count) {
    return '$count वार्तालाप';
  }

  @override
  String get pleaseEnterName => 'कृपया एक नाम दर्ज करें';

  @override
  String get nameMustBeBetweenCharacters => 'नाम 2 से 40 अक्षरों के बीच होना चाहिए';

  @override
  String get deleteSampleQuestion => 'नमूना हटाएं?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'क्या आप वाकई $name का नमूना हटाना चाहते हैं?';
  }

  @override
  String get confirmDeletion => 'हटाने की पुष्टि करें';

  @override
  String deletePersonConfirmation(String name) {
    return 'क्या आप वाकई $name को हटाना चाहते हैं? इससे सभी संबंधित भाषण नमूने भी हट जाएंगे।';
  }

  @override
  String get howItWorksTitle => 'यह कैसे काम करता है?';

  @override
  String get howPeopleWorks =>
      'एक बार व्यक्ति बन जाने के बाद, आप बातचीत के ट्रांसक्रिप्ट में जा सकते हैं और उन्हें उनके संबंधित सेगमेंट असाइन कर सकते हैं, इस तरह Omi उनकी आवाज़ को भी पहचान पाएगा!';

  @override
  String get tapToDelete => 'हटाने के लिए टैप करें';

  @override
  String get newTag => 'नया';

  @override
  String get needHelpChatWithUs => 'मदद चाहिए? हमसे चैट करें';

  @override
  String get localStorageEnabled => 'स्थानीय संग्रहण सक्षम';

  @override
  String get localStorageDisabled => 'स्थानीय संग्रहण अक्षम';

  @override
  String failedToUpdateSettings(String error) {
    return 'सेटिंग्स अपडेट करने में विफल: $error';
  }

  @override
  String get privacyNotice => 'गोपनीयता सूचना';

  @override
  String get recordingsMayCaptureOthers =>
      'रिकॉर्डिंग दूसरों की आवाज़ें कैप्चर कर सकती हैं। सक्षम करने से पहले सभी प्रतिभागियों की सहमति सुनिश्चित करें।';

  @override
  String get enable => 'सक्षम करें';

  @override
  String get storeAudioOnPhone => 'Store Audio on Phone';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'सभी ऑडियो रिकॉर्डिंग को अपने फ़ोन पर स्थानीय रूप से संग्रहीत रखें। अक्षम होने पर, केवल विफल अपलोड संग्रहण स्थान बचाने के लिए रखे जाते हैं।';

  @override
  String get enableLocalStorage => 'स्थानीय संग्रहण सक्षम करें';

  @override
  String get cloudStorageEnabled => 'क्लाउड स्टोरेज सक्षम';

  @override
  String get cloudStorageDisabled => 'क्लाउड स्टोरेज अक्षम';

  @override
  String get enableCloudStorage => 'क्लाउड स्टोरेज सक्षम करें';

  @override
  String get storeAudioOnCloud => 'Store Audio on Cloud';

  @override
  String get cloudStorageDialogMessage =>
      'बोलते समय आपकी रीयल-टाइम रिकॉर्डिंग निजी क्लाउड स्टोरेज में संग्रहीत की जाएंगी।';

  @override
  String get storeAudioCloudDescription =>
      'बोलते समय अपनी रीयल-टाइम रिकॉर्डिंग को निजी क्लाउड स्टोरेज में संग्रहीत करें। ऑडियो रीयल-टाइम में सुरक्षित रूप से कैप्चर और सहेजा जाता है।';

  @override
  String get downloadingFirmware => 'फर्मवेयर डाउनलोड हो रहा है';

  @override
  String get installingFirmware => 'फर्मवेयर इंस्टॉल हो रहा है';

  @override
  String get firmwareUpdateWarning => 'ऐप बंद न करें या डिवाइस बंद न करें। इससे आपका डिवाइस खराब हो सकता है।';

  @override
  String get firmwareUpdated => 'फर्मवेयर अपडेट हो गया';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'अपडेट पूरा करने के लिए कृपया अपना $deviceName पुनः प्रारंभ करें।';
  }

  @override
  String get yourDeviceIsUpToDate => 'आपका डिवाइस अप टू डेट है';

  @override
  String get currentVersion => 'वर्तमान संस्करण';

  @override
  String get latestVersion => 'नवीनतम संस्करण';

  @override
  String get whatsNew => 'नया क्या है';

  @override
  String get installUpdate => 'अपडेट इंस्टॉल करें';

  @override
  String get updateNow => 'अभी अपडेट करें';

  @override
  String get updateGuide => 'अपडेट गाइड';

  @override
  String get checkingForUpdates => 'अपडेट की जांच हो रही है';

  @override
  String get checkingFirmwareVersion => 'फर्मवेयर संस्करण की जांच हो रही है...';

  @override
  String get firmwareUpdate => 'फर्मवेयर अपडेट';

  @override
  String get payments => 'भुगतान';

  @override
  String get connectPaymentMethodInfo =>
      'अपने ऐप्स के लिए भुगतान प्राप्त करना शुरू करने के लिए नीचे एक भुगतान विधि कनेक्ट करें।';

  @override
  String get selectedPaymentMethod => 'चयनित भुगतान विधि';

  @override
  String get availablePaymentMethods => 'उपलब्ध भुगतान विधियाँ';

  @override
  String get activeStatus => 'सक्रिय';

  @override
  String get connectedStatus => 'कनेक्टेड';

  @override
  String get notConnectedStatus => 'कनेक्ट नहीं';

  @override
  String get setActive => 'सक्रिय के रूप में सेट करें';

  @override
  String get getPaidThroughStripe => 'Stripe के माध्यम से अपने ऐप की बिक्री के लिए भुगतान प्राप्त करें';

  @override
  String get monthlyPayouts => 'मासिक भुगतान';

  @override
  String get monthlyPayoutsDescription =>
      'जब आप \$10 की कमाई तक पहुंचें तो सीधे अपने खाते में मासिक भुगतान प्राप्त करें';

  @override
  String get secureAndReliable => 'सुरक्षित और विश्वसनीय';

  @override
  String get stripeSecureDescription => 'Stripe आपके ऐप राजस्व के सुरक्षित और समय पर हस्तांतरण सुनिश्चित करता है';

  @override
  String get selectYourCountry => 'अपना देश चुनें';

  @override
  String get countrySelectionPermanent => 'आपका देश चयन स्थायी है और बाद में बदला नहीं जा सकता।';

  @override
  String get byClickingConnectNow => '\"अभी कनेक्ट करें\" पर क्लिक करके आप सहमत होते हैं';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe कनेक्टेड खाता समझौता';

  @override
  String get errorConnectingToStripe => 'Stripe से कनेक्ट करने में त्रुटि! कृपया बाद में पुनः प्रयास करें।';

  @override
  String get connectingYourStripeAccount => 'आपका Stripe खाता कनेक्ट हो रहा है';

  @override
  String get stripeOnboardingInstructions =>
      'कृपया अपने ब्राउज़र में Stripe ऑनबोर्डिंग प्रक्रिया पूरी करें। पूरा होने पर यह पेज स्वचालित रूप से अपडेट हो जाएगा।';

  @override
  String get failedTryAgain => 'विफल? पुनः प्रयास करें';

  @override
  String get illDoItLater => 'मैं बाद में करूंगा';

  @override
  String get successfullyConnected => 'सफलतापूर्वक कनेक्ट हो गया!';

  @override
  String get stripeReadyForPayments =>
      'आपका Stripe खाता अब भुगतान प्राप्त करने के लिए तैयार है। आप तुरंत अपने ऐप की बिक्री से कमाई शुरू कर सकते हैं।';

  @override
  String get updateStripeDetails => 'Stripe विवरण अपडेट करें';

  @override
  String get errorUpdatingStripeDetails => 'Stripe विवरण अपडेट करने में त्रुटि! कृपया बाद में पुनः प्रयास करें।';

  @override
  String get updatePayPal => 'PayPal अपडेट करें';

  @override
  String get setUpPayPal => 'PayPal सेट अप करें';

  @override
  String get updatePayPalAccountDetails => 'अपने PayPal खाते का विवरण अपडेट करें';

  @override
  String get connectPayPalToReceivePayments =>
      'अपने ऐप्स के लिए भुगतान प्राप्त करना शुरू करने के लिए अपना PayPal खाता कनेक्ट करें';

  @override
  String get paypalEmail => 'PayPal ईमेल';

  @override
  String get paypalMeLink => 'PayPal.me लिंक';

  @override
  String get stripeRecommendation =>
      'यदि आपके देश में Stripe उपलब्ध है, तो तेज़ और आसान भुगतान के लिए हम इसका उपयोग करने की अत्यधिक अनुशंसा करते हैं।';

  @override
  String get updatePayPalDetails => 'PayPal विवरण अपडेट करें';

  @override
  String get savePayPalDetails => 'PayPal विवरण सहेजें';

  @override
  String get pleaseEnterPayPalEmail => 'कृपया अपना PayPal ईमेल दर्ज करें';

  @override
  String get pleaseEnterPayPalMeLink => 'कृपया अपना PayPal.me लिंक दर्ज करें';

  @override
  String get doNotIncludeHttpInLink => 'लिंक में http या https या www शामिल न करें';

  @override
  String get pleaseEnterValidPayPalMeLink => 'कृपया एक वैध PayPal.me लिंक दर्ज करें';

  @override
  String get pleaseEnterValidEmail => 'कृपया एक वैध ईमेल पता दर्ज करें';

  @override
  String get syncingYourRecordings => 'आपकी रिकॉर्डिंग सिंक हो रही हैं';

  @override
  String get syncYourRecordings => 'अपनी रिकॉर्डिंग सिंक करें';

  @override
  String get syncNow => 'अभी सिंक करें';

  @override
  String get error => 'त्रुटि';

  @override
  String get speechSamples => 'भाषण के नमूने';

  @override
  String additionalSampleIndex(String index) {
    return 'अतिरिक्त नमूना $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'अवधि: $seconds सेकंड';
  }

  @override
  String get additionalSpeechSampleRemoved => 'अतिरिक्त भाषण नमूना हटाया गया';

  @override
  String get consentDataMessage =>
      'जारी रखने पर, इस ऐप के साथ आपके द्वारा साझा किया गया सभी डेटा (आपकी बातचीत, रिकॉर्डिंग और व्यक्तिगत जानकारी सहित) AI-संचालित अंतर्दृष्टि प्रदान करने और सभी ऐप सुविधाओं को सक्षम करने के लिए हमारे सर्वर पर सुरक्षित रूप से संग्रहीत किया जाएगा।';

  @override
  String get tasksEmptyStateMessage =>
      'आपकी बातचीत के कार्य यहां दिखाई देंगे।\nमैन्युअल रूप से बनाने के लिए + टैप करें।';

  @override
  String get clearChatAction => 'चैट साफ़ करें';

  @override
  String get enableApps => 'ऐप्स सक्षम करें';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'और दिखाएं ↓';

  @override
  String get showLess => 'कम दिखाएं ↑';

  @override
  String get loadingYourRecording => 'आपकी रिकॉर्डिंग लोड हो रही है...';

  @override
  String get photoDiscardedMessage => 'यह फोटो हटा दी गई क्योंकि यह महत्वपूर्ण नहीं थी।';

  @override
  String get analyzing => 'विश्लेषण हो रहा है...';

  @override
  String get searchCountries => 'देश खोजें...';

  @override
  String get checkingAppleWatch => 'Apple Watch की जाँच हो रही है...';

  @override
  String get installOmiOnAppleWatch => 'अपने Apple Watch पर\nOmi इंस्टॉल करें';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Omi के साथ Apple Watch का उपयोग करने के लिए, आपको पहले अपनी घड़ी पर Omi ऐप इंस्टॉल करना होगा।';

  @override
  String get openOmiOnAppleWatch => 'अपने Apple Watch पर\nOmi खोलें';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi ऐप आपके Apple Watch पर इंस्टॉल है। इसे खोलें और शुरू करने के लिए Start पर टैप करें।';

  @override
  String get openWatchApp => 'Watch ऐप खोलें';

  @override
  String get iveInstalledAndOpenedTheApp => 'मैंने ऐप इंस्टॉल और खोल लिया है';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch ऐप खोलने में असमर्थ। कृपया अपने Apple Watch पर Watch ऐप मैन्युअल रूप से खोलें और \"उपलब्ध ऐप्स\" सेक्शन से Omi इंस्टॉल करें।';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch सफलतापूर्वक कनेक्ट हो गया!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch अभी भी पहुंच योग्य नहीं है। कृपया सुनिश्चित करें कि Omi ऐप आपकी घड़ी पर खुला है।';

  @override
  String errorCheckingConnection(String error) {
    return 'कनेक्शन जाँचने में त्रुटि: $error';
  }

  @override
  String get muted => 'म्यूट';

  @override
  String get processNow => 'अभी प्रोसेस करें';

  @override
  String get finishedConversation => 'बातचीत समाप्त?';

  @override
  String get stopRecordingConfirmation => 'क्या आप वाकई रिकॉर्डिंग रोकना और बातचीत का सारांश अभी बनाना चाहते हैं?';

  @override
  String get conversationEndsManually => 'बातचीत केवल मैन्युअल रूप से समाप्त होगी।';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'बातचीत $minutes मिनट$suffix की चुप्पी के बाद सारांशित होती है।';
  }

  @override
  String get dontAskAgain => 'मुझसे दोबारा मत पूछो';

  @override
  String get waitingForTranscriptOrPhotos => 'ट्रांसक्रिप्ट या फ़ोटो की प्रतीक्षा...';

  @override
  String get noSummaryYet => 'अभी तक कोई सारांश नहीं';

  @override
  String hints(String text) {
    return 'संकेत: $text';
  }

  @override
  String get testConversationPrompt => 'बातचीत प्रॉम्प्ट टेस्ट करें';

  @override
  String get prompt => 'प्रॉम्प्ट';

  @override
  String get result => 'परिणाम:';

  @override
  String get compareTranscripts => 'ट्रांसक्रिप्ट की तुलना करें';

  @override
  String get notHelpful => 'सहायक नहीं';

  @override
  String get exportTasksWithOneTap => 'एक टैप से कार्य निर्यात करें!';

  @override
  String get inProgress => 'प्रगति में';

  @override
  String get photos => 'फ़ोटो';

  @override
  String get rawData => 'कच्चा डेटा';

  @override
  String get content => 'सामग्री';

  @override
  String get noContentToDisplay => 'दिखाने के लिए कोई सामग्री नहीं';

  @override
  String get noSummary => 'कोई सारांश नहीं';

  @override
  String get updateOmiFirmware => 'omi फर्मवेयर अपडेट करें';

  @override
  String get anErrorOccurredTryAgain => 'एक त्रुटि हुई। कृपया पुनः प्रयास करें।';

  @override
  String get welcomeBackSimple => 'वापसी पर स्वागत है';

  @override
  String get addVocabularyDescription => 'ऐसे शब्द जोड़ें जिन्हें Omi को ट्रांसक्रिप्शन के दौरान पहचानना चाहिए।';

  @override
  String get enterWordsCommaSeparated => 'शब्द दर्ज करें (अल्पविराम से अलग)';

  @override
  String get whenToReceiveDailySummary => 'अपना दैनिक सारांश कब प्राप्त करें';

  @override
  String get checkingNextSevenDays => 'अगले 7 दिनों की जाँच';

  @override
  String failedToDeleteError(String error) {
    return 'हटाने में विफल: $error';
  }

  @override
  String get developerApiKeys => 'डेवलपर API कुंजियाँ';

  @override
  String get noApiKeysCreateOne => 'कोई API कुंजी नहीं। शुरू करने के लिए एक बनाएं।';

  @override
  String get commandRequired => '⌘ आवश्यक है';

  @override
  String get spaceKey => 'स्पेस';

  @override
  String loadMoreRemaining(String count) {
    return 'और लोड करें ($count शेष)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'शीर्ष $percentile% उपयोगकर्ता';
  }

  @override
  String get wrappedMinutes => 'मिनट';

  @override
  String get wrappedConversations => 'बातचीत';

  @override
  String get wrappedDaysActive => 'सक्रिय दिन';

  @override
  String get wrappedYouTalkedAbout => 'आपने बात की';

  @override
  String get wrappedActionItems => 'कार्य';

  @override
  String get wrappedTasksCreated => 'बनाए गए कार्य';

  @override
  String get wrappedCompleted => 'पूर्ण';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% पूर्णता दर';
  }

  @override
  String get wrappedYourTopDays => 'आपके शीर्ष दिन';

  @override
  String get wrappedBestMoments => 'सर्वश्रेष्ठ पल';

  @override
  String get wrappedMyBuddies => 'मेरे दोस्त';

  @override
  String get wrappedCouldntStopTalkingAbout => 'बात करना बंद नहीं कर सका';

  @override
  String get wrappedShow => 'शो';

  @override
  String get wrappedMovie => 'फिल्म';

  @override
  String get wrappedBook => 'किताब';

  @override
  String get wrappedCelebrity => 'सेलिब्रिटी';

  @override
  String get wrappedFood => 'खाना';

  @override
  String get wrappedMovieRecs => 'दोस्तों के लिए फिल्म सुझाव';

  @override
  String get wrappedBiggest => 'सबसे बड़ी';

  @override
  String get wrappedStruggle => 'चुनौती';

  @override
  String get wrappedButYouPushedThrough => 'लेकिन आपने कर दिखाया 💪';

  @override
  String get wrappedWin => 'जीत';

  @override
  String get wrappedYouDidIt => 'आपने कर दिखाया! 🎉';

  @override
  String get wrappedTopPhrases => 'शीर्ष 5 वाक्य';

  @override
  String get wrappedMins => 'मिनट';

  @override
  String get wrappedConvos => 'बातचीत';

  @override
  String get wrappedDays => 'दिन';

  @override
  String get wrappedMyBuddiesLabel => 'मेरे दोस्त';

  @override
  String get wrappedObsessionsLabel => 'जुनून';

  @override
  String get wrappedStruggleLabel => 'चुनौती';

  @override
  String get wrappedWinLabel => 'जीत';

  @override
  String get wrappedTopPhrasesLabel => 'शीर्ष वाक्य';

  @override
  String get wrappedLetsHitRewind => 'चलो आपके साल को रिवाइंड करें';

  @override
  String get wrappedGenerateMyWrapped => 'मेरा Wrapped बनाएं';

  @override
  String get wrappedProcessingDefault => 'प्रोसेसिंग...';

  @override
  String get wrappedCreatingYourStory => 'आपकी\n2025 कहानी बना रहे हैं...';

  @override
  String get wrappedSomethingWentWrong => 'कुछ गड़बड़\nहो गई';

  @override
  String get wrappedAnErrorOccurred => 'एक त्रुटि हुई';

  @override
  String get wrappedTryAgain => 'फिर से कोशिश करें';

  @override
  String get wrappedNoDataAvailable => 'कोई डेटा उपलब्ध नहीं';

  @override
  String get wrappedOmiLifeRecap => 'Omi लाइफ रीकैप';

  @override
  String get wrappedSwipeUpToBegin => 'शुरू करने के लिए ऊपर स्वाइप करें';

  @override
  String get wrappedShareText => 'मेरा 2025, Omi द्वारा याद किया गया ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'शेयर करने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get wrappedFailedToStartGeneration => 'जनरेशन शुरू करने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get wrappedStarting => 'शुरू हो रहा है...';

  @override
  String get wrappedShare => 'शेयर करें';

  @override
  String get wrappedShareYourWrapped => 'अपना Wrapped शेयर करें';

  @override
  String get wrappedMy2025 => 'मेरा 2025';

  @override
  String get wrappedRememberedByOmi => 'Omi द्वारा याद किया गया';

  @override
  String get wrappedMostFunDay => 'सबसे मजेदार';

  @override
  String get wrappedMostProductiveDay => 'सबसे उत्पादक';

  @override
  String get wrappedMostIntenseDay => 'सबसे तीव्र';

  @override
  String get wrappedFunniestMoment => 'सबसे हास्यास्पद';

  @override
  String get wrappedMostCringeMoment => 'सबसे शर्मनाक';

  @override
  String get wrappedMinutesLabel => 'मिनट';

  @override
  String get wrappedConversationsLabel => 'बातचीत';

  @override
  String get wrappedDaysActiveLabel => 'सक्रिय दिन';

  @override
  String get wrappedTasksGenerated => 'कार्य बनाए गए';

  @override
  String get wrappedTasksCompleted => 'कार्य पूरे किए';

  @override
  String get wrappedTopFivePhrases => 'टॉप 5 फ्रेज';

  @override
  String get wrappedAGreatDay => 'एक शानदार दिन';

  @override
  String get wrappedGettingItDone => 'काम पूरा करना';

  @override
  String get wrappedAChallenge => 'एक चुनौती';

  @override
  String get wrappedAHilariousMoment => 'एक मजेदार पल';

  @override
  String get wrappedThatAwkwardMoment => 'वो अजीब पल';

  @override
  String get wrappedYouHadFunnyMoments => 'इस साल आपके मजेदार पल रहे!';

  @override
  String get wrappedWeveAllBeenThere => 'हम सब वहाँ रहे हैं!';

  @override
  String get wrappedFriend => 'दोस्त';

  @override
  String get wrappedYourBuddy => 'आपका दोस्त!';

  @override
  String get wrappedNotMentioned => 'उल्लेख नहीं';

  @override
  String get wrappedTheHardPart => 'कठिन भाग';

  @override
  String get wrappedPersonalGrowth => 'व्यक्तिगत विकास';

  @override
  String get wrappedFunDay => 'मजेदार';

  @override
  String get wrappedProductiveDay => 'उत्पादक';

  @override
  String get wrappedIntenseDay => 'तीव्र';

  @override
  String get wrappedFunnyMomentTitle => 'मजेदार पल';

  @override
  String get wrappedCringeMomentTitle => 'शर्मनाक पल';

  @override
  String get wrappedYouTalkedAboutBadge => 'आपने बात की';

  @override
  String get wrappedCompletedLabel => 'पूर्ण';

  @override
  String get wrappedMyBuddiesCard => 'मेरे दोस्त';

  @override
  String get wrappedBuddiesLabel => 'दोस्त';

  @override
  String get wrappedObsessionsLabelUpper => 'जुनून';

  @override
  String get wrappedStruggleLabelUpper => 'संघर्ष';

  @override
  String get wrappedWinLabelUpper => 'जीत';

  @override
  String get wrappedTopPhrasesLabelUpper => 'टॉप फ्रेज';

  @override
  String get wrappedYourHeader => 'आपके';

  @override
  String get wrappedTopDaysHeader => 'सर्वश्रेष्ठ दिन';

  @override
  String get wrappedYourTopDaysBadge => 'आपके सर्वश्रेष्ठ दिन';

  @override
  String get wrappedBestHeader => 'सर्वश्रेष्ठ';

  @override
  String get wrappedMomentsHeader => 'पल';

  @override
  String get wrappedBestMomentsBadge => 'सर्वश्रेष्ठ पल';

  @override
  String get wrappedBiggestHeader => 'सबसे बड़ा';

  @override
  String get wrappedStruggleHeader => 'संघर्ष';

  @override
  String get wrappedWinHeader => 'जीत';

  @override
  String get wrappedButYouPushedThroughEmoji => 'लेकिन आपने कर दिखाया 💪';

  @override
  String get wrappedYouDidItEmoji => 'आपने कर लिया! 🎉';

  @override
  String get wrappedHours => 'घंटे';

  @override
  String get wrappedActions => 'कार्य';

  @override
  String get multipleSpeakersDetected => 'कई वक्ता पाए गए';

  @override
  String get multipleSpeakersDescription =>
      'ऐसा लगता है कि रिकॉर्डिंग में कई वक्ता हैं। कृपया सुनिश्चित करें कि आप एक शांत जगह पर हैं और पुनः प्रयास करें।';

  @override
  String get invalidRecordingDetected => 'अमान्य रिकॉर्डिंग पाई गई';

  @override
  String get notEnoughSpeechDescription => 'पर्याप्त भाषण नहीं पाया गया। कृपया अधिक बोलें और पुनः प्रयास करें।';

  @override
  String get speechDurationDescription => 'कृपया सुनिश्चित करें कि आप कम से कम 5 सेकंड और 90 से अधिक नहीं बोलते हैं।';

  @override
  String get connectionLostDescription =>
      'कनेक्शन बाधित हो गया था। कृपया अपना इंटरनेट कनेक्शन जांचें और पुनः प्रयास करें।';

  @override
  String get howToTakeGoodSample => 'एक अच्छा नमूना कैसे लें?';

  @override
  String get goodSampleInstructions =>
      '1. सुनिश्चित करें कि आप एक शांत जगह पर हैं।\n2. स्पष्ट और स्वाभाविक रूप से बोलें।\n3. सुनिश्चित करें कि आपका उपकरण आपकी गर्दन पर अपनी प्राकृतिक स्थिति में है।\n\nएक बार बन जाने के बाद, आप इसे हमेशा सुधार सकते हैं या फिर से कर सकते हैं।';

  @override
  String get noDeviceConnectedUseMic => 'कोई उपकरण कनेक्ट नहीं है। फोन माइक्रोफोन का उपयोग किया जाएगा।';

  @override
  String get doItAgain => 'फिर से करें';

  @override
  String get listenToSpeechProfile => 'मेरी वॉइस प्रोफ़ाइल सुनें ➡️';

  @override
  String get recognizingOthers => 'दूसरों को पहचानना 👀';

  @override
  String get keepGoingGreat => 'जारी रखें, आप बहुत अच्छा कर रहे हैं';

  @override
  String get somethingWentWrongTryAgain => 'कुछ गलत हो गया! कृपया बाद में पुनः प्रयास करें।';

  @override
  String get uploadingVoiceProfile => 'आपकी वॉइस प्रोफाइल अपलोड हो रही है....';

  @override
  String get memorizingYourVoice => 'आपकी आवाज़ याद की जा रही है...';

  @override
  String get personalizingExperience => 'आपका अनुभव व्यक्तिगत किया जा रहा है...';

  @override
  String get keepSpeakingUntil100 => '100% तक पहुंचने तक बोलते रहें।';

  @override
  String get greatJobAlmostThere => 'शानदार काम, आप लगभग वहां हैं';

  @override
  String get soCloseJustLittleMore => 'बस थोड़ा और';

  @override
  String get notificationFrequency => 'सूचना आवृत्ति';

  @override
  String get controlNotificationFrequency => 'नियंत्रित करें कि Omi आपको कितनी बार सक्रिय सूचनाएं भेजता है।';

  @override
  String get yourScore => 'आपका स्कोर';

  @override
  String get dailyScoreBreakdown => 'दैनिक स्कोर विवरण';

  @override
  String get todaysScore => 'आज का स्कोर';

  @override
  String get tasksCompleted => 'कार्य पूर्ण';

  @override
  String get completionRate => 'पूर्णता दर';

  @override
  String get howItWorks => 'यह कैसे काम करता है';

  @override
  String get dailyScoreExplanation =>
      'आपका दैनिक स्कोर कार्य पूर्णता पर आधारित है। अपना स्कोर सुधारने के लिए अपने कार्य पूरे करें!';

  @override
  String get notificationFrequencyDescription =>
      'नियंत्रित करें कि Omi आपको कितनी बार सक्रिय सूचनाएं और अनुस्मारक भेजता है।';

  @override
  String get sliderOff => 'बंद';

  @override
  String get sliderMax => 'अधिकतम';

  @override
  String summaryGeneratedFor(String date) {
    return '$date के लिए सारांश बनाया गया';
  }

  @override
  String get failedToGenerateSummary => 'सारांश बनाने में विफल। सुनिश्चित करें कि उस दिन की बातचीत मौजूद है।';

  @override
  String get recap => 'रीकैप';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" हटाएं';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count बातचीत को यहां ले जाएं:';
  }

  @override
  String get noFolder => 'कोई फ़ोल्डर नहीं';

  @override
  String get removeFromAllFolders => 'सभी फ़ोल्डरों से हटाएं';

  @override
  String get buildAndShareYourCustomApp => 'अपना कस्टम ऐप बनाएं और साझा करें';

  @override
  String get searchAppsPlaceholder => '1500+ ऐप्स में खोजें';

  @override
  String get filters => 'फ़िल्टर';

  @override
  String get frequencyOff => 'बंद';

  @override
  String get frequencyMinimal => 'न्यूनतम';

  @override
  String get frequencyLow => 'कम';

  @override
  String get frequencyBalanced => 'संतुलित';

  @override
  String get frequencyHigh => 'उच्च';

  @override
  String get frequencyMaximum => 'अधिकतम';

  @override
  String get frequencyDescOff => 'कोई सक्रिय सूचनाएं नहीं';

  @override
  String get frequencyDescMinimal => 'केवल महत्वपूर्ण रिमाइंडर';

  @override
  String get frequencyDescLow => 'केवल महत्वपूर्ण अपडेट';

  @override
  String get frequencyDescBalanced => 'नियमित सहायक रिमाइंडर';

  @override
  String get frequencyDescHigh => 'बार-बार जांच';

  @override
  String get frequencyDescMaximum => 'लगातार जुड़े रहें';

  @override
  String get clearChatQuestion => 'चैट साफ करें?';

  @override
  String get syncingMessages => 'सर्वर के साथ संदेश सिंक हो रहे हैं...';

  @override
  String get chatAppsTitle => 'चैट ऐप्स';

  @override
  String get selectApp => 'ऐप चुनें';

  @override
  String get noChatAppsEnabled => 'कोई चैट ऐप सक्षम नहीं है।\nकुछ जोड़ने के लिए \"ऐप्स सक्षम करें\" पर टैप करें।';

  @override
  String get disable => 'अक्षम करें';

  @override
  String get photoLibrary => 'फोटो लाइब्रेरी';

  @override
  String get chooseFile => 'फ़ाइल चुनें';

  @override
  String get configureAiPersona => 'Configure your AI persona';

  @override
  String get connectAiAssistantsToYourData => 'Connect AI assistants to your data';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get deleteRecording => 'Delete Recording';

  @override
  String get thisCannotBeUndone => 'This cannot be undone.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'From SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'फास्ट ट्रांसफर';

  @override
  String get syncingStatus => 'Syncing';

  @override
  String get failedStatus => 'Failed';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'ट्रांसफर विधि';

  @override
  String get fast => 'Fast';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Phone';

  @override
  String get cancelSync => 'Cancel Sync';

  @override
  String get cancelSyncMessage => 'Data already downloaded will be saved. You can resume later.';

  @override
  String get syncCancelled => 'Sync cancelled';

  @override
  String get deleteProcessedFiles => 'Delete Processed Files';

  @override
  String get processedFilesDeleted => 'Processed files deleted';

  @override
  String get wifiEnableFailed => 'Failed to enable WiFi on device. Please try again.';

  @override
  String get deviceNoFastTransfer => 'Your device does not support Fast Transfer. Use Bluetooth instead.';

  @override
  String get enableHotspotMessage => 'Please enable your phone\'s hotspot and try again.';

  @override
  String get transferStartFailed => 'Failed to start transfer. Please try again.';

  @override
  String get deviceNotResponding => 'Device did not respond. Please try again.';

  @override
  String get invalidWifiCredentials => 'Invalid WiFi credentials. Check your hotspot settings.';

  @override
  String get wifiConnectionFailed => 'WiFi connection failed. Please try again.';

  @override
  String get sdCardProcessing => 'SD Card Processing';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Processing $count recording(s). Files will be removed from SD card after.';
  }

  @override
  String get process => 'Process';

  @override
  String get wifiSyncFailed => 'WiFi Sync Failed';

  @override
  String get processingFailed => 'Processing Failed';

  @override
  String get downloadingFromSdCard => 'Downloading from SD Card';

  @override
  String processingProgress(int current, int total) {
    return 'Processing $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count conversations created';
  }

  @override
  String get internetRequired => 'Internet required';

  @override
  String get processAudio => 'Process Audio';

  @override
  String get start => 'Start';

  @override
  String get noRecordings => 'No Recordings';

  @override
  String get audioFromOmiWillAppearHere => 'Audio from your Omi device will appear here';

  @override
  String get deleteProcessed => 'Delete Processed';

  @override
  String get tryDifferentFilter => 'Try a different filter';

  @override
  String get recordings => 'Recordings';

  @override
  String get enableRemindersAccess =>
      'Apple रिमाइंडर का उपयोग करने के लिए कृपया सेटिंग्स में रिमाइंडर एक्सेस सक्षम करें';

  @override
  String todayAtTime(String time) {
    return 'आज $time पर';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'कल $time पर';
  }

  @override
  String get lessThanAMinute => 'एक मिनट से कम';

  @override
  String estimatedMinutes(int count) {
    return '~$count मिनट';
  }

  @override
  String estimatedHours(int count) {
    return '~$count घंटे';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'अनुमानित: $time शेष';
  }

  @override
  String get summarizingConversation => 'बातचीत का सारांश...\nइसमें कुछ सेकंड लग सकते हैं';

  @override
  String get resummarizingConversation => 'बातचीत का पुनः सारांश...\nइसमें कुछ सेकंड लग सकते हैं';

  @override
  String get nothingInterestingRetry => 'कुछ दिलचस्प नहीं मिला,\nक्या आप फिर से कोशिश करना चाहते हैं?';

  @override
  String get noSummaryForConversation => 'इस बातचीत के लिए\nकोई सारांश उपलब्ध नहीं है।';

  @override
  String get unknownLocation => 'अज्ञात स्थान';

  @override
  String get couldNotLoadMap => 'मानचित्र लोड नहीं हो सका';

  @override
  String get triggerConversationIntegration => 'बातचीत निर्माण एकीकरण ट्रिगर करें';

  @override
  String get webhookUrlNotSet => 'Webhook URL सेट नहीं है';

  @override
  String get setWebhookUrlInSettings =>
      'इस सुविधा का उपयोग करने के लिए कृपया डेवलपर सेटिंग्स में webhook URL सेट करें।';

  @override
  String get sendWebUrl => 'वेब URL भेजें';

  @override
  String get sendTranscript => 'प्रतिलिपि भेजें';

  @override
  String get sendSummary => 'सारांश भेजें';

  @override
  String get debugModeDetected => 'डीबग मोड का पता चला';

  @override
  String get performanceReduced => 'प्रदर्शन कम हो सकता है';

  @override
  String autoClosingInSeconds(int seconds) {
    return '$seconds सेकंड में स्वचालित रूप से बंद हो रहा है';
  }

  @override
  String get modelRequired => 'मॉडल आवश्यक';

  @override
  String get downloadWhisperModel => 'डिवाइस पर ट्रांसक्रिप्शन का उपयोग करने के लिए व्हिस्पर मॉडल डाउनलोड करें';

  @override
  String get deviceNotCompatible => 'आपका डिवाइस ऑन-डिवाइस ट्रांसक्रिप्शन के साथ संगत नहीं है';

  @override
  String get deviceRequirements => 'Your device does not meet the requirements for On-Device transcription.';

  @override
  String get willLikelyCrash => 'इसे सक्षम करने से ऐप क्रैश या फ्रीज हो सकता है।';

  @override
  String get transcriptionSlowerLessAccurate => 'ट्रांसक्रिप्शन काफी धीमा और कम सटीक होगा।';

  @override
  String get proceedAnyway => 'फिर भी जारी रखें';

  @override
  String get olderDeviceDetected => 'पुराना डिवाइस पाया गया';

  @override
  String get onDeviceSlower => 'On-device transcription may be slower on this device.';

  @override
  String get batteryUsageHigher => 'बैटरी उपयोग क्लाउड ट्रांसक्रिप्शन से अधिक होगा।';

  @override
  String get considerOmiCloud => 'बेहतर प्रदर्शन के लिए Omi Cloud का उपयोग करने पर विचार करें।';

  @override
  String get highResourceUsage => 'उच्च संसाधन उपयोग';

  @override
  String get onDeviceIntensive => 'On-Device transcription is computationally intensive.';

  @override
  String get batteryDrainIncrease => 'Battery drain will increase significantly.';

  @override
  String get deviceMayWarmUp => 'लंबे समय तक उपयोग के दौरान डिवाइस गर्म हो सकता है।';

  @override
  String get speedAccuracyLower => 'गति और सटीकता क्लाउड मॉडल से कम हो सकती है।';

  @override
  String get cloudProvider => 'क्लाउड प्रदाता';

  @override
  String get premiumMinutesInfo => '1,200 premium minutes/month. On-Device tab offers unlimited free transcription.';

  @override
  String get viewUsage => 'उपयोग देखें';

  @override
  String get localProcessingInfo => 'Audio is processed locally. Works offline, more private, but uses more battery.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'प्रदर्शन चेतावनी';

  @override
  String get largeModelWarning =>
      'This model is large and may crash the app or run very slowly on mobile devices.\n\n\"small\" or \"base\" is recommended.';

  @override
  String get usingNativeIosSpeech => 'मूल iOS स्पीच रिकग्निशन का उपयोग';

  @override
  String get noModelDownloadRequired => 'Your device\'s native speech engine will be used. No model download required.';

  @override
  String get modelReady => 'Model Ready';

  @override
  String get redownload => 'Re-download';

  @override
  String get doNotCloseApp => 'कृपया ऐप बंद न करें।';

  @override
  String get downloading => 'डाउनलोड हो रहा है...';

  @override
  String get downloadModel => 'मॉडल डाउनलोड करें';

  @override
  String estimatedSize(String size) {
    return 'Estimated Size: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Available Space: $space';
  }

  @override
  String get notEnoughSpace => 'चेतावनी: पर्याप्त स्थान नहीं!';

  @override
  String get download => 'डाउनलोड';

  @override
  String downloadError(String error) {
    return 'Download error: $error';
  }

  @override
  String get cancelled => 'रद्द';

  @override
  String get deviceNotCompatibleTitle => 'डिवाइस संगत नहीं है';

  @override
  String get deviceNotMeetRequirements => 'आपका डिवाइस ऑन-डिवाइस ट्रांसक्रिप्शन की आवश्यकताओं को पूरा नहीं करता।';

  @override
  String get transcriptionSlowerOnDevice => 'इस डिवाइस पर ऑन-डिवाइस ट्रांसक्रिप्शन धीमा हो सकता है।';

  @override
  String get computationallyIntensive => 'ऑन-डिवाइस ट्रांसक्रिप्शन कम्प्यूटेशनली गहन है।';

  @override
  String get batteryDrainSignificantly => 'बैटरी की खपत काफी बढ़ जाएगी।';

  @override
  String get premiumMinutesMonth =>
      '1,200 प्रीमियम मिनट/माह। ऑन-डिवाइस टैब असीमित मुफ्त ट्रांसक्रिप्शन प्रदान करता है। ';

  @override
  String get audioProcessedLocally =>
      'ऑडियो स्थानीय रूप से संसाधित होता है। ऑफ़लाइन काम करता है, अधिक निजी, लेकिन अधिक बैटरी उपयोग करता है।';

  @override
  String get languageLabel => 'भाषा';

  @override
  String get modelLabel => 'मॉडल';

  @override
  String get modelTooLargeWarning =>
      'यह मॉडल बड़ा है और मोबाइल डिवाइस पर ऐप क्रैश या बहुत धीमा हो सकता है।\n\nsmall या base की सिफारिश की जाती है।';

  @override
  String get nativeEngineNoDownload => 'आपके डिवाइस का मूल स्पीच इंजन उपयोग किया जाएगा। मॉडल डाउनलोड की आवश्यकता नहीं।';

  @override
  String modelReadyWithName(String model) {
    return 'मॉडल तैयार ($model)';
  }

  @override
  String get reDownload => 'पुनः डाउनलोड';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model डाउनलोड हो रहा है: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model तैयार हो रहा है...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'डाउनलोड त्रुटि: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'अनुमानित आकार: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'उपलब्ध स्थान: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omi की अंतर्निहित लाइव ट्रांसक्रिप्शन स्वचालित स्पीकर डिटेक्शन और डायराइज़ेशन के साथ रियल-टाइम वार्तालाप के लिए अनुकूलित है।';

  @override
  String get reset => 'रीसेट';

  @override
  String get useTemplateFrom => 'टेम्पलेट का उपयोग करें';

  @override
  String get selectProviderTemplate => 'प्रदाता टेम्पलेट चुनें...';

  @override
  String get quicklyPopulateResponse => 'ज्ञात प्रदाता प्रतिक्रिया प्रारूप से जल्दी भरें';

  @override
  String get quicklyPopulateRequest => 'ज्ञात प्रदाता अनुरोध प्रारूप से जल्दी भरें';

  @override
  String get invalidJsonError => 'अमान्य JSON';

  @override
  String downloadModelWithName(String model) {
    return 'मॉडल डाउनलोड करें ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'मॉडल: $model';
  }

  @override
  String get device => 'Device';

  @override
  String get chatAssistantsTitle => 'चैट सहायक';

  @override
  String get permissionReadConversations => 'बातचीत पढ़ें';

  @override
  String get permissionReadMemories => 'यादें पढ़ें';

  @override
  String get permissionReadTasks => 'कार्य पढ़ें';

  @override
  String get permissionCreateConversations => 'बातचीत बनाएं';

  @override
  String get permissionCreateMemories => 'यादें बनाएं';

  @override
  String get permissionTypeAccess => 'पहुंच';

  @override
  String get permissionTypeCreate => 'बनाएं';

  @override
  String get permissionTypeTrigger => 'ट्रिगर';

  @override
  String get permissionDescReadConversations => 'यह ऐप आपकी बातचीत तक पहुंच सकता है।';

  @override
  String get permissionDescReadMemories => 'यह ऐप आपकी यादों तक पहुंच सकता है।';

  @override
  String get permissionDescReadTasks => 'यह ऐप आपके कार्यों तक पहुंच सकता है।';

  @override
  String get permissionDescCreateConversations => 'यह ऐप नई बातचीत बना सकता है।';

  @override
  String get permissionDescCreateMemories => 'यह ऐप नई यादें बना सकता है।';

  @override
  String get realtimeListening => 'रीयलटाइम सुनना';

  @override
  String get setupCompleted => 'पूर्ण';

  @override
  String get pleaseSelectRating => 'कृपया रेटिंग चुनें';

  @override
  String get writeReviewOptional => 'समीक्षा लिखें (वैकल्पिक)';

  @override
  String get setupQuestionsIntro => 'Help us improve Omi by answering a few questions.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. What do you do?';

  @override
  String get setupQuestionUsage => '2. Where do you plan to use your Omi?';

  @override
  String get setupQuestionAge => '3. What\'s your age range?';

  @override
  String get setupAnswerAllQuestions => 'You haven\'t answered all the questions yet! 🥺';

  @override
  String get setupSkipHelp => 'Skip, I don\'t want to help :C';

  @override
  String get professionEntrepreneur => 'Entrepreneur';

  @override
  String get professionSoftwareEngineer => 'Software Engineer';

  @override
  String get professionProductManager => 'Product Manager';

  @override
  String get professionExecutive => 'Executive';

  @override
  String get professionSales => 'Sales';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'At work';

  @override
  String get usageIrlEvents => 'IRL Events';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'In Social Settings';

  @override
  String get usageEverywhere => 'Everywhere';

  @override
  String get customBackendUrlTitle => 'कस्टम बैकएंड URL';

  @override
  String get backendUrlLabel => 'बैकएंड URL';

  @override
  String get saveUrlButton => 'URL सहेजें';

  @override
  String get enterBackendUrlError => 'कृपया बैकएंड URL दर्ज करें';

  @override
  String get urlMustEndWithSlashError => 'URL \"/\" से समाप्त होना चाहिए';

  @override
  String get invalidUrlError => 'कृपया एक वैध URL दर्ज करें';

  @override
  String get backendUrlSavedSuccess => 'बैकएंड URL सफलतापूर्वक सहेजा गया!';

  @override
  String get signInTitle => 'साइन इन करें';

  @override
  String get signInButton => 'साइन इन करें';

  @override
  String get enterEmailError => 'कृपया अपना ईमेल दर्ज करें';

  @override
  String get invalidEmailError => 'कृपया एक वैध ईमेल दर्ज करें';

  @override
  String get enterPasswordError => 'कृपया अपना पासवर्ड दर्ज करें';

  @override
  String get passwordMinLengthError => 'पासवर्ड कम से कम 8 अक्षरों का होना चाहिए';

  @override
  String get signInSuccess => 'साइन इन सफल!';

  @override
  String get alreadyHaveAccountLogin => 'पहले से खाता है? लॉग इन करें';

  @override
  String get emailLabel => 'ईमेल';

  @override
  String get passwordLabel => 'पासवर्ड';

  @override
  String get createAccountTitle => 'खाता बनाएं';

  @override
  String get nameLabel => 'नाम';

  @override
  String get repeatPasswordLabel => 'पासवर्ड दोहराएं';

  @override
  String get signUpButton => 'साइन अप करें';

  @override
  String get enterNameError => 'कृपया अपना नाम दर्ज करें';

  @override
  String get passwordsDoNotMatch => 'पासवर्ड मेल नहीं खाते';

  @override
  String get signUpSuccess => 'साइन अप सफल!';

  @override
  String get loadingKnowledgeGraph => 'ज्ञान ग्राफ़ लोड हो रहा है...';

  @override
  String get noKnowledgeGraphYet => 'अभी तक कोई ज्ञान ग्राफ़ नहीं';

  @override
  String get buildingKnowledgeGraphFromMemories => 'यादों से ज्ञान ग्राफ़ बनाया जा रहा है...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'जब आप नई यादें बनाएंगे तो आपका ज्ञान ग्राफ़ स्वचालित रूप से बनेगा।';

  @override
  String get buildGraphButton => 'ग्राफ़ बनाएं';

  @override
  String get checkOutMyMemoryGraph => 'मेरा मेमोरी ग्राफ़ देखें!';

  @override
  String get getButton => 'प्राप्त करें';

  @override
  String openingApp(String appName) {
    return '$appName खुल रहा है...';
  }

  @override
  String get writeSomething => 'कुछ लिखें';

  @override
  String get submitReply => 'जवाब भेजें';

  @override
  String get editYourReply => 'अपना जवाब संपादित करें';

  @override
  String get replyToReview => 'समीक्षा का जवाब दें';

  @override
  String get rateAndReviewThisApp => 'इस ऐप को रेट और समीक्षा करें';

  @override
  String get noChangesInReview => 'समीक्षा में अपडेट करने के लिए कोई बदलाव नहीं।';

  @override
  String get cantRateWithoutInternet => 'इंटरनेट कनेक्शन के बिना ऐप को रेट नहीं कर सकते।';

  @override
  String get appAnalytics => 'ऐप एनालिटिक्स';

  @override
  String get learnMoreLink => 'अधिक जानें';

  @override
  String get moneyEarned => 'कमाई';

  @override
  String get writeYourReply => 'Write your reply...';

  @override
  String get replySentSuccessfully => 'Reply sent successfully';

  @override
  String failedToSendReply(String error) {
    return 'Failed to send reply: $error';
  }

  @override
  String get send => 'Send';

  @override
  String starFilter(int count) {
    return '$count Star';
  }

  @override
  String get noReviewsFound => 'No Reviews Found';

  @override
  String get editReply => 'Edit Reply';

  @override
  String get reply => 'Reply';

  @override
  String starFilterLabel(int count) {
    return '$count सितारा';
  }

  @override
  String get sharePublicLink => 'Share Public Link';

  @override
  String get makePersonaPublic => 'Make Persona Public';

  @override
  String get connectedKnowledgeData => 'Connected Knowledge Data';

  @override
  String get enterName => 'Enter name';

  @override
  String get disconnectTwitter => 'Disconnect Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Are you sure you want to disconnect your Twitter account? Your persona will no longer have access to your Twitter data.';

  @override
  String get getOmiDeviceDescription => 'Create a more accurate clone with your personal conversations';

  @override
  String get getOmi => 'Get Omi';

  @override
  String get iHaveOmiDevice => 'I have Omi device';

  @override
  String get goal => 'लक्ष्य';

  @override
  String get tapToTrackThisGoal => 'इस लक्ष्य को ट्रैक करने के लिए टैप करें';

  @override
  String get tapToSetAGoal => 'लक्ष्य सेट करने के लिए टैप करें';

  @override
  String get processedConversations => 'संसाधित वार्तालाप';

  @override
  String get updatedConversations => 'अपडेट की गई वार्तालाप';

  @override
  String get newConversations => 'नई वार्तालाप';

  @override
  String get summaryTemplate => 'सारांश टेम्पलेट';

  @override
  String get suggestedTemplates => 'सुझाए गए टेम्पलेट';

  @override
  String get otherTemplates => 'अन्य टेम्पलेट';

  @override
  String get availableTemplates => 'उपलब्ध टेम्पलेट';

  @override
  String get getCreative => 'रचनात्मक बनें';

  @override
  String get defaultLabel => 'डिफ़ॉल्ट';

  @override
  String get lastUsedLabel => 'अंतिम उपयोग';

  @override
  String get setDefaultApp => 'डिफ़ॉल्ट ऐप सेट करें';

  @override
  String setDefaultAppContent(String appName) {
    return 'क्या $appName को आपके डिफ़ॉल्ट सारांश ऐप के रूप में सेट करें?\\n\\nइस ऐप का उपयोग स्वचालित रूप से सभी भविष्य की बातचीत के सारांश के लिए किया जाएगा।';
  }

  @override
  String get setDefaultButton => 'डिफ़ॉल्ट सेट करें';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName को डिफ़ॉल्ट सारांश ऐप के रूप में सेट किया गया';
  }

  @override
  String get createCustomTemplate => 'कस्टम टेम्पलेट बनाएं';

  @override
  String get allTemplates => 'सभी टेम्पलेट';

  @override
  String failedToInstallApp(String appName) {
    return '$appName इंस्टॉल करने में विफल। कृपया पुनः प्रयास करें।';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appName इंस्टॉल करने में त्रुटि: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Tag Speaker $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'A person with this name already exists.';

  @override
  String get selectYouFromList => 'To tag yourself, please select \"You\" from the list.';

  @override
  String get enterPersonsName => 'Enter Person\'s Name';

  @override
  String get addPerson => 'Add Person';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Tag other segments from this speaker ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Tag other segments';

  @override
  String get managePeople => 'Manage People';

  @override
  String get shareViaSms => 'SMS के माध्यम से साझा करें';

  @override
  String get selectContactsToShareSummary => 'अपनी बातचीत का सारांश साझा करने के लिए संपर्क चुनें';

  @override
  String get searchContactsHint => 'संपर्क खोजें...';

  @override
  String contactsSelectedCount(int count) {
    return '$count चयनित';
  }

  @override
  String get clearAllSelection => 'सभी साफ करें';

  @override
  String get selectContactsToShare => 'साझा करने के लिए संपर्क चुनें';

  @override
  String shareWithContactCount(int count) {
    return '$count संपर्क के साथ साझा करें';
  }

  @override
  String shareWithContactsCount(int count) {
    return '$count संपर्कों के साथ साझा करें';
  }

  @override
  String get contactsPermissionRequired => 'संपर्क अनुमति आवश्यक है';

  @override
  String get contactsPermissionRequiredForSms => 'SMS के माध्यम से साझा करने के लिए संपर्क अनुमति आवश्यक है';

  @override
  String get grantContactsPermissionForSms => 'कृपया SMS के माध्यम से साझा करने के लिए संपर्क अनुमति दें';

  @override
  String get noContactsWithPhoneNumbers => 'फ़ोन नंबर वाला कोई संपर्क नहीं मिला';

  @override
  String get noContactsMatchSearch => 'कोई संपर्क आपकी खोज से मेल नहीं खाता';

  @override
  String get failedToLoadContacts => 'संपर्क लोड करने में विफल';

  @override
  String get failedToPrepareConversationForSharing =>
      'साझा करने के लिए बातचीत तैयार करने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get couldNotOpenSmsApp => 'SMS ऐप नहीं खोला जा सका। कृपया पुनः प्रयास करें।';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'यहाँ हमने अभी जो चर्चा की वह है: $link';
  }

  @override
  String get wifiSync => 'वाईफाई सिंक';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item क्लिपबोर्ड पर कॉपी किया गया';
  }

  @override
  String get wifiConnectionFailedTitle => 'Connection Failed';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Connecting to $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Enable $deviceName\'s WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Connect to $deviceName';
  }

  @override
  String get recordingDetails => 'Recording Details';

  @override
  String get storageLocationSdCard => 'SD Card';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Phone';

  @override
  String get storageLocationPhoneMemory => 'Phone (Memory)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Stored on $deviceName';
  }

  @override
  String get transferring => 'Transferring...';

  @override
  String get transferRequired => 'Transfer Required';

  @override
  String get downloadingAudioFromSdCard => 'Downloading audio from your device\'s SD card';

  @override
  String get transferRequiredDescription =>
      'This recording is stored on your device\'s SD card. Transfer it to your phone to play or share.';

  @override
  String get cancelTransfer => 'Cancel Transfer';

  @override
  String get transferToPhone => 'Transfer to Phone';

  @override
  String get privateAndSecureOnDevice => 'Private & secure on your device';

  @override
  String get recordingInfo => 'Recording Info';

  @override
  String get transferInProgress => 'Transfer in progress...';

  @override
  String get shareRecording => 'Share Recording';

  @override
  String get deleteRecordingConfirmation =>
      'Are you sure you want to permanently delete this recording? This can\'t be undone.';

  @override
  String get recordingIdLabel => 'Recording ID';

  @override
  String get dateTimeLabel => 'Date & Time';

  @override
  String get durationLabel => 'Duration';

  @override
  String get audioFormatLabel => 'Audio Format';

  @override
  String get storageLocationLabel => 'Storage Location';

  @override
  String get estimatedSizeLabel => 'Estimated Size';

  @override
  String get deviceModelLabel => 'Device Model';

  @override
  String get deviceIdLabel => 'Device ID';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Processed';

  @override
  String get statusUnprocessed => 'Unprocessed';

  @override
  String get switchedToFastTransfer => 'Switched to Fast Transfer';

  @override
  String get transferCompleteMessage => 'Transfer complete! You can now play this recording.';

  @override
  String transferFailedMessage(String error) {
    return 'Transfer failed: $error';
  }

  @override
  String get transferCancelled => 'Transfer cancelled';

  @override
  String get fastTransferEnabled => 'फास्ट ट्रांसफर सक्षम';

  @override
  String get bluetoothSyncEnabled => 'ब्लूटूथ सिंक सक्षम';

  @override
  String get enableFastTransfer => 'फास्ट ट्रांसफर सक्षम करें';

  @override
  String get fastTransferDescription =>
      'फास्ट ट्रांसफर ~5x तेज गति के लिए WiFi का उपयोग करता है। ट्रांसफर के दौरान आपका फोन अस्थायी रूप से आपके Omi डिवाइस के WiFi नेटवर्क से कनेक्ट होगा।';

  @override
  String get internetAccessPausedDuringTransfer => 'ट्रांसफर के दौरान इंटरनेट एक्सेस रुका हुआ है';

  @override
  String get chooseTransferMethodDescription =>
      'चुनें कि आपके Omi डिवाइस से आपके फोन में रिकॉर्डिंग कैसे ट्रांसफर की जाएं।';

  @override
  String get wifiSpeed => '~150 KB/s WiFi के माध्यम से';

  @override
  String get fiveTimesFaster => '5X तेज';

  @override
  String get fastTransferMethodDescription =>
      'आपके Omi डिवाइस से सीधा WiFi कनेक्शन बनाता है। ट्रांसफर के दौरान आपका फोन अस्थायी रूप से आपके सामान्य WiFi से डिस्कनेक्ट हो जाता है।';

  @override
  String get bluetooth => 'ब्लूटूथ';

  @override
  String get bleSpeed => '~30 KB/s BLE के माध्यम से';

  @override
  String get bluetoothMethodDescription =>
      'मानक ब्लूटूथ लो एनर्जी कनेक्शन का उपयोग करता है। धीमा लेकिन आपके WiFi कनेक्शन को प्रभावित नहीं करता।';

  @override
  String get selected => 'चयनित';

  @override
  String get selectOption => 'चुनें';

  @override
  String get lowBatteryAlertTitle => 'कम बैटरी अलर्ट';

  @override
  String get lowBatteryAlertBody => 'आपके डिवाइस की बैटरी कम है। रिचार्ज करने का समय! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'आपका Omi डिवाइस डिस्कनेक्ट हो गया';

  @override
  String get deviceDisconnectedNotificationBody => 'कृपया Omi का उपयोग जारी रखने के लिए पुनः कनेक्ट करें।';

  @override
  String get firmwareUpdateAvailable => 'फर्मवेयर अपडेट उपलब्ध';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'आपके Omi डिवाइस के लिए एक नया फर्मवेयर अपडेट ($version) उपलब्ध है। क्या आप अभी अपडेट करना चाहते हैं?';
  }

  @override
  String get later => 'बाद में';

  @override
  String get appDeletedSuccessfully => 'ऐप सफलतापूर्वक हटा दिया गया';

  @override
  String get appDeleteFailed => 'ऐप हटाने में विफल। कृपया बाद में पुन: प्रयास करें।';

  @override
  String get appVisibilityChangedSuccessfully =>
      'ऐप दृश्यता सफलतापूर्वक बदल दी गई। प्रतिबिंबित होने में कुछ मिनट लग सकते हैं।';

  @override
  String get errorActivatingAppIntegration =>
      'ऐप सक्रिय करने में त्रुटि। यदि यह एकीकरण ऐप है, तो सुनिश्चित करें कि सेटअप पूरा हो गया है।';

  @override
  String get errorUpdatingAppStatus => 'ऐप स्थिति अपडेट करते समय एक त्रुटि हुई।';

  @override
  String get calculatingETA => 'Calculating...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'About $minutes minutes remaining';
  }

  @override
  String get aboutAMinuteRemaining => 'About a minute remaining';

  @override
  String get almostDone => 'Almost done...';

  @override
  String get omiSays => 'omi says';

  @override
  String get analyzingYourData => 'Analyzing your data...';

  @override
  String migratingToProtection(String level) {
    return 'Migrating to $level protection...';
  }

  @override
  String get noDataToMigrateFinalizing => 'No data to migrate. Finalizing...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrating $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'All objects migrated. Finalizing...';

  @override
  String get migrationErrorOccurred => 'An error occurred during migration. Please try again.';

  @override
  String get migrationComplete => 'Migration complete!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Your data is now protected with the new $level settings.';
  }

  @override
  String get chatsLowercase => 'chats';

  @override
  String get dataLowercase => 'data';

  @override
  String get fallNotificationTitle => 'Ouch';

  @override
  String get fallNotificationBody => 'Did you fall?';

  @override
  String get importantConversationTitle => 'महत्वपूर्ण बातचीत';

  @override
  String get importantConversationBody => 'आपकी अभी एक महत्वपूर्ण बातचीत हुई। सारांश साझा करने के लिए टैप करें।';

  @override
  String get templateName => 'टेम्पलेट नाम';

  @override
  String get templateNameHint => 'उदा. मीटिंग एक्शन आइटम एक्सट्रैक्टर';

  @override
  String get nameMustBeAtLeast3Characters => 'नाम कम से कम 3 अक्षर का होना चाहिए';

  @override
  String get conversationPromptHint => 'उदा., दी गई बातचीत से एक्शन आइटम, लिए गए निर्णय और मुख्य बिंदु निकालें।';

  @override
  String get pleaseEnterAppPrompt => 'कृपया अपने ऐप के लिए एक प्रॉम्प्ट दर्ज करें';

  @override
  String get promptMustBeAtLeast10Characters => 'प्रॉम्प्ट कम से कम 10 अक्षर का होना चाहिए';

  @override
  String get anyoneCanDiscoverTemplate => 'कोई भी आपका टेम्पलेट खोज सकता है';

  @override
  String get onlyYouCanUseTemplate => 'केवल आप इस टेम्पलेट का उपयोग कर सकते हैं';

  @override
  String get generatingDescription => 'विवरण जनरेट हो रहा है...';

  @override
  String get creatingAppIcon => 'ऐप आइकन बनाया जा रहा है...';

  @override
  String get installingApp => 'ऐप इंस्टॉल हो रहा है...';

  @override
  String get appCreatedAndInstalled => 'ऐप बनाया और इंस्टॉल किया गया!';

  @override
  String get appCreatedSuccessfully => 'ऐप सफलतापूर्वक बनाया गया!';

  @override
  String get failedToCreateApp => 'ऐप बनाने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get addAppSelectCoreCapability => 'कृपया अपने ऐप के लिए एक और मुख्य क्षमता चुनें';

  @override
  String get addAppSelectPaymentPlan => 'कृपया भुगतान योजना चुनें और अपने ऐप के लिए कीमत दर्ज करें';

  @override
  String get addAppSelectCapability => 'कृपया अपने ऐप के लिए कम से कम एक क्षमता चुनें';

  @override
  String get addAppSelectLogo => 'कृपया अपने ऐप के लिए एक लोगो चुनें';

  @override
  String get addAppEnterChatPrompt => 'कृपया अपने ऐप के लिए चैट प्रॉम्प्ट दर्ज करें';

  @override
  String get addAppEnterConversationPrompt => 'कृपया अपने ऐप के लिए वार्तालाप प्रॉम्प्ट दर्ज करें';

  @override
  String get addAppSelectTriggerEvent => 'कृपया अपने ऐप के लिए ट्रिगर इवेंट चुनें';

  @override
  String get addAppEnterWebhookUrl => 'कृपया अपने ऐप के लिए वेबहुक URL दर्ज करें';

  @override
  String get addAppSelectCategory => 'कृपया अपने ऐप के लिए एक श्रेणी चुनें';

  @override
  String get addAppFillRequiredFields => 'कृपया सभी आवश्यक फ़ील्ड सही ढंग से भरें';

  @override
  String get addAppUpdatedSuccess => 'ऐप सफलतापूर्वक अपडेट हुआ 🚀';

  @override
  String get addAppUpdateFailed => 'अपडेट विफल। कृपया बाद में पुनः प्रयास करें';

  @override
  String get addAppSubmittedSuccess => 'ऐप सफलतापूर्वक सबमिट हुआ 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'फ़ाइल पिकर खोलने में त्रुटि: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'छवि चुनने में त्रुटि: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'फ़ोटो अनुमति अस्वीकृत। कृपया फ़ोटो एक्सेस की अनुमति दें';

  @override
  String get addAppErrorSelectingImageRetry => 'छवि चुनने में त्रुटि। कृपया पुनः प्रयास करें।';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'थंबनेल चुनने में त्रुटि: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'थंबनेल चुनने में त्रुटि। कृपया पुनः प्रयास करें।';

  @override
  String get addAppCapabilityConflictWithPersona => 'पर्सोना के साथ अन्य क्षमताएं नहीं चुनी जा सकतीं';

  @override
  String get addAppPersonaConflictWithCapabilities => 'पर्सोना को अन्य क्षमताओं के साथ नहीं चुना जा सकता';

  @override
  String get personaTwitterHandleNotFound => 'Twitter हैंडल नहीं मिला';

  @override
  String get personaTwitterHandleSuspended => 'Twitter हैंडल निलंबित है';

  @override
  String get personaFailedToVerifyTwitter => 'Twitter हैंडल सत्यापन विफल';

  @override
  String get personaFailedToFetch => 'आपका पर्सोना प्राप्त करने में विफल';

  @override
  String get personaFailedToCreate => 'पर्सोना बनाने में विफल';

  @override
  String get personaConnectKnowledgeSource => 'कृपया कम से कम एक डेटा स्रोत कनेक्ट करें (Omi या Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'पर्सोना सफलतापूर्वक अपडेट हुआ';

  @override
  String get personaFailedToUpdate => 'पर्सोना अपडेट विफल';

  @override
  String get personaPleaseSelectImage => 'कृपया एक छवि चुनें';

  @override
  String get personaFailedToCreateTryLater => 'पर्सोना बनाने में विफल। कृपया बाद में पुनः प्रयास करें।';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'पर्सोना बनाने में विफल: $error';
  }

  @override
  String get personaFailedToEnable => 'पर्सोना सक्षम करने में विफल';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'पर्सोना सक्षम करने में त्रुटि: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'समर्थित देश प्राप्त करने में विफल। कृपया बाद में पुनः प्रयास करें।';

  @override
  String get paymentFailedToSetDefault => 'डिफ़ॉल्ट भुगतान विधि सेट करने में विफल। कृपया बाद में पुनः प्रयास करें।';

  @override
  String get paymentFailedToSavePaypal => 'PayPal विवरण सहेजने में विफल। कृपया बाद में पुनः प्रयास करें।';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'सक्रिय';

  @override
  String get paymentStatusConnected => 'कनेक्टेड';

  @override
  String get paymentStatusNotConnected => 'कनेक्ट नहीं';

  @override
  String get paymentAppCost => 'ऐप लागत';

  @override
  String get paymentEnterValidAmount => 'कृपया एक वैध राशि दर्ज करें';

  @override
  String get paymentEnterAmountGreaterThanZero => 'कृपया 0 से अधिक राशि दर्ज करें';

  @override
  String get paymentPlan => 'भुगतान योजना';

  @override
  String get paymentNoneSelected => 'कोई नहीं चुना';

  @override
  String get aiGenPleaseEnterDescription => 'कृपया अपने ऐप के लिए विवरण दर्ज करें';

  @override
  String get aiGenCreatingAppIcon => 'ऐप आइकन बनाया जा रहा है...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'एक त्रुटि हुई: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'ऐप सफलतापूर्वक बनाया गया!';

  @override
  String get aiGenFailedToCreateApp => 'ऐप बनाने में विफल';

  @override
  String get aiGenErrorWhileCreatingApp => 'ऐप बनाते समय एक त्रुटि हुई';

  @override
  String get aiGenFailedToGenerateApp => 'ऐप जनरेट करने में विफल। कृपया पुनः प्रयास करें।';

  @override
  String get aiGenFailedToRegenerateIcon => 'आइकन पुनः जनरेट करने में विफल';

  @override
  String get aiGenPleaseGenerateAppFirst => 'कृपया पहले एक ऐप जनरेट करें';

  @override
  String get xHandleTitle => 'What\'s your X handle?';

  @override
  String get xHandleDescription => 'We will pre-train your Omi clone\nbased on your account\'s activity';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Please enter your X handle';

  @override
  String get xHandlePleaseEnterValid => 'Please enter a valid X handle';

  @override
  String get nextButton => 'Next';

  @override
  String get connectOmiDevice => 'Connect Omi Device';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'You\'re switching your Unlimited Plan to the $title. Are you sure you want to proceed?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Upgrade scheduled! Your monthly plan continues until the end of your billing period, then automatically switches to annual.';

  @override
  String get couldNotSchedulePlanChange => 'Could not schedule plan change. Please try again.';

  @override
  String get subscriptionReactivatedDefault =>
      'Your subscription has been reactivated! No charge now - you\'ll be billed at the end of your current period.';

  @override
  String get subscriptionSuccessfulCharged =>
      'Subscription successful! You\'ve been charged for the new billing period.';

  @override
  String get couldNotProcessSubscription => 'Could not process subscription. Please try again.';

  @override
  String get couldNotLaunchUpgradePage => 'Could not launch upgrade page. Please try again.';

  @override
  String get transcriptionJsonPlaceholder => 'Paste your JSON configuration here...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'फ़ाइल पिकर खोलने में त्रुटि: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'त्रुटि: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'वार्तालाप सफलतापूर्वक मर्ज किए गए';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count वार्तालाप सफलतापूर्वक मर्ज किए गए';
  }

  @override
  String get dailyReflectionNotificationTitle => 'दैनिक चिंतन का समय';

  @override
  String get dailyReflectionNotificationBody => 'मुझे अपने दिन के बारे में बताओ';

  @override
  String get actionItemReminderTitle => 'Omi अनुस्मारक';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName डिस्कनेक्ट हो गया';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'कृपया अपने $deviceName का उपयोग जारी रखने के लिए फिर से कनेक्ट करें।';
  }

  @override
  String get onboardingSignIn => 'साइन इन करें';

  @override
  String get onboardingYourName => 'आपका नाम';

  @override
  String get onboardingLanguage => 'भाषा';

  @override
  String get onboardingPermissions => 'अनुमतियाँ';

  @override
  String get onboardingComplete => 'पूर्ण';

  @override
  String get onboardingWelcomeToOmi => 'Omi में आपका स्वागत है';

  @override
  String get onboardingTellUsAboutYourself => 'हमें अपने बारे में बताएं';

  @override
  String get onboardingChooseYourPreference => 'अपनी पसंद चुनें';

  @override
  String get onboardingGrantRequiredAccess => 'आवश्यक पहुँच प्रदान करें';

  @override
  String get onboardingYoureAllSet => 'आप तैयार हैं';
}
