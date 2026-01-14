// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Ukrainian (`uk`).
class AppLocalizationsUk extends AppLocalizations {
  AppLocalizationsUk([String locale = 'uk']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Розмова';

  @override
  String get transcriptTab => 'Транскрипція';

  @override
  String get actionItemsTab => 'Завдання';

  @override
  String get deleteConversationTitle => 'Видалити розмову?';

  @override
  String get deleteConversationMessage => 'Ви впевнені, що хочете видалити цю розмову? Цю дію не можна скасувати.';

  @override
  String get confirm => 'Підтвердити';

  @override
  String get cancel => 'Скасувати';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Видалити';

  @override
  String get add => 'Додати';

  @override
  String get update => 'Оновити';

  @override
  String get save => 'Зберегти';

  @override
  String get edit => 'Редагувати';

  @override
  String get close => 'Закрити';

  @override
  String get clear => 'Очистити';

  @override
  String get copyTranscript => 'Копіювати транскрипцію';

  @override
  String get copySummary => 'Копіювати підсумок';

  @override
  String get testPrompt => 'Тестовий запит';

  @override
  String get reprocessConversation => 'Перепрацювати розмову';

  @override
  String get deleteConversation => 'Видалити розмову';

  @override
  String get contentCopied => 'Вміст скопійовано до буфера обміну';

  @override
  String get failedToUpdateStarred => 'Не вдалося оновити статус обраного.';

  @override
  String get conversationUrlNotShared => 'Не вдалося поділитися URL розмови.';

  @override
  String get errorProcessingConversation => 'Помилка під час обробки розмови. Будь ласка, спробуйте пізніше.';

  @override
  String get noInternetConnection => 'Немає підключення до Інтернету';

  @override
  String get unableToDeleteConversation => 'Не вдалося видалити розмову';

  @override
  String get somethingWentWrong => 'Щось пішло не так! Будь ласка, спробуйте пізніше.';

  @override
  String get copyErrorMessage => 'Копіювати повідомлення про помилку';

  @override
  String get errorCopied => 'Повідомлення про помилку скопійовано до буфера обміну';

  @override
  String get remaining => 'Залишилося';

  @override
  String get loading => 'Завантаження...';

  @override
  String get loadingDuration => 'Завантаження тривалості...';

  @override
  String secondsCount(int count) {
    return '$count секунд';
  }

  @override
  String get people => 'Люди';

  @override
  String get addNewPerson => 'Додати нову особу';

  @override
  String get editPerson => 'Редагувати особу';

  @override
  String get createPersonHint => 'Створіть нову особу та навчіть Omi розпізнавати її мовлення!';

  @override
  String get speechProfile => 'Мовний профіль';

  @override
  String sampleNumber(int number) {
    return 'Зразок $number';
  }

  @override
  String get settings => 'Налаштування';

  @override
  String get language => 'Мова';

  @override
  String get selectLanguage => 'Вибрати мову';

  @override
  String get deleting => 'Видалення...';

  @override
  String get pleaseCompleteAuthentication =>
      'Будь ласка, завершіть автентифікацію у браузері. Після завершення поверніться до додатка.';

  @override
  String get failedToStartAuthentication => 'Не вдалося розпочати автентифікацію';

  @override
  String get importStarted => 'Імпорт розпочато! Ви отримаєте сповіщення після завершення.';

  @override
  String get failedToStartImport => 'Не вдалося розпочати імпорт. Будь ласка, спробуйте ще раз.';

  @override
  String get couldNotAccessFile => 'Не вдалося отримати доступ до вибраного файлу';

  @override
  String get askOmi => 'Запитати Omi';

  @override
  String get done => 'Готово';

  @override
  String get disconnected => 'Відєднано';

  @override
  String get searching => 'Пошук...';

  @override
  String get connectDevice => 'Підключити пристрій';

  @override
  String get monthlyLimitReached => 'Ви досягли свого місячного ліміту.';

  @override
  String get checkUsage => 'Перевірити використання';

  @override
  String get syncingRecordings => 'Синхронізація записів';

  @override
  String get recordingsToSync => 'Записи для синхронізації';

  @override
  String get allCaughtUp => 'Все синхронізовано';

  @override
  String get sync => 'Синхронізувати';

  @override
  String get pendantUpToDate => 'Підвіска оновлена';

  @override
  String get allRecordingsSynced => 'Всі записи синхронізовано';

  @override
  String get syncingInProgress => 'Йде синхронізація';

  @override
  String get readyToSync => 'Готово до синхронізації';

  @override
  String get tapSyncToStart => 'Натисніть Синхронізувати, щоб почати';

  @override
  String get pendantNotConnected => 'Підвіска не підключена. Підключіть для синхронізації.';

  @override
  String get everythingSynced => 'Все вже синхронізовано.';

  @override
  String get recordingsNotSynced => 'У вас є записи, які ще не синхронізовано.';

  @override
  String get syncingBackground => 'Ми продовжимо синхронізацію ваших записів у фоновому режимі.';

  @override
  String get noConversationsYet => 'Ще немає розмов';

  @override
  String get noStarredConversations => 'Обраних розмов поки немає.';

  @override
  String get starConversationHint =>
      'Щоб позначити розмову зірочкою, відкрийте її та натисніть іконку зірки в заголовку.';

  @override
  String get searchConversations => 'Пошук розмов...';

  @override
  String selectedCount(int count, Object s) {
    return 'Вибрано: $count';
  }

  @override
  String get merge => 'Об\'єднати';

  @override
  String get mergeConversations => 'Об\'єднати розмови';

  @override
  String mergeConversationsMessage(int count) {
    return 'Це об\'єднає $count розмов в одну. Весь вміст буде об\'єднано та перегенеровано.';
  }

  @override
  String get mergingInBackground => 'Об\'єднання у фоновому режимі. Це може зайняти деякий час.';

  @override
  String get failedToStartMerge => 'Не вдалося розпочати об\'єднання';

  @override
  String get askAnything => 'Запитайте що завгодно';

  @override
  String get noMessagesYet => 'Повідомлень поки немає!\nЧому б не почати розмову?';

  @override
  String get deletingMessages => 'Видалення ваших повідомлень з пам\'яті Omi...';

  @override
  String get messageCopied => 'Повідомлення скопійовано до буфера обміну.';

  @override
  String get cannotReportOwnMessage => 'Ви не можете поскаржитись на власні повідомлення.';

  @override
  String get reportMessage => 'Поскаржитись на повідомлення';

  @override
  String get reportMessageConfirm => 'Ви впевнені, що хочете поскаржитись на це повідомлення?';

  @override
  String get messageReported => 'Повідомлення успішно відправлено.';

  @override
  String get thankYouFeedback => 'Дякуємо за ваш відгук!';

  @override
  String get clearChat => 'Очистити чат?';

  @override
  String get clearChatConfirm => 'Ви впевнені, що хочете очистити чат? Цю дію не можна скасувати.';

  @override
  String get maxFilesLimit => 'Ви можете завантажити лише 4 файли за раз';

  @override
  String get chatWithOmi => 'Чат з Omi';

  @override
  String get apps => 'Додатки';

  @override
  String get noAppsFound => 'Додатків не знайдено';

  @override
  String get tryAdjustingSearch => 'Спробуйте змінити пошуковий запит або фільтри';

  @override
  String get createYourOwnApp => 'Створіть власний додаток';

  @override
  String get buildAndShareApp => 'Створюйте та діліться своїм власним додатком';

  @override
  String get searchApps => 'Шукати додатки...';

  @override
  String get myApps => 'Мої додатки';

  @override
  String get installedApps => 'Встановлені додатки';

  @override
  String get unableToFetchApps =>
      'Не вдалося завантажити додатки :(\n\nБудь ласка, перевірте підключення до інтернету та спробуйте ще раз.';

  @override
  String get aboutOmi => 'Про Omi';

  @override
  String get privacyPolicy => 'Політикою конфіденційності';

  @override
  String get visitWebsite => 'Відвідати веб-сайт';

  @override
  String get helpOrInquiries => 'Допомога або запитання?';

  @override
  String get joinCommunity => 'Приєднуйтесь до спільноти!';

  @override
  String get membersAndCounting => 'Понад 8000 учасників.';

  @override
  String get deleteAccountTitle => 'Видалити обліковий запис';

  @override
  String get deleteAccountConfirm => 'Ви впевнені, що хочете видалити свій обліковий запис?';

  @override
  String get cannotBeUndone => 'Це не можна скасувати.';

  @override
  String get allDataErased => 'Всі ваші спогади та розмови будуть остаточно видалені.';

  @override
  String get appsDisconnected => 'Ваші додатки та інтеграції будуть негайно відключені.';

  @override
  String get exportBeforeDelete =>
      'Ви можете експортувати свої дані перед видаленням облікового запису, але після видалення їх неможливо буде відновити.';

  @override
  String get deleteAccountCheckbox =>
      'Я розумію, що видалення мого облікового запису є остаточним, і всі дані, включно зі спогадами та розмовами, будуть втрачені і не можуть бути відновлені.';

  @override
  String get areYouSure => 'Ви впевнені?';

  @override
  String get deleteAccountFinal =>
      'Ця дія є незворотною та назавжди видалить ваш обліковий запис і всі пов\'язані дані. Ви впевнені, що хочете продовжити?';

  @override
  String get deleteNow => 'Видалити зараз';

  @override
  String get goBack => 'Повернутися';

  @override
  String get checkBoxToConfirm =>
      'Встановіть прапорець, щоб підтвердити, що ви розумієте, що видалення облікового запису є остаточним і незворотним.';

  @override
  String get profile => 'Профіль';

  @override
  String get name => 'Ім\'я';

  @override
  String get email => 'Електронна пошта';

  @override
  String get customVocabulary => 'Власний словник';

  @override
  String get identifyingOthers => 'Ідентифікація інших';

  @override
  String get paymentMethods => 'Способи оплати';

  @override
  String get conversationDisplay => 'Відображення розмов';

  @override
  String get dataPrivacy => 'Дані та конфіденційність';

  @override
  String get userId => 'ID користувача';

  @override
  String get notSet => 'Не встановлено';

  @override
  String get userIdCopied => 'ID користувача скопійовано до буфера обміну';

  @override
  String get systemDefault => 'За замовчуванням системи';

  @override
  String get planAndUsage => 'План та використання';

  @override
  String get offlineSync => 'Офлайн-синхронізація';

  @override
  String get deviceSettings => 'Налаштування пристрою';

  @override
  String get chatTools => 'Інструменти чату';

  @override
  String get feedbackBug => 'Відгук / Помилка';

  @override
  String get helpCenter => 'Центр допомоги';

  @override
  String get developerSettings => 'Налаштування розробника';

  @override
  String get getOmiForMac => 'Отримати Omi для Mac';

  @override
  String get referralProgram => 'Реферальна програма';

  @override
  String get signOut => 'Вийти';

  @override
  String get appAndDeviceCopied => 'Деталі додатка та пристрою скопійовано';

  @override
  String get wrapped2025 => 'Підсумки 2025';

  @override
  String get yourPrivacyYourControl => 'Ваша конфіденційність, ваш контроль';

  @override
  String get privacyIntro =>
      'В Omi ми прагнемо захистити вашу конфіденційність. Ця сторінка дозволяє контролювати, як зберігаються та використовуються ваші дані.';

  @override
  String get learnMore => 'Дізнатися більше...';

  @override
  String get dataProtectionLevel => 'Рівень захисту даних';

  @override
  String get dataProtectionDesc =>
      'Ваші дані за замовчуванням захищені надійним шифруванням. Перегляньте свої налаштування та майбутні параметри конфіденційності нижче.';

  @override
  String get appAccess => 'Доступ додатків';

  @override
  String get appAccessDesc =>
      'Наступні додатки можуть отримувати доступ до ваших даних. Натисніть на додаток, щоб керувати його дозволами.';

  @override
  String get noAppsExternalAccess => 'Жоден встановлений додаток не має зовнішнього доступу до ваших даних.';

  @override
  String get deviceName => 'Назва пристрою';

  @override
  String get deviceId => 'ID пристрою';

  @override
  String get firmware => 'Прошивка';

  @override
  String get sdCardSync => 'Синхронізація SD-карти';

  @override
  String get hardwareRevision => 'Ревізія апаратного забезпечення';

  @override
  String get modelNumber => 'Номер моделі';

  @override
  String get manufacturer => 'Виробник';

  @override
  String get doubleTap => 'Подвійне натискання';

  @override
  String get ledBrightness => 'Яскравість світлодіода';

  @override
  String get micGain => 'Підсилення мікрофона';

  @override
  String get disconnect => 'Відключити';

  @override
  String get forgetDevice => 'Забути пристрій';

  @override
  String get chargingIssues => 'Проблеми із зарядкою';

  @override
  String get disconnectDevice => 'Від\'єднати пристрій';

  @override
  String get unpairDevice => 'Скасувати з\'єднання пристрою';

  @override
  String get unpairAndForget => 'Роз\'єднати та забути пристрій';

  @override
  String get deviceDisconnectedMessage => 'Ваш Omi було відключено 😔';

  @override
  String get deviceUnpairedMessage =>
      'З\'єднання пристрою скасовано. Перейдіть до Налаштування > Bluetooth і забудьте пристрій, щоб завершити скасування з\'єднання.';

  @override
  String get unpairDialogTitle => 'Роз\'єднати пристрій';

  @override
  String get unpairDialogMessage =>
      'Це роз\'єднає пристрій, щоб його можна було підключити до іншого телефону. Вам потрібно буде перейти до Налаштування > Bluetooth і забути пристрій, щоб завершити процес.';

  @override
  String get deviceNotConnected => 'Пристрій не підключено';

  @override
  String get connectDeviceMessage =>
      'Підключіть свій пристрій Omi для доступу до\nналаштувань пристрою та налаштування';

  @override
  String get deviceInfoSection => 'Інформація про пристрій';

  @override
  String get customizationSection => 'Налаштування';

  @override
  String get hardwareSection => 'Апаратне забезпечення';

  @override
  String get v2Undetected => 'V2 не виявлено';

  @override
  String get v2UndetectedMessage =>
      'Ми бачимо, що у вас або пристрій V1, або ваш пристрій не підключений. Функціонал SD-карти доступний лише для пристроїв V2.';

  @override
  String get endConversation => 'Завершити розмову';

  @override
  String get pauseResume => 'Призупинити/Відновити';

  @override
  String get starConversation => 'Позначити розмову';

  @override
  String get doubleTapAction => 'Дія подвійного натискання';

  @override
  String get endAndProcess => 'Завершити та обробити розмову';

  @override
  String get pauseResumeRecording => 'Призупинити/Відновити запис';

  @override
  String get starOngoing => 'Позначити поточну розмову';

  @override
  String get off => 'Вимкнено';

  @override
  String get max => 'Максимум';

  @override
  String get mute => 'Без звуку';

  @override
  String get quiet => 'Тихо';

  @override
  String get normal => 'Нормально';

  @override
  String get high => 'Високо';

  @override
  String get micGainDescMuted => 'Мікрофон вимкнено';

  @override
  String get micGainDescLow => 'Дуже тихо - для гучного середовища';

  @override
  String get micGainDescModerate => 'Тихо - для помірного шуму';

  @override
  String get micGainDescNeutral => 'Нейтрально - збалансований запис';

  @override
  String get micGainDescSlightlyBoosted => 'Трохи посилено - нормальне використання';

  @override
  String get micGainDescBoosted => 'Посилено - для тихого середовища';

  @override
  String get micGainDescHigh => 'Високо - для далеких або тихих голосів';

  @override
  String get micGainDescVeryHigh => 'Дуже високо - для дуже тихих джерел';

  @override
  String get micGainDescMax => 'Максимум - використовувати обережно';

  @override
  String get developerSettingsTitle => 'Налаштування розробника';

  @override
  String get saving => 'Збереження...';

  @override
  String get personaConfig => 'Налаштуйте свою AI-персону';

  @override
  String get beta => 'БЕТА';

  @override
  String get transcription => 'Транскрипція';

  @override
  String get transcriptionConfig => 'Налаштувати STT-провайдер';

  @override
  String get conversationTimeout => 'Час очікування розмови';

  @override
  String get conversationTimeoutConfig => 'Встановіть, коли розмови завершуються автоматично';

  @override
  String get importData => 'Імпортувати дані';

  @override
  String get importDataConfig => 'Імпортуйте дані з інших джерел';

  @override
  String get debugDiagnostics => 'Налагодження та діагностика';

  @override
  String get endpointUrl => 'URL кінцевої точки';

  @override
  String get noApiKeys => 'API-ключів поки немає';

  @override
  String get createKeyToStart => 'Створіть ключ, щоб почати';

  @override
  String get createKey => 'Створити ключ';

  @override
  String get docs => 'Документація';

  @override
  String get yourOmiInsights => 'Ваша статистика Omi';

  @override
  String get today => 'Сьогодні';

  @override
  String get thisMonth => 'Цей місяць';

  @override
  String get thisYear => 'Цей рік';

  @override
  String get allTime => 'За весь час';

  @override
  String get noActivityYet => 'Активності поки немає';

  @override
  String get startConversationToSeeInsights => 'Почніть розмову з Omi,\nщоб побачити статистику використання тут.';

  @override
  String get listening => 'Прослуховування';

  @override
  String get listeningSubtitle => 'Загальний час активного прослуховування Omi.';

  @override
  String get understanding => 'Розуміння';

  @override
  String get understandingSubtitle => 'Слів зрозуміно з ваших розмов.';

  @override
  String get providing => 'Надання';

  @override
  String get providingSubtitle => 'Завдання та нотатки, автоматично зафіксовані.';

  @override
  String get remembering => 'Запам\'ятовування';

  @override
  String get rememberingSubtitle => 'Факти та деталі, запам\'ятовані для вас.';

  @override
  String get unlimitedPlan => 'Необмежений план';

  @override
  String get managePlan => 'Керувати планом';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Ваш план буде скасовано $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Ваш план поновиться $date.';
  }

