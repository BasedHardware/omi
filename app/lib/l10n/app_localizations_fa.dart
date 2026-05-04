// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Persian (`fa`).
class AppLocalizationsFa extends AppLocalizations {
  AppLocalizationsFa([String locale = 'fa']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'گفتگو';

  @override
  String get transcriptTab => 'متن مکالمه';

  @override
  String get actionItemsTab => 'موارد اقدام';

  @override
  String get deleteConversationTitle => 'حذف گفتگو؟';

  @override
  String get deleteConversationMessage =>
      'این عمل باعث حذف یادداشت‌های، وظایف و فایل‌های صوتی مرتبط نیز می‌شود. این عمل قابل بازگشت نیست.';

  @override
  String get confirm => 'تایید';

  @override
  String get cancel => 'لغو';

  @override
  String get ok => 'تایید';

  @override
  String get delete => 'حذف';

  @override
  String get add => 'افزودن';

  @override
  String get update => 'بروزرسانی';

  @override
  String get save => 'ذخیره';

  @override
  String get edit => 'ویرایش';

  @override
  String get close => 'بستن';

  @override
  String get clear => 'پاک کردن';

  @override
  String get copyTranscript => 'کپی متن مکالمه';

  @override
  String get copySummary => 'کپی خلاصه';

  @override
  String get testPrompt => 'تست موضوع';

  @override
  String get reprocessConversation => 'پردازش مجدد گفتگو';

  @override
  String get deleteConversation => 'حذف گفتگو';

  @override
  String get contentCopied => 'محتوا به تخته گذاشته شد';

  @override
  String get failedToUpdateStarred => 'ناتوان در به‌روزرسانی وضعیت ستاره.';

  @override
  String get conversationUrlNotShared => 'آدرس گفتگو قابل اشتراک‌گذاری نیست.';

  @override
  String get errorProcessingConversation => 'خطا در پردازش گفتگو. لطفاً بعداً دوباره تلاش کنید.';

  @override
  String get noInternetConnection => 'بدون اتصال اینترنت';

  @override
  String get unableToDeleteConversation => 'ناتوان در حذف گفتگو';

  @override
  String get somethingWentWrong => 'مشکلی پیش آمد! لطفاً بعداً دوباره تلاش کنید.';

  @override
  String get copyErrorMessage => 'کپی پیام خطا';

  @override
  String get errorCopied => 'پیام خطا به تخته گذاشته شد';

  @override
  String get remaining => 'باقی‌مانده';

  @override
  String get loading => 'درحال بارگذاری...';

  @override
  String get loadingDuration => 'درحال بارگذاری مدت‌زمان...';

  @override
  String secondsCount(int count) {
    return '$count ثانیه';
  }

  @override
  String get people => 'افراد';

  @override
  String get addNewPerson => 'افزودن فرد جدید';

  @override
  String get editPerson => 'ویرایش فرد';

  @override
  String get createPersonHint => 'فردی جدید ایجاد کنید و Omi را آموزش دهید تا صدای آن‌ها را نیز شناسایی کند!';

  @override
  String get speechProfile => 'پروفایل صوتی';

  @override
  String sampleNumber(int number) {
    return 'نمونه $number';
  }

  @override
  String get settings => 'تنظیمات';

  @override
  String get language => 'زبان';

  @override
  String get selectLanguage => 'انتخاب زبان';

  @override
  String get deleting => 'درحال حذف...';

  @override
  String get pleaseCompleteAuthentication =>
      'لطفاً احراز هویت را در مرورگر خود تکمیل کنید. پس از انجام، به اپلیکیشن بازگردید.';

  @override
  String get failedToStartAuthentication => 'ناتوان در شروع احراز هویت';

  @override
  String get importStarted => 'وارد کردن شروع شد! هنگام تکمیل به شما اطلاع داده خواهد شد.';

  @override
  String get failedToStartImport => 'ناتوان در شروع وارد کردن. لطفاً دوباره تلاش کنید.';

  @override
  String get couldNotAccessFile => 'ناتوان در دسترسی به فایل انتخاب‌شده';

  @override
  String get askOmi => 'از Omi بپرسید';

  @override
  String get done => 'انجام شد';

  @override
  String get disconnected => 'قطع‌شده';

  @override
  String get searching => 'درحال جستجو...';

  @override
  String get connectDevice => 'اتصال دستگاه';

  @override
  String get monthlyLimitReached => 'شما به حد ماهانه خود رسیده‌اید.';

  @override
  String get checkUsage => 'بررسی استفاده';

  @override
  String get syncingRecordings => 'درحال همگام‌سازی ضبط‌ها';

  @override
  String get recordingsToSync => 'ضبط‌هایی برای همگام‌سازی';

  @override
  String get allCaughtUp => 'همه چیز بروز است';

  @override
  String get sync => 'همگام‌سازی';

  @override
  String get pendantUpToDate => 'پنجره به‌روز است';

  @override
  String get allRecordingsSynced => 'تمام ضبط‌ها همگام‌سازی شده‌اند';

  @override
  String get syncingInProgress => 'همگام‌سازی درجریان است';

  @override
  String get readyToSync => 'آماده برای همگام‌سازی';

  @override
  String get tapSyncToStart => 'برای شروع روی دکمه همگام‌سازی ضربه بزنید';

  @override
  String get pendantNotConnected => 'پنجره متصل نیست. برای همگام‌سازی متصل کنید.';

  @override
  String get everythingSynced => 'همه چیز قبلاً همگام‌سازی شده است.';

  @override
  String get recordingsNotSynced => 'شما ضبط‌هایی دارید که هنوز همگام‌سازی نشده‌اند.';

  @override
  String get syncingBackground => 'ما ضبط‌های شما را در پس‌زمینه همگام‌سازی می‌کنیم.';

  @override
  String get noConversationsYet => 'هنوز گفتگویی وجود ندارد';

  @override
  String get noStarredConversations => 'گفتگوی ستاره‌دار وجود ندارد';

  @override
  String get starConversationHint => 'برای ستاره‌دار کردن گفتگو، آن را باز کنید و روی آیکن ستاره در سرصفحه ضربه بزنید.';

  @override
  String get searchConversations => 'جستجوی گفتگوها...';

  @override
  String selectedCount(int count, Object s) {
    return '$count انتخاب‌شده';
  }

  @override
  String get merge => 'ادغام';

  @override
  String get mergeConversations => 'ادغام گفتگوها';

  @override
  String mergeConversationsMessage(int count) {
    return 'این $count گفتگو را در یکی ادغام خواهد کرد. تمام محتوا ادغام و دوباره تولید خواهد شد.';
  }

  @override
  String get mergingInBackground => 'درحال ادغام در پس‌زمینه. این ممکن است کمی زمان ببرد.';

  @override
  String get failedToStartMerge => 'ناتوان در شروع ادغام';

  @override
  String get askAnything => 'هر چیزی بپرسید';

  @override
  String get noMessagesYet => 'هنوز پیامی وجود ندارد!\nچرا یک گفتگو شروع نمی‌کنید؟';

  @override
  String get deletingMessages => 'درحال حذف پیام‌های شما از حافظه Omi...';

  @override
  String get messageCopied => '✨ پیام به تخته گذاشته شد';

  @override
  String get cannotReportOwnMessage => 'نمی‌توانید پیام‌های خود را گزارش کنید.';

  @override
  String get reportMessage => 'گزارش پیام';

  @override
  String get reportMessageConfirm => 'آیا مطمئن هستید که می‌خواهید این پیام را گزارش کنید؟';

  @override
  String get messageReported => 'پیام با موفقیت گزارش شد.';

  @override
  String get thankYouFeedback => 'از نظر شما سپاسگزاریم!';

  @override
  String get clearChat => 'پاک کردن چت';

  @override
  String get clearChatConfirm => 'آیا مطمئن هستید که می‌خواهید چت را پاک کنید؟ این عمل قابل بازگشت نیست.';

  @override
  String get maxFilesLimit => 'شما می‌توانید تنها 4 فایل را در یک‌بار آپلود کنید';

  @override
  String get chatWithOmi => 'چت کردن با Omi';

  @override
  String get apps => 'اپلیکیشن‌ها';

  @override
  String get noAppsFound => 'اپلیکیشنی یافت نشد';

  @override
  String get tryAdjustingSearch => 'سعی کنید جستجو یا فیلترهای خود را تنظیم کنید';

  @override
  String get createYourOwnApp => 'اپلیکیشن خود را بسازید';

  @override
  String get buildAndShareApp => 'اپلیکیشن سفارشی خود را بسازید و اشتراک‌گذاری کنید';

  @override
  String get searchApps => 'جستجوی اپلیکیشن‌ها...';

  @override
  String get myApps => 'اپلیکیشن‌های من';

  @override
  String get installedApps => 'اپلیکیشن‌های نصب‌شده';

  @override
  String get unableToFetchApps =>
      'ناتوان در دریافت اپلیکیشن‌ها :(\n\nلطفاً اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید.';

  @override
  String get aboutOmi => 'درباره Omi';

  @override
  String get privacyPolicy => 'سیاست حریم خصوصی';

  @override
  String get visitWebsite => 'بازدید از وب‌سایت';

  @override
  String get helpOrInquiries => 'کمک یا پرسش؟';

  @override
  String get joinCommunity => 'به جامعه بپیوندید!';

  @override
  String get membersAndCounting => '8000+ اعضا و افزایش.';

  @override
  String get deleteAccountTitle => 'حذف حساب';

  @override
  String get deleteAccountConfirm => 'آیا مطمئن هستید که می‌خواهید حساب خود را حذف کنید؟';

  @override
  String get cannotBeUndone => 'این عمل قابل بازگشت نیست.';

  @override
  String get allDataErased => 'تمام یادداشت‌ها و گفتگوهای شما برای همیشه حذف خواهند شد.';

  @override
  String get appsDisconnected => 'اپلیکیشن‌ها و ادغام‌های شما بلافاصله قطع خواهند شد.';

  @override
  String get exportBeforeDelete =>
      'شما می‌توانید داده‌های خود را قبل از حذف حساب صادر کنید، اما پس از حذف، نمی‌توان آن را بازیابی کرد.';

  @override
  String get deleteAccountCheckbox =>
      'درک می‌کنم که حذف حساب من دائمی است و تمام داده‌ها، شامل یادداشت‌ها و گفتگوها، برای همیشه حذف خواهند شد و نمی‌توان آن‌ها را بازیابی کرد.';

  @override
  String get areYouSure => 'آیا مطمئن هستید؟';

  @override
  String get deleteAccountFinal =>
      'این عمل برگشت‌ناپذیر است و حساب شما و تمام داده‌های مرتبط را برای همیشه حذف خواهد کرد. آیا مطمئن هستید که می‌خواهید ادامه دهید؟';

  @override
  String get deleteNow => 'همین‌الان حذف کن';

  @override
  String get goBack => 'بازگشت';

  @override
  String get checkBoxToConfirm =>
      'جعبه را علامت‌گذاری کنید تا تایید کنید که درک می‌کنید حذف حساب دائمی و برگشت‌ناپذیر است.';

  @override
  String get profile => 'پروفایل';

  @override
  String get name => 'نام';

  @override
  String get email => 'ایمیل';

  @override
  String get customVocabulary => 'واژگان سفارشی';

  @override
  String get identifyingOthers => 'شناسایی دیگران';

  @override
  String get paymentMethods => 'روش‌های پرداخت';

  @override
  String get conversationDisplay => 'نمایش گفتگو';

  @override
  String get dataPrivacy => 'حریم خصوصی داده‌ها';

  @override
  String get userId => 'شناسه کاربر';

  @override
  String get notSet => 'تنظیم‌نشده';

  @override
  String get userIdCopied => 'شناسه کاربر به تخته گذاشته شد';

  @override
  String get systemDefault => 'پیش‌فرض سیستم';

  @override
  String get planAndUsage => 'طرح و استفاده';

  @override
  String get offlineSync => 'همگام‌سازی آفلاین';

  @override
  String get deviceSettings => 'تنظیمات دستگاه';

  @override
  String get integrations => 'ادغام‌ها';

  @override
  String get feedbackBug => 'بازخورد / مشکل';

  @override
  String get helpCenter => 'مرکز کمک';

  @override
  String get developerSettings => 'تنظیمات توسعه‌دهنده';

  @override
  String get getOmiForMac => 'Omi برای Mac را دریافت کنید';

  @override
  String get referralProgram => 'برنامه معرفی';

  @override
  String get signOut => 'خروج';

  @override
  String get appAndDeviceCopied => 'جزئیات اپلیکیشن و دستگاه کپی شد';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'حریم خصوصی شما، کنترل شما';

  @override
  String get privacyIntro =>
      'در Omi، ما متعهد به حفاظت از حریم خصوصی شما هستیم. این صفحه به شما اجازه می‌دهد که کنترل کنید داده‌های شما چگونه ذخیره و استفاده می‌شوند.';

  @override
  String get learnMore => 'اطلاعات بیشتر...';

  @override
  String get dataProtectionLevel => 'سطح حفاظت داده‌ها';

  @override
  String get dataProtectionDesc =>
      'داده‌های شما به‌طور پیش‌فرض با رمزگذاری قوی ایمن هستند. تنظیمات و گزینه‌های حریم خصوصی آینده خود را مرور کنید.';

  @override
  String get appAccess => 'دسترسی اپلیکیشن';

  @override
  String get appAccessDesc =>
      'اپلیکیشن‌های زیر می‌توانند به داده‌های شما دسترسی داشته باشند. برای مدیریت اجازه‌های آن روی اپلیکیشن ضربه بزنید.';

  @override
  String get noAppsExternalAccess => 'هیچ اپلیکیشن نصب‌شده‌ای دسترسی خارجی به داده‌های شما ندارد.';

  @override
  String get deviceName => 'نام دستگاه';

  @override
  String get deviceId => 'شناسه دستگاه';

  @override
  String get firmware => 'فیرم‌ور';

  @override
  String get sdCardSync => 'همگام‌سازی کارت SD';

  @override
  String get hardwareRevision => 'نسخه سخت‌افزار';

  @override
  String get modelNumber => 'شماره مدل';

  @override
  String get manufacturer => 'سازنده';

  @override
  String get doubleTap => 'دو ضربه';

  @override
  String get ledBrightness => 'روشنایی LED';

  @override
  String get micGain => 'بهره میکروفن';

  @override
  String get disconnect => 'قطع‌کردن';

  @override
  String get forgetDevice => 'فراموش کردن دستگاه';

  @override
  String get chargingIssues => 'مشکلات شارژ';

  @override
  String get disconnectDevice => 'قطع‌کردن دستگاه';

  @override
  String get unpairDevice => 'جدا کردن دستگاه';

  @override
  String get unpairAndForget => 'جدا کردن و فراموش کردن دستگاه';

  @override
  String get deviceDisconnectedMessage => 'Omi شما قطع شده است 😔';

  @override
  String get deviceUnpairedMessage =>
      'دستگاه جدا شد. به تنظیمات > Bluetooth بروید و دستگاه را فراموش کنید تا جدایی تکمیل شود.';

  @override
  String get unpairDialogTitle => 'جدا کردن دستگاه';

  @override
  String get unpairDialogMessage =>
      'این دستگاه را جدا می‌کند تا بتوان آن را به تلفن دیگری متصل کرد. شما باید به تنظیمات > Bluetooth بروید و دستگاه را فراموش کنید تا فرایند تکمیل شود.';

  @override
  String get deviceNotConnected => 'دستگاه متصل نیست';

  @override
  String get connectDeviceMessage =>
      'دستگاه Omi خود را متصل کنید تا\nبه تنظیمات و سفارشی‌سازی دستگاه دسترسی داشته باشید';

  @override
  String get deviceInfoSection => 'اطلاعات دستگاه';

  @override
  String get customizationSection => 'سفارشی‌سازی';

  @override
  String get hardwareSection => 'سخت‌افزار';

  @override
  String get v2Undetected => 'V2 شناسایی نشد';

  @override
  String get v2UndetectedMessage =>
      'ما می‌بینیم که شما یک دستگاه V1 دارید یا دستگاه شما متصل نیست. عملکرد کارت SD فقط برای دستگاه‌های V2 دردسترس است.';

  @override
  String get endConversation => 'پایان‌دادن به گفتگو';

  @override
  String get pauseResume => 'مکث/ادامه';

  @override
  String get starConversation => 'ستاره‌دار کردن گفتگو';

  @override
  String get doubleTapAction => 'عمل دو ضربه';

  @override
  String get endAndProcess => 'پایان‌دادن و پردازش گفتگو';

  @override
  String get pauseResumeRecording => 'مکث/ادامه ضبط';

  @override
  String get starOngoing => 'ستاره‌دار کردن گفتگوی جاری';

  @override
  String get off => 'خاموش';

  @override
  String get max => 'حداکثر';

  @override
  String get mute => 'بی‌صدا';

  @override
  String get quiet => 'آرام';

  @override
  String get normal => 'عادی';

  @override
  String get high => 'بالا';

  @override
  String get micGainDescMuted => 'میکروفن بی‌صدا است';

  @override
  String get micGainDescLow => 'بسیار آرام - برای محیط‌های پرسروصدا';

  @override
  String get micGainDescModerate => 'آرام - برای نویز متوسط';

  @override
  String get micGainDescNeutral => 'بی‌طرف - ضبط متعادل';

  @override
  String get micGainDescSlightlyBoosted => 'کمی تقویت‌شده - استفاده عادی';

  @override
  String get micGainDescBoosted => 'تقویت‌شده - برای محیط‌های ساکت';

  @override
  String get micGainDescHigh => 'بالا - برای صدای دور یا آهسته';

  @override
  String get micGainDescVeryHigh => 'بسیار بالا - برای منابع بسیار آرام';

  @override
  String get micGainDescMax => 'حداکثر - با احتیاط استفاده کنید';

  @override
  String get developerSettingsTitle => 'تنظیمات توسعه‌دهنده';

  @override
  String get saving => 'درحال ذخیره...';

  @override
  String get beta => 'بتا';

  @override
  String get transcription => 'رونویسی';

  @override
  String get transcriptionConfig => 'پیکربندی ارائه‌دهنده STT';

  @override
  String get conversationTimeout => 'مهلت گفتگو';

  @override
  String get conversationTimeoutConfig => 'تنظیم زمان خودکار پایان گفتگو';

  @override
  String get importData => 'وارد کردن داده‌ها';

  @override
  String get importDataConfig => 'وارد کردن داده‌ها از منابع دیگر';

  @override
  String get debugDiagnostics => 'اشکال‌زدایی و تشخیص';

  @override
  String get endpointUrl => 'URL نقطه‌انجام';

  @override
  String get noApiKeys => 'هنوز کلید API وجود ندارد';

  @override
  String get createKeyToStart => 'برای شروع کلیدی ایجاد کنید';

  @override
  String get createKey => 'ایجاد کلید';

  @override
  String get docs => 'اسناد';

  @override
  String get yourOmiInsights => 'بینش‌های Omi شما';

  @override
  String get today => 'امروز';

  @override
  String get thisMonth => 'این ماه';

  @override
  String get thisYear => 'این سال';

  @override
  String get allTime => 'همه‌زمان';

  @override
  String get noActivityYet => 'هنوز فعالیتی وجود ندارد';

  @override
  String get startConversationToSeeInsights => 'یک گفتگو با Omi شروع کنید\nتا بینش‌های استفاده خود را اینجا ببینید.';

  @override
  String get listening => 'گوش دادن';

  @override
  String get listeningSubtitle => 'کل زمانی که Omi به فعالیت گوش داده است.';

  @override
  String get understanding => 'درک';

  @override
  String get understandingSubtitle => 'کلمات درک‌شده از گفتگوهای شما.';

  @override
  String get providing => 'ارائه';

  @override
  String get providingSubtitle => 'موارد اقدام و یادداشت‌های خودکار ثبت‌شده.';

  @override
  String get remembering => 'یادآوری';

  @override
  String get rememberingSubtitle => 'واقعیات و جزئیات یادآوری‌شده برای شما.';

  @override
  String get unlimitedPlan => 'طرح نامحدود';

  @override
  String get managePlan => 'مدیریت طرح';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'طرح شما در تاریخ $date لغو خواهد شد.';
  }

  @override
  String renewsOn(String date) {
    return 'طرح شما در تاریخ $date تجدید خواهد شد.';
  }

