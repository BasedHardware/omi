// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Macedonian (`mk`).
class AppLocalizationsMk extends AppLocalizations {
  AppLocalizationsMk([String locale = 'mk']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Разговор';

  @override
  String get transcriptTab => 'Транскрипт';

  @override
  String get actionItemsTab => 'Работни предмети';

  @override
  String get deleteConversationTitle => 'Избриши разговор?';

  @override
  String get deleteConversationMessage =>
      'Ова ќе избрише и поврзаните спомени, задачи и аудио датотеки. Оваа акција не може да се отповика.';

  @override
  String get confirm => 'Потврди';

  @override
  String get cancel => 'Откажи';

  @override
  String get ok => 'ОК';

  @override
  String get delete => 'Избриши';

  @override
  String get add => 'Додај';

  @override
  String get update => 'Ажурирај';

  @override
  String get save => 'Зачувај';

  @override
  String get edit => 'Уреди';

  @override
  String get close => 'Затвори';

  @override
  String get clear => 'Очисти';

  @override
  String get copyTranscript => 'Копирај транскрипт';

  @override
  String get copySummary => 'Копирај резиме';

  @override
  String get testPrompt => 'Тест подсетник';

  @override
  String get reprocessConversation => 'Прерапди разговор';

  @override
  String get deleteConversation => 'Избриши разговор';

  @override
  String get contentCopied => 'Содржината е копирана во меморија';

  @override
  String get failedToUpdateStarred => 'Неуспешно ажурирање на означување со ѕвезда.';

  @override
  String get conversationUrlNotShared => 'URL адресата на разговорот не можеше да се сподели.';

  @override
  String get errorProcessingConversation => 'Грешка при обработка на разговорот. Обидете се повторно подоцна.';

  @override
  String get noInternetConnection => 'Нема интернет врска';

  @override
  String get unableToDeleteConversation => 'Неможно да се избрише разговорот';

  @override
  String get somethingWentWrong => 'Нешто тргна наопако! Обидете се повторно подоцна.';

  @override
  String get copyErrorMessage => 'Копирај порака за грешка';

  @override
  String get errorCopied => 'Пораката за грешка е копирана во меморија';

  @override
  String get remaining => 'Преостанало';

  @override
  String get loading => 'Вчитување...';

  @override
  String get loadingDuration => 'Вчитување траење...';

  @override
  String secondsCount(int count) {
    return '$count секунди';
  }

  @override
  String get people => 'Луѓе';

  @override
  String get addNewPerson => 'Додај ново лице';

  @override
  String get editPerson => 'Уреди лице';

  @override
  String get createPersonHint => 'Направи ново лице и научи ја Omi да препознава и нивниот глас!';

  @override
  String get speechProfile => 'Профил на глас';

  @override
  String sampleNumber(int number) {
    return 'Примерок $number';
  }

  @override
  String get settings => 'Поставки';

  @override
  String get language => 'Јазик';

  @override
  String get selectLanguage => 'Избери јазик';

  @override
  String get deleting => 'Бришам...';

  @override
  String get pleaseCompleteAuthentication =>
      'Завршите аутентификација во вашиот претседател. Откако ќе завршите, вратете се во апликацијата.';

  @override
  String get failedToStartAuthentication => 'Неуспешен почеток на аутентификација';

  @override
  String get importStarted => 'Увозот почна! Ќе бидете известени кога ќе биде завршен.';

  @override
  String get failedToStartImport => 'Неуспешен почеток на увоз. Обидете се повторно.';

  @override
  String get couldNotAccessFile => 'Не можеше да се пристапи до избраната датотека';

  @override
  String get askOmi => 'Праши ја Omi';

  @override
  String get done => 'Завршено';

  @override
  String get disconnected => 'Исклучено';

  @override
  String get searching => 'Пребарување...';

  @override
  String get connectDevice => 'Поврзи уред';

  @override
  String get monthlyLimitReached => 'Достигнувте го вашиот месечен лимит.';

  @override
  String get checkUsage => 'Проверете користење';

  @override
  String get syncingRecordings => 'Синхронизирање записи';

  @override
  String get recordingsToSync => 'Записи за синхронизирање';

  @override
  String get allCaughtUp => 'Сите се чувани';

  @override
  String get sync => 'Синхронизирај';

  @override
  String get pendantUpToDate => 'Привесокот е ажуриран';

  @override
  String get allRecordingsSynced => 'Сите записи се синхронизирани';

  @override
  String get syncingInProgress => 'Синхронизирањето е во тек';

  @override
  String get readyToSync => 'Подготовено за синхронизирање';

  @override
  String get tapSyncToStart => 'Допрете синхронизирај за почеток';

  @override
  String get pendantNotConnected => 'Привесокот не е поврзан. Поврзете се за синхронизирање.';

  @override
  String get everythingSynced => 'Сегорашното е веќе синхронизирано.';

  @override
  String get recordingsNotSynced => 'Имате записи кои сè нису синхронизирани.';

  @override
  String get syncingBackground => 'Ќе продолжиме да синхронизираме ваши записи во позадина.';

  @override
  String get noConversationsYet => 'Сè нема разговори';

  @override
  String get noStarredConversations => 'Нема означени разговори со ѕвезда';

  @override
  String get starConversationHint =>
      'За да означите разговор со ѕвезда, отворете го и допрете икона ѕвезда во заглавието.';

  @override
  String get searchConversations => 'Пребарај разговори...';

  @override
  String selectedCount(int count, Object s) {
    return '$count избрано';
  }

  @override
  String get merge => 'Спои';

  @override
  String get mergeConversations => 'Спој разговори';

  @override
  String mergeConversationsMessage(int count) {
    return 'Ово ќе ги спои $count разговори во еден. Сва содржина ќе биде спојена и регенерирана.';
  }

  @override
  String get mergingInBackground => 'Спојување во позадина. Ова може да трае минута.';

  @override
  String get failedToStartMerge => 'Неуспешен почеток на спојување';

  @override
  String get askAnything => 'Праши било што';

  @override
  String get noMessagesYet => 'Сè нема пораки!\nЗошто не почнете разговор?';

  @override
  String get deletingMessages => 'Бришам ваши пораки од меморија на Omi...';

  @override
  String get messageCopied => '✨ Пораката е копирана во меморија';

  @override
  String get cannotReportOwnMessage => 'Не можете да пријавите ваши сопствени пораки.';

  @override
  String get reportMessage => 'Пријави порака';

  @override
  String get reportMessageConfirm => 'Дали сте сигурни дека сакате да ја пријавите оваа порака?';

  @override
  String get messageReported => 'Пораката е успешно пријавена.';

  @override
  String get thankYouFeedback => 'Благодариме за вашата повратна информација!';

  @override
  String get clearChat => 'Очисти разговор';

  @override
  String get clearChatConfirm =>
      'Дали сте сигурни дека сакате да го очистите разговорот? Оваа акција не може да се отповика.';

  @override
  String get maxFilesLimit => 'Можете да подигнете максимално 4 датотеки одеднаш';

  @override
  String get chatWithOmi => 'Разговарај со Omi';

  @override
  String get apps => 'Апликации';

  @override
  String get noAppsFound => 'Нема пронајдени апликации';

  @override
  String get tryAdjustingSearch => 'Обидете се да ги прилагодите пребарувањето или филтрите';

  @override
  String get createYourOwnApp => 'Направи своја апликација';

  @override
  String get buildAndShareApp => 'Направи и сподели своја прилагодена апликација';

  @override
  String get searchApps => 'Пребарај апликации...';

  @override
  String get myApps => 'Мои апликации';

  @override
  String get installedApps => 'Инсталирани апликации';

  @override
  String get unableToFetchApps =>
      'Неможно да се преземат апликациите :(\n\nПроверете ја интернет врската и обидете се повторно.';

  @override
  String get aboutOmi => 'За Omi';

  @override
  String get privacyPolicy => 'Политика за приватност';

  @override
  String get visitWebsite => 'Посети веб-сајт';

  @override
  String get helpOrInquiries => 'Помош или прашања?';

  @override
  String get joinCommunity => 'Придружи се на заедницата!';

  @override
  String get membersAndCounting => '8000+ членови и се зголемува.';

  @override
  String get deleteAccountTitle => 'Избриши профил';

  @override
  String get deleteAccountConfirm => 'Дали сте сигурни дека сакате да го избришете вашиот профил?';

  @override
  String get cannotBeUndone => 'Ова не може да се отповика.';

  @override
  String get allDataErased => 'Сите ваши спомени и разговори ќе бидат трајно избришани.';

  @override
  String get appsDisconnected => 'Ваши апликации и интеграции ќе бидат исклучени веднаш.';

  @override
  String get exportBeforeDelete =>
      'Можете да ги извезете ваши податоци пред да го избришете профилот, но откако ќе биде избришан, не може да се врати.';

  @override
  String get deleteAccountCheckbox =>
      'Разбирам дека бришењето на мој профил е трајно и сите податоци, вклучувајќи ги спомените и разговорите, ќе бидат изгубени и не можат да се вратат.';

  @override
  String get areYouSure => 'Дали сте сигурни?';

  @override
  String get deleteAccountFinal =>
      'Оваа акција е неревидна и трајно ќе го избрише вашиот профил и сите поврзани податоци. Дали сте сигурни дека сакате да продолжите?';

  @override
  String get deleteNow => 'Избриши сега';

  @override
  String get goBack => 'Назад';

  @override
  String get checkBoxToConfirm =>
      'Означете го полето за да потврдите дека разбирате дека бришењето на вашиот профил е трајно и неревидно.';

  @override
  String get profile => 'Профил';

  @override
  String get name => 'Име';

  @override
  String get email => 'Е-пошта';

  @override
  String get customVocabulary => 'Прилагодена лексика';

  @override
  String get identifyingOthers => 'Идентификување на други';

  @override
  String get paymentMethods => 'Начини на плаќање';

  @override
  String get conversationDisplay => 'Приказ на разговор';

  @override
  String get dataPrivacy => 'Приватност на податоци';

  @override
  String get userId => 'ID на корисник';

  @override
  String get notSet => 'Не е поставено';

  @override
  String get userIdCopied => 'ID на корисник е копиран во меморија';

  @override
  String get systemDefault => 'Системска стандардна вредност';

  @override
  String get planAndUsage => 'План и користење';

  @override
  String get offlineSync => 'Синхронизирање без интернет';

  @override
  String get deviceSettings => 'Поставки на уред';

  @override
  String get integrations => 'Интеграции';

  @override
  String get feedbackBug => 'Повратна информација / Грешка';

  @override
  String get helpCenter => 'Центар за помош';

  @override
  String get developerSettings => 'Поставки за развивачи';

  @override
  String get getOmiForMac => 'Земи Omi за Mac';

  @override
  String get referralProgram => 'Програма за препорачување';

  @override
  String get signOut => 'Одјави се';

  @override
  String get appAndDeviceCopied => 'Детали на апликацијата и уредот се копирани';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Вашата приватност, вашата контрола';

  @override
  String get privacyIntro =>
      'На Omi, сме посветени на заштита на вашата приватност. Оваа страница вам овозможува контрола како ваши податоци се складираат и користат.';

  @override
  String get learnMore => 'Научи повеќе...';

  @override
  String get dataProtectionLevel => 'Ниво на заштита на податоци';

  @override
  String get dataProtectionDesc =>
      'Вашите податоци се безбедни по стандард со силна енкрипција. Преглед ваши поставки и идните опции за приватност подолу.';

  @override
  String get appAccess => 'Пристап на апликација';

  @override
  String get appAccessDesc =>
      'Следниве апликации можат да пристапат до ваши податоци. Допрете апликација за управување нејзините дозволи.';

  @override
  String get noAppsExternalAccess => 'Нема инсталирани апликации со надворешен пристап до ваши податоци.';

  @override
  String get deviceName => 'Име на уред';

  @override
  String get deviceId => 'ID на уред';

  @override
  String get firmware => 'Фирмвер';

  @override
  String get sdCardSync => 'Синхронизирање на SD картичка';

  @override
  String get hardwareRevision => 'Преработка на хардвер';

  @override
  String get modelNumber => 'Број на модел';

  @override
  String get manufacturer => 'Производител';

  @override
  String get doubleTap => 'Двојно допирање';

  @override
  String get ledBrightness => 'Осветленост на LED';

  @override
  String get micGain => 'Pojачање на микрофон';

  @override
  String get disconnect => 'Исклучи';

  @override
  String get forgetDevice => 'Заборави уред';

  @override
  String get chargingIssues => 'Проблеми со полнење';

  @override
  String get disconnectDevice => 'Исклучи уред';

  @override
  String get unpairDevice => 'Раскачи уред';

  @override
  String get unpairAndForget => 'Раскачи и заборави уред';

  @override
  String get deviceDisconnectedMessage => 'Вашиот Omi е исклучен 😔';

  @override
  String get deviceUnpairedMessage =>
      'Уредот е раскачен. Одите на Поставки > Bluetooth и заборавете го уредот за завршување раскачување.';

  @override
  String get unpairDialogTitle => 'Раскачи уред';

  @override
  String get unpairDialogMessage =>
      'Ово ќе го раскачи уредот така што може да се поврзи со друг телефон. Ќе мора да одите на Поставки > Bluetooth и да го заборавите уредот за завршување на процесот.';

  @override
  String get deviceNotConnected => 'Уредот не е поврзан';

  @override
  String get connectDeviceMessage => 'Поврзете го вашиот Omi уред за пристап\nна поставки на уред и прилагодување';

  @override
  String get deviceInfoSection => 'Информации на уред';

  @override
  String get customizationSection => 'Прилагодување';

  @override
  String get hardwareSection => 'Хардвер';

  @override
  String get v2Undetected => 'V2 не е детектирано';

  @override
  String get v2UndetectedMessage =>
      'Видиме дека имате V1 уред или вашиот уред не е поврзан. Функционалност на SD картичка е достапна само за V2 уреди.';

  @override
  String get endConversation => 'Крај разговор';

  @override
  String get pauseResume => 'Пауза/Продолжи';

  @override
  String get starConversation => 'Означи разговор со ѕвезда';

  @override
  String get doubleTapAction => 'Акција при двојно допирање';

  @override
  String get endAndProcess => 'Крај и обработи разговор';

  @override
  String get pauseResumeRecording => 'Пауза/Продолжи запис';

  @override
  String get starOngoing => 'Означи текуч разговор со ѕвезда';

  @override
  String get off => 'Исклучено';

  @override
  String get max => 'Макс';

  @override
  String get mute => 'Исклучи звук';

  @override
  String get quiet => 'Тивко';

  @override
  String get normal => 'Нормално';

  @override
  String get high => 'Високо';

  @override
  String get micGainDescMuted => 'Микрофонот е исклучен';

  @override
  String get micGainDescLow => 'Многу тивко - за гласни средини';

  @override
  String get micGainDescModerate => 'Тивко - за умерена бука';

  @override
  String get micGainDescNeutral => 'Неутрално - уравнотежена снимање';

  @override
  String get micGainDescSlightlyBoosted => 'Малку зајачано - нормална употреба';

  @override
  String get micGainDescBoosted => 'Зајачано - за тивки средини';

  @override
  String get micGainDescHigh => 'Високо - за далечни или мeки гласови';

  @override
  String get micGainDescVeryHigh => 'Многу високо - за многу тивни извори';

  @override
  String get micGainDescMax => 'Максимално - користете со внимание';

  @override
  String get developerSettingsTitle => 'Поставки за развивачи';

  @override
  String get saving => 'Зачувување...';

  @override
  String get beta => 'БЕТА';

  @override
  String get transcription => 'Трансрипција';

  @override
  String get transcriptionConfig => 'Конфигурирај STT провајдер';

  @override
  String get conversationTimeout => 'Време за истек на разговор';

  @override
  String get conversationTimeoutConfig => 'Постави кога разговорите автоматски завршуваат';

  @override
  String get importData => 'Увези податоци';

  @override
  String get importDataConfig => 'Увези податоци од други извори';

  @override
  String get debugDiagnostics => 'Debug & Дијагностика';

  @override
  String get endpointUrl => 'URL адреса на крајната точка';

  @override
  String get noApiKeys => 'Сè нема API клучеви';

  @override
  String get createKeyToStart => 'Направи клучи за почеток';

  @override
  String get createKey => 'Направи клучи';

  @override
  String get docs => 'Документација';

  @override
  String get yourOmiInsights => 'Ваши Omi увиди';

  @override
  String get today => 'Денес';

  @override
  String get thisMonth => 'Овој месец';

  @override
  String get thisYear => 'Оваа година';

  @override
  String get allTime => 'Целото време';

  @override
  String get noActivityYet => 'Сè нема активност';

  @override
  String get startConversationToSeeInsights => 'Почнете разговор со Omi\nза да видите ваши увиди за користење овде.';

  @override
  String get listening => 'Слушам';

  @override
  String get listeningSubtitle => 'Вкупно време кога Omi активно слушала.';

  @override
  String get understanding => 'Разбирање';

  @override
  String get understandingSubtitle => 'Зборови разбрани од ваши разговори.';

  @override
  String get providing => 'Обезбедување';

  @override
  String get providingSubtitle => 'Работни предмети и белешки автоматски зафатени.';

  @override
  String get remembering => 'Помнење';

  @override
  String get rememberingSubtitle => 'Факти и детали запомнети за вас.';

  @override
  String get unlimitedPlan => 'Неограничен план';

  @override
  String get managePlan => 'Управувај со план';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Вашиот план ќе биде отказан на $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Вашиот план се обновува на $date.';
  }

