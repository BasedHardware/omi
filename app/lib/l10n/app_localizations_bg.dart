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
      'Това ще изтрие и свързаните спомени, задачи и аудио файлове. Това действие не може да бъде отменено.';

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
  String get copyTranscript => 'Копирай стенограма';

  @override
  String get copySummary => 'Копирай обобщение';

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
  String get clearChat => 'Изчисти чата';

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
  String get integrations => 'Интеграции';

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
  String get wrapped2025 => 'Обобщение 2025';

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
  String get off => 'Изкл';

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
  String get endpointUrl => 'URL адрес на крайна точка';

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
  String get noLogFilesFound => 'Не са намерени лог файлове.';

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
  String get urlCopied => 'URL адресът е копиран';

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
  String get webhooks => 'Уеб куки';

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
  String get connect => 'Свързване';

  @override
  String get comingSoon => 'Скоро';

  @override
  String get integrationsFooter => 'Свържете вашите приложения, за да виждате данни и метрики в чата.';

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
  String get noUpcomingMeetings => 'Няма предстоящи срещи';

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
  String get freeMinutesMonth => '4 800 безплатни минути/месец включени. Неограничено с ';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device използва $reason. Ще се използва Omi.';
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
  String get appName => 'App Name';

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
  String get speechProfileIntro => 'Omi трябва да научи вашите цели и глас. Ще можете да го промените по-късно.';

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
  String get descriptionOptional => 'Описание (незадължително)';

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
  String get conversationUrlCouldNotBeShared => 'URL на разговора не може да бъде споделен.';

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
  String get generateSummary => 'Генерирай обобщение';

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
  String get unknownDevice => 'Неизвестно';

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
    return '$label копирано';
  }

  @override
  String get noApiKeysYet => 'Все още няма API ключове. Създайте един за интеграция с приложението си.';

  @override
  String get createKeyToGetStarted => 'Създайте ключ, за да започнете';

  @override
  String get persona => 'Персона';

  @override
  String get configureYourAiPersona => 'Конфигурирайте вашата AI персона';

  @override
  String get configureSttProvider => 'Конфигуриране на доставчик на STT';

  @override
  String get setWhenConversationsAutoEnd => 'Задайте кога разговорите приключват автоматично';

  @override
  String get importDataFromOtherSources => 'Импортиране на данни от други източници';

  @override
  String get debugAndDiagnostics => 'Отстраняване на грешки и диагностика';

  @override
  String get autoDeletesAfter3Days => 'Автоматично изтриване след 3 дни';

  @override
  String get helpsDiagnoseIssues => 'Помага при диагностицирането на проблеми';

  @override
  String get exportStartedMessage => 'Експортирането започна. Това може да отнеме няколко секунди...';

  @override
  String get exportConversationsToJson => 'Експортиране на разговори в JSON файл';

  @override
  String get knowledgeGraphDeletedSuccess => 'Графът на знанията е изтрит успешно';

  @override
  String failedToDeleteGraph(String error) {
    return 'Неуспешно изтриване на графа: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Изчистване на всички възли и връзки';

  @override
  String get addToClaudeDesktopConfig => 'Добавяне към claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Свържете AI асистенти с вашите данни';

  @override
  String get useYourMcpApiKey => 'Използвайте вашия MCP API ключ';

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
  String get autoCreateWhenNameDetected => 'Автоматично създаване при откриване на име';

  @override
  String get followUpQuestions => 'Последващи въпроси';

  @override
  String get suggestQuestionsAfterConversations => 'Предложете въпроси след разговори';

  @override
  String get goalTracker => 'Проследяване на цели';

  @override
  String get trackPersonalGoalsOnHomepage => 'Проследявайте личните си цели на началната страница';

  @override
  String get dailyReflection => 'Дневна рефлексия';

  @override
  String get get9PmReminderToReflect => 'Получете напомняне в 21:00 да размислите за деня си';

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
  String get editGoal => 'Редактиране на цел';

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
  String get noTasksForToday => 'Няма задачи за днес.\nПопитайте Omi за повече задачи или създайте ръчно.';

  @override
  String get dailyScore => 'ДНЕВЕН РЕЗУЛТАТ';

  @override
  String get dailyScoreDescription => 'Резултат, който ви помага\nда се фокусирате върху изпълнението.';

  @override
  String get searchResults => 'Резултати от търсенето';

  @override
  String get actionItems => 'Действия';

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
  String get timePM => 'сл.об.';

  @override
  String get timeAM => 'пр.об.';

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
  String get installsCount => 'Инсталации';

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
  String get ratingsAndReviews => 'Рейтинги и отзиви';

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
  String get takePhoto => 'Снимай';

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
  String get microphonePermissionRequired => 'Разрешение за микрофон е необходимо за обаждания';

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
  String get discardedConversation => 'Изхвърлен разговор';

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
  String get starred => 'Със звезда';

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
  String get getOmiDevice => 'Вземете Omi устройство';

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
      'Няма налично обобщение за това приложение. Опитайте друго приложение за по-добри резултати.';

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
  String get dailySummary => 'Дневно обобщение';

  @override
  String get developer => 'Разработчик';

  @override
  String get about => 'За';

  @override
  String get selectTime => 'Изберете час';

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
  String get dailySummaryDescription =>
      'Получавайте персонализирано обобщение на разговорите ви за деня като известие.';

  @override
  String get deliveryTime => 'Час на доставка';

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
  String get upcomingMeetings => 'Предстоящи срещи';

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
  String get dailyReflectionDescription =>
      'Получавайте напомняне в 21:00 ч. да размислите за деня си и да запишете мислите си.';

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
  String get summaryPrompt => 'Подсказка за резюме';

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
      'Това приложение ще има достъп до вашите данни. Omi AI не носи отговорност за начина, по който вашите данни се използват, променят или изтриват от това приложение';

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
  String get cancelSubscription => 'Отмени абонамента';

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

  @override
  String get privacyInformation => 'Информация за поверителност';

  @override
  String get yourPrivacyMattersToUs => 'Вашата поверителност е важна за нас';

  @override
  String get privacyIntroText =>
      'В Omi приемаме поверителността ви много сериозно. Искаме да бъдем прозрачни относно данните, които събираме и как ги използваме за подобряване на продукта. Ето какво трябва да знаете:';

  @override
  String get whatWeTrack => 'Какво проследяваме';

  @override
  String get anonymityAndPrivacy => 'Анонимност и поверителност';

  @override
  String get optInAndOptOutOptions => 'Опции за включване и изключване';

  @override
  String get ourCommitment => 'Нашият ангажимент';

  @override
  String get commitmentText =>
      'Ние сме ангажирани да използваме събраните данни само за да направим Omi по-добър продукт за вас. Вашата поверителност и доверие са от първостепенно значение за нас.';

  @override
  String get thankYouText =>
      'Благодарим ви, че сте ценен потребител на Omi. Ако имате въпроси или притеснения, не се колебайте да се свържете с нас на team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Настройки за WiFi синхронизация';

  @override
  String get enterHotspotCredentials => 'Въведете данните за гореща точка на телефона';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi синхронизацията използва телефона ви като гореща точка. Намерете името и паролата в Настройки > Лична гореща точка.';

  @override
  String get hotspotNameSsid => 'Име на гореща точка (SSID)';

  @override
  String get exampleIphoneHotspot => 'напр. iPhone Hotspot';

  @override
  String get password => 'Парола';

  @override
  String get enterHotspotPassword => 'Въведете парола за гореща точка';

  @override
  String get saveCredentials => 'Запазване на данните';

  @override
  String get clearCredentials => 'Изчистване на данните';

  @override
  String get pleaseEnterHotspotName => 'Моля, въведете име на гореща точка';

  @override
  String get wifiCredentialsSaved => 'WiFi данните са запазени';

  @override
  String get wifiCredentialsCleared => 'WiFi данните са изчистени';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Резюмето е генерирано за $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Неуспешно генериране на резюме. Уверете се, че имате разговори за този ден.';

  @override
  String get summaryNotFound => 'Резюмето не е намерено';

  @override
  String get yourDaysJourney => 'Пътуването ви за деня';

  @override
  String get highlights => 'Акценти';

  @override
  String get unresolvedQuestions => 'Нерешени въпроси';

  @override
  String get decisions => 'Решения';

  @override
  String get learnings => 'Научено';

  @override
  String get autoDeletesAfterThreeDays => 'Автоматично се изтрива след 3 дни.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Графът на знанията е изтрит успешно';

  @override
  String get exportStartedMayTakeFewSeconds => 'Експортирането започна. Това може да отнеме няколко секунди...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Това ще изтрие всички производни данни от графа на знанията (възли и връзки). Оригиналните ви спомени ще останат в безопасност. Графът ще бъде възстановен с времето или при следваща заявка.';

  @override
  String get configureDailySummaryDigest => 'Конфигурирайте вашия дневен дайджест на задачите';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Достъп до $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'задействано от $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription и е $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Е $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Няма конфигуриран специфичен достъп до данни.';

  @override
  String get basicPlanDescription => '4 800 премиум минути + неограничено на устройството';

  @override
  String get minutes => 'минути';

  @override
  String get omiHas => 'Omi има:';

  @override
  String get premiumMinutesUsed => 'Използвани премиум минути.';

  @override
  String get setupOnDevice => 'Настройте на устройството';

  @override
  String get forUnlimitedFreeTranscription => 'за неограничен безплатен транскрипт.';

  @override
  String premiumMinsLeft(int count) {
    return 'Остават $count премиум минути.';
  }

  @override
  String get alwaysAvailable => 'винаги налично.';

  @override
  String get importHistory => 'История на импортиране';

  @override
  String get noImportsYet => 'Все още няма импортирания';

  @override
  String get selectZipFileToImport => 'Изберете .zip файл за импортиране!';

  @override
  String get otherDevicesComingSoon => 'Други устройства очаквайте скоро';

  @override
  String get deleteAllLimitlessConversations => 'Изтриване на всички разговори от Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Това ще изтрие завинаги всички разговори, импортирани от Limitless. Това действие не може да бъде отменено.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Изтрити $count разговора от Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Неуспешно изтриване на разговори';

  @override
  String get deleteImportedData => 'Изтриване на импортирани данни';

  @override
  String get statusPending => 'В изчакване';

  @override
  String get statusProcessing => 'Обработва се';

  @override
  String get statusCompleted => 'Завършено';

  @override
  String get statusFailed => 'Неуспешно';

  @override
  String nConversations(int count) {
    return '$count разговора';
  }

  @override
  String get pleaseEnterName => 'Моля, въведете име';

  @override
  String get nameMustBeBetweenCharacters => 'Името трябва да е между 2 и 40 знака';

  @override
  String get deleteSampleQuestion => 'Изтриване на пробата?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Сигурни ли сте, че искате да изтриете пробата на $name?';
  }

  @override
  String get confirmDeletion => 'Потвърдете изтриването';

  @override
  String deletePersonConfirmation(String name) {
    return 'Сигурни ли сте, че искате да изтриете $name? Това ще премахне и всички свързани гласови проби.';
  }

  @override
  String get howItWorksTitle => 'Как работи?';

  @override
  String get howPeopleWorks =>
      'След като създадете човек, можете да отидете в транскрипция на разговор и да му зададете съответните сегменти, така Omi ще може да разпознава и неговата реч!';

  @override
  String get tapToDelete => 'Докоснете за изтриване';

  @override
  String get newTag => 'НОВО';

  @override
  String get needHelpChatWithUs => 'Нуждаете се от помощ? Свържете се с нас';

  @override
  String get localStorageEnabled => 'Локалното хранилище е активирано';

  @override
  String get localStorageDisabled => 'Локалното хранилище е деактивирано';

  @override
  String failedToUpdateSettings(String error) {
    return 'Неуспешно актуализиране на настройките: $error';
  }

  @override
  String get privacyNotice => 'Известие за поверителност';

  @override
  String get recordingsMayCaptureOthers =>
      'Записите могат да уловят гласовете на други хора. Уверете се, че имате съгласието на всички участници преди активиране.';

  @override
  String get enable => 'Активиране';

  @override
  String get storeAudioOnPhone => 'Съхранявай аудио на телефона';

  @override
  String get on => 'Вкл';

  @override
  String get storeAudioDescription =>
      'Съхранявайте всички аудио записи локално на телефона си. Когато е деактивирано, само неуспешните качвания се запазват, за да се спести място.';

  @override
  String get enableLocalStorage => 'Активиране на локално хранилище';

  @override
  String get cloudStorageEnabled => 'Облачното хранилище е активирано';

  @override
  String get cloudStorageDisabled => 'Облачното хранилище е деактивирано';

  @override
  String get enableCloudStorage => 'Активиране на облачно хранилище';

  @override
  String get storeAudioOnCloud => 'Съхранявай аудио в облака';

  @override
  String get cloudStorageDialogMessage =>
      'Вашите записи в реално време ще се съхраняват в частно облачно хранилище, докато говорите.';

  @override
  String get storeAudioCloudDescription =>
      'Съхранявайте записите си в реално време в частно облачно хранилище, докато говорите. Аудиото се улавя и запазва сигурно в реално време.';

  @override
  String get downloadingFirmware => 'Изтегляне на фърмуер';

  @override
  String get installingFirmware => 'Инсталиране на фърмуер';

  @override
  String get firmwareUpdateWarning =>
      'Не затваряйте приложението и не изключвайте устройството. Това може да повреди устройството ви.';

  @override
  String get firmwareUpdated => 'Фърмуерът е актуализиран';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Моля, рестартирайте вашия $deviceName, за да завършите актуализацията.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Вашето устройство е актуално';

  @override
  String get currentVersion => 'Текуща версия';

  @override
  String get latestVersion => 'Последна версия';

  @override
  String get whatsNew => 'Какво ново';

  @override
  String get installUpdate => 'Инсталиране на актуализацията';

  @override
  String get updateNow => 'Актуализирай сега';

  @override
  String get updateGuide => 'Ръководство за актуализация';

  @override
  String get checkingForUpdates => 'Проверка за актуализации';

  @override
  String get checkingFirmwareVersion => 'Проверка на версията на фърмуера...';

  @override
  String get firmwareUpdate => 'Актуализация на фърмуера';

  @override
  String get payments => 'Плащания';

  @override
  String get connectPaymentMethodInfo =>
      'Свържете метод на плащане по-долу, за да започнете да получавате плащания за вашите приложения.';

  @override
  String get selectedPaymentMethod => 'Избран метод на плащане';

  @override
  String get availablePaymentMethods => 'Налични методи за плащане';

  @override
  String get activeStatus => 'Активен';

  @override
  String get connectedStatus => 'Свързан';

  @override
  String get notConnectedStatus => 'Не е свързан';

  @override
  String get setActive => 'Задай като активен';

  @override
  String get getPaidThroughStripe => 'Получавайте плащания за продажбите на вашето приложение чрез Stripe';

  @override
  String get monthlyPayouts => 'Месечни плащания';

  @override
  String get monthlyPayoutsDescription =>
      'Получавайте месечни плащания директно в сметката си, когато достигнете \$10 печалби';

  @override
  String get secureAndReliable => 'Сигурно и надеждно';

  @override
  String get stripeSecureDescription =>
      'Stripe осигурява безопасни и навременни преводи на приходите от вашето приложение';

  @override
  String get selectYourCountry => 'Изберете вашата държава';

  @override
  String get countrySelectionPermanent => 'Изборът на държава е постоянен и не може да бъде променен по-късно.';

  @override
  String get byClickingConnectNow => 'Като щракнете върху \"Свържете се сега\", вие се съгласявате с';

  @override
  String get stripeConnectedAccountAgreement => 'Споразумение за свързан акаунт в Stripe';

  @override
  String get errorConnectingToStripe => 'Грешка при свързване със Stripe! Моля, опитайте отново по-късно.';

  @override
  String get connectingYourStripeAccount => 'Свързване на вашия Stripe акаунт';

  @override
  String get stripeOnboardingInstructions =>
      'Моля, завършете процеса на регистрация в Stripe във вашия браузър. Тази страница ще се актуализира автоматично след завършване.';

  @override
  String get failedTryAgain => 'Неуспешно? Опитайте отново';

  @override
  String get illDoItLater => 'Ще го направя по-късно';

  @override
  String get successfullyConnected => 'Успешно свързано!';

  @override
  String get stripeReadyForPayments =>
      'Вашият Stripe акаунт вече е готов да получава плащания. Можете да започнете да печелите от продажбите на приложението си веднага.';

  @override
  String get updateStripeDetails => 'Актуализиране на детайлите на Stripe';

  @override
  String get errorUpdatingStripeDetails =>
      'Грешка при актуализиране на детайлите на Stripe! Моля, опитайте отново по-късно.';

  @override
  String get updatePayPal => 'Актуализиране на PayPal';

  @override
  String get setUpPayPal => 'Настройка на PayPal';

  @override
  String get updatePayPalAccountDetails => 'Актуализирайте данните на вашия PayPal акаунт';

  @override
  String get connectPayPalToReceivePayments =>
      'Свържете вашия PayPal акаунт, за да започнете да получавате плащания за вашите приложения';

  @override
  String get paypalEmail => 'PayPal имейл';

  @override
  String get paypalMeLink => 'PayPal.me връзка';

  @override
  String get stripeRecommendation =>
      'Ако Stripe е наличен във вашата държава, силно препоръчваме да го използвате за по-бързи и лесни плащания.';

  @override
  String get updatePayPalDetails => 'Актуализиране на детайлите на PayPal';

  @override
  String get savePayPalDetails => 'Запазване на детайлите на PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Моля, въведете вашия PayPal имейл';

  @override
  String get pleaseEnterPayPalMeLink => 'Моля, въведете вашата PayPal.me връзка';

  @override
  String get doNotIncludeHttpInLink => 'Не включвайте http или https или www в връзката';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Моля, въведете валидна PayPal.me връзка';

  @override
  String get pleaseEnterValidEmail => 'Моля, въведете валиден имейл адрес';

  @override
  String get syncingYourRecordings => 'Синхронизиране на записите ви';

  @override
  String get syncYourRecordings => 'Синхронизирай записите си';

  @override
  String get syncNow => 'Синхронизирай сега';

  @override
  String get error => 'Грешка';

  @override
  String get speechSamples => 'Гласови проби';

  @override
  String additionalSampleIndex(String index) {
    return 'Допълнителна проба $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Продължителност: $seconds секунди';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Допълнителната гласова проба е премахната';

  @override
  String get consentDataMessage =>
      'Като продължите, всички данни, които споделяте с това приложение (включително вашите разговори, записи и лична информация), ще бъдат сигурно съхранени на нашите сървъри, за да ви предоставим прозрения с изкуствен интелект и да активираме всички функции на приложението.';

  @override
  String get tasksEmptyStateMessage =>
      'Задачите от вашите разговори ще се появят тук.\nДокоснете + за ръчно създаване.';

  @override
  String get clearChatAction => 'Изчисти чата';

  @override
  String get enableApps => 'Активиране на приложения';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'покажи повече ↓';

  @override
  String get showLess => 'покажи по-малко ↑';

  @override
  String get loadingYourRecording => 'Зареждане на записа...';

  @override
  String get photoDiscardedMessage => 'Тази снимка беше отхвърлена, тъй като не е значима.';

  @override
  String get analyzing => 'Анализиране...';

  @override
  String get searchCountries => 'Търсене на държави';

  @override
  String get checkingAppleWatch => 'Проверка на Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Инсталирайте Omi на вашия\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'За да използвате Apple Watch с Omi, първо трябва да инсталирате приложението Omi на часовника си.';

  @override
  String get openOmiOnAppleWatch => 'Отворете Omi на вашия\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Приложението Omi е инсталирано на вашия Apple Watch. Отворете го и натиснете Старт, за да започнете.';

  @override
  String get openWatchApp => 'Отворете приложението Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Инсталирах и отворих приложението';

  @override
  String get unableToOpenWatchApp =>
      'Не може да се отвори приложението Apple Watch. Моля, отворете ръчно приложението Watch на вашия Apple Watch и инсталирайте Omi от секцията \"Налични приложения\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch е свързан успешно!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch все още не е достъпен. Моля, уверете се, че приложението Omi е отворено на часовника ви.';

  @override
  String errorCheckingConnection(String error) {
    return 'Грешка при проверка на връзката: $error';
  }

  @override
  String get muted => 'Заглушено';

  @override
  String get processNow => 'Обработи сега';

  @override
  String get finishedConversation => 'Приключен разговор?';

  @override
  String get stopRecordingConfirmation => 'Сигурни ли сте, че искате да спрете записа и да обобщите разговора сега?';

  @override
  String get conversationEndsManually => 'Разговорът ще приключи само ръчно.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Разговорът се обобщава след $minutes минут$suffix без говорене.';
  }

  @override
  String get dontAskAgain => 'Не ме питай отново';

  @override
  String get waitingForTranscriptOrPhotos => 'Изчакване на транскрипция или снимки...';

  @override
  String get noSummaryYet => 'Все още няма резюме';

  @override
  String hints(String text) {
    return 'Съвети: $text';
  }

  @override
  String get testConversationPrompt => 'Тест на подсказка за разговор';

  @override
  String get prompt => 'Подкана';

  @override
  String get result => 'Резултат:';

  @override
  String get compareTranscripts => 'Сравни транскрипции';

  @override
  String get notHelpful => 'Не е полезно';

  @override
  String get exportTasksWithOneTap => 'Експортирайте задачи с едно докосване!';

  @override
  String get inProgress => 'В процес';

  @override
  String get photos => 'Снимки';

  @override
  String get rawData => 'Необработени данни';

  @override
  String get content => 'Съдържание';

  @override
  String get noContentToDisplay => 'Няма съдържание за показване';

  @override
  String get noSummary => 'Няма резюме';

  @override
  String get updateOmiFirmware => 'Актуализиране на фърмуера на omi';

  @override
  String get anErrorOccurredTryAgain => 'Възникна грешка. Моля, опитайте отново.';

  @override
  String get welcomeBackSimple => 'Добре дошли отново';

  @override
  String get addVocabularyDescription => 'Добавете думи, които Omi трябва да разпознава по време на транскрипция.';

  @override
  String get enterWordsCommaSeparated => 'Въведете думи (разделени със запетая)';

  @override
  String get whenToReceiveDailySummary => 'Кога да получите дневното си резюме';

  @override
  String get checkingNextSevenDays => 'Проверка на следващите 7 дни';

  @override
  String failedToDeleteError(String error) {
    return 'Неуспешно изтриване: $error';
  }

  @override
  String get developerApiKeys => 'API ключове за разработчици';

  @override
  String get noApiKeysCreateOne => 'Няма API ключове. Създайте един, за да започнете.';

  @override
  String get commandRequired => '⌘ е задължителен';

  @override
  String get spaceKey => 'Интервал';

  @override
  String loadMoreRemaining(String count) {
    return 'Зареди още ($count останали)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Топ $percentile% потребител';
  }

  @override
  String get wrappedMinutes => 'минути';

  @override
  String get wrappedConversations => 'разговори';

  @override
  String get wrappedDaysActive => 'активни дни';

  @override
  String get wrappedYouTalkedAbout => 'Говорихте за';

  @override
  String get wrappedActionItems => 'Задачи';

  @override
  String get wrappedTasksCreated => 'създадени задачи';

  @override
  String get wrappedCompleted => 'завършени';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% степен на завършване';
  }

  @override
  String get wrappedYourTopDays => 'Вашите топ дни';

  @override
  String get wrappedBestMoments => 'Най-добри моменти';

  @override
  String get wrappedMyBuddies => 'Моите приятели';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Не можех да спра да говоря за';

  @override
  String get wrappedShow => 'СЕРИАЛ';

  @override
  String get wrappedMovie => 'ФИЛМ';

  @override
  String get wrappedBook => 'КНИГА';

  @override
  String get wrappedCelebrity => 'ЗНАМЕНИТОСТ';

  @override
  String get wrappedFood => 'ХРАНА';

  @override
  String get wrappedMovieRecs => 'Филмови препоръки за приятели';

  @override
  String get wrappedBiggest => 'Най-голямо';

  @override
  String get wrappedStruggle => 'Предизвикателство';

  @override
  String get wrappedButYouPushedThrough => 'Но се справихте 💪';

  @override
  String get wrappedWin => 'Победа';

  @override
  String get wrappedYouDidIt => 'Успяхте! 🎉';

  @override
  String get wrappedTopPhrases => 'Топ 5 фрази';

  @override
  String get wrappedMins => 'мин';

  @override
  String get wrappedConvos => 'разговори';

  @override
  String get wrappedDays => 'дни';

  @override
  String get wrappedMyBuddiesLabel => 'МОИТЕ ПРИЯТЕЛИ';

  @override
  String get wrappedObsessionsLabel => 'ОБСЕСИИ';

  @override
  String get wrappedStruggleLabel => 'ПРЕДИЗВИКАТЕЛСТВО';

  @override
  String get wrappedWinLabel => 'ПОБЕДА';

  @override
  String get wrappedTopPhrasesLabel => 'ТОП ФРАЗИ';

  @override
  String get wrappedLetsHitRewind => 'Нека превъртим назад твоята';

  @override
  String get wrappedGenerateMyWrapped => 'Генерирай моя Wrapped';

  @override
  String get wrappedProcessingDefault => 'Обработка...';

  @override
  String get wrappedCreatingYourStory => 'Създаваме твоята\nистория за 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Нещо\nсе обърка';

  @override
  String get wrappedAnErrorOccurred => 'Възникна грешка';

  @override
  String get wrappedTryAgain => 'Опитай отново';

  @override
  String get wrappedNoDataAvailable => 'Няма налични данни';

  @override
  String get wrappedOmiLifeRecap => 'Omi преглед на живота';

  @override
  String get wrappedSwipeUpToBegin => 'Плъзни нагоре за начало';

  @override
  String get wrappedShareText => 'Моята 2025, запомнена от Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Споделянето не успя. Моля, опитайте отново.';

  @override
  String get wrappedFailedToStartGeneration => 'Стартирането на генерирането не успя. Моля, опитайте отново.';

  @override
  String get wrappedStarting => 'Стартиране...';

  @override
  String get wrappedShare => 'Сподели';

  @override
  String get wrappedShareYourWrapped => 'Сподели своя Wrapped';

  @override
  String get wrappedMy2025 => 'Моята 2025';

  @override
  String get wrappedRememberedByOmi => 'запомнена от Omi';

  @override
  String get wrappedMostFunDay => 'Най-забавен';

  @override
  String get wrappedMostProductiveDay => 'Най-продуктивен';

  @override
  String get wrappedMostIntenseDay => 'Най-интензивен';

  @override
  String get wrappedFunniestMoment => 'Най-смешен';

  @override
  String get wrappedMostCringeMoment => 'Най-неудобен';

  @override
  String get wrappedMinutesLabel => 'минути';

  @override
  String get wrappedConversationsLabel => 'разговори';

  @override
  String get wrappedDaysActiveLabel => 'активни дни';

  @override
  String get wrappedTasksGenerated => 'създадени задачи';

  @override
  String get wrappedTasksCompleted => 'завършени задачи';

  @override
  String get wrappedTopFivePhrases => 'Топ 5 фрази';

  @override
  String get wrappedAGreatDay => 'Страхотен ден';

  @override
  String get wrappedGettingItDone => 'Свършване на работата';

  @override
  String get wrappedAChallenge => 'Предизвикателство';

  @override
  String get wrappedAHilariousMoment => 'Смешен момент';

  @override
  String get wrappedThatAwkwardMoment => 'Този неловък момент';

  @override
  String get wrappedYouHadFunnyMoments => 'Имахте забавни моменти тази година!';

  @override
  String get wrappedWeveAllBeenThere => 'Всички сме били там!';

  @override
  String get wrappedFriend => 'Приятел';

  @override
  String get wrappedYourBuddy => 'Твоят приятел!';

  @override
  String get wrappedNotMentioned => 'Не е споменато';

  @override
  String get wrappedTheHardPart => 'Трудната част';

  @override
  String get wrappedPersonalGrowth => 'Личностно развитие';

  @override
  String get wrappedFunDay => 'Забавен';

  @override
  String get wrappedProductiveDay => 'Продуктивен';

  @override
  String get wrappedIntenseDay => 'Интензивен';

  @override
  String get wrappedFunnyMomentTitle => 'Смешен момент';

  @override
  String get wrappedCringeMomentTitle => 'Неловък момент';

  @override
  String get wrappedYouTalkedAboutBadge => 'Говорихте за';

  @override
  String get wrappedCompletedLabel => 'Завършено';

  @override
  String get wrappedMyBuddiesCard => 'Моите приятели';

  @override
  String get wrappedBuddiesLabel => 'ПРИЯТЕЛИ';

  @override
  String get wrappedObsessionsLabelUpper => 'УВЛЕЧЕНИЯ';

  @override
  String get wrappedStruggleLabelUpper => 'БОРБА';

  @override
  String get wrappedWinLabelUpper => 'ПОБЕДА';

  @override
  String get wrappedTopPhrasesLabelUpper => 'ТОП ФРАЗИ';

  @override
  String get wrappedYourHeader => 'Твоите';

  @override
  String get wrappedTopDaysHeader => 'Топ дни';

  @override
  String get wrappedYourTopDaysBadge => 'Твоите топ дни';

  @override
  String get wrappedBestHeader => 'Най-добри';

  @override
  String get wrappedMomentsHeader => 'Моменти';

  @override
  String get wrappedBestMomentsBadge => 'Най-добри моменти';

  @override
  String get wrappedBiggestHeader => 'Най-голям';

  @override
  String get wrappedStruggleHeader => 'Борба';

  @override
  String get wrappedWinHeader => 'Победа';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Но ти се справи 💪';

  @override
  String get wrappedYouDidItEmoji => 'Успя! 🎉';

  @override
  String get wrappedHours => 'часове';

  @override
  String get wrappedActions => 'действия';

  @override
  String get multipleSpeakersDetected => 'Открити са множество говорители';

  @override
  String get multipleSpeakersDescription =>
      'Изглежда, че в записа има множество говорители. Моля, уверете се, че сте на тихо място и опитайте отново.';

  @override
  String get invalidRecordingDetected => 'Открит е невалиден запис';

  @override
  String get notEnoughSpeechDescription => 'Не е открита достатъчно реч. Моля, говорете повече и опитайте отново.';

  @override
  String get speechDurationDescription => 'Моля, уверете се, че говорите поне 5 секунди и не повече от 90.';

  @override
  String get connectionLostDescription =>
      'Връзката беше прекъсната. Моля, проверете интернет връзката си и опитайте отново.';

  @override
  String get howToTakeGoodSample => 'Как да направите добра проба?';

  @override
  String get goodSampleInstructions =>
      '1. Уверете се, че сте на тихо място.\n2. Говорете ясно и естествено.\n3. Уверете се, че устройството ви е в естествена позиция на врата ви.\n\nСлед като бъде създаден, винаги можете да го подобрите или направите отново.';

  @override
  String get noDeviceConnectedUseMic => 'Няма свързано устройство. Ще се използва микрофонът на телефона.';

  @override
  String get doItAgain => 'Направи отново';

  @override
  String get listenToSpeechProfile => 'Слушай моя гласов профил ➡️';

  @override
  String get recognizingOthers => 'Разпознаване на други 👀';

  @override
  String get keepGoingGreat => 'Продължавай, справяш се страхотно';

  @override
  String get somethingWentWrongTryAgain => 'Нещо се обърка! Моля, опитайте отново по-късно.';

  @override
  String get uploadingVoiceProfile => 'Качване на гласовия ви профил....';

  @override
  String get memorizingYourVoice => 'Запаметяване на гласа ви...';

  @override
  String get personalizingExperience => 'Персонализиране на вашето изживяване...';

  @override
  String get keepSpeakingUntil100 => 'Продължавайте да говорите до 100%.';

  @override
  String get greatJobAlmostThere => 'Страхотна работа, почти сте готови';

  @override
  String get soCloseJustLittleMore => 'Съвсем малко остава';

  @override
  String get notificationFrequency => 'Честота на известията';

  @override
  String get controlNotificationFrequency => 'Контролирайте колко често Omi ви изпраща проактивни известия.';

  @override
  String get yourScore => 'Вашият резултат';

  @override
  String get dailyScoreBreakdown => 'Разбивка на дневния резултат';

  @override
  String get todaysScore => 'Днешен резултат';

  @override
  String get tasksCompleted => 'Завършени задачи';

  @override
  String get completionRate => 'Процент на завършване';

  @override
  String get howItWorks => 'Как работи';

  @override
  String get dailyScoreExplanation =>
      'Дневният ви резултат се базира на завършените задачи. Завършете задачите си, за да подобрите резултата!';

  @override
  String get notificationFrequencyDescription =>
      'Контролирайте колко често Omi ви изпраща проактивни известия и напомняния.';

  @override
  String get sliderOff => 'Изкл.';

  @override
  String get sliderMax => 'Макс.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Обобщение генерирано за $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Неуспешно генериране на обобщение. Уверете се, че имате разговори за този ден.';

  @override
  String get recap => 'Резюме';

  @override
  String deleteQuoted(String name) {
    return 'Изтриване на \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Преместване на $count разговора в:';
  }

  @override
  String get noFolder => 'Без папка';

  @override
  String get removeFromAllFolders => 'Премахване от всички папки';

  @override
  String get buildAndShareYourCustomApp => 'Създайте и споделете персонализирано приложение';

  @override
  String get searchAppsPlaceholder => 'Търсене в 1500+ приложения';

  @override
  String get filters => 'Филтри';

  @override
  String get frequencyOff => 'Изключено';

  @override
  String get frequencyMinimal => 'Минимално';

  @override
  String get frequencyLow => 'Ниско';

  @override
  String get frequencyBalanced => 'Балансирано';

  @override
  String get frequencyHigh => 'Високо';

  @override
  String get frequencyMaximum => 'Максимално';

  @override
  String get frequencyDescOff => 'Без проактивни известия';

  @override
  String get frequencyDescMinimal => 'Само критични напомняния';

  @override
  String get frequencyDescLow => 'Само важни актуализации';

  @override
  String get frequencyDescBalanced => 'Редовни полезни напомняния';

  @override
  String get frequencyDescHigh => 'Чести проверки';

  @override
  String get frequencyDescMaximum => 'Поддържайте постоянна ангажираност';

  @override
  String get clearChatQuestion => 'Изчисти чата?';

  @override
  String get syncingMessages => 'Синхронизиране на съобщенията със сървъра...';

  @override
  String get chatAppsTitle => 'Чат приложения';

  @override
  String get selectApp => 'Избери приложение';

  @override
  String get noChatAppsEnabled =>
      'Няма активирани чат приложения.\nДокоснете \"Активиране на приложения\" за добавяне.';

  @override
  String get disable => 'Деактивирай';

  @override
  String get photoLibrary => 'Фотогалерия';

  @override
  String get chooseFile => 'Избери файл';

  @override
  String get configureAiPersona => 'Конфигурирай своята AI персона';

  @override
  String get connectAiAssistantsToYourData => 'Свържи AI асистенти към твоите данни';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Следи личните си цели на началната страница';

  @override
  String get deleteRecording => 'Изтрий запис';

  @override
  String get thisCannotBeUndone => 'Това действие не може да бъде отменено.';

  @override
  String get sdCard => 'SD Card';

  @override
  String get fromSd => 'От SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Бърз трансфер';

  @override
  String get syncingStatus => 'Синхронизиране';

  @override
  String get failedStatus => 'Неуспешно';

  @override
  String etaLabel(String time) {
    return 'Очаквано време: $time';
  }

  @override
  String get transferMethod => 'Метод на трансфер';

  @override
  String get fast => 'Бързо';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Телефон';

  @override
  String get cancelSync => 'Отмени синхронизацията';

  @override
  String get cancelSyncMessage => 'Вече изтеглените данни ще бъдат запазени. Можете да продължите по-късно.';

  @override
  String get syncCancelled => 'Синхронизацията е отменена';

  @override
  String get deleteProcessedFiles => 'Изтрий обработените файлове';

  @override
  String get processedFilesDeleted => 'Обработените файлове са изтрити';

  @override
  String get wifiEnableFailed => 'Неуспешно активиране на WiFi на устройството. Моля, опитайте отново.';

  @override
  String get deviceNoFastTransfer => 'Вашето устройство не поддържа бърз трансфер. Използвайте Bluetooth вместо това.';

  @override
  String get enableHotspotMessage => 'Моля, активирайте точката за достъп на телефона си и опитайте отново.';

  @override
  String get transferStartFailed => 'Неуспешно стартиране на трансфера. Моля, опитайте отново.';

  @override
  String get deviceNotResponding => 'Устройството не отговаря. Моля, опитайте отново.';

  @override
  String get invalidWifiCredentials => 'Невалидни WiFi данни. Проверете настройките на точката за достъп.';

  @override
  String get wifiConnectionFailed => 'WiFi връзката е неуспешна. Моля, опитайте отново.';

  @override
  String get sdCardProcessing => 'Обработка на SD карта';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Обработка на $count запис(а). Файловете ще бъдат премахнати от SD картата след това.';
  }

  @override
  String get process => 'Обработи';

  @override
  String get wifiSyncFailed => 'WiFi синхронизацията е неуспешна';

  @override
  String get processingFailed => 'Обработката е неуспешна';

  @override
  String get downloadingFromSdCard => 'Изтегляне от SD карта';

  @override
  String processingProgress(int current, int total) {
    return 'Обработка $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count създадени разговори';
  }

  @override
  String get internetRequired => 'Необходим е интернет';

  @override
  String get processAudio => 'Обработи аудио';

  @override
  String get start => 'Старт';

  @override
  String get noRecordings => 'Няма записи';

  @override
  String get audioFromOmiWillAppearHere => 'Аудиото от вашето Omi устройство ще се появи тук';

  @override
  String get deleteProcessed => 'Изтрий обработените';

  @override
  String get tryDifferentFilter => 'Опитайте с различен филтър';

  @override
  String get recordings => 'Записи';

  @override
  String get enableRemindersAccess =>
      'Моля, активирайте достъпа до Напомняния в Настройки, за да използвате Apple Напомняния';

  @override
  String todayAtTime(String time) {
    return 'Днес в $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Вчера в $time';
  }

  @override
  String get lessThanAMinute => 'По-малко от минута';

  @override
  String estimatedMinutes(int count) {
    return '~$count минута/минути';
  }

  @override
  String estimatedHours(int count) {
    return '~$count час/часа';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Оставащо време: $time';
  }

  @override
  String get summarizingConversation => 'Обобщаване на разговора...\nТова може да отнеме няколко секунди';

  @override
  String get resummarizingConversation => 'Преобобщаване на разговора...\nТова може да отнеме няколко секунди';

  @override
  String get nothingInterestingRetry => 'Не е намерено нищо интересно,\nискате ли да опитате отново?';

  @override
  String get noSummaryForConversation => 'Няма налично обобщение\nза този разговор.';

  @override
  String get unknownLocation => 'Неизвестно местоположение';

  @override
  String get couldNotLoadMap => 'Картата не може да се зареди';

  @override
  String get triggerConversationIntegration => 'Стартиране на интеграция при създаване на разговор';

  @override
  String get webhookUrlNotSet => 'Webhook URL не е зададен';

  @override
  String get setWebhookUrlInSettings =>
      'Моля, задайте Webhook URL в настройките за разработчици, за да използвате тази функция.';

  @override
  String get sendWebUrl => 'Изпрати уеб връзка';

  @override
  String get sendTranscript => 'Изпрати стенограма';

  @override
  String get sendSummary => 'Изпрати обобщение';

  @override
  String get debugModeDetected => 'Открит е режим за отстраняване на грешки';

  @override
  String get performanceReduced => 'Производителността е намалена 5-10 пъти. Използвайте Release режим.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Автоматично затваряне след $secondsс';
  }

  @override
  String get modelRequired => 'Необходим е модел';

  @override
  String get downloadWhisperModel => 'Моля, изтеглете Whisper модел преди запазване.';

  @override
  String get deviceNotCompatible => 'Устройството не е съвместимо';

  @override
  String get deviceRequirements => 'Вашето устройство не отговаря на изискванията за транскрипция на устройството.';

  @override
  String get willLikelyCrash => 'Активирането вероятно ще причини срив или замръзване на приложението.';

  @override
  String get transcriptionSlowerLessAccurate => 'Транскрипцията ще бъде значително по-бавна и по-малко точна.';

  @override
  String get proceedAnyway => 'Продължи въпреки това';

  @override
  String get olderDeviceDetected => 'Открито е по-старо устройство';

  @override
  String get onDeviceSlower => 'Транскрипцията на устройството може да е по-бавна.';

  @override
  String get batteryUsageHigher => 'Консумацията на батерия ще бъде по-висока от облачната транскрипция.';

  @override
  String get considerOmiCloud => 'Помислете за използване на Omi Cloud за по-добра производителност.';

  @override
  String get highResourceUsage => 'Висока консумация на ресурси';

  @override
  String get onDeviceIntensive => 'Транскрипцията на устройството е изчислително интензивна.';

  @override
  String get batteryDrainIncrease => 'Изтощаването на батерията ще се увеличи значително.';

  @override
  String get deviceMayWarmUp => 'Устройството може да се нагрее при продължителна употреба.';

  @override
  String get speedAccuracyLower => 'Скоростта и точността може да бъдат по-ниски от облачните модели.';

  @override
  String get cloudProvider => 'Облачен доставчик';

  @override
  String get premiumMinutesInfo =>
      '4800 премиум минути/месец. Разделът На устройството предлага неограничена безплатна транскрипция.';

  @override
  String get viewUsage => 'Преглед на използването';

  @override
  String get localProcessingInfo =>
      'Аудиото се обработва локално. Работи офлайн, по-поверително, но използва повече батерия.';

  @override
  String get model => 'Модел';

  @override
  String get performanceWarning => 'Предупреждение за производителност';

  @override
  String get largeModelWarning =>
      'Този модел е голям и може да срине приложението или да работи много бавно.\n\nПрепоръчва се \"small\" или \"base\".';

  @override
  String get usingNativeIosSpeech => 'Използване на вградено iOS разпознаване на реч';

  @override
  String get noModelDownloadRequired =>
      'Ще се използва вграденият речеви двигател на устройството. Не е необходимо изтегляне на модел.';

  @override
  String get modelReady => 'Моделът е готов';

  @override
  String get redownload => 'Изтегли отново';

  @override
  String get doNotCloseApp => 'Моля, не затваряйте приложението.';

  @override
  String get downloading => 'Изтегляне...';

  @override
  String get downloadModel => 'Изтегляне на модел';

  @override
  String estimatedSize(String size) {
    return 'Прогнозен размер: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Налично място: $space';
  }

  @override
  String get notEnoughSpace => 'Предупреждение: Няма достатъчно място!';

  @override
  String get download => 'Изтегли';

  @override
  String downloadError(String error) {
    return 'Грешка при изтегляне: $error';
  }

  @override
  String get cancelled => 'Отменено';

  @override
  String get deviceNotCompatibleTitle => 'Устройството не е съвместимо';

  @override
  String get deviceNotMeetRequirements =>
      'Вашето устройство не отговаря на изискванията за транскрипция на устройството.';

  @override
  String get transcriptionSlowerOnDevice => 'Транскрипцията на устройството може да бъде по-бавна на това устройство.';

  @override
  String get computationallyIntensive => 'Транскрипцията на устройството изисква интензивни изчисления.';

  @override
  String get batteryDrainSignificantly => 'Изтощаването на батерията ще се увеличи значително.';

  @override
  String get premiumMinutesMonth =>
      '4800 премиум минути/месец. Разделът На устройството предлага неограничена безплатна транскрипция. ';

  @override
  String get audioProcessedLocally =>
      'Аудиото се обработва локално. Работи офлайн, по-поверително, но консумира повече батерия.';

  @override
  String get languageLabel => 'Език';

  @override
  String get modelLabel => 'Модел';

  @override
  String get modelTooLargeWarning =>
      'Този модел е голям и може да причини срив на приложението или много бавна работа на мобилни устройства.\n\nПрепоръчва се small или base.';

  @override
  String get nativeEngineNoDownload =>
      'Ще се използва вграденият речеви механизъм на устройството. Не е необходимо изтегляне на модел.';

  @override
  String modelReadyWithName(String model) {
    return 'Моделът е готов ($model)';
  }

  @override
  String get reDownload => 'Изтегли отново';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Изтегляне на $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Подготовка на $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Грешка при изтегляне: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Прогнозен размер: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Налично място: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Вградената транскрипция на живо на Omi е оптимизирана за разговори в реално време с автоматично разпознаване и разделяне на говорителите.';

  @override
  String get reset => 'Нулиране';

  @override
  String get useTemplateFrom => 'Използвай шаблон от';

  @override
  String get selectProviderTemplate => 'Изберете шаблон на доставчик...';

  @override
  String get quicklyPopulateResponse => 'Бързо попълване с познат формат на отговор на доставчик';

  @override
  String get quicklyPopulateRequest => 'Бързо попълване с познат формат на заявка на доставчик';

  @override
  String get invalidJsonError => 'Невалиден JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Изтегли модел ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Модел: $model';
  }

  @override
  String get device => 'Устройство';

  @override
  String get chatAssistantsTitle => 'Чат асистенти';

  @override
  String get permissionReadConversations => 'Четене на разговори';

  @override
  String get permissionReadMemories => 'Четене на спомени';

  @override
  String get permissionReadTasks => 'Четене на задачи';

  @override
  String get permissionCreateConversations => 'Създаване на разговори';

  @override
  String get permissionCreateMemories => 'Създаване на спомени';

  @override
  String get permissionTypeAccess => 'Достъп';

  @override
  String get permissionTypeCreate => 'Създаване';

  @override
  String get permissionTypeTrigger => 'Тригер';

  @override
  String get permissionDescReadConversations => 'Това приложение може да достъпва вашите разговори.';

  @override
  String get permissionDescReadMemories => 'Това приложение може да достъпва вашите спомени.';

  @override
  String get permissionDescReadTasks => 'Това приложение може да достъпва вашите задачи.';

  @override
  String get permissionDescCreateConversations => 'Това приложение може да създава нови разговори.';

  @override
  String get permissionDescCreateMemories => 'Това приложение може да създава нови спомени.';

  @override
  String get realtimeListening => 'Слушане в реално време';

  @override
  String get setupCompleted => 'Завършено';

  @override
  String get pleaseSelectRating => 'Моля, изберете рейтинг';

  @override
  String get writeReviewOptional => 'Напишете отзив (по избор)';

  @override
  String get setupQuestionsIntro => 'Помогнете ни да подобрим Omi, като отговорите на няколко въпроса. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. С какво се занимавате?';

  @override
  String get setupQuestionUsage => '2. Къде планирате да използвате вашия Omi?';

  @override
  String get setupQuestionAge => '3. Каква е вашата възрастова група?';

  @override
  String get setupAnswerAllQuestions => 'Все още не сте отговорили на всички въпроси! 🥺';

  @override
  String get setupSkipHelp => 'Пропусни, не искам да помагам :C';

  @override
  String get professionEntrepreneur => 'Предприемач';

  @override
  String get professionSoftwareEngineer => 'Софтуерен инженер';

  @override
  String get professionProductManager => 'Продуктов мениджър';

  @override
  String get professionExecutive => 'Изпълнителен директор';

  @override
  String get professionSales => 'Продажби';

  @override
  String get professionStudent => 'Студент';

  @override
  String get usageAtWork => 'На работа';

  @override
  String get usageIrlEvents => 'Събития на живо';

  @override
  String get usageOnline => 'Онлайн';

  @override
  String get usageSocialSettings => 'В социални ситуации';

  @override
  String get usageEverywhere => 'Навсякъде';

  @override
  String get customBackendUrlTitle => 'Персонализиран URL на сървъра';

  @override
  String get backendUrlLabel => 'URL на сървъра';

  @override
  String get saveUrlButton => 'Запази URL';

  @override
  String get enterBackendUrlError => 'Моля, въведете URL на сървъра';

  @override
  String get urlMustEndWithSlashError => 'URL трябва да завършва с \"/\"';

  @override
  String get invalidUrlError => 'Моля, въведете валиден URL';

  @override
  String get backendUrlSavedSuccess => 'URL на сървъра е запазен успешно!';

  @override
  String get signInTitle => 'Вход';

  @override
  String get signInButton => 'Вход';

  @override
  String get enterEmailError => 'Моля, въведете вашия имейл';

  @override
  String get invalidEmailError => 'Моля, въведете валиден имейл';

  @override
  String get enterPasswordError => 'Моля, въведете вашата парола';

  @override
  String get passwordMinLengthError => 'Паролата трябва да е поне 8 символа';

  @override
  String get signInSuccess => 'Успешен вход!';

  @override
  String get alreadyHaveAccountLogin => 'Вече имате акаунт? Влезте';

  @override
  String get emailLabel => 'Имейл';

  @override
  String get passwordLabel => 'Парола';

  @override
  String get createAccountTitle => 'Създаване на акаунт';

  @override
  String get nameLabel => 'Име';

  @override
  String get repeatPasswordLabel => 'Повторете паролата';

  @override
  String get signUpButton => 'Регистрация';

  @override
  String get enterNameError => 'Моля, въведете името си';

  @override
  String get passwordsDoNotMatch => 'Паролите не съвпадат';

  @override
  String get signUpSuccess => 'Регистрацията е успешна!';

  @override
  String get loadingKnowledgeGraph => 'Зареждане на графа на знанията...';

  @override
  String get noKnowledgeGraphYet => 'Все още няма граф на знанията';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Изграждане на графа на знанията от спомени...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Графът на знанията ще се изгради автоматично, когато създавате нови спомени.';

  @override
  String get buildGraphButton => 'Изграждане на граф';

  @override
  String get checkOutMyMemoryGraph => 'Вижте моя граф на паметта!';

  @override
  String get getButton => 'Вземи';

  @override
  String openingApp(String appName) {
    return 'Отваряне на $appName...';
  }

  @override
  String get writeSomething => 'Напишете нещо';

  @override
  String get submitReply => 'Изпрати отговор';

  @override
  String get editYourReply => 'Редактирай отговора';

  @override
  String get replyToReview => 'Отговори на ревюто';

  @override
  String get rateAndReviewThisApp => 'Оценете и рецензирайте това приложение';

  @override
  String get noChangesInReview => 'Няма промени в отзива за актуализиране.';

  @override
  String get cantRateWithoutInternet => 'Не може да оценявате приложението без интернет връзка.';

  @override
  String get appAnalytics => 'Анализ на приложението';

  @override
  String get learnMoreLink => 'научете повече';

  @override
  String get moneyEarned => 'Спечелени пари';

  @override
  String get writeYourReply => 'Напишете вашия отговор...';

  @override
  String get replySentSuccessfully => 'Отговорът е изпратен успешно';

  @override
  String failedToSendReply(String error) {
    return 'Неуспешно изпращане на отговор: $error';
  }

  @override
  String get send => 'Изпрати';

  @override
  String starFilter(int count) {
    return '$count звезда';
  }

  @override
  String get noReviewsFound => 'Няма намерени отзиви';

  @override
  String get editReply => 'Редактиране на отговор';

  @override
  String get reply => 'Отговор';

  @override
  String starFilterLabel(int count) {
    return '$count звезда';
  }

  @override
  String get sharePublicLink => 'Сподели публична връзка';

  @override
  String get makePersonaPublic => 'Направи персоната публична';

  @override
  String get connectedKnowledgeData => 'Свързани данни от знания';

  @override
  String get enterName => 'Въведете име';

  @override
  String get disconnectTwitter => 'Прекъсни връзката с Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Сигурни ли сте, че искате да прекъснете връзката с Twitter акаунта си? Вашата персона вече няма да има достъп до вашите Twitter данни.';

  @override
  String get getOmiDeviceDescription => 'Създайте по-точен клонинг с вашите лични разговори';

  @override
  String get getOmi => 'Вземете Omi';

  @override
  String get iHaveOmiDevice => 'Имам Omi устройство';

  @override
  String get goal => 'ЦЕЛ';

  @override
  String get tapToTrackThisGoal => 'Докоснете, за да проследите тази цел';

  @override
  String get tapToSetAGoal => 'Докоснете, за да зададете цел';

  @override
  String get processedConversations => 'Обработени разговори';

  @override
  String get updatedConversations => 'Актуализирани разговори';

  @override
  String get newConversations => 'Нови разговори';

  @override
  String get summaryTemplate => 'Шаблон за резюме';

  @override
  String get suggestedTemplates => 'Предложени шаблони';

  @override
  String get otherTemplates => 'Други шаблони';

  @override
  String get availableTemplates => 'Налични шаблони';

  @override
  String get getCreative => 'Бъдете креативни';

  @override
  String get defaultLabel => 'По подразбиране';

  @override
  String get lastUsedLabel => 'Последно използван';

  @override
  String get setDefaultApp => 'Задаване на приложение по подразбиране';

  @override
  String setDefaultAppContent(String appName) {
    return 'Да зададем $appName като ваше приложение за обобщаване по подразбиране?\\n\\nТова приложение ще се използва автоматично за всички бъдещи резюмета на разговори.';
  }

  @override
  String get setDefaultButton => 'Задай по подразбиране';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName е зададено като приложение за обобщаване по подразбиране';
  }

  @override
  String get createCustomTemplate => 'Създаване на персонализиран шаблон';

  @override
  String get allTemplates => 'Всички шаблони';

  @override
  String failedToInstallApp(String appName) {
    return 'Неуспешно инсталиране на $appName. Моля, опитайте отново.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Грешка при инсталиране на $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Маркирай говорител $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Човек с това име вече съществува.';

  @override
  String get selectYouFromList => 'За да маркирате себе си, моля изберете \"Вие\" от списъка.';

  @override
  String get enterPersonsName => 'Въведете име на човека';

  @override
  String get addPerson => 'Добави човек';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Маркирай други сегменти от този говорител ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Маркирай други сегменти';

  @override
  String get managePeople => 'Управлявай хора';

  @override
  String get shareViaSms => 'Споделяне чрез SMS';

  @override
  String get selectContactsToShareSummary => 'Изберете контакти за споделяне на обобщението на разговора';

  @override
  String get searchContactsHint => 'Търсене на контакти...';

  @override
  String contactsSelectedCount(int count) {
    return '$count избрани';
  }

  @override
  String get clearAllSelection => 'Изчисти всичко';

  @override
  String get selectContactsToShare => 'Изберете контакти за споделяне';

  @override
  String shareWithContactCount(int count) {
    return 'Споделяне с $count контакт';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Споделяне с $count контакта';
  }

  @override
  String get contactsPermissionRequired => 'Изисква се разрешение за контакти';

  @override
  String get contactsPermissionRequiredForSms => 'За споделяне чрез SMS е необходимо разрешение за контакти';

  @override
  String get grantContactsPermissionForSms => 'Моля, дайте разрешение за контакти за споделяне чрез SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Не са намерени контакти с телефонни номера';

  @override
  String get noContactsMatchSearch => 'Няма контакти, съответстващи на търсенето';

  @override
  String get failedToLoadContacts => 'Неуспешно зареждане на контакти';

  @override
  String get failedToPrepareConversationForSharing =>
      'Неуспешна подготовка на разговора за споделяне. Моля, опитайте отново.';

  @override
  String get couldNotOpenSmsApp => 'Не можа да се отвори SMS приложението. Моля, опитайте отново.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Ето какво обсъдихме: $link';
  }

  @override
  String get wifiSync => 'WiFi синхронизация';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item копирано в клипборда';
  }

  @override
  String get wifiConnectionFailedTitle => 'Неуспешна връзка';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Свързване с $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Активирай WiFi на $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Свържи се с $deviceName';
  }

  @override
  String get recordingDetails => 'Детайли на записа';

  @override
  String get storageLocationSdCard => 'SD карта';

  @override
  String get storageLocationLimitlessPendant => 'Limitless медальон';

  @override
  String get storageLocationPhone => 'Телефон';

  @override
  String get storageLocationPhoneMemory => 'Телефон (Памет)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Съхранено на $deviceName';
  }

  @override
  String get transferring => 'Прехвърляне...';

  @override
  String get transferRequired => 'Необходимо е прехвърляне';

  @override
  String get downloadingAudioFromSdCard => 'Изтегляне на аудио от SD картата на устройството ви';

  @override
  String get transferRequiredDescription =>
      'Този запис се съхранява на SD картата на вашето устройство. Прехвърлете го на телефона си, за да го слушате или споделите.';

  @override
  String get cancelTransfer => 'Отмени прехвърлянето';

  @override
  String get transferToPhone => 'Прехвърли на телефона';

  @override
  String get privateAndSecureOnDevice => 'Лично и сигурно на вашето устройство';

  @override
  String get recordingInfo => 'Информация за записа';

  @override
  String get transferInProgress => 'Прехвърлянето е в ход...';

  @override
  String get shareRecording => 'Сподели записа';

  @override
  String get deleteRecordingConfirmation =>
      'Сигурни ли сте, че искате да изтриете окончателно този запис? Това не може да бъде отменено.';

  @override
  String get recordingIdLabel => 'ID на записа';

  @override
  String get dateTimeLabel => 'Дата и час';

  @override
  String get durationLabel => 'Продължителност';

  @override
  String get audioFormatLabel => 'Аудио формат';

  @override
  String get storageLocationLabel => 'Място на съхранение';

  @override
  String get estimatedSizeLabel => 'Приблизителен размер';

  @override
  String get deviceModelLabel => 'Модел на устройството';

  @override
  String get deviceIdLabel => 'ID на устройството';

  @override
  String get statusLabel => 'Статус';

  @override
  String get statusProcessed => 'Обработен';

  @override
  String get statusUnprocessed => 'Необработен';

  @override
  String get switchedToFastTransfer => 'Превключено на бърз трансфер';

  @override
  String get transferCompleteMessage => 'Прехвърлянето е завършено! Вече можете да слушате този запис.';

  @override
  String transferFailedMessage(String error) {
    return 'Прехвърлянето е неуспешно: $error';
  }

  @override
  String get transferCancelled => 'Прехвърлянето е отменено';

  @override
  String get fastTransferEnabled => 'Бързият трансфер е активиран';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth синхронизацията е активирана';

  @override
  String get enableFastTransfer => 'Активиране на бърз трансфер';

  @override
  String get fastTransferDescription =>
      'Бързият трансфер използва WiFi за ~5 пъти по-бързи скорости. Телефонът ви временно ще се свърже с WiFi мрежата на вашето Omi устройство по време на трансфер.';

  @override
  String get internetAccessPausedDuringTransfer => 'Достъпът до интернет е на пауза по време на трансфер';

  @override
  String get chooseTransferMethodDescription =>
      'Изберете как записите да се прехвърлят от вашето Omi устройство на телефона.';

  @override
  String get wifiSpeed => '~150 KB/s чрез WiFi';

  @override
  String get fiveTimesFaster => '5 ПЪТИ ПО-БЪРЗО';

  @override
  String get fastTransferMethodDescription =>
      'Създава директна WiFi връзка с вашето Omi устройство. Телефонът ви временно се изключва от обичайната WiFi мрежа по време на трансфер.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s чрез BLE';

  @override
  String get bluetoothMethodDescription =>
      'Използва стандартна Bluetooth Low Energy връзка. По-бавно, но не засяга WiFi връзката ви.';

  @override
  String get selected => 'Избрано';

  @override
  String get selectOption => 'Избери';

  @override
  String get lowBatteryAlertTitle => 'Предупреждение за изтощена батерия';

  @override
  String get lowBatteryAlertBody => 'Батерията на устройството ви е изтощена. Време е за презареждане! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Вашето Omi устройство е изключено';

  @override
  String get deviceDisconnectedNotificationBody => 'Моля, свържете се отново, за да продължите да използвате Omi.';

  @override
  String get firmwareUpdateAvailable => 'Налична е актуализация на фърмуера';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Налична е нова актуализация на фърмуера ($version) за вашето Omi устройство. Искате ли да актуализирате сега?';
  }

  @override
  String get later => 'По-късно';

  @override
  String get appDeletedSuccessfully => 'Приложението е изтрито успешно';

  @override
  String get appDeleteFailed => 'Неуспешно изтриване на приложението. Моля, опитайте отново по-късно.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Видимостта на приложението е променена успешно. Може да отнеме няколко минути.';

  @override
  String get errorActivatingAppIntegration =>
      'Грешка при активиране на приложението. Ако е интеграционно приложение, уверете се, че настройката е завършена.';

  @override
  String get errorUpdatingAppStatus => 'Възникна грешка при актуализиране на състоянието на приложението.';

  @override
  String get calculatingETA => 'Изчисляване...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Остават около $minutes минути';
  }

  @override
  String get aboutAMinuteRemaining => 'Остава около минута';

  @override
  String get almostDone => 'Почти готово...';

  @override
  String get omiSays => 'omi казва';

  @override
  String get analyzingYourData => 'Анализиране на вашите данни...';

  @override
  String migratingToProtection(String level) {
    return 'Мигриране към $level защита...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Няма данни за миграция. Завършване...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Мигриране на $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Всички обекти са мигрирани. Завършване...';

  @override
  String get migrationErrorOccurred => 'Възникна грешка по време на миграцията. Моля, опитайте отново.';

  @override
  String get migrationComplete => 'Миграцията е завършена!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Вашите данни вече са защитени с новите $level настройки.';
  }

  @override
  String get chatsLowercase => 'чатове';

  @override
  String get dataLowercase => 'данни';

  @override
  String get fallNotificationTitle => 'Ох';

  @override
  String get fallNotificationBody => 'Паднахте ли?';

  @override
  String get importantConversationTitle => 'Важен разговор';

  @override
  String get importantConversationBody =>
      'Току-що проведохте важен разговор. Докоснете, за да споделите резюмето с други.';

  @override
  String get templateName => 'Име на шаблон';

  @override
  String get templateNameHint => 'напр. Екстрактор на действия от среща';

  @override
  String get nameMustBeAtLeast3Characters => 'Името трябва да е поне 3 символа';

  @override
  String get conversationPromptHint =>
      'напр. Извлечете действия, взети решения и ключови изводи от предоставения разговор.';

  @override
  String get pleaseEnterAppPrompt => 'Моля, въведете подсказка за вашето приложение';

  @override
  String get promptMustBeAtLeast10Characters => 'Подсказката трябва да е поне 10 символа';

  @override
  String get anyoneCanDiscoverTemplate => 'Всеки може да открие вашия шаблон';

  @override
  String get onlyYouCanUseTemplate => 'Само вие можете да използвате този шаблон';

  @override
  String get generatingDescription => 'Генериране на описание...';

  @override
  String get creatingAppIcon => 'Създаване на икона...';

  @override
  String get installingApp => 'Инсталиране на приложението...';

  @override
  String get appCreatedAndInstalled => 'Приложението е създадено и инсталирано!';

  @override
  String get appCreatedSuccessfully => 'Приложението е създадено успешно!';

  @override
  String get failedToCreateApp => 'Неуспешно създаване. Моля, опитайте отново.';

  @override
  String get addAppSelectCoreCapability => 'Моля, изберете още една основна способност за вашето приложение';

  @override
  String get addAppSelectPaymentPlan => 'Моля, изберете план за плащане и въведете цена за вашето приложение';

  @override
  String get addAppSelectCapability => 'Моля, изберете поне една способност за вашето приложение';

  @override
  String get addAppSelectLogo => 'Моля, изберете лого за вашето приложение';

  @override
  String get addAppEnterChatPrompt => 'Моля, въведете чат подкана за вашето приложение';

  @override
  String get addAppEnterConversationPrompt => 'Моля, въведете подкана за разговор за вашето приложение';

  @override
  String get addAppSelectTriggerEvent => 'Моля, изберете задействащо събитие за вашето приложение';

  @override
  String get addAppEnterWebhookUrl => 'Моля, въведете webhook URL за вашето приложение';

  @override
  String get addAppSelectCategory => 'Моля, изберете категория за вашето приложение';

  @override
  String get addAppFillRequiredFields => 'Моля, попълнете правилно всички задължителни полета';

  @override
  String get addAppUpdatedSuccess => 'Приложението е актуализирано успешно 🚀';

  @override
  String get addAppUpdateFailed => 'Актуализацията е неуспешна. Опитайте по-късно';

  @override
  String get addAppSubmittedSuccess => 'Приложението е изпратено успешно 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Грешка при отваряне на избора на файлове: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Грешка при избор на изображение: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Разрешението за снимки е отказано. Разрешете достъп до снимки';

  @override
  String get addAppErrorSelectingImageRetry => 'Грешка при избор на изображение. Опитайте отново.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Грешка при избор на миниатюра: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Грешка при избор на миниатюра. Опитайте отново.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Други способности не могат да бъдат избрани с Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona не може да бъде избрана с други способности';

  @override
  String get personaTwitterHandleNotFound => 'Twitter акаунт не е намерен';

  @override
  String get personaTwitterHandleSuspended => 'Twitter акаунтът е спрян';

  @override
  String get personaFailedToVerifyTwitter => 'Неуспешна проверка на Twitter акаунт';

  @override
  String get personaFailedToFetch => 'Неуспешно извличане на вашата персона';

  @override
  String get personaFailedToCreate => 'Неуспешно създаване на персона';

  @override
  String get personaConnectKnowledgeSource => 'Моля, свържете поне един източник на данни (Omi или Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Персоната е актуализирана успешно';

  @override
  String get personaFailedToUpdate => 'Неуспешна актуализация на персона';

  @override
  String get personaPleaseSelectImage => 'Моля, изберете изображение';

  @override
  String get personaFailedToCreateTryLater => 'Неуспешно създаване на персона. Опитайте по-късно.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Неуспешно създаване на персона: $error';
  }

  @override
  String get personaFailedToEnable => 'Неуспешно активиране на персона';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Грешка при активиране на персона: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Неуспешно извличане на поддържани държави. Опитайте по-късно.';

  @override
  String get paymentFailedToSetDefault => 'Неуспешно задаване на метод за плащане по подразбиране. Опитайте по-късно.';

  @override
  String get paymentFailedToSavePaypal => 'Неуспешно запазване на PayPal данни. Опитайте по-късно.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Активен';

  @override
  String get paymentStatusConnected => 'Свързан';

  @override
  String get paymentStatusNotConnected => 'Несвързан';

  @override
  String get paymentAppCost => 'Цена на приложение';

  @override
  String get paymentEnterValidAmount => 'Моля, въведете валидна сума';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Моля, въведете сума по-голяма от 0';

  @override
  String get paymentPlan => 'План за плащане';

  @override
  String get paymentNoneSelected => 'Нищо не е избрано';

  @override
  String get aiGenPleaseEnterDescription => 'Моля, въведете описание за вашето приложение';

  @override
  String get aiGenCreatingAppIcon => 'Създаване на икона на приложението...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Възникна грешка: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Приложението е създадено успешно!';

  @override
  String get aiGenFailedToCreateApp => 'Неуспешно създаване на приложение';

  @override
  String get aiGenErrorWhileCreatingApp => 'Възникна грешка при създаването на приложението';

  @override
  String get aiGenFailedToGenerateApp => 'Неуспешно генериране на приложение. Моля, опитайте отново.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Неуспешно регенериране на иконата';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Моля, първо генерирайте приложение';

  @override
  String get xHandleTitle => 'Какъв е вашият X профил?';

  @override
  String get xHandleDescription =>
      'Ще предварително обучим вашия Omi клонинг\nвъз основа на активността на вашия акаунт';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Моля, въведете вашия X профил';

  @override
  String get xHandlePleaseEnterValid => 'Моля, въведете валиден X профил';

  @override
  String get nextButton => 'Напред';

  @override
  String get connectOmiDevice => 'Свържете Omi устройство';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Превключвате вашия Unlimited план към $title. Сигурни ли сте, че искате да продължите?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Надграждането е планирано! Вашият месечен план продължава до края на периода за фактуриране, след което автоматично преминава към годишен.';

  @override
  String get couldNotSchedulePlanChange => 'Не можахме да планираме промяна на плана. Моля, опитайте отново.';

  @override
  String get subscriptionReactivatedDefault =>
      'Вашият абонамент е активиран отново! Без такса сега - ще бъдете таксувани в края на текущия период.';

  @override
  String get subscriptionSuccessfulCharged => 'Абонаментът е успешен! Таксувани сте за новия период на фактуриране.';

  @override
  String get couldNotProcessSubscription => 'Не можахме да обработим абонамента. Моля, опитайте отново.';

  @override
  String get couldNotLaunchUpgradePage => 'Не можахме да отворим страницата за надграждане. Моля, опитайте отново.';

  @override
  String get transcriptionJsonPlaceholder => 'Поставете вашата JSON конфигурация тук...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Грешка при отваряне на избирача на файлове: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Грешка: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Разговорите са обединени успешно';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count разговора бяха обединени успешно';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Време за дневна рефлексия';

  @override
  String get dailyReflectionNotificationBody => 'Разкажи ми за деня си';

  @override
  String get actionItemReminderTitle => 'Напомняне от Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName е изключен';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Моля, свържете се отново, за да продължите да използвате вашето $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Вход';

  @override
  String get onboardingYourName => 'Вашето име';

  @override
  String get onboardingLanguage => 'Език';

  @override
  String get onboardingPermissions => 'Разрешения';

  @override
  String get onboardingComplete => 'Завършено';

  @override
  String get onboardingWelcomeToOmi => 'Добре дошли в Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Разкажете ни за себе си';

  @override
  String get onboardingChooseYourPreference => 'Изберете предпочитанието си';

  @override
  String get onboardingGrantRequiredAccess => 'Дайте необходимия достъп';

  @override
  String get onboardingYoureAllSet => 'Всичко е готово';

  @override
  String get searchTranscriptOrSummary => 'Търсене в транскрипция или резюме...';

  @override
  String get myGoal => 'Моята цел';

  @override
  String get appNotAvailable => 'Опа! Изглежда, че приложението, което търсите, не е налично.';

  @override
  String get failedToConnectTodoist => 'Неуспешно свързване с Todoist';

  @override
  String get failedToConnectAsana => 'Неуспешно свързване с Asana';

  @override
  String get failedToConnectGoogleTasks => 'Неуспешно свързване с Google Tasks';

  @override
  String get failedToConnectClickUp => 'Неуспешно свързване с ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Неуспешно свързване с $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Успешно свързване с Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Неуспешно свързване с Todoist. Моля, опитайте отново.';

  @override
  String get successfullyConnectedAsana => 'Успешно свързване с Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Неуспешно свързване с Asana. Моля, опитайте отново.';

  @override
  String get successfullyConnectedGoogleTasks => 'Успешно свързване с Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Неуспешно свързване с Google Tasks. Моля, опитайте отново.';

  @override
  String get successfullyConnectedClickUp => 'Успешно свързване с ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Неуспешно свързване с ClickUp. Моля, опитайте отново.';

  @override
  String get successfullyConnectedNotion => 'Успешно свързване с Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Неуспешно обновяване на състоянието на връзката с Notion.';

  @override
  String get successfullyConnectedGoogle => 'Успешно свързване с Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Неуспешно обновяване на състоянието на връзката с Google.';

  @override
  String get successfullyConnectedWhoop => 'Успешно свързване с Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Неуспешно обновяване на състоянието на връзката с Whoop.';

  @override
  String get successfullyConnectedGitHub => 'Успешно свързване с GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Неуспешно обновяване на състоянието на връзката с GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'Неуспешно влизане с Google, моля опитайте отново.';

  @override
  String get authenticationFailed => 'Удостоверяването е неуспешно. Моля, опитайте отново.';

  @override
  String get authFailedToSignInWithApple => 'Неуспешно влизане с Apple, моля опитайте отново.';

  @override
  String get authFailedToRetrieveToken => 'Неуспешно извличане на Firebase токен, моля опитайте отново.';

  @override
  String get authUnexpectedErrorFirebase => 'Неочаквана грешка при влизане, грешка на Firebase, моля опитайте отново.';

  @override
  String get authUnexpectedError => 'Неочаквана грешка при влизане, моля опитайте отново';

  @override
  String get authFailedToLinkGoogle => 'Неуспешно свързване с Google, моля опитайте отново.';

  @override
  String get authFailedToLinkApple => 'Неуспешно свързване с Apple, моля опитайте отново.';

  @override
  String get onboardingBluetoothRequired => 'За свързване с вашето устройство е необходимо разрешение за Bluetooth.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Разрешението за Bluetooth е отказано. Моля, дайте разрешение в Системни настройки.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Състояние на разрешението за Bluetooth: $status. Моля, проверете Системни настройки.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Неуспешна проверка на разрешението за Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Разрешението за известия е отказано. Моля, дайте разрешение в Системни настройки.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Разрешението за известия е отказано. Моля, дайте разрешение в Системни настройки > Известия.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Състояние на разрешението за известия: $status. Моля, проверете Системни настройки.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Неуспешна проверка на разрешението за известия: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Моля, дайте разрешение за местоположение в Настройки > Поверителност и сигурност > Услуги за местоположение';

  @override
  String get onboardingMicrophoneRequired => 'За запис е необходимо разрешение за микрофон.';

  @override
  String get onboardingMicrophoneDenied =>
      'Разрешението за микрофон е отказано. Моля, дайте разрешение в Системни настройки > Поверителност и сигурност > Микрофон.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Състояние на разрешението за микрофон: $status. Моля, проверете Системни настройки.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Неуспешна проверка на разрешението за микрофон: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'За запис на системен звук е необходимо разрешение за заснемане на екран.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Разрешението за заснемане на екран е отказано. Моля, дайте разрешение в Системни настройки > Поверителност и сигурност > Запис на екран.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Състояние на разрешението за заснемане на екран: $status. Моля, проверете Системни настройки.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Неуспешна проверка на разрешението за заснемане на екран: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'За откриване на срещи в браузъра е необходимо разрешение за достъпност.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Състояние на разрешението за достъпност: $status. Моля, проверете Системни настройки.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Неуспешна проверка на разрешението за достъпност: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Заснемането с камера не е налично на тази платформа';

  @override
  String get msgCameraPermissionDenied => 'Достъпът до камерата е отказан. Моля, разрешете достъп до камерата';

  @override
  String msgCameraAccessError(String error) {
    return 'Грешка при достъп до камерата: $error';
  }

  @override
  String get msgPhotoError => 'Грешка при заснемане на снимка. Моля, опитайте отново.';

  @override
  String get msgMaxImagesLimit => 'Можете да изберете най-много 4 изображения';

  @override
  String msgFilePickerError(String error) {
    return 'Грешка при отваряне на избирача на файлове: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Грешка при избиране на изображения: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Достъпът до снимки е отказан. Моля, разрешете достъп до снимки, за да изберете изображения';

  @override
  String get msgSelectImagesGenericError => 'Грешка при избиране на изображения. Моля, опитайте отново.';

  @override
  String get msgMaxFilesLimit => 'Можете да изберете най-много 4 файла';

  @override
  String msgSelectFilesError(String error) {
    return 'Грешка при избиране на файлове: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Грешка при избиране на файлове. Моля, опитайте отново.';

  @override
  String get msgUploadFileFailed => 'Качването на файла се провали, моля опитайте отново по-късно';

  @override
  String get msgReadingMemories => 'Четене на вашите спомени...';

  @override
  String get msgLearningMemories => 'Учене от вашите спомени...';

  @override
  String get msgUploadAttachedFileFailed => 'Качването на прикачения файл се провали.';

  @override
  String captureRecordingError(String error) {
    return 'Възникна грешка по време на записа: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Записът спря: $reason. Може да се наложи да свържете отново външните дисплеи или да рестартирате записа.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Изисква се разрешение за микрофон';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Дайте разрешение за микрофон в Системни предпочитания';

  @override
  String get captureScreenRecordingPermissionRequired => 'Изисква се разрешение за запис на екрана';

  @override
  String get captureDisplayDetectionFailed => 'Откриването на дисплея е неуспешно. Записът е спрян.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Невалиден URL адрес на уебхук за аудио байтове';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl =>
      'Невалиден URL адрес на уебхук за транскрипция в реално време';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Невалиден URL адрес на уебхук за създаден разговор';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Невалиден URL адрес на уебхук за дневно обобщение';

  @override
  String get devModeSettingsSaved => 'Настройките са запазени!';

  @override
  String get voiceFailedToTranscribe => 'Неуспешно транскрибиране на аудио';

  @override
  String get locationPermissionRequired => 'Необходимо е разрешение за местоположение';

  @override
  String get locationPermissionContent =>
      'Разрешението за местоположение е необходимо, за да съхранявате местоположението на вашите разговори в приложението.';

  @override
  String get pdfTranscriptExport => 'Експорт на транскрипт';

  @override
  String get pdfConversationExport => 'Експорт на разговор';

  @override
  String pdfTitleLabel(String title) {
    return 'Заглавие: $title';
  }

  @override
  String get conversationNewIndicator => 'Нов';

  @override
  String conversationPhotosCount(int count) {
    return '$count снимки';
  }

  @override
  String get mergingStatus => 'Сливане...';

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
    return '$count мин';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count мин';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins мин $secs сек';
  }

  @override
  String timeHourSingular(int count) {
    return '$count час';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count часа';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours часа $mins мин';
  }

  @override
  String timeDaySingular(int count) {
    return '$count ден';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count дни';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days дни $hours часа';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countс';
  }

  @override
  String timeCompactMins(int count) {
    return '$countм';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsм $secsс';
  }

  @override
  String timeCompactHours(int count) {
    return '$countч';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursч $minsм';
  }

  @override
  String get moveToFolder => 'Преместване в папка';

  @override
  String get noFoldersAvailable => 'Няма налични папки';

  @override
  String get newFolder => 'Нова папка';

  @override
  String get color => 'Цвят';

  @override
  String get waitingForDevice => 'Изчаква се устройство...';

  @override
  String get saySomething => 'Кажете нещо...';

  @override
  String get initialisingSystemAudio => 'Инициализиране на системното аудио';

  @override
  String get stopRecording => 'Спиране на записа';

  @override
  String get continueRecording => 'Продължаване на записа';

  @override
  String get initialisingRecorder => 'Инициализиране на записващото устройство';

  @override
  String get pauseRecording => 'Пауза на записа';

  @override
  String get resumeRecording => 'Възобновяване на записа';

  @override
  String get noDailyRecapsYet => 'Все още няма дневни обобщения';

  @override
  String get dailyRecapsDescription => 'Вашите дневни обобщения ще се появят тук, след като бъдат генерирани';

  @override
  String get chooseTransferMethod => 'Изберете метод на прехвърляне';

  @override
  String get fastTransferSpeed => '~150 KB/s чрез WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Открита е голяма времева разлика ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Открити са големи времеви разлики ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Устройството не поддържа WiFi синхронизация, превключване към Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health не е налично на това устройство';

  @override
  String get downloadAudio => 'Изтегляне на аудио';

  @override
  String get audioDownloadSuccess => 'Аудиото е изтеглено успешно';

  @override
  String get audioDownloadFailed => 'Неуспешно изтегляне на аудио';

  @override
  String get downloadingAudio => 'Изтегляне на аудио...';

  @override
  String get shareAudio => 'Споделяне на аудио';

  @override
  String get preparingAudio => 'Подготовка на аудио';

  @override
  String get gettingAudioFiles => 'Получаване на аудио файлове...';

  @override
  String get downloadingAudioProgress => 'Изтегляне на аудио';

  @override
  String get processingAudio => 'Обработка на аудио';

  @override
  String get combiningAudioFiles => 'Комбиниране на аудио файлове...';

  @override
  String get audioReady => 'Аудиото е готово';

  @override
  String get openingShareSheet => 'Отваряне на страницата за споделяне...';

  @override
  String get audioShareFailed => 'Споделянето е неуспешно';

  @override
  String get dailyRecaps => 'Дневни резюмета';

  @override
  String get removeFilter => 'Премахни филтъра';

  @override
  String get categoryConversationAnalysis => 'Анализ на разговори';

  @override
  String get categoryPersonalityClone => 'Клониране на личност';

  @override
  String get categoryHealth => 'Здраве';

  @override
  String get categoryEducation => 'Образование';

  @override
  String get categoryCommunication => 'Комуникация';

  @override
  String get categoryEmotionalSupport => 'Емоционална подкрепа';

  @override
  String get categoryProductivity => 'Продуктивност';

  @override
  String get categoryEntertainment => 'Забавление';

  @override
  String get categoryFinancial => 'Финанси';

  @override
  String get categoryTravel => 'Пътуване';

  @override
  String get categorySafety => 'Безопасност';

  @override
  String get categoryShopping => 'Пазаруване';

  @override
  String get categorySocial => 'Социални';

  @override
  String get categoryNews => 'Новини';

  @override
  String get categoryUtilities => 'Инструменти';

  @override
  String get categoryOther => 'Други';

  @override
  String get capabilityChat => 'Чат';

  @override
  String get capabilityConversations => 'Разговори';

  @override
  String get capabilityExternalIntegration => 'Външна интеграция';

  @override
  String get capabilityNotification => 'Известие';

  @override
  String get triggerAudioBytes => 'Аудио байтове';

  @override
  String get triggerConversationCreation => 'Създаване на разговор';

  @override
  String get triggerTranscriptProcessed => 'Обработен транскрипт';

  @override
  String get actionCreateConversations => 'Създаване на разговори';

  @override
  String get actionCreateMemories => 'Създаване на спомени';

  @override
  String get actionReadConversations => 'Четене на разговори';

  @override
  String get actionReadMemories => 'Четене на спомени';

  @override
  String get actionReadTasks => 'Четене на задачи';

  @override
  String get scopeUserName => 'Потребителско име';

  @override
  String get scopeUserFacts => 'Факти за потребителя';

  @override
  String get scopeUserConversations => 'Разговори на потребителя';

  @override
  String get scopeUserChat => 'Чат на потребителя';

  @override
  String get capabilitySummary => 'Резюме';

  @override
  String get capabilityFeatured => 'Препоръчани';

  @override
  String get capabilityTasks => 'Задачи';

  @override
  String get capabilityIntegrations => 'Интеграции';

  @override
  String get categoryPersonalityClones => 'Клонове на личности';

  @override
  String get categoryProductivityLifestyle => 'Продуктивност и начин на живот';

  @override
  String get categorySocialEntertainment => 'Социални и забавление';

  @override
  String get categoryProductivityTools => 'Инструменти за продуктивност';

  @override
  String get categoryPersonalWellness => 'Лично благосъстояние';

  @override
  String get rating => 'Рейтинг';

  @override
  String get categories => 'Категории';

  @override
  String get sortBy => 'Сортиране';

  @override
  String get highestRating => 'Най-висок рейтинг';

  @override
  String get lowestRating => 'Най-нисък рейтинг';

  @override
  String get resetFilters => 'Нулиране на филтрите';

  @override
  String get applyFilters => 'Прилагане на филтрите';

  @override
  String get mostInstalls => 'Най-много инсталации';

  @override
  String get couldNotOpenUrl => 'Не можа да се отвори URL адресът. Моля, опитайте отново.';

  @override
  String get newTask => 'Нова задача';

  @override
  String get viewAll => 'Виж всички';

  @override
  String get addTask => 'Добавяне на задача';

  @override
  String get addMcpServer => 'Добавяне на MCP сървър';

  @override
  String get connectExternalAiTools => 'Свързване на външни AI инструменти';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return '$count инструмента свързани успешно';
  }

  @override
  String get mcpConnectionFailed => 'Неуспешно свързване с MCP сървър';

  @override
  String get authorizingMcpServer => 'Упълномощаване...';

  @override
  String get whereDidYouHearAboutOmi => 'Как ни намерихте?';

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
  String get friendWordOfMouth => 'Приятел';

  @override
  String get otherSource => 'Друго';

  @override
  String get pleaseSpecify => 'Моля, уточнете';

  @override
  String get event => 'Събитие';

  @override
  String get coworker => 'Колега';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Аудио файлът не е наличен за възпроизвеждане';

  @override
  String get audioPlaybackFailed => 'Не може да се възпроизведе аудиото. Файлът може да е повреден или липсващ.';

  @override
  String get connectionGuide => 'Ръководство за свързване';

  @override
  String get iveDoneThis => 'Направих го';

  @override
  String get pairNewDevice => 'Сдвояване на ново устройство';

  @override
  String get dontSeeYourDevice => 'Не виждате устройството си?';

  @override
  String get reportAnIssue => 'Докладване на проблем';

  @override
  String get pairingTitleOmi => 'Включете Omi';

  @override
  String get pairingDescOmi => 'Натиснете и задръжте устройството, докато завибрира, за да го включите.';

  @override
  String get pairingTitleOmiDevkit => 'Поставете Omi DevKit в режим на сдвояване';

  @override
  String get pairingDescOmiDevkit =>
      'Натиснете бутона веднъж, за да включите. Светодиодът ще мига в лилаво в режим на сдвояване.';

  @override
  String get pairingTitleOmiGlass => 'Включете Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Натиснете и задръжте страничния бутон за 3 секунди, за да включите.';

  @override
  String get pairingTitlePlaudNote => 'Поставете Plaud Note в режим на сдвояване';

  @override
  String get pairingDescPlaudNote =>
      'Натиснете и задръжте страничния бутон за 2 секунди. Червеният светодиод ще мига, когато е готов за сдвояване.';

  @override
  String get pairingTitleBee => 'Поставете Bee в режим на сдвояване';

  @override
  String get pairingDescBee =>
      'Натиснете бутона 5 пъти последователно. Светлината ще започне да мига в синьо и зелено.';

  @override
  String get pairingTitleLimitless => 'Поставете Limitless в режим на сдвояване';

  @override
  String get pairingDescLimitless =>
      'Когато свети индикатор, натиснете веднъж, след това натиснете и задръжте, докато устройството покаже розова светлина, след което отпуснете.';

  @override
  String get pairingTitleFriendPendant => 'Поставете Friend Pendant в режим на сдвояване';

  @override
  String get pairingDescFriendPendant =>
      'Натиснете бутона на медальона, за да го включите. Той ще влезе в режим на сдвояване автоматично.';

  @override
  String get pairingTitleFieldy => 'Поставете Fieldy в режим на сдвояване';

  @override
  String get pairingDescFieldy => 'Натиснете и задръжте устройството, докато се появи светлината, за да го включите.';

  @override
  String get pairingTitleAppleWatch => 'Свържете Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Инсталирайте и отворете приложението Omi на вашия Apple Watch, след което натиснете Свързване в приложението.';

  @override
  String get pairingTitleNeoOne => 'Поставете Neo One в режим на сдвояване';

  @override
  String get pairingDescNeoOne =>
      'Натиснете и задръжте бутона за захранване, докато светодиодът мигне. Устройството ще бъде видимо.';

  @override
  String get downloadingFromDevice => 'Изтегляне от устройството';

  @override
  String get reconnectingToInternet => 'Повторно свързване с интернет...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Качване на $current от $total';
  }

  @override
  String get processedStatus => 'Обработено';

  @override
  String get corruptedStatus => 'Повредено';

  @override
  String nPending(int count) {
    return '$count в изчакване';
  }

  @override
  String nProcessed(int count) {
    return '$count обработени';
  }

  @override
  String get synced => 'Синхронизирано';

  @override
  String get noPendingRecordings => 'Няма записи в изчакване';

  @override
  String get noProcessedRecordings => 'Все още няма обработени записи';

  @override
  String get pending => 'В изчакване';

  @override
  String whatsNewInVersion(String version) {
    return 'Какво ново във $version';
  }

  @override
  String get addToYourTaskList => 'Добавяне към списъка ви със задачи?';

  @override
  String get failedToCreateShareLink => 'Неуспешно създаване на линк за споделяне';

  @override
  String get deleteGoal => 'Изтриване на целта';

  @override
  String get deviceUpToDate => 'Устройството ви е актуално';

  @override
  String get wifiConfiguration => 'WiFi конфигурация';

  @override
  String get wifiConfigurationSubtitle => 'Въведете данните за WiFi, за да може устройството да изтегли фърмуера.';

  @override
  String get networkNameSsid => 'Име на мрежата (SSID)';

  @override
  String get enterWifiNetworkName => 'Въведете името на WiFi мрежата';

  @override
  String get enterWifiPassword => 'Въведете парола за WiFi';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Ето какво знам за теб';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Тази карта се обновява, докато Omi учи от вашите разговори.';

  @override
  String get apiEnvironment => 'API среда';

  @override
  String get apiEnvironmentDescription => 'Изберете към кой сървър да се свържете';

  @override
  String get production => 'Продукция';

  @override
  String get staging => 'Тестова среда';

  @override
  String get switchRequiresRestart => 'Превключването изисква рестартиране на приложението';

  @override
  String get switchApiConfirmTitle => 'Превключване на API среда';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Превключване към $environment? Ще трябва да затворите и отворите отново приложението, за да влязат в сила промените.';
  }

  @override
  String get switchAndRestart => 'Превключи';

  @override
  String get stagingDisclaimer =>
      'Тестовата среда може да е нестабилна, с непостоянна производителност и данните могат да бъдат загубени. Само за тестване.';

  @override
  String get apiEnvSavedRestartRequired =>
      'Запазено. Затворете и отворете отново приложението, за да приложите промените.';

  @override
  String get shared => 'Споделено';

  @override
  String get onlyYouCanSeeConversation => 'Само вие можете да видите този разговор';

  @override
  String get anyoneWithLinkCanView => 'Всеки с връзката може да преглежда';

  @override
  String get tasksCleanTodayTitle => 'Да изчистим днешните задачи?';

  @override
  String get tasksCleanTodayMessage => 'Това само ще премахне крайните срокове';

  @override
  String get tasksOverdue => 'Просрочени';

  @override
  String get phoneCallsWithOmi => 'Телефонни обаждания с Omi';

  @override
  String get phoneCallsSubtitle => 'Обаждайте се с транскрипция в реално време';

  @override
  String get phoneSetupStep1Title => 'Потвърдете телефонния си номер';

  @override
  String get phoneSetupStep1Subtitle => 'Ще ви се обадим, за да потвърдим, че е ваш';

  @override
  String get phoneSetupStep2Title => 'Въведете код за потвърждение';

  @override
  String get phoneSetupStep2Subtitle => 'Кратък код, който ще въведете по време на обаждането';

  @override
  String get phoneSetupStep3Title => 'Започнете да се обаждате на контактите си';

  @override
  String get phoneSetupStep3Subtitle => 'С вградена транскрипция на живо';

  @override
  String get phoneGetStarted => 'Започнете';

  @override
  String get callRecordingConsentDisclaimer =>
      'Записването на обаждания може да изисква съгласие във вашата юрисдикция';

  @override
  String get enterYourNumber => 'Въведете номера си';

  @override
  String get phoneNumberCallerIdHint => 'След потвърждение това ще стане вашият идентификатор на обаждащия се';

  @override
  String get phoneNumberHint => 'Телефонен номер';

  @override
  String get failedToStartVerification => 'Неуспешно стартиране на потвърждението';

  @override
  String get phoneContinue => 'Продължи';

  @override
  String get verifyYourNumber => 'Потвърдете номера си';

  @override
  String get answerTheCallFrom => 'Отговорете на обаждането от';

  @override
  String get onTheCallEnterThisCode => 'По време на обаждането въведете този код';

  @override
  String get followTheVoiceInstructions => 'Следвайте гласовите инструкции';

  @override
  String get statusCalling => 'Обаждане...';

  @override
  String get statusCallInProgress => 'Обаждане в ход';

  @override
  String get statusVerifiedLabel => 'Потвърдено';

  @override
  String get statusCallMissed => 'Пропуснато обаждане';

  @override
  String get statusTimedOut => 'Времето изтече';

  @override
  String get phoneTryAgain => 'Опитайте отново';

  @override
  String get phonePageTitle => 'Телефон';

  @override
  String get phoneContactsTab => 'Контакти';

  @override
  String get phoneKeypadTab => 'Клавиатура';

  @override
  String get grantContactsAccess => 'Предоставете достъп до контактите си';

  @override
  String get phoneAllow => 'Разреши';

  @override
  String get phoneSearchHint => 'Търсене';

  @override
  String get phoneNoContactsFound => 'Няма намерени контакти';

  @override
  String get phoneEnterNumber => 'Въведете номер';

  @override
  String get failedToStartCall => 'Неуспешно стартиране на обаждането';

  @override
  String get callStateConnecting => 'Свързване...';

  @override
  String get callStateRinging => 'Звъни...';

  @override
  String get callStateEnded => 'Обаждането приключи';

  @override
  String get callStateFailed => 'Обаждането не успя';

  @override
  String get transcriptPlaceholder => 'Транскрипцията ще се появи тук...';

  @override
  String get phoneUnmute => 'Включи звука';

  @override
  String get phoneMute => 'Заглуши';

  @override
  String get phoneSpeaker => 'Високоговорител';

  @override
  String get phoneEndCall => 'Край';

  @override
  String get phoneCallSettingsTitle => 'Настройки на телефонните обаждания';

  @override
  String get yourVerifiedNumbers => 'Вашите потвърдени номера';

  @override
  String get verifiedNumbersDescription => 'Когато се обадите на някого, той ще види този номер на телефона си';

  @override
  String get noVerifiedNumbers => 'Няма потвърдени номера';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Изтриване на $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Ще трябва да потвърдите отново, за да извършвате обаждания';

  @override
  String get phoneDeleteButton => 'Изтрий';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Потвърдено преди $minutes мин';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Потвърдено преди $hours ч';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Потвърдено преди $days дни';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Потвърдено на $date';
  }

  @override
  String get verifiedFallback => 'Потвърдено';

  @override
  String get callAlreadyInProgress => 'Вече има обаждане в ход';

  @override
  String get failedToGetCallToken => 'Неуспешно получаване на токен за обаждане. Първо потвърдете телефонния си номер.';

  @override
  String get failedToInitializeCallService => 'Неуспешна инициализация на услугата за обаждания';

  @override
  String get speakerLabelYou => 'Вие';

  @override
  String get speakerLabelUnknown => 'Неизвестен';

  @override
  String get showDailyScoreOnHomepage => 'Покажи дневния резултат на началната страница';

  @override
  String get showTasksOnHomepage => 'Покажи задачите на началната страница';

  @override
  String get phoneCallsUnlimitedOnly => 'Телефонни обаждания чрез Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Правете обаждания чрез Omi и получавайте транскрипция в реално време, автоматични резюмета и още. Достъпно само за абонати на план Неограничен.';

  @override
  String get phoneCallsUpsellFeature1 => 'Транскрипция в реално време на всяко обаждане';

  @override
  String get phoneCallsUpsellFeature2 => 'Автоматични резюмета и задачи от обаждания';

  @override
  String get phoneCallsUpsellFeature3 => 'Получателите виждат истинския ви номер, не случаен';

  @override
  String get phoneCallsUpsellFeature4 => 'Вашите обаждания остават лични и сигурни';

  @override
  String get phoneCallsUpgradeButton => 'Надградете до Неограничен';

  @override
  String get phoneCallsMaybeLater => 'Може би по-късно';

  @override
  String get deleteSynced => 'Изтриване на синхронизираните';

  @override
  String get deleteSyncedFiles => 'Изтрий синхронизираните записи';

  @override
  String get deleteSyncedFilesMessage =>
      'Тези записи вече са синхронизирани с телефона ви. Това не може да бъде отменено.';

  @override
  String get syncedFilesDeleted => 'Синхронизираните записи са изтрити';

  @override
  String get deletePending => 'Изтриване на чакащите';

  @override
  String get deletePendingFiles => 'Изтрий чакащите записи';

  @override
  String get deletePendingFilesWarning =>
      'Тези записи НЕ са синхронизирани с телефона ви и ще бъдат загубени завинаги. Това не може да бъде отменено.';

  @override
  String get pendingFilesDeleted => 'Чакащите записи са изтрити';

  @override
  String get deleteAllFiles => 'Изтрий всички записи';

  @override
  String get deleteAll => 'Изтриване на всички';

  @override
  String get deleteAllFilesWarning =>
      'Това ще изтрие синхронизираните и чакащите записи. Чакащите записи НЕ са синхронизирани и ще бъдат загубени завинаги.';

  @override
  String get allFilesDeleted => 'Всички записи са изтрити';

  @override
  String nFiles(int count) {
    return '$count записа';
  }

  @override
  String get manageStorage => 'Управление на хранилището';

  @override
  String get safelyBackedUp => 'Безопасно запазено на телефона ви';

  @override
  String get notYetSynced => 'Все още не е синхронизирано с телефона ви';

  @override
  String get clearAll => 'Изчисти всичко';

  @override
  String get phoneKeypad => 'Клавиатура';

  @override
  String get phoneHideKeypad => 'Скрий клавиатурата';

  @override
  String get fairUsePolicy => 'Честна употреба';

  @override
  String get fairUseLoadError => 'Неуспешно зареждане на статуса на честна употреба. Моля, опитайте отново.';

  @override
  String get fairUseStatusNormal => 'Вашата употреба е в нормалните граници.';

  @override
  String get fairUseStageNormal => 'Нормална';

  @override
  String get fairUseStageWarning => 'Предупреждение';

  @override
  String get fairUseStageThrottle => 'Ограничена';

  @override
  String get fairUseStageRestrict => 'Забранена';

  @override
  String get fairUseSpeechUsage => 'Употреба на реч';

  @override
  String get fairUseToday => 'Днес';

  @override
  String get fairUse3Day => '3-дневен период';

  @override
  String get fairUseWeekly => 'Седмичен период';

  @override
  String get fairUseAboutTitle => 'Относно честната употреба';

  @override
  String get fairUseAboutBody =>
      'Omi е проектиран за лични разговори, срещи и взаимодействия на живо. Употребата се измерва по реалното открито време на реч, а не по времето на връзка. Ако употребата значително надвишава нормалните модели за неличностно съдържание, може да се приложат корекции.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef копирано';
  }

  @override
  String get fairUseDailyTranscription => 'Daily Transcription';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'Daily transcription limit reached';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resets $time';
  }

  @override
  String get transcriptionPaused => 'Записва се, свързване отново';

  @override
  String get transcriptionPausedReconnecting => 'Все още се записва — свързване с транскрипцията...';

  @override
  String fairUseBannerStatus(String status) {
    return 'Добросъвестно ползване: $status';
  }

  @override
  String get improveConnectionTitle => 'Подобряване на връзката';

  @override
  String get improveConnectionContent =>
      'Подобрихме начина, по който Omi остава свързан с вашето устройство. За да активирате това, моля, отидете на страницата с информация за устройството, натиснете \"Изключване на устройството\" и сдвоете устройството си отново.';

  @override
  String get improveConnectionAction => 'Разбрах';

  @override
  String clockSkewWarning(int minutes) {
    return 'Часовникът на устройството ви е разместен с ~$minutes мин. Проверете настройките за дата и час.';
  }
}