  @override
  String get basicPlan => 'طرح رایگان';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used از $limit دقیقه استفاده‌شده است';
  }

  @override
  String get upgrade => 'ارتقا';

  @override
  String get upgradeToUnlimited => 'ارتقا به نامحدود';

  @override
  String basicPlanDesc(int limit) {
    return 'طرح شما شامل $limit دقیقه رایگان در ماه است. برای نامحدود ارتقا دهید.';
  }

  @override
  String get shareStatsMessage => 'از آمار Omi من استفاده می‌کنم! (omi.me - دستیار هوشمند همیشه‌فعال شما)';

  @override
  String get sharePeriodToday => 'امروز، omi:';

  @override
  String get sharePeriodMonth => 'این ماه، omi:';

  @override
  String get sharePeriodYear => 'این سال، omi:';

  @override
  String get sharePeriodAllTime => 'تاکنون، omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 برای $minutes دقیقه گوش داد';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words کلمه را درک کرد';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count بینش ارائه کرد';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count یادداشت یادآوری کرد';
  }

  @override
  String get debugLogs => 'گزارش‌های اشکال‌زدایی';

  @override
  String get debugLogsAutoDelete => 'بعد از 3 روز خودکار حذف می‌شود.';

  @override
  String get debugLogsDesc => 'کمک به تشخیص مشکلات';

  @override
  String get noLogFilesFound => 'هیچ فایل گزارشی یافت نشد.';

  @override
  String get omiDebugLog => 'گزارش اشکال‌زدایی Omi';

  @override
  String get logShared => 'گزارش اشتراک‌گذاری شد';

  @override
  String get selectLogFile => 'انتخاب فایل گزارش';

  @override
  String get shareLogs => 'اشتراک‌گذاری گزارش‌ها';

  @override
  String get debugLogCleared => 'گزارش اشکال‌زدایی پاک شد';

  @override
  String get exportStarted => 'صادر کردن شروع شد. این ممکن است چند ثانیه طول بکشد...';

  @override
  String get exportAllData => 'صادر کردن تمام داده‌ها';

  @override
  String get exportDataDesc => 'صادر کردن گفتگوها به فایل JSON';

  @override
  String get exportedConversations => 'گفتگوهای صادر‌شده از Omi';

  @override
  String get exportShared => 'صادرات اشتراک‌گذاری شد';

  @override
  String get deleteKnowledgeGraphTitle => 'حذف گراف دانش؟';

  @override
  String get deleteKnowledgeGraphMessage =>
      'این کار تمام داده‌های گراف دانش مشتق‌شده (گره‌ها و اتصالات) را حذف خواهد کرد. یادداشت‌های اصلی شما امن باقی خواهند ماند. گراف در طول زمان یا در درخواست بعدی بازسازی خواهد شد.';

  @override
  String get knowledgeGraphDeleted => 'گراف دانش حذف شد';

  @override
  String deleteGraphFailed(String error) {
    return 'ناتوان در حذف گراف: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'حذف گراف دانش';

  @override
  String get deleteKnowledgeGraphDesc => 'تمام گره‌ها و اتصالات را پاک کنید';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'سرور MCP';

  @override
  String get mcpServerDesc => 'دستیارهای هوشمند را به داده‌های خود وصل کنید';

  @override
  String get serverUrl => 'URL سرور';

  @override
  String get urlCopied => 'URL کپی شد';

  @override
  String get apiKeyAuth => 'احراز هویت کلید API';

  @override
  String get header => 'سرصفحه';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'شناسه کلاینت';

  @override
  String get clientSecret => 'رمز کلاینت';

  @override
  String get useMcpApiKey => 'از کلید API MCP خود استفاده کنید';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'رویدادهای گفتگو';

  @override
  String get newConversationCreated => 'گفتگوی جدید ایجاد شد';

  @override
  String get realtimeTranscript => 'رونویسی بلادرنگ';

  @override
  String get transcriptReceived => 'رونویسی دریافت شد';

  @override
  String get audioBytes => 'بایت‌های صوتی';

  @override
  String get audioDataReceived => 'داده صوتی دریافت شد';

  @override
  String get intervalSeconds => 'فاصله (ثانیه)';

  @override
  String get daySummary => 'خلاصه روز';

  @override
  String get summaryGenerated => 'خلاصه تولید شد';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'افزودن به claude_desktop_config.json';

  @override
  String get copyConfig => 'کپی پیکربندی';

  @override
  String get configCopied => 'پیکربندی به تخته گذاشته شد';

  @override
  String get listeningMins => 'گوش دادن (دقیقه)';

  @override
  String get understandingWords => 'درک (کلمات)';

  @override
  String get insights => 'بینش‌ها';

  @override
  String get memories => 'یادداشت‌ها';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used از $limit دقیقه این ماه استفاده‌شده است';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used از $limit کلمه این ماه استفاده‌شده است';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used از $limit بینش این ماه کسب‌شده است';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used از $limit یادداشت این ماه ایجاد‌شده است';
  }

  @override
  String get visibility => 'دید';

  @override
  String get visibilitySubtitle => 'کنترل کنید کدام گفتگوها در لیست شما نمایش داده شوند';

  @override
  String get showShortConversations => 'نمایش گفتگوهای کوتاه';

  @override
  String get showShortConversationsDesc => 'نمایش گفتگوهای کوتاه‌تر از آستانه';

  @override
  String get showDiscardedConversations => 'نمایش گفتگوهای کنار‌گذاشته‌شده';

  @override
  String get showDiscardedConversationsDesc => 'شامل‌کردن گفتگوهایی که علامت‌گذاری برای حذف شده‌اند';

  @override
  String get shortConversationThreshold => 'آستانه گفتگوی کوتاه';

  @override
  String get shortConversationThresholdSubtitle => 'گفتگوهای کوتاه‌تر از این مخفی خواهند شد مگر اینکه بالا فعال باشند';

  @override
  String get durationThreshold => 'آستانه مدت‌زمان';

  @override
  String get durationThresholdDesc => 'مخفی‌کردن گفتگوهای کوتاه‌تر از این';

  @override
  String minLabel(int count) {
    return '$count دقیقه';
  }

  @override
  String get customVocabularyTitle => 'واژگان سفارشی';

  @override
  String get addWords => 'افزودن کلمات';

  @override
  String get addWordsDesc => 'نام‌ها، اصطلاحات یا کلمات نادر';

  @override
  String get vocabularyHint => 'Omi، Callie، OpenAI';

  @override
  String get connect => 'اتصال';

  @override
  String get comingSoon => 'به‌زودی';

  @override
  String get integrationsFooter => 'اپلیکیشن‌های خود را وصل کنید تا داده‌ها و معیارها را در چت مشاهده کنید.';

  @override
  String get completeAuthInBrowser =>
      'لطفاً احراز هویت را در مرورگر خود تکمیل کنید. پس از انجام، به اپلیکیشن بازگردید.';

  @override
  String failedToStartAuth(String appName) {
    return 'ناتوان در شروع احراز هویت $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'قطع‌کردن $appName؟';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'آیا مطمئن هستید که می‌خواهید از $appName قطع شوید؟ شما می‌توانید هر زمان دوباره متصل شوید.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'قطع شده از $appName';
  }

  @override
  String get failedToDisconnect => 'ناتوان در قطع‌کردن';

  @override
  String connectTo(String appName) {
    return 'اتصال به $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'شما باید Omi را مجاز کنید تا به داده‌های $appName شما دسترسی داشته باشد. این مرورگر شما را برای احراز هویت باز خواهد کرد.';
  }

  @override
  String get continueAction => 'ادامه';

  @override
  String get languageTitle => 'زبان';

  @override
  String get primaryLanguage => 'زبان اصلی';

  @override
  String get automaticTranslation => 'ترجمه خودکار';

  @override
  String get detectLanguages => 'تشخیص 10+ زبان';

  @override
  String get authorizeSavingRecordings => 'مجاز کردن ذخیره ضبط‌ها';

  @override
  String get thanksForAuthorizing => 'سپاس برای مجاز کردن!';

  @override
  String get needYourPermission => 'ما نیاز به اجازه شما داریم';

  @override
  String get alreadyGavePermission =>
      'شما قبلاً اجازه‌ای برای ذخیره ضبط‌های صوتی شما داده‌اید. اینجا یادآوری دلیل نیاز ما است:';

  @override
  String get wouldLikePermission => 'ما می‌خواهیم اجازه شما را برای ذخیره ضبط‌های صوتی خود بگیریم. دلیل این است:';

  @override
  String get improveSpeechProfile => 'بهبود پروفایل صوتی شما';

  @override
  String get improveSpeechProfileDesc => 'ما از ضبط‌ها برای آموزش و بهبود پروفایل صوتی شخصی شما استفاده می‌کنیم.';

  @override
  String get trainFamilyProfiles => 'آموزش پروفایل‌ها برای دوستان و خانواده';

  @override
  String get trainFamilyProfilesDesc =>
      'ضبط‌های شما کمک می‌کند ما دوستان و خانواده شما را شناسایی و پروفایل ایجاد کنیم.';

  @override
  String get enhanceTranscriptAccuracy => 'بهبود دقت رونویسی';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'هنگامی که مدل ما بهبود می‌یابد، می‌توانیم نتایج رونویسی بهتری برای ضبط‌های شما ارائه دهیم.';

  @override
  String get legalNotice =>
      'اخطار قانونی: قانونی بودن ضبط و ذخیره داده‌های صوتی ممکن است بسته به موقعیت مکانی شما و نحوه استفاده از این ویژگی متفاوت باشد. شما مسئول اطمینان از انطباق با قوانین و مقررات محلی هستید.';

  @override
  String get alreadyAuthorized => 'قبلاً مجاز';

  @override
  String get authorize => 'مجاز کردن';

  @override
  String get revokeAuthorization => 'لغو مجوز';

  @override
  String get authorizationSuccessful => 'مجوز موفق!';

  @override
  String get failedToAuthorize => 'خطا در تأیید هویت. لطفاً دوباره تلاش کنید.';

  @override
  String get authorizationRevoked => 'تأیید هویت لغو شد.';

  @override
  String get recordingsDeleted => 'ضبط‌ها حذف شدند.';

  @override
  String get failedToRevoke => 'خطا در لغو تأیید هویت. لطفاً دوباره تلاش کنید.';

  @override
  String get permissionRevokedTitle => 'اجازه لغو شد';

  @override
  String get permissionRevokedMessage => 'آیا می‌خواهید تمام ضبط‌های موجود خود را نیز حذف کنیم؟';

  @override
  String get yes => 'بلی';

  @override
  String get editName => 'ویرایش نام';

  @override
  String get howShouldOmiCallYou => 'Omi باید چطور شما را صدا بزند؟';

  @override
  String get enterYourName => 'نام خود را وارد کنید';

  @override
  String get nameCannotBeEmpty => 'نام نمی‌تواند خالی باشد';

  @override
  String get nameUpdatedSuccessfully => 'نام با موفقیت به‌روزرسانی شد!';

  @override
  String get calendarSettings => 'تنظیمات تقویم';

  @override
  String get calendarProviders => 'ارائه‌دهندگان تقویم';

  @override
  String get macOsCalendar => 'تقویم macOS';

  @override
  String get connectMacOsCalendar => 'تقویم محلی macOS خود را متصل کنید';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'با حساب Google خود همگام‌سازی کنید';

  @override
  String get showMeetingsMenuBar => 'نمایش جلسات آینده در نوار منو';

  @override
  String get showMeetingsMenuBarDesc => 'جلسه بعدی و مدت زمان تا شروع آن را در نوار منو macOS نمایش دهید';

  @override
  String get showEventsNoParticipants => 'نمایش رویدادهایی بدون شرکت‌کننده';

  @override
  String get showEventsNoParticipantsDesc =>
      'هنگام فعال‌سازی، Coming Up رویدادهایی بدون شرکت‌کننده یا پیوند ویدیویی را نمایش می‌دهد.';

  @override
  String get yourMeetings => 'جلسات شما';

  @override
  String get refresh => 'بازخوانی';

  @override
  String get noUpcomingMeetings => 'جلسه آینده‌ای نیست';

  @override
  String get checkingNextDays => 'بررسی 30 روز بعدی';

  @override
  String get tomorrow => 'فردا';

  @override
  String get googleCalendarComingSoon => 'یکپارچگی Google Calendar به‌زودی!';

  @override
  String connectedAsUser(String userId) {
    return 'به‌عنوان کاربر متصل شده: $userId';
  }

  @override
  String get defaultWorkspace => 'فضای کاری پیش‌فرض';

  @override
  String get tasksCreatedInWorkspace => 'وظایف در این فضای کاری ایجاد خواهند شد';

  @override
  String get defaultProjectOptional => 'پروژه پیش‌فرض (اختیاری)';

  @override
  String get leaveUnselectedTasks => 'برای ایجاد وظایف بدون پروژه، آن را انتخاب نکنید';

  @override
  String get noProjectsInWorkspace => 'هیچ پروژه‌ای در این فضای کاری یافت نشد';

  @override
  String get conversationTimeoutDesc =>
      'انتخاب کنید که چقدر زمان در سکوت منتظر بمانید تا گفتگو به‌طور خودکار پایان یابد:';

  @override
  String get timeout2Minutes => '2 دقیقه';

  @override
  String get timeout2MinutesDesc => 'گفتگو پس از 2 دقیقه سکوت پایان می‌یابد';

  @override
  String get timeout5Minutes => '5 دقیقه';

  @override
  String get timeout5MinutesDesc => 'گفتگو پس از 5 دقیقه سکوت پایان می‌یابد';

  @override
  String get timeout10Minutes => '10 دقیقه';

  @override
  String get timeout10MinutesDesc => 'گفتگو پس از 10 دقیقه سکوت پایان می‌یابد';

  @override
  String get timeout30Minutes => '30 دقیقه';

  @override
  String get timeout30MinutesDesc => 'گفتگو پس از 30 دقیقه سکوت پایان می‌یابد';

  @override
  String get timeout4Hours => '4 ساعت';

  @override
  String get timeout4HoursDesc => 'گفتگو پس از 4 ساعت سکوت پایان می‌یابد';

  @override
  String get conversationEndAfterHours => 'گفتگو‌ها اکنون پس از 4 ساعت سکوت پایان می‌یابند';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'گفتگو‌ها اکنون پس از $minutes دقیقه سکوت پایان می‌یابند';
  }

  @override
  String get tellUsPrimaryLanguage => 'زبان اصلی خود را به ما بگویید';

  @override
  String get languageForTranscription => 'زبان خود را برای رونویسی‌های تیزتر و تجربه شخصی‌سازی‌شده تنظیم کنید.';

  @override
  String get singleLanguageModeInfo => 'حالت زبان تکی فعال شده است. ترجمه برای دقت بالاتر غیرفعال است.';

  @override
  String get searchLanguageHint => 'زبان را بر اساس نام یا کد جستجو کنید';

  @override
  String get noLanguagesFound => 'هیچ زبانی یافت نشد';

  @override
  String get skip => 'رد کردن';

  @override
  String languageSetTo(String language) {
    return 'زبان تنظیم شد به $language';
  }

  @override
  String get failedToSetLanguage => 'خطا در تنظیم زبان';

  @override
  String appSettings(String appName) {
    return 'تنظیمات $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'از $appName قطع‌کردن؟';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'این تأیید هویت $appName را حذف می‌کند. برای استفاده دوباره، باید دوباره متصل شوید.';
  }

  @override
  String connectedToApp(String appName) {
    return 'به $appName متصل شده';
  }

  @override
  String get account => 'حساب';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'موارد اقدام شما با حساب $appName شما همگام‌سازی خواهد شد';
  }

  @override
  String get defaultSpace => 'فضای پیش‌فرض';

  @override
  String get selectSpaceInWorkspace => 'فضایی در فضای کاری خود را انتخاب کنید';

  @override
  String get noSpacesInWorkspace => 'هیچ فضایی در این فضای کاری یافت نشد';

  @override
  String get defaultList => 'فهرست پیش‌فرض';

  @override
  String get tasksAddedToList => 'وظایف به این فهرست اضافه خواهد شد';

  @override
  String get noListsInSpace => 'هیچ فهرستی در این فضا یافت نشد';

  @override
  String failedToLoadRepos(String error) {
    return 'خطا در بارگیری مخازن: $error';
  }

  @override
  String get defaultRepoSaved => 'مخزن پیش‌فرض ذخیره شد';

  @override
  String get failedToSaveDefaultRepo => 'خطا در ذخیره مخزن پیش‌فرض';

  @override
  String get defaultRepository => 'مخزن پیش‌فرض';

  @override
  String get selectDefaultRepoDesc =>
      'مخزنی پیش‌فرض برای ایجاد مسائل را انتخاب کنید. هنگام ایجاد مسائل، همچنان می‌توانید مخزن متفاوتی را مشخص کنید.';

  @override
  String get noReposFound => 'هیچ مخزنی یافت نشد';

  @override
  String get private => 'خصوصی';

  @override
  String updatedDate(String date) {
    return '$date به‌روزرسانی شد';
  }

  @override
  String get yesterday => 'دیروز';

  @override
  String daysAgo(int count) {
    return '$count روز پیش';
  }

  @override
  String get oneWeekAgo => '1 هفته پیش';

  @override
  String weeksAgo(int count) {
    return '$count هفته پیش';
  }

  @override
  String get oneMonthAgo => '1 ماه پیش';

  @override
  String monthsAgo(int count) {
    return '$count ماه پیش';
  }

  @override
  String get issuesCreatedInRepo => 'مسائل در مخزن پیش‌فرض شما ایجاد خواهند شد';

  @override
  String get taskIntegrations => 'یکپارچگی‌های وظیفه';

  @override
  String get configureSettings => 'تنظیمات پیکربندی';

  @override
  String get completeAuthBrowser => 'لطفاً تأیید هویت را در مرورگر خود تکمیل کنید. پس از اتمام، به برنامه بازگردید.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'خطا در شروع تأیید هویت $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'اتصال به $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'باید Omi را برای ایجاد وظایف در حساب $appName خود مجاز کنید. این کار مرورگر شما را برای تأیید هویت باز می‌کند.';
  }

  @override
  String get continueButton => 'ادامه';

  @override
  String appIntegration(String appName) {
    return 'یکپارچگی $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'یکپارچگی با $appName به‌زودی! ما سخت برای ارائه گزینه‌های مدیریت وظیفه بیشتر کار می‌کنیم.';
  }

  @override
  String get gotIt => 'فهمیدم';

  @override
  String get tasksExportedOneApp => 'وظایف را می‌توان یک باره فقط به یک برنامه صادر کرد.';

  @override
  String get completeYourUpgrade => 'ارتقا خود را تکمیل کنید';

  @override
  String get importConfiguration => 'وارد کردن پیکربندی';

  @override
  String get exportConfiguration => 'صادر کردن پیکربندی';

  @override
  String get bringYourOwn => 'خود را بیاورید';

  @override
  String get payYourSttProvider =>
      'آزادانه از omi استفاده کنید. شما فقط مستقیماً ارائه‌دهنده STT خود را پرداخت می‌کنید.';

  @override
  String get freeMinutesMonth => '1200 دقیقه رایگان/ماه شامل است. نامحدود با ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'میزبان ضروری است';

  @override
  String get validPortRequired => 'پورت معتبر ضروری است';

  @override
  String get validWebsocketUrlRequired => 'URL معتبر WebSocket ضروری است (wss://)';

  @override
  String get apiUrlRequired => 'URL API ضروری است';

  @override
  String get apiKeyRequired => 'کلید API ضروری است';

  @override
  String get invalidJsonConfig => 'پیکربندی JSON نامعتبر';

  @override
  String errorSaving(String error) {
    return 'خطا در ذخیره: $error';
  }

  @override
  String get configCopiedToClipboard => 'پیکربندی به کلیپ‌بورد کپی شد';

  @override
  String get pasteJsonConfig => 'پیکربندی JSON خود را در زیر بچسبانید:';

  @override
  String get addApiKeyAfterImport => 'پس از وارد کردن، باید کلید API خود را اضافه کنید';

  @override
  String get paste => 'چسباندن';

  @override
  String get import => 'وارد کردن';

  @override
  String get invalidProviderInConfig => 'ارائه‌دهنده نامعتبر در پیکربندی';

  @override
  String importedConfig(String providerName) {
    return 'پیکربندی $providerName وارد شد';
  }

  @override
  String invalidJson(String error) {
    return 'JSON نامعتبر: $error';
  }

  @override
  String get provider => 'ارائه‌دهنده';

  @override
  String get live => 'زنده';

  @override
  String get onDevice => 'روی دستگاه';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'نقطه پایانی HTTP STT خود را وارد کنید';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'نقطه پایانی WebSocket STT زنده خود را وارد کنید';

  @override
  String get apiKey => 'کلید API';

  @override
  String get enterApiKey => 'کلید API خود را وارد کنید';

  @override
  String get storedLocallyNeverShared => 'به‌طور محلی ذخیره شده است، هرگز به‌اشتراک گذاشته نشده است';

  @override
  String get host => 'میزبان';

  @override
  String get port => 'درگاه';

  @override
  String get advanced => 'پیشرفته';

  @override
  String get configuration => 'پیکربندی';

  @override
  String get requestConfiguration => 'پیکربندی درخواست';

  @override
  String get responseSchema => 'طرح پاسخ';

  @override
  String get modified => 'تغییر یافته';

  @override
  String get resetRequestConfig => 'تنظیم مجدد پیکربندی درخواست به پیش‌فرض';

  @override
  String get logs => 'گزارش‌ها';

  @override
  String get logsCopied => 'گزارش‌ها کپی شدند';

  @override
  String get noLogsYet => 'هیچ گزارشی هنوز نیست. برای دیدن فعالیت STT سفارشی، ضبط را شروع کنید.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device از $reason استفاده می‌کند. Omi استفاده خواهد شد.';
  }

  @override
  String get omiTranscription => 'رونویسی Omi';

  @override
  String get bestInClassTranscription => 'بهترین کلاس رونویسی بدون راه‌اندازی';

  @override
  String get instantSpeakerLabels => 'برچسب‌های فوری سخنران';

  @override
  String get languageTranslation => 'ترجمه 100+ زبان';

  @override
  String get optimizedForConversation => 'برای گفتگو بهینه‌سازی شده';

  @override
  String get autoLanguageDetection => 'تشخیص خودکار زبان';

  @override
  String get highAccuracy => 'دقت بالا';

  @override
  String get privacyFirst => 'حریم خصوصی اول';

  @override
  String get saveChanges => 'ذخیره تغییرات';

  @override
  String get resetToDefault => 'بازنشانی به پیش‌فرض';

  @override
  String get viewTemplate => 'مشاهده الگو';

  @override
  String get trySomethingLike => 'چیزی مانند این را امتحان کنید...';

  @override
  String get tryIt => 'امتحان کنید';

  @override
  String get creatingPlan => 'ایجاد طرح';

  @override
  String get developingLogic => 'توسعه منطق';

  @override
  String get designingApp => 'طراحی برنامه';

  @override
  String get generatingIconStep => 'تولید آیکون';

  @override
  String get finalTouches => 'لمسات نهایی';

  @override
  String get processing => 'در حال پردازش...';

  @override
  String get features => 'ویژگی‌ها';

  @override
  String get creatingYourApp => 'در حال ایجاد برنامه شما...';

  @override
  String get generatingIcon => 'در حال تولید آیکون...';

  @override
  String get whatShouldWeMake => 'چه چیزی را باید ایجاد کنیم؟';

  @override
  String get appName => 'نام برنامه';

  @override
  String get description => 'توصیف';

  @override
  String get publicLabel => 'عمومی';

  @override
  String get privateLabel => 'خصوصی';

  @override
  String get free => 'رایگان';

  @override
  String get perMonth => '/ ماه';

  @override
  String get tailoredConversationSummaries => 'خلاصه‌های گفتگو شخصی‌سازی‌شده';

  @override
  String get customChatbotPersonality => 'شخصیت چت‌بات سفارشی';

  @override
  String get makePublic => 'عمومی کنید';

  @override
  String get anyoneCanDiscover => 'هر کسی می‌تواند برنامه شما را کشف کند';

  @override
  String get onlyYouCanUse => 'فقط شما می‌توانید از این برنامه استفاده کنید';

  @override
  String get paidApp => 'برنامه پولی';

  @override
  String get usersPayToUse => 'کاربران برای استفاده از برنامه شما پرداخت می‌کنند';

  @override
  String get freeForEveryone => 'برای همه رایگان';

  @override
  String get perMonthLabel => '/ ماه';

  @override
  String get creating => 'در حال ایجاد...';

  @override
  String get createApp => 'ایجاد برنامه';

  @override
  String get searchingForDevices => 'در حال جستجو برای دستگاه‌ها...';

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
  String get pairingSuccessful => 'جفت‌سازی موفق';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'خطا در اتصال به Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'دوباره نمایش ندهید';

  @override
  String get iUnderstand => 'متوجه شدم';

  @override
  String get enableBluetooth => 'فعال‌سازی Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi نیاز به Bluetooth برای اتصال به دستگاه پوشیدنی دارد. لطفاً Bluetooth را فعال کنید و دوباره تلاش کنید.';

  @override
  String get contactSupport => 'تماس با پشتیبانی؟';

  @override
  String get connectLater => 'اتصال بعداً';

  @override
  String get grantPermissions => 'اعطای اجازات';

  @override
  String get backgroundActivity => 'فعالیت پس‌زمینه';

  @override
  String get backgroundActivityDesc => 'اجازه دهید Omi در پس‌زمینه اجرا شود برای پایداری بهتر';

  @override
  String get locationAccess => 'دسترسی به مکان';

  @override
  String get locationAccessDesc => 'مکان پس‌زمینه را برای تجربه کامل فعال کنید';

  @override
  String get notifications => 'اطلاع‌رسانی‌ها';

  @override
  String get notificationsDesc => 'اطلاع‌رسانی را برای اطلاع‌رسانی فعال کنید';

  @override
  String get locationServiceDisabled => 'سرویس مکان غیرفعال است';

  @override
  String get locationServiceDisabledDesc =>
      'سرویس مکان غیرفعال است. لطفاً به Settings > Privacy & Security > Location Services بروید و آن را فعال کنید';

  @override
  String get backgroundLocationDenied => 'دسترسی مکان پس‌زمینه رد شد';

  @override
  String get backgroundLocationDeniedDesc =>
      'لطفاً به تنظیمات دستگاه بروید و مجوز مکان را روی \"Always Allow\" تنظیم کنید';

  @override
  String get lovingOmi => 'Omi را دوست داشتید؟';

  @override
  String get leaveReviewIos =>
      'با گذاشتن نظری در App Store، کمک کنید ما به مردم بیشتری برسیم. بازخوردتان برای ما بسیار مهم است!';

  @override
  String get leaveReviewAndroid =>
      'با گذاشتن نظری در Google Play Store، کمک کنید ما به مردم بیشتری برسیم. بازخوردتان برای ما بسیار مهم است!';

  @override
  String get rateOnAppStore => 'در App Store امتیاز دهید';

  @override
  String get rateOnGooglePlay => 'در Google Play امتیاز دهید';

  @override
  String get maybeLater => 'شاید بعداً';

  @override
  String get speechProfileIntro => 'Omi نیاز دارد اهداف و صدای شما را یاد بگیرد. بعداً می‌توانید آن را تغییر دهید.';

  @override
  String get getStarted => 'شروع کنید';

  @override
  String get allDone => 'همه کار تمام شد!';

  @override
  String get keepGoing => 'ادامه دهید، خیلی خوب انجام می‌دهید';

  @override
  String get skipThisQuestion => 'این سؤال را رد کنید';

  @override
  String get skipForNow => 'ابتدا رد کنید';

  @override
  String get connectionError => 'خطای اتصال';

  @override
  String get connectionErrorDesc => 'خطا در اتصال به سرور. لطفاً اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید.';

  @override
  String get invalidRecordingMultipleSpeakers => 'ضبط نامعتبر تشخیص داده شد';

  @override
  String get multipleSpeakersDesc =>
      'به نظر می‌رسد چندین سخنران در ضبط وجود دارند. لطفاً اطمینان حاصل کنید که در مکانی ساکت هستید و دوباره تلاش کنید.';

  @override
  String get tooShortDesc => 'سخن کافی تشخیص داده نشده است. لطفاً بیشتر صحبت کنید و دوباره تلاش کنید.';

  @override
  String get invalidRecordingDesc => 'لطفاً اطمینان حاصل کنید که حداقل 5 ثانیه و حداکثر 90 ثانیه صحبت می‌کنید.';

  @override
  String get areYouThere => 'آیا آنجایی؟';

  @override
  String get noSpeechDesc => 'ما نتوانستیم سخنی را تشخیص دهیم. لطفاً حداقل 10 ثانیه و حداکثر 3 دقیقه صحبت کنید.';

  @override
  String get connectionLost => 'اتصال قطع شد';

  @override
  String get connectionLostDesc => 'اتصال قطع شده است. لطفاً اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید.';

  @override
  String get tryAgain => 'دوباره تلاش کنید';

  @override
  String get connectOmiOmiGlass => 'اتصال Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'ادامه بدون دستگاه';

  @override
  String get permissionsRequired => 'اجازات ضروری';

  @override
  String get permissionsRequiredDesc =>
      'این برنامه نیاز به اجازات Bluetooth و Location برای کارکرد صحیح دارد. لطفاً آنها را در تنظیمات فعال کنید.';

  @override
  String get openSettings => 'باز کردن تنظیمات';

  @override
  String get wantDifferentName => 'می‌خواهید به چیز دیگری نامیده شوید؟';

  @override
  String get whatsYourName => 'نام شما چیست؟';

  @override
  String get speakTranscribeSummarize => 'صحبت کنید. رونویس کنید. خلاصه کنید.';

  @override
  String get signInWithApple => 'ورود با Apple';

  @override
  String get signInWithGoogle => 'ورود با Google';

  @override
  String get byContinuingAgree => 'با ادامه، موافقت می‌کنید با ';

  @override
  String get termsOfUse => 'شرایط استفاده';

  @override
  String get omiYourAiCompanion => 'Omi – همراه هوش مصنوعی شما';

  @override
  String get captureEveryMoment => 'هر لحظه را ثبت کنید. خلاصه‌های هوش مصنوعی دریافت کنید.\nدیگر یادداشت نگیرید.';

  @override
  String get appleWatchSetup => 'راه‌اندازی Apple Watch';

  @override
  String get permissionRequestedExclaim => 'اجازه درخواست شد!';

  @override
  String get microphonePermission => 'اجازه میکروفن';

  @override
  String get permissionGrantedNow =>
      'اجازه اعطا شد! اکنون:\n\nبرنامه Omi را روی ساعت خود باز کنید و روی \"Continue\" زیر ضربه بزنید';

  @override
  String get needMicrophonePermission =>
      'ما به اجازه میکروفن نیاز داریم.\n\n1. روی \"اعطای اجازات\" ضربه بزنید\n2. در iPhone خود اجازه دهید\n3. برنامه ساعت بسته می‌شود\n4. دوباره باز کنید و روی \"Continue\" ضربه بزنید';

  @override
  String get grantPermissionButton => 'اعطای اجازات';

  @override
  String get needHelp => 'کمک نیاز دارید؟';

  @override
  String get troubleshootingSteps =>
      'حل‌مسئله:\n\n1. مطمئن شوید که Omi روی ساعت شما نصب شده است\n2. برنامه Omi را روی ساعت خود باز کنید\n3. برای بالا رفتن اجازه به دنبال پنجره اجازات باشید\n4. هنگام درخواست، روی \"Allow\" ضربه بزنید\n5. برنامه روی ساعت شما بسته می‌شود - دوباره باز کنید\n6. به iPhone بازگردید و روی \"Continue\" ضربه بزنید';

  @override
  String get recordingStartedSuccessfully => 'ضبط با موفقیت شروع شد!';

  @override
  String get permissionNotGrantedYet =>
      'اجازه هنوز اعطا نشده است. لطفاً مطمئن شوید که دسترسی میکروفن را اجازه داده‌اید و برنامه را روی ساعت خود دوباره باز کرده‌اید.';

  @override
  String errorRequestingPermission(String error) {
    return 'خطا در درخواست اجازات: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'خطا در شروع ضبط: $error';
  }

  @override
  String get selectPrimaryLanguage => 'زبان اصلی خود را انتخاب کنید';

  @override
  String get languageBenefits => 'زبان خود را برای رونویسی‌های تیزتر و تجربه شخصی‌سازی‌شده تنظیم کنید';

  @override
  String get whatsYourPrimaryLanguage => 'زبان اصلی شما چیست؟';

  @override
  String get selectYourLanguage => 'زبان خود را انتخاب کنید';

  @override
  String get personalGrowthJourney => 'سفر رشد شخصی شما با هوش مصنوعی که به هر کلمه شما گوش می‌دهد.';

  @override
  String get actionItemsTitle => 'فهرست کارها';

  @override
  String get actionItemsDescription => 'برای ویرایش ضربه بزنید • برای انتخاب فشار طولانی کنید • برای اقدام بکشید';

  @override
  String get tabToDo => 'برای انجام';

  @override
  String get tabDone => 'انجام شد';

  @override
  String get tabOld => 'قدیمی';

  @override
  String get emptyTodoMessage => '🎉 همه تمام شد!\nهیچ موارد اقدام در انتظار نیست';

  @override
  String get emptyDoneMessage => 'هیچ موارد تکمیل شده‌ای هنوز نیست';

  @override
  String get emptyOldMessage => '✅ هیچ وظیفه قدیمی‌ای نیست';

  @override
  String get noItems => 'هیچ موردی نیست';

  @override
  String get actionItemMarkedIncomplete => 'موارد اقدام به‌عنوان ناتکمیل علامت‌گذاری شد';

  @override
  String get actionItemCompleted => 'موارد اقدام تکمیل شد';

  @override
  String get deleteActionItemTitle => 'حذف موارد اقدام';

  @override
  String get deleteActionItemMessage => 'آیا مطمئن هستید که می‌خواهید این موارد اقدام را حذف کنید؟';

  @override
  String get deleteSelectedItemsTitle => 'حذف موارد انتخاب شده';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'موارد اقدام \"$description\" حذف شد';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'خطا در حذف موارد اقدام';

  @override
  String get failedToDeleteItems => 'خطا در حذف موارد';

  @override
  String get failedToDeleteSomeItems => 'خطا در حذف برخی موارد';

  @override
  String get welcomeActionItemsTitle => 'آماده موارد اقدام';

  @override
  String get welcomeActionItemsDescription =>
      'هوش مصنوعی شما به‌طور خودکار وظایف و کارهای انجام‌شده را از گفتگو‌های شما استخراج می‌کند. آنها در اینجا ظاهر می‌شوند.';

  @override
  String get autoExtractionFeature => 'به‌طور خودکار از گفتگو‌ها استخراج شده';

  @override
  String get editSwipeFeature => 'برای ویرایش ضربه بزنید، برای تکمیل یا حذف بکشید';

  @override
  String itemsSelected(int count) {
    return '$count انتخاب شده';
  }

  @override
  String get selectAll => 'انتخاب همه';

  @override
  String get deleteSelected => 'حذف انتخاب شده';

  @override
  String get searchMemories => 'جستجو خاطرات...';

  @override
  String get memoryDeleted => 'خاطره حذف شد.';

  @override
  String get undo => 'بازگشت';

  @override
  String get noMemoriesYet => '🧠 هیچ خاطره‌ای هنوز نیست';

  @override
  String get noAutoMemories => 'هیچ خاطره‌ای استخراج شده‌ای هنوز نیست';

  @override
  String get noManualMemories => 'هیچ خاطره‌ای دستی‌ای هنوز نیست';

  @override
  String get noMemoriesInCategories => 'هیچ خاطره‌ای در این دسته‌بندی‌ها نیست';

  @override
  String get noMemoriesFound => '🔍 هیچ خاطره‌ای یافت نشد';

  @override
  String get addFirstMemory => 'اولین خاطره خود را اضافه کنید';

  @override
  String get clearMemoryTitle => 'پاک کردن حافظه Omi';

  @override
  String get clearMemoryMessage => 'آیا مطمئن هستید که می‌خواهید حافظه Omi را پاک کنید؟ این اقدام قابل برگشت نیست.';

  @override
  String get clearMemoryButton => 'پاک کردن حافظه';

  @override
  String get memoryClearedSuccess => 'خاطره Omi در مورد شما پاک شده است';

  @override
  String get noMemoriesToDelete => 'هیچ خاطره‌ای برای حذف نیست';

  @override
  String get createMemoryTooltip => 'ایجاد خاطره جدید';

  @override
  String get createActionItemTooltip => 'ایجاد موارد اقدام جدید';

  @override
  String get memoryManagement => 'مدیریت خاطره';

  @override
  String get filterMemories => 'فیلتر کردن خاطرات';

  @override
  String totalMemoriesCount(int count) {
    return 'شما $count خاطره کل دارید';
  }

  @override
  String get publicMemories => 'خاطرات عمومی';

  @override
  String get privateMemories => 'خاطرات خصوصی';

  @override
  String get makeAllPrivate => 'تمام خاطرات را خصوصی کنید';

  @override
  String get makeAllPublic => 'تمام خاطرات را عمومی کنید';

  @override
  String get deleteAllMemories => 'حذف تمام خاطرات';

  @override
  String get allMemoriesPrivateResult => 'تمام خاطرات اکنون خصوصی هستند';

  @override
  String get allMemoriesPublicResult => 'تمام خاطرات اکنون عمومی هستند';

  @override
  String get newMemory => '✨ خاطره جدید';

  @override
  String get editMemory => '✏️ ویرایش خاطره';

  @override
  String get memoryContentHint => 'من دوست دارم بستنی بخورم...';

  @override
  String get failedToSaveMemory => 'خطا در ذخیره. لطفاً اتصال خود را بررسی کنید.';

  @override
  String get saveMemory => 'ذخیره خاطره';

  @override
  String get retry => 'تلاش دوباره';

  @override
  String get createActionItem => 'ایجاد موارد اقدام';

  @override
  String get editActionItem => 'ویرایش موارد اقدام';

  @override
  String get actionItemDescriptionHint => 'چه چیزی باید انجام شود؟';

  @override
  String get actionItemDescriptionEmpty => 'توصیف موارد اقدام نمی‌تواند خالی باشد.';

  @override
  String get actionItemUpdated => 'موارد اقدام به‌روزرسانی شد';

  @override
  String get failedToUpdateActionItem => 'خطا در به‌روزرسانی موارد اقدام';

  @override
  String get actionItemCreated => 'موارد اقدام ایجاد شد';

  @override
  String get failedToCreateActionItem => 'خطا در ایجاد موارد اقدام';

  @override
  String get dueDate => 'تاریخ سررسید';

  @override
  String get time => 'زمان';

  @override
  String get addDueDate => 'افزودن تاریخ سررسید';

  @override
  String get pressDoneToSave => 'برای ذخیره، Done را فشار دهید';

  @override
  String get pressDoneToCreate => 'برای ایجاد، Done را فشار دهید';

  @override
  String get filterAll => 'همه';

  @override
  String get filterSystem => 'درباره شما';

  @override
  String get filterInteresting => 'بینش‌ها';

  @override
  String get filterManual => 'دستی';

  @override
  String get completed => 'تکمیل شده';

  @override
  String get markComplete => 'علامت‌گذاری به‌عنوان تکمیل شده';

  @override
  String get actionItemDeleted => 'موارد اقدام حذف شد';

  @override
  String get failedToDeleteActionItem => 'خطا در حذف موارد اقدام';

  @override
  String get deleteActionItemConfirmTitle => 'حذف موارد اقدام';

  @override
  String get deleteActionItemConfirmMessage => 'آیا مطمئن هستید که می‌خواهید این موارد اقدام را حذف کنید؟';

  @override
  String get appLanguage => 'زبان برنامه';

  @override
  String get appInterfaceSectionTitle => 'رابط برنامه';

  @override
  String get speechTranscriptionSectionTitle => 'سخن و رونویسی';

  @override
  String get languageSettingsHelperText =>
      'زبان برنامه منوها و دکمه‌ها را تغییر می‌دهد. زبان سخن بر نحوه رونویسی ضبط‌های شما تأثیر می‌گذارد.';

  @override
  String get translationNotice => 'اطلاع ترجمه';

  @override
  String get translationNoticeMessage =>
      'Omi گفتگو‌های شما را به زبان اصلی شما ترجمه می‌کند. هر زمانی در Settings → Profiles آن را به‌روزرسانی کنید.';

  @override
  String get pleaseCheckInternetConnection => 'لطفاً اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید';

  @override
  String get pleaseSelectReason => 'لطفاً دلیلی را انتخاب کنید';

  @override
  String get tellUsMoreWhatWentWrong => 'بیشتر در مورد آنچه اشتباه رفته است به ما بگویید...';

  @override
  String get selectText => 'انتخاب متن';

  @override
  String maximumGoalsAllowed(int count) {
    return 'حداکثر $count اهداف مجاز است';
  }

  @override
  String get conversationCannotBeMerged => 'این گفتگو نمی‌تواند ادغام شود (قفل شده یا در حال ادغام)';

  @override
  String get pleaseEnterFolderName => 'لطفاً نام پوشه را وارد کنید';

  @override
  String get failedToCreateFolder => 'خطا در ایجاد پوشه';

  @override
  String get failedToUpdateFolder => 'خطا در به‌روزرسانی پوشه';

  @override
  String get folderName => 'نام پوشه';

  @override
  String get descriptionOptional => 'توضیح (اختیاری)';

  @override
  String get failedToDeleteFolder => 'حذف پوشه ناموفق بود';

  @override
  String get editFolder => 'ویرایش پوشه';

  @override
  String get deleteFolder => 'حذف پوشه';

  @override
  String get transcriptCopiedToClipboard => 'رونوشت به کلیپ بورد کپی شد';

  @override
  String get summaryCopiedToClipboard => 'خلاصه به کلیپ بورد کپی شد';

  @override
  String get conversationUrlCouldNotBeShared => 'URL گفتگو را نتوانستیم اشتراک‌گذاری کنیم.';

  @override
  String get urlCopiedToClipboard => 'URL به کلیپ بورد کپی شد';

  @override
  String get exportTranscript => 'صادرات رونوشت';

  @override
  String get exportSummary => 'صادرات خلاصه';

  @override
  String get exportButton => 'صادرات';

  @override
  String get actionItemsCopiedToClipboard => 'مورد اقدامات به کلیپ بورد کپی شد';

  @override
  String get summarize => 'خلاصه سازی';

  @override
  String get generateSummary => 'تولید خلاصه';

  @override
  String get conversationNotFoundOrDeleted => 'گفتگو یافت نشد یا حذف شده است';

  @override
  String get deleteMemory => 'حذف یادآوری';

  @override
  String get thisActionCannotBeUndone => 'این عمل قابل بازگشت نیست.';

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
  String get noMemoriesInCategory => 'هیچ یادآوری در این دسته‌بندی وجود ندارد';

  @override
  String get addYourFirstMemory => 'اولین یادآوری خود را اضافه کنید';

  @override
  String get firmwareDisconnectUsb => 'قطع اتصال USB';

  @override
  String get firmwareUsbWarning => 'اتصال USB در حین بروزرسانی ممکن است دستگاه شما را آسیب برساند.';

  @override
  String get firmwareBatteryAbove15 => 'شارژ باتری بالای 15 درصد';

  @override
  String get firmwareEnsureBattery => 'مطمئن شوید دستگاه شما 15 درصد شارژ دارد.';

  @override
  String get firmwareStableConnection => 'اتصال پایدار';

  @override
  String get firmwareConnectWifi => 'به Wi-Fi یا شبکه محمول متصل شوید.';

  @override
  String failedToStartUpdate(String error) {
    return 'شروع بروزرسانی ناموفق بود: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'قبل از بروزرسانی، مطمئن شوید:';

  @override
  String get confirmed => 'تأیید شد!';

  @override
  String get release => 'انتشار';

  @override
  String get slideToUpdate => 'برای بروزرسانی بکشید';

  @override
  String copiedToClipboard(String title) {
    return '$title به کلیپ بورد کپی شد';
  }

  @override
  String get batteryLevel => 'سطح باتری';

  @override
  String get charging => 'در حال شارژ';

  @override
  String get productUpdate => 'بروزرسانی محصول';

  @override
  String get offline => 'آفلاین';

  @override
  String get available => 'دستیاب';

  @override
  String get unpairDeviceDialogTitle => 'جدا کردن دستگاه';

  @override
  String get unpairDeviceDialogMessage =>
      'این کار دستگاه را جدا می‌کند تا بتوان آن را به تلفن دیگری متصل کرد. برای تکمیل فرآیند، باید به تنظیمات > Bluetooth رفته و دستگاه را فراموش کنید.';

  @override
  String get unpair => 'جدا کردن';

  @override
  String get unpairAndForgetDevice => 'جدا کردن و فراموش کردن دستگاه';

  @override
  String get unknownDevice => 'نامشخص';

  @override
  String get unknown => 'نامشخص';

  @override
  String get productName => 'نام محصول';

  @override
  String get serialNumber => 'شماره سریال';

  @override
  String get connected => 'متصل';

  @override
  String get privacyPolicyTitle => 'سیاست حریم خصوصی';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label کپی شد';
  }

  @override
  String get noApiKeysYet => 'هیچ کلید API وجود ندارد';

  @override
  String get createKeyToGetStarted => 'کلید را برای شروع ایجاد کنید';

  @override
  String get configureSttProvider => 'ارائه‌دهنده تبدیل گفتار به متن را پیکربندی کنید';

  @override
  String get setWhenConversationsAutoEnd => 'تنظیم زمان خاتمه خودکار گفتگوها';

  @override
  String get importDataFromOtherSources => 'واردات داده از منابع دیگر';

  @override
  String get debugAndDiagnostics => 'اشکال‌زدایی و تشخیص';

  @override
  String get autoDeletesAfter3Days => 'به‌طور خودکار بعد از 3 روز حذف می‌شود.';

  @override
  String get helpsDiagnoseIssues => 'کمک به تشخیص مشکلات';

  @override
  String get exportStartedMessage => 'صادرات شروع شد. این کار ممکن است چند ثانیه طول بکشد...';

  @override
  String get exportConversationsToJson => 'صادرات گفتگوها به فایل JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'نمودار دانش با موفقیت حذف شد';

  @override
  String failedToDeleteGraph(String error) {
    return 'حذف نمودار ناموفق بود: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'پاک کردن تمام گره‌ها و اتصالات';

  @override
  String get addToClaudeDesktopConfig => 'افزودن به claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'دستیارهای هوش مصنوعی را به داده‌های خود متصل کنید';

  @override
  String get useYourMcpApiKey => 'از کلید MCP API خود استفاده کنید';

  @override
  String get realTimeTranscript => 'رونوشت بلادرنگ';

  @override
  String get experimental => 'تجربی';

  @override
  String get transcriptionDiagnostics => 'تشخیص تبدیل گفتار به متن';

  @override
  String get detailedDiagnosticMessages => 'پیام‌های تشخیص تفصیلی';

  @override
  String get autoCreateSpeakers => 'ایجاد خودکار سخنرانان';

  @override
  String get autoCreateWhenNameDetected => 'ایجاد خودکار هنگام تشخیص نام';

  @override
  String get followUpQuestions => 'سؤالات دنبال‌کننده';

  @override
  String get suggestQuestionsAfterConversations => 'پیشنهاد سؤالات بعد از گفتگوها';

  @override
  String get goalTracker => 'ردیاب اهداف';

  @override
  String get trackPersonalGoalsOnHomepage => 'ردیابی اهداف شخصی خود در صفحه اصلی';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'توضیح مورد اقدام نمی‌تواند خالی باشد';

  @override
  String get saved => 'ذخیره شد';

  @override
  String get overdue => 'تأخیری';

  @override
  String get failedToUpdateDueDate => 'بروزرسانی تاریخ سررسید ناموفق بود';

  @override
  String get markIncomplete => 'علامت‌گذاری به‌عنوان ناتمام';

  @override
  String get editDueDate => 'ویرایش تاریخ سررسید';

  @override
  String get setDueDate => 'تنظیم تاریخ سررسید';

  @override
  String get clearDueDate => 'پاک کردن تاریخ سررسید';

  @override
  String get failedToClearDueDate => 'پاک کردن تاریخ سررسید ناموفق بود';

  @override
  String get mondayAbbr => 'د';

  @override
  String get tuesdayAbbr => 'س';

  @override
  String get wednesdayAbbr => 'چ';

  @override
  String get thursdayAbbr => 'پ';

  @override
  String get fridayAbbr => 'ج';

  @override
  String get saturdayAbbr => 'ش';

  @override
  String get sundayAbbr => 'ی';

  @override
  String get howDoesItWork => 'چگونه کار می‌کند؟';

  @override
  String get sdCardSyncDescription => 'همگام‌سازی کارت SD، یادآوری‌های شما را از کارت SD به برنامه وارد می‌کند';

  @override
  String get checksForAudioFiles => 'بررسی فایل‌های صوتی در کارت SD';

  @override
  String get omiSyncsAudioFiles => 'سپس Omi فایل‌های صوتی را با سرور همگام می‌کند';

  @override
  String get serverProcessesAudio => 'سرور فایل‌های صوتی را پردازش می‌کند و یادآوری‌ها را ایجاد می‌کند';

  @override
  String get youreAllSet => 'شما آماده‌اید!';

  @override
  String get welcomeToOmiDescription =>
      'خوش‌آمدید به Omi! دستیار هوش مصنوعی شما آماده‌است تا در گفتگوها، وظایف و بسیاری مورد دیگر به شما کمک کند.';

  @override
  String get startUsingOmi => 'شروع استفاده از Omi';

  @override
  String get back => 'بازگشت';

  @override
  String get keyboardShortcuts => 'میانبرهای صفحه‌کلید';

  @override
  String get toggleControlBar => 'تبدیل نوار کنترل';

  @override
  String get pressKeys => 'کلیدها را فشار دهید...';

  @override
  String get cmdRequired => '⌘ مورد نیاز است';

  @override
  String get invalidKey => 'کلید نامعتبر';

  @override
  String get space => 'فاصله';

  @override
  String get search => 'جستجو';

  @override
  String get searchPlaceholder => 'جستجو...';

  @override
  String get untitledConversation => 'گفتگوی بدون عنوان';

  @override
  String countRemaining(String count) {
    return '$count باقی‌مانده';
  }

  @override
  String get addGoal => 'افزودن هدف';

  @override
  String get editGoal => 'ویرایش هدف';

  @override
  String get icon => 'نماد';

  @override
  String get goalTitle => 'عنوان هدف';

  @override
  String get current => 'فعلی';

  @override
  String get target => 'هدف';

  @override
  String get saveGoal => 'ذخیره';

  @override
  String get goals => 'اهداف';

  @override
  String get tapToAddGoal => 'برای افزودن هدف ضربه بزنید';

  @override
  String welcomeBack(String name) {
    return 'خوش‌آمدید، $name';
  }

  @override
  String get yourConversations => 'گفتگوهای شما';

  @override
  String get reviewAndManageConversations => 'بررسی و مدیریت گفتگوهای ضبط‌شده خود';

  @override
  String get startCapturingConversations => 'برای مشاهده گفتگوها در اینجا، شروع به ضبط گفتگوها با دستگاه Omi خود کنید.';

  @override
  String get useMobileAppToCapture => 'برای ضبط صوت از برنامه موبایل خود استفاده کنید';

  @override
  String get conversationsProcessedAutomatically => 'گفتگوها به‌طور خودکار پردازش می‌شوند';

  @override
  String get getInsightsInstantly => 'بلافاصله بینش‌ها و خلاصه‌ها را دریافت کنید';

  @override
  String get showAll => 'نمایش همه';

  @override
  String get noTasksForToday => 'امروز هیچ وظیفه‌ای وجود ندارد.\nاز Omi وظایف بیشتری بخواهید یا به‌صورت دستی بسازید.';

  @override
  String get dailyScore => 'امتیاز روزانه';

  @override
  String get dailyScoreDescription => 'امتیازی برای کمک به شما\nدر تمرکز بر اجرا.';

  @override
  String get searchResults => 'نتایج جستجو';

  @override
  String get actionItems => 'موارد اقدام';

  @override
  String get tasksToday => 'امروز';

  @override
  String get tasksTomorrow => 'فردا';

  @override
  String get tasksNoDeadline => 'بدون سررسید';

  @override
  String get tasksLater => 'بعدتر';

  @override
  String get loadingTasks => 'در حال بارگذاری وظایف...';

  @override
  String get tasks => 'وظایف';

  @override
  String get swipeTasksToIndent => 'برای تورفتگی وظایف را بکشید، بین دسته‌بندی‌ها بکشید';

  @override
  String get create => 'ایجاد';

  @override
  String get noTasksYet => 'هیچ وظیفه‌ای وجود ندارد';

  @override
  String get tasksFromConversationsWillAppear =>
      'وظایف از گفتگوهای شما در اینجا ظاهر می‌شوند.\nبرای افزودن دستی بر روی ایجاد کلیک کنید.';

  @override
  String get monthJan => 'ژان';

  @override
  String get monthFeb => 'فور';

  @override
  String get monthMar => 'مار';

  @override
  String get monthApr => 'آپر';

  @override
  String get monthMay => 'می';

  @override
  String get monthJun => 'ژوئ';

  @override
  String get monthJul => 'جول';

  @override
  String get monthAug => 'اوت';

  @override
  String get monthSep => 'سپت';

  @override
  String get monthOct => 'اکت';

  @override
  String get monthNov => 'نوا';

  @override
  String get monthDec => 'دسا';

  @override
  String get timePM => 'بعدازظهر';

  @override
  String get timeAM => 'قبل‌ازظهر';

  @override
  String get actionItemUpdatedSuccessfully => 'مورد اقدام با موفقیت بروزرسانی شد';

  @override
  String get actionItemCreatedSuccessfully => 'مورد اقدام با موفقیت ایجاد شد';

  @override
  String get actionItemDeletedSuccessfully => 'مورد اقدام با موفقیت حذف شد';

  @override
  String get deleteActionItem => 'حذف مورد اقدام';

  @override
  String get deleteActionItemConfirmation =>
      'آیا مطمئن هستید که می‌خواهید این مورد اقدام را حذف کنید؟ این عمل قابل بازگشت نیست.';

  @override
  String get enterActionItemDescription => 'توضیح مورد اقدام را وارد کنید...';

  @override
  String get markAsCompleted => 'علامت‌گذاری به‌عنوان تکمیل‌شده';

  @override
  String get setDueDateAndTime => 'تنظیم تاریخ و زمان سررسید';

  @override
  String get reloadingApps => 'در حال بارگذاری مجدد برنامه‌ها...';

  @override
  String get loadingApps => 'در حال بارگذاری برنامه‌ها...';

  @override
  String get browseInstallCreateApps => 'جستجو، نصب و ایجاد برنامه‌ها';

  @override
  String get all => 'همه';

  @override
  String get open => 'باز کردن';

  @override
  String get install => 'نصب';

  @override
  String get noAppsAvailable => 'هیچ برنامه‌ای در دسترس نیست';

  @override
  String get unableToLoadApps => 'نتوانستیم برنامه‌ها را بارگذاری کنیم';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'سعی کنید شرایط جستجو یا فیلترها را تنظیم کنید';

  @override
  String get checkBackLaterForNewApps => 'بعدتر برای برنامه‌های جدید بازگردید';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'لطفا اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید';

  @override
  String get createNewApp => 'ایجاد برنامه جدید';

  @override
  String get buildSubmitCustomOmiApp => 'ساخت و ارسال برنامه Omi سفارشی خود';

  @override
  String get submittingYourApp => 'درحال ارسال برنامه شما...';

  @override
  String get preparingFormForYou => 'فرم را برای شما آماده می‌کنیم...';

  @override
  String get appDetails => 'جزئیات برنامه';

  @override
  String get paymentDetails => 'جزئیات پرداخت';

  @override
  String get previewAndScreenshots => 'پیش‌نمایش و عکس‌های صفحه';

  @override
  String get appCapabilities => 'توانایی‌های برنامه';

  @override
  String get aiPrompts => 'دستورالعمل‌های هوش مصنوعی';

  @override
  String get chatPrompt => 'دستورالعمل چت';

  @override
  String get chatPromptPlaceholder =>
      'شما یک برنامه عالی هستید، کار شما پاسخ‌دهی به سؤالات کاربر و خوب احساس کردن آنها است...';

  @override
  String get conversationPrompt => 'دستورالعمل گفتگو';

  @override
  String get conversationPromptPlaceholder =>
      'شما یک برنامه عالی هستید، رونوشت و خلاصه یک گفتگو را دریافت خواهید کرد...';

  @override
  String get notificationScopes => 'محدوده‌های اطلاع‌رسانی';

  @override
  String get appPrivacyAndTerms => 'حریم خصوصی و شرایط برنامه';

  @override
  String get makeMyAppPublic => 'برنامه خود را عمومی کنید';

  @override
  String get submitAppTermsAgreement =>
      'با ارسال این برنامه، من با شرایط خدمات و سیاست حریم خصوصی Omi AI موافقت می‌کنم';

  @override
  String get submitApp => 'ارسال برنامه';

  @override
  String get needHelpGettingStarted => 'برای شروع کمک نیاز دارید؟';

  @override
  String get clickHereForAppBuildingGuides => 'برای راهنماهای ساخت برنامه و مستندات اینجا کلیک کنید';

  @override
  String get submitAppQuestion => 'ارسال برنامه؟';

  @override
  String get submitAppPublicDescription =>
      'برنامه شما بررسی می‌شود و عمومی می‌شود. می‌توانید بلافاصله از آن استفاده کنید، حتی در حین بررسی!';

  @override
  String get submitAppPrivateDescription =>
      'برنامه شما بررسی می‌شود و به‌صورت خصوصی برای شما در دسترس قرار می‌گیرد. می‌توانید بلافاصله از آن استفاده کنید، حتی در حین بررسی!';

  @override
  String get startEarning => 'شروع به درآمد! 💰';

  @override
  String get connectStripeOrPayPal => 'Stripe یا PayPal را متصل کنید تا برای برنامه خود پرداخت دریافت کنید.';

  @override
  String get connectNow => 'اتصال کنید';

  @override
  String get installsCount => 'نصب‌ها';

  @override
  String get uninstallApp => 'حذف نصب برنامه';

  @override
  String get subscribe => 'اشتراک';

  @override
  String get dataAccessNotice => 'اطلاع دسترسی به داده';

  @override
  String get dataAccessWarning =>
      'این برنامه به داده‌های شما دسترسی خواهد داشت. Omi AI مسئول نحوه استفاده، تغییر یا حذف داده‌های شما توسط این برنامه نیست';

  @override
  String get installApp => 'نصب برنامه';

  @override
  String get betaTesterNotice =>
      'شما یک آزمایشگر بتا برای این برنامه هستید. هنوز عمومی نیست. پس از تأیید عمومی می‌شود.';

  @override
  String get appUnderReviewOwner =>
      'برنامه شما در حال بررسی است و تنها برای شما قابل مشاهده است. پس از تأیید عمومی می‌شود.';

  @override
  String get appRejectedNotice =>
      'برنامه شما رد شده است. لطفا جزئیات برنامه را به‌روز کنید و برای بررسی مجدد ارسال کنید.';

  @override
  String get setupSteps => 'مراحل راه‌اندازی';

  @override
  String get setupInstructions => 'دستورالعمل‌های راه‌اندازی';

  @override
  String get integrationInstructions => 'دستورالعمل‌های یکپارچگی';

  @override
  String get preview => 'پیش‌نمایش';

  @override
  String get aboutTheApp => 'درباره برنامه';

  @override
  String get chatPersonality => 'شخصیت چت';

  @override
  String get ratingsAndReviews => 'امتیازات و نظرات';

  @override
  String get noRatings => 'بدون امتیاز';

  @override
  String ratingsCount(String count) {
    return '$count+ امتیاز';
  }

  @override
  String get errorActivatingApp => 'خطا در فعال‌سازی برنامه';

  @override
  String get integrationSetupRequired => 'اگر این یک برنامه یکپارچگی است، مطمئن شوید که راه‌اندازی تکمیل شده است.';

  @override
  String get installed => 'نصب‌شده';

  @override
  String get appIdLabel => 'شناسه برنامه';

  @override
  String get appNameLabel => 'نام برنامه';

  @override
  String get appNamePlaceholder => 'برنامه فوق‌العاده من';

  @override
  String get pleaseEnterAppName => 'لطفا نام برنامه را وارد کنید';

  @override
  String get categoryLabel => 'دسته‌بندی';

  @override
  String get selectCategory => 'انتخاب دسته‌بندی';

  @override
  String get descriptionLabel => 'توضیح';

  @override
  String get appDescriptionPlaceholder =>
      'برنامه فوق‌العاده من یک برنامه عالی است که کارهای فوق‌العاده انجام می‌دهد. این بهترین برنامه است!';

  @override
  String get pleaseProvideValidDescription => 'لطفا توضیح معتبری بدهید';

  @override
  String get appPricingLabel => 'قیمت برنامه';

  @override
  String get noneSelected => 'هیچ کدام انتخاب نشده';

  @override
  String get appIdCopiedToClipboard => 'شناسه برنامه به کلیپ بورد کپی شد';

  @override
  String get appCategoryModalTitle => 'دسته‌بندی برنامه';

  @override
  String get pricingFree => 'رایگان';

  @override
  String get pricingPaid => 'پولی';

  @override
  String get loadingCapabilities => 'در حال بارگذاری توانایی‌ها...';

  @override
  String get filterInstalled => 'نصب‌شده';

  @override
  String get filterMyApps => 'برنامه‌های من';

  @override
  String get clearSelection => 'پاک کردن انتخاب';

  @override
  String get filterCategory => 'دسته‌بندی';

  @override
  String get rating4PlusStars => '4+ ستاره';

  @override
  String get rating3PlusStars => '3+ ستاره';

  @override
  String get rating2PlusStars => '2+ ستاره';

  @override
  String get rating1PlusStars => '1+ ستاره';

  @override
  String get filterRating => 'امتیاز';

  @override
  String get filterCapabilities => 'توانایی‌ها';

  @override
  String get noNotificationScopesAvailable => 'هیچ محدوده اطلاع‌رسانی در دسترس نیست';

  @override
  String get popularApps => 'برنامه‌های محبوب';

  @override
  String get pleaseProvidePrompt => 'لطفا دستورالعمل بدهید';

  @override
  String chatWithAppName(String appName) {
    return 'چت با $appName';
  }

  @override
  String get defaultAiAssistant => 'دستیار هوش مصنوعی پیش‌فرض';

  @override
  String get readyToChat => '✨ آماده برای چت!';

  @override
  String get connectionNeeded => '🌐 اتصال لازم است';

  @override
  String get startConversation => 'یک گفتگو شروع کنید و بگذارید جادو شروع شود';

  @override
  String get checkInternetConnection => 'لطفا اتصال اینترنت خود را بررسی کنید';

  @override
  String get wasThisHelpful => 'آیا این مفید بود؟';

  @override
  String get thankYouForFeedback => 'از بازخورد شما سپاسگزاریم!';

  @override
  String get maxFilesUploadError => 'شما می‌توانید فقط 4 فایل را همزمان آپلود کنید';

  @override
  String get attachedFiles => '📎 فایل‌های پیوست‌شده';

  @override
  String get takePhoto => 'گرفتن عکس';

  @override
  String get captureWithCamera => 'ضبط با دوربین';

  @override
  String get selectImages => 'انتخاب تصاویر';

  @override
  String get chooseFromGallery => 'انتخاب از گالری';

  @override
  String get selectFile => 'انتخاب یک فایل';

  @override
  String get chooseAnyFileType => 'انتخاب هر نوع فایل';

  @override
  String get cannotReportOwnMessages => 'نمی‌توانید پیام‌های خود را گزارش کنید';

  @override
  String get messageReportedSuccessfully => '✅ پیام با موفقیت گزارش شد';

  @override
  String get confirmReportMessage => 'آیا مطمئن هستید که می‌خواهید این پیام را گزارش کنید؟';

  @override
  String get selectChatAssistant => 'انتخاب دستیار چت';

  @override
  String get enableMoreApps => 'فعال‌سازی برنامه‌های بیشتر';

  @override
  String get chatCleared => 'چت پاک شد';

  @override
  String get clearChatTitle => 'پاک کردن چت؟';

  @override
  String get confirmClearChat => 'آیا مطمئن هستید که می‌خواهید چت را پاک کنید؟ این عمل قابل بازگشت نیست.';

  @override
  String get copy => 'کپی';

  @override
  String get share => 'اشتراک‌گذاری';

  @override
  String get report => 'گزارش';

  @override
  String get microphonePermissionRequired => 'برای تماس، اجازه میکروفون لازم است';

  @override
  String get microphonePermissionDenied =>
      'اجازه میکروفون رد شد. لطفا اجازه را در تنظیمات سیستم > حریم خصوصی و امنیت > میکروفون بدهید.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'بررسی اجازه میکروفون ناموفق بود: $error';
  }

  @override
  String get failedToTranscribeAudio => 'تبدیل صوت به متن ناموفق بود';

  @override
  String get transcribing => 'درحال تبدیل...';

  @override
  String get transcriptionFailed => 'تبدیل صوت به متن ناموفق بود';

  @override
  String get discardedConversation => 'گفتگوی دورریخته‌شده';

  @override
  String get at => 'در';

  @override
  String get from => 'از';

  @override
  String get copied => 'کپی شد!';

  @override
  String get copyLink => 'کپی پیوند';

  @override
  String get hideTranscript => 'پنهان کردن رونوشت';

  @override
  String get viewTranscript => 'مشاهده رونوشت';

  @override
  String get conversationDetails => 'جزئیات گفتگو';

  @override
  String get transcript => 'رونوشت';

  @override
  String segmentsCount(int count) {
    return '$count بخش';
  }

  @override
  String get noTranscriptAvailable => 'رونوشتی در دسترس نیست';

  @override
  String get noTranscriptMessage => 'این گفتگو رونوشت ندارد.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL گفتگو را نتوانستیم ایجاد کنیم.';

  @override
  String get failedToGenerateConversationLink => 'ایجاد پیوند گفتگو ناموفق بود';

  @override
  String get failedToGenerateShareLink => 'ایجاد پیوند اشتراک‌گذاری ناموفق بود';

  @override
  String get reloadingConversations => 'در حال بارگذاری مجدد گفتگوها...';

  @override
  String get user => 'کاربر';

  @override
  String get starred => 'ستاره‌دار';

  @override
  String get date => 'تاریخ';

  @override
  String get noResultsFound => 'نتیجه‌ای یافت نشد';

  @override
  String get tryAdjustingSearchTerms => 'سعی کنید شرایط جستجو را تنظیم کنید';

  @override
  String get starConversationsToFindQuickly => 'گفتگوها را ستاره‌دار کنید تا بتوانید به سرعت آنها را اینجا پیدا کنید';

  @override
  String noConversationsOnDate(String date) {
    return 'گفتگویی در $date وجود ندارد';
  }

  @override
  String get trySelectingDifferentDate => 'سعی کنید تاریخ متفاوتی را انتخاب کنید';

  @override
  String get conversations => 'گفتگوها';

  @override
  String get chat => 'چت';

  @override
  String get actions => 'اقدامات';

  @override
  String get syncAvailable => 'همگام‌سازی در دسترس';

  @override
  String get referAFriend => 'معرفی یک دوست';

  @override
  String get help => 'کمک';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'ارتقا به Pro';

  @override
  String get getOmiDevice => 'دستگاه Omi را بگیرید';

  @override
  String get wearableAiCompanion => 'دستیار هوش مصنوعی قابل پوشیدن';

  @override
  String get loadingMemories => 'در حال بارگذاری یادآوری‌ها...';

  @override
  String get allMemories => 'تمام یادآوری‌ها';

  @override
  String get aboutYou => 'درباره شما';

  @override
  String get manual => 'دستی';

  @override
  String get loadingYourMemories => 'در حال بارگذاری یادآوری‌های شما...';

  @override
  String get createYourFirstMemory => 'اولین یادآوری خود را ایجاد کنید تا شروع کنید';

  @override
  String get tryAdjustingFilter => 'سعی کنید جستجو یا فیلتر خود را تنظیم کنید';

  @override
  String get whatWouldYouLikeToRemember => 'می‌خواهید چه چیزی را یاد بگیرید؟';

  @override
  String get category => 'دسته‌بندی';

  @override
  String get public => 'عمومی';

  @override
  String get failedToSaveCheckConnection => 'ذخیره ناموفق بود. لطفا اتصال خود را بررسی کنید.';

  @override
  String get createMemory => 'ایجاد یادآوری';

  @override
  String get deleteMemoryConfirmation =>
      'آیا مطمئن هستید که می‌خواهید این یادآوری را حذف کنید؟ این عمل قابل بازگشت نیست.';

  @override
  String get makePrivate => 'خصوصی کردن';

  @override
  String get organizeAndControlMemories => 'تنظیم و کنترل یادآوری‌های خود';

  @override
  String get total => 'کل';

  @override
  String get makeAllMemoriesPrivate => 'تمام یادآوری‌ها را خصوصی کنید';

  @override
  String get setAllMemoriesToPrivate => 'تنظیم تمام یادآوری‌ها به حالت خصوصی';

  @override
  String get makeAllMemoriesPublic => 'تمام یادآوری‌ها را عمومی کنید';

  @override
  String get setAllMemoriesToPublic => 'تنظیم تمام یادآوری‌ها به حالت عمومی';

  @override
  String get permanentlyRemoveAllMemories => 'حذف دائمی تمام یادآوری‌ها از Omi';

  @override
  String get allMemoriesAreNowPrivate => 'تمام یادآوری‌ها اکنون خصوصی هستند';

  @override
  String get allMemoriesAreNowPublic => 'تمام یادآوری‌ها اکنون عمومی هستند';

  @override
  String get clearOmisMemory => 'پاک کردن حافظه Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'آیا مطمئن هستید که می‌خواهید حافظه Omi را پاک کنید؟ این عمل قابل بازگشت نیست و تمام $count یادآوری را به‌طور دائمی حذف می‌کند.';
  }

  @override
  String get omisMemoryCleared => 'حافظه Omi درباره شما پاک شده است';

  @override
  String get welcomeToOmi => 'خوش‌آمدید به Omi';

  @override
  String get continueWithApple => 'ادامه با Apple';

  @override
  String get continueWithGoogle => 'ادامه با Google';

  @override
  String get byContinuingYouAgree => 'با ادامه، شما موافقت می‌کنید با ';

  @override
  String get termsOfService => 'شرایط خدمات';

  @override
  String get and => ' و ';

  @override
  String get dataAndPrivacy => 'داده‌ها و حریم‌خصوصی';

  @override
  String get secureAuthViaAppleId => 'احراز هویت امن از طریق Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'احراز هویت امن از طریق حساب Google';

  @override
  String get whatWeCollect => 'آنچه ما جمع‌آوری می‌کنیم';

  @override
  String get dataCollectionMessage =>
      'با ادامه، گفتگوهای شما، ضبط‌ها و اطلاعات شخصی به‌طور ایمن در سرورهای ما ذخیره می‌شوند تا بینش‌های مبتنی بر هوش مصنوعی ارائه دهند و تمام ویژگی‌های برنامه را فعال کنند.';

  @override
  String get dataProtection => 'محافظت از داده‌ها';

  @override
  String get yourDataIsProtected => 'داده‌های شما محافظت شده و تحت حاکمیت ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'لطفاً زبان اصلی خود را انتخاب کنید';

  @override
  String get chooseYourLanguage => 'زبان خود را انتخاب کنید';

  @override
  String get selectPreferredLanguageForBestExperience => 'زبان ترجیحی خود را برای بهترین تجربه Omi انتخاب کنید';

  @override
  String get searchLanguages => 'جستجو زبان‌ها...';

  @override
  String get selectALanguage => 'یک زبان را انتخاب کنید';

  @override
  String get tryDifferentSearchTerm => 'یک واژه جستجویی متفاوت را امتحان کنید';

  @override
  String get pleaseEnterYourName => 'لطفاً نام خود را وارد کنید';

  @override
  String get nameMustBeAtLeast2Characters => 'نام باید حداقل ۲ کاراکتر باشد';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'به ما بگویید چگونه می‌خواهید صدا زده شوید. این به شخصی‌سازی تجربه Omi شما کمک می‌کند.';

  @override
  String charactersCount(int count) {
    return '$count کاراکتر';
  }

  @override
  String get enableFeaturesForBestExperience => 'ویژگی‌ها را برای بهترین تجربه Omi بر روی دستگاه خود فعال کنید.';

  @override
  String get microphoneAccess => 'دسترسی میکروفن';

  @override
  String get recordAudioConversations => 'ضبط گفتگوهای صوتی';

  @override
  String get microphoneAccessDescription => 'Omi برای ضبط گفتگوهای شما و ارائه رونوشت‌ها به دسترسی میکروفن نیاز دارد.';

  @override
  String get screenRecording => 'ضبط صفحه';

  @override
  String get captureSystemAudioFromMeetings => 'ثبت صوت سیستم از جلسات';

  @override
  String get screenRecordingDescription =>
      'Omi برای ثبت صوت سیستم از جلسات مبتنی بر مرورگر شما به مجوز ضبط صفحه نیاز دارد.';

  @override
  String get accessibility => 'دسترسی‌پذیری';

  @override
  String get detectBrowserBasedMeetings => 'تشخیص جلسات مبتنی بر مرورگر';

  @override
  String get accessibilityDescription =>
      'Omi برای تشخیص زمانی که به جلسات Zoom، Meet یا Teams در مرورگر خود پیوند می‌زنید به مجوز دسترسی‌پذیری نیاز دارد.';

  @override
  String get pleaseWait => 'لطفاً منتظر بمانید...';

  @override
  String get joinTheCommunity => 'به جامعه بپیوندید!';

  @override
  String get loadingProfile => 'در حال بارگذاری پروفایل...';

  @override
  String get profileSettings => 'تنظیمات پروفایل';

  @override
  String get noEmailSet => 'ایمیلی تنظیم نشده';

  @override
  String get userIdCopiedToClipboard => 'ID کاربر در کلیپ‌بورد کپی شد';

  @override
  String get yourInformation => 'اطلاعات شما';

  @override
  String get setYourName => 'نام خود را تنظیم کنید';

  @override
  String get changeYourName => 'نام خود را تغییر دهید';

  @override
  String get voiceAndPeople => 'صوت و افراد';

  @override
  String get teachOmiYourVoice => 'Omi را صدای خود را یاد دهید';

  @override
  String get tellOmiWhoSaidIt => 'به Omi بگویید کی آن را گفت 🗣️';

  @override
  String get payment => 'پرداخت';

  @override
  String get addOrChangeYourPaymentMethod => 'روش پرداخت خود را اضافه یا تغییر دهید';

  @override
  String get preferences => 'ترجیحات';

  @override
  String get helpImproveOmiBySharing => 'با اشتراک‌گذاری داده‌های تحلیلی ناشناس به بهبود Omi کمک کنید';

  @override
  String get deleteAccount => 'حذف حساب';

  @override
  String get deleteYourAccountAndAllData => 'حساب خود و تمام داده‌های خود را حذف کنید';

  @override
  String get clearLogs => 'پاک کردن گزارش‌ها';

  @override
  String get debugLogsCleared => 'گزارش‌های اشکال‌زدایی پاک شدند';

  @override
  String get exportConversations => 'صادر کردن گفتگوها';

  @override
  String get exportAllConversationsToJson => 'تمام گفتگوهای خود را به یک فایل JSON صادر کنید.';

  @override
  String get conversationsExportStarted =>
      'صادرات گفتگوها آغاز شد. این ممکن است چند ثانیه طول بکشد، لطفاً منتظر بمانید.';

  @override
  String get mcpDescription =>
      'برای اتصال Omi به برنامه‌های دیگر برای خواندن، جستجو و مدیریت خاطرات و گفتگوهای خود. یک کلید ایجاد کنید تا شروع کنید.';

  @override
  String get apiKeys => 'کلیدهای API';

  @override
  String errorLabel(String error) {
    return 'خطا: $error';
  }

  @override
  String get noApiKeysFound => 'کلید API پیدا نشد. یکی ایجاد کنید تا شروع کنید.';

  @override
  String get advancedSettings => 'تنظیمات پیشرفته';

  @override
  String get triggersWhenNewConversationCreated => 'زمانی که یک گفتگوی جدید ایجاد شود فعال می‌شود.';

  @override
  String get triggersWhenNewTranscriptReceived => 'زمانی که رونوشت جدیدی دریافت شود فعال می‌شود.';

  @override
  String get realtimeAudioBytes => 'بایت‌های صوتی بلادرنگ';

  @override
  String get triggersWhenAudioBytesReceived => 'زمانی که بایت‌های صوتی دریافت شوند فعال می‌شود.';

  @override
  String get everyXSeconds => 'هر x ثانیه';

  @override
  String get triggersWhenDaySummaryGenerated => 'زمانی که خلاصه روزانه ایجاد شود فعال می‌شود.';

  @override
  String get tryLatestExperimentalFeatures => 'آخرین ویژگی‌های آزمایشی را از تیم Omi امتحان کنید.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'وضعیت تشخیصی سرویس رونویسی';

  @override
  String get enableDetailedDiagnosticMessages => 'پیام‌های تشخیصی دقیق از سرویس رونویسی را فعال کنید';

  @override
  String get autoCreateAndTagNewSpeakers => 'ایجاد و برچسب‌گذاری خودکار سخنرانان جدید';

  @override
  String get automaticallyCreateNewPerson => 'زمانی که نام در رونوشت تشخیص داده شود، یک فرد جدید ایجاد کنید.';

  @override
  String get pilotFeatures => 'ویژگی‌های آزمایشی';

  @override
  String get pilotFeaturesDescription => 'این ویژگی‌ها آزمایشات هستند و هیچ پشتیبانی تضمین نشده است.';

  @override
  String get suggestFollowUpQuestion => 'سؤال پیگیری را پیشنهاد کنید';

  @override
  String get saveSettings => 'ذخیره تنظیمات';

  @override
  String get syncingDeveloperSettings => 'در حال همگام‌سازی تنظیمات توسعه‌دهنده...';

  @override
  String get summary => 'خلاصه';

  @override
  String get auto => 'خودکار';

  @override
  String get noSummaryForApp => 'خلاصه‌ای برای این برنامه دردسترس نیست. برنامه دیگری را امتحان کنید برای نتایج بهتر.';

  @override
  String get tryAnotherApp => 'برنامه دیگر را امتحان کنید';

  @override
  String generatedBy(String appName) {
    return 'تولید شده توسط $appName';
  }

  @override
  String get overview => 'نمای کلی';

  @override
  String get otherAppResults => 'نتایج برنامه دیگر';

  @override
  String get unknownApp => 'برنامه نامشخص';

  @override
  String get noSummaryAvailable => 'خلاصه‌ای دردسترس نیست';

  @override
  String get conversationNoSummaryYet => 'این گفتگو هنوز خلاصه‌ای ندارد.';

  @override
  String get chooseSummarizationApp => 'برنامه خلاصه‌سازی را انتخاب کنید';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName به عنوان برنامه خلاصه‌سازی پیش‌فرض تنظیم شد';
  }

  @override
  String get letOmiChooseAutomatically => 'اجازه دهید Omi بهترین برنامه را به طور خودکار انتخاب کند';

  @override
  String get deleteConversationConfirmation =>
      'آیا مطمئنید که می‌خواهید این گفتگو را حذف کنید؟ این عمل قابل بازگشت نیست.';

  @override
  String get conversationDeleted => 'گفتگو حذف شد';

  @override
  String get generatingLink => 'در حال ایجاد پیوند...';

  @override
  String get editConversation => 'ویرایش گفتگو';

  @override
  String get conversationLinkCopiedToClipboard => 'پیوند گفتگو در کلیپ‌بورد کپی شد';

  @override
  String get conversationTranscriptCopiedToClipboard => 'رونوشت گفتگو در کلیپ‌بورد کپی شد';

  @override
  String get editConversationDialogTitle => 'ویرایش گفتگو';

  @override
  String get changeTheConversationTitle => 'عنوان گفتگو را تغییر دهید';

  @override
  String get conversationTitle => 'عنوان گفتگو';

  @override
  String get enterConversationTitle => 'عنوان گفتگو را وارد کنید...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'عنوان گفتگو با موفقیت به‌روز شد';

  @override
  String get failedToUpdateConversationTitle => 'به‌روزرسانی عنوان گفتگو ناموفق بود';

  @override
  String get errorUpdatingConversationTitle => 'خطا در به‌روزرسانی عنوان گفتگو';

  @override
  String get settingUp => 'در حال تنظیم...';

  @override
  String get startYourFirstRecording => 'اولین ضبط خود را شروع کنید';

  @override
  String get preparingSystemAudioCapture => 'در حال آماده‌سازی ثبت صوت سیستم';

  @override
  String get clickTheButtonToCaptureAudio =>
      'روی دکمه کلیک کنید تا صوت را برای رونوشت‌های زنده، بینش‌های هوش مصنوعی و ذخیره‌سازی خودکار ثبت کنید.';

  @override
  String get reconnecting => 'در حال اتصال مجدد...';

  @override
  String get recordingPaused => 'ضبط متوقف شد';

  @override
  String get recordingActive => 'ضبط فعال است';

  @override
  String get startRecording => 'شروع ضبط';

  @override
  String resumingInCountdown(String countdown) {
    return 'ادامه در ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'برای ادامه دادن روی پخش کلیک کنید';

  @override
  String get listeningForAudio => 'در حال گوش دادن برای صوت...';

  @override
  String get preparingAudioCapture => 'در حال آماده‌سازی ثبت صوت';

  @override
  String get clickToBeginRecording => 'برای شروع ضبط کلیک کنید';

  @override
  String get translated => 'ترجمه‌شده';

  @override
  String get liveTranscript => 'رونوشت زنده';

  @override
  String segmentsSingular(String count) {
    return '$count بخش';
  }

  @override
  String segmentsPlural(String count) {
    return '$count بخش';
  }

  @override
  String get startRecordingToSeeTranscript => 'برای مشاهده رونوشت زنده، ضبط را شروع کنید';

  @override
  String get paused => 'متوقف شد';

  @override
  String get initializing => 'در حال مقدار‌دهی اولیه...';

  @override
  String get recording => 'در حال ضبط';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'میکروفن تغییر یافت. ادامه در ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'برای ادامه دادن روی پخش یا برای پایان دادن روی توقف کلیک کنید';

  @override
  String get settingUpSystemAudioCapture => 'در حال تنظیم ثبت صوت سیستم';

  @override
  String get capturingAudioAndGeneratingTranscript => 'در حال ثبت صوت و تولید رونوشت';

  @override
  String get clickToBeginRecordingSystemAudio => 'برای شروع ضبط صوت سیستم کلیک کنید';

  @override
  String get you => 'شما';

  @override
  String speakerWithId(String speakerId) {
    return 'سخنران $speakerId';
  }

  @override
  String get translatedByOmi => 'ترجمه‌شده توسط omi';

  @override
  String get backToConversations => 'بازگشت به گفتگوها';

  @override
  String get systemAudio => 'سیستم';

  @override
  String get mic => 'میک';

  @override
  String audioInputSetTo(String deviceName) {
    return 'ورودی صوت تنظیم شده بر روی $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'خطا در تبدیل دستگاه صوتی: $error';
  }

  @override
  String get selectAudioInput => 'انتخاب ورودی صوت';

  @override
  String get loadingDevices => 'در حال بارگذاری دستگاه‌ها...';

  @override
  String get settingsHeader => 'تنظیمات';

  @override
  String get plansAndBilling => 'طرح‌ها و صورت‌حساب';

  @override
  String get calendarIntegration => 'یکپارچگی تقویم';

  @override
  String get dailySummary => 'خلاصه روزانه';

  @override
  String get developer => 'توسعه‌دهنده';

  @override
  String get about => 'درباره';

  @override
  String get selectTime => 'انتخاب زمان';

  @override
  String get accountGroup => 'حساب';

  @override
  String get signOutQuestion => 'خروج؟';

  @override
  String get signOutConfirmation => 'آیا مطمئنید که می‌خواهید خارج شوید؟';

  @override
  String get customVocabularyHeader => 'واژگان سفارشی';

  @override
  String get addWordsDescription => 'کلماتی را اضافه کنید که Omi باید آنها را در طول رونویسی تشخیص دهد.';

  @override
  String get enterWordsHint => 'کلمات را وارد کنید (جدا شده با ویرگول)';

  @override
  String get dailySummaryHeader => 'خلاصه روزانه';

  @override
  String get dailySummaryTitle => 'خلاصه روزانه';

  @override
  String get dailySummaryDescription => 'خلاصه شخصی‌شده‌ای از گفتگوهای روز خود را به عنوان اطلاع‌رسانی دریافت کنید.';

  @override
  String get deliveryTime => 'زمان تحویل';

  @override
  String get deliveryTimeDescription => 'زمان دریافت خلاصه روزانه خود';

  @override
  String get subscription => 'اشتراک';

  @override
  String get viewPlansAndUsage => 'مشاهده طرح‌ها و استفاده';

  @override
  String get viewPlansDescription => 'اشتراک و آمار استفاده خود را مدیریت کنید';

  @override
  String get addOrChangePaymentMethod => 'روش پرداخت خود را اضافه یا تغییر دهید';

  @override
  String get displayOptions => 'گزینه‌های نمایش';

  @override
  String get showMeetingsInMenuBar => 'نمایش جلسات در نوار منو';

  @override
  String get displayUpcomingMeetingsDescription => 'نمایش جلسات آتی در نوار منو';

  @override
  String get showEventsWithoutParticipants => 'نمایش رویدادهای بدون شرکت‌کنندگان';

  @override
  String get includePersonalEventsDescription => 'شامل رویدادهای شخصی بدون حضور';

  @override
  String get upcomingMeetings => 'جلسات آتی';

  @override
  String get checkingNext7Days => 'بررسی ۷ روز بعد';

  @override
  String get shortcuts => 'میانبرها';

  @override
  String get shortcutChangeInstruction => 'برای تغییر میانبر، روی آن کلیک کنید. برای انصراف، Escape را فشار دهید.';

  @override
  String get configureSTTProvider => 'پیکربندی ارائه‌دهنده STT';

  @override
  String get setConversationEndDescription => 'تنظیم زمان خودکار پایان گفتگوها';

  @override
  String get importDataDescription => 'داده‌ها را از منابع دیگر وارد کنید';

  @override
  String get exportConversationsDescription => 'گفتگوها را به JSON صادر کنید';

  @override
  String get exportingConversations => 'در حال صادر کردن گفتگوها...';

  @override
  String get clearNodesDescription => 'تمام گره‌ها و اتصالات را پاک کنید';

  @override
  String get deleteKnowledgeGraphQuestion => 'نمودار دانش را حذف کنید؟';

  @override
  String get deleteKnowledgeGraphWarning =>
      'این تمام داده‌های نمودار دانش مشتق‌شده را حذف می‌کند. خاطرات اصلی شما ایمن می‌مانند.';

  @override
  String get connectOmiWithAI => 'Omi را با دستیاران هوش مصنوعی متصل کنید';

  @override
  String get noAPIKeys => 'کلید API نیست. یکی ایجاد کنید تا شروع کنید.';

  @override
  String get autoCreateWhenDetected => 'ایجاد خودکار زمانی که نام تشخیص داده شود';

  @override
  String get trackPersonalGoals => 'پیگیری اهداف شخصی در صفحه اصلی';

  @override
  String get endpointURL => 'URL نقطه پایانی';

  @override
  String get links => 'پیوندها';

  @override
  String get discordMemberCount => '۸۰۰۰+ عضو بر روی Discord';

  @override
  String get userInformation => 'اطلاعات کاربر';

  @override
  String get capabilities => 'توانایی‌ها';

  @override
  String get previewScreenshots => 'نمایش پیش‌نمایش اسکریوت‌شات';

  @override
  String get holdOnPreparingForm => 'منتظر باشید، ما فرم را برای شما آماده می‌کنیم';

  @override
  String get bySubmittingYouAgreeToOmi => 'با تقدیم، شما موافقت می‌کنید با Omi ';

  @override
  String get termsAndPrivacyPolicy => 'شرایط و سیاست حریم‌خصوصی';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'کمک برای تشخیص مشکلات. حذف خودکار پس از ۳ روز.';

  @override
  String get manageYourApp => 'برنامه خود را مدیریت کنید';

  @override
  String get updatingYourApp => 'در حال به‌روزرسانی برنامه شما';

  @override
  String get fetchingYourAppDetails => 'در حال واکشی جزئیات برنامه شما';

  @override
  String get updateAppQuestion => 'برنامه را به‌روز کنید؟';

  @override
  String get updateAppConfirmation =>
      'آیا مطمئنید که می‌خواهید برنامه خود را به‌روز کنید؟ تغییرات زمانی‌که توسط تیم ما بررسی شوند منعکس می‌شوند.';

  @override
  String get updateApp => 'به‌روزرسانی برنامه';

  @override
  String get createAndSubmitNewApp => 'یک برنامه جدید ایجاد و تقدیم کنید';

  @override
  String appsCount(String count) {
    return 'برنامه‌ها ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'برنامه‌های خصوصی ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'برنامه‌های عمومی ($count)';
  }

  @override
  String get newVersionAvailable => 'نسخه جدید دردسترس است 🎉';

  @override
  String get no => 'نه';

  @override
  String get subscriptionCancelledSuccessfully => 'اشتراک با موفقیت لغو شد. تا پایان دوره صورت‌حساب جاری فعال می‌ماند.';

  @override
  String get failedToCancelSubscription => 'لغو اشتراک ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get invalidPaymentUrl => 'URL پرداخت نامعتبر';

  @override
  String get permissionsAndTriggers => 'مجوزها و فعال‌کننده‌ها';

  @override
  String get chatFeatures => 'ویژگی‌های گپ';

  @override
  String get uninstall => 'حذف نصب';

  @override
  String get installs => 'نصب‌ها';

  @override
  String get priceLabel => 'قیمت';

  @override
  String get updatedLabel => 'به‌روزشده';

  @override
  String get createdLabel => 'ایجادشده';

  @override
  String get featuredLabel => 'برجسته';

  @override
  String get cancelSubscriptionQuestion => 'اشتراک را لغو کنید؟';

  @override
  String get cancelSubscriptionConfirmation =>
      'آیا مطمئنید که می‌خواهید اشتراک خود را لغو کنید؟ تا پایان دوره صورت‌حساب جاری دسترسی خواهید داشت.';

  @override
  String get cancelSubscriptionButton => 'لغو اشتراک';

  @override
  String get cancelling => 'در حال لغو...';

  @override
  String get betaTesterMessage =>
      'شما یک آزمایشگر بتا برای این برنامه هستید. هنوز عمومی نیست. پس از تایید عمومی خواهد شد.';

  @override
  String get appUnderReviewMessage =>
      'برنامه شما در حال بررسی است و فقط برای شما قابل مشاهده است. پس از تایید عمومی خواهد شد.';

  @override
  String get appRejectedMessage =>
      'برنامه شما رد شده است. لطفاً جزئیات برنامه را به‌روز کنید و دوباره برای بررسی تقدیم کنید.';

  @override
  String get invalidIntegrationUrl => 'URL یکپارچگی نامعتبر';

  @override
  String get tapToComplete => 'برای تکمیل لمس کنید';

  @override
  String get invalidSetupInstructionsUrl => 'URL دستورالعمل راه‌اندازی نامعتبر';

  @override
  String get pushToTalk => 'فشار برای صحبت';

  @override
  String get summaryPrompt => 'فشار خلاصه';

  @override
  String get pleaseSelectARating => 'لطفاً یک رتبه‌بندی را انتخاب کنید';

  @override
  String get reviewAddedSuccessfully => 'نظر با موفقیت اضافه شد 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'نظر با موفقیت به‌روز شد 🚀';

  @override
  String get failedToSubmitReview => 'تقدیم نظر ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get addYourReview => 'نظر خود را اضافه کنید';

  @override
  String get editYourReview => 'نظر خود را ویرایش کنید';

  @override
  String get writeAReviewOptional => 'نظر بنویسید (اختیاری)';

  @override
  String get submitReview => 'تقدیم نظر';

  @override
  String get updateReview => 'به‌روزرسانی نظر';

  @override
  String get yourReview => 'نظر شما';

  @override
  String get anonymousUser => 'کاربر ناشناس';

  @override
  String get issueActivatingApp => 'مشکلی در فعال‌سازی این برنامه وجود داشت. لطفاً دوباره تلاش کنید.';

  @override
  String get dataAccessNoticeDescription =>
      'این برنامه به داده‌های شما دسترسی خواهد داشت. Omi AI برای نحوه استفاده، تغییر یا حذف داده‌های شما توسط این برنامه مسئول نیست';

  @override
  String get copyUrl => 'کپی URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'دوشنبه';

  @override
  String get weekdayTue => 'سه‌شنبه';

  @override
  String get weekdayWed => 'چهارشنبه';

  @override
  String get weekdayThu => 'پنج‌شنبه';

  @override
  String get weekdayFri => 'جمعه';

  @override
  String get weekdaySat => 'شنبه';

  @override
  String get weekdaySun => 'یکشنبه';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'یکپارچگی $serviceName به زودی';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'قبلاً به $platform صادرشده';
  }

  @override
  String get anotherPlatform => 'پلتفرم دیگر';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'لطفاً در تنظیمات > یکپارچگی‌های وظیفه با $serviceName احراز هویت کنید';
  }

  @override
  String addingToService(String serviceName) {
    return 'در حال اضافه کردن به $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'به $serviceName اضافه شد';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'اضافه کردن به $serviceName ناموفق بود';
  }

  @override
  String get permissionDeniedForAppleReminders => 'مجوز رد شده برای Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'ایجاد کلید API ارائه‌دهنده ناموفق بود: $error';
  }

  @override
  String get createAKey => 'یک کلید ایجاد کنید';

  @override
  String get apiKeyRevokedSuccessfully => 'کلید API با موفقیت لغو شد';

  @override
  String failedToRevokeApiKey(String error) {
    return 'لغو کلید API ناموفق بود: $error';
  }

  @override
  String get omiApiKeys => 'کلیدهای API Omi';

  @override
  String get apiKeysDescription =>
      'کلیدهای API برای احراز هویت زمانی که برنامه شما با سرور OMI ارتباط برقرار می‌کند استفاده می‌شوند. آنها به برنامه شما اجازه می‌دهند خاطرات ایجاد کنید و سایر سرویس‌های OMI را به طور ایمن دسترسی کنید.';

  @override
  String get aboutOmiApiKeys => 'درباره کلیدهای API Omi';

  @override
  String get yourNewKey => 'کلید جدید شما:';

  @override
  String get copyToClipboard => 'کپی به کلیپ‌بورد';

  @override
  String get pleaseCopyKeyNow => 'لطفاً آن را اکنون کپی کنید و در جایی امن بنویسید. ';

  @override
  String get willNotSeeAgain => 'شما دیگر نخواهید توانست آن را ببینید.';

  @override
  String get revokeKey => 'کلید را لغو کنید';

  @override
  String get revokeApiKeyQuestion => 'کلید API را لغو کنید؟';

  @override
  String get revokeApiKeyWarning =>
      'این عمل قابل بازگشت نیست. هر برنامه‌ای که از این کلید استفاده می‌کند دیگر نخواهد توانست API را دسترسی کند.';

  @override
  String get revoke => 'لغو';

  @override
  String get whatWouldYouLikeToCreate => 'آنچه که می‌خواهید ایجاد کنید چیست؟';

  @override
  String get createAnApp => 'یک برنامه ایجاد کنید';

  @override
  String get createAndShareYourApp => 'برنامه خود را ایجاد و اشتراک کنید';

  @override
  String get itemApp => 'برنامه';

  @override
  String keepItemPublic(String item) {
    return '$item را عمومی نگه دارید';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item را عمومی کنید؟';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item را خصوصی کنید؟';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'اگر $item را عمومی کنید، می‌تواند توسط همه استفاده شود';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'اگر اکنون $item را خصوصی کنید، برای همه کار کردن متوقف می‌شود و فقط برای شما قابل مشاهده خواهد بود';
  }

  @override
  String get manageApp => 'مدیریت برنامه';

  @override
  String deleteItemTitle(String item) {
    return 'حذف $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item را حذف کنید؟';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'آیا مطمئنید که می‌خواهید این $item را حذف کنید؟ این عمل قابل بازگشت نیست.';
  }

  @override
  String get revokeKeyQuestion => 'کلید را لغو کنید؟';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'آیا مطمئنید که می‌خواهید کلید \"$keyName\" را لغو کنید؟ این عمل قابل بازگشت نیست.';
  }

  @override
  String get createNewKey => 'کلید جدید ایجاد کنید';

  @override
  String get keyNameHint => 'به عنوان مثال، Claude Desktop';

  @override
  String get pleaseEnterAName => 'لطفاً نام وارد کنید.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'ایجاد کلید ناموفق بود: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'ایجاد کلید ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get keyCreated => 'کلید ایجادشده';

  @override
  String get keyCreatedMessage =>
      'کلید جدید شما ایجاد شده است. لطفاً آن را اکنون کپی کنید. شما دیگر نخواهید توانست آن را ببینید.';

  @override
  String get keyWord => 'کلید';

  @override
  String get externalAppAccess => 'دسترسی برنامه خارجی';

  @override
  String get externalAppAccessDescription =>
      'برنامه‌های نصب‌شده زیر دارای یکپارچگی‌های خارجی هستند و می‌توانند داده‌های شما، مانند گفتگوها و خاطرات را دسترسی کنند.';

  @override
  String get noExternalAppsHaveAccess => 'هیچ برنامه خارجی به داده‌های شما دسترسی ندارد.';

  @override
  String get maximumSecurityE2ee => 'حداکثر امنیت (E2EE)';

  @override
  String get e2eeDescription =>
      'رمزگذاری از سر به سر استاندارد طلایی برای حریم‌خصوصی است. هنگامی که فعال باشد، داده‌های شما قبل از ارسال به سرورهای ما در دستگاه شما رمزگذاری می‌شوند. این بدان معناست که هیچ کس، حتی Omi، نمی‌تواند محتوای شما را دسترسی کند.';

  @override
  String get importantTradeoffs => 'معامله‌های مهم:';

  @override
  String get e2eeTradeoff1 => '• برخی ویژگی‌ها مانند یکپارچگی‌های برنامه خارجی ممکن است غیرفعال باشند.';

  @override
  String get e2eeTradeoff2 => '• اگر گذرواژه خود را گم کنید، داده‌های شما قابل بازیابی نیستند.';

  @override
  String get featureComingSoon => 'این ویژگی به زودی می‌آید!';

  @override
  String get migrationInProgressMessage =>
      'مهاجرت در حال انجام است. تا زمانی که تکمیل نشود نمی‌توانید سطح حفاظت را تغییر دهید.';

  @override
  String get migrationFailed => 'مهاجرت ناموفق';

  @override
  String migratingFromTo(String source, String target) {
    return 'مهاجرت از $source به $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objects';
  }

  @override
  String get secureEncryption => 'رمزگذاری ایمن';

  @override
  String get secureEncryptionDescription =>
      'داده‌های شما با کلیدی منحصر به فرد برای شما در سرورهای ما، میزبان‌شده در Google Cloud، رمزگذاری می‌شوند. این بدان معناست که محتوای خام شما برای هیچ کس، از جمله کارکنان Omi یا Google، مستقیماً از پایگاه داده قابل دسترسی نیست.';

  @override
  String get endToEndEncryption => 'رمزگذاری از سر به سر';

  @override
  String get e2eeCardDescription =>
      'برای حداکثر امنیت فعال کنید جایی که فقط شما می‌توانید داده‌های خود را دسترسی کنید. برای اطلاعات بیشتر لمس کنید.';

  @override
  String get dataAlwaysEncrypted => 'صرف‌نظر از سطح، داده‌های شما همیشه در حالت سکون و در حین انتقال رمزگذاری شده است.';

  @override
  String get readOnlyScope => 'فقط خواندن';

  @override
  String get fullAccessScope => 'دسترسی کامل';

  @override
  String get readScope => 'خواندن';

  @override
  String get writeScope => 'نوشتن';

  @override
  String get apiKeyCreated => 'کلید API ایجادشده!';

  @override
  String get saveKeyWarning => 'این کلید را اکنون ذخیره کنید! شما دیگر نخواهید توانست آن را ببینید.';

  @override
  String get yourApiKey => 'کلید API شما';

  @override
  String get tapToCopy => 'برای کپی لمس کنید';

  @override
  String get copyKey => 'کپی کلید';

  @override
  String get createApiKey => 'ایجاد کلید API';

  @override
  String get accessDataProgrammatically => 'داده‌های خود را به‌طور برنامه‌ریزی دسترسی کنید';

  @override
  String get keyNameLabel => 'نام کلید';

  @override
  String get keyNamePlaceholder => 'به عنوان مثال، یکپارچگی برنامه من';

  @override
  String get permissionsLabel => 'مجوزها';

  @override
  String get permissionsInfoNote => 'R = خواندن، W = نوشتن. اگر چیزی انتخاب نشود، پیش‌فرض فقط‌خواندن است.';

  @override
  String get developerApi => 'API توسعه‌دهنده';

  @override
  String get createAKeyToGetStarted => 'یک کلید ایجاد کنید تا شروع کنید';

  @override
  String errorWithMessage(String error) {
    return 'خطا: $error';
  }

  @override
  String get omiTraining => 'آموزش Omi';

  @override
  String get trainingDataProgram => 'برنامه داده‌های آموزشی';

  @override
  String get getOmiUnlimitedFree =>
      'Omi Unlimited را برای رایگان دریافت کنید با مشارکت داده‌های خود برای آموزش مدل‌های هوش مصنوعی.';

  @override
  String get trainingDataBullets =>
      '• داده‌های شما به بهبود مدل‌های هوش مصنوعی کمک می‌کند\n• فقط داده‌های غیر‌حساس اشتراک‌گذاری می‌شوند\n• فرآیند کاملاً شفاف';

  @override
  String get learnMoreAtOmiTraining => 'اطلاعات بیشتر را در omi.me/training بیابید';

  @override
  String get agreeToContributeData => 'من درک می‌کنم و موافق‌ام داده‌های خود را برای آموزش هوش مصنوعی مشارکت کنم';

  @override
  String get submitRequest => 'تقدیم درخواست';

  @override
  String get thankYouRequestUnderReview => 'متشکرم! درخواست شما در حال بررسی است. پس از تایید به شما اطلاع خواهیم داد.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'طرح شما تا $date فعال می‌ماند. پس از آن، دسترسی به ویژگی‌های نامحدود خود را از دست خواهید داد. آیا مطمئنید؟';
  }

  @override
  String get confirmCancellation => 'تایید لغو';

  @override
  String get keepMyPlan => 'طرح خود را نگه دارید';

  @override
  String get subscriptionSetToCancel => 'اشتراک شما برای لغو در پایان دوره تنظیم شده است.';

  @override
  String get switchedToOnDevice => 'به رونویسی بر روی دستگاه تغییر کرد';

  @override
  String get couldNotSwitchToFreePlan => 'نتوانستیم شما را به طرح رایگان تغییر دهیم. لطفا دوباره تلاش کنید.';

  @override
  String get couldNotLoadPlans => 'نتوانستیم طرح‌های موجود را بارگذاری کنیم. لطفا دوباره تلاش کنید.';

  @override
  String get selectedPlanNotAvailable => 'طرح انتخاب شده در دسترس نیست. لطفا دوباره تلاش کنید.';

  @override
  String get upgradeToAnnualPlan => 'ارتقا به طرح سالانه';

  @override
  String get importantBillingInfo => 'اطلاعات مهم صورت‌حساب:';

  @override
  String get monthlyPlanContinues => 'طرح ماهانه فعلی شما تا پایان دوره صورت‌حساب ادامه خواهد داشت';

  @override
  String get paymentMethodCharged => 'روش پرداخت موجود شما به‌طور خودکار هنگام پایان طرح ماهانه شما شارژ می‌شود';

  @override
  String get annualSubscriptionStarts => 'اشتراک 12 ماهه سالانه شما به‌طور خودکار پس از شارژ شروع خواهد شد';

  @override
  String get thirteenMonthsCoverage => 'شما 13 ماه پوشش کل خواهید داشت (ماه فعلی + 12 ماه سالانه)';

  @override
  String get confirmUpgrade => 'تأیید ارتقا';

  @override
  String get confirmPlanChange => 'تأیید تغییر طرح';

  @override
  String get confirmAndProceed => 'تأیید و ادامه';

  @override
  String get upgradeScheduled => 'ارتقا برنامه‌ریزی شده است';

  @override
  String get changePlan => 'تغییر طرح';

  @override
  String get upgradeAlreadyScheduled => 'ارتقای شما به طرح سالانه قبلا برنامه‌ریزی شده است';

  @override
  String get youAreOnUnlimitedPlan => 'شما در طرح نامحدود هستید.';

  @override
  String get yourOmiUnleashed => 'Omi شما، آزاد شده. بی‌محدود بروید برای امکانات بی‌پایان.';

  @override
  String planEndedOn(String date) {
    return 'طرح شما در تاریخ $date پایان یافت.\\nهمین الآن مجددا مشترک شوید - برای یک دوره صورت‌حساب جدید بلافاصله شارژ خواهید شد.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'طرح شما برای لغو در تاریخ $date برنامه‌ریزی شده است.\\nهمین الآن مجددا مشترک شوید تا از مزایای خود محروم نشوید - تا $date هیچ هزینه‌ای نخواهید داشت.';
  }

  @override
  String get annualPlanStartsAutomatically => 'طرح سالانه شما به‌طور خودکار هنگام پایان طرح ماهانه شما شروع خواهد شد.';

  @override
  String planRenewsOn(String date) {
    return 'طرح شما در تاریخ $date تمدید خواهد شد.';
  }

  @override
  String get unlimitedConversations => 'مکالمات نامحدود';

  @override
  String get askOmiAnything => 'از Omi در مورد زندگی خود هر چیزی بپرسید';

  @override
  String get unlockOmiInfiniteMemory => 'حافظه نامحدود Omi را بازگشایید';

  @override
  String get youreOnAnnualPlan => 'شما در طرح سالانه هستید';

  @override
  String get alreadyBestValuePlan => 'شما قبلا بهترین طرح ارزش را دارید. نیاز به تغییری نیست.';

  @override
  String get unableToLoadPlans => 'بارگذاری طرح‌ها ممکن نشد';

  @override
  String get checkConnectionTryAgain => 'اتصال خود را بررسی کنید و دوباره تلاش کنید';

  @override
  String get useFreePlan => 'استفاده از طرح رایگان';

  @override
  String get continueText => 'ادامه';

  @override
  String get resubscribe => 'مجددا مشترک شوید';

  @override
  String get couldNotOpenPaymentSettings => 'نتوانستیم تنظیمات پرداخت را باز کنیم. لطفا دوباره تلاش کنید.';

  @override
  String get managePaymentMethod => 'مدیریت روش پرداخت';

  @override
  String get cancelSubscription => 'لغو اشتراک';

  @override
  String endsOnDate(String date) {
    return 'پایان می‌یابد در $date';
  }

  @override
  String get active => 'فعال';

  @override
  String get freePlan => 'طرح رایگان';

  @override
  String get configure => 'تنظیم';

  @override
  String get privacyInformation => 'اطلاعات حریم خصوصی';

  @override
  String get yourPrivacyMattersToUs => 'حریم خصوصی شما برای ما مهم است';

  @override
  String get privacyIntroText =>
      'در Omi، ما حریم خصوصی شما را بسیار جدی می‌گیریم. ما می‌خواهیم در مورد داده‌هایی که جمع‌آوری می‌کنیم و نحوه استفاده از آن برای بهبود محصول خود برای شما شفاف باشیم. در اینجا آنچه باید بدانید:';

  @override
  String get whatWeTrack => 'آنچه ما ردیابی می‌کنیم';

  @override
  String get anonymityAndPrivacy => 'ناشناسی و حریم خصوصی';

  @override
  String get optInAndOptOutOptions => 'گزینه‌های فعال‌سازی و غیرفعال‌سازی';

  @override
  String get ourCommitment => 'تعهد ما';

  @override
  String get commitmentText =>
      'ما متعهد هستیم داده‌هایی که جمع‌آوری می‌کنیم را تنها برای بهتر کردن Omi برای شما استفاده کنیم. حریم خصوصی و اعتماد شما برای ما بسیار اهمیت دارند.';

  @override
  String get thankYouText =>
      'از اینکه کاربر ارزشمندی از Omi هستید تشکر می‌کنیم. اگر سؤالات یا نگرانی‌ای دارید، لطفا با ما تماس بگیرید team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'تنظیمات نقطه اتصال Wi-Fi';

  @override
  String get enterHotspotCredentials => 'اطلاعات اعتباری نقطه اتصال تلفن خود را وارد کنید';

  @override
  String get wifiSyncUsesHotspot =>
      'هم‌راه‌سازی Wi-Fi از تلفن شما به‌عنوان نقطه اتصال استفاده می‌کند. نام نقطه اتصال و رمز عبور خود را در تنظیمات > Personal Hotspot بیابید.';

  @override
  String get hotspotNameSsid => 'نام نقطه اتصال (SSID)';

  @override
  String get exampleIphoneHotspot => 'مثال: iPhone Hotspot';

  @override
  String get password => 'رمز عبور';

  @override
  String get enterHotspotPassword => 'رمز عبور نقطه اتصال را وارد کنید';

  @override
  String get saveCredentials => 'ذخیره اطلاعات اعتباری';

  @override
  String get clearCredentials => 'پاک‌کردن اطلاعات اعتباری';

  @override
  String get pleaseEnterHotspotName => 'لطفا نام نقطه اتصال را وارد کنید';

  @override
  String get wifiCredentialsSaved => 'اطلاعات اعتباری Wi-Fi ذخیره شد';

  @override
  String get wifiCredentialsCleared => 'اطلاعات اعتباری Wi-Fi پاک‌شد';

  @override
  String summaryGeneratedForDate(String date) {
    return 'خلاصه برای $date تولید شد';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'نتوانستیم خلاصه را تولید کنیم. مطمئن شوید که برای آن روز مکالمات دارید.';

  @override
  String get summaryNotFound => 'خلاصه یافت نشد';

  @override
  String get yourDaysJourney => 'سفر روز شما';

  @override
  String get highlights => 'نکات برجسته';

  @override
  String get unresolvedQuestions => 'سؤالات حل‌نشده';

  @override
  String get decisions => 'تصمیمات';

  @override
  String get learnings => 'یادگیری‌ها';

  @override
  String get autoDeletesAfterThreeDays => 'به‌طور خودکار پس از 3 روز حذف می‌شود.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'نمودار دانش با موفقیت حذف شد';

  @override
  String get exportStartedMayTakeFewSeconds => 'صادرات شروع شد. این ممکن است چند ثانیه طول بکشد...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'این تمام داده‌های نمودار دانش مشتق‌شده (گره‌ها و اتصالات) را حذف خواهد کرد. یادآوری‌های اصلی شما ایمن خواهند ماند. نمودار در طول زمان یا بعد از درخواست بعدی بازسازی خواهد شد.';

  @override
  String get configureDailySummaryDigest => 'تنظیم خلاصه اقدامات روزانه خود';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'دسترسی به $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'فعال‌شده توسط $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription و $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'است $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'هیچ دسترسی داده خاصی تنظیم‌نشده است.';

  @override
  String get basicPlanDescription => '1,200 دقیقه حرفه‌ای + نامحدود روی‌دستگاه';

  @override
  String get minutes => 'دقیقه';

  @override
  String get omiHas => 'Omi دارای:';

  @override
  String get premiumMinutesUsed => 'دقایق حرفه‌ای استفاده‌شده.';

  @override
  String get setupOnDevice => 'تنظیم روی‌دستگاه';

  @override
  String get forUnlimitedFreeTranscription => 'برای رونویسی رایگان نامحدود.';

  @override
  String premiumMinsLeft(int count) {
    return '$count دقیقه حرفه‌ای باقی‌مانده.';
  }

  @override
  String get alwaysAvailable => 'همیشه در دسترس.';

  @override
  String get importHistory => 'تاریخ واردات';

  @override
  String get noImportsYet => 'هنوز واردات‌ای نشده است';

  @override
  String get selectZipFileToImport => 'فایل .zip را برای واردات انتخاب کنید!';

  @override
  String get otherDevicesComingSoon => 'دستگاه‌های دیگر به‌زودی می‌آیند';

  @override
  String get deleteAllLimitlessConversations => 'تمام مکالمات Limitless حذف شود؟';

  @override
  String get deleteAllLimitlessWarning =>
      'این تمام مکالمات واردشده از Limitless را به‌طور دائم حذف خواهد کرد. این عمل برگشت‌پذیر نیست.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'حذف $count مکالمه Limitless';
  }

  @override
  String get failedToDeleteConversations => 'نتوانستیم مکالمات را حذف کنیم';

  @override
  String get deleteImportedData => 'حذف داده‌های واردشده';

  @override
  String get statusPending => 'در انتظار';

  @override
  String get statusProcessing => 'در حال پردازش';

  @override
  String get statusCompleted => 'تکمیل‌شده';

  @override
  String get statusFailed => 'ناموفق';

  @override
  String nConversations(int count) {
    return '$count مکالمه';
  }

  @override
  String get pleaseEnterName => 'لطفا نام را وارد کنید';

  @override
  String get nameMustBeBetweenCharacters => 'نام باید بین 2 تا 40 کاراکتر باشد';

  @override
  String get deleteSampleQuestion => 'نمونه حذف شود؟';

  @override
  String deleteSampleConfirmation(String name) {
    return 'آیا مطمئن هستید که می‌خواهید نمونه $name را حذف کنید؟';
  }

  @override
  String get confirmDeletion => 'تأیید حذف';

  @override
  String deletePersonConfirmation(String name) {
    return 'آیا مطمئن هستید که می‌خواهید $name را حذف کنید؟ این تمام نمونه‌های صوتی مرتبط را نیز حذف خواهد کرد.';
  }

  @override
  String get howItWorksTitle => 'چگونه کار می‌کند؟';

  @override
  String get howPeopleWorks =>
      'بعد از اینکه یک فرد ایجاد شود، می‌توانید به رونویس مکالمه بروید و بخش‌های مرتبط با آن‌ها را تعیین کنید، به این ترتیب Omi می‌تواند صوت آن‌ها را نیز تشخیص دهد!';

  @override
  String get tapToDelete => 'برای حذف ضربه بزنید';

  @override
  String get newTag => 'نو';

  @override
  String get needHelpChatWithUs => 'به کمک نیاز دارید؟ با ما چت کنید';

  @override
  String get localStorageEnabled => 'ذخیره‌سازی محلی فعال شد';

  @override
  String get localStorageDisabled => 'ذخیره‌سازی محلی غیرفعال شد';

  @override
  String failedToUpdateSettings(String error) {
    return 'نتوانستیم تنظیمات را به‌روزرسانی کنیم: $error';
  }

  @override
  String get privacyNotice => 'اطلاعیه حریم خصوصی';

  @override
  String get recordingsMayCaptureOthers =>
      'ضبط‌ها ممکن است صدای دیگران را ضبط کنند. قبل از فعال‌سازی مطمئن شوید که رضایت تمام شرکت‌کنندگان را دارید.';

  @override
  String get enable => 'فعال‌سازی';

  @override
  String get storeAudioOnPhone => 'ذخیره صوت در تلفن';

  @override
  String get on => 'روشن';

  @override
  String get storeAudioDescription =>
      'تمام ضبط‌های صوتی را به‌طور محلی در تلفن خود ذخیره کنید. هنگام غیرفعال‌سازی، تنها آپلود‌های ناموفق ذخیره می‌شود تا فضای ذخیره‌سازی صرفه‌جویی شود.';

  @override
  String get enableLocalStorage => 'فعال‌سازی ذخیره‌سازی محلی';

  @override
  String get cloudStorageEnabled => 'ذخیره‌سازی ابری فعال شد';

  @override
  String get cloudStorageDisabled => 'ذخیره‌سازی ابری غیرفعال شد';

  @override
  String get enableCloudStorage => 'فعال‌سازی ذخیره‌سازی ابری';

  @override
  String get storeAudioOnCloud => 'ذخیره صوت در ابر';

  @override
  String get cloudStorageDialogMessage => 'ضبط‌های بلادرنگ شما در ذخیره‌سازی ابری خصوصی ذخیره خواهند شد.';

  @override
  String get storeAudioCloudDescription =>
      'ضبط‌های بلادرنگ خود را در ذخیره‌سازی ابری خصوصی ذخیره کنید. صوت به‌طور بلادرنگ ضبط و به‌طور ایمن ذخیره می‌شود.';

  @override
  String get downloadingFirmware => 'بارگیری نرم‌افزار';

  @override
  String get installingFirmware => 'نصب نرم‌افزار';

  @override
  String get firmwareUpdateWarning =>
      'برنامه را بسته نکنید یا دستگاه را خاموش نکنید. این می‌تواند دستگاه شما را خراب کند.';

  @override
  String get firmwareUpdated => 'نرم‌افزار به‌روزرسانی شد';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'لطفا $deviceName خود را دوباره راه‌اندازی کنید تا به‌روزرسانی تکمیل شود.';
  }

  @override
  String get yourDeviceIsUpToDate => 'دستگاه شما به‌روزترین است';

  @override
  String get currentVersion => 'نسخه فعلی';

  @override
  String get latestVersion => 'آخرین نسخه';

  @override
  String get whatsNew => 'چه جدیدی است';

  @override
  String get installUpdate => 'نصب به‌روزرسانی';

  @override
  String get updateNow => 'اکنون به‌روزرسانی کنید';

  @override
  String get updateGuide => 'راهنمای به‌روزرسانی';

  @override
  String get checkingForUpdates => 'بررسی به‌روزرسانی‌ها';

  @override
  String get checkingFirmwareVersion => 'بررسی نسخه نرم‌افزار...';

  @override
  String get firmwareUpdate => 'به‌روزرسانی نرم‌افزار';

  @override
  String get payments => 'پرداخت‌ها';

  @override
  String get connectPaymentMethodInfo =>
      'یک روش پرداخت در زیر متصل کنید تا برای برنامه‌های خود پرداخت‌های خود را دریافت کنید.';

  @override
  String get selectedPaymentMethod => 'روش پرداخت انتخاب‌شده';

  @override
  String get availablePaymentMethods => 'روش‌های پرداخت موجود';

  @override
  String get activeStatus => 'فعال';

  @override
  String get connectedStatus => 'متصل';

  @override
  String get notConnectedStatus => 'متصل‌نشده';

  @override
  String get setActive => 'تعیین فعال';

  @override
  String get getPaidThroughStripe => 'برای فروش برنامه خود از طریق Stripe پرداخت دریافت کنید';

  @override
  String get monthlyPayouts => 'پرداخت‌های ماهانه';

  @override
  String get monthlyPayoutsDescription => 'وقتی به 10 دلار درآمد برسید، هر ماه پرداخت‌های مستقیم را دریافت کنید';

  @override
  String get secureAndReliable => 'ایمن و قابل‌اعتماد';

  @override
  String get stripeSecureDescription => 'Stripe انتقال ایمن و به‌موقع درآمد برنامه شما را تضمین می‌کند';

  @override
  String get selectYourCountry => 'کشور خود را انتخاب کنید';

  @override
  String get countrySelectionPermanent => 'انتخاب کشور شما دائمی است و بعدا نمی‌تواند تغییر کند.';

  @override
  String get byClickingConnectNow => 'با کلیک بر روی \"اتصال اکنون\" موافقت می‌کنید';

  @override
  String get stripeConnectedAccountAgreement => 'موافقت‌نامه حساب متصل Stripe';

  @override
  String get errorConnectingToStripe => 'خطا در اتصال به Stripe! لطفا بعدا دوباره تلاش کنید.';

  @override
  String get connectingYourStripeAccount => 'اتصال حساب Stripe شما';

  @override
  String get stripeOnboardingInstructions =>
      'لطفا فرایند راه‌اندازی Stripe را در مرورگر خود تکمیل کنید. این صفحه به‌طور خودکار به‌روزرسانی خواهد شد.';

  @override
  String get failedTryAgain => 'ناموفق؟ دوباره تلاش کنید';

  @override
  String get illDoItLater => 'بعدا انجام خواهم داد';

  @override
  String get successfullyConnected => 'با موفقیت متصل!';

  @override
  String get stripeReadyForPayments =>
      'حساب Stripe شما اکنون برای دریافت پرداخت آماده است. می‌توانید بلافاصله از فروش برنامه شود درآمد کسب کنید.';

  @override
  String get updateStripeDetails => 'به‌روزرسانی جزئیات Stripe';

  @override
  String get errorUpdatingStripeDetails => 'خطا در به‌روزرسانی جزئیات Stripe! لطفا بعدا دوباره تلاش کنید.';

  @override
  String get updatePayPal => 'به‌روزرسانی PayPal';

  @override
  String get setUpPayPal => 'تنظیم PayPal';

  @override
  String get updatePayPalAccountDetails => 'به‌روزرسانی جزئیات حساب PayPal خود';

  @override
  String get connectPayPalToReceivePayments =>
      'حساب PayPal خود را متصل کنید تا برای برنامه‌های خود پرداخت‌های خود را دریافت کنید';

  @override
  String get paypalEmail => 'رایانامه PayPal';

  @override
  String get paypalMeLink => 'پیوند PayPal.me';

  @override
  String get stripeRecommendation =>
      'اگر Stripe در کشور شما موجود است، ما بسیار توصیه می‌کنیم که آن را برای پرداخت‌های سریع‌تر و آسان‌تر استفاده کنید.';

  @override
  String get updatePayPalDetails => 'به‌روزرسانی جزئیات PayPal';

  @override
  String get savePayPalDetails => 'ذخیره جزئیات PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'لطفا رایانامه PayPal خود را وارد کنید';

  @override
  String get pleaseEnterPayPalMeLink => 'لطفا پیوند PayPal.me خود را وارد کنید';

  @override
  String get doNotIncludeHttpInLink => 'http یا https یا www را در پیوند شامل نکنید';

  @override
  String get pleaseEnterValidPayPalMeLink => 'لطفا پیوند PayPal.me معتبر را وارد کنید';

  @override
  String get pleaseEnterValidEmail => 'لطفا رایانامه معتبری را وارد کنید';

  @override
  String get syncingYourRecordings => 'هم‌راه‌سازی ضبط‌های شما';

  @override
  String get syncYourRecordings => 'هم‌راه‌سازی ضبط‌های خود';

  @override
  String get syncNow => 'اکنون هم‌راه‌سازی کنید';

  @override
  String get error => 'خطا';

  @override
  String get speechSamples => 'نمونه‌های صوتی';

  @override
  String additionalSampleIndex(String index) {
    return 'نمونه اضافی $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'مدت: $seconds ثانیه';
  }

  @override
  String get additionalSpeechSampleRemoved => 'نمونه صوتی اضافی حذف‌شد';

  @override
  String get consentDataMessage =>
      'با ادامه دادن، مکالمات، ضبط‌ها و اطلاعات شخصی شما به طور ایمن در سرورهای ما ذخیره می‌شود. ضبط‌های صوتی و رونوشت‌های شما توسط سرویس‌های هوش مصنوعی شخص ثالث (از جمله Deepgram برای رونویسی و OpenAI برای تحلیل) پردازش می‌شوند تا بینش‌های مبتنی بر هوش مصنوعی را به شما ارائه دهند و تمام ویژگی‌های برنامه را فعال کنند.';

  @override
  String get tasksEmptyStateMessage =>
      'وظایف از مکالمات شما اینجا ظاهر خواهند شد.\\n+ را ضربه بزنید تا یکی به‌صورت دستی ایجاد کنید.';

  @override
  String get clearChatAction => 'پاک‌کردن چت';

  @override
  String get enableApps => 'فعال‌سازی برنامه‌ها';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'نمایش بیشتر ↓';

  @override
  String get showLess => 'نمایش کمتر ↑';

  @override
  String get loadingYourRecording => 'بارگیری ضبط شما...';

  @override
  String get photoDiscardedMessage => 'این عکس به‌دلیل اینکه معنی‌دار نبود کنار گذاشته شد.';

  @override
  String get analyzing => 'تجزیه و تحلیل...';

  @override
  String get searchCountries => 'جستجوی کشورها';

  @override
  String get checkingAppleWatch => 'بررسی Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'نصب Omi روی\\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'برای استفاده از Apple Watch با Omi، شما باید ابتدا برنامه Omi را روی ساعت نصب کنید.';

  @override
  String get openOmiOnAppleWatch => 'باز کردن Omi روی\\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'برنامه Omi روی Apple Watch نصب‌شده است. آن را باز کنید و Start را ضربه بزنید تا شروع کنید.';

  @override
  String get openWatchApp => 'باز کردن برنامه ساعت';

  @override
  String get iveInstalledAndOpenedTheApp => 'نصب و باز کردم برنامه را';

  @override
  String get unableToOpenWatchApp =>
      'نتوانستیم برنامه Apple Watch را باز کنیم. لطفا برنامه Watch را روی Apple Watch خود به‌صورت دستی باز کنید و Omi را از بخش \"برنامه‌های موجود\" نصب کنید.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch با موفقیت متصل شد!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch هنوز در دسترس نیست. لطفا مطمئن شوید که برنامه Omi روی ساعت شما باز است.';

  @override
  String errorCheckingConnection(String error) {
    return 'خطا در بررسی اتصال: $error';
  }

  @override
  String get muted => 'بی‌صدا شده';

  @override
  String get processNow => 'فوری پردازش کنید';

  @override
  String get finishedConversation => 'مکالمه تکمیل شد؟';

  @override
  String get stopRecordingConfirmation =>
      'آیا مطمئن هستید که می‌خواهید ضبط را متوقف کنید و مکالمه را اکنون خلاصه کنید؟';

  @override
  String get conversationEndsManually => 'مکالمه تنها به‌صورت دستی پایان خواهد یافت.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'مکالمه پس از $minutes دقیقه$suffix بدون صحبت خلاصه می‌شود.';
  }

  @override
  String get dontAskAgain => 'دوباره از من نپرس';

  @override
  String get waitingForTranscriptOrPhotos => 'انتظار برای رونویس یا عکس‌ها...';

  @override
  String get noSummaryYet => 'هنوز خلاصه‌ای نیست';

  @override
  String hints(String text) {
    return 'راهنمایی‌ها: $text';
  }

  @override
  String get testConversationPrompt => 'آزمایش پیشنهاد مکالمه';

  @override
  String get prompt => 'پیشنهاد';

  @override
  String get result => 'نتیجه:';

  @override
  String get compareTranscripts => 'مقایسه رونویس‌ها';

  @override
  String get notHelpful => 'کمکی نکرد';

  @override
  String get exportTasksWithOneTap => 'صادرات وظایف با یک ضربه!';

  @override
  String get inProgress => 'در حال انجام';

  @override
  String get photos => 'عکس‌ها';

  @override
  String get rawData => 'داده‌های خام';

  @override
  String get content => 'محتوا';

  @override
  String get noContentToDisplay => 'محتوایی برای نمایش نیست';

  @override
  String get noSummary => 'بدون خلاصه';

  @override
  String get updateOmiFirmware => 'به‌روزرسانی نرم‌افزار Omi';

  @override
  String get anErrorOccurredTryAgain => 'خطایی رخ داده است. لطفا دوباره تلاش کنید.';

  @override
  String get welcomeBackSimple => 'خوش بازگشتید';

  @override
  String get addVocabularyDescription => 'کلماتی اضافه کنید که Omi باید در طول رونویسی آن‌ها را تشخیص دهد.';

  @override
  String get enterWordsCommaSeparated => 'کلمات را وارد کنید (با کاما جداشده)';

  @override
  String get whenToReceiveDailySummary => 'چه وقت خلاصه روزانه خود را دریافت کنید';

  @override
  String get checkingNextSevenDays => 'بررسی 7 روز بعد';

  @override
  String failedToDeleteError(String error) {
    return 'نتوانستیم حذف کنیم: $error';
  }

  @override
  String get developerApiKeys => 'کلیدهای API توسعه‌دهنده';

  @override
  String get noApiKeysCreateOne => 'بدون کلیدهای API. یکی ایجاد کنید تا شروع کنید.';

  @override
  String get commandRequired => '⌘ الزامی';

  @override
  String get spaceKey => 'فضا';

  @override
  String loadMoreRemaining(String count) {
    return 'بارگذاری بیشتر ($count باقی‌مانده)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'کاربر $percentile% برتر';
  }

  @override
  String get wrappedMinutes => 'دقیقه';

  @override
  String get wrappedConversations => 'مکالمات';

  @override
  String get wrappedDaysActive => 'روزهای فعال';

  @override
  String get wrappedYouTalkedAbout => 'شما درمورد صحبت کردید';

  @override
  String get wrappedActionItems => 'موارد عملیاتی';

  @override
  String get wrappedTasksCreated => 'وظایف ایجادشده';

  @override
  String get wrappedCompleted => 'تکمیل‌شده';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% نرخ تکمیل';
  }

  @override
  String get wrappedYourTopDays => 'بهترین روزهای شما';

  @override
  String get wrappedBestMoments => 'بهترین لحظات';

  @override
  String get wrappedMyBuddies => 'دوستان من';

  @override
  String get wrappedCouldntStopTalkingAbout => 'نتوانستند صحبت درمورد آن را متوقف کنند';

  @override
  String get wrappedShow => 'سریال';

  @override
  String get wrappedMovie => 'فیلم';

  @override
  String get wrappedBook => 'کتاب';

  @override
  String get wrappedCelebrity => 'سلبریتی';

  @override
  String get wrappedFood => 'غذا';

  @override
  String get wrappedMovieRecs => 'سفارش‌های فیلم برای دوستان';

  @override
  String get wrappedBiggest => 'بزرگ‌ترین';

  @override
  String get wrappedStruggle => 'مبارزه';

  @override
  String get wrappedButYouPushedThrough => 'اما شما ادامه دادید 💪';

  @override
  String get wrappedWin => 'پیروزی';

  @override
  String get wrappedYouDidIt => 'شما موفق شدید! 🎉';

  @override
  String get wrappedTopPhrases => '5 عبارت برتر';

  @override
  String get wrappedMins => 'دقیقه';

  @override
  String get wrappedConvos => 'مکالمات';

  @override
  String get wrappedDays => 'روزها';

  @override
  String get wrappedMyBuddiesLabel => 'دوستان من';

  @override
  String get wrappedObsessionsLabel => 'وسواس‌ها';

  @override
  String get wrappedStruggleLabel => 'مبارزه';

  @override
  String get wrappedWinLabel => 'پیروزی';

  @override
  String get wrappedTopPhrasesLabel => 'عبارات برتر';

  @override
  String get wrappedLetsHitRewind => 'بیایید بازگردید به';

  @override
  String get wrappedGenerateMyWrapped => 'تولید Wrapped من';

  @override
  String get wrappedProcessingDefault => 'پردازش...';

  @override
  String get wrappedCreatingYourStory => 'ایجاد\\nداستان 2025 شما...';

  @override
  String get wrappedSomethingWentWrong => 'چیز\\nاشتباهی رخ داد';

  @override
  String get wrappedAnErrorOccurred => 'خطایی رخ داده است';

  @override
  String get wrappedTryAgain => 'دوباره تلاش کنید';

  @override
  String get wrappedNoDataAvailable => 'داده‌ای در دسترس نیست';

  @override
  String get wrappedOmiLifeRecap => 'خلاصه زندگی Omi';

  @override
  String get wrappedSwipeUpToBegin => 'برای شروع به‌بالا بکشید';

  @override
  String get wrappedShareText => '2025 من، به‌خاطر سپردهً توسط Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'نتوانستیم اشتراک بگذاریم. لطفا دوباره تلاش کنید.';

  @override
  String get wrappedFailedToStartGeneration => 'نتوانستیم تولید را شروع کنیم. لطفا دوباره تلاش کنید.';

  @override
  String get wrappedStarting => 'شروع...';

  @override
  String get wrappedShare => 'اشتراک';

  @override
  String get wrappedShareYourWrapped => 'اشتراک Wrapped شما';

  @override
  String get wrappedMy2025 => '2025 من';

  @override
  String get wrappedRememberedByOmi => 'به‌خاطر سپردهً توسط Omi';

  @override
  String get wrappedMostFunDay => 'بیشترین سرگرمی';

  @override
  String get wrappedMostProductiveDay => 'بیشترین بهره‌وری';

  @override
  String get wrappedMostIntenseDay => 'بیشترین شدت';

  @override
  String get wrappedFunniestMoment => 'طنز‌آمیز‌ترین';

  @override
  String get wrappedMostCringeMoment => 'بیشترین احساس عجیب';

  @override
  String get wrappedMinutesLabel => 'دقیقه';

  @override
  String get wrappedConversationsLabel => 'مکالمات';

  @override
  String get wrappedDaysActiveLabel => 'روزهای فعال';

  @override
  String get wrappedTasksGenerated => 'وظایف تولیدشده';

  @override
  String get wrappedTasksCompleted => 'وظایف تکمیل‌شده';

  @override
  String get wrappedTopFivePhrases => '5 عبارت برتر';

  @override
  String get wrappedAGreatDay => 'روز بسیار خوبی';

  @override
  String get wrappedGettingItDone => 'انجام دادن کار';

  @override
  String get wrappedAChallenge => 'یک چالش';

  @override
  String get wrappedAHilariousMoment => 'یک لحظه خنده‌دار';

  @override
  String get wrappedThatAwkwardMoment => 'آن لحظه ناخوشایند';

  @override
  String get wrappedYouHadFunnyMoments => 'شما برخی لحظات خنده‌دار داشتید این سال!';

  @override
  String get wrappedWeveAllBeenThere => 'ما همه آنجا بوده‌ایم!';

  @override
  String get wrappedFriend => 'دوست';

  @override
  String get wrappedYourBuddy => 'دوست شما!';

  @override
  String get wrappedNotMentioned => 'ذکر نشده';

  @override
  String get wrappedTheHardPart => 'قسمت سخت';

  @override
  String get wrappedPersonalGrowth => 'رشد شخصی';

  @override
  String get wrappedFunDay => 'سرگرمی';

  @override
  String get wrappedProductiveDay => 'بهره‌وری';

  @override
  String get wrappedIntenseDay => 'شدت';

  @override
  String get wrappedFunnyMomentTitle => 'لحظه خنده‌دار';

  @override
  String get wrappedCringeMomentTitle => 'لحظه عجیب';

  @override
  String get wrappedYouTalkedAboutBadge => 'شما درمورد صحبت کردید';

  @override
  String get wrappedCompletedLabel => 'تکمیل‌شده';

  @override
  String get wrappedMyBuddiesCard => 'دوستان من';

  @override
  String get wrappedBuddiesLabel => 'دوستان';

  @override
  String get wrappedObsessionsLabelUpper => 'وسواس‌ها';

  @override
  String get wrappedStruggleLabelUpper => 'مبارزه';

  @override
  String get wrappedWinLabelUpper => 'پیروزی';

  @override
  String get wrappedTopPhrasesLabelUpper => 'عبارات برتر';

  @override
  String get wrappedYourHeader => 'شما';

  @override
  String get wrappedTopDaysHeader => 'بهترین روزها';

  @override
  String get wrappedYourTopDaysBadge => 'بهترین روزهای شما';

  @override
  String get wrappedBestHeader => 'بهترین';

  @override
  String get wrappedMomentsHeader => 'لحظات';

  @override
  String get wrappedBestMomentsBadge => 'بهترین لحظات';

  @override
  String get wrappedBiggestHeader => 'بزرگ‌ترین';

  @override
  String get wrappedStruggleHeader => 'مبارزه';

  @override
  String get wrappedWinHeader => 'پیروزی';

  @override
  String get wrappedButYouPushedThroughEmoji => 'اما شما ادامه دادید 💪';

  @override
  String get wrappedYouDidItEmoji => 'شما موفق شدید! 🎉';

  @override
  String get wrappedHours => 'ساعات';

  @override
  String get wrappedActions => 'اقدامات';

  @override
  String get multipleSpeakersDetected => 'چند گوینده تشخیص‌داده‌شد';

  @override
  String get multipleSpeakersDescription =>
      'به نظر می‌رسد که در ضبط چند گوینده وجود دارند. لطفا مطمئن شوید که در مکانی ساکت هستید و دوباره تلاش کنید.';

  @override
  String get invalidRecordingDetected => 'ضبط نامعتبر تشخیص‌داده‌شد';

  @override
  String get notEnoughSpeechDescription => 'صحبت کافی تشخیص‌داده نشده است. لطفا بیشتر صحبت کنید و دوباره تلاش کنید.';

  @override
  String get speechDurationDescription => 'لطفاً مطمئن شوید که حداقل 5 ثانیه و حداکثر 90 ثانیه صحبت می کنید.';

  @override
  String get connectionLostDescription => 'اتصال قطع شد. لطفاً اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید.';

  @override
  String get howToTakeGoodSample => 'چگونه نمونه خوبی بگیریم؟';

  @override
  String get goodSampleInstructions =>
      '1. مطمئن شوید که در مکانی آرام قرار دارید.\n2. واضح و طبیعی صحبت کنید.\n3. مطمئن شوید که دستگاه شما در موضع طبیعی خود قرار دارد، روی گردن شما.\n\nپس از ایجاد، می توانید آن را بهبود بخشید یا دوباره انجام دهید.';

  @override
  String get noDeviceConnectedUseMic => 'هیچ دستگاهی متصل نشده است. از میکروفن تلفن استفاده خواهد شد.';

  @override
  String get doItAgain => 'دوباره انجام دهید';

  @override
  String get listenToSpeechProfile => 'گوش دادن به نمایه صدای من ➡️';

  @override
  String get recognizingOthers => 'شناخت افراد دیگر 👀';

  @override
  String get keepGoingGreat => 'ادامه دهید، عملکرد خوبی دارید';

  @override
  String get somethingWentWrongTryAgain => 'مشکلی پیش آمد! لطفاً بعداً دوباره تلاش کنید.';

  @override
  String get uploadingVoiceProfile => 'در حال آپلود نمایه صدای شما...';

  @override
  String get memorizingYourVoice => 'در حال حفظ صدای شما...';

  @override
  String get personalizingExperience => 'در حال شخصی سازی تجربه شما...';

  @override
  String get keepSpeakingUntil100 => 'تا زمانی که به 100٪ برسید ادامه دهید.';

  @override
  String get greatJobAlmostThere => 'کار خوبی انجام دادید، تقریباً به انجام رسیده است';

  @override
  String get soCloseJustLittleMore => 'خیلی نزدیک، فقط یکم دیگر';

  @override
  String get notificationFrequency => 'فرکانس اعلان';

  @override
  String get controlNotificationFrequency => 'کنترل کنید که Omi چند بار اعلانات پیشفعال ارسال می کند.';

  @override
  String get yourScore => 'امتیاز شما';

  @override
  String get dailyScoreBreakdown => 'تفکیک امتیاز روزانه';

  @override
  String get todaysScore => 'امتیاز امروز';

  @override
  String get tasksCompleted => 'تکالیف انجام شده';

  @override
  String get completionRate => 'نسبت تکمیل';

  @override
  String get howItWorks => 'چگونه کار می کند';

  @override
  String get dailyScoreExplanation =>
      'امتیاز روزانه شما بر اساس تکمیل تکالیف است. تکالیف خود را تکمیل کنید تا امتیاز خود را بهبود بخشید!';

  @override
  String get notificationFrequencyDescription => 'کنترل کنید که Omi چند بار اعلانات پیشفعال و یادآوری ارسال می کند.';

  @override
  String get sliderOff => 'خاموش';

  @override
  String get sliderMax => 'حداکثر';

  @override
  String summaryGeneratedFor(String date) {
    return 'خلاصه برای $date تولید شد';
  }

  @override
  String get failedToGenerateSummary => 'خلاصه را نتوانستم تولید کنم. مطمئن شوید که برای آن روز مکالمات دارید.';

  @override
  String get recap => 'خلاصه';

  @override
  String deleteQuoted(String name) {
    return 'حذف \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'انتقال $count مکالمه به:';
  }

  @override
  String get noFolder => 'بدون پوشه';

  @override
  String get removeFromAllFolders => 'حذف از تمام پوشه ها';

  @override
  String get buildAndShareYourCustomApp => 'برنامه سفارشی خود را بسازید و به اشتراک بگذارید';

  @override
  String get searchAppsPlaceholder => 'جستجو 1500+ برنامه';

  @override
  String get filters => 'فیلترها';

  @override
  String get frequencyOff => 'خاموش';

  @override
  String get frequencyMinimal => 'حداقل';

  @override
  String get frequencyLow => 'کم';

  @override
  String get frequencyBalanced => 'متعادل';

  @override
  String get frequencyHigh => 'زیاد';

  @override
  String get frequencyMaximum => 'حداکثر';

  @override
  String get frequencyDescOff => 'بدون اعلانات پیشفعال';

  @override
  String get frequencyDescMinimal => 'فقط یادآوری های حیاتی';

  @override
  String get frequencyDescLow => 'فقط به روزرسانی های مهم';

  @override
  String get frequencyDescBalanced => 'تشویق های کمکی منظم';

  @override
  String get frequencyDescHigh => 'بررسی های مکرر';

  @override
  String get frequencyDescMaximum => 'همیشه درگیر بمانید';

  @override
  String get clearChatQuestion => 'پاک کردن چت؟';

  @override
  String get syncingMessages => 'هماهنگ سازی پیام ها با سرور...';

  @override
  String get chatAppsTitle => 'برنامه های چت';

  @override
  String get selectApp => 'انتخاب برنامه';

  @override
  String get noChatAppsEnabled =>
      'هیچ برنامه چت فعال نشده است.\nبرای افزودن برنامه ها \"برنامه های فعال کن\" را ضربه بزنید.';

  @override
  String get disable => 'غیرفعال کن';

  @override
  String get photoLibrary => 'کتابخانه عکس';

  @override
  String get chooseFile => 'انتخاب فایل';

  @override
  String get connectAiAssistantsToYourData => 'کمک دستیاران هوش مصنوعی را به داده های خود متصل کنید';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'اهداف شخصی خود را در صفحه اصلی ردیابی کنید';

  @override
  String get deleteRecording => 'حذف ضبط';

  @override
  String get thisCannotBeUndone => 'این کار قابل بازگشت نیست.';

  @override
  String get sdCard => 'کارت SD';

  @override
  String get fromSd => 'از SD';

  @override
  String get limitless => 'بی محدود';

  @override
  String get fastTransfer => 'انتقال سریع';

  @override
  String get syncingStatus => 'هماهنگ سازی';

  @override
  String get failedStatus => 'ناموفق';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'روش انتقال';

  @override
  String get fast => 'سریع';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'تلفن';

  @override
  String get cancelSync => 'لغو هماهنگ سازی';

  @override
  String get cancelSyncMessage => 'داده های دانلود شده ذخیره خواهند شد. می توانید بعداً ادامه دهید.';

  @override
  String get syncCancelled => 'هماهنگ سازی لغو شد';

  @override
  String get deleteProcessedFiles => 'حذف فایل های پردازش شده';

  @override
  String get processedFilesDeleted => 'فایل های پردازش شده حذف شدند';

  @override
  String get wifiEnableFailed => 'فعال کردن WiFi در دستگاه ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get deviceNoFastTransfer =>
      'دستگاه شما از Fast Transfer پشتیبانی نمی کند. به جای آن از Bluetooth استفاده کنید.';

  @override
  String get enableHotspotMessage => 'لطفاً hotspot تلفن خود را فعال کنید و دوباره تلاش کنید.';

  @override
  String get transferStartFailed => 'شروع انتقال ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get deviceNotResponding => 'دستگاه پاسخ نداد. لطفاً دوباره تلاش کنید.';

  @override
  String get invalidWifiCredentials => 'اعتبارات WiFi نامعتبر است. تنظیمات hotspot خود را بررسی کنید.';

  @override
  String get wifiConnectionFailed => 'اتصال WiFi ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get sdCardProcessing => 'پردازش کارت SD';

  @override
  String sdCardProcessingMessage(int count) {
    return 'پردازش $count ضبط. فایل ها پس از آن از کارت SD حذف خواهند شد.';
  }

  @override
  String get process => 'پردازش';

  @override
  String get wifiSyncFailed => 'هماهنگ سازی WiFi ناموفق بود';

  @override
  String get processingFailed => 'پردازش ناموفق بود';

  @override
  String get downloadingFromSdCard => 'دانلود از کارت SD';

  @override
  String processingProgress(int current, int total) {
    return 'پردازش $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count مکالمه ایجاد شد';
  }

  @override
  String get internetRequired => 'اینترنت مورد نیاز است';

  @override
  String get processAudio => 'پردازش صوت';

  @override
  String get start => 'شروع';

  @override
  String get noRecordings => 'بدون ضبط';

  @override
  String get audioFromOmiWillAppearHere => 'صوت از دستگاه Omi شما در اینجا ظاهر خواهد شد';

  @override
  String get deleteProcessed => 'حذف پردازش شده';

  @override
  String get tryDifferentFilter => 'فیلتر متفاوتی را امتحان کنید';

  @override
  String get recordings => 'ضبط ها';

  @override
  String get enableRemindersAccess =>
      'لطفاً دسترسی Reminders را در تنظیمات فعال کنید تا از Apple Reminders استفاده کنید';

  @override
  String todayAtTime(String time) {
    return 'امروز در $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'دیروز در $time';
  }

  @override
  String get lessThanAMinute => 'کمتر از یک دقیقه';

  @override
  String estimatedMinutes(int count) {
    return '~$count دقیقه';
  }

  @override
  String estimatedHours(int count) {
    return '~$count ساعت';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'تخمینی: $time باقی مانده';
  }

  @override
  String get summarizingConversation => 'خلاصه کردن مکالمه...\nاین ممکن است چند ثانیه طول بکشد';

  @override
  String get resummarizingConversation => 'بازخلاصه کردن مکالمه...\nاین ممکن است چند ثانیه طول بکشد';

  @override
  String get nothingInterestingRetry => 'هیچ چیز جالب یافت نشد،\nمی خواهید دوباره تلاش کنید؟';

  @override
  String get noSummaryForConversation => 'خلاصه ای موجود نیست\nبرای این مکالمه.';

  @override
  String get unknownLocation => 'مکان نامشخص';

  @override
  String get couldNotLoadMap => 'نتوانستم نقشه را بارگذاری کنم';

  @override
  String get triggerConversationIntegration => 'فعال کردن یکپارچگی مکالمه ایجاد شده';

  @override
  String get webhookUrlNotSet => 'URL Webhook تنظیم نشده است';

  @override
  String get setWebhookUrlInSettings =>
      'لطفاً برای استفاده از این ویژگی URL webhook را در تنظیمات توسعه دهنده تنظیم کنید.';

  @override
  String get sendWebUrl => 'ارسال URL وب';

  @override
  String get sendTranscript => 'ارسال رونوشت';

  @override
  String get sendSummary => 'ارسال خلاصه';

  @override
  String get debugModeDetected => 'حالت اشکال زدایی شناسایی شد';

  @override
  String get performanceReduced => 'عملکرد 5-10 برابر کاهش یافته است. از حالت Release استفاده کنید.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'بسته شدن خودکار در ${seconds}s';
  }

  @override
  String get modelRequired => 'مدل مورد نیاز است';

  @override
  String get downloadWhisperModel => 'لطفاً قبل از ذخیره یک مدل Whisper دانلود کنید.';

  @override
  String get deviceNotCompatible => 'دستگاه سازگار نیست';

  @override
  String get deviceRequirements => 'دستگاه شما الزامات On-Device transcription را برآورده نمی کند.';

  @override
  String get willLikelyCrash => 'فعال کردن این احتمالاً باعث سقوط یا معلق شدن برنامه خواهد شد.';

  @override
  String get transcriptionSlowerLessAccurate => 'رونویسی به طور قابل توجهی کندتر و کمتر دقیق خواهد بود.';

  @override
  String get proceedAnyway => 'هر چه باشد ادامه دهید';

  @override
  String get olderDeviceDetected => 'دستگاه قدیمی تر شناسایی شد';

  @override
  String get onDeviceSlower => 'رونویسی On-device ممکن است در این دستگاه کندتر باشد.';

  @override
  String get batteryUsageHigher => 'مصرف باتری بیشتر از رونویسی ابری خواهد بود.';

  @override
  String get considerOmiCloud => 'برای عملکرد بهتر از Omi Cloud استفاده کنید.';

  @override
  String get highResourceUsage => 'مصرف منابع زیاد';

  @override
  String get onDeviceIntensive => 'رونویسی On-Device از لحاظ محاسباتی فشرده است.';

  @override
  String get batteryDrainIncrease => 'تخلیه باتری به طور قابل توجهی افزایش خواهد یافت.';

  @override
  String get deviceMayWarmUp => 'دستگاه ممکن است در هنگام استفاده طولانی مدت گرم شود.';

  @override
  String get speedAccuracyLower => 'سرعت و دقت ممکن است کمتر از مدل های ابری باشد.';

  @override
  String get cloudProvider => 'ارائه دهنده ابری';

  @override
  String get premiumMinutesInfo => '1,200 دقیقه premium/ماه. برگه On-Device رونویسی رایگان نامحدود را ارائه می دهد.';

  @override
  String get viewUsage => 'مشاهده استفاده';

  @override
  String get localProcessingInfo =>
      'صوت به صورت محلی پردازش می شود. بدون اینترنت کار می کند، خصوصی تر است، اما باتری بیشتری مصرف می کند.';

  @override
  String get model => 'مدل';

  @override
  String get performanceWarning => 'هشدار عملکرد';

  @override
  String get largeModelWarning =>
      'این مدل بزرگ است و ممکن است برنامه را سقوط دهد یا بسیار آهسته اجرا شود.\n\n\"small\" یا \"base\" توصیه می شود.';

  @override
  String get usingNativeIosSpeech => 'استفاده از شناخت گفتار بومی iOS';

  @override
  String get noModelDownloadRequired => 'موتور گفتار بومی دستگاه شما استفاده خواهد شد. بدون دانلود مدل مورد نیاز.';

  @override
  String get modelReady => 'مدل آماده است';

  @override
  String get redownload => 'دوباره دانلود کنید';

  @override
  String get doNotCloseApp => 'لطفاً برنامه را بسته نکنید.';

  @override
  String get downloading => 'در حال دانلود...';

  @override
  String get downloadModel => 'دانلود مدل';

  @override
  String estimatedSize(String size) {
    return 'اندازه تخمینی: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'فضای دسترسی: $space';
  }

  @override
  String get notEnoughSpace => 'هشدار: فضای کافی نیست!';

  @override
  String get download => 'دانلود';

  @override
  String downloadError(String error) {
    return 'خطای دانلود: $error';
  }

  @override
  String get cancelled => 'لغو شد';

  @override
  String get deviceNotCompatibleTitle => 'دستگاه سازگار نیست';

  @override
  String get deviceNotMeetRequirements => 'دستگاه شما الزامات On-Device transcription را برآورده نمی کند.';

  @override
  String get transcriptionSlowerOnDevice => 'رونویسی On-device ممکن است در این دستگاه کندتر باشد.';

  @override
  String get computationallyIntensive => 'رونویسی On-Device از لحاظ محاسباتی فشرده است.';

  @override
  String get batteryDrainSignificantly => 'تخلیه باتری به طور قابل توجهی افزایش خواهد یافت.';

  @override
  String get premiumMinutesMonth => '1,200 دقیقه premium/ماه. برگه On-Device رونویسی رایگان نامحدود را ارائه می دهد.';

  @override
  String get audioProcessedLocally =>
      'صوت به صورت محلی پردازش می شود. بدون اینترنت کار می کند، خصوصی تر است، اما باتری بیشتری مصرف می کند.';

  @override
  String get languageLabel => 'زبان';

  @override
  String get modelLabel => 'مدل';

  @override
  String get modelTooLargeWarning =>
      'این مدل بزرگ است و ممکن است برنامه را سقوط دهد یا بسیار آهسته اجرا شود.\n\n\"small\" یا \"base\" توصیه می شود.';

  @override
  String get nativeEngineNoDownload => 'موتور گفتار بومی دستگاه شما استفاده خواهد شد. بدون دانلود مدل مورد نیاز.';

  @override
  String modelReadyWithName(String model) {
    return 'مدل آماده ($model)';
  }

  @override
  String get reDownload => 'دوباره دانلود کنید';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'دانلود $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'آماده سازی $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'خطای دانلود: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'اندازه تخمینی: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'فضای دسترسی: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'رونویسی زنده تعبیه شده Omi برای مکالمات بلادرنگ با شناسایی و دیاریزاسیون گوینده خودکار بهینه شده است.';

  @override
  String get reset => 'بازنشانی';

  @override
  String get useTemplateFrom => 'استفاده از الگو از';

  @override
  String get selectProviderTemplate => 'الگوی ارائه دهنده را انتخاب کنید...';

  @override
  String get quicklyPopulateResponse => 'به سرعت با فرمت پاسخ یک ارائه دهنده شناخته شده پر کنید';

  @override
  String get quicklyPopulateRequest => 'به سرعت با فرمت درخواست یک ارائه دهنده شناخته شده پر کنید';

  @override
  String get invalidJsonError => 'JSON نامعتبر';

  @override
  String downloadModelWithName(String model) {
    return 'دانلود مدل ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'مدل: $model';
  }

  @override
  String get device => 'دستگاه';

  @override
  String get chatAssistantsTitle => 'دستیاران چت';

  @override
  String get permissionReadConversations => 'خواندن مکالمات';

  @override
  String get permissionReadMemories => 'خواندن خاطرات';

  @override
  String get permissionReadTasks => 'خواندن تکالیف';

  @override
  String get permissionCreateConversations => 'ایجاد مکالمات';

  @override
  String get permissionCreateMemories => 'ایجاد خاطرات';

  @override
  String get permissionTypeAccess => 'دسترسی';

  @override
  String get permissionTypeCreate => 'ایجاد';

  @override
  String get permissionTypeTrigger => 'فعال کردن';

  @override
  String get permissionDescReadConversations => 'این برنامه می تواند مکالمات شما را بخواند.';

  @override
  String get permissionDescReadMemories => 'این برنامه می تواند خاطرات شما را بخواند.';

  @override
  String get permissionDescReadTasks => 'این برنامه می تواند تکالیف شما را بخواند.';

  @override
  String get permissionDescCreateConversations => 'این برنامه می تواند مکالمات جدید ایجاد کند.';

  @override
  String get permissionDescCreateMemories => 'این برنامه می تواند خاطرات جدید ایجاد کند.';

  @override
  String get realtimeListening => 'شنیدن بلادرنگ';

  @override
  String get setupCompleted => 'انجام شده';

  @override
  String get pleaseSelectRating => 'لطفاً رتبه بندی را انتخاب کنید';

  @override
  String get writeReviewOptional => 'نوشتن نقد (اختیاری)';

  @override
  String get setupQuestionsIntro => 'برای بهبود Omi با پاسخ دادن به چند سؤال کمک کنید. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. شما چه کار می کنید؟';

  @override
  String get setupQuestionUsage => '2. در کجا قصد دارید از Omi خود استفاده کنید؟';

  @override
  String get setupQuestionAge => '3. محدوده سنی شما چیست؟';

  @override
  String get setupAnswerAllQuestions => 'هنوز به تمام سؤالات پاسخ ندادید! 🥺';

  @override
  String get setupSkipHelp => 'رد کن، من نمی خواهم کمک کنم :C';

  @override
  String get professionEntrepreneur => 'کارآفرین';

  @override
  String get professionSoftwareEngineer => 'مهندس نرم افزار';

  @override
  String get professionProductManager => 'مدیر محصول';

  @override
  String get professionExecutive => 'مدیر اجرایی';

  @override
  String get professionSales => 'فروش';

  @override
  String get professionStudent => 'دانشجو';

  @override
  String get usageAtWork => 'در کار';

  @override
  String get usageIrlEvents => 'رویدادهای IRL';

  @override
  String get usageOnline => 'آنلاین';

  @override
  String get usageSocialSettings => 'در تنظیمات اجتماعی';

  @override
  String get usageEverywhere => 'همه جا';

  @override
  String get customBackendUrlTitle => 'URL پایگاه داده سفارشی';

  @override
  String get backendUrlLabel => 'URL پایگاه داده';

  @override
  String get saveUrlButton => 'ذخیره URL';

  @override
  String get enterBackendUrlError => 'لطفاً URL پایگاه داده را وارد کنید';

  @override
  String get urlMustEndWithSlashError => 'URL باید با \"/\" پایان یابد';

  @override
  String get invalidUrlError => 'لطفاً URL معتبری را وارد کنید';

  @override
  String get backendUrlSavedSuccess => 'URL پایگاه داده با موفقیت ذخیره شد!';

  @override
  String get signInTitle => 'ورود';

  @override
  String get signInButton => 'ورود';

  @override
  String get enterEmailError => 'لطفاً ایمیل خود را وارد کنید';

  @override
  String get invalidEmailError => 'لطفاً ایمیل معتبری را وارد کنید';

  @override
  String get enterPasswordError => 'لطفاً کلمه عبور خود را وارد کنید';

  @override
  String get passwordMinLengthError => 'کلمه عبور باید حداقل 8 کاراکتر باشد';

  @override
  String get signInSuccess => 'ورود موفق!';

  @override
  String get alreadyHaveAccountLogin => 'از قبل حساب دارید؟ وارد شوید';

  @override
  String get emailLabel => 'ایمیل';

  @override
  String get passwordLabel => 'کلمه عبور';

  @override
  String get createAccountTitle => 'ایجاد حساب';

  @override
  String get nameLabel => 'نام';

  @override
  String get repeatPasswordLabel => 'تکرار کلمه عبور';

  @override
  String get signUpButton => 'ثبت نام';

  @override
  String get enterNameError => 'لطفاً نام خود را وارد کنید';

  @override
  String get passwordsDoNotMatch => 'کلمه های عبور مطابقت ندارند';

  @override
  String get signUpSuccess => 'ثبت نام موفق!';

  @override
  String get loadingKnowledgeGraph => 'بارگذاری نمودار دانش...';

  @override
  String get noKnowledgeGraphYet => 'هیچ نمودار دانش هنوز نیست';

  @override
  String get buildingKnowledgeGraphFromMemories => 'ساخت نمودار دانش شما از خاطرات...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'نمودار دانش شما به طور خودکار با ایجاد خاطرات جدید ساخته خواهد شد.';

  @override
  String get buildGraphButton => 'ساخت نمودار';

  @override
  String get checkOutMyMemoryGraph => 'نمودار خاطرات من را بررسی کنید!';

  @override
  String get getButton => 'دریافت';

  @override
  String openingApp(String appName) {
    return 'بازکردن $appName...';
  }

  @override
  String get writeSomething => 'چیزی بنویسید';

  @override
  String get submitReply => 'ارسال پاسخ';

  @override
  String get editYourReply => 'ویرایش پاسخ خود';

  @override
  String get replyToReview => 'پاسخ به نقد';

  @override
  String get rateAndReviewThisApp => 'رتبه بندی و نقد این برنامه';

  @override
  String get noChangesInReview => 'هیچ تغییری در نقد برای به روز رسانی وجود ندارد.';

  @override
  String get cantRateWithoutInternet => 'نمی توانید بدون اتصال اینترنت برنامه را رتبه بندی کنید.';

  @override
  String get appAnalytics => 'تحلیل برنامه';

  @override
  String get learnMoreLink => 'اطلاعات بیشتر';

  @override
  String get moneyEarned => 'درآمد کسب شده';

  @override
  String get writeYourReply => 'پاسخ خود را بنویسید...';

  @override
  String get replySentSuccessfully => 'پاسخ با موفقیت ارسال شد';

  @override
  String failedToSendReply(String error) {
    return 'ارسال پاسخ ناموفق: $error';
  }

  @override
  String get send => 'ارسال';

  @override
  String starFilter(int count) {
    return '$count ستاره';
  }

  @override
  String get noReviewsFound => 'هیچ نقد یافت نشد';

  @override
  String get editReply => 'ویرایش پاسخ';

  @override
  String get reply => 'پاسخ';

  @override
  String starFilterLabel(int count) {
    return '$count ستاره';
  }

  @override
  String get sharePublicLink => 'اشتراک گذاری پیوند عمومی';

  @override
  String get connectedKnowledgeData => 'داده های دانش متصل شده';

  @override
  String get enterName => 'نام را وارد کنید';

  @override
  String get goal => 'هدف';

  @override
  String get tapToTrackThisGoal => 'برای ردیابی این هدف ضربه بزنید';

  @override
  String get tapToSetAGoal => 'برای تعیین هدف ضربه بزنید';

  @override
  String get processedConversations => 'مکالمات پردازش شده';

  @override
  String get updatedConversations => 'مکالمات به روز شده';

  @override
  String get newConversations => 'مکالمات جدید';

  @override
  String get summaryTemplate => 'الگوی خلاصه';

  @override
  String get suggestedTemplates => 'الگوهای پیشنهادی';

  @override
  String get otherTemplates => 'الگوهای دیگر';

  @override
  String get availableTemplates => 'الگوهای موجود';

  @override
  String get getCreative => 'خلاقانه شوید';

  @override
  String get defaultLabel => 'پیش فرض';

  @override
  String get lastUsedLabel => 'آخرین استفاده';

  @override
  String get setDefaultApp => 'تنظیم برنامه پیش فرض';

  @override
  String setDefaultAppContent(String appName) {
    return 'تنظیم $appName به عنوان برنامه خلاصه سازی پیش فرض شما؟\\n\\nاین برنامه به طور خودکار برای تمام خلاصه های مکالمه آینده استفاده خواهد شد.';
  }

  @override
  String get setDefaultButton => 'تنظیم پیش فرض';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName به عنوان برنامه خلاصه سازی پیش فرض تنظیم شد';
  }

  @override
  String get createCustomTemplate => 'ایجاد الگوی سفارشی';

  @override
  String get allTemplates => 'تمام الگوها';

  @override
  String failedToInstallApp(String appName) {
    return 'نتوانستم $appName را نصب کنم. لطفاً دوباره تلاش کنید.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'خطا در نصب $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'برچسب گذاری گوینده $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'فردی با این نام از قبل وجود دارد.';

  @override
  String get selectYouFromList => 'برای برچسب گذاری خود، لطفاً \"شما\" را از فهرست انتخاب کنید.';

  @override
  String get enterPersonsName => 'نام فرد را وارد کنید';

  @override
  String get addPerson => 'اضافه کردن فرد';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'برچسب گذاری سایر بخش ها از این گوینده ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'برچسب گذاری سایر بخش ها';

  @override
  String get managePeople => 'مدیریت افراد';

  @override
  String get shareViaSms => 'اشتراک گذاری از طریق SMS';

  @override
  String get selectContactsToShareSummary => 'برای اشتراک گذاری خلاصه مکالمه خود مخاطبین را انتخاب کنید';

  @override
  String get searchContactsHint => 'جستجو مخاطبین...';

  @override
  String contactsSelectedCount(int count) {
    return '$count انتخاب شده';
  }

  @override
  String get clearAllSelection => 'حذف تمام';

  @override
  String get selectContactsToShare => 'برای اشتراک گذاری مخاطبین را انتخاب کنید';

  @override
  String shareWithContactCount(int count) {
    return 'اشتراک گذاری با $count مخاطب';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'اشتراک گذاری با $count مخاطبین';
  }

  @override
  String get contactsPermissionRequired => 'اجازه مخاطبین مورد نیاز است';

  @override
  String get contactsPermissionRequiredForSms => 'برای اشتراک گذاری از طریق SMS نیاز به اجازه مخاطبین است';

  @override
  String get grantContactsPermissionForSms => 'لطفاً برای اشتراک گذاری از طریق SMS اجازه مخاطبین را بدهید';

  @override
  String get noContactsWithPhoneNumbers => 'هیچ مخاطبی با شماره تلفن یافت نشد';

  @override
  String get noContactsMatchSearch => 'هیچ مخاطبی با جستجوی شما مطابقت ندارد';

  @override
  String get failedToLoadContacts => 'بارگذاری مخاطبین ناموفق بود';

  @override
  String get failedToPrepareConversationForSharing =>
      'آماده سازی مکالمه برای اشتراک گذاری ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get couldNotOpenSmsApp => 'نتوانستم برنامه SMS را باز کنم. لطفاً دوباره تلاش کنید.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'در اینجا آنچه تازه بحث کردیم: $link';
  }

  @override
  String get wifiSync => 'هماهنگ سازی WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item در کلیپ بورد کپی شد';
  }

  @override
  String get wifiConnectionFailedTitle => 'اتصال ناموفق';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'اتصال به $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'فعال کردن WiFi $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'اتصال به $deviceName';
  }

  @override
  String get recordingDetails => 'جزئیات ضبط';

  @override
  String get storageLocationSdCard => 'کارت SD';

  @override
  String get storageLocationLimitlessPendant => 'آویز بی محدود';

  @override
  String get storageLocationPhone => 'تلفن';

  @override
  String get storageLocationPhoneMemory => 'تلفن (حافظه)';

  @override
  String storedOnDevice(String deviceName) {
    return 'ذخیره شده در $deviceName';
  }

  @override
  String get transferring => 'در حال انتقال...';

  @override
  String get transferRequired => 'انتقال مورد نیاز است';

  @override
  String get downloadingAudioFromSdCard => 'دانلود صوت از کارت SD دستگاه';

  @override
  String get transferRequiredDescription =>
      'این ضبط روی کارت SD دستگاه شما ذخیره شده است. آن را به تلفن خود منتقل کنید تا بتوانید پخش یا اشتراک گذاری کنید.';

  @override
  String get cancelTransfer => 'لغو انتقال';

  @override
  String get transferToPhone => 'انتقال به تلفن';

  @override
  String get privateAndSecureOnDevice => 'خصوصی و امن روی دستگاه شما';

  @override
  String get recordingInfo => 'اطلاعات ضبط';

  @override
  String get transferInProgress => 'در حال انتقال...';

  @override
  String get shareRecording => 'اشتراک‌گذاری ضبط‌شده';

  @override
  String get deleteRecordingConfirmation =>
      'آیا می‌خواهید این ضبط‌شده را برای همیشه حذف کنید؟ این کار قابل بازگشت نیست.';

  @override
  String get recordingIdLabel => 'شناسه ضبط';

  @override
  String get dateTimeLabel => 'تاریخ و زمان';

  @override
  String get durationLabel => 'مدت زمان';

  @override
  String get audioFormatLabel => 'فرمت صدا';

  @override
  String get storageLocationLabel => 'مکان ذخیره‌سازی';

  @override
  String get estimatedSizeLabel => 'اندازه تخمینی';

  @override
  String get deviceModelLabel => 'مدل دستگاه';

  @override
  String get deviceIdLabel => 'شناسه دستگاه';

  @override
  String get statusLabel => 'وضعیت';

  @override
  String get statusProcessed => 'پردازش‌شده';

  @override
  String get statusUnprocessed => 'پردازش‌نشده';

  @override
  String get switchedToFastTransfer => 'به انتقال سریع تغییر یافت';

  @override
  String get transferCompleteMessage => 'انتقال تکمیل شد! اکنون می‌توانید این ضبط را پخش کنید.';

  @override
  String transferFailedMessage(String error) {
    return 'انتقال ناموفق بود: $error';
  }

  @override
  String get transferCancelled => 'انتقال لغو شد';

  @override
  String get fastTransferEnabled => 'انتقال سریع فعال شد';

  @override
  String get bluetoothSyncEnabled => 'هماهنگ‌سازی Bluetooth فعال شد';

  @override
  String get enableFastTransfer => 'فعال‌کردن انتقال سریع';

  @override
  String get fastTransferDescription =>
      'انتقال سریع از Wi-Fi برای سرعت تقریباً 5 برابر سریع‌تر استفاده می‌کند. تلفن شما به‌طور موقت در طی انتقال به شبکه Wi-Fi دستگاه Omi متصل خواهد شد.';

  @override
  String get internetAccessPausedDuringTransfer => 'دسترسی به اینترنت در طی انتقال متوقف است';

  @override
  String get chooseTransferMethodDescription => 'نحوه انتقال ضبط‌شده‌ها از دستگاه Omi به تلفن خود را انتخاب کنید.';

  @override
  String get wifiSpeed => 'تقریباً 150 کیلوبایت بر ثانیه از طریق Wi-Fi';

  @override
  String get fiveTimesFaster => '5 برابر سریع‌تر';

  @override
  String get fastTransferMethodDescription =>
      'اتصال مستقیم Wi-Fi را به دستگاه Omi ایجاد می‌کند. تلفن شما به‌طور موقت از Wi-Fi معمولی خود در طی انتقال قطع می‌شود.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => 'تقریباً 30 کیلوبایت بر ثانیه از طریق BLE';

  @override
  String get bluetoothMethodDescription =>
      'از اتصال استاندارد Bluetooth Low Energy استفاده می‌کند. کندتر اما اتصال Wi-Fi شما را تحت تأثیر قرار نمی‌دهد.';

  @override
  String get selected => 'انتخاب‌شده';

  @override
  String get selectOption => 'انتخاب کنید';

  @override
  String get lowBatteryAlertTitle => 'هشدار باتری کم';

  @override
  String get lowBatteryAlertBody => 'باتری دستگاه شما تقریباً تمام است. وقت شارژ کردن است! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'دستگاه Omi شما قطع شد';

  @override
  String get deviceDisconnectedNotificationBody => 'برای ادامه استفاده از Omi خود دوباره متصل شوید.';

  @override
  String get firmwareUpdateAvailable => 'به‌روزرسانی فیرم‌ور در دسترس است';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'به‌روزرسانی فیرم‌ور جدید ($version) برای دستگاه Omi شما در دسترس است. آیا می‌خواهید اکنون به‌روز رسانی کنید؟';
  }

  @override
  String get later => 'بعداً';

  @override
  String get appDeletedSuccessfully => 'برنامه با موفقیت حذف شد';

  @override
  String get appDeleteFailed => 'حذف برنامه ناموفق بود. لطفاً بعداً دوباره تلاش کنید.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'دید برنامه با موفقیت تغییر کرد. ممکن است چند دقیقه طول بکشد تا منعکس شود.';

  @override
  String get errorActivatingAppIntegration =>
      'خطا در فعال‌کردن برنامه. اگر این یک برنامه یکپارچگی است، مطمئن شوید که تنظیم تکمیل شده است.';

  @override
  String get errorUpdatingAppStatus => 'خطایی هنگام به‌روزرسانی وضعیت برنامه رخ داد.';

  @override
  String get calculatingETA => 'در حال محاسبه...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'تقریباً $minutes دقیقه مانده';
  }

  @override
  String get aboutAMinuteRemaining => 'تقریباً یک دقیقه مانده';

  @override
  String get almostDone => 'تقریباً تکمیل...';

  @override
  String get omiSays => 'Omi می‌گوید';

  @override
  String get analyzingYourData => 'در حال تجزیه و تحلیل داده‌های شما...';

  @override
  String migratingToProtection(String level) {
    return 'مهاجرت به حفاظت $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'هیچ داده‌ای برای مهاجرت وجود ندارد. نهایی‌سازی...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'مهاجرت $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'تمام اشیاء مهاجرت کردند. نهایی‌سازی...';

  @override
  String get migrationErrorOccurred => 'خطایی هنگام مهاجرت رخ داد. لطفاً دوباره تلاش کنید.';

  @override
  String get migrationComplete => 'مهاجرت تکمیل شد!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'داده‌های شما اکنون با تنظیمات جدید $level محفوظ هستند.';
  }

  @override
  String get chatsLowercase => 'چت‌ها';

  @override
  String get dataLowercase => 'داده';

  @override
  String get fallNotificationTitle => 'آوچ';

  @override
  String get fallNotificationBody => 'آیا افتادید؟';

  @override
  String get importantConversationTitle => 'گفتگوی مهم';

  @override
  String get importantConversationBody => 'تازه یک گفتگوی مهم داشتید. برای اشتراک‌گذاری خلاصه با دیگران ضربه بزنید.';

  @override
  String get templateName => 'نام الگو';

  @override
  String get templateNameHint => 'برای مثال، استخراج‌کننده اقلام اقدام جلسه';

  @override
  String get nameMustBeAtLeast3Characters => 'نام باید حداقل 3 کاراکتر باشد';

  @override
  String get conversationPromptHint =>
      'برای مثال، اقلام اقدام، تصمیمات گرفته‌شده و نکات کلیدی را از گفتگوی ارائه‌شده استخراج کنید.';

  @override
  String get pleaseEnterAppPrompt => 'لطفاً دستور برای برنامه خود را وارد کنید';

  @override
  String get promptMustBeAtLeast10Characters => 'دستور باید حداقل 10 کاراکتر باشد';

  @override
  String get anyoneCanDiscoverTemplate => 'هر کسی می‌تواند الگوی شما را کشف کند';

  @override
  String get onlyYouCanUseTemplate => 'تنها شما می‌توانید این الگو را استفاده کنید';

  @override
  String get generatingDescription => 'در حال تولید توضیح...';

  @override
  String get creatingAppIcon => 'در حال ایجاد نماد برنامه...';

  @override
  String get installingApp => 'در حال نصب برنامه...';

  @override
  String get appCreatedAndInstalled => 'برنامه ایجاد و نصب شد!';

  @override
  String get appCreatedSuccessfully => 'برنامه با موفقیت ایجاد شد!';

  @override
  String get failedToCreateApp => 'ایجاد برنامه ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get addAppSelectCoreCapability => 'لطفاً یک تواناییِ اصلی دیگر برای برنامه خود انتخاب کنید تا ادامه دهید';

  @override
  String get addAppSelectPaymentPlan => 'لطفاً یک نقشه پرداخت انتخاب کنید و قیمتی برای برنامه خود وارد کنید';

  @override
  String get addAppSelectCapability => 'لطفاً حداقل یک تواناییِ برای برنامه خود انتخاب کنید';

  @override
  String get addAppSelectLogo => 'لطفاً یک لوگو برای برنامه خود انتخاب کنید';

  @override
  String get addAppEnterChatPrompt => 'لطفاً یک دستور چت برای برنامه خود وارد کنید';

  @override
  String get addAppEnterConversationPrompt => 'لطفاً یک دستور گفتگو برای برنامه خود وارد کنید';

  @override
  String get addAppSelectTriggerEvent => 'لطفاً یک رویداد ماشین‌راه برای برنامه خود انتخاب کنید';

  @override
  String get addAppEnterWebhookUrl => 'لطفاً یک URL webhook برای برنامه خود وارد کنید';

  @override
  String get addAppSelectCategory => 'لطفاً یک دسته برای برنامه خود انتخاب کنید';

  @override
  String get addAppFillRequiredFields => 'لطفاً تمام فیلدهای مورد نیاز را به‌درستی پر کنید';

  @override
  String get addAppUpdatedSuccess => 'برنامه با موفقیت به‌روز شد 🚀';

  @override
  String get addAppUpdateFailed => 'به‌روزرسانی برنامه ناموفق بود. لطفاً بعداً دوباره تلاش کنید';

  @override
  String get addAppSubmittedSuccess => 'برنامه با موفقیت ارسال شد 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'خطا در باز کردن انتخاب‌کننده فایل: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'خطا در انتخاب تصویر: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'اجازه عکس‌ها رد شد. لطفاً برای انتخاب تصویر دسترسی به عکس‌ها را مجاز کنید';

  @override
  String get addAppErrorSelectingImageRetry => 'خطا در انتخاب تصویر. لطفاً دوباره تلاش کنید.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'خطا در انتخاب تصویر کوچک: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'خطا در انتخاب تصویر کوچک. لطفاً دوباره تلاش کنید.';

  @override
  String get addAppCapabilityConflictWithPersona => 'سایر توانایی‌ها نمی‌توانند با Persona انتخاب شوند';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona نمی‌تواند با سایر توانایی‌ها انتخاب شود';

  @override
  String get paymentFailedToFetchCountries => 'دریافت کشورهای پشتیبانی‌شده ناموفق بود. لطفاً بعداً دوباره تلاش کنید.';

  @override
  String get paymentFailedToSetDefault => 'تنظیم روش پرداخت پیش‌فرض ناموفق بود. لطفاً بعداً دوباره تلاش کنید.';

  @override
  String get paymentFailedToSavePaypal => 'ذخیره جزئیات PayPal ناموفق بود. لطفاً بعداً دوباره تلاش کنید.';

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
  String get paymentStatusConnected => 'متصل';

  @override
  String get paymentStatusNotConnected => 'متصل نشده';

  @override
  String get paymentAppCost => 'هزینه برنامه';

  @override
  String get paymentEnterValidAmount => 'لطفاً یک مبلغ معتبر وارد کنید';

  @override
  String get paymentEnterAmountGreaterThanZero => 'لطفاً مبلغی بیش از 0 وارد کنید';

  @override
  String get paymentPlan => 'نقشه پرداخت';

  @override
  String get paymentNoneSelected => 'هیچ کس انتخاب نشده';

  @override
  String get aiGenPleaseEnterDescription => 'لطفاً یک توضیح برای برنامه خود وارد کنید';

  @override
  String get aiGenCreatingAppIcon => 'در حال ایجاد نماد برنامه...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'خطایی رخ داد: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'برنامه با موفقیت ایجاد شد!';

  @override
  String get aiGenFailedToCreateApp => 'ایجاد برنامه ناموفق بود';

  @override
  String get aiGenErrorWhileCreatingApp => 'خطایی هنگام ایجاد برنامه رخ داد';

  @override
  String get aiGenFailedToGenerateApp => 'تولید برنامه ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get aiGenFailedToRegenerateIcon => 'تولید مجدد نماد ناموفق بود';

  @override
  String get aiGenPleaseGenerateAppFirst => 'لطفاً ابتدا یک برنامه تولید کنید';

  @override
  String get nextButton => 'بعدی';

  @override
  String get connectOmiDevice => 'دستگاه Omi را متصل کنید';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'شما نقشهِ نامحدود خود را به $title تغییر می‌دهید. آیا مطمئن هستید می‌خواهید ادامه دهید؟';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'ارتقا زمان‌بندی شد! نقشهِ ماهانهِ شما تا پایان دورهِ صورت‌حسابِ شما ادامه می‌یابد، سپس به‌طور خودکار به نقشهِ سالانه تغییر می‌کند.';

  @override
  String get couldNotSchedulePlanChange => 'نتوانست تغییر نقشه را زمان‌بندی کند. لطفاً دوباره تلاش کنید.';

  @override
  String get subscriptionReactivatedDefault =>
      'اشتراک شما دوباره فعال شد! هیچ شارژی در حال حاضر وجود ندارد - شما در پایان دورهِ فعلیِ خود شارژ شده‌اید.';

  @override
  String get subscriptionSuccessfulCharged => 'اشتراک موفق بود! برای دورهِ صورت‌حساب جدید شارژ شده‌اید.';

  @override
  String get couldNotProcessSubscription => 'نتوانست اشتراک را پردازش کند. لطفاً دوباره تلاش کنید.';

  @override
  String get couldNotLaunchUpgradePage => 'نتوانست صفحهِ ارتقا را راه‌اندازی کند. لطفاً دوباره تلاش کنید.';

  @override
  String get transcriptionJsonPlaceholder => 'تنظیم JSON خود را اینجا بچسبانید...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'خطا در باز کردن انتخاب‌کننده فایل: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'خطا: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'گفتگو‌ها با موفقیت ادغام شدند';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count گفتگو با موفقیت ادغام شدند';
  }

  @override
  String get actionItemReminderTitle => 'یادآور Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName قطع شد';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'برای ادامه استفاده از $deviceName خود دوباره متصل شوید.';
  }

  @override
  String get onboardingSignIn => 'ورود';

  @override
  String get onboardingYourName => 'نام شما';

  @override
  String get onboardingLanguage => 'زبان';

  @override
  String get onboardingPermissions => 'اجازه‌ها';

  @override
  String get onboardingComplete => 'تکمیل';

  @override
  String get onboardingWelcomeToOmi => 'به Omi خوش آمدید';

  @override
  String get onboardingTellUsAboutYourself => 'درباره خود به ما بگویید';

  @override
  String get onboardingChooseYourPreference => 'ترجیح خود را انتخاب کنید';

  @override
  String get onboardingGrantRequiredAccess => 'دسترسی مورد نیاز را اعطا کنید';

  @override
  String get onboardingYoureAllSet => 'همه چیز آماده است';

  @override
  String get searchTranscriptOrSummary => 'رونوشت یا خلاصه را جستجو کنید...';

  @override
  String get myGoal => 'هدف من';

  @override
  String get appNotAvailable => 'افسوس! به نظر می‌رسد برنامه‌ای که به دنبال آن هستید در دسترس نیست.';

  @override
  String get failedToConnectTodoist => 'اتصال به Todoist ناموفق بود';

  @override
  String get failedToConnectAsana => 'اتصال به Asana ناموفق بود';

  @override
  String get failedToConnectGoogleTasks => 'اتصال به Google Tasks ناموفق بود';

  @override
  String get failedToConnectClickUp => 'اتصال به ClickUp ناموفق بود';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'اتصال به $serviceName ناموفق بود: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'اتصال به Todoist با موفقیت برقرار شد!';

  @override
  String get failedToConnectTodoistRetry => 'اتصال به Todoist ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get successfullyConnectedAsana => 'اتصال به Asana با موفقیت برقرار شد!';

  @override
  String get failedToConnectAsanaRetry => 'اتصال به Asana ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get successfullyConnectedGoogleTasks => 'اتصال به Google Tasks با موفقیت برقرار شد!';

  @override
  String get failedToConnectGoogleTasksRetry => 'اتصال به Google Tasks ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get successfullyConnectedClickUp => 'اتصال به ClickUp با موفقیت برقرار شد!';

  @override
  String get failedToConnectClickUpRetry => 'اتصال به ClickUp ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get successfullyConnectedNotion => 'اتصال به Notion با موفقیت برقرار شد!';

  @override
  String get failedToRefreshNotionStatus => 'بازخوانی وضعیت اتصال Notion ناموفق بود.';

  @override
  String get successfullyConnectedGoogle => 'اتصال به Google با موفقیت برقرار شد!';

  @override
  String get failedToRefreshGoogleStatus => 'بازخوانی وضعیت اتصال Google ناموفق بود.';

  @override
  String get successfullyConnectedWhoop => 'اتصال به Whoop با موفقیت برقرار شد!';

  @override
  String get failedToRefreshWhoopStatus => 'بازخوانی وضعیت اتصال Whoop ناموفق بود.';

  @override
  String get successfullyConnectedGitHub => 'اتصال به GitHub با موفقیت برقرار شد!';

  @override
  String get failedToRefreshGitHubStatus => 'بازخوانی وضعیت اتصال GitHub ناموفق بود.';

  @override
  String get authFailedToSignInWithGoogle => 'ورود با Google ناموفق بود، لطفاً دوباره تلاش کنید.';

  @override
  String get authenticationFailed => 'احراز هویت ناموفق بود. لطفاً دوباره تلاش کنید.';

  @override
  String get authFailedToSignInWithApple => 'ورود با Apple ناموفق بود، لطفاً دوباره تلاش کنید.';

  @override
  String get authFailedToRetrieveToken => 'بازیابی نشانهِ Firebase ناموفق بود، لطفاً دوباره تلاش کنید.';

  @override
  String get authUnexpectedErrorFirebase => 'خطای غیرمنتظره در ورود، خطای Firebase، لطفاً دوباره تلاش کنید.';

  @override
  String get authUnexpectedError => 'خطای غیرمنتظره در ورود، لطفاً دوباره تلاش کنید';

  @override
  String get authFailedToLinkGoogle => 'پیوند با Google ناموفق بود، لطفاً دوباره تلاش کنید.';

  @override
  String get authFailedToLinkApple => 'پیوند با Apple ناموفق بود، لطفاً دوباره تلاش کنید.';

  @override
  String get onboardingBluetoothRequired => 'اجازهِ Bluetooth برای اتصال به دستگاه ضروری است.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'اجازهِ Bluetooth رد شد. لطفاً اجازه را در تنظیمات سیستم اعطا کنید.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'وضعیت اجازهِ Bluetooth: $status. لطفاً تنظیمات سیستم را بررسی کنید.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'بررسی اجازهِ Bluetooth ناموفق بود: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'اجازهِ اطلاع رسانی رد شد. لطفاً اجازه را در تنظیمات سیستم اعطا کنید.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'اجازهِ اطلاع رسانی رد شد. لطفاً اجازه را در تنظیمات سیستم > اطلاع رسانی اعطا کنید.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'وضعیت اجازهِ اطلاع رسانی: $status. لطفاً تنظیمات سیستم را بررسی کنید.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'بررسی اجازهِ اطلاع رسانی ناموفق بود: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'لطفاً اجازهِ مکان را در تنظیمات > حریم خصوصی و امنیت > خدمات مکان اعطا کنید';

  @override
  String get onboardingMicrophoneRequired => 'اجازهِ میکروفن برای ضبط ضروری است.';

  @override
  String get onboardingMicrophoneDenied =>
      'اجازهِ میکروفن رد شد. لطفاً اجازه را در تنظیمات سیستم > حریم خصوصی و امنیت > میکروفن اعطا کنید.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'وضعیت اجازهِ میکروفن: $status. لطفاً تنظیمات سیستم را بررسی کنید.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'بررسی اجازهِ میکروفن ناموفق بود: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'اجازهِ ضبطِ صفحهِ نمایش برای ضبط صدای سیستم ضروری است.';

  @override
  String get onboardingScreenCaptureDenied =>
      'اجازهِ ضبطِ صفحهِ نمایش رد شد. لطفاً اجازه را در تنظیمات سیستم > حریم خصوصی و امنیت > ضبط صفحه اعطا کنید.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'وضعیت اجازهِ ضبطِ صفحهِ نمایش: $status. لطفاً تنظیمات سیستم را بررسی کنید.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'بررسی اجازهِ ضبطِ صفحهِ نمایش ناموفق بود: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'اجازهِ دسترسی برای تشخیص جلسات مرورگر ضروری است.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'وضعیت اجازهِ دسترسی: $status. لطفاً تنظیمات سیستم را بررسی کنید.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'بررسی اجازهِ دسترسی ناموفق بود: $error';
  }

  @override
  String get msgCameraNotAvailable => 'ضبطِ دوربین در این پلتفرم در دسترس نیست';

  @override
  String get msgCameraPermissionDenied => 'اجازهِ دوربین رد شد. لطفاً دسترسی به دوربین را مجاز کنید';

  @override
  String msgCameraAccessError(String error) {
    return 'خطا در دسترسی به دوربین: $error';
  }

  @override
  String get msgPhotoError => 'خطا در گرفتن عکس. لطفاً دوباره تلاش کنید.';

  @override
  String get msgMaxImagesLimit => 'می‌توانید تا 4 عکس انتخاب کنید';

  @override
  String msgFilePickerError(String error) {
    return 'خطا در باز کردن انتخاب‌کننده فایل: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'خطا در انتخاب عکس‌ها: $error';
  }

  @override
  String get msgPhotosPermissionDenied => 'اجازهِ عکس‌ها رد شد. لطفاً برای انتخاب عکس‌ها دسترسی به عکس‌ها را مجاز کنید';

  @override
  String get msgSelectImagesGenericError => 'خطا در انتخاب عکس‌ها. لطفاً دوباره تلاش کنید.';

  @override
  String get msgMaxFilesLimit => 'می‌توانید تا 4 فایل انتخاب کنید';

  @override
  String msgSelectFilesError(String error) {
    return 'خطا در انتخاب فایل‌ها: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'خطا در انتخاب فایل‌ها. لطفاً دوباره تلاش کنید.';

  @override
  String get msgUploadFileFailed => 'بارگذاری فایل ناموفق بود، لطفاً بعداً دوباره تلاش کنید';

  @override
  String get msgReadingMemories => 'در حال خواندن خاطراتِ شما...';

  @override
  String get msgLearningMemories => 'یادگیری از خاطراتِ شما...';

  @override
  String get msgUploadAttachedFileFailed => 'بارگذاری فایل پیوست‌شده ناموفق بود.';

  @override
  String captureRecordingError(String error) {
    return 'خطایی هنگام ضبط رخ داد: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'ضبط متوقف شد: $reason. ممکن است نیاز باشد نمایشگرهای خارجی را دوباره متصل کنید یا ضبط را دوباره شروع کنید.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'اجازهِ میکروفن مورد نیاز است';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'اجازهِ میکروفن را در تنظیمات سیستم اعطا کنید';

  @override
  String get captureScreenRecordingPermissionRequired => 'اجازهِ ضبطِ صفحه مورد نیاز است';

  @override
  String get captureDisplayDetectionFailed => 'تشخیص نمایشگر ناموفق بود. ضبط متوقف شد.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'URL webhook بایت‌های صدا نامعتبر است';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'URL webhook رونوشتِ بلادرنگ نامعتبر است';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'URL webhook ایجاد گفتگو نامعتبر است';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'URL webhook خلاصهِ روز نامعتبر است';

  @override
  String get devModeSettingsSaved => 'تنظیمات ذخیره شد!';

  @override
  String get voiceFailedToTranscribe => 'رونوشت صدا ناموفق بود';

  @override
  String get locationPermissionRequired => 'اجازهِ مکان مورد نیاز است';

  @override
  String get locationPermissionContent =>
      'انتقال سریع برای تأیید اتصال Wi-Fi به اجازهِ مکان نیاز دارد. لطفاً برای ادامه اجازهِ مکان را اعطا کنید.';

  @override
  String get pdfTranscriptExport => 'صادرات رونوشت';

  @override
  String get pdfConversationExport => 'صادرات گفتگو';

  @override
  String pdfTitleLabel(String title) {
    return 'عنوان: $title';
  }

  @override
  String get conversationNewIndicator => 'جدید 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count عکس';
  }

  @override
  String get mergingStatus => 'در حال ادغام...';

  @override
  String timeSecsSingular(int count) {
    return '$count ثانیه';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count ثانیه';
  }

  @override
  String timeMinSingular(int count) {
    return '$count دقیقه';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count دقیقه';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins دقیقه $secs ثانیه';
  }

  @override
  String timeHourSingular(int count) {
    return '$count ساعت';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count ساعت';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours ساعت $mins دقیقه';
  }

  @override
  String timeDaySingular(int count) {
    return '$count روز';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count روز';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days روز $hours ساعت';
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
  String get moveToFolder => 'منتقل به پوشه';

  @override
  String get noFoldersAvailable => 'هیچ پوشه‌ای در دسترس نیست';

  @override
  String get newFolder => 'پوشه جدید';

  @override
  String get color => 'رنگ';

  @override
  String get waitingForDevice => 'در انتظار دستگاه...';

  @override
  String get saySomething => 'چیزی بگویید...';

  @override
  String get initialisingSystemAudio => 'مقدارِ اولیهِ صدای سیستم';

  @override
  String get stopRecording => 'ضبط را متوقف کنید';

  @override
  String get continueRecording => 'ادامهِ ضبط';

  @override
  String get initialisingRecorder => 'مقدارِ اولیهِ ضبط‌کننده';

  @override
  String get pauseRecording => 'ضبط را مکث کنید';

  @override
  String get resumeRecording => 'ادامهِ ضبط';

  @override
  String get noDailyRecapsYet => 'هنوز هیچ خلاصهِ روزانه‌ای وجود ندارد';

  @override
  String get dailyRecapsDescription => 'خلاصه‌های روزانهِ شما پس از تولید در اینجا ظاهر خواهد شد';

  @override
  String get chooseTransferMethod => 'انتخاب روش انتقال';

  @override
  String get fastTransferSpeed => 'تقریباً 150 کیلوبایت بر ثانیه از طریق Wi-Fi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'فاصلهِ زمانیِ بزرگ تشخیص داده شد ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'فاصله‌های زمانیِ بزرگ تشخیص داده شدند ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'دستگاه از هماهنگ‌سازی Wi-Fi پشتیبانی نمی‌کند، تغییر به Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health در این دستگاه در دسترس نیست';

  @override
  String get downloadAudio => 'دانلود صدا';

  @override
  String get audioDownloadSuccess => 'صدا با موفقیت دانلود شد';

  @override
  String get audioDownloadFailed => 'دانلود صدا ناموفق بود';

  @override
  String get downloadingAudio => 'در حال دانلود صدا...';

  @override
  String get shareAudio => 'اشتراک‌گذاری صدا';

  @override
  String get preparingAudio => 'آماده‌سازی صدا';

  @override
  String get gettingAudioFiles => 'در حال دریافت فایل‌های صدا...';

  @override
  String get downloadingAudioProgress => 'در حال دانلود صدا';

  @override
  String get processingAudio => 'پردازش صدا';

  @override
  String get combiningAudioFiles => 'در حال ترکیب فایل‌های صدا...';

  @override
  String get audioReady => 'صدا آماده است';

  @override
  String get openingShareSheet => 'در حال باز کردن برگ اشتراک‌گذاری...';

  @override
  String get audioShareFailed => 'اشتراک‌گذاری ناموفق بود';

  @override
  String get dailyRecaps => 'خلاصه‌های روزانه';

  @override
  String get removeFilter => 'حذف فیلتر';

  @override
  String get categoryConversationAnalysis => 'تجزیه و تحلیل گفتگو';

  @override
  String get categoryHealth => 'سلامت';

  @override
  String get categoryEducation => 'آموزش';

  @override
  String get categoryCommunication => 'ارتباط';

  @override
  String get categoryEmotionalSupport => 'پشتیبانی عاطفی';

  @override
  String get categoryProductivity => 'بهره‌وری';

  @override
  String get categoryEntertainment => 'سرگرمی';

  @override
  String get categoryFinancial => 'مالی';

  @override
  String get categoryTravel => 'سفر';

  @override
  String get categorySafety => 'ایمنی';

  @override
  String get categoryShopping => 'خرید';

  @override
  String get categorySocial => 'اجتماعی';

  @override
  String get categoryNews => 'اخبار';

  @override
  String get categoryUtilities => 'ابزارها';

  @override
  String get categoryOther => 'دیگر';

  @override
  String get capabilityChat => 'چت';

  @override
  String get capabilityConversations => 'گفتگو‌ها';

  @override
  String get capabilityExternalIntegration => 'یکپارچگی خارجی';

  @override
  String get capabilityNotification => 'اطلاع رسانی';

  @override
  String get triggerAudioBytes => 'بایت‌های صدا';

  @override
  String get triggerConversationCreation => 'ایجاد گفتگو';

  @override
  String get triggerTranscriptProcessed => 'رونوشت پردازش‌شده';

  @override
  String get actionCreateConversations => 'ایجاد گفتگو‌ها';

  @override
  String get actionCreateMemories => 'ایجاد خاطرات';

  @override
  String get actionReadConversations => 'خواندن گفتگو‌ها';

  @override
  String get actionReadMemories => 'خواندن خاطرات';

  @override
  String get actionReadTasks => 'خواندن وظایف';

  @override
  String get scopeUserName => 'نام کاربر';

  @override
  String get scopeUserFacts => 'حقایق کاربر';

  @override
  String get scopeUserConversations => 'گفتگو‌های کاربر';

  @override
  String get scopeUserChat => 'چتِ کاربر';

  @override
  String get capabilitySummary => 'خلاصه';

  @override
  String get capabilityFeatured => 'برگزیده';

  @override
  String get capabilityTasks => 'وظایف';

  @override
  String get capabilityIntegrations => 'یکپارچگی‌ها';

  @override
  String get categoryProductivityLifestyle => 'بهره‌وری و سبک زندگی';

  @override
  String get categorySocialEntertainment => 'شبکه‌های اجتماعی و سرگرمی';

  @override
  String get categoryProductivityTools => 'ابزارهای بهره‌وری و ابزارها';

  @override
  String get categoryPersonalWellness => 'فردی و سبک زندگی';

  @override
  String get rating => 'امتیاز';

  @override
  String get categories => 'دسته‌بندی‌ها';

  @override
  String get sortBy => 'ترتیب';

  @override
  String get highestRating => 'بالاترین امتیاز';

  @override
  String get lowestRating => 'پایین‌ترین امتیاز';

  @override
  String get resetFilters => 'بازنشانی فیلترها';

  @override
  String get applyFilters => 'اعمال فیلترها';

  @override
  String get mostInstalls => 'بیشترین نصب';

  @override
  String get couldNotOpenUrl => 'نتوانست URL را باز کند. لطفا دوباره تلاش کنید.';

  @override
  String get newTask => 'کار جدید';

  @override
  String get viewAll => 'مشاهده همه';

  @override
  String get addTask => 'افزودن کار';

  @override
  String get addMcpServer => 'افزودن سرور MCP';

  @override
  String get connectExternalAiTools => 'اتصال ابزارهای هوش مصنوعی خارجی';

  @override
  String get mcpServerUrl => 'آدرس سرور MCP';

  @override
  String mcpServerConnected(int count) {
    return '$count ابزار با موفقیت متصل شد';
  }

  @override
  String get mcpConnectionFailed => 'اتصال به سرور MCP ناموفق بود';

  @override
  String get authorizingMcpServer => 'تأیید هویت...';

  @override
  String get whereDidYouHearAboutOmi => 'چگونه ما را پیدا کردید؟';

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
  String get otherSource => 'سایر';

  @override
  String get pleaseSpecify => 'لطفا مشخص کنید';

  @override
  String get event => 'رویداد';

  @override
  String get coworker => 'همکار';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'جستجوی Google';

  @override
  String get audioPlaybackUnavailable => 'فایل صوتی برای پخش دسترسی‌پذیر نیست';

  @override
  String get audioPlaybackFailed => 'نتوانست صوت را پخش کند. فایل ممکن است خراب یا حذف شده باشد.';

  @override
  String get connectionGuide => 'راهنمای اتصال';

  @override
  String get iveDoneThis => 'این کار را انجام داده‌ام';

  @override
  String get pairNewDevice => 'جفت کردن دستگاه جدید';

  @override
  String get dontSeeYourDevice => 'دستگاه خود را نمی‌بینید؟';

  @override
  String get reportAnIssue => 'گزارش یک مشکل';

  @override
  String get pairingTitleOmi => 'روشن کردن Omi';

  @override
  String get pairingDescOmi => 'دکمه را فشار دهید و نگاه دارید تا دستگاه لرزش پیدا کند.';

  @override
  String get pairingTitleOmiDevkit => 'قرار دادن Omi DevKit در حالت جفت‌کردن';

  @override
  String get pairingDescOmiDevkit => 'دکمه را یک بار فشار دهید تا روشن شود. LED هنگام جفت‌کردن بنفش خواهد چشمک زد.';

  @override
  String get pairingTitleOmiGlass => 'روشن کردن Omi Glass';

  @override
  String get pairingDescOmiGlass => 'با فشار دادن دکمه کناری برای 3 ثانیه خاموشی را روشن کنید.';

  @override
  String get pairingTitlePlaudNote => 'قرار دادن Plaud Note در حالت جفت‌کردن';

  @override
  String get pairingDescPlaudNote =>
      'دکمه کناری را برای 2 ثانیه فشار دهید و نگاه دارید. LED قرمز هنگام آماده‌باش برای جفت‌کردن چشمک خواهد زد.';

  @override
  String get pairingTitleBee => 'قرار دادن Bee در حالت جفت‌کردن';

  @override
  String get pairingDescBee => 'دکمه را 5 بار متوالی فشار دهید. نور آبی و سبز خواهد چشمک زد.';

  @override
  String get pairingTitleLimitless => 'قرار دادن Limitless در حالت جفت‌کردن';

  @override
  String get pairingDescLimitless =>
      'هنگامی که چراغی دیده شود، یک بار فشار دهید و سپس فشار دهید و نگاه دارید تا دستگاه نور صورتی نشان دهد، سپس رها کنید.';

  @override
  String get pairingTitleFriendPendant => 'قرار دادن Friend Pendant در حالت جفت‌کردن';

  @override
  String get pairingDescFriendPendant =>
      'دکمه روی مدال را فشار دهید تا روشن شود. به‌طور خودکار وارد حالت جفت‌کردن خواهد شد.';

  @override
  String get pairingTitleFieldy => 'قرار دادن Fieldy در حالت جفت‌کردن';

  @override
  String get pairingDescFieldy => 'دستگاه را فشار دهید و نگاه دارید تا نور ظاهر شود.';

  @override
  String get pairingTitleAppleWatch => 'اتصال Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'برنامه Omi را روی Apple Watch نصب و باز کنید، سپس در برنامه روی Connect ضربه بزنید.';

  @override
  String get pairingTitleNeoOne => 'قرار دادن Neo One در حالت جفت‌کردن';

  @override
  String get pairingDescNeoOne => 'دکمه برق را فشار دهید و نگاه دارید تا LED چشمک بزند. دستگاه قابل کشف خواهد بود.';

  @override
  String get downloadingFromDevice => 'دانلود از دستگاه';

  @override
  String get reconnectingToInternet => 'بازاتصال به اینترنت...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'آپلود $current از $total';
  }

  @override
  String get processingOnServer => 'پردازش روی سرور...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'پردازش... $current/$total بخش';
  }

  @override
  String get processedStatus => 'پردازش شده';

  @override
  String get corruptedStatus => 'خراب';

  @override
  String nPending(int count) {
    return '$count در انتظار';
  }

  @override
  String nProcessed(int count) {
    return '$count پردازش شده';
  }

  @override
  String get synced => 'همگام‌سازی شده';

  @override
  String get noPendingRecordings => 'بدون ضبط‌های در انتظار';

  @override
  String get noProcessedRecordings => 'هنوز بدون ضبط‌های پردازش شده';

  @override
  String get pending => 'در انتظار';

  @override
  String whatsNewInVersion(String version) {
    return 'جدیدترین‌های نسخه $version';
  }

  @override
  String get addToYourTaskList => 'افزودن به فهرست کارهای شما؟';

  @override
  String get failedToCreateShareLink => 'انشاء لینک اشتراک ناموفق بود';

  @override
  String get deleteGoal => 'حذف هدف';

  @override
  String get deviceUpToDate => 'دستگاه شما به‌روز است';

  @override
  String get wifiConfiguration => 'تنظیم WiFi';

  @override
  String get wifiConfigurationSubtitle => 'مختصات WiFi خود را وارد کنید تا دستگاه بتواند فیرم‌ور را دانلود کند.';

  @override
  String get networkNameSsid => 'نام شبکه (SSID)';

  @override
  String get enterWifiNetworkName => 'نام شبکه WiFi را وارد کنید';

  @override
  String get enterWifiPassword => 'رمز WiFi را وارد کنید';

  @override
  String get appIconLabel => 'نماد برنامه';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'این چیزهایی هستند که درباره شما می‌دانم';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'این نقشه با یادگیری Omi از گفتگوهای شما به‌روز شود.';

  @override
  String get apiEnvironment => 'محیط API';

  @override
  String get apiEnvironmentDescription => 'انتخاب کنید کدام سرویس‌گیر را مورد اتصال قرار دهید';

  @override
  String get production => 'تولید';

  @override
  String get staging => 'انتقالی';

  @override
  String get switchRequiresRestart => 'تغییر نیاز به راه‌اندازی مجدد برنامه دارد';

  @override
  String get switchApiConfirmTitle => 'تبدیل محیط API';

  @override
  String switchApiConfirmBody(String environment) {
    return 'تغییر به $environment؟ برای اعمال تغییرات باید برنامه را ببندید و دوباره باز کنید.';
  }

  @override
  String get switchAndRestart => 'تغییر';

  @override
  String get stagingDisclaimer =>
      'انتقالی ممکن است دارای اشکال باشد، عملکرد نامتناسب داشته باشد و داده‌ها ممکن است از دست برود. فقط برای آزمایش استفاده کنید.';

  @override
  String get apiEnvSavedRestartRequired => 'ذخیره شد. برنامه را ببندید و دوباره باز کنید تا اعمال شود.';

  @override
  String get shared => 'اشتراک شده';

  @override
  String get onlyYouCanSeeConversation => 'فقط شما می‌توانید این گفتگو را ببینید';

  @override
  String get anyoneWithLinkCanView => 'هر کسی با لینک می‌تواند ببیند';

  @override
  String get tasksCleanTodayTitle => 'کارهای امروز را پاک کنید؟';

  @override
  String get tasksCleanTodayMessage => 'این فقط ددلاین‌ها را حذف خواهد کرد';

  @override
  String get tasksOverdue => 'تاخیری';

  @override
  String get phoneCallsWithOmi => 'تماس‌های تلفنی با Omi';

  @override
  String get phoneCallsSubtitle => 'تماس بگیرید با رونویسی زمان‌حقیقی';

  @override
  String get phoneSetupStep1Title => 'تأیید شماره تلفن خود';

  @override
  String get phoneSetupStep1Subtitle => 'ما برای تأیید این‌که متعلق به شما است تماس خواهیم گرفت';

  @override
  String get phoneSetupStep2Title => 'وارد کردن کد تأیید';

  @override
  String get phoneSetupStep2Subtitle => 'کد کوتاهی که در طول تماس تایپ خواهید کرد';

  @override
  String get phoneSetupStep3Title => 'شروع به تماس با مخاطبین خود کنید';

  @override
  String get phoneSetupStep3Subtitle => 'با رونویسی زمان‌حقیقی درون‌ساخت';

  @override
  String get phoneGetStarted => 'شروع کنید';

  @override
  String get callRecordingConsentDisclaimer => 'ضبط تماس ممکن است نیاز به رضایت در حوزه قانونی شما داشته باشد';

  @override
  String get enterYourNumber => 'شماره خود را وارد کنید';

  @override
  String get phoneNumberCallerIdHint => 'پس از تأیید، این شماره شناسه تماس‌گیرنده شما خواهد شد';

  @override
  String get phoneNumberHint => 'شماره تلفن';

  @override
  String get failedToStartVerification => 'شروع تأیید ناموفق بود';

  @override
  String get phoneContinue => 'ادامه';

  @override
  String get verifyYourNumber => 'شماره خود را تأیید کنید';

  @override
  String get answerTheCallFrom => 'به تماس از جواب دهید';

  @override
  String get onTheCallEnterThisCode => 'در طول تماس، این کد را وارد کنید';

  @override
  String get followTheVoiceInstructions => 'دستورالعمل‌های صدایی را دنبال کنید';

  @override
  String get statusCalling => 'درحال تماس...';

  @override
  String get statusCallInProgress => 'تماس جاری است';

  @override
  String get statusVerifiedLabel => 'تأیید شده';

  @override
  String get statusCallMissed => 'تماس غفلت‌زده';

  @override
  String get statusTimedOut => 'مهلت زمانی تمام شد';

  @override
  String get phoneTryAgain => 'دوباره تلاش کنید';

  @override
  String get phonePageTitle => 'تلفن';

  @override
  String get phoneContactsTab => 'مخاطبین';

  @override
  String get phoneKeypadTab => 'صفحه کلید';

  @override
  String get grantContactsAccess => 'اجازه دسترسی به مخاطبین خود را بدهید';

  @override
  String get phoneAllow => 'اجازه دهید';

  @override
  String get phoneSearchHint => 'جستجو';

  @override
  String get phoneNoContactsFound => 'هیچ مخاطب پیدا نشد';

  @override
  String get phoneEnterNumber => 'شماره را وارد کنید';

  @override
  String get failedToStartCall => 'شروع تماس ناموفق بود';

  @override
  String get callStateConnecting => 'در حال اتصال...';

  @override
  String get callStateRinging => 'درحال زنگ خوردن...';

  @override
  String get callStateEnded => 'تماس پایان یافت';

  @override
  String get callStateFailed => 'تماس ناموفق بود';

  @override
  String get transcriptPlaceholder => 'رونویسی در اینجا ظاهر خواهد شد...';

  @override
  String get phoneUnmute => 'بی‌سکوت کردن';

  @override
  String get phoneMute => 'سکوت';

  @override
  String get phoneSpeaker => 'بلندگو';

  @override
  String get phoneEndCall => 'پایان';

  @override
  String get phoneCallSettingsTitle => 'تنظیمات تماس تلفنی';

  @override
  String get showPhoneCallButtonTitle => 'نمایش دکمه تماس';

  @override
  String get showPhoneCallButtonDesc => 'نمایش دکمه تماس تلفنی در صفحه اصلی';

  @override
  String get yourVerifiedNumbers => 'شماره‌های تأیید شده شما';

  @override
  String get verifiedNumbersDescription => 'هنگامی که شما تماس می‌گیرید، طرف مقابل این شماره را روی تلفن خود خواهد دید';

  @override
  String get noVerifiedNumbers => 'بدون شماره تأیید شده';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return '$phoneNumber را حذف کنید؟';
  }

  @override
  String get deletePhoneNumberWarning => 'برای تماس‌گیری باید دوباره تأیید کنید';

  @override
  String get phoneDeleteButton => 'حذف';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'تأیید شده $minutesد پیش';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'تأیید شده $hoursس پیش';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'تأیید شده $daysر پیش';
  }

  @override
  String verifiedOnDate(String date) {
    return 'تأیید شده در $date';
  }

  @override
  String get verifiedFallback => 'تأیید شده';

  @override
  String get callAlreadyInProgress => 'تماس دیگری در حال انجام است';

  @override
  String get failedToGetCallToken => 'دریافت توکن تماس ناموفق بود. ابتدا شماره تلفن خود را تأیید کنید.';

  @override
  String get failedToInitializeCallService => 'اولیه‌سازی سرویس تماس ناموفق بود';

  @override
  String get speakerLabelYou => 'شما';

  @override
  String get speakerLabelUnknown => 'نامشخص';

  @override
  String get showDailyScoreOnHomepage => 'نمایش امتیاز روزانه در صفحه اصلی';

  @override
  String get showTasksOnHomepage => 'نمایش کارها در صفحه اصلی';

  @override
  String get phoneCallsUnlimitedOnly => 'تماس‌های تلفنی از طریق Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'از طریق Omi تماس بگیرید و رونویسی زمان‌حقیقی، خلاصه‌های خودکار و موارد دیگر را دریافت کنید. منحصراً برای مشترکین نسخه Unlimited در دسترس است.';

  @override
  String get phoneCallsUpsellFeature1 => 'رونویسی زمان‌حقیقی هر تماس';

  @override
  String get phoneCallsUpsellFeature2 => 'خلاصه‌های خودکار تماس و موارد عمل';

  @override
  String get phoneCallsUpsellFeature3 => 'گیرندگان شماره واقعی شما را می‌بینند، نه یک عدد تصادفی';

  @override
  String get phoneCallsUpsellFeature4 => 'تماس‌های شما خصوصی و ایمن هستند';

  @override
  String get phoneCallsUpgradeButton => 'ارتقا به Unlimited';

  @override
  String get phoneCallsMaybeLater => 'شاید بعدا';

  @override
  String get deleteSynced => 'حذف همگام‌سازی شده';

  @override
  String get deleteSyncedFiles => 'حذف ضبط‌های همگام‌سازی شده';

  @override
  String get deleteSyncedFilesMessage => 'این ضبط‌ها قبلا به تلفن شما همگام‌سازی شده‌اند. این قابل بازگشت نیست.';

  @override
  String get syncedFilesDeleted => 'ضبط‌های همگام‌سازی شده حذف شدند';

  @override
  String get deletePending => 'حذف در انتظار';

  @override
  String get deletePendingFiles => 'حذف ضبط‌های در انتظار';

  @override
  String get deletePendingFilesWarning =>
      'این ضبط‌ها به تلفن شما همگام‌سازی نشده‌اند و برای همیشه از دست خواهند رفت. این قابل بازگشت نیست.';

  @override
  String get pendingFilesDeleted => 'ضبط‌های در انتظار حذف شدند';

  @override
  String get deleteAllFiles => 'حذف تمام ضبط‌ها';

  @override
  String get deleteAll => 'حذف همه';

  @override
  String get deleteAllFilesWarning =>
      'این کار تمام ضبط‌های همگام‌سازی شده و در انتظار را حذف خواهد کرد. ضبط‌های در انتظار به تلفن شما همگام‌سازی نشده‌اند و برای همیشه از دست خواهند رفت. این قابل بازگشت نیست.';

  @override
  String get allFilesDeleted => 'تمام ضبط‌ها حذف شدند';

  @override
  String nFiles(int count) {
    return '$count ضبط';
  }

  @override
  String get manageStorage => 'مدیریت فضای ذخیره‌سازی';

  @override
  String get safelyBackedUp => 'به‌طور ایمن در تلفن شما پشتیبان‌گیری شد';

  @override
  String get notYetSynced => 'هنوز به تلفن شما همگام‌سازی نشده‌است';

  @override
  String get clearAll => 'پاک کردن همه';

  @override
  String get phoneKeypad => 'صفحه کلید';

  @override
  String get phoneHideKeypad => 'پنهان کردن صفحه کلید';

  @override
  String get fairUsePolicy => 'استفاده منصفانه';

  @override
  String get fairUseLoadError => 'بارگذاری وضعیت استفاده منصفانه ناموفق بود. لطفا دوباره تلاش کنید.';

  @override
  String get fairUseStatusNormal => 'میزان استفاده شما در حدود معمول است.';

  @override
  String get fairUseStageNormal => 'عادی';

  @override
  String get fairUseStageWarning => 'هشدار';

  @override
  String get fairUseStageThrottle => 'محدود شده';

  @override
  String get fairUseStageRestrict => 'محدود';

  @override
  String get fairUseSpeechUsage => 'استفاده از گفتار';

  @override
  String get fairUseToday => 'امروز';

  @override
  String get fairUse3Day => 'غلتش 3 روزه';

  @override
  String get fairUseWeekly => 'غلتش هفتگی';

  @override
  String get fairUseAboutTitle => 'درباره استفاده منصفانه';

  @override
  String get fairUseAboutBody =>
      'Omi برای گفتگوهای شخصی، جلسات و تعاملات زنده طراحی شده‌است. استفاده بر اساس زمان گفتار واقعی تشخیص‌داده‌شده، نه زمان اتصال اندازه‌گیری می‌شود. اگر استفاده به‌طور قابل‌توجهی از الگوهای معمول برای محتوای غیرشخصی تجاوز کند، تعدیل‌هایی اعمال قد می‌شود.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef کپی شد';
  }

  @override
  String get fairUseDailyTranscription => 'رونویسی روزانه';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '$usedد / $limitد';
  }

  @override
  String get fairUseBudgetExhausted => 'محدودیت رونویسی روزانه به پایان رسید';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'بازنشانی $time';
  }

  @override
  String get transcriptionPaused => 'ضبط، بازاتصال';

  @override
  String get transcriptionPausedReconnecting => 'هنوز ضبط می‌شود — دوباره اتصال به رونویسی...';

  @override
  String fairUseBannerStatus(String status) {
    return 'استفاده منصفانه: $status';
  }

  @override
  String get improveConnectionTitle => 'بهبود اتصال';

  @override
  String get improveConnectionContent =>
      'ما نحوه اتصال Omi به دستگاه شما را بهبود دادیم. برای فعال کردن آن، لطفا به صفحه اطلاعات دستگاه بروید، روی \"قطع دستگاه\" ضربه بزنید و سپس دستگاه خود را دوباره جفت کنید.';

  @override
  String get improveConnectionAction => 'فهمیدم';

  @override
  String clockSkewWarning(int minutes) {
    return 'ساعت دستگاه شما تقریبا $minutes دقیقه جلو یا عقب است. تنظیمات تاریخ و ساعت را بررسی کنید.';
  }

  @override
  String get omisStorage => 'فضای ذخیره‌سازی Omi';

  @override
  String get phoneStorage => 'فضای ذخیره‌سازی تلفن';

  @override
  String get cloudStorage => 'فضای ذخیره‌سازی ابری';

  @override
  String get howSyncingWorks => 'نحوه کار همگام‌سازی';

  @override
  String get noSyncedRecordings => 'هنوز بدون ضبط‌های همگام‌سازی شده';

  @override
  String get recordingsSyncAutomatically => 'ضبط‌ها به‌طور خودکار همگام‌سازی می‌شوند — هیچ اقدامی لازم نیست.';

  @override
  String get filesDownloadedUploadedNextTime => 'فایل‌های بارگذاری‌شده قبلا در دفعه بعد بارگذاری خواهند شد.';

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
  String get tapToView => 'برای مشاهده ضربه بزنید';

  @override
  String get syncFailed => 'همگام‌سازی ناموفق بود';

  @override
  String get keepSyncing => 'همگام‌سازی را ادامه دهید';

  @override
  String get cancelSyncQuestion => 'همگام‌سازی را لغو کنید؟';

  @override
  String get omisStorageDesc =>
      'هنگامی که Omi به تلفن شما متصل نیست، صوت را به‌طور محلی روی حافظه داخلی‌اش ذخیره می‌کند. شما هرگز ضبط را از دست نمی‌دهید.';

  @override
  String get phoneStorageDesc =>
      'هنگامی که Omi دوباره متصل شود، ضبط‌ها به‌طور خودکار به تلفن شما به‌عنوان یک ناحیه نگهداری موقت قبل از بارگذاری منتقل می‌شوند.';

  @override
  String get cloudStorageDesc =>
      'پس از بارگذاری، ضبط‌های شما پردازش و رونویسی می‌شوند. گفتگوها در عرض یک دقیقه در دسترس خواهند بود.';

  @override
  String get tipKeepPhoneNearby => 'تلفن خود را نزدیک نگاه دارید تا همگام‌سازی سریع‌تر شود';

  @override
  String get tipStableInternet => 'سرعات اینترنت پایدار بارگذاری ابری را تسریع می‌کند';

  @override
  String get tipAutoSync => 'ضبط‌ها به‌طور خودکار همگام‌سازی می‌شوند';

  @override
  String get storageSection => 'فضای ذخیره‌سازی';

  @override
  String get permissions => 'مجوزها';

  @override
  String get permissionEnabled => 'فعال شده';

  @override
  String get permissionEnable => 'فعال کردن';

  @override
  String get permissionsPageDescription =>
      'این مجوزها برای کار کردن Omi بسیار مهم‌اند. آن‌ها ویژگی‌های کلیدی مانند اطلاعات، تجربیات مبتنی بر مکان و ضبط صوت را فعال می‌کنند.';

  @override
  String get permissionsRequiredDescription =>
      'Omi برای کار صحیح به چند مجوز نیاز دارد. برای ادامه لطفا آن‌ها را اعطا کنید.';

  @override
  String get permissionsSetupTitle => 'بهترین تجربه را بدست آورید';

  @override
  String get permissionsSetupDescription => 'چند مجوز را فعال کنید تا Omi بتواند جادو کند.';

  @override
  String get permissionsChangeAnytime => 'می‌توانید این مجوزها را هر زمان در تنظیمات > مجوزها تغییر دهید';

  @override
  String get location => 'مکان';

  @override
  String get microphone => 'میکروفن';

  @override
  String get whyAreYouCanceling => 'چرا لغو می‌کنید؟';

  @override
  String get cancelReasonSubtitle => 'می‌توانید بگویید چرا می‌روید؟';

  @override
  String get cancelReasonTooExpensive => 'بیش از حد گران است';

  @override
  String get cancelReasonNotUsing => 'به‌اندازه کافی از آن استفاده نمی‌کنم';

  @override
  String get cancelReasonMissingFeatures => 'ویژگی‌های گمشده';

  @override
  String get cancelReasonAudioQuality => 'کیفیت صوت/رونویسی';

  @override
  String get cancelReasonBatteryDrain => 'نگرانی‌های تخلیه باتری';

  @override
  String get cancelReasonFoundAlternative => 'یک جایگزین پیدا کردم';

  @override
  String get cancelReasonOther => 'سایر';

  @override
  String get tellUsMore => 'بیشتر بگویید (اختیاری)';

  @override
  String get cancelReasonDetailHint => 'ما از هر نظری قدردان هستیم...';

  @override
  String get justAMoment => 'لطفا صبر کنید';

  @override
  String get cancelConsequencesSubtitle => 'ما به شدت توصیه می‌کنیم گزینه‌های دیگر را کاوش کنید به جای لغو.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'نسخه شما تا $date فعال خواهد ماند. پس از آن، به نسخه رایگان با ویژگی‌های محدود منتقل خواهید شد.';
  }

  @override
  String get ifYouCancel => 'اگر لغو کنید:';

  @override
  String get cancelConsequenceNoAccess => 'در پایان دوره صورت‌حساب دیگر دسترسی نامحدود ندارید.';

  @override
  String get cancelConsequenceBattery => 'مصرف باتری 7 برابر بیشتر (پردازش روی دستگاه)';

  @override
  String get cancelConsequenceQuality => 'کیفیت رونویسی 30٪ پایین‌تر (مدل‌های روی دستگاه)';

  @override
  String get cancelConsequenceDelay => 'تاخیر پردازش 5-7 ثانیه (مدل‌های روی دستگاه)';

  @override
  String get cancelConsequenceSpeakers => 'نمی‌تواند گوینده‌ها را شناسایی کند.';

  @override
  String get confirmAndCancel => 'تأیید و لغو';

  @override
  String get cancelConsequencePhoneCalls => 'بدون رونویسی تماس تلفنی زمان‌حقیقی';

  @override
  String get feedbackTitleTooExpensive => 'چه قیمتی برای شما مناسب است؟';

  @override
  String get feedbackTitleMissingFeatures => 'چه ویژگی‌هایی را از دست دادید؟';

  @override
  String get feedbackTitleAudioQuality => 'چه مشکلاتی را تجربه کردید؟';

  @override
  String get feedbackTitleBatteryDrain => 'درباره مشکلات باتری بگویید';

  @override
  String get feedbackTitleFoundAlternative => 'به چه چیز روی می‌آورید؟';

  @override
  String get feedbackTitleNotUsing => 'چه چیز Omi را برای شما مفید‌تر می‌کند؟';

  @override
  String get feedbackSubtitleTooExpensive => 'نظر شما به ما در یافتن تعادل صحیح کمک می‌کند.';

  @override
  String get feedbackSubtitleMissingFeatures => 'ما همیشه در حال ساخت هستیم — این به ما کمک می‌کند اولویت بندی کنیم.';

  @override
  String get feedbackSubtitleAudioQuality => 'ما دوست داریم بفهمیم چه چیز غلط شد.';

  @override
  String get feedbackSubtitleBatteryDrain => 'این به تیم سخت‌افزار ما کمک می‌کند تا بهبود کند.';

  @override
  String get feedbackSubtitleFoundAlternative => 'ما دوست داریم بدانیم که چه چیز توجه شما را جلب کرد.';

  @override
  String get feedbackSubtitleNotUsing => 'ما می‌خواهیم Omi را برای شما مفید‌تر کنیم.';

  @override
  String get deviceDiagnostics => 'تشخیص دستگاه';

  @override
  String get signalStrength => 'قوت سیگنال';

  @override
  String get connectionUptime => 'وقت‌فعال';

  @override
  String get reconnections => 'باز اتصال‌ها';

  @override
  String get disconnectHistory => 'سابقه قطع';

  @override
  String get noDisconnectsRecorded => 'بدون قطع ثبت شده';

  @override
  String get diagnostics => 'تشخیص';

  @override
  String get waitingForData => 'درانتظار داده‌ها...';

  @override
  String get liveRssiOverTime => 'RSSI زنده در طول زمان';

  @override
  String get noRssiDataYet => 'هنوز داده RSSI نیست';

  @override
  String get collectingData => 'جمع‌آوری داده‌ها...';

  @override
  String get cleanDisconnect => 'قطع تمیز';

  @override
  String get connectionTimeout => 'مهلت زمانی اتصال';

  @override
  String get remoteDeviceTerminated => 'دستگاه دور خاتمه یافت';

  @override
  String get pairedToAnotherPhone => 'جفت شده با تلفن دیگری';

  @override
  String get linkKeyMismatch => 'عدم تطابق کلید پیوند';

  @override
  String get connectionFailed => 'اتصال ناموفق بود';

  @override
  String get appClosed => 'برنامه بسته شد';

  @override
  String get manualDisconnect => 'قطع دستی';

  @override
  String lastNEvents(int count) {
    return 'آخرین $count رویداد';
  }

  @override
  String get signal => 'سیگنال';

  @override
  String get battery => 'باتری';

  @override
  String get excellent => 'عالی';

  @override
  String get good => 'خوب';

  @override
  String get fair => 'قابل قبول';

  @override
  String get weak => 'ضعیف';

  @override
  String gattError(String code) {
    return 'خطای GATT ($code)';
  }

  @override
  String get batteryHistory => 'باتری';

  @override
  String get noBatteryDataYet => 'هنوز داده‌ای از باتری موجود نیست';

  @override
  String get day => 'روز';

  @override
  String get week => 'هفته';

  @override
  String get rollbackToStableFirmware => 'برگشت به فیرم‌ور پایدار';

  @override
  String get rollbackConfirmTitle => 'فیرم‌ور را برگرداند؟';

  @override
  String rollbackConfirmMessage(String version) {
    return 'این فیرم‌ور فعلی شما را با آخرین نسخه پایدار ($version) جایگزین خواهد کرد. دستگاه شما پس از به‌روز‌رسانی راه‌اندازی مجدد خواهد شد.';
  }

  @override
  String get stableFirmware => 'فیرم‌ور پایدار';

  @override
  String get fetchingStableFirmware => 'بازیافت آخرین فیرم‌ور پایدار...';

  @override
  String get noStableFirmwareFound => 'نتوانست نسخه فیرم‌ور پایدار برای دستگاه شما پیدا کند.';

  @override
  String get installStableFirmware => 'نصب فیرم‌ور پایدار';

  @override
  String get alreadyOnStableFirmware => 'شما قبلا در آخرین نسخه پایدار هستید.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration صوت ذخیره شده محلی';
  }

  @override
  String get willSyncAutomatically => 'به‌طور خودکار همگام‌سازی خواهد شد';

  @override
  String get enableLocationTitle => 'فعال کردن مکان';

  @override
  String get enableLocationDescription => 'مجوز مکان برای یافتن دستگاه‌های Bluetooth نزدیک لازم است.';

  @override
  String get voiceRecordingFound => 'ضبط پیدا شد';

  @override
  String get transcriptionConnecting => 'اتصال رونویسی...';

  @override
  String get transcriptionReconnecting => 'باز اتصال رونویسی...';

  @override
  String get transcriptionUnavailable => 'رونویسی در دسترس نیست';

  @override
  String get audioOutput => 'خروجی صوت';

  @override
  String get firmwareWarningTitle => 'مهم: قبل از به‌روزرسانی بخوانید';

  @override
  String get firmwareFormatWarning =>
      'این فریمور کارت SD را فرمت می‌کند. لطفاً قبل از ارتقا مطمئن شوید که تمام داده‌های آفلاین همگام‌سازی شده‌اند.\n\nاگر بعد از نصب این نسخه چراغ قرمز چشمک‌زن دیدید، نگران نشوید. کافی است دستگاه را به برنامه متصل کنید و باید آبی شود. چراغ قرمز به این معنی است که ساعت دستگاه هنوز همگام‌سازی نشده است.';

  @override
  String get continueAnyway => 'ادامه';

  @override
  String get tasksClearCompleted => 'پاک کردن تکمیل‌شده‌ها';

  @override
  String get tasksSelectAll => 'انتخاب همه';

  @override
  String tasksDeleteSelected(int count) {
    return 'حذف $count وظیفه';
  }

  @override
  String get tasksMarkComplete => 'به عنوان تکمیل‌شده علامت‌گذاری شد';

  @override
  String get appleHealthManageNote =>
      'Omi از طریق چارچوب HealthKit اپل به Apple Health دسترسی دارد. در هر زمان می‌توانید دسترسی را از تنظیمات iOS لغو کنید.';

  @override
  String get appleHealthConnectCta => 'اتصال به Apple Health';

  @override
  String get appleHealthDisconnectCta => 'قطع اتصال از Apple Health';

  @override
  String get appleHealthConnectedBadge => 'متصل';

  @override
  String get appleHealthFeatureChatTitle => 'درباره سلامتی خود گفتگو کنید';

  @override
  String get appleHealthFeatureChatDesc => 'از Omi درباره قدم‌ها، خواب، ضربان قلب و تمرین‌های خود بپرسید.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'دسترسی فقط خواندنی';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi هرگز در Apple Health نمی‌نویسد و داده‌های شما را تغییر نمی‌دهد.';

  @override
  String get appleHealthFeatureSecureTitle => 'همگام‌سازی امن';

  @override
  String get appleHealthFeatureSecureDesc => 'داده‌های Apple Health شما به‌صورت خصوصی با حساب Omi همگام می‌شوند.';

  @override
  String get appleHealthDeniedTitle => 'دسترسی به Apple Health رد شد';

  @override
  String get appleHealthDeniedBody =>
      'Omi مجوز خواندن داده‌های Apple Health شما را ندارد. آن را در تنظیمات iOS ← حریم خصوصی و امنیت ← Health ← Omi فعال کنید.';

  @override
  String get deleteFlowReasonTitle => 'چرا می‌روید؟';

  @override
  String get deleteFlowReasonSubtitle => 'بازخورد شما به ما کمک می‌کند Omi را برای همه بهتر کنیم.';

  @override
  String get deleteReasonPrivacy => 'نگرانی‌های حریم خصوصی';

  @override
  String get deleteReasonNotUsing => 'به اندازه کافی استفاده نمی‌کنم';

  @override
  String get deleteReasonMissingFeatures => 'ویژگی‌هایی که نیاز دارم وجود ندارد';

  @override
  String get deleteReasonTechnicalIssues => 'مشکلات فنی زیاد';

  @override
  String get deleteReasonFoundAlternative => 'از چیز دیگری استفاده می‌کنم';

  @override
  String get deleteReasonTakingBreak => 'فقط کمی استراحت می‌کنم';

  @override
  String get deleteReasonOther => 'دیگر';

  @override
  String get deleteFlowFeedbackTitle => 'بیشتر بگویید';

  @override
  String get deleteFlowFeedbackSubtitle => 'چه چیزی باعث می‌شد Omi برای شما مفید باشد؟';

  @override
  String get deleteFlowFeedbackHint => 'اختیاری — نظرات شما به ما کمک می‌کند محصول بهتری بسازیم.';

  @override
  String get deleteFlowConfirmTitle => 'این عمل برگشت‌ناپذیر است';

  @override
  String get deleteFlowConfirmSubtitle => 'پس از حذف حساب، راهی برای بازیابی آن وجود ندارد.';

  @override
  String get deleteConsequenceSubscription => 'هرگونه اشتراک فعال لغو خواهد شد.';

  @override
  String get deleteConsequenceNoRecovery => 'حساب شما قابل بازیابی نیست — حتی توسط پشتیبانی.';

  @override
  String get deleteTypeToConfirm => 'برای تأیید، DELETE را تایپ کنید';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'حذف دائمی حساب';

  @override
  String get keepMyAccount => 'حفظ حساب من';

  @override
  String get deleteAccountFailed => 'حذف حساب شما ممکن نشد. لطفاً دوباره تلاش کنید.';

  @override
  String get planUpdate => 'به‌روزرسانی طرح';

  @override
  String get planDeprecationMessage =>
      'طرح Unlimited شما در حال بازنشسته شدن است. به طرح Operator تغییر دهید — همان ویژگی‌های عالی با \$49/ماه. طرح فعلی شما در این مدت به کار خود ادامه خواهد داد.';

  @override
  String get upgradeYourPlan => 'طرح خود را ارتقا دهید';

  @override
  String get youAreOnAPaidPlan => 'شما در یک طرح پولی هستید.';

  @override
  String get chatTitle => 'چت';

  @override
  String get chatMessages => 'پیام';

  @override
  String get unlimitedChatThisMonth => 'پیام‌های چت نامحدود این ماه';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used از $limit بودجه محاسباتی استفاده شده';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used از $limit پیام این ماه استفاده شده';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit استفاده شده';
  }

  @override
  String get chatLimitReachedUpgrade => 'سقف چت تمام شد. برای پیام‌های بیشتر ارتقا دهید.';

  @override
  String get chatLimitReachedTitle => 'سقف چت تمام شد';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'شما $used از $limitDisplay را در طرح $plan استفاده کرده‌اید.';
  }

  @override
  String resetsInDays(int count) {
    return 'بازنشانی در $count روز';
  }

  @override
  String resetsInHours(int count) {
    return 'بازنشانی در $count ساعت';
  }

  @override
  String get resetsSoon => 'به‌زودی بازنشانی می‌شود';

  @override
  String get upgradePlan => 'ارتقای طرح';

  @override
  String get billingMonthly => 'ماهانه';

  @override
  String get billingYearly => 'سالانه';

  @override
  String get savePercent => '~17% صرفه‌جویی';

  @override
  String get popular => 'محبوب';

  @override
  String get currentPlan => 'فعلی';

  @override
  String neoSubtitle(int count) {
    return '$count پرسش در ماه';
  }

  @override
  String operatorSubtitle(int count) {
    return '$count پرسش در ماه';
  }

  @override
  String get architectSubtitle => 'هوش مصنوعی پیشرفته — هزاران گفتگو + اتوماسیون عاملی';

  @override
  String chatUsageCost(String used, String limit) {
    return 'چت: \$$used / \$$limit مصرف‌شده این ماه';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'چت: \$$used مصرف‌شده این ماه';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'چت: $used / $limit پیام این ماه';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'چت: $used پیام این ماه';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'شما به حد ماهانه خود رسیده‌اید. برای ادامه گفتگو با Omi بدون محدودیت ارتقا دهید.';

  @override
  String get voiceResponseAudio => 'خواندن پاسخ Omi با صدای بلند';

  @override
  String get voiceResponseMode => 'پاسخ صوتی';

  @override
  String get voiceResponseModeTitle => 'چه زمانی پاسخ‌ها خوانده شوند';

  @override
  String get voiceResponseOff => 'خاموش';

  @override
  String get voiceResponseHeadphonesOnly => 'فقط هدفون';

  @override
  String get voiceResponseAlways => 'همیشه';

  @override
  String get agreeAndContinue => 'موافقم و ادامه';

  @override
  String get startVoiceRecording => 'شروع ضبط صدا';

  @override
  String get startCallRecording => 'شروع ضبط تماس';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'حالت صوتی';

  @override
  String get quickActionAskOmi => 'از Omi هر چیزی بپرسید';

  @override
  String get record => 'ضبط';

  @override
  String get stop => 'توقف';

  @override
  String get recordWithPhoneMic => 'ضبط با میکروفون تلفن';

  @override
  String get recordWithPhoneMicSubtitle => 'صدای اطراف خود را ضبط کنید';

  @override
  String get phoneCall => 'تماس تلفنی';

  @override
  String get phoneCallSubtitle => 'یک تماس را با رونویسی زنده ضبط کنید';

  @override
  String get searchActionItems => 'جستجوی موارد اقدام';

  @override
  String get selectActionItems => 'انتخاب چندگانه';

  @override
  String chooseExportDestination(int count) {
    return 'صادرات $count مورد به…';
  }

  @override
  String get bulkExportInProgress => 'در حال صادرات…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return '$count به $platform صادر شد';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return '$success از $total به $platform صادر شد';
  }

  @override
  String get showCompletedTasks => 'نمایش انجام‌شده‌ها';

  @override
  String get hideCompletedTasks => 'پنهان کردن انجام‌شده‌ها';

  @override
  String get selectAllTasksMenu => 'انتخاب همه';

  @override
  String get connectTaskAppToExport => 'برای صادرات، یک برنامه وظایف را در تنظیمات متصل کنید';

  @override
  String get connectAction => 'اتصال';

  @override
  String get deselectAllTasksMenu => 'لغو انتخاب همه';
}
