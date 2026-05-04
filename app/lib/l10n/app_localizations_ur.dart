// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Urdu (`ur`).
class AppLocalizationsUr extends AppLocalizations {
  AppLocalizationsUr([String locale = 'ur']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'بات چیت';

  @override
  String get transcriptTab => 'ٹرانسکرپٹ';

  @override
  String get actionItemsTab => 'کردہ کام';

  @override
  String get deleteConversationTitle => 'بات چیت حذف کریں؟';

  @override
  String get deleteConversationMessage =>
      'یہ منسلکہ یادیں، ٹاسک، اور آڈیو فائلیں بھی حذف کر دے گا۔ یہ عمل واپس نہیں کیا جا سکتا۔';

  @override
  String get confirm => 'تصدیق کریں';

  @override
  String get cancel => 'منسوخ کریں';

  @override
  String get ok => 'ٹھیک ہے';

  @override
  String get delete => 'حذف کریں';

  @override
  String get add => 'شامل کریں';

  @override
  String get update => 'اپڈیٹ کریں';

  @override
  String get save => 'محفوظ کریں';

  @override
  String get edit => 'ترمیم کریں';

  @override
  String get close => 'بند کریں';

  @override
  String get clear => 'صاف کریں';

  @override
  String get copyTranscript => 'ٹرانسکرپٹ کاپی کریں';

  @override
  String get copySummary => 'خلاصہ کاپی کریں';

  @override
  String get testPrompt => 'ٹیسٹ پروپٹ';

  @override
  String get reprocessConversation => 'بات چیت دوبارہ پروسیس کریں';

  @override
  String get deleteConversation => 'بات چیت حذف کریں';

  @override
  String get contentCopied => 'مواد کلپ بورڈ پر کاپی ہو گیا';

  @override
  String get failedToUpdateStarred => 'اسٹار شدہ حالت اپڈیٹ نہیں ہو سکی۔';

  @override
  String get conversationUrlNotShared => 'بات چیت کا URL شیئر نہیں کیا جا سکا۔';

  @override
  String get errorProcessingConversation => 'بات چیت کو پروسیس کرتے ہوئے خرابی۔ براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get noInternetConnection => 'انٹرنیٹ کنکشن نہیں';

  @override
  String get unableToDeleteConversation => 'بات چیت حذف نہیں کی جا سکی';

  @override
  String get somethingWentWrong => 'کچھ غلط ہو گیا! براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get copyErrorMessage => 'خرابی کا پیغام کاپی کریں';

  @override
  String get errorCopied => 'خرابی کا پیغام کلپ بورڈ پر کاپی ہو گیا';

  @override
  String get remaining => 'باقی';

  @override
  String get loading => 'لوڈ ہو رہا ہے...';

  @override
  String get loadingDuration => 'مدت لوڈ ہو رہی ہے...';

  @override
  String secondsCount(int count) {
    return '$count سیکنڈ';
  }

  @override
  String get people => 'لوگ';

  @override
  String get addNewPerson => 'نیا شخص شامل کریں';

  @override
  String get editPerson => 'شخص میں ترمیم کریں';

  @override
  String get createPersonHint => 'ایک نیا شخص بنائیں اور Omi کو ان کی بات کو سمجھنے کی تربیت دیں!';

  @override
  String get speechProfile => 'تقریری پروفائل';

  @override
  String sampleNumber(int number) {
    return 'نمونہ $number';
  }

  @override
  String get settings => 'ترتیبات';

  @override
  String get language => 'زبان';

  @override
  String get selectLanguage => 'زبان منتخب کریں';

  @override
  String get deleting => 'حذف ہو رہا ہے...';

  @override
  String get pleaseCompleteAuthentication =>
      'براہ کرم اپنے براؤزر میں تصدیق مکمل کریں۔ مکمل ہونے کے بعد، ایپ پر واپس جائیں۔';

  @override
  String get failedToStartAuthentication => 'تصدیق شروع نہیں ہو سکی';

  @override
  String get importStarted => 'درآمد شروع ہو گئی! مکمل ہونے پر آپ کو مطلع کیا جائے گا۔';

  @override
  String get failedToStartImport => 'درآمد شروع نہیں ہو سکی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get couldNotAccessFile => 'منتخب فائل تک رسائی نہیں ہو سکی';

  @override
  String get askOmi => 'Omi سے پوچھیں';

  @override
  String get done => 'مکمل';

  @override
  String get disconnected => 'منقطع';

  @override
  String get searching => 'تلاش ہو رہی ہے...';

  @override
  String get connectDevice => 'ڈیوائس سے جڑیں';

  @override
  String get monthlyLimitReached => 'آپ نے اپنی ماہانہ حد پوری کر دی۔';

  @override
  String get checkUsage => 'استعمال دیکھیں';

  @override
  String get syncingRecordings => 'ریکارڈنگز ہم وقت میں لائے جا رہے ہیں';

  @override
  String get recordingsToSync => 'ہم وقت میں لانے کے لیے ریکارڈنگز';

  @override
  String get allCaughtUp => 'سب کچھ اپڈیٹ ہے';

  @override
  String get sync => 'ہم وقت';

  @override
  String get pendantUpToDate => 'پینڈنٹ تازہ ترین ہے';

  @override
  String get allRecordingsSynced => 'تمام ریکارڈنگز ہم وقت میں ہیں';

  @override
  String get syncingInProgress => 'ہم وقت میں لانا جاری ہے';

  @override
  String get readyToSync => 'ہم وقت میں لانے کے لیے تیار';

  @override
  String get tapSyncToStart => 'شروع کرنے کے لیے ہم وقت تھپتھپائیں';

  @override
  String get pendantNotConnected => 'پینڈنٹ متصل نہیں۔ ہم وقت کے لیے جڑیں۔';

  @override
  String get everythingSynced => 'سب کچھ پہلے سے ہم وقت میں ہے۔';

  @override
  String get recordingsNotSynced => 'آپ کے پاس ریکارڈنگز ہیں جو ابھی ہم وقت میں نہیں ہیں۔';

  @override
  String get syncingBackground => 'ہم آپ کی ریکارڈنگز کو پس منظر میں ہم وقت میں لاتے رہیں گے۔';

  @override
  String get noConversationsYet => 'ابھی کوئی بات چیت نہیں';

  @override
  String get noStarredConversations => 'کوئی اسٹار شدہ بات چیت نہیں';

  @override
  String get starConversationHint => 'بات چیت کو اسٹار کرنے کے لیے، اسے کھولیں اور ہیڈر میں ستارے کی علامت تھپتھپائیں۔';

  @override
  String get searchConversations => 'بات چیتوں کو تلاش کریں...';

  @override
  String selectedCount(int count, Object s) {
    return '$count منتخب';
  }

  @override
  String get merge => 'ملائیں';

  @override
  String get mergeConversations => 'بات چیتیں ملائیں';

  @override
  String mergeConversationsMessage(int count) {
    return 'یہ $count بات چیتوں کو ایک میں ملاتا ہے۔ تمام مواد ملایا اور دوبارہ تیار کیا جائے گا۔';
  }

  @override
  String get mergingInBackground => 'پس منظر میں ملایا جا رہا ہے۔ اس میں کچھ لمحے لگ سکتے ہیں۔';

  @override
  String get failedToStartMerge => 'ملانا شروع نہیں ہو سکا';

  @override
  String get askAnything => 'کچھ بھی پوچھیں';

  @override
  String get noMessagesYet => 'ابھی کوئی پیغام نہیں!\nکیا آپ بات چیت شروع نہیں کریں گے?';

  @override
  String get deletingMessages => 'اپنے پیغامات کو Omi کی یادوں سے حذف کیا جا رہا ہے...';

  @override
  String get messageCopied => '✨ پیغام کلپ بورڈ پر کاپی ہو گیا';

  @override
  String get cannotReportOwnMessage => 'آپ اپنے پیغامات کی اطلاع نہیں دے سکتے۔';

  @override
  String get reportMessage => 'پیغام کی اطلاع دیں';

  @override
  String get reportMessageConfirm => 'کیا آپ واقعی اس پیغام کی اطلاع دینا چاہتے ہیں؟';

  @override
  String get messageReported => 'پیغام کی کامیابی سے اطلاع دی گئی۔';

  @override
  String get thankYouFeedback => 'آپ کے فیڈبیک کے لیے شکریہ!';

  @override
  String get clearChat => 'بات چیت صاف کریں';

  @override
  String get clearChatConfirm => 'کیا آپ واقعی بات چیت صاف کرنا چاہتے ہیں؟ یہ عمل واپس نہیں کیا جا سکتا۔';

  @override
  String get maxFilesLimit => 'آپ ایک وقت میں صرف 4 فائلیں اپ لوڈ کر سکتے ہیں';

  @override
  String get chatWithOmi => 'Omi کے ساتھ بات چیت کریں';

  @override
  String get apps => 'ایپلیکیشنز';

  @override
  String get noAppsFound => 'کوئی ایپلیکیشن نہیں ملی';

  @override
  String get tryAdjustingSearch => 'اپنی تلاش یا فلٹرز میں ترمیم کرنے کی کوشش کریں';

  @override
  String get createYourOwnApp => 'اپنی خود کی ایپلیکیشن بنائیں';

  @override
  String get buildAndShareApp => 'اپنی حسب ضرورت ایپلیکیشن بنائیں اور شیئر کریں';

  @override
  String get searchApps => 'ایپلیکیشنز تلاش کریں...';

  @override
  String get myApps => 'میری ایپلیکیشنز';

  @override
  String get installedApps => 'انسٹال شدہ ایپلیکیشنز';

  @override
  String get unableToFetchApps => 'ایپلیکیشنز حاصل نہیں کر سکے :(\n\nاپنا انٹرنیٹ کنکشن چیک کریں اور دوبارہ کوشش کریں۔';

  @override
  String get aboutOmi => 'Omi کے بارے میں';

  @override
  String get privacyPolicy => 'رازداری کی پالیسی';

  @override
  String get visitWebsite => 'ویب سائٹ دیکھیں';

  @override
  String get helpOrInquiries => 'مدد یا سوالات؟';

  @override
  String get joinCommunity => 'کمیونٹی میں شامل ہوں!';

  @override
  String get membersAndCounting => '8000+ اراکین اور بڑھ رہے ہیں۔';

  @override
  String get deleteAccountTitle => 'اکاؤنٹ حذف کریں';

  @override
  String get deleteAccountConfirm => 'کیا آپ واقعی اپنا اکاؤنٹ حذف کرنا چاہتے ہیں؟';

  @override
  String get cannotBeUndone => 'یہ واپس نہیں کیا جا سکتا۔';

  @override
  String get allDataErased => 'آپ کی تمام یادیں اور بات چیتیں مستقل طور پر حذف ہو جائیں گی۔';

  @override
  String get appsDisconnected => 'آپ کی ایپلیکیشنز اور انضمام فوری طور پر منقطع ہو جائیں گے۔';

  @override
  String get exportBeforeDelete =>
      'آپ اپنا اکاؤنٹ حذف کرنے سے پہلے اپنا ڈیٹا ایکسپورٹ کر سکتے ہیں، لیکن ایک بار حذف ہونے کے بعد، اسے بحال نہیں کیا جا سکتا۔';

  @override
  String get deleteAccountCheckbox =>
      'میں سمجھتا ہوں کہ میرے اکاؤنٹ کو حذف کرنا مستقل ہے اور تمام ڈیٹا، بشمول یادیں اور بات چیتیں، کھو جائیں گے اور بحال نہیں ہو سکیں گے۔';

  @override
  String get areYouSure => 'کیا آپ یقین ہیں؟';

  @override
  String get deleteAccountFinal =>
      'یہ عمل ناقابل واپسی ہے اور آپ کے اکاؤنٹ اور تمام منسلکہ ڈیٹا کو مستقل طور پر حذف کر دے گا۔ کیا آپ آگے بڑھنا چاہتے ہیں؟';

  @override
  String get deleteNow => 'اب حذف کریں';

  @override
  String get goBack => 'واپس جائیں';

  @override
  String get checkBoxToConfirm =>
      'تصدیق کے لیے باکس چیک کریں کہ آپ سمجھتے ہیں کہ اپنے اکاؤنٹ کو حذف کرنا مستقل اور ناقابل واپسی ہے۔';

  @override
  String get profile => 'پروفائل';

  @override
  String get name => 'نام';

  @override
  String get email => 'ای میل';

  @override
  String get customVocabulary => 'حسب ضرورت الفاظ';

  @override
  String get identifyingOthers => 'دوسروں کی شناخت';

  @override
  String get paymentMethods => 'ادائیگی کے طریقے';

  @override
  String get conversationDisplay => 'بات چیت کی نمائش';

  @override
  String get dataPrivacy => 'ڈیٹا کی رازداری';

  @override
  String get userId => 'صارف کی نشانی';

  @override
  String get notSet => 'مقرر نہیں';

  @override
  String get userIdCopied => 'صارف کی نشانی کلپ بورڈ پر کاپی ہو گئی';

  @override
  String get systemDefault => 'نظام کا ڈیفالٹ';

  @override
  String get planAndUsage => 'منصوبہ اور استعمال';

  @override
  String get offlineSync => 'آفلائن ہم وقت';

  @override
  String get deviceSettings => 'ڈیوائس کی ترتیبات';

  @override
  String get integrations => 'انضمام';

  @override
  String get feedbackBug => 'فیڈبیک / بگ';

  @override
  String get helpCenter => 'مدد کا مرکز';

  @override
  String get developerSettings => 'ڈیولپر ترتیبات';

  @override
  String get getOmiForMac => 'Mac کے لیے Omi حاصل کریں';

  @override
  String get referralProgram => 'حوالہ دینے والے پروگرام';

  @override
  String get signOut => 'سائن آؤٹ کریں';

  @override
  String get appAndDeviceCopied => 'ایپلیکیشن اور ڈیوائس کی تفصیلات کاپی ہو گئیں';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'آپ کی رازداری، آپ کا کنٹرول';

  @override
  String get privacyIntro =>
      'Omi میں، ہم آپ کی رازداری کی حفاظت کے لیے پرتوشامل ہیں۔ یہ صفحہ آپ کو اپنے ڈیٹا کو کیسے محفوظ اور استعمال کیا جاتا ہے اس پر کنٹرول کرنے کی اجازت دیتا ہے۔';

  @override
  String get learnMore => 'مزید جانیں...';

  @override
  String get dataProtectionLevel => 'ڈیٹا تحفظ کی سطح';

  @override
  String get dataProtectionDesc =>
      'آپ کا ڈیٹا مضبوط انکوڈنگ کے ساتھ ڈیفالٹ طور پر محفوظ ہے۔ اپنی ترتیبات اور نیچے کی مستقبل کی رازداری کے اختیارات کا جائزہ لیں۔';

  @override
  String get appAccess => 'ایپلیکیشن تک رسائی';

  @override
  String get appAccessDesc =>
      'درج ذیل ایپلیکیشنز آپ کے ڈیٹا تک رسائی کر سکتی ہیں۔ اس کے اذن کو سنبھالنے کے لیے کسی ایپلیکیشن پر تھپتھپائیں۔';

  @override
  String get noAppsExternalAccess => 'کوئی بھی انسٹال شدہ ایپلیکیشن آپ کے ڈیٹا تک بیرونی رسائی نہیں رکھتی۔';

  @override
  String get deviceName => 'ڈیوائس کا نام';

  @override
  String get deviceId => 'ڈیوائس کی نشانی';

  @override
  String get firmware => 'فرم ویئر';

  @override
  String get sdCardSync => 'SD کارڈ ہم وقت';

  @override
  String get hardwareRevision => 'ہارڈ ویئر کی تبدیلی';

  @override
  String get modelNumber => 'ماڈل نمبر';

  @override
  String get manufacturer => 'تیاری کنندہ';

  @override
  String get doubleTap => 'دوگنا تھپتھپائیں';

  @override
  String get ledBrightness => 'LED روشنی';

  @override
  String get micGain => 'مائک کا حصول';

  @override
  String get disconnect => 'منقطع کریں';

  @override
  String get forgetDevice => 'ڈیوائس بھول جائیں';

  @override
  String get chargingIssues => 'چارج کرنے میں مسائل';

  @override
  String get disconnectDevice => 'ڈیوائس منقطع کریں';

  @override
  String get unpairDevice => 'ڈیوائس سے جوڑی کو ہٹائیں';

  @override
  String get unpairAndForget => 'ڈیوائس سے جوڑی کو ہٹائیں اور بھول جائیں';

  @override
  String get deviceDisconnectedMessage => 'آپ کا Omi منقطع ہو گیا ہے 😔';

  @override
  String get deviceUnpairedMessage =>
      'ڈیوائس سے جوڑی ہٹائی گئی۔ ترتیبات > Bluetooth پر جائیں اور جوڑی ہٹانا مکمل کرنے کے لیے ڈیوائس بھول جائیں۔';

  @override
  String get unpairDialogTitle => 'ڈیوائس سے جوڑی ہٹائیں';

  @override
  String get unpairDialogMessage =>
      'یہ ڈیوائس کو جوڑی سے ہٹا دے گا تاکہ اسے دوسرے فون سے جڑا جا سکے۔ آپ کو ترتیبات > Bluetooth پر جانا ہوگا اور عمل کو مکمل کرنے کے لیے ڈیوائس بھول جانا ہوگا۔';

  @override
  String get deviceNotConnected => 'ڈیوائس متصل نہیں';

  @override
  String get connectDeviceMessage =>
      'اپنے Omi ڈیوائس کو جڑیں\nڈیوائس کی ترتیبات اور حسب ضرورت تک رسائی حاصل کرنے کے لیے';

  @override
  String get deviceInfoSection => 'ڈیوائس کی معلومات';

  @override
  String get customizationSection => 'حسب ضرورت';

  @override
  String get hardwareSection => 'ہارڈ ویئر';

  @override
  String get v2Undetected => 'V2 شناخت نہیں';

  @override
  String get v2UndetectedMessage =>
      'ہمیں لگتا ہے کہ آپ کے پاس ایک V1 ڈیوائس ہے یا آپ کا ڈیوائس متصل نہیں ہے۔ SD کارڈ کی فعالیت صرف V2 ڈیوائسز کے لیے دستیاب ہے۔';

  @override
  String get endConversation => 'بات چیت ختم کریں';

  @override
  String get pauseResume => 'موقوف/دوبارہ شروع کریں';

  @override
  String get starConversation => 'بات چیت کو اسٹار کریں';

  @override
  String get doubleTapAction => 'دوگنا تھپتھپانے کا عمل';

  @override
  String get endAndProcess => 'بات چیت ختم اور پروسیس کریں';

  @override
  String get pauseResumeRecording => 'ریکارڈنگ موقوف/دوبارہ شروع کریں';

  @override
  String get starOngoing => 'جاری بات چیت کو اسٹار کریں';

  @override
  String get off => 'بند';

  @override
  String get max => 'زیادہ سے زیادہ';

  @override
  String get mute => 'خاموشی کریں';

  @override
  String get quiet => 'خاموش';

  @override
  String get normal => 'عام';

  @override
  String get high => 'اونچا';

  @override
  String get micGainDescMuted => 'مائک خاموش ہے';

  @override
  String get micGainDescLow => 'بہت خاموش - اونچے ماحول کے لیے';

  @override
  String get micGainDescModerate => 'خاموش - اعتدال پسند شور کے لیے';

  @override
  String get micGainDescNeutral => 'غیر جانبدار - متوازن ریکارڈنگ';

  @override
  String get micGainDescSlightlyBoosted => 'تھوڑا بہتر - معمولی استعمال';

  @override
  String get micGainDescBoosted => 'بہتر - خاموش ماحول کے لیے';

  @override
  String get micGainDescHigh => 'اونچا - دور یا نرم آوازوں کے لیے';

  @override
  String get micGainDescVeryHigh => 'بہت اونچا - بہت خاموش ذرائع کے لیے';

  @override
  String get micGainDescMax => 'زیادہ سے زیادہ - احتیاط کے ساتھ استعمال کریں';

  @override
  String get developerSettingsTitle => 'ڈیولپر ترتیبات';

  @override
  String get saving => 'محفوظ ہو رہا ہے...';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'تحریری شکل میں تبدیلی';

  @override
  String get transcriptionConfig => 'STT فراہم کنندہ ترتیب دیں';

  @override
  String get conversationTimeout => 'بات چیت کا وقت ختم ہونا';

  @override
  String get conversationTimeoutConfig => 'یہ مقرر کریں کہ بات چیتیں کب خود بند ہوں';

  @override
  String get importData => 'ڈیٹا درآمد کریں';

  @override
  String get importDataConfig => 'دوسری جگہوں سے ڈیٹا درآمد کریں';

  @override
  String get debugDiagnostics => 'ڈیبگ اور تشخیص';

  @override
  String get endpointUrl => 'اختتام نقطہ URL';

  @override
  String get noApiKeys => 'ابھی کوئی API کلیدیں نہیں';

  @override
  String get createKeyToStart => 'شروع کرنے کے لیے کلید بنائیں';

  @override
  String get createKey => 'کلید بنائیں';

  @override
  String get docs => 'دستاویزات';

  @override
  String get yourOmiInsights => 'آپ کے Omi اندرونی خیالات';

  @override
  String get today => 'آج';

  @override
  String get thisMonth => 'اس ماہ';

  @override
  String get thisYear => 'اس سال';

  @override
  String get allTime => 'ہر وقت';

  @override
  String get noActivityYet => 'ابھی کوئی سرگرمی نہیں';

  @override
  String get startConversationToSeeInsights =>
      'Omi کے ساتھ بات چیت شروع کریں\nاپنے استعمال کے اندرونی خیالات یہاں دیکھنے کے لیے۔';

  @override
  String get listening => 'سن رہا ہے';

  @override
  String get listeningSubtitle => 'کل وقت Omi نے فعال طور پر سنا۔';

  @override
  String get understanding => 'سمجھنا';

  @override
  String get understandingSubtitle => 'آپ کی بات چیتوں سے سمجھے گئے الفاظ۔';

  @override
  String get providing => 'فراہم کرنا';

  @override
  String get providingSubtitle => 'کردہ کام، اور خود بخود حاصل نوٹس۔';

  @override
  String get remembering => 'یاد رکھنا';

  @override
  String get rememberingSubtitle => 'حقائق اور تفصیلات آپ کے لیے یاد رکھی گئیں۔';

  @override
  String get unlimitedPlan => 'غیر محدود منصوبہ';

  @override
  String get managePlan => 'منصوبہ منیج کریں';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'آپ کا منصوبہ $date پر منسوخ ہو جائے گا۔';
  }

  @override
  String renewsOn(String date) {
    return 'آپ کا منصوبہ $date پر تجدید ہو گا۔';
  }

