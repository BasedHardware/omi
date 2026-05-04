// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Belarusian (`be`).
class AppLocalizationsBe extends AppLocalizations {
  AppLocalizationsBe([String locale = 'be']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Размова';

  @override
  String get transcriptTab => 'Транскрыпцыя';

  @override
  String get actionItemsTab => 'Пункты дзеяння';

  @override
  String get deleteConversationTitle => 'Выдаліць размову?';

  @override
  String get deleteConversationMessage =>
      'Гэта таксама выдаліць звязаныя ўспаміны, задачы і аўдыёфайлы. Гэта дзеянне нельга адмяніць.';

  @override
  String get confirm => 'Пацвердзіць';

  @override
  String get cancel => 'Скасаваць';

  @override
  String get ok => 'Ладна';

  @override
  String get delete => 'Выдаліць';

  @override
  String get add => 'Дадаць';

  @override
  String get update => 'Абнавіць';

  @override
  String get save => 'Захаваць';

  @override
  String get edit => 'Рэдагаваць';

  @override
  String get close => 'Закрыць';

  @override
  String get clear => 'Ачысціць';

  @override
  String get copyTranscript => 'Скапіяваць транскрыпцыю';

  @override
  String get copySummary => 'Скапіяваць рэзюмэ';

  @override
  String get testPrompt => 'Тэставаць запыт';

  @override
  String get reprocessConversation => 'Перапрацаваць размову';

  @override
  String get deleteConversation => 'Выдаліць размову';

  @override
  String get contentCopied => 'Змесціва скапіяванае ў буфер абмену';

  @override
  String get failedToUpdateStarred => 'Не атрымалася абнавіць статус адзнакі.';

  @override
  String get conversationUrlNotShared => 'URL размовы не атрымалася даліться.';

  @override
  String get errorProcessingConversation => 'Памылка пры перапрацоўцы размовы. Спрабуйце яшчэ раз пазней.';

  @override
  String get noInternetConnection => 'Няма падключэння да інтэрнету';

  @override
  String get unableToDeleteConversation => 'Не атрымалася выдаліць размову';

  @override
  String get somethingWentWrong => 'Нешто пайшло не так! Спрабуйце яшчэ раз пазней.';

  @override
  String get copyErrorMessage => 'Скапіяваць повідомленне об памылцы';

  @override
  String get errorCopied => 'Повідомленне об памылцы скапіяванае ў буфер абмену';

  @override
  String get remaining => 'Звесткі';

  @override
  String get loading => 'Загрузка...';

  @override
  String get loadingDuration => 'Загрузка тычасалікі...';

  @override
  String secondsCount(int count) {
    return '$count секунд';
  }

  @override
  String get people => 'Людзі';

  @override
  String get addNewPerson => 'Дадаць новую асобу';

  @override
  String get editPerson => 'Рэдагаваць асобу';

  @override
  String get createPersonHint => 'Стварыце новую асобу і навучыце Omi распазнаваць яе голас!';

  @override
  String get speechProfile => 'Профіль голасу';

  @override
  String sampleNumber(int number) {
    return 'Узор $number';
  }

  @override
  String get settings => 'Параметры';

  @override
  String get language => 'Мова';

  @override
  String get selectLanguage => 'Выберыце мову';

  @override
  String get deleting => 'Выданне...';

  @override
  String get pleaseCompleteAuthentication => 'Завершыце аўтэнтыфікацыю ў браўзеры. Пасля гэтага вярніцеся ў дадатак.';

  @override
  String get failedToStartAuthentication => 'Не атрымалася пачаць аўтэнтыфікацыю';

  @override
  String get importStarted => 'Імпорт пачаўся! Вы атрымаеце ўведамленне пасля завяршэння.';

  @override
  String get failedToStartImport => 'Не атрымалася пачаць імпорт. Спрабуйце яшчэ раз.';

  @override
  String get couldNotAccessFile => 'Не атрымалася атрымаць доступ да выбранага файла';

  @override
  String get askOmi => 'Запытаць Omi';

  @override
  String get done => 'Готава';

  @override
  String get disconnected => 'Адключана';

  @override
  String get searching => 'Поіск...';

  @override
  String get connectDevice => 'Падключыць прыладу';

  @override
  String get monthlyLimitReached => 'Вы дасягнулі месячнага лімітэ.';

  @override
  String get checkUsage => 'Праверыць выкарыстанне';

  @override
  String get syncingRecordings => 'Сінхранізацыя запісаў';

  @override
  String get recordingsToSync => 'Запісы для сінхранізацыі';

  @override
  String get allCaughtUp => 'Усё адноўлена';

  @override
  String get sync => 'Сінхранізаваць';

  @override
  String get pendantUpToDate => 'Прывеска абнаўлена';

  @override
  String get allRecordingsSynced => 'Усе запісы сінхранізаваны';

  @override
  String get syncingInProgress => 'Сінхранізацыя ў прагрэсе';

  @override
  String get readyToSync => 'Готава да сінхранізацыі';

  @override
  String get tapSyncToStart => 'Націсніце \"Сінхранізаваць\", каб пачаць';

  @override
  String get pendantNotConnected => 'Прывеска не падключана. Падключыцеся для сінхранізацыі.';

  @override
  String get everythingSynced => 'Усё ўжо сінхранізавана.';

  @override
  String get recordingsNotSynced => 'У вас ёсць запісы, якія яшчэ не сінхранізаваны.';

  @override
  String get syncingBackground => 'Мы будзем сінхранізаваць вашы запісы ў фонавым рэжыме.';

  @override
  String get noConversationsYet => 'Пакі нета размоў';

  @override
  String get noStarredConversations => 'Пакі нета адзначаных размоў';

  @override
  String get starConversationHint => 'Каб адзначыць размову, адкрыйце яе і націсніце значок зоркі ў загаловку.';

  @override
  String get searchConversations => 'Поіск размоў...';

  @override
  String selectedCount(int count, Object s) {
    return '$count выбрана';
  }

  @override
  String get merge => 'Аб\'яднаць';

  @override
  String get mergeConversations => 'Аб\'яднаць размовы';

  @override
  String mergeConversationsMessage(int count) {
    return 'Гэта аб\'яднае $count размоў у адну. Усё змесціва будзе аб\'яднана і перагенеравана.';
  }

  @override
  String get mergingInBackground => 'Аб\'яднанне ў фонавым рэжыме. Гэта можа заняць хвіліну.';

  @override
  String get failedToStartMerge => 'Не атрымалася пачаць аб\'яднанне';

  @override
  String get askAnything => 'Запытайцеся чаго-небудзь';

  @override
  String get noMessagesYet => 'Пакі нета паведамленняў!\nЧаму б вам не пачаць размову?';

  @override
  String get deletingMessages => 'Выданне вашых паведамленняў з памяці Omi...';

  @override
  String get messageCopied => '✨ Паведамленне скапіяванае ў буфер абмену';

  @override
  String get cannotReportOwnMessage => 'Вы не можаце скаржыцца на вашыя паведамленні.';

  @override
  String get reportMessage => 'Скаржыцца на паведамленне';

  @override
  String get reportMessageConfirm => 'Вы ўпэўнены, што хочаце скаржыцца на гэта паведамленне?';

  @override
  String get messageReported => 'Паведамленне скаржыцца паспяхова.';

  @override
  String get thankYouFeedback => 'Дзякуй за ваш адзнагадзенне!';

  @override
  String get clearChat => 'Ачысціць чат';

  @override
  String get clearChatConfirm => 'Вы ўпэўнены, што хочаце ачысціць чат? Гэта дзеянне нельга адмяніць.';

  @override
  String get maxFilesLimit => 'Вы можаце загрузіць толькі 4 файлы адначасова';

  @override
  String get chatWithOmi => 'Чатаваць з Omi';

  @override
  String get apps => 'Дадатыі';

  @override
  String get noAppsFound => 'Дадатыі не знойдзены';

  @override
  String get tryAdjustingSearch => 'Спрабуйце адправіць поіск або фільтры';

  @override
  String get createYourOwnApp => 'Стварыце свой дадатак';

  @override
  String get buildAndShareApp => 'Стварыце і раздзеліцеся сваім дадатком';

  @override
  String get searchApps => 'Поіск дадатаў...';

  @override
  String get myApps => 'Мае дадатыі';

  @override
  String get installedApps => 'Усталяваныя дадатыі';

  @override
  String get unableToFetchApps =>
      'Не атрымалася загрузіць дадатыі :(\n\nПрацяніце вашае падключэнне да інтэрнету і спрабуйце яшчэ раз.';

  @override
  String get aboutOmi => 'Пра Omi';

  @override
  String get privacyPolicy => 'Палітыка прыватнасці';

  @override
  String get visitWebsite => 'Наведаць вебсайт';

  @override
  String get helpOrInquiries => 'Дапамога або запыты?';

  @override
  String get joinCommunity => 'Далучыцеся да грамады!';

  @override
  String get membersAndCounting => '8000+ членаў і больш.';

  @override
  String get deleteAccountTitle => 'Выдаліць рахунак';

  @override
  String get deleteAccountConfirm => 'Вы ўпэўнены, што хочаце выдаліць ваш рахунак?';

  @override
  String get cannotBeUndone => 'Гэта нельга адмяніць.';

  @override
  String get allDataErased => 'Усе вашы ўспаміны і размовы будуць безвяртана выданы.';

  @override
  String get appsDisconnected => 'Вашы дадатыі і інтэграцыі будуць адключаны адразу.';

  @override
  String get exportBeforeDelete =>
      'Вы можаце экспартаваць вашы дадзеныя да выдалення рахунка, але пасля выдалення ўспаміны нельга будзе адноўіць.';

  @override
  String get deleteAccountCheckbox =>
      'Я разумею, што выданне мага рахунка перманентна і ўсе дадзеныя, уключаючы ўспаміны і размовы, будуць страчаны і не могуць быць адноўлены.';

  @override
  String get areYouSure => 'Вы ўпэўнены?';

  @override
  String get deleteAccountFinal =>
      'Гэта дзеянне незаўратна і безвяртана выдаліць ваш рахунак і ўсе звязаныя дадзеныя. Вы ўпэўнены, што хочаце перайсці да гэтага?';

  @override
  String get deleteNow => 'Выдаліць зараз';

  @override
  String get goBack => 'Вярніцца';

  @override
  String get checkBoxToConfirm =>
      'Адзначце поле, каб пацвердзіць, што вы разумееце, што выданне вашага рахунка перманентна і незаўратна.';

  @override
  String get profile => 'Профіль';

  @override
  String get name => 'Імя';

  @override
  String get email => 'Электронная пошта';

  @override
  String get customVocabulary => 'Дап. слоўнік';

  @override
  String get identifyingOthers => 'Распазнаванне іншых';

  @override
  String get paymentMethods => 'Спосабы аплаты';

  @override
  String get conversationDisplay => 'Дысплей размовы';

  @override
  String get dataPrivacy => 'Прыватнасць дадзеных';

  @override
  String get userId => 'ID карыстальніка';

  @override
  String get notSet => 'Не ўсталявана';

  @override
  String get userIdCopied => 'ID карыстальніка скапіяваны ў буфер абмену';

  @override
  String get systemDefault => 'Па змаўчанні сістэмы';

  @override
  String get planAndUsage => 'План і выкарыстанне';

  @override
  String get offlineSync => 'Аўтаномная сінхранізацыя';

  @override
  String get deviceSettings => 'Параметры прылады';

  @override
  String get integrations => 'Інтэграцыі';

  @override
  String get feedbackBug => 'Адзнагадзенне / Памылка';

  @override
  String get helpCenter => 'Центр дапамогі';

  @override
  String get developerSettings => 'Параметры распрацоўніка';

  @override
  String get getOmiForMac => 'Атрымаць Omi для Mac';

  @override
  String get referralProgram => 'Праграма рэферальнага маркетынгу';

  @override
  String get signOut => 'Выйсці';

  @override
  String get appAndDeviceCopied => 'Дасьведамленні пра дадатак і прыладу скапіяваны';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Ваша прыватнасць, ваша кантроль';

  @override
  String get privacyIntro =>
      'У Omi мы адданы абаронцы вашай прыватнасці. Гэта старонка дазваляе вам кантраляваць, як вашы дадзеныя захоўваюцца і выкарыстоўваюцца.';

  @override
  String get learnMore => 'Даведацца больш...';

  @override
  String get dataProtectionLevel => 'Ўзровень абароны дадзеных';

  @override
  String get dataProtectionDesc =>
      'Вашы дадзеныя абаронены па змаўчанні сільным шыфраваннем. Прагледзьце ваш параметры і адносныя вариянты прыватнасці ніжэй.';

  @override
  String get appAccess => 'Доступ дадатка';

  @override
  String get appAccessDesc =>
      'Наступныя дадатыі могуць атрымаць доступ да вашых дадзеных. Націсніце на дадатак, каб кантраляваць яго дазволы.';

  @override
  String get noAppsExternalAccess => 'Ні адзін з установленых дадатаў не мае зовнішняга доступу да вашых дадзеных.';

  @override
  String get deviceName => 'Імя прылады';

  @override
  String get deviceId => 'ID прылады';

  @override
  String get firmware => 'Мікрапраграмнае забеспячэнне';

  @override
  String get sdCardSync => 'Сінхранізацыя SD карты';

  @override
  String get hardwareRevision => 'Ревізія апаратнага забеспячэння';

  @override
  String get modelNumber => 'Номар мадэлі';

  @override
  String get manufacturer => 'Вытворца';

  @override
  String get doubleTap => 'Двайны дотык';

  @override
  String get ledBrightness => 'Яркасць LED';

  @override
  String get micGain => 'Узмацненне мікрафона';

  @override
  String get disconnect => 'Адключыць';

  @override
  String get forgetDevice => 'Забыць прыладу';

  @override
  String get chargingIssues => 'Праблемы з зарадкай';

  @override
  String get disconnectDevice => 'Адключыць прыладу';

  @override
  String get unpairDevice => 'Адключыць прыладу ад пары';

  @override
  String get unpairAndForget => 'Адключыць і забыць прыладу';

  @override
  String get deviceDisconnectedMessage => 'Ваш Omi быў адключаны 😔';

  @override
  String get deviceUnpairedMessage =>
      'Прылада адключана ад пары. Перайдзіце ў Параметры > Bluetooth і забудзьцеся прыладе, каб завяршыць адключэнне ад пары.';

  @override
  String get unpairDialogTitle => 'Адключыць прыладу ад пары';

  @override
  String get unpairDialogMessage =>
      'Гэта адключыць прыладу ад пары, каб яе можна было падключыць да іншага тэлефона. Вы павінны будзеце перайсці ў Параметры > Bluetooth і забыць прыладу, каб завяршыць працэс.';

  @override
  String get deviceNotConnected => 'Прылада не падключана';

  @override
  String get connectDeviceMessage =>
      'Падключыце вашу прыладу Omi, каб атрымаць доступ\nдаа параметраў прылады і персанолізацыі';

  @override
  String get deviceInfoSection => 'Інфармацыя пра прыладу';

  @override
  String get customizationSection => 'Персаналізацыя';

  @override
  String get hardwareSection => 'Апаратнае забеспячэнне';

  @override
  String get v2Undetected => 'V2 не знойдзена';

  @override
  String get v2UndetectedMessage =>
      'Мы бачым, што ў вас ёсць V1 прылада або ваша прылада не падключана. Функцыянальнасць SD карты даступна толькі для V2 прыладаў.';

  @override
  String get endConversation => 'Завяршыць размову';

  @override
  String get pauseResume => 'Паўза / Абнавіць';

  @override
  String get starConversation => 'Адзначыць размову';

  @override
  String get doubleTapAction => 'Дзеянне двойнага дотыку';

  @override
  String get endAndProcess => 'Завяршыць і перапрацаваць размову';

  @override
  String get pauseResumeRecording => 'Паўза / Абнавіць запіс';

  @override
  String get starOngoing => 'Адзначыць тэкущую размову';

  @override
  String get off => 'Адключена';

  @override
  String get max => 'Макс';

  @override
  String get mute => 'Цьміць';

  @override
  String get quiet => 'Квітка';

  @override
  String get normal => 'Обычна';

  @override
  String get high => 'Высока';

  @override
  String get micGainDescMuted => 'Мікрафон адключаны';

  @override
  String get micGainDescLow => 'Вельмі квітка - для гучных асяродзьдзяў';

  @override
  String get micGainDescModerate => 'Квітка - для умеранага шуму';

  @override
  String get micGainDescNeutral => 'Нейтральна - збалансавана запіс';

  @override
  String get micGainDescSlightlyBoosted => 'Трохі ўзмацнена - звычайнае выкарыстанне';

  @override
  String get micGainDescBoosted => 'Узмацнена - для цішкх асяродзьдзяў';

  @override
  String get micGainDescHigh => 'Высока - для вельмі далёкіх або мяккіх голасаў';

  @override
  String get micGainDescVeryHigh => 'Вельмі высока - для вельмі цішкх крыніц';

  @override
  String get micGainDescMax => 'Максімум - выкарыстоўваць з асцярожнасцю';

  @override
  String get developerSettingsTitle => 'Параметры распрацоўніка';

  @override
  String get saving => 'Захаванне...';

  @override
  String get beta => 'БЕТА';

  @override
  String get transcription => 'Транскрыпцыя';

  @override
  String get transcriptionConfig => 'Наладзіць пастаўшчыка STT';

  @override
  String get conversationTimeout => 'Тайм-аут размовы';

  @override
  String get conversationTimeoutConfig => 'Устанавіць, калі размовы аўтаматычна завяршаюцца';

  @override
  String get importData => 'Імпартаваць дадзеныя';

  @override
  String get importDataConfig => 'Імпартаваць дадзеныя з іншых крыніц';

  @override
  String get debugDiagnostics => 'Адладка і дыягностыка';

  @override
  String get endpointUrl => 'URL канчатка';

  @override
  String get noApiKeys => 'Пакі API ключаў няма';

  @override
  String get createKeyToStart => 'Стварыце ключ, каб пачаць';

  @override
  String get createKey => 'Стварыць ключ';

  @override
  String get docs => 'Дакументацыя';

  @override
  String get yourOmiInsights => 'Вашы ўсвідомленні Omi';

  @override
  String get today => 'Сёння';

  @override
  String get thisMonth => 'Гэты месяц';

  @override
  String get thisYear => 'Гэты год';

  @override
  String get allTime => 'Ўсё час';

  @override
  String get noActivityYet => 'Пакі няма дзеяння';

  @override
  String get startConversationToSeeInsights =>
      'Пачніце размову з Omi\nкаб убачыць вашыя ўсвідомленні выкарыстання тут.';

  @override
  String get listening => 'Слуханне';

  @override
  String get listeningSubtitle => 'Усяго часу Omi актыўна слуша.';

  @override
  String get understanding => 'Разуменне';

  @override
  String get understandingSubtitle => 'Слоў разумена з вашых размоў.';

  @override
  String get providing => 'Абеспячэнне';

  @override
  String get providingSubtitle => 'Пункты дзеяння і заметкі аўтаматычна захопленыя.';

  @override
  String get remembering => 'Запамінанне';

  @override
  String get rememberingSubtitle => 'Факты і дэталі запамінаны для вас.';

  @override
  String get unlimitedPlan => 'Неабмежаваны план';

  @override
  String get managePlan => 'Кантраляваць план';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Ваш план скасуецца на $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Ваш план аднаўляецца на $date.';
  }