  @override
  String get basicPlan => 'Безкоштовний план';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used з $limit хв використано';
  }

  @override
  String get upgrade => 'Оновити';

  @override
  String get upgradeToUnlimited => 'Оновити до необмеженого';

  @override
  String basicPlanDesc(int limit) {
    return 'Ваш план включає $limit безкоштовних хвилин на місяць. Оновіть, щоб отримати необмежений доступ.';
  }

  @override
  String get shareStatsMessage => 'Ділюся своєю статистикою Omi! (omi.me - ваш завжди активний AI-асистент)';

  @override
  String get sharePeriodToday => 'Сьогодні omi:';

  @override
  String get sharePeriodMonth => 'Цього місяця omi:';

  @override
  String get sharePeriodYear => 'Цього року omi:';

  @override
  String get sharePeriodAllTime => 'Загалом omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Прослухав $minutes хвилин';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Зрозумів $words слів';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Надав $count insights';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Запам\'ятав $count спогадів';
  }

  @override
  String get debugLogs => 'Журнали налагодження';

  @override
  String get debugLogsAutoDelete => 'Автоматичне видалення через 3 дні.';

  @override
  String get debugLogsDesc => 'Допомагає діагностувати проблеми';

  @override
  String get noLogFilesFound => 'Файли журналів не знайдено.';

  @override
  String get omiDebugLog => 'Журнал налагодження Omi';

  @override
  String get logShared => 'Журнал надіслано';

  @override
  String get selectLogFile => 'Вибрати файл журналу';

  @override
  String get shareLogs => 'Поділитися журналами';

  @override
  String get debugLogCleared => 'Журнал налагодження очищено';

  @override
  String get exportStarted => 'Експорт розпочато. Це може зайняти кілька секунд...';

  @override
  String get exportAllData => 'Експортувати всі дані';

  @override
  String get exportDataDesc => 'Експортувати розмови у файл JSON';

  @override
  String get exportedConversations => 'Експортовані розмови з Omi';

  @override
  String get exportShared => 'Експорт надіслано';

  @override
  String get deleteKnowledgeGraphTitle => 'Видалити граф знань?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Це видалить всі похідні дані графа знань (вузли та з\'єднання). Ваші оригінальні спогади залишаться в безпеці. Граф буде перебудовано з часом або за наступним запитом.';

  @override
  String get knowledgeGraphDeleted => 'Граф знань успішно видалено';

  @override
  String deleteGraphFailed(String error) {
    return 'Не вдалося видалити граф: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Видалити граф знань';

  @override
  String get deleteKnowledgeGraphDesc => 'Очистити всі вузли та з\'єднання';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP-сервер';

  @override
  String get mcpServerDesc => 'Підключіть AI-асистентів до ваших даних';

  @override
  String get serverUrl => 'URL сервера';

  @override
  String get urlCopied => 'URL скопійовано';

  @override
  String get apiKeyAuth => 'Автентифікація API-ключем';

  @override
  String get header => 'Заголовок';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID клієнта';

  @override
  String get clientSecret => 'Секрет клієнта';

  @override
  String get useMcpApiKey => 'Використовуйте свій MCP API-ключ';

  @override
  String get webhooks => 'Вебхуки';

  @override
  String get conversationEvents => 'Події розмови';

  @override
  String get newConversationCreated => 'Створено нову розмову';

  @override
  String get realtimeTranscript => 'Транскрипція в реальному часі';

  @override
  String get transcriptReceived => 'Транскрипцію отримано';

  @override
  String get audioBytes => 'Аудіо байти';

  @override
  String get audioDataReceived => 'Аудіо дані отримано';

  @override
  String get intervalSeconds => 'Інтервал (секунди)';

  @override
  String get daySummary => 'Підсумок дня';

  @override
  String get summaryGenerated => 'Підсумок згенеровано';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Додати до claude_desktop_config.json';

  @override
  String get copyConfig => 'Копіювати конфігурацію';

  @override
  String get configCopied => 'Конфігурацію скопійовано до буфера обміну';

  @override
  String get listeningMins => 'Прослуховування (хв)';

  @override
  String get understandingWords => 'Розуміння (слів)';

  @override
  String get insights => 'Insights';

  @override
  String get memories => 'Спогади';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used з $limit хв використано цього місяця';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used з $limit слів використано цього місяця';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used з $limit insights отримано цього місяця';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used з $limit спогадів створено цього місяця';
  }

  @override
  String get visibility => 'Видимість';

  @override
  String get visibilitySubtitle => 'Керуйте тим, які розмови відображаються у вашому списку';

  @override
  String get showShortConversations => 'Показувати короткі розмови';

  @override
  String get showShortConversationsDesc => 'Відображати розмови коротші за поріг';

  @override
  String get showDiscardedConversations => 'Показувати відхилені розмови';

  @override
  String get showDiscardedConversationsDesc => 'Включати розмови, позначені як відхилені';

  @override
  String get shortConversationThreshold => 'Поріг коротких розмов';

  @override
  String get shortConversationThresholdSubtitle =>
      'Розмови коротші за це значення будуть приховані, якщо не увімкнено вище';

  @override
  String get durationThreshold => 'Поріг тривалості';

  @override
  String get durationThresholdDesc => 'Приховувати розмови коротші за це';

  @override
  String minLabel(int count) {
    return '$count хв';
  }

  @override
  String get customVocabularyTitle => 'Власний словник';

  @override
  String get addWords => 'Додати слова';

  @override
  String get addWordsDesc => 'Імена, терміни або незвичні слова';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Підключити';

  @override
  String get comingSoon => 'Незабаром';

  @override
  String get chatToolsFooter => 'Підключіть свої додатки для перегляду даних та метрик у чаті.';

  @override
  String get completeAuthInBrowser =>
      'Будь ласка, завершіть автентифікацію у браузері. Після завершення поверніться до додатка.';

  @override
  String failedToStartAuth(String appName) {
    return 'Не вдалося розпочати автентифікацію $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Відключити $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Ви впевнені, що хочете відключитись від $appName? Ви можете підключитись знову в будь-який час.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Відключено від $appName';
  }

  @override
  String get failedToDisconnect => 'Не вдалося відключитись';

  @override
  String connectTo(String appName) {
    return 'Підключитись до $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Вам потрібно авторизувати Omi для доступу до ваших даних $appName. Це відкриє ваш браузер для автентифікації.';
  }

  @override
  String get continueAction => 'Продовжити';

  @override
  String get languageTitle => 'Мова';

  @override
  String get primaryLanguage => 'Основна мова';

  @override
  String get automaticTranslation => 'Автоматичний переклад';

  @override
  String get detectLanguages => 'Виявлення 10+ мов';

  @override
  String get authorizeSavingRecordings => 'Авторизувати збереження записів';

  @override
  String get thanksForAuthorizing => 'Дякуємо за авторизацію!';

  @override
  String get needYourPermission => 'Нам потрібен ваш дозвіл';

  @override
  String get alreadyGavePermission =>
      'Ви вже надали нам дозвіл на збереження ваших записів. Нагадуємо, навіщо це потрібно:';

  @override
  String get wouldLikePermission => 'Ми хотіли б отримати ваш дозвіл на збереження ваших голосових записів. Ось чому:';

  @override
  String get improveSpeechProfile => 'Покращити ваш мовний профіль';

  @override
  String get improveSpeechProfileDesc =>
      'Ми використовуємо записи для подальшого навчання та покращення вашого особистого мовного профілю.';

  @override
  String get trainFamilyProfiles => 'Навчити профілі для друзів та родини';

  @override
  String get trainFamilyProfilesDesc =>
      'Ваші записи допомагають нам розпізнавати та створювати профілі для ваших друзів та родини.';

  @override
  String get enhanceTranscriptAccuracy => 'Покращити точність транскрипції';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'У міру вдосконалення нашої моделі ми можемо надавати кращі результати транскрипції ваших записів.';

  @override
  String get legalNotice =>
      'Юридичне повідомлення: Законність запису та зберігання голосових даних може відрізнятися залежно від вашого місцезнаходження та того, як ви використовуєте цю функцію. Ви несете відповідальність за дотримання місцевих законів та правил.';

  @override
  String get alreadyAuthorized => 'Вже авторизовано';

  @override
  String get authorize => 'Авторизувати';

  @override
  String get revokeAuthorization => 'Відкликати авторизацію';

  @override
  String get authorizationSuccessful => 'Авторизація успішна!';

  @override
  String get failedToAuthorize => 'Не вдалося авторизувати. Будь ласка, спробуйте ще раз.';

  @override
  String get authorizationRevoked => 'Авторизацію відкликано.';

  @override
  String get recordingsDeleted => 'Записи видалено.';

  @override
  String get failedToRevoke => 'Не вдалося відкликати авторизацію. Будь ласка, спробуйте ще раз.';

  @override
  String get permissionRevokedTitle => 'Дозвіл відкликано';

  @override
  String get permissionRevokedMessage => 'Чи хочете ви також видалити всі ваші існуючі записи?';

  @override
  String get yes => 'Так';

  @override
  String get editName => 'Редагувати ім\'я';

  @override
  String get howShouldOmiCallYou => 'Як Omi має до вас звертатися?';

  @override
  String get enterYourName => 'Введіть своє ім\'я';

  @override
  String get nameCannotBeEmpty => 'Ім\'я не може бути порожнім';

  @override
  String get nameUpdatedSuccessfully => 'Ім\'я успішно оновлено!';

  @override
  String get calendarSettings => 'Налаштування календаря';

  @override
  String get calendarProviders => 'Провайдери календаря';

  @override
  String get macOsCalendar => 'Календар macOS';

  @override
  String get connectMacOsCalendar => 'Підключіть свій локальний календар macOS';

  @override
  String get googleCalendar => 'Google Календар';

  @override
  String get syncGoogleAccount => 'Синхронізація з вашим обліковим записом Google';

  @override
  String get showMeetingsMenuBar => 'Показувати майбутні зустрічі у меню';

  @override
  String get showMeetingsMenuBarDesc => 'Відображати вашу наступну зустріч та час до її початку у меню macOS';

  @override
  String get showEventsNoParticipants => 'Показувати події без учасників';

  @override
  String get showEventsNoParticipantsDesc => 'Коли увімкнено, показує події без учасників або відео-посилання.';

  @override
  String get yourMeetings => 'Ваші зустрічі';

  @override
  String get refresh => 'Оновити';

  @override
  String get noUpcomingMeetings => 'Майбутніх зустрічей не знайдено';

  @override
  String get checkingNextDays => 'Перевірка наступних 30 днів';

  @override
  String get tomorrow => 'Завтра';

  @override
  String get googleCalendarComingSoon => 'Інтеграція з Google Календарем незабаром!';

  @override
  String connectedAsUser(String userId) {
    return 'Підключено як користувач: $userId';
  }

  @override
  String get defaultWorkspace => 'Робочий простір за замовчуванням';

  @override
  String get tasksCreatedInWorkspace => 'Завдання будуть створені у цьому робочому просторі';

  @override
  String get defaultProjectOptional => 'Проект за замовчуванням (необов\'язково)';

  @override
  String get leaveUnselectedTasks => 'Залиште невибраним для створення завдань без проекту';

  @override
  String get noProjectsInWorkspace => 'У цьому робочому просторі не знайдено проектів';

  @override
  String get conversationTimeoutDesc => 'Виберіть, скільки часу чекати в тиші перед автоматичним завершенням розмови:';

  @override
  String get timeout2Minutes => '2 хвилини';

  @override
  String get timeout2MinutesDesc => 'Завершити розмову після 2 хвилин тиші';

  @override
  String get timeout5Minutes => '5 хвилин';

  @override
  String get timeout5MinutesDesc => 'Завершити розмову після 5 хвилин тиші';

  @override
  String get timeout10Minutes => '10 хвилин';

  @override
  String get timeout10MinutesDesc => 'Завершити розмову після 10 хвилин тиші';

  @override
  String get timeout30Minutes => '30 хвилин';

  @override
  String get timeout30MinutesDesc => 'Завершити розмову після 30 хвилин тиші';

  @override
  String get timeout4Hours => '4 години';

  @override
  String get timeout4HoursDesc => 'Завершити розмову після 4 годин тиші';

  @override
  String get conversationEndAfterHours => 'Розмови тепер завершуватимуться після 4 годин тиші';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Розмови тепер завершуватимуться після $minutes хвилин тиші';
  }

  @override
  String get tellUsPrimaryLanguage => 'Вкажіть свою основну мову';

  @override
  String get languageForTranscription => 'Встановіть свою мову для точнішої транскрипції та персоналізованого досвіду.';

  @override
  String get singleLanguageModeInfo => 'Режим однієї мови увімкнено. Переклад вимкнено для вищої точності.';

  @override
  String get searchLanguageHint => 'Шукайте мову за назвою або кодом';

  @override
  String get noLanguagesFound => 'Мов не знайдено';

  @override
  String get skip => 'Пропустити';

  @override
  String languageSetTo(String language) {
    return 'Мову встановлено на $language';
  }

  @override
  String get failedToSetLanguage => 'Не вдалося встановити мову';

  @override
  String appSettings(String appName) {
    return 'Налаштування $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Відключитись від $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Це видалить вашу автентифікацію $appName. Вам потрібно буде підключитися знову, щоб використовувати це.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Підключено до $appName';
  }

  @override
  String get account => 'Обліковий запис';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Ваші завдання будуть синхронізовані з вашим обліковим записом $appName';
  }

  @override
  String get defaultSpace => 'Простір за замовчуванням';

  @override
  String get selectSpaceInWorkspace => 'Виберіть простір у вашому робочому просторі';

  @override
  String get noSpacesInWorkspace => 'У цьому робочому просторі не знайдено просторів';

  @override
  String get defaultList => 'Список за замовчуванням';

  @override
  String get tasksAddedToList => 'Завдання будуть додані до цього списку';

  @override
  String get noListsInSpace => 'У цьому просторі не знайдено списків';

  @override
  String failedToLoadRepos(String error) {
    return 'Не вдалося завантажити репозиторії: $error';
  }

  @override
  String get defaultRepoSaved => 'Репозиторій за замовчуванням збережено';

  @override
  String get failedToSaveDefaultRepo => 'Не вдалося зберегти репозиторій за замовчуванням';

  @override
  String get defaultRepository => 'Репозиторій за замовчуванням';

  @override
  String get selectDefaultRepoDesc =>
      'Виберіть репозиторій за замовчуванням для створення issues. Ви все ще можете вказати інший репозиторій під час створення issues.';

  @override
  String get noReposFound => 'Репозиторіїв не знайдено';

  @override
  String get private => 'Приватний';

  @override
  String updatedDate(String date) {
    return 'Оновлено $date';
  }

  @override
  String get yesterday => 'Вчора';

  @override
  String daysAgo(int count) {
    return '$count днів тому';
  }

  @override
  String get oneWeekAgo => '1 тиждень тому';

  @override
  String weeksAgo(int count) {
    return '$count тижнів тому';
  }

  @override
  String get oneMonthAgo => '1 місяць тому';

  @override
  String monthsAgo(int count) {
    return '$count місяців тому';
  }

  @override
  String get issuesCreatedInRepo => 'Issues будуть створені у вашому репозиторії за замовчуванням';

  @override
  String get taskIntegrations => 'Інтеграції завдань';

  @override
  String get configureSettings => 'Налаштувати параметри';

  @override
  String get completeAuthBrowser =>
      'Будь ласка, завершіть автентифікацію у браузері. Після завершення поверніться до додатка.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Не вдалося розпочати автентифікацію $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Підключитися до $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Вам потрібно авторизувати Omi для створення завдань у вашому обліковому записі $appName. Це відкриє ваш браузер для автентифікації.';
  }

  @override
  String get continueButton => 'Продовжити';

  @override
  String appIntegration(String appName) {
    return 'Інтеграція $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Інтеграція з $appName незабаром! Ми наполегливо працюємо, щоб надати вам більше опцій управління завданнями.';
  }

  @override
  String get gotIt => 'Зрозуміло';

  @override
  String get tasksExportedOneApp => 'Завдання можна експортувати в один додаток за раз.';

  @override
  String get completeYourUpgrade => 'Завершіть оновлення';

  @override
  String get importConfiguration => 'Імпортувати конфігурацію';

  @override
  String get exportConfiguration => 'Експортувати конфігурацію';

  @override
  String get bringYourOwn => 'Використовуйте власний';

  @override
  String get payYourSttProvider => 'Вільно користуйтесь omi. Ви платите лише своєму STT-провайдеру безпосередньо.';

  @override
  String get freeMinutesMonth => '1,200 безкоштовних хвилин/місяць включено. Необмежено з ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Хост обов\'язковий';

  @override
  String get validPortRequired => 'Потрібен дійсний порт';

  @override
  String get validWebsocketUrlRequired => 'Потрібен дійсний URL WebSocket (wss://)';

  @override
  String get apiUrlRequired => 'API URL обов\'язковий';

  @override
  String get apiKeyRequired => 'API-ключ обов\'язковий';

  @override
  String get invalidJsonConfig => 'Недійсна конфігурація JSON';

  @override
  String errorSaving(String error) {
    return 'Помилка збереження: $error';
  }

  @override
  String get configCopiedToClipboard => 'Конфігурацію скопійовано до буфера обміну';

  @override
  String get pasteJsonConfig => 'Вставте свою конфігурацію JSON нижче:';

  @override
  String get addApiKeyAfterImport => 'Вам потрібно буде додати власний API-ключ після імпорту';

  @override
  String get paste => 'Вставити';

  @override
  String get import => 'Імпортувати';

  @override
  String get invalidProviderInConfig => 'Недійсний провайдер у конфігурації';

  @override
  String importedConfig(String providerName) {
    return 'Імпортовано конфігурацію $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'Недійсний JSON: $error';
  }

  @override
  String get provider => 'Провайдер';

  @override
  String get live => 'В реальному часі';

  @override
  String get onDevice => 'На пристрої';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Введіть свою HTTP кінцеву точку STT';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Введіть свою WebSocket кінцеву точку STT в реальному часі';

  @override
  String get apiKey => 'API-ключ';

  @override
  String get enterApiKey => 'Введіть свій API-ключ';

  @override
  String get storedLocallyNeverShared => 'Зберігається локально, ніколи не передається';

  @override
  String get host => 'Хост';

  @override
  String get port => 'Порт';

  @override
  String get advanced => 'Розширені';

  @override
  String get configuration => 'Конфігурація';

  @override
  String get requestConfiguration => 'Конфігурація запиту';

  @override
  String get responseSchema => 'Схема відповіді';

  @override
  String get modified => 'Змінено';

  @override
  String get resetRequestConfig => 'Скинути конфігурацію запиту до значень за замовчуванням';

  @override
  String get logs => 'Журнали';

  @override
  String get logsCopied => 'Журнали скопійовано';

  @override
  String get noLogsYet => 'Журналів поки немає. Почніть запис, щоб побачити активність власного STT.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName використовує $codecReason. Буде використано Omi.';
  }

  @override
  String get omiTranscription => 'Транскрипція Omi';

  @override
  String get bestInClassTranscription => 'Найкраща транскрипція без налаштування';

  @override
  String get instantSpeakerLabels => 'Миттєві мітки спікерів';

  @override
  String get languageTranslation => 'Переклад 100+ мов';

  @override
  String get optimizedForConversation => 'Оптимізовано для розмов';

  @override
  String get autoLanguageDetection => 'Автоматичне визначення мови';

  @override
  String get highAccuracy => 'Висока точність';

  @override
  String get privacyFirst => 'Конфіденційність на першому місці';

  @override
  String get saveChanges => 'Зберегти зміни';

  @override
  String get resetToDefault => 'Скинути до типового';

  @override
  String get viewTemplate => 'Переглянути шаблон';

  @override
  String get trySomethingLike => 'Спробуйте щось подібне...';

  @override
  String get tryIt => 'Спробувати';

  @override
  String get creatingPlan => 'Створення плану';

  @override
  String get developingLogic => 'Розробка логіки';

  @override
  String get designingApp => 'Проектування додатка';

  @override
  String get generatingIconStep => 'Генерація іконки';

  @override
  String get finalTouches => 'Фінальні штрихи';

  @override
  String get processing => 'Обробка...';

  @override
  String get features => 'Можливості';

  @override
  String get creatingYourApp => 'Створення вашого додатка...';

  @override
  String get generatingIcon => 'Генерація іконки...';

  @override
  String get whatShouldWeMake => 'Що ми повинні створити?';

  @override
  String get appName => 'Назва додатка';

  @override
  String get description => 'Опис';

  @override
  String get publicLabel => 'Публічний';

  @override
  String get privateLabel => 'Приватний';

  @override
  String get free => 'Безкоштовно';

  @override
  String get perMonth => '/ Місяць';

  @override
  String get tailoredConversationSummaries => 'Персоналізовані підсумки розмов';

  @override
  String get customChatbotPersonality => 'Налаштована особистість чат-бота';

  @override
  String get makePublic => 'Зробити публічним';

  @override
  String get anyoneCanDiscover => 'Будь-хто може знайти ваш додаток';

  @override
  String get onlyYouCanUse => 'Лише ви можете використовувати цей додаток';

  @override
  String get paidApp => 'Платний додаток';

  @override
  String get usersPayToUse => 'Користувачі платять за використання вашого додатка';

  @override
  String get freeForEveryone => 'Безкоштовно для всіх';

  @override
  String get perMonthLabel => '/ місяць';

  @override
  String get creating => 'Створення...';

  @override
  String get createApp => 'Створити додаток';

  @override
  String get searchingForDevices => 'Пошук пристроїв...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'ПРИСТРОЇВ',
      one: 'ПРИСТРІЙ',
    );
    return '$count $_temp0 ЗНАЙДЕНО ПОБЛИЗУ';
  }

  @override
  String get pairingSuccessful => 'З\'ЄДНАННЯ УСПІШНЕ';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Помилка підключення до Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Більше не показувати';

  @override
  String get iUnderstand => 'Я розумію';

  @override
  String get enableBluetooth => 'Увімкнути Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi потребує Bluetooth для підключення до вашого носимого пристрою. Будь ласка, увімкніть Bluetooth та спробуйте ще раз.';

  @override
  String get contactSupport => 'Зв\'язатися з підтримкою?';

  @override
  String get connectLater => 'Підключити пізніше';

  @override
  String get grantPermissions => 'Надати дозволи';

  @override
  String get backgroundActivity => 'Фонова активність';

  @override
  String get backgroundActivityDesc => 'Дозвольте Omi працювати у фоновому режимі для кращої стабільності';

  @override
  String get locationAccess => 'Доступ до місцезнаходження';

  @override
  String get locationAccessDesc => 'Увімкніть фонове місцезнаходження для повного досвіду';

  @override
  String get notifications => 'Сповіщення';

  @override
  String get notificationsDesc => 'Увімкніть сповіщення, щоб бути в курсі';

  @override
  String get locationServiceDisabled => 'Служба визначення місцезнаходження вимкнена';

  @override
  String get locationServiceDisabledDesc =>
      'Служба визначення місцезнаходження вимкнена. Будь ласка, перейдіть до Налаштування > Конфіденційність і безпека > Служби визначення місцезнаходження та увімкніть її';

  @override
  String get backgroundLocationDenied => 'Відмовлено в доступі до фонового місцезнаходження';

  @override
  String get backgroundLocationDeniedDesc =>
      'Будь ласка, перейдіть до налаштувань пристрою та встановіть дозвіл на місцезнаходження на \"Завжди дозволяти\"';

  @override
  String get lovingOmi => 'Подобається Omi?';

  @override
  String get leaveReviewIos =>
      'Допоможіть нам охопити більше людей, залишивши відгук в App Store. Ваші відгуки дуже важливі для нас!';

  @override
  String get leaveReviewAndroid =>
      'Допоможіть нам охопити більше людей, залишивши відгук в Google Play Store. Ваші відгуки дуже важливі для нас!';

  @override
  String get rateOnAppStore => 'Оцінити в App Store';

  @override
  String get rateOnGooglePlay => 'Оцінити в Google Play';

  @override
  String get maybeLater => 'Можливо, пізніше';

  @override
  String get speechProfileIntro => 'Omi потрібно дізнатися про ваші цілі та ваш голос. Ви зможете змінити це пізніше.';

  @override
  String get getStarted => 'Почати';

  @override
  String get allDone => 'Все готово!';

  @override
  String get keepGoing => 'Продовжуйте, у вас чудово виходить';

  @override
  String get skipThisQuestion => 'Пропустити це питання';

  @override
  String get skipForNow => 'Пропустити зараз';

  @override
  String get connectionError => 'Помилка підключення';

  @override
  String get connectionErrorDesc =>
      'Не вдалося підключитися до сервера. Будь ласка, перевірте підключення до інтернету та спробуйте ще раз.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Виявлено недійсний запис';

  @override
  String get multipleSpeakersDesc =>
      'Схоже, що в записі кілька спікерів. Будь ласка, переконайтеся, що ви знаходитесь у тихому місці, та спробуйте ще раз.';

  @override
  String get tooShortDesc => 'Недостатньо мовлення виявлено. Будь ласка, говоріть більше та спробуйте ще раз.';

  @override
  String get invalidRecordingDesc => 'Будь ласка, переконайтеся, що ви говорите щонайменше 5 секунд і не більше 90.';

  @override
  String get areYouThere => 'Ви тут?';

  @override
  String get noSpeechDesc =>
      'Ми не змогли виявити жодного мовлення. Будь ласка, переконайтеся, що ви говорите щонайменше 10 секунд і не більше 3 хвилин.';

  @override
  String get connectionLost => 'З\'єднання втрачено';

  @override
  String get connectionLostDesc =>
      'З\'єднання було перервано. Будь ласка, перевірте підключення до інтернету та спробуйте ще раз.';

  @override
  String get tryAgain => 'Спробувати ще раз';

  @override
  String get connectOmiOmiGlass => 'Підключити Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Продовжити без пристрою';

  @override
  String get permissionsRequired => 'Потрібні дозволи';

  @override
  String get permissionsRequiredDesc =>
      'Цей додаток потребує дозволів Bluetooth та Місцезнаходження для правильної роботи. Будь ласка, увімкніть їх у налаштуваннях.';

  @override
  String get openSettings => 'Відкрити налаштування';

  @override
  String get wantDifferentName => 'Хочете, щоб до вас звертались інакше?';

  @override
  String get whatsYourName => 'Як вас звати?';

  @override
  String get speakTranscribeSummarize => 'Говоріть. Транскрибуйте. Підсумовуйте.';

  @override
  String get signInWithApple => 'Увійти через Apple';

  @override
  String get signInWithGoogle => 'Увійти через Google';

  @override
  String get byContinuingAgree => 'Продовжуючи, ви погоджуєтесь з нашою ';

  @override
  String get termsOfUse => 'Умовами використання';

  @override
  String get omiYourAiCompanion => 'Omi – ваш AI-компаньйон';

  @override
  String get captureEveryMoment =>
      'Захопіть кожну мить. Отримуйте підсумки на основі AI.\nНіколи більше не робіть нотатки.';

  @override
  String get appleWatchSetup => 'Налаштування Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Запит дозволу!';

  @override
  String get microphonePermission => 'Дозвіл на мікрофон';

  @override
  String get permissionGrantedNow =>
      'Дозвіл надано! Тепер:\n\nВідкрийте додаток Omi на вашому годиннику та натисніть \"Продовжити\" нижче';

  @override
  String get needMicrophonePermission =>
      'Нам потрібен дозвіл на мікрофон.\n\n1. Натисніть \"Надати дозвіл\"\n2. Дозвольте на вашому iPhone\n3. Додаток на годиннику закриється\n4. Відкрийте знову та натисніть \"Продовжити\"';

  @override
  String get grantPermissionButton => 'Надати дозвіл';

  @override
  String get needHelp => 'Потрібна допомога?';

  @override
  String get troubleshootingSteps =>
      'Усунення несправностей:\n\n1. Переконайтеся, що Omi встановлено на вашому годиннику\n2. Відкрийте додаток Omi на вашому годиннику\n3. Шукайте спливаюче вікно дозволу\n4. Натисніть \"Дозволити\" при запиті\n5. Додаток на вашому годиннику закриється - відкрийте його знову\n6. Поверніться та натисніть \"Продовжити\" на вашому iPhone';

  @override
  String get recordingStartedSuccessfully => 'Запис успішно розпочато!';

  @override
  String get permissionNotGrantedYet =>
      'Дозвіл ще не надано. Будь ласка, переконайтеся, що ви дозволили доступ до мікрофона та відкрили додаток на вашому годиннику знову.';

  @override
  String errorRequestingPermission(String error) {
    return 'Помилка запиту дозволу: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Помилка початку запису: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Виберіть свою основну мову';

  @override
  String get languageBenefits => 'Встановіть свою мову для точнішої транскрипції та персоналізованого досвіду';

  @override
  String get whatsYourPrimaryLanguage => 'Яка ваша основна мова?';

  @override
  String get selectYourLanguage => 'Виберіть свою мову';

  @override
  String get personalGrowthJourney => 'Ваша подорож особистого зростання з AI, який слухає кожне ваше слово.';

  @override
  String get actionItemsTitle => 'Завдання';

  @override
  String get actionItemsDescription => 'Торкніться для редагування • Довге натискання для вибору • Проведіть для дій';

  @override
  String get tabToDo => 'До виконання';

  @override
  String get tabDone => 'Виконано';

  @override
  String get tabOld => 'Старі';

  @override
  String get emptyTodoMessage => '🎉 Все виконано!\nНемає завдань у черзі';

  @override
  String get emptyDoneMessage => 'Виконаних завдань поки немає';

  @override
  String get emptyOldMessage => '✅ Немає старих завдань';

  @override
  String get noItems => 'Немає елементів';

  @override
  String get actionItemMarkedIncomplete => 'Завдання позначено як невиконане';

  @override
  String get actionItemCompleted => 'Завдання виконано';

  @override
  String get deleteActionItemTitle => 'Видалити елемент дії';

  @override
  String get deleteActionItemMessage => 'Ви впевнені, що хочете видалити цей елемент дії?';

  @override
  String get deleteSelectedItemsTitle => 'Видалити вибрані елементи';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Ви впевнені, що хочете видалити $count вибраних завдань$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Завдання \"$description\" видалено';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count завдань$s видалено';
  }

  @override
  String get failedToDeleteItem => 'Не вдалося видалити завдання';

  @override
  String get failedToDeleteItems => 'Не вдалося видалити елементи';

  @override
  String get failedToDeleteSomeItems => 'Не вдалося видалити деякі елементи';

  @override
  String get welcomeActionItemsTitle => 'Готовий до завдань';

  @override
  String get welcomeActionItemsDescription =>
      'Ваш AI автоматично витягатиме завдання з ваших розмов. Вони з\'являться тут після створення.';

  @override
  String get autoExtractionFeature => 'Автоматично витягуються з розмов';

  @override
  String get editSwipeFeature => 'Торкніться для редагування, проведіть для завершення або видалення';

  @override
  String itemsSelected(int count) {
    return 'Вибрано: $count';
  }

  @override
  String get selectAll => 'Вибрати все';

  @override
  String get deleteSelected => 'Видалити вибрані';

  @override
  String searchMemories(int count) {
    return 'Пошук серед $count спогадів';
  }

  @override
  String get memoryDeleted => 'Спогад видалено.';

  @override
  String get undo => 'Скасувати';

  @override
  String get noMemoriesYet => 'Спогадів поки немає';

  @override
  String get noAutoMemories => 'Автоматично витягнутих спогадів поки немає';

  @override
  String get noManualMemories => 'Власних спогадів поки немає';

  @override
  String get noMemoriesInCategories => 'Немає спогадів у цих категоріях';

  @override
  String get noMemoriesFound => 'Спогадів не знайдено';

  @override
  String get addFirstMemory => 'Додати перший спогад';

  @override
  String get clearMemoryTitle => 'Очистити пам\'ять Omi';

  @override
  String get clearMemoryMessage => 'Ви впевнені, що хочете очистити пам\'ять Omi? Цю дію не можна скасувати.';

  @override
  String get clearMemoryButton => 'Очистити пам\'ять';

  @override
  String get memoryClearedSuccess => 'Пам\'ять Omi про вас очищено';

  @override
  String get noMemoriesToDelete => 'Немає спогадів для видалення';

  @override
  String get createMemoryTooltip => 'Створити новий спогад';

  @override
  String get createActionItemTooltip => 'Створити нове завдання';

  @override
  String get memoryManagement => 'Управління спогадами';

  @override
  String get filterMemories => 'Фільтрувати спогади';

  @override
  String totalMemoriesCount(int count) {
    return 'У вас є $count спогадів загалом';
  }

  @override
  String get publicMemories => 'Публічні спогади';

  @override
  String get privateMemories => 'Приватні спогади';

  @override
  String get makeAllPrivate => 'Зробити всі спогади приватними';

  @override
  String get makeAllPublic => 'Зробити всі спогади публічними';

  @override
  String get deleteAllMemories => 'Видалити всі спогади';

  @override
  String get allMemoriesPrivateResult => 'Всі спогади тепер приватні';

  @override
  String get allMemoriesPublicResult => 'Всі спогади тепер публічні';

  @override
  String get newMemory => 'Новий спогад';

  @override
  String get editMemory => 'Редагувати спогад';

  @override
  String get memoryContentHint => 'Мені подобається їсти морозиво...';

  @override
  String get failedToSaveMemory => 'Не вдалося зберегти. Будь ласка, перевірте підключення.';

  @override
  String get saveMemory => 'Зберегти спогад';

  @override
  String get retry => 'Спробувати ще раз';

  @override
  String get createActionItem => 'Створити елемент дії';

  @override
  String get editActionItem => 'Редагувати елемент дії';

  @override
  String get actionItemDescriptionHint => 'Що потрібно зробити?';

  @override
  String get actionItemDescriptionEmpty => 'Опис завдання не може бути порожнім.';

  @override
  String get actionItemUpdated => 'Завдання оновлено';

  @override
  String get failedToUpdateActionItem => 'Не вдалося оновити елемент дії';

  @override
  String get actionItemCreated => 'Завдання створено';

  @override
  String get failedToCreateActionItem => 'Не вдалося створити елемент дії';

  @override
  String get dueDate => 'Термін виконання';

  @override
  String get time => 'Час';

  @override
  String get addDueDate => 'Додати термін виконання';

  @override
  String get pressDoneToSave => 'Натисніть готово для збереження';

  @override
  String get pressDoneToCreate => 'Натисніть готово для створення';

  @override
  String get filterAll => 'Всі';

  @override
  String get filterSystem => 'Про вас';

  @override
  String get filterInteresting => 'Insights';

  @override
  String get filterManual => 'Власні';

  @override
  String get completed => 'Завершено';

  @override
  String get markComplete => 'Позначити як виконане';

  @override
  String get actionItemDeleted => 'Елемент дії видалено';

  @override
  String get failedToDeleteActionItem => 'Не вдалося видалити елемент дії';

  @override
  String get deleteActionItemConfirmTitle => 'Видалити завдання';

  @override
  String get deleteActionItemConfirmMessage => 'Ви впевнені, що хочете видалити це завдання?';

  @override
  String get appLanguage => 'Мова додатка';

  @override
  String get appInterfaceSectionTitle => 'ІНТЕРФЕЙС ДОДАТКУ';

  @override
  String get speechTranscriptionSectionTitle => 'МОВЛЕННЯ ТА ТРАНСКРИПЦІЯ';

  @override
  String get languageSettingsHelperText =>
      'Мова додатку змінює меню та кнопки. Мова мовлення впливає на те, як транскрибуються ваші записи.';

  @override
  String get translationNotice => 'Повідомлення про переклад';

  @override
  String get translationNoticeMessage =>
      'Omi перекладає розмови на вашу основну мову. Оновіть її в будь-який час у Налаштування → Профілі.';

  @override
  String get pleaseCheckInternetConnection => 'Будь ласка, перевірте підключення до Інтернету та спробуйте ще раз';

  @override
  String get pleaseSelectReason => 'Будь ласка, виберіть причину';

  @override
  String get tellUsMoreWhatWentWrong => 'Розкажіть нам більше про те, що пішло не так...';

  @override
  String get selectText => 'Вибрати текст';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Максимум $count цілей дозволено';
  }

  @override
  String get conversationCannotBeMerged => 'Цю розмову не можна об\'єднати (заблокована або вже об\'єднується)';

  @override
  String get pleaseEnterFolderName => 'Будь ласка, введіть ім\'я папки';

  @override
  String get failedToCreateFolder => 'Не вдалося створити папку';

  @override
  String get failedToUpdateFolder => 'Не вдалося оновити папку';

  @override
  String get folderName => 'Назва папки';

  @override
  String get descriptionOptional => 'Опис (необов\'язково)';

  @override
  String get failedToDeleteFolder => 'Не вдалося видалити папку';

  @override
  String get editFolder => 'Редагувати папку';

  @override
  String get deleteFolder => 'Видалити папку';

  @override
  String get transcriptCopiedToClipboard => 'Транскрипт скопійовано в буфер обміну';

  @override
  String get summaryCopiedToClipboard => 'Резюме скопійовано в буфер обміну';

  @override
  String get conversationUrlCouldNotBeShared => 'URL-адресу розмови не вдалося поділитися.';

  @override
  String get urlCopiedToClipboard => 'URL скопійовано в буфер обміну';

  @override
  String get exportTranscript => 'Експортувати транскрипт';

  @override
  String get exportSummary => 'Експортувати резюме';

  @override
  String get exportButton => 'Експортувати';

  @override
  String get actionItemsCopiedToClipboard => 'Елементи дій скопійовано в буфер обміну';

  @override
  String get summarize => 'Резюмувати';

  @override
  String get generateSummary => 'Створити резюме';

  @override
  String get conversationNotFoundOrDeleted => 'Розмову не знайдено або вона була видалена';

  @override
  String get deleteMemory => 'Видалити пам\'ять?';

  @override
  String get thisActionCannotBeUndone => 'Цю дію не можна скасувати.';

  @override
  String memoriesCount(int count) {
    return '$count спогадів';
  }

  @override
  String get noMemoriesInCategory => 'У цій категорії поки немає спогадів';

  @override
  String get addYourFirstMemory => 'Додайте свій перший спогад';

  @override
  String get firmwareDisconnectUsb => 'Від\'єднайте USB';

  @override
  String get firmwareUsbWarning => 'USB-з\'єднання під час оновлень може пошкодити ваш пристрій.';

  @override
  String get firmwareBatteryAbove15 => 'Батарея вище 15%';

  @override
  String get firmwareEnsureBattery => 'Переконайтеся, що ваш пристрій має 15% заряду батареї.';

  @override
  String get firmwareStableConnection => 'Стабільне з\'єднання';

  @override
  String get firmwareConnectWifi => 'Підключіться до WiFi або мобільної мережі.';

  @override
  String failedToStartUpdate(String error) {
    return 'Не вдалося почати оновлення: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Перед оновленням переконайтеся:';

  @override
  String get confirmed => 'Підтверджено!';

  @override
  String get release => 'Відпустіть';

  @override
  String get slideToUpdate => 'Проведіть для оновлення';

  @override
  String copiedToClipboard(String title) {
    return '$title скопійовано в буфер обміну';
  }

  @override
  String get batteryLevel => 'Рівень заряду';

  @override
  String get productUpdate => 'Оновлення продукту';

  @override
  String get offline => 'Не в мережі';

  @override
  String get available => 'Доступно';

  @override
  String get unpairDeviceDialogTitle => 'Скасувати з\'єднання пристрою';

  @override
  String get unpairDeviceDialogMessage =>
      'Це скасує з\'єднання пристрою, щоб його можна було підключити до іншого телефону. Вам потрібно буде перейти до Налаштування > Bluetooth і забути пристрій, щоб завершити процес.';

  @override
  String get unpair => 'Скасувати з\'єднання';

  @override
  String get unpairAndForgetDevice => 'Скасувати з\'єднання та забути пристрій';

  @override
  String get unknownDevice => 'Невідомий пристрій';

  @override
  String get unknown => 'Невідомо';

  @override
  String get productName => 'Назва продукту';

  @override
  String get serialNumber => 'Серійний номер';

  @override
  String get connected => 'Підключено';

  @override
  String get privacyPolicyTitle => 'Політика конфіденційності';

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
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Configure your AI persona';

  @override
  String get configureSttProvider => 'Configure STT provider';

  @override
  String get setWhenConversationsAutoEnd => 'Set when conversations auto-end';

  @override
  String get importDataFromOtherSources => 'Import data from other sources';

  @override
  String get debugAndDiagnostics => 'Debug & Diagnostics';

  @override
  String get autoDeletesAfter3Days => 'Auto-deletes after 3 days.';

  @override
  String get helpsDiagnoseIssues => 'Helps diagnose issues';

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
  String get realTimeTranscript => 'Real-time Transcript';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Transcription Diagnostics';

  @override
  String get detailedDiagnosticMessages => 'Detailed diagnostic messages';

  @override
  String get autoCreateSpeakers => 'Auto-create Speakers';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Follow-up Questions';

  @override
  String get suggestQuestionsAfterConversations => 'Suggest questions after conversations';

  @override
  String get goalTracker => 'Goal Tracker';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Daily Reflection';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Опис елемента дії не може бути порожнім';

  @override
  String get saved => 'Збережено';

  @override
  String get overdue => 'Прострочено';

  @override
  String get failedToUpdateDueDate => 'Не вдалося оновити термін';

  @override
  String get markIncomplete => 'Позначити як невиконане';

  @override
  String get editDueDate => 'Редагувати термін';

  @override
  String get setDueDate => 'Встановити термін';

  @override
  String get clearDueDate => 'Очистити термін';

  @override
  String get failedToClearDueDate => 'Не вдалося очистити термін';

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
  String get howDoesItWork => 'Як це працює?';

  @override
  String get sdCardSyncDescription => 'Синхронізація SD-карти імпортує ваші спогади з SD-карти в додаток';

  @override
  String get checksForAudioFiles => 'Перевіряє аудіофайли на SD-карті';

  @override
  String get omiSyncsAudioFiles => 'Omi потім синхронізує аудіофайли з сервером';

  @override
  String get serverProcessesAudio => 'Сервер обробляє аудіофайли та створює спогади';

  @override
  String get youreAllSet => 'Все готово!';

  @override
  String get welcomeToOmiDescription =>
      'Ласкаво просимо до Omi! Ваш AI-компаньйон готовий допомогти вам із розмовами, завданнями та багато іншим.';

  @override
  String get startUsingOmi => 'Почати використання Omi';

  @override
  String get back => 'Назад';

  @override
  String get keyboardShortcuts => 'Гарячі клавіші';

  @override
  String get toggleControlBar => 'Перемкнути панель керування';

  @override
  String get pressKeys => 'Натисніть клавіші...';

  @override
  String get cmdRequired => '⌘ потрібно';

  @override
  String get invalidKey => 'Недійсна клавіша';

  @override
  String get space => 'Пробіл';

  @override
  String get search => 'Пошук';

  @override
  String get searchPlaceholder => 'Пошук...';

  @override
  String get untitledConversation => 'Бесіда без назви';

  @override
  String countRemaining(String count) {
    return '$count залишилось';
  }

  @override
  String get addGoal => 'Додати ціль';

  @override
  String get editGoal => 'Редагувати ціль';

  @override
  String get icon => 'Значок';

  @override
  String get goalTitle => 'Назва цілі';

  @override
  String get current => 'Поточний';

  @override
  String get target => 'Ціль';

  @override
  String get saveGoal => 'Зберегти';

  @override
  String get goals => 'Цілі';

  @override
  String get tapToAddGoal => 'Натисніть, щоб додати ціль';

  @override
  String get welcomeBack => 'Ласкаво просимо назад';

  @override
  String get yourConversations => 'Ваші розмови';

  @override
  String get reviewAndManageConversations => 'Переглядайте та керуйте записаними розмовами';

  @override
  String get startCapturingConversations =>
      'Почніть записувати розмови за допомогою пристрою Omi, щоб побачити їх тут.';

  @override
  String get useMobileAppToCapture => 'Використовуйте мобільний додаток для запису аудіо';

  @override
  String get conversationsProcessedAutomatically => 'Розмови обробляються автоматично';

  @override
  String get getInsightsInstantly => 'Отримуйте інформацію та резюме миттєво';

  @override
  String get showAll => 'Показати все →';

  @override
  String get noTasksForToday => 'Немає завдань на сьогодні.\\nЗапитайте Omi про більше завдань або створіть вручну.';

  @override
  String get dailyScore => 'ЩОДЕННИЙ БАЛ';

  @override
  String get dailyScoreDescription => 'Бал, який допомагає краще зосередитися на виконанні.';

  @override
  String get searchResults => 'Результати пошуку';

  @override
  String get actionItems => 'Елементи дій';

  @override
  String get tasksToday => 'Сьогодні';

  @override
  String get tasksTomorrow => 'Завтра';

  @override
  String get tasksNoDeadline => 'Без терміну';

  @override
  String get tasksLater => 'Пізніше';

  @override
  String get loadingTasks => 'Завантаження завдань...';

  @override
  String get tasks => 'Завдання';

  @override
  String get swipeTasksToIndent => 'Проведіть пальцем по завданнях для відступу, перетягніть між категоріями';

  @override
  String get create => 'Створити';

  @override
  String get noTasksYet => 'Поки що немає завдань';

  @override
  String get tasksFromConversationsWillAppear =>
      'Завдання з ваших розмов з\'являться тут.\nНатисніть Створити, щоб додати завдання вручну.';

  @override
  String get monthJan => 'Січ';

  @override
  String get monthFeb => 'Лют';

  @override
  String get monthMar => 'Бер';

  @override
  String get monthApr => 'Кві';

  @override
  String get monthMay => 'Тра';

  @override
  String get monthJun => 'Чер';

  @override
  String get monthJul => 'Лип';

  @override
  String get monthAug => 'Сер';

  @override
  String get monthSep => 'Вер';

  @override
  String get monthOct => 'Жов';

  @override
  String get monthNov => 'Лис';

  @override
  String get monthDec => 'Гру';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Елемент дії успішно оновлено';

  @override
  String get actionItemCreatedSuccessfully => 'Елемент дії успішно створено';

  @override
  String get actionItemDeletedSuccessfully => 'Елемент дії успішно видалено';

  @override
  String get deleteActionItem => 'Видалити елемент дії';

  @override
  String get deleteActionItemConfirmation =>
      'Ви впевнені, що хочете видалити цей елемент дії? Цю дію не можна скасувати.';

  @override
  String get enterActionItemDescription => 'Введіть опис елемента дії...';

  @override
  String get markAsCompleted => 'Позначити як виконане';

  @override
  String get setDueDateAndTime => 'Встановити термін і час';

  @override
  String get reloadingApps => 'Перезавантаження додатків...';

  @override
  String get loadingApps => 'Завантаження додатків...';

  @override
  String get browseInstallCreateApps => 'Переглядайте, встановлюйте та створюйте додатки';

  @override
  String get all => 'Усі';

  @override
  String get open => 'Відкрити';

  @override
  String get install => 'Встановити';

  @override
  String get noAppsAvailable => 'Немає доступних додатків';

  @override
  String get unableToLoadApps => 'Не вдалося завантажити додатки';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Спробуйте змінити умови пошуку або фільтри';

  @override
  String get checkBackLaterForNewApps => 'Повертайтеся пізніше за новими додатками';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Будь ласка, перевірте підключення до Інтернету та спробуйте ще раз';

  @override
  String get createNewApp => 'Створити новий додаток';

  @override
  String get buildSubmitCustomOmiApp => 'Створіть і надішліть свій власний додаток Omi';

  @override
  String get submittingYourApp => 'Надсилання вашого додатка...';

  @override
  String get preparingFormForYou => 'Підготовка форми для вас...';

  @override
  String get appDetails => 'Деталі додатка';

  @override
  String get paymentDetails => 'Платіжні дані';

  @override
  String get previewAndScreenshots => 'Попередній перегляд і знімки екрана';

  @override
  String get appCapabilities => 'Можливості додатка';

  @override
  String get aiPrompts => 'Підказки ШІ';

  @override
  String get chatPrompt => 'Підказка чату';

  @override
  String get chatPromptPlaceholder =>
      'Ви чудовий додаток, ваше завдання - відповідати на запити користувачів і змушувати їх почуватися добре...';

  @override
  String get conversationPrompt => 'Запит розмови';

  @override
  String get conversationPromptPlaceholder =>
      'Ви чудовий додаток, вам будуть надані транскрипція та короткий зміст розмови...';

  @override
  String get notificationScopes => 'Області сповіщень';

  @override
  String get appPrivacyAndTerms => 'Конфіденційність і умови додатка';

  @override
  String get makeMyAppPublic => 'Зробити мій додаток публічним';

  @override
  String get submitAppTermsAgreement =>
      'Надсилаючи цей додаток, я приймаю Умови використання та Політику конфіденційності Omi AI';

  @override
  String get submitApp => 'Надіслати додаток';

  @override
  String get needHelpGettingStarted => 'Потрібна допомога для початку роботи?';

  @override
  String get clickHereForAppBuildingGuides => 'Натисніть тут для посібників зі створення додатків та документації';

  @override
  String get submitAppQuestion => 'Надіслати додаток?';

  @override
  String get submitAppPublicDescription =>
      'Ваш додаток буде розглянуто і опубліковано. Ви можете почати використовувати його негайно, навіть під час розгляду!';

  @override
  String get submitAppPrivateDescription =>
      'Ваш додаток буде розглянуто і стане доступним для вас приватно. Ви можете почати використовувати його негайно, навіть під час розгляду!';

  @override
  String get startEarning => 'Почніть заробляти! 💰';

  @override
  String get connectStripeOrPayPal => 'Підключіть Stripe або PayPal, щоб отримувати платежі за ваш додаток.';

  @override
  String get connectNow => 'Підключити зараз';

  @override
  String installsCount(String count) {
    return '$count+ встановлень';
  }

  @override
  String get uninstallApp => 'Видалити додаток';

  @override
  String get subscribe => 'Підписатися';

  @override
  String get dataAccessNotice => 'Повідомлення про доступ до даних';

  @override
  String get dataAccessWarning =>
      'Цей додаток матиме доступ до ваших даних. Omi AI не несе відповідальності за те, як ваші дані використовуються, змінюються або видаляються цим додатком';

  @override
  String get installApp => 'Встановити додаток';

  @override
  String get betaTesterNotice =>
      'Ви бета-тестувальник цього додатка. Він ще не є публічним. Він стане публічним після схвалення.';

  @override
  String get appUnderReviewOwner => 'Ваш додаток на розгляді та видимий лише вам. Він стане публічним після схвалення.';

  @override
  String get appRejectedNotice =>
      'Ваш додаток було відхилено. Будь ласка, оновіть деталі додатка та надішліть його на розгляд знову.';

  @override
  String get setupSteps => 'Кроки налаштування';

  @override
  String get setupInstructions => 'Інструкції з налаштування';

  @override
  String get integrationInstructions => 'Інструкції з інтеграції';

  @override
  String get preview => 'Попередній перегляд';

  @override
  String get aboutTheApp => 'Про додаток';

  @override
  String get aboutThePersona => 'Про персону';

  @override
  String get chatPersonality => 'Особистість чату';

  @override
  String get ratingsAndReviews => 'Оцінки та відгуки';

  @override
  String get noRatings => 'немає оцінок';

  @override
  String ratingsCount(String count) {
    return '$count+ оцінок';
  }

  @override
  String get errorActivatingApp => 'Помилка активації додатка';

  @override
  String get integrationSetupRequired => 'Якщо це додаток інтеграції, переконайтеся, що налаштування завершено.';

  @override
  String get installed => 'Встановлено';
}
