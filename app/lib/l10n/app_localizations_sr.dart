// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Serbian (`sr`).
class AppLocalizationsSr extends AppLocalizations {
  AppLocalizationsSr([String locale = 'sr']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Разговор';

  @override
  String get transcriptTab => 'Препис';

  @override
  String get actionItemsTab => 'Задаци';

  @override
  String get deleteConversationTitle => 'Обрисати разговор?';

  @override
  String get deleteConversationMessage =>
      'Ово ће такође обрисати повезане успомене, задатке и аудио датотеке. Ова радња се не може отказати.';

  @override
  String get confirm => 'Потврди';

  @override
  String get cancel => 'Отказ';

  @override
  String get ok => 'Ок';

  @override
  String get delete => 'Обриши';

  @override
  String get add => 'Додај';

  @override
  String get update => 'Ажурирај';

  @override
  String get save => 'Сачувај';

  @override
  String get edit => 'Уреди';

  @override
  String get close => 'Затвори';

  @override
  String get clear => 'Очисти';

  @override
  String get copyTranscript => 'Копирај препис';

  @override
  String get copySummary => 'Копирај садржај';

  @override
  String get testPrompt => 'Тестирај подстицај';

  @override
  String get reprocessConversation => 'Поново обради разговор';

  @override
  String get deleteConversation => 'Обриши разговор';

  @override
  String get contentCopied => 'Садржај скопиран у привремену меморију';

  @override
  String get failedToUpdateStarred => 'Неуспешно ажурирање статуса звезде.';

  @override
  String get conversationUrlNotShared => 'URL разговора се не може делити.';

  @override
  String get errorProcessingConversation => 'Грешка при обради разговора. Молим вас, покушајте касније.';

  @override
  String get noInternetConnection => 'Нема интернет повезаности';

  @override
  String get unableToDeleteConversation => 'Није могуће обрисати разговор';

  @override
  String get somethingWentWrong => 'Нешто је пошло наопако! Молим вас, покушајте касније.';

  @override
  String get copyErrorMessage => 'Копирај поруку о грешци';

  @override
  String get errorCopied => 'Порука о грешци скопирана у привремену меморију';

  @override
  String get remaining => 'Преостало';

  @override
  String get loading => 'Учитавање...';

  @override
  String get loadingDuration => 'Учитавање трајања...';

  @override
  String secondsCount(int count) {
    return '$count секунди';
  }

  @override
  String get people => 'Људи';

  @override
  String get addNewPerson => 'Додај нову особу';

  @override
  String get editPerson => 'Уреди особу';

  @override
  String get createPersonHint => 'Направи нову особу и обучи Omi да препознаје њихов глас!';

  @override
  String get speechProfile => 'Профил говора';

  @override
  String sampleNumber(int number) {
    return 'Узорак $number';
  }

  @override
  String get settings => 'Подешавања';

  @override
  String get language => 'Језик';

  @override
  String get selectLanguage => 'Изаберите језик';

  @override
  String get deleting => 'Брисање...';

  @override
  String get pleaseCompleteAuthentication =>
      'Молим вас, завршите аутентификацију у својој прегледачу. Када завршите, вратите се у апликацију.';

  @override
  String get failedToStartAuthentication => 'Неуспешан почетак аутентификације';

  @override
  String get importStarted => 'Увоз почет! Бићете обавештени када је готово.';

  @override
  String get failedToStartImport => 'Неуспешан почетак увоза. Молим вас, покушајте поново.';

  @override
  String get couldNotAccessFile => 'Није могуће приступити одабраној датотеци';

  @override
  String get askOmi => 'Питај Omi';

  @override
  String get done => 'Готово';

  @override
  String get disconnected => 'Прекинута повезаност';

  @override
  String get searching => 'Претраживање...';

  @override
  String get connectDevice => 'Повежи уређај';

  @override
  String get monthlyLimitReached => 'Достигли сте месечни лимит.';

  @override
  String get checkUsage => 'Проверите употребу';

  @override
  String get syncingRecordings => 'Синхронизовање снимака';

  @override
  String get recordingsToSync => 'Снимци за синхронизовање';

  @override
  String get allCaughtUp => 'Све је правилно';

  @override
  String get sync => 'Синхронизуј';

  @override
  String get pendantUpToDate => 'Привесак је ажуриран';

  @override
  String get allRecordingsSynced => 'Сви снимци су синхронизовани';

  @override
  String get syncingInProgress => 'Синхронизовање је у току';

  @override
  String get readyToSync => 'Спремно за синхронизовање';

  @override
  String get tapSyncToStart => 'Додирни Синхронизуј да почнеш';

  @override
  String get pendantNotConnected => 'Привесак није повезан. Повежи се да синхронизуеш.';

  @override
  String get everythingSynced => 'Све је већ синхронизовано.';

  @override
  String get recordingsNotSynced => 'Имате снимке који нису још синхронизовани.';

  @override
  String get syncingBackground => 'Наставићемо да синхронизујемо ваше снимке у позадини.';

  @override
  String get noConversationsYet => 'Нема разговора';

  @override
  String get noStarredConversations => 'Нема означених разговора';

  @override
  String get starConversationHint => 'Да означиш разговор, отвори га и додирни икону звезде у заглављу.';

  @override
  String get searchConversations => 'Претражи разговоре...';

  @override
  String selectedCount(int count, Object s) {
    return '$count изабрано';
  }

  @override
  String get merge => 'Спаја';

  @override
  String get mergeConversations => 'Спаја разговоре';

  @override
  String mergeConversationsMessage(int count) {
    return 'Ово ће комбиновати $count разговора у један. Сав садржај ће бити спојен и регенерисан.';
  }

  @override
  String get mergingInBackground => 'Спајање у позадини. Ово може потрајати.';

  @override
  String get failedToStartMerge => 'Неуспешан почетак спајања';

  @override
  String get askAnything => 'Питај шта год';

  @override
  String get noMessagesYet => 'Нема поруга до сада!\nЗашто не почнеш разговор?';

  @override
  String get deletingMessages => 'Брисање твоих порука из Omi-јеве меморије...';

  @override
  String get messageCopied => '✨ Порука скопирана у привремену меморију';

  @override
  String get cannotReportOwnMessage => 'Не можеш пријавити своје поруке.';

  @override
  String get reportMessage => 'Пријави поруку';

  @override
  String get reportMessageConfirm => 'Да ли сте сигурни да желите пријавити ову поруку?';

  @override
  String get messageReported => 'Порука успешно пријављена.';

  @override
  String get thankYouFeedback => 'Хвала вам на повратној информацији!';

  @override
  String get clearChat => 'Очисти разговор';

  @override
  String get clearChatConfirm => 'Да ли сте сигурни да желите очистити разговор? Ова радња се не може отказати.';

  @override
  String get maxFilesLimit => 'Можете учитати само 4 датотеке одједном';

  @override
  String get chatWithOmi => 'Разговарај са Omi';

  @override
  String get apps => 'Апликације';

  @override
  String get noAppsFound => 'Нема пронађених апликација';

  @override
  String get tryAdjustingSearch => 'Покушајте да прилагодите претрагу или филтере';

  @override
  String get createYourOwnApp => 'Направи своју апликацију';

  @override
  String get buildAndShareApp => 'Направи и дели своју прилагођену апликацију';

  @override
  String get searchApps => 'Претражи апликације...';

  @override
  String get myApps => 'Моје апликације';

  @override
  String get installedApps => 'Инсталиране апликације';

  @override
  String get unableToFetchApps =>
      'Није могуће добити апликације :(\n\nМолим вас, проверите вашу интернет повезаност и покушајте поново.';

  @override
  String get aboutOmi => 'О Omi';

  @override
  String get privacyPolicy => 'Политика приватности';

  @override
  String get visitWebsite => 'Посетите веб страницу';

  @override
  String get helpOrInquiries => 'Помоћ или упитивања?';

  @override
  String get joinCommunity => 'Придружи се заједници!';

  @override
  String get membersAndCounting => '8000+ чланова и наставља се.';

  @override
  String get deleteAccountTitle => 'Обриши налог';

  @override
  String get deleteAccountConfirm => 'Да ли сте сигурни да желите обрисати свој налог?';

  @override
  String get cannotBeUndone => 'Ово се не може отказати.';

  @override
  String get allDataErased => 'Све ваше успомене и разговори ће бити трајно обрисани.';

  @override
  String get appsDisconnected => 'Ваше апликације и интеграције ће бити одмах одсоединене.';

  @override
  String get exportBeforeDelete =>
      'Можете извезти своје податке пре брисања налога, али када буду обрисани, не могу се опоравити.';

  @override
  String get deleteAccountCheckbox =>
      'Разумем да је брисање мог налога трајно и сви подаци, укључујући успомене и разговоре, биће изгубљени и не могу се опоравити.';

  @override
  String get areYouSure => 'Да ли сте сигурни?';

  @override
  String get deleteAccountFinal =>
      'Ова радња је неповратна и трајно ће обрисати ваш налог и све повезане податке. Да ли сте сигурни да желите да наставите?';

  @override
  String get deleteNow => 'Обриши сада';

  @override
  String get goBack => 'Назад';

  @override
  String get checkBoxToConfirm => 'Означи поље да потврдиш да разумеш да је брисање налога трајно и неповратно.';

  @override
  String get profile => 'Профил';

  @override
  String get name => 'Име';

  @override
  String get email => 'Имејл';

  @override
  String get customVocabulary => 'Прилагођени вокабулар';

  @override
  String get identifyingOthers => 'Препознавање других';

  @override
  String get paymentMethods => 'Методе плаћања';

  @override
  String get conversationDisplay => 'Приказ разговора';

  @override
  String get dataPrivacy => 'Приватност података';

  @override
  String get userId => 'Корисник ID';

  @override
  String get notSet => 'Није постављено';

  @override
  String get userIdCopied => 'Корисник ID скопиран у привремену меморију';

  @override
  String get systemDefault => 'Подразумевана системска подешавања';

  @override
  String get planAndUsage => 'План и употреба';

  @override
  String get offlineSync => 'Синхронизовање без интернета';

  @override
  String get deviceSettings => 'Подешавања уређаја';

  @override
  String get integrations => 'Интеграције';

  @override
  String get feedbackBug => 'Повратна информација / Грешка';

  @override
  String get helpCenter => 'Центар за помоћ';

  @override
  String get developerSettings => 'Подешавања разработача';

  @override
  String get getOmiForMac => 'Преузмите Omi за Mac';

  @override
  String get referralProgram => 'Програм препоруке';

  @override
  String get signOut => 'Одјави се';

  @override
  String get appAndDeviceCopied => 'Детаљи апликације и уређаја скопирани';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Твоја приватност, твоја контрола';

  @override
  String get privacyIntro =>
      'На Omi, посвећени смо заштити ваше приватности. Ова страница вам омогућава да контролишете како се ваши подаци чувају и користе.';

  @override
  String get learnMore => 'Сазнајте више...';

  @override
  String get dataProtectionLevel => 'Ниво заштите података';

  @override
  String get dataProtectionDesc =>
      'Ваши подаци су подразумевано заштићени јаким шифровањем. Прегледајте своја подешавања и будуће опције приватности испод.';

  @override
  String get appAccess => 'Приступ апликације';

  @override
  String get appAccessDesc =>
      'Следеће апликације могу приступити вашим подацима. Додирни апликацију да управљаш њеним дозволама.';

  @override
  String get noAppsExternalAccess => 'Ниједна инсталирана апликација нема спољни приступ вашим подацима.';

  @override
  String get deviceName => 'Име уређаја';

  @override
  String get deviceId => 'Уређај ID';

  @override
  String get firmware => 'Фирмвер';

  @override
  String get sdCardSync => 'Синхронизовање SD картице';

  @override
  String get hardwareRevision => 'Ревизија хардвера';

  @override
  String get modelNumber => 'Број модела';

  @override
  String get manufacturer => 'Произвођач';

  @override
  String get doubleTap => 'Дупло додирни';

  @override
  String get ledBrightness => 'Сјајност LED';

  @override
  String get micGain => 'Дојачање микрофона';

  @override
  String get disconnect => 'Прекини повезаност';

  @override
  String get forgetDevice => 'Забави уређај';

  @override
  String get chargingIssues => 'Проблеми са пуњењем';

  @override
  String get disconnectDevice => 'Прекини повезаност уређаја';

  @override
  String get unpairDevice => 'Распари уређај';

  @override
  String get unpairAndForget => 'Распари и забави уређај';

  @override
  String get deviceDisconnectedMessage => 'Ваш Omi је прекинут 😔';

  @override
  String get deviceUnpairedMessage =>
      'Уређај је распарен. Идите на Подешавања > Bluetooth и забавите уређај да завршите распаривање.';

  @override
  String get unpairDialogTitle => 'Распари уређај';

  @override
  String get unpairDialogMessage =>
      'Ово ће распарити уређај тако да га можеш повезати са другим телефоном. Мораћеш да идеш на Подешавања > Bluetooth и забаву уређај да завршиш процес.';

  @override
  String get deviceNotConnected => 'Уређај није повезан';

  @override
  String get connectDeviceMessage => 'Повежи свој Omi уређај да приступиш\nподешавањима уређаја и прилагођавању';

  @override
  String get deviceInfoSection => 'Информације о уређају';

  @override
  String get customizationSection => 'Прилагођавање';

  @override
  String get hardwareSection => 'Хардвер';

  @override
  String get v2Undetected => 'V2 није детектован';

  @override
  String get v2UndetectedMessage =>
      'Видимо да имате V1 уређај или ваш уређај није повезан. Функционалност SD картице је доступна само за V2 уређаје.';

  @override
  String get endConversation => 'Заврши разговор';

  @override
  String get pauseResume => 'Паузирај/Наставак';

  @override
  String get starConversation => 'Означи разговор';

  @override
  String get doubleTapAction => 'Акција дуплог додира';

  @override
  String get endAndProcess => 'Заврши и обради разговор';

  @override
  String get pauseResumeRecording => 'Паузирај/Наставак снимања';

  @override
  String get starOngoing => 'Означи текући разговор';

  @override
  String get off => 'Искључено';

  @override
  String get max => 'Макс';

  @override
  String get mute => 'Утишај';

  @override
  String get quiet => 'Тихо';

  @override
  String get normal => 'Нормално';

  @override
  String get high => 'Високо';

  @override
  String get micGainDescMuted => 'Микрофон је утишан';

  @override
  String get micGainDescLow => 'Веома тихо - за бучну окружење';

  @override
  String get micGainDescModerate => 'Тихо - за умерену буку';

  @override
  String get micGainDescNeutral => 'Неутрално - балансирано снимање';

  @override
  String get micGainDescSlightlyBoosted => 'Благо дојачано - за нормалну употребу';

  @override
  String get micGainDescBoosted => 'Дојачано - за тиха окружења';

  @override
  String get micGainDescHigh => 'Високо - за удаљене или тихе гласове';

  @override
  String get micGainDescVeryHigh => 'Веома високо - за веома тихе изворе';

  @override
  String get micGainDescMax => 'Максимално - користи опрезно';

  @override
  String get developerSettingsTitle => 'Подешавања разработача';

  @override
  String get saving => 'Чување...';

  @override
  String get beta => 'БЕТА';

  @override
  String get transcription => 'Препис';

  @override
  String get transcriptionConfig => 'Конфигуриши STT добављача';

  @override
  String get conversationTimeout => 'Временски лимит разговора';

  @override
  String get conversationTimeoutConfig => 'Постави када се разговори аутоматски завршавају';

  @override
  String get importData => 'Увези податке';

  @override
  String get importDataConfig => 'Увези податке из других извора';

  @override
  String get debugDiagnostics => 'Дебаговање и дијагностика';

  @override
  String get endpointUrl => 'URL крајње тачке';

  @override
  String get noApiKeys => 'Нема API кључева';

  @override
  String get createKeyToStart => 'Направи кључ да почнеш';

  @override
  String get createKey => 'Направи кључ';

  @override
  String get docs => 'Документација';

  @override
  String get yourOmiInsights => 'Твоји Omi увиди';

  @override
  String get today => 'Данас';

  @override
  String get thisMonth => 'Овог месеца';

  @override
  String get thisYear => 'Ове године';

  @override
  String get allTime => 'Свих времена';

  @override
  String get noActivityYet => 'Нема активности';

  @override
  String get startConversationToSeeInsights => 'Почни разговор са Omi\nда видиш своје увиде у употреби овде.';

  @override
  String get listening => 'Слушање';

  @override
  String get listeningSubtitle => 'Укупно време Omi је активно слушао.';

  @override
  String get understanding => 'Разумевање';

  @override
  String get understandingSubtitle => 'Речи разумене из твоих разговора.';

  @override
  String get providing => 'Пружање';

  @override
  String get providingSubtitle => 'Задаци и напомене аутоматски ухваћени.';

  @override
  String get remembering => 'Памћење';

  @override
  String get rememberingSubtitle => 'Чињенице и детаљи запамћени за тебе.';

  @override
  String get unlimitedPlan => 'Неограничен план';

  @override
  String get managePlan => 'Управљај планом';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Твој план ће бити отказан $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Твој план се обнавља $date.';
  }