  @override
  String get basicPlan => 'Бясплатны план';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used з $limit хвілін выкарыстана';
  }

  @override
  String get upgrade => 'Абнавіць';

  @override
  String get upgradeToUnlimited => 'Абнавіць на неабмежаваны';

  @override
  String basicPlanDesc(int limit) {
    return 'Ваш план ўключае $limit бясплатных хвілін у месяц. Абнавіце, каб атрымаць неабмежаваны доступ.';
  }

  @override
  String get shareStatsMessage => 'Раздзеляюся мая статыстыкай Omi! (omi.me - ваш заўсёды ўключаны AI ассістэнт)';

  @override
  String get sharePeriodToday => 'Сёння, omi:';

  @override
  String get sharePeriodMonth => 'Гэты месяц, omi:';

  @override
  String get sharePeriodYear => 'Гэты год, omi:';

  @override
  String get sharePeriodAllTime => 'Да гэтага пункта, omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Слуша $minutes хвілін';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Разумеў $words слоў';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Забяспечыў $count ўсвідомленняў';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Запамінаў $count ўспаміны';
  }

  @override
  String get debugLogs => 'Лагі адладкі';

  @override
  String get debugLogsAutoDelete => 'Аўтаматычна выдаляюцца пасля 3 дзён.';

  @override
  String get debugLogsDesc => 'Дапамагае дыягнаставаць праблемы';

  @override
  String get noLogFilesFound => 'Файлы логаў не знойдзены.';

  @override
  String get omiDebugLog => 'Лог адладкі Omi';

  @override
  String get logShared => 'Лог раздзелены';

  @override
  String get selectLogFile => 'Выберыце файл логу';

  @override
  String get shareLogs => 'Раздзеліцеся логамі';

  @override
  String get debugLogCleared => 'Лог адладкі ачышчены';

  @override
  String get exportStarted => 'Экспорт пачаўся. Гэта можа заняць нешто секунд...';

  @override
  String get exportAllData => 'Экспартаваць усе дадзеныя';

  @override
  String get exportDataDesc => 'Экспартаваць размовы ў JSON файл';

  @override
  String get exportedConversations => 'Экспартаваныя размовы з Omi';

  @override
  String get exportShared => 'Экспорт раздзелены';

  @override
  String get deleteKnowledgeGraphTitle => 'Выдаліць граф ведаў?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Гэта выдаліць усе вывераныя дадзеныя графа ведаў (вузлы і звязкі). Вашы арыгінальныя ўспаміны заставаюцца бяспечныя. Граф будзе перабудаваны з часам або пры наступным запыце.';

  @override
  String get knowledgeGraphDeleted => 'Граф ведаў выдалены';

  @override
  String deleteGraphFailed(String error) {
    return 'Не атрымалася выдаліць граф: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Выдаліць граф ведаў';

  @override
  String get deleteKnowledgeGraphDesc => 'Ачысціць усе вузлы і звязкі';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP сервер';

  @override
  String get mcpServerDesc => 'Падключыце AI ассістэнтаў да вашых дадзеных';

  @override
  String get serverUrl => 'URL сервера';

  @override
  String get urlCopied => 'URL скапіяваны';

  @override
  String get apiKeyAuth => 'Аўтэнтыфікацыя API ключа';

  @override
  String get header => 'Загалавак';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID клієнта';

  @override
  String get clientSecret => 'Сакрэт клієнта';

  @override
  String get useMcpApiKey => 'Выкарыстоўваць ваш MCP API ключ';

  @override
  String get webhooks => 'Вэбкрокі';

  @override
  String get conversationEvents => 'Падзеі размовы';

  @override
  String get newConversationCreated => 'Новая размова стварена';

  @override
  String get realtimeTranscript => 'Транскрыпцыя ў рэальным часе';

  @override
  String get transcriptReceived => 'Транскрыпцыя атрымана';

  @override
  String get audioBytes => 'Байты аўдыё';

  @override
  String get audioDataReceived => 'Дадзеныя аўдыё атрыманы';

  @override
  String get intervalSeconds => 'Інтэрвал (секунды)';

  @override
  String get daySummary => 'Рэзюмэ дня';

  @override
  String get summaryGenerated => 'Рэзюмэ генераванае';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Дадаць у claude_desktop_config.json';

  @override
  String get copyConfig => 'Скапіяваць канфіг';

  @override
  String get configCopied => 'Канфіг скапіяваны ў буфер абмену';

  @override
  String get listeningMins => 'Слуханне (хвіліны)';

  @override
  String get understandingWords => 'Разуменне (словы)';

  @override
  String get insights => 'Ўсвідомленні';

  @override
  String get memories => 'Ўспаміны';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used з $limit хвіл. выкарыстана гэты месяц';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used з $limit слоў выкарыстана гэты месяц';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used з $limit ўсвідомленняў атрыманы гэты месяц';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used з $limit ўспаміны створаны гэты месяц';
  }

  @override
  String get visibility => 'Рыштатнасць';

  @override
  String get visibilitySubtitle => 'Кантраляйце, якія размовы з\'яўляюцца ў вашым спісе';

  @override
  String get showShortConversations => 'Паказаць коротка размовы';

  @override
  String get showShortConversationsDesc => 'Паказаць размовы, карацейшыя за парог';

  @override
  String get showDiscardedConversations => 'Паказаць адхіленыя размовы';

  @override
  String get showDiscardedConversationsDesc => 'Ўключыць размовы, адзначаныя як адхіленыя';

  @override
  String get shortConversationThreshold => 'Парог коротка размоў';

  @override
  String get shortConversationThresholdSubtitle =>
      'Размовы, карацейшыя за гэта, будуць схованы, хіба што ўключаны вышэй';

  @override
  String get durationThreshold => 'Парог тычаса';

  @override
  String get durationThresholdDesc => 'Сховаць размовы, карацейшыя за гэта';

  @override
  String minLabel(int count) {
    return '$count хвіл.';
  }

  @override
  String get customVocabularyTitle => 'Дапаўніты слоўнік';

  @override
  String get addWords => 'Дадаць словы';

  @override
  String get addWordsDesc => 'Імёны, тэрміны або не звычайныя словы';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Падключыць';

  @override
  String get comingSoon => 'Па-скорасцінаў';

  @override
  String get integrationsFooter => 'Падключыце вашы дадатыі, каб праглядаць дадзеныя і метрыкі ў чаце.';

  @override
  String get completeAuthInBrowser => 'Завершыце аўтэнтыфікацыю ў браўзеры. Пасля гэтага вярніцеся ў дадатак.';

  @override
  String failedToStartAuth(String appName) {
    return 'Не атрымалася пачаць аўтэнтыфікацыю $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Адключыць $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Вы ўпэўнены, што хочаце адключыцца ад $appName? Вы можаце переадключыцца ў любы час.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Адключана ад $appName';
  }

  @override
  String get failedToDisconnect => 'Не атрымалася адключыцца';

  @override
  String connectTo(String appName) {
    return 'Падключыцца да $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Вам потрабіцца аўтарызаваць Omi, каб атрымаць доступ да вашых дадзеных $appName. Гэта адкрые ваш браўзер для аўтэнтыфікацыі.';
  }

  @override
  String get continueAction => 'Цягнуць';

  @override
  String get languageTitle => 'Мова';

  @override
  String get primaryLanguage => 'Первасная мова';

  @override
  String get automaticTranslation => 'Аўтаматычны пераклад';

  @override
  String get detectLanguages => 'Распазнаць 10+ моў';

  @override
  String get authorizeSavingRecordings => 'Аўтарызаваць захаванне запісаў';

  @override
  String get thanksForAuthorizing => 'Спасібо за аўтарызацыю!';

  @override
  String get needYourPermission => 'Нам трэба ваша разрешэнне';

  @override
  String get alreadyGavePermission =>
      'Вы ўжо даў нам разрешэнне захаваць вашыя голасныя запісы. Вось напоміненне, чаму нам гэта трэба:';

  @override
  String get wouldLikePermission => 'Мы хацелі б вашы разрешэнне захаваць вашыя голасныя запісы. Вось чаму:';

  @override
  String get improveSpeechProfile => 'Палепшыць ваш профіль голасу';

  @override
  String get improveSpeechProfileDesc =>
      'Мы выкарыстоўваем запісы, каб больш тренаваць і зацацаниць ваш персанальны профіль голасу.';

  @override
  String get trainFamilyProfiles => 'Тренаваць профілі для сяброў і сямей';

  @override
  String get trainFamilyProfilesDesc =>
      'Вашы запісы дапамаглі нам распазнаваць і стварыць профілі для вашых сяброў і сямей.';

  @override
  String get enhanceTranscriptAccuracy => 'Палепшыць дакладнасць транскрыпцыі';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Па меры палепшэння нашай мадэлі, мы можам забяспечыць лепшыя вынікі транскрыпцыі для вашых запісаў.';

  @override
  String get legalNotice =>
      'Юридычнае ўведамленне: Легальнасць запісу і захаванне голасных дадзеных можа варыяваць ў залежнасці ад вашага месцазнаходжання і вашага выкарыстання гэтай функцыі. Вы адказаны за захаванне адпаведнасці месцавым законам і рэгуляцыям.';

  @override
  String get alreadyAuthorized => 'Ужо аўтарызавана';

  @override
  String get authorize => 'Аўтарызаваць';

  @override
  String get revokeAuthorization => 'Адменіць аўтарызацыю';

  @override
  String get authorizationSuccessful => 'Аўтарызацыя паспяхова!';

  @override
  String get failedToAuthorize => 'Не вдалося аўтарызаваць. Спробуйце яшчэ раз.';

  @override
  String get authorizationRevoked => 'Аўтарызацыя адменена.';

  @override
  String get recordingsDeleted => 'Запісы выдалены.';

  @override
  String get failedToRevoke => 'Не вдалося адменіць аўтарызацыю. Спробуйце яшчэ раз.';

  @override
  String get permissionRevokedTitle => 'Дазвол адменены';

  @override
  String get permissionRevokedMessage => 'Хочаце, каб мы выдалілі ўсе вашы існуючыя запісы?';

  @override
  String get yes => 'Так';

  @override
  String get editName => 'Змяніць імя';

  @override
  String get howShouldOmiCallYou => 'Як Omi павінна вас называць?';

  @override
  String get enterYourName => 'Уведзіце ваше імя';

  @override
  String get nameCannotBeEmpty => 'Імя не можа быць пустым';

  @override
  String get nameUpdatedSuccessfully => 'Імя паспяхова абноўлена!';

  @override
  String get calendarSettings => 'Налады календара';

  @override
  String get calendarProviders => 'Паставальнікі календара';

  @override
  String get macOsCalendar => 'Календар macOS';

  @override
  String get connectMacOsCalendar => 'Падключыце ваш лакальны календар macOS';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Сінхранізуйце з вашым ўліком Google';

  @override
  String get showMeetingsMenuBar => 'Паказваць прадстаящыя сустрэчы ў строцы меню';

  @override
  String get showMeetingsMenuBarDesc => 'Паказваць вашу наступную сустрэчу і час да яе пачатку ў строцы меню macOS';

  @override
  String get showEventsNoParticipants => 'Паказваць палітыі без удзельнікаў';

  @override
  String get showEventsNoParticipantsDesc =>
      'Калі ўключана, Coming Up паказвае палітыі без удзельнікаў ці ссылкі на відэа.';

  @override
  String get yourMeetings => 'Ваша сустрэчы';

  @override
  String get refresh => 'Абнавіць';

  @override
  String get noUpcomingMeetings => 'Няма прадстаящых сустрэч';

  @override
  String get checkingNextDays => 'Праверка наступных 30 дзён';

  @override
  String get tomorrow => 'Завтра';

  @override
  String get googleCalendarComingSoon => 'Інтэграцыя Google Calendar скора дойдзе!';

  @override
  String connectedAsUser(String userId) {
    return 'Падключаны як карыстальнік: $userId';
  }

  @override
  String get defaultWorkspace => 'Рабочая прастора па змаўчанні';

  @override
  String get tasksCreatedInWorkspace => 'Задачы будуць створаны ў гэтай рабочай прасторы';

  @override
  String get defaultProjectOptional => 'Праект па змаўчанні (опцыёнальна)';

  @override
  String get leaveUnselectedTasks => 'Астаўце невыбранным, каб створыць задачы без праекта';

  @override
  String get noProjectsInWorkspace => 'Праектаў не знойдзена ў гэтай рабочай прасторы';

  @override
  String get conversationTimeoutDesc => 'Выберыце, як долга чакаць цішыны перад аўтаматычным завяршэннем разговора:';

  @override
  String get timeout2Minutes => '2 мінуты';

  @override
  String get timeout2MinutesDesc => 'Завяршыць разговор пасля 2 мінут цішыны';

  @override
  String get timeout5Minutes => '5 мінут';

  @override
  String get timeout5MinutesDesc => 'Завяршыць разговор пасля 5 мінут цішыны';

  @override
  String get timeout10Minutes => '10 мінут';

  @override
  String get timeout10MinutesDesc => 'Завяршыць разговор пасля 10 мінут цішыны';

  @override
  String get timeout30Minutes => '30 мінут';

  @override
  String get timeout30MinutesDesc => 'Завяршыць разговор пасля 30 мінут цішыны';

  @override
  String get timeout4Hours => '4 гадзіны';

  @override
  String get timeout4HoursDesc => 'Завяршыць разговор пасля 4 гадзін цішыны';

  @override
  String get conversationEndAfterHours => 'Разговоры зараз будуць завяршацца пасля 4 гадзін цішыны';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Разговоры будуць завяршацца пасля $minutes хвіліны(і) цішыны';
  }

  @override
  String get tellUsPrimaryLanguage => 'Скажыце нам вашу асноўную мову';

  @override
  String get languageForTranscription =>
      'Устаноўце вашу мову для больш складаных расшифровак і персаналізаванага вопыту.';

  @override
  String get singleLanguageModeInfo => 'Адзінмоўны рэжым уключаны. Пераклад адключаны для больш высокай дакладнасці.';

  @override
  String get searchLanguageHint => 'Пошук мовы па імі ці коду';

  @override
  String get noLanguagesFound => 'Мовы не знойдзены';

  @override
  String get skip => 'Прапусціць';

  @override
  String languageSetTo(String language) {
    return 'Мова ўстаноўлена на $language';
  }

  @override
  String get failedToSetLanguage => 'Не вдалося ўстаноўіць мову';

  @override
  String appSettings(String appName) {
    return 'Налады $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Адлучыцца ад $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Гэта выдаліць вашу аўтэнтыфікацыю $appName. Вам трэба перадлучыцца, каб яго выкарыстоўваць.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Падключаны да $appName';
  }

  @override
  String get account => 'Ўлік';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Ваша элементы дзеяння будуць сінхранізаваны з вашым ліком $appName';
  }

  @override
  String get defaultSpace => 'Месца па змаўчанні';

  @override
  String get selectSpaceInWorkspace => 'Выберыце месца ў вашай рабочай прасторы';

  @override
  String get noSpacesInWorkspace => 'Местаў не знойдзена ў гэтай рабочай прасторы';

  @override
  String get defaultList => 'Спіс па змаўчанні';

  @override
  String get tasksAddedToList => 'Задачы будуць даданы ў гэты спіс';

  @override
  String get noListsInSpace => 'Спісаў не знойдзена ў гэтым месцы';

  @override
  String failedToLoadRepos(String error) {
    return 'Не вдалося загрузіць сховішчы: $error';
  }

  @override
  String get defaultRepoSaved => 'Сховішча па змаўчанні захавана';

  @override
  String get failedToSaveDefaultRepo => 'Не вдалося захаваць сховішча па змаўчанні';

  @override
  String get defaultRepository => 'Сховішча па змаўчанні';

  @override
  String get selectDefaultRepoDesc =>
      'Выберыце сховішча па змаўчанні для стварэння задач. Вы ўсё адно можаце вызначыць іншае сховішча пры стварэнні задач.';

  @override
  String get noReposFound => 'Сховішча не знойдзены';

  @override
  String get private => 'Прыватны';

  @override
  String updatedDate(String date) {
    return 'Абноўлена $date';
  }

  @override
  String get yesterday => 'Учора';

  @override
  String daysAgo(int count) {
    return '$count дзён тому';
  }

  @override
  String get oneWeekAgo => '1 тыдзень тому';

  @override
  String weeksAgo(int count) {
    return '$count тыдзняў тому';
  }

  @override
  String get oneMonthAgo => '1 месяц тому';

  @override
  String monthsAgo(int count) {
    return '$count месяцаў тому';
  }

  @override
  String get issuesCreatedInRepo => 'Задачы будуць створаны ў вашым сховішчы па змаўчанні';

  @override
  String get taskIntegrations => 'Інтэграцыі задач';

  @override
  String get configureSettings => 'Канфігураваць налады';

  @override
  String get completeAuthBrowser =>
      'Калі ласка, завяршыце аўтэнтыфікацыю ў вашым браўзеры. Пасля гэтага вярніцеся ў прыкладанне.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Не вдалося пачаць аўтэнтыфікацыю $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Падключыцца да $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Вам трэба авторызаваць Omi для стварэння задач ў вашым ліку $appName. Гэта адкрые ваш браўзер для аўтэнтыфікацыі.';
  }

  @override
  String get continueButton => 'Прадоўжыць';

  @override
  String appIntegration(String appName) {
    return 'Інтэграцыя $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Інтэграцыя з $appName скора дойдзе! Мы цяжка працуем над больш опцыямі кіравання задачамі.';
  }

  @override
  String get gotIt => 'Разумею';

  @override
  String get tasksExportedOneApp => 'Задачы можна экспартаваць у адно прыкладанне адразу.';

  @override
  String get completeYourUpgrade => 'Завяршыце вашу аднаўленне';

  @override
  String get importConfiguration => 'Імпартаваць канфігурацыю';

  @override
  String get exportConfiguration => 'Экспартаваць канфігурацыю';

  @override
  String get bringYourOwn => 'Прынясіце ваше';

  @override
  String get payYourSttProvider => 'Свабодна выкарыстоўвайце omi. Вы плаціце толькі вашаму паставальніку STT прама.';

  @override
  String get freeMinutesMonth => '1200 свабодных мінут/месяц уключана. Неабмежавана з ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Хост абавязаны';

  @override
  String get validPortRequired => 'Абавязаны сапраўдны порт';

  @override
  String get validWebsocketUrlRequired => 'Абавязаны сапраўдны URL WebSocket (wss://)';

  @override
  String get apiUrlRequired => 'URL API абавязаны';

  @override
  String get apiKeyRequired => 'Ключ API абавязаны';

  @override
  String get invalidJsonConfig => 'Неправільная канфігурацыя JSON';

  @override
  String errorSaving(String error) {
    return 'Памылка пры сахраненні: $error';
  }

  @override
  String get configCopiedToClipboard => 'Канфігурацыя скапіявана ў буфер абмену';

  @override
  String get pasteJsonConfig => 'Убачыце вашу конфігурацыю JSON ніжэй:';

  @override
  String get addApiKeyAfterImport => 'Вам трэба дадаць ваш уласны ключ API пасля імпарту';

  @override
  String get paste => 'Убачыце';

  @override
  String get import => 'Імпарт';

  @override
  String get invalidProviderInConfig => 'Невалідны паставальнік у канфігурацыі';

  @override
  String importedConfig(String providerName) {
    return 'Імпартавана канфігурацыя $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'Невалідны JSON: $error';
  }

  @override
  String get provider => 'Паставальнік';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'На прыладзе';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Уведзіце ваш STT HTTP endpoint';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Уведзіце ваш live STT WebSocket endpoint';

  @override
  String get apiKey => 'Ключ API';

  @override
  String get enterApiKey => 'Уведзіце ваш ключ API';

  @override
  String get storedLocallyNeverShared => 'Захавана лакальна, ніколі не дзяліцца';

  @override
  String get host => 'Хост';

  @override
  String get port => 'Порт';

  @override
  String get advanced => 'Развінутыя';

  @override
  String get configuration => 'Канфігурацыя';

  @override
  String get requestConfiguration => 'Канфігурацыя запыту';

  @override
  String get responseSchema => 'Схема адказу';

  @override
  String get modified => 'Зменена';

  @override
  String get resetRequestConfig => 'Скінуць конфігурацыю запыту на змаўчанне';

  @override
  String get logs => 'Логі';

  @override
  String get logsCopied => 'Логі скапіяваны';

  @override
  String get noLogsYet => 'Логаў яшчэ нету. Пачніце запіс, каб убачыць дзейнасць користуемага STT.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device выкарыстоўвае $reason. Omi будзе выкарыстовуваца.';
  }

  @override
  String get omiTranscription => 'Расшыфроўка Omi';

  @override
  String get bestInClassTranscription => 'Лепшая ў сваім класе расшыфроўка без наладкі';

  @override
  String get instantSpeakerLabels => 'Імгненныя метакі дыктарай';

  @override
  String get languageTranslation => 'Пераклад более чем 100 моў';

  @override
  String get optimizedForConversation => 'Аптымізавана для разговора';

  @override
  String get autoLanguageDetection => 'Аўтаматычнае вызначэнне мовы';

  @override
  String get highAccuracy => 'Высокая дакладнасць';

  @override
  String get privacyFirst => 'Прыватнасць наперш';

  @override
  String get saveChanges => 'Захаваць змены';

  @override
  String get resetToDefault => 'Скінуць на змаўчанне';

  @override
  String get viewTemplate => 'Прагледаць шаблон';

  @override
  String get trySomethingLike => 'Спробуйце зробіць штось падобнае...';

  @override
  String get tryIt => 'Спробуйце';

  @override
  String get creatingPlan => 'Стварэнне плана';

  @override
  String get developingLogic => 'Развіццё логікі';

  @override
  String get designingApp => 'Дызайн прыкладання';

  @override
  String get generatingIconStep => 'Генерацыя значка';

  @override
  String get finalTouches => 'Канцовыя штахы';

  @override
  String get processing => 'Апрацоўка...';

  @override
  String get features => 'Функцыі';

  @override
  String get creatingYourApp => 'Стварэнне вашага прыкладання...';

  @override
  String get generatingIcon => 'Генерацыя значка...';

  @override
  String get whatShouldWeMake => 'Што мы павінны стварыць?';

  @override
  String get appName => 'Назва прыкладання';

  @override
  String get description => 'Апісанне';

  @override
  String get publicLabel => 'Публічны';

  @override
  String get privateLabel => 'Прыватны';

  @override
  String get free => 'Свабодны';

  @override
  String get perMonth => '/ Месяц';

  @override
  String get tailoredConversationSummaries => 'Прыналежныя рэзюме разговораў';

  @override
  String get customChatbotPersonality => 'Персаніфіцыраны характар чат-бота';

  @override
  String get makePublic => 'Зрабіць публічным';

  @override
  String get anyoneCanDiscover => 'Любы можа адкрыць вашае прыкладанне';

  @override
  String get onlyYouCanUse => 'Толькі вы можаце выкарыстоўваць гэтае прыкладанне';

  @override
  String get paidApp => 'Платнае прыкладанне';

  @override
  String get usersPayToUse => 'Карыстальнікі плацяць за выкарыстанне вашага прыкладання';

  @override
  String get freeForEveryone => 'Свабодна для ўсіх';

  @override
  String get perMonthLabel => '/ месяц';

  @override
  String get creating => 'Стварэнне...';

  @override
  String get createApp => 'Стварыць прыкладанне';

  @override
  String get searchingForDevices => 'Пошук прылад...';

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
  String get pairingSuccessful => 'СПАЎВАННЕ ПРАЙШЛО ПАСПЯХОВА';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Памылка пры падлучэнні да Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Не паказваць больш';

  @override
  String get iUnderstand => 'Я разумею';

  @override
  String get enableBluetooth => 'Уключыць Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi трэба Bluetooth для падлучэння да вашага нашпігальнага прыстроя. Калі ласка, уключыце Bluetooth і спробуйце яшчэ раз.';

  @override
  String get contactSupport => 'Звярнуцца ў тэхподтрымку?';

  @override
  String get connectLater => 'Падключыцца пазней';

  @override
  String get grantPermissions => 'Дайце дазволы';

  @override
  String get backgroundActivity => 'Дзейнасць у фоне';

  @override
  String get backgroundActivityDesc => 'Дайцюе Omi працаваць у фоне для лучшай стабільнасці';

  @override
  String get locationAccess => 'Доступ да месцазнаходжання';

  @override
  String get locationAccessDesc => 'Уключыце фонавое месцазнаходжанне для поўнага вопыту';

  @override
  String get notifications => 'Паведамленні';

  @override
  String get notificationsDesc => 'Уключыце паведамленні, каб быць інфармаваным';

  @override
  String get locationServiceDisabled => 'Сервіс месцазнаходжання адключаны';

  @override
  String get locationServiceDisabledDesc =>
      'Сервіс месцазнаходжання адключаны. Калі ласка, перайдзіце ў Налады > Прыватнасць і безпека > Сервісы месцазнаходжання і уключыце яго';

  @override
  String get backgroundLocationDenied => 'Доступ да фонавога месцазнаходжання адказаны';

  @override
  String get backgroundLocationDeniedDesc =>
      'Калі ласка, перайдзіце ў налады прыстроя і ўстаноўце дазвол месцазнаходжання на \"Всегда разрешить\"';

  @override
  String get lovingOmi => 'Нравіцца вам Omi?';

  @override
  String get leaveReviewIos =>
      'Дапамажыце нам дасягнуць больш людзей, пакідаючы водгук ў App Store. Ваш водгук значыць шмат для нас!';

  @override
  String get leaveReviewAndroid =>
      'Дапамажыце нам дасягнуць больш людзей, пакідаючы водгук ў Google Play Store. Ваш водгук значыць шмат для нас!';

  @override
  String get rateOnAppStore => 'Агранізавіць ў App Store';

  @override
  String get rateOnGooglePlay => 'Агранізавіць ў Google Play';

  @override
  String get maybeLater => 'Магчыма пазней';

  @override
  String get speechProfileIntro => 'Omi трэба вывучыць вашы мэты і ваш голас. Вы зможаце яго змяніць пазней.';

  @override
  String get getStarted => 'Пачаць';

  @override
  String get allDone => 'Ўсё готова!';

  @override
  String get keepGoing => 'Прадоўжайце, вы робіце адлічна';

  @override
  String get skipThisQuestion => 'Прапусціць гэта пытанне';

  @override
  String get skipForNow => 'Прапусціць на зараз';

  @override
  String get connectionError => 'Памылка злучэння';

  @override
  String get connectionErrorDesc =>
      'Не вдалося злучыцца з сервером. Калі ласка, праверыце вашу інтэрнэт-злучэнне і спробуйце яшчэ раз.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Невалідны запіс выяўлены';

  @override
  String get multipleSpeakersDesc =>
      'Здаецца, ў запісе больш адной дыктара. Калі ласка, пераканайцеся, што вы ў спакойным месцы, і спробуйце яшчэ раз.';

  @override
  String get tooShortDesc => 'Выяўлена недастаткова маў. Калі ласка, гаварыце больш і спробуйце яшчэ раз.';

  @override
  String get invalidRecordingDesc => 'Калі ласка, пераканайцеся, што вы гаварыце мінімум 5 секунд і не больш як 90.';

  @override
  String get areYouThere => 'Вы там?';

  @override
  String get noSpeechDesc =>
      'Мы не можам выявіць маў. Калі ласка, пераканайцеся, што вы гаварыце мінімум 10 секунд і не больш за 3 хвіліны.';

  @override
  String get connectionLost => 'Злучэнне страчана';

  @override
  String get connectionLostDesc =>
      'Злучэнне было перарвана. Калі ласка, праверыце вашу інтэрнэт-злучэнне і спробуйце яшчэ раз.';

  @override
  String get tryAgain => 'Спробуйце яшчэ раз';

  @override
  String get connectOmiOmiGlass => 'Падключыце Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Прадоўжыць без прыстроя';

  @override
  String get permissionsRequired => 'Дазволы абавязаны';

  @override
  String get permissionsRequiredDesc =>
      'Гэтаму прыкладанню трэба дазволы Bluetooth і месцазнаходжання для правільнай работы. Калі ласка, уключыце іх у наладах.';

  @override
  String get openSettings => 'Адкрыць налады';

  @override
  String get wantDifferentName => 'Хочаце быць вядомамі пад чым-то іншым?';

  @override
  String get whatsYourName => 'Якое вашае імя?';

  @override
  String get speakTranscribeSummarize => 'Гавярыце. Расшыфруйце. Рэзюміруйце.';

  @override
  String get signInWithApple => 'Приказаць праз Apple';

  @override
  String get signInWithGoogle => 'Приказаць праз Google';

  @override
  String get byContinuingAgree => 'Прадоўжаючы, вы памятаеце пры нашыях ';

  @override
  String get termsOfUse => 'Усім ўмовам выкарыстання';

  @override
  String get omiYourAiCompanion => 'Omi – вашы AI помочнік';

  @override
  String get captureEveryMoment => 'Захапляйце кожны момант. Атрымайце рэзюме на базе AI.\nАбыходіцеся бес запісаў.';

  @override
  String get appleWatchSetup => 'Налада Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Дазвол запрошаны!';

  @override
  String get microphonePermission => 'Дазвол мікрафона';

  @override
  String get permissionGrantedNow =>
      'Дазвол дадзены! Зараз:\n\nАдкрыйце прыкладанне Omi на вашым гадзінніку і дакніце \"Прадоўжыць\" ніжэй';

  @override
  String get needMicrophonePermission =>
      'Нам трэба дазвол мікрафона.\n\n1. Дакніце \"Дайце дазвол\"\n2. Дазвольце на вашым iPhone\n3. Прыкладанне на гадзінніку затворыцца\n4. Адкрыйце яго і дакніце \"Прадоўжыць\"';

  @override
  String get grantPermissionButton => 'Дайце дазвол';

  @override
  String get needHelp => 'Потрэбна помоч?';

  @override
  String get troubleshootingSteps =>
      'Развязанне праблем:\n\n1. Пераканайцеся, што Omi ўстаноўлена на вашым гадзінніку\n2. Адкрыйце прыкладанне Omi на вашым гадзінніку\n3. Поўкайце спливаючае акно дазвола\n4. Дакніце \"Дазволіць\" пры запыте\n5. Прыкладанне на гадзінніку затворыцца - адкрыйце яго\n6. Вярніцеся і дакніце \"Прадоўжыць\" на вашым iPhone';

  @override
  String get recordingStartedSuccessfully => 'Запіс пачаўся паспяхова!';

  @override
  String get permissionNotGrantedYet =>
      'Дазвол яшчэ не дадзены. Калі ласка, пераканайцеся, што вы дадзілі доступ мікрафона і адкрылі прыкладанне на вашым гадзінніку.';

  @override
  String errorRequestingPermission(String error) {
    return 'Памылка пры запыце дазвола: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Памылка пры пачатку запісу: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Выберыце вашу асноўную мову';

  @override
  String get languageBenefits => 'Ўстаноўце вашу мову для больш складаных расшифровак і персаналізаванага вопыту';

  @override
  String get whatsYourPrimaryLanguage => 'Якая вашая асноўная мова?';

  @override
  String get selectYourLanguage => 'Выберыце вашу мову';

  @override
  String get personalGrowthJourney => 'Ваш персаніфічны шлях росту з AI, які слухае кожнае вашае слова.';

  @override
  String get actionItemsTitle => 'Да-зроб';

  @override
  String get actionItemsDescription => 'Дакніце для редагавання • Доўгі націк для выбара • Провядзіце для дзеяння';

  @override
  String get tabToDo => 'Да зрабіць';

  @override
  String get tabDone => 'Готова';

  @override
  String get tabOld => 'Старыя';

  @override
  String get emptyTodoMessage => '🎉 Усё зроблена!\nНяма очаківаючых дзеяння';

  @override
  String get emptyDoneMessage => 'Завершаных элементаў яшчэ нету';

  @override
  String get emptyOldMessage => '✅ Няма старых задач';

  @override
  String get noItems => 'Няма элементаў';

  @override
  String get actionItemMarkedIncomplete => 'Дзеянне адзначана як незавершана';

  @override
  String get actionItemCompleted => 'Дзеянне завершана';

  @override
  String get deleteActionItemTitle => 'Выдаліць дзеянне';

  @override
  String get deleteActionItemMessage => 'Вы ўпэўнены, што хочаце выдаліць гэтае дзеянне?';

  @override
  String get deleteSelectedItemsTitle => 'Выдаліць выбраныя элементы';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Вы ўпэўнены, што хочаце выдаліць $count выбранае дзеянне$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Дзеянне \"$description\" выдалена';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count дзеянне$s выдалена';
  }

  @override
  String get failedToDeleteItem => 'Не вдалося выдаліць дзеянне';

  @override
  String get failedToDeleteItems => 'Не вдалося выдаліць элементы';

  @override
  String get failedToDeleteSomeItems => 'Не вдалося выдаліць некалькі элементаў';

  @override
  String get welcomeActionItemsTitle => 'Готовы да дзеяння';

  @override
  String get welcomeActionItemsDescription =>
      'Ваш AI аўтаматычна выцягне задачы і да-зробы з вашых разговораў. Яны будуць адлюстравацца тут пры стварэнні.';

  @override
  String get autoExtractionFeature => 'Аўтаматычна выцягнута з разговораў';

  @override
  String get editSwipeFeature => 'Дакніце для редагавання, провядзіце для завяршэння ці выдалення';

  @override
  String itemsSelected(int count) {
    return '$count выбрана';
  }

  @override
  String get selectAll => 'Выбраць ўсё';

  @override
  String get deleteSelected => 'Выдаліць выбранае';

  @override
  String get searchMemories => 'Пошук спамінаў...';

  @override
  String get memoryDeleted => 'Спамін выдалена.';

  @override
  String get undo => 'Адмяніць';

  @override
  String get noMemoriesYet => '🧠 Спамінаў яшчэ нету';

  @override
  String get noAutoMemories => 'Автоматычна выцягнутых спамінаў яшчэ нету';

  @override
  String get noManualMemories => 'Ручных спамінаў яшчэ нету';

  @override
  String get noMemoriesInCategories => 'Спамінаў у гэтых катэгорыях нету';

  @override
  String get noMemoriesFound => '🔍 Спамінаў не знойдзена';

  @override
  String get addFirstMemory => 'Дадайце ваш першы спамін';

  @override
  String get clearMemoryTitle => 'Вычысціць памяць Omi';

  @override
  String get clearMemoryMessage => 'Вы ўпэўнены, што хочаце вычысціць памяць Omi? Гэтае дзеянне нельга адмяніць.';

  @override
  String get clearMemoryButton => 'Вычысціць памяць';

  @override
  String get memoryClearedSuccess => 'Памяць Omi аб вас вычышчана';

  @override
  String get noMemoriesToDelete => 'Спамінаў для выдалення нету';

  @override
  String get createMemoryTooltip => 'Стварыць новы спамін';

  @override
  String get createActionItemTooltip => 'Стварыць новае дзеянне';

  @override
  String get memoryManagement => 'Кіраванне спамінамі';

  @override
  String get filterMemories => 'Фільтраваць спаміны';

  @override
  String totalMemoriesCount(int count) {
    return 'У вас ёсць $count всяго спамінаў';
  }

  @override
  String get publicMemories => 'Публічныя спаміны';

  @override
  String get privateMemories => 'Прыватныя спаміны';

  @override
  String get makeAllPrivate => 'Зрабіць ўсё спаміны прыватнымі';

  @override
  String get makeAllPublic => 'Зрабіць ўсё спаміны публічнымі';

  @override
  String get deleteAllMemories => 'Выдаліць ўсе спаміны';

  @override
  String get allMemoriesPrivateResult => 'Усе спаміны зараз прыватныя';

  @override
  String get allMemoriesPublicResult => 'Усе спаміны зараз публічныя';

  @override
  String get newMemory => '✨ Новы спамін';

  @override
  String get editMemory => '✏️ Редагаваць спамін';

  @override
  String get memoryContentHint => 'Мне нравіцца есці мароженае...';

  @override
  String get failedToSaveMemory => 'Не вдалося захаваць. Калі ласка, праверыце вашу злучэнне.';

  @override
  String get saveMemory => 'Захаваць спамін';

  @override
  String get retry => 'Спробаваць яшчэ раз';

  @override
  String get createActionItem => 'Стварыць дзеянне';

  @override
  String get editActionItem => 'Редагаваць дзеянне';

  @override
  String get actionItemDescriptionHint => 'Што трэба зробіць?';

  @override
  String get actionItemDescriptionEmpty => 'Апісанне дзеяння не можа быць пустым.';

  @override
  String get actionItemUpdated => 'Дзеянне абноўлена';

  @override
  String get failedToUpdateActionItem => 'Не вдалося абнавіць дзеянне';

  @override
  String get actionItemCreated => 'Дзеянне створана';

  @override
  String get failedToCreateActionItem => 'Не вдалося стварыць дзеянне';

  @override
  String get dueDate => 'Тэрмін выканання';

  @override
  String get time => 'Час';

  @override
  String get addDueDate => 'Дадаць тэрмін выканання';

  @override
  String get pressDoneToSave => 'Дакніце \"Готово\" для захаванння';

  @override
  String get pressDoneToCreate => 'Дакніце \"Готово\" для стварэння';

  @override
  String get filterAll => 'Ўсё';

  @override
  String get filterSystem => 'Аб вас';

  @override
  String get filterInteresting => 'Інсайты';

  @override
  String get filterManual => 'Ручны';

  @override
  String get completed => 'Завершана';

  @override
  String get markComplete => 'Адзначыць як завершана';

  @override
  String get actionItemDeleted => 'Дзеянне выдалена';

  @override
  String get failedToDeleteActionItem => 'Не вдалося выдаліць дзеянне';

  @override
  String get deleteActionItemConfirmTitle => 'Выдаліць дзеянне';

  @override
  String get deleteActionItemConfirmMessage => 'Вы ўпэўнены, што хочаце выдаліць гэтае дзеянне?';

  @override
  String get appLanguage => 'Мова прыкладання';

  @override
  String get appInterfaceSectionTitle => 'ІНТЭРФЕЙС ПРЫКЛАДАННЯ';

  @override
  String get speechTranscriptionSectionTitle => 'МОВ І РАСШЫФРОЎКА';

  @override
  String get languageSettingsHelperText =>
      'Мова прыкладання змяняе меню і кнопкі. Мова маўлення влывае на тое, як вашы запісы расшыфроўваюцца.';

  @override
  String get translationNotice => 'Паведамленне аб перакладе';

  @override
  String get translationNoticeMessage =>
      'Omi перакладае разговоры на вашу асноўную мову. Абнавіце яе ў любы час у Наладах → Профілі.';

  @override
  String get pleaseCheckInternetConnection => 'Калі ласка, праверыце вашу інтэрнэт-злучэнне і спробуйце яшчэ раз';

  @override
  String get pleaseSelectReason => 'Калі ласка, выберыце прычыну';

  @override
  String get tellUsMoreWhatWentWrong => 'Скажыце нам больш аб тым, што пайшло не так...';

  @override
  String get selectText => 'Выбраць тэкст';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Максімум $count мэты дазволена';
  }

  @override
  String get conversationCannotBeMerged =>
      'Гэты разговор не можа быць аб\'ёдзінаны (заблакаваны ці ўжо аб\'ёдноўваецца)';

  @override
  String get pleaseEnterFolderName => 'Калі ласка, уведзіце назву папкі';

  @override
  String get failedToCreateFolder => 'Не вдалося стварыць папку';

  @override
  String get failedToUpdateFolder => 'Не вдалося абнавіць папку';

  @override
  String get folderName => 'Назва папкі';

  @override
  String get descriptionOptional => 'Апісанне (дадаткова)';

  @override
  String get failedToDeleteFolder => 'Не ўдалося выдаліць папку';

  @override
  String get editFolder => 'Рэдагаваць папку';

  @override
  String get deleteFolder => 'Выдаліць папку';

  @override
  String get transcriptCopiedToClipboard => 'Стэнаграма скапіравана ў буфер абмену';

  @override
  String get summaryCopiedToClipboard => 'Рэзюмэ скапіравана ў буфер абмену';

  @override
  String get conversationUrlCouldNotBeShared => 'URL разнамовы немагчыма паделіцца.';

  @override
  String get urlCopiedToClipboard => 'URL скапіраван ў буфер абмену';

  @override
  String get exportTranscript => 'Экспартаваць стэнаграму';

  @override
  String get exportSummary => 'Экспартаваць рэзюмэ';

  @override
  String get exportButton => 'Экспартаваць';

  @override
  String get actionItemsCopiedToClipboard => 'Пункты дзеяння скапіраваны ў буфер абмену';

  @override
  String get summarize => 'Рэзюмаваць';

  @override
  String get generateSummary => 'Ствараць рэзюмэ';

  @override
  String get conversationNotFoundOrDeleted => 'Разнамова не знайдзена або была выдалена';

  @override
  String get deleteMemory => 'Выдаліць памяць';

  @override
  String get thisActionCannotBeUndone => 'Гэта дзеянне невозможна адмяніць.';

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
  String get noMemoriesInCategory => 'У гэтай катэгорыі памятак яшчэ няма';

  @override
  String get addYourFirstMemory => 'Дадайце вашу першую памяць';

  @override
  String get firmwareDisconnectUsb => 'Адключыць USB';

  @override
  String get firmwareUsbWarning => 'Падлучэнне USB во час абнаўленняў можа пашкодзіць ваш прыбор.';

  @override
  String get firmwareBatteryAbove15 => 'Батарэя вышэй за 15%';

  @override
  String get firmwareEnsureBattery => 'Пераканайцеся, што ў вашага прыбору 15% батарэі.';

  @override
  String get firmwareStableConnection => 'Стабільнае злучэнне';

  @override
  String get firmwareConnectWifi => 'Падлучыцеся да WiFi або мабільнай сеткі.';

  @override
  String failedToStartUpdate(String error) {
    return 'Не ўдалося пачаць абнаўленне: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Перад абнаўленнем пераканайцеся:';

  @override
  String get confirmed => 'Пацверджана!';

  @override
  String get release => 'Выпуск';

  @override
  String get slideToUpdate => 'Праслізніце, каб абнавіць';

  @override
  String copiedToClipboard(String title) {
    return '$title скапіраван ў буфер абмену';
  }

  @override
  String get batteryLevel => 'Узровень батарэі';

  @override
  String get charging => 'Зарадка';

  @override
  String get productUpdate => 'Абнаўленне прадукту';

  @override
  String get offline => 'Аўтлайн';

  @override
  String get available => 'Даступна';

  @override
  String get unpairDeviceDialogTitle => 'Адлучыць прыбор';

  @override
  String get unpairDeviceDialogMessage =>
      'Гэта адлучыць прыбор, каб яго можна было падлучыць да іншага тэлефона. Вам трэба перайсці ў Параметры > Bluetooth і забыць прыбор, каб завяршыць працэс.';

  @override
  String get unpair => 'Адлучыць';

  @override
  String get unpairAndForgetDevice => 'Адлучыць і забыць прыбор';

  @override
  String get unknownDevice => 'Невядомы';

  @override
  String get unknown => 'Невядомы';

  @override
  String get productName => 'Назва прадукту';

  @override
  String get serialNumber => 'Серыйны нумар';

  @override
  String get connected => 'Падлучана';

  @override
  String get privacyPolicyTitle => 'Палітыка прыватнасці';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label скапіраван';
  }

  @override
  String get noApiKeysYet => 'Ключаў API яшчэ няма';

  @override
  String get createKeyToGetStarted => 'Стварыце ключ, каб пачаць';

  @override
  String get configureSttProvider => 'Наладзьце пастаўшчыка STT';

  @override
  String get setWhenConversationsAutoEnd => 'Установіце, калі разнамовы аўтаматычна заканчваюцца';

  @override
  String get importDataFromOtherSources => 'Імпартаваць дадзеныя з іншых крыніц';

  @override
  String get debugAndDiagnostics => 'Адладка і дыягностыка';

  @override
  String get autoDeletesAfter3Days => 'Аўтаматычна выдаляецца праз 3 дні.';

  @override
  String get helpsDiagnoseIssues => 'Дапамагае дыягнаставаць праблемы';

  @override
  String get exportStartedMessage => 'Экспартацыя пачалася. Гэта может заняць некалькі секунд...';

  @override
  String get exportConversationsToJson => 'Экспартаваць разнамовы ў JSON файл';

  @override
  String get knowledgeGraphDeletedSuccess => 'Граф ведаў паспяхова выдалены';

  @override
  String failedToDeleteGraph(String error) {
    return 'Не ўдалося выдаліць граф: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Очыстіць усе вузлы і злучэнні';

  @override
  String get addToClaudeDesktopConfig => 'Дадайце да claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Падлучыце AI асістэнтаў да вашых дадзеных';

  @override
  String get useYourMcpApiKey => 'Выкарыстоўвайце ваш MCP ключ API';

  @override
  String get realTimeTranscript => 'Стэнаграма ў рэальным часе';

  @override
  String get experimental => 'Эксперыментальна';

  @override
  String get transcriptionDiagnostics => 'Дыягностыка трансцыпцыі';

  @override
  String get detailedDiagnosticMessages => 'Дэтальныя дыягностычныя паведамленні';

  @override
  String get autoCreateSpeakers => 'Аўтаматычна ствараць дыктарыў';

  @override
  String get autoCreateWhenNameDetected => 'Аўтаматычна ствараць пры выяўленні імя';

  @override
  String get followUpQuestions => 'Наступныя пытанні';

  @override
  String get suggestQuestionsAfterConversations => 'Прапаноўваць пытанні пасля разнамоў';

  @override
  String get goalTracker => 'Трэкер цэляў';

  @override
  String get trackPersonalGoalsOnHomepage => 'Отстёгивайте свои личные цели на главной странице';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Апісанне пункту дзеяння не можа быць пусты';

  @override
  String get saved => 'Захавана';

  @override
  String get overdue => 'Праср​ван';

  @override
  String get failedToUpdateDueDate => 'Не ўдалося абнавіць дату выконання';

  @override
  String get markIncomplete => 'Пазначыць як незавершанае';

  @override
  String get editDueDate => 'Рэдагаваць дату выконання';

  @override
  String get setDueDate => 'Установіць дату выконання';

  @override
  String get clearDueDate => 'Очыстіць дату выконання';

  @override
  String get failedToClearDueDate => 'Не ўдалося очыстіць дату выконання';

  @override
  String get mondayAbbr => 'Пн';

  @override
  String get tuesdayAbbr => 'Вт';

  @override
  String get wednesdayAbbr => 'Ср';

  @override
  String get thursdayAbbr => 'Чт';

  @override
  String get fridayAbbr => 'Пт';

  @override
  String get saturdayAbbr => 'Сб';

  @override
  String get sundayAbbr => 'Вс';

  @override
  String get howDoesItWork => 'Як гэта працуе?';

  @override
  String get sdCardSyncDescription => 'Сінхронізацыя SD Card імпартуе вашыя памяткі з SD Card ў прыбор';

  @override
  String get checksForAudioFiles => 'Праверыць аўдыёфайлы на SD Card';

  @override
  String get omiSyncsAudioFiles => 'Omi затым сінхранізуе аўдыёфайлы з сервером';

  @override
  String get serverProcessesAudio => 'Сервер апрацоўвае аўдыёфайлы і ствварае памяткі';

  @override
  String get youreAllSet => 'Вы рэды!';

  @override
  String get welcomeToOmiDescription =>
      'Вітаем у Omi! Ваш AI асістэнт готаў дапамагаць вам з разнамовамі, задачамі і многім іншым.';

  @override
  String get startUsingOmi => 'Пачаць выкарыстоўваць Omi';

  @override
  String get back => 'Назад';

  @override
  String get keyboardShortcuts => 'Клавіёвыя скарачэнні';

  @override
  String get toggleControlBar => 'Пераключыць панель кіравання';

  @override
  String get pressKeys => 'Націскайце клавішы...';

  @override
  String get cmdRequired => '⌘ абавязкова';

  @override
  String get invalidKey => 'Недапусцімая клавіша';

  @override
  String get space => 'Прабел';

  @override
  String get search => 'Пошук';

  @override
  String get searchPlaceholder => 'Пошук...';

  @override
  String get untitledConversation => 'Безназванная разнамова';

  @override
  String countRemaining(String count) {
    return '$count засталося';
  }

  @override
  String get addGoal => 'Дадайце мэту';

  @override
  String get editGoal => 'Рэдагаваць мэту';

  @override
  String get icon => 'Значок';

  @override
  String get goalTitle => 'Названне мэты';

  @override
  String get current => 'Бягучы';

  @override
  String get target => 'Мэта';

  @override
  String get saveGoal => 'Захаваць';

  @override
  String get goals => 'Мэты';

  @override
  String get tapToAddGoal => 'Цукніце, каб дадаць мэту';

  @override
  String welcomeBack(String name) {
    return 'Вітаем вяртання, $name';
  }

  @override
  String get yourConversations => 'Вашыя разнамовы';

  @override
  String get reviewAndManageConversations => 'Рэвью і кіруйце вашымі перехоплены разнамовамі';

  @override
  String get startCapturingConversations =>
      'Пачніце перахоплівацьразнамовы з вашым прыбором Omi, каб яны паяўіліся здесь.';

  @override
  String get useMobileAppToCapture => 'Выкарыстоўвайце мабільны прыбор для перахоплівання аўдыё';

  @override
  String get conversationsProcessedAutomatically => 'Разнамовы апрацоўваюцца аўтаматычна';

  @override
  String get getInsightsInstantly => 'Атрымаць ўгледзінаў і рэзюмаў танічна';

  @override
  String get showAll => 'Паказаць ўсё';

  @override
  String get noTasksForToday => 'Памежаў на сёння няма.\nПапросіце Omi для дапамогаў або стварыце ручна.';

  @override
  String get dailyScore => 'ЕЖЕДНЕВНАЯ ОЦЕНКА';

  @override
  String get dailyScoreDescription => 'Оценка, чтобы помочь вам лучше\nсосредоточиться на исполнении.';

  @override
  String get searchResults => 'Вынікі пошуку';

  @override
  String get actionItems => 'Пункты дзеяння';

  @override
  String get tasksToday => 'Сёння';

  @override
  String get tasksTomorrow => 'Завтра';

  @override
  String get tasksNoDeadline => 'Без узроку';

  @override
  String get tasksLater => 'Позней';

  @override
  String get loadingTasks => 'Загрузка задач...';

  @override
  String get tasks => 'Задачы';

  @override
  String get swipeTasksToIndent => 'Прасдвінуць задачы для адступу, перацягніце паміж катэгорыямі';

  @override
  String get create => 'Ствараць';

  @override
  String get noTasksYet => 'Задач яшчэ няма';

  @override
  String get tasksFromConversationsWillAppear =>
      'Задачы з вашых разнамоў паявяцца здесь.\nЦукніце Ствараць, каб дадаць адну ручна.';

  @override
  String get monthJan => 'Сцяніч';

  @override
  String get monthFeb => 'Люты';

  @override
  String get monthMar => 'Бераз';

  @override
  String get monthApr => 'Квіт';

  @override
  String get monthMay => 'Май';

  @override
  String get monthJun => 'Чэр';

  @override
  String get monthJul => 'Ліп';

  @override
  String get monthAug => 'Жнв';

  @override
  String get monthSep => 'Вер';

  @override
  String get monthOct => 'Каст';

  @override
  String get monthNov => 'Ліст';

  @override
  String get monthDec => 'Снеж';

  @override
  String get timePM => 'ВЧ';

  @override
  String get timeAM => 'ПП';

  @override
  String get actionItemUpdatedSuccessfully => 'Пункт дзеяння паспяхово абнаўлены';

  @override
  String get actionItemCreatedSuccessfully => 'Пункт дзеяння паспяхово створаны';

  @override
  String get actionItemDeletedSuccessfully => 'Пункт дзеяння паспяхова выдалены';

  @override
  String get deleteActionItem => 'Выдаліць пункт дзеяння';

  @override
  String get deleteActionItemConfirmation =>
      'Вы ўпэўнены, што хочаце выдаліць гэты пункт дзеяння? Гэта дзеянне невозможна адмяніць.';

  @override
  String get enterActionItemDescription => 'Увядзіце апісанне пункту дзеяння...';

  @override
  String get markAsCompleted => 'Пазначыць як завершанае';

  @override
  String get setDueDateAndTime => 'Установіць дату і час выконання';

  @override
  String get reloadingApps => 'Перагрузка прыбордаў...';

  @override
  String get loadingApps => 'Загрузка прыбордаў...';

  @override
  String get browseInstallCreateApps => 'Праглядайце, ўстанаўлівайце і стварайце прыбордаў';

  @override
  String get all => 'Усё';

  @override
  String get open => 'Адкрыць';

  @override
  String get install => 'Ўстанавіць';

  @override
  String get noAppsAvailable => 'Прыбордаў недаступна';

  @override
  String get unableToLoadApps => 'Немагчыма загрузіць прыбордаў';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Паспрабуйце адзміні​цца тэрміны пошуку ці фільтры';

  @override
  String get checkBackLaterForNewApps => 'Праверыце позней для новых прыбордаў';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Будь ласка, праверыце сувязь з Інтэрнэтам і паспрабуйце зноў';

  @override
  String get createNewApp => 'Ствараць новы прыбор';

  @override
  String get buildSubmitCustomOmiApp => 'Збудуйце і падайце ваш другасны Omi прыбор';

  @override
  String get submittingYourApp => 'Адпраўка вашага прыбора...';

  @override
  String get preparingFormForYou => 'Падрыхтоўка формы для вас...';

  @override
  String get appDetails => 'Дэталі прыбора';

  @override
  String get paymentDetails => 'Дэталі плацежа';

  @override
  String get previewAndScreenshots => 'Папярэдні прагляд і скрынкі';

  @override
  String get appCapabilities => 'Магчымасці прыбора';

  @override
  String get aiPrompts => 'AI падказкі';

  @override
  String get chatPrompt => 'Чат падказка';

  @override
  String get chatPromptPlaceholder =>
      'Вы чудасны прыбор, ваша праца - адказаць на пытанні карыстальніка і заставіць яго адчуць сябе добра...';

  @override
  String get conversationPrompt => 'Падказка разнамовы';

  @override
  String get conversationPromptPlaceholder => 'Вы чудасны прыбор, вам будзе дадзена трансцыпцыя і рэзюмэ разнамовы...';

  @override
  String get notificationScopes => 'Сферы паведамленняў';

  @override
  String get appPrivacyAndTerms => 'Прыватнасць & Тэрміны прыбора';

  @override
  String get makeMyAppPublic => 'Ўчыніць мой прыбор публічным';

  @override
  String get submitAppTermsAgreement =>
      'Адпраўляючы гэты прыбор, я пагаджаюся з Тэрмінамі абслугоўвання Omi AI і Палітыкай прыватнасці';

  @override
  String get submitApp => 'Адправіць прыбор';

  @override
  String get needHelpGettingStarted => 'Вам трэба помач пачаткі?';

  @override
  String get clickHereForAppBuildingGuides => 'Цукніце здесь для даведніка па пабудове прыбордаў і дакументацыі';

  @override
  String get submitAppQuestion => 'Адправіць прыбор?';

  @override
  String get submitAppPublicDescription =>
      'Ваш прыбор будзе рэвюявацца і зрабленаў публічным. Вы можаце пачаць выкарыстоўваць яго танічна, нават падчас рэвю!';

  @override
  String get submitAppPrivateDescription =>
      'Ваш прыбор будзе рэвюявацца і зроблены даступны вам прыватна. Вы можаце пачаць выкарыстоўваць яго танічна, нават падчас рэвю!';

  @override
  String get startEarning => 'Пачніце зарабляць! 💰';

  @override
  String get connectStripeOrPayPal => 'Падключыце Stripe ці PayPal, каб атрымаць плацежы за ваш прыбор.';

  @override
  String get connectNow => 'Падключыцеся зараз';

  @override
  String get installsCount => 'Ўстаноўкі';

  @override
  String get uninstallApp => 'Удаліць прыбор';

  @override
  String get subscribe => 'Падпіс​ацца';

  @override
  String get dataAccessNotice => 'Паведамленне аб доступе да дадзеных';

  @override
  String get dataAccessWarning =>
      'Гэты прыбор будзе мець доступ да вашых дадзеных. Omi AI не адказны за тое, як вашыя дадзеныя выкарыстоўваюцца, змяняюцца ці выдаляюцца гэтым прыбором';

  @override
  String get installApp => 'Ўстанавіць прыбор';

  @override
  String get betaTesterNotice =>
      'Вы бета-тэстер гэтага прыбора. Ён яшчэ не публічны. Ён будзе публічным пасля ўхвалення.';

  @override
  String get appUnderReviewOwner => 'Ваш прыбор на рэвю і відны толькі вам. Ён будзе публічным пасля ўхвалення.';

  @override
  String get appRejectedNotice => 'Ваш прыбор быў адхінуты. Будь ласка, абнавіце дэталі прыбора і адправіце на рэвю.';

  @override
  String get setupSteps => 'Этапы ўстаноўкі';

  @override
  String get setupInstructions => 'Інструкцыі па ўстаноўцы';

  @override
  String get integrationInstructions => 'Інструкцыі па інтэграцыі';

  @override
  String get preview => 'Папярэдні прагляд';

  @override
  String get aboutTheApp => 'Аб прыборы';

  @override
  String get chatPersonality => 'Персанальнасць чата';

  @override
  String get ratingsAndReviews => 'Адзнакі & Рэвю';

  @override
  String get noRatings => 'адзнак няма';

  @override
  String ratingsCount(String count) {
    return '$count+ адзнак';
  }

  @override
  String get errorActivatingApp => 'Памылка пры ўключэнні прыбора';

  @override
  String get integrationSetupRequired => 'Калі гэта прыбор інтэграцыі, пераканайцеся, што ўстаноўка завершана.';

  @override
  String get installed => 'Ўстаноўлена';

  @override
  String get appIdLabel => 'ID прыбора';

  @override
  String get appNameLabel => 'Назва прыбора';

  @override
  String get appNamePlaceholder => 'Мой дзівосны прыбор';

  @override
  String get pleaseEnterAppName => 'Будь ласка, уведзіце назву прыбора';

  @override
  String get categoryLabel => 'Катэгорыя';

  @override
  String get selectCategory => 'Выберыце катэгорыю';

  @override
  String get descriptionLabel => 'Апісанне';

  @override
  String get appDescriptionPlaceholder =>
      'Мой дзівосны прыбор - гэта чудасны прыбор, які робіць дзівосныя рэчы. Гэта лепшы прыбор ў свеце!';

  @override
  String get pleaseProvideValidDescription => 'Будь ласка, падайце сапраўднае апісанне';

  @override
  String get appPricingLabel => 'Цаноўка прыбора';

  @override
  String get noneSelected => 'Нічога не выбрана';

  @override
  String get appIdCopiedToClipboard => 'ID прыбора скапіраван ў буфер абмену';

  @override
  String get appCategoryModalTitle => 'Катэгорыя прыбора';

  @override
  String get pricingFree => 'Бясплатна';

  @override
  String get pricingPaid => 'Платная';

  @override
  String get loadingCapabilities => 'Загрузка магчымасцей...';

  @override
  String get filterInstalled => 'Ўстаноўлена';

  @override
  String get filterMyApps => 'Мае прыбордаў';

  @override
  String get clearSelection => 'Очыстіць выбар';

  @override
  String get filterCategory => 'Катэгорыя';

  @override
  String get rating4PlusStars => '4+ зорак';

  @override
  String get rating3PlusStars => '3+ зорак';

  @override
  String get rating2PlusStars => '2+ зорак';

  @override
  String get rating1PlusStars => '1+ зорак';

  @override
  String get filterRating => 'Адзнака';

  @override
  String get filterCapabilities => 'Магчымасці';

  @override
  String get noNotificationScopesAvailable => 'Сферы паведамленняў недаступны';

  @override
  String get popularApps => 'Папулярныя прыбордаў';

  @override
  String get pleaseProvidePrompt => 'Будь ласка, адпрацуйце падказку';

  @override
  String chatWithAppName(String appName) {
    return 'Чат з $appName';
  }

  @override
  String get defaultAiAssistant => 'Стандартны AI асістэнт';

  @override
  String get readyToChat => '✨ Рэдзі чатаць!';

  @override
  String get connectionNeeded => '🌐 Злучэнне потрэбна';

  @override
  String get startConversation => 'Пачніце разнамову і дайце чарадзэйству пачаціся';

  @override
  String get checkInternetConnection => 'Будь ласка, праверыце сувязь з Інтэрнэтам';

  @override
  String get wasThisHelpful => 'Гэта было дапамогай?';

  @override
  String get thankYouForFeedback => 'Дзякуй за вашы каментары!';

  @override
  String get maxFilesUploadError => 'Вы можаце загрузіць толькі 4 файлы адначасова';

  @override
  String get attachedFiles => '📎 Прыкладзеныя файлы';

  @override
  String get takePhoto => 'Зрабіць фота';

  @override
  String get captureWithCamera => 'Захопіць камерай';

  @override
  String get selectImages => 'Выберыце іміджы';

  @override
  String get chooseFromGallery => 'Выберыце з галерэі';

  @override
  String get selectFile => 'Выберыце файл';

  @override
  String get chooseAnyFileType => 'Выберыце любы тып файла';

  @override
  String get cannotReportOwnMessages => 'Вы не можаце паведаміць аб ваших паведамленнях';

  @override
  String get messageReportedSuccessfully => '✅ Паведамленне паспяхова паведамлена';

  @override
  String get confirmReportMessage => 'Вы ўпэўнены, што хочаце паведаміць аб гэтым паведамленні?';

  @override
  String get selectChatAssistant => 'Выберыце асістэнта чата';

  @override
  String get enableMoreApps => 'Даставіць больш прыбордаў';

  @override
  String get chatCleared => 'Чат очышчаны';

  @override
  String get clearChatTitle => 'Очыстіць чат?';

  @override
  String get confirmClearChat => 'Вы ўпэўнены, што хочаце очыстіць чат? Гэта дзеянне невозможна адмяніць.';

  @override
  String get copy => 'Копіяваць';

  @override
  String get share => 'Паделіцца';

  @override
  String get report => 'Паведаміць';

  @override
  String get microphonePermissionRequired => 'Дазвол мікрафона патрэбны для рабібаць звонкаў';

  @override
  String get microphonePermissionDenied =>
      'Дазвол мікрафона адхінуты. Будь ласка, дайце дазвол у Сістэмных параметрах > Прыватнасць & Бяспека > Мікрафон.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Не ўдалося праверыць дазвол мікрафона: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Не ўдалося трансцыбаваць аўдыё';

  @override
  String get transcribing => 'Трансцыпцыя...';

  @override
  String get transcriptionFailed => 'Трансцыпцыя не ўдалася';

  @override
  String get discardedConversation => 'Адкінутая разнамова';

  @override
  String get at => 'у';

  @override
  String get from => 'з';

  @override
  String get copied => 'Скапіравана!';

  @override
  String get copyLink => 'Копіяваць спасылку';

  @override
  String get hideTranscript => 'Схаваць стэнаграму';

  @override
  String get viewTranscript => 'Паглядзіць стэнаграму';

  @override
  String get conversationDetails => 'Дэталі разнамовы';

  @override
  String get transcript => 'Стэнаграма';

  @override
  String segmentsCount(int count) {
    return '$count сегмента';
  }

  @override
  String get noTranscriptAvailable => 'Стэнаграма недаступна';

  @override
  String get noTranscriptMessage => 'Гэтая разнамова не мае стэнаграмы.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL разнамовы не мог быць сгенерыраны.';

  @override
  String get failedToGenerateConversationLink => 'Не ўдалося ствараць спасылку разнамовы';

  @override
  String get failedToGenerateShareLink => 'Не ўдалося ствараць спасылку для абмену';

  @override
  String get reloadingConversations => 'Перагрузка разнамоў...';

  @override
  String get user => 'Карыстальнік';

  @override
  String get starred => 'Пазначаны';

  @override
  String get date => 'Дата';

  @override
  String get noResultsFound => 'Вынікаў не знойдзена';

  @override
  String get tryAdjustingSearchTerms => 'Паспрабуйце адзміні​цца тэрміны пошуку';

  @override
  String get starConversationsToFindQuickly => 'Пазначьце разнамовы, каб знайсці іх хутка здесь';

  @override
  String noConversationsOnDate(String date) {
    return 'Разнамоў на $date няма';
  }

  @override
  String get trySelectingDifferentDate => 'Паспрабуйце выбраць іншую дату';

  @override
  String get conversations => 'Разнамовы';

  @override
  String get chat => 'Чат';

  @override
  String get actions => 'Дзеянні';

  @override
  String get syncAvailable => 'Сінхронізацыя даступна';

  @override
  String get referAFriend => 'Рэкамендаваць прыяцеля';

  @override
  String get help => 'Дапамога';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Абнавіць да Pro';

  @override
  String get getOmiDevice => 'Атрымаць прыбор Omi';

  @override
  String get wearableAiCompanion => 'Надзеваны AI асістэнт';

  @override
  String get loadingMemories => 'Загрузка памятак...';

  @override
  String get allMemories => 'Усе памяткі';

  @override
  String get aboutYou => 'Аб вас';

  @override
  String get manual => 'Ручны';

  @override
  String get loadingYourMemories => 'Загрузка вашых памятак...';

  @override
  String get createYourFirstMemory => 'Ствварыце вашу першую памяць, каб пачаць';

  @override
  String get tryAdjustingFilter => 'Паспрабуйце адзміні​цца ваш пошук ці фільтр';

  @override
  String get whatWouldYouLikeToRemember => 'Што вы хочаце памятаць?';

  @override
  String get category => 'Катэгорыя';

  @override
  String get public => 'Публічна';

  @override
  String get failedToSaveCheckConnection => 'Не ўдалося захаваць. Будь ласка, праверыце сувязь.';

  @override
  String get createMemory => 'Ствараць памяць';

  @override
  String get deleteMemoryConfirmation =>
      'Вы ўпэўнены, што хочаце выдаліць гэту памяць? Гэта дзеянне невозможна адмяніць.';

  @override
  String get makePrivate => 'Ўчыніць прыватнай';

  @override
  String get organizeAndControlMemories => 'Арганізуйце і кіруйце вашымі памяткамі';

  @override
  String get total => 'Усяго';

  @override
  String get makeAllMemoriesPrivate => 'Ўчыніць усе памяткі прыватнымі';

  @override
  String get setAllMemoriesToPrivate => 'Установіць усе памяткі на прыватны доступ';

  @override
  String get makeAllMemoriesPublic => 'Ўчыніць усе памяткі публічнымі';

  @override
  String get setAllMemoriesToPublic => 'Установіць усе памяткі на публічны доступ';

  @override
  String get permanentlyRemoveAllMemories => 'Назаўсёды выдаліць усе памяткі з Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Усе памяткі цяпер прыватныя';

  @override
  String get allMemoriesAreNowPublic => 'Усе памяткі цяпер публічныя';

  @override
  String get clearOmisMemory => 'Очыстіць памяць Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Вы ўпэўнены, што хочаце очыстіць памяць Omi? Гэта дзеянне невозможна адмяніць і назаўсёды выдаліць усе $count памяткі.';
  }

  @override
  String get omisMemoryCleared => 'Памяць Omi аб вас была очышчана';

  @override
  String get welcomeToOmi => 'Вітаем у Omi';

  @override
  String get continueWithApple => 'Прадоўжыць з Apple';

  @override
  String get continueWithGoogle => 'Продолжыць з Google';

  @override
  String get byContinuingYouAgree => 'Продолжаючы, вы пагаджаецеся з нашымі ';

  @override
  String get termsOfService => 'Умовамі абслугоўвання';

  @override
  String get and => ' і ';

  @override
  String get dataAndPrivacy => 'Даннымі і Прыватнасцю';

  @override
  String get secureAuthViaAppleId => 'Бяспечная аўтэнтыфікацыя праз Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Бяспечная аўтэнтыфікацыя праз акаўнт Google';

  @override
  String get whatWeCollect => 'Што мы збіраем';

  @override
  String get dataCollectionMessage =>
      'Продолжаючы, вашы размовы, запісы і персаналь­ная інфармацыя будуць бяспечна захоўваны на нашых серверах для прадастаўлення выснаваў на базе ШІ і ўключэння ўсіх функцый прыкладання.';

  @override
  String get dataProtection => 'Абарона даных';

  @override
  String get yourDataIsProtected => 'Вашы даныя абаронены і кіруюцца нашай ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Пажалуйста, выберыце вашу асноўную мову';

  @override
  String get chooseYourLanguage => 'Выберыце вашу мову';

  @override
  String get selectPreferredLanguageForBestExperience => 'Выберыце вашу аддаленую мову для лепшага вопыту Omi';

  @override
  String get searchLanguages => 'Шукаць мовы...';

  @override
  String get selectALanguage => 'Выберыце мову';

  @override
  String get tryDifferentSearchTerm => 'Спрабуйце іншы тэрмін пошуку';

  @override
  String get pleaseEnterYourName => 'Пажалуйста, увядзіце ваше імя';

  @override
  String get nameMustBeAtLeast2Characters => 'Імя павінна быць не менш за 2 сімвалы';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Скажыце нам, як вас завяць. Гэта дапамагае персаналізаваць ваш вопыт Omi.';

  @override
  String charactersCount(int count) {
    return '$count сімвалаў';
  }

  @override
  String get enableFeaturesForBestExperience => 'Ўключыце функцыі для лепшага вопыту Omi на вашым прыладзе.';

  @override
  String get microphoneAccess => 'Доступ да мікрофона';

  @override
  String get recordAudioConversations => 'Запісваць аўдыёразмовы';

  @override
  String get microphoneAccessDescription =>
      'Omi патрабуе доступ да мікрофона для запісу вашых размаў і прадастаўлення транскрыпцый.';

  @override
  String get screenRecording => 'Запіс экрана';

  @override
  String get captureSystemAudioFromMeetings => 'Захопіць сістэмны аўдыё з сустрэч';

  @override
  String get screenRecordingDescription =>
      'Omi патрабуе дазвол на запіс экрана для захопу сістэмнага аўдыё з вашых веб-сустрэч.';

  @override
  String get accessibility => 'Доступнасць';

  @override
  String get detectBrowserBasedMeetings => 'Выявіць веб-сустрэчы';

  @override
  String get accessibilityDescription =>
      'Omi патрабуе дазвол на доступнасць для выявлення, калі вы ўдзельнічаеце ў сустрэчах Zoom, Meet або Teams у вашым браўзеры.';

  @override
  String get pleaseWait => 'Пачакайце...';

  @override
  String get joinTheCommunity => 'Приєднайцеся да суполкі!';

  @override
  String get loadingProfile => 'Загрузка профіля...';

  @override
  String get profileSettings => 'Параметры профіля';

  @override
  String get noEmailSet => 'Email не ўстаноўлен';

  @override
  String get userIdCopiedToClipboard => 'ID карыстальніка скапіяван у буфер абмену';

  @override
  String get yourInformation => 'Ваша інфармацыя';

  @override
  String get setYourName => 'Ўстаноўце ваше імя';

  @override
  String get changeYourName => 'Змяніце ваше імя';

  @override
  String get voiceAndPeople => 'Голас і людзі';

  @override
  String get teachOmiYourVoice => 'Навучыце Omi вашему голасу';

  @override
  String get tellOmiWhoSaidIt => 'Скажыце Omi, хто гэта сказаў 🗣️';

  @override
  String get payment => 'Плата';

  @override
  String get addOrChangeYourPaymentMethod => 'Дадайце або змяніце спосаб платы';

  @override
  String get preferences => 'Адпавіды';

  @override
  String get helpImproveOmiBySharing => 'Дапамажыце палепшыць Omi, дзяліўшыся анонімнымі дадзенымі аналітыкі';

  @override
  String get deleteAccount => 'Выдаліць акаўнт';

  @override
  String get deleteYourAccountAndAllData => 'Выдаліце ваш акаўнт і ўсе даныя';

  @override
  String get clearLogs => 'Очысціць журналы';

  @override
  String get debugLogsCleared => 'Журналы адладкі очышчаны';

  @override
  String get exportConversations => 'Экспартаваць размовы';

  @override
  String get exportAllConversationsToJson => 'Экспартуйце ўсе вашы размовы ў JSON файл.';

  @override
  String get conversationsExportStarted => 'Экспарт размаў пачаўся. Гэта можа заняць некалькі секунд, пачакайце.';

  @override
  String get mcpDescription =>
      'Для злучэння Omi з іншымі прыкладаннямі для чытання, пошуку і кіравання вашымі спогадамі і размовамі. Создайте ключ для пачатку.';

  @override
  String get apiKeys => 'API ключы';

  @override
  String errorLabel(String error) {
    return 'Памылка: $error';
  }

  @override
  String get noApiKeysFound => 'API ключы не знойдзены. Создайте адзін для пачатку.';

  @override
  String get advancedSettings => 'Адвансаваныя параметры';

  @override
  String get triggersWhenNewConversationCreated => 'Спрацёўвае, калі створана новая размова.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Спрацёўвае, калі атрыманая новая транскрыпцыя.';

  @override
  String get realtimeAudioBytes => 'Байты аўдыё ў рэальным часе';

  @override
  String get triggersWhenAudioBytesReceived => 'Спрацёўвае, калі атрыманы байты аўдыё.';

  @override
  String get everyXSeconds => 'Кожныя х секунд';

  @override
  String get triggersWhenDaySummaryGenerated => 'Спрацёўвае, калі генеруецца зводка дня.';

  @override
  String get tryLatestExperimentalFeatures => 'Спрабуйце найноўшыя эксперыментальныя функцыі ад каманды Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Статус дыягностыкі сервісу транскрыпцыі';

  @override
  String get enableDetailedDiagnosticMessages => 'Ўключыце дэталёвыя дыягностычныя паведамленні з сервісу транскрыпцыі';

  @override
  String get autoCreateAndTagNewSpeakers => 'Аўтаматычна стварыць і пазначыць новых дыктараў';

  @override
  String get automaticallyCreateNewPerson => 'Аўтаматычна стварыце новую персону, калі імя выявлена ў транскрыпцыі.';

  @override
  String get pilotFeatures => 'Пілотныя функцыі';

  @override
  String get pilotFeaturesDescription => 'Гэтыя функцыі апошнямі тэстамі, і гарантыя падтрымкі не аказана.';

  @override
  String get suggestFollowUpQuestion => 'Прапанаваць дапаўняющы пытанне';

  @override
  String get saveSettings => 'Захаваць параметры';

  @override
  String get syncingDeveloperSettings => 'Сінхранізацыя параметраў распрацоўніка...';

  @override
  String get summary => 'Зводка';

  @override
  String get auto => 'Аўта';

  @override
  String get noSummaryForApp =>
      'Зводка не даступна для гэтага прыкладання. Спрабуйце іншае прыкладанне для лепшых результатаў.';

  @override
  String get tryAnotherApp => 'Спрабуйце іншае прыкладанне';

  @override
  String generatedBy(String appName) {
    return 'Генеруецца $appName';
  }

  @override
  String get overview => 'Вобраз';

  @override
  String get otherAppResults => 'Вынікі іншых прыкладанняў';

  @override
  String get unknownApp => 'Невядомае прыкладанне';

  @override
  String get noSummaryAvailable => 'Зводка не даступна';

  @override
  String get conversationNoSummaryYet => 'Гэтая размова яшчэ не мае зводкі.';

  @override
  String get chooseSummarizationApp => 'Выберыце прыкладанне для кратчайшага выкладу';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName усталяваны як прыкладанне для кратчайшага выкладу па змаўчанні';
  }

  @override
  String get letOmiChooseAutomatically => 'Дозвольце Omi выбраць най­лепшае прыкладанне аўтаматычна';

  @override
  String get deleteConversationConfirmation =>
      'Вы сапраўды хочаце выдаліць гэтую размову? Гэта дзеянне не можна адмяніць.';

  @override
  String get conversationDeleted => 'Размова выдалена';

  @override
  String get generatingLink => 'Генеруецца спасылка...';

  @override
  String get editConversation => 'Рэдагаваць размову';

  @override
  String get conversationLinkCopiedToClipboard => 'Спасылка на размову скапіяванаў буфер абмену';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Транскрыпцыя размовы скапіяванаў буфер абмену';

  @override
  String get editConversationDialogTitle => 'Рэдагаваць размову';

  @override
  String get changeTheConversationTitle => 'Змяніце назву размовы';

  @override
  String get conversationTitle => 'Назва размовы';

  @override
  String get enterConversationTitle => 'Увядзіце назву размовы...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Назва размовы паспяхова абноўлена';

  @override
  String get failedToUpdateConversationTitle => 'Не ўдалася абнавіць назву размовы';

  @override
  String get errorUpdatingConversationTitle => 'Памылка пры абнаўленні назвы размовы';

  @override
  String get settingUp => 'Наладка...';

  @override
  String get startYourFirstRecording => 'Пачніце сваю першую запіс';

  @override
  String get preparingSystemAudioCapture => 'Падрыхтоўка захопу сістэмнага аўдыё';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Клацніце кнопку для захопу аўдыё для жывых транскрыпцый, выснаваў ШІ і аўтаматычнага захавання.';

  @override
  String get reconnecting => 'Перападключэнне...';

  @override
  String get recordingPaused => 'Запіс паўзаваны';

  @override
  String get recordingActive => 'Запіс актыўны';

  @override
  String get startRecording => 'Пачаць запіс';

  @override
  String resumingInCountdown(String countdown) {
    return 'Възнаўленне праз $countdownс...';
  }

  @override
  String get tapPlayToResume => 'Клацніце прайграўванне для вознаўлення';

  @override
  String get listeningForAudio => 'Слуша аўдыё...';

  @override
  String get preparingAudioCapture => 'Падрыхтоўка захопу аўдыё';

  @override
  String get clickToBeginRecording => 'Клацніце для пачатку запісу';

  @override
  String get translated => 'перавязана';

  @override
  String get liveTranscript => 'Жывая транскрыпцыя';

  @override
  String segmentsSingular(String count) {
    return '$count сегмент';
  }

  @override
  String segmentsPlural(String count) {
    return '$count сегментаў';
  }

  @override
  String get startRecordingToSeeTranscript => 'Пачніце запіс, каб убачыць жывую транскрыпцыю';

  @override
  String get paused => 'Паўзаванна';

  @override
  String get initializing => 'Ініцыалізацыя...';

  @override
  String get recording => 'Запіс';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Мікрофон змяніўся. Вознаўленне праз $countdownс';
  }

  @override
  String get clickPlayToResumeOrStop => 'Клацніце прайграўванне для вознаўлення або стоп для завяршэння';

  @override
  String get settingUpSystemAudioCapture => 'Наладка захопу сістэмнага аўдыё';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Захоп аўдыё і генерацыя транскрыпцыі';

  @override
  String get clickToBeginRecordingSystemAudio => 'Клацніце для пачатку запісу сістэмнага аўдыё';

  @override
  String get you => 'Вы';

  @override
  String speakerWithId(String speakerId) {
    return 'Дыктар $speakerId';
  }

  @override
  String get translatedByOmi => 'перавязана omi';

  @override
  String get backToConversations => 'Вяртаюцца да размаў';

  @override
  String get systemAudio => 'Сістэма';

  @override
  String get mic => 'Мік';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Аўдыё вход ўстаноўлен на $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Памылка пры перамыканні аўдыёпрыстасавання: $error';
  }

  @override
  String get selectAudioInput => 'Выберыце аўдыё ўвод';

  @override
  String get loadingDevices => 'Загрузка прыстасаванняў...';

  @override
  String get settingsHeader => 'ПАРАМЕТРЫ';

  @override
  String get plansAndBilling => 'Планы і біллінг';

  @override
  String get calendarIntegration => 'Інтэграцыя календара';

  @override
  String get dailySummary => 'Щодзённая зводка';

  @override
  String get developer => 'Распрацоўнік';

  @override
  String get about => 'Аб нас';

  @override
  String get selectTime => 'Выберыце час';

  @override
  String get accountGroup => 'Акаўнт';

  @override
  String get signOutQuestion => 'Выйсці?';

  @override
  String get signOutConfirmation => 'Вы сапраўды хочаце выйсці?';

  @override
  String get customVocabularyHeader => 'АДВОЛЬНЫ СЛОЎНІК';

  @override
  String get addWordsDescription => 'Дадайце словы, якія Omi павінна распазнаць падчас транскрыпцыі.';

  @override
  String get enterWordsHint => 'Увядзіце словы (адокремлены коскамі)';

  @override
  String get dailySummaryHeader => 'ЩОДЗЁННАЯ ЗВОДКА';

  @override
  String get dailySummaryTitle => 'Щодзённая зводка';

  @override
  String get dailySummaryDescription =>
      'Атрымайце персаналізаваную зводку размаў вашага дня, дастаўленую як паведамленне.';

  @override
  String get deliveryTime => 'Час дастаўкі';

  @override
  String get deliveryTimeDescription => 'Когда атрымаць вашу щодзённую зводку';

  @override
  String get subscription => 'Подпіска';

  @override
  String get viewPlansAndUsage => 'Прагледзіце планы і выкарыстанне';

  @override
  String get viewPlansDescription => 'Кіруйце вашай падпіскай і глядзіце статыстыку выкарыстання';

  @override
  String get addOrChangePaymentMethod => 'Дадайце або змяніце спосаб платы';

  @override
  String get displayOptions => 'Опцыі адлюстравання';

  @override
  String get showMeetingsInMenuBar => 'Паказаць сустрэчы ў панэлі меню';

  @override
  String get displayUpcomingMeetingsDescription => 'Адлюстраваць прыходзячыя сустрэчы ў панэлі меню';

  @override
  String get showEventsWithoutParticipants => 'Паказаць падзеі без удзельніков';

  @override
  String get includePersonalEventsDescription => 'Уключыць персанальныя падзеі без удзельніков';

  @override
  String get upcomingMeetings => 'Прыходзячыя сустрэчы';

  @override
  String get checkingNext7Days => 'Праверка наступных 7 дзён';

  @override
  String get shortcuts => 'Ярлыкі';

  @override
  String get shortcutChangeInstruction => 'Клацніце на ярлык, каб змяніць яго. Клацніце Escape для скасавання.';

  @override
  String get configureSTTProvider => 'Наканфігуйце пастаўшчыка STT';

  @override
  String get setConversationEndDescription => 'Ўстаноўце, калі размовы аўтаматычна заканчваюцца';

  @override
  String get importDataDescription => 'Імпартуйце даныя з іншых крыніц';

  @override
  String get exportConversationsDescription => 'Экспартуйце размовы ў JSON';

  @override
  String get exportingConversations => 'Экспарт размаў...';

  @override
  String get clearNodesDescription => 'Очысціць ўсе вузлы і злучэнні';

  @override
  String get deleteKnowledgeGraphQuestion => 'Выдаліць граф ведаў?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Гэта выдаліць ўсе вывядзеныя даныя графа ведаў. Вашы асноўныя спогады застаюцца бяспечны.';

  @override
  String get connectOmiWithAI => 'Злучыце Omi з помацнікамі ШІ';

  @override
  String get noAPIKeys => 'Адсутнічаюць API ключы. Создайте адзін для пачатку.';

  @override
  String get autoCreateWhenDetected => 'Аўтаматычна стварыць, калі выявлена імя';

  @override
  String get trackPersonalGoals => 'Сачыць персанальныя мэты на хатняй старонцы';

  @override
  String get endpointURL => 'URL дакрайнай кропкі';

  @override
  String get links => 'Спасылкі';

  @override
  String get discordMemberCount => '8000+ членаў на Discord';

  @override
  String get userInformation => 'Інфармацыя карыстальніка';

  @override
  String get capabilities => 'Магчымасці';

  @override
  String get previewScreenshots => 'Прагледзіце здымкі экрана';

  @override
  String get holdOnPreparingForm => 'Зачакайце, мы падрыхтоўваем форму для вас';

  @override
  String get bySubmittingYouAgreeToOmi => 'Адправляючы, вы пагаджаецеся з Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Умовамі і палітыкай прыватнасці';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Дапамагае дыягнаставаць праблемы. Аўтаматычна выдаляецца праз 3 дні.';

  @override
  String get manageYourApp => 'Кіруйце вашым прыкладаннем';

  @override
  String get updatingYourApp => 'Абнаўленне вашага прыкладання';

  @override
  String get fetchingYourAppDetails => 'Атрыманне дэталяў вашага прыкладання';

  @override
  String get updateAppQuestion => 'Абнавіць прыкладанне?';

  @override
  String get updateAppConfirmation =>
      'Вы сапраўды хочаце абнавіць вашае прыкладанне? Змяненні будуць адлюстраны пасля рэцэнзіі нашай каманды.';

  @override
  String get updateApp => 'Абнавіць прыкладанне';

  @override
  String get createAndSubmitNewApp => 'Стварыце і адправце новае прыкладанне';

  @override
  String appsCount(String count) {
    return 'Прыкладанні ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Персанальныя прыкладанні ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Публічныя прыкладанні ($count)';
  }

  @override
  String get newVersionAvailable => 'Даступна новая версія 🎉';

  @override
  String get no => 'Не';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Подпіска скасована паспяхова. Она застанецца актыўнай да канца цякучага біллінгавога перыяду.';

  @override
  String get failedToCancelSubscription => 'Не ўдалася скасаваць падпіску. Спрабуйце яшчэ раз.';

  @override
  String get invalidPaymentUrl => 'Недапусцімы URL платы';

  @override
  String get permissionsAndTriggers => 'Дазволы і спрацовванні';

  @override
  String get chatFeatures => 'Функцыі чата';

  @override
  String get uninstall => 'Выдаліць';

  @override
  String get installs => 'УСТАЛЯВАННІ';

  @override
  String get priceLabel => 'ЦАНА';

  @override
  String get updatedLabel => 'АБНОЎЛЕНА';

  @override
  String get createdLabel => 'СТВОРЕНА';

  @override
  String get featuredLabel => 'АДЗНАЧЕНА';

  @override
  String get cancelSubscriptionQuestion => 'Скасаваць падпіску?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Вы сапраўды хочаце скасаваць вашу падпіску? Вы будзеце мець доступ да конца цякучага біллінгавога перыяду.';

  @override
  String get cancelSubscriptionButton => 'Скасаваць падпіску';

  @override
  String get cancelling => 'Скасаванне...';

  @override
  String get betaTesterMessage =>
      'Вы бета-тэстар гэтага прыкладання. Яно яшчэ не публічнае. Яно будзе публічным пасля адобрення.';

  @override
  String get appUnderReviewMessage =>
      'Вашае прыкладанне перагледаецца і адлюстраецца толькі вам. Яно будзе публічным пасля адобрення.';

  @override
  String get appRejectedMessage =>
      'Ваша прыкладанне адхілена. Пакалуйста, абнавіце дэталі прыкладання і адправце яго заноў для перагляду.';

  @override
  String get invalidIntegrationUrl => 'Недапусцімы URL інтэграцыі';

  @override
  String get tapToComplete => 'Клацніце для завяршэння';

  @override
  String get invalidSetupInstructionsUrl => 'Недапусцімы URL інструкцый наладкі';

  @override
  String get pushToTalk => 'Пацісніце для раговора';

  @override
  String get summaryPrompt => 'Промт зводкі';

  @override
  String get pleaseSelectARating => 'Пакалуйста, выберыце рэйтынг';

  @override
  String get reviewAddedSuccessfully => 'Рэцэнзія дадана паспяхова 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Рэцэнзія абноўлена паспяхова 🚀';

  @override
  String get failedToSubmitReview => 'Не ўдалася адправіць рэцэнзію. Спрабуйце яшчэ раз.';

  @override
  String get addYourReview => 'Дадайце вашу рэцэнзію';

  @override
  String get editYourReview => 'Рэдагуйце вашу рэцэнзію';

  @override
  String get writeAReviewOptional => 'Напішыце рэцэнзію (факультатыўна)';

  @override
  String get submitReview => 'Адправіць рэцэнзію';

  @override
  String get updateReview => 'Абнавіць рэцэнзію';

  @override
  String get yourReview => 'Ваша рэцэнзія';

  @override
  String get anonymousUser => 'Анонімны карыстальнік';

  @override
  String get issueActivatingApp => 'Была праблема пры ўключэнні гэтага прыкладання. Спрабуйце яшчэ раз.';

  @override
  String get dataAccessNoticeDescription =>
      'Гэта прыкладанне будзе мець доступ да вашых даных. Omi AI не адказвае за тое, як ваша прыкладанне выкарыстоўвае, змяняе або выдаляе вашы даныя';

  @override
  String get copyUrl => 'Скапіяваць URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Пн';

  @override
  String get weekdayTue => 'Вт';

  @override
  String get weekdayWed => 'Ср';

  @override
  String get weekdayThu => 'Чц';

  @override
  String get weekdayFri => 'Пт';

  @override
  String get weekdaySat => 'Сб';

  @override
  String get weekdaySun => 'Вс';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Інтэграцыя $serviceName скора';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Ужо экспартавана на $platform';
  }

  @override
  String get anotherPlatform => 'іншую платформу';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Пакалуйста, аўтэнтыфікуйцеся ў $serviceName у параметрах > інтэграцыях задач';
  }

  @override
  String addingToService(String serviceName) {
    return 'Дадаванне да $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Дадана да $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Не ўдалася дадаць да $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Доступ адхілены да Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Не ўдалася стварыць API ключ пастаўшчыка: $error';
  }

  @override
  String get createAKey => 'Стварыце ключ';

  @override
  String get apiKeyRevokedSuccessfully => 'API ключ адкліклен паспяхова';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Не ўдалася адкліклаць API ключ: $error';
  }

  @override
  String get omiApiKeys => 'API ключы Omi';

  @override
  String get apiKeysDescription =>
      'API ключы выкарыстоўваюцца для аўтэнтыфікацыі, калі ваша прыкладанне зносіцца з сервером OMI. Яны дазваляюць вашаму прыкладанню стварыць спогады і бяспечна атрымаць доступ да іншых сервісаў OMI.';

  @override
  String get aboutOmiApiKeys => 'Аб API ключах Omi';

  @override
  String get yourNewKey => 'Ваш новы ключ:';

  @override
  String get copyToClipboard => 'Скапіяваць у буфер абмену';

  @override
  String get pleaseCopyKeyNow => 'Пакалуйста, скапіюйце яго зараз і запішыце яго дзе-небудзь у бяспечным месцы. ';

  @override
  String get willNotSeeAgain => 'Вы не зможаце убачыць яго зноў.';

  @override
  String get revokeKey => 'Адкліклаць ключ';

  @override
  String get revokeApiKeyQuestion => 'Адкліклаць API ключ?';

  @override
  String get revokeApiKeyWarning =>
      'Гэта дзеянне не можна адмяніць. Любыя прыкладанні, якія выкарыстоўваюць гэты ключ, больш не зможуць мець доступ да API.';

  @override
  String get revoke => 'Адкліклаць';

  @override
  String get whatWouldYouLikeToCreate => 'Што вы хочаце стварыць?';

  @override
  String get createAnApp => 'Стварыце прыкладанне';

  @override
  String get createAndShareYourApp => 'Стварыце і дзяліцеся вашым прыкладаннем';

  @override
  String get itemApp => 'Прыкладанне';

  @override
  String keepItemPublic(String item) {
    return 'Захаваць $item публічным';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Зрабіць $item публічным?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Зрабіць $item персанальным?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Калі вы зробіце $item публічным, яго зможе выкарыстоўваць кожны';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Калі вы зробіце $item персанальным, яно перастане працаваць для ўсіх і будзе адлюстраны толькі вам';
  }

  @override
  String get manageApp => 'Кіруйце прыкладаннем';

  @override
  String deleteItemTitle(String item) {
    return 'Выдаліць $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Выдаліць $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Вы сапраўды хочаце выдаліць гэты $item? Гэта дзеянне не можна адмяніць.';
  }

  @override
  String get revokeKeyQuestion => 'Адкліклаць ключ?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Вы сапраўды хочаце адкліклаць ключ \"$keyName\"? Гэта дзеянне не можна адмяніць.';
  }

  @override
  String get createNewKey => 'Стварыце новы ключ';

  @override
  String get keyNameHint => 'напр., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Пакалуйста, увядзіце імя.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Не ўдалося стварыць ключ: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Не ўдалося стварыць ключ. Спрабуйце яшчэ раз.';

  @override
  String get keyCreated => 'Ключ створен';

  @override
  String get keyCreatedMessage =>
      'Ваш новы ключ створен. Пакалуйста, скапіюйце яго зараз. Вы не зможаце убачыць яго зноў.';

  @override
  String get keyWord => 'Ключ';

  @override
  String get externalAppAccess => 'Доступ зовнішняй прыкладання';

  @override
  String get externalAppAccessDescription =>
      'Наступныя ўсталяваныя прыкладанні маюць вонкавыя інтэграцыі і могуць мець доступ да вашых даных, такія як размовы і спогады.';

  @override
  String get noExternalAppsHaveAccess => 'Ніякія зовнішнія прыкладанні не маюць доступу да вашых даных.';

  @override
  String get maximumSecurityE2ee => 'Максімальная бяспека (E2EE)';

  @override
  String get e2eeDescription =>
      'Шыфраванне ад канца да канца - гэта золаты стандарт для прыватнасці. Калі ўключана, вашы даныя шыфруюцца на вашым прыладзе да адпраўкі на нашы серверы. Гэта азначае, што ніхто, нават Omi, не можа атрымаць доступ да вашага змесціва.';

  @override
  String get importantTradeoffs => 'Важныя кампраміс:';

  @override
  String get e2eeTradeoff1 => '• Некаторыя функцыі, такія як інтэграцыі зовнішніх прыкладанняў, могуць быць вывучаны.';

  @override
  String get e2eeTradeoff2 => '• Калі вы загубіце ваш пароль, вашы даныя не могуць быць аднавлены.';

  @override
  String get featureComingSoon => 'Гэта функцыя скора адойдзе!';

  @override
  String get migrationInProgressMessage =>
      'Міграцыя ў працэсе. Вы не можаце змяніць узровень абароны, пакуль яна не завершыцца.';

  @override
  String get migrationFailed => 'Міграцыя не ўдалася';

  @override
  String migratingFromTo(String source, String target) {
    return 'Міграцыя з $source на $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total аб\'ектаў';
  }

  @override
  String get secureEncryption => 'Бяспечнае шыфраванне';

  @override
  String get secureEncryptionDescription =>
      'Вашы даныя шыфруюцца з ключом, адзінкавым для вас на нашых серверах, размешчаны на Google Cloud. Гэта азначае, што ваше сыра змесціва недаступна ніхто, уключаючы персонал Omi або Google, непасрэдна з базы даных.';

  @override
  String get endToEndEncryption => 'Шыфраванне ад канца да канца';

  @override
  String get e2eeCardDescription =>
      'Ўключыце для максімальнай бяспекі, дзе толькі вы можаце мець доступ да вашых даных. Клацніце для больш дэталяў.';

  @override
  String get dataAlwaysEncrypted =>
      'Незалежна ад узроўня, вашы даныя заўсёды шыфруюцца ў спокойнаму стане і ў транзіце.';

  @override
  String get readOnlyScope => 'Толькі чытанне';

  @override
  String get fullAccessScope => 'Поўны доступ';

  @override
  String get readScope => 'Чытанне';

  @override
  String get writeScope => 'Запіс';

  @override
  String get apiKeyCreated => 'API ключ створен!';

  @override
  String get saveKeyWarning => 'Захаваць гэты ключ зараз! Вы не зможаце убачыць яго зноў.';

  @override
  String get yourApiKey => 'ВАШ API КЛЮЧ';

  @override
  String get tapToCopy => 'Клацніце для копіяванна';

  @override
  String get copyKey => 'Скапіяваць ключ';

  @override
  String get createApiKey => 'Стварыце API ключ';

  @override
  String get accessDataProgrammatically => 'Мець доступ да вашых даных праграматычна';

  @override
  String get keyNameLabel => 'НАЗВА КЛЮЧА';

  @override
  String get keyNamePlaceholder => 'напр., Мая інтэграцыя прыкладання';

  @override
  String get permissionsLabel => 'ДАЗВОЛЫ';

  @override
  String get permissionsInfoNote => 'R = Чытанне, W = Запіс. Па змаўчанні чытанне толькі, калі нічога не выбрана.';

  @override
  String get developerApi => 'Developer API';

  @override
  String get createAKeyToGetStarted => 'Стварыце ключ для пачатку';

  @override
  String errorWithMessage(String error) {
    return 'Памылка: $error';
  }

  @override
  String get omiTraining => 'Omi обучение';

  @override
  String get trainingDataProgram => 'Праграма даных навучання';

  @override
  String get getOmiUnlimitedFree =>
      'Атрымайце Omi Unlimited бясплатна, удзельнічаючы ў даных для навучання мадэляў ШІ.';

  @override
  String get trainingDataBullets =>
      '• Ваша даныя дапамагаюць палепшыць мадэлі ШІ\n• Толькі нечуллівыя даныя дзяляцца\n• Цалкам прозрыста процес';

  @override
  String get learnMoreAtOmiTraining => 'Больш дзеянняў на omi.me/training';

  @override
  String get agreeToContributeData => 'Я разумею і пагаджаюся ўнесці мае даныя для навучання ШІ';

  @override
  String get submitRequest => 'Адправіць запыт';

  @override
  String get thankYouRequestUnderReview => 'Спасібо! Ваш запыт разглядаецца. Мы повядомім вас, калі прыняты.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Ваш план застанецца актыўным да $date. Пасля гэтага вы страцяеце доступ да вашых неабмежаваных функцый. Вы сапраўды?';
  }

  @override
  String get confirmCancellation => 'Потвердзіце скасаванне';

  @override
  String get keepMyPlan => 'Захаваць мой план';

  @override
  String get subscriptionSetToCancel => 'Ваша подпіска ўстаноўлена для скасавання ў канцы перыяду.';

  @override
  String get switchedToOnDevice => 'Переключыўся на транскрыпцыю на прыладзе';

  @override
  String get couldNotSwitchToFreePlan => 'Не ўдалося переключыцца на бясплатны план. Спробуйце яшчэ раз.';

  @override
  String get couldNotLoadPlans => 'Не ўдалося загрузіць даступныя планы. Спробуйце яшчэ раз.';

  @override
  String get selectedPlanNotAvailable => 'Выбраны план недаступны. Спробуйце яшчэ раз.';

  @override
  String get upgradeToAnnualPlan => 'Абнавіць на Гадавы План';

  @override
  String get importantBillingInfo => 'Важная інфармацыя аб выстаўленні сметы:';

  @override
  String get monthlyPlanContinues => 'Ваш бягучы штомесячны план будзе працягваць да канца перыяду выстаўлення сметы';

  @override
  String get paymentMethodCharged =>
      'Ваш існуючы спосаб плацежу будзе аўтаматычна дэбетаваны, калі ваш штомесячны план скончыцца';

  @override
  String get annualSubscriptionStarts => 'Ваша 12-месячная гадавая подпіска пачнецца аўтаматычна пасля спісання';

  @override
  String get thirteenMonthsCoverage => 'Вы атрымаеце 13 месяцаў пакрыцця ў сумме (бягучы месяц + 12 месяцаў гадавай)';

  @override
  String get confirmUpgrade => 'Пацвердзіць Абнаўленне';

  @override
  String get confirmPlanChange => 'Пацвердзіць Змену Плана';

  @override
  String get confirmAndProceed => 'Пацвердзіць і Прыступіць';

  @override
  String get upgradeScheduled => 'Абнаўленне Запланавана';

  @override
  String get changePlan => 'Змяніць План';

  @override
  String get upgradeAlreadyScheduled => 'Ваша абнаўленне да гадавага плана ўжо запланавана';

  @override
  String get youAreOnUnlimitedPlan => 'Вы прыйшлі да Неабмежаванага Плана.';

  @override
  String get yourOmiUnleashed => 'Ваш Omi, далі. Прайсцяце неабмежавана для бясконцых магчымасцей.';

  @override
  String planEndedOn(String date) {
    return 'Ваш план скончыўся $date.\nПадпішыцеся яшчэ раз - вы будзеце адразу дэбетаваны за новы перыяд выстаўлення сметы.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Ваш план пастаўлены на скасаванне $date.\nПадпішыцеся яшчэ раз, каб сахаваць свае прывілеі - плата адсуцная да $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Ваш гадавы план пачнецца аўтаматычна, калі скончыцца ваш штомесячны план.';

  @override
  String planRenewsOn(String date) {
    return 'Ваш план адновіцца $date.';
  }

  @override
  String get unlimitedConversations => 'Неабмежаваныя разговоры';

  @override
  String get askOmiAnything => 'Запытайцеся у Omi ўсё аб вашым жыцці';

  @override
  String get unlockOmiInfiniteMemory => 'Разблакуйце бясконцую память Omi';

  @override
  String get youreOnAnnualPlan => 'Вы на Гадавым Плане';

  @override
  String get alreadyBestValuePlan => 'У вас ужо ёсць план з лучшым стаўленнем цаны да якасці. Змен не требуецца.';

  @override
  String get unableToLoadPlans => 'Немагчыма загрузіць планы';

  @override
  String get checkConnectionTryAgain => 'Праверце падключэнне і паспрабуйце зноў';

  @override
  String get useFreePlan => 'Выкарыстаць Бясплатны План';

  @override
  String get continueText => 'Прыступіць';

  @override
  String get resubscribe => 'Падпішыцеся яшчэ раз';

  @override
  String get couldNotOpenPaymentSettings => 'Не ўдалося адкрыць параметры плацежу. Спробуйце яшчэ раз.';

  @override
  String get managePaymentMethod => 'Кіраванне Спосабам Плацежу';

  @override
  String get cancelSubscription => 'Скасаваць Падпіску';

  @override
  String endsOnDate(String date) {
    return 'Скончыцца $date';
  }

  @override
  String get active => 'Актыўны';

  @override
  String get freePlan => 'Бясплатны План';

  @override
  String get configure => 'Канфігураваць';

  @override
  String get privacyInformation => 'Інфармацыя аб Прыватнасці';

  @override
  String get yourPrivacyMattersToUs => 'Ваша Прыватнасць Важлівая для Нас';

  @override
  String get privacyIntroText =>
      'У Omi мы вельмі цэнім вашу прыватнасць. Мы хочам быць прозрыстымі адносна дадзеных, якія мы збіраем, і як мы іх выкарыстоўваем для палепшэння нашага прадукту для вас. Вось што вам трэба ведаць:';

  @override
  String get whatWeTrack => 'Што мы адсочваем';

  @override
  String get anonymityAndPrivacy => 'Анонімнасць і Прыватнасць';

  @override
  String get optInAndOptOutOptions => 'Параметры Уключэння і Выключэння';

  @override
  String get ourCommitment => 'Наша Адзвяртанне';

  @override
  String get commitmentText =>
      'Мы зацвёрджаны выкарыстоўваць дадзеныя, якія мы збіраем, толькі для палепшэння Omi. Ваша прыватнасць і даверыгу нам вельмі важныя.';

  @override
  String get thankYouText =>
      'Дзякуем, што вы каристальнік Omi. Калі ў вас ёсць якія-либо пытанні або ўзнікаюць праблемы, не вагайцеся звяртацца да нас team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Параметры Сінхранізацыі WiFi';

  @override
  String get enterHotspotCredentials => 'Уведзіце меркаванні гарячай тачкі вашага тэлефона';

  @override
  String get wifiSyncUsesHotspot =>
      'Сінхранізацыя WiFi выкарыстоўвае ваш тэлефон як гарячую тачку. Знайдзіце імя гарячай тачкі і пароль у Параметрах > Персанальная гарячая тачка.';

  @override
  String get hotspotNameSsid => 'Імя Гарячай Тачкі (SSID)';

  @override
  String get exampleIphoneHotspot => 'напр. iPhone Hotspot';

  @override
  String get password => 'Пароль';

  @override
  String get enterHotspotPassword => 'Уведзіце пароль гарячай тачкі';

  @override
  String get saveCredentials => 'Сахаваць Меркаванні';

  @override
  String get clearCredentials => 'Очыстіць Меркаванні';

  @override
  String get pleaseEnterHotspotName => 'Калі ласка, уведзіце імя гарячай тачкі';

  @override
  String get wifiCredentialsSaved => 'Меркаванні WiFi сахаваны';

  @override
  String get wifiCredentialsCleared => 'Меркаванні WiFi очышчаны';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Рэзюмэ генеравана для $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Не ўдалося сгенерыраваць рэзюмэ. Пераканайцеся, што ў вас ёсць разговоры за той дзень.';

  @override
  String get summaryNotFound => 'Рэзюмэ не знойдзена';

  @override
  String get yourDaysJourney => 'Ваш Дзённы Паход';

  @override
  String get highlights => 'Асноўныя Пункты';

  @override
  String get unresolvedQuestions => 'Нявырашаныя Пытанні';

  @override
  String get decisions => 'Рашэнні';

  @override
  String get learnings => 'Навучанні';

  @override
  String get autoDeletesAfterThreeDays => 'Аўтаматычна удаляецца праз 3 дні.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Граф Ведаў Успешна Удалены';

  @override
  String get exportStartedMayTakeFewSeconds => 'Экспорт пачаўся. Гэта можа заняць некалькі секунд...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Гэта удаліт усе дадзеныя дэрыванага графа ведаў (вузлы і злучэнні). Ваша арыгінальная память застанецца ў безпеце. Граф будзе адбудаваны з часам або пры наступным запыце.';

  @override
  String get configureDailySummaryDigest => 'Канфігураваць ваш дзённы дайджэст элементаў дзеяння';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Атрымліваюць доступ да $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'запушчаны $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription і запушчаны $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Запушчаны $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Немаэ канфігураванага спецыфічнага доступу да дадзеных.';

  @override
  String get basicPlanDescription => '1 200 прэміум мін + неабмежавана на прыладзе';

  @override
  String get minutes => 'хвіліны';

  @override
  String get omiHas => 'Omi мае:';

  @override
  String get premiumMinutesUsed => 'Прэміум хвіліны выкарыстаны.';

  @override
  String get setupOnDevice => 'Канфігураваць на прыладзе';

  @override
  String get forUnlimitedFreeTranscription => 'для неабмежаванага бясплатнага транскрыпцыі.';

  @override
  String premiumMinsLeft(int count) {
    return '$count прэміум мін паліку.';
  }

  @override
  String get alwaysAvailable => 'заўсёды даступна.';

  @override
  String get importHistory => 'Гісторыя Імпорту';

  @override
  String get noImportsYet => 'Яшчэ няма імпортаў';

  @override
  String get selectZipFileToImport => 'Абярыце файл .zip для імпорту!';

  @override
  String get otherDevicesComingSoon => 'Іншыя прыладзі скора прыйдуць';

  @override
  String get deleteAllLimitlessConversations => 'Удаліць Усе Разговоры Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Гэта перманентна удаліт усе разговоры, імпартаваныя з Limitless. Гэта дзеяннне нельга адмяніць.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Удалены $count разговоры Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Не ўдалося удаліць разговоры';

  @override
  String get deleteImportedData => 'Удаліць Імпартаваныя Дадзеныя';

  @override
  String get statusPending => 'Чакаецца';

  @override
  String get statusProcessing => 'Апрацоўка';

  @override
  String get statusCompleted => 'Завершана';

  @override
  String get statusFailed => 'Не ўдалося';

  @override
  String nConversations(int count) {
    return '$count разговоры';
  }

  @override
  String get pleaseEnterName => 'Калі ласка, уведзіце імя';

  @override
  String get nameMustBeBetweenCharacters => 'Імя павінна быць ад 2 да 40 знаках';

  @override
  String get deleteSampleQuestion => 'Удаліць Ўзор?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Вы ўпэўнены, што хочаце удаліць ўзор $name?';
  }

  @override
  String get confirmDeletion => 'Пацвердзіць Удаленне';

  @override
  String deletePersonConfirmation(String name) {
    return 'Вы ўпэўнены, што хочаце удаліць $name? Гэта таксама выдаліт усе звязаныя ўзоры мовы.';
  }

  @override
  String get howItWorksTitle => 'Як гэта працуе?';

  @override
  String get howPeopleWorks =>
      'Як толькі чалавек створаны, вы можаце перайсці да транскрыпцыі разговора і прызначыць яму іх адпаведныя сегменты, гэта дозваліт Omi распазнаваць іх мову!';

  @override
  String get tapToDelete => 'Тапніце для удалення';

  @override
  String get newTag => 'НОВЫ';

  @override
  String get needHelpChatWithUs => 'Потрэба Дапамога? Пакідайцеся з Намі';

  @override
  String get localStorageEnabled => 'Мясцовае сховіще ўключана';

  @override
  String get localStorageDisabled => 'Мясцовае сховіще выключана';

  @override
  String failedToUpdateSettings(String error) {
    return 'Не ўдалося абнавіць параметры: $error';
  }

  @override
  String get privacyNotice => 'Адведамленне аб Прыватнасці';

  @override
  String get recordingsMayCaptureOthers =>
      'Запісы могуць захопіць голасы іншых. Пераканайцеся, што вы маеце согласія ў усіх удзельнікаў перад уключэннем.';

  @override
  String get enable => 'Уключыць';

  @override
  String get storeAudioOnPhone => 'Захоўваць Аўдыё на Тэлефоне';

  @override
  String get on => 'Ўкл.';

  @override
  String get storeAudioDescription =>
      'Сахавайце ўсе аўдыё запісы мясцова на вашым тэлефоне. Калі выключана, захавліваюцца толькі не ўдалыя загрузкі для экономіі месца на сховіщы.';

  @override
  String get enableLocalStorage => 'Уключыць Мясцовае Сховіще';

  @override
  String get cloudStorageEnabled => 'Облачнае сховіще ўключана';

  @override
  String get cloudStorageDisabled => 'Облачнае сховіще выключана';

  @override
  String get enableCloudStorage => 'Уключыць Облачнае Сховіще';

  @override
  String get storeAudioOnCloud => 'Захоўваць Аўдыё ў Облаку';

  @override
  String get cloudStorageDialogMessage =>
      'Ваша запісы ў рэжыме рэальнага часу будуць захаваны ў прыватным облачным сховіщы па мене, як вы гавараеце.';

  @override
  String get storeAudioCloudDescription =>
      'Захавайце свае запісы ў рэжыме рэальнага часу ў прыватным облачным сховіщы па мене, як вы гавараеце. Аўдыё захоплівается і безбяспечна захавліваецца ў рэжыме рэальнага часу.';

  @override
  String get downloadingFirmware => 'Загрузка Прашыўкі';

  @override
  String get installingFirmware => 'Ўстаноўка Прашыўкі';

  @override
  String get firmwareUpdateWarning => 'Не закрывайце прыладу і не выключайце прыладу. Гэта можа пакаваць вашу прыладу.';

  @override
  String get firmwareUpdated => 'Прашыўка Абнаўлена';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Калі ласка, перазагрузіце ваш $deviceName каб завяршыць абнаўленне.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Ваша прылада сучаснаяс';

  @override
  String get currentVersion => 'Бягучая Версія';

  @override
  String get latestVersion => 'Апошняя Версія';

  @override
  String get whatsNew => 'Што Новага';

  @override
  String get installUpdate => 'Ўсталяваць Абнаўленне';

  @override
  String get updateNow => 'Абнавіць Зараз';

  @override
  String get updateGuide => 'Гід Абнаўлення';

  @override
  String get checkingForUpdates => 'Праверка Абнаўленняў';

  @override
  String get checkingFirmwareVersion => 'Праверка версіі прашыўкі...';

  @override
  String get firmwareUpdate => 'Абнаўленне Прашыўкі';

  @override
  String get payments => 'Плацежы';

  @override
  String get connectPaymentMethodInfo =>
      'Прыстаўце спосаб плацежу ніжэй, каб пачаць атрымліваць выплаты за вашыя прыложэнні.';

  @override
  String get selectedPaymentMethod => 'Выбраны Спосаб Плацежу';

  @override
  String get availablePaymentMethods => 'Даступныя Спосабы Плацежу';

  @override
  String get activeStatus => 'Актыўны';

  @override
  String get connectedStatus => 'Падлучана';

  @override
  String get notConnectedStatus => 'Не Падлучана';

  @override
  String get setActive => 'Ўсталяваць Актыўным';

  @override
  String get getPaidThroughStripe => 'Атрымліваць плацежі за вашыя прыложэнні праз Stripe';

  @override
  String get monthlyPayouts => 'Штомесячныя Выплаты';

  @override
  String get monthlyPayoutsDescription =>
      'Атрымліваць штомесячныя плацежы непасрэдна на ваш рахунак, калі вы дасягнеце \$10 у заробку';

  @override
  String get secureAndReliable => 'Бяспечна і Надзейна';

  @override
  String get stripeSecureDescription => 'Stripe абясцечвае бяспечныя і сваёвыя передачы вашага даходу ад прыложэння';

  @override
  String get selectYourCountry => 'Абярыце Вашу Краіну';

  @override
  String get countrySelectionPermanent => 'Ваш выбар краіны з\'яўляецца перманентным і не можа быць змянёны позней.';

  @override
  String get byClickingConnectNow => 'Клікаючы на \"Padlučyć Zara\", вы гаджаецеся з';

  @override
  String get stripeConnectedAccountAgreement => 'Пагадай Stripe Padlučanaga Raxunku';

  @override
  String get errorConnectingToStripe => 'Ошибка падлучэння да Stripe! Калі ласка, спробуйце яшчэ раз позней.';

  @override
  String get connectingYourStripeAccount => 'Падлучэнне вашага рахунку Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Калі ласка, завяршыце працэс ўбудовання Stripe ў вашы браўзеры. Гэта старонка аўтаматычна абнавіцца пасля завяршэння.';

  @override
  String get failedTryAgain => 'Не ўдалось? Спробуйце Яшчэ Раз';

  @override
  String get illDoItLater => 'Я гэта зроблю позней';

  @override
  String get successfullyConnected => 'Успешна Падлучана!';

  @override
  String get stripeReadyForPayments =>
      'Ваш рахунак Stripe цяпер гатаў атрымліваць плацежы. Вы можаце пачаць заробляць з вашых прыложэнняў адразу.';

  @override
  String get updateStripeDetails => 'Абнавіць Дадзеныя Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Ошибка абнаўлення дадзеных Stripe! Калі ласка, спробуйце яшчэ раз позней.';

  @override
  String get updatePayPal => 'Абнавіць PayPal';

  @override
  String get setUpPayPal => 'Ўсталяваць PayPal';

  @override
  String get updatePayPalAccountDetails => 'Абнавіць дадзеныя вашага рахунку PayPal';

  @override
  String get connectPayPalToReceivePayments =>
      'Прыстаўце ваш рахунак PayPal, каб пачаць атрымліваць плацежы за вашыя прыложэнні';

  @override
  String get paypalEmail => 'Электронная Пошта PayPal';

  @override
  String get paypalMeLink => 'PayPal.me Спасылка';

  @override
  String get stripeRecommendation =>
      'Калі Stripe даступна ў вашай краіне, мы вельмі рэкамендуем яе выкарыстоўваць для хутчэйшых і лягчэйшых выплат.';

  @override
  String get updatePayPalDetails => 'Абнавіць Дадзеныя PayPal';

  @override
  String get savePayPalDetails => 'Сахаваць Дадзеныя PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Калі ласка, уведзіце вашу электронную пошту PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Калі ласка, уведзіце вашу PayPal.me спасылку';

  @override
  String get doNotIncludeHttpInLink => 'Не ўключайце http ці https ці www у спасылку';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Калі ласка, уведзіце сапраўдную PayPal.me спасылку';

  @override
  String get pleaseEnterValidEmail => 'Калі ласка, уведзіце сапраўдны адрас электронны пошты';

  @override
  String get syncingYourRecordings => 'Сінхранізацыя вашых запісаў';

  @override
  String get syncYourRecordings => 'Сінхранізаваць вашы запісы';

  @override
  String get syncNow => 'Сінхранізаваць Зараз';

  @override
  String get error => 'Ошибка';

  @override
  String get speechSamples => 'Ўзоры Мовы';

  @override
  String additionalSampleIndex(String index) {
    return 'Дадатковы Ўзор $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Тривалась: $seconds секунд';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Дадатковы Ўзор Мовы Выдалены';

  @override
  String get consentDataMessage =>
      'Працягваючы, вашы размовы, запісы і асабістая інфармацыя будуць надзейна захоўвацца на нашых серверах. Вашы аўдыязапісы і транскрыпцыі апрацоўваюцца староннімі сэрвісамі ШІ (уключаючы Deepgram для транскрыпцыі і OpenAI для аналізу), каб забяспечыць вас аналітыкай на аснове ШІ і ўключыць усе функцыі праграмы.';

  @override
  String get tasksEmptyStateMessage =>
      'Задачы з вашых разговораў пояўляцца тут.\nТапніце + каб стварыць адну ручнічна.';

  @override
  String get clearChatAction => 'Очыстіць Чат';

  @override
  String get enableApps => 'Уключыць Прыложэнні';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'Паказаць больш ↓';

  @override
  String get showLess => 'Паказаць менш ↑';

  @override
  String get loadingYourRecording => 'Загрузка вашага запісу...';

  @override
  String get photoDiscardedMessage => 'Гэта фота было адкінута, так як яно не было значнае.';

  @override
  String get analyzing => 'Аналіз...';

  @override
  String get searchCountries => 'Пошук краін';

  @override
  String get checkingAppleWatch => 'Праверка Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Ўстаноўьце Omi на ваш\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Каб выкарыстоўваць ваш Apple Watch з Omi, вам трэба спачатку ўсталяваць прыложэнне Omi на вашы гадзінкі.';

  @override
  String get openOmiOnAppleWatch => 'Адкрыйце Omi на ваш\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Прыложэнне Omi ўстаноўлена на вашым Apple Watch. Адкрыйце яго і тапніце Пачаць, каб пачаць.';

  @override
  String get openWatchApp => 'Адкрыць Прыложэнне Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Я Ўсталявам і Адкрыў Прыложэнне';

  @override
  String get unableToOpenWatchApp =>
      'Не ўдалося адкрыць прыложэнне Apple Watch. Калі ласка, ручнічна адкрыйце прыложэнне Watch на вашым Apple Watch і ўсталяйце Omi з секкіі \"Даступныя Прыложэнні\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch Успешна Падлучана!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch яшчэ недаступна. Калі ласка, пераканайцеся, што прыложэнне Omi адкрыто на вашых гадзінках.';

  @override
  String errorCheckingConnection(String error) {
    return 'Ошибка праверкі падлучэння: $error';
  }

  @override
  String get muted => 'Адключана';

  @override
  String get processNow => 'Апрацаваць Зараз';

  @override
  String get finishedConversation => 'Завяршыць Разговор?';

  @override
  String get stopRecordingConfirmation => 'Вы ўпэўнены, што хочаце спыніць запіс і рэзюміраваць разговор зараз?';

  @override
  String get conversationEndsManually => 'Разговор буде скончцацца толькі ручнічна.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Разговор рэзюміруецца пасля $minutes хвіліны$suffix беж мовы.';
  }

  @override
  String get dontAskAgain => 'Не пытайцеся мне яшчэ раз';

  @override
  String get waitingForTranscriptOrPhotos => 'Чаканне на транскрыпцыю ці фота...';

  @override
  String get noSummaryYet => 'Рэзюмэ яшчэ няма';

  @override
  String hints(String text) {
    return 'Падказкі: $text';
  }

  @override
  String get testConversationPrompt => 'Тэставаць Прампт Разговора';

  @override
  String get prompt => 'Прампт';

  @override
  String get result => 'Вынік:';

  @override
  String get compareTranscripts => 'Паравнаць Транскрыпцыі';

  @override
  String get notHelpful => 'Не Карысна';

  @override
  String get exportTasksWithOneTap => 'Экспартаваць задачы адным тапам!';

  @override
  String get inProgress => 'У Працэсе';

  @override
  String get photos => 'Фота';

  @override
  String get rawData => 'Сыравільная Інфармацыя';

  @override
  String get content => 'Змест';

  @override
  String get noContentToDisplay => 'Нема зместу для адлюстравання';

  @override
  String get noSummary => 'Нема рэзюмэ';

  @override
  String get updateOmiFirmware => 'Абнавіць прашыўку omi';

  @override
  String get anErrorOccurredTryAgain => 'Здарылася ошибка. Калі ласка, спробуйце яшчэ раз.';

  @override
  String get welcomeBackSimple => 'Дабро Пажаловаць Назад';

  @override
  String get addVocabularyDescription => 'Дадайце словы, якія Omi павінен распазнаваць падчас транскрыпцыі.';

  @override
  String get enterWordsCommaSeparated => 'Уведзіце словы (падзелены коміст)';

  @override
  String get whenToReceiveDailySummary => 'Кагда атрымаць ваш дзённы рэзюмэ';

  @override
  String get checkingNextSevenDays => 'Праверка наступных 7 дзён';

  @override
  String failedToDeleteError(String error) {
    return 'Не ўдалося удаліць: $error';
  }

  @override
  String get developerApiKeys => 'Ключы API Разпрацоўніка';

  @override
  String get noApiKeysCreateOne => 'Нема ключаў API. Стварыце адзін, каб пачаць.';

  @override
  String get commandRequired => '⌘ Трэба';

  @override
  String get spaceKey => 'Прабел';

  @override
  String loadMoreRemaining(String count) {
    return 'Загрузіць Больш ($count паліку)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Топ $percentile% Карысальнік';
  }

  @override
  String get wrappedMinutes => 'хвіліны';

  @override
  String get wrappedConversations => 'разговоры';

  @override
  String get wrappedDaysActive => 'дзён актыўны';

  @override
  String get wrappedYouTalkedAbout => 'Вы Гаварыў Аб';

  @override
  String get wrappedActionItems => 'Элементы Дзеяння';

  @override
  String get wrappedTasksCreated => 'задачы створаны';

  @override
  String get wrappedCompleted => 'завершана';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% Норма Завяршэння';
  }

  @override
  String get wrappedYourTopDays => 'Ваш Топ Дзён';

  @override
  String get wrappedBestMoments => 'Лучшыя Моманты';

  @override
  String get wrappedMyBuddies => 'Мая Дружыны';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Не Магу Пакінуць Гавараць Аб';

  @override
  String get wrappedShow => 'ПАКАЗ';

  @override
  String get wrappedMovie => 'ФІЛЬМ';

  @override
  String get wrappedBook => 'КНІГА';

  @override
  String get wrappedCelebrity => 'ЗНАМЯНІТЫ';

  @override
  String get wrappedFood => 'ЕДА';

  @override
  String get wrappedMovieRecs => 'Рэкамендацыі Фільмаў для Дзяўчат';

  @override
  String get wrappedBiggest => 'Найбольш';

  @override
  String get wrappedStruggle => 'Барацьба';

  @override
  String get wrappedButYouPushedThrough => 'Але вы пушлі скозь 💪';

  @override
  String get wrappedWin => 'Перамога';

  @override
  String get wrappedYouDidIt => 'Вы гэта зробілі! 🎉';

  @override
  String get wrappedTopPhrases => 'Топ 5 Фраз';

  @override
  String get wrappedMins => 'мін';

  @override
  String get wrappedConvos => 'разгаворы';

  @override
  String get wrappedDays => 'дзён';

  @override
  String get wrappedMyBuddiesLabel => 'МА ДРУЖЫНЫ';

  @override
  String get wrappedObsessionsLabel => 'АБСЕСІІ';

  @override
  String get wrappedStruggleLabel => 'БАРАЦЬБА';

  @override
  String get wrappedWinLabel => 'ПЕРАМОГА';

  @override
  String get wrappedTopPhrasesLabel => 'ТОП ФРАЗЫ';

  @override
  String get wrappedLetsHitRewind => 'Давайце адмяніцца';

  @override
  String get wrappedGenerateMyWrapped => 'Генерыраваць Мой Wrapped';

  @override
  String get wrappedProcessingDefault => 'Апрацоўка...';

  @override
  String get wrappedCreatingYourStory => 'Стварэнне вашага\n2025 аповеда...';

  @override
  String get wrappedSomethingWentWrong => 'Што-то пайшло не так';

  @override
  String get wrappedAnErrorOccurred => 'Здарылася ошибка';

  @override
  String get wrappedTryAgain => 'Спробуйце Яшчэ Раз';

  @override
  String get wrappedNoDataAvailable => 'Нема даступных дадзеных';

  @override
  String get wrappedOmiLifeRecap => 'Omi Жыццё Резюмэ';

  @override
  String get wrappedSwipeUpToBegin => 'Пракруціце, каб пачаць';

  @override
  String get wrappedShareText => 'Мая 2025, запамінана Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Не ўдалось дзелік. Калі ласка, спробуйце яшчэ раз.';

  @override
  String get wrappedFailedToStartGeneration => 'Не ўдалось пачаць генерацыю. Калі ласка, спробуйце яшчэ раз.';

  @override
  String get wrappedStarting => 'Пачатак...';

  @override
  String get wrappedShare => 'Дзелік';

  @override
  String get wrappedShareYourWrapped => 'Дзеліцеся Вашым Wrapped';

  @override
  String get wrappedMy2025 => 'Мая 2025';

  @override
  String get wrappedRememberedByOmi => 'запамінана Omi';

  @override
  String get wrappedMostFunDay => 'Найбольш Забавны';

  @override
  String get wrappedMostProductiveDay => 'Найбольш Прадуктыўны';

  @override
  String get wrappedMostIntenseDay => 'Найбольш Інтэнсіўны';

  @override
  String get wrappedFunniestMoment => 'Найсмешнейшы';

  @override
  String get wrappedMostCringeMoment => 'Найбольш Нязручны';

  @override
  String get wrappedMinutesLabel => 'хвіліны';

  @override
  String get wrappedConversationsLabel => 'разговоры';

  @override
  String get wrappedDaysActiveLabel => 'дзён актыўны';

  @override
  String get wrappedTasksGenerated => 'задачы генерыраваны';

  @override
  String get wrappedTasksCompleted => 'задачы завершаны';

  @override
  String get wrappedTopFivePhrases => 'Топ 5 Фраз';

  @override
  String get wrappedAGreatDay => 'Адличны Дзень';

  @override
  String get wrappedGettingItDone => 'Усё Зроблена';

  @override
  String get wrappedAChallenge => 'Выклік';

  @override
  String get wrappedAHilariousMoment => 'Смешны Момант';

  @override
  String get wrappedThatAwkwardMoment => 'Гэта Нязручны Момант';

  @override
  String get wrappedYouHadFunnyMoments => 'У вас быў некалькі смешных моментаў гэтага году!';

  @override
  String get wrappedWeveAllBeenThere => 'Мы ўсе там былі!';

  @override
  String get wrappedFriend => 'Друг';

  @override
  String get wrappedYourBuddy => 'Ваш сябар!';

  @override
  String get wrappedNotMentioned => 'Не Упамінаны';

  @override
  String get wrappedTheHardPart => 'Цяжкая Частка';

  @override
  String get wrappedPersonalGrowth => 'Персанальны Рост';

  @override
  String get wrappedFunDay => 'Забава';

  @override
  String get wrappedProductiveDay => 'Прадуктыўны';

  @override
  String get wrappedIntenseDay => 'Інтэнсіўны';

  @override
  String get wrappedFunnyMomentTitle => 'Смешны Момант';

  @override
  String get wrappedCringeMomentTitle => 'Нязручны Момант';

  @override
  String get wrappedYouTalkedAboutBadge => 'Вы Гаварыў Аб';

  @override
  String get wrappedCompletedLabel => 'Завершана';

  @override
  String get wrappedMyBuddiesCard => 'Мая Дружыны';

  @override
  String get wrappedBuddiesLabel => 'ДРУЖЫНЫ';

  @override
  String get wrappedObsessionsLabelUpper => 'АБСЕСІІ';

  @override
  String get wrappedStruggleLabelUpper => 'БАРАЦЬБА';

  @override
  String get wrappedWinLabelUpper => 'ПЕРАМОГА';

  @override
  String get wrappedTopPhrasesLabelUpper => 'ТОП ФРАЗЫ';

  @override
  String get wrappedYourHeader => 'Ваш';

  @override
  String get wrappedTopDaysHeader => 'Топ Дзён';

  @override
  String get wrappedYourTopDaysBadge => 'Ваш Топ Дзён';

  @override
  String get wrappedBestHeader => 'Лучшыя';

  @override
  String get wrappedMomentsHeader => 'Моманты';

  @override
  String get wrappedBestMomentsBadge => 'Лучшыя Моманты';

  @override
  String get wrappedBiggestHeader => 'Найбольш';

  @override
  String get wrappedStruggleHeader => 'Барацьба';

  @override
  String get wrappedWinHeader => 'Перамога';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Але вы пушлі скозь 💪';

  @override
  String get wrappedYouDidItEmoji => 'Вы гэта зробілі! 🎉';

  @override
  String get wrappedHours => 'часы';

  @override
  String get wrappedActions => 'дзеяннi';

  @override
  String get multipleSpeakersDetected => 'Выяўлена Некалькі Спікераў';

  @override
  String get multipleSpeakersDescription =>
      'Здаецца, ў запісе ёсць некалькі спікераў. Калі ласка, пераканайцеся, што вы знаходзіцеся ў спакойным месцы і спробуйце яшчэ раз.';

  @override
  String get invalidRecordingDetected => 'Выяўлена Неправільны Запіс';

  @override
  String get notEnoughSpeechDescription => 'Нема дастаткова мовы. Калі ласка, гавараеце больш і спробуйце яшчэ раз.';

  @override
  String get speechDurationDescription =>
      'Пожалуйста, переконайцеся, што вы гавораце не менш за 5 секунд і не больш за 90.';

  @override
  String get connectionLostDescription =>
      'Сувязь была перарвана. Пожалуйста, праверце сувязь з інтэрнэтам і паспрабуйце яшчэ раз.';

  @override
  String get howToTakeGoodSample => 'Як зрабіць добрую выбарку?';

  @override
  String get goodSampleInstructions =>
      '1. Переконайцеся, што вы ў цішкім месцы.\n2. Гавораце ясна і натуральна.\n3. Переконайцеся, што ваш прыбор у натуральным становішчы, на вашай шыі.\n\nПасля стварэння вы заўсёды можаце яго палепшыць або зрабіць яшчэ раз.';

  @override
  String get noDeviceConnectedUseMic => 'Прыбор не падключаны. Будзе выкарыстаны мікрафон тэлефона.';

  @override
  String get doItAgain => 'Зрабіць яшчэ раз';

  @override
  String get listenToSpeechProfile => 'Слухаць мой профіль голаса ➡️';

  @override
  String get recognizingOthers => 'Распазнаванне іншых 👀';

  @override
  String get keepGoingGreat => 'Працягвайце, вы робіце чудоўна';

  @override
  String get somethingWentWrongTryAgain => 'Нешто палося не так! Пожалуйста, паспрабуйце яшчэ раз пазней.';

  @override
  String get uploadingVoiceProfile => 'Загрузка вашага профіля голаса....';

  @override
  String get memorizingYourVoice => 'Запамінанне вашага голаса...';

  @override
  String get personalizingExperience => 'Персаналізацыя вашага досведу...';

  @override
  String get keepSpeakingUntil100 => 'Гавораце, пакуль вы не атрымаеце 100%.';

  @override
  String get greatJobAlmostThere => 'Выдатна, вы ўжо блізка';

  @override
  String get soCloseJustLittleMore => 'Так блізка, толькі крупіцу больш';

  @override
  String get notificationFrequency => 'Частата апавяшчэнняў';

  @override
  String get controlNotificationFrequency => 'Кантраліруйце, як часта Omi адпраўляе вам прааактыўныя апавяшчэнні.';

  @override
  String get yourScore => 'Ваш бал';

  @override
  String get dailyScoreBreakdown => 'Раскладанне дзённага балу';

  @override
  String get todaysScore => 'Dzеnny bal';

  @override
  String get tasksCompleted => 'Выкананыя задачы';

  @override
  String get completionRate => 'Адсотак завяршэння';

  @override
  String get howItWorks => 'Як гэта працуе';

  @override
  String get dailyScoreExplanation =>
      'Ваш дзённы бал базуецца на выкананні задач. Выканайце свае задачы, каб палепшыць ваш бал!';

  @override
  String get notificationFrequencyDescription =>
      'Кантраліруйце, як часта Omi адпраўляе вам прааактыўныя апавяшчэнні і напамінаўі.';

  @override
  String get sliderOff => 'Выкл.';

  @override
  String get sliderMax => 'Макс.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Рэзюмэ створана для $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Не удалося стварыць рэзюмэ. Переконайцеся, што у вас ёсць разговоры для гэтага дня.';

  @override
  String get recap => 'Адно воку';

  @override
  String deleteQuoted(String name) {
    return 'Выдаліць \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Перамясціць $count разговор(аў) у:';
  }

  @override
  String get noFolder => 'Нема папкі';

  @override
  String get removeFromAllFolders => 'Выдаліць з усіх папак';

  @override
  String get buildAndShareYourCustomApp => 'Постаў і дзелісь сваім адмысловым прыкладаннем';

  @override
  String get searchAppsPlaceholder => 'Пошук 1500+ прыкладанняў';

  @override
  String get filters => 'Фільтры';

  @override
  String get frequencyOff => 'Выкл.';

  @override
  String get frequencyMinimal => 'Мінімальна';

  @override
  String get frequencyLow => 'Нізка';

  @override
  String get frequencyBalanced => 'Збалансавана';

  @override
  String get frequencyHigh => 'Высока';

  @override
  String get frequencyMaximum => 'Максімальна';

  @override
  String get frequencyDescOff => 'Без прааактыўных апавяшчэнняў';

  @override
  String get frequencyDescMinimal => 'Толькі крітычныя напамінаўі';

  @override
  String get frequencyDescLow => 'Толькі важныя абнаўленні';

  @override
  String get frequencyDescBalanced => 'Звычайныя карыснымі падштурхаўкі';

  @override
  String get frequencyDescHigh => 'Частыя праверкі';

  @override
  String get frequencyDescMaximum => 'Застаёцеся пастаянна ўключаны';

  @override
  String get clearChatQuestion => 'Ачысціць чат?';

  @override
  String get syncingMessages => 'Синхранізацыя паведамленняў з сервером...';

  @override
  String get chatAppsTitle => 'Прыкладанні чата';

  @override
  String get selectApp => 'Абраць прыкладанне';

  @override
  String get noChatAppsEnabled =>
      'Няма ўключаных прыкладанняў чата.\nНатісніце \"Ўключыць прыкладанні\", каб дадаць яшчэ.';

  @override
  String get disable => 'Выключыць';

  @override
  String get photoLibrary => 'Бібліятэка фотаў';

  @override
  String get chooseFile => 'Абраць файл';

  @override
  String get connectAiAssistantsToYourData => 'Падлучыце AI асістэнтаў да ваших даных';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Śleдзьце свае личныя мэты на галаўнай старонцы';

  @override
  String get deleteRecording => 'Выдаліць запіс';

  @override
  String get thisCannotBeUndone => 'Гэта нельзя адмяніць.';

  @override
  String get sdCard => 'SD картка';

  @override
  String get fromSd => 'З SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Хуткі пераноса';

  @override
  String get syncingStatus => 'Синхранізацыя';

  @override
  String get failedStatus => 'Не вышло';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Метад передачы';

  @override
  String get fast => 'Хуткі';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Тэлефон';

  @override
  String get cancelSync => 'Скасаваць синхранізацыю';

  @override
  String get cancelSyncMessage => 'Даныя, якія ўжо звантажаны, будуць сахаваны. Вы можаце пановіць пазней.';

  @override
  String get syncCancelled => 'Синхранізацыя скасавана';

  @override
  String get deleteProcessedFiles => 'Выдаліць апрацаваныя файлы';

  @override
  String get processedFilesDeleted => 'Апрацаваныя файлы выдалены';

  @override
  String get wifiEnableFailed => 'Не вышло ўключыць WiFi на прыборы. Пожалуйста, паспрабуйце яшчэ раз.';

  @override
  String get deviceNoFastTransfer => 'Ваш прыбор не падтрымлівае хуткі пераноса. Выкарыстайце Bluetooth замест гэтага.';

  @override
  String get enableHotspotMessage => 'Пожалуйста, ўключыце хотспот вашага тэлефона і паспрабуйце яшчэ раз.';

  @override
  String get transferStartFailed => 'Не вышло запусціць пераноса. Пожалуйста, паспрабуйце яшчэ раз.';

  @override
  String get deviceNotResponding => 'Прыбор не адрэагаваў. Пожалуйста, паспрабуйце яшчэ раз.';

  @override
  String get invalidWifiCredentials => 'Няправільныя запалогінванні WiFi. Праверце налады хотспота.';

  @override
  String get wifiConnectionFailed => 'Не удалося падлучыцца да WiFi. Пожалуйста, паспрабуйце яшчэ раз.';

  @override
  String get sdCardProcessing => 'Апрацаванне SD картка';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Апрацаванне $count запісу(ў). Файлы будуць выдалены з SD картка пасля.';
  }

  @override
  String get process => 'Апрацаваць';

  @override
  String get wifiSyncFailed => 'WiFi синхранізацыя не вышла';

  @override
  String get processingFailed => 'Апрацаванне не вышло';

  @override
  String get downloadingFromSdCard => 'Загрузка з SD картка';

  @override
  String processingProgress(int current, int total) {
    return 'Апрацаванне $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count разговор(аў) стварана';
  }

  @override
  String get internetRequired => 'Інтэрнэт патрэбны';

  @override
  String get processAudio => 'Апрацаваць аудыё';

  @override
  String get start => 'Пачаць';

  @override
  String get noRecordings => 'Няма запісаў';

  @override
  String get audioFromOmiWillAppearHere => 'Аудыё з вашага прыбора Omi будзе пацвяршана тут';

  @override
  String get deleteProcessed => 'Выдаліць апрацаваныя';

  @override
  String get tryDifferentFilter => 'Паспрабуйце іншы фільтр';

  @override
  String get recordings => 'Запісы';

  @override
  String get enableRemindersAccess =>
      'Пожалуйста, ўключыце доступ да напамінаўяў ў налладах, каб выкарыстоўваць Apple Reminders';

  @override
  String todayAtTime(String time) {
    return 'Сёння ў $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Учора ў $time';
  }

  @override
  String get lessThanAMinute => 'Менш за хвіліну';

  @override
  String estimatedMinutes(int count) {
    return '~$count хвіліна(м)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count гадзіна(м)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Прыблізны: $time засталося';
  }

  @override
  String get summarizingConversation => 'Рэзюмаванне разговора...\nГэта можа занять некалькі секунд';

  @override
  String get resummarizingConversation => 'Пераўтварэнне разговора...\nГэта можа занять некалькі секунд';

  @override
  String get nothingInterestingRetry => 'Нічога цікавага не знойдзена,\nхочаце паспрабаваць яшчэ раз?';

  @override
  String get noSummaryForConversation => 'Рэзюмэ не даступна\nдля гэтага разговора.';

  @override
  String get unknownLocation => 'Невядомае месцазнаходжанне';

  @override
  String get couldNotLoadMap => 'Не вышло загрузіць карту';

  @override
  String get triggerConversationIntegration => 'Запусціць інтэграцыю разговора, созданного';

  @override
  String get webhookUrlNotSet => 'URL webhook не ўстаўлены';

  @override
  String get setWebhookUrlInSettings =>
      'Пожалуйста, ўстаўце URL webhook ў налады разработчыка, каб выкарыстоўваць гэтую функцыю.';

  @override
  String get sendWebUrl => 'Адправіць URL вэба';

  @override
  String get sendTranscript => 'Адправіць транскрыпцыю';

  @override
  String get sendSummary => 'Адправіць рэзюмэ';

  @override
  String get debugModeDetected => 'Праверка рэжыму выявлена';

  @override
  String get performanceReduced => 'Прадуктыўнасць скошана ў 5-10 разоў. Выкарыстайце рэжым выпуску.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Аўтаматычна закрывацца ў ${seconds}s';
  }

  @override
  String get modelRequired => 'Мадэль патрэбна';

  @override
  String get downloadWhisperModel => 'Пожалуйста, загрузьце мадэль Whisper перад тым, як захаваць.';

  @override
  String get deviceNotCompatible => 'Прыбор не сумяшчаўны';

  @override
  String get deviceRequirements => 'Ваш прыбор не адпавядае патрабаванням для транскрыпцыі на прыборы.';

  @override
  String get willLikelyCrash => 'Ўключэнне гэтага, верагодна, прывядзе да краху або замарожання прыкладання.';

  @override
  String get transcriptionSlowerLessAccurate => 'Транскрыпцыя будзе значна павольнейшая і менш дакладная.';

  @override
  String get proceedAnyway => 'Працягнуць у любым выпадку';

  @override
  String get olderDeviceDetected => 'Старэйшы прыбор выявлены';

  @override
  String get onDeviceSlower => 'Транскрыпцыя на прыборы можа быць павольнейшая на гэтым прыборы.';

  @override
  String get batteryUsageHigher => 'Выкарыстанне батарэі будзе вышэй за облачную транскрыпцыю.';

  @override
  String get considerOmiCloud => 'Разгледайце выкарыстанне Omi Cloud для лепшай прадуктыўнасці.';

  @override
  String get highResourceUsage => 'Высокае выкарыстанне рэсурсаў';

  @override
  String get onDeviceIntensive => 'Транскрыпцыя на прыборы вельмі інтэнсіўная ў вычыслядель.';

  @override
  String get batteryDrainIncrease => 'Дранаж батарэі значна павеліцца.';

  @override
  String get deviceMayWarmUp => 'Прыбор можа наніцца падчас доўгого выкарыстання.';

  @override
  String get speedAccuracyLower => 'Хутквасць і дакладнасць могуць быць ніжэй за облачныя мадэлі.';

  @override
  String get cloudProvider => 'Облачны пастаўшчык';

  @override
  String get premiumMinutesInfo =>
      '1200 премыум хвілін/месяц. Вкладка На прыборы прапанавае неабмежаваную бясплатную транскрыпцыю.';

  @override
  String get viewUsage => 'Прагляд выкарыстання';

  @override
  String get localProcessingInfo =>
      'Аудыё апрацоўваецца лакальна. Працуе аўтаномна, больш прыватна, але выкарыстоўвае больш батарэі.';

  @override
  String get model => 'Мадэль';

  @override
  String get performanceWarning => 'Папярэджаны аб прадуктыўнасці';

  @override
  String get largeModelWarning =>
      'Гэтая мадэль вельмі воладзьма і можа прывесці да краху прыкладання або працаваць вельмі павольна на мабільных прыборах.\n\nРакамендаваны \"small\" ці \"base\".';

  @override
  String get usingNativeIosSpeech => 'Выкарыстанне родзімага распазнавання маўлення iOS';

  @override
  String get noModelDownloadRequired =>
      'Будзе выкарыстаны родзім рухавік маўлення вашага прыбора. Загрузка мадэлі не патрэбна.';

  @override
  String get modelReady => 'Мадэль готавая';

  @override
  String get redownload => 'Загрузіць яшчэ раз';

  @override
  String get doNotCloseApp => 'Пожалуйста, не закрывайце прыкладанне.';

  @override
  String get downloading => 'Загрузка...';

  @override
  String get downloadModel => 'Загрузіць мадэль';

  @override
  String estimatedSize(String size) {
    return 'Прыблізны памер: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Даступна месца: $space';
  }

  @override
  String get notEnoughSpace => 'Папярэджаны: Няма дастатковага месца!';

  @override
  String get download => 'Загрузіць';

  @override
  String downloadError(String error) {
    return 'Памылка загрузкі: $error';
  }

  @override
  String get cancelled => 'Скасавана';

  @override
  String get deviceNotCompatibleTitle => 'Прыбор не сумяшчаўны';

  @override
  String get deviceNotMeetRequirements => 'Ваш прыбор не адпавядае патрабаванням для транскрыпцыі на прыборы.';

  @override
  String get transcriptionSlowerOnDevice => 'Транскрыпцыя на прыборы можа быць павольнейшая на гэтым прыборы.';

  @override
  String get computationallyIntensive => 'Транскрыпцыя на прыборы вельмі інтэнсіўная ў вычыслядель.';

  @override
  String get batteryDrainSignificantly => 'Дранаж батарэі значна павеліцца.';

  @override
  String get premiumMinutesMonth =>
      '1200 премыум хвілін/месяц. Вкладка На прыборы прапанавае неабмежаваную бясплатную транскрыпцыю. ';

  @override
  String get audioProcessedLocally =>
      'Аудыё апрацоўваецца лакальна. Працуе аўтаномна, больш прыватна, але выкарыстоўвае больш батарэі.';

  @override
  String get languageLabel => 'Мова';

  @override
  String get modelLabel => 'Мадэль';

  @override
  String get modelTooLargeWarning =>
      'Гэтая мадэль вельмі воладзьма і можа прывесці да краху прыкладання або працаваць вельмі павольна на мабільных прыборах.\n\nРакамендаваны \"small\" ці \"base\".';

  @override
  String get nativeEngineNoDownload =>
      'Будзе выкарыстаны родзім рухавік маўлення вашага прыбора. Загрузка мадэлі не патрэбна.';

  @override
  String modelReadyWithName(String model) {
    return 'Мадэль готавая ($model)';
  }

  @override
  String get reDownload => 'Загрузіць яшчэ раз';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Загрузка $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Падрыхтоўка $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Памылка загрузкі: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Прыблізны памер: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Даступна месца: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Убудаваная жывая транскрыпцыя Omi аптымізавана для разговораў у рэальным часе з аўтаматычным распазнаваннем дыктарыў і дыяризацыяй.';

  @override
  String get reset => 'Скінуць';

  @override
  String get useTemplateFrom => 'Выкарыстоўваць шаблон з';

  @override
  String get selectProviderTemplate => 'Абраць шаблон пастаўшчыка...';

  @override
  String get quicklyPopulateResponse => 'Хутка запоўніце вядомым фарматам адказу пастаўшчыка';

  @override
  String get quicklyPopulateRequest => 'Хутка запоўніце вядомым фарматам запыту пастаўшчыка';

  @override
  String get invalidJsonError => 'Няправільны JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Загрузіць мадэль ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Мадэль: $model';
  }

  @override
  String get device => 'Прыбор';

  @override
  String get chatAssistantsTitle => 'Асістэнты чата';

  @override
  String get permissionReadConversations => 'Чытаць разговоры';

  @override
  String get permissionReadMemories => 'Чытаць памяць';

  @override
  String get permissionReadTasks => 'Чытаць задачы';

  @override
  String get permissionCreateConversations => 'Стварыць разговоры';

  @override
  String get permissionCreateMemories => 'Стварыць памяць';

  @override
  String get permissionTypeAccess => 'Доступ';

  @override
  String get permissionTypeCreate => 'Стварыць';

  @override
  String get permissionTypeTrigger => 'Запусціць';

  @override
  String get permissionDescReadConversations => 'Гэтае прыкладанне можа адкрыць доступ да вашых разговораў.';

  @override
  String get permissionDescReadMemories => 'Гэтае прыкладанне можа адкрыць доступ да вашой памяці.';

  @override
  String get permissionDescReadTasks => 'Гэтае прыкладанне можа адкрыць доступ да ваших задач.';

  @override
  String get permissionDescCreateConversations => 'Гэтае прыкладанне можа стварыць новыя разговоры.';

  @override
  String get permissionDescCreateMemories => 'Гэтае прыкладанне можа стварыць новую памяць.';

  @override
  String get realtimeListening => 'Слуханне ў рэальным часе';

  @override
  String get setupCompleted => 'Завершана';

  @override
  String get pleaseSelectRating => 'Пожалуйста, абярыце адзнаку';

  @override
  String get writeReviewOptional => 'Напісаць адгук (неабавязаельна)';

  @override
  String get setupQuestionsIntro => 'Дапамажыце нам палепшыць Omi, адпавядаючы на некалькі пытанняў. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Што вы робіце?';

  @override
  String get setupQuestionUsage => '2. Дзе вы плануеце выкарыстоўваць сваю Omi?';

  @override
  String get setupQuestionAge => '3. Якой ваш ўзрост?';

  @override
  String get setupAnswerAllQuestions => 'Вы яшчэ не адпавяділі на ўсе пытанні! 🥺';

  @override
  String get setupSkipHelp => 'Прапусціць, я не хачу дапамагаць :C';

  @override
  String get professionEntrepreneur => 'Прадпрымальнік';

  @override
  String get professionSoftwareEngineer => 'Інжынер па апрацоўцы';

  @override
  String get professionProductManager => 'Менеджэр прадукту';

  @override
  String get professionExecutive => 'Кіраўнік';

  @override
  String get professionSales => 'Продажі';

  @override
  String get professionStudent => 'Студэнт';

  @override
  String get usageAtWork => 'На пра­цы';

  @override
  String get usageIrlEvents => 'Мерапрыемства IRL';

  @override
  String get usageOnline => 'В сеціве';

  @override
  String get usageSocialSettings => 'У сацыальных параўдах';

  @override
  String get usageEverywhere => 'Скрыж ва ўсюды';

  @override
  String get customBackendUrlTitle => 'Адмысловы URL бэкэнда';

  @override
  String get backendUrlLabel => 'URL бэкэнда';

  @override
  String get saveUrlButton => 'Захаваць URL';

  @override
  String get enterBackendUrlError => 'Пожалуйста, ўвядзіце URL бэкэнда';

  @override
  String get urlMustEndWithSlashError => 'URL мусіць заканчвацца на \"/\"';

  @override
  String get invalidUrlError => 'Пожалуйста, ўвядзіце дакладны URL';

  @override
  String get backendUrlSavedSuccess => 'URL бэкэнда сахаваны паспяхова!';

  @override
  String get signInTitle => 'Уваход';

  @override
  String get signInButton => 'Уваход';

  @override
  String get enterEmailError => 'Пожалуйста, ўвядзіце ваш email';

  @override
  String get invalidEmailError => 'Пожалуйста, ўвядзіце дакладны email';

  @override
  String get enterPasswordError => 'Пожалуйста, ўвядзіце ваш пароль';

  @override
  String get passwordMinLengthError => 'Пароль мусіць быць адна ў 8 сімвалаў';

  @override
  String get signInSuccess => 'Уваход паспяхово!';

  @override
  String get alreadyHaveAccountLogin => 'Ужо ёсць рахунак? Увайдзіце';

  @override
  String get emailLabel => 'Email';

  @override
  String get passwordLabel => 'Пароль';

  @override
  String get createAccountTitle => 'Стварыць рахунак';

  @override
  String get nameLabel => 'Імя';

  @override
  String get repeatPasswordLabel => 'Паўтарыць пароль';

  @override
  String get signUpButton => 'Зарэгістравацца';

  @override
  String get enterNameError => 'Пожалуйста, ўвядзіце ваше імя';

  @override
  String get passwordsDoNotMatch => 'Паролі не супадаюць';

  @override
  String get signUpSuccess => 'Рэгістрацыя паспяхова!';

  @override
  String get loadingKnowledgeGraph => 'Загрузка графіка ведаў...';

  @override
  String get noKnowledgeGraphYet => 'Графіка ведаў яшчэ нема';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Пабудова графіка ведаў з памяці...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Ваш графік ведаў будзе пабудаваны аўтаматычна, калі вы стварыце новыя памяці.';

  @override
  String get buildGraphButton => 'Пабудаваць графік';

  @override
  String get checkOutMyMemoryGraph => 'Праверыце мой графік памяці!';

  @override
  String get getButton => 'Атрымаць';

  @override
  String openingApp(String appName) {
    return 'Адкрыванне $appName...';
  }

  @override
  String get writeSomething => 'Напішыце нешто';

  @override
  String get submitReply => 'Адправіць адказ';

  @override
  String get editYourReply => 'Адрэдагаваць ваш адказ';

  @override
  String get replyToReview => 'Адказаць на адгук';

  @override
  String get rateAndReviewThisApp => 'Адзнаціць і адправіць адгук гэтага прыкладання';

  @override
  String get noChangesInReview => 'Няма змен у адгуку для абнаўлення.';

  @override
  String get cantRateWithoutInternet => 'Нельзя адзнаціць прыкладанне без сувязі з інтэрнэтам.';

  @override
  String get appAnalytics => 'Аналітыка прыкладання';

  @override
  String get learnMoreLink => 'узнаць больш';

  @override
  String get moneyEarned => 'Зарабіены грошы';

  @override
  String get writeYourReply => 'Напішыце ваш адказ...';

  @override
  String get replySentSuccessfully => 'Адказ адправлены паспяхово';

  @override
  String failedToSendReply(String error) {
    return 'Не вышло адправіць адказ: $error';
  }

  @override
  String get send => 'Адправіць';

  @override
  String starFilter(int count) {
    return '$count звязда';
  }

  @override
  String get noReviewsFound => 'Адгукаў не знойдзена';

  @override
  String get editReply => 'Адрэдагаваць адказ';

  @override
  String get reply => 'Адказаць';

  @override
  String starFilterLabel(int count) {
    return '$count звязда';
  }

  @override
  String get sharePublicLink => 'Дзелісь публічным спасылкай';

  @override
  String get connectedKnowledgeData => 'Падлучаныя даныя ведаў';

  @override
  String get enterName => 'Ўвядзіце імя';

  @override
  String get goal => 'МЭТА';

  @override
  String get tapToTrackThisGoal => 'Натісніце, каб сцягнуць гэту мэту';

  @override
  String get tapToSetAGoal => 'Натісніце, каб ўстаўіць мэту';

  @override
  String get processedConversations => 'Апрацаваны разговоры';

  @override
  String get updatedConversations => 'Абнаўленыя разговоры';

  @override
  String get newConversations => 'Новыя разговоры';

  @override
  String get summaryTemplate => 'Шаблон рэзюмэ';

  @override
  String get suggestedTemplates => 'Прапанаваны шаблоны';

  @override
  String get otherTemplates => 'Іншыя шаблоны';

  @override
  String get availableTemplates => 'Даступныя шаблоны';

  @override
  String get getCreative => 'Будзьце крэатыўны';

  @override
  String get defaultLabel => 'Па змоўчанню';

  @override
  String get lastUsedLabel => 'Апошняе выкарыстанне';

  @override
  String get setDefaultApp => 'Устаўіць прыкладанне па змоўчанню';

  @override
  String setDefaultAppContent(String appName) {
    return 'Ўстаўіць $appName як адмысловае прыкладанне рэзюмавання?\n\nГэтае прыкладанне будзе аўтаматычна выкарыстоўвацца для ўсіх будучых рэзюме разговораў.';
  }

  @override
  String get setDefaultButton => 'Устаўіць па змоўчанню';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName ўстаўлена як адмысловае прыкладанне рэзюмавання';
  }

  @override
  String get createCustomTemplate => 'Стварыць адмысловы шаблон';

  @override
  String get allTemplates => 'Усе шаблоны';

  @override
  String failedToInstallApp(String appName) {
    return 'Не вышло ўстаноўць $appName. Пожалуйста, паспрабуйце яшчэ раз.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Памылка ўстаноўкі $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Пазначыць дыктара $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Персона з гэтым імем ужо існуе.';

  @override
  String get selectYouFromList => 'Каб пазначыць сябе, пожалуйста, абярыце \"Вы\" са спіса.';

  @override
  String get enterPersonsName => 'Ўвядзіце імя персоны';

  @override
  String get addPerson => 'Дадаць персону';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Пазначыць іншыя сегменты з гэтага дыктара ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Пазначыць іншыя сегменты';

  @override
  String get managePeople => 'Кіраваць людзьмі';

  @override
  String get shareViaSms => 'Дзелісь праз SMS';

  @override
  String get selectContactsToShareSummary => 'Абярыце контакты, каб дзелініцца рэзюмэ разговара';

  @override
  String get searchContactsHint => 'Шукаць контакты...';

  @override
  String contactsSelectedCount(int count) {
    return '$count выбрана';
  }

  @override
  String get clearAllSelection => 'Ачысціць ўсё';

  @override
  String get selectContactsToShare => 'Абярыце контакты для дзяління';

  @override
  String shareWithContactCount(int count) {
    return 'Дзелісь з $count контактам';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Дзелісь з $count контактамі';
  }

  @override
  String get contactsPermissionRequired => 'Дозвол контактаў патрэбны';

  @override
  String get contactsPermissionRequiredForSms => 'Дозвол контактаў патрэбны для дзяління праз SMS';

  @override
  String get grantContactsPermissionForSms => 'Пожалуйста, даруйце дозвол контактаў для дзяління праз SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Контакты з нумарамі тэлефонаў не знойдзены';

  @override
  String get noContactsMatchSearch => 'Контакты, якія адпавядаюць вашаму пошуку, не знойдзены';

  @override
  String get failedToLoadContacts => 'Не вышло загрузіць контакты';

  @override
  String get failedToPrepareConversationForSharing =>
      'Не вышло падрыхтаваць разговор для дзяління. Пожалуйста, паспрабуйце яшчэ раз.';

  @override
  String get couldNotOpenSmsApp => 'Не вышло адкрыць прыкладанне SMS. Пожалуйста, паспрабуйце яшчэ раз.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Вось што мы толькі што абмяркоўвалі: $link';
  }

  @override
  String get wifiSync => 'WiFi синхранізацыя';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item скапіяваны ў буфер абмену';
  }

  @override
  String get wifiConnectionFailedTitle => 'Сувязь не вышла';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Падлучэнне да $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Ўключыць WiFi на $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Падлучыцца да $deviceName';
  }

  @override
  String get recordingDetails => 'Дэталі запісу';

  @override
  String get storageLocationSdCard => 'SD картка';

  @override
  String get storageLocationLimitlessPendant => 'Limitless кулон';

  @override
  String get storageLocationPhone => 'Тэлефон';

  @override
  String get storageLocationPhoneMemory => 'Тэлефон (памяць)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Сахавана на $deviceName';
  }

  @override
  String get transferring => 'Пераноса...';

  @override
  String get transferRequired => 'Пераноса патрэбна';

  @override
  String get downloadingAudioFromSdCard => 'Загрузка аудыё з SD картка вашага прыбора';

  @override
  String get transferRequiredDescription =>
      'Гэты запіс сахаваны на SD картка вашага прыбора. Перамясціце яго на ваш тэлефон, каб слухаць ці дзелініцца.';

  @override
  String get cancelTransfer => 'Скасаваць пераноса';

  @override
  String get transferToPhone => 'Перамясціць на тэлефон';

  @override
  String get privateAndSecureOnDevice => 'Прыватны і бяспечны на вашым прыборы';

  @override
  String get recordingInfo => 'Інфармацыя запісу';

  @override
  String get transferInProgress => 'Пераноска выконваецца...';

  @override
  String get shareRecording => 'Абагуліць запіс';

  @override
  String get deleteRecordingConfirmation =>
      'Вы ўпэўнены, што хочаце назаўсёды выдаліць гэты запіс? Гэта не можна адмяніць.';

  @override
  String get recordingIdLabel => 'ID запісу';

  @override
  String get dateTimeLabel => 'Дата і час';

  @override
  String get durationLabel => 'Трыванне';

  @override
  String get audioFormatLabel => 'Фармат аўдыё';

  @override
  String get storageLocationLabel => 'Месцазнаходжанне сховішча';

  @override
  String get estimatedSizeLabel => 'Прыблізны памер';

  @override
  String get deviceModelLabel => 'Мадэль прыстасавання';

  @override
  String get deviceIdLabel => 'ID прыстасавання';

  @override
  String get statusLabel => 'Статус';

  @override
  String get statusProcessed => 'Апрацавана';

  @override
  String get statusUnprocessed => 'Не апрацавана';

  @override
  String get switchedToFastTransfer => 'Пераклучана на хуткую пераноску';

  @override
  String get transferCompleteMessage => 'Пераноска завершана! Вы можаце граць гэты запіс.';

  @override
  String transferFailedMessage(String error) {
    return 'Пераноска не атрымалася: $error';
  }

  @override
  String get transferCancelled => 'Пераноска скасавана';

  @override
  String get fastTransferEnabled => 'Хутка пераноска ўключана';

  @override
  String get bluetoothSyncEnabled => 'Синхранізацыя Bluetooth ўключана';

  @override
  String get enableFastTransfer => 'Ўключыць хуткую пераноску';

  @override
  String get fastTransferDescription =>
      'Хутка пераноска выкарыстоўвае WiFi для ~5х больш хуткага хуткасці. Ваш тэлефон часова падключыцца да сеткі WiFi вашага прыстасавання Omi падчас пераносы.';

  @override
  String get internetAccessPausedDuringTransfer => 'Доступ у інтэрнет паставлены на паўзу падчас пераносы';

  @override
  String get chooseTransferMethodDescription =>
      'Выберыце спосаб пераносы запісаў з вашага прыстасавання Omi на ваш тэлефон.';

  @override
  String get wifiSpeed => '~150 KB/s праз WiFi';

  @override
  String get fiveTimesFaster => '5X ХУТЧЭЙ';

  @override
  String get fastTransferMethodDescription =>
      'Стварае прамую злучэнне WiFi з вашым прыстасаваннем Omi. Ваш тэлефон часова адключаецца ад звычайнай сеткі WiFi падчас пераносы.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s праз BLE';

  @override
  String get bluetoothMethodDescription =>
      'Выкарыстоўвае стандартнае Bluetooth Low Energy злучэнне. Павольней, але не ўплывае на ваше WiFi злучэнне.';

  @override
  String get selected => 'Выбрана';

  @override
  String get selectOption => 'Выбраць';

  @override
  String get lowBatteryAlertTitle => 'Абвяшчэнне пра нізкі заряд батарэі';

  @override
  String get lowBatteryAlertBody => 'Ваша прыстасаванне буквальна вычарпвае батарэю. Час пазарадзіць! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Ваша прыстасаванне Omi адключылося';

  @override
  String get deviceDisconnectedNotificationBody => 'Калі ласка, перазлучыцеся, каб пацягнуць Omi.';

  @override
  String get firmwareUpdateAvailable => 'Абнаўленне прашывак даступнае';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Новае абнаўленне прашывак ($version) даступнае для вашага прыстасавання Omi. Ці хочаце вы абнавіць прямо зараз?';
  }

  @override
  String get later => 'Позней';

  @override
  String get appDeletedSuccessfully => 'Прыклад выдалены ўдала';

  @override
  String get appDeleteFailed => 'Не вдалося выдаліць дадатак. Спрабуйце яшчэ раз позней.';

  @override
  String get appVisibilityChangedSuccessfully => 'Відимасць дадатка змененая ўдала. Гэта можа заняць некалькі хвілін.';

  @override
  String get errorActivatingAppIntegration =>
      'Памылка пры актывізацыі дадатка. Калі гэта дадатак інтэграцыі, заканчыце наладку.';

  @override
  String get errorUpdatingAppStatus => 'Адбылася памылка пры абнаўленні стану дадатка.';

  @override
  String get calculatingETA => 'Разлічваецца...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Прыблізна $minutes хвілін да канца';
  }

  @override
  String get aboutAMinuteRemaining => 'Прыблізна хвіліна да канца';

  @override
  String get almostDone => 'Амаль скончана...';

  @override
  String get omiSays => 'Omi кажа';

  @override
  String get analyzingYourData => 'Аналіз вашых даных...';

  @override
  String migratingToProtection(String level) {
    return 'Пераносяцца да $level абаронячу...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Няма даных для пераносу. Завяршаюцца...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Пераносяцца $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Ўсе аб\'екты перанесены. Завяршаюцца...';

  @override
  String get migrationErrorOccurred => 'Адбылася памылка пры міграцыі. Спрабуйце яшчэ раз.';

  @override
  String get migrationComplete => 'Міграцыя завершана!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Ваша даты цяпер абаронены новымі $level наладкамі.';
  }

  @override
  String get chatsLowercase => 'чаты';

  @override
  String get dataLowercase => 'даты';

  @override
  String get fallNotificationTitle => 'Ой';

  @override
  String get fallNotificationBody => 'Вы упалі?';

  @override
  String get importantConversationTitle => 'Важная разма';

  @override
  String get importantConversationBody =>
      'Вы толькі што мелі важную размову. Націсніце, каб абагуліць рэзюмэ з іншымі.';

  @override
  String get templateName => 'Назва шаблёна';

  @override
  String get templateNameHint => 'напрыклад, Іспаўнялец элементаў дзеяння наездак';

  @override
  String get nameMustBeAtLeast3Characters => 'Назва павінна быць не менш за 3 сімвалы';

  @override
  String get conversationPromptHint =>
      'напрыклад, Выняць элементы дзеяння, рашэнні, прынятыя і ключавыя моменты з прадстаўленай размовы.';

  @override
  String get pleaseEnterAppPrompt => 'Калі ласка, введзіце запіт да вашага дадатка';

  @override
  String get promptMustBeAtLeast10Characters => 'Запіт павінен быць не менш за 10 сімвалаў';

  @override
  String get anyoneCanDiscoverTemplate => 'Любы можа адкрыць ваш шаблён';

  @override
  String get onlyYouCanUseTemplate => 'Толькі вы можаце выкарыстаць гэты шаблён';

  @override
  String get generatingDescription => 'Генерацыя апісання...';

  @override
  String get creatingAppIcon => 'Стварэнне значка дадатка...';

  @override
  String get installingApp => 'Ўстанаўленне дадатка...';

  @override
  String get appCreatedAndInstalled => 'Дадатак створаны і ўстаноўлены!';

  @override
  String get appCreatedSuccessfully => 'Дадатак створаны ўдала!';

  @override
  String get failedToCreateApp => 'Не вдалося стварыць дадатак. Спрабуйце яшчэ раз.';

  @override
  String get addAppSelectCoreCapability => 'Калі ласка, выберыце адну яшчэ асноўную магчымасць для вашага дадатка';

  @override
  String get addAppSelectPaymentPlan => 'Калі ласка, выберыце план плацежа і ўведзіце цану за ваш дадатак';

  @override
  String get addAppSelectCapability => 'Калі ласка, выберыце хаця б адну магчымасць для вашага дадатка';

  @override
  String get addAppSelectLogo => 'Калі ласка, выберыце лога для вашага дадатка';

  @override
  String get addAppEnterChatPrompt => 'Калі ласка, введзіце запіт чата для вашага дадатка';

  @override
  String get addAppEnterConversationPrompt => 'Калі ласка, введзіце запіт разма для вашага дадатка';

  @override
  String get addAppSelectTriggerEvent => 'Калі ласка, выберыце падзею трыгера для вашага дадатка';

  @override
  String get addAppEnterWebhookUrl => 'Калі ласка, введзіце URL-адрас вэбхука для вашага дадатка';

  @override
  String get addAppSelectCategory => 'Калі ласка, выберыце катэгорыю для вашага дадатка';

  @override
  String get addAppFillRequiredFields => 'Калі ласка, запоўніце ўсе абавязковыя палі правільна';

  @override
  String get addAppUpdatedSuccess => 'Дадатак абнаўлены ўдала 🚀';

  @override
  String get addAppUpdateFailed => 'Не вдалося абнавіць дадатак. Спрабуйце яшчэ раз позней';

  @override
  String get addAppSubmittedSuccess => 'Дадатак прыняты ўдала 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Памылка пры адкрыцці вызначальніка файлаў: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Памылка пры выбары выявы: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Дозвол на фотаграфіі адмоўлены. Калі ласка, разрэшыце доступ да фотаграфій, каб выбраць выяву';

  @override
  String get addAppErrorSelectingImageRetry => 'Памылка пры выбары выявы. Спрабуйце яшчэ раз.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Памылка пры выбары мініяцюры: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Памылка пры выбары мініяцюры. Спрабуйце яшчэ раз.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Іншыя магчымасці не могуць быць выбраны з асобай';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Персана не можа быць выбрана з іншымі магчымасцямі';

  @override
  String get paymentFailedToFetchCountries => 'Не вдалося атрымаць падтрымліваемыя краіны. Спрабуйце яшчэ раз позней.';

  @override
  String get paymentFailedToSetDefault => 'Не вдалося задаць спосаб плацежа па змаўчанню. Спрабуйце яшчэ раз позней.';

  @override
  String get paymentFailedToSavePaypal => 'Не вдалося захаваць дэталі PayPal. Спрабуйце яшчэ раз позней.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Актыўны';

  @override
  String get paymentStatusConnected => 'Падключана';

  @override
  String get paymentStatusNotConnected => 'Не падключана';

  @override
  String get paymentAppCost => 'Кошт дадатка';

  @override
  String get paymentEnterValidAmount => 'Калі ласка, введзіце правільную суму';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Калі ласка, введзіце суму больш за 0';

  @override
  String get paymentPlan => 'План плацежа';

  @override
  String get paymentNoneSelected => 'Ніхто не выбраны';

  @override
  String get aiGenPleaseEnterDescription => 'Калі ласка, введзіце апісанне для вашага дадатка';

  @override
  String get aiGenCreatingAppIcon => 'Стварэнне значка дадатка...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Адбылася памылка: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Дадатак створаны ўдала!';

  @override
  String get aiGenFailedToCreateApp => 'Не вдалося стварыць дадатак';

  @override
  String get aiGenErrorWhileCreatingApp => 'Адбылася памылка пры стварэнні дадатка';

  @override
  String get aiGenFailedToGenerateApp => 'Не вдалося стварыць дадатак. Спрабуйце яшчэ раз.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Не вдалося перастварыць значок';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Калі ласка, спачатку стварыце дадатак';

  @override
  String get nextButton => 'Далей';

  @override
  String get connectOmiDevice => 'Падключыць прыстасаванне Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Вы мяняеце ваш Unlimite план на $title. Вы ўпэўнены, што хочаце адкіць?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Паўпшасцэнне заплянавана! Ваш штомесячны план працягваецца да канца вашага біліцейнага перыёда, затым аўтаматычна мяняецца на річны.';

  @override
  String get couldNotSchedulePlanChange => 'Не вдалося заплянаваць смену плана. Спрабуйце яшчэ раз.';

  @override
  String get subscriptionReactivatedDefault =>
      'Ваша подпіска была перазапушчана! Без плацежа зараз - вы будзеце выставлены рахунак у канцы вашага цяперашняга перыёда.';

  @override
  String get subscriptionSuccessfulCharged => 'Подпіска ўспяшнай! Вам вылічаны плата за новы біліцейны перыёд.';

  @override
  String get couldNotProcessSubscription => 'Не вдалося апрацаваць подпіску. Спрабуйце яшчэ раз.';

  @override
  String get couldNotLaunchUpgradePage => 'Не вдалося запусціць старонку паўпшасцэння. Спрабуйце яшчэ раз.';

  @override
  String get transcriptionJsonPlaceholder => 'Вставіце вашу кагфіўрацыю JSON тут...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Памылка пры адкрыцці вызначальніка файлаў: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Памылка: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Разьмовы злучаны ўдала';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count разьмовы злучаны ўдала';
  }

  @override
  String get actionItemReminderTitle => 'Нагадаванне Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName адключаны';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Калі ласка, перазлучыцеся, каб пацягнуць ваш $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Уваход';

  @override
  String get onboardingYourName => 'Ваша назва';

  @override
  String get onboardingLanguage => 'Мова';

  @override
  String get onboardingPermissions => 'Дозволы';

  @override
  String get onboardingComplete => 'Завяршыць';

  @override
  String get onboardingWelcomeToOmi => 'Вітаем у Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Расказыце нам пра сябе';

  @override
  String get onboardingChooseYourPreference => 'Выберыце ваш перавагу';

  @override
  String get onboardingGrantRequiredAccess => 'Прадаць патрэбны доступ';

  @override
  String get onboardingYoureAllSet => 'Вы ўсё гатовы';

  @override
  String get searchTranscriptOrSummary => 'Пошук транскрыпцыі або рэзюмэ...';

  @override
  String get myGoal => 'Моя мета';

  @override
  String get appNotAvailable => 'Ой! Здаецца, дадатак, якi вы шукаеце, недаступны.';

  @override
  String get failedToConnectTodoist => 'Не вдалося падключыцца да Todoist';

  @override
  String get failedToConnectAsana => 'Не вдалося падключыцца да Asana';

  @override
  String get failedToConnectGoogleTasks => 'Не вдалося падключыцца да Google Tasks';

  @override
  String get failedToConnectClickUp => 'Не вдалося падключыцца да ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Не вдалося падключыцца да $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Успяшна падключаны да Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Не вдалося падключыцца да Todoist. Спрабуйце яшчэ раз.';

  @override
  String get successfullyConnectedAsana => 'Успяшна падключаны да Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Не вдалося падключыцца да Asana. Спрабуйце яшчэ раз.';

  @override
  String get successfullyConnectedGoogleTasks => 'Успяшна падключаны да Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Не вдалося падключыцца да Google Tasks. Спрабуйце яшчэ раз.';

  @override
  String get successfullyConnectedClickUp => 'Успяшна падключаны да ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Не вдалося падключыцца да ClickUp. Спрабуйце яшчэ раз.';

  @override
  String get successfullyConnectedNotion => 'Успяшна падключаны да Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Не вдалося абнавіць статус пакучэння Notion.';

  @override
  String get successfullyConnectedGoogle => 'Успяшна падключаны да Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Не вдалося абнавіць статус пакучэння Google.';

  @override
  String get successfullyConnectedWhoop => 'Успяшна падключаны да Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Не вдалося абнавіць статус пакучэння Whoop.';

  @override
  String get successfullyConnectedGitHub => 'Успяшна падключаны да GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Не вдалося абнавіць статус пакучэння GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'Не вдалося ўвайсці праз Google, спрабуйце яшчэ раз.';

  @override
  String get authenticationFailed => 'Аўтэнтыфікацыя не атрымалася. Спрабуйце яшчэ раз.';

  @override
  String get authFailedToSignInWithApple => 'Не вдалося ўвайсці праз Apple, спрабуйце яшчэ раз.';

  @override
  String get authFailedToRetrieveToken => 'Не вдалося атрымаць токен firebase, спрабуйце яшчэ раз.';

  @override
  String get authUnexpectedErrorFirebase => 'Неўдаўдаўёнауўхіба пры ўваходзе, памылка Firebase, спрабуйце яшчэ раз.';

  @override
  String get authUnexpectedError => 'Неўдаўдаўёнауўхіба пры ўваходзе, спрабуйце яшчэ раз';

  @override
  String get authFailedToLinkGoogle => 'Не вдалося звязаць з Google, спрабуйце яшчэ раз.';

  @override
  String get authFailedToLinkApple => 'Не вдалося звязаць з Apple, спрабуйце яшчэ раз.';

  @override
  String get onboardingBluetoothRequired => 'Дозвол Bluetooth патрэбны для падключэння да вашага прыстасавання.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Дозвол Bluetooth адмоўлены. Калі ласка, разрэшыце дозвол у Параметрах системы.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Статус дозволу Bluetooth: $status. Калі ласка, праверыце Параметры системы.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Не вдалося праверыць дозвол Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Дозвол на ведаміяць адмоўлены. Калі ласка, разрэшыце дозвол у Параметрах системы.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Дозвол на ведаміяць адмоўлены. Калі ласка, разрэшыце дозвол у Параметрах системы > Ведаміяці.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Статус дозволу ведаміяці: $status. Калі ласка, праверыце Параметры системы.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Не вдалося праверыць дозвол ведаміяці: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Калі ласка, разрэшыце дозвол на месцазнаходжанне ў Параметрах > Прыватнасць і бяспека > Сервісы месцазнаходжання';

  @override
  String get onboardingMicrophoneRequired => 'Дозвол мікрофона патрэбны для запісу.';

  @override
  String get onboardingMicrophoneDenied =>
      'Дозвол мікрофона адмоўлены. Калі ласка, разрэшыце дозвол у Параметрах системы > Прыватнасць і бяспека > Мікрофон.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Статус дозволу мікрофона: $status. Калі ласка, праверыце Параметры системы.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Не вдалося праверыць дозвол мікрофона: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Дозвол на захоп экрана патрэбны для запісу сістэмнага аўдыё.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Дозвол на захоп экрана адмоўлены. Калі ласка, разрэшыце дозвол у Параметрах системы > Прыватнасць і бяспека > Запіс экрана.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Статус дозволу захопу экрана: $status. Калі ласка, праверыце Параметры системы.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Не вдалося праверыць дозвол захопу экрана: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'Дозвол на даступнасць патрэбны для вызначэння сустрэч браўзара.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Статус дозволу даступнасці: $status. Калі ласка, праверыце Параметры системы.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Не вдалося праверыць дозвол даступнасці: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Захоп камеры недаступны на гэтай платформе';

  @override
  String get msgCameraPermissionDenied => 'Дозвол камеры адмоўлены. Калі ласка, разрэшыце доступ да камеры';

  @override
  String msgCameraAccessError(String error) {
    return 'Памылка пры доступе да камеры: $error';
  }

  @override
  String get msgPhotoError => 'Памылка пры фатаграфіцы. Спрабуйце яшчэ раз.';

  @override
  String get msgMaxImagesLimit => 'Вы можаце выбраць не больш за 4 выявы';

  @override
  String msgFilePickerError(String error) {
    return 'Памылка пры адкрыцці вызначальніка файлаў: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Памылка пры выбары выяў: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Дозвол на фотаграфіі адмоўлены. Калі ласка, разрэшыце доступ да фотаграфій, каб выбраць выявы';

  @override
  String get msgSelectImagesGenericError => 'Памылка пры выбары выяў. Спрабуйце яшчэ раз.';

  @override
  String get msgMaxFilesLimit => 'Вы можаце выбраць не больш за 4 файлы';

  @override
  String msgSelectFilesError(String error) {
    return 'Памылка пры выбары файлаў: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Памылка пры выбары файлаў. Спрабуйце яшчэ раз.';

  @override
  String get msgUploadFileFailed => 'Не вдалося загрузіць файл, спрабуйце яшчэ раз позней';

  @override
  String get msgReadingMemories => 'Чытанне вашых успамінаў...';

  @override
  String get msgLearningMemories => 'Навучанне ад вашых успамінаў...';

  @override
  String get msgUploadAttachedFileFailed => 'Не вдалося загрузіць прыкладзены файл.';

  @override
  String captureRecordingError(String error) {
    return 'Адбылася памылка пры запісе: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Запіс прыпынены: $reason. Вам можа потрабавацца перападключыць знешнія дысплеі або перастварыць запіс.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Дозвол мікрофона патрэбны';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Разрэшыце дозвол мікрофона ў Параметрах системы';

  @override
  String get captureScreenRecordingPermissionRequired => 'Дозвол на запіс экрана патрэбны';

  @override
  String get captureDisplayDetectionFailed => 'Вызначэнне дысплея не атрымалася. Запіс прыпынены.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Недапушчальны URL-адрас вэбхука байтаў аўдыё';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl =>
      'Недапушчальны URL-адрас вэбхука транскрыпцыі рэального часу';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Недапушчальны URL-адрас вэбхука стварэння разьмовы';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Недапушчальны URL-адрас вэбхука рэзюмэ дня';

  @override
  String get devModeSettingsSaved => 'Параметры захаваны!';

  @override
  String get voiceFailedToTranscribe => 'Не вдалося пераскладаць аўдыё';

  @override
  String get locationPermissionRequired => 'Дозвол на месцазнаходжанне патрэбны';

  @override
  String get locationPermissionContent =>
      'Хутка пераноска патрэбуе дозвол на месцазнаходжанне, каб прапаноўваць WiFi злучэнне. Калі ласка, разрэшыце дозвол на месцазнаходжанне, каб адкіць.';

  @override
  String get pdfTranscriptExport => 'Экспорт транскрыпцыі';

  @override
  String get pdfConversationExport => 'Экспорт разьмовы';

  @override
  String pdfTitleLabel(String title) {
    return 'Заголовак: $title';
  }

  @override
  String get conversationNewIndicator => 'Новая 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count выяў';
  }

  @override
  String get mergingStatus => 'Злучанне...';

  @override
  String timeSecsSingular(int count) {
    return '$count сек';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count сек';
  }

  @override
  String timeMinSingular(int count) {
    return '$count хвіл';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count хвіл';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins хвіл $secs сек';
  }

  @override
  String timeHourSingular(int count) {
    return '$count гадзіна';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count гадзін';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours гадзін $mins хвіл';
  }

  @override
  String timeDaySingular(int count) {
    return '$count дзень';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count дзён';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days дзён $hours гадзін';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countс';
  }

  @override
  String timeCompactMins(int count) {
    return '$countх';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsх $secsс';
  }

  @override
  String timeCompactHours(int count) {
    return '$countг';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursг $minsх';
  }

  @override
  String get moveToFolder => 'Перамясціць у папку';

  @override
  String get noFoldersAvailable => 'Папкі не даступны';

  @override
  String get newFolder => 'Новая папка';

  @override
  String get color => 'Колер';

  @override
  String get waitingForDevice => 'Чаканне прыстасавання...';

  @override
  String get saySomething => 'Расказыце што-небудзь...';

  @override
  String get initialisingSystemAudio => 'Ініцыялізацыя сістэмнага аўдыё';

  @override
  String get stopRecording => 'Спыніць запіс';

  @override
  String get continueRecording => 'Адновіць запіс';

  @override
  String get initialisingRecorder => 'Ініцыялізацыя рэкордэра';

  @override
  String get pauseRecording => 'Паўзаваць запіс';

  @override
  String get resumeRecording => 'Адновіць запіс';

  @override
  String get noDailyRecapsYet => 'Штодзённых рэзюмэ яшчэ нема';

  @override
  String get dailyRecapsDescription => 'Ваша штодзённыя рэзюмэ з\'явяцца тут пасля стварэння';

  @override
  String get chooseTransferMethod => 'Выберыце спосаб пераносы';

  @override
  String get fastTransferSpeed => '~150 KB/s праз WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Вялікі часовы разрыў выяўлены ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Вялікі часовы разрывы выяўлены ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Прыстасаванне не падтрымлівае WiFi синхранізацыю, мяняем на Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health недаступна на гэтым прыстасаванні';

  @override
  String get downloadAudio => 'Загрузіць аўдыё';

  @override
  String get audioDownloadSuccess => 'Аўдыё загружана ўдала';

  @override
  String get audioDownloadFailed => 'Не вдалося загрузіць аўдыё';

  @override
  String get downloadingAudio => 'Загрузка аўдыё...';

  @override
  String get shareAudio => 'Абагуліць аўдыё';

  @override
  String get preparingAudio => 'Падрыхтоўка аўдыё';

  @override
  String get gettingAudioFiles => 'Атрыманне файлаў аўдыё...';

  @override
  String get downloadingAudioProgress => 'Загрузка аўдыё';

  @override
  String get processingAudio => 'Апрацоўка аўдыё';

  @override
  String get combiningAudioFiles => 'Комбініраванне файлаў аўдыё...';

  @override
  String get audioReady => 'Аўдыё гатова';

  @override
  String get openingShareSheet => 'Адкрыццё аркуша абагулення...';

  @override
  String get audioShareFailed => 'Абагуленне не атрымалася';

  @override
  String get dailyRecaps => 'Штодзённыя рэзюмэ';

  @override
  String get removeFilter => 'Прыбраць фільтр';

  @override
  String get categoryConversationAnalysis => 'Аналіз разьмовы';

  @override
  String get categoryHealth => 'Здаровье';

  @override
  String get categoryEducation => 'Адукацыя';

  @override
  String get categoryCommunication => 'Камунікацыя';

  @override
  String get categoryEmotionalSupport => 'Эмацыянальная падтрымка';

  @override
  String get categoryProductivity => 'Прадуктыўнасць';

  @override
  String get categoryEntertainment => 'Забава';

  @override
  String get categoryFinancial => 'Фінансавы';

  @override
  String get categoryTravel => 'Падарожжы';

  @override
  String get categorySafety => 'Бяспека';

  @override
  String get categoryShopping => 'Пакупкі';

  @override
  String get categorySocial => 'Сацыяльны';

  @override
  String get categoryNews => 'Навіны';

  @override
  String get categoryUtilities => 'Утыліты';

  @override
  String get categoryOther => 'Іншае';

  @override
  String get capabilityChat => 'Чат';

  @override
  String get capabilityConversations => 'Разьмовы';

  @override
  String get capabilityExternalIntegration => 'Знешняя інтэграцыя';

  @override
  String get capabilityNotification => 'Ведаміяць';

  @override
  String get triggerAudioBytes => 'Байты аўдыё';

  @override
  String get triggerConversationCreation => 'Стварэнне разьмовы';

  @override
  String get triggerTranscriptProcessed => 'Транскрыпцыя апрацавана';

  @override
  String get actionCreateConversations => 'Стварыць разьмовы';

  @override
  String get actionCreateMemories => 'Стварыць успамніны';

  @override
  String get actionReadConversations => 'Чытаць разьмовы';

  @override
  String get actionReadMemories => 'Чытаць успамніны';

  @override
  String get actionReadTasks => 'Чытаць завданні';

  @override
  String get scopeUserName => 'Імя карыстальніка';

  @override
  String get scopeUserFacts => 'Факты карыстальніка';

  @override
  String get scopeUserConversations => 'Разьмовы карыстальніка';

  @override
  String get scopeUserChat => 'Чат карыстальніка';

  @override
  String get capabilitySummary => 'Рэзюмэ';

  @override
  String get capabilityFeatured => 'Асноўны';

  @override
  String get capabilityTasks => 'Завданні';

  @override
  String get capabilityIntegrations => 'Інтэграцыі';

  @override
  String get categoryProductivityLifestyle => 'Прадуктыўнасць і стыль жыцця';

  @override
  String get categorySocialEntertainment => 'Сацыяльны і забава';

  @override
  String get categoryProductivityTools => 'Прадуктыўнасць і інструменты';

  @override
  String get categoryPersonalWellness => 'Асобiсты жыццё і ўзаёмаальнасць';

  @override
  String get rating => 'Рэйтынг';

  @override
  String get categories => 'Катэгорыi';

  @override
  String get sortBy => 'Сартаванне';

  @override
  String get highestRating => 'Найвышэйшы рэйтынг';

  @override
  String get lowestRating => 'Найніжэйшы рэйтынг';

  @override
  String get resetFilters => 'Очысціць фільтры';

  @override
  String get applyFilters => 'Прыменіць фільтры';

  @override
  String get mostInstalls => 'Найбольш устаноўак';

  @override
  String get couldNotOpenUrl => 'Не ўдалося адкрыць URL. Спрабуйце яшчэ раз.';

  @override
  String get newTask => 'Новая задача';

  @override
  String get viewAll => 'Паглядзець ўсё';

  @override
  String get addTask => 'Дадаць задачу';

  @override
  String get addMcpServer => 'Дадаць MCP-сервер';

  @override
  String get connectExternalAiTools => 'Падключыць внешнія інструменты AI';

  @override
  String get mcpServerUrl => 'URL MCP-сервера';

  @override
  String mcpServerConnected(int count) {
    return 'Усё $count інструментаў успяшна падключаны';
  }

  @override
  String get mcpConnectionFailed => 'Не ўдалося падключыцца да MCP-сервера';

  @override
  String get authorizingMcpServer => 'Аўтарызацыя...';

  @override
  String get whereDidYouHearAboutOmi => 'Як вы пра нас даведаліся?';

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
  String get friendWordOfMouth => 'Ад друга';

  @override
  String get otherSource => 'Іншае';

  @override
  String get pleaseSpecify => 'Калі ласка, уточніце';

  @override
  String get event => 'Мерапрыемства';

  @override
  String get coworker => '칈лег';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Аўдыё-файл недаступны для прайграння';

  @override
  String get audioPlaybackFailed => 'Не ўдалося ўключыць аўдыё. Файл можа быць пашкоджаны ці адсутнічаць.';

  @override
  String get connectionGuide => 'Кіраўнік па падключэнню';

  @override
  String get iveDoneThis => 'Я гэта зрабіў';

  @override
  String get pairNewDevice => 'Спарыць новае прыстасаванне';

  @override
  String get dontSeeYourDevice => 'Не бачыце свайго прыстасавання?';

  @override
  String get reportAnIssue => 'Паведаміць аб праблеме';

  @override
  String get pairingTitleOmi => 'Уключыце Omi';

  @override
  String get pairingDescOmi => 'Прыціскайце і трымайце прыстасаванне да вібрацыі.';

  @override
  String get pairingTitleOmiDevkit => 'Пакладзіце Omi DevKit у рэжым спарыпання';

  @override
  String get pairingDescOmiDevkit =>
      'Натысніце кнопку адзін раз для ўключэння. Калі рэжым спарыпання актыўны, LED мігацьме фіялетавым.';

  @override
  String get pairingTitleOmiGlass => 'Уключыце Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Уключыце, натыснуўшы бакавую кнопку на 3 секунды.';

  @override
  String get pairingTitlePlaudNote => 'Пакладзіце Plaud Note у рэжым спарыпання';

  @override
  String get pairingDescPlaudNote =>
      'Прыціскайце і трымайце бакавую кнопку на 2 секунды. Чырвоны LED мігацьме, калі гатовы.';

  @override
  String get pairingTitleBee => 'Пакладзіце Bee у рэжым спарыпання';

  @override
  String get pairingDescBee => 'Натысніце кнопку 5 разоў без пазы. Індыкатар пачне мігаць сінім і зялёным.';

  @override
  String get pairingTitleLimitless => 'Пакладзіце Limitless у рэжым спарыпання';

  @override
  String get pairingDescLimitless =>
      'Калі любы індыкатар бачны, натысніце адзін раз, потым прыціскайце кнопку да ружоватага сцвятлення і адпусціце.';

  @override
  String get pairingTitleFriendPendant => 'Пакладзіце Friend Pendant у рэжым спарыпання';

  @override
  String get pairingDescFriendPendant =>
      'Натысніце кнопку на медальёне для ўключэння. Ён аўтаматычна ўвойде у рэжым спарыпання.';

  @override
  String get pairingTitleFieldy => 'Пакладзіце Fieldy у рэжым спарыпання';

  @override
  String get pairingDescFieldy => 'Прыціскайце і трымайце прыстасаванне да з\'яўлення сцвятла.';

  @override
  String get pairingTitleAppleWatch => 'Падключыце Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Устанавіце і адкрыйце прыкладанне Omi на сваім Apple Watch, потым натысніце Connect у прыкладанні.';

  @override
  String get pairingTitleNeoOne => 'Пакладзіце Neo One у рэжым спарыпання';

  @override
  String get pairingDescNeoOne =>
      'Прыціскайце і трымайце кнопку ўключэння, пакуль LED не пачне мігаць. Прыстасаванне будзе адкрыта.';

  @override
  String get downloadingFromDevice => 'Загрузка з прыстасавання';

  @override
  String get reconnectingToInternet => 'Перасяданне да Інтэрнету...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Загрузка $current з $total';
  }

  @override
  String get processingOnServer => 'Апрацоўка на сервері...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Апрацоўка... $current/$total сегментаў';
  }

  @override
  String get processedStatus => 'Апрацавана';

  @override
  String get corruptedStatus => 'Пашкоджана';

  @override
  String nPending(int count) {
    return '$count чакаючых';
  }

  @override
  String nProcessed(int count) {
    return '$count апрацаваных';
  }

  @override
  String get synced => 'Сінхранізавана';

  @override
  String get noPendingRecordings => 'Няма чакаючых запісаў';

  @override
  String get noProcessedRecordings => 'Пакуль няма апрацаваных запісаў';

  @override
  String get pending => 'Чакаючыя';

  @override
  String whatsNewInVersion(String version) {
    return 'Што новага ў версіі $version';
  }

  @override
  String get addToYourTaskList => 'Дадаць у спіс задач?';

  @override
  String get failedToCreateShareLink => 'Не ўдалося стварыць спасылку на абагуленне';

  @override
  String get deleteGoal => 'Выдаліць мету';

  @override
  String get deviceUpToDate => 'Ваша прыстасаванне заўсёды актуальна';

  @override
  String get wifiConfiguration => 'Канфігурацыя WiFi';

  @override
  String get wifiConfigurationSubtitle =>
      'Уведзіце свае ўліку дадаткі WiFi, каб дазволіць прыстасаванню загруліцца прошыўку.';

  @override
  String get networkNameSsid => 'Назва сеткі (SSID)';

  @override
  String get enterWifiNetworkName => 'Уведзіце назву сеткі WiFi';

  @override
  String get enterWifiPassword => 'Уведзіце пароль WiFi';

  @override
  String get appIconLabel => 'Значок прыкладання';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Вось што я пра вас ведаю';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Гэта карта абнаўляецца, калі Omi вучыцца з вашых размоў.';

  @override
  String get apiEnvironment => 'Окружэнне API';

  @override
  String get apiEnvironmentDescription => 'Выберыце, да якога бэкэнда падключыцца';

  @override
  String get production => 'Прадукцыйна';

  @override
  String get staging => 'Этап';

  @override
  String get switchRequiresRestart => 'Пераключэнне патрабуе перазагрузкі прыкладання';

  @override
  String get switchApiConfirmTitle => 'Пераключыць окружэнне API';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Пераключыцца на $environment? Вам трэба буде закрыць і заноў адкрыць прыкладанне.';
  }

  @override
  String get switchAndRestart => 'Пераключыцца';

  @override
  String get stagingDisclaimer =>
      'Этап можа мець ошыбкі, непаслядоўную прадукцыйнасць і стрататы дадзеных. Ужывайце толькі для тэставання.';

  @override
  String get apiEnvSavedRestartRequired => 'Захавана. Закрыйце і перападкрыйце прыкладанне.';

  @override
  String get shared => 'Абагул.';

  @override
  String get onlyYouCanSeeConversation => 'Толькі вы можаце бачыць гэты размову';

  @override
  String get anyoneWithLinkCanView => 'Любы са спасылкай можа праглядаць';

  @override
  String get tasksCleanTodayTitle => 'Очысціць сённяшнія задачы?';

  @override
  String get tasksCleanTodayMessage => 'Гэта толькі прыберыце тэрміны';

  @override
  String get tasksOverdue => 'Прострочаныя';

  @override
  String get phoneCallsWithOmi => 'Тэлефонныя вызовы з Omi';

  @override
  String get phoneCallsSubtitle => 'Делайце вызовы з трансляцыяй у рэжыме рэальнага часу';

  @override
  String get phoneSetupStep1Title => 'Параўнайце свой тэлефонны нумар';

  @override
  String get phoneSetupStep1Subtitle => 'Мы вам пазвоним, каб растацьь яго';

  @override
  String get phoneSetupStep2Title => 'Уведзіце код аўтэнтыфікацыі';

  @override
  String get phoneSetupStep2Subtitle => 'Кароткі код, які вы напішаце на вызове';

  @override
  String get phoneSetupStep3Title => 'Пачніце звязвацьсяе са сваімі кантактамі';

  @override
  String get phoneSetupStep3Subtitle => 'З убудаванай трансляцыяй у рэжыме рэальнага часу';

  @override
  String get phoneGetStarted => 'Пачаць';

  @override
  String get callRecordingConsentDisclaimer => 'Запіс вызова можа патрабаваць зваду ў вашай юрысдыкцыі';

  @override
  String get enterYourNumber => 'Уведзіце свой нумар';

  @override
  String get phoneNumberCallerIdHint => 'Пасля праверкі гэта стане вашым ідэнтыфікатарам абонента';

  @override
  String get phoneNumberHint => 'Тэлефонны нумар';

  @override
  String get failedToStartVerification => 'Не ўдалося пачаць аўтэнтыфікацыю';

  @override
  String get phoneContinue => '働き';

  @override
  String get verifyYourNumber => 'Параўнайце свой нумар';

  @override
  String get answerTheCallFrom => 'Адкажыце на вызоў ад';

  @override
  String get onTheCallEnterThisCode => 'На вызове уведзіце гэты код';

  @override
  String get followTheVoiceInstructions => 'Следуйце голасавым інструкцыям';

  @override
  String get statusCalling => 'Звязванне...';

  @override
  String get statusCallInProgress => 'Вызоў у прагрэсе';

  @override
  String get statusVerifiedLabel => 'Параўнана';

  @override
  String get statusCallMissed => 'Вызоў ддатак';

  @override
  String get statusTimedOut => 'Утэчка часу';

  @override
  String get phoneTryAgain => 'Спрабуйце яшчэ раз';

  @override
  String get phonePageTitle => 'Тэлефон';

  @override
  String get phoneContactsTab => 'Кантакты';

  @override
  String get phoneKeypadTab => 'Клавіятура';

  @override
  String get grantContactsAccess => 'Дазволіць доступ да вашых кантактаў';

  @override
  String get phoneAllow => 'Дазволіць';

  @override
  String get phoneSearchHint => 'Пошук';

  @override
  String get phoneNoContactsFound => 'Кантакты не знойдзены';

  @override
  String get phoneEnterNumber => 'Уведзіце нумар';

  @override
  String get failedToStartCall => 'Не ўдалося пачаць вызоў';

  @override
  String get callStateConnecting => 'Па\'яданне...';

  @override
  String get callStateRinging => 'Звянелла...';

  @override
  String get callStateEnded => 'Вызоў завершаны';

  @override
  String get callStateFailed => 'Вызоў сабрал';

  @override
  String get transcriptPlaceholder => 'Трансляцыя з\'явіцца тут...';

  @override
  String get phoneUnmute => 'Ўвічыўіць гук';

  @override
  String get phoneMute => 'Адмяніць гук';

  @override
  String get phoneSpeaker => 'Спікер';

  @override
  String get phoneEndCall => 'Завершыць';

  @override
  String get phoneCallSettingsTitle => 'Параметры тэлефонных вызваў';

  @override
  String get showPhoneCallButtonTitle => 'Паказаць кнопку тэлефоннага выкліку';

  @override
  String get showPhoneCallButtonDesc => 'Адлюстраваць кнопку тэлефоннага выкліку на галоўным экране';

  @override
  String get yourVerifiedNumbers => 'Ваш параўныя нумары';

  @override
  String get verifiedNumbersDescription => 'Калі вы звяжэцца з кім-небудзь, яны паўідяць гэты нумар на сваім тэлефоне';

  @override
  String get noVerifiedNumbers => 'Няма параўныш нумараў';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Выдаліць $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Вам трэба будзе яшчэ раз параўнаць, каб дзвоніць';

  @override
  String get phoneDeleteButton => 'Выдаліць';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Параўнана $minutesм назад';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Параўнана $hoursг назад';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Параўнана $daysд назад';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Параўнана на $date';
  }

  @override
  String get verifiedFallback => 'Параўнана';

  @override
  String get callAlreadyInProgress => 'Вызоў ужо ў прагрэсе';

  @override
  String get failedToGetCallToken => 'Не ўдалося атрымаць токен вызова. Спачатку параўнайце свой тэлефонны нумар.';

  @override
  String get failedToInitializeCallService => 'Не ўдалося ініцыялізаваць сэрвіс вызваў';

  @override
  String get speakerLabelYou => 'Вы';

  @override
  String get speakerLabelUnknown => 'Невядомо';

  @override
  String get showDailyScoreOnHomepage => 'Паказаць папялёнак дня на хаме';

  @override
  String get showTasksOnHomepage => 'Паказаць задачы на хаме';

  @override
  String get phoneCallsUnlimitedOnly => 'Тэлефонныя вызовы праз Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Звяжэцца праз Omi і атрымайце трансляцыю у рэжыме рэальнага часу, аўтаматычныя аніяцыі і іншае. Даступна толькі для падпісчыкаў плана Unlimited.';

  @override
  String get phoneCallsUpsellFeature1 => 'Трансляцыя кожнага вызова у рэжыме рэальнага часу';

  @override
  String get phoneCallsUpsellFeature2 => 'Аўтаматычныя аніяцыі вызваў і элементы дзеяння';

  @override
  String get phoneCallsUpsellFeature3 => 'Адпраўляючы яны бачаць вашы сапраўдны нумар, а не выпадковы';

  @override
  String get phoneCallsUpsellFeature4 => 'Ваш вызовы астаюцца прыватнымі і бяспечнымі';

  @override
  String get phoneCallsUpgradeButton => 'Абнавіць на Unlimited';

  @override
  String get phoneCallsMaybeLater => 'Можа быць, пазней';

  @override
  String get deleteSynced => 'Выдаліць сінхранізавана';

  @override
  String get deleteSyncedFiles => 'Выдаліць сінхранізаваныя запісы';

  @override
  String get deleteSyncedFilesMessage => 'Гэтыя запісы ужо сінхранізаваны з вашым тэлефонам. Гэта нельга адмяніць.';

  @override
  String get syncedFilesDeleted => 'Сінхранізаваныя запісы выдаленыя';

  @override
  String get deletePending => 'Выдаліць чакаючыя';

  @override
  String get deletePendingFiles => 'Выдаліць чакаючыя запісы';

  @override
  String get deletePendingFilesWarning =>
      'Гэтыя запісы НЕ сінхранізаваны з вашым тэлефонам і будуць назаўсёды страчаны. Гэта нельга адмяніць.';

  @override
  String get pendingFilesDeleted => 'Чакаючыя запісы выдаленыя';

  @override
  String get deleteAllFiles => 'Выдаліць усе запісы';

  @override
  String get deleteAll => 'Выдаліць ўсё';

  @override
  String get deleteAllFilesWarning =>
      'Гэта выдаліць як сінхранізаваныя, так і чакаючыя запісы. Чакаючыя запісы НЕ сінхранізаваны і будуць назаўсёды страчаны. Гэта нельга адмяніць.';

  @override
  String get allFilesDeleted => 'Усе запісы выдаленыя';

  @override
  String nFiles(int count) {
    return '$count запісаў';
  }

  @override
  String get manageStorage => 'Кіраваць сховішчам';

  @override
  String get safelyBackedUp => 'Бяспечна зарэзервавана на вашым тэлефоне';

  @override
  String get notYetSynced => 'Яшчэ не сінхранізавана на вашым тэлефоне';

  @override
  String get clearAll => 'Очысціць ўсё';

  @override
  String get phoneKeypad => 'Клавіятура';

  @override
  String get phoneHideKeypad => 'Хаваць клавіятуру';

  @override
  String get fairUsePolicy => 'Справядлівы ўжыванне';

  @override
  String get fairUseLoadError => 'Не ўдалося загруліць статус справядлівага ўжывання. Спрабуйце яшчэ раз.';

  @override
  String get fairUseStatusNormal => 'Ваше ўжыванне ў нармальных límach.';

  @override
  String get fairUseStageNormal => 'Нармальны';

  @override
  String get fairUseStageWarning => 'Папярэджанне';

  @override
  String get fairUseStageThrottle => 'Дроселявана';

  @override
  String get fairUseStageRestrict => 'Абмежавана';

  @override
  String get fairUseSpeechUsage => 'Ужыванне мовы';

  @override
  String get fairUseToday => 'Сёння';

  @override
  String get fairUse3Day => '3-дневны прокат';

  @override
  String get fairUseWeekly => 'Еженедельны прокат';

  @override
  String get fairUseAboutTitle => 'Аб справядлівым ўжыванні';

  @override
  String get fairUseAboutBody =>
      'Omi прызначаны для асобных размоў, сустрэч і жывых узаёмадзеянняў. Ужыванне вымяраецца рэальным часом мовы, а не часам злучэння. Калі ўжыванне значна перавышае нармальныя мадэлі для ненасобнага контэнта, могуць быць зробленыя карэкцыі.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef скапіравана';
  }

  @override
  String get fairUseDailyTranscription => 'Щаднённая трансляцыя';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'Лімітанне дзённай трансляцыі дасягнута';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Перазагружаецца $time';
  }

  @override
  String get transcriptionPaused => 'Запіс, перасяданне';

  @override
  String get transcriptionPausedReconnecting => 'Запіс усё яшчэ працяглідаецца — перасяданне да трансляцыі...';

  @override
  String fairUseBannerStatus(String status) {
    return 'Справядлівы ўжыванне: $status';
  }

  @override
  String get improveConnectionTitle => 'Палепшыць злучэнне';

  @override
  String get improveConnectionContent =>
      'Мы палепшылі, як Omi астается злучаным з вашым прыстасаваннем. Каб актывіраваць гэта, перайдзіце на старонку Device Info, натысніце \"Адключыць прыстасаванне\", а потым яшчэ раз спарыце свая прыстасаванне.';

  @override
  String get improveConnectionAction => 'Зразумелі';

  @override
  String clockSkewWarning(int minutes) {
    return 'Годзiнник вашага прыстасавання збіты прыблізна на $minutes мін. Праверьце параметры даты і часу.';
  }

  @override
  String get omisStorage => 'Сховішча Omi';

  @override
  String get phoneStorage => 'Сховішча тэлефона';

  @override
  String get cloudStorage => 'Облачнае сховішча';

  @override
  String get howSyncingWorks => 'Як працуе сінхранізацыя';

  @override
  String get noSyncedRecordings => 'Пакуль няма сінхранізаваных запісаў';

  @override
  String get recordingsSyncAutomatically => 'Запісы сінхранізуюцца аўтаматычна — дзеянне не патрэбна.';

  @override
  String get filesDownloadedUploadedNextTime => 'Файлы, ужо загружаныя, будуць загружаны наступны раз.';

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
  String get tapToView => 'Натысніце, каб праглядаць';

  @override
  String get syncFailed => 'Сінхранізацыя не ўдалася';

  @override
  String get keepSyncing => 'Прадолжыць сінхранізацыю';

  @override
  String get cancelSyncQuestion => 'Адмяніць сінхранізацыю?';

  @override
  String get omisStorageDesc =>
      'Калі вашы Omi не злучаны з вашым тэлефонам, ён захоўвае аўдыё адзінаў у абрана пам\'яці прыстасавання. Вы ніколі не страчаеце запіс.';

  @override
  String get phoneStorageDesc =>
      'Калі Omi яшчэ раз злучаюцца, запісы аўтаматычна переносяцца на вашы тэлефон як часовае адзінаў да загрузкі.';

  @override
  String get cloudStorageDesc =>
      'Пасля загрузкі ваш запісы апрацоўваюцца і трансляцуюцца. Размовы будуць даступны у велічыні хвіліны.';

  @override
  String get tipKeepPhoneNearby => 'Трымайце тэлефон побач для хутшыбшай сінхранізацыі';

  @override
  String get tipStableInternet => 'Стабільны Інтэрнэт паскарае загрузку ў облако';

  @override
  String get tipAutoSync => 'Запісы сінхранізуюцца аўтаматычна';

  @override
  String get storageSection => 'СХОВІШЧА';

  @override
  String get permissions => 'Дазволы';

  @override
  String get permissionEnabled => 'Уключана';

  @override
  String get permissionEnable => 'Уключыць';

  @override
  String get permissionsPageDescription =>
      'Гэтыя дазволы важны для таго, как працуе Omi. Яны дазваляюць ключавыя функцыі, такія як апавяшчэнні, месцазнаходжанні і захоп аўдыё.';

  @override
  String get permissionsRequiredDescription =>
      'Omi патрабуе некалькі дазволаў для нармальнай работы. Калі ласка, дайце іх, каб прадолжыць.';

  @override
  String get permissionsSetupTitle => 'Атрымайце найлепшыя адносіны';

  @override
  String get permissionsSetupDescription => 'Уключыце некалькі дазволаў, каб Omi мог адкрыць свайна магію.';

  @override
  String get permissionsChangeAnytime => 'Вы можаце змяніць гэтыя дазволы ў любы час у Параметрах > Дазволы';

  @override
  String get location => 'Месцазнаходжанне';

  @override
  String get microphone => 'Мікрофон';

  @override
  String get whyAreYouCanceling => 'Чаму вы адмяняеце?';

  @override
  String get cancelReasonSubtitle => 'Вы можаце мне сказаць, чаму вы адыходзіце?';

  @override
  String get cancelReasonTooExpensive => 'Занадта дорга';

  @override
  String get cancelReasonNotUsing => 'Не ўжываюць дастаткова';

  @override
  String get cancelReasonMissingFeatures => 'Адсутнічаюць функцыі';

  @override
  String get cancelReasonAudioQuality => 'Якасць аўдыё/трансляцыі';

  @override
  String get cancelReasonBatteryDrain => 'Праблемы сцяканнем батарэі';

  @override
  String get cancelReasonFoundAlternative => 'Знайшлі альтэрнатыўу';

  @override
  String get cancelReasonOther => 'Іншае';

  @override
  String get tellUsMore => 'Скажыце больш (апцыёнальна)';

  @override
  String get cancelReasonDetailHint => 'Мы оцэнім любыя адгуку...';

  @override
  String get justAMoment => 'Толькі адну хвілінку, калі ласка';

  @override
  String get cancelConsequencesSubtitle => 'Мы настойліва рэкамендуем разгледзеці іншыя варыянты замест адмены.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Ваш план будзе актыўны да $date. Пасля гэтага вы будзеце перайманы на бясплатную версію з абмежаванымі функцыямі.';
  }

  @override
  String get ifYouCancel => 'Калі вы адменяеце:';

  @override
  String get cancelConsequenceNoAccess => 'Больш няма неабмежаванага доступу ў канцы вашага расчётнага перыяду.';

  @override
  String get cancelConsequenceBattery => '7x больш ўжывання батарэі (апрацоўка на прыстасаванні)';

  @override
  String get cancelConsequenceQuality => 'На 30% ніжэйшая якасць трансляцыі (мадэлі на прыстасаванні)';

  @override
  String get cancelConsequenceDelay => 'Затрымка на 5-7 секунд (мадэлі на прыстасаванні)';

  @override
  String get cancelConsequenceSpeakers => 'Не можа ідэнтыфіцыраць спікерыў.';

  @override
  String get confirmAndCancel => 'Апаўнаміць і адмяніць';

  @override
  String get cancelConsequencePhoneCalls => 'Няма трансляцыі тэлефонных вызваў у рэжыме рэальнага часу';

  @override
  String get feedbackTitleTooExpensive => 'Якая цэна была б вам прыдаўся?';

  @override
  String get feedbackTitleMissingFeatures => 'Якія функцыі вам адсутнічаюць?';

  @override
  String get feedbackTitleAudioQuality => 'Якія праблемы вы испытваlī?';

  @override
  String get feedbackTitleBatteryDrain => 'Раскажыце нам аб праблемах з батарэяй';

  @override
  String get feedbackTitleFoundAlternative => 'На што вы пераходзіце?';

  @override
  String get feedbackTitleNotUsing => 'Што б зрабіў Omi больш карыснаю?';

  @override
  String get feedbackSubtitleTooExpensive => 'Ваш адгук дапамагае нам знайсці правільнае баланс.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Мы ўсё будуем — гэта дапамагае нам расстаўіць прыярытэты.';

  @override
  String get feedbackSubtitleAudioQuality => 'Мы б хацелі зразумець, что пайшло не так.';

  @override
  String get feedbackSubtitleBatteryDrain => 'Гэта дапамагае нашай каманде аборудавання палепшыцца.';

  @override
  String get feedbackSubtitleFoundAlternative => 'Мы б хацелі даведацца, якая рашэнне прыцягнула вашу ўвагу.';

  @override
  String get feedbackSubtitleNotUsing => 'Мы хочам зрабіць Omi больш карыснаю для вас.';

  @override
  String get deviceDiagnostics => 'Дыягностыка прыстасавання';

  @override
  String get signalStrength => 'Мацнасць сігналу';

  @override
  String get connectionUptime => 'Час ўчынёння';

  @override
  String get reconnections => 'Перасяданні';

  @override
  String get disconnectHistory => 'Гісторыя адлучэнняў';

  @override
  String get noDisconnectsRecorded => 'Нема зафіксаваных адлучэнняў';

  @override
  String get diagnostics => 'Дыягностыка';

  @override
  String get waitingForData => 'Чаканне дадзеных...';

  @override
  String get liveRssiOverTime => 'Жывая RSSI на працягу часу';

  @override
  String get noRssiDataYet => 'Дадзеных RSSI яшчэ няма';

  @override
  String get collectingData => 'Зборка дадзеных...';

  @override
  String get cleanDisconnect => 'Чыстае адлучэнне';

  @override
  String get connectionTimeout => 'Тайм-аут злучэння';

  @override
  String get remoteDeviceTerminated => 'Адлегле прыстасаванне завершана';

  @override
  String get pairedToAnotherPhone => 'Спарана з іншым тэлефонам';

  @override
  String get linkKeyMismatch => 'Спарвніванне ключа спасылкі';

  @override
  String get connectionFailed => 'Злучэнне не ўдалося';

  @override
  String get appClosed => 'Прыкладанне закрыта';

  @override
  String get manualDisconnect => 'Ручное адлучэнне';

  @override
  String lastNEvents(int count) {
    return 'Апошнія $count падзей';
  }

  @override
  String get signal => 'Сігнал';

  @override
  String get battery => 'Батарэя';

  @override
  String get excellent => 'Прекрасна';

  @override
  String get good => 'Добра';

  @override
  String get fair => 'Добра';

  @override
  String get weak => 'Слаба';

  @override
  String gattError(String code) {
    return 'Ошыбка GATT ($code)';
  }

  @override
  String get batteryHistory => 'Батарэя';

  @override
  String get noBatteryDataYet => 'Даных пра батарэю яшчэ няма';

  @override
  String get day => 'Дзень';

  @override
  String get week => 'Тыдзень';

  @override
  String get rollbackToStableFirmware => 'Вярнуцца да стабільнай прошыўкі';

  @override
  String get rollbackConfirmTitle => 'Вярнуцца да прошыўкі?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Гэта замяніць вашу бягучую прошыўку на апошнюю стабільную версію ($version). Вашы прыстасаванне перазагрузіцца пасля абнаўлення.';
  }

  @override
  String get stableFirmware => 'Стабільная прошыўка';

  @override
  String get fetchingStableFirmware => 'Загрузка апошняй стабільнай прошыўкі...';

  @override
  String get noStableFirmwareFound => 'Не ўдалося знайсці стабільную версію прошыўкі для вашага прыстасавання.';

  @override
  String get installStableFirmware => 'Устанавіць стабільную прошыўку';

  @override
  String get alreadyOnStableFirmware => 'Вы ужо на апошняй стабільнай версіі.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration аўдыё захаваны адзінаў';
  }

  @override
  String get willSyncAutomatically => 'будзе сінхранізавана аўтаматычна';

  @override
  String get enableLocationTitle => 'Уключыць месцазнаходжанне';

  @override
  String get enableLocationDescription =>
      'Дазвол на месцазнаходжанне патрэбны, каб знайсці pobliski Bluetooth-прыстасаванні.';

  @override
  String get voiceRecordingFound => 'Запіс знойдзены';

  @override
  String get transcriptionConnecting => 'Падключэнне трансляцыі...';

  @override
  String get transcriptionReconnecting => 'Перасяданне трансляцыі...';

  @override
  String get transcriptionUnavailable => 'Трансляцыя недаступна';

  @override
  String get audioOutput => 'Аўдыё выхад';

  @override
  String get firmwareWarningTitle => 'Важна: Прачытайце перад абнаўленнем';

  @override
  String get firmwareFormatWarning =>
      'Гэта прашыўка адфарматуе SD-карту. Калі ласка, пераканайцеся, што ўсе афлайн-даныя сінхранізаваны перад абнаўленнем.\n\nКалі пасля ўстаноўкі гэтай версіі вы ўбачыце мігатлівы чырвоны індыкатар, не хвалюйцеся. Проста падключыце прыладу да праграмы, і яна павінна стаць сіняй. Чырвоны індыкатар азначае, што гадзіннік прылады яшчэ не сінхранізаваны.';

  @override
  String get continueAnyway => 'Працягнуць';

  @override
  String get tasksClearCompleted => 'Ачысціць выкананыя';

  @override
  String get tasksSelectAll => 'Выбраць усё';

  @override
  String tasksDeleteSelected(int count) {
    return 'Выдаліць $count задачу(і)';
  }

  @override
  String get tasksMarkComplete => 'Адзначана як выкананае';

  @override
  String get appleHealthManageNote =>
      'Omi атрымлівае доступ да Apple Health праз фрэймворк HealthKit ад Apple. Вы можаце адклікаць доступ у любы час у Наладах iOS.';

  @override
  String get appleHealthConnectCta => 'Падключыць Apple Health';

  @override
  String get appleHealthDisconnectCta => 'Адключыць Apple Health';

  @override
  String get appleHealthConnectedBadge => 'Падключана';

  @override
  String get appleHealthFeatureChatTitle => 'Размаўляйце пра здароўе';

  @override
  String get appleHealthFeatureChatDesc => 'Пытайцеся ў Omi пра крокі, сон, пульс і трэніроўкі.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Толькі для чытання';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi ніколі не піша ў Apple Health і не змяняе вашы даныя.';

  @override
  String get appleHealthFeatureSecureTitle => 'Бяспечная сінхранізацыя';

  @override
  String get appleHealthFeatureSecureDesc => 'Даныя Apple Health прыватна сінхранізуюцца з акаўнтам Omi.';

  @override
  String get appleHealthDeniedTitle => 'Доступ да Apple Health адхілены';

  @override
  String get appleHealthDeniedBody =>
      'У Omi няма дазволу на чытанне даных Apple Health. Уключыце яго ў Налады iOS → Прыватнасць і бяспека → Health → Omi.';

  @override
  String get deleteFlowReasonTitle => 'Чаму вы сыходзіце?';

  @override
  String get deleteFlowReasonSubtitle => 'Ваш водгук дапамагае нам зрабіць Omi лепшым для ўсіх.';

  @override
  String get deleteReasonPrivacy => 'Праблемы з прыватнасцю';

  @override
  String get deleteReasonNotUsing => 'Карыстаюся недастаткова часта';

  @override
  String get deleteReasonMissingFeatures => 'Не хапае патрэбных функцый';

  @override
  String get deleteReasonTechnicalIssues => 'Зашмат тэхнічных праблем';

  @override
  String get deleteReasonFoundAlternative => 'Карыстаюся нечым іншым';

  @override
  String get deleteReasonTakingBreak => 'Проста раблю перапынак';

  @override
  String get deleteReasonOther => 'Іншае';

  @override
  String get deleteFlowFeedbackTitle => 'Раскажыце падрабязней';

  @override
  String get deleteFlowFeedbackSubtitle => 'Што прымусіла б Omi працаваць для вас?';

  @override
  String get deleteFlowFeedbackHint => 'Неабавязкова — вашы думкі дапамагаюць нам ствараць лепшы прадукт.';

  @override
  String get deleteFlowConfirmTitle => 'Гэта назаўсёды';

  @override
  String get deleteFlowConfirmSubtitle => 'Пасля выдалення ўліковага запісу аднавіць яго немагчыма.';

  @override
  String get deleteConsequenceSubscription => 'Любая актыўная падпіска будзе скасавана.';

  @override
  String get deleteConsequenceNoRecovery => 'Ваш уліковы запіс нельга аднавіць — нават службай падтрымкі.';

  @override
  String get deleteTypeToConfirm => 'Увядзіце DELETE для пацвярджэння';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'Выдаліць уліковы запіс назаўсёды';

  @override
  String get keepMyAccount => 'Захаваць мой уліковы запіс';

  @override
  String get deleteAccountFailed => 'Не атрымалася выдаліць ваш уліковы запіс. Паспрабуйце яшчэ раз.';

  @override
  String get planUpdate => 'Абнаўленне плана';

  @override
  String get planDeprecationMessage =>
      'Ваш план Unlimited спыняецца. Пераключыцеся на план Operator — тыя ж выдатныя магчымасці за \$49/мес. Ваш бягучы план будзе працягваць працаваць тым часам.';

  @override
  String get upgradeYourPlan => 'Палепшыце свой план';

  @override
  String get youAreOnAPaidPlan => 'Вы на платным плане.';

  @override
  String get chatTitle => 'Чат';

  @override
  String get chatMessages => 'паведамленняў';

  @override
  String get unlimitedChatThisMonth => 'Неабмежаваныя паведамленні ў чаце гэты месяц';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used з $limit бюджэту вылічэнняў выкарыстана';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used з $limit паведамленняў выкарыстана гэты месяц';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit выкарыстана';
  }

  @override
  String get chatLimitReachedUpgrade => 'Ліміт чату дасягнуты. Абнавіце для большай колькасці паведамленняў.';

  @override
  String get chatLimitReachedTitle => 'Ліміт чату дасягнуты';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Вы выкарысталі $used з $limitDisplay на плане $plan.';
  }

  @override
  String resetsInDays(int count) {
    return 'Скід праз $count дзён';
  }

  @override
  String resetsInHours(int count) {
    return 'Скід праз $count гадзін';
  }

  @override
  String get resetsSoon => 'Хутка скінецца';

  @override
  String get upgradePlan => 'Абнавіць план';

  @override
  String get billingMonthly => 'Штомесяц';

  @override
  String get billingYearly => 'Штогод';

  @override
  String get savePercent => 'Зэканомце ~17%';

  @override
  String get popular => 'Папулярны';

  @override
  String get currentPlan => 'Бягучы';

  @override
  String neoSubtitle(int count) {
    return '$count пытанняў у месяц';
  }

  @override
  String operatorSubtitle(int count) {
    return '$count пытанняў у месяц';
  }

  @override
  String get architectSubtitle => 'AI для прафесіяналаў — тысячы чатаў + агентная аўтаматызацыя';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Чат: \$$used / \$$limit выкарыстана ў гэтым месяцы';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Чат: \$$used выкарыстана ў гэтым месяцы';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Чат: $used / $limit паведамленняў у гэтым месяцы';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Чат: $used паведамленняў у гэтым месяцы';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'Вы дасягнулі свайго месячнага ліміту. Абнавіце, каб працягваць размаўляць з Omi без абмежаванняў.';

  @override
  String get voiceResponseAudio => 'Чытаць адказ Omi уголас';

  @override
  String get voiceResponseMode => 'Галасавы адказ';

  @override
  String get voiceResponseModeTitle => 'Калі агучваць адказы';

  @override
  String get voiceResponseOff => 'Выкл';

  @override
  String get voiceResponseHeadphonesOnly => 'Толькі навушнікі';

  @override
  String get voiceResponseAlways => 'Заўсёды';

  @override
  String get agreeAndContinue => 'Прыняць і працягнуць';

  @override
  String get startVoiceRecording => 'Пачаць галасавы запіс';

  @override
  String get startCallRecording => 'Пачаць запіс званка';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'Галасавы рэжым';

  @override
  String get quickActionAskOmi => 'Спытайце ў Омі што заўгодна';

  @override
  String get record => 'Запісаць';

  @override
  String get stop => 'Спыніць';

  @override
  String get recordWithPhoneMic => 'Запіс мікрафонам тэлефона';

  @override
  String get recordWithPhoneMicSubtitle => 'Запісвайце гук вакол сябе';

  @override
  String get phoneCall => 'Тэлефонны званок';

  @override
  String get phoneCallSubtitle => 'Запіс званка з жывой транскрыпцыяй';

  @override
  String get searchActionItems => 'Шукаць элементы дзеянняў';

  @override
  String get selectActionItems => 'Выбраць некалькі';

  @override
  String chooseExportDestination(int count) {
    return 'Экспартаваць $count элемент(аў) у…';
  }

  @override
  String get bulkExportInProgress => 'Экспарт…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Экспартавана $count у $platform';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Экспартавана $success з $total у $platform';
  }

  @override
  String get showCompletedTasks => 'Паказаць завершаныя';

  @override
  String get hideCompletedTasks => 'Схаваць завершаныя';

  @override
  String get selectAllTasksMenu => 'Выбраць усе';

  @override
  String get connectTaskAppToExport => 'Падключыце праграму задач у Наладах для экспарту';

  @override
  String get connectAction => 'Злучыць';

  @override
  String get deselectAllTasksMenu => 'Зняць выбар усіх';
}
