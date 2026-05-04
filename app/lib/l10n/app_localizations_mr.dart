// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Marathi (`mr`).
class AppLocalizationsMr extends AppLocalizations {
  AppLocalizationsMr([String locale = 'mr']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'संभाषण';

  @override
  String get transcriptTab => 'प्रतिलेख';

  @override
  String get actionItemsTab => 'कार्य आयटम';

  @override
  String get deleteConversationTitle => 'संभाषण हटवू?';

  @override
  String get deleteConversationMessage =>
      'यामुळे संबंधित स्मृती, कार्य आणि ऑडिओ फाइल देखील हटवल्या जातील. ही कारवाई पूर्ववत केली जाऊ शकत नाही.';

  @override
  String get confirm => 'पुष्टी करा';

  @override
  String get cancel => 'रद्द करा';

  @override
  String get ok => 'ठीक आहे';

  @override
  String get delete => 'हटवा';

  @override
  String get add => 'जोडा';

  @override
  String get update => 'अपडेट करा';

  @override
  String get save => 'सेव्ह करा';

  @override
  String get edit => 'संपादन करा';

  @override
  String get close => 'बंद करा';

  @override
  String get clear => 'साफ करा';

  @override
  String get copyTranscript => 'प्रतिलेख कॉपी करा';

  @override
  String get copySummary => 'सारांश कॉपी करा';

  @override
  String get testPrompt => 'टेस्ट प्रॉम्प्ट';

  @override
  String get reprocessConversation => 'संभाषण पुन: प्रक्रिया करा';

  @override
  String get deleteConversation => 'संभाषण हटवा';

  @override
  String get contentCopied => 'क्लिपबोर्डला सामग्री कॉपी केली';

  @override
  String get failedToUpdateStarred => 'तारकांकित स्थिती अपडेट करणे अयोग्य.';

  @override
  String get conversationUrlNotShared => 'संभाषण URL शेयर केला जाऊ शकला नाही.';

  @override
  String get errorProcessingConversation => 'संभाषण प्रक्रिया करताना त्रुटी. कृपया नंतर पुन्हा प्रयत्न करा.';

  @override
  String get noInternetConnection => 'इंटरनेट कनेक्शन नाही';

  @override
  String get unableToDeleteConversation => 'संभाषण हटवू शकत नाही';

  @override
  String get somethingWentWrong => 'काहीतरी गाढळले! कृपया नंतर पुन्हा प्रयत्न करा.';

  @override
  String get copyErrorMessage => 'त्रुटी संदेश कॉपी करा';

  @override
  String get errorCopied => 'त्रुटी संदेश क्लिपबोर्डला कॉपी केला';

  @override
  String get remaining => 'उरलेले';

  @override
  String get loading => 'लोड होत आहे...';

  @override
  String get loadingDuration => 'अवधान लोड होत आहे...';

  @override
  String secondsCount(int count) {
    return '$count सेकंद';
  }

  @override
  String get people => 'लोक';

  @override
  String get addNewPerson => 'नवीन व्यक्ती जोडा';

  @override
  String get editPerson => 'व्यक्ती संपादित करा';

  @override
  String get createPersonHint => 'एक नवीन व्यक्ती तयार करा आणि Omi ला त्यांची बोलणी ओळखायला प्रशिक्षित करा!';

  @override
  String get speechProfile => 'वाण प्रोफाइल';

  @override
  String sampleNumber(int number) {
    return 'नमुना $number';
  }

  @override
  String get settings => 'सेटिंग्ज';

  @override
  String get language => 'भाषा';

  @override
  String get selectLanguage => 'भाषा निवडा';

  @override
  String get deleting => 'हटवत आहे...';

  @override
  String get pleaseCompleteAuthentication =>
      'कृपया आपल्या ब्राउজरमध्ये प्रमाणीकरण पूर्ण करा. केल्यानंतर, अ‍ॅपवर परत या.';

  @override
  String get failedToStartAuthentication => 'प्रमाणीकरण सुरू करणे अयोग्य';

  @override
  String get importStarted => 'आयात सुरू केला! हे पूर्ण झाल्यावर आपल्याला सूचित केले जाईल.';

  @override
  String get failedToStartImport => 'आयात सुरू करणे अयोग्य. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get couldNotAccessFile => 'निवडलेली फाइल अ‍ॅक्सेस करू शकत नाही';

  @override
  String get askOmi => 'Omi ला विचारा';

  @override
  String get done => 'पूर्ण';

  @override
  String get disconnected => 'डिस्कनेक्ट केला';

  @override
  String get searching => 'शोधत आहे...';

  @override
  String get connectDevice => 'डिव्हाइस कनेक्ट करा';

  @override
  String get monthlyLimitReached => 'आपण मासिक मर्यादा गाठली आहे.';

  @override
  String get checkUsage => 'वापर तपासा';

  @override
  String get syncingRecordings => 'रेकॉर्डिंग सिंक करत आहे';

  @override
  String get recordingsToSync => 'सिंक करण्यासाठी रेकॉर्डिंग';

  @override
  String get allCaughtUp => 'सर्व अद्यतन झाले';

  @override
  String get sync => 'सिंक करा';

  @override
  String get pendantUpToDate => 'पेंडेंट अद्यतन आहे';

  @override
  String get allRecordingsSynced => 'सर्व रेकॉर्डिंग सिंक केली गेली आहे';

  @override
  String get syncingInProgress => 'सिंक प्रगतीपथावर आहे';

  @override
  String get readyToSync => 'सिंक करण्यासाठी तयार';

  @override
  String get tapSyncToStart => 'सुरू करण्यासाठी सिंक टॅप करा';

  @override
  String get pendantNotConnected => 'पेंडेंट कनेक्ट नाही. सिंक करण्यासाठी कनेक्ट करा.';

  @override
  String get everythingSynced => 'सर्व काही आधीच सिंक केलेले आहे.';

  @override
  String get recordingsNotSynced => 'आपल्याकडे अशी रेकॉर्डिंग आहेत जी अद्याप सिंक केली नाहीत.';

  @override
  String get syncingBackground => 'आम्ही आपल्या रेकॉर्डिंग पार्श्वभूमीमध्ये सिंक करत राहू.';

  @override
  String get noConversationsYet => 'अद्याप संभाषण नाही';

  @override
  String get noStarredConversations => 'तारकांकित संभाषण नाही';

  @override
  String get starConversationHint => 'संभाषणला तारकांकित करण्यासाठी, ते उघडा आणि हेडरमधील तारा चिन्ह टॅप करा.';

  @override
  String get searchConversations => 'संभाषण शोधा...';

  @override
  String selectedCount(int count, Object s) {
    return '$count निवडले';
  }

  @override
  String get merge => 'विलीन करा';

  @override
  String get mergeConversations => 'संभाषण विलीन करा';

  @override
  String mergeConversationsMessage(int count) {
    return 'यामुळे $count संभाषण एकात विलीन होतील. सर्व सामग्री विलीन आणि पुनः निर्मित केली जाईल.';
  }

  @override
  String get mergingInBackground => 'पार्श्वभूमीमध्ये विलीन करत आहे. यामुळे थोडा वेळ लागू शकतो.';

  @override
  String get failedToStartMerge => 'विलीन सुरू करणे अयोग्य';

  @override
  String get askAnything => 'कुछ भी पूछें';

  @override
  String get noMessagesYet => 'अद्याप संदेश नाही!\nका संभाषण सुरू करत नाही?';

  @override
  String get deletingMessages => 'Omi च्या स्मृतीतून आपल्या संदेश हटवत आहे...';

  @override
  String get messageCopied => '✨ संदेश क्लिपबोर्डला कॉपी केला';

  @override
  String get cannotReportOwnMessage => 'आप स्वतःचे संदेश अहवाल केू शकत नाही.';

  @override
  String get reportMessage => 'संदेशाचा अहवाल द्या';

  @override
  String get reportMessageConfirm => 'आप हा संदेश अहवाल द्यायला निश्चित आहात?';

  @override
  String get messageReported => 'संदेश यशस्वीरित्या अहवाल दिला.';

  @override
  String get thankYouFeedback => 'आपल्या प्रतिक्रियेबद्दल धन्यवाद!';

  @override
  String get clearChat => 'चॅट साफ करा';

  @override
  String get clearChatConfirm => 'आप चॅट साफ करू इच्छिता? ही कारवाई पूर्ववत केली जाऊ शकत नाही.';

  @override
  String get maxFilesLimit => 'आप एक वेळी केवळ 4 फाइल अपलोड करू शकता';

  @override
  String get chatWithOmi => 'Omi सह चॅट करा';

  @override
  String get apps => 'अ‍ॅप';

  @override
  String get noAppsFound => 'कोणतेही अ‍ॅप सापडले नाही';

  @override
  String get tryAdjustingSearch => 'आपल्या शोध किंवा फिल्टर समायोजित करून पहा';

  @override
  String get createYourOwnApp => 'आपले स्वतःचे अ‍ॅप तयार करा';

  @override
  String get buildAndShareApp => 'आपले सुधारित अ‍ॅप तयार करा आणि शेयर करा';

  @override
  String get searchApps => 'अ‍ॅप शोधा...';

  @override
  String get myApps => 'माझी अ‍ॅप्स';

  @override
  String get installedApps => 'स्थापित अ‍ॅप्स';

  @override
  String get unableToFetchApps =>
      'अ‍ॅप्स आणू शकत नाही :(\n\nकृपया आपल्या इंटरनेट कनेक्शन तपासा आणि पुन्हा प्रयत्न करा.';

  @override
  String get aboutOmi => 'Omi बद्दल';

  @override
  String get privacyPolicy => 'गोपनीयता धोरण';

  @override
  String get visitWebsite => 'वेबसाइट भेट द्या';

  @override
  String get helpOrInquiries => 'मदत किंवा चौकशी?';

  @override
  String get joinCommunity => 'समुदायात सामील हा!';

  @override
  String get membersAndCounting => '8000+ सदस्य आणि अधिक.';

  @override
  String get deleteAccountTitle => 'खाता हटवा';

  @override
  String get deleteAccountConfirm => 'आप आपला खाता हटवू इच्छिता?';

  @override
  String get cannotBeUndone => 'हे पूर्ववत केले जाऊ शकत नाही.';

  @override
  String get allDataErased => 'आपली सर्व स्मृती आणि संभाषण स्थायीपणे हटवल्या जातील.';

  @override
  String get appsDisconnected => 'आपली अ‍ॅप्स आणि एकीकरण तातडीने डिस्कनेक्ट केली जाईल.';

  @override
  String get exportBeforeDelete =>
      'आप आपला खाता हटवण्यापूर्वी आपल्या डेटा निर्यात करू शकता, परंतु एकदा हटवल्यानंतर, ते पुनर्प्राप्त केले जाऊ शकत नाही.';

  @override
  String get deleteAccountCheckbox =>
      'मी समजतो की माझा खाता हटवणे स्थायी आहे आणि सर्व डेटा, स्मृती आणि संभाषण सह, हरवल्या जातील आणि पुनर्प्राप्त केले जाऊ शकत नाही.';

  @override
  String get areYouSure => 'आप निश्चित आहात?';

  @override
  String get deleteAccountFinal =>
      'ही कारवाई पूर्ववत नाही आणि आपला खाता आणि सर्व संबंधित डेटा स्थायीपणे हटवल्या जातील. आप पुढे जाऊ इच्छिता?';

  @override
  String get deleteNow => 'आता हटवा';

  @override
  String get goBack => 'परत जा';

  @override
  String get checkBoxToConfirm =>
      'पुष्टी करण्यासाठी बॉक्स तपासा की आप समजतात की आपल्या खाता हटवणे स्थायी आणि पूर्ववत नाही.';

  @override
  String get profile => 'प्रोफाइल';

  @override
  String get name => 'नाव';

  @override
  String get email => 'ईमेल';

  @override
  String get customVocabulary => 'कस्टम शब्दावली';

  @override
  String get identifyingOthers => 'इतरांची ओळख करा';

  @override
  String get paymentMethods => 'भुगतान पद्धती';

  @override
  String get conversationDisplay => 'संभाषण प्रदर्शन';

  @override
  String get dataPrivacy => 'डेटा गोपनीयता';

  @override
  String get userId => 'वापरकर्ता ID';

  @override
  String get notSet => 'सेट नाही';

  @override
  String get userIdCopied => 'वापरकर्ता ID क्लिपबोर्डला कॉपी केली';

  @override
  String get systemDefault => 'प्रणाली डिफॉल्ट';

  @override
  String get planAndUsage => 'योजना आणि वापर';

  @override
  String get offlineSync => 'ऑफलाइन सिंक करा';

  @override
  String get deviceSettings => 'डिव्हाइस सेटिंग्ज';

  @override
  String get integrations => 'एकीकरण';

  @override
  String get feedbackBug => 'प्रतिक्रिया / बग';

  @override
  String get helpCenter => 'मदत केंद्र';

  @override
  String get developerSettings => 'विकासक सेटिंग्ज';

  @override
  String get getOmiForMac => 'Mac साठी Omi मिळवा';

  @override
  String get referralProgram => 'संदर्भ कार्यक्रम';

  @override
  String get signOut => 'साइन आउट करा';

  @override
  String get appAndDeviceCopied => 'अ‍ॅप आणि डिव्हाइस तपशील कॉपी केले';

  @override
  String get wrapped2025 => '2025 मुडी';

  @override
  String get yourPrivacyYourControl => 'आपली गोपनीयता, आपला नियंत्रण';

  @override
  String get privacyIntro =>
      'Omi मध्ये, आम्ही आपल्या गोपनीयतेची संरक्षण करण्यासाठी प्रतिबद्ध आहोत. हे पृष्ठ आपल्याला आपल्या डेटा कसा संग्रहित आणि वापरला जातो याचे नियंत्रण करण्यास अनुमती देते.';

  @override
  String get learnMore => 'अधिक जाणून घ्या...';

  @override
  String get dataProtectionLevel => 'डेटा संरक्षण स्तर';

  @override
  String get dataProtectionDesc =>
      'आपल्या डेटा मजबूत एन्क्रिप्शनद्वारे डिफॉल्टनुसार सुरक्षित आहेत. खालील आपल्या सेटिंग्ज आणि भविष्यातील गोपनीयता पर्याय पुनरावलोकन करा.';

  @override
  String get appAccess => 'अ‍ॅप प्रवेश';

  @override
  String get appAccessDesc =>
      'खालील अ‍ॅप्स आपल्या डेटा अ‍ॅक्सेस करू शकते. त्याचे अनुमती व्यवस्थापित करण्यासाठी अ‍ॅपवर टॅप करा.';

  @override
  String get noAppsExternalAccess => 'स्थापित अ‍ॅप्सचा आपल्या डेटासाठी कोणताही बाह्य प्रवेश नाही.';

  @override
  String get deviceName => 'डिव्हाइस नाव';

  @override
  String get deviceId => 'डिव्हाइस ID';

  @override
  String get firmware => 'फर्मवेअर';

  @override
  String get sdCardSync => 'SD कार्ड सिंक करा';

  @override
  String get hardwareRevision => 'हार्डवेअर सुधार';

  @override
  String get modelNumber => 'मॉडेल क्रमांक';

  @override
  String get manufacturer => 'उत्पादक';

  @override
  String get doubleTap => 'दुहेरी टॅप';

  @override
  String get ledBrightness => 'LED चमक';

  @override
  String get micGain => 'मायक्रोफोन लाभ';

  @override
  String get disconnect => 'डिस्कनेक्ट करा';

  @override
  String get forgetDevice => 'डिव्हाइस विसरा';

  @override
  String get chargingIssues => 'चार्जिंग समस्या';

  @override
  String get disconnectDevice => 'डिव्हाइस डिस्कनेक्ट करा';

  @override
  String get unpairDevice => 'डिव्हाइस अनपेअर करा';

  @override
  String get unpairAndForget => 'डिव्हाइस अनपेअर आणि विसरा';

  @override
  String get deviceDisconnectedMessage => 'आपल्या Omi डिस्कनेक्ट केला गेला आहे 😔';

  @override
  String get deviceUnpairedMessage =>
      'डिव्हाइस अनपेअर केला. अनपेअरिंग पूर्ण करण्यासाठी सेटिंग्ज > Bluetooth वर जा आणि डिव्हाइस विसरा.';

  @override
  String get unpairDialogTitle => 'डिव्हाइस अनपेअर करा';

  @override
  String get unpairDialogMessage =>
      'यामुळे डिव्हाइस अनपेअर होईल जेणेकरून ते दुसर्‍या फोनवर कनेक्ट केले जाऊ शकेल. आपल्याला सेटिंग्ज > Bluetooth वर जावे लागेल आणि प्रक्रिया पूर्ण करण्यासाठी डिव्हाइस विसरावे लागेल.';

  @override
  String get deviceNotConnected => 'डिव्हाइस कनेक्ट नाही';

  @override
  String get connectDeviceMessage =>
      'डिव्हाइस सेटिंग्ज आणि कस्टमाइজेशन अ‍ॅक्सेस करण्यासाठी आपल्या Omi डिव्हाइस कनेक्ट करा';

  @override
  String get deviceInfoSection => 'डिव्हाइस माहिती';

  @override
  String get customizationSection => 'कस्टमाइजेशन';

  @override
  String get hardwareSection => 'हार्डवेअर';

  @override
  String get v2Undetected => 'V2 ओळखला नाही';

  @override
  String get v2UndetectedMessage =>
      'आम्ही पाहतो की आपल्याकडे V1 डिव्हाइस आहे किंवा आपल्या डिव्हाइस कनेक्ट नाही. SD कार्ड कार्यक्षमता केवळ V2 डिव्हाइससाठी उपलब्ध आहे.';

  @override
  String get endConversation => 'संभाषण समाप्त करा';

  @override
  String get pauseResume => 'विराम/पुनः सुरू करा';

  @override
  String get starConversation => 'संभाषणला तारकांकित करा';

  @override
  String get doubleTapAction => 'दुहेरी टॅप क्रिया';

  @override
  String get endAndProcess => 'संभाषण समाप्त आणि प्रक्रिया करा';

  @override
  String get pauseResumeRecording => 'रेकॉर्डिंग विराम/पुनः सुरू करा';

  @override
  String get starOngoing => 'सुरू संभाषणला तारकांकित करा';

  @override
  String get off => 'बंद';

  @override
  String get max => 'कमाल';

  @override
  String get mute => 'निःशब्द करा';

  @override
  String get quiet => 'शांत';

  @override
  String get normal => 'सामान्य';

  @override
  String get high => 'उच्च';

  @override
  String get micGainDescMuted => 'मायक्रोफोन निःशब्द आहे';

  @override
  String get micGainDescLow => 'खूप शांत - मोठ्या वातावरणांसाठी';

  @override
  String get micGainDescModerate => 'शांत - मध्यम आवाजासाठी';

  @override
  String get micGainDescNeutral => 'तटस्थ - संतुलित रेकॉर्डिंग';

  @override
  String get micGainDescSlightlyBoosted => 'किंचित वाढवले - सामान्य वापर';

  @override
  String get micGainDescBoosted => 'वाढवले - शांत वातावरणांसाठी';

  @override
  String get micGainDescHigh => 'उच्च - दूरचे किंवा मऊ आवाजांसाठी';

  @override
  String get micGainDescVeryHigh => 'खूप उच्च - खूप शांत स्रोतांसाठी';

  @override
  String get micGainDescMax => 'कमाल - सावधानीने वापरा';

  @override
  String get developerSettingsTitle => 'विकासक सेटिंग्ज';

  @override
  String get saving => 'सेव्ह करत आहे...';

  @override
  String get beta => 'बीटा';

  @override
  String get transcription => 'प्रतिलेख';

  @override
  String get transcriptionConfig => 'STT प्रदाता कॉन्फिगर करा';

  @override
  String get conversationTimeout => 'संभाषण टाइमआउट';

  @override
  String get conversationTimeoutConfig => 'संभाषण कधी स्वयंचलितपणे समाप्त होतात हे सेट करा';

  @override
  String get importData => 'डेटा आयात करा';

  @override
  String get importDataConfig => 'इतर स्रोतांमधून डेटा आयात करा';

  @override
  String get debugDiagnostics => 'डिबग आणि निदान';

  @override
  String get endpointUrl => 'एंडपॉइंट URL';

  @override
  String get noApiKeys => 'अद्याप कोणतेही API की नाही';

  @override
  String get createKeyToStart => 'सुरू करण्यासाठी की तयार करा';

  @override
  String get createKey => 'की तयार करा';

  @override
  String get docs => 'डॉक्स';

  @override
  String get yourOmiInsights => 'आपल्या Omi अंतर्दृष्टी';

  @override
  String get today => 'आज';

  @override
  String get thisMonth => 'या महिन्यात';

  @override
  String get thisYear => 'या वर्षी';

  @override
  String get allTime => 'सर्व काळ';

  @override
  String get noActivityYet => 'अद्याप कोणतीही क्रिया नाही';

  @override
  String get startConversationToSeeInsights => 'Omi सह संभाषण सुरू करा\nआपल्या वापर अंतर्दृष्टी येथे पाहण्यासाठी.';

  @override
  String get listening => 'ऐकत आहे';

  @override
  String get listeningSubtitle => 'Omi सक्रियपणे ऐकलेला एकूण वेळ.';

  @override
  String get understanding => 'समजून घेत आहे';

  @override
  String get understandingSubtitle => 'आपल्या संभाषणांमधून समजलेले शब्द.';

  @override
  String get providing => 'प्रदान करत आहे';

  @override
  String get providingSubtitle => 'कार्य आयटम आणि स्वयंचलितपणे कॅप्चर केलेल्या नोट्स.';

  @override
  String get remembering => 'लक्षात ठेवत आहे';

  @override
  String get rememberingSubtitle => 'आपल्यासाठी लक्षात ठेवलेले तथ्य आणि तपशील.';

  @override
  String get unlimitedPlan => 'मर्यादित योजना';

  @override
  String get managePlan => 'योजना व्यवस्थापित करा';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'आपल्या योजना $date वर रद्द होईल.';
  }

  @override
  String renewsOn(String date) {
    return 'आपल्या योजना $date वर नवीकरण होईल.';
  }