  @override
  String get basicPlan => 'Бесплатен план';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used од $limit минути користени';
  }

  @override
  String get upgrade => 'Надгради';

  @override
  String get upgradeToUnlimited => 'Надгради на неограничено';

  @override
  String basicPlanDesc(int limit) {
    return 'Вашиот план вклучува $limit бесплатни минути месечно. Надградете за неограничено.';
  }

  @override
  String get shareStatsMessage => 'Дели ги моите Omi статистики! (omi.me - твој секогаш-активен AI асистент)';

  @override
  String get sharePeriodToday => 'Денес, omi има:';

  @override
  String get sharePeriodMonth => 'Овој месец, omi има:';

  @override
  String get sharePeriodYear => 'Оваа година, omi има:';

  @override
  String get sharePeriodAllTime => 'Досега, omi има:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Слушала за $minutes минути';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Разбрала $words зборови';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Обезбедила $count увиди';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Запомнала $count спомени';
  }

  @override
  String get debugLogs => 'Debug логови';

  @override
  String get debugLogsAutoDelete => 'Автоматски се бриши по 3 денови.';

  @override
  String get debugLogsDesc => 'Помага при дијагностицирање проблеми';

  @override
  String get noLogFilesFound => 'Нема пронајдени датотеки логови.';

  @override
  String get omiDebugLog => 'Omi debug лог';

  @override
  String get logShared => 'Логот е споделен';

  @override
  String get selectLogFile => 'Избери датотека лог';

  @override
  String get shareLogs => 'Сподели логови';

  @override
  String get debugLogCleared => 'Debug логот е очистен';

  @override
  String get exportStarted => 'Извезување почна. Ова може да трае неколку секунди...';

  @override
  String get exportAllData => 'Извези сите податоци';

  @override
  String get exportDataDesc => 'Извези разговори во JSON датотека';

  @override
  String get exportedConversations => 'Извезени разговори од Omi';

  @override
  String get exportShared => 'Извезување споделено';

  @override
  String get deleteKnowledgeGraphTitle => 'Избриши граф на знаење?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Ово ќе избрише сави извлечени податоци на граф на знаење (чворови и врски). Ваши оригинални спомени ќе останат безбедни. Графот ќе биде обновен со текот на времето или при следното барање.';

  @override
  String get knowledgeGraphDeleted => 'Граф на знаење е избришан';

  @override
  String deleteGraphFailed(String error) {
    return 'Неуспешно бришење на граф: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Избриши граф на знаење';

  @override
  String get deleteKnowledgeGraphDesc => 'Очисти сите чворови и врски';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP сервер';

  @override
  String get mcpServerDesc => 'Поврзи AI асистенти со твои податоци';

  @override
  String get serverUrl => 'URL адреса на сервер';

  @override
  String get urlCopied => 'URL адреса копирана';

  @override
  String get apiKeyAuth => 'API клучи аутентификација';

  @override
  String get header => 'Заглавие';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID на клиент';

  @override
  String get clientSecret => 'Тајна на клиент';

  @override
  String get useMcpApiKey => 'Користи твој MCP API клучи';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'События на разговор';

  @override
  String get newConversationCreated => 'Нов разговор создаден';

  @override
  String get realtimeTranscript => 'Реално време транскрипт';

  @override
  String get transcriptReceived => 'Транскрипт примен';

  @override
  String get audioBytes => 'Audio бајти';

  @override
  String get audioDataReceived => 'Audio податоци примени';

  @override
  String get intervalSeconds => 'Интервал (секунди)';

  @override
  String get daySummary => 'Резиме на ден';

  @override
  String get summaryGenerated => 'Резиме генерирано';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Додај во claude_desktop_config.json';

  @override
  String get copyConfig => 'Копирај конфигурација';

  @override
  String get configCopied => 'Конфигурација копирана во меморија';

  @override
  String get listeningMins => 'Слушање (мин)';

  @override
  String get understandingWords => 'Разбирање (зборови)';

  @override
  String get insights => 'Увиди';

  @override
  String get memories => 'Спомени';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used од $limit мин користени овој месец';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used од $limit зборови користени овој месец';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used од $limit увиди добиени овој месец';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used од $limit спомени креирани овој месец';
  }

  @override
  String get visibility => 'Видливост';

  @override
  String get visibilitySubtitle => 'Контролирај кои разговори се појавуваат во твоја листа';

  @override
  String get showShortConversations => 'Покажи кратки разговори';

  @override
  String get showShortConversationsDesc => 'Прикажи разговори пократки од прагот';

  @override
  String get showDiscardedConversations => 'Покажи отфрлени разговори';

  @override
  String get showDiscardedConversationsDesc => 'Вклучи разговори означени како отфрлени';

  @override
  String get shortConversationThreshold => 'Праг на кратък разговор';

  @override
  String get shortConversationThresholdSubtitle =>
      'Разговори пократки од ова ќе бидат скриени освен ако е овозможено горе';

  @override
  String get durationThreshold => 'Праг на траење';

  @override
  String get durationThresholdDesc => 'Скрии разговори пократки од ова';

  @override
  String minLabel(int count) {
    return '$count мин';
  }

  @override
  String get customVocabularyTitle => 'Прилагодена лексика';

  @override
  String get addWords => 'Додај зборови';

  @override
  String get addWordsDesc => 'Имиња, термини или необични зборови';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Поврзи';

  @override
  String get comingSoon => 'Наскоро';

  @override
  String get integrationsFooter => 'Поврзи ги ваши апликации за преглед на податоци и метрики во разговор.';

  @override
  String get completeAuthInBrowser =>
      'Завршите аутентификација во вашиот претседател. Откако ќе завршите, вратете се во апликацијата.';

  @override
  String failedToStartAuth(String appName) {
    return 'Неуспешен почеток на $appName аутентификација';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Исклучи се од $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Дали сте сигурни дека сакате да се исклучите од $appName? Можете да се поврзете повторно во секој момент.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Исклучен од $appName';
  }

  @override
  String get failedToDisconnect => 'Неуспешно исклучување';

  @override
  String connectTo(String appName) {
    return 'Поврзи се со $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Ќе треба да го авторизирате Omi за пристап до вашите $appName податоци. Ово ќе го отвори вашиот претседател за аутентификација.';
  }

  @override
  String get continueAction => 'Продолжи';

  @override
  String get languageTitle => 'Јазик';

  @override
  String get primaryLanguage => 'Примарен јазик';

  @override
  String get automaticTranslation => 'Автоматска превод';

  @override
  String get detectLanguages => 'Препознај 10+ јазици';

  @override
  String get authorizeSavingRecordings => 'Авторизирај зачувување записи';

  @override
  String get thanksForAuthorizing => 'Благодариме на авторизирањето!';

  @override
  String get needYourPermission => 'Ви треба вашата дозвола';

  @override
  String get alreadyGavePermission =>
      'Веќе ни дадовте дозвола да ги зачувуваме ваши записи. Еве напомена зошто ни треба:';

  @override
  String get wouldLikePermission => 'Би ја сакале вашата дозвола да ги зачувуваме ваши гласни записи. Еве зошто:';

  @override
  String get improveSpeechProfile => 'Подобри ја твојата токолна личност';

  @override
  String get improveSpeechProfileDesc =>
      'Ги користиме записите за понатамошно обука и подобрување на твојот личен профил на глас.';

  @override
  String get trainFamilyProfiles => 'Обучи профили за пријатели и семејство';

  @override
  String get trainFamilyProfilesDesc =>
      'Ваши записи ни помагаат да препознаеме и направиме профили за вашите пријатели и семејство.';

  @override
  String get enhanceTranscriptAccuracy => 'Подобри точност на транскрипт';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Како што нашиот модел се подобрува, можеме да обезбедиме подобри резултати на транскрипција за ваши записи.';

  @override
  String get legalNotice =>
      'Правна напомена: Законитоста на снимање и складирање на гласни податоци може да варира во зависност од вашата локација и начинот на кој ја користите оваа функција. Вашa е одговорност да обезбедите соответност со локалните закони и регулативи.';

  @override
  String get alreadyAuthorized => 'Веќе авторизирано';

  @override
  String get authorize => 'Авторизирај';

  @override
  String get revokeAuthorization => 'Отповики авторизација';

  @override
  String get authorizationSuccessful => 'Авторизацијата е успешна!';

  @override
  String get failedToAuthorize => 'Не можете да се најдете. Пробајте повторно.';

  @override
  String get authorizationRevoked => 'Авторизацијата е отповикана.';

  @override
  String get recordingsDeleted => 'Записите се избришани.';

  @override
  String get failedToRevoke => 'Не можеше да се отповика авторизацијата. Пробајте повторно.';

  @override
  String get permissionRevokedTitle => 'Дозволата е отповикана';

  @override
  String get permissionRevokedMessage => 'Дали сакате да ги избришеме и сите ваши постоечки записи?';

  @override
  String get yes => 'Да';

  @override
  String get editName => 'Уредување на име';

  @override
  String get howShouldOmiCallYou => 'Како да Вас зовува Omi?';

  @override
  String get enterYourName => 'Внесете ваше име';

  @override
  String get nameCannotBeEmpty => 'Името не може да биде празно';

  @override
  String get nameUpdatedSuccessfully => 'Името е успешно ажурирано!';

  @override
  String get calendarSettings => 'Поставки на календар';

  @override
  String get calendarProviders => 'Добавувачи на календар';

  @override
  String get macOsCalendar => 'macOS Календар';

  @override
  String get connectMacOsCalendar => 'Поврзете го вашиот локален macOS календар';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Синхронизирајте се со вашата Google сметка';

  @override
  String get showMeetingsMenuBar => 'Прикажи предстојни состаноци во мени лента';

  @override
  String get showMeetingsMenuBarDesc =>
      'Прикажете го вашиот следниот состанок и време до почеток во macOS мени лентата';

  @override
  String get showEventsNoParticipants => 'Прикажи настани без учесници';

  @override
  String get showEventsNoParticipantsDesc => 'Кога е активирано, Наскоро прикажува настани без учесници или видеолинк.';

  @override
  String get yourMeetings => 'Ваши состаноци';

  @override
  String get refresh => 'Освежување';

  @override
  String get noUpcomingMeetings => 'Нема предстојни состаноци';

  @override
  String get checkingNextDays => 'Проверување на следните 30 дни';

  @override
  String get tomorrow => 'Утре';

  @override
  String get googleCalendarComingSoon => 'Google Calendar интеграција ускоро!';

  @override
  String connectedAsUser(String userId) {
    return 'Поврзано како корисник: $userId';
  }

  @override
  String get defaultWorkspace => 'Стандардна работна област';

  @override
  String get tasksCreatedInWorkspace => 'Задачите ќе бидат создадени во оваа работна област';

  @override
  String get defaultProjectOptional => 'Стандарден проект (опционално)';

  @override
  String get leaveUnselectedTasks => 'Оставете неизбрано за да создадете задачи без проект';

  @override
  String get noProjectsInWorkspace => 'Нема пронајдени проекти во оваа работна област';

  @override
  String get conversationTimeoutDesc =>
      'Изберете колку долго да чекате во тишина пред автоматско завршување на разговор:';

  @override
  String get timeout2Minutes => '2 минути';

  @override
  String get timeout2MinutesDesc => 'Завршете разговор по 2 минути тишина';

  @override
  String get timeout5Minutes => '5 минути';

  @override
  String get timeout5MinutesDesc => 'Завршете разговор по 5 минути тишина';

  @override
  String get timeout10Minutes => '10 минути';

  @override
  String get timeout10MinutesDesc => 'Завршете разговор по 10 минути тишина';

  @override
  String get timeout30Minutes => '30 минути';

  @override
  String get timeout30MinutesDesc => 'Завршете разговор по 30 минути тишина';

  @override
  String get timeout4Hours => '4 часа';

  @override
  String get timeout4HoursDesc => 'Завршете разговор по 4 часа тишина';

  @override
  String get conversationEndAfterHours => 'Разговорите сега ќе се завршат по 4 часа тишина';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Разговорите сега ќе се завршат по $minutes минута/и тишина';
  }

  @override
  String get tellUsPrimaryLanguage => 'Кажете ни го вашиот основен јазик';

  @override
  String get languageForTranscription =>
      'Поставете го вашиот јазик за поостри транскрипции и персонализирано искуство.';

  @override
  String get singleLanguageModeInfo => 'Режимот на еден јазик е активиран. Преводот е онемогучен за поголема точност.';

  @override
  String get searchLanguageHint => 'Пребарувајте јазик по име или код';

  @override
  String get noLanguagesFound => 'Нема пронајдени јазици';

  @override
  String get skip => 'Прескочи';

  @override
  String languageSetTo(String language) {
    return 'Јазик поставен на $language';
  }

  @override
  String get failedToSetLanguage => 'Не можеше да се постави јазикот';

  @override
  String appSettings(String appName) {
    return '$appName поставки';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Откажување од $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Ова ќе го отстрани вашиот $appName пристап. Ќе треба да се повторно поврзете за да го користите.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Поврзано на $appName';
  }

  @override
  String get account => 'Сметка';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Ваших работни предмети ќе бидат синхронизирани на вашата $appName сметка';
  }

  @override
  String get defaultSpace => 'Стандардна област';

  @override
  String get selectSpaceInWorkspace => 'Изберете област во вашата работна област';

  @override
  String get noSpacesInWorkspace => 'Нема пронајдени области во оваа работна област';

  @override
  String get defaultList => 'Стандардна листа';

  @override
  String get tasksAddedToList => 'Задачите ќе бидат додадени на оваа листа';

  @override
  String get noListsInSpace => 'Нема пронајдени листи во оваа област';

  @override
  String failedToLoadRepos(String error) {
    return 'Не можеше да се вчитаат складишта: $error';
  }

  @override
  String get defaultRepoSaved => 'Стандардното складиште е зачувано';

  @override
  String get failedToSaveDefaultRepo => 'Не можеше да се зачува стандардното складиште';

  @override
  String get defaultRepository => 'Стандардно складиште';

  @override
  String get selectDefaultRepoDesc =>
      'Изберете стандардно складиште за создавање на проблеми. Сепак можете да назначите различно складиште при создавање на проблеми.';

  @override
  String get noReposFound => 'Нема пронајдени складишта';

  @override
  String get private => 'Приватно';

  @override
  String updatedDate(String date) {
    return 'Ажурирано $date';
  }

  @override
  String get yesterday => 'Вчера';

  @override
  String daysAgo(int count) {
    return 'пред $count денови';
  }

  @override
  String get oneWeekAgo => 'пред 1 неделја';

  @override
  String weeksAgo(int count) {
    return 'пред $count недели';
  }

  @override
  String get oneMonthAgo => 'пред 1 месец';

  @override
  String monthsAgo(int count) {
    return 'пред $count месеци';
  }

  @override
  String get issuesCreatedInRepo => 'Проблемите ќе бидат создадени во вашето стандардно складиште';

  @override
  String get taskIntegrations => 'Интеграции на задачи';

  @override
  String get configureSettings => 'Конфигурирај поставки';

  @override
  String get completeAuthBrowser =>
      'Ве молиме завршете аутентификација во вашиот прелистувач. По завршувањето, вратете се во апликацијата.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Не можеше да се започне $appName аутентификација';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Поврзување на $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Ќе треба да го авторизирате Omi да создава задачи во вашата $appName сметка. Ова ќе го отвори вашиот прелистувач за аутентификација.';
  }

  @override
  String get continueButton => 'Продолжи';

  @override
  String appIntegration(String appName) {
    return '$appName интеграција';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Интеграција со $appName ускоро! Тешко работиме да вам донесеме повеќе опции за управување со задачи.';
  }

  @override
  String get gotIt => 'Разбрав';

  @override
  String get tasksExportedOneApp => 'Задачите можат да бидат извезени на една апликација одеднаш.';

  @override
  String get completeYourUpgrade => 'Завршете го вашиот надградба';

  @override
  String get importConfiguration => 'Конфигурирај увоз';

  @override
  String get exportConfiguration => 'Извезување конфигурација';

  @override
  String get bringYourOwn => 'Донесете ваше';

  @override
  String get payYourSttProvider => 'Слободно користете omi. Плаќате директно на вашиот STT добавувач.';

  @override
  String get freeMinutesMonth => '1,200 слободни минути/месец вклучени. Неограничено со ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Домаќин е задолжителен';

  @override
  String get validPortRequired => 'Валиден порт е задолжителен';

  @override
  String get validWebsocketUrlRequired => 'Валиден WebSocket URL е задолжителен (wss://)';

  @override
  String get apiUrlRequired => 'API URL е задолжителен';

  @override
  String get apiKeyRequired => 'API клучот е задолжителен';

  @override
  String get invalidJsonConfig => 'Невалидна JSON конфигурација';

  @override
  String errorSaving(String error) {
    return 'Грешка при зачување: $error';
  }

  @override
  String get configCopiedToClipboard => 'Конфигурација копирана во клипбордот';

  @override
  String get pasteJsonConfig => 'Залепете ја вашата JSON конфигурација подолу:';

  @override
  String get addApiKeyAfterImport => 'Ќе треба да го додадете ваш API клуч по увезувањето';

  @override
  String get paste => 'Залепи';

  @override
  String get import => 'Увоз';

  @override
  String get invalidProviderInConfig => 'Невалиден добавувач во конфигурација';

  @override
  String importedConfig(String providerName) {
    return 'Увезена $providerName конфигурација';
  }

  @override
  String invalidJson(String error) {
    return 'Невалидна JSON: $error';
  }

  @override
  String get provider => 'Добавувач';

  @override
  String get live => 'Вживо';

  @override
  String get onDevice => 'На уред';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Внесете го вашиот STT HTTP крајна точка';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Внесете го вашиот вживо STT WebSocket крајна точка';

  @override
  String get apiKey => 'API клуч';

  @override
  String get enterApiKey => 'Внесете го вашиот API клуч';

  @override
  String get storedLocallyNeverShared => 'Зачувано локално, никогаш споделено';

  @override
  String get host => 'Домаќин';

  @override
  String get port => 'Порт';

  @override
  String get advanced => 'Напредно';

  @override
  String get configuration => 'Конфигурација';

  @override
  String get requestConfiguration => 'Конфигурирај барање';

  @override
  String get responseSchema => 'Шема на одговор';

  @override
  String get modified => 'Измено';

  @override
  String get resetRequestConfig => 'Ресетирај конфигурација на стандардна';

  @override
  String get logs => 'Дневници';

  @override
  String get logsCopied => 'Дневници копирани';

  @override
  String get noLogsYet => 'Нема дневници сеуште. Почнете да снимате за да видите прилагодена STT активност.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device користи $reason. Omi ќе биде користен.';
  }

  @override
  String get omiTranscription => 'Omi транскрипција';

  @override
  String get bestInClassTranscription => 'Најдобра транскрипција без подесување';

  @override
  String get instantSpeakerLabels => 'Веќе означување на звучник';

  @override
  String get languageTranslation => 'Превод на 100+ јазици';

  @override
  String get optimizedForConversation => 'Оптимизирано за разговор';

  @override
  String get autoLanguageDetection => 'Автоматско откривање на јазик';

  @override
  String get highAccuracy => 'Висока точност';

  @override
  String get privacyFirst => 'Приватност прво';

  @override
  String get saveChanges => 'Зачувај промени';

  @override
  String get resetToDefault => 'Ресетирај на стандардна';

  @override
  String get viewTemplate => 'Преглед шаблон';

  @override
  String get trySomethingLike => 'Пробајте нешто како...';

  @override
  String get tryIt => 'Пробај го';

  @override
  String get creatingPlan => 'Создавање план';

  @override
  String get developingLogic => 'Развивање логика';

  @override
  String get designingApp => 'Дизајнирање апликација';

  @override
  String get generatingIconStep => 'Генерирање икона';

  @override
  String get finalTouches => 'Последни штипови';

  @override
  String get processing => 'Обработка...';

  @override
  String get features => 'Карактеристики';

  @override
  String get creatingYourApp => 'Создавање на вашата апликација...';

  @override
  String get generatingIcon => 'Генерирање икона...';

  @override
  String get whatShouldWeMake => 'Што треба да направиме?';

  @override
  String get appName => 'Име на апликација';

  @override
  String get description => 'Опис';

  @override
  String get publicLabel => 'Јавно';

  @override
  String get privateLabel => 'Приватно';

  @override
  String get free => 'Слободно';

  @override
  String get perMonth => '/ месец';

  @override
  String get tailoredConversationSummaries => 'Усклађени резимеа на разговори';

  @override
  String get customChatbotPersonality => 'Прилагодена личност на chatbot';

  @override
  String get makePublic => 'Направи јавно';

  @override
  String get anyoneCanDiscover => 'Секој може да ја открие вашата апликација';

  @override
  String get onlyYouCanUse => 'Само вие можете да ја користите оваа апликација';

  @override
  String get paidApp => 'Платена апликација';

  @override
  String get usersPayToUse => 'Корисниците плаќаат да ја користат вашата апликација';

  @override
  String get freeForEveryone => 'Слободно за сите';

  @override
  String get perMonthLabel => '/ месец';

  @override
  String get creating => 'Создавање...';

  @override
  String get createApp => 'Создај апликација';

  @override
  String get searchingForDevices => 'Пребарување на уреди...';

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
  String get pairingSuccessful => 'СПАРУВАЊЕ УСПЕШНО';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Грешка при поврзување на Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Не прикажи повторно';

  @override
  String get iUnderstand => 'Разбирам';

  @override
  String get enableBluetooth => 'Активирај Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi има потреба од Bluetooth за поврзување на вашето нослива опрема. Ве молиме активирајте Bluetooth и пробајте повторно.';

  @override
  String get contactSupport => 'Контактирај поддршка?';

  @override
  String get connectLater => 'Поврзи се подоцна';

  @override
  String get grantPermissions => 'Одобри дозволи';

  @override
  String get backgroundActivity => 'Активност во позадина';

  @override
  String get backgroundActivityDesc => 'Дозволи Omi да работи во позадина за подобра стабилност';

  @override
  String get locationAccess => 'Пристап на локација';

  @override
  String get locationAccessDesc => 'Активирајте локација во позадина за целосно искуство';

  @override
  String get notifications => 'Известувања';

  @override
  String get notificationsDesc => 'Активирајте известувања за да останете информирани';

  @override
  String get locationServiceDisabled => 'Услугата за локација е деактивирана';

  @override
  String get locationServiceDisabledDesc =>
      'Услугата за локација е деактивирана. Ве молиме одите на Поставки > Приватност и безбедност > Услуги за локација и активирајте ја';

  @override
  String get backgroundLocationDenied => 'Пристап на локација во позадина одбиен';

  @override
  String get backgroundLocationDeniedDesc =>
      'Ве молиме одите на поставки на уредот и поставете дозвола за локација на \"Секогаш дозволи\"';

  @override
  String get lovingOmi => 'Вам се допаѓа Omi?';

  @override
  String get leaveReviewIos =>
      'Помогнете ни да дојдеме до повеќе луѓе со оставување рецензија во App Store. Вашата повратна информација ни значи многу!';

  @override
  String get leaveReviewAndroid =>
      'Помогнете ни да дојдеме до повеќе луѓе со оставување рецензија во Google Play Store. Вашата повратна информација ни значи многу!';

  @override
  String get rateOnAppStore => 'Оценете во App Store';

  @override
  String get rateOnGooglePlay => 'Оценете на Google Play';

  @override
  String get maybeLater => 'Можеби подоцна';

  @override
  String get speechProfileIntro =>
      'Omi има потреба да научи ваши цели и вашиот глас. Ќе можете да го менувате подоцна.';

  @override
  String get getStarted => 'Почни';

  @override
  String get allDone => 'Сè завршено!';

  @override
  String get keepGoing => 'Продолжи, ја правиш добро работа';

  @override
  String get skipThisQuestion => 'Прескочи го овој прашање';

  @override
  String get skipForNow => 'Прескочи засега';

  @override
  String get connectionError => 'Грешка при поврзување';

  @override
  String get connectionErrorDesc =>
      'Не успеав да се поврзам на серверот. Ве молиме проверете ја вашата интернет врска и пробајте повторно.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Пронајдена невалидна снимка';

  @override
  String get multipleSpeakersDesc =>
      'Изгледа дека има повеќе звучници во снимката. Ве молиме осигурајте се дека сте на тивуа локација и пробајте повторно.';

  @override
  String get tooShortDesc => 'Нема доволно откриен говор. Ве молиме говорете повеќе и пробајте повторно.';

  @override
  String get invalidRecordingDesc => 'Ве молиме осигурајте се дека говорите барем 5 секунди и не повеќе од 90.';

  @override
  String get areYouThere => 'Дали сте тука?';

  @override
  String get noSpeechDesc =>
      'Не можевме да откријеме никакво говор. Ве молиме осигурајте се да говорите барем 10 секунди и не повеќе од 3 минути.';

  @override
  String get connectionLost => 'Врската е прекината';

  @override
  String get connectionLostDesc =>
      'Врската беше прекината. Ве молиме проверете ја вашата интернет врска и пробајте повторно.';

  @override
  String get tryAgain => 'Пробај повторно';

  @override
  String get connectOmiOmiGlass => 'Поврзување Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Продолжи без уред';

  @override
  String get permissionsRequired => 'Потребни се дозволи';

  @override
  String get permissionsRequiredDesc =>
      'Оваа апликација има потреба од Bluetooth и дозволи за локација за да функционира правилно. Ве молиме активирајте ги во поставките.';

  @override
  String get openSettings => 'Отворете поставки';

  @override
  String get wantDifferentName => 'Сакате да использите некое друго име?';

  @override
  String get whatsYourName => 'Кое е вашето име?';

  @override
  String get speakTranscribeSummarize => 'Говори. Транскрибирај. Сумирај.';

  @override
  String get signInWithApple => 'Најавете се со Apple';

  @override
  String get signInWithGoogle => 'Најавете се со Google';

  @override
  String get byContinuingAgree => 'Со продолжување, се согласувате со нашиот ';

  @override
  String get termsOfUse => 'Услови на користење';

  @override
  String get omiYourAiCompanion => 'Omi – Ваш AI сопатник';

  @override
  String get captureEveryMoment =>
      'Фатете секој момент. Добијте AI-напаљени\nрезимеа. Никогаш нема да пишувате белешки повторно.';

  @override
  String get appleWatchSetup => 'Подесување на Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Дозволата е побарана!';

  @override
  String get microphonePermission => 'Дозвола за микрофон';

  @override
  String get permissionGrantedNow =>
      'Дозволата е дозволена! Сега:\n\nОтворете ја апликацијата Omi на вашиот часовник и притиснете \"Продолжи\" подолу';

  @override
  String get needMicrophonePermission =>
      'Ни треба дозвола за микрофон.\n\n1. Притиснете \"Одобри дозвола\"\n2. Дозволете на вашиот iPhone\n3. Апликацијата на часовникот ќе се затвори\n4. Отворете ја повторно и притиснете \"Продолжи\"';

  @override
  String get grantPermissionButton => 'Одобри дозвола';

  @override
  String get needHelp => 'Ви треба помош?';

  @override
  String get troubleshootingSteps =>
      'Отстранување на проблеми:\n\n1. Осигурајте се дека Omi е инсталирана на вашиот часовник\n2. Отворете ја апликацијата Omi на вашиот часовник\n3. Барајте го popup за дозвола\n4. Притиснете \"Дозволи\" кога ќе се барате\n5. Апликацијата на вашиот часовник ќе се затвори - отворете ја повторно\n6. Вратете се и притиснете \"Продолжи\" на вашиот iPhone';

  @override
  String get recordingStartedSuccessfully => 'Снимката е успешно започната!';

  @override
  String get permissionNotGrantedYet =>
      'Дозволата сеуште не е дозволена. Ве молиме осигурајте се дека сте дозволиле пристап на микрофон и отворивте ја апликацијата на вашиот часовник.';

  @override
  String errorRequestingPermission(String error) {
    return 'Грешка при барање на дозвола: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Грешка при започнување на снимката: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Изберете го вашиот основен јазик';

  @override
  String get languageBenefits => 'Поставете го вашиот јазик за поостри транскрипции и персонализирано искуство';

  @override
  String get whatsYourPrimaryLanguage => 'Кое е вашето основно јазик?';

  @override
  String get selectYourLanguage => 'Изберете го вашиот јазик';

  @override
  String get personalGrowthJourney => 'Вашите лично растење патување со AI што слуша на секое ваше слово.';

  @override
  String get actionItemsTitle => 'За да направам';

  @override
  String get actionItemsDescription => 'Притиснете за уредување • Долго притиснете за избор • Swipe за акции';

  @override
  String get tabToDo => 'За да направам';

  @override
  String get tabDone => 'Завршено';

  @override
  String get tabOld => 'Старо';

  @override
  String get emptyTodoMessage => '🎉 Сè е расчистено!\nНема предстојни работни предмети';

  @override
  String get emptyDoneMessage => 'Нема завршени предмети сеуште';

  @override
  String get emptyOldMessage => '✅ Нема стари задачи';

  @override
  String get noItems => 'Нема предмети';

  @override
  String get actionItemMarkedIncomplete => 'Работниот предмет е означен како незавршен';

  @override
  String get actionItemCompleted => 'Работниот предмет е завршен';

  @override
  String get deleteActionItemTitle => 'Избрирајте го работниот предмет';

  @override
  String get deleteActionItemMessage => 'Дали сте сигурни дека сакате да го избришете овој работен предмет?';

  @override
  String get deleteSelectedItemsTitle => 'Избрирајте ги избраните предмети';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Дали сте сигурни дека сакате да избришете $count избрани работни предмет$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Работниот предмет \"$description\" е избришан';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count работни предмет$s избришани';
  }

  @override
  String get failedToDeleteItem => 'Не успеав да го избришам работниот предмет';

  @override
  String get failedToDeleteItems => 'Не успеав да ги избришам предметите';

  @override
  String get failedToDeleteSomeItems => 'Не успеав да избришам некои предмети';

  @override
  String get welcomeActionItemsTitle => 'Готови за работни предмети';

  @override
  String get welcomeActionItemsDescription =>
      'Вашиот AI автоматски ќе извлекува задачи и за да направам од вашите разговори. Тие ќе се појават овде кога ќе бидат создадени.';

  @override
  String get autoExtractionFeature => 'Автоматски извлечено од разговори';

  @override
  String get editSwipeFeature => 'Притиснете за уредување, swipe за завршување или бришење';

  @override
  String itemsSelected(int count) {
    return '$count избрано';
  }

  @override
  String get selectAll => 'Изберете ги сите';

  @override
  String get deleteSelected => 'Избришете избрано';

  @override
  String get searchMemories => 'Пребарување на успомени...';

  @override
  String get memoryDeleted => 'Успоменa е избришана.';

  @override
  String get undo => 'Врати';

  @override
  String get noMemoriesYet => '🧠 Нема успомени сеуште';

  @override
  String get noAutoMemories => 'Нема автоматски извлечени успомени сеуште';

  @override
  String get noManualMemories => 'Нема ручни успомени сеуште';

  @override
  String get noMemoriesInCategories => 'Нема успомени во овие категории';

  @override
  String get noMemoriesFound => '🔍 Нема пронајдени успомени';

  @override
  String get addFirstMemory => 'Додајте ја вашата прва успомена';

  @override
  String get clearMemoryTitle => 'Исчисти ја меморијата на Omi';

  @override
  String get clearMemoryMessage =>
      'Дали сте сигурни дека сакате да ја исчистите меморијата на Omi? Оваа акција не може да биде намалена.';

  @override
  String get clearMemoryButton => 'Исчисти меморија';

  @override
  String get memoryClearedSuccess => 'Меморијата на Omi за вас е исчистена';

  @override
  String get noMemoriesToDelete => 'Нема успомени за бришење';

  @override
  String get createMemoryTooltip => 'Создај нова успомена';

  @override
  String get createActionItemTooltip => 'Создај нов работен предмет';

  @override
  String get memoryManagement => 'Управување на меморија';

  @override
  String get filterMemories => 'Филтрирај успомени';

  @override
  String totalMemoriesCount(int count) {
    return 'Имате $count вкупно успомени';
  }

  @override
  String get publicMemories => 'Јавни успомени';

  @override
  String get privateMemories => 'Приватни успомени';

  @override
  String get makeAllPrivate => 'Направи ги сите успомени приватни';

  @override
  String get makeAllPublic => 'Направи ги сите успомени јавни';

  @override
  String get deleteAllMemories => 'Избршите ги сите успомени';

  @override
  String get allMemoriesPrivateResult => 'Сите успомени се сега приватни';

  @override
  String get allMemoriesPublicResult => 'Сите успомени се сега јавни';

  @override
  String get newMemory => '✨ Нова успомена';

  @override
  String get editMemory => '✏️ Уредување успомена';

  @override
  String get memoryContentHint => 'Волам да јадам сладолед...';

  @override
  String get failedToSaveMemory => 'Не успеав да зачувам. Ве молиме проверете го вашиот врска.';

  @override
  String get saveMemory => 'Зачувај успомена';

  @override
  String get retry => 'Пробај повторно';

  @override
  String get createActionItem => 'Создај работен предмет';

  @override
  String get editActionItem => 'Уредување работен предмет';

  @override
  String get actionItemDescriptionHint => 'Што треба да се направи?';

  @override
  String get actionItemDescriptionEmpty => 'Описот на работниот предмет не може да биде празен.';

  @override
  String get actionItemUpdated => 'Работниот предмет е ажуриран';

  @override
  String get failedToUpdateActionItem => 'Не успеав да го ажурирам работниот предмет';

  @override
  String get actionItemCreated => 'Работниот предмет е создаден';

  @override
  String get failedToCreateActionItem => 'Не успеав да создам работен предмет';

  @override
  String get dueDate => 'Рок';

  @override
  String get time => 'Време';

  @override
  String get addDueDate => 'Додај рок';

  @override
  String get pressDoneToSave => 'Притиснете готово за зачување';

  @override
  String get pressDoneToCreate => 'Притиснете готово за создавање';

  @override
  String get filterAll => 'Сите';

  @override
  String get filterSystem => 'За вас';

  @override
  String get filterInteresting => 'Увиди';

  @override
  String get filterManual => 'Ручни';

  @override
  String get completed => 'Завршено';

  @override
  String get markComplete => 'Означи како завршено';

  @override
  String get actionItemDeleted => 'Работниот предмет е избришан';

  @override
  String get failedToDeleteActionItem => 'Не успеав да го избришам работниот предмет';

  @override
  String get deleteActionItemConfirmTitle => 'Избрирајте го работниот предмет';

  @override
  String get deleteActionItemConfirmMessage => 'Дали сте сигурни дека сакате да го избришете овој работен предмет?';

  @override
  String get appLanguage => 'Јазик на апликација';

  @override
  String get appInterfaceSectionTitle => 'ИНТЕРФЕЈС НА АПЛИКАЦИЈА';

  @override
  String get speechTranscriptionSectionTitle => 'ГОВОР И ТРАНСКРИПЦИЈА';

  @override
  String get languageSettingsHelperText =>
      'Јазикот на апликацијата менува менија и копчиња. Јазикот на говор влијае на тоа како ваши записи се транскрибираат.';

  @override
  String get translationNotice => 'Известување за превод';

  @override
  String get translationNoticeMessage =>
      'Omi преводи разговори на вашиот основен јазик. Ажурирајте го во било кое време во Поставки → Профили.';

  @override
  String get pleaseCheckInternetConnection => 'Ве молиме проверете ја вашата интернет врска и пробајте повторно';

  @override
  String get pleaseSelectReason => 'Ве молиме изберете причина';

  @override
  String get tellUsMoreWhatWentWrong => 'Кажете ни повеќе за тоа што се случи...';

  @override
  String get selectText => 'Изберете текст';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Максимум $count цели дозволени';
  }

  @override
  String get conversationCannotBeMerged => 'Овој разговор не може да биде спојен (заклучен или веќе се спојува)';

  @override
  String get pleaseEnterFolderName => 'Ве молиме внесете име на папка';

  @override
  String get failedToCreateFolder => 'Не успеав да создам папка';

  @override
  String get failedToUpdateFolder => 'Не успеав да ја ажурирам папката';

  @override
  String get folderName => 'Име на папка';

  @override
  String get descriptionOptional => 'Опис (по избор)';

  @override
  String get failedToDeleteFolder => 'Неуспешно бришење на папка';

  @override
  String get editFolder => 'Уреди папка';

  @override
  String get deleteFolder => 'Избриши папка';

  @override
  String get transcriptCopiedToClipboard => 'Препис копиран во клипбордот';

  @override
  String get summaryCopiedToClipboard => 'Резиме копирано во клипбордот';

  @override
  String get conversationUrlCouldNotBeShared => 'URL на разговор не можеше да се сподели.';

  @override
  String get urlCopiedToClipboard => 'URL копиран во клипбордот';

  @override
  String get exportTranscript => 'Извези препис';

  @override
  String get exportSummary => 'Извези резиме';

  @override
  String get exportButton => 'Извези';

  @override
  String get actionItemsCopiedToClipboard => 'Активни предмети копирани во клипбордот';

  @override
  String get summarize => 'Резимирај';

  @override
  String get generateSummary => 'Генерирај резиме';

  @override
  String get conversationNotFoundOrDeleted => 'Разговор не е пронајден или е избришан';

  @override
  String get deleteMemory => 'Избриши меморија';

  @override
  String get thisActionCannotBeUndone => 'Оваа акција не може да се отповика.';

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
  String get noMemoriesInCategory => 'Нема мемории во оваа категорија сè уште';

  @override
  String get addYourFirstMemory => 'Додај твоја прва меморија';

  @override
  String get firmwareDisconnectUsb => 'Исклучи USB';

  @override
  String get firmwareUsbWarning => 'USB врска durante обновувања може да го оштети твојот уред.';

  @override
  String get firmwareBatteryAbove15 => 'Батерија над 15%';

  @override
  String get firmwareEnsureBattery => 'Осигури дека твојот уред има 15% батерија.';

  @override
  String get firmwareStableConnection => 'Стабилна врска';

  @override
  String get firmwareConnectWifi => 'Поврзи се на WiFi или мобилна мрежа.';

  @override
  String failedToStartUpdate(String error) {
    return 'Неуспешен почеток на ажурирање: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Пред ажурирање, осигури:';

  @override
  String get confirmed => 'Потврдено!';

  @override
  String get release => 'Издание';

  @override
  String get slideToUpdate => 'Движи нагоре за ажурирање';

  @override
  String copiedToClipboard(String title) {
    return '$title копирано во клипбордот';
  }

  @override
  String get batteryLevel => 'Ниво на батерија';

  @override
  String get charging => 'Полнење';

  @override
  String get productUpdate => 'Ажурирање на производ';

  @override
  String get offline => 'Офлајн';

  @override
  String get available => 'Достапно';

  @override
  String get unpairDeviceDialogTitle => 'Отвори паирање на уред';

  @override
  String get unpairDeviceDialogMessage =>
      'Ова ќе го отвори паирањето на уредот така што може да се поврзе на телефон. Ќе мораш да отидеш на Поставки > Bluetooth и да го заборавиш уредот за да го завршиш процесот.';

  @override
  String get unpair => 'Отвори паирање';

  @override
  String get unpairAndForgetDevice => 'Отвори паирање и заборави уред';

  @override
  String get unknownDevice => 'Непознато';

  @override
  String get unknown => 'Непознато';

  @override
  String get productName => 'Име на производ';

  @override
  String get serialNumber => 'Серијски број';

  @override
  String get connected => 'Поврзано';

  @override
  String get privacyPolicyTitle => 'Политика на приватност';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label копирано';
  }

  @override
  String get noApiKeysYet => 'Нема API клучеви сè уште';

  @override
  String get createKeyToGetStarted => 'Создај клуч за да почнеш';

  @override
  String get configureSttProvider => 'Конфигурирај STT обезбедувач';

  @override
  String get setWhenConversationsAutoEnd => 'Постави кога разговорите автоматски завршуваат';

  @override
  String get importDataFromOtherSources => 'Увези податоци од други извори';

  @override
  String get debugAndDiagnostics => 'Дебугирање и дијагностика';

  @override
  String get autoDeletesAfter3Days => 'Автоматски се брише по 3 денови.';

  @override
  String get helpsDiagnoseIssues => 'Помага да се дијагностицираат проблеми';

  @override
  String get exportStartedMessage => 'Извезување почнато. Ово може да потрае неколку секунди...';

  @override
  String get exportConversationsToJson => 'Извези разговори во JSON датотека';

  @override
  String get knowledgeGraphDeletedSuccess => 'Граф на знаење успешно избришан';

  @override
  String failedToDeleteGraph(String error) {
    return 'Неуспешно бришење на граф: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Обриши сите јазли и врски';

  @override
  String get addToClaudeDesktopConfig => 'Додај во claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Поврзи AI асистенти со твои податоци';

  @override
  String get useYourMcpApiKey => 'Користи твој MCP API клуч';

  @override
  String get realTimeTranscript => 'Препис во реално време';

  @override
  String get experimental => 'Експериментално';

  @override
  String get transcriptionDiagnostics => 'Дијагностика на транскрипција';

  @override
  String get detailedDiagnosticMessages => 'Детални дијагностички пораки';

  @override
  String get autoCreateSpeakers => 'Автоматски создавај говорници';

  @override
  String get autoCreateWhenNameDetected => 'Автоматски создавај кога е детектирано име';

  @override
  String get followUpQuestions => 'Следни прашања';

  @override
  String get suggestQuestionsAfterConversations => 'Предложи прашања по разговори';

  @override
  String get goalTracker => 'Траченик на цели';

  @override
  String get trackPersonalGoalsOnHomepage => 'Прати твои лични цели на почетната страница';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Описот на активниот предмет не може да буде празан';

  @override
  String get saved => 'Зачувано';

  @override
  String get overdue => 'Закаснено';

  @override
  String get failedToUpdateDueDate => 'Неуспешно ажурирање на датумот на доспеност';

  @override
  String get markIncomplete => 'Означи како незавршено';

  @override
  String get editDueDate => 'Уреди датум на доспеност';

  @override
  String get setDueDate => 'Постави датум на доспеност';

  @override
  String get clearDueDate => 'Обриши датум на доспеност';

  @override
  String get failedToClearDueDate => 'Неуспешно бришење на датумот на доспеност';

  @override
  String get mondayAbbr => 'Пон';

  @override
  String get tuesdayAbbr => 'Вто';

  @override
  String get wednesdayAbbr => 'Сря';

  @override
  String get thursdayAbbr => 'Чет';

  @override
  String get fridayAbbr => 'Пет';

  @override
  String get saturdayAbbr => 'Саб';

  @override
  String get sundayAbbr => 'Нед';

  @override
  String get howDoesItWork => 'Како функционира?';

  @override
  String get sdCardSyncDescription =>
      'SD картата за синхронизација ќе ги увезе твои мемории од SD картата во апликацијата';

  @override
  String get checksForAudioFiles => 'Проверува за аудио датотеки на SD картата';

  @override
  String get omiSyncsAudioFiles => 'Omi потоа синхронизира аудио датотеки со серверот';

  @override
  String get serverProcessesAudio => 'Серверот обработува аудио датотеки и создава мемории';

  @override
  String get youreAllSet => 'Сте целосно подготвени!';

  @override
  String get welcomeToOmiDescription =>
      'Добредојде на Omi! Твојот AI придружник е подготвен да ти помогне со разговори, задачи и повеќе.';

  @override
  String get startUsingOmi => 'Почни да користиш Omi';

  @override
  String get back => 'Назад';

  @override
  String get keyboardShortcuts => 'Пречици на тастатура';

  @override
  String get toggleControlBar => 'Вклучи/исклучи контролна лента';

  @override
  String get pressKeys => 'Притисни копчиња...';

  @override
  String get cmdRequired => '⌘ е задолжително';

  @override
  String get invalidKey => 'Невалидно копче';

  @override
  String get space => 'Простор';

  @override
  String get search => 'Барај';

  @override
  String get searchPlaceholder => 'Барај...';

  @override
  String get untitledConversation => 'Без назив разговор';

  @override
  String countRemaining(String count) {
    return '$count преостанаа';
  }

  @override
  String get addGoal => 'Додај цел';

  @override
  String get editGoal => 'Уреди цел';

  @override
  String get icon => 'Икона';

  @override
  String get goalTitle => 'Насlov на цел';

  @override
  String get current => 'Тековно';

  @override
  String get target => 'Целта';

  @override
  String get saveGoal => 'Зачувај';

  @override
  String get goals => 'Цели';

  @override
  String get tapToAddGoal => 'Допри за да додаш цел';

  @override
  String welcomeBack(String name) {
    return 'Добредојде, $name';
  }

  @override
  String get yourConversations => 'Твои разговори';

  @override
  String get reviewAndManageConversations => 'Прегледај и управувај со твои зафатени разговори';

  @override
  String get startCapturingConversations => 'Почни да зафаќаш разговори со твој Omi уред за да ги видиш тука.';

  @override
  String get useMobileAppToCapture => 'Користи твоја мобилна апликација за да зафатиш аудио';

  @override
  String get conversationsProcessedAutomatically => 'Разговорите се обработуваат автоматски';

  @override
  String get getInsightsInstantly => 'Добивај увиди и резимеа веднаш';

  @override
  String get showAll => 'Покажи се';

  @override
  String get noTasksForToday => 'Нема задачи за денес.\nПрашај Omi за повеќе задачи или создај рачно.';

  @override
  String get dailyScore => 'ДНЕВНА ОЦЕНКА';

  @override
  String get dailyScoreDescription => 'Оценка која ти помага да се\nфокусираш на извршување.';

  @override
  String get searchResults => 'Резултати од барање';

  @override
  String get actionItems => 'Активни предмети';

  @override
  String get tasksToday => 'Денес';

  @override
  String get tasksTomorrow => 'Утре';

  @override
  String get tasksNoDeadline => 'Нема рок';

  @override
  String get tasksLater => 'Подоцна';

  @override
  String get loadingTasks => 'Се учитуваат задачи...';

  @override
  String get tasks => 'Задачи';

  @override
  String get swipeTasksToIndent => 'Движи задачи за да ги вовлачиш, влечи помеѓу категории';

  @override
  String get create => 'Создај';

  @override
  String get noTasksYet => 'Нема задачи сè уште';

  @override
  String get tasksFromConversationsWillAppear =>
      'Задачи од твои разговори ќе се појават тука.\nКликни Создај за да додаш една рачно.';

  @override
  String get monthJan => 'јан';

  @override
  String get monthFeb => 'феб';

  @override
  String get monthMar => 'мар';

  @override
  String get monthApr => 'апр';

  @override
  String get monthMay => 'мај';

  @override
  String get monthJun => 'јун';

  @override
  String get monthJul => 'јул';

  @override
  String get monthAug => 'авг';

  @override
  String get monthSep => 'сеп';

  @override
  String get monthOct => 'окт';

  @override
  String get monthNov => 'ное';

  @override
  String get monthDec => 'дек';

  @override
  String get timePM => 'по пладне';

  @override
  String get timeAM => 'претпладне';

  @override
  String get actionItemUpdatedSuccessfully => 'Активниот предмет е успешно ажуриран';

  @override
  String get actionItemCreatedSuccessfully => 'Активниот предмет е успешно создаден';

  @override
  String get actionItemDeletedSuccessfully => 'Активниот предмет е успешно избришан';

  @override
  String get deleteActionItem => 'Избриши активен предмет';

  @override
  String get deleteActionItemConfirmation =>
      'Дали си сигурен дека сакаш да го избришеш овој активен предмет? Оваа акција не може да се отповика.';

  @override
  String get enterActionItemDescription => 'Внеси опис на активниот предмет...';

  @override
  String get markAsCompleted => 'Означи како завршено';

  @override
  String get setDueDateAndTime => 'Постави датум и време на доспеност';

  @override
  String get reloadingApps => 'Повторно учитување на апликации...';

  @override
  String get loadingApps => 'Се учитуваат апликации...';

  @override
  String get browseInstallCreateApps => 'Прегледај, инсталирај и создавај апликации';

  @override
  String get all => 'Се';

  @override
  String get open => 'Отвори';

  @override
  String get install => 'Инсталирај';

  @override
  String get noAppsAvailable => 'Нема достапни апликации';

  @override
  String get unableToLoadApps => 'Не можам да ги учитам апликациите';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Пробај да ги прилагодиш условите за барање или филтрите';

  @override
  String get checkBackLaterForNewApps => 'Врати се подоцна за нови апликации';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Молиме провери твоја интернет врска и пробај повторно';

  @override
  String get createNewApp => 'Создај нова апликација';

  @override
  String get buildSubmitCustomOmiApp => 'Создај и поднеси твоја прилагодена Omi апликација';

  @override
  String get submittingYourApp => 'Поднесување на твоја апликација...';

  @override
  String get preparingFormForYou => 'Подготвување на формуларот за тебе...';

  @override
  String get appDetails => 'Детали на апликација';

  @override
  String get paymentDetails => 'Детали за плаќање';

  @override
  String get previewAndScreenshots => 'Преглед и снимки на екран';

  @override
  String get appCapabilities => 'Способности на апликација';

  @override
  String get aiPrompts => 'AI упатствувања';

  @override
  String get chatPrompt => 'Упатствување за разговор';

  @override
  String get chatPromptPlaceholder =>
      'Ти си одлична апликација, твоја работа е да одговориш на прашањата на корисникот и да го направиш среќен...';

  @override
  String get conversationPrompt => 'Упатствување за разговор';

  @override
  String get conversationPromptPlaceholder => 'Ти си одлична апликација, ќе добиеш препис и резиме на разговор...';

  @override
  String get notificationScopes => 'Опсег на известувања';

  @override
  String get appPrivacyAndTerms => 'Приватност и услови на апликација';

  @override
  String get makeMyAppPublic => 'Направи моја апликација јавна';

  @override
  String get submitAppTermsAgreement =>
      'Со поднесување на оваа апликација, се согласувам со Omi AI услови за услуга и политика за приватност';

  @override
  String get submitApp => 'Поднеси апликација';

  @override
  String get needHelpGettingStarted => 'Ти треба помош за почеток?';

  @override
  String get clickHereForAppBuildingGuides => 'Кликни тука за водичи за изградба на апликации и документација';

  @override
  String get submitAppQuestion => 'Поднеси апликација?';

  @override
  String get submitAppPublicDescription =>
      'Твоја апликација ќе биде прегледана и направена јавна. Можеш да почнеш да ја користиш веднаш, дури и за време на преглед!';

  @override
  String get submitAppPrivateDescription =>
      'Твоја апликација ќе биде прегледана и направена достапна за тебе приватно. Можеш да почнеш да ја користиш веднаш, дури и за време на преглед!';

  @override
  String get startEarning => 'Почни да заработуваш! 💰';

  @override
  String get connectStripeOrPayPal => 'Поврзи Stripe или PayPal за да примиш плаќања за твоја апликација.';

  @override
  String get connectNow => 'Поврзи сега';

  @override
  String get installsCount => 'Инсталации';

  @override
  String get uninstallApp => 'Деинсталирај апликација';

  @override
  String get subscribe => 'Претплати се';

  @override
  String get dataAccessNotice => 'Известување за пристап до податоци';

  @override
  String get dataAccessWarning =>
      'Оваа апликација ќе има пристап до твои податоци. Omi AI не е одговорна за начинот на кој твои податоци се користат, менуваат или бришат од оваа апликација';

  @override
  String get installApp => 'Инсталирај апликација';

  @override
  String get betaTesterNotice =>
      'Ти си бета тестер за оваа апликација. Сè уште не е јавна. Ќе биде јавна откако ќе биде одобрена.';

  @override
  String get appUnderReviewOwner =>
      'Твоја апликација е под преглед и видлива само за тебе. Ќе биде јавна откако ќе биде одобрена.';

  @override
  String get appRejectedNotice =>
      'Твоја апликација е одбиена. Молиме ажурирај ги деталите на апликацијата и повторно поднеси за преглед.';

  @override
  String get setupSteps => 'Чекори на подготовка';

  @override
  String get setupInstructions => 'Упатствувања за подготовка';

  @override
  String get integrationInstructions => 'Упатствувања за интеграција';

  @override
  String get preview => 'Преглед';

  @override
  String get aboutTheApp => 'За апликацијата';

  @override
  String get chatPersonality => 'Личност на разговор';

  @override
  String get ratingsAndReviews => 'Оценки и критики';

  @override
  String get noRatings => 'нема оценки';

  @override
  String ratingsCount(String count) {
    return '$count+ оценки';
  }

  @override
  String get errorActivatingApp => 'Грешка при активирање на апликацијата';

  @override
  String get integrationSetupRequired => 'Ако ова е интеграциона апликација, осигури дека подготовката е завршена.';

  @override
  String get installed => 'Инсталирано';

  @override
  String get appIdLabel => 'ID на апликација';

  @override
  String get appNameLabel => 'Име на апликација';

  @override
  String get appNamePlaceholder => 'Моја одлична апликација';

  @override
  String get pleaseEnterAppName => 'Молиме внеси име на апликација';

  @override
  String get categoryLabel => 'Категорија';

  @override
  String get selectCategory => 'Избери категорија';

  @override
  String get descriptionLabel => 'Опис';

  @override
  String get appDescriptionPlaceholder =>
      'Моја одлична апликација е одлична апликација која прави невероватни работи. Таа е најдобрата апликација кога икогаш!';

  @override
  String get pleaseProvideValidDescription => 'Молиме обезбеди важечки опис';

  @override
  String get appPricingLabel => 'Цена на апликација';

  @override
  String get noneSelected => 'Ниеден избран';

  @override
  String get appIdCopiedToClipboard => 'ID на апликација копиран во клипбордот';

  @override
  String get appCategoryModalTitle => 'Категорија на апликација';

  @override
  String get pricingFree => 'Слободно';

  @override
  String get pricingPaid => 'Плаќано';

  @override
  String get loadingCapabilities => 'Се учитуваат способности...';

  @override
  String get filterInstalled => 'Инсталирано';

  @override
  String get filterMyApps => 'Мои апликации';

  @override
  String get clearSelection => 'Обриши селекција';

  @override
  String get filterCategory => 'Категорија';

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
  String get filterCapabilities => 'Способности';

  @override
  String get noNotificationScopesAvailable => 'Нема достапни обсеги на известувања';

  @override
  String get popularApps => 'Популарни апликации';

  @override
  String get pleaseProvidePrompt => 'Молиме обезбеди упатствување';

  @override
  String chatWithAppName(String appName) {
    return 'Разговарај со $appName';
  }

  @override
  String get defaultAiAssistant => 'Стандарден AI асистент';

  @override
  String get readyToChat => '✨ Подготвено за разговор!';

  @override
  String get connectionNeeded => '🌐 Врска е потребна';

  @override
  String get startConversation => 'Почни разговор и дозволи магијата да почне';

  @override
  String get checkInternetConnection => 'Молиме провери твоја интернет врска';

  @override
  String get wasThisHelpful => 'Дали ово беше корисно?';

  @override
  String get thankYouForFeedback => 'Благодарам за твојата повратна информација!';

  @override
  String get maxFilesUploadError => 'Можеш да преземаш само 4 датотеки одеднаш';

  @override
  String get attachedFiles => '📎 Приложени датотеки';

  @override
  String get takePhoto => 'Фотографирај';

  @override
  String get captureWithCamera => 'Фатете со камера';

  @override
  String get selectImages => 'Избери слики';

  @override
  String get chooseFromGallery => 'Избери од галерија';

  @override
  String get selectFile => 'Избери датотека';

  @override
  String get chooseAnyFileType => 'Избери било каков тип датотека';

  @override
  String get cannotReportOwnMessages => 'Не можеш да пријавиш твои пораки';

  @override
  String get messageReportedSuccessfully => '✅ Порака е успешно пријавена';

  @override
  String get confirmReportMessage => 'Дали си сигурен дека сакаш да ја пријавиш оваа порака?';

  @override
  String get selectChatAssistant => 'Избери асистент за разговор';

  @override
  String get enableMoreApps => 'Активирај повеќе апликации';

  @override
  String get chatCleared => 'Разговор е обришан';

  @override
  String get clearChatTitle => 'Обриши разговор?';

  @override
  String get confirmClearChat =>
      'Дали си сигурен дека сакаш да го обришеш разговорот? Оваа акција не може да се отповика.';

  @override
  String get copy => 'Копирај';

  @override
  String get share => 'Сподели';

  @override
  String get report => 'Пријави';

  @override
  String get microphonePermissionRequired => 'Дозвола за микрофон е потребна за да прави повици';

  @override
  String get microphonePermissionDenied =>
      'Дозвола за микрофон е одбиена. Молиме додели дозвола во Системски поставки > Приватност и безбедност > Микрофон.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Неуспешна проверка на дозвола за микрофон: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Неуспешна транскрипција на аудио';

  @override
  String get transcribing => 'Се транскрибира...';

  @override
  String get transcriptionFailed => 'Транскрипција неуспешна';

  @override
  String get discardedConversation => 'Отфрлен разговор';

  @override
  String get at => 'во';

  @override
  String get from => 'од';

  @override
  String get copied => 'Копирано!';

  @override
  String get copyLink => 'Копирај врска';

  @override
  String get hideTranscript => 'Скриј препис';

  @override
  String get viewTranscript => 'Преглед препис';

  @override
  String get conversationDetails => 'Детали на разговор';

  @override
  String get transcript => 'Препис';

  @override
  String segmentsCount(int count) {
    return '$count делови';
  }

  @override
  String get noTranscriptAvailable => 'Нема достапен препис';

  @override
  String get noTranscriptMessage => 'Овој разговор нема препис.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL на разговор не можеше да се генерира.';

  @override
  String get failedToGenerateConversationLink => 'Неуспешна генерирање на врска на разговор';

  @override
  String get failedToGenerateShareLink => 'Неуспешна генерирање на врска за делење';

  @override
  String get reloadingConversations => 'Повторно учитување на разговори...';

  @override
  String get user => 'Корисник';

  @override
  String get starred => 'Означено со ѕвезда';

  @override
  String get date => 'Датум';

  @override
  String get noResultsFound => 'Нема пронајдени резултати';

  @override
  String get tryAdjustingSearchTerms => 'Пробај да ги прилагодиш условите за барање';

  @override
  String get starConversationsToFindQuickly => 'Означи разговори со ѕвезда за да ги пронајдеш брзо тука';

  @override
  String noConversationsOnDate(String date) {
    return 'Нема разговори на $date';
  }

  @override
  String get trySelectingDifferentDate => 'Пробај да избереш различен датум';

  @override
  String get conversations => 'Разговори';

  @override
  String get chat => 'Разговор';

  @override
  String get actions => 'Акции';

  @override
  String get syncAvailable => 'Синхронизација достапна';

  @override
  String get referAFriend => 'Препоручи пријател';

  @override
  String get help => 'Помош';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Надгради на Pro';

  @override
  String get getOmiDevice => 'Набави Omi уред';

  @override
  String get wearableAiCompanion => 'Преносив AI придружник';

  @override
  String get loadingMemories => 'Се учитуваат мемории...';

  @override
  String get allMemories => 'Сите мемории';

  @override
  String get aboutYou => 'За тебе';

  @override
  String get manual => 'Рачно';

  @override
  String get loadingYourMemories => 'Се учитуваат твои мемории...';

  @override
  String get createYourFirstMemory => 'Создај твоја прва меморија за да почнеш';

  @override
  String get tryAdjustingFilter => 'Пробај да ја прилагодиш твоја потрага или филтер';

  @override
  String get whatWouldYouLikeToRemember => 'Што би сакал да се сетиш?';

  @override
  String get category => 'Категорија';

  @override
  String get public => 'Јавно';

  @override
  String get failedToSaveCheckConnection => 'Неуспешно зачување. Молиме провери твоја врска.';

  @override
  String get createMemory => 'Создај меморија';

  @override
  String get deleteMemoryConfirmation =>
      'Дали си сигурен дека сакаш да ја избришеш оваа меморија? Оваа акција не може да се отповика.';

  @override
  String get makePrivate => 'Направи приватна';

  @override
  String get organizeAndControlMemories => 'Организирај и управувај со твои мемории';

  @override
  String get total => 'Вкупно';

  @override
  String get makeAllMemoriesPrivate => 'Направи сите мемории приватни';

  @override
  String get setAllMemoriesToPrivate => 'Постави сите мемории во приватна видливост';

  @override
  String get makeAllMemoriesPublic => 'Направи сите мемории јавни';

  @override
  String get setAllMemoriesToPublic => 'Постави сите мемории во јавна видливост';

  @override
  String get permanentlyRemoveAllMemories => 'Трајно отстрани сите мемории од Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Сите мемории се сега приватни';

  @override
  String get allMemoriesAreNowPublic => 'Сите мемории се сега јавни';

  @override
  String get clearOmisMemory => 'Обриши Omi меморија';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Дали си сигурен дека сакаш да ја обришеш Omi меморијата? Оваа акција не може да се отповика и ќе трајно избрише сите $count мемории.';
  }

  @override
  String get omisMemoryCleared => 'Omi меморијата за тебе е обришана';

  @override
  String get welcomeToOmi => 'Добредојде на Omi';

  @override
  String get continueWithApple => 'Продолжи со Apple';

  @override
  String get continueWithGoogle => 'Продолжи со Google';

  @override
  String get byContinuingYouAgree => 'Со продолжување, се согласувате со нашите ';

  @override
  String get termsOfService => 'Услови на коришћење';

  @override
  String get and => ' и ';

  @override
  String get dataAndPrivacy => 'Податоци и приватност';

  @override
  String get secureAuthViaAppleId => 'Безбедна аутентификација преку Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Безбедна аутентификација преку Google налог';

  @override
  String get whatWeCollect => 'Што собираме';

  @override
  String get dataCollectionMessage =>
      'Со продолжување, вашите разговори, записи и лични информации ќе бидат безбедно складирани на нашите серверни места за да обезбедиме AI-моќни увиди и да ги омозниме сите функции на апликацијата.';

  @override
  String get dataProtection => 'Заштита на податоци';

  @override
  String get yourDataIsProtected => 'Вашите податоци се заштитени и ги регулира нашата ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Молам, одберете го вашиот примарен јазик';

  @override
  String get chooseYourLanguage => 'Одберете го вашиот јазик';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Одберете го вашиот претпочитан јазик за најдобро Omi искуство';

  @override
  String get searchLanguages => 'Пребарувај јазици...';

  @override
  String get selectALanguage => 'Одберете јазик';

  @override
  String get tryDifferentSearchTerm => 'Пробајте со друг термин за пребарување';

  @override
  String get pleaseEnterYourName => 'Молам, внесете го вашето име';

  @override
  String get nameMustBeAtLeast2Characters => 'Името мора да има барем 2 знака';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Кажи ни како би сакал/сакала да бидеш титулиран/титулирана. Ово помага да го персонализираме твоето Omi искуство.';

  @override
  String charactersCount(int count) {
    return '$count знака';
  }

  @override
  String get enableFeaturesForBestExperience => 'Овозможи функции за најдобро Omi искуство на твоето уредување.';

  @override
  String get microphoneAccess => 'Приступ на микрофон';

  @override
  String get recordAudioConversations => 'Запиши аудио разговори';

  @override
  String get microphoneAccessDescription =>
      'Omi треба приступ на микрофон за да запише твои разговори и да обезбеди транскрипции.';

  @override
  String get screenRecording => 'Снимање на екран';

  @override
  String get captureSystemAudioFromMeetings => 'Прилози системски аудио од состаноци';

  @override
  String get screenRecordingDescription =>
      'Omi треба дозвола за снимање на екран за да прилози системски аудио од твои состаноци преку веб-прелистувач.';

  @override
  String get accessibility => 'Приступачност';

  @override
  String get detectBrowserBasedMeetings => 'Откри состаноци врз основа на прелистувач';

  @override
  String get accessibilityDescription =>
      'Omi треба дозвола за приступачност за да откри кога се приклучиш на Zoom, Meet или Teams состаноци во твоја веб-прелистувач.';

  @override
  String get pleaseWait => 'Молам, чекајте...';

  @override
  String get joinTheCommunity => 'Придружи се на заедницата!';

  @override
  String get loadingProfile => 'Се вчитува профилот...';

  @override
  String get profileSettings => 'Поставки на профилот';

  @override
  String get noEmailSet => 'Нема поставено е-пошта';

  @override
  String get userIdCopiedToClipboard => 'Корисничко ID копирано во клипбордот';

  @override
  String get yourInformation => 'Твоите информации';

  @override
  String get setYourName => 'Постави го твоето име';

  @override
  String get changeYourName => 'Промени го твоето име';

  @override
  String get voiceAndPeople => 'Глас и луѓе';

  @override
  String get teachOmiYourVoice => 'Научи го Omi твој глас';

  @override
  String get tellOmiWhoSaidIt => 'Кажи му на Omi кој го рече тоа 🗣️';

  @override
  String get payment => 'Плаќање';

  @override
  String get addOrChangeYourPaymentMethod => 'Додај или промени го твој начин на плаќање';

  @override
  String get preferences => 'Преференции';

  @override
  String get helpImproveOmiBySharing => 'Помогни да го подобриме Omi со делење анонимни податоци од аналитика';

  @override
  String get deleteAccount => 'Избриши налог';

  @override
  String get deleteYourAccountAndAllData => 'Избриши го твој налог и сите твои податоци';

  @override
  String get clearLogs => 'Избриши логи';

  @override
  String get debugLogsCleared => 'Дебаг логи избришани';

  @override
  String get exportConversations => 'Експортирај разговори';

  @override
  String get exportAllConversationsToJson => 'Експортирај ги сите твои разговори во JSON датотека.';

  @override
  String get conversationsExportStarted =>
      'Експортирање на разговори почнатокритично. Ово може да потрае неколку секунди, молам чекајте.';

  @override
  String get mcpDescription =>
      'За да поврзи Omi со други апликации за да читаш, пребарув и управуваш со твои спомени и разговори. Создај клуч за да почнеш.';

  @override
  String get apiKeys => 'API клучеви';

  @override
  String errorLabel(String error) {
    return 'Грешка: $error';
  }

  @override
  String get noApiKeysFound => 'Нема пронајдени API клучеви. Создај еден за да почнеш.';

  @override
  String get advancedSettings => 'Напредни поставки';

  @override
  String get triggersWhenNewConversationCreated => 'Се активира кога се создава нов разговор.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Се активира кога се прими нова транскрипција.';

  @override
  String get realtimeAudioBytes => 'Аудио бајтови во реално време';

  @override
  String get triggersWhenAudioBytesReceived => 'Се активира кога се примат аудио бајтови.';

  @override
  String get everyXSeconds => 'Секој х секунди';

  @override
  String get triggersWhenDaySummaryGenerated => 'Се активира кога се генерира резиме на денот.';

  @override
  String get tryLatestExperimentalFeatures => 'Пробај ги најновите експериментални функции од Omi Team.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Статус на дијагностика на услугата за транскрипција';

  @override
  String get enableDetailedDiagnosticMessages => 'Овозможи детални дијагностички пораки од услугата за транскрипција';

  @override
  String get autoCreateAndTagNewSpeakers => 'Автоматски создај и означи нови говорувачи';

  @override
  String get automaticallyCreateNewPerson => 'Автоматски создај нова личност кога се открие име во транскрипцијата.';

  @override
  String get pilotFeatures => 'Пилот функции';

  @override
  String get pilotFeaturesDescription => 'Овие функции се тестови и не е гарантирана поддршка.';

  @override
  String get suggestFollowUpQuestion => 'Предложи следно прашање';

  @override
  String get saveSettings => 'Зачувај поставки';

  @override
  String get syncingDeveloperSettings => 'Синхронизирање на поставки за развивач...';

  @override
  String get summary => 'Резиме';

  @override
  String get auto => 'Автоматско';

  @override
  String get noSummaryForApp =>
      'Нема достапно резиме за оваа апликација. Пробај друга апликација за подобри резултати.';

  @override
  String get tryAnotherApp => 'Пробај друга апликација';

  @override
  String generatedBy(String appName) {
    return 'Генерирано од $appName';
  }

  @override
  String get overview => 'Преглед';

  @override
  String get otherAppResults => 'Резултати од други апликации';

  @override
  String get unknownApp => 'Непозната апликација';

  @override
  String get noSummaryAvailable => 'Нема достапно резиме';

  @override
  String get conversationNoSummaryYet => 'Овој разговор сеуште нема резиме.';

  @override
  String get chooseSummarizationApp => 'Одберете апликација за резимирање';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName поставена како предвидена апликација за резимирање';
  }

  @override
  String get letOmiChooseAutomatically => 'Дозволи му на Omi да избере најдобра апликација автоматски';

  @override
  String get deleteConversationConfirmation =>
      'Дали си сигурен/сигурна дека сакаш да го избришеш овој разговор? Ова дејство не може да се врати.';

  @override
  String get conversationDeleted => 'Разговор избришан';

  @override
  String get generatingLink => 'Се генерира врска...';

  @override
  String get editConversation => 'Уредување разговор';

  @override
  String get conversationLinkCopiedToClipboard => 'Врската на разговорот копирана во клипбордот';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Транскрипцијата на разговорот копирана во клипбордот';

  @override
  String get editConversationDialogTitle => 'Уредување на разговор';

  @override
  String get changeTheConversationTitle => 'Промени го наслова на разговорот';

  @override
  String get conversationTitle => 'Наслов на разговорот';

  @override
  String get enterConversationTitle => 'Внеси наслов на разговорот...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Наслова на разговорот успешно ажуриран';

  @override
  String get failedToUpdateConversationTitle => 'Неуспешно ажурирање на наслова на разговорот';

  @override
  String get errorUpdatingConversationTitle => 'Грешка при ажурирање на наслова на разговорот';

  @override
  String get settingUp => 'Се поставува...';

  @override
  String get startYourFirstRecording => 'Почни со твоја прва снимка';

  @override
  String get preparingSystemAudioCapture => 'Подготовка на прилог на системски аудио';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Кликни го копчето за да прилович аудио за жив транскрипт, AI увиди и автоматско зачувување.';

  @override
  String get reconnecting => 'Повторно поврзување...';

  @override
  String get recordingPaused => 'Снимањето е паузирано';

  @override
  String get recordingActive => 'Снимањето е активно';

  @override
  String get startRecording => 'Почни со снимање';

  @override
  String resumingInCountdown(String countdown) {
    return 'Се враќа за ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Кликни play за да се врати';

  @override
  String get listeningForAudio => 'Слушање за аудио...';

  @override
  String get preparingAudioCapture => 'Подготовка на прилог на аудио';

  @override
  String get clickToBeginRecording => 'Кликни за да почнеш со снимање';

  @override
  String get translated => 'преведено';

  @override
  String get liveTranscript => 'Жив транскрипт';

  @override
  String segmentsSingular(String count) {
    return '$count сегмент';
  }

  @override
  String segmentsPlural(String count) {
    return '$count сегменти';
  }

  @override
  String get startRecordingToSeeTranscript => 'Почни со снимање за да видиш жив транскрипт';

  @override
  String get paused => 'Паузирано';

  @override
  String get initializing => 'Се инијализира...';

  @override
  String get recording => 'Снимање';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Микрофонот се променил. Се враќа за ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Кликни play за да се врати или stop за да завршиш';

  @override
  String get settingUpSystemAudioCapture => 'Поставување на прилог на системски аудио';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Приложување аудио и генерирање транскрипција';

  @override
  String get clickToBeginRecordingSystemAudio => 'Кликни за да почнеш со снимање на системски аудио';

  @override
  String get you => 'Ти';

  @override
  String speakerWithId(String speakerId) {
    return 'Говорувач $speakerId';
  }

  @override
  String get translatedByOmi => 'преведено од omi';

  @override
  String get backToConversations => 'Назад на разговори';

  @override
  String get systemAudio => 'Систем';

  @override
  String get mic => 'Мик';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Аудио улез поставен на $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Грешка при смена на аудио уредување: $error';
  }

  @override
  String get selectAudioInput => 'Одберете аудио улез';

  @override
  String get loadingDevices => 'Се вчитуваат уредива...';

  @override
  String get settingsHeader => 'ПОСТАВКИ';

  @override
  String get plansAndBilling => 'Планови и Наплата';

  @override
  String get calendarIntegration => 'Интеграција со календар';

  @override
  String get dailySummary => 'Дневно резиме';

  @override
  String get developer => 'Развивач';

  @override
  String get about => 'За';

  @override
  String get selectTime => 'Одберете време';

  @override
  String get accountGroup => 'Налог';

  @override
  String get signOutQuestion => 'Одјава?';

  @override
  String get signOutConfirmation => 'Дали си сигурен/сигурна дека сакаш да се одјавиш?';

  @override
  String get customVocabularyHeader => 'ПРИЛАГОДЕНО РЕЧЕСТВО';

  @override
  String get addWordsDescription => 'Додај зборови што Omi требаше да ги препознае во текот на транскрипција.';

  @override
  String get enterWordsHint => 'Внеси зборови (одделени со запирка)';

  @override
  String get dailySummaryHeader => 'ДНЕВНО РЕЗИМЕ';

  @override
  String get dailySummaryTitle => 'Дневно резиме';

  @override
  String get dailySummaryDescription =>
      'Добиј персонализирано резиме на твојот дневен разговор доставено како известување.';

  @override
  String get deliveryTime => 'Време на доставување';

  @override
  String get deliveryTimeDescription => 'Кога да приме твое дневно резиме';

  @override
  String get subscription => 'Претплата';

  @override
  String get viewPlansAndUsage => 'Преглед планови и користење';

  @override
  String get viewPlansDescription => 'Управувај со твојата претплата и види статистика на користење';

  @override
  String get addOrChangePaymentMethod => 'Додај или промени го твој начин на плаќање';

  @override
  String get displayOptions => 'Можности на приказ';

  @override
  String get showMeetingsInMenuBar => 'Прикажи состаноци во мени барот';

  @override
  String get displayUpcomingMeetingsDescription => 'Прикажи долни состаноци во мени барот';

  @override
  String get showEventsWithoutParticipants => 'Прикажи настани без учесници';

  @override
  String get includePersonalEventsDescription => 'Вклучи лични настани без присутни лица';

  @override
  String get upcomingMeetings => 'Долни состаноци';

  @override
  String get checkingNext7Days => 'Проверување на следните 7 дена';

  @override
  String get shortcuts => 'Кратенки';

  @override
  String get shortcutChangeInstruction => 'Кликни на кратенка за да је промениш. Притисни Escape за откажување.';

  @override
  String get configureSTTProvider => 'Конфигурирај STT добавувач';

  @override
  String get setConversationEndDescription => 'Постави кога разговорите автоматски завршува';

  @override
  String get importDataDescription => 'Увезување податоци од други извори';

  @override
  String get exportConversationsDescription => 'Експортирај разговори во JSON';

  @override
  String get exportingConversations => 'Експортирање разговори...';

  @override
  String get clearNodesDescription => 'Избриши сите јазлови и врски';

  @override
  String get deleteKnowledgeGraphQuestion => 'Избриши граф на знаење?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Ово ќе избрише сви изведени податоци на граф на знаење. Твоите оригинални спомени остануваат безбедни.';

  @override
  String get connectOmiWithAI => 'Поврзи Omi со AI асистенти';

  @override
  String get noAPIKeys => 'Нема API клучеви. Создај еден за да почнеш.';

  @override
  String get autoCreateWhenDetected => 'Автоматски создај кога се открие име';

  @override
  String get trackPersonalGoals => 'Праток лични цели на почетна страница';

  @override
  String get endpointURL => 'URL на крајна точка';

  @override
  String get links => 'Врски';

  @override
  String get discordMemberCount => '8000+ членови на Discord';

  @override
  String get userInformation => 'Информации на корисникот';

  @override
  String get capabilities => 'Способности';

  @override
  String get previewScreenshots => 'Преглед на снимки на екран';

  @override
  String get holdOnPreparingForm => 'Седи, ја подготвуваме формата за тебе';

  @override
  String get bySubmittingYouAgreeToOmi => 'Со поднесување, се согласувате со Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Услови и политика на приватност';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Помага да се дијагностицираат проблеми. Автоматски се избришува по 3 дена.';

  @override
  String get manageYourApp => 'Управувај со твоја апликација';

  @override
  String get updatingYourApp => 'Ажурирање твоја апликација';

  @override
  String get fetchingYourAppDetails => 'Преземање детали на твоја апликација';

  @override
  String get updateAppQuestion => 'Ажурирај апликација?';

  @override
  String get updateAppConfirmation =>
      'Дали си сигурен/сигурна дека сакаш да ја ажурираш твоја апликација? Промените ќе се рефлектираат кога ќе бидат одобрени од нашиот тим.';

  @override
  String get updateApp => 'Ажурирај апликација';

  @override
  String get createAndSubmitNewApp => 'Создај и поднеси нова апликација';

  @override
  String appsCount(String count) {
    return 'Апликации ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Приватни апликации ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Јавни апликации ($count)';
  }

  @override
  String get newVersionAvailable => 'Нова верзија достапна 🎉';

  @override
  String get no => 'Не';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Претплатата успешно отказана. Тоа ќе остане активно до крајот на текуцата година за наплата.';

  @override
  String get failedToCancelSubscription => 'Неуспешно откажување на претплатата. Молам, пробајте повторно.';

  @override
  String get invalidPaymentUrl => 'Невалидна URL на плаќање';

  @override
  String get permissionsAndTriggers => 'Дозволи и активирачи';

  @override
  String get chatFeatures => 'Функции на разговор';

  @override
  String get uninstall => 'Отинсталирај';

  @override
  String get installs => 'ИНСТАЛАЦИИ';

  @override
  String get priceLabel => 'ЦЕНА';

  @override
  String get updatedLabel => 'АЖУРИРАНО';

  @override
  String get createdLabel => 'СОЗДАДЕНО';

  @override
  String get featuredLabel => 'ИСТАКНАТО';

  @override
  String get cancelSubscriptionQuestion => 'Откажи претплата?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Дали си сигурен/сигурна дека сакаш да ја откажеш твоја претплата? Ќе имаш приступ до крајот на твојата теречна година за наплата.';

  @override
  String get cancelSubscriptionButton => 'Откажи претплата';

  @override
  String get cancelling => 'Откажување...';

  @override
  String get betaTesterMessage =>
      'Ти си бета тестер за оваа апликација. Таа сеуште не е јавна. Ќе биде јавна кога ќе биде одобрена.';

  @override
  String get appUnderReviewMessage =>
      'Твоја апликација е под преглед и видлива само за тебе. Ќе биде јавна кога ќе биде одобрена.';

  @override
  String get appRejectedMessage =>
      'Твоја апликација е отфрлена. Молам, ажурирај детали на апликацијата и повторно поднеси за преглед.';

  @override
  String get invalidIntegrationUrl => 'Невалидна URL на интеграција';

  @override
  String get tapToComplete => 'Кликни за да завршиш';

  @override
  String get invalidSetupInstructionsUrl => 'Невалидна URL на инструкции за поставување';

  @override
  String get pushToTalk => 'Притисни за да зборуваш';

  @override
  String get summaryPrompt => 'Промпт на резиме';

  @override
  String get pleaseSelectARating => 'Молам, одберете рејтинг';

  @override
  String get reviewAddedSuccessfully => 'Преглед успешно додаден 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Преглед успешно ажуриран 🚀';

  @override
  String get failedToSubmitReview => 'Неуспешно поднесување на преглед. Молам, пробајте повторно.';

  @override
  String get addYourReview => 'Додај твој преглед';

  @override
  String get editYourReview => 'Уредување твој преглед';

  @override
  String get writeAReviewOptional => 'Напиши преглед (опционално)';

  @override
  String get submitReview => 'Поднеси преглед';

  @override
  String get updateReview => 'Ажурирај преглед';

  @override
  String get yourReview => 'Твој преглед';

  @override
  String get anonymousUser => 'Анонимен корисник';

  @override
  String get issueActivatingApp => 'Имаше проблем при активирање на оваа апликација. Молам, пробајте повторно.';

  @override
  String get dataAccessNoticeDescription =>
      'Оваа апликација ќе пристапи твои податоци. Omi AI не е одговорна за тоа како твои податоци се користат, модифицираат или избришуваат од оваа апликација';

  @override
  String get copyUrl => 'Копирај URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Пон';

  @override
  String get weekdayTue => 'Вто';

  @override
  String get weekdayWed => 'Сре';

  @override
  String get weekdayThu => 'Чет';

  @override
  String get weekdayFri => 'Пет';

  @override
  String get weekdaySat => 'Сабота';

  @override
  String get weekdaySun => 'Недела';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Интеграција со $serviceName доаѓа наскоро';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Веќе експортирано на $platform';
  }

  @override
  String get anotherPlatform => 'друга платформа';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Молам, аутентификувај се со $serviceName во Поставки > Интеграции на задачи';
  }

  @override
  String addingToService(String serviceName) {
    return 'Додавање на $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Додадено на $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Неуспешно додавање на $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Дозвола одобрена за Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Неуспешно создавање на добавувач API клуч: $error';
  }

  @override
  String get createAKey => 'Создај клуч';

  @override
  String get apiKeyRevokedSuccessfully => 'API клуч успешно одозван';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Неуспешно одозивање на API клучот: $error';
  }

  @override
  String get omiApiKeys => 'Omi API клучеви';

  @override
  String get apiKeysDescription =>
      'API клучевите се користат за аутентификација кога твоја апликација комуницира со OMI серверот. Тие овозможуваат твоја апликација да создава спомени и безбедно пристапува други OMI услуги.';

  @override
  String get aboutOmiApiKeys => 'За Omi API клучеви';

  @override
  String get yourNewKey => 'Твој нов клуч:';

  @override
  String get copyToClipboard => 'Копирај во клипборд';

  @override
  String get pleaseCopyKeyNow => 'Молам, копирај го сега и го запиши некаде безбедно.';

  @override
  String get willNotSeeAgain => 'Нема да можеш да го видиш повторно.';

  @override
  String get revokeKey => 'Одозови клуч';

  @override
  String get revokeApiKeyQuestion => 'Одозови API клуч?';

  @override
  String get revokeApiKeyWarning =>
      'Ово дејство не може да се врати. Сите апликации што го користат овој клуч нема да можат да пристапат API.';

  @override
  String get revoke => 'Одозови';

  @override
  String get whatWouldYouLikeToCreate => 'Што би сакал/сакала да создадеш?';

  @override
  String get createAnApp => 'Создај апликација';

  @override
  String get createAndShareYourApp => 'Создај и дели твоја апликација';

  @override
  String get itemApp => 'Апликација';

  @override
  String keepItemPublic(String item) {
    return 'Держи $item јавна';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Направи $item јавна?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Направи $item приватна?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Ако направиш $item јавна, може да се користи од сите';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Ако направиш $item приватна сега, нема да функционира за сите и ќе биде видлива само за тебе';
  }

  @override
  String get manageApp => 'Управувај апликација';

  @override
  String deleteItemTitle(String item) {
    return 'Избриши $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Избриши $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Дали си сигурен/сигурна дека сакаш да го избришеш овој $item? Ово дејство не може да се врати.';
  }

  @override
  String get revokeKeyQuestion => 'Одозови клуч?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Дали си сигурен/сигурна дека сакаш да го одозовеш клучот \"$keyName\"? Ово дејство не може да се врати.';
  }

  @override
  String get createNewKey => 'Создај нов клуч';

  @override
  String get keyNameHint => 'пр. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Молам, внесете име.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Неуспешно создавање на клуч: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Неуспешно создавање на клуч. Молам, пробајте повторно.';

  @override
  String get keyCreated => 'Клуч создаден';

  @override
  String get keyCreatedMessage =>
      'Твој нов клуч е создаден. Молам, копирај го сега. Нема да можеш да го видиш повторно.';

  @override
  String get keyWord => 'Клуч';

  @override
  String get externalAppAccess => 'Приступ на надворешна апликација';

  @override
  String get externalAppAccessDescription =>
      'Следните инсталирани апликации имаат надворешни интеграции и можат да пристапат твои податоци, како што се разговори и спомени.';

  @override
  String get noExternalAppsHaveAccess => 'Нема надворешни апликации што имаат приступ твои податоци.';

  @override
  String get maximumSecurityE2ee => 'Максимална безбедност (E2EE)';

  @override
  String get e2eeDescription =>
      'Криптирање крај-до-крај е голдениот стандард за приватност. Кога е овозможено, твои податоци се криптирани на твоето уредување пред да се испрати на нашите серверски места. Тоа значи нема никој, дури и Omi, може да пристапи твој содржај.';

  @override
  String get importantTradeoffs => 'Важни трговски замени:';

  @override
  String get e2eeTradeoff1 => '• Некои функции како интеграции на надворешни апликации можеби ќе бидат оневозможени.';

  @override
  String get e2eeTradeoff2 => '• Ако го загубиш твоја лозинка, твои податоци не можат да бидат враќени.';

  @override
  String get featureComingSoon => 'Оваа функција доаѓа наскоро!';

  @override
  String get migrationInProgressMessage =>
      'Миграција во прогрес. Не можеш да го промениш нивото на заштита додека не завршиме.';

  @override
  String get migrationFailed => 'Миграција неуспешна';

  @override
  String migratingFromTo(String source, String target) {
    return 'Мигрирање од $source во $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total објекти';
  }

  @override
  String get secureEncryption => 'Безбедна криптирање';

  @override
  String get secureEncryptionDescription =>
      'Твои податоци се криптирани со клуч единствен за тебе на нашите серверски места, хостирани на Google Cloud. Тоа значи твој суров содржај е недостапен за никој, вклучително Omi персонал или Google, директно од базата на податоци.';

  @override
  String get endToEndEncryption => 'Криптирање крај-до-крај';

  @override
  String get e2eeCardDescription =>
      'Овозможи за максимална безбедност каде само ти можеш пристапи твои податоци. Кликни за да научиш повеќе.';

  @override
  String get dataAlwaysEncrypted =>
      'Независно од нивото, твои податоци се секогаш криптирани на мирување и во транзит.';

  @override
  String get readOnlyScope => 'Само читање';

  @override
  String get fullAccessScope => 'Целосен приступ';

  @override
  String get readScope => 'Читање';

  @override
  String get writeScope => 'Пишување';

  @override
  String get apiKeyCreated => 'API клуч создаден!';

  @override
  String get saveKeyWarning => 'Зачувај го овој клуч сега! Нема да можеш да го видиш повторно.';

  @override
  String get yourApiKey => 'ТВОЈ API КЛУЧ';

  @override
  String get tapToCopy => 'Кликни за копирање';

  @override
  String get copyKey => 'Копирај клуч';

  @override
  String get createApiKey => 'Создај API клуч';

  @override
  String get accessDataProgrammatically => 'Пристапи твои податоци програматски';

  @override
  String get keyNameLabel => 'ИМЕ НА КЛУЧ';

  @override
  String get keyNamePlaceholder => 'пр. Моја интеграција на апликација';

  @override
  String get permissionsLabel => 'ДОЗВОЛИ';

  @override
  String get permissionsInfoNote => 'R = Читање, W = Пишување. Подразбирана е само за читање ако ничего не е одберено.';

  @override
  String get developerApi => 'API за развивачи';

  @override
  String get createAKeyToGetStarted => 'Создај клуч за да почнеш';

  @override
  String errorWithMessage(String error) {
    return 'Грешка: $error';
  }

  @override
  String get omiTraining => 'Omi обука';

  @override
  String get trainingDataProgram => 'Програма за обучни податоци';

  @override
  String get getOmiUnlimitedFree =>
      'Добиј Omi неограничено бесплатно со допринесување твои податоци за обука на AI модели.';

  @override
  String get trainingDataBullets =>
      '• Твои податоци помагаат да го подобриме AI модели\n• Само неосетливи податоци се делат\n• Целосно транспарентен процес';

  @override
  String get learnMoreAtOmiTraining => 'Научи повеќе на omi.me/training';

  @override
  String get agreeToContributeData => 'Го разбирам и се согласувам да ги допринесам твои податоци за AI обука';

  @override
  String get submitRequest => 'Поднеси барање';

  @override
  String get thankYouRequestUnderReview =>
      'Благодарам! Твое барање е под преглед. Ќе те известиме кога ќе биде одобрено.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Твој план ќе остане активен до $date. По тоа, ќе ја загубиш приступ твоите неограничени функции. Дали си сигурен/сигурна?';
  }

  @override
  String get confirmCancellation => 'Потврди откажување';

  @override
  String get keepMyPlan => 'Držи мој план';

  @override
  String get subscriptionSetToCancel => 'Твоја претплата е постављена да се откаже на крајот на периодот.';

  @override
  String get switchedToOnDevice => 'Потврдена врата на уредување транскрипција';

  @override
  String get couldNotSwitchToFreePlan => 'Не можеше да се префрли на бесплатниот план. Обидете се повторно.';

  @override
  String get couldNotLoadPlans => 'Не можеше да се вчитаат достапните планови. Обидете се повторно.';

  @override
  String get selectedPlanNotAvailable => 'Избраниот план не е достапен. Обидете се повторно.';

  @override
  String get upgradeToAnnualPlan => 'Надградба на годишен план';

  @override
  String get importantBillingInfo => 'Важни информации за наплатување:';

  @override
  String get monthlyPlanContinues => 'Вашиот тековен месечен план ќе продолжи до крајот на периодот на наплатување';

  @override
  String get paymentMethodCharged =>
      'Вашиот постоечки начин на плаќање ќе биде наплатен автоматски кога ќе заврши месечниот план';

  @override
  String get annualSubscriptionStarts => 'Вашата 12-месечна годишна претплата ќе почне автоматски по наплатата';

  @override
  String get thirteenMonthsCoverage => 'Ќе добиете вкупно 13 месеци покриеност (тековен месец + 12 месеци годишно)';

  @override
  String get confirmUpgrade => 'Потврди надградба';

  @override
  String get confirmPlanChange => 'Потврди промена на план';

  @override
  String get confirmAndProceed => 'Потврди и продолжи';

  @override
  String get upgradeScheduled => 'Надградба закажана';

  @override
  String get changePlan => 'Промени план';

  @override
  String get upgradeAlreadyScheduled => 'Вашата надградба на годишниот план е веќе закажана';

  @override
  String get youAreOnUnlimitedPlan => 'Сте на Неограничениот план.';

  @override
  String get yourOmiUnleashed => 'Вашиот Omi, ослободен. Одете неограничено за бесконечни можности.';

  @override
  String planEndedOn(String date) {
    return 'Вашиот план заврши на $date.\\nПретплатете се сега - ќе бидете наплатени веднаш за нов период на наплатување.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Вашиот план е поставен да се откаже на $date.\\nПретплатете се сега за да ги задржите вашите бенефиции - без наплата до $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Вашиот годишен план ќе почне автоматски кога ќе заврши месечниот план.';

  @override
  String planRenewsOn(String date) {
    return 'Вашиот план се обновува на $date.';
  }

  @override
  String get unlimitedConversations => 'Неограничени разговори';

  @override
  String get askOmiAnything => 'Праши Omi било што за вашиот живот';

  @override
  String get unlockOmiInfiniteMemory => 'Отклучи неограничена меморија на Omi';

  @override
  String get youreOnAnnualPlan => 'Сте на годишниот план';

  @override
  String get alreadyBestValuePlan => 'Веќе имате план со најдобра вредност. Не се потребни промени.';

  @override
  String get unableToLoadPlans => 'Не можат да се вчитаат плановите';

  @override
  String get checkConnectionTryAgain => 'Проверете ја врската и обидете се повторно';

  @override
  String get useFreePlan => 'Користи бесплатен план';

  @override
  String get continueText => 'Продолжи';

  @override
  String get resubscribe => 'Претплати се повторно';

  @override
  String get couldNotOpenPaymentSettings => 'Не можеше да се отворат поставките за плаќање. Обидете се повторно.';

  @override
  String get managePaymentMethod => 'Управувај со начин на плаќање';

  @override
  String get cancelSubscription => 'Откажи претплата';

  @override
  String endsOnDate(String date) {
    return 'Завршува на $date';
  }

  @override
  String get active => 'Активно';

  @override
  String get freePlan => 'Бесплатен план';

  @override
  String get configure => 'Конфигурирај';

  @override
  String get privacyInformation => 'Информации за приватност';

  @override
  String get yourPrivacyMattersToUs => 'Вашата приватност е важна за нас';

  @override
  String get privacyIntroText =>
      'Во Omi, го земаме вашата приватност многу сериозно. Сакаме да бидеме транспарентни за податоците што ги собираме и како ги користиме за да го подобриме нашиот производ за вас. Ево што треба да знаете:';

  @override
  String get whatWeTrack => 'Што го следиме';

  @override
  String get anonymityAndPrivacy => 'Анонимност и приватност';

  @override
  String get optInAndOptOutOptions => 'Опции за избор и отфрлање';

  @override
  String get ourCommitment => 'Нашето обврзување';

  @override
  String get commitmentText =>
      'Посветени сме да ги користиме соберените податоци само за да го направиме Omi подобар производ за вас. Вашата приватност и доверба се од највисокo значење за нас.';

  @override
  String get thankYouText =>
      'Благодариме што сте вреден корисник на Omi. Ако имате прашања или забрзи, слободно нас контактирајте на team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Поставки за WiFi синхронизација';

  @override
  String get enterHotspotCredentials => 'Внесете ги врите за личната точка на вашиот телефон';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi синхронизација ја користи вашата телефон како личната точка. Најдете го називот на вашата личната точка и лозинката во Поставки > Лична точка.';

  @override
  String get hotspotNameSsid => 'Назив на личната точка (SSID)';

  @override
  String get exampleIphoneHotspot => 'нпр. iPhone личната точка';

  @override
  String get password => 'Лозинка';

  @override
  String get enterHotspotPassword => 'Внесете лозинка за личната точка';

  @override
  String get saveCredentials => 'Зачувај врите';

  @override
  String get clearCredentials => 'Избриши врите';

  @override
  String get pleaseEnterHotspotName => 'Внесете назив на личната точка';

  @override
  String get wifiCredentialsSaved => 'WiFi врите зачувани';

  @override
  String get wifiCredentialsCleared => 'WiFi врите избришани';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Резиме генерирано за $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Не успеа да се генерира резиме. Проверете дали имате разговори за тој ден.';

  @override
  String get summaryNotFound => 'Резиме не е пронајдено';

  @override
  String get yourDaysJourney => 'Патување на вашиот ден';

  @override
  String get highlights => 'Главни пункти';

  @override
  String get unresolvedQuestions => 'Нерешени прашања';

  @override
  String get decisions => 'Одлуки';

  @override
  String get learnings => 'Учења';

  @override
  String get autoDeletesAfterThreeDays => 'Автоматски брише по 3 дни.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Графикот на знаење беше успешно избришан';

  @override
  String get exportStartedMayTakeFewSeconds => 'Извозот почна. Ова може да потрае неколку секунди...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Ова ќе го избрише целиот извлечен графички податок на знаење (чворови и врски). Вашите оригинални мемории ќе остану безбедни. Графикот ќе се преправи со текот на времето или по следната барање.';

  @override
  String get configureDailySummaryDigest => 'Конфигурирајте го вашиот дневен резиме на список на работи';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Пристапува $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'активирано од $triggerType';
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
  String get noSpecificDataAccessConfigured => 'Нема конфигуриран специфичен пристап до податоци.';

  @override
  String get basicPlanDescription => '1.200 премиум минути + неограничено на уред';

  @override
  String get minutes => 'минути';

  @override
  String get omiHas => 'Omi има:';

  @override
  String get premiumMinutesUsed => 'Премиум минути потрошени.';

  @override
  String get setupOnDevice => 'Конфигурирај на уред';

  @override
  String get forUnlimitedFreeTranscription => 'за неограничена бесплатна транскрипција.';

  @override
  String premiumMinsLeft(int count) {
    return '$count премиум минути останати.';
  }

  @override
  String get alwaysAvailable => 'секогаш достапни.';

  @override
  String get importHistory => 'Историја на увоз';

  @override
  String get noImportsYet => 'Нема увозни извештаи';

  @override
  String get selectZipFileToImport => 'Избери .zip датотека за увоз!';

  @override
  String get otherDevicesComingSoon => 'Други уреди ќе дојдат наскоро';

  @override
  String get deleteAllLimitlessConversations => 'Избриши ги сите разговори од Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Ова ќе го трајно избрише сите разговори увезени од Limitless. Оваа акција не може да се отмене.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Избришани $count разговори од Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Не успеа да се избришат разговори';

  @override
  String get deleteImportedData => 'Избриши увезени податоци';

  @override
  String get statusPending => 'На чекање';

  @override
  String get statusProcessing => 'Се обработува';

  @override
  String get statusCompleted => 'Завршено';

  @override
  String get statusFailed => 'Неуспешно';

  @override
  String nConversations(int count) {
    return '$count разговори';
  }

  @override
  String get pleaseEnterName => 'Внесете назив';

  @override
  String get nameMustBeBetweenCharacters => 'Називот мора да содржи од 2 до 40 карактери';

  @override
  String get deleteSampleQuestion => 'Избриши примерок?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Дали сигурно сакате да го избришите примерокот на $name?';
  }

  @override
  String get confirmDeletion => 'Потврди бришење';

  @override
  String deletePersonConfirmation(String name) {
    return 'Дали сигурно сакате да го избришите $name? Ова исто така ќе ги отстрани сите поврзани примероци на говор.';
  }

  @override
  String get howItWorksTitle => 'Како функционира?';

  @override
  String get howPeopleWorks =>
      'Откако лицето ќе се создаде, можете да одите на разговор транскрипт и да им доделите одговарачки сегменти, на тој начин Omi ќе биде способен да го препознае и нивниот говор!';

  @override
  String get tapToDelete => 'Отвори за да избришеш';

  @override
  String get newTag => 'НОВО';

  @override
  String get needHelpChatWithUs => 'Потребна помош? Разговарај со нас';

  @override
  String get localStorageEnabled => 'Локално складирање активирано';

  @override
  String get localStorageDisabled => 'Локално складирање деактивирано';

  @override
  String failedToUpdateSettings(String error) {
    return 'Не успеа да се ажурираат поставките: $error';
  }

  @override
  String get privacyNotice => 'Обвест за приватност';

  @override
  String get recordingsMayCaptureOthers =>
      'Снимките може да ја прифатат гласовите на други. Осигурајте се дека имате согласност од сите учесници пред да активирате.';

  @override
  String get enable => 'Активирај';

  @override
  String get storeAudioOnPhone => 'Складирај аудио на телефонот';

  @override
  String get on => 'Вклучено';

  @override
  String get storeAudioDescription =>
      'Задржи ги сите аудио снимки складирани локално на твој телефон. Кога е деактивирано, само неуспешните преноси се задржуваат за да заштедиш простор за складирање.';

  @override
  String get enableLocalStorage => 'Активирај локално складирање';

  @override
  String get cloudStorageEnabled => 'Облачно складирање активирано';

  @override
  String get cloudStorageDisabled => 'Облачно складирање деактивирано';

  @override
  String get enableCloudStorage => 'Активирај облачно складирање';

  @override
  String get storeAudioOnCloud => 'Складирај аудио на облак';

  @override
  String get cloudStorageDialogMessage =>
      'Вашите снимки во реално време ќе бидат складирани во приватно облачно складирање додека говорите.';

  @override
  String get storeAudioCloudDescription =>
      'Складирајте ги вашите снимки во реално време во приватно облачно складирање додека говорите. Аудиото се прифаќа и зачувува безбедно во реално време.';

  @override
  String get downloadingFirmware => 'Преземање на фирмвер';

  @override
  String get installingFirmware => 'Инсталирање на фирмвер';

  @override
  String get firmwareUpdateWarning =>
      'Не затворајте ја апликацијата или исклучувајте го уредот. Ова може да го оштети вашиот уред.';

  @override
  String get firmwareUpdated => 'Фирмверот е ажуриран';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Рестартирајте го вашиот $deviceName за да ја завршите ажурирањето.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Вашиот уред е ажуриран';

  @override
  String get currentVersion => 'Тековна верзија';

  @override
  String get latestVersion => 'Најнова верзија';

  @override
  String get whatsNew => 'Што е ново';

  @override
  String get installUpdate => 'Инсталирај ажурирање';

  @override
  String get updateNow => 'Ажурирај сега';

  @override
  String get updateGuide => 'Водич за ажурирање';

  @override
  String get checkingForUpdates => 'Проверување за ажурирања';

  @override
  String get checkingFirmwareVersion => 'Проверување верзија на фирмверот...';

  @override
  String get firmwareUpdate => 'Ажурирање на фирмверот';

  @override
  String get payments => 'Плаќања';

  @override
  String get connectPaymentMethodInfo =>
      'Поврзи начин на плаќање подолу за да почнеш да добиваш исплати за твоите апликации.';

  @override
  String get selectedPaymentMethod => 'Избран начин на плаќање';

  @override
  String get availablePaymentMethods => 'Достапни начини на плаќање';

  @override
  String get activeStatus => 'Активно';

  @override
  String get connectedStatus => 'Поврзано';

  @override
  String get notConnectedStatus => 'Не е поврзано';

  @override
  String get setActive => 'Постави како активно';

  @override
  String get getPaidThroughStripe => 'Добивајте плаќање за продажба на апликациите преку Stripe';

  @override
  String get monthlyPayouts => 'Месечни исплати';

  @override
  String get monthlyPayoutsDescription =>
      'Добивајте месечни плаќања директно на вашата сметка кога ќе достигнете \$10 зараб';

  @override
  String get secureAndReliable => 'Безбедно и поуздано';

  @override
  String get stripeSecureDescription =>
      'Stripe осигурува безбедни и навремени трансфери на вашите приходи од апликацијата';

  @override
  String get selectYourCountry => 'Избери ја твоја земја';

  @override
  String get countrySelectionPermanent => 'Вашиот избор на земја е трајан и не може да се промени подоцна.';

  @override
  String get byClickingConnectNow => 'Со клик на \"Поврзи се сега\" согласувате со';

  @override
  String get stripeConnectedAccountAgreement => 'Договор за поврзана сметка на Stripe';

  @override
  String get errorConnectingToStripe => 'Грешка при поврзување на Stripe! Обидете се повторно подоцна.';

  @override
  String get connectingYourStripeAccount => 'Поврзување на вашата Stripe сметка';

  @override
  String get stripeOnboardingInstructions =>
      'Ве молиме завршете го процесот на Stripe онбординг во вашиот прелистувач. Оваа страница ќе се ажурира автоматски откако ќе завршите.';

  @override
  String get failedTryAgain => 'Неуспешно? Обидете се повторно';

  @override
  String get illDoItLater => 'Ќе го направам подоцна';

  @override
  String get successfullyConnected => 'Успешно поврзан!';

  @override
  String get stripeReadyForPayments =>
      'Вашата Stripe сметка е сега подготвена да прима плаќања. Можете да почнете да заработувате од продажба на вашата апликација веднаш.';

  @override
  String get updateStripeDetails => 'Ажурирај детали на Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Грешка при ажурирање на детали на Stripe! Обидете се повторно подоцна.';

  @override
  String get updatePayPal => 'Ажурирај PayPal';

  @override
  String get setUpPayPal => 'Конфигурирај PayPal';

  @override
  String get updatePayPalAccountDetails => 'Ажурирајте ги детали на вашата PayPal сметка';

  @override
  String get connectPayPalToReceivePayments =>
      'Поврзете ја вашата PayPal сметка за да почнете да примате плаќања за вашите апликации';

  @override
  String get paypalEmail => 'PayPal е-пошта';

  @override
  String get paypalMeLink => 'PayPal.me врска';

  @override
  String get stripeRecommendation =>
      'Ако Stripe е достапен во вашата земја, ја препорачуваме да ја користите за побрзи и полесни исплати.';

  @override
  String get updatePayPalDetails => 'Ажурирај детали на PayPal';

  @override
  String get savePayPalDetails => 'Зачувај детали на PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Внесете ја вашата PayPal е-пошта';

  @override
  String get pleaseEnterPayPalMeLink => 'Внесете ја вашата PayPal.me врска';

  @override
  String get doNotIncludeHttpInLink => 'Не вклучувајте http или https или www во врската';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Внесете валидна PayPal.me врска';

  @override
  String get pleaseEnterValidEmail => 'Внесете валидна адреса на е-пошта';

  @override
  String get syncingYourRecordings => 'Синхронизирање на вашите снимки';

  @override
  String get syncYourRecordings => 'Синхронизирај ги вашите снимки';

  @override
  String get syncNow => 'Синхронизирај сега';

  @override
  String get error => 'Грешка';

  @override
  String get speechSamples => 'Примероци на говор';

  @override
  String additionalSampleIndex(String index) {
    return 'Дополнителен примерок $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Траење: $seconds секунди';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Дополнителен примерок на говор отстранет';

  @override
  String get consentDataMessage =>
      'Со продолжување, вашите разговори, снимки и лични информации ќе бидат безбедно зачувани на нашите сервери. Вашите аудио снимки и транскрипти се обработуваат од AI услуги на трети страни (вклучувајќи Deepgram за транскрипција и OpenAI за анализа) за да ви обезбедат увиди базирани на AI и да ги овозможат сите функции на апликацијата.';

  @override
  String get tasksEmptyStateMessage =>
      'Задачите од вашите разговори ќе се појават овде.\\nОтвори + за да создадеш една ручно.';

  @override
  String get clearChatAction => 'Очисти разговор';

  @override
  String get enableApps => 'Активирај апликации';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'покажи повеќе ↓';

  @override
  String get showLess => 'покажи помалку ↑';

  @override
  String get loadingYourRecording => 'Вчитување на вашата снимка...';

  @override
  String get photoDiscardedMessage => 'Оваа фотографија беше отфрлена бидејќи не беше значајна.';

  @override
  String get analyzing => 'Анализирање...';

  @override
  String get searchCountries => 'Пребарај земји';

  @override
  String get checkingAppleWatch => 'Проверување на Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Инсталирај Omi на вашиот\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'За да го користите вашиот Apple Watch со Omi, прво мораш да ја инсталираш апликацијата Omi на твој часовник.';

  @override
  String get openOmiOnAppleWatch => 'Отвори Omi на вашиот\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Апликацијата Omi е инсталирана на вашиот Apple Watch. Отвори ја и отвори го Start за да почнеш.';

  @override
  String get openWatchApp => 'Отвори апликацијата на часовникот';

  @override
  String get iveInstalledAndOpenedTheApp => 'Ја инсталирав и отворив апликацијата';

  @override
  String get unableToOpenWatchApp =>
      'Не можеше да се отвори апликацијата на Apple Watch. Ве молиме ручно отворете ја апликацијата на часовникот на вашиот Apple Watch и инсталирајте Omi од секцијата \"Достапни апликации\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch успешно поврзан!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch сè уште не е достапен. Ве молиме проверете дали апликацијата Omi е отворена на вашиот часовник.';

  @override
  String errorCheckingConnection(String error) {
    return 'Грешка при проверување на врска: $error';
  }

  @override
  String get muted => 'Ставена на молчење';

  @override
  String get processNow => 'Обработи сега';

  @override
  String get finishedConversation => 'Завршена разговор?';

  @override
  String get stopRecordingConfirmation =>
      'Дали сигурно сакате да престанете да снимате и да го резимирате разговорот сега?';

  @override
  String get conversationEndsManually => 'Разговорот ќе завршип само ручно.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Разговорот се резимира по $minutes минута$suffix без говор.';
  }

  @override
  String get dontAskAgain => 'Не прашувај ме повторно';

  @override
  String get waitingForTranscriptOrPhotos => 'Чека се транскрипт или фотографии...';

  @override
  String get noSummaryYet => 'Нема резиме сè уште';

  @override
  String hints(String text) {
    return 'Совети: $text';
  }

  @override
  String get testConversationPrompt => 'Тестирај разговор упатство';

  @override
  String get prompt => 'Упатство';

  @override
  String get result => 'Резултат:';

  @override
  String get compareTranscripts => 'Спореди транскрипти';

  @override
  String get notHelpful => 'Не е корисно';

  @override
  String get exportTasksWithOneTap => 'Извези задачи со еден клик!';

  @override
  String get inProgress => 'Во напредок';

  @override
  String get photos => 'Фотографии';

  @override
  String get rawData => 'Сурови податоци';

  @override
  String get content => 'Содржина';

  @override
  String get noContentToDisplay => 'Нема содржина за приказ';

  @override
  String get noSummary => 'Нема резиме';

  @override
  String get updateOmiFirmware => 'Ажурирај omi фирмвер';

  @override
  String get anErrorOccurredTryAgain => 'Се појави грешка. Обидете се повторно.';

  @override
  String get welcomeBackSimple => 'Добредојде повторно';

  @override
  String get addVocabularyDescription => 'Додајте зборови што Omi треба да ги препознае за време на транскрипција.';

  @override
  String get enterWordsCommaSeparated => 'Внесете зборови (одделени со запирка)';

  @override
  String get whenToReceiveDailySummary => 'Кога да прима дневно резиме';

  @override
  String get checkingNextSevenDays => 'Проверување на следниот 7 дни';

  @override
  String failedToDeleteError(String error) {
    return 'Не успеа да се избрише: $error';
  }

  @override
  String get developerApiKeys => 'API клучеви за разработувачи';

  @override
  String get noApiKeysCreateOne => 'Нема API клучеви. Создајте еден за да почнете.';

  @override
  String get commandRequired => '⌘ потребна';

  @override
  String get spaceKey => 'Место';

  @override
  String loadMoreRemaining(String count) {
    return 'Вчитај повеќе ($count останати)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Топ $percentile% корисник';
  }

  @override
  String get wrappedMinutes => 'минути';

  @override
  String get wrappedConversations => 'разговори';

  @override
  String get wrappedDaysActive => 'денови активни';

  @override
  String get wrappedYouTalkedAbout => 'Разговараше за';

  @override
  String get wrappedActionItems => 'Работи за делување';

  @override
  String get wrappedTasksCreated => 'задачи создадени';

  @override
  String get wrappedCompleted => 'завршени';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% стопка на завршување';
  }

  @override
  String get wrappedYourTopDays => 'Твои топ денови';

  @override
  String get wrappedBestMoments => 'Најдобри моменти';

  @override
  String get wrappedMyBuddies => 'Мои другари';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Не можеше да престане да разговара за';

  @override
  String get wrappedShow => 'ШОУ';

  @override
  String get wrappedMovie => 'ФИЛМ';

  @override
  String get wrappedBook => 'КНИГА';

  @override
  String get wrappedCelebrity => 'ЗНАМЕНИТОСТ';

  @override
  String get wrappedFood => 'ЈАДЕЊЕ';

  @override
  String get wrappedMovieRecs => 'Препораки на филм за пријатели';

  @override
  String get wrappedBiggest => 'Најголема';

  @override
  String get wrappedStruggle => 'Борба';

  @override
  String get wrappedButYouPushedThrough => 'Но си го притиснал низ 💪';

  @override
  String get wrappedWin => 'Победа';

  @override
  String get wrappedYouDidIt => 'Си го направил! 🎉';

  @override
  String get wrappedTopPhrases => 'Топ 5 фрази';

  @override
  String get wrappedMins => 'мин';

  @override
  String get wrappedConvos => 'разговори';

  @override
  String get wrappedDays => 'денови';

  @override
  String get wrappedMyBuddiesLabel => 'МЕНИ ДРУГАРИ';

  @override
  String get wrappedObsessionsLabel => 'ОПСЕСИИ';

  @override
  String get wrappedStruggleLabel => 'БОРБА';

  @override
  String get wrappedWinLabel => 'ПОБЕДА';

  @override
  String get wrappedTopPhrasesLabel => 'ТОП ФРАЗИ';

  @override
  String get wrappedLetsHitRewind => 'Да ударимо назад на твоја';

  @override
  String get wrappedGenerateMyWrapped => 'Генерирај мој резиме';

  @override
  String get wrappedProcessingDefault => 'Обработка...';

  @override
  String get wrappedCreatingYourStory => 'Создавање на твоја\n2025 приказна...';

  @override
  String get wrappedSomethingWentWrong => 'Нешто\nпоморисе';

  @override
  String get wrappedAnErrorOccurred => 'Се случи грешка';

  @override
  String get wrappedTryAgain => 'Обидете се повторно';

  @override
  String get wrappedNoDataAvailable => 'Нема достапни податоци';

  @override
  String get wrappedOmiLifeRecap => 'Omi животен преглед';

  @override
  String get wrappedSwipeUpToBegin => 'Повлечи нагоре за да почнеш';

  @override
  String get wrappedShareText => 'Мој 2025, запомнет од Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Не успеа да се дели. Обидете се повторно.';

  @override
  String get wrappedFailedToStartGeneration => 'Не успеа да се почне генерирање. Обидете се повторно.';

  @override
  String get wrappedStarting => 'Почнување...';

  @override
  String get wrappedShare => 'Дели';

  @override
  String get wrappedShareYourWrapped => 'Делење на твој резиме';

  @override
  String get wrappedMy2025 => 'Мој 2025';

  @override
  String get wrappedRememberedByOmi => 'запомнет од Omi';

  @override
  String get wrappedMostFunDay => 'Најсмешно';

  @override
  String get wrappedMostProductiveDay => 'Најпродуктивно';

  @override
  String get wrappedMostIntenseDay => 'Најинтензивно';

  @override
  String get wrappedFunniestMoment => 'Најсмешен';

  @override
  String get wrappedMostCringeMoment => 'Најзамачко';

  @override
  String get wrappedMinutesLabel => 'минути';

  @override
  String get wrappedConversationsLabel => 'разговори';

  @override
  String get wrappedDaysActiveLabel => 'денови активни';

  @override
  String get wrappedTasksGenerated => 'задачи генерирани';

  @override
  String get wrappedTasksCompleted => 'задачи завршени';

  @override
  String get wrappedTopFivePhrases => 'Топ 5 фрази';

  @override
  String get wrappedAGreatDay => 'Одличен ден';

  @override
  String get wrappedGettingItDone => 'Го направив';

  @override
  String get wrappedAChallenge => 'Предизвик';

  @override
  String get wrappedAHilariousMoment => 'Хиларичен момент';

  @override
  String get wrappedThatAwkwardMoment => 'Таа чудна момент';

  @override
  String get wrappedYouHadFunnyMoments => 'Имаше некои смешни моменти оваа година!';

  @override
  String get wrappedWeveAllBeenThere => 'Сите сме таму биле!';

  @override
  String get wrappedFriend => 'Пријател';

  @override
  String get wrappedYourBuddy => 'Твој другар!';

  @override
  String get wrappedNotMentioned => 'Не е споменато';

  @override
  String get wrappedTheHardPart => 'Тешкиот дел';

  @override
  String get wrappedPersonalGrowth => 'Личен раст';

  @override
  String get wrappedFunDay => 'Смешно';

  @override
  String get wrappedProductiveDay => 'Продуктивно';

  @override
  String get wrappedIntenseDay => 'Интензивно';

  @override
  String get wrappedFunnyMomentTitle => 'Смешен момент';

  @override
  String get wrappedCringeMomentTitle => 'Замачок момент';

  @override
  String get wrappedYouTalkedAboutBadge => 'Разговараше за';

  @override
  String get wrappedCompletedLabel => 'Завршено';

  @override
  String get wrappedMyBuddiesCard => 'Мои другари';

  @override
  String get wrappedBuddiesLabel => 'ДРУГАРИ';

  @override
  String get wrappedObsessionsLabelUpper => 'ОПСЕСИИ';

  @override
  String get wrappedStruggleLabelUpper => 'БОРБА';

  @override
  String get wrappedWinLabelUpper => 'ПОБЕДА';

  @override
  String get wrappedTopPhrasesLabelUpper => 'ТОП ФРАЗИ';

  @override
  String get wrappedYourHeader => 'Твој';

  @override
  String get wrappedTopDaysHeader => 'Топ денови';

  @override
  String get wrappedYourTopDaysBadge => 'Твои топ денови';

  @override
  String get wrappedBestHeader => 'Најдобр';

  @override
  String get wrappedMomentsHeader => 'Моменти';

  @override
  String get wrappedBestMomentsBadge => 'Најдобри моменти';

  @override
  String get wrappedBiggestHeader => 'Најголем';

  @override
  String get wrappedStruggleHeader => 'Борба';

  @override
  String get wrappedWinHeader => 'Победа';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Но си го притиснал низ 💪';

  @override
  String get wrappedYouDidItEmoji => 'Си го направил! 🎉';

  @override
  String get wrappedHours => 'часови';

  @override
  String get wrappedActions => 'активности';

  @override
  String get multipleSpeakersDetected => 'Обнаружени повеќе говорници';

  @override
  String get multipleSpeakersDescription =>
      'Изгледа дека има повеќе говорници во снимката. Ве молиме проверете дали сте на тихо место и обидете се повторно.';

  @override
  String get invalidRecordingDetected => 'Обнаружена невалидна снимка';

  @override
  String get notEnoughSpeechDescription =>
      'Нема доволно говор обнаружен. Ве молиме говорете повеќе и обидете се повторно.';

  @override
  String get speechDurationDescription => 'Моля, обезбедете да зборувате најмалку 5 секунди и не повеќе од 90.';

  @override
  String get connectionLostDescription =>
      'Врската беше прекината. Моля, проверете ја вашата интернет врска и обидете се повторно.';

  @override
  String get howToTakeGoodSample => 'Како да земе добар примерок?';

  @override
  String get goodSampleInstructions =>
      '1. Обезбедете дека сте на тихо место.\n2. Зборувајте јасно и природно.\n3. Обезбедете дека вашиот уред е во неговата природна позиција, на вашата врат.\n\nКога ќе биде создадено, можете да го подобрите или да го направите повторно.';

  @override
  String get noDeviceConnectedUseMic => 'Нема поврзан уред. Ќе се користи микрофон на телефон.';

  @override
  String get doItAgain => 'Направи го повторно';

  @override
  String get listenToSpeechProfile => 'Слушај го мој профил за говор ➡️';

  @override
  String get recognizingOthers => 'Препознавање на други 👀';

  @override
  String get keepGoingGreat => 'Продолжи, се снаходиш одлично';

  @override
  String get somethingWentWrongTryAgain => 'Нешто се случи погрешно! Моля, обидете се повторно подоцна.';

  @override
  String get uploadingVoiceProfile => 'Се подига вашиот профил на глас....';

  @override
  String get memorizingYourVoice => 'Се памти твојот глас...';

  @override
  String get personalizingExperience => 'Персонализирање на вашето искуство...';

  @override
  String get keepSpeakingUntil100 => 'Продолжи да зборуваш додека не добиеш 100%.';

  @override
  String get greatJobAlmostThere => 'Добра работа, речиси си на крај';

  @override
  String get soCloseJustLittleMore => 'Толку блиску, само малку повеќе';

  @override
  String get notificationFrequency => 'Честина на известувања';

  @override
  String get controlNotificationFrequency => 'Контролирајте колку често Omi ви испраќа проактивни известувања.';

  @override
  String get yourScore => 'Твој резултат';

  @override
  String get dailyScoreBreakdown => 'Дневна анализа на резултати';

  @override
  String get todaysScore => 'Денешниот резултат';

  @override
  String get tasksCompleted => 'Завршени задачи';

  @override
  String get completionRate => 'Процент на завршување';

  @override
  String get howItWorks => 'Како работи';

  @override
  String get dailyScoreExplanation =>
      'Вашиот дневен резултат е врз основа на завршување на задачи. Завршете ги вашите задачи за да го подобрите вашиот резултат!';

  @override
  String get notificationFrequencyDescription =>
      'Контролирајте колку често Omi ви испраќа проактивни известувања и потсетници.';

  @override
  String get sliderOff => 'Исклучено';

  @override
  String get sliderMax => 'Максимум';

  @override
  String summaryGeneratedFor(String date) {
    return 'Резиме создадено за $date';
  }

  @override
  String get failedToGenerateSummary => 'Не успеаше да се создаде резиме. Обезбедете дека имате разговори за тој ден.';

  @override
  String get recap => 'Сумирано';

  @override
  String deleteQuoted(String name) {
    return 'Избриши \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Преместете $count разговори во:';
  }

  @override
  String get noFolder => 'Нема папка';

  @override
  String get removeFromAllFolders => 'Отстранете од сите папки';

  @override
  String get buildAndShareYourCustomApp => 'Создавај и дели ја твојата прилагодена апликација';

  @override
  String get searchAppsPlaceholder => 'Претражи 1500+ апликации';

  @override
  String get filters => 'Филтри';

  @override
  String get frequencyOff => 'Исклучено';

  @override
  String get frequencyMinimal => 'Минимално';

  @override
  String get frequencyLow => 'Ниско';

  @override
  String get frequencyBalanced => 'Избалансирано';

  @override
  String get frequencyHigh => 'Високо';

  @override
  String get frequencyMaximum => 'Максимум';

  @override
  String get frequencyDescOff => 'Нема проактивни известувања';

  @override
  String get frequencyDescMinimal => 'Само критични потсетници';

  @override
  String get frequencyDescLow => 'Само важни ажурирања';

  @override
  String get frequencyDescBalanced => 'Редовни корисни потисни подстреки';

  @override
  String get frequencyDescHigh => 'Чести проверки';

  @override
  String get frequencyDescMaximum => 'Остани константно ангажиран';

  @override
  String get clearChatQuestion => 'Очисти разговор?';

  @override
  String get syncingMessages => 'Синхронизирање на пораки со сервер...';

  @override
  String get chatAppsTitle => 'Апликации за разговор';

  @override
  String get selectApp => 'Избери апликација';

  @override
  String get noChatAppsEnabled =>
      'Нема активирани апликации за разговор.\nТапни \"Активирај апликации\" за да додаш некои.';

  @override
  String get disable => 'Деактивирај';

  @override
  String get photoLibrary => 'Библиотека на фотографии';

  @override
  String get chooseFile => 'Избери датотека';

  @override
  String get connectAiAssistantsToYourData => 'Поврзи ИИ асистенти со твојите податоци';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Следи ги твоите лични цели на главната страница';

  @override
  String get deleteRecording => 'Избриши запис';

  @override
  String get thisCannotBeUndone => 'Ова не може да се врати.';

  @override
  String get sdCard => 'SD картичка';

  @override
  String get fromSd => 'Од SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Брз пренос';

  @override
  String get syncingStatus => 'Синхронизирање';

  @override
  String get failedStatus => 'Неуспешно';

  @override
  String etaLabel(String time) {
    return 'Проценено време: $time';
  }

  @override
  String get transferMethod => 'Метод на пренос';

  @override
  String get fast => 'Брз';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Телефон';

  @override
  String get cancelSync => 'Откажи синхронизирање';

  @override
  String get cancelSyncMessage => 'Веќе преземените податоци ќе бидат зачувани. Можете да се врнете подоцна.';

  @override
  String get syncCancelled => 'Синхронизирањето е откажано';

  @override
  String get deleteProcessedFiles => 'Избриши обработени датотеки';

  @override
  String get processedFilesDeleted => 'Обработените датотеки се избришаа';

  @override
  String get wifiEnableFailed => 'Не успеаше да се активира WiFi на уредот. Моля, обидете се повторно.';

  @override
  String get deviceNoFastTransfer => 'Вашиот уред не поддржува брз пренос. Користете Bluetooth наместо тоа.';

  @override
  String get enableHotspotMessage => 'Моля, активирајте го хотспотот на вашиот телефон и обидете се повторно.';

  @override
  String get transferStartFailed => 'Не успеаше да се почне преносот. Моја, обидете се повторно.';

  @override
  String get deviceNotResponding => 'Уредот не одговори. Моля, обидете се повторно.';

  @override
  String get invalidWifiCredentials => 'Невалидни kredencijali за WiFi. Проверете ги вашите подесувања на хотспот.';

  @override
  String get wifiConnectionFailed => 'Врската WiFi неуспеа. Моля, обидете се повторно.';

  @override
  String get sdCardProcessing => 'Обработка на SD картичка';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Обработка $count запис(и). Датотеките ќе бидат отстранети од SD картичката после.';
  }

  @override
  String get process => 'Обработи';

  @override
  String get wifiSyncFailed => 'WiFi синхронизирањето неуспеа';

  @override
  String get processingFailed => 'Обработката неуспеа';

  @override
  String get downloadingFromSdCard => 'Преземање од SD картичка';

  @override
  String processingProgress(int current, int total) {
    return 'Обработка $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count разговори создадени';
  }

  @override
  String get internetRequired => 'Интернет е потребен';

  @override
  String get processAudio => 'Обработи аудио';

  @override
  String get start => 'Почни';

  @override
  String get noRecordings => 'Нема записи';

  @override
  String get audioFromOmiWillAppearHere => 'Аудио од твојот Omi уред ќе се појави овде';

  @override
  String get deleteProcessed => 'Избриши обработени';

  @override
  String get tryDifferentFilter => 'Пробај различит филтер';

  @override
  String get recordings => 'Записи';

  @override
  String get enableRemindersAccess =>
      'Моля, активирајте пристап до потсетници во подесувањата за да го користите Apple Reminders';

  @override
  String todayAtTime(String time) {
    return 'Денес во $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Вчера во $time';
  }

  @override
  String get lessThanAMinute => 'Помалку од минута';

  @override
  String estimatedMinutes(int count) {
    return '~$count минута(и)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count час(ови)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Проценено: $time преостанато';
  }

  @override
  String get summarizingConversation => 'Сумирање на разговор...\nОво може да трае неколку секунди';

  @override
  String get resummarizingConversation => 'Повторно сумирање на разговор...\nОво може да трае неколку секунди';

  @override
  String get nothingInterestingRetry => 'Ничего интересно не е пронајдено,\nсаќаш ли да се обидеш повторно?';

  @override
  String get noSummaryForConversation => 'Нема достапно резиме\nза овој разговор.';

  @override
  String get unknownLocation => 'Непозната локација';

  @override
  String get couldNotLoadMap => 'Не можеше да се вчита маپата';

  @override
  String get triggerConversationIntegration => 'Активирај интеграција за создадена разговор';

  @override
  String get webhookUrlNotSet => 'URL-ot за webhook не е поставен';

  @override
  String get setWebhookUrlInSettings =>
      'Моля, поставете го URL-от на webhook во подесувањата за програмери за да ја користите оваа функција.';

  @override
  String get sendWebUrl => 'Пошали веб URL';

  @override
  String get sendTranscript => 'Пошали транскрипт';

  @override
  String get sendSummary => 'Пошали резиме';

  @override
  String get debugModeDetected => 'Откривен е режим на отстранување грешки';

  @override
  String get performanceReduced => 'Перформансите се намалени 5-10x. Користи режим на издавање.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Автоматско затворање за ${seconds}s';
  }

  @override
  String get modelRequired => 'Модел е потребен';

  @override
  String get downloadWhisperModel => 'Моля, преземете Whisper модел пред да зачувате.';

  @override
  String get deviceNotCompatible => 'Уредот не е компатибилен';

  @override
  String get deviceRequirements => 'Вашиот уред не ги задоволува требованијата за транскрипција на уредот.';

  @override
  String get willLikelyCrash => 'Активирањето на ова веројатно ќе предизвика крај на апликацијата или замрзнување.';

  @override
  String get transcriptionSlowerLessAccurate => 'Транскрипцијата ќе биде значајно побавна и помалку точна.';

  @override
  String get proceedAnyway => 'Продолжи секако';

  @override
  String get olderDeviceDetected => 'Откривен е постар уред';

  @override
  String get onDeviceSlower => 'Транскрипцијата на уредот може да биде побава на овој уред.';

  @override
  String get batteryUsageHigher => 'Потрошувачката на батеријата ќе биде повисока од облачната транскрипција.';

  @override
  String get considerOmiCloud => 'Разметни да користиш Omi Cloud за подобрени перформанси.';

  @override
  String get highResourceUsage => 'Висока потрошувачка на ресурси';

  @override
  String get onDeviceIntensive => 'Транскрипцијата на уредот е интензивна во однос на пресметување.';

  @override
  String get batteryDrainIncrease => 'Потрошувачката на батеријата ќе се зголеми значајно.';

  @override
  String get deviceMayWarmUp => 'Уредот може да се загрее за време на долг употреба.';

  @override
  String get speedAccuracyLower => 'Брзината и точноста можат да бидат пониски од облачните модели.';

  @override
  String get cloudProvider => 'Облачен добавувач';

  @override
  String get premiumMinutesInfo =>
      '1.200 премиум минути/месец. Картичката На-уред нуди неограничена бесплатна транскрипција.';

  @override
  String get viewUsage => 'Преглед на користење';

  @override
  String get localProcessingInfo =>
      'Аудиото се обработува локално. Работи без интернет, поприватно, но користи повеќе батеријата.';

  @override
  String get model => 'Модел';

  @override
  String get performanceWarning => 'Предупредување за перформанси';

  @override
  String get largeModelWarning =>
      'Овој модел е голем и може да предизвика крај на апликацијата или многу спора работа на мобилни уреди.\n\n\"small\" или \"base\" е препорачано.';

  @override
  String get usingNativeIosSpeech => 'Користи нативно iOS препознавање на говор';

  @override
  String get noModelDownloadRequired =>
      'Ќе се користи нативната говор-машина на твојот уред. Нема потреба од преземање модел.';

  @override
  String get modelReady => 'Модел е подготвен';

  @override
  String get redownload => 'Преземи повторно';

  @override
  String get doNotCloseApp => 'Молиме, не затворајте ја апликацијата.';

  @override
  String get downloading => 'Се преземa...';

  @override
  String get downloadModel => 'Преземи модел';

  @override
  String estimatedSize(String size) {
    return 'Проценена големина: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Достапно место: $space';
  }

  @override
  String get notEnoughSpace => 'Предупредување: Нема доволно место!';

  @override
  String get download => 'Преземи';

  @override
  String downloadError(String error) {
    return 'Грешка при преземање: $error';
  }

  @override
  String get cancelled => 'Откажано';

  @override
  String get deviceNotCompatibleTitle => 'Уредот не е компатибилен';

  @override
  String get deviceNotMeetRequirements => 'Вашиот уред не ги задоволува требованијата за транскрипција на уредот.';

  @override
  String get transcriptionSlowerOnDevice => 'Транскрипцијата на уредот може да биде побава на овој уред.';

  @override
  String get computationallyIntensive => 'Транскрипцијата на уредот е интензивна во однос на пресметување.';

  @override
  String get batteryDrainSignificantly => 'Потрошувачката на батеријата ќе се зголеми значајно.';

  @override
  String get premiumMinutesMonth =>
      '1.200 премиум минути/месец. Картичката На-уред нуди неограничена бесплатна транскрипција. ';

  @override
  String get audioProcessedLocally =>
      'Аудиото се обработува локално. Работи без интернет, поприватно, но користи повеќе батеријата.';

  @override
  String get languageLabel => 'Јазик';

  @override
  String get modelLabel => 'Модел';

  @override
  String get modelTooLargeWarning =>
      'Овој модел е голем и може да предизвика крај на апликацијата или многу спора работа на мобилни уреди.\n\n\"small\" или \"base\" е препорачано.';

  @override
  String get nativeEngineNoDownload =>
      'Ќе се користи нативната машина за говор на твојот уред. Нема потреба од преземање модел.';

  @override
  String modelReadyWithName(String model) {
    return 'Модел е подготвен ($model)';
  }

  @override
  String get reDownload => 'Преземи повторно';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Се преземa $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Подготвување $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Грешка при преземање: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Проценена големина: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Достапно место: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Вградената живо транскрипција на Omi е оптимизирана за разговори во реално време со автоматско препознавање и диаризирање на говорник.';

  @override
  String get reset => 'Ресетирај';

  @override
  String get useTemplateFrom => 'Користи шаблон од';

  @override
  String get selectProviderTemplate => 'Избери шаблон на добавувач...';

  @override
  String get quicklyPopulateResponse => 'Брзо пополни со познат формат на одговор од добавувачот';

  @override
  String get quicklyPopulateRequest => 'Брзо пополни со познат формат на барање од добавувачот';

  @override
  String get invalidJsonError => 'Невалидна JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Преземи модел ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Модел: $model';
  }

  @override
  String get device => 'Уред';

  @override
  String get chatAssistantsTitle => 'Асистенти за разговор';

  @override
  String get permissionReadConversations => 'Прочитај разговори';

  @override
  String get permissionReadMemories => 'Прочитај сеќавања';

  @override
  String get permissionReadTasks => 'Прочитај задачи';

  @override
  String get permissionCreateConversations => 'Создади разговори';

  @override
  String get permissionCreateMemories => 'Создади сеќавања';

  @override
  String get permissionTypeAccess => 'Пристап';

  @override
  String get permissionTypeCreate => 'Создади';

  @override
  String get permissionTypeTrigger => 'Активирај';

  @override
  String get permissionDescReadConversations => 'Оваа апликација може да пристапи до твоите разговори.';

  @override
  String get permissionDescReadMemories => 'Оваа апликација може да пристапи до твоите сеќавања.';

  @override
  String get permissionDescReadTasks => 'Оваа апликација може да пристапи до твоите задачи.';

  @override
  String get permissionDescCreateConversations => 'Оваа апликација може да создаде нови разговори.';

  @override
  String get permissionDescCreateMemories => 'Оваа апликација може да создаде нови сеќавања.';

  @override
  String get realtimeListening => 'Слушање во реално време';

  @override
  String get setupCompleted => 'Завршено';

  @override
  String get pleaseSelectRating => 'Молиме, избери оценка';

  @override
  String get writeReviewOptional => 'Напиши преглед (опционално)';

  @override
  String get setupQuestionsIntro => 'Помозни нам да го подобриме Omi со одговорање на неколку прашања. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Што работиш?';

  @override
  String get setupQuestionUsage => '2. Каде планираш да ја користиш твојата Omi?';

  @override
  String get setupQuestionAge => '3. Која е твоја возрасна група?';

  @override
  String get setupAnswerAllQuestions => 'Нема одговорено на сите прашања! 🥺';

  @override
  String get setupSkipHelp => 'Прескочи, не сакам да помогнам :C';

  @override
  String get professionEntrepreneur => 'Претприемач';

  @override
  String get professionSoftwareEngineer => 'Софтверски инженер';

  @override
  String get professionProductManager => 'Раководител на производ';

  @override
  String get professionExecutive => 'Извршна личност';

  @override
  String get professionSales => 'Продажба';

  @override
  String get professionStudent => 'Студент';

  @override
  String get usageAtWork => 'На работа';

  @override
  String get usageIrlEvents => 'IRL настани';

  @override
  String get usageOnline => 'На интернет';

  @override
  String get usageSocialSettings => 'Во друштвени средини';

  @override
  String get usageEverywhere => 'Насекаде';

  @override
  String get customBackendUrlTitle => 'Прилагодена URL на позадина';

  @override
  String get backendUrlLabel => 'URL на позадина';

  @override
  String get saveUrlButton => 'Зачувај URL';

  @override
  String get enterBackendUrlError => 'Молиме, внесете ја URL-от на позадина';

  @override
  String get urlMustEndWithSlashError => 'URL мора да се завршува со \"/\"';

  @override
  String get invalidUrlError => 'Молиме, внесете валидна URL';

  @override
  String get backendUrlSavedSuccess => 'URL на позадина е успешно зачувана!';

  @override
  String get signInTitle => 'Најава';

  @override
  String get signInButton => 'Најави се';

  @override
  String get enterEmailError => 'Молиме, внесете ја вашата е-пошта';

  @override
  String get invalidEmailError => 'Молиме, внесете валидна е-пошта';

  @override
  String get enterPasswordError => 'Молиме, внесете ја вашата лозинка';

  @override
  String get passwordMinLengthError => 'Лозинката мора да биде најмалку 8 знакови долга';

  @override
  String get signInSuccess => 'Успешна најава!';

  @override
  String get alreadyHaveAccountLogin => 'Веќе имаш сметка? Најави се';

  @override
  String get emailLabel => 'Е-пошта';

  @override
  String get passwordLabel => 'Лозинка';

  @override
  String get createAccountTitle => 'Создади сметка';

  @override
  String get nameLabel => 'Име';

  @override
  String get repeatPasswordLabel => 'Повтори лозинка';

  @override
  String get signUpButton => 'Регистрирај се';

  @override
  String get enterNameError => 'Молиме, внесете го вашето име';

  @override
  String get passwordsDoNotMatch => 'Лозинките не се совпаѓаат';

  @override
  String get signUpSuccess => 'Успешна регистрација!';

  @override
  String get loadingKnowledgeGraph => 'Учитување на графа на знаење...';

  @override
  String get noKnowledgeGraphYet => 'Нема граф на знаење сè уште';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Се гради твојата граф на знаење од сеќавања...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Твојата граф на знаење ќе се гради автоматски кога ќе создадаш нови сеќавања.';

  @override
  String get buildGraphButton => 'Направи граф';

  @override
  String get checkOutMyMemoryGraph => 'Проверете ја мојата граф на сеќавања!';

  @override
  String get getButton => 'Земи';

  @override
  String openingApp(String appName) {
    return 'Се отвора $appName...';
  }

  @override
  String get writeSomething => 'Напиши нешто';

  @override
  String get submitReply => 'Поднеси одговор';

  @override
  String get editYourReply => 'Уреди го твојот одговор';

  @override
  String get replyToReview => 'Одговори на преглед';

  @override
  String get rateAndReviewThisApp => 'Оцени и дај преглед на оваа апликација';

  @override
  String get noChangesInReview => 'Нема промени во преглед за ажурирање.';

  @override
  String get cantRateWithoutInternet => 'Не можеш да оцениш апликација без интернет врска.';

  @override
  String get appAnalytics => 'Аналитика на апликација';

  @override
  String get learnMoreLink => 'научи повеќе';

  @override
  String get moneyEarned => 'Заработени пари';

  @override
  String get writeYourReply => 'Напиши го твојот одговор...';

  @override
  String get replySentSuccessfully => 'Одговорот е успешно испратен';

  @override
  String failedToSendReply(String error) {
    return 'Не успеаше да се испрати одговор: $error';
  }

  @override
  String get send => 'Пошли';

  @override
  String starFilter(int count) {
    return '$count звезда';
  }

  @override
  String get noReviewsFound => 'Нема пронајдени прегледи';

  @override
  String get editReply => 'Уреди одговор';

  @override
  String get reply => 'Одговори';

  @override
  String starFilterLabel(int count) {
    return '$count звезда';
  }

  @override
  String get sharePublicLink => 'Дели јавна врска';

  @override
  String get connectedKnowledgeData => 'Поврзани податоци на знаење';

  @override
  String get enterName => 'Внеси име';

  @override
  String get goal => 'ЦЕЛ';

  @override
  String get tapToTrackThisGoal => 'Тапни за да ја следиш оваа цел';

  @override
  String get tapToSetAGoal => 'Тапни за да поставиш цел';

  @override
  String get processedConversations => 'Обработени разговори';

  @override
  String get updatedConversations => 'Ажурирани разговори';

  @override
  String get newConversations => 'Нови разговори';

  @override
  String get summaryTemplate => 'Шаблон на резиме';

  @override
  String get suggestedTemplates => 'Предложени шаблони';

  @override
  String get otherTemplates => 'Други шаблони';

  @override
  String get availableTemplates => 'Достапни шаблони';

  @override
  String get getCreative => 'Биди креативен';

  @override
  String get defaultLabel => 'Подразумеван';

  @override
  String get lastUsedLabel => 'Последно користено';

  @override
  String get setDefaultApp => 'Постави подразумевана апликација';

  @override
  String setDefaultAppContent(String appName) {
    return 'Постави $appName како твоја подразумевана апликација за сумирање?\n\nОваа апликација ќе се користи автоматски за сите идни сумирања на разговори.';
  }

  @override
  String get setDefaultButton => 'Постави подразумевано';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName е поставена како подразумевана апликација за сумирање';
  }

  @override
  String get createCustomTemplate => 'Создади прилагодена шаблон';

  @override
  String get allTemplates => 'Сите шаблони';

  @override
  String failedToInstallApp(String appName) {
    return 'Не успеаше да се инсталира $appName. Молиме, обидете се повторно.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Грешка при инсталација на $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Означи говорник $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Веќе постои лице со ово име.';

  @override
  String get selectYouFromList => 'За да се означиш себе, молиме избери \"Ти\" од листата.';

  @override
  String get enterPersonsName => 'Внесете го името на лицето';

  @override
  String get addPerson => 'Додај лице';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Означи други делови од овој говорник ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Означи други делови';

  @override
  String get managePeople => 'Управувај со луѓе';

  @override
  String get shareViaSms => 'Дели преку SMS';

  @override
  String get selectContactsToShareSummary => 'Избери контакти за да го делиш твое резиме на разговор';

  @override
  String get searchContactsHint => 'Претражи контакти...';

  @override
  String contactsSelectedCount(int count) {
    return '$count избрани';
  }

  @override
  String get clearAllSelection => 'Очисти сè';

  @override
  String get selectContactsToShare => 'Избери контакти за делење';

  @override
  String shareWithContactCount(int count) {
    return 'Дели со $count контакт';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Дели со $count контакти';
  }

  @override
  String get contactsPermissionRequired => 'Е потребна дозвола за контакти';

  @override
  String get contactsPermissionRequiredForSms => 'Е потребна дозвола за контакти за делење преку SMS';

  @override
  String get grantContactsPermissionForSms => 'Молиме, дај дозвола за контакти за делење преку SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Нема пронајдени контакти со телефонски броеви';

  @override
  String get noContactsMatchSearch => 'Нема контакти кои се совпаѓаат со твојата претрага';

  @override
  String get failedToLoadContacts => 'Не успеаше да се вчитаат контакти';

  @override
  String get failedToPrepareConversationForSharing =>
      'Не успеаше да се подготви разговор за делење. Молиме, обидете се повторно.';

  @override
  String get couldNotOpenSmsApp => 'Не можеше да се отвори SMS апликација. Молиме, обидете се повторно.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Ево што штом дискутиравме: $link';
  }

  @override
  String get wifiSync => 'WiFi синхронизирање';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item е копирано во клипбордот';
  }

  @override
  String get wifiConnectionFailedTitle => 'Врската неуспеа';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Поврзување со $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Активирај WiFi на $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Поврзи се на $deviceName';
  }

  @override
  String get recordingDetails => 'Детали на запис';

  @override
  String get storageLocationSdCard => 'SD картичка';

  @override
  String get storageLocationLimitlessPendant => 'Limitless привезок';

  @override
  String get storageLocationPhone => 'Телефон';

  @override
  String get storageLocationPhoneMemory => 'Телефон (сеќавање)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Складирано на $deviceName';
  }

  @override
  String get transferring => 'Се преносува...';

  @override
  String get transferRequired => 'Пренос е потребен';

  @override
  String get downloadingAudioFromSdCard => 'Се преземa аудио од SD картичката на твојот уред';

  @override
  String get transferRequiredDescription =>
      'Овој запис е складиран на SD картичката на твојот уред. Пренеси го на твојот телефон за да можеш да го слушаш или делиш.';

  @override
  String get cancelTransfer => 'Откажи пренос';

  @override
  String get transferToPhone => 'Пренеси во телефон';

  @override
  String get privateAndSecureOnDevice => 'Приватно и безбедно на твојот уред';

  @override
  String get recordingInfo => 'Информации за запис';

  @override
  String get transferInProgress => 'Трансфер во напредок...';

  @override
  String get shareRecording => 'Сподели Снимање';

  @override
  String get deleteRecordingConfirmation =>
      'Сигурни ли сте дека сакате трајно да го избришете ова снимање? Ова не може да се отповика.';

  @override
  String get recordingIdLabel => 'ID на Снимање';

  @override
  String get dateTimeLabel => 'Датум и Време';

  @override
  String get durationLabel => 'Траење';

  @override
  String get audioFormatLabel => 'Формат на Аудио';

  @override
  String get storageLocationLabel => 'Локација на Складување';

  @override
  String get estimatedSizeLabel => 'Проценета Големина';

  @override
  String get deviceModelLabel => 'Модел на Уред';

  @override
  String get deviceIdLabel => 'ID на Уред';

  @override
  String get statusLabel => 'Статус';

  @override
  String get statusProcessed => 'Обработено';

  @override
  String get statusUnprocessed => 'Необработено';

  @override
  String get switchedToFastTransfer => 'Пребачено на Брз Трансфер';

  @override
  String get transferCompleteMessage => 'Трансфер завршен! Сега можете да го пуштите ово снимање.';

  @override
  String transferFailedMessage(String error) {
    return 'Трансфер неуспешен: $error';
  }

  @override
  String get transferCancelled => 'Трансфер откажан';

  @override
  String get fastTransferEnabled => 'Брз трансфер активиран';

  @override
  String get bluetoothSyncEnabled => 'Синхронизација преку Bluetooth активирана';

  @override
  String get enableFastTransfer => 'Активирај Брз Трансфер';

  @override
  String get fastTransferDescription =>
      'Брз трансфер користи WiFi за ~5x побрзи брзини. Вашиот телефон привремено ќе се поврзе со WiFi мрежата на вашиот Omi уред durante трансферот.';

  @override
  String get internetAccessPausedDuringTransfer => 'Пристапот до интернет е паузиран durante трансферот';

  @override
  String get chooseTransferMethodDescription =>
      'Одберете како снимањата ќе се трансферуваат од вашиот Omi уред на вашиот телефон.';

  @override
  String get wifiSpeed => '~150 KB/s преку WiFi';

  @override
  String get fiveTimesFaster => '5X ПОБРЗО';

  @override
  String get fastTransferMethodDescription =>
      'Создава директна WiFi врска со вашиот Omi уред. Вашиот телефон привремено се откачува од вашата редовна WiFi durante трансферот.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s преку BLE';

  @override
  String get bluetoothMethodDescription =>
      'Користи стандардна Bluetooth Low Energy врска. Побавно, но не влијае на вашата WiFi врска.';

  @override
  String get selected => 'Избрано';

  @override
  String get selectOption => 'Одбери';

  @override
  String get lowBatteryAlertTitle => 'Предупредување за Мала Батерија';

  @override
  String get lowBatteryAlertBody => 'Вашиот уред има ниска батерија. Време е за полнење! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Вашиот Omi Уред се Откачи';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Ве молиме се поврзете повторно за да продолжите да го користите вашиот Omi.';

  @override
  String get firmwareUpdateAvailable => 'Достапна е Ажурирање на Firmware';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Ново ажурирање на firmware ($version) е достапно за вашиот Omi уред. Дали сакате да ажурирате сега?';
  }

  @override
  String get later => 'Подоцна';

  @override
  String get appDeletedSuccessfully => 'Апликацијата е избришана успешно';

  @override
  String get appDeleteFailed => 'Неуспешно бришење на апликација. Ве молиме обидете се подоцна.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Видливоста на апликацијата е променена успешно. Може да потрае неколку минути да се рефлектира.';

  @override
  String get errorActivatingAppIntegration =>
      'Грешка при активирање на апликацијата. Ако е интеграциона апликација, осигурајте се дека постапката за подготовка е завршена.';

  @override
  String get errorUpdatingAppStatus => 'Дошло до грешка при ажурирање на статусот на апликацијата.';

  @override
  String get calculatingETA => 'Пресметување...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Приближно $minutes минути преостануваат';
  }

  @override
  String get aboutAMinuteRemaining => 'Приближно една минута преостанува';

  @override
  String get almostDone => 'Скоро завршено...';

  @override
  String get omiSays => 'omi вели';

  @override
  String get analyzingYourData => 'Анализа на вашите податоци...';

  @override
  String migratingToProtection(String level) {
    return 'Мигрирање на $level заштита...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Нема податоци за мигрирање. Финализирање...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Мигрирање $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Сите објекти мигрирани. Финализирање...';

  @override
  String get migrationErrorOccurred => 'Дошло до грешка durante мигрирањето. Ве молиме обидете се повторно.';

  @override
  String get migrationComplete => 'Мигрирањето е завршено!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Вашите податоци се сега заштитени со новите $level поставки.';
  }

  @override
  String get chatsLowercase => 'разговори';

  @override
  String get dataLowercase => 'податоци';

  @override
  String get fallNotificationTitle => 'Ауч';

  @override
  String get fallNotificationBody => 'Дали паднавте?';

  @override
  String get importantConversationTitle => 'Важен Разговор';

  @override
  String get importantConversationBody =>
      'Штотуку имавте важен разговор. Допрете за да го споделите резимеот со други.';

  @override
  String get templateName => 'Име на Шаблон';

  @override
  String get templateNameHint => 'нпр., Извлекувач на Акциони Ставки од Состанок';

  @override
  String get nameMustBeAtLeast3Characters => 'Името мора да содржи најмалку 3 карактери';

  @override
  String get conversationPromptHint =>
      'нпр., Извлеци акциони ставки, одлуки направени и клучни заклучоци од дадениот разговор.';

  @override
  String get pleaseEnterAppPrompt => 'Ве молиме внесете промпт за вашата апликација';

  @override
  String get promptMustBeAtLeast10Characters => 'Промптот мора да содржи најмалку 10 карактери';

  @override
  String get anyoneCanDiscoverTemplate => 'Секој може да го откае вашиот шаблон';

  @override
  String get onlyYouCanUseTemplate => 'Само вие можете да го користите овој шаблон';

  @override
  String get generatingDescription => 'Генерирање опис...';

  @override
  String get creatingAppIcon => 'Создавање икона на апликација...';

  @override
  String get installingApp => 'Инсталирање апликација...';

  @override
  String get appCreatedAndInstalled => 'Апликацијата е создадена и инсталирана!';

  @override
  String get appCreatedSuccessfully => 'Апликацијата е успешно создадена!';

  @override
  String get failedToCreateApp => 'Неуспешно создавање на апликација. Ве молиме обидете се повторно.';

  @override
  String get addAppSelectCoreCapability =>
      'Ве молиме одберете една повеќе основна способност за вашата апликација за да продолжите';

  @override
  String get addAppSelectPaymentPlan => 'Ве молиме одберете план за плаќање и внесете цена за вашата апликација';

  @override
  String get addAppSelectCapability => 'Ве молиме одберете најмалку една способност за вашата апликација';

  @override
  String get addAppSelectLogo => 'Ве молиме одберете лого за вашата апликација';

  @override
  String get addAppEnterChatPrompt => 'Ве молиме внесете промпт за разговор за вашата апликација';

  @override
  String get addAppEnterConversationPrompt => 'Ве молиме внесете промпт за разговор за вашата апликација';

  @override
  String get addAppSelectTriggerEvent => 'Ве молиме одберете настан за активирање за вашата апликација';

  @override
  String get addAppEnterWebhookUrl => 'Ве молиме внесете URL на вебхук за вашата апликација';

  @override
  String get addAppSelectCategory => 'Ве молиме одберете категорија за вашата апликација';

  @override
  String get addAppFillRequiredFields => 'Ве молиме пополнете ги сите задолжителни полиња правилно';

  @override
  String get addAppUpdatedSuccess => 'Апликацијата е успешно ажурирана 🚀';

  @override
  String get addAppUpdateFailed => 'Неуспешно ажурирање на апликација. Ве молиме обидете се подоцна';

  @override
  String get addAppSubmittedSuccess => 'Апликацијата е успешно поднесена 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Грешка при отворање на избирач на датотеки: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Грешка при избирање на слика: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Дозвола за фотографии одбиена. Ве молиме дозволете пристап до фотографии за да одберете слика';

  @override
  String get addAppErrorSelectingImageRetry => 'Грешка при избирање на слика. Ве молиме обидете се повторно.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Грешка при избирање на минијатура: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Грешка при избирање на минијатура. Ве молиме обидете се повторно.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Други способности не можат да бидат избрани со Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona не може да биде избрана со други способности';

  @override
  String get paymentFailedToFetchCountries => 'Неуспешно преземање на поддржани держави. Ве молиме обидете се подоцна.';

  @override
  String get paymentFailedToSetDefault =>
      'Неуспешна постава на стандарден метод за плаќање. Ве молиме обидете се подоцна.';

  @override
  String get paymentFailedToSavePaypal => 'Неуспешно зачување на детали за PayPal. Ве молиме обидете се подоцна.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Активно';

  @override
  String get paymentStatusConnected => 'Поврзано';

  @override
  String get paymentStatusNotConnected => 'Не е поврзано';

  @override
  String get paymentAppCost => 'Цена на Апликација';

  @override
  String get paymentEnterValidAmount => 'Ве молиме внесете валидна сума';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Ве молиме внесете сума поголема од 0';

  @override
  String get paymentPlan => 'План за Плаќање';

  @override
  String get paymentNoneSelected => 'Ничего не е избрано';

  @override
  String get aiGenPleaseEnterDescription => 'Ве молиме внесете опис за вашата апликација';

  @override
  String get aiGenCreatingAppIcon => 'Создавање икона на апликација...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Дошло до грешка: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Апликацијата е успешно создадена!';

  @override
  String get aiGenFailedToCreateApp => 'Неуспешно создавање на апликација';

  @override
  String get aiGenErrorWhileCreatingApp => 'Дошло до грешка при создавање на апликацијата';

  @override
  String get aiGenFailedToGenerateApp => 'Неуспешно генерирање на апликација. Ве молиме обидете се повторно.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Неуспешна регенерирање на икона';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Ве молиме прво генерирајте апликација';

  @override
  String get nextButton => 'Следно';

  @override
  String get connectOmiDevice => 'Поврзи Omi Уред';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Го сменувате вашиот Unlimited План на $title. Сигурни ли сте дека сакате да продолжите?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Ажурирање закажано! Вашиот месечен план продолжува до крајот на вашиот билинг период, потоа автоматски се смена на годишен.';

  @override
  String get couldNotSchedulePlanChange => 'Не можеше да се закаже промена на план. Ве молиме обидете се повторно.';

  @override
  String get subscriptionReactivatedDefault =>
      'Вашата претплата е повторно активирана! Без наплата сега - ќе бидете наплатени на крајот на вашиот тековен период.';

  @override
  String get subscriptionSuccessfulCharged => 'Претплата успешна! Сте наплатени за новиот билинг период.';

  @override
  String get couldNotProcessSubscription => 'Не можеше да се обработи претплата. Ве молиме обидете се повторно.';

  @override
  String get couldNotLaunchUpgradePage =>
      'Не можеше да се лансира страница за ажурирање. Ве молиме обидете се повторно.';

  @override
  String get transcriptionJsonPlaceholder => 'Налепете вашата JSON конфигурација овде...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Грешка при отворање на избирач на датотеки: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Грешка: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Разговорите се Успешно Споени';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count разговори се успешно споени';
  }

  @override
  String get actionItemReminderTitle => 'Omi Потсетник';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName Откачено';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Ве молиме се поврзете повторно за да продолжите да го користите вашиот $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Пријава';

  @override
  String get onboardingYourName => 'Вашето Име';

  @override
  String get onboardingLanguage => 'Јазик';

  @override
  String get onboardingPermissions => 'Дозволи';

  @override
  String get onboardingComplete => 'Завршено';

  @override
  String get onboardingWelcomeToOmi => 'Добредојде на Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Кажи ни за себеси';

  @override
  String get onboardingChooseYourPreference => 'Одберете вашата преференција';

  @override
  String get onboardingGrantRequiredAccess => 'Дозволете потребен пристап';

  @override
  String get onboardingYoureAllSet => 'Сите сте подготвени';

  @override
  String get searchTranscriptOrSummary => 'Пребарај транскрипт или резиме...';

  @override
  String get myGoal => 'Мојата цел';

  @override
  String get appNotAvailable => 'Ој! Изгледа дека апликацијата што ја бараш не е достапна.';

  @override
  String get failedToConnectTodoist => 'Неуспешна поврзување со Todoist';

  @override
  String get failedToConnectAsana => 'Неуспешна поврзување со Asana';

  @override
  String get failedToConnectGoogleTasks => 'Неуспешна поврзување со Google Tasks';

  @override
  String get failedToConnectClickUp => 'Неуспешна поврзување со ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Неуспешна поврзување со $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Успешно поврзување со Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Неуспешна поврзување со Todoist. Ве молиме обидете се повторно.';

  @override
  String get successfullyConnectedAsana => 'Успешно поврзување со Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Неуспешна поврзување со Asana. Ве молиме обидете се повторно.';

  @override
  String get successfullyConnectedGoogleTasks => 'Успешно поврзување со Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Неуспешна поврзување со Google Tasks. Ве молиме обидете се повторно.';

  @override
  String get successfullyConnectedClickUp => 'Успешно поврзување со ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Неуспешна поврзување со ClickUp. Ве молиме обидете се повторно.';

  @override
  String get successfullyConnectedNotion => 'Успешно поврзување со Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Неуспешна освежување на статусот на поврзување со Notion.';

  @override
  String get successfullyConnectedGoogle => 'Успешно поврзување со Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Неуспешна освежување на статусот на поврзување со Google.';

  @override
  String get successfullyConnectedWhoop => 'Успешно поврзување со Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Неуспешна освежување на статусот на поврзување со Whoop.';

  @override
  String get successfullyConnectedGitHub => 'Успешно поврзување со GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Неуспешна освежување на статусот на поврзување со GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'Неуспешна пријава со Google, ве молиме обидете се повторно.';

  @override
  String get authenticationFailed => 'Пријавата неуспешна. Ве молиме обидете се повторно.';

  @override
  String get authFailedToSignInWithApple => 'Неуспешна пријава со Apple, ве молиме обидете се повторно.';

  @override
  String get authFailedToRetrieveToken => 'Неуспешно преземање на firebase жетон, ве молиме обидете се повторно.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Неочекувана грешка при пријава, Firebase грешка, ве молиме обидете се повторно.';

  @override
  String get authUnexpectedError => 'Неочекувана грешка при пријава, ве молиме обидете се повторно';

  @override
  String get authFailedToLinkGoogle => 'Неуспешно поврзување со Google, ве молиме обидете се повторно.';

  @override
  String get authFailedToLinkApple => 'Неуспешно поврзување со Apple, ве молиме обидете се повторно.';

  @override
  String get onboardingBluetoothRequired => 'Дозволата за Bluetooth е потребна за поврзување со вашиот уред.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Дозволата за Bluetooth е одбиена. Ве молиме дозволете дозвола во Системски Преференции.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Статус на дозвола за Bluetooth: $status. Ве молиме проверете Системски Преференции.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Неуспешна проверка на дозвола за Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Дозволата за Известување е одбиена. Ве молиме дозволете дозвола во Системски Преференции.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Дозволата за Известување е одбиена. Ве молиме дозволете дозвола во Системски Преференции > Известувања.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Статус на дозвола за Известување: $status. Ве молиме проверете Системски Преференции.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Неуспешна проверка на дозвола за Известување: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Ве молиме дозволете дозвола за локација во Поставки > Приватност и Безбедност > Услуги на Локација';

  @override
  String get onboardingMicrophoneRequired => 'Дозволата за Микрофон е потребна за снимање.';

  @override
  String get onboardingMicrophoneDenied =>
      'Дозволата за Микрофон е одбиена. Ве молиме дозволете дозвола во Системски Преференции > Приватност и Безбедност > Микрофон.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Статус на дозвола за Микрофон: $status. Ве молиме проверете Системски Преференции.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Неуспешна проверка на дозвола за Микрофон: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'Дозволата за Снимање на Екран е потребна за снимање на системски аудио.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Дозволата за Снимање на Екран е одбиена. Ве молиме дозволете дозвола во Системски Преференции > Приватност и Безбедност > Снимање на Екран.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Статус на дозвола за Снимање на Екран: $status. Ве молиме проверете Системски Преференции.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Неуспешна проверка на дозвола за Снимање на Екран: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Дозволата за Пристапност е потребна за детектирање на состаноци во прелистувачот.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Статус на дозвола за Пристапност: $status. Ве молиме проверете Системски Преференции.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Неуспешна проверка на дозвола за Пристапност: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Снимање со камера не е достапно на оваа платформа';

  @override
  String get msgCameraPermissionDenied => 'Дозволата за Камера е одбиена. Ве молиме дозволете пристап до камера';

  @override
  String msgCameraAccessError(String error) {
    return 'Грешка при пристап до камера: $error';
  }

  @override
  String get msgPhotoError => 'Грешка при фотографирање. Ве молиме обидете се повторно.';

  @override
  String get msgMaxImagesLimit => 'Можете да одберете до 4 слики';

  @override
  String msgFilePickerError(String error) {
    return 'Грешка при отворање на избирач на датотеки: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Грешка при избирање на слики: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Дозволата за Фотографии е одбиена. Ве молиме дозволете пристап до фотографии за да одберете слики';

  @override
  String get msgSelectImagesGenericError => 'Грешка при избирање на слики. Ве молиме обидете се повторно.';

  @override
  String get msgMaxFilesLimit => 'Можете да одберете до 4 датотеки';

  @override
  String msgSelectFilesError(String error) {
    return 'Грешка при избирање на датотеки: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Грешка при избирање на датотеки. Ве молиме обидете се повторно.';

  @override
  String get msgUploadFileFailed => 'Неуспешна подигање на датотека, ве молиме обидете се подоцна';

  @override
  String get msgReadingMemories => 'Читање на вашите спомени...';

  @override
  String get msgLearningMemories => 'Учење од вашите спомени...';

  @override
  String get msgUploadAttachedFileFailed => 'Неуспешна подигање на приложената датотека.';

  @override
  String captureRecordingError(String error) {
    return 'Дошло до грешка durante снимањето: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Снимањето е застанато: $reason. Можеби ќе треба да ги повеќе поврзете надворешните дисплеи или да го почнете повторно снимањето.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Дозвола за микрофон потребна';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Дозволете дозвола за микрофон во Системски Преференции';

  @override
  String get captureScreenRecordingPermissionRequired => 'Дозвола за снимање на екран потребна';

  @override
  String get captureDisplayDetectionFailed => 'Детектирање на екран неуспешно. Снимањето е застанато.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Невалиден URL на вебхук за аудио бајтови';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Невалиден URL на вебхук за приливно-времече транскрипт';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Невалиден URL на вебхук за создадена разговор';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Невалиден URL на вебхук за резиме на ден';

  @override
  String get devModeSettingsSaved => 'Поставките се зачувани!';

  @override
  String get voiceFailedToTranscribe => 'Неуспешна транскрипција на аудио';

  @override
  String get locationPermissionRequired => 'Дозвола за Локација Потребна';

  @override
  String get locationPermissionContent =>
      'Брз трансфер бара дозвола за локација за потврда на WiFi врска. Ве молиме дозволете дозвола за локација за да продолжите.';

  @override
  String get pdfTranscriptExport => 'Извоз на Транскрипт';

  @override
  String get pdfConversationExport => 'Извоз на Разговор';

  @override
  String pdfTitleLabel(String title) {
    return 'Наслов: $title';
  }

  @override
  String get conversationNewIndicator => 'Ново 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count фотографии';
  }

  @override
  String get mergingStatus => 'Спојување...';

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
    return '$count денови';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days денови $hours часа';
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
  String get moveToFolder => 'Премести во Папка';

  @override
  String get noFoldersAvailable => 'Нема достапни папки';

  @override
  String get newFolder => 'Нова Папка';

  @override
  String get color => 'Боја';

  @override
  String get waitingForDevice => 'Чекање на уред...';

  @override
  String get saySomething => 'Кажи нешто...';

  @override
  String get initialisingSystemAudio => 'Иницијализирање на Системски Аудио';

  @override
  String get stopRecording => 'Стоп Снимање';

  @override
  String get continueRecording => 'Продолжи Снимање';

  @override
  String get initialisingRecorder => 'Иницијализирање на Снимач';

  @override
  String get pauseRecording => 'Пауза Снимање';

  @override
  String get resumeRecording => 'Продолжи Снимање';

  @override
  String get noDailyRecapsYet => 'Нема дневни резимеа сѐ пока';

  @override
  String get dailyRecapsDescription => 'Вашите дневни резимеа ќе се појават овде кога ќе бидат генерирани';

  @override
  String get chooseTransferMethod => 'Одбери Метод за Трансфер';

  @override
  String get fastTransferSpeed => '~150 KB/s преку WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Голем временски јаз детектиран ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Големи временски јазови детектирани ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle => 'Уредот не подржува WiFi синхронизација, смена на Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health не е достапно на овој уред';

  @override
  String get downloadAudio => 'Преземи Аудио';

  @override
  String get audioDownloadSuccess => 'Аудио е успешно преземен';

  @override
  String get audioDownloadFailed => 'Неуспешно преземање на аудио';

  @override
  String get downloadingAudio => 'Преземање на аудио...';

  @override
  String get shareAudio => 'Сподели Аудио';

  @override
  String get preparingAudio => 'Подготовка на Аудио';

  @override
  String get gettingAudioFiles => 'Преземање на аудио датотеки...';

  @override
  String get downloadingAudioProgress => 'Преземање на Аудио';

  @override
  String get processingAudio => 'Обработка на Аудио';

  @override
  String get combiningAudioFiles => 'Комбинирање на аудио датотеки...';

  @override
  String get audioReady => 'Аудио Подготвено';

  @override
  String get openingShareSheet => 'Отворање на лист за споделување...';

  @override
  String get audioShareFailed => 'Спелување Неуспешно';

  @override
  String get dailyRecaps => 'Дневни Резимеа';

  @override
  String get removeFilter => 'Отстрани Филтер';

  @override
  String get categoryConversationAnalysis => 'Анализа на Разговор';

  @override
  String get categoryHealth => 'Здравје';

  @override
  String get categoryEducation => 'Образование';

  @override
  String get categoryCommunication => 'Комуникација';

  @override
  String get categoryEmotionalSupport => 'Емоционална Поддршка';

  @override
  String get categoryProductivity => 'Продуктивност';

  @override
  String get categoryEntertainment => 'Забава';

  @override
  String get categoryFinancial => 'Финансиско';

  @override
  String get categoryTravel => 'Патување';

  @override
  String get categorySafety => 'Безбедност';

  @override
  String get categoryShopping => 'Куповање';

  @override
  String get categorySocial => 'Социјално';

  @override
  String get categoryNews => 'Вести';

  @override
  String get categoryUtilities => 'Комунални Услуги';

  @override
  String get categoryOther => 'Друго';

  @override
  String get capabilityChat => 'Разговор';

  @override
  String get capabilityConversations => 'Разговори';

  @override
  String get capabilityExternalIntegration => 'Надворешна Интеграција';

  @override
  String get capabilityNotification => 'Известување';

  @override
  String get triggerAudioBytes => 'Аудио Бајтови';

  @override
  String get triggerConversationCreation => 'Создавање на Разговор';

  @override
  String get triggerTranscriptProcessed => 'Транскрипт Обработен';

  @override
  String get actionCreateConversations => 'Создади разговори';

  @override
  String get actionCreateMemories => 'Создади спомени';

  @override
  String get actionReadConversations => 'Читај разговори';

  @override
  String get actionReadMemories => 'Читај спомени';

  @override
  String get actionReadTasks => 'Читај задачи';

  @override
  String get scopeUserName => 'Име на Корисник';

  @override
  String get scopeUserFacts => 'Факти на Корисник';

  @override
  String get scopeUserConversations => 'Разговори на Корисник';

  @override
  String get scopeUserChat => 'Разговор на Корисник';

  @override
  String get capabilitySummary => 'Резиме';

  @override
  String get capabilityFeatured => 'Избраңо';

  @override
  String get capabilityTasks => 'Задачи';

  @override
  String get capabilityIntegrations => 'Интеграции';

  @override
  String get categoryProductivityLifestyle => 'Продуктивност и Начин на Живот';

  @override
  String get categorySocialEntertainment => 'Социјално и Забава';

  @override
  String get categoryProductivityTools => 'Продуктивност и Алатки';

  @override
  String get categoryPersonalWellness => 'Лично и начин на живот';

  @override
  String get rating => 'Оценка';

  @override
  String get categories => 'Категории';

  @override
  String get sortBy => 'Сортирај';

  @override
  String get highestRating => 'Највисока оценка';

  @override
  String get lowestRating => 'Најниска оценка';

  @override
  String get resetFilters => 'Исчисти филтери';

  @override
  String get applyFilters => 'Примени филтери';

  @override
  String get mostInstalls => 'Најмногу инсталирања';

  @override
  String get couldNotOpenUrl => 'Неможам да ја отворам врската. Пробај повторно.';

  @override
  String get newTask => 'Нова задача';

  @override
  String get viewAll => 'Преглед на сите';

  @override
  String get addTask => 'Додај задача';

  @override
  String get addMcpServer => 'Додај MCP сервер';

  @override
  String get connectExternalAiTools => 'Поврзи надворешни алатки за вештачка интелигенција';

  @override
  String get mcpServerUrl => 'MCP сервер URL';

  @override
  String mcpServerConnected(int count) {
    return '$count алатки успешно поврзани';
  }

  @override
  String get mcpConnectionFailed => 'Неуспешна врска со MCP сервер';

  @override
  String get authorizingMcpServer => 'Овластување...';

  @override
  String get whereDidYouHearAboutOmi => 'Како ви се натипа Omi?';

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
  String get friendWordOfMouth => 'Пријател';

  @override
  String get otherSource => 'Друго';

  @override
  String get pleaseSpecify => 'Веќе специфицирај';

  @override
  String get event => 'Настан';

  @override
  String get coworker => 'Колега';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Аудио датотеката не е достапна за пуштање';

  @override
  String get audioPlaybackFailed => 'Неможам да го пуштам аудиото. Датотеката може да е оштетена или недостасува.';

  @override
  String get connectionGuide => 'Водич за поврзување';

  @override
  String get iveDoneThis => 'Веќе го направив ова';

  @override
  String get pairNewDevice => 'Спарај ново уред';

  @override
  String get dontSeeYourDevice => 'Не видиш го твојот уред?';

  @override
  String get reportAnIssue => 'Пријави проблем';

  @override
  String get pairingTitleOmi => 'Вклучи го Omi';

  @override
  String get pairingDescOmi => 'Притисни и држи го уредот додека не трепери за да го вклучиш.';

  @override
  String get pairingTitleOmiDevkit => 'Стави го Omi DevKit во режим на спарување';

  @override
  String get pairingDescOmiDevkit =>
      'Притисни го копчето еднаш за вклучување. LED ќе блика виолетово кога е во режим на спарување.';

  @override
  String get pairingTitleOmiGlass => 'Вклучи го Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Вклучи го притиснувајќи го страничното копче 3 секунди.';

  @override
  String get pairingTitlePlaudNote => 'Стави го Plaud Note во режим на спарување';

  @override
  String get pairingDescPlaudNote =>
      'Притисни и држи го страничното копче 2 секунди. Црвениот LED ќе блика кога е спремен за спарување.';

  @override
  String get pairingTitleBee => 'Стави го Bee во режим на спарување';

  @override
  String get pairingDescBee =>
      'Притисни го копчето 5 пати последователно. Светлината ќе почне да блика синьо и зелено.';

  @override
  String get pairingTitleLimitless => 'Стави го Limitless во режим на спарување';

  @override
  String get pairingDescLimitless =>
      'Кога е видлива каква било светлина, притисни еднаш и потоа притисни и држи додека уредот не покаже розова светлина, потоа пушти.';

  @override
  String get pairingTitleFriendPendant => 'Стави го Friend Pendant во режим на спарување';

  @override
  String get pairingDescFriendPendant =>
      'Притисни го копчето на привескот за да го вклучиш. Автоматски ќе влезе во режим на спарување.';

  @override
  String get pairingTitleFieldy => 'Стави го Fieldy во режим на спарување';

  @override
  String get pairingDescFieldy => 'Притисни и држи го уредот додека светлината не се појави за да го вклучиш.';

  @override
  String get pairingTitleAppleWatch => 'Поврзи го Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Инсталирај и отвори ја апликацијата Omi на твојот Apple Watch, потоа допри Поврзи во апликацијата.';

  @override
  String get pairingTitleNeoOne => 'Стави го Neo One во режим на спарување';

  @override
  String get pairingDescNeoOne =>
      'Притисни и држи го копчето за напајување додека LED не трепери. Уредот ќе биде достопен.';

  @override
  String get downloadingFromDevice => 'Преземање од уред';

  @override
  String get reconnectingToInternet => 'Повторна поврзување на интернет...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Ископување $current од $total';
  }

  @override
  String get processingOnServer => 'Обработка на сервер...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Обработка... $current/$total сегменти';
  }

  @override
  String get processedStatus => 'Обработено';

  @override
  String get corruptedStatus => 'Оштетено';

  @override
  String nPending(int count) {
    return '$count во очекување';
  }

  @override
  String nProcessed(int count) {
    return '$count обработено';
  }

  @override
  String get synced => 'Синхронизирано';

  @override
  String get noPendingRecordings => 'Нема записи во очекување';

  @override
  String get noProcessedRecordings => 'Нема обработени записи сè уште';

  @override
  String get pending => 'Во очекување';

  @override
  String whatsNewInVersion(String version) {
    return 'Што е ново во $version';
  }

  @override
  String get addToYourTaskList => 'Додај на твоја листа на задачи?';

  @override
  String get failedToCreateShareLink => 'Неуспешно создавање врска за споделување';

  @override
  String get deleteGoal => 'Избриши цел';

  @override
  String get deviceUpToDate => 'Твојот уред е ажуриран';

  @override
  String get wifiConfiguration => 'WiFi конфигурација';

  @override
  String get wifiConfigurationSubtitle =>
      'Внеси ги твоите WiFi верификации за да дозволиш уредот да ја преземе фирмверот.';

  @override
  String get networkNameSsid => 'Назив на мрежа (SSID)';

  @override
  String get enterWifiNetworkName => 'Внеси назив на WiFi мрежа';

  @override
  String get enterWifiPassword => 'Внеси WiFi лозинка';

  @override
  String get appIconLabel => 'Икона на апликација';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Ево што знам за тебе';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Оваа карта се ажурира додека Omi учи од твоите разговори.';

  @override
  String get apiEnvironment => 'API окружување';

  @override
  String get apiEnvironmentDescription => 'Одбери на кој позадински систем да се поврзеш';

  @override
  String get production => 'Производство';

  @override
  String get staging => 'Фаза на тестирање';

  @override
  String get switchRequiresRestart => 'Менување бара рестартање на апликацијата';

  @override
  String get switchApiConfirmTitle => 'Смени API окружување';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Смени во $environment? Мораш да ја затвориш и повторно да ја отвориш апликацијата за промените да влезат во сила.';
  }

  @override
  String get switchAndRestart => 'Смени';

  @override
  String get stagingDisclaimer =>
      'Фаза на тестирање може да биде со грешки, нестабилна и податоците може да се изгубат. Користи само за тестирање.';

  @override
  String get apiEnvSavedRestartRequired => 'Сачувано. Затвори и повторно отвори ја апликацијата да применя.';

  @override
  String get shared => 'Споделено';

  @override
  String get onlyYouCanSeeConversation => 'Само ти можеш да видиш овој разговор';

  @override
  String get anyoneWithLinkCanView => 'Секој со врска може да види';

  @override
  String get tasksCleanTodayTitle => 'Избриши ги денешните задачи?';

  @override
  String get tasksCleanTodayMessage => 'Ќе ги избрише само рокови';

  @override
  String get tasksOverdue => 'Закаснело';

  @override
  String get phoneCallsWithOmi => 'Телефонски разговори со Omi';

  @override
  String get phoneCallsSubtitle => 'Направи повици со транскрипција во реално време';

  @override
  String get phoneSetupStep1Title => 'Потврди го твојот телефонски број';

  @override
  String get phoneSetupStep1Subtitle => 'Ќе те повикаме за да потврдиме дека е твој';

  @override
  String get phoneSetupStep2Title => 'Внеси верификачки код';

  @override
  String get phoneSetupStep2Subtitle => 'Кратък код што ќе го напишеш на повикот';

  @override
  String get phoneSetupStep3Title => 'Почни да повикуваш ги твоите контакти';

  @override
  String get phoneSetupStep3Subtitle => 'Со вградена транскрипција во реално време';

  @override
  String get phoneGetStarted => 'Почни';

  @override
  String get callRecordingConsentDisclaimer => 'Снимање на повици може да бара согласност во твојата јурисдикција';

  @override
  String get enterYourNumber => 'Внеси го твојот број';

  @override
  String get phoneNumberCallerIdHint => 'Откако ќе се потврди, ова станува твој ID на повик';

  @override
  String get phoneNumberHint => 'Телефонски број';

  @override
  String get failedToStartVerification => 'Неуспешно стартување на верификација';

  @override
  String get phoneContinue => 'Продолжи';

  @override
  String get verifyYourNumber => 'Потврди го твојот број';

  @override
  String get answerTheCallFrom => 'Одговори на повикот од';

  @override
  String get onTheCallEnterThisCode => 'На повикот, внеси го овој код';

  @override
  String get followTheVoiceInstructions => 'Следи ги гласовните инструкции';

  @override
  String get statusCalling => 'Се повикува...';

  @override
  String get statusCallInProgress => 'Повик во тек';

  @override
  String get statusVerifiedLabel => 'Потврдено';

  @override
  String get statusCallMissed => 'Пропуштен повик';

  @override
  String get statusTimedOut => 'Истекло време';

  @override
  String get phoneTryAgain => 'Пробај повторно';

  @override
  String get phonePageTitle => 'Телефон';

  @override
  String get phoneContactsTab => 'Контакти';

  @override
  String get phoneKeypadTab => 'Табела со броеви';

  @override
  String get grantContactsAccess => 'Дозволи пристап до твоите контакти';

  @override
  String get phoneAllow => 'Дозволи';

  @override
  String get phoneSearchHint => 'Пребарај';

  @override
  String get phoneNoContactsFound => 'Нема пронајдени контакти';

  @override
  String get phoneEnterNumber => 'Внеси број';

  @override
  String get failedToStartCall => 'Неуспешно стартување на повик';

  @override
  String get callStateConnecting => 'Се поврзува...';

  @override
  String get callStateRinging => 'Се звони...';

  @override
  String get callStateEnded => 'Повик завршен';

  @override
  String get callStateFailed => 'Повик неуспешен';

  @override
  String get transcriptPlaceholder => 'Транскрипцијата ќе се појави овде...';

  @override
  String get phoneUnmute => 'Вклучи звук';

  @override
  String get phoneMute => 'Исклучи звук';

  @override
  String get phoneSpeaker => 'Глас';

  @override
  String get phoneEndCall => 'Завршена';

  @override
  String get phoneCallSettingsTitle => 'Поставки за телефонски разговор';

  @override
  String get showPhoneCallButtonTitle => 'Прикажи копче за повик';

  @override
  String get showPhoneCallButtonDesc => 'Прикажи копче за телефонски повик на почетниот екран';

  @override
  String get yourVerifiedNumbers => 'Твоите потврдени броеви';

  @override
  String get verifiedNumbersDescription => 'Кога ќе повикаш некој, тие ќе видат овој број на нивниот телефон';

  @override
  String get noVerifiedNumbers => 'Нема потврдени броеви';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Избриши $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Мораш повторно да верификуваш за да направиш повици';

  @override
  String get phoneDeleteButton => 'Избриши';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Потврдено ${minutes}m поради';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Потврдено ${hours}h поради';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Потврдено ${days}d поради';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Потврдено на $date';
  }

  @override
  String get verifiedFallback => 'Потврдено';

  @override
  String get callAlreadyInProgress => 'Веќе е во тек повик';

  @override
  String get failedToGetCallToken => 'Неуспешно добивање на жетон за повик. Прво потврди го твојот телефонски број.';

  @override
  String get failedToInitializeCallService => 'Неуспешна иницијализација на услуга за повици';

  @override
  String get speakerLabelYou => 'Ти';

  @override
  String get speakerLabelUnknown => 'Непознато';

  @override
  String get showDailyScoreOnHomepage => 'Прикажи дневна оценка на почетната страница';

  @override
  String get showTasksOnHomepage => 'Прикажи задачи на почетната страница';

  @override
  String get phoneCallsUnlimitedOnly => 'Телефонски разговори преку Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Направи повици преку Omi и добиј транскрипција во реално време, автоматски резимеја и многу повеќе. Достапно исклучиво за претплатници на Unlimited план.';

  @override
  String get phoneCallsUpsellFeature1 => 'Транскрипција во реално време на секој повик';

  @override
  String get phoneCallsUpsellFeature2 => 'Автоматски резимеја на повици и ставки за дејствување';

  @override
  String get phoneCallsUpsellFeature3 => 'Примачите го видат твојот вистински број, а не случаен';

  @override
  String get phoneCallsUpsellFeature4 => 'Твоите повици останувач приватни и безбедни';

  @override
  String get phoneCallsUpgradeButton => 'Надгради на Unlimited';

  @override
  String get phoneCallsMaybeLater => 'Можеби подоцна';

  @override
  String get deleteSynced => 'Избриши синхронизирано';

  @override
  String get deleteSyncedFiles => 'Избриши синхронизирани записи';

  @override
  String get deleteSyncedFilesMessage =>
      'Овие записи веќе се синхронизирани на твојот телефон. Ова не може да се откаже.';

  @override
  String get syncedFilesDeleted => 'Синхронизирани записи избришани';

  @override
  String get deletePending => 'Избриши во очекување';

  @override
  String get deletePendingFiles => 'Избриши записи во очекување';

  @override
  String get deletePendingFilesWarning =>
      'Овие записи НЕ се синхронизирани на твојот телефон и трајно ќе се изгубат. Ова не може да се откаже.';

  @override
  String get pendingFilesDeleted => 'Записи во очекување избришани';

  @override
  String get deleteAllFiles => 'Избриши ги сите записи';

  @override
  String get deleteAll => 'Избриши сите';

  @override
  String get deleteAllFilesWarning =>
      'Ќе ги избришеш и синхронизираните и записите во очекување. Записите во очекување НЕ се синхронизирани и трајно ќе се изгубат. Ова не може да се откаже.';

  @override
  String get allFilesDeleted => 'Сите записи избришани';

  @override
  String nFiles(int count) {
    return '$count записи';
  }

  @override
  String get manageStorage => 'Управување со складирање';

  @override
  String get safelyBackedUp => 'Безбедно резервирано на твојот телефон';

  @override
  String get notYetSynced => 'Сé уште не е синхронизирано на твојот телефон';

  @override
  String get clearAll => 'Исчисти сё';

  @override
  String get phoneKeypad => 'Табела со броеви';

  @override
  String get phoneHideKeypad => 'Скрии ја табелата со броеви';

  @override
  String get fairUsePolicy => 'Правично користење';

  @override
  String get fairUseLoadError => 'Неможам да го учитам статусот на правично користење. Пробај повторно.';

  @override
  String get fairUseStatusNormal => 'Твојата употреба е во нормални граници.';

  @override
  String get fairUseStageNormal => 'Нормално';

  @override
  String get fairUseStageWarning => 'Предупредување';

  @override
  String get fairUseStageThrottle => 'Ограничено';

  @override
  String get fairUseStageRestrict => 'Забранено';

  @override
  String get fairUseSpeechUsage => 'Употреба на говор';

  @override
  String get fairUseToday => 'Денес';

  @override
  String get fairUse3Day => '3-дневен намотување';

  @override
  String get fairUseWeekly => 'Неделна намотување';

  @override
  String get fairUseAboutTitle => 'За правично користење';

  @override
  String get fairUseAboutBody =>
      'Omi е дизајнирана за лични разговори, состаноци и живи интеракции. Употребата се мери по вистински детектиран говор време, а не по време на поврзување. Доколку употребата значајно надминува нормални обрасци за не-лично содржување, прилагодување може да се примени.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef копирано';
  }

  @override
  String get fairUseDailyTranscription => 'Дневна транскрипција';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'Дневна граница на транскрипција достигната';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Рестартирање $time';
  }

  @override
  String get transcriptionPaused => 'Снимање, повторна поврзување';

  @override
  String get transcriptionPausedReconnecting => 'Сè уште снима — повторна поврзување на транскрипција...';

  @override
  String fairUseBannerStatus(String status) {
    return 'Правично користење: $status';
  }

  @override
  String get improveConnectionTitle => 'Подобри врска';

  @override
  String get improveConnectionContent =>
      'Подобривме како Omi останува поврзана со твојот уред. За да го активираш ова, молиме оди на страницата Device Info, допри \"Откачи уред\" и потоа спарај го твојот уред повторно.';

  @override
  String get improveConnectionAction => 'Разбирам';

  @override
  String clockSkewWarning(int minutes) {
    return 'Часовникот на твојот уред е оделен за ~$minutes мин. Проверка на твоите поставки за датум и време.';
  }

  @override
  String get omisStorage => 'Складирање на Omi';

  @override
  String get phoneStorage => 'Складирање на телефон';

  @override
  String get cloudStorage => 'Облачно складирање';

  @override
  String get howSyncingWorks => 'Како функционира синхронизирањето';

  @override
  String get noSyncedRecordings => 'Нема синхронизирани записи сё уште';

  @override
  String get recordingsSyncAutomatically => 'Записите се синхронизираат автоматски — нема потреба за дејствување.';

  @override
  String get filesDownloadedUploadedNextTime => 'Датотеки веќе преземени ќе бидат ископани следниот пат.';

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
  String get tapToView => 'Допри за преглед';

  @override
  String get syncFailed => 'Синхронизирање неуспешно';

  @override
  String get keepSyncing => 'Продолжи синхронизирање';

  @override
  String get cancelSyncQuestion => 'Откажи синхронизирање?';

  @override
  String get omisStorageDesc =>
      'Кога твојот Omi не е поврзан на твојот телефон, тој складира звук локално на неговата вградена меморија. Никогаш не теглиш запис.';

  @override
  String get phoneStorageDesc =>
      'Кога Omi се повторно поврзе, записите се автоматски пренесуваат на твојот телефон како привремена облас за ископување пред ископување.';

  @override
  String get cloudStorageDesc =>
      'Откако ќе ги ископаш, твоите записи се обработуваат и транскрибираат. Разговорите ќе бидат достапни во минута.';

  @override
  String get tipKeepPhoneNearby => 'Задржи го телефонот во близина за побрзо синхронизирање';

  @override
  String get tipStableInternet => 'Стабилна интернет брзина го забрзува облачното ископување';

  @override
  String get tipAutoSync => 'Записите се синхронизираат автоматски';

  @override
  String get storageSection => 'СКЛАДИРАЊЕ';

  @override
  String get permissions => 'Дозволи';

  @override
  String get permissionEnabled => 'Дозволено';

  @override
  String get permissionEnable => 'Дозволи';

  @override
  String get permissionsPageDescription =>
      'Овие дозволи се основни за тоа како функционира Omi. Тие овозможуваат клучни функции како известувања, локациски искуства и снимање звук.';

  @override
  String get permissionsRequiredDescription =>
      'Omi има потреба од неколку дозволи за правилна работа. Молиме дозволи им да продолжи.';

  @override
  String get permissionsSetupTitle => 'Добиј најдобро искуство';

  @override
  String get permissionsSetupDescription => 'Дозволи неколку дозволи за да Omi може да ја направи своја магија.';

  @override
  String get permissionsChangeAnytime => 'Можеш да ги смениш овие било кога во Поставки > Дозволи';

  @override
  String get location => 'Локација';

  @override
  String get microphone => 'Микрофон';

  @override
  String get whyAreYouCanceling => 'Зошто го отказуваш?';

  @override
  String get cancelReasonSubtitle => 'Можеш ли да ни кажеш зошто го напушташ?';

  @override
  String get cancelReasonTooExpensive => 'Прескупо';

  @override
  String get cancelReasonNotUsing => 'Не го користам доволно';

  @override
  String get cancelReasonMissingFeatures => 'Недостасуваат функции';

  @override
  String get cancelReasonAudioQuality => 'Квалитет на звук/транскрипција';

  @override
  String get cancelReasonBatteryDrain => 'Загрижености за исцрнување на батерија';

  @override
  String get cancelReasonFoundAlternative => 'Нашол нова алтернатива';

  @override
  String get cancelReasonOther => 'Друго';

  @override
  String get tellUsMore => 'Кажи нам повеќе (опционално)';

  @override
  String get cancelReasonDetailHint => 'Го ценимеме секоја повратна информација...';

  @override
  String get justAMoment => 'Чекај малку, молиме';

  @override
  String get cancelConsequencesSubtitle =>
      'Силно препорачуваме да ги истражиш твоите останатите опции наместо откажување.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Твојот план останува активен до $date. После тоа, ќе биш преместен на бесплатната верзија со ограничени функции.';
  }

  @override
  String get ifYouCancel => 'Доколку го отказеш:';

  @override
  String get cancelConsequenceNoAccess =>
      'Нема да го имаш неограничениот пристап на крајот на твојот период на плаќање.';

  @override
  String get cancelConsequenceBattery => '7x повеќе потрошување на батерија (обработка на уредот)';

  @override
  String get cancelConsequenceQuality => '30% пониска квалитет на транскрипција (модели на уредот)';

  @override
  String get cancelConsequenceDelay => '5-7 секунда задержување при обработка (модели на уредот)';

  @override
  String get cancelConsequenceSpeakers => 'Не може да ги идентификува говорниците.';

  @override
  String get confirmAndCancel => 'Потврди и откажи';

  @override
  String get cancelConsequencePhoneCalls => 'Нема транскрипција на телефонски разговори во реално време';

  @override
  String get feedbackTitleTooExpensive => 'Каква цена би ти одговорила?';

  @override
  String get feedbackTitleMissingFeatures => 'Кои функции ти недостасуваат?';

  @override
  String get feedbackTitleAudioQuality => 'Кои проблеми имаше?';

  @override
  String get feedbackTitleBatteryDrain => 'Кажи ни за проблемите со батеријата';

  @override
  String get feedbackTitleFoundAlternative => 'На што се пребрзуваш?';

  @override
  String get feedbackTitleNotUsing => 'Што би те довело да користиш повеќе Omi?';

  @override
  String get feedbackSubtitleTooExpensive => 'Твојата повратна информација ни помага да најдеме вистина рамнотежа.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Сé време градиме — ова ни помага да пристапиме.';

  @override
  String get feedbackSubtitleAudioQuality => 'Би сакале да разумеме што отиде наопако.';

  @override
  String get feedbackSubtitleBatteryDrain => 'Ово помага на нашиот хардверски тим да побољшава.';

  @override
  String get feedbackSubtitleFoundAlternative => 'Би сакале да научиме што те привлече.';

  @override
  String get feedbackSubtitleNotUsing => 'Сакаме да го направиме Omi полезен за тебе.';

  @override
  String get deviceDiagnostics => 'Дијагностика на уред';

  @override
  String get signalStrength => 'Јачина на сигнал';

  @override
  String get connectionUptime => 'Време на активност';

  @override
  String get reconnections => 'Повторни поврзувања';

  @override
  String get disconnectHistory => 'Историја на разединување';

  @override
  String get noDisconnectsRecorded => 'Нема запишани разединувања';

  @override
  String get diagnostics => 'Дијагностика';

  @override
  String get waitingForData => 'Чекање на податоци...';

  @override
  String get liveRssiOverTime => 'Жива RSSI временски тек';

  @override
  String get noRssiDataYet => 'Нема RSSI податоци сё уште';

  @override
  String get collectingData => 'Собирање податоци...';

  @override
  String get cleanDisconnect => 'Чисто разединување';

  @override
  String get connectionTimeout => 'Истекло време на врска';

  @override
  String get remoteDeviceTerminated => 'Далечинскиот уред е прекинат';

  @override
  String get pairedToAnotherPhone => 'Спарено со друг телефон';

  @override
  String get linkKeyMismatch => 'Неусклад на клучот на врска';

  @override
  String get connectionFailed => 'Врска неуспешна';

  @override
  String get appClosed => 'Апликацијата е затворена';

  @override
  String get manualDisconnect => 'Рачно разединување';

  @override
  String lastNEvents(int count) {
    return 'Последни $count настани';
  }

  @override
  String get signal => 'Сигнал';

  @override
  String get battery => 'Батерија';

  @override
  String get excellent => 'Одличен';

  @override
  String get good => 'Добар';

  @override
  String get fair => 'Одличен';

  @override
  String get weak => 'Слаб';

  @override
  String gattError(String code) {
    return 'GATT грешка ($code)';
  }

  @override
  String get batteryHistory => 'Батерија';

  @override
  String get noBatteryDataYet => 'Сè уште нема податоци за батеријата';

  @override
  String get day => 'Ден';

  @override
  String get week => 'Седмица';

  @override
  String get rollbackToStableFirmware => 'Врати се на стабилен фирмвер';

  @override
  String get rollbackConfirmTitle => 'Враќање на фирмвер?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Ова ќе ја замени твојата тековна фирмвер со најновата стабилна верзија ($version). Твојот уред ќе се рестартира после ажурирањето.';
  }

  @override
  String get stableFirmware => 'Стабилен фирмвер';

  @override
  String get fetchingStableFirmware => 'Преземање на најновиот стабилен фирмвер...';

  @override
  String get noStableFirmwareFound => 'Неможам да најде стабилна верзија на фирмвер за твојот уред.';

  @override
  String get installStableFirmware => 'Инсталирај стабилен фирмвер';

  @override
  String get alreadyOnStableFirmware => 'Веќе си на најновата стабилна верзија.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration звук сачуван локално';
  }

  @override
  String get willSyncAutomatically => 'ќе се синхронизира автоматски';

  @override
  String get enableLocationTitle => 'Дозволи локација';

  @override
  String get enableLocationDescription => 'Дозвола за локација е потребна за пронаоѓање на близу Bluetooth уреди.';

  @override
  String get voiceRecordingFound => 'Запис пронајден';

  @override
  String get transcriptionConnecting => 'Поврзување на транскрипција...';

  @override
  String get transcriptionReconnecting => 'Повторна поврзување на транскрипција...';

  @override
  String get transcriptionUnavailable => 'Транскрипција недостапна';

  @override
  String get audioOutput => 'Звучен излез';

  @override
  String get firmwareWarningTitle => 'Важно: Прочитајте пред ажурирање';

  @override
  String get firmwareFormatWarning =>
      'Овој фирмвер ќе ја форматира SD картичката. Ве молиме осигурајте се дека сите офлајн податоци се синхронизирани пред надградба.\n\nАко видите трепкачко црвено светло по инсталирањето на оваа верзија, не грижете се. Едноставно поврзете го уредот со апликацијата и треба да стане сино. Црвеното светло значи дека часовникот на уредот сè уште не е синхронизиран.';

  @override
  String get continueAnyway => 'Продолжи';

  @override
  String get tasksClearCompleted => 'Исчисти завршени';

  @override
  String get tasksSelectAll => 'Избери сè';

  @override
  String tasksDeleteSelected(int count) {
    return 'Избриши $count задача(и)';
  }

  @override
  String get tasksMarkComplete => 'Означено како завршено';

  @override
  String get appleHealthManageNote =>
      'Omi пристапува до Apple Health преку HealthKit рамката на Apple. Пристапот можете да го повлечете во секое време во поставките на iOS.';

  @override
  String get appleHealthConnectCta => 'Поврзи со Apple Health';

  @override
  String get appleHealthDisconnectCta => 'Прекини врска со Apple Health';

  @override
  String get appleHealthConnectedBadge => 'Поврзано';

  @override
  String get appleHealthFeatureChatTitle => 'Разговарајте за своето здравје';

  @override
  String get appleHealthFeatureChatDesc => 'Прашајте го Omi за вашите чекори, сон, срцев ритам и тренинзи.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Пристап само за читање';

  @override
  String get appleHealthFeatureReadOnlyDesc =>
      'Omi никогаш не запишува во Apple Health и не ги менува вашите податоци.';

  @override
  String get appleHealthFeatureSecureTitle => 'Безбедна синхронизација';

  @override
  String get appleHealthFeatureSecureDesc => 'Вашите Apple Health податоци приватно се синхронизираат со Omi сметката.';

  @override
  String get appleHealthDeniedTitle => 'Пристапот до Apple Health е одбиен';

  @override
  String get appleHealthDeniedBody =>
      'Omi нема дозвола да ги чита вашите Apple Health податоци. Овозможете го во iOS Поставки → Приватност и безбедност → Health → Omi.';

  @override
  String get deleteFlowReasonTitle => 'Зошто си одите?';

  @override
  String get deleteFlowReasonSubtitle => 'Вашите повратни информации ни помагаат да го подобриме Omi за сите.';

  @override
  String get deleteReasonPrivacy => 'Грижи за приватноста';

  @override
  String get deleteReasonNotUsing => 'Не го користам доволно често';

  @override
  String get deleteReasonMissingFeatures => 'Недостасуваат функции што ми се потребни';

  @override
  String get deleteReasonTechnicalIssues => 'Премногу технички проблеми';

  @override
  String get deleteReasonFoundAlternative => 'Користам нешто друго';

  @override
  String get deleteReasonTakingBreak => 'Само правам пауза';

  @override
  String get deleteReasonOther => 'Друго';

  @override
  String get deleteFlowFeedbackTitle => 'Кажете ни повеќе';

  @override
  String get deleteFlowFeedbackSubtitle => 'Што би направило Omi да работи за вас?';

  @override
  String get deleteFlowFeedbackHint => 'Опционално — вашите мисли ни помагаат да изградиме подобар производ.';

  @override
  String get deleteFlowConfirmTitle => 'Ова е трајно';

  @override
  String get deleteFlowConfirmSubtitle => 'Откако ќе ја избришете сметката, не може да се врати.';

  @override
  String get deleteConsequenceSubscription => 'Секоја активна претплата ќе биде откажана.';

  @override
  String get deleteConsequenceNoRecovery => 'Вашата сметка не може да се обнови — ниту од поддршката.';

  @override
  String get deleteTypeToConfirm => 'Внесете DELETE за потврда';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'Трајно избриши ја сметката';

  @override
  String get keepMyAccount => 'Задржи ја мојата сметка';

  @override
  String get deleteAccountFailed => 'Не успеавме да ја избришеме вашата сметка. Обидете се повторно.';

  @override
  String get planUpdate => 'Ажурирање на планот';

  @override
  String get planDeprecationMessage =>
      'Вашиот Unlimited план се укинува. Преминете на Operator план — истите одлични функции за \$49/мес. Вашиот тековен план ќе продолжи да работи во меѓувреме.';

  @override
  String get upgradeYourPlan => 'Надградете го вашиот план';

  @override
  String get youAreOnAPaidPlan => 'Вие сте на платен план.';

  @override
  String get chatTitle => 'Чат';

  @override
  String get chatMessages => 'пораки';

  @override
  String get unlimitedChatThisMonth => 'Неограничени пораки овој месец';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used од $limit буџет за пресметка искористен';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used од $limit пораки искористени овој месец';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit искористено';
  }

  @override
  String get chatLimitReachedUpgrade => 'Лимитот за чат е достигнат. Надградете за повеќе пораки.';

  @override
  String get chatLimitReachedTitle => 'Лимитот за чат е достигнат';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Искористивте $used од $limitDisplay на планот $plan.';
  }

  @override
  String resetsInDays(int count) {
    return 'Се ресетира за $count дена';
  }

  @override
  String resetsInHours(int count) {
    return 'Се ресетира за $count часа';
  }

  @override
  String get resetsSoon => 'Наскоро се ресетира';

  @override
  String get upgradePlan => 'Надгради план';

  @override
  String get billingMonthly => 'Месечно';

  @override
  String get billingYearly => 'Годишно';

  @override
  String get savePercent => 'Заштедете ~17%';

  @override
  String get popular => 'Популарно';

  @override
  String get currentPlan => 'Тековен';

  @override
  String neoSubtitle(int count) {
    return '$count прашања месечно';
  }

  @override
  String operatorSubtitle(int count) {
    return '$count прашања месечно';
  }

  @override
  String get architectSubtitle => 'Напреден AI — илјадници разговори + агентна автоматизација';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Разговор: \$$used / \$$limit искористено овој месец';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Разговор: \$$used искористено овој месец';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Разговор: $used / $limit пораки овој месец';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Разговор: $used пораки овој месец';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'Го достигнавте вашиот месечен лимит. Надградете за да продолжите да разговарате со Omi без ограничувања.';

  @override
  String get voiceResponseAudio => 'Прочитај го одговорот на Omi гласно';

  @override
  String get voiceResponseMode => 'Гласовен одговор';

  @override
  String get voiceResponseModeTitle => 'Кога да се изговараат одговорите';

  @override
  String get voiceResponseOff => 'Исклучено';

  @override
  String get voiceResponseHeadphonesOnly => 'Само слушалки';

  @override
  String get voiceResponseAlways => 'Секогаш';

  @override
  String get agreeAndContinue => 'Се согласувам и продолжи';

  @override
  String get startVoiceRecording => 'Започни гласовно снимање';

  @override
  String get startCallRecording => 'Започни снимање повик';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'Гласовен режим';

  @override
  String get quickActionAskOmi => 'Прашајте го Omi за сè';

  @override
  String get record => 'Сними';

  @override
  String get stop => 'Стоп';

  @override
  String get recordWithPhoneMic => 'Снимај со микрофон на телефонот';

  @override
  String get recordWithPhoneMicSubtitle => 'Снимајте звук околу вас';

  @override
  String get phoneCall => 'Телефонски повик';

  @override
  String get phoneCallSubtitle => 'Снимајте повик со транскрипција во живо';

  @override
  String get searchActionItems => 'Пребарај акциски ставки';

  @override
  String get selectActionItems => 'Избери повеќе';

  @override
  String chooseExportDestination(int count) {
    return 'Извези $count ставка/и во…';
  }

  @override
  String get bulkExportInProgress => 'Извезување…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Извезени $count во $platform';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Извезени $success од $total во $platform';
  }

  @override
  String get showCompletedTasks => 'Прикажи завршени';

  @override
  String get hideCompletedTasks => 'Сокриј завршени';

  @override
  String get selectAllTasksMenu => 'Избери ги сите';

  @override
  String get connectTaskAppToExport => 'Поврзете апликација за задачи во Поставки за извоз';

  @override
  String get connectAction => 'Поврзи';

  @override
  String get deselectAllTasksMenu => 'Одселектирај ги сите';
}
