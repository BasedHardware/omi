// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Arabic (`ar`).
class AppLocalizationsAr extends AppLocalizations {
  AppLocalizationsAr([String locale = 'ar']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'المحادثة';

  @override
  String get transcriptTab => 'النص المكتوب';

  @override
  String get actionItemsTab => 'المهام';

  @override
  String get deleteConversationTitle => 'حذف المحادثة؟';

  @override
  String get deleteConversationMessage => 'هل أنت متأكد من رغبتك في حذف هذه المحادثة؟ لا يمكن التراجع عن هذا الإجراء.';

  @override
  String get confirm => 'تأكيد';

  @override
  String get cancel => 'إلغاء';

  @override
  String get ok => 'حسناً';

  @override
  String get delete => 'حذف';

  @override
  String get add => 'إضافة';

  @override
  String get update => 'تحديث';

  @override
  String get save => 'حفظ';

  @override
  String get edit => 'تعديل';

  @override
  String get close => 'إغلاق';

  @override
  String get clear => 'مسح';

  @override
  String get copyTranscript => 'نسخ النص';

  @override
  String get copySummary => 'نسخ الملخص';

  @override
  String get testPrompt => 'اختبار الأمر';

  @override
  String get reprocessConversation => 'إعادة معالجة المحادثة';

  @override
  String get deleteConversation => 'حذف المحادثة';

  @override
  String get contentCopied => 'تم نسخ المحتوى إلى الحافظة';

  @override
  String get failedToUpdateStarred => 'فشل تحديث حالة التمييز بنجمة.';

  @override
  String get conversationUrlNotShared => 'تعذرت مشاركة رابط المحادثة.';

  @override
  String get errorProcessingConversation => 'خطأ أثناء معالجة المحادثة. يرجى المحاولة مرة أخرى لاحقاً.';

  @override
  String get noInternetConnection => 'لا يوجد اتصال بالإنترنت';

  @override
  String get unableToDeleteConversation => 'تعذر حذف المحادثة';

  @override
  String get somethingWentWrong => 'حدث خطأ ما! يرجى المحاولة مرة أخرى لاحقاً.';

  @override
  String get copyErrorMessage => 'نسخ رسالة الخطأ';

  @override
  String get errorCopied => 'تم نسخ رسالة الخطأ إلى الحافظة';

  @override
  String get remaining => 'متبقي';

  @override
  String get loading => 'جاري التحميل...';

  @override
  String get loadingDuration => 'جاري تحميل المدة...';

  @override
  String secondsCount(int count) {
    return '$count ثانية';
  }

  @override
  String get people => 'الأشخاص';

  @override
  String get addNewPerson => 'إضافة شخص جديد';

  @override
  String get editPerson => 'تعديل الشخص';

  @override
  String get createPersonHint => 'أنشئ شخصاً جديداً ودرب Omi على التعرف على صوته أيضاً!';

  @override
  String get speechProfile => 'ملف الصوت';

  @override
  String sampleNumber(int number) {
    return 'عينة $number';
  }

  @override
  String get settings => 'الإعدادات';

  @override
  String get language => 'اللغة';

  @override
  String get selectLanguage => 'اختر اللغة';

  @override
  String get deleting => 'جاري الحذف...';

  @override
  String get pleaseCompleteAuthentication => 'يرجى إكمال المصادقة في متصفحك. بعد الانتهاء، ارجع إلى التطبيق.';

  @override
  String get failedToStartAuthentication => 'فشل بدء المصادقة';

  @override
  String get importStarted => 'بدأ الاستيراد! سيتم إشعارك عند اكتماله.';

  @override
  String get failedToStartImport => 'فشل بدء الاستيراد. يرجى المحاولة مرة أخرى.';

  @override
  String get couldNotAccessFile => 'تعذر الوصول إلى الملف المحدد';

  @override
  String get askOmi => 'اسأل Omi';

  @override
  String get done => 'تم';

  @override
  String get disconnected => 'غير متصل';

  @override
  String get searching => 'جارٍ البحث...';

  @override
  String get connectDevice => 'توصيل جهاز';

  @override
  String get monthlyLimitReached => 'لقد وصلت إلى الحد الشهري.';

  @override
  String get checkUsage => 'التحقق من الاستخدام';

  @override
  String get syncingRecordings => 'مزامنة التسجيلات';

  @override
  String get recordingsToSync => 'التسجيلات المراد مزامنتها';

  @override
  String get allCaughtUp => 'كل شيء محدث';

  @override
  String get sync => 'مزامنة';

  @override
  String get pendantUpToDate => 'القلادة محدثة';

  @override
  String get allRecordingsSynced => 'جميع التسجيلات متزامنة';

  @override
  String get syncingInProgress => 'المزامنة قيد التنفيذ';

  @override
  String get readyToSync => 'جاهز للمزامنة';

  @override
  String get tapSyncToStart => 'اضغط على مزامنة للبدء';

  @override
  String get pendantNotConnected => 'القلادة غير متصلة. قم بالتوصيل للمزامنة.';

  @override
  String get everythingSynced => 'كل شيء متزامن بالفعل.';

  @override
  String get recordingsNotSynced => 'لديك تسجيلات لم تتم مزامنتها بعد.';

  @override
  String get syncingBackground => 'سنستمر في مزامنة تسجيلاتك في الخلفية.';

  @override
  String get noConversationsYet => 'لا توجد محادثات بعد';

  @override
  String get noStarredConversations => 'لا توجد محادثات مميزة';

  @override
  String get starConversationHint => 'لتمييز محادثة بنجمة، افتحها واضغط على أيقونة النجمة في الرأس.';

  @override
  String get searchConversations => 'البحث في المحادثات...';

  @override
  String selectedCount(int count, Object s) {
    return '$count محدد';
  }

  @override
  String get merge => 'دمج';

  @override
  String get mergeConversations => 'دمج المحادثات';

  @override
  String mergeConversationsMessage(int count) {
    return 'سيؤدي هذا إلى دمج $count محادثة في واحدة. سيتم دمج وإعادة إنشاء جميع المحتويات.';
  }

  @override
  String get mergingInBackground => 'جاري الدمج في الخلفية. قد يستغرق هذا لحظة.';

  @override
  String get failedToStartMerge => 'فشل بدء الدمج';

  @override
  String get askAnything => 'اسأل أي شيء';

  @override
  String get noMessagesYet => 'لا توجد رسائل بعد!\nلماذا لا تبدأ محادثة؟';

  @override
  String get deletingMessages => 'حذف رسائلك من ذاكرة Omi...';

  @override
  String get messageCopied => '✨ تم نسخ الرسالة إلى الحافظة';

  @override
  String get cannotReportOwnMessage => 'لا يمكنك الإبلاغ عن رسائلك الخاصة.';

  @override
  String get reportMessage => 'الإبلاغ عن الرسالة';

  @override
  String get reportMessageConfirm => 'هل أنت متأكد من رغبتك في الإبلاغ عن هذه الرسالة؟';

  @override
  String get messageReported => 'تم الإبلاغ عن الرسالة بنجاح.';

  @override
  String get thankYouFeedback => 'شكراً لك على ملاحظاتك!';

  @override
  String get clearChat => 'مسح المحادثة';

  @override
  String get clearChatConfirm => 'هل أنت متأكد من رغبتك في مسح المحادثة؟ لا يمكن التراجع عن هذا الإجراء.';

  @override
  String get maxFilesLimit => 'يمكنك تحميل 4 ملفات فقط في كل مرة';

  @override
  String get chatWithOmi => 'الدردشة مع Omi';

  @override
  String get apps => 'التطبيقات';

  @override
  String get noAppsFound => 'لم يتم العثور على تطبيقات';

  @override
  String get tryAdjustingSearch => 'حاول تعديل البحث أو الفلاتر';

  @override
  String get createYourOwnApp => 'أنشئ تطبيقك الخاص';

  @override
  String get buildAndShareApp => 'أنشئ وشارك تطبيقك المخصص';

  @override
  String get searchApps => 'البحث عن التطبيقات...';

  @override
  String get myApps => 'تطبيقاتي';

  @override
  String get installedApps => 'التطبيقات المثبتة';

  @override
  String get unableToFetchApps => 'تعذر جلب التطبيقات :(\n\nيرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى.';

  @override
  String get aboutOmi => 'حول Omi';

  @override
  String get privacyPolicy => 'سياسة الخصوصية';

  @override
  String get visitWebsite => 'زيارة الموقع';

  @override
  String get helpOrInquiries => 'مساعدة أو استفسارات؟';

  @override
  String get joinCommunity => 'انضم إلى المجتمع!';

  @override
  String get membersAndCounting => '8000+ عضو وما زال العدد في ازدياد.';

  @override
  String get deleteAccountTitle => 'حذف الحساب';

  @override
  String get deleteAccountConfirm => 'هل أنت متأكد من رغبتك في حذف حسابك؟';

  @override
  String get cannotBeUndone => 'لا يمكن التراجع عن هذا.';

  @override
  String get allDataErased => 'سيتم حذف جميع ذكرياتك ومحادثاتك بشكل دائم.';

  @override
  String get appsDisconnected => 'سيتم فصل تطبيقاتك وتكاملاتك فوراً.';

  @override
  String get exportBeforeDelete => 'يمكنك تصدير بياناتك قبل حذف حسابك، ولكن بمجرد الحذف، لا يمكن استردادها.';

  @override
  String get deleteAccountCheckbox =>
      'أدرك أن حذف حسابي دائم وأن جميع البيانات، بما في ذلك الذكريات والمحادثات، ستُفقد ولا يمكن استردادها.';

  @override
  String get areYouSure => 'هل أنت متأكد؟';

  @override
  String get deleteAccountFinal =>
      'هذا الإجراء لا رجعة فيه وسيحذف حسابك وجميع البيانات المرتبطة به نهائياً. هل أنت متأكد من رغبتك في المتابعة؟';

  @override
  String get deleteNow => 'احذف الآن';

  @override
  String get goBack => 'العودة';

  @override
  String get checkBoxToConfirm => 'حدد المربع لتأكيد فهمك أن حذف حسابك دائم ولا رجعة فيه.';

  @override
  String get profile => 'الملف الشخصي';

  @override
  String get name => 'الاسم';

  @override
  String get email => 'البريد الإلكتروني';

  @override
  String get customVocabulary => 'المفردات المخصصة';

  @override
  String get identifyingOthers => 'تحديد الآخرين';

  @override
  String get paymentMethods => 'طرق الدفع';

  @override
  String get conversationDisplay => 'عرض المحادثات';

  @override
  String get dataPrivacy => 'خصوصية البيانات';

  @override
  String get userId => 'معرف المستخدم';

  @override
  String get notSet => 'غير محدد';

  @override
  String get userIdCopied => 'تم نسخ معرف المستخدم إلى الحافظة';

  @override
  String get systemDefault => 'افتراضي النظام';

  @override
  String get planAndUsage => 'الخطة والاستخدام';

  @override
  String get offlineSync => 'المزامنة دون اتصال';

  @override
  String get deviceSettings => 'إعدادات الجهاز';

  @override
  String get integrations => 'التكاملات';

  @override
  String get feedbackBug => 'ملاحظات / خطأ';

  @override
  String get helpCenter => 'مركز المساعدة';

  @override
  String get developerSettings => 'إعدادات المطور';

  @override
  String get getOmiForMac => 'احصل على Omi لنظام Mac';

  @override
  String get referralProgram => 'برنامج الإحالة';

  @override
  String get signOut => 'تسجيل الخروج';

  @override
  String get appAndDeviceCopied => 'تم نسخ تفاصيل التطبيق والجهاز';

  @override
  String get wrapped2025 => 'ملخص 2025';

  @override
  String get yourPrivacyYourControl => 'خصوصيتك، تحكمك';

  @override
  String get privacyIntro =>
      'في Omi، نحن ملتزمون بحماية خصوصيتك. تتيح لك هذه الصفحة التحكم في كيفية تخزين بياناتك واستخدامها.';

  @override
  String get learnMore => 'اعرف المزيد...';

  @override
  String get dataProtectionLevel => 'مستوى حماية البيانات';

  @override
  String get dataProtectionDesc =>
      'بياناتك محمية افتراضياً بتشفير قوي. راجع إعداداتك وخيارات الخصوصية المستقبلية أدناه.';

  @override
  String get appAccess => 'وصول التطبيقات';

  @override
  String get appAccessDesc => 'يمكن للتطبيقات التالية الوصول إلى بياناتك. اضغط على تطبيق لإدارة أذوناته.';

  @override
  String get noAppsExternalAccess => 'لا توجد تطبيقات مثبتة لها وصول خارجي إلى بياناتك.';

  @override
  String get deviceName => 'اسم الجهاز';

  @override
  String get deviceId => 'معرف الجهاز';

  @override
  String get firmware => 'البرنامج الثابت';

  @override
  String get sdCardSync => 'مزامنة بطاقة SD';

  @override
  String get hardwareRevision => 'مراجعة الأجهزة';

  @override
  String get modelNumber => 'رقم الطراز';

  @override
  String get manufacturer => 'الشركة المصنعة';

  @override
  String get doubleTap => 'نقرة مزدوجة';

  @override
  String get ledBrightness => 'سطوع LED';

  @override
  String get micGain => 'تضخيم الميكروفون';

  @override
  String get disconnect => 'قطع الاتصال';

  @override
  String get forgetDevice => 'نسيان الجهاز';

  @override
  String get chargingIssues => 'مشاكل الشحن';

  @override
  String get disconnectDevice => 'قطع اتصال الجهاز';

  @override
  String get unpairDevice => 'إلغاء إقران الجهاز';

  @override
  String get unpairAndForget => 'إلغاء الإقران ونسيان الجهاز';

  @override
  String get deviceDisconnectedMessage => 'تم قطع اتصال Omi الخاص بك 😔';

  @override
  String get deviceUnpairedMessage =>
      'تم إلغاء إقران الجهاز. انتقل إلى الإعدادات > البلوتوث وانسَ الجهاز لإكمال إلغاء الإقران.';

  @override
  String get unpairDialogTitle => 'إلغاء إقران الجهاز';

  @override
  String get unpairDialogMessage =>
      'سيؤدي هذا إلى إلغاء إقران الجهاز بحيث يمكن توصيله بهاتف آخر. ستحتاج إلى الذهاب إلى الإعدادات > البلوتوث ونسيان الجهاز لإكمال العملية.';

  @override
  String get deviceNotConnected => 'الجهاز غير متصل';

  @override
  String get connectDeviceMessage => 'قم بتوصيل جهاز Omi الخاص بك للوصول\nإلى إعدادات الجهاز والتخصيص';

  @override
  String get deviceInfoSection => 'معلومات الجهاز';

  @override
  String get customizationSection => 'التخصيص';

  @override
  String get hardwareSection => 'الأجهزة';

  @override
  String get v2Undetected => 'لم يتم اكتشاف V2';

  @override
  String get v2UndetectedMessage => 'نرى أن لديك جهاز V1 أو أن جهازك غير متصل. وظيفة بطاقة SD متاحة فقط لأجهزة V2.';

  @override
  String get endConversation => 'إنهاء المحادثة';

  @override
  String get pauseResume => 'إيقاف مؤقت/استئناف';

  @override
  String get starConversation => 'تمييز المحادثة بنجمة';

  @override
  String get doubleTapAction => 'إجراء النقر المزدوج';

  @override
  String get endAndProcess => 'إنهاء ومعالجة المحادثة';

  @override
  String get pauseResumeRecording => 'إيقاف مؤقت/استئناف التسجيل';

  @override
  String get starOngoing => 'تمييز المحادثة الجارية بنجمة';

  @override
  String get off => 'إيقاف';

  @override
  String get max => 'الحد الأقصى';

  @override
  String get mute => 'كتم';

  @override
  String get quiet => 'هادئ';

  @override
  String get normal => 'عادي';

  @override
  String get high => 'عالي';

  @override
  String get micGainDescMuted => 'الميكروفون مكتوم';

  @override
  String get micGainDescLow => 'هادئ جداً - للبيئات الصاخبة';

  @override
  String get micGainDescModerate => 'هادئ - للضوضاء المعتدلة';

  @override
  String get micGainDescNeutral => 'متعادل - تسجيل متوازن';

  @override
  String get micGainDescSlightlyBoosted => 'معزز قليلاً - للاستخدام العادي';

  @override
  String get micGainDescBoosted => 'معزز - للبيئات الهادئة';

  @override
  String get micGainDescHigh => 'عالي - للأصوات البعيدة أو الناعمة';

  @override
  String get micGainDescVeryHigh => 'عالي جداً - للمصادر الهادئة جداً';

  @override
  String get micGainDescMax => 'الحد الأقصى - استخدم بحذر';

  @override
  String get developerSettingsTitle => 'إعدادات المطور';

  @override
  String get saving => 'جارٍ الحفظ...';

  @override
  String get personaConfig => 'قم بتكوين شخصية الذكاء الاصطناعي الخاصة بك';

  @override
  String get beta => 'تجريبي';

  @override
  String get transcription => 'النسخ';

  @override
  String get transcriptionConfig => 'قم بتكوين موفر STT';

  @override
  String get conversationTimeout => 'مهلة المحادثة';

  @override
  String get conversationTimeoutConfig => 'حدد متى تنتهي المحادثات تلقائياً';

  @override
  String get importData => 'استيراد البيانات';

  @override
  String get importDataConfig => 'استيراد البيانات من مصادر أخرى';

  @override
  String get debugDiagnostics => 'تصحيح الأخطاء والتشخيصات';

  @override
  String get endpointUrl => 'رابط نقطة النهاية';

  @override
  String get noApiKeys => 'لا توجد مفاتيح API بعد';

  @override
  String get createKeyToStart => 'أنشئ مفتاحاً للبدء';

  @override
  String get createKey => 'إنشاء مفتاح';

  @override
  String get docs => 'المستندات';

  @override
  String get yourOmiInsights => 'رؤى Omi الخاصة بك';

  @override
  String get today => 'اليوم';

  @override
  String get thisMonth => 'هذا الشهر';

  @override
  String get thisYear => 'هذا العام';

  @override
  String get allTime => 'كل الأوقات';

  @override
  String get noActivityYet => 'لا يوجد نشاط بعد';

  @override
  String get startConversationToSeeInsights => 'ابدأ محادثة مع Omi\nلرؤية رؤى استخدامك هنا.';

  @override
  String get listening => 'الاستماع';

  @override
  String get listeningSubtitle => 'إجمالي الوقت الذي استمع فيه Omi بنشاط.';

  @override
  String get understanding => 'الفهم';

  @override
  String get understandingSubtitle => 'الكلمات المفهومة من محادثاتك.';

  @override
  String get providing => 'التوفير';

  @override
  String get providingSubtitle => 'المهام والملاحظات الملتقطة تلقائياً.';

  @override
  String get remembering => 'التذكر';

  @override
  String get rememberingSubtitle => 'الحقائق والتفاصيل المحفوظة من أجلك.';

  @override
  String get unlimitedPlan => 'خطة غير محدودة';

  @override
  String get managePlan => 'إدارة الخطة';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'ستنتهي خطتك في $date.';
  }

  @override
  String renewsOn(String date) {
    return 'تتجدد خطتك في $date.';
  }

