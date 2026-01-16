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
  String get conversationUrlCouldNotBeShared => 'URL-адресу розмови не вдалося поширити.';

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
  String get noApiKeysYet => 'API-ключів поки немає. Створіть один для інтеграції з вашим додатком.';

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
  String get debugAndDiagnostics => 'Налагодження та діагностика';

  @override
  String get autoDeletesAfter3Days => 'Автоматичне видалення через 3 дні';

  @override
  String get helpsDiagnoseIssues => 'Допомагає діагностувати проблеми';

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
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Додаткові питання';

  @override
  String get suggestQuestionsAfterConversations => 'Пропонувати питання після розмов';

  @override
  String get goalTracker => 'Відстеження цілей';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Щоденна рефлексія';

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
  String get all => 'Всі';

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
  String get starred => 'Обране';

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
  String get noSummaryForApp => 'Для цього додатка резюме недоступне. Спробуйте інший додаток для кращих результатів.';

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
  String get unknownApp => 'Невідомий додаток';

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
  String get dailySummary => 'Щоденна Зведення';

  @override
  String get developer => 'Розробник';

  @override
  String get about => 'Про програму';

  @override
  String get selectTime => 'Вибрати Час';

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
  String get dailySummaryDescription => 'Отримуйте персоналізовану зведення ваших розмов';

  @override
  String get deliveryTime => 'Час Доставки';

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
  String get upcomingMeetings => 'МАЙБУТНІ ЗУСТРІЧІ';

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
  String get dailyReflectionDescription => 'Нагадування о 21:00 для роздумів про ваш день';

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
  String get invalidIntegrationUrl => 'Недійсний URL інтеграції';

  @override
  String get tapToComplete => 'Торкніться для завершення';

  @override
  String get invalidSetupInstructionsUrl => 'Недійсний URL інструкцій з налаштування';

  @override
  String get pushToTalk => 'Натисніть, щоб говорити';

  @override
  String get summaryPrompt => 'Промпт резюме';

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
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

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
}
