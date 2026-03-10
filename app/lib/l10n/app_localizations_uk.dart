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
  String get copyTranscript => 'Копіювати транскрипт';

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
  String get speechProfile => 'Мовний Профіль';

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
  String get noStarredConversations => 'Немає обраних бесід';

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
  String get messageCopied => '✨ Повідомлення скопійовано в буфер обміну';

  @override
  String get cannotReportOwnMessage => 'Ви не можете поскаржитись на власні повідомлення.';

  @override
  String get reportMessage => 'Повідомити про повідомлення';

  @override
  String get reportMessageConfirm => 'Ви впевнені, що хочете поскаржитись на це повідомлення?';

  @override
  String get messageReported => 'Повідомлення успішно відправлено.';

  @override
  String get thankYouFeedback => 'Дякуємо за ваш відгук!';

  @override
  String get clearChat => 'Очистити чат';

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
  String get helpOrInquiries => 'Допомога чи запитання?';

  @override
  String get joinCommunity => 'Приєднуйтесь до спільноти!';

  @override
  String get membersAndCounting => '8000+ учасників і їх кількість зростає.';

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
  String get customVocabulary => 'Користувацький Словник';

  @override
  String get identifyingOthers => 'Ідентифікація Інших';

  @override
  String get paymentMethods => 'Способи Оплати';

  @override
  String get conversationDisplay => 'Відображення Розмов';

  @override
  String get dataPrivacy => 'Конфіденційність Даних';

  @override
  String get userId => 'ID Користувача';

  @override
  String get notSet => 'Не задано';

  @override
  String get userIdCopied => 'ID користувача скопійовано до буфера обміну';

  @override
  String get systemDefault => 'За замовчуванням системи';

  @override
  String get planAndUsage => 'План та використання';

  @override
  String get offlineSync => 'Офлайн синхронізація';

  @override
  String get deviceSettings => 'Налаштування пристрою';

  @override
  String get integrations => 'Інтеграції';

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
  String get off => 'Вимк.';

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
  String get createKey => 'Створити Ключ';

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
  String get upgradeToUnlimited => 'Оновити до безлімітного';

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
  String get noLogFilesFound => 'Файли журналу не знайдено.';

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
  String get knowledgeGraphDeleted => 'Граф знань видалено';

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
  String get authorizationBearer => 'Авторизація: Bearer <key>';

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
  String get realtimeTranscript => 'Транскрипт у реальному часі';

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
  String get insights => 'Ідеї';

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
  String get integrationsFooter => 'Підключіть свої додатки для перегляду даних та метрик у чаті.';

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
  String get enterYourName => 'Введіть ваше ім\'я';

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
  String get noUpcomingMeetings => 'Немає майбутніх зустрічей';

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
  String get noLanguagesFound => 'Мови не знайдені';

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
  String get private => 'Приватна';

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
  String get omiUnlimited => 'Omi Безлімітний';

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
  String get apiUrl => 'URL API';

  @override
  String get enterSttHttpEndpoint => 'Введіть свою HTTP кінцеву точку STT';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Введіть свою WebSocket кінцеву точку STT в реальному часі';

  @override
  String get apiKey => 'API ключ';

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
  String deviceUsesCodec(String device, String reason) {
    return '$device використовує $reason. Буде використано Omi.';
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
  String get appName => 'App Name';

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
  String get makePublic => 'Зробити публічною';

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
  String get speechProfileIntro => 'Omi потрібно вивчити ваші цілі та голос. Ви зможете змінити це пізніше.';

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
  String get personalGrowthJourney =>
      'Ваша подорож особистісного зростання зі штучним інтелектом, який слухає кожне ваше слово.';

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
  String get searchMemories => 'Пошук спогадів...';

  @override
  String get memoryDeleted => 'Спогад видалено.';

  @override
  String get undo => 'Скасувати';

  @override
  String get noMemoriesYet => '🧠 Поки що немає спогадів';

  @override
  String get noAutoMemories => 'Автоматично витягнутих спогадів поки немає';

  @override
  String get noManualMemories => 'Власних спогадів поки немає';

  @override
  String get noMemoriesInCategories => 'Немає спогадів у цих категоріях';

  @override
  String get noMemoriesFound => '🔍 Спогади не знайдено';

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
  String get memoryManagement => 'Керування пам\'яттю';

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
  String get newMemory => '✨ Нова пам\'ять';

  @override
  String get editMemory => '✏️ Редагувати пам\'ять';

  @override
  String get memoryContentHint => 'Мені подобається їсти морозиво...';

  @override
  String get failedToSaveMemory => 'Не вдалося зберегти. Будь ласка, перевірте підключення.';

  @override
  String get saveMemory => 'Зберегти спогад';

  @override
  String get retry => 'Повторити';

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
  String get filterInteresting => 'Інсайти';

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
  String get conversationUrlCouldNotBeShared => 'Не вдалося поділитися посиланням на розмову.';

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
  String get generateSummary => 'Створити підсумок';

  @override
  String get conversationNotFoundOrDeleted => 'Розмову не знайдено або вона була видалена';

  @override
  String get deleteMemory => 'Видалити пам\'ять';

  @override
  String get thisActionCannotBeUndone => 'Цю дію не можна скасувати.';

  @override
  String memoriesCount(int count) {
    return '$count спогадів';
  }

  @override
  String get noMemoriesInCategory => 'У цій категорії поки немає спогадів';

  @override
  String get addYourFirstMemory => 'Додайте перший спогад';

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
  String get unknownDevice => 'Невідомий';

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
    return '$label скопійовано';
  }

  @override
  String get noApiKeysYet => 'API-ключів поки немає. Створіть один для інтеграції з вашим додатком.';

  @override
  String get createKeyToGetStarted => 'Створіть ключ, щоб почати';

  @override
  String get persona => 'Персона';

  @override
  String get configureYourAiPersona => 'Налаштуйте свою AI-персону';

  @override
  String get configureSttProvider => 'Налаштувати провайдера STT';

  @override
  String get setWhenConversationsAutoEnd => 'Встановіть, коли розмови закінчуються автоматично';

  @override
  String get importDataFromOtherSources => 'Імпорт даних з інших джерел';

  @override
  String get debugAndDiagnostics => 'Налагодження та діагностика';

  @override
  String get autoDeletesAfter3Days => 'Автоматичне видалення через 3 дні';

  @override
  String get helpsDiagnoseIssues => 'Допомагає діагностувати проблеми';

  @override
  String get exportStartedMessage => 'Експорт розпочато. Це може зайняти кілька секунд...';

  @override
  String get exportConversationsToJson => 'Експортувати розмови у JSON-файл';

  @override
  String get knowledgeGraphDeletedSuccess => 'Граф знань успішно видалено';

  @override
  String failedToDeleteGraph(String error) {
    return 'Не вдалося видалити граф: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Очистити всі вузли та з\'єднання';

  @override
  String get addToClaudeDesktopConfig => 'Додати до claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Підключіть AI-помічників до ваших даних';

  @override
  String get useYourMcpApiKey => 'Використовуйте свій MCP API-ключ';

  @override
  String get realTimeTranscript => 'Транскрипція в реальному часі';

  @override
  String get experimental => 'Експериментальний';

  @override
  String get transcriptionDiagnostics => 'Діагностика транскрипції';

  @override
  String get detailedDiagnosticMessages => 'Детальні діагностичні повідомлення';

  @override
  String get autoCreateSpeakers => 'Автоматично створювати спікерів';

  @override
  String get autoCreateWhenNameDetected => 'Автоматично створювати при виявленні імені';

  @override
  String get followUpQuestions => 'Додаткові питання';

  @override
  String get suggestQuestionsAfterConversations => 'Пропонувати питання після розмов';

  @override
  String get goalTracker => 'Відстеження цілей';

  @override
  String get trackPersonalGoalsOnHomepage => 'Відстежуйте особисті цілі на головній сторінці';

  @override
  String get dailyReflection => 'Щоденна рефлексія';

  @override
  String get get9PmReminderToReflect => 'Отримуйте нагадування о 21:00, щоб обдумати свій день';

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
  String get keyboardShortcuts => 'Гарячі Клавіші';

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
  String get untitledConversation => 'Розмова без назви';

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
  String get current => 'Поточне';

  @override
  String get target => 'Ціль';

  @override
  String get saveGoal => 'Зберегти';

  @override
  String get goals => 'Цілі';

  @override
  String get tapToAddGoal => 'Натисніть, щоб додати ціль';

  @override
  String welcomeBack(String name) {
    return 'З поверненням, $name';
  }

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
  String get dailyScore => 'ДЕННИЙ РАХУНОК';

  @override
  String get dailyScoreDescription => 'Рахунок, який допомагає краще\nзосередитися на виконанні.';

  @override
  String get searchResults => 'Результати пошуку';

  @override
  String get actionItems => 'Завдання';

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
  String get timePM => 'ПП';

  @override
  String get timeAM => 'ДП';

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
  String get installsCount => 'Встановлення';

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

  @override
  String get appIdLabel => 'ID додатку';

  @override
  String get appNameLabel => 'Назва додатку';

  @override
  String get appNamePlaceholder => 'Мій чудовий додаток';

  @override
  String get pleaseEnterAppName => 'Будь ласка, введіть назву додатку';

  @override
  String get categoryLabel => 'Категорія';

  @override
  String get selectCategory => 'Виберіть категорію';

  @override
  String get descriptionLabel => 'Опис';

  @override
  String get appDescriptionPlaceholder =>
      'Мій чудовий додаток — це чудовий додаток, який робить дивовижні речі. Це найкращий додаток!';

  @override
  String get pleaseProvideValidDescription => 'Будь ласка, надайте дійсний опис';

  @override
  String get appPricingLabel => 'Ціноутворення додатку';

  @override
  String get noneSelected => 'Нічого не вибрано';

  @override
  String get appIdCopiedToClipboard => 'ID додатку скопійовано в буфер обміну';

  @override
  String get appCategoryModalTitle => 'Категорія додатку';

  @override
  String get pricingFree => 'Безкоштовно';

  @override
  String get pricingPaid => 'Платно';

  @override
  String get loadingCapabilities => 'Завантаження можливостей...';

  @override
  String get filterInstalled => 'Встановлено';

  @override
  String get filterMyApps => 'Мої додатки';

  @override
  String get clearSelection => 'Очистити вибір';

  @override
  String get filterCategory => 'Категорія';

  @override
  String get rating4PlusStars => '4+ зірки';

  @override
  String get rating3PlusStars => '3+ зірки';

  @override
  String get rating2PlusStars => '2+ зірки';

  @override
  String get rating1PlusStars => '1+ зірка';

  @override
  String get filterRating => 'Рейтинг';

  @override
  String get filterCapabilities => 'Можливості';

  @override
  String get noNotificationScopesAvailable => 'Немає доступних областей сповіщень';

  @override
  String get popularApps => 'Популярні додатки';

  @override
  String get pleaseProvidePrompt => 'Будь ласка, надайте запит';

  @override
  String chatWithAppName(String appName) {
    return 'Чат з $appName';
  }

  @override
  String get defaultAiAssistant => 'AI-асистент за замовчуванням';

  @override
  String get readyToChat => '✨ Готовий до чату!';

  @override
  String get connectionNeeded => '🌐 Потрібне підключення';

  @override
  String get startConversation => 'Почніть розмову і дозвольте магії розпочатися';

  @override
  String get checkInternetConnection => 'Будь ласка, перевірте підключення до Інтернету';

  @override
  String get wasThisHelpful => 'Чи було це корисно?';

  @override
  String get thankYouForFeedback => 'Дякуємо за ваш відгук!';

  @override
  String get maxFilesUploadError => 'Ви можете завантажити лише 4 файли за раз';

  @override
  String get attachedFiles => '📎 Прикріплені файли';

  @override
  String get takePhoto => 'Зробити фото';

  @override
  String get captureWithCamera => 'Зняти камерою';

  @override
  String get selectImages => 'Вибрати зображення';

  @override
  String get chooseFromGallery => 'Вибрати з галереї';

  @override
  String get selectFile => 'Вибрати файл';

  @override
  String get chooseAnyFileType => 'Вибрати будь-який тип файлу';

  @override
  String get cannotReportOwnMessages => 'Ви не можете повідомити про власні повідомлення';

  @override
  String get messageReportedSuccessfully => '✅ Повідомлення успішно надіслано';

  @override
  String get confirmReportMessage => 'Ви впевнені, що хочете повідомити про це повідомлення?';

  @override
  String get selectChatAssistant => 'Вибрати чат-асистента';

  @override
  String get enableMoreApps => 'Увімкнути більше додатків';

  @override
  String get chatCleared => 'Чат очищено';

  @override
  String get clearChatTitle => 'Очистити чат?';

  @override
  String get confirmClearChat => 'Ви впевнені, що хочете очистити чат? Цю дію не можна скасувати.';

  @override
  String get copy => 'Копіювати';

  @override
  String get share => 'Поділитися';

  @override
  String get report => 'Повідомити';

  @override
  String get microphonePermissionRequired => 'Для запису голосу потрібен дозвіл мікрофона.';

  @override
  String get microphonePermissionDenied =>
      'Доступ до мікрофона заборонено. Будь ласка, надайте дозвіл у Системні налаштування > Конфіденційність та безпека > Мікрофон.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Не вдалося перевірити дозвіл мікрофона: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Не вдалося розшифрувати аудіо';

  @override
  String get transcribing => 'Розшифровка...';

  @override
  String get transcriptionFailed => 'Розшифровка не вдалася';

  @override
  String get discardedConversation => 'Відхилена розмова';

  @override
  String get at => 'о';

  @override
  String get from => 'з';

  @override
  String get copied => 'Скопійовано!';

  @override
  String get copyLink => 'Копіювати посилання';

  @override
  String get hideTranscript => 'Сховати розшифровку';

  @override
  String get viewTranscript => 'Показати розшифровку';

  @override
  String get conversationDetails => 'Деталі розмови';

  @override
  String get transcript => 'Розшифровка';

  @override
  String segmentsCount(int count) {
    return '$count сегментів';
  }

  @override
  String get noTranscriptAvailable => 'Розшифровка недоступна';

  @override
  String get noTranscriptMessage => 'Ця розмова не має розшифровки.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL-адресу розмови не вдалося створити.';

  @override
  String get failedToGenerateConversationLink => 'Не вдалося створити посилання на розмову';

  @override
  String get failedToGenerateShareLink => 'Не вдалося створити посилання для спільного доступу';

  @override
  String get reloadingConversations => 'Перезавантаження бесід...';

  @override
  String get user => 'Користувач';

  @override
  String get starred => 'Із зірочкою';

  @override
  String get date => 'Дата';

  @override
  String get noResultsFound => 'Результатів не знайдено';

  @override
  String get tryAdjustingSearchTerms => 'Спробуйте змінити умови пошуку';

  @override
  String get starConversationsToFindQuickly => 'Позначте бесіди зіркою, щоб швидко знаходити їх тут';

  @override
  String noConversationsOnDate(String date) {
    return 'Немає бесід $date';
  }

  @override
  String get trySelectingDifferentDate => 'Спробуйте вибрати іншу дату';

  @override
  String get conversations => 'Бесіди';

  @override
  String get chat => 'Чат';

  @override
  String get actions => 'Дії';

  @override
  String get syncAvailable => 'Синхронізація доступна';

  @override
  String get referAFriend => 'Порекомендувати друга';

  @override
  String get help => 'Допомога';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Оновити до Pro';

  @override
  String get getOmiDevice => 'Отримати пристрій Omi';

  @override
  String get wearableAiCompanion => 'Носимий AI-компаньйон';

  @override
  String get loadingMemories => 'Завантаження спогадів...';

  @override
  String get allMemories => 'Всі спогади';

  @override
  String get aboutYou => 'Про вас';

  @override
  String get manual => 'Ручні';

  @override
  String get loadingYourMemories => 'Завантаження ваших спогадів...';

  @override
  String get createYourFirstMemory => 'Створіть перший спогад, щоб почати';

  @override
  String get tryAdjustingFilter => 'Спробуйте змінити параметри пошуку або фільтр';

  @override
  String get whatWouldYouLikeToRemember => 'Що ви хочете запам\'ятати?';

  @override
  String get category => 'Категорія';

  @override
  String get public => 'Публічна';

  @override
  String get failedToSaveCheckConnection => 'Не вдалося зберегти. Перевірте підключення.';

  @override
  String get createMemory => 'Створити пам\'ять';

  @override
  String get deleteMemoryConfirmation => 'Ви впевнені, що хочете видалити цю пам\'ять? Цю дію не можна скасувати.';

  @override
  String get makePrivate => 'Зробити приватною';

  @override
  String get organizeAndControlMemories => 'Організуйте та керуйте своїми спогадами';

  @override
  String get total => 'Всього';

  @override
  String get makeAllMemoriesPrivate => 'Зробити всі спогади приватними';

  @override
  String get setAllMemoriesToPrivate => 'Встановити всі спогади як приватні';

  @override
  String get makeAllMemoriesPublic => 'Зробити всі спогади публічними';

  @override
  String get setAllMemoriesToPublic => 'Встановити всі спогади як публічні';

  @override
  String get permanentlyRemoveAllMemories => 'Назавжди видалити всі спогади з Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Всі спогади тепер приватні';

  @override
  String get allMemoriesAreNowPublic => 'Всі спогади тепер публічні';

  @override
  String get clearOmisMemory => 'Очистити пам\'ять Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Ви впевнені, що хочете очистити пам\'ять Omi? Цю дію не можна скасувати, і вона назавжди видалить всі $count спогадів.';
  }

  @override
  String get omisMemoryCleared => 'Пам\'ять Omi про вас очищено';

  @override
  String get welcomeToOmi => 'Ласкаво просимо до Omi';

  @override
  String get continueWithApple => 'Продовжити з Apple';

  @override
  String get continueWithGoogle => 'Продовжити з Google';

  @override
  String get byContinuingYouAgree => 'Продовжуючи, ви погоджуєтесь з нашими ';

  @override
  String get termsOfService => 'Умовами надання послуг';

  @override
  String get and => ' та ';

  @override
  String get dataAndPrivacy => 'Дані та конфіденційність';

  @override
  String get secureAuthViaAppleId => 'Безпечна автентифікація через Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Безпечна автентифікація через обліковий запис Google';

  @override
  String get whatWeCollect => 'Що ми збираємо';

  @override
  String get dataCollectionMessage =>
      'Продовжуючи, ваші розмови, записи та особиста інформація будуть безпечно зберігатися на наших серверах для надання аналітики на основі ШІ та увімкнення всіх функцій додатку.';

  @override
  String get dataProtection => 'Захист даних';

  @override
  String get yourDataIsProtected => 'Ваші дані захищені та регулюються нашою ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Будь ласка, оберіть вашу основну мову';

  @override
  String get chooseYourLanguage => 'Оберіть вашу мову';

  @override
  String get selectPreferredLanguageForBestExperience => 'Оберіть бажану мову для найкращого досвіду Omi';

  @override
  String get searchLanguages => 'Пошук мов...';

  @override
  String get selectALanguage => 'Оберіть мову';

  @override
  String get tryDifferentSearchTerm => 'Спробуйте інший пошуковий запит';

  @override
  String get pleaseEnterYourName => 'Будь ласка, введіть ваше ім\'я';

  @override
  String get nameMustBeAtLeast2Characters => 'Ім\'я повинно містити принаймні 2 символи';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Розкажіть нам, як ви хотіли б, щоб до вас зверталися. Це допомагає персоналізувати ваш досвід Omi.';

  @override
  String charactersCount(int count) {
    return '$count символів';
  }

  @override
  String get enableFeaturesForBestExperience => 'Увімкніть функції для найкращого досвіду Omi на вашому пристрої.';

  @override
  String get microphoneAccess => 'Доступ до мікрофона';

  @override
  String get recordAudioConversations => 'Записувати аудіо розмови';

  @override
  String get microphoneAccessDescription =>
      'Omi потребує доступу до мікрофона для запису ваших розмов і надання транскрипцій.';

  @override
  String get screenRecording => 'Запис екрана';

  @override
  String get captureSystemAudioFromMeetings => 'Захоплення системного звуку зі зустрічей';

  @override
  String get screenRecordingDescription =>
      'Omi потребує дозволу на запис екрана для захоплення системного звуку з ваших зустрічей на основі браузера.';

  @override
  String get accessibility => 'Доступність';

  @override
  String get detectBrowserBasedMeetings => 'Виявлення зустрічей на основі браузера';

  @override
  String get accessibilityDescription =>
      'Omi потребує дозволу доступності для виявлення, коли ви приєднуєтесь до зустрічей Zoom, Meet або Teams у вашому браузері.';

  @override
  String get pleaseWait => 'Будь ласка, зачекайте...';

  @override
  String get joinTheCommunity => 'Приєднуйтесь до спільноти!';

  @override
  String get loadingProfile => 'Завантаження профілю...';

  @override
  String get profileSettings => 'Налаштування профілю';

  @override
  String get noEmailSet => 'Електронну пошту не встановлено';

  @override
  String get userIdCopiedToClipboard => 'ID користувача скопійовано';

  @override
  String get yourInformation => 'Ваша Інформація';

  @override
  String get setYourName => 'Встановити ваше ім\'я';

  @override
  String get changeYourName => 'Змінити ваше ім\'я';

  @override
  String get manageYourOmiPersona => 'Керування вашою персоною Omi';

  @override
  String get voiceAndPeople => 'Голос і Люди';

  @override
  String get teachOmiYourVoice => 'Навчіть Omi вашому голосу';

  @override
  String get tellOmiWhoSaidIt => 'Скажіть Omi, хто це сказав 🗣️';

  @override
  String get payment => 'Оплата';

  @override
  String get addOrChangeYourPaymentMethod => 'Додати або змінити спосіб оплати';

  @override
  String get preferences => 'Налаштування';

  @override
  String get helpImproveOmiBySharing => 'Допоможіть покращити Omi, діліться анонімними аналітичними даними';

  @override
  String get deleteAccount => 'Видалити Обліковий запис';

  @override
  String get deleteYourAccountAndAllData => 'Видалити обліковий запис та всі дані';

  @override
  String get clearLogs => 'Очистити журнали';

  @override
  String get debugLogsCleared => 'Журнали відлагодження очищено';

  @override
  String get exportConversations => 'Експорт розмов';

  @override
  String get exportAllConversationsToJson => 'Експортуйте всі свої розмови до файлу JSON.';

  @override
  String get conversationsExportStarted =>
      'Експорт розмов розпочато. Це може зайняти кілька секунд, будь ласка, зачекайте.';

  @override
  String get mcpDescription =>
      'Для підключення Omi до інших додатків для читання, пошуку та керування вашими спогадами та розмовами. Створіть ключ для початку.';

  @override
  String get apiKeys => 'Ключі API';

  @override
  String errorLabel(String error) {
    return 'Помилка: $error';
  }

  @override
  String get noApiKeysFound => 'Ключі API не знайдено. Створіть один для початку.';

  @override
  String get advancedSettings => 'Розширені налаштування';

  @override
  String get triggersWhenNewConversationCreated => 'Спрацьовує при створенні нової розмови.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Спрацьовує при отриманні нового транскрипту.';

  @override
  String get realtimeAudioBytes => 'Байти аудіо в реальному часі';

  @override
  String get triggersWhenAudioBytesReceived => 'Спрацьовує при отриманні байтів аудіо.';

  @override
  String get everyXSeconds => 'Кожні x секунд';

  @override
  String get triggersWhenDaySummaryGenerated => 'Спрацьовує при генерації підсумку дня.';

  @override
  String get tryLatestExperimentalFeatures => 'Спробуйте найновіші експериментальні функції від команди Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Діагностичний статус служби транскрипції';

  @override
  String get enableDetailedDiagnosticMessages => 'Увімкнути детальні діагностичні повідомлення від служби транскрипції';

  @override
  String get autoCreateAndTagNewSpeakers => 'Автоматично створювати та позначати нових мовців';

  @override
  String get automaticallyCreateNewPerson => 'Автоматично створювати нову особу, коли ім\'я виявлено в транскрипті.';

  @override
  String get pilotFeatures => 'Пілотні функції';

  @override
  String get pilotFeaturesDescription => 'Ці функції є тестами, і підтримка не гарантується.';

  @override
  String get suggestFollowUpQuestion => 'Запропонувати додаткове запитання';

  @override
  String get saveSettings => 'Зберегти Налаштування';

  @override
  String get syncingDeveloperSettings => 'Синхронізація налаштувань розробника...';

  @override
  String get summary => 'Резюме';

  @override
  String get auto => 'Автоматично';

  @override
  String get noSummaryForApp =>
      'Для цього застосунку немає підсумку. Спробуйте інший застосунок для кращих результатів.';

  @override
  String get tryAnotherApp => 'Спробувати інший додаток';

  @override
  String generatedBy(String appName) {
    return 'Створено $appName';
  }

  @override
  String get overview => 'Огляд';

  @override
  String get otherAppResults => 'Результати інших додатків';

  @override
  String get unknownApp => 'Невідомий застосунок';

  @override
  String get noSummaryAvailable => 'Резюме недоступне';

  @override
  String get conversationNoSummaryYet => 'Ця розмова ще не має резюме.';

  @override
  String get chooseSummarizationApp => 'Виберіть додаток для резюме';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName встановлено як додаток для резюме за замовчуванням';
  }

  @override
  String get letOmiChooseAutomatically => 'Дозвольте Omi автоматично вибрати найкращий додаток';

  @override
  String get deleteConversationConfirmation => 'Ви впевнені, що хочете видалити цю розмову? Цю дію не можна скасувати.';

  @override
  String get conversationDeleted => 'Розмову видалено';

  @override
  String get generatingLink => 'Генерація посилання...';

  @override
  String get editConversation => 'Редагувати розмову';

  @override
  String get conversationLinkCopiedToClipboard => 'Посилання на розмову скопійовано в буфер обміну';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Транскрипцію розмови скопійовано в буфер обміну';

  @override
  String get editConversationDialogTitle => 'Редагувати розмову';

  @override
  String get changeTheConversationTitle => 'Змінити назву розмови';

  @override
  String get conversationTitle => 'Назва розмови';

  @override
  String get enterConversationTitle => 'Введіть назву розмови...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Назву розмови успішно оновлено';

  @override
  String get failedToUpdateConversationTitle => 'Не вдалося оновити назву розмови';

  @override
  String get errorUpdatingConversationTitle => 'Помилка при оновленні назви розмови';

  @override
  String get settingUp => 'Налаштування...';

  @override
  String get startYourFirstRecording => 'Розпочніть свій перший запис';

  @override
  String get preparingSystemAudioCapture => 'Підготовка запису системного аудіо';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Натисніть кнопку, щоб записати аудіо для живих транскриптів, AI-інсайтів та автоматичного збереження.';

  @override
  String get reconnecting => 'Перепідключення...';

  @override
  String get recordingPaused => 'Запис призупинено';

  @override
  String get recordingActive => 'Запис активний';

  @override
  String get startRecording => 'Почати запис';

  @override
  String resumingInCountdown(String countdown) {
    return 'Відновлення через $countdownс...';
  }

  @override
  String get tapPlayToResume => 'Натисніть відтворення, щоб продовжити';

  @override
  String get listeningForAudio => 'Прослуховування аудіо...';

  @override
  String get preparingAudioCapture => 'Підготовка запису аудіо';

  @override
  String get clickToBeginRecording => 'Натисніть, щоб почати запис';

  @override
  String get translated => 'перекладено';

  @override
  String get liveTranscript => 'Живий транскрипт';

  @override
  String segmentsSingular(String count) {
    return '$count сегмент';
  }

  @override
  String segmentsPlural(String count) {
    return '$count сегментів';
  }

  @override
  String get startRecordingToSeeTranscript => 'Розпочніть запис, щоб побачити живий транскрипт';

  @override
  String get paused => 'Призупинено';

  @override
  String get initializing => 'Ініціалізація...';

  @override
  String get recording => 'Запис';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Мікрофон змінено. Відновлення через $countdownс';
  }

  @override
  String get clickPlayToResumeOrStop => 'Натисніть відтворення для продовження або зупинку для завершення';

  @override
  String get settingUpSystemAudioCapture => 'Налаштування запису системного аудіо';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Запис аудіо та створення транскрипту';

  @override
  String get clickToBeginRecordingSystemAudio => 'Натисніть, щоб почати запис системного аудіо';

  @override
  String get you => 'Ви';

  @override
  String speakerWithId(String speakerId) {
    return 'Доповідач $speakerId';
  }

  @override
  String get translatedByOmi => 'перекладено omi';

  @override
  String get backToConversations => 'Повернутися до розмов';

  @override
  String get systemAudio => 'Система';

  @override
  String get mic => 'Мікрофон';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Аудіовхід встановлено на $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Помилка перемикання аудіопристрою: $error';
  }

  @override
  String get selectAudioInput => 'Виберіть аудіовхід';

  @override
  String get loadingDevices => 'Завантаження пристроїв...';

  @override
  String get settingsHeader => 'НАЛАШТУВАННЯ';

  @override
  String get plansAndBilling => 'Плани та Оплата';

  @override
  String get calendarIntegration => 'Інтеграція Календаря';

  @override
  String get dailySummary => 'Щоденний підсумок';

  @override
  String get developer => 'Розробник';

  @override
  String get about => 'Про програму';

  @override
  String get selectTime => 'Вибрати час';

  @override
  String get accountGroup => 'Обліковий запис';

  @override
  String get signOutQuestion => 'Вийти?';

  @override
  String get signOutConfirmation => 'Ви впевнені, що хочете вийти?';

  @override
  String get customVocabularyHeader => 'КОРИСТУВАЦЬКИЙ СЛОВНИК';

  @override
  String get addWordsDescription => 'Додайте слова, які Omi має розпізнавати під час транскрипції.';

  @override
  String get enterWordsHint => 'Введіть слова (через кому)';

  @override
  String get dailySummaryHeader => 'ЩОДЕННА ЗВЕДЕННЯ';

  @override
  String get dailySummaryTitle => 'Щоденна Зведення';

  @override
  String get dailySummaryDescription => 'Отримуйте персоналізований підсумок розмов за день у вигляді сповіщення.';

  @override
  String get deliveryTime => 'Час доставки';

  @override
  String get deliveryTimeDescription => 'Коли отримувати щоденну зведення';

  @override
  String get subscription => 'Підписка';

  @override
  String get viewPlansAndUsage => 'Перегляд Планів та Використання';

  @override
  String get viewPlansDescription => 'Керуйте підпискою та переглядайте статистику використання';

  @override
  String get addOrChangePaymentMethod => 'Додати або змінити спосіб оплати';

  @override
  String get displayOptions => 'Параметри відображення';

  @override
  String get showMeetingsInMenuBar => 'Показувати зустрічі в рядку меню';

  @override
  String get displayUpcomingMeetingsDescription => 'Відображати майбутні зустрічі в рядку меню';

  @override
  String get showEventsWithoutParticipants => 'Показувати події без учасників';

  @override
  String get includePersonalEventsDescription => 'Включити особисті події без учасників';

  @override
  String get upcomingMeetings => 'Майбутні зустрічі';

  @override
  String get checkingNext7Days => 'Перевірка наступних 7 днів';

  @override
  String get shortcuts => 'Комбінації клавіш';

  @override
  String get shortcutChangeInstruction =>
      'Натисніть на комбінацію клавіш, щоб змінити її. Натисніть Escape для скасування.';

  @override
  String get configurePersonaDescription => 'Налаштуйте свою персону ШІ';

  @override
  String get configureSTTProvider => 'Налаштувати постачальника STT';

  @override
  String get setConversationEndDescription => 'Встановіть, коли розмови автоматично завершуються';

  @override
  String get importDataDescription => 'Імпортувати дані з інших джерел';

  @override
  String get exportConversationsDescription => 'Експортувати розмови в JSON';

  @override
  String get exportingConversations => 'Експорт розмов...';

  @override
  String get clearNodesDescription => 'Очистити всі вузли та з\'єднання';

  @override
  String get deleteKnowledgeGraphQuestion => 'Видалити граф знань?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Це видалить усі похідні дані графа знань. Ваші оригінальні спогади залишаться в безпеці.';

  @override
  String get connectOmiWithAI => 'Підключіть Omi до ШІ-асистентів';

  @override
  String get noAPIKeys => 'Немає ключів API. Створіть один, щоб почати.';

  @override
  String get autoCreateWhenDetected => 'Автоматично створювати при виявленні імені';

  @override
  String get trackPersonalGoals => 'Відстежувати особисті цілі на головній сторінці';

  @override
  String get dailyReflectionDescription => 'Отримуйте нагадування о 21:00 для роздумів про свій день та запису думок.';

  @override
  String get endpointURL => 'URL кінцевої точки';

  @override
  String get links => 'Посилання';

  @override
  String get discordMemberCount => 'Понад 8000 учасників у Discord';

  @override
  String get userInformation => 'Інформація про користувача';

  @override
  String get capabilities => 'Можливості';

  @override
  String get previewScreenshots => 'Попередній перегляд знімків';

  @override
  String get holdOnPreparingForm => 'Зачекайте, ми готуємо форму для вас';

  @override
  String get bySubmittingYouAgreeToOmi => 'Надсилаючи, ви погоджуєтеся з Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Умови та Політика конфіденційності';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Допомагає діагностувати проблеми. Автоматично видаляється через 3 дні.';

  @override
  String get manageYourApp => 'Керуйте своїм додатком';

  @override
  String get updatingYourApp => 'Оновлення вашого додатка';

  @override
  String get fetchingYourAppDetails => 'Отримання даних додатка';

  @override
  String get updateAppQuestion => 'Оновити додаток?';

  @override
  String get updateAppConfirmation =>
      'Ви впевнені, що хочете оновити свій додаток? Зміни набудуть чинності після перевірки нашою командою.';

  @override
  String get updateApp => 'Оновити додаток';

  @override
  String get createAndSubmitNewApp => 'Створіть і надішліть новий додаток';

  @override
  String appsCount(String count) {
    return 'Додатки ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Приватні додатки ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Публічні додатки ($count)';
  }

  @override
  String get newVersionAvailable => 'Доступна нова версія  🎉';

  @override
  String get no => 'Ні';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Підписку успішно скасовано. Вона залишиться активною до кінця поточного розрахункового періоду.';

  @override
  String get failedToCancelSubscription => 'Не вдалося скасувати підписку. Будь ласка, спробуйте ще раз.';

  @override
  String get invalidPaymentUrl => 'Недійсний URL оплати';

  @override
  String get permissionsAndTriggers => 'Дозволи та тригери';

  @override
  String get chatFeatures => 'Функції чату';

  @override
  String get uninstall => 'Видалити';

  @override
  String get installs => 'ВСТАНОВЛЕННЯ';

  @override
  String get priceLabel => 'ЦІНА';

  @override
  String get updatedLabel => 'ОНОВЛЕНО';

  @override
  String get createdLabel => 'СТВОРЕНО';

  @override
  String get featuredLabel => 'РЕКОМЕНДОВАНО';

  @override
  String get cancelSubscriptionQuestion => 'Скасувати підписку?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Ви впевнені, що хочете скасувати підписку? Ви матимете доступ до кінця поточного розрахункового періоду.';

  @override
  String get cancelSubscriptionButton => 'Скасувати підписку';

  @override
  String get cancelling => 'Скасування...';

  @override
  String get betaTesterMessage => 'Ви бета-тестер цього додатка. Він ще не публічний. Стане публічним після схвалення.';

  @override
  String get appUnderReviewMessage => 'Ваш додаток на розгляді і видимий тільки вам. Стане публічним після схвалення.';

  @override
  String get appRejectedMessage => 'Ваш додаток відхилено. Оновіть дані та надішліть повторно на розгляд.';

  @override
  String get invalidIntegrationUrl => 'Недійсна URL інтеграції';

  @override
  String get tapToComplete => 'Натисніть для завершення';

  @override
  String get invalidSetupInstructionsUrl => 'Недійсна URL інструкцій з налаштування';

  @override
  String get pushToTalk => 'Натисни і говори';

  @override
  String get summaryPrompt => 'Промпт для резюме';

  @override
  String get pleaseSelectARating => 'Будь ласка, виберіть оцінку';

  @override
  String get reviewAddedSuccessfully => 'Відгук успішно додано 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Відгук успішно оновлено 🚀';

  @override
  String get failedToSubmitReview => 'Не вдалося надіслати відгук. Будь ласка, спробуйте ще раз.';

  @override
  String get addYourReview => 'Додайте свій відгук';

  @override
  String get editYourReview => 'Редагувати свій відгук';

  @override
  String get writeAReviewOptional => 'Написати відгук (необов\'язково)';

  @override
  String get submitReview => 'Надіслати відгук';

  @override
  String get updateReview => 'Оновити відгук';

  @override
  String get yourReview => 'Ваш відгук';

  @override
  String get anonymousUser => 'Анонімний користувач';

  @override
  String get issueActivatingApp => 'Виникла проблема з активацією цього додатка. Будь ласка, спробуйте ще раз.';

  @override
  String get dataAccessNoticeDescription =>
      'Цей додаток отримає доступ до ваших даних. Omi AI не несе відповідальності за те, як ваші дані використовуються, змінюються або видаляються цим додатком';

  @override
  String get copyUrl => 'Копіювати URL';

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
  String get weekdaySun => 'Нд';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Інтеграція з $serviceName незабаром';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Вже експортовано до $platform';
  }

  @override
  String get anotherPlatform => 'іншу платформу';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Будь ласка, авторизуйтесь в $serviceName у Налаштування > Інтеграції завдань';
  }

  @override
  String addingToService(String serviceName) {
    return 'Додавання до $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Додано до $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Не вдалося додати до $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Дозвіл для Apple Reminders відхилено';

  @override
  String failedToCreateApiKey(String error) {
    return 'Не вдалося створити API-ключ провайдера: $error';
  }

  @override
  String get createAKey => 'Створити ключ';

  @override
  String get apiKeyRevokedSuccessfully => 'API-ключ успішно відкликано';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Не вдалося відкликати API-ключ: $error';
  }

  @override
  String get omiApiKeys => 'API-ключі Omi';

  @override
  String get apiKeysDescription =>
      'API-ключі використовуються для автентифікації, коли ваш додаток взаємодіє з сервером OMI. Вони дозволяють вашому додатку створювати спогади та безпечно отримувати доступ до інших сервісів OMI.';

  @override
  String get aboutOmiApiKeys => 'Про API-ключі Omi';

  @override
  String get yourNewKey => 'Ваш новий ключ:';

  @override
  String get copyToClipboard => 'Копіювати в буфер обміну';

  @override
  String get pleaseCopyKeyNow => 'Будь ласка, скопіюйте його зараз і запишіть у безпечному місці. ';

  @override
  String get willNotSeeAgain => 'Ви не зможете побачити його знову.';

  @override
  String get revokeKey => 'Відкликати ключ';

  @override
  String get revokeApiKeyQuestion => 'Відкликати API-ключ?';

  @override
  String get revokeApiKeyWarning =>
      'Цю дію не можна скасувати. Будь-які додатки, що використовують цей ключ, більше не зможуть отримати доступ до API.';

  @override
  String get revoke => 'Відкликати';

  @override
  String get whatWouldYouLikeToCreate => 'Що ви хочете створити?';

  @override
  String get createAnApp => 'Створити додаток';

  @override
  String get createAndShareYourApp => 'Створіть і поділіться своїм додатком';

  @override
  String get createMyClone => 'Створити мій клон';

  @override
  String get createYourDigitalClone => 'Створіть свій цифровий клон';

  @override
  String get itemApp => 'Додаток';

  @override
  String get itemPersona => 'Персона';

  @override
  String keepItemPublic(String item) {
    return 'Залишити $item публічним';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Зробити $item публічним?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Зробити $item приватним?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Якщо ви зробите $item публічним, ним зможуть користуватися всі';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Якщо ви зараз зробите $item приватним, він перестане працювати для всіх і буде видимий тільки вам';
  }

  @override
  String get manageApp => 'Керувати додатком';

  @override
  String get updatePersonaDetails => 'Оновити деталі персони';

  @override
  String deleteItemTitle(String item) {
    return 'Видалити $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Видалити $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Ви впевнені, що хочете видалити цей $item? Цю дію неможливо скасувати.';
  }

  @override
  String get revokeKeyQuestion => 'Відкликати ключ?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Ви впевнені, що хочете відкликати ключ \"$keyName\"? Цю дію неможливо скасувати.';
  }

  @override
  String get createNewKey => 'Створити новий ключ';

  @override
  String get keyNameHint => 'напр., Claude Desktop';

  @override
  String get pleaseEnterAName => 'Будь ласка, введіть назву.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Не вдалося створити ключ: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Не вдалося створити ключ. Будь ласка, спробуйте ще раз.';

  @override
  String get keyCreated => 'Ключ створено';

  @override
  String get keyCreatedMessage =>
      'Ваш новий ключ створено. Будь ласка, скопіюйте його зараз. Ви більше не зможете його побачити.';

  @override
  String get keyWord => 'Ключ';

  @override
  String get externalAppAccess => 'Доступ зовнішніх додатків';

  @override
  String get externalAppAccessDescription =>
      'Наступні встановлені додатки мають зовнішні інтеграції та можуть отримати доступ до ваших даних, таких як розмови та спогади.';

  @override
  String get noExternalAppsHaveAccess => 'Жоден зовнішній додаток не має доступу до ваших даних.';

  @override
  String get maximumSecurityE2ee => 'Максимальна безпека (E2EE)';

  @override
  String get e2eeDescription =>
      'Наскрізне шифрування є золотим стандартом конфіденційності. Коли ввімкнено, ваші дані шифруються на вашому пристрої перед відправленням на наші сервери. Це означає, що ніхто, навіть Omi, не може отримати доступ до вашого вмісту.';

  @override
  String get importantTradeoffs => 'Важливі компроміси:';

  @override
  String get e2eeTradeoff1 => '• Деякі функції, такі як інтеграції із зовнішніми додатками, можуть бути вимкнені.';

  @override
  String get e2eeTradeoff2 => '• Якщо ви втратите пароль, ваші дані не можуть бути відновлені.';

  @override
  String get featureComingSoon => 'Ця функція незабаром зявиться!';

  @override
  String get migrationInProgressMessage =>
      'Міграція виконується. Ви не можете змінити рівень захисту, поки вона не завершиться.';

  @override
  String get migrationFailed => 'Міграція не вдалася';

  @override
  String migratingFromTo(String source, String target) {
    return 'Міграція з $source до $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total обєктів';
  }

  @override
  String get secureEncryption => 'Безпечне шифрування';

  @override
  String get secureEncryptionDescription =>
      'Ваші дані зашифровані унікальним для вас ключем на наших серверах, розміщених у Google Cloud. Це означає, що ваш необроблений вміст недоступний нікому, включаючи співробітників Omi або Google, безпосередньо з бази даних.';

  @override
  String get endToEndEncryption => 'Наскрізне шифрування';

  @override
  String get e2eeCardDescription =>
      'Увімкніть для максимальної безпеки, де тільки ви можете отримати доступ до своїх даних. Торкніться, щоб дізнатися більше.';

  @override
  String get dataAlwaysEncrypted =>
      'Незалежно від рівня, ваші дані завжди зашифровані в стані спокою та під час передачі.';

  @override
  String get readOnlyScope => 'Лише читання';

  @override
  String get fullAccessScope => 'Повний доступ';

  @override
  String get readScope => 'Читання';

  @override
  String get writeScope => 'Запис';

  @override
  String get apiKeyCreated => 'API ключ створено!';

  @override
  String get saveKeyWarning => 'Збережіть цей ключ зараз! Ви більше не зможете його побачити.';

  @override
  String get yourApiKey => 'ВАШ API КЛЮЧ';

  @override
  String get tapToCopy => 'Торкніться, щоб скопіювати';

  @override
  String get copyKey => 'Копіювати ключ';

  @override
  String get createApiKey => 'Створити API ключ';

  @override
  String get accessDataProgrammatically => 'Програмний доступ до ваших даних';

  @override
  String get keyNameLabel => 'НАЗВА КЛЮЧА';

  @override
  String get keyNamePlaceholder => 'напр., Моя інтеграція';

  @override
  String get permissionsLabel => 'ДОЗВОЛИ';

  @override
  String get permissionsInfoNote => 'R = Читання, W = Запис. За замовчуванням лише читання, якщо нічого не вибрано.';

  @override
  String get developerApi => 'API розробника';

  @override
  String get createAKeyToGetStarted => 'Створіть ключ, щоб почати';

  @override
  String errorWithMessage(String error) {
    return 'Помилка: $error';
  }

  @override
  String get omiTraining => 'Навчання Omi';

  @override
  String get trainingDataProgram => 'Програма даних для навчання';

  @override
  String get getOmiUnlimitedFree => 'Отримайте Omi Unlimited безкоштовно, надавши свої дані для навчання моделей ШІ.';

  @override
  String get trainingDataBullets =>
      '• Ваші дані допомагають покращувати моделі ШІ\n• Передаються лише нечутливі дані\n• Повністю прозорий процес';

  @override
  String get learnMoreAtOmiTraining => 'Дізнайтеся більше на omi.me/training';

  @override
  String get agreeToContributeData => 'Я розумію і погоджуюсь надати свої дані для навчання ШІ';

  @override
  String get submitRequest => 'Надіслати запит';

  @override
  String get thankYouRequestUnderReview => 'Дякуємо! Ваш запит розглядається. Ми повідомимо вас після схвалення.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Ваш план залишиться активним до $date. Після цього ви втратите доступ до необмежених функцій. Ви впевнені?';
  }

  @override
  String get confirmCancellation => 'Підтвердити скасування';

  @override
  String get keepMyPlan => 'Зберегти мій план';

  @override
  String get subscriptionSetToCancel => 'Вашу підписку встановлено для скасування в кінці періоду.';

  @override
  String get switchedToOnDevice => 'Переключено на транскрипцію на пристрої';

  @override
  String get couldNotSwitchToFreePlan => 'Не вдалося перейти на безкоштовний план. Будь ласка, спробуйте ще раз.';

  @override
  String get couldNotLoadPlans => 'Не вдалося завантажити доступні плани. Будь ласка, спробуйте ще раз.';

  @override
  String get selectedPlanNotAvailable => 'Вибраний план недоступний. Будь ласка, спробуйте ще раз.';

  @override
  String get upgradeToAnnualPlan => 'Оновити до річного плану';

  @override
  String get importantBillingInfo => 'Важлива інформація про виставлення рахунків:';

  @override
  String get monthlyPlanContinues => 'Ваш поточний місячний план продовжуватиметься до кінця розрахункового періоду';

  @override
  String get paymentMethodCharged =>
      'Ваш існуючий спосіб оплати буде автоматично списано, коли закінчиться ваш місячний план';

  @override
  String get annualSubscriptionStarts => 'Ваша 12-місячна річна підписка розпочнеться автоматично після списання';

  @override
  String get thirteenMonthsCoverage =>
      'Ви отримаєте 13 місяців покриття загалом (поточний місяць + 12 місяців річної підписки)';

  @override
  String get confirmUpgrade => 'Підтвердити оновлення';

  @override
  String get confirmPlanChange => 'Підтвердити зміну плану';

  @override
  String get confirmAndProceed => 'Підтвердити і продовжити';

  @override
  String get upgradeScheduled => 'Оновлення заплановано';

  @override
  String get changePlan => 'Змінити план';

  @override
  String get upgradeAlreadyScheduled => 'Ваше оновлення до річного плану вже заплановано';

  @override
  String get youAreOnUnlimitedPlan => 'Ви на плані Безлімітний.';

  @override
  String get yourOmiUnleashed => 'Ваш Omi, розкритий. Перейдіть на безлімітний для безмежних можливостей.';

  @override
  String planEndedOn(String date) {
    return 'Ваш план закінчився $date.\\nПідпишіться знову зараз - з вас буде негайно списано за новий розрахунковий період.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Ваш план налаштовано на скасування $date.\\nПідпишіться знову, щоб зберегти переваги - без оплати до $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Ваш річний план розпочнеться автоматично, коли закінчиться ваш місячний план.';

  @override
  String planRenewsOn(String date) {
    return 'Ваш план поновлюється $date.';
  }

  @override
  String get unlimitedConversations => 'Необмежені розмови';

  @override
  String get askOmiAnything => 'Запитайте Omi будь-що про своє життя';

  @override
  String get unlockOmiInfiniteMemory => 'Розблокуйте безмежну пам\'ять Omi';

  @override
  String get youreOnAnnualPlan => 'Ви на річному плані';

  @override
  String get alreadyBestValuePlan => 'У вас вже найвигідніший план. Зміни не потрібні.';

  @override
  String get unableToLoadPlans => 'Не вдається завантажити плани';

  @override
  String get checkConnectionTryAgain => 'Перевірте з\'єднання і спробуйте ще раз';

  @override
  String get useFreePlan => 'Використати безкоштовний план';

  @override
  String get continueText => 'Продовжити';

  @override
  String get resubscribe => 'Підписатися знову';

  @override
  String get couldNotOpenPaymentSettings => 'Не вдалося відкрити налаштування оплати. Будь ласка, спробуйте ще раз.';

  @override
  String get managePaymentMethod => 'Керування способом оплати';

  @override
  String get cancelSubscription => 'Скасувати підписку';

  @override
  String endsOnDate(String date) {
    return 'Закінчується $date';
  }

  @override
  String get active => 'Активний';

  @override
  String get freePlan => 'Безкоштовний план';

  @override
  String get configure => 'Налаштувати';

  @override
  String get privacyInformation => 'Інформація про конфіденційність';

  @override
  String get yourPrivacyMattersToUs => 'Ваша конфіденційність важлива для нас';

  @override
  String get privacyIntroText =>
      'В Omi ми дуже серйозно ставимося до вашої конфіденційності. Ми хочемо бути прозорими щодо даних, які збираємо, і як їх використовуємо. Ось що вам потрібно знати:';

  @override
  String get whatWeTrack => 'Що ми відстежуємо';

  @override
  String get anonymityAndPrivacy => 'Анонімність і конфіденційність';

  @override
  String get optInAndOptOutOptions => 'Опції згоди та відмови';

  @override
  String get ourCommitment => 'Наше зобов\'язання';

  @override
  String get commitmentText =>
      'Ми зобов\'язуємося використовувати зібрані дані лише для того, щоб зробити Omi кращим продуктом для вас. Ваша конфіденційність і довіра є для нас найважливішими.';

  @override
  String get thankYouText =>
      'Дякуємо, що ви цінний користувач Omi. Якщо у вас є запитання чи занепокоєння, зв\'яжіться з нами за адресою team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Налаштування синхронізації WiFi';

  @override
  String get enterHotspotCredentials => 'Введіть облікові дані точки доступу телефону';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi синхронізація використовує телефон як точку доступу. Знайдіть ім\'я та пароль у Налаштування > Режим модема.';

  @override
  String get hotspotNameSsid => 'Ім\'я точки доступу (SSID)';

  @override
  String get exampleIphoneHotspot => 'напр. iPhone Hotspot';

  @override
  String get password => 'Пароль';

  @override
  String get enterHotspotPassword => 'Введіть пароль точки доступу';

  @override
  String get saveCredentials => 'Зберегти облікові дані';

  @override
  String get clearCredentials => 'Очистити облікові дані';

  @override
  String get pleaseEnterHotspotName => 'Будь ласка, введіть ім\'я точки доступу';

  @override
  String get wifiCredentialsSaved => 'Облікові дані WiFi збережено';

  @override
  String get wifiCredentialsCleared => 'Облікові дані WiFi очищено';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Підсумок створено для $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Не вдалося створити підсумок. Переконайтеся, що у вас є розмови за цей день.';

  @override
  String get summaryNotFound => 'Підсумок не знайдено';

  @override
  String get yourDaysJourney => 'Ваша подорож за день';

  @override
  String get highlights => 'Основні моменти';

  @override
  String get unresolvedQuestions => 'Невирішені питання';

  @override
  String get decisions => 'Рішення';

  @override
  String get learnings => 'Висновки';

  @override
  String get autoDeletesAfterThreeDays => 'Автоматично видаляється через 3 дні.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Граф знань успішно видалено';

  @override
  String get exportStartedMayTakeFewSeconds => 'Експорт розпочато. Це може зайняти кілька секунд...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Це видалить усі похідні дані графа знань (вузли та з\'єднання). Ваші оригінальні спогади залишаться в безпеці. Граф буде відновлено з часом або за наступним запитом.';

  @override
  String get configureDailySummaryDigest => 'Налаштуйте щоденний підсумок завдань';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Доступ до $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'запускається $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription і $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Конкретний доступ до даних не налаштовано.';

  @override
  String get basicPlanDescription => '1 200 преміум хвилин + необмежено на пристрої';

  @override
  String get minutes => 'хвилин';

  @override
  String get omiHas => 'У Omi:';

  @override
  String get premiumMinutesUsed => 'Преміум хвилини використано.';

  @override
  String get setupOnDevice => 'Налаштувати на пристрої';

  @override
  String get forUnlimitedFreeTranscription => 'для необмеженої безкоштовної транскрипції.';

  @override
  String premiumMinsLeft(int count) {
    return 'Залишилось $count преміум хвилин.';
  }

  @override
  String get alwaysAvailable => 'завжди доступно.';

  @override
  String get importHistory => 'Історія імпорту';

  @override
  String get noImportsYet => 'Імпортів поки немає';

  @override
  String get selectZipFileToImport => 'Виберіть .zip файл для імпорту!';

  @override
  String get otherDevicesComingSoon => 'Інші пристрої незабаром';

  @override
  String get deleteAllLimitlessConversations => 'Видалити всі розмови Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Це назавжди видалить усі розмови, імпортовані з Limitless. Цю дію не можна скасувати.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Видалено $count розмов Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Не вдалося видалити розмови';

  @override
  String get deleteImportedData => 'Видалити імпортовані дані';

  @override
  String get statusPending => 'Очікує';

  @override
  String get statusProcessing => 'Обробка';

  @override
  String get statusCompleted => 'Завершено';

  @override
  String get statusFailed => 'Помилка';

  @override
  String nConversations(int count) {
    return '$count розмов';
  }

  @override
  String get pleaseEnterName => 'Будь ласка, введіть ім\'я';

  @override
  String get nameMustBeBetweenCharacters => 'Ім\'я має бути від 2 до 40 символів';

  @override
  String get deleteSampleQuestion => 'Видалити зразок?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Ви впевнені, що хочете видалити зразок $name?';
  }

  @override
  String get confirmDeletion => 'Підтвердити видалення';

  @override
  String deletePersonConfirmation(String name) {
    return 'Ви впевнені, що хочете видалити $name? Це також видалить усі пов\'язані зразки мовлення.';
  }

  @override
  String get howItWorksTitle => 'Як це працює?';

  @override
  String get howPeopleWorks =>
      'Після створення особи ви можете перейти до транскрипції розмови та призначити їм відповідні сегменти, таким чином Omi зможе розпізнавати і їхнє мовлення!';

  @override
  String get tapToDelete => 'Торкніться, щоб видалити';

  @override
  String get newTag => 'НОВЕ';

  @override
  String get needHelpChatWithUs => 'Потрібна допомога? Напишіть нам';

  @override
  String get localStorageEnabled => 'Локальне сховище увімкнено';

  @override
  String get localStorageDisabled => 'Локальне сховище вимкнено';

  @override
  String failedToUpdateSettings(String error) {
    return 'Не вдалося оновити налаштування: $error';
  }

  @override
  String get privacyNotice => 'Повідомлення про конфіденційність';

  @override
  String get recordingsMayCaptureOthers =>
      'Записи можуть фіксувати голоси інших людей. Перед увімкненням переконайтеся, що ви отримали згоду від усіх учасників.';

  @override
  String get enable => 'Увімкнути';

  @override
  String get storeAudioOnPhone => 'Зберігати аудіо на телефоні';

  @override
  String get on => 'Увімк.';

  @override
  String get storeAudioDescription =>
      'Зберігайте всі аудіозаписи локально на телефоні. Коли вимкнено, зберігаються лише невдалі завантаження для економії місця.';

  @override
  String get enableLocalStorage => 'Увімкнути локальне сховище';

  @override
  String get cloudStorageEnabled => 'Хмарне сховище увімкнено';

  @override
  String get cloudStorageDisabled => 'Хмарне сховище вимкнено';

  @override
  String get enableCloudStorage => 'Увімкнути хмарне сховище';

  @override
  String get storeAudioOnCloud => 'Зберігати аудіо в хмарі';

  @override
  String get cloudStorageDialogMessage =>
      'Ваші записи в реальному часі зберігатимуться в приватному хмарному сховищі під час розмови.';

  @override
  String get storeAudioCloudDescription =>
      'Зберігайте записи в реальному часі в приватному хмарному сховищі під час розмови. Аудіо захоплюється та безпечно зберігається в реальному часі.';

  @override
  String get downloadingFirmware => 'Завантаження прошивки';

  @override
  String get installingFirmware => 'Встановлення прошивки';

  @override
  String get firmwareUpdateWarning =>
      'Не закривайте програму та не вимикайте пристрій. Це може пошкодити ваш пристрій.';

  @override
  String get firmwareUpdated => 'Прошивку оновлено';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Будь ласка, перезавантажте $deviceName, щоб завершити оновлення.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Ваш пристрій оновлено';

  @override
  String get currentVersion => 'Поточна версія';

  @override
  String get latestVersion => 'Остання версія';

  @override
  String get whatsNew => 'Що нового';

  @override
  String get installUpdate => 'Встановити оновлення';

  @override
  String get updateNow => 'Оновити зараз';

  @override
  String get updateGuide => 'Посібник з оновлення';

  @override
  String get checkingForUpdates => 'Перевірка оновлень';

  @override
  String get checkingFirmwareVersion => 'Перевірка версії прошивки...';

  @override
  String get firmwareUpdate => 'Оновлення прошивки';

  @override
  String get payments => 'Платежі';

  @override
  String get connectPaymentMethodInfo =>
      'Підключіть спосіб оплати нижче, щоб почати отримувати виплати за ваші додатки.';

  @override
  String get selectedPaymentMethod => 'Обраний спосіб оплати';

  @override
  String get availablePaymentMethods => 'Доступні способи оплати';

  @override
  String get activeStatus => 'Активний';

  @override
  String get connectedStatus => 'Підключено';

  @override
  String get notConnectedStatus => 'Не підключено';

  @override
  String get setActive => 'Встановити активним';

  @override
  String get getPaidThroughStripe => 'Отримуйте оплату за продажі додатків через Stripe';

  @override
  String get monthlyPayouts => 'Щомісячні виплати';

  @override
  String get monthlyPayoutsDescription => 'Отримуйте щомісячні виплати прямо на рахунок, коли заробите \$10';

  @override
  String get secureAndReliable => 'Безпечно та надійно';

  @override
  String get stripeSecureDescription => 'Stripe забезпечує безпечні та своєчасні перекази доходів від додатка';

  @override
  String get selectYourCountry => 'Виберіть свою країну';

  @override
  String get countrySelectionPermanent => 'Вибір країни є постійним і не може бути змінений пізніше.';

  @override
  String get byClickingConnectNow => 'Натискаючи \"Підключити зараз\", ви погоджуєтесь з';

  @override
  String get stripeConnectedAccountAgreement => 'Угода про підключений обліковий запис Stripe';

  @override
  String get errorConnectingToStripe => 'Помилка підключення до Stripe! Будь ласка, спробуйте пізніше.';

  @override
  String get connectingYourStripeAccount => 'Підключення вашого облікового запису Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Будь ласка, завершіть процес реєстрації Stripe у вашому браузері. Ця сторінка автоматично оновиться після завершення.';

  @override
  String get failedTryAgain => 'Не вдалося? Спробувати знову';

  @override
  String get illDoItLater => 'Зроблю це пізніше';

  @override
  String get successfullyConnected => 'Успішно підключено!';

  @override
  String get stripeReadyForPayments =>
      'Ваш обліковий запис Stripe готовий отримувати платежі. Ви можете одразу почати заробляти на продажах додатків.';

  @override
  String get updateStripeDetails => 'Оновити дані Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Помилка оновлення даних Stripe! Будь ласка, спробуйте пізніше.';

  @override
  String get updatePayPal => 'Оновити PayPal';

  @override
  String get setUpPayPal => 'Налаштувати PayPal';

  @override
  String get updatePayPalAccountDetails => 'Оновіть дані вашого облікового запису PayPal';

  @override
  String get connectPayPalToReceivePayments =>
      'Підключіть свій обліковий запис PayPal, щоб почати отримувати платежі за ваші додатки';

  @override
  String get paypalEmail => 'Email PayPal';

  @override
  String get paypalMeLink => 'Посилання PayPal.me';

  @override
  String get stripeRecommendation =>
      'Якщо Stripe доступний у вашій країні, ми наполегливо рекомендуємо використовувати його для швидших і простіших виплат.';

  @override
  String get updatePayPalDetails => 'Оновити дані PayPal';

  @override
  String get savePayPalDetails => 'Зберегти дані PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Будь ласка, введіть ваш email PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Будь ласка, введіть ваше посилання PayPal.me';

  @override
  String get doNotIncludeHttpInLink => 'Не включайте http, https або www у посилання';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Будь ласка, введіть дійсне посилання PayPal.me';

  @override
  String get pleaseEnterValidEmail => 'Будь ласка, введіть дійсну адресу електронної пошти';

  @override
  String get syncingYourRecordings => 'Синхронізація ваших записів';

  @override
  String get syncYourRecordings => 'Синхронізуйте ваші записи';

  @override
  String get syncNow => 'Синхронізувати зараз';

  @override
  String get error => 'Помилка';

  @override
  String get speechSamples => 'Зразки голосу';

  @override
  String additionalSampleIndex(String index) {
    return 'Додатковий зразок $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Тривалість: $seconds секунд';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Додатковий зразок голосу видалено';

  @override
  String get consentDataMessage =>
      'Продовжуючи, всі дані, якими ви ділитесь з цим додатком (включаючи ваші розмови, записи та особисту інформацію), будуть надійно зберігатися на наших серверах, щоб надавати вам аналітику на основі ШІ та увімкнути всі функції додатку.';

  @override
  String get tasksEmptyStateMessage => 'Завдання з ваших розмов з\'являться тут.\nНатисніть +, щоб створити вручну.';

  @override
  String get clearChatAction => 'Очистити чат';

  @override
  String get enableApps => 'Увімкнути додатки';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'показати більше ↓';

  @override
  String get showLess => 'показати менше ↑';

  @override
  String get loadingYourRecording => 'Завантаження запису...';

  @override
  String get photoDiscardedMessage => 'Це фото було відхилено, оскільки воно не було значущим.';

  @override
  String get analyzing => 'Аналіз...';

  @override
  String get searchCountries => 'Пошук країн...';

  @override
  String get checkingAppleWatch => 'Перевірка Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Встановіть Omi на\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Щоб використовувати Apple Watch з Omi, спочатку потрібно встановити додаток Omi на годинник.';

  @override
  String get openOmiOnAppleWatch => 'Відкрийте Omi на\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Додаток Omi встановлено на Apple Watch. Відкрийте його та натисніть Старт.';

  @override
  String get openWatchApp => 'Відкрити додаток Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Я встановив і відкрив додаток';

  @override
  String get unableToOpenWatchApp =>
      'Не вдалося відкрити додаток Apple Watch. Відкрийте додаток Watch вручну на Apple Watch і встановіть Omi з розділу \"Доступні додатки\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch успішно підключено!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch досі недоступний. Переконайтеся, що додаток Omi відкритий на годиннику.';

  @override
  String errorCheckingConnection(String error) {
    return 'Помилка перевірки підключення: $error';
  }

  @override
  String get muted => 'Вимкнено звук';

  @override
  String get processNow => 'Обробити зараз';

  @override
  String get finishedConversation => 'Завершити розмову?';

  @override
  String get stopRecordingConfirmation => 'Ви впевнені, що хочете зупинити запис і підсумувати розмову зараз?';

  @override
  String get conversationEndsManually => 'Розмова завершиться лише вручну.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Розмова підсумовується після $minutes хвилин$suffix мовчання.';
  }

  @override
  String get dontAskAgain => 'Більше не питати';

  @override
  String get waitingForTranscriptOrPhotos => 'Очікування транскрипції або фотографій...';

  @override
  String get noSummaryYet => 'Ще немає підсумку';

  @override
  String hints(String text) {
    return 'Підказки: $text';
  }

  @override
  String get testConversationPrompt => 'Тестувати запит розмови';

  @override
  String get prompt => 'Запит';

  @override
  String get result => 'Результат:';

  @override
  String get compareTranscripts => 'Порівняти транскрипції';

  @override
  String get notHelpful => 'Не корисно';

  @override
  String get exportTasksWithOneTap => 'Експортуйте завдання одним дотиком!';

  @override
  String get inProgress => 'В процесі';

  @override
  String get photos => 'Фото';

  @override
  String get rawData => 'Необроблені дані';

  @override
  String get content => 'Вміст';

  @override
  String get noContentToDisplay => 'Немає вмісту для відображення';

  @override
  String get noSummary => 'Немає підсумку';

  @override
  String get updateOmiFirmware => 'Оновити прошивку omi';

  @override
  String get anErrorOccurredTryAgain => 'Сталася помилка. Будь ласка, спробуйте ще раз.';

  @override
  String get welcomeBackSimple => 'З поверненням';

  @override
  String get addVocabularyDescription => 'Додайте слова, які Omi повинен розпізнавати під час транскрипції.';

  @override
  String get enterWordsCommaSeparated => 'Введіть слова (через кому)';

  @override
  String get whenToReceiveDailySummary => 'Коли отримувати щоденний підсумок';

  @override
  String get checkingNextSevenDays => 'Перевірка наступних 7 днів';

  @override
  String failedToDeleteError(String error) {
    return 'Не вдалося видалити: $error';
  }

  @override
  String get developerApiKeys => 'API-ключі розробника';

  @override
  String get noApiKeysCreateOne => 'Немає API-ключів. Створіть один, щоб почати.';

  @override
  String get commandRequired => '⌘ обов\'язкова';

  @override
  String get spaceKey => 'Пробіл';

  @override
  String loadMoreRemaining(String count) {
    return 'Завантажити ще ($count залишилося)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Топ $percentile% користувач';
  }

  @override
  String get wrappedMinutes => 'хвилин';

  @override
  String get wrappedConversations => 'розмов';

  @override
  String get wrappedDaysActive => 'активних днів';

  @override
  String get wrappedYouTalkedAbout => 'Ви говорили про';

  @override
  String get wrappedActionItems => 'Завдання';

  @override
  String get wrappedTasksCreated => 'створених завдань';

  @override
  String get wrappedCompleted => 'виконано';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% завершеність';
  }

  @override
  String get wrappedYourTopDays => 'Ваші найкращі дні';

  @override
  String get wrappedBestMoments => 'Найкращі моменти';

  @override
  String get wrappedMyBuddies => 'Мої друзі';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Не міг перестати говорити про';

  @override
  String get wrappedShow => 'СЕРІАЛ';

  @override
  String get wrappedMovie => 'ФІЛЬМ';

  @override
  String get wrappedBook => 'КНИГА';

  @override
  String get wrappedCelebrity => 'ЗНАМЕНИТІСТЬ';

  @override
  String get wrappedFood => 'ЇЖА';

  @override
  String get wrappedMovieRecs => 'Рекомендації фільмів для друзів';

  @override
  String get wrappedBiggest => 'Найбільший';

  @override
  String get wrappedStruggle => 'Виклик';

  @override
  String get wrappedButYouPushedThrough => 'Але ви впоралися 💪';

  @override
  String get wrappedWin => 'Перемога';

  @override
  String get wrappedYouDidIt => 'У вас вийшло! 🎉';

  @override
  String get wrappedTopPhrases => 'Топ-5 фраз';

  @override
  String get wrappedMins => 'хв';

  @override
  String get wrappedConvos => 'розмов';

  @override
  String get wrappedDays => 'днів';

  @override
  String get wrappedMyBuddiesLabel => 'МОЇ ДРУЗІ';

  @override
  String get wrappedObsessionsLabel => 'ЗАХОПЛЕННЯ';

  @override
  String get wrappedStruggleLabel => 'ВИКЛИК';

  @override
  String get wrappedWinLabel => 'ПЕРЕМОГА';

  @override
  String get wrappedTopPhrasesLabel => 'ТОП ФРАЗ';

  @override
  String get wrappedLetsHitRewind => 'Давай перемотаємо твій';

  @override
  String get wrappedGenerateMyWrapped => 'Створити мій Wrapped';

  @override
  String get wrappedProcessingDefault => 'Обробка...';

  @override
  String get wrappedCreatingYourStory => 'Створюємо твою\nісторію 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Щось пішло\nне так';

  @override
  String get wrappedAnErrorOccurred => 'Сталася помилка';

  @override
  String get wrappedTryAgain => 'Спробувати ще';

  @override
  String get wrappedNoDataAvailable => 'Дані недоступні';

  @override
  String get wrappedOmiLifeRecap => 'Огляд життя Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Свайпни вгору, щоб почати';

  @override
  String get wrappedShareText => 'Мій 2025, збережений Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Не вдалося поділитися. Будь ласка, спробуйте ще раз.';

  @override
  String get wrappedFailedToStartGeneration => 'Не вдалося почати генерацію. Будь ласка, спробуйте ще раз.';

  @override
  String get wrappedStarting => 'Запуск...';

  @override
  String get wrappedShare => 'Поділитися';

  @override
  String get wrappedShareYourWrapped => 'Поділися своїм Wrapped';

  @override
  String get wrappedMy2025 => 'Мій 2025';

  @override
  String get wrappedRememberedByOmi => 'збережений Omi';

  @override
  String get wrappedMostFunDay => 'Найвеселіший';

  @override
  String get wrappedMostProductiveDay => 'Найпродуктивніший';

  @override
  String get wrappedMostIntenseDay => 'Найінтенсивніший';

  @override
  String get wrappedFunniestMoment => 'Найсмішніший';

  @override
  String get wrappedMostCringeMoment => 'Найніяковіший';

  @override
  String get wrappedMinutesLabel => 'хвилин';

  @override
  String get wrappedConversationsLabel => 'розмов';

  @override
  String get wrappedDaysActiveLabel => 'активних днів';

  @override
  String get wrappedTasksGenerated => 'завдань створено';

  @override
  String get wrappedTasksCompleted => 'завдань виконано';

  @override
  String get wrappedTopFivePhrases => 'Топ-5 фраз';

  @override
  String get wrappedAGreatDay => 'Чудовий день';

  @override
  String get wrappedGettingItDone => 'Зробити це';

  @override
  String get wrappedAChallenge => 'Виклик';

  @override
  String get wrappedAHilariousMoment => 'Смішний момент';

  @override
  String get wrappedThatAwkwardMoment => 'Той ніяковий момент';

  @override
  String get wrappedYouHadFunnyMoments => 'У тебе були смішні моменти цього року!';

  @override
  String get wrappedWeveAllBeenThere => 'Ми всі через це проходили!';

  @override
  String get wrappedFriend => 'Друг';

  @override
  String get wrappedYourBuddy => 'Твій друг!';

  @override
  String get wrappedNotMentioned => 'Не згадано';

  @override
  String get wrappedTheHardPart => 'Важка частина';

  @override
  String get wrappedPersonalGrowth => 'Особистісний ріст';

  @override
  String get wrappedFunDay => 'Веселий';

  @override
  String get wrappedProductiveDay => 'Продуктивний';

  @override
  String get wrappedIntenseDay => 'Інтенсивний';

  @override
  String get wrappedFunnyMomentTitle => 'Смішний момент';

  @override
  String get wrappedCringeMomentTitle => 'Ніяковий момент';

  @override
  String get wrappedYouTalkedAboutBadge => 'Ти говорив про';

  @override
  String get wrappedCompletedLabel => 'Виконано';

  @override
  String get wrappedMyBuddiesCard => 'Мої друзі';

  @override
  String get wrappedBuddiesLabel => 'ДРУЗІ';

  @override
  String get wrappedObsessionsLabelUpper => 'ЗАХОПЛЕННЯ';

  @override
  String get wrappedStruggleLabelUpper => 'БОРОТЬБА';

  @override
  String get wrappedWinLabelUpper => 'ПЕРЕМОГА';

  @override
  String get wrappedTopPhrasesLabelUpper => 'ТОП ФРАЗИ';

  @override
  String get wrappedYourHeader => 'Твої';

  @override
  String get wrappedTopDaysHeader => 'Найкращі дні';

  @override
  String get wrappedYourTopDaysBadge => 'Твої найкращі дні';

  @override
  String get wrappedBestHeader => 'Найкращі';

  @override
  String get wrappedMomentsHeader => 'Моменти';

  @override
  String get wrappedBestMomentsBadge => 'Найкращі моменти';

  @override
  String get wrappedBiggestHeader => 'Найбільший';

  @override
  String get wrappedStruggleHeader => 'Боротьба';

  @override
  String get wrappedWinHeader => 'Перемога';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Але ти впорався 💪';

  @override
  String get wrappedYouDidItEmoji => 'Ти зробив це! 🎉';

  @override
  String get wrappedHours => 'годин';

  @override
  String get wrappedActions => 'дій';

  @override
  String get multipleSpeakersDetected => 'Виявлено кількох мовців';

  @override
  String get multipleSpeakersDescription =>
      'Схоже, що в записі є кілька мовців. Переконайтеся, що ви знаходитесь у тихому місці, і спробуйте знову.';

  @override
  String get invalidRecordingDetected => 'Виявлено недійсний запис';

  @override
  String get notEnoughSpeechDescription =>
      'Недостатньо мовлення виявлено. Будь ласка, говоріть більше і спробуйте знову.';

  @override
  String get speechDurationDescription => 'Переконайтеся, що ви говорите не менше 5 секунд і не більше 90.';

  @override
  String get connectionLostDescription =>
      'Зʼєднання було перервано. Перевірте підключення до інтернету і спробуйте знову.';

  @override
  String get howToTakeGoodSample => 'Як зробити хороший зразок?';

  @override
  String get goodSampleInstructions =>
      '1. Переконайтеся, що ви в тихому місці.\n2. Говоріть чітко і природно.\n3. Переконайтеся, що ваш пристрій знаходиться в природному положенні на шиї.\n\nПісля створення ви завжди можете покращити його або зробити знову.';

  @override
  String get noDeviceConnectedUseMic => 'Пристрій не підключено. Буде використано мікрофон телефону.';

  @override
  String get doItAgain => 'Зробити знову';

  @override
  String get listenToSpeechProfile => 'Послухати мій голосовий профіль ➡️';

  @override
  String get recognizingOthers => 'Розпізнавання інших 👀';

  @override
  String get keepGoingGreat => 'Продовжуйте, у вас чудово виходить';

  @override
  String get somethingWentWrongTryAgain => 'Щось пішло не так! Будь ласка, спробуйте пізніше.';

  @override
  String get uploadingVoiceProfile => 'Завантаження вашого голосового профілю....';

  @override
  String get memorizingYourVoice => 'Запам\'ятовування вашого голосу...';

  @override
  String get personalizingExperience => 'Персоналізація вашого досвіду...';

  @override
  String get keepSpeakingUntil100 => 'Продовжуйте говорити, поки не досягнете 100%.';

  @override
  String get greatJobAlmostThere => 'Чудова робота, майже готово';

  @override
  String get soCloseJustLittleMore => 'Так близько, ще трохи';

  @override
  String get notificationFrequency => 'Частота сповіщень';

  @override
  String get controlNotificationFrequency => 'Контролюйте, як часто Omi надсилає вам проактивні сповіщення.';

  @override
  String get yourScore => 'Ваш рахунок';

  @override
  String get dailyScoreBreakdown => 'Деталі денного рахунку';

  @override
  String get todaysScore => 'Сьогоднішній рахунок';

  @override
  String get tasksCompleted => 'Завдання виконано';

  @override
  String get completionRate => 'Відсоток виконання';

  @override
  String get howItWorks => 'Як це працює';

  @override
  String get dailyScoreExplanation =>
      'Ваш денний рахунок базується на виконанні завдань. Виконуйте завдання, щоб покращити рахунок!';

  @override
  String get notificationFrequencyDescription =>
      'Контролюйте, як часто Omi надсилає вам проактивні сповіщення та нагадування.';

  @override
  String get sliderOff => 'Вимк.';

  @override
  String get sliderMax => 'Макс.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Підсумок створено для $date';
  }

  @override
  String get failedToGenerateSummary => 'Не вдалося створити підсумок. Переконайтеся, що у вас є розмови за цей день.';

  @override
  String get recap => 'Огляд';

  @override
  String deleteQuoted(String name) {
    return 'Видалити «$name»';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Перемістити $count розмов до:';
  }

  @override
  String get noFolder => 'Без папки';

  @override
  String get removeFromAllFolders => 'Видалити з усіх папок';

  @override
  String get buildAndShareYourCustomApp => 'Створюйте та діліться своїм додатком';

  @override
  String get searchAppsPlaceholder => 'Шукати серед 1500+ додатків';

  @override
  String get filters => 'Фільтри';

  @override
  String get frequencyOff => 'Вимкнено';

  @override
  String get frequencyMinimal => 'Мінімальна';

  @override
  String get frequencyLow => 'Низька';

  @override
  String get frequencyBalanced => 'Збалансована';

  @override
  String get frequencyHigh => 'Висока';

  @override
  String get frequencyMaximum => 'Максимальна';

  @override
  String get frequencyDescOff => 'Без проактивних сповіщень';

  @override
  String get frequencyDescMinimal => 'Лише критичні нагадування';

  @override
  String get frequencyDescLow => 'Лише важливі оновлення';

  @override
  String get frequencyDescBalanced => 'Регулярні корисні нагадування';

  @override
  String get frequencyDescHigh => 'Часті перевірки';

  @override
  String get frequencyDescMaximum => 'Залишайтеся постійно залученими';

  @override
  String get clearChatQuestion => 'Очистити чат?';

  @override
  String get syncingMessages => 'Синхронізація повідомлень з сервером...';

  @override
  String get chatAppsTitle => 'Чат-застосунки';

  @override
  String get selectApp => 'Обрати застосунок';

  @override
  String get noChatAppsEnabled => 'Чат-застосунки не ввімкнено.\nНатисніть \"Увімкнути застосунки\", щоб додати.';

  @override
  String get disable => 'Вимкнути';

  @override
  String get photoLibrary => 'Бібліотека фото';

  @override
  String get chooseFile => 'Обрати файл';

  @override
  String get configureAiPersona => 'Налаштуйте свою AI персону';

  @override
  String get connectAiAssistantsToYourData => 'Підключіть AI асистентів до ваших даних';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Відстежуйте свої особисті цілі на головній сторінці';

  @override
  String get deleteRecording => 'Видалити запис';

  @override
  String get thisCannotBeUndone => 'Цю дію неможливо скасувати.';

  @override
  String get sdCard => 'SD-карта';

  @override
  String get fromSd => 'З SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Швидка передача';

  @override
  String get syncingStatus => 'Синхронізація';

  @override
  String get failedStatus => 'Помилка';

  @override
  String etaLabel(String time) {
    return 'Орієнтовний час: $time';
  }

  @override
  String get transferMethod => 'Метод передачі';

  @override
  String get fast => 'Швидко';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Телефон';

  @override
  String get cancelSync => 'Скасувати синхронізацію';

  @override
  String get cancelSyncMessage => 'Вже завантажені дані будуть збережені. Ви зможете продовжити пізніше.';

  @override
  String get syncCancelled => 'Синхронізацію скасовано';

  @override
  String get deleteProcessedFiles => 'Видалити оброблені файли';

  @override
  String get processedFilesDeleted => 'Оброблені файли видалено';

  @override
  String get wifiEnableFailed => 'Не вдалося увімкнути WiFi на пристрої. Спробуйте ще раз.';

  @override
  String get deviceNoFastTransfer => 'Ваш пристрій не підтримує швидку передачу. Використовуйте Bluetooth.';

  @override
  String get enableHotspotMessage => 'Увімкніть точку доступу на телефоні та спробуйте ще раз.';

  @override
  String get transferStartFailed => 'Не вдалося розпочати передачу. Спробуйте ще раз.';

  @override
  String get deviceNotResponding => 'Пристрій не відповідає. Спробуйте ще раз.';

  @override
  String get invalidWifiCredentials => 'Недійсні облікові дані WiFi. Перевірте налаштування точки доступу.';

  @override
  String get wifiConnectionFailed => 'Помилка з\'єднання WiFi. Спробуйте ще раз.';

  @override
  String get sdCardProcessing => 'Обробка SD-карти';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Обробка $count запису(ів). Файли буде видалено з SD-карти після обробки.';
  }

  @override
  String get process => 'Обробити';

  @override
  String get wifiSyncFailed => 'Помилка синхронізації WiFi';

  @override
  String get processingFailed => 'Помилка обробки';

  @override
  String get downloadingFromSdCard => 'Завантаження з SD-карти';

  @override
  String processingProgress(int current, int total) {
    return 'Обробка $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return 'Створено $count розмов';
  }

  @override
  String get internetRequired => 'Потрібен інтернет';

  @override
  String get processAudio => 'Обробити аудіо';

  @override
  String get start => 'Почати';

  @override
  String get noRecordings => 'Немає записів';

  @override
  String get audioFromOmiWillAppearHere => 'Аудіо з вашого пристрою Omi з\'явиться тут';

  @override
  String get deleteProcessed => 'Видалити оброблені';

  @override
  String get tryDifferentFilter => 'Спробуйте інший фільтр';

  @override
  String get recordings => 'Записи';

  @override
  String get enableRemindersAccess =>
      'Будь ласка, увімкніть доступ до Нагадувань у Налаштуваннях для використання Нагадувань Apple';

  @override
  String todayAtTime(String time) {
    return 'Сьогодні о $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Вчора о $time';
  }

  @override
  String get lessThanAMinute => 'Менше хвилини';

  @override
  String estimatedMinutes(int count) {
    return '~$count хв.';
  }

  @override
  String estimatedHours(int count) {
    return '~$count год.';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Приблизно: залишилось $time';
  }

  @override
  String get summarizingConversation => 'Підсумовування розмови...\nЦе може зайняти кілька секунд';

  @override
  String get resummarizingConversation => 'Повторне підсумовування розмови...\nЦе може зайняти кілька секунд';

  @override
  String get nothingInterestingRetry => 'Нічого цікавого не знайдено,\nхочете спробувати ще раз?';

  @override
  String get noSummaryForConversation => 'Для цієї розмови\nнемає підсумку.';

  @override
  String get unknownLocation => 'Невідоме місцезнаходження';

  @override
  String get couldNotLoadMap => 'Не вдалося завантажити карту';

  @override
  String get triggerConversationIntegration => 'Запустити інтеграцію створення розмови';

  @override
  String get webhookUrlNotSet => 'URL вебхука не встановлено';

  @override
  String get setWebhookUrlInSettings =>
      'Встановіть URL вебхука в налаштуваннях розробника для використання цієї функції.';

  @override
  String get sendWebUrl => 'Надіслати веб-посилання';

  @override
  String get sendTranscript => 'Надіслати транскрипт';

  @override
  String get sendSummary => 'Надіслати підсумок';

  @override
  String get debugModeDetected => 'Виявлено режим налагодження';

  @override
  String get performanceReduced => 'Продуктивність може бути знижена';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Автоматичне закриття через $seconds секунд';
  }

  @override
  String get modelRequired => 'Потрібна модель';

  @override
  String get downloadWhisperModel => 'Завантажте модель whisper для використання транскрипції на пристрої';

  @override
  String get deviceNotCompatible => 'Ваш пристрій несумісний з транскрипцією на пристрої';

  @override
  String get deviceRequirements => 'Ваш пристрій не відповідає вимогам для транскрипції на пристрої';

  @override
  String get willLikelyCrash => 'Увімкнення, ймовірно, призведе до збою або зависання програми.';

  @override
  String get transcriptionSlowerLessAccurate => 'Транскрипція буде значно повільнішою та менш точною.';

  @override
  String get proceedAnyway => 'Все одно продовжити';

  @override
  String get olderDeviceDetected => 'Виявлено старіший пристрій';

  @override
  String get onDeviceSlower => 'Транскрипція на пристрої може бути повільнішою на цьому пристрої.';

  @override
  String get batteryUsageHigher => 'Використання батареї буде вищим, ніж при хмарній транскрипції.';

  @override
  String get considerOmiCloud => 'Розгляньте можливість використання Omi Cloud для кращої продуктивності.';

  @override
  String get highResourceUsage => 'Високе використання ресурсів';

  @override
  String get onDeviceIntensive => 'Транскрипція на пристрої є обчислювально інтенсивною.';

  @override
  String get batteryDrainIncrease => 'Споживання батареї значно зросте.';

  @override
  String get deviceMayWarmUp => 'Пристрій може нагрітися під час тривалого використання.';

  @override
  String get speedAccuracyLower => 'Швидкість і точність можуть бути нижчими, ніж у хмарних моделей.';

  @override
  String get cloudProvider => 'Хмарний провайдер';

  @override
  String get premiumMinutesInfo =>
      '1200 преміум хвилин/місяць. Вкладка \"На пристрої\" пропонує необмежену транскрипцію.';

  @override
  String get viewUsage => 'Переглянути використання';

  @override
  String get localProcessingInfo =>
      'Аудіо обробляється локально. Працює офлайн, більш приватно, але може бути менш точним.';

  @override
  String get model => 'Модель';

  @override
  String get performanceWarning => 'Попередження про продуктивність';

  @override
  String get largeModelWarning => 'Ця модель велика і може призвести до збою додатку або працювати дуже повільно.';

  @override
  String get usingNativeIosSpeech => 'Використання вбудованого розпізнавання мовлення iOS';

  @override
  String get noModelDownloadRequired =>
      'Буде використано вбудований мовний движок вашого пристрою. Завантаження моделі не потрібне.';

  @override
  String get modelReady => 'Модель готова';

  @override
  String get redownload => 'Перезавантажити';

  @override
  String get doNotCloseApp => 'Будь ласка, не закривайте програму.';

  @override
  String get downloading => 'Завантаження...';

  @override
  String get downloadModel => 'Завантажити модель';

  @override
  String estimatedSize(String size) {
    return 'Орієнтовний розмір: ~$size МБ';
  }

  @override
  String availableSpace(String space) {
    return 'Доступний простір: $space';
  }

  @override
  String get notEnoughSpace => 'Попередження: Недостатньо місця!';

  @override
  String get download => 'Завантажити';

  @override
  String downloadError(String error) {
    return 'Помилка завантаження: $error';
  }

  @override
  String get cancelled => 'Скасовано';

  @override
  String get deviceNotCompatibleTitle => 'Пристрій несумісний';

  @override
  String get deviceNotMeetRequirements => 'Ваш пристрій не відповідає вимогам для транскрипції на пристрої.';

  @override
  String get transcriptionSlowerOnDevice => 'Транскрипція на пристрої може бути повільнішою на цьому пристрої.';

  @override
  String get computationallyIntensive => 'Транскрипція на пристрої потребує значних обчислювальних ресурсів.';

  @override
  String get batteryDrainSignificantly => 'Розряд батареї значно збільшиться.';

  @override
  String get premiumMinutesMonth =>
      '1200 преміум-хвилин/місяць. Вкладка На пристрої пропонує необмежену безкоштовну транскрипцію. ';

  @override
  String get audioProcessedLocally =>
      'Аудіо обробляється локально. Працює офлайн, більш приватно, але споживає більше батареї.';

  @override
  String get languageLabel => 'Мова';

  @override
  String get modelLabel => 'Модель';

  @override
  String get modelTooLargeWarning =>
      'Ця модель велика і може спричинити збій програми або дуже повільну роботу на мобільних пристроях.\n\nРекомендується small або base.';

  @override
  String get nativeEngineNoDownload =>
      'Буде використано вбудований мовленнєвий рушій вашого пристрою. Завантаження моделі не потрібне.';

  @override
  String modelReadyWithName(String model) {
    return 'Модель готова ($model)';
  }

  @override
  String get reDownload => 'Завантажити знову';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Завантаження $model: $received / $total МБ';
  }

  @override
  String preparingModel(String model) {
    return 'Підготовка $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Помилка завантаження: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Орієнтовний розмір: ~$size МБ';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Доступний простір: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Вбудована жива транскрипція Omi оптимізована для розмов у реальному часі з автоматичним визначенням мовця та діаризацією.';

  @override
  String get reset => 'Скинути';

  @override
  String get useTemplateFrom => 'Використати шаблон від';

  @override
  String get selectProviderTemplate => 'Виберіть шаблон провайдера...';

  @override
  String get quicklyPopulateResponse => 'Швидко заповнити відомим форматом відповіді провайдера';

  @override
  String get quicklyPopulateRequest => 'Швидко заповнити відомим форматом запиту провайдера';

  @override
  String get invalidJsonError => 'Недійсний JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Завантажити модель ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Модель: $model';
  }

  @override
  String get device => 'Пристрій';

  @override
  String get chatAssistantsTitle => 'Чат-асистенти';

  @override
  String get permissionReadConversations => 'Читати розмови';

  @override
  String get permissionReadMemories => 'Читати спогади';

  @override
  String get permissionReadTasks => 'Читати завдання';

  @override
  String get permissionCreateConversations => 'Створювати розмови';

  @override
  String get permissionCreateMemories => 'Створювати спогади';

  @override
  String get permissionTypeAccess => 'Доступ';

  @override
  String get permissionTypeCreate => 'Створення';

  @override
  String get permissionTypeTrigger => 'Тригер';

  @override
  String get permissionDescReadConversations => 'Цей додаток може отримати доступ до ваших розмов.';

  @override
  String get permissionDescReadMemories => 'Цей додаток може отримати доступ до ваших спогадів.';

  @override
  String get permissionDescReadTasks => 'Цей додаток може отримати доступ до ваших завдань.';

  @override
  String get permissionDescCreateConversations => 'Цей додаток може створювати нові розмови.';

  @override
  String get permissionDescCreateMemories => 'Цей додаток може створювати нові спогади.';

  @override
  String get realtimeListening => 'Прослуховування в реальному часі';

  @override
  String get setupCompleted => 'Завершено';

  @override
  String get pleaseSelectRating => 'Будь ласка, виберіть оцінку';

  @override
  String get writeReviewOptional => 'Написати відгук (необов\'язково)';

  @override
  String get setupQuestionsIntro => 'Допоможіть нам покращити Omi, відповівши на кілька запитань. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Чим ви займаєтесь?';

  @override
  String get setupQuestionUsage => '2. Де ви плануєте використовувати Omi?';

  @override
  String get setupQuestionAge => '3. Який ваш віковий діапазон?';

  @override
  String get setupAnswerAllQuestions => 'Ви ще не відповіли на всі запитання! 🥺';

  @override
  String get setupSkipHelp => 'Пропустити, я не хочу допомагати :C';

  @override
  String get professionEntrepreneur => 'Підприємець';

  @override
  String get professionSoftwareEngineer => 'Інженер-програміст';

  @override
  String get professionProductManager => 'Продакт-менеджер';

  @override
  String get professionExecutive => 'Керівник';

  @override
  String get professionSales => 'Продажі';

  @override
  String get professionStudent => 'Студент';

  @override
  String get usageAtWork => 'На роботі';

  @override
  String get usageIrlEvents => 'На заходах';

  @override
  String get usageOnline => 'Онлайн';

  @override
  String get usageSocialSettings => 'У соціальних умовах';

  @override
  String get usageEverywhere => 'Скрізь';

  @override
  String get customBackendUrlTitle => 'Користувацька URL сервера';

  @override
  String get backendUrlLabel => 'URL сервера';

  @override
  String get saveUrlButton => 'Зберегти URL';

  @override
  String get enterBackendUrlError => 'Введіть URL сервера';

  @override
  String get urlMustEndWithSlashError => 'URL повинен закінчуватися на \"/\"';

  @override
  String get invalidUrlError => 'Введіть дійсну URL';

  @override
  String get backendUrlSavedSuccess => 'URL сервера успішно збережено!';

  @override
  String get signInTitle => 'Увійти';

  @override
  String get signInButton => 'Увійти';

  @override
  String get enterEmailError => 'Будь ласка, введіть вашу електронну пошту';

  @override
  String get invalidEmailError => 'Будь ласка, введіть дійсну електронну пошту';

  @override
  String get enterPasswordError => 'Будь ласка, введіть ваш пароль';

  @override
  String get passwordMinLengthError => 'Пароль повинен містити не менше 8 символів';

  @override
  String get signInSuccess => 'Вхід успішний!';

  @override
  String get alreadyHaveAccountLogin => 'Вже маєте обліковий запис? Увійдіть';

  @override
  String get emailLabel => 'Електронна пошта';

  @override
  String get passwordLabel => 'Пароль';

  @override
  String get createAccountTitle => 'Створити обліковий запис';

  @override
  String get nameLabel => 'Ім\'я';

  @override
  String get repeatPasswordLabel => 'Повторіть пароль';

  @override
  String get signUpButton => 'Зареєструватися';

  @override
  String get enterNameError => 'Будь ласка, введіть ваше ім\'я';

  @override
  String get passwordsDoNotMatch => 'Паролі не співпадають';

  @override
  String get signUpSuccess => 'Реєстрація успішна!';

  @override
  String get loadingKnowledgeGraph => 'Завантаження графа знань...';

  @override
  String get noKnowledgeGraphYet => 'Графа знань ще немає';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Побудова графа знань зі спогадів...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Ваш граф знань буде побудовано автоматично, коли ви створите нові спогади.';

  @override
  String get buildGraphButton => 'Побудувати граф';

  @override
  String get checkOutMyMemoryGraph => 'Подивіться мій граф пам\'яті!';

  @override
  String get getButton => 'Отримати';

  @override
  String openingApp(String appName) {
    return 'Відкриваємо $appName...';
  }

  @override
  String get writeSomething => 'Напишіть щось';

  @override
  String get submitReply => 'Надіслати відповідь';

  @override
  String get editYourReply => 'Редагувати відповідь';

  @override
  String get replyToReview => 'Відповісти на відгук';

  @override
  String get rateAndReviewThisApp => 'Оцініть і залиште відгук про цей додаток';

  @override
  String get noChangesInReview => 'Немає змін у відгуку для оновлення.';

  @override
  String get cantRateWithoutInternet => 'Неможливо оцінити додаток без підключення до інтернету.';

  @override
  String get appAnalytics => 'Аналітика додатку';

  @override
  String get learnMoreLink => 'дізнатися більше';

  @override
  String get moneyEarned => 'Зароблено';

  @override
  String get writeYourReply => 'Напишіть вашу відповідь...';

  @override
  String get replySentSuccessfully => 'Відповідь успішно надіслано';

  @override
  String failedToSendReply(String error) {
    return 'Не вдалося надіслати відповідь: $error';
  }

  @override
  String get send => 'Надіслати';

  @override
  String starFilter(int count) {
    return '$count Зірок';
  }

  @override
  String get noReviewsFound => 'Відгуків не знайдено';

  @override
  String get editReply => 'Редагувати відповідь';

  @override
  String get reply => 'Відповісти';

  @override
  String starFilterLabel(int count) {
    return '$count зірка';
  }

  @override
  String get sharePublicLink => 'Поділитися публічним посиланням';

  @override
  String get makePersonaPublic => 'Зробити персону публічною';

  @override
  String get connectedKnowledgeData => 'Підключені дані знань';

  @override
  String get enterName => 'Введіть ім\'я';

  @override
  String get disconnectTwitter => 'Від\'єднати Twitter';

  @override
  String get disconnectTwitterConfirmation =>
      'Ви впевнені, що хочете від\'єднати свій обліковий запис Twitter? Ваша персона більше не матиме доступу до ваших даних Twitter.';

  @override
  String get getOmiDeviceDescription => 'Створіть більш точний клон за допомогою ваших особистих розмов';

  @override
  String get getOmi => 'Отримати Omi';

  @override
  String get iHaveOmiDevice => 'У мене є пристрій Omi';

  @override
  String get goal => 'ЦІЛЬ';

  @override
  String get tapToTrackThisGoal => 'Торкніться, щоб відстежувати цю ціль';

  @override
  String get tapToSetAGoal => 'Торкніться, щоб встановити ціль';

  @override
  String get processedConversations => 'Оброблені розмови';

  @override
  String get updatedConversations => 'Оновлені розмови';

  @override
  String get newConversations => 'Нові розмови';

  @override
  String get summaryTemplate => 'Шаблон підсумку';

  @override
  String get suggestedTemplates => 'Рекомендовані шаблони';

  @override
  String get otherTemplates => 'Інші шаблони';

  @override
  String get availableTemplates => 'Доступні шаблони';

  @override
  String get getCreative => 'Будьте креативні';

  @override
  String get defaultLabel => 'За замовчуванням';

  @override
  String get lastUsedLabel => 'Останнє використання';

  @override
  String get setDefaultApp => 'Встановити додаток за замовчуванням';

  @override
  String setDefaultAppContent(String appName) {
    return 'Встановити $appName як додаток для підсумків за замовчуванням?\\n\\nЦей додаток буде автоматично використовуватися для всіх майбутніх підсумків розмов.';
  }

  @override
  String get setDefaultButton => 'Встановити за замовчуванням';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName встановлено як додаток для підсумків за замовчуванням';
  }

  @override
  String get createCustomTemplate => 'Створити власний шаблон';

  @override
  String get allTemplates => 'Усі шаблони';

  @override
  String failedToInstallApp(String appName) {
    return 'Не вдалося встановити $appName. Будь ласка, спробуйте ще раз.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Помилка встановлення $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Позначити спікера $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Людина з таким ім\'ям вже існує.';

  @override
  String get selectYouFromList => 'Щоб позначити себе, виберіть \"Ви\" зі списку.';

  @override
  String get enterPersonsName => 'Введіть ім\'я людини';

  @override
  String get addPerson => 'Додати людину';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Позначити інші сегменти від цього спікера ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Позначити інші сегменти';

  @override
  String get managePeople => 'Керувати людьми';

  @override
  String get shareViaSms => 'Поділитися через SMS';

  @override
  String get selectContactsToShareSummary => 'Виберіть контакти для надсилання підсумку розмови';

  @override
  String get searchContactsHint => 'Пошук контактів...';

  @override
  String contactsSelectedCount(int count) {
    return '$count вибрано';
  }

  @override
  String get clearAllSelection => 'Очистити все';

  @override
  String get selectContactsToShare => 'Виберіть контакти для надсилання';

  @override
  String shareWithContactCount(int count) {
    return 'Надіслати $count контакту';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Надіслати $count контактам';
  }

  @override
  String get contactsPermissionRequired => 'Потрібен дозвіл на доступ до контактів';

  @override
  String get contactsPermissionRequiredForSms => 'Для надсилання через SMS потрібен дозвіл на доступ до контактів';

  @override
  String get grantContactsPermissionForSms =>
      'Будь ласка, надайте дозвіл на доступ до контактів для надсилання через SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Не знайдено контактів з номерами телефонів';

  @override
  String get noContactsMatchSearch => 'Контакти за вашим запитом не знайдено';

  @override
  String get failedToLoadContacts => 'Не вдалося завантажити контакти';

  @override
  String get failedToPrepareConversationForSharing =>
      'Не вдалося підготувати розмову для надсилання. Будь ласка, спробуйте знову.';

  @override
  String get couldNotOpenSmsApp => 'Не вдалося відкрити додаток SMS. Будь ласка, спробуйте знову.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Ось про що ми щойно говорили: $link';
  }

  @override
  String get wifiSync => 'Синхронізація WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item скопійовано в буфер обміну';
  }

  @override
  String get wifiConnectionFailedTitle => 'Помилка з\'єднання';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Підключення до $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Увімкнути WiFi на $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Підключитися до $deviceName';
  }

  @override
  String get recordingDetails => 'Деталі запису';

  @override
  String get storageLocationSdCard => 'SD-карта';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Телефон';

  @override
  String get storageLocationPhoneMemory => 'Телефон (Пам\'ять)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Збережено на $deviceName';
  }

  @override
  String get transferring => 'Передача...';

  @override
  String get transferRequired => 'Потрібна передача';

  @override
  String get downloadingAudioFromSdCard => 'Завантаження аудіо з SD-карти вашого пристрою';

  @override
  String get transferRequiredDescription =>
      'Цей запис зберігається на SD-карті вашого пристрою. Передайте його на телефон, щоб відтворити або поділитися.';

  @override
  String get cancelTransfer => 'Скасувати передачу';

  @override
  String get transferToPhone => 'Передати на телефон';

  @override
  String get privateAndSecureOnDevice => 'Приватно та безпечно на вашому пристрої';

  @override
  String get recordingInfo => 'Інформація про запис';

  @override
  String get transferInProgress => 'Передача в процесі...';

  @override
  String get shareRecording => 'Поділитися записом';

  @override
  String get deleteRecordingConfirmation =>
      'Ви впевнені, що хочете остаточно видалити цей запис? Цю дію неможливо скасувати.';

  @override
  String get recordingIdLabel => 'ID запису';

  @override
  String get dateTimeLabel => 'Дата та час';

  @override
  String get durationLabel => 'Тривалість';

  @override
  String get audioFormatLabel => 'Формат аудіо';

  @override
  String get storageLocationLabel => 'Місце зберігання';

  @override
  String get estimatedSizeLabel => 'Орієнтовний розмір';

  @override
  String get deviceModelLabel => 'Модель пристрою';

  @override
  String get deviceIdLabel => 'ID пристрою';

  @override
  String get statusLabel => 'Статус';

  @override
  String get statusProcessed => 'Оброблено';

  @override
  String get statusUnprocessed => 'Не оброблено';

  @override
  String get switchedToFastTransfer => 'Переключено на швидку передачу';

  @override
  String get transferCompleteMessage => 'Передача завершена! Тепер ви можете відтворити цей запис.';

  @override
  String transferFailedMessage(String error) {
    return 'Помилка передачі: $error';
  }

  @override
  String get transferCancelled => 'Передачу скасовано';

  @override
  String get fastTransferEnabled => 'Швидку передачу увімкнено';

  @override
  String get bluetoothSyncEnabled => 'Синхронізацію Bluetooth увімкнено';

  @override
  String get enableFastTransfer => 'Увімкнути швидку передачу';

  @override
  String get fastTransferDescription =>
      'Швидка передача використовує WiFi для ~5x швидших швидкостей. Ваш телефон тимчасово підключиться до WiFi-мережі пристрою Omi під час передачі.';

  @override
  String get internetAccessPausedDuringTransfer => 'Доступ до інтернету призупинено під час передачі';

  @override
  String get chooseTransferMethodDescription => 'Виберіть, як записи передаються з пристрою Omi на телефон.';

  @override
  String get wifiSpeed => '~150 КБ/с через WiFi';

  @override
  String get fiveTimesFaster => 'У 5 РАЗІВ ШВИДШЕ';

  @override
  String get fastTransferMethodDescription =>
      'Створює пряме WiFi-підключення до пристрою Omi. Телефон тимчасово відключається від звичайного WiFi під час передачі.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 КБ/с через BLE';

  @override
  String get bluetoothMethodDescription =>
      'Використовує стандартне підключення Bluetooth Low Energy. Повільніше, але не впливає на WiFi-з\'єднання.';

  @override
  String get selected => 'Вибрано';

  @override
  String get selectOption => 'Вибрати';

  @override
  String get lowBatteryAlertTitle => 'Попередження про низький заряд батареї';

  @override
  String get lowBatteryAlertBody => 'Батарея вашого пристрою розряджена. Час зарядити! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Ваш пристрій Omi відключено';

  @override
  String get deviceDisconnectedNotificationBody => 'Будь ласка, підключіться знову, щоб продовжити використання Omi.';

  @override
  String get firmwareUpdateAvailable => 'Доступне оновлення прошивки';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Для вашого пристрою Omi доступне нове оновлення прошивки ($version). Бажаєте оновити зараз?';
  }

  @override
  String get later => 'Пізніше';

  @override
  String get appDeletedSuccessfully => 'Додаток успішно видалено';

  @override
  String get appDeleteFailed => 'Не вдалося видалити додаток. Спробуйте пізніше.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Видимість додатка успішно змінено. Зміни можуть відобразитися через кілька хвилин.';

  @override
  String get errorActivatingAppIntegration =>
      'Помилка при активації додатка. Якщо це інтеграційний додаток, переконайтеся, що налаштування завершено.';

  @override
  String get errorUpdatingAppStatus => 'Виникла помилка під час оновлення статусу додатка.';

  @override
  String get calculatingETA => 'Розрахунок...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Залишилось близько $minutes хвилин';
  }

  @override
  String get aboutAMinuteRemaining => 'Залишилось близько хвилини';

  @override
  String get almostDone => 'Майже готово...';

  @override
  String get omiSays => 'omi каже';

  @override
  String get analyzingYourData => 'Аналіз ваших даних...';

  @override
  String migratingToProtection(String level) {
    return 'Міграція до захисту $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Немає даних для міграції. Завершення...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Міграція $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Усі об\'єкти мігровано. Завершення...';

  @override
  String get migrationErrorOccurred => 'Під час міграції сталася помилка. Спробуйте ще раз.';

  @override
  String get migrationComplete => 'Міграцію завершено!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Ваші дані тепер захищені новими налаштуваннями $level.';
  }

  @override
  String get chatsLowercase => 'чати';

  @override
  String get dataLowercase => 'дані';

  @override
  String get fallNotificationTitle => 'Ой';

  @override
  String get fallNotificationBody => 'Ви впали?';

  @override
  String get importantConversationTitle => 'Важлива розмова';

  @override
  String get importantConversationBody => 'Ви щойно провели важливу розмову. Торкніться, щоб поділитися резюме.';

  @override
  String get templateName => 'Назва шаблону';

  @override
  String get templateNameHint => 'напр. Екстрактор дій зустрічі';

  @override
  String get nameMustBeAtLeast3Characters => 'Назва повинна містити щонайменше 3 символи';

  @override
  String get conversationPromptHint => 'напр., Витягніть завдання, прийняті рішення та ключові висновки з розмови.';

  @override
  String get pleaseEnterAppPrompt => 'Будь ласка, введіть підказку для програми';

  @override
  String get promptMustBeAtLeast10Characters => 'Підказка повинна містити щонайменше 10 символів';

  @override
  String get anyoneCanDiscoverTemplate => 'Будь-хто може знайти ваш шаблон';

  @override
  String get onlyYouCanUseTemplate => 'Тільки ви можете використовувати цей шаблон';

  @override
  String get generatingDescription => 'Створення опису...';

  @override
  String get creatingAppIcon => 'Створення значка програми...';

  @override
  String get installingApp => 'Встановлення програми...';

  @override
  String get appCreatedAndInstalled => 'Програму створено та встановлено!';

  @override
  String get appCreatedSuccessfully => 'Програму успішно створено!';

  @override
  String get failedToCreateApp => 'Не вдалося створити програму. Спробуйте ще раз.';

  @override
  String get addAppSelectCoreCapability => 'Виберіть ще одну основну можливість для вашого додатку';

  @override
  String get addAppSelectPaymentPlan => 'Виберіть план оплати та введіть ціну для вашого додатку';

  @override
  String get addAppSelectCapability => 'Виберіть принаймні одну можливість для вашого додатку';

  @override
  String get addAppSelectLogo => 'Виберіть логотип для вашого додатку';

  @override
  String get addAppEnterChatPrompt => 'Введіть підказку чату для вашого додатку';

  @override
  String get addAppEnterConversationPrompt => 'Введіть підказку розмови для вашого додатку';

  @override
  String get addAppSelectTriggerEvent => 'Виберіть подію-тригер для вашого додатку';

  @override
  String get addAppEnterWebhookUrl => 'Введіть URL вебхука для вашого додатку';

  @override
  String get addAppSelectCategory => 'Виберіть категорію для вашого додатку';

  @override
  String get addAppFillRequiredFields => 'Заповніть правильно всі обов\'язкові поля';

  @override
  String get addAppUpdatedSuccess => 'Додаток успішно оновлено 🚀';

  @override
  String get addAppUpdateFailed => 'Не вдалося оновити. Спробуйте пізніше';

  @override
  String get addAppSubmittedSuccess => 'Додаток успішно надіслано 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Помилка відкриття вибору файлів: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Помилка вибору зображення: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Доступ до фото заборонено. Дозвольте доступ до фотографій';

  @override
  String get addAppErrorSelectingImageRetry => 'Помилка вибору зображення. Спробуйте знову.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Помилка вибору мініатюри: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Помилка вибору мініатюри. Спробуйте знову.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Інші можливості не можна вибрати разом з Персоною';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Персону не можна вибрати разом з іншими можливостями';

  @override
  String get personaTwitterHandleNotFound => 'Twitter-акаунт не знайдено';

  @override
  String get personaTwitterHandleSuspended => 'Twitter-акаунт заблоковано';

  @override
  String get personaFailedToVerifyTwitter => 'Не вдалося перевірити Twitter-акаунт';

  @override
  String get personaFailedToFetch => 'Не вдалося отримати вашу персону';

  @override
  String get personaFailedToCreate => 'Не вдалося створити персону';

  @override
  String get personaConnectKnowledgeSource => 'Підключіть принаймні одне джерело даних (Omi або Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Персону успішно оновлено';

  @override
  String get personaFailedToUpdate => 'Не вдалося оновити персону';

  @override
  String get personaPleaseSelectImage => 'Виберіть зображення';

  @override
  String get personaFailedToCreateTryLater => 'Не вдалося створити персону. Спробуйте пізніше.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Не вдалося створити персону: $error';
  }

  @override
  String get personaFailedToEnable => 'Не вдалося увімкнути персону';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Помилка увімкнення персони: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Не вдалося отримати підтримувані країни. Спробуйте пізніше.';

  @override
  String get paymentFailedToSetDefault => 'Не вдалося встановити спосіб оплати за замовчуванням. Спробуйте пізніше.';

  @override
  String get paymentFailedToSavePaypal => 'Не вдалося зберегти дані PayPal. Спробуйте пізніше.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Активний';

  @override
  String get paymentStatusConnected => 'Підключено';

  @override
  String get paymentStatusNotConnected => 'Не підключено';

  @override
  String get paymentAppCost => 'Вартість додатку';

  @override
  String get paymentEnterValidAmount => 'Введіть дійсну суму';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Введіть суму більше 0';

  @override
  String get paymentPlan => 'План оплати';

  @override
  String get paymentNoneSelected => 'Не вибрано';

  @override
  String get aiGenPleaseEnterDescription => 'Будь ласка, введіть опис вашого додатку';

  @override
  String get aiGenCreatingAppIcon => 'Створення іконки додатку...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Сталася помилка: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Додаток успішно створено!';

  @override
  String get aiGenFailedToCreateApp => 'Не вдалося створити додаток';

  @override
  String get aiGenErrorWhileCreatingApp => 'Під час створення додатку сталася помилка';

  @override
  String get aiGenFailedToGenerateApp => 'Не вдалося згенерувати додаток. Будь ласка, спробуйте ще раз.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Не вдалося повторно згенерувати іконку';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Будь ласка, спочатку згенеруйте додаток';

  @override
  String get xHandleTitle => 'Який ваш нік у X?';

  @override
  String get xHandleDescription =>
      'Ми попередньо навчимо вашого клона Omi\nна основі активності вашого облікового запису';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Введіть ваш нік у X';

  @override
  String get xHandlePleaseEnterValid => 'Введіть дійсний нік у X';

  @override
  String get nextButton => 'Далі';

  @override
  String get connectOmiDevice => 'Підключити пристрій Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Ви переключаєте свій Безлімітний план на $title. Ви впевнені, що хочете продовжити?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Оновлення заплановано! Ваш місячний план продовжується до кінця платіжного періоду, потім автоматично переключиться на річний.';

  @override
  String get couldNotSchedulePlanChange => 'Не вдалося запланувати зміну плану. Спробуйте ще раз.';

  @override
  String get subscriptionReactivatedDefault =>
      'Вашу підписку відновлено! Оплата зараз не стягується - вам буде виставлено рахунок наприкінці поточного періоду.';

  @override
  String get subscriptionSuccessfulCharged =>
      'Підписку успішно оформлено! З вас стягнуто оплату за новий платіжний період.';

  @override
  String get couldNotProcessSubscription => 'Не вдалося обробити підписку. Спробуйте ще раз.';

  @override
  String get couldNotLaunchUpgradePage => 'Не вдалося відкрити сторінку оновлення. Спробуйте ще раз.';

  @override
  String get transcriptionJsonPlaceholder => 'Вставте вашу JSON конфігурацію тут...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Помилка при відкритті вибору файлів: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Помилка: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Розмови успішно об\'єднані';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count розмов успішно об\'єднано';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Час для щоденної рефлексії';

  @override
  String get dailyReflectionNotificationBody => 'Розкажи мені про свій день';

  @override
  String get actionItemReminderTitle => 'Нагадування Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName відключено';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Будь ласка, підключіться знову, щоб продовжити використання вашого $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Увійти';

  @override
  String get onboardingYourName => 'Ваше ім\'я';

  @override
  String get onboardingLanguage => 'Мова';

  @override
  String get onboardingPermissions => 'Дозволи';

  @override
  String get onboardingComplete => 'Завершено';

  @override
  String get onboardingWelcomeToOmi => 'Ласкаво просимо до Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Розкажіть про себе';

  @override
  String get onboardingChooseYourPreference => 'Оберіть ваші налаштування';

  @override
  String get onboardingGrantRequiredAccess => 'Надати необхідний доступ';

  @override
  String get onboardingYoureAllSet => 'Все готово';

  @override
  String get searchTranscriptOrSummary => 'Пошук у транскрипції або резюме...';

  @override
  String get myGoal => 'Моя ціль';

  @override
  String get appNotAvailable => 'Ой! Схоже, що застосунок, який ви шукаєте, недоступний.';

  @override
  String get failedToConnectTodoist => 'Не вдалося підключитися до Todoist';

  @override
  String get failedToConnectAsana => 'Не вдалося підключитися до Asana';

  @override
  String get failedToConnectGoogleTasks => 'Не вдалося підключитися до Google Tasks';

  @override
  String get failedToConnectClickUp => 'Не вдалося підключитися до ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Не вдалося підключитися до $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Успішно підключено до Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Не вдалося підключитися до Todoist. Будь ласка, спробуйте ще раз.';

  @override
  String get successfullyConnectedAsana => 'Успішно підключено до Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Не вдалося підключитися до Asana. Будь ласка, спробуйте ще раз.';

  @override
  String get successfullyConnectedGoogleTasks => 'Успішно підключено до Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry =>
      'Не вдалося підключитися до Google Tasks. Будь ласка, спробуйте ще раз.';

  @override
  String get successfullyConnectedClickUp => 'Успішно підключено до ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Не вдалося підключитися до ClickUp. Будь ласка, спробуйте ще раз.';

  @override
  String get successfullyConnectedNotion => 'Успішно підключено до Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Не вдалося оновити статус підключення Notion.';

  @override
  String get successfullyConnectedGoogle => 'Успішно підключено до Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Не вдалося оновити статус підключення Google.';

  @override
  String get successfullyConnectedWhoop => 'Успішно підключено до Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Не вдалося оновити статус підключення Whoop.';

  @override
  String get successfullyConnectedGitHub => 'Успішно підключено до GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Не вдалося оновити статус підключення GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'Не вдалося увійти через Google, спробуйте ще раз.';

  @override
  String get authenticationFailed => 'Помилка автентифікації. Будь ласка, спробуйте ще раз.';

  @override
  String get authFailedToSignInWithApple => 'Не вдалося увійти через Apple, спробуйте ще раз.';

  @override
  String get authFailedToRetrieveToken => 'Не вдалося отримати токен Firebase, спробуйте ще раз.';

  @override
  String get authUnexpectedErrorFirebase => 'Неочікувана помилка під час входу, помилка Firebase, спробуйте ще раз.';

  @override
  String get authUnexpectedError => 'Неочікувана помилка під час входу, спробуйте ще раз';

  @override
  String get authFailedToLinkGoogle => 'Не вдалося зв\'язати з Google, спробуйте ще раз.';

  @override
  String get authFailedToLinkApple => 'Не вдалося зв\'язати з Apple, спробуйте ще раз.';

  @override
  String get onboardingBluetoothRequired => 'Для підключення до пристрою потрібен дозвіл Bluetooth.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Дозвіл Bluetooth відхилено. Надайте дозвіл у Системних налаштуваннях.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Статус дозволу Bluetooth: $status. Перевірте Системні налаштування.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Не вдалося перевірити дозвіл Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Дозвіл на сповіщення відхилено. Надайте дозвіл у Системних налаштуваннях.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Дозвіл на сповіщення відхилено. Надайте дозвіл у Системні налаштування > Сповіщення.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Статус дозволу на сповіщення: $status. Перевірте Системні налаштування.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Не вдалося перевірити дозвіл на сповіщення: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Надайте дозвіл на місцезнаходження в Налаштування > Конфіденційність і безпека > Служби геолокації';

  @override
  String get onboardingMicrophoneRequired => 'Для запису потрібен дозвіл мікрофона.';

  @override
  String get onboardingMicrophoneDenied =>
      'Дозвіл мікрофона відхилено. Надайте дозвіл у Системні налаштування > Конфіденційність і безпека > Мікрофон.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Статус дозволу мікрофона: $status. Перевірте Системні налаштування.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Не вдалося перевірити дозвіл мікрофона: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Для запису системного звуку потрібен дозвіл на захоплення екрана.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Дозвіл на захоплення екрана відхилено. Надайте дозвіл у Системні налаштування > Конфіденційність і безпека > Запис екрана.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Статус дозволу на захоплення екрана: $status. Перевірте Системні налаштування.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Не вдалося перевірити дозвіл на захоплення екрана: $error';
  }

  @override
  String get onboardingAccessibilityRequired => 'Для виявлення зустрічей у браузері потрібен дозвіл на доступність.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Статус дозволу на доступність: $status. Перевірте Системні налаштування.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Не вдалося перевірити дозвіл на доступність: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Зйомка камерою недоступна на цій платформі';

  @override
  String get msgCameraPermissionDenied => 'Дозвіл на камеру відхилено. Будь ласка, дозвольте доступ до камери';

  @override
  String msgCameraAccessError(String error) {
    return 'Помилка доступу до камери: $error';
  }

  @override
  String get msgPhotoError => 'Помилка під час фотографування. Будь ласка, спробуйте ще раз.';

  @override
  String get msgMaxImagesLimit => 'Ви можете вибрати лише до 4 зображень';

  @override
  String msgFilePickerError(String error) {
    return 'Помилка відкриття вибору файлів: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Помилка вибору зображень: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Дозвіл на фото відхилено. Будь ласка, дозвольте доступ до фото для вибору зображень';

  @override
  String get msgSelectImagesGenericError => 'Помилка вибору зображень. Будь ласка, спробуйте ще раз.';

  @override
  String get msgMaxFilesLimit => 'Ви можете вибрати лише до 4 файлів';

  @override
  String msgSelectFilesError(String error) {
    return 'Помилка вибору файлів: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Помилка вибору файлів. Будь ласка, спробуйте ще раз.';

  @override
  String get msgUploadFileFailed => 'Не вдалося завантажити файл, спробуйте пізніше';

  @override
  String get msgReadingMemories => 'Читаємо ваші спогади...';

  @override
  String get msgLearningMemories => 'Вчимося з ваших спогадів...';

  @override
  String get msgUploadAttachedFileFailed => 'Не вдалося завантажити прикріплений файл.';

  @override
  String captureRecordingError(String error) {
    return 'Під час запису сталася помилка: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Запис зупинено: $reason. Можливо, вам потрібно буде повторно підключити зовнішні дисплеї або перезапустити запис.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Потрібен дозвіл на мікрофон';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Надайте дозвіл на мікрофон у Системних налаштуваннях';

  @override
  String get captureScreenRecordingPermissionRequired => 'Потрібен дозвіл на запис екрану';

  @override
  String get captureDisplayDetectionFailed => 'Виявлення дисплея не вдалося. Запис зупинено.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Недійсний URL вебхука аудіо-байтів';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Недійсний URL вебхука транскрипції в реальному часі';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Недійсний URL вебхука створеної бесіди';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Недійсний URL вебхука денного звіту';

  @override
  String get devModeSettingsSaved => 'Налаштування збережено!';

  @override
  String get voiceFailedToTranscribe => 'Не вдалося транскрибувати аудіо';

  @override
  String get locationPermissionRequired => 'Потрібен дозвіл на місцезнаходження';

  @override
  String get locationPermissionContent =>
      'Для швидкої передачі потрібен дозвіл на місцезнаходження для перевірки з\'єднання WiFi. Будь ласка, надайте дозвіл на місцезнаходження, щоб продовжити.';

  @override
  String get pdfTranscriptExport => 'Експорт транскрипції';

  @override
  String get pdfConversationExport => 'Експорт бесіди';

  @override
  String pdfTitleLabel(String title) {
    return 'Заголовок: $title';
  }

  @override
  String get conversationNewIndicator => 'Нове 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count фото';
  }

  @override
  String get mergingStatus => 'Об\'єднання...';

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
    return '$count хв';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count хв';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins хв $secs сек';
  }

  @override
  String timeHourSingular(int count) {
    return '$count година';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count годин';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours годин $mins хв';
  }

  @override
  String timeDaySingular(int count) {
    return '$count день';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count днів';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days днів $hours годин';
  }

  @override
  String timeCompactSecs(int count) {
    return '$countс';
  }

  @override
  String timeCompactMins(int count) {
    return '$countхв';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '$minsхв $secsс';
  }

  @override
  String timeCompactHours(int count) {
    return '$countг';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '$hoursг $minsхв';
  }

  @override
  String get moveToFolder => 'Перемістити до папки';

  @override
  String get noFoldersAvailable => 'Немає доступних папок';

  @override
  String get newFolder => 'Нова папка';

  @override
  String get color => 'Колір';

  @override
  String get waitingForDevice => 'Очікування пристрою...';

  @override
  String get saySomething => 'Скажіть щось...';

  @override
  String get initialisingSystemAudio => 'Ініціалізація системного аудіо';

  @override
  String get stopRecording => 'Зупинити запис';

  @override
  String get continueRecording => 'Продовжити запис';

  @override
  String get initialisingRecorder => 'Ініціалізація диктофона';

  @override
  String get pauseRecording => 'Призупинити запис';

  @override
  String get resumeRecording => 'Відновити запис';

  @override
  String get noDailyRecapsYet => 'Podsumowania dzienne jeszcze niedostępne';

  @override
  String get dailyRecapsDescription => 'Twoje podsumowania dzienne pojawią się tutaj po wygenerowaniu';

  @override
  String get chooseTransferMethod => 'Оберіть метод передачі';

  @override
  String get fastTransferSpeed => '~150 КБ/с через WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Виявлено великий часовий розрив ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Виявлено великі часові розриви ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Пристрій не підтримує синхронізацію WiFi, перемикання на Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health недоступний на цьому пристрої';

  @override
  String get downloadAudio => 'Завантажити аудіо';

  @override
  String get audioDownloadSuccess => 'Аудіо успішно завантажено';

  @override
  String get audioDownloadFailed => 'Не вдалося завантажити аудіо';

  @override
  String get downloadingAudio => 'Завантаження аудіо...';

  @override
  String get shareAudio => 'Поділитися аудіо';

  @override
  String get preparingAudio => 'Підготовка аудіо';

  @override
  String get gettingAudioFiles => 'Отримання аудіофайлів...';

  @override
  String get downloadingAudioProgress => 'Завантаження аудіо';

  @override
  String get processingAudio => 'Обробка аудіо';

  @override
  String get combiningAudioFiles => 'Об\'єднання аудіофайлів...';

  @override
  String get audioReady => 'Аудіо готове';

  @override
  String get openingShareSheet => 'Відкриття аркушу спільного доступу...';

  @override
  String get audioShareFailed => 'Не вдалося поділитися';

  @override
  String get dailyRecaps => 'Щоденні підсумки';

  @override
  String get removeFilter => 'Видалити фільтр';

  @override
  String get categoryConversationAnalysis => 'Аналіз розмов';

  @override
  String get categoryPersonalityClone => 'Клон особистості';

  @override
  String get categoryHealth => 'Здоров\'я';

  @override
  String get categoryEducation => 'Освіта';

  @override
  String get categoryCommunication => 'Комунікація';

  @override
  String get categoryEmotionalSupport => 'Емоційна підтримка';

  @override
  String get categoryProductivity => 'Продуктивність';

  @override
  String get categoryEntertainment => 'Розваги';

  @override
  String get categoryFinancial => 'Фінанси';

  @override
  String get categoryTravel => 'Подорожі';

  @override
  String get categorySafety => 'Безпека';

  @override
  String get categoryShopping => 'Покупки';

  @override
  String get categorySocial => 'Соціальне';

  @override
  String get categoryNews => 'Новини';

  @override
  String get categoryUtilities => 'Інструменти';

  @override
  String get categoryOther => 'Інше';

  @override
  String get capabilityChat => 'Чат';

  @override
  String get capabilityConversations => 'Розмови';

  @override
  String get capabilityExternalIntegration => 'Зовнішня інтеграція';

  @override
  String get capabilityNotification => 'Сповіщення';

  @override
  String get triggerAudioBytes => 'Аудіо байти';

  @override
  String get triggerConversationCreation => 'Створення розмови';

  @override
  String get triggerTranscriptProcessed => 'Транскрипт оброблено';

  @override
  String get actionCreateConversations => 'Створити розмови';

  @override
  String get actionCreateMemories => 'Створити спогади';

  @override
  String get actionReadConversations => 'Читати розмови';

  @override
  String get actionReadMemories => 'Читати спогади';

  @override
  String get actionReadTasks => 'Читати завдання';

  @override
  String get scopeUserName => 'Ім\'я користувача';

  @override
  String get scopeUserFacts => 'Дані користувача';

  @override
  String get scopeUserConversations => 'Розмови користувача';

  @override
  String get scopeUserChat => 'Чат користувача';

  @override
  String get capabilitySummary => 'Підсумок';

  @override
  String get capabilityFeatured => 'Рекомендовані';

  @override
  String get capabilityTasks => 'Завдання';

  @override
  String get capabilityIntegrations => 'Інтеграції';

  @override
  String get categoryPersonalityClones => 'Клони особистості';

  @override
  String get categoryProductivityLifestyle => 'Продуктивність та спосіб життя';

  @override
  String get categorySocialEntertainment => 'Соціальне та розваги';

  @override
  String get categoryProductivityTools => 'Інструменти продуктивності';

  @override
  String get categoryPersonalWellness => 'Особисте благополуччя';

  @override
  String get rating => 'Рейтинг';

  @override
  String get categories => 'Категорії';

  @override
  String get sortBy => 'Сортування';

  @override
  String get highestRating => 'Найвищий рейтинг';

  @override
  String get lowestRating => 'Найнижчий рейтинг';

  @override
  String get resetFilters => 'Скинути фільтри';

  @override
  String get applyFilters => 'Застосувати фільтри';

  @override
  String get mostInstalls => 'Найбільше встановлень';

  @override
  String get couldNotOpenUrl => 'Не вдалося відкрити URL. Будь ласка, спробуйте ще раз.';

  @override
  String get newTask => 'Нове завдання';

  @override
  String get viewAll => 'Переглянути все';

  @override
  String get addTask => 'Додати завдання';

  @override
  String get addMcpServer => 'Додати сервер MCP';

  @override
  String get connectExternalAiTools => 'Підключити зовнішні інструменти ШІ';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return 'Успішно підключено інструментів: $count';
  }

  @override
  String get mcpConnectionFailed => 'Не вдалося підключитися до сервера MCP';

  @override
  String get authorizingMcpServer => 'Авторизація...';

  @override
  String get whereDidYouHearAboutOmi => 'Як ви про нас дізналися?';

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
  String get friendWordOfMouth => 'Друг';

  @override
  String get otherSource => 'Інше';

  @override
  String get pleaseSpecify => 'Будь ласка, уточніть';

  @override
  String get event => 'Подія';

  @override
  String get coworker => 'Колега';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Аудіофайл недоступний для відтворення';

  @override
  String get audioPlaybackFailed => 'Неможливо відтворити аудіо. Файл може бути пошкоджений або відсутній.';

  @override
  String get connectionGuide => 'Посібник з підключення';

  @override
  String get iveDoneThis => 'Я це зробив';

  @override
  String get pairNewDevice => 'Сполучити новий пристрій';

  @override
  String get dontSeeYourDevice => 'Не бачите свій пристрій?';

  @override
  String get reportAnIssue => 'Повідомити про проблему';

  @override
  String get pairingTitleOmi => 'Увімкніть Omi';

  @override
  String get pairingDescOmi => 'Натисніть і утримуйте пристрій, доки він не завібрує, щоб увімкнути його.';

  @override
  String get pairingTitleOmiDevkit => 'Переведіть Omi DevKit в режим сполучення';

  @override
  String get pairingDescOmiDevkit =>
      'Натисніть кнопку один раз для ввімкнення. Світлодіод блиматиме фіолетовим у режимі сполучення.';

  @override
  String get pairingTitleOmiGlass => 'Увімкніть Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Натисніть і утримуйте бічну кнопку 3 секунди для ввімкнення.';

  @override
  String get pairingTitlePlaudNote => 'Переведіть Plaud Note в режим сполучення';

  @override
  String get pairingDescPlaudNote =>
      'Натисніть і утримуйте бічну кнопку протягом 2 секунд. Червоний світлодіод блиматиме, коли пристрій буде готовий до сполучення.';

  @override
  String get pairingTitleBee => 'Переведіть Bee в режим сполучення';

  @override
  String get pairingDescBee => 'Натисніть кнопку 5 разів поспіль. Індикатор почне блимати синім і зеленим.';

  @override
  String get pairingTitleLimitless => 'Переведіть Limitless в режим сполучення';

  @override
  String get pairingDescLimitless =>
      'Коли горить будь-який індикатор, натисніть один раз, потім натисніть і утримуйте, доки пристрій не покаже рожеве світло, потім відпустіть.';

  @override
  String get pairingTitleFriendPendant => 'Переведіть Friend Pendant в режим сполучення';

  @override
  String get pairingDescFriendPendant =>
      'Натисніть кнопку на кулоні, щоб увімкнути його. Він автоматично перейде в режим сполучення.';

  @override
  String get pairingTitleFieldy => 'Переведіть Fieldy в режим сполучення';

  @override
  String get pairingDescFieldy => 'Натисніть і утримуйте пристрій, доки не з\'явиться індикатор, щоб увімкнути його.';

  @override
  String get pairingTitleAppleWatch => 'Під\'єднайте Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Встановіть і відкрийте додаток Omi на Apple Watch, потім натисніть Під\'єднати в додатку.';

  @override
  String get pairingTitleNeoOne => 'Переведіть Neo One в режим сполучення';

  @override
  String get pairingDescNeoOne =>
      'Натисніть і утримуйте кнопку живлення, доки не заблимає світлодіод. Пристрій стане видимим.';

  @override
  String get downloadingFromDevice => 'Завантаження з пристрою';

  @override
  String get reconnectingToInternet => 'Повторне підключення до інтернету...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Завантаження $current з $total';
  }

  @override
  String get processedStatus => 'Оброблено';

  @override
  String get corruptedStatus => 'Пошкоджено';

  @override
  String nPending(int count) {
    return '$count очікують';
  }

  @override
  String nProcessed(int count) {
    return '$count оброблено';
  }

  @override
  String get synced => 'Синхронізовано';

  @override
  String get noPendingRecordings => 'Немає очікуючих записів';

  @override
  String get noProcessedRecordings => 'Ще немає оброблених записів';

  @override
  String get pending => 'Очікування';

  @override
  String whatsNewInVersion(String version) {
    return 'Що нового у $version';
  }

  @override
  String get addToYourTaskList => 'Додати до списку завдань?';

  @override
  String get failedToCreateShareLink => 'Не вдалося створити посилання для поширення';

  @override
  String get deleteGoal => 'Видалити ціль';

  @override
  String get deviceUpToDate => 'Ваш пристрій оновлений';

  @override
  String get wifiConfiguration => 'Налаштування WiFi';

  @override
  String get wifiConfigurationSubtitle => 'Введіть дані WiFi, щоб пристрій міг завантажити прошивку.';

  @override
  String get networkNameSsid => 'Назва мережі (SSID)';

  @override
  String get enterWifiNetworkName => 'Введіть назву мережі WiFi';

  @override
  String get enterWifiPassword => 'Введіть пароль WiFi';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Ось що я знаю про тебе';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Ця карта оновлюється, коли Omi навчається з ваших розмов.';

  @override
  String get apiEnvironment => 'Середовище API';

  @override
  String get apiEnvironmentDescription => 'Оберіть сервер для підключення';

  @override
  String get production => 'Продакшн';

  @override
  String get staging => 'Тестове середовище';

  @override
  String get switchRequiresRestart => 'Перемикання потребує перезапуску додатку';

  @override
  String get switchApiConfirmTitle => 'Перемикання середовища API';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Перемкнути на $environment? Вам потрібно буде закрити та знову відкрити додаток, щоб зміни набули чинності.';
  }

  @override
  String get switchAndRestart => 'Перемкнути';

  @override
  String get stagingDisclaimer =>
      'Тестове середовище може бути нестабільним, мати непослідовну продуктивність, і дані можуть бути втрачені. Тільки для тестування.';

  @override
  String get apiEnvSavedRestartRequired => 'Збережено. Закрийте та знову відкрийте додаток, щоб застосувати зміни.';

  @override
  String get shared => 'Спільний';

  @override
  String get onlyYouCanSeeConversation => 'Лише ви можете бачити цю розмову';

  @override
  String get anyoneWithLinkCanView => 'Будь-хто з посиланням може переглядати';

  @override
  String get tasksCleanTodayTitle => 'Очистити завдання на сьогодні?';

  @override
  String get tasksCleanTodayMessage => 'Це видалить лише дедлайни';

  @override
  String get tasksOverdue => 'Прострочені';

  @override
  String get phoneCallsWithOmi => 'Дзвінки з Omi';

  @override
  String get phoneCallsSubtitle => 'Дзвоніть з транскрипцією в реальному часі';

  @override
  String get phoneSetupStep1Title => 'Підтвердіть свій номер телефону';

  @override
  String get phoneSetupStep1Subtitle => 'Ми зателефонуємо для підтвердження';

  @override
  String get phoneSetupStep2Title => 'Введіть код підтвердження';

  @override
  String get phoneSetupStep2Subtitle => 'Короткий код, який ви введете під час дзвінка';

  @override
  String get phoneSetupStep3Title => 'Почніть дзвонити своїм контактам';

  @override
  String get phoneSetupStep3Subtitle => 'З вбудованою живою транскрипцією';

  @override
  String get phoneGetStarted => 'Розпочати';

  @override
  String get callRecordingConsentDisclaimer => 'Запис дзвінків може вимагати згоди у вашій юрисдикції';

  @override
  String get enterYourNumber => 'Введіть свій номер';

  @override
  String get phoneNumberCallerIdHint => 'Після підтвердження це стане вашим ID дзвінка';

  @override
  String get phoneNumberHint => 'Номер телефону';

  @override
  String get failedToStartVerification => 'Не вдалося розпочати підтвердження';

  @override
  String get phoneContinue => 'Продовжити';

  @override
  String get verifyYourNumber => 'Підтвердіть свій номер';

  @override
  String get answerTheCallFrom => 'Відповідайте на дзвінок від';

  @override
  String get onTheCallEnterThisCode => 'Під час дзвінка введіть цей код';

  @override
  String get followTheVoiceInstructions => 'Дотримуйтесь голосових інструкцій';

  @override
  String get statusCalling => 'Дзвоним...';

  @override
  String get statusCallInProgress => 'Дзвінок йде';

  @override
  String get statusVerifiedLabel => 'Підтверджено';

  @override
  String get statusCallMissed => 'Пропущений дзвінок';

  @override
  String get statusTimedOut => 'Час вийшов';

  @override
  String get phoneTryAgain => 'Спробувати знову';

  @override
  String get phonePageTitle => 'Телефон';

  @override
  String get phoneContactsTab => 'Контакти';

  @override
  String get phoneKeypadTab => 'Клавіатура';

  @override
  String get grantContactsAccess => 'Надайте доступ до контактів';

  @override
  String get phoneAllow => 'Дозволити';

  @override
  String get phoneSearchHint => 'Пошук';

  @override
  String get phoneNoContactsFound => 'Контакти не знайдено';

  @override
  String get phoneEnterNumber => 'Введіть номер';

  @override
  String get failedToStartCall => 'Не вдалося розпочати дзвінок';

  @override
  String get callStateConnecting => 'Підключення...';

  @override
  String get callStateRinging => 'Дзвонить...';

  @override
  String get callStateEnded => 'Дзвінок завершено';

  @override
  String get callStateFailed => 'Дзвінок не вдався';

  @override
  String get transcriptPlaceholder => 'Транскрипція з\'явиться тут...';

  @override
  String get phoneUnmute => 'Увімкнути звук';

  @override
  String get phoneMute => 'Вимкнути звук';

  @override
  String get phoneSpeaker => 'Динамік';

  @override
  String get phoneEndCall => 'Завершити';

  @override
  String get phoneCallSettingsTitle => 'Налаштування дзвінків';

  @override
  String get yourVerifiedNumbers => 'Ваші підтверджені номери';

  @override
  String get verifiedNumbersDescription => 'Коли ви дзвоните, абонент побачить цей номер';

  @override
  String get noVerifiedNumbers => 'Немає підтверджених номерів';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Видалити $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Для дзвінків потрібно буде повторно підтвердити';

  @override
  String get phoneDeleteButton => 'Видалити';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Підтверджено $minutesхв тому';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Підтверджено $hoursгод тому';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Підтверджено $daysд тому';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Підтверджено $date';
  }

  @override
  String get verifiedFallback => 'Підтверджено';

  @override
  String get callAlreadyInProgress => 'Дзвінок вже йде';

  @override
  String get failedToGetCallToken => 'Не вдалося отримати токен. Спочатку підтвердіть номер.';

  @override
  String get failedToInitializeCallService => 'Не вдалося ініціалізувати службу дзвінків';

  @override
  String get speakerLabelYou => 'Ви';

  @override
  String get speakerLabelUnknown => 'Невідомий';

  @override
  String get showDailyScoreOnHomepage => 'Показати щоденний рахунок на головній сторінці';

  @override
  String get showTasksOnHomepage => 'Показати завдання на головній сторінці';

  @override
  String get phoneCallsUnlimitedOnly => 'Телефонні дзвінки через Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Здійснюйте дзвінки через Omi та отримуйте транскрипцію в реальному часі, автоматичні зведення та багато іншого.';

  @override
  String get phoneCallsUpsellFeature1 => 'Транскрипція кожного дзвінка в реальному часі';

  @override
  String get phoneCallsUpsellFeature2 => 'Автоматичні зведення дзвінків та завдання';

  @override
  String get phoneCallsUpsellFeature3 => 'Одержувачі бачать ваш справжній номер, а не випадковий';

  @override
  String get phoneCallsUpsellFeature4 => 'Ваші дзвінки залишаються приватними та захищеними';

  @override
  String get phoneCallsUpgradeButton => 'Перейти на Безлімітний';

  @override
  String get phoneCallsMaybeLater => 'Можливо пізніше';
}
