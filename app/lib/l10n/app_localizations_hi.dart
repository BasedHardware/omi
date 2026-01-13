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
  String get cancel => 'रद्द करें';

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
  String get copyTranscript => 'प्रतिलेख कॉपी करें';

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
  String get noInternetConnection => 'कृपया अपना इंटरनेट कनेक्शन जांचें और पुनः प्रयास करें।';

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
  String get speechProfile => 'वाक् प्रोफ़ाइल';

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
  String get disconnected => 'डिस्कनेक्ट हुआ';

  @override
  String get searching => 'खोज रहा है';

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
  String get noConversationsYet => 'अभी तक कोई बातचीत नहीं।';

  @override
  String get noStarredConversations => 'कोई तारांकित बातचीत नहीं।';

  @override
  String get starConversationHint => 'बातचीत को तारांकित करने के लिए, उसे खोलें और शीर्ष पर तारे के आइकन को टैप करें।';

  @override
  String get searchConversations => 'बातचीत खोजें';

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
  String get deletingMessages => 'Omi की यादों से आपके संदेश हटा रहा है...';

  @override
  String get messageCopied => 'संदेश कॉपी किया गया।';

  @override
  String get cannotReportOwnMessage => 'आप अपने खुद के संदेशों की रिपोर्ट नहीं कर सकते।';

  @override
  String get reportMessage => 'संदेश की रिपोर्ट करें';

  @override
  String get reportMessageConfirm => 'क्या आप वाकई इस संदेश की रिपोर्ट करना चाहते हैं?';

  @override
  String get messageReported => 'संदेश सफलतापूर्वक रिपोर्ट किया गया।';

  @override
  String get thankYouFeedback => 'आपकी प्रतिक्रिया के लिए धन्यवाद!';

  @override
  String get clearChat => 'चैट साफ़ करें?';

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
  String get searchApps => '1500+ ऐप्स खोजें';

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
  String get helpOrInquiries => 'सहायता या पूछताछ?';

  @override
  String get joinCommunity => 'समुदाय में शामिल हों!';

  @override
  String get membersAndCounting => '8000+ सदस्य और बढ़ रहे हैं।';

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
  String get paymentMethods => 'भुगतान के तरीके';

  @override
  String get conversationDisplay => 'बातचीत प्रदर्शन';

  @override
  String get dataPrivacy => 'डेटा और गोपनीयता';

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
  String get offlineSync => 'ऑफ़लाइन सिंक';

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
  String get deviceId => 'डिवाइस ID';

  @override
  String get firmware => 'फर्मवेयर';

  @override
  String get sdCardSync => 'SD कार्ड सिंक';

  @override
  String get hardwareRevision => 'हार्डवेयर संशोधन';

  @override
  String get modelNumber => 'मॉडल नंबर';

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
  String get chargingIssues => 'चार्जिंग की समस्या';

  @override
  String get disconnectDevice => 'डिवाइस डिस्कनेक्ट करें';

  @override
  String get unpairDevice => 'डिवाइस अनपेयर करें';

  @override
  String get unpairAndForget => 'अनपेयर करें और डिवाइस भूल जाएं';

  @override
  String get deviceDisconnectedMessage => 'आपका Omi डिस्कनेक्ट हो गया 😔';

  @override
  String get deviceUnpairedMessage =>
      'डिवाइस अनपेयर हो गया। इसे पूरी तरह से अनपेयर करने के लिए सेटिंग्स > ब्लूटूथ पर जाएं और डिवाइस को भूल जाएं।';

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
  String get off => 'बंद';

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
  String get debugLogs => 'डीबग लॉग';

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
  String get knowledgeGraphDeleted => 'नॉलेज ग्राफ़ सफलतापूर्वक हटा दिया गया';

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
  String get webhooks => 'वेबहुक्स';

  @override
  String get conversationEvents => 'बातचीत ईवेंट';

  @override
  String get newConversationCreated => 'नई बातचीत बनाई गई';

  @override
  String get realtimeTranscript => 'रीयलटाइम ट्रांसक्रिप्ट';

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
  String get editName => 'नाम संपादित करें';

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
  String get refresh => 'ताज़ा करें';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName $codecReason का उपयोग करता है। Omi का उपयोग किया जाएगा।';
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
  String get makePublic => 'सार्वजनिक करें';

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
  String get speechProfileIntro => 'Omi को आपके लक्ष्यों और आपकी आवाज़ को जानने की ज़रूरत है।';

  @override
  String get getStarted => 'शुरू करें';

  @override
  String get allDone => 'सब हो गया!';

  @override
  String get keepGoing => 'जारी रखें';

  @override
  String get skipThisQuestion => 'यह प्रश्न छोड़ें';

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
  String get personalGrowthJourney => 'AI सुनने के साथ आपकी व्यक्तिगत विकास यात्रा।';

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
  String get deleteActionItemTitle => 'कार्य हटाएं';

  @override
  String get deleteActionItemMessage => 'क्या आप वाकई इस कार्य को हटाना चाहते हैं?';

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
  String searchMemories(int count) {
    return '$count यादें खोजें';
  }

  @override
  String get memoryDeleted => 'याद हटा दी गई।';

  @override
  String get undo => 'पूर्ववत करें';

  @override
  String get noMemoriesYet => 'अभी तक कोई यादें नहीं';

  @override
  String get noAutoMemories => 'कोई स्वतः यादें नहीं';

  @override
  String get noManualMemories => 'कोई मैनुअल यादें नहीं';

  @override
  String get noMemoriesInCategories => 'इन श्रेणियों में कोई यादें नहीं';

  @override
  String get noMemoriesFound => 'कोई यादें नहीं मिलीं';

  @override
  String get addFirstMemory => 'अपनी पहली याद जोड़ें';

  @override
  String get clearMemoryTitle => 'Omi मेमोरी साफ़ करें?';

  @override
  String get clearMemoryMessage => 'क्या आप वाकई Omi मेमोरी साफ़ करना चाहते हैं? यह पूर्ववत नहीं किया जा सकता।';

  @override
  String get clearMemoryButton => 'मेमोरी साफ़ करें';

  @override
  String get memoryClearedSuccess => 'मेमोरी साफ़ हो गई';

  @override
  String get noMemoriesToDelete => 'हटाने के लिए कोई यादें नहीं';

  @override
  String get createMemoryTooltip => 'नई याद बनाएं';

  @override
  String get createActionItemTooltip => 'नया कार्य बनाएं';

  @override
  String get memoryManagement => 'मेमोरी प्रबंधन';

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
  String get deleteAllMemories => 'सभी हटाएं';

  @override
  String get allMemoriesPrivateResult => 'सभी यादें अब निजी हैं';

  @override
  String get allMemoriesPublicResult => 'सभी यादें अब सार्वजनिक हैं';

  @override
  String get newMemory => 'नई याद';

  @override
  String get editMemory => 'याद संपादित करें';

  @override
  String get memoryContentHint => 'मुझे आइसक्रीम पसंद है...';

  @override
  String get failedToSaveMemory => 'सहेजने में विफल।';

  @override
  String get saveMemory => 'याद सहेजें';

  @override
  String get retry => 'पुनः प्रयास करें';

  @override
  String get createActionItem => 'कार्य बनाएं';

  @override
  String get editActionItem => 'कार्य संपादित करें';

  @override
  String get actionItemDescriptionHint => 'क्या करने की आवश्यकता है?';

  @override
  String get actionItemDescriptionEmpty => 'विवरण खाली नहीं हो सकता।';

  @override
  String get actionItemUpdated => 'कार्य अपडेट किया गया';

  @override
  String get failedToUpdateActionItem => 'अपडेट करने में विफल';

  @override
  String get actionItemCreated => 'कार्य बनाया गया';

  @override
  String get failedToCreateActionItem => 'बनाने में विफल';

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
  String get markComplete => 'पूर्ण चिह्नित करें';

  @override
  String get actionItemDeleted => 'कार्य हटाया गया';

  @override
  String get failedToDeleteActionItem => 'हटाने में विफल';

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
}