  @override
  String get basicPlan => 'خطة مجانية';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used من $limit دقيقة مستخدمة';
  }

  @override
  String get upgrade => 'ترقية';

  @override
  String get upgradeToUnlimited => 'الترقية إلى غير محدود';

  @override
  String basicPlanDesc(int limit) {
    return 'تتضمن خطتك $limit دقيقة مجانية شهرياً. قم بالترقية للحصول على دقائق غير محدودة.';
  }

  @override
  String get shareStatsMessage => 'مشاركة إحصائيات Omi الخاصة بي! (omi.me - مساعدك الذكي الدائم)';

  @override
  String get sharePeriodToday => 'اليوم، قام omi بـ:';

  @override
  String get sharePeriodMonth => 'هذا الشهر، قام omi بـ:';

  @override
  String get sharePeriodYear => 'هذا العام، قام omi بـ:';

  @override
  String get sharePeriodAllTime => 'حتى الآن، قام omi بـ:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 استمع لمدة $minutes دقيقة';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 فهم $words كلمة';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ قدم $count رؤية';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 تذكر $count ذكرى';
  }

  @override
  String get debugLogs => 'سجلات التصحيح';

  @override
  String get debugLogsAutoDelete => 'يتم الحذف التلقائي بعد 3 أيام.';

  @override
  String get debugLogsDesc => 'يساعد في تشخيص المشاكل';

  @override
  String get noLogFilesFound => 'لم يتم العثور على ملفات السجل.';

  @override
  String get omiDebugLog => 'سجل تصحيح Omi';

  @override
  String get logShared => 'تمت مشاركة السجل';

  @override
  String get selectLogFile => 'حدد ملف السجل';

  @override
  String get shareLogs => 'مشاركة السجلات';

  @override
  String get debugLogCleared => 'تم مسح سجل التصحيح';

  @override
  String get exportStarted => 'بدأ التصدير. قد يستغرق هذا بضع ثوان...';

  @override
  String get exportAllData => 'تصدير جميع البيانات';

  @override
  String get exportDataDesc => 'تصدير المحادثات إلى ملف JSON';

  @override
  String get exportedConversations => 'المحادثات المصدرة من Omi';

  @override
  String get exportShared => 'تمت مشاركة التصدير';

  @override
  String get deleteKnowledgeGraphTitle => 'حذف الرسم البياني للمعرفة؟';

  @override
  String get deleteKnowledgeGraphMessage =>
      'سيؤدي هذا إلى حذف جميع بيانات الرسم البياني للمعرفة المشتقة (العقد والاتصالات). ستبقى ذكرياتك الأصلية آمنة. سيتم إعادة بناء الرسم البياني بمرور الوقت أو عند الطلب التالي.';

  @override
  String get knowledgeGraphDeleted => 'تم حذف الرسم البياني المعرفي';

  @override
  String deleteGraphFailed(String error) {
    return 'فشل حذف الرسم: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'حذف الرسم البياني للمعرفة';

  @override
  String get deleteKnowledgeGraphDesc => 'مسح جميع العقد والاتصالات';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'خادم MCP';

  @override
  String get mcpServerDesc => 'ربط مساعدي الذكاء الاصطناعي ببياناتك';

  @override
  String get serverUrl => 'عنوان URL للخادم';

  @override
  String get urlCopied => 'تم نسخ الرابط';

  @override
  String get apiKeyAuth => 'مصادقة مفتاح API';

  @override
  String get header => 'الرأس';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'معرف العميل';

  @override
  String get clientSecret => 'سر العميل';

  @override
  String get useMcpApiKey => 'استخدم مفتاح MCP API الخاص بك';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'أحداث المحادثة';

  @override
  String get newConversationCreated => 'تم إنشاء محادثة جديدة';

  @override
  String get realtimeTranscript => 'النص الفوري';

  @override
  String get transcriptReceived => 'تم استلام النسخ';

  @override
  String get audioBytes => 'بايتات الصوت';

  @override
  String get audioDataReceived => 'تم استلام بيانات الصوت';

  @override
  String get intervalSeconds => 'الفاصل الزمني (بالثواني)';

  @override
  String get daySummary => 'ملخص اليوم';

  @override
  String get summaryGenerated => 'تم إنشاء الملخص';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'أضف إلى claude_desktop_config.json';

  @override
  String get copyConfig => 'نسخ التكوين';

  @override
  String get configCopied => 'تم نسخ التكوين إلى الحافظة';

  @override
  String get listeningMins => 'الاستماع (دقائق)';

  @override
  String get understandingWords => 'الفهم (كلمات)';

  @override
  String get insights => 'رؤى';

  @override
  String get memories => 'الذكريات';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used من $limit دقيقة مستخدمة هذا الشهر';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used من $limit كلمة مستخدمة هذا الشهر';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used من $limit رؤية تم اكتسابها هذا الشهر';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used من $limit ذكرى تم إنشاؤها هذا الشهر';
  }

  @override
  String get visibility => 'الظهور';

  @override
  String get visibilitySubtitle => 'تحكم في المحادثات التي تظهر في قائمتك';

  @override
  String get showShortConversations => 'إظهار المحادثات القصيرة';

  @override
  String get showShortConversationsDesc => 'عرض المحادثات الأقصر من الحد الأدنى';

  @override
  String get showDiscardedConversations => 'إظهار المحادثات المهملة';

  @override
  String get showDiscardedConversationsDesc => 'تضمين المحادثات المميزة كمهملة';

  @override
  String get shortConversationThreshold => 'حد المحادثة القصيرة';

  @override
  String get shortConversationThresholdSubtitle => 'سيتم إخفاء المحادثات الأقصر من هذا ما لم يتم تمكينها أعلاه';

  @override
  String get durationThreshold => 'حد المدة';

  @override
  String get durationThresholdDesc => 'إخفاء المحادثات الأقصر من هذا';

  @override
  String minLabel(int count) {
    return '$count دقيقة';
  }

  @override
  String get customVocabularyTitle => 'المفردات المخصصة';

  @override
  String get addWords => 'إضافة كلمات';

  @override
  String get addWordsDesc => 'أسماء أو مصطلحات أو كلمات غير شائعة';

  @override
  String get vocabularyHint => 'Omi، Callie، OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'قريباً';

  @override
  String get integrationsFooter => 'قم بتوصيل تطبيقاتك لعرض البيانات والمقاييس في الدردشة.';

  @override
  String get completeAuthInBrowser => 'يرجى إكمال المصادقة في متصفحك. بعد الانتهاء، ارجع إلى التطبيق.';

  @override
  String failedToStartAuth(String appName) {
    return 'فشل بدء مصادقة $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'قطع الاتصال بـ $appName؟';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'هل أنت متأكد من رغبتك في قطع الاتصال بـ $appName؟ يمكنك إعادة الاتصال في أي وقت.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'تم قطع الاتصال بـ $appName';
  }

  @override
  String get failedToDisconnect => 'فشل قطع الاتصال';

  @override
  String connectTo(String appName) {
    return 'الاتصال بـ $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'ستحتاج إلى تفويض Omi للوصول إلى بيانات $appName الخاصة بك. سيتم فتح متصفحك للمصادقة.';
  }

  @override
  String get continueAction => 'متابعة';

  @override
  String get languageTitle => 'اللغة';

  @override
  String get primaryLanguage => 'اللغة الأساسية';

  @override
  String get automaticTranslation => 'الترجمة التلقائية';

  @override
  String get detectLanguages => 'اكتشاف أكثر من 10 لغات';

  @override
  String get authorizeSavingRecordings => 'التفويض بحفظ التسجيلات';

  @override
  String get thanksForAuthorizing => 'شكراً على التفويض!';

  @override
  String get needYourPermission => 'نحتاج إذنك';

  @override
  String get alreadyGavePermission => 'لقد منحتنا بالفعل إذناً بحفظ تسجيلاتك. إليك تذكير بسبب حاجتنا إليه:';

  @override
  String get wouldLikePermission => 'نود الحصول على إذنك لحفظ تسجيلاتك الصوتية. إليك السبب:';

  @override
  String get improveSpeechProfile => 'تحسين ملف الصوت الخاص بك';

  @override
  String get improveSpeechProfileDesc => 'نستخدم التسجيلات لمواصلة تدريب وتحسين ملف الصوت الشخصي الخاص بك.';

  @override
  String get trainFamilyProfiles => 'تدريب ملفات تعريف الأصدقاء والعائلة';

  @override
  String get trainFamilyProfilesDesc => 'تساعدنا تسجيلاتك في التعرف على أصدقائك وعائلتك وإنشاء ملفات تعريف لهم.';

  @override
  String get enhanceTranscriptAccuracy => 'تحسين دقة النص المكتوب';

  @override
  String get enhanceTranscriptAccuracyDesc => 'مع تحسن نموذجنا، يمكننا توفير نتائج نسخ أفضل لتسجيلاتك.';

  @override
  String get legalNotice =>
      'إشعار قانوني: قد تختلف قانونية تسجيل وتخزين البيانات الصوتية اعتماداً على موقعك وكيفية استخدامك لهذه الميزة. من مسؤوليتك ضمان الامتثال للقوانين واللوائح المحلية.';

  @override
  String get alreadyAuthorized => 'تم التفويض بالفعل';

  @override
  String get authorize => 'تفويض';

  @override
  String get revokeAuthorization => 'إلغاء التفويض';

  @override
  String get authorizationSuccessful => 'التفويض ناجح!';

  @override
  String get failedToAuthorize => 'فشل التفويض. يرجى المحاولة مرة أخرى.';

  @override
  String get authorizationRevoked => 'تم إلغاء التفويض.';

  @override
  String get recordingsDeleted => 'تم حذف التسجيلات.';

  @override
  String get failedToRevoke => 'فشل إلغاء التفويض. يرجى المحاولة مرة أخرى.';

  @override
  String get permissionRevokedTitle => 'تم إلغاء الإذن';

  @override
  String get permissionRevokedMessage => 'هل تريد منا حذف جميع تسجيلاتك الحالية أيضاً؟';

  @override
  String get yes => 'نعم';

  @override
  String get editName => 'تعديل الاسم';

  @override
  String get howShouldOmiCallYou => 'كيف يجب على Omi أن يناديك؟';

  @override
  String get enterYourName => 'أدخل اسمك';

  @override
  String get nameCannotBeEmpty => 'لا يمكن أن يكون الاسم فارغاً';

  @override
  String get nameUpdatedSuccessfully => 'تم تحديث الاسم بنجاح!';

  @override
  String get calendarSettings => 'إعدادات التقويم';

  @override
  String get calendarProviders => 'موفرو التقويم';

  @override
  String get macOsCalendar => 'تقويم macOS';

  @override
  String get connectMacOsCalendar => 'قم بتوصيل تقويم macOS المحلي الخاص بك';

  @override
  String get googleCalendar => 'تقويم Google';

  @override
  String get syncGoogleAccount => 'المزامنة مع حساب Google الخاص بك';

  @override
  String get showMeetingsMenuBar => 'إظهار الاجتماعات القادمة في شريط القوائم';

  @override
  String get showMeetingsMenuBarDesc => 'عرض اجتماعك التالي والوقت حتى يبدأ في شريط قوائم macOS';

  @override
  String get showEventsNoParticipants => 'إظهار الأحداث بدون مشاركين';

  @override
  String get showEventsNoParticipantsDesc => 'عند التمكين، يعرض القادم الأحداث بدون مشاركين أو رابط فيديو.';

  @override
  String get yourMeetings => 'اجتماعاتك';

  @override
  String get refresh => 'تحديث';

  @override
  String get noUpcomingMeetings => 'لا توجد اجتماعات قادمة';

  @override
  String get checkingNextDays => 'التحقق من الـ 30 يوماً القادمة';

  @override
  String get tomorrow => 'غداً';

  @override
  String get googleCalendarComingSoon => 'تكامل تقويم Google قريباً!';

  @override
  String connectedAsUser(String userId) {
    return 'متصل كمستخدم: $userId';
  }

  @override
  String get defaultWorkspace => 'مساحة العمل الافتراضية';

  @override
  String get tasksCreatedInWorkspace => 'سيتم إنشاء المهام في مساحة العمل هذه';

  @override
  String get defaultProjectOptional => 'المشروع الافتراضي (اختياري)';

  @override
  String get leaveUnselectedTasks => 'اترك غير محدد لإنشاء مهام بدون مشروع';

  @override
  String get noProjectsInWorkspace => 'لم يتم العثور على مشاريع في مساحة العمل هذه';

  @override
  String get conversationTimeoutDesc => 'اختر المدة التي يجب الانتظار فيها في صمت قبل إنهاء المحادثة تلقائياً:';

  @override
  String get timeout2Minutes => 'دقيقتان';

  @override
  String get timeout2MinutesDesc => 'إنهاء المحادثة بعد دقيقتين من الصمت';

  @override
  String get timeout5Minutes => '5 دقائق';

  @override
  String get timeout5MinutesDesc => 'إنهاء المحادثة بعد 5 دقائق من الصمت';

  @override
  String get timeout10Minutes => '10 دقائق';

  @override
  String get timeout10MinutesDesc => 'إنهاء المحادثة بعد 10 دقائق من الصمت';

  @override
  String get timeout30Minutes => '30 دقيقة';

  @override
  String get timeout30MinutesDesc => 'إنهاء المحادثة بعد 30 دقيقة من الصمت';

  @override
  String get timeout4Hours => '4 ساعات';

  @override
  String get timeout4HoursDesc => 'إنهاء المحادثة بعد 4 ساعات من الصمت';

  @override
  String get conversationEndAfterHours => 'ستنتهي المحادثات الآن بعد 4 ساعات من الصمت';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'ستنتهي المحادثات الآن بعد $minutes دقيقة من الصمت';
  }

  @override
  String get tellUsPrimaryLanguage => 'أخبرنا بلغتك الأساسية';

  @override
  String get languageForTranscription => 'حدد لغتك للحصول على نسخ أكثر دقة وتجربة شخصية.';

  @override
  String get singleLanguageModeInfo => 'وضع اللغة الواحدة ممكّن. الترجمة معطلة لدقة أعلى.';

  @override
  String get searchLanguageHint => 'بحث عن اللغة بالاسم أو الرمز';

  @override
  String get noLanguagesFound => 'لم يتم العثور على لغات';

  @override
  String get skip => 'تخطي';

  @override
  String languageSetTo(String language) {
    return 'تم تعيين اللغة إلى $language';
  }

  @override
  String get failedToSetLanguage => 'فشل تعيين اللغة';

  @override
  String appSettings(String appName) {
    return 'إعدادات $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'قطع الاتصال بـ $appName؟';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'سيؤدي هذا إلى حذف مصادقة $appName الخاصة بك. ستحتاج إلى إعادة الاتصال لاستخدامه مرة أخرى.';
  }

  @override
  String connectedToApp(String appName) {
    return 'متصل بـ $appName';
  }

  @override
  String get account => 'الحساب';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'سيتم مزامنة مهامك مع حساب $appName الخاص بك';
  }

  @override
  String get defaultSpace => 'المساحة الافتراضية';

  @override
  String get selectSpaceInWorkspace => 'حدد مساحة في مساحة العمل الخاصة بك';

  @override
  String get noSpacesInWorkspace => 'لم يتم العثور على مساحات في مساحة العمل هذه';

  @override
  String get defaultList => 'القائمة الافتراضية';

  @override
  String get tasksAddedToList => 'سيتم إضافة المهام إلى هذه القائمة';

  @override
  String get noListsInSpace => 'لم يتم العثور على قوائم في هذه المساحة';

  @override
  String failedToLoadRepos(String error) {
    return 'فشل تحميل المستودعات: $error';
  }

  @override
  String get defaultRepoSaved => 'تم حفظ المستودع الافتراضي';

  @override
  String get failedToSaveDefaultRepo => 'فشل حفظ المستودع الافتراضي';

  @override
  String get defaultRepository => 'المستودع الافتراضي';

  @override
  String get selectDefaultRepoDesc =>
      'حدد مستودعاً افتراضياً لإنشاء المشكلات. لا يزال بإمكانك تحديد مستودع مختلف عند إنشاء المشكلات.';

  @override
  String get noReposFound => 'لم يتم العثور على مستودعات';

  @override
  String get private => 'خاص';

  @override
  String updatedDate(String date) {
    return 'تم التحديث $date';
  }

  @override
  String get yesterday => 'أمس';

  @override
  String daysAgo(int count) {
    return 'منذ $count أيام';
  }

  @override
  String get oneWeekAgo => 'منذ أسبوع';

  @override
  String weeksAgo(int count) {
    return 'منذ $count أسابيع';
  }

  @override
  String get oneMonthAgo => 'منذ شهر';

  @override
  String monthsAgo(int count) {
    return 'منذ $count أشهر';
  }

  @override
  String get issuesCreatedInRepo => 'سيتم إنشاء المشكلات في مستودعك الافتراضي';

  @override
  String get taskIntegrations => 'تكاملات المهام';

  @override
  String get configureSettings => 'تكوين الإعدادات';

  @override
  String get completeAuthBrowser => 'يرجى إكمال المصادقة في متصفحك. بعد الانتهاء، ارجع إلى التطبيق.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'فشل بدء مصادقة $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'الاتصال بـ $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'ستحتاج إلى تفويض Omi لإنشاء مهام في حساب $appName الخاص بك. سيتم فتح متصفحك للمصادقة.';
  }

  @override
  String get continueButton => 'متابعة';

  @override
  String appIntegration(String appName) {
    return 'تكامل $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'التكامل مع $appName قريباً! نعمل بجد لنوفر لك المزيد من خيارات إدارة المهام.';
  }

  @override
  String get gotIt => 'فهمت';

  @override
  String get tasksExportedOneApp => 'يمكن تصدير المهام إلى تطبيق واحد في كل مرة.';

  @override
  String get completeYourUpgrade => 'أكمل ترقيتك';

  @override
  String get importConfiguration => 'استيراد التكوين';

  @override
  String get exportConfiguration => 'تصدير التكوين';

  @override
  String get bringYourOwn => 'احضر الخاص بك';

  @override
  String get payYourSttProvider => 'استخدم omi بحرية. أنت تدفع فقط لموفر STT الخاص بك مباشرة.';

  @override
  String get freeMinutesMonth => '1,200 دقيقة مجانية شهرياً متضمنة. غير محدود مع ';

  @override
  String get omiUnlimited => 'Omi غير محدود';

  @override
  String get hostRequired => 'المضيف مطلوب';

  @override
  String get validPortRequired => 'المنفذ الصحيح مطلوب';

  @override
  String get validWebsocketUrlRequired => 'رابط WebSocket صحيح مطلوب (wss://)';

  @override
  String get apiUrlRequired => 'رابط API مطلوب';

  @override
  String get apiKeyRequired => 'مفتاح API مطلوب';

  @override
  String get invalidJsonConfig => 'تكوين JSON غير صالح';

  @override
  String errorSaving(String error) {
    return 'خطأ في الحفظ: $error';
  }

  @override
  String get configCopiedToClipboard => 'تم نسخ التكوين إلى الحافظة';

  @override
  String get pasteJsonConfig => 'الصق تكوين JSON الخاص بك أدناه:';

  @override
  String get addApiKeyAfterImport => 'ستحتاج إلى إضافة مفتاح API الخاص بك بعد الاستيراد';

  @override
  String get paste => 'لصق';

  @override
  String get import => 'استيراد';

  @override
  String get invalidProviderInConfig => 'موفر غير صالح في التكوين';

  @override
  String importedConfig(String providerName) {
    return 'تم استيراد تكوين $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'JSON غير صالح: $error';
  }

  @override
  String get provider => 'الموفر';

  @override
  String get live => 'مباشر';

  @override
  String get onDevice => 'على الجهاز';

  @override
  String get apiUrl => 'رابط API';

  @override
  String get enterSttHttpEndpoint => 'أدخل نقطة نهاية STT HTTP الخاصة بك';

  @override
  String get websocketUrl => 'رابط WebSocket';

  @override
  String get enterLiveSttWebsocket => 'أدخل نقطة نهاية WebSocket STT المباشرة';

  @override
  String get apiKey => 'مفتاح API';

  @override
  String get enterApiKey => 'أدخل مفتاح API الخاص بك';

  @override
  String get storedLocallyNeverShared => 'يُخزن محلياً، ولا يُشارك أبداً';

  @override
  String get host => 'المضيف';

  @override
  String get port => 'المنفذ';

  @override
  String get advanced => 'متقدم';

  @override
  String get configuration => 'التكوين';

  @override
  String get requestConfiguration => 'تكوين الطلب';

  @override
  String get responseSchema => 'مخطط الاستجابة';

  @override
  String get modified => 'معدل';

  @override
  String get resetRequestConfig => 'إعادة تعيين تكوين الطلب إلى الافتراضي';

  @override
  String get logs => 'السجلات';

  @override
  String get logsCopied => 'تم نسخ السجلات';

  @override
  String get noLogsYet => 'لا توجد سجلات بعد. ابدأ التسجيل لرؤية نشاط STT المخصص.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device يستخدم $reason. سيتم استخدام Omi.';
  }

  @override
  String get omiTranscription => 'نسخ Omi';

  @override
  String get bestInClassTranscription => 'أفضل نسخ في فئته بدون إعداد';

  @override
  String get instantSpeakerLabels => 'تسميات المتحدثين الفورية';

  @override
  String get languageTranslation => 'ترجمة أكثر من 100 لغة';

  @override
  String get optimizedForConversation => 'محسّن للمحادثة';

  @override
  String get autoLanguageDetection => 'اكتشاف اللغة التلقائي';

  @override
  String get highAccuracy => 'دقة عالية';

  @override
  String get privacyFirst => 'الخصوصية أولاً';

  @override
  String get saveChanges => 'حفظ التغييرات';

  @override
  String get resetToDefault => 'إعادة تعيين إلى الافتراضي';

  @override
  String get viewTemplate => 'عرض النموذج';

  @override
  String get trySomethingLike => 'جرب شيئاً مثل...';

  @override
  String get tryIt => 'جربه';

  @override
  String get creatingPlan => 'إنشاء خطة';

  @override
  String get developingLogic => 'تطوير المنطق';

  @override
  String get designingApp => 'تصميم التطبيق';

  @override
  String get generatingIconStep => 'إنشاء أيقونة';

  @override
  String get finalTouches => 'اللمسات الأخيرة';

  @override
  String get processing => 'جاري المعالجة...';

  @override
  String get features => 'الميزات';

  @override
  String get creatingYourApp => 'جاري إنشاء تطبيقك...';

  @override
  String get generatingIcon => 'جاري إنشاء الأيقونة...';

  @override
  String get whatShouldWeMake => 'ماذا يجب أن نصنع؟';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'الوصف';

  @override
  String get publicLabel => 'عام';

  @override
  String get privateLabel => 'خاص';

  @override
  String get free => 'مجاني';

  @override
  String get perMonth => '/ شهرياً';

  @override
  String get tailoredConversationSummaries => 'ملخصات محادثة مخصصة';

  @override
  String get customChatbotPersonality => 'شخصية chatbot مخصصة';

  @override
  String get makePublic => 'جعلها عامة';

  @override
  String get anyoneCanDiscover => 'يمكن لأي شخص اكتشاف تطبيقك';

  @override
  String get onlyYouCanUse => 'أنت فقط يمكنك استخدام هذا التطبيق';

  @override
  String get paidApp => 'تطبيق مدفوع';

  @override
  String get usersPayToUse => 'يدفع المستخدمون لاستخدام تطبيقك';

  @override
  String get freeForEveryone => 'مجاني للجميع';

  @override
  String get perMonthLabel => '/ شهرياً';

  @override
  String get creating => 'جاري الإنشاء...';

  @override
  String get createApp => 'إنشاء تطبيق';

  @override
  String get searchingForDevices => 'جاري البحث عن الأجهزة...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'أجهزة',
      one: 'جهاز',
    );
    return '$count $_temp0 تم العثور عليها بالقرب منك';
  }

  @override
  String get pairingSuccessful => 'نجح الإقران';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'خطأ في الاتصال بـ Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'لا تظهر هذا مرة أخرى';

  @override
  String get iUnderstand => 'أفهم';

  @override
  String get enableBluetooth => 'تمكين البلوتوث';

  @override
  String get bluetoothNeeded =>
      'يحتاج Omi إلى البلوتوث للاتصال بجهازك القابل للارتداء. يرجى تمكين البلوتوث والمحاولة مرة أخرى.';

  @override
  String get contactSupport => 'الاتصال بالدعم؟';

  @override
  String get connectLater => 'الاتصال لاحقاً';

  @override
  String get grantPermissions => 'منح الأذونات';

  @override
  String get backgroundActivity => 'النشاط في الخلفية';

  @override
  String get backgroundActivityDesc => 'دع Omi يعمل في الخلفية لاستقرار أفضل';

  @override
  String get locationAccess => 'الوصول إلى الموقع';

  @override
  String get locationAccessDesc => 'تمكين الموقع في الخلفية للحصول على التجربة الكاملة';

  @override
  String get notifications => 'الإشعارات';

  @override
  String get notificationsDesc => 'تمكين الإشعارات للبقاء على اطلاع';

  @override
  String get locationServiceDisabled => 'خدمة الموقع معطلة';

  @override
  String get locationServiceDisabledDesc =>
      'خدمة الموقع معطلة. يرجى الذهاب إلى الإعدادات > الخصوصية والأمان > خدمات الموقع وتمكينها';

  @override
  String get backgroundLocationDenied => 'تم رفض الوصول إلى الموقع في الخلفية';

  @override
  String get backgroundLocationDeniedDesc => 'يرجى الذهاب إلى إعدادات الجهاز وتعيين إذن الموقع إلى \"السماح دائماً\"';

  @override
  String get lovingOmi => 'تحب Omi؟';

  @override
  String get leaveReviewIos =>
      'ساعدنا في الوصول إلى المزيد من الأشخاص من خلال ترك تقييم في App Store. ملاحظاتك تعني لنا الكثير!';

  @override
  String get leaveReviewAndroid =>
      'ساعدنا في الوصول إلى المزيد من الأشخاص من خلال ترك تقييم في Google Play Store. ملاحظاتك تعني لنا الكثير!';

  @override
  String get rateOnAppStore => 'التقييم على App Store';

  @override
  String get rateOnGooglePlay => 'التقييم على Google Play';

  @override
  String get maybeLater => 'ربما لاحقًا';

  @override
  String get speechProfileIntro => 'يحتاج Omi إلى تعلم أهدافك وصوتك. ستتمكن من تعديله لاحقًا.';

  @override
  String get getStarted => 'ابدأ';

  @override
  String get allDone => 'تم كل شيء!';

  @override
  String get keepGoing => 'استمر، أنت تقوم بعمل رائع';

  @override
  String get skipThisQuestion => 'تخطي هذا السؤال';

  @override
  String get skipForNow => 'تخطي الآن';

  @override
  String get connectionError => 'خطأ في الاتصال';

  @override
  String get connectionErrorDesc => 'فشل الاتصال بالخادم. يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى.';

  @override
  String get invalidRecordingMultipleSpeakers => 'تم اكتشاف تسجيل غير صالح';

  @override
  String get multipleSpeakersDesc =>
      'يبدو أن هناك عدة متحدثين في التسجيل. يرجى التأكد من أنك في موقع هادئ والمحاولة مرة أخرى.';

  @override
  String get tooShortDesc => 'لا يوجد كلام كافٍ مكتشف. يرجى التحدث أكثر والمحاولة مرة أخرى.';

  @override
  String get invalidRecordingDesc => 'يرجى التأكد من التحدث لمدة 5 ثوانٍ على الأقل وليس أكثر من 90.';

  @override
  String get areYouThere => 'هل أنت هناك؟';

  @override
  String get noSpeechDesc =>
      'لم نتمكن من اكتشاف أي كلام. يرجى التأكد من التحدث لمدة 10 ثوانٍ على الأقل وليس أكثر من 3 دقائق.';

  @override
  String get connectionLost => 'فُقد الاتصال';

  @override
  String get connectionLostDesc => 'تم انقطاع الاتصال. يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى.';

  @override
  String get tryAgain => 'حاول مرة أخرى';

  @override
  String get connectOmiOmiGlass => 'توصيل Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'متابعة بدون جهاز';

  @override
  String get permissionsRequired => 'الأذونات مطلوبة';

  @override
  String get permissionsRequiredDesc =>
      'يحتاج هذا التطبيق إلى أذونات البلوتوث والموقع للعمل بشكل صحيح. يرجى تمكينها في الإعدادات.';

  @override
  String get openSettings => 'فتح الإعدادات';

  @override
  String get wantDifferentName => 'تريد أن يُناديك باسم آخر؟';

  @override
  String get whatsYourName => 'ما اسمك؟';

  @override
  String get speakTranscribeSummarize => 'تحدث. انسخ. لخص.';

  @override
  String get signInWithApple => 'تسجيل الدخول باستخدام Apple';

  @override
  String get signInWithGoogle => 'تسجيل الدخول باستخدام Google';

  @override
  String get byContinuingAgree => 'بالمتابعة، فإنك توافق على ';

  @override
  String get termsOfUse => 'شروط الاستخدام';

  @override
  String get omiYourAiCompanion => 'Omi – رفيقك الذكي';

  @override
  String get captureEveryMoment =>
      'احتفظ بكل لحظة. احصل على ملخصات مدعومة بالذكاء الاصطناعي.\nلا تدون ملاحظات بعد الآن.';

  @override
  String get appleWatchSetup => 'إعداد Apple Watch';

  @override
  String get permissionRequestedExclaim => 'تم طلب الإذن!';

  @override
  String get microphonePermission => 'إذن الميكروفون';

  @override
  String get permissionGrantedNow => 'تم منح الإذن! الآن:\n\nافتح تطبيق Omi على ساعتك واضغط على \"متابعة\" أدناه';

  @override
  String get needMicrophonePermission =>
      'نحتاج إذن الميكروفون.\n\n1. اضغط على \"منح الإذن\"\n2. اسمح على iPhone الخاص بك\n3. سيُغلق تطبيق الساعة\n4. أعد فتحه واضغط على \"متابعة\"';

  @override
  String get grantPermissionButton => 'منح الإذن';

  @override
  String get needHelp => 'تحتاج مساعدة؟';

  @override
  String get troubleshootingSteps =>
      'استكشاف الأخطاء وإصلاحها:\n\n1. تأكد من تثبيت Omi على ساعتك\n2. افتح تطبيق Omi على ساعتك\n3. ابحث عن نافذة الإذن المنبثقة\n4. اضغط على \"السماح\" عند المطالبة\n5. سيغلق التطبيق على ساعتك - أعد فتحه\n6. ارجع واضغط على \"متابعة\" على iPhone الخاص بك';

  @override
  String get recordingStartedSuccessfully => 'بدأ التسجيل بنجاح!';

  @override
  String get permissionNotGrantedYet =>
      'لم يتم منح الإذن بعد. يرجى التأكد من أنك سمحت بالوصول إلى الميكروفون وأعدت فتح التطبيق على ساعتك.';

  @override
  String errorRequestingPermission(String error) {
    return 'خطأ في طلب الإذن: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'خطأ في بدء التسجيل: $error';
  }

  @override
  String get selectPrimaryLanguage => 'حدد لغتك الأساسية';

  @override
  String get languageBenefits => 'حدد لغتك للحصول على نسخ أكثر دقة وتجربة شخصية';

  @override
  String get whatsYourPrimaryLanguage => 'ما هي لغتك الأساسية؟';

  @override
  String get selectYourLanguage => 'حدد لغتك';

  @override
  String get personalGrowthJourney => 'رحلة نموك الشخصية مع الذكاء الاصطناعي الذي يستمع لكل كلمة تقولها.';

  @override
  String get actionItemsTitle => 'المهام';

  @override
  String get actionItemsDescription => 'اضغط للتعديل • اضغط مطولاً للتحديد • اسحب للإجراءات';

  @override
  String get tabToDo => 'للقيام به';

  @override
  String get tabDone => 'تم';

  @override
  String get tabOld => 'قديم';

  @override
  String get emptyTodoMessage => '🎉 كل شيء محدث!\nلا توجد مهام معلقة';

  @override
  String get emptyDoneMessage => 'لا توجد عناصر مكتملة بعد';

  @override
  String get emptyOldMessage => '✅ لا توجد مهام قديمة';

  @override
  String get noItems => 'لا توجد عناصر';

  @override
  String get actionItemMarkedIncomplete => 'تم وضع علامة على المهمة كغير مكتملة';

  @override
  String get actionItemCompleted => 'تم إنجاز المهمة';

  @override
  String get deleteActionItemTitle => 'حذف عنصر الإجراء';

  @override
  String get deleteActionItemMessage => 'هل أنت متأكد أنك تريد حذف عنصر الإجراء هذا؟';

  @override
  String get deleteSelectedItemsTitle => 'حذف العناصر المحددة';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'هل أنت متأكد من رغبتك في حذف $count مهمة محددة$s؟';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'تم حذف المهمة \"$description\"';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return 'تم حذف $count مهمة$s';
  }

  @override
  String get failedToDeleteItem => 'فشل حذف المهمة';

  @override
  String get failedToDeleteItems => 'فشل حذف المهام';

  @override
  String get failedToDeleteSomeItems => 'فشل حذف بعض المهام';

  @override
  String get welcomeActionItemsTitle => 'جاهز للمهام';

  @override
  String get welcomeActionItemsDescription =>
      'سيستخرج الذكاء الاصطناعي الخاص بك المهام والأعمال تلقائياً من محادثاتك. ستظهر هنا عند إنشائها.';

  @override
  String get autoExtractionFeature => 'يتم استخراجها تلقائياً من المحادثات';

  @override
  String get editSwipeFeature => 'اضغط للتعديل، اسحب للإكمال أو الحذف';

  @override
  String itemsSelected(int count) {
    return '$count محدد';
  }

  @override
  String get selectAll => 'تحديد الكل';

  @override
  String get deleteSelected => 'حذف المحدد';

  @override
  String get searchMemories => 'البحث عن ذكريات...';

  @override
  String get memoryDeleted => 'تم حذف الذكرى.';

  @override
  String get undo => 'تراجع';

  @override
  String get noMemoriesYet => '🧠 لا توجد ذكريات بعد';

  @override
  String get noAutoMemories => 'لا توجد ذكريات مستخرجة تلقائياً بعد';

  @override
  String get noManualMemories => 'لا توجد ذكريات يدوية بعد';

  @override
  String get noMemoriesInCategories => 'لا توجد ذكريات في هذه الفئات';

  @override
  String get noMemoriesFound => '🔍 لم يتم العثور على ذكريات';

  @override
  String get addFirstMemory => 'أضف ذكرتك الأولى';

  @override
  String get clearMemoryTitle => 'مسح ذاكرة Omi';

  @override
  String get clearMemoryMessage => 'هل أنت متأكد من رغبتك في مسح ذاكرة Omi؟ لا يمكن التراجع عن هذا الإجراء.';

  @override
  String get clearMemoryButton => 'مسح الذاكرة';

  @override
  String get memoryClearedSuccess => 'تم مسح ذاكرة Omi عنك';

  @override
  String get noMemoriesToDelete => 'لا توجد ذكريات للحذف';

  @override
  String get createMemoryTooltip => 'إنشاء ذكرى جديدة';

  @override
  String get createActionItemTooltip => 'إنشاء مهمة جديدة';

  @override
  String get memoryManagement => 'إدارة الذاكرة';

  @override
  String get filterMemories => 'تصفية الذكريات';

  @override
  String totalMemoriesCount(int count) {
    return 'لديك $count ذكرى إجمالية';
  }

  @override
  String get publicMemories => 'ذكريات عامة';

  @override
  String get privateMemories => 'ذكريات خاصة';

  @override
  String get makeAllPrivate => 'جعل جميع الذكريات خاصة';

  @override
  String get makeAllPublic => 'جعل جميع الذكريات عامة';

  @override
  String get deleteAllMemories => 'حذف كل الذكريات';

  @override
  String get allMemoriesPrivateResult => 'جميع الذكريات خاصة الآن';

  @override
  String get allMemoriesPublicResult => 'جميع الذكريات عامة الآن';

  @override
  String get newMemory => '✨ ذاكرة جديدة';

  @override
  String get editMemory => '✏️ تعديل الذاكرة';

  @override
  String get memoryContentHint => 'أحب تناول الآيس كريم...';

  @override
  String get failedToSaveMemory => 'فشل الحفظ. يرجى التحقق من اتصالك.';

  @override
  String get saveMemory => 'حفظ الذكرى';

  @override
  String get retry => 'إعادة المحاولة';

  @override
  String get createActionItem => 'إنشاء عنصر إجراء';

  @override
  String get editActionItem => 'تعديل عنصر الإجراء';

  @override
  String get actionItemDescriptionHint => 'ما الذي يجب القيام به؟';

  @override
  String get actionItemDescriptionEmpty => 'لا يمكن أن يكون وصف المهمة فارغاً.';

  @override
  String get actionItemUpdated => 'تم تحديث المهمة';

  @override
  String get failedToUpdateActionItem => 'فشل تحديث عنصر الإجراء';

  @override
  String get actionItemCreated => 'تم إنشاء المهمة';

  @override
  String get failedToCreateActionItem => 'فشل إنشاء عنصر الإجراء';

  @override
  String get dueDate => 'تاريخ الاستحقاق';

  @override
  String get time => 'الوقت';

  @override
  String get addDueDate => 'إضافة تاريخ استحقاق';

  @override
  String get pressDoneToSave => 'اضغط على تم للحفظ';

  @override
  String get pressDoneToCreate => 'اضغط على تم للإنشاء';

  @override
  String get filterAll => 'الكل';

  @override
  String get filterSystem => 'عنك';

  @override
  String get filterInteresting => 'رؤى';

  @override
  String get filterManual => 'يدوي';

  @override
  String get completed => 'مكتمل';

  @override
  String get markComplete => 'تعيين كمكتمل';

  @override
  String get actionItemDeleted => 'تم حذف عنصر الإجراء';

  @override
  String get failedToDeleteActionItem => 'فشل حذف عنصر الإجراء';

  @override
  String get deleteActionItemConfirmTitle => 'حذف المهمة';

  @override
  String get deleteActionItemConfirmMessage => 'هل أنت متأكد من رغبتك في حذف هذه المهمة؟';

  @override
  String get appLanguage => 'لغة التطبيق';

  @override
  String get appInterfaceSectionTitle => 'واجهة التطبيق';

  @override
  String get speechTranscriptionSectionTitle => 'الكلام والنسخ';

  @override
  String get languageSettingsHelperText => 'لغة التطبيق تغير القوائم والأزرار. لغة الكلام تؤثر على كيفية نسخ تسجيلاتك.';

  @override
  String get translationNotice => 'إشعار الترجمة';

  @override
  String get translationNoticeMessage =>
      'يترجم Omi المحادثات إلى لغتك الأساسية. يمكنك تحديثها في أي وقت في الإعدادات → الملفات الشخصية.';

  @override
  String get pleaseCheckInternetConnection => 'يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى';

  @override
  String get pleaseSelectReason => 'يرجى اختيار سبب';

  @override
  String get tellUsMoreWhatWentWrong => 'أخبرنا المزيد عما حدث خطأ...';

  @override
  String get selectText => 'تحديد النص';

  @override
  String maximumGoalsAllowed(int count) {
    return 'الحد الأقصى $count أهداف مسموح به';
  }

  @override
  String get conversationCannotBeMerged => 'لا يمكن دمج هذه المحادثة (مقفلة أو قيد الدمج بالفعل)';

  @override
  String get pleaseEnterFolderName => 'يرجى إدخال اسم المجلد';

  @override
  String get failedToCreateFolder => 'فشل إنشاء المجلد';

  @override
  String get failedToUpdateFolder => 'فشل تحديث المجلد';

  @override
  String get folderName => 'اسم المجلد';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'فشل حذف المجلد';

  @override
  String get editFolder => 'تحرير المجلد';

  @override
  String get deleteFolder => 'حذف المجلد';

  @override
  String get transcriptCopiedToClipboard => 'تم نسخ النص إلى الحافظة';

  @override
  String get summaryCopiedToClipboard => 'تم نسخ الملخص إلى الحافظة';

  @override
  String get conversationUrlCouldNotBeShared => 'تعذرت مشاركة رابط المحادثة.';

  @override
  String get urlCopiedToClipboard => 'تم نسخ الرابط إلى الحافظة';

  @override
  String get exportTranscript => 'تصدير النص';

  @override
  String get exportSummary => 'تصدير الملخص';

  @override
  String get exportButton => 'تصدير';

  @override
  String get actionItemsCopiedToClipboard => 'تم نسخ عناصر الإجراء إلى الحافظة';

  @override
  String get summarize => 'تلخيص';

  @override
  String get generateSummary => 'إنشاء ملخص';

  @override
  String get conversationNotFoundOrDeleted => 'المحادثة غير موجودة أو تم حذفها';

  @override
  String get deleteMemory => 'حذف الذاكرة';

  @override
  String get thisActionCannotBeUndone => 'لا يمكن التراجع عن هذا الإجراء.';

  @override
  String memoriesCount(int count) {
    return '$count ذكريات';
  }

  @override
  String get noMemoriesInCategory => 'لا توجد ذكريات في هذه الفئة بعد';

  @override
  String get addYourFirstMemory => 'أضف أول ذاكرة';

  @override
  String get firmwareDisconnectUsb => 'افصل USB';

  @override
  String get firmwareUsbWarning => 'قد يؤدي توصيل USB أثناء التحديثات إلى إتلاف جهازك.';

  @override
  String get firmwareBatteryAbove15 => 'البطارية أعلى من 15%';

  @override
  String get firmwareEnsureBattery => 'تأكد من أن جهازك لديه 15% من البطارية.';

  @override
  String get firmwareStableConnection => 'اتصال مستقر';

  @override
  String get firmwareConnectWifi => 'اتصل بشبكة WiFi أو شبكة خلوية.';

  @override
  String failedToStartUpdate(String error) {
    return 'فشل بدء التحديث: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'قبل التحديث، تأكد من:';

  @override
  String get confirmed => 'تم التأكيد!';

  @override
  String get release => 'حرر';

  @override
  String get slideToUpdate => 'اسحب للتحديث';

  @override
  String copiedToClipboard(String title) {
    return 'تم نسخ $title إلى الحافظة';
  }

  @override
  String get batteryLevel => 'مستوى البطارية';

  @override
  String get productUpdate => 'تحديث المنتج';

  @override
  String get offline => 'غير متصل';

  @override
  String get available => 'متاح';

  @override
  String get unpairDeviceDialogTitle => 'إلغاء إقران الجهاز';

  @override
  String get unpairDeviceDialogMessage =>
      'سيؤدي هذا إلى إلغاء إقران الجهاز حتى يمكن توصيله بهاتف آخر. ستحتاج إلى الانتقال إلى الإعدادات > البلوتوث ونسيان الجهاز لإكمال العملية.';

  @override
  String get unpair => 'إلغاء الإقران';

  @override
  String get unpairAndForgetDevice => 'إلغاء الإقران ونسيان الجهاز';

  @override
  String get unknownDevice => 'غير معروف';

  @override
  String get unknown => 'غير معروف';

  @override
  String get productName => 'اسم المنتج';

  @override
  String get serialNumber => 'الرقم التسلسلي';

  @override
  String get connected => 'متصل';

  @override
  String get privacyPolicyTitle => 'سياسة الخصوصية';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return 'تم نسخ $label';
  }

  @override
  String get noApiKeysYet => 'لا توجد مفاتيح API بعد';

  @override
  String get createKeyToGetStarted => 'أنشئ مفتاحًا للبدء';

  @override
  String get persona => 'الشخصية';

  @override
  String get configureYourAiPersona => 'قم بتكوين شخصية الذكاء الاصطناعي الخاصة بك';

  @override
  String get configureSttProvider => 'تكوين مزود تحويل الكلام إلى نص';

  @override
  String get setWhenConversationsAutoEnd => 'حدد متى تنتهي المحادثات تلقائيًا';

  @override
  String get importDataFromOtherSources => 'استيراد البيانات من مصادر أخرى';

  @override
  String get debugAndDiagnostics => 'التصحيح والتشخيص';

  @override
  String get autoDeletesAfter3Days => 'يتم الحذف التلقائي بعد 3 أيام.';

  @override
  String get helpsDiagnoseIssues => 'يساعد في تشخيص المشكلات';

  @override
  String get exportStartedMessage => 'بدأ التصدير. قد يستغرق هذا بضع ثوانٍ...';

  @override
  String get exportConversationsToJson => 'تصدير المحادثات إلى ملف JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'تم حذف الرسم البياني المعرفي بنجاح';

  @override
  String failedToDeleteGraph(String error) {
    return 'فشل في حذف الرسم البياني: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'مسح جميع العقد والاتصالات';

  @override
  String get addToClaudeDesktopConfig => 'أضف إلى claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'اربط مساعدي الذكاء الاصطناعي ببياناتك';

  @override
  String get useYourMcpApiKey => 'استخدم مفتاح MCP API الخاص بك';

  @override
  String get realTimeTranscript => 'نسخ في الوقت الفعلي';

  @override
  String get experimental => 'تجريبي';

  @override
  String get transcriptionDiagnostics => 'تشخيصات النسخ';

  @override
  String get detailedDiagnosticMessages => 'رسائل تشخيصية مفصلة';

  @override
  String get autoCreateSpeakers => 'إنشاء المتحدثين تلقائيًا';

  @override
  String get autoCreateWhenNameDetected => 'إنشاء تلقائي عند اكتشاف الاسم';

  @override
  String get followUpQuestions => 'أسئلة المتابعة';

  @override
  String get suggestQuestionsAfterConversations => 'اقتراح الأسئلة بعد المحادثات';

  @override
  String get goalTracker => 'متتبع الأهداف';

  @override
  String get trackPersonalGoalsOnHomepage => 'تتبع أهدافك الشخصية على الصفحة الرئيسية';

  @override
  String get dailyReflection => 'التأمل اليومي';

  @override
  String get get9PmReminderToReflect => 'احصل على تذكير في الساعة 9 مساءً للتأمل في يومك';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'لا يمكن أن يكون وصف عنصر الإجراء فارغًا';

  @override
  String get saved => 'تم الحفظ';

  @override
  String get overdue => 'متأخر';

  @override
  String get failedToUpdateDueDate => 'فشل تحديث تاريخ الاستحقاق';

  @override
  String get markIncomplete => 'تعيين كغير مكتمل';

  @override
  String get editDueDate => 'تعديل تاريخ الاستحقاق';

  @override
  String get setDueDate => 'تعيين تاريخ الاستحقاق';

  @override
  String get clearDueDate => 'مسح تاريخ الاستحقاق';

  @override
  String get failedToClearDueDate => 'فشل مسح تاريخ الاستحقاق';

  @override
  String get mondayAbbr => 'الإثنين';

  @override
  String get tuesdayAbbr => 'الثلاثاء';

  @override
  String get wednesdayAbbr => 'الأربعاء';

  @override
  String get thursdayAbbr => 'الخميس';

  @override
  String get fridayAbbr => 'الجمعة';

  @override
  String get saturdayAbbr => 'السبت';

  @override
  String get sundayAbbr => 'الأحد';

  @override
  String get howDoesItWork => 'كيف يعمل؟';

  @override
  String get sdCardSyncDescription => 'ستقوم مزامنة بطاقة SD باستيراد ذكرياتك من بطاقة SD إلى التطبيق';

  @override
  String get checksForAudioFiles => 'يتحقق من ملفات الصوت على بطاقة SD';

  @override
  String get omiSyncsAudioFiles => 'يقوم Omi بعد ذلك بمزامنة ملفات الصوت مع الخادم';

  @override
  String get serverProcessesAudio => 'يقوم الخادم بمعالجة ملفات الصوت وإنشاء الذكريات';

  @override
  String get youreAllSet => 'أنت جاهز تمامًا!';

  @override
  String get welcomeToOmiDescription => 'مرحبًا بك في Omi! رفيقك الذكي جاهز لمساعدتك في المحادثات والمهام والمزيد.';

  @override
  String get startUsingOmi => 'ابدأ استخدام Omi';

  @override
  String get back => 'رجوع';

  @override
  String get keyboardShortcuts => 'اختصارات لوحة المفاتيح';

  @override
  String get toggleControlBar => 'تبديل شريط التحكم';

  @override
  String get pressKeys => 'اضغط المفاتيح...';

  @override
  String get cmdRequired => '⌘ مطلوب';

  @override
  String get invalidKey => 'مفتاح غير صالح';

  @override
  String get space => 'مسافة';

  @override
  String get search => 'بحث';

  @override
  String get searchPlaceholder => 'بحث...';

  @override
  String get untitledConversation => 'محادثة بدون عنوان';

  @override
  String countRemaining(String count) {
    return '$count متبقي';
  }

  @override
  String get addGoal => 'إضافة هدف';

  @override
  String get editGoal => 'تعديل الهدف';

  @override
  String get icon => 'أيقونة';

  @override
  String get goalTitle => 'عنوان الهدف';

  @override
  String get current => 'الحالي';

  @override
  String get target => 'الهدف';

  @override
  String get saveGoal => 'حفظ';

  @override
  String get goals => 'الأهداف';

  @override
  String get tapToAddGoal => 'اضغط لإضافة هدف';

  @override
  String welcomeBack(String name) {
    return 'مرحبًا بعودتك، $name';
  }

  @override
  String get yourConversations => 'محادثاتك';

  @override
  String get reviewAndManageConversations => 'راجع وأدر محادثاتك المسجلة';

  @override
  String get startCapturingConversations => 'ابدأ في التقاط المحادثات باستخدام جهاز Omi الخاص بك لرؤيتها هنا.';

  @override
  String get useMobileAppToCapture => 'استخدم تطبيق الهاتف المحمول لالتقاط الصوت';

  @override
  String get conversationsProcessedAutomatically => 'تتم معالجة المحادثات تلقائيًا';

  @override
  String get getInsightsInstantly => 'احصل على الرؤى والملخصات على الفور';

  @override
  String get showAll => 'عرض الكل ←';

  @override
  String get noTasksForToday => 'لا توجد مهام لليوم.\\nاسأل Omi عن المزيد من المهام أو أنشئها يدويًا.';

  @override
  String get dailyScore => 'النتيجة اليومية';

  @override
  String get dailyScoreDescription => 'نتيجة تساعدك على التركيز\nبشكل أفضل على التنفيذ.';

  @override
  String get searchResults => 'نتائج البحث';

  @override
  String get actionItems => 'عناصر العمل';

  @override
  String get tasksToday => 'اليوم';

  @override
  String get tasksTomorrow => 'غداً';

  @override
  String get tasksNoDeadline => 'بدون موعد نهائي';

  @override
  String get tasksLater => 'لاحقاً';

  @override
  String get loadingTasks => 'جاري تحميل المهام...';

  @override
  String get tasks => 'المهام';

  @override
  String get swipeTasksToIndent => 'اسحب المهام للمسافة البادئة، اسحب بين الفئات';

  @override
  String get create => 'إنشاء';

  @override
  String get noTasksYet => 'لا توجد مهام بعد';

  @override
  String get tasksFromConversationsWillAppear => 'ستظهر المهام من محادثاتك هنا.\nانقر على إنشاء لإضافة واحدة يدوياً.';

  @override
  String get monthJan => 'يناير';

  @override
  String get monthFeb => 'فبراير';

  @override
  String get monthMar => 'مارس';

  @override
  String get monthApr => 'أبريل';

  @override
  String get monthMay => 'مايو';

  @override
  String get monthJun => 'يونيو';

  @override
  String get monthJul => 'يوليو';

  @override
  String get monthAug => 'أغسطس';

  @override
  String get monthSep => 'سبتمبر';

  @override
  String get monthOct => 'أكتوبر';

  @override
  String get monthNov => 'نوفمبر';

  @override
  String get monthDec => 'ديسمبر';

  @override
  String get timePM => 'م';

  @override
  String get timeAM => 'ص';

  @override
  String get actionItemUpdatedSuccessfully => 'تم تحديث عنصر الإجراء بنجاح';

  @override
  String get actionItemCreatedSuccessfully => 'تم إنشاء عنصر الإجراء بنجاح';

  @override
  String get actionItemDeletedSuccessfully => 'تم حذف عنصر الإجراء بنجاح';

  @override
  String get deleteActionItem => 'حذف عنصر الإجراء';

  @override
  String get deleteActionItemConfirmation => 'هل أنت متأكد من حذف عنصر الإجراء هذا؟ لا يمكن التراجع عن هذا الإجراء.';

  @override
  String get enterActionItemDescription => 'أدخل وصف عنصر الإجراء...';

  @override
  String get markAsCompleted => 'تحديد كمكتمل';

  @override
  String get setDueDateAndTime => 'تعيين تاريخ ووقت الاستحقاق';

  @override
  String get reloadingApps => 'إعادة تحميل التطبيقات...';

  @override
  String get loadingApps => 'تحميل التطبيقات...';

  @override
  String get browseInstallCreateApps => 'تصفح وتثبيت وإنشاء التطبيقات';

  @override
  String get all => 'الكل';

  @override
  String get open => 'فتح';

  @override
  String get install => 'تثبيت';

  @override
  String get noAppsAvailable => 'لا توجد تطبيقات متاحة';

  @override
  String get unableToLoadApps => 'تعذر تحميل التطبيقات';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'حاول تعديل مصطلحات البحث أو الفلاتر';

  @override
  String get checkBackLaterForNewApps => 'تحقق لاحقاً من التطبيقات الجديدة';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى';

  @override
  String get createNewApp => 'إنشاء تطبيق جديد';

  @override
  String get buildSubmitCustomOmiApp => 'قم ببناء وإرسال تطبيق Omi المخصص الخاص بك';

  @override
  String get submittingYourApp => 'جارٍ إرسال تطبيقك...';

  @override
  String get preparingFormForYou => 'جارٍ تحضير النموذج لك...';

  @override
  String get appDetails => 'تفاصيل التطبيق';

  @override
  String get paymentDetails => 'تفاصيل الدفع';

  @override
  String get previewAndScreenshots => 'المعاينة ولقطات الشاشة';

  @override
  String get appCapabilities => 'قدرات التطبيق';

  @override
  String get aiPrompts => 'مطالبات الذكاء الاصطناعي';

  @override
  String get chatPrompt => 'مطالبة الدردشة';

  @override
  String get chatPromptPlaceholder => 'أنت تطبيق رائع، مهمتك هي الرد على استفسارات المستخدم وجعلهم يشعرون بالرضا...';

  @override
  String get conversationPrompt => 'مطالبة المحادثة';

  @override
  String get conversationPromptPlaceholder => 'أنت تطبيق رائع، سيتم إعطاؤك نص ملخص المحادثة...';

  @override
  String get notificationScopes => 'نطاقات الإشعارات';

  @override
  String get appPrivacyAndTerms => 'خصوصية التطبيق والشروط';

  @override
  String get makeMyAppPublic => 'اجعل تطبيقي عامًا';

  @override
  String get submitAppTermsAgreement => 'بإرسال هذا التطبيق، أوافق على شروط الخدمة وسياسة الخصوصية لـ Omi AI';

  @override
  String get submitApp => 'إرسال التطبيق';

  @override
  String get needHelpGettingStarted => 'هل تحتاج إلى مساعدة للبدء؟';

  @override
  String get clickHereForAppBuildingGuides => 'انقر هنا للحصول على أدلة بناء التطبيقات والتوثيق';

  @override
  String get submitAppQuestion => 'إرسال التطبيق؟';

  @override
  String get submitAppPublicDescription =>
      'سيتم مراجعة تطبيقك ونشره للعامة. يمكنك البدء في استخدامه فورًا، حتى أثناء المراجعة!';

  @override
  String get submitAppPrivateDescription =>
      'سيتم مراجعة تطبيقك وإتاحته لك بشكل خاص. يمكنك البدء في استخدامه فورًا، حتى أثناء المراجعة!';

  @override
  String get startEarning => 'ابدأ الكسب! 💰';

  @override
  String get connectStripeOrPayPal => 'اربط Stripe أو PayPal لاستلام المدفوعات لتطبيقك.';

  @override
  String get connectNow => 'الاتصال الآن';

  @override
  String get installsCount => 'التثبيتات';

  @override
  String get uninstallApp => 'إلغاء تثبيت التطبيق';

  @override
  String get subscribe => 'اشترك';

  @override
  String get dataAccessNotice => 'إشعار الوصول إلى البيانات';

  @override
  String get dataAccessWarning =>
      'سيصل هذا التطبيق إلى بياناتك. Omi AI غير مسؤول عن كيفية استخدام بياناتك أو تعديلها أو حذفها بواسطة هذا التطبيق';

  @override
  String get installApp => 'تثبيت التطبيق';

  @override
  String get betaTesterNotice =>
      'أنت مختبر تجريبي لهذا التطبيق. إنه غير عام حتى الآن. سيكون عامًا بمجرد الموافقة عليه.';

  @override
  String get appUnderReviewOwner => 'تطبيقك قيد المراجعة ومرئي لك فقط. سيكون عامًا بمجرد الموافقة عليه.';

  @override
  String get appRejectedNotice => 'تم رفض تطبيقك. يرجى تحديث تفاصيل التطبيق وإعادة تقديمه للمراجعة.';

  @override
  String get setupSteps => 'خطوات الإعداد';

  @override
  String get setupInstructions => 'تعليمات الإعداد';

  @override
  String get integrationInstructions => 'تعليمات التكامل';

  @override
  String get preview => 'معاينة';

  @override
  String get aboutTheApp => 'حول التطبيق';

  @override
  String get aboutThePersona => 'حول الشخصية';

  @override
  String get chatPersonality => 'شخصية المحادثة';

  @override
  String get ratingsAndReviews => 'التقييمات والمراجعات';

  @override
  String get noRatings => 'لا توجد تقييمات';

  @override
  String ratingsCount(String count) {
    return '$count+ تقييم';
  }

  @override
  String get errorActivatingApp => 'خطأ في تفعيل التطبيق';

  @override
  String get integrationSetupRequired => 'إذا كان هذا تطبيق تكامل، تأكد من اكتمال الإعداد.';

  @override
  String get installed => 'مثبت';

  @override
  String get appIdLabel => 'معرّف التطبيق';

  @override
  String get appNameLabel => 'اسم التطبيق';

  @override
  String get appNamePlaceholder => 'تطبيقي الرائع';

  @override
  String get pleaseEnterAppName => 'يرجى إدخال اسم التطبيق';

  @override
  String get categoryLabel => 'الفئة';

  @override
  String get selectCategory => 'اختر الفئة';

  @override
  String get descriptionLabel => 'الوصف';

  @override
  String get appDescriptionPlaceholder => 'تطبيقي الرائع هو تطبيق رائع يقوم بأشياء مذهلة. إنه أفضل تطبيق على الإطلاق!';

  @override
  String get pleaseProvideValidDescription => 'يرجى تقديم وصف صحيح';

  @override
  String get appPricingLabel => 'سعر التطبيق';

  @override
  String get noneSelected => 'لم يتم الاختيار';

  @override
  String get appIdCopiedToClipboard => 'تم نسخ معرّف التطبيق إلى الحافظة';

  @override
  String get appCategoryModalTitle => 'فئة التطبيق';

  @override
  String get pricingFree => 'مجاني';

  @override
  String get pricingPaid => 'مدفوع';

  @override
  String get loadingCapabilities => 'جارٍ تحميل الإمكانيات...';

  @override
  String get filterInstalled => 'مثبتة';

  @override
  String get filterMyApps => 'تطبيقاتي';

  @override
  String get clearSelection => 'مسح الاختيار';

  @override
  String get filterCategory => 'الفئة';

  @override
  String get rating4PlusStars => '4+ نجوم';

  @override
  String get rating3PlusStars => '3+ نجوم';

  @override
  String get rating2PlusStars => '2+ نجوم';

  @override
  String get rating1PlusStars => '1+ نجوم';

  @override
  String get filterRating => 'التقييم';

  @override
  String get filterCapabilities => 'الإمكانيات';

  @override
  String get noNotificationScopesAvailable => 'لا توجد نطاقات إشعارات متاحة';

  @override
  String get popularApps => 'التطبيقات الشائعة';

  @override
  String get pleaseProvidePrompt => 'يرجى تقديم موجه';

  @override
  String chatWithAppName(String appName) {
    return 'الدردشة مع $appName';
  }

  @override
  String get defaultAiAssistant => 'مساعد الذكاء الاصطناعي الافتراضي';

  @override
  String get readyToChat => '✨ جاهز للدردشة!';

  @override
  String get connectionNeeded => '🌐 يتطلب الاتصال';

  @override
  String get startConversation => 'ابدأ محادثة ودع السحر يبدأ';

  @override
  String get checkInternetConnection => 'يرجى التحقق من اتصالك بالإنترنت';

  @override
  String get wasThisHelpful => 'هل كان هذا مفيدًا؟';

  @override
  String get thankYouForFeedback => 'شكرًا لك على ملاحظاتك!';

  @override
  String get maxFilesUploadError => 'يمكنك تحميل 4 ملفات فقط في المرة الواحدة';

  @override
  String get attachedFiles => '📎 الملفات المرفقة';

  @override
  String get takePhoto => 'التقاط صورة';

  @override
  String get captureWithCamera => 'التقط بالكاميرا';

  @override
  String get selectImages => 'اختر الصور';

  @override
  String get chooseFromGallery => 'اختر من المعرض';

  @override
  String get selectFile => 'اختر ملف';

  @override
  String get chooseAnyFileType => 'اختر أي نوع ملف';

  @override
  String get cannotReportOwnMessages => 'لا يمكنك الإبلاغ عن رسائلك الخاصة';

  @override
  String get messageReportedSuccessfully => '✅ تم الإبلاغ عن الرسالة بنجاح';

  @override
  String get confirmReportMessage => 'هل أنت متأكد من أنك تريد الإبلاغ عن هذه الرسالة؟';

  @override
  String get selectChatAssistant => 'اختر مساعد الدردشة';

  @override
  String get enableMoreApps => 'تمكين المزيد من التطبيقات';

  @override
  String get chatCleared => 'تم مسح الدردشة';

  @override
  String get clearChatTitle => 'مسح الدردشة؟';

  @override
  String get confirmClearChat => 'هل أنت متأكد من أنك تريد مسح الدردشة؟ هذا الإجراء لا يمكن التراجع عنه.';

  @override
  String get copy => 'نسخ';

  @override
  String get share => 'مشاركة';

  @override
  String get report => 'إبلاغ';

  @override
  String get microphonePermissionRequired => 'مطلوب إذن الميكروفون للتسجيل الصوتي.';

  @override
  String get microphonePermissionDenied =>
      'تم رفض إذن الميكروفون. يرجى منح الإذن في تفضيلات النظام > الخصوصية والأمان > الميكروفون.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'فشل التحقق من إذن الميكروفون: $error';
  }

  @override
  String get failedToTranscribeAudio => 'فشل تحويل الصوت إلى نص';

  @override
  String get transcribing => 'جاري التحويل...';

  @override
  String get transcriptionFailed => 'فشل التحويل';

  @override
  String get discardedConversation => 'محادثة محذوفة';

  @override
  String get at => 'في';

  @override
  String get from => 'من';

  @override
  String get copied => 'تم النسخ!';

  @override
  String get copyLink => 'نسخ الرابط';

  @override
  String get hideTranscript => 'إخفاء النسخ';

  @override
  String get viewTranscript => 'عرض النسخ';

  @override
  String get conversationDetails => 'تفاصيل المحادثة';

  @override
  String get transcript => 'النسخ';

  @override
  String segmentsCount(int count) {
    return '$count مقاطع';
  }

  @override
  String get noTranscriptAvailable => 'لا يوجد نسخ متاح';

  @override
  String get noTranscriptMessage => 'هذه المحادثة ليس لديها نسخ.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'تعذر إنشاء رابط المحادثة.';

  @override
  String get failedToGenerateConversationLink => 'فشل إنشاء رابط المحادثة';

  @override
  String get failedToGenerateShareLink => 'فشل إنشاء رابط المشاركة';

  @override
  String get reloadingConversations => 'إعادة تحميل المحادثات...';

  @override
  String get user => 'مستخدم';

  @override
  String get starred => 'مميز بنجمة';

  @override
  String get date => 'التاريخ';

  @override
  String get noResultsFound => 'لم يتم العثور على نتائج';

  @override
  String get tryAdjustingSearchTerms => 'حاول تعديل مصطلحات البحث';

  @override
  String get starConversationsToFindQuickly => 'ضع نجمة على المحادثات للعثور عليها بسرعة هنا';

  @override
  String noConversationsOnDate(String date) {
    return 'لا توجد محادثات في $date';
  }

  @override
  String get trySelectingDifferentDate => 'حاول اختيار تاريخ مختلف';

  @override
  String get conversations => 'المحادثات';

  @override
  String get chat => 'الدردشة';

  @override
  String get actions => 'الإجراءات';

  @override
  String get syncAvailable => 'المزامنة متاحة';

  @override
  String get referAFriend => 'أوصِ بصديق';

  @override
  String get help => 'المساعدة';

  @override
  String get pro => 'احترافي';

  @override
  String get upgradeToPro => 'الترقية إلى Pro';

  @override
  String get getOmiDevice => 'احصل على جهاز Omi';

  @override
  String get wearableAiCompanion => 'رفيق ذكاء اصطناعي يمكن ارتداؤه';

  @override
  String get loadingMemories => 'تحميل الذكريات...';

  @override
  String get allMemories => 'جميع الذكريات';

  @override
  String get aboutYou => 'عنك';

  @override
  String get manual => 'يدوي';

  @override
  String get loadingYourMemories => 'تحميل ذكرياتك...';

  @override
  String get createYourFirstMemory => 'إنشاء أول ذاكرة للبدء';

  @override
  String get tryAdjustingFilter => 'حاول ضبط البحث أو المرشح';

  @override
  String get whatWouldYouLikeToRemember => 'ما الذي تريد تذكره؟';

  @override
  String get category => 'الفئة';

  @override
  String get public => 'عام';

  @override
  String get failedToSaveCheckConnection => 'فشل الحفظ. يرجى التحقق من الاتصال.';

  @override
  String get createMemory => 'إنشاء ذاكرة';

  @override
  String get deleteMemoryConfirmation => 'هل أنت متأكد من حذف هذه الذاكرة؟ لا يمكن التراجع عن هذا الإجراء.';

  @override
  String get makePrivate => 'جعلها خاصة';

  @override
  String get organizeAndControlMemories => 'تنظيم والتحكم في ذكرياتك';

  @override
  String get total => 'الإجمالي';

  @override
  String get makeAllMemoriesPrivate => 'جعل كل الذكريات خاصة';

  @override
  String get setAllMemoriesToPrivate => 'تعيين جميع الذكريات إلى خاصة';

  @override
  String get makeAllMemoriesPublic => 'جعل كل الذكريات عامة';

  @override
  String get setAllMemoriesToPublic => 'تعيين جميع الذكريات إلى عامة';

  @override
  String get permanentlyRemoveAllMemories => 'إزالة جميع الذكريات من Omi نهائياً';

  @override
  String get allMemoriesAreNowPrivate => 'كل الذكريات الآن خاصة';

  @override
  String get allMemoriesAreNowPublic => 'كل الذكريات الآن عامة';

  @override
  String get clearOmisMemory => 'مسح ذاكرة Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'هل أنت متأكد من مسح ذاكرة Omi؟ لا يمكن التراجع عن هذا الإجراء وسيتم حذف جميع الذكريات الـ $count نهائياً.';
  }

  @override
  String get omisMemoryCleared => 'تم مسح ذاكرة Omi عنك';

  @override
  String get welcomeToOmi => 'مرحباً بك في Omi';

  @override
  String get continueWithApple => 'متابعة مع Apple';

  @override
  String get continueWithGoogle => 'متابعة مع Google';

  @override
  String get byContinuingYouAgree => 'بالمتابعة، فإنك توافق على ';

  @override
  String get termsOfService => 'شروط الخدمة';

  @override
  String get and => ' و';

  @override
  String get dataAndPrivacy => 'البيانات والخصوصية';

  @override
  String get secureAuthViaAppleId => 'المصادقة الآمنة عبر Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'المصادقة الآمنة عبر حساب Google';

  @override
  String get whatWeCollect => 'ما نجمعه';

  @override
  String get dataCollectionMessage =>
      'بالمتابعة، سيتم تخزين محادثاتك وتسجيلاتك ومعلوماتك الشخصية بشكل آمن على خوادمنا لتوفير رؤى مدعومة بالذكاء الاصطناعي وتمكين جميع ميزات التطبيق.';

  @override
  String get dataProtection => 'حماية البيانات';

  @override
  String get yourDataIsProtected => 'بياناتك محمية وتخضع لـ ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'يرجى تحديد لغتك الأساسية';

  @override
  String get chooseYourLanguage => 'اختر لغتك';

  @override
  String get selectPreferredLanguageForBestExperience => 'اختر لغتك المفضلة للحصول على أفضل تجربة Omi';

  @override
  String get searchLanguages => 'بحث عن اللغات...';

  @override
  String get selectALanguage => 'اختر لغة';

  @override
  String get tryDifferentSearchTerm => 'جرب مصطلح بحث مختلف';

  @override
  String get pleaseEnterYourName => 'يرجى إدخال اسمك';

  @override
  String get nameMustBeAtLeast2Characters => 'يجب أن يكون الاسم على الأقل حرفين';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed => 'أخبرنا كيف تريد أن نخاطبك. هذا يساعد في تخصيص تجربة Omi الخاصة بك.';

  @override
  String charactersCount(int count) {
    return '$count حرف';
  }

  @override
  String get enableFeaturesForBestExperience => 'تمكين الميزات للحصول على أفضل تجربة Omi على جهازك.';

  @override
  String get microphoneAccess => 'الوصول إلى الميكروفون';

  @override
  String get recordAudioConversations => 'تسجيل المحادثات الصوتية';

  @override
  String get microphoneAccessDescription =>
      'يحتاج Omi إلى الوصول إلى الميكروفون لتسجيل محادثاتك وتوفير النصوص المكتوبة.';

  @override
  String get screenRecording => 'تسجيل الشاشة';

  @override
  String get captureSystemAudioFromMeetings => 'التقاط صوت النظام من الاجتماعات';

  @override
  String get screenRecordingDescription =>
      'يحتاج Omi إلى إذن تسجيل الشاشة للتقاط صوت النظام من اجتماعات المتصفح الخاصة بك.';

  @override
  String get accessibility => 'إمكانية الوصول';

  @override
  String get detectBrowserBasedMeetings => 'اكتشاف الاجتماعات عبر المتصفح';

  @override
  String get accessibilityDescription =>
      'يحتاج Omi إلى إذن إمكانية الوصول لاكتشاف متى تنضم إلى اجتماعات Zoom أو Meet أو Teams في متصفحك.';

  @override
  String get pleaseWait => 'يرجى الانتظار...';

  @override
  String get joinTheCommunity => 'انضم إلى المجتمع!';

  @override
  String get loadingProfile => 'جارٍ تحميل الملف الشخصي...';

  @override
  String get profileSettings => 'إعدادات الملف الشخصي';

  @override
  String get noEmailSet => 'لم يتم تعيين بريد إلكتروني';

  @override
  String get userIdCopiedToClipboard => 'تم نسخ معرف المستخدم';

  @override
  String get yourInformation => 'معلوماتك';

  @override
  String get setYourName => 'عيّن اسمك';

  @override
  String get changeYourName => 'غيّر اسمك';

  @override
  String get manageYourOmiPersona => 'إدارة شخصيتك في Omi';

  @override
  String get voiceAndPeople => 'الصوت والأشخاص';

  @override
  String get teachOmiYourVoice => 'علّم Omi صوتك';

  @override
  String get tellOmiWhoSaidIt => 'أخبر Omi من قال ذلك 🗣️';

  @override
  String get payment => 'الدفع';

  @override
  String get addOrChangeYourPaymentMethod => 'إضافة أو تغيير طريقة الدفع';

  @override
  String get preferences => 'التفضيلات';

  @override
  String get helpImproveOmiBySharing => 'ساعد في تحسين Omi من خلال مشاركة بيانات التحليلات المجهولة';

  @override
  String get deleteAccount => 'حذف الحساب';

  @override
  String get deleteYourAccountAndAllData => 'حذف حسابك وجميع البيانات';

  @override
  String get clearLogs => 'مسح السجلات';

  @override
  String get debugLogsCleared => 'تم مسح سجلات التصحيح';

  @override
  String get exportConversations => 'تصدير المحادثات';

  @override
  String get exportAllConversationsToJson => 'تصدير جميع محادثاتك إلى ملف JSON.';

  @override
  String get conversationsExportStarted => 'بدأ تصدير المحادثات. قد يستغرق هذا بضع ثوانٍ، يرجى الانتظار.';

  @override
  String get mcpDescription =>
      'للاتصال بـ Omi مع التطبيقات الأخرى لقراءة وبحث وإدارة ذكرياتك ومحادثاتك. قم بإنشاء مفتاح للبدء.';

  @override
  String get apiKeys => 'مفاتيح API';

  @override
  String errorLabel(String error) {
    return 'خطأ: $error';
  }

  @override
  String get noApiKeysFound => 'لم يتم العثور على مفاتيح API. قم بإنشاء واحد للبدء.';

  @override
  String get advancedSettings => 'الإعدادات المتقدمة';

  @override
  String get triggersWhenNewConversationCreated => 'يتم تشغيله عند إنشاء محادثة جديدة.';

  @override
  String get triggersWhenNewTranscriptReceived => 'يتم تشغيله عند استلام نص جديد.';

  @override
  String get realtimeAudioBytes => 'بايتات الصوت الفورية';

  @override
  String get triggersWhenAudioBytesReceived => 'يتم تشغيله عند استلام بايتات الصوت.';

  @override
  String get everyXSeconds => 'كل x ثانية';

  @override
  String get triggersWhenDaySummaryGenerated => 'يتم تشغيله عند إنشاء ملخص اليوم.';

  @override
  String get tryLatestExperimentalFeatures => 'جرب أحدث الميزات التجريبية من فريق Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'حالة تشخيص خدمة النسخ';

  @override
  String get enableDetailedDiagnosticMessages => 'تمكين رسائل التشخيص التفصيلية من خدمة النسخ';

  @override
  String get autoCreateAndTagNewSpeakers => 'إنشاء ووسم المتحدثين الجدد تلقائيًا';

  @override
  String get automaticallyCreateNewPerson => 'إنشاء شخص جديد تلقائيًا عند اكتشاف اسم في النص.';

  @override
  String get pilotFeatures => 'الميزات التجريبية';

  @override
  String get pilotFeaturesDescription => 'هذه الميزات اختبارية ولا يُضمن دعمها.';

  @override
  String get suggestFollowUpQuestion => 'اقتراح سؤال للمتابعة';

  @override
  String get saveSettings => 'حفظ الإعدادات';

  @override
  String get syncingDeveloperSettings => 'مزامنة إعدادات المطور...';

  @override
  String get summary => 'ملخص';

  @override
  String get auto => 'تلقائي';

  @override
  String get noSummaryForApp => 'لا يوجد ملخص لهذا التطبيق. جرب تطبيقاً آخر للحصول على نتائج أفضل.';

  @override
  String get tryAnotherApp => 'جرب تطبيقًا آخر';

  @override
  String generatedBy(String appName) {
    return 'تم إنشاؤه بواسطة $appName';
  }

  @override
  String get overview => 'نظرة عامة';

  @override
  String get otherAppResults => 'نتائج التطبيقات الأخرى';

  @override
  String get unknownApp => 'تطبيق غير معروف';

  @override
  String get noSummaryAvailable => 'لا يوجد ملخص متاح';

  @override
  String get conversationNoSummaryYet => 'لا يحتوي هذا الحوار على ملخص بعد.';

  @override
  String get chooseSummarizationApp => 'اختر تطبيق الملخص';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return 'تم تعيين $appName كتطبيق ملخص افتراضي';
  }

  @override
  String get letOmiChooseAutomatically => 'دع Omi يختار أفضل تطبيق تلقائيًا';

  @override
  String get deleteConversationConfirmation => 'هل أنت متأكد من حذف هذه المحادثة؟ لا يمكن التراجع عن هذا الإجراء.';

  @override
  String get conversationDeleted => 'تم حذف المحادثة';

  @override
  String get generatingLink => 'جارٍ إنشاء الرابط...';

  @override
  String get editConversation => 'تحرير المحادثة';

  @override
  String get conversationLinkCopiedToClipboard => 'تم نسخ رابط المحادثة إلى الحافظة';

  @override
  String get conversationTranscriptCopiedToClipboard => 'تم نسخ نص المحادثة إلى الحافظة';

  @override
  String get editConversationDialogTitle => 'تحرير المحادثة';

  @override
  String get changeTheConversationTitle => 'تغيير عنوان المحادثة';

  @override
  String get conversationTitle => 'عنوان المحادثة';

  @override
  String get enterConversationTitle => 'أدخل عنوان المحادثة...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'تم تحديث عنوان المحادثة بنجاح';

  @override
  String get failedToUpdateConversationTitle => 'فشل تحديث عنوان المحادثة';

  @override
  String get errorUpdatingConversationTitle => 'خطأ في تحديث عنوان المحادثة';

  @override
  String get settingUp => 'جارٍ الإعداد...';

  @override
  String get startYourFirstRecording => 'ابدأ تسجيلك الأول';

  @override
  String get preparingSystemAudioCapture => 'جارٍ تحضير التقاط الصوت النظام';

  @override
  String get clickTheButtonToCaptureAudio =>
      'انقر على الزر لالتقاط الصوت للحصول على نصوص مباشرة ورؤى الذكاء الاصطناعي والحفظ التلقائي.';

  @override
  String get reconnecting => 'جارٍ إعادة الاتصال...';

  @override
  String get recordingPaused => 'التسجيل متوقف مؤقتاً';

  @override
  String get recordingActive => 'التسجيل نشط';

  @override
  String get startRecording => 'بدء التسجيل';

  @override
  String resumingInCountdown(String countdown) {
    return 'سيتم الاستئناف خلال $countdown ثانية...';
  }

  @override
  String get tapPlayToResume => 'انقر على تشغيل للاستئناف';

  @override
  String get listeningForAudio => 'الاستماع للصوت...';

  @override
  String get preparingAudioCapture => 'جارٍ تحضير التقاط الصوت';

  @override
  String get clickToBeginRecording => 'انقر لبدء التسجيل';

  @override
  String get translated => 'مترجم';

  @override
  String get liveTranscript => 'النص المباشر';

  @override
  String segmentsSingular(String count) {
    return '$count مقطع';
  }

  @override
  String segmentsPlural(String count) {
    return '$count مقاطع';
  }

  @override
  String get startRecordingToSeeTranscript => 'ابدأ التسجيل لرؤية النص المباشر';

  @override
  String get paused => 'متوقف مؤقتاً';

  @override
  String get initializing => 'جارٍ التهيئة...';

  @override
  String get recording => 'جارٍ التسجيل';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'تم تغيير الميكروفون. سيتم الاستئناف خلال $countdown ثانية';
  }

  @override
  String get clickPlayToResumeOrStop => 'انقر على تشغيل للاستئناف أو إيقاف للإنهاء';

  @override
  String get settingUpSystemAudioCapture => 'جارٍ إعداد التقاط صوت النظام';

  @override
  String get capturingAudioAndGeneratingTranscript => 'التقاط الصوت وإنشاء النص';

  @override
  String get clickToBeginRecordingSystemAudio => 'انقر لبدء تسجيل صوت النظام';

  @override
  String get you => 'أنت';

  @override
  String speakerWithId(String speakerId) {
    return 'المتحدث $speakerId';
  }

  @override
  String get translatedByOmi => 'مترجم بواسطة omi';

  @override
  String get backToConversations => 'العودة إلى المحادثات';

  @override
  String get systemAudio => 'النظام';

  @override
  String get mic => 'ميكروفون';

  @override
  String audioInputSetTo(String deviceName) {
    return 'تم تعيين إدخال الصوت إلى $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'خطأ في تبديل جهاز الصوت: $error';
  }

  @override
  String get selectAudioInput => 'اختر إدخال الصوت';

  @override
  String get loadingDevices => 'جارٍ تحميل الأجهزة...';

  @override
  String get settingsHeader => 'الإعدادات';

  @override
  String get plansAndBilling => 'الخطط والفواتير';

  @override
  String get calendarIntegration => 'تكامل التقويم';

  @override
  String get dailySummary => 'الملخص اليومي';

  @override
  String get developer => 'المطور';

  @override
  String get about => 'حول';

  @override
  String get selectTime => 'اختر الوقت';

  @override
  String get accountGroup => 'الحساب';

  @override
  String get signOutQuestion => 'تسجيل الخروج؟';

  @override
  String get signOutConfirmation => 'هل أنت متأكد من رغبتك في تسجيل الخروج؟';

  @override
  String get customVocabularyHeader => 'المفردات المخصصة';

  @override
  String get addWordsDescription => 'أضف كلمات يجب أن يتعرف عليها Omi أثناء النسخ.';

  @override
  String get enterWordsHint => 'أدخل الكلمات (مفصولة بفواصل)';

  @override
  String get dailySummaryHeader => 'الملخص اليومي';

  @override
  String get dailySummaryTitle => 'الملخص اليومي';

  @override
  String get dailySummaryDescription => 'احصل على ملخص مخصص لمحادثات يومك يُرسل كإشعار.';

  @override
  String get deliveryTime => 'وقت التسليم';

  @override
  String get deliveryTimeDescription => 'متى تتلقى ملخصك اليومي';

  @override
  String get subscription => 'الاشتراك';

  @override
  String get viewPlansAndUsage => 'عرض الخطط والاستخدام';

  @override
  String get viewPlansDescription => 'إدارة اشتراكك ومشاهدة إحصائيات الاستخدام';

  @override
  String get addOrChangePaymentMethod => 'إضافة أو تغيير طريقة الدفع';

  @override
  String get displayOptions => 'خيارات العرض';

  @override
  String get showMeetingsInMenuBar => 'إظهار الاجتماعات في شريط القوائم';

  @override
  String get displayUpcomingMeetingsDescription => 'عرض الاجتماعات القادمة في شريط القوائم';

  @override
  String get showEventsWithoutParticipants => 'إظهار الأحداث بدون مشاركين';

  @override
  String get includePersonalEventsDescription => 'تضمين الأحداث الشخصية بدون حضور';

  @override
  String get upcomingMeetings => 'الاجتماعات القادمة';

  @override
  String get checkingNext7Days => 'التحقق من الأيام السبعة القادمة';

  @override
  String get shortcuts => 'اختصارات';

  @override
  String get shortcutChangeInstruction => 'انقر فوق اختصار لتغييره. اضغط Escape للإلغاء.';

  @override
  String get configurePersonaDescription => 'قم بتكوين شخصية الذكاء الاصطناعي الخاصة بك';

  @override
  String get configureSTTProvider => 'تكوين مزود STT';

  @override
  String get setConversationEndDescription => 'حدد متى تنتهي المحادثات تلقائيًا';

  @override
  String get importDataDescription => 'استيراد البيانات من مصادر أخرى';

  @override
  String get exportConversationsDescription => 'تصدير المحادثات إلى JSON';

  @override
  String get exportingConversations => 'جاري تصدير المحادثات...';

  @override
  String get clearNodesDescription => 'مسح جميع العقد والاتصالات';

  @override
  String get deleteKnowledgeGraphQuestion => 'حذف رسم المعرفة؟';

  @override
  String get deleteKnowledgeGraphWarning =>
      'سيؤدي هذا إلى حذف جميع بيانات رسم المعرفة المشتقة. تظل ذكرياتك الأصلية آمنة.';

  @override
  String get connectOmiWithAI => 'ربط Omi بمساعدي الذكاء الاصطناعي';

  @override
  String get noAPIKeys => 'لا توجد مفاتيح API. قم بإنشاء واحد للبدء.';

  @override
  String get autoCreateWhenDetected => 'الإنشاء التلقائي عند اكتشاف الاسم';

  @override
  String get trackPersonalGoals => 'تتبع الأهداف الشخصية على الصفحة الرئيسية';

  @override
  String get dailyReflectionDescription => 'احصل على تذكير في الساعة 9 مساءً للتأمل في يومك وتدوين أفكارك.';

  @override
  String get endpointURL => 'عنوان URL لنقطة النهاية';

  @override
  String get links => 'الروابط';

  @override
  String get discordMemberCount => 'أكثر من 8000 عضو على Discord';

  @override
  String get userInformation => 'معلومات المستخدم';

  @override
  String get capabilities => 'القدرات';

  @override
  String get previewScreenshots => 'معاينة لقطات الشاشة';

  @override
  String get holdOnPreparingForm => 'انتظر قليلاً، نحن نجهز النموذج لك';

  @override
  String get bySubmittingYouAgreeToOmi => 'بالإرسال، أنت توافق على Omi ';

  @override
  String get termsAndPrivacyPolicy => 'الشروط وسياسة الخصوصية';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'يساعد في تشخيص المشاكل. يحذف تلقائيًا بعد 3 أيام.';

  @override
  String get manageYourApp => 'إدارة تطبيقك';

  @override
  String get updatingYourApp => 'جارٍ تحديث تطبيقك';

  @override
  String get fetchingYourAppDetails => 'جارٍ جلب تفاصيل تطبيقك';

  @override
  String get updateAppQuestion => 'تحديث التطبيق؟';

  @override
  String get updateAppConfirmation =>
      'هل أنت متأكد من رغبتك في تحديث تطبيقك؟ ستظهر التغييرات بعد مراجعتها من قبل فريقنا.';

  @override
  String get updateApp => 'تحديث التطبيق';

  @override
  String get createAndSubmitNewApp => 'إنشاء وإرسال تطبيق جديد';

  @override
  String appsCount(String count) {
    return 'التطبيقات ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'التطبيقات الخاصة ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'التطبيقات العامة ($count)';
  }

  @override
  String get newVersionAvailable => 'إصدار جديد متاح  🎉';

  @override
  String get no => 'لا';

  @override
  String get subscriptionCancelledSuccessfully => 'تم إلغاء الاشتراك بنجاح. سيظل نشطًا حتى نهاية فترة الفوترة الحالية.';

  @override
  String get failedToCancelSubscription => 'فشل إلغاء الاشتراك. يرجى المحاولة مرة أخرى.';

  @override
  String get invalidPaymentUrl => 'رابط الدفع غير صالح';

  @override
  String get permissionsAndTriggers => 'الأذونات والمحفزات';

  @override
  String get chatFeatures => 'ميزات الدردشة';

  @override
  String get uninstall => 'إلغاء التثبيت';

  @override
  String get installs => 'التثبيتات';

  @override
  String get priceLabel => 'السعر';

  @override
  String get updatedLabel => 'محدث';

  @override
  String get createdLabel => 'تم الإنشاء';

  @override
  String get featuredLabel => 'مميز';

  @override
  String get cancelSubscriptionQuestion => 'إلغاء الاشتراك؟';

  @override
  String get cancelSubscriptionConfirmation =>
      'هل أنت متأكد من رغبتك في إلغاء اشتراكك؟ سيستمر وصولك حتى نهاية فترة الفوترة الحالية.';

  @override
  String get cancelSubscriptionButton => 'إلغاء الاشتراك';

  @override
  String get cancelling => 'جارٍ الإلغاء...';

  @override
  String get betaTesterMessage => 'أنت مختبر تجريبي لهذا التطبيق. إنه ليس عامًا بعد. سيصبح عامًا بعد الموافقة.';

  @override
  String get appUnderReviewMessage => 'تطبيقك قيد المراجعة ومرئي لك فقط. سيصبح عامًا بعد الموافقة.';

  @override
  String get appRejectedMessage => 'تم رفض تطبيقك. يرجى تحديث تفاصيل التطبيق وإعادة الإرسال للمراجعة.';

  @override
  String get invalidIntegrationUrl => 'رابط التكامل غير صالح';

  @override
  String get tapToComplete => 'انقر للإكمال';

  @override
  String get invalidSetupInstructionsUrl => 'رابط تعليمات الإعداد غير صالح';

  @override
  String get pushToTalk => 'اضغط للتحدث';

  @override
  String get summaryPrompt => 'موجه الملخص';

  @override
  String get pleaseSelectARating => 'يرجى اختيار تقييم';

  @override
  String get reviewAddedSuccessfully => 'تمت إضافة المراجعة بنجاح 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'تم تحديث المراجعة بنجاح 🚀';

  @override
  String get failedToSubmitReview => 'فشل إرسال المراجعة. يرجى المحاولة مرة أخرى.';

  @override
  String get addYourReview => 'أضف مراجعتك';

  @override
  String get editYourReview => 'تعديل مراجعتك';

  @override
  String get writeAReviewOptional => 'اكتب مراجعة (اختياري)';

  @override
  String get submitReview => 'إرسال المراجعة';

  @override
  String get updateReview => 'تحديث المراجعة';

  @override
  String get yourReview => 'مراجعتك';

  @override
  String get anonymousUser => 'مستخدم مجهول';

  @override
  String get issueActivatingApp => 'حدثت مشكلة في تفعيل هذا التطبيق. يرجى المحاولة مرة أخرى.';

  @override
  String get dataAccessNoticeDescription =>
      'سيصل هذا التطبيق إلى بياناتك. Omi AI ليس مسؤولاً عن كيفية استخدام بياناتك أو تعديلها أو حذفها بواسطة هذا التطبيق';

  @override
  String get copyUrl => 'نسخ الرابط';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'الإثنين';

  @override
  String get weekdayTue => 'الثلاثاء';

  @override
  String get weekdayWed => 'الأربعاء';

  @override
  String get weekdayThu => 'الخميس';

  @override
  String get weekdayFri => 'الجمعة';

  @override
  String get weekdaySat => 'السبت';

  @override
  String get weekdaySun => 'الأحد';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'تكامل $serviceName قريباً';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'تم التصدير بالفعل إلى $platform';
  }

  @override
  String get anotherPlatform => 'منصة أخرى';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'يرجى المصادقة مع $serviceName في الإعدادات > تكاملات المهام';
  }

  @override
  String addingToService(String serviceName) {
    return 'جارٍ الإضافة إلى $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'تمت الإضافة إلى $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'فشل الإضافة إلى $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'تم رفض الإذن لتذكيرات Apple';

  @override
  String failedToCreateApiKey(String error) {
    return 'فشل إنشاء مفتاح API للمزود: $error';
  }

  @override
  String get createAKey => 'إنشاء مفتاح';

  @override
  String get apiKeyRevokedSuccessfully => 'تم إلغاء مفتاح API بنجاح';

  @override
  String failedToRevokeApiKey(String error) {
    return 'فشل إلغاء مفتاح API: $error';
  }

  @override
  String get omiApiKeys => 'مفاتيح Omi API';

  @override
  String get apiKeysDescription =>
      'تُستخدم مفاتيح API للمصادقة عندما يتواصل تطبيقك مع خادم OMI. تسمح لتطبيقك بإنشاء ذكريات والوصول إلى خدمات OMI الأخرى بأمان.';

  @override
  String get aboutOmiApiKeys => 'حول مفاتيح Omi API';

  @override
  String get yourNewKey => 'مفتاحك الجديد:';

  @override
  String get copyToClipboard => 'نسخ إلى الحافظة';

  @override
  String get pleaseCopyKeyNow => 'يرجى نسخه الآن وكتابته في مكان آمن. ';

  @override
  String get willNotSeeAgain => 'لن تتمكن من رؤيته مرة أخرى.';

  @override
  String get revokeKey => 'إلغاء المفتاح';

  @override
  String get revokeApiKeyQuestion => 'إلغاء مفتاح API؟';

  @override
  String get revokeApiKeyWarning =>
      'لا يمكن التراجع عن هذا الإجراء. لن تتمكن أي تطبيقات تستخدم هذا المفتاح من الوصول إلى API بعد الآن.';

  @override
  String get revoke => 'إلغاء';

  @override
  String get whatWouldYouLikeToCreate => 'ماذا تريد أن تنشئ؟';

  @override
  String get createAnApp => 'إنشاء تطبيق';

  @override
  String get createAndShareYourApp => 'أنشئ وشارك تطبيقك';

  @override
  String get createMyClone => 'إنشاء نسختي';

  @override
  String get createYourDigitalClone => 'أنشئ نسختك الرقمية';

  @override
  String get itemApp => 'التطبيق';

  @override
  String get itemPersona => 'الشخصية';

  @override
  String keepItemPublic(String item) {
    return 'إبقاء $item عامًا';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'جعل $item عامًا؟';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'جعل $item خاصًا؟';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'إذا جعلت $item عامًا، يمكن للجميع استخدامه';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'إذا جعلت $item خاصًا الآن، سيتوقف عن العمل للجميع وسيكون مرئيًا لك فقط';
  }

  @override
  String get manageApp => 'إدارة التطبيق';

  @override
  String get updatePersonaDetails => 'تحديث تفاصيل الشخصية';

  @override
  String deleteItemTitle(String item) {
    return 'حذف $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'حذف $item؟';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'هل أنت متأكد أنك تريد حذف هذا $item؟ لا يمكن التراجع عن هذا الإجراء.';
  }

  @override
  String get revokeKeyQuestion => 'إلغاء المفتاح؟';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'هل أنت متأكد أنك تريد إلغاء المفتاح \"$keyName\"؟ لا يمكن التراجع عن هذا الإجراء.';
  }

  @override
  String get createNewKey => 'إنشاء مفتاح جديد';

  @override
  String get keyNameHint => 'مثال: Claude Desktop';

  @override
  String get pleaseEnterAName => 'يرجى إدخال اسم.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'فشل إنشاء المفتاح: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'فشل إنشاء المفتاح. يرجى المحاولة مرة أخرى.';

  @override
  String get keyCreated => 'تم إنشاء المفتاح';

  @override
  String get keyCreatedMessage => 'تم إنشاء مفتاحك الجديد. يرجى نسخه الآن. لن تتمكن من رؤيته مرة أخرى.';

  @override
  String get keyWord => 'المفتاح';

  @override
  String get externalAppAccess => 'وصول التطبيقات الخارجية';

  @override
  String get externalAppAccessDescription =>
      'التطبيقات المثبتة التالية لديها تكاملات خارجية ويمكنها الوصول إلى بياناتك، مثل المحادثات والذكريات.';

  @override
  String get noExternalAppsHaveAccess => 'لا توجد تطبيقات خارجية لديها وصول إلى بياناتك.';

  @override
  String get maximumSecurityE2ee => 'الأمان الأقصى (E2EE)';

  @override
  String get e2eeDescription =>
      'التشفير من طرف إلى طرف هو المعيار الذهبي للخصوصية. عند تفعيله، يتم تشفير بياناتك على جهازك قبل إرسالها إلى خوادمنا. هذا يعني أنه لا أحد، ولا حتى Omi، يمكنه الوصول إلى محتواك.';

  @override
  String get importantTradeoffs => 'المقايضات المهمة:';

  @override
  String get e2eeTradeoff1 => '• قد يتم تعطيل بعض الميزات مثل تكامل التطبيقات الخارجية.';

  @override
  String get e2eeTradeoff2 => '• إذا فقدت كلمة المرور، لا يمكن استرداد بياناتك.';

  @override
  String get featureComingSoon => 'هذه الميزة قادمة قريباً!';

  @override
  String get migrationInProgressMessage => 'الترحيل قيد التقدم. لا يمكنك تغيير مستوى الحماية حتى يكتمل.';

  @override
  String get migrationFailed => 'فشل الترحيل';

  @override
  String migratingFromTo(String source, String target) {
    return 'الترحيل من $source إلى $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total كائنات';
  }

  @override
  String get secureEncryption => 'تشفير آمن';

  @override
  String get secureEncryptionDescription =>
      'يتم تشفير بياناتك بمفتاح فريد لك على خوادمنا المستضافة على Google Cloud. هذا يعني أن محتواك الأصلي غير متاح لأي شخص، بما في ذلك موظفي Omi أو Google، مباشرة من قاعدة البيانات.';

  @override
  String get endToEndEncryption => 'التشفير من طرف إلى طرف';

  @override
  String get e2eeCardDescription =>
      'قم بالتفعيل لأقصى درجات الأمان حيث يمكنك أنت فقط الوصول إلى بياناتك. انقر لمعرفة المزيد.';

  @override
  String get dataAlwaysEncrypted => 'بغض النظر عن المستوى، يتم تشفير بياناتك دائمًا أثناء التخزين وأثناء النقل.';

  @override
  String get readOnlyScope => 'قراءة فقط';

  @override
  String get fullAccessScope => 'وصول كامل';

  @override
  String get readScope => 'قراءة';

  @override
  String get writeScope => 'كتابة';

  @override
  String get apiKeyCreated => 'تم إنشاء مفتاح API!';

  @override
  String get saveKeyWarning => 'احفظ هذا المفتاح الآن! لن تتمكن من رؤيته مرة أخرى.';

  @override
  String get yourApiKey => 'مفتاح API الخاص بك';

  @override
  String get tapToCopy => 'اضغط للنسخ';

  @override
  String get copyKey => 'نسخ المفتاح';

  @override
  String get createApiKey => 'إنشاء مفتاح API';

  @override
  String get accessDataProgrammatically => 'الوصول إلى بياناتك برمجياً';

  @override
  String get keyNameLabel => 'اسم المفتاح';

  @override
  String get keyNamePlaceholder => 'مثال: تكامل تطبيقي';

  @override
  String get permissionsLabel => 'الأذونات';

  @override
  String get permissionsInfoNote => 'R = قراءة، W = كتابة. الافتراضي قراءة فقط إذا لم يتم تحديد شيء.';

  @override
  String get developerApi => 'واجهة برمجة تطبيقات المطور';

  @override
  String get createAKeyToGetStarted => 'أنشئ مفتاحاً للبدء';

  @override
  String errorWithMessage(String error) {
    return 'خطأ: $error';
  }

  @override
  String get omiTraining => 'تدريب Omi';

  @override
  String get trainingDataProgram => 'برنامج بيانات التدريب';

  @override
  String get getOmiUnlimitedFree =>
      'احصل على Omi غير محدود مجاناً من خلال المساهمة ببياناتك لتدريب نماذج الذكاء الاصطناعي.';

  @override
  String get trainingDataBullets =>
      '• بياناتك تساعد في تحسين نماذج الذكاء الاصطناعي\n• يتم مشاركة البيانات غير الحساسة فقط\n• عملية شفافة بالكامل';

  @override
  String get learnMoreAtOmiTraining => 'تعرف على المزيد في omi.me/training';

  @override
  String get agreeToContributeData => 'أفهم وأوافق على المساهمة ببياناتي لتدريب الذكاء الاصطناعي';

  @override
  String get submitRequest => 'إرسال الطلب';

  @override
  String get thankYouRequestUnderReview => 'شكراً لك! طلبك قيد المراجعة. سنعلمك بمجرد الموافقة.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'سيبقى اشتراكك نشطاً حتى $date. بعد ذلك، ستفقد الوصول إلى الميزات غير المحدودة. هل أنت متأكد؟';
  }

  @override
  String get confirmCancellation => 'تأكيد الإلغاء';

  @override
  String get keepMyPlan => 'الاحتفاظ باشتراكي';

  @override
  String get subscriptionSetToCancel => 'تم تعيين اشتراكك للإلغاء في نهاية الفترة.';

  @override
  String get switchedToOnDevice => 'تم التبديل إلى النسخ على الجهاز';

  @override
  String get couldNotSwitchToFreePlan => 'تعذر التبديل إلى الخطة المجانية. يرجى المحاولة مرة أخرى.';

  @override
  String get couldNotLoadPlans => 'تعذر تحميل الخطط المتاحة. يرجى المحاولة مرة أخرى.';

  @override
  String get selectedPlanNotAvailable => 'الخطة المحددة غير متاحة. يرجى المحاولة مرة أخرى.';

  @override
  String get upgradeToAnnualPlan => 'الترقية إلى الخطة السنوية';

  @override
  String get importantBillingInfo => 'معلومات فوترة مهمة:';

  @override
  String get monthlyPlanContinues => 'ستستمر خطتك الشهرية الحالية حتى نهاية فترة الفوترة';

  @override
  String get paymentMethodCharged => 'سيتم خصم الرسوم تلقائياً من طريقة الدفع الحالية عند انتهاء خطتك الشهرية';

  @override
  String get annualSubscriptionStarts => 'سيبدأ اشتراكك السنوي لمدة 12 شهراً تلقائياً بعد الخصم';

  @override
  String get thirteenMonthsCoverage => 'ستحصل على تغطية إجمالية لمدة 13 شهراً (الشهر الحالي + 12 شهراً سنوياً)';

  @override
  String get confirmUpgrade => 'تأكيد الترقية';

  @override
  String get confirmPlanChange => 'تأكيد تغيير الخطة';

  @override
  String get confirmAndProceed => 'تأكيد ومتابعة';

  @override
  String get upgradeScheduled => 'تمت جدولة الترقية';

  @override
  String get changePlan => 'تغيير الخطة';

  @override
  String get upgradeAlreadyScheduled => 'تمت جدولة ترقيتك إلى الخطة السنوية بالفعل';

  @override
  String get youAreOnUnlimitedPlan => 'أنت مشترك في الخطة غير المحدودة.';

  @override
  String get yourOmiUnleashed => 'أطلق العنان لـ Omi الخاص بك. انطلق بلا حدود لإمكانيات لا نهائية.';

  @override
  String planEndedOn(String date) {
    return 'انتهت خطتك في $date.\\nأعد الاشتراك الآن - سيتم تحصيل الرسوم فوراً لفترة فوترة جديدة.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'تم تعيين خطتك للإلغاء في $date.\\nأعد الاشتراك الآن للحفاظ على مزاياك - لن يتم تحصيل رسوم حتى $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'ستبدأ خطتك السنوية تلقائياً عند انتهاء خطتك الشهرية.';

  @override
  String planRenewsOn(String date) {
    return 'يتم تجديد خطتك في $date.';
  }

  @override
  String get unlimitedConversations => 'محادثات غير محدودة';

  @override
  String get askOmiAnything => 'اسأل Omi أي شيء عن حياتك';

  @override
  String get unlockOmiInfiniteMemory => 'افتح ذاكرة Omi اللامحدودة';

  @override
  String get youreOnAnnualPlan => 'أنت مشترك في الخطة السنوية';

  @override
  String get alreadyBestValuePlan => 'لديك بالفعل أفضل خطة من حيث القيمة. لا حاجة لأي تغييرات.';

  @override
  String get unableToLoadPlans => 'تعذر تحميل الخطط';

  @override
  String get checkConnectionTryAgain => 'يرجى التحقق من اتصالك والمحاولة مرة أخرى';

  @override
  String get useFreePlan => 'استخدام الخطة المجانية';

  @override
  String get continueText => 'متابعة';

  @override
  String get resubscribe => 'إعادة الاشتراك';

  @override
  String get couldNotOpenPaymentSettings => 'تعذر فتح إعدادات الدفع. يرجى المحاولة مرة أخرى.';

  @override
  String get managePaymentMethod => 'إدارة طريقة الدفع';

  @override
  String get cancelSubscription => 'إلغاء الاشتراك';

  @override
  String endsOnDate(String date) {
    return 'ينتهي في $date';
  }

  @override
  String get active => 'نشط';

  @override
  String get freePlan => 'الخطة المجانية';

  @override
  String get configure => 'تكوين';

  @override
  String get privacyInformation => 'معلومات الخصوصية';

  @override
  String get yourPrivacyMattersToUs => 'خصوصيتك تهمنا';

  @override
  String get privacyIntroText =>
      'في Omi، نأخذ خصوصيتك على محمل الجد. نريد أن نكون شفافين بشأن البيانات التي نجمعها وكيف نستخدمها لتحسين منتجنا لك. إليك ما تحتاج معرفته:';

  @override
  String get whatWeTrack => 'ما نتتبعه';

  @override
  String get anonymityAndPrivacy => 'الهوية المجهولة والخصوصية';

  @override
  String get optInAndOptOutOptions => 'خيارات الاشتراك وإلغاء الاشتراك';

  @override
  String get ourCommitment => 'التزامنا';

  @override
  String get commitmentText =>
      'نحن ملتزمون باستخدام البيانات التي نجمعها فقط لجعل Omi منتجًا أفضل لك. خصوصيتك وثقتك في غاية الأهمية لنا.';

  @override
  String get thankYouText =>
      'شكرًا لك لكونك مستخدمًا قيمًا لـ Omi. إذا كانت لديك أي أسئلة أو مخاوف، فلا تتردد في التواصل معنا على team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'إعدادات مزامنة WiFi';

  @override
  String get enterHotspotCredentials => 'أدخل بيانات اعتماد نقطة اتصال هاتفك';

  @override
  String get wifiSyncUsesHotspot =>
      'تستخدم مزامنة WiFi هاتفك كنقطة اتصال. ابحث عن اسم وكلمة مرور نقطة الاتصال في الإعدادات > نقطة اتصال شخصية.';

  @override
  String get hotspotNameSsid => 'اسم نقطة الاتصال (SSID)';

  @override
  String get exampleIphoneHotspot => 'مثال: نقطة اتصال iPhone';

  @override
  String get password => 'كلمة المرور';

  @override
  String get enterHotspotPassword => 'أدخل كلمة مرور نقطة الاتصال';

  @override
  String get saveCredentials => 'حفظ بيانات الاعتماد';

  @override
  String get clearCredentials => 'مسح بيانات الاعتماد';

  @override
  String get pleaseEnterHotspotName => 'يرجى إدخال اسم نقطة الاتصال';

  @override
  String get wifiCredentialsSaved => 'تم حفظ بيانات اعتماد WiFi';

  @override
  String get wifiCredentialsCleared => 'تم مسح بيانات اعتماد WiFi';

  @override
  String summaryGeneratedForDate(String date) {
    return 'تم إنشاء الملخص لـ $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations => 'فشل في إنشاء الملخص. تأكد من وجود محادثات لذلك اليوم.';

  @override
  String get summaryNotFound => 'الملخص غير موجود';

  @override
  String get yourDaysJourney => 'رحلة يومك';

  @override
  String get highlights => 'أبرز الأحداث';

  @override
  String get unresolvedQuestions => 'أسئلة لم تحل';

  @override
  String get decisions => 'القرارات';

  @override
  String get learnings => 'الدروس المستفادة';

  @override
  String get autoDeletesAfterThreeDays => 'يحذف تلقائيًا بعد 3 أيام.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'تم حذف الرسم البياني المعرفي بنجاح';

  @override
  String get exportStartedMayTakeFewSeconds => 'بدأ التصدير. قد يستغرق هذا بضع ثوانٍ...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'سيؤدي هذا إلى حذف جميع بيانات الرسم البياني المعرفي المشتقة (العقد والاتصالات). ستبقى ذكرياتك الأصلية آمنة. سيتم إعادة بناء الرسم البياني بمرور الوقت أو عند الطلب التالي.';

  @override
  String get configureDailySummaryDigest => 'قم بتكوين ملخص مهامك اليومية';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'يصل إلى $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'يتم تشغيله بواسطة $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription و$triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'لم يتم تكوين وصول محدد للبيانات.';

  @override
  String get basicPlanDescription => '1,200 دقيقة مميزة + غير محدود على الجهاز';

  @override
  String get minutes => 'دقائق';

  @override
  String get omiHas => 'لدى Omi:';

  @override
  String get premiumMinutesUsed => 'تم استخدام الدقائق المميزة.';

  @override
  String get setupOnDevice => 'إعداد على الجهاز';

  @override
  String get forUnlimitedFreeTranscription => 'للنسخ المجاني غير المحدود.';

  @override
  String premiumMinsLeft(int count) {
    return '$count دقائق مميزة متبقية.';
  }

  @override
  String get alwaysAvailable => 'متاح دائمًا.';

  @override
  String get importHistory => 'سجل الاستيراد';

  @override
  String get noImportsYet => 'لا توجد عمليات استيراد بعد';

  @override
  String get selectZipFileToImport => 'اختر ملف .zip للاستيراد!';

  @override
  String get otherDevicesComingSoon => 'أجهزة أخرى قريبًا';

  @override
  String get deleteAllLimitlessConversations => 'حذف جميع محادثات Limitless؟';

  @override
  String get deleteAllLimitlessWarning =>
      'سيؤدي هذا إلى حذف جميع المحادثات المستوردة من Limitless نهائيًا. لا يمكن التراجع عن هذا الإجراء.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'تم حذف $count محادثة Limitless';
  }

  @override
  String get failedToDeleteConversations => 'فشل في حذف المحادثات';

  @override
  String get deleteImportedData => 'حذف البيانات المستوردة';

  @override
  String get statusPending => 'قيد الانتظار';

  @override
  String get statusProcessing => 'جاري المعالجة';

  @override
  String get statusCompleted => 'مكتمل';

  @override
  String get statusFailed => 'فشل';

  @override
  String nConversations(int count) {
    return '$count محادثات';
  }

  @override
  String get pleaseEnterName => 'الرجاء إدخال اسم';

  @override
  String get nameMustBeBetweenCharacters => 'يجب أن يكون الاسم بين 2 و 40 حرفًا';

  @override
  String get deleteSampleQuestion => 'حذف العينة؟';

  @override
  String deleteSampleConfirmation(String name) {
    return 'هل أنت متأكد من حذف عينة $name؟';
  }

  @override
  String get confirmDeletion => 'تأكيد الحذف';

  @override
  String deletePersonConfirmation(String name) {
    return 'هل أنت متأكد من حذف $name؟ سيؤدي ذلك أيضًا إلى إزالة جميع عينات الكلام المرتبطة.';
  }

  @override
  String get howItWorksTitle => 'كيف يعمل؟';

  @override
  String get howPeopleWorks =>
      'بمجرد إنشاء شخص، يمكنك الذهاب إلى نص المحادثة وتعيين الأجزاء المقابلة لهم، وبهذه الطريقة سيتمكن Omi من التعرف على كلامهم أيضًا!';

  @override
  String get tapToDelete => 'اضغط للحذف';

  @override
  String get newTag => 'جديد';

  @override
  String get needHelpChatWithUs => 'تحتاج مساعدة؟ تحدث معنا';

  @override
  String get localStorageEnabled => 'تم تفعيل التخزين المحلي';

  @override
  String get localStorageDisabled => 'تم تعطيل التخزين المحلي';

  @override
  String failedToUpdateSettings(String error) {
    return 'فشل تحديث الإعدادات: $error';
  }

  @override
  String get privacyNotice => 'إشعار الخصوصية';

  @override
  String get recordingsMayCaptureOthers =>
      'قد تلتقط التسجيلات أصوات الآخرين. تأكد من الحصول على موافقة جميع المشاركين قبل التفعيل.';

  @override
  String get enable => 'تفعيل';

  @override
  String get storeAudioOnPhone => 'تخزين الصوت على الهاتف';

  @override
  String get on => 'تشغيل';

  @override
  String get storeAudioDescription =>
      'احتفظ بجميع التسجيلات الصوتية مخزنة محليًا على هاتفك. عند التعطيل، يتم الاحتفاظ فقط بالتحميلات الفاشلة لتوفير مساحة التخزين.';

  @override
  String get enableLocalStorage => 'تفعيل التخزين المحلي';

  @override
  String get cloudStorageEnabled => 'تم تفعيل التخزين السحابي';

  @override
  String get cloudStorageDisabled => 'تم تعطيل التخزين السحابي';

  @override
  String get enableCloudStorage => 'تفعيل التخزين السحابي';

  @override
  String get storeAudioOnCloud => 'تخزين الصوت على السحابة';

  @override
  String get cloudStorageDialogMessage => 'سيتم تخزين تسجيلاتك في الوقت الفعلي في التخزين السحابي الخاص أثناء التحدث.';

  @override
  String get storeAudioCloudDescription =>
      'قم بتخزين تسجيلاتك في الوقت الفعلي في التخزين السحابي الخاص أثناء التحدث. يتم التقاط الصوت وحفظه بشكل آمن في الوقت الفعلي.';

  @override
  String get downloadingFirmware => 'جارٍ تنزيل البرنامج الثابت';

  @override
  String get installingFirmware => 'جارٍ تثبيت البرنامج الثابت';

  @override
  String get firmwareUpdateWarning => 'لا تغلق التطبيق أو توقف الجهاز. قد يؤدي ذلك إلى إتلاف جهازك.';

  @override
  String get firmwareUpdated => 'تم تحديث البرنامج الثابت';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'يرجى إعادة تشغيل $deviceName لإكمال التحديث.';
  }

  @override
  String get yourDeviceIsUpToDate => 'جهازك محدث';

  @override
  String get currentVersion => 'الإصدار الحالي';

  @override
  String get latestVersion => 'أحدث إصدار';

  @override
  String get whatsNew => 'ما الجديد';

  @override
  String get installUpdate => 'تثبيت التحديث';

  @override
  String get updateNow => 'تحديث الآن';

  @override
  String get updateGuide => 'دليل التحديث';

  @override
  String get checkingForUpdates => 'جارٍ البحث عن التحديثات';

  @override
  String get checkingFirmwareVersion => 'جارٍ التحقق من إصدار البرنامج الثابت...';

  @override
  String get firmwareUpdate => 'تحديث البرنامج الثابت';

  @override
  String get payments => 'المدفوعات';

  @override
  String get connectPaymentMethodInfo => 'قم بتوصيل طريقة دفع أدناه لبدء تلقي المدفوعات لتطبيقاتك.';

  @override
  String get selectedPaymentMethod => 'طريقة الدفع المحددة';

  @override
  String get availablePaymentMethods => 'طرق الدفع المتاحة';

  @override
  String get activeStatus => 'نشط';

  @override
  String get connectedStatus => 'متصل';

  @override
  String get notConnectedStatus => 'غير متصل';

  @override
  String get setActive => 'تعيين كنشط';

  @override
  String get getPaidThroughStripe => 'احصل على أموالك من مبيعات تطبيقاتك عبر Stripe';

  @override
  String get monthlyPayouts => 'دفعات شهرية';

  @override
  String get monthlyPayoutsDescription => 'احصل على دفعات شهرية مباشرة إلى حسابك عندما تصل أرباحك إلى 10 دولارات';

  @override
  String get secureAndReliable => 'آمن وموثوق';

  @override
  String get stripeSecureDescription => 'يضمن Stripe تحويلات آمنة وفي الوقت المناسب لإيرادات تطبيقك';

  @override
  String get selectYourCountry => 'اختر بلدك';

  @override
  String get countrySelectionPermanent => 'اختيار بلدك دائم ولا يمكن تغييره لاحقًا.';

  @override
  String get byClickingConnectNow => 'بالنقر على \"اتصل الآن\" فإنك توافق على';

  @override
  String get stripeConnectedAccountAgreement => 'اتفاقية حساب Stripe المتصل';

  @override
  String get errorConnectingToStripe => 'خطأ في الاتصال بـ Stripe! يرجى المحاولة مرة أخرى لاحقًا.';

  @override
  String get connectingYourStripeAccount => 'جاري توصيل حساب Stripe الخاص بك';

  @override
  String get stripeOnboardingInstructions =>
      'يرجى إكمال عملية تسجيل Stripe في متصفحك. ستتحدث هذه الصفحة تلقائيًا عند الانتهاء.';

  @override
  String get failedTryAgain => 'فشل؟ حاول مرة أخرى';

  @override
  String get illDoItLater => 'سأفعل ذلك لاحقًا';

  @override
  String get successfullyConnected => 'تم الاتصال بنجاح!';

  @override
  String get stripeReadyForPayments =>
      'حساب Stripe الخاص بك جاهز الآن لاستقبال المدفوعات. يمكنك البدء في الكسب من مبيعات تطبيقك على الفور.';

  @override
  String get updateStripeDetails => 'تحديث تفاصيل Stripe';

  @override
  String get errorUpdatingStripeDetails => 'خطأ في تحديث تفاصيل Stripe! يرجى المحاولة مرة أخرى لاحقًا.';

  @override
  String get updatePayPal => 'تحديث PayPal';

  @override
  String get setUpPayPal => 'إعداد PayPal';

  @override
  String get updatePayPalAccountDetails => 'تحديث تفاصيل حساب PayPal الخاص بك';

  @override
  String get connectPayPalToReceivePayments => 'قم بتوصيل حساب PayPal الخاص بك لبدء تلقي المدفوعات لتطبيقاتك';

  @override
  String get paypalEmail => 'بريد PayPal الإلكتروني';

  @override
  String get paypalMeLink => 'رابط PayPal.me';

  @override
  String get stripeRecommendation =>
      'إذا كان Stripe متاحًا في بلدك، نوصي بشدة باستخدامه للحصول على مدفوعات أسرع وأسهل.';

  @override
  String get updatePayPalDetails => 'تحديث تفاصيل PayPal';

  @override
  String get savePayPalDetails => 'حفظ تفاصيل PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'يرجى إدخال بريد PayPal الإلكتروني الخاص بك';

  @override
  String get pleaseEnterPayPalMeLink => 'يرجى إدخال رابط PayPal.me الخاص بك';

  @override
  String get doNotIncludeHttpInLink => 'لا تقم بتضمين http أو https أو www في الرابط';

  @override
  String get pleaseEnterValidPayPalMeLink => 'يرجى إدخال رابط PayPal.me صالح';

  @override
  String get pleaseEnterValidEmail => 'يرجى إدخال عنوان بريد إلكتروني صالح';

  @override
  String get syncingYourRecordings => 'جاري مزامنة تسجيلاتك';

  @override
  String get syncYourRecordings => 'مزامنة تسجيلاتك';

  @override
  String get syncNow => 'مزامنة الآن';

  @override
  String get error => 'خطأ';

  @override
  String get speechSamples => 'عينات الكلام';

  @override
  String additionalSampleIndex(String index) {
    return 'عينة إضافية $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'المدة: $seconds ثانية';
  }

  @override
  String get additionalSpeechSampleRemoved => 'تمت إزالة عينة الكلام الإضافية';

  @override
  String get consentDataMessage =>
      'بالمتابعة، سيتم تخزين جميع البيانات التي تشاركها مع هذا التطبيق (بما في ذلك محادثاتك وتسجيلاتك ومعلوماتك الشخصية) بشكل آمن على خوادمنا لتزويدك برؤى مدعومة بالذكاء الاصطناعي وتمكين جميع ميزات التطبيق.';

  @override
  String get tasksEmptyStateMessage => 'ستظهر المهام من محادثاتك هنا.\nاضغط على + لإنشاء مهمة يدويًا.';

  @override
  String get clearChatAction => 'مسح المحادثة';

  @override
  String get enableApps => 'تفعيل التطبيقات';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'عرض المزيد ↓';

  @override
  String get showLess => 'عرض أقل ↑';

  @override
  String get loadingYourRecording => 'جاري تحميل التسجيل...';

  @override
  String get photoDiscardedMessage => 'تم تجاهل هذه الصورة لأنها غير مهمة.';

  @override
  String get analyzing => 'جاري التحليل...';

  @override
  String get searchCountries => 'البحث عن البلدان...';

  @override
  String get checkingAppleWatch => 'جاري فحص Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'قم بتثبيت Omi على\nApple Watch الخاص بك';

  @override
  String get installOmiOnAppleWatchDescription =>
      'لاستخدام Apple Watch مع Omi، تحتاج أولاً إلى تثبيت تطبيق Omi على ساعتك.';

  @override
  String get openOmiOnAppleWatch => 'افتح Omi على\nApple Watch الخاص بك';

  @override
  String get openOmiOnAppleWatchDescription =>
      'تم تثبيت تطبيق Omi على Apple Watch الخاص بك. افتحه واضغط على بدء للبدء.';

  @override
  String get openWatchApp => 'افتح تطبيق الساعة';

  @override
  String get iveInstalledAndOpenedTheApp => 'لقد قمت بتثبيت وفتح التطبيق';

  @override
  String get unableToOpenWatchApp =>
      'تعذر فتح تطبيق Apple Watch. يرجى فتح تطبيق Watch يدويًا على Apple Watch وتثبيت Omi من قسم \"التطبيقات المتاحة\".';

  @override
  String get appleWatchConnectedSuccessfully => 'تم توصيل Apple Watch بنجاح!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch لا يزال غير قابل للوصول. يرجى التأكد من أن تطبيق Omi مفتوح على ساعتك.';

  @override
  String errorCheckingConnection(String error) {
    return 'خطأ في التحقق من الاتصال: $error';
  }

  @override
  String get muted => 'مكتوم';

  @override
  String get processNow => 'معالجة الآن';

  @override
  String get finishedConversation => 'هل انتهت المحادثة؟';

  @override
  String get stopRecordingConfirmation => 'هل أنت متأكد أنك تريد إيقاف التسجيل وتلخيص المحادثة الآن؟';

  @override
  String get conversationEndsManually => 'ستنتهي المحادثة يدويًا فقط.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'يتم تلخيص المحادثة بعد $minutes دقيقة$suffix من عدم الكلام.';
  }

  @override
  String get dontAskAgain => 'لا تسألني مرة أخرى';

  @override
  String get waitingForTranscriptOrPhotos => 'في انتظار النص أو الصور...';

  @override
  String get noSummaryYet => 'لا يوجد ملخص بعد';

  @override
  String hints(String text) {
    return 'تلميحات: $text';
  }

  @override
  String get testConversationPrompt => 'اختبار موجه المحادثة';

  @override
  String get prompt => 'موجه';

  @override
  String get result => 'النتيجة:';

  @override
  String get compareTranscripts => 'مقارنة النصوص';

  @override
  String get notHelpful => 'غير مفيد';

  @override
  String get exportTasksWithOneTap => 'صدّر المهام بنقرة واحدة!';

  @override
  String get inProgress => 'قيد التنفيذ';

  @override
  String get photos => 'الصور';

  @override
  String get rawData => 'البيانات الخام';

  @override
  String get content => 'المحتوى';

  @override
  String get noContentToDisplay => 'لا يوجد محتوى للعرض';

  @override
  String get noSummary => 'لا يوجد ملخص';

  @override
  String get updateOmiFirmware => 'تحديث برنامج omi';

  @override
  String get anErrorOccurredTryAgain => 'حدث خطأ. يرجى المحاولة مرة أخرى.';

  @override
  String get welcomeBackSimple => 'مرحباً بعودتك';

  @override
  String get addVocabularyDescription => 'أضف كلمات يجب أن يتعرف عليها Omi أثناء النسخ.';

  @override
  String get enterWordsCommaSeparated => 'أدخل الكلمات (مفصولة بفواصل)';

  @override
  String get whenToReceiveDailySummary => 'متى تستلم ملخصك اليومي';

  @override
  String get checkingNextSevenDays => 'فحص الأيام السبعة القادمة';

  @override
  String failedToDeleteError(String error) {
    return 'فشل الحذف: $error';
  }

  @override
  String get developerApiKeys => 'مفاتيح API للمطورين';

  @override
  String get noApiKeysCreateOne => 'لا توجد مفاتيح API. أنشئ واحدة للبدء.';

  @override
  String get commandRequired => '⌘ مطلوب';

  @override
  String get spaceKey => 'المسافة';

  @override
  String loadMoreRemaining(String count) {
    return 'تحميل المزيد ($count متبقي)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'أفضل $percentile% مستخدم';
  }

  @override
  String get wrappedMinutes => 'دقائق';

  @override
  String get wrappedConversations => 'محادثات';

  @override
  String get wrappedDaysActive => 'أيام نشاط';

  @override
  String get wrappedYouTalkedAbout => 'تحدثت عن';

  @override
  String get wrappedActionItems => 'عناصر العمل';

  @override
  String get wrappedTasksCreated => 'مهام تم إنشاؤها';

  @override
  String get wrappedCompleted => 'مكتملة';

  @override
  String wrappedCompletionRate(String rate) {
    return 'معدل إتمام $rate%';
  }

  @override
  String get wrappedYourTopDays => 'أفضل أيامك';

  @override
  String get wrappedBestMoments => 'أفضل اللحظات';

  @override
  String get wrappedMyBuddies => 'أصدقائي';

  @override
  String get wrappedCouldntStopTalkingAbout => 'لم أتوقف عن الحديث عن';

  @override
  String get wrappedShow => 'مسلسل';

  @override
  String get wrappedMovie => 'فيلم';

  @override
  String get wrappedBook => 'كتاب';

  @override
  String get wrappedCelebrity => 'مشهور';

  @override
  String get wrappedFood => 'طعام';

  @override
  String get wrappedMovieRecs => 'توصيات أفلام للأصدقاء';

  @override
  String get wrappedBiggest => 'أكبر';

  @override
  String get wrappedStruggle => 'تحدي';

  @override
  String get wrappedButYouPushedThrough => 'لكنك تجاوزته 💪';

  @override
  String get wrappedWin => 'فوز';

  @override
  String get wrappedYouDidIt => 'لقد فعلتها! 🎉';

  @override
  String get wrappedTopPhrases => 'أكثر 5 عبارات';

  @override
  String get wrappedMins => 'دقائق';

  @override
  String get wrappedConvos => 'محادثات';

  @override
  String get wrappedDays => 'أيام';

  @override
  String get wrappedMyBuddiesLabel => 'أصدقائي';

  @override
  String get wrappedObsessionsLabel => 'هوسي';

  @override
  String get wrappedStruggleLabel => 'تحدي';

  @override
  String get wrappedWinLabel => 'فوز';

  @override
  String get wrappedTopPhrasesLabel => 'أكثر العبارات';

  @override
  String get wrappedLetsHitRewind => 'هيا نعيد لفّ';

  @override
  String get wrappedGenerateMyWrapped => 'أنشئ ملخصي';

  @override
  String get wrappedProcessingDefault => 'جاري المعالجة...';

  @override
  String get wrappedCreatingYourStory => 'جاري إنشاء\nقصة 2025 الخاصة بك...';

  @override
  String get wrappedSomethingWentWrong => 'حدث\nخطأ ما';

  @override
  String get wrappedAnErrorOccurred => 'حدث خطأ';

  @override
  String get wrappedTryAgain => 'حاول مرة أخرى';

  @override
  String get wrappedNoDataAvailable => 'لا توجد بيانات متاحة';

  @override
  String get wrappedOmiLifeRecap => 'ملخص حياة Omi';

  @override
  String get wrappedSwipeUpToBegin => 'اسحب للأعلى للبدء';

  @override
  String get wrappedShareText => '2025 الخاص بي، موثق بواسطة Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'فشلت المشاركة. يرجى المحاولة مرة أخرى.';

  @override
  String get wrappedFailedToStartGeneration => 'فشل بدء الإنشاء. يرجى المحاولة مرة أخرى.';

  @override
  String get wrappedStarting => 'جاري البدء...';

  @override
  String get wrappedShare => 'مشاركة';

  @override
  String get wrappedShareYourWrapped => 'شارك ملخصك';

  @override
  String get wrappedMy2025 => '2025 الخاص بي';

  @override
  String get wrappedRememberedByOmi => 'موثق بواسطة Omi';

  @override
  String get wrappedMostFunDay => 'الأكثر متعة';

  @override
  String get wrappedMostProductiveDay => 'الأكثر إنتاجية';

  @override
  String get wrappedMostIntenseDay => 'الأكثر حدة';

  @override
  String get wrappedFunniestMoment => 'الأكثر طرافة';

  @override
  String get wrappedMostCringeMoment => 'الأكثر إحراجاً';

  @override
  String get wrappedMinutesLabel => 'دقيقة';

  @override
  String get wrappedConversationsLabel => 'محادثة';

  @override
  String get wrappedDaysActiveLabel => 'يوم نشط';

  @override
  String get wrappedTasksGenerated => 'مهمة تم إنشاؤها';

  @override
  String get wrappedTasksCompleted => 'مهمة مكتملة';

  @override
  String get wrappedTopFivePhrases => 'أفضل 5 عبارات';

  @override
  String get wrappedAGreatDay => 'يوم رائع';

  @override
  String get wrappedGettingItDone => 'إنجاز المهام';

  @override
  String get wrappedAChallenge => 'تحدي';

  @override
  String get wrappedAHilariousMoment => 'لحظة مضحكة';

  @override
  String get wrappedThatAwkwardMoment => 'تلك اللحظة المحرجة';

  @override
  String get wrappedYouHadFunnyMoments => 'لقد مررت بلحظات مضحكة هذا العام!';

  @override
  String get wrappedWeveAllBeenThere => 'كلنا مررنا بهذا!';

  @override
  String get wrappedFriend => 'صديق';

  @override
  String get wrappedYourBuddy => 'صديقك!';

  @override
  String get wrappedNotMentioned => 'غير مذكور';

  @override
  String get wrappedTheHardPart => 'الجزء الصعب';

  @override
  String get wrappedPersonalGrowth => 'نمو شخصي';

  @override
  String get wrappedFunDay => 'متعة';

  @override
  String get wrappedProductiveDay => 'إنتاجي';

  @override
  String get wrappedIntenseDay => 'حاد';

  @override
  String get wrappedFunnyMomentTitle => 'لحظة مضحكة';

  @override
  String get wrappedCringeMomentTitle => 'لحظة محرجة';

  @override
  String get wrappedYouTalkedAboutBadge => 'تحدثت عن';

  @override
  String get wrappedCompletedLabel => 'مكتمل';

  @override
  String get wrappedMyBuddiesCard => 'أصدقائي';

  @override
  String get wrappedBuddiesLabel => 'الأصدقاء';

  @override
  String get wrappedObsessionsLabelUpper => 'الهوايات';

  @override
  String get wrappedStruggleLabelUpper => 'التحدي';

  @override
  String get wrappedWinLabelUpper => 'الفوز';

  @override
  String get wrappedTopPhrasesLabelUpper => 'أفضل العبارات';

  @override
  String get wrappedYourHeader => 'أيامك';

  @override
  String get wrappedTopDaysHeader => 'الأفضل';

  @override
  String get wrappedYourTopDaysBadge => 'أفضل أيامك';

  @override
  String get wrappedBestHeader => 'أفضل';

  @override
  String get wrappedMomentsHeader => 'اللحظات';

  @override
  String get wrappedBestMomentsBadge => 'أفضل اللحظات';

  @override
  String get wrappedBiggestHeader => 'أكبر';

  @override
  String get wrappedStruggleHeader => 'تحدي';

  @override
  String get wrappedWinHeader => 'فوز';

  @override
  String get wrappedButYouPushedThroughEmoji => 'لكنك تجاوزت ذلك 💪';

  @override
  String get wrappedYouDidItEmoji => 'لقد فعلتها! 🎉';

  @override
  String get wrappedHours => 'ساعات';

  @override
  String get wrappedActions => 'إجراءات';

  @override
  String get multipleSpeakersDetected => 'تم اكتشاف عدة متحدثين';

  @override
  String get multipleSpeakersDescription =>
      'يبدو أن هناك عدة متحدثين في التسجيل. يرجى التأكد من أنك في مكان هادئ والمحاولة مرة أخرى.';

  @override
  String get invalidRecordingDetected => 'تم اكتشاف تسجيل غير صالح';

  @override
  String get notEnoughSpeechDescription => 'لم يتم اكتشاف كلام كافٍ. يرجى التحدث أكثر والمحاولة مرة أخرى.';

  @override
  String get speechDurationDescription => 'يرجى التأكد من التحدث لمدة 5 ثوانٍ على الأقل وليس أكثر من 90 ثانية.';

  @override
  String get connectionLostDescription => 'تم قطع الاتصال. يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى.';

  @override
  String get howToTakeGoodSample => 'كيف تأخذ عينة جيدة؟';

  @override
  String get goodSampleInstructions =>
      '1. تأكد من أنك في مكان هادئ.\n2. تحدث بوضوح وطبيعية.\n3. تأكد من أن جهازك في وضعه الطبيعي على رقبتك.\n\nبمجرد إنشائه، يمكنك دائمًا تحسينه أو القيام به مرة أخرى.';

  @override
  String get noDeviceConnectedUseMic => 'لا يوجد جهاز متصل. سيتم استخدام ميكروفون الهاتف.';

  @override
  String get doItAgain => 'أعد المحاولة';

  @override
  String get listenToSpeechProfile => 'استمع إلى ملفي الصوتي ➡️';

  @override
  String get recognizingOthers => 'التعرف على الآخرين 👀';

  @override
  String get keepGoingGreat => 'استمر، أنت تقوم بعمل رائع';

  @override
  String get somethingWentWrongTryAgain => 'حدث خطأ ما! يرجى المحاولة مرة أخرى لاحقاً.';

  @override
  String get uploadingVoiceProfile => 'جاري تحميل ملفك الصوتي....';

  @override
  String get memorizingYourVoice => 'جاري حفظ صوتك...';

  @override
  String get personalizingExperience => 'جاري تخصيص تجربتك...';

  @override
  String get keepSpeakingUntil100 => 'استمر في التحدث حتى تصل إلى 100%.';

  @override
  String get greatJobAlmostThere => 'عمل رائع، أنت على وشك الانتهاء';

  @override
  String get soCloseJustLittleMore => 'قريب جداً، فقط القليل';

  @override
  String get notificationFrequency => 'تكرار الإشعارات';

  @override
  String get controlNotificationFrequency => 'تحكم في عدد مرات إرسال Omi للإشعارات الاستباقية.';

  @override
  String get yourScore => 'نتيجتك';

  @override
  String get dailyScoreBreakdown => 'تفاصيل النتيجة اليومية';

  @override
  String get todaysScore => 'نتيجة اليوم';

  @override
  String get tasksCompleted => 'المهام المكتملة';

  @override
  String get completionRate => 'نسبة الإنجاز';

  @override
  String get howItWorks => 'كيف يعمل';

  @override
  String get dailyScoreExplanation => 'نتيجتك اليومية تعتمد على إكمال المهام. أكمل مهامك لتحسين نتيجتك!';

  @override
  String get notificationFrequencyDescription => 'تحكم في عدد مرات إرسال Omi للإشعارات والتذكيرات الاستباقية.';

  @override
  String get sliderOff => 'إيقاف';

  @override
  String get sliderMax => 'الحد الأقصى';

  @override
  String summaryGeneratedFor(String date) {
    return 'تم إنشاء ملخص لـ $date';
  }

  @override
  String get failedToGenerateSummary => 'فشل في إنشاء الملخص. تأكد من وجود محادثات لذلك اليوم.';

  @override
  String get recap => 'ملخص';

  @override
  String deleteQuoted(String name) {
    return 'حذف \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'نقل $count محادثات إلى:';
  }

  @override
  String get noFolder => 'بدون مجلد';

  @override
  String get removeFromAllFolders => 'إزالة من جميع المجلدات';

  @override
  String get buildAndShareYourCustomApp => 'قم ببناء ومشاركة تطبيقك المخصص';

  @override
  String get searchAppsPlaceholder => 'ابحث في أكثر من 1500 تطبيق';

  @override
  String get filters => 'التصفيات';

  @override
  String get frequencyOff => 'إيقاف';

  @override
  String get frequencyMinimal => 'الحد الأدنى';

  @override
  String get frequencyLow => 'منخفض';

  @override
  String get frequencyBalanced => 'متوازن';

  @override
  String get frequencyHigh => 'عالي';

  @override
  String get frequencyMaximum => 'الحد الأقصى';

  @override
  String get frequencyDescOff => 'لا توجد إشعارات استباقية';

  @override
  String get frequencyDescMinimal => 'تذكيرات حرجة فقط';

  @override
  String get frequencyDescLow => 'التحديثات المهمة فقط';

  @override
  String get frequencyDescBalanced => 'تنبيهات مفيدة منتظمة';

  @override
  String get frequencyDescHigh => 'متابعات متكررة';

  @override
  String get frequencyDescMaximum => 'ابق على تواصل دائم';

  @override
  String get clearChatQuestion => 'مسح المحادثة؟';

  @override
  String get syncingMessages => 'جاري مزامنة الرسائل مع الخادم...';

  @override
  String get chatAppsTitle => 'تطبيقات الدردشة';

  @override
  String get selectApp => 'اختر التطبيق';

  @override
  String get noChatAppsEnabled => 'لا توجد تطبيقات دردشة مفعلة.\nاضغط على \"تمكين التطبيقات\" لإضافة بعضها.';

  @override
  String get disable => 'تعطيل';

  @override
  String get photoLibrary => 'مكتبة الصور';

  @override
  String get chooseFile => 'اختر ملف';

  @override
  String get configureAiPersona => 'إعداد شخصية الذكاء الاصطناعي الخاصة بك';

  @override
  String get connectAiAssistantsToYourData => 'ربط مساعدي الذكاء الاصطناعي ببياناتك';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'تتبع أهدافك الشخصية على الصفحة الرئيسية';

  @override
  String get deleteRecording => 'حذف التسجيل';

  @override
  String get thisCannotBeUndone => 'لا يمكن التراجع عن هذا الإجراء.';

  @override
  String get sdCard => 'بطاقة SD';

  @override
  String get fromSd => 'من SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'النقل السريع';

  @override
  String get syncingStatus => 'جارٍ المزامنة';

  @override
  String get failedStatus => 'فشل';

  @override
  String etaLabel(String time) {
    return 'الوقت المتبقي: $time';
  }

  @override
  String get transferMethod => 'طريقة النقل';

  @override
  String get fast => 'سريع';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'الهاتف';

  @override
  String get cancelSync => 'إلغاء المزامنة';

  @override
  String get cancelSyncMessage => 'سيتم حفظ البيانات التي تم تنزيلها. يمكنك الاستئناف لاحقاً.';

  @override
  String get syncCancelled => 'تم إلغاء المزامنة';

  @override
  String get deleteProcessedFiles => 'حذف الملفات المعالجة';

  @override
  String get processedFilesDeleted => 'تم حذف الملفات المعالجة';

  @override
  String get wifiEnableFailed => 'فشل تفعيل واي فاي على الجهاز. يرجى المحاولة مرة أخرى.';

  @override
  String get deviceNoFastTransfer => 'جهازك لا يدعم النقل السريع. استخدم البلوتوث في الوقت الحالي.';

  @override
  String get enableHotspotMessage => 'يرجى تفعيل نقطة اتصال هاتفك والمحاولة مرة أخرى.';

  @override
  String get transferStartFailed => 'فشل بدء النقل. يرجى المحاولة مرة أخرى.';

  @override
  String get deviceNotResponding => 'لم يستجب الجهاز. يرجى المحاولة مرة أخرى.';

  @override
  String get invalidWifiCredentials => 'بيانات واي فاي غير صالحة. تحقق من إعدادات نقطة الاتصال.';

  @override
  String get wifiConnectionFailed => 'فشل اتصال واي فاي. يرجى المحاولة مرة أخرى.';

  @override
  String get sdCardProcessing => 'معالجة بطاقة SD';

  @override
  String sdCardProcessingMessage(int count) {
    return 'جارٍ معالجة $count تسجيل(ات). سيتم إزالة الملفات من البطاقة بعد المعالجة.';
  }

  @override
  String get process => 'معالجة';

  @override
  String get wifiSyncFailed => 'فشلت مزامنة واي فاي';

  @override
  String get processingFailed => 'فشلت المعالجة';

  @override
  String get downloadingFromSdCard => 'جارٍ التنزيل من بطاقة SD';

  @override
  String processingProgress(int current, int total) {
    return 'جارٍ المعالجة $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return 'تم إنشاء $count محادثة';
  }

  @override
  String get internetRequired => 'يتطلب اتصال بالإنترنت';

  @override
  String get processAudio => 'معالجة الصوت';

  @override
  String get start => 'بدء';

  @override
  String get noRecordings => 'لا توجد تسجيلات';

  @override
  String get audioFromOmiWillAppearHere => 'سيظهر الصوت من جهاز Omi الخاص بك هنا';

  @override
  String get deleteProcessed => 'حذف المعالجة';

  @override
  String get tryDifferentFilter => 'جرب فلتراً مختلفاً';

  @override
  String get recordings => 'التسجيلات';

  @override
  String get enableRemindersAccess => 'يرجى تمكين الوصول للتذكيرات في الإعدادات لاستخدام تذكيرات Apple';

  @override
  String todayAtTime(String time) {
    return 'اليوم في $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'أمس في $time';
  }

  @override
  String get lessThanAMinute => 'أقل من دقيقة';

  @override
  String estimatedMinutes(int count) {
    return '~$count دقيقة/دقائق';
  }

  @override
  String estimatedHours(int count) {
    return '~$count ساعة/ساعات';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'المتبقي: $time تقريباً';
  }

  @override
  String get summarizingConversation => 'جاري تلخيص المحادثة...\nقد يستغرق هذا بضع ثوانٍ';

  @override
  String get resummarizingConversation => 'إعادة تلخيص المحادثة...\nقد يستغرق هذا بضع ثوانٍ';

  @override
  String get nothingInterestingRetry => 'لم يتم العثور على شيء مثير،\nهل تريد المحاولة مرة أخرى؟';

  @override
  String get noSummaryForConversation => 'لا يوجد ملخص\nلهذه المحادثة.';

  @override
  String get unknownLocation => 'موقع غير معروف';

  @override
  String get couldNotLoadMap => 'تعذر تحميل الخريطة';

  @override
  String get triggerConversationIntegration => 'تشغيل تكامل إنشاء المحادثة';

  @override
  String get webhookUrlNotSet => 'عنوان Webhook غير محدد';

  @override
  String get setWebhookUrlInSettings => 'يرجى تعيين عنوان Webhook في إعدادات المطور لاستخدام هذه الميزة.';

  @override
  String get sendWebUrl => 'إرسال رابط الويب';

  @override
  String get sendTranscript => 'إرسال النص';

  @override
  String get sendSummary => 'إرسال الملخص';

  @override
  String get debugModeDetected => 'تم اكتشاف وضع التصحيح';

  @override
  String get performanceReduced => 'الأداء منخفض 5-10 أضعاف. استخدم وضع الإصدار.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'يُغلق تلقائياً خلال $seconds ثانية';
  }

  @override
  String get modelRequired => 'النموذج مطلوب';

  @override
  String get downloadWhisperModel => 'يرجى تنزيل نموذج Whisper قبل الحفظ.';

  @override
  String get deviceNotCompatible => 'الجهاز غير متوافق';

  @override
  String get deviceRequirements => 'جهازك لا يستوفي متطلبات النسخ على الجهاز.';

  @override
  String get willLikelyCrash => 'من المحتمل أن يؤدي تمكين هذا إلى تعطل التطبيق أو تجمده.';

  @override
  String get transcriptionSlowerLessAccurate => 'سيكون النسخ أبطأ وأقل دقة بشكل ملحوظ.';

  @override
  String get proceedAnyway => 'المتابعة على أي حال';

  @override
  String get olderDeviceDetected => 'تم اكتشاف جهاز قديم';

  @override
  String get onDeviceSlower => 'قد يكون النسخ على الجهاز أبطأ.';

  @override
  String get batteryUsageHigher => 'استهلاك البطارية سيكون أعلى من النسخ السحابي.';

  @override
  String get considerOmiCloud => 'فكر في استخدام Omi Cloud للحصول على أداء أفضل.';

  @override
  String get highResourceUsage => 'استخدام مرتفع للموارد';

  @override
  String get onDeviceIntensive => 'النسخ على الجهاز يستهلك موارد حسابية كثيرة.';

  @override
  String get batteryDrainIncrease => 'سيزداد استنزاف البطارية بشكل كبير.';

  @override
  String get deviceMayWarmUp => 'قد يسخن الجهاز أثناء الاستخدام المطول.';

  @override
  String get speedAccuracyLower => 'قد تكون السرعة والدقة أقل من النماذج السحابية.';

  @override
  String get cloudProvider => 'مزود سحابي';

  @override
  String get premiumMinutesInfo => '1,200 دقيقة مميزة/شهر. علامة التبويب على الجهاز توفر نسخاً مجانياً غير محدود.';

  @override
  String get viewUsage => 'عرض الاستخدام';

  @override
  String get localProcessingInfo => 'تتم معالجة الصوت محلياً. يعمل دون اتصال، أكثر خصوصية، لكنه يستهلك بطارية أكثر.';

  @override
  String get model => 'النموذج';

  @override
  String get performanceWarning => 'تحذير الأداء';

  @override
  String get largeModelWarning =>
      'هذا النموذج كبير وقد يتسبب في تعطل التطبيق أو بطئه الشديد.\n\nيُنصح باستخدام \"small\" أو \"base\".';

  @override
  String get usingNativeIosSpeech => 'استخدام التعرف على الكلام الأصلي لـ iOS';

  @override
  String get noModelDownloadRequired => 'سيتم استخدام محرك الكلام الأصلي لجهازك. لا حاجة لتنزيل نموذج.';

  @override
  String get modelReady => 'النموذج جاهز';

  @override
  String get redownload => 'إعادة التنزيل';

  @override
  String get doNotCloseApp => 'يرجى عدم إغلاق التطبيق.';

  @override
  String get downloading => 'جاري التنزيل...';

  @override
  String get downloadModel => 'تنزيل النموذج';

  @override
  String estimatedSize(String size) {
    return 'الحجم التقديري: ~$size ميجابايت';
  }

  @override
  String availableSpace(String space) {
    return 'المساحة المتاحة: $space';
  }

  @override
  String get notEnoughSpace => 'تحذير: مساحة غير كافية!';

  @override
  String get download => 'تنزيل';

  @override
  String downloadError(String error) {
    return 'خطأ في التنزيل: $error';
  }

  @override
  String get cancelled => 'ملغى';

  @override
  String get deviceNotCompatibleTitle => 'الجهاز غير متوافق';

  @override
  String get deviceNotMeetRequirements => 'جهازك لا يستوفي متطلبات النسخ على الجهاز.';

  @override
  String get transcriptionSlowerOnDevice => 'قد يكون النسخ على الجهاز أبطأ على هذا الجهاز.';

  @override
  String get computationallyIntensive => 'النسخ على الجهاز يستهلك الكثير من الموارد الحسابية.';

  @override
  String get batteryDrainSignificantly => 'سيزداد استنزاف البطارية بشكل كبير.';

  @override
  String get premiumMinutesMonth => '1,200 دقيقة مميزة/شهر. علامة التبويب على الجهاز توفر نسخاً مجانياً غير محدود. ';

  @override
  String get audioProcessedLocally =>
      'تتم معالجة الصوت محلياً. يعمل بدون اتصال، أكثر خصوصية، لكنه يستهلك المزيد من البطارية.';

  @override
  String get languageLabel => 'اللغة';

  @override
  String get modelLabel => 'النموذج';

  @override
  String get modelTooLargeWarning =>
      'هذا النموذج كبير وقد يتسبب في تعطل التطبيق أو تشغيله ببطء شديد على الأجهزة المحمولة.\n\nيُوصى باستخدام small أو base.';

  @override
  String get nativeEngineNoDownload => 'سيتم استخدام محرك الكلام الأصلي لجهازك. لا يلزم تنزيل نموذج.';

  @override
  String modelReadyWithName(String model) {
    return 'النموذج جاهز ($model)';
  }

  @override
  String get reDownload => 'إعادة التنزيل';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'جارِ تنزيل $model: $received / $total ميجابايت';
  }

  @override
  String preparingModel(String model) {
    return 'جارِ تحضير $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'خطأ في التنزيل: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'الحجم التقريبي: ~$size ميجابايت';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'المساحة المتاحة: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'النسخ المباشر المدمج في Omi مُحسّن للمحادثات في الوقت الفعلي مع الكشف التلقائي عن المتحدثين والفصل بينهم.';

  @override
  String get reset => 'إعادة تعيين';

  @override
  String get useTemplateFrom => 'استخدام قالب من';

  @override
  String get selectProviderTemplate => 'اختر قالب مزود...';

  @override
  String get quicklyPopulateResponse => 'ملء سريع بتنسيق استجابة مزود معروف';

  @override
  String get quicklyPopulateRequest => 'ملء سريع بتنسيق طلب مزود معروف';

  @override
  String get invalidJsonError => 'JSON غير صالح';

  @override
  String downloadModelWithName(String model) {
    return 'تنزيل النموذج ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'النموذج: $model';
  }

  @override
  String get device => 'الجهاز';

  @override
  String get chatAssistantsTitle => 'مساعدو الدردشة';

  @override
  String get permissionReadConversations => 'قراءة المحادثات';

  @override
  String get permissionReadMemories => 'قراءة الذكريات';

  @override
  String get permissionReadTasks => 'قراءة المهام';

  @override
  String get permissionCreateConversations => 'إنشاء المحادثات';

  @override
  String get permissionCreateMemories => 'إنشاء الذكريات';

  @override
  String get permissionTypeAccess => 'الوصول';

  @override
  String get permissionTypeCreate => 'إنشاء';

  @override
  String get permissionTypeTrigger => 'مشغّل';

  @override
  String get permissionDescReadConversations => 'يمكن لهذا التطبيق الوصول إلى محادثاتك.';

  @override
  String get permissionDescReadMemories => 'يمكن لهذا التطبيق الوصول إلى ذكرياتك.';

  @override
  String get permissionDescReadTasks => 'يمكن لهذا التطبيق الوصول إلى مهامك.';

  @override
  String get permissionDescCreateConversations => 'يمكن لهذا التطبيق إنشاء محادثات جديدة.';

  @override
  String get permissionDescCreateMemories => 'يمكن لهذا التطبيق إنشاء ذكريات جديدة.';

  @override
  String get realtimeListening => 'الاستماع في الوقت الفعلي';

  @override
  String get setupCompleted => 'مكتمل';

  @override
  String get pleaseSelectRating => 'يرجى تحديد تقييم';

  @override
  String get writeReviewOptional => 'اكتب مراجعة (اختياري)';

  @override
  String get setupQuestionsIntro => 'ساعدنا في تحسين Omi بالإجابة على بعض الأسئلة. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. ما هو عملك؟';

  @override
  String get setupQuestionUsage => '2. أين تخطط لاستخدام Omi؟';

  @override
  String get setupQuestionAge => '3. ما هو نطاق عمرك؟';

  @override
  String get setupAnswerAllQuestions => 'لم تجب على جميع الأسئلة بعد! 🥺';

  @override
  String get setupSkipHelp => 'تخطي، لا أريد المساعدة :C';

  @override
  String get professionEntrepreneur => 'رائد أعمال';

  @override
  String get professionSoftwareEngineer => 'مهندس برمجيات';

  @override
  String get professionProductManager => 'مدير منتج';

  @override
  String get professionExecutive => 'تنفيذي';

  @override
  String get professionSales => 'مبيعات';

  @override
  String get professionStudent => 'طالب';

  @override
  String get usageAtWork => 'في العمل';

  @override
  String get usageIrlEvents => 'أحداث واقعية';

  @override
  String get usageOnline => 'عبر الإنترنت';

  @override
  String get usageSocialSettings => 'في المناسبات الاجتماعية';

  @override
  String get usageEverywhere => 'في كل مكان';

  @override
  String get customBackendUrlTitle => 'عنوان URL للخادم المخصص';

  @override
  String get backendUrlLabel => 'عنوان URL للخادم';

  @override
  String get saveUrlButton => 'حفظ URL';

  @override
  String get enterBackendUrlError => 'يرجى إدخال عنوان URL للخادم';

  @override
  String get urlMustEndWithSlashError => 'يجب أن ينتهي URL بـ \"/\"';

  @override
  String get invalidUrlError => 'يرجى إدخال عنوان URL صالح';

  @override
  String get backendUrlSavedSuccess => 'تم حفظ عنوان URL للخادم بنجاح!';

  @override
  String get signInTitle => 'تسجيل الدخول';

  @override
  String get signInButton => 'تسجيل الدخول';

  @override
  String get enterEmailError => 'يرجى إدخال بريدك الإلكتروني';

  @override
  String get invalidEmailError => 'يرجى إدخال بريد إلكتروني صالح';

  @override
  String get enterPasswordError => 'يرجى إدخال كلمة المرور';

  @override
  String get passwordMinLengthError => 'يجب أن تتكون كلمة المرور من 8 أحرف على الأقل';

  @override
  String get signInSuccess => 'تم تسجيل الدخول بنجاح!';

  @override
  String get alreadyHaveAccountLogin => 'لديك حساب بالفعل؟ سجل الدخول';

  @override
  String get emailLabel => 'البريد الإلكتروني';

  @override
  String get passwordLabel => 'كلمة المرور';

  @override
  String get createAccountTitle => 'إنشاء حساب';

  @override
  String get nameLabel => 'الاسم';

  @override
  String get repeatPasswordLabel => 'تكرار كلمة المرور';

  @override
  String get signUpButton => 'إنشاء حساب';

  @override
  String get enterNameError => 'يرجى إدخال اسمك';

  @override
  String get passwordsDoNotMatch => 'كلمات المرور غير متطابقة';

  @override
  String get signUpSuccess => 'تم التسجيل بنجاح!';

  @override
  String get loadingKnowledgeGraph => 'جارٍ تحميل رسم المعرفة...';

  @override
  String get noKnowledgeGraphYet => 'لا يوجد رسم معرفة بعد';

  @override
  String get buildingKnowledgeGraphFromMemories => 'جارٍ بناء رسم المعرفة من الذكريات...';

  @override
  String get knowledgeGraphWillBuildAutomatically => 'سيتم بناء رسم المعرفة تلقائياً عند إنشاء ذكريات جديدة.';

  @override
  String get buildGraphButton => 'بناء الرسم';

  @override
  String get checkOutMyMemoryGraph => 'شاهد رسم الذاكرة الخاص بي!';

  @override
  String get getButton => 'تحميل';

  @override
  String openingApp(String appName) {
    return 'جارٍ فتح $appName...';
  }

  @override
  String get writeSomething => 'اكتب شيئاً';

  @override
  String get submitReply => 'إرسال الرد';

  @override
  String get editYourReply => 'تعديل ردك';

  @override
  String get replyToReview => 'الرد على التقييم';

  @override
  String get rateAndReviewThisApp => 'قيم وراجع هذا التطبيق';

  @override
  String get noChangesInReview => 'لا توجد تغييرات في المراجعة للتحديث.';

  @override
  String get cantRateWithoutInternet => 'لا يمكن تقييم التطبيق بدون اتصال بالإنترنت.';

  @override
  String get appAnalytics => 'تحليلات التطبيق';

  @override
  String get learnMoreLink => 'اعرف المزيد';

  @override
  String get moneyEarned => 'الأرباح';

  @override
  String get writeYourReply => 'اكتب ردك...';

  @override
  String get replySentSuccessfully => 'تم إرسال الرد بنجاح';

  @override
  String failedToSendReply(String error) {
    return 'فشل في إرسال الرد: $error';
  }

  @override
  String get send => 'إرسال';

  @override
  String starFilter(int count) {
    return '$count نجمة';
  }

  @override
  String get noReviewsFound => 'لا توجد مراجعات';

  @override
  String get editReply => 'تعديل الرد';

  @override
  String get reply => 'رد';

  @override
  String starFilterLabel(int count) {
    return '$count نجمة';
  }

  @override
  String get sharePublicLink => 'مشاركة رابط عام';

  @override
  String get makePersonaPublic => 'جعل الشخصية عامة';

  @override
  String get connectedKnowledgeData => 'بيانات المعرفة المتصلة';

  @override
  String get enterName => 'أدخل الاسم';

  @override
  String get disconnectTwitter => 'فصل تويتر';

  @override
  String get disconnectTwitterConfirmation =>
      'هل أنت متأكد من رغبتك في فصل حساب تويتر الخاص بك؟ سيتم إزالة بياناتك المتصلة.';

  @override
  String get getOmiDeviceDescription => 'أنشئ نسخة أكثر دقة مع محادثاتك الشخصية وبياناتك.';

  @override
  String get getOmi => 'احصل على Omi';

  @override
  String get iHaveOmiDevice => 'لدي جهاز Omi';

  @override
  String get goal => 'هدف';

  @override
  String get tapToTrackThisGoal => 'انقر لتتبع هذا الهدف';

  @override
  String get tapToSetAGoal => 'انقر لتعيين هدف';

  @override
  String get processedConversations => 'المحادثات المعالجة';

  @override
  String get updatedConversations => 'المحادثات المحدثة';

  @override
  String get newConversations => 'محادثات جديدة';

  @override
  String get summaryTemplate => 'قالب الملخص';

  @override
  String get suggestedTemplates => 'القوالب المقترحة';

  @override
  String get otherTemplates => 'قوالب أخرى';

  @override
  String get availableTemplates => 'القوالب المتاحة';

  @override
  String get getCreative => 'كن مبدعًا';

  @override
  String get defaultLabel => 'افتراضي';

  @override
  String get lastUsedLabel => 'آخر استخدام';

  @override
  String get setDefaultApp => 'تعيين التطبيق الافتراضي';

  @override
  String setDefaultAppContent(String appName) {
    return 'هل تريد تعيين $appName كتطبيق تلخيص افتراضي؟\\n\\nسيتم استخدام هذا التطبيق تلقائيًا لجميع ملخصات المحادثات المستقبلية.';
  }

  @override
  String get setDefaultButton => 'تعيين كافتراضي';

  @override
  String setAsDefaultSuccess(String appName) {
    return 'تم تعيين $appName كتطبيق تلخيص افتراضي';
  }

  @override
  String get createCustomTemplate => 'إنشاء قالب مخصص';

  @override
  String get allTemplates => 'جميع القوالب';

  @override
  String failedToInstallApp(String appName) {
    return 'فشل في تثبيت $appName. يرجى المحاولة مرة أخرى.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'خطأ في تثبيت $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'وضع علامة على المتحدث $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'يوجد شخص بهذا الاسم بالفعل.';

  @override
  String get selectYouFromList => 'لوضع علامة على نفسك، يرجى اختيار \"أنت\" من القائمة.';

  @override
  String get enterPersonsName => 'أدخل اسم الشخص';

  @override
  String get addPerson => 'إضافة شخص';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'وضع علامة على مقاطع أخرى من هذا المتحدث ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'وضع علامة على مقاطع أخرى';

  @override
  String get managePeople => 'إدارة الأشخاص';

  @override
  String get shareViaSms => 'مشاركة عبر الرسائل القصيرة';

  @override
  String get selectContactsToShareSummary => 'اختر جهات الاتصال لمشاركة ملخص محادثتك';

  @override
  String get searchContactsHint => 'بحث في جهات الاتصال...';

  @override
  String contactsSelectedCount(int count) {
    return '$count محدد';
  }

  @override
  String get clearAllSelection => 'مسح الكل';

  @override
  String get selectContactsToShare => 'اختر جهات اتصال للمشاركة';

  @override
  String shareWithContactCount(int count) {
    return 'مشاركة مع $count جهة اتصال';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'مشاركة مع $count جهات اتصال';
  }

  @override
  String get contactsPermissionRequired => 'إذن الوصول لجهات الاتصال مطلوب';

  @override
  String get contactsPermissionRequiredForSms => 'إذن الوصول لجهات الاتصال مطلوب للمشاركة عبر الرسائل القصيرة';

  @override
  String get grantContactsPermissionForSms => 'يرجى منح إذن الوصول لجهات الاتصال للمشاركة عبر الرسائل القصيرة';

  @override
  String get noContactsWithPhoneNumbers => 'لم يتم العثور على جهات اتصال بأرقام هواتف';

  @override
  String get noContactsMatchSearch => 'لا توجد جهات اتصال تطابق بحثك';

  @override
  String get failedToLoadContacts => 'فشل تحميل جهات الاتصال';

  @override
  String get failedToPrepareConversationForSharing => 'فشل تحضير المحادثة للمشاركة. يرجى المحاولة مرة أخرى.';

  @override
  String get couldNotOpenSmsApp => 'تعذر فتح تطبيق الرسائل القصيرة. يرجى المحاولة مرة أخرى.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'إليك ما ناقشناه للتو: $link';
  }

  @override
  String get wifiSync => 'مزامنة الواي فاي';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item تم نسخه إلى الحافظة';
  }

  @override
  String get wifiConnectionFailedTitle => 'فشل الاتصال';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'جارٍ الاتصال بـ $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'تفعيل واي فاي $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'الاتصال بـ $deviceName';
  }

  @override
  String get recordingDetails => 'تفاصيل التسجيل';

  @override
  String get storageLocationSdCard => 'بطاقة SD';

  @override
  String get storageLocationLimitlessPendant => 'قلادة Limitless';

  @override
  String get storageLocationPhone => 'الهاتف';

  @override
  String get storageLocationPhoneMemory => 'الهاتف (الذاكرة)';

  @override
  String storedOnDevice(String deviceName) {
    return 'مخزن على $deviceName';
  }

  @override
  String get transferring => 'جارٍ النقل...';

  @override
  String get transferRequired => 'يتطلب النقل';

  @override
  String get downloadingAudioFromSdCard => 'جارٍ تنزيل الصوت من بطاقة SD الخاصة بجهازك';

  @override
  String get transferRequiredDescription => 'هذا التسجيل مخزن على بطاقة SD الخاصة بجهازك. انقله إلى هاتفك لتشغيله.';

  @override
  String get cancelTransfer => 'إلغاء النقل';

  @override
  String get transferToPhone => 'النقل إلى الهاتف';

  @override
  String get privateAndSecureOnDevice => 'خاص وآمن على جهازك';

  @override
  String get recordingInfo => 'معلومات التسجيل';

  @override
  String get transferInProgress => 'النقل جارٍ...';

  @override
  String get shareRecording => 'مشاركة التسجيل';

  @override
  String get deleteRecordingConfirmation =>
      'هل أنت متأكد من رغبتك في حذف هذا التسجيل نهائياً؟ لا يمكن التراجع عن هذا الإجراء.';

  @override
  String get recordingIdLabel => 'معرّف التسجيل';

  @override
  String get dateTimeLabel => 'التاريخ والوقت';

  @override
  String get durationLabel => 'المدة';

  @override
  String get audioFormatLabel => 'صيغة الصوت';

  @override
  String get storageLocationLabel => 'موقع التخزين';

  @override
  String get estimatedSizeLabel => 'الحجم التقديري';

  @override
  String get deviceModelLabel => 'طراز الجهاز';

  @override
  String get deviceIdLabel => 'معرّف الجهاز';

  @override
  String get statusLabel => 'الحالة';

  @override
  String get statusProcessed => 'تمت المعالجة';

  @override
  String get statusUnprocessed => 'لم تتم المعالجة';

  @override
  String get switchedToFastTransfer => 'تم التبديل إلى النقل السريع';

  @override
  String get transferCompleteMessage => 'اكتمل النقل! يمكنك الآن تشغيل هذا التسجيل.';

  @override
  String transferFailedMessage(String error) {
    return 'فشل النقل: $error';
  }

  @override
  String get transferCancelled => 'تم إلغاء النقل';

  @override
  String get fastTransferEnabled => 'تم تفعيل النقل السريع';

  @override
  String get bluetoothSyncEnabled => 'تم تفعيل مزامنة البلوتوث';

  @override
  String get enableFastTransfer => 'تفعيل النقل السريع';

  @override
  String get fastTransferDescription =>
      'يستخدم النقل السريع شبكة WiFi للحصول على سرعات أسرع بـ 5 مرات. سيتصل هاتفك مؤقتًا بشبكة WiFi الخاصة بجهاز Omi أثناء النقل.';

  @override
  String get internetAccessPausedDuringTransfer => 'يتم إيقاف الوصول إلى الإنترنت أثناء النقل';

  @override
  String get chooseTransferMethodDescription => 'اختر كيفية نقل التسجيلات من جهاز Omi إلى هاتفك.';

  @override
  String get wifiSpeed => '~150 كيلوبايت/ثانية عبر WiFi';

  @override
  String get fiveTimesFaster => 'أسرع 5 مرات';

  @override
  String get fastTransferMethodDescription =>
      'ينشئ اتصال WiFi مباشر بجهاز Omi. يتم فصل هاتفك مؤقتًا عن شبكة WiFi العادية أثناء النقل.';

  @override
  String get bluetooth => 'بلوتوث';

  @override
  String get bleSpeed => '~30 كيلوبايت/ثانية عبر BLE';

  @override
  String get bluetoothMethodDescription =>
      'يستخدم اتصال Bluetooth منخفض الطاقة القياسي. أبطأ لكنه لا يؤثر على اتصال WiFi.';

  @override
  String get selected => 'محدد';

  @override
  String get selectOption => 'اختر';

  @override
  String get lowBatteryAlertTitle => 'تنبيه انخفاض البطارية';

  @override
  String get lowBatteryAlertBody => 'بطارية جهازك منخفضة. حان وقت إعادة الشحن! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'تم قطع اتصال جهاز Omi';

  @override
  String get deviceDisconnectedNotificationBody => 'يرجى إعادة الاتصال لمتابعة استخدام Omi.';

  @override
  String get firmwareUpdateAvailable => 'تحديث البرنامج الثابت متاح';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'تحديث جديد للبرنامج الثابت ($version) متاح لجهاز Omi الخاص بك. هل تريد التحديث الآن؟';
  }

  @override
  String get later => 'لاحقاً';

  @override
  String get appDeletedSuccessfully => 'تم حذف التطبيق بنجاح';

  @override
  String get appDeleteFailed => 'فشل في حذف التطبيق. يرجى المحاولة مرة أخرى لاحقًا.';

  @override
  String get appVisibilityChangedSuccessfully => 'تم تغيير إعدادات الرؤية للتطبيق بنجاح. قد يستغرق الأمر بضع دقائق.';

  @override
  String get errorActivatingAppIntegration =>
      'حدث خطأ أثناء تفعيل التطبيق. إذا كان تطبيق تكامل، تأكد من اكتمال الإعداد.';

  @override
  String get errorUpdatingAppStatus => 'حدث خطأ أثناء تحديث حالة التطبيق.';

  @override
  String get calculatingETA => 'جارٍ الحساب...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'تبقى حوالي $minutes دقيقة';
  }

  @override
  String get aboutAMinuteRemaining => 'تبقى حوالي دقيقة واحدة';

  @override
  String get almostDone => 'على وشك الانتهاء...';

  @override
  String get omiSays => 'يقول Omi';

  @override
  String get analyzingYourData => 'جارٍ تحليل بياناتك...';

  @override
  String migratingToProtection(String level) {
    return 'جارٍ الترحيل إلى حماية $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'لا توجد بيانات للترحيل. جارٍ الإنهاء...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'جارٍ ترحيل $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'تم ترحيل جميع العناصر. جارٍ الإنهاء...';

  @override
  String get migrationErrorOccurred => 'حدث خطأ أثناء الترحيل. يرجى المحاولة مرة أخرى.';

  @override
  String get migrationComplete => 'اكتملت عملية الترحيل!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'بياناتك الآن محمية بإعدادات $level الجديدة.';
  }

  @override
  String get chatsLowercase => 'محادثات';

  @override
  String get dataLowercase => 'بيانات';

  @override
  String get fallNotificationTitle => 'آوه';

  @override
  String get fallNotificationBody => 'هل سقطت؟';

  @override
  String get importantConversationTitle => 'محادثة مهمة';

  @override
  String get importantConversationBody => 'لقد أجريت للتو محادثة مهمة. انقر لمشاركة الملخص مع الآخرين.';

  @override
  String get templateName => 'اسم القالب';

  @override
  String get templateNameHint => 'مثال: مستخرج إجراءات الاجتماع';

  @override
  String get nameMustBeAtLeast3Characters => 'يجب أن يكون الاسم 3 أحرف على الأقل';

  @override
  String get conversationPromptHint =>
      'مثال: استخراج عناصر الإجراءات والقرارات المتخذة والنقاط الرئيسية من المحادثة المقدمة.';

  @override
  String get pleaseEnterAppPrompt => 'يرجى إدخال موجه لتطبيقك';

  @override
  String get promptMustBeAtLeast10Characters => 'يجب أن يكون الموجه 10 أحرف على الأقل';

  @override
  String get anyoneCanDiscoverTemplate => 'يمكن لأي شخص اكتشاف قالبك';

  @override
  String get onlyYouCanUseTemplate => 'أنت فقط يمكنك استخدام هذا القالب';

  @override
  String get generatingDescription => 'جارٍ إنشاء الوصف...';

  @override
  String get creatingAppIcon => 'جارٍ إنشاء أيقونة التطبيق...';

  @override
  String get installingApp => 'جارٍ تثبيت التطبيق...';

  @override
  String get appCreatedAndInstalled => 'تم إنشاء التطبيق وتثبيته!';

  @override
  String get appCreatedSuccessfully => 'تم إنشاء التطبيق بنجاح!';

  @override
  String get failedToCreateApp => 'فشل إنشاء التطبيق. يرجى المحاولة مرة أخرى.';

  @override
  String get addAppSelectCoreCapability => 'يرجى تحديد قدرة أساسية أخرى لتطبيقك';

  @override
  String get addAppSelectPaymentPlan => 'يرجى تحديد خطة الدفع وإدخال سعر لتطبيقك';

  @override
  String get addAppSelectCapability => 'يرجى تحديد قدرة واحدة على الأقل لتطبيقك';

  @override
  String get addAppSelectLogo => 'يرجى تحديد شعار لتطبيقك';

  @override
  String get addAppEnterChatPrompt => 'يرجى إدخال موجه المحادثة لتطبيقك';

  @override
  String get addAppEnterConversationPrompt => 'يرجى إدخال موجه المحادثة لتطبيقك';

  @override
  String get addAppSelectTriggerEvent => 'يرجى تحديد حدث التشغيل لتطبيقك';

  @override
  String get addAppEnterWebhookUrl => 'يرجى إدخال عنوان URL للويب هوك لتطبيقك';

  @override
  String get addAppSelectCategory => 'يرجى تحديد فئة لتطبيقك';

  @override
  String get addAppFillRequiredFields => 'يرجى ملء جميع الحقول المطلوبة بشكل صحيح';

  @override
  String get addAppUpdatedSuccess => 'تم تحديث التطبيق بنجاح 🚀';

  @override
  String get addAppUpdateFailed => 'فشل التحديث. يرجى المحاولة لاحقاً';

  @override
  String get addAppSubmittedSuccess => 'تم إرسال التطبيق بنجاح 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'خطأ في فتح منتقي الملفات: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'خطأ في اختيار الصورة: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'تم رفض إذن الصور. يرجى السماح بالوصول إلى الصور';

  @override
  String get addAppErrorSelectingImageRetry => 'خطأ في اختيار الصورة. يرجى المحاولة مرة أخرى.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'خطأ في اختيار الصورة المصغرة: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'خطأ في اختيار الصورة المصغرة. يرجى المحاولة مرة أخرى.';

  @override
  String get addAppCapabilityConflictWithPersona => 'لا يمكن تحديد قدرات أخرى مع الشخصية';

  @override
  String get addAppPersonaConflictWithCapabilities => 'لا يمكن تحديد الشخصية مع قدرات أخرى';

  @override
  String get personaTwitterHandleNotFound => 'لم يتم العثور على حساب تويتر';

  @override
  String get personaTwitterHandleSuspended => 'حساب تويتر معلق';

  @override
  String get personaFailedToVerifyTwitter => 'فشل التحقق من حساب تويتر';

  @override
  String get personaFailedToFetch => 'فشل في جلب شخصيتك';

  @override
  String get personaFailedToCreate => 'فشل في إنشاء شخصيتك';

  @override
  String get personaConnectKnowledgeSource => 'يرجى ربط مصدر بيانات واحد على الأقل (Omi أو Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'تم تحديث الشخصية بنجاح';

  @override
  String get personaFailedToUpdate => 'فشل تحديث الشخصية';

  @override
  String get personaPleaseSelectImage => 'يرجى اختيار صورة';

  @override
  String get personaFailedToCreateTryLater => 'فشل إنشاء الشخصية. يرجى المحاولة لاحقاً.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'فشل إنشاء الشخصية: $error';
  }

  @override
  String get personaFailedToEnable => 'فشل تفعيل الشخصية';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'خطأ في تفعيل الشخصية: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'فشل في جلب البلدان المدعومة. يرجى المحاولة لاحقاً.';

  @override
  String get paymentFailedToSetDefault => 'فشل في تعيين طريقة الدفع الافتراضية. يرجى المحاولة لاحقاً.';

  @override
  String get paymentFailedToSavePaypal => 'فشل في حفظ تفاصيل PayPal. يرجى المحاولة لاحقاً.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'نشط';

  @override
  String get paymentStatusConnected => 'متصل';

  @override
  String get paymentStatusNotConnected => 'غير متصل';

  @override
  String get paymentAppCost => 'تكلفة التطبيق';

  @override
  String get paymentEnterValidAmount => 'يرجى إدخال مبلغ صالح';

  @override
  String get paymentEnterAmountGreaterThanZero => 'يرجى إدخال مبلغ أكبر من 0';

  @override
  String get paymentPlan => 'خطة الدفع';

  @override
  String get paymentNoneSelected => 'لم يتم التحديد';

  @override
  String get aiGenPleaseEnterDescription => 'يرجى إدخال وصف لتطبيقك';

  @override
  String get aiGenCreatingAppIcon => 'جارٍ إنشاء أيقونة التطبيق...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'حدث خطأ: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'تم إنشاء التطبيق بنجاح!';

  @override
  String get aiGenFailedToCreateApp => 'فشل في إنشاء التطبيق';

  @override
  String get aiGenErrorWhileCreatingApp => 'حدث خطأ أثناء إنشاء التطبيق';

  @override
  String get aiGenFailedToGenerateApp => 'فشل في إنشاء التطبيق. يرجى المحاولة مرة أخرى.';

  @override
  String get aiGenFailedToRegenerateIcon => 'فشل في إعادة إنشاء الأيقونة';

  @override
  String get aiGenPleaseGenerateAppFirst => 'يرجى إنشاء تطبيق أولاً';

  @override
  String get xHandleTitle => 'ما هو معرف X الخاص بك؟';

  @override
  String get xHandleDescription => 'سنقوم بتدريب نسخة Omi الخاصة بك مسبقاً\nبناءً على نشاط حسابك.';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'يرجى إدخال معرف X الخاص بك';

  @override
  String get xHandlePleaseEnterValid => 'يرجى إدخال معرف X صالح';

  @override
  String get nextButton => 'التالي';

  @override
  String get connectOmiDevice => 'ربط جهاز Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'أنت تقوم بتغيير خطتك غير المحدودة إلى $title. هل أنت متأكد؟';
  }

  @override
  String get planUpgradeScheduledMessage => 'تمت جدولة الترقية! تستمر خطتك الشهرية حتى نهاية فترة الفوترة الحالية.';

  @override
  String get couldNotSchedulePlanChange => 'تعذر جدولة تغيير الخطة. يرجى المحاولة مرة أخرى.';

  @override
  String get subscriptionReactivatedDefault =>
      'تم إعادة تفعيل اشتراكك! لا توجد رسوم الآن - ستستمر في الاستمتاع بالميزات المميزة.';

  @override
  String get subscriptionSuccessfulCharged => 'تم الاشتراك بنجاح! تم خصم المبلغ لفترة الفوترة الجديدة.';

  @override
  String get couldNotProcessSubscription => 'تعذرت معالجة الاشتراك. يرجى المحاولة مرة أخرى.';

  @override
  String get couldNotLaunchUpgradePage => 'تعذر فتح صفحة الترقية. يرجى المحاولة مرة أخرى.';

  @override
  String get transcriptionJsonPlaceholder => 'الصق إعدادات JSON الخاصة بك هنا...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'خطأ في فتح منتقي الملفات: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'خطأ: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'تم دمج المحادثات بنجاح';

  @override
  String mergeConversationsSuccessBody(int count) {
    return 'تم دمج $count محادثات بنجاح';
  }

  @override
  String get dailyReflectionNotificationTitle => 'حان وقت التأمل اليومي';

  @override
  String get dailyReflectionNotificationBody => 'أخبرني عن يومك';

  @override
  String get actionItemReminderTitle => 'تذكير Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName غير متصل';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'يرجى إعادة الاتصال لمواصلة استخدام $deviceName الخاص بك.';
  }

  @override
  String get onboardingSignIn => 'تسجيل الدخول';

  @override
  String get onboardingYourName => 'اسمك';

  @override
  String get onboardingLanguage => 'اللغة';

  @override
  String get onboardingPermissions => 'الأذونات';

  @override
  String get onboardingComplete => 'اكتمل';

  @override
  String get onboardingWelcomeToOmi => 'مرحبًا بك في Omi';

  @override
  String get onboardingTellUsAboutYourself => 'أخبرنا عن نفسك';

  @override
  String get onboardingChooseYourPreference => 'اختر تفضيلاتك';

  @override
  String get onboardingGrantRequiredAccess => 'منح الوصول المطلوب';

  @override
  String get onboardingYoureAllSet => 'أنت جاهز';

  @override
  String get searchTranscriptOrSummary => 'ابحث في النص أو الملخص...';

  @override
  String get myGoal => 'هدفي';

  @override
  String get appNotAvailable => 'عفواً! يبدو أن التطبيق الذي تبحث عنه غير متوفر.';

  @override
  String get failedToConnectTodoist => 'فشل الاتصال بـ Todoist';

  @override
  String get failedToConnectAsana => 'فشل الاتصال بـ Asana';

  @override
  String get failedToConnectGoogleTasks => 'فشل الاتصال بـ Google Tasks';

  @override
  String get failedToConnectClickUp => 'فشل الاتصال بـ ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'فشل الاتصال بـ $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'تم الاتصال بـ Todoist بنجاح!';

  @override
  String get failedToConnectTodoistRetry => 'فشل الاتصال بـ Todoist. يرجى المحاولة مرة أخرى.';

  @override
  String get successfullyConnectedAsana => 'تم الاتصال بـ Asana بنجاح!';

  @override
  String get failedToConnectAsanaRetry => 'فشل الاتصال بـ Asana. يرجى المحاولة مرة أخرى.';

  @override
  String get successfullyConnectedGoogleTasks => 'تم الاتصال بـ Google Tasks بنجاح!';

  @override
  String get failedToConnectGoogleTasksRetry => 'فشل الاتصال بـ Google Tasks. يرجى المحاولة مرة أخرى.';

  @override
  String get successfullyConnectedClickUp => 'تم الاتصال بـ ClickUp بنجاح!';

  @override
  String get failedToConnectClickUpRetry => 'فشل الاتصال بـ ClickUp. يرجى المحاولة مرة أخرى.';

  @override
  String get successfullyConnectedNotion => 'تم الاتصال بـ Notion بنجاح!';

  @override
  String get failedToRefreshNotionStatus => 'فشل تحديث حالة اتصال Notion.';

  @override
  String get successfullyConnectedGoogle => 'تم الاتصال بـ Google بنجاح!';

  @override
  String get failedToRefreshGoogleStatus => 'فشل تحديث حالة اتصال Google.';

  @override
  String get successfullyConnectedWhoop => 'تم الاتصال بـ Whoop بنجاح!';

  @override
  String get failedToRefreshWhoopStatus => 'فشل تحديث حالة اتصال Whoop.';

  @override
  String get successfullyConnectedGitHub => 'تم الاتصال بـ GitHub بنجاح!';

  @override
  String get failedToRefreshGitHubStatus => 'فشل تحديث حالة اتصال GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'فشل تسجيل الدخول باستخدام Google، يرجى المحاولة مرة أخرى.';

  @override
  String get authenticationFailed => 'فشلت المصادقة. يرجى المحاولة مرة أخرى.';

  @override
  String get authFailedToSignInWithApple => 'فشل تسجيل الدخول باستخدام Apple، يرجى المحاولة مرة أخرى.';

  @override
  String get authFailedToRetrieveToken => 'فشل استرداد رمز Firebase، يرجى المحاولة مرة أخرى.';

  @override
  String get authUnexpectedErrorFirebase =>
      'خطأ غير متوقع أثناء تسجيل الدخول، خطأ في Firebase، يرجى المحاولة مرة أخرى.';

  @override
  String get authUnexpectedError => 'خطأ غير متوقع أثناء تسجيل الدخول، يرجى المحاولة مرة أخرى';

  @override
  String get authFailedToLinkGoogle => 'فشل الربط بحساب Google، يرجى المحاولة مرة أخرى.';

  @override
  String get authFailedToLinkApple => 'فشل الربط بحساب Apple، يرجى المحاولة مرة أخرى.';

  @override
  String get onboardingBluetoothRequired => 'يتطلب إذن البلوتوث للاتصال بجهازك.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs => 'تم رفض إذن البلوتوث. يرجى منح الإذن في تفضيلات النظام.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'حالة إذن البلوتوث: $status. يرجى التحقق من تفضيلات النظام.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'فشل التحقق من إذن البلوتوث: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs => 'تم رفض إذن الإشعارات. يرجى منح الإذن في تفضيلات النظام.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'تم رفض إذن الإشعارات. يرجى منح الإذن في تفضيلات النظام > الإشعارات.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'حالة إذن الإشعارات: $status. يرجى التحقق من تفضيلات النظام.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'فشل التحقق من إذن الإشعارات: $error';
  }

  @override
  String get onboardingLocationGrantInSettings => 'يرجى منح إذن الموقع في الإعدادات > الخصوصية والأمان > خدمات الموقع';

  @override
  String get onboardingMicrophoneRequired => 'يتطلب إذن الميكروفون للتسجيل.';

  @override
  String get onboardingMicrophoneDenied =>
      'تم رفض إذن الميكروفون. يرجى منح الإذن في تفضيلات النظام > الخصوصية والأمان > الميكروفون.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'حالة إذن الميكروفون: $status. يرجى التحقق من تفضيلات النظام.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'فشل التحقق من إذن الميكروفون: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'يتطلب إذن التقاط الشاشة لتسجيل صوت النظام.';

  @override
  String get onboardingScreenCaptureDenied =>
      'تم رفض إذن التقاط الشاشة. يرجى منح الإذن في تفضيلات النظام > الخصوصية والأمان > تسجيل الشاشة.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'حالة إذن التقاط الشاشة: $status. يرجى التحقق من تفضيلات النظام.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'فشل التحقق من إذن التقاط الشاشة: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'يتطلب إذن إمكانية الوصول لاكتشاف اجتماعات المتصفح.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'حالة إذن إمكانية الوصول: $status. يرجى التحقق من تفضيلات النظام.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'فشل التحقق من إذن إمكانية الوصول: $error';
  }

  @override
  String get msgCameraNotAvailable => 'التقاط الكاميرا غير متاح على هذه المنصة';

  @override
  String get msgCameraPermissionDenied => 'تم رفض إذن الكاميرا. يرجى السماح بالوصول إلى الكاميرا';

  @override
  String msgCameraAccessError(String error) {
    return 'خطأ في الوصول إلى الكاميرا: $error';
  }

  @override
  String get msgPhotoError => 'خطأ في التقاط الصورة. يرجى المحاولة مرة أخرى.';

  @override
  String get msgMaxImagesLimit => 'يمكنك اختيار 4 صور كحد أقصى';

  @override
  String msgFilePickerError(String error) {
    return 'خطأ في فتح منتقي الملفات: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'خطأ في اختيار الصور: $error';
  }

  @override
  String get msgPhotosPermissionDenied => 'تم رفض إذن الصور. يرجى السماح بالوصول إلى الصور لاختيار الصور';

  @override
  String get msgSelectImagesGenericError => 'خطأ في اختيار الصور. يرجى المحاولة مرة أخرى.';

  @override
  String get msgMaxFilesLimit => 'يمكنك اختيار 4 ملفات كحد أقصى';

  @override
  String msgSelectFilesError(String error) {
    return 'خطأ في اختيار الملفات: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'خطأ في اختيار الملفات. يرجى المحاولة مرة أخرى.';

  @override
  String get msgUploadFileFailed => 'فشل تحميل الملف، يرجى المحاولة مرة أخرى لاحقاً';

  @override
  String get msgReadingMemories => 'جارٍ قراءة ذكرياتك...';

  @override
  String get msgLearningMemories => 'جارٍ التعلم من ذكرياتك...';

  @override
  String get msgUploadAttachedFileFailed => 'فشل تحميل الملف المرفق.';

  @override
  String captureRecordingError(String error) {
    return 'حدث خطأ أثناء التسجيل: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'توقف التسجيل: $reason. قد تحتاج إلى إعادة توصيل الشاشات الخارجية أو إعادة بدء التسجيل.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'إذن الميكروفون مطلوب';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'منح إذن الميكروفون في تفضيلات النظام';

  @override
  String get captureScreenRecordingPermissionRequired => 'إذن تسجيل الشاشة مطلوب';

  @override
  String get captureDisplayDetectionFailed => 'فشل اكتشاف الشاشة. توقف التسجيل.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'عنوان URL للويب هوك لبايتات الصوت غير صالح';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'عنوان URL للويب هوك للنص الفوري غير صالح';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'عنوان URL للويب هوك لإنشاء المحادثة غير صالح';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'عنوان URL للويب هوك لملخص اليوم غير صالح';

  @override
  String get devModeSettingsSaved => 'تم حفظ الإعدادات!';

  @override
  String get voiceFailedToTranscribe => 'فشل في نسخ الصوت';

  @override
  String get locationPermissionRequired => 'إذن الموقع مطلوب';

  @override
  String get locationPermissionContent =>
      'يتطلب النقل السريع إذن الموقع للتحقق من اتصال WiFi. يرجى منح إذن الموقع للمتابعة.';

  @override
  String get pdfTranscriptExport => 'تصدير النص';

  @override
  String get pdfConversationExport => 'تصدير المحادثة';

  @override
  String pdfTitleLabel(String title) {
    return 'العنوان: $title';
  }

  @override
  String get conversationNewIndicator => 'جديد 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count صور';
  }

  @override
  String get mergingStatus => 'جارٍ الدمج...';

  @override
  String timeSecsSingular(int count) {
    return '$count ثانية';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count ثوانٍ';
  }

  @override
  String timeMinSingular(int count) {
    return '$count دقيقة';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count دقائق';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins دقائق $secs ثوانٍ';
  }

  @override
  String timeHourSingular(int count) {
    return '$count ساعة';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count ساعات';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours ساعات $mins دقائق';
  }

  @override
  String timeDaySingular(int count) {
    return '$count يوم';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count أيام';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days أيام $hours ساعات';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countث';
  }

  @override
  String timeCompactMins(int count) {
    return '$countد';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsد $secsث';
  }

  @override
  String timeCompactHours(int count) {
    return '$countس';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursس $minsد';
  }

  @override
  String get moveToFolder => 'نقل إلى المجلد';

  @override
  String get noFoldersAvailable => 'لا توجد مجلدات متاحة';

  @override
  String get newFolder => 'مجلد جديد';

  @override
  String get color => 'اللون';

  @override
  String get waitingForDevice => 'في انتظار الجهاز...';

  @override
  String get saySomething => 'قل شيئاً...';

  @override
  String get initialisingSystemAudio => 'جارٍ تهيئة صوت النظام';

  @override
  String get stopRecording => 'إيقاف التسجيل';

  @override
  String get continueRecording => 'متابعة التسجيل';

  @override
  String get initialisingRecorder => 'جارٍ تهيئة المسجل';

  @override
  String get pauseRecording => 'إيقاف التسجيل مؤقتاً';

  @override
  String get resumeRecording => 'استئناف التسجيل';

  @override
  String get noDailyRecapsYet => 'لا توجد ملخصات يومية بعد';

  @override
  String get dailyRecapsDescription => 'ستظهر ملخصاتك اليومية هنا بمجرد إنشائها';

  @override
  String get chooseTransferMethod => 'اختر طريقة النقل';

  @override
  String get fastTransferSpeed => '~150 كيلوبايت/ثانية عبر WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'تم اكتشاف فجوة زمنية كبيرة ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'تم اكتشاف فجوات زمنية كبيرة ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'الجهاز لا يدعم مزامنة WiFi، التبديل إلى البلوتوث';

  @override
  String get appleHealthNotAvailable => 'Apple Health غير متاح على هذا الجهاز';

  @override
  String get downloadAudio => 'تنزيل الصوت';

  @override
  String get audioDownloadSuccess => 'تم تنزيل الصوت بنجاح';

  @override
  String get audioDownloadFailed => 'فشل تنزيل الصوت';

  @override
  String get downloadingAudio => 'جاري تنزيل الصوت...';

  @override
  String get shareAudio => 'مشاركة الصوت';

  @override
  String get preparingAudio => 'جاري تحضير الصوت';

  @override
  String get gettingAudioFiles => 'جاري الحصول على ملفات الصوت...';

  @override
  String get downloadingAudioProgress => 'جاري تنزيل الصوت';

  @override
  String get processingAudio => 'جاري معالجة الصوت';

  @override
  String get combiningAudioFiles => 'جاري دمج ملفات الصوت...';

  @override
  String get audioReady => 'الصوت جاهز';

  @override
  String get openingShareSheet => 'جاري فتح صفحة المشاركة...';

  @override
  String get audioShareFailed => 'فشلت المشاركة';

  @override
  String get dailyRecaps => 'الملخصات اليومية';

  @override
  String get removeFilter => 'إزالة الفلتر';

  @override
  String get categoryConversationAnalysis => 'تحليل المحادثة';

  @override
  String get categoryPersonalityClone => 'استنساخ الشخصية';

  @override
  String get categoryHealth => 'الصحة';

  @override
  String get categoryEducation => 'التعليم';

  @override
  String get categoryCommunication => 'التواصل';

  @override
  String get categoryEmotionalSupport => 'الدعم العاطفي';

  @override
  String get categoryProductivity => 'الإنتاجية';

  @override
  String get categoryEntertainment => 'الترفيه';

  @override
  String get categoryFinancial => 'المالية';

  @override
  String get categoryTravel => 'السفر';

  @override
  String get categorySafety => 'الأمان';

  @override
  String get categoryShopping => 'التسوق';

  @override
  String get categorySocial => 'اجتماعي';

  @override
  String get categoryNews => 'الأخبار';

  @override
  String get categoryUtilities => 'الأدوات';

  @override
  String get categoryOther => 'أخرى';

  @override
  String get capabilityChat => 'الدردشة';

  @override
  String get capabilityConversations => 'المحادثات';

  @override
  String get capabilityExternalIntegration => 'التكامل الخارجي';

  @override
  String get capabilityNotification => 'الإشعارات';

  @override
  String get triggerAudioBytes => 'بايتات الصوت';

  @override
  String get triggerConversationCreation => 'إنشاء المحادثة';

  @override
  String get triggerTranscriptProcessed => 'معالجة النص';

  @override
  String get actionCreateConversations => 'إنشاء المحادثات';

  @override
  String get actionCreateMemories => 'إنشاء الذكريات';

  @override
  String get actionReadConversations => 'قراءة المحادثات';

  @override
  String get actionReadMemories => 'قراءة الذكريات';

  @override
  String get actionReadTasks => 'قراءة المهام';

  @override
  String get scopeUserName => 'اسم المستخدم';

  @override
  String get scopeUserFacts => 'معلومات المستخدم';

  @override
  String get scopeUserConversations => 'محادثات المستخدم';

  @override
  String get scopeUserChat => 'دردشة المستخدم';

  @override
  String get capabilitySummary => 'الملخص';

  @override
  String get capabilityFeatured => 'المميزة';

  @override
  String get capabilityTasks => 'المهام';

  @override
  String get capabilityIntegrations => 'التكاملات';

  @override
  String get categoryPersonalityClones => 'استنساخ الشخصيات';

  @override
  String get categoryProductivityLifestyle => 'الإنتاجية ونمط الحياة';

  @override
  String get categorySocialEntertainment => 'التواصل والترفيه';

  @override
  String get categoryProductivityTools => 'أدوات الإنتاجية';

  @override
  String get categoryPersonalWellness => 'الصحة الشخصية';

  @override
  String get rating => 'التقييم';

  @override
  String get categories => 'الفئات';

  @override
  String get sortBy => 'ترتيب';

  @override
  String get highestRating => 'الأعلى تقييماً';

  @override
  String get lowestRating => 'الأقل تقييماً';

  @override
  String get resetFilters => 'إعادة تعيين الفلاتر';

  @override
  String get applyFilters => 'تطبيق الفلاتر';

  @override
  String get mostInstalls => 'الأكثر تثبيتاً';

  @override
  String get couldNotOpenUrl => 'تعذر فتح الرابط. يرجى المحاولة مرة أخرى.';

  @override
  String get newTask => 'مهمة جديدة';

  @override
  String get viewAll => 'عرض الكل';

  @override
  String get addTask => 'إضافة مهمة';

  @override
  String get addMcpServer => 'Add MCP Server';

  @override
  String get connectExternalAiTools => 'Connect external AI tools';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return '$count tools connected successfully';
  }

  @override
  String get mcpConnectionFailed => 'Failed to connect to MCP server';

  @override
  String get authorizingMcpServer => 'Authorizing...';

  @override
  String get whereDidYouHearAboutOmi => 'How did you find us?';

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
  String get friendWordOfMouth => 'Friend';

  @override
  String get otherSource => 'Other';

  @override
  String get pleaseSpecify => 'Please specify';

  @override
  String get event => 'Event';

  @override
  String get coworker => 'Coworker';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'ملف الصوت غير متاح للتشغيل';

  @override
  String get audioPlaybackFailed => 'تعذر تشغيل الصوت. قد يكون الملف تالفًا أو مفقودًا.';

  @override
  String get connectionGuide => 'دليل الاتصال';

  @override
  String get iveDoneThis => 'لقد فعلت هذا';

  @override
  String get pairNewDevice => 'إقران جهاز جديد';

  @override
  String get dontSeeYourDevice => 'لا ترى جهازك؟';

  @override
  String get reportAnIssue => 'الإبلاغ عن مشكلة';

  @override
  String get pairingTitleOmi => 'تشغيل Omi';

  @override
  String get pairingDescOmi => 'اضغط مع الاستمرار على الجهاز حتى يهتز لتشغيله.';

  @override
  String get pairingTitleOmiDevkit => 'ضع Omi DevKit في وضع الإقران';

  @override
  String get pairingDescOmiDevkit => 'اضغط على الزر مرة واحدة للتشغيل. سيومض مؤشر LED باللون الأرجواني في وضع الإقران.';

  @override
  String get pairingTitleOmiGlass => 'تشغيل Omi Glass';

  @override
  String get pairingDescOmiGlass => 'اضغط مع الاستمرار على الزر الجانبي لمدة 3 ثوانٍ لتشغيل الجهاز.';

  @override
  String get pairingTitlePlaudNote => 'ضع Plaud Note في وضع الإقران';

  @override
  String get pairingDescPlaudNote =>
      'اضغط مع الاستمرار على الزر الجانبي لمدة ثانيتين. سيومض مؤشر LED الأحمر عندما يكون جاهزًا للإقران.';

  @override
  String get pairingTitleBee => 'ضع Bee في وضع الإقران';

  @override
  String get pairingDescBee => 'اضغط على الزر 5 مرات متتالية. سيبدأ الضوء بالوميض بالأزرق والأخضر.';

  @override
  String get pairingTitleLimitless => 'ضع Limitless في وضع الإقران';

  @override
  String get pairingDescLimitless =>
      'عندما يكون أي ضوء مرئيًا، اضغط مرة واحدة ثم اضغط مع الاستمرار حتى يظهر الجهاز ضوءًا ورديًا، ثم حرر.';

  @override
  String get pairingTitleFriendPendant => 'ضع Friend Pendant في وضع الإقران';

  @override
  String get pairingDescFriendPendant => 'اضغط على الزر الموجود على القلادة لتشغيلها. ستدخل وضع الإقران تلقائيًا.';

  @override
  String get pairingTitleFieldy => 'ضع Fieldy في وضع الإقران';

  @override
  String get pairingDescFieldy => 'اضغط مع الاستمرار على الجهاز حتى يظهر الضوء لتشغيله.';

  @override
  String get pairingTitleAppleWatch => 'توصيل Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'قم بتثبيت وفتح تطبيق Omi على Apple Watch الخاص بك، ثم اضغط على اتصال في التطبيق.';

  @override
  String get pairingTitleNeoOne => 'ضع Neo One في وضع الإقران';

  @override
  String get pairingDescNeoOne => 'اضغط مع الاستمرار على زر الطاقة حتى يومض مؤشر LED. سيكون الجهاز قابلاً للاكتشاف.';
}
