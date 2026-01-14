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
  String get copyTranscript => 'نسخ النص المكتوب';

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
  String get noStarredConversations => 'لا توجد محادثات مميزة بنجمة بعد.';

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
  String get deletingMessages => 'جاري حذف رسائلك من ذاكرة Omi...';

  @override
  String get messageCopied => 'تم نسخ الرسالة إلى الحافظة.';

  @override
  String get cannotReportOwnMessage => 'لا يمكنك الإبلاغ عن رسائلك الخاصة.';

  @override
  String get reportMessage => 'الإبلاغ عن رسالة';

  @override
  String get reportMessageConfirm => 'هل أنت متأكد من رغبتك في الإبلاغ عن هذه الرسالة؟';

  @override
  String get messageReported => 'تم الإبلاغ عن الرسالة بنجاح.';

  @override
  String get thankYouFeedback => 'شكراً لك على ملاحظاتك!';

  @override
  String get clearChat => 'مسح المحادثة؟';

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
  String get aboutOmi => 'عن Omi';

  @override
  String get privacyPolicy => 'سياسة الخصوصية';

  @override
  String get visitWebsite => 'زيارة الموقع';

  @override
  String get helpOrInquiries => 'مساعدة أو استفسارات؟';

  @override
  String get joinCommunity => 'انضم إلى المجتمع!';

  @override
  String get membersAndCounting => 'أكثر من 8000 عضو وما زال العدد في ازدياد.';

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
  String get identifyingOthers => 'التعرف على الآخرين';

  @override
  String get paymentMethods => 'طرق الدفع';

  @override
  String get conversationDisplay => 'عرض المحادثة';

  @override
  String get dataPrivacy => 'البيانات والخصوصية';

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
  String get chatTools => 'أدوات الدردشة';

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
  String get off => 'متوقف';

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
  String get endpointUrl => 'عنوان URL للنقطة النهائية';

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
  String get noLogFilesFound => 'لم يتم العثور على ملفات سجل.';

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
  String get knowledgeGraphDeleted => 'تم حذف رسم المعرفة بنجاح';

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
  String get urlCopied => 'تم نسخ عنوان URL';

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
  String get webhooks => 'خطافات الويب';

  @override
  String get conversationEvents => 'أحداث المحادثة';

  @override
  String get newConversationCreated => 'تم إنشاء محادثة جديدة';

  @override
  String get realtimeTranscript => 'نص مباشر';

  @override
  String get transcriptReceived => 'تم استلام النسخ';

  @override
  String get audioBytes => 'بايتات الصوت';

  @override
  String get audioDataReceived => 'تم استلام بيانات الصوت';

  @override
  String get intervalSeconds => 'الفاصل الزمني (ثوان)';

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
  String get memories => 'ذكريات';

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
  String get visibility => 'الرؤية';

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
  String get connect => 'اتصال';

  @override
  String get comingSoon => 'قريباً';

  @override
  String get chatToolsFooter => 'قم بتوصيل تطبيقاتك لعرض البيانات والمقاييس في الدردشة.';

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
  String get noUpcomingMeetings => 'لم يتم العثور على اجتماعات قادمة';

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
  String get omiUnlimited => 'Omi Unlimited';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName يستخدم $codecReason. سيتم استخدام Omi.';
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
  String get appName => 'اسم التطبيق';

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
  String get makePublic => 'جعله عاماً';

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
  String get speechProfileIntro => 'يحتاج Omi إلى تعلم أهدافك وصوتك. ستتمكن من تعديله لاحقاً.';

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
  String get personalGrowthJourney => 'رحلة نموك الشخصية مع الذكاء الاصطناعي الذي يستمع إلى كل كلمة تقولها.';

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
  String searchMemories(int count) {
    return 'بحث في $count ذكرى';
  }

  @override
  String get memoryDeleted => 'تم حذف الذكرى.';

  @override
  String get undo => 'تراجع';

  @override
  String get noMemoriesYet => 'لا توجد ذكريات بعد';

  @override
  String get noAutoMemories => 'لا توجد ذكريات مستخرجة تلقائياً بعد';

  @override
  String get noManualMemories => 'لا توجد ذكريات يدوية بعد';

  @override
  String get noMemoriesInCategories => 'لا توجد ذكريات في هذه الفئات';

  @override
  String get noMemoriesFound => 'لم يتم العثور على ذكريات';

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
  String get noMemoriesToDelete => 'لا توجد ذكريات لحذفها';

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
  String get deleteAllMemories => 'حذف جميع الذكريات';

  @override
  String get allMemoriesPrivateResult => 'جميع الذكريات خاصة الآن';

  @override
  String get allMemoriesPublicResult => 'جميع الذكريات عامة الآن';

  @override
  String get newMemory => 'ذكرى جديدة';

  @override
  String get editMemory => 'تعديل الذكرى';

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
  String get selectText => 'اختر النص';

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
  String get descriptionOptional => 'الوصف (اختياري)';

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
  String get deleteMemory => 'حذف الذكرى؟';

  @override
  String get thisActionCannotBeUndone => 'لا يمكن التراجع عن هذا الإجراء.';

  @override
  String memoriesCount(int count) {
    return '$count ذكريات';
  }

  @override
  String get noMemoriesInCategory => 'لا توجد ذكريات في هذه الفئة بعد';

  @override
  String get addYourFirstMemory => 'أضف ذكرتك الأولى';

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
  String get unknownDevice => 'جهاز غير معروف';

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
  String get configureYourAiPersona => 'قم بتكوين شخصيتك الذكية';

  @override
  String get configureSttProvider => 'تكوين موفر STT';

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
  String get knowledgeGraphDeletedSuccess => 'تم حذف الرسم البياني للمعرفة بنجاح';

  @override
  String failedToDeleteGraph(String error) {
    return 'فشل حذف الرسم البياني: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'مسح جميع العقد والاتصالات';

  @override
  String get addToClaudeDesktopConfig => 'إضافة إلى claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'ربط مساعدي الذكاء الاصطناعي ببياناتك';

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
  String get dailyReflection => 'التفكير اليومي';

  @override
  String get get9PmReminderToReflect => 'احصل على تذكير في الساعة 9 مساءً للتفكير في يومك';

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
  String get pressKeys => 'اضغط على المفاتيح...';

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
  String get welcomeBack => 'مرحبا بعودتك';

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
  String get dailyScore => 'الدرجة اليومية';

  @override
  String get dailyScoreDescription => 'درجة لمساعدتك على التركيز بشكل أفضل على التنفيذ.';

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
  String installsCount(String count) {
    return '$count+ عملية تثبيت';
  }

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
  String get chatPersonality => 'شخصية الدردشة';

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
  String get installed => 'مثبّت';
}
