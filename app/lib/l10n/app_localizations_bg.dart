// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Bulgarian (`bg`).
class AppLocalizationsBg extends AppLocalizations {
  AppLocalizationsBg([String locale = 'bg']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Разговор';

  @override
  String get transcriptTab => 'Транскрипт';

  @override
  String get actionItemsTab => 'Задачи';

  @override
  String get deleteConversationTitle => 'Изтриване на разговор?';

  @override
  String get deleteConversationMessage =>
      'Сигурни ли сте, че искате да изтриете този разговор? Това действие не може да бъде отменено.';

  @override
  String get confirm => 'Потвърди';

  @override
  String get cancel => 'Отказ';

  @override
  String get ok => 'ОК';

  @override
  String get delete => 'Изтрий';

  @override
  String get add => 'Добави';

  @override
  String get update => 'Актуализирай';

  @override
  String get save => 'Запази';

  @override
  String get edit => 'Редактиране';

  @override
  String get close => 'Затвори';

  @override
  String get clear => 'Изчисти';

  @override
  String get copyTranscript => 'Копиране на текст';

  @override
  String get copySummary => 'Копирай резюме';

  @override
  String get testPrompt => 'Тествай подсказка';

  @override
  String get reprocessConversation => 'Преработи разговор';

  @override
  String get deleteConversation => 'Изтриване на разговор';

  @override
  String get contentCopied => 'Съдържанието е копирано в клипборда';

  @override
  String get failedToUpdateStarred => 'Неуспешна актуализация на статуса с отметка.';

  @override
  String get conversationUrlNotShared => 'URL адресът на разговора не можа да бъде споделен.';

  @override
  String get errorProcessingConversation => 'Грешка при обработка на разговора. Моля, опитайте отново по-късно.';

  @override
  String get noInternetConnection => 'Няма интернет връзка';

  @override
  String get unableToDeleteConversation => 'Невъзможно изтриване на разговор';

  @override
  String get somethingWentWrong => 'Нещо се обърка! Моля, опитайте отново по-късно.';

  @override
  String get copyErrorMessage => 'Копирай съобщение за грешка';

  @override
  String get errorCopied => 'Съобщението за грешка е копирано в клипборда';

  @override
  String get remaining => 'Оставащо';

  @override
  String get loading => 'Зареждане...';

  @override
  String get loadingDuration => 'Зареждане на продължителност...';

  @override
  String secondsCount(int count) {
    return '$count секунди';
  }

  @override
  String get people => 'Хора';

  @override
  String get addNewPerson => 'Добави нов човек';

  @override
  String get editPerson => 'Редактирай човек';

  @override
  String get createPersonHint => 'Създайте нов човек и обучете Omi да разпознава и тяхната реч!';

  @override
  String get speechProfile => 'Речеви Профил';

  @override
  String sampleNumber(int number) {
    return 'Образец $number';
  }

  @override
  String get settings => 'Настройки';

  @override
  String get language => 'Език';

  @override
  String get selectLanguage => 'Изберете език';

  @override
  String get deleting => 'Изтриване...';

  @override
  String get pleaseCompleteAuthentication =>
      'Моля, завършете удостоверяването в браузъра си. След това се върнете в приложението.';

  @override
  String get failedToStartAuthentication => 'Неуспешно стартиране на удостоверяване';

  @override
  String get importStarted => 'Импортирането започна! Ще получите известие, когато приключи.';

  @override
  String get failedToStartImport => 'Неуспешно стартиране на импортиране. Моля, опитайте отново.';

  @override
  String get couldNotAccessFile => 'Не можа да се получи достъп до избрания файл';

  @override
  String get askOmi => 'Попитай Omi';

  @override
  String get done => 'Готово';

  @override
  String get disconnected => 'Прекъснато';

  @override
  String get searching => 'Търсене...';

  @override
  String get connectDevice => 'Свържи устройство';

  @override
  String get monthlyLimitReached => 'Достигнахте месечния си лимит.';

  @override
  String get checkUsage => 'Провери използване';

  @override
  String get syncingRecordings => 'Синхронизиране на записи';

  @override
  String get recordingsToSync => 'Записи за синхронизиране';

  @override
  String get allCaughtUp => 'Всичко е актуално';

  @override
  String get sync => 'Синхронизирай';

  @override
  String get pendantUpToDate => 'Медальонът е актуален';

  @override
  String get allRecordingsSynced => 'Всички записи са синхронизирани';

  @override
  String get syncingInProgress => 'Синхронизацията е в ход';

  @override
  String get readyToSync => 'Готово за синхронизация';

  @override
  String get tapSyncToStart => 'Натиснете Синхронизирай за начало';

  @override
  String get pendantNotConnected => 'Медальонът не е свързан. Свържете за синхронизация.';

  @override
  String get everythingSynced => 'Всичко вече е синхронизирано.';

  @override
  String get recordingsNotSynced => 'Имате записи, които все още не са синхронизирани.';

  @override
  String get syncingBackground => 'Ще продължим да синхронизираме записите ви във фонов режим.';

  @override
  String get noConversationsYet => 'Все още няма разговори';

  @override
  String get noStarredConversations => 'Няма отбелязани разговори';

  @override
  String get starConversationHint =>
      'За да отбележите разговор, отворете го и натиснете иконката със звезда в заглавието.';

  @override
  String get searchConversations => 'Търсене на разговори...';

  @override
  String selectedCount(int count, Object s) {
    return '$count избрани';
  }

  @override
  String get merge => 'Обедини';

  @override
  String get mergeConversations => 'Обедини разговори';

  @override
  String mergeConversationsMessage(int count) {
    return 'Това ще комбинира $count разговора в един. Всичко съдържание ще бъде обединено и регенерирано.';
  }

  @override
  String get mergingInBackground => 'Обединяване във фонов режим. Това може да отнеме момент.';

  @override
  String get failedToStartMerge => 'Неуспешно стартиране на обединяване';

  @override
  String get askAnything => 'Попитайте каквото и да е';

  @override
  String get noMessagesYet => 'Все още няма съобщения!\nЗащо не започнете разговор?';

  @override
  String get deletingMessages => 'Изтриване на вашите съобщения от паметта на Omi...';

  @override
  String get messageCopied => '✨ Съобщението е копирано в клипборда';

  @override
  String get cannotReportOwnMessage => 'Не можете да докладвате собствените си съобщения.';

  @override
  String get reportMessage => 'Докладване на съобщение';

  @override
  String get reportMessageConfirm => 'Сигурни ли сте, че искате да докладвате това съобщение?';

  @override
  String get messageReported => 'Съобщението е докладвано успешно.';

  @override
  String get thankYouFeedback => 'Благодарим за обратната връзка!';

  @override
  String get clearChat => 'Изчисти чат?';

  @override
  String get clearChatConfirm => 'Сигурни ли сте, че искате да изчистите чата? Това действие не може да бъде отменено.';

  @override
  String get maxFilesLimit => 'Можете да качите само 4 файла наведнъж';

  @override
  String get chatWithOmi => 'Чат с Omi';

  @override
  String get apps => 'Приложения';

  @override
  String get noAppsFound => 'Не са намерени приложения';

  @override
  String get tryAdjustingSearch => 'Опитайте да коригирате търсенето или филтрите си';

  @override
  String get createYourOwnApp => 'Създайте свое приложение';

  @override
  String get buildAndShareApp => 'Създайте и споделете персонализирано приложение';

  @override
  String get searchApps => 'Търсене на приложения...';

  @override
  String get myApps => 'Моите приложения';

  @override
  String get installedApps => 'Инсталирани приложения';

  @override
  String get unableToFetchApps =>
      'Не могат да се заредят приложенията :(\n\nМоля, проверете интернет връзката си и опитайте отново.';

  @override
  String get aboutOmi => 'За Omi';

  @override
  String get privacyPolicy => 'Политика за поверителност';

  @override
  String get visitWebsite => 'Посетете уебсайта';

  @override
  String get helpOrInquiries => 'Помощ или запитвания?';

  @override
  String get joinCommunity => 'Присъединете се към общността!';

  @override
  String get membersAndCounting => '8000+ членове и броят продължава да расте.';

  @override
  String get deleteAccountTitle => 'Изтриване на акаунт';

  @override
  String get deleteAccountConfirm => 'Сигурни ли сте, че искате да изтриете акаунта си?';

  @override
  String get cannotBeUndone => 'Това не може да бъде отменено.';

  @override
  String get allDataErased => 'Всички ваши спомени и разговори ще бъдат изтрити завинаги.';

  @override
  String get appsDisconnected => 'Вашите приложения и интеграции ще бъдат прекратени незабавно.';

  @override
  String get exportBeforeDelete =>
      'Можете да експортирате данните си преди да изтриете акаунта си, но след като бъде изтрит, не може да бъде възстановен.';

  @override
  String get deleteAccountCheckbox =>
      'Разбирам, че изтриването на акаунта ми е постоянно и всички данни, включително спомени и разговори, ще бъдат загубени и не могат да бъдат възстановени.';

  @override
  String get areYouSure => 'Сигурни ли сте?';

  @override
  String get deleteAccountFinal =>
      'Това действие е необратимо и ще изтрие завинаги вашия акаунт и всички свързани данни. Сигурни ли сте, че искате да продължите?';

  @override
  String get deleteNow => 'Изтрий сега';

  @override
  String get goBack => 'Назад';

  @override
  String get checkBoxToConfirm =>
      'Отметнете квадратчето, за да потвърдите, че разбирате, че изтриването на акаунта ви е постоянно и необратимо.';

  @override
  String get profile => 'Профил';

  @override
  String get name => 'Име';

  @override
  String get email => 'Имейл';

  @override
  String get customVocabulary => 'Персонализиран Речник';

  @override
  String get identifyingOthers => 'Идентифициране на Други';

  @override
  String get paymentMethods => 'Методи за Плащане';

  @override
  String get conversationDisplay => 'Показване на Разговори';

  @override
  String get dataPrivacy => 'Поверителност на Данните';

  @override
  String get userId => 'Потребителски ID';

  @override
  String get notSet => 'Не е зададено';

  @override
  String get userIdCopied => 'ID на потребителя е копиран в клипборда';

  @override
  String get systemDefault => 'По подразбиране на системата';

  @override
  String get planAndUsage => 'План и използване';

  @override
  String get offlineSync => 'Офлайн синхронизация';

  @override
  String get deviceSettings => 'Настройки на устройството';

  @override
  String get chatTools => 'Инструменти за чат';

  @override
  String get feedbackBug => 'Обратна връзка / Грешка';

  @override
  String get helpCenter => 'Център за помощ';

  @override
  String get developerSettings => 'Настройки за разработчици';

  @override
  String get getOmiForMac => 'Вземете Omi за Mac';

  @override
  String get referralProgram => 'Програма за препоръки';

  @override
  String get signOut => 'Изход';

  @override
  String get appAndDeviceCopied => 'Детайлите за приложението и устройството са копирани';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Вашата поверителност, вашият контрол';

  @override
  String get privacyIntro =>
      'В Omi сме ангажирани със защитата на вашата поверителност. Тази страница ви позволява да контролирате как вашите данни се съхраняват и използват.';

  @override
  String get learnMore => 'Научете повече...';

  @override
  String get dataProtectionLevel => 'Ниво на защита на данните';

  @override
  String get dataProtectionDesc =>
      'Вашите данни са защитени по подразбиране със силно криптиране. Прегледайте настройките си и бъдещите опции за поверителност по-долу.';

  @override
  String get appAccess => 'Достъп до приложение';

  @override
  String get appAccessDesc =>
      'Следните приложения могат да имат достъп до вашите данни. Докоснете приложение, за да управлявате неговите разрешения.';

  @override
  String get noAppsExternalAccess => 'Няма инсталирани приложения с външен достъп до вашите данни.';

  @override
  String get deviceName => 'Име на устройство';

  @override
  String get deviceId => 'Идентификатор на устройството';

  @override
  String get firmware => 'Фърмуер';

  @override
  String get sdCardSync => 'Синхронизация на SD карта';

  @override
  String get hardwareRevision => 'Хардуерна ревизия';

  @override
  String get modelNumber => 'Номер на модела';

  @override
  String get manufacturer => 'Производител';

  @override
  String get doubleTap => 'Двойно докосване';

  @override
  String get ledBrightness => 'Яркост на LED';

  @override
  String get micGain => 'Усилване на микрофон';

  @override
  String get disconnect => 'Прекъсни';

  @override
  String get forgetDevice => 'Забрави устройство';

  @override
  String get chargingIssues => 'Проблеми със зареждането';

  @override
  String get disconnectDevice => 'Прекъсни връзката с устройството';

  @override
  String get unpairDevice => 'Разкачи устройството';

  @override
  String get unpairAndForget => 'Разедини и забрави устройство';

  @override
  String get deviceDisconnectedMessage => 'Вашият Omi беше прекъснат 😔';

  @override
  String get deviceUnpairedMessage =>
      'Устройството е разкачено. Отидете в Настройки > Bluetooth и забравете устройството, за да завършите разкачването.';

  @override
  String get unpairDialogTitle => 'Разедини устройство';

  @override
  String get unpairDialogMessage =>
      'Това ще разедини устройството, така че да може да бъде свързано с друг телефон. Ще трябва да отидете в Настройки > Bluetooth и да забравите устройството, за да завършите процеса.';

  @override
  String get deviceNotConnected => 'Устройството не е свързано';

  @override
  String get connectDeviceMessage =>
      'Свържете вашето Omi устройство за достъп\nдо настройките на устройството и персонализация';

  @override
  String get deviceInfoSection => 'Информация за устройството';

  @override
  String get customizationSection => 'Персонализация';

  @override
  String get hardwareSection => 'Хардуер';

  @override
  String get v2Undetected => 'V2 не е открит';

  @override
  String get v2UndetectedMessage =>
      'Виждаме, че имате V1 устройство или устройството ви не е свързано. Функционалността на SD картата е налична само за V2 устройства.';

  @override
  String get endConversation => 'Край на разговор';

  @override
  String get pauseResume => 'Пауза/Възобнови';

  @override
  String get starConversation => 'Отбележи разговор';

  @override
  String get doubleTapAction => 'Действие при двойно докосване';

  @override
  String get endAndProcess => 'Край и обработка на разговор';

  @override
  String get pauseResumeRecording => 'Пауза/Възобнови записването';

  @override
  String get starOngoing => 'Отбележи текущ разговор';

  @override
  String get off => 'Изключено';

  @override
  String get max => 'Макс';

  @override
  String get mute => 'Заглуши';

  @override
  String get quiet => 'Тихо';

  @override
  String get normal => 'Нормално';

  @override
  String get high => 'Високо';

  @override
  String get micGainDescMuted => 'Микрофонът е заглушен';

  @override
  String get micGainDescLow => 'Много тихо - за шумни среди';

  @override
  String get micGainDescModerate => 'Тихо - за умерен шум';

  @override
  String get micGainDescNeutral => 'Неутрално - балансирано записване';

  @override
  String get micGainDescSlightlyBoosted => 'Леко засилено - нормално използване';

  @override
  String get micGainDescBoosted => 'Засилено - за тихи среди';

  @override
  String get micGainDescHigh => 'Високо - за далечни или тихи гласове';

  @override
  String get micGainDescVeryHigh => 'Много високо - за много тихи източници';

  @override
  String get micGainDescMax => 'Максимално - използвайте с внимание';

  @override
  String get developerSettingsTitle => 'Настройки за разработчици';

  @override
  String get saving => 'Запазване...';

  @override
  String get personaConfig => 'Конфигурирайте вашата AI персона';

  @override
  String get beta => 'БЕТА';

  @override
  String get transcription => 'Транскрипция';

  @override
  String get transcriptionConfig => 'Конфигурирай STT доставчик';

  @override
  String get conversationTimeout => 'Изчакване на разговор';

  @override
  String get conversationTimeoutConfig => 'Задайте кога разговорите приключват автоматично';

  @override
  String get importData => 'Импортирай данни';

  @override
  String get importDataConfig => 'Импортирайте данни от други източници';

  @override
  String get debugDiagnostics => 'Отстраняване на грешки и диагностика';

  @override
  String get endpointUrl => 'URL на крайна точка';

  @override
  String get noApiKeys => 'Все още няма API ключове';

  @override
  String get createKeyToStart => 'Създайте ключ, за да започнете';

  @override
  String get createKey => 'Създай Ключ';

  @override
  String get docs => 'Документация';

  @override
  String get yourOmiInsights => 'Вашите Omi прозрения';

  @override
  String get today => 'Днес';

  @override
  String get thisMonth => 'Този месец';

  @override
  String get thisYear => 'Тази година';

  @override
  String get allTime => 'Цялото време';

  @override
  String get noActivityYet => 'Все още няма дейност';

  @override
  String get startConversationToSeeInsights =>
      'Започнете разговор с Omi,\nза да видите прозренията си за използване тук.';

  @override
  String get listening => 'Слушане';

  @override
  String get listeningSubtitle => 'Общо време, през което Omi активно е слушал.';

  @override
  String get understanding => 'Разбиране';

  @override
  String get understandingSubtitle => 'Думи, разбрани от вашите разговори.';

  @override
  String get providing => 'Предоставяне';

  @override
  String get providingSubtitle => 'Задачи и бележки, автоматично записани.';

  @override
  String get remembering => 'Запомняне';

  @override
  String get rememberingSubtitle => 'Факти и детайли, запомнени за вас.';

  @override
  String get unlimitedPlan => 'Неограничен план';

  @override
  String get managePlan => 'Управлявай план';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Вашият план ще бъде анулиран на $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Вашият план се подновява на $date.';
  }

