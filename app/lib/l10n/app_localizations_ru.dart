// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Russian (`ru`).
class AppLocalizationsRu extends AppLocalizations {
  AppLocalizationsRu([String locale = 'ru']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Разговор';

  @override
  String get transcriptTab => 'Расшифровка';

  @override
  String get actionItemsTab => 'Задачи';

  @override
  String get deleteConversationTitle => 'Удалить разговор?';

  @override
  String get deleteConversationMessage =>
      'Вы уверены, что хотите удалить этот разговор? Это действие нельзя будет отменить.';

  @override
  String get confirm => 'Подтвердить';

  @override
  String get cancel => 'Отмена';

  @override
  String get ok => 'Ок';

  @override
  String get delete => 'Удалить';

  @override
  String get add => 'Добавить';

  @override
  String get update => 'Обновить';

  @override
  String get save => 'Сохранить';

  @override
  String get edit => 'Редактировать';

  @override
  String get close => 'Закрыть';

  @override
  String get clear => 'Очистить';

  @override
  String get copyTranscript => 'Копировать транскрипт';

  @override
  String get copySummary => 'Копировать сводку';

  @override
  String get testPrompt => 'Тестовый запрос';

  @override
  String get reprocessConversation => 'Переобработать разговор';

  @override
  String get deleteConversation => 'Удалить разговор';

  @override
  String get contentCopied => 'Содержимое скопировано в буфер обмена';

  @override
  String get failedToUpdateStarred => 'Не удалось обновить статус избранного.';

  @override
  String get conversationUrlNotShared => 'Не удалось поделиться ссылкой на разговор.';

  @override
  String get errorProcessingConversation => 'Ошибка при обработке разговора. Пожалуйста, попробуйте позже.';

  @override
  String get noInternetConnection => 'Нет подключения к Интернету';

  @override
  String get unableToDeleteConversation => 'Не удалось удалить разговор';

  @override
  String get somethingWentWrong => 'Что-то пошло не так! Пожалуйста, попробуйте позже.';

  @override
  String get copyErrorMessage => 'Копировать сообщение об ошибке';

  @override
  String get errorCopied => 'Сообщение об ошибке скопировано в буфер обмена';

  @override
  String get remaining => 'Осталось';

  @override
  String get loading => 'Загрузка...';

  @override
  String get loadingDuration => 'Загрузка длительности...';

  @override
  String secondsCount(int count) {
    return '$count секунд';
  }

  @override
  String get people => 'Люди';

  @override
  String get addNewPerson => 'Добавить нового человека';

  @override
  String get editPerson => 'Редактировать человека';

  @override
  String get createPersonHint => 'Создайте нового человека и обучите Omi распознавать его голос тоже!';

  @override
  String get speechProfile => 'Речевой Профиль';

  @override
  String sampleNumber(int number) {
    return 'Образец $number';
  }

  @override
  String get settings => 'Настройки';

  @override
  String get language => 'Язык';

  @override
  String get selectLanguage => 'Выберите язык';

  @override
  String get deleting => 'Удаление...';

  @override
  String get pleaseCompleteAuthentication =>
      'Пожалуйста, завершите аутентификацию в браузере. После этого вернитесь в приложение.';

  @override
  String get failedToStartAuthentication => 'Не удалось начать аутентификацию';

  @override
  String get importStarted => 'Импорт начат! Вы получите уведомление, когда он завершится.';

  @override
  String get failedToStartImport => 'Не удалось начать импорт. Пожалуйста, попробуйте снова.';

  @override
  String get couldNotAccessFile => 'Не удалось получить доступ к выбранному файлу';

  @override
  String get askOmi => 'Спросить Omi';

  @override
  String get done => 'Готово';

  @override
  String get disconnected => 'Отключено';

  @override
  String get searching => 'Поиск...';

  @override
  String get connectDevice => 'Подключить устройство';

  @override
  String get monthlyLimitReached => 'Вы достигли месячного лимита.';

  @override
  String get checkUsage => 'Проверить использование';

  @override
  String get syncingRecordings => 'Синхронизация записей';

  @override
  String get recordingsToSync => 'Записи для синхронизации';

  @override
  String get allCaughtUp => 'Всё синхронизировано';

  @override
  String get sync => 'Синхронизация';

  @override
  String get pendantUpToDate => 'Кулон обновлён';

  @override
  String get allRecordingsSynced => 'Все записи синхронизированы';

  @override
  String get syncingInProgress => 'Идёт синхронизация';

  @override
  String get readyToSync => 'Готово к синхронизации';

  @override
  String get tapSyncToStart => 'Нажмите Синхронизация для начала';

  @override
  String get pendantNotConnected => 'Кулон не подключён. Подключите для синхронизации.';

  @override
  String get everythingSynced => 'Всё уже синхронизировано.';

  @override
  String get recordingsNotSynced => 'У вас есть записи, которые ещё не синхронизированы.';

  @override
  String get syncingBackground => 'Мы продолжим синхронизировать ваши записи в фоновом режиме.';

  @override
  String get noConversationsYet => 'Пока нет разговоров';

  @override
  String get noStarredConversations => 'Нет избранных бесед';

  @override
  String get starConversationHint =>
      'Чтобы добавить разговор в избранное, откройте его и нажмите на значок звезды в заголовке.';

  @override
  String get searchConversations => 'Поиск разговоров...';

  @override
  String selectedCount(int count, Object s) {
    return 'Выбрано $count';
  }

  @override
  String get merge => 'Объединить';

  @override
  String get mergeConversations => 'Объединить разговоры';

  @override
  String mergeConversationsMessage(int count) {
    return 'Это объединит $count разговоров в один. Всё содержимое будет объединено и перегенерировано.';
  }

  @override
  String get mergingInBackground => 'Объединение в фоновом режиме. Это может занять некоторое время.';

  @override
  String get failedToStartMerge => 'Не удалось начать объединение';

  @override
  String get askAnything => 'Спросите что угодно';

  @override
  String get noMessagesYet => 'Сообщений пока нет!\nПочему бы не начать разговор?';

  @override
  String get deletingMessages => 'Удаление ваших сообщений из памяти Omi...';

  @override
  String get messageCopied => '✨ Сообщение скопировано в буфер обмена';

  @override
  String get cannotReportOwnMessage => 'Вы не можете пожаловаться на свои собственные сообщения.';

  @override
  String get reportMessage => 'Сообщить о сообщении';

  @override
  String get reportMessageConfirm => 'Вы уверены, что хотите пожаловаться на это сообщение?';

  @override
  String get messageReported => 'Жалоба на сообщение успешно отправлена.';

  @override
  String get thankYouFeedback => 'Спасибо за ваш отзыв!';

  @override
  String get clearChat => 'Очистить чат';

  @override
  String get clearChatConfirm => 'Вы уверены, что хотите очистить чат? Это действие нельзя будет отменить.';

  @override
  String get maxFilesLimit => 'Вы можете загрузить только 4 файла одновременно';

  @override
  String get chatWithOmi => 'Чат с Omi';

  @override
  String get apps => 'Приложения';

  @override
  String get noAppsFound => 'Приложения не найдены';

  @override
  String get tryAdjustingSearch => 'Попробуйте изменить параметры поиска или фильтры';

  @override
  String get createYourOwnApp => 'Создайте своё приложение';

  @override
  String get buildAndShareApp => 'Создавайте и делитесь своим пользовательским приложением';

  @override
  String get searchApps => 'Поиск приложений...';

  @override
  String get myApps => 'Мои приложения';

  @override
  String get installedApps => 'Установленные приложения';

  @override
  String get unableToFetchApps =>
      'Не удалось загрузить приложения :(\n\nПожалуйста, проверьте подключение к интернету и попробуйте снова.';

  @override
  String get aboutOmi => 'О Omi';

  @override
  String get privacyPolicy => 'Политикой конфиденциальности';

  @override
  String get visitWebsite => 'Посетить сайт';

  @override
  String get helpOrInquiries => 'Помощь или вопросы?';

  @override
  String get joinCommunity => 'Присоединяйтесь к сообществу!';

  @override
  String get membersAndCounting => '8000+ участников и их число растет.';

  @override
  String get deleteAccountTitle => 'Удалить аккаунт';

  @override
  String get deleteAccountConfirm => 'Вы уверены, что хотите удалить свой аккаунт?';

  @override
  String get cannotBeUndone => 'Это действие нельзя отменить.';

  @override
  String get allDataErased => 'Все ваши воспоминания и разговоры будут безвозвратно удалены.';

  @override
  String get appsDisconnected => 'Ваши приложения и интеграции будут немедленно отключены.';

  @override
  String get exportBeforeDelete =>
      'Вы можете экспортировать свои данные перед удалением аккаунта, но после удаления восстановить их будет невозможно.';

  @override
  String get deleteAccountCheckbox =>
      'Я понимаю, что удаление аккаунта необратимо, и все данные, включая воспоминания и разговоры, будут потеряны без возможности восстановления.';

  @override
  String get areYouSure => 'Вы уверены?';

  @override
  String get deleteAccountFinal =>
      'Это действие необратимо и навсегда удалит ваш аккаунт и все связанные с ним данные. Вы уверены, что хотите продолжить?';

  @override
  String get deleteNow => 'Удалить сейчас';

  @override
  String get goBack => 'Вернуться назад';

  @override
  String get checkBoxToConfirm =>
      'Поставьте галочку, чтобы подтвердить, что вы понимаете: удаление аккаунта необратимо.';

  @override
  String get profile => 'Профиль';

  @override
  String get name => 'Имя';

  @override
  String get email => 'Эл. почта';

  @override
  String get customVocabulary => 'Пользовательский Словарь';

  @override
  String get identifyingOthers => 'Идентификация Других';

  @override
  String get paymentMethods => 'Способы Оплаты';

  @override
  String get conversationDisplay => 'Отображение Разговоров';

  @override
  String get dataPrivacy => 'Конфиденциальность Данных';

  @override
  String get userId => 'ID Пользователя';

  @override
  String get notSet => 'Не задано';

  @override
  String get userIdCopied => 'ID пользователя скопирован в буфер обмена';

  @override
  String get systemDefault => 'По умолчанию системы';

  @override
  String get planAndUsage => 'Тариф и использование';

  @override
  String get offlineSync => 'Офлайн синхронизация';

  @override
  String get deviceSettings => 'Настройки устройства';

  @override
  String get integrations => 'Интеграции';

  @override
  String get feedbackBug => 'Отзыв / Ошибка';

  @override
  String get helpCenter => 'Центр помощи';

  @override
  String get developerSettings => 'Настройки разработчика';

  @override
  String get getOmiForMac => 'Получить Omi для Mac';

  @override
  String get referralProgram => 'Реферальная программа';

  @override
  String get signOut => 'Выйти';

  @override
  String get appAndDeviceCopied => 'Информация о приложении и устройстве скопирована';

  @override
  String get wrapped2025 => 'Итоги 2025';

  @override
  String get yourPrivacyYourControl => 'Ваша конфиденциальность, ваш контроль';

  @override
  String get privacyIntro =>
      'В Omi мы стремимся защитить вашу конфиденциальность. Эта страница позволяет вам контролировать, как хранятся и используются ваши данные.';

  @override
  String get learnMore => 'Узнать больше...';

  @override
  String get dataProtectionLevel => 'Уровень защиты данных';

  @override
  String get dataProtectionDesc =>
      'Ваши данные по умолчанию защищены надёжным шифрованием. Просмотрите ваши настройки и будущие опции конфиденциальности ниже.';

  @override
  String get appAccess => 'Доступ приложений';

  @override
  String get appAccessDesc =>
      'Следующие приложения могут получить доступ к вашим данным. Нажмите на приложение, чтобы управлять его разрешениями.';

  @override
  String get noAppsExternalAccess => 'Ни одно установленное приложение не имеет внешнего доступа к вашим данным.';

  @override
  String get deviceName => 'Название устройства';

  @override
  String get deviceId => 'ID устройства';

  @override
  String get firmware => 'Прошивка';

  @override
  String get sdCardSync => 'Синхронизация SD-карты';

  @override
  String get hardwareRevision => 'Ревизия оборудования';

  @override
  String get modelNumber => 'Номер модели';

  @override
  String get manufacturer => 'Производитель';

  @override
  String get doubleTap => 'Двойное нажатие';

  @override
  String get ledBrightness => 'Яркость LED';

  @override
  String get micGain => 'Усиление микрофона';

  @override
  String get disconnect => 'Отключить';

  @override
  String get forgetDevice => 'Забыть устройство';

  @override
  String get chargingIssues => 'Проблемы с зарядкой';

  @override
  String get disconnectDevice => 'Отключить устройство';

  @override
  String get unpairDevice => 'Отменить сопряжение устройства';

  @override
  String get unpairAndForget => 'Разорвать пару и забыть устройство';

  @override
  String get deviceDisconnectedMessage => 'Ваш Omi был отключён 😔';

  @override
  String get deviceUnpairedMessage =>
      'Сопряжение устройства отменено. Перейдите в Настройки > Bluetooth и забудьте устройство, чтобы завершить отмену сопряжения.';

  @override
  String get unpairDialogTitle => 'Разорвать пару с устройством';

  @override
  String get unpairDialogMessage =>
      'Это разорвёт пару с устройством, чтобы оно могло быть подключено к другому телефону. Вам нужно будет перейти в Настройки > Bluetooth и забыть устройство для завершения процесса.';

  @override
  String get deviceNotConnected => 'Устройство не подключено';

  @override
  String get connectDeviceMessage => 'Подключите устройство Omi для доступа\nк настройкам устройства и настройке';

  @override
  String get deviceInfoSection => 'Информация об устройстве';

  @override
  String get customizationSection => 'Настройка';

  @override
  String get hardwareSection => 'Оборудование';

  @override
  String get v2Undetected => 'V2 не обнаружено';

  @override
  String get v2UndetectedMessage =>
      'Мы видим, что у вас либо устройство V1, либо ваше устройство не подключено. Функция SD-карты доступна только для устройств V2.';

  @override
  String get endConversation => 'Завершить разговор';

  @override
  String get pauseResume => 'Пауза/Возобновить';

  @override
  String get starConversation => 'Добавить разговор в избранное';

  @override
  String get doubleTapAction => 'Действие при двойном нажатии';

  @override
  String get endAndProcess => 'Завершить и обработать разговор';

  @override
  String get pauseResumeRecording => 'Пауза/Возобновить запись';

  @override
  String get starOngoing => 'Добавить текущий разговор в избранное';

  @override
  String get off => 'Выкл';

  @override
  String get max => 'Макс';

  @override
  String get mute => 'Без звука';

  @override
  String get quiet => 'Тихий';

  @override
  String get normal => 'Обычный';

  @override
  String get high => 'Высокий';

  @override
  String get micGainDescMuted => 'Микрофон выключен';

  @override
  String get micGainDescLow => 'Очень тихий - для шумной обстановки';

  @override
  String get micGainDescModerate => 'Тихий - для умеренного шума';

  @override
  String get micGainDescNeutral => 'Нейтральный - сбалансированная запись';

  @override
  String get micGainDescSlightlyBoosted => 'Слегка усиленный - обычное использование';

  @override
  String get micGainDescBoosted => 'Усиленный - для тихой обстановки';

  @override
  String get micGainDescHigh => 'Высокий - для отдалённых или тихих голосов';

  @override
  String get micGainDescVeryHigh => 'Очень высокий - для очень тихих источников';

  @override
  String get micGainDescMax => 'Максимальный - используйте с осторожностью';

  @override
  String get developerSettingsTitle => 'Настройки разработчика';

  @override
  String get saving => 'Сохранение...';

  @override
  String get personaConfig => 'Настройте вашу AI-персону';

  @override
  String get beta => 'БЕТА';

  @override
  String get transcription => 'Расшифровка';

  @override
  String get transcriptionConfig => 'Настройте провайдера STT';

  @override
  String get conversationTimeout => 'Тайм-аут разговора';

  @override
  String get conversationTimeoutConfig => 'Установите, когда разговоры автоматически завершаются';

  @override
  String get importData => 'Импорт данных';

  @override
  String get importDataConfig => 'Импортируйте данные из других источников';

  @override
  String get debugDiagnostics => 'Отладка и диагностика';

  @override
  String get endpointUrl => 'URL конечной точки';

  @override
  String get noApiKeys => 'API-ключей пока нет';

  @override
  String get createKeyToStart => 'Создайте ключ для начала';

  @override
  String get createKey => 'Создать Ключ';

  @override
  String get docs => 'Документация';

  @override
  String get yourOmiInsights => 'Ваша статистика Omi';

  @override
  String get today => 'Сегодня';

  @override
  String get thisMonth => 'Этот месяц';

  @override
  String get thisYear => 'Этот год';

  @override
  String get allTime => 'Всё время';

  @override
  String get noActivityYet => 'Активности пока нет';

  @override
  String get startConversationToSeeInsights =>
      'Начните разговор с Omi,\nчтобы увидеть здесь вашу статистику использования.';

  @override
  String get listening => 'Прослушивание';

  @override
  String get listeningSubtitle => 'Общее время активного прослушивания Omi.';

  @override
  String get understanding => 'Понимание';

  @override
  String get understandingSubtitle => 'Слов понято из ваших разговоров.';

  @override
  String get providing => 'Предоставление';

  @override
  String get providingSubtitle => 'Задач и заметок, автоматически зафиксированных.';

  @override
  String get remembering => 'Запоминание';

  @override
  String get rememberingSubtitle => 'Фактов и деталей, запомненных для вас.';

  @override
  String get unlimitedPlan => 'Безлимитный тариф';

  @override
  String get managePlan => 'Управление тарифом';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Ваш тариф будет отменён $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Ваш тариф продлится $date.';
  }

  @override
  String get basicPlan => 'Бесплатный тариф';

  @override
  String usageLimitMessage(String used, int limit) {
    return 'Использовано $used из $limit минут';
  }

  @override
  String get upgrade => 'Повысить тариф';

  @override
  String get upgradeToUnlimited => 'Обновить до безлимитного';

  @override
  String basicPlanDesc(int limit) {
    return 'Ваш тариф включает $limit бесплатных минут в месяц. Перейдите на безлимитный тариф.';
  }

  @override
  String get shareStatsMessage => 'Делюсь статистикой Omi! (omi.me - ваш постоянный AI-помощник)';

  @override
  String get sharePeriodToday => 'Сегодня omi:';

  @override
  String get sharePeriodMonth => 'В этом месяце omi:';

  @override
  String get sharePeriodYear => 'В этом году omi:';