  @override
  String get basicPlan => 'मुक्त योजना';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used of $limit मिनिटे वापरली गेली';
  }

  @override
  String get upgrade => 'अपग्रेड करा';

  @override
  String get upgradeToUnlimited => 'मर्यादित अपग्रेड करा';

  @override
  String basicPlanDesc(int limit) {
    return 'आपल्या योजनामध्ये प्रति महिने $limit मुक्त मिनिटे समाविष्ट आहेत. मर्यादित जाण्यासाठी अपग्रेड करा.';
  }

  @override
  String get shareStatsMessage => 'माझ्या Omi आकडे शेयर करत आहे! (omi.me - आपल्या नेहमीचे AI सहायक)';

  @override
  String get sharePeriodToday => 'आज, omi आहे:';

  @override
  String get sharePeriodMonth => 'या महिन्यात, omi आहे:';

  @override
  String get sharePeriodYear => 'या वर्षी, omi आहे:';

  @override
  String get sharePeriodAllTime => 'अब तक, omi आहे:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes मिनिटे ऐकले';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words शब्द समजून घेतले';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count अंतर्दृष्टी प्रदान केली';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count स्मृती लक्षात ठेवली';
  }

  @override
  String get debugLogs => 'डिबग लॉग्स';

  @override
  String get debugLogsAutoDelete => '3 दिवसानंतर स्वयंचलितपणे हटवा.';

  @override
  String get debugLogsDesc => 'समस्या निदान करण्यात मदत करते';

  @override
  String get noLogFilesFound => 'कोणतीही लॉग फाइल सापडली नाही.';

  @override
  String get omiDebugLog => 'Omi डिबग लॉग';

  @override
  String get logShared => 'लॉग शेयर केला';

  @override
  String get selectLogFile => 'लॉग फाइल निवडा';

  @override
  String get shareLogs => 'लॉग्स शेयर करा';

  @override
  String get debugLogCleared => 'डिबग लॉग साफ केला';

  @override
  String get exportStarted => 'निर्यात सुरू केला. यामुळे काही सेकंद लागू शकतो...';

  @override
  String get exportAllData => 'सर्व डेटा निर्यात करा';

  @override
  String get exportDataDesc => 'संभाषण JSON फाइलमध्ये निर्यात करा';

  @override
  String get exportedConversations => 'Omi मधून निर्यात केलेले संभाषण';

  @override
  String get exportShared => 'निर्यात शेयर केला';

  @override
  String get deleteKnowledgeGraphTitle => 'ज्ञान ग्राफ हटवू?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'यामुळे सर्व व्युत्पन्न ज्ञान ग्राफ डेटा (नोड्स आणि कनेक्शन) हटवल्या जातील. आपल्या मूळ स्मृती सुरक्षित राहतील. ग्राफ कालांतराने किंवा पुढील विनंतीवर पुनर्निर्मित होईल.';

  @override
  String get knowledgeGraphDeleted => 'ज्ञान ग्राफ हटवला';

  @override
  String deleteGraphFailed(String error) {
    return 'ग्राफ हटवणे अयोग्य: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'ज्ञान ग्राफ हटवा';

  @override
  String get deleteKnowledgeGraphDesc => 'सर्व नोड्स आणि कनेक्शन साफ करा';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP सर्व्हर';

  @override
  String get mcpServerDesc => 'AI सहायकांना आपल्या डेटासाठी कनेक्ट करा';

  @override
  String get serverUrl => 'सर्व्हर URL';

  @override
  String get urlCopied => 'URL कॉपी केला';

  @override
  String get apiKeyAuth => 'API की प्रमाणीकरण';

  @override
  String get header => 'हेडर';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'क्लायंट ID';

  @override
  String get clientSecret => 'क्लायंट गुप्त';

  @override
  String get useMcpApiKey => 'आपल्या MCP API की वापरा';

  @override
  String get webhooks => 'वेबहुक्स';

  @override
  String get conversationEvents => 'संभाषण इव्हेंट्स';

  @override
  String get newConversationCreated => 'नवीन संभाषण तयार केले';

  @override
  String get realtimeTranscript => 'रीयल-टाइम प्रतिलेख';

  @override
  String get transcriptReceived => 'प्रतिलेख प्राप्त';

  @override
  String get audioBytes => 'ऑडिओ बाईट्स';

  @override
  String get audioDataReceived => 'ऑडिओ डेटा प्राप्त';

  @override
  String get intervalSeconds => 'अंतराल (सेकंद)';

  @override
  String get daySummary => 'दिवस सारांश';

  @override
  String get summaryGenerated => 'सारांश तयार केला';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.json मध्ये जोडा';

  @override
  String get copyConfig => 'कॉन्फिग कॉपी करा';

  @override
  String get configCopied => 'कॉन्फिग क्लिपबोर्डला कॉपी केला';

  @override
  String get listeningMins => 'ऐकत आहे (मिनिटे)';

  @override
  String get understandingWords => 'समजून घेत आहे (शब्द)';

  @override
  String get insights => 'अंतर्दृष्टी';

  @override
  String get memories => 'स्मृती';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'या महिन्यात $used of $limit मिनिट वापरली';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'या महिन्यात $used of $limit शब्द वापरले';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'या महिन्यात $used of $limit अंतर्दृष्टी मिळवली';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'या महिन्यात $used of $limit स्मृती तयार केली';
  }

  @override
  String get visibility => 'दृश्यमानता';

  @override
  String get visibilitySubtitle => 'कोण संभाषण आपल्या सूचीमध्ये दिसतात हे नियंत्रण करा';

  @override
  String get showShortConversations => 'लघु संभाषण दाखवा';

  @override
  String get showShortConversationsDesc => 'मर्यादेपेक्षा लहान संभाषण प्रदर्शित करा';

  @override
  String get showDiscardedConversations => 'त्याग केलेले संभाषण दाखवा';

  @override
  String get showDiscardedConversationsDesc => 'त्याग केलेले चिन्हांकित संभाषण समाविष्ट करा';

  @override
  String get shortConversationThreshold => 'लघु संभाषण मर्यादा';

  @override
  String get shortConversationThresholdSubtitle =>
      'या मर्यादेपेक्षा लहान संभाषण लपवल्या जातील जोपर्यंत वरील सक्षम नाही';

  @override
  String get durationThreshold => 'अवधान मर्यादा';

  @override
  String get durationThresholdDesc => 'याच्या मर्यादेपेक्षा लहान संभाषण लपवा';

  @override
  String minLabel(int count) {
    return '$count मिनिट';
  }

  @override
  String get customVocabularyTitle => 'कस्टम शब्दावली';

  @override
  String get addWords => 'शब्द जोडा';

  @override
  String get addWordsDesc => 'नावे, अटी, किंवा असामान्य शब्द';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'कनेक्ट करा';

  @override
  String get comingSoon => 'जवळच येत आहे';

  @override
  String get integrationsFooter => 'चॅटमध्ये डेटा आणि मेट्रिक्स पाहण्यासाठी आपल्या अ‍ॅप्स कनेक्ट करा.';

  @override
  String get completeAuthInBrowser => 'कृपया आपल्या ब्राउজरमध्ये प्रमाणीकरण पूर्ण करा. केल्यानंतर, अ‍ॅपवर परत या.';

  @override
  String failedToStartAuth(String appName) {
    return '$appName प्रमाणीकरण सुरू करणे अयोग्य';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName डिस्कनेक्ट करू?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'आप $appName मधून डिस्कनेक्ट करू इच्छिता? आप कधीही पुन्हा कनेक्ट करू शकता.';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName मधून डिस्कनेक्ट केला';
  }

  @override
  String get failedToDisconnect => 'डिस्कनेक्ट करणे अयोग्य';

  @override
  String connectTo(String appName) {
    return '$appName सह कनेक्ट करा';
  }

  @override
  String authAccessMessage(String appName) {
    return 'आपल्या $appName डेटा अ‍ॅक्सेस करण्यासाठी Omi ला अधिकार देणे आवश्यक आहे. यामुळे प्रमाणीकरणासाठी आपल्या ब्राउজर उघडेल.';
  }

  @override
  String get continueAction => 'सुरू ठेवा';

  @override
  String get languageTitle => 'भाषा';

  @override
  String get primaryLanguage => 'प्राथमिक भाषा';

  @override
  String get automaticTranslation => 'स्वयंचलित अनुवाद';

  @override
  String get detectLanguages => '10+ भाषा शोधा';

  @override
  String get authorizeSavingRecordings => 'रेकॉर्डिंग संरक्षण अधिकृत करा';

  @override
  String get thanksForAuthorizing => 'अधिकृत केल्याबद्दल धन्यवाद!';

  @override
  String get needYourPermission => 'आमला आपल्या अनुमतीची आवश्यकता आहे';

  @override
  String get alreadyGavePermission =>
      'आपण आमला आपल्या रेकॉर्डिंग संरक्षण करण्याची अनुमती दिली आहे. हे आवश्यक असणार्या कारणाचे स्मरण:';

  @override
  String get wouldLikePermission => 'आम्हाला आपल्या व्हॉयस रेकॉर्डिंग संरक्षण करण्याची अनुमती हवी आहे. येथे का आहे:';

  @override
  String get improveSpeechProfile => 'आपल्या वाण प्रोफाइल सुधारा';

  @override
  String get improveSpeechProfileDesc =>
      'आम्ही आपल्या व्यक्तिगत वाण प्रोफाइल प्रशिक्षित आणि वाढवण्यासाठी रेकॉर्डिंग वापरतो.';

  @override
  String get trainFamilyProfiles => 'मित्र आणि कुटुंब सदस्यांसाठी प्रोफाइल प्रशिक्षित करा';

  @override
  String get trainFamilyProfilesDesc =>
      'आपल्या रेकॉर्डिंग आपल्या मित्र आणि कुटुंब सदस्यांना ओळखायला आणि प्रोफाइल तयार करायला मदत करते.';

  @override
  String get enhanceTranscriptAccuracy => 'प्रतिलेख अचूकता वाढवा';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'आमचा मॉडेल सुधारत असताना, आम्ही आपल्या रेकॉर्डिंगसाठी बेहतर प्रतिलेख परिणाम प्रदान करू शकतो.';

  @override
  String get legalNotice =>
      'कायदेशीर सूचना: आपल्या स्थान आणि या वैशिष्ट्याचा वापर कसा करतात यावर आधारित, रेकॉर्डिंग आणि व्हॉयस डेटा संरक्षण करणे कानूनी असू शकते किंवा नसू शकते. स्थानिक कायदे आणि नियमांचे पालन सुनिश्चित करणे हे आपल्याचे जबाबदारी आहे.';

  @override
  String get alreadyAuthorized => 'आधीच अधिकृत';

  @override
  String get authorize => 'अधिकृत करा';

  @override
  String get revokeAuthorization => 'अधिकार रद्द करा';

  @override
  String get authorizationSuccessful => 'अधिकार यशस्वी!';

  @override
  String get failedToAuthorize => 'प्राधिकृत करण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get authorizationRevoked => 'प्राधिकार रद्द केला.';

  @override
  String get recordingsDeleted => 'रेकॉर्डिंग हटवली गेली.';

  @override
  String get failedToRevoke => 'प्राधिकार रद्द करण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get permissionRevokedTitle => 'परवानगी रद्द केली गेली';

  @override
  String get permissionRevokedMessage => 'आम्ही आपली सर्व विद्यमान रेकॉर्डिंग हटवावी असे आपल्याला वाटते?';

  @override
  String get yes => 'होय';

  @override
  String get editName => 'नाव संपादित करा';

  @override
  String get howShouldOmiCallYou => 'Omi आपल्याला कसे संबोधू शकतो?';

  @override
  String get enterYourName => 'आपले नाव प्रविष्ट करा';

  @override
  String get nameCannotBeEmpty => 'नाव रिक्त असू शकत नाही';

  @override
  String get nameUpdatedSuccessfully => 'नाव यशस्वीरित्या अपडेट केलं!';

  @override
  String get calendarSettings => 'कॅलेंडर सेटिंग्ज';

  @override
  String get calendarProviders => 'कॅलेंडर प्रदाते';

  @override
  String get macOsCalendar => 'macOS कॅलेंडर';

  @override
  String get connectMacOsCalendar => 'आपले स्थानिक macOS कॅलेंडर जोडा';

  @override
  String get googleCalendar => 'Google कॅलेंडर';

  @override
  String get syncGoogleAccount => 'आपल्या Google खातेशी सिंक करा';

  @override
  String get showMeetingsMenuBar => 'मेनू बारमध्ये आगामी मीटिंग दाखवा';

  @override
  String get showMeetingsMenuBarDesc => 'macOS मेनू बारमध्ये आपली पुढील मीटिंग आणि सुरू होण्यापर्यंत उर्वरित वेळ दाखवा';

  @override
  String get showEventsNoParticipants => 'सहभागी नसलेली इव्हेंट दाखवा';

  @override
  String get showEventsNoParticipantsDesc =>
      'सक्षम केल्यास, Coming Up सहभागी किंवा व्हिडिओ लिंक नसलेली इव्हेंट दाखवते.';

  @override
  String get yourMeetings => 'आपली मीटिंग्ज';

  @override
  String get refresh => 'रीफ्रेश करा';

  @override
  String get noUpcomingMeetings => 'आगामी कोणतीही मीटिंग नाही';

  @override
  String get checkingNextDays => 'पुढील 30 दिन तपासत आहे';

  @override
  String get tomorrow => 'उद्या';

  @override
  String get googleCalendarComingSoon => 'Google कॅलेंडर इंटीग्रेशन लवकरच येतं!';

  @override
  String connectedAsUser(String userId) {
    return 'वापरकर्ता म्हणून जोडलेः $userId';
  }

  @override
  String get defaultWorkspace => 'डिफॉल्ट वर्कस्पेस';

  @override
  String get tasksCreatedInWorkspace => 'कार्य या वर्कस्पेसमध्ये तयार केले जातील';

  @override
  String get defaultProjectOptional => 'डिफॉल्ट प्रोजेक्ट (वैकल्पिक)';

  @override
  String get leaveUnselectedTasks => 'प्रोजेक्ट शिवाय कार्य तयार करण्यासाठी निवडलेले सोडा';

  @override
  String get noProjectsInWorkspace => 'या वर्कस्पेसमध्ये कोणत्याही प्रोजेक्ट सापडले नाहीत';

  @override
  String get conversationTimeoutDesc => 'संभाषण स्वतः समाप्त करण्यापूर्वी शांतताकालचे अपेक्षा कितपत करायचे ते निवडा:';

  @override
  String get timeout2Minutes => '2 मिनिटे';

  @override
  String get timeout2MinutesDesc => '2 मिनिटे शांतताकाल अंतर्गत संभाषण समाप्त करा';

  @override
  String get timeout5Minutes => '5 मिनिटे';

  @override
  String get timeout5MinutesDesc => '5 मिनिटे शांतताकाल अंतर्गत संभाषण समाप्त करा';

  @override
  String get timeout10Minutes => '10 मिनिटे';

  @override
  String get timeout10MinutesDesc => '10 मिनिटे शांतताकाल अंतर्गत संभाषण समाप्त करा';

  @override
  String get timeout30Minutes => '30 मिनिटे';

  @override
  String get timeout30MinutesDesc => '30 मिनिटे शांतताकाल अंतर्गत संभाषण समाप्त करा';

  @override
  String get timeout4Hours => '4 तास';

  @override
  String get timeout4HoursDesc => '4 तास शांतताकाल अंतर्गत संभाषण समाप्त करा';

  @override
  String get conversationEndAfterHours => 'संभाषण आता 4 तास शांतताकाल अंतर्गत समाप्त होतील';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'संभाषण आता $minutes मिनिटे शांतताकाल अंतर्गत समाप्त होतील';
  }

  @override
  String get tellUsPrimaryLanguage => 'आमच्या सांगा आपली प्राथमिक भाषा';

  @override
  String get languageForTranscription => 'तीक्ष्ण ट्रांसक्रिप्शन आणि व्यक्तिगत अनुभवासाठी आपली भाषा सेट करा.';

  @override
  String get singleLanguageModeInfo => 'एकल भाषा मोड सक्षम आहे. उच्च अचूकतेसाठी अनुवाद अक्षम आहे.';

  @override
  String get searchLanguageHint => 'भाषा नाम किंवा कोडने शोधा';

  @override
  String get noLanguagesFound => 'कोणतीही भाषा सापडली नाही';

  @override
  String get skip => 'वगळा';

  @override
  String languageSetTo(String language) {
    return 'भाषा $language वर सेट केली गेली';
  }

  @override
  String get failedToSetLanguage => 'भाषा सेट करण्यात अयशस्वी';

  @override
  String appSettings(String appName) {
    return '$appName सेटिंग्ज';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName पासून डिस्कनेक्ट करायचे?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'यामुळे आपली $appName प्रमाणीकरण हटवली जाईल. पुन्हा वापरण्यासाठी आपल्याला पुन्हा जोडणे आवश्यक असेल.';
  }

  @override
  String connectedToApp(String appName) {
    return '$appName ला जोडलेले';
  }

  @override
  String get account => 'खाते';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'आपली कृती आयटम्स आपल्या $appName खात्यासह सिंक केली जातील';
  }

  @override
  String get defaultSpace => 'डिफॉल्ट स्पेस';

  @override
  String get selectSpaceInWorkspace => 'आपल्या वर्कस्पेसमध्ये स्पेस निवडा';

  @override
  String get noSpacesInWorkspace => 'या वर्कस्पेसमध्ये कोणती स्पेस सापडली नाही';

  @override
  String get defaultList => 'डिफॉल्ट सूची';

  @override
  String get tasksAddedToList => 'कार्य या सूचीमध्ये जोडली जातील';

  @override
  String get noListsInSpace => 'या स्पेसमध्ये कोणत्याही सूची सापडली नाही';

  @override
  String failedToLoadRepos(String error) {
    return 'रेपोजिटरी लोड करण्यात अयशस्वी: $error';
  }

  @override
  String get defaultRepoSaved => 'डिफॉल्ट रेपोजिटरी सेव केली गेली';

  @override
  String get failedToSaveDefaultRepo => 'डिफॉल्ट रेपोजिटरी सेव करण्यात अयशस्वी';

  @override
  String get defaultRepository => 'डिफॉल्ट रेपोजिटरी';

  @override
  String get selectDefaultRepoDesc =>
      'समस्या तयार करण्यासाठी डिफॉल्ट रेपोजिटरी निवडा. आपण समस्या तयार करताना तरीही वेगळी रेपोजिटरी निर्दिष्ट करू शकता.';

  @override
  String get noReposFound => 'कोणती रेपोजिटरी सापडली नाही';

  @override
  String get private => 'खाजगी';

  @override
  String updatedDate(String date) {
    return '$date अपडेट केलं';
  }

  @override
  String get yesterday => 'काल';

  @override
  String daysAgo(int count) {
    return '$count दिवस आधी';
  }

  @override
  String get oneWeekAgo => '1 आठवड्याआधी';

  @override
  String weeksAgo(int count) {
    return '$count आठवडे आधी';
  }

  @override
  String get oneMonthAgo => '1 महिन्याआधी';

  @override
  String monthsAgo(int count) {
    return '$count महिने आधी';
  }

  @override
  String get issuesCreatedInRepo => 'समस्या आपल्या डिफॉल्ट रेपोजिटरीमध्ये तयार केली जातील';

  @override
  String get taskIntegrations => 'कार्य समन्वय';

  @override
  String get configureSettings => 'सेटिंग्ज कॉन्फिगर करा';

  @override
  String get completeAuthBrowser =>
      'कृपया आपल्या ब्राउজरमध्ये प्रमाणीकरण पूर्ण करा. पूर्ण झाल्यानंतर, अॅपमध्ये परत या.';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName प्रमाणीकरण सुरू करण्यात अयशस्वी';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appName ला जोडा';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'आपल्या $appName खात्यामध्ये कार्य तयार करण्यासाठी Omi ला अधिकृत करणे आवश्यक आहे. हे आपल्या ब्राउজर प्रमाणीकरणासाठी खुले करेल.';
  }

  @override
  String get continueButton => 'सुरू ठेवा';

  @override
  String appIntegration(String appName) {
    return '$appName इंटीग्रेशन';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName सह इंटीग्रेशन लवकरच येतं! आम्ही आपल्याला अधिक कार्य व्यवस्थापन पर्याय आणण्यासाठी कठोर परिश्रम करत आहोत.';
  }

  @override
  String get gotIt => 'समजले';

  @override
  String get tasksExportedOneApp => 'कार्य एका वेळी एका अॅपमध्ये निर्यात केली जाऊ शकतात.';

  @override
  String get completeYourUpgrade => 'आपल्या अपग्रेड पूर्ण करा';

  @override
  String get importConfiguration => 'कॉन्फिगरेशन आयात करा';

  @override
  String get exportConfiguration => 'कॉन्फिगरेशन निर्यात करा';

  @override
  String get bringYourOwn => 'आपले स्वतःचे आणा';

  @override
  String get payYourSttProvider => 'Omi मुक्तपणे वापरा. आपण केवळ आपल्या STT प्रदाता ला थेट भुगतान करा.';

  @override
  String get freeMinutesMonth => '1,200 मुक्त मिनिटे/महिना समाविष्ट. अमर्यादित ';

  @override
  String get omiUnlimited => 'Omi अमर्यादित';

  @override
  String get hostRequired => 'होस्ट आवश्यक आहे';

  @override
  String get validPortRequired => 'वैध पोर्ट आवश्यक आहे';

  @override
  String get validWebsocketUrlRequired => 'वैध WebSocket URL आवश्यक आहे (wss://)';

  @override
  String get apiUrlRequired => 'API URL आवश्यक आहे';

  @override
  String get apiKeyRequired => 'API की आवश्यक आहे';

  @override
  String get invalidJsonConfig => 'अवैध JSON कॉन्फिगरेशन';

  @override
  String errorSaving(String error) {
    return 'सेव करण्यात त्रुटी: $error';
  }

  @override
  String get configCopiedToClipboard => 'कॉन्फिगरेशन क्लिपबोर्डला कॉपी केले गेले';

  @override
  String get pasteJsonConfig => 'आपला JSON कॉन्फिगरेशन खाली पेस्ट करा:';

  @override
  String get addApiKeyAfterImport => 'आयात केल्यानंतर आपल्याला आपली स्वतःची API की जोडणे आवश्यक असेल';

  @override
  String get paste => 'पेस्ट करा';

  @override
  String get import => 'आयात करा';

  @override
  String get invalidProviderInConfig => 'कॉन्फिगरेशनमध्ये अवैध प्रदाता';

  @override
  String importedConfig(String providerName) {
    return '$providerName कॉन्फिगरेशन आयात केली गेली';
  }

  @override
  String invalidJson(String error) {
    return 'अवैध JSON: $error';
  }

  @override
  String get provider => 'प्रदाता';

  @override
  String get live => 'लाइव्ह';

  @override
  String get onDevice => 'उपकरणावर';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'आपला STT HTTP एंडपॉइंट प्रविष्ट करा';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'आपला लाइव्ह STT WebSocket एंडपॉइंट प्रविष्ट करा';

  @override
  String get apiKey => 'API की';

  @override
  String get enterApiKey => 'आपली API की प्रविष्ट करा';

  @override
  String get storedLocallyNeverShared => 'स्थानिकरित्या संग्रहीत, कधीही शेअर केले जात नाही';

  @override
  String get host => 'होस्ट';

  @override
  String get port => 'पोर्ट';

  @override
  String get advanced => 'प्रगत';

  @override
  String get configuration => 'कॉन्फिगरेशन';

  @override
  String get requestConfiguration => 'विनंती कॉन्फिगरेशन';

  @override
  String get responseSchema => 'प्रतिक्रिया स्कीमा';

  @override
  String get modified => 'सुधारलेले';

  @override
  String get resetRequestConfig => 'विनंती कॉन्फिगरेशन डिफॉल्टमध्ये रीसेट करा';

  @override
  String get logs => 'लॉग्ज';

  @override
  String get logsCopied => 'लॉग्ज कॉपी केले';

  @override
  String get noLogsYet => 'अद्याप कोणत्याही लॉग्ज नाहीत. कस्टम STT क्रियाकलाप पाहण्यासाठी रेकॉर्डिंग सुरू करा.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device $reason वापरते. Omi वापरला जाईल.';
  }

  @override
  String get omiTranscription => 'Omi ट्रांसक्रिप्शन';

  @override
  String get bestInClassTranscription => 'शून्य सेटअप सह सर्वोत्कृष्ट ट्रांसक्रिप्शन';

  @override
  String get instantSpeakerLabels => 'तात्काळ स्पीकर लेबल्स';

  @override
  String get languageTranslation => '100+ भाषांचे अनुवाद';

  @override
  String get optimizedForConversation => 'संभाषणासाठी अनुकूलित';

  @override
  String get autoLanguageDetection => 'स्वतः भाषा शोध';

  @override
  String get highAccuracy => 'उच्च अचूकता';

  @override
  String get privacyFirst => 'गोपनीयता प्रथम';

  @override
  String get saveChanges => 'बदल सेव करा';

  @override
  String get resetToDefault => 'डिफॉल्टमध्ये रीसेट करा';

  @override
  String get viewTemplate => 'टेम्पलेट पहा';

  @override
  String get trySomethingLike => 'अशा काहीचा प्रयत्न करा...';

  @override
  String get tryIt => 'प्रयत्न करा';

  @override
  String get creatingPlan => 'योजना तयार करत आहे';

  @override
  String get developingLogic => 'लॉजिक विकसित करत आहे';

  @override
  String get designingApp => 'अॅप डिজाइन करत आहे';

  @override
  String get generatingIconStep => 'आयकन तयार करत आहे';

  @override
  String get finalTouches => 'अंतिम स्पर्श';

  @override
  String get processing => 'प्रक्रिया करत आहे...';

  @override
  String get features => 'वैशिष्ट्ये';

  @override
  String get creatingYourApp => 'आपली अॅप तयार करत आहे...';

  @override
  String get generatingIcon => 'आयकन तयार करत आहे...';

  @override
  String get whatShouldWeMake => 'आम्ही काय तयार करुशकतो?';

  @override
  String get appName => 'अॅप नाव';

  @override
  String get description => 'वर्णन';

  @override
  String get publicLabel => 'सार्वजनिक';

  @override
  String get privateLabel => 'खाजगी';

  @override
  String get free => 'मुक्त';

  @override
  String get perMonth => '/ महिना';

  @override
  String get tailoredConversationSummaries => 'तयार केलेली संभाषण सारांश';

  @override
  String get customChatbotPersonality => 'कस्टम चॅटबॉट व्यक्तिमत्व';

  @override
  String get makePublic => 'सार्वजनिक बनवा';

  @override
  String get anyoneCanDiscover => 'कोणीही आपली अॅप शोधू शकतो';

  @override
  String get onlyYouCanUse => 'केवळ आपण या अॅप वापरू शकता';

  @override
  String get paidApp => 'सशुल्क अॅप';

  @override
  String get usersPayToUse => 'वापरकर्ते आपली अॅप वापरण्यासाठी भुगतान करतात';

  @override
  String get freeForEveryone => 'सर्वांसाठी मुक्त';

  @override
  String get perMonthLabel => '/ महिना';

  @override
  String get creating => 'तयार करत आहे...';

  @override
  String get createApp => 'अॅप तयार करा';

  @override
  String get searchingForDevices => 'उपकरण शोधत आहे...';

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
  String get pairingSuccessful => 'जोडणी यशस्वी';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch ला जोडण्यात त्रुटी: $error';
  }

  @override
  String get dontShowAgain => 'पुन्हा दाखवू नका';

  @override
  String get iUnderstand => 'मी समजले';

  @override
  String get enableBluetooth => 'Bluetooth सक्षम करा';

  @override
  String get bluetoothNeeded =>
      'Omi आपल्या पहनने केल्या जाणार्‍या उपकरणाला जोडण्यासाठी Bluetooth आवश्यक आहे. कृपया Bluetooth सक्षम करा आणि पुन्हा प्रयत्न करा.';

  @override
  String get contactSupport => 'समर्थन संपर्क करायचे?';

  @override
  String get connectLater => 'नंतर जोडा';

  @override
  String get grantPermissions => 'परवानग्या द्या';

  @override
  String get backgroundActivity => 'पार्श्वभूमी क्रियाकलाप';

  @override
  String get backgroundActivityDesc => 'बेहतर स्थिरतेसाठी Omi ला पार्श्वभूमीमध्ये चालू करा';

  @override
  String get locationAccess => 'स्थान प्रवेश';

  @override
  String get locationAccessDesc => 'पूर्ण अनुभवासाठी पार्श्वभूमी स्थान सक्षम करा';

  @override
  String get notifications => 'सूचना';

  @override
  String get notificationsDesc => 'सूचित राहण्यासाठी सूचना सक्षम करा';

  @override
  String get locationServiceDisabled => 'स्थान सेवा अक्षम';

  @override
  String get locationServiceDisabledDesc =>
      'स्थान सेवा अक्षम आहे. कृपया सेटिंग्ज > गोपनीयता आणि सुरक्षा > स्थान सेवा वर जा आणि सक्षम करा';

  @override
  String get backgroundLocationDenied => 'पार्श्वभूमी स्थान प्रवेश नाकारला';

  @override
  String get backgroundLocationDeniedDesc =>
      'कृपया डिव्हाइस सेटिंग्जमध्ये जा आणि स्थान परवानगी \"नेहमी परवानगी द्या\" वर सेट करा';

  @override
  String get lovingOmi => 'Omi आवडतंय?';

  @override
  String get leaveReviewIos =>
      'App Store मध्ये पुनरावलोकन सोडून आम्हाला अधिक लोकांपर्यंत पोहोचण्यास मदत करा. आपल्या प्रतिक्रिया आमच्यासाठी खूप महत्वाची आहे!';

  @override
  String get leaveReviewAndroid =>
      'Google Play Store मध्ये पुनरावलोकन सोडून आम्हाला अधिक लोकांपर्यंत पोहोचण्यास मदत करा. आपल्या प्रतिक्रिया आमच्यासाठी खूप महत्वाची आहे!';

  @override
  String get rateOnAppStore => 'App Store वर रेट करा';

  @override
  String get rateOnGooglePlay => 'Google Play वर रेट करा';

  @override
  String get maybeLater => 'कदाचित नंतर';

  @override
  String get speechProfileIntro => 'Omi आपल्या लक्ष्य आणि आपल्या व्हॉइस शिकणे आवश्यक आहे. आपण ते नंतर सुधारू शकता.';

  @override
  String get getStarted => 'सुरुवात करा';

  @override
  String get allDone => 'सर्व पूर्ण!';

  @override
  String get keepGoing => 'सुरू ठेवा, आप खूप चांगले आहात';

  @override
  String get skipThisQuestion => 'हा प्रश्न वगळा';

  @override
  String get skipForNow => 'आताच वगळा';

  @override
  String get connectionError => 'कनेक्शन त्रुटी';

  @override
  String get connectionErrorDesc =>
      'सर्व्हरला जोडण्यात अयशस्वी. कृपया आपल्या इंटरनेट कनेक्शन तपासा आणि पुन्हा प्रयत्न करा.';

  @override
  String get invalidRecordingMultipleSpeakers => 'अमान्य रेकॉर्डिंग शोधली';

  @override
  String get multipleSpeakersDesc =>
      'असे दिसते की रेकॉर्डिंगमध्ये अनेक स्पीकर आहेत. कृपया खाली की शांत जागेत आहात याची खात्री करा आणि पुन्हा प्रयत्न करा.';

  @override
  String get tooShortDesc => 'पुरेशी भाषण शोधली नाही. कृपया अधिक बोला आणि पुन्हा प्रयत्न करा.';

  @override
  String get invalidRecordingDesc => 'कृपया खात्री करा की आपण कमीत कमी 5 सेकंद आणि 90 पेक्षा जास्त नाही बोलतात.';

  @override
  String get areYouThere => 'आप तेथे आहात का?';

  @override
  String get noSpeechDesc =>
      'आम्ही कोणतीही भाषण शोधू शकलो नाही. कृपया कमीत कमी 10 सेकंद आणि 3 मिनिटांपेक्षा जास्त नाही बोलण्याची खात्री करा.';

  @override
  String get connectionLost => 'कनेक्शन हरवले';

  @override
  String get connectionLostDesc => 'कनेक्शन खंडित झाले. कृपया आपल्या इंटरनेट कनेक्शन तपासा आणि पुन्हा प्रयत्न करा.';

  @override
  String get tryAgain => 'पुन्हा प्रयत्न करा';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass जोडा';

  @override
  String get continueWithoutDevice => 'डिव्हाइस शिवाय सुरू करा';

  @override
  String get permissionsRequired => 'परवानग्या आवश्यक';

  @override
  String get permissionsRequiredDesc =>
      'या अॅपला योग्यरित्या कार्य करण्यासाठी Bluetooth आणि स्थान परवानग्या आवश्यक आहेत. कृपया सेटिंग्जमध्ये सक्षम करा.';

  @override
  String get openSettings => 'सेटिंग्ज खोला';

  @override
  String get wantDifferentName => 'अन्य काहीतरी नावाने जाऊ इच्छिता?';

  @override
  String get whatsYourName => 'आपले नाव काय आहे?';

  @override
  String get speakTranscribeSummarize => 'बोला. ट्रांसक्राइब करा. सारांश करा.';

  @override
  String get signInWithApple => 'Apple सह साइन इन करा';

  @override
  String get signInWithGoogle => 'Google सह साइन इन करा';

  @override
  String get byContinuingAgree => 'सुरू करून, आपण आमच्या ';

  @override
  String get termsOfUse => 'सेवेच्या अटी';

  @override
  String get omiYourAiCompanion => 'Omi - आपली AI साथी';

  @override
  String get captureEveryMoment => 'प्रत्येक क्षण कॅप्चर करा. AI-पॉवर्ड\nसारांश मिळवा. पुन्हा कधीही नोट्स घेऊ नका.';

  @override
  String get appleWatchSetup => 'Apple Watch सेटअप';

  @override
  String get permissionRequestedExclaim => 'परवानगी विनंती!';

  @override
  String get microphonePermission => 'मायक्रोफोन परवानगी';

  @override
  String get permissionGrantedNow => 'परवानगी दिली! आता:\n\nआपल्या वॉचवर Omi अॅप खोला आणि खाली \"सुरू करा\" टॅप करा';

  @override
  String get needMicrophonePermission =>
      'आम्हाला मायक्रोफोन परवानगी आवश्यक आहे.\n\n1. \"परवानगी दे\" टॅप करा\n2. आपल्या iPhone वर परवानगी द्या\n3. वॉच अॅप बंद होईल\n4. पुन्हा खोला आणि \"सुरू करा\" टॅप करा';

  @override
  String get grantPermissionButton => 'परवानगी द्या';

  @override
  String get needHelp => 'मदत हवी?';

  @override
  String get troubleshootingSteps =>
      'समस्या निवारणः\n\n1. Omi आपल्या वॉचवर इंस्टॉल आहे याची खात्री करा\n2. आपल्या वॉचवर Omi अॅप खोला\n3. परवानगी पॉपअप शोधा\n4. विचारले गेल्यावर \"परवानगी द्या\" टॅप करा\n5. आपल्या वॉचवर अॅप बंद होईल - ते पुन्हा खोला\n6. आपल्या iPhone वर परत या आणि \"सुरू करा\" टॅप करा';

  @override
  String get recordingStartedSuccessfully => 'रेकॉर्डिंग यशस्वीरित्या सुरू झाली!';

  @override
  String get permissionNotGrantedYet =>
      'परवानगी अद्याप दिली नाही. कृपया खात्री करा की आपण मायक्रोफोन प्रवेश परवानगी दिली आणि आपल्या वॉचवर अॅप पुन्हा खोली.';

  @override
  String errorRequestingPermission(String error) {
    return 'परवानगी विनंती करण्यात त्रुटीः $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'रेकॉर्डिंग सुरू करण्यात त्रुटीः $error';
  }

  @override
  String get selectPrimaryLanguage => 'आपली प्राथमिक भाषा निवडा';

  @override
  String get languageBenefits => 'तीक्ष्ण ट्रांसक्रिप्शन आणि व्यक्तिगत अनुभवासाठी आपली भाषा सेट करा';

  @override
  String get whatsYourPrimaryLanguage => 'आपली प्राथमिक भाषा काय आहे?';

  @override
  String get selectYourLanguage => 'आपली भाषा निवडा';

  @override
  String get personalGrowthJourney => 'आपल्या व्यक्तिगत वाढीचा प्रवास AI सह जो आपल्या प्रत्येक शब्दाऐका घेतो.';

  @override
  String get actionItemsTitle => 'To-Do\'s';

  @override
  String get actionItemsDescription =>
      'संपादित करण्यासाठी टॅप करा • निवडण्यासाठी लांब प्रेस करा • क्रियांसाठी स्वाइप करा';

  @override
  String get tabToDo => 'करायचे';

  @override
  String get tabDone => 'पूर्ण';

  @override
  String get tabOld => 'जुने';

  @override
  String get emptyTodoMessage => '🎉 सर्व पूर्ण!\nकोणतीही अपेक्षित कृती आयटम नाही';

  @override
  String get emptyDoneMessage => 'अद्याप कोणत्याही पूर्ण आयटम नाहीत';

  @override
  String get emptyOldMessage => '✅ कोणत्याही जुन्या कार्य नाहीत';

  @override
  String get noItems => 'कोणत्याही आयटम नाहीत';

  @override
  String get actionItemMarkedIncomplete => 'कृती आयटम अपूर्ण म्हणून चिन्हांकित';

  @override
  String get actionItemCompleted => 'कृती आयटम पूर्ण';

  @override
  String get deleteActionItemTitle => 'कृती आयटम हटवा';

  @override
  String get deleteActionItemMessage => 'आपल्याला खरोखर या कृती आयटम हटवायचे आहे?';

  @override
  String get deleteSelectedItemsTitle => 'निवडलेली आयटम हटवा';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'कृती आयटम \"$description\" हटवली गेली';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'कृती आयटम हटवण्यात अयशस्वी';

  @override
  String get failedToDeleteItems => 'आयटम हटवण्यात अयशस्वी';

  @override
  String get failedToDeleteSomeItems => 'काही आयटम हटवण्यात अयशस्वी';

  @override
  String get welcomeActionItemsTitle => 'कृती आयटमसाठी तयार';

  @override
  String get welcomeActionItemsDescription =>
      'आपला AI संभाषणातून कार्य आणि to-do स्वतः काढून घेणार. ते येथे दिसतील जेव्हा तयार होतील.';

  @override
  String get autoExtractionFeature => 'संभाषणातून स्वतः काढून घेतले';

  @override
  String get editSwipeFeature => 'संपादित करण्यासाठी टॅप करा, पूर्ण किंवा हटवण्यासाठी स्वाइप करा';

  @override
  String itemsSelected(int count) {
    return '$count निवडले';
  }

  @override
  String get selectAll => 'सर्व निवडा';

  @override
  String get deleteSelected => 'निवडलेले हटवा';

  @override
  String get searchMemories => 'स्मृती शोधा...';

  @override
  String get memoryDeleted => 'स्मृती हटवली गेली.';

  @override
  String get undo => 'पूर्ववत् करा';

  @override
  String get noMemoriesYet => '🧠 अद्याप कोणत्याही स्मृती नाही';

  @override
  String get noAutoMemories => 'अद्याप कोणत्याही स्वतः-काढून घेतलेली स्मृती नाही';

  @override
  String get noManualMemories => 'अद्याप कोणत्याही व्यक्तिगत स्मृती नाही';

  @override
  String get noMemoriesInCategories => 'या श्रेणींमध्ये कोणत्याही स्मृती नाही';

  @override
  String get noMemoriesFound => '🔍 कोणत्याही स्मृती सापडली नाही';

  @override
  String get addFirstMemory => 'आपली पहिली स्मृती जोडा';

  @override
  String get clearMemoryTitle => 'Omi ची स्मृती स्पष्ट करा';

  @override
  String get clearMemoryMessage =>
      'आपल्याला खरोखर Omi ची स्मृती स्पष्ट करायची आहे? हे क्रिया पूर्ववत् केली जाऊ शकत नाही.';

  @override
  String get clearMemoryButton => 'स्मृती स्पष्ट करा';

  @override
  String get memoryClearedSuccess => 'आपल्याबद्दल Omi ची स्मृती साफ केली गेली';

  @override
  String get noMemoriesToDelete => 'हटवण्यासाठी कोणत्याही स्मृती नाहीत';

  @override
  String get createMemoryTooltip => 'नवीन स्मृती तयार करा';

  @override
  String get createActionItemTooltip => 'नवीन कृती आयटम तयार करा';

  @override
  String get memoryManagement => 'स्मृती व्यवस्थापन';

  @override
  String get filterMemories => 'स्मृती फिल्टर करा';

  @override
  String totalMemoriesCount(int count) {
    return 'आपल्याकडे $count एकूण स्मृती आहे';
  }

  @override
  String get publicMemories => 'सार्वजनिक स्मृती';

  @override
  String get privateMemories => 'खाजगी स्मृती';

  @override
  String get makeAllPrivate => 'सर्व स्मृती खाजगी बनवा';

  @override
  String get makeAllPublic => 'सर्व स्मृती सार्वजनिक बनवा';

  @override
  String get deleteAllMemories => 'सर्व स्मृती हटवा';

  @override
  String get allMemoriesPrivateResult => 'सर्व स्मृती आता खाजगी आहेत';

  @override
  String get allMemoriesPublicResult => 'सर्व स्मृती आता सार्वजनिक आहेत';

  @override
  String get newMemory => '✨ नवीन स्मृती';

  @override
  String get editMemory => '✏️ स्मृती संपादित करा';

  @override
  String get memoryContentHint => 'मला आयस्क्रीम खाण्यास आवडते...';

  @override
  String get failedToSaveMemory => 'सेव करण्यात अयशस्वी. कृपया आपल्या कनेक्शन तपासा.';

  @override
  String get saveMemory => 'स्मृती सेव करा';

  @override
  String get retry => 'पुन्हा प्रयत्न करा';

  @override
  String get createActionItem => 'कृती आयटम तयार करा';

  @override
  String get editActionItem => 'कृती आयटम संपादित करा';

  @override
  String get actionItemDescriptionHint => 'काय करायचे आहे?';

  @override
  String get actionItemDescriptionEmpty => 'कृती आयटम वर्णन रिक्त असू शकत नाही.';

  @override
  String get actionItemUpdated => 'कृती आयटम अपडेट केली गेली';

  @override
  String get failedToUpdateActionItem => 'कृती आयटम अपडेट करण्यात अयशस्वी';

  @override
  String get actionItemCreated => 'कृती आयटम तयार केली गेली';

  @override
  String get failedToCreateActionItem => 'कृती आयटम तयार करण्यात अयशस्वी';

  @override
  String get dueDate => 'नियत तारीख';

  @override
  String get time => 'वेळ';

  @override
  String get addDueDate => 'नियत तारीख जोडा';

  @override
  String get pressDoneToSave => 'सेव करण्यासाठी पूर्ण दाबा';

  @override
  String get pressDoneToCreate => 'तयार करण्यासाठी पूर्ण दाबा';

  @override
  String get filterAll => 'सर्व';

  @override
  String get filterSystem => 'आपल्याबद्दल';

  @override
  String get filterInteresting => 'अंतर्दृष्टी';

  @override
  String get filterManual => 'व्यक्तिगत';

  @override
  String get completed => 'पूर्ण';

  @override
  String get markComplete => 'पूर्ण म्हणून चिन्हांकित करा';

  @override
  String get actionItemDeleted => 'कृती आयटम हटवली गेली';

  @override
  String get failedToDeleteActionItem => 'कृती आयटम हटवण्यात अयशस्वी';

  @override
  String get deleteActionItemConfirmTitle => 'कृती आयटम हटवा';

  @override
  String get deleteActionItemConfirmMessage => 'आपल्याला खरोखर या कृती आयटम हटवायचे आहे?';

  @override
  String get appLanguage => 'अॅप भाषा';

  @override
  String get appInterfaceSectionTitle => 'अॅप इंटरफेस';

  @override
  String get speechTranscriptionSectionTitle => 'भाषण आणि ट्रांसक्रिप्शन';

  @override
  String get languageSettingsHelperText =>
      'अॅप भाषा मेनू आणि बटण बदलते. भाषण भाषा आपल्या रेकॉर्डिंग कसे ट्रांसक्राइब केली जाते यावर परिणाम करते.';

  @override
  String get translationNotice => 'अनुवाद सूचना';

  @override
  String get translationNoticeMessage =>
      'Omi संभाषण आपल्या प्राथमिक भाषेमध्ये अनुवादित करते. सेटिंग्ज → प्रोफाइल मध्ये कधीही अपडेट करा.';

  @override
  String get pleaseCheckInternetConnection => 'कृपया आपल्या इंटरनेट कनेक्शन तपासा आणि पुन्हा प्रयत्न करा';

  @override
  String get pleaseSelectReason => 'कृपया कारण निवडा';

  @override
  String get tellUsMoreWhatWentWrong => 'काय चुकले याबद्दल आमच्या अधिक सांगा...';

  @override
  String get selectText => 'मजकूर निवडा';

  @override
  String maximumGoalsAllowed(int count) {
    return 'जास्तीत जास्त $count लक्ष्य अनुमति';
  }

  @override
  String get conversationCannotBeMerged => 'या संभाषणाचे विलीन करू शकत नाही (लॉक केलेले किंवा आधीच विलीन होत आहे)';

  @override
  String get pleaseEnterFolderName => 'कृपया फोल्डर नाव प्रविष्ट करा';

  @override
  String get failedToCreateFolder => 'फोल्डर तयार करण्यात अयशस्वी';

  @override
  String get failedToUpdateFolder => 'फोल्डर अपडेट करण्यात अयशस्वी';

  @override
  String get folderName => 'फोल्डर नाव';

  @override
  String get descriptionOptional => 'वर्णन (वैकल्पिक)';

  @override
  String get failedToDeleteFolder => 'फोल्डर हटाण्यात अयशस्वी';

  @override
  String get editFolder => 'फोल्डर संपादित करा';

  @override
  String get deleteFolder => 'फोल्डर हटवा';

  @override
  String get transcriptCopiedToClipboard => 'ट्रान्सक्रिप्ट क्लिपबोर्डवर कॉपी केला';

  @override
  String get summaryCopiedToClipboard => 'सारांश क्लिपबोर्डवर कॉपी केला';

  @override
  String get conversationUrlCouldNotBeShared => 'संभाषण URL सामायिक केला जाऊ शकला नाही।';

  @override
  String get urlCopiedToClipboard => 'URL क्लिपबोर्डवर कॉपी केला';

  @override
  String get exportTranscript => 'ट्रान्सक्रिप्ट निर्यात करा';

  @override
  String get exportSummary => 'सारांश निर्यात करा';

  @override
  String get exportButton => 'निर्यात करा';

  @override
  String get actionItemsCopiedToClipboard => 'कृती आयटम क्लिपबोर्डवर कॉपी केल्या गेल्या';

  @override
  String get summarize => 'सारांश दा';

  @override
  String get generateSummary => 'सारांश तयार करा';

  @override
  String get conversationNotFoundOrDeleted => 'संभाषण सापडला नाही किंवा हटवला गेला आहे';

  @override
  String get deleteMemory => 'स्मृती हटवा';

  @override
  String get thisActionCannotBeUndone => 'हे कृती पूर्ववत केली जाऊ शकत नाही।';

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
  String get noMemoriesInCategory => 'या श्रेणीत अजून कोणत्याही स्मृती नाहीत';

  @override
  String get addYourFirstMemory => 'आपली पहिली स्मृती जोडा';

  @override
  String get firmwareDisconnectUsb => 'USB जोडणी काढून टाका';

  @override
  String get firmwareUsbWarning => 'अपडेट्स दरम्यान USB कनेक्शन आपल्या डिव्हाइसचे नुकसान करू शकते।';

  @override
  String get firmwareBatteryAbove15 => 'बॅटरी १५% च्या वर';

  @override
  String get firmwareEnsureBattery => 'आपल्या डिव्हाइसमध्ये १५% बॅटरी आहे याची खात्री करा।';

  @override
  String get firmwareStableConnection => 'स्थिर कनेक्शन';

  @override
  String get firmwareConnectWifi => 'WiFi किंवा सेल्युलर वर कनेक्ट करा।';

  @override
  String failedToStartUpdate(String error) {
    return 'अपडेट सुरू करण्यात अयशस्वी: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'अपडेटपूर्वी हे सुनिश्चित करा:';

  @override
  String get confirmed => 'पुष्टी झाली!';

  @override
  String get release => 'रिलीज';

  @override
  String get slideToUpdate => 'अपडेट करण्यासाठी स्लाइड करा';

  @override
  String copiedToClipboard(String title) {
    return '$title क्लिपबोर्डवर कॉपी केला';
  }

  @override
  String get batteryLevel => 'बॅटरी स्तर';

  @override
  String get charging => 'चार्ज होत आहे';

  @override
  String get productUpdate => 'उत्पादन अपडेट';

  @override
  String get offline => 'ऑफलाइन';

  @override
  String get available => 'उपलब्ध';

  @override
  String get unpairDeviceDialogTitle => 'डिव्हाइस जोडणी काढून टाका';

  @override
  String get unpairDeviceDialogMessage =>
      'हे डिव्हाइसची जोडणी काढून टाकेल ज्यामुळे ते दुसऱ्या फोनशी कनेक्ट केले जाऊ शकेल. प्रक्रिया पूर्ण करण्यासाठी तुम्हाला सेटिंग्ज > ब्लूटूथ वर जाऊन डिव्हाइस विसरावे लागेल.';

  @override
  String get unpair => 'जोडणी काढून टाका';

  @override
  String get unpairAndForgetDevice => 'डिव्हाइसची जोडणी काढून टाका आणि विसरा';

  @override
  String get unknownDevice => 'अज्ञात';

  @override
  String get unknown => 'अज्ञात';

  @override
  String get productName => 'उत्पादन नाव';

  @override
  String get serialNumber => 'सीरिज संख्या';

  @override
  String get connected => 'कनेक्ट केलेला';

  @override
  String get privacyPolicyTitle => 'गोपनीयता धोरण';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label कॉपी केला';
  }

  @override
  String get noApiKeysYet => 'अजून कोणत्याही API की नाहीत';

  @override
  String get createKeyToGetStarted => 'सुरू करण्यासाठी की तयार करा';

  @override
  String get configureSttProvider => 'STT प्रदाता संरचित करा';

  @override
  String get setWhenConversationsAutoEnd => 'संभाषण कधी स्वयंचलितपणे समाप्त होतील हे सेट करा';

  @override
  String get importDataFromOtherSources => 'इतर स्रोतांकडून डेटा आयात करा';

  @override
  String get debugAndDiagnostics => 'डीबग आणि निदान';

  @override
  String get autoDeletesAfter3Days => '३ दिवसांनंतर स्वयंचलितपणे हटवले जाते।';

  @override
  String get helpsDiagnoseIssues => 'समस्या निदान करण्यात मदत करते';

  @override
  String get exportStartedMessage => 'निर्यात सुरू झाली. हे काही सेकंद घेऊ शकते...';

  @override
  String get exportConversationsToJson => 'संभाषण JSON फाइलमध्ये निर्यात करा';

  @override
  String get knowledgeGraphDeletedSuccess => 'ज्ञान आलेख यशस्वीरित्या हटवला गेला';

  @override
  String failedToDeleteGraph(String error) {
    return 'आलेख हटाण्यात अयशस्वी: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'सर्व नोड्स आणि कनेक्शन साफ करा';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.json मध्ये जोडा';

  @override
  String get connectAiAssistantsToData => 'AI सहायकांना आपल्या डेटाशी कनेक्ट करा';

  @override
  String get useYourMcpApiKey => 'आपली MCP API की वापरा';

  @override
  String get realTimeTranscript => 'रिअल-टाइम ट्रान्सक्रिप्ट';

  @override
  String get experimental => 'प्रायोगिक';

  @override
  String get transcriptionDiagnostics => 'ट्रांसक्रिप्शन निदान';

  @override
  String get detailedDiagnosticMessages => 'तपशीलवार निदान संदेश';

  @override
  String get autoCreateSpeakers => 'स्वयंचलितपणे व्यक्तीची निर्मिती करा';

  @override
  String get autoCreateWhenNameDetected => 'नाव सापडल्यावर स्वयंचलितपणे निर्मिती करा';

  @override
  String get followUpQuestions => 'अनुवर्तन प्रश्न';

  @override
  String get suggestQuestionsAfterConversations => 'संभाषणानंतर प्रश्न सुचवा';

  @override
  String get goalTracker => 'लक्ष्य ट्रैकर';

  @override
  String get trackPersonalGoalsOnHomepage => 'मुख्यपृष्ठावर आपल्या व्यक्तिगत लक्ष्यांचा मागोवा घ्या';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'कृती आयटमचे वर्णन रिक्त असू शकत नाही';

  @override
  String get saved => 'जतन केला';

  @override
  String get overdue => 'मुदतीचा अंत झाली';

  @override
  String get failedToUpdateDueDate => 'मुदत अपडेट करण्यात अयशस्वी';

  @override
  String get markIncomplete => 'अपूर्ण म्हणून चिन्हांकित करा';

  @override
  String get editDueDate => 'मुदत संपादित करा';

  @override
  String get setDueDate => 'मुदत सेट करा';

  @override
  String get clearDueDate => 'मुदत साफ करा';

  @override
  String get failedToClearDueDate => 'मुदत साफ करण्यात अयशस्वी';

  @override
  String get mondayAbbr => 'सोमवार';

  @override
  String get tuesdayAbbr => 'मंगळवार';

  @override
  String get wednesdayAbbr => 'बुधवार';

  @override
  String get thursdayAbbr => 'गुरुवार';

  @override
  String get fridayAbbr => 'शुक्रवार';

  @override
  String get saturdayAbbr => 'शनिवार';

  @override
  String get sundayAbbr => 'रविवार';

  @override
  String get howDoesItWork => 'हे कसे काम करते?';

  @override
  String get sdCardSyncDescription => 'SD कार्ड सिंक आपल्या SD कार्डवरील स्मृती अ‍ॅपमध्ये आयात करेल';

  @override
  String get checksForAudioFiles => 'SD कार्डवर ऑडिओ फाइलांची तपासणी करते';

  @override
  String get omiSyncsAudioFiles => 'Omi नंतर ऑडिओ फाइलांना सर्व्हरशी सिंक करते';

  @override
  String get serverProcessesAudio => 'सर्व्हर ऑडिओ फाइलांची प्रक्रिया करते आणि स्मृती तयार करते';

  @override
  String get youreAllSet => 'तुम्ही सब्कुशीत आहात!';

  @override
  String get welcomeToOmiDescription =>
      'Omi मध्ये स्वागत आहे! आपला AI सहचर संभाषण, कार्य इत्यादी मध्ये आपल्याला मदत करण्यासाठी तयार आहे।';

  @override
  String get startUsingOmi => 'Omi वापरण्यास सुरुवात करा';

  @override
  String get back => 'परत';

  @override
  String get keyboardShortcuts => 'कीबोर्ड शॉर्टकट्स';

  @override
  String get toggleControlBar => 'नियंत्रण पट्टी टॉगल करा';

  @override
  String get pressKeys => 'की दाबा...';

  @override
  String get cmdRequired => '⌘ आवश्यक';

  @override
  String get invalidKey => 'अमान्य की';

  @override
  String get space => 'स्पेस';

  @override
  String get search => 'शोधा';

  @override
  String get searchPlaceholder => 'शोधा...';

  @override
  String get untitledConversation => 'शीर्षकविहीन संभाषण';

  @override
  String countRemaining(String count) {
    return '$count शिल्लक';
  }

  @override
  String get addGoal => 'लक्ष्य जोडा';

  @override
  String get editGoal => 'लक्ष्य संपादित करा';

  @override
  String get icon => 'चिन्ह';

  @override
  String get goalTitle => 'लक्ष्य शीर्षक';

  @override
  String get current => 'वर्तमान';

  @override
  String get target => 'लक्ष्य';

  @override
  String get saveGoal => 'जतन करा';

  @override
  String get goals => 'लक्ष्य';

  @override
  String get tapToAddGoal => 'लक्ष्य जोडण्यासाठी टॅप करा';

  @override
  String welcomeBack(String name) {
    return 'परत स्वागत आहे, $name';
  }

  @override
  String get yourConversations => 'आपले संभाषण';

  @override
  String get reviewAndManageConversations => 'आपल्या कॅप्चर केलेल्या संभाषणांची पुनरावलोकन करा आणि व्यवस्थापन करा';

  @override
  String get startCapturingConversations =>
      'आपल्या Omi डिव्हाइसशी संभाषण कॅप्चर करण्यास सुरुवात करा त्यांना येथे पाहण्यासाठी।';

  @override
  String get useMobileAppToCapture => 'ऑडिओ कॅप्चर करण्यासाठी आपल्या मोबाइल अ‍ॅपचा वापर करा';

  @override
  String get conversationsProcessedAutomatically => 'संभाषण स्वयंचलितपणे प्रक्रिया केली जाते';

  @override
  String get getInsightsInstantly => 'तुरंत अंतर्दृष्टी आणि सारांश मिळवा';

  @override
  String get showAll => 'सर्व दाखवा';

  @override
  String get noTasksForToday => 'आज कोणतेही कार्य नाहीत।\nOmi कडे अधिक कार्यांची विनंती करा किंवा स्वहस्ते तयार करा।';

  @override
  String get dailyScore => 'दैनिक स्कोर';

  @override
  String get dailyScoreDescription => 'अंमलबजावणीवर अधिक\nएकाग्र होण्यास मदत करण्यासाठी एक स्कोर।';

  @override
  String get searchResults => 'शोध परिणाम';

  @override
  String get actionItems => 'कृती आयटम';

  @override
  String get tasksToday => 'आज';

  @override
  String get tasksTomorrow => 'उद्या';

  @override
  String get tasksNoDeadline => 'कोणतीही मुदत नाही';

  @override
  String get tasksLater => 'नंतर';

  @override
  String get loadingTasks => 'कार्य लोड होत आहे...';

  @override
  String get tasks => 'कार्य';

  @override
  String get swipeTasksToIndent => 'इंडेंट करण्यासाठी कार्य स्वाइप करा, श्रेणीमध्ये ड्रॅग करा';

  @override
  String get create => 'तयार करा';

  @override
  String get noTasksYet => 'अजून कोणतेही कार्य नाहीत';

  @override
  String get tasksFromConversationsWillAppear =>
      'आपल्या संभाषणातील कार्य येथे दिसू शकतील।\nएक स्वहस्ते जोडण्यासाठी तयार करा क्लिक करा।';

  @override
  String get monthJan => 'जान';

  @override
  String get monthFeb => 'फेब';

  @override
  String get monthMar => 'मार्च';

  @override
  String get monthApr => 'एप्रिल';

  @override
  String get monthMay => 'मे';

  @override
  String get monthJun => 'जून';

  @override
  String get monthJul => 'जुलै';

  @override
  String get monthAug => 'ऑग';

  @override
  String get monthSep => 'सेप';

  @override
  String get monthOct => 'ऑक्ट';

  @override
  String get monthNov => 'नोव';

  @override
  String get monthDec => 'डिस';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'कृती आयटम यशस्वीरित्या अपडेट केली गेली';

  @override
  String get actionItemCreatedSuccessfully => 'कृती आयटम यशस्वीरित्या तयार केली गेली';

  @override
  String get actionItemDeletedSuccessfully => 'कृती आयटम यशस्वीरित्या हटवली गेली';

  @override
  String get deleteActionItem => 'कृती आयटम हटवा';

  @override
  String get deleteActionItemConfirmation =>
      'आप्या खात्रीने हे कृती आयटम हटवू इच्छितात? हे कृती पूर्ववत केली जाऊ शकत नाही।';

  @override
  String get enterActionItemDescription => 'कृती आयटमचे वर्णन प्रविष्ट करा...';

  @override
  String get markAsCompleted => 'पूर्ण म्हणून चिन्हांकित करा';

  @override
  String get setDueDateAndTime => 'मुदत आणि वेळ सेट करा';

  @override
  String get reloadingApps => 'अ‍ॅप्स पुनः लोड होत आहे...';

  @override
  String get loadingApps => 'अ‍ॅप्स लोड होत आहे...';

  @override
  String get browseInstallCreateApps => 'अ‍ॅप्स ब्राउজ करा, इंस्टॉल करा आणि तयार करा';

  @override
  String get all => 'सर्व';

  @override
  String get open => 'खुला';

  @override
  String get install => 'इंस्टॉल करा';

  @override
  String get noAppsAvailable => 'कोणतेही अ‍ॅप्स उपलब्ध नाहीत';

  @override
  String get unableToLoadApps => 'अ‍ॅप्स लोड करू शकत नाहीत';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'आपल्या शोध अटी किंवा फिल्टर सुधारण्याचा प्रयत्न करा';

  @override
  String get checkBackLaterForNewApps => 'नवीन अ‍ॅप्ससाठी नंतर परत तपासा';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'कृपया आपल्या इंटरनेट कनेक्शन तपासा आणि पुन्हा प्रयत्न करा';

  @override
  String get createNewApp => 'नवीन अ‍ॅप तयार करा';

  @override
  String get buildSubmitCustomOmiApp => 'आपल्या कस्टम Omi अ‍ॅप तयार करा आणि जमा करा';

  @override
  String get submittingYourApp => 'आपला अ‍ॅप जमा होत आहे...';

  @override
  String get preparingFormForYou => 'आपल्यासाठी फॉर्म तयार होत आहे...';

  @override
  String get appDetails => 'अ‍ॅप तपशील';

  @override
  String get paymentDetails => 'पेमेंट तपशील';

  @override
  String get previewAndScreenshots => 'पूर्वावलोकन आणि स्क्रीनशॉट्स';

  @override
  String get appCapabilities => 'अ‍ॅप क्षमता';

  @override
  String get aiPrompts => 'AI प्रॉम्प्ट्स';

  @override
  String get chatPrompt => 'चॅट प्रॉम्प्ट';

  @override
  String get chatPromptPlaceholder =>
      'तुम्ही एक अद्भुत अ‍ॅप आहात, तुमचे काम उपयोगकर्त्याच्या क्वेरीला प्रतिक्रिया देणे आणि त्यांना चांगले वाटवणे आहे...';

  @override
  String get conversationPrompt => 'संभाषण प्रॉम्प्ट';

  @override
  String get conversationPromptPlaceholder =>
      'तुम्ही एक अद्भुत अ‍ॅप आहात, तुम्हाला संभाषणाची ट्रान्सक्रिप्ट आणि सारांश दिला जाईल...';

  @override
  String get notificationScopes => 'सूचना स्कोप्स';

  @override
  String get appPrivacyAndTerms => 'अ‍ॅप गोपनीयता आणि अटी';

  @override
  String get makeMyAppPublic => 'माझा अ‍ॅप सार्वजनिक करा';

  @override
  String get submitAppTermsAgreement => 'हा अ‍ॅप जमा केल्याने, मी Omi AI सेवा अटी आणि गोपनीयता धोरणास सहमत आहे';

  @override
  String get submitApp => 'अ‍ॅप जमा करा';

  @override
  String get needHelpGettingStarted => 'सुरू होण्यासाठी मदत चाहिए?';

  @override
  String get clickHereForAppBuildingGuides => 'अ‍ॅप बिल्डिंग गाईड आणि दस्तऐवजीकरणासाठी येथे क्लिक करा';

  @override
  String get submitAppQuestion => 'अ‍ॅप जमा करा?';

  @override
  String get submitAppPublicDescription =>
      'आपला अ‍ॅप पुनरावलोकन केला जाईल आणि सार्वजनिक केला जाईल. आप्य तक्षणच वापरण्यास सुरुवात करू शकता, पुनरावलोकन सुरु असतानाही!';

  @override
  String get submitAppPrivateDescription =>
      'आपला अ‍ॅप पुनरावलोकन केला जाईल आणि आपल्यासाठी खाजगीपणे उपलब्ध केला जाईल. आप्य तक्षणच वापरण्यास सुरुवात करू शकता, पुनरावलोकन सुरु असतानाही!';

  @override
  String get startEarning => 'कमाई सुरू करा! 💰';

  @override
  String get connectStripeOrPayPal => 'आपल्या अ‍ॅपसाठी भुगतान प्राप्त करण्यासाठी Stripe किंवा PayPal कनेक्ट करा।';

  @override
  String get connectNow => 'आता कनेक्ट करा';

  @override
  String get installsCount => 'इंस्टॉल';

  @override
  String get uninstallApp => 'अ‍ॅप अनइंस्टॉल करा';

  @override
  String get subscribe => 'सदस्यता घ्या';

  @override
  String get dataAccessNotice => 'डेटा प्रवेश सूचना';

  @override
  String get dataAccessWarning =>
      'हा अ‍ॅप आपल्या डेटामध्ये प्रवेश करेल. Omi AI आपल्या डेटा या अ‍ॅपद्वारे कसे वापरला, सुधारला किंवा हटवला जाते याबद्दल जबाबदार नाही';

  @override
  String get installApp => 'अ‍ॅप इंस्टॉल करा';

  @override
  String get betaTesterNotice =>
      'तुम्ही या अ‍ॅपचे बीटा टेस्टर आहात. हा अजून सार्वजनिक नाही. मंजूरी मिळल्यावर हा सार्वजनिक होईल।';

  @override
  String get appUnderReviewOwner =>
      'आपला अ‍ॅप पुनरावलोकनाधीन आहे आणि केवळ आपल्यासाठी दृश्यमान आहे. मंजूरी मिळल्यावर हा सार्वजनिक होईल।';

  @override
  String get appRejectedNotice =>
      'आपला अ‍ॅप नाकारला गेला आहे. कृपया अ‍ॅपचे तपशील अपडेट करा आणि पुनरावलोकनासाठी पुन्हा जमा करा।';

  @override
  String get setupSteps => 'सेटअप चरण';

  @override
  String get setupInstructions => 'सेटअप सूचना';

  @override
  String get integrationInstructions => 'एकीकरण सूचना';

  @override
  String get preview => 'पूर्वावलोकन';

  @override
  String get aboutTheApp => 'अ‍ॅपबद्दल';

  @override
  String get chatPersonality => 'चॅट व्यक्तिमत्व';

  @override
  String get ratingsAndReviews => 'रेटिंग आणि समीक्षा';

  @override
  String get noRatings => 'कोणत्याही रेटिंग नाहीत';

  @override
  String ratingsCount(String count) {
    return '$count+ रेटिंग';
  }

  @override
  String get errorActivatingApp => 'अ‍ॅप सक्रिय करण्यात त्रुटी';

  @override
  String get integrationSetupRequired => 'हे एकीकरण अ‍ॅप असल्यास, सेटअप पूर्ण केल्याची खात्री करा।';

  @override
  String get installed => 'इंस्टॉल केलेले';

  @override
  String get appIdLabel => 'अ‍ॅप ID';

  @override
  String get appNameLabel => 'अ‍ॅप नाव';

  @override
  String get appNamePlaceholder => 'माझा अद्भुत अ‍ॅप';

  @override
  String get pleaseEnterAppName => 'कृपया अ‍ॅपचे नाव प्रविष्ट करा';

  @override
  String get categoryLabel => 'श्रेणी';

  @override
  String get selectCategory => 'श्रेणी निवडा';

  @override
  String get descriptionLabel => 'वर्णन';

  @override
  String get appDescriptionPlaceholder =>
      'माझा अद्भुत अ‍ॅप एक छान अ‍ॅप आहे जे आश्चर्यकारी गोष्टी करते. हा सर्वात छान अ‍ॅप आहे!';

  @override
  String get pleaseProvideValidDescription => 'कृपया वैध वर्णन प्रदान करा';

  @override
  String get appPricingLabel => 'अ‍ॅप मूल्य';

  @override
  String get noneSelected => 'कोणतेही निवडलेले नाही';

  @override
  String get appIdCopiedToClipboard => 'अ‍ॅप ID क्लिपबोर्डवर कॉपी केली गेली';

  @override
  String get appCategoryModalTitle => 'अ‍ॅप श्रेणी';

  @override
  String get pricingFree => 'विनामूल्य';

  @override
  String get pricingPaid => 'सशुल्क';

  @override
  String get loadingCapabilities => 'क्षमता लोड होत आहे...';

  @override
  String get filterInstalled => 'इंस्टॉल केलेले';

  @override
  String get filterMyApps => 'माझी अ‍ॅप्स';

  @override
  String get clearSelection => 'निवड साफ करा';

  @override
  String get filterCategory => 'श्रेणी';

  @override
  String get rating4PlusStars => '४+ तारे';

  @override
  String get rating3PlusStars => '३+ तारे';

  @override
  String get rating2PlusStars => '२+ तारे';

  @override
  String get rating1PlusStars => '१+ तारे';

  @override
  String get filterRating => 'रेटिंग';

  @override
  String get filterCapabilities => 'क्षमता';

  @override
  String get noNotificationScopesAvailable => 'कोणतेही सूचना स्कोप्स उपलब्ध नाहीत';

  @override
  String get popularApps => 'लोकप्रिय अ‍ॅप्स';

  @override
  String get pleaseProvidePrompt => 'कृपया प्रॉम्प्ट प्रदान करा';

  @override
  String chatWithAppName(String appName) {
    return '$appName शी चॅट करा';
  }

  @override
  String get defaultAiAssistant => 'डिफॉल्ट AI सहायक';

  @override
  String get readyToChat => '✨ चॅट करण्यासाठी तयार!';

  @override
  String get connectionNeeded => '🌐 कनेक्शन आवश्यक';

  @override
  String get startConversation => 'एक संभाषण सुरू करा आणि जादू सुरू होऊ द्या';

  @override
  String get checkInternetConnection => 'कृपया आपल्या इंटरनेट कनेक्शन तपासा';

  @override
  String get wasThisHelpful => 'हे मदत झाले का?';

  @override
  String get thankYouForFeedback => 'आपल्या प्रतिक्रियेबद्दल धन्यवाद!';

  @override
  String get maxFilesUploadError => 'आप एक वेळी केवळ ४ फाइलांची अपलोड करू शकता';

  @override
  String get attachedFiles => '📎 संलग्न फाइलें';

  @override
  String get takePhoto => 'फोटो घ्या';

  @override
  String get captureWithCamera => 'कॅमेऱ्यासह कॅप्चर करा';

  @override
  String get selectImages => 'प्रतिमा निवडा';

  @override
  String get chooseFromGallery => 'गेलरीमधून निवडा';

  @override
  String get selectFile => 'फाइल निवडा';

  @override
  String get chooseAnyFileType => 'कोणत्याही फाइल प्रकार निवडा';

  @override
  String get cannotReportOwnMessages => 'आप आपल्या स्वतःच्या संदेशांची नोंद करू शकत नाही';

  @override
  String get messageReportedSuccessfully => '✅ संदेश यशस्वीरित्या नोंदवला गेला';

  @override
  String get confirmReportMessage => 'आप खात्रीने हा संदेश नोंदवू इच्छितात?';

  @override
  String get selectChatAssistant => 'चॅट सहायक निवडा';

  @override
  String get enableMoreApps => 'अधिक अ‍ॅप्स सक्षम करा';

  @override
  String get chatCleared => 'चॅट साफ केली गेली';

  @override
  String get clearChatTitle => 'चॅट साफ करा?';

  @override
  String get confirmClearChat => 'आप खात्रीने चॅट साफ करू इच्छितात? हे कृती पूर्ववत केली जाऊ शकत नाही।';

  @override
  String get copy => 'कॉपी करा';

  @override
  String get share => 'सामायिक करा';

  @override
  String get report => 'नोंद करा';

  @override
  String get microphonePermissionRequired => 'कॉल करण्यासाठी मायक्रोफोन परवानगी आवश्यक आहे';

  @override
  String get microphonePermissionDenied =>
      'मायक्रोफोन परवानगी नकारली गेली. कृपया सिस्टम प्राधान्ये > गोपनीयता आणि सुरक्षा > मायक्रोफोन मध्ये परवानगी द्या।';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'मायक्रोफोन परवानगी तपासण्यात अयशस्वी: $error';
  }

  @override
  String get failedToTranscribeAudio => 'ऑडिओ लिप्यंतरण करण्यात अयशस्वी';

  @override
  String get transcribing => 'लिप्यंतरण होत आहे...';

  @override
  String get transcriptionFailed => 'लिप्यंतरण अयशस्वी';

  @override
  String get discardedConversation => 'सोडून दिलेला संभाषण';

  @override
  String get at => 'येथे';

  @override
  String get from => 'पासून';

  @override
  String get copied => 'कॉपी केले!';

  @override
  String get copyLink => 'लिंक कॉपी करा';

  @override
  String get hideTranscript => 'ट्रान्सक्रिप्ट लपवा';

  @override
  String get viewTranscript => 'ट्रान्सक्रिप्ट पाहा';

  @override
  String get conversationDetails => 'संभाषण तपशील';

  @override
  String get transcript => 'ट्रान्सक्रिप्ट';

  @override
  String segmentsCount(int count) {
    return '$count खंड';
  }

  @override
  String get noTranscriptAvailable => 'कोणत्याही ट्रान्सक्रिप्ट उपलब्ध नाहीत';

  @override
  String get noTranscriptMessage => 'या संभाषणाला ट्रान्सक्रिप्ट नाही।';

  @override
  String get conversationUrlCouldNotBeGenerated => 'संभाषण URL तयार केला जाऊ शकला नाही।';

  @override
  String get failedToGenerateConversationLink => 'संभाषण लिंक तयार करण्यात अयशस्वी';

  @override
  String get failedToGenerateShareLink => 'सामायिक लिंक तयार करण्यात अयशस्वी';

  @override
  String get reloadingConversations => 'संभाषण पुनः लोड होत आहे...';

  @override
  String get user => 'उपयोगकर्ता';

  @override
  String get starred => 'तारांकित';

  @override
  String get date => 'तारीख';

  @override
  String get noResultsFound => 'कोणतेही परिणाम सापडले नाहीत';

  @override
  String get tryAdjustingSearchTerms => 'आपल्या शोध अटी सुधारण्याचा प्रयत्न करा';

  @override
  String get starConversationsToFindQuickly => 'त्यांना येथे जलद शोधण्यासाठी संभाषण तारांकित करा';

  @override
  String noConversationsOnDate(String date) {
    return '$date ला कोणतेही संभाषण नाहीत';
  }

  @override
  String get trySelectingDifferentDate => 'भिन्न तारीख निवडण्याचा प्रयत्न करा';

  @override
  String get conversations => 'संभाषण';

  @override
  String get chat => 'चॅट';

  @override
  String get actions => 'कार्य';

  @override
  String get syncAvailable => 'सिंक उपलब्ध';

  @override
  String get referAFriend => 'मित्राला संदर्भित करा';

  @override
  String get help => 'मदत';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Pro मध्ये अपग्रेड करा';

  @override
  String get getOmiDevice => 'Omi डिव्हाइस मिळवा';

  @override
  String get wearableAiCompanion => 'वेअरेबल AI सहचर';

  @override
  String get loadingMemories => 'स्मृती लोड होत आहे...';

  @override
  String get allMemories => 'सर्व स्मृती';

  @override
  String get aboutYou => 'आपल्याबद्दल';

  @override
  String get manual => 'व्यक्तिनिष्ठ';

  @override
  String get loadingYourMemories => 'आपल्या स्मृती लोड होत आहे...';

  @override
  String get createYourFirstMemory => 'सुरू करण्यासाठी आपली पहिली स्मृती तयार करा';

  @override
  String get tryAdjustingFilter => 'आपल्या शोध किंवा फिल्टर सुधारण्याचा प्रयत्न करा';

  @override
  String get whatWouldYouLikeToRemember => 'आप काय लक्षात ठेवू इच्छितात?';

  @override
  String get category => 'श्रेणी';

  @override
  String get public => 'सार्वजनिक';

  @override
  String get failedToSaveCheckConnection => 'जतन करण्यात अयशस्वी. कृपया आपल्या कनेक्शन तपासा।';

  @override
  String get createMemory => 'स्मृती तयार करा';

  @override
  String get deleteMemoryConfirmation => 'आप खात्रीने हे स्मृती हटवू इच्छितात? हे कृती पूर्ववत केली जाऊ शकत नाही।';

  @override
  String get makePrivate => 'खाजगी करा';

  @override
  String get organizeAndControlMemories => 'आपल्या स्मृती संघटित करा आणि नियंत्रण करा';

  @override
  String get total => 'एकूण';

  @override
  String get makeAllMemoriesPrivate => 'सर्व स्मृती खाजगी करा';

  @override
  String get setAllMemoriesToPrivate => 'सर्व स्मृती खाजगी दृश्यमानतेमध्ये सेट करा';

  @override
  String get makeAllMemoriesPublic => 'सर्व स्मृती सार्वजनिक करा';

  @override
  String get setAllMemoriesToPublic => 'सर्व स्मृती सार्वजनिक दृश्यमानतेमध्ये सेट करा';

  @override
  String get permanentlyRemoveAllMemories => 'Omi पासून सर्व स्मृती कायमचा काढून टाका';

  @override
  String get allMemoriesAreNowPrivate => 'सर्व स्मृती आता खाजगी आहेत';

  @override
  String get allMemoriesAreNowPublic => 'सर्व स्मृती आता सार्वजनिक आहेत';

  @override
  String get clearOmisMemory => 'Omi ची स्मृती साफ करा';

  @override
  String clearMemoryConfirmation(int count) {
    return 'आप खात्रीने Omi ची स्मृती साफ करू इच्छितात? हे कृती पूर्ववत केली जाऊ शकत नाही आणि सर्व $count स्मृती कायमचा हटवेल।';
  }

  @override
  String get omisMemoryCleared => 'आपल्याबद्दल Omi ची स्मृती साफ केली गेली';

  @override
  String get welcomeToOmi => 'Omi मध्ये स्वागत आहे';

  @override
  String get continueWithApple => 'Apple सह सुरू ठेवा';

  @override
  String get continueWithGoogle => 'Google सह सुरू ठेवा';

  @override
  String get byContinuingYouAgree => 'सुरू ठेवून, आप आमच्या ';

  @override
  String get termsOfService => 'सेवा अटी';

  @override
  String get and => ' आणि ';

  @override
  String get dataAndPrivacy => 'डेटा आणि गोपनीयता';

  @override
  String get secureAuthViaAppleId => 'Apple ID द्वारे सुरक्षित प्रमाणीकरण';

  @override
  String get secureAuthViaGoogleAccount => 'Google खाते द्वारे सुरक्षित प्रमाणीकरण';

  @override
  String get whatWeCollect => 'आम्ही काय संकलित करतो';

  @override
  String get dataCollectionMessage =>
      'सुरू ठेवून, आपले संभाषण, रेकॉर्डिंग्‍स आणि व्यक्तिगत माहिती आमच्या सर्व्हरवर सुरक्षित ठेवली जाईल जेणेकरून AI-संचालित अंतर्दृष्टी प्रदान करू शकू शकें आणि सर्व अॅप वैशिष्ट्य सक्षम करू शकें.';

  @override
  String get dataProtection => 'डेटा संरक्षण';

  @override
  String get yourDataIsProtected => 'आपला डेटा सुरक्षित आहे आणि आमच्या ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'कृपया आपली प्राथमिक भाषा निवडा';

  @override
  String get chooseYourLanguage => 'आपली भाषा निवडा';

  @override
  String get selectPreferredLanguageForBestExperience => 'सर्वोत्तम Omi अनुभवासाठी आपली पसंदीची भाषा निवडा';

  @override
  String get searchLanguages => 'भाषा शोधा...';

  @override
  String get selectALanguage => 'भाषा निवडा';

  @override
  String get tryDifferentSearchTerm => 'भिन्न शोध शब्द वापरून पाहा';

  @override
  String get pleaseEnterYourName => 'कृपया आपले नाव प्रविष्ट करा';

  @override
  String get nameMustBeAtLeast2Characters => 'नाव किमान २ वर्ण असणे आवश्यक आहे';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'आमला सांगा कि आपल्याला कसे संबोधले जावे. हे आपल्या Omi अनुभव वैयक्तिकृत करण्यास मदत करते.';

  @override
  String charactersCount(int count) {
    return '$count वर्ण';
  }

  @override
  String get enableFeaturesForBestExperience => 'आपल्या डिव्हाइसवर सर्वोत्तम Omi अनुभवासाठी वैशिष्ट्य सक्षम करा.';

  @override
  String get microphoneAccess => 'मायक्रोफोन प्रवेश';

  @override
  String get recordAudioConversations => 'ऑडियो संभाषण रेकॉर्ड करा';

  @override
  String get microphoneAccessDescription =>
      'आपले संभाषण रेकॉर्ड करण्यासाठी आणि लिप्यंतरण प्रदान करण्यासाठी Omi ला मायक्रोफोन प्रवेश आवश्यक आहे.';

  @override
  String get screenRecording => 'स्क्रीन रेकॉर्डिंग';

  @override
  String get captureSystemAudioFromMeetings => 'मीटिंग्समधून सिस्टम ऑडियो कॅप्चर करा';

  @override
  String get screenRecordingDescription =>
      'आपल्या ब्राउজर-आधारित मीटिंग्समधून सिस्टम ऑडियो कॅप्चर करण्यासाठी Omi ला स्क्रीन रेकॉर्डिंग परवानगी आवश्यक आहे.';

  @override
  String get accessibility => 'अॅक्सेसिबिलिटी';

  @override
  String get detectBrowserBasedMeetings => 'ब्राउজर-आधारित मीटिंग्स शोधा';

  @override
  String get accessibilityDescription =>
      'आपण आपल्या ब्राउজरमध्ये Zoom, Meet किंवा Teams मीटिंग्समध्ये सामील होताना शोधण्यासाठी Omi ला अॅक्सेसिबिलिटी परवानगी आवश्यक आहे.';

  @override
  String get pleaseWait => 'कृपया प्रतीक्षा करा...';

  @override
  String get joinTheCommunity => 'समुदायात सामील व्हा!';

  @override
  String get loadingProfile => 'प्रोफाइल लोड होत आहे...';

  @override
  String get profileSettings => 'प्रोफाइल सेटिंग्‍स';

  @override
  String get noEmailSet => 'कोणती ईमेल सेट नाही';

  @override
  String get userIdCopiedToClipboard => 'वापरकर्ता ID क्लिपबोर्डवर कॉपी केली';

  @override
  String get yourInformation => 'आपली माहिती';

  @override
  String get setYourName => 'आपले नाव सेट करा';

  @override
  String get changeYourName => 'आपले नाव बदला';

  @override
  String get voiceAndPeople => 'व्हॉइस आणि लोक';

  @override
  String get teachOmiYourVoice => 'Omi ला आपल्या आवाजाचे शिक्षण द्या';

  @override
  String get tellOmiWhoSaidIt => 'Omi ला सांगा कि हे कोणी म्हणाले 🗣️';

  @override
  String get payment => 'पेमेंट';

  @override
  String get addOrChangeYourPaymentMethod => 'आपल्या पेमेंट पद्धती जोडा किंवा बदला';

  @override
  String get preferences => 'प्राधान्ये';

  @override
  String get helpImproveOmiBySharing => 'गुप्त विश्लेषण डेटा शेअर करून Omi सुधारण्यास मदत करा';

  @override
  String get deleteAccount => 'खाता हटवा';

  @override
  String get deleteYourAccountAndAllData => 'आपल्या खाते आणि सर्व डेटा हटवा';

  @override
  String get clearLogs => 'लॉग्‍स साफ करा';

  @override
  String get debugLogsCleared => 'डीबग लॉग्‍स साफ केले';

  @override
  String get exportConversations => 'संभाषण निर्यात करा';

  @override
  String get exportAllConversationsToJson => 'आपल्या सर्व संभाषण JSON फाइलमध्ये निर्यात करा.';

  @override
  String get conversationsExportStarted => 'संभाषण निर्यात सुरू झाला. हे काही सेकंद लागू शकते, कृपया प्रतीक्षा करा.';

  @override
  String get mcpDescription =>
      'Omi ला इतर अनुप्रयोगांसह कनेक्ट करण्यासाठी आपल्या आठवणी आणि संभाषण वाचा, शोधा आणि व्यवस्थापित करा. सुरू करण्यासाठी की तयार करा.';

  @override
  String get apiKeys => 'API की';

  @override
  String errorLabel(String error) {
    return 'त्रुटी: $error';
  }

  @override
  String get noApiKeysFound => 'कोणतीही API की सापडली नाही. सुरू करण्यासाठी एक तयार करा.';

  @override
  String get advancedSettings => 'उन्नत सेटिंग्‍स';

  @override
  String get triggersWhenNewConversationCreated => 'नवीन संभाषण तयार होताना ट्रिगर होते.';

  @override
  String get triggersWhenNewTranscriptReceived => 'नई लिप्यंतरण प्राप्त होताना ट्रिगर होते.';

  @override
  String get realtimeAudioBytes => 'रीयलटाइम ऑडियो बाइट्स';

  @override
  String get triggersWhenAudioBytesReceived => 'ऑडियो बाइट्स प्राप्त होताना ट्रिगर होते.';

  @override
  String get everyXSeconds => 'प्रत्येक x सेकंद';

  @override
  String get triggersWhenDaySummaryGenerated => 'दिन सारांश तयार होताना ट्रिगर होते.';

  @override
  String get tryLatestExperimentalFeatures => 'Omi टीम कडून नवीनतम प्रायोगिक वैशिष्ट्य वापरून पाहा.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'लिप्यंतरण सेवा निदान स्थिती';

  @override
  String get enableDetailedDiagnosticMessages => 'लिप्यंतरण सेवा कडून तपशीलवार निदान संदेश सक्षम करा';

  @override
  String get autoCreateAndTagNewSpeakers => 'नवीन वक्ते स्वयंचलितपणे तयार आणि टॅग करा';

  @override
  String get automaticallyCreateNewPerson => 'लिप्यंतरणमध्ये नाव शोधले जाताना नवीन व्यक्ती स्वयंचलितपणे तयार करा.';

  @override
  String get pilotFeatures => 'पायलट वैशिष्ट्य';

  @override
  String get pilotFeaturesDescription => 'ही वैशिष्ट्य परीक्षा आहेत आणि कोणतेही समर्थन हमी नाही.';

  @override
  String get suggestFollowUpQuestion => 'फॉलो-अप प्रश्न सुचवा';

  @override
  String get saveSettings => 'सेटिंग्‍स सेव करा';

  @override
  String get syncingDeveloperSettings => 'डेव्हलपर सेटिंग्‍स सिंक होत आहे...';

  @override
  String get summary => 'सारांश';

  @override
  String get auto => 'स्वयंचलित';

  @override
  String get noSummaryForApp => 'या अॅप साठी कोणतेही सारांश उपलब्ध नाही. चांगल्या परिणामांसाठी दुसरा अॅप वापरून पाहा.';

  @override
  String get tryAnotherApp => 'दुसरा अॅप वापरून पाहा';

  @override
  String generatedBy(String appName) {
    return '$appName द्वारे तयार';
  }

  @override
  String get overview => 'विहंगावलोकन';

  @override
  String get otherAppResults => 'इतर अॅप परिणाम';

  @override
  String get unknownApp => 'अज्ञात अॅप';

  @override
  String get noSummaryAvailable => 'कोणतेही सारांश उपलब्ध नाही';

  @override
  String get conversationNoSummaryYet => 'या संभाषणाचा अजून सारांश नाही.';

  @override
  String get chooseSummarizationApp => 'सारांशन अॅप निवडा';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName डिफॉल्ट सारांशन अॅप म्हणून सेट केले';
  }

  @override
  String get letOmiChooseAutomatically => 'Omi ला स्वयंचलितपणे सर्वोत्तम अॅप निवडू द्या';

  @override
  String get deleteConversationConfirmation =>
      'आप हा संभाषण हटविण्याचे सुनिश्चित आहात? हे क्रिया पूर्ववत् करू शकत नाही.';

  @override
  String get conversationDeleted => 'संभाषण हटवले';

  @override
  String get generatingLink => 'लिंक तयार होत आहे...';

  @override
  String get editConversation => 'संभाषण संपादित करा';

  @override
  String get conversationLinkCopiedToClipboard => 'संभाषण लिंक क्लिपबोर्डवर कॉपी केली';

  @override
  String get conversationTranscriptCopiedToClipboard => 'संभाषण लिप्यंतरण क्लिपबोर्डवर कॉपी केली';

  @override
  String get editConversationDialogTitle => 'संभाषण संपादित करा';

  @override
  String get changeTheConversationTitle => 'संभाषण शीर्षक बदला';

  @override
  String get conversationTitle => 'संभाषण शीर्षक';

  @override
  String get enterConversationTitle => 'संभाषण शीर्षक प्रविष्ट करा...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'संभाषण शीर्षक यशस्वीरित्या अपडेट केला';

  @override
  String get failedToUpdateConversationTitle => 'संभाषण शीर्षक अपडेट करण्यास अपयश आली';

  @override
  String get errorUpdatingConversationTitle => 'संभाषण शीर्षक अपडेट करण्यात त्रुटी';

  @override
  String get settingUp => 'सेटअप होत आहे...';

  @override
  String get startYourFirstRecording => 'आपल्या पहिली रेकॉर्डिंग सुरू करा';

  @override
  String get preparingSystemAudioCapture => 'सिस्टम ऑडियो कॅप्चर तयार होत आहे';

  @override
  String get clickTheButtonToCaptureAudio =>
      'लाइव्ह लिप्यंतरण, AI अंतर्दृष्टी आणि स्वयंचलित सेव्हिंगसाठी ऑडियो कॅप्चर करण्यासाठी बटण क्लिक करा.';

  @override
  String get reconnecting => 'पुन्हा कनेक्ट होत आहे...';

  @override
  String get recordingPaused => 'रेकॉर्डिंग विराम दिली';

  @override
  String get recordingActive => 'रेकॉर्डिंग सक्रिय';

  @override
  String get startRecording => 'रेकॉर्डिंग सुरू करा';

  @override
  String resumingInCountdown(String countdown) {
    return '$countdown सेकंदांत पुनः सुरू होत आहे...';
  }

  @override
  String get tapPlayToResume => 'पुनः सुरू करण्यासाठी प्ले टॅप करा';

  @override
  String get listeningForAudio => 'ऑडियो ऐकत आहे...';

  @override
  String get preparingAudioCapture => 'ऑडियो कॅप्चर तयार होत आहे';

  @override
  String get clickToBeginRecording => 'रेकॉर्डिंग सुरू करण्यासाठी क्लिक करा';

  @override
  String get translated => 'अनुवादित';

  @override
  String get liveTranscript => 'लाइव्ह लिप्यंतरण';

  @override
  String segmentsSingular(String count) {
    return '$count खंड';
  }

  @override
  String segmentsPlural(String count) {
    return '$count खंड';
  }

  @override
  String get startRecordingToSeeTranscript => 'लाइव्ह लिप्यंतरण पाहण्यासाठी रेकॉर्डिंग सुरू करा';

  @override
  String get paused => 'विराम दिली';

  @override
  String get initializing => 'आरंभ होत आहे...';

  @override
  String get recording => 'रेकॉर्डिंग';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'मायक्रोफोन बदली. $countdown सेकंदांत पुनः सुरू होत आहे';
  }

  @override
  String get clickPlayToResumeOrStop => 'पुनः सुरू करण्यासाठी प्ले किंवा संपविण्यासाठी स्टॉप क्लिक करा';

  @override
  String get settingUpSystemAudioCapture => 'सिस्टम ऑडियो कॅप्चर सेटअप होत आहे';

  @override
  String get capturingAudioAndGeneratingTranscript => 'ऑडियो कॅप्चर होत आहे आणि लिप्यंतरण तयार होत आहे';

  @override
  String get clickToBeginRecordingSystemAudio => 'सिस्टम ऑडियो रेकॉर्ड करण्यास सुरू करण्यासाठी क्लिक करा';

  @override
  String get you => 'तुम्ही';

  @override
  String speakerWithId(String speakerId) {
    return 'वक्ता $speakerId';
  }

  @override
  String get translatedByOmi => 'omi द्वारे अनुवादित';

  @override
  String get backToConversations => 'संभाषणांकडे परत';

  @override
  String get systemAudio => 'सिस्टम';

  @override
  String get mic => 'मायक्रोफोन';

  @override
  String audioInputSetTo(String deviceName) {
    return 'ऑडियो इनपुट $deviceName वर सेट केली';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'ऑडियो डिव्हाइस स्विच करण्यात त्रुटी: $error';
  }

  @override
  String get selectAudioInput => 'ऑडियो इनपुट निवडा';

  @override
  String get loadingDevices => 'डिव्हाइसेस लोड होत आहे...';

  @override
  String get settingsHeader => 'सेटिंग्‍स';

  @override
  String get plansAndBilling => 'योजना आणि बिलिंग';

  @override
  String get calendarIntegration => 'कॅलेंडर एकीकरण';

  @override
  String get dailySummary => 'दैनिक सारांश';

  @override
  String get developer => 'डेव्हलपर';

  @override
  String get about => 'परिचय';

  @override
  String get selectTime => 'वेळ निवडा';

  @override
  String get accountGroup => 'खाता';

  @override
  String get signOutQuestion => 'साइन आउट करा?';

  @override
  String get signOutConfirmation => 'आप साइन आउट करण्याचे सुनिश्चित आहात?';

  @override
  String get customVocabularyHeader => 'कस्टम व्यावहारिकता';

  @override
  String get addWordsDescription => 'असे शब्द जोडा जे Omi लिप्यंतरणादरम्यान ओळखले पाहिजे.';

  @override
  String get enterWordsHint => 'शब्द प्रविष्ट करा (स्वल्पविरामाने वेगळे)';

  @override
  String get dailySummaryHeader => 'दैनिक सारांश';

  @override
  String get dailySummaryTitle => 'दैनिक सारांश';

  @override
  String get dailySummaryDescription => 'आपल्या दिवसाच्या संभाषणांचा व्यक्तिगतकृत सारांश सूचना म्हणून वितरित करा.';

  @override
  String get deliveryTime => 'वितरण वेळ';

  @override
  String get deliveryTimeDescription => 'आपल्या दैनिक सारांश कधी प्राप्त करायचा';

  @override
  String get subscription => 'सदस्यता';

  @override
  String get viewPlansAndUsage => 'योजना आणि वापर पहा';

  @override
  String get viewPlansDescription => 'आपल्या सदस्यता व्यवस्थापित करा आणि वापर आकडे पहा';

  @override
  String get addOrChangePaymentMethod => 'आपल्या पेमेंट पद्धती जोडा किंवा बदला';

  @override
  String get displayOptions => 'प्रदर्शन पर्याय';

  @override
  String get showMeetingsInMenuBar => 'मेनू बारमध्ये मीटिंग्स दाखवा';

  @override
  String get displayUpcomingMeetingsDescription => 'मेनू बारमध्ये आगामी मीटिंग्‍स प्रदर्शित करा';

  @override
  String get showEventsWithoutParticipants => 'सहभागींशिवाय इव्हेंट्स दाखवा';

  @override
  String get includePersonalEventsDescription => 'सहभागीशिवाय व्यक्तिगत इव्हेंट्स समाविष्ट करा';

  @override
  String get upcomingMeetings => 'आगामी मीटिंग्‍स';

  @override
  String get checkingNext7Days => 'पुढील ७ दिवस तपासत आहे';

  @override
  String get shortcuts => 'शॉर्टकट्स';

  @override
  String get shortcutChangeInstruction => 'शॉर्टकट बदलण्यासाठी एकावर क्लिक करा. रद्द करण्यासाठी Escape दाबा.';

  @override
  String get configureSTTProvider => 'STT प्रदाता कॉन्फिगर करा';

  @override
  String get setConversationEndDescription => 'संभाषण कधी स्वयंचलितपणे समाप्त होतील हे सेट करा';

  @override
  String get importDataDescription => 'इतर स्रोतांकडून डेटा आयात करा';

  @override
  String get exportConversationsDescription => 'संभाषण JSON मध्ये निर्यात करा';

  @override
  String get exportingConversations => 'संभाषण निर्यात होत आहे...';

  @override
  String get clearNodesDescription => 'सर्व नोड्स आणि कनेक्शन साफ करा';

  @override
  String get deleteKnowledgeGraphQuestion => 'ज्ञान आलेख हटवा?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'हे सर्व व्युत्पन्न ज्ञान आलेख डेटा हटवेल. आपल्या मूळ आठवणी सुरक्षित राहतात.';

  @override
  String get connectOmiWithAI => 'Omi ला AI सहायकांसह कनेक्ट करा';

  @override
  String get noAPIKeys => 'कोणतीही API की नाही. सुरू करण्यासाठी एक तयार करा.';

  @override
  String get autoCreateWhenDetected => 'नाव शोधले जाताना स्वयंचलितपणे तयार करा';

  @override
  String get trackPersonalGoals => 'होमपेजवर व्यक्तिगत लक्ष्य ट्रॅक करा';

  @override
  String get endpointURL => 'एंडपॉइंट URL';

  @override
  String get links => 'लिंक्स';

  @override
  String get discordMemberCount => 'Discord वर ८००० + सदस्य';

  @override
  String get userInformation => 'वापरकर्ता माहिती';

  @override
  String get capabilities => 'क्षमता';

  @override
  String get previewScreenshots => 'पूर्वावलोकन स्क्रीनशॉट्स';

  @override
  String get holdOnPreparingForm => 'थांब, आम्ही तुमच्यासाठी फॉर्म तयार करत आहो';

  @override
  String get bySubmittingYouAgreeToOmi => 'सबमिट करून, आप Omi ';

  @override
  String get termsAndPrivacyPolicy => 'अटी आणि गोपनीयता धोरण';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'समस्या निदान करण्यास मदत करते. ३ दिवसानंतर स्वयंचलितपणे हटवते.';

  @override
  String get manageYourApp => 'आपल्या अॅप व्यवस्थापित करा';

  @override
  String get updatingYourApp => 'आपल्या अॅप अपडेट होत आहे';

  @override
  String get fetchingYourAppDetails => 'आपल्या अॅप तपशील प्राप्त होत आहे';

  @override
  String get updateAppQuestion => 'अॅप अपडेट करा?';

  @override
  String get updateAppConfirmation =>
      'आप आपल्या अॅप अपडेट करण्याचे सुनिश्चित आहात? आमच्या टीम द्वारे पुनरावलोकन केल्यानंतर बदल प्रतिबिंबित होतील.';

  @override
  String get updateApp => 'अॅप अपडेट करा';

  @override
  String get createAndSubmitNewApp => 'नवीन अॅप तयार आणि सबमिट करा';

  @override
  String appsCount(String count) {
    return 'अॅप्स ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'खाजगी अॅप्स ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'सार्वजनिक अॅप्स ($count)';
  }

  @override
  String get newVersionAvailable => 'नवीन संस्करण उपलब्ध 🎉';

  @override
  String get no => 'नाही';

  @override
  String get subscriptionCancelledSuccessfully =>
      'सदस्यता यशस्वीरित्या रद्द केली. ती चालू बिलिंग कालावधीच्या शेवटपर्यंत सक्रिय राहील.';

  @override
  String get failedToCancelSubscription => 'सदस्यता रद्द करण्यास अपयश आली. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get invalidPaymentUrl => 'अमान्य पेमेंट URL';

  @override
  String get permissionsAndTriggers => 'परवानगी आणि ट्रिगर्स';

  @override
  String get chatFeatures => 'चॅट वैशिष्ट्य';

  @override
  String get uninstall => 'स्थापना रद्द करा';

  @override
  String get installs => 'स्थापना';

  @override
  String get priceLabel => 'किंमत';

  @override
  String get updatedLabel => 'अपडेट केलेले';

  @override
  String get createdLabel => 'तयार केलेले';

  @override
  String get featuredLabel => 'वैशिष्ट्यीकृत';

  @override
  String get cancelSubscriptionQuestion => 'सदस्यता रद्द करा?';

  @override
  String get cancelSubscriptionConfirmation =>
      'आप आपल्या सदस्यता रद्द करण्याचे सुनिश्चित आहात? आप आपल्या चालू बिलिंग कालावधीच्या शेवटपर्यंत प्रवेश ठेवू शकतील.';

  @override
  String get cancelSubscriptionButton => 'सदस्यता रद्द करा';

  @override
  String get cancelling => 'रद्द होत आहे...';

  @override
  String get betaTesterMessage =>
      'आप या अॅपचे बीटा टेस्टर आहात. ते अजून सार्वजनिक नाही. मंजूरी मिळल्यावर ते सार्वजनिक होईल.';

  @override
  String get appUnderReviewMessage =>
      'आपला अॅप पुनरावलोकनाखाली आहे आणि केवळ आपल्यास दृश्यमान आहे. मंजूरी मिळल्यावर ते सार्वजनिक होईल.';

  @override
  String get appRejectedMessage =>
      'आपल्या अॅपला अस्वीकार करण्यात आला आहे. कृपया अॅप तपशील अपडेट करा आणि पुनरावलोकनासाठी पुन्हा सबमिट करा.';

  @override
  String get invalidIntegrationUrl => 'अमान्य एकीकरण URL';

  @override
  String get tapToComplete => 'पूर्ण करण्यासाठी टॅप करा';

  @override
  String get invalidSetupInstructionsUrl => 'अमान्य सेटअप सूचना URL';

  @override
  String get pushToTalk => 'बोलण्यासाठी दाबा';

  @override
  String get summaryPrompt => 'सारांश प्रॉम्प्ट';

  @override
  String get pleaseSelectARating => 'कृपया रेटिंग निवडा';

  @override
  String get reviewAddedSuccessfully => 'पुनरावलोकन यशस्वीरित्या जोडले 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'पुनरावलोकन यशस्वीरित्या अपडेट केला 🚀';

  @override
  String get failedToSubmitReview => 'पुनरावलोकन सबमिट करण्यास अपयश आली. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get addYourReview => 'आपल्या पुनरावलोकन जोडा';

  @override
  String get editYourReview => 'आपल्या पुनरावलोकन संपादित करा';

  @override
  String get writeAReviewOptional => 'पुनरावलोकन लिहा (वैकल्पिक)';

  @override
  String get submitReview => 'पुनरावलोकन सबमिट करा';

  @override
  String get updateReview => 'पुनरावलोकन अपडेट करा';

  @override
  String get yourReview => 'आपल्या पुनरावलोकन';

  @override
  String get anonymousUser => 'अनामिक वापरकर्ता';

  @override
  String get issueActivatingApp => 'या अॅप सक्रिय करण्यात समस्या आली. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get dataAccessNoticeDescription =>
      'हा अॅप आपल्या डेटामध्ये प्रवेश करेल. Omi AI हा अॅप आपल्या डेटा कसे वापरते, सुधारते किंवा हटवते याच्यासाठी जबाबदार नाही';

  @override
  String get copyUrl => 'URL कॉपी करा';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'सोम';

  @override
  String get weekdayTue => 'मंगळ';

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
    return '$serviceName एकीकरण जल्दीच आये';
  }

  @override
  String alreadyExportedTo(String platform) {
    return '$platform वर आधी निर्यात केले';
  }

  @override
  String get anotherPlatform => 'दुसरा प्लेटफॉर्म';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'कृपया सेटिंग्‍स > कार्य एकीकरण मध्ये $serviceName सह प्रमाणीकृत करा';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceName मध्ये जोडत आहे...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceName मध्ये जोडले';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceName मध्ये जोडण्यास अपयश आली';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple Reminders साठी परवानगी नाकारली';

  @override
  String failedToCreateApiKey(String error) {
    return 'प्रदाता API की तयार करण्यास अपयश आली: $error';
  }

  @override
  String get createAKey => 'की तयार करा';

  @override
  String get apiKeyRevokedSuccessfully => 'API की यशस्वीरित्या रद्द केली';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API की रद्द करण्यास अपयश आली: $error';
  }

  @override
  String get omiApiKeys => 'Omi API की';

  @override
  String get apiKeysDescription =>
      'API की हे प्रमाणीकरणासाठी वापरली जातात जेव्हा आपल्या अॅप OMI सर्व्हरसह संवाद करते. ते आपल्या अनुप्रयोगास स्मृतिमान तयार करण्यास आणि इतर OMI सेवा सुरक्षितपणे प्रवेश करण्यास अनुमती देते.';

  @override
  String get aboutOmiApiKeys => 'Omi API की बद्दल';

  @override
  String get yourNewKey => 'आपल्या नवीन की:';

  @override
  String get copyToClipboard => 'क्लिपबोर्डवर कॉपी करा';

  @override
  String get pleaseCopyKeyNow => 'कृपया आता कॉपी करा आणि सुरक्षित ठिकाणी लिहून ठेवा. ';

  @override
  String get willNotSeeAgain => 'आप हे पुन्हा पाहू शकणार नाही.';

  @override
  String get revokeKey => 'की रद्द करा';

  @override
  String get revokeApiKeyQuestion => 'API की रद्द करा?';

  @override
  String get revokeApiKeyWarning =>
      'हे क्रिया पूर्ववत् करू शकत नाही. या की वापरणारी कोणतीही अनुप्रयोग यापुढे API मध्ये प्रवेश करू शकणार नाही.';

  @override
  String get revoke => 'रद्द करा';

  @override
  String get whatWouldYouLikeToCreate => 'आप काय तयार करू इच्छित आहात?';

  @override
  String get createAnApp => 'अॅप तयार करा';

  @override
  String get createAndShareYourApp => 'आपल्या अॅप तयार आणि शेअर करा';

  @override
  String get itemApp => 'अॅप';

  @override
  String keepItemPublic(String item) {
    return '$item सार्वजनिक ठेवा';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item सार्वजनिक करा?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item खाजगी करा?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'जर आप $item सार्वजनिक केले तर हे सर्वांद्वारे वापरले जाऊ शकते';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'जर आप $item आता खाजगी केले तर हे सर्वांसाठी काम करणे बंद होईल आणि केवळ आपल्यास दृश्यमान होईल';
  }

  @override
  String get manageApp => 'अॅप व्यवस्थापित करा';

  @override
  String deleteItemTitle(String item) {
    return '$item हटवा';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item हटवा?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'आप हा $item हटविण्याचे सुनिश्चित आहात? हे क्रिया पूर्ववत् करू शकत नाही.';
  }

  @override
  String get revokeKeyQuestion => 'की रद्द करा?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'आप \"$keyName\" की रद्द करण्याचे सुनिश्चित आहात? हे क्रिया पूर्ववत् करू शकत नाही.';
  }

  @override
  String get createNewKey => 'नवीन की तयार करा';

  @override
  String get keyNameHint => 'उदा., Claude Desktop';

  @override
  String get pleaseEnterAName => 'कृपया नाव प्रविष्ट करा.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'की तयार करण्यास अपयश आली: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'की तयार करण्यास अपयश आली. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get keyCreated => 'की तयार झाली';

  @override
  String get keyCreatedMessage =>
      'आपल्या नवीन की तयार केली गेली आहे. कृपया आता कॉपी करा. आप हे पुन्हा पाहू शकणार नाही.';

  @override
  String get keyWord => 'की';

  @override
  String get externalAppAccess => 'बाह्य अॅप प्रवेश';

  @override
  String get externalAppAccessDescription =>
      'खालील स्थापित अॅप्सचे बाह्य एकीकरण आहे आणि आपल्या डेटामध्ये प्रवेश करू शकते, जसे संभाषण आणि आठवणी.';

  @override
  String get noExternalAppsHaveAccess => 'कोणत्याही बाह्य अॅप्सला आपल्या डेटामध्ये प्रवेश नाही.';

  @override
  String get maximumSecurityE2ee => 'अधिकतम सुरक्षा (E2EE)';

  @override
  String get e2eeDescription =>
      'एंड-टू-एंड एन्क्रिप्शन गोपनीयताचा सोने मानक आहे. सक्षम होताना, आपल्या डेटा आपल्या डिव्हाइसवर एन्क्रिप्ट केली जाते त्याच्या आगे आमच्या सर्व्हरला पाठवले जाते. याचा अर्थ असा की कोणीही, Omi सारखेच नाही, आपल्या सामग्रीमध्ये प्रवेश करू शकत नाही.';

  @override
  String get importantTradeoffs => 'महत्वपूर्ण ट्रेड-ऑफ:';

  @override
  String get e2eeTradeoff1 => '• बाह्य अॅप एकीकरण यासारख्या काही वैशिष्ट्य अक्षम केली जाऊ शकते.';

  @override
  String get e2eeTradeoff2 => '• जर आप आपल्या पासवर्ड गमवले तर आपल्या डेटा पुनर्प्राप्त केली जाऊ शकत नाही.';

  @override
  String get featureComingSoon => 'ही वैशिष्ट्य जल्दीच आये!';

  @override
  String get migrationInProgressMessage =>
      'स्थलांतरण प्रगतीमध्ये आहे. हे पूर्ण होईपर्यंत आप संरक्षण स्तर बदलू शकत नाही.';

  @override
  String get migrationFailed => 'स्थलांतरण अपयश आली';

  @override
  String migratingFromTo(String source, String target) {
    return '$source कडून $target ला स्थलांतरित होत आहे';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total ऑब्जेक्ट्स';
  }

  @override
  String get secureEncryption => 'सुरक्षित एन्क्रिप्शन';

  @override
  String get secureEncryptionDescription =>
      'आपल्या डेटा आपल्यासाठी अद्वितीय की सह आमच्या सर्व्हरवर एन्क्रिप्ट केली जाते, Google Cloud वर होस्ट केली जाते. याचा अर्थ असा की आपल्या कच्ची सामग्री डेटाबेसकडून कोणीही, Omi कर्मचारी किंवा Google सारखेच, सरळ प्रवेशयोग्य नाही.';

  @override
  String get endToEndEncryption => 'एंड-टू-एंड एन्क्रिप्शन';

  @override
  String get e2eeCardDescription =>
      'अधिकतम सुरक्षा सक्षम करा जेथे केवळ आप आपल्या डेटामध्ये प्रवेश करू शकता. अधिक जाणून घेण्यासाठी टॅप करा.';

  @override
  String get dataAlwaysEncrypted =>
      'स्तरापेक्षा असूनही, आपल्या डेटा नेहमी विश्रांती वर आणि पारगमनात एन्क्रिप्ट केली जाते.';

  @override
  String get readOnlyScope => 'फक्त वाचा';

  @override
  String get fullAccessScope => 'संपूर्ण प्रवेश';

  @override
  String get readScope => 'वाचा';

  @override
  String get writeScope => 'लिहा';

  @override
  String get apiKeyCreated => 'API की तयार झाली!';

  @override
  String get saveKeyWarning => 'ही की सेव करा! आप हे पुन्हा पाहू शकणार नाही.';

  @override
  String get yourApiKey => 'आपल्या API की';

  @override
  String get tapToCopy => 'कॉपी करण्यासाठी टॅप करा';

  @override
  String get copyKey => 'की कॉपी करा';

  @override
  String get createApiKey => 'API की तयार करा';

  @override
  String get accessDataProgrammatically => 'प्रोग्रामॅटिक्ली आपल्या डेटामध्ये प्रवेश करा';

  @override
  String get keyNameLabel => 'की नाव';

  @override
  String get keyNamePlaceholder => 'उदा., माझ्या अॅप एकीकरण';

  @override
  String get permissionsLabel => 'परवानगी';

  @override
  String get permissionsInfoNote => 'R = वाचा, W = लिहा. काहीही निवडले नाही तर फक्त वाचा करा स्क्रीन करा.';

  @override
  String get developerApi => 'डेव्हलपर API';

  @override
  String get createAKeyToGetStarted => 'सुरू करण्यासाठी की तयार करा';

  @override
  String errorWithMessage(String error) {
    return 'त्रुटी: $error';
  }

  @override
  String get omiTraining => 'Omi प्रशिक्षण';

  @override
  String get trainingDataProgram => 'प्रशिक्षण डेटा कार्यक्रम';

  @override
  String get getOmiUnlimitedFree =>
      'AI मॉडेल प्रशिक्षण साठी आपल्या डेटा योगदान करून Omi Unlimited विनामूल्य प्राप्त करा.';

  @override
  String get trainingDataBullets =>
      '• आपल्या डेटा AI मॉडेल सुधारण्यास मदत करते\n• फक्त गैर-संवेदनशील डेटा शेअर केली जाते\n• संपूर्ण पारदर्शी प्रक्रिया';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training वर अधिक जाणून घ्या';

  @override
  String get agreeToContributeData => 'मी समजून घेतो आणि AI प्रशिक्षणासाठी माझे डेटा योगदान करण्यास सहमत आहे';

  @override
  String get submitRequest => 'विनंती सबमिट करा';

  @override
  String get thankYouRequestUnderReview =>
      'धन्यवाद! आपल्या विनंती पुनरावलोकनाखाली आहे. मंजूरी मिळल्यावर आम्ही आपल्याला सूचित करु.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'आपल्या योजना $date पर्यंत सक्रिय राहील. त्यानंतर, आप आपल्या असीम वैशिष्ट्यांमध्ये प्रवेश गमवाल. आप सुनिश्चित आहात?';
  }

  @override
  String get confirmCancellation => 'रद्दीकरण पुष्टी करा';

  @override
  String get keepMyPlan => 'माझी योजना ठेवा';

  @override
  String get subscriptionSetToCancel => 'आपल्या सदस्यता कालावधीच्या शेवटी रद्द करण्यासाठी सेट आहे.';

  @override
  String get switchedToOnDevice => 'ऑन-डिव्हाइस लिप्यंतरणमध्ये स्विच केले';

  @override
  String get couldNotSwitchToFreePlan => 'मोफत योजनेवर स्विच करू शकत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get couldNotLoadPlans => 'उपलब्ध योजना लोड करू शकत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get selectedPlanNotAvailable => 'निवडलेली योजना उपलब्ध नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get upgradeToAnnualPlan => 'वार्षिक योजनेवर अपग्रेड करा';

  @override
  String get importantBillingInfo => 'महत्वाचे बिलिंग माहिती:';

  @override
  String get monthlyPlanContinues => 'आपली वर्तमान मासिक योजना आपच्या बिलिंग कालावधीच्या शेवटपर्यंत सुरू राहील';

  @override
  String get paymentMethodCharged =>
      'आपली विद्यमान पेमेंट पद्धत आपली मासिक योजना संपल्यावर स्वयंचलितपणे चार्ज केली जाईल';

  @override
  String get annualSubscriptionStarts => 'आपली १२-महिन्यांची वार्षिक सदस्यता चार्जनंतर स्वयंचलितपणे सुरू होईल';

  @override
  String get thirteenMonthsCoverage => 'आपल्याला एकूण १३ महिन्यांचा कव्हरेज मिळेल (सध्याचा महिना + १२ महिने वार्षिक)';

  @override
  String get confirmUpgrade => 'अपग्रेड पुष्टी करा';

  @override
  String get confirmPlanChange => 'योजना बदल पुष्टी करा';

  @override
  String get confirmAndProceed => 'पुष्टी करा आणि पुढे जा';

  @override
  String get upgradeScheduled => 'अपग्रेड शेड्यूल केले';

  @override
  String get changePlan => 'योजना बदला';

  @override
  String get upgradeAlreadyScheduled => 'आपली वार्षिक योजनेवर अपग्रेड आधीच शेड्यूल केली आहे';

  @override
  String get youAreOnUnlimitedPlan => 'आप Unlimited योजनेवर आहात.';

  @override
  String get yourOmiUnleashed => 'आपला Omi, मुक्त. अमर्याद शक्यतांसाठी अनलिमिटेड जा.';

  @override
  String planEndedOn(String date) {
    return 'आपली योजना $date ला संपली.\\nआता पुन्हा सदस्यता घ्या - नवीन बिलिंग कालावधीसाठी आपला तात्काळ चार्ज होईल.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'आपली योजना $date ला रद्द होण्यासाठी सेट केली आहे.\\nआपले फायदे कायम राखण्यासाठी आता पुन्हा सदस्यता घ्या - $date पर्यंत कोणतीही शुल्क नाही.';
  }

  @override
  String get annualPlanStartsAutomatically => 'आपली वार्षिक योजना आपली मासिक योजना संपल्यावर स्वयंचलितपणे सुरू होईल.';

  @override
  String planRenewsOn(String date) {
    return 'आपली योजना $date ला नवीकरण होईल.';
  }

  @override
  String get unlimitedConversations => 'अनलिमिटेड संभाषण';

  @override
  String get askOmiAnything => 'आपल्या जीवनाबद्दल Omi ला कहिही विचारा';

  @override
  String get unlockOmiInfiniteMemory => 'Omi च्या अनंत स्मृती अनलॉक करा';

  @override
  String get youreOnAnnualPlan => 'आप वार्षिक योजनेवर आहात';

  @override
  String get alreadyBestValuePlan => 'आपल्याकडे आधीच सर्वोत्तम मूल्य योजना आहे. कोणतेही बदल आवश्यक नाही.';

  @override
  String get unableToLoadPlans => 'प्लॅन लोड करता आले नाहीत';

  @override
  String get checkConnectionTryAgain => 'कनेक्शन तपासा आणि पुन्हा प्रयत्न करा';

  @override
  String get useFreePlan => 'मोफत योजना वापरा';

  @override
  String get continueText => 'पुढे जा';

  @override
  String get resubscribe => 'पुन्हा सदस्यता घ्या';

  @override
  String get couldNotOpenPaymentSettings => 'पेमेंट सेटिंग्ज उघडू शकत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get managePaymentMethod => 'पेमेंट पद्धती व्यवस्थापित करा';

  @override
  String get cancelSubscription => 'सदस्यता रद्द करा';

  @override
  String endsOnDate(String date) {
    return '$date ला समाप्त होईल';
  }

  @override
  String get active => 'सक्रिय';

  @override
  String get freePlan => 'मोफत योजना';

  @override
  String get configure => 'कॉन्फ़िगर करा';

  @override
  String get privacyInformation => 'गोपनीयता माहिती';

  @override
  String get yourPrivacyMattersToUs => 'आपली गोपनीयता आमच्यासाठी महत्वाची आहे';

  @override
  String get privacyIntroText =>
      'Omi मध्ये, आम्ही आपली गोपनीयता अत्यंत गंभीरपणे घेतो. आम्ही आपल्याकरिता आमच्या उत्पादनाची सुधारणा करण्यासाठी आम्ही कोणता डेटा संकलित करतो आणि कसे वापरतो याबद्दल पारदर्शक असू इच्छितो. येथे आपल्याला जाणून घेणे आवश्यक आहे:';

  @override
  String get whatWeTrack => 'आम्ही काय ट्रॅक करतो';

  @override
  String get anonymityAndPrivacy => 'अनामिकता आणि गोपनीयता';

  @override
  String get optInAndOptOutOptions => 'ऑप्ट-इन आणि ऑप्ट-आउट पर्याय';

  @override
  String get ourCommitment => 'आमची प्रतिबद्धता';

  @override
  String get commitmentText =>
      'आम्ही आमच्या द्वारा संकलित डेटा Omi ला आपल्यासाठी एक चांगले उत्पादन बनवण्यासाठी वापरण्यास प्रतिबद्ध आहे. आपली गोपनीयता आणि विश्वास आमच्यासाठी सर्वोच्च प्राधान्य आहे.';

  @override
  String get thankYouText =>
      'Omi चे मूल्यवान वापरकर्ता असल्याबद्दल धन्यवाद. आपल्याला कोणतीही प्रश्न किंवा चिंता असल्यास, आमच्याशी संपर्क करण्यास नेहमी स्वागत आहे team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'WiFi सिंक सेटिंग्ज';

  @override
  String get enterHotspotCredentials => 'आपल्या फोनच्या हॉटस्पॉट क्रेडेंशियल्स प्रविष्ट करा';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi सिंक आपल्या फोनला हॉटस्पॉट म्हणून वापरते. आपल्या हॉटस्पॉट नाव आणि पासवर्ड सेटिंग्ज > व्यक्तिगत हॉटस्पॉट मध्ये शोधा.';

  @override
  String get hotspotNameSsid => 'हॉटस्पॉट नाव (SSID)';

  @override
  String get exampleIphoneHotspot => 'उदा. iPhone हॉटस्पॉट';

  @override
  String get password => 'पासवर्ड';

  @override
  String get enterHotspotPassword => 'हॉटस्पॉट पासवर्ड प्रविष्ट करा';

  @override
  String get saveCredentials => 'क्रेडेंशियल्स सेव करा';

  @override
  String get clearCredentials => 'क्रेडेंशियल्स साफ करा';

  @override
  String get pleaseEnterHotspotName => 'कृपया हॉटस्पॉट नाव प्रविष्ट करा';

  @override
  String get wifiCredentialsSaved => 'WiFi क्रेडेंशियल्स सेव केली आहेत';

  @override
  String get wifiCredentialsCleared => 'WiFi क्रेडेंशियल्स साफ केली आहेत';

  @override
  String summaryGeneratedForDate(String date) {
    return '$date साठी सारांश तयार केला गेला';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'सारांश तयार करण्यास अपयश आले. सुनिश्चित करा की आपल्याकडे त्या दिवसासाठी संभाषण आहेत.';

  @override
  String get summaryNotFound => 'सारांश सापडला नाही';

  @override
  String get yourDaysJourney => 'आपल्या दिवसाची यात्रा';

  @override
  String get highlights => 'मुख्य मुद्दे';

  @override
  String get unresolvedQuestions => 'अनिर्णीत प्रश्न';

  @override
  String get decisions => 'निर्णय';

  @override
  String get learnings => 'शिक्षणे';

  @override
  String get autoDeletesAfterThreeDays => '३ दिवसानंतर स्वयंचलितपणे हटवले जाते.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'ज्ञान ग्राफ यशस्वीरित्या हटवले गेले';

  @override
  String get exportStartedMayTakeFewSeconds => 'निर्यात सुरू झाले. यास काही सेकंद लागू शकतात...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'हे सर्व व्युत्पन्न ज्ञान ग्राफ डेटा (नोड्स आणि कनेक्शन) हटाईल. आपली मूळ स्मृती सुरक्षित राहील. ग्राफ समय मिळल्यावर किंवा पुढील विनंतीवर पुनर्निर्मित होईल.';

  @override
  String get configureDailySummaryDigest => 'आपल्या दैनिक कृती मुद्दे पचन कॉन्फ़िगर करा';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes मध्ये प्रवेश करते';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType द्वारे सक्रिय केले';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription आणि $triggerDescription आहे.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription आहे.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'कोणतेही विशिष्ट डेटा प्रवेश कॉन्फ़िगर केलेला नाही.';

  @override
  String get basicPlanDescription => '१,२०० प्रीमियम मिनिटे + डिव्हाइसवर अनलिमिटेड';

  @override
  String get minutes => 'मिनिटे';

  @override
  String get omiHas => 'Omi कडे आहे:';

  @override
  String get premiumMinutesUsed => 'प्रीमियम मिनिटे वापरली आहेत.';

  @override
  String get setupOnDevice => 'डिव्हाइसवर सेटअप करा';

  @override
  String get forUnlimitedFreeTranscription => 'अनलिमिटेड मुक्त लेखांकनसाठी.';

  @override
  String premiumMinsLeft(int count) {
    return '$count प्रीमियम मिनिटे बाकी आहेत.';
  }

  @override
  String get alwaysAvailable => 'नेहमी उपलब्ध.';

  @override
  String get importHistory => 'इतिहास आयात करा';

  @override
  String get noImportsYet => 'अद्याप कोणतीही आयात नाही';

  @override
  String get selectZipFileToImport => 'आयात करण्यासाठी .zip फाइल निवडा!';

  @override
  String get otherDevicesComingSoon => 'इतर डिव्हाइस लवकरच येत आहेत';

  @override
  String get deleteAllLimitlessConversations => 'सर्व सीमाहीन संभाषण हटवा?';

  @override
  String get deleteAllLimitlessWarning =>
      'हे Limitless मधून आयात केलेले सर्व संभाषण स्थायीरित्या हटाईल. ही कारवाई पूर्ववत्त करता येणार नाही.';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless संभाषण हटवली';
  }

  @override
  String get failedToDeleteConversations => 'संभाषण हटविण्यास अपयश आले';

  @override
  String get deleteImportedData => 'आयात केलेले डेटा हटवा';

  @override
  String get statusPending => 'प्रलंबित';

  @override
  String get statusProcessing => 'प्रक्रियाकरण';

  @override
  String get statusCompleted => 'पूर्ण';

  @override
  String get statusFailed => 'अपयश';

  @override
  String nConversations(int count) {
    return '$count संभाषण';
  }

  @override
  String get pleaseEnterName => 'कृपया नाव प्रविष्ट करा';

  @override
  String get nameMustBeBetweenCharacters => 'नाव २ आणि ४० वर्णांच्या दरम्यान असणे आवश्यक आहे';

  @override
  String get deleteSampleQuestion => 'नमुना हटवा?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'आप $name चा नमुना हटविण्याचा खरेच निश्चय आहे?';
  }

  @override
  String get confirmDeletion => 'हटवणे पुष्टी करा';

  @override
  String deletePersonConfirmation(String name) {
    return 'आप $name हटविण्याचा खरेच निश्चय आहे? हे सर्व संबंधित भाषण नमुने देखील काढून टाकेल.';
  }

  @override
  String get howItWorksTitle => 'हे कसे काम करते?';

  @override
  String get howPeopleWorks =>
      'एकदा व्यक्ती तयार झाल्यानंतर, आप संभाषण लेखा मध्ये जाऊ शकता आणि त्यांना त्यांचे संबंधित खंड नियुक्त करू शकता, त्या प्रकारे Omi त्यांच्या भाषणाची देखील ओळख करू शकेल!';

  @override
  String get tapToDelete => 'हटविण्यासाठी टॅप करा';

  @override
  String get newTag => 'नवीन';

  @override
  String get needHelpChatWithUs => 'मदतीची आवश्यकता आहे? आमच्याशी चॅट करा';

  @override
  String get localStorageEnabled => 'स्थानिक संग्रहण सक्षम केला';

  @override
  String get localStorageDisabled => 'स्थानिक संग्रहण अक्षम केला';

  @override
  String failedToUpdateSettings(String error) {
    return 'सेटिंग्ज अपडेट करण्यास अपयश आले: $error';
  }

  @override
  String get privacyNotice => 'गोपनीयता सूचना';

  @override
  String get recordingsMayCaptureOthers =>
      'रेकॉर्डिंग्ज इतरांचे आवाज कॅप्चर करू शकतात. सक्षम करण्यापूर्वी सर्व सहभागींचा सहमती सुनिश्चित करा.';

  @override
  String get enable => 'सक्षम करा';

  @override
  String get storeAudioOnPhone => 'फोनवर ऑडिओ स्टोर करा';

  @override
  String get on => 'चालू';

  @override
  String get storeAudioDescription =>
      'सर्व ऑडिओ रेकॉर्डिंग्ज आपल्या फोनवर स्थानिकरित्या संग्रहीत ठेवा. अक्षम केल्यावर, संग्रहण स्थान वाचविण्यासाठी फक्त अपयश आपलोडचे ठेवले जातात.';

  @override
  String get enableLocalStorage => 'स्थानिक संग्रहण सक्षम करा';

  @override
  String get cloudStorageEnabled => 'क्लाउड संग्रहण सक्षम केला';

  @override
  String get cloudStorageDisabled => 'क्लाउड संग्रहण अक्षम केला';

  @override
  String get enableCloudStorage => 'क्लाउड संग्रहण सक्षम करा';

  @override
  String get storeAudioOnCloud => 'क्लाउडवर ऑडिओ स्टोर करा';

  @override
  String get cloudStorageDialogMessage =>
      'आपली रीयल-टाइम रेकॉर्डिंग्ज आपण बोलत असताना खाजगी क्लाउड संग्रहणमध्ये संग्रहीत केली जातील.';

  @override
  String get storeAudioCloudDescription =>
      'आपली रीयल-टाइम रेकॉर्डिंग्ज आपण बोलत असताना खाजगी क्लाउड संग्रहणमध्ये संग्रहीत करा. ऑडिओ रीयल-टाइममध्ये सुरक्षितपणे कॅप्चर आणि सेव केला जातो.';

  @override
  String get downloadingFirmware => 'फर्मवेयर डाउनलोड करत आहे';

  @override
  String get installingFirmware => 'फर्मवेयर स्थापित करत आहे';

  @override
  String get firmwareUpdateWarning =>
      'अ‍ॅप बंद करू नका किंवा डिव्हाइस बंद करू नका. यामुळे आपल्या डिव्हाइसचे नुकसान होऊ शकते.';

  @override
  String get firmwareUpdated => 'फर्मवेयर अपडेट केले';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'अपडेट पूर्ण करण्यासाठी कृपया आपल्या $deviceName ला पुनः सुरू करा.';
  }

  @override
  String get yourDeviceIsUpToDate => 'आपली डिव्हाइस सद्य आहे';

  @override
  String get currentVersion => 'सध्याची आवृत्ती';

  @override
  String get latestVersion => 'नवीनतम आवृत्ती';

  @override
  String get whatsNew => 'नवीन काय आहे';

  @override
  String get installUpdate => 'अपडेट स्थापित करा';

  @override
  String get updateNow => 'आता अपडेट करा';

  @override
  String get updateGuide => 'अपडेट गाईड';

  @override
  String get checkingForUpdates => 'अपडेटसाठी तपासत आहे';

  @override
  String get checkingFirmwareVersion => 'फर्मवेयर आवृत्ती तपासत आहे...';

  @override
  String get firmwareUpdate => 'फर्मवेयर अपडेट';

  @override
  String get payments => 'पेमेंट्स';

  @override
  String get connectPaymentMethodInfo =>
      'आपल्या अ‍ॅप्लिकेशनसाठी पेआउट प्राप्त करणे सुरू करण्यासाठी खाली पेमेंट पद्धती कनेक्ट करा.';

  @override
  String get selectedPaymentMethod => 'निवडलेली पेमेंट पद्धती';

  @override
  String get availablePaymentMethods => 'उपलब्ध पेमेंट पद्धती';

  @override
  String get activeStatus => 'सक्रिय';

  @override
  String get connectedStatus => 'कनेक्ट केला';

  @override
  String get notConnectedStatus => 'कनेक्ट केलेला नाही';

  @override
  String get setActive => 'सक्रिय सेट करा';

  @override
  String get getPaidThroughStripe => 'Stripe द्वारे आपल्या अ‍ॅप विक्रीसाठी पैसे मिळा';

  @override
  String get monthlyPayouts => 'मासिक पेआउट्स';

  @override
  String get monthlyPayoutsDescription =>
      'जेव्हा आप \$१० कमाई पर्यंत पोहोचता तेव्हा आपल्या खात्यात थेट मासिक पेमेंट प्राप्त करा';

  @override
  String get secureAndReliable => 'सुरक्षित आणि विश्वसनीय';

  @override
  String get stripeSecureDescription => 'Stripe आपल्या अ‍ॅप राजस्वचे सुरक्षित आणि वेळेवर हस्तांतरण सुनिश्चित करते';

  @override
  String get selectYourCountry => 'आपला देश निवडा';

  @override
  String get countrySelectionPermanent => 'आपली देश निवड स्थायी आहे आणि नंतर बदली शकत नाही.';

  @override
  String get byClickingConnectNow => '\"आता कनेक्ट करा\" वर क्लिक करून आप सहमत आहात';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe कनेक्ट केलेला खाता करार';

  @override
  String get errorConnectingToStripe => 'Stripe ला कनेक्ट करण्यास त्रुटी! कृपया नंतर पुन्हा प्रयत्न करा.';

  @override
  String get connectingYourStripeAccount => 'आपल्या Stripe खाते कनेक्ट करत आहे';

  @override
  String get stripeOnboardingInstructions =>
      'कृपया आपल्या ब्राउজरमध्ये Stripe ऑनबोर्डिंग प्रक्रिया पूर्ण करा. हा पृष्ठ पूर्ण झाल्यानंतर स्वयंचलितपणे अपडेट होईल.';

  @override
  String get failedTryAgain => 'अपयश? पुन्हा प्रयत्न करा';

  @override
  String get illDoItLater => 'मी हे नंतर करीन';

  @override
  String get successfullyConnected => 'यशस्वीरित्या कनेक्ट केले!';

  @override
  String get stripeReadyForPayments =>
      'आपल्या Stripe खाते आता पेमेंट प्राप्त करण्यासाठी तयार आहे. आप आपल्या अ‍ॅप विक्रीमधून लगेचच कमाई सुरू करू शकता.';

  @override
  String get updateStripeDetails => 'Stripe तपशील अपडेट करा';

  @override
  String get errorUpdatingStripeDetails => 'Stripe तपशील अपडेट करण्यास त्रुटी! कृपया नंतर पुन्हा प्रयत्न करा.';

  @override
  String get updatePayPal => 'PayPal अपडेट करा';

  @override
  String get setUpPayPal => 'PayPal सेटअप करा';

  @override
  String get updatePayPalAccountDetails => 'आपल्या PayPal खाते तपशील अपडेट करा';

  @override
  String get connectPayPalToReceivePayments =>
      'आपल्या अ‍ॅप्लिकेशनसाठी पेमेंट प्राप्त करणे सुरू करण्यासाठी आपल्या PayPal खाते कनेक्ट करा';

  @override
  String get paypalEmail => 'PayPal ईमेल';

  @override
  String get paypalMeLink => 'PayPal.me लिंक';

  @override
  String get stripeRecommendation =>
      'जर Stripe आपल्या देशात उपलब्ध असेल, तर आम्ही वेगवान आणि सोपे पेआउटसाठी यासाठी अत्यंत शिफारस करतो.';

  @override
  String get updatePayPalDetails => 'PayPal तपशील अपडेट करा';

  @override
  String get savePayPalDetails => 'PayPal तपशील सेव करा';

  @override
  String get pleaseEnterPayPalEmail => 'कृपया आपल्या PayPal ईमेल प्रविष्ट करा';

  @override
  String get pleaseEnterPayPalMeLink => 'कृपया आपल्या PayPal.me लिंक प्रविष्ट करा';

  @override
  String get doNotIncludeHttpInLink => 'लिंकमध्ये http किंवा https किंवा www समाविष्ट करू नका';

  @override
  String get pleaseEnterValidPayPalMeLink => 'कृपया वैध PayPal.me लिंक प्रविष्ट करा';

  @override
  String get pleaseEnterValidEmail => 'कृपया वैध ईमेल पत्ता प्रविष्ट करा';

  @override
  String get syncingYourRecordings => 'आपल्या रेकॉर्डिंग्ज सिंक करत आहे';

  @override
  String get syncYourRecordings => 'आपल्या रेकॉर्डिंग्ज सिंक करा';

  @override
  String get syncNow => 'आता सिंक करा';

  @override
  String get error => 'त्रुटी';

  @override
  String get speechSamples => 'भाषण नमुने';

  @override
  String additionalSampleIndex(String index) {
    return 'अतिरिक्त नमुना $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'अवधी: $seconds सेकंद';
  }

  @override
  String get additionalSpeechSampleRemoved => 'अतिरिक्त भाषण नमुना काढून टाकला';

  @override
  String get consentDataMessage =>
      'पुढे चालू ठेवल्यास, तुमच्या संभाषणा, रेकॉर्डिंग आणि वैयक्तिक माहिती आमच्या सर्व्हरवर सुरक्षितपणे साठवली जाईल. तुमच्या ऑडिओ रेकॉर्डिंग आणि ट्रान्सक्रिप्ट तृतीय-पक्ष AI सेवांद्वारे प्रक्रिया केली जातात (ट्रान्सक्रिप्शनसाठी Deepgram आणि विश्लेषणासाठी OpenAI सह) तुम्हाला AI-चालित अंतर्दृष्टी प्रदान करण्यासाठी आणि सर्व अॅप वैशिष्ट्ये सक्षम करण्यासाठी.';

  @override
  String get tasksEmptyStateMessage => 'आपल्या संभाषणातील कार्य येथे दिसतील.\\n+ टॅप करून एक मॅन्युअल्ली तयार करा.';

  @override
  String get clearChatAction => 'चॅट साफ करा';

  @override
  String get enableApps => 'अ‍ॅप्स सक्षम करा';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'अधिक दाखवा ↓';

  @override
  String get showLess => 'कमी दाखवा ↑';

  @override
  String get loadingYourRecording => 'आपली रेकॉर्डिंग लोड करत आहे...';

  @override
  String get photoDiscardedMessage => 'हे फोटो महत्त्वाचे नसल्यामुळे टाकून दिले गेले.';

  @override
  String get analyzing => 'विश्लेषण करत आहे...';

  @override
  String get searchCountries => 'देश शोधा';

  @override
  String get checkingAppleWatch => 'Apple Watch तपासत आहे...';

  @override
  String get installOmiOnAppleWatch => 'Omi आपल्या\\nApple Watch वर स्थापित करा';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Omi सह आपल्या Apple Watch वापरण्यासाठी, आपल्याला प्रथम आपल्या घड्याळावर Omi अ‍ॅप स्थापित करणे आवश्यक आहे.';

  @override
  String get openOmiOnAppleWatch => 'Omi आपल्या\\nApple Watch वर उघडा';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi अ‍ॅप आपल्या Apple Watch वर स्थापित आहे. हे उघडा आणि प्रारंभ करण्यासाठी टॅप करा.';

  @override
  String get openWatchApp => 'Watch अ‍ॅप उघडा';

  @override
  String get iveInstalledAndOpenedTheApp => 'मी अ‍ॅप स्थापित आणि खुले केले आहे';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch अ‍ॅप उघडू शकत नाही. कृपया आपल्या Apple Watch वरील Watch अ‍ॅप मॅन्युअल्ली उघडा आणि \"उपलब्ध अ‍ॅप्स\" विभागातून Omi स्थापित करा.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch यशस्वीरित्या कनेक्ट केले!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch अद्यापही पोहोचता येत नाही. कृपया सुनिश्चित करा की Omi अ‍ॅप आपल्या घड्याळावर खुली आहे.';

  @override
  String errorCheckingConnection(String error) {
    return 'जोडणी तपासण्यास त्रुटी: $error';
  }

  @override
  String get muted => 'शांत केला';

  @override
  String get processNow => 'आता प्रक्रिया करा';

  @override
  String get finishedConversation => 'संभाषण संपली?';

  @override
  String get stopRecordingConfirmation => 'आप रेकॉर्डिंग थांबवण्याचा आणि संभाषण आता सारांशित करण्याचा खरेच निश्चय आहे?';

  @override
  String get conversationEndsManually => 'संभाषण फक्त मॅन्युअल्ली संपेल.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'कोणतीही भाषण नसल्यानंतर $minutes मिनिट$suffix नंतर संभाषण सारांशित केली जाते.';
  }

  @override
  String get dontAskAgain => 'मला पुन्हा विचारू नका';

  @override
  String get waitingForTranscriptOrPhotos => 'लेखा किंवा फोटो्स साठी प्रतीक्षा करत आहे...';

  @override
  String get noSummaryYet => 'अद्याप सारांश नाही';

  @override
  String hints(String text) {
    return 'सूचना: $text';
  }

  @override
  String get testConversationPrompt => 'संभाषण प्रॉम्प्ट चाचणी करा';

  @override
  String get prompt => 'प्रॉम्प्ट';

  @override
  String get result => 'परिणाम:';

  @override
  String get compareTranscripts => 'लेख तुलना करा';

  @override
  String get notHelpful => 'मदतीचे नाही';

  @override
  String get exportTasksWithOneTap => 'एका टॅपने कार्य निर्यात करा!';

  @override
  String get inProgress => 'प्रगतीमध्ये';

  @override
  String get photos => 'फोटो';

  @override
  String get rawData => 'कच्चा डेटा';

  @override
  String get content => 'सामग्री';

  @override
  String get noContentToDisplay => 'प्रदर्शन करण्यासाठी कोणतीही सामग्री नाही';

  @override
  String get noSummary => 'कोणतेही सारांश नाही';

  @override
  String get updateOmiFirmware => 'Omi फर्मवेयर अपडेट करा';

  @override
  String get anErrorOccurredTryAgain => 'त्रुटी आली. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get welcomeBackSimple => 'पुन्हा स्वागत आहे';

  @override
  String get addVocabularyDescription => 'Omi ला लेखांकनादरम्यान ओळख असावी असे शब्द जोडा.';

  @override
  String get enterWordsCommaSeparated => 'शब्द प्रविष्ट करा (अल्पविरामाने वेगळे केलेले)';

  @override
  String get whenToReceiveDailySummary => 'आपल्या दैनिक सारांश कधी प्राप्त करायचा';

  @override
  String get checkingNextSevenDays => 'पुढील ७ दिवस तपासत आहे';

  @override
  String failedToDeleteError(String error) {
    return 'हटविण्यास अपयश आले: $error';
  }

  @override
  String get developerApiKeys => 'डेव्हलपर API की';

  @override
  String get noApiKeysCreateOne => 'कोणतीही API की नाही. सुरू करण्यासाठी एक तयार करा.';

  @override
  String get commandRequired => '⌘ आवश्यक';

  @override
  String get spaceKey => 'स्पेस';

  @override
  String loadMoreRemaining(String count) {
    return 'अधिक लोड करा ($count बाकी)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'शीर्ष $percentile% वापरकर्ता';
  }

  @override
  String get wrappedMinutes => 'मिनिटे';

  @override
  String get wrappedConversations => 'संभाषण';

  @override
  String get wrappedDaysActive => 'दिवस सक्रिय';

  @override
  String get wrappedYouTalkedAbout => 'आपण बोलले';

  @override
  String get wrappedActionItems => 'कृती मुद्दे';

  @override
  String get wrappedTasksCreated => 'कार्य तयार केली';

  @override
  String get wrappedCompleted => 'पूर्ण';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% पूर्णता दर';
  }

  @override
  String get wrappedYourTopDays => 'आपले शीर्ष दिवस';

  @override
  String get wrappedBestMoments => 'सर्वोत्तम क्षण';

  @override
  String get wrappedMyBuddies => 'माझे मित्र';

  @override
  String get wrappedCouldntStopTalkingAbout => 'बोलणे थांबवू शकत नाही';

  @override
  String get wrappedShow => 'शो';

  @override
  String get wrappedMovie => 'चित्रपट';

  @override
  String get wrappedBook => 'पुस्तक';

  @override
  String get wrappedCelebrity => 'सेलिब्रिटी';

  @override
  String get wrappedFood => 'खाद्य';

  @override
  String get wrappedMovieRecs => 'मित्रांसाठी चित्रपट शिफारसी';

  @override
  String get wrappedBiggest => 'सर्वात मोठे';

  @override
  String get wrappedStruggle => 'संघर्ष';

  @override
  String get wrappedButYouPushedThrough => 'परंतु आपण पुढे जाता 💪';

  @override
  String get wrappedWin => 'विजय';

  @override
  String get wrappedYouDidIt => 'आपन्या केले! 🎉';

  @override
  String get wrappedTopPhrases => 'शीर्ष ५ वाक्य';

  @override
  String get wrappedMins => 'मिनिटे';

  @override
  String get wrappedConvos => 'संभाषण';

  @override
  String get wrappedDays => 'दिवस';

  @override
  String get wrappedMyBuddiesLabel => 'माझे मित्र';

  @override
  String get wrappedObsessionsLabel => 'ऑब्सेशन';

  @override
  String get wrappedStruggleLabel => 'संघर्ष';

  @override
  String get wrappedWinLabel => 'विजय';

  @override
  String get wrappedTopPhrasesLabel => 'शीर्ष वाक्य';

  @override
  String get wrappedLetsHitRewind => 'Let\'s hit rewind on your';

  @override
  String get wrappedGenerateMyWrapped => 'माझी Wrapped तयार करा';

  @override
  String get wrappedProcessingDefault => 'प्रक्रियाकरण...';

  @override
  String get wrappedCreatingYourStory => 'आपल्या\\n२०२५ कथा तयार करत आहे...';

  @override
  String get wrappedSomethingWentWrong => 'काहीतरी\\nचुकीचे झाले';

  @override
  String get wrappedAnErrorOccurred => 'त्रुटी आली';

  @override
  String get wrappedTryAgain => 'पुन्हा प्रयत्न करा';

  @override
  String get wrappedNoDataAvailable => 'कोणताही डेटा उपलब्ध नाही';

  @override
  String get wrappedOmiLifeRecap => 'Omi जीवन पुनरावलोकन';

  @override
  String get wrappedSwipeUpToBegin => 'सुरू करण्यासाठी वर स्वाइप करा';

  @override
  String get wrappedShareText => 'माझे २०२५, Omi द्वारे लक्षात ठेवले ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'शेयर करण्यास अपयश आले. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get wrappedFailedToStartGeneration => 'निर्माण सुरू करण्यास अपयश आले. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get wrappedStarting => 'सुरू करत आहे...';

  @override
  String get wrappedShare => 'शेयर करा';

  @override
  String get wrappedShareYourWrapped => 'आपली Wrapped शेयर करा';

  @override
  String get wrappedMy2025 => 'माझे २०२५';

  @override
  String get wrappedRememberedByOmi => 'Omi द्वारे लक्षात ठेवले';

  @override
  String get wrappedMostFunDay => 'सर्वात मजेदार';

  @override
  String get wrappedMostProductiveDay => 'सर्वात उत्पादक';

  @override
  String get wrappedMostIntenseDay => 'सर्वात तीव्र';

  @override
  String get wrappedFunniestMoment => 'सर्वात मजेदार';

  @override
  String get wrappedMostCringeMoment => 'सर्वात शर्मनाक';

  @override
  String get wrappedMinutesLabel => 'मिनिटे';

  @override
  String get wrappedConversationsLabel => 'संभाषण';

  @override
  String get wrappedDaysActiveLabel => 'दिवस सक्रिय';

  @override
  String get wrappedTasksGenerated => 'कार्य तयार केली';

  @override
  String get wrappedTasksCompleted => 'कार्य पूर्ण केली';

  @override
  String get wrappedTopFivePhrases => 'शीर्ष ५ वाक्य';

  @override
  String get wrappedAGreatDay => 'एक अद्भुत दिवस';

  @override
  String get wrappedGettingItDone => 'हे पूर्ण करत आहे';

  @override
  String get wrappedAChallenge => 'एक आव्हान';

  @override
  String get wrappedAHilariousMoment => 'एक हास्यास्पद क्षण';

  @override
  String get wrappedThatAwkwardMoment => 'तो शर्मनाक क्षण';

  @override
  String get wrappedYouHadFunnyMoments => 'आपल्याला या वर्षी काही मजेदार क्षण होते!';

  @override
  String get wrappedWeveAllBeenThere => 'आपण सर्वजण तेथे गेले आहे!';

  @override
  String get wrappedFriend => 'मित्र';

  @override
  String get wrappedYourBuddy => 'आपला मित्र!';

  @override
  String get wrappedNotMentioned => 'उल्लेख नाही';

  @override
  String get wrappedTheHardPart => 'कठीण भाग';

  @override
  String get wrappedPersonalGrowth => 'व्यक्तिगत विकास';

  @override
  String get wrappedFunDay => 'मजेदार';

  @override
  String get wrappedProductiveDay => 'उत्पादक';

  @override
  String get wrappedIntenseDay => 'तीव्र';

  @override
  String get wrappedFunnyMomentTitle => 'मजेदार क्षण';

  @override
  String get wrappedCringeMomentTitle => 'शर्मनाक क्षण';

  @override
  String get wrappedYouTalkedAboutBadge => 'आपण बोलले';

  @override
  String get wrappedCompletedLabel => 'पूर्ण';

  @override
  String get wrappedMyBuddiesCard => 'माझे मित्र';

  @override
  String get wrappedBuddiesLabel => 'मित्र';

  @override
  String get wrappedObsessionsLabelUpper => 'ऑब्सेशन';

  @override
  String get wrappedStruggleLabelUpper => 'संघर्ष';

  @override
  String get wrappedWinLabelUpper => 'विजय';

  @override
  String get wrappedTopPhrasesLabelUpper => 'शीर्ष वाक्य';

  @override
  String get wrappedYourHeader => 'आपला';

  @override
  String get wrappedTopDaysHeader => 'शीर्ष दिवस';

  @override
  String get wrappedYourTopDaysBadge => 'आपले शीर्ष दिवस';

  @override
  String get wrappedBestHeader => 'सर्वोत्तम';

  @override
  String get wrappedMomentsHeader => 'क्षण';

  @override
  String get wrappedBestMomentsBadge => 'सर्वोत्तम क्षण';

  @override
  String get wrappedBiggestHeader => 'सर्वात मोठे';

  @override
  String get wrappedStruggleHeader => 'संघर्ष';

  @override
  String get wrappedWinHeader => 'विजय';

  @override
  String get wrappedButYouPushedThroughEmoji => 'परंतु आपण पुढे जाता 💪';

  @override
  String get wrappedYouDidItEmoji => 'आपन्या केले! 🎉';

  @override
  String get wrappedHours => 'तास';

  @override
  String get wrappedActions => 'कृती';

  @override
  String get multipleSpeakersDetected => 'एकाधिक वक्ते शोधले गेले';

  @override
  String get multipleSpeakersDescription =>
      'असे दिसते की रेकॉर्डिंगमध्ये एकाधिक वक्ते आहेत. कृपया सुनिश्चित करा की आप शांत ठिकाणी आहात आणि पुन्हा प्रयत्न करा.';

  @override
  String get invalidRecordingDetected => 'अमान्य रेकॉर्डिंग शोधली गेली';

  @override
  String get notEnoughSpeechDescription => 'पुरेसा भाषण शोधला गेला नाही. कृपया अधिक बोला आणि पुन्हा प्रयत्न करा.';

  @override
  String get speechDurationDescription => 'कृपया सुनिश्चित करा की आप कमीतकमी 5 सेकंद आणि 90 पेक्षा जास्त नाही बोलता.';

  @override
  String get connectionLostDescription =>
      'कनेक्शन व्यस्त झाला. कृपया आपल्या इंटरनेट कनेक्शन तपासा आणि पुन्हा प्रयत्न करा.';

  @override
  String get howToTakeGoodSample => 'चांगला नमुना कसा घेायचा?';

  @override
  String get goodSampleInstructions =>
      '1. सुनिश्चित करा की आप एक शांत जागेत आहात.\n2. स्पष्टपणे आणि नैसर्गिकरित्या बोला.\n3. सुनिश्चित करा की आपले डिव्हाइस त्याच्या नैसर्गिक स्थितीत आहे, आपल्या गळ्यावर.\n\nएकदा तयार झाल्यानंतर, आप हे सुधारू शकता किंवा पुन्हा करू शकता.';

  @override
  String get noDeviceConnectedUseMic => 'कोणताही डिव्हाइस कनेक्ट नाही. फोन मायक्रोफोन वापरा.';

  @override
  String get doItAgain => 'पुन्हा करा';

  @override
  String get listenToSpeechProfile => 'माझे स्पीच प्रोफाइल ऐका ➡️';

  @override
  String get recognizingOthers => 'इतरांना ओळखत आहे 👀';

  @override
  String get keepGoingGreat => 'सुरू ठेवा, आप उत्तम काम करत आहात';

  @override
  String get somethingWentWrongTryAgain => 'काहीतरी चूक झाली! कृपया नंतर पुन्हा प्रयत्न करा.';

  @override
  String get uploadingVoiceProfile => 'आपले व्हॉइस प्रोफाइल अपलोड करत आहे....';

  @override
  String get memorizingYourVoice => 'आपले व्हॉइस लक्षात ठेवत आहे...';

  @override
  String get personalizingExperience => 'आपला अनुभव व्यक्तिगत करत आहे...';

  @override
  String get keepSpeakingUntil100 => '100% मिळेपर्यंत बोलत ठेवा.';

  @override
  String get greatJobAlmostThere => 'उत्तम काम, आप जवळजवळ तेथे आहात';

  @override
  String get soCloseJustLittleMore => 'इतके जवळ, थोडेसे अधिक';

  @override
  String get notificationFrequency => 'सूचना वारंवारता';

  @override
  String get controlNotificationFrequency => 'Omi किती वेळा सक्रिय सूचना पाठवते हे नियंत्रित करा.';

  @override
  String get yourScore => 'आपला स्कोर';

  @override
  String get dailyScoreBreakdown => 'दैनिक स्कोर विभाजन';

  @override
  String get todaysScore => 'आजचा स्कोर';

  @override
  String get tasksCompleted => 'पूर्ण केलेले कार्य';

  @override
  String get completionRate => 'पूर्णता दर';

  @override
  String get howItWorks => 'हे कसे काम करते';

  @override
  String get dailyScoreExplanation =>
      'आपला दैनिक स्कोर कार्य पूर्णतेवर आधारित आहे. आपला स्कोर सुधारण्यासाठी आपले कार्य पूर्ण करा!';

  @override
  String get notificationFrequencyDescription => 'Omi किती वेळा सक्रिय सूचना आणि स्मरणीये पाठवते हे नियंत्रित करा.';

  @override
  String get sliderOff => 'बंद';

  @override
  String get sliderMax => 'सर्वाधिक';

  @override
  String summaryGeneratedFor(String date) {
    return '$date साठी सारांश तयार केला';
  }

  @override
  String get failedToGenerateSummary => 'सारांश तयार करणे अयोग्य. सुनिश्चित करा की त्या दिवसासाठी संभाषणे आहेत.';

  @override
  String get recap => 'पुनरावलोकन';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" हटवा';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count संभाषणे येथे स्थानांतरित करा:';
  }

  @override
  String get noFolder => 'कोणता फोल्डर नाही';

  @override
  String get removeFromAllFolders => 'सर्व फोल्डरमधून काढा';

  @override
  String get buildAndShareYourCustomApp => 'आपल्या कस्टम अ‍ॅप्लिकेशन तयार करा आणि शेअर करा';

  @override
  String get searchAppsPlaceholder => '1500+ अ‍ॅप्स शोधा';

  @override
  String get filters => 'फिल्टर्स';

  @override
  String get frequencyOff => 'बंद';

  @override
  String get frequencyMinimal => 'किमान';

  @override
  String get frequencyLow => 'कमी';

  @override
  String get frequencyBalanced => 'संतुलित';

  @override
  String get frequencyHigh => 'उच्च';

  @override
  String get frequencyMaximum => 'सर्वाधिक';

  @override
  String get frequencyDescOff => 'कोणत्याही सक्रिय सूचना नाही';

  @override
  String get frequencyDescMinimal => 'केवळ महत्वपूर्ण स्मरणीये';

  @override
  String get frequencyDescLow => 'केवळ महत्वपूर्ण अपडेट्स';

  @override
  String get frequencyDescBalanced => 'नियमित मदतीचे संकेत';

  @override
  String get frequencyDescHigh => 'वारंवार चेक-इन्स';

  @override
  String get frequencyDescMaximum => 'सर्वदा गोंधळ बनवून ठेवा';

  @override
  String get clearChatQuestion => 'चॅट साफ करा?';

  @override
  String get syncingMessages => 'सर्व्हरसह संदेश समन्वय करत आहे...';

  @override
  String get chatAppsTitle => 'चॅट अ‍ॅप्स';

  @override
  String get selectApp => 'अ‍ॅप निवडा';

  @override
  String get noChatAppsEnabled => 'कोणतेही चॅट अ‍ॅप्स सक्षम नाहीत.\n\"अ‍ॅप्स सक्षम करा\" वर टॅप करून काही जोडा.';

  @override
  String get disable => 'अक्षम करा';

  @override
  String get photoLibrary => 'फोटो लायब्रेरी';

  @override
  String get chooseFile => 'फाइल निवडा';

  @override
  String get connectAiAssistantsToYourData => 'AI सहायकांना आपल्या डेटाशी जोडा';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'होमपेजवर आपल्या व्यक्तिगत लक्ष्य ट्रॅक करा';

  @override
  String get deleteRecording => 'रेकॉर्डिंग हटवा';

  @override
  String get thisCannotBeUndone => 'हे पूर्ववत करता येणार नाही.';

  @override
  String get sdCard => 'SD कार्ड';

  @override
  String get fromSd => 'SD वरून';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'जलद स्थानांतर';

  @override
  String get syncingStatus => 'समन्वय करत आहे';

  @override
  String get failedStatus => 'अयोग्य';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'स्थानांतर पद्धत';

  @override
  String get fast => 'जलद';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'फोन';

  @override
  String get cancelSync => 'समन्वय रद्द करा';

  @override
  String get cancelSyncMessage => 'आधीपासूनच डाउनलोड केलेला डेटा सेव्ह केला जाईल. आप नंतर पुन्हा सुरू करू शकता.';

  @override
  String get syncCancelled => 'समन्वय रद्द केला';

  @override
  String get deleteProcessedFiles => 'प्रक्रिया केलेल्या फाइल्स हटवा';

  @override
  String get processedFilesDeleted => 'प्रक्रिया केलेल्या फाइल्स हटवल्या';

  @override
  String get wifiEnableFailed => 'डिव्हाइसवर WiFi सक्षम करणे अयोग्य. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get deviceNoFastTransfer => 'आपल्या डिव्हाइसला जलद स्थानांतर समर्थित नाही. त्याऐवजी Bluetooth वापरा.';

  @override
  String get enableHotspotMessage => 'कृपया आपल्या फोनची हॉटस्पॉट सक्षम करा आणि पुन्हा प्रयत्न करा.';

  @override
  String get transferStartFailed => 'स्थानांतर सुरू करणे अयोग्य. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get deviceNotResponding => 'डिव्हाइस प्रतिसाद दिला नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get invalidWifiCredentials => 'अमान्य WiFi प्रमाणपत्र. आपल्या हॉटस्पॉट सेटिंग्स तपासा.';

  @override
  String get wifiConnectionFailed => 'WiFi कनेक्शन अयोग्य. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get sdCardProcessing => 'SD कार्ड प्रक्रिया करणे';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count रेकॉर्डिंग(s) प्रक्रिया करत आहे. फाइल्स नंतर SD कार्डमधून काढल्या जातील.';
  }

  @override
  String get process => 'प्रक्रिया करा';

  @override
  String get wifiSyncFailed => 'WiFi समन्वय अयोग्य';

  @override
  String get processingFailed => 'प्रक्रिया अयोग्य';

  @override
  String get downloadingFromSdCard => 'SD कार्डमधून डाउनलोड करत आहे';

  @override
  String processingProgress(int current, int total) {
    return 'प्रक्रिया करत आहे $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count संभाषणे तयार केली';
  }

  @override
  String get internetRequired => 'इंटरनेट आवश्यक';

  @override
  String get processAudio => 'ऑडिओ प्रक्रिया करा';

  @override
  String get start => 'सुरू करा';

  @override
  String get noRecordings => 'कोणत्याही रेकॉर्डिंग नाही';

  @override
  String get audioFromOmiWillAppearHere => 'आपल्या Omi डिव्हाइसमधून ऑडिओ येथे दिसेल';

  @override
  String get deleteProcessed => 'प्रक्रिया केलेले हटवा';

  @override
  String get tryDifferentFilter => 'वेगळा फिल्टर वापरून पहा';

  @override
  String get recordings => 'रेकॉर्डिंग्स';

  @override
  String get enableRemindersAccess => 'Apple Reminders वापरण्यासाठी कृपया सेटिंग्समध्ये स्मरणीये प्रवेश सक्षम करा';

  @override
  String todayAtTime(String time) {
    return 'आज $time ला';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'कल $time ला';
  }

  @override
  String get lessThanAMinute => 'एक मिनिटापेक्षा कमी';

  @override
  String estimatedMinutes(int count) {
    return '~$count मिनिट(s)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count तास(s)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'अंदाज: $time उरलेले';
  }

  @override
  String get summarizingConversation => 'संभाषण सारांश करत आहे...\nयाला काही सेकंद लागू शकतात';

  @override
  String get resummarizingConversation => 'संभाषण पुन्हा सारांश करत आहे...\nयाला काही सेकंद लागू शकतात';

  @override
  String get nothingInterestingRetry => 'कोणताही मनोरंजक गोष्ट सापडला नाही,\nपुन्हा प्रयत्न करायचा?';

  @override
  String get noSummaryForConversation => 'या संभाषणासाठी कोणताही सारांश उपलब्ध नाही.';

  @override
  String get unknownLocation => 'अज्ञात स्थान';

  @override
  String get couldNotLoadMap => 'नकाशा लोड करता येत नाही';

  @override
  String get triggerConversationIntegration => 'संभाषण तयार करणे एकीकरण ट्रिगर करा';

  @override
  String get webhookUrlNotSet => 'Webhook URL सेट नाही';

  @override
  String get setWebhookUrlInSettings => 'हे वैशिष्ट्य वापरण्यासाठी कृपया विकासकर्ता सेटिंग्समध्ये webhook URL सेट करा.';

  @override
  String get sendWebUrl => 'वेब url पाठवा';

  @override
  String get sendTranscript => 'प्रतिलेख पाठवा';

  @override
  String get sendSummary => 'सारांश पाठवा';

  @override
  String get debugModeDetected => 'डीबग मोड शोधला गेला';

  @override
  String get performanceReduced => 'कार्यप्रदर्शन 5-10x कमी केले. Release मोड वापरा.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'स्वयंचलितपणे बंद होत आहे ${seconds}s';
  }

  @override
  String get modelRequired => 'मॉडेल आवश्यक';

  @override
  String get downloadWhisperModel => 'कृपया सेव्ह करण्यापूर्वी Whisper मॉडेल डाउनलोड करा.';

  @override
  String get deviceNotCompatible => 'डिव्हाइस संगत नाही';

  @override
  String get deviceRequirements => 'आपल्या डिव्हाइसला ऑन-डिव्हाइस ट्रान्सक्रिप्शनसाठी आवश्यकतांची पूर्तता करत नाही.';

  @override
  String get willLikelyCrash => 'हे सक्षम केल्याने अ‍ॅप क्रॅश किंवा फ्रीজ होण्याची शक्यता आहे.';

  @override
  String get transcriptionSlowerLessAccurate => 'ट्रान्सक्रिप्शन लक्षणीयरित्या मंद आणि कमी अचूक असेल.';

  @override
  String get proceedAnyway => 'तरीही पुढे जा';

  @override
  String get olderDeviceDetected => 'जुने डिव्हाइस शोधला गेला';

  @override
  String get onDeviceSlower => 'ऑन-डिव्हाइस ट्रान्सक्रिप्शन या डिव्हाइसवर मंद असू शकते.';

  @override
  String get batteryUsageHigher => 'बॅटरी वापर क्लाउड ट्रान्सक्रिप्शनपेक्षा जास्त असेल.';

  @override
  String get considerOmiCloud => 'उत्तम कार्यप्रदर्शनासाठी Omi Cloud वापरण्याचा विचार करा.';

  @override
  String get highResourceUsage => 'उच्च संसाधन वापर';

  @override
  String get onDeviceIntensive => 'ऑन-डिव्हाइस ट्रान्सक्रिप्शन संगणकीयपणे गहन आहे.';

  @override
  String get batteryDrainIncrease => 'बॅटरी ड्रेन लक्षणीयरित्या वाढेल.';

  @override
  String get deviceMayWarmUp => 'विस्तारित वापराच्या वेळी डिव्हाइस गरम होऊ शकते.';

  @override
  String get speedAccuracyLower => 'गती आणि अचूकता Cloud मॉडेल्सपेक्षा कमी असू शकतात.';

  @override
  String get cloudProvider => 'क्लाउड प्रदाता';

  @override
  String get premiumMinutesInfo =>
      '1,200 प्रीमियम मिनिटे/महिना. ऑन-डिव्हाइस टॅब अमर्यादित विनामूल्य ट्रान्सक्रिप्शन ऑफर करते.';

  @override
  String get viewUsage => 'वापर पहा';

  @override
  String get localProcessingInfo =>
      'ऑडिओ स्थानिकरित्या प्रक्रिया केला जातो. ऑफलाइन कार्य करते, अधिक खाजगी, परंतु अधिक बॅटरी वापरते.';

  @override
  String get model => 'मॉडेल';

  @override
  String get performanceWarning => 'कार्यप्रदर्शन सावधानी';

  @override
  String get largeModelWarning =>
      'हा मॉडेल मोठा आहे आणि मोबाइल डिव्हाइसवर अ‍ॅप क्रॅश किंवा खूप मंद चालू शकतो.\n\n\"small\" किंवा \"base\" अनुशंसित आहे.';

  @override
  String get usingNativeIosSpeech => 'नेटिव्ह iOS स्पीच रिकग्निशन वापरत आहे';

  @override
  String get noModelDownloadRequired => 'आपल्या डिव्हाइसचा नेटिव्ह स्पीच इंजिन वापरला जाईल. मॉडेल डाउनलोड आवश्यक नाही.';

  @override
  String get modelReady => 'मॉडेल तयार';

  @override
  String get redownload => 'पुन्हा डाउनलोड करा';

  @override
  String get doNotCloseApp => 'कृपया अ‍ॅप बंद करू नका.';

  @override
  String get downloading => 'डाउनलोड करत आहे...';

  @override
  String get downloadModel => 'मॉडेल डाउनलोड करा';

  @override
  String estimatedSize(String size) {
    return 'अंदाजित आकार: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'उपलब्ध जागा: $space';
  }

  @override
  String get notEnoughSpace => 'चेतावणी: पुरेशी जागा नाही!';

  @override
  String get download => 'डाउनलोड करा';

  @override
  String downloadError(String error) {
    return 'डाउनलोड त्रुटी: $error';
  }

  @override
  String get cancelled => 'रद्द केले';

  @override
  String get deviceNotCompatibleTitle => 'डिव्हाइस संगत नाही';

  @override
  String get deviceNotMeetRequirements =>
      'आपल्या डिव्हाइसला ऑन-डिव्हाइस ट्रान्सक्रिप्शनसाठी आवश्यकतांची पूर्तता करत नाही.';

  @override
  String get transcriptionSlowerOnDevice => 'ऑन-डिव्हाइस ट्रान्सक्रिप्शन या डिव्हाइसवर मंद असू शकते.';

  @override
  String get computationallyIntensive => 'ऑन-डिव्हाइस ट्रान्सक्रिप्शन संगणकीयपणे गहन आहे.';

  @override
  String get batteryDrainSignificantly => 'बॅटरी ड्रेन लक्षणीयरित्या वाढेल.';

  @override
  String get premiumMinutesMonth =>
      '1,200 प्रीमियम मिनिटे/महिना. ऑन-डिव्हाइस टॅब अमर्यादित विनामूल्य ट्रान्सक्रिप्शन ऑफर करते. ';

  @override
  String get audioProcessedLocally =>
      'ऑडिओ स्थानिकरित्या प्रक्रिया केला जातो. ऑफलाइन कार्य करते, अधिक खाजगी, परंतु अधिक बॅटरी वापरते.';

  @override
  String get languageLabel => 'भाषा';

  @override
  String get modelLabel => 'मॉडेल';

  @override
  String get modelTooLargeWarning =>
      'हा मॉडेल मोठा आहे आणि मोबाइल डिव्हाइसवर अ‍ॅप क्रॅश किंवा खूप मंद चालू शकतो.\n\n\"small\" किंवा \"base\" अनुशंसित आहे.';

  @override
  String get nativeEngineNoDownload => 'आपल्या डिव्हाइसचा नेटिव्ह स्पीच इंजिन वापरला जाईल. मॉडेल डाउनलोड आवश्यक नाही.';

  @override
  String modelReadyWithName(String model) {
    return 'मॉडेल तयार ($model)';
  }

  @override
  String get reDownload => 'पुन्हा डाउनलोड करा';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model डाउनलोड करत आहे: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model तयार करत आहे...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'डाउनलोड त्रुटी: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'अंदाजित आकार: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'उपलब्ध जागा: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omi चा अंतर्निर्मित लाइव्ह ट्रान्सक्रिप्शन स्वयंचलित स्पीकर शोध आणि डायराइজेशनसह रिअल-टाइम संभाषणांसाठी अनुकूलित आहे.';

  @override
  String get reset => 'पुनःसेट करा';

  @override
  String get useTemplateFrom => 'येथून टेम्पलेट वापरा';

  @override
  String get selectProviderTemplate => 'प्रदाता टेम्पलेट निवडा...';

  @override
  String get quicklyPopulateResponse => 'ज्ञात प्रदाता प्रतिसाद स्वरूपसह जलद भरा';

  @override
  String get quicklyPopulateRequest => 'ज्ञात प्रदाता विनंती स्वरूपसह जलद भरा';

  @override
  String get invalidJsonError => 'अमान्य JSON';

  @override
  String downloadModelWithName(String model) {
    return 'मॉडेल डाउनलोड करा ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'मॉडेल: $model';
  }

  @override
  String get device => 'डिव्हाइस';

  @override
  String get chatAssistantsTitle => 'चॅट सहायक';

  @override
  String get permissionReadConversations => 'संभाषणे वाचा';

  @override
  String get permissionReadMemories => 'स्मृती वाचा';

  @override
  String get permissionReadTasks => 'कार्य वाचा';

  @override
  String get permissionCreateConversations => 'संभाषणे तयार करा';

  @override
  String get permissionCreateMemories => 'स्मृती तयार करा';

  @override
  String get permissionTypeAccess => 'प्रवेश';

  @override
  String get permissionTypeCreate => 'तयार करा';

  @override
  String get permissionTypeTrigger => 'ट्रिगर करा';

  @override
  String get permissionDescReadConversations => 'हे अ‍ॅप आपल्या संभाषणांना प्रवेश करू शकते.';

  @override
  String get permissionDescReadMemories => 'हे अ‍ॅप आपल्या स्मृतीना प्रवेश करू शकते.';

  @override
  String get permissionDescReadTasks => 'हे अ‍ॅप आपल्या कार्यांना प्रवेश करू शकते.';

  @override
  String get permissionDescCreateConversations => 'हे अ‍ॅप नवीन संभाषणे तयार करू शकते.';

  @override
  String get permissionDescCreateMemories => 'हे अ‍ॅप नवीन स्मृती तयार करू शकते.';

  @override
  String get realtimeListening => 'रिअल-टाइम श्रवण';

  @override
  String get setupCompleted => 'पूर्ण';

  @override
  String get pleaseSelectRating => 'कृपया रेटिंग निवडा';

  @override
  String get writeReviewOptional => 'पुनरावलोकन लिहा (पर्यायी)';

  @override
  String get setupQuestionsIntro => 'काही प्रश्नांची उत्तरे देऊन Omi सुधारण्यास मदत करा.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. आप काय करता?';

  @override
  String get setupQuestionUsage => '2. आप आपल्या Omi कोठे वापरण्याचा योजना करता?';

  @override
  String get setupQuestionAge => '3. आपल्या वयाचा श्रेणी कोणता आहे?';

  @override
  String get setupAnswerAllQuestions => 'आपण अजून सर्व प्रश्नांची उत्तरे दिली नाहीत! 🥺';

  @override
  String get setupSkipHelp => 'स्किप करा, मला मदत करायची नाही :C';

  @override
  String get professionEntrepreneur => 'उद्योगस्थ';

  @override
  String get professionSoftwareEngineer => 'सॉफ्टवेअर अभियंता';

  @override
  String get professionProductManager => 'उत्पाद व्यवस्थापक';

  @override
  String get professionExecutive => 'कार्यकारी';

  @override
  String get professionSales => 'विक्रय';

  @override
  String get professionStudent => 'विद्यार्थी';

  @override
  String get usageAtWork => 'काम करताना';

  @override
  String get usageIrlEvents => 'IRL इव्हेंट्स';

  @override
  String get usageOnline => 'ऑनलाइन';

  @override
  String get usageSocialSettings => 'सामाजिक सेटिंग्समध्ये';

  @override
  String get usageEverywhere => 'सर्वत्र';

  @override
  String get customBackendUrlTitle => 'कस्टम बैकएंड URL';

  @override
  String get backendUrlLabel => 'बैकएंड URL';

  @override
  String get saveUrlButton => 'URL सेव्ह करा';

  @override
  String get enterBackendUrlError => 'कृपया बैकएंड URL प्रविष्ट करा';

  @override
  String get urlMustEndWithSlashError => 'URL \"/\" सह समाप्त होणे आवश्यक आहे';

  @override
  String get invalidUrlError => 'कृपया वैध URL प्रविष्ट करा';

  @override
  String get backendUrlSavedSuccess => 'बैकएंड URL यशस्वीरित्या सेव्ह केला!';

  @override
  String get signInTitle => 'साइन इन करा';

  @override
  String get signInButton => 'साइन इन करा';

  @override
  String get enterEmailError => 'कृपया आपल्या ईमेल प्रविष्ट करा';

  @override
  String get invalidEmailError => 'कृपया वैध ईमेल प्रविष्ट करा';

  @override
  String get enterPasswordError => 'कृपया आपल्या पासवर्ड प्रविष्ट करा';

  @override
  String get passwordMinLengthError => 'पासवर्ड कमीतकमी 8 वर्ण लांब असणे आवश्यक आहे';

  @override
  String get signInSuccess => 'साइन इन यशस्वी!';

  @override
  String get alreadyHaveAccountLogin => 'आधीपासून खाते आहे? लॉगइन करा';

  @override
  String get emailLabel => 'ईमेल';

  @override
  String get passwordLabel => 'पासवर्ड';

  @override
  String get createAccountTitle => 'खाते तयार करा';

  @override
  String get nameLabel => 'नाव';

  @override
  String get repeatPasswordLabel => 'पासवर्ड पुन्हा करा';

  @override
  String get signUpButton => 'साइन अप करा';

  @override
  String get enterNameError => 'कृपया आपल्या नाव प्रविष्ट करा';

  @override
  String get passwordsDoNotMatch => 'पासवर्ड जुळत नाहीत';

  @override
  String get signUpSuccess => 'साइन अप यशस्वी!';

  @override
  String get loadingKnowledgeGraph => 'ज्ञान आलेख लोड करत आहे...';

  @override
  String get noKnowledgeGraphYet => 'अजून कोणताही ज्ञान आलेख नाही';

  @override
  String get buildingKnowledgeGraphFromMemories => 'स्मृतीमधून आपला ज्ञान आलेख तयार करत आहे...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'आपल्या ज्ञान आलेखा स्वयंचलितपणे तयार केले जातील कारण आप नवीन स्मृती तयार करता.';

  @override
  String get buildGraphButton => 'आलेख तयार करा';

  @override
  String get checkOutMyMemoryGraph => 'माझा स्मृती आलेख पहा!';

  @override
  String get getButton => 'मिळवा';

  @override
  String openingApp(String appName) {
    return '$appName उघडत आहे...';
  }

  @override
  String get writeSomething => 'काहीतरी लिहा';

  @override
  String get submitReply => 'प्रतिसाद सबमिट करा';

  @override
  String get editYourReply => 'आपल्या प्रतिसाद संपादित करा';

  @override
  String get replyToReview => 'पुनरावलोकनाला प्रतिसाद द्या';

  @override
  String get rateAndReviewThisApp => 'या अ‍ॅपला रेट करा आणि पुनरावलोकन करा';

  @override
  String get noChangesInReview => 'पुनरावलोकन अपडेट करण्यासाठी कोणतेही बदल नाहीत.';

  @override
  String get cantRateWithoutInternet => 'इंटरनेट कनेक्शन शिवाय अ‍ॅपला रेट करू शकत नाही.';

  @override
  String get appAnalytics => 'अ‍ॅप विश्लेषण';

  @override
  String get learnMoreLink => 'अधिक जाणून घ्या';

  @override
  String get moneyEarned => 'कमाविलेले पैसे';

  @override
  String get writeYourReply => 'आपल्या प्रतिसाद लिहा...';

  @override
  String get replySentSuccessfully => 'प्रतिसाद यशस्वीरित्या पाठविला';

  @override
  String failedToSendReply(String error) {
    return 'प्रतिसाद पाठवणे अयोग्य: $error';
  }

  @override
  String get send => 'पाठवा';

  @override
  String starFilter(int count) {
    return '$count तारा';
  }

  @override
  String get noReviewsFound => 'कोणतेही पुनरावलोकन सापडले नाही';

  @override
  String get editReply => 'प्रतिसाद संपादित करा';

  @override
  String get reply => 'प्रतिसाद द्या';

  @override
  String starFilterLabel(int count) {
    return '$count तारा';
  }

  @override
  String get sharePublicLink => 'सार्वजनिक लिंक शेअर करा';

  @override
  String get connectedKnowledgeData => 'जोडलेला ज्ञान डेटा';

  @override
  String get enterName => 'नाव प्रविष्ट करा';

  @override
  String get goal => 'लक्ष्य';

  @override
  String get tapToTrackThisGoal => 'या लक्ष्याचा मागोवा घेण्यासाठी टॅप करा';

  @override
  String get tapToSetAGoal => 'लक्ष्य सेट करण्यासाठी टॅप करा';

  @override
  String get processedConversations => 'प्रक्रिया केलेले संभाषणे';

  @override
  String get updatedConversations => 'अपडेट केलेले संभाषणे';

  @override
  String get newConversations => 'नवीन संभाषणे';

  @override
  String get summaryTemplate => 'सारांश टेम्पलेट';

  @override
  String get suggestedTemplates => 'सुझाव दिलेले टेम्पलेट्स';

  @override
  String get otherTemplates => 'इतर टेम्पलेट्स';

  @override
  String get availableTemplates => 'उपलब्ध टेम्पलेट्स';

  @override
  String get getCreative => 'सर्जनशील व्हा';

  @override
  String get defaultLabel => 'डिफॉल्ट';

  @override
  String get lastUsedLabel => 'शेवटचा वापर';

  @override
  String get setDefaultApp => 'डिफॉल्ट अ‍ॅप सेट करा';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName हे आपल्या डिफॉल्ट सारांश अ‍ॅप म्हणून सेट करायचे?\n\nहे अ‍ॅप सर्व भविष्यातील संभाषण सारांशांसाठी स्वयंचलितपणे वापरला जाईल.';
  }

  @override
  String get setDefaultButton => 'डिफॉल्ट सेट करा';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName डिफॉल्ट सारांश अ‍ॅप म्हणून सेट केले';
  }

  @override
  String get createCustomTemplate => 'कस्टम टेम्पलेट तयार करा';

  @override
  String get allTemplates => 'सर्व टेम्पलेट्स';

  @override
  String failedToInstallApp(String appName) {
    return '$appName इंस्टॉल करणे अयोग्य. कृपया पुन्हा प्रयत्न करा.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appName इंस्टॉल करतेवेळी त्रुटी: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'स्पीकर टॅग करा $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'या नावाचा व्यक्ती आधीपासून अस्तित्वात आहे.';

  @override
  String get selectYouFromList => 'स्वत: टॅग करण्यासाठी, कृपया सूचीमधून \"आप\" निवडा.';

  @override
  String get enterPersonsName => 'व्यक्तीचे नाव प्रविष्ट करा';

  @override
  String get addPerson => 'व्यक्ती जोडा';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'या स्पीकरमधून इतर विभाग टॅग करा ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'इतर विभाग टॅग करा';

  @override
  String get managePeople => 'लोकांना व्यवस्थापित करा';

  @override
  String get shareViaSms => 'SMS द्वारे शेअर करा';

  @override
  String get selectContactsToShareSummary => 'आपल्या संभाषण सारांश शेअर करण्यासाठी संपर्क निवडा';

  @override
  String get searchContactsHint => 'संपर्कांचा शोध घ्या...';

  @override
  String contactsSelectedCount(int count) {
    return '$count निवडले';
  }

  @override
  String get clearAllSelection => 'सर्व साफ करा';

  @override
  String get selectContactsToShare => 'शेअर करण्यासाठी संपर्क निवडा';

  @override
  String shareWithContactCount(int count) {
    return '$count संपर्कसह शेअर करा';
  }

  @override
  String shareWithContactsCount(int count) {
    return '$count संपर्कांसह शेअर करा';
  }

  @override
  String get contactsPermissionRequired => 'संपर्क परवानगी आवश्यक';

  @override
  String get contactsPermissionRequiredForSms => 'SMS द्वारे शेअर करण्यासाठी संपर्क परवानगी आवश्यक आहे';

  @override
  String get grantContactsPermissionForSms => 'कृपया SMS द्वारे शेअर करण्यासाठी संपर्क परवानगी दिहा';

  @override
  String get noContactsWithPhoneNumbers => 'फोन नंबरसह कोणतेही संपर्क सापडले नाहीत';

  @override
  String get noContactsMatchSearch => 'कोणतेही संपर्क आपल्या शोधाशी जुळत नाहीत';

  @override
  String get failedToLoadContacts => 'संपर्क लोड करणे अयोग्य';

  @override
  String get failedToPrepareConversationForSharing =>
      'शेअर करण्यासाठी संभाषण तयार करणे अयोग्य. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get couldNotOpenSmsApp => 'SMS अ‍ॅप उघडता येत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'आमरा फक्त चर्चा केलेले येथे आहे: $link';
  }

  @override
  String get wifiSync => 'WiFi समन्वय';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item क्लिपबोर्डवर कॉपी केले';
  }

  @override
  String get wifiConnectionFailedTitle => 'कनेक्शन अयोग्य';

  @override
  String connectingToDeviceName(String deviceName) {
    return '$deviceName शी कनेक्ट करत आहे';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '$deviceName चा WiFi सक्षम करा';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return '$deviceName शी कनेक्ट करा';
  }

  @override
  String get recordingDetails => 'रेकॉर्डिंग तपशील';

  @override
  String get storageLocationSdCard => 'SD कार्ड';

  @override
  String get storageLocationLimitlessPendant => 'Limitless पेंडेंट';

  @override
  String get storageLocationPhone => 'फोन';

  @override
  String get storageLocationPhoneMemory => 'फोन (स्मृती)';

  @override
  String storedOnDevice(String deviceName) {
    return '$deviceName वर संग्रहित';
  }

  @override
  String get transferring => 'स्थानांतरित करत आहे...';

  @override
  String get transferRequired => 'स्थानांतर आवश्यक';

  @override
  String get downloadingAudioFromSdCard => 'आपल्या डिव्हाइसच्या SD कार्डमधून ऑडिओ डाउनलोड करत आहे';

  @override
  String get transferRequiredDescription =>
      'हे रेकॉर्डिंग आपल्या डिव्हाइसच्या SD कार्डवर संग्रहित आहे. प्ले किंवा शेअर करण्यासाठी त्याचे आपल्या फोनवर स्थानांतर करा.';

  @override
  String get cancelTransfer => 'स्थानांतर रद्द करा';

  @override
  String get transferToPhone => 'फोनवर स्थानांतरित करा';

  @override
  String get privateAndSecureOnDevice => 'आपल्या डिव्हाइसवर खाजगी आणि सुरक्षित';

  @override
  String get recordingInfo => 'रेकॉर्डिंग माहिती';

  @override
  String get transferInProgress => 'स्थानांतरण चल रहे आहे...';

  @override
  String get shareRecording => 'रेकॉर्डिंग शेयर करा';

  @override
  String get deleteRecordingConfirmation =>
      'आपण खरोखर या रेकॉर्डिंगला कायमीपणे हटवू इच्छिता का? हे पूर्ववत करता येणार नाही.';

  @override
  String get recordingIdLabel => 'रेकॉर्डिंग आयडी';

  @override
  String get dateTimeLabel => 'तारीख आणि वेळ';

  @override
  String get durationLabel => 'कालावधी';

  @override
  String get audioFormatLabel => 'ऑडिओ फॉर्मेट';

  @override
  String get storageLocationLabel => 'स्टोरेज स्थान';

  @override
  String get estimatedSizeLabel => 'अंदाजे आकार';

  @override
  String get deviceModelLabel => 'डिव्हाइस मॉडेल';

  @override
  String get deviceIdLabel => 'डिव्हाइस आयडी';

  @override
  String get statusLabel => 'स्थिती';

  @override
  String get statusProcessed => 'प्रक्रिया केली';

  @override
  String get statusUnprocessed => 'अप्रक्रिया';

  @override
  String get switchedToFastTransfer => 'फास्ट ट्रांसफरवर स्विच केले';

  @override
  String get transferCompleteMessage => 'स्थानांतरण पूर्ण! आता आप्पण ही रेकॉर्डिंग प्ले करू शकता.';

  @override
  String transferFailedMessage(String error) {
    return 'स्थानांतरण अयशस्वी: $error';
  }

  @override
  String get transferCancelled => 'स्थानांतरण रद्द केले';

  @override
  String get fastTransferEnabled => 'फास्ट ट्रांसफर सक्षम केले';

  @override
  String get bluetoothSyncEnabled => 'ब्लूटूथ सिंक सक्षम केला';

  @override
  String get enableFastTransfer => 'फास्ट ट्रांसफर सक्षम करा';

  @override
  String get fastTransferDescription =>
      'फास्ट ट्रांसफर WiFi वापरून ~5x वेगवान गती देतो. आपले फोन स्थानांतरणादरम्यान आपल्या Omi डिव्हाइसच्या WiFi नेटवर्कला तात्पुरते जोडेल.';

  @override
  String get internetAccessPausedDuringTransfer => 'स्थानांतरणादरम्यान इंटरनेट प्रवेश सक्षम केला आहे';

  @override
  String get chooseTransferMethodDescription =>
      'आपल्या Omi डिव्हाइसमधून आपल्या फोनवर रेकॉर्डिंग कसे स्थानांतरित करायचे ते निवडा.';

  @override
  String get wifiSpeed => 'WiFi द्वारे ~150 KB/s';

  @override
  String get fiveTimesFaster => '५X वेगवान';

  @override
  String get fastTransferMethodDescription =>
      'आपल्या Omi डिव्हाइसला थेट WiFi कनेक्शन तयार करते. स्थानांतरणादरम्यान आपले फोन आपल्या नियमित WiFi पासून तात्पुरते डिस्कनेक्ट होईल.';

  @override
  String get bluetooth => 'ब्लूटूथ';

  @override
  String get bleSpeed => 'BLE द्वारे ~30 KB/s';

  @override
  String get bluetoothMethodDescription =>
      'मानक ब्लूटूथ कम ऊर्जा कनेक्शन वापरते. हळू पण आपल्या WiFi कनेक्शनवर परिणाम करत नाही.';

  @override
  String get selected => 'निवडले';

  @override
  String get selectOption => 'निवडा';

  @override
  String get lowBatteryAlertTitle => 'कमी बॅटरी सूचना';

  @override
  String get lowBatteryAlertBody => 'आपली डिव्हाइस बॅटरीवर कमी चल रही आहे. रिचार्जने वेळ आली! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'आपली Omi डिव्हाइस डिस्कनेक्ट झाली';

  @override
  String get deviceDisconnectedNotificationBody => 'कृपया आपल्या Omi वापरणे चालू ठेवण्यासाठी पुन्हा कनेक्ट करा.';

  @override
  String get firmwareUpdateAvailable => 'फर्मवेअर अपडेट उपलब्ध';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'आपल्या Omi डिव्हाइससाठी नवीन फर्मवेअर अपडेट ($version) उपलब्ध आहे. आता अपडेट करू इच्छिता का?';
  }

  @override
  String get later => 'नंतर';

  @override
  String get appDeletedSuccessfully => 'अॅप यशस्वीरित्या हटवली गेली';

  @override
  String get appDeleteFailed => 'अॅप हटवण्यात अयशस्वी. कृपया नंतर पुन्हा प्रयत्न करा.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'अॅप दृश्यमानता यशस्वीरित्या बदलली. प्रतिबिंबित होण्यास काही मिनिटे लागू शकतात.';

  @override
  String get errorActivatingAppIntegration =>
      'अॅप सक्रिय करण्यात त्रुटी. जर हे एकीकरण अॅप असेल तर सेटअप पूर्ण झाले आहे याची खात्री करा.';

  @override
  String get errorUpdatingAppStatus => 'अॅप स्थिती अपडेट करताना त्रुटी आली.';

  @override
  String get calculatingETA => 'गणना करत आहे...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'लगभग $minutes मिनिटे शेष';
  }

  @override
  String get aboutAMinuteRemaining => 'लगभग एक मिनिट शेष';

  @override
  String get almostDone => 'जवळजवळ पूर्ण...';

  @override
  String get omiSays => 'omi म्हणते';

  @override
  String get analyzingYourData => 'आपल्या डेटा विश्लेषण करत आहे...';

  @override
  String migratingToProtection(String level) {
    return '$level सुरक्षेला स्थलांतरित करत आहे...';
  }

  @override
  String get noDataToMigrateFinalizing => 'स्थलांतरित करण्यासाठी कोणताही डेटा नाही. अंतिम करत आहे...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType स्थलांतरित करत आहे... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'सर्व ऑब्जेक्ट्स स्थलांतरित केले. अंतिम करत आहे...';

  @override
  String get migrationErrorOccurred => 'स्थलांतरणादरम्यान त्रुटी आली. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get migrationComplete => 'स्थलांतरण पूर्ण!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'आपल्या डेटा आता नवीन $level सेटिंग्जसह सुरक्षित आहे.';
  }

  @override
  String get chatsLowercase => 'चॅट';

  @override
  String get dataLowercase => 'डेटा';

  @override
  String get fallNotificationTitle => 'अरे';

  @override
  String get fallNotificationBody => 'आप्पण पडले का?';

  @override
  String get importantConversationTitle => 'महत्वाचे संभाषण';

  @override
  String get importantConversationBody =>
      'आप्पणे नुकताच एक महत्वाचे संभाषण केले. इतरांसह सारांश शेयर करण्यासाठी टॅप करा.';

  @override
  String get templateName => 'टेम्पलेट नाव';

  @override
  String get templateNameHint => 'उदा., मीटिंग अॅक्शन आयटम एक्सट्रॅक्टर';

  @override
  String get nameMustBeAtLeast3Characters => 'नाव किमान 3 वर्ण असणे आवश्यक आहे';

  @override
  String get conversationPromptHint => 'उदा., प्रदान केलेल्या संभाषणातून कार्य आयटम, निर्णय आणि मुख्य मुद्दे निकाळा.';

  @override
  String get pleaseEnterAppPrompt => 'कृपया आपल्या अॅपसाठी एक प्रॉम्प्ट प्रविष्ट करा';

  @override
  String get promptMustBeAtLeast10Characters => 'प्रॉम्प्ट किमान 10 वर्ण असणे आवश्यक आहे';

  @override
  String get anyoneCanDiscoverTemplate => 'कोणीही आपल्या टेम्पलेट शोधू शकतो';

  @override
  String get onlyYouCanUseTemplate => 'केवळ आप्पण या टेम्पलेटचा वापर करू शकता';

  @override
  String get generatingDescription => 'विवरण तयार करत आहे...';

  @override
  String get creatingAppIcon => 'अॅप आयकन तयार करत आहे...';

  @override
  String get installingApp => 'अॅप स्थापित करत आहे...';

  @override
  String get appCreatedAndInstalled => 'अॅप तयार आणि स्थापित केली गेली!';

  @override
  String get appCreatedSuccessfully => 'अॅप यशस्वीरित्या तयार केली गेली!';

  @override
  String get failedToCreateApp => 'अॅप तयार करण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get addAppSelectCoreCapability => 'कृपया आपल्या अॅपसाठी आगे जाण्यासाठी एक अधिक मूल क्षमता निवडा';

  @override
  String get addAppSelectPaymentPlan => 'कृपया आपल्या अॅपसाठी पेमेंट योजना निवडा आणि किंमत प्रविष्ट करा';

  @override
  String get addAppSelectCapability => 'कृपया आपल्या अॅपसाठी किमान एक क्षमता निवडा';

  @override
  String get addAppSelectLogo => 'कृपया आपल्या अॅपसाठी लोगो निवडा';

  @override
  String get addAppEnterChatPrompt => 'कृपया आपल्या अॅपसाठी चॅट प्रॉम्प्ट प्रविष्ट करा';

  @override
  String get addAppEnterConversationPrompt => 'कृपया आपल्या अॅपसाठी संभाषण प्रॉम्प्ट प्रविष्ट करा';

  @override
  String get addAppSelectTriggerEvent => 'कृपया आपल्या अॅपसाठी ट्रिगर इव्हेंट निवडा';

  @override
  String get addAppEnterWebhookUrl => 'कृपया आपल्या अॅपसाठी webhook URL प्रविष्ट करा';

  @override
  String get addAppSelectCategory => 'कृपया आपल्या अॅपसाठी श्रेणी निवडा';

  @override
  String get addAppFillRequiredFields => 'कृपया सर्व आवश्यक फील्ड योग्यरित्या भरा';

  @override
  String get addAppUpdatedSuccess => 'अॅप यशस्वीरित्या अपडेट केली गेली 🚀';

  @override
  String get addAppUpdateFailed => 'अॅप अपडेट करण्यात अयशस्वी. कृपया नंतर पुन्हा प्रयत्न करा';

  @override
  String get addAppSubmittedSuccess => 'अॅप यशस्वीरित्या सादर केली गेली 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'फाइल पिकर उघडण्यात त्रुटी: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'प्रतिमा निवडण्यात त्रुटी: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'फोटो परवानगी नाकारली गेली. प्रतिमा निवडण्यासाठी फोटोमध्ये प्रवेश अनुमती द्या';

  @override
  String get addAppErrorSelectingImageRetry => 'प्रतिमा निवडण्यात त्रुटी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'थंबनेल निवडण्यात त्रुटी: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'थंबनेल निवडण्यात त्रुटी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Persona सह इतर क्षमता निवडल्या जाऊ शकत नाहीत';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona इतर क्षमतेसह निवडली जाऊ शकत नाही';

  @override
  String get paymentFailedToFetchCountries => 'समर्थित देश आणले अयशस्वी. कृपया नंतर पुन्हा प्रयत्न करा.';

  @override
  String get paymentFailedToSetDefault => 'डिफॉल्ट पेमेंट पद्धती सेट करण्यात अयशस्वी. कृपया नंतर पुन्हा प्रयत्न करा.';

  @override
  String get paymentFailedToSavePaypal => 'PayPal तपशील जतन करण्यात अयशस्वी. कृपया नंतर पुन्हा प्रयत्न करा.';

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
  String get paymentStatusConnected => 'कनेक्ट केली';

  @override
  String get paymentStatusNotConnected => 'कनेक्ट नाही';

  @override
  String get paymentAppCost => 'अॅप खर्च';

  @override
  String get paymentEnterValidAmount => 'कृपया वैध रक्कम प्रविष्ट करा';

  @override
  String get paymentEnterAmountGreaterThanZero => 'कृपया 0 पेक्षा मोठी रक्कम प्रविष्ट करा';

  @override
  String get paymentPlan => 'पेमेंट योजना';

  @override
  String get paymentNoneSelected => 'कोणतेही निवडले नाही';

  @override
  String get aiGenPleaseEnterDescription => 'कृपया आपल्या अॅपसाठी विवरण प्रविष्ट करा';

  @override
  String get aiGenCreatingAppIcon => 'अॅप आयकन तयार करत आहे...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'त्रुटी आली: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'अॅप यशस्वीरित्या तयार केली गेली!';

  @override
  String get aiGenFailedToCreateApp => 'अॅप तयार करण्यात अयशस्वी';

  @override
  String get aiGenErrorWhileCreatingApp => 'अॅप तयार करताना त्रुटी आली';

  @override
  String get aiGenFailedToGenerateApp => 'अॅप तयार करण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get aiGenFailedToRegenerateIcon => 'आयकन पुन्हा तयार करण्यात अयशस्वी';

  @override
  String get aiGenPleaseGenerateAppFirst => 'कृपया प्रथम अॅप तयार करा';

  @override
  String get nextButton => 'पुढील';

  @override
  String get connectOmiDevice => 'Omi डिव्हाइस कनेक्ट करा';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'आप्पण आपल्या Unlimited योजना $title वर स्विच करत आहात. आप्पण आगे जाण्यास खरोखर इच्छुक आहात का?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'अपग्रेड शेड्यूल केली! आपली मासिक योजना आपल्या बिलिंग कालावधीच्या शेवटपर्यंत चालू राहते, नंतर स्वयंचलितपणे वार्षिकमध्ये स्विच होते.';

  @override
  String get couldNotSchedulePlanChange => 'योजना बदल शेड्यूल करू शकत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get subscriptionReactivatedDefault =>
      'आपल्या सदस्यता पुन्हा सक्रिय केली गेली! आता कोणत्याही शुल्कास नाही - आपल्या वर्तमान कालावधीच्या शेवटी आपल्यास शुल्क दिले जाईल.';

  @override
  String get subscriptionSuccessfulCharged => 'सदस्यता यशस्वी! आपल्यास नवीन बिलिंग कालावधीसाठी शुल्क दिले गेले आहे.';

  @override
  String get couldNotProcessSubscription => 'सदस्यता प्रक्रिया करू शकत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get couldNotLaunchUpgradePage => 'अपग्रेड पृष्ठ लॉन्च करू शकत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get transcriptionJsonPlaceholder => 'आपल्या JSON कॉन्फिगरेशन येथे पेस्ट करा...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'फाइल पिकर उघडण्यात त्रुटी: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'त्रुटी: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'संभाषण यशस्वीरित्या विलीन केले';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count संभाषण यशस्वीरित्या विलीन केली गेली';
  }

  @override
  String get actionItemReminderTitle => 'Omi स्मरणपत्र';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName डिस्कनेक्ट झाली';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'कृपया आपल्या $deviceName वापरणे चालू ठेवण्यासाठी पुन्हा कनेक्ट करा.';
  }

  @override
  String get onboardingSignIn => 'साइन इन करा';

  @override
  String get onboardingYourName => 'आपले नाव';

  @override
  String get onboardingLanguage => 'भाषा';

  @override
  String get onboardingPermissions => 'परवानग्या';

  @override
  String get onboardingComplete => 'पूर्ण';

  @override
  String get onboardingWelcomeToOmi => 'Omi मध्ये स्वागतम';

  @override
  String get onboardingTellUsAboutYourself => 'आपल्याविषयी आमला सांगा';

  @override
  String get onboardingChooseYourPreference => 'आपली पसंद निवडा';

  @override
  String get onboardingGrantRequiredAccess => 'आवश्यक प्रवेश द्या';

  @override
  String get onboardingYoureAllSet => 'सर्व तयार आहात';

  @override
  String get searchTranscriptOrSummary => 'टेप किंवा सारांश शोधा...';

  @override
  String get myGoal => 'माझे लक्ष्य';

  @override
  String get appNotAvailable => 'अरे! असे दिसते की आप्पण शोधत असलेली अॅप उपलब्ध नाही.';

  @override
  String get failedToConnectTodoist => 'Todoist वर कनेक्ट करण्यात अयशस्वी';

  @override
  String get failedToConnectAsana => 'Asana वर कनेक्ट करण्यात अयशस्वी';

  @override
  String get failedToConnectGoogleTasks => 'Google Tasks वर कनेक्ट करण्यात अयशस्वी';

  @override
  String get failedToConnectClickUp => 'ClickUp वर कनेक्ट करण्यात अयशस्वी';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName वर कनेक्ट करण्यात अयशस्वी: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Todoist वर यशस्वीरित्या कनेक्ट केले!';

  @override
  String get failedToConnectTodoistRetry => 'Todoist वर कनेक्ट करण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get successfullyConnectedAsana => 'Asana वर यशस्वीरित्या कनेक्ट केले!';

  @override
  String get failedToConnectAsanaRetry => 'Asana वर कनेक्ट करण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get successfullyConnectedGoogleTasks => 'Google Tasks वर यशस्वीरित्या कनेक्ट केले!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google Tasks वर कनेक्ट करण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get successfullyConnectedClickUp => 'ClickUp वर यशस्वीरित्या कनेक्ट केले!';

  @override
  String get failedToConnectClickUpRetry => 'ClickUp वर कनेक्ट करण्यात अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get successfullyConnectedNotion => 'Notion वर यशस्वीरित्या कनेक्ट केले!';

  @override
  String get failedToRefreshNotionStatus => 'Notion कनेक्शन स्थिती ताजी करण्यात अयशस्वी.';

  @override
  String get successfullyConnectedGoogle => 'Google वर यशस्वीरित्या कनेक्ट केले!';

  @override
  String get failedToRefreshGoogleStatus => 'Google कनेक्शन स्थिती ताजी करण्यात अयशस्वी.';

  @override
  String get successfullyConnectedWhoop => 'Whoop वर यशस्वीरित्या कनेक्ट केले!';

  @override
  String get failedToRefreshWhoopStatus => 'Whoop कनेक्शन स्थिती ताजी करण्यात अयशस्वी.';

  @override
  String get successfullyConnectedGitHub => 'GitHub वर यशस्वीरित्या कनेक्ट केले!';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub कनेक्शन स्थिती ताजी करण्यात अयशस्वी.';

  @override
  String get authFailedToSignInWithGoogle => 'Google सह साइन इन करण्यात अयशस्वी, कृपया पुन्हा प्रयत्न करा.';

  @override
  String get authenticationFailed => 'प्रमाणीकरण अयशस्वी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get authFailedToSignInWithApple => 'Apple सह साइन इन करण्यात अयशस्वी, कृपया पुन्हा प्रयत्न करा.';

  @override
  String get authFailedToRetrieveToken => 'firebase टोकन प्राप्त करण्यात अयशस्वी, कृपया पुन्हा प्रयत्न करा.';

  @override
  String get authUnexpectedErrorFirebase =>
      'साइन इन करताना अनपेक्षित त्रुटी, Firebase त्रुटी, कृपया पुन्हा प्रयत्न करा.';

  @override
  String get authUnexpectedError => 'साइन इन करताना अनपेक्षित त्रुटी, कृपया पुन्हा प्रयत्न करा';

  @override
  String get authFailedToLinkGoogle => 'Google सह लिंक करण्यात अयशस्वी, कृपया पुन्हा प्रयत्न करा.';

  @override
  String get authFailedToLinkApple => 'Apple सह लिंक करण्यात अयशस्वी, कृपया पुन्हा प्रयत्न करा.';

  @override
  String get onboardingBluetoothRequired => 'आपल्या डिव्हाइसला कनेक्ट करण्यासाठी ब्लूटूथ परवानगी आवश्यक आहे.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'ब्लूटूथ परवानगी नाकारली गेली. कृपया सिस्टम पसंदीमध्ये परवानगी द्या.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'ब्लूटूथ परवानगी स्थिती: $status. कृपया सिस्टम पसंदी तपासा.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'ब्लूटूथ परवानगी तपासण्यात अयशस्वी: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'सूचना परवानगी नाकारली गेली. कृपया सिस्टम पसंदीमध्ये परवानगी द्या.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'सूचना परवानगी नाकारली गेली. कृपया सिस्टम पसंदी > सूचना मध्ये परवानगी द्या.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'सूचना परवानगी स्थिती: $status. कृपया सिस्टम पसंदी तपासा.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'सूचना परवानगी तपासण्यात अयशस्वी: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'कृपया सेटिंग्ज > गोपनीयता आणि सुरक्षा > स्थान सेवा मध्ये स्थान परवानगी द्या';

  @override
  String get onboardingMicrophoneRequired => 'रेकॉर्डिंगसाठी मायक्रोफोन परवानगी आवश्यक आहे.';

  @override
  String get onboardingMicrophoneDenied =>
      'मायक्रोफोन परवानगी नाकारली गेली. कृपया सिस्टम पसंदी > गोपनीयता आणि सुरक्षा > मायक्रोफोन मध्ये परवानगी द्या.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'मायक्रोफोन परवानगी स्थिती: $status. कृपया सिस्टम पसंदी तपासा.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'मायक्रोफोन परवानगी तपासण्यात अयशस्वी: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'प्रणाली ऑडिओ रेकॉर्डिंगसाठी स्क्रीन कॅप्चर परवानगी आवश्यक आहे.';

  @override
  String get onboardingScreenCaptureDenied =>
      'स्क्रीन कॅप्चर परवानगी नाकारली गेली. कृपया सिस्टम पसंदी > गोपनीयता आणि सुरक्षा > स्क्रीन रेकॉर्डिंग मध्ये परवानगी द्या.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'स्क्रीन कॅप्चर परवानगी स्थिती: $status. कृपया सिस्टम पसंदी तपासा.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'स्क्रीन कॅप्चर परवानगी तपासण्यात अयशस्वी: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'ब्राउজर मीटिंग शोधण्यासाठी प्रवेशयोग्यता परवानगी आवश्यक आहे.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'प्रवेशयोग्यता परवानगी स्थिती: $status. कृपया सिस्टम पसंदी तपासा.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'प्रवेशयोग्यता परवानगी तपासण्यात अयशस्वी: $error';
  }

  @override
  String get msgCameraNotAvailable => 'कॅमेरा कॅप्चर या प्लॅटफॉर्मवर उपलब्ध नाही';

  @override
  String get msgCameraPermissionDenied => 'कॅमेरा परवानगी नाकारली गेली. कृपया कॅमेरामध्ये प्रवेश अनुमती द्या';

  @override
  String msgCameraAccessError(String error) {
    return 'कॅमेरामध्ये प्रवेश करण्यात त्रुटी: $error';
  }

  @override
  String get msgPhotoError => 'फोटो घेण्यात त्रुटी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get msgMaxImagesLimit => 'आप्पण केवळ 4 प्रतिमा निवडू शकता';

  @override
  String msgFilePickerError(String error) {
    return 'फाइल पिकर उघडण्यात त्रुटी: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'प्रतिमा निवडण्यात त्रुटी: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'फोटो परवानगी नाकारली गेली. प्रतिमा निवडण्यासाठी फोटोमध्ये प्रवेश अनुमती द्या';

  @override
  String get msgSelectImagesGenericError => 'प्रतिमा निवडण्यात त्रुटी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get msgMaxFilesLimit => 'आप्पण केवळ 4 फाइल निवडू शकता';

  @override
  String msgSelectFilesError(String error) {
    return 'फाइल निवडण्यात त्रुटी: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'फाइल निवडण्यात त्रुटी. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get msgUploadFileFailed => 'फाइल अपलोड करण्यात अयशस्वी, कृपया नंतर पुन्हा प्रयत्न करा';

  @override
  String get msgReadingMemories => 'आपल्या स्मृती वाचत आहे...';

  @override
  String get msgLearningMemories => 'आपल्या स्मृती पासून शिकत आहे...';

  @override
  String get msgUploadAttachedFileFailed => 'संलग्न फाइल अपलोड करण्यात अयशस्वी.';

  @override
  String captureRecordingError(String error) {
    return 'रेकॉर्डिंग दरम्यान त्रुटी आली: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'रेकॉर्डिंग बंद: $reason. आपल्याला बाह्य डिस्प्ले पुन्हा कनेक्ट करावे लागू शकते किंवा रेकॉर्डिंग पुन्हा सुरू करावे लागू शकते.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'मायक्रोफोन परवानगी आवश्यक';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'सिस्टम पसंदीमध्ये मायक्रोफोन परवानगी द्या';

  @override
  String get captureScreenRecordingPermissionRequired => 'स्क्रीन रेकॉर्डिंग परवानगी आवश्यक';

  @override
  String get captureDisplayDetectionFailed => 'डिस्प्ले शोध अयशस्वी. रेकॉर्डिंग बंद केली.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'अमान्य ऑडिओ बाइट्स webhook URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'अमान्य रीयल-टाइम ट्रान्सक्रिप्ट webhook URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'अमान्य संभाषण तयार webhook URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'अमान्य दिन सारांश webhook URL';

  @override
  String get devModeSettingsSaved => 'सेटिंग्ज जतन केल्या!';

  @override
  String get voiceFailedToTranscribe => 'ऑडिओ ट्रान्सक्राइब करण्यात अयशस्वी';

  @override
  String get locationPermissionRequired => 'स्थान परवानगी आवश्यक';

  @override
  String get locationPermissionContent =>
      'फास्ट ट्रांसफरला WiFi कनेक्शन सत्यापित करण्यासाठी स्थान परवानगी आवश्यक आहे. कृपया आगे जाण्यासाठी स्थान परवानगी द्या.';

  @override
  String get pdfTranscriptExport => 'ट्रान्सक्रिप्ट निर्यात';

  @override
  String get pdfConversationExport => 'संभाषण निर्यात';

  @override
  String pdfTitleLabel(String title) {
    return 'शीर्षक: $title';
  }

  @override
  String get conversationNewIndicator => 'नवीन 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count फोटो';
  }

  @override
  String get mergingStatus => 'विलीन करत आहे...';

  @override
  String timeSecsSingular(int count) {
    return '$count सेकंद';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count सेकंद';
  }

  @override
  String timeMinSingular(int count) {
    return '$count मिनिट';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count मिनिटे';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins मिनिटे $secs सेकंद';
  }

  @override
  String timeHourSingular(int count) {
    return '$count तास';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count तास';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours तास $mins मिनिटे';
  }

  @override
  String timeDaySingular(int count) {
    return '$count दिवस';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count दिवस';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days दिवस $hours तास';
  }

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}h';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}h ${mins}m';
  }

  @override
  String get moveToFolder => 'फोल्डरमध्ये हलवा';

  @override
  String get noFoldersAvailable => 'कोणतेही फोल्डर उपलब्ध नाही';

  @override
  String get newFolder => 'नवीन फोल्डर';

  @override
  String get color => 'रंग';

  @override
  String get waitingForDevice => 'डिव्हाइसची प्रतीक्षा करत आहे...';

  @override
  String get saySomething => 'काही सांगा...';

  @override
  String get initialisingSystemAudio => 'सिस्टम ऑडिओ प्रारंभ करत आहे';

  @override
  String get stopRecording => 'रेकॉर्डिंग बंद करा';

  @override
  String get continueRecording => 'रेकॉर्डिंग चालू ठेवा';

  @override
  String get initialisingRecorder => 'रेकॉर्डर प्रारंभ करत आहे';

  @override
  String get pauseRecording => 'रेकॉर्डिंग थांबवा';

  @override
  String get resumeRecording => 'रेकॉर्डिंग पुन्हा सुरू करा';

  @override
  String get noDailyRecapsYet => 'अद्याप कोणत्याही दैनिक रीकॅप नाही';

  @override
  String get dailyRecapsDescription => 'आपल्या दैनिक रीकॅप्स तयार झाल्या की येथे दिसतील';

  @override
  String get chooseTransferMethod => 'स्थानांतरण पद्धती निवडा';

  @override
  String get fastTransferSpeed => 'WiFi द्वारे ~150 KB/s';

  @override
  String largeTimeGapDetected(String gap) {
    return 'मोठा वेळ अंतर शोधला ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'मोठे वेळ अंतर शोधले ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'डिव्हाइस WiFi सिंक समर्थन करत नाही, ब्लूटूथ वर स्विच करत आहे';

  @override
  String get appleHealthNotAvailable => 'Apple Health या डिव्हाइसवर उपलब्ध नाही';

  @override
  String get downloadAudio => 'ऑडिओ डाउनलोड करा';

  @override
  String get audioDownloadSuccess => 'ऑडिओ यशस्वीरित्या डाउनलोड केली';

  @override
  String get audioDownloadFailed => 'ऑडिओ डाउनलोड करण्यात अयशस्वी';

  @override
  String get downloadingAudio => 'ऑडिओ डाउनलोड करत आहे...';

  @override
  String get shareAudio => 'ऑडिओ शेयर करा';

  @override
  String get preparingAudio => 'ऑडिओ तयार करत आहे';

  @override
  String get gettingAudioFiles => 'ऑडिओ फाइल मिळवत आहे...';

  @override
  String get downloadingAudioProgress => 'ऑडिओ डाउनलोड करत आहे';

  @override
  String get processingAudio => 'ऑडिओ प्रक्रिया करत आहे';

  @override
  String get combiningAudioFiles => 'ऑडिओ फाइल एकत्र करत आहे...';

  @override
  String get audioReady => 'ऑडिओ तयार';

  @override
  String get openingShareSheet => 'शेयर शीट उघडत आहे...';

  @override
  String get audioShareFailed => 'शेयर अयशस्वी';

  @override
  String get dailyRecaps => 'दैनिक रीकॅप्स';

  @override
  String get removeFilter => 'फिल्टर काढून टाका';

  @override
  String get categoryConversationAnalysis => 'संभाषण विश्लेषण';

  @override
  String get categoryHealth => 'स्वास्थ्य';

  @override
  String get categoryEducation => 'शिक्षा';

  @override
  String get categoryCommunication => 'संप्रेषण';

  @override
  String get categoryEmotionalSupport => 'भावनिक समर्थन';

  @override
  String get categoryProductivity => 'उत्पादकता';

  @override
  String get categoryEntertainment => 'मनोरंजन';

  @override
  String get categoryFinancial => 'आर्थिक';

  @override
  String get categoryTravel => 'ভ्रमण';

  @override
  String get categorySafety => 'सुरक्षा';

  @override
  String get categoryShopping => 'खरेदी';

  @override
  String get categorySocial => 'सामाजिक';

  @override
  String get categoryNews => 'बातमी';

  @override
  String get categoryUtilities => 'उपयोगिता';

  @override
  String get categoryOther => 'अन्य';

  @override
  String get capabilityChat => 'चॅट';

  @override
  String get capabilityConversations => 'संभाषण';

  @override
  String get capabilityExternalIntegration => 'बाह्य एकीकरण';

  @override
  String get capabilityNotification => 'सूचना';

  @override
  String get triggerAudioBytes => 'ऑडिओ बाइट्स';

  @override
  String get triggerConversationCreation => 'संभाषण निर्माण';

  @override
  String get triggerTranscriptProcessed => 'ट्रान्सक्रिप्ट प्रक्रिया';

  @override
  String get actionCreateConversations => 'संभाषण तयार करा';

  @override
  String get actionCreateMemories => 'स्मृती तयार करा';

  @override
  String get actionReadConversations => 'संभाषण वाचा';

  @override
  String get actionReadMemories => 'स्मृती वाचा';

  @override
  String get actionReadTasks => 'कार्य वाचा';

  @override
  String get scopeUserName => 'वापरकर्ता नाव';

  @override
  String get scopeUserFacts => 'वापरकर्ता तथ्य';

  @override
  String get scopeUserConversations => 'वापरकर्ता संभाषण';

  @override
  String get scopeUserChat => 'वापरकर्ता चॅट';

  @override
  String get capabilitySummary => 'सारांश';

  @override
  String get capabilityFeatured => 'वैशिष्ट्यीकृत';

  @override
  String get capabilityTasks => 'कार्य';

  @override
  String get capabilityIntegrations => 'एकीकरण';

  @override
  String get categoryProductivityLifestyle => 'उत्पादकता आणि जीवनशैली';

  @override
  String get categorySocialEntertainment => 'सामाजिक आणि मनोरंजन';

  @override
  String get categoryProductivityTools => 'उत्पादकता आणि साधने';

  @override
  String get categoryPersonalWellness => 'व्यक्तिगत आणि जीवनशैली';

  @override
  String get rating => 'रेटिंग';

  @override
  String get categories => 'श्रेणी';

  @override
  String get sortBy => 'क्रमवारी लावा';

  @override
  String get highestRating => 'सर्वोच्च रेटिंग';

  @override
  String get lowestRating => 'सर्वनिम्न रेटिंग';

  @override
  String get resetFilters => 'फिल्टर रीसेट करा';

  @override
  String get applyFilters => 'फिल्टर लागू करा';

  @override
  String get mostInstalls => 'सर्वाधिक इंस्टॉल';

  @override
  String get couldNotOpenUrl => 'URL उघडू शकत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get newTask => 'नवीन कार्य';

  @override
  String get viewAll => 'सर्व पाहा';

  @override
  String get addTask => 'कार्य जोडा';

  @override
  String get addMcpServer => 'MCP सर्व्हर जोडा';

  @override
  String get connectExternalAiTools => 'बाह्य AI साधने जोडा';

  @override
  String get mcpServerUrl => 'MCP सर्व्हर URL';

  @override
  String mcpServerConnected(int count) {
    return '$count साधने यशस्वीरित्या जोडली गेली';
  }

  @override
  String get mcpConnectionFailed => 'MCP सर्व्हरशी जोडणे अयशस्वी झाले';

  @override
  String get authorizingMcpServer => 'अधिकृत केत आहे...';

  @override
  String get whereDidYouHearAboutOmi => 'तू आमच्याकडे कसे आला?';

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
  String get friendWordOfMouth => 'मित्र';

  @override
  String get otherSource => 'इतर';

  @override
  String get pleaseSpecify => 'कृपया निर्दिष्ट करा';

  @override
  String get event => 'कार्यक्रम';

  @override
  String get coworker => 'सहकर्मी';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google शोध';

  @override
  String get audioPlaybackUnavailable => 'ऑडिओ फाइल प्लेबॅकसाठी उपलब्ध नाही';

  @override
  String get audioPlaybackFailed => 'ऑडिओ प्ले करू शकत नाही. फाइल खराब किंवा हरवली असू शकते.';

  @override
  String get connectionGuide => 'जोडणी मार्गदर्शक';

  @override
  String get iveDoneThis => 'मी हे केले आहे';

  @override
  String get pairNewDevice => 'नवीन डिव्हाइस जोडा';

  @override
  String get dontSeeYourDevice => 'तुमचे डिव्हाइस दिसत नाही?';

  @override
  String get reportAnIssue => 'समस्येची तक्रार करा';

  @override
  String get pairingTitleOmi => 'Omi चालू करा';

  @override
  String get pairingDescOmi => 'डिव्हाइस चालू करण्यासाठी बटणावर दबाव ठेवून धरा जोपर्यंत ते कंपन न करे.';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit पेयरिंग मोडमध्ये ठेवा';

  @override
  String get pairingDescOmiDevkit => 'पेयरिंग मोडमध्ये बटण एकदा दाबा. LED जांभळ्या रंगात लगदगदी करेल.';

  @override
  String get pairingTitleOmiGlass => 'Omi Glass चालू करा';

  @override
  String get pairingDescOmiGlass => 'बाजूचा बटण 3 सेकंडांसाठी दाबून शक्ती चालू करा.';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note पेयरिंग मोडमध्ये ठेवा';

  @override
  String get pairingDescPlaudNote =>
      'बाजूचा बटण 2 सेकंडांसाठी दाबा आणि धरा. लाल LED जोडणीसाठी तयार असताना लगदगदी करेल.';

  @override
  String get pairingTitleBee => 'Bee पेयरिंग मोडमध्ये ठेवा';

  @override
  String get pairingDescBee => 'बटण 5 वेळा सतत दाबा. प्रकाश निळा आणि हिरवा रंगात लगदगदी करू लागेल.';

  @override
  String get pairingTitleLimitless => 'Limitless पेयरिंग मोडमध्ये ठेवा';

  @override
  String get pairingDescLimitless =>
      'जेव्हा कोणताही प्रकाश दिसत असेल तेव्हा एकदा दाबा आणि नंतर गुलाबी प्रकाश दिसेपर्यंत दाबा आणि धरा, नंतर सोडा.';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant पेयरिंग मोडमध्ये ठेवा';

  @override
  String get pairingDescFriendPendant =>
      'लटकनीवरील बटण दाबा ते चालू करण्यासाठी. ते स्वयंचलितपणे पेयरिंग मोडमध्ये प्रवेश करेल.';

  @override
  String get pairingTitleFieldy => 'Fieldy पेयरिंग मोडमध्ये ठेवा';

  @override
  String get pairingDescFieldy => 'डिव्हाइस चालू करण्यासाठी बटणावर दबाव ठेवून धरा जोपर्यंत प्रकाश दिसत नाही.';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch जोडा';

  @override
  String get pairingDescAppleWatch => 'तुमच्या Apple Watch वर Omi अॅप इंस्टॉल आणि उघडा, नंतर अॅपमध्ये जोडण्या टॅप करा.';

  @override
  String get pairingTitleNeoOne => 'Neo One पेयरिंग मोडमध्ये ठेवा';

  @override
  String get pairingDescNeoOne => 'LED लगदगद होईपर्यंत पॉवर बटण दाबा आणि धरा. डिव्हाइस शोधायोग्य असेल.';

  @override
  String get downloadingFromDevice => 'डिव्हाइसमधून डाउनलोड करत आहे';

  @override
  String get reconnectingToInternet => 'इंटरनेटशी पुन्हा जोडत आहे...';

  @override
  String uploadingToCloud(int current, int total) {
    return '$total पैकी $current अपलोड करत आहे';
  }

  @override
  String get processingOnServer => 'सर्व्हरवर प्रक्रिया करत आहे...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'प्रक्रिया करत आहे... $current/$total सेगमेंट';
  }

  @override
  String get processedStatus => 'प्रक्रिया केली गेली';

  @override
  String get corruptedStatus => 'खराब';

  @override
  String nPending(int count) {
    return '$count प्रलंबित';
  }

  @override
  String nProcessed(int count) {
    return '$count प्रक्रिया केली गेली';
  }

  @override
  String get synced => 'सिंक केले गेले';

  @override
  String get noPendingRecordings => 'कोणतेही प्रलंबित रेकॉर्डिंग नाही';

  @override
  String get noProcessedRecordings => 'अद्याप कोणतेही प्रक्रिया केलेले रेकॉर्डिंग नाही';

  @override
  String get pending => 'प्रलंबित';

  @override
  String whatsNewInVersion(String version) {
    return '$version मध्ये काय नवीन आहे';
  }

  @override
  String get addToYourTaskList => 'तुमच्या कार्य सूचीमध्ये जोडा?';

  @override
  String get failedToCreateShareLink => 'शेअर लिंक तयार करणे अयशस्वी झाले';

  @override
  String get deleteGoal => 'लक्ष्य हटवा';

  @override
  String get deviceUpToDate => 'तुमचे डिव्हाइस अद्ययावत आहे';

  @override
  String get wifiConfiguration => 'WiFi कॉन्फिगरेशन';

  @override
  String get wifiConfigurationSubtitle => 'डिव्हाइसला फर्मवेअर डाउनलोड करण्यासाठी तुमचे WiFi क्रेडेंशियल एंटर करा.';

  @override
  String get networkNameSsid => 'नेटवर्क नाव (SSID)';

  @override
  String get enterWifiNetworkName => 'WiFi नेटवर्क नाव एंटर करा';

  @override
  String get enterWifiPassword => 'WiFi पासवर्ड एंटर करा';

  @override
  String get appIconLabel => 'अॅप आयकन';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'मला तुमच्याबद्दल काय माहिती आहे';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'हा नकाशा Omi तुमच्या संभाषणांमधून शिखरत असताना अपडेट होतो.';

  @override
  String get apiEnvironment => 'API वातावरण';

  @override
  String get apiEnvironmentDescription => 'कोणता बॅकएंड जोडायचा ते निवडा';

  @override
  String get production => 'उत्पादन';

  @override
  String get staging => 'स्टेजिंग';

  @override
  String get switchRequiresRestart => 'स्विच करण्यासाठी अॅप रीस्टार्ट आवश्यक आहे';

  @override
  String get switchApiConfirmTitle => 'API वातावरण स्विच करा';

  @override
  String switchApiConfirmBody(String environment) {
    return '$environment वर स्विच करा? बदल लागू करण्यासाठी तुम्हाला अॅप बंद आणि पुन्हा उघडावा लागेल.';
  }

  @override
  String get switchAndRestart => 'स्विच करा';

  @override
  String get stagingDisclaimer =>
      'स्टेजिंग बगी असू शकते, अयोग्य कार्यक्षमता असू शकते आणि डेटा हरवू शकते. फक्त चाचणीसाठी वापरा.';

  @override
  String get apiEnvSavedRestartRequired => 'सेव केले गेले. लागू करण्यासाठी अॅप बंद आणि पुन्हा उघडा.';

  @override
  String get shared => 'शेअर केले गेले';

  @override
  String get onlyYouCanSeeConversation => 'या संभाषणास फक्त तू पाहू शकतोस';

  @override
  String get anyoneWithLinkCanView => 'लिंक असलेला कोणी पाहू शकतो';

  @override
  String get tasksCleanTodayTitle => 'आजचे कार्य साफ करा?';

  @override
  String get tasksCleanTodayMessage => 'हे फक्त अंतिम तारखा काढून टाकेल';

  @override
  String get tasksOverdue => 'मुदत संपली';

  @override
  String get phoneCallsWithOmi => 'Omi सह फोन कॉल';

  @override
  String get phoneCallsSubtitle => 'वास्तविक-वेळ ट्रांसक्रिप्शन सह कॉल करा';

  @override
  String get phoneSetupStep1Title => 'तुमचा फोन नंबर सत्यापित करा';

  @override
  String get phoneSetupStep1Subtitle => 'हा तुमचा आहे हे सुनिश्चित करण्यासाठी आम्ही तुम्हाला कॉल करू';

  @override
  String get phoneSetupStep2Title => 'सत्यापन कोड एंटर करा';

  @override
  String get phoneSetupStep2Subtitle => 'कॉलवर टाइप करण्याचा एक लहान कोड';

  @override
  String get phoneSetupStep3Title => 'तुमच्या संपर्कांना कॉल करण्यास सुरुवात करा';

  @override
  String get phoneSetupStep3Subtitle => 'अंतर्निर्मित लाइव ट्रांसक्रिप्शन सह';

  @override
  String get phoneGetStarted => 'सुरुवात करा';

  @override
  String get callRecordingConsentDisclaimer => 'कॉल रेकॉर्डिंगसाठी तुमच्या अधिक्षेत्रात सहमती आवश्यक असू शकते';

  @override
  String get enterYourNumber => 'तुमचा नंबर एंटर करा';

  @override
  String get phoneNumberCallerIdHint => 'सत्यापित केल्यानंतर, हा तुमचा कॉलर ID बनतो';

  @override
  String get phoneNumberHint => 'फोन नंबर';

  @override
  String get failedToStartVerification => 'सत्यापन सुरू करणे अयशस्वी झाले';

  @override
  String get phoneContinue => 'सुरू ठेवा';

  @override
  String get verifyYourNumber => 'तुमचा नंबर सत्यापित करा';

  @override
  String get answerTheCallFrom => 'हुंडा कॉल सुनो';

  @override
  String get onTheCallEnterThisCode => 'कॉलवर हा कोड एंटर करा';

  @override
  String get followTheVoiceInstructions => 'व्हॉइस सूचनांचे अनुसरण करा';

  @override
  String get statusCalling => 'कॉल करत आहे...';

  @override
  String get statusCallInProgress => 'कॉल प्रगतीमध्ये आहे';

  @override
  String get statusVerifiedLabel => 'सत्यापित';

  @override
  String get statusCallMissed => 'कॉल हरवली गेली';

  @override
  String get statusTimedOut => 'वेळ संपली';

  @override
  String get phoneTryAgain => 'पुन्हा प्रयत्न करा';

  @override
  String get phonePageTitle => 'फोन';

  @override
  String get phoneContactsTab => 'संपर्क';

  @override
  String get phoneKeypadTab => 'की पॅड';

  @override
  String get grantContactsAccess => 'तुमच्या संपर्कांशी प्रवेश दा';

  @override
  String get phoneAllow => 'परवानगी द्या';

  @override
  String get phoneSearchHint => 'शोध';

  @override
  String get phoneNoContactsFound => 'कोणतेही संपर्क आढळले नाहीत';

  @override
  String get phoneEnterNumber => 'नंबर एंटर करा';

  @override
  String get failedToStartCall => 'कॉल सुरू करणे अयशस्वी झाले';

  @override
  String get callStateConnecting => 'जोडत आहे...';

  @override
  String get callStateRinging => 'बाजत आहे...';

  @override
  String get callStateEnded => 'कॉल संपली';

  @override
  String get callStateFailed => 'कॉल अयशस्वी झाली';

  @override
  String get transcriptPlaceholder => 'ट्रांसक्रिप्ट येथे दिसेल...';

  @override
  String get phoneUnmute => 'अनम्यूट करा';

  @override
  String get phoneMute => 'म्यूट करा';

  @override
  String get phoneSpeaker => 'स्पीकर';

  @override
  String get phoneEndCall => 'संपला';

  @override
  String get phoneCallSettingsTitle => 'फोन कॉल सेटिंग्ज';

  @override
  String get showPhoneCallButtonTitle => 'फोन कॉल बटण दाखवा';

  @override
  String get showPhoneCallButtonDesc => 'मुख्य स्क्रीनवर फोन कॉल बटण प्रदर्शित करा';

  @override
  String get yourVerifiedNumbers => 'तुमचे सत्यापित नंबर';

  @override
  String get verifiedNumbersDescription => 'तू कोणाला कॉल करतोस तेव्हा त्यांना त्यांच्या फोनवर हा नंबर दिसेल';

  @override
  String get noVerifiedNumbers => 'कोणतेही सत्यापित नंबर नाही';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber हटवा?';
  }

  @override
  String get deletePhoneNumberWarning => 'कॉल करण्यासाठी तुम्हाला पुन्हा सत्यापित करावे लागेल';

  @override
  String get phoneDeleteButton => 'हटवा';

  @override
  String verifiedMinutesAgo(int minutes) {
    return '$minutesमिनिट आधी सत्यापित';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return '$hoursतास आधी सत्यापित';
  }

  @override
  String verifiedDaysAgo(int days) {
    return '$daysदिवस आधी सत्यापित';
  }

  @override
  String verifiedOnDate(String date) {
    return '$date वर सत्यापित';
  }

  @override
  String get verifiedFallback => 'सत्यापित';

  @override
  String get callAlreadyInProgress => 'कॉल आधीच प्रगतीमध्ये आहे';

  @override
  String get failedToGetCallToken => 'कॉल टोकन मिळवणे अयशस्वी झाले. प्रथम तुमचा फोन नंबर सत्यापित करा.';

  @override
  String get failedToInitializeCallService => 'कॉल सेवा सुरू करणे अयशस्वी झाले';

  @override
  String get speakerLabelYou => 'तू';

  @override
  String get speakerLabelUnknown => 'अज्ञात';

  @override
  String get showDailyScoreOnHomepage => 'होमपेजवर दैनिक स्कोर दाखवा';

  @override
  String get showTasksOnHomepage => 'होमपेजवर कार्य दाखवा';

  @override
  String get phoneCallsUnlimitedOnly => 'Omi द्वारे फोन कॉल';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Omi द्वारे कॉल करा आणि वास्तविक-वेळ ट्रांसक्रिप्शन, स्वयंचलित सारांश आणि बरेच काही मिळवा. Unlimited योजना ग्राहकांसाठी विशेषरित्या उपलब्ध.';

  @override
  String get phoneCallsUpsellFeature1 => 'प्रत्येक कॉलचे वास्तविक-वेळ ट्रांसक्रिप्शन';

  @override
  String get phoneCallsUpsellFeature2 => 'स्वयंचलित कॉल सारांश आणि कार्य आयटम';

  @override
  String get phoneCallsUpsellFeature3 => 'प्राप्तकर्ता तुमचा वास्तविक नंबर पाहतो, यादृच्छिक नाही';

  @override
  String get phoneCallsUpsellFeature4 => 'तुमच्या कॉल खाजगी आणि सुरक्षित राहतात';

  @override
  String get phoneCallsUpgradeButton => 'Unlimited वर अपग्रेड करा';

  @override
  String get phoneCallsMaybeLater => 'कदाचित नंतर';

  @override
  String get deleteSynced => 'सिंक केलेले हटवा';

  @override
  String get deleteSyncedFiles => 'सिंक केलेली रेकॉर्डिंग हटवा';

  @override
  String get deleteSyncedFilesMessage =>
      'या रेकॉर्डिंग आधीच तुमच्या फोनशी सिंक केली गेली आहेत. हे पूर्ववत् केले जाऊ शकत नाही.';

  @override
  String get syncedFilesDeleted => 'सिंक केलेली रेकॉर्डिंग हटवली गेली';

  @override
  String get deletePending => 'प्रलंबित हटवा';

  @override
  String get deletePendingFiles => 'प्रलंबित रेकॉर्डिंग हटवा';

  @override
  String get deletePendingFilesWarning =>
      'या रेकॉर्डिंग तुमच्या फोनशी सिंक केल्या गेल्या नाहीत आणि कायमचे हरवली जातील. हे पूर्ववत् केले जाऊ शकत नाही.';

  @override
  String get pendingFilesDeleted => 'प्रलंबित रेकॉर्डिंग हटवली गेली';

  @override
  String get deleteAllFiles => 'सर्व रेकॉर्डिंग हटवा';

  @override
  String get deleteAll => 'सर्व हटवा';

  @override
  String get deleteAllFilesWarning =>
      'हे सिंक केलेली आणि प्रलंबित दोन्ही रेकॉर्डिंग हटवेल. प्रलंबित रेकॉर्डिंग सिंक केलेली नाहीत आणि कायमचे हरवली जातील. हे पूर्ववत् केले जाऊ शकत नाही.';

  @override
  String get allFilesDeleted => 'सर्व रेकॉर्डिंग हटवली गेली';

  @override
  String nFiles(int count) {
    return '$count रेकॉर्डिंग';
  }

  @override
  String get manageStorage => 'स्टोरेज व्यवस्थापित करा';

  @override
  String get safelyBackedUp => 'तुमच्या फोनमध्ये सुरक्षितपणे बॅकअप केले गेले';

  @override
  String get notYetSynced => 'अद्याप तुमच्या फोनशी सिंक केले नाही';

  @override
  String get clearAll => 'सर्व साफ करा';

  @override
  String get phoneKeypad => 'की पॅड';

  @override
  String get phoneHideKeypad => 'की पॅड लपवा';

  @override
  String get fairUsePolicy => 'न्याय्य वापर';

  @override
  String get fairUseLoadError => 'न्याय्य वापर स्थिति लोड करू शकत नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get fairUseStatusNormal => 'तुमचा वापर सामान्य मर्यादेत आहे.';

  @override
  String get fairUseStageNormal => 'सामान्य';

  @override
  String get fairUseStageWarning => 'चेतावणी';

  @override
  String get fairUseStageThrottle => 'थ्रॉटल केले गेले';

  @override
  String get fairUseStageRestrict => 'प्रतिबंधित';

  @override
  String get fairUseSpeechUsage => 'भाषण वापर';

  @override
  String get fairUseToday => 'आज';

  @override
  String get fairUse3Day => '3-दिवसीय रोलिंग';

  @override
  String get fairUseWeekly => 'साप्ताहिक रोलिंग';

  @override
  String get fairUseAboutTitle => 'न्याय्य वापराविषयी';

  @override
  String get fairUseAboutBody =>
      'Omi व्यक्तिगत संभाषण, बैठक आणि लाइव संवादसाठी डिজाइन केले गेले आहे. वापर वास्तविक भाषण वेळ द्वारे मोजला जातो, जोडणी वेळ नाही. जर वापर गैर-व्यक्तिगत सामग्रीसाठी सामान्य पॅटर्नचा बराच अधिक असेल तर समायोजन लागू होऊ शकते.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef कॉपी केले गेले';
  }

  @override
  String get fairUseDailyTranscription => 'दैनिक ट्रांसक्रिप्शन';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '$usedमि / $limitमि';
  }

  @override
  String get fairUseBudgetExhausted => 'दैनिक ट्रांसक्रिप्शन मर्यादा पूर्ण झाली';

  @override
  String fairUseBudgetResetsAt(String time) {
    return '$time वर रीसेट होतो';
  }

  @override
  String get transcriptionPaused => 'रेकॉर्डिंग, पुन्हा जोडत आहे';

  @override
  String get transcriptionPausedReconnecting => 'अद्याप रेकॉर्डिंग — ट्रांसक्रिप्शनशी पुन्हा जोडत आहे...';

  @override
  String fairUseBannerStatus(String status) {
    return 'न्याय्य वापर: $status';
  }

  @override
  String get improveConnectionTitle => 'जोडणी सुधारा';

  @override
  String get improveConnectionContent =>
      'आम्ही Omi तुमच्या डिव्हाइसशी जोडून ठेवण्याचे तरीके सुधारले आहे. हे सक्रिय करण्यासाठी, कृपया डिव्हाइस माहिती पृष्ठावर जा, \"डिव्हाइस डिस्कनेक्ट करा\" टॅप करा आणि नंतर तुमचे डिव्हाइस पुन्हा जोडा.';

  @override
  String get improveConnectionAction => 'समजले';

  @override
  String clockSkewWarning(int minutes) {
    return 'तुमचा डिव्हाइस घड्याळ ~$minutes मिनिट बंद आहे. तुमच्या तारीख व वेळ सेटिंग्ज तपासा.';
  }

  @override
  String get omisStorage => 'Omi चा स्टोरेज';

  @override
  String get phoneStorage => 'फोन स्टोरेज';

  @override
  String get cloudStorage => 'क्लाउड स्टोरेज';

  @override
  String get howSyncingWorks => 'सिंकिंग कसे काम करते';

  @override
  String get noSyncedRecordings => 'अद्याप कोणतेही सिंक केलेली रेकॉर्डिंग नाही';

  @override
  String get recordingsSyncAutomatically => 'रेकॉर्डिंग स्वयंचलितपणे सिंक होतात — कोणतीही कार्रवाई आवश्यक नाही.';

  @override
  String get filesDownloadedUploadedNextTime => 'आधीच डाउनलोड केलेल्या फाइल्स पुढच्या वेळी अपलोड केल्या जातील.';

  @override
  String nConversationsCreated(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 's',
      one: '',
    );
    return '$count संभाषण$_temp0 तयार केले गेले';
  }

  @override
  String get tapToView => 'पाहण्यासाठी टॅप करा';

  @override
  String get syncFailed => 'सिंक अयशस्वी झाली';

  @override
  String get keepSyncing => 'सिंक करत रहा';

  @override
  String get cancelSyncQuestion => 'सिंक रद्द करा?';

  @override
  String get omisStorageDesc =>
      'जेव्हा तुमचा Omi तुमच्या फोनशी जोडलेला नसतो तेव्हा ते त्याच्या अंतर्निर्मित स्मृतीमध्ये ऑडिओ स्थानिकपणे संचयित करतो. तू कधीही रेकॉर्डिंग हरावतोस नाही.';

  @override
  String get phoneStorageDesc =>
      'जेव्हा Omi पुन्हा जोडते तेव्हा, रेकॉर्डिंग स्वयंचलितपणे तुमच्या फोनमध्ये हस्तांतरित केली जातात. अपलोडिंगपूर्वी हे एक तात्पुरते धारण क्षेत्र असते.';

  @override
  String get cloudStorageDesc =>
      'अपलोड केल्यानंतर, तुमच्या रेकॉर्डिंग प्रक्रिया केली जातात आणि लिखित केली जातात. संभाषण एक मिनिटामध्ये उपलब्ध असतील.';

  @override
  String get tipKeepPhoneNearby => 'तेजस्वी सिंकिंगसाठी तुमचा फोन जवळ ठेवा';

  @override
  String get tipStableInternet => 'स्थिर इंटरनेट क्लाउड अपलोड गती वाढवतो';

  @override
  String get tipAutoSync => 'रेकॉर्डिंग स्वयंचलितपणे सिंक होतात';

  @override
  String get storageSection => 'स्टोरेज';

  @override
  String get permissions => 'परवानगी';

  @override
  String get permissionEnabled => 'सक्षम';

  @override
  String get permissionEnable => 'सक्षम करा';

  @override
  String get permissionsPageDescription =>
      'या परवानगी Omi कसे काम करते याचे मूल आहेत. ते सूचना, स्थान-आधारित अनुभव आणि ऑडिओ कॅप्चर सारख्या मुख्य वैशिष्ट्य सक्षम करतात.';

  @override
  String get permissionsRequiredDescription =>
      'Omi योग्यरित्या काम करण्यासाठी काही परवानगी आवश्यक आहे. कृपया सुरू ठेवण्यासाठी त्यांना दे.';

  @override
  String get permissionsSetupTitle => 'सर्वोत्तम अनुभव मिळवा';

  @override
  String get permissionsSetupDescription => 'Omi त्याचा जादू करू शकेल म्हणून काही परवानगी सक्षम करा.';

  @override
  String get permissionsChangeAnytime => 'तुम्ही सेटिंग्ज > परवानगी मध्ये कधीही हे बदलू शकता';

  @override
  String get location => 'स्थान';

  @override
  String get microphone => 'मायक्रोफोन';

  @override
  String get whyAreYouCanceling => 'तू किमतीकरण का रद्द करत आहेस?';

  @override
  String get cancelReasonSubtitle => 'तू का निघत आहेस हे सांगू शकतोस का?';

  @override
  String get cancelReasonTooExpensive => 'खूप महाग';

  @override
  String get cancelReasonNotUsing => 'पुरेसे वापरत नाही';

  @override
  String get cancelReasonMissingFeatures => 'हरवलेली वैशिष्ट्ये';

  @override
  String get cancelReasonAudioQuality => 'ऑडिओ/ट्रांसक्रिप्शन गुणवत्ता';

  @override
  String get cancelReasonBatteryDrain => 'बॅटरी अपचय चिंता';

  @override
  String get cancelReasonFoundAlternative => 'एक पर्याय सापडला';

  @override
  String get cancelReasonOther => 'इतर';

  @override
  String get tellUsMore => 'आमाला अधिक सांगा (वैकल्पिक)';

  @override
  String get cancelReasonDetailHint => 'आम्ही कोणतेही प्रतिक्रिया सराहतो...';

  @override
  String get justAMoment => 'एक क्षण, कृपया';

  @override
  String get cancelConsequencesSubtitle => 'आम्ही अत्यंत सुचवितो की रद्द करण्याऐवजी तुमचे इतर पर्याय शोधा.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'तुमची योजना $date पर्यंत सक्रिय राहिल. त्यानंतर, तुम्हाला मर्यादित वैशिष्ट्य असलेल्या मुक्त आवृत्तीमध्ये हलवले जाईल.';
  }

  @override
  String get ifYouCancel => 'जर तू रद्द करतोस:';

  @override
  String get cancelConsequenceNoAccess => 'तुमच्या बिलिंग कालावधीच्या शेवटी अधिक असीम प्रवेशाधिकार नाहीत.';

  @override
  String get cancelConsequenceBattery => '7 पट अधिक बॅटरी वापर (ऑन-डिव्हाइस प्रोसेसिंग)';

  @override
  String get cancelConsequenceQuality => '30% कमी ट्रांसक्रिप्शन गुणवत्ता (ऑन-डिव्हाइस मॉडेल)';

  @override
  String get cancelConsequenceDelay => '5-7 सेकंदांचा प्रोसेसिंग विलंब (ऑन-डिव्हाइस मॉडेल)';

  @override
  String get cancelConsequenceSpeakers => 'स्पीकर ओळखू शकत नाही.';

  @override
  String get confirmAndCancel => 'पुष्टी करा आणि रद्द करा';

  @override
  String get cancelConsequencePhoneCalls => 'वास्तविक-वेळ फोन कॉल ट्रांसक्रिप्शन नाही';

  @override
  String get feedbackTitleTooExpensive => 'तुमच्यासाठी कोणती किंमत कार्य करेल?';

  @override
  String get feedbackTitleMissingFeatures => 'तुम्ही कोणती वैशिष्ट्ये हरवत आहात?';

  @override
  String get feedbackTitleAudioQuality => 'तुम्हाला कोणत्या समस्या अनुभवल्या?';

  @override
  String get feedbackTitleBatteryDrain => 'बॅटरी समस्यांबद्दल सांगा';

  @override
  String get feedbackTitleFoundAlternative => 'तुम्ही काय वर स्विच करत आहात?';

  @override
  String get feedbackTitleNotUsing => 'काय Omi अधिक वापरण्यासाठी तुम्हाला प्रेरित करेल?';

  @override
  String get feedbackSubtitleTooExpensive => 'तुमची प्रतिक्रिया आमाला योग्य संतुलन शोधण्यास मदत करते.';

  @override
  String get feedbackSubtitleMissingFeatures => 'आम्ही नेहमी बांधत आहोत — हे आमाला प्राधान्य द्यास मदत करते.';

  @override
  String get feedbackSubtitleAudioQuality => 'हे काय चुकीचे गेले हे समजून घेऊ इच्छितो.';

  @override
  String get feedbackSubtitleBatteryDrain => 'हे आमच्या हार्डवेअर टीमला सुधारण्यास मदत करते.';

  @override
  String get feedbackSubtitleFoundAlternative => 'तुमचा दृष्टिकोन काय आकृष्ट करतो हे जाणून घेऊ इच्छितो.';

  @override
  String get feedbackSubtitleNotUsing => 'आम्ही Omi तुमच्यासाठी अधिक उपयुक्त बनवू इच्छितो.';

  @override
  String get deviceDiagnostics => 'डिव्हाइस निदान';

  @override
  String get signalStrength => 'सिग्नल शक्ती';

  @override
  String get connectionUptime => 'अपटाइम';

  @override
  String get reconnections => 'पुन्हा जोडणी';

  @override
  String get disconnectHistory => 'डिस्कनेक्ट इतिहास';

  @override
  String get noDisconnectsRecorded => 'कोणतेही डिस्कनेक्ट रेकॉर्ड केलेले नाहीत';

  @override
  String get diagnostics => 'निदान';

  @override
  String get waitingForData => 'डेटाची प्रतीक्षा करत आहे...';

  @override
  String get liveRssiOverTime => 'वेळेवर लाइव RSSI';

  @override
  String get noRssiDataYet => 'अद्याप कोणताही RSSI डेटा नाही';

  @override
  String get collectingData => 'डेटा संकलित करत आहे...';

  @override
  String get cleanDisconnect => 'स्वच्छ डिस्कनेक्ट';

  @override
  String get connectionTimeout => 'जोडणी वेळसीमा';

  @override
  String get remoteDeviceTerminated => 'रिमोट डिव्हाइस समाप्त केली गेली';

  @override
  String get pairedToAnotherPhone => 'दुसऱ्या फोनशी जोडलेले';

  @override
  String get linkKeyMismatch => 'लिंक की बेमेल';

  @override
  String get connectionFailed => 'जोडणी अयशस्वी झाली';

  @override
  String get appClosed => 'अॅप बंद केली गेली';

  @override
  String get manualDisconnect => 'मॅनुअल डिस्कनेक्ट';

  @override
  String lastNEvents(int count) {
    return 'शेवटचे $count इव्हेंट';
  }

  @override
  String get signal => 'सिग्नल';

  @override
  String get battery => 'बॅटरी';

  @override
  String get excellent => 'उत्कृष्ट';

  @override
  String get good => 'चांगली';

  @override
  String get fair => 'न्याय्य';

  @override
  String get weak => 'कमजोर';

  @override
  String gattError(String code) {
    return 'GATT त्रुटी ($code)';
  }

  @override
  String get batteryHistory => 'बॅटरी';

  @override
  String get noBatteryDataYet => 'अजून बॅटरी डेटा नाही';

  @override
  String get day => 'दिवस';

  @override
  String get week => 'आठवडा';

  @override
  String get rollbackToStableFirmware => 'स्थिर फर्मवेअर वर रोल बॅक करा';

  @override
  String get rollbackConfirmTitle => 'फर्मवेअर रोल बॅक करा?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'हे तुमचा सद्य फर्मवेअर सर्वशेष स्थिर आवृत्तीने ($version) बदलेल. अपडेट केल्यानंतर तुमचे डिव्हाइस पुन्हा सुरू होईल.';
  }

  @override
  String get stableFirmware => 'स्थिर फर्मवेअर';

  @override
  String get fetchingStableFirmware => 'सर्वशेष स्थिर फर्मवेअर मिळवत आहे...';

  @override
  String get noStableFirmwareFound => 'तुमच्या डिव्हाइससाठी स्थिर फर्मवेअर आवृत्ती सापडू शकत नाही.';

  @override
  String get installStableFirmware => 'स्थिर फर्मवेअर इंस्टॉल करा';

  @override
  String get alreadyOnStableFirmware => 'तुम्ही सर्वशेष स्थिर आवृत्तीवर आहात.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration ऑडिओ स्थानिकपणे सेव केली गेली';
  }

  @override
  String get willSyncAutomatically => 'स्वयंचलितपणे सिंक होईल';

  @override
  String get enableLocationTitle => 'स्थान सक्षम करा';

  @override
  String get enableLocationDescription => 'जवळपासून ब्लूटूथ डिव्हाइस शोधण्यासाठी स्थान परवानगी आवश्यक आहे.';

  @override
  String get voiceRecordingFound => 'रेकॉर्डिंग आढळली';

  @override
  String get transcriptionConnecting => 'ट्रांसक्रिप्शन जोडत आहे...';

  @override
  String get transcriptionReconnecting => 'ट्रांसक्रिप्शन पुन्हा जोडत आहे...';

  @override
  String get transcriptionUnavailable => 'ट्रांसक्रिप्शन उपलब्ध नाही';

  @override
  String get audioOutput => 'ऑडिओ आउटपुट';

  @override
  String get firmwareWarningTitle => 'महत्त्वाचे: अपडेट करण्यापूर्वी वाचा';

  @override
  String get firmwareFormatWarning =>
      'हे फर्मवेअर SD कार्ड फॉर्मेट करेल. कृपया अपग्रेड करण्यापूर्वी सर्व ऑफलाइन डेटा सिंक झाला आहे याची खात्री करा.\n\nहा आवृत्ती इंस्टॉल केल्यानंतर लाल दिवा चमकत असल्यास काळजी करू नका. फक्त डिव्हाइस अ‍ॅपशी कनेक्ट करा आणि ते निळे व्हायला हवे. लाल दिवा म्हणजे डिव्हाइसचे घड्याळ अजून सिंक झालेले नाही.';

  @override
  String get continueAnyway => 'पुढे सुरू ठेवा';

  @override
  String get tasksClearCompleted => 'पूर्ण झालेले साफ करा';

  @override
  String get tasksSelectAll => 'सर्व निवडा';

  @override
  String tasksDeleteSelected(int count) {
    return '$count कार्य हटवा';
  }

  @override
  String get tasksMarkComplete => 'पूर्ण म्हणून चिन्हांकित';

  @override
  String get appleHealthManageNote =>
      'Omi Apple च्या HealthKit फ्रेमवर्कद्वारे Apple Health ला प्रवेश करतो. आपण कोणत्याही वेळी iOS सेटिंग्जमधून प्रवेश रद्द करू शकता.';

  @override
  String get appleHealthConnectCta => 'Apple Health शी कनेक्ट करा';

  @override
  String get appleHealthDisconnectCta => 'Apple Health डिस्कनेक्ट करा';

  @override
  String get appleHealthConnectedBadge => 'कनेक्ट केले';

  @override
  String get appleHealthFeatureChatTitle => 'आपल्या आरोग्याबद्दल गप्पा मारा';

  @override
  String get appleHealthFeatureChatDesc => 'Omi ला आपल्या पावले, झोप, हृदय गती आणि वर्कआउट्सबद्दल विचारा.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'फक्त वाचन प्रवेश';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi कधीही Apple Health मध्ये लिहित नाही किंवा आपला डेटा बदलत नाही.';

  @override
  String get appleHealthFeatureSecureTitle => 'सुरक्षित सिंक';

  @override
  String get appleHealthFeatureSecureDesc => 'आपला Apple Health डेटा खासगीरित्या आपल्या Omi खात्याशी सिंक होतो.';

  @override
  String get appleHealthDeniedTitle => 'Apple Health प्रवेश नाकारला';

  @override
  String get appleHealthDeniedBody =>
      'Omi कडे आपला Apple Health डेटा वाचण्याची परवानगी नाही. iOS सेटिंग्ज → गोपनीयता आणि सुरक्षा → Health → Omi मध्ये ते सक्षम करा.';

  @override
  String get deleteFlowReasonTitle => 'तुम्ही का सोडत आहात?';

  @override
  String get deleteFlowReasonSubtitle => 'तुमचा अभिप्राय आम्हाला सर्वांसाठी Omi सुधारण्यात मदत करतो.';

  @override
  String get deleteReasonPrivacy => 'गोपनीयतेच्या चिंता';

  @override
  String get deleteReasonNotUsing => 'पुरेसा वापर करत नाही';

  @override
  String get deleteReasonMissingFeatures => 'मला आवश्यक असलेली वैशिष्ट्ये नाहीत';

  @override
  String get deleteReasonTechnicalIssues => 'खूप तांत्रिक समस्या';

  @override
  String get deleteReasonFoundAlternative => 'दुसरे काहीतरी वापरत आहे';

  @override
  String get deleteReasonTakingBreak => 'फक्त विश्रांती घेत आहे';

  @override
  String get deleteReasonOther => 'इतर';

  @override
  String get deleteFlowFeedbackTitle => 'आम्हाला अधिक सांगा';

  @override
  String get deleteFlowFeedbackSubtitle => 'Omi तुमच्यासाठी कसे उपयुक्त ठरले असते?';

  @override
  String get deleteFlowFeedbackHint => 'ऐच्छिक — तुमचे विचार आम्हाला एक चांगले उत्पादन बनवण्यात मदत करतात.';

  @override
  String get deleteFlowConfirmTitle => 'हे कायमचे आहे';

  @override
  String get deleteFlowConfirmSubtitle => 'एकदा खाते हटवले की ते पुनर्प्राप्त करण्याचा कोणताही मार्ग नाही.';

  @override
  String get deleteConsequenceSubscription => 'कोणतीही सक्रिय सदस्यता रद्द केली जाईल.';

  @override
  String get deleteConsequenceNoRecovery => 'तुमचे खाते पुनर्संचयित केले जाऊ शकत नाही — सपोर्टद्वारेही नाही.';

  @override
  String get deleteTypeToConfirm => 'पुष्टी करण्यासाठी DELETE टाइप करा';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'खाते कायमचे हटवा';

  @override
  String get keepMyAccount => 'माझे खाते ठेवा';

  @override
  String get deleteAccountFailed => 'तुमचे खाते हटवता आले नाही. कृपया पुन्हा प्रयत्न करा.';

  @override
  String get planUpdate => 'प्लॅन अपडेट';

  @override
  String get planDeprecationMessage =>
      'तुमचा Unlimited प्लॅन बंद केला जात आहे. Operator प्लॅनवर स्विच करा — तेच उत्कृष्ट वैशिष्ट्ये \$49/महिना. तुमचा सध्याचा प्लॅन तोपर्यंत काम करत राहील.';

  @override
  String get upgradeYourPlan => 'तुमचा प्लॅन अपग्रेड करा';

  @override
  String get youAreOnAPaidPlan => 'तुम्ही सशुल्क प्लॅनवर आहात.';

  @override
  String get chatTitle => 'चॅट';

  @override
  String get chatMessages => 'संदेश';

  @override
  String get unlimitedChatThisMonth => 'या महिन्यात अमर्यादित चॅट संदेश';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used / $limit गणना बजेट वापरले';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return 'या महिन्यात $used / $limit संदेश वापरले';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit वापरले';
  }

  @override
  String get chatLimitReachedUpgrade => 'चॅट मर्यादा गाठली. अधिक संदेशांसाठी अपग्रेड करा.';

  @override
  String get chatLimitReachedTitle => 'चॅट मर्यादा गाठली';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return '$plan प्लॅनवर $limitDisplay पैकी $used वापरले.';
  }

  @override
  String resetsInDays(int count) {
    return '$count दिवसांत रीसेट होईल';
  }

  @override
  String resetsInHours(int count) {
    return '$count तासांत रीसेट होईल';
  }

  @override
  String get resetsSoon => 'लवकरच रीसेट होईल';

  @override
  String get upgradePlan => 'प्लॅन अपग्रेड करा';

  @override
  String get billingMonthly => 'मासिक';

  @override
  String get billingYearly => 'वार्षिक';

  @override
  String get savePercent => '~17% बचत करा';

  @override
  String get popular => 'लोकप्रिय';

  @override
  String get currentPlan => 'सध्याचा';

  @override
  String neoSubtitle(int count) {
    return 'दरमहा $count प्रश्न';
  }

  @override
  String operatorSubtitle(int count) {
    return 'दरमहा $count प्रश्न';
  }

  @override
  String get architectSubtitle => 'पॉवर-यूजर AI — हजारो चॅट + एजेंटिक ऑटोमेशन';

  @override
  String chatUsageCost(String used, String limit) {
    return 'चॅट: \$$used / \$$limit या महिन्यात वापरले';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'चॅट: \$$used या महिन्यात वापरले';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'चॅट: $used / $limit संदेश या महिन्यात';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'चॅट: $used संदेश या महिन्यात';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'तुम्ही तुमची मासिक मर्यादा गाठली आहे. निर्बंधांशिवाय Omi सोबत चॅट सुरू ठेवण्यासाठी अपग्रेड करा.';

  @override
  String get voiceResponseAudio => 'Omi चे उत्तर मोठ्याने वाचा';

  @override
  String get voiceResponseMode => 'व्हॉइस प्रतिसाद';

  @override
  String get voiceResponseModeTitle => 'प्रतिसाद केव्हा बोलायचा';

  @override
  String get voiceResponseOff => 'बंद';

  @override
  String get voiceResponseHeadphonesOnly => 'फक्त हेडफोन';

  @override
  String get voiceResponseAlways => 'नेहमी';

  @override
  String get agreeAndContinue => 'सहमत व्हा आणि सुरू ठेवा';

  @override
  String get startVoiceRecording => 'व्हॉइस रेकॉर्डिंग सुरू करा';

  @override
  String get startCallRecording => 'कॉल रेकॉर्डिंग सुरू करा';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'व्हॉइस मोड';

  @override
  String get quickActionAskOmi => 'Omi ला काहीही विचारा';

  @override
  String get record => 'रेकॉर्ड';

  @override
  String get stop => 'थांबवा';

  @override
  String get recordWithPhoneMic => 'फोन माइकने रेकॉर्ड करा';

  @override
  String get recordWithPhoneMicSubtitle => 'तुमच्या आजूबाजूचा ऑडिओ कॅप्चर करा';

  @override
  String get phoneCall => 'फोन कॉल';

  @override
  String get phoneCallSubtitle => 'लाइव्ह ट्रान्स्क्रिप्शनसह कॉल रेकॉर्ड करा';

  @override
  String get searchActionItems => 'कृती आयटम शोधा';

  @override
  String get selectActionItems => 'अनेक निवडा';

  @override
  String chooseExportDestination(int count) {
    return '$count आयटम निर्यात करा…';
  }

  @override
  String get bulkExportInProgress => 'निर्यात होत आहे…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$count $platform वर निर्यात केले';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$total पैकी $success $platform वर निर्यात केले';
  }

  @override
  String get showCompletedTasks => 'पूर्ण झालेले दाखवा';

  @override
  String get hideCompletedTasks => 'पूर्ण झालेले लपवा';

  @override
  String get selectAllTasksMenu => 'सर्व निवडा';

  @override
  String get connectTaskAppToExport => 'निर्यात करण्यासाठी सेटिंग्जमध्ये टास्क ॲप जोडा';

  @override
  String get connectAction => 'जोडा';

  @override
  String get deselectAllTasksMenu => 'सर्वांची निवड रद्द करा';
}