  @override
  String get basicPlan => 'Безплатен план';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used от $limit мин използвани';
  }

  @override
  String get upgrade => 'Надстрой';

  @override
  String get upgradeToUnlimited => 'Надградете до неограничено';

  @override
  String basicPlanDesc(int limit) {
    return 'Вашият план включва $limit безплатни минути на месец. Надстройте за неограничен достъп.';
  }

  @override
  String get shareStatsMessage => 'Споделям моите Omi статистики! (omi.me - вашият винаги включен AI асистент)';

  @override
  String get sharePeriodToday => 'Днес omi има:';

  @override
  String get sharePeriodMonth => 'Този месец omi има:';

  @override
  String get sharePeriodYear => 'Тази година omi има:';

  @override
  String get sharePeriodAllTime => 'Досега omi има:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Слушал $minutes минути';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Разбрал $words думи';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Предоставил $count прозрения';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Запомнил $count спомена';
  }

  @override
  String get debugLogs => 'Регистрационни файлове за отстраняване на грешки';

  @override
  String get debugLogsAutoDelete => 'Автоматично се изтриват след 3 дни.';

  @override
  String get debugLogsDesc => 'Помага за диагностициране на проблеми';

  @override
  String get noLogFilesFound => 'Не са намерени регистрационни файлове.';

  @override
  String get omiDebugLog => 'Omi дневник за отстраняване на грешки';

  @override
  String get logShared => 'Дневникът е споделен';

  @override
  String get selectLogFile => 'Изберете файл с дневник';

  @override
  String get shareLogs => 'Споделяне на регистрационни файлове';

  @override
  String get debugLogCleared => 'Дневникът за отстраняване на грешки е изчистен';

  @override
  String get exportStarted => 'Експортирането започна. Може да отнеме няколко секунди...';

  @override
  String get exportAllData => 'Експортирай всички данни';

  @override
  String get exportDataDesc => 'Експортирайте разговори в JSON файл';

  @override
  String get exportedConversations => 'Експортирани разговори от Omi';

  @override
  String get exportShared => 'Експортът е споделен';

  @override
  String get deleteKnowledgeGraphTitle => 'Изтриване на граф на знанията?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Това ще изтрие всички производни данни от графа на знанията (възли и връзки). Вашите оригинални спомени ще останат в безопасност. Графът ще бъде възстановен с течение на времето или при следващо запитване.';

  @override
  String get knowledgeGraphDeleted => 'Графът на знанията е изтрит';

  @override
  String deleteGraphFailed(String error) {
    return 'Неуспешно изтриване на граф: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Изтрий граф на знанията';

  @override
  String get deleteKnowledgeGraphDesc => 'Изчисти всички възли и връзки';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP сървър';

  @override
  String get mcpServerDesc => 'Свържете AI асистенти с вашите данни';

  @override
  String get serverUrl => 'URL на сървър';

  @override
  String get urlCopied => 'URL копиран';

  @override
  String get apiKeyAuth => 'Удостоверяване с API ключ';

  @override
  String get header => 'Заглавка';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID на клиент';

  @override
  String get clientSecret => 'Тайна на клиент';

  @override
  String get useMcpApiKey => 'Използвайте вашия MCP API ключ';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Събития на разговори';

  @override
  String get newConversationCreated => 'Създаден нов разговор';

  @override
  String get realtimeTranscript => 'Транскрипт в реално време';

  @override
  String get transcriptReceived => 'Получен транскрипт';

  @override
  String get audioBytes => 'Аудио байтове';

  @override
  String get audioDataReceived => 'Получени аудио данни';

  @override
  String get intervalSeconds => 'Интервал (секунди)';

  @override
  String get daySummary => 'Дневно резюме';

  @override
  String get summaryGenerated => 'Генерирано резюме';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Добавете към claude_desktop_config.json';

  @override
  String get copyConfig => 'Копирай конфигурация';

  @override
  String get configCopied => 'Конфигурацията е копирана в клипборда';

  @override
  String get listeningMins => 'Слушане (мин)';

  @override
  String get understandingWords => 'Разбиране (думи)';

  @override
  String get insights => 'Прозрения';

  @override
  String get memories => 'Спомени';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used от $limit мин използвани този месец';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used от $limit думи използвани този месец';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used от $limit прозрения получени този месец';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used от $limit спомена създадени този месец';
  }

  @override
  String get visibility => 'Видимост';

  @override
  String get visibilitySubtitle => 'Контролирайте кои разговори се появяват във вашия списък';

  @override
  String get showShortConversations => 'Показвай кратки разговори';

  @override
  String get showShortConversationsDesc => 'Показвай разговори по-къси от прага';

  @override
  String get showDiscardedConversations => 'Показвай изхвърлени разговори';

  @override
  String get showDiscardedConversationsDesc => 'Включи разговори, маркирани като изхвърлени';

  @override
  String get shortConversationThreshold => 'Праг за кратък разговор';

  @override
  String get shortConversationThresholdSubtitle =>
      'Разговорите по-къси от това ще бъдат скрити, освен ако не са активирани по-горе';

  @override
  String get durationThreshold => 'Праг на продължителност';

  @override
  String get durationThresholdDesc => 'Скривай разговори по-къси от това';

  @override
  String minLabel(int count) {
    return '$count мин';
  }

  @override
  String get customVocabularyTitle => 'Персонализиран речник';

  @override
  String get addWords => 'Добавете думи';

  @override
  String get addWordsDesc => 'Имена, термини или необичайни думи';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Свържи';

  @override
  String get comingSoon => 'Скоро';

  @override
  String get chatToolsFooter => 'Свържете вашите приложения, за да виждате данни и метрики в чата.';

  @override
  String get completeAuthInBrowser =>
      'Моля, завършете удостоверяването в браузъра си. След това се върнете в приложението.';

  @override
  String failedToStartAuth(String appName) {
    return 'Неуспешно стартиране на $appName удостоверяване';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Прекъсни връзката с $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Сигурни ли сте, че искате да прекъснете връзката с $appName? Можете да се свържете отново по всяко време.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Прекъсната връзка с $appName';
  }

  @override
  String get failedToDisconnect => 'Неуспешно прекъсване на връзката';

  @override
  String connectTo(String appName) {
    return 'Свържи се с $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Ще трябва да упълномощите Omi за достъп до вашите $appName данни. Това ще отвори браузъра ви за удостоверяване.';
  }

  @override
  String get continueAction => 'Продължи';

  @override
  String get languageTitle => 'Език';

  @override
  String get primaryLanguage => 'Основен език';

  @override
  String get automaticTranslation => 'Автоматичен превод';

  @override
  String get detectLanguages => 'Разпознавай 10+ езика';

  @override
  String get authorizeSavingRecordings => 'Разрешете запазване на записи';

  @override
  String get thanksForAuthorizing => 'Благодарим, че разрешихте!';

  @override
  String get needYourPermission => 'Нуждаем се от вашето разрешение';

  @override
  String get alreadyGavePermission =>
      'Вече сте ни дали разрешение да запазваме вашите записи. Ето напомняне защо го нуждаем:';

  @override
  String get wouldLikePermission => 'Бихме искали вашето разрешение да запазваме вашите гласови записи. Ето защо:';

  @override
  String get improveSpeechProfile => 'Подобрете вашия гласов профил';

  @override
  String get improveSpeechProfileDesc => 'Използваме записи, за да обучим и подобрим вашия личен гласов профил.';

  @override
  String get trainFamilyProfiles => 'Обучете профили за приятели и семейство';

  @override
  String get trainFamilyProfilesDesc =>
      'Вашите записи ни помагат да разпознаем и създадем профили за вашите приятели и семейство.';

  @override
  String get enhanceTranscriptAccuracy => 'Подобрете точността на транскрипта';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'С подобряването на нашия модел, можем да предоставим по-добри резултати от транскрипцията за вашите записи.';

  @override
  String get legalNotice =>
      'Юридическо уведомление: Законността на записването и съхраняването на гласови данни може да варира в зависимост от вашето местоположение и как използвате тази функция. Вие сте отговорни за спазването на местните закони и разпоредби.';

  @override
  String get alreadyAuthorized => 'Вече разрешено';

  @override
  String get authorize => 'Разреши';

  @override
  String get revokeAuthorization => 'Оттегли разрешение';

  @override
  String get authorizationSuccessful => 'Разрешението е успешно!';

  @override
  String get failedToAuthorize => 'Неуспешно разрешаване. Моля, опитайте отново.';

  @override
  String get authorizationRevoked => 'Разрешението е оттеглено.';

  @override
  String get recordingsDeleted => 'Записите са изтрити.';

  @override
  String get failedToRevoke => 'Неуспешно оттегляне на разрешение. Моля, опитайте отново.';

  @override
  String get permissionRevokedTitle => 'Разрешението е оттеглено';

  @override
  String get permissionRevokedMessage => 'Искате ли да премахнем и всички ваши съществуващи записи?';

  @override
  String get yes => 'Да';

  @override
  String get editName => 'Редактирай име';

  @override
  String get howShouldOmiCallYou => 'Как Omi да ви нарича?';

  @override
  String get enterYourName => 'Въведете вашето име';

  @override
  String get nameCannotBeEmpty => 'Името не може да бъде празно';

  @override
  String get nameUpdatedSuccessfully => 'Името е актуализирано успешно!';

  @override
  String get calendarSettings => 'Настройки на календар';

  @override
  String get calendarProviders => 'Доставчици на календар';

  @override
  String get macOsCalendar => 'macOS Календар';

  @override
  String get connectMacOsCalendar => 'Свържете вашия локален macOS календар';

  @override
  String get googleCalendar => 'Google Календар';

  @override
  String get syncGoogleAccount => 'Синхронизирай с вашия Google акаунт';

  @override
  String get showMeetingsMenuBar => 'Показвай предстоящи срещи в лентата с менюта';

  @override
  String get showMeetingsMenuBarDesc => 'Показвай следващата ви среща и време до нея в macOS лентата с менюта';

  @override
  String get showEventsNoParticipants => 'Показвай събития без участници';

  @override
  String get showEventsNoParticipantsDesc => 'Когато е активирано, показва събития без участници или видео връзка.';

  @override
  String get yourMeetings => 'Вашите срещи';

  @override
  String get refresh => 'Опресни';

  @override
  String get noUpcomingMeetings => 'Няма намерени предстоящи срещи';

  @override
  String get checkingNextDays => 'Проверка на следващите 30 дни';

  @override
  String get tomorrow => 'Утре';

  @override
  String get googleCalendarComingSoon => 'Google Календар интеграция скоро!';

  @override
  String connectedAsUser(String userId) {
    return 'Свързан като потребител: $userId';
  }

  @override
  String get defaultWorkspace => 'Работно пространство по подразбиране';

  @override
  String get tasksCreatedInWorkspace => 'Задачите ще бъдат създадени в това работно пространство';

  @override
  String get defaultProjectOptional => 'Проект по подразбиране (Незадължително)';

  @override
  String get leaveUnselectedTasks => 'Оставете неизбрано, за да създавате задачи без проект';

  @override
  String get noProjectsInWorkspace => 'Няма намерени проекти в това работно пространство';

  @override
  String get conversationTimeoutDesc =>
      'Изберете колко дълго да се чака в тишина преди автоматично приключване на разговор:';

  @override
  String get timeout2Minutes => '2 минути';

  @override
  String get timeout2MinutesDesc => 'Приключи разговор след 2 минути тишина';

  @override
  String get timeout5Minutes => '5 минути';

  @override
  String get timeout5MinutesDesc => 'Приключи разговор след 5 минути тишина';

  @override
  String get timeout10Minutes => '10 минути';

  @override
  String get timeout10MinutesDesc => 'Приключи разговор след 10 минути тишина';

  @override
  String get timeout30Minutes => '30 минути';

  @override
  String get timeout30MinutesDesc => 'Приключи разговор след 30 минути тишина';

  @override
  String get timeout4Hours => '4 часа';

  @override
  String get timeout4HoursDesc => 'Приключи разговор след 4 часа тишина';

  @override
  String get conversationEndAfterHours => 'Разговорите сега ще приключват след 4 часа тишина';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Разговорите сега ще приключват след $minutes минута(и) тишина';
  }

  @override
  String get tellUsPrimaryLanguage => 'Кажете ни вашия основен език';

  @override
  String get languageForTranscription => 'Задайте вашия език за по-точни транскрипции и персонализирано изживяване.';

  @override
  String get singleLanguageModeInfo => 'Режимът с един език е активиран. Преводът е деактивиран за по-висока точност.';

  @override
  String get searchLanguageHint => 'Търсете език по име или код';

  @override
  String get noLanguagesFound => 'Няма намерени езици';

  @override
  String get skip => 'Пропусни';

  @override
  String languageSetTo(String language) {
    return 'Езикът е зададен на $language';
  }

  @override
  String get failedToSetLanguage => 'Неуспешно задаване на език';

  @override
  String appSettings(String appName) {
    return '$appName Настройки';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Прекъсни връзката с $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Това ще премахне вашето $appName удостоверяване. Ще трябва да се свържете отново, за да го използвате.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Свързан с $appName';
  }

  @override
  String get account => 'Акаунт';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Вашите задачи ще бъдат синхронизирани с вашия $appName акаунт';
  }

  @override
  String get defaultSpace => 'Пространство по подразбиране';

  @override
  String get selectSpaceInWorkspace => 'Изберете пространство във вашето работно пространство';

  @override
  String get noSpacesInWorkspace => 'Няма намерени пространства в това работно пространство';

  @override
  String get defaultList => 'Списък по подразбиране';

  @override
  String get tasksAddedToList => 'Задачите ще бъдат добавени в този списък';

  @override
  String get noListsInSpace => 'Няма намерени списъци в това пространство';

  @override
  String failedToLoadRepos(String error) {
    return 'Неуспешно зареждане на хранилища: $error';
  }

  @override
  String get defaultRepoSaved => 'Хранилището по подразбиране е запазено';

  @override
  String get failedToSaveDefaultRepo => 'Неуспешно запазване на хранилище по подразбиране';

  @override
  String get defaultRepository => 'Хранилище по подразбиране';

  @override
  String get selectDefaultRepoDesc =>
      'Изберете хранилище по подразбиране за създаване на проблеми. Все още можете да посочите различно хранилище при създаване на проблеми.';

  @override
  String get noReposFound => 'Не са намерени хранилища';

  @override
  String get private => 'Частен';

  @override
  String updatedDate(String date) {
    return 'Актуализиран $date';
  }

  @override
  String get yesterday => 'Вчера';

  @override
  String daysAgo(int count) {
    return 'преди $count дни';
  }

  @override
  String get oneWeekAgo => 'преди 1 седмица';

  @override
  String weeksAgo(int count) {
    return 'преди $count седмици';
  }

  @override
  String get oneMonthAgo => 'преди 1 месец';

  @override
  String monthsAgo(int count) {
    return 'преди $count месеца';
  }

  @override
  String get issuesCreatedInRepo => 'Проблемите ще бъдат създадени във вашето хранилище по подразбиране';

  @override
  String get taskIntegrations => 'Интеграции на задачи';

  @override
  String get configureSettings => 'Конфигурирай настройки';

  @override
  String get completeAuthBrowser =>
      'Моля, завършете удостоверяването в браузъра си. След това се върнете в приложението.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Неуспешно стартиране на $appName удостоверяване';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Свържи се с $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Ще трябва да упълномощите Omi за създаване на задачи в вашия $appName акаунт. Това ще отвори браузъра ви за удостоверяване.';
  }

  @override
  String get continueButton => 'Продължи';

  @override
  String appIntegration(String appName) {
    return '$appName Интеграция';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Интеграцията с $appName идва скоро! Работим усилено, за да ви предоставим повече опции за управление на задачи.';
  }

  @override
  String get gotIt => 'Разбрах';

  @override
  String get tasksExportedOneApp => 'Задачите могат да бъдат експортирани в едно приложение наведнъж.';

  @override
  String get completeYourUpgrade => 'Завършете вашата надстройка';

  @override
  String get importConfiguration => 'Импортирай конфигурация';

  @override
  String get exportConfiguration => 'Експортирай конфигурация';

  @override
  String get bringYourOwn => 'Донесете свой собствен';

  @override
  String get payYourSttProvider => 'Използвайте omi свободно. Плащате само на вашия STT доставчик директно.';

  @override
  String get freeMinutesMonth => '1 200 безплатни минути/месец включени. Неограничено с ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Хостът е задължителен';

  @override
  String get validPortRequired => 'Валиден порт е задължителен';

  @override
  String get validWebsocketUrlRequired => 'Валиден WebSocket URL е задължителен (wss://)';

  @override
  String get apiUrlRequired => 'API URL е задължителен';

  @override
  String get apiKeyRequired => 'API ключ е задължителен';

  @override
  String get invalidJsonConfig => 'Невалидна JSON конфигурация';

  @override
  String errorSaving(String error) {
    return 'Грешка при запазване: $error';
  }

  @override
  String get configCopiedToClipboard => 'Конфигурацията е копирана в клипборда';

  @override
  String get pasteJsonConfig => 'Поставете вашата JSON конфигурация по-долу:';

  @override
  String get addApiKeyAfterImport => 'Ще трябва да добавите собствен API ключ след импортиране';

  @override
  String get paste => 'Постави';

  @override
  String get import => 'Импортирай';

  @override
  String get invalidProviderInConfig => 'Невалиден доставчик в конфигурацията';

  @override
  String importedConfig(String providerName) {
    return 'Импортирана $providerName конфигурация';
  }

  @override
  String invalidJson(String error) {
    return 'Невалиден JSON: $error';
  }

  @override
  String get provider => 'Доставчик';

  @override
  String get live => 'На живо';

  @override
  String get onDevice => 'На устройството';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Въведете вашата STT HTTP крайна точка';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Въведете вашата STT WebSocket крайна точка на живо';

  @override
  String get apiKey => 'API ключ';

  @override
  String get enterApiKey => 'Въведете вашия API ключ';

  @override
  String get storedLocallyNeverShared => 'Съхранено локално, никога не се споделя';

  @override
  String get host => 'Хост';

  @override
  String get port => 'Порт';

  @override
  String get advanced => 'Разширени';

  @override
  String get configuration => 'Конфигурация';

  @override
  String get requestConfiguration => 'Конфигурация на заявка';

  @override
  String get responseSchema => 'Схема на отговор';

  @override
  String get modified => 'Модифициран';

  @override
  String get resetRequestConfig => 'Нулирай конфигурацията на заявката по подразбиране';

  @override
  String get logs => 'Дневници';

  @override
  String get logsCopied => 'Дневниците са копирани';

  @override
  String get noLogsYet =>
      'Все още няма дневници. Започнете записване, за да видите активността на персонализирания STT.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName използва $codecReason. Ще се използва Omi.';
  }

  @override
  String get omiTranscription => 'Omi транскрипция';

  @override
  String get bestInClassTranscription => 'Най-добра транскрипция в класа си без настройки';

  @override
  String get instantSpeakerLabels => 'Моментални етикети на говорител';

  @override
  String get languageTranslation => 'Превод на 100+ езика';

  @override
  String get optimizedForConversation => 'Оптимизирано за разговор';

  @override
  String get autoLanguageDetection => 'Автоматично разпознаване на език';

  @override
  String get highAccuracy => 'Висока точност';

  @override
  String get privacyFirst => 'Поверителност на първо място';

  @override
  String get saveChanges => 'Запази промените';

  @override
  String get resetToDefault => 'Нулиране до стандартно';

  @override
  String get viewTemplate => 'Виж шаблон';

  @override
  String get trySomethingLike => 'Опитайте нещо като...';

  @override
  String get tryIt => 'Опитай го';

  @override
  String get creatingPlan => 'Създаване на план';

  @override
  String get developingLogic => 'Разработване на логика';

  @override
  String get designingApp => 'Дизайниране на приложение';

  @override
  String get generatingIconStep => 'Генериране на икона';

  @override
  String get finalTouches => 'Финални щрихи';

  @override
  String get processing => 'Обработка...';

  @override
  String get features => 'Функции';

  @override
  String get creatingYourApp => 'Създаване на вашето приложение...';

  @override
  String get generatingIcon => 'Генериране на икона...';

  @override
  String get whatShouldWeMake => 'Какво да направим?';

  @override
  String get appName => 'Име на приложение';

  @override
  String get description => 'Описание';

  @override
  String get publicLabel => 'Публично';

  @override
  String get privateLabel => 'Частно';

  @override
  String get free => 'Безплатно';

  @override
  String get perMonth => '/ Месец';

  @override
  String get tailoredConversationSummaries => 'Персонализирани резюмета на разговори';

  @override
  String get customChatbotPersonality => 'Персонализирана личност на чатбот';

  @override
  String get makePublic => 'Направи публична';

  @override
  String get anyoneCanDiscover => 'Всеки може да открие вашето приложение';

  @override
  String get onlyYouCanUse => 'Само вие можете да използвате това приложение';

  @override
  String get paidApp => 'Платено приложение';

  @override
  String get usersPayToUse => 'Потребителите плащат, за да използват вашето приложение';

  @override
  String get freeForEveryone => 'Безплатно за всички';

  @override
  String get perMonthLabel => '/ месец';

  @override
  String get creating => 'Създаване...';

  @override
  String get createApp => 'Създаване на приложение';

  @override
  String get searchingForDevices => 'Търсене на устройства...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'УСТРОЙСТВА',
      one: 'УСТРОЙСТВО',
    );
    return '$count $_temp0 НАМЕРЕНИ НАБЛИЗО';
  }

  @override
  String get pairingSuccessful => 'СДВОЯВАНЕТО Е УСПЕШНО';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Грешка при свързване с Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Не показвай отново';

  @override
  String get iUnderstand => 'Разбирам';

  @override
  String get enableBluetooth => 'Активирай Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi се нуждае от Bluetooth, за да се свърже с вашето носимо устройство. Моля, активирайте Bluetooth и опитайте отново.';

  @override
  String get contactSupport => 'Свържете се с поддръжката?';

  @override
  String get connectLater => 'Свържи по-късно';

  @override
  String get grantPermissions => 'Предоставяне на разрешения';

  @override
  String get backgroundActivity => 'Фонова активност';

  @override
  String get backgroundActivityDesc => 'Позволете на Omi да работи на заден план за по-добра стабилност';

  @override
  String get locationAccess => 'Достъп до местоположение';

  @override
  String get locationAccessDesc => 'Активирайте фоново местоположение за пълното изживяване';

  @override
  String get notifications => 'Известия';

  @override
  String get notificationsDesc => 'Активирайте известия, за да сте информирани';

  @override
  String get locationServiceDisabled => 'Услугата за местоположение е деактивирана';

  @override
  String get locationServiceDisabledDesc =>
      'Услугата за местоположение е деактивирана. Моля, отидете в Настройки > Поверителност и сигурност > Услуги за местоположение и я активирайте';

  @override
  String get backgroundLocationDenied => 'Отказан достъп до фоново местоположение';

  @override
  String get backgroundLocationDeniedDesc =>
      'Моля, отидете в настройките на устройството и задайте разрешението за местоположение на \"Винаги разрешавай\"';

  @override
  String get lovingOmi => 'Обичате ли Omi?';

  @override
  String get leaveReviewIos =>
      'Помогнете ни да достигнем до повече хора, като оставите отзив в App Store. Вашата обратна връзка е много важна за нас!';

  @override
  String get leaveReviewAndroid =>
      'Помогнете ни да достигнем до повече хора, като оставите отзив в Google Play Store. Вашата обратна връзка е много важна за нас!';

  @override
  String get rateOnAppStore => 'Оценете в App Store';

  @override
  String get rateOnGooglePlay => 'Оценете в Google Play';

  @override
  String get maybeLater => 'Може би по-късно';

  @override
  String get speechProfileIntro => 'Omi трябва да научи вашите цели и вашия глас. Ще можете да го промените по-късно.';

  @override
  String get getStarted => 'Започнете';

  @override
  String get allDone => 'Готово!';

  @override
  String get keepGoing => 'Продължавайте, справяте се страхотно';

  @override
  String get skipThisQuestion => 'Пропусни този въпрос';

  @override
  String get skipForNow => 'Пропусни засега';

  @override
  String get connectionError => 'Грешка в връзката';

  @override
  String get connectionErrorDesc =>
      'Неуспешна връзка със сървъра. Моля, проверете интернет връзката си и опитайте отново.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Открит е невалиден запис';

  @override
  String get multipleSpeakersDesc =>
      'Изглежда има множество говорители в записа. Моля, уверете се, че сте на тихо място и опитайте отново.';

  @override
  String get tooShortDesc => 'Не е открита достатъчно реч. Моля, говорете повече и опитайте отново.';

  @override
  String get invalidRecordingDesc => 'Моля, уверете се, че говорите поне 5 секунди и не повече от 90.';

  @override
  String get areYouThere => 'Там ли сте?';

  @override
  String get noSpeechDesc =>
      'Не можахме да открием реч. Моля, уверете се, че говорите поне 10 секунди и не повече от 3 минути.';

  @override
  String get connectionLost => 'Връзката е изгубена';

  @override
  String get connectionLostDesc => 'Връзката беше прекъсната. Моля, проверете интернет връзката си и опитайте отново.';

  @override
  String get tryAgain => 'Опитай отново';

  @override
  String get connectOmiOmiGlass => 'Свържи Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Продължи без устройство';

  @override
  String get permissionsRequired => 'Изискват се разрешения';

  @override
  String get permissionsRequiredDesc =>
      'Това приложение се нуждае от разрешения за Bluetooth и местоположение, за да функционира правилно. Моля, активирайте ги в настройките.';

  @override
  String get openSettings => 'Отвори настройки';

  @override
  String get wantDifferentName => 'Искате ли различно име?';

  @override
  String get whatsYourName => 'Как се казвате?';

  @override
  String get speakTranscribeSummarize => 'Говорете. Транскрибирайте. Обобщавайте.';

  @override
  String get signInWithApple => 'Влезте с Apple';

  @override
  String get signInWithGoogle => 'Влезте с Google';

  @override
  String get byContinuingAgree => 'Като продължавате, вие се съгласявате с нашата ';

  @override
  String get termsOfUse => 'Условия за ползване';

  @override
  String get omiYourAiCompanion => 'Omi – Вашият AI спътник';

  @override
  String get captureEveryMoment => 'Уловете всеки момент. Получавайте резюмета с\nAI. Никога повече бележки.';

  @override
  String get appleWatchSetup => 'Настройка на Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Разрешение заявено!';

  @override
  String get microphonePermission => 'Разрешение за микрофон';

  @override
  String get permissionGrantedNow =>
      'Разрешението е дадено! Сега:\n\nОтворете приложението Omi на часовника си и натиснете \"Продължи\" по-долу';

  @override
  String get needMicrophonePermission =>
      'Нуждаем се от разрешение за микрофон.\n\n1. Натиснете \"Дайте разрешение\"\n2. Разрешете на вашия iPhone\n3. Приложението на часовника ще се затвори\n4. Отворете отново и натиснете \"Продължи\"';

  @override
  String get grantPermissionButton => 'Дайте разрешение';

  @override
  String get needHelp => 'Нужда от помощ?';

  @override
  String get troubleshootingSteps =>
      'Отстраняване на проблеми:\n\n1. Уверете се, че Omi е инсталиран на часовника ви\n2. Отворете приложението Omi на часовника си\n3. Потърсете изскачащия прозорец за разрешение\n4. Натиснете \"Разреши\" когато бъдете подканени\n5. Приложението на часовника ще се затвори - отворете го отново\n6. Върнете се и натиснете \"Продължи\" на вашия iPhone';

  @override
  String get recordingStartedSuccessfully => 'Записването започна успешно!';

  @override
  String get permissionNotGrantedYet =>
      'Разрешението все още не е дадено. Моля, уверете се, че сте разрешили достъп до микрофона и сте отворили отново приложението на часовника си.';

  @override
  String errorRequestingPermission(String error) {
    return 'Грешка при заявяване на разрешение: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Грешка при стартиране на записване: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Изберете вашия основен език';

  @override
  String get languageBenefits => 'Задайте вашия език за по-точни транскрипции и персонализирано изживяване';

  @override
  String get whatsYourPrimaryLanguage => 'Кой е вашият основен език?';

  @override
  String get selectYourLanguage => 'Изберете вашия език';

  @override
  String get personalGrowthJourney => 'Вашето пътешествие на личностен растеж с AI, който слуша всяка ваша дума.';

  @override
  String get actionItemsTitle => 'Задачи';

  @override
  String get actionItemsDescription => 'Докоснете за редактиране • Натиснете дълго за избор • Плъзнете за действия';

  @override
  String get tabToDo => 'За изпълнение';

  @override
  String get tabDone => 'Готово';

  @override
  String get tabOld => 'Стари';

  @override
  String get emptyTodoMessage => '🎉 Всичко е актуално!\nНяма чакащи задачи';

  @override
  String get emptyDoneMessage => 'Все още няма завършени елементи';

  @override
  String get emptyOldMessage => '✅ Няма стари задачи';

  @override
  String get noItems => 'Няма елементи';

  @override
  String get actionItemMarkedIncomplete => 'Задачата е маркирана като незавършена';

  @override
  String get actionItemCompleted => 'Задачата е завършена';

  @override
  String get deleteActionItemTitle => 'Изтрий задача';

  @override
  String get deleteActionItemMessage => 'Сигурни ли сте, че искате да изтриете тази задача?';

  @override
  String get deleteSelectedItemsTitle => 'Изтриване на избраните елементи';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Сигурни ли сте, че искате да изтриете $count избрана(и) задача(и)$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Задачата \"$description\" е изтрита';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count задача(и)$s изтрити';
  }

  @override
  String get failedToDeleteItem => 'Неуспешно изтриване на задача';

  @override
  String get failedToDeleteItems => 'Неуспешно изтриване на елементи';

  @override
  String get failedToDeleteSomeItems => 'Неуспешно изтриване на някои елементи';

  @override
  String get welcomeActionItemsTitle => 'Готови за задачи';

  @override
  String get welcomeActionItemsDescription =>
      'Вашият AI автоматично ще извлича задачи и дейности от вашите разговори. Те ще се появят тук, когато бъдат създадени.';

  @override
  String get autoExtractionFeature => 'Автоматично извлечени от разговори';

  @override
  String get editSwipeFeature => 'Докоснете за редактиране, плъзнете за завършване или изтриване';

  @override
  String itemsSelected(int count) {
    return '$count избрани';
  }

  @override
  String get selectAll => 'Избери всички';

  @override
  String get deleteSelected => 'Изтрий избраните';

  @override
  String get searchMemories => 'Търсене на спомени...';

  @override
  String get memoryDeleted => 'Споменът е изтрит.';

  @override
  String get undo => 'Отмени';

  @override
  String get noMemoriesYet => '🧠 Все още няма спомени';

  @override
  String get noAutoMemories => 'Все още няма автоматично извлечени спомени';

  @override
  String get noManualMemories => 'Все още няма ръчно добавени спомени';

  @override
  String get noMemoriesInCategories => 'Няма спомени в тези категории';

  @override
  String get noMemoriesFound => '🔍 Не са намерени спомени';

  @override
  String get addFirstMemory => 'Добавете вашия първи спомен';

  @override
  String get clearMemoryTitle => 'Изчистване на паметта на Omi';

  @override
  String get clearMemoryMessage =>
      'Сигурни ли сте, че искате да изчистите паметта на Omi? Това действие не може да бъде отменено.';

  @override
  String get clearMemoryButton => 'Изчисти паметта';

  @override
  String get memoryClearedSuccess => 'Паметта на Omi за вас е изчистена';

  @override
  String get noMemoriesToDelete => 'Няма спомени за изтриване';

  @override
  String get createMemoryTooltip => 'Създай нов спомен';

  @override
  String get createActionItemTooltip => 'Създай нова задача';

  @override
  String get memoryManagement => 'Управление на спомените';

  @override
  String get filterMemories => 'Филтриране на спомени';

  @override
  String totalMemoriesCount(int count) {
    return 'Имате общо $count спомена';
  }

  @override
  String get publicMemories => 'Публични спомени';

  @override
  String get privateMemories => 'Частни спомени';

  @override
  String get makeAllPrivate => 'Направи всички спомени частни';

  @override
  String get makeAllPublic => 'Направи всички спомени публични';

  @override
  String get deleteAllMemories => 'Изтрий всички спомени';

  @override
  String get allMemoriesPrivateResult => 'Всички спомени сега са частни';

  @override
  String get allMemoriesPublicResult => 'Всички спомени сега са публични';

  @override
  String get newMemory => '✨ Нов спомен';

  @override
  String get editMemory => '✏️ Редактирай спомен';

  @override
  String get memoryContentHint => 'Обичам да ям сладолед...';

  @override
  String get failedToSaveMemory => 'Неуспешно запазване. Моля, проверете връзката си.';

  @override
  String get saveMemory => 'Запази спомен';

  @override
  String get retry => 'Опитай отново';

  @override
  String get createActionItem => 'Създаване на задача';

  @override
  String get editActionItem => 'Редактиране на задача';

  @override
  String get actionItemDescriptionHint => 'Какво трябва да се направи?';

  @override
  String get actionItemDescriptionEmpty => 'Описанието на задачата не може да бъде празно.';

  @override
  String get actionItemUpdated => 'Задачата е актуализирана';

  @override
  String get failedToUpdateActionItem => 'Неуспешна актуализация на задачата';

  @override
  String get actionItemCreated => 'Задачата е създадена';

  @override
  String get failedToCreateActionItem => 'Неуспешно създаване на задача';

  @override
  String get dueDate => 'Краен срок';

  @override
  String get time => 'Час';

  @override
  String get addDueDate => 'Добави краен срок';

  @override
  String get pressDoneToSave => 'Натиснете готово за запазване';

  @override
  String get pressDoneToCreate => 'Натиснете готово за създаване';

  @override
  String get filterAll => 'Всички';

  @override
  String get filterSystem => 'За вас';

  @override
  String get filterInteresting => 'Прозрения';

  @override
  String get filterManual => 'Ръчно';

  @override
  String get completed => 'Завършено';

  @override
  String get markComplete => 'Маркирай като завършено';

  @override
  String get actionItemDeleted => 'Задачата е изтрита';

  @override
  String get failedToDeleteActionItem => 'Неуспешно изтриване на задачата';

  @override
  String get deleteActionItemConfirmTitle => 'Изтриване на задача';

  @override
  String get deleteActionItemConfirmMessage => 'Сигурни ли сте, че искате да изтриете тази задача?';

  @override
  String get appLanguage => 'Език на приложението';

  @override
  String get appInterfaceSectionTitle => 'ИНТЕРФЕЙС НА ПРИЛОЖЕНИЕТО';

  @override
  String get speechTranscriptionSectionTitle => 'РЕЧ И ТРАНСКРИПЦИЯ';

  @override
  String get languageSettingsHelperText =>
      'Езикът на приложението променя менютата и бутоните. Езикът на речта влияе на начина, по който се транскрибират вашите записи.';

  @override
  String get translationNotice => 'Известие за превод';

  @override
  String get translationNoticeMessage =>
      'Omi превежда разговори на вашия основен език. Актуализирайте го по всяко време в Настройки → Профили.';

  @override
  String get pleaseCheckInternetConnection => 'Моля, проверете интернет връзката си и опитайте отново';

  @override
  String get pleaseSelectReason => 'Моля, изберете причина';

  @override
  String get tellUsMoreWhatWentWrong => 'Разкажете ни повече за това, което се обърка...';

  @override
  String get selectText => 'Избор на текст';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Максимум $count цели са позволени';
  }

  @override
  String get conversationCannotBeMerged => 'Този разговор не може да бъде обединен (заключен или вече се обединява)';

  @override
  String get pleaseEnterFolderName => 'Моля, въведете име на папка';

  @override
  String get failedToCreateFolder => 'Неуспешно създаване на папка';

  @override
  String get failedToUpdateFolder => 'Неуспешно актуализиране на папка';

  @override
  String get folderName => 'Име на папка';

  @override
  String get descriptionOptional => 'Описание (по избор)';

  @override
  String get failedToDeleteFolder => 'Неуспешно изтриване на папка';

  @override
  String get editFolder => 'Редактиране на папка';

  @override
  String get deleteFolder => 'Изтриване на папка';

  @override
  String get transcriptCopiedToClipboard => 'Преписът е копиран в клипборда';

  @override
  String get summaryCopiedToClipboard => 'Резюмето е копирано в клипборда';

  @override
  String get conversationUrlCouldNotBeShared => 'URL адресът на разговора не можа да бъде споделен.';

  @override
  String get urlCopiedToClipboard => 'URL адресът е копиран в клипборда';

  @override
  String get exportTranscript => 'Експортиране на препис';

  @override
  String get exportSummary => 'Експортиране на резюме';

  @override
  String get exportButton => 'Експортиране';

  @override
  String get actionItemsCopiedToClipboard => 'Елементите за действие са копирани в клипборда';

  @override
  String get summarize => 'Резюмиране';

  @override
  String get generateSummary => 'Генериране на резюме';

  @override
  String get conversationNotFoundOrDeleted => 'Разговорът не е намерен или е изтрит';

  @override
  String get deleteMemory => 'Изтрий спомен';

  @override
  String get thisActionCannotBeUndone => 'Това действие не може да бъде отменено.';

  @override
  String memoriesCount(int count) {
    return '$count спомени';
  }

  @override
  String get noMemoriesInCategory => 'Все още няма спомени в тази категория';

  @override
  String get addYourFirstMemory => 'Добавете първия си спомен';

  @override
  String get firmwareDisconnectUsb => 'Изключете USB';

  @override
  String get firmwareUsbWarning => 'USB връзката по време на актуализации може да повреди устройството ви.';

  @override
  String get firmwareBatteryAbove15 => 'Батерия над 15%';

  @override
  String get firmwareEnsureBattery => 'Уверете се, че устройството ви има 15% батерия.';

  @override
  String get firmwareStableConnection => 'Стабилна връзка';

  @override
  String get firmwareConnectWifi => 'Свържете се към WiFi или мобилна мрежа.';

  @override
  String failedToStartUpdate(String error) {
    return 'Неуспешно стартиране на актуализация: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Преди актуализация, уверете се:';

  @override
  String get confirmed => 'Потвърдено!';

  @override
  String get release => 'Пуснете';

  @override
  String get slideToUpdate => 'Плъзнете за актуализация';

  @override
  String copiedToClipboard(String title) {
    return '$title копирано в клипборда';
  }

  @override
  String get batteryLevel => 'Ниво на батерията';

  @override
  String get productUpdate => 'Актуализация на продукта';

  @override
  String get offline => 'Офлайн';

  @override
  String get available => 'Наличен';

  @override
  String get unpairDeviceDialogTitle => 'Разкачи устройството';

  @override
  String get unpairDeviceDialogMessage =>
      'Това ще разкачи устройството, за да може да бъде свързано с друг телефон. Ще трябва да отидете в Настройки > Bluetooth и да забравите устройството, за да завършите процеса.';

  @override
  String get unpair => 'Разкачи';

  @override
  String get unpairAndForgetDevice => 'Разкачи и забрави устройството';

  @override
  String get unknownDevice => 'Неизвестно устройство';

  @override
  String get unknown => 'Неизвестно';

  @override
  String get productName => 'Име на продукта';

  @override
  String get serialNumber => 'Сериен номер';

  @override
  String get connected => 'Свързано';

  @override
  String get privacyPolicyTitle => 'Политика за поверителност';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Все още няма API ключове. Създайте един за интеграция с приложението си.';

  @override
  String get createKeyToGetStarted => 'Create a key to get started';

  @override
  String get persona => 'Персона';

  @override
  String get configureYourAiPersona => 'Configure your AI persona';

  @override
  String get configureSttProvider => 'Configure STT provider';

  @override
  String get setWhenConversationsAutoEnd => 'Set when conversations auto-end';

  @override
  String get importDataFromOtherSources => 'Import data from other sources';

  @override
  String get debugAndDiagnostics => 'Отстраняване на грешки и диагностика';

  @override
  String get autoDeletesAfter3Days => 'Автоматично изтриване след 3 дни';

  @override
  String get helpsDiagnoseIssues => 'Помага при диагностицирането на проблеми';

  @override
  String get exportStartedMessage => 'Export started. This may take a few seconds...';

  @override
  String get exportConversationsToJson => 'Export conversations to a JSON file';

  @override
  String get knowledgeGraphDeletedSuccess => 'Knowledge Graph deleted successfully';

  @override
  String failedToDeleteGraph(String error) {
    return 'Failed to delete graph: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Clear all nodes and connections';

  @override
  String get addToClaudeDesktopConfig => 'Add to claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Connect AI assistants to your data';

  @override
  String get useYourMcpApiKey => 'Use your MCP API key';

  @override
  String get realTimeTranscript => 'Транскрипция в реално време';

  @override
  String get experimental => 'Експериментални';

  @override
  String get transcriptionDiagnostics => 'Диагностика на транскрипция';

  @override
  String get detailedDiagnosticMessages => 'Подробни диагностични съобщения';

  @override
  String get autoCreateSpeakers => 'Автоматично създаване на говорители';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Последващи въпроси';

  @override
  String get suggestQuestionsAfterConversations => 'Предложете въпроси след разговори';

  @override
  String get goalTracker => 'Проследяване на цели';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Ежедневно размисъл';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Описанието на задачата не може да бъде празно';

  @override
  String get saved => 'Запазено';

  @override
  String get overdue => 'Просрочено';

  @override
  String get failedToUpdateDueDate => 'Неуспешно актуализиране на крайния срок';

  @override
  String get markIncomplete => 'Маркирай като незавършено';

  @override
  String get editDueDate => 'Редактирай краен срок';

  @override
  String get setDueDate => 'Задай краен срок';

  @override
  String get clearDueDate => 'Изчисти краен срок';

  @override
  String get failedToClearDueDate => 'Неуспешно изчистване на крайния срок';

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
  String get sundayAbbr => 'Нд';

  @override
  String get howDoesItWork => 'Как работи?';

  @override
  String get sdCardSyncDescription => 'SD Card Sync ще импортира вашите спомени от SD картата в приложението';

  @override
  String get checksForAudioFiles => 'Проверява за аудио файлове на SD картата';

  @override
  String get omiSyncsAudioFiles => 'Omi след това синхронизира аудио файловете със сървъра';

  @override
  String get serverProcessesAudio => 'Сървърът обработва аудио файловете и създава спомени';

  @override
  String get youreAllSet => 'Готови сте!';

  @override
  String get welcomeToOmiDescription =>
      'Добре дошли в Omi! Вашият AI спътник е готов да ви помогне с разговори, задачи и още.';

  @override
  String get startUsingOmi => 'Започнете да използвате Omi';

  @override
  String get back => 'Назад';

  @override
  String get keyboardShortcuts => 'Клавишни Комбинации';

  @override
  String get toggleControlBar => 'Превключване на контролната лента';

  @override
  String get pressKeys => 'Натиснете клавиши...';

  @override
  String get cmdRequired => '⌘ е задължителен';

  @override
  String get invalidKey => 'Невалиден клавиш';

  @override
  String get space => 'Интервал';

  @override
  String get search => 'Търсене';

  @override
  String get searchPlaceholder => 'Търсене...';

  @override
  String get untitledConversation => 'Разговор без заглавие';

  @override
  String countRemaining(String count) {
    return '$count оставащи';
  }

  @override
  String get addGoal => 'Добави цел';

  @override
  String get editGoal => 'Редактирай цел';

  @override
  String get icon => 'Икона';

  @override
  String get goalTitle => 'Заглавие на целта';

  @override
  String get current => 'Текущо';

  @override
  String get target => 'Цел';

  @override
  String get saveGoal => 'Запази';

  @override
  String get goals => 'Цели';

  @override
  String get tapToAddGoal => 'Докоснете, за да добавите цел';

  @override
  String welcomeBack(String name) {
    return 'Добре дошъл обратно, $name';
  }

  @override
  String get yourConversations => 'Вашите разговори';

  @override
  String get reviewAndManageConversations => 'Прегледайте и управлявайте записаните си разговори';

  @override
  String get startCapturingConversations =>
      'Започнете да записвате разговори с вашето устройство Omi, за да ги видите тук.';

  @override
  String get useMobileAppToCapture => 'Използвайте мобилното приложение за записване на аудио';

  @override
  String get conversationsProcessedAutomatically => 'Разговорите се обработват автоматично';

  @override
  String get getInsightsInstantly => 'Получавайте прозрения и обобщения моментално';

  @override
  String get showAll => 'Покажи всички →';

  @override
  String get noTasksForToday => 'Няма задачи за днес.\\nПопитайте Omi за повече задачи или създайте ръчно.';

  @override
  String get dailyScore => 'ДНЕВНА ОЦЕНКА';

  @override
  String get dailyScoreDescription => 'Оценка, която ви помага да се фокусирате по-добре върху изпълнението.';

  @override
  String get searchResults => 'Резултати от търсенето';

  @override
  String get actionItems => 'Задачи за действие';

  @override
  String get tasksToday => 'Днес';

  @override
  String get tasksTomorrow => 'Утре';

  @override
  String get tasksNoDeadline => 'Без краен срок';

  @override
  String get tasksLater => 'По-късно';

  @override
  String get loadingTasks => 'Зареждане на задачи...';

  @override
  String get tasks => 'Задачи';

  @override
  String get swipeTasksToIndent => 'Плъзнете задачи за отстъп, преместете между категории';

  @override
  String get create => 'Създаване';

  @override
  String get noTasksYet => 'Все още няма задачи';

  @override
  String get tasksFromConversationsWillAppear =>
      'Задачите от вашите разговори ще се показват тук.\nЩракнете върху Създаване, за да добавите една ръчно.';

  @override
  String get monthJan => 'Ян';

  @override
  String get monthFeb => 'Фев';

  @override
  String get monthMar => 'Март';

  @override
  String get monthApr => 'Апр';

  @override
  String get monthMay => 'Май';

  @override
  String get monthJun => 'Юни';

  @override
  String get monthJul => 'Юли';

  @override
  String get monthAug => 'Авг';

  @override
  String get monthSep => 'Сеп';

  @override
  String get monthOct => 'Окт';

  @override
  String get monthNov => 'Ное';

  @override
  String get monthDec => 'Дек';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Задачата е актуализирана успешно';

  @override
  String get actionItemCreatedSuccessfully => 'Задачата е създадена успешно';

  @override
  String get actionItemDeletedSuccessfully => 'Задачата е изтрита успешно';

  @override
  String get deleteActionItem => 'Изтриване на задача';

  @override
  String get deleteActionItemConfirmation =>
      'Сигурни ли сте, че искате да изтриете тази задача? Това действие не може да бъде отменено.';

  @override
  String get enterActionItemDescription => 'Въведете описание на задачата...';

  @override
  String get markAsCompleted => 'Маркирай като завършена';

  @override
  String get setDueDateAndTime => 'Задай краен срок и час';

  @override
  String get reloadingApps => 'Презареждане на приложения...';

  @override
  String get loadingApps => 'Зареждане на приложения...';

  @override
  String get browseInstallCreateApps => 'Разглеждане, инсталиране и създаване на приложения';

  @override
  String get all => 'Всички';

  @override
  String get open => 'Отваряне';

  @override
  String get install => 'Инсталиране';

  @override
  String get noAppsAvailable => 'Няма налични приложения';

  @override
  String get unableToLoadApps => 'Неуспешно зареждане на приложения';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Опитайте да промените термините за търсене или филтрите';

  @override
  String get checkBackLaterForNewApps => 'Проверете отново по-късно за нови приложения';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Моля, проверете интернет връзката си и опитайте отново';

  @override
  String get createNewApp => 'Създаване на ново приложение';

  @override
  String get buildSubmitCustomOmiApp => 'Създайте и изпратете вашето персонализирано Omi приложение';

  @override
  String get submittingYourApp => 'Изпращане на вашето приложение...';

  @override
  String get preparingFormForYou => 'Подготвяне на формуляра за вас...';

  @override
  String get appDetails => 'Детайли за приложението';

  @override
  String get paymentDetails => 'Детайли за плащането';

  @override
  String get previewAndScreenshots => 'Преглед и екранни снимки';

  @override
  String get appCapabilities => 'Възможности на приложението';

  @override
  String get aiPrompts => 'AI подсказки';

  @override
  String get chatPrompt => 'Подсказка за чат';

  @override
  String get chatPromptPlaceholder =>
      'Вие сте страхотно приложение, вашата задача е да отговаряте на потребителските запитвания и да ги карате да се чувстват добре...';

  @override
  String get conversationPrompt => 'Подканване за разговор';

  @override
  String get conversationPromptPlaceholder =>
      'Вие сте страхотно приложение, ще ви бъде даден транскрипт и резюме на разговор...';

  @override
  String get notificationScopes => 'Обхват на известията';

  @override
  String get appPrivacyAndTerms => 'Поверителност и условия на приложението';

  @override
  String get makeMyAppPublic => 'Направи приложението ми публично';

  @override
  String get submitAppTermsAgreement =>
      'С изпращането на това приложение приемам Условията за ползване и Политиката за поверителност на Omi AI';

  @override
  String get submitApp => 'Изпрати приложението';

  @override
  String get needHelpGettingStarted => 'Нуждаете се от помощ за започване?';

  @override
  String get clickHereForAppBuildingGuides => 'Кликнете тук за ръководства за създаване на приложения и документация';

  @override
  String get submitAppQuestion => 'Изпрати приложението?';

  @override
  String get submitAppPublicDescription =>
      'Вашето приложение ще бъде прегледано и направено публично. Можете да започнете да го използвате веднага, дори по време на прегледа!';

  @override
  String get submitAppPrivateDescription =>
      'Вашето приложение ще бъде прегледано и направено достъпно за вас лично. Можете да започнете да го използвате веднага, дори по време на прегледа!';

  @override
  String get startEarning => 'Започнете да печелите! 💰';

  @override
  String get connectStripeOrPayPal => 'Свържете Stripe или PayPal, за да получавате плащания за вашето приложение.';

  @override
  String get connectNow => 'Свържи сега';

  @override
  String installsCount(String count) {
    return '$count+ инсталации';
  }

  @override
  String get uninstallApp => 'Деинсталиране на приложението';

  @override
  String get subscribe => 'Абониране';

  @override
  String get dataAccessNotice => 'Уведомление за достъп до данни';

  @override
  String get dataAccessWarning =>
      'Това приложение ще има достъп до вашите данни. Omi AI не носи отговорност за това как вашите данни се използват, модифицират или изтриват от това приложение';

  @override
  String get installApp => 'Инсталиране на приложението';

  @override
  String get betaTesterNotice =>
      'Вие сте бета тестер за това приложение. То все още не е публично. Ще стане публично след одобрение.';

  @override
  String get appUnderReviewOwner =>
      'Вашето приложение е в процес на преглед и е видимо само за вас. Ще стане публично след одобрение.';

  @override
  String get appRejectedNotice =>
      'Вашето приложение е отхвърлено. Моля, актуализирайте детайлите на приложението и го подайте отново за преглед.';

  @override
  String get setupSteps => 'Стъпки за настройка';

  @override
  String get setupInstructions => 'Инструкции за настройка';

  @override
  String get integrationInstructions => 'Инструкции за интеграция';

  @override
  String get preview => 'Преглед';

  @override
  String get aboutTheApp => 'За приложението';

  @override
  String get aboutThePersona => 'За персоната';

  @override
  String get chatPersonality => 'Личност на чата';

  @override
  String get ratingsAndReviews => 'Оценки и отзиви';

  @override
  String get noRatings => 'няма оценки';

  @override
  String ratingsCount(String count) {
    return '$count+ оценки';
  }

  @override
  String get errorActivatingApp => 'Грешка при активиране на приложението';

  @override
  String get integrationSetupRequired => 'Ако това е интеграционно приложение, уверете се, че настройката е завършена.';

  @override
  String get installed => 'Инсталирано';

  @override
  String get appIdLabel => 'ID на приложението';

  @override
  String get appNameLabel => 'Име на приложението';

  @override
  String get appNamePlaceholder => 'Моето страхотно приложение';

  @override
  String get pleaseEnterAppName => 'Моля, въведете име на приложението';

  @override
  String get categoryLabel => 'Категория';

  @override
  String get selectCategory => 'Изберете категория';

  @override
  String get descriptionLabel => 'Описание';

  @override
  String get appDescriptionPlaceholder =>
      'Моето страхотно приложение е страхотно приложение, което прави невероятни неща. То е най-доброто приложение!';

  @override
  String get pleaseProvideValidDescription => 'Моля, предоставете валидно описание';

  @override
  String get appPricingLabel => 'Ценообразуване на приложението';

  @override
  String get noneSelected => 'Няма избрано';

  @override
  String get appIdCopiedToClipboard => 'ID на приложението е копирано в клипборда';

  @override
  String get appCategoryModalTitle => 'Категория на приложението';

  @override
  String get pricingFree => 'Безплатно';

  @override
  String get pricingPaid => 'Платено';

  @override
  String get loadingCapabilities => 'Зареждане на възможностите...';

  @override
  String get filterInstalled => 'Инсталирани';

  @override
  String get filterMyApps => 'Моите приложения';

  @override
  String get clearSelection => 'Изчистване на избора';

  @override
  String get filterCategory => 'Категория';

  @override
  String get rating4PlusStars => '4+ звезди';

  @override
  String get rating3PlusStars => '3+ звезди';

  @override
  String get rating2PlusStars => '2+ звезди';

  @override
  String get rating1PlusStars => '1+ звезди';

  @override
  String get filterRating => 'Оценка';

  @override
  String get filterCapabilities => 'Възможности';

  @override
  String get noNotificationScopesAvailable => 'Няма налични области за уведомления';

  @override
  String get popularApps => 'Популярни приложения';

  @override
  String get pleaseProvidePrompt => 'Моля, предоставете подсказка';

  @override
  String chatWithAppName(String appName) {
    return 'Чат с $appName';
  }

  @override
  String get defaultAiAssistant => 'AI асистент по подразбиране';

  @override
  String get readyToChat => '✨ Готов за чат!';

  @override
  String get connectionNeeded => '🌐 Необходима връзка';

  @override
  String get startConversation => 'Започнете разговор и нека магията започне';

  @override
  String get checkInternetConnection => 'Моля, проверете интернет връзката си';

  @override
  String get wasThisHelpful => 'Беше ли това полезно?';

  @override
  String get thankYouForFeedback => 'Благодарим за отзива!';

  @override
  String get maxFilesUploadError => 'Можете да качите само 4 файла наведнъж';

  @override
  String get attachedFiles => '📎 Прикачени файлове';

  @override
  String get takePhoto => 'Направете снимка';

  @override
  String get captureWithCamera => 'Заснемане с камера';

  @override
  String get selectImages => 'Изберете изображения';

  @override
  String get chooseFromGallery => 'Изберете от галерията';

  @override
  String get selectFile => 'Изберете файл';

  @override
  String get chooseAnyFileType => 'Изберете всякакъв тип файл';

  @override
  String get cannotReportOwnMessages => 'Не можете да докладвате собствените си съобщения';

  @override
  String get messageReportedSuccessfully => '✅ Съобщението е докладвано успешно';

  @override
  String get confirmReportMessage => 'Сигурни ли сте, че искате да докладвате това съобщение?';

  @override
  String get selectChatAssistant => 'Изберете чат асистент';

  @override
  String get enableMoreApps => 'Активиране на повече приложения';

  @override
  String get chatCleared => 'Чатът е изчистен';

  @override
  String get clearChatTitle => 'Изчистване на чата?';

  @override
  String get confirmClearChat => 'Сигурни ли сте, че искате да изчистите чата? Това действие не може да бъде отменено.';

  @override
  String get copy => 'Копиране';

  @override
  String get share => 'Споделяне';

  @override
  String get report => 'Докладване';

  @override
  String get microphonePermissionRequired => 'Разрешение за микрофон е необходимо за гласов запис.';

  @override
  String get microphonePermissionDenied =>
      'Разрешението за микрофон е отказано. Моля, предоставете разрешение в Системни настройки > Поверителност и сигурност > Микрофон.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Неуспешна проверка на разрешението за микрофон: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Неуспешно транскрибиране на аудио';

  @override
  String get transcribing => 'Транскрибиране...';

  @override
  String get transcriptionFailed => 'Транскрибирането не успя';

  @override
  String get discardedConversation => 'Отхвърлен разговор';

  @override
  String get at => 'в';

  @override
  String get from => 'от';

  @override
  String get copied => 'Копирано!';

  @override
  String get copyLink => 'Копиране на връзка';

  @override
  String get hideTranscript => 'Скриване на транскрипт';

  @override
  String get viewTranscript => 'Показване на транскрипт';

  @override
  String get conversationDetails => 'Детайли за разговора';

  @override
  String get transcript => 'Транскрипт';

  @override
  String segmentsCount(int count) {
    return '$count сегмента';
  }

  @override
  String get noTranscriptAvailable => 'Няма наличен транскрипт';

  @override
  String get noTranscriptMessage => 'Този разговор няма транскрипт.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL адресът на разговора не можа да бъде генериран.';

  @override
  String get failedToGenerateConversationLink => 'Неуспешно генериране на връзка към разговора';

  @override
  String get failedToGenerateShareLink => 'Неуспешно генериране на връзка за споделяне';

  @override
  String get reloadingConversations => 'Презареждане на разговори...';

  @override
  String get user => 'Потребител';

  @override
  String get starred => 'Звездичка';

  @override
  String get date => 'Дата';

  @override
  String get noResultsFound => 'Не са намерени резултати';

  @override
  String get tryAdjustingSearchTerms => 'Опитайте да промените условията за търсене';

  @override
  String get starConversationsToFindQuickly => 'Отбележете разговори, за да ги намирате бързо тук';

  @override
  String noConversationsOnDate(String date) {
    return 'Няма разговори на $date';
  }

  @override
  String get trySelectingDifferentDate => 'Опитайте да изберете друга дата';

  @override
  String get conversations => 'Разговори';

  @override
  String get chat => 'Чат';

  @override
  String get actions => 'Действия';

  @override
  String get syncAvailable => 'Налична синхронизация';

  @override
  String get referAFriend => 'Препоръчай на приятел';

  @override
  String get help => 'Помощ';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Надграждане до Pro';

  @override
  String get getOmiDevice => 'Получете устройство Omi';

  @override
  String get wearableAiCompanion => 'Носим AI спътник';

  @override
  String get loadingMemories => 'Зареждане на спомени...';

  @override
  String get allMemories => 'Всички спомени';

  @override
  String get aboutYou => 'За теб';

  @override
  String get manual => 'Ръчни';

  @override
  String get loadingYourMemories => 'Зареждане на вашите спомени...';

  @override
  String get createYourFirstMemory => 'Създайте първия си спомен, за да започнете';

  @override
  String get tryAdjustingFilter => 'Опитайте да промените търсенето или филтъра';

  @override
  String get whatWouldYouLikeToRemember => 'Какво искате да запомните?';

  @override
  String get category => 'Категория';

  @override
  String get public => 'Публичен';

  @override
  String get failedToSaveCheckConnection => 'Неуспешно запазване. Проверете връзката си.';

  @override
  String get createMemory => 'Създай спомен';

  @override
  String get deleteMemoryConfirmation =>
      'Сигурни ли сте, че искате да изтриете този спомен? Това действие не може да бъде отменено.';

  @override
  String get makePrivate => 'Направи частна';

  @override
  String get organizeAndControlMemories => 'Организирайте и контролирайте спомените си';

  @override
  String get total => 'Общо';

  @override
  String get makeAllMemoriesPrivate => 'Направи всички спомени частни';

  @override
  String get setAllMemoriesToPrivate => 'Задай всички спомени като частни';

  @override
  String get makeAllMemoriesPublic => 'Направи всички спомени публични';

  @override
  String get setAllMemoriesToPublic => 'Задай всички спомени като публични';

  @override
  String get permanentlyRemoveAllMemories => 'Премахни трайно всички спомени от Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Всички спомени са вече частни';

  @override
  String get allMemoriesAreNowPublic => 'Всички спомени са вече публични';

  @override
  String get clearOmisMemory => 'Изчисти паметта на Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Сигурни ли сте, че искате да изчистите паметта на Omi? Това действие не може да бъде отменено и ще изтрие трайно всички $count спомена.';
  }

  @override
  String get omisMemoryCleared => 'Паметта на Omi за вас е изчистена';

  @override
  String get welcomeToOmi => 'Добре дошли в Omi';

  @override
  String get continueWithApple => 'Продължи с Apple';

  @override
  String get continueWithGoogle => 'Продължи с Google';

  @override
  String get byContinuingYouAgree => 'Продължавайки, вие се съгласявате с нашите ';

  @override
  String get termsOfService => 'Общи условия';

  @override
  String get and => ' и ';

  @override
  String get dataAndPrivacy => 'Данни и поверителност';

  @override
  String get secureAuthViaAppleId => 'Сигурна автентикация чрез Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Сигурна автентикация чрез Google акаунт';

  @override
  String get whatWeCollect => 'Какво събираме';

  @override
  String get dataCollectionMessage =>
      'Продължавайки, вашите разговори, записи и лична информация ще бъдат съхранявани сигурно на нашите сървъри, за да предоставим прозрения, задвижвани от AI, и да активираме всички функции на приложението.';

  @override
  String get dataProtection => 'Защита на данните';

  @override
  String get yourDataIsProtected => 'Вашите данни са защитени и регулирани от нашата ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Моля, изберете основния си език';

  @override
  String get chooseYourLanguage => 'Изберете вашия език';

  @override
  String get selectPreferredLanguageForBestExperience => 'Изберете предпочитания език за най-добро Omi изживяване';

  @override
  String get searchLanguages => 'Търсене на езици...';

  @override
  String get selectALanguage => 'Изберете език';

  @override
  String get tryDifferentSearchTerm => 'Опитайте с различен термин за търсене';

  @override
  String get pleaseEnterYourName => 'Моля, въведете вашето име';

  @override
  String get nameMustBeAtLeast2Characters => 'Името трябва да съдържа поне 2 знака';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Кажете ни как бихте искали да се обръщаме към вас. Това помага за персонализиране на вашето Omi изживяване.';

  @override
  String charactersCount(int count) {
    return '$count знака';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Активирайте функции за най-доброто Omi изживяване на вашето устройство.';

  @override
  String get microphoneAccess => 'Достъп до микрофон';

  @override
  String get recordAudioConversations => 'Записване на аудио разговори';

  @override
  String get microphoneAccessDescription =>
      'Omi се нуждае от достъп до микрофона, за да записва вашите разговори и да предоставя транскрипции.';

  @override
  String get screenRecording => 'Запис на екрана';

  @override
  String get captureSystemAudioFromMeetings => 'Заснемане на системен звук от срещи';

  @override
  String get screenRecordingDescription =>
      'Omi се нуждае от разрешение за запис на екрана, за да заснема системен звук от вашите срещи в браузъра.';

  @override
  String get accessibility => 'Достъпност';

  @override
  String get detectBrowserBasedMeetings => 'Откриване на срещи в браузъра';

  @override
  String get accessibilityDescription =>
      'Omi се нуждае от разрешение за достъпност, за да открива кога се присъединявате към срещи в Zoom, Meet или Teams във вашия браузър.';

  @override
  String get pleaseWait => 'Моля, изчакайте...';

  @override
  String get joinTheCommunity => 'Присъединете се към общността!';

  @override
  String get loadingProfile => 'Зареждане на профила...';

  @override
  String get profileSettings => 'Настройки на профила';

  @override
  String get noEmailSet => 'Няма зададен имейл';

  @override
  String get userIdCopiedToClipboard => 'Потребителски ID копиран';

  @override
  String get yourInformation => 'Вашата информация';

  @override
  String get setYourName => 'Задайте вашето име';

  @override
  String get changeYourName => 'Променете вашето име';

  @override
  String get manageYourOmiPersona => 'Управлявайте вашата Omi персона';

  @override
  String get voiceAndPeople => 'Глас и Хора';

  @override
  String get teachOmiYourVoice => 'Научете Omi на вашия глас';

  @override
  String get tellOmiWhoSaidIt => 'Кажете на Omi кой го каза 🗣️';

  @override
  String get payment => 'Плащане';

  @override
  String get addOrChangeYourPaymentMethod => 'Добавете или променете метод на плащане';

  @override
  String get preferences => 'Предпочитания';

  @override
  String get helpImproveOmiBySharing =>
      'Помогнете за подобряването на Omi чрез споделяне на анонимизирани данни за анализ';

  @override
  String get deleteAccount => 'Изтриване на Акаунт';

  @override
  String get deleteYourAccountAndAllData => 'Изтрийте вашия акаунт и всички данни';

  @override
  String get clearLogs => 'Изчистване на регистрационни файлове';

  @override
  String get debugLogsCleared => 'Логовете за отстраняване на грешки са изчистени';

  @override
  String get exportConversations => 'Експортиране на разговори';

  @override
  String get exportAllConversationsToJson => 'Експортирайте всички свои разговори в JSON файл.';

  @override
  String get conversationsExportStarted =>
      'Експортирането на разговори започна. Това може да отнеме няколко секунди, моля, изчакайте.';

  @override
  String get mcpDescription =>
      'За свързване на Omi с други приложения за четене, търсене и управление на вашите спомени и разговори. Създайте ключ, за да започнете.';

  @override
  String get apiKeys => 'API ключове';

  @override
  String errorLabel(String error) {
    return 'Грешка: $error';
  }

  @override
  String get noApiKeysFound => 'Не са намерени API ключове. Създайте един, за да започнете.';

  @override
  String get advancedSettings => 'Разширени настройки';

  @override
  String get triggersWhenNewConversationCreated => 'Активира се при създаване на нов разговор.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Активира се при получаване на нов транскрипт.';

  @override
  String get realtimeAudioBytes => 'Аудио байтове в реално време';

  @override
  String get triggersWhenAudioBytesReceived => 'Активира се при получаване на аудио байтове.';

  @override
  String get everyXSeconds => 'На всеки x секунди';

  @override
  String get triggersWhenDaySummaryGenerated => 'Активира се при генериране на дневно резюме.';

  @override
  String get tryLatestExperimentalFeatures => 'Опитайте най-новите експериментални функции от екипа на Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Диагностично състояние на услугата за транскрипция';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Активирайте подробни диагностични съобщения от услугата за транскрипция';

  @override
  String get autoCreateAndTagNewSpeakers => 'Автоматично създаване и маркиране на нови говорители';

  @override
  String get automaticallyCreateNewPerson => 'Автоматично създаване на нов човек при откриване на име в транскрипта.';

  @override
  String get pilotFeatures => 'Пилотни функции';

  @override
  String get pilotFeaturesDescription => 'Тези функции са тестове и не се гарантира поддръжка.';

  @override
  String get suggestFollowUpQuestion => 'Предложете последващ въпрос';

  @override
  String get saveSettings => 'Запази Настройки';

  @override
  String get syncingDeveloperSettings => 'Синхронизиране на настройките за разработчици...';

  @override
  String get summary => 'Резюме';

  @override
  String get auto => 'Автоматично';

  @override
  String get noSummaryForApp =>
      'Няма налично резюме за това приложение. Опитайте друго приложение за по-добри резултати.';

  @override
  String get tryAnotherApp => 'Опитайте друго приложение';

  @override
  String generatedBy(String appName) {
    return 'Генерирано от $appName';
  }

  @override
  String get overview => 'Общ преглед';

  @override
  String get otherAppResults => 'Резултати от други приложения';

  @override
  String get unknownApp => 'Неизвестно приложение';

  @override
  String get noSummaryAvailable => 'Няма налично резюме';

  @override
  String get conversationNoSummaryYet => 'Този разговор все още няма резюме.';

  @override
  String get chooseSummarizationApp => 'Изберете приложение за резюме';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName е зададено като приложение за резюме по подразбиране';
  }

  @override
  String get letOmiChooseAutomatically => 'Нека Omi избере най-доброто приложение автоматично';

  @override
  String get deleteConversationConfirmation =>
      'Сигурни ли сте, че искате да изтриете този разговор? Това действие не може да бъде отменено.';

  @override
  String get conversationDeleted => 'Разговорът е изтрит';

  @override
  String get generatingLink => 'Генериране на връзка...';

  @override
  String get editConversation => 'Редактиране на разговор';

  @override
  String get conversationLinkCopiedToClipboard => 'Връзката към разговора е копирана в клипборда';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Текстът на разговора е копиран в клипборда';

  @override
  String get editConversationDialogTitle => 'Редактиране на разговор';

  @override
  String get changeTheConversationTitle => 'Промяна на заглавието на разговора';

  @override
  String get conversationTitle => 'Заглавие на разговора';

  @override
  String get enterConversationTitle => 'Въведете заглавие на разговора...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Заглавието на разговора е актуализирано успешно';

  @override
  String get failedToUpdateConversationTitle => 'Неуспешна актуализация на заглавието на разговора';

  @override
  String get errorUpdatingConversationTitle => 'Грешка при актуализиране на заглавието на разговора';

  @override
  String get settingUp => 'Настройване...';

  @override
  String get startYourFirstRecording => 'Започнете първия си запис';

  @override
  String get preparingSystemAudioCapture => 'Подготовка на системното аудио заснемане';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Щракнете върху бутона, за да заснемете аудио за реални транскрипции, AI прозрения и автоматично запазване.';

  @override
  String get reconnecting => 'Повторно свързване...';

  @override
  String get recordingPaused => 'Записът е на пауза';

  @override
  String get recordingActive => 'Записът е активен';

  @override
  String get startRecording => 'Започнете запис';

  @override
  String resumingInCountdown(String countdown) {
    return 'Възобновяване след ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Натиснете възпроизвеждане за възобновяване';

  @override
  String get listeningForAudio => 'Слушане за аудио...';

  @override
  String get preparingAudioCapture => 'Подготовка на аудио заснемане';

  @override
  String get clickToBeginRecording => 'Щракнете, за да започнете запис';

  @override
  String get translated => 'преведено';

  @override
  String get liveTranscript => 'Реален транскрипт';

  @override
  String segmentsSingular(String count) {
    return '$count сегмент';
  }

  @override
  String segmentsPlural(String count) {
    return '$count сегмента';
  }

  @override
  String get startRecordingToSeeTranscript => 'Започнете запис, за да видите реален транскрипт';

  @override
  String get paused => 'На пауза';

  @override
  String get initializing => 'Инициализиране...';

  @override
  String get recording => 'Записване';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Микрофонът е сменен. Възобновяване след ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Натиснете възпроизвеждане за възобновяване или стоп за завършване';

  @override
  String get settingUpSystemAudioCapture => 'Настройване на системното аудио заснемане';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Заснемане на аудио и генериране на транскрипт';

  @override
  String get clickToBeginRecordingSystemAudio => 'Щракнете, за да започнете запис на системно аудио';

  @override
  String get you => 'Вие';

  @override
  String speakerWithId(String speakerId) {
    return 'Говорител $speakerId';
  }

  @override
  String get translatedByOmi => 'преведено от omi';

  @override
  String get backToConversations => 'Обратно към разговорите';

  @override
  String get systemAudio => 'Система';

  @override
  String get mic => 'Микрофон';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Аудио входът е зададен на $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Грешка при превключване на аудио устройство: $error';
  }

  @override
  String get selectAudioInput => 'Изберете аудио вход';

  @override
  String get loadingDevices => 'Зареждане на устройства...';

  @override
  String get settingsHeader => 'НАСТРОЙКИ';

  @override
  String get plansAndBilling => 'Планове и Фактуриране';

  @override
  String get calendarIntegration => 'Интеграция на Календар';

  @override
  String get dailySummary => 'Дневно Резюме';

  @override
  String get developer => 'Разработчик';

  @override
  String get about => 'За';

  @override
  String get selectTime => 'Избери Час';

  @override
  String get accountGroup => 'Акаунт';

  @override
  String get signOutQuestion => 'Изход?';

  @override
  String get signOutConfirmation => 'Сигурни ли сте, че искате да излезете?';

  @override
  String get customVocabularyHeader => 'ПЕРСОНАЛИЗИРАН РЕЧНИК';

  @override
  String get addWordsDescription => 'Добавете думи, които Omi трябва да разпознава по време на транскрипция.';

  @override
  String get enterWordsHint => 'Въведете думи (разделени със запетая)';

  @override
  String get dailySummaryHeader => 'ДНЕВНО РЕЗЮМЕ';

  @override
  String get dailySummaryTitle => 'Дневно Резюме';

  @override
  String get dailySummaryDescription => 'Получете персонализирано резюме на разговорите си';

  @override
  String get deliveryTime => 'Време на Доставка';

  @override
  String get deliveryTimeDescription => 'Кога да получавате дневното си резюме';

  @override
  String get subscription => 'Абонамент';

  @override
  String get viewPlansAndUsage => 'Преглед на Планове и Използване';

  @override
  String get viewPlansDescription => 'Управлявайте абонамента си и вижте статистика за използването';

  @override
  String get addOrChangePaymentMethod => 'Добавете или променете метода си за плащане';

  @override
  String get displayOptions => 'Опции за показване';

  @override
  String get showMeetingsInMenuBar => 'Показване на срещи в лентата с менюта';

  @override
  String get displayUpcomingMeetingsDescription => 'Показване на предстоящи срещи в лентата с менюта';

  @override
  String get showEventsWithoutParticipants => 'Показване на събития без участници';

  @override
  String get includePersonalEventsDescription => 'Включване на лични събития без участници';

  @override
  String get upcomingMeetings => 'ПРЕДСТОЯЩИ СРЕЩИ';

  @override
  String get checkingNext7Days => 'Проверка на следващите 7 дни';

  @override
  String get shortcuts => 'Клавишни комбинации';

  @override
  String get shortcutChangeInstruction =>
      'Щракнете върху пряк път, за да го промените. Натиснете Escape, за да отмените.';

  @override
  String get configurePersonaDescription => 'Конфигурирайте вашата AI персона';

  @override
  String get configureSTTProvider => 'Конфигуриране на доставчик на STT';

  @override
  String get setConversationEndDescription => 'Задайте кога разговорите приключват автоматично';

  @override
  String get importDataDescription => 'Импортиране на данни от други източници';

  @override
  String get exportConversationsDescription => 'Експортиране на разговори в JSON';

  @override
  String get exportingConversations => 'Експортиране на разговори...';

  @override
  String get clearNodesDescription => 'Изчистване на всички възли и връзки';

  @override
  String get deleteKnowledgeGraphQuestion => 'Изтриване на графа на знанието?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Това ще изтрие всички производни данни от графа на знанието. Вашите оригинални спомени остават в безопасност.';

  @override
  String get connectOmiWithAI => 'Свържете Omi с AI асистенти';

  @override
  String get noAPIKeys => 'Няма API ключове. Създайте един, за да започнете.';

  @override
  String get autoCreateWhenDetected => 'Автоматично създаване при откриване на име';

  @override
  String get trackPersonalGoals => 'Проследяване на лични цели на началната страница';

  @override
  String get dailyReflectionDescription => 'Напомняне в 21:00 за размисъл над деня ви';

  @override
  String get endpointURL => 'URL на крайна точка';

  @override
  String get links => 'Връзки';

  @override
  String get discordMemberCount => 'Над 8000 членове в Discord';

  @override
  String get userInformation => 'Информация за потребителя';

  @override
  String get capabilities => 'Възможности';

  @override
  String get previewScreenshots => 'Преглед на екранни снимки';

  @override
  String get holdOnPreparingForm => 'Моля, изчакайте, подготвяме формуляра за вас';

  @override
  String get bySubmittingYouAgreeToOmi => 'С изпращането се съгласявате с Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Условия и Политика за поверителност';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Помага за диагностициране на проблеми. Автоматично изтрива след 3 дни.';

  @override
  String get manageYourApp => 'Управление на приложението ви';

  @override
  String get updatingYourApp => 'Актуализиране на приложението ви';

  @override
  String get fetchingYourAppDetails => 'Извличане на детайлите на приложението';

  @override
  String get updateAppQuestion => 'Актуализиране на приложението?';

  @override
  String get updateAppConfirmation =>
      'Сигурни ли сте, че искате да актуализирате приложението си? Промените ще бъдат отразени след преглед от нашия екип.';

  @override
  String get updateApp => 'Актуализиране на приложението';

  @override
  String get createAndSubmitNewApp => 'Създайте и изпратете ново приложение';

  @override
  String appsCount(String count) {
    return 'Приложения ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Лични приложения ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Публични приложения ($count)';
  }

  @override
  String get newVersionAvailable => 'Налична е нова версия  🎉';

  @override
  String get no => 'Не';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Абонаментът е отменен успешно. Той ще остане активен до края на текущия период на фактуриране.';

  @override
  String get failedToCancelSubscription => 'Неуспешно отменяне на абонамента. Моля, опитайте отново.';

  @override
  String get invalidPaymentUrl => 'Невалиден URL за плащане';

  @override
  String get permissionsAndTriggers => 'Разрешения и тригери';

  @override
  String get chatFeatures => 'Функции за чат';

  @override
  String get uninstall => 'Деинсталиране';

  @override
  String get installs => 'ИНСТАЛАЦИИ';

  @override
  String get priceLabel => 'ЦЕНА';

  @override
  String get updatedLabel => 'АКТУАЛИЗИРАНО';

  @override
  String get createdLabel => 'СЪЗДАДЕНО';

  @override
  String get featuredLabel => 'ПРЕПОРЪЧАНО';

  @override
  String get cancelSubscriptionQuestion => 'Отмяна на абонамента?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Сигурни ли сте, че искате да отмените абонамента си? Ще имате достъп до края на текущия период на фактуриране.';

  @override
  String get cancelSubscriptionButton => 'Отмяна на абонамента';

  @override
  String get cancelling => 'Отменяне...';

  @override
  String get betaTesterMessage =>
      'Вие сте бета тестер за това приложение. То все още не е публично. Ще стане публично след одобрение.';

  @override
  String get appUnderReviewMessage =>
      'Вашето приложение е в процес на преглед и е видимо само за вас. Ще стане публично след одобрение.';

  @override
  String get appRejectedMessage =>
      'Вашето приложение беше отхвърлено. Моля, актуализирайте детайлите и изпратете отново за преглед.';

  @override
  String get invalidIntegrationUrl => 'Невалиден URL за интеграция';

  @override
  String get tapToComplete => 'Докоснете за завършване';

  @override
  String get invalidSetupInstructionsUrl => 'Невалиден URL за инструкции за настройка';

  @override
  String get pushToTalk => 'Натисни за говорене';

  @override
  String get summaryPrompt => 'Подкана за обобщение';

  @override
  String get pleaseSelectARating => 'Моля, изберете оценка';

  @override
  String get reviewAddedSuccessfully => 'Отзивът е добавен успешно 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Отзивът е актуализиран успешно 🚀';

  @override
  String get failedToSubmitReview => 'Неуспешно изпращане на отзив. Моля, опитайте отново.';

  @override
  String get addYourReview => 'Добавете вашия отзив';

  @override
  String get editYourReview => 'Редактирайте вашия отзив';

  @override
  String get writeAReviewOptional => 'Напишете отзив (по избор)';

  @override
  String get submitReview => 'Изпрати отзив';

  @override
  String get updateReview => 'Актуализиране на отзива';

  @override
  String get yourReview => 'Вашият отзив';

  @override
  String get anonymousUser => 'Анонимен потребител';

  @override
  String get issueActivatingApp => 'Възникна проблем при активирането на това приложение. Моля, опитайте отново.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Копиране на URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Пон';

  @override
  String get weekdayTue => 'Вт';

  @override
  String get weekdayWed => 'Ср';

  @override
  String get weekdayThu => 'Чет';

  @override
  String get weekdayFri => 'Пет';

  @override
  String get weekdaySat => 'Съб';

  @override
  String get weekdaySun => 'Нед';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Интеграцията с $serviceName предстои';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Вече експортирано към $platform';
  }

  @override
  String get anotherPlatform => 'друга платформа';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Моля, удостоверете се с $serviceName в Настройки > Интеграции на задачи';
  }

  @override
  String addingToService(String serviceName) {
    return 'Добавяне към $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Добавено в $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Неуспешно добавяне към $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Разрешението за Apple Reminders е отказано';

  @override
  String failedToCreateApiKey(String error) {
    return 'Неуспешно създаване на API ключ на доставчика: $error';
  }

  @override
  String get createAKey => 'Създаване на ключ';

  @override
  String get apiKeyRevokedSuccessfully => 'API ключът е отменен успешно';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Неуспешно отменяне на API ключ: $error';
  }

  @override
  String get omiApiKeys => 'Omi API ключове';

  @override
  String get apiKeysDescription =>
      'API ключовете се използват за удостоверяване, когато приложението ви комуникира със сървъра на OMI. Те позволяват на приложението ви да създава спомени и да получава достъп до други услуги на OMI по сигурен начин.';

  @override
  String get aboutOmiApiKeys => 'Относно Omi API ключове';

  @override
  String get yourNewKey => 'Вашият нов ключ:';

  @override
  String get copyToClipboard => 'Копиране в клипборда';

  @override
  String get pleaseCopyKeyNow => 'Моля, копирайте го сега и го запишете на сигурно място. ';

  @override
  String get willNotSeeAgain => 'Няма да можете да го видите отново.';

  @override
  String get revokeKey => 'Отмяна на ключ';

  @override
  String get revokeApiKeyQuestion => 'Отмяна на API ключ?';

  @override
  String get revokeApiKeyWarning =>
      'Това действие не може да бъде отменено. Всички приложения, използващи този ключ, вече няма да имат достъп до API.';

  @override
  String get revoke => 'Отмяна';

  @override
  String get whatWouldYouLikeToCreate => 'Какво искате да създадете?';

  @override
  String get createAnApp => 'Създаване на приложение';

  @override
  String get createAndShareYourApp => 'Създайте и споделете вашето приложение';

  @override
  String get createMyClone => 'Създай моя клонинг';

  @override
  String get createYourDigitalClone => 'Създайте вашия цифров клонинг';

  @override
  String get itemApp => 'Приложение';

  @override
  String get itemPersona => 'Персона';

  @override
  String keepItemPublic(String item) {
    return 'Запази $item публично';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Да се направи $item публично?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Да се направи $item частно?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Ако направите $item публично, то може да се използва от всички';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Ако направите $item частно сега, то ще спре да работи за всички и ще бъде видимо само за вас';
  }

  @override
  String get manageApp => 'Управление на приложението';

  @override
  String get updatePersonaDetails => 'Актуализиране на детайлите на персоната';

  @override
  String deleteItemTitle(String item) {
    return 'Изтриване на $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Изтриване на $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Сигурни ли сте, че искате да изтриете това $item? Това действие не може да бъде отменено.';
  }

  @override
  String get revokeKeyQuestion => 'Отмяна на ключа?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Сигурни ли сте, че искате да отмените ключа \"$keyName\"? Това действие не може да бъде отменено.';
  }

  @override
  String get createNewKey => 'Създаване на нов ключ';

  @override
  String get keyNameHint => 'напр. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Моля, въведете име.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Неуспешно създаване на ключ: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Неуспешно създаване на ключ. Моля, опитайте отново.';

  @override
  String get keyCreated => 'Ключът е създаден';

  @override
  String get keyCreatedMessage =>
      'Вашият нов ключ е създаден. Моля, копирайте го сега. Няма да можете да го видите отново.';

  @override
  String get keyWord => 'Ключ';

  @override
  String get externalAppAccess => 'Достъп на външни приложения';

  @override
  String get externalAppAccessDescription =>
      'Следните инсталирани приложения имат външни интеграции и могат да достъпват данните ви, като разговори и спомени.';

  @override
  String get noExternalAppsHaveAccess => 'Няма външни приложения с достъп до вашите данни.';

  @override
  String get maximumSecurityE2ee => 'Максимална сигурност (E2EE)';

  @override
  String get e2eeDescription =>
      'Криптирането от край до край е златният стандарт за поверителност. Когато е активирано, вашите данни се криптират на вашето устройство, преди да бъдат изпратени до нашите сървъри. Това означава, че никой, дори Omi, не може да получи достъп до вашето съдържание.';

  @override
  String get importantTradeoffs => 'Важни компромиси:';

  @override
  String get e2eeTradeoff1 => '• Някои функции като интеграции с външни приложения може да бъдат деактивирани.';

  @override
  String get e2eeTradeoff2 => '• Ако загубите паролата си, данните ви не могат да бъдат възстановени.';

  @override
  String get featureComingSoon => 'Тази функция идва скоро!';

  @override
  String get migrationInProgressMessage =>
      'Миграцията е в ход. Не можете да промените нивото на защита, докато не приключи.';

  @override
  String get migrationFailed => 'Миграцията неуспешна';

  @override
  String migratingFromTo(String source, String target) {
    return 'Мигриране от $source към $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total обекта';
  }

  @override
  String get secureEncryption => 'Сигурно криптиране';

  @override
  String get secureEncryptionDescription =>
      'Вашите данни са криптирани с ключ, уникален за вас, на нашите сървъри, хоствани в Google Cloud. Това означава, че вашето сурово съдържание е недостъпно за никого, включително персонала на Omi или Google, директно от базата данни.';

  @override
  String get endToEndEncryption => 'Криптиране от край до край';

  @override
  String get e2eeCardDescription =>
      'Активирайте за максимална сигурност, при която само вие имате достъп до данните си. Докоснете, за да научите повече.';

  @override
  String get dataAlwaysEncrypted => 'Независимо от нивото, вашите данни винаги са криптирани в покой и при пренос.';

  @override
  String get readOnlyScope => 'Само за четене';

  @override
  String get fullAccessScope => 'Пълен достъп';

  @override
  String get readScope => 'Четене';

  @override
  String get writeScope => 'Запис';

  @override
  String get apiKeyCreated => 'API ключът е създаден!';

  @override
  String get saveKeyWarning => 'Запазете този ключ сега! Няма да можете да го видите отново.';

  @override
  String get yourApiKey => 'ВАШИЯТ API КЛЮЧ';

  @override
  String get tapToCopy => 'Докоснете за копиране';

  @override
  String get copyKey => 'Копиране на ключа';

  @override
  String get createApiKey => 'Създаване на API ключ';

  @override
  String get accessDataProgrammatically => 'Достъп до данните ви програмно';

  @override
  String get keyNameLabel => 'ИМЕ НА КЛЮЧА';

  @override
  String get keyNamePlaceholder => 'напр., Моята интеграция';

  @override
  String get permissionsLabel => 'РАЗРЕШЕНИЯ';

  @override
  String get permissionsInfoNote => 'R = Четене, W = Запис. По подразбиране само за четене, ако не е избрано нищо.';

  @override
  String get developerApi => 'API за разработчици';

  @override
  String get createAKeyToGetStarted => 'Създайте ключ, за да започнете';

  @override
  String errorWithMessage(String error) {
    return 'Грешка: $error';
  }

  @override
  String get omiTraining => 'Обучение на Omi';

  @override
  String get trainingDataProgram => 'Програма за данни за обучение';

  @override
  String get getOmiUnlimitedFree =>
      'Получете Omi Unlimited безплатно, като допринесете данните си за обучение на AI модели.';

  @override
  String get trainingDataBullets =>
      '• Вашите данни помагат за подобряване на AI модели\n• Споделят се само нечувствителни данни\n• Напълно прозрачен процес';

  @override
  String get learnMoreAtOmiTraining => 'Научете повече на omi.me/training';

  @override
  String get agreeToContributeData => 'Разбирам и се съгласявам да допринеса с данните си за обучение на AI';

  @override
  String get submitRequest => 'Изпрати заявка';

  @override
  String get thankYouRequestUnderReview => 'Благодарим ви! Вашата заявка се разглежда. Ще ви уведомим след одобрение.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Планът ви ще остане активен до $date. След това ще загубите достъп до неограничените функции. Сигурни ли сте?';
  }

  @override
  String get confirmCancellation => 'Потвърдете отказа';

  @override
  String get keepMyPlan => 'Запази плана ми';

  @override
  String get subscriptionSetToCancel => 'Абонаментът ви е настроен да бъде отказан в края на периода.';

  @override
  String get switchedToOnDevice => 'Превключено към транскрипция на устройството';

  @override
  String get couldNotSwitchToFreePlan => 'Не може да се премине към безплатен план. Моля, опитайте отново.';

  @override
  String get couldNotLoadPlans => 'Не може да се заредят наличните планове. Моля, опитайте отново.';

  @override
  String get selectedPlanNotAvailable => 'Избраният план не е наличен. Моля, опитайте отново.';

  @override
  String get upgradeToAnnualPlan => 'Надграждане до годишен план';

  @override
  String get importantBillingInfo => 'Важна информация за фактуриране:';

  @override
  String get monthlyPlanContinues => 'Текущият ви месечен план ще продължи до края на периода на фактуриране';

  @override
  String get paymentMethodCharged =>
      'Съществуващият ви метод на плащане ще бъде таксуван автоматично, когато месечният ви план приключи';

  @override
  String get annualSubscriptionStarts => 'Вашият 12-месечен годишен абонамент ще започне автоматично след таксуването';

  @override
  String get thirteenMonthsCoverage => 'Ще получите общо 13 месеца покритие (текущ месец + 12 месеца годишно)';

  @override
  String get confirmUpgrade => 'Потвърдете надграждането';

  @override
  String get confirmPlanChange => 'Потвърдете промяната на плана';

  @override
  String get confirmAndProceed => 'Потвърди и продължи';

  @override
  String get upgradeScheduled => 'Надграждането е планирано';

  @override
  String get changePlan => 'Промяна на плана';

  @override
  String get upgradeAlreadyScheduled => 'Вашето надграждане до годишен план вече е планирано';

  @override
  String get youAreOnUnlimitedPlan => 'Вие сте на план Неограничен.';

  @override
  String get yourOmiUnleashed => 'Вашият Omi, освободен. Станете неограничени за безкрайни възможности.';

  @override
  String planEndedOn(String date) {
    return 'Планът ви приключи на $date.\\nАбонирайте се отново сега - ще бъдете таксувани незабавно за нов период на фактуриране.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Планът ви е настроен да се отмени на $date.\\nАбонирайте се отново сега, за да запазите предимствата си - без такса до $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Годишният ви план ще започне автоматично, когато месечният ви план приключи.';

  @override
  String planRenewsOn(String date) {
    return 'Планът ви се подновява на $date.';
  }

  @override
  String get unlimitedConversations => 'Неограничени разговори';

  @override
  String get askOmiAnything => 'Попитайте Omi каквото и да е за живота си';

  @override
  String get unlockOmiInfiniteMemory => 'Отключете безкрайната памет на Omi';

  @override
  String get youreOnAnnualPlan => 'Вие сте на годишен план';

  @override
  String get alreadyBestValuePlan => 'Вече имате плана с най-добра стойност. Не са необходими промени.';

  @override
  String get unableToLoadPlans => 'Не може да се заредят планове';

  @override
  String get checkConnectionTryAgain => 'Моля, проверете връзката си и опитайте отново';

  @override
  String get useFreePlan => 'Използвай безплатен план';

  @override
  String get continueText => 'Продължи';

  @override
  String get resubscribe => 'Повторен абонамент';

  @override
  String get couldNotOpenPaymentSettings => 'Не може да се отворят настройките за плащане. Моля, опитайте отново.';

  @override
  String get managePaymentMethod => 'Управление на метод на плащане';

  @override
  String get cancelSubscription => 'Отказ от абонамент';

  @override
  String endsOnDate(String date) {
    return 'Изтича на $date';
  }

  @override
  String get active => 'Активен';

  @override
  String get freePlan => 'Безплатен план';

  @override
  String get configure => 'Конфигуриране';
}