  @override
  String get basicPlan => 'Бесплатан план';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used од $limit минута коришћено';
  }

  @override
  String get upgrade => 'Надогради';

  @override
  String get upgradeToUnlimited => 'Надогради на неограничено';

  @override
  String basicPlanDesc(int limit) {
    return 'Твој план укључује $limit бесплатних минута месечно. Надогради да иде неограничено.';
  }

  @override
  String get shareStatsMessage => 'Делим своје Omi статистике! (omi.me - твој алати-укључени AI асистент)';

  @override
  String get sharePeriodToday => 'Данас, omi има:';

  @override
  String get sharePeriodMonth => 'Овог месеца, omi има:';

  @override
  String get sharePeriodYear => 'Ове године, omi има:';

  @override
  String get sharePeriodAllTime => 'До сада, omi има:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Слушао за $minutes минута';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Разумео $words речи';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Пружио $count увида';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Запамтио $count успомена';
  }

  @override
  String get debugLogs => 'Дебаг логови';

  @override
  String get debugLogsAutoDelete => 'Аутоматски бриши после 3 дана.';

  @override
  String get debugLogsDesc => 'Помаже у дијагностицирању проблема';

  @override
  String get noLogFilesFound => 'Нема пронађених лог датотека.';

  @override
  String get omiDebugLog => 'Omi дебаг лог';

  @override
  String get logShared => 'Лог дељен';

  @override
  String get selectLogFile => 'Изабери лог датотеку';

  @override
  String get shareLogs => 'Дели логове';

  @override
  String get debugLogCleared => 'Дебаг лог очишћен';

  @override
  String get exportStarted => 'Извоз почет. Ово може потрајати неколико секунди...';

  @override
  String get exportAllData => 'Извези све податке';

  @override
  String get exportDataDesc => 'Извези разговоре у JSON датотеку';

  @override
  String get exportedConversations => 'Извезени разговори из Omi';

  @override
  String get exportShared => 'Извоз дељен';

  @override
  String get deleteKnowledgeGraphTitle => 'Обриши граф знања?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Ово ће обрисати све изведене податке графа знања (чворове и конекције). Ваше оригиналне успомене остају безбедне. Граф ће бити обновљен током времена или при следећем захтеву.';

  @override
  String get knowledgeGraphDeleted => 'Граф знања обрисан';

  @override
  String deleteGraphFailed(String error) {
    return 'Неуспешно брисање графа: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Обриши граф знања';

  @override
  String get deleteKnowledgeGraphDesc => 'Очисти све чворове и конекције';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP сервер';

  @override
  String get mcpServerDesc => 'Повежи AI асистенте са својим податцима';

  @override
  String get serverUrl => 'URL сервера';

  @override
  String get urlCopied => 'URL скопиран';

  @override
  String get apiKeyAuth => 'API кључ аутентификација';

  @override
  String get header => 'Заглавље';

  @override
  String get authorizationBearer => 'Ауторизација: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Client ID';

  @override
  String get clientSecret => 'Client Secret';

  @override
  String get useMcpApiKey => 'Користи твој MCP API кључ';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'События разговора';

  @override
  String get newConversationCreated => 'Нов разговор направљен';

  @override
  String get realtimeTranscript => 'Препис у реалном времену';

  @override
  String get transcriptReceived => 'Препис примљен';

  @override
  String get audioBytes => 'Аудио Bytes';

  @override
  String get audioDataReceived => 'Аудио подаци примљени';

  @override
  String get intervalSeconds => 'Интервал (секунди)';

  @override
  String get daySummary => 'Дневни садржај';

  @override
  String get summaryGenerated => 'Садржај генерисан';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Додај на claude_desktop_config.json';

  @override
  String get copyConfig => 'Копирај конфигурацију';

  @override
  String get configCopied => 'Конфигурација скопирана у привремену меморију';

  @override
  String get listeningMins => 'Слушање (минути)';

  @override
  String get understandingWords => 'Разумевање (речи)';

  @override
  String get insights => 'Увиди';

  @override
  String get memories => 'Успомене';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used од $limit минута коришћено овог месеца';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used од $limit речи коришћено овог месеца';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used од $limit увида стечено овог месеца';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used од $limit успомена направљено овог месеца';
  }

  @override
  String get visibility => 'Видљивост';

  @override
  String get visibilitySubtitle => 'Контролиши који разговори се приказују у твојој листи';

  @override
  String get showShortConversations => 'Прикажи кратке разговоре';

  @override
  String get showShortConversationsDesc => 'Прикажи разговоре краће од прага';

  @override
  String get showDiscardedConversations => 'Прикажи одбачене разговоре';

  @override
  String get showDiscardedConversationsDesc => 'Укључи разговоре означене као одбачени';

  @override
  String get shortConversationThreshold => 'Праг кратког разговора';

  @override
  String get shortConversationThresholdSubtitle =>
      'Разговори краћи од овога ће бити скривени осим ако су омогућени горе';

  @override
  String get durationThreshold => 'Праг трајања';

  @override
  String get durationThresholdDesc => 'Скриј разговоре краће од овога';

  @override
  String minLabel(int count) {
    return '$count мин';
  }

  @override
  String get customVocabularyTitle => 'Прилагођени вокабулар';

  @override
  String get addWords => 'Додај речи';

  @override
  String get addWordsDesc => 'Имена, термини или необични речи';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Повежи';

  @override
  String get comingSoon => 'Скоро доступно';

  @override
  String get integrationsFooter => 'Повежи своје апликације да видиш податке и метрике у разговору.';

  @override
  String get completeAuthInBrowser =>
      'Молим вас, завршите аутентификацију у својој прегледачу. Када завршите, вратите се у апликацију.';

  @override
  String failedToStartAuth(String appName) {
    return 'Неуспешан почетак аутентификације $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Прекини повезаност са $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Да ли сте сигурни да желите одсоединити од $appName? Можете се поново повезати било када.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Одсоединиран од $appName';
  }

  @override
  String get failedToDisconnect => 'Неуспешно отпајање';

  @override
  String connectTo(String appName) {
    return 'Повежи се на $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Требаћеш да овластиш Omi да приступи твоим $appName подацима. Ово ће отворити твој прегледач за аутентификацију.';
  }

  @override
  String get continueAction => 'Наставак';

  @override
  String get languageTitle => 'Језик';

  @override
  String get primaryLanguage => 'Главни језик';

  @override
  String get automaticTranslation => 'Аутоматски превод';

  @override
  String get detectLanguages => 'Открај 10+ језика';

  @override
  String get authorizeSavingRecordings => 'Овласти чување снимака';

  @override
  String get thanksForAuthorizing => 'Хвала што сте овластили!';

  @override
  String get needYourPermission => 'Требамо твоју дозволу';

  @override
  String get alreadyGavePermission =>
      'Већ си нам дао дозволу да чувамо твоје снимке. Ево подсетника зашто је то потребно:';

  @override
  String get wouldLikePermission => 'Желели бисмо твоју дозволу да чувамо твоје гласовне снимке. Ево зашто:';

  @override
  String get improveSpeechProfile => 'Побољшај свој профил говора';

  @override
  String get improveSpeechProfileDesc => 'Користимо снимке да додатно обучимо и побољшамо твој лични профил говора.';

  @override
  String get trainFamilyProfiles => 'Обучи профиле за пријатеље и породицу';

  @override
  String get trainFamilyProfilesDesc =>
      'Твоји снимци нам помажу да препознамо и направимо профиле за твоје пријатеље и породицу.';

  @override
  String get enhanceTranscriptAccuracy => 'Побољшај тачност преписа';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Како се наш модел побољшава, можемо пружити боље резултате преписа за твоје снимке.';

  @override
  String get legalNotice =>
      'Правна напомена: Законитост снимања и чувања гласовних података може варирати у зависности од твоје локације и како користиш ову функцију. Твоја је одговорност да обезбедиш усклађеност са локалним законима и прописима.';

  @override
  String get alreadyAuthorized => 'Већ овлашћен';

  @override
  String get authorize => 'Овласти';

  @override
  String get revokeAuthorization => 'Опозови овлаћење';

  @override
  String get authorizationSuccessful => 'Аутентификација успешна!';

  @override
  String get failedToAuthorize => 'Не могу да аутентификујем. Покушајте поново.';

  @override
  String get authorizationRevoked => 'Аутентификација је одозвана.';

  @override
  String get recordingsDeleted => 'Снимци су избрисани.';

  @override
  String get failedToRevoke => 'Не могу да одозовем аутентификацију. Покушајте поново.';

  @override
  String get permissionRevokedTitle => 'Дозвола је одозвана';

  @override
  String get permissionRevokedMessage => 'Да ли желите да избришемо све ваше постојеће снимке?';

  @override
  String get yes => 'Да';

  @override
  String get editName => 'Уреди име';

  @override
  String get howShouldOmiCallYou => 'Како да те Omi зове?';

  @override
  String get enterYourName => 'Унеси своје име';

  @override
  String get nameCannotBeEmpty => 'Име не може бити празно';

  @override
  String get nameUpdatedSuccessfully => 'Име је успешно ажурирано!';

  @override
  String get calendarSettings => 'Подешавања календара';

  @override
  String get calendarProviders => 'Добављачи календара';

  @override
  String get macOsCalendar => 'macOS календар';

  @override
  String get connectMacOsCalendar => 'Повежи локални macOS календар';

  @override
  String get googleCalendar => 'Google календар';

  @override
  String get syncGoogleAccount => 'Синхронизуј са Google налогом';

  @override
  String get showMeetingsMenuBar => 'Прикажи предстојеће састанке у траци менија';

  @override
  String get showMeetingsMenuBarDesc => 'Прикажи следећи састанак и време док почне у macOS траци менија';

  @override
  String get showEventsNoParticipants => 'Прикажи догађаје без учесника';

  @override
  String get showEventsNoParticipantsDesc =>
      'Када је омогућено, Coming Up приказује догађаје без учесника или видео линка.';

  @override
  String get yourMeetings => 'Ваши састанци';

  @override
  String get refresh => 'Освежи';

  @override
  String get noUpcomingMeetings => 'Нема предстојећих састанака';

  @override
  String get checkingNextDays => 'Проверавам следећих 30 дана';

  @override
  String get tomorrow => 'Сутра';

  @override
  String get googleCalendarComingSoon => 'Google календар интеграција ускоро!';

  @override
  String connectedAsUser(String userId) {
    return 'Повезан као корисник: $userId';
  }

  @override
  String get defaultWorkspace => 'Подразумевани радни простор';

  @override
  String get tasksCreatedInWorkspace => 'Задаци ће бити креирани у овом радном простору';

  @override
  String get defaultProjectOptional => 'Подразумевани пројекат (опционално)';

  @override
  String get leaveUnselectedTasks => 'Оставите неизабрано да креирате задатке без пројекта';

  @override
  String get noProjectsInWorkspace => 'Нису пронађени пројекти у овом радном простору';

  @override
  String get conversationTimeoutDesc =>
      'Одаберите колико дуго чекати у тишини пре него што аутоматски завршите разговор:';

  @override
  String get timeout2Minutes => '2 минута';

  @override
  String get timeout2MinutesDesc => 'Заврши разговор после 2 минута тишине';

  @override
  String get timeout5Minutes => '5 минута';

  @override
  String get timeout5MinutesDesc => 'Заврши разговор после 5 минута тишине';

  @override
  String get timeout10Minutes => '10 минута';

  @override
  String get timeout10MinutesDesc => 'Заврши разговор после 10 минута тишине';

  @override
  String get timeout30Minutes => '30 минута';

  @override
  String get timeout30MinutesDesc => 'Заврши разговор после 30 минута тишине';

  @override
  String get timeout4Hours => '4 часа';

  @override
  String get timeout4HoursDesc => 'Заврши разговор после 4 часа тишине';

  @override
  String get conversationEndAfterHours => 'Разговори ће сада завршити се после 4 часа тишине';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Разговори ће сада завршити се после $minutes минут(е) тишине';
  }

  @override
  String get tellUsPrimaryLanguage => 'Реци нам свој примарни језик';

  @override
  String get languageForTranscription => 'Постави језик за боље препознавање и персонализовано искуство.';

  @override
  String get singleLanguageModeInfo => 'Режим једног језика је омогућен. Превођење је онемогућено за већу тачност.';

  @override
  String get searchLanguageHint => 'Претражи језик по имену или коду';

  @override
  String get noLanguagesFound => 'Нису пронађени језици';

  @override
  String get skip => 'Прескочи';

  @override
  String languageSetTo(String language) {
    return 'Језик је постављен на $language';
  }

  @override
  String get failedToSetLanguage => 'Не могу да постави језик';

  @override
  String appSettings(String appName) {
    return '$appName подешавања';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Откачи се од $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Ово ће уклонити вашу $appName аутентификацију. Требаћете да се поново повежете да бисте је користили.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Повезан на $appName';
  }

  @override
  String get account => 'Налог';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Ваше задаци ће бити синхронизовани на ваш $appName налог';
  }

  @override
  String get defaultSpace => 'Подразумевани простор';

  @override
  String get selectSpaceInWorkspace => 'Одаберите простор у вашем радном простору';

  @override
  String get noSpacesInWorkspace => 'Нису пронађени простори у овом радном простору';

  @override
  String get defaultList => 'Подразумевана листа';

  @override
  String get tasksAddedToList => 'Задаци ће бити додати на ову листу';

  @override
  String get noListsInSpace => 'Нису пронађене листе у овом простору';

  @override
  String failedToLoadRepos(String error) {
    return 'Не могу да учитам складишта: $error';
  }

  @override
  String get defaultRepoSaved => 'Подразумевано складиште је сачувано';

  @override
  String get failedToSaveDefaultRepo => 'Не могу да сачувам подразумевано складиште';

  @override
  String get defaultRepository => 'Подразумевано складиште';

  @override
  String get selectDefaultRepoDesc =>
      'Одаберите подразумевано складиште за прављење проблема. Можете и даље одредити друго складиште при прављењу проблема.';

  @override
  String get noReposFound => 'Нису пронађена складишта';

  @override
  String get private => 'Приватно';

  @override
  String updatedDate(String date) {
    return 'Ажурирано $date';
  }

  @override
  String get yesterday => 'Јучер';

  @override
  String daysAgo(int count) {
    return 'пре $count дана';
  }

  @override
  String get oneWeekAgo => 'пре 1 недеље';

  @override
  String weeksAgo(int count) {
    return 'пре $count недеља';
  }

  @override
  String get oneMonthAgo => 'пре 1 месеца';

  @override
  String monthsAgo(int count) {
    return 'пре $count месеци';
  }

  @override
  String get issuesCreatedInRepo => 'Проблеми ће бити креирани у вашем подразуеваном складишту';

  @override
  String get taskIntegrations => 'Интеграције задатака';

  @override
  String get configureSettings => 'Подешавања';

  @override
  String get completeAuthBrowser =>
      'Молим вас, завршите аутентификацију у браузеру. Када завршите, вратите се у апликацију.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Не могу да почnem $appName аутентификацију';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Повежи се на $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Требаћете да аутентификујете Omi да креира задатке у вашем $appName налогу. Ово ће отворити браузер за аутентификацију.';
  }

  @override
  String get continueButton => 'Наставите';

  @override
  String appIntegration(String appName) {
    return '$appName интеграција';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Интеграција са $appName ускоро! Напорно радимо да вам донесемо више опција управљања задацима.';
  }

  @override
  String get gotIt => 'Разумем';

  @override
  String get tasksExportedOneApp => 'Задаци могу бити извезени на једну апликацију одједном.';

  @override
  String get completeYourUpgrade => 'Завршите унапређење';

  @override
  String get importConfiguration => 'Увоз конфигурације';

  @override
  String get exportConfiguration => 'Извоз конфигурације';

  @override
  String get bringYourOwn => 'Донесите своју';

  @override
  String get payYourSttProvider => 'Слободно користите omi. Плаћате само добављачу STT директно.';

  @override
  String get freeMinutesMonth => '1.200 слободних минута/месец укључено. Неограничено са ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Хост је обавезан';

  @override
  String get validPortRequired => 'Важећи порт је обавезан';

  @override
  String get validWebsocketUrlRequired => 'Важећи WebSocket URL је обавезан (wss://)';

  @override
  String get apiUrlRequired => 'API URL је обавезан';

  @override
  String get apiKeyRequired => 'API кључ је обавезан';

  @override
  String get invalidJsonConfig => 'Неважећа JSON конфигурација';

  @override
  String errorSaving(String error) {
    return 'Грешка при чувању: $error';
  }

  @override
  String get configCopiedToClipboard => 'Конфигурација је копирана у привремену меморију';

  @override
  String get pasteJsonConfig => 'Налепите вашу JSON конфигурацију испод:';

  @override
  String get addApiKeyAfterImport => 'Требаћете да додате сопствени API кључ после увоза';

  @override
  String get paste => 'Налепи';

  @override
  String get import => 'Увози';

  @override
  String get invalidProviderInConfig => 'Неважећи добављач у конфигурацији';

  @override
  String importedConfig(String providerName) {
    return 'Увезена $providerName конфигурација';
  }

  @override
  String invalidJson(String error) {
    return 'Неважећи JSON: $error';
  }

  @override
  String get provider => 'Добављач';

  @override
  String get live => 'Уживо';

  @override
  String get onDevice => 'На уређају';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Унесите STT HTTP крајњу тачку';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Унесите вашу уживо STT WebSocket крајњу тачку';

  @override
  String get apiKey => 'API кључ';

  @override
  String get enterApiKey => 'Унесите ваш API кључ';

  @override
  String get storedLocallyNeverShared => 'Чувано локално, никада се не дели';

  @override
  String get host => 'Хост';

  @override
  String get port => 'Порт';

  @override
  String get advanced => 'Напредно';

  @override
  String get configuration => 'Конфигурација';

  @override
  String get requestConfiguration => 'Конфигурација захтева';

  @override
  String get responseSchema => 'Шема одговора';

  @override
  String get modified => 'Измењено';

  @override
  String get resetRequestConfig => 'Ресетуј конфигурацију захтева на подразумевану';

  @override
  String get logs => 'Дневници';

  @override
  String get logsCopied => 'Дневници су копирани';

  @override
  String get noLogsYet => 'Нема дневника. Почните са снимањем да бисте видели прилагођену STT активност.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device користи $reason. Omi ће бити коришћен.';
  }

  @override
  String get omiTranscription => 'Omi препознавање говора';

  @override
  String get bestInClassTranscription => 'Најбоље препознавање говора без постављања';

  @override
  String get instantSpeakerLabels => 'Тренутне ознаке говорника';

  @override
  String get languageTranslation => 'Превод на 100+ језика';

  @override
  String get optimizedForConversation => 'Оптимизовано за разговор';

  @override
  String get autoLanguageDetection => 'Аутоматска детекција језика';

  @override
  String get highAccuracy => 'Висока тачност';

  @override
  String get privacyFirst => 'Приватност прво';

  @override
  String get saveChanges => 'Сачувај измене';

  @override
  String get resetToDefault => 'Ресетуј на подразумевано';

  @override
  String get viewTemplate => 'Приказ шаблона';

  @override
  String get trySomethingLike => 'Покушајте нешто као...';

  @override
  String get tryIt => 'Покушај';

  @override
  String get creatingPlan => 'Прављење плана';

  @override
  String get developingLogic => 'Развој логике';

  @override
  String get designingApp => 'Дизајнирање апликације';

  @override
  String get generatingIconStep => 'Прављење иконе';

  @override
  String get finalTouches => 'Финалне дораде';

  @override
  String get processing => 'Обрада...';

  @override
  String get features => 'Функције';

  @override
  String get creatingYourApp => 'Прављење ваше апликације...';

  @override
  String get generatingIcon => 'Прављење иконе...';

  @override
  String get whatShouldWeMake => 'Шта би требало да направимо?';

  @override
  String get appName => 'Име апликације';

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
  String get tailoredConversationSummaries => 'Прилагођени резимеи разговора';

  @override
  String get customChatbotPersonality => 'Прилагођена личност чатбота';

  @override
  String get makePublic => 'Направи јавно';

  @override
  String get anyoneCanDiscover => 'Свако може открити вашу апликацију';

  @override
  String get onlyYouCanUse => 'Само ви можете користити ову апликацију';

  @override
  String get paidApp => 'Плаћена апликација';

  @override
  String get usersPayToUse => 'Корисници плаћају за коришћење ваше апликације';

  @override
  String get freeForEveryone => 'Слободно за све';

  @override
  String get perMonthLabel => '/ месец';

  @override
  String get creating => 'Прављење...';

  @override
  String get createApp => 'Направи апликацију';

  @override
  String get searchingForDevices => 'Претраживање уређаја...';

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
  String get pairingSuccessful => 'УПАРИВАЊЕ УСПЕШНО';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Грешка при повезивању на Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Не приказуј поново';

  @override
  String get iUnderstand => 'Разумем';

  @override
  String get enableBluetooth => 'Омогући Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi треба Bluetooth да би се повезао на вашу носиву. Омогућите Bluetooth и покушајте поново.';

  @override
  String get contactSupport => 'Контактирајте подршку?';

  @override
  String get connectLater => 'Повежи се касније';

  @override
  String get grantPermissions => 'Додели дозволе';

  @override
  String get backgroundActivity => 'Позадинска активност';

  @override
  String get backgroundActivityDesc => 'Дозволи Omi да ради у позадини за већу стабилност';

  @override
  String get locationAccess => 'Приступ локацији';

  @override
  String get locationAccessDesc => 'Омогући позадинску локацију за потпуно искуство';

  @override
  String get notifications => 'Обавештења';

  @override
  String get notificationsDesc => 'Омогући обавештења да будеш обавештен';

  @override
  String get locationServiceDisabled => 'Услуга локације је онемогућена';

  @override
  String get locationServiceDisabledDesc =>
      'Услуга локације је онемогућена. Молим вас идите на Подешавања > Приватност и безбедност > Услуге локације и омогућите је';

  @override
  String get backgroundLocationDenied => 'Приступ позадинској локацији је одбијен';

  @override
  String get backgroundLocationDeniedDesc =>
      'Молим вас идите на подешавања уређаја и постављање дозволе за локацију на \"Увек дозволи\"';

  @override
  String get lovingOmi => 'Волиш ли Omi?';

  @override
  String get leaveReviewIos =>
      'Помози нам да дође до више људи остављањем рецензије у App Store-у. Твој повратни информације значи много нам!';

  @override
  String get leaveReviewAndroid =>
      'Помози нам да дође до више људи остављањем рецензије у Google Play Store-у. Твој повратни информације значи много нам!';

  @override
  String get rateOnAppStore => 'Оцени на App Store-у';

  @override
  String get rateOnGooglePlay => 'Оцени на Google Play';

  @override
  String get maybeLater => 'Можда касније';

  @override
  String get speechProfileIntro => 'Omi треба да научи твоје циљеве и твој глас. Касније ћеш моћи да га мењаш.';

  @override
  String get getStarted => 'Почни';

  @override
  String get allDone => 'Све је завршено!';

  @override
  String get keepGoing => 'Настави, чиниш одличан посао';

  @override
  String get skipThisQuestion => 'Прескочи ово питање';

  @override
  String get skipForNow => 'Прескочи за сада';

  @override
  String get connectionError => 'Грешка при повезивању';

  @override
  String get connectionErrorDesc =>
      'Не могу да се повежем на сервер. Молим вас проверите интернет везу и покушајте поново.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Неважећи снимак открит';

  @override
  String get multipleSpeakersDesc =>
      'Чини се да су у снимку мултипли говорници. Молим вас уверите се да сте на тихој локацији и покушајте поново.';

  @override
  String get tooShortDesc => 'Нема довољно говора открит. Молим вас говорите више и покушајте поново.';

  @override
  String get invalidRecordingDesc => 'Молим вас уверите се да говорите најмање 5 секунди и не више од 90.';

  @override
  String get areYouThere => 'Да ли си ту?';

  @override
  String get noSpeechDesc =>
      'Нисмо могли открит говор. Молим вас уверите се да говорите најмање 10 секунди и не више од 3 минута.';

  @override
  String get connectionLost => 'Веза је потргана';

  @override
  String get connectionLostDesc => 'Веза је прекинута. Молим вас проверите интернет везу и покушајте поново.';

  @override
  String get tryAgain => 'Покушај поново';

  @override
  String get connectOmiOmiGlass => 'Повежи Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Наставите без уређаја';

  @override
  String get permissionsRequired => 'Дозволе су обавезне';

  @override
  String get permissionsRequiredDesc =>
      'Ова апликација треба Bluetooth и дозволе за локацију да функционише правилно. Молим вас омогућите их у подешавањима.';

  @override
  String get openSettings => 'Отвори подешавања';

  @override
  String get wantDifferentName => 'Желиш да идеш под неким другим именом?';

  @override
  String get whatsYourName => 'Како се зовеш?';

  @override
  String get speakTranscribeSummarize => 'Говори. Препознај. Сумирај.';

  @override
  String get signInWithApple => 'Пријави се са Apple-ом';

  @override
  String get signInWithGoogle => 'Пријави се са Google-ом';

  @override
  String get byContinuingAgree => 'Наставком, слажеш се са нашим ';

  @override
  String get termsOfUse => 'Условима коришћења';

  @override
  String get omiYourAiCompanion => 'Omi – Твој AI пратилац';

  @override
  String get captureEveryMoment => 'Хвати сваки тренутак. Добиј AI-покретане\nрезимеје. Никад више не пишите белешке.';

  @override
  String get appleWatchSetup => 'Apple Watch подешавање';

  @override
  String get permissionRequestedExclaim => 'Дозвола је тражена!';

  @override
  String get microphonePermission => 'Дозвола за микрофон';

  @override
  String get permissionGrantedNow =>
      'Дозвола је додељена! Сада:\n\nОтвори Omi апликацију на часовнику и нажми на \"Настави\" испод';

  @override
  String get needMicrophonePermission =>
      'Trebamo дозволу за микрофон.\n\n1. Нажми \"Додели дозволу\"\n2. Дозволи на iPhone-у\n3. Апликација на часовнику ће се затворити\n4. Поново отвори и нажми \"Настави\"';

  @override
  String get grantPermissionButton => 'Додели дозволу';

  @override
  String get needHelp => 'Требаш помоћ?';

  @override
  String get troubleshootingSteps =>
      'Отклањање проблема:\n\n1. Уверите се да је Omi инсталиран на часовнику\n2. Отвори Omi апликацију на часовнику\n3. Потражи поп-ап дозволе\n4. Нажми \"Дозволи\" када је упитан\n5. Апликација на часовнику ће се затворити - поново је отвори\n6. Врати се и нажми \"Настави\" на iPhone-у';

  @override
  String get recordingStartedSuccessfully => 'Снимање је успешно почело!';

  @override
  String get permissionNotGrantedYet =>
      'Дозвола није додељена. Молим вас уверите се да сте дозволили приступ микрофону и поново отворили апликацију на часовнику.';

  @override
  String errorRequestingPermission(String error) {
    return 'Грешка при тражењу дозволе: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Грешка при почињању снимања: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Одаберите свој примарни језик';

  @override
  String get languageBenefits => 'Постави језик за боље препознавање и персонализовано искуство';

  @override
  String get whatsYourPrimaryLanguage => 'Који је твој примарни језик?';

  @override
  String get selectYourLanguage => 'Одаберите свој језик';

  @override
  String get personalGrowthJourney => 'Твој путь личног развоја са AI који слуша сваку твоју реч.';

  @override
  String get actionItemsTitle => 'За-рађивања';

  @override
  String get actionItemsDescription => 'Нажми да уредиш • Дуго притисни да одабереш • Повуци за акције';

  @override
  String get tabToDo => 'За-рађивања';

  @override
  String get tabDone => 'Завршено';

  @override
  String get tabOld => 'Старо';

  @override
  String get emptyTodoMessage => '🎉 Све је завршено!\nНема задатака на чекању';

  @override
  String get emptyDoneMessage => 'Нема завршених ставки';

  @override
  String get emptyOldMessage => '✅ Нема старих задатака';

  @override
  String get noItems => 'Нема ставки';

  @override
  String get actionItemMarkedIncomplete => 'Задатак је означен као незавршен';

  @override
  String get actionItemCompleted => 'Задатак је завршен';

  @override
  String get deleteActionItemTitle => 'Избриши задатак';

  @override
  String get deleteActionItemMessage => 'Да ли си сигуран да желиш да избришеш овај задатак?';

  @override
  String get deleteSelectedItemsTitle => 'Избриши одабране ставке';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Да ли си сигуран да желиш да избришеш $count одабран$s задатак?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Задатак \"$description\" је избрисан';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count задатак$s је избрисан';
  }

  @override
  String get failedToDeleteItem => 'Не могу да избришем задатак';

  @override
  String get failedToDeleteItems => 'Не могу да избришем ставке';

  @override
  String get failedToDeleteSomeItems => 'Не могу да избришем неке ставке';

  @override
  String get welcomeActionItemsTitle => 'Спреман за задатке';

  @override
  String get welcomeActionItemsDescription =>
      'Твој AI ће аутоматски извлачити задатке и за-рађивања из твоих разговора. Они ће се појавити овде када буду креирани.';

  @override
  String get autoExtractionFeature => 'Аутоматски извучено из разговора';

  @override
  String get editSwipeFeature => 'Нажми да уредиш, повуци да завршиш или избришеш';

  @override
  String itemsSelected(int count) {
    return '$count одабрано';
  }

  @override
  String get selectAll => 'Одаберите све';

  @override
  String get deleteSelected => 'Избриши одабрано';

  @override
  String get searchMemories => 'Претражи сећања...';

  @override
  String get memoryDeleted => 'Сећање је избрисано.';

  @override
  String get undo => 'Врати';

  @override
  String get noMemoriesYet => '🧠 Нема сећања';

  @override
  String get noAutoMemories => 'Нема аутоматски извучених сећања';

  @override
  String get noManualMemories => 'Нема ручно додатих сећања';

  @override
  String get noMemoriesInCategories => 'Нема сећања у овим категоријама';

  @override
  String get noMemoriesFound => '🔍 Нема пронађених сећања';

  @override
  String get addFirstMemory => 'Додај своје прво сећање';

  @override
  String get clearMemoryTitle => 'Очисти Omi-јево сећање';

  @override
  String get clearMemoryMessage =>
      'Да ли си сигуран да желиш да очистиш Omi-јево сећање? Ова акција се не може поништити.';

  @override
  String get clearMemoryButton => 'Очисти сећање';

  @override
  String get memoryClearedSuccess => 'Omi-јево сећање о теби је очишћено';

  @override
  String get noMemoriesToDelete => 'Нема сећања за брисање';

  @override
  String get createMemoryTooltip => 'Направи ново сећање';

  @override
  String get createActionItemTooltip => 'Направи нов задатак';

  @override
  String get memoryManagement => 'Управљање сећањем';

  @override
  String get filterMemories => 'Филтрирај сећања';

  @override
  String totalMemoriesCount(int count) {
    return 'Имаш $count укупно сећања';
  }

  @override
  String get publicMemories => 'Јавна сећања';

  @override
  String get privateMemories => 'Приватна сећања';

  @override
  String get makeAllPrivate => 'Направи сва сећања приватна';

  @override
  String get makeAllPublic => 'Направи сва сећања јавна';

  @override
  String get deleteAllMemories => 'Избриши сва сећања';

  @override
  String get allMemoriesPrivateResult => 'Сва сећања су сада приватна';

  @override
  String get allMemoriesPublicResult => 'Сва сећања су сада јавна';

  @override
  String get newMemory => '✨ Ново сећање';

  @override
  String get editMemory => '✏️ Уреди сећање';

  @override
  String get memoryContentHint => 'Волим да једем сладолед...';

  @override
  String get failedToSaveMemory => 'Не могу да сачувам. Молим вас проверите везу.';

  @override
  String get saveMemory => 'Сачувај сећање';

  @override
  String get retry => 'Покушај поново';

  @override
  String get createActionItem => 'Направи задатак';

  @override
  String get editActionItem => 'Уреди задатак';

  @override
  String get actionItemDescriptionHint => 'Шта треба да буде урађено?';

  @override
  String get actionItemDescriptionEmpty => 'Опис задатка не може бити празан.';

  @override
  String get actionItemUpdated => 'Задатак је ажуриран';

  @override
  String get failedToUpdateActionItem => 'Не могу да ажурирам задатак';

  @override
  String get actionItemCreated => 'Задатак је креиран';

  @override
  String get failedToCreateActionItem => 'Не могу да направим задатак';

  @override
  String get dueDate => 'Рок';

  @override
  String get time => 'Време';

  @override
  String get addDueDate => 'Додај рок';

  @override
  String get pressDoneToSave => 'Притисни готово да сачуваш';

  @override
  String get pressDoneToCreate => 'Притисни готово да направиш';

  @override
  String get filterAll => 'Све';

  @override
  String get filterSystem => 'О теби';

  @override
  String get filterInteresting => 'Увиди';

  @override
  String get filterManual => 'Ручно';

  @override
  String get completed => 'Завршено';

  @override
  String get markComplete => 'Означи као завршено';

  @override
  String get actionItemDeleted => 'Задатак је избрисан';

  @override
  String get failedToDeleteActionItem => 'Не могу да избришем задатак';

  @override
  String get deleteActionItemConfirmTitle => 'Избриши задатак';

  @override
  String get deleteActionItemConfirmMessage => 'Да ли си сигуран да желиш да избришеш овај задатак?';

  @override
  String get appLanguage => 'Језик апликације';

  @override
  String get appInterfaceSectionTitle => 'ИНТЕРФЕЈС АПЛИКАЦИЈЕ';

  @override
  String get speechTranscriptionSectionTitle => 'ГОВОР И ПРЕПОЗНАВАЊЕ';

  @override
  String get languageSettingsHelperText =>
      'Језик апликације мења менијеe и дугмад. Језик говора утиче на то како су твоја снимања препозната.';

  @override
  String get translationNotice => 'Напомена о преводу';

  @override
  String get translationNoticeMessage =>
      'Omi преводи разговоре на твој примарни језик. Ажурирај га у било које време у Подешавањима → Профили.';

  @override
  String get pleaseCheckInternetConnection => 'Молим вас проверите интернет везу и покушајте поново';

  @override
  String get pleaseSelectReason => 'Молим вас одаберите разлог';

  @override
  String get tellUsMoreWhatWentWrong => 'Реци нам више шта је пошло наопако...';

  @override
  String get selectText => 'Одаберите текст';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Максимално $count циљева дозвољено';
  }

  @override
  String get conversationCannotBeMerged => 'Овај разговор се не може обединити (закључан или већ се обединјава)';

  @override
  String get pleaseEnterFolderName => 'Молим вас унесите име фолдера';

  @override
  String get failedToCreateFolder => 'Не могу да направим фолдер';

  @override
  String get failedToUpdateFolder => 'Не могу да ажурирам фолдер';

  @override
  String get folderName => 'Име фолдера';

  @override
  String get descriptionOptional => 'Опис (опционално)';

  @override
  String get failedToDeleteFolder => 'Неуспешно брисање фолдера';

  @override
  String get editFolder => 'Уреди фолдер';

  @override
  String get deleteFolder => 'Обриши фолдер';

  @override
  String get transcriptCopiedToClipboard => 'Транскрипт копиран у привремену меморију';

  @override
  String get summaryCopiedToClipboard => 'Резиме копирано у привремену меморију';

  @override
  String get conversationUrlCouldNotBeShared => 'URL разговора није могао бити дељен.';

  @override
  String get urlCopiedToClipboard => 'URL копиран у привремену меморију';

  @override
  String get exportTranscript => 'Извези транскрипт';

  @override
  String get exportSummary => 'Извези резиме';

  @override
  String get exportButton => 'Извези';

  @override
  String get actionItemsCopiedToClipboard => 'Ставке радног списка копиране у привремену меморију';

  @override
  String get summarize => 'Направи резиме';

  @override
  String get generateSummary => 'Генериши резиме';

  @override
  String get conversationNotFoundOrDeleted => 'Разговор није пронађен или је обрисан';

  @override
  String get deleteMemory => 'Обриши меморију';

  @override
  String get thisActionCannotBeUndone => 'Ова радња се не може опозвати.';

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
  String get noMemoriesInCategory => 'Нема меморија у овој категорији';

  @override
  String get addYourFirstMemory => 'Додај своју прву меморију';

  @override
  String get firmwareDisconnectUsb => 'Откачи USB';

  @override
  String get firmwareUsbWarning => 'USB веза током ажурирања може оштетити ваш уређај.';

  @override
  String get firmwareBatteryAbove15 => 'Батерија изнад 15%';

  @override
  String get firmwareEnsureBattery => 'Уверите се да ваш уређај има 15% батерије.';

  @override
  String get firmwareStableConnection => 'Стабилна веза';

  @override
  String get firmwareConnectWifi => 'Повежите се на WiFi или мобилну мрежу.';

  @override
  String failedToStartUpdate(String error) {
    return 'Неуспешан почетак ажурирања: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Пре ажурирања, уверите се:';

  @override
  String get confirmed => 'Потврђено!';

  @override
  String get release => 'Издање';

  @override
  String get slideToUpdate => 'Клизи да ажурираш';

  @override
  String copiedToClipboard(String title) {
    return '$title копирано у привремену меморију';
  }

  @override
  String get batteryLevel => 'Ниво батерије';

  @override
  String get charging => 'Пуњење';

  @override
  String get productUpdate => 'Ажурирање производа';

  @override
  String get offline => 'Офлајн';

  @override
  String get available => 'Доступно';

  @override
  String get unpairDeviceDialogTitle => 'Откачи уређај';

  @override
  String get unpairDeviceDialogMessage =>
      'Ово ће откачити уређај како би могао бити повезан на други телефон. Мораћете да идете на Подешавања > Bluetooth и заборавите уређај да бисте завршили процес.';

  @override
  String get unpair => 'Откачи';

  @override
  String get unpairAndForgetDevice => 'Откачи и заборави уређај';

  @override
  String get unknownDevice => 'Непознато';

  @override
  String get unknown => 'Непознато';

  @override
  String get productName => 'Назив производа';

  @override
  String get serialNumber => 'Серијски број';

  @override
  String get connected => 'Повезано';

  @override
  String get privacyPolicyTitle => 'Политика приватности';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label копиран';
  }

  @override
  String get noApiKeysYet => 'Нема API кључева';

  @override
  String get createKeyToGetStarted => 'Направи кључ да почнеш';

  @override
  String get configureSttProvider => 'Конфигуриши STT провајдера';

  @override
  String get setWhenConversationsAutoEnd => 'Постави када се разговори аутоматски завршавају';

  @override
  String get importDataFromOtherSources => 'Увези податке из других извора';

  @override
  String get debugAndDiagnostics => 'Отклањање грешака и дијагностика';

  @override
  String get autoDeletesAfter3Days => 'Аутоматски briši после 3 дана.';

  @override
  String get helpsDiagnoseIssues => 'Помаже у дијагностици проблема';

  @override
  String get exportStartedMessage => 'Извоз је почео. Ово може потрајати неколико секунди...';

  @override
  String get exportConversationsToJson => 'Извези разговоре у JSON датотеку';

  @override
  String get knowledgeGraphDeletedSuccess => 'Граф знања успешно обрисан';

  @override
  String failedToDeleteGraph(String error) {
    return 'Неуспешно брисање графа: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Очисти све чворове и везе';

  @override
  String get addToClaudeDesktopConfig => 'Додај у claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Повежи AI асистенте са својим подацима';

  @override
  String get useYourMcpApiKey => 'Користи свој MCP API кључ';

  @override
  String get realTimeTranscript => 'Транскрипт у реалном времену';

  @override
  String get experimental => 'Експериментално';

  @override
  String get transcriptionDiagnostics => 'Дијагностика транскрипције';

  @override
  String get detailedDiagnosticMessages => 'Детаљне дијагностичке поруке';

  @override
  String get autoCreateSpeakers => 'Аутоматски создај говорнике';

  @override
  String get autoCreateWhenNameDetected => 'Аутоматски создај када је име откривено';

  @override
  String get followUpQuestions => 'Додатна питања';

  @override
  String get suggestQuestionsAfterConversations => 'Предложи питања после разговора';

  @override
  String get goalTracker => 'Пратач циљева';

  @override
  String get trackPersonalGoalsOnHomepage => 'Пратите своје личне циљеве на почетној страници';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Опис ставке радног списка не може бити празан';

  @override
  String get saved => 'Сачувано';

  @override
  String get overdue => 'Просрочено';

  @override
  String get failedToUpdateDueDate => 'Неуспешна промена датума завршетка';

  @override
  String get markIncomplete => 'Означи као незавршено';

  @override
  String get editDueDate => 'Уреди датум завршетка';

  @override
  String get setDueDate => 'Постави датум завршетка';

  @override
  String get clearDueDate => 'Очисти датум завршетка';

  @override
  String get failedToClearDueDate => 'Неуспешно брисање датума завршетка';

  @override
  String get mondayAbbr => 'Пон';

  @override
  String get tuesdayAbbr => 'Уто';

  @override
  String get wednesdayAbbr => 'Сре';

  @override
  String get thursdayAbbr => 'Чет';

  @override
  String get fridayAbbr => 'Пет';

  @override
  String get saturdayAbbr => 'Суб';

  @override
  String get sundayAbbr => 'Нед';

  @override
  String get howDoesItWork => 'Како функционише?';

  @override
  String get sdCardSyncDescription => 'SD картица синхронизација ће увести твоје меморије са SD картице у апликацију';

  @override
  String get checksForAudioFiles => 'Проверава звучне датотеке на SD картици';

  @override
  String get omiSyncsAudioFiles => 'Omi затим синхронизује звучне датотеке са сервером';

  @override
  String get serverProcessesAudio => 'Сервер обрађује звучне датотеке и прави меморије';

  @override
  String get youreAllSet => 'Све си спремна!';

  @override
  String get welcomeToOmiDescription =>
      'Добродошли у Omi! Твој AI пратилац је спреман да те помогне са разговорима, задацима и још много чега.';

  @override
  String get startUsingOmi => 'Почни користити Omi';

  @override
  String get back => 'Назад';

  @override
  String get keyboardShortcuts => 'Пречице за тастатуру';

  @override
  String get toggleControlBar => 'Пребаци контролну траку';

  @override
  String get pressKeys => 'Притисни дугмиће...';

  @override
  String get cmdRequired => '⌘ обавезно';

  @override
  String get invalidKey => 'Неважећи дугме';

  @override
  String get space => 'Размак';

  @override
  String get search => 'Претрага';

  @override
  String get searchPlaceholder => 'Претрага...';

  @override
  String get untitledConversation => 'Разговор без наслова';

  @override
  String countRemaining(String count) {
    return '$count преостало';
  }

  @override
  String get addGoal => 'Додај циљ';

  @override
  String get editGoal => 'Уреди циљ';

  @override
  String get icon => 'Икона';

  @override
  String get goalTitle => 'Наслов циља';

  @override
  String get current => 'Тренутно';

  @override
  String get target => 'Циљ';

  @override
  String get saveGoal => 'Сачувај';

  @override
  String get goals => 'Циљеви';

  @override
  String get tapToAddGoal => 'Додирни да додаш циљ';

  @override
  String welcomeBack(String name) {
    return 'Добродошли назад, $name';
  }

  @override
  String get yourConversations => 'Твои разговори';

  @override
  String get reviewAndManageConversations => 'Преглед и управљање твоим заснетим разговорима';

  @override
  String get startCapturingConversations => 'Почни да заснимаш разговоре са твоја Omi уређајем да видиш их овде.';

  @override
  String get useMobileAppToCapture => 'Користи своју мобилну апликацију да снимиш аудио';

  @override
  String get conversationsProcessedAutomatically => 'Разговори се обрађују аутоматски';

  @override
  String get getInsightsInstantly => 'Добити увиде и резимеа мгновено';

  @override
  String get showAll => 'Покажи све';

  @override
  String get noTasksForToday => 'Нема задатака за данас.\nПитај Omi за више задатака или направи ручно.';

  @override
  String get dailyScore => 'ДНЕВНА ОЦЕНА';

  @override
  String get dailyScoreDescription => 'Оцена која те помаже да боље\nфокусираш се на извршење.';

  @override
  String get searchResults => 'Резултати претраге';

  @override
  String get actionItems => 'Ставке радног списка';

  @override
  String get tasksToday => 'Данас';

  @override
  String get tasksTomorrow => 'Сутра';

  @override
  String get tasksNoDeadline => 'Нема крајњег рока';

  @override
  String get tasksLater => 'Касније';

  @override
  String get loadingTasks => 'Учитавање задатака...';

  @override
  String get tasks => 'Задаци';

  @override
  String get swipeTasksToIndent => 'Превуци задатке за увлачење, превлачи између категорија';

  @override
  String get create => 'Направи';

  @override
  String get noTasksYet => 'Нема задатака';

  @override
  String get tasksFromConversationsWillAppear =>
      'Задаци из твоих разговора ће се појавити овде.\nЛикни Направи да додаш један ручно.';

  @override
  String get monthJan => 'Јан';

  @override
  String get monthFeb => 'Феб';

  @override
  String get monthMar => 'Мар';

  @override
  String get monthApr => 'Апр';

  @override
  String get monthMay => 'Мај';

  @override
  String get monthJun => 'Јун';

  @override
  String get monthJul => 'Јул';

  @override
  String get monthAug => 'Авг';

  @override
  String get monthSep => 'Сеп';

  @override
  String get monthOct => 'Окт';

  @override
  String get monthNov => 'Нов';

  @override
  String get monthDec => 'Дец';

  @override
  String get timePM => 'ПМ';

  @override
  String get timeAM => 'АМ';

  @override
  String get actionItemUpdatedSuccessfully => 'Ставка радног списка успешно ажурирана';

  @override
  String get actionItemCreatedSuccessfully => 'Ставка радног списка успешно направљена';

  @override
  String get actionItemDeletedSuccessfully => 'Ставка радног списка успешно обрисана';

  @override
  String get deleteActionItem => 'Обриши ставку радног списка';

  @override
  String get deleteActionItemConfirmation =>
      'Да ли си сигуран да желиш да обришеш ову ставку радног списка? Ова радња се не може опозвати.';

  @override
  String get enterActionItemDescription => 'Унеси опис ставке радног списка...';

  @override
  String get markAsCompleted => 'Означи као завршено';

  @override
  String get setDueDateAndTime => 'Постави датум и време завршетка';

  @override
  String get reloadingApps => 'Поново учитавање апликација...';

  @override
  String get loadingApps => 'Учитавање апликација...';

  @override
  String get browseInstallCreateApps => 'Прегледај, инсталирај и направи апликације';

  @override
  String get all => 'Све';

  @override
  String get open => 'Отвори';

  @override
  String get install => 'Инсталирај';

  @override
  String get noAppsAvailable => 'Нема доступних апликација';

  @override
  String get unableToLoadApps => 'Неуспешно учитавање апликација';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Покушај да прилагодиш своје услове претраге или филтере';

  @override
  String get checkBackLaterForNewApps => 'Враћи се касније за нове апликације';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Молимо проверите своју интернет везу и покушајте поново';

  @override
  String get createNewApp => 'Направи нову апликацију';

  @override
  String get buildSubmitCustomOmiApp => 'Направи и пошаљи своју прилагођену Omi апликацију';

  @override
  String get submittingYourApp => 'Слање твоје апликације...';

  @override
  String get preparingFormForYou => 'Припремам формулар за тебе...';

  @override
  String get appDetails => 'Детаљи апликације';

  @override
  String get paymentDetails => 'Детаљи плаћања';

  @override
  String get previewAndScreenshots => 'Преглед и снимци екрана';

  @override
  String get appCapabilities => 'Могућности апликације';

  @override
  String get aiPrompts => 'AI упите';

  @override
  String get chatPrompt => 'Чат упит';

  @override
  String get chatPromptPlaceholder =>
      'Ти си невероватна апликација, твој посао је да одговориш на упите корисника и учиниш га срећним...';

  @override
  String get conversationPrompt => 'Упит разговора';

  @override
  String get conversationPromptPlaceholder => 'Ти си невероватна апликација, добићеш транскрипт и резиме разговора...';

  @override
  String get notificationScopes => 'Опсезима обавештења';

  @override
  String get appPrivacyAndTerms => 'Приватност и услови апликације';

  @override
  String get makeMyAppPublic => 'Направи моју апликацију јавном';

  @override
  String get submitAppTermsAgreement =>
      'Слањем ове апликације, слажем се са Omi AI условима коришћења и политиком приватности';

  @override
  String get submitApp => 'Пошаљи апликацију';

  @override
  String get needHelpGettingStarted => 'Треба ти помоћ на почетку?';

  @override
  String get clickHereForAppBuildingGuides => 'Лики овде за водиче за прављење апликација и документацију';

  @override
  String get submitAppQuestion => 'Пошаљи апликацију?';

  @override
  String get submitAppPublicDescription =>
      'Твоја апликација ће бити прегледана и направљена јавна. Можеш почети да је користиш одмах, чак и док је у прегледу!';

  @override
  String get submitAppPrivateDescription =>
      'Твоја апликација ће бити прегледана и направљена доступна теби приватно. Можеш почети да је користиш одмах, чак и док је у прегледу!';

  @override
  String get startEarning => 'Почни да зарађиваш! 💰';

  @override
  String get connectStripeOrPayPal => 'Повежи Stripe или PayPal да примиш плаћања за своју апликацију.';

  @override
  String get connectNow => 'Повежи се сада';

  @override
  String get installsCount => 'Инсталације';

  @override
  String get uninstallApp => 'Деинсталирај апликацију';

  @override
  String get subscribe => 'Претплати се';

  @override
  String get dataAccessNotice => 'Обавеза приступа подаципма';

  @override
  String get dataAccessWarning =>
      'Ова апликација ће приступити твоим подаципма. Omi AI није одговоран за начин на који твоји подаци буду коришћени, модификовани или обрисани од стране ове апликације';

  @override
  String get installApp => 'Инсталирај апликацију';

  @override
  String get betaTesterNotice =>
      'Ти си бета тестер за ову апликацију. Она још није јавна. Биће јавна када буде одобрена.';

  @override
  String get appUnderReviewOwner =>
      'Твоја апликација је на прегледу и видљива само теби. Биће јавна када буде одобрена.';

  @override
  String get appRejectedNotice =>
      'Твоја апликација је одбијена. Молимо ажурирај детаље апликације и поново пошаљи на преглед.';

  @override
  String get setupSteps => 'Кораци подешавања';

  @override
  String get setupInstructions => 'Упутства за подешавање';

  @override
  String get integrationInstructions => 'Упутства за интеграцију';

  @override
  String get preview => 'Преглед';

  @override
  String get aboutTheApp => 'О апликацији';

  @override
  String get chatPersonality => 'Личност чата';

  @override
  String get ratingsAndReviews => 'Оцене и отзиви';

  @override
  String get noRatings => 'без оцена';

  @override
  String ratingsCount(String count) {
    return '$count+ оцена';
  }

  @override
  String get errorActivatingApp => 'Грешка при активирању апликације';

  @override
  String get integrationSetupRequired => 'Ако је ово апликација за интеграцију, уверите се да је подешавање завршено.';

  @override
  String get installed => 'Инсталирано';

  @override
  String get appIdLabel => 'ID апликације';

  @override
  String get appNameLabel => 'Назив апликације';

  @override
  String get appNamePlaceholder => 'Моја невероватна апликација';

  @override
  String get pleaseEnterAppName => 'Молимо унеси назив апликације';

  @override
  String get categoryLabel => 'Категорија';

  @override
  String get selectCategory => 'Изабери категорију';

  @override
  String get descriptionLabel => 'Опис';

  @override
  String get appDescriptionPlaceholder =>
      'Моја невероватна апликација је одличнна апликација која чини невероватне ствари. То је најбоља апликација икад!';

  @override
  String get pleaseProvideValidDescription => 'Молимо дај важећи опис';

  @override
  String get appPricingLabel => 'Цена апликације';

  @override
  String get noneSelected => 'Ничего није изабрано';

  @override
  String get appIdCopiedToClipboard => 'ID апликације копиран у привремену меморију';

  @override
  String get appCategoryModalTitle => 'Категорија апликације';

  @override
  String get pricingFree => 'Бесплатно';

  @override
  String get pricingPaid => 'Плаћено';

  @override
  String get loadingCapabilities => 'Учитавање могућности...';

  @override
  String get filterInstalled => 'Инсталирано';

  @override
  String get filterMyApps => 'Моје апликације';

  @override
  String get clearSelection => 'Очисти избор';

  @override
  String get filterCategory => 'Категорија';

  @override
  String get rating4PlusStars => '4+ звезде';

  @override
  String get rating3PlusStars => '3+ звезде';

  @override
  String get rating2PlusStars => '2+ звезде';

  @override
  String get rating1PlusStars => '1+ звезда';

  @override
  String get filterRating => 'Оцена';

  @override
  String get filterCapabilities => 'Могућности';

  @override
  String get noNotificationScopesAvailable => 'Нема доступних опсезима обавештења';

  @override
  String get popularApps => 'Популарне апликације';

  @override
  String get pleaseProvidePrompt => 'Молимо дај упит';

  @override
  String chatWithAppName(String appName) {
    return 'Чатуј са $appName';
  }

  @override
  String get defaultAiAssistant => 'Подразумевани AI асистент';

  @override
  String get readyToChat => '✨ Спреман за чат!';

  @override
  String get connectionNeeded => '🌐 Веза је потребна';

  @override
  String get startConversation => 'Почни разговор и нека магија почне';

  @override
  String get checkInternetConnection => 'Молимо проверите своју интернет везу';

  @override
  String get wasThisHelpful => 'Да ли је ово помогло?';

  @override
  String get thankYouForFeedback => 'Хвала на повратној информацији!';

  @override
  String get maxFilesUploadError => 'Можеш учитати само 4 датотеке одједном';

  @override
  String get attachedFiles => '📎 Приложене датотеке';

  @override
  String get takePhoto => 'Направи фотографију';

  @override
  String get captureWithCamera => 'Сними са камером';

  @override
  String get selectImages => 'Изабери слике';

  @override
  String get chooseFromGallery => 'Одабери из галерије';

  @override
  String get selectFile => 'Изабери датотеку';

  @override
  String get chooseAnyFileType => 'Одабери било коју врсту датотеке';

  @override
  String get cannotReportOwnMessages => 'Не можеш пријавити своје поруке';

  @override
  String get messageReportedSuccessfully => '✅ Порука успешно пријављена';

  @override
  String get confirmReportMessage => 'Да ли си сигуран да желиш да пријавиш ову поруку?';

  @override
  String get selectChatAssistant => 'Изабери чат асистента';

  @override
  String get enableMoreApps => 'Омогући више апликација';

  @override
  String get chatCleared => 'Чат је очишћен';

  @override
  String get clearChatTitle => 'Очисти чат?';

  @override
  String get confirmClearChat => 'Да ли си сигуран да желиш да очистиш чат? Ова радња се не може опозвати.';

  @override
  String get copy => 'Копирај';

  @override
  String get share => 'Дели';

  @override
  String get report => 'Пријави';

  @override
  String get microphonePermissionRequired => 'Дозвола за микрофон је потребна за позивање';

  @override
  String get microphonePermissionDenied =>
      'Дозвола за микрофон одбијена. Молимо одобри дозволу у системским подешавањима > Приватност и безбедност > Микрофон.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Неуспешна проверка дозволе за микрофон: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Неуспешна транскрипција аудиа';

  @override
  String get transcribing => 'Транскрибовање...';

  @override
  String get transcriptionFailed => 'Транскрипција неуспешна';

  @override
  String get discardedConversation => 'Одбачени разговор';

  @override
  String get at => 'у';

  @override
  String get from => 'од';

  @override
  String get copied => 'Копирано!';

  @override
  String get copyLink => 'Копирај везу';

  @override
  String get hideTranscript => 'Сакриј транскрипт';

  @override
  String get viewTranscript => 'Погледај транскрипт';

  @override
  String get conversationDetails => 'Детаљи разговора';

  @override
  String get transcript => 'Транскрипт';

  @override
  String segmentsCount(int count) {
    return '$count сегмената';
  }

  @override
  String get noTranscriptAvailable => 'Нема доступног транскрипта';

  @override
  String get noTranscriptMessage => 'Овај разговор нема транскрипт.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL разговора није могао бити генерисан.';

  @override
  String get failedToGenerateConversationLink => 'Неуспешна генерисање везе разговора';

  @override
  String get failedToGenerateShareLink => 'Неуспешна генерисање везе за дељење';

  @override
  String get reloadingConversations => 'Поново учитавање разговора...';

  @override
  String get user => 'Корисник';

  @override
  String get starred => 'Означено звездом';

  @override
  String get date => 'Датум';

  @override
  String get noResultsFound => 'Нема пронађених резултата';

  @override
  String get tryAdjustingSearchTerms => 'Покушај прилагођавање услова претраге';

  @override
  String get starConversationsToFindQuickly => 'Означи разговоре звездом да их брзо пронађеш овде';

  @override
  String noConversationsOnDate(String date) {
    return 'Нема разговора на дан $date';
  }

  @override
  String get trySelectingDifferentDate => 'Покушај да изабереш другачију датум';

  @override
  String get conversations => 'Разговори';

  @override
  String get chat => 'Чат';

  @override
  String get actions => 'Радње';

  @override
  String get syncAvailable => 'Синхронизација доступна';

  @override
  String get referAFriend => 'Препоручи пријатељу';

  @override
  String get help => 'Помоћ';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Напредуј на Pro';

  @override
  String get getOmiDevice => 'Добави Omi уређај';

  @override
  String get wearableAiCompanion => 'Носиви AI пратилац';

  @override
  String get loadingMemories => 'Учитавање меморија...';

  @override
  String get allMemories => 'Све меморије';

  @override
  String get aboutYou => 'О теби';

  @override
  String get manual => 'Ручно';

  @override
  String get loadingYourMemories => 'Учитавање твоих меморија...';

  @override
  String get createYourFirstMemory => 'Направи своју прву меморију да почнеш';

  @override
  String get tryAdjustingFilter => 'Покушај прилагођавање своје претраге или филтера';

  @override
  String get whatWouldYouLikeToRemember => 'Шта би волео да запамтиш?';

  @override
  String get category => 'Категорија';

  @override
  String get public => 'Јавно';

  @override
  String get failedToSaveCheckConnection => 'Неуспешно чување. Молимо проверите вашу везу.';

  @override
  String get createMemory => 'Направи меморију';

  @override
  String get deleteMemoryConfirmation =>
      'Да ли си сигуран да желиш да обришеш ову меморију? Ова радња се не може опозвати.';

  @override
  String get makePrivate => 'Направи приватном';

  @override
  String get organizeAndControlMemories => 'Организуј и контролиши своје меморије';

  @override
  String get total => 'Укупно';

  @override
  String get makeAllMemoriesPrivate => 'Направи све меморије приватним';

  @override
  String get setAllMemoriesToPrivate => 'Постави све меморије на приватну видљивост';

  @override
  String get makeAllMemoriesPublic => 'Направи све меморије јавним';

  @override
  String get setAllMemoriesToPublic => 'Постави све меморије на јавну видљивост';

  @override
  String get permanentlyRemoveAllMemories => 'Трајно уклони све меморије из Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Све меморије су сада приватне';

  @override
  String get allMemoriesAreNowPublic => 'Све меморије су сада јавне';

  @override
  String get clearOmisMemory => 'Очисти Omi-јеву меморију';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Да ли си сигуран да желиш да очистиш Omi-јеву меморију? Ова радња се не може опозвати и трајно ће обрисати све $count меморије.';
  }

  @override
  String get omisMemoryCleared => 'Omi-јева меморија о теби је очишћена';

  @override
  String get welcomeToOmi => 'Добродошли у Omi';

  @override
  String get continueWithApple => 'Настави са Apple';

  @override
  String get continueWithGoogle => 'Наставите са Гуглом';

  @override
  String get byContinuingYouAgree => 'Наставком се слажете са нашим ';

  @override
  String get termsOfService => 'Условима коришћења';

  @override
  String get and => ' и ';

  @override
  String get dataAndPrivacy => 'Подацима и приватношћу';

  @override
  String get secureAuthViaAppleId => 'Безбедна аутентификација преко Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Безбедна аутентификација преко Google налога';

  @override
  String get whatWeCollect => 'Шта прикупљамо';

  @override
  String get dataCollectionMessage =>
      'Наставком, ваше разговоре, снимке и личне информације ће бити безбедно похрањене на нашим серверима да би вам пружили AI-подржане увиде и омогућили све функције апликације.';

  @override
  String get dataProtection => 'Заштита podataka';

  @override
  String get yourDataIsProtected => 'Ваши подаци су заштићени и регулисани са нашим ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Молимо изаберите свој главни језик';

  @override
  String get chooseYourLanguage => 'Изаберите свој језик';

  @override
  String get selectPreferredLanguageForBestExperience => 'Изаберите префериран језик за најбољи Omi искуство';

  @override
  String get searchLanguages => 'Претражите језике...';

  @override
  String get selectALanguage => 'Изаберите језик';

  @override
  String get tryDifferentSearchTerm => 'Покушајте други термин претраге';

  @override
  String get pleaseEnterYourName => 'Молимо унесите своје име';

  @override
  String get nameMustBeAtLeast2Characters => 'Име мора имати најмање 2 карактера';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Скажите нам како бисте желели да будете названи. Ово помаже да персонализујемо ваше Omi искуство.';

  @override
  String charactersCount(int count) {
    return '$count карактера';
  }

  @override
  String get enableFeaturesForBestExperience => 'Омогућите функције за најбоље Omi искуство на вашем уређају.';

  @override
  String get microphoneAccess => 'Приступ микрофону';

  @override
  String get recordAudioConversations => 'Снимајте аудио разговоре';

  @override
  String get microphoneAccessDescription =>
      'Omi треба приступ микрофону да би снимио ваше разговоре и пружио транскрипције.';

  @override
  String get screenRecording => 'Снимање екрана';

  @override
  String get captureSystemAudioFromMeetings => 'Хватајте системски звук са састанака';

  @override
  String get screenRecordingDescription =>
      'Omi треба дозвола за снимање екрана да би хватио системски звук са ваших веб-базираних састанака.';

  @override
  String get accessibility => 'Приступачност';

  @override
  String get detectBrowserBasedMeetings => 'Откријте веб-базиране састанке';

  @override
  String get accessibilityDescription =>
      'Omi треба дозвола за приступачност да би открио када се прикључите Zoom, Meet или Teams sastancima у вашем прегледачу.';

  @override
  String get pleaseWait => 'Молимо чекајте...';

  @override
  String get joinTheCommunity => 'Придружите се заједници!';

  @override
  String get loadingProfile => 'Учитавање профила...';

  @override
  String get profileSettings => 'Поставке профила';

  @override
  String get noEmailSet => 'Нема постављене е-поште';

  @override
  String get userIdCopiedToClipboard => 'ID корисника копиран у клипборд';

  @override
  String get yourInformation => 'Ваше информације';

  @override
  String get setYourName => 'Поставите своје име';

  @override
  String get changeYourName => 'Промените своје име';

  @override
  String get voiceAndPeople => 'Глас и људи';

  @override
  String get teachOmiYourVoice => 'Научите Omi вашем гласу';

  @override
  String get tellOmiWhoSaidIt => 'Скажите Omi ко је то рекао 🗣️';

  @override
  String get payment => 'Плаћање';

  @override
  String get addOrChangeYourPaymentMethod => 'Додајте или промените своју методу плаћања';

  @override
  String get preferences => 'Преференце';

  @override
  String get helpImproveOmiBySharing => 'Помогните да се Omi побољша дељењем анонимизованих аналитичких podataka';

  @override
  String get deleteAccount => 'Обришите налог';

  @override
  String get deleteYourAccountAndAllData => 'Обришите свој налог и све podatke';

  @override
  String get clearLogs => 'Очистите дневнике';

  @override
  String get debugLogsCleared => 'Дебаг дневници очишћени';

  @override
  String get exportConversations => 'Извезите разговоре';

  @override
  String get exportAllConversationsToJson => 'Извезите све своје разговоре у JSON датотеку.';

  @override
  String get conversationsExportStarted =>
      'Извоз разговора почео. Ово може потрајати неколико секунди, молимо чекајте.';

  @override
  String get mcpDescription =>
      'Повежите Omi са другим апликацијама да читате, претражите и управљате својим успоменама и разговорима. Направите кључ да почнете.';

  @override
  String get apiKeys => 'API кључеви';

  @override
  String errorLabel(String error) {
    return 'Грешка: $error';
  }

  @override
  String get noApiKeysFound => 'Нема найдених API кључева. Направите један да почнете.';

  @override
  String get advancedSettings => 'Напредне поставке';

  @override
  String get triggersWhenNewConversationCreated => 'Активира се када се направи нов разговор.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Активира се када се прими нова транскрипција.';

  @override
  String get realtimeAudioBytes => 'Аудио бајтови у реалном времену';

  @override
  String get triggersWhenAudioBytesReceived => 'Активира се када се примају аудио бајтови.';

  @override
  String get everyXSeconds => 'Свих x секунди';

  @override
  String get triggersWhenDaySummaryGenerated => 'Активира се када се генерише дневни резиме.';

  @override
  String get tryLatestExperimentalFeatures => 'Пробајте најновије експерименталне функције од Omi тима.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Статус дијагнозе услуге транскрипције';

  @override
  String get enableDetailedDiagnosticMessages => 'Омогућите детаљне дијагностичке поруке од услуге транскрипције';

  @override
  String get autoCreateAndTagNewSpeakers => 'Аутоматски направите и означите нове говорнике';

  @override
  String get automaticallyCreateNewPerson => 'Аутоматски направите нову особу када се име открије у транскрипцији.';

  @override
  String get pilotFeatures => 'Пилотне функције';

  @override
  String get pilotFeaturesDescription => 'Ове функције су тестови и подршка није гарантована.';

  @override
  String get suggestFollowUpQuestion => 'Предложи праћење питања';

  @override
  String get saveSettings => 'Сачувај поставке';

  @override
  String get syncingDeveloperSettings => 'Синхронизовање поставки разработнвача...';

  @override
  String get summary => 'Резиме';

  @override
  String get auto => 'Аутоматско';

  @override
  String get noSummaryForApp =>
      'Нема доступног резимеа за ову апликацију. Пробајте другу апликацију за боље резултате.';

  @override
  String get tryAnotherApp => 'Пробајте другу апликацију';

  @override
  String generatedBy(String appName) {
    return 'Генерисано од $appName';
  }

  @override
  String get overview => 'Преглед';

  @override
  String get otherAppResults => 'Резултати других апликација';

  @override
  String get unknownApp => 'Непозната апликација';

  @override
  String get noSummaryAvailable => 'Нема доступног резимеа';

  @override
  String get conversationNoSummaryYet => 'Овај разговор још увек нема резиме.';

  @override
  String get chooseSummarizationApp => 'Изаберите апликацију за резимирање';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName је постављена као подразумевана апликација за резимирање';
  }

  @override
  String get letOmiChooseAutomatically => 'Дозволи Omi да аутоматски изабере најбољу апликацију';

  @override
  String get deleteConversationConfirmation =>
      'Да ли сте сигурни да желите да обришете овај разговор? Ова радња не може бити отказана.';

  @override
  String get conversationDeleted => 'Разговор обрисан';

  @override
  String get generatingLink => 'Генерисање веће...';

  @override
  String get editConversation => 'Уредите разговор';

  @override
  String get conversationLinkCopiedToClipboard => 'Веза разговора копирана у клипборд';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Транскрипција разговора копирана у клипборд';

  @override
  String get editConversationDialogTitle => 'Уредите разговор';

  @override
  String get changeTheConversationTitle => 'Промените наслов разговора';

  @override
  String get conversationTitle => 'Наслов разговора';

  @override
  String get enterConversationTitle => 'Унесите наслов разговора...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Наслов разговора је успешно ажуриран';

  @override
  String get failedToUpdateConversationTitle => 'Неуспешна ажурирања наслова разговора';

  @override
  String get errorUpdatingConversationTitle => 'Грешка при ажурирању наслова разговора';

  @override
  String get settingUp => 'Постављање...';

  @override
  String get startYourFirstRecording => 'Почните ваш први снимак';

  @override
  String get preparingSystemAudioCapture => 'Припремање хватања системског звука';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Кликните на дугме да хватите звук за директне транскрипције, AI увиде и аутоматско чување.';

  @override
  String get reconnecting => 'Поновно повезивање...';

  @override
  String get recordingPaused => 'Снимање паузирано';

  @override
  String get recordingActive => 'Снимање активно';

  @override
  String get startRecording => 'Почните снимање';

  @override
  String resumingInCountdown(String countdown) {
    return 'Наставља се за ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Додирните палај да наставите';

  @override
  String get listeningForAudio => 'Слушање звука...';

  @override
  String get preparingAudioCapture => 'Припремање хватања звука';

  @override
  String get clickToBeginRecording => 'Кликните да почнете снимање';

  @override
  String get translated => 'преведено';

  @override
  String get liveTranscript => 'Директна транскрипција';

  @override
  String segmentsSingular(String count) {
    return '$count сегмент';
  }

  @override
  String segmentsPlural(String count) {
    return '$count сегмената';
  }

  @override
  String get startRecordingToSeeTranscript => 'Почните снимање да видите директну транскрипцију';

  @override
  String get paused => 'Паузирано';

  @override
  String get initializing => 'Иницијализовање...';

  @override
  String get recording => 'Снимање';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Микрофон промењен. Наставља се за ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Кликните палај да наставите или стопирајте да завршите';

  @override
  String get settingUpSystemAudioCapture => 'Постављање хватања системског звука';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Хватање звука и генерисање транскрипције';

  @override
  String get clickToBeginRecordingSystemAudio => 'Кликните да почнете снимање системског звука';

  @override
  String get you => 'Ви';

  @override
  String speakerWithId(String speakerId) {
    return 'Говорник $speakerId';
  }

  @override
  String get translatedByOmi => 'преведено од стране omi';

  @override
  String get backToConversations => 'Назад на разговоре';

  @override
  String get systemAudio => 'Систем';

  @override
  String get mic => 'Микрофон';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Аудио улаз постављен на $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Грешка при преласку аудио уређаја: $error';
  }

  @override
  String get selectAudioInput => 'Изаберите аудио улаз';

  @override
  String get loadingDevices => 'Учитавање уређаја...';

  @override
  String get settingsHeader => 'ПОСТАВКЕ';

  @override
  String get plansAndBilling => 'Планови и наплате';

  @override
  String get calendarIntegration => 'Интеграција календара';

  @override
  String get dailySummary => 'Дневни резиме';

  @override
  String get developer => 'Разработнвач';

  @override
  String get about => 'О апликацији';

  @override
  String get selectTime => 'Изаберите време';

  @override
  String get accountGroup => 'Налог';

  @override
  String get signOutQuestion => 'Одјава?';

  @override
  String get signOutConfirmation => 'Да ли сте сигурни да желите да се одјавите?';

  @override
  String get customVocabularyHeader => 'ПРИЛАГОЂЕНИ РЕЧНИК';

  @override
  String get addWordsDescription => 'Додајте речи које Omi требо да препозна при транскрипцији.';

  @override
  String get enterWordsHint => 'Унесите речи (одвојене зарезом)';

  @override
  String get dailySummaryHeader => 'ДНЕВНИ РЕЗИМЕ';

  @override
  String get dailySummaryTitle => 'Дневни резиме';

  @override
  String get dailySummaryDescription => 'Добијте персонализовани резиме разговора вашег дана достављен као обавештење.';

  @override
  String get deliveryTime => 'Време доставе';

  @override
  String get deliveryTimeDescription => 'Када желите да примите ваш дневни резиме';

  @override
  String get subscription => 'Претплата';

  @override
  String get viewPlansAndUsage => 'Прегледајте планове и употребу';

  @override
  String get viewPlansDescription => 'Управљајте вашом претплатом и видите статистику употребе';

  @override
  String get addOrChangePaymentMethod => 'Додајте или променитеваше методе плаћања';

  @override
  String get displayOptions => 'Опције приказа';

  @override
  String get showMeetingsInMenuBar => 'Приказ састанака у траци менија';

  @override
  String get displayUpcomingMeetingsDescription => 'Приказ предстојећих састанака у траци менија';

  @override
  String get showEventsWithoutParticipants => 'Приказ догађаја без учесника';

  @override
  String get includePersonalEventsDescription => 'Укључи личне догађаје без присутвујућих';

  @override
  String get upcomingMeetings => 'Предстојећи састанци';

  @override
  String get checkingNext7Days => 'Проверавање наредних 7 дана';

  @override
  String get shortcuts => 'Пречице';

  @override
  String get shortcutChangeInstruction => 'Кликните на пречицу да је промените. Притисните Escape да отказете.';

  @override
  String get configureSTTProvider => 'Конфигуришите STT провајдера';

  @override
  String get setConversationEndDescription => 'Поставите када разговори аутоматски завршавају';

  @override
  String get importDataDescription => 'Увезите податке из других извора';

  @override
  String get exportConversationsDescription => 'Извезите разговоре у JSON';

  @override
  String get exportingConversations => 'Извоз разговора...';

  @override
  String get clearNodesDescription => 'Очистите све чворове и веза';

  @override
  String get deleteKnowledgeGraphQuestion => 'Обришите граф знања?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Ово ће обрисати све изведене податке графа знања. Ваше оригиналне успомене остају безбедне.';

  @override
  String get connectOmiWithAI => 'Повежите Omi са AI асистентима';

  @override
  String get noAPIKeys => 'Нема API кључева. Направите један да почнете.';

  @override
  String get autoCreateWhenDetected => 'Аутоматски направи када је име открито';

  @override
  String get trackPersonalGoals => 'Пратите личне циљеве на почетној страни';

  @override
  String get endpointURL => 'URL крајне тачке';

  @override
  String get links => 'Веза';

  @override
  String get discordMemberCount => '8000+ чланова на Discord-у';

  @override
  String get userInformation => 'Информације о кориснику';

  @override
  String get capabilities => 'Способности';

  @override
  String get previewScreenshots => 'Прегледајте снимке екрана';

  @override
  String get holdOnPreparingForm => 'Задржите се, припремамо образац за вас';

  @override
  String get bySubmittingYouAgreeToOmi => 'Слањем се слажете са Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Условима и политиком приватности';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Помаже да се дијагностикују проблеми. Аутоматски брише се после 3 дана.';

  @override
  String get manageYourApp => 'Управљајте својом апликацијом';

  @override
  String get updatingYourApp => 'Ажурирање ваше апликације';

  @override
  String get fetchingYourAppDetails => 'Преузимање детаља ваше апликације';

  @override
  String get updateAppQuestion => 'Ажурирати апликацију?';

  @override
  String get updateAppConfirmation =>
      'Да ли сте сигурни да желите да ажурирате вашу апликацију? Измене ће бити рефлектоване када буду прегледане од наше тима.';

  @override
  String get updateApp => 'Ажурирај апликацију';

  @override
  String get createAndSubmitNewApp => 'Направите и пошаљите нову апликацију';

  @override
  String appsCount(String count) {
    return 'Апликације ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Приватне апликације ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Јавне апликације ($count)';
  }

  @override
  String get newVersionAvailable => 'Нова верзија доступна 🎉';

  @override
  String get no => 'Не';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Претплата је успешно отказана. Остаће активна до краја тренутног периода наплате.';

  @override
  String get failedToCancelSubscription => 'Неуспешно отказивање претплате. Молимо покушајте поново.';

  @override
  String get invalidPaymentUrl => 'Неважећи URL плаћања';

  @override
  String get permissionsAndTriggers => 'Дозволе и активирачи';

  @override
  String get chatFeatures => 'Функције за ћаскање';

  @override
  String get uninstall => 'Деинсталирај';

  @override
  String get installs => 'ИНСТАЛАЦИЈЕ';

  @override
  String get priceLabel => 'ЦЕНА';

  @override
  String get updatedLabel => 'АЖУРИРАНО';

  @override
  String get createdLabel => 'НАПРАВЉЕНО';

  @override
  String get featuredLabel => 'ИСТАКНУТО';

  @override
  String get cancelSubscriptionQuestion => 'Отказати претплату?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Да ли сте сигурни да желите да отказете вашу претплату? Наставићете да имате приступ до краја вашег тренутног периода наплате.';

  @override
  String get cancelSubscriptionButton => 'Отказати претплату';

  @override
  String get cancelling => 'Отказивање...';

  @override
  String get betaTesterMessage =>
      'Вештаци сте бета тестер за ову апликацију. Није јавна. Биће јавна када буде одобрена.';

  @override
  String get appUnderReviewMessage =>
      'Ваша апликација је на прегледу и видљива је само вама. Биће јавна када буде одобрена.';

  @override
  String get appRejectedMessage =>
      'Ваша апликација је одбијена. Молимо ажурирајте детаље апликације и поново пошаљите на преглед.';

  @override
  String get invalidIntegrationUrl => 'Неважећи URL интеграције';

  @override
  String get tapToComplete => 'Додирни да завршиш';

  @override
  String get invalidSetupInstructionsUrl => 'Неважећи URL упутстава за подешавање';

  @override
  String get pushToTalk => 'Притисни да говориш';

  @override
  String get summaryPrompt => 'Подсетник за резиме';

  @override
  String get pleaseSelectARating => 'Молимо изаберите оцену';

  @override
  String get reviewAddedSuccessfully => 'Преглед је успешно додан 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Преглед је успешно ажуриран 🚀';

  @override
  String get failedToSubmitReview => 'Неуспешно слање прегледа. Молимо покушајте поново.';

  @override
  String get addYourReview => 'Додајте своју рецензију';

  @override
  String get editYourReview => 'Уредите своју рецензију';

  @override
  String get writeAReviewOptional => 'Напишите прегледа (опционално)';

  @override
  String get submitReview => 'Пошаљи преглед';

  @override
  String get updateReview => 'Ажурирај преглед';

  @override
  String get yourReview => 'Ваш преглед';

  @override
  String get anonymousUser => 'Анониман корисник';

  @override
  String get issueActivatingApp => 'Дошло је до проблема при активирању ове апликације. Молимо покушајте поново.';

  @override
  String get dataAccessNoticeDescription =>
      'Ова апликација ће приступити вашим подацима. Omi AI није одговоран за то како ваши подаци буду коришћени, измењени или избрисани од стране ове апликације';

  @override
  String get copyUrl => 'Копирај URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Пон';

  @override
  String get weekdayTue => 'Ут';

  @override
  String get weekdayWed => 'Сре';

  @override
  String get weekdayThu => 'Чет';

  @override
  String get weekdayFri => 'Пет';

  @override
  String get weekdaySat => 'Суб';

  @override
  String get weekdaySun => 'Нед';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName интеграција ускоро';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Већ извезено на $platform';
  }

  @override
  String get anotherPlatform => 'другу платформу';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Молимо аутентификујте са $serviceName у Поставке > Интеграције задатака';
  }

  @override
  String addingToService(String serviceName) {
    return 'Додавање у $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Додано у $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Неуспешно додавање у $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Дозвола одбијена за Apple подсетнике';

  @override
  String failedToCreateApiKey(String error) {
    return 'Неуспешно стварање API кључа провајдера: $error';
  }

  @override
  String get createAKey => 'Направите кључ';

  @override
  String get apiKeyRevokedSuccessfully => 'API кључ је успешно опозван';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Неуспешно опозивање API кључа: $error';
  }

  @override
  String get omiApiKeys => 'Omi API кључеви';

  @override
  String get apiKeysDescription =>
      'API кључеви се користе за аутентификацију када ваша апликација комуницира са OMI серверу. Дозвољавају вашој апликацији да прави успомене и безбедно приступа другим OMI услугама.';

  @override
  String get aboutOmiApiKeys => 'О Omi API кључевима';

  @override
  String get yourNewKey => 'Ваш нов кључ:';

  @override
  String get copyToClipboard => 'Копирај у клипборд';

  @override
  String get pleaseCopyKeyNow => 'Молимо копирајте сада и запишите га на безбедном месту. ';

  @override
  String get willNotSeeAgain => 'Нећете моћи да га видите поново.';

  @override
  String get revokeKey => 'Опозови кључ';

  @override
  String get revokeApiKeyQuestion => 'Опозови API кључ?';

  @override
  String get revokeApiKeyWarning =>
      'Ова радња не може бити отказана. Било која апликација која користи овај кључ неће моћи да приступи API-ју.';

  @override
  String get revoke => 'Опозови';

  @override
  String get whatWouldYouLikeToCreate => 'Шта би ли желели да направите?';

  @override
  String get createAnApp => 'Направите апликацију';

  @override
  String get createAndShareYourApp => 'Направите и делите своју апликацију';

  @override
  String get itemApp => 'Апликација';

  @override
  String keepItemPublic(String item) {
    return 'Držite $item јавно';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Направити $item јавно?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Направити $item приватно?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Ако направите $item јавно, може га користити свако';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Ако направите $item приватно сада, престаће да ради за све и биће видљиво само вама';
  }

  @override
  String get manageApp => 'Управљај апликацијом';

  @override
  String deleteItemTitle(String item) {
    return 'Обришите $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Обришите $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Да ли сте сигурни да желите да обришете ово $item? Ова радња не може бити отказана.';
  }

  @override
  String get revokeKeyQuestion => 'Опозови кључ?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Да ли сте сигурни да желите да опозовете кључ \"$keyName\"? Ова радња не може бити отказана.';
  }

  @override
  String get createNewKey => 'Направи нов кључ';

  @override
  String get keyNameHint => 'нпр., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Молимо унесите име.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Неуспешно стварање кључа: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Неуспешно стварање кључа. Молимо покушајте поново.';

  @override
  String get keyCreated => 'Кључ направљен';

  @override
  String get keyCreatedMessage => 'Ваш нов кључ је направљен. Молимо копирајте сада. Нећете моћи да га видите поново.';

  @override
  String get keyWord => 'Кључ';

  @override
  String get externalAppAccess => 'Приступ外ње апликације';

  @override
  String get externalAppAccessDescription =>
      'Следеће инсталиране апликације имају外не интеграције и могу приступити вашим подацима, као што су разговори и успомене.';

  @override
  String get noExternalAppsHaveAccess => 'Нема外њих апликација које имају приступ вашим подацима.';

  @override
  String get maximumSecurityE2ee => 'Максимална безбедност (E2EE)';

  @override
  String get e2eeDescription =>
      'Криптировање од краја до краја је золни стандард за приватност. Када је омогућено, ваши подаци су криптовани на вашем уређају пре него што буду послати нашим серверима. То значи да нико, чак ни Omi, не може приступити вашем садржају.';

  @override
  String get importantTradeoffs => 'Важна одступања:';

  @override
  String get e2eeTradeoff1 => '• Неке функције као што су外не интеграције апликација могу бити онемогућене.';

  @override
  String get e2eeTradeoff2 => '• Ако изгубите своју лозинку, ваши подаци не могу бити повраћени.';

  @override
  String get featureComingSoon => 'Ова функција ускоро долази!';

  @override
  String get migrationInProgressMessage => 'Миграција у току. Не можете променити ниво заштите док се не заврши.';

  @override
  String get migrationFailed => 'Миграција неуспешна';

  @override
  String migratingFromTo(String source, String target) {
    return 'Миграција са $source на $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total објеката';
  }

  @override
  String get secureEncryption => 'Безбедна криптција';

  @override
  String get secureEncryptionDescription =>
      'Ваши подаци су криптовани са кључем јединственим за вас на нашим серверима, смештеним на Google Cloud. То значи да ваш сирови садржај није приступачан никоме, укључујући Omi особље или Google, директно из базе podataka.';

  @override
  String get endToEndEncryption => 'Криптирање од краја до краја';

  @override
  String get e2eeCardDescription =>
      'Омогућите за максималну безбедност где само вас можете приступити вашим подацима. Додирни да сазнаш више.';

  @override
  String get dataAlwaysEncrypted =>
      'Без обзира на ниво, ваши подаци су увек криптовани у мирујућем стању и у транзиту.';

  @override
  String get readOnlyScope => 'Само читање';

  @override
  String get fullAccessScope => 'Потпун приступ';

  @override
  String get readScope => 'Читај';

  @override
  String get writeScope => 'Напиши';

  @override
  String get apiKeyCreated => 'API кључ направљен!';

  @override
  String get saveKeyWarning => 'Сачувај овај кључ сада! Нећеш моћи да га видиш поново.';

  @override
  String get yourApiKey => 'ВАШ API КЉУЧ';

  @override
  String get tapToCopy => 'Додирни да копираш';

  @override
  String get copyKey => 'Копирај кључ';

  @override
  String get createApiKey => 'Направи API кључ';

  @override
  String get accessDataProgrammatically => 'Приступи својим подацима програмски';

  @override
  String get keyNameLabel => 'ИМЕ КЉУЧА';

  @override
  String get keyNamePlaceholder => 'нпр., Моја интеграција апликације';

  @override
  String get permissionsLabel => 'ДОЗВОЛЕ';

  @override
  String get permissionsInfoNote => 'R = Читај, W = Напиши. Подразумева се само читање ако ничего нису означено.';

  @override
  String get developerApi => 'Developer API';

  @override
  String get createAKeyToGetStarted => 'Направи кључ да почнеш';

  @override
  String errorWithMessage(String error) {
    return 'Грешка: $error';
  }

  @override
  String get omiTraining => 'Omi обука';

  @override
  String get trainingDataProgram => 'Програм обучних podataka';

  @override
  String get getOmiUnlimitedFree => 'Добијте Omi неограничено бесплатно доприносећи своје податке за обуку AI модела.';

  @override
  String get trainingDataBullets =>
      '• Ваши подаци помажу да се побољшају AI модели\n• Само неоседљиви подаци се деле\n• Потпуно транспарентан процес';

  @override
  String get learnMoreAtOmiTraining => 'Сазнајте више на omi.me/training';

  @override
  String get agreeToContributeData => 'Разумем и слажем се да допринесем своје податке за обуку AI модела';

  @override
  String get submitRequest => 'Пошаљи захтев';

  @override
  String get thankYouRequestUnderReview => 'Хвала! Ваш захтев је на прегледу. Обавестићемо вас када буде одобрен.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Ваш план остаје активан до $date. После тога, изгубићете приступ вашим неограниченим функцијама. Да ли сте сигурни?';
  }

  @override
  String get confirmCancellation => 'Потврди отказивање';

  @override
  String get keepMyPlan => 'Задржи мој план';

  @override
  String get subscriptionSetToCancel => 'Ваша претплата је постављена да се отказе на крају периода.';

  @override
  String get switchedToOnDevice => 'Пребачена на транскрипцију на уређају';

  @override
  String get couldNotSwitchToFreePlan => 'Не могу да пребродам на бесплатни план. Молим вас, покушајте поново.';

  @override
  String get couldNotLoadPlans => 'Не могу да учитам доступне планове. Молим вас, покушајте поново.';

  @override
  String get selectedPlanNotAvailable => 'Изабрани план није доступан. Молим вас, покушајте поново.';

  @override
  String get upgradeToAnnualPlan => 'Надгради на годишњи план';

  @override
  String get importantBillingInfo => 'Важне информације о наплати:';

  @override
  String get monthlyPlanContinues => 'Ваш тренутни месечни план ће се наставити до краја вашег периода наплате';

  @override
  String get paymentMethodCharged =>
      'Ваш постојећи начин плаћања ће бити аутоматски наплаћен када се ваш месечни план заврши';

  @override
  String get annualSubscriptionStarts => 'Ваша 12-месечна годишња претплата ће почети аутоматски после наплате';

  @override
  String get thirteenMonthsCoverage => 'Добићете укупно 13 месеци покривености (тренутни месец + 12 месеци годишње)';

  @override
  String get confirmUpgrade => 'Потврди надградњу';

  @override
  String get confirmPlanChange => 'Потврди промену плана';

  @override
  String get confirmAndProceed => 'Потврди и настави';

  @override
  String get upgradeScheduled => 'Надградња је заказана';

  @override
  String get changePlan => 'Промени план';

  @override
  String get upgradeAlreadyScheduled => 'Ваша надградња на годишњи план је већ заказана';

  @override
  String get youAreOnUnlimitedPlan => 'Налазите се на плану Без ограничења.';

  @override
  String get yourOmiUnleashed => 'Твој Omi, ослобођен. Иди без ограничења за бесконачне могућности.';

  @override
  String planEndedOn(String date) {
    return 'Ваш план је завршио дана $date.\\nПретплатите се поново - одмах ћемо вас наплатити за нов период наплате.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Ваш план је подешен да буде отказан дана $date.\\nПретплатите се поново да бисте задржали своје предности - никаква наплата до $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Ваш годишњи план ће почети аутоматски када се ваш месечни план заврши.';

  @override
  String planRenewsOn(String date) {
    return 'Ваш план се обнављa дана $date.';
  }

  @override
  String get unlimitedConversations => 'Неограничене разговоре';

  @override
  String get askOmiAnything => 'Питај Omi било шта о својој животу';

  @override
  String get unlockOmiInfiniteMemory => 'Отклучај Omi-јеву бесконачну меморију';

  @override
  String get youreOnAnnualPlan => 'Налазите се на годишњем плану';

  @override
  String get alreadyBestValuePlan => 'Већ имате план са најбољом вредношћу. Никаква промена није потребна.';

  @override
  String get unableToLoadPlans => 'Није могуће учитати планове';

  @override
  String get checkConnectionTryAgain => 'Проверите везу и покушајте поново';

  @override
  String get useFreePlan => 'Користи бесплатни план';

  @override
  String get continueText => 'Настави';

  @override
  String get resubscribe => 'Претплати се поново';

  @override
  String get couldNotOpenPaymentSettings => 'Не могу да отворим postavke плаћања. Молим вас, покушајте поново.';

  @override
  String get managePaymentMethod => 'Управљај начином плаћања';

  @override
  String get cancelSubscription => 'Отакажи претплату';

  @override
  String endsOnDate(String date) {
    return 'Завршава се дана $date';
  }

  @override
  String get active => 'Активна';

  @override
  String get freePlan => 'Бесплатни план';

  @override
  String get configure => 'Конфигуриши';

  @override
  String get privacyInformation => 'Информације о приватности';

  @override
  String get yourPrivacyMattersToUs => 'Твоја приватност је важна нама';

  @override
  String get privacyIntroText =>
      'У Omi, озбиљно узимамо вашу приватност. Желимо да будемо транспарентни у вези са подаците које скупљамо и како их користимо да унапредимо наш производ за вас. Ево шта требате знати:';

  @override
  String get whatWeTrack => 'Шта ми пратимо';

  @override
  String get anonymityAndPrivacy => 'Аноним и приватност';

  @override
  String get optInAndOptOutOptions => 'Опције за укупну поард и одустајање';

  @override
  String get ourCommitment => 'Наша обавеза';

  @override
  String get commitmentText =>
      'Обавезани смо да користимо податке које скупљамо само да направимо Omi бољи производ за вас. Ваша приватност и поверење су од крајње важности за нас.';

  @override
  String get thankYouText =>
      'Хвала вам што сте драгоцени корисник Omi. Ако имате неке питање или забринутости, слободно нас контактирајте на team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Поставке WiFi синхронизације';

  @override
  String get enterHotspotCredentials => 'Унесите акредитиве топле тачке вашег телефона';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi синхронизација користи ваш телефон као топлу тачку. Пронађите име и лозинку топле тачке у Поставкама > Лична топла тачка.';

  @override
  String get hotspotNameSsid => 'Назив топле тачке (SSID)';

  @override
  String get exampleIphoneHotspot => 'нпр. iPhone топла тачка';

  @override
  String get password => 'Лозинка';

  @override
  String get enterHotspotPassword => 'Унесите лозинку топле тачке';

  @override
  String get saveCredentials => 'Сачувај акредитиве';

  @override
  String get clearCredentials => 'Обриши акредитиве';

  @override
  String get pleaseEnterHotspotName => 'Молим вас, унесите назив топле тачке';

  @override
  String get wifiCredentialsSaved => 'WiFi акредитиви су сачувани';

  @override
  String get wifiCredentialsCleared => 'WiFi акредитиви су обрисани';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Резиме генерисано за $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Неуспешно генерисање резимеа. Пажите да имате разговоре за тај дан.';

  @override
  String get summaryNotFound => 'Резиме није пронађен';

  @override
  String get yourDaysJourney => 'Путовање вашег дана';

  @override
  String get highlights => 'Истицања';

  @override
  String get unresolvedQuestions => 'Неразрешена питања';

  @override
  String get decisions => 'Одлуке';

  @override
  String get learnings => 'Учења';

  @override
  String get autoDeletesAfterThreeDays => 'Аутоматски брише после 3 дана.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Граф знања је успешно обрисан';

  @override
  String get exportStartedMayTakeFewSeconds => 'Извоз је почео. Ово може да потраје неколико секунди...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Ово ће обрисати све изведене податке графа знања (чворове и конексије). Ваша оригинална меморија остаће безбедна. Граф ће бити обновљен течајом времена или при следећем захтеву.';

  @override
  String get configureDailySummaryDigest => 'Конфигуриши твој дневни резиме активних ставки';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Приступа $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'покренуто од $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription и је $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Је $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Нема конфигурисаног специфичног приступа подаците.';

  @override
  String get basicPlanDescription => '1.200 премиум минута + без ограничења на уређају';

  @override
  String get minutes => 'минута';

  @override
  String get omiHas => 'Omi има:';

  @override
  String get premiumMinutesUsed => 'Премиум минута коришћено.';

  @override
  String get setupOnDevice => 'Конфигуриши на уређају';

  @override
  String get forUnlimitedFreeTranscription => 'за неограничену бесплатну транскрипцију.';

  @override
  String premiumMinsLeft(int count) {
    return '$count премиум минута остало.';
  }

  @override
  String get alwaysAvailable => 'увек доступно.';

  @override
  String get importHistory => 'Историја увоза';

  @override
  String get noImportsYet => 'Нема увоза';

  @override
  String get selectZipFileToImport => 'Изаберите .zip датотеку за увоз!';

  @override
  String get otherDevicesComingSoon => 'Други уређаји долазе ускоро';

  @override
  String get deleteAllLimitlessConversations => 'Избрисати све разговоре без ограничења?';

  @override
  String get deleteAllLimitlessWarning =>
      'Ово ће трајно обрисати све разговоре увезене из Limitless. Ова акција се не може отменити.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Избрисано $count Limitless разговора';
  }

  @override
  String get failedToDeleteConversations => 'Неуспешно брисање разговора';

  @override
  String get deleteImportedData => 'Избриши увезене податке';

  @override
  String get statusPending => 'На чекању';

  @override
  String get statusProcessing => 'Обрада';

  @override
  String get statusCompleted => 'Завршено';

  @override
  String get statusFailed => 'Неуспешно';

  @override
  String nConversations(int count) {
    return '$count разговора';
  }

  @override
  String get pleaseEnterName => 'Молим вас, унесите назив';

  @override
  String get nameMustBeBetweenCharacters => 'Назив мора бити између 2 и 40 карактера';

  @override
  String get deleteSampleQuestion => 'Избрисати узорак?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Да ли сте сигурни да желите да избришете узорак од $name?';
  }

  @override
  String get confirmDeletion => 'Потврди брисање';

  @override
  String deletePersonConfirmation(String name) {
    return 'Да ли сте сигурни да желите да избришете $name? Ово ће такође уклонити све асоцијаторе узорке говора.';
  }

  @override
  String get howItWorksTitle => 'Како функционише?';

  @override
  String get howPeopleWorks =>
      'Када се особа направи, можете да идете на транскрипцију разговора и доделите јој одговарајуће сегменте, на тај начин Omi ће бити способна да препозна и њихов говор!';

  @override
  String get tapToDelete => 'Гаси да избришеш';

  @override
  String get newTag => 'НОВО';

  @override
  String get needHelpChatWithUs => 'Требаш помоћ? Комуницирај са нама';

  @override
  String get localStorageEnabled => 'Локална складишта је омогућена';

  @override
  String get localStorageDisabled => 'Локална складишта је онемогућена';

  @override
  String failedToUpdateSettings(String error) {
    return 'Неуспешна ажурирање поставки: $error';
  }

  @override
  String get privacyNotice => 'Обавештење о приватности';

  @override
  String get recordingsMayCaptureOthers =>
      'Снимања могу захватити гласове других. Пажите да имате сагласност свих учесника пре омогућавања.';

  @override
  String get enable => 'Омогући';

  @override
  String get storeAudioOnPhone => 'Чувај аудио на телефону';

  @override
  String get on => 'Укл.';

  @override
  String get storeAudioDescription =>
      'Чувај све аудио снимке локално на твом телефону. Када је онемогућено, само неуспешни преноси су чувани да бисте уштедели простор за складиштење.';

  @override
  String get enableLocalStorage => 'Омогући локалну складишту';

  @override
  String get cloudStorageEnabled => 'Облак складишта је омогућена';

  @override
  String get cloudStorageDisabled => 'Облак складишта је онемогућена';

  @override
  String get enableCloudStorage => 'Омогући облак складишту';

  @override
  String get storeAudioOnCloud => 'Чувај аудио у облаку';

  @override
  String get cloudStorageDialogMessage =>
      'Ваша снимања у реалном времену ће бити чувана у приватном облак складишту док говорите.';

  @override
  String get storeAudioCloudDescription =>
      'Чувај твоја снимања у реалном времену у приватном облак складишту док говориш. Аудио је захваћен и сачуван безбедно у реалном времену.';

  @override
  String get downloadingFirmware => 'Преузимање фирмвера';

  @override
  String get installingFirmware => 'Инсталирање фирмвера';

  @override
  String get firmwareUpdateWarning => 'Не затварајте апликацију и не гасите уређај. Ово би могло да оштети ваш уређај.';

  @override
  String get firmwareUpdated => 'Фирмвер ажуриран';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Молим вас, поново покрените ваш $deviceName да завршите ажурирање.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Ваш уређај је ажуриран';

  @override
  String get currentVersion => 'Тренутна верзија';

  @override
  String get latestVersion => 'Последња верзија';

  @override
  String get whatsNew => 'Шта је ново';

  @override
  String get installUpdate => 'Инсталирај ажурирање';

  @override
  String get updateNow => 'Ажурирај сада';

  @override
  String get updateGuide => 'Водич за ажурирање';

  @override
  String get checkingForUpdates => 'Проверавање ажурирања';

  @override
  String get checkingFirmwareVersion => 'Проверавање верзије фирмвера...';

  @override
  String get firmwareUpdate => 'Ажурирање фирмвера';

  @override
  String get payments => 'Плаћања';

  @override
  String get connectPaymentMethodInfo => 'Повежи начин плаћања испод да почнеш да прима исплате за своје апликације.';

  @override
  String get selectedPaymentMethod => 'Изабран начин плаћања';

  @override
  String get availablePaymentMethods => 'Доступни начини плаћања';

  @override
  String get activeStatus => 'Активна';

  @override
  String get connectedStatus => 'Повезана';

  @override
  String get notConnectedStatus => 'Није повезана';

  @override
  String get setActive => 'Постави активну';

  @override
  String get getPaidThroughStripe => 'Добиј плаћање за продају своје апликације кроз Stripe';

  @override
  String get monthlyPayouts => 'Месечне исплате';

  @override
  String get monthlyPayoutsDescription => 'Прими месечна плаћања директно на свој рачун када достигнеш \$10 зараде';

  @override
  String get secureAndReliable => 'Безбедно и поузданно';

  @override
  String get stripeSecureDescription => 'Stripe обезбеђује безбедан и благовремен пренос прихода твоје апликације';

  @override
  String get selectYourCountry => 'Изаберите вашу земљу';

  @override
  String get countrySelectionPermanent => 'Ваш избор земље је трајан и не може се касније променити.';

  @override
  String get byClickingConnectNow => 'Кликом на \"Повежи сада\" прихватате';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe уговор о повезаном рачуну';

  @override
  String get errorConnectingToStripe => 'Грешка при повезивању на Stripe! Молим вас, покушајте касније.';

  @override
  String get connectingYourStripeAccount => 'Повезивање вашег Stripe рачуна';

  @override
  String get stripeOnboardingInstructions =>
      'Молим вас, завршите Stripe процес укупне обуке у вашем прегледачу. Ова страна ће се аутоматски ажурирати када буде завршена.';

  @override
  String get failedTryAgain => 'Неуспешно? Покушај поново';

  @override
  String get illDoItLater => 'Урадићу то касније';

  @override
  String get successfullyConnected => 'Успешно повезано!';

  @override
  String get stripeReadyForPayments =>
      'Ваш Stripe рачун је сада спреман да прима плаћања. Можете почети да зарађујете од продаје своје апликације одмах.';

  @override
  String get updateStripeDetails => 'Ажурирај Stripe детаље';

  @override
  String get errorUpdatingStripeDetails => 'Грешка при ажурирању Stripe детаља! Молим вас, покушајте касније.';

  @override
  String get updatePayPal => 'Ажурирај PayPal';

  @override
  String get setUpPayPal => 'Подеси PayPal';

  @override
  String get updatePayPalAccountDetails => 'Ажурирај своје PayPal детаље рачуна';

  @override
  String get connectPayPalToReceivePayments =>
      'Повежи свој PayPal рачун да почнеш да прима плаћања за своје апликације';

  @override
  String get paypalEmail => 'PayPal имејл';

  @override
  String get paypalMeLink => 'PayPal.me веза';

  @override
  String get stripeRecommendation =>
      'Ако је Stripe доступан у вашој земљи, препоручујемо вам да га користите за брже и лакше исплате.';

  @override
  String get updatePayPalDetails => 'Ажурирај PayPal детаље';

  @override
  String get savePayPalDetails => 'Сачувај PayPal детаље';

  @override
  String get pleaseEnterPayPalEmail => 'Молим вас, унесите свој PayPal имејл';

  @override
  String get pleaseEnterPayPalMeLink => 'Молим вас, унесите своју PayPal.me везу';

  @override
  String get doNotIncludeHttpInLink => 'Не укључујте http или https или www у вези';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Молим вас, унесите важећу PayPal.me везу';

  @override
  String get pleaseEnterValidEmail => 'Молим вас, унесите важећу имејл адресу';

  @override
  String get syncingYourRecordings => 'Синхронизација твоја снимања';

  @override
  String get syncYourRecordings => 'Синхронизуј твоја снимања';

  @override
  String get syncNow => 'Синхронизуј сада';

  @override
  String get error => 'Грешка';

  @override
  String get speechSamples => 'Узорци говора';

  @override
  String additionalSampleIndex(String index) {
    return 'Додатни узорак $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Трајање: $seconds секунди';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Додатни узорак говора је уклоњен';

  @override
  String get consentDataMessage =>
      'Настављањем, ваши разговори, снимци и лични подаци биће безбедно ускладиштени на нашим серверима. Ваши аудио снимци и транскрипти се обрађују од стране AI сервиса трећих страна (укључујући Deepgram за транскрипцију и OpenAI за анализу) како би вам пружили увиде засноване на вештачкој интелигенцији и омогућили све функције апликације.';

  @override
  String get tasksEmptyStateMessage =>
      'Активне ставке из твоје разговора ће се појавити овде.\\nГаси + да направиш једну ручно.';

  @override
  String get clearChatAction => 'Обриши разговор';

  @override
  String get enableApps => 'Омогући апликације';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'прикажи више ↓';

  @override
  String get showLess => 'прикажи мање ↑';

  @override
  String get loadingYourRecording => 'Учитавање твог снимања...';

  @override
  String get photoDiscardedMessage => 'Ова фотографија је одбачена јер није била значајна.';

  @override
  String get analyzing => 'Анализирање...';

  @override
  String get searchCountries => 'Претражи земље';

  @override
  String get checkingAppleWatch => 'Проверавање Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Инсталирај Omi на твој\\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Да користиш Apple Watch са Omi, прво мораш да инсталираш Omi апликацију на твом часовнику.';

  @override
  String get openOmiOnAppleWatch => 'Отвори Omi на твој\\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi апликација је инсталирана на твом Apple Watch. Отвори је и гаски Почни да почнеш.';

  @override
  String get openWatchApp => 'Отвори Watch апликацију';

  @override
  String get iveInstalledAndOpenedTheApp => 'Сам инсталирао и открио апликацију';

  @override
  String get unableToOpenWatchApp =>
      'Не могу да отворим Apple Watch апликацију. Молим вас, ручно отворите Watch апликацију на вашем Apple Watch и инсталирајте Omi из одељка \"Доступне апликације\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch је успешно повезан!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch је и даље недостижан. Молим вас, пажите да је Omi апликација отворена на твом часовнику.';

  @override
  String errorCheckingConnection(String error) {
    return 'Грешка при проверавању конексије: $error';
  }

  @override
  String get muted => 'Утишана';

  @override
  String get processNow => 'Процесирај сада';

  @override
  String get finishedConversation => 'Завршио разговор?';

  @override
  String get stopRecordingConfirmation =>
      'Да ли сте сигурни да желите да zaustavите записивање и sažmete разговор сада?';

  @override
  String get conversationEndsManually => 'Разговор ће завршити само ручно.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Разговор је sažet nakon $minutes миnut$suffix без говора.';
  }

  @override
  String get dontAskAgain => 'Не питај ме опет';

  @override
  String get waitingForTranscriptOrPhotos => 'Чека транскрипцију или фотографије...';

  @override
  String get noSummaryYet => 'Нема резимеа';

  @override
  String hints(String text) {
    return 'Савети: $text';
  }

  @override
  String get testConversationPrompt => 'Тестирај разговор Prompt';

  @override
  String get prompt => 'Prompt';

  @override
  String get result => 'Резултат:';

  @override
  String get compareTranscripts => 'Упореди транскрипције';

  @override
  String get notHelpful => 'Није помогло';

  @override
  String get exportTasksWithOneTap => 'Извези активне ставке са једним гаском!';

  @override
  String get inProgress => 'У процесу';

  @override
  String get photos => 'Фотографије';

  @override
  String get rawData => 'Сирови подаци';

  @override
  String get content => 'Садржај';

  @override
  String get noContentToDisplay => 'Нема садржаја за приказ';

  @override
  String get noSummary => 'Нема резимеа';

  @override
  String get updateOmiFirmware => 'Ажурирај omi firmware';

  @override
  String get anErrorOccurredTryAgain => 'Дошло је до грешке. Молим вас, покушајте поново.';

  @override
  String get welcomeBackSimple => 'Добродошли назад';

  @override
  String get addVocabularyDescription => 'Додај речи које Omi треба да препозна durante транскрипције.';

  @override
  String get enterWordsCommaSeparated => 'Унесите речи (одвојено запетом)';

  @override
  String get whenToReceiveDailySummary => 'Када да прими твој дневни резиме';

  @override
  String get checkingNextSevenDays => 'Проверавање наредних 7 дана';

  @override
  String failedToDeleteError(String error) {
    return 'Неуспешно брисање: $error';
  }

  @override
  String get developerApiKeys => 'Кључеви API разработача';

  @override
  String get noApiKeysCreateOne => 'Нема кључева API. Направи једног да почнеш.';

  @override
  String get commandRequired => '⌘ потребно';

  @override
  String get spaceKey => 'Размак';

  @override
  String loadMoreRemaining(String count) {
    return 'Учитај више ($count остало)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Корисник са $percentile%';
  }

  @override
  String get wrappedMinutes => 'минута';

  @override
  String get wrappedConversations => 'разговора';

  @override
  String get wrappedDaysActive => 'дана активна';

  @override
  String get wrappedYouTalkedAbout => 'Причао си о';

  @override
  String get wrappedActionItems => 'Активне ставке';

  @override
  String get wrappedTasksCreated => 'направљене активне ставке';

  @override
  String get wrappedCompleted => 'завршено';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% стопа завршетка';
  }

  @override
  String get wrappedYourTopDays => 'Твоја најбоља дана';

  @override
  String get wrappedBestMoments => 'Најбоља момента';

  @override
  String get wrappedMyBuddies => 'Мој пријатељи';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Не могу да престану да причају о';

  @override
  String get wrappedShow => 'ШОУ';

  @override
  String get wrappedMovie => 'ФИЛМ';

  @override
  String get wrappedBook => 'КЊИГА';

  @override
  String get wrappedCelebrity => 'СЛАВНА ЛИЧНОСТ';

  @override
  String get wrappedFood => 'ХРАНА';

  @override
  String get wrappedMovieRecs => 'Препоруке филмова за пријатеље';

  @override
  String get wrappedBiggest => 'Највећи';

  @override
  String get wrappedStruggle => 'Борба';

  @override
  String get wrappedButYouPushedThrough => 'Али си пробио 💪';

  @override
  String get wrappedWin => 'Победа';

  @override
  String get wrappedYouDidIt => 'Урадио си то! 🎉';

  @override
  String get wrappedTopPhrases => 'Преди 5 фраза';

  @override
  String get wrappedMins => 'мин';

  @override
  String get wrappedConvos => 'разговара';

  @override
  String get wrappedDays => 'дана';

  @override
  String get wrappedMyBuddiesLabel => 'МЕШЕЈ ПРИЈАТЕЉИ';

  @override
  String get wrappedObsessionsLabel => 'ОПСЕДНУТОСТ';

  @override
  String get wrappedStruggleLabel => 'БОРБА';

  @override
  String get wrappedWinLabel => 'ПОБЕДА';

  @override
  String get wrappedTopPhrasesLabel => 'ПРЕДИ ФРАЗА';

  @override
  String get wrappedLetsHitRewind => 'Хајде да се враћамо на твој';

  @override
  String get wrappedGenerateMyWrapped => 'Направи мој Wrapped';

  @override
  String get wrappedProcessingDefault => 'Обрада...';

  @override
  String get wrappedCreatingYourStory => 'Правим твој\\n2025 причу...';

  @override
  String get wrappedSomethingWentWrong => 'Нешто\\nје пошло наниже';

  @override
  String get wrappedAnErrorOccurred => 'Дошло је до грешке';

  @override
  String get wrappedTryAgain => 'Покушај поново';

  @override
  String get wrappedNoDataAvailable => 'Нема доступних podataka';

  @override
  String get wrappedOmiLifeRecap => 'Omi животни преглед';

  @override
  String get wrappedSwipeUpToBegin => 'Плови мене да почнеш';

  @override
  String get wrappedShareText => 'Мој 2025, запамћен од Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Неуспешно дељење. Молим вас, покушајте поново.';

  @override
  String get wrappedFailedToStartGeneration => 'Неуспешно почињање генерисања. Молим вас, покушајте поново.';

  @override
  String get wrappedStarting => 'Почињање...';

  @override
  String get wrappedShare => 'Подели';

  @override
  String get wrappedShareYourWrapped => 'Подели свој Wrapped';

  @override
  String get wrappedMy2025 => 'Мој 2025';

  @override
  String get wrappedRememberedByOmi => 'запамћено од Omi';

  @override
  String get wrappedMostFunDay => 'Најбоље забаве';

  @override
  String get wrappedMostProductiveDay => 'Најпродуктивнија';

  @override
  String get wrappedMostIntenseDay => 'Најинтензивнија';

  @override
  String get wrappedFunniestMoment => 'Најсмешнија';

  @override
  String get wrappedMostCringeMoment => 'Најнезгодна';

  @override
  String get wrappedMinutesLabel => 'минута';

  @override
  String get wrappedConversationsLabel => 'разговора';

  @override
  String get wrappedDaysActiveLabel => 'дана активна';

  @override
  String get wrappedTasksGenerated => 'активне ставке генерисане';

  @override
  String get wrappedTasksCompleted => 'активне ставке завршене';

  @override
  String get wrappedTopFivePhrases => 'Преди 5 фраза';

  @override
  String get wrappedAGreatDay => 'Одличан дан';

  @override
  String get wrappedGettingItDone => 'Завршавање';

  @override
  String get wrappedAChallenge => 'Изазов';

  @override
  String get wrappedAHilariousMoment => 'Смешна момента';

  @override
  String get wrappedThatAwkwardMoment => 'Та неугодна момента';

  @override
  String get wrappedYouHadFunnyMoments => 'Имао си неке смешне момента ове године!';

  @override
  String get wrappedWeveAllBeenThere => 'Сви смо били тамо!';

  @override
  String get wrappedFriend => 'Пријатељ';

  @override
  String get wrappedYourBuddy => 'Твој пријатељ!';

  @override
  String get wrappedNotMentioned => 'Није спомињено';

  @override
  String get wrappedTheHardPart => 'Тешка деловања';

  @override
  String get wrappedPersonalGrowth => 'Лични раст';

  @override
  String get wrappedFunDay => 'Забава';

  @override
  String get wrappedProductiveDay => 'Продуктивна';

  @override
  String get wrappedIntenseDay => 'Интензивна';

  @override
  String get wrappedFunnyMomentTitle => 'Смешна момента';

  @override
  String get wrappedCringeMomentTitle => 'Неугодна момента';

  @override
  String get wrappedYouTalkedAboutBadge => 'Причао си о';

  @override
  String get wrappedCompletedLabel => 'Завршено';

  @override
  String get wrappedMyBuddiesCard => 'Мешеј пријатељи';

  @override
  String get wrappedBuddiesLabel => 'ПРИЈАТЕЉИ';

  @override
  String get wrappedObsessionsLabelUpper => 'ОПСЕДНУТОСТ';

  @override
  String get wrappedStruggleLabelUpper => 'БОРБА';

  @override
  String get wrappedWinLabelUpper => 'ПОБЕДА';

  @override
  String get wrappedTopPhrasesLabelUpper => 'ПРЕДИ ФРАЗА';

  @override
  String get wrappedYourHeader => 'Твој';

  @override
  String get wrappedTopDaysHeader => 'Њихови дана';

  @override
  String get wrappedYourTopDaysBadge => 'Твоја најбоља дана';

  @override
  String get wrappedBestHeader => 'Најбоља';

  @override
  String get wrappedMomentsHeader => 'Момента';

  @override
  String get wrappedBestMomentsBadge => 'Најбоља момента';

  @override
  String get wrappedBiggestHeader => 'Највећи';

  @override
  String get wrappedStruggleHeader => 'Борба';

  @override
  String get wrappedWinHeader => 'Победа';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Али си пробио 💪';

  @override
  String get wrappedYouDidItEmoji => 'Урадио си то! 🎉';

  @override
  String get wrappedHours => 'сати';

  @override
  String get wrappedActions => 'акције';

  @override
  String get multipleSpeakersDetected => 'Открити више говорника';

  @override
  String get multipleSpeakersDescription =>
      'Чини се да има више говорника у записивању. Молим вас, пажите да сте у тихој локацији и покушајте поново.';

  @override
  String get invalidRecordingDetected => 'Открити неважећи записивање';

  @override
  String get notEnoughSpeechDescription => 'Нема довољно говора открити. Молим вас, причајте више и покушајте поново.';

  @override
  String get speechDurationDescription => 'Обавезно говорите најмање 5 секунди и не више од 90.';

  @override
  String get connectionLostDescription => 'Веза је прекинута. Проверите вашу интернет везу и покушајте поново.';

  @override
  String get howToTakeGoodSample => 'Како направити добар узорак?';

  @override
  String get goodSampleInstructions =>
      '1. Уверите се да сте на тихом месту.\n2. Говорите јасно и природно.\n3. Уверите се да је ваш уређај у природној позицији, на вашем врату.\n\nКада буде креиран, можете га увек побољшати или поново направити.';

  @override
  String get noDeviceConnectedUseMic => 'Ниједан уређај није повезан. Биће коришћен микрофон телефона.';

  @override
  String get doItAgain => 'Направи то поново';

  @override
  String get listenToSpeechProfile => 'Слушајте мој профил гласа ➡️';

  @override
  String get recognizingOthers => 'Препознавање осталих 👀';

  @override
  String get keepGoingGreat => 'Наставите, добро вам иде';

  @override
  String get somethingWentWrongTryAgain => 'Нешто је пошло наопако! Покушајте поново касније.';

  @override
  String get uploadingVoiceProfile => 'Отпремање вашег профила гласа....';

  @override
  String get memorizingYourVoice => 'Памћење вашег гласа...';

  @override
  String get personalizingExperience => 'Персонализација вашег искуства...';

  @override
  String get keepSpeakingUntil100 => 'Наставите да говорите док не достигнете 100%.';

  @override
  String get greatJobAlmostThere => 'Одличан посао, скоро сте на крају';

  @override
  String get soCloseJustLittleMore => 'Веома близу, само још мало';

  @override
  String get notificationFrequency => 'Учесталост обавештења';

  @override
  String get controlNotificationFrequency => 'Контролишите колико често Omi шаље активна обавештења.';

  @override
  String get yourScore => 'Ваш резултат';

  @override
  String get dailyScoreBreakdown => 'Преглед дневног резултата';

  @override
  String get todaysScore => 'Данашњи резултат';

  @override
  String get tasksCompleted => 'Завршени задаци';

  @override
  String get completionRate => 'Стопа завршетка';

  @override
  String get howItWorks => 'Како то функционише';

  @override
  String get dailyScoreExplanation =>
      'Ваш дневни резултат је заснован на завршавању задатака. Завршите своје задатке да бисте побољшали резултат!';

  @override
  String get notificationFrequencyDescription => 'Контролишите колико често Omi шаље активна обавештења и подсетнике.';

  @override
  String get sliderOff => 'Искључено';

  @override
  String get sliderMax => 'Максимално';

  @override
  String summaryGeneratedFor(String date) {
    return 'Резиме генерисано за $date';
  }

  @override
  String get failedToGenerateSummary => 'Грешка приликом генерисања резимеа. Уверите се да имате разговоре за тај дан.';

  @override
  String get recap => 'Преглед';

  @override
  String deleteQuoted(String name) {
    return 'Обриши \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Преместите $count разговора на:';
  }

  @override
  String get noFolder => 'Без папке';

  @override
  String get removeFromAllFolders => 'Уклоните из свих папки';

  @override
  String get buildAndShareYourCustomApp => 'Направите и поделите своју прилагођену апликацију';

  @override
  String get searchAppsPlaceholder => 'Претражите 1500+ апликација';

  @override
  String get filters => 'Филтери';

  @override
  String get frequencyOff => 'Искључено';

  @override
  String get frequencyMinimal => 'Минимално';

  @override
  String get frequencyLow => 'Ниско';

  @override
  String get frequencyBalanced => 'Уравнотежено';

  @override
  String get frequencyHigh => 'Високо';

  @override
  String get frequencyMaximum => 'Максимално';

  @override
  String get frequencyDescOff => 'Нема активних обавештења';

  @override
  String get frequencyDescMinimal => 'Само критични подсетници';

  @override
  String get frequencyDescLow => 'Само важна ажурирања';

  @override
  String get frequencyDescBalanced => 'Редовне корисне препоруке';

  @override
  String get frequencyDescHigh => 'Честе проверке';

  @override
  String get frequencyDescMaximum => 'Будите стално укључени';

  @override
  String get clearChatQuestion => 'Очистити разговор?';

  @override
  String get syncingMessages => 'Синхронизација порука са сервером...';

  @override
  String get chatAppsTitle => 'Апликације за разговор';

  @override
  String get selectApp => 'Одаберите апликацију';

  @override
  String get noChatAppsEnabled =>
      'Нема омогућених апликација за разговор.\nДотакните \"Омогући апликације\" да додате неке.';

  @override
  String get disable => 'Искључи';

  @override
  String get photoLibrary => 'Библиотека фотографија';

  @override
  String get chooseFile => 'Одаберите датотеку';

  @override
  String get connectAiAssistantsToYourData => 'Повежите AI асистенте са вашим подацима';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Пратите своје личне циљеве на почетној страни';

  @override
  String get deleteRecording => 'Обриши снимак';

  @override
  String get thisCannotBeUndone => 'Ово не може бити опозвано.';

  @override
  String get sdCard => 'SD картица';

  @override
  String get fromSd => 'Из SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Брз пренос';

  @override
  String get syncingStatus => 'Синхронизација';

  @override
  String get failedStatus => 'Неуспешно';

  @override
  String etaLabel(String time) {
    return 'Процењено време: $time';
  }

  @override
  String get transferMethod => 'Метода преноса';

  @override
  String get fast => 'Брзо';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Телефон';

  @override
  String get cancelSync => 'Отказати синхронизацију';

  @override
  String get cancelSyncMessage => 'Подаци који су већ преузети биће сачувани. Можете наставити касније.';

  @override
  String get syncCancelled => 'Синхронизација отказана';

  @override
  String get deleteProcessedFiles => 'Обриши обрађене датотеке';

  @override
  String get processedFilesDeleted => 'Обрађене датотеке су обрисане';

  @override
  String get wifiEnableFailed => 'Грешка при омогућавању WiFi-ја на уређају. Покушајте поново.';

  @override
  String get deviceNoFastTransfer => 'Ваш уређај не подржава брз пренос. Користите Bluetooth уместо тога.';

  @override
  String get enableHotspotMessage => 'Омогућите точку приступа телефона и покушајте поново.';

  @override
  String get transferStartFailed => 'Грешка при покретању преноса. Покушајте поново.';

  @override
  String get deviceNotResponding => 'Уређај није одговорио. Покушајте поново.';

  @override
  String get invalidWifiCredentials => 'Неважећи учитељи за WiFi. Проверите подешавања точке приступа.';

  @override
  String get wifiConnectionFailed => 'Грешка при повезивању са WiFi-јем. Покушајте поново.';

  @override
  String get sdCardProcessing => 'Обрада SD картице';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Обрада $count снимка. Датотеке ће бити уклоњене са SD картице наконсто.';
  }

  @override
  String get process => 'Обради';

  @override
  String get wifiSyncFailed => 'WiFi синхронизација неуспешна';

  @override
  String get processingFailed => 'Обрада неуспешна';

  @override
  String get downloadingFromSdCard => 'Преузимање са SD картице';

  @override
  String processingProgress(int current, int total) {
    return 'Обрада $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count разговор(а) креирано';
  }

  @override
  String get internetRequired => 'Потребан је интернет';

  @override
  String get processAudio => 'Обради аудио';

  @override
  String get start => 'Почетак';

  @override
  String get noRecordings => 'Нема снимака';

  @override
  String get audioFromOmiWillAppearHere => 'Аудио са вашег Omi уређаја ће се појавити овде';

  @override
  String get deleteProcessed => 'Обриши обрађене';

  @override
  String get tryDifferentFilter => 'Покушајте са другим филтером';

  @override
  String get recordings => 'Снимци';

  @override
  String get enableRemindersAccess => 'Омогућите приступ подсетницима у подешавањима да користите Apple Reminders';

  @override
  String todayAtTime(String time) {
    return 'Данас у $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Јуче у $time';
  }

  @override
  String get lessThanAMinute => 'Мање од минута';

  @override
  String estimatedMinutes(int count) {
    return '~$count минут(а)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count сат(и)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Процењено: $time остаје';
  }

  @override
  String get summarizingConversation => 'Сумирање разговора...\nОво може потрајати неколико секунди';

  @override
  String get resummarizingConversation => 'Поново сумирање разговора...\nОво може потрајати неколико секунди';

  @override
  String get nothingInterestingRetry => 'Ничег занимљивог нет,\nжелите ли да покушате поново?';

  @override
  String get noSummaryForConversation => 'Нема доступног резимеа\nза овај разговор.';

  @override
  String get unknownLocation => 'Непозната локација';

  @override
  String get couldNotLoadMap => 'Грешка при учитавању мапе';

  @override
  String get triggerConversationIntegration => 'Активирај интеграцију креираног разговора';

  @override
  String get webhookUrlNotSet => 'Webhook URL није постављен';

  @override
  String get setWebhookUrlInSettings =>
      'Молимо поставите webhook URL у развојачка подешавања да користите ову функцију.';

  @override
  String get sendWebUrl => 'Пошаљи веб адресу';

  @override
  String get sendTranscript => 'Пошаљи транскрипцију';

  @override
  String get sendSummary => 'Пошаљи резиме';

  @override
  String get debugModeDetected => 'Откривен режим отклањања грешака';

  @override
  String get performanceReduced => 'Перформансе смањене 5-10 пута. Користите режим издања.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Аутоматско затварање за ${seconds}s';
  }

  @override
  String get modelRequired => 'Модел захтеван';

  @override
  String get downloadWhisperModel => 'Молимо преузмите Whisper модел пре него што сачувате.';

  @override
  String get deviceNotCompatible => 'Уређај није компатибилан';

  @override
  String get deviceRequirements => 'Ваш уређај не испуњава захтеве за транскрипцију на уређају.';

  @override
  String get willLikelyCrash => 'Омогућавање овога ће вероватно узроковати пад или замрзавање апликације.';

  @override
  String get transcriptionSlowerLessAccurate => 'Транскрипција ће бити значајно спорија и мање тачна.';

  @override
  String get proceedAnyway => 'Настави свакако';

  @override
  String get olderDeviceDetected => 'Откривен старији уређај';

  @override
  String get onDeviceSlower => 'Транскрипција на уређају може бити спорија на овом уређају.';

  @override
  String get batteryUsageHigher => 'Утрошак батерије ће бити већи него код облачне транскрипције.';

  @override
  String get considerOmiCloud => 'Размотрите коришћење Omi Cloud за боље перформансе.';

  @override
  String get highResourceUsage => 'Висока потрошња ресурса';

  @override
  String get onDeviceIntensive => 'Транскрипција на уређају је рачунски интензивна.';

  @override
  String get batteryDrainIncrease => 'Исцрпљивање батерије ће се значајно повећати.';

  @override
  String get deviceMayWarmUp => 'Уређај може постати топлији при дужој употреби.';

  @override
  String get speedAccuracyLower => 'Брзина и тачност могу бити мање него код облачних модела.';

  @override
  String get cloudProvider => 'Облачни провајдер';

  @override
  String get premiumMinutesInfo =>
      '1.200 премиум минута/месец. Картица \"На уређају\" нуди неограничену бесплатну транскрипцију.';

  @override
  String get viewUsage => 'Погледајте утрошак';

  @override
  String get localProcessingInfo =>
      'Аудио се обрађује локално. Функционише без интернета, приватније је, али больше исцрпљује батерију.';

  @override
  String get model => 'Модел';

  @override
  String get performanceWarning => 'Упозорење о перформансама';

  @override
  String get largeModelWarning =>
      'Овај модел је велик и може узроковати пад апликације или веома спорно покретање на мобилним уређајима.\n\nПрепоручена су \"small\" или \"base\".';

  @override
  String get usingNativeIosSpeech => 'Коришћење изворног iOS препознавања говора';

  @override
  String get noModelDownloadRequired =>
      'Биће коришћен изворни говорни механизам вашег уређаја. Преузимање модела није потребно.';

  @override
  String get modelReady => 'Модел спреман';

  @override
  String get redownload => 'Поново преузми';

  @override
  String get doNotCloseApp => 'Молимо затворите апликацију.';

  @override
  String get downloading => 'Преузимање...';

  @override
  String get downloadModel => 'Преузми модел';

  @override
  String estimatedSize(String size) {
    return 'Процењена величина: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Доступан простор: $space';
  }

  @override
  String get notEnoughSpace => 'Упозорење: Нема довољно простора!';

  @override
  String get download => 'Преузми';

  @override
  String downloadError(String error) {
    return 'Грешка при преузимању: $error';
  }

  @override
  String get cancelled => 'Отказано';

  @override
  String get deviceNotCompatibleTitle => 'Уређај није компатибилан';

  @override
  String get deviceNotMeetRequirements => 'Ваш уређај не испуњава захтеве за транскрипцију на уређају.';

  @override
  String get transcriptionSlowerOnDevice => 'Транскрипција на уређају може бити спорија на овом уређају.';

  @override
  String get computationallyIntensive => 'Транскрипција на уређају је рачунски интензивна.';

  @override
  String get batteryDrainSignificantly => 'Исцрпљивање батерије ће се значајно повећати.';

  @override
  String get premiumMinutesMonth =>
      '1.200 премиум минута/месец. Картица \"На уређају\" нуди неограничену бесплатну транскрипцију. ';

  @override
  String get audioProcessedLocally =>
      'Аудио се обрађује локално. Функционише без интернета, приватније је, али больше исцрпљује батерију.';

  @override
  String get languageLabel => 'Језик';

  @override
  String get modelLabel => 'Модел';

  @override
  String get modelTooLargeWarning =>
      'Овај модел је велик и може узроковати пад апликације или веома спорно покретање на мобилним уређајима.\n\nПрепоручена су \"small\" или \"base\".';

  @override
  String get nativeEngineNoDownload =>
      'Биће коришћен изворни говорни механизам вашег уређаја. Преузимање модела није потребно.';

  @override
  String modelReadyWithName(String model) {
    return 'Модел спреман ($model)';
  }

  @override
  String get reDownload => 'Поново преузми';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Преузимање $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Припремање $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Грешка при преузимању: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Процењена величина: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Доступан простор: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Уграђена директна транскрипција Omi-ја је оптимизована за разговоре у реалном времену са аутоматским препознавањем и дијаризацијом говорника.';

  @override
  String get reset => 'Ресетуј';

  @override
  String get useTemplateFrom => 'Користи шаблон од';

  @override
  String get selectProviderTemplate => 'Одаберите шаблон провајдера...';

  @override
  String get quicklyPopulateResponse => 'Брзо попуните са познатим форматом одговора провајдера';

  @override
  String get quicklyPopulateRequest => 'Брзо попуните са познатим форматом захтева провајдера';

  @override
  String get invalidJsonError => 'Неважећи JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Преузми модел ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Модел: $model';
  }

  @override
  String get device => 'Уређај';

  @override
  String get chatAssistantsTitle => 'Асистенти за разговор';

  @override
  String get permissionReadConversations => 'Читање разговора';

  @override
  String get permissionReadMemories => 'Читање сећања';

  @override
  String get permissionReadTasks => 'Читање задатака';

  @override
  String get permissionCreateConversations => 'Креирање разговора';

  @override
  String get permissionCreateMemories => 'Креирање сећања';

  @override
  String get permissionTypeAccess => 'Приступ';

  @override
  String get permissionTypeCreate => 'Креирање';

  @override
  String get permissionTypeTrigger => 'Активирање';

  @override
  String get permissionDescReadConversations => 'Ова апликација може приступити вашим разговорима.';

  @override
  String get permissionDescReadMemories => 'Ова апликација може приступити вашем сећању.';

  @override
  String get permissionDescReadTasks => 'Ова апликација може приступити вашим задацима.';

  @override
  String get permissionDescCreateConversations => 'Ова апликација може креирати нове разговоре.';

  @override
  String get permissionDescCreateMemories => 'Ова апликација може креирати ново сећање.';

  @override
  String get realtimeListening => 'Слушање у реалном времену';

  @override
  String get setupCompleted => 'Завршено';

  @override
  String get pleaseSelectRating => 'Молимо одаберите оцену';

  @override
  String get writeReviewOptional => 'Напишите рецензију (опционално)';

  @override
  String get setupQuestionsIntro => 'Помогните нам да побољшамо Omi одговарањем на неколико питања. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Шта радите?';

  @override
  String get setupQuestionUsage => '2. Где планирате да користите своју Omi?';

  @override
  String get setupQuestionAge => '3. Који је ваш узрастни опсег?';

  @override
  String get setupAnswerAllQuestions => 'Нисте одговорили на сва питања! 🥺';

  @override
  String get setupSkipHelp => 'Прескочи, не желим да помогnem :C';

  @override
  String get professionEntrepreneur => 'Предузетник';

  @override
  String get professionSoftwareEngineer => 'Инжењер софтвера';

  @override
  String get professionProductManager => 'Управник производа';

  @override
  String get professionExecutive => 'Извршни директор';

  @override
  String get professionSales => 'Продаја';

  @override
  String get professionStudent => 'Студент';

  @override
  String get usageAtWork => 'На послу';

  @override
  String get usageIrlEvents => 'IRL догађаји';

  @override
  String get usageOnline => 'Онлајн';

  @override
  String get usageSocialSettings => 'У социјалним окружењима';

  @override
  String get usageEverywhere => 'Свуда';

  @override
  String get customBackendUrlTitle => 'Прилагођена URL адреса позадине';

  @override
  String get backendUrlLabel => 'URL адреса позадине';

  @override
  String get saveUrlButton => 'Сачувај URL';

  @override
  String get enterBackendUrlError => 'Молимо унесите URL адресу позадине';

  @override
  String get urlMustEndWithSlashError => 'URL адреса мора завршити са \"/\"';

  @override
  String get invalidUrlError => 'Молимо унесите важећу URL адресу';

  @override
  String get backendUrlSavedSuccess => 'URL адреса позадине успешно сачувана!';

  @override
  String get signInTitle => 'Пријава';

  @override
  String get signInButton => 'Пријава';

  @override
  String get enterEmailError => 'Молимо унесите своју имејл адресу';

  @override
  String get invalidEmailError => 'Молимо унесите важећу имејл адресу';

  @override
  String get enterPasswordError => 'Молимо унесите своју лозинку';

  @override
  String get passwordMinLengthError => 'Лозинка мора имати најмање 8 карактера';

  @override
  String get signInSuccess => 'Пријава успешна!';

  @override
  String get alreadyHaveAccountLogin => 'Већ имате налог? Пријавите се';

  @override
  String get emailLabel => 'Имејл';

  @override
  String get passwordLabel => 'Лозинка';

  @override
  String get createAccountTitle => 'Креирај налог';

  @override
  String get nameLabel => 'Име';

  @override
  String get repeatPasswordLabel => 'Поновите лозинку';

  @override
  String get signUpButton => 'Направи налог';

  @override
  String get enterNameError => 'Молимо унесите своје име';

  @override
  String get passwordsDoNotMatch => 'Лозинке се не подударају';

  @override
  String get signUpSuccess => 'Регистрација успешна!';

  @override
  String get loadingKnowledgeGraph => 'Учитавање графа знања...';

  @override
  String get noKnowledgeGraphYet => 'Нема графа знања';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Грађење вашег графа знања из сећања...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Ваш граф знања ће бити изграђен аутоматски док креирате ново сећање.';

  @override
  String get buildGraphButton => 'Направи граф';

  @override
  String get checkOutMyMemoryGraph => 'Погледајте мој граф сећања!';

  @override
  String get getButton => 'Добијање';

  @override
  String openingApp(String appName) {
    return 'Отварање $appName...';
  }

  @override
  String get writeSomething => 'Напишите нешто';

  @override
  String get submitReply => 'Пошаљи одговор';

  @override
  String get editYourReply => 'Уредите одговор';

  @override
  String get replyToReview => 'Одговори на рецензију';

  @override
  String get rateAndReviewThisApp => 'Оцени и рецензирај ову апликацију';

  @override
  String get noChangesInReview => 'Нема промена у рецензији за ажурирање.';

  @override
  String get cantRateWithoutInternet => 'Не можете оценити апликацију без интернет везе.';

  @override
  String get appAnalytics => 'Аналитика апликације';

  @override
  String get learnMoreLink => 'сазнајте више';

  @override
  String get moneyEarned => 'Зарађено';

  @override
  String get writeYourReply => 'Напишите одговор...';

  @override
  String get replySentSuccessfully => 'Одговор успешно послат';

  @override
  String failedToSendReply(String error) {
    return 'Грешка при слању одговора: $error';
  }

  @override
  String get send => 'Пошаљи';

  @override
  String starFilter(int count) {
    return '$count звезда';
  }

  @override
  String get noReviewsFound => 'Нема пронађених рецензија';

  @override
  String get editReply => 'Уредити одговор';

  @override
  String get reply => 'Одговори';

  @override
  String starFilterLabel(int count) {
    return '$count звезда';
  }

  @override
  String get sharePublicLink => 'Дели јавну везу';

  @override
  String get connectedKnowledgeData => 'Повезани подаци знања';

  @override
  String get enterName => 'Унесите име';

  @override
  String get goal => 'ЦИЉ';

  @override
  String get tapToTrackThisGoal => 'Додирните да пратите овај циљ';

  @override
  String get tapToSetAGoal => 'Додирните да поставите циљ';

  @override
  String get processedConversations => 'Обрађени разговори';

  @override
  String get updatedConversations => 'Ажурирани разговори';

  @override
  String get newConversations => 'Нови разговори';

  @override
  String get summaryTemplate => 'Шаблон резимеа';

  @override
  String get suggestedTemplates => 'Предложени шаблони';

  @override
  String get otherTemplates => 'Остали шаблони';

  @override
  String get availableTemplates => 'Доступни шаблони';

  @override
  String get getCreative => 'Будите креативни';

  @override
  String get defaultLabel => 'Подразумевано';

  @override
  String get lastUsedLabel => 'Последњи пут коришћено';

  @override
  String get setDefaultApp => 'Постави подразумевану апликацију';

  @override
  String setDefaultAppContent(String appName) {
    return 'Поставите $appName као подразумевану апликацију за сумирање?\\n\\nОва апликација ће аутоматски бити коришћена за сва будућа резимеа разговора.';
  }

  @override
  String get setDefaultButton => 'Постави подразумевану';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName постављена као подразумевана апликација за сумирање';
  }

  @override
  String get createCustomTemplate => 'Направи прилагођени шаблон';

  @override
  String get allTemplates => 'Сви шаблони';

  @override
  String failedToInstallApp(String appName) {
    return 'Грешка при инсталирању $appName. Покушајте поново.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Грешка при инсталирању $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Означи говорника $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Особа са овим именом већ постоји.';

  @override
  String get selectYouFromList => 'Да бисте означили себе, молимо одаберите \"Ви\" са листе.';

  @override
  String get enterPersonsName => 'Унесите име особе';

  @override
  String get addPerson => 'Додај особу';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Означи остале сегменте од овог говорника ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Означи остале сегменте';

  @override
  String get managePeople => 'Управљање особама';

  @override
  String get shareViaSms => 'Дели преко SMS';

  @override
  String get selectContactsToShareSummary => 'Одаберите контакте са којима желите да поделите резиме разговора';

  @override
  String get searchContactsHint => 'Претражите контакте...';

  @override
  String contactsSelectedCount(int count) {
    return '$count одабрано';
  }

  @override
  String get clearAllSelection => 'Обриши све';

  @override
  String get selectContactsToShare => 'Одаберите контакте за дељење';

  @override
  String shareWithContactCount(int count) {
    return 'Дели са $count контактом';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Дели са $count контаката';
  }

  @override
  String get contactsPermissionRequired => 'Потребна дозвола за контакте';

  @override
  String get contactsPermissionRequiredForSms => 'Дозвола за контакте је потребна за дељење преко SMS';

  @override
  String get grantContactsPermissionForSms => 'Молимо дајте дозволу за контакте за дељење преко SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Нема пронађених контаката са бројевима телефона';

  @override
  String get noContactsMatchSearch => 'Нема контаката који одговарају вашој претрази';

  @override
  String get failedToLoadContacts => 'Грешка при учитавању контаката';

  @override
  String get failedToPrepareConversationForSharing => 'Грешка при припремању разговора за дељење. Покушајте поново.';

  @override
  String get couldNotOpenSmsApp => 'Грешка при отварању SMS апликације. Покушајте поново.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Ево шта смо управо разговарали: $link';
  }

  @override
  String get wifiSync => 'WiFi синхронизација';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item копиран у привремену меморију';
  }

  @override
  String get wifiConnectionFailedTitle => 'Веза неуспешна';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Повезивање на $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Омогући $deviceName WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Повежи на $deviceName';
  }

  @override
  String get recordingDetails => 'Детаљи снимка';

  @override
  String get storageLocationSdCard => 'SD картица';

  @override
  String get storageLocationLimitlessPendant => 'Limitless привезак';

  @override
  String get storageLocationPhone => 'Телефон';

  @override
  String get storageLocationPhoneMemory => 'Телефон (меморија)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Сачувано на $deviceName';
  }

  @override
  String get transferring => 'Пренос у току...';

  @override
  String get transferRequired => 'Потребан пренос';

  @override
  String get downloadingAudioFromSdCard => 'Преузимање аудиа са SD картице вашег уређаја';

  @override
  String get transferRequiredDescription =>
      'Овај снимак је сачуван на SD картици вашег уређаја. Пренесите га на телефон да бисте могли да га слушате или поделите.';

  @override
  String get cancelTransfer => 'Отказати пренос';

  @override
  String get transferToPhone => 'Пренеси на телефон';

  @override
  String get privateAndSecureOnDevice => 'Приватно и сигурно на вашем уређају';

  @override
  String get recordingInfo => 'Информације о снимку';

  @override
  String get transferInProgress => 'Пренос је у току...';

  @override
  String get shareRecording => 'Дели снимак';

  @override
  String get deleteRecordingConfirmation =>
      'Да ли сте сигурни да желите трајно да избришете овај снимак? Ово се не може отказати.';

  @override
  String get recordingIdLabel => 'Шифра записа';

  @override
  String get dateTimeLabel => 'Датум и време';

  @override
  String get durationLabel => 'Трајање';

  @override
  String get audioFormatLabel => 'Облик звука';

  @override
  String get storageLocationLabel => 'Место складишта';

  @override
  String get estimatedSizeLabel => 'Процењена величина';

  @override
  String get deviceModelLabel => 'Модел уређаја';

  @override
  String get deviceIdLabel => 'Шифра уређаја';

  @override
  String get statusLabel => 'Статус';

  @override
  String get statusProcessed => 'Обрађено';

  @override
  String get statusUnprocessed => 'Необрађено';

  @override
  String get switchedToFastTransfer => 'Пребачено на брз пренос';

  @override
  String get transferCompleteMessage => 'Пренос је завршен! Сада можете пустити овај снимак.';

  @override
  String transferFailedMessage(String error) {
    return 'Пренос је неуспешан: $error';
  }

  @override
  String get transferCancelled => 'Пренос је отказан';

  @override
  String get fastTransferEnabled => 'Брз пренос је омогућен';

  @override
  String get bluetoothSyncEnabled => 'Синхронизација путем Bluetooth је омогућена';

  @override
  String get enableFastTransfer => 'Омогући брз пренос';

  @override
  String get fastTransferDescription =>
      'Брз пренос користи WiFi за ~5x бржу брзину. Ваш телефон ће привремено бити повезан на WiFi мрежу вашег Omi уређаја током преноса.';

  @override
  String get internetAccessPausedDuringTransfer => 'Приступ интернету је паузиран током преноса';

  @override
  String get chooseTransferMethodDescription =>
      'Изаберите како ће се снимци преносити са вашег Omi уређаја на телефон.';

  @override
  String get wifiSpeed => '~150 KB/s преко WiFi';

  @override
  String get fiveTimesFaster => '5X БРЖЕ';

  @override
  String get fastTransferMethodDescription =>
      'Прави директну WiFi везу са вашим Omi уређајем. Ваш телефон ће привремено бити одсоединут од обичне WiFi мреже током преноса.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s преко BLE';

  @override
  String get bluetoothMethodDescription =>
      'Користи стандардну Bluetooth Low Energy везу. Спорија али не утиче на вашу WiFi везу.';

  @override
  String get selected => 'Изабрано';

  @override
  String get selectOption => 'Изабери';

  @override
  String get lowBatteryAlertTitle => 'Обавештење о слабој батерији';

  @override
  String get lowBatteryAlertBody => 'Батерија вашег уређаја је скоро празна. Време је за пуњење! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Ваш Omi уређај је одсоединут';

  @override
  String get deviceDisconnectedNotificationBody => 'Поново се повезујте да бисте наставили да користите Omi.';

  @override
  String get firmwareUpdateAvailable => 'Ажурирање фирмвера је доступно';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Ново ажурирање фирмвера ($version) је доступно за ваш Omi уређај. Да ли желите да ажурирате сада?';
  }

  @override
  String get later => 'Касније';

  @override
  String get appDeletedSuccessfully => 'Апликација је успешно избрисана';

  @override
  String get appDeleteFailed => 'Неуспешно брисање апликације. Молим покушајте касније.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Видљивост апликације је успешно промењена. Може потрајати неколико минута да се рефлектује.';

  @override
  String get errorActivatingAppIntegration =>
      'Грешка при активирању апликације. Ако је ово апликација за интеграцију, проверите да ли је подешавање завршено.';

  @override
  String get errorUpdatingAppStatus => 'Дошло је до грешке при ажурирању статуса апликације.';

  @override
  String get calculatingETA => 'Израчунавање...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Остало је приближно $minutes минута';
  }

  @override
  String get aboutAMinuteRemaining => 'Остало је приближно једна минута';

  @override
  String get almostDone => 'Скоро готово...';

  @override
  String get omiSays => 'omi каже';

  @override
  String get analyzingYourData => 'Анализирам ваше податке...';

  @override
  String migratingToProtection(String level) {
    return 'Пребацивање на $level заштиту...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Нема података за пребацивање. Завршавање...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Пребацивање $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Сви објекти су пребачени. Завршавање...';

  @override
  String get migrationErrorOccurred => 'Дошло је до грешке при пребацивању. Молим покушајте поново.';

  @override
  String get migrationComplete => 'Пребацивање је завршено!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Ваши подаци су сада заштићени новим $level подешавањима.';
  }

  @override
  String get chatsLowercase => 'разговори';

  @override
  String get dataLowercase => 'подаци';

  @override
  String get fallNotificationTitle => 'Ауч';

  @override
  String get fallNotificationBody => 'Да ли сте пали?';

  @override
  String get importantConversationTitle => 'Важан разговор';

  @override
  String get importantConversationBody => 'Управо сте имали важан разговор. Додирните да делите резиме са другима.';

  @override
  String get templateName => 'Назив шаблона';

  @override
  String get templateNameHint => 'нпр. Извлачач ставки за састанке';

  @override
  String get nameMustBeAtLeast3Characters => 'Назив мора имати најмање 3 карактера';

  @override
  String get conversationPromptHint =>
      'нпр. Извуците ставке за акцију, донета решења и кључне закључке из дате разговора.';

  @override
  String get pleaseEnterAppPrompt => 'Молим унесите упутство за вашу апликацију';

  @override
  String get promptMustBeAtLeast10Characters => 'Упутство мора имати најмање 10 карактера';

  @override
  String get anyoneCanDiscoverTemplate => 'Свако може открити ваш шаблон';

  @override
  String get onlyYouCanUseTemplate => 'Само вии можете користити овај шаблон';

  @override
  String get generatingDescription => 'Генерисање описа...';

  @override
  String get creatingAppIcon => 'Прављење иконе апликације...';

  @override
  String get installingApp => 'Инсталирање апликације...';

  @override
  String get appCreatedAndInstalled => 'Апликација је креирана и инсталирана!';

  @override
  String get appCreatedSuccessfully => 'Апликација је успешно креирана!';

  @override
  String get failedToCreateApp => 'Неуспешно прављење апликације. Молим покушајте поново.';

  @override
  String get addAppSelectCoreCapability =>
      'Молим одаберите једну другу основну способност за вашу апликацију да наставите';

  @override
  String get addAppSelectPaymentPlan => 'Молим одаберите план плаћања и унесите цену за вашу апликацију';

  @override
  String get addAppSelectCapability => 'Молим одаберите најмање једну способност за вашу апликацију';

  @override
  String get addAppSelectLogo => 'Молим одаберите логотип за вашу апликацију';

  @override
  String get addAppEnterChatPrompt => 'Молим унесите упутство за чет за вашу апликацију';

  @override
  String get addAppEnterConversationPrompt => 'Молим унесите упутство за разговор за вашу апликацију';

  @override
  String get addAppSelectTriggerEvent => 'Молим одаберите дogan event за вашу апликацију';

  @override
  String get addAppEnterWebhookUrl => 'Молим унесите webhook URL за вашу апликацију';

  @override
  String get addAppSelectCategory => 'Молим одаберите категорију за вашу апликацију';

  @override
  String get addAppFillRequiredFields => 'Молим попуните сва обавезна поља исправно';

  @override
  String get addAppUpdatedSuccess => 'Апликација је успешно ажурирана 🚀';

  @override
  String get addAppUpdateFailed => 'Неуспешно ажурирање апликације. Молим покушајте касније';

  @override
  String get addAppSubmittedSuccess => 'Апликација је успешно послата 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Грешка при отварању избирача датотека: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Грешка при избору слике: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Дозвола за слике је одбијена. Молим дозволите приступ сликама да одабрате слику';

  @override
  String get addAppErrorSelectingImageRetry => 'Грешка при избору слике. Молим покушајте поново.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Грешка при избору смањене слике: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Грешка при избору смањене слике. Молим покушајте поново.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Остале способности се не могу одабрати са Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona се не може одабрати са осталим способностима';

  @override
  String get paymentFailedToFetchCountries => 'Неуспешно преузимање подржаних земаља. Молим покушајте касније.';

  @override
  String get paymentFailedToSetDefault => 'Неуспешно подешавање подразумеване методе плаћања. Молим покушајте касније.';

  @override
  String get paymentFailedToSavePaypal => 'Неуспешно чување PayPal детаља. Молим покушајте касније.';

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
  String get paymentStatusConnected => 'Повезано';

  @override
  String get paymentStatusNotConnected => 'Није повезано';

  @override
  String get paymentAppCost => 'Цена апликације';

  @override
  String get paymentEnterValidAmount => 'Молим унесите исправну суму';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Молим унесите суму већу од 0';

  @override
  String get paymentPlan => 'План плаћања';

  @override
  String get paymentNoneSelected => 'Ништа није изабрано';

  @override
  String get aiGenPleaseEnterDescription => 'Молим унесите опис за вашу апликацију';

  @override
  String get aiGenCreatingAppIcon => 'Прављење иконе апликације...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Дошло је до грешке: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Апликација је успешно креирана!';

  @override
  String get aiGenFailedToCreateApp => 'Неуспешно прављење апликације';

  @override
  String get aiGenErrorWhileCreatingApp => 'Дошло је до грешке при прављењу апликације';

  @override
  String get aiGenFailedToGenerateApp => 'Неуспешна генерација апликације. Молим покушајте поново.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Неуспешна регенерација иконе';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Молим прво генеришите апликацију';

  @override
  String get nextButton => 'Даље';

  @override
  String get connectOmiDevice => 'Повежи Omi уређај';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Прелазите са Неограниченог плана на $title. Да ли сте сигурни да желите да наставите?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Надоградња је заказана! Ваш месечни план наставља до краја периода наплате, а затим се аутоматски пребацује на годишњи.';

  @override
  String get couldNotSchedulePlanChange => 'Није могуће заказати промену плана. Молим покушајте поново.';

  @override
  String get subscriptionReactivatedDefault =>
      'Ваша претплата је реактивирана! Нема наплате сада - биће вам наплаћено на крају текућег периода.';

  @override
  String get subscriptionSuccessfulCharged => 'Претплата је успешна! Наплаћена вам је за нови период наплате.';

  @override
  String get couldNotProcessSubscription => 'Није могуће обработити претплату. Молим покушајте поново.';

  @override
  String get couldNotLaunchUpgradePage => 'Није могуће отворити страну за надоградњу. Молим покушајте поново.';

  @override
  String get transcriptionJsonPlaceholder => 'Уклоните вашу JSON конфигурацију овде...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Грешка при отварању избирача датотека: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Грешка: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Разговори су успешно спојени';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count разговора је успешно спојено';
  }

  @override
  String get actionItemReminderTitle => 'Omi подсетник';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName је одсоединут';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Молим повезујте се да наставите са коришћењем $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Пријави се';

  @override
  String get onboardingYourName => 'Ваше име';

  @override
  String get onboardingLanguage => 'Језик';

  @override
  String get onboardingPermissions => 'Дозволе';

  @override
  String get onboardingComplete => 'Заврши';

  @override
  String get onboardingWelcomeToOmi => 'Добро дошли у Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Расскажите нам о себи';

  @override
  String get onboardingChooseYourPreference => 'Одаберите своју преференцу';

  @override
  String get onboardingGrantRequiredAccess => 'Дајте потребан приступ';

  @override
  String get onboardingYoureAllSet => 'Сви сте спремни';

  @override
  String get searchTranscriptOrSummary => 'Претражите транскрипт или резиме...';

  @override
  String get myGoal => 'Мој циљ';

  @override
  String get appNotAvailable => 'Упс! Чини се да апликација коју тражите није доступна.';

  @override
  String get failedToConnectTodoist => 'Неуспешна веза са Todoist';

  @override
  String get failedToConnectAsana => 'Неуспешна веза са Asana';

  @override
  String get failedToConnectGoogleTasks => 'Неуспешна веза са Google Tasks';

  @override
  String get failedToConnectClickUp => 'Неуспешна веза са ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Неуспешна веза са $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Успешно повезани са Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Неуспешна веза са Todoist. Молим покушајте поново.';

  @override
  String get successfullyConnectedAsana => 'Успешно повезани са Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Неуспешна веза са Asana. Молим покушајте поново.';

  @override
  String get successfullyConnectedGoogleTasks => 'Успешно повезани са Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Неуспешна веза са Google Tasks. Молим покушајте поново.';

  @override
  String get successfullyConnectedClickUp => 'Успешно повезани са ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Неуспешна веза са ClickUp. Молим покушајте поново.';

  @override
  String get successfullyConnectedNotion => 'Успешно повезани са Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Неуспешна освежавање статуса Notion povezаности.';

  @override
  String get successfullyConnectedGoogle => 'Успешно повезани са Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Неуспешна освежавање статуса Google povezаности.';

  @override
  String get successfullyConnectedWhoop => 'Успешно повезани са Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Неуспешна освежавање статуса Whoop povezаности.';

  @override
  String get successfullyConnectedGitHub => 'Успешно повезани са GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Неуспешна освежавање статуса GitHub povezаности.';

  @override
  String get authFailedToSignInWithGoogle => 'Неуспешна пријава са Google, молим покушајте поново.';

  @override
  String get authenticationFailed => 'Аутентификација је неуспешна. Молим покушајте поново.';

  @override
  String get authFailedToSignInWithApple => 'Неуспешна пријава са Apple, молим покушајте поново.';

  @override
  String get authFailedToRetrieveToken => 'Неуспешно преузимање firebase токена, молим покушајте поново.';

  @override
  String get authUnexpectedErrorFirebase => 'Неочекивана грешка при пријави, Firebase грешка, молим покушајте поново.';

  @override
  String get authUnexpectedError => 'Неочекивана грешка при пријави, молим покушајте поново';

  @override
  String get authFailedToLinkGoogle => 'Неуспешна повезивање са Google, молим покушајте поново.';

  @override
  String get authFailedToLinkApple => 'Неуспешна повезивање са Apple, молим покушајте поново.';

  @override
  String get onboardingBluetoothRequired => 'Дозвола за Bluetooth је потребна да бисте се повезали на ваш уређај.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Дозвола за Bluetooth је одбијена. Молим дајте дозволу у Системским преферентијама.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Статус дозволе за Bluetooth: $status. Молим проверите Системске преференције.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Неуспешна провера дозволе за Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Дозвола за обавештења је одбијена. Молим дајте дозволу у Системским преферентијама.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Дозвола за обавештења је одбијена. Молим дајте дозволу у Системским преферентијама > Обавештења.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Статус дозволе за обавештења: $status. Молим проверите Системске преференције.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Неуспешна провера дозволе за обавештења: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Молим дајте дозволу за локацију у Подешавањима > Приватност и безбедност > Услуге локације';

  @override
  String get onboardingMicrophoneRequired => 'Дозвола за микрофон је потребна за снимање.';

  @override
  String get onboardingMicrophoneDenied =>
      'Дозвола за микрофон је одбијена. Молим дајте дозволу у Системским преферентијама > Приватност и безбедност > Микрофон.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Статус дозволе за микрофон: $status. Молим проверите Системске преференције.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Неуспешна провера дозволе за микрофон: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Дозвола за снимање екрана је потребна за снимање системског звука.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Дозвола за снимање екрана је одбијена. Молим дајте дозволу у Системским преферентијама > Приватност и безбедност > Снимање екрана.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Статус дозволе за снимање екрана: $status. Молим проверите Системске преференције.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Неуспешна провера дозволе за снимање екрана: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Дозвола за приступачност је потребна за детектовање веб сајта мајтинга.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Статус дозволе за приступачност: $status. Молим проверите Системске преференције.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Неуспешна провера дозволе за приступачност: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Снимање камере није доступно на овој платформи';

  @override
  String get msgCameraPermissionDenied => 'Дозвола за камеру је одбијена. Молим дозволите приступ камери';

  @override
  String msgCameraAccessError(String error) {
    return 'Грешка при приступу камери: $error';
  }

  @override
  String get msgPhotoError => 'Грешка при прављењу слике. Молим покушајте поново.';

  @override
  String get msgMaxImagesLimit => 'Можете одабрати максимално 4 слике';

  @override
  String msgFilePickerError(String error) {
    return 'Грешка при отварању избирача датотека: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Грешка при избору слика: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Дозвола за слике је одбијена. Молим дозволите приступ сликама да одабрате слике';

  @override
  String get msgSelectImagesGenericError => 'Грешка при избору слика. Молим покушајте поново.';

  @override
  String get msgMaxFilesLimit => 'Можете одабрати максимално 4 датотеке';

  @override
  String msgSelectFilesError(String error) {
    return 'Грешка при избору датотека: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Грешка при избору датотека. Молим покушајте поново.';

  @override
  String get msgUploadFileFailed => 'Неуспешно отпремање датотеке, молим покушајте касније';

  @override
  String get msgReadingMemories => 'Читам ваше успомене...';

  @override
  String get msgLearningMemories => 'Учим из ваших успомена...';

  @override
  String get msgUploadAttachedFileFailed => 'Неуспешно отпремање приложене датотеке.';

  @override
  String captureRecordingError(String error) {
    return 'Дошло је до грешке при снимању: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Снимање је заустављено: $reason. Можда ћете морати да поново повежете екстерне дисплеје или да поново почнете снимање.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Потребна је дозвола за микрофон';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Дајте дозволу за микрофон у Системским преферентијама';

  @override
  String get captureScreenRecordingPermissionRequired => 'Потребна је дозвола за снимање екрана';

  @override
  String get captureDisplayDetectionFailed => 'Детектовање дисплеја је неуспешно. Снимање је заустављено.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Неисправан webhook URL за аудио бајтове';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Неисправан webhook URL за реално време транскрипта';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Неисправан webhook URL за креирани разговор';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Неисправан webhook URL за дневни резиме';

  @override
  String get devModeSettingsSaved => 'Подешавања су сачувана!';

  @override
  String get voiceFailedToTranscribe => 'Неуспешна транскрипција аудиа';

  @override
  String get locationPermissionRequired => 'Потребна је дозвола за локацију';

  @override
  String get locationPermissionContent =>
      'Брз пренос захтева дозволу за локацију да би се верификовала WiFi веза. Молим дајте дозволу за локацију да наставите.';

  @override
  String get pdfTranscriptExport => 'Извоз транскрипта';

  @override
  String get pdfConversationExport => 'Извоз разговора';

  @override
  String pdfTitleLabel(String title) {
    return 'Наслов: $title';
  }

  @override
  String get conversationNewIndicator => 'Ново 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count слика';
  }

  @override
  String get mergingStatus => 'Спајање...';

  @override
  String timeSecsSingular(int count) {
    return '$count сек';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count секи';
  }

  @override
  String timeMinSingular(int count) {
    return '$count мин';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count мина';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins мина $secs секи';
  }

  @override
  String timeHourSingular(int count) {
    return '$count час';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count часова';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours часова $mins мина';
  }

  @override
  String timeDaySingular(int count) {
    return '$count дан';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count дана';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days дана $hours часова';
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
  String get moveToFolder => 'Премести у фасциклу';

  @override
  String get noFoldersAvailable => 'Нема доступних фасцикли';

  @override
  String get newFolder => 'Нова фасцикла';

  @override
  String get color => 'Боја';

  @override
  String get waitingForDevice => 'Чекање на уређај...';

  @override
  String get saySomething => 'Реците нешто...';

  @override
  String get initialisingSystemAudio => 'Инијализирање системског звука';

  @override
  String get stopRecording => 'Заустави снимање';

  @override
  String get continueRecording => 'Настави снимање';

  @override
  String get initialisingRecorder => 'Инијализирање снимача';

  @override
  String get pauseRecording => 'Паузирај снимање';

  @override
  String get resumeRecording => 'Настави снимање';

  @override
  String get noDailyRecapsYet => 'Нема дневних резимеа за сада';

  @override
  String get dailyRecapsDescription => 'Ваши дневни резимеи ће се појавити овде када буду генерисани';

  @override
  String get chooseTransferMethod => 'Одаберите метод преноса';

  @override
  String get fastTransferSpeed => '~150 KB/s преко WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Откривена велика временска разлика ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Откривене велике временске разлике ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Уређај не подржава WiFi синхронизацију, пребацивање на Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health није доступна на овом уређају';

  @override
  String get downloadAudio => 'Преузми звук';

  @override
  String get audioDownloadSuccess => 'Звук је успешно преузет';

  @override
  String get audioDownloadFailed => 'Неуспешно преузимање звука';

  @override
  String get downloadingAudio => 'Преузимање звука...';

  @override
  String get shareAudio => 'Дели звук';

  @override
  String get preparingAudio => 'Припремање звука';

  @override
  String get gettingAudioFiles => 'Преузимање аудио датотека...';

  @override
  String get downloadingAudioProgress => 'Преузимање звука';

  @override
  String get processingAudio => 'Обрада звука';

  @override
  String get combiningAudioFiles => 'Комбиновање аудио датотека...';

  @override
  String get audioReady => 'Звук је спреман';

  @override
  String get openingShareSheet => 'Отварање листе дељења...';

  @override
  String get audioShareFailed => 'Дељење је неуспешно';

  @override
  String get dailyRecaps => 'Дневни резимеи';

  @override
  String get removeFilter => 'Уклони филтер';

  @override
  String get categoryConversationAnalysis => 'Анализа разговора';

  @override
  String get categoryHealth => 'Здравље';

  @override
  String get categoryEducation => 'Образовање';

  @override
  String get categoryCommunication => 'Комуникација';

  @override
  String get categoryEmotionalSupport => 'Емоционална подршка';

  @override
  String get categoryProductivity => 'Продуктивност';

  @override
  String get categoryEntertainment => 'Забава';

  @override
  String get categoryFinancial => 'Финансије';

  @override
  String get categoryTravel => 'Путовање';

  @override
  String get categorySafety => 'Безбедност';

  @override
  String get categoryShopping => 'Куповање';

  @override
  String get categorySocial => 'Друштво';

  @override
  String get categoryNews => 'Вести';

  @override
  String get categoryUtilities => 'Услужни програми';

  @override
  String get categoryOther => 'Остало';

  @override
  String get capabilityChat => 'Чет';

  @override
  String get capabilityConversations => 'Разговори';

  @override
  String get capabilityExternalIntegration => 'Екстерна интеграција';

  @override
  String get capabilityNotification => 'Обавештење';

  @override
  String get triggerAudioBytes => 'Аудио бајтови';

  @override
  String get triggerConversationCreation => 'Прављење разговора';

  @override
  String get triggerTranscriptProcessed => 'Транскрипт је обрађен';

  @override
  String get actionCreateConversations => 'Прави разговоре';

  @override
  String get actionCreateMemories => 'Прави успомене';

  @override
  String get actionReadConversations => 'Читај разговоре';

  @override
  String get actionReadMemories => 'Читај успомене';

  @override
  String get actionReadTasks => 'Читај задатке';

  @override
  String get scopeUserName => 'Користничко име';

  @override
  String get scopeUserFacts => 'Кориснички чињенице';

  @override
  String get scopeUserConversations => 'Кориснички разговори';

  @override
  String get scopeUserChat => 'Кориснички чет';

  @override
  String get capabilitySummary => 'Резиме';

  @override
  String get capabilityFeatured => 'Препоручено';

  @override
  String get capabilityTasks => 'Задаци';

  @override
  String get capabilityIntegrations => 'Интеграције';

  @override
  String get categoryProductivityLifestyle => 'Продуктивност и начин живота';

  @override
  String get categorySocialEntertainment => 'Друштво и забава';

  @override
  String get categoryProductivityTools => 'Продуктивност и алати';

  @override
  String get categoryPersonalWellness => 'Лично добростање и начин живота';

  @override
  String get rating => 'Оцена';

  @override
  String get categories => 'Категорије';

  @override
  String get sortBy => 'Сортирај';

  @override
  String get highestRating => 'Највиша оцена';

  @override
  String get lowestRating => 'Најнижа оцена';

  @override
  String get resetFilters => 'Ресетуј филтере';

  @override
  String get applyFilters => 'Примени филтере';

  @override
  String get mostInstalls => 'Највише инсталација';

  @override
  String get couldNotOpenUrl => 'Не могу отворити УРЛ. Покушај поново.';

  @override
  String get newTask => 'Нов задатак';

  @override
  String get viewAll => 'Погледај све';

  @override
  String get addTask => 'Додај задатак';

  @override
  String get addMcpServer => 'Додај MCP сервер';

  @override
  String get connectExternalAiTools => 'Повежи екстерне ВИ алате';

  @override
  String get mcpServerUrl => 'MCP сервер УРЛ';

  @override
  String mcpServerConnected(int count) {
    return '$count алата су успешно повезана';
  }

  @override
  String get mcpConnectionFailed => 'Неуспело повезивање на MCP сервер';

  @override
  String get authorizingMcpServer => 'Аутентификовање...';

  @override
  String get whereDidYouHearAboutOmi => 'Како си сазнао за нас?';

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
  String get friendWordOfMouth => 'Пријатељ';

  @override
  String get otherSource => 'Друго';

  @override
  String get pleaseSpecify => 'Молимо наведи';

  @override
  String get event => 'Догађај';

  @override
  String get coworker => 'Колега';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google претрага';

  @override
  String get audioPlaybackUnavailable => 'Аудио датотека није доступна за пуштање';

  @override
  String get audioPlaybackFailed => 'Не могу пустити аудио. Датотека може бити оштећена или недостаје.';

  @override
  String get connectionGuide => 'Водич за повезивање';

  @override
  String get iveDoneThis => 'Урадио/ла сам ово';

  @override
  String get pairNewDevice => 'Упари нов уређај';

  @override
  String get dontSeeYourDevice => 'Не видиш свој уређај?';

  @override
  String get reportAnIssue => 'Пријави проблем';

  @override
  String get pairingTitleOmi => 'Укључи Omi';

  @override
  String get pairingDescOmi => 'Притисни и држи уређај док се не вибрира да га укључиш.';

  @override
  String get pairingTitleOmiDevkit => 'Постави Omi DevKit у режим паривања';

  @override
  String get pairingDescOmiDevkit =>
      'Притисни дугме једном да укључиш. LED ће трептати наранџасто када је у режиму паривања.';

  @override
  String get pairingTitleOmiGlass => 'Укључи Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Укључи притиском на боково дугме 3 секунде.';

  @override
  String get pairingTitlePlaudNote => 'Постави Plaud Note у режим паривања';

  @override
  String get pairingDescPlaudNote =>
      'Притисни и држи боково дугме 2 секунде. Црвена LED ће трептати када је спремна за паривање.';

  @override
  String get pairingTitleBee => 'Постави Bee у режим паривања';

  @override
  String get pairingDescBee => 'Притисни дугме 5 пута узастопно. Светло ће почети да трепти плаво и зелено.';

  @override
  String get pairingTitleLimitless => 'Постави Limitless у режим паривања';

  @override
  String get pairingDescLimitless =>
      'Када су светла видљива, притисни једном и затим притисни и држи док уређај не покаже розо светло, затим отпусти.';

  @override
  String get pairingTitleFriendPendant => 'Постави Friend Pendant у режим паривања';

  @override
  String get pairingDescFriendPendant =>
      'Притисни дугме на привеску да га укључиш. Аутоматски ће ући у режим паривања.';

  @override
  String get pairingTitleFieldy => 'Постави Fieldy у режим паривања';

  @override
  String get pairingDescFieldy => 'Притисни и држи уређај док се светло не појави да га укључиш.';

  @override
  String get pairingTitleAppleWatch => 'Повежи Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Инсталирај и отвори Omi апликацију на Apple Watch, затим притисни \"Повежи\" у апликацији.';

  @override
  String get pairingTitleNeoOne => 'Постави Neo One у режим паривања';

  @override
  String get pairingDescNeoOne => 'Притисни и држи дугме за напајање док LED не трепти. Уређај ће бити открив.';

  @override
  String get downloadingFromDevice => 'Преузимање са уређаја';

  @override
  String get reconnectingToInternet => 'Поновно повезивање на интернет...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Слање $current од $total';
  }

  @override
  String get processingOnServer => 'Обработка на серверу...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Обработка... $current/$total сегмената';
  }

  @override
  String get processedStatus => 'Обработена';

  @override
  String get corruptedStatus => 'Оштећена';

  @override
  String nPending(int count) {
    return '$count на чекању';
  }

  @override
  String nProcessed(int count) {
    return '$count обработена';
  }

  @override
  String get synced => 'Синхронизована';

  @override
  String get noPendingRecordings => 'Нема снимака на чекању';

  @override
  String get noProcessedRecordings => 'Нема обработених снимака';

  @override
  String get pending => 'На чекању';

  @override
  String whatsNewInVersion(String version) {
    return 'Шта је ново у верзији $version';
  }

  @override
  String get addToYourTaskList => 'Додај на твој списак задатака?';

  @override
  String get failedToCreateShareLink => 'Неуспело прављење линка за дељење';

  @override
  String get deleteGoal => 'Избриши циљ';

  @override
  String get deviceUpToDate => 'Твој уређај је најновија верзија';

  @override
  String get wifiConfiguration => 'WiFi конфигурација';

  @override
  String get wifiConfigurationSubtitle => 'Унеси своје WiFi акредитиве да би уређај могао да преузме firmware.';

  @override
  String get networkNameSsid => 'Назив мреже (SSID)';

  @override
  String get enterWifiNetworkName => 'Унеси назив WiFi мреже';

  @override
  String get enterWifiPassword => 'Унеси WiFi лозинку';

  @override
  String get appIconLabel => 'Икона апликације';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Ево шта знам о теби';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Ова мапа се ажурира док Omi учи из твојих разговора.';

  @override
  String get apiEnvironment => 'API окружење';

  @override
  String get apiEnvironmentDescription => 'Одабери са којим backend-ом да се повежеш';

  @override
  String get production => 'Производна верзија';

  @override
  String get staging => 'Staging';

  @override
  String get switchRequiresRestart => 'Преуслањање захтева рестартовање апликације';

  @override
  String get switchApiConfirmTitle => 'Промени API окружење';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Промени на $environment? Мораћеш затворити и отворити апликацију да би се промене применила.';
  }

  @override
  String get switchAndRestart => 'Промени';

  @override
  String get stagingDisclaimer =>
      'Staging може бити пун грешака, има неусаглашене перформансе и подаци могу бити изгубљени. Користи само за тестирање.';

  @override
  String get apiEnvSavedRestartRequired => 'Сачувано. Затвори и поново отвори апликацију да би се применила.';

  @override
  String get shared => 'Дељено';

  @override
  String get onlyYouCanSeeConversation => 'Само ти можеш видети овај разговор';

  @override
  String get anyoneWithLinkCanView => 'Било ко са линком може видети';

  @override
  String get tasksCleanTodayTitle => 'Очисти данашње задатке?';

  @override
  String get tasksCleanTodayMessage => 'Ово ће уклонити само време истека';

  @override
  String get tasksOverdue => 'Просрочени';

  @override
  String get phoneCallsWithOmi => 'Телефонски позиви са Omi';

  @override
  String get phoneCallsSubtitle => 'Направи позиве са трансцирпцијом у реално време';

  @override
  String get phoneSetupStep1Title => 'Потврди твој телефонски број';

  @override
  String get phoneSetupStep1Subtitle => 'Позваћемо те да потврдимо да је твој';

  @override
  String get phoneSetupStep2Title => 'Унеси код за потврду';

  @override
  String get phoneSetupStep2Subtitle => 'Кратки код који ћеш унети у позиву';

  @override
  String get phoneSetupStep3Title => 'Почни да позиваш своје контакте';

  @override
  String get phoneSetupStep3Subtitle => 'Са трансцирпцијом у реално време';

  @override
  String get phoneGetStarted => 'Почни';

  @override
  String get callRecordingConsentDisclaimer => 'Снимање позива може захтевати сагласност у твој јурисдикцији';

  @override
  String get enterYourNumber => 'Унеси свој број';

  @override
  String get phoneNumberCallerIdHint => 'Када буде потврђен, ово постаје твој ID позиваоца';

  @override
  String get phoneNumberHint => 'Телефонски број';

  @override
  String get failedToStartVerification => 'Неуспело покретање верификације';

  @override
  String get phoneContinue => 'Настави';

  @override
  String get verifyYourNumber => 'Потврди свој број';

  @override
  String get answerTheCallFrom => 'Одговори на позив од';

  @override
  String get onTheCallEnterThisCode => 'У позиву, унеси овај код';

  @override
  String get followTheVoiceInstructions => 'Следи гласовне инструкције';

  @override
  String get statusCalling => 'Позивање...';

  @override
  String get statusCallInProgress => 'Позив је у току';

  @override
  String get statusVerifiedLabel => 'Потврђено';

  @override
  String get statusCallMissed => 'Позив пропуштен';

  @override
  String get statusTimedOut => 'Време истекло';

  @override
  String get phoneTryAgain => 'Покушај поново';

  @override
  String get phonePageTitle => 'Телефон';

  @override
  String get phoneContactsTab => 'Контакти';

  @override
  String get phoneKeypadTab => 'Тастатура';

  @override
  String get grantContactsAccess => 'Дозволи приступ твојим контактима';

  @override
  String get phoneAllow => 'Дозволи';

  @override
  String get phoneSearchHint => 'Претрага';

  @override
  String get phoneNoContactsFound => 'Нема пронађених контаката';

  @override
  String get phoneEnterNumber => 'Унеси број';

  @override
  String get failedToStartCall => 'Неуспело покретање позива';

  @override
  String get callStateConnecting => 'Повезивање...';

  @override
  String get callStateRinging => 'Звони...';

  @override
  String get callStateEnded => 'Позив завршен';

  @override
  String get callStateFailed => 'Позив неуспешан';

  @override
  String get transcriptPlaceholder => 'Трансцирпција ће се појавити овде...';

  @override
  String get phoneUnmute => 'Укључи звук';

  @override
  String get phoneMute => 'Искључи звук';

  @override
  String get phoneSpeaker => 'Звучник';

  @override
  String get phoneEndCall => 'Заврши';

  @override
  String get phoneCallSettingsTitle => 'Подешавања телефонског позива';

  @override
  String get showPhoneCallButtonTitle => 'Прикажи дугме за позив';

  @override
  String get showPhoneCallButtonDesc => 'Прикажи дугме за телефонски позив на почетном екрану';

  @override
  String get yourVerifiedNumbers => 'Твоји потврђени бројеви';

  @override
  String get verifiedNumbersDescription => 'Када позиваш неког, видећу овај број на телефону';

  @override
  String get noVerifiedNumbers => 'Нема потврђених бројева';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Избриши $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Мораћеш поново да потвردиш да направиш позиве';

  @override
  String get phoneDeleteButton => 'Избриши';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Потврђено пре $minutesм';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Потврђено пре $hoursч';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Потврђено пре $daysд';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Потврђено $date';
  }

  @override
  String get verifiedFallback => 'Потврђено';

  @override
  String get callAlreadyInProgress => 'Позив је већ у току';

  @override
  String get failedToGetCallToken => 'Неуспело добијање позив токена. Прво потврди твој телефонски број.';

  @override
  String get failedToInitializeCallService => 'Неуспело иницијализовање услуге позива';

  @override
  String get speakerLabelYou => 'Ти';

  @override
  String get speakerLabelUnknown => 'Непозната';

  @override
  String get showDailyScoreOnHomepage => 'Прикажи дневну оцену на почетној страни';

  @override
  String get showTasksOnHomepage => 'Прикажи задатке на почетној страни';

  @override
  String get phoneCallsUnlimitedOnly => 'Телефонски позиви преко Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Направи позиве преко Omi и добиј трансцирпцију у реално време, аутоматске резиме и више. Доступно искључиво за Unlimited план кориснике.';

  @override
  String get phoneCallsUpsellFeature1 => 'Трансцирпција у реално време за сваки позив';

  @override
  String get phoneCallsUpsellFeature2 => 'Аутоматске резиме позива и активности';

  @override
  String get phoneCallsUpsellFeature3 => 'Примаоци виде твој прави број, а не насумичан';

  @override
  String get phoneCallsUpsellFeature4 => 'Твоји позиви су приватни и безбедни';

  @override
  String get phoneCallsUpgradeButton => 'Надогради на Unlimited';

  @override
  String get phoneCallsMaybeLater => 'Можда касније';

  @override
  String get deleteSynced => 'Избриши синхронизовано';

  @override
  String get deleteSyncedFiles => 'Избриши синхронизоване снимке';

  @override
  String get deleteSyncedFilesMessage =>
      'Ови снимци су већ синхронизовани са твојим телефоном. Ово се не може отпозвати.';

  @override
  String get syncedFilesDeleted => 'Синхронизовани снимци избрисани';

  @override
  String get deletePending => 'Избриши на чекању';

  @override
  String get deletePendingFiles => 'Избриши снимке на чекању';

  @override
  String get deletePendingFilesWarning =>
      'Ови снимци НИСУ синхронизовани са твојим телефоном и биће трајно избрисани. Ово се не може отпозвати.';

  @override
  String get pendingFilesDeleted => 'Снимци на чекању избрисани';

  @override
  String get deleteAllFiles => 'Избриши све снимке';

  @override
  String get deleteAll => 'Избриши све';

  @override
  String get deleteAllFilesWarning =>
      'Ово ће избрисати синхронизоване и снимке на чекању. Снимци на чекању НИСУ синхронизовани и биће трајно избрисани. Ово се не може отпозвати.';

  @override
  String get allFilesDeleted => 'Сви снимци избрисани';

  @override
  String nFiles(int count) {
    return '$count снимка';
  }

  @override
  String get manageStorage => 'Управљај складиштем';

  @override
  String get safelyBackedUp => 'Безбедно сачувано на твој телефон';

  @override
  String get notYetSynced => 'Још није синхронизовано са твојим телефоном';

  @override
  String get clearAll => 'Очисти све';

  @override
  String get phoneKeypad => 'Тастатура';

  @override
  String get phoneHideKeypad => 'Скриј тастатуру';

  @override
  String get fairUsePolicy => 'Честита употреба';

  @override
  String get fairUseLoadError => 'Не могу учитати статус честите употребе. Молимо покушај поново.';

  @override
  String get fairUseStatusNormal => 'Твоја употреба је у нормалним границама.';

  @override
  String get fairUseStageNormal => 'Нормално';

  @override
  String get fairUseStageWarning => 'Упозорење';

  @override
  String get fairUseStageThrottle => 'Ограничена';

  @override
  String get fairUseStageRestrict => 'Ограничена јако';

  @override
  String get fairUseSpeechUsage => 'Употреба говора';

  @override
  String get fairUseToday => 'Данас';

  @override
  String get fairUse3Day => '3-дневно кољење';

  @override
  String get fairUseWeekly => 'Недељно кољење';

  @override
  String get fairUseAboutTitle => 'О честитој употреби';

  @override
  String get fairUseAboutBody =>
      'Omi је направљен за личне разговоре, састанке и живе интеракције. Употреба се мери реалним временом говора, не временом повезивања. Ако употреба значајно превише превише превиши обрасцима за личну употребу, могу се применити прилагођавања.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef копиран';
  }

  @override
  String get fairUseDailyTranscription => 'Дневна трансцирпција';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '$usedм / $limitм';
  }

  @override
  String get fairUseBudgetExhausted => 'Дневна граница трансцирпције достигнута';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Ресетује се $time';
  }

  @override
  String get transcriptionPaused => 'Снимање, поновно повезивање';

  @override
  String get transcriptionPausedReconnecting => 'Још увек се снима — поновно повезивање на трансцирпцију...';

  @override
  String fairUseBannerStatus(String status) {
    return 'Честита употреба: $status';
  }

  @override
  String get improveConnectionTitle => 'Побољшај повезивање';

  @override
  String get improveConnectionContent =>
      'Побољшали смо како Omi остаје повезан са твојим уређајем. Да би активирао ово, молимо отиди на страницу Информације о уређају, притисни \"Одвежи уређај\" и затим поново упари твој уређај.';

  @override
  String get improveConnectionAction => 'Разумем';

  @override
  String clockSkewWarning(int minutes) {
    return 'Сат твог уређаја је разликован за ~$minutes мин. Провери подешавања датума и времена.';
  }

  @override
  String get omisStorage => 'Omi складиште';

  @override
  String get phoneStorage => 'Складиште телефона';

  @override
  String get cloudStorage => 'Облачно складиште';

  @override
  String get howSyncingWorks => 'Како функционише синхронизовање';

  @override
  String get noSyncedRecordings => 'Нема синхронизованих снимака';

  @override
  String get recordingsSyncAutomatically => 'Снимци се синхронизују аутоматски — није потребно ничего.';

  @override
  String get filesDownloadedUploadedNextTime => 'Датотеке које су већ преузете биће послане следећи пут.';

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
  String get tapToView => 'Притисни да видиш';

  @override
  String get syncFailed => 'Синхронизовање неуспешно';

  @override
  String get keepSyncing => 'Настави синхронизовање';

  @override
  String get cancelSyncQuestion => 'Отказати синхронизовање?';

  @override
  String get omisStorageDesc =>
      'Када твој Omi није повезан са твојим телефоном, снимци аудио се чувају локално на уграђеној меморији. Никада не губиш снимак.';

  @override
  String get phoneStorageDesc =>
      'Када се Omi поново повезује, снимци се аутоматски преносе на твој телефон као привремена складишна подручја пре слања.';

  @override
  String get cloudStorageDesc =>
      'Када буде послано, твоји снимци се обрађују и трансцирају. Разговори ће бити доступни за минут.';

  @override
  String get tipKeepPhoneNearby => 'Держи свој телефон близу за брже синхронизовање';

  @override
  String get tipStableInternet => 'Стабилна интернет брзина убрзава облачна слања';

  @override
  String get tipAutoSync => 'Снимци се синхронизују аутоматски';

  @override
  String get storageSection => 'СКЛАДИШТЕ';

  @override
  String get permissions => 'Дозволе';

  @override
  String get permissionEnabled => 'Омогућена';

  @override
  String get permissionEnable => 'Омогући';

  @override
  String get permissionsPageDescription =>
      'Ове дозволе су суштине за то како Omi функционише. Омогућавају главне функције као обавештење, локацијске искуства и аудио прихватање.';

  @override
  String get permissionsRequiredDescription =>
      'Omi затреба неколико дозвола да функционише правилно. Молимо их допусти да наставиш.';

  @override
  String get permissionsSetupTitle => 'Добиј најбоље искуство';

  @override
  String get permissionsSetupDescription => 'Омогући неколико дозвола да Omi может радити своју магију.';

  @override
  String get permissionsChangeAnytime => 'Можеш променити ове дозволе било када у Подешаваља > Дозволе';

  @override
  String get location => 'Локација';

  @override
  String get microphone => 'Микрофон';

  @override
  String get whyAreYouCanceling => 'Зашто отказујеш?';

  @override
  String get cancelReasonSubtitle => 'Можеш ли нам рећи зашто одлазиш?';

  @override
  String get cancelReasonTooExpensive => 'Превише скупо';

  @override
  String get cancelReasonNotUsing => 'Недовољно користим';

  @override
  String get cancelReasonMissingFeatures => 'Недостају функције';

  @override
  String get cancelReasonAudioQuality => 'Аудио/трансцирпција квалитета';

  @override
  String get cancelReasonBatteryDrain => 'Забринутост због пражњења батерије';

  @override
  String get cancelReasonFoundAlternative => 'Нашао/ла алтернативу';

  @override
  String get cancelReasonOther => 'Друго';

  @override
  String get tellUsMore => 'Речи нам више (опционално)';

  @override
  String get cancelReasonDetailHint => 'Ценимо сваку повратну информацију...';

  @override
  String get justAMoment => 'Чекај мало';

  @override
  String get cancelConsequencesSubtitle => 'Високо препоручујемо да истражиш друге опције уместо отказивања.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Твој план ће остати активан до $date. Након тога, бићеш премештен на бесплатну верзију са ограниченим функцијама.';
  }

  @override
  String get ifYouCancel => 'Ако отажиш:';

  @override
  String get cancelConsequenceNoAccess => 'Нећеш више имати неограничен приступ на крају твог периода наплате.';

  @override
  String get cancelConsequenceBattery => '7х више трошења батерије (обработка на уређају)';

  @override
  String get cancelConsequenceQuality => '30% нижи квалитет трансцирпције (модели на уређају)';

  @override
  String get cancelConsequenceDelay => '5-7 секундна кашњења у обработци (модели на уређају)';

  @override
  String get cancelConsequenceSpeakers => 'Не могу препознати говорнике.';

  @override
  String get confirmAndCancel => 'Потврди и откази';

  @override
  String get cancelConsequencePhoneCalls => 'Нема трансцирпције телефонског позива у реално време';

  @override
  String get feedbackTitleTooExpensive => 'Која цена би функционисала за тебе?';

  @override
  String get feedbackTitleMissingFeatures => 'Које функције недостају?';

  @override
  String get feedbackTitleAudioQuality => 'Какве проблеме си доживео/ла?';

  @override
  String get feedbackTitleBatteryDrain => 'Речи нам о проблемима са батеријом';

  @override
  String get feedbackTitleFoundAlternative => 'На шта прелазиш?';

  @override
  String get feedbackTitleNotUsing => 'Шта би те учинило да више користиш Omi?';

  @override
  String get feedbackSubtitleTooExpensive => 'Твоја повратна информација нам помаже да наћемо право равнотежу.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Стално градимо — ово нам помаже да одредимо приоритете.';

  @override
  String get feedbackSubtitleAudioQuality => 'Веома желимо да разумемо шта је пошло наопако.';

  @override
  String get feedbackSubtitleBatteryDrain => 'Ово помаже нашем hardware тиму да се побољша.';

  @override
  String get feedbackSubtitleFoundAlternative => 'Веома желимо да научимо шта је привукло твоју пажњу.';

  @override
  String get feedbackSubtitleNotUsing => 'Желимо да направимо Omi кориснијим за тебе.';

  @override
  String get deviceDiagnostics => 'Дијагностика уређаја';

  @override
  String get signalStrength => 'Јачина сигнала';

  @override
  String get connectionUptime => 'Време док је повезано';

  @override
  String get reconnections => 'Поновна повезивања';

  @override
  String get disconnectHistory => 'Историја прекида';

  @override
  String get noDisconnectsRecorded => 'Нема снимљених прекида';

  @override
  String get diagnostics => 'Дијагностика';

  @override
  String get waitingForData => 'Чекам податке...';

  @override
  String get liveRssiOverTime => 'Живи RSSI током времена';

  @override
  String get noRssiDataYet => 'Нема RSSI podataka';

  @override
  String get collectingData => 'Прикупљање podataka...';

  @override
  String get cleanDisconnect => 'Чист прекид';

  @override
  String get connectionTimeout => 'Време за повезивање истекло';

  @override
  String get remoteDeviceTerminated => 'Удаљени уређај прекинут';

  @override
  String get pairedToAnotherPhone => 'Упарено са другим телефоном';

  @override
  String get linkKeyMismatch => 'Неподударање кључа линка';

  @override
  String get connectionFailed => 'Повезивање неуспешно';

  @override
  String get appClosed => 'Апликација затворена';

  @override
  String get manualDisconnect => 'Ручан прекид';

  @override
  String lastNEvents(int count) {
    return 'Последњих $count догађаја';
  }

  @override
  String get signal => 'Сигнал';

  @override
  String get battery => 'Батерија';

  @override
  String get excellent => 'Одличан';

  @override
  String get good => 'Добар';

  @override
  String get fair => 'Задовољавајућ';

  @override
  String get weak => 'Слаб';

  @override
  String gattError(String code) {
    return 'GATT грешка ($code)';
  }

  @override
  String get batteryHistory => 'Батерија';

  @override
  String get noBatteryDataYet => 'Још нема података о батерији';

  @override
  String get day => 'Дан';

  @override
  String get week => 'Недеља';

  @override
  String get rollbackToStableFirmware => 'Врати се на стабилан firmware';

  @override
  String get rollbackConfirmTitle => 'Врати се на firmware?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Ово ће заменити твој тренутни firmware са најновијом стабилном верзијом ($version). Твој уређај ће се рестартовати после ажурирања.';
  }

  @override
  String get stableFirmware => 'Стабилан firmware';

  @override
  String get fetchingStableFirmware => 'Преузимање најновијег стабилног firmware-а...';

  @override
  String get noStableFirmwareFound => 'Не могу пронаћи стабилну firmware верзију за твој уређај.';

  @override
  String get installStableFirmware => 'Инсталирај стабилан firmware';

  @override
  String get alreadyOnStableFirmware => 'Већ си на најновијој стабилној верзији.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration аудио сачувано локално';
  }

  @override
  String get willSyncAutomatically => 'ће се синхронизовати аутоматски';

  @override
  String get enableLocationTitle => 'Омогући локацију';

  @override
  String get enableLocationDescription => 'Дозвола за локацију је потребна да пронађеш близу Bluetooth уређаје.';

  @override
  String get voiceRecordingFound => 'Снимак пронађен';

  @override
  String get transcriptionConnecting => 'Повезивање трансцирпције...';

  @override
  String get transcriptionReconnecting => 'Поновно повезивање трансцирпције...';

  @override
  String get transcriptionUnavailable => 'Трансцирпција недоступна';

  @override
  String get audioOutput => 'Аудио излаз';

  @override
  String get firmwareWarningTitle => 'Важно: Прочитајте пре ажурирања';

  @override
  String get firmwareFormatWarning =>
      'Овај фирмвер ће форматирати SD картицу. Молимо вас да се уверите да су сви офлајн подаци синхронизовани пре надоградње.\n\nАко видите треперeће црвено светло након инсталирања ове верзије, не брините. Једноставно повежите уређај са апликацијом и требало би да постане плаво. Црвено светло значи да сат уређаја још увек није синхронизован.';

  @override
  String get continueAnyway => 'Настави';

  @override
  String get tasksClearCompleted => 'Обриши завршене';

  @override
  String get tasksSelectAll => 'Изабери све';

  @override
  String tasksDeleteSelected(int count) {
    return 'Обриши $count задатак(е)';
  }

  @override
  String get tasksMarkComplete => 'Означено као завршено';

  @override
  String get appleHealthManageNote =>
      'Omi приступа Apple Health-у преко Apple-овог HealthKit оквира. Приступ можете опозвати у било ком тренутку у подешавањима iOS-а.';

  @override
  String get appleHealthConnectCta => 'Повежи са Apple Health';

  @override
  String get appleHealthDisconnectCta => 'Прекини везу са Apple Health';

  @override
  String get appleHealthConnectedBadge => 'Повезано';

  @override
  String get appleHealthFeatureChatTitle => 'Разговарајте о свом здрављу';

  @override
  String get appleHealthFeatureChatDesc => 'Питајте Omi о корацима, сну, откуцајима срца и тренинзима.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Приступ само за читање';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi никада не уписује у Apple Health и не мења ваше податке.';

  @override
  String get appleHealthFeatureSecureTitle => 'Безбедна синхронизација';

  @override
  String get appleHealthFeatureSecureDesc => 'Ваши Apple Health подаци се приватно синхронизују са Omi налогом.';

  @override
  String get appleHealthDeniedTitle => 'Приступ Apple Health-у одбијен';

  @override
  String get appleHealthDeniedBody =>
      'Omi нема дозволу да чита ваше Apple Health податке. Омогућите га у iOS Подешавања → Приватност и безбедност → Health → Omi.';

  @override
  String get deleteFlowReasonTitle => 'Зашто одлазите?';

  @override
  String get deleteFlowReasonSubtitle => 'Ваше повратне информације помажу нам да побољшамо Omi за све.';

  @override
  String get deleteReasonPrivacy => 'Бриге о приватности';

  @override
  String get deleteReasonNotUsing => 'Не користим довољно често';

  @override
  String get deleteReasonMissingFeatures => 'Недостају функције које су ми потребне';

  @override
  String get deleteReasonTechnicalIssues => 'Превише техничких проблема';

  @override
  String get deleteReasonFoundAlternative => 'Користим нешто друго';

  @override
  String get deleteReasonTakingBreak => 'Само правим паузу';

  @override
  String get deleteReasonOther => 'Остало';

  @override
  String get deleteFlowFeedbackTitle => 'Реците нам више';

  @override
  String get deleteFlowFeedbackSubtitle => 'Шта би учинило да Omi ради за вас?';

  @override
  String get deleteFlowFeedbackHint => 'Опционо — ваше мисли нам помажу да направимо бољи производ.';

  @override
  String get deleteFlowConfirmTitle => 'Ово је трајно';

  @override
  String get deleteFlowConfirmSubtitle => 'Након брисања налога, његово враћање није могуће.';

  @override
  String get deleteConsequenceSubscription => 'Свака активна претплата биће отказана.';

  @override
  String get deleteConsequenceNoRecovery => 'Ваш налог се не може вратити — чак ни путем подршке.';

  @override
  String get deleteTypeToConfirm => 'Унесите DELETE за потврду';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'Трајно избриши налог';

  @override
  String get keepMyAccount => 'Задржи мој налог';

  @override
  String get deleteAccountFailed => 'Брисање вашег налога није успело. Покушајте поново.';

  @override
  String get planUpdate => 'Ажурирање плана';

  @override
  String get planDeprecationMessage =>
      'Ваш Unlimited план се укида. Пређите на Operator план — исте одличне функције за \$49/мес. Ваш тренутни план ће наставити да ради у међувремену.';

  @override
  String get upgradeYourPlan => 'Надоградите свој план';

  @override
  String get youAreOnAPaidPlan => 'На плаћеном сте плану.';

  @override
  String get chatTitle => 'Ћаскање';

  @override
  String get chatMessages => 'порука';

  @override
  String get unlimitedChatThisMonth => 'Неограничене поруке овог месеца';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used од $limit буџета за рачунање искоришћено';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used од $limit порука искоришћено овог месеца';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit искоришћено';
  }

  @override
  String get chatLimitReachedUpgrade => 'Лимит ћаскања достигнут. Надоградите за више порука.';

  @override
  String get chatLimitReachedTitle => 'Лимит ћаскања достигнут';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Искористили сте $used од $limitDisplay на плану $plan.';
  }

  @override
  String resetsInDays(int count) {
    return 'Ресетује се за $count дана';
  }

  @override
  String resetsInHours(int count) {
    return 'Ресетује се за $count сати';
  }

  @override
  String get resetsSoon => 'Ускоро се ресетује';

  @override
  String get upgradePlan => 'Надогради план';

  @override
  String get billingMonthly => 'Месечно';

  @override
  String get billingYearly => 'Годишње';

  @override
  String get savePercent => 'Уштедите ~17%';

  @override
  String get popular => 'Популарно';

  @override
  String get currentPlan => 'Тренутни';

  @override
  String neoSubtitle(int count) {
    return '$count питања месечно';
  }

  @override
  String operatorSubtitle(int count) {
    return '$count питања месечно';
  }

  @override
  String get architectSubtitle => 'Напредни AI — хиљаде разговора + агентна аутоматизација';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Ћаскање: \$$used / \$$limit искоришћено овог месеца';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Ћаскање: \$$used искоришћено овог месеца';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Ћаскање: $used / $limit порука овог месеца';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Ћаскање: $used порука овог месеца';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'Достигли сте свој месечни лимит. Надоградите да наставите да разговарате са Omi без ограничења.';

  @override
  String get voiceResponseAudio => 'Прочитај Omi одговор наглас';

  @override
  String get voiceResponseMode => 'Гласовни одговор';

  @override
  String get voiceResponseModeTitle => 'Када изговарати одговоре';

  @override
  String get voiceResponseOff => 'Искључено';

  @override
  String get voiceResponseHeadphonesOnly => 'Само слушалице';

  @override
  String get voiceResponseAlways => 'Увек';

  @override
  String get agreeAndContinue => 'Slažem se i nastavi';

  @override
  String get startVoiceRecording => 'Покрени гласовно снимање';

  @override
  String get startCallRecording => 'Покрени снимање позива';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'Гласовни режим';

  @override
  String get quickActionAskOmi => 'Питајте Omi bilo što';

  @override
  String get record => 'Сними';

  @override
  String get stop => 'Заустави';

  @override
  String get recordWithPhoneMic => 'Снимај микрофоном телефона';

  @override
  String get recordWithPhoneMicSubtitle => 'Снимите звук око вас';

  @override
  String get phoneCall => 'Телефонски позив';

  @override
  String get phoneCallSubtitle => 'Снимајте позив са транскрипцијом уживо';

  @override
  String get searchActionItems => 'Претражи акционе ставке';

  @override
  String get selectActionItems => 'Изабери више';

  @override
  String chooseExportDestination(int count) {
    return 'Извези $count ставку/и у…';
  }

  @override
  String get bulkExportInProgress => 'Извоз…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Извезено $count у $platform';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Извезено $success од $total у $platform';
  }

  @override
  String get showCompletedTasks => 'Прикажи завршене';

  @override
  String get hideCompletedTasks => 'Сакриј завршене';

  @override
  String get selectAllTasksMenu => 'Изабери све';

  @override
  String get connectTaskAppToExport => 'Повежите апликацију за задатке у Подешавањима за извоз';

  @override
  String get connectAction => 'Повежи';

  @override
  String get deselectAllTasksMenu => 'Поништи избор свих';
}
