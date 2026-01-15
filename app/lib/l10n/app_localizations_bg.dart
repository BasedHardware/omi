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
  String get edit => 'Редактирай';

  @override
  String get close => 'Затвори';

  @override
  String get clear => 'Изчисти';

  @override
  String get copyTranscript => 'Копирай транскрипт';

  @override
  String get copySummary => 'Копирай резюме';

  @override
  String get testPrompt => 'Тествай подсказка';

  @override
  String get reprocessConversation => 'Преработи разговор';

  @override
  String get deleteConversation => 'Изтрий разговор';

  @override
  String get contentCopied => 'Съдържанието е копирано в клипборда';

  @override
  String get failedToUpdateStarred => 'Неуспешна актуализация на статуса с отметка.';

  @override
  String get conversationUrlNotShared => 'URL адресът на разговора не можа да бъде споделен.';

  @override
  String get errorProcessingConversation => 'Грешка при обработка на разговора. Моля, опитайте отново по-късно.';

  @override
  String get noInternetConnection => 'Моля, проверете интернет връзката си и опитайте отново.';

  @override
  String get unableToDeleteConversation => 'Невъзможно изтриване на разговор';

  @override
  String get somethingWentWrong => 'Нещо се обърка! Моля, опитайте отново по-късно.';

  @override
  String get copyErrorMessage => 'Копирай съобщение за грешка';

  @override
  String get errorCopied => 'Съобщението за грешка е копирано в клипборда';

  @override
  String get remaining => 'Остават';

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
  String get speechProfile => 'Гласов профил';

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
  String get searching => 'Търсене';

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
  String get noConversationsYet => 'Все още няма разговори.';

  @override
  String get noStarredConversations => 'Все още няма отбелязани разговори.';

  @override
  String get starConversationHint =>
      'За да отбележите разговор, отворете го и натиснете иконката със звезда в заглавието.';

  @override
  String get searchConversations => 'Търсене на разговори';

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
  String get deletingMessages => 'Изтриване на съобщенията ви от паметта на Omi...';

  @override
  String get messageCopied => 'Съобщението е копирано в клипборда.';

  @override
  String get cannotReportOwnMessage => 'Не можете да докладвате собствените си съобщения.';

  @override
  String get reportMessage => 'Докладвай съобщение';

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
  String get searchApps => 'Търсене в над 1500 приложения';

  @override
  String get myApps => 'Моите приложения';

  @override
  String get installedApps => 'Инсталирани приложения';

  @override
  String get unableToFetchApps =>
      'Не могат да се заредят приложенията :(\n\nМоля, проверете интернет връзката си и опитайте отново.';

  @override
  String get aboutOmi => 'Относно Omi';

  @override
  String get privacyPolicy => 'Политика за поверителност';

  @override
  String get visitWebsite => 'Посетете уебсайта';

  @override
  String get helpOrInquiries => 'Помощ или запитвания?';

  @override
  String get joinCommunity => 'Присъединете се към общността!';

  @override
  String get membersAndCounting => '8000+ членове и продължават да се увеличават.';

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
  String get customVocabulary => 'Персонализиран речник';

  @override
  String get identifyingOthers => 'Идентифициране на други';

  @override
  String get paymentMethods => 'Методи на плащане';

  @override
  String get conversationDisplay => 'Показване на разговор';

  @override
  String get dataPrivacy => 'Данни и поверителност';

  @override
  String get userId => 'ID на потребител';

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
  String get signOut => 'Излез';

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
  String get deviceId => 'ID на устройство';

  @override
  String get firmware => 'Фърмуер';

  @override
  String get sdCardSync => 'Синхронизация на SD карта';

  @override
  String get hardwareRevision => 'Хардуерна ревизия';

  @override
  String get modelNumber => 'Модел номер';

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
  String get disconnectDevice => 'Прекъсни устройство';

  @override
  String get unpairDevice => 'Разедини устройство';

  @override
  String get unpairAndForget => 'Разедини и забрави устройство';

  @override
  String get deviceDisconnectedMessage => 'Вашият Omi беше прекъснат 😔';

  @override
  String get deviceUnpairedMessage =>
      'Устройството е разединено. Отидете в Настройки > Bluetooth и забравете устройството, за да завършите разединяването.';

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
  String get createKey => 'Създай ключ';

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
  String get upgradeToUnlimited => 'Надстрой до неограничен';

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
  String get debugLogs => 'Дневници за отстраняване на грешки';

  @override
  String get debugLogsAutoDelete => 'Автоматично се изтриват след 3 дни.';

  @override
  String get debugLogsDesc => 'Помага за диагностициране на проблеми';

  @override
  String get noLogFilesFound => 'Не са намерени файлове с дневници.';

  @override
  String get omiDebugLog => 'Omi дневник за отстраняване на грешки';

  @override
  String get logShared => 'Дневникът е споделен';

  @override
  String get selectLogFile => 'Изберете файл с дневник';

  @override
  String get shareLogs => 'Споделете дневници';

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
  String get knowledgeGraphDeleted => 'Графът на знанията е изтрит успешно';

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
  String get urlCopied => 'URL е копиран';

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
  String get conversationEvents => 'События на разговор';

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
  String get refresh => 'Обнови';

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
  String get noLanguagesFound => 'Не са намерени езици';

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
  String get private => 'Частно';

  @override
  String updatedDate(String date) {
    return 'Актуализиран $date';
  }

  @override
  String get yesterday => 'вчера';

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
  String get saveChanges => 'Запази промени';

  @override
  String get resetToDefault => 'Нулирай по подразбиране';

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
  String get makePublic => 'Направи публично';

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
  String get createApp => 'Създай приложение';

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
  String get dontShowAgain => 'Не го показвай отново';

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
  String get grantPermissions => 'Дайте разрешения';

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
  String get deleteActionItemTitle => 'Изтриване на задача';

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
  String searchMemories(int count) {
    return 'Търсене в $count спомени';
  }

  @override
  String get memoryDeleted => 'Споменът е изтрит.';

  @override
  String get undo => 'Отмени';

  @override
  String get noMemoriesYet => 'Все още няма спомени';

  @override
  String get noAutoMemories => 'Все още няма автоматично извлечени спомени';

  @override
  String get noManualMemories => 'Все още няма ръчно добавени спомени';

  @override
  String get noMemoriesInCategories => 'Няма спомени в тези категории';

  @override
  String get noMemoriesFound => 'Не са намерени спомени';

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
  String get memoryManagement => 'Управление на паметта';

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
  String get newMemory => 'Нов спомен';

  @override
  String get editMemory => 'Редактирай спомен';

  @override
  String get memoryContentHint => 'Обичам да ям сладолед...';

  @override
  String get failedToSaveMemory => 'Неуспешно запазване. Моля, проверете връзката си.';

  @override
  String get saveMemory => 'Запази спомен';

  @override
  String get retry => 'Опитай отново';

  @override
  String get createActionItem => 'Създай задача';

  @override
  String get editActionItem => 'Редактирай задача';

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
  String get failedToDeleteActionItem => 'Неуспешно изтриване на задача';

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
}