  @override
  String get basicPlan => 'مفت منصوبہ';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used کے $limit منٹ استعمال کیے گئے';
  }

  @override
  String get upgrade => 'اپ گریڈ کریں';

  @override
  String get upgradeToUnlimited => 'غیر محدود میں اپ گریڈ کریں';

  @override
  String basicPlanDesc(int limit) {
    return 'آپ کے منصوبے میں $limit مفت منٹ فی ماہ شامل ہیں۔ غیر محدود جانے کے لیے اپ گریڈ کریں۔';
  }

  @override
  String get shareStatsMessage => 'اپنے Omi کے اعدادوشمار شیئر کر رہے ہیں! (omi.me - آپ کا ہمیشہ چالو AI معاون)';

  @override
  String get sharePeriodToday => 'آج، omi نے:';

  @override
  String get sharePeriodMonth => 'اس ماہ، omi نے:';

  @override
  String get sharePeriodYear => 'اس سال، omi نے:';

  @override
  String get sharePeriodAllTime => 'ابھی تک، omi نے:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes منٹ سنے';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words الفاظ سمجھے';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count اندرونی خیالات فراہم کیے';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count یادیں یادوں میں رکھیں';
  }

  @override
  String get debugLogs => 'ڈیبگ لاگز';

  @override
  String get debugLogsAutoDelete => '3 دن کے بعد خود بخود حذف ہو جاتے ہیں۔';

  @override
  String get debugLogsDesc => 'مسائل کی تشخیص میں مدد کرتا ہے';

  @override
  String get noLogFilesFound => 'کوئی لاگ فائلیں نہیں ملیں۔';

  @override
  String get omiDebugLog => 'Omi ڈیبگ لاگ';

  @override
  String get logShared => 'لاگ شیئر کیا گیا';

  @override
  String get selectLogFile => 'لاگ فائل منتخب کریں';

  @override
  String get shareLogs => 'لاگز شیئر کریں';

  @override
  String get debugLogCleared => 'ڈیبگ لاگ صاف ہو گیا';

  @override
  String get exportStarted => 'برآمد شروع ہو گیا۔ یہ کچھ سیکنڈ لگ سکتے ہیں...';

  @override
  String get exportAllData => 'تمام ڈیٹا برآمد کریں';

  @override
  String get exportDataDesc => 'بات چیتوں کو JSON فائل میں برآمد کریں';

  @override
  String get exportedConversations => 'Omi سے برآمد شدہ بات چیتیں';

  @override
  String get exportShared => 'برآمد شیئر کیا گیا';

  @override
  String get deleteKnowledgeGraphTitle => 'علم کے گراف کو حذف کریں؟';

  @override
  String get deleteKnowledgeGraphMessage =>
      'یہ تمام اخذ شدہ علم کے گراف کا ڈیٹا (نوڈز اور تعلقات) حذف کر دے گا۔ آپ کی اصل یادیں محفوظ رہیں گی۔ گراف وقت کے ساتھ یا اگلی درخواست پر دوبارہ تیار ہو گا۔';

  @override
  String get knowledgeGraphDeleted => 'علم کا گراف حذف ہو گیا';

  @override
  String deleteGraphFailed(String error) {
    return 'گراف حذف کرنے میں ناکام: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'علم کے گراف کو حذف کریں';

  @override
  String get deleteKnowledgeGraphDesc => 'تمام نوڈز اور تعلقات صاف کریں';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP سرور';

  @override
  String get mcpServerDesc => 'AI معاونین کو اپنے ڈیٹا سے جوڑیں';

  @override
  String get serverUrl => 'سرور URL';

  @override
  String get urlCopied => 'URL کاپی ہو گیا';

  @override
  String get apiKeyAuth => 'API کلید کی تصدیق';

  @override
  String get header => 'ہیڈر';

  @override
  String get authorizationBearer => 'اختیار: بیئر <کلید>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'کلائنٹ ID';

  @override
  String get clientSecret => 'کلائنٹ خفیہ';

  @override
  String get useMcpApiKey => 'اپنی MCP API کلید استعمال کریں';

  @override
  String get webhooks => 'ویب ہکس';

  @override
  String get conversationEvents => 'بات چیت کے واقعات';

  @override
  String get newConversationCreated => 'نئی بات چیت بنائی گئی';

  @override
  String get realtimeTranscript => 'حقیقی وقتی ٹرانسکرپٹ';

  @override
  String get transcriptReceived => 'ٹرانسکرپٹ موصول ہوا';

  @override
  String get audioBytes => 'آڈیو بائٹس';

  @override
  String get audioDataReceived => 'آڈیو ڈیٹا موصول ہوا';

  @override
  String get intervalSeconds => 'وقفہ (سیکنڈ)';

  @override
  String get daySummary => 'روزانہ خلاصہ';

  @override
  String get summaryGenerated => 'خلاصہ تیار کیا گیا';

  @override
  String get claudeDesktop => 'Claude ڈیسک ٹاپ';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.json میں شامل کریں';

  @override
  String get copyConfig => 'ترتیب کاپی کریں';

  @override
  String get configCopied => 'ترتیب کلپ بورڈ پر کاپی ہو گئی';

  @override
  String get listeningMins => 'سن رہا ہے (منٹ)';

  @override
  String get understandingWords => 'سمجھنا (الفاظ)';

  @override
  String get insights => 'اندرونی خیالات';

  @override
  String get memories => 'یادیں';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'اس ماہ $used کے $limit منٹ استعمال کیے گئے';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'اس ماہ $used کے $limit الفاظ استعمال کیے گئے';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'اس ماہ $used کے $limit اندرونی خیالات حاصل کیے گئے';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'اس ماہ $used کے $limit یادیں بنائی گئیں';
  }

  @override
  String get visibility => 'نمائش';

  @override
  String get visibilitySubtitle => 'کنٹرول کریں کہ کون سی بات چیتیں آپ کی فہرست میں نظر آتی ہیں';

  @override
  String get showShortConversations => 'مختصر بات چیتیں دکھائیں';

  @override
  String get showShortConversationsDesc => 'حد سے کم بات چیتیں دکھائیں';

  @override
  String get showDiscardedConversations => 'مسترد شدہ بات چیتیں دکھائیں';

  @override
  String get showDiscardedConversationsDesc => 'مسترد شدہ نشان زد بات چیتیں شامل کریں';

  @override
  String get shortConversationThreshold => 'مختصر بات چیت کی حد';

  @override
  String get shortConversationThresholdSubtitle => 'اس سے کم بات چیتیں پوشیدہ ہوں گی جب تک اوپر فعال نہ ہو';

  @override
  String get durationThreshold => 'مدت کی حد';

  @override
  String get durationThresholdDesc => 'اس سے کم بات چیتیں چھپائیں';

  @override
  String minLabel(int count) {
    return '$count منٹ';
  }

  @override
  String get customVocabularyTitle => 'حسب ضرورت الفاظ';

  @override
  String get addWords => 'الفاظ شامل کریں';

  @override
  String get addWordsDesc => 'نام، شرائط، یا غیر معمولی الفاظ';

  @override
  String get vocabularyHint => 'Omi، کالی، OpenAI';

  @override
  String get connect => 'جڑیں';

  @override
  String get comingSoon => 'جلد آنے والا';

  @override
  String get integrationsFooter => 'اپنی ایپلیکیشنز کو جوڑیں تاکہ بات چیت میں ڈیٹا اور میٹرکس دیکھیں۔';

  @override
  String get completeAuthInBrowser => 'براہ کرم اپنے براؤزر میں تصدیق مکمل کریں۔ مکمل ہونے کے بعد، ایپ پر واپس جائیں۔';

  @override
  String failedToStartAuth(String appName) {
    return '$appName تصدیق شروع نہیں ہو سکی';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName سے منقطع کریں؟';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'کیا آپ واقعی $appName سے منقطع کرنا چاہتے ہیں؟ آپ کسی بھی وقت دوبارہ جڑ سکتے ہیں۔';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName سے منقطع ہو گیا';
  }

  @override
  String get failedToDisconnect => 'منقطع کرنے میں ناکام';

  @override
  String connectTo(String appName) {
    return '$appName سے جڑیں';
  }

  @override
  String authAccessMessage(String appName) {
    return 'آپ کو Omi کو اپنے $appName ڈیٹا تک رسائی حاصل کرنے کی اجازت دینی ہوگی۔ یہ تصدیق کے لیے آپ کے براؤزر کو کھولے گا۔';
  }

  @override
  String get continueAction => 'جاری رکھیں';

  @override
  String get languageTitle => 'زبان';

  @override
  String get primaryLanguage => 'بنیادی زبان';

  @override
  String get automaticTranslation => 'خودکار ترجمہ';

  @override
  String get detectLanguages => '10+ زبانوں کو شناخت کریں';

  @override
  String get authorizeSavingRecordings => 'ریکارڈنگز محفوظ کرنے کی اجازت دیں';

  @override
  String get thanksForAuthorizing => 'اجازت دینے کے لیے شکریہ!';

  @override
  String get needYourPermission => 'ہمیں آپ کی اجازت کی ضرورت ہے';

  @override
  String get alreadyGavePermission =>
      'آپ نے پہلے سے ہمیں اپنی ریکارڈنگز محفوظ کرنے کی اجازت دی ہے۔ یہاں یاد دہانی ہے کہ ہمیں یہ کیوں چاہیے:';

  @override
  String get wouldLikePermission => 'ہم آپ کی آواز کی ریکارڈنگز محفوظ کرنے کی اجازت چاہتے ہیں۔ یہاں وجہ ہے:';

  @override
  String get improveSpeechProfile => 'اپنی تقریری پروفائل بہتر بنائیں';

  @override
  String get improveSpeechProfileDesc =>
      'ہم ریکارڈنگز استعمال کرتے ہوئے اپنی ذاتی تقریری پروفائل کو مزید تربیت اور بہتری دیتے ہیں۔';

  @override
  String get trainFamilyProfiles => 'دوستوں اور خاندان کے لیے پروفائلز تربیت دیں';

  @override
  String get trainFamilyProfilesDesc =>
      'آپ کی ریکارڈنگز ہمیں اپنے دوستوں اور خاندان کو سمجھنے اور پروفائلز بنانے میں مدد کرتے ہیں۔';

  @override
  String get enhanceTranscriptAccuracy => 'ٹرانسکرپٹ کی درستگی میں اضافہ کریں';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'جیسے جیسے ہماری ماڈل بہتر ہوتی ہے، ہم آپ کی ریکارڈنگز کے لیے بہتر تحریری شکل میں تبدیلی کی نتائج فراہم کر سکتے ہیں۔';

  @override
  String get legalNotice =>
      'قانونی نوٹس: آڈیو ڈیٹا ریکارڈ اور محفوظ کرنے کی قانونی حیثیت آپ کے مقام اور اس خصوصیت کو کس طریقے سے استعمال کرتے ہیں اس پر منحصر ہو سکتی ہے۔ یہ آپ کی ذمہ داری ہے کہ مقامی قوانین اور ضوابط کی تعریف کو یقینی بنائیں۔';

  @override
  String get alreadyAuthorized => 'پہلے سے اجازت دی گئی';

  @override
  String get authorize => 'اجازت دیں';

  @override
  String get revokeAuthorization => 'اجازت منسوخ کریں';

  @override
  String get authorizationSuccessful => 'اجازت کامیاب رہی!';

  @override
  String get failedToAuthorize => 'اختیار دینا ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get authorizationRevoked => 'اختیار منسوخ کر دیا گیا۔';

  @override
  String get recordingsDeleted => 'ریکارڈنگز حذف کر دی گئی ہیں۔';

  @override
  String get failedToRevoke => 'اختیار منسوخ کرنا ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get permissionRevokedTitle => 'اختیار منسوخ کر دیا گیا';

  @override
  String get permissionRevokedMessage => 'کیا آپ چاہتے ہیں کہ ہم آپ کی تمام موجودہ ریکارڈنگز بھی ہٹا دیں؟';

  @override
  String get yes => 'جی ہاں';

  @override
  String get editName => 'نام میں ترمیم کریں';

  @override
  String get howShouldOmiCallYou => 'Omi آپ کو کیا کہہ کر پکارے؟';

  @override
  String get enterYourName => 'اپنا نام درج کریں';

  @override
  String get nameCannotBeEmpty => 'نام خالی نہیں ہو سکتا';

  @override
  String get nameUpdatedSuccessfully => 'نام کامیابی سے اپ ڈیٹ ہو گیا!';

  @override
  String get calendarSettings => 'کیلنڈر کی ترتیبات';

  @override
  String get calendarProviders => 'کیلنڈر فراہم کنندگان';

  @override
  String get macOsCalendar => 'macOS کیلنڈر';

  @override
  String get connectMacOsCalendar => 'اپنے مقامی macOS کیلنڈر سے جڑیں';

  @override
  String get googleCalendar => 'Google کیلنڈر';

  @override
  String get syncGoogleAccount => 'اپنے Google اکاؤنٹ کے ساتھ ہم آہنگ کریں';

  @override
  String get showMeetingsMenuBar => 'مینو بار میں آنے والی میٹنگز دکھائیں';

  @override
  String get showMeetingsMenuBarDesc => 'macOS مینو بار میں اپنی اگلی میٹنگ اور اس کے شروع ہونے تک کا وقت دکھائیں';

  @override
  String get showEventsNoParticipants => 'بغیر شرکاء کے ایونٹس دکھائیں';

  @override
  String get showEventsNoParticipantsDesc =>
      'جب فعال ہو تو Coming Up شرکاء کے بغیر یا ویڈیو لنک کے بغیر ایونٹس دکھاتا ہے۔';

  @override
  String get yourMeetings => 'آپ کی میٹنگز';

  @override
  String get refresh => 'تازہ کریں';

  @override
  String get noUpcomingMeetings => 'کوئی آنے والی میٹنگز نہیں';

  @override
  String get checkingNextDays => 'اگلے 30 دن چیک کیے جا رہے ہیں';

  @override
  String get tomorrow => 'کل';

  @override
  String get googleCalendarComingSoon => 'Google کیلنڈر انضمام جلد آ رہا ہے!';

  @override
  String connectedAsUser(String userId) {
    return 'صارف کے طور پر جڑا ہوا ہے: $userId';
  }

  @override
  String get defaultWorkspace => 'ڈیفالٹ ورک اسپیس';

  @override
  String get tasksCreatedInWorkspace => 'کام اس ورک اسپیس میں بنائے جائیں گے';

  @override
  String get defaultProjectOptional => 'ڈیفالٹ منصوبہ (اختیاری)';

  @override
  String get leaveUnselectedTasks => 'کام کو بغیر منصوبے کے بنانے کے لیے منتخب نہ کریں';

  @override
  String get noProjectsInWorkspace => 'اس ورک اسپیس میں کوئی منصوبے نہیں ملے';

  @override
  String get conversationTimeoutDesc => 'خاموشی میں کتنی دیر انتظار کریں اس سے پہلے خودکار طور پر بات چیت ختم کریں:';

  @override
  String get timeout2Minutes => '2 منٹ';

  @override
  String get timeout2MinutesDesc => '2 منٹ کی خاموشی کے بعد بات چیت ختم کریں';

  @override
  String get timeout5Minutes => '5 منٹ';

  @override
  String get timeout5MinutesDesc => '5 منٹ کی خاموشی کے بعد بات چیت ختم کریں';

  @override
  String get timeout10Minutes => '10 منٹ';

  @override
  String get timeout10MinutesDesc => '10 منٹ کی خاموشی کے بعد بات چیت ختم کریں';

  @override
  String get timeout30Minutes => '30 منٹ';

  @override
  String get timeout30MinutesDesc => '30 منٹ کی خاموشی کے بعد بات چیت ختم کریں';

  @override
  String get timeout4Hours => '4 گھنٹے';

  @override
  String get timeout4HoursDesc => '4 گھنٹے کی خاموشی کے بعد بات چیت ختم کریں';

  @override
  String get conversationEndAfterHours => 'بات چیت اب 4 گھنٹے کی خاموشی کے بعد ختم ہوگی';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'بات چیت اب $minutes منٹ کی خاموشی کے بعد ختم ہوگی';
  }

  @override
  String get tellUsPrimaryLanguage => 'ہمیں اپنی بنیادی زبان بتائیں';

  @override
  String get languageForTranscription => 'تیز تر ٹرانسکرپشن اور ذاتی نوعیت کے تجربے کے لیے اپنی زبان مقرر کریں۔';

  @override
  String get singleLanguageModeInfo => 'سنگل لینگویج موڈ فعال ہے۔ اعلیٰ درستگی کے لیے ترجمہ غیر فعال ہے۔';

  @override
  String get searchLanguageHint => 'نام یا کوڈ کے لحاظ سے زبان تلاش کریں';

  @override
  String get noLanguagesFound => 'کوئی زبان نہیں ملی';

  @override
  String get skip => 'چھوڑ دیں';

  @override
  String languageSetTo(String language) {
    return 'زبان $language پر مقرر کی گئی';
  }

  @override
  String get failedToSetLanguage => 'زبان مقرر کرنا ناکام';

  @override
  String appSettings(String appName) {
    return '$appName ترتیبات';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName سے منقطع کریں؟';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'یہ آپ کی $appName تصدیق کو ہٹا دے گا۔ اسے دوبارہ استعمال کرنے کے لیے آپ کو دوبارہ جڑنا ہوگا۔';
  }

  @override
  String connectedToApp(String appName) {
    return '$appName سے جڑا ہوا';
  }

  @override
  String get account => 'اکاؤنٹ';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'آپ کے کام آپ کے $appName اکاؤنٹ میں ہم آہنگ ہوں گے';
  }

  @override
  String get defaultSpace => 'ڈیفالٹ اسپیس';

  @override
  String get selectSpaceInWorkspace => 'اپنے ورک اسپیس میں ایک اسپیس منتخب کریں';

  @override
  String get noSpacesInWorkspace => 'اس ورک اسپیس میں کوئی اسپیسز نہیں ملے';

  @override
  String get defaultList => 'ڈیفالٹ فہرست';

  @override
  String get tasksAddedToList => 'کام اس فہرست میں شامل کیے جائیں گے';

  @override
  String get noListsInSpace => 'اس اسپیس میں کوئی فہرستیں نہیں ملیں';

  @override
  String failedToLoadRepos(String error) {
    return 'ذخائر لوڈ کرنا ناکام: $error';
  }

  @override
  String get defaultRepoSaved => 'ڈیفالٹ ذخیرہ محفوظ ہو گیا';

  @override
  String get failedToSaveDefaultRepo => 'ڈیفالٹ ذخیرہ محفوظ کرنا ناکام';

  @override
  String get defaultRepository => 'ڈیفالٹ ذخیرہ';

  @override
  String get selectDefaultRepoDesc =>
      'مسائل بنانے کے لیے ایک ڈیفالٹ ذخیرہ منتخب کریں۔ آپ مسائل بناتے وقت ایک مختلف ذخیرہ بھی متعین کر سکتے ہیں۔';

  @override
  String get noReposFound => 'کوئی ذخائر نہیں ملے';

  @override
  String get private => 'نجی';

  @override
  String updatedDate(String date) {
    return '$date کو اپ ڈیٹ کیا';
  }

  @override
  String get yesterday => 'کل';

  @override
  String daysAgo(int count) {
    return '$count دن پہلے';
  }

  @override
  String get oneWeekAgo => '1 ہفتہ پہلے';

  @override
  String weeksAgo(int count) {
    return '$count ہفتے پہلے';
  }

  @override
  String get oneMonthAgo => '1 ماہ پہلے';

  @override
  String monthsAgo(int count) {
    return '$count مہینے پہلے';
  }

  @override
  String get issuesCreatedInRepo => 'مسائل آپ کے ڈیفالٹ ذخیرے میں بنائے جائیں گے';

  @override
  String get taskIntegrations => 'کام انضمام';

  @override
  String get configureSettings => 'ترتیبات ترتیب دیں';

  @override
  String get completeAuthBrowser => 'براہ کرم اپنے براؤزر میں تصدیق مکمل کریں۔ ہو جانے کے بعد ایپ پر واپس آئیں۔';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName تصدیق شروع کرنا ناکام';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appName سے جڑیں';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'آپ کو Omi کو اپنے $appName اکاؤنٹ میں کام بنانے کا اختیار دینا ہوگا۔ یہ تصدیق کے لیے آپ کے براؤزر کو کھولے گا۔';
  }

  @override
  String get continueButton => 'جاری رکھیں';

  @override
  String appIntegration(String appName) {
    return '$appName انضمام';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName کے ساتھ انضمام جلد آ رہا ہے! ہم آپ کو مزید کام کی تدبیری آپشنز دینے کے لیے سخت محنت کر رہے ہیں۔';
  }

  @override
  String get gotIt => 'سمجھ گئے';

  @override
  String get tasksExportedOneApp => 'کام ایک وقت میں ایک ایپ میں برآمد کیے جا سکتے ہیں۔';

  @override
  String get completeYourUpgrade => 'اپنی ترقی مکمل کریں';

  @override
  String get importConfiguration => 'ترتیب درآمد کریں';

  @override
  String get exportConfiguration => 'ترتیب برآمد کریں';

  @override
  String get bringYourOwn => 'اپنا لے کر آئیں';

  @override
  String get payYourSttProvider => 'Omi کو آزادانہ استعمال کریں۔ آپ صرف اپنے STT فراہم کنندہ کو براہ راست ادا کریں۔';

  @override
  String get freeMinutesMonth => 'ہر ماہ 1,200 منٹ مفت شامل ہیں۔ آن لائن کریں ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'میزبان درکار ہے';

  @override
  String get validPortRequired => 'درست پورٹ درکار ہے';

  @override
  String get validWebsocketUrlRequired => 'درست WebSocket URL درکار ہے (wss://)';

  @override
  String get apiUrlRequired => 'API URL درکار ہے';

  @override
  String get apiKeyRequired => 'API کلید درکار ہے';

  @override
  String get invalidJsonConfig => 'غلط JSON ترتیب';

  @override
  String errorSaving(String error) {
    return 'محفوظ کرتے وقت خرابی: $error';
  }

  @override
  String get configCopiedToClipboard => 'ترتیب کلپ بورڈ میں نقل کی گئی';

  @override
  String get pasteJsonConfig => 'اپنی JSON ترتیب یہاں پیسٹ کریں:';

  @override
  String get addApiKeyAfterImport => 'درآمد کے بعد آپ کو اپنی API کلید شامل کرنی ہوگی';

  @override
  String get paste => 'پیسٹ کریں';

  @override
  String get import => 'درآمد کریں';

  @override
  String get invalidProviderInConfig => 'ترتیب میں غلط فراہم کنندہ';

  @override
  String importedConfig(String providerName) {
    return '$providerName ترتیب درآمد کی گئی';
  }

  @override
  String invalidJson(String error) {
    return 'غلط JSON: $error';
  }

  @override
  String get provider => 'فراہم کنندہ';

  @override
  String get live => 'براہ راست';

  @override
  String get onDevice => 'آلے پر';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'اپنا STT HTTP اختتام پوائنٹ درج کریں';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'اپنا براہ راست STT WebSocket اختتام پوائنٹ درج کریں';

  @override
  String get apiKey => 'API کلید';

  @override
  String get enterApiKey => 'اپنی API کلید درج کریں';

  @override
  String get storedLocallyNeverShared => 'مقامی طور پر محفوظ، کبھی شیئر نہیں';

  @override
  String get host => 'میزبان';

  @override
  String get port => 'پورٹ';

  @override
  String get advanced => 'اعلیٰ';

  @override
  String get configuration => 'ترتیب';

  @override
  String get requestConfiguration => 'درخواست ترتیب';

  @override
  String get responseSchema => 'جواب سکیما';

  @override
  String get modified => 'ترمیم شدہ';

  @override
  String get resetRequestConfig => 'درخواست ترتیب کو ڈیفالٹ میں ری سیٹ کریں';

  @override
  String get logs => 'لاگز';

  @override
  String get logsCopied => 'لاگز نقل کیے گئے';

  @override
  String get noLogsYet => 'ابھی کوئی لاگز نہیں۔ حسب ضرورت STT سرگرمی دیکھنے کے لیے ریکارڈنگ شروع کریں۔';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device $reason استعمال کرتا ہے۔ Omi استعمال کیا جائے گا۔';
  }

  @override
  String get omiTranscription => 'Omi ٹرانسکرپشن';

  @override
  String get bestInClassTranscription => 'صفر سیٹ اپ کے ساتھ بہترین درجے کی ٹرانسکرپشن';

  @override
  String get instantSpeakerLabels => 'فوری سپیکر لیبلز';

  @override
  String get languageTranslation => '100+ زبانوں میں ترجمہ';

  @override
  String get optimizedForConversation => 'بات چیت کے لیے بہتر بنایا گیا';

  @override
  String get autoLanguageDetection => 'خودکار زبان کی شناخت';

  @override
  String get highAccuracy => 'اعلیٰ درستگی';

  @override
  String get privacyFirst => 'رازداری پہلے';

  @override
  String get saveChanges => 'تبدیلیوں کو محفوظ کریں';

  @override
  String get resetToDefault => 'ڈیفالٹ میں ری سیٹ کریں';

  @override
  String get viewTemplate => 'ٹیمپلیٹ دیکھیں';

  @override
  String get trySomethingLike => 'کچھ اس طرح کریں...';

  @override
  String get tryIt => 'کوشش کریں';

  @override
  String get creatingPlan => 'منصوبہ بنایا جا رہا ہے';

  @override
  String get developingLogic => 'منطق تیار کی جا رہی ہے';

  @override
  String get designingApp => 'ایپ ڈیزائن کیا جا رہا ہے';

  @override
  String get generatingIconStep => 'آئیکن تیار کیا جا رہا ہے';

  @override
  String get finalTouches => 'حتمی نکات';

  @override
  String get processing => 'کارکردگی میں...';

  @override
  String get features => 'خصوصیات';

  @override
  String get creatingYourApp => 'آپ کی ایپ بن رہی ہے...';

  @override
  String get generatingIcon => 'آئیکن تیار ہو رہا ہے...';

  @override
  String get whatShouldWeMake => 'ہمیں کیا بنانا چاہیے؟';

  @override
  String get appName => 'ایپ کا نام';

  @override
  String get description => 'تفصیل';

  @override
  String get publicLabel => 'عوامی';

  @override
  String get privateLabel => 'نجی';

  @override
  String get free => 'مفت';

  @override
  String get perMonth => '/ ماہ';

  @override
  String get tailoredConversationSummaries => 'حسب ضرورت بات چیت کے خلاصے';

  @override
  String get customChatbotPersonality => 'حسب ضرورت چیٹ بوٹ شخصیت';

  @override
  String get makePublic => 'عوامی بنائیں';

  @override
  String get anyoneCanDiscover => 'کوئی بھی آپ کی ایپ تلاش کر سکتا ہے';

  @override
  String get onlyYouCanUse => 'صرف آپ اس ایپ کو استعمال کر سکتے ہیں';

  @override
  String get paidApp => 'ادا شدہ ایپ';

  @override
  String get usersPayToUse => 'صارفین آپ کی ایپ استعمال کرنے کے لیے ادا کریں';

  @override
  String get freeForEveryone => 'سب کے لیے مفت';

  @override
  String get perMonthLabel => '/ ماہ';

  @override
  String get creating => 'بنایا جا رہا ہے...';

  @override
  String get createApp => 'ایپ بنائیں';

  @override
  String get searchingForDevices => 'آلے تلاش کیے جا رہے ہیں...';

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
  String get pairingSuccessful => 'پیئرنگ کامیاب';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch سے جڑنے میں خرابی: $error';
  }

  @override
  String get dontShowAgain => 'دوبارہ نہ دکھائیں';

  @override
  String get iUnderstand => 'میں سمجھتا ہوں';

  @override
  String get enableBluetooth => 'Bluetooth فعال کریں';

  @override
  String get bluetoothNeeded =>
      'Omi کو اپنے قابل پہننے کے آلے سے جڑنے کے لیے Bluetooth کی ضرورت ہے۔ براہ کرم Bluetooth فعال کریں اور دوبارہ کوشش کریں۔';

  @override
  String get contactSupport => 'معاونت سے رابطہ کریں؟';

  @override
  String get connectLater => 'بعد میں جڑیں';

  @override
  String get grantPermissions => 'اختیارات دیں';

  @override
  String get backgroundActivity => 'پس منظر کی سرگرمی';

  @override
  String get backgroundActivityDesc => 'Omi کو بہتر استحکام کے لیے پس منظر میں چلنے دیں';

  @override
  String get locationAccess => 'مقام رسائی';

  @override
  String get locationAccessDesc => 'مکمل تجربے کے لیے پس منظر مقام فعال کریں';

  @override
  String get notifications => 'اطلاعات';

  @override
  String get notificationsDesc => 'باخبر رہنے کے لیے اطلاعات فعال کریں';

  @override
  String get locationServiceDisabled => 'مقام کی خدمت غیر فعال ہے';

  @override
  String get locationServiceDisabledDesc =>
      'مقام کی خدمت غیر فعال ہے۔ براہ کرم Settings > Privacy & Security > Location Services میں جائیں اور اسے فعال کریں';

  @override
  String get backgroundLocationDenied => 'پس منظر مقام رسائی مسترد کی گئی';

  @override
  String get backgroundLocationDeniedDesc =>
      'براہ کرم آلے کی ترتیبات میں جائیں اور مقام کی اجازت کو \"ہمیشہ اجازت دیں\" میں سیٹ کریں';

  @override
  String get lovingOmi => 'Omi سے محبت ہے؟';

  @override
  String get leaveReviewIos =>
      'ہمیں مزید لوگوں تک پہنچنے میں مدد کریں App Store میں ریویو چھوڑ کر۔ آپ کی رائے ہمارے لیے بہت اہم ہے!';

  @override
  String get leaveReviewAndroid =>
      'ہمیں مزید لوگوں تک پہنچنے میں مدد کریں Google Play Store میں ریویو چھوڑ کر۔ آپ کی رائے ہمارے لیے بہت اہم ہے!';

  @override
  String get rateOnAppStore => 'App Store پر ریٹنگ دیں';

  @override
  String get rateOnGooglePlay => 'Google Play پر ریٹنگ دیں';

  @override
  String get maybeLater => 'شاید بعد میں';

  @override
  String get speechProfileIntro =>
      'Omi کو آپ کے مقاصد اور آپ کی آواز سے سیکھنے کی ضرورت ہے۔ آپ اسے بعد میں ترمیم کر سکیں گے۔';

  @override
  String get getStarted => 'شروع کریں';

  @override
  String get allDone => 'ہو گیا!';

  @override
  String get keepGoing => 'جاری رکھیں، آپ بہترین کام کر رہے ہیں';

  @override
  String get skipThisQuestion => 'اس سوال کو چھوڑ دیں';

  @override
  String get skipForNow => 'ابھی کے لیے چھوڑ دیں';

  @override
  String get connectionError => 'کنکشن خرابی';

  @override
  String get connectionErrorDesc => 'سرور سے جڑنا ناکام۔ براہ کرم اپنی انٹرنیٹ کنکشن چیک کریں اور دوبارہ کوشش کریں۔';

  @override
  String get invalidRecordingMultipleSpeakers => 'غلط ریکارڈنگ شدہ';

  @override
  String get multipleSpeakersDesc =>
      'ایسا لگتا ہے کہ ریکارڈنگ میں متعدد سپیکر ہیں۔ براہ کرم یقینی بنائیں کہ آپ خاموش جگہ میں ہیں اور دوبارہ کوشش کریں۔';

  @override
  String get tooShortDesc => 'کافی تقریر شدہ نہیں ہے۔ براہ کرم زیادہ بول کر دوبارہ کوشش کریں۔';

  @override
  String get invalidRecordingDesc => 'براہ کرم یقینی بنائیں کہ آپ کم از کم 5 سیکنڈ اور 90 سے زیادہ نہیں بول رہے ہیں۔';

  @override
  String get areYouThere => 'آپ ہیں؟';

  @override
  String get noSpeechDesc =>
      'ہم کوئی تقریر معلوم نہیں کر سکے۔ براہ کرم کم از کم 10 سیکنڈ اور 3 منٹ سے کم نہ بول کر یقینی بنائیں۔';

  @override
  String get connectionLost => 'کنکشن ٹوٹ گیا';

  @override
  String get connectionLostDesc => 'کنکشن میں خلل پڑا۔ براہ کرم اپنی انٹرنیٹ کنکشن چیک کریں اور دوبارہ کوشش کریں۔';

  @override
  String get tryAgain => 'دوبارہ کوشش کریں';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass سے جڑیں';

  @override
  String get continueWithoutDevice => 'آلے کے بغیر جاری رکھیں';

  @override
  String get permissionsRequired => 'اختیارات درکار ہیں';

  @override
  String get permissionsRequiredDesc =>
      'اس ایپ کو صحیح طریقے سے کام کرنے کے لیے Bluetooth اور Location کی اختیارات کی ضرورت ہے۔ براہ کرم انہیں ترتیبات میں فعال کریں۔';

  @override
  String get openSettings => 'ترتیبات کھولیں';

  @override
  String get wantDifferentName => 'کچھ اور نام سے جانا چاہتے ہیں؟';

  @override
  String get whatsYourName => 'آپ کا نام کیا ہے؟';

  @override
  String get speakTranscribeSummarize => 'بولیں۔ ٹرانسکرائب کریں۔ خلاصہ کریں۔';

  @override
  String get signInWithApple => 'Apple کے ساتھ سائن ان کریں';

  @override
  String get signInWithGoogle => 'Google کے ساتھ سائن ان کریں';

  @override
  String get byContinuingAgree => 'جاری رکھ کر، آپ ہمارے سے متفق ہیں ';

  @override
  String get termsOfUse => 'استعمال کی شرائط';

  @override
  String get omiYourAiCompanion => 'Omi – آپ کا AI ساتھی';

  @override
  String get captureEveryMoment => 'ہر لمحہ پکڑیں۔ AI سے چلائے ہوئے\nخلاصے حاصل کریں۔ کبھی نوٹس نہ لیں۔';

  @override
  String get appleWatchSetup => 'Apple Watch سیٹ اپ';

  @override
  String get permissionRequestedExclaim => 'اختیار درخواست دی گئی!';

  @override
  String get microphonePermission => 'مائیکروفون اختیار';

  @override
  String get permissionGrantedNow =>
      'اختیار دی گئی! اب:\n\nاپنی گھڑی پر Omi ایپ کھولیں اور نیچے \"جاری رکھیں\" پر ٹیپ کریں';

  @override
  String get needMicrophonePermission =>
      'ہمیں مائیکروفون اختیار کی ضرورت ہے۔\n\n1. \"اختیار دیں\" ٹیپ کریں\n2. اپنے iPhone پر اجازت دیں\n3. گھڑی کی ایپ بند ہو جائے گی\n4. دوبارہ کھولیں اور \"جاری رکھیں\" ٹیپ کریں';

  @override
  String get grantPermissionButton => 'اختیار دیں';

  @override
  String get needHelp => 'مدد کی ضرورت ہے؟';

  @override
  String get troubleshootingSteps =>
      'مسائل کا حل:\n\n1. یقینی بنائیں کہ Omi آپ کی گھڑی پر انسٹال ہے\n2. اپنی گھڑی پر Omi ایپ کھولیں\n3. اختیار پاپ اپ تلاش کریں\n4. جب پوچھا جائے \"اجازت دیں\" ٹیپ کریں\n5. آپ کی گھڑی کی ایپ بند ہوگی - اسے دوبارہ کھولیں\n6. اپنے iPhone پر واپس آئیں اور \"جاری رکھیں\" ٹیپ کریں';

  @override
  String get recordingStartedSuccessfully => 'ریکارڈنگ کامیابی سے شروع ہو گئی!';

  @override
  String get permissionNotGrantedYet =>
      'اختیار ابھی نہیں دیا گیا۔ براہ کرم یقینی بنائیں کہ آپ نے مائیکروفون رسائی کی اجازت دی ہے اور اپنی گھڑی پر ایپ دوبارہ کھولی ہے۔';

  @override
  String errorRequestingPermission(String error) {
    return 'اختیار درخواست کرتے وقت خرابی: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'ریکارڈنگ شروع کرتے وقت خرابی: $error';
  }

  @override
  String get selectPrimaryLanguage => 'اپنی بنیادی زبان منتخب کریں';

  @override
  String get languageBenefits => 'تیز تر ٹرانسکرپشن اور ذاتی نوعیت کے تجربے کے لیے اپنی زبان مقرر کریں';

  @override
  String get whatsYourPrimaryLanguage => 'آپ کی بنیادی زبان کیا ہے؟';

  @override
  String get selectYourLanguage => 'اپنی زبان منتخب کریں';

  @override
  String get personalGrowthJourney => 'AI کے ساتھ آپ کا ذاتی نشوونما کا سفر جو آپ کے ہر لفظ کو سنتا ہے۔';

  @override
  String get actionItemsTitle => 'کام کریں';

  @override
  String get actionItemsDescription =>
      'ترمیم کرنے کے لیے ٹیپ کریں • منتخب کرنے کے لیے لمبی دبائیں • اقدامات کے لیے سوائپ کریں';

  @override
  String get tabToDo => 'کریں';

  @override
  String get tabDone => 'مکمل';

  @override
  String get tabOld => 'پرانا';

  @override
  String get emptyTodoMessage => '🎉 سب ختم!\nکوئی زیر التوا کام نہیں';

  @override
  String get emptyDoneMessage => 'ابھی کوئی مکمل شدہ چیز نہیں';

  @override
  String get emptyOldMessage => '✅ کوئی پرانا کام نہیں';

  @override
  String get noItems => 'کوئی چیزیں نہیں';

  @override
  String get actionItemMarkedIncomplete => 'کام نامکمل کے طور پر نشان زد کیا گیا';

  @override
  String get actionItemCompleted => 'کام مکمل ہو گیا';

  @override
  String get deleteActionItemTitle => 'کام حذف کریں';

  @override
  String get deleteActionItemMessage => 'کیا آپ یقینی ہیں کہ یہ کام حذف کرنا چاہتے ہیں؟';

  @override
  String get deleteSelectedItemsTitle => 'منتخب شدہ چیزیں حذف کریں';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'کام \"$description\" حذف ہو گیا';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'کام حذف کرنا ناکام';

  @override
  String get failedToDeleteItems => 'چیزیں حذف کرنا ناکام';

  @override
  String get failedToDeleteSomeItems => 'کچھ چیزیں حذف کرنا ناکام';

  @override
  String get welcomeActionItemsTitle => 'کام کے لیے تیار ہیں';

  @override
  String get welcomeActionItemsDescription =>
      'آپ کا AI خودکار طور پر آپ کی بات چیت سے کام اور کام نکالے گا۔ وہ بنائے جانے پر یہاں ظاہر ہوں گے۔';

  @override
  String get autoExtractionFeature => 'بات چیت سے خودکار طور پر نکالا گیا';

  @override
  String get editSwipeFeature => 'ترمیم کے لیے ٹیپ کریں، مکمل یا حذف کرنے کے لیے سوائپ کریں';

  @override
  String itemsSelected(int count) {
    return '$count منتخب';
  }

  @override
  String get selectAll => 'تمام منتخب کریں';

  @override
  String get deleteSelected => 'منتخب شدہ حذف کریں';

  @override
  String get searchMemories => 'یادوں میں تلاش کریں...';

  @override
  String get memoryDeleted => 'یاد حذف ہو گئی۔';

  @override
  String get undo => 'واپس لیں';

  @override
  String get noMemoriesYet => '🧠 ابھی کوئی یادیں نہیں';

  @override
  String get noAutoMemories => 'ابھی کوئی خودکار نکالی گئی یادیں نہیں';

  @override
  String get noManualMemories => 'ابھی کوئی دستی یادیں نہیں';

  @override
  String get noMemoriesInCategories => 'ان اقسام میں کوئی یادیں نہیں';

  @override
  String get noMemoriesFound => '🔍 کوئی یادیں نہیں ملیں';

  @override
  String get addFirstMemory => 'اپنی پہلی یاد شامل کریں';

  @override
  String get clearMemoryTitle => 'Omi کی میموری صاف کریں';

  @override
  String get clearMemoryMessage => 'کیا آپ یقینی ہیں کہ Omi کی میموری صاف کرنا چاہتے ہیں؟ یہ عمل الٹایا نہیں جا سکتا۔';

  @override
  String get clearMemoryButton => 'میموری صاف کریں';

  @override
  String get memoryClearedSuccess => 'آپ کے بارے میں Omi کی میموری صاف ہو گئی';

  @override
  String get noMemoriesToDelete => 'حذف کرنے کے لیے کوئی یادیں نہیں';

  @override
  String get createMemoryTooltip => 'نئی یاد بنائیں';

  @override
  String get createActionItemTooltip => 'نیا کام بنائیں';

  @override
  String get memoryManagement => 'یاد کی تدبیر';

  @override
  String get filterMemories => 'یادوں میں فلٹر کریں';

  @override
  String totalMemoriesCount(int count) {
    return 'آپ کے پاس $count کل یادیں ہیں';
  }

  @override
  String get publicMemories => 'عوامی یادیں';

  @override
  String get privateMemories => 'نجی یادیں';

  @override
  String get makeAllPrivate => 'تمام یادوں کو نجی بنائیں';

  @override
  String get makeAllPublic => 'تمام یادوں کو عوامی بنائیں';

  @override
  String get deleteAllMemories => 'تمام یادیں حذف کریں';

  @override
  String get allMemoriesPrivateResult => 'تمام یادیں اب نجی ہیں';

  @override
  String get allMemoriesPublicResult => 'تمام یادیں اب عوامی ہیں';

  @override
  String get newMemory => '✨ نئی یاد';

  @override
  String get editMemory => '✏️ یاد میں ترمیم کریں';

  @override
  String get memoryContentHint => 'مجھے آئس کریم کھانا پسند ہے...';

  @override
  String get failedToSaveMemory => 'محفوظ کرنا ناکام۔ براہ کرم اپنی کنکشن چیک کریں۔';

  @override
  String get saveMemory => 'یاد محفوظ کریں';

  @override
  String get retry => 'دوبارہ کوشش کریں';

  @override
  String get createActionItem => 'کام بنائیں';

  @override
  String get editActionItem => 'کام میں ترمیم کریں';

  @override
  String get actionItemDescriptionHint => 'کیا کرنے کی ضرورت ہے؟';

  @override
  String get actionItemDescriptionEmpty => 'کام کی تفصیل خالی نہیں ہو سکتی۔';

  @override
  String get actionItemUpdated => 'کام اپ ڈیٹ ہو گیا';

  @override
  String get failedToUpdateActionItem => 'کام اپ ڈیٹ کرنا ناکام';

  @override
  String get actionItemCreated => 'کام بنایا گیا';

  @override
  String get failedToCreateActionItem => 'کام بنانا ناکام';

  @override
  String get dueDate => 'مقررہ تاریخ';

  @override
  String get time => 'وقت';

  @override
  String get addDueDate => 'مقررہ تاریخ شامل کریں';

  @override
  String get pressDoneToSave => 'محفوظ کرنے کے لیے مکمل دبائیں';

  @override
  String get pressDoneToCreate => 'بنانے کے لیے مکمل دبائیں';

  @override
  String get filterAll => 'تمام';

  @override
  String get filterSystem => 'آپ کے بارے میں';

  @override
  String get filterInteresting => 'بصیرتیں';

  @override
  String get filterManual => 'دستی';

  @override
  String get completed => 'مکمل';

  @override
  String get markComplete => 'مکمل کے طور پر نشان زد کریں';

  @override
  String get actionItemDeleted => 'کام حذف ہو گیا';

  @override
  String get failedToDeleteActionItem => 'کام حذف کرنا ناکام';

  @override
  String get deleteActionItemConfirmTitle => 'کام حذف کریں';

  @override
  String get deleteActionItemConfirmMessage => 'کیا آپ یقینی ہیں کہ یہ کام حذف کرنا چاہتے ہیں؟';

  @override
  String get appLanguage => 'ایپ کی زبان';

  @override
  String get appInterfaceSectionTitle => 'ایپ انٹرفیس';

  @override
  String get speechTranscriptionSectionTitle => 'تقریر اور ٹرانسکرپشن';

  @override
  String get languageSettingsHelperText =>
      'ایپ کی زبان مینوز اور بٹن بدلتی ہے۔ تقریر کی زبان آپ کی ریکارڈنگز کی ٹرانسکرپشن کو متاثر کرتی ہے۔';

  @override
  String get translationNotice => 'ترجمے کا نوٹس';

  @override
  String get translationNoticeMessage =>
      'Omi آپ کی بات چیت کو اپنی بنیادی زبان میں ترجمہ کرتا ہے۔ Settings → Profiles میں کسی بھی وقت اپ ڈیٹ کریں۔';

  @override
  String get pleaseCheckInternetConnection => 'براہ کرم اپنی انٹرنیٹ کنکشن چیک کریں اور دوبارہ کوشش کریں';

  @override
  String get pleaseSelectReason => 'براہ کرم ایک وجہ منتخب کریں';

  @override
  String get tellUsMoreWhatWentWrong => 'ہمیں مزید بتائیں کہ کیا غلط ہوا...';

  @override
  String get selectText => 'متن منتخب کریں';

  @override
  String maximumGoalsAllowed(int count) {
    return 'زیادہ سے زیادہ $count مقاصد کی اجازت ہے';
  }

  @override
  String get conversationCannotBeMerged => 'یہ بات چیت ملائی نہیں جا سکتی (بند یا پہلے سے ملایا جا رہا ہے)';

  @override
  String get pleaseEnterFolderName => 'براہ کرم فوڈر کا نام درج کریں';

  @override
  String get failedToCreateFolder => 'فوڈر بنانا ناکام';

  @override
  String get failedToUpdateFolder => 'فوڈر اپ ڈیٹ کرنا ناکام';

  @override
  String get folderName => 'فوڈر کا نام';

  @override
  String get descriptionOptional => 'تفصیل (اختیاری)';

  @override
  String get failedToDeleteFolder => 'فولڈر کو حذف کرنے میں ناکام';

  @override
  String get editFolder => 'فولڈر میں ترمیم کریں';

  @override
  String get deleteFolder => 'فولڈر حذف کریں';

  @override
  String get transcriptCopiedToClipboard => 'ٹرانسکرپٹ کلپ بورڈ پر کاپی ہو گیا';

  @override
  String get summaryCopiedToClipboard => 'خلاصہ کلپ بورڈ پر کاپی ہو گیا';

  @override
  String get conversationUrlCouldNotBeShared => 'بات چیت کا URL شیئر نہیں کیا جا سکا۔';

  @override
  String get urlCopiedToClipboard => 'URL کلپ بورڈ پر کاپی ہو گیا';

  @override
  String get exportTranscript => 'ٹرانسکرپٹ برائے';

  @override
  String get exportSummary => 'خلاصہ برائے';

  @override
  String get exportButton => 'برائے';

  @override
  String get actionItemsCopiedToClipboard => 'کارروائی کی چیزیں کلپ بورڈ پر کاپی ہو گئیں';

  @override
  String get summarize => 'خلاصہ';

  @override
  String get generateSummary => 'خلاصہ بنائیں';

  @override
  String get conversationNotFoundOrDeleted => 'بات چیت نہیں ملی یا حذف ہو گئی ہے';

  @override
  String get deleteMemory => 'یادوں کو حذف کریں';

  @override
  String get thisActionCannotBeUndone => 'یہ کارروائی واپس نہیں کی جا سکتی۔';

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
  String get noMemoriesInCategory => 'ابھی اس زمرے میں کوئی یادیں نہیں ہیں';

  @override
  String get addYourFirstMemory => 'اپنی پہلی یاد شامل کریں';

  @override
  String get firmwareDisconnectUsb => 'USB کو الگ کریں';

  @override
  String get firmwareUsbWarning => 'اپ ڈیٹ کے دوران USB کنکشن آپ کے ڈیوائس کو نقصان پہنچا سکتا ہے۔';

  @override
  String get firmwareBatteryAbove15 => 'بیٹری 15 فیصد سے اوپر';

  @override
  String get firmwareEnsureBattery => 'یقینی بنائیں کہ آپ کے ڈیوائس میں 15 فیصد بیٹری ہے۔';

  @override
  String get firmwareStableConnection => 'مستحکم کنکشن';

  @override
  String get firmwareConnectWifi => 'Wi-Fi یا سیلولر سے منسلک کریں۔';

  @override
  String failedToStartUpdate(String error) {
    return 'اپ ڈیٹ شروع کرنے میں ناکام: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'اپ ڈیٹ سے پہلے یقینی بنائیں:';

  @override
  String get confirmed => 'تصدیق ہو گئی!';

  @override
  String get release => 'جاری کریں';

  @override
  String get slideToUpdate => 'اپ ڈیٹ کے لیے سلائڈ کریں';

  @override
  String copiedToClipboard(String title) {
    return '$title کلپ بورڈ پر کاپی ہو گیا';
  }

  @override
  String get batteryLevel => 'بیٹری کی سطح';

  @override
  String get charging => 'چارج ہو رہا ہے';

  @override
  String get productUpdate => 'مصنوع کی اپ ڈیٹ';

  @override
  String get offline => 'آن لائن نہیں';

  @override
  String get available => 'دستیاب';

  @override
  String get unpairDeviceDialogTitle => 'ڈیوائس کو الگ کریں';

  @override
  String get unpairDeviceDialogMessage =>
      'یہ ڈیوائس کو الگ کر دے گا تاکہ یہ دوسرے فون سے منسلک ہو سکے۔ اس عمل کو مکمل کرنے کے لیے آپ کو Settings > Bluetooth میں جانا ہوگا اور ڈیوائس کو بھول جانا ہوگا۔';

  @override
  String get unpair => 'الگ کریں';

  @override
  String get unpairAndForgetDevice => 'ڈیوائس کو الگ اور بھول جائیں';

  @override
  String get unknownDevice => 'نامعلوم';

  @override
  String get unknown => 'نامعلوم';

  @override
  String get productName => 'مصنوع کا نام';

  @override
  String get serialNumber => 'سیریل نمبر';

  @override
  String get connected => 'منسلک';

  @override
  String get privacyPolicyTitle => 'رازداری کی پالیسی';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label کاپی کیا گیا';
  }

  @override
  String get noApiKeysYet => 'ابھی کوئی API کلیدیں نہیں ہیں';

  @override
  String get createKeyToGetStarted => 'شروع کرنے کے لیے کلید بنائیں';

  @override
  String get configureSttProvider => 'STT فراہم کنندہ کنفیگر کریں';

  @override
  String get setWhenConversationsAutoEnd => 'سیٹ کریں کہ بات چیتیں کب خودکار طور پر ختم ہوں';

  @override
  String get importDataFromOtherSources => 'دوسری ذرائع سے ڈیٹا درآمد کریں';

  @override
  String get debugAndDiagnostics => 'ڈیبگ اور تشخیص';

  @override
  String get autoDeletesAfter3Days => '3 دن کے بعد خود حذف ہو جاتا ہے۔';

  @override
  String get helpsDiagnoseIssues => 'مسائل کی تشخیص میں مدد کرتا ہے';

  @override
  String get exportStartedMessage => 'برائے شروع ہو گیا۔ یہ کچھ سیکنڈ لگ سکتے ہیں...';

  @override
  String get exportConversationsToJson => 'بات چیتوں کو JSON فائل میں برائے کریں';

  @override
  String get knowledgeGraphDeletedSuccess => 'علم کا گراف کامیابی سے حذف ہو گیا';

  @override
  String failedToDeleteGraph(String error) {
    return 'گراف حذف کرنے میں ناکام: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'تمام نوڈز اور کنکشنز کو صاف کریں';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.json میں شامل کریں';

  @override
  String get connectAiAssistantsToData => 'AI معاونین کو اپنے ڈیٹا سے منسلک کریں';

  @override
  String get useYourMcpApiKey => 'اپنی MCP API کلید استعمال کریں';

  @override
  String get realTimeTranscript => 'حقیقی وقت میں ٹرانسکرپٹ';

  @override
  String get experimental => 'تجرباتی';

  @override
  String get transcriptionDiagnostics => 'ٹرانسکریشن تشخیص';

  @override
  String get detailedDiagnosticMessages => 'تفصیلی تشخیصی پیغامات';

  @override
  String get autoCreateSpeakers => 'خود کار طور پر بولنے والے بنائیں';

  @override
  String get autoCreateWhenNameDetected => 'جب نام پایا جائے تو خود کار طور پر بنائیں';

  @override
  String get followUpQuestions => 'فالو اپ سوالات';

  @override
  String get suggestQuestionsAfterConversations => 'بات چیت کے بعد سوالات کی تجویز دیں';

  @override
  String get goalTracker => 'مقصد کا ٹریکر';

  @override
  String get trackPersonalGoalsOnHomepage => 'ہوم پیج پر اپنے ذاتی مقاصد کو ٹریک کریں';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'کارروائی کی چیز کی تفصیل خالی نہیں ہو سکتی';

  @override
  String get saved => 'محفوظ کیا گیا';

  @override
  String get overdue => 'مقررہ سے زیادہ';

  @override
  String get failedToUpdateDueDate => 'مقررہ تاریخ اپ ڈیٹ کرنے میں ناکام';

  @override
  String get markIncomplete => 'نامکمل کے طور پر نشان زد کریں';

  @override
  String get editDueDate => 'مقررہ تاریخ میں ترمیم کریں';

  @override
  String get setDueDate => 'مقررہ تاریخ سیٹ کریں';

  @override
  String get clearDueDate => 'مقررہ تاریخ صاف کریں';

  @override
  String get failedToClearDueDate => 'مقررہ تاریخ صاف کرنے میں ناکام';

  @override
  String get mondayAbbr => 'پیر';

  @override
  String get tuesdayAbbr => 'منگل';

  @override
  String get wednesdayAbbr => 'بدھ';

  @override
  String get thursdayAbbr => 'جمعرات';

  @override
  String get fridayAbbr => 'جمعہ';

  @override
  String get saturdayAbbr => 'ہفتہ';

  @override
  String get sundayAbbr => 'اتوار';

  @override
  String get howDoesItWork => 'یہ کیسے کام کرتا ہے؟';

  @override
  String get sdCardSyncDescription => 'SD کارڈ Sync آپ کی یادوں کو SD کارڈ سے ایپ میں درآمد کرے گا';

  @override
  String get checksForAudioFiles => 'SD کارڈ پر آڈیو فائلوں کی جانچ کرتا ہے';

  @override
  String get omiSyncsAudioFiles => 'Omi پھر آڈیو فائلوں کو سرور کے ساتھ Sync کرتا ہے';

  @override
  String get serverProcessesAudio => 'سرور آڈیو فائلوں کو پروسیس کرتا ہے اور یادیں بناتا ہے';

  @override
  String get youreAllSet => 'آپ تیار ہیں!';

  @override
  String get welcomeToOmiDescription =>
      'Omi میں خوش آمدید! آپ کا AI ساتھی بات چیت، کاموں اور بہت کچھ میں آپ کی مدد کے لیے تیار ہے۔';

  @override
  String get startUsingOmi => 'Omi استعمال کرنا شروع کریں';

  @override
  String get back => 'واپس';

  @override
  String get keyboardShortcuts => 'کی بورڈ کے اختصارات';

  @override
  String get toggleControlBar => 'کنٹرول بار کو ٹوگل کریں';

  @override
  String get pressKeys => 'کلیدیں دبائیں...';

  @override
  String get cmdRequired => '⌘ ضروری';

  @override
  String get invalidKey => 'غلط کلید';

  @override
  String get space => 'Space';

  @override
  String get search => 'تلاش کریں';

  @override
  String get searchPlaceholder => 'تلاش کریں...';

  @override
  String get untitledConversation => 'بغیر عنوان کی بات چیت';

  @override
  String countRemaining(String count) {
    return '$count باقی';
  }

  @override
  String get addGoal => 'مقصد شامل کریں';

  @override
  String get editGoal => 'مقصد میں ترمیم کریں';

  @override
  String get icon => 'شبیہ';

  @override
  String get goalTitle => 'مقصد کا عنوان';

  @override
  String get current => 'موجودہ';

  @override
  String get target => 'مقصد';

  @override
  String get saveGoal => 'محفوظ کریں';

  @override
  String get goals => 'مقاصد';

  @override
  String get tapToAddGoal => 'مقصد شامل کرنے کے لیے تھپتھپائیں';

  @override
  String welcomeBack(String name) {
    return 'خوش آمدید $name';
  }

  @override
  String get yourConversations => 'آپ کی بات چیتیں';

  @override
  String get reviewAndManageConversations => 'اپنی پکڑی گئی بات چیتوں کا جائزہ لیں اور انتظام کریں';

  @override
  String get startCapturingConversations =>
      'اپنے Omi ڈیوائس کے ساتھ بات چیتوں کو پکڑنا شروع کریں تاکہ انہیں یہاں دیکھ سکیں۔';

  @override
  String get useMobileAppToCapture => 'آڈیو پکڑنے کے لیے اپنی موبائل ایپ استعمال کریں';

  @override
  String get conversationsProcessedAutomatically => 'بات چیتوں کو خود کار طور پر پروسیس کیا جاتا ہے';

  @override
  String get getInsightsInstantly => 'فوری طور پر بصیرت اور خلاصے حاصل کریں';

  @override
  String get showAll => 'تمام دیکھیں';

  @override
  String get noTasksForToday => 'آج کے لیے کوئی کام نہیں۔\nOmi سے مزید کام مانگیں یا دستی طور پر بنائیں۔';

  @override
  String get dailyScore => 'روز مرہ کا اسکور';

  @override
  String get dailyScoreDescription => 'ایک اسکور جو آپ کو بہتر طریقے سے\nعمل پر توجہ مرکوز کرنے میں مدد کرتا ہے۔';

  @override
  String get searchResults => 'تلاش کے نتائج';

  @override
  String get actionItems => 'کارروائی کی چیزیں';

  @override
  String get tasksToday => 'آج';

  @override
  String get tasksTomorrow => 'کل';

  @override
  String get tasksNoDeadline => 'کوئی مقررہ نہیں';

  @override
  String get tasksLater => 'بعد میں';

  @override
  String get loadingTasks => 'کام لوڈ ہو رہے ہیں...';

  @override
  String get tasks => 'کام';

  @override
  String get swipeTasksToIndent => 'کام داخل کرنے کے لیے سوائپ کریں، زمرے کے درمیان گھسیٹیں';

  @override
  String get create => 'بنائیں';

  @override
  String get noTasksYet => 'ابھی کوئی کام نہیں';

  @override
  String get tasksFromConversationsWillAppear =>
      'آپ کی بات چیتوں سے کام یہاں ظاہر ہوں گے۔\nدستی طور پر شامل کرنے کے لیے بنائیں پر کلک کریں۔';

  @override
  String get monthJan => 'جنوری';

  @override
  String get monthFeb => 'فروری';

  @override
  String get monthMar => 'مارچ';

  @override
  String get monthApr => 'اپریل';

  @override
  String get monthMay => 'مئی';

  @override
  String get monthJun => 'جون';

  @override
  String get monthJul => 'جولائی';

  @override
  String get monthAug => 'اگست';

  @override
  String get monthSep => 'ستمبر';

  @override
  String get monthOct => 'اکتوبر';

  @override
  String get monthNov => 'نومبر';

  @override
  String get monthDec => 'دسمبر';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'کارروائی کی چیز کامیابی سے اپ ڈیٹ ہو گئی';

  @override
  String get actionItemCreatedSuccessfully => 'کارروائی کی چیز کامیابی سے بنائی گئی';

  @override
  String get actionItemDeletedSuccessfully => 'کارروائی کی چیز کامیابی سے حذف ہو گئی';

  @override
  String get deleteActionItem => 'کارروائی کی چیز حذف کریں';

  @override
  String get deleteActionItemConfirmation =>
      'کیا آپ اس کارروائی کی چیز کو حذف کرنا چاہتے ہیں؟ یہ کارروائی واپس نہیں کی جا سکتی۔';

  @override
  String get enterActionItemDescription => 'کارروائی کی چیز کی تفصیل درج کریں...';

  @override
  String get markAsCompleted => 'مکمل کے طور پر نشان زد کریں';

  @override
  String get setDueDateAndTime => 'مقررہ تاریخ اور وقت سیٹ کریں';

  @override
  String get reloadingApps => 'ایپس دوبارہ لوڈ ہو رہی ہیں...';

  @override
  String get loadingApps => 'ایپس لوڈ ہو رہی ہیں...';

  @override
  String get browseInstallCreateApps => 'ایپس براؤز، انسٹال اور بنائیں';

  @override
  String get all => 'تمام';

  @override
  String get open => 'کھولیں';

  @override
  String get install => 'انسٹال کریں';

  @override
  String get noAppsAvailable => 'کوئی ایپس دستیاب نہیں ہیں';

  @override
  String get unableToLoadApps => 'ایپس لوڈ کرنے میں ناکام';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'اپنی تلاش کی شرائط یا فلٹرز میں ترمیم کرنے کی کوشش کریں';

  @override
  String get checkBackLaterForNewApps => 'نئی ایپس کے لیے بعد میں واپس چیک کریں';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'براہ کرم اپنے انٹرنیٹ کنکشن کی جانچ کریں اور دوبارہ کوشش کریں';

  @override
  String get createNewApp => 'نئی ایپ بنائیں';

  @override
  String get buildSubmitCustomOmiApp => 'اپنی کسٹم Omi ایپ بنائیں اور جمع کریں';

  @override
  String get submittingYourApp => 'اپنی ایپ جمع کی جا رہی ہے...';

  @override
  String get preparingFormForYou => 'آپ کے لیے فارم تیار کیا جا رہا ہے...';

  @override
  String get appDetails => 'ایپ کی تفصیلات';

  @override
  String get paymentDetails => 'ادائیگی کی تفصیلات';

  @override
  String get previewAndScreenshots => 'پریویو اور اسکرین شاٹس';

  @override
  String get appCapabilities => 'ایپ کی صلاحیتیں';

  @override
  String get aiPrompts => 'AI اشارات';

  @override
  String get chatPrompt => 'چیٹ کا اشارہ';

  @override
  String get chatPromptPlaceholder =>
      'آپ ایک بہترین ایپ ہیں، آپ کا کام صارف کی سوالات کا جواب دینا اور انہیں خوش محسوس کرانا ہے...';

  @override
  String get conversationPrompt => 'بات چیت کا اشارہ';

  @override
  String get conversationPromptPlaceholder =>
      'آپ ایک بہترین ایپ ہیں، آپ کو بات چیت کا ٹرانسکرپٹ اور خلاصہ دیا جائے گا...';

  @override
  String get notificationScopes => 'اطلاع کے دائرے';

  @override
  String get appPrivacyAndTerms => 'ایپ کی رازداری اور شرائط';

  @override
  String get makeMyAppPublic => 'میری ایپ کو عوامی بنائیں';

  @override
  String get submitAppTermsAgreement =>
      'اس ایپ کو جمع کر کے، میں Omi AI کی خدمات کی شرائط اور رازداری کی پالیسی سے متفق ہوں';

  @override
  String get submitApp => 'ایپ جمع کریں';

  @override
  String get needHelpGettingStarted => 'شروع کرنے میں مدد کی ضرورت ہے؟';

  @override
  String get clickHereForAppBuildingGuides => 'ایپ بنانے کی رہنمائی اور دستاویزات کے لیے یہاں کلک کریں';

  @override
  String get submitAppQuestion => 'ایپ جمع کریں؟';

  @override
  String get submitAppPublicDescription =>
      'آپ کی ایپ کا جائزہ لیا جائے گا اور عوامی بنایا جائے گا۔ جائزے کے دوران بھی آپ فوری طور پر اس کا استعمال شروع کر سکتے ہیں!';

  @override
  String get submitAppPrivateDescription =>
      'آپ کی ایپ کا جائزہ لیا جائے گا اور آپ کے لیے نجی طور پر دستیاب بنایا جائے گا۔ جائزے کے دوران بھی آپ فوری طور پر اس کا استعمال شروع کر سکتے ہیں!';

  @override
  String get startEarning => 'کمائی شروع کریں! 💰';

  @override
  String get connectStripeOrPayPal => 'Stripe یا PayPal سے منسلک کریں اپنی ایپ کے لیے ادائیگی وصول کرنے کے لیے۔';

  @override
  String get connectNow => 'اب منسلک کریں';

  @override
  String get installsCount => 'انسٹالز';

  @override
  String get uninstallApp => 'ایپ انسٹال کریں';

  @override
  String get subscribe => 'رکنیت حاصل کریں';

  @override
  String get dataAccessNotice => 'ڈیٹا کی رسائی کا نوٹس';

  @override
  String get dataAccessWarning =>
      'یہ ایپ آپ کے ڈیٹا کو رسائی حاصل کرے گی۔ Omi AI اس بات کے لیے ذمہ دار نہیں ہے کہ یہ ایپ آپ کے ڈیٹا کو کیسے استعمال، تبدیل یا حذف کرتا ہے';

  @override
  String get installApp => 'ایپ انسٹال کریں';

  @override
  String get betaTesterNotice =>
      'آپ اس ایپ کے لیے بیٹا ٹیسٹر ہیں۔ یہ ابھی عوامی نہیں ہے۔ یہ منظور ہونے کے بعد عوامی ہوگا۔';

  @override
  String get appUnderReviewOwner => 'آپ کی ایپ جائزے میں ہے اور صرف آپ کو نظر آتی ہے۔ یہ منظور ہونے کے بعد عوامی ہوگی۔';

  @override
  String get appRejectedNotice =>
      'آپ کی ایپ مسترد کر دی گئی ہے۔ براہ کرم ایپ کی تفصیلات میں ترمیم کریں اور دوبارہ جائزے کے لیے جمع کریں۔';

  @override
  String get setupSteps => 'سیٹ اپ کے اقدامات';

  @override
  String get setupInstructions => 'سیٹ اپ کی ہدایات';

  @override
  String get integrationInstructions => 'انضمام کی ہدایات';

  @override
  String get preview => 'پریویو';

  @override
  String get aboutTheApp => 'ایپ کے بارے میں';

  @override
  String get chatPersonality => 'چیٹ کی شخصیت';

  @override
  String get ratingsAndReviews => 'درجہ بندی اور جائزے';

  @override
  String get noRatings => 'کوئی درجہ بندی نہیں';

  @override
  String ratingsCount(String count) {
    return '$count+ درجہ بندیاں';
  }

  @override
  String get errorActivatingApp => 'ایپ کو فعال کرنے میں خرابی';

  @override
  String get integrationSetupRequired => 'اگر یہ ایک انضمام ایپ ہے، تو یقینی بنائیں کہ سیٹ اپ مکمل ہو گیا ہے۔';

  @override
  String get installed => 'انسٹال شدہ';

  @override
  String get appIdLabel => 'ایپ ID';

  @override
  String get appNameLabel => 'ایپ کا نام';

  @override
  String get appNamePlaceholder => 'میری بہترین ایپ';

  @override
  String get pleaseEnterAppName => 'براہ کرم ایپ کا نام درج کریں';

  @override
  String get categoryLabel => 'زمرہ';

  @override
  String get selectCategory => 'زمرہ منتخب کریں';

  @override
  String get descriptionLabel => 'تفصیل';

  @override
  String get appDescriptionPlaceholder =>
      'میری بہترین ایپ ایک بہترین ایپ ہے جو حیرت انگیز چیزیں کرتی ہے۔ یہ سب سے بہترین ایپ ہے!';

  @override
  String get pleaseProvideValidDescription => 'براہ کرم درست تفصیل فراہم کریں';

  @override
  String get appPricingLabel => 'ایپ کی قیمت';

  @override
  String get noneSelected => 'کوئی منتخب نہیں';

  @override
  String get appIdCopiedToClipboard => 'ایپ ID کلپ بورڈ پر کاپی ہو گیا';

  @override
  String get appCategoryModalTitle => 'ایپ کا زمرہ';

  @override
  String get pricingFree => 'مفت';

  @override
  String get pricingPaid => 'معاوضہ';

  @override
  String get loadingCapabilities => 'صلاحیتیں لوڈ ہو رہی ہیں...';

  @override
  String get filterInstalled => 'انسٹال شدہ';

  @override
  String get filterMyApps => 'میری ایپس';

  @override
  String get clearSelection => 'انتخاب صاف کریں';

  @override
  String get filterCategory => 'زمرہ';

  @override
  String get rating4PlusStars => '4+ ستارے';

  @override
  String get rating3PlusStars => '3+ ستارے';

  @override
  String get rating2PlusStars => '2+ ستارے';

  @override
  String get rating1PlusStars => '1+ ستارہ';

  @override
  String get filterRating => 'درجہ بندی';

  @override
  String get filterCapabilities => 'صلاحیتیں';

  @override
  String get noNotificationScopesAvailable => 'کوئی اطلاع کے دائرے دستیاب نہیں ہیں';

  @override
  String get popularApps => 'مشہور ایپس';

  @override
  String get pleaseProvidePrompt => 'براہ کرم اشارہ فراہم کریں';

  @override
  String chatWithAppName(String appName) {
    return '$appName کے ساتھ چیٹ کریں';
  }

  @override
  String get defaultAiAssistant => 'ڈیفالٹ AI معاون';

  @override
  String get readyToChat => '✨ چیٹ کے لیے تیار!';

  @override
  String get connectionNeeded => '🌐 کنکشن درکار ہے';

  @override
  String get startConversation => 'ایک بات چیت شروع کریں اور جادو شروع ہونے دیں';

  @override
  String get checkInternetConnection => 'براہ کرم اپنے انٹرنیٹ کنکشن کی جانچ کریں';

  @override
  String get wasThisHelpful => 'کیا یہ مفید تھا؟';

  @override
  String get thankYouForFeedback => 'آپ کی رائے کے لیے شکریہ!';

  @override
  String get maxFilesUploadError => 'آپ ایک وقت میں صرف 4 فائلیں اپ لوڈ کر سکتے ہیں';

  @override
  String get attachedFiles => '📎 منسلک فائلیں';

  @override
  String get takePhoto => 'تصویر لیں';

  @override
  String get captureWithCamera => 'کیمرے سے کیپچر کریں';

  @override
  String get selectImages => 'تصویریں منتخب کریں';

  @override
  String get chooseFromGallery => 'گیلری سے منتخب کریں';

  @override
  String get selectFile => 'ایک فائل منتخب کریں';

  @override
  String get chooseAnyFileType => 'کوئی بھی فائل کی قسم منتخب کریں';

  @override
  String get cannotReportOwnMessages => 'آپ اپنے پیغامات کی رپورٹ نہیں کر سکتے';

  @override
  String get messageReportedSuccessfully => '✅ پیغام کامیابی سے رپورٹ ہوا';

  @override
  String get confirmReportMessage => 'کیا آپ اس پیغام کی رپورٹ کرنا چاہتے ہیں؟';

  @override
  String get selectChatAssistant => 'چیٹ معاون منتخب کریں';

  @override
  String get enableMoreApps => 'مزید ایپس فعال کریں';

  @override
  String get chatCleared => 'چیٹ صاف ہو گئی';

  @override
  String get clearChatTitle => 'چیٹ صاف کریں؟';

  @override
  String get confirmClearChat => 'کیا آپ چیٹ صاف کرنا چاہتے ہیں؟ یہ کارروائی واپس نہیں کی جا سکتی۔';

  @override
  String get copy => 'کاپی کریں';

  @override
  String get share => 'شیئر کریں';

  @override
  String get report => 'رپورٹ کریں';

  @override
  String get microphonePermissionRequired => 'کالز بنانے کے لیے مائیکروفون کی اجازت ضروری ہے';

  @override
  String get microphonePermissionDenied =>
      'مائیکروفون کی اجازت مسترد کر دی گئی۔ براہ کرم System Preferences > Privacy & Security > Microphone میں اجازت دیں۔';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'مائیکروفون کی اجازت کی جانچ میں ناکام: $error';
  }

  @override
  String get failedToTranscribeAudio => 'آڈیو کو ٹرانسکرائب کرنے میں ناکام';

  @override
  String get transcribing => 'ٹرانسکرائب کیا جا رہا ہے...';

  @override
  String get transcriptionFailed => 'ٹرانسکریشن ناکام';

  @override
  String get discardedConversation => 'مسترد شدہ بات چیت';

  @override
  String get at => 'میں';

  @override
  String get from => 'سے';

  @override
  String get copied => 'کاپی ہو گیا!';

  @override
  String get copyLink => 'لنک کاپی کریں';

  @override
  String get hideTranscript => 'ٹرانسکرپٹ چھپائیں';

  @override
  String get viewTranscript => 'ٹرانسکرپٹ دیکھیں';

  @override
  String get conversationDetails => 'بات چیت کی تفصیلات';

  @override
  String get transcript => 'ٹرانسکرپٹ';

  @override
  String segmentsCount(int count) {
    return '$count حصے';
  }

  @override
  String get noTranscriptAvailable => 'کوئی ٹرانسکرپٹ دستیاب نہیں ہے';

  @override
  String get noTranscriptMessage => 'اس بات چیت میں کوئی ٹرانسکرپٹ نہیں ہے۔';

  @override
  String get conversationUrlCouldNotBeGenerated => 'بات چیت کا URL نہیں بنایا جا سکا۔';

  @override
  String get failedToGenerateConversationLink => 'بات چیت کی لنک بنانے میں ناکام';

  @override
  String get failedToGenerateShareLink => 'شیئر لنک بنانے میں ناکام';

  @override
  String get reloadingConversations => 'بات چیتیں دوبارہ لوڈ ہو رہی ہیں...';

  @override
  String get user => 'صارف';

  @override
  String get starred => 'ستارہ شدہ';

  @override
  String get date => 'تاریخ';

  @override
  String get noResultsFound => 'کوئی نتیجہ نہیں ملا';

  @override
  String get tryAdjustingSearchTerms => 'اپنی تلاش کی شرائط میں ترمیم کرنے کی کوشش کریں';

  @override
  String get starConversationsToFindQuickly => 'بات چیتوں کو ستارہ کریں تاکہ انہیں یہاں جلدی تلاش کریں';

  @override
  String noConversationsOnDate(String date) {
    return '$date کو کوئی بات چیتیں نہیں ہیں';
  }

  @override
  String get trySelectingDifferentDate => 'مختلف تاریخ منتخب کرنے کی کوشش کریں';

  @override
  String get conversations => 'بات چیتیں';

  @override
  String get chat => 'چیٹ';

  @override
  String get actions => 'کارروائیاں';

  @override
  String get syncAvailable => 'Sync دستیاب ہے';

  @override
  String get referAFriend => 'دوست کو ریفر کریں';

  @override
  String get help => 'مدد';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Pro میں اپ گریڈ کریں';

  @override
  String get getOmiDevice => 'Omi ڈیوائس حاصل کریں';

  @override
  String get wearableAiCompanion => 'قابل فراغ AI ساتھی';

  @override
  String get loadingMemories => 'یادیں لوڈ ہو رہی ہیں...';

  @override
  String get allMemories => 'تمام یادیں';

  @override
  String get aboutYou => 'آپ کے بارے میں';

  @override
  String get manual => 'دستی';

  @override
  String get loadingYourMemories => 'آپ کی یادیں لوڈ ہو رہی ہیں...';

  @override
  String get createYourFirstMemory => 'شروع کرنے کے لیے اپنی پہلی یاد بنائیں';

  @override
  String get tryAdjustingFilter => 'اپنی تلاش یا فلٹر میں ترمیم کرنے کی کوشش کریں';

  @override
  String get whatWouldYouLikeToRemember => 'آپ کیا یاد رکھنا چاہتے ہیں؟';

  @override
  String get category => 'زمرہ';

  @override
  String get public => 'عوامی';

  @override
  String get failedToSaveCheckConnection => 'محفوظ کرنے میں ناکام۔ براہ کرم اپنے کنکشن کی جانچ کریں۔';

  @override
  String get createMemory => 'یاد بنائیں';

  @override
  String get deleteMemoryConfirmation => 'کیا آپ اس یاد کو حذف کرنا چاہتے ہیں؟ یہ کارروائی واپس نہیں کی جا سکتی۔';

  @override
  String get makePrivate => 'نجی بنائیں';

  @override
  String get organizeAndControlMemories => 'اپنی یادوں کو منظم اور کنٹرول کریں';

  @override
  String get total => 'کل';

  @override
  String get makeAllMemoriesPrivate => 'تمام یادوں کو نجی بنائیں';

  @override
  String get setAllMemoriesToPrivate => 'تمام یادوں کو نجی رویہ پر سیٹ کریں';

  @override
  String get makeAllMemoriesPublic => 'تمام یادوں کو عوامی بنائیں';

  @override
  String get setAllMemoriesToPublic => 'تمام یادوں کو عوامی رویہ پر سیٹ کریں';

  @override
  String get permanentlyRemoveAllMemories => 'Omi سے تمام یادوں کو مستقل طور پر ہٹائیں';

  @override
  String get allMemoriesAreNowPrivate => 'تمام یادیں اب نجی ہیں';

  @override
  String get allMemoriesAreNowPublic => 'تمام یادیں اب عوامی ہیں';

  @override
  String get clearOmisMemory => 'Omi کی یاد صاف کریں';

  @override
  String clearMemoryConfirmation(int count) {
    return 'کیا آپ Omi کی یاد صاف کرنا چاہتے ہیں؟ یہ کارروائی واپس نہیں کی جا سکتی اور تمام $count یادوں کو ہٹا دے گی۔';
  }

  @override
  String get omisMemoryCleared => 'Omi کی آپ کے بارے میں یاد صاف ہو گئی';

  @override
  String get welcomeToOmi => 'Omi میں خوش آمدید';

  @override
  String get continueWithApple => 'Apple کے ساتھ جاری رکھیں';

  @override
  String get continueWithGoogle => 'Google کے ساتھ جاری رکھیں';

  @override
  String get byContinuingYouAgree => 'جاری رکھنے سے آپ ہماری ';

  @override
  String get termsOfService => 'خدمات کی شرائط';

  @override
  String get and => ' اور ';

  @override
  String get dataAndPrivacy => 'ڈیٹا اور رازداری';

  @override
  String get secureAuthViaAppleId => 'Apple ID کے ذریعے محفوظ تصدیق';

  @override
  String get secureAuthViaGoogleAccount => 'Google اکاؤنٹ کے ذریعے محفوظ تصدیق';

  @override
  String get whatWeCollect => 'ہم کیا جمع کرتے ہیں';

  @override
  String get dataCollectionMessage =>
      'جاری رکھنے سے آپ کی بات چیت، ریکارڈنگز، اور ذاتی معلومات ہماری سرورز پر محفوظ طریقے سے محفوظ ہوں گی تاکہ AI کی طاقتور بصیرت فراہم کی جا سکے اور تمام ایپ کی خصوصیات فعال ہوں۔';

  @override
  String get dataProtection => 'ڈیٹا کی حفاظت';

  @override
  String get yourDataIsProtected => 'آپ کا ڈیٹا محفوظ ہے اور ہماری ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'براہ کرم اپنی بنیادی زبان منتخب کریں';

  @override
  String get chooseYourLanguage => 'اپنی زبان منتخب کریں';

  @override
  String get selectPreferredLanguageForBestExperience => 'بہترین Omi تجربے کے لیے اپنی پسندیدہ زبان منتخب کریں';

  @override
  String get searchLanguages => 'زبانوں میں تلاش کریں...';

  @override
  String get selectALanguage => 'کوئی زبان منتخب کریں';

  @override
  String get tryDifferentSearchTerm => 'کوئی مختلف تلاش کی اصطلاح آزمائیں';

  @override
  String get pleaseEnterYourName => 'براہ کرم اپنا نام درج کریں';

  @override
  String get nameMustBeAtLeast2Characters => 'نام میں کم از کم 2 حروف ہونے چاہیں';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'ہمیں بتائیں کہ آپ کو کیسے پکارا جائے۔ یہ آپ کے Omi تجربے کو ذاتی نوعیت سے تبدیل کرنے میں مدد کرتا ہے۔';

  @override
  String charactersCount(int count) {
    return '$count حروف';
  }

  @override
  String get enableFeaturesForBestExperience => 'اپنے ڈیوائس پر بہترین Omi تجربے کے لیے خصوصیات فعال کریں۔';

  @override
  String get microphoneAccess => 'مائیکروفون کی رسائی';

  @override
  String get recordAudioConversations => 'آڈیو کی بات چیت ریکارڈ کریں';

  @override
  String get microphoneAccessDescription =>
      'Omi کو آپ کی بات چیت ریکارڈ کرنے اور نقول فراہم کرنے کے لیے مائیکروفون کی رسائی کی ضرورت ہے۔';

  @override
  String get screenRecording => 'اسکرین ریکارڈنگ';

  @override
  String get captureSystemAudioFromMeetings => 'میٹنگز سے سسٹم آڈیو کیپچر کریں';

  @override
  String get screenRecordingDescription =>
      'Omi کو اپنے براؤزر پر مبنی میٹنگز سے سسٹم آڈیو کیپچر کرنے کے لیے اسکرین ریکارڈنگ کی اجازت کی ضرورت ہے۔';

  @override
  String get accessibility => 'رسائی';

  @override
  String get detectBrowserBasedMeetings => 'براؤزر پر مبنی میٹنگز کا پتہ لگائیں';

  @override
  String get accessibilityDescription =>
      'Omi کو جب آپ اپنے براؤزر میں Zoom، Meet، یا Teams میٹنگز میں شامل ہوں تب ان کا پتہ لگانے کے لیے رسائی کی اجازت کی ضرورت ہے۔';

  @override
  String get pleaseWait => 'براہ کرم انتظار کریں...';

  @override
  String get joinTheCommunity => 'کمیونٹی میں شامل ہوں!';

  @override
  String get loadingProfile => 'پروفائل لوڈ ہو رہا ہے...';

  @override
  String get profileSettings => 'پروفائل کی ترتیبات';

  @override
  String get noEmailSet => 'کوئی ای میل سیٹ نہیں';

  @override
  String get userIdCopiedToClipboard => 'صارف ID کلپ بورڈ میں کاپی ہو گیا';

  @override
  String get yourInformation => 'آپ کی معلومات';

  @override
  String get setYourName => 'اپنا نام سیٹ کریں';

  @override
  String get changeYourName => 'اپنا نام تبدیل کریں';

  @override
  String get voiceAndPeople => 'آواز اور لوگ';

  @override
  String get teachOmiYourVoice => 'Omi کو اپنی آواز سکھائیں';

  @override
  String get tellOmiWhoSaidIt => 'Omi کو بتائیں کہ کس نے کہا ہے 🗣️';

  @override
  String get payment => 'ادائیگی';

  @override
  String get addOrChangeYourPaymentMethod => 'اپنا ادائیگی کا طریقہ شامل یا تبدیل کریں';

  @override
  String get preferences => 'ترجیحات';

  @override
  String get helpImproveOmiBySharing => 'Omi کو بہتر بنانے میں مدد کریں اور گمنام تجزیات کا ڈیٹا شیئر کریں';

  @override
  String get deleteAccount => 'اکاؤنٹ حذف کریں';

  @override
  String get deleteYourAccountAndAllData => 'اپنے اکاؤنٹ اور تمام ڈیٹا کو حذف کریں';

  @override
  String get clearLogs => 'لاگز صاف کریں';

  @override
  String get debugLogsCleared => 'ڈیبگ لاگز صاف کر دیے گئے';

  @override
  String get exportConversations => 'بات چیت برآمد کریں';

  @override
  String get exportAllConversationsToJson => 'اپنی تمام بات چیت کو JSON فائل میں برآمد کریں۔';

  @override
  String get conversationsExportStarted =>
      'بات چیت کی برآمدگی شروع ہو گئی۔ یہ کچھ سیکنڈ لے سکتا ہے، براہ کرم انتظار کریں۔';

  @override
  String get mcpDescription =>
      'Omi کو دوسری ایپلیکیشنز کے ساتھ جڑنے کے لیے تاکہ آپ اپنی یادوں اور بات چیت کو پڑھ، تلاش، اور منظم کر سکیں۔ شروعات کرنے کے لیے کلید بنائیں۔';

  @override
  String get apiKeys => 'API کلیدیں';

  @override
  String errorLabel(String error) {
    return 'خرابی: $error';
  }

  @override
  String get noApiKeysFound => 'کوئی API کلیدیں نہیں ملیں۔ شروعات کرنے کے لیے کوئی بنائیں۔';

  @override
  String get advancedSettings => 'اعلیٰ ترتیبات';

  @override
  String get triggersWhenNewConversationCreated => 'جب نئی بات چیت بنائی جائے تو چلتا ہے۔';

  @override
  String get triggersWhenNewTranscriptReceived => 'جب نئی نقل موصول ہو تو چلتا ہے۔';

  @override
  String get realtimeAudioBytes => 'حقیقی وقت میں آڈیو بائٹس';

  @override
  String get triggersWhenAudioBytesReceived => 'جب آڈیو بائٹس موصول ہوں تو چلتا ہے۔';

  @override
  String get everyXSeconds => 'ہر x سیکنڈ';

  @override
  String get triggersWhenDaySummaryGenerated => 'جب دن کا خلاصہ بنایا جائے تو چلتا ہے۔';

  @override
  String get tryLatestExperimentalFeatures => 'Omi ٹیم کی تازہ ترین آزمائشی خصوصیات آزمائیں۔';

  @override
  String get transcriptionServiceDiagnosticStatus => 'نقل کی خدمت کی تشخیصی حالت';

  @override
  String get enableDetailedDiagnosticMessages => 'نقل کی خدمت سے تفصیلی تشخیصی پیغام فعال کریں';

  @override
  String get autoCreateAndTagNewSpeakers => 'نے مقررین کو خودکار طور پر بنائیں اور ٹیگ کریں';

  @override
  String get automaticallyCreateNewPerson => 'جب نام نقل میں معلوم ہو تو خودکار طور پر نیا شخص بنائیں۔';

  @override
  String get pilotFeatures => 'ٹیسٹ کی خصوصیات';

  @override
  String get pilotFeaturesDescription => 'یہ خصوصیات ٹیسٹ ہیں اور کوئی معاونت کی ضمانت نہیں ہے۔';

  @override
  String get suggestFollowUpQuestion => 'فالو اپ سوال تجویز کریں';

  @override
  String get saveSettings => 'ترتیبات محفوظ کریں';

  @override
  String get syncingDeveloperSettings => 'ڈیولپر کی ترتیبات کو ہم آہنگ کیا جا رہا ہے...';

  @override
  String get summary => 'خلاصہ';

  @override
  String get auto => 'خودکار';

  @override
  String get noSummaryForApp => 'اس ایپ کے لیے کوئی خلاصہ دستیاب نہیں۔ بہتر نتائج کے لیے کوئی اور ایپ آزمائیں۔';

  @override
  String get tryAnotherApp => 'کوئی اور ایپ آزمائیں';

  @override
  String generatedBy(String appName) {
    return '$appName نے بنایا ہوا';
  }

  @override
  String get overview => 'جائزہ';

  @override
  String get otherAppResults => 'دوسری ایپ کے نتائج';

  @override
  String get unknownApp => 'نامعلوم ایپ';

  @override
  String get noSummaryAvailable => 'کوئی خلاصہ دستیاب نہیں';

  @override
  String get conversationNoSummaryYet => 'اس بات چیت کے لیے ابھی کوئی خلاصہ نہیں۔';

  @override
  String get chooseSummarizationApp => 'خلاصہ کرنے والی ایپ منتخب کریں';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName کو ڈیفالٹ خلاصہ کرنے والی ایپ کے طور پر سیٹ کیا گیا';
  }

  @override
  String get letOmiChooseAutomatically => 'Omi کو بہترین ایپ خودکار طور پر منتخب کرنے دیں';

  @override
  String get deleteConversationConfirmation =>
      'کیا آپ واقعی یہ بات چیت حذف کرنا چاہتے ہیں؟ یہ کارنامہ واپس نہیں ہو سکتا۔';

  @override
  String get conversationDeleted => 'بات چیت حذف ہو گئی';

  @override
  String get generatingLink => 'لنک بنایا جا رہا ہے...';

  @override
  String get editConversation => 'بات چیت میں ترمیم کریں';

  @override
  String get conversationLinkCopiedToClipboard => 'بات چیت کا لنک کلپ بورڈ میں کاپی ہو گیا';

  @override
  String get conversationTranscriptCopiedToClipboard => 'بات چیت کی نقل کلپ بورڈ میں کاپی ہو گئی';

  @override
  String get editConversationDialogTitle => 'بات چیت میں ترمیم کریں';

  @override
  String get changeTheConversationTitle => 'بات چیت کے عنوان کو تبدیل کریں';

  @override
  String get conversationTitle => 'بات چیت کا عنوان';

  @override
  String get enterConversationTitle => 'بات چیت کا عنوان درج کریں...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'بات چیت کا عنوان کامیابی سے اپ ڈیٹ ہو گیا';

  @override
  String get failedToUpdateConversationTitle => 'بات چیت کے عنوان کو اپ ڈیٹ کرنا ناکام';

  @override
  String get errorUpdatingConversationTitle => 'بات چیت کے عنوان کو اپ ڈیٹ کرتے ہوئے خرابی';

  @override
  String get settingUp => 'ترتیب دی جا رہی ہے...';

  @override
  String get startYourFirstRecording => 'اپنی پہلی ریکارڈنگ شروع کریں';

  @override
  String get preparingSystemAudioCapture => 'سسٹم آڈیو کیپچر کی تیاری ہو رہی ہے';

  @override
  String get clickTheButtonToCaptureAudio =>
      'براہ راست نقول، AI کی بصیرت، اور خودکار بچت کے لیے آڈیو کیپچر کرنے کے لیے بٹن پر کلک کریں۔';

  @override
  String get reconnecting => 'دوبارہ جڑ رہے ہیں...';

  @override
  String get recordingPaused => 'ریکارڈنگ موقوف';

  @override
  String get recordingActive => 'ریکارڈنگ فعال';

  @override
  String get startRecording => 'ریکارڈنگ شروع کریں';

  @override
  String resumingInCountdown(String countdown) {
    return '${countdown}s میں دوبارہ شروع ہو رہا ہے...';
  }

  @override
  String get tapPlayToResume => 'دوبارہ شروع کرنے کے لیے پلے پر ٹیپ کریں';

  @override
  String get listeningForAudio => 'آڈیو سن رہا ہے...';

  @override
  String get preparingAudioCapture => 'آڈیو کیپچر کی تیاری ہو رہی ہے';

  @override
  String get clickToBeginRecording => 'ریکارڈنگ شروع کرنے کے لیے کلک کریں';

  @override
  String get translated => 'ترجمہ شدہ';

  @override
  String get liveTranscript => 'براہ راست نقل';

  @override
  String segmentsSingular(String count) {
    return '$count حصہ';
  }

  @override
  String segmentsPlural(String count) {
    return '$count حصے';
  }

  @override
  String get startRecordingToSeeTranscript => 'براہ راست نقل دیکھنے کے لیے ریکارڈنگ شروع کریں';

  @override
  String get paused => 'موقوف';

  @override
  String get initializing => 'شروع کیا جا رہا ہے...';

  @override
  String get recording => 'ریکارڈنگ';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'مائیکروفون تبدیل ہو گیا۔ ${countdown}s میں دوبارہ شروع ہو رہا ہے';
  }

  @override
  String get clickPlayToResumeOrStop => 'دوبارہ شروع کرنے یا ختم کرنے کے لیے پلے پر کلک کریں';

  @override
  String get settingUpSystemAudioCapture => 'سسٹم آڈیو کیپچر ترتیب دی جا رہی ہے';

  @override
  String get capturingAudioAndGeneratingTranscript => 'آڈیو کیپچر اور نقل بنائی جا رہی ہے';

  @override
  String get clickToBeginRecordingSystemAudio => 'سسٹم آڈیو ریکارڈ کرنا شروع کرنے کے لیے کلک کریں';

  @override
  String get you => 'آپ';

  @override
  String speakerWithId(String speakerId) {
    return 'مقرر $speakerId';
  }

  @override
  String get translatedByOmi => 'omi نے ترجمہ کیا ہوا';

  @override
  String get backToConversations => 'بات چیت پر واپس جائیں';

  @override
  String get systemAudio => 'نظام';

  @override
  String get mic => 'مائیک';

  @override
  String audioInputSetTo(String deviceName) {
    return 'آڈیو ان پٹ $deviceName پر سیٹ ہے';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'آڈیو ڈیوائس سوئچ کرتے ہوئے خرابی: $error';
  }

  @override
  String get selectAudioInput => 'آڈیو ان پٹ منتخب کریں';

  @override
  String get loadingDevices => 'ڈیوائسز لوڈ ہو رہے ہیں...';

  @override
  String get settingsHeader => 'ترتیبات';

  @override
  String get plansAndBilling => 'منصوبے اور بلنگ';

  @override
  String get calendarIntegration => 'کیلنڈر کا انضمام';

  @override
  String get dailySummary => 'روزانہ کا خلاصہ';

  @override
  String get developer => 'ڈیولپر';

  @override
  String get about => 'کے بارے میں';

  @override
  String get selectTime => 'وقت منتخب کریں';

  @override
  String get accountGroup => 'اکاؤنٹ';

  @override
  String get signOutQuestion => 'سائن آؤٹ کریں؟';

  @override
  String get signOutConfirmation => 'کیا آپ واقعی سائن آؤٹ کرنا چاہتے ہیں؟';

  @override
  String get customVocabularyHeader => 'اپنی زبان';

  @override
  String get addWordsDescription => 'وہ الفاظ شامل کریں جن کو Omi نقل کے دوران تسلیم کرے۔';

  @override
  String get enterWordsHint => 'الفاظ درج کریں (کوما سے الگ)';

  @override
  String get dailySummaryHeader => 'روزانہ کا خلاصہ';

  @override
  String get dailySummaryTitle => 'روزانہ کا خلاصہ';

  @override
  String get dailySummaryDescription => 'اپنے دن کی بات چیت کا ایک ذاتی خلاصہ حاصل کریں جو اطلاع کے طور پر پہنچے۔';

  @override
  String get deliveryTime => 'ترسیل کا وقت';

  @override
  String get deliveryTimeDescription => 'اپنا روزانہ کا خلاصہ کب حاصل کریں';

  @override
  String get subscription => 'رکنیت';

  @override
  String get viewPlansAndUsage => 'منصوبوں اور استعمال کو دیکھیں';

  @override
  String get viewPlansDescription => 'اپنی رکنیت کو منظم کریں اور استعمال کے اعدادوشمار دیکھیں';

  @override
  String get addOrChangePaymentMethod => 'اپنا ادائیگی کا طریقہ شامل یا تبدیل کریں';

  @override
  String get displayOptions => 'نمائش کے اختیارات';

  @override
  String get showMeetingsInMenuBar => 'مینو بار میں میٹنگز دکھائیں';

  @override
  String get displayUpcomingMeetingsDescription => 'مینو بار میں آنے والی میٹنگز دکھائیں';

  @override
  String get showEventsWithoutParticipants => 'بغیر شرکاء کے ایونٹس دکھائیں';

  @override
  String get includePersonalEventsDescription => 'کوئی شرکاء نہیں کے ساتھ ذاتی ایونٹس شامل کریں';

  @override
  String get upcomingMeetings => 'آنے والی میٹنگز';

  @override
  String get checkingNext7Days => 'اگلے 7 دن کی جانچ کی جا رہی ہے';

  @override
  String get shortcuts => 'شارٹ کٹس';

  @override
  String get shortcutChangeInstruction =>
      'شارٹ کٹ کو تبدیل کرنے کے لیے اس پر کلک کریں۔ منسوخ کرنے کے لیے Escape دبائیں۔';

  @override
  String get configureSTTProvider => 'STT فراہم کنندہ کو ترتیب دیں';

  @override
  String get setConversationEndDescription => 'سیٹ کریں کہ بات چیت کب خود ختم ہو';

  @override
  String get importDataDescription => 'دوسری جگہوں سے ڈیٹا درآمد کریں';

  @override
  String get exportConversationsDescription => 'JSON میں بات چیت برآمد کریں';

  @override
  String get exportingConversations => 'بات چیت برآمد کی جا رہی ہے...';

  @override
  String get clearNodesDescription => 'تمام نوڈس اور تعلقات صاف کریں';

  @override
  String get deleteKnowledgeGraphQuestion => 'علم کا گراف حذف کریں؟';

  @override
  String get deleteKnowledgeGraphWarning =>
      'یہ تمام حاصل شدہ علم کے گراف کو حذف کرے گا۔ آپ کی اصل یادیں محفوظ رہیں گی۔';

  @override
  String get connectOmiWithAI => 'Omi کو AI معاونین کے ساتھ جوڑیں';

  @override
  String get noAPIKeys => 'کوئی API کلیدیں نہیں۔ شروعات کرنے کے لیے کوئی بنائیں۔';

  @override
  String get autoCreateWhenDetected => 'جب نام پایا جائے تو خود بنائیں';

  @override
  String get trackPersonalGoals => 'ہوم پیج پر ذاتی اہداف کو ٹریک کریں';

  @override
  String get endpointURL => 'اختتام پوائنٹ URL';

  @override
  String get links => 'لنکس';

  @override
  String get discordMemberCount => 'Discord پر 8000+ اراکین';

  @override
  String get userInformation => 'صارف کی معلومات';

  @override
  String get capabilities => 'صلاحیتیں';

  @override
  String get previewScreenshots => 'پریویو اسکرین شاٹس';

  @override
  String get holdOnPreparingForm => 'رکیں، ہم آپ کے لیے فارم تیار کر رہے ہیں';

  @override
  String get bySubmittingYouAgreeToOmi => 'جمع کرتے ہوئے آپ Omi ';

  @override
  String get termsAndPrivacyPolicy => 'شرائط اور رازداری کی پالیسی';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'مسائل کی تشخیص میں مدد کرتا ہے۔ 3 دن بعد خود حذف ہو جاتا ہے۔';

  @override
  String get manageYourApp => 'اپنی ایپ کو منظم کریں';

  @override
  String get updatingYourApp => 'آپ کی ایپ اپ ڈیٹ ہو رہی ہے';

  @override
  String get fetchingYourAppDetails => 'آپ کی ایپ کی تفصیلات حاصل کی جا رہی ہیں';

  @override
  String get updateAppQuestion => 'ایپ اپ ڈیٹ کریں؟';

  @override
  String get updateAppConfirmation =>
      'کیا آپ واقعی اپنی ایپ اپ ڈیٹ کرنا چاہتے ہیں؟ ہماری ٹیم کے نقطہ نظر سے تبدیلیاں نظر آئیں گی۔';

  @override
  String get updateApp => 'ایپ اپ ڈیٹ کریں';

  @override
  String get createAndSubmitNewApp => 'نئی ایپ بنائیں اور جمع کریں';

  @override
  String appsCount(String count) {
    return 'ایپس ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'نجی ایپس ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'عوامی ایپس ($count)';
  }

  @override
  String get newVersionAvailable => 'نیا ورژن دستیاب ہے 🎉';

  @override
  String get no => 'نہیں';

  @override
  String get subscriptionCancelledSuccessfully =>
      'رکنیت کامیابی سے منسوخ کر دی گئی۔ یہ موجودہ بلنگ مدت کے اختتام تک فعال رہے گی۔';

  @override
  String get failedToCancelSubscription => 'رکنیت منسوخ کرنا ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get invalidPaymentUrl => 'غلط ادائیگی URL';

  @override
  String get permissionsAndTriggers => 'اجازتیں اور ٹریگرز';

  @override
  String get chatFeatures => 'بات چیت کی خصوصیات';

  @override
  String get uninstall => 'ہٹائیں';

  @override
  String get installs => 'انسٹالیشنز';

  @override
  String get priceLabel => 'قیمت';

  @override
  String get updatedLabel => 'اپ ڈیٹ شدہ';

  @override
  String get createdLabel => 'بنایا گیا';

  @override
  String get featuredLabel => 'نمایاں';

  @override
  String get cancelSubscriptionQuestion => 'رکنیت منسوخ کریں؟';

  @override
  String get cancelSubscriptionConfirmation =>
      'کیا آپ واقعی اپنی رکنیت منسوخ کرنا چاہتے ہیں؟ آپ اپنی موجودہ بلنگ مدت کے اختتام تک رسائی میں رہیں گے۔';

  @override
  String get cancelSubscriptionButton => 'رکنیت منسوخ کریں';

  @override
  String get cancelling => 'منسوخ کیا جا رہا ہے...';

  @override
  String get betaTesterMessage =>
      'آپ اس ایپ کے بیٹا ٹیسٹر ہیں۔ ابھی یہ عوامی نہیں ہے۔ منظوری کے بعد یہ عوامی ہو جائے گی۔';

  @override
  String get appUnderReviewMessage =>
      'آپ کی ایپ جائزہ میں ہے اور صرف آپ کو نظر آتی ہے۔ منظوری کے بعد یہ عوامی ہو جائے گی۔';

  @override
  String get appRejectedMessage =>
      'آپ کی ایپ مسترد کر دی گئی ہے۔ براہ کرم ایپ کی تفصیلات اپ ڈیٹ کریں اور دوبارہ جائزہ کے لیے جمع کریں۔';

  @override
  String get invalidIntegrationUrl => 'غلط انضمام URL';

  @override
  String get tapToComplete => 'مکمل کرنے کے لیے ٹیپ کریں';

  @override
  String get invalidSetupInstructionsUrl => 'غلط ترتیب کی ہدایات URL';

  @override
  String get pushToTalk => 'بات کرنے کے لیے دبائیں';

  @override
  String get summaryPrompt => 'خلاصہ سوال';

  @override
  String get pleaseSelectARating => 'براہ کرم کوئی درجہ بندی منتخب کریں';

  @override
  String get reviewAddedSuccessfully => 'جائزہ کامیابی سے شامل کیا گیا 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'جائزہ کامیابی سے اپ ڈیٹ کیا گیا 🚀';

  @override
  String get failedToSubmitReview => 'جائزہ جمع کرنا ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get addYourReview => 'اپنا جائزہ شامل کریں';

  @override
  String get editYourReview => 'اپنا جائزہ میں ترمیم کریں';

  @override
  String get writeAReviewOptional => 'جائزہ لکھیں (اختیاری)';

  @override
  String get submitReview => 'جائزہ جمع کریں';

  @override
  String get updateReview => 'جائزہ اپ ڈیٹ کریں';

  @override
  String get yourReview => 'آپ کا جائزہ';

  @override
  String get anonymousUser => 'نام نہاد صارف';

  @override
  String get issueActivatingApp => 'اس ایپ کو فعال کرنے میں مسئلہ ہوا۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get dataAccessNoticeDescription =>
      'یہ ایپ آپ کے ڈیٹا تک رسائی حاصل کرے گی۔ Omi AI اس بات کے لیے ذمہ دار نہیں کہ آپ کا ڈیٹا اس ایپ نے کیسے استعمال، تبدیل یا حذف کیا ہے';

  @override
  String get copyUrl => 'URL کاپی کریں';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'سوموار';

  @override
  String get weekdayTue => 'منگل';

  @override
  String get weekdayWed => 'بدھ';

  @override
  String get weekdayThu => 'جمعرات';

  @override
  String get weekdayFri => 'جمعہ';

  @override
  String get weekdaySat => 'ہفتہ';

  @override
  String get weekdaySun => 'اتوار';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName انضمام جلد آنے والا ہے';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'پہلے سے $platform میں برآمد ہو چکا ہے';
  }

  @override
  String get anotherPlatform => 'دوسرا پلیٹ فارم';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'براہ کرم ترتیبات میں $serviceName کے ساتھ تصدیق کریں > کام کے انضمام';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceName میں شامل کیا جا رہا ہے...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceName میں شامل کیا گیا';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceName میں شامل کرنا ناکام';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple Reminders کے لیے اجازت مسترد کر دی گئی';

  @override
  String failedToCreateApiKey(String error) {
    return 'فراہم کنندہ API کلید بنانا ناکام: $error';
  }

  @override
  String get createAKey => 'کلید بنائیں';

  @override
  String get apiKeyRevokedSuccessfully => 'API کلید کامیابی سے منسوخ کر دی گئی';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API کلید منسوخ کرنا ناکام: $error';
  }

  @override
  String get omiApiKeys => 'Omi API کلیدیں';

  @override
  String get apiKeysDescription =>
      'API کلیدیں تصدیق کے لیے استعمال ہوتی ہیں جب آپ کی ایپ OMI سرور سے بات کرے۔ یہ آپ کی ایپ کو یادوں بنانے اور دوسری OMI خدمات تک محفوظ طریقے سے رسائی حاصل کرنے دیتی ہے۔';

  @override
  String get aboutOmiApiKeys => 'Omi API کلیدوں کے بارے میں';

  @override
  String get yourNewKey => 'آپ کی نئی کلید:';

  @override
  String get copyToClipboard => 'کلپ بورڈ میں کاپی کریں';

  @override
  String get pleaseCopyKeyNow => 'براہ کرم اسے اب کاپی کریں اور کسی محفوظ جگہ لکھ لیں۔ ';

  @override
  String get willNotSeeAgain => 'آپ اسے دوبارہ نہیں دیکھ سکیں گے۔';

  @override
  String get revokeKey => 'کلید منسوخ کریں';

  @override
  String get revokeApiKeyQuestion => 'API کلید منسوخ کریں؟';

  @override
  String get revokeApiKeyWarning =>
      'یہ کارنامہ واپس نہیں ہو سکتا۔ اس کلید کو استعمال کرنے والی کوئی بھی ایپلیکیشنز اب API تک رسائی نہیں کر سکیں گی۔';

  @override
  String get revoke => 'منسوخ کریں';

  @override
  String get whatWouldYouLikeToCreate => 'آپ کیا بنانا چاہتے ہیں؟';

  @override
  String get createAnApp => 'ایپ بنائیں';

  @override
  String get createAndShareYourApp => 'اپنی ایپ بنائیں اور شیئر کریں';

  @override
  String get itemApp => 'ایپ';

  @override
  String keepItemPublic(String item) {
    return '$item کو عوامی رکھیں';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item کو عوامی بنائیں؟';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item کو نجی بنائیں؟';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'اگر آپ $item کو عوامی بناتے ہیں تو یہ سب کی طرف سے استعمال کیا جا سکتا ہے';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'اگر آپ $item کو ابھی نجی بناتے ہیں تو یہ سب کے لیے کام کرنا بند کر دے گا اور صرف آپ کو نظر آئے گا';
  }

  @override
  String get manageApp => 'ایپ کا انتظام کریں';

  @override
  String deleteItemTitle(String item) {
    return '$item حذف کریں';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item حذف کریں؟';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'کیا آپ واقعی یہ $item حذف کرنا چاہتے ہیں؟ یہ کارنامہ واپس نہیں ہو سکتا۔';
  }

  @override
  String get revokeKeyQuestion => 'کلید منسوخ کریں؟';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'کیا آپ واقعی کلید \"$keyName\" منسوخ کرنا چاہتے ہیں؟ یہ کارنامہ واپس نہیں ہو سکتا۔';
  }

  @override
  String get createNewKey => 'نئی کلید بنائیں';

  @override
  String get keyNameHint => 'مثال کے طور پر Claude Desktop';

  @override
  String get pleaseEnterAName => 'براہ کرم نام درج کریں۔';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'کلید بنانا ناکام: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'کلید بنانا ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get keyCreated => 'کلید بنائی گئی';

  @override
  String get keyCreatedMessage =>
      'آپ کی نئی کلید بنا دی گئی ہے۔ براہ کرم اسے اب کاپی کریں۔ آپ اسے دوبارہ نہیں دیکھ سکیں گے۔';

  @override
  String get keyWord => 'کلید';

  @override
  String get externalAppAccess => 'بیرونی ایپ کی رسائی';

  @override
  String get externalAppAccessDescription =>
      'مندرجہ ذیل انسٹال شدہ ایپس میں بیرونی انضمام ہے اور آپ کے ڈیٹا تک رسائی حاصل کر سکتے ہیں، جیسے بات چیت اور یادیں۔';

  @override
  String get noExternalAppsHaveAccess => 'کوئی بیرونی ایپ آپ کے ڈیٹا تک رسائی نہیں کر سکتی۔';

  @override
  String get maximumSecurityE2ee => 'زیادہ سے زیادہ سیکیورٹی (E2EE)';

  @override
  String get e2eeDescription =>
      'اختتام سے اختتام تک مشفر کاری رازداری کا سونے کا معیار ہے۔ جب فعال ہو تو آپ کا ڈیٹا آپ کے ڈیوائس پر مشفر ہو جاتا ہے اس سے پہلے کہ یہ ہماری سرورز پر بھیجا جائے۔ اس کا مطلب یہ ہے کہ کوئی بھی، یہاں تک کہ Omi، آپ کے مواد تک رسائی حاصل نہیں کر سکتا۔';

  @override
  String get importantTradeoffs => 'اہم تبادلے:';

  @override
  String get e2eeTradeoff1 => '• کچھ خصوصیات جیسے بیرونی ایپ انضمام غیر فعال ہو سکتے ہیں۔';

  @override
  String get e2eeTradeoff2 => '• اگر آپ اپنا پاس ورڈ بھول جاتے ہیں تو آپ کا ڈیٹا بحال نہیں ہو سکتا۔';

  @override
  String get featureComingSoon => 'یہ خصوصیت جلد آنے والی ہے!';

  @override
  String get migrationInProgressMessage => 'منتقلی جاری ہے۔ آپ اسے مکمل ہونے تک حفاظت کی سطح تبدیل نہیں کر سکتے۔';

  @override
  String get migrationFailed => 'منتقلی ناکام';

  @override
  String migratingFromTo(String source, String target) {
    return '$source سے $target میں منتقل کیا جا رہا ہے';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total اشیاء';
  }

  @override
  String get secureEncryption => 'محفوظ مشفر کاری';

  @override
  String get secureEncryptionDescription =>
      'آپ کا ڈیٹا ہماری سرورز پر آپ کے لیے منفرد کلید کے ساتھ مشفر ہے، Google Cloud پر میزبان ہے۔ اس کا مطلب یہ ہے کہ آپ کا خام مواد ڈیٹا بیس سے براہ راست کسی کے لیے بھی رسائی سے دور ہے، بشمول Omi اسٹاف یا Google۔';

  @override
  String get endToEndEncryption => 'اختتام سے اختتام تک مشفر کاری';

  @override
  String get e2eeCardDescription =>
      'زیادہ سے زیادہ سیکیورٹی کے لیے فعال کریں جہاں صرف آپ اپنے ڈیٹا تک رسائی حاصل کر سکتے ہوں۔ مزید جاننے کے لیے ٹیپ کریں۔';

  @override
  String get dataAlwaysEncrypted => 'سطح کے قطع نظر، آپ کا ڈیٹا ہمیشہ باقی اور ترسیل میں مشفر ہوتا ہے۔';

  @override
  String get readOnlyScope => 'صرف پڑھیں';

  @override
  String get fullAccessScope => 'مکمل رسائی';

  @override
  String get readScope => 'پڑھیں';

  @override
  String get writeScope => 'لکھیں';

  @override
  String get apiKeyCreated => 'API کلید بنائی گئی!';

  @override
  String get saveKeyWarning => 'یہ کلید ابھی محفوظ کریں! آپ اسے دوبارہ نہیں دیکھ سکیں گے۔';

  @override
  String get yourApiKey => 'آپ کی API کلید';

  @override
  String get tapToCopy => 'کاپی کرنے کے لیے ٹیپ کریں';

  @override
  String get copyKey => 'کلید کاپی کریں';

  @override
  String get createApiKey => 'API کلید بنائیں';

  @override
  String get accessDataProgrammatically => 'اپنے ڈیٹا تک بروگرام سے رسائی حاصل کریں';

  @override
  String get keyNameLabel => 'کلید کا نام';

  @override
  String get keyNamePlaceholder => 'مثال کے طور پر میری ایپ کا انضمام';

  @override
  String get permissionsLabel => 'اجازتیں';

  @override
  String get permissionsInfoNote => 'R = پڑھیں، W = لکھیں۔ اگر کوئی بھی منتخب نہیں ہو تو صرف پڑھیں پر ڈیفالٹ۔';

  @override
  String get developerApi => 'ڈیولپر API';

  @override
  String get createAKeyToGetStarted => 'شروعات کرنے کے لیے کلید بنائیں';

  @override
  String errorWithMessage(String error) {
    return 'خرابی: $error';
  }

  @override
  String get omiTraining => 'Omi تربیت';

  @override
  String get trainingDataProgram => 'تربیت کا ڈیٹا پروگرام';

  @override
  String get getOmiUnlimitedFree => 'اپنے ڈیٹا کو AI ماڈلز کی تربیت کے لیے شراکت کر کے Omi Unlimited مفت حاصل کریں۔';

  @override
  String get trainingDataBullets =>
      '• آپ کا ڈیٹا AI ماڈلز کو بہتر بنانے میں مدد کرتا ہے\n• صرف غیر حساس ڈیٹا شیئر کیا جاتا ہے\n• مکمل طور پر شفاف عمل';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training پر مزید جانیں';

  @override
  String get agreeToContributeData => 'میں سمجھتا ہوں اور AI تربیت کے لیے اپنے ڈیٹا میں شراکت کے لیے اتفاق کرتا ہوں';

  @override
  String get submitRequest => 'درخواست جمع کریں';

  @override
  String get thankYouRequestUnderReview => 'شکریہ! آپ کی درخواست جائزہ میں ہے۔ منظوری کے بعد ہم آپ کو مطلع کریں گے۔';

  @override
  String planRemainsActiveUntil(String date) {
    return 'آپ کا منصوبہ $date تک فعال رہے گا۔ اس کے بعد آپ اپنی لامحدود خصوصیات تک رسائی سے محروم ہو جائیں گے۔ کیا آپ یقینی ہیں؟';
  }

  @override
  String get confirmCancellation => 'منسوخ کرنے کی تصدیق کریں';

  @override
  String get keepMyPlan => 'اپنے منصوبے کو رکھیں';

  @override
  String get subscriptionSetToCancel => 'آپ کی رکنیت مدت کے اختتام پر منسوخ ہونے کے لیے سیٹ ہے۔';

  @override
  String get switchedToOnDevice => 'آن ڈیوائس نقل میں تبدیل ہو گیا';

  @override
  String get couldNotSwitchToFreePlan => 'مفت منصوبہ پر منتقل نہیں ہو سکے۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get couldNotLoadPlans => 'دستیاب منصوبے لوڈ نہیں ہو سکے۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get selectedPlanNotAvailable => 'منتخب منصوبہ دستیاب نہیں ہے۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get upgradeToAnnualPlan => 'سالانہ منصوبے میں اپ گریڈ کریں';

  @override
  String get importantBillingInfo => 'اہم بلنگ کی معلومات:';

  @override
  String get monthlyPlanContinues => 'آپ کا موجودہ ماہانہ منصوبہ آپ کی بلنگ مدت کے اختتام تک جاری رہے گا';

  @override
  String get paymentMethodCharged =>
      'آپ کے موجودہ ادائیگی کے طریقے سے خود کار طریقے سے چارج کیا جائے گا جب آپ کا ماہانہ منصوبہ ختم ہوگا';

  @override
  String get annualSubscriptionStarts => 'آپ کی 12 ماہ کی سالانہ رکنیت خود کار طریقے سے چارج کے بعد شروع ہوگی';

  @override
  String get thirteenMonthsCoverage => 'آپ کو کل 13 ماہ کا احاطہ ملے گا (موجودہ ماہ + 12 ماہ سالانہ)';

  @override
  String get confirmUpgrade => 'اپ گریڈ کی تصدیق کریں';

  @override
  String get confirmPlanChange => 'منصوبہ کی تبدیلی کی تصدیق کریں';

  @override
  String get confirmAndProceed => 'تصدیق کریں اور آگے بڑھیں';

  @override
  String get upgradeScheduled => 'اپ گریڈ طے شدہ ہے';

  @override
  String get changePlan => 'منصوبہ تبدیل کریں';

  @override
  String get upgradeAlreadyScheduled => 'سالانہ منصوبے میں آپ کی اپ گریڈ پہلے سے طے شدہ ہے';

  @override
  String get youAreOnUnlimitedPlan => 'آپ لامحدود منصوبے پر ہیں۔';

  @override
  String get yourOmiUnleashed => 'آپ کا Omi، بیکل ہو گیا۔ لامحدود کے لیے جائیں لامحدود امکانات کے لیے۔';

  @override
  String planEndedOn(String date) {
    return 'آپ کا منصوبہ $date کو ختم ہو گیا۔\nاب دوبارہ رکنیت حاصل کریں - نیا بلنگ مدت کے لیے فوری طور پر چارج کیا جائے گا۔';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'آپ کا منصوبہ $date کو منسوخ ہونے کے لیے طے شدہ ہے۔\nاپنے فوائل کو برقرار رکھنے کے لیے اب دوبارہ رکنیت حاصل کریں - $date تک کوئی چارج نہیں۔';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'آپ کی سالانہ رکنیت خود کار طریقے سے شروع ہوگی جب آپ کا ماہانہ منصوبہ ختم ہوگا۔';

  @override
  String planRenewsOn(String date) {
    return 'آپ کا منصوبہ $date کو تازہ ہوگا۔';
  }

  @override
  String get unlimitedConversations => 'لامحدود گفتگو';

  @override
  String get askOmiAnything => 'اپنی زندگی کے بارے میں Omi سے کچھ بھی پوچھیں';

  @override
  String get unlockOmiInfiniteMemory => 'Omi کی لامحدود یادوں کو کھولیں';

  @override
  String get youreOnAnnualPlan => 'آپ سالانہ منصوبے پر ہیں';

  @override
  String get alreadyBestValuePlan => 'آپ کے پاس پہلے سے بہترین قدر والا منصوبہ ہے۔ کوئی تبدیلی درکار نہیں۔';

  @override
  String get unableToLoadPlans => 'پلان لوڈ نہیں ہو سکے';

  @override
  String get checkConnectionTryAgain => 'کنکشن چیک کریں اور دوبارہ کوشش کریں';

  @override
  String get useFreePlan => 'مفت منصوبہ استعمال کریں';

  @override
  String get continueText => 'جاری رکھیں';

  @override
  String get resubscribe => 'دوبارہ رکنیت حاصل کریں';

  @override
  String get couldNotOpenPaymentSettings => 'ادائیگی کی ترتیبات نہیں کھول سکے۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get managePaymentMethod => 'ادائیگی کا طریقہ منظم کریں';

  @override
  String get cancelSubscription => 'رکنیت منسوخ کریں';

  @override
  String endsOnDate(String date) {
    return '$date کو ختم ہوتا ہے';
  }

  @override
  String get active => 'فعال';

  @override
  String get freePlan => 'مفت منصوبہ';

  @override
  String get configure => 'ترتیب دیں';

  @override
  String get privacyInformation => 'رازداری کی معلومات';

  @override
  String get yourPrivacyMattersToUs => 'آپ کی رازداری ہمارے لیے اہم ہے';

  @override
  String get privacyIntroText =>
      'Omi میں، ہم آپ کی رازداری کو بہت سنجیدگی سے لیتے ہیں۔ ہم ہماری جمع کردہ ڈیٹا اور اسے آپ کے لیے ہماری پروڈکٹ بہتر بنانے میں کیسے استعمال کرتے ہیں اس کے بارے میں شفاف رہنا چاہتے ہیں۔ یہاں وہ ہے جو آپ کو معلوم ہونے کی ضرورت ہے:';

  @override
  String get whatWeTrack => 'ہم کیا ٹریک کرتے ہیں';

  @override
  String get anonymityAndPrivacy => 'گمنامی اور رازداری';

  @override
  String get optInAndOptOutOptions => 'آپٹ ان اور آپٹ آؤٹ کے اختیارات';

  @override
  String get ourCommitment => 'ہماری پابندی';

  @override
  String get commitmentText =>
      'ہم ہماری جمع کردہ ڈیٹا کو صرف Omi کو آپ کے لیے بہتر پروڈکٹ بنانے کے لیے استعمال کرنے کے لیے پابند ہیں۔ آپ کی رازداری اور اعتماد ہمارے لیے سب سے اہم ہے۔';

  @override
  String get thankYouText =>
      'Omi کے قدری صارف ہونے کے لیے آپ کا شکریہ۔ اگر آپ کے کوئی سوالات یا خدشات ہیں تو براہ کرم ہم سے رابطہ کریں team@basedhardware.com۔';

  @override
  String get wifiSyncSettings => 'WiFi سنک کی ترتیبات';

  @override
  String get enterHotspotCredentials => 'اپنے فون کے ہاٹ اسپاٹ کی شناخت درج کریں';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi سنک آپ کے فون کو ہاٹ اسپاٹ کے طور پر استعمال کرتا ہے۔ ترتیبات میں اپنے ہاٹ اسپاٹ کا نام اور پاس ورڈ تلاش کریں > ذاتی ہاٹ اسپاٹ۔';

  @override
  String get hotspotNameSsid => 'ہاٹ اسپاٹ کا نام (SSID)';

  @override
  String get exampleIphoneHotspot => 'مثلاً iPhone کا ہاٹ اسپاٹ';

  @override
  String get password => 'پاس ورڈ';

  @override
  String get enterHotspotPassword => 'ہاٹ اسپاٹ پاس ورڈ درج کریں';

  @override
  String get saveCredentials => 'شناخت محفوظ کریں';

  @override
  String get clearCredentials => 'شناخت صاف کریں';

  @override
  String get pleaseEnterHotspotName => 'براہ کرم ہاٹ اسپاٹ کا نام درج کریں';

  @override
  String get wifiCredentialsSaved => 'WiFi کی شناخت محفوظ کی گئی';

  @override
  String get wifiCredentialsCleared => 'WiFi کی شناخت صاف کی گئی';

  @override
  String summaryGeneratedForDate(String date) {
    return '$date کے لیے خلاصہ تیار کیا گیا';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'خلاصہ تیار کرنے میں ناکام۔ یقینی بنائیں کہ آپ کے پاس اس دن کی گفتگو ہے۔';

  @override
  String get summaryNotFound => 'خلاصہ نہیں ملا';

  @override
  String get yourDaysJourney => 'آپ کے دن کا سفر';

  @override
  String get highlights => 'اہم نکات';

  @override
  String get unresolvedQuestions => 'حل نہ شدہ سوالات';

  @override
  String get decisions => 'فیصلے';

  @override
  String get learnings => 'سیکھیں';

  @override
  String get autoDeletesAfterThreeDays => '3 دن کے بعد خود کار طریقے سے حذف ہوتا ہے۔';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'علم کے گراف کو کامیابی سے حذف کیا گیا';

  @override
  String get exportStartedMayTakeFewSeconds => 'برآمدگی شروع ہو گئی۔ اس میں کچھ سیکنڈ لگ سکتے ہیں...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'اس سے تمام اخذ شدہ علم کے گراف ڈیٹا (نوڈس اور کنکشنز) حذف ہوں گے۔ آپ کی اصل یادیں محفوظ رہیں گی۔ گراف وقت کے ساتھ یا اگلی درخواست پر دوبارہ بنایا جائے گا۔';

  @override
  String get configureDailySummaryDigest => 'اپنے روزانہ کام کی چیزوں کا خلاصہ ترتیب دیں';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes تک رسائی حاصل کرتا ہے';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType سے متحرک ہے';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription اور $triggerDescription سے متحرک ہے۔';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription سے متحرک ہے۔';
  }

  @override
  String get noSpecificDataAccessConfigured => 'کوئی مخصوص ڈیٹا رسائی ترتیب نہیں دی گئی ہے۔';

  @override
  String get basicPlanDescription => '1,200 پریمیم منٹ + آن ڈیوائس پر لامحدود';

  @override
  String get minutes => 'منٹ';

  @override
  String get omiHas => 'Omi کے پاس ہے:';

  @override
  String get premiumMinutesUsed => 'پریمیم منٹ استعمال کیے گئے۔';

  @override
  String get setupOnDevice => 'آن ڈیوائس پر سیٹ اپ کریں';

  @override
  String get forUnlimitedFreeTranscription => 'لامحدود مفت ٹرانسکرپشن کے لیے۔';

  @override
  String premiumMinsLeft(int count) {
    return '$count پریمیم منٹ باقی رہے۔';
  }

  @override
  String get alwaysAvailable => 'ہمیشہ دستیاب۔';

  @override
  String get importHistory => 'درآمد کی تاریخ';

  @override
  String get noImportsYet => 'ابھی کوئی درآمد نہیں';

  @override
  String get selectZipFileToImport => 'درآمد کے لیے .zip فائل منتخب کریں!';

  @override
  String get otherDevicesComingSoon => 'دوسری ڈیوائسز جلد آئیں گی';

  @override
  String get deleteAllLimitlessConversations => 'تمام Limitless کی گفتگو حذف کریں؟';

  @override
  String get deleteAllLimitlessWarning =>
      'اس سے Limitless سے درآمد شدہ تمام گفتگو مستقل طور پر حذف ہوں گی۔ یہ عمل واپس نہیں کیا جا سکتا۔';

  @override
  String deletedLimitlessConversations(int count) {
    return '$count Limitless کی گفتگو حذف کی گئی';
  }

  @override
  String get failedToDeleteConversations => 'گفتگو حذف کرنے میں ناکام';

  @override
  String get deleteImportedData => 'درآمد شدہ ڈیٹا حذف کریں';

  @override
  String get statusPending => 'زیر التوا';

  @override
  String get statusProcessing => 'پروسیسنگ';

  @override
  String get statusCompleted => 'مکمل ہو گیا';

  @override
  String get statusFailed => 'ناکام';

  @override
  String nConversations(int count) {
    return '$count گفتگو';
  }

  @override
  String get pleaseEnterName => 'براہ کرم نام درج کریں';

  @override
  String get nameMustBeBetweenCharacters => 'نام 2 سے 40 حروف کے درمیان ہونا چاہیے';

  @override
  String get deleteSampleQuestion => 'نمونہ حذف کریں؟';

  @override
  String deleteSampleConfirmation(String name) {
    return 'کیا آپ واقی $name کا نمونہ حذف کرنا چاہتے ہیں؟';
  }

  @override
  String get confirmDeletion => 'حذف کرنے کی تصدیق کریں';

  @override
  String deletePersonConfirmation(String name) {
    return 'کیا آپ واقی $name کو حذف کرنا چاہتے ہیں؟ اس سے تمام متعلقہ صوتی نمونے بھی ہٹائے جائیں گے۔';
  }

  @override
  String get howItWorksTitle => 'یہ کیسے کام کرتا ہے؟';

  @override
  String get howPeopleWorks =>
      'ایک بار جب کوئی شخص بنایا جاتا ہے تو آپ کسی گفتگو کے ٹرانسکرپٹ پر جا سکتے ہیں اور انہیں ان کے متعلقہ حصے تفویض کر سکتے ہیں، اس طریقے سے Omi ان کی بھی تشخیص کرنے کے قابل ہوگا!';

  @override
  String get tapToDelete => 'حذف کرنے کے لیے ٹیپ کریں';

  @override
  String get newTag => 'نیا';

  @override
  String get needHelpChatWithUs => 'مدد درکار ہے؟ ہمارے ساتھ بات کریں';

  @override
  String get localStorageEnabled => 'مقامی اسٹوریج فعال کیا گیا';

  @override
  String get localStorageDisabled => 'مقامی اسٹوریج غیر فعال کیا گیا';

  @override
  String failedToUpdateSettings(String error) {
    return 'ترتیبات اپڈیٹ کرنے میں ناکام: $error';
  }

  @override
  String get privacyNotice => 'رازداری کی نوٹس';

  @override
  String get recordingsMayCaptureOthers =>
      'ریکارڈنگز دوسروں کی آوازیں پکڑ سکتی ہیں۔ فعال کرنے سے پہلے تمام شرکاء سے رضامندی یقینی بنائیں۔';

  @override
  String get enable => 'فعال کریں';

  @override
  String get storeAudioOnPhone => 'فون پر آڈیو محفوظ کریں';

  @override
  String get on => 'آن';

  @override
  String get storeAudioDescription =>
      'تمام آڈیو ریکارڈنگز اپنے فون پر مقامی طور پر محفوظ رکھیں۔ جب غیر فعال ہو تو اسٹوریج کی جگہ بچانے کے لیے صرف ناکام اپ لوڈز رکھے جاتے ہیں۔';

  @override
  String get enableLocalStorage => 'مقامی اسٹوریج فعال کریں';

  @override
  String get cloudStorageEnabled => 'کلاؤڈ اسٹوریج فعال کیا گیا';

  @override
  String get cloudStorageDisabled => 'کلاؤڈ اسٹوریج غیر فعال کیا گیا';

  @override
  String get enableCloudStorage => 'کلاؤڈ اسٹوریج فعال کریں';

  @override
  String get storeAudioOnCloud => 'کلاؤڈ پر آڈیو محفوظ کریں';

  @override
  String get cloudStorageDialogMessage =>
      'آپ کی حقیقی وقت کی ریکارڈنگز جیسے جیسے آپ بولتے ہیں نجی کلاؤڈ اسٹوریج میں محفوظ کی جائیں گی۔';

  @override
  String get storeAudioCloudDescription =>
      'اپنی حقیقی وقت کی ریکارڈنگز نجی کلاؤڈ اسٹوریج میں محفوظ کریں جیسے جیسے آپ بولتے ہیں۔ آڈیو حقیقی وقت میں محفوظ طریقے سے پکڑی اور محفوظ کی جاتی ہے۔';

  @override
  String get downloadingFirmware => 'فرم وئیئر ڈاؤن لوڈ کیا جا رہا ہے';

  @override
  String get installingFirmware => 'فرم وئیئر انسٹال کیا جا رہا ہے';

  @override
  String get firmwareUpdateWarning => 'ایپ بند نہ کریں یا ڈیوائس بند نہ کریں۔ اس سے آپ کی ڈیوائس خراب ہو سکتی ہے۔';

  @override
  String get firmwareUpdated => 'فرم وئیئر اپڈیٹ ہو گیا';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'براہ کرم اپنے $deviceName کو اپ ڈیٹ مکمل کرنے کے لیے دوبارہ شروع کریں۔';
  }

  @override
  String get yourDeviceIsUpToDate => 'آپ کی ڈیوائس اپ ڈیٹ ہے';

  @override
  String get currentVersion => 'موجودہ ورژن';

  @override
  String get latestVersion => 'تازہ ترین ورژن';

  @override
  String get whatsNew => 'کیا نیا ہے';

  @override
  String get installUpdate => 'اپ ڈیٹ انسٹال کریں';

  @override
  String get updateNow => 'اب اپ ڈیٹ کریں';

  @override
  String get updateGuide => 'اپ ڈیٹ گائیڈ';

  @override
  String get checkingForUpdates => 'اپ ڈیٹس کے لیے چیک کیا جا رہا ہے';

  @override
  String get checkingFirmwareVersion => 'فرم وئیئر ورژن چیک کیا جا رہا ہے...';

  @override
  String get firmwareUpdate => 'فرم وئیئر اپ ڈیٹ';

  @override
  String get payments => 'ادائیگیاں';

  @override
  String get connectPaymentMethodInfo =>
      'اپنی ایپس کے لیے ادائیگیاں وصول کرنا شروع کرنے کے لیے نیچے ادائیگی کا طریقہ منسلک کریں۔';

  @override
  String get selectedPaymentMethod => 'منتخب ادائیگی کا طریقہ';

  @override
  String get availablePaymentMethods => 'دستیاب ادائیگی کے طریقے';

  @override
  String get activeStatus => 'فعال';

  @override
  String get connectedStatus => 'منسلک';

  @override
  String get notConnectedStatus => 'منسلک نہیں';

  @override
  String get setActive => 'فعال سیٹ کریں';

  @override
  String get getPaidThroughStripe => 'Stripe کے ذریعے اپنی ایپ کی فروخت کے لیے ادائیگی حاصل کریں';

  @override
  String get monthlyPayouts => 'ماہانہ ادائیگیاں';

  @override
  String get monthlyPayoutsDescription =>
      'جب آپ \$10 کی کمائی حاصل کریں تو براہ راست اپنے اکاؤنٹ میں ماہانہ ادائیگیاں وصول کریں';

  @override
  String get secureAndReliable => 'محفوظ اور قابل اعتماد';

  @override
  String get stripeSecureDescription => 'Stripe آپ کی ایپ کی آمدنی کی محفوظ اور بروقت منتقلی کو یقینی بناتا ہے';

  @override
  String get selectYourCountry => 'اپنا ملک منتخب کریں';

  @override
  String get countrySelectionPermanent => 'آپ کا ملک کا انتخاب مستقل ہے اور بعد میں تبدیل نہیں کیا جا سکتا۔';

  @override
  String get byClickingConnectNow => '\"اب منسلک کریں\" پر کلک کر کے آپ اتفاق کرتے ہیں';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe منسلک اکاؤنٹ معاہدہ';

  @override
  String get errorConnectingToStripe => 'Stripe سے منسلک کرنے میں خرابی! براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get connectingYourStripeAccount => 'اپنے Stripe اکاؤنٹ کو منسلک کیا جا رہا ہے';

  @override
  String get stripeOnboardingInstructions =>
      'براہ کرم اپنے براؤزر میں Stripe آن بورڈنگ عمل مکمل کریں۔ یہ صفحہ مکمل ہونے کے بعد خود کار طریقے سے اپڈیٹ ہوگا۔';

  @override
  String get failedTryAgain => 'ناکام؟ دوبارہ کوشش کریں';

  @override
  String get illDoItLater => 'میں بعد میں کروں گا';

  @override
  String get successfullyConnected => 'کامیابی سے منسلک!';

  @override
  String get stripeReadyForPayments =>
      'آپ کا Stripe اکاؤنٹ اب ادائیگیاں وصول کرنے کے لیے تیار ہے۔ آپ اپنی ایپ کی فروخت سے فوری ہی کمانا شروع کر سکتے ہیں۔';

  @override
  String get updateStripeDetails => 'Stripe کی تفصیلات اپڈیٹ کریں';

  @override
  String get errorUpdatingStripeDetails => 'Stripe کی تفصیلات اپڈیٹ کرنے میں خرابی! براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get updatePayPal => 'PayPal اپڈیٹ کریں';

  @override
  String get setUpPayPal => 'PayPal سیٹ اپ کریں';

  @override
  String get updatePayPalAccountDetails => 'اپنے PayPal اکاؤنٹ کی تفصیلات اپڈیٹ کریں';

  @override
  String get connectPayPalToReceivePayments => 'ادائیگیاں وصول کرنا شروع کرنے کے لیے اپنے PayPal اکاؤنٹ کو منسلک کریں';

  @override
  String get paypalEmail => 'PayPal کی ای میل';

  @override
  String get paypalMeLink => 'PayPal.me لنک';

  @override
  String get stripeRecommendation =>
      'اگر Stripe آپ کے ملک میں دستیاب ہے تو ہم تیزی اور آسان ادائیگیوں کے لیے اسے استعمال کرنے کی سفارش کرتے ہیں۔';

  @override
  String get updatePayPalDetails => 'PayPal کی تفصیلات اپڈیٹ کریں';

  @override
  String get savePayPalDetails => 'PayPal کی تفصیلات محفوظ کریں';

  @override
  String get pleaseEnterPayPalEmail => 'براہ کرم PayPal کی ای میل درج کریں';

  @override
  String get pleaseEnterPayPalMeLink => 'براہ کرم PayPal.me لنک درج کریں';

  @override
  String get doNotIncludeHttpInLink => 'لنک میں http یا https یا www شامل نہ کریں';

  @override
  String get pleaseEnterValidPayPalMeLink => 'براہ کرم درست PayPal.me لنک درج کریں';

  @override
  String get pleaseEnterValidEmail => 'براہ کرم درست ای میل ایڈریس درج کریں';

  @override
  String get syncingYourRecordings => 'آپ کی ریکارڈنگز سنک کی جا رہی ہیں';

  @override
  String get syncYourRecordings => 'اپنی ریکارڈنگز سنک کریں';

  @override
  String get syncNow => 'اب سنک کریں';

  @override
  String get error => 'خرابی';

  @override
  String get speechSamples => 'صوتی نمونے';

  @override
  String additionalSampleIndex(String index) {
    return 'اضافی نمونہ $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'مدت: $seconds سیکنڈ';
  }

  @override
  String get additionalSpeechSampleRemoved => 'اضافی صوتی نمونہ ہٹایا گیا';

  @override
  String get consentDataMessage =>
      'جاری رکھ کر، آپ کی بات چیت، ریکارڈنگز اور ذاتی معلومات ہمارے سرورز پر محفوظ طریقے سے ذخیرہ کی جائیں گی۔ آپ کی آڈیو ریکارڈنگز اور ٹرانسکرپٹس تھرڈ پارٹی AI سروسز کے ذریعے پراسیس کی جاتی ہیں (بشمول ٹرانسکرپشن کے لیے Deepgram اور تجزیے کے لیے OpenAI) تاکہ آپ کو AI سے چلنے والی بصیرتیں فراہم کی جا سکیں اور ایپ کی تمام خصوصیات کو فعال کیا جا سکے۔';

  @override
  String get tasksEmptyStateMessage =>
      'آپ کی گفتگو سے کام کی چیزیں یہاں ظاہر ہوں گی۔\n+ ٹیپ کریں دستی طور پر ایک بنانے کے لیے۔';

  @override
  String get clearChatAction => 'بات کو صاف کریں';

  @override
  String get enableApps => 'ایپس فعال کریں';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'مزید دکھائیں ↓';

  @override
  String get showLess => 'کم دکھائیں ↑';

  @override
  String get loadingYourRecording => 'آپ کی ریکارڈنگ لوڈ ہو رہی ہے...';

  @override
  String get photoDiscardedMessage => 'یہ تصویر اس لیے ہٹا دی گئی کیونکہ یہ نمایاں نہیں تھی۔';

  @override
  String get analyzing => 'تجزیہ کیا جا رہا ہے...';

  @override
  String get searchCountries => 'ممالک تلاش کریں';

  @override
  String get checkingAppleWatch => 'Apple Watch چیک کیا جا رہا ہے...';

  @override
  String get installOmiOnAppleWatch => 'Omi کو اپنے\nApple Watch پر انسٹال کریں';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Omi کے ساتھ اپنے Apple Watch کو استعمال کرنے کے لیے آپ کو پہلے اپنی گھڑی پر Omi ایپ انسٹال کرنی ہوگی۔';

  @override
  String get openOmiOnAppleWatch => 'Omi کو اپنے\nApple Watch پر کھولیں';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi ایپ آپ کی Apple Watch پر انسٹال ہے۔ اسے کھولیں اور شروع کرنے کے لیے شروع ٹیپ کریں۔';

  @override
  String get openWatchApp => 'گھڑی کی ایپ کھولیں';

  @override
  String get iveInstalledAndOpenedTheApp => 'میں نے ایپ انسٹال اور کھول دی';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch کی ایپ نہیں کھول سکتے۔ براہ کرم اپنے Apple Watch پر Watch ایپ کو دستی طور پر کھولیں اور \"دستیاب ایپس\" حصے سے Omi انسٹال کریں۔';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch کامیابی سے منسلک!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch ابھی تک قابل رسائی نہیں۔ براہ کرم یقینی بنائیں کہ Omi ایپ آپ کی گھڑی پر کھلی ہے۔';

  @override
  String errorCheckingConnection(String error) {
    return 'کنکشن چیک کرتے ہوئے خرابی: $error';
  }

  @override
  String get muted => 'خاموش';

  @override
  String get processNow => 'اب پروسیس کریں';

  @override
  String get finishedConversation => 'گفتگو مختتم کر دی؟';

  @override
  String get stopRecordingConfirmation => 'کیا آپ یقینی ہیں کہ آپ ریکارڈنگ روک کر گفتگو کو اب خلاصہ کرنا چاہتے ہیں؟';

  @override
  String get conversationEndsManually => 'گفتگو صرف دستی طور پر ختم ہوگی۔';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'گفتگو کو $minutes منٹ$suffix خاموشی کے بعد خلاصہ کیا جاتا ہے۔';
  }

  @override
  String get dontAskAgain => 'دوبارہ مت پوچھیں';

  @override
  String get waitingForTranscriptOrPhotos => 'ٹرانسکرپٹ یا تصاویر کا انتظار کیا جا رہا ہے...';

  @override
  String get noSummaryYet => 'ابھی کوئی خلاصہ نہیں';

  @override
  String hints(String text) {
    return 'اشارے: $text';
  }

  @override
  String get testConversationPrompt => 'گفتگو کی ترغیب آزمائیں';

  @override
  String get prompt => 'ترغیب';

  @override
  String get result => 'نتیجہ:';

  @override
  String get compareTranscripts => 'ٹرانسکرپٹس کا موازنہ کریں';

  @override
  String get notHelpful => 'مفید نہیں';

  @override
  String get exportTasksWithOneTap => 'ایک ٹیپ سے کام کی چیزیں برآمد کریں!';

  @override
  String get inProgress => 'جاری ہے';

  @override
  String get photos => 'تصاویر';

  @override
  String get rawData => 'خام ڈیٹا';

  @override
  String get content => 'مواد';

  @override
  String get noContentToDisplay => 'دکھانے کے لیے کوئی مواد نہیں';

  @override
  String get noSummary => 'کوئی خلاصہ نہیں';

  @override
  String get updateOmiFirmware => 'Omi فرم وئیئر اپڈیٹ کریں';

  @override
  String get anErrorOccurredTryAgain => 'ایک خرابی ہو گئی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get welcomeBackSimple => 'دوبارہ خوش آمدید';

  @override
  String get addVocabularyDescription => 'وہ الفاظ شامل کریں جو Omi کو ٹرانسکرپشن کے دوران شناخت کرنی چاہیے۔';

  @override
  String get enterWordsCommaSeparated => 'الفاظ درج کریں (کوما سے الگ)';

  @override
  String get whenToReceiveDailySummary => 'اپنے روزانہ خلاصے کو کب وصول کریں';

  @override
  String get checkingNextSevenDays => 'اگلے 7 دن چیک کیے جا رہے ہیں';

  @override
  String failedToDeleteError(String error) {
    return 'حذف کرنے میں ناکام: $error';
  }

  @override
  String get developerApiKeys => 'ڈیولپر API کلیدیں';

  @override
  String get noApiKeysCreateOne => 'کوئی API کلیدی نہیں۔ شروع کرنے کے لیے ایک بنائیں۔';

  @override
  String get commandRequired => '⌘ درکار ہے';

  @override
  String get spaceKey => 'اسپیس';

  @override
  String loadMoreRemaining(String count) {
    return 'مزید لوڈ کریں ($count باقی)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'اہم $percentile% صارف';
  }

  @override
  String get wrappedMinutes => 'منٹ';

  @override
  String get wrappedConversations => 'گفتگو';

  @override
  String get wrappedDaysActive => 'فعال دن';

  @override
  String get wrappedYouTalkedAbout => 'آپ نے اس کے بارے میں بات کی';

  @override
  String get wrappedActionItems => 'کام کی چیزیں';

  @override
  String get wrappedTasksCreated => 'کام بنائے گئے';

  @override
  String get wrappedCompleted => 'مکمل';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% مکمل شدگی کی شرح';
  }

  @override
  String get wrappedYourTopDays => 'آپ کے بہترین دن';

  @override
  String get wrappedBestMoments => 'بہترین لمحے';

  @override
  String get wrappedMyBuddies => 'میرے دوست';

  @override
  String get wrappedCouldntStopTalkingAbout => 'اس کے بارے میں بات کرنا رک نہیں سکے';

  @override
  String get wrappedShow => 'شو';

  @override
  String get wrappedMovie => 'فلم';

  @override
  String get wrappedBook => 'کتاب';

  @override
  String get wrappedCelebrity => 'سیلیبرٹی';

  @override
  String get wrappedFood => 'کھانا';

  @override
  String get wrappedMovieRecs => 'دوستوں کے لیے فلم کی سفارشیں';

  @override
  String get wrappedBiggest => 'سب سے بڑا';

  @override
  String get wrappedStruggle => 'جدوجہد';

  @override
  String get wrappedButYouPushedThrough => 'لیکن آپ نے اسے آگے بڑھایا 💪';

  @override
  String get wrappedWin => 'جیت';

  @override
  String get wrappedYouDidIt => 'آپ نے کیا! 🎉';

  @override
  String get wrappedTopPhrases => 'اہم 5 فقرے';

  @override
  String get wrappedMins => 'منٹ';

  @override
  String get wrappedConvos => 'گفتگو';

  @override
  String get wrappedDays => 'دن';

  @override
  String get wrappedMyBuddiesLabel => 'میرے دوست';

  @override
  String get wrappedObsessionsLabel => 'پریشانی';

  @override
  String get wrappedStruggleLabel => 'جدوجہد';

  @override
  String get wrappedWinLabel => 'جیت';

  @override
  String get wrappedTopPhrasesLabel => 'اہم فقرے';

  @override
  String get wrappedLetsHitRewind => 'آئیے اپنے کی ریونڈ بجائیں';

  @override
  String get wrappedGenerateMyWrapped => 'میرا Wrapped بنائیں';

  @override
  String get wrappedProcessingDefault => 'پروسیس کیا جا رہا ہے...';

  @override
  String get wrappedCreatingYourStory => 'آپ کی\n2025 کی کہانی بنائی جا رہی ہے...';

  @override
  String get wrappedSomethingWentWrong => 'کچھ\nغلط ہوگیا';

  @override
  String get wrappedAnErrorOccurred => 'ایک خرابی ہو گئی';

  @override
  String get wrappedTryAgain => 'دوبارہ کوشش کریں';

  @override
  String get wrappedNoDataAvailable => 'کوئی ڈیٹا دستیاب نہیں';

  @override
  String get wrappedOmiLifeRecap => 'Omi کے ساتھ زندگی کا خلاصہ';

  @override
  String get wrappedSwipeUpToBegin => 'شروع کرنے کے لیے اوپر سوائپ کریں';

  @override
  String get wrappedShareText => 'میرا 2025، Omi کی یاد میں ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'شیئر کرنے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get wrappedFailedToStartGeneration => 'تخلیق شروع کرنے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get wrappedStarting => 'شروع ہو رہا ہے...';

  @override
  String get wrappedShare => 'شیئر کریں';

  @override
  String get wrappedShareYourWrapped => 'اپنا Wrapped شیئر کریں';

  @override
  String get wrappedMy2025 => 'میرا 2025';

  @override
  String get wrappedRememberedByOmi => 'Omi کی یاد میں';

  @override
  String get wrappedMostFunDay => 'سب سے زیادہ مزہ';

  @override
  String get wrappedMostProductiveDay => 'سب سے زیادہ پروڈکٹو';

  @override
  String get wrappedMostIntenseDay => 'سب سے زیادہ شدید';

  @override
  String get wrappedFunniestMoment => 'سب سے مضحکہ';

  @override
  String get wrappedMostCringeMoment => 'سب سے زیادہ شرمناک';

  @override
  String get wrappedMinutesLabel => 'منٹ';

  @override
  String get wrappedConversationsLabel => 'گفتگو';

  @override
  String get wrappedDaysActiveLabel => 'فعال دن';

  @override
  String get wrappedTasksGenerated => 'کام بنائے گئے';

  @override
  String get wrappedTasksCompleted => 'کام مکمل کیے گئے';

  @override
  String get wrappedTopFivePhrases => 'اہم 5 فقرے';

  @override
  String get wrappedAGreatDay => 'ایک بہترین دن';

  @override
  String get wrappedGettingItDone => 'اسے مکمل کرنا';

  @override
  String get wrappedAChallenge => 'ایک چیلنج';

  @override
  String get wrappedAHilariousMoment => 'ایک مضحکہ خیز لمحہ';

  @override
  String get wrappedThatAwkwardMoment => 'وہ شرمناک لمحہ';

  @override
  String get wrappedYouHadFunnyMoments => 'آپ کے پاس اس سال کچھ مضحکہ خیز لمحے تھے!';

  @override
  String get wrappedWeveAllBeenThere => 'ہم سب وہاں گئے ہیں!';

  @override
  String get wrappedFriend => 'دوست';

  @override
  String get wrappedYourBuddy => 'آپ کا ساتھی!';

  @override
  String get wrappedNotMentioned => 'ذکر نہیں کیا گیا';

  @override
  String get wrappedTheHardPart => 'مشکل حصہ';

  @override
  String get wrappedPersonalGrowth => 'ذاتی ترقی';

  @override
  String get wrappedFunDay => 'مزہ';

  @override
  String get wrappedProductiveDay => 'پروڈکٹو';

  @override
  String get wrappedIntenseDay => 'شدید';

  @override
  String get wrappedFunnyMomentTitle => 'مضحکہ خیز لمحہ';

  @override
  String get wrappedCringeMomentTitle => 'شرمناک لمحہ';

  @override
  String get wrappedYouTalkedAboutBadge => 'آپ نے اس کے بارے میں بات کی';

  @override
  String get wrappedCompletedLabel => 'مکمل';

  @override
  String get wrappedMyBuddiesCard => 'میرے دوست';

  @override
  String get wrappedBuddiesLabel => 'دوست';

  @override
  String get wrappedObsessionsLabelUpper => 'پریشانی';

  @override
  String get wrappedStruggleLabelUpper => 'جدوجہد';

  @override
  String get wrappedWinLabelUpper => 'جیت';

  @override
  String get wrappedTopPhrasesLabelUpper => 'اہم فقرے';

  @override
  String get wrappedYourHeader => 'آپ کا';

  @override
  String get wrappedTopDaysHeader => 'بہترین دن';

  @override
  String get wrappedYourTopDaysBadge => 'آپ کے بہترین دن';

  @override
  String get wrappedBestHeader => 'بہترین';

  @override
  String get wrappedMomentsHeader => 'لمحے';

  @override
  String get wrappedBestMomentsBadge => 'بہترین لمحے';

  @override
  String get wrappedBiggestHeader => 'سب سے بڑا';

  @override
  String get wrappedStruggleHeader => 'جدوجہد';

  @override
  String get wrappedWinHeader => 'جیت';

  @override
  String get wrappedButYouPushedThroughEmoji => 'لیکن آپ نے اسے آگے بڑھایا 💪';

  @override
  String get wrappedYouDidItEmoji => 'آپ نے کیا! 🎉';

  @override
  String get wrappedHours => 'گھنٹے';

  @override
  String get wrappedActions => 'کام';

  @override
  String get multipleSpeakersDetected => 'متعدد اسپیکرز شناخت کیے گئے';

  @override
  String get multipleSpeakersDescription =>
      'ایسا لگتا ہے کہ ریکارڈنگ میں متعدد اسپیکرز ہیں۔ براہ کرم یقینی بنائیں کہ آپ خاموش جگہ میں ہیں اور دوبارہ کوشش کریں۔';

  @override
  String get invalidRecordingDetected => 'غلط ریکارڈنگ شناخت کی گئی';

  @override
  String get notEnoughSpeechDescription => 'کافی تقریر کی شناخت نہیں ہے۔ براہ کرم مزید بولیں اور دوبارہ کوشش کریں۔';

  @override
  String get speechDurationDescription => 'براہ کرم یقینی بنائیں کہ آپ کم از کم 5 سیکنڈ اور 90 سے زیادہ نہ بولیں۔';

  @override
  String get connectionLostDescription =>
      'کنکشن میں خلل پڑا۔ براہ کرم اپنی انٹرنیٹ کنکشن کی جانچ کریں اور دوبارہ کوشش کریں۔';

  @override
  String get howToTakeGoodSample => 'اچھا نمونہ کیسے لیں؟';

  @override
  String get goodSampleInstructions =>
      '1. یقینی بنائیں کہ آپ کسی خاموش جگہ میں ہیں۔\n2. واضح طور سے اور قدرتی انداز میں بولیں۔\n3. یقینی بنائیں کہ آپ کا ڈیوائس اپنی قدرتی پوزیشن میں، آپ کی گردن پر ہے۔\n\nایک بار بننے کے بعد، آپ اسے ہمیشہ بہتر بنا سکتے ہیں یا دوبارہ کر سکتے ہیں۔';

  @override
  String get noDeviceConnectedUseMic => 'کوئی ڈیوائس متصل نہیں۔ فون مائیکروفون استعمال کیا جائے گا۔';

  @override
  String get doItAgain => 'دوبارہ کریں';

  @override
  String get listenToSpeechProfile => 'میرا سپیچ پروفائل سنیں ➡️';

  @override
  String get recognizingOthers => 'دوسروں کو پہچاننا 👀';

  @override
  String get keepGoingGreat => 'جاری رکھیں، آپ بہترین کر رہے ہیں';

  @override
  String get somethingWentWrongTryAgain => 'کچھ غلط ہو گیا! براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get uploadingVoiceProfile => 'آپ کا وائس پروفائل اپ لوڈ کیا جا رہا ہے....';

  @override
  String get memorizingYourVoice => 'آپ کی آواز یاد کی جا رہی ہے...';

  @override
  String get personalizingExperience => 'آپ کے تجربے کو ذاتی بنایا جا رہا ہے...';

  @override
  String get keepSpeakingUntil100 => '100% تک پہنچنے تک بولتے رہیں۔';

  @override
  String get greatJobAlmostThere => 'بہترین کام، آپ تقریباً وہاں ہیں';

  @override
  String get soCloseJustLittleMore => 'بہت قریب، صرف تھوڑا سا مزید';

  @override
  String get notificationFrequency => 'اطلاع کی تعداد';

  @override
  String get controlNotificationFrequency => 'یہ کنٹرول کریں کہ Omi آپ کو کتنی بار فعال طریقے سے مطلع کرتا ہے۔';

  @override
  String get yourScore => 'آپ کا سکور';

  @override
  String get dailyScoreBreakdown => 'روزانہ سکور کی تفصیل';

  @override
  String get todaysScore => 'آج کا سکور';

  @override
  String get tasksCompleted => 'مکمل شدہ کام';

  @override
  String get completionRate => 'مکمل کرنے کی شرح';

  @override
  String get howItWorks => 'یہ کیسے کام کرتا ہے';

  @override
  String get dailyScoreExplanation =>
      'آپ کا روزانہ سکور کام مکمل کرنے پر مبنی ہے۔ اپنا سکور بہتر بنانے کے لیے اپنے کام مکمل کریں!';

  @override
  String get notificationFrequencyDescription =>
      'یہ کنٹرول کریں کہ Omi آپ کو کتنی بار فعال طریقے سے مطلع کرتا ہے اور یاد دہانی دیتا ہے۔';

  @override
  String get sliderOff => 'بند';

  @override
  String get sliderMax => 'زیادہ سے زیادہ';

  @override
  String summaryGeneratedFor(String date) {
    return '$date کے لیے خلاصہ تیار کیا گیا';
  }

  @override
  String get failedToGenerateSummary => 'خلاصہ تیار کرنے میں ناکام۔ یقینی بنائیں کہ آپ کے پاس اس دن کے لیے بات چیت ہے۔';

  @override
  String get recap => 'خلاصہ';

  @override
  String deleteQuoted(String name) {
    return '\"$name\" حذف کریں';
  }

  @override
  String moveConversationsTo(int count) {
    return '$count بات چیت یہاں منتقل کریں:';
  }

  @override
  String get noFolder => 'کوئی فولڈر نہیں';

  @override
  String get removeFromAllFolders => 'تمام فولڈرز سے ہٹائیں';

  @override
  String get buildAndShareYourCustomApp => 'اپنی کسٹم ایپ بنائیں اور شیئر کریں';

  @override
  String get searchAppsPlaceholder => '1500+ ایپس تلاش کریں';

  @override
  String get filters => 'فلٹرز';

  @override
  String get frequencyOff => 'بند';

  @override
  String get frequencyMinimal => 'کم سے کم';

  @override
  String get frequencyLow => 'کم';

  @override
  String get frequencyBalanced => 'متوازن';

  @override
  String get frequencyHigh => 'زیادہ';

  @override
  String get frequencyMaximum => 'زیادہ سے زیادہ';

  @override
  String get frequencyDescOff => 'کوئی فعال اطلاعات نہیں';

  @override
  String get frequencyDescMinimal => 'صرف اہم یاد دہانی';

  @override
  String get frequencyDescLow => 'صرف اہم اپ ڈیٹس';

  @override
  String get frequencyDescBalanced => 'باقاعدہ مددگار تنبیہ';

  @override
  String get frequencyDescHigh => 'کثرت سے چیک ان';

  @override
  String get frequencyDescMaximum => 'مسلسل منسلک رہیں';

  @override
  String get clearChatQuestion => 'چیٹ صاف کریں؟';

  @override
  String get syncingMessages => 'سرور کے ساتھ پیغامات کو ہم آہنگ کیا جا رہا ہے...';

  @override
  String get chatAppsTitle => 'چیٹ ایپس';

  @override
  String get selectApp => 'ایپ منتخب کریں';

  @override
  String get noChatAppsEnabled => 'کوئی چیٹ ایپ فعال نہیں۔\n\"ایپس فعال کریں\" پر ٹیپ کریں کچھ شامل کرنے کے لیے۔';

  @override
  String get disable => 'غیر فعال کریں';

  @override
  String get photoLibrary => 'فوٹو لائبریری';

  @override
  String get chooseFile => 'فائل منتخب کریں';

  @override
  String get connectAiAssistantsToYourData => 'AI معاونین کو اپنے ڈیٹا سے منسلک کریں';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'ہوم پیج پر اپنے ذاتی اہداف کو ٹریک کریں';

  @override
  String get deleteRecording => 'ریکارڈنگ حذف کریں';

  @override
  String get thisCannotBeUndone => 'یہ کالعدم نہیں ہو سکتا۔';

  @override
  String get sdCard => 'SD کارڈ';

  @override
  String get fromSd => 'SD سے';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'تیز رفتار منتقلی';

  @override
  String get syncingStatus => 'ہم آہنگ کیا جا رہا ہے';

  @override
  String get failedStatus => 'ناکام';

  @override
  String etaLabel(String time) {
    return 'تخمینہ: $time';
  }

  @override
  String get transferMethod => 'منتقلی کا طریقہ';

  @override
  String get fast => 'تیز';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'فون';

  @override
  String get cancelSync => 'ہم آہنگی منسوخ کریں';

  @override
  String get cancelSyncMessage => 'پہلے سے ڈاؤن لوڈ شدہ ڈیٹا محفوظ ہوگا۔ آپ بعد میں شروع کر سکتے ہیں۔';

  @override
  String get syncCancelled => 'ہم آہنگی منسوخ کر دی گئی';

  @override
  String get deleteProcessedFiles => 'پروسیس شدہ فائلیں حذف کریں';

  @override
  String get processedFilesDeleted => 'پروسیس شدہ فائلیں حذف کر دی گئیں';

  @override
  String get wifiEnableFailed => 'ڈیوائس پر WiFi فعال کرنے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get deviceNoFastTransfer =>
      'آپ کے ڈیوائس میں تیز رفتار منتقلی کی سہولت نہیں ہے۔ اس کی بجائے Bluetooth استعمال کریں۔';

  @override
  String get enableHotspotMessage => 'براہ کرم اپنے فون کا ہاٹ سپاٹ فعال کریں اور دوبارہ کوشش کریں۔';

  @override
  String get transferStartFailed => 'منتقلی شروع کرنے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get deviceNotResponding => 'ڈیوائس نے جواب نہیں دیا۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get invalidWifiCredentials => 'غلط WiFi بروز اہل۔ اپنی ہاٹ سپاٹ سیٹنگز کی جانچ کریں۔';

  @override
  String get wifiConnectionFailed => 'WiFi کنکشن ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get sdCardProcessing => 'SD کارڈ پروسیسنگ';

  @override
  String sdCardProcessingMessage(int count) {
    return '$count ریکارڈنگ پروسیس کی جا رہی ہے۔ فائلیں بعد میں SD کارڈ سے ہٹا دی جائیں گی۔';
  }

  @override
  String get process => 'پروسیس کریں';

  @override
  String get wifiSyncFailed => 'WiFi ہم آہنگی ناکام';

  @override
  String get processingFailed => 'پروسیسنگ ناکام';

  @override
  String get downloadingFromSdCard => 'SD کارڈ سے ڈاؤن لوڈ کیا جا رہا ہے';

  @override
  String processingProgress(int current, int total) {
    return 'پروسیس کیا جا رہا ہے $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count بات چیت بنائی گئی';
  }

  @override
  String get internetRequired => 'انٹرنیٹ درکار ہے';

  @override
  String get processAudio => 'آڈیو پروسیس کریں';

  @override
  String get start => 'شروع کریں';

  @override
  String get noRecordings => 'کوئی ریکارڈنگ نہیں';

  @override
  String get audioFromOmiWillAppearHere => 'آپ کے Omi ڈیوائس سے آڈیو یہاں ظاہر ہوگی';

  @override
  String get deleteProcessed => 'پروسیس شدہ حذف کریں';

  @override
  String get tryDifferentFilter => 'مختلف فلٹر آزمائیں';

  @override
  String get recordings => 'ریکارڈنگز';

  @override
  String get enableRemindersAccess =>
      'Apple Reminders استعمال کرنے کے لیے براہ کرم سیٹنگز میں Reminders رسائی فعال کریں';

  @override
  String todayAtTime(String time) {
    return 'آج $time کو';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'کل $time کو';
  }

  @override
  String get lessThanAMinute => 'ایک منٹ سے کم';

  @override
  String estimatedMinutes(int count) {
    return '~$count منٹ';
  }

  @override
  String estimatedHours(int count) {
    return '~$count گھنٹے';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'تخمینہ: $time باقی';
  }

  @override
  String get summarizingConversation => 'بات چیت کو خلاصہ کیا جا رہا ہے...\nاس میں چند سیکنڈ لگ سکتے ہیں';

  @override
  String get resummarizingConversation => 'بات چیت کو دوبارہ خلاصہ کیا جا رہا ہے...\nاس میں چند سیکنڈ لگ سکتے ہیں';

  @override
  String get nothingInterestingRetry => 'کچھ دلچسپ نہیں ملا،\nکیا آپ دوبارہ کوشش کرنا چاہتے ہیں؟';

  @override
  String get noSummaryForConversation => 'اس بات چیت کے لیے کوئی خلاصہ دستیاب نہیں۔';

  @override
  String get unknownLocation => 'نامعلوم مقام';

  @override
  String get couldNotLoadMap => 'نقشہ لوڈ نہیں کر سکا';

  @override
  String get triggerConversationIntegration => 'بات چیت بنائی گئی انٹیگریشن کو ٹریگر کریں';

  @override
  String get webhookUrlNotSet => 'ویب ہک URL سیٹ نہیں ہے';

  @override
  String get setWebhookUrlInSettings =>
      'براہ کرم اس خصوصیت کو استعمال کرنے کے لیے ڈیولپر سیٹنگز میں ویب ہک URL سیٹ کریں۔';

  @override
  String get sendWebUrl => 'ویب URL بھیجیں';

  @override
  String get sendTranscript => 'ٹرانسکرپٹ بھیجیں';

  @override
  String get sendSummary => 'خلاصہ بھیجیں';

  @override
  String get debugModeDetected => 'ڈیبگ موڈ دریافت ہوا';

  @override
  String get performanceReduced => 'کارکردگی میں 5-10 گنا کمی۔ Release موڈ استعمال کریں۔';

  @override
  String autoClosingInSeconds(int seconds) {
    return '${seconds}s میں خودکار طور پر بند ہو رہا ہے';
  }

  @override
  String get modelRequired => 'ماڈل درکار ہے';

  @override
  String get downloadWhisperModel => 'براہ کرم محفوظ کرنے سے پہلے ایک Whisper ماڈل ڈاؤن لوڈ کریں۔';

  @override
  String get deviceNotCompatible => 'ڈیوائس مطابقت نہیں رکھتا';

  @override
  String get deviceRequirements => 'آپ کا ڈیوائس On-Device ٹرانسکریپشن کی ضروریات پوری نہیں کرتا۔';

  @override
  String get willLikelyCrash => 'یہ فعال کرنے سے ایپ شاید کریش ہو جائے یا فریز ہو جائے۔';

  @override
  String get transcriptionSlowerLessAccurate => 'ٹرانسکریپشن نمایاں طور پر سست ہوگی اور کم درست ہوگی۔';

  @override
  String get proceedAnyway => 'بہرحال آگے بڑھیں';

  @override
  String get olderDeviceDetected => 'پرانا ڈیوائس دریافت ہوا';

  @override
  String get onDeviceSlower => 'On-device ٹرانسکریپشن اس ڈیوائس پر سست ہو سکتی ہے۔';

  @override
  String get batteryUsageHigher => 'بیٹری کا استعمال کلاؤڈ ٹرانسکریپشن سے زیادہ ہوگا۔';

  @override
  String get considerOmiCloud => 'بہتر کارکردگی کے لیے Omi Cloud استعمال کرنے پر غور کریں۔';

  @override
  String get highResourceUsage => 'زیادہ وسائل کا استعمال';

  @override
  String get onDeviceIntensive => 'On-Device ٹرانسکریپشن حسابی لحاظ سے شدید ہے۔';

  @override
  String get batteryDrainIncrease => 'بیٹری کی ڈرین میں نمایاں اضافہ ہوگا۔';

  @override
  String get deviceMayWarmUp => 'طویل استعمال کے دوران ڈیوائس گرم ہو سکتا ہے۔';

  @override
  String get speedAccuracyLower => 'رفتار اور درستگی کلاؤڈ ماڈلز سے کم ہو سکتی ہے۔';

  @override
  String get cloudProvider => 'کلاؤڈ فراہم کنندہ';

  @override
  String get premiumMinutesInfo => 'ماہانہ 1,200 پریمیم منٹ۔ On-Device ٹیب غیر محدود مفت ٹرانسکریپشن فراہم کرتا ہے۔';

  @override
  String get viewUsage => 'استعمال دیکھیں';

  @override
  String get localProcessingInfo =>
      'آڈیو مقامی طور پر پروسیس کیا جاتا ہے۔ آف لائن کام کرتا ہے، زیادہ نجی، لیکن زیادہ بیٹری استعمال کرتا ہے۔';

  @override
  String get model => 'ماڈل';

  @override
  String get performanceWarning => 'کارکردگی انتباہ';

  @override
  String get largeModelWarning =>
      'یہ ماڈل بڑا ہے اور موبائل ڈیوائسز پر ایپ کو کریش کر سکتا ہے یا بہت سست چل سکتا ہے۔\n\n\"small\" یا \"base\" کی سفارش کی جاتی ہے۔';

  @override
  String get usingNativeIosSpeech => 'Native iOS Speech Recognition استعمال کیا جا رہا ہے';

  @override
  String get noModelDownloadRequired =>
      'آپ کے ڈیوائس کے native speech engine کا استعمال کیا جائے گا۔ کوئی ماڈل ڈاؤن لوڈ درکار نہیں۔';

  @override
  String get modelReady => 'ماڈل تیار ہے';

  @override
  String get redownload => 'دوبارہ ڈاؤن لوڈ کریں';

  @override
  String get doNotCloseApp => 'براہ کرم ایپ بند نہ کریں۔';

  @override
  String get downloading => 'ڈاؤن لوڈ کیا جا رہا ہے...';

  @override
  String get downloadModel => 'ماڈل ڈاؤن لوڈ کریں';

  @override
  String estimatedSize(String size) {
    return 'تخمینہ حجم: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'دستیاب جگہ: $space';
  }

  @override
  String get notEnoughSpace => 'انتباہ: کافی جگہ نہیں!';

  @override
  String get download => 'ڈاؤن لوڈ کریں';

  @override
  String downloadError(String error) {
    return 'ڈاؤن لوڈ خرابی: $error';
  }

  @override
  String get cancelled => 'منسوخ کیا گیا';

  @override
  String get deviceNotCompatibleTitle => 'ڈیوائس مطابقت نہیں رکھتا';

  @override
  String get deviceNotMeetRequirements => 'آپ کا ڈیوائس On-Device ٹرانسکریپشن کی ضروریات پوری نہیں کرتا۔';

  @override
  String get transcriptionSlowerOnDevice => 'On-device ٹرانسکریپشن اس ڈیوائس پر سست ہو سکتی ہے۔';

  @override
  String get computationallyIntensive => 'On-Device ٹرانسکریپشن حسابی لحاظ سے شدید ہے۔';

  @override
  String get batteryDrainSignificantly => 'بیٹری کی ڈرین میں نمایاں اضافہ ہوگا۔';

  @override
  String get premiumMinutesMonth => 'ماہانہ 1,200 پریمیم منٹ۔ On-Device ٹیب غیر محدود مفت ٹرانسکریپشن فراہم کرتا ہے۔ ';

  @override
  String get audioProcessedLocally =>
      'آڈیو مقامی طور پر پروسیس کیا جاتا ہے۔ آف لائن کام کرتا ہے، زیادہ نجی، لیکن زیادہ بیٹری استعمال کرتا ہے۔';

  @override
  String get languageLabel => 'زبان';

  @override
  String get modelLabel => 'ماڈل';

  @override
  String get modelTooLargeWarning =>
      'یہ ماڈل بڑا ہے اور موبائل ڈیوائسز پر ایپ کو کریش کر سکتا ہے یا بہت سست چل سکتا ہے۔\n\n\"small\" یا \"base\" کی سفارش کی جاتی ہے۔';

  @override
  String get nativeEngineNoDownload =>
      'آپ کے ڈیوائس کے native speech engine کا استعمال کیا جائے گا۔ کوئی ماڈل ڈاؤن لوڈ درکار نہیں۔';

  @override
  String modelReadyWithName(String model) {
    return 'ماڈل تیار ہے ($model)';
  }

  @override
  String get reDownload => 'دوبارہ ڈاؤن لوڈ کریں';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return '$model ڈاؤن لوڈ کیا جا رہا ہے: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return '$model تیار کیا جا رہا ہے...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'ڈاؤن لوڈ خرابی: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'تخمینہ حجم: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'دستیاب جگہ: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omi کا built-in لائیو ٹرانسکریپشن خودکار speaker detection اور diarization کے ساتھ real-time بات چیت کے لیے بہتر بنایا گیا ہے۔';

  @override
  String get reset => 'دوبارہ سیٹ کریں';

  @override
  String get useTemplateFrom => 'اس سے ٹیمپلیٹ استعمال کریں';

  @override
  String get selectProviderTemplate => 'ایک فراہم کنندہ ٹیمپلیٹ منتخب کریں...';

  @override
  String get quicklyPopulateResponse => 'معروف فراہم کنندہ کے جواب کی شکل سے تیزی سے بھریں';

  @override
  String get quicklyPopulateRequest => 'معروف فراہم کنندہ کی درخواست کی شکل سے تیزی سے بھریں';

  @override
  String get invalidJsonError => 'غلط JSON';

  @override
  String downloadModelWithName(String model) {
    return 'ماڈل ڈاؤن لوڈ کریں ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'ماڈل: $model';
  }

  @override
  String get device => 'ڈیوائس';

  @override
  String get chatAssistantsTitle => 'چیٹ معاونین';

  @override
  String get permissionReadConversations => 'بات چیت پڑھیں';

  @override
  String get permissionReadMemories => 'یادیں پڑھیں';

  @override
  String get permissionReadTasks => 'کام پڑھیں';

  @override
  String get permissionCreateConversations => 'بات چیت بنائیں';

  @override
  String get permissionCreateMemories => 'یادیں بنائیں';

  @override
  String get permissionTypeAccess => 'رسائی';

  @override
  String get permissionTypeCreate => 'بنائیں';

  @override
  String get permissionTypeTrigger => 'ٹریگر';

  @override
  String get permissionDescReadConversations => 'یہ ایپ آپ کی بات چیت تک رسائی حاصل کر سکتی ہے۔';

  @override
  String get permissionDescReadMemories => 'یہ ایپ آپ کی یادوں تک رسائی حاصل کر سکتی ہے۔';

  @override
  String get permissionDescReadTasks => 'یہ ایپ آپ کے کام تک رسائی حاصل کر سکتی ہے۔';

  @override
  String get permissionDescCreateConversations => 'یہ ایپ نئی بات چیت بنا سکتی ہے۔';

  @override
  String get permissionDescCreateMemories => 'یہ ایپ نئی یادیں بنا سکتی ہے۔';

  @override
  String get realtimeListening => 'Real-time Listening';

  @override
  String get setupCompleted => 'مکمل';

  @override
  String get pleaseSelectRating => 'براہ کرم ایک درجہ بندی منتخب کریں';

  @override
  String get writeReviewOptional => 'ایک جائزہ لکھیں (اختیاری)';

  @override
  String get setupQuestionsIntro => 'کچھ سوالات کے جوابات دے کر Omi کو بہتر بنانے میں ہماری مدد کریں۔  🫶 💜';

  @override
  String get setupQuestionProfession => '1. آپ کیا کرتے ہیں؟';

  @override
  String get setupQuestionUsage => '2. آپ اپنے Omi کو کہاں استعمال کرنے کا منصوبہ بناتے ہیں؟';

  @override
  String get setupQuestionAge => '3. آپ کی عمر کی حد کیا ہے؟';

  @override
  String get setupAnswerAllQuestions => 'آپ نے ابھی تک تمام سوالات کا جواب نہیں دیا! 🥺';

  @override
  String get setupSkipHelp => 'چھوڑ دیں، میں مدد نہیں کرنا چاہتا :C';

  @override
  String get professionEntrepreneur => 'سرمایہ کار';

  @override
  String get professionSoftwareEngineer => 'سافٹ ویئر انجینئر';

  @override
  String get professionProductManager => 'پروڈکٹ منیجر';

  @override
  String get professionExecutive => 'ایگزیکٹو';

  @override
  String get professionSales => 'فروخت';

  @override
  String get professionStudent => 'طالب علم';

  @override
  String get usageAtWork => 'کام میں';

  @override
  String get usageIrlEvents => 'IRL ایونٹس';

  @override
  String get usageOnline => 'آن لائن';

  @override
  String get usageSocialSettings => 'سماجی ترتیبات میں';

  @override
  String get usageEverywhere => 'ہر جگہ';

  @override
  String get customBackendUrlTitle => 'کسٹم Backend URL';

  @override
  String get backendUrlLabel => 'Backend URL';

  @override
  String get saveUrlButton => 'URL محفوظ کریں';

  @override
  String get enterBackendUrlError => 'براہ کرم backend URL درج کریں';

  @override
  String get urlMustEndWithSlashError => 'URL کو \"/\" کے ساتھ ختم ہونا چاہیے';

  @override
  String get invalidUrlError => 'براہ کرم ایک درست URL درج کریں';

  @override
  String get backendUrlSavedSuccess => 'Backend URL کامیابی سے محفوظ ہوگیا!';

  @override
  String get signInTitle => 'سائن ان کریں';

  @override
  String get signInButton => 'سائن ان کریں';

  @override
  String get enterEmailError => 'براہ کرم اپنی ای میل درج کریں';

  @override
  String get invalidEmailError => 'براہ کرم ایک درست ای میل درج کریں';

  @override
  String get enterPasswordError => 'براہ کرم اپنا پاس ورڈ درج کریں';

  @override
  String get passwordMinLengthError => 'پاس ورڈ کم از کم 8 حروف طویل ہونا چاہیے';

  @override
  String get signInSuccess => 'سائن ان کامیاب!';

  @override
  String get alreadyHaveAccountLogin => 'پہلے سے اکاؤنٹ ہے؟ لاگ ان کریں';

  @override
  String get emailLabel => 'ای میل';

  @override
  String get passwordLabel => 'پاس ورڈ';

  @override
  String get createAccountTitle => 'اکاؤنٹ بنائیں';

  @override
  String get nameLabel => 'نام';

  @override
  String get repeatPasswordLabel => 'پاس ورڈ دہرائیں';

  @override
  String get signUpButton => 'سائن اپ کریں';

  @override
  String get enterNameError => 'براہ کرم اپنا نام درج کریں';

  @override
  String get passwordsDoNotMatch => 'پاس ورڈز ملتے نہیں ہیں';

  @override
  String get signUpSuccess => 'سائن اپ کامیاب!';

  @override
  String get loadingKnowledgeGraph => 'Knowledge Graph لوڈ کیا جا رہا ہے...';

  @override
  String get noKnowledgeGraphYet => 'ابھی کوئی knowledge graph نہیں';

  @override
  String get buildingKnowledgeGraphFromMemories => 'یادوں سے آپ کا knowledge graph بنایا جا رہا ہے...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'جیسے ہی آپ نئی یادیں بنائیں گے آپ کا knowledge graph خود بخود بنایا جائے گا۔';

  @override
  String get buildGraphButton => 'گراف بنائیں';

  @override
  String get checkOutMyMemoryGraph => 'میرا memory graph دیکھیں!';

  @override
  String get getButton => 'حاصل کریں';

  @override
  String openingApp(String appName) {
    return '$appName کھولا جا رہا ہے...';
  }

  @override
  String get writeSomething => 'کچھ لکھیں';

  @override
  String get submitReply => 'جواب جمع کریں';

  @override
  String get editYourReply => 'اپنا جواب ترمیم کریں';

  @override
  String get replyToReview => 'جائزے کا جواب دیں';

  @override
  String get rateAndReviewThisApp => 'اس ایپ کو ریٹ اور جائزہ لیں';

  @override
  String get noChangesInReview => 'جائزے میں کوئی تبدیلی نہیں ہے۔';

  @override
  String get cantRateWithoutInternet => 'انٹرنیٹ کنکشن کے بغیر ایپ کو ریٹ نہیں کر سکتے۔';

  @override
  String get appAnalytics => 'ایپ تجزیات';

  @override
  String get learnMoreLink => 'مزید جانیں';

  @override
  String get moneyEarned => 'کمائی ہوئی رقم';

  @override
  String get writeYourReply => 'اپنا جواب لکھیں...';

  @override
  String get replySentSuccessfully => 'جواب کامیابی سے بھیجا گیا';

  @override
  String failedToSendReply(String error) {
    return 'جواب بھیجنے میں ناکام: $error';
  }

  @override
  String get send => 'بھیجیں';

  @override
  String starFilter(int count) {
    return '$count سٹار';
  }

  @override
  String get noReviewsFound => 'کوئی جائزہ نہیں ملا';

  @override
  String get editReply => 'جواب ترمیم کریں';

  @override
  String get reply => 'جواب دیں';

  @override
  String starFilterLabel(int count) {
    return '$count سٹار';
  }

  @override
  String get sharePublicLink => 'عوامی لنک شیئر کریں';

  @override
  String get connectedKnowledgeData => 'منسلک Knowledge ڈیٹا';

  @override
  String get enterName => 'نام درج کریں';

  @override
  String get goal => 'مقصد';

  @override
  String get tapToTrackThisGoal => 'اس مقصد کو ٹریک کرنے کے لیے ٹیپ کریں';

  @override
  String get tapToSetAGoal => 'مقصد سیٹ کرنے کے لیے ٹیپ کریں';

  @override
  String get processedConversations => 'پروسیس شدہ بات چیت';

  @override
  String get updatedConversations => 'اپ ڈیٹ شدہ بات چیت';

  @override
  String get newConversations => 'نئی بات چیت';

  @override
  String get summaryTemplate => 'خلاصہ ٹیمپلیٹ';

  @override
  String get suggestedTemplates => 'تجویز شدہ ٹیمپلیٹس';

  @override
  String get otherTemplates => 'دوسرے ٹیمپلیٹس';

  @override
  String get availableTemplates => 'دستیاب ٹیمپلیٹس';

  @override
  String get getCreative => 'تخلیقی بنیں';

  @override
  String get defaultLabel => 'ڈیفالٹ';

  @override
  String get lastUsedLabel => 'آخری استعمال';

  @override
  String get setDefaultApp => 'ڈیفالٹ ایپ سیٹ کریں';

  @override
  String setDefaultAppContent(String appName) {
    return '$appName کو اپنی ڈیفالٹ خلاصہ کاری ایپ کے طور پر سیٹ کریں؟\\n\\nیہ ایپ تمام مستقبل کی بات چیت کے خلاصوں کے لیے خودکار طور پر استعمال کی جائے گی۔';
  }

  @override
  String get setDefaultButton => 'ڈیفالٹ سیٹ کریں';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName ڈیفالٹ خلاصہ کاری ایپ کے طور پر سیٹ کیا گیا';
  }

  @override
  String get createCustomTemplate => 'کسٹم ٹیمپلیٹ بنائیں';

  @override
  String get allTemplates => 'تمام ٹیمپلیٹس';

  @override
  String failedToInstallApp(String appName) {
    return '$appName انسٹال کرنے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return '$appName انسٹال کرنے میں خرابی: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Speaker $speakerId کو ٹیگ کریں';
  }

  @override
  String get personNameAlreadyExists => 'اس نام کا شخص پہلے سے موجود ہے۔';

  @override
  String get selectYouFromList => 'اپنے آپ کو ٹیگ کرنے کے لیے، براہ کرم فہرست سے \"آپ\" منتخب کریں۔';

  @override
  String get enterPersonsName => 'شخص کا نام درج کریں';

  @override
  String get addPerson => 'شخص شامل کریں';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'اس speaker سے دوسرے حصے کو ٹیگ کریں ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'دوسرے حصوں کو ٹیگ کریں';

  @override
  String get managePeople => 'لوگوں کو منیج کریں';

  @override
  String get shareViaSms => 'SMS کے ذریعے شیئر کریں';

  @override
  String get selectContactsToShareSummary => 'اپنی بات چیت کا خلاصہ شیئر کرنے کے لیے رابطے منتخب کریں';

  @override
  String get searchContactsHint => 'رابطے تلاش کریں...';

  @override
  String contactsSelectedCount(int count) {
    return '$count منتخب';
  }

  @override
  String get clearAllSelection => 'تمام صاف کریں';

  @override
  String get selectContactsToShare => 'شیئر کرنے کے لیے رابطے منتخب کریں';

  @override
  String shareWithContactCount(int count) {
    return '$count رابطے کے ساتھ شیئر کریں';
  }

  @override
  String shareWithContactsCount(int count) {
    return '$count رابطوں کے ساتھ شیئر کریں';
  }

  @override
  String get contactsPermissionRequired => 'رابطوں کی اجازت درکار ہے';

  @override
  String get contactsPermissionRequiredForSms => 'SMS کے ذریعے شیئر کرنے کے لیے رابطوں کی اجازت درکار ہے';

  @override
  String get grantContactsPermissionForSms => 'براہ کرم SMS کے ذریعے شیئر کرنے کے لیے رابطوں کی اجازت دیں';

  @override
  String get noContactsWithPhoneNumbers => 'فون نمبروں والے کوئی رابطے نہیں ملے';

  @override
  String get noContactsMatchSearch => 'آپ کی تلاش سے کوئی رابطے نہیں ملے';

  @override
  String get failedToLoadContacts => 'رابطے لوڈ کرنے میں ناکام';

  @override
  String get failedToPrepareConversationForSharing =>
      'شیئرنگ کے لیے بات چیت کی تیاری میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get couldNotOpenSmsApp => 'SMS ایپ نہیں کھول سکا۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'یہاں وہ ہے جس پر ہم نے ابھی بات کی: $link';
  }

  @override
  String get wifiSync => 'WiFi ہم آہنگی';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item کلپ بورڈ میں کاپی کیا گیا';
  }

  @override
  String get wifiConnectionFailedTitle => 'کنکشن ناکام';

  @override
  String connectingToDeviceName(String deviceName) {
    return '$deviceName سے متصل ہو رہے ہیں';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return '$deviceName کا WiFi فعال کریں';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return '$deviceName سے متصل کریں';
  }

  @override
  String get recordingDetails => 'ریکارڈنگ کی تفصیلات';

  @override
  String get storageLocationSdCard => 'SD کارڈ';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'فون';

  @override
  String get storageLocationPhoneMemory => 'فون (میموری)';

  @override
  String storedOnDevice(String deviceName) {
    return '$deviceName پر محفوظ';
  }

  @override
  String get transferring => 'منتقل کیا جا رہا ہے...';

  @override
  String get transferRequired => 'منتقلی درکار ہے';

  @override
  String get downloadingAudioFromSdCard => 'آپ کے ڈیوائس کے SD کارڈ سے آڈیو ڈاؤن لوڈ کیا جا رہا ہے';

  @override
  String get transferRequiredDescription =>
      'یہ ریکارڈنگ آپ کے ڈیوائس کے SD کارڈ پر محفوظ ہے۔ اسے اپنے فون میں منتقل کریں تاکہ اسے چلا سکیں یا شیئر کر سکیں۔';

  @override
  String get cancelTransfer => 'منتقلی منسوخ کریں';

  @override
  String get transferToPhone => 'فون میں منتقل کریں';

  @override
  String get privateAndSecureOnDevice => 'آپ کے ڈیوائس پر نجی اور محفوظ';

  @override
  String get recordingInfo => 'ریکارڈنگ کی معلومات';

  @override
  String get transferInProgress => 'ٹرانسفر جاری ہے...';

  @override
  String get shareRecording => 'ریکارڈنگ شیئر کریں';

  @override
  String get deleteRecordingConfirmation =>
      'کیا آپ یقینی ہیں کہ آپ یہ ریکارڈنگ مستقل طور پر ڈیلیٹ کرنا چاہتے ہیں؟ یہ واپس نہیں کیا جا سکتا۔';

  @override
  String get recordingIdLabel => 'ریکارڈنگ ID';

  @override
  String get dateTimeLabel => 'تاریخ اور وقت';

  @override
  String get durationLabel => 'مدت';

  @override
  String get audioFormatLabel => 'آڈیو فارمیٹ';

  @override
  String get storageLocationLabel => 'اسٹوریج کی جگہ';

  @override
  String get estimatedSizeLabel => 'تخمینہ سائز';

  @override
  String get deviceModelLabel => 'ڈیوائس ماڈل';

  @override
  String get deviceIdLabel => 'ڈیوائس ID';

  @override
  String get statusLabel => 'حالت';

  @override
  String get statusProcessed => 'پروسیس شدہ';

  @override
  String get statusUnprocessed => 'غیر پروسیس شدہ';

  @override
  String get switchedToFastTransfer => 'Fast Transfer پر سوئچ کیا گیا';

  @override
  String get transferCompleteMessage => 'ٹرانسفر مکمل! اب آپ یہ ریکارڈنگ چلا سکتے ہیں۔';

  @override
  String transferFailedMessage(String error) {
    return 'ٹرانسفر ناکام: $error';
  }

  @override
  String get transferCancelled => 'ٹرانسفر منسوخ کیا گیا';

  @override
  String get fastTransferEnabled => 'Fast Transfer فعال کیا گیا';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth ہم آہنگی فعال کی گئی';

  @override
  String get enableFastTransfer => 'Fast Transfer فعال کریں';

  @override
  String get fastTransferDescription =>
      'Fast Transfer WiFi استعمال کرتے ہوئے تقریباً 5 گنا تیز رفتار ہے۔ ٹرانسفر کے دوران آپ کا فون عارضی طور پر آپ کے Omi ڈیوائس کے WiFi نیٹ ورک سے منسلک ہوگا۔';

  @override
  String get internetAccessPausedDuringTransfer => 'ٹرانسفر کے دوران انٹرنیٹ رسائی موقوف ہے';

  @override
  String get chooseTransferMethodDescription =>
      'آپ کے Omi ڈیوائس سے آپ کے فون تک ریکارڈنگز کو منتقل کرنے کا طریقہ منتخب کریں۔';

  @override
  String get wifiSpeed => 'WiFi کے ذریعے ~150 KB/s';

  @override
  String get fiveTimesFaster => '5 گنا تیز رفتار';

  @override
  String get fastTransferMethodDescription =>
      'آپ کے Omi ڈیوائس کے ساتھ براہ راست WiFi کنکشن بناتا ہے۔ ٹرانسفر کے دوران آپ کا فون عارضی طور پر آپ کے معمول کے WiFi سے منقطع ہوتا ہے۔';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => 'BLE کے ذریعے ~30 KB/s';

  @override
  String get bluetoothMethodDescription =>
      'معیاری Bluetooth Low Energy کنکشن استعمال کرتا ہے۔ سست ہے لیکن آپ کے WiFi کنکشن کو متاثر نہیں کرتا۔';

  @override
  String get selected => 'منتخب';

  @override
  String get selectOption => 'منتخب کریں';

  @override
  String get lowBatteryAlertTitle => 'کم بیٹری الرٹ';

  @override
  String get lowBatteryAlertBody => 'آپ کا ڈیوائس بیٹری میں کم ہو رہا ہے۔ دوبارہ چارج کرنے کا وقت! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'آپ کا Omi ڈیوائس منقطع ہو گیا';

  @override
  String get deviceDisconnectedNotificationBody => 'براہ کرم اپنے Omi کو استعمال جاری رکھنے کے لیے دوبارہ منسلک کریں۔';

  @override
  String get firmwareUpdateAvailable => 'فرم ویئر اپڈیٹ دستیاب ہے';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'آپ کے Omi ڈیوائس کے لیے ایک نیا فرم ویئر اپڈیٹ ($version) دستیاب ہے۔ کیا آپ ابھی اپڈیٹ کرنا چاہتے ہیں؟';
  }

  @override
  String get later => 'بعد میں';

  @override
  String get appDeletedSuccessfully => 'ایپ کامیابی سے حذف کر دی گئی';

  @override
  String get appDeleteFailed => 'ایپ حذف کرنے میں ناکام۔ براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get appVisibilityChangedSuccessfully =>
      'ایپ کی نمائندگی کامیابی سے تبدیل کر دی گئی۔ اس میں کچھ منٹ لگ سکتے ہیں۔';

  @override
  String get errorActivatingAppIntegration =>
      'ایپ کو فعال کرنے میں خرابی۔ اگر یہ انضمام ایپ ہے، تو اس بات کو یقینی بنائیں کہ سیٹ اپ مکمل ہو گیا ہے۔';

  @override
  String get errorUpdatingAppStatus => 'ایپ کی حالت کو اپڈیٹ کرتے ہوئے ایک خرابی واقع ہوئی۔';

  @override
  String get calculatingETA => 'شمار ہو رہا ہے...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'تقریباً $minutes منٹ باقی ہے';
  }

  @override
  String get aboutAMinuteRemaining => 'تقریباً ایک منٹ باقی ہے';

  @override
  String get almostDone => 'تقریباً ختم ہو گیا...';

  @override
  String get omiSays => 'omi کہتا ہے';

  @override
  String get analyzingYourData => 'آپ کے ڈیٹا کا تجزیہ جاری ہے...';

  @override
  String migratingToProtection(String level) {
    return '$level حفاظت میں منتقل کیا جا رہا ہے...';
  }

  @override
  String get noDataToMigrateFinalizing => 'منتقل کرنے کے لیے کوئی ڈیٹا نہیں۔ حتمی کیا جا رہا ہے...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType منتقل کیا جا رہا ہے... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'تمام اشیاء منتقل کر دی گئی ہیں۔ حتمی کیا جا رہا ہے...';

  @override
  String get migrationErrorOccurred => 'منتقلی کے دوران ایک خرابی واقع ہوئی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get migrationComplete => 'منتقلی مکمل!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'آپ کا ڈیٹا اب نئی $level ترتیبات کے ساتھ محفوظ ہے۔';
  }

  @override
  String get chatsLowercase => 'بات چیت';

  @override
  String get dataLowercase => 'ڈیٹا';

  @override
  String get fallNotificationTitle => 'آؤ';

  @override
  String get fallNotificationBody => 'کیا آپ گر گئے؟';

  @override
  String get importantConversationTitle => 'اہم بات چیت';

  @override
  String get importantConversationBody =>
      'آپ نے ابھی اہم بات چیت کی۔ دوسروں کے ساتھ خلاصہ شیئر کرنے کے لیے تھپتھپائیں۔';

  @override
  String get templateName => 'ٹیمپلیٹ کا نام';

  @override
  String get templateNameHint => 'مثال کے طور پر، میٹنگ ایکشن آئٹمز نکالنے والا';

  @override
  String get nameMustBeAtLeast3Characters => 'نام کم از کم 3 حروف ہونا چاہیے';

  @override
  String get conversationPromptHint => 'مثال کے طور پر، فراہم کردہ بات چیت سے ایکشن آئٹمز، فیصلے، اور اہم نکات نکالیں۔';

  @override
  String get pleaseEnterAppPrompt => 'براہ کرم اپنی ایپ کے لیے ایک اشارہ درج کریں';

  @override
  String get promptMustBeAtLeast10Characters => 'اشارہ کم از کم 10 حروف ہونا چاہیے';

  @override
  String get anyoneCanDiscoverTemplate => 'کوئی بھی آپ کی ٹیمپلیٹ کو دریافت کر سکتا ہے';

  @override
  String get onlyYouCanUseTemplate => 'صرف آپ اس ٹیمپلیٹ کو استعمال کر سکتے ہیں';

  @override
  String get generatingDescription => 'تفصیل تیار کی جا رہی ہے...';

  @override
  String get creatingAppIcon => 'ایپ کا آئکن بنایا جا رہا ہے...';

  @override
  String get installingApp => 'ایپ انسٹال کی جا رہی ہے...';

  @override
  String get appCreatedAndInstalled => 'ایپ بنائی گئی اور انسٹال کی گئی!';

  @override
  String get appCreatedSuccessfully => 'ایپ کامیابی سے بنائی گئی!';

  @override
  String get failedToCreateApp => 'ایپ بنانے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get addAppSelectCoreCapability => 'براہ کرم اپنی ایپ کو آگے بڑھانے کے لیے ایک اور بنیادی صلاحیت منتخب کریں';

  @override
  String get addAppSelectPaymentPlan => 'براہ کرم اپنی ایپ کے لیے ایک ادائیگی کا منصوبہ منتخب کریں اور قیمت درج کریں';

  @override
  String get addAppSelectCapability => 'براہ کرم اپنی ایپ کے لیے کم از کم ایک صلاحیت منتخب کریں';

  @override
  String get addAppSelectLogo => 'براہ کرم اپنی ایپ کے لیے ایک لوگو منتخب کریں';

  @override
  String get addAppEnterChatPrompt => 'براہ کرم اپنی ایپ کے لیے ایک چیٹ اشارہ درج کریں';

  @override
  String get addAppEnterConversationPrompt => 'براہ کرم اپنی ایپ کے لیے ایک بات چیت کا اشارہ درج کریں';

  @override
  String get addAppSelectTriggerEvent => 'براہ کرم اپنی ایپ کے لیے ایک ٹریگر ایونٹ منتخب کریں';

  @override
  String get addAppEnterWebhookUrl => 'براہ کرم اپنی ایپ کے لیے ایک webhook URL درج کریں';

  @override
  String get addAppSelectCategory => 'براہ کرم اپنی ایپ کے لیے ایک زمرہ منتخب کریں';

  @override
  String get addAppFillRequiredFields => 'براہ کرم تمام ضروری فیلڈز کو صحیح طریقے سے بھریں';

  @override
  String get addAppUpdatedSuccess => 'ایپ کامیابی سے اپڈیٹ کی گئی 🚀';

  @override
  String get addAppUpdateFailed => 'ایپ اپڈیٹ میں ناکام۔ براہ کرم بعد میں دوبارہ کوشش کریں';

  @override
  String get addAppSubmittedSuccess => 'ایپ کامیابی سے جمع کی گئی 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'فائل پیکر کھولنے میں خرابی: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'تصویر منتخب کرنے میں خرابی: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'فوٹوز کی اجازت مسترد کر دی گئی۔ براہ کرم تصویر منتخب کرنے کے لیے فوٹوز تک رسائی کی اجازت دیں';

  @override
  String get addAppErrorSelectingImageRetry => 'تصویر منتخب کرنے میں خرابی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'تھمب نیل منتخب کرنے میں خرابی: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'تھمب نیل منتخب کرنے میں خرابی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get addAppCapabilityConflictWithPersona => 'Persona کے ساتھ دوسری صلاحیتوں کو منتخب نہیں کیا جا سکتا';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona کو دوسری صلاحیتوں کے ساتھ منتخب نہیں کیا جا سکتا';

  @override
  String get paymentFailedToFetchCountries => 'معاون ممالک حاصل کرنے میں ناکام۔ براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get paymentFailedToSetDefault =>
      'ڈیفالٹ ادائیگی کا طریقہ سیٹ کرنے میں ناکام۔ براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get paymentFailedToSavePaypal => 'PayPal تفصیلات محفوظ کرنے میں ناکام۔ براہ کرم بعد میں دوبارہ کوشش کریں۔';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'فعال';

  @override
  String get paymentStatusConnected => 'منسلک';

  @override
  String get paymentStatusNotConnected => 'منسلک نہیں';

  @override
  String get paymentAppCost => 'ایپ کی لاگت';

  @override
  String get paymentEnterValidAmount => 'براہ کرم ایک درست رقم درج کریں';

  @override
  String get paymentEnterAmountGreaterThanZero => 'براہ کرم 0 سے زیادہ رقم درج کریں';

  @override
  String get paymentPlan => 'ادائیگی کا منصوبہ';

  @override
  String get paymentNoneSelected => 'کوئی منتخب نہیں';

  @override
  String get aiGenPleaseEnterDescription => 'براہ کرم اپنی ایپ کے لیے ایک تفصیل درج کریں';

  @override
  String get aiGenCreatingAppIcon => 'ایپ کا آئکن بنایا جا رہا ہے...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'ایک خرابی واقع ہوئی: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'ایپ کامیابی سے بنائی گئی!';

  @override
  String get aiGenFailedToCreateApp => 'ایپ بنانے میں ناکام';

  @override
  String get aiGenErrorWhileCreatingApp => 'ایپ بنانے میں خرابی واقع ہوئی';

  @override
  String get aiGenFailedToGenerateApp => 'ایپ بنانے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get aiGenFailedToRegenerateIcon => 'آئکن دوبارہ تیار کرنے میں ناکام';

  @override
  String get aiGenPleaseGenerateAppFirst => 'براہ کرم پہلے ایک ایپ تیار کریں';

  @override
  String get nextButton => 'اگلا';

  @override
  String get connectOmiDevice => 'Omi ڈیوائس سے منسلک ہوں';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'آپ اپنی Unlimited منصوبہ کو $title میں تبدیل کر رہے ہیں۔ کیا آپ آگے بڑھنا چاہتے ہیں؟';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'اپ گریڈ شیڈول کیا گیا! آپ کا ماہانہ منصوبہ آپ کی بلنگ مدت کے آخر تک جاری رہتا ہے، پھر خودکار طریقے سے سالانہ میں تبدیل ہو جاتا ہے۔';

  @override
  String get couldNotSchedulePlanChange => 'منصوبے کی تبدیلی شیڈول نہیں کی جا سکی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get subscriptionReactivatedDefault =>
      'آپ کی رکنیت دوبارہ فعال کر دی گئی ہے! ابھی کوئی خرچ نہیں - آپ کو اپنی موجودہ مدت کے آخر میں بل دیا جائے گا۔';

  @override
  String get subscriptionSuccessfulCharged => 'سبسکرپشن کامیاب! آپ سے نئی بلنگ مدت کے لیے چارج کیا گیا ہے۔';

  @override
  String get couldNotProcessSubscription => 'سبسکرپشن پروسیس نہیں کیا جا سکا۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get couldNotLaunchUpgradePage => 'اپ گریڈ صفحہ شروع نہیں کیا جا سکا۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get transcriptionJsonPlaceholder => 'اپنی JSON ترتیب یہاں پیسٹ کریں...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'فائل پیکر کھولنے میں خرابی: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'خرابی: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'بات چیتیں کامیابی سے ملائی گئیں';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count بات چیتیں کامیابی سے ملائی گئیں';
  }

  @override
  String get actionItemReminderTitle => 'Omi یادگار';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName منقطع ہو گیا';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'براہ کرم اپنے $deviceName کو استعمال جاری رکھنے کے لیے دوبارہ منسلک کریں۔';
  }

  @override
  String get onboardingSignIn => 'سائن ان کریں';

  @override
  String get onboardingYourName => 'آپ کا نام';

  @override
  String get onboardingLanguage => 'زبان';

  @override
  String get onboardingPermissions => 'اجازتیں';

  @override
  String get onboardingComplete => 'مکمل';

  @override
  String get onboardingWelcomeToOmi => 'Omi میں خوش آمدید';

  @override
  String get onboardingTellUsAboutYourself => 'ہمیں اپنے بارے میں بتائیں';

  @override
  String get onboardingChooseYourPreference => 'اپنی پسند منتخب کریں';

  @override
  String get onboardingGrantRequiredAccess => 'ضروری رسائی دیں';

  @override
  String get onboardingYoureAllSet => 'آپ تیار ہیں';

  @override
  String get searchTranscriptOrSummary => 'ٹرانسکرپٹ یا خلاصہ تلاش کریں...';

  @override
  String get myGoal => 'میرا مقصد';

  @override
  String get appNotAvailable => 'افسوس! ایسا لگتا ہے کہ جو ایپ آپ تلاش کر رہے ہیں وہ دستیاب نہیں ہے۔';

  @override
  String get failedToConnectTodoist => 'Todoist سے منسلک ہونے میں ناکام';

  @override
  String get failedToConnectAsana => 'Asana سے منسلک ہونے میں ناکام';

  @override
  String get failedToConnectGoogleTasks => 'Google Tasks سے منسلک ہونے میں ناکام';

  @override
  String get failedToConnectClickUp => 'ClickUp سے منسلک ہونے میں ناکام';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName سے منسلک ہونے میں ناکام: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Todoist سے کامیابی سے منسلک!';

  @override
  String get failedToConnectTodoistRetry => 'Todoist سے منسلک ہونے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get successfullyConnectedAsana => 'Asana سے کامیابی سے منسلک!';

  @override
  String get failedToConnectAsanaRetry => 'Asana سے منسلک ہونے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get successfullyConnectedGoogleTasks => 'Google Tasks سے کامیابی سے منسلک!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Google Tasks سے منسلک ہونے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get successfullyConnectedClickUp => 'ClickUp سے کامیابی سے منسلک!';

  @override
  String get failedToConnectClickUpRetry => 'ClickUp سے منسلک ہونے میں ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get successfullyConnectedNotion => 'Notion سے کامیابی سے منسلک!';

  @override
  String get failedToRefreshNotionStatus => 'Notion کنکشن کی حالت تازہ کرنے میں ناکام۔';

  @override
  String get successfullyConnectedGoogle => 'Google سے کامیابی سے منسلک!';

  @override
  String get failedToRefreshGoogleStatus => 'Google کنکشن کی حالت تازہ کرنے میں ناکام۔';

  @override
  String get successfullyConnectedWhoop => 'Whoop سے کامیابی سے منسلک!';

  @override
  String get failedToRefreshWhoopStatus => 'Whoop کنکشن کی حالت تازہ کرنے میں ناکام۔';

  @override
  String get successfullyConnectedGitHub => 'GitHub سے کامیابی سے منسلک!';

  @override
  String get failedToRefreshGitHubStatus => 'GitHub کنکشن کی حالت تازہ کرنے میں ناکام۔';

  @override
  String get authFailedToSignInWithGoogle => 'Google کے ساتھ سائن ان میں ناکام، براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get authenticationFailed => 'تصدیق ناکام۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get authFailedToSignInWithApple => 'Apple کے ساتھ سائن ان میں ناکام، براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get authFailedToRetrieveToken => 'Firebase ٹوکن حاصل کرنے میں ناکام، براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get authUnexpectedErrorFirebase => 'سائن ان میں غیر متوقع خرابی، Firebase خرابی، براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get authUnexpectedError => 'سائن ان میں غیر متوقع خرابی، براہ کرم دوبارہ کوشش کریں';

  @override
  String get authFailedToLinkGoogle => 'Google سے لنک کرنے میں ناکام، براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get authFailedToLinkApple => 'Apple سے لنک کرنے میں ناکام، براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get onboardingBluetoothRequired => 'آپ کے ڈیوائس سے منسلک ہونے کے لیے Bluetooth اجازت ضروری ہے۔';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetooth اجازت مسترد کر دی گئی۔ براہ کرم سسٹم ترجیحات میں اجازت دیں۔';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetooth اجازت کی حالت: $status۔ براہ کرم سسٹم ترجیحات چیک کریں۔';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetooth اجازت چیک کرنے میں ناکام: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'اطلاع اجازت مسترد کر دی گئی۔ براہ کرم سسٹم ترجیحات میں اجازت دیں۔';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'اطلاع اجازت مسترد کر دی گئی۔ براہ کرم سسٹم ترجیحات > اطلاعات میں اجازت دیں۔';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'اطلاع اجازت کی حالت: $status۔ براہ کرم سسٹم ترجیحات چیک کریں۔';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'اطلاع اجازت چیک کرنے میں ناکام: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'براہ کرم ترتیبات > رازداری اور سیکیورٹی > مقام کی خدمات میں مقام کی اجازت دیں';

  @override
  String get onboardingMicrophoneRequired => 'ریکارڈنگ کے لیے مائیکروفون اجازت ضروری ہے۔';

  @override
  String get onboardingMicrophoneDenied =>
      'مائیکروفون اجازت مسترد کر دی گئی۔ براہ کرم سسٹم ترجیحات > رازداری اور سیکیورٹی > مائیکروفون میں اجازت دیں۔';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'مائیکروفون اجازت کی حالت: $status۔ براہ کرم سسٹم ترجیحات چیک کریں۔';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'مائیکروفون اجازت چیک کرنے میں ناکام: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'سسٹم آڈیو ریکارڈنگ کے لیے اسکرین کیپچر اجازت ضروری ہے۔';

  @override
  String get onboardingScreenCaptureDenied =>
      'اسکرین کیپچر اجازت مسترد کر دی گئی۔ براہ کرم سسٹم ترجیحات > رازداری اور سیکیورٹی > اسکرین ریکارڈنگ میں اجازت دیں۔';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'اسکرین کیپچر اجازت کی حالت: $status۔ براہ کرم سسٹم ترجیحات چیک کریں۔';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'اسکرین کیپچر اجازت چیک کرنے میں ناکام: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'براؤزر میٹنگز کا پتہ لگانے کے لیے رسائی کی اجازت ضروری ہے۔';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'رسائی اجازت کی حالت: $status۔ براہ کرم سسٹم ترجیحات چیک کریں۔';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'رسائی اجازت چیک کرنے میں ناکام: $error';
  }

  @override
  String get msgCameraNotAvailable => 'اس پلیٹ فارم پر کیمرہ کیپچر دستیاب نہیں ہے';

  @override
  String get msgCameraPermissionDenied => 'کیمرہ اجازت مسترد کر دی گئی۔ براہ کرم کیمرے تک رسائی کی اجازت دیں';

  @override
  String msgCameraAccessError(String error) {
    return 'کیمرہ تک رسائی میں خرابی: $error';
  }

  @override
  String get msgPhotoError => 'فوٹو لینے میں خرابی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get msgMaxImagesLimit => 'آپ صرف 4 تصاویر تک منتخب کر سکتے ہیں';

  @override
  String msgFilePickerError(String error) {
    return 'فائل پیکر کھولنے میں خرابی: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'تصاویر منتخب کرنے میں خرابی: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'فوٹوز کی اجازت مسترد کر دی گئی۔ براہ کرم تصاویر منتخب کرنے کے لیے فوٹوز تک رسائی کی اجازت دیں';

  @override
  String get msgSelectImagesGenericError => 'تصاویر منتخب کرنے میں خرابی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get msgMaxFilesLimit => 'آپ صرف 4 فائلیں تک منتخب کر سکتے ہیں';

  @override
  String msgSelectFilesError(String error) {
    return 'فائلیں منتخب کرنے میں خرابی: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'فائلیں منتخب کرنے میں خرابی۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get msgUploadFileFailed => 'فائل اپ لوڈ میں ناکام، براہ کرم بعد میں دوبارہ کوشش کریں';

  @override
  String get msgReadingMemories => 'آپ کی یادوں کو پڑھا جا رہا ہے...';

  @override
  String get msgLearningMemories => 'آپ کی یادوں سے سیکھا جا رہا ہے...';

  @override
  String get msgUploadAttachedFileFailed => 'منسلک فائل اپ لوڈ میں ناکام۔';

  @override
  String captureRecordingError(String error) {
    return 'ریکارڈنگ کے دوران ایک خرابی واقع ہوئی: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'ریکارڈنگ بند ہو گئی: $reason۔ آپ کو بیرونی ڈسپلے دوبارہ منسلک کرنے یا ریکارڈنگ دوبارہ شروع کرنے کی ضرورت ہو سکتی ہے۔';
  }

  @override
  String get captureMicrophonePermissionRequired => 'مائیکروفون اجازت ضروری ہے';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'سسٹم ترجیحات میں مائیکروفون اجازت دیں';

  @override
  String get captureScreenRecordingPermissionRequired => 'اسکرین ریکارڈنگ کی اجازت ضروری ہے';

  @override
  String get captureDisplayDetectionFailed => 'ڈسپلے کی شناخت ناکام۔ ریکارڈنگ بند ہو گئی۔';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'غلط آڈیو بائٹس webhook URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'غلط حقیقی وقت کے ٹرانسکرپٹ webhook URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'غلط بات چیت بنائی گئی webhook URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'غلط دن کا خلاصہ webhook URL';

  @override
  String get devModeSettingsSaved => 'ترتیبات محفوظ!';

  @override
  String get voiceFailedToTranscribe => 'آڈیو کو ٹرانسکرائب کرنے میں ناکام';

  @override
  String get locationPermissionRequired => 'مقام کی اجازت ضروری ہے';

  @override
  String get locationPermissionContent =>
      'Fast Transfer کو WiFi کنکشن کی تصدیق کے لیے مقام کی اجازت ضروری ہے۔ براہ کرم جاری رکھنے کے لیے مقام کی اجازت دیں۔';

  @override
  String get pdfTranscriptExport => 'ٹرانسکرپٹ برآمد';

  @override
  String get pdfConversationExport => 'بات چیت برآمد';

  @override
  String pdfTitleLabel(String title) {
    return 'عنوان: $title';
  }

  @override
  String get conversationNewIndicator => 'نیا 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count فوٹوز';
  }

  @override
  String get mergingStatus => 'ملایا جا رہا ہے...';

  @override
  String timeSecsSingular(int count) {
    return '$count سیکنڈ';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count سیکنڈ';
  }

  @override
  String timeMinSingular(int count) {
    return '$count منٹ';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count منٹ';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins منٹ $secs سیکنڈ';
  }

  @override
  String timeHourSingular(int count) {
    return '$count گھنٹہ';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count گھنٹے';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours گھنٹے $mins منٹ';
  }

  @override
  String timeDaySingular(int count) {
    return '$count دن';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count دن';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days دن $hours گھنٹے';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countس';
  }

  @override
  String timeCompactMins(int count) {
    return '$countم';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsم $secsس';
  }

  @override
  String timeCompactHours(int count) {
    return '$countگ';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursگ $minsم';
  }

  @override
  String get moveToFolder => 'فولڈر میں منتقل کریں';

  @override
  String get noFoldersAvailable => 'کوئی فولڈر دستیاب نہیں';

  @override
  String get newFolder => 'نیا فولڈر';

  @override
  String get color => 'رنگ';

  @override
  String get waitingForDevice => 'ڈیوائس کی انتظار ہو رہی ہے...';

  @override
  String get saySomething => 'کچھ کہیں...';

  @override
  String get initialisingSystemAudio => 'سسٹم آڈیو شروع کیا جا رہا ہے';

  @override
  String get stopRecording => 'ریکارڈنگ روکیں';

  @override
  String get continueRecording => 'ریکارڈنگ جاری رکھیں';

  @override
  String get initialisingRecorder => 'ریکارڈر شروع کیا جا رہا ہے';

  @override
  String get pauseRecording => 'ریکارڈنگ موقوف کریں';

  @override
  String get resumeRecording => 'ریکارڈنگ دوبارہ شروع کریں';

  @override
  String get noDailyRecapsYet => 'ابھی کوئی روزانہ خلاصہ نہیں';

  @override
  String get dailyRecapsDescription => 'آپ کے روزانہ خلاصے یہاں ظاہر ہوں گے جب تیار ہو جائیں';

  @override
  String get chooseTransferMethod => 'ٹرانسفر کا طریقہ منتخب کریں';

  @override
  String get fastTransferSpeed => 'WiFi کے ذریعے ~150 KB/s';

  @override
  String largeTimeGapDetected(String gap) {
    return 'بڑے وقت کا فاصلہ دیکھا گیا ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'بڑے وقت کے فاصلے دیکھے گئے ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'ڈیوائس WiFi ہم آہنگی کو سپورٹ نہیں کرتا، Bluetooth پر سوئچ کیا جا رہا ہے';

  @override
  String get appleHealthNotAvailable => 'Apple Health اس ڈیوائس پر دستیاب نہیں ہے';

  @override
  String get downloadAudio => 'آڈیو ڈاؤن لوڈ کریں';

  @override
  String get audioDownloadSuccess => 'آڈیو کامیابی سے ڈاؤن لوڈ ہو گیا';

  @override
  String get audioDownloadFailed => 'آڈیو ڈاؤن لوڈ میں ناکام';

  @override
  String get downloadingAudio => 'آڈیو ڈاؤن لوڈ کیا جا رہا ہے...';

  @override
  String get shareAudio => 'آڈیو شیئر کریں';

  @override
  String get preparingAudio => 'آڈیو تیار کیا جا رہا ہے';

  @override
  String get gettingAudioFiles => 'آڈیو فائلیں حاصل کی جا رہی ہیں...';

  @override
  String get downloadingAudioProgress => 'آڈیو ڈاؤن لوڈ کیا جا رہا ہے';

  @override
  String get processingAudio => 'آڈیو پروسیس کیا جا رہا ہے';

  @override
  String get combiningAudioFiles => 'آڈیو فائلیں ملائی جا رہی ہیں...';

  @override
  String get audioReady => 'آڈیو تیار ہے';

  @override
  String get openingShareSheet => 'شیئر شیٹ کھولی جا رہی ہے...';

  @override
  String get audioShareFailed => 'شیئر ناکام';

  @override
  String get dailyRecaps => 'روزانہ خلاصے';

  @override
  String get removeFilter => 'فلٹر ہٹائیں';

  @override
  String get categoryConversationAnalysis => 'بات چیت کا تجزیہ';

  @override
  String get categoryHealth => 'صحت';

  @override
  String get categoryEducation => 'تعلیم';

  @override
  String get categoryCommunication => 'رابطہ';

  @override
  String get categoryEmotionalSupport => 'جذباتی معاونت';

  @override
  String get categoryProductivity => 'پروڈکٹیویٹی';

  @override
  String get categoryEntertainment => 'تفریح';

  @override
  String get categoryFinancial => 'مالیاتی';

  @override
  String get categoryTravel => 'سفر';

  @override
  String get categorySafety => 'حفاظت';

  @override
  String get categoryShopping => 'خریداری';

  @override
  String get categorySocial => 'سوشل';

  @override
  String get categoryNews => 'خبریں';

  @override
  String get categoryUtilities => 'یوٹیلٹیز';

  @override
  String get categoryOther => 'دیگر';

  @override
  String get capabilityChat => 'چیٹ';

  @override
  String get capabilityConversations => 'بات چیتیں';

  @override
  String get capabilityExternalIntegration => 'بیرونی انضمام';

  @override
  String get capabilityNotification => 'اطلاع';

  @override
  String get triggerAudioBytes => 'آڈیو بائٹس';

  @override
  String get triggerConversationCreation => 'بات چیت کی تخلیق';

  @override
  String get triggerTranscriptProcessed => 'ٹرانسکرپٹ پروسیس شدہ';

  @override
  String get actionCreateConversations => 'بات چیتیں بنائیں';

  @override
  String get actionCreateMemories => 'یادیں بنائیں';

  @override
  String get actionReadConversations => 'بات چیتیں پڑھیں';

  @override
  String get actionReadMemories => 'یادیں پڑھیں';

  @override
  String get actionReadTasks => 'کام پڑھیں';

  @override
  String get scopeUserName => 'صارف کا نام';

  @override
  String get scopeUserFacts => 'صارف کے حقائق';

  @override
  String get scopeUserConversations => 'صارف کی بات چیتیں';

  @override
  String get scopeUserChat => 'صارف کی چیٹ';

  @override
  String get capabilitySummary => 'خلاصہ';

  @override
  String get capabilityFeatured => 'خصوصی';

  @override
  String get capabilityTasks => 'کام';

  @override
  String get capabilityIntegrations => 'انضمامات';

  @override
  String get categoryProductivityLifestyle => 'پروڈکٹیویٹی اور طرز زندگی';

  @override
  String get categorySocialEntertainment => 'سوشل اور تفریح';

  @override
  String get categoryProductivityTools => 'پروڈکٹیویٹی اور ٹولز';

  @override
  String get categoryPersonalWellness => 'ذاتی اور طرز زندگی';

  @override
  String get rating => 'ریٹنگ';

  @override
  String get categories => 'زمرے';

  @override
  String get sortBy => 'ترتیب دیں';

  @override
  String get highestRating => 'سب سے زیادہ ریٹنگ';

  @override
  String get lowestRating => 'سب سے کم ریٹنگ';

  @override
  String get resetFilters => 'فلٹرز ری سیٹ کریں';

  @override
  String get applyFilters => 'فلٹرز لاگو کریں';

  @override
  String get mostInstalls => 'سب سے زیادہ انسٹالز';

  @override
  String get couldNotOpenUrl => 'URL کھول نہیں سکے۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get newTask => 'نیا کام';

  @override
  String get viewAll => 'سب دیکھیں';

  @override
  String get addTask => 'کام شامل کریں';

  @override
  String get addMcpServer => 'MCP سرور شامل کریں';

  @override
  String get connectExternalAiTools => 'بیرونی AI ٹولز کو منسلک کریں';

  @override
  String get mcpServerUrl => 'MCP سرور URL';

  @override
  String mcpServerConnected(int count) {
    return '$count ٹولز کامیابی سے منسلک ہو گئے';
  }

  @override
  String get mcpConnectionFailed => 'MCP سرور سے منسلک ہونا ناکام';

  @override
  String get authorizingMcpServer => 'اختیار دیا جا رہا ہے...';

  @override
  String get whereDidYouHearAboutOmi => 'آپ نے ہم سے کہاں سنا؟';

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
  String get friendWordOfMouth => 'دوست';

  @override
  String get otherSource => 'دیگر';

  @override
  String get pleaseSpecify => 'براہ کرم واضح کریں';

  @override
  String get event => 'پروگرام';

  @override
  String get coworker => 'کام کے ساتھی';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google تلاش';

  @override
  String get audioPlaybackUnavailable => 'آڈیو فائل چلانے کے لیے دستیاب نہیں ہے';

  @override
  String get audioPlaybackFailed => 'آڈیو چلانے میں ناکام۔ فائل خراب ہو سکتی ہے یا غائب ہو سکتی ہے۔';

  @override
  String get connectionGuide => 'منسلکی گائیڈ';

  @override
  String get iveDoneThis => 'میں نے یہ کیا ہے';

  @override
  String get pairNewDevice => 'نیا ڈیوائس جوڑیں';

  @override
  String get dontSeeYourDevice => 'اپنا ڈیوائس نہیں دیکھ رہے؟';

  @override
  String get reportAnIssue => 'مسئلہ رپورٹ کریں';

  @override
  String get pairingTitleOmi => 'Omi کو چلائیں';

  @override
  String get pairingDescOmi => 'ڈیوائس کو چلانے کے لیے دبائے رکھیں جب تک یہ کمپن نہ کرے۔';

  @override
  String get pairingTitleOmiDevkit => 'Omi DevKit کو جوڑنے کی حالت میں رکھیں';

  @override
  String get pairingDescOmiDevkit =>
      'چلانے کے لیے بٹن کو ایک بار دبائیں۔ جوڑنے کی حالت میں LED بنفشی رنگ میں جھلکے گی۔';

  @override
  String get pairingTitleOmiGlass => 'Omi Glass کو چلائیں';

  @override
  String get pairingDescOmiGlass => 'سائیڈ بٹن کو 3 سیکنڈ کے لیے دبا کر چلائیں۔';

  @override
  String get pairingTitlePlaudNote => 'Plaud Note کو جوڑنے کی حالت میں رکھیں';

  @override
  String get pairingDescPlaudNote =>
      'سائیڈ بٹن کو 2 سیکنڈ کے لیے دبائے رکھیں۔ جوڑنے کے لیے تیار ہونے پر سرخ LED جھلکے گی۔';

  @override
  String get pairingTitleBee => 'Bee کو جوڑنے کی حالت میں رکھیں';

  @override
  String get pairingDescBee => 'بٹن کو 5 بار لگاتار دبائیں۔ روشنی نیلے اور سبز رنگ میں جھلکنا شروع ہوگی۔';

  @override
  String get pairingTitleLimitless => 'Limitless کو جوڑنے کی حالت میں رکھیں';

  @override
  String get pairingDescLimitless =>
      'جب کوئی روشنی نظر آئے تو ایک بار دبائیں اور پھر دبائے رکھیں جب تک ڈیوائس گلابی روشنی نہ دکھائے، پھر چھوڑیں۔';

  @override
  String get pairingTitleFriendPendant => 'Friend Pendant کو جوڑنے کی حالت میں رکھیں';

  @override
  String get pairingDescFriendPendant =>
      'لاکیٹ پر بٹن دبائیں تاکہ یہ چلے۔ یہ خودکار طور پر جوڑنے کی حالت میں داخل ہوگا۔';

  @override
  String get pairingTitleFieldy => 'Fieldy کو جوڑنے کی حالت میں رکھیں';

  @override
  String get pairingDescFieldy => 'روشنی ظاہر ہونے تک ڈیوائس کو دبائے رکھیں تاکہ یہ چلے۔';

  @override
  String get pairingTitleAppleWatch => 'Apple Watch کو منسلک کریں';

  @override
  String get pairingDescAppleWatch =>
      'اپنی Apple Watch پر Omi ایپ کو انسٹال اور کھولیں، پھر ایپ میں Connect کو ٹیپ کریں۔';

  @override
  String get pairingTitleNeoOne => 'Neo One کو جوڑنے کی حالت میں رکھیں';

  @override
  String get pairingDescNeoOne => 'پاور بٹن کو دبائے رکھیں جب تک LED جھلکے۔ ڈیوائس دریافت ہونے کے قابل ہوگا۔';

  @override
  String get downloadingFromDevice => 'ڈیوائس سے ڈاؤن لوڈ ہو رہا ہے';

  @override
  String get reconnectingToInternet => 'انٹرنیٹ سے دوبارہ منسلک ہو رہے ہیں...';

  @override
  String uploadingToCloud(int current, int total) {
    return '$current میں سے $total اپ لوڈ ہو رہے ہیں';
  }

  @override
  String get processingOnServer => 'سرور پر پروسیس ہو رہا ہے...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'پروسیس ہو رہا ہے... $current/$total حصے';
  }

  @override
  String get processedStatus => 'پروسیس شدہ';

  @override
  String get corruptedStatus => 'خراب';

  @override
  String nPending(int count) {
    return '$count زیرِ التوا';
  }

  @override
  String nProcessed(int count) {
    return '$count پروسیس شدہ';
  }

  @override
  String get synced => 'ہم آہنگ';

  @override
  String get noPendingRecordings => 'کوئی زیرِ التوا ریکارڈنگ نہیں';

  @override
  String get noProcessedRecordings => 'ابھی کوئی پروسیس شدہ ریکارڈنگ نہیں';

  @override
  String get pending => 'زیرِ التوا';

  @override
  String whatsNewInVersion(String version) {
    return '$version میں کیا نیا ہے';
  }

  @override
  String get addToYourTaskList => 'اپنی ٹاسک فہرست میں شامل کریں؟';

  @override
  String get failedToCreateShareLink => 'شیئر لنک بنانا ناکام';

  @override
  String get deleteGoal => 'مقصد حذف کریں';

  @override
  String get deviceUpToDate => 'آپ کا ڈیوائس جدید ہے';

  @override
  String get wifiConfiguration => 'WiFi کنفیگریشن';

  @override
  String get wifiConfigurationSubtitle => 'فرم ویئر ڈاؤن لوڈ کرنے کی اجازت دینے کے لیے اپنے WiFi کی اعتبارات درج کریں۔';

  @override
  String get networkNameSsid => 'نیٹ ورک کا نام (SSID)';

  @override
  String get enterWifiNetworkName => 'WiFi نیٹ ورک کا نام درج کریں';

  @override
  String get enterWifiPassword => 'WiFi پاس ورڈ درج کریں';

  @override
  String get appIconLabel => 'ایپ آئیکن';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'یہاں ہے جو میں آپ کے بارے میں جانتا ہوں';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'یہ نقشہ اپڈیٹ ہوتا ہے جب Omi آپ کی بات چیت سے سیکھتا ہے۔';

  @override
  String get apiEnvironment => 'API ماحول';

  @override
  String get apiEnvironmentDescription => 'منتخب کریں کہ کس بیک اینڈ سے منسلک کریں';

  @override
  String get production => 'پروڈکشن';

  @override
  String get staging => 'اسٹیجنگ';

  @override
  String get switchRequiresRestart => 'سوئچ کرنے کے لیے ایپ ری سٹارٹ ضروری ہے';

  @override
  String get switchApiConfirmTitle => 'API ماحول سوئچ کریں';

  @override
  String switchApiConfirmBody(String environment) {
    return '$environment میں سوئچ کریں؟ تبدیلیوں کو نافذ کرنے کے لیے آپ کو ایپ کو بند اور دوبارہ کھولنا ہوگا۔';
  }

  @override
  String get switchAndRestart => 'سوئچ';

  @override
  String get stagingDisclaimer =>
      'اسٹیجنگ خرابیوں سے بھرپور ہو سکتی ہے، غیر مستقل کارکردگی رکھتی ہے، اور ڈیٹا کھو سکتا ہے۔ صرف ٹیسٹنگ کے لیے استعمال کریں۔';

  @override
  String get apiEnvSavedRestartRequired => 'محفوظ ہو گیا۔ لاگو کرنے کے لیے ایپ کو بند اور دوبارہ کھولیں۔';

  @override
  String get shared => 'شیئر شدہ';

  @override
  String get onlyYouCanSeeConversation => 'صرف آپ یہ بات چیت دیکھ سکتے ہیں';

  @override
  String get anyoneWithLinkCanView => 'لنک والا کوئی بھی دیکھ سکتا ہے';

  @override
  String get tasksCleanTodayTitle => 'آج کے ٹاسکس صاف کریں؟';

  @override
  String get tasksCleanTodayMessage => 'یہ صرف مہلت ہٹائے گا';

  @override
  String get tasksOverdue => 'تاخیر سے';

  @override
  String get phoneCallsWithOmi => 'Omi کے ساتھ فون کالیں';

  @override
  String get phoneCallsSubtitle => 'حقیقی وقت میں نسخہ کے ساتھ کالیں کریں';

  @override
  String get phoneSetupStep1Title => 'اپنا فون نمبر تصدیق کریں';

  @override
  String get phoneSetupStep1Subtitle => 'ہم آپ کو کال کریں گے تاکہ اس کی تصدیق کر سکیں کہ یہ آپ کا ہے';

  @override
  String get phoneSetupStep2Title => 'تصدیق کوڈ درج کریں';

  @override
  String get phoneSetupStep2Subtitle => 'ایک مختصر کوڈ جو آپ کال پر درج کریں گے';

  @override
  String get phoneSetupStep3Title => 'اپنے رابطوں کو کال کرنا شروع کریں';

  @override
  String get phoneSetupStep3Subtitle => 'حقیقی وقت میں نسخہ کے ساتھ';

  @override
  String get phoneGetStarted => 'شروع کریں';

  @override
  String get callRecordingConsentDisclaimer => 'کال ریکارڈنگ کے لیے آپ کے علاقے میں رضامندی کی ضرورت ہو سکتی ہے';

  @override
  String get enterYourNumber => 'اپنا نمبر درج کریں';

  @override
  String get phoneNumberCallerIdHint => 'تصدیق ہونے کے بعد، یہ آپ کا کال کنندہ ID بن جاتا ہے';

  @override
  String get phoneNumberHint => 'فون نمبر';

  @override
  String get failedToStartVerification => 'تصدیق شروع کرنا ناکام';

  @override
  String get phoneContinue => 'جاری رکھیں';

  @override
  String get verifyYourNumber => 'اپنا نمبر تصدیق کریں';

  @override
  String get answerTheCallFrom => 'سے آنے والی کال کا جواب دیں';

  @override
  String get onTheCallEnterThisCode => 'کال پر یہ کوڈ درج کریں';

  @override
  String get followTheVoiceInstructions => 'آواز کی ہدایات پر عمل کریں';

  @override
  String get statusCalling => 'کال ہو رہی ہے...';

  @override
  String get statusCallInProgress => 'کال جاری ہے';

  @override
  String get statusVerifiedLabel => 'تصدیق شدہ';

  @override
  String get statusCallMissed => 'کال مسڑ ہو گئی';

  @override
  String get statusTimedOut => 'وقت ختم ہو گیا';

  @override
  String get phoneTryAgain => 'دوبارہ کوشش کریں';

  @override
  String get phonePageTitle => 'فون';

  @override
  String get phoneContactsTab => 'رابطے';

  @override
  String get phoneKeypadTab => 'کی پیڈ';

  @override
  String get grantContactsAccess => 'اپنے رابطوں تک رسائی کی اجازت دیں';

  @override
  String get phoneAllow => 'اجازت دیں';

  @override
  String get phoneSearchHint => 'تلاش';

  @override
  String get phoneNoContactsFound => 'کوئی رابطہ نہیں ملا';

  @override
  String get phoneEnterNumber => 'نمبر درج کریں';

  @override
  String get failedToStartCall => 'کال شروع کرنا ناکام';

  @override
  String get callStateConnecting => 'منسلک ہو رہے ہیں...';

  @override
  String get callStateRinging => 'بجائی جا رہی ہے...';

  @override
  String get callStateEnded => 'کال ختم ہو گئی';

  @override
  String get callStateFailed => 'کال ناکام';

  @override
  String get transcriptPlaceholder => 'نسخہ یہاں ظاہر ہوگا...';

  @override
  String get phoneUnmute => 'آواز کھولیں';

  @override
  String get phoneMute => 'خاموش کریں';

  @override
  String get phoneSpeaker => 'اسپیکر';

  @override
  String get phoneEndCall => 'ختم کریں';

  @override
  String get phoneCallSettingsTitle => 'فون کال کی ترتیبات';

  @override
  String get showPhoneCallButtonTitle => 'فون کال بٹن دکھائیں';

  @override
  String get showPhoneCallButtonDesc => 'ہوم اسکرین پر فون کال بٹن دکھائیں';

  @override
  String get yourVerifiedNumbers => 'آپ کے تصدیق شدہ نمبر';

  @override
  String get verifiedNumbersDescription => 'جب آپ کسی کو کال کریں گے، تو وہ اپنے فون پر یہ نمبر دیکھے گا';

  @override
  String get noVerifiedNumbers => 'کوئی تصدیق شدہ نمبر نہیں';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber حذف کریں؟';
  }

  @override
  String get deletePhoneNumberWarning => 'کالیں کرنے کے لیے دوبارہ تصدیق کرنی ہوگی';

  @override
  String get phoneDeleteButton => 'حذف';

  @override
  String verifiedMinutesAgo(int minutes) {
    return '${minutes}m پہلے تصدیق شدہ';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return '${hours}h پہلے تصدیق شدہ';
  }

  @override
  String verifiedDaysAgo(int days) {
    return '${days}d پہلے تصدیق شدہ';
  }

  @override
  String verifiedOnDate(String date) {
    return '$date کو تصدیق شدہ';
  }

  @override
  String get verifiedFallback => 'تصدیق شدہ';

  @override
  String get callAlreadyInProgress => 'پہلے سے ایک کال جاری ہے';

  @override
  String get failedToGetCallToken => 'کال ٹوکن حاصل کرنا ناکام۔ پہلے اپنا فون نمبر تصدیق کریں۔';

  @override
  String get failedToInitializeCallService => 'کال سروس شروع کرنا ناکام';

  @override
  String get speakerLabelYou => 'آپ';

  @override
  String get speakerLabelUnknown => 'نامعلوم';

  @override
  String get showDailyScoreOnHomepage => 'ہوم پیج پر روزانہ کا اسکور دکھائیں';

  @override
  String get showTasksOnHomepage => 'ہوم پیج پر ٹاسکس دکھائیں';

  @override
  String get phoneCallsUnlimitedOnly => 'Omi کے ذریعے فون کالیں';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Omi کے ذریعے کالیں کریں اور حقیقی وقت میں نسخہ، خودکار خلاصے، اور بہت کچھ حاصل کریں۔ صرف غیر محدود منصوبے کے صارفین کے لیے دستیاب۔';

  @override
  String get phoneCallsUpsellFeature1 => 'ہر کال کی حقیقی وقت میں نقل';

  @override
  String get phoneCallsUpsellFeature2 => 'خودکار کال خلاصے اور ایکشن آئٹمز';

  @override
  String get phoneCallsUpsellFeature3 => 'وصول کنندگان آپ کا اصل نمبر دیکھتے ہیں، بے ترتیب نہیں';

  @override
  String get phoneCallsUpsellFeature4 => 'آپ کی کالیں نجی اور محفوظ رہتی ہیں';

  @override
  String get phoneCallsUpgradeButton => 'غیر محدود میں اپ گریڈ کریں';

  @override
  String get phoneCallsMaybeLater => 'شاید بعد میں';

  @override
  String get deleteSynced => 'ہم آہنگ حذف کریں';

  @override
  String get deleteSyncedFiles => 'ہم آہنگ ریکارڈنگز حذف کریں';

  @override
  String get deleteSyncedFilesMessage =>
      'یہ ریکارڈنگز پہلے سے آپ کے فون میں ہم آہنگ ہو چکی ہیں۔ یہ تبدیل نہیں ہو سکتا۔';

  @override
  String get syncedFilesDeleted => 'ہم آہنگ ریکارڈنگز حذف ہو گئیں';

  @override
  String get deletePending => 'زیرِ التوا حذف کریں';

  @override
  String get deletePendingFiles => 'زیرِ التوا ریکارڈنگز حذف کریں';

  @override
  String get deletePendingFilesWarning =>
      'یہ ریکارڈنگز آپ کے فون میں ہم آہنگ نہیں ہوئیں اور ہمیشہ کے لیے ضائع ہوں گی۔ یہ تبدیل نہیں ہو سکتا۔';

  @override
  String get pendingFilesDeleted => 'زیرِ التوا ریکارڈنگز حذف ہو گئیں';

  @override
  String get deleteAllFiles => 'تمام ریکارڈنگز حذف کریں';

  @override
  String get deleteAll => 'سب حذف کریں';

  @override
  String get deleteAllFilesWarning =>
      'یہ ہم آہنگ اور زیرِ التوا دونوں ریکارڈنگز حذف کرے گا۔ زیرِ التوا ریکارڈنگز ہم آہنگ نہیں ہوئیں اور ہمیشہ کے لیے ضائع ہوں گی۔ یہ تبدیل نہیں ہو سکتا۔';

  @override
  String get allFilesDeleted => 'تمام ریکارڈنگز حذف ہو گئیں';

  @override
  String nFiles(int count) {
    return '$count ریکارڈنگز';
  }

  @override
  String get manageStorage => 'اسٹوریج منظم کریں';

  @override
  String get safelyBackedUp => 'آپ کے فون میں محفوظ طریقے سے بیک اپ ہو گیا';

  @override
  String get notYetSynced => 'ابھی آپ کے فون میں ہم آہنگ نہیں ہوا';

  @override
  String get clearAll => 'سب صاف کریں';

  @override
  String get phoneKeypad => 'کی پیڈ';

  @override
  String get phoneHideKeypad => 'کی پیڈ چھپائیں';

  @override
  String get fairUsePolicy => 'منصفانہ استعمال';

  @override
  String get fairUseLoadError => 'منصفانہ استعمال کی حالت لوڈ نہیں کر سکے۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get fairUseStatusNormal => 'آپ کا استعمال عام حدود میں ہے۔';

  @override
  String get fairUseStageNormal => 'عام';

  @override
  String get fairUseStageWarning => 'انتباہ';

  @override
  String get fairUseStageThrottle => 'موڑا گیا';

  @override
  String get fairUseStageRestrict => 'محدود';

  @override
  String get fairUseSpeechUsage => 'تقریر کا استعمال';

  @override
  String get fairUseToday => 'آج';

  @override
  String get fairUse3Day => '3 دن کی رولنگ';

  @override
  String get fairUseWeekly => 'ہفتہ وار رولنگ';

  @override
  String get fairUseAboutTitle => 'منصفانہ استعمال کے بارے میں';

  @override
  String get fairUseAboutBody =>
      'Omi ذاتی بات چیت، میٹنگ، اور براہ راست بات چیت کے لیے ڈیزائن کیا گیا ہے۔ استعمال کو حقیقی تقریر کے وقت سے ماپا جاتا ہے، منسلکی کے وقت سے نہیں۔ اگر استعمال ذاتی غیر مواد کے لیے عام نمونوں کو نمایاں طور پر تجاوز کرے، تو ایڈجسٹمنٹ لاگو ہو سکتے ہیں۔';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef کاپی ہو گیا';
  }

  @override
  String get fairUseDailyTranscription => 'روزانہ کی نقل';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'روزانہ کی نقل کی حد پوری ہو گئی';

  @override
  String fairUseBudgetResetsAt(String time) {
    return '$time پر دوبارہ سیٹ ہوتا ہے';
  }

  @override
  String get transcriptionPaused => 'ریکارڈ ہو رہا ہے، دوبارہ منسلک ہو رہے ہیں';

  @override
  String get transcriptionPausedReconnecting => 'ابھی ریکارڈ ہو رہا ہے — نقل سے دوبارہ منسلک ہو رہے ہیں...';

  @override
  String fairUseBannerStatus(String status) {
    return 'منصفانہ استعمال: $status';
  }

  @override
  String get improveConnectionTitle => 'منسلکی بہتر بنائیں';

  @override
  String get improveConnectionContent =>
      'ہم نے بہتر بنایا ہے کہ Omi آپ کے ڈیوائس سے کیسے منسلک رہتا ہے۔ اس کو فعال کرنے کے لیے، براہ کرم ڈیوائس معلومات کے صفحے پر جائیں، \"ڈیوائس کو ڈسکنیکٹ کریں\" کو ٹیپ کریں، اور پھر اپنے ڈیوائس کو دوبارہ جوڑیں۔';

  @override
  String get improveConnectionAction => 'سمجھ گئے';

  @override
  String clockSkewWarning(int minutes) {
    return 'آپ کی ڈیوائس کی گھڑی ~$minutes منٹ کی غلطی سے ہے۔ اپنی تاریخ اور وقت کی ترتیبات کو چیک کریں۔';
  }

  @override
  String get omisStorage => 'Omi کی اسٹوریج';

  @override
  String get phoneStorage => 'فون کی اسٹوریج';

  @override
  String get cloudStorage => 'کلاؤڈ اسٹوریج';

  @override
  String get howSyncingWorks => 'ہم آہنگی کیسے کام کرتی ہے';

  @override
  String get noSyncedRecordings => 'ابھی کوئی ہم آہنگ ریکارڈنگ نہیں';

  @override
  String get recordingsSyncAutomatically => 'ریکارڈنگز خودکار طور پر ہم آہنگ ہوتی ہیں — کوئی کارروائی کی ضرورت نہیں۔';

  @override
  String get filesDownloadedUploadedNextTime => 'پہلے سے ڈاؤن لوڈ کی گئی فائلیں اگلی بار اپ لوڈ ہوں گی۔';

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
  String get tapToView => 'دیکھنے کے لیے ٹیپ کریں';

  @override
  String get syncFailed => 'ہم آہنگی ناکام';

  @override
  String get keepSyncing => 'ہم آہنگی جاری رکھیں';

  @override
  String get cancelSyncQuestion => 'ہم آہنگی منسوخ کریں؟';

  @override
  String get omisStorageDesc =>
      'جب آپ کا Omi آپ کے فون سے منسلک نہ ہو، تو یہ آڈیو کو اپنی بنی ہوئی میموری میں مقامی طور پر محفوظ کرتا ہے۔ آپ کبھی بھی ریکارڈنگ نہیں کھوتے۔';

  @override
  String get phoneStorageDesc =>
      'جب Omi دوبارہ منسلک ہوتا ہے، تو ریکارڈنگز خودکار طور پر آپ کے فون میں منتقل ہوتی ہیں اپ لوڈ کرنے سے پہلے ایک عارضی رکھنے والے علاقے کے طور پر۔';

  @override
  String get cloudStorageDesc =>
      'اپ لوڈ ہونے کے بعد، آپ کی ریکارڈنگز پروسیس اور نقل ہوتی ہیں۔ بات چیت ایک منٹ میں دستیاب ہوں گی۔';

  @override
  String get tipKeepPhoneNearby => 'تیز ہم آہنگی کے لیے اپنے فون کو قریب رکھیں';

  @override
  String get tipStableInternet => 'مستحکم انٹرنیٹ کلاؤڈ اپ لوڈز کو تیز کرتا ہے';

  @override
  String get tipAutoSync => 'ریکارڈنگز خودکار طور پر ہم آہنگ ہوتی ہیں';

  @override
  String get storageSection => 'اسٹوریج';

  @override
  String get permissions => 'اجازتیں';

  @override
  String get permissionEnabled => 'فعال';

  @override
  String get permissionEnable => 'فعال کریں';

  @override
  String get permissionsPageDescription =>
      'یہ اجازتیں Omi کے کام کرنے کے لیے اہم ہیں۔ وہ اطلاعات، مقام پر مبنی تجربات، اور آڈیو کی تفتیش جیسی اہم خصوصیات کو فعال کرتی ہیں۔';

  @override
  String get permissionsRequiredDescription =>
      'Omi کو صحیح طریقے سے کام کرنے کے لیے کچھ اجازتوں کی ضرورت ہے۔ براہ کرم جاری رکھنے کے لیے انہیں منظور کریں۔';

  @override
  String get permissionsSetupTitle => 'بہترین تجربہ حاصل کریں';

  @override
  String get permissionsSetupDescription => 'کچھ اجازتیں فعال کریں تاکہ Omi اپنا جادو دکھا سکے۔';

  @override
  String get permissionsChangeAnytime => 'آپ یہ ترتیبات میں کسی بھی وقت تبدیل کر سکتے ہیں > اجازتیں';

  @override
  String get location => 'مقام';

  @override
  String get microphone => 'مائکروفون';

  @override
  String get whyAreYouCanceling => 'آپ منسوخ کیوں کر رہے ہیں؟';

  @override
  String get cancelReasonSubtitle => 'کیا آپ ہمیں بتا سکتے ہیں کہ آپ کیوں جا رہے ہیں؟';

  @override
  String get cancelReasonTooExpensive => 'بہت مہنگا';

  @override
  String get cancelReasonNotUsing => 'اتنا استعمال نہیں';

  @override
  String get cancelReasonMissingFeatures => 'خصوصیات نہیں ہیں';

  @override
  String get cancelReasonAudioQuality => 'آڈیو/نقل کی معیار';

  @override
  String get cancelReasonBatteryDrain => 'بیٹری کی کھپت کی فکر';

  @override
  String get cancelReasonFoundAlternative => 'متبادل ڈھونڈا';

  @override
  String get cancelReasonOther => 'دیگر';

  @override
  String get tellUsMore => 'ہمیں مزید بتائیں (اختیاری)';

  @override
  String get cancelReasonDetailHint => 'ہم کسی بھی رائے کی تعریف کرتے ہیں...';

  @override
  String get justAMoment => 'برائے کرم ایک لمحہ انتظار کریں';

  @override
  String get cancelConsequencesSubtitle =>
      'ہم منسوخ کرنے کی بجائے اپنی دوسری اختیارات کی تلاش کرنے کی سختی سے سفارش کرتے ہیں۔';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'آپ کا منصوبہ $date تک فعال رہے گا۔ اس کے بعد، آپ کو محدود خصوصیات کے ساتھ مفت ورژن میں منتقل کیا جائے گا۔';
  }

  @override
  String get ifYouCancel => 'اگر آپ منسوخ کریں:';

  @override
  String get cancelConsequenceNoAccess => 'آپ کے بلنگ دور کے آخر میں غیر محدود رسائی نہیں رہے گی۔';

  @override
  String get cancelConsequenceBattery => '7x زیادہ بیٹری کا استعمال (آن ڈیوائس پروسیسنگ)';

  @override
  String get cancelConsequenceQuality => '30% کم نقل کی معیار (آن ڈیوائس ماڈلز)';

  @override
  String get cancelConsequenceDelay => '5-7 سیکنڈ کی پروسیسنگ میں تاخیر (آن ڈیوائس ماڈلز)';

  @override
  String get cancelConsequenceSpeakers => 'متحدثین کی نشاندہی نہیں کر سکتے۔';

  @override
  String get confirmAndCancel => 'تصدیق اور منسوخ کریں';

  @override
  String get cancelConsequencePhoneCalls => 'فون کال میں حقیقی وقت میں نقل نہیں';

  @override
  String get feedbackTitleTooExpensive => 'آپ کے لیے کون سی قیمت کام کرے گی؟';

  @override
  String get feedbackTitleMissingFeatures => 'آپ کو کون سی خصوصیات نہیں ہیں؟';

  @override
  String get feedbackTitleAudioQuality => 'آپ نے کون سے مسائل کا سامنا کیا؟';

  @override
  String get feedbackTitleBatteryDrain => 'ہمیں بیٹری کے مسائل کے بارے میں بتائیں';

  @override
  String get feedbackTitleFoundAlternative => 'آپ کس چیز میں تبدیل ہو رہے ہیں؟';

  @override
  String get feedbackTitleNotUsing => 'Omi کو کیا زیادہ استعمال کرے گا؟';

  @override
  String get feedbackSubtitleTooExpensive => 'آپ کی رائے ہمیں صحیح توازن تلاش کرنے میں مدد دیتی ہے۔';

  @override
  String get feedbackSubtitleMissingFeatures => 'ہم ہمیشہ بناتے ہیں — یہ ہمیں ترجیح دینے میں مدد دیتا ہے۔';

  @override
  String get feedbackSubtitleAudioQuality => 'ہم یہ سمجھنا چاہتے ہیں کہ کیا غلط ہوا۔';

  @override
  String get feedbackSubtitleBatteryDrain => 'یہ ہمارے ہارڈ ویئر ٹیم کو بہتر بنانے میں مدد دیتا ہے۔';

  @override
  String get feedbackSubtitleFoundAlternative => 'ہم یہ سیکھنا چاہتے ہیں کہ آپ کو کیا متاثر کیا۔';

  @override
  String get feedbackSubtitleNotUsing => 'ہم Omi کو آپ کے لیے زیادہ مفید بنانا چاہتے ہیں۔';

  @override
  String get deviceDiagnostics => 'ڈیوائس کی تشخیص';

  @override
  String get signalStrength => 'سگنل کی طاقت';

  @override
  String get connectionUptime => 'اپ ٹائم';

  @override
  String get reconnections => 'دوبارہ منسلکی';

  @override
  String get disconnectHistory => 'ڈسکنیکٹ کی تاریخ';

  @override
  String get noDisconnectsRecorded => 'کوئی ڈسکنیکٹ ریکارڈ نہیں ہوا';

  @override
  String get diagnostics => 'تشخیص';

  @override
  String get waitingForData => 'ڈیٹا کے انتظار میں...';

  @override
  String get liveRssiOverTime => 'وقت کے ساتھ RSSI کی زندگی';

  @override
  String get noRssiDataYet => 'ابھی کوئی RSSI ڈیٹا نہیں';

  @override
  String get collectingData => 'ڈیٹا جمع ہو رہا ہے...';

  @override
  String get cleanDisconnect => 'صاف ڈسکنیکٹ';

  @override
  String get connectionTimeout => 'منسلکی ختم ہو گئی';

  @override
  String get remoteDeviceTerminated => 'دور ڈیوائس ختم ہو گیا';

  @override
  String get pairedToAnotherPhone => 'دوسرے فون سے جوڑے گئے';

  @override
  String get linkKeyMismatch => 'لنک کی غلط مماثلت';

  @override
  String get connectionFailed => 'منسلکی ناکام';

  @override
  String get appClosed => 'ایپ بند ہو گئی';

  @override
  String get manualDisconnect => 'دستی ڈسکنیکٹ';

  @override
  String lastNEvents(int count) {
    return 'آخری $count واقعات';
  }

  @override
  String get signal => 'سگنل';

  @override
  String get battery => 'بیٹری';

  @override
  String get excellent => 'بہترین';

  @override
  String get good => 'اچھا';

  @override
  String get fair => 'منصفانہ';

  @override
  String get weak => 'کمزور';

  @override
  String gattError(String code) {
    return 'GATT خرابی ($code)';
  }

  @override
  String get batteryHistory => 'بیٹری';

  @override
  String get noBatteryDataYet => 'ابھی تک کوئی بیٹری ڈیٹا نہیں';

  @override
  String get day => 'دن';

  @override
  String get week => 'ہفتہ';

  @override
  String get rollbackToStableFirmware => 'مستحکم فرم ویئر پر واپس لیں';

  @override
  String get rollbackConfirmTitle => 'فرم ویئر واپس لیں؟';

  @override
  String rollbackConfirmMessage(String version) {
    return 'یہ آپ کے موجودہ فرم ویئر کو تازہ ترین مستحکم ورژن ($version) سے بدل دے گا۔ اپ ڈیٹ کے بعد آپ کا ڈیوائس دوبارہ شروع ہوگا۔';
  }

  @override
  String get stableFirmware => 'مستحکم فرم ویئر';

  @override
  String get fetchingStableFirmware => 'تازہ ترین مستحکم فرم ویئر حاصل ہو رہا ہے...';

  @override
  String get noStableFirmwareFound => 'آپ کے ڈیوائس کے لیے مستحکم فرم ویئر ورژن نہیں مل سکا۔';

  @override
  String get installStableFirmware => 'مستحکم فرم ویئر انسٹال کریں';

  @override
  String get alreadyOnStableFirmware => 'آپ پہلے سے تازہ ترین مستحکم ورژن پر ہیں۔';

  @override
  String audioSavedLocally(String duration) {
    return '$duration آڈیو مقامی طور پر محفوظ ہے';
  }

  @override
  String get willSyncAutomatically => 'خودکار طور پر ہم آہنگ ہوگا';

  @override
  String get enableLocationTitle => 'مقام فعال کریں';

  @override
  String get enableLocationDescription => 'قریبی بلیو ٹوتھ ڈیوائسز تلاش کرنے کے لیے مقام کی اجازت ضروری ہے۔';

  @override
  String get voiceRecordingFound => 'ریکارڈنگ ملی';

  @override
  String get transcriptionConnecting => 'نقل منسلک ہو رہی ہے...';

  @override
  String get transcriptionReconnecting => 'نقل دوبارہ منسلک ہو رہی ہے...';

  @override
  String get transcriptionUnavailable => 'نقل دستیاب نہیں';

  @override
  String get audioOutput => 'آڈیو آؤٹ پٹ';

  @override
  String get firmwareWarningTitle => 'اہم: اپ ڈیٹ سے پہلے پڑھیں';

  @override
  String get firmwareFormatWarning =>
      'یہ فرم ویئر SD کارڈ کو فارمیٹ کرے گا۔ براہ کرم اپ گریڈ کرنے سے پہلے یقینی بنائیں کہ تمام آف لائن ڈیٹا مطابقت پذیر ہو چکا ہے۔\n\nاگر اس ورژن کو انسٹال کرنے کے بعد سرخ روشنی چمکتی نظر آئے تو پریشان نہ ہوں۔ بس آلے کو ایپ سے جوڑیں اور یہ نیلا ہو جانا چاہیے۔ سرخ روشنی کا مطلب ہے کہ آلے کی گھڑی ابھی تک مطابقت پذیر نہیں ہوئی۔';

  @override
  String get continueAnyway => 'جاری رکھیں';

  @override
  String get tasksClearCompleted => 'مکمل کو صاف کریں';

  @override
  String get tasksSelectAll => 'سب منتخب کریں';

  @override
  String tasksDeleteSelected(int count) {
    return '$count کام حذف کریں';
  }

  @override
  String get tasksMarkComplete => 'مکمل کے طور پر نشان زد';

  @override
  String get appleHealthManageNote =>
      'Omi، Apple کے HealthKit فریم ورک کے ذریعے Apple Health تک رسائی حاصل کرتا ہے۔ آپ کسی بھی وقت iOS کی ترتیبات سے رسائی منسوخ کر سکتے ہیں۔';

  @override
  String get appleHealthConnectCta => 'Apple Health سے منسلک کریں';

  @override
  String get appleHealthDisconnectCta => 'Apple Health منقطع کریں';

  @override
  String get appleHealthConnectedBadge => 'منسلک';

  @override
  String get appleHealthFeatureChatTitle => 'اپنی صحت کے بارے میں گفتگو کریں';

  @override
  String get appleHealthFeatureChatDesc => 'Omi سے اپنے قدم، نیند، دل کی دھڑکن اور ورزشوں کے بارے میں پوچھیں۔';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'صرف پڑھنے کی رسائی';

  @override
  String get appleHealthFeatureReadOnlyDesc =>
      'Omi کبھی Apple Health میں نہیں لکھتا اور نہ ہی آپ کا ڈیٹا تبدیل کرتا ہے۔';

  @override
  String get appleHealthFeatureSecureTitle => 'محفوظ ہم وقت سازی';

  @override
  String get appleHealthFeatureSecureDesc =>
      'آپ کا Apple Health ڈیٹا نجی طور پر آپ کے Omi اکاؤنٹ کے ساتھ ہم وقت ہوتا ہے۔';

  @override
  String get appleHealthDeniedTitle => 'Apple Health تک رسائی مسترد';

  @override
  String get appleHealthDeniedBody =>
      'Omi کو آپ کا Apple Health ڈیٹا پڑھنے کی اجازت نہیں ہے۔ اسے iOS ترتیبات ← پرائیویسی اور سیکیورٹی ← Health ← Omi میں فعال کریں۔';

  @override
  String get deleteFlowReasonTitle => 'آپ کیوں جا رہے ہیں؟';

  @override
  String get deleteFlowReasonSubtitle => 'آپ کا فیڈ بیک ہمیں Omi کو سب کے لیے بہتر بنانے میں مدد کرتا ہے۔';

  @override
  String get deleteReasonPrivacy => 'رازداری کے خدشات';

  @override
  String get deleteReasonNotUsing => 'اتنا زیادہ استعمال نہیں کرتا';

  @override
  String get deleteReasonMissingFeatures => 'جن فیچرز کی ضرورت ہے وہ موجود نہیں';

  @override
  String get deleteReasonTechnicalIssues => 'بہت زیادہ تکنیکی مسائل';

  @override
  String get deleteReasonFoundAlternative => 'کچھ اور استعمال کر رہا ہوں';

  @override
  String get deleteReasonTakingBreak => 'بس تھوڑا وقفہ لے رہا ہوں';

  @override
  String get deleteReasonOther => 'دیگر';

  @override
  String get deleteFlowFeedbackTitle => 'مزید بتائیں';

  @override
  String get deleteFlowFeedbackSubtitle => 'کس چیز سے Omi آپ کے لیے کام کرتا؟';

  @override
  String get deleteFlowFeedbackHint => 'اختیاری — آپ کے خیالات ہمیں بہتر پروڈکٹ بنانے میں مدد دیتے ہیں۔';

  @override
  String get deleteFlowConfirmTitle => 'یہ مستقل ہے';

  @override
  String get deleteFlowConfirmSubtitle => 'ایک بار اکاؤنٹ حذف ہونے کے بعد اسے بحال نہیں کیا جا سکتا۔';

  @override
  String get deleteConsequenceSubscription => 'کوئی بھی فعال سبسکرپشن منسوخ کر دی جائے گی۔';

  @override
  String get deleteConsequenceNoRecovery => 'آپ کا اکاؤنٹ بحال نہیں ہو سکتا — سپورٹ بھی نہیں کر سکتی۔';

  @override
  String get deleteTypeToConfirm => 'تصدیق کے لیے DELETE ٹائپ کریں';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'اکاؤنٹ مستقل طور پر حذف کریں';

  @override
  String get keepMyAccount => 'میرا اکاؤنٹ برقرار رکھیں';

  @override
  String get deleteAccountFailed => 'آپ کا اکاؤنٹ حذف نہیں ہو سکا۔ براہ کرم دوبارہ کوشش کریں۔';

  @override
  String get planUpdate => 'پلان اپ ڈیٹ';

  @override
  String get planDeprecationMessage =>
      'آپ کا Unlimited پلان ختم کیا جا رہا ہے۔ Operator پلان پر سوئچ کریں — وہی شاندار فیچرز \$49/ماہ پر۔ آپ کا موجودہ پلان اس دوران کام کرتا رہے گا۔';

  @override
  String get upgradeYourPlan => 'اپنا پلان اپ گریڈ کریں';

  @override
  String get youAreOnAPaidPlan => 'آپ ایک ادا شدہ پلان پر ہیں۔';

  @override
  String get chatTitle => 'چیٹ';

  @override
  String get chatMessages => 'پیغامات';

  @override
  String get unlimitedChatThisMonth => 'اس مہینے لامحدود چیٹ پیغامات';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used / $limit کمپیوٹ بجٹ استعمال ہوا';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return 'اس مہینے $used / $limit پیغامات استعمال ہوئے';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit استعمال ہوا';
  }

  @override
  String get chatLimitReachedUpgrade => 'چیٹ کی حد پوری ہو گئی۔ مزید پیغامات کے لیے اپ گریڈ کریں۔';

  @override
  String get chatLimitReachedTitle => 'چیٹ کی حد پوری ہو گئی';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'آپ نے $plan پلان پر $limitDisplay میں سے $used استعمال کیے ہیں۔';
  }

  @override
  String resetsInDays(int count) {
    return '$count دنوں میں ری سیٹ ہوگا';
  }

  @override
  String resetsInHours(int count) {
    return '$count گھنٹوں میں ری سیٹ ہوگا';
  }

  @override
  String get resetsSoon => 'جلد ری سیٹ ہوگا';

  @override
  String get upgradePlan => 'پلان اپ گریڈ کریں';

  @override
  String get billingMonthly => 'ماہانہ';

  @override
  String get billingYearly => 'سالانہ';

  @override
  String get savePercent => '~17% بچائیں';

  @override
  String get popular => 'مقبول';

  @override
  String get currentPlan => 'موجودہ';

  @override
  String neoSubtitle(int count) {
    return 'ماہانہ $count سوالات';
  }

  @override
  String operatorSubtitle(int count) {
    return 'ماہانہ $count سوالات';
  }

  @override
  String get architectSubtitle => 'پاور یوزر AI — ہزاروں چیٹس + ایجنٹک آٹومیشن';

  @override
  String chatUsageCost(String used, String limit) {
    return 'چیٹ: \$$used / \$$limit اس مہینے استعمال ہوا';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'چیٹ: \$$used اس مہینے استعمال ہوا';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'چیٹ: $used / $limit پیغامات اس مہینے';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'چیٹ: $used پیغامات اس مہینے';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'آپ اپنی ماہانہ حد تک پہنچ گئے ہیں۔ بغیر کسی پابندی کے Omi کے ساتھ چیٹ جاری رکھنے کے لیے اپ گریڈ کریں۔';

  @override
  String get voiceResponseAudio => 'Omi کا جواب بلند آواز میں پڑھیں';

  @override
  String get voiceResponseMode => 'آواز کا جواب';

  @override
  String get voiceResponseModeTitle => 'جواب کب پڑھے جائیں';

  @override
  String get voiceResponseOff => 'بند';

  @override
  String get voiceResponseHeadphonesOnly => 'صرف ہیڈ فون';

  @override
  String get voiceResponseAlways => 'ہمیشہ';

  @override
  String get agreeAndContinue => 'اتفاق اور جاری رکھیں';

  @override
  String get startVoiceRecording => 'وائس ریکارڈنگ شروع کریں';

  @override
  String get startCallRecording => 'کال ریکارڈنگ شروع کریں';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'آواز موڈ';

  @override
  String get quickActionAskOmi => 'Omi سے کچھ بھی پوچھیں';

  @override
  String get record => 'ریکارڈ کریں';

  @override
  String get stop => 'روکیں';

  @override
  String get recordWithPhoneMic => 'فون مائیک سے ریکارڈ کریں';

  @override
  String get recordWithPhoneMicSubtitle => 'اپنے ارد گرد کی آواز ریکارڈ کریں';

  @override
  String get phoneCall => 'فون کال';

  @override
  String get phoneCallSubtitle => 'لائیو ٹرانسکرپشن کے ساتھ کال ریکارڈ کریں';

  @override
  String get searchActionItems => 'ایکشن آئٹمز تلاش کریں';

  @override
  String get selectActionItems => 'متعدد منتخب کریں';

  @override
  String chooseExportDestination(int count) {
    return '$count آئٹم ایکسپورٹ کریں…';
  }

  @override
  String get bulkExportInProgress => 'ایکسپورٹ ہو رہا ہے…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$count کو $platform میں ایکسپورٹ کیا گیا';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$total میں سے $success کو $platform میں ایکسپورٹ کیا گیا';
  }

  @override
  String get showCompletedTasks => 'مکمل شدہ دکھائیں';

  @override
  String get hideCompletedTasks => 'مکمل شدہ چھپائیں';

  @override
  String get selectAllTasksMenu => 'سب منتخب کریں';

  @override
  String get connectTaskAppToExport => 'ایکسپورٹ کے لیے ترتیبات میں ٹاسک ایپ جوڑیں';

  @override
  String get connectAction => 'جوڑیں';

  @override
  String get deselectAllTasksMenu => 'تمام کا انتخاب ختم کریں';
}