  @override
  String get sharePeriodAllTime => 'За всё время omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Слушал $minutes минут';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Понял $words слов';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Предоставил $count инсайтов';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Запомнил $count воспоминаний';
  }

  @override
  String get debugLogs => 'Журналы отладки';

  @override
  String get debugLogsAutoDelete => 'Автоматически удаляются через 3 дня.';

  @override
  String get debugLogsDesc => 'Помогает диагностировать проблемы';

  @override
  String get noLogFilesFound => 'Файлы журнала не найдены.';

  @override
  String get omiDebugLog => 'Журнал отладки Omi';

  @override
  String get logShared => 'Журнал отправлен';

  @override
  String get selectLogFile => 'Выберите файл журнала';

  @override
  String get shareLogs => 'Поделиться журналами';

  @override
  String get debugLogCleared => 'Журнал отладки очищен';

  @override
  String get exportStarted => 'Экспорт начат. Это может занять несколько секунд...';

  @override
  String get exportAllData => 'Экспортировать все данные';

  @override
  String get exportDataDesc => 'Экспортировать разговоры в JSON-файл';

  @override
  String get exportedConversations => 'Экспортированные разговоры из Omi';

  @override
  String get exportShared => 'Экспорт отправлен';

  @override
  String get deleteKnowledgeGraphTitle => 'Удалить граф знаний?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Это удалит все производные данные графа знаний (узлы и связи). Ваши исходные воспоминания останутся в безопасности. Граф будет восстановлен со временем или при следующем запросе.';

  @override
  String get knowledgeGraphDeleted => 'Граф знаний удалён';

  @override
  String deleteGraphFailed(String error) {
    return 'Не удалось удалить граф: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Удалить граф знаний';

  @override
  String get deleteKnowledgeGraphDesc => 'Очистить все узлы и связи';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Сервер MCP';

  @override
  String get mcpServerDesc => 'Подключите AI-помощников к вашим данным';

  @override
  String get serverUrl => 'URL сервера';

  @override
  String get urlCopied => 'URL скопирован';

  @override
  String get apiKeyAuth => 'Аутентификация по API-ключу';

  @override
  String get header => 'Заголовок';

  @override
  String get authorizationBearer => 'Authorization: Bearer <ключ>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID клиента';

  @override
  String get clientSecret => 'Секрет клиента';

  @override
  String get useMcpApiKey => 'Используйте ваш MCP API-ключ';

  @override
  String get webhooks => 'Вебхуки';

  @override
  String get conversationEvents => 'События беседы';

  @override
  String get newConversationCreated => 'Создан новый разговор';

  @override
  String get realtimeTranscript => 'Транскрипт в реальном времени';

  @override
  String get transcriptReceived => 'Расшифровка получена';

  @override
  String get audioBytes => 'Байты аудио';

  @override
  String get audioDataReceived => 'Данные аудио получены';

  @override
  String get intervalSeconds => 'Интервал (секунды)';

  @override
  String get daySummary => 'Сводка дня';

  @override
  String get summaryGenerated => 'Сводка создана';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Добавить в claude_desktop_config.json';

  @override
  String get copyConfig => 'Копировать конфигурацию';

  @override
  String get configCopied => 'Конфигурация скопирована в буфер обмена';

  @override
  String get listeningMins => 'Прослушивание (мин)';

  @override
  String get understandingWords => 'Понимание (слов)';

  @override
  String get insights => 'Идеи';

  @override
  String get memories => 'Воспоминания';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'Использовано $used из $limit минут в этом месяце';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'Использовано $used из $limit слов в этом месяце';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'Получено $used из $limit инсайтов в этом месяце';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'Создано $used из $limit воспоминаний в этом месяце';
  }

  @override
  String get visibility => 'Видимость';

  @override
  String get visibilitySubtitle => 'Контролируйте, какие разговоры появляются в вашем списке';

  @override
  String get showShortConversations => 'Показывать короткие разговоры';

  @override
  String get showShortConversationsDesc => 'Показывать разговоры короче порогового значения';

  @override
  String get showDiscardedConversations => 'Показывать отброшенные разговоры';

  @override
  String get showDiscardedConversationsDesc => 'Включать разговоры, отмеченные как отброшенные';

  @override
  String get shortConversationThreshold => 'Порог коротких разговоров';

  @override
  String get shortConversationThresholdSubtitle =>
      'Разговоры короче этого значения будут скрыты, если не включено выше';

  @override
  String get durationThreshold => 'Порог длительности';

  @override
  String get durationThresholdDesc => 'Скрыть разговоры короче этого значения';

  @override
  String minLabel(int count) {
    return '$count мин';
  }

  @override
  String get customVocabularyTitle => 'Пользовательский словарь';

  @override
  String get addWords => 'Добавить слова';

  @override
  String get addWordsDesc => 'Имена, термины или редкие слова';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Скоро';

  @override
  String get integrationsFooter => 'Подключите ваши приложения для просмотра данных и метрик в чате.';

  @override
  String get completeAuthInBrowser =>
      'Пожалуйста, завершите аутентификацию в браузере. После этого вернитесь в приложение.';

  @override
  String failedToStartAuth(String appName) {
    return 'Не удалось начать аутентификацию $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Отключить $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Вы уверены, что хотите отключиться от $appName? Вы можете переподключиться в любое время.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Отключено от $appName';
  }

  @override
  String get failedToDisconnect => 'Не удалось отключить';

  @override
  String connectTo(String appName) {
    return 'Подключиться к $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Вам нужно авторизовать Omi для доступа к вашим данным $appName. Это откроет браузер для аутентификации.';
  }

  @override
  String get continueAction => 'Продолжить';

  @override
  String get languageTitle => 'Язык';

  @override
  String get primaryLanguage => 'Основной язык';

  @override
  String get automaticTranslation => 'Автоматический перевод';

  @override
  String get detectLanguages => 'Определение 10+ языков';

  @override
  String get authorizeSavingRecordings => 'Разрешить сохранение записей';

  @override
  String get thanksForAuthorizing => 'Спасибо за разрешение!';

  @override
  String get needYourPermission => 'Нам нужно ваше разрешение';

  @override
  String get alreadyGavePermission =>
      'Вы уже дали нам разрешение на сохранение ваших записей. Напоминаем, зачем нам это нужно:';

  @override
  String get wouldLikePermission =>
      'Мы хотели бы получить ваше разрешение на сохранение ваших голосовых записей. Вот почему:';

  @override
  String get improveSpeechProfile => 'Улучшение вашего голосового профиля';

  @override
  String get improveSpeechProfileDesc =>
      'Мы используем записи для дальнейшего обучения и улучшения вашего персонального голосового профиля.';

  @override
  String get trainFamilyProfiles => 'Обучение профилей друзей и семьи';

  @override
  String get trainFamilyProfilesDesc =>
      'Ваши записи помогают нам распознавать и создавать профили для ваших друзей и семьи.';

  @override
  String get enhanceTranscriptAccuracy => 'Повышение точности расшифровки';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'По мере улучшения нашей модели мы сможем предоставлять лучшие результаты расшифровки для ваших записей.';

  @override
  String get legalNotice =>
      'Юридическое уведомление: Законность записи и хранения голосовых данных может различаться в зависимости от вашего местоположения и того, как вы используете эту функцию. Вы несёте ответственность за соблюдение местных законов и нормативных актов.';

  @override
  String get alreadyAuthorized => 'Уже разрешено';

  @override
  String get authorize => 'Разрешить';

  @override
  String get revokeAuthorization => 'Отозвать разрешение';

  @override
  String get authorizationSuccessful => 'Разрешение успешно получено!';

  @override
  String get failedToAuthorize => 'Не удалось получить разрешение. Пожалуйста, попробуйте снова.';

  @override
  String get authorizationRevoked => 'Разрешение отозвано.';

  @override
  String get recordingsDeleted => 'Записи удалены.';

  @override
  String get failedToRevoke => 'Не удалось отозвать разрешение. Пожалуйста, попробуйте снова.';

  @override
  String get permissionRevokedTitle => 'Разрешение отозвано';

  @override
  String get permissionRevokedMessage => 'Хотите, чтобы мы удалили все ваши существующие записи тоже?';

  @override
  String get yes => 'Да';

  @override
  String get editName => 'Изменить имя';

  @override
  String get howShouldOmiCallYou => 'Как Omi должен вас называть?';

  @override
  String get enterYourName => 'Введите ваше имя';

  @override
  String get nameCannotBeEmpty => 'Имя не может быть пустым';

  @override
  String get nameUpdatedSuccessfully => 'Имя успешно обновлено!';

  @override
  String get calendarSettings => 'Настройки календаря';

  @override
  String get calendarProviders => 'Провайдеры календаря';

  @override
  String get macOsCalendar => 'Календарь macOS';

  @override
  String get connectMacOsCalendar => 'Подключите ваш локальный календарь macOS';

  @override
  String get googleCalendar => 'Google Календарь';

  @override
  String get syncGoogleAccount => 'Синхронизация с вашим аккаунтом Google';

  @override
  String get showMeetingsMenuBar => 'Показывать предстоящие встречи в строке меню';

  @override
  String get showMeetingsMenuBarDesc => 'Отображать вашу следующую встречу и время до её начала в строке меню macOS';

  @override
  String get showEventsNoParticipants => 'Показывать события без участников';

  @override
  String get showEventsNoParticipantsDesc =>
      'Когда включено, Coming Up показывает события без участников или видеосвязи.';

  @override
  String get yourMeetings => 'Ваши встречи';

  @override
  String get refresh => 'Обновить';

  @override
  String get noUpcomingMeetings => 'Нет предстоящих встреч';

  @override
  String get checkingNextDays => 'Проверка следующих 30 дней';

  @override
  String get tomorrow => 'Завтра';

  @override
  String get googleCalendarComingSoon => 'Интеграция с Google Календарём скоро!';

  @override
  String connectedAsUser(String userId) {
    return 'Подключено как пользователь: $userId';
  }

  @override
  String get defaultWorkspace => 'Рабочее пространство по умолчанию';

  @override
  String get tasksCreatedInWorkspace => 'Задачи будут созданы в этом рабочем пространстве';

  @override
  String get defaultProjectOptional => 'Проект по умолчанию (опционально)';

  @override
  String get leaveUnselectedTasks => 'Оставьте не выбранным для создания задач без проекта';

  @override
  String get noProjectsInWorkspace => 'Проекты в этом рабочем пространстве не найдены';

  @override
  String get conversationTimeoutDesc =>
      'Выберите, сколько времени ждать в тишине перед автоматическим завершением разговора:';

  @override
  String get timeout2Minutes => '2 минуты';

  @override
  String get timeout2MinutesDesc => 'Завершить разговор после 2 минут тишины';

  @override
  String get timeout5Minutes => '5 минут';

  @override
  String get timeout5MinutesDesc => 'Завершить разговор после 5 минут тишины';

  @override
  String get timeout10Minutes => '10 минут';

  @override
  String get timeout10MinutesDesc => 'Завершить разговор после 10 минут тишины';

  @override
  String get timeout30Minutes => '30 минут';

  @override
  String get timeout30MinutesDesc => 'Завершить разговор после 30 минут тишины';

  @override
  String get timeout4Hours => '4 часа';

  @override
  String get timeout4HoursDesc => 'Завершить разговор после 4 часов тишины';

  @override
  String get conversationEndAfterHours => 'Разговоры теперь будут завершаться после 4 часов тишины';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Разговоры теперь будут завершаться после $minutes минут тишины';
  }

  @override
  String get tellUsPrimaryLanguage => 'Укажите ваш основной язык';

  @override
  String get languageForTranscription =>
      'Установите ваш язык для более точной расшифровки и персонализированного опыта.';

  @override
  String get singleLanguageModeInfo => 'Режим одного языка включён. Перевод отключён для повышения точности.';

  @override
  String get searchLanguageHint => 'Поиск языка по названию или коду';

  @override
  String get noLanguagesFound => 'Языки не найдены';

  @override
  String get skip => 'Пропустить';

  @override
  String languageSetTo(String language) {
    return 'Язык установлен на $language';
  }

  @override
  String get failedToSetLanguage => 'Не удалось установить язык';

  @override
  String appSettings(String appName) {
    return 'Настройки $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Отключиться от $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Это удалит вашу аутентификацию $appName. Вам нужно будет переподключиться для повторного использования.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Подключено к $appName';
  }

  @override
  String get account => 'Аккаунт';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Ваши задачи будут синхронизированы с вашим аккаунтом $appName';
  }

  @override
  String get defaultSpace => 'Пространство по умолчанию';

  @override
  String get selectSpaceInWorkspace => 'Выберите пространство в вашем рабочем пространстве';

  @override
  String get noSpacesInWorkspace => 'Пространства в этом рабочем пространстве не найдены';

  @override
  String get defaultList => 'Список по умолчанию';

  @override
  String get tasksAddedToList => 'Задачи будут добавлены в этот список';

  @override
  String get noListsInSpace => 'Списки в этом пространстве не найдены';

  @override
  String failedToLoadRepos(String error) {
    return 'Не удалось загрузить репозитории: $error';
  }

  @override
  String get defaultRepoSaved => 'Репозиторий по умолчанию сохранён';

  @override
  String get failedToSaveDefaultRepo => 'Не удалось сохранить репозиторий по умолчанию';

  @override
  String get defaultRepository => 'Репозиторий по умолчанию';

  @override
  String get selectDefaultRepoDesc =>
      'Выберите репозиторий по умолчанию для создания задач. Вы все еще можете указать другой репозиторий при создании задач.';

  @override
  String get noReposFound => 'Репозитории не найдены';

  @override
  String get private => 'Приватная';

  @override
  String updatedDate(String date) {
    return 'Обновлено $date';
  }

  @override
  String get yesterday => 'Вчера';

  @override
  String daysAgo(int count) {
    return '$count дней назад';
  }

  @override
  String get oneWeekAgo => '1 неделю назад';

  @override
  String weeksAgo(int count) {
    return '$count недель назад';
  }

  @override
  String get oneMonthAgo => '1 месяц назад';

  @override
  String monthsAgo(int count) {
    return '$count месяцев назад';
  }

  @override
  String get issuesCreatedInRepo => 'Задачи будут создаваться в вашем репозитории по умолчанию';

  @override
  String get taskIntegrations => 'Интеграции задач';

  @override
  String get configureSettings => 'Настроить параметры';

  @override
  String get completeAuthBrowser =>
      'Пожалуйста, завершите аутентификацию в браузере. После этого вернитесь в приложение.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Не удалось начать аутентификацию $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Подключиться к $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Вам нужно авторизовать Omi для создания задач в вашем аккаунте $appName. Это откроет браузер для аутентификации.';
  }

  @override
  String get continueButton => 'Продолжить';

  @override
  String appIntegration(String appName) {
    return 'Интеграция $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Интеграция с $appName скоро! Мы упорно работаем, чтобы предоставить вам больше вариантов управления задачами.';
  }

  @override
  String get gotIt => 'Понятно';

  @override
  String get tasksExportedOneApp => 'Задачи могут быть экспортированы только в одно приложение за раз.';

  @override
  String get completeYourUpgrade => 'Завершите обновление';

  @override
  String get importConfiguration => 'Импорт конфигурации';

  @override
  String get exportConfiguration => 'Экспорт конфигурации';

  @override
  String get bringYourOwn => 'Используйте свой';

  @override
  String get payYourSttProvider => 'Свободно используйте omi. Вы платите только своему провайдеру STT напрямую.';

  @override
  String get freeMinutesMonth => '1200 бесплатных минут в месяц включено. Безлимитно с ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Требуется хост';

  @override
  String get validPortRequired => 'Требуется действительный порт';

  @override
  String get validWebsocketUrlRequired => 'Требуется действительный URL WebSocket (wss://)';

  @override
  String get apiUrlRequired => 'Требуется URL API';

  @override
  String get apiKeyRequired => 'Требуется API-ключ';

  @override
  String get invalidJsonConfig => 'Недействительная конфигурация JSON';

  @override
  String errorSaving(String error) {
    return 'Ошибка сохранения: $error';
  }

  @override
  String get configCopiedToClipboard => 'Конфигурация скопирована в буфер обмена';

  @override
  String get pasteJsonConfig => 'Вставьте вашу конфигурацию JSON ниже:';

  @override
  String get addApiKeyAfterImport => 'Вам нужно будет добавить свой API-ключ после импорта';

  @override
  String get paste => 'Вставить';

  @override
  String get import => 'Импорт';

  @override
  String get invalidProviderInConfig => 'Недействительный провайдер в конфигурации';

  @override
  String importedConfig(String providerName) {
    return 'Импортирована конфигурация $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'Недействительный JSON: $error';
  }

  @override
  String get provider => 'Провайдер';

  @override
  String get live => 'В реальном времени';

  @override
  String get onDevice => 'На устройстве';

  @override
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Введите вашу конечную точку STT HTTP';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Введите вашу конечную точку WebSocket для STT в реальном времени';

  @override
  String get apiKey => 'API ключ';

  @override
  String get enterApiKey => 'Введите ваш API-ключ';

  @override
  String get storedLocallyNeverShared => 'Хранится локально, никогда не передаётся';

  @override
  String get host => 'Хост';

  @override
  String get port => 'Порт';

  @override
  String get advanced => 'Расширенные';

  @override
  String get configuration => 'Конфигурация';

  @override
  String get requestConfiguration => 'Конфигурация запроса';

  @override
  String get responseSchema => 'Схема ответа';

  @override
  String get modified => 'Изменено';

  @override
  String get resetRequestConfig => 'Сбросить конфигурацию запроса по умолчанию';

  @override
  String get logs => 'Журналы';

  @override
  String get logsCopied => 'Журналы скопированы';

  @override
  String get noLogsYet => 'Журналов пока нет. Начните запись, чтобы увидеть активность пользовательского STT.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device использует $reason. Будет использован Omi.';
  }

  @override
  String get omiTranscription => 'Расшифровка Omi';

  @override
  String get bestInClassTranscription => 'Лучшая расшифровка без настройки';

  @override
  String get instantSpeakerLabels => 'Мгновенные метки спикеров';

  @override
  String get languageTranslation => 'Перевод на 100+ языков';

  @override
  String get optimizedForConversation => 'Оптимизировано для разговоров';

  @override
  String get autoLanguageDetection => 'Автоматическое определение языка';

  @override
  String get highAccuracy => 'Высокая точность';

  @override
  String get privacyFirst => 'Конфиденциальность прежде всего';

  @override
  String get saveChanges => 'Сохранить изменения';

  @override
  String get resetToDefault => 'Сбросить по умолчанию';

  @override
  String get viewTemplate => 'Просмотреть шаблон';

  @override
  String get trySomethingLike => 'Попробуйте что-то вроде...';

  @override
  String get tryIt => 'Попробовать';

  @override
  String get creatingPlan => 'Создание плана';

  @override
  String get developingLogic => 'Разработка логики';

  @override
  String get designingApp => 'Проектирование приложения';

  @override
  String get generatingIconStep => 'Генерация иконки';

  @override
  String get finalTouches => 'Завершающие штрихи';

  @override
  String get processing => 'Обработка...';

  @override
  String get features => 'Возможности';

  @override
  String get creatingYourApp => 'Создание вашего приложения...';

  @override
  String get generatingIcon => 'Генерация иконки...';

  @override
  String get whatShouldWeMake => 'Что мы должны создать?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Описание';

  @override
  String get publicLabel => 'Публичное';

  @override
  String get privateLabel => 'Приватное';

  @override
  String get free => 'Бесплатно';

  @override
  String get perMonth => '/ Месяц';

  @override
  String get tailoredConversationSummaries => 'Персонализированные резюме разговоров';

  @override
  String get customChatbotPersonality => 'Пользовательская личность чат-бота';

  @override
  String get makePublic => 'Сделать публичной';

  @override
  String get anyoneCanDiscover => 'Любой может найти ваше приложение';

  @override
  String get onlyYouCanUse => 'Только вы можете использовать это приложение';

  @override
  String get paidApp => 'Платное приложение';

  @override
  String get usersPayToUse => 'Пользователи платят за использование вашего приложения';

  @override
  String get freeForEveryone => 'Бесплатно для всех';

  @override
  String get perMonthLabel => '/ месяц';

  @override
  String get creating => 'Создание...';

  @override
  String get createApp => 'Создать приложение';

  @override
  String get searchingForDevices => 'Поиск устройств...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'УСТРОЙСТВ',
      few: 'УСТРОЙСТВА',
      one: 'УСТРОЙСТВО',
    );
    return '$_temp0 НАЙДЕНО РЯДОМ: $count';
  }

  @override
  String get pairingSuccessful => 'СОПРЯЖЕНИЕ УСПЕШНО';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Ошибка подключения к Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Больше не показывать';

  @override
  String get iUnderstand => 'Я понимаю';

  @override
  String get enableBluetooth => 'Включите Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi требуется Bluetooth для подключения к вашему устройству. Пожалуйста, включите Bluetooth и попробуйте снова.';

  @override
  String get contactSupport => 'Связаться с поддержкой?';

  @override
  String get connectLater => 'Подключить позже';

  @override
  String get grantPermissions => 'Предоставить разрешения';

  @override
  String get backgroundActivity => 'Фоновая активность';

  @override
  String get backgroundActivityDesc => 'Позвольте Omi работать в фоновом режиме для лучшей стабильности';

  @override
  String get locationAccess => 'Доступ к местоположению';

  @override
  String get locationAccessDesc => 'Включите фоновое определение местоположения для полного опыта';

  @override
  String get notifications => 'Уведомления';

  @override
  String get notificationsDesc => 'Включите уведомления, чтобы быть в курсе';

  @override
  String get locationServiceDisabled => 'Служба определения местоположения отключена';

  @override
  String get locationServiceDisabledDesc =>
      'Служба определения местоположения отключена. Пожалуйста, перейдите в Настройки > Конфиденциальность и безопасность > Службы геолокации и включите её';

  @override
  String get backgroundLocationDenied => 'Доступ к местоположению в фоновом режиме отклонён';

  @override
  String get backgroundLocationDeniedDesc =>
      'Пожалуйста, перейдите в настройки устройства и установите разрешение на местоположение как \"Всегда разрешать\"';

  @override
  String get lovingOmi => 'Нравится Omi?';

  @override
  String get leaveReviewIos =>
      'Помогите нам достичь большего количества людей, оставив отзыв в App Store. Ваш отзыв очень важен для нас!';

  @override
  String get leaveReviewAndroid =>
      'Помогите нам достичь большего количества людей, оставив отзыв в Google Play Store. Ваш отзыв очень важен для нас!';

  @override
  String get rateOnAppStore => 'Оценить в App Store';

  @override
  String get rateOnGooglePlay => 'Оценить в Google Play';

  @override
  String get maybeLater => 'Может быть, позже';

  @override
  String get speechProfileIntro => 'Omi нужно узнать ваши цели и ваш голос. Вы сможете изменить это позже.';

  @override
  String get getStarted => 'Начать';

  @override
  String get allDone => 'Всё готово!';

  @override
  String get keepGoing => 'Продолжайте, вы отлично справляетесь';

  @override
  String get skipThisQuestion => 'Пропустить этот вопрос';

  @override
  String get skipForNow => 'Пропустить пока';

  @override
  String get connectionError => 'Ошибка подключения';

  @override
  String get connectionErrorDesc =>
      'Не удалось подключиться к серверу. Пожалуйста, проверьте подключение к интернету и попробуйте снова.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Обнаружена недействительная запись';

  @override
  String get multipleSpeakersDesc =>
      'Похоже, в записи несколько говорящих. Пожалуйста, убедитесь, что вы находитесь в тихом месте, и попробуйте снова.';

  @override
  String get tooShortDesc => 'Обнаружено недостаточно речи. Пожалуйста, говорите больше и попробуйте снова.';

  @override
  String get invalidRecordingDesc => 'Пожалуйста, убедитесь, что вы говорите не менее 5 секунд и не более 90.';

  @override
  String get areYouThere => 'Вы здесь?';

  @override
  String get noSpeechDesc =>
      'Мы не смогли обнаружить речь. Пожалуйста, убедитесь, что говорите не менее 10 секунд и не более 3 минут.';

  @override
  String get connectionLost => 'Соединение потеряно';

  @override
  String get connectionLostDesc =>
      'Соединение было прервано. Пожалуйста, проверьте подключение к интернету и попробуйте снова.';

  @override
  String get tryAgain => 'Попробовать снова';

  @override
  String get connectOmiOmiGlass => 'Подключить Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Продолжить без устройства';

  @override
  String get permissionsRequired => 'Требуются разрешения';

  @override
  String get permissionsRequiredDesc =>
      'Этому приложению нужны разрешения Bluetooth и Местоположение для правильной работы. Пожалуйста, включите их в настройках.';

  @override
  String get openSettings => 'Открыть настройки';

  @override
  String get wantDifferentName => 'Хотите использовать другое имя?';

  @override
  String get whatsYourName => 'Как вас зовут?';

  @override
  String get speakTranscribeSummarize => 'Говорите. Расшифровывайте. Резюмируйте.';

  @override
  String get signInWithApple => 'Войти с Apple';

  @override
  String get signInWithGoogle => 'Войти с Google';

  @override
  String get byContinuingAgree => 'Продолжая, вы соглашаетесь с нашей ';

  @override
  String get termsOfUse => 'Условиями использования';

  @override
  String get omiYourAiCompanion => 'Omi – ваш AI-компаньон';

  @override
  String get captureEveryMoment => 'Фиксируйте каждый момент. Получайте резюме на основе AI.\nБольше никаких заметок.';

  @override
  String get appleWatchSetup => 'Настройка Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Разрешение запрошено!';

  @override
  String get microphonePermission => 'Разрешение на микрофон';

  @override
  String get permissionGrantedNow =>
      'Разрешение предоставлено! Теперь:\n\nОткройте приложение Omi на ваших часах и нажмите \"Продолжить\" ниже';

  @override
  String get needMicrophonePermission =>
      'Нам нужно разрешение на микрофон.\n\n1. Нажмите \"Предоставить разрешение\"\n2. Разрешите на вашем iPhone\n3. Приложение на часах закроется\n4. Откройте снова и нажмите \"Продолжить\"';

  @override
  String get grantPermissionButton => 'Предоставить разрешение';

  @override
  String get needHelp => 'Нужна помощь?';

  @override
  String get troubleshootingSteps =>
      'Устранение неполадок:\n\n1. Убедитесь, что Omi установлен на ваших часах\n2. Откройте приложение Omi на ваших часах\n3. Найдите всплывающее окно с разрешением\n4. Нажмите \"Разрешить\" при запросе\n5. Приложение на часах закроется - откройте его снова\n6. Вернитесь и нажмите \"Продолжить\" на вашем iPhone';

  @override
  String get recordingStartedSuccessfully => 'Запись успешно начата!';

  @override
  String get permissionNotGrantedYet =>
      'Разрешение ещё не предоставлено. Пожалуйста, убедитесь, что вы разрешили доступ к микрофону и открыли приложение на часах заново.';

  @override
  String errorRequestingPermission(String error) {
    return 'Ошибка при запросе разрешения: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Ошибка при начале записи: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Выберите ваш основной язык';

  @override
  String get languageBenefits => 'Установите ваш язык для более точной расшифровки и персонализированного опыта';

  @override
  String get whatsYourPrimaryLanguage => 'Какой ваш основной язык?';

  @override
  String get selectYourLanguage => 'Выберите ваш язык';

  @override
  String get personalGrowthJourney => 'Ваше путешествие личностного роста с ИИ, который слушает каждое ваше слово.';

  @override
  String get actionItemsTitle => 'Задачи';

  @override
  String get actionItemsDescription => 'Нажмите для редактирования • Удерживайте для выбора • Свайп для действий';

  @override
  String get tabToDo => 'К выполнению';

  @override
  String get tabDone => 'Выполнено';

  @override
  String get tabOld => 'Старые';

  @override
  String get emptyTodoMessage => '🎉 Всё выполнено!\nНет ожидающих задач';

  @override
  String get emptyDoneMessage => 'Выполненных задач пока нет';

  @override
  String get emptyOldMessage => '✅ Нет старых задач';

  @override
  String get noItems => 'Нет элементов';

  @override
  String get actionItemMarkedIncomplete => 'Задача отмечена как невыполненная';

  @override
  String get actionItemCompleted => 'Задача выполнена';

  @override
  String get deleteActionItemTitle => 'Удалить элемент действия';

  @override
  String get deleteActionItemMessage => 'Вы уверены, что хотите удалить этот элемент действия?';

  @override
  String get deleteSelectedItemsTitle => 'Удалить выбранные элементы';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Вы уверены, что хотите удалить $count выбранных задач$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Задача \"$description\" удалена';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return 'Удалено $count задач$s';
  }

  @override
  String get failedToDeleteItem => 'Не удалось удалить задачу';

  @override
  String get failedToDeleteItems => 'Не удалось удалить элементы';

  @override
  String get failedToDeleteSomeItems => 'Не удалось удалить некоторые элементы';

  @override
  String get welcomeActionItemsTitle => 'Готово к задачам';

  @override
  String get welcomeActionItemsDescription =>
      'Ваш AI автоматически извлечёт задачи и дела из ваших разговоров. Они появятся здесь при создании.';

  @override
  String get autoExtractionFeature => 'Автоматически извлекается из разговоров';

  @override
  String get editSwipeFeature => 'Нажмите для редактирования, свайп для завершения или удаления';

  @override
  String itemsSelected(int count) {
    return 'Выбрано $count';
  }

  @override
  String get selectAll => 'Выбрать всё';

  @override
  String get deleteSelected => 'Удалить выбранное';

  @override
  String get searchMemories => 'Поиск воспоминаний...';

  @override
  String get memoryDeleted => 'Воспоминание удалено.';

  @override
  String get undo => 'Отменить';

  @override
  String get noMemoriesYet => '🧠 Пока нет воспоминаний';

  @override
  String get noAutoMemories => 'Автоматически извлечённых воспоминаний пока нет';

  @override
  String get noManualMemories => 'Ручных воспоминаний пока нет';

  @override
  String get noMemoriesInCategories => 'Нет воспоминаний в этих категориях';

  @override
  String get noMemoriesFound => '🔍 Воспоминания не найдены';

  @override
  String get addFirstMemory => 'Добавьте ваше первое воспоминание';

  @override
  String get clearMemoryTitle => 'Очистить память Omi';

  @override
  String get clearMemoryMessage => 'Вы уверены, что хотите очистить память Omi? Это действие нельзя отменить.';

  @override
  String get clearMemoryButton => 'Очистить память';

  @override
  String get memoryClearedSuccess => 'Память Omi о вас была очищена';

  @override
  String get noMemoriesToDelete => 'Нет воспоминаний для удаления';

  @override
  String get createMemoryTooltip => 'Создать новое воспоминание';

  @override
  String get createActionItemTooltip => 'Создать новую задачу';

  @override
  String get memoryManagement => 'Управление памятью';

  @override
  String get filterMemories => 'Фильтр воспоминаний';

  @override
  String totalMemoriesCount(int count) {
    return 'У вас всего $count воспоминаний';
  }

  @override
  String get publicMemories => 'Публичные воспоминания';

  @override
  String get privateMemories => 'Приватные воспоминания';

  @override
  String get makeAllPrivate => 'Сделать все воспоминания приватными';

  @override
  String get makeAllPublic => 'Сделать все воспоминания публичными';

  @override
  String get deleteAllMemories => 'Удалить все воспоминания';

  @override
  String get allMemoriesPrivateResult => 'Все воспоминания теперь приватные';

  @override
  String get allMemoriesPublicResult => 'Все воспоминания теперь публичные';

  @override
  String get newMemory => '✨ Новая память';

  @override
  String get editMemory => '✏️ Редактировать память';

  @override
  String get memoryContentHint => 'Я люблю есть мороженое...';

  @override
  String get failedToSaveMemory => 'Не удалось сохранить. Пожалуйста, проверьте подключение.';

  @override
  String get saveMemory => 'Сохранить воспоминание';

  @override
  String get retry => 'Повторить';

  @override
  String get createActionItem => 'Создать задачу';

  @override
  String get editActionItem => 'Редактировать задачу';

  @override
  String get actionItemDescriptionHint => 'Что нужно сделать?';

  @override
  String get actionItemDescriptionEmpty => 'Описание задачи не может быть пустым.';

  @override
  String get actionItemUpdated => 'Задача обновлена';

  @override
  String get failedToUpdateActionItem => 'Не удалось обновить задачу';

  @override
  String get actionItemCreated => 'Задача создана';

  @override
  String get failedToCreateActionItem => 'Не удалось создать задачу';

  @override
  String get dueDate => 'Срок выполнения';

  @override
  String get time => 'Время';

  @override
  String get addDueDate => 'Добавить срок выполнения';

  @override
  String get pressDoneToSave => 'Нажмите готово для сохранения';

  @override
  String get pressDoneToCreate => 'Нажмите готово для создания';

  @override
  String get filterAll => 'Все';

  @override
  String get filterSystem => 'О вас';

  @override
  String get filterInteresting => 'Инсайты';

  @override
  String get filterManual => 'Ручные';

  @override
  String get completed => 'Завершено';

  @override
  String get markComplete => 'Отметить как выполненное';

  @override
  String get actionItemDeleted => 'Элемент действия удален';

  @override
  String get failedToDeleteActionItem => 'Не удалось удалить задачу';

  @override
  String get deleteActionItemConfirmTitle => 'Удалить задачу';

  @override
  String get deleteActionItemConfirmMessage => 'Вы уверены, что хотите удалить эту задачу?';

  @override
  String get appLanguage => 'Язык приложения';

  @override
  String get appInterfaceSectionTitle => 'ИНТЕРФЕЙС ПРИЛОЖЕНИЯ';

  @override
  String get speechTranscriptionSectionTitle => 'РЕЧЬ И ТРАНСКРИПЦИЯ';

  @override
  String get languageSettingsHelperText =>
      'Язык приложения изменяет меню и кнопки. Язык речи влияет на то, как транскрибируются ваши записи.';

  @override
  String get translationNotice => 'Уведомление о переводе';

  @override
  String get translationNoticeMessage =>
      'Omi переводит разговоры на ваш основной язык. Обновите его в любое время в Настройки → Профили.';

  @override
  String get pleaseCheckInternetConnection => 'Пожалуйста, проверьте подключение к Интернету и повторите попытку';

  @override
  String get pleaseSelectReason => 'Пожалуйста, выберите причину';

  @override
  String get tellUsMoreWhatWentWrong => 'Расскажите нам подробнее, что пошло не так...';

  @override
  String get selectText => 'Выбрать текст';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Максимум $count целей разрешено';
  }

  @override
  String get conversationCannotBeMerged => 'Этот разговор нельзя объединить (заблокирован или уже объединяется)';

  @override
  String get pleaseEnterFolderName => 'Пожалуйста, введите имя папки';

  @override
  String get failedToCreateFolder => 'Не удалось создать папку';

  @override
  String get failedToUpdateFolder => 'Не удалось обновить папку';

  @override
  String get folderName => 'Имя папки';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Не удалось удалить папку';

  @override
  String get editFolder => 'Редактировать папку';

  @override
  String get deleteFolder => 'Удалить папку';

  @override
  String get transcriptCopiedToClipboard => 'Транскрипт скопирован в буфер обмена';

  @override
  String get summaryCopiedToClipboard => 'Резюме скопировано в буфер обмена';

  @override
  String get conversationUrlCouldNotBeShared => 'Не удалось поделиться ссылкой на разговор.';

  @override
  String get urlCopiedToClipboard => 'URL скопирован в буфер обмена';

  @override
  String get exportTranscript => 'Экспортировать транскрипт';

  @override
  String get exportSummary => 'Экспортировать резюме';

  @override
  String get exportButton => 'Экспортировать';

  @override
  String get actionItemsCopiedToClipboard => 'Пункты действий скопированы в буфер обмена';

  @override
  String get summarize => 'Резюмировать';

  @override
  String get generateSummary => 'Создать сводку';

  @override
  String get conversationNotFoundOrDeleted => 'Разговор не найден или был удален';

  @override
  String get deleteMemory => 'Удалить память';

  @override
  String get thisActionCannotBeUndone => 'Это действие нельзя отменить.';

  @override
  String memoriesCount(int count) {
    return '$count воспоминаний';
  }

  @override
  String get noMemoriesInCategory => 'В этой категории пока нет воспоминаний';

  @override
  String get addYourFirstMemory => 'Добавьте первое воспоминание';

  @override
  String get firmwareDisconnectUsb => 'Отключите USB';

  @override
  String get firmwareUsbWarning => 'USB-соединение во время обновлений может повредить ваше устройство.';

  @override
  String get firmwareBatteryAbove15 => 'Батарея выше 15%';

  @override
  String get firmwareEnsureBattery => 'Убедитесь, что у вашего устройства 15% заряда батареи.';

  @override
  String get firmwareStableConnection => 'Стабильное соединение';

  @override
  String get firmwareConnectWifi => 'Подключитесь к WiFi или мобильной сети.';

  @override
  String failedToStartUpdate(String error) {
    return 'Не удалось начать обновление: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Перед обновлением убедитесь:';

  @override
  String get confirmed => 'Подтверждено!';

  @override
  String get release => 'Отпустите';

  @override
  String get slideToUpdate => 'Проведите для обновления';

  @override
  String copiedToClipboard(String title) {
    return '$title скопировано в буфер обмена';
  }

  @override
  String get batteryLevel => 'Уровень заряда';

  @override
  String get productUpdate => 'Обновление продукта';

  @override
  String get offline => 'Не в сети';

  @override
  String get available => 'Доступно';

  @override
  String get unpairDeviceDialogTitle => 'Отменить сопряжение устройства';

  @override
  String get unpairDeviceDialogMessage =>
      'Это отменит сопряжение устройства, чтобы его можно было подключить к другому телефону. Вам нужно будет перейти в Настройки > Bluetooth и забыть устройство, чтобы завершить процесс.';

  @override
  String get unpair => 'Отменить сопряжение';

  @override
  String get unpairAndForgetDevice => 'Отменить сопряжение и забыть устройство';

  @override
  String get unknownDevice => 'Неизвестно';

  @override
  String get unknown => 'Неизвестно';

  @override
  String get productName => 'Название продукта';

  @override
  String get serialNumber => 'Серийный номер';

  @override
  String get connected => 'Подключено';

  @override
  String get privacyPolicyTitle => 'Политика конфиденциальности';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label скопировано';
  }

  @override
  String get noApiKeysYet => 'API-ключей пока нет. Создайте один для интеграции с вашим приложением.';

  @override
  String get createKeyToGetStarted => 'Создайте ключ, чтобы начать';

  @override
  String get persona => 'Персона';

  @override
  String get configureYourAiPersona => 'Настройте свою AI-персону';

  @override
  String get configureSttProvider => 'Настроить провайдера STT';

  @override
  String get setWhenConversationsAutoEnd => 'Установите, когда разговоры заканчиваются автоматически';

  @override
  String get importDataFromOtherSources => 'Импорт данных из других источников';

  @override
  String get debugAndDiagnostics => 'Отладка и диагностика';

  @override
  String get autoDeletesAfter3Days => 'Автоматическое удаление через 3 дня';

  @override
  String get helpsDiagnoseIssues => 'Помогает диагностировать проблемы';

  @override
  String get exportStartedMessage => 'Экспорт начат. Это может занять несколько секунд...';

  @override
  String get exportConversationsToJson => 'Экспорт разговоров в JSON-файл';

  @override
  String get knowledgeGraphDeletedSuccess => 'Граф знаний успешно удалён';

  @override
  String failedToDeleteGraph(String error) {
    return 'Не удалось удалить граф: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Очистить все узлы и соединения';

  @override
  String get addToClaudeDesktopConfig => 'Добавить в claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Подключите AI-помощников к вашим данным';

  @override
  String get useYourMcpApiKey => 'Используйте свой MCP API-ключ';

  @override
  String get realTimeTranscript => 'Транскрипция в реальном времени';

  @override
  String get experimental => 'Экспериментальный';

  @override
  String get transcriptionDiagnostics => 'Диагностика транскрипции';

  @override
  String get detailedDiagnosticMessages => 'Подробные диагностические сообщения';

  @override
  String get autoCreateSpeakers => 'Автосоздание спикеров';

  @override
  String get autoCreateWhenNameDetected => 'Автоматически создавать при обнаружении имени';

  @override
  String get followUpQuestions => 'Дополнительные вопросы';

  @override
  String get suggestQuestionsAfterConversations => 'Предлагать вопросы после разговоров';

  @override
  String get goalTracker => 'Отслеживание целей';

  @override
  String get trackPersonalGoalsOnHomepage => 'Отслеживайте личные цели на главной странице';

  @override
  String get dailyReflection => 'Ежедневная рефлексия';

  @override
  String get get9PmReminderToReflect => 'Получите напоминание в 21:00, чтобы подвести итоги дня';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Описание элемента действия не может быть пустым';

  @override
  String get saved => 'Сохранено';

  @override
  String get overdue => 'Просрочено';

  @override
  String get failedToUpdateDueDate => 'Не удалось обновить срок';

  @override
  String get markIncomplete => 'Отметить как невыполненное';

  @override
  String get editDueDate => 'Изменить срок';

  @override
  String get setDueDate => 'Установить срок';

  @override
  String get clearDueDate => 'Очистить срок';

  @override
  String get failedToClearDueDate => 'Не удалось очистить срок';

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
  String get howDoesItWork => 'Как это работает?';

  @override
  String get sdCardSyncDescription => 'Синхронизация SD-карты импортирует ваши воспоминания с SD-карты в приложение';

  @override
  String get checksForAudioFiles => 'Проверяет аудиофайлы на SD-карте';

  @override
  String get omiSyncsAudioFiles => 'Omi затем синхронизирует аудиофайлы с сервером';

  @override
  String get serverProcessesAudio => 'Сервер обрабатывает аудиофайлы и создает воспоминания';

  @override
  String get youreAllSet => 'Всё готово!';

  @override
  String get welcomeToOmiDescription =>
      'Добро пожаловать в Omi! Ваш AI-компаньон готов помочь вам с разговорами, задачами и многим другим.';

  @override
  String get startUsingOmi => 'Начать использовать Omi';

  @override
  String get back => 'Назад';

  @override
  String get keyboardShortcuts => 'Горячие Клавиши';

  @override
  String get toggleControlBar => 'Переключить панель управления';

  @override
  String get pressKeys => 'Нажмите клавиши...';

  @override
  String get cmdRequired => '⌘ требуется';

  @override
  String get invalidKey => 'Недопустимая клавиша';

  @override
  String get space => 'Пробел';

  @override
  String get search => 'Поиск';

  @override
  String get searchPlaceholder => 'Поиск...';

  @override
  String get untitledConversation => 'Разговор без названия';

  @override
  String countRemaining(String count) {
    return '$count осталось';
  }

  @override
  String get addGoal => 'Добавить цель';

  @override
  String get editGoal => 'Редактировать цель';

  @override
  String get icon => 'Значок';

  @override
  String get goalTitle => 'Название цели';

  @override
  String get current => 'Текущее';

  @override
  String get target => 'Цель';

  @override
  String get saveGoal => 'Сохранить';

  @override
  String get goals => 'Цели';

  @override
  String get tapToAddGoal => 'Нажмите, чтобы добавить цель';

  @override
  String welcomeBack(String name) {
    return 'С возвращением, $name';
  }

  @override
  String get yourConversations => 'Ваши разговоры';

  @override
  String get reviewAndManageConversations => 'Просматривайте и управляйте записанными разговорами';

  @override
  String get startCapturingConversations =>
      'Начните записывать разговоры с помощью устройства Omi, чтобы увидеть их здесь.';

  @override
  String get useMobileAppToCapture => 'Используйте мобильное приложение для записи аудио';

  @override
  String get conversationsProcessedAutomatically => 'Разговоры обрабатываются автоматически';

  @override
  String get getInsightsInstantly => 'Получайте информацию и резюме мгновенно';

  @override
  String get showAll => 'Показать все →';

  @override
  String get noTasksForToday => 'Нет задач на сегодня.\\nСпросите Omi о дополнительных задачах или создайте вручную.';

  @override
  String get dailyScore => 'ДНЕВНОЙ СЧЁТ';

  @override
  String get dailyScoreDescription => 'Счёт, помогающий лучше\nсосредоточиться на выполнении.';

  @override
  String get searchResults => 'Результаты поиска';

  @override
  String get actionItems => 'Задачи';

  @override
  String get tasksToday => 'Сегодня';

  @override
  String get tasksTomorrow => 'Завтра';

  @override
  String get tasksNoDeadline => 'Без срока';

  @override
  String get tasksLater => 'Позже';

  @override
  String get loadingTasks => 'Загрузка задач...';

  @override
  String get tasks => 'Задачи';

  @override
  String get swipeTasksToIndent => 'Проведите пальцем по задачам для отступа, перетащите между категориями';

  @override
  String get create => 'Создать';

  @override
  String get noTasksYet => 'Пока нет задач';

  @override
  String get tasksFromConversationsWillAppear =>
      'Задачи из ваших разговоров появятся здесь.\nНажмите Создать, чтобы добавить задачу вручную.';

  @override
  String get monthJan => 'Янв';

  @override
  String get monthFeb => 'Фев';

  @override
  String get monthMar => 'Мар';

  @override
  String get monthApr => 'Апр';

  @override
  String get monthMay => 'Май';

  @override
  String get monthJun => 'Июн';

  @override
  String get monthJul => 'Июл';

  @override
  String get monthAug => 'Авг';

  @override
  String get monthSep => 'Сен';

  @override
  String get monthOct => 'Окт';

  @override
  String get monthNov => 'Ноя';

  @override
  String get monthDec => 'Дек';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Задача успешно обновлена';

  @override
  String get actionItemCreatedSuccessfully => 'Задача успешно создана';

  @override
  String get actionItemDeletedSuccessfully => 'Задача успешно удалена';

  @override
  String get deleteActionItem => 'Удалить задачу';

  @override
  String get deleteActionItemConfirmation => 'Вы уверены, что хотите удалить эту задачу? Это действие нельзя отменить.';

  @override
  String get enterActionItemDescription => 'Введите описание задачи...';

  @override
  String get markAsCompleted => 'Отметить как выполненную';

  @override
  String get setDueDateAndTime => 'Установить срок и время';

  @override
  String get reloadingApps => 'Перезагрузка приложений...';

  @override
  String get loadingApps => 'Загрузка приложений...';

  @override
  String get browseInstallCreateApps => 'Просматривайте, устанавливайте и создавайте приложения';

  @override
  String get all => 'Все';

  @override
  String get open => 'Открыть';

  @override
  String get install => 'Установить';

  @override
  String get noAppsAvailable => 'Нет доступных приложений';

  @override
  String get unableToLoadApps => 'Не удалось загрузить приложения';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Попробуйте изменить условия поиска или фильтры';

  @override
  String get checkBackLaterForNewApps => 'Загляните позже за новыми приложениями';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Пожалуйста, проверьте подключение к Интернету и попробуйте снова';

  @override
  String get createNewApp => 'Создать новое приложение';

  @override
  String get buildSubmitCustomOmiApp => 'Создайте и отправьте свое пользовательское приложение Omi';

  @override
  String get submittingYourApp => 'Отправка вашего приложения...';

  @override
  String get preparingFormForYou => 'Подготовка формы для вас...';

  @override
  String get appDetails => 'Сведения о приложении';

  @override
  String get paymentDetails => 'Платежные данные';

  @override
  String get previewAndScreenshots => 'Предварительный просмотр и скриншоты';

  @override
  String get appCapabilities => 'Возможности приложения';

  @override
  String get aiPrompts => 'Подсказки ИИ';

  @override
  String get chatPrompt => 'Подсказка чата';

  @override
  String get chatPromptPlaceholder =>
      'Вы - отличное приложение, ваша задача - отвечать на запросы пользователей и заставлять их чувствовать себя хорошо...';

  @override
  String get conversationPrompt => 'Запрос разговора';

  @override
  String get conversationPromptPlaceholder =>
      'Вы - отличное приложение, вам будут предоставлены транскрипция и краткое содержание разговора...';

  @override
  String get notificationScopes => 'Области уведомлений';

  @override
  String get appPrivacyAndTerms => 'Конфиденциальность и условия приложения';

  @override
  String get makeMyAppPublic => 'Сделать мое приложение публичным';

  @override
  String get submitAppTermsAgreement =>
      'Отправляя это приложение, я принимаю Условия использования и Политику конфиденциальности Omi AI';

  @override
  String get submitApp => 'Отправить приложение';

  @override
  String get needHelpGettingStarted => 'Нужна помощь для начала работы?';

  @override
  String get clickHereForAppBuildingGuides => 'Нажмите здесь для руководств по созданию приложений и документации';

  @override
  String get submitAppQuestion => 'Отправить приложение?';

  @override
  String get submitAppPublicDescription =>
      'Ваше приложение будет рассмотрено и опубликовано. Вы можете начать использовать его немедленно, даже во время рассмотрения!';

  @override
  String get submitAppPrivateDescription =>
      'Ваше приложение будет рассмотрено и станет доступным для вас в частном порядке. Вы можете начать использовать его немедленно, даже во время рассмотрения!';

  @override
  String get startEarning => 'Начните зарабатывать! 💰';

  @override
  String get connectStripeOrPayPal => 'Подключите Stripe или PayPal, чтобы получать платежи за ваше приложение.';

  @override
  String get connectNow => 'Подключить сейчас';

  @override
  String get installsCount => 'Установки';

  @override
  String get uninstallApp => 'Удалить приложение';

  @override
  String get subscribe => 'Подписаться';

  @override
  String get dataAccessNotice => 'Уведомление о доступе к данным';

  @override
  String get dataAccessWarning =>
      'Это приложение получит доступ к вашим данным. Omi AI не несет ответственности за то, как ваши данные используются, изменяются или удаляются этим приложением';

  @override
  String get installApp => 'Установить приложение';

  @override
  String get betaTesterNotice =>
      'Вы бета-тестер этого приложения. Оно еще не является публичным. Оно станет публичным после одобрения.';

  @override
  String get appUnderReviewOwner =>
      'Ваше приложение находится на рассмотрении и видно только вам. Оно станет публичным после одобрения.';

  @override
  String get appRejectedNotice =>
      'Ваше приложение было отклонено. Пожалуйста, обновите информацию о приложении и отправьте его на рассмотрение снова.';

  @override
  String get setupSteps => 'Шаги настройки';

  @override
  String get setupInstructions => 'Инструкции по настройке';

  @override
  String get integrationInstructions => 'Инструкции по интеграции';

  @override
  String get preview => 'Предварительный просмотр';

  @override
  String get aboutTheApp => 'О приложении';

  @override
  String get aboutThePersona => 'О персоне';

  @override
  String get chatPersonality => 'Личность чата';

  @override
  String get ratingsAndReviews => 'Оценки и отзывы';

  @override
  String get noRatings => 'нет оценок';

  @override
  String ratingsCount(String count) {
    return '$count+ оценок';
  }

  @override
  String get errorActivatingApp => 'Ошибка активации приложения';

  @override
  String get integrationSetupRequired => 'Если это интеграционное приложение, убедитесь, что настройка завершена.';

  @override
  String get installed => 'Установлено';

  @override
  String get appIdLabel => 'ID приложения';

  @override
  String get appNameLabel => 'Название приложения';

  @override
  String get appNamePlaceholder => 'Моё потрясающее приложение';

  @override
  String get pleaseEnterAppName => 'Пожалуйста, введите название приложения';

  @override
  String get categoryLabel => 'Категория';

  @override
  String get selectCategory => 'Выберите категорию';

  @override
  String get descriptionLabel => 'Описание';

  @override
  String get appDescriptionPlaceholder =>
      'Моё потрясающее приложение — это отличное приложение, которое делает удивительные вещи. Это лучшее приложение!';

  @override
  String get pleaseProvideValidDescription => 'Пожалуйста, предоставьте действительное описание';

  @override
  String get appPricingLabel => 'Ценообразование приложения';

  @override
  String get noneSelected => 'Ничего не выбрано';

  @override
  String get appIdCopiedToClipboard => 'ID приложения скопирован в буфер обмена';

  @override
  String get appCategoryModalTitle => 'Категория приложения';

  @override
  String get pricingFree => 'Бесплатно';

  @override
  String get pricingPaid => 'Платно';

  @override
  String get loadingCapabilities => 'Загрузка возможностей...';

  @override
  String get filterInstalled => 'Установлено';

  @override
  String get filterMyApps => 'Мои приложения';

  @override
  String get clearSelection => 'Очистить выбор';

  @override
  String get filterCategory => 'Категория';

  @override
  String get rating4PlusStars => '4+ звезды';

  @override
  String get rating3PlusStars => '3+ звезды';

  @override
  String get rating2PlusStars => '2+ звезды';

  @override
  String get rating1PlusStars => '1+ звезда';

  @override
  String get filterRating => 'Рейтинг';

  @override
  String get filterCapabilities => 'Возможности';

  @override
  String get noNotificationScopesAvailable => 'Нет доступных областей уведомлений';

  @override
  String get popularApps => 'Популярные приложения';

  @override
  String get pleaseProvidePrompt => 'Пожалуйста, укажите запрос';

  @override
  String chatWithAppName(String appName) {
    return 'Чат с $appName';
  }

  @override
  String get defaultAiAssistant => 'AI-ассистент по умолчанию';

  @override
  String get readyToChat => '✨ Готов к чату!';

  @override
  String get connectionNeeded => '🌐 Требуется подключение';

  @override
  String get startConversation => 'Начните разговор и позвольте магии начаться';

  @override
  String get checkInternetConnection => 'Пожалуйста, проверьте подключение к Интернету';

  @override
  String get wasThisHelpful => 'Было ли это полезно?';

  @override
  String get thankYouForFeedback => 'Спасибо за ваш отзыв!';

  @override
  String get maxFilesUploadError => 'Вы можете загрузить только 4 файла за раз';

  @override
  String get attachedFiles => '📎 Прикрепленные файлы';

  @override
  String get takePhoto => 'Сделать фото';

  @override
  String get captureWithCamera => 'Снять камерой';

  @override
  String get selectImages => 'Выбрать изображения';

  @override
  String get chooseFromGallery => 'Выбрать из галереи';

  @override
  String get selectFile => 'Выбрать файл';

  @override
  String get chooseAnyFileType => 'Выбрать любой тип файла';

  @override
  String get cannotReportOwnMessages => 'Вы не можете сообщить о своих собственных сообщениях';

  @override
  String get messageReportedSuccessfully => '✅ Сообщение успешно отправлено';

  @override
  String get confirmReportMessage => 'Вы уверены, что хотите сообщить об этом сообщении?';

  @override
  String get selectChatAssistant => 'Выбрать чат-ассистента';

  @override
  String get enableMoreApps => 'Включить больше приложений';

  @override
  String get chatCleared => 'Чат очищен';

  @override
  String get clearChatTitle => 'Очистить чат?';

  @override
  String get confirmClearChat => 'Вы уверены, что хотите очистить чат? Это действие нельзя отменить.';

  @override
  String get copy => 'Копировать';

  @override
  String get share => 'Поделиться';

  @override
  String get report => 'Сообщить';

  @override
  String get microphonePermissionRequired => 'Для записи голоса требуется разрешение микрофона.';

  @override
  String get microphonePermissionDenied =>
      'Доступ к микрофону запрещен. Пожалуйста, предоставьте разрешение в Системные настройки > Конфиденциальность и безопасность > Микрофон.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Не удалось проверить разрешение микрофона: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Не удалось расшифровать аудио';

  @override
  String get transcribing => 'Расшифровка...';

  @override
  String get transcriptionFailed => 'Расшифровка не удалась';

  @override
  String get discardedConversation => 'Отклонённый разговор';

  @override
  String get at => 'в';

  @override
  String get from => 'с';

  @override
  String get copied => 'Скопировано!';

  @override
  String get copyLink => 'Копировать ссылку';

  @override
  String get hideTranscript => 'Скрыть расшифровку';

  @override
  String get viewTranscript => 'Показать расшифровку';

  @override
  String get conversationDetails => 'Детали разговора';

  @override
  String get transcript => 'Расшифровка';

  @override
  String segmentsCount(int count) {
    return '$count сегментов';
  }

  @override
  String get noTranscriptAvailable => 'Расшифровка недоступна';

  @override
  String get noTranscriptMessage => 'У этого разговора нет расшифровки.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL-адрес разговора не может быть создан.';

  @override
  String get failedToGenerateConversationLink => 'Не удалось создать ссылку на разговор';

  @override
  String get failedToGenerateShareLink => 'Не удалось создать ссылку для совместного использования';

  @override
  String get reloadingConversations => 'Перезагрузка бесед...';

  @override
  String get user => 'Пользователь';

  @override
  String get starred => 'Избранное';

  @override
  String get date => 'Дата';

  @override
  String get noResultsFound => 'Результаты не найдены';

  @override
  String get tryAdjustingSearchTerms => 'Попробуйте изменить условия поиска';

  @override
  String get starConversationsToFindQuickly => 'Отметьте беседы звездой, чтобы быстро находить их здесь';

  @override
  String noConversationsOnDate(String date) {
    return 'Нет бесед $date';
  }

  @override
  String get trySelectingDifferentDate => 'Попробуйте выбрать другую дату';

  @override
  String get conversations => 'Беседы';

  @override
  String get chat => 'Чат';

  @override
  String get actions => 'Действия';

  @override
  String get syncAvailable => 'Синхронизация доступна';

  @override
  String get referAFriend => 'Порекомендовать друга';

  @override
  String get help => 'Помощь';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Обновить до Pro';

  @override
  String get getOmiDevice => 'Получить устройство Omi';

  @override
  String get wearableAiCompanion => 'Носимый AI-компаньон';

  @override
  String get loadingMemories => 'Загрузка воспоминаний...';

  @override
  String get allMemories => 'Все воспоминания';

  @override
  String get aboutYou => 'О вас';

  @override
  String get manual => 'Ручные';

  @override
  String get loadingYourMemories => 'Загрузка ваших воспоминаний...';

  @override
  String get createYourFirstMemory => 'Создайте первое воспоминание, чтобы начать';

  @override
  String get tryAdjustingFilter => 'Попробуйте изменить параметры поиска или фильтр';

  @override
  String get whatWouldYouLikeToRemember => 'Что вы хотите запомнить?';

  @override
  String get category => 'Категория';

  @override
  String get public => 'Публичная';

  @override
  String get failedToSaveCheckConnection => 'Не удалось сохранить. Проверьте подключение.';

  @override
  String get createMemory => 'Создать память';

  @override
  String get deleteMemoryConfirmation => 'Вы уверены, что хотите удалить эту память? Это действие нельзя отменить.';

  @override
  String get makePrivate => 'Сделать приватной';

  @override
  String get organizeAndControlMemories => 'Организуйте и управляйте своими воспоминаниями';

  @override
  String get total => 'Всего';

  @override
  String get makeAllMemoriesPrivate => 'Сделать все воспоминания приватными';

  @override
  String get setAllMemoriesToPrivate => 'Установить все воспоминания как приватные';

  @override
  String get makeAllMemoriesPublic => 'Сделать все воспоминания публичными';

  @override
  String get setAllMemoriesToPublic => 'Установить все воспоминания как публичные';

  @override
  String get permanentlyRemoveAllMemories => 'Навсегда удалить все воспоминания из Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Все воспоминания теперь приватные';

  @override
  String get allMemoriesAreNowPublic => 'Все воспоминания теперь публичные';

  @override
  String get clearOmisMemory => 'Очистить память Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Вы уверены, что хотите очистить память Omi? Это действие нельзя отменить, и оно навсегда удалит все $count воспоминаний.';
  }

  @override
  String get omisMemoryCleared => 'Память Omi о вас была очищена';

  @override
  String get welcomeToOmi => 'Добро пожаловать в Omi';

  @override
  String get continueWithApple => 'Продолжить с Apple';

  @override
  String get continueWithGoogle => 'Продолжить с Google';

  @override
  String get byContinuingYouAgree => 'Продолжая, вы соглашаетесь с нашими ';

  @override
  String get termsOfService => 'Условиями обслуживания';

  @override
  String get and => ' и ';

  @override
  String get dataAndPrivacy => 'Данные и конфиденциальность';

  @override
  String get secureAuthViaAppleId => 'Безопасная аутентификация через Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Безопасная аутентификация через аккаунт Google';

  @override
  String get whatWeCollect => 'Что мы собираем';

  @override
  String get dataCollectionMessage =>
      'Продолжая, ваши разговоры, записи и личная информация будут надежно храниться на наших серверах для предоставления аналитики на основе ИИ и включения всех функций приложения.';

  @override
  String get dataProtection => 'Защита данных';

  @override
  String get yourDataIsProtected => 'Ваши данные защищены и регулируются нашей ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Пожалуйста, выберите ваш основной язык';

  @override
  String get chooseYourLanguage => 'Выберите ваш язык';

  @override
  String get selectPreferredLanguageForBestExperience => 'Выберите предпочитаемый язык для наилучшего опыта Omi';

  @override
  String get searchLanguages => 'Поиск языков...';

  @override
  String get selectALanguage => 'Выберите язык';

  @override
  String get tryDifferentSearchTerm => 'Попробуйте другой поисковый запрос';

  @override
  String get pleaseEnterYourName => 'Пожалуйста, введите ваше имя';

  @override
  String get nameMustBeAtLeast2Characters => 'Имя должно содержать не менее 2 символов';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Скажите нам, как вы хотели бы, чтобы к вам обращались. Это помогает персонализировать ваш опыт Omi.';

  @override
  String charactersCount(int count) {
    return '$count символов';
  }

  @override
  String get enableFeaturesForBestExperience => 'Включите функции для наилучшего опыта Omi на вашем устройстве.';

  @override
  String get microphoneAccess => 'Доступ к микрофону';

  @override
  String get recordAudioConversations => 'Записывать аудиоразговоры';

  @override
  String get microphoneAccessDescription =>
      'Omi нужен доступ к микрофону для записи ваших разговоров и предоставления транскрипций.';

  @override
  String get screenRecording => 'Запись экрана';

  @override
  String get captureSystemAudioFromMeetings => 'Захват системного звука со встреч';

  @override
  String get screenRecordingDescription =>
      'Omi нужно разрешение на запись экрана для захвата системного звука с ваших встреч на базе браузера.';

  @override
  String get accessibility => 'Доступность';

  @override
  String get detectBrowserBasedMeetings => 'Обнаружение встреч на базе браузера';

  @override
  String get accessibilityDescription =>
      'Omi нужно разрешение доступности для обнаружения, когда вы присоединяетесь к встречам Zoom, Meet или Teams в вашем браузере.';

  @override
  String get pleaseWait => 'Пожалуйста, подождите...';

  @override
  String get joinTheCommunity => 'Присоединяйтесь к сообществу!';

  @override
  String get loadingProfile => 'Загрузка профиля...';

  @override
  String get profileSettings => 'Настройки профиля';

  @override
  String get noEmailSet => 'Электронная почта не установлена';

  @override
  String get userIdCopiedToClipboard => 'ID пользователя скопирован';

  @override
  String get yourInformation => 'Ваша Информация';

  @override
  String get setYourName => 'Установить ваше имя';

  @override
  String get changeYourName => 'Изменить ваше имя';

  @override
  String get manageYourOmiPersona => 'Управление вашей персоной Omi';

  @override
  String get voiceAndPeople => 'Голос и Люди';

  @override
  String get teachOmiYourVoice => 'Научите Omi вашему голосу';

  @override
  String get tellOmiWhoSaidIt => 'Скажите Omi, кто это сказал 🗣️';

  @override
  String get payment => 'Оплата';

  @override
  String get addOrChangeYourPaymentMethod => 'Добавить или изменить способ оплаты';

  @override
  String get preferences => 'Предпочтения';

  @override
  String get helpImproveOmiBySharing => 'Помогите улучшить Omi, делясь анонимными аналитическими данными';

  @override
  String get deleteAccount => 'Удалить Аккаунт';

  @override
  String get deleteYourAccountAndAllData => 'Удалить аккаунт и все данные';

  @override
  String get clearLogs => 'Очистить журналы';

  @override
  String get debugLogsCleared => 'Журналы отладки очищены';

  @override
  String get exportConversations => 'Экспорт бесед';

  @override
  String get exportAllConversationsToJson => 'Экспортируйте все свои беседы в файл JSON.';

  @override
  String get conversationsExportStarted =>
      'Экспорт бесед начат. Это может занять несколько секунд, пожалуйста, подождите.';

  @override
  String get mcpDescription =>
      'Для подключения Omi к другим приложениям для чтения, поиска и управления вашими воспоминаниями и беседами. Создайте ключ для начала.';

  @override
  String get apiKeys => 'Ключи API';

  @override
  String errorLabel(String error) {
    return 'Ошибка: $error';
  }

  @override
  String get noApiKeysFound => 'Ключи API не найдены. Создайте один для начала.';

  @override
  String get advancedSettings => 'Расширенные настройки';

  @override
  String get triggersWhenNewConversationCreated => 'Срабатывает при создании новой беседы.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Срабатывает при получении нового транскрипта.';

  @override
  String get realtimeAudioBytes => 'Байты аудио в реальном времени';

  @override
  String get triggersWhenAudioBytesReceived => 'Срабатывает при получении байтов аудио.';

  @override
  String get everyXSeconds => 'Каждые x секунд';

  @override
  String get triggersWhenDaySummaryGenerated => 'Срабатывает при генерации сводки дня.';

  @override
  String get tryLatestExperimentalFeatures => 'Попробуйте новейшие экспериментальные функции от команды Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Диагностический статус службы транскрипции';

  @override
  String get enableDetailedDiagnosticMessages => 'Включить подробные диагностические сообщения от службы транскрипции';

  @override
  String get autoCreateAndTagNewSpeakers => 'Автоматически создавать и помечать новых говорящих';

  @override
  String get automaticallyCreateNewPerson =>
      'Автоматически создавать нового человека, когда имя обнаружено в транскрипте.';

  @override
  String get pilotFeatures => 'Пилотные функции';

  @override
  String get pilotFeaturesDescription => 'Эти функции являются тестами, и поддержка не гарантируется.';

  @override
  String get suggestFollowUpQuestion => 'Предложить дополнительный вопрос';

  @override
  String get saveSettings => 'Сохранить Настройки';

  @override
  String get syncingDeveloperSettings => 'Синхронизация настроек разработчика...';

  @override
  String get summary => 'Резюме';

  @override
  String get auto => 'Автоматически';

  @override
  String get noSummaryForApp => 'Для этого приложения нет сводки. Попробуйте другое приложение для лучших результатов.';

  @override
  String get tryAnotherApp => 'Попробовать другое приложение';

  @override
  String generatedBy(String appName) {
    return 'Создано $appName';
  }

  @override
  String get overview => 'Обзор';

  @override
  String get otherAppResults => 'Результаты других приложений';

  @override
  String get unknownApp => 'Неизвестное приложение';

  @override
  String get noSummaryAvailable => 'Резюме недоступно';

  @override
  String get conversationNoSummaryYet => 'У этого разговора пока нет резюме.';

  @override
  String get chooseSummarizationApp => 'Выберите приложение для резюме';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName установлено как приложение для резюме по умолчанию';
  }

  @override
  String get letOmiChooseAutomatically => 'Позвольте Omi автоматически выбрать лучшее приложение';

  @override
  String get deleteConversationConfirmation =>
      'Вы уверены, что хотите удалить этот разговор? Это действие нельзя отменить.';

  @override
  String get conversationDeleted => 'Разговор удален';

  @override
  String get generatingLink => 'Генерация ссылки...';

  @override
  String get editConversation => 'Редактировать разговор';

  @override
  String get conversationLinkCopiedToClipboard => 'Ссылка на разговор скопирована в буфер обмена';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Расшифровка разговора скопирована в буфер обмена';

  @override
  String get editConversationDialogTitle => 'Редактировать разговор';

  @override
  String get changeTheConversationTitle => 'Изменить название разговора';

  @override
  String get conversationTitle => 'Название разговора';

  @override
  String get enterConversationTitle => 'Введите название разговора...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Название разговора успешно обновлено';

  @override
  String get failedToUpdateConversationTitle => 'Не удалось обновить название разговора';

  @override
  String get errorUpdatingConversationTitle => 'Ошибка при обновлении названия разговора';

  @override
  String get settingUp => 'Настройка...';

  @override
  String get startYourFirstRecording => 'Начните свою первую запись';

  @override
  String get preparingSystemAudioCapture => 'Подготовка записи системного аудио';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Нажмите кнопку, чтобы записать аудио для живых транскриптов, AI-инсайтов и автоматического сохранения.';

  @override
  String get reconnecting => 'Переподключение...';

  @override
  String get recordingPaused => 'Запись приостановлена';

  @override
  String get recordingActive => 'Запись активна';

  @override
  String get startRecording => 'Начать запись';

  @override
  String resumingInCountdown(String countdown) {
    return 'Возобновление через $countdownс...';
  }

  @override
  String get tapPlayToResume => 'Нажмите воспроизведение, чтобы продолжить';

  @override
  String get listeningForAudio => 'Прослушивание аудио...';

  @override
  String get preparingAudioCapture => 'Подготовка записи аудио';

  @override
  String get clickToBeginRecording => 'Нажмите, чтобы начать запись';

  @override
  String get translated => 'переведено';

  @override
  String get liveTranscript => 'Живой транскрипт';

  @override
  String segmentsSingular(String count) {
    return '$count сегмент';
  }

  @override
  String segmentsPlural(String count) {
    return '$count сегментов';
  }

  @override
  String get startRecordingToSeeTranscript => 'Начните запись, чтобы увидеть живой транскрипт';

  @override
  String get paused => 'Приостановлено';

  @override
  String get initializing => 'Инициализация...';

  @override
  String get recording => 'Запись';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Микрофон изменен. Возобновление через $countdownс';
  }

  @override
  String get clickPlayToResumeOrStop => 'Нажмите воспроизведение для продолжения или остановку для завершения';

  @override
  String get settingUpSystemAudioCapture => 'Настройка записи системного аудио';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Запись аудио и создание транскрипта';

  @override
  String get clickToBeginRecordingSystemAudio => 'Нажмите, чтобы начать запись системного аудио';

  @override
  String get you => 'Вы';

  @override
  String speakerWithId(String speakerId) {
    return 'Докладчик $speakerId';
  }

  @override
  String get translatedByOmi => 'переведено omi';

  @override
  String get backToConversations => 'Вернуться к разговорам';

  @override
  String get systemAudio => 'Система';

  @override
  String get mic => 'Микрофон';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Аудиовход установлен на $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Ошибка переключения аудиоустройства: $error';
  }

  @override
  String get selectAudioInput => 'Выберите аудиовход';

  @override
  String get loadingDevices => 'Загрузка устройств...';

  @override
  String get settingsHeader => 'НАСТРОЙКИ';

  @override
  String get plansAndBilling => 'Планы и Оплата';

  @override
  String get calendarIntegration => 'Интеграция Календаря';

  @override
  String get dailySummary => 'Ежедневная сводка';

  @override
  String get developer => 'Разработчик';

  @override
  String get about => 'О программе';

  @override
  String get selectTime => 'Выбрать время';

  @override
  String get accountGroup => 'Аккаунт';

  @override
  String get signOutQuestion => 'Выйти?';

  @override
  String get signOutConfirmation => 'Вы уверены, что хотите выйти?';

  @override
  String get customVocabularyHeader => 'ПОЛЬЗОВАТЕЛЬСКИЙ СЛОВАРЬ';

  @override
  String get addWordsDescription => 'Добавьте слова, которые Omi должен распознавать во время транскрипции.';

  @override
  String get enterWordsHint => 'Введите слова (через запятую)';

  @override
  String get dailySummaryHeader => 'ЕЖЕДНЕВНАЯ СВОДКА';

  @override
  String get dailySummaryTitle => 'Ежедневная Сводка';

  @override
  String get dailySummaryDescription => 'Получайте персонализированную сводку разговоров за день в виде уведомления.';

  @override
  String get deliveryTime => 'Время доставки';

  @override
  String get deliveryTimeDescription => 'Когда получать ежедневную сводку';

  @override
  String get subscription => 'Подписка';

  @override
  String get viewPlansAndUsage => 'Просмотр Планов и Использования';

  @override
  String get viewPlansDescription => 'Управляйте подпиской и просматривайте статистику использования';

  @override
  String get addOrChangePaymentMethod => 'Добавить или изменить способ оплаты';

  @override
  String get displayOptions => 'Параметры отображения';

  @override
  String get showMeetingsInMenuBar => 'Показывать встречи в строке меню';

  @override
  String get displayUpcomingMeetingsDescription => 'Отображать предстоящие встречи в строке меню';

  @override
  String get showEventsWithoutParticipants => 'Показывать события без участников';

  @override
  String get includePersonalEventsDescription => 'Включать личные события без участников';

  @override
  String get upcomingMeetings => 'Предстоящие встречи';

  @override
  String get checkingNext7Days => 'Проверка следующих 7 дней';

  @override
  String get shortcuts => 'Комбинации клавиш';

  @override
  String get shortcutChangeInstruction => 'Нажмите на комбинацию клавиш, чтобы изменить ее. Нажмите Escape для отмены.';

  @override
  String get configurePersonaDescription => 'Настройте свою персону ИИ';

  @override
  String get configureSTTProvider => 'Настроить провайдера STT';

  @override
  String get setConversationEndDescription => 'Установите, когда разговоры автоматически завершаются';

  @override
  String get importDataDescription => 'Импортировать данные из других источников';

  @override
  String get exportConversationsDescription => 'Экспортировать разговоры в JSON';

  @override
  String get exportingConversations => 'Экспорт разговоров...';

  @override
  String get clearNodesDescription => 'Очистить все узлы и связи';

  @override
  String get deleteKnowledgeGraphQuestion => 'Удалить граф знаний?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Это удалит все производные данные графа знаний. Ваши исходные воспоминания останутся в безопасности.';

  @override
  String get connectOmiWithAI => 'Подключите Omi к ИИ-ассистентам';

  @override
  String get noAPIKeys => 'Нет ключей API. Создайте один, чтобы начать.';

  @override
  String get autoCreateWhenDetected => 'Автосоздание при обнаружении имени';

  @override
  String get trackPersonalGoals => 'Отслеживать личные цели на главной странице';

  @override
  String get dailyReflectionDescription =>
      'Получайте напоминание в 21:00 для размышления о прошедшем дне и записи мыслей.';

  @override
  String get endpointURL => 'URL конечной точки';

  @override
  String get links => 'Ссылки';

  @override
  String get discordMemberCount => 'Более 8000 участников в Discord';

  @override
  String get userInformation => 'Информация о пользователе';

  @override
  String get capabilities => 'Возможности';

  @override
  String get previewScreenshots => 'Предпросмотр скриншотов';

  @override
  String get holdOnPreparingForm => 'Подождите, мы готовим форму для вас';

  @override
  String get bySubmittingYouAgreeToOmi => 'Отправляя, вы соглашаетесь с ';

  @override
  String get termsAndPrivacyPolicy => 'Условия и Политика конфиденциальности';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Помогает диагностировать проблемы. Автоматически удаляется через 3 дня.';

  @override
  String get manageYourApp => 'Управление приложением';

  @override
  String get updatingYourApp => 'Обновление приложения';

  @override
  String get fetchingYourAppDetails => 'Получение данных приложения';

  @override
  String get updateAppQuestion => 'Обновить приложение?';

  @override
  String get updateAppConfirmation =>
      'Вы уверены, что хотите обновить приложение? Изменения вступят в силу после проверки нашей командой.';

  @override
  String get updateApp => 'Обновить приложение';

  @override
  String get createAndSubmitNewApp => 'Создать и отправить новое приложение';

  @override
  String appsCount(String count) {
    return 'Приложения ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Приватные приложения ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Публичные приложения ($count)';
  }

  @override
  String get newVersionAvailable => 'Доступна новая версия  🎉';

  @override
  String get no => 'Нет';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Подписка успешно отменена. Она останется активной до конца текущего расчетного периода.';

  @override
  String get failedToCancelSubscription => 'Не удалось отменить подписку. Пожалуйста, попробуйте снова.';

  @override
  String get invalidPaymentUrl => 'Неверный URL оплаты';

  @override
  String get permissionsAndTriggers => 'Разрешения и триггеры';

  @override
  String get chatFeatures => 'Функции чата';

  @override
  String get uninstall => 'Удалить';

  @override
  String get installs => 'УСТАНОВКИ';

  @override
  String get priceLabel => 'ЦЕНА';

  @override
  String get updatedLabel => 'ОБНОВЛЕНО';

  @override
  String get createdLabel => 'СОЗДАНО';

  @override
  String get featuredLabel => 'РЕКОМЕНДУЕМОЕ';

  @override
  String get cancelSubscriptionQuestion => 'Отменить подписку?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Вы уверены, что хотите отменить подписку? У вас будет доступ до конца текущего расчетного периода.';

  @override
  String get cancelSubscriptionButton => 'Отменить подписку';

  @override
  String get cancelling => 'Отмена...';

  @override
  String get betaTesterMessage =>
      'Вы бета-тестер этого приложения. Оно еще не опубликовано. Станет публичным после одобрения.';

  @override
  String get appUnderReviewMessage =>
      'Ваше приложение на рассмотрении и видно только вам. Станет публичным после одобрения.';

  @override
  String get appRejectedMessage => 'Ваше приложение отклонено. Обновите данные и отправьте повторно на рассмотрение.';

  @override
  String get invalidIntegrationUrl => 'Недействительный URL интеграции';

  @override
  String get tapToComplete => 'Нажмите для завершения';

  @override
  String get invalidSetupInstructionsUrl => 'Недействительный URL инструкций по настройке';

  @override
  String get pushToTalk => 'Нажми и говори';

  @override
  String get summaryPrompt => 'Промпт для резюме';

  @override
  String get pleaseSelectARating => 'Пожалуйста, выберите оценку';

  @override
  String get reviewAddedSuccessfully => 'Отзыв успешно добавлен 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Отзыв успешно обновлён 🚀';

  @override
  String get failedToSubmitReview => 'Не удалось отправить отзыв. Пожалуйста, попробуйте снова.';

  @override
  String get addYourReview => 'Добавить отзыв';

  @override
  String get editYourReview => 'Редактировать отзыв';

  @override
  String get writeAReviewOptional => 'Написать отзыв (необязательно)';

  @override
  String get submitReview => 'Отправить отзыв';

  @override
  String get updateReview => 'Обновить отзыв';

  @override
  String get yourReview => 'Ваш отзыв';

  @override
  String get anonymousUser => 'Анонимный пользователь';

  @override
  String get issueActivatingApp => 'При активации этого приложения возникла проблема. Пожалуйста, попробуйте снова.';

  @override
  String get dataAccessNoticeDescription =>
      'Это приложение получит доступ к вашим данным. Omi AI не несет ответственности за то, как ваши данные используются, изменяются или удаляются этим приложением';

  @override
  String get copyUrl => 'Копировать URL';

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
  String get weekdayThu => 'Чт';

  @override
  String get weekdayFri => 'Пт';

  @override
  String get weekdaySat => 'Сб';

  @override
  String get weekdaySun => 'Вс';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Интеграция с $serviceName скоро';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Уже экспортировано в $platform';
  }

  @override
  String get anotherPlatform => 'другую платформу';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Пожалуйста, авторизуйтесь в $serviceName в Настройки > Интеграции задач';
  }

  @override
  String addingToService(String serviceName) {
    return 'Добавление в $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Добавлено в $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Не удалось добавить в $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Разрешение для Apple Reminders отклонено';

  @override
  String failedToCreateApiKey(String error) {
    return 'Не удалось создать API-ключ провайдера: $error';
  }

  @override
  String get createAKey => 'Создать ключ';

  @override
  String get apiKeyRevokedSuccessfully => 'API-ключ успешно отозван';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Не удалось отозвать API-ключ: $error';
  }

  @override
  String get omiApiKeys => 'API-ключи Omi';

  @override
  String get apiKeysDescription =>
      'API-ключи используются для аутентификации, когда ваше приложение взаимодействует с сервером OMI. Они позволяют вашему приложению создавать воспоминания и безопасно получать доступ к другим сервисам OMI.';

  @override
  String get aboutOmiApiKeys => 'Об API-ключах Omi';

  @override
  String get yourNewKey => 'Ваш новый ключ:';

  @override
  String get copyToClipboard => 'Копировать в буфер обмена';

  @override
  String get pleaseCopyKeyNow => 'Пожалуйста, скопируйте его сейчас и запишите в надёжном месте. ';

  @override
  String get willNotSeeAgain => 'Вы не сможете увидеть его снова.';

  @override
  String get revokeKey => 'Отозвать ключ';

  @override
  String get revokeApiKeyQuestion => 'Отозвать API-ключ?';

  @override
  String get revokeApiKeyWarning =>
      'Это действие нельзя отменить. Приложения, использующие этот ключ, больше не смогут получить доступ к API.';

  @override
  String get revoke => 'Отозвать';

  @override
  String get whatWouldYouLikeToCreate => 'Что вы хотите создать?';

  @override
  String get createAnApp => 'Создать приложение';

  @override
  String get createAndShareYourApp => 'Создайте и поделитесь своим приложением';

  @override
  String get createMyClone => 'Создать мой клон';

  @override
  String get createYourDigitalClone => 'Создайте свой цифровой клон';

  @override
  String get itemApp => 'Приложение';

  @override
  String get itemPersona => 'Персона';

  @override
  String keepItemPublic(String item) {
    return 'Оставить $item публичным';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Сделать $item публичным?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Сделать $item приватным?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Если вы сделаете $item публичным, им смогут пользоваться все';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Если вы сейчас сделаете $item приватным, он перестанет работать для всех и будет виден только вам';
  }

  @override
  String get manageApp => 'Управление приложением';

  @override
  String get updatePersonaDetails => 'Обновить данные персоны';

  @override
  String deleteItemTitle(String item) {
    return 'Удалить $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Удалить $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Вы уверены, что хотите удалить этот $item? Это действие нельзя отменить.';
  }

  @override
  String get revokeKeyQuestion => 'Отозвать ключ?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Вы уверены, что хотите отозвать ключ \"$keyName\"? Это действие нельзя отменить.';
  }

  @override
  String get createNewKey => 'Создать новый ключ';

  @override
  String get keyNameHint => 'напр., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Пожалуйста, введите название.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Не удалось создать ключ: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Не удалось создать ключ. Пожалуйста, попробуйте снова.';

  @override
  String get keyCreated => 'Ключ создан';

  @override
  String get keyCreatedMessage =>
      'Ваш новый ключ создан. Пожалуйста, скопируйте его сейчас. Вы больше не сможете его увидеть.';

  @override
  String get keyWord => 'Ключ';

  @override
  String get externalAppAccess => 'Доступ внешних приложений';

  @override
  String get externalAppAccessDescription =>
      'Следующие установленные приложения имеют внешние интеграции и могут получить доступ к вашим данным, таким как разговоры и воспоминания.';

  @override
  String get noExternalAppsHaveAccess => 'Ни одно внешнее приложение не имеет доступа к вашим данным.';

  @override
  String get maximumSecurityE2ee => 'Максимальная безопасность (E2EE)';

  @override
  String get e2eeDescription =>
      'Сквозное шифрование — это золотой стандарт конфиденциальности. При включении ваши данные шифруются на вашем устройстве перед отправкой на наши серверы. Это означает, что никто, даже Omi, не может получить доступ к вашему контенту.';

  @override
  String get importantTradeoffs => 'Важные компромиссы:';

  @override
  String get e2eeTradeoff1 =>
      '• Некоторые функции, такие как интеграции с внешними приложениями, могут быть отключены.';

  @override
  String get e2eeTradeoff2 => '• Если вы потеряете пароль, ваши данные не могут быть восстановлены.';

  @override
  String get featureComingSoon => 'Эта функция скоро появится!';

  @override
  String get migrationInProgressMessage =>
      'Миграция выполняется. Вы не можете изменить уровень защиты, пока она не завершится.';

  @override
  String get migrationFailed => 'Миграция не удалась';

  @override
  String migratingFromTo(String source, String target) {
    return 'Миграция с $source на $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total объектов';
  }

  @override
  String get secureEncryption => 'Безопасное шифрование';

  @override
  String get secureEncryptionDescription =>
      'Ваши данные шифруются уникальным для вас ключом на наших серверах, размещенных в Google Cloud. Это означает, что ваш необработанный контент недоступен никому, включая сотрудников Omi или Google, напрямую из базы данных.';

  @override
  String get endToEndEncryption => 'Сквозное шифрование';

  @override
  String get e2eeCardDescription =>
      'Включите для максимальной безопасности, где только вы можете получить доступ к своим данным. Нажмите, чтобы узнать больше.';

  @override
  String get dataAlwaysEncrypted =>
      'Независимо от уровня, ваши данные всегда зашифрованы в состоянии покоя и при передаче.';

  @override
  String get readOnlyScope => 'Только чтение';

  @override
  String get fullAccessScope => 'Полный доступ';

  @override
  String get readScope => 'Чтение';

  @override
  String get writeScope => 'Запись';

  @override
  String get apiKeyCreated => 'API ключ создан!';

  @override
  String get saveKeyWarning => 'Сохраните этот ключ сейчас! Вы больше не сможете его увидеть.';

  @override
  String get yourApiKey => 'ВАШ API КЛЮЧ';

  @override
  String get tapToCopy => 'Нажмите, чтобы скопировать';

  @override
  String get copyKey => 'Копировать ключ';

  @override
  String get createApiKey => 'Создать API ключ';

  @override
  String get accessDataProgrammatically => 'Программный доступ к вашим данным';

  @override
  String get keyNameLabel => 'НАЗВАНИЕ КЛЮЧА';

  @override
  String get keyNamePlaceholder => 'напр., Моя интеграция';

  @override
  String get permissionsLabel => 'РАЗРЕШЕНИЯ';

  @override
  String get permissionsInfoNote => 'R = Чтение, W = Запись. По умолчанию только чтение, если ничего не выбрано.';

  @override
  String get developerApi => 'API разработчика';

  @override
  String get createAKeyToGetStarted => 'Создайте ключ для начала';

  @override
  String errorWithMessage(String error) {
    return 'Ошибка: $error';
  }

  @override
  String get omiTraining => 'Обучение Omi';

  @override
  String get trainingDataProgram => 'Программа данных для обучения';

  @override
  String get getOmiUnlimitedFree =>
      'Получите Omi Unlimited бесплатно, предоставив свои данные для обучения моделей ИИ.';

  @override
  String get trainingDataBullets =>
      '• Ваши данные помогают улучшать модели ИИ\n• Передаются только нечувствительные данные\n• Полностью прозрачный процесс';

  @override
  String get learnMoreAtOmiTraining => 'Узнайте больше на omi.me/training';

  @override
  String get agreeToContributeData => 'Я понимаю и соглашаюсь предоставить свои данные для обучения ИИ';

  @override
  String get submitRequest => 'Отправить запрос';

  @override
  String get thankYouRequestUnderReview => 'Спасибо! Ваш запрос рассматривается. Мы уведомим вас после одобрения.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Ваш план останется активным до $date. После этого вы потеряете доступ к безлимитным функциям. Вы уверены?';
  }

  @override
  String get confirmCancellation => 'Подтвердить отмену';

  @override
  String get keepMyPlan => 'Сохранить мой план';

  @override
  String get subscriptionSetToCancel => 'Ваша подписка будет отменена в конце периода.';

  @override
  String get switchedToOnDevice => 'Переключено на транскрипцию на устройстве';

  @override
  String get couldNotSwitchToFreePlan => 'Не удалось переключиться на бесплатный план. Пожалуйста, попробуйте снова.';

  @override
  String get couldNotLoadPlans => 'Не удалось загрузить доступные планы. Пожалуйста, попробуйте снова.';

  @override
  String get selectedPlanNotAvailable => 'Выбранный план недоступен. Пожалуйста, попробуйте снова.';

  @override
  String get upgradeToAnnualPlan => 'Перейти на годовой план';

  @override
  String get importantBillingInfo => 'Важная информация о выставлении счетов:';

  @override
  String get monthlyPlanContinues => 'Ваш текущий месячный план будет действовать до конца расчетного периода';

  @override
  String get paymentMethodCharged =>
      'С вашего существующего способа оплаты будет автоматически списана сумма по окончании месячного плана';

  @override
  String get annualSubscriptionStarts => 'Ваша 12-месячная годовая подписка начнется автоматически после списания';

  @override
  String get thirteenMonthsCoverage => 'Вы получите 13 месяцев покрытия (текущий месяц + 12 месяцев годовой подписки)';

  @override
  String get confirmUpgrade => 'Подтвердить обновление';

  @override
  String get confirmPlanChange => 'Подтвердить изменение плана';

  @override
  String get confirmAndProceed => 'Подтвердить и продолжить';

  @override
  String get upgradeScheduled => 'Обновление запланировано';

  @override
  String get changePlan => 'Изменить план';

  @override
  String get upgradeAlreadyScheduled => 'Ваше обновление до годового плана уже запланировано';

  @override
  String get youAreOnUnlimitedPlan => 'Вы на плане Безлимитный.';

  @override
  String get yourOmiUnleashed => 'Ваш Omi, раскрытый. Перейдите на безлимит для бесконечных возможностей.';

  @override
  String planEndedOn(String date) {
    return 'Ваш план закончился $date.\\nПодпишитесь снова - с вас сразу спишется оплата за новый расчетный период.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Ваш план будет отменен $date.\\nПодпишитесь снова, чтобы сохранить преимущества - без оплаты до $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Ваш годовой план начнется автоматически по окончании месячного плана.';

  @override
  String planRenewsOn(String date) {
    return 'Ваш план продлевается $date.';
  }

  @override
  String get unlimitedConversations => 'Неограниченные разговоры';

  @override
  String get askOmiAnything => 'Спросите Omi о чём угодно о своей жизни';

  @override
  String get unlockOmiInfiniteMemory => 'Разблокируйте бесконечную память Omi';

  @override
  String get youreOnAnnualPlan => 'Вы на годовом плане';

  @override
  String get alreadyBestValuePlan => 'У вас уже самый выгодный план. Изменения не требуются.';

  @override
  String get unableToLoadPlans => 'Не удается загрузить планы';

  @override
  String get checkConnectionTryAgain => 'Проверьте подключение и попробуйте снова';

  @override
  String get useFreePlan => 'Использовать бесплатный план';

  @override
  String get continueText => 'Продолжить';

  @override
  String get resubscribe => 'Подписаться снова';

  @override
  String get couldNotOpenPaymentSettings => 'Не удалось открыть настройки оплаты. Пожалуйста, попробуйте снова.';

  @override
  String get managePaymentMethod => 'Управление способом оплаты';

  @override
  String get cancelSubscription => 'Отменить подписку';

  @override
  String endsOnDate(String date) {
    return 'Заканчивается $date';
  }

  @override
  String get active => 'Активен';

  @override
  String get freePlan => 'Бесплатный план';

  @override
  String get configure => 'Настроить';

  @override
  String get privacyInformation => 'Информация о конфиденциальности';

  @override
  String get yourPrivacyMattersToUs => 'Ваша конфиденциальность важна для нас';

  @override
  String get privacyIntroText =>
      'В Omi мы очень серьезно относимся к вашей конфиденциальности. Мы хотим быть прозрачными в отношении собираемых данных и их использования. Вот что вам нужно знать:';

  @override
  String get whatWeTrack => 'Что мы отслеживаем';

  @override
  String get anonymityAndPrivacy => 'Анонимность и конфиденциальность';

  @override
  String get optInAndOptOutOptions => 'Опции согласия и отказа';

  @override
  String get ourCommitment => 'Наше обязательство';

  @override
  String get commitmentText =>
      'Мы обязуемся использовать собранные данные только для улучшения Omi для вас. Ваша конфиденциальность и доверие имеют для нас первостепенное значение.';

  @override
  String get thankYouText =>
      'Спасибо, что вы ценный пользователь Omi. Если у вас есть вопросы или проблемы, свяжитесь с нами по адресу team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Настройки синхронизации WiFi';

  @override
  String get enterHotspotCredentials => 'Введите данные точки доступа телефона';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi синхронизация использует телефон как точку доступа. Найдите имя и пароль в Настройки > Режим модема.';

  @override
  String get hotspotNameSsid => 'Имя точки доступа (SSID)';

  @override
  String get exampleIphoneHotspot => 'напр. iPhone Hotspot';

  @override
  String get password => 'Пароль';

  @override
  String get enterHotspotPassword => 'Введите пароль точки доступа';

  @override
  String get saveCredentials => 'Сохранить данные';

  @override
  String get clearCredentials => 'Очистить данные';

  @override
  String get pleaseEnterHotspotName => 'Пожалуйста, введите имя точки доступа';

  @override
  String get wifiCredentialsSaved => 'Данные WiFi сохранены';

  @override
  String get wifiCredentialsCleared => 'Данные WiFi очищены';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Сводка создана для $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Не удалось создать сводку. Убедитесь, что у вас есть разговоры за этот день.';

  @override
  String get summaryNotFound => 'Сводка не найдена';

  @override
  String get yourDaysJourney => 'Ваш путь за день';

  @override
  String get highlights => 'Основные моменты';

  @override
  String get unresolvedQuestions => 'Нерешённые вопросы';

  @override
  String get decisions => 'Решения';

  @override
  String get learnings => 'Выводы';

  @override
  String get autoDeletesAfterThreeDays => 'Автоматически удаляется через 3 дня.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Граф знаний успешно удалён';

  @override
  String get exportStartedMayTakeFewSeconds => 'Экспорт начат. Это может занять несколько секунд...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Это удалит все производные данные графа знаний (узлы и связи). Ваши исходные воспоминания останутся в безопасности. Граф будет восстановлен со временем или по следующему запросу.';

  @override
  String get configureDailySummaryDigest => 'Настройте ежедневную сводку задач';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Доступ к $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'запускается $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription и $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Конкретный доступ к данным не настроен.';

  @override
  String get basicPlanDescription => '1 200 премиум минут + неограниченно на устройстве';

  @override
  String get minutes => 'минут';

  @override
  String get omiHas => 'У Omi:';

  @override
  String get premiumMinutesUsed => 'Премиум минуты использованы.';

  @override
  String get setupOnDevice => 'Настроить на устройстве';

  @override
  String get forUnlimitedFreeTranscription => 'для неограниченной бесплатной транскрипции.';

  @override
  String premiumMinsLeft(int count) {
    return 'Осталось $count премиум минут.';
  }

  @override
  String get alwaysAvailable => 'всегда доступно.';

  @override
  String get importHistory => 'История импорта';

  @override
  String get noImportsYet => 'Импортов пока нет';

  @override
  String get selectZipFileToImport => 'Выберите .zip файл для импорта!';

  @override
  String get otherDevicesComingSoon => 'Другие устройства скоро';

  @override
  String get deleteAllLimitlessConversations => 'Удалить все разговоры Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Это навсегда удалит все разговоры, импортированные из Limitless. Это действие нельзя отменить.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Удалено $count разговоров Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Не удалось удалить разговоры';

  @override
  String get deleteImportedData => 'Удалить импортированные данные';

  @override
  String get statusPending => 'Ожидание';

  @override
  String get statusProcessing => 'Обработка';

  @override
  String get statusCompleted => 'Завершено';

  @override
  String get statusFailed => 'Ошибка';

  @override
  String nConversations(int count) {
    return '$count разговоров';
  }

  @override
  String get pleaseEnterName => 'Пожалуйста, введите имя';

  @override
  String get nameMustBeBetweenCharacters => 'Имя должно содержать от 2 до 40 символов';

  @override
  String get deleteSampleQuestion => 'Удалить образец?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Вы уверены, что хотите удалить образец $name?';
  }

  @override
  String get confirmDeletion => 'Подтвердить удаление';

  @override
  String deletePersonConfirmation(String name) {
    return 'Вы уверены, что хотите удалить $name? Это также удалит все связанные образцы речи.';
  }

  @override
  String get howItWorksTitle => 'Как это работает?';

  @override
  String get howPeopleWorks =>
      'После создания человека вы можете перейти к расшифровке разговора и назначить ему соответствующие сегменты, тогда Omi сможет распознавать и его речь!';

  @override
  String get tapToDelete => 'Нажмите для удаления';

  @override
  String get newTag => 'НОВОЕ';

  @override
  String get needHelpChatWithUs => 'Нужна помощь? Свяжитесь с нами';

  @override
  String get localStorageEnabled => 'Локальное хранилище включено';

  @override
  String get localStorageDisabled => 'Локальное хранилище отключено';

  @override
  String failedToUpdateSettings(String error) {
    return 'Не удалось обновить настройки: $error';
  }

  @override
  String get privacyNotice => 'Уведомление о конфиденциальности';

  @override
  String get recordingsMayCaptureOthers =>
      'Записи могут захватывать голоса других людей. Перед включением убедитесь, что у вас есть согласие всех участников.';

  @override
  String get enable => 'Включить';

  @override
  String get storeAudioOnPhone => 'Хранить аудио на телефоне';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Храните все аудиозаписи локально на телефоне. При отключении сохраняются только неудачные загрузки для экономии места.';

  @override
  String get enableLocalStorage => 'Включить локальное хранилище';

  @override
  String get cloudStorageEnabled => 'Облачное хранилище включено';

  @override
  String get cloudStorageDisabled => 'Облачное хранилище отключено';

  @override
  String get enableCloudStorage => 'Включить облачное хранилище';

  @override
  String get storeAudioOnCloud => 'Хранить аудио в облаке';

  @override
  String get cloudStorageDialogMessage =>
      'Ваши записи в реальном времени будут храниться в частном облачном хранилище во время разговора.';

  @override
  String get storeAudioCloudDescription =>
      'Храните записи в реальном времени в частном облачном хранилище во время разговора. Аудио захватывается и сохраняется безопасно в реальном времени.';

  @override
  String get downloadingFirmware => 'Загрузка прошивки';

  @override
  String get installingFirmware => 'Установка прошивки';

  @override
  String get firmwareUpdateWarning =>
      'Не закрывайте приложение и не выключайте устройство. Это может повредить устройство.';

  @override
  String get firmwareUpdated => 'Прошивка обновлена';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Пожалуйста, перезагрузите $deviceName для завершения обновления.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Ваше устройство обновлено';

  @override
  String get currentVersion => 'Текущая версия';

  @override
  String get latestVersion => 'Последняя версия';

  @override
  String get whatsNew => 'Что нового';

  @override
  String get installUpdate => 'Установить обновление';

  @override
  String get updateNow => 'Обновить сейчас';

  @override
  String get updateGuide => 'Руководство по обновлению';

  @override
  String get checkingForUpdates => 'Проверка обновлений';

  @override
  String get checkingFirmwareVersion => 'Проверка версии прошивки...';

  @override
  String get firmwareUpdate => 'Обновление прошивки';

  @override
  String get payments => 'Платежи';

  @override
  String get connectPaymentMethodInfo =>
      'Подключите способ оплаты ниже, чтобы начать получать выплаты за ваши приложения.';

  @override
  String get selectedPaymentMethod => 'Выбранный способ оплаты';

  @override
  String get availablePaymentMethods => 'Доступные способы оплаты';

  @override
  String get activeStatus => 'Активный';

  @override
  String get connectedStatus => 'Подключено';

  @override
  String get notConnectedStatus => 'Не подключено';

  @override
  String get setActive => 'Сделать активным';

  @override
  String get getPaidThroughStripe => 'Получайте оплату за продажи приложений через Stripe';

  @override
  String get monthlyPayouts => 'Ежемесячные выплаты';

  @override
  String get monthlyPayoutsDescription => 'Получайте ежемесячные выплаты прямо на счёт, когда заработаете \$10';

  @override
  String get secureAndReliable => 'Безопасно и надёжно';

  @override
  String get stripeSecureDescription => 'Stripe обеспечивает безопасные и своевременные переводы доходов от приложения';

  @override
  String get selectYourCountry => 'Выберите свою страну';

  @override
  String get countrySelectionPermanent => 'Выбор страны является постоянным и не может быть изменён позже.';

  @override
  String get byClickingConnectNow => 'Нажимая \"Подключить сейчас\", вы соглашаетесь с';

  @override
  String get stripeConnectedAccountAgreement => 'Соглашение о подключенном аккаунте Stripe';

  @override
  String get errorConnectingToStripe => 'Ошибка подключения к Stripe! Пожалуйста, попробуйте позже.';

  @override
  String get connectingYourStripeAccount => 'Подключение вашего аккаунта Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Пожалуйста, завершите процесс регистрации Stripe в браузере. Эта страница автоматически обновится после завершения.';

  @override
  String get failedTryAgain => 'Не удалось? Попробовать снова';

  @override
  String get illDoItLater => 'Сделаю позже';

  @override
  String get successfullyConnected => 'Успешно подключено!';

  @override
  String get stripeReadyForPayments =>
      'Ваш аккаунт Stripe готов принимать платежи. Вы можете сразу начать зарабатывать на продажах приложений.';

  @override
  String get updateStripeDetails => 'Обновить данные Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Ошибка обновления данных Stripe! Пожалуйста, попробуйте позже.';

  @override
  String get updatePayPal => 'Обновить PayPal';

  @override
  String get setUpPayPal => 'Настроить PayPal';

  @override
  String get updatePayPalAccountDetails => 'Обновите данные вашего аккаунта PayPal';

  @override
  String get connectPayPalToReceivePayments =>
      'Подключите свой аккаунт PayPal, чтобы начать получать платежи за ваши приложения';

  @override
  String get paypalEmail => 'Email PayPal';

  @override
  String get paypalMeLink => 'Ссылка PayPal.me';

  @override
  String get stripeRecommendation =>
      'Если Stripe доступен в вашей стране, мы настоятельно рекомендуем использовать его для более быстрых и простых выплат.';

  @override
  String get updatePayPalDetails => 'Обновить данные PayPal';

  @override
  String get savePayPalDetails => 'Сохранить данные PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Пожалуйста, введите ваш email PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Пожалуйста, введите вашу ссылку PayPal.me';

  @override
  String get doNotIncludeHttpInLink => 'Не включайте http, https или www в ссылку';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Пожалуйста, введите действительную ссылку PayPal.me';

  @override
  String get pleaseEnterValidEmail => 'Пожалуйста, введите действительный адрес электронной почты';

  @override
  String get syncingYourRecordings => 'Синхронизация записей';

  @override
  String get syncYourRecordings => 'Синхронизировать записи';

  @override
  String get syncNow => 'Синхронизировать сейчас';

  @override
  String get error => 'Ошибка';

  @override
  String get speechSamples => 'Образцы голоса';

  @override
  String additionalSampleIndex(String index) {
    return 'Дополнительный образец $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Длительность: $seconds секунд';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Дополнительный образец голоса удален';

  @override
  String get consentDataMessage =>
      'Продолжая, все данные, которыми вы делитесь с этим приложением (включая ваши разговоры, записи и личную информацию), будут надежно храниться на наших серверах для предоставления вам аналитики на основе ИИ и включения всех функций приложения.';

  @override
  String get tasksEmptyStateMessage => 'Задачи из ваших разговоров появятся здесь.\nНажмите +, чтобы создать вручную.';

  @override
  String get clearChatAction => 'Очистить чат';

  @override
  String get enableApps => 'Включить приложения';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'показать больше ↓';

  @override
  String get showLess => 'показать меньше ↑';

  @override
  String get loadingYourRecording => 'Загрузка записи...';

  @override
  String get photoDiscardedMessage => 'Это фото было отклонено, так как оно не было значимым.';

  @override
  String get analyzing => 'Анализ...';

  @override
  String get searchCountries => 'Поиск стран...';

  @override
  String get checkingAppleWatch => 'Проверка Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Установите Omi на\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Чтобы использовать Apple Watch с Omi, сначала необходимо установить приложение Omi на часы.';

  @override
  String get openOmiOnAppleWatch => 'Откройте Omi на\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Приложение Omi установлено на Apple Watch. Откройте его и нажмите Старт.';

  @override
  String get openWatchApp => 'Открыть приложение Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Я установил и открыл приложение';

  @override
  String get unableToOpenWatchApp =>
      'Не удалось открыть приложение Apple Watch. Откройте приложение Watch вручную на Apple Watch и установите Omi из раздела \"Доступные приложения\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch успешно подключены!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch все еще недоступны. Убедитесь, что приложение Omi открыто на часах.';

  @override
  String errorCheckingConnection(String error) {
    return 'Ошибка проверки подключения: $error';
  }

  @override
  String get muted => 'Отключен звук';

  @override
  String get processNow => 'Обработать сейчас';

  @override
  String get finishedConversation => 'Завершить разговор?';

  @override
  String get stopRecordingConfirmation => 'Вы уверены, что хотите остановить запись и подвести итоги разговора сейчас?';

  @override
  String get conversationEndsManually => 'Разговор завершится только вручную.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Разговор подводится итог после $minutes минут$suffix молчания.';
  }

  @override
  String get dontAskAgain => 'Больше не спрашивать';

  @override
  String get waitingForTranscriptOrPhotos => 'Ожидание транскрипции или фотографий...';

  @override
  String get noSummaryYet => 'Резюме пока нет';

  @override
  String hints(String text) {
    return 'Подсказки: $text';
  }

  @override
  String get testConversationPrompt => 'Тестировать запрос разговора';

  @override
  String get prompt => 'Запрос';

  @override
  String get result => 'Результат:';

  @override
  String get compareTranscripts => 'Сравнить транскрипции';

  @override
  String get notHelpful => 'Бесполезно';

  @override
  String get exportTasksWithOneTap => 'Экспортируйте задачи одним нажатием!';

  @override
  String get inProgress => 'В процессе';

  @override
  String get photos => 'Фото';

  @override
  String get rawData => 'Необработанные данные';

  @override
  String get content => 'Контент';

  @override
  String get noContentToDisplay => 'Нет контента для отображения';

  @override
  String get noSummary => 'Нет сводки';

  @override
  String get updateOmiFirmware => 'Обновить прошивку omi';

  @override
  String get anErrorOccurredTryAgain => 'Произошла ошибка. Пожалуйста, попробуйте снова.';

  @override
  String get welcomeBackSimple => 'С возвращением';

  @override
  String get addVocabularyDescription => 'Добавьте слова, которые Omi должен распознавать при транскрипции.';

  @override
  String get enterWordsCommaSeparated => 'Введите слова (через запятую)';

  @override
  String get whenToReceiveDailySummary => 'Когда получать ежедневную сводку';

  @override
  String get checkingNextSevenDays => 'Проверка ближайших 7 дней';

  @override
  String failedToDeleteError(String error) {
    return 'Не удалось удалить: $error';
  }

  @override
  String get developerApiKeys => 'API-ключи разработчика';

  @override
  String get noApiKeysCreateOne => 'Нет API-ключей. Создайте один для начала.';

  @override
  String get commandRequired => '⌘ обязательна';

  @override
  String get spaceKey => 'Пробел';

  @override
  String loadMoreRemaining(String count) {
    return 'Загрузить ещё ($count осталось)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Топ $percentile% пользователь';
  }

  @override
  String get wrappedMinutes => 'минут';

  @override
  String get wrappedConversations => 'разговоров';

  @override
  String get wrappedDaysActive => 'активных дней';

  @override
  String get wrappedYouTalkedAbout => 'Вы говорили о';

  @override
  String get wrappedActionItems => 'Задачи';

  @override
  String get wrappedTasksCreated => 'созданных задач';

  @override
  String get wrappedCompleted => 'выполнено';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% завершённость';
  }

  @override
  String get wrappedYourTopDays => 'Ваши лучшие дни';

  @override
  String get wrappedBestMoments => 'Лучшие моменты';

  @override
  String get wrappedMyBuddies => 'Мои друзья';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Не мог перестать говорить о';

  @override
  String get wrappedShow => 'СЕРИАЛ';

  @override
  String get wrappedMovie => 'ФИЛЬМ';

  @override
  String get wrappedBook => 'КНИГА';

  @override
  String get wrappedCelebrity => 'ЗНАМЕНИТОСТЬ';

  @override
  String get wrappedFood => 'ЕДА';

  @override
  String get wrappedMovieRecs => 'Рекомендации фильмов для друзей';

  @override
  String get wrappedBiggest => 'Самый большой';

  @override
  String get wrappedStruggle => 'Вызов';

  @override
  String get wrappedButYouPushedThrough => 'Но вы справились 💪';

  @override
  String get wrappedWin => 'Победа';

  @override
  String get wrappedYouDidIt => 'У вас получилось! 🎉';

  @override
  String get wrappedTopPhrases => 'Топ-5 фраз';

  @override
  String get wrappedMins => 'мин';

  @override
  String get wrappedConvos => 'разговоров';

  @override
  String get wrappedDays => 'дней';

  @override
  String get wrappedMyBuddiesLabel => 'МОИ ДРУЗЬЯ';

  @override
  String get wrappedObsessionsLabel => 'УВЛЕЧЕНИЯ';

  @override
  String get wrappedStruggleLabel => 'ВЫЗОВ';

  @override
  String get wrappedWinLabel => 'ПОБЕДА';

  @override
  String get wrappedTopPhrasesLabel => 'ТОП ФРАЗ';

  @override
  String get wrappedLetsHitRewind => 'Давай перемотаем твой';

  @override
  String get wrappedGenerateMyWrapped => 'Создать мой Wrapped';

  @override
  String get wrappedProcessingDefault => 'Обработка...';

  @override
  String get wrappedCreatingYourStory => 'Создаём твою\nисторию 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Что-то пошло\nне так';

  @override
  String get wrappedAnErrorOccurred => 'Произошла ошибка';

  @override
  String get wrappedTryAgain => 'Попробовать снова';

  @override
  String get wrappedNoDataAvailable => 'Данные недоступны';

  @override
  String get wrappedOmiLifeRecap => 'Обзор жизни Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Свайпни вверх, чтобы начать';

  @override
  String get wrappedShareText => 'Мой 2025, сохранённый Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Не удалось поделиться. Пожалуйста, попробуйте снова.';

  @override
  String get wrappedFailedToStartGeneration => 'Не удалось начать генерацию. Пожалуйста, попробуйте снова.';

  @override
  String get wrappedStarting => 'Запуск...';

  @override
  String get wrappedShare => 'Поделиться';

  @override
  String get wrappedShareYourWrapped => 'Поделись своим Wrapped';

  @override
  String get wrappedMy2025 => 'Мой 2025';

  @override
  String get wrappedRememberedByOmi => 'сохранённый Omi';

  @override
  String get wrappedMostFunDay => 'Самый весёлый';

  @override
  String get wrappedMostProductiveDay => 'Самый продуктивный';

  @override
  String get wrappedMostIntenseDay => 'Самый интенсивный';

  @override
  String get wrappedFunniestMoment => 'Самый смешной';

  @override
  String get wrappedMostCringeMoment => 'Самый неловкий';

  @override
  String get wrappedMinutesLabel => 'минут';

  @override
  String get wrappedConversationsLabel => 'разговоров';

  @override
  String get wrappedDaysActiveLabel => 'активных дней';

  @override
  String get wrappedTasksGenerated => 'задач создано';

  @override
  String get wrappedTasksCompleted => 'задач выполнено';

  @override
  String get wrappedTopFivePhrases => 'Топ-5 фраз';

  @override
  String get wrappedAGreatDay => 'Отличный день';

  @override
  String get wrappedGettingItDone => 'Сделать это';

  @override
  String get wrappedAChallenge => 'Вызов';

  @override
  String get wrappedAHilariousMoment => 'Смешной момент';

  @override
  String get wrappedThatAwkwardMoment => 'Тот неловкий момент';

  @override
  String get wrappedYouHadFunnyMoments => 'У тебя были смешные моменты в этом году!';

  @override
  String get wrappedWeveAllBeenThere => 'Мы все через это проходили!';

  @override
  String get wrappedFriend => 'Друг';

  @override
  String get wrappedYourBuddy => 'Твой друг!';

  @override
  String get wrappedNotMentioned => 'Не упомянуто';

  @override
  String get wrappedTheHardPart => 'Трудная часть';

  @override
  String get wrappedPersonalGrowth => 'Личностный рост';

  @override
  String get wrappedFunDay => 'Весёлый';

  @override
  String get wrappedProductiveDay => 'Продуктивный';

  @override
  String get wrappedIntenseDay => 'Интенсивный';

  @override
  String get wrappedFunnyMomentTitle => 'Смешной момент';

  @override
  String get wrappedCringeMomentTitle => 'Неловкий момент';

  @override
  String get wrappedYouTalkedAboutBadge => 'Ты говорил о';

  @override
  String get wrappedCompletedLabel => 'Выполнено';

  @override
  String get wrappedMyBuddiesCard => 'Мои друзья';

  @override
  String get wrappedBuddiesLabel => 'ДРУЗЬЯ';

  @override
  String get wrappedObsessionsLabelUpper => 'УВЛЕЧЕНИЯ';

  @override
  String get wrappedStruggleLabelUpper => 'БОРЬБА';

  @override
  String get wrappedWinLabelUpper => 'ПОБЕДА';

  @override
  String get wrappedTopPhrasesLabelUpper => 'ТОП ФРАЗЫ';

  @override
  String get wrappedYourHeader => 'Твои';

  @override
  String get wrappedTopDaysHeader => 'Лучшие дни';

  @override
  String get wrappedYourTopDaysBadge => 'Твои лучшие дни';

  @override
  String get wrappedBestHeader => 'Лучшие';

  @override
  String get wrappedMomentsHeader => 'Моменты';

  @override
  String get wrappedBestMomentsBadge => 'Лучшие моменты';

  @override
  String get wrappedBiggestHeader => 'Самый большой';

  @override
  String get wrappedStruggleHeader => 'Борьба';

  @override
  String get wrappedWinHeader => 'Победа';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Но ты справился 💪';

  @override
  String get wrappedYouDidItEmoji => 'Ты сделал это! 🎉';

  @override
  String get wrappedHours => 'часов';

  @override
  String get wrappedActions => 'действий';

  @override
  String get multipleSpeakersDetected => 'Обнаружено несколько говорящих';

  @override
  String get multipleSpeakersDescription =>
      'Похоже, что в записи несколько говорящих. Убедитесь, что вы находитесь в тихом месте, и попробуйте снова.';

  @override
  String get invalidRecordingDetected => 'Обнаружена недействительная запись';

  @override
  String get notEnoughSpeechDescription =>
      'Недостаточно речи обнаружено. Пожалуйста, говорите больше и попробуйте снова.';

  @override
  String get speechDurationDescription => 'Убедитесь, что вы говорите не менее 5 секунд и не более 90.';

  @override
  String get connectionLostDescription =>
      'Соединение было прервано. Проверьте подключение к интернету и попробуйте снова.';

  @override
  String get howToTakeGoodSample => 'Как сделать хороший образец?';

  @override
  String get goodSampleInstructions =>
      '1. Убедитесь, что вы находитесь в тихом месте.\n2. Говорите четко и естественно.\n3. Убедитесь, что ваше устройство находится в естественном положении на шее.\n\nПосле создания вы всегда можете улучшить его или сделать заново.';

  @override
  String get noDeviceConnectedUseMic => 'Устройство не подключено. Будет использоваться микрофон телефона.';

  @override
  String get doItAgain => 'Сделать снова';

  @override
  String get listenToSpeechProfile => 'Послушать мой голосовой профиль ➡️';

  @override
  String get recognizingOthers => 'Распознавание других 👀';

  @override
  String get keepGoingGreat => 'Продолжайте, у вас отлично получается';

  @override
  String get somethingWentWrongTryAgain => 'Что-то пошло не так! Пожалуйста, попробуйте позже.';

  @override
  String get uploadingVoiceProfile => 'Загрузка вашего голосового профиля....';

  @override
  String get memorizingYourVoice => 'Запоминание вашего голоса...';

  @override
  String get personalizingExperience => 'Персонализация вашего опыта...';

  @override
  String get keepSpeakingUntil100 => 'Продолжайте говорить до 100%.';

  @override
  String get greatJobAlmostThere => 'Отличная работа, почти готово';

  @override
  String get soCloseJustLittleMore => 'Так близко, ещё немного';

  @override
  String get notificationFrequency => 'Частота уведомлений';

  @override
  String get controlNotificationFrequency => 'Управляйте частотой отправки проактивных уведомлений от Omi.';

  @override
  String get yourScore => 'Ваш счёт';

  @override
  String get dailyScoreBreakdown => 'Разбивка дневного счёта';

  @override
  String get todaysScore => 'Сегодняшний счёт';

  @override
  String get tasksCompleted => 'Задачи выполнены';

  @override
  String get completionRate => 'Процент выполнения';

  @override
  String get howItWorks => 'Как это работает';

  @override
  String get dailyScoreExplanation =>
      'Ваш дневной счёт основан на выполнении задач. Выполняйте задачи, чтобы улучшить свой счёт!';

  @override
  String get notificationFrequencyDescription =>
      'Управляйте тем, как часто Omi отправляет вам проактивные уведомления и напоминания.';

  @override
  String get sliderOff => 'Выкл.';

  @override
  String get sliderMax => 'Макс.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Сводка создана для $date';
  }

  @override
  String get failedToGenerateSummary => 'Не удалось создать сводку. Убедитесь, что у вас есть разговоры за этот день.';

  @override
  String get recap => 'Обзор';

  @override
  String deleteQuoted(String name) {
    return 'Удалить «$name»';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Переместить $count разговоров в:';
  }

  @override
  String get noFolder => 'Без папки';

  @override
  String get removeFromAllFolders => 'Удалить из всех папок';

  @override
  String get buildAndShareYourCustomApp => 'Создайте и поделитесь своим приложением';

  @override
  String get searchAppsPlaceholder => 'Поиск среди 1500+ приложений';

  @override
  String get filters => 'Фильтры';

  @override
  String get frequencyOff => 'Выкл';

  @override
  String get frequencyMinimal => 'Минимальная';

  @override
  String get frequencyLow => 'Низкая';

  @override
  String get frequencyBalanced => 'Сбалансированная';

  @override
  String get frequencyHigh => 'Высокая';

  @override
  String get frequencyMaximum => 'Максимальная';

  @override
  String get frequencyDescOff => 'Без проактивных уведомлений';

  @override
  String get frequencyDescMinimal => 'Только критические напоминания';

  @override
  String get frequencyDescLow => 'Только важные обновления';

  @override
  String get frequencyDescBalanced => 'Регулярные полезные напоминания';

  @override
  String get frequencyDescHigh => 'Частые проверки';

  @override
  String get frequencyDescMaximum => 'Оставайтесь постоянно вовлеченными';

  @override
  String get clearChatQuestion => 'Очистить чат?';

  @override
  String get syncingMessages => 'Синхронизация сообщений с сервером...';

  @override
  String get chatAppsTitle => 'Чат-приложения';

  @override
  String get selectApp => 'Выбрать приложение';

  @override
  String get noChatAppsEnabled => 'Чат-приложения не включены.\nНажмите \"Включить приложения\", чтобы добавить.';

  @override
  String get disable => 'Отключить';

  @override
  String get photoLibrary => 'Фотогалерея';

  @override
  String get chooseFile => 'Выбрать файл';

  @override
  String get configureAiPersona => 'Настройте своего ИИ-персонажа';

  @override
  String get connectAiAssistantsToYourData => 'Подключите ИИ-ассистентов к вашим данным';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Отслеживайте свои цели на главной странице';

  @override
  String get deleteRecording => 'Удалить запись';

  @override
  String get thisCannotBeUndone => 'Это действие нельзя отменить.';

  @override
  String get sdCard => 'SD-карта';

  @override
  String get fromSd => 'С SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Быстрая передача';

  @override
  String get syncingStatus => 'Синхронизация';

  @override
  String get failedStatus => 'Ошибка';

  @override
  String etaLabel(String time) {
    return 'Осталось: $time';
  }

  @override
  String get transferMethod => 'Метод передачи';

  @override
  String get fast => 'Быстрый';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Телефон';

  @override
  String get cancelSync => 'Отменить синхронизацию';

  @override
  String get cancelSyncMessage => 'Уже загруженные данные будут сохранены. Вы можете продолжить позже.';

  @override
  String get syncCancelled => 'Синхронизация отменена';

  @override
  String get deleteProcessedFiles => 'Удалить обработанные файлы';

  @override
  String get processedFilesDeleted => 'Обработанные файлы удалены';

  @override
  String get wifiEnableFailed => 'Не удалось включить WiFi на устройстве. Пожалуйста, попробуйте снова.';

  @override
  String get deviceNoFastTransfer => 'Ваше устройство не поддерживает быструю передачу. Используйте Bluetooth.';

  @override
  String get enableHotspotMessage => 'Пожалуйста, включите точку доступа на телефоне и попробуйте снова.';

  @override
  String get transferStartFailed => 'Не удалось начать передачу. Пожалуйста, попробуйте снова.';

  @override
  String get deviceNotResponding => 'Устройство не отвечает. Пожалуйста, попробуйте снова.';

  @override
  String get invalidWifiCredentials => 'Неверные данные WiFi. Проверьте настройки точки доступа.';

  @override
  String get wifiConnectionFailed => 'Ошибка подключения WiFi. Пожалуйста, попробуйте снова.';

  @override
  String get sdCardProcessing => 'Обработка SD-карты';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Обработка $count записи(ей). После обработки файлы будут удалены с SD-карты.';
  }

  @override
  String get process => 'Обработать';

  @override
  String get wifiSyncFailed => 'Ошибка синхронизации WiFi';

  @override
  String get processingFailed => 'Ошибка обработки';

  @override
  String get downloadingFromSdCard => 'Загрузка с SD-карты';

  @override
  String processingProgress(int current, int total) {
    return 'Обработка $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return 'Создано разговоров: $count';
  }

  @override
  String get internetRequired => 'Требуется интернет';

  @override
  String get processAudio => 'Обработать аудио';

  @override
  String get start => 'Начать';

  @override
  String get noRecordings => 'Нет записей';

  @override
  String get audioFromOmiWillAppearHere => 'Аудио с вашего устройства Omi появится здесь';

  @override
  String get deleteProcessed => 'Удалить обработанные';

  @override
  String get tryDifferentFilter => 'Попробуйте другой фильтр';

  @override
  String get recordings => 'Записи';

  @override
  String get enableRemindersAccess =>
      'Пожалуйста, включите доступ к Напоминаниям в Настройках для использования Apple Напоминаний';

  @override
  String todayAtTime(String time) {
    return 'Сегодня в $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Вчера в $time';
  }

  @override
  String get lessThanAMinute => 'Меньше минуты';

  @override
  String estimatedMinutes(int count) {
    return '~$count мин.';
  }

  @override
  String estimatedHours(int count) {
    return '~$count ч.';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Примерно: осталось $time';
  }

  @override
  String get summarizingConversation => 'Создание сводки разговора...\nЭто может занять несколько секунд';

  @override
  String get resummarizingConversation => 'Повторное создание сводки...\nЭто может занять несколько секунд';

  @override
  String get nothingInterestingRetry => 'Ничего интересного не найдено,\nхотите попробовать снова?';

  @override
  String get noSummaryForConversation => 'Для этого разговора\nнет сводки.';

  @override
  String get unknownLocation => 'Неизвестное местоположение';

  @override
  String get couldNotLoadMap => 'Не удалось загрузить карту';

  @override
  String get triggerConversationIntegration => 'Запустить интеграцию создания разговора';

  @override
  String get webhookUrlNotSet => 'URL вебхука не установлен';

  @override
  String get setWebhookUrlInSettings =>
      'Установите URL вебхука в настройках разработчика для использования этой функции.';

  @override
  String get sendWebUrl => 'Отправить веб-ссылку';

  @override
  String get sendTranscript => 'Отправить транскрипт';

  @override
  String get sendSummary => 'Отправить сводку';

  @override
  String get debugModeDetected => 'Обнаружен режим отладки';

  @override
  String get performanceReduced => 'Производительность может быть снижена';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Автоматическое закрытие через $seconds секунд';
  }

  @override
  String get modelRequired => 'Требуется модель';

  @override
  String get downloadWhisperModel => 'Загрузите модель whisper для использования транскрипции на устройстве';

  @override
  String get deviceNotCompatible => 'Ваше устройство несовместимо с транскрипцией на устройстве';

  @override
  String get deviceRequirements => 'Ваше устройство не соответствует требованиям для транскрипции на устройстве.';

  @override
  String get willLikelyCrash => 'Включение, вероятно, приведёт к сбою или зависанию приложения.';

  @override
  String get transcriptionSlowerLessAccurate => 'Транскрипция будет значительно медленнее и менее точной.';

  @override
  String get proceedAnyway => 'Всё равно продолжить';

  @override
  String get olderDeviceDetected => 'Обнаружено старое устройство';

  @override
  String get onDeviceSlower => 'Транскрипция на устройстве может быть медленнее на этом устройстве.';

  @override
  String get batteryUsageHigher => 'Расход батареи будет выше, чем при облачной транскрипции.';

  @override
  String get considerOmiCloud => 'Рассмотрите использование Omi Cloud для лучшей производительности.';

  @override
  String get highResourceUsage => 'Высокое использование ресурсов';

  @override
  String get onDeviceIntensive => 'Транскрипция на устройстве требует значительных вычислительных ресурсов.';

  @override
  String get batteryDrainIncrease => 'Расход заряда батареи значительно увеличится.';

  @override
  String get deviceMayWarmUp => 'Устройство может нагреться при длительном использовании.';

  @override
  String get speedAccuracyLower => 'Скорость и точность могут быть ниже, чем у облачных моделей.';

  @override
  String get cloudProvider => 'Облачный провайдер';

  @override
  String get premiumMinutesInfo =>
      '1 200 премиум-минут в месяц. Вкладка \"На устройстве\" предлагает неограниченную бесплатную транскрипцию.';

  @override
  String get viewUsage => 'Посмотреть использование';

  @override
  String get localProcessingInfo =>
      'Аудио обрабатывается локально. Работает офлайн, более приватно, но расходует больше заряда батареи.';

  @override
  String get model => 'Модель';

  @override
  String get performanceWarning => 'Предупреждение о производительности';

  @override
  String get largeModelWarning =>
      'Эта модель большая и может привести к сбою приложения или очень медленной работе на мобильных устройствах.\n\nРекомендуется использовать \"small\" или \"base\".';

  @override
  String get usingNativeIosSpeech => 'Использование встроенного распознавания речи iOS';

  @override
  String get noModelDownloadRequired =>
      'Будет использован встроенный механизм распознавания речи вашего устройства. Загрузка модели не требуется.';

  @override
  String get modelReady => 'Модель готова';

  @override
  String get redownload => 'Загрузить повторно';

  @override
  String get doNotCloseApp => 'Пожалуйста, не закрывайте приложение.';

  @override
  String get downloading => 'Загрузка...';

  @override
  String get downloadModel => 'Загрузить модель';

  @override
  String estimatedSize(String size) {
    return 'Приблизительный размер: ~$size МБ';
  }

  @override
  String availableSpace(String space) {
    return 'Доступное место: $space';
  }

  @override
  String get notEnoughSpace => 'Предупреждение: Недостаточно места!';

  @override
  String get download => 'Загрузить';

  @override
  String downloadError(String error) {
    return 'Ошибка загрузки: $error';
  }

  @override
  String get cancelled => 'Отменено';

  @override
  String get deviceNotCompatibleTitle => 'Устройство несовместимо';

  @override
  String get deviceNotMeetRequirements =>
      'Ваше устройство не соответствует требованиям для транскрипции на устройстве.';

  @override
  String get transcriptionSlowerOnDevice => 'Транскрипция на устройстве может быть медленнее на этом устройстве.';

  @override
  String get computationallyIntensive => 'Транскрипция на устройстве требует больших вычислительных ресурсов.';

  @override
  String get batteryDrainSignificantly => 'Расход батареи значительно увеличится.';

  @override
  String get premiumMinutesMonth =>
      '1200 премиум-минут/месяц. Вкладка На устройстве предлагает неограниченную бесплатную транскрипцию. ';

  @override
  String get audioProcessedLocally =>
      'Аудио обрабатывается локально. Работает офлайн, более приватно, но расходует больше батареи.';

  @override
  String get languageLabel => 'Язык';

  @override
  String get modelLabel => 'Модель';

  @override
  String get modelTooLargeWarning =>
      'Эта модель большая и может вызвать сбой приложения или очень медленную работу на мобильных устройствах.\n\nРекомендуется small или base.';

  @override
  String get nativeEngineNoDownload =>
      'Будет использован встроенный речевой движок вашего устройства. Загрузка модели не требуется.';

  @override
  String modelReadyWithName(String model) {
    return 'Модель готова ($model)';
  }

  @override
  String get reDownload => 'Загрузить снова';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Загрузка $model: $received / $total МБ';
  }

  @override
  String preparingModel(String model) {
    return 'Подготовка $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Ошибка загрузки: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Приблизительный размер: ~$size МБ';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Доступное место: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Встроенная живая транскрипция Omi оптимизирована для разговоров в реальном времени с автоматическим определением говорящего и диаризацией.';

  @override
  String get reset => 'Сбросить';

  @override
  String get useTemplateFrom => 'Использовать шаблон от';

  @override
  String get selectProviderTemplate => 'Выберите шаблон провайдера...';

  @override
  String get quicklyPopulateResponse => 'Быстро заполнить известным форматом ответа провайдера';

  @override
  String get quicklyPopulateRequest => 'Быстро заполнить известным форматом запроса провайдера';

  @override
  String get invalidJsonError => 'Недопустимый JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Загрузить модель ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Модель: $model';
  }

  @override
  String get device => 'Устройство';

  @override
  String get chatAssistantsTitle => 'Чат-ассистенты';

  @override
  String get permissionReadConversations => 'Читать разговоры';

  @override
  String get permissionReadMemories => 'Читать воспоминания';

  @override
  String get permissionReadTasks => 'Читать задачи';

  @override
  String get permissionCreateConversations => 'Создавать разговоры';

  @override
  String get permissionCreateMemories => 'Создавать воспоминания';

  @override
  String get permissionTypeAccess => 'Доступ';

  @override
  String get permissionTypeCreate => 'Создание';

  @override
  String get permissionTypeTrigger => 'Триггер';

  @override
  String get permissionDescReadConversations => 'Это приложение может получить доступ к вашим разговорам.';

  @override
  String get permissionDescReadMemories => 'Это приложение может получить доступ к вашим воспоминаниям.';

  @override
  String get permissionDescReadTasks => 'Это приложение может получить доступ к вашим задачам.';

  @override
  String get permissionDescCreateConversations => 'Это приложение может создавать новые разговоры.';

  @override
  String get permissionDescCreateMemories => 'Это приложение может создавать новые воспоминания.';

  @override
  String get realtimeListening => 'Прослушивание в реальном времени';

  @override
  String get setupCompleted => 'Завершено';

  @override
  String get pleaseSelectRating => 'Пожалуйста, выберите оценку';

  @override
  String get writeReviewOptional => 'Написать отзыв (необязательно)';

  @override
  String get setupQuestionsIntro => 'Помогите нам улучшить Omi, ответив на несколько вопросов. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Чем вы занимаетесь?';

  @override
  String get setupQuestionUsage => '2. Где вы планируете использовать Omi?';

  @override
  String get setupQuestionAge => '3. Ваш возраст?';

  @override
  String get setupAnswerAllQuestions => 'Вы ещё не ответили на все вопросы! 🥺';

  @override
  String get setupSkipHelp => 'Пропустить, я не хочу помогать :C';

  @override
  String get professionEntrepreneur => 'Предприниматель';

  @override
  String get professionSoftwareEngineer => 'Разработчик ПО';

  @override
  String get professionProductManager => 'Продакт-менеджер';

  @override
  String get professionExecutive => 'Руководитель';

  @override
  String get professionSales => 'Продажи';

  @override
  String get professionStudent => 'Студент';

  @override
  String get usageAtWork => 'На работе';

  @override
  String get usageIrlEvents => 'На мероприятиях';

  @override
  String get usageOnline => 'Онлайн';

  @override
  String get usageSocialSettings => 'В социальных ситуациях';

  @override
  String get usageEverywhere => 'Везде';

  @override
  String get customBackendUrlTitle => 'Пользовательский URL сервера';

  @override
  String get backendUrlLabel => 'URL сервера';

  @override
  String get saveUrlButton => 'Сохранить URL';

  @override
  String get enterBackendUrlError => 'Введите URL сервера';

  @override
  String get urlMustEndWithSlashError => 'URL должен заканчиваться на \"/\"';

  @override
  String get invalidUrlError => 'Введите корректный URL';

  @override
  String get backendUrlSavedSuccess => 'URL сервера успешно сохранён!';

  @override
  String get signInTitle => 'Войти';

  @override
  String get signInButton => 'Войти';

  @override
  String get enterEmailError => 'Введите ваш email';

  @override
  String get invalidEmailError => 'Введите корректный email';

  @override
  String get enterPasswordError => 'Введите ваш пароль';

  @override
  String get passwordMinLengthError => 'Пароль должен быть не менее 8 символов';

  @override
  String get signInSuccess => 'Вход выполнен успешно!';

  @override
  String get alreadyHaveAccountLogin => 'Уже есть аккаунт? Войдите';

  @override
  String get emailLabel => 'Эл. почта';

  @override
  String get passwordLabel => 'Пароль';

  @override
  String get createAccountTitle => 'Создать аккаунт';

  @override
  String get nameLabel => 'Имя';

  @override
  String get repeatPasswordLabel => 'Повторите пароль';

  @override
  String get signUpButton => 'Зарегистрироваться';

  @override
  String get enterNameError => 'Введите ваше имя';

  @override
  String get passwordsDoNotMatch => 'Пароли не совпадают';

  @override
  String get signUpSuccess => 'Регистрация успешна!';

  @override
  String get loadingKnowledgeGraph => 'Загрузка графа знаний...';

  @override
  String get noKnowledgeGraphYet => 'Графа знаний пока нет';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Построение графа знаний из воспоминаний...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Ваш граф знаний будет построен автоматически при создании новых воспоминаний.';

  @override
  String get buildGraphButton => 'Построить граф';

  @override
  String get checkOutMyMemoryGraph => 'Посмотрите мой граф памяти!';

  @override
  String get getButton => 'Загрузить';

  @override
  String openingApp(String appName) {
    return 'Открытие $appName...';
  }

  @override
  String get writeSomething => 'Напишите что-нибудь';

  @override
  String get submitReply => 'Отправить ответ';

  @override
  String get editYourReply => 'Редактировать ответ';

  @override
  String get replyToReview => 'Ответить на отзыв';

  @override
  String get rateAndReviewThisApp => 'Оцените и напишите отзыв об этом приложении';

  @override
  String get noChangesInReview => 'Нет изменений в отзыве для обновления.';

  @override
  String get cantRateWithoutInternet => 'Невозможно оценить приложение без подключения к интернету.';

  @override
  String get appAnalytics => 'Аналитика приложения';

  @override
  String get learnMoreLink => 'узнать больше';

  @override
  String get moneyEarned => 'Заработано';

  @override
  String get writeYourReply => 'Напишите ваш ответ...';

  @override
  String get replySentSuccessfully => 'Ответ успешно отправлен';

  @override
  String failedToSendReply(String error) {
    return 'Не удалось отправить ответ: $error';
  }

  @override
  String get send => 'Отправить';

  @override
  String starFilter(int count) {
    return '$count звезд';
  }

  @override
  String get noReviewsFound => 'Отзывы не найдены';

  @override
  String get editReply => 'Редактировать ответ';

  @override
  String get reply => 'Ответить';

  @override
  String starFilterLabel(int count) {
    return '$count звезда';
  }

  @override
  String get sharePublicLink => 'Поделиться публичной ссылкой';

  @override
  String get makePersonaPublic => 'Сделать персонажа публичным';

  @override
  String get connectedKnowledgeData => 'Подключённые данные';

  @override
  String get enterName => 'Введите имя';

  @override
  String get disconnectTwitter => 'Отключить Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Вы уверены, что хотите отключить свой аккаунт Twitter? Ваш персонаж больше не будет иметь доступа к данным Twitter.';

  @override
  String get getOmiDeviceDescription => 'Создайте более точный клон с помощью ваших личных разговоров';

  @override
  String get getOmi => 'Получить Omi';

  @override
  String get iHaveOmiDevice => 'У меня есть устройство Omi';

  @override
  String get goal => 'ЦЕЛЬ';

  @override
  String get tapToTrackThisGoal => 'Нажмите, чтобы отслеживать эту цель';

  @override
  String get tapToSetAGoal => 'Нажмите, чтобы установить цель';

  @override
  String get processedConversations => 'Обработанные разговоры';

  @override
  String get updatedConversations => 'Обновлённые разговоры';

  @override
  String get newConversations => 'Новые разговоры';

  @override
  String get summaryTemplate => 'Шаблон сводки';

  @override
  String get suggestedTemplates => 'Рекомендуемые шаблоны';

  @override
  String get otherTemplates => 'Другие шаблоны';

  @override
  String get availableTemplates => 'Доступные шаблоны';

  @override
  String get getCreative => 'Будьте креативны';

  @override
  String get defaultLabel => 'По умолчанию';

  @override
  String get lastUsedLabel => 'Последнее использование';

  @override
  String get setDefaultApp => 'Установить приложение по умолчанию';

  @override
  String setDefaultAppContent(String appName) {
    return 'Установить $appName как приложение для сводок по умолчанию?\\n\\nЭто приложение будет автоматически использоваться для всех будущих сводок разговоров.';
  }

  @override
  String get setDefaultButton => 'Установить по умолчанию';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName установлено как приложение для сводок по умолчанию';
  }

  @override
  String get createCustomTemplate => 'Создать свой шаблон';

  @override
  String get allTemplates => 'Все шаблоны';

  @override
  String failedToInstallApp(String appName) {
    return 'Не удалось установить $appName. Пожалуйста, попробуйте снова.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Ошибка установки $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Отметить говорящего $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Человек с таким именем уже существует.';

  @override
  String get selectYouFromList => 'Чтобы отметить себя, выберите \"Вы\" из списка.';

  @override
  String get enterPersonsName => 'Введите имя человека';

  @override
  String get addPerson => 'Добавить человека';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Отметить другие сегменты этого говорящего ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Отметить другие сегменты';

  @override
  String get managePeople => 'Управление людьми';

  @override
  String get shareViaSms => 'Поделиться по SMS';

  @override
  String get selectContactsToShareSummary => 'Выберите контакты для отправки сводки разговора';

  @override
  String get searchContactsHint => 'Поиск контактов...';

  @override
  String contactsSelectedCount(int count) {
    return '$count выбрано';
  }

  @override
  String get clearAllSelection => 'Очистить все';

  @override
  String get selectContactsToShare => 'Выберите контакты для отправки';

  @override
  String shareWithContactCount(int count) {
    return 'Отправить $count контакту';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Отправить $count контактам';
  }

  @override
  String get contactsPermissionRequired => 'Требуется разрешение на доступ к контактам';

  @override
  String get contactsPermissionRequiredForSms => 'Для отправки по SMS требуется разрешение на доступ к контактам';

  @override
  String get grantContactsPermissionForSms =>
      'Пожалуйста, предоставьте разрешение на доступ к контактам для отправки по SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Контакты с номерами телефонов не найдены';

  @override
  String get noContactsMatchSearch => 'Контакты по вашему запросу не найдены';

  @override
  String get failedToLoadContacts => 'Не удалось загрузить контакты';

  @override
  String get failedToPrepareConversationForSharing =>
      'Не удалось подготовить разговор для отправки. Пожалуйста, попробуйте снова.';

  @override
  String get couldNotOpenSmsApp => 'Не удалось открыть приложение SMS. Пожалуйста, попробуйте снова.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Вот о чём мы только что говорили: $link';
  }

  @override
  String get wifiSync => 'Синхронизация WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item скопировано в буфер обмена';
  }

  @override
  String get wifiConnectionFailedTitle => 'Ошибка подключения';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Подключение к $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Включить WiFi на $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Подключиться к $deviceName';
  }

  @override
  String get recordingDetails => 'Детали записи';

  @override
  String get storageLocationSdCard => 'SD-карта';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Телефон';

  @override
  String get storageLocationPhoneMemory => 'Телефон (память)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Хранится на $deviceName';
  }

  @override
  String get transferring => 'Передача...';

  @override
  String get transferRequired => 'Требуется передача';

  @override
  String get downloadingAudioFromSdCard => 'Загрузка аудио с SD-карты вашего устройства';

  @override
  String get transferRequiredDescription =>
      'Эта запись хранится на SD-карте вашего устройства. Передайте её на телефон для воспроизведения или обмена.';

  @override
  String get cancelTransfer => 'Отменить передачу';

  @override
  String get transferToPhone => 'Передать на телефон';

  @override
  String get privateAndSecureOnDevice => 'Конфиденциально и безопасно на вашем устройстве';

  @override
  String get recordingInfo => 'Информация о записи';

  @override
  String get transferInProgress => 'Идёт передача...';

  @override
  String get shareRecording => 'Поделиться записью';

  @override
  String get deleteRecordingConfirmation =>
      'Вы уверены, что хотите безвозвратно удалить эту запись? Это действие нельзя отменить.';

  @override
  String get recordingIdLabel => 'ID записи';

  @override
  String get dateTimeLabel => 'Дата и время';

  @override
  String get durationLabel => 'Длительность';

  @override
  String get audioFormatLabel => 'Формат аудио';

  @override
  String get storageLocationLabel => 'Место хранения';

  @override
  String get estimatedSizeLabel => 'Примерный размер';

  @override
  String get deviceModelLabel => 'Модель устройства';

  @override
  String get deviceIdLabel => 'ID устройства';

  @override
  String get statusLabel => 'Статус';

  @override
  String get statusProcessed => 'Обработано';

  @override
  String get statusUnprocessed => 'Не обработано';

  @override
  String get switchedToFastTransfer => 'Переключено на быструю передачу';

  @override
  String get transferCompleteMessage => 'Передача завершена! Теперь вы можете воспроизвести эту запись.';

  @override
  String transferFailedMessage(String error) {
    return 'Ошибка передачи: $error';
  }

  @override
  String get transferCancelled => 'Передача отменена';

  @override
  String get fastTransferEnabled => 'Быстрая передача включена';

  @override
  String get bluetoothSyncEnabled => 'Синхронизация Bluetooth включена';

  @override
  String get enableFastTransfer => 'Включить быструю передачу';

  @override
  String get fastTransferDescription =>
      'Быстрая передача использует WiFi для ~5x более быстрых скоростей. Ваш телефон временно подключится к WiFi-сети устройства Omi во время передачи.';

  @override
  String get internetAccessPausedDuringTransfer => 'Доступ в интернет приостановлен во время передачи';

  @override
  String get chooseTransferMethodDescription => 'Выберите, как записи передаются с устройства Omi на телефон.';

  @override
  String get wifiSpeed => '~150 КБ/с через WiFi';

  @override
  String get fiveTimesFaster => 'В 5 РАЗ БЫСТРЕЕ';

  @override
  String get fastTransferMethodDescription =>
      'Создаёт прямое WiFi-подключение к устройству Omi. Телефон временно отключается от обычного WiFi во время передачи.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 КБ/с через BLE';

  @override
  String get bluetoothMethodDescription =>
      'Использует стандартное подключение Bluetooth Low Energy. Медленнее, но не влияет на WiFi-соединение.';

  @override
  String get selected => 'Выбрано';

  @override
  String get selectOption => 'Выбрать';

  @override
  String get lowBatteryAlertTitle => 'Предупреждение о низком заряде';

  @override
  String get lowBatteryAlertBody => 'Батарея вашего устройства разряжена. Пора зарядить! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Ваше устройство Omi отключено';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Пожалуйста, подключитесь снова, чтобы продолжить использование Omi.';

  @override
  String get firmwareUpdateAvailable => 'Доступно обновление прошивки';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Для вашего устройства Omi доступно новое обновление прошивки ($version). Хотите обновить сейчас?';
  }

  @override
  String get later => 'Позже';

  @override
  String get appDeletedSuccessfully => 'Приложение успешно удалено';

  @override
  String get appDeleteFailed => 'Не удалось удалить приложение. Попробуйте позже.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Видимость приложения успешно изменена. Изменения могут отобразиться через несколько минут.';

  @override
  String get errorActivatingAppIntegration =>
      'Ошибка при активации приложения. Если это приложение-интеграция, убедитесь, что настройка завершена.';

  @override
  String get errorUpdatingAppStatus => 'Произошла ошибка при обновлении статуса приложения.';

  @override
  String get calculatingETA => 'Вычисление...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Осталось около $minutes минут';
  }

  @override
  String get aboutAMinuteRemaining => 'Осталось около минуты';

  @override
  String get almostDone => 'Почти готово...';

  @override
  String get omiSays => 'omi говорит';

  @override
  String get analyzingYourData => 'Анализ ваших данных...';

  @override
  String migratingToProtection(String level) {
    return 'Миграция на защиту $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Нет данных для миграции. Завершение...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Миграция $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Все объекты перенесены. Завершение...';

  @override
  String get migrationErrorOccurred => 'Произошла ошибка при миграции. Пожалуйста, попробуйте снова.';

  @override
  String get migrationComplete => 'Миграция завершена!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Ваши данные теперь защищены новыми настройками $level.';
  }

  @override
  String get chatsLowercase => 'чаты';

  @override
  String get dataLowercase => 'данные';

  @override
  String get fallNotificationTitle => 'Ой';

  @override
  String get fallNotificationBody => 'Вы упали?';

  @override
  String get importantConversationTitle => 'Важный разговор';

  @override
  String get importantConversationBody => 'У вас только что был важный разговор. Нажмите, чтобы поделиться сводкой.';

  @override
  String get templateName => 'Название шаблона';

  @override
  String get templateNameHint => 'напр. Извлечение действий из совещания';

  @override
  String get nameMustBeAtLeast3Characters => 'Название должно содержать не менее 3 символов';

  @override
  String get conversationPromptHint => 'напр., Извлеките задачи, принятые решения и ключевые выводы из разговора.';

  @override
  String get pleaseEnterAppPrompt => 'Пожалуйста, введите подсказку для приложения';

  @override
  String get promptMustBeAtLeast10Characters => 'Подсказка должна содержать не менее 10 символов';

  @override
  String get anyoneCanDiscoverTemplate => 'Любой может найти ваш шаблон';

  @override
  String get onlyYouCanUseTemplate => 'Только вы можете использовать этот шаблон';

  @override
  String get generatingDescription => 'Создание описания...';

  @override
  String get creatingAppIcon => 'Создание значка приложения...';

  @override
  String get installingApp => 'Установка приложения...';

  @override
  String get appCreatedAndInstalled => 'Приложение создано и установлено!';

  @override
  String get appCreatedSuccessfully => 'Приложение успешно создано!';

  @override
  String get failedToCreateApp => 'Не удалось создать приложение. Попробуйте снова.';

  @override
  String get addAppSelectCoreCapability => 'Выберите ещё одну основную возможность для вашего приложения';

  @override
  String get addAppSelectPaymentPlan => 'Выберите план оплаты и укажите цену приложения';

  @override
  String get addAppSelectCapability => 'Выберите хотя бы одну возможность для вашего приложения';

  @override
  String get addAppSelectLogo => 'Выберите логотип для вашего приложения';

  @override
  String get addAppEnterChatPrompt => 'Введите подсказку чата для вашего приложения';

  @override
  String get addAppEnterConversationPrompt => 'Введите подсказку для разговора';

  @override
  String get addAppSelectTriggerEvent => 'Выберите событие-триггер для вашего приложения';

  @override
  String get addAppEnterWebhookUrl => 'Введите URL вебхука для вашего приложения';

  @override
  String get addAppSelectCategory => 'Выберите категорию для вашего приложения';

  @override
  String get addAppFillRequiredFields => 'Заполните все обязательные поля правильно';

  @override
  String get addAppUpdatedSuccess => 'Приложение успешно обновлено 🚀';

  @override
  String get addAppUpdateFailed => 'Не удалось обновить. Попробуйте позже';

  @override
  String get addAppSubmittedSuccess => 'Приложение успешно отправлено 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Ошибка при открытии выбора файлов: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Ошибка при выборе изображения: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Доступ к фото запрещён. Разрешите доступ к фотографиям';

  @override
  String get addAppErrorSelectingImageRetry => 'Ошибка при выборе изображения. Попробуйте снова.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Ошибка при выборе миниатюры: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Ошибка при выборе миниатюры. Попробуйте снова.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Другие возможности нельзя выбрать вместе с Персоной';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Персону нельзя выбрать вместе с другими возможностями';

  @override
  String get personaTwitterHandleNotFound => 'Twitter-аккаунт не найден';

  @override
  String get personaTwitterHandleSuspended => 'Twitter-аккаунт заблокирован';

  @override
  String get personaFailedToVerifyTwitter => 'Не удалось проверить Twitter-аккаунт';

  @override
  String get personaFailedToFetch => 'Не удалось получить вашу персону';

  @override
  String get personaFailedToCreate => 'Не удалось создать персону';

  @override
  String get personaConnectKnowledgeSource => 'Подключите хотя бы один источник данных (Omi или Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Персона успешно обновлена';

  @override
  String get personaFailedToUpdate => 'Не удалось обновить персону';

  @override
  String get personaPleaseSelectImage => 'Выберите изображение';

  @override
  String get personaFailedToCreateTryLater => 'Не удалось создать персону. Попробуйте позже.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Не удалось создать персону: $error';
  }

  @override
  String get personaFailedToEnable => 'Не удалось включить персону';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Ошибка при включении персоны: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Не удалось получить список стран. Попробуйте позже.';

  @override
  String get paymentFailedToSetDefault => 'Не удалось установить способ оплаты по умолчанию. Попробуйте позже.';

  @override
  String get paymentFailedToSavePaypal => 'Не удалось сохранить данные PayPal. Попробуйте позже.';

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
  String get paymentStatusConnected => 'Подключено';

  @override
  String get paymentStatusNotConnected => 'Не подключено';

  @override
  String get paymentAppCost => 'Стоимость приложения';

  @override
  String get paymentEnterValidAmount => 'Введите корректную сумму';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Введите сумму больше 0';

  @override
  String get paymentPlan => 'План оплаты';

  @override
  String get paymentNoneSelected => 'Не выбрано';

  @override
  String get aiGenPleaseEnterDescription => 'Пожалуйста, введите описание вашего приложения';

  @override
  String get aiGenCreatingAppIcon => 'Создание иконки приложения...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Произошла ошибка: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Приложение успешно создано!';

  @override
  String get aiGenFailedToCreateApp => 'Не удалось создать приложение';

  @override
  String get aiGenErrorWhileCreatingApp => 'При создании приложения произошла ошибка';

  @override
  String get aiGenFailedToGenerateApp => 'Не удалось сгенерировать приложение. Пожалуйста, попробуйте снова.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Не удалось повторно сгенерировать иконку';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Пожалуйста, сначала сгенерируйте приложение';

  @override
  String get xHandleTitle => 'Какой у вас X?';

  @override
  String get xHandleDescription => 'Мы предварительно обучим вашего клона Omi\nна основе активности вашего аккаунта';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Пожалуйста, введите ваш X';

  @override
  String get xHandlePleaseEnterValid => 'Пожалуйста, введите корректный X';

  @override
  String get nextButton => 'Далее';

  @override
  String get connectOmiDevice => 'Подключить устройство Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Вы меняете свой тарифный план Unlimited на $title. Вы уверены, что хотите продолжить?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Обновление запланировано! Ваш месячный план продолжает действовать до конца расчётного периода, затем автоматически переключится на годовой.';

  @override
  String get couldNotSchedulePlanChange => 'Не удалось запланировать смену тарифа. Пожалуйста, попробуйте снова.';

  @override
  String get subscriptionReactivatedDefault =>
      'Ваша подписка восстановлена! Оплата сейчас не взимается — счёт будет выставлен в конце текущего периода.';

  @override
  String get subscriptionSuccessfulCharged =>
      'Подписка успешно оформлена! Вам выставлен счёт за новый расчётный период.';

  @override
  String get couldNotProcessSubscription => 'Не удалось обработать подписку. Пожалуйста, попробуйте снова.';

  @override
  String get couldNotLaunchUpgradePage => 'Не удалось открыть страницу обновления. Пожалуйста, попробуйте снова.';

  @override
  String get transcriptionJsonPlaceholder => 'Вставьте вашу конфигурацию JSON здесь...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Ошибка при открытии выбора файлов: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Ошибка: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Разговоры успешно объединены';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count разговоров успешно объединено';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Время для ежедневной рефлексии';

  @override
  String get dailyReflectionNotificationBody => 'Расскажи мне о своём дне';

  @override
  String get actionItemReminderTitle => 'Напоминание Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName отключено';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Пожалуйста, переподключитесь, чтобы продолжить использование вашего $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Войти';

  @override
  String get onboardingYourName => 'Ваше имя';

  @override
  String get onboardingLanguage => 'Язык';

  @override
  String get onboardingPermissions => 'Разрешения';

  @override
  String get onboardingComplete => 'Готово';

  @override
  String get onboardingWelcomeToOmi => 'Добро пожаловать в Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Расскажите о себе';

  @override
  String get onboardingChooseYourPreference => 'Выберите предпочтения';

  @override
  String get onboardingGrantRequiredAccess => 'Предоставить необходимый доступ';

  @override
  String get onboardingYoureAllSet => 'Всё готово';

  @override
  String get searchTranscriptOrSummary => 'Поиск в транскрипции или резюме...';

  @override
  String get myGoal => 'Моя цель';

  @override
  String get appNotAvailable => 'Упс! Похоже, что приложение, которое вы ищете, недоступно.';

  @override
  String get failedToConnectTodoist => 'Не удалось подключиться к Todoist';

  @override
  String get failedToConnectAsana => 'Не удалось подключиться к Asana';

  @override
  String get failedToConnectGoogleTasks => 'Не удалось подключиться к Google Tasks';

  @override
  String get failedToConnectClickUp => 'Не удалось подключиться к ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Не удалось подключиться к $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Успешно подключено к Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Не удалось подключиться к Todoist. Пожалуйста, попробуйте снова.';

  @override
  String get successfullyConnectedAsana => 'Успешно подключено к Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Не удалось подключиться к Asana. Пожалуйста, попробуйте снова.';

  @override
  String get successfullyConnectedGoogleTasks => 'Успешно подключено к Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Не удалось подключиться к Google Tasks. Пожалуйста, попробуйте снова.';

  @override
  String get successfullyConnectedClickUp => 'Успешно подключено к ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Не удалось подключиться к ClickUp. Пожалуйста, попробуйте снова.';

  @override
  String get successfullyConnectedNotion => 'Успешно подключено к Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Не удалось обновить статус подключения Notion.';

  @override
  String get successfullyConnectedGoogle => 'Успешно подключено к Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Не удалось обновить статус подключения Google.';

  @override
  String get successfullyConnectedWhoop => 'Успешно подключено к Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Не удалось обновить статус подключения Whoop.';

  @override
  String get successfullyConnectedGitHub => 'Успешно подключено к GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Не удалось обновить статус подключения GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'Не удалось войти через Google, пожалуйста, попробуйте снова.';

  @override
  String get authenticationFailed => 'Аутентификация не удалась. Пожалуйста, попробуйте снова.';

  @override
  String get authFailedToSignInWithApple => 'Не удалось войти через Apple, пожалуйста, попробуйте снова.';

  @override
  String get authFailedToRetrieveToken => 'Не удалось получить токен Firebase, пожалуйста, попробуйте снова.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Непредвиденная ошибка при входе, ошибка Firebase, пожалуйста, попробуйте снова.';

  @override
  String get authUnexpectedError => 'Непредвиденная ошибка при входе, пожалуйста, попробуйте снова';

  @override
  String get authFailedToLinkGoogle => 'Не удалось связать с Google, пожалуйста, попробуйте снова.';

  @override
  String get authFailedToLinkApple => 'Не удалось связать с Apple, пожалуйста, попробуйте снова.';

  @override
  String get onboardingBluetoothRequired => 'Для подключения к устройству требуется разрешение Bluetooth.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Разрешение Bluetooth отклонено. Предоставьте разрешение в Системных настройках.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Статус разрешения Bluetooth: $status. Проверьте Системные настройки.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Не удалось проверить разрешение Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Разрешение на уведомления отклонено. Предоставьте разрешение в Системных настройках.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Разрешение на уведомления отклонено. Предоставьте разрешение в Системные настройки > Уведомления.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Статус разрешения на уведомления: $status. Проверьте Системные настройки.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Не удалось проверить разрешение на уведомления: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Предоставьте разрешение на геолокацию в Настройки > Конфиденциальность и безопасность > Службы геолокации';

  @override
  String get onboardingMicrophoneRequired => 'Для записи требуется разрешение микрофона.';

  @override
  String get onboardingMicrophoneDenied =>
      'Разрешение микрофона отклонено. Предоставьте разрешение в Системные настройки > Конфиденциальность и безопасность > Микрофон.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Статус разрешения микрофона: $status. Проверьте Системные настройки.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Не удалось проверить разрешение микрофона: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Для записи системного звука требуется разрешение на захват экрана.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Разрешение на захват экрана отклонено. Предоставьте разрешение в Системные настройки > Конфиденциальность и безопасность > Запись экрана.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Статус разрешения на захват экрана: $status. Проверьте Системные настройки.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Не удалось проверить разрешение на захват экрана: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Для обнаружения встреч в браузере требуется разрешение на специальные возможности.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Статус разрешения на специальные возможности: $status. Проверьте Системные настройки.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Не удалось проверить разрешение на специальные возможности: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Захват камеры недоступен на этой платформе';

  @override
  String get msgCameraPermissionDenied => 'Разрешение на камеру отклонено. Пожалуйста, разрешите доступ к камере';

  @override
  String msgCameraAccessError(String error) {
    return 'Ошибка доступа к камере: $error';
  }

  @override
  String get msgPhotoError => 'Ошибка при съёмке фото. Пожалуйста, попробуйте снова.';

  @override
  String get msgMaxImagesLimit => 'Вы можете выбрать только до 4 изображений';

  @override
  String msgFilePickerError(String error) {
    return 'Ошибка открытия выбора файлов: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Ошибка выбора изображений: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Разрешение на фото отклонено. Пожалуйста, разрешите доступ к фото для выбора изображений';

  @override
  String get msgSelectImagesGenericError => 'Ошибка выбора изображений. Пожалуйста, попробуйте снова.';

  @override
  String get msgMaxFilesLimit => 'Вы можете выбрать только до 4 файлов';

  @override
  String msgSelectFilesError(String error) {
    return 'Ошибка выбора файлов: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Ошибка выбора файлов. Пожалуйста, попробуйте снова.';

  @override
  String get msgUploadFileFailed => 'Не удалось загрузить файл, попробуйте позже';

  @override
  String get msgReadingMemories => 'Читаем ваши воспоминания...';

  @override
  String get msgLearningMemories => 'Учимся на ваших воспоминаниях...';

  @override
  String get msgUploadAttachedFileFailed => 'Не удалось загрузить прикреплённый файл.';

  @override
  String captureRecordingError(String error) {
    return 'Произошла ошибка во время записи: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Запись остановлена: $reason. Возможно, вам потребуется переподключить внешние дисплеи или перезапустить запись.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Требуется разрешение на использование микрофона';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Предоставьте разрешение на микрофон в Системных настройках';

  @override
  String get captureScreenRecordingPermissionRequired => 'Требуется разрешение на запись экрана';

  @override
  String get captureDisplayDetectionFailed => 'Ошибка обнаружения дисплея. Запись остановлена.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Недействительный URL вебхука аудио-байтов';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl =>
      'Недействительный URL вебхука транскрипции в реальном времени';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Недействительный URL вебхука созданной беседы';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Недействительный URL вебхука дневного отчёта';

  @override
  String get devModeSettingsSaved => 'Настройки сохранены!';

  @override
  String get voiceFailedToTranscribe => 'Не удалось транскрибировать аудио';

  @override
  String get locationPermissionRequired => 'Требуется разрешение на местоположение';

  @override
  String get locationPermissionContent =>
      'Для быстрой передачи требуется разрешение на определение местоположения для проверки WiFi-соединения. Пожалуйста, предоставьте разрешение на местоположение, чтобы продолжить.';

  @override
  String get pdfTranscriptExport => 'Экспорт транскрипции';

  @override
  String get pdfConversationExport => 'Экспорт беседы';

  @override
  String pdfTitleLabel(String title) {
    return 'Заголовок: $title';
  }

  @override
  String get conversationNewIndicator => 'Новое 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count фото';
  }

  @override
  String get mergingStatus => 'Объединение...';

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
    return '$count часов';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours часов $mins мин';
  }

  @override
  String timeDaySingular(int count) {
    return '$count день';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count дней';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days дней $hours часов';
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
  String get moveToFolder => 'Переместить в папку';

  @override
  String get noFoldersAvailable => 'Нет доступных папок';

  @override
  String get newFolder => 'Новая папка';

  @override
  String get color => 'Цвет';

  @override
  String get waitingForDevice => 'Ожидание устройства...';

  @override
  String get saySomething => 'Скажите что-нибудь...';

  @override
  String get initialisingSystemAudio => 'Инициализация системного аудио';

  @override
  String get stopRecording => 'Остановить запись';

  @override
  String get continueRecording => 'Продолжить запись';

  @override
  String get initialisingRecorder => 'Инициализация диктофона';

  @override
  String get pauseRecording => 'Приостановить запись';

  @override
  String get resumeRecording => 'Возобновить запись';

  @override
  String get noDailyRecapsYet => 'Пока нет ежедневных сводок';

  @override
  String get dailyRecapsDescription => 'Ваши ежедневные сводки появятся здесь после создания';

  @override
  String get chooseTransferMethod => 'Выберите способ передачи';

  @override
  String get fastTransferSpeed => '~150 КБ/с через WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Обнаружен большой временной разрыв ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Обнаружены большие временные разрывы ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Устройство не поддерживает синхронизацию WiFi, переключение на Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health недоступно на этом устройстве';

  @override
  String get downloadAudio => 'Скачать аудио';

  @override
  String get audioDownloadSuccess => 'Аудио успешно скачано';

  @override
  String get audioDownloadFailed => 'Не удалось скачать аудио';

  @override
  String get downloadingAudio => 'Скачивание аудио...';

  @override
  String get shareAudio => 'Поделиться аудио';

  @override
  String get preparingAudio => 'Подготовка аудио';

  @override
  String get gettingAudioFiles => 'Получение аудиофайлов...';

  @override
  String get downloadingAudioProgress => 'Скачивание аудио';

  @override
  String get processingAudio => 'Обработка аудио';

  @override
  String get combiningAudioFiles => 'Объединение аудиофайлов...';

  @override
  String get audioReady => 'Аудио готово';

  @override
  String get openingShareSheet => 'Открытие листа общего доступа...';

  @override
  String get audioShareFailed => 'Не удалось поделиться';

  @override
  String get dailyRecaps => 'Ежедневные сводки';

  @override
  String get removeFilter => 'Удалить фильтр';

  @override
  String get categoryConversationAnalysis => 'Анализ разговоров';

  @override
  String get categoryPersonalityClone => 'Клон личности';

  @override
  String get categoryHealth => 'Здоровье';

  @override
  String get categoryEducation => 'Образование';

  @override
  String get categoryCommunication => 'Общение';

  @override
  String get categoryEmotionalSupport => 'Эмоциональная поддержка';

  @override
  String get categoryProductivity => 'Продуктивность';

  @override
  String get categoryEntertainment => 'Развлечения';

  @override
  String get categoryFinancial => 'Финансы';

  @override
  String get categoryTravel => 'Путешествия';

  @override
  String get categorySafety => 'Безопасность';

  @override
  String get categoryShopping => 'Покупки';

  @override
  String get categorySocial => 'Социальное';

  @override
  String get categoryNews => 'Новости';

  @override
  String get categoryUtilities => 'Инструменты';

  @override
  String get categoryOther => 'Другое';

  @override
  String get capabilityChat => 'Чат';

  @override
  String get capabilityConversations => 'Разговоры';

  @override
  String get capabilityExternalIntegration => 'Внешняя интеграция';

  @override
  String get capabilityNotification => 'Уведомление';

  @override
  String get triggerAudioBytes => 'Аудио байты';

  @override
  String get triggerConversationCreation => 'Создание разговора';

  @override
  String get triggerTranscriptProcessed => 'Транскрипт обработан';

  @override
  String get actionCreateConversations => 'Создать разговоры';

  @override
  String get actionCreateMemories => 'Создать воспоминания';

  @override
  String get actionReadConversations => 'Читать разговоры';

  @override
  String get actionReadMemories => 'Читать воспоминания';

  @override
  String get actionReadTasks => 'Читать задачи';

  @override
  String get scopeUserName => 'Имя пользователя';

  @override
  String get scopeUserFacts => 'Данные пользователя';

  @override
  String get scopeUserConversations => 'Разговоры пользователя';

  @override
  String get scopeUserChat => 'Чат пользователя';

  @override
  String get capabilitySummary => 'Сводка';

  @override
  String get capabilityFeatured => 'Рекомендуемые';

  @override
  String get capabilityTasks => 'Задачи';

  @override
  String get capabilityIntegrations => 'Интеграции';

  @override
  String get categoryPersonalityClones => 'Клоны личности';

  @override
  String get categoryProductivityLifestyle => 'Продуктивность и образ жизни';

  @override
  String get categorySocialEntertainment => 'Социальное и развлечения';

  @override
  String get categoryProductivityTools => 'Инструменты продуктивности';

  @override
  String get categoryPersonalWellness => 'Личное благополучие';

  @override
  String get rating => 'Рейтинг';

  @override
  String get categories => 'Категории';

  @override
  String get sortBy => 'Сортировка';

  @override
  String get highestRating => 'Высший рейтинг';

  @override
  String get lowestRating => 'Низший рейтинг';

  @override
  String get resetFilters => 'Сбросить фильтры';

  @override
  String get applyFilters => 'Применить фильтры';

  @override
  String get mostInstalls => 'Больше всего установок';

  @override
  String get couldNotOpenUrl => 'Не удалось открыть URL. Пожалуйста, попробуйте снова.';

  @override
  String get newTask => 'Новая задача';

  @override
  String get viewAll => 'Показать все';

  @override
  String get addTask => 'Добавить задачу';

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
  String get audioPlaybackUnavailable => 'Аудиофайл недоступен для воспроизведения';

  @override
  String get audioPlaybackFailed => 'Не удалось воспроизвести аудио. Файл может быть повреждён или отсутствовать.';

  @override
  String get connectionGuide => 'Руководство по подключению';

  @override
  String get iveDoneThis => 'Я это сделал';

  @override
  String get pairNewDevice => 'Подключить новое устройство';

  @override
  String get dontSeeYourDevice => 'Не видите своё устройство?';

  @override
  String get reportAnIssue => 'Сообщить о проблеме';

  @override
  String get pairingTitleOmi => 'Включите Omi';

  @override
  String get pairingDescOmi => 'Нажмите и удерживайте устройство, пока оно не завибрирует, чтобы включить его.';

  @override
  String get pairingTitleOmiDevkit => 'Переведите Omi DevKit в режим сопряжения';

  @override
  String get pairingDescOmiDevkit =>
      'Нажмите кнопку один раз для включения. Светодиод будет мигать фиолетовым в режиме сопряжения.';

  @override
  String get pairingTitleOmiGlass => 'Включите Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Нажмите и удерживайте боковую кнопку 3 секунды для включения.';

  @override
  String get pairingTitlePlaudNote => 'Переведите Plaud Note в режим сопряжения';

  @override
  String get pairingDescPlaudNote =>
      'Нажмите и удерживайте боковую кнопку 2 секунды. Красный светодиод замигает, когда устройство будет готово к сопряжению.';

  @override
  String get pairingTitleBee => 'Переведите Bee в режим сопряжения';

  @override
  String get pairingDescBee => 'Нажмите кнопку 5 раз подряд. Индикатор начнёт мигать синим и зелёным.';

  @override
  String get pairingTitleLimitless => 'Переведите Limitless в режим сопряжения';

  @override
  String get pairingDescLimitless =>
      'Когда горит любой индикатор, нажмите один раз, затем нажмите и удерживайте, пока устройство не покажет розовый свет, затем отпустите.';

  @override
  String get pairingTitleFriendPendant => 'Переведите Friend Pendant в режим сопряжения';

  @override
  String get pairingDescFriendPendant =>
      'Нажмите кнопку на кулоне, чтобы включить его. Он автоматически перейдёт в режим сопряжения.';

  @override
  String get pairingTitleFieldy => 'Переведите Fieldy в режим сопряжения';

  @override
  String get pairingDescFieldy => 'Нажмите и удерживайте устройство, пока не появится индикатор, чтобы включить его.';

  @override
  String get pairingTitleAppleWatch => 'Подключить Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Установите и откройте приложение Omi на Apple Watch, затем нажмите Подключить в приложении.';

  @override
  String get pairingTitleNeoOne => 'Переведите Neo One в режим сопряжения';

  @override
  String get pairingDescNeoOne =>
      'Нажмите и удерживайте кнопку питания, пока не замигает светодиод. Устройство станет обнаруживаемым.';
}
