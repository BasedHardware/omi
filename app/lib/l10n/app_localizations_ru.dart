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
  String get noInternetConnection => 'Пожалуйста, проверьте подключение к интернету и попробуйте снова.';

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
  String get speechProfile => 'Голосовой профиль';

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
  String get searching => 'Поиск';

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
  String get noConversationsYet => 'Разговоров пока нет.';

  @override
  String get noStarredConversations => 'Избранных разговоров пока нет.';

  @override
  String get starConversationHint =>
      'Чтобы добавить разговор в избранное, откройте его и нажмите на значок звезды в заголовке.';

  @override
  String get searchConversations => 'Поиск разговоров';

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
  String get messageCopied => 'Сообщение скопировано в буфер обмена.';

  @override
  String get cannotReportOwnMessage => 'Вы не можете пожаловаться на свои собственные сообщения.';

  @override
  String get reportMessage => 'Пожаловаться на сообщение';

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
  String get searchApps => 'Поиск среди 1500+ приложений';

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
  String get membersAndCounting => 'Более 8000 участников.';

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
  String get email => 'Электронная почта';

  @override
  String get customVocabulary => 'Пользовательский словарь';

  @override
  String get identifyingOthers => 'Идентификация других';

  @override
  String get paymentMethods => 'Способы оплаты';

  @override
  String get conversationDisplay => 'Отображение разговоров';

  @override
  String get dataPrivacy => 'Данные и конфиденциальность';

  @override
  String get userId => 'ID пользователя';

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
  String get unpairDevice => 'Разорвать пару с устройством';

  @override
  String get unpairAndForget => 'Разорвать пару и забыть устройство';

  @override
  String get deviceDisconnectedMessage => 'Ваш Omi был отключён 😔';

  @override
  String get deviceUnpairedMessage =>
      'Пара с устройством разорвана. Перейдите в Настройки > Bluetooth и забудьте устройство для завершения разрыва пары.';

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
  String get createKey => 'Создать ключ';

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
  String get upgradeToUnlimited => 'Перейти на безлимитный';

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
  String get knowledgeGraphDeleted => 'Граф знаний успешно удалён';

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
  String get conversationEvents => 'События разговоров';

  @override
  String get newConversationCreated => 'Создан новый разговор';

  @override
  String get realtimeTranscript => 'Расшифровка в реальном времени';

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
  String get insights => 'Инсайты';

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
  String get private => 'Приватный';

  @override
  String updatedDate(String date) {
    return 'Обновлено $date';
  }

  @override
  String get yesterday => 'вчера';

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
  String get makePublic => 'Сделать публичным';

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
  String get personalGrowthJourney => 'Ваше личностное развитие с AI, который слушает каждое ваше слово.';

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
  String get deleteActionItemTitle => 'Удалить задачу';

  @override
  String get deleteActionItemMessage => 'Вы уверены, что хотите удалить эту задачу?';

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
  String searchMemories(int count) {
    return 'Поиск среди $count воспоминаний';
  }

  @override
  String get memoryDeleted => 'Воспоминание удалено.';

  @override
  String get undo => 'Отменить';

  @override
  String get noMemoriesYet => 'Воспоминаний пока нет';

  @override
  String get noAutoMemories => 'Автоматически извлечённых воспоминаний пока нет';

  @override
  String get noManualMemories => 'Ручных воспоминаний пока нет';

  @override
  String get noMemoriesInCategories => 'Нет воспоминаний в этих категориях';

  @override
  String get noMemoriesFound => 'Воспоминания не найдены';

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
  String get newMemory => 'Новое воспоминание';

  @override
  String get editMemory => 'Редактировать воспоминание';

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
  String get completed => 'Выполнено';

  @override
  String get markComplete => 'Отметить как выполненное';

  @override
  String get actionItemDeleted => 'Задача удалена';

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
}
