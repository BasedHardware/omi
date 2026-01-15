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
  String get copyTranscript => 'Копировать расшифровку';

  @override
  String get copySummary => 'Копировать резюме';

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
  String get clearChat => 'Очистить чат?';

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
  String get offlineSync => 'Оффлайн-синхронизация';

  @override
  String get deviceSettings => 'Настройки устройства';

  @override
  String get chatTools => 'Инструменты чата';

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
  String get noLogFilesFound => 'Файлы журналов не найдены.';

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
  String get connect => 'Подключить';

  @override
  String get comingSoon => 'Скоро';

  @override
  String get chatToolsFooter => 'Подключите ваши приложения для просмотра данных и метрик в чате.';

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
  String get noUpcomingMeetings => 'Предстоящих встреч не найдено';

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
  String get apiKey => 'API-ключ';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName использует $codecReason. Будет использован Omi.';
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
  String get appName => 'Название приложения';

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
  String get descriptionOptional => 'Описание (необязательно)';

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
  String get conversationUrlCouldNotBeShared => 'URL-адрес разговора не может быть передан.';

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
  String get generateSummary => 'Создать резюме';

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
  String get unknownDevice => 'Неизвестное устройство';

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
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'No API keys yet';

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
  String get debugAndDiagnostics => 'Отладка и диагностика';

  @override
  String get autoDeletesAfter3Days => 'Автоматическое удаление через 3 дня';

  @override
  String get helpsDiagnoseIssues => 'Помогает диагностировать проблемы';

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
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Дополнительные вопросы';

  @override
  String get suggestQuestionsAfterConversations => 'Предлагать вопросы после разговоров';

  @override
  String get goalTracker => 'Отслеживание целей';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Ежедневное размышление';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

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
  String get current => 'Текущий';

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
  String get dailyScore => 'ЕЖЕДНЕВНЫЙ БАЛЛ';

  @override
  String get dailyScoreDescription => 'Балл, который помогает лучше сосредоточиться на выполнении.';

  @override
  String get searchResults => 'Результаты поиска';

  @override
  String get actionItems => 'Элементы действий';

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
  String installsCount(String count) {
    return '$count+ установок';
  }

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
  String get discardedConversation => 'Отклоненный разговор';

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
  String get noSummaryForApp =>
      'Для этого приложения резюме недоступно. Попробуйте другое приложение для лучших результатов.';

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
  String get dailySummary => 'Ежедневная Сводка';

  @override
  String get developer => 'Разработчик';

  @override
  String get about => 'О программе';

  @override
  String get selectTime => 'Выбрать Время';

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
  String get dailySummaryDescription => 'Получайте персонализированную сводку ваших разговоров';

  @override
  String get deliveryTime => 'Время Доставки';

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
  String get upcomingMeetings => 'ПРЕДСТОЯЩИЕ ВСТРЕЧИ';

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
  String get dailyReflectionDescription => 'Напоминание в 21:00 для размышлений о вашем дне';

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
  String get invalidIntegrationUrl => 'Неверный URL интеграции';

  @override
  String get tapToComplete => 'Нажмите для завершения';

  @override
  String get invalidSetupInstructionsUrl => 'Неверный URL инструкций по настройке';

  @override
  String get pushToTalk => 'Нажмите, чтобы говорить';

  @override
  String get summaryPrompt => 'Промпт резюме';

  @override
  String get pleaseSelectARating => 'Пожалуйста, выберите оценку';

  @override
  String get reviewAddedSuccessfully => 'Отзыв успешно добавлен 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Отзыв успешно обновлен 🚀';

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
}
