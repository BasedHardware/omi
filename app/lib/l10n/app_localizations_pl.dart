// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Polish (`pl`).
class AppLocalizationsPl extends AppLocalizations {
  AppLocalizationsPl([String locale = 'pl']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Rozmowa';

  @override
  String get transcriptTab => 'Transkrypcja';

  @override
  String get actionItemsTab => 'Zadania';

  @override
  String get deleteConversationTitle => 'Usunąć rozmowę?';

  @override
  String get deleteConversationMessage =>
      'Czy na pewno chcesz usunąć tę rozmowę? Ta czynność nie może zostać cofnięta.';

  @override
  String get confirm => 'Potwierdź';

  @override
  String get cancel => 'Anuluj';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Usuń';

  @override
  String get add => 'Dodaj';

  @override
  String get update => 'Aktualizuj';

  @override
  String get save => 'Zapisz';

  @override
  String get edit => 'Edytuj';

  @override
  String get close => 'Zamknij';

  @override
  String get clear => 'Wyczyść';

  @override
  String get copyTranscript => 'Kopiuj transkrypcję';

  @override
  String get copySummary => 'Kopiuj podsumowanie';

  @override
  String get testPrompt => 'Testuj prompt';

  @override
  String get reprocessConversation => 'Przetwórz ponownie rozmowę';

  @override
  String get deleteConversation => 'Usuń rozmowę';

  @override
  String get contentCopied => 'Zawartość skopiowana do schowka';

  @override
  String get failedToUpdateStarred => 'Nie udało się zaktualizować statusu ulubionego.';

  @override
  String get conversationUrlNotShared => 'Nie można udostępnić adresu URL rozmowy.';

  @override
  String get errorProcessingConversation => 'Błąd podczas przetwarzania rozmowy. Spróbuj ponownie później.';

  @override
  String get noInternetConnection => 'Brak połączenia z internetem';

  @override
  String get unableToDeleteConversation => 'Nie można usunąć rozmowy';

  @override
  String get somethingWentWrong => 'Coś poszło nie tak! Spróbuj ponownie później.';

  @override
  String get copyErrorMessage => 'Kopiuj komunikat błędu';

  @override
  String get errorCopied => 'Komunikat błędu skopiowany do schowka';

  @override
  String get remaining => 'Pozostało';

  @override
  String get loading => 'Ładowanie...';

  @override
  String get loadingDuration => 'Ładowanie czasu trwania...';

  @override
  String secondsCount(int count) {
    return '$count sekund';
  }

  @override
  String get people => 'Osoby';

  @override
  String get addNewPerson => 'Dodaj nową osobę';

  @override
  String get editPerson => 'Edytuj osobę';

  @override
  String get createPersonHint => 'Utwórz nową osobę i naucz Omi rozpoznawać jej głos!';

  @override
  String get speechProfile => 'Profil Mowy';

  @override
  String sampleNumber(int number) {
    return 'Próbka $number';
  }

  @override
  String get settings => 'Ustawienia';

  @override
  String get language => 'Język';

  @override
  String get selectLanguage => 'Wybierz język';

  @override
  String get deleting => 'Usuwanie...';

  @override
  String get pleaseCompleteAuthentication =>
      'Ukończ uwierzytelnianie w przeglądarce. Po zakończeniu wróć do aplikacji.';

  @override
  String get failedToStartAuthentication => 'Nie udało się rozpocząć uwierzytelniania';

  @override
  String get importStarted => 'Import rozpoczęty! Otrzymasz powiadomienie po zakończeniu.';

  @override
  String get failedToStartImport => 'Nie udało się rozpocząć importu. Spróbuj ponownie.';

  @override
  String get couldNotAccessFile => 'Nie można uzyskać dostępu do wybranego pliku';

  @override
  String get askOmi => 'Zapytaj Omi';

  @override
  String get done => 'Gotowe';

  @override
  String get disconnected => 'Rozłączono';

  @override
  String get searching => 'Wyszukiwanie...';

  @override
  String get connectDevice => 'Połącz urządzenie';

  @override
  String get monthlyLimitReached => 'Osiągnięto miesięczny limit.';

  @override
  String get checkUsage => 'Sprawdź wykorzystanie';

  @override
  String get syncingRecordings => 'Synchronizacja nagrań';

  @override
  String get recordingsToSync => 'Nagrania do synchronizacji';

  @override
  String get allCaughtUp => 'Wszystko na bieżąco';

  @override
  String get sync => 'Synchronizuj';

  @override
  String get pendantUpToDate => 'Pendant jest aktualny';

  @override
  String get allRecordingsSynced => 'Wszystkie nagrania są zsynchronizowane';

  @override
  String get syncingInProgress => 'Trwa synchronizacja';

  @override
  String get readyToSync => 'Gotowe do synchronizacji';

  @override
  String get tapSyncToStart => 'Dotknij Synchronizuj, aby rozpocząć';

  @override
  String get pendantNotConnected => 'Pendant nie jest podłączony. Podłącz, aby zsynchronizować.';

  @override
  String get everythingSynced => 'Wszystko jest już zsynchronizowane.';

  @override
  String get recordingsNotSynced => 'Masz nagrania, które nie zostały jeszcze zsynchronizowane.';

  @override
  String get syncingBackground => 'Będziemy synchronizować Twoje nagrania w tle.';

  @override
  String get noConversationsYet => 'Jeszcze brak rozmów';

  @override
  String get noStarredConversations => 'Brak rozmów oznaczonych gwiazdką';

  @override
  String get starConversationHint => 'Aby oznaczyć rozmowę gwiazdką, otwórz ją i dotknij ikony gwiazdki w nagłówku.';

  @override
  String get searchConversations => 'Szukaj rozmów...';

  @override
  String selectedCount(int count, Object s) {
    return 'Wybrano: $count';
  }

  @override
  String get merge => 'Scal';

  @override
  String get mergeConversations => 'Scal rozmowy';

  @override
  String mergeConversationsMessage(int count) {
    return 'Spowoduje to połączenie $count rozmów w jedną. Cała zawartość zostanie scalone i wygenerowana ponownie.';
  }

  @override
  String get mergingInBackground => 'Scalanie w tle. To może chwilę potrwać.';

  @override
  String get failedToStartMerge => 'Nie udało się rozpocząć scalania';

  @override
  String get askAnything => 'Zapytaj o cokolwiek';

  @override
  String get noMessagesYet => 'Brak wiadomości!\nCzemu nie rozpoczniesz rozmowy?';

  @override
  String get deletingMessages => 'Usuwanie wiadomości z pamięci Omi...';

  @override
  String get messageCopied => '✨ Wiadomość skopiowana do schowka';

  @override
  String get cannotReportOwnMessage => 'Nie możesz zgłosić własnych wiadomości.';

  @override
  String get reportMessage => 'Zgłoś wiadomość';

  @override
  String get reportMessageConfirm => 'Czy na pewno chcesz zgłosić tę wiadomość?';

  @override
  String get messageReported => 'Wiadomość zgłoszona pomyślnie.';

  @override
  String get thankYouFeedback => 'Dziękujemy za opinię!';

  @override
  String get clearChat => 'Wyczyść czat';

  @override
  String get clearChatConfirm => 'Czy na pewno chcesz wyczyścić czat? Ta czynność nie może zostać cofnięta.';

  @override
  String get maxFilesLimit => 'Możesz przesłać maksymalnie 4 pliki naraz';

  @override
  String get chatWithOmi => 'Czat z Omi';

  @override
  String get apps => 'Aplikacje';

  @override
  String get noAppsFound => 'Nie znaleziono aplikacji';

  @override
  String get tryAdjustingSearch => 'Spróbuj dostosować wyszukiwanie lub filtry';

  @override
  String get createYourOwnApp => 'Stwórz własną aplikację';

  @override
  String get buildAndShareApp => 'Zbuduj i udostępnij swoją własną aplikację';

  @override
  String get searchApps => 'Szukaj aplikacji...';

  @override
  String get myApps => 'Moje aplikacje';

  @override
  String get installedApps => 'Zainstalowane aplikacje';

  @override
  String get unableToFetchApps => 'Nie można pobrać aplikacji :(\n\nSprawdź połączenie internetowe i spróbuj ponownie.';

  @override
  String get aboutOmi => 'O Omi';

  @override
  String get privacyPolicy => 'Polityką prywatności';

  @override
  String get visitWebsite => 'Odwiedź stronę internetową';

  @override
  String get helpOrInquiries => 'Pomoc lub pytania?';

  @override
  String get joinCommunity => 'Dołącz do społeczności!';

  @override
  String get membersAndCounting => '8000+ członków i przybywa.';

  @override
  String get deleteAccountTitle => 'Usuń konto';

  @override
  String get deleteAccountConfirm => 'Czy na pewno chcesz usunąć swoje konto?';

  @override
  String get cannotBeUndone => 'Tej operacji nie można cofnąć.';

  @override
  String get allDataErased => 'Wszystkie Twoje wspomnienia i rozmowy zostaną trwale usunięte.';

  @override
  String get appsDisconnected => 'Twoje aplikacje i integracje zostaną natychmiast rozłączone.';

  @override
  String get exportBeforeDelete =>
      'Możesz wyeksportować swoje dane przed usunięciem konta, ale po usunięciu nie można ich odzyskać.';

  @override
  String get deleteAccountCheckbox =>
      'Rozumiem, że usunięcie mojego konta jest trwałe i wszystkie dane, w tym wspomnienia i rozmowy, zostaną utracone bez możliwości odzyskania.';

  @override
  String get areYouSure => 'Czy jesteś pewien?';

  @override
  String get deleteAccountFinal =>
      'Ta czynność jest nieodwracalna i trwale usunie Twoje konto oraz wszystkie powiązane dane. Czy na pewno chcesz kontynuować?';

  @override
  String get deleteNow => 'Usuń teraz';

  @override
  String get goBack => 'Wróć';

  @override
  String get checkBoxToConfirm =>
      'Zaznacz pole, aby potwierdzić, że rozumiesz, iż usunięcie konta jest trwałe i nieodwracalne.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Imię';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Niestandardowy Słownik';

  @override
  String get identifyingOthers => 'Identyfikacja Innych';

  @override
  String get paymentMethods => 'Metody Płatności';

  @override
  String get conversationDisplay => 'Wyświetlanie Rozmów';

  @override
  String get dataPrivacy => 'Prywatność Danych';

  @override
  String get userId => 'ID Użytkownika';

  @override
  String get notSet => 'Nie ustawiono';

  @override
  String get userIdCopied => 'ID użytkownika skopiowane do schowka';

  @override
  String get systemDefault => 'Domyślny systemowy';

  @override
  String get planAndUsage => 'Plan i wykorzystanie';

  @override
  String get offlineSync => 'Synchronizacja offline';

  @override
  String get deviceSettings => 'Ustawienia urządzenia';

  @override
  String get integrations => 'Integracje';

  @override
  String get feedbackBug => 'Opinia / Błąd';

  @override
  String get helpCenter => 'Centrum pomocy';

  @override
  String get developerSettings => 'Ustawienia dewelopera';

  @override
  String get getOmiForMac => 'Pobierz Omi dla Mac';

  @override
  String get referralProgram => 'Program poleceń';

  @override
  String get signOut => 'Wyloguj';

  @override
  String get appAndDeviceCopied => 'Szczegóły aplikacji i urządzenia skopiowane';

  @override
  String get wrapped2025 => 'Podsumowanie 2025';

  @override
  String get yourPrivacyYourControl => 'Twoja prywatność, Twoja kontrola';

  @override
  String get privacyIntro =>
      'W Omi dbamy o Twoją prywatność. Ta strona pozwala kontrolować sposób przechowywania i wykorzystywania Twoich danych.';

  @override
  String get learnMore => 'Dowiedz się więcej...';

  @override
  String get dataProtectionLevel => 'Poziom ochrony danych';

  @override
  String get dataProtectionDesc =>
      'Twoje dane są domyślnie zabezpieczone silnym szyfrowaniem. Przejrzyj swoje ustawienia i przyszłe opcje prywatności poniżej.';

  @override
  String get appAccess => 'Dostęp aplikacji';

  @override
  String get appAccessDesc =>
      'Następujące aplikacje mogą uzyskać dostęp do Twoich danych. Dotknij aplikacji, aby zarządzać jej uprawnieniami.';

  @override
  String get noAppsExternalAccess => 'Żadne zainstalowane aplikacje nie mają zewnętrznego dostępu do Twoich danych.';

  @override
  String get deviceName => 'Nazwa urządzenia';

  @override
  String get deviceId => 'ID urządzenia';

  @override
  String get firmware => 'Oprogramowanie sprzętowe';

  @override
  String get sdCardSync => 'Synchronizacja karty SD';

  @override
  String get hardwareRevision => 'Wersja sprzętu';

  @override
  String get modelNumber => 'Numer modelu';

  @override
  String get manufacturer => 'Producent';

  @override
  String get doubleTap => 'Podwójne dotknięcie';

  @override
  String get ledBrightness => 'Jasność LED';

  @override
  String get micGain => 'Wzmocnienie mikrofonu';

  @override
  String get disconnect => 'Rozłącz';

  @override
  String get forgetDevice => 'Zapomnij urządzenie';

  @override
  String get chargingIssues => 'Problemy z ładowaniem';

  @override
  String get disconnectDevice => 'Odłącz urządzenie';

  @override
  String get unpairDevice => 'Rozłącz urządzenie';

  @override
  String get unpairAndForget => 'Rozparuj i zapomnij urządzenie';

  @override
  String get deviceDisconnectedMessage => 'Twoje Omi zostało rozłączone 😔';

  @override
  String get deviceUnpairedMessage =>
      'Urządzenie rozłączone. Przejdź do Ustawienia > Bluetooth i zapomnij urządzenie, aby zakończyć rozłączanie.';

  @override
  String get unpairDialogTitle => 'Rozparuj urządzenie';

  @override
  String get unpairDialogMessage =>
      'Spowoduje to rozparowanie urządzenia, aby można je było podłączyć do innego telefonu. Musisz przejść do Ustawienia > Bluetooth i zapomnieć urządzenie, aby zakończyć proces.';

  @override
  String get deviceNotConnected => 'Urządzenie nie jest podłączone';

  @override
  String get connectDeviceMessage =>
      'Podłącz swoje urządzenie Omi, aby uzyskać dostęp\ndo ustawień urządzenia i personalizacji';

  @override
  String get deviceInfoSection => 'Informacje o urządzeniu';

  @override
  String get customizationSection => 'Personalizacja';

  @override
  String get hardwareSection => 'Sprzęt';

  @override
  String get v2Undetected => 'Nie wykryto V2';

  @override
  String get v2UndetectedMessage =>
      'Widzimy, że masz urządzenie V1 lub Twoje urządzenie nie jest podłączone. Funkcja karty SD jest dostępna tylko dla urządzeń V2.';

  @override
  String get endConversation => 'Zakończ rozmowę';

  @override
  String get pauseResume => 'Wstrzymaj/Wznów';

  @override
  String get starConversation => 'Oznacz rozmowę gwiazdką';

  @override
  String get doubleTapAction => 'Akcja podwójnego dotknięcia';

  @override
  String get endAndProcess => 'Zakończ i przetwórz rozmowę';

  @override
  String get pauseResumeRecording => 'Wstrzymaj/wznów nagrywanie';

  @override
  String get starOngoing => 'Oznacz bieżącą rozmowę gwiazdką';

  @override
  String get off => 'Wyłączone';

  @override
  String get max => 'Maks.';

  @override
  String get mute => 'Wycisz';

  @override
  String get quiet => 'Cicho';

  @override
  String get normal => 'Normalnie';

  @override
  String get high => 'Wysoko';

  @override
  String get micGainDescMuted => 'Mikrofon jest wyciszony';

  @override
  String get micGainDescLow => 'Bardzo cicho - do głośnych środowisk';

  @override
  String get micGainDescModerate => 'Cicho - do umiarkowanego hałasu';

  @override
  String get micGainDescNeutral => 'Neutralnie - zrównoważone nagrywanie';

  @override
  String get micGainDescSlightlyBoosted => 'Lekko wzmocnione - normalne użycie';

  @override
  String get micGainDescBoosted => 'Wzmocnione - do cichych środowisk';

  @override
  String get micGainDescHigh => 'Wysokie - do odległych lub cichych głosów';

  @override
  String get micGainDescVeryHigh => 'Bardzo wysokie - do bardzo cichych źródeł';

  @override
  String get micGainDescMax => 'Maksymalne - używaj z ostrożnością';

  @override
  String get developerSettingsTitle => 'Ustawienia programisty';

  @override
  String get saving => 'Zapisywanie...';

  @override
  String get personaConfig => 'Skonfiguruj swoją osobowość AI';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkrypcja';

  @override
  String get transcriptionConfig => 'Skonfiguruj dostawcę STT';

  @override
  String get conversationTimeout => 'Limit czasu rozmowy';

  @override
  String get conversationTimeoutConfig => 'Ustaw, kiedy rozmowy kończą się automatycznie';

  @override
  String get importData => 'Importuj dane';

  @override
  String get importDataConfig => 'Importuj dane z innych źródeł';

  @override
  String get debugDiagnostics => 'Debugowanie i diagnostyka';

  @override
  String get endpointUrl => 'URL punktu końcowego';

  @override
  String get noApiKeys => 'Brak kluczy API';

  @override
  String get createKeyToStart => 'Utwórz klucz, aby rozpocząć';

  @override
  String get createKey => 'Utwórz Klucz';

  @override
  String get docs => 'Dokumentacja';

  @override
  String get yourOmiInsights => 'Twoje statystyki Omi';

  @override
  String get today => 'Dzisiaj';

  @override
  String get thisMonth => 'W tym miesiącu';

  @override
  String get thisYear => 'W tym roku';

  @override
  String get allTime => 'Cały czas';

  @override
  String get noActivityYet => 'Brak aktywności';

  @override
  String get startConversationToSeeInsights =>
      'Rozpocznij rozmowę z Omi,\naby zobaczyć tutaj statystyki wykorzystania.';

  @override
  String get listening => 'Słuchanie';

  @override
  String get listeningSubtitle => 'Całkowity czas, przez który Omi aktywnie słuchało.';

  @override
  String get understanding => 'Rozumienie';

  @override
  String get understandingSubtitle => 'Słowa zrozumiane z Twoich rozmów.';

  @override
  String get providing => 'Dostarczanie';

  @override
  String get providingSubtitle => 'Zadania i notatki automatycznie zarejestrowane.';

  @override
  String get remembering => 'Zapamiętywanie';

  @override
  String get rememberingSubtitle => 'Fakty i szczegóły zapamiętane dla Ciebie.';

  @override
  String get unlimitedPlan => 'Plan nieograniczony';

  @override
  String get managePlan => 'Zarządzaj planem';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Twój plan zostanie anulowany $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Twój plan odnawia się $date.';
  }

  @override
  String get basicPlan => 'Plan darmowy';

  @override
  String usageLimitMessage(String used, int limit) {
    return 'Wykorzystano $used z $limit min';
  }

  @override
  String get upgrade => 'Ulepsz';

  @override
  String get upgradeToUnlimited => 'Uaktualnij do nieograniczonego';

  @override
  String basicPlanDesc(int limit) {
    return 'Twój plan obejmuje $limit darmowych minut miesięcznie. Ulepsz, aby uzyskać nielimitowany dostęp.';
  }

  @override
  String get shareStatsMessage => 'Udostępniam moje statystyki Omi! (omi.me - Twój asystent AI zawsze dostępny)';

  @override
  String get sharePeriodToday => 'Dzisiaj Omi:';

  @override
  String get sharePeriodMonth => 'W tym miesiącu Omi:';

  @override
  String get sharePeriodYear => 'W tym roku Omi:';

  @override
  String get sharePeriodAllTime => 'Do tej pory Omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Słuchało przez $minutes minut';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Zrozumiało $words słów';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Dostarczyło $count spostrzeżeń';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Zapamiętało $count wspomnień';
  }

  @override
  String get debugLogs => 'Dzienniki debugowania';

  @override
  String get debugLogsAutoDelete => 'Automatyczne usuwanie po 3 dniach.';

  @override
  String get debugLogsDesc => 'Pomaga diagnozować problemy';

  @override
  String get noLogFilesFound => 'Nie znaleziono plików dziennika.';

  @override
  String get omiDebugLog => 'Log debugowania Omi';

  @override
  String get logShared => 'Log udostępniony';

  @override
  String get selectLogFile => 'Wybierz plik logu';

  @override
  String get shareLogs => 'Udostępnij dzienniki';

  @override
  String get debugLogCleared => 'Log debugowania wyczyszczony';

  @override
  String get exportStarted => 'Eksport rozpoczęty. To może potrwać kilka sekund...';

  @override
  String get exportAllData => 'Eksportuj wszystkie dane';

  @override
  String get exportDataDesc => 'Eksportuj rozmowy do pliku JSON';

  @override
  String get exportedConversations => 'Wyeksportowane rozmowy z Omi';

  @override
  String get exportShared => 'Eksport udostępniony';

  @override
  String get deleteKnowledgeGraphTitle => 'Usunąć graf wiedzy?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Spowoduje to usunięcie wszystkich danych grafu wiedzy (węzłów i połączeń). Twoje oryginalne wspomnienia pozostaną bezpieczne. Graf zostanie odbudowany z czasem lub na następne żądanie.';

  @override
  String get knowledgeGraphDeleted => 'Graf wiedzy usunięty';

  @override
  String deleteGraphFailed(String error) {
    return 'Nie udało się usunąć grafu: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Usuń graf wiedzy';

  @override
  String get deleteKnowledgeGraphDesc => 'Wyczyść wszystkie węzły i połączenia';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Serwer MCP';

  @override
  String get mcpServerDesc => 'Połącz asystentów AI z Twoimi danymi';

  @override
  String get serverUrl => 'Adres URL serwera';

  @override
  String get urlCopied => 'Skopiowano URL';

  @override
  String get apiKeyAuth => 'Uwierzytelnianie kluczem API';

  @override
  String get header => 'Nagłówek';

  @override
  String get authorizationBearer => 'Authorization: Bearer <klucz>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID klienta';

  @override
  String get clientSecret => 'Sekret klienta';

  @override
  String get useMcpApiKey => 'Użyj swojego klucza API MCP';

  @override
  String get webhooks => 'Webhooki';

  @override
  String get conversationEvents => 'Zdarzenia rozmowy';

  @override
  String get newConversationCreated => 'Utworzono nową rozmowę';

  @override
  String get realtimeTranscript => 'Transkrypcja w czasie rzeczywistym';

  @override
  String get transcriptReceived => 'Otrzymano transkrypcję';

  @override
  String get audioBytes => 'Bajty audio';

  @override
  String get audioDataReceived => 'Otrzymano dane audio';

  @override
  String get intervalSeconds => 'Interwał (sekundy)';

  @override
  String get daySummary => 'Podsumowanie dnia';

  @override
  String get summaryGenerated => 'Wygenerowano podsumowanie';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Dodaj do claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopiuj konfigurację';

  @override
  String get configCopied => 'Konfiguracja skopiowana do schowka';

  @override
  String get listeningMins => 'Słuchanie (min)';

  @override
  String get understandingWords => 'Rozumienie (słowa)';

  @override
  String get insights => 'Spostrzeżenia';

  @override
  String get memories => 'Wspomnienia';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'Wykorzystano $used z $limit min w tym miesiącu';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'Wykorzystano $used z $limit słów w tym miesiącu';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'Uzyskano $used z $limit spostrzeżeń w tym miesiącu';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'Utworzono $used z $limit wspomnień w tym miesiącu';
  }

  @override
  String get visibility => 'Widoczność';

  @override
  String get visibilitySubtitle => 'Kontroluj, które rozmowy pojawiają się na Twojej liście';

  @override
  String get showShortConversations => 'Pokaż krótkie rozmowy';

  @override
  String get showShortConversationsDesc => 'Wyświetl rozmowy krótsze niż próg';

  @override
  String get showDiscardedConversations => 'Pokaż odrzucone rozmowy';

  @override
  String get showDiscardedConversationsDesc => 'Uwzględnij rozmowy oznaczone jako odrzucone';

  @override
  String get shortConversationThreshold => 'Próg krótkiej rozmowy';

  @override
  String get shortConversationThresholdSubtitle =>
      'Rozmowy krótsze niż ten próg będą ukryte, chyba że włączysz powyższą opcję';

  @override
  String get durationThreshold => 'Próg czasu trwania';

  @override
  String get durationThresholdDesc => 'Ukryj rozmowy krótsze niż ten próg';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Własny słownik';

  @override
  String get addWords => 'Dodaj słowa';

  @override
  String get addWordsDesc => 'Imiona, terminy lub rzadkie słowa';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Połącz';

  @override
  String get comingSoon => 'Wkrótce';

  @override
  String get integrationsFooter => 'Połącz swoje aplikacje, aby wyświetlać dane i metryki w czacie.';

  @override
  String get completeAuthInBrowser => 'Ukończ uwierzytelnianie w przeglądarce. Po zakończeniu wróć do aplikacji.';

  @override
  String failedToStartAuth(String appName) {
    return 'Nie udało się rozpocząć uwierzytelniania $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Rozłączyć $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Czy na pewno chcesz rozłączyć się z $appName? Możesz ponownie połączyć w dowolnym momencie.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Rozłączono z $appName';
  }

  @override
  String get failedToDisconnect => 'Nie udało się rozłączyć';

  @override
  String connectTo(String appName) {
    return 'Połącz z $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Musisz upoważnić Omi do dostępu do Twoich danych $appName. Otworzy to przeglądarkę w celu uwierzytelnienia.';
  }

  @override
  String get continueAction => 'Kontynuuj';

  @override
  String get languageTitle => 'Język';

  @override
  String get primaryLanguage => 'Język podstawowy';

  @override
  String get automaticTranslation => 'Automatyczne tłumaczenie';

  @override
  String get detectLanguages => 'Wykryj ponad 10 języków';

  @override
  String get authorizeSavingRecordings => 'Autoryzuj zapisywanie nagrań';

  @override
  String get thanksForAuthorizing => 'Dziękujemy za autoryzację!';

  @override
  String get needYourPermission => 'Potrzebujemy Twojego pozwolenia';

  @override
  String get alreadyGavePermission =>
      'Już udzieliłeś nam zgody na zapisywanie nagrań. Oto przypomnienie, dlaczego tego potrzebujemy:';

  @override
  String get wouldLikePermission => 'Chcielibyśmy uzyskać Twoją zgodę na zapisywanie nagrań głosowych. Oto dlaczego:';

  @override
  String get improveSpeechProfile => 'Popraw swój profil głosu';

  @override
  String get improveSpeechProfileDesc =>
      'Używamy nagrań do dalszego szkolenia i ulepszania Twojego osobistego profilu głosu.';

  @override
  String get trainFamilyProfiles => 'Trenuj profile dla przyjaciół i rodziny';

  @override
  String get trainFamilyProfilesDesc =>
      'Twoje nagrania pomagają nam rozpoznawać i tworzyć profile dla Twoich przyjaciół i rodziny.';

  @override
  String get enhanceTranscriptAccuracy => 'Zwiększ dokładność transkrypcji';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'W miarę jak nasz model się poprawia, możemy zapewnić lepsze wyniki transkrypcji Twoich nagrań.';

  @override
  String get legalNotice =>
      'Uwaga prawna: Legalność nagrywania i przechowywania danych głosowych może się różnić w zależności od lokalizacji i sposobu korzystania z tej funkcji. Twoim obowiązkiem jest zapewnienie zgodności z lokalnymi przepisami i regulacjami.';

  @override
  String get alreadyAuthorized => 'Już autoryzowano';

  @override
  String get authorize => 'Autoryzuj';

  @override
  String get revokeAuthorization => 'Cofnij autoryzację';

  @override
  String get authorizationSuccessful => 'Autoryzacja pomyślna!';

  @override
  String get failedToAuthorize => 'Nie udało się autoryzować. Spróbuj ponownie.';

  @override
  String get authorizationRevoked => 'Autoryzacja cofnięta.';

  @override
  String get recordingsDeleted => 'Nagrania usunięte.';

  @override
  String get failedToRevoke => 'Nie udało się cofnąć autoryzacji. Spróbuj ponownie.';

  @override
  String get permissionRevokedTitle => 'Cofnięto pozwolenie';

  @override
  String get permissionRevokedMessage => 'Czy chcesz, abyśmy usunęli również wszystkie Twoje istniejące nagrania?';

  @override
  String get yes => 'Tak';

  @override
  String get editName => 'Edytuj imię';

  @override
  String get howShouldOmiCallYou => 'Jak Omi powinno Cię nazywać?';

  @override
  String get enterYourName => 'Wprowadź swoje imię';

  @override
  String get nameCannotBeEmpty => 'Imię nie może być puste';

  @override
  String get nameUpdatedSuccessfully => 'Imię zaktualizowane pomyślnie!';

  @override
  String get calendarSettings => 'Ustawienia kalendarza';

  @override
  String get calendarProviders => 'Dostawcy kalendarza';

  @override
  String get macOsCalendar => 'Kalendarz macOS';

  @override
  String get connectMacOsCalendar => 'Połącz swój lokalny kalendarz macOS';

  @override
  String get googleCalendar => 'Kalendarz Google';

  @override
  String get syncGoogleAccount => 'Synchronizuj z kontem Google';

  @override
  String get showMeetingsMenuBar => 'Pokaż nadchodzące spotkania w pasku menu';

  @override
  String get showMeetingsMenuBarDesc => 'Wyświetl następne spotkanie i czas do jego rozpoczęcia w pasku menu macOS';

  @override
  String get showEventsNoParticipants => 'Pokaż wydarzenia bez uczestników';

  @override
  String get showEventsNoParticipantsDesc =>
      'Po włączeniu, Nadchodzące pokazuje wydarzenia bez uczestników lub linku wideo.';

  @override
  String get yourMeetings => 'Twoje spotkania';

  @override
  String get refresh => 'Odśwież';

  @override
  String get noUpcomingMeetings => 'Brak nadchodzących spotkań';

  @override
  String get checkingNextDays => 'Sprawdzanie następnych 30 dni';

  @override
  String get tomorrow => 'Jutro';

  @override
  String get googleCalendarComingSoon => 'Integracja z Kalendarzem Google wkrótce!';

  @override
  String connectedAsUser(String userId) {
    return 'Połączono jako użytkownik: $userId';
  }

  @override
  String get defaultWorkspace => 'Domyślny obszar roboczy';

  @override
  String get tasksCreatedInWorkspace => 'Zadania będą tworzone w tym obszarze roboczym';

  @override
  String get defaultProjectOptional => 'Domyślny projekt (opcjonalnie)';

  @override
  String get leaveUnselectedTasks => 'Pozostaw niezaznaczone, aby tworzyć zadania bez projektu';

  @override
  String get noProjectsInWorkspace => 'Nie znaleziono projektów w tym obszarze roboczym';

  @override
  String get conversationTimeoutDesc => 'Wybierz, jak długo czekać w ciszy przed automatycznym zakończeniem rozmowy:';

  @override
  String get timeout2Minutes => '2 minuty';

  @override
  String get timeout2MinutesDesc => 'Zakończ rozmowę po 2 minutach ciszy';

  @override
  String get timeout5Minutes => '5 minut';

  @override
  String get timeout5MinutesDesc => 'Zakończ rozmowę po 5 minutach ciszy';

  @override
  String get timeout10Minutes => '10 minut';

  @override
  String get timeout10MinutesDesc => 'Zakończ rozmowę po 10 minutach ciszy';

  @override
  String get timeout30Minutes => '30 minut';

  @override
  String get timeout30MinutesDesc => 'Zakończ rozmowę po 30 minutach ciszy';

  @override
  String get timeout4Hours => '4 godziny';

  @override
  String get timeout4HoursDesc => 'Zakończ rozmowę po 4 godzinach ciszy';

  @override
  String get conversationEndAfterHours => 'Rozmowy będą teraz kończyć się po 4 godzinach ciszy';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Rozmowy będą teraz kończyć się po $minutes minutach ciszy';
  }

  @override
  String get tellUsPrimaryLanguage => 'Podaj nam swój język podstawowy';

  @override
  String get languageForTranscription =>
      'Ustaw swój język dla ostrzejszych transkrypcji i spersonalizowanego doświadczenia.';

  @override
  String get singleLanguageModeInfo =>
      'Tryb pojedynczego języka jest włączony. Tłumaczenie jest wyłączone dla większej dokładności.';

  @override
  String get searchLanguageHint => 'Szukaj języka według nazwy lub kodu';

  @override
  String get noLanguagesFound => 'Nie znaleziono języków';

  @override
  String get skip => 'Pomiń';

  @override
  String languageSetTo(String language) {
    return 'Język ustawiony na $language';
  }

  @override
  String get failedToSetLanguage => 'Nie udało się ustawić języka';

  @override
  String appSettings(String appName) {
    return 'Ustawienia $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Rozłączyć z $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Spowoduje to usunięcie uwierzytelnienia $appName. Będziesz musiał ponownie połączyć, aby użyć go ponownie.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Połączono z $appName';
  }

  @override
  String get account => 'Konto';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Twoje zadania będą synchronizowane z Twoim kontem $appName';
  }

  @override
  String get defaultSpace => 'Domyślna przestrzeń';

  @override
  String get selectSpaceInWorkspace => 'Wybierz przestrzeń w swoim obszarze roboczym';

  @override
  String get noSpacesInWorkspace => 'Nie znaleziono przestrzeni w tym obszarze roboczym';

  @override
  String get defaultList => 'Domyślna lista';

  @override
  String get tasksAddedToList => 'Zadania będą dodawane do tej listy';

  @override
  String get noListsInSpace => 'Nie znaleziono list w tej przestrzeni';

  @override
  String failedToLoadRepos(String error) {
    return 'Nie udało się załadować repozytoriów: $error';
  }

  @override
  String get defaultRepoSaved => 'Domyślne repozytorium zapisane';

  @override
  String get failedToSaveDefaultRepo => 'Nie udało się zapisać domyślnego repozytorium';

  @override
  String get defaultRepository => 'Domyślne repozytorium';

  @override
  String get selectDefaultRepoDesc =>
      'Wybierz domyślne repozytorium do tworzenia problemów. Nadal możesz określić inne repozytorium podczas tworzenia problemów.';

  @override
  String get noReposFound => 'Nie znaleziono repozytoriów';

  @override
  String get private => 'Prywatne';

  @override
  String updatedDate(String date) {
    return 'Zaktualizowano $date';
  }

  @override
  String get yesterday => 'Wczoraj';

  @override
  String daysAgo(int count) {
    return '$count dni temu';
  }

  @override
  String get oneWeekAgo => '1 tydzień temu';

  @override
  String weeksAgo(int count) {
    return '$count tygodni temu';
  }

  @override
  String get oneMonthAgo => '1 miesiąc temu';

  @override
  String monthsAgo(int count) {
    return '$count miesięcy temu';
  }

  @override
  String get issuesCreatedInRepo => 'Problemy będą tworzone w Twoim domyślnym repozytorium';

  @override
  String get taskIntegrations => 'Integracje zadań';

  @override
  String get configureSettings => 'Konfiguruj ustawienia';

  @override
  String get completeAuthBrowser => 'Ukończ uwierzytelnianie w przeglądarce. Po zakończeniu wróć do aplikacji.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Nie udało się rozpocząć uwierzytelniania $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Połącz z $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Musisz upoważnić Omi do tworzenia zadań w Twoim koncie $appName. Otworzy to przeglądarkę w celu uwierzytelnienia.';
  }

  @override
  String get continueButton => 'Kontynuuj';

  @override
  String appIntegration(String appName) {
    return 'Integracja z $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integracja z $appName wkrótce! Ciężko pracujemy, aby przynieść Ci więcej opcji zarządzania zadaniami.';
  }

  @override
  String get gotIt => 'Rozumiem';

  @override
  String get tasksExportedOneApp => 'Zadania mogą być eksportowane do jednej aplikacji naraz.';

  @override
  String get completeYourUpgrade => 'Ukończ aktualizację';

  @override
  String get importConfiguration => 'Importuj konfigurację';

  @override
  String get exportConfiguration => 'Eksportuj konfigurację';

  @override
  String get bringYourOwn => 'Przynieś własny';

  @override
  String get payYourSttProvider => 'Swobodnie korzystaj z Omi. Płacisz tylko swojemu dostawcy STT bezpośrednio.';

  @override
  String get freeMinutesMonth => '1200 darmowych minut/miesiąc w zestawie. Nieograniczone z ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host jest wymagany';

  @override
  String get validPortRequired => 'Wymagany jest prawidłowy port';

  @override
  String get validWebsocketUrlRequired => 'Wymagany jest prawidłowy adres URL WebSocket (wss://)';

  @override
  String get apiUrlRequired => 'Adres URL API jest wymagany';

  @override
  String get apiKeyRequired => 'Klucz API jest wymagany';

  @override
  String get invalidJsonConfig => 'Nieprawidłowa konfiguracja JSON';

  @override
  String errorSaving(String error) {
    return 'Błąd zapisu: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfiguracja skopiowana do schowka';

  @override
  String get pasteJsonConfig => 'Wklej swoją konfigurację JSON poniżej:';

  @override
  String get addApiKeyAfterImport => 'Musisz dodać własny klucz API po zaimportowaniu';

  @override
  String get paste => 'Wklej';

  @override
  String get import => 'Importuj';

  @override
  String get invalidProviderInConfig => 'Nieprawidłowy dostawca w konfiguracji';

  @override
  String importedConfig(String providerName) {
    return 'Zaimportowano konfigurację $providerName';
  }

  @override
  String invalidJson(String error) {
    return 'Nieprawidłowy JSON: $error';
  }

  @override
  String get provider => 'Dostawca';

  @override
  String get live => 'Na żywo';

  @override
  String get onDevice => 'Na urządzeniu';

  @override
  String get apiUrl => 'Adres URL API';

  @override
  String get enterSttHttpEndpoint => 'Wprowadź swój punkt końcowy HTTP STT';

  @override
  String get websocketUrl => 'Adres URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Wprowadź swój punkt końcowy WebSocket STT na żywo';

  @override
  String get apiKey => 'Klucz API';

  @override
  String get enterApiKey => 'Wprowadź swój klucz API';

  @override
  String get storedLocallyNeverShared => 'Przechowywane lokalnie, nigdy nie udostępniane';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Zaawansowane';

  @override
  String get configuration => 'Konfiguracja';

  @override
  String get requestConfiguration => 'Konfiguracja żądania';

  @override
  String get responseSchema => 'Schemat odpowiedzi';

  @override
  String get modified => 'Zmodyfikowano';

  @override
  String get resetRequestConfig => 'Zresetuj konfigurację żądania do domyślnej';

  @override
  String get logs => 'Logi';

  @override
  String get logsCopied => 'Logi skopiowane';

  @override
  String get noLogsYet => 'Brak logów. Rozpocznij nagrywanie, aby zobaczyć aktywność niestandardowego STT.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device używa $reason. Zostanie użyte Omi.';
  }

  @override
  String get omiTranscription => 'Transkrypcja Omi';

  @override
  String get bestInClassTranscription => 'Najlepsza w klasie transkrypcja bez konfiguracji';

  @override
  String get instantSpeakerLabels => 'Natychmiastowe etykiety mówców';

  @override
  String get languageTranslation => 'Tłumaczenie na ponad 100 języków';

  @override
  String get optimizedForConversation => 'Zoptymalizowane pod kątem rozmów';

  @override
  String get autoLanguageDetection => 'Automatyczne wykrywanie języka';

  @override
  String get highAccuracy => 'Wysoka dokładność';

  @override
  String get privacyFirst => 'Prywatność na pierwszym miejscu';

  @override
  String get saveChanges => 'Zapisz zmiany';

  @override
  String get resetToDefault => 'Przywróć domyślne';

  @override
  String get viewTemplate => 'Zobacz szablon';

  @override
  String get trySomethingLike => 'Spróbuj czegoś takiego...';

  @override
  String get tryIt => 'Wypróbuj';

  @override
  String get creatingPlan => 'Tworzenie planu';

  @override
  String get developingLogic => 'Rozwijanie logiki';

  @override
  String get designingApp => 'Projektowanie aplikacji';

  @override
  String get generatingIconStep => 'Generowanie ikony';

  @override
  String get finalTouches => 'Końcowe poprawki';

  @override
  String get processing => 'Przetwarzanie...';

  @override
  String get features => 'Funkcje';

  @override
  String get creatingYourApp => 'Tworzenie Twojej aplikacji...';

  @override
  String get generatingIcon => 'Generowanie ikony...';

  @override
  String get whatShouldWeMake => 'Co powinniśmy stworzyć?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Opis';

  @override
  String get publicLabel => 'Publiczne';

  @override
  String get privateLabel => 'Prywatne';

  @override
  String get free => 'Darmowe';

  @override
  String get perMonth => '/ miesiąc';

  @override
  String get tailoredConversationSummaries => 'Dostosowane podsumowania rozmów';

  @override
  String get customChatbotPersonality => 'Niestandardowa osobowość chatbota';

  @override
  String get makePublic => 'Upublicznij';

  @override
  String get anyoneCanDiscover => 'Każdy może odkryć Twoją aplikację';

  @override
  String get onlyYouCanUse => 'Tylko Ty możesz korzystać z tej aplikacji';

  @override
  String get paidApp => 'Płatna aplikacja';

  @override
  String get usersPayToUse => 'Użytkownicy płacą za korzystanie z Twojej aplikacji';

  @override
  String get freeForEveryone => 'Darmowa dla wszystkich';

  @override
  String get perMonthLabel => '/ miesiąc';

  @override
  String get creating => 'Tworzenie...';

  @override
  String get createApp => 'Utwórz aplikację';

  @override
  String get searchingForDevices => 'Wyszukiwanie urządzeń...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'URZĄDZEŃ',
      few: 'URZĄDZENIA',
      one: 'URZĄDZENIE',
    );
    return 'ZNALEZIONO $count $_temp0 W POBLIŻU';
  }

  @override
  String get pairingSuccessful => 'PAROWANIE UDANE';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Błąd połączenia z Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Nie pokazuj ponownie';

  @override
  String get iUnderstand => 'Rozumiem';

  @override
  String get enableBluetooth => 'Włącz Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi potrzebuje Bluetooth, aby połączyć się z Twoim urządzeniem noszonym. Włącz Bluetooth i spróbuj ponownie.';

  @override
  String get contactSupport => 'Skontaktuj się z pomocą techniczną?';

  @override
  String get connectLater => 'Połącz później';

  @override
  String get grantPermissions => 'Przyznaj uprawnienia';

  @override
  String get backgroundActivity => 'Aktywność w tle';

  @override
  String get backgroundActivityDesc => 'Pozwól Omi działać w tle dla lepszej stabilności';

  @override
  String get locationAccess => 'Dostęp do lokalizacji';

  @override
  String get locationAccessDesc => 'Włącz lokalizację w tle dla pełnego doświadczenia';

  @override
  String get notifications => 'Powiadomienia';

  @override
  String get notificationsDesc => 'Włącz powiadomienia, aby być na bieżąco';

  @override
  String get locationServiceDisabled => 'Usługa lokalizacji wyłączona';

  @override
  String get locationServiceDisabledDesc =>
      'Usługa lokalizacji jest wyłączona. Przejdź do Ustawienia > Prywatność i bezpieczeństwo > Usługi lokalizacji i włącz ją';

  @override
  String get backgroundLocationDenied => 'Odmowa dostępu do lokalizacji w tle';

  @override
  String get backgroundLocationDeniedDesc =>
      'Przejdź do ustawień urządzenia i ustaw uprawnienie lokalizacji na \"Zawsze zezwalaj\"';

  @override
  String get lovingOmi => 'Podoba Ci się Omi?';

  @override
  String get leaveReviewIos =>
      'Pomóż nam dotrzeć do większej liczby osób, zostawiając recenzję w App Store. Twoja opinia wiele dla nas znaczy!';

  @override
  String get leaveReviewAndroid =>
      'Pomóż nam dotrzeć do większej liczby osób, zostawiając recenzję w Google Play Store. Twoja opinia wiele dla nas znaczy!';

  @override
  String get rateOnAppStore => 'Oceń w App Store';

  @override
  String get rateOnGooglePlay => 'Oceń w Google Play';

  @override
  String get maybeLater => 'Może później';

  @override
  String get speechProfileIntro => 'Omi musi poznać Twoje cele i Twój głos. Będziesz mógł to później zmienić.';

  @override
  String get getStarted => 'Rozpocznij';

  @override
  String get allDone => 'Wszystko gotowe!';

  @override
  String get keepGoing => 'Dalej tak trzymaj, świetnie Ci idzie';

  @override
  String get skipThisQuestion => 'Pomiń to pytanie';

  @override
  String get skipForNow => 'Pomiń na razie';

  @override
  String get connectionError => 'Błąd połączenia';

  @override
  String get connectionErrorDesc =>
      'Nie udało się połączyć z serwerem. Sprawdź połączenie internetowe i spróbuj ponownie.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Wykryto nieprawidłowe nagranie';

  @override
  String get multipleSpeakersDesc =>
      'Wygląda na to, że w nagraniu jest wielu mówców. Upewnij się, że jesteś w cichym miejscu i spróbuj ponownie.';

  @override
  String get tooShortDesc => 'Nie wykryto wystarczającej ilości mowy. Mów więcej i spróbuj ponownie.';

  @override
  String get invalidRecordingDesc => 'Upewnij się, że mówisz przez co najmniej 5 sekund i nie więcej niż 90.';

  @override
  String get areYouThere => 'Jesteś tam?';

  @override
  String get noSpeechDesc =>
      'Nie udało się wykryć żadnej mowy. Upewnij się, że mówisz przez co najmniej 10 sekund i nie więcej niż 3 minuty.';

  @override
  String get connectionLost => 'Utracono połączenie';

  @override
  String get connectionLostDesc => 'Połączenie zostało przerwane. Sprawdź połączenie internetowe i spróbuj ponownie.';

  @override
  String get tryAgain => 'Spróbuj ponownie';

  @override
  String get connectOmiOmiGlass => 'Połącz Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Kontynuuj bez urządzenia';

  @override
  String get permissionsRequired => 'Wymagane uprawnienia';

  @override
  String get permissionsRequiredDesc =>
      'Ta aplikacja wymaga uprawnień Bluetooth i lokalizacji, aby działać prawidłowo. Włącz je w ustawieniach.';

  @override
  String get openSettings => 'Otwórz ustawienia';

  @override
  String get wantDifferentName => 'Chcesz być nazywany inaczej?';

  @override
  String get whatsYourName => 'Jak masz na imię?';

  @override
  String get speakTranscribeSummarize => 'Mów. Transkrybuj. Podsumuj.';

  @override
  String get signInWithApple => 'Zaloguj się przez Apple';

  @override
  String get signInWithGoogle => 'Zaloguj się przez Google';

  @override
  String get byContinuingAgree => 'Kontynuując, zgadzasz się z naszą ';

  @override
  String get termsOfUse => 'Warunkami korzystania';

  @override
  String get omiYourAiCompanion => 'Omi – Twój kompan AI';

  @override
  String get captureEveryMoment =>
      'Uchwycaj każdą chwilę. Otrzymuj podsumowania\nnapędzane przez AI. Nigdy więcej nie rób notatek.';

  @override
  String get appleWatchSetup => 'Konfiguracja Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Zażądano uprawnień!';

  @override
  String get microphonePermission => 'Uprawnienie mikrofonu';

  @override
  String get permissionGrantedNow =>
      'Uprawnienie przyznane! Teraz:\n\nOtwórz aplikację Omi na zegarku i dotknij \"Kontynuuj\" poniżej';

  @override
  String get needMicrophonePermission =>
      'Potrzebujemy uprawnienia do mikrofonu.\n\n1. Dotknij \"Przyznaj uprawnienie\"\n2. Zezwól na iPhone\n3. Aplikacja na zegarku zostanie zamknięta\n4. Otwórz ponownie i dotknij \"Kontynuuj\"';

  @override
  String get grantPermissionButton => 'Przyznaj uprawnienie';

  @override
  String get needHelp => 'Potrzebujesz pomocy?';

  @override
  String get troubleshootingSteps =>
      'Rozwiązywanie problemów:\n\n1. Upewnij się, że Omi jest zainstalowane na Twoim zegarku\n2. Otwórz aplikację Omi na zegarku\n3. Poszukaj okna z prośbą o uprawnienie\n4. Dotknij \"Zezwól\" po wyświetleniu monitu\n5. Aplikacja na zegarku zostanie zamknięta - otwórz ją ponownie\n6. Wróć i dotknij \"Kontynuuj\" na iPhone';

  @override
  String get recordingStartedSuccessfully => 'Nagrywanie rozpoczęte pomyślnie!';

  @override
  String get permissionNotGrantedYet =>
      'Uprawnienie nie zostało jeszcze przyznane. Upewnij się, że zezwoliłeś na dostęp do mikrofonu i ponownie otworzyłeś aplikację na zegarku.';

  @override
  String errorRequestingPermission(String error) {
    return 'Błąd żądania uprawnień: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Błąd rozpoczęcia nagrywania: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Wybierz swój język podstawowy';

  @override
  String get languageBenefits => 'Ustaw swój język dla ostrzejszych transkrypcji i spersonalizowanego doświadczenia';

  @override
  String get whatsYourPrimaryLanguage => 'Jaki jest Twój język podstawowy?';

  @override
  String get selectYourLanguage => 'Wybierz swój język';

  @override
  String get personalGrowthJourney => 'Twoja podróż rozwoju osobistego z AI, które słucha każdego twojego słowa.';

  @override
  String get actionItemsTitle => 'Zadania';

  @override
  String get actionItemsDescription => 'Dotknij, aby edytować • Przytrzymaj, aby wybrać • Przesuń, aby wykonać akcje';

  @override
  String get tabToDo => 'Do zrobienia';

  @override
  String get tabDone => 'Zrobione';

  @override
  String get tabOld => 'Stare';

  @override
  String get emptyTodoMessage => '🎉 Wszystko na bieżąco!\nBrak oczekujących zadań';

  @override
  String get emptyDoneMessage => 'Brak ukończonych zadań';

  @override
  String get emptyOldMessage => '✅ Brak starych zadań';

  @override
  String get noItems => 'Brak elementów';

  @override
  String get actionItemMarkedIncomplete => 'Zadanie oznaczone jako nieukończone';

  @override
  String get actionItemCompleted => 'Zadanie ukończone';

  @override
  String get deleteActionItemTitle => 'Usuń element działania';

  @override
  String get deleteActionItemMessage => 'Czy na pewno chcesz usunąć ten element działania?';

  @override
  String get deleteSelectedItemsTitle => 'Usuń wybrane elementy';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Czy na pewno chcesz usunąć $count wybrane zadani$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Zadanie \"$description\" usunięte';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return 'Usunięto $count zadani$s';
  }

  @override
  String get failedToDeleteItem => 'Nie udało się usunąć zadania';

  @override
  String get failedToDeleteItems => 'Nie udało się usunąć zadań';

  @override
  String get failedToDeleteSomeItems => 'Nie udało się usunąć niektórych zadań';

  @override
  String get welcomeActionItemsTitle => 'Gotowe na zadania';

  @override
  String get welcomeActionItemsDescription =>
      'Twoje AI automatycznie wyodrębni zadania z Twoich rozmów. Pojawią się tutaj, gdy zostaną utworzone.';

  @override
  String get autoExtractionFeature => 'Automatycznie wyodrębniane z rozmów';

  @override
  String get editSwipeFeature => 'Dotknij, aby edytować, przesuń, aby ukończyć lub usunąć';

  @override
  String itemsSelected(int count) {
    return 'Wybrano: $count';
  }

  @override
  String get selectAll => 'Zaznacz wszystko';

  @override
  String get deleteSelected => 'Usuń zaznaczone';

  @override
  String get searchMemories => 'Szukaj wspomnień...';

  @override
  String get memoryDeleted => 'Wspomnienie usunięte.';

  @override
  String get undo => 'Cofnij';

  @override
  String get noMemoriesYet => '🧠 Brak wspomnień';

  @override
  String get noAutoMemories => 'Brak automatycznie wyodrębnionych wspomnień';

  @override
  String get noManualMemories => 'Brak ręcznych wspomnień';

  @override
  String get noMemoriesInCategories => 'Brak wspomnień w tych kategoriach';

  @override
  String get noMemoriesFound => '🔍 Nie znaleziono wspomnień';

  @override
  String get addFirstMemory => 'Dodaj swoje pierwsze wspomnienie';

  @override
  String get clearMemoryTitle => 'Wyczyść pamięć Omi';

  @override
  String get clearMemoryMessage => 'Czy na pewno chcesz wyczyścić pamięć Omi? Tej czynności nie można cofnąć.';

  @override
  String get clearMemoryButton => 'Wyczyść pamięć';

  @override
  String get memoryClearedSuccess => 'Pamięć Omi o Tobie została wyczyszczona';

  @override
  String get noMemoriesToDelete => 'Brak wspomnień do usunięcia';

  @override
  String get createMemoryTooltip => 'Utwórz nowe wspomnienie';

  @override
  String get createActionItemTooltip => 'Utwórz nowe zadanie';

  @override
  String get memoryManagement => 'Zarządzanie pamięcią';

  @override
  String get filterMemories => 'Filtruj wspomnienia';

  @override
  String totalMemoriesCount(int count) {
    return 'Masz $count wspomnień łącznie';
  }

  @override
  String get publicMemories => 'Publiczne wspomnienia';

  @override
  String get privateMemories => 'Prywatne wspomnienia';

  @override
  String get makeAllPrivate => 'Ustaw wszystkie wspomnienia jako prywatne';

  @override
  String get makeAllPublic => 'Ustaw wszystkie wspomnienia jako publiczne';

  @override
  String get deleteAllMemories => 'Usuń wszystkie wspomnienia';

  @override
  String get allMemoriesPrivateResult => 'Wszystkie wspomnienia są teraz prywatne';

  @override
  String get allMemoriesPublicResult => 'Wszystkie wspomnienia są teraz publiczne';

  @override
  String get newMemory => '✨ Nowe wspomnienie';

  @override
  String get editMemory => '✏️ Edytuj wspomnienie';

  @override
  String get memoryContentHint => 'Lubię jeść lody...';

  @override
  String get failedToSaveMemory => 'Nie udało się zapisać. Sprawdź połączenie.';

  @override
  String get saveMemory => 'Zapisz wspomnienie';

  @override
  String get retry => 'Ponów';

  @override
  String get createActionItem => 'Utwórz zadanie';

  @override
  String get editActionItem => 'Edytuj zadanie';

  @override
  String get actionItemDescriptionHint => 'Co trzeba zrobić?';

  @override
  String get actionItemDescriptionEmpty => 'Opis zadania nie może być pusty.';

  @override
  String get actionItemUpdated => 'Zadanie zaktualizowane';

  @override
  String get failedToUpdateActionItem => 'Nie udało się zaktualizować zadania';

  @override
  String get actionItemCreated => 'Zadanie utworzone';

  @override
  String get failedToCreateActionItem => 'Nie udało się utworzyć zadania';

  @override
  String get dueDate => 'Termin';

  @override
  String get time => 'Czas';

  @override
  String get addDueDate => 'Dodaj termin';

  @override
  String get pressDoneToSave => 'Naciśnij Gotowe, aby zapisać';

  @override
  String get pressDoneToCreate => 'Naciśnij Gotowe, aby utworzyć';

  @override
  String get filterAll => 'Wszystkie';

  @override
  String get filterSystem => 'O Tobie';

  @override
  String get filterInteresting => 'Spostrzeżenia';

  @override
  String get filterManual => 'Ręczne';

  @override
  String get completed => 'Ukończone';

  @override
  String get markComplete => 'Oznacz jako ukończone';

  @override
  String get actionItemDeleted => 'Element działania usunięty';

  @override
  String get failedToDeleteActionItem => 'Nie udało się usunąć zadania';

  @override
  String get deleteActionItemConfirmTitle => 'Usuń zadanie';

  @override
  String get deleteActionItemConfirmMessage => 'Czy na pewno chcesz usunąć to zadanie?';

  @override
  String get appLanguage => 'Język aplikacji';

  @override
  String get appInterfaceSectionTitle => 'INTERFEJS APLIKACJI';

  @override
  String get speechTranscriptionSectionTitle => 'MOWA I TRANSKRYPCJA';

  @override
  String get languageSettingsHelperText =>
      'Język aplikacji zmienia menu i przyciski. Język mowy wpływa na sposób transkrypcji nagrań.';

  @override
  String get translationNotice => 'Powiadomienie o tłumaczeniu';

  @override
  String get translationNoticeMessage =>
      'Omi tłumaczy rozmowy na Twój główny język. Zaktualizuj to w dowolnym momencie w Ustawienia → Profile.';

  @override
  String get pleaseCheckInternetConnection => 'Sprawdź połączenie internetowe i spróbuj ponownie';

  @override
  String get pleaseSelectReason => 'Wybierz przyczynę';

  @override
  String get tellUsMoreWhatWentWrong => 'Powiedz nam więcej o tym, co poszło nie tak...';

  @override
  String get selectText => 'Wybierz tekst';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksymalnie $count celów dozwolonych';
  }

  @override
  String get conversationCannotBeMerged => 'Ta rozmowa nie może zostać scalona (zablokowana lub już scalana)';

  @override
  String get pleaseEnterFolderName => 'Wprowadź nazwę folderu';

  @override
  String get failedToCreateFolder => 'Nie udało się utworzyć folderu';

  @override
  String get failedToUpdateFolder => 'Nie udało się zaktualizować folderu';

  @override
  String get folderName => 'Nazwa folderu';

  @override
  String get descriptionOptional => 'Opis (opcjonalny)';

  @override
  String get failedToDeleteFolder => 'Nie udało się usunąć folderu';

  @override
  String get editFolder => 'Edytuj folder';

  @override
  String get deleteFolder => 'Usuń folder';

  @override
  String get transcriptCopiedToClipboard => 'Transkrypcja skopiowana do schowka';

  @override
  String get summaryCopiedToClipboard => 'Podsumowanie skopiowane do schowka';

  @override
  String get conversationUrlCouldNotBeShared => 'Nie udało się udostępnić URL rozmowy.';

  @override
  String get urlCopiedToClipboard => 'URL skopiowany do schowka';

  @override
  String get exportTranscript => 'Eksportuj transkrypcję';

  @override
  String get exportSummary => 'Eksportuj podsumowanie';

  @override
  String get exportButton => 'Eksportuj';

  @override
  String get actionItemsCopiedToClipboard => 'Elementy działań skopiowane do schowka';

  @override
  String get summarize => 'Podsumuj';

  @override
  String get generateSummary => 'Generuj podsumowanie';

  @override
  String get conversationNotFoundOrDeleted => 'Rozmowa nie została znaleziona lub została usunięta';

  @override
  String get deleteMemory => 'Usuń wspomnienie';

  @override
  String get thisActionCannotBeUndone => 'Ta czynność nie może być cofnięta.';

  @override
  String memoriesCount(int count) {
    return '$count wspomnień';
  }

  @override
  String get noMemoriesInCategory => 'Brak wspomnień w tej kategorii';

  @override
  String get addYourFirstMemory => 'Dodaj swoje pierwsze wspomnienie';

  @override
  String get firmwareDisconnectUsb => 'Odłącz USB';

  @override
  String get firmwareUsbWarning => 'Połączenie USB podczas aktualizacji może uszkodzić urządzenie.';

  @override
  String get firmwareBatteryAbove15 => 'Bateria powyżej 15%';

  @override
  String get firmwareEnsureBattery => 'Upewnij się, że urządzenie ma 15% baterii.';

  @override
  String get firmwareStableConnection => 'Stabilne połączenie';

  @override
  String get firmwareConnectWifi => 'Połącz się z WiFi lub siecią komórkową.';

  @override
  String failedToStartUpdate(String error) {
    return 'Nie udało się rozpocząć aktualizacji: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Przed aktualizacją upewnij się:';

  @override
  String get confirmed => 'Potwierdzone!';

  @override
  String get release => 'Zwolnij';

  @override
  String get slideToUpdate => 'Przesuń, aby zaktualizować';

  @override
  String copiedToClipboard(String title) {
    return '$title skopiowano do schowka';
  }

  @override
  String get batteryLevel => 'Poziom baterii';

  @override
  String get productUpdate => 'Aktualizacja produktu';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Dostępne';

  @override
  String get unpairDeviceDialogTitle => 'Rozłącz urządzenie';

  @override
  String get unpairDeviceDialogMessage =>
      'To rozłączy urządzenie, aby mogło zostać połączone z innym telefonem. Będziesz musiał przejść do Ustawienia > Bluetooth i zapomnieć urządzenie, aby zakończyć proces.';

  @override
  String get unpair => 'Rozłącz';

  @override
  String get unpairAndForgetDevice => 'Rozłącz i zapomnij urządzenie';

  @override
  String get unknownDevice => 'Nieznane';

  @override
  String get unknown => 'Nieznane';

  @override
  String get productName => 'Nazwa produktu';

  @override
  String get serialNumber => 'Numer seryjny';

  @override
  String get connected => 'Połączono';

  @override
  String get privacyPolicyTitle => 'Polityka prywatności';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label skopiowano';
  }

  @override
  String get noApiKeysYet => 'Brak kluczy API. Utwórz jeden, aby zintegrować z aplikacją.';

  @override
  String get createKeyToGetStarted => 'Utwórz klucz, aby rozpocząć';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Skonfiguruj swoją osobowość AI';

  @override
  String get configureSttProvider => 'Skonfiguruj dostawcę STT';

  @override
  String get setWhenConversationsAutoEnd => 'Ustaw, kiedy rozmowy kończą się automatycznie';

  @override
  String get importDataFromOtherSources => 'Importuj dane z innych źródeł';

  @override
  String get debugAndDiagnostics => 'Debugowanie i diagnostyka';

  @override
  String get autoDeletesAfter3Days => 'Automatyczne usuwanie po 3 dniach';

  @override
  String get helpsDiagnoseIssues => 'Pomaga diagnozować problemy';

  @override
  String get exportStartedMessage => 'Eksport rozpoczęty. Może to potrwać kilka sekund...';

  @override
  String get exportConversationsToJson => 'Eksportuj rozmowy do pliku JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Graf wiedzy został pomyślnie usunięty';

  @override
  String failedToDeleteGraph(String error) {
    return 'Nie udało się usunąć grafu: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Wyczyść wszystkie węzły i połączenia';

  @override
  String get addToClaudeDesktopConfig => 'Dodaj do claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Połącz asystentów AI z danymi';

  @override
  String get useYourMcpApiKey => 'Użyj swojego klucza API MCP';

  @override
  String get realTimeTranscript => 'Transkrypcja w czasie rzeczywistym';

  @override
  String get experimental => 'Eksperymentalne';

  @override
  String get transcriptionDiagnostics => 'Diagnostyka transkrypcji';

  @override
  String get detailedDiagnosticMessages => 'Szczegółowe komunikaty diagnostyczne';

  @override
  String get autoCreateSpeakers => 'Automatycznie twórz mówców';

  @override
  String get autoCreateWhenNameDetected => 'Automatycznie twórz po wykryciu nazwy';

  @override
  String get followUpQuestions => 'Pytania uzupełniające';

  @override
  String get suggestQuestionsAfterConversations => 'Sugeruj pytania po rozmowach';

  @override
  String get goalTracker => 'Śledzenie celów';

  @override
  String get trackPersonalGoalsOnHomepage => 'Śledź swoje osobiste cele na stronie głównej';

  @override
  String get dailyReflection => 'Codzienna refleksja';

  @override
  String get get9PmReminderToReflect => 'Otrzymuj przypomnienie o 21:00, aby przemyśleć swój dzień';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Opis elementu działania nie może być pusty';

  @override
  String get saved => 'Zapisano';

  @override
  String get overdue => 'Zaległe';

  @override
  String get failedToUpdateDueDate => 'Nie udało się zaktualizować terminu';

  @override
  String get markIncomplete => 'Oznacz jako nieukończone';

  @override
  String get editDueDate => 'Edytuj termin';

  @override
  String get setDueDate => 'Ustaw termin';

  @override
  String get clearDueDate => 'Wyczyść termin';

  @override
  String get failedToClearDueDate => 'Nie udało się wyczyścić terminu';

  @override
  String get mondayAbbr => 'Pon';

  @override
  String get tuesdayAbbr => 'Wt';

  @override
  String get wednesdayAbbr => 'Śr';

  @override
  String get thursdayAbbr => 'Czw';

  @override
  String get fridayAbbr => 'Pt';

  @override
  String get saturdayAbbr => 'Sob';

  @override
  String get sundayAbbr => 'Niedz';

  @override
  String get howDoesItWork => 'Jak to działa?';

  @override
  String get sdCardSyncDescription => 'Synchronizacja karty SD zaimportuje twoje wspomnienia z karty SD do aplikacji';

  @override
  String get checksForAudioFiles => 'Sprawdza pliki audio na karcie SD';

  @override
  String get omiSyncsAudioFiles => 'Omi następnie synchronizuje pliki audio z serwerem';

  @override
  String get serverProcessesAudio => 'Serwer przetwarza pliki audio i tworzy wspomnienia';

  @override
  String get youreAllSet => 'Gotowe!';

  @override
  String get welcomeToOmiDescription =>
      'Witamy w Omi! Twój towarzysz AI jest gotowy, aby pomóc ci w rozmowach, zadaniach i nie tylko.';

  @override
  String get startUsingOmi => 'Zacznij korzystać z Omi';

  @override
  String get back => 'Wstecz';

  @override
  String get keyboardShortcuts => 'Skróty Klawiszowe';

  @override
  String get toggleControlBar => 'Przełącz pasek sterowania';

  @override
  String get pressKeys => 'Naciśnij klawisze...';

  @override
  String get cmdRequired => '⌘ wymagane';

  @override
  String get invalidKey => 'Nieprawidłowy klawisz';

  @override
  String get space => 'Spacja';

  @override
  String get search => 'Szukaj';

  @override
  String get searchPlaceholder => 'Szukaj...';

  @override
  String get untitledConversation => 'Rozmowa bez tytułu';

  @override
  String countRemaining(String count) {
    return '$count pozostało';
  }

  @override
  String get addGoal => 'Dodaj cel';

  @override
  String get editGoal => 'Edytuj cel';

  @override
  String get icon => 'Ikona';

  @override
  String get goalTitle => 'Tytuł celu';

  @override
  String get current => 'Obecny';

  @override
  String get target => 'Cel';

  @override
  String get saveGoal => 'Zapisz';

  @override
  String get goals => 'Cele';

  @override
  String get tapToAddGoal => 'Stuknij, aby dodać cel';

  @override
  String welcomeBack(String name) {
    return 'Witaj ponownie, $name';
  }

  @override
  String get yourConversations => 'Twoje rozmowy';

  @override
  String get reviewAndManageConversations => 'Przeglądaj i zarządzaj zapisanymi rozmowami';

  @override
  String get startCapturingConversations =>
      'Zacznij przechwytywać rozmowy za pomocą urządzenia Omi, aby je tutaj zobaczyć.';

  @override
  String get useMobileAppToCapture => 'Użyj aplikacji mobilnej, aby nagrać dźwięk';

  @override
  String get conversationsProcessedAutomatically => 'Rozmowy są przetwarzane automatycznie';

  @override
  String get getInsightsInstantly => 'Uzyskaj natychmiastowe spostrzeżenia i podsumowania';

  @override
  String get showAll => 'Pokaż wszystko →';

  @override
  String get noTasksForToday => 'Brak zadań na dziś.\\nZapytaj Omi o więcej zadań lub utwórz je ręcznie.';

  @override
  String get dailyScore => 'DZIENNY WYNIK';

  @override
  String get dailyScoreDescription => 'Wynik, który pomoże Ci lepiej\nskupić się na realizacji.';

  @override
  String get searchResults => 'Wyniki wyszukiwania';

  @override
  String get actionItems => 'Elementy do działania';

  @override
  String get tasksToday => 'Dzisiaj';

  @override
  String get tasksTomorrow => 'Jutro';

  @override
  String get tasksNoDeadline => 'Bez terminu';

  @override
  String get tasksLater => 'Później';

  @override
  String get loadingTasks => 'Ładowanie zadań...';

  @override
  String get tasks => 'Zadania';

  @override
  String get swipeTasksToIndent => 'Przesuń zadania, aby wcięcia, przeciągnij między kategoriami';

  @override
  String get create => 'Utwórz';

  @override
  String get noTasksYet => 'Jeszcze nie ma zadań';

  @override
  String get tasksFromConversationsWillAppear =>
      'Zadania z Twoich rozmów pojawią się tutaj.\nKliknij Utwórz, aby dodać jedno ręcznie.';

  @override
  String get monthJan => 'Sty';

  @override
  String get monthFeb => 'Lut';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Kwi';

  @override
  String get monthMay => 'Maj';

  @override
  String get monthJun => 'Cze';

  @override
  String get monthJul => 'Lip';

  @override
  String get monthAug => 'Sie';

  @override
  String get monthSep => 'Wrz';

  @override
  String get monthOct => 'Paź';

  @override
  String get monthNov => 'Lis';

  @override
  String get monthDec => 'Gru';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Zadanie zaktualizowane pomyślnie';

  @override
  String get actionItemCreatedSuccessfully => 'Zadanie utworzone pomyślnie';

  @override
  String get actionItemDeletedSuccessfully => 'Zadanie usunięte pomyślnie';

  @override
  String get deleteActionItem => 'Usuń zadanie';

  @override
  String get deleteActionItemConfirmation => 'Czy na pewno chcesz usunąć to zadanie? Tej operacji nie można cofnąć.';

  @override
  String get enterActionItemDescription => 'Wprowadź opis zadania...';

  @override
  String get markAsCompleted => 'Oznacz jako ukończone';

  @override
  String get setDueDateAndTime => 'Ustaw termin i godzinę';

  @override
  String get reloadingApps => 'Ponowne ładowanie aplikacji...';

  @override
  String get loadingApps => 'Ładowanie aplikacji...';

  @override
  String get browseInstallCreateApps => 'Przeglądaj, instaluj i twórz aplikacje';

  @override
  String get all => 'All';

  @override
  String get open => 'Otwórz';

  @override
  String get install => 'Zainstaluj';

  @override
  String get noAppsAvailable => 'Brak dostępnych aplikacji';

  @override
  String get unableToLoadApps => 'Nie można załadować aplikacji';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Spróbuj dostosować wyszukiwane hasła lub filtry';

  @override
  String get checkBackLaterForNewApps => 'Sprawdź później, czy są nowe aplikacje';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Sprawdź połączenie internetowe i spróbuj ponownie';

  @override
  String get createNewApp => 'Utwórz nową aplikację';

  @override
  String get buildSubmitCustomOmiApp => 'Zbuduj i prześlij swoją niestandardową aplikację Omi';

  @override
  String get submittingYourApp => 'Przesyłanie aplikacji...';

  @override
  String get preparingFormForYou => 'Przygotowywanie formularza...';

  @override
  String get appDetails => 'Szczegóły aplikacji';

  @override
  String get paymentDetails => 'Szczegóły płatności';

  @override
  String get previewAndScreenshots => 'Podgląd i zrzuty ekranu';

  @override
  String get appCapabilities => 'Możliwości aplikacji';

  @override
  String get aiPrompts => 'Podpowiedzi AI';

  @override
  String get chatPrompt => 'Podpowiedź czatu';

  @override
  String get chatPromptPlaceholder =>
      'Jesteś wspaniałą aplikacją, Twoim zadaniem jest odpowiadanie na zapytania użytkowników i sprawianie, by czuli się dobrze...';

  @override
  String get conversationPrompt => 'Podpowiedź konwersacji';

  @override
  String get conversationPromptPlaceholder =>
      'Jesteś wspaniałą aplikacją, otrzymasz transkrypcję i podsumowanie rozmowy...';

  @override
  String get notificationScopes => 'Zakresy powiadomień';

  @override
  String get appPrivacyAndTerms => 'Prywatność i warunki aplikacji';

  @override
  String get makeMyAppPublic => 'Upublicznij moją aplikację';

  @override
  String get submitAppTermsAgreement =>
      'Przesyłając tę aplikację, akceptuję Warunki korzystania z usługi i Politykę prywatności Omi AI';

  @override
  String get submitApp => 'Prześlij aplikację';

  @override
  String get needHelpGettingStarted => 'Potrzebujesz pomocy na start?';

  @override
  String get clickHereForAppBuildingGuides =>
      'Kliknij tutaj, aby uzyskać przewodniki tworzenia aplikacji i dokumentację';

  @override
  String get submitAppQuestion => 'Przesłać aplikację?';

  @override
  String get submitAppPublicDescription =>
      'Twoja aplikacja zostanie sprawdzona i upubliczniona. Możesz zacząć z niej korzystać natychmiast, nawet podczas sprawdzania!';

  @override
  String get submitAppPrivateDescription =>
      'Twoja aplikacja zostanie sprawdzona i udostępniona Tobie prywatnie. Możesz zacząć z niej korzystać natychmiast, nawet podczas sprawdzania!';

  @override
  String get startEarning => 'Zacznij zarabiać! 💰';

  @override
  String get connectStripeOrPayPal => 'Połącz Stripe lub PayPal, aby otrzymywać płatności za swoją aplikację.';

  @override
  String get connectNow => 'Połącz teraz';

  @override
  String get installsCount => 'Instalacje';

  @override
  String get uninstallApp => 'Odinstaluj aplikację';

  @override
  String get subscribe => 'Subskrybuj';

  @override
  String get dataAccessNotice => 'Powiadomienie o dostępie do danych';

  @override
  String get dataAccessWarning =>
      'Ta aplikacja będzie miała dostęp do Twoich danych. Omi AI nie ponosi odpowiedzialności za sposób, w jaki Twoje dane są wykorzystywane, modyfikowane lub usuwane przez tę aplikację';

  @override
  String get installApp => 'Zainstaluj aplikację';

  @override
  String get betaTesterNotice =>
      'Jesteś testerem beta tej aplikacji. Nie jest jeszcze publiczna. Stanie się publiczna po zatwierdzeniu.';

  @override
  String get appUnderReviewOwner =>
      'Twoja aplikacja jest w trakcie przeglądu i widoczna tylko dla Ciebie. Stanie się publiczna po zatwierdzeniu.';

  @override
  String get appRejectedNotice =>
      'Twoja aplikacja została odrzucona. Zaktualizuj szczegóły aplikacji i prześlij ją ponownie do przeglądu.';

  @override
  String get setupSteps => 'Kroki konfiguracji';

  @override
  String get setupInstructions => 'Instrukcje konfiguracji';

  @override
  String get integrationInstructions => 'Instrukcje integracji';

  @override
  String get preview => 'Podgląd';

  @override
  String get aboutTheApp => 'O aplikacji';

  @override
  String get aboutThePersona => 'O personie';

  @override
  String get chatPersonality => 'Osobowość czatu';

  @override
  String get ratingsAndReviews => 'Oceny i recenzje';

  @override
  String get noRatings => 'brak ocen';

  @override
  String ratingsCount(String count) {
    return '$count+ ocen';
  }

  @override
  String get errorActivatingApp => 'Błąd aktywacji aplikacji';

  @override
  String get integrationSetupRequired =>
      'Jeśli to aplikacja integracyjna, upewnij się, że konfiguracja jest zakończona.';

  @override
  String get installed => 'Zainstalowano';

  @override
  String get appIdLabel => 'ID aplikacji';

  @override
  String get appNameLabel => 'Nazwa aplikacji';

  @override
  String get appNamePlaceholder => 'Moja wspaniała aplikacja';

  @override
  String get pleaseEnterAppName => 'Proszę wprowadzić nazwę aplikacji';

  @override
  String get categoryLabel => 'Kategoria';

  @override
  String get selectCategory => 'Wybierz kategorię';

  @override
  String get descriptionLabel => 'Opis';

  @override
  String get appDescriptionPlaceholder =>
      'Moja wspaniała aplikacja to świetna aplikacja, która robi niesamowite rzeczy. To najlepsza aplikacja!';

  @override
  String get pleaseProvideValidDescription => 'Proszę podać prawidłowy opis';

  @override
  String get appPricingLabel => 'Ceny aplikacji';

  @override
  String get noneSelected => 'Nie wybrano';

  @override
  String get appIdCopiedToClipboard => 'ID aplikacji skopiowane do schowka';

  @override
  String get appCategoryModalTitle => 'Kategoria aplikacji';

  @override
  String get pricingFree => 'Bezpłatna';

  @override
  String get pricingPaid => 'Płatna';

  @override
  String get loadingCapabilities => 'Ładowanie funkcji...';

  @override
  String get filterInstalled => 'Zainstalowane';

  @override
  String get filterMyApps => 'Moje aplikacje';

  @override
  String get clearSelection => 'Wyczyść wybór';

  @override
  String get filterCategory => 'Kategoria';

  @override
  String get rating4PlusStars => '4+ gwiazdki';

  @override
  String get rating3PlusStars => '3+ gwiazdki';

  @override
  String get rating2PlusStars => '2+ gwiazdki';

  @override
  String get rating1PlusStars => '1+ gwiazdka';

  @override
  String get filterRating => 'Ocena';

  @override
  String get filterCapabilities => 'Funkcje';

  @override
  String get noNotificationScopesAvailable => 'Brak dostępnych zakresów powiadomień';

  @override
  String get popularApps => 'Popularne aplikacje';

  @override
  String get pleaseProvidePrompt => 'Proszę podać monit';

  @override
  String chatWithAppName(String appName) {
    return 'Czat z $appName';
  }

  @override
  String get defaultAiAssistant => 'Domyślny asystent AI';

  @override
  String get readyToChat => '✨ Gotowy do czatu!';

  @override
  String get connectionNeeded => '🌐 Wymagane połączenie';

  @override
  String get startConversation => 'Rozpocznij rozmowę i pozwól magii się zacząć';

  @override
  String get checkInternetConnection => 'Sprawdź połączenie internetowe';

  @override
  String get wasThisHelpful => 'Czy to było pomocne?';

  @override
  String get thankYouForFeedback => 'Dziękujemy za opinię!';

  @override
  String get maxFilesUploadError => 'Możesz przesłać tylko 4 pliki na raz';

  @override
  String get attachedFiles => '📎 Załączone pliki';

  @override
  String get takePhoto => 'Zrób zdjęcie';

  @override
  String get captureWithCamera => 'Przechwyć aparatem';

  @override
  String get selectImages => 'Wybierz obrazy';

  @override
  String get chooseFromGallery => 'Wybierz z galerii';

  @override
  String get selectFile => 'Wybierz plik';

  @override
  String get chooseAnyFileType => 'Wybierz dowolny typ pliku';

  @override
  String get cannotReportOwnMessages => 'Nie możesz zgłaszać własnych wiadomości';

  @override
  String get messageReportedSuccessfully => '✅ Wiadomość zgłoszona pomyślnie';

  @override
  String get confirmReportMessage => 'Czy na pewno chcesz zgłosić tę wiadomość?';

  @override
  String get selectChatAssistant => 'Wybierz asystenta czatu';

  @override
  String get enableMoreApps => 'Włącz więcej aplikacji';

  @override
  String get chatCleared => 'Czat wyczyszczony';

  @override
  String get clearChatTitle => 'Wyczyścić czat?';

  @override
  String get confirmClearChat => 'Czy na pewno chcesz wyczyścić czat? Tej akcji nie można cofnąć.';

  @override
  String get copy => 'Kopiuj';

  @override
  String get share => 'Udostępnij';

  @override
  String get report => 'Zgłoś';

  @override
  String get microphonePermissionRequired => 'Wymagane jest uprawnienie mikrofonu do nagrywania głosu.';

  @override
  String get microphonePermissionDenied =>
      'Uprawnienie mikrofonu odrzucone. Przyznaj uprawnienie w Preferencje systemowe > Prywatność i bezpieczeństwo > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Nie udało się sprawdzić uprawnienia mikrofonu: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Nie udało się przepisać dźwięku';

  @override
  String get transcribing => 'Przepisywanie...';

  @override
  String get transcriptionFailed => 'Przepisywanie nie powiodło się';

  @override
  String get discardedConversation => 'Odrzucona rozmowa';

  @override
  String get at => 'o';

  @override
  String get from => 'od';

  @override
  String get copied => 'Skopiowano!';

  @override
  String get copyLink => 'Kopiuj link';

  @override
  String get hideTranscript => 'Ukryj transkrypcję';

  @override
  String get viewTranscript => 'Zobacz transkrypcję';

  @override
  String get conversationDetails => 'Szczegóły rozmowy';

  @override
  String get transcript => 'Transkrypcja';

  @override
  String segmentsCount(int count) {
    return '$count segmentów';
  }

  @override
  String get noTranscriptAvailable => 'Brak dostępnej transkrypcji';

  @override
  String get noTranscriptMessage => 'Ta rozmowa nie ma transkrypcji.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'Adres URL rozmowy nie może być wygenerowany.';

  @override
  String get failedToGenerateConversationLink => 'Nie udało się wygenerować linku rozmowy';

  @override
  String get failedToGenerateShareLink => 'Nie udało się wygenerować linku do udostępnienia';

  @override
  String get reloadingConversations => 'Ponowne ładowanie rozmów...';

  @override
  String get user => 'Użytkownik';

  @override
  String get starred => 'Oznaczone gwiazdką';

  @override
  String get date => 'Data';

  @override
  String get noResultsFound => 'Nie znaleziono wyników';

  @override
  String get tryAdjustingSearchTerms => 'Spróbuj dostosować hasła wyszukiwania';

  @override
  String get starConversationsToFindQuickly => 'Oznacz rozmowy gwiazdką, aby szybko je znaleźć tutaj';

  @override
  String noConversationsOnDate(String date) {
    return 'Brak rozmów w dniu $date';
  }

  @override
  String get trySelectingDifferentDate => 'Spróbuj wybrać inną datę';

  @override
  String get conversations => 'Rozmowy';

  @override
  String get chat => 'Czat';

  @override
  String get actions => 'Akcje';

  @override
  String get syncAvailable => 'Synchronizacja dostępna';

  @override
  String get referAFriend => 'Poleć znajomemu';

  @override
  String get help => 'Pomoc';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Przejdź na Pro';

  @override
  String get getOmiDevice => 'Kup urządzenie Omi';

  @override
  String get wearableAiCompanion => 'Noszony towarzysz AI';

  @override
  String get loadingMemories => 'Ładowanie wspomnień...';

  @override
  String get allMemories => 'Wszystkie wspomnienia';

  @override
  String get aboutYou => 'O tobie';

  @override
  String get manual => 'Ręczne';

  @override
  String get loadingYourMemories => 'Ładowanie twoich wspomnień...';

  @override
  String get createYourFirstMemory => 'Utwórz swoje pierwsze wspomnienie, aby rozpocząć';

  @override
  String get tryAdjustingFilter => 'Spróbuj dostosować wyszukiwanie lub filtr';

  @override
  String get whatWouldYouLikeToRemember => 'Co chcesz zapamiętać?';

  @override
  String get category => 'Kategoria';

  @override
  String get public => 'Publiczne';

  @override
  String get failedToSaveCheckConnection => 'Nie udało się zapisać. Sprawdź połączenie.';

  @override
  String get createMemory => 'Utwórz wspomnienie';

  @override
  String get deleteMemoryConfirmation => 'Czy na pewno chcesz usunąć to wspomnienie? Tej czynności nie można cofnąć.';

  @override
  String get makePrivate => 'Ustaw jako prywatne';

  @override
  String get organizeAndControlMemories => 'Organizuj i kontroluj swoje wspomnienia';

  @override
  String get total => 'Razem';

  @override
  String get makeAllMemoriesPrivate => 'Ustaw wszystkie wspomnienia jako prywatne';

  @override
  String get setAllMemoriesToPrivate => 'Ustaw wszystkie wspomnienia na widoczność prywatną';

  @override
  String get makeAllMemoriesPublic => 'Ustaw wszystkie wspomnienia jako publiczne';

  @override
  String get setAllMemoriesToPublic => 'Ustaw wszystkie wspomnienia na widoczność publiczną';

  @override
  String get permanentlyRemoveAllMemories => 'Trwale usuń wszystkie wspomnienia z Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Wszystkie wspomnienia są teraz prywatne';

  @override
  String get allMemoriesAreNowPublic => 'Wszystkie wspomnienia są teraz publiczne';

  @override
  String get clearOmisMemory => 'Wyczyść pamięć Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Czy na pewno chcesz wyczyścić pamięć Omi? Tej czynności nie można cofnąć i trwale usunie wszystkie $count wspomnienia.';
  }

  @override
  String get omisMemoryCleared => 'Pamięć Omi o tobie została wyczyszczona';

  @override
  String get welcomeToOmi => 'Witamy w Omi';

  @override
  String get continueWithApple => 'Kontynuuj z Apple';

  @override
  String get continueWithGoogle => 'Kontynuuj z Google';

  @override
  String get byContinuingYouAgree => 'Kontynuując, zgadzasz się na nasze ';

  @override
  String get termsOfService => 'Warunki usługi';

  @override
  String get and => ' i ';

  @override
  String get dataAndPrivacy => 'Dane i prywatność';

  @override
  String get secureAuthViaAppleId => 'Bezpieczne uwierzytelnianie przez Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Bezpieczne uwierzytelnianie przez konto Google';

  @override
  String get whatWeCollect => 'Co zbieramy';

  @override
  String get dataCollectionMessage =>
      'Kontynuując, twoje rozmowy, nagrania i informacje osobiste będą bezpiecznie przechowywane na naszych serwerach, aby zapewnić wgląd napędzany AI i włączyć wszystkie funkcje aplikacji.';

  @override
  String get dataProtection => 'Ochrona danych';

  @override
  String get yourDataIsProtected => 'Twoje dane są chronione i regulowane przez naszą ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Wybierz swój główny język';

  @override
  String get chooseYourLanguage => 'Wybierz swój język';

  @override
  String get selectPreferredLanguageForBestExperience => 'Wybierz preferowany język dla najlepszego doświadczenia Omi';

  @override
  String get searchLanguages => 'Szukaj języków...';

  @override
  String get selectALanguage => 'Wybierz język';

  @override
  String get tryDifferentSearchTerm => 'Spróbuj innego terminu wyszukiwania';

  @override
  String get pleaseEnterYourName => 'Wprowadź swoje imię';

  @override
  String get nameMustBeAtLeast2Characters => 'Imię musi mieć co najmniej 2 znaki';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Powiedz nam, jak chciałbyś być zwracany. To pomaga spersonalizować Twoje doświadczenie Omi.';

  @override
  String charactersCount(int count) {
    return '$count znaków';
  }

  @override
  String get enableFeaturesForBestExperience => 'Włącz funkcje dla najlepszego doświadczenia Omi na swoim urządzeniu.';

  @override
  String get microphoneAccess => 'Dostęp do mikrofonu';

  @override
  String get recordAudioConversations => 'Nagrywaj rozmowy audio';

  @override
  String get microphoneAccessDescription =>
      'Omi potrzebuje dostępu do mikrofonu, aby nagrywać rozmowy i dostarczać transkrypcje.';

  @override
  String get screenRecording => 'Nagrywanie ekranu';

  @override
  String get captureSystemAudioFromMeetings => 'Przechwytuj dźwięk systemowy ze spotkań';

  @override
  String get screenRecordingDescription =>
      'Omi potrzebuje uprawnień do nagrywania ekranu, aby przechwytywać dźwięk systemowy z twoich spotkań opartych na przeglądarce.';

  @override
  String get accessibility => 'Dostępność';

  @override
  String get detectBrowserBasedMeetings => 'Wykrywaj spotkania oparte na przeglądarce';

  @override
  String get accessibilityDescription =>
      'Omi potrzebuje uprawnień dostępności, aby wykrywać, kiedy dołączasz do spotkań Zoom, Meet lub Teams w przeglądarce.';

  @override
  String get pleaseWait => 'Proszę czekać...';

  @override
  String get joinTheCommunity => 'Dołącz do społeczności!';

  @override
  String get loadingProfile => 'Ładowanie profilu...';

  @override
  String get profileSettings => 'Ustawienia profilu';

  @override
  String get noEmailSet => 'Nie ustawiono e-maila';

  @override
  String get userIdCopiedToClipboard => 'ID użytkownika skopiowane';

  @override
  String get yourInformation => 'Twoje Informacje';

  @override
  String get setYourName => 'Ustaw swoje imię';

  @override
  String get changeYourName => 'Zmień swoje imię';

  @override
  String get manageYourOmiPersona => 'Zarządzaj swoją personą Omi';

  @override
  String get voiceAndPeople => 'Głos i Ludzie';

  @override
  String get teachOmiYourVoice => 'Naucz Omi swojego głosu';

  @override
  String get tellOmiWhoSaidIt => 'Powiedz Omi, kto to powiedział 🗣️';

  @override
  String get payment => 'Płatność';

  @override
  String get addOrChangeYourPaymentMethod => 'Dodaj lub zmień metodę płatności';

  @override
  String get preferences => 'Preferencje';

  @override
  String get helpImproveOmiBySharing => 'Pomóż ulepszyć Omi, udostępniając zanonimizowane dane analityczne';

  @override
  String get deleteAccount => 'Usuń Konto';

  @override
  String get deleteYourAccountAndAllData => 'Usuń swoje konto i wszystkie dane';

  @override
  String get clearLogs => 'Wyczyść dzienniki';

  @override
  String get debugLogsCleared => 'Logi debugowania wyczyszczone';

  @override
  String get exportConversations => 'Eksportuj rozmowy';

  @override
  String get exportAllConversationsToJson => 'Eksportuj wszystkie rozmowy do pliku JSON.';

  @override
  String get conversationsExportStarted => 'Rozpoczęto eksport rozmów. To może potrwać kilka sekund, proszę czekać.';

  @override
  String get mcpDescription =>
      'Aby połączyć Omi z innymi aplikacjami w celu odczytu, wyszukiwania i zarządzania wspomnieniami i rozmowami. Utwórz klucz, aby rozpocząć.';

  @override
  String get apiKeys => 'Klucze API';

  @override
  String errorLabel(String error) {
    return 'Błąd: $error';
  }

  @override
  String get noApiKeysFound => 'Nie znaleziono kluczy API. Utwórz jeden, aby rozpocząć.';

  @override
  String get advancedSettings => 'Ustawienia zaawansowane';

  @override
  String get triggersWhenNewConversationCreated => 'Wyzwalane, gdy tworzona jest nowa rozmowa.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Wyzwalane, gdy otrzymywana jest nowa transkrypcja.';

  @override
  String get realtimeAudioBytes => 'Bajty audio w czasie rzeczywistym';

  @override
  String get triggersWhenAudioBytesReceived => 'Wyzwalane, gdy otrzymywane są bajty audio.';

  @override
  String get everyXSeconds => 'Co x sekund';

  @override
  String get triggersWhenDaySummaryGenerated => 'Wyzwalane, gdy generowane jest podsumowanie dnia.';

  @override
  String get tryLatestExperimentalFeatures => 'Wypróbuj najnowsze eksperymentalne funkcje zespołu Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Status diagnostyczny usługi transkrypcji';

  @override
  String get enableDetailedDiagnosticMessages => 'Włącz szczegółowe komunikaty diagnostyczne z usługi transkrypcji';

  @override
  String get autoCreateAndTagNewSpeakers => 'Automatycznie twórz i oznaczaj nowych mówców';

  @override
  String get automaticallyCreateNewPerson => 'Automatycznie twórz nową osobę, gdy w transkrypcji wykryto imię.';

  @override
  String get pilotFeatures => 'Funkcje pilotażowe';

  @override
  String get pilotFeaturesDescription => 'Te funkcje są testami i nie gwarantuje się wsparcia.';

  @override
  String get suggestFollowUpQuestion => 'Zaproponuj pytanie uzupełniające';

  @override
  String get saveSettings => 'Zapisz Ustawienia';

  @override
  String get syncingDeveloperSettings => 'Synchronizacja ustawień dewelopera...';

  @override
  String get summary => 'Podsumowanie';

  @override
  String get auto => 'Automatycznie';

  @override
  String get noSummaryForApp =>
      'Brak podsumowania dla tej aplikacji. Wypróbuj inną aplikację, aby uzyskać lepsze wyniki.';

  @override
  String get tryAnotherApp => 'Wypróbuj inną aplikację';

  @override
  String generatedBy(String appName) {
    return 'Wygenerowane przez $appName';
  }

  @override
  String get overview => 'Przegląd';

  @override
  String get otherAppResults => 'Wyniki innych aplikacji';

  @override
  String get unknownApp => 'Nieznana aplikacja';

  @override
  String get noSummaryAvailable => 'Brak dostępnego podsumowania';

  @override
  String get conversationNoSummaryYet => 'Ta rozmowa nie ma jeszcze podsumowania.';

  @override
  String get chooseSummarizationApp => 'Wybierz aplikację do podsumowania';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName ustawiona jako domyślna aplikacja do podsumowania';
  }

  @override
  String get letOmiChooseAutomatically => 'Pozwól Omi automatycznie wybrać najlepszą aplikację';

  @override
  String get deleteConversationConfirmation =>
      'Czy na pewno chcesz usunąć tę rozmowę? Ta operacja nie może zostać cofnięta.';

  @override
  String get conversationDeleted => 'Rozmowa usunięta';

  @override
  String get generatingLink => 'Generowanie linku...';

  @override
  String get editConversation => 'Edytuj rozmowę';

  @override
  String get conversationLinkCopiedToClipboard => 'Link rozmowy skopiowany do schowka';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transkrypcja rozmowy skopiowana do schowka';

  @override
  String get editConversationDialogTitle => 'Edytuj rozmowę';

  @override
  String get changeTheConversationTitle => 'Zmień tytuł rozmowy';

  @override
  String get conversationTitle => 'Tytuł rozmowy';

  @override
  String get enterConversationTitle => 'Wprowadź tytuł rozmowy...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Tytuł rozmowy został pomyślnie zaktualizowany';

  @override
  String get failedToUpdateConversationTitle => 'Nie udało się zaktualizować tytułu rozmowy';

  @override
  String get errorUpdatingConversationTitle => 'Błąd podczas aktualizacji tytułu rozmowy';

  @override
  String get settingUp => 'Konfigurowanie...';

  @override
  String get startYourFirstRecording => 'Rozpocznij pierwsze nagranie';

  @override
  String get preparingSystemAudioCapture => 'Przygotowywanie przechwytywania dźwięku systemu';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Kliknij przycisk, aby przechwycić dźwięk do transkrypcji na żywo, informacji AI i automatycznego zapisywania.';

  @override
  String get reconnecting => 'Ponowne łączenie...';

  @override
  String get recordingPaused => 'Nagrywanie wstrzymane';

  @override
  String get recordingActive => 'Nagrywanie aktywne';

  @override
  String get startRecording => 'Rozpocznij nagrywanie';

  @override
  String resumingInCountdown(String countdown) {
    return 'Wznawianie za ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Dotknij odtwarzania, aby wznowić';

  @override
  String get listeningForAudio => 'Nasłuchiwanie dźwięku...';

  @override
  String get preparingAudioCapture => 'Przygotowywanie przechwytywania dźwięku';

  @override
  String get clickToBeginRecording => 'Kliknij, aby rozpocząć nagrywanie';

  @override
  String get translated => 'przetłumaczone';

  @override
  String get liveTranscript => 'Transkrypcja na żywo';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmentów';
  }

  @override
  String get startRecordingToSeeTranscript => 'Rozpocznij nagrywanie, aby zobaczyć transkrypcję na żywo';

  @override
  String get paused => 'Wstrzymano';

  @override
  String get initializing => 'Inicjalizacja...';

  @override
  String get recording => 'Nagrywanie';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon zmieniony. Wznawianie za ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Kliknij odtwarzanie, aby wznowić, lub zatrzymaj, aby zakończyć';

  @override
  String get settingUpSystemAudioCapture => 'Konfigurowanie przechwytywania dźwięku systemu';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Przechwytywanie dźwięku i generowanie transkrypcji';

  @override
  String get clickToBeginRecordingSystemAudio => 'Kliknij, aby rozpocząć nagrywanie dźwięku systemu';

  @override
  String get you => 'Ty';

  @override
  String speakerWithId(String speakerId) {
    return 'Mówca $speakerId';
  }

  @override
  String get translatedByOmi => 'przetłumaczone przez omi';

  @override
  String get backToConversations => 'Powrót do rozmów';

  @override
  String get systemAudio => 'System';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Wejście audio ustawione na $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Błąd przełączania urządzenia audio: $error';
  }

  @override
  String get selectAudioInput => 'Wybierz wejście audio';

  @override
  String get loadingDevices => 'Ładowanie urządzeń...';

  @override
  String get settingsHeader => 'USTAWIENIA';

  @override
  String get plansAndBilling => 'Plany i Rozliczenia';

  @override
  String get calendarIntegration => 'Integracja Kalendarza';

  @override
  String get dailySummary => 'Podsumowanie dnia';

  @override
  String get developer => 'Deweloper';

  @override
  String get about => 'O aplikacji';

  @override
  String get selectTime => 'Wybierz godzinę';

  @override
  String get accountGroup => 'Konto';

  @override
  String get signOutQuestion => 'Wylogować się?';

  @override
  String get signOutConfirmation => 'Czy na pewno chcesz się wylogować?';

  @override
  String get customVocabularyHeader => 'NIESTANDARDOWY SŁOWNIK';

  @override
  String get addWordsDescription => 'Dodaj słowa, które Omi powinien rozpoznawać podczas transkrypcji.';

  @override
  String get enterWordsHint => 'Wprowadź słowa (oddzielone przecinkami)';

  @override
  String get dailySummaryHeader => 'DZIENNE PODSUMOWANIE';

  @override
  String get dailySummaryTitle => 'Dzienne Podsumowanie';

  @override
  String get dailySummaryDescription => 'Otrzymuj spersonalizowane podsumowanie rozmów dnia jako powiadomienie.';

  @override
  String get deliveryTime => 'Godzina dostarczenia';

  @override
  String get deliveryTimeDescription => 'Kiedy otrzymywać dzienne podsumowanie';

  @override
  String get subscription => 'Subskrypcja';

  @override
  String get viewPlansAndUsage => 'Zobacz Plany i Użycie';

  @override
  String get viewPlansDescription => 'Zarządzaj subskrypcją i zobacz statystyki użycia';

  @override
  String get addOrChangePaymentMethod => 'Dodaj lub zmień metodę płatności';

  @override
  String get displayOptions => 'Opcje wyświetlania';

  @override
  String get showMeetingsInMenuBar => 'Pokaż spotkania na pasku menu';

  @override
  String get displayUpcomingMeetingsDescription => 'Wyświetl nadchodzące spotkania na pasku menu';

  @override
  String get showEventsWithoutParticipants => 'Pokaż wydarzenia bez uczestników';

  @override
  String get includePersonalEventsDescription => 'Uwzględnij wydarzenia osobiste bez uczestników';

  @override
  String get upcomingMeetings => 'Nadchodzące spotkania';

  @override
  String get checkingNext7Days => 'Sprawdzanie następnych 7 dni';

  @override
  String get shortcuts => 'Skróty';

  @override
  String get shortcutChangeInstruction => 'Kliknij skrót, aby go zmienić. Naciśnij Escape, aby anulować.';

  @override
  String get configurePersonaDescription => 'Skonfiguruj swoją personę AI';

  @override
  String get configureSTTProvider => 'Skonfiguruj dostawcę STT';

  @override
  String get setConversationEndDescription => 'Ustaw, kiedy rozmowy kończą się automatycznie';

  @override
  String get importDataDescription => 'Importuj dane z innych źródeł';

  @override
  String get exportConversationsDescription => 'Eksportuj rozmowy do JSON';

  @override
  String get exportingConversations => 'Eksportowanie rozmów...';

  @override
  String get clearNodesDescription => 'Wyczyść wszystkie węzły i połączenia';

  @override
  String get deleteKnowledgeGraphQuestion => 'Usunąć graf wiedzy?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Spowoduje to usunięcie wszystkich pochodnych danych grafu wiedzy. Twoje oryginalne wspomnienia pozostaną bezpieczne.';

  @override
  String get connectOmiWithAI => 'Połącz Omi z asystentami AI';

  @override
  String get noAPIKeys => 'Brak kluczy API. Utwórz jeden, aby rozpocząć.';

  @override
  String get autoCreateWhenDetected => 'Automatycznie twórz po wykryciu nazwy';

  @override
  String get trackPersonalGoals => 'Śledź osobiste cele na stronie głównej';

  @override
  String get dailyReflectionDescription =>
      'Otrzymuj przypomnienie o 21:00, aby przemyśleć swój dzień i zapisać swoje myśli.';

  @override
  String get endpointURL => 'URL punktu końcowego';

  @override
  String get links => 'Linki';

  @override
  String get discordMemberCount => 'Ponad 8000 członków na Discordzie';

  @override
  String get userInformation => 'Informacje o użytkowniku';

  @override
  String get capabilities => 'Możliwości';

  @override
  String get previewScreenshots => 'Podgląd zrzutów ekranu';

  @override
  String get holdOnPreparingForm => 'Poczekaj, przygotowujemy formularz dla Ciebie';

  @override
  String get bySubmittingYouAgreeToOmi => 'Wysyłając, zgadzasz się z Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Warunki i Polityka Prywatności';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Pomaga diagnozować problemy. Automatycznie usuwany po 3 dniach.';

  @override
  String get manageYourApp => 'Zarządzaj swoją aplikacją';

  @override
  String get updatingYourApp => 'Aktualizowanie aplikacji';

  @override
  String get fetchingYourAppDetails => 'Pobieranie szczegółów aplikacji';

  @override
  String get updateAppQuestion => 'Zaktualizować aplikację?';

  @override
  String get updateAppConfirmation =>
      'Czy na pewno chcesz zaktualizować aplikację? Zmiany zostaną wprowadzone po sprawdzeniu przez nasz zespół.';

  @override
  String get updateApp => 'Zaktualizuj aplikację';

  @override
  String get createAndSubmitNewApp => 'Utwórz i prześlij nową aplikację';

  @override
  String appsCount(String count) {
    return 'Aplikacje ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Prywatne aplikacje ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Publiczne aplikacje ($count)';
  }

  @override
  String get newVersionAvailable => 'Dostępna nowa wersja  🎉';

  @override
  String get no => 'Nie';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Subskrypcja anulowana pomyślnie. Pozostanie aktywna do końca bieżącego okresu rozliczeniowego.';

  @override
  String get failedToCancelSubscription => 'Nie udało się anulować subskrypcji. Spróbuj ponownie.';

  @override
  String get invalidPaymentUrl => 'Nieprawidłowy adres URL płatności';

  @override
  String get permissionsAndTriggers => 'Uprawnienia i wyzwalacze';

  @override
  String get chatFeatures => 'Funkcje czatu';

  @override
  String get uninstall => 'Odinstaluj';

  @override
  String get installs => 'INSTALACJE';

  @override
  String get priceLabel => 'CENA';

  @override
  String get updatedLabel => 'ZAKTUALIZOWANO';

  @override
  String get createdLabel => 'UTWORZONO';

  @override
  String get featuredLabel => 'POLECANE';

  @override
  String get cancelSubscriptionQuestion => 'Anulować subskrypcję?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Czy na pewno chcesz anulować subskrypcję? Będziesz mieć dostęp do końca bieżącego okresu rozliczeniowego.';

  @override
  String get cancelSubscriptionButton => 'Anuluj subskrypcję';

  @override
  String get cancelling => 'Anulowanie...';

  @override
  String get betaTesterMessage =>
      'Jesteś beta testerem tej aplikacji. Nie jest jeszcze publiczna. Będzie publiczna po zatwierdzeniu.';

  @override
  String get appUnderReviewMessage =>
      'Twoja aplikacja jest w trakcie weryfikacji i widoczna tylko dla Ciebie. Będzie publiczna po zatwierdzeniu.';

  @override
  String get appRejectedMessage => 'Twoja aplikacja została odrzucona. Zaktualizuj szczegóły i prześlij ponownie.';

  @override
  String get invalidIntegrationUrl => 'Nieprawidłowy URL integracji';

  @override
  String get tapToComplete => 'Dotknij, aby zakończyć';

  @override
  String get invalidSetupInstructionsUrl => 'Nieprawidłowy URL instrukcji konfiguracji';

  @override
  String get pushToTalk => 'Naciśnij, aby mówić';

  @override
  String get summaryPrompt => 'Monit podsumowania';

  @override
  String get pleaseSelectARating => 'Wybierz ocenę';

  @override
  String get reviewAddedSuccessfully => 'Recenzja dodana pomyślnie 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recenzja zaktualizowana pomyślnie 🚀';

  @override
  String get failedToSubmitReview => 'Nie udało się przesłać recenzji. Spróbuj ponownie.';

  @override
  String get addYourReview => 'Dodaj swoją recenzję';

  @override
  String get editYourReview => 'Edytuj swoją recenzję';

  @override
  String get writeAReviewOptional => 'Napisz recenzję (opcjonalnie)';

  @override
  String get submitReview => 'Prześlij recenzję';

  @override
  String get updateReview => 'Zaktualizuj recenzję';

  @override
  String get yourReview => 'Twoja recenzja';

  @override
  String get anonymousUser => 'Anonimowy użytkownik';

  @override
  String get issueActivatingApp => 'Wystąpił problem z aktywacją tej aplikacji. Spróbuj ponownie.';

  @override
  String get dataAccessNoticeDescription =>
      'This app will access your data. Omi AI is not responsible for how your data is used, modified, or deleted by this app';

  @override
  String get copyUrl => 'Kopiuj URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Pon';

  @override
  String get weekdayTue => 'Wt';

  @override
  String get weekdayWed => 'Śr';

  @override
  String get weekdayThu => 'Czw';

  @override
  String get weekdayFri => 'Pt';

  @override
  String get weekdaySat => 'Sob';

  @override
  String get weekdaySun => 'Nd';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integracja z $serviceName wkrótce';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Już wyeksportowano do $platform';
  }

  @override
  String get anotherPlatform => 'inną platformę';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Proszę uwierzytelnić się w $serviceName w Ustawienia > Integracje zadań';
  }

  @override
  String addingToService(String serviceName) {
    return 'Dodawanie do $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Dodano do $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Nie udało się dodać do $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Odmowa uprawnień dla Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Nie udało się utworzyć klucza API dostawcy: $error';
  }

  @override
  String get createAKey => 'Utwórz klucz';

  @override
  String get apiKeyRevokedSuccessfully => 'Klucz API został pomyślnie unieważniony';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Nie udało się unieważnić klucza API: $error';
  }

  @override
  String get omiApiKeys => 'Klucze API Omi';

  @override
  String get apiKeysDescription =>
      'Klucze API są używane do uwierzytelniania, gdy aplikacja komunikuje się z serwerem OMI. Umożliwiają aplikacji tworzenie wspomnień i bezpieczny dostęp do innych usług OMI.';

  @override
  String get aboutOmiApiKeys => 'O kluczach API Omi';

  @override
  String get yourNewKey => 'Twój nowy klucz:';

  @override
  String get copyToClipboard => 'Kopiuj do schowka';

  @override
  String get pleaseCopyKeyNow => 'Skopiuj go teraz i zapisz w bezpiecznym miejscu. ';

  @override
  String get willNotSeeAgain => 'Nie będziesz mógł go ponownie zobaczyć.';

  @override
  String get revokeKey => 'Unieważnij klucz';

  @override
  String get revokeApiKeyQuestion => 'Unieważnić klucz API?';

  @override
  String get revokeApiKeyWarning =>
      'Tej akcji nie można cofnąć. Aplikacje używające tego klucza nie będą już mogły uzyskać dostępu do API.';

  @override
  String get revoke => 'Unieważnij';

  @override
  String get whatWouldYouLikeToCreate => 'Co chciałbyś stworzyć?';

  @override
  String get createAnApp => 'Utwórz aplikację';

  @override
  String get createAndShareYourApp => 'Stwórz i udostępnij swoją aplikację';

  @override
  String get createMyClone => 'Utwórz mojego klona';

  @override
  String get createYourDigitalClone => 'Stwórz swój cyfrowy klon';

  @override
  String get itemApp => 'Aplikacja';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Zachowaj $item publiczną';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Upublicznić $item?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Ustawić $item jako prywatną?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Jeśli upublicznisz $item, będzie mogła być używana przez wszystkich';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Jeśli teraz ustawisz $item jako prywatną, przestanie działać dla wszystkich i będzie widoczna tylko dla ciebie';
  }

  @override
  String get manageApp => 'Zarządzaj aplikacją';

  @override
  String get updatePersonaDetails => 'Aktualizuj szczegóły persony';

  @override
  String deleteItemTitle(String item) {
    return 'Usuń $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Usunąć $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Czy na pewno chcesz usunąć tę $item? Tej czynności nie można cofnąć.';
  }

  @override
  String get revokeKeyQuestion => 'Unieważnić klucz?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Czy na pewno chcesz unieważnić klucz \"$keyName\"? Tej czynności nie można cofnąć.';
  }

  @override
  String get createNewKey => 'Utwórz nowy klucz';

  @override
  String get keyNameHint => 'np. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Proszę podać nazwę.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Nie udało się utworzyć klucza: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Nie udało się utworzyć klucza. Spróbuj ponownie.';

  @override
  String get keyCreated => 'Klucz utworzony';

  @override
  String get keyCreatedMessage =>
      'Twój nowy klucz został utworzony. Skopiuj go teraz. Nie będziesz mógł go ponownie zobaczyć.';

  @override
  String get keyWord => 'Klucz';

  @override
  String get externalAppAccess => 'Dostęp aplikacji zewnętrznych';

  @override
  String get externalAppAccessDescription =>
      'Następujące zainstalowane aplikacje mają zewnętrzne integracje i mogą uzyskać dostęp do twoich danych, takich jak rozmowy i wspomnienia.';

  @override
  String get noExternalAppsHaveAccess => 'Żadne zewnętrzne aplikacje nie mają dostępu do twoich danych.';

  @override
  String get maximumSecurityE2ee => 'Maksymalne bezpieczeństwo (E2EE)';

  @override
  String get e2eeDescription =>
      'Szyfrowanie end-to-end to złoty standard prywatności. Po włączeniu dane są szyfrowane na urządzeniu przed wysłaniem na nasze serwery. Oznacza to, że nikt, nawet Omi, nie może uzyskać dostępu do Twoich treści.';

  @override
  String get importantTradeoffs => 'Ważne kompromisy:';

  @override
  String get e2eeTradeoff1 =>
      '• Niektóre funkcje, takie jak integracje z zewnętrznymi aplikacjami, mogą być wyłączone.';

  @override
  String get e2eeTradeoff2 => '• Jeśli zgubisz hasło, Twoje dane nie mogą zostać odzyskane.';

  @override
  String get featureComingSoon => 'Ta funkcja wkrótce będzie dostępna!';

  @override
  String get migrationInProgressMessage =>
      'Migracja w toku. Nie możesz zmienić poziomu ochrony, dopóki się nie zakończy.';

  @override
  String get migrationFailed => 'Migracja nie powiodła się';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migracja z $source do $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total obiektów';
  }

  @override
  String get secureEncryption => 'Bezpieczne szyfrowanie';

  @override
  String get secureEncryptionDescription =>
      'Twoje dane są szyfrowane kluczem unikalnym dla Ciebie na naszych serwerach hostowanych w Google Cloud. Oznacza to, że Twoje surowe treści są niedostępne dla nikogo, w tym pracowników Omi lub Google, bezpośrednio z bazy danych.';

  @override
  String get endToEndEncryption => 'Szyfrowanie end-to-end';

  @override
  String get e2eeCardDescription =>
      'Włącz dla maksymalnego bezpieczeństwa, gdzie tylko Ty masz dostęp do swoich danych. Dotknij, aby dowiedzieć się więcej.';

  @override
  String get dataAlwaysEncrypted =>
      'Niezależnie od poziomu, Twoje dane są zawsze szyfrowane w stanie spoczynku i podczas przesyłania.';

  @override
  String get readOnlyScope => 'Tylko odczyt';

  @override
  String get fullAccessScope => 'Pełny dostęp';

  @override
  String get readScope => 'Odczyt';

  @override
  String get writeScope => 'Zapis';

  @override
  String get apiKeyCreated => 'Klucz API utworzony!';

  @override
  String get saveKeyWarning => 'Zapisz ten klucz teraz! Nie będziesz mógł go ponownie zobaczyć.';

  @override
  String get yourApiKey => 'TWÓJ KLUCZ API';

  @override
  String get tapToCopy => 'Dotknij, aby skopiować';

  @override
  String get copyKey => 'Kopiuj klucz';

  @override
  String get createApiKey => 'Utwórz klucz API';

  @override
  String get accessDataProgrammatically => 'Uzyskaj programowy dostęp do swoich danych';

  @override
  String get keyNameLabel => 'NAZWA KLUCZA';

  @override
  String get keyNamePlaceholder => 'np. Moja integracja';

  @override
  String get permissionsLabel => 'UPRAWNIENIA';

  @override
  String get permissionsInfoNote => 'R = Odczyt, W = Zapis. Domyślnie tylko odczyt, jeśli nic nie wybrano.';

  @override
  String get developerApi => 'API dla programistów';

  @override
  String get createAKeyToGetStarted => 'Utwórz klucz, aby rozpocząć';

  @override
  String errorWithMessage(String error) {
    return 'Błąd: $error';
  }

  @override
  String get omiTraining => 'Szkolenie Omi';

  @override
  String get trainingDataProgram => 'Program danych szkoleniowych';

  @override
  String get getOmiUnlimitedFree => 'Uzyskaj Omi Unlimited za darmo, przekazując swoje dane do trenowania modeli AI.';

  @override
  String get trainingDataBullets =>
      '• Twoje dane pomagają ulepszać modele AI\n• Udostępniane są tylko dane niewrażliwe\n• W pełni przejrzysty proces';

  @override
  String get learnMoreAtOmiTraining => 'Dowiedz się więcej na omi.me/training';

  @override
  String get agreeToContributeData => 'Rozumiem i zgadzam się na przekazanie moich danych do trenowania AI';

  @override
  String get submitRequest => 'Wyślij prośbę';

  @override
  String get thankYouRequestUnderReview =>
      'Dziękujemy! Twoja prośba jest rozpatrywana. Powiadomimy Cię po zatwierdzeniu.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Twój plan pozostanie aktywny do $date. Następnie utracisz dostęp do nieograniczonych funkcji. Czy na pewno?';
  }

  @override
  String get confirmCancellation => 'Potwierdź anulowanie';

  @override
  String get keepMyPlan => 'Zachowaj mój plan';

  @override
  String get subscriptionSetToCancel => 'Twoja subskrypcja jest ustawiona na anulowanie na koniec okresu.';

  @override
  String get switchedToOnDevice => 'Przełączono na transkrypcję na urządzeniu';

  @override
  String get couldNotSwitchToFreePlan => 'Nie można przełączyć na darmowy plan. Spróbuj ponownie.';

  @override
  String get couldNotLoadPlans => 'Nie można załadować dostępnych planów. Spróbuj ponownie.';

  @override
  String get selectedPlanNotAvailable => 'Wybrany plan nie jest dostępny. Spróbuj ponownie.';

  @override
  String get upgradeToAnnualPlan => 'Przejdź na plan roczny';

  @override
  String get importantBillingInfo => 'Ważne informacje rozliczeniowe:';

  @override
  String get monthlyPlanContinues => 'Twój obecny plan miesięczny będzie kontynuowany do końca okresu rozliczeniowego';

  @override
  String get paymentMethodCharged =>
      'Twoja istniejąca metoda płatności zostanie automatycznie obciążona po zakończeniu planu miesięcznego';

  @override
  String get annualSubscriptionStarts =>
      'Twoja 12-miesięczna subskrypcja roczna rozpocznie się automatycznie po obciążeniu';

  @override
  String get thirteenMonthsCoverage => 'Otrzymasz łącznie 13 miesięcy ochrony (bieżący miesiąc + 12 miesięcy rocznie)';

  @override
  String get confirmUpgrade => 'Potwierdź ulepszenie';

  @override
  String get confirmPlanChange => 'Potwierdź zmianę planu';

  @override
  String get confirmAndProceed => 'Potwierdź i kontynuuj';

  @override
  String get upgradeScheduled => 'Aktualizacja zaplanowana';

  @override
  String get changePlan => 'Zmień plan';

  @override
  String get upgradeAlreadyScheduled => 'Twoja aktualizacja do planu rocznego jest już zaplanowana';

  @override
  String get youAreOnUnlimitedPlan => 'Jesteś na planie Unlimited.';

  @override
  String get yourOmiUnleashed => 'Twoje Omi, uwolnione. Przejdź na unlimited dla nieskończonych możliwości.';

  @override
  String planEndedOn(String date) {
    return 'Twój plan zakończył się $date.\\nSubskrybuj ponownie teraz - zostaniesz natychmiast obciążony za nowy okres rozliczeniowy.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Twój plan jest ustawiony na anulowanie $date.\\nSubskrybuj ponownie teraz, aby zachować korzyści - bez opłat do $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Twój plan roczny rozpocznie się automatycznie po zakończeniu planu miesięcznego.';

  @override
  String planRenewsOn(String date) {
    return 'Twój plan odnawia się $date.';
  }

  @override
  String get unlimitedConversations => 'Nieograniczone rozmowy';

  @override
  String get askOmiAnything => 'Zapytaj Omi o cokolwiek dotyczącego swojego życia';

  @override
  String get unlockOmiInfiniteMemory => 'Odblokuj nieskończoną pamięć Omi';

  @override
  String get youreOnAnnualPlan => 'Jesteś na planie rocznym';

  @override
  String get alreadyBestValuePlan => 'Masz już plan o najlepszej wartości. Zmiany nie są potrzebne.';

  @override
  String get unableToLoadPlans => 'Nie można załadować planów';

  @override
  String get checkConnectionTryAgain => 'Sprawdź połączenie i spróbuj ponownie';

  @override
  String get useFreePlan => 'Użyj darmowego planu';

  @override
  String get continueText => 'Kontynuuj';

  @override
  String get resubscribe => 'Subskrybuj ponownie';

  @override
  String get couldNotOpenPaymentSettings => 'Nie można otworzyć ustawień płatności. Spróbuj ponownie.';

  @override
  String get managePaymentMethod => 'Zarządzaj metodą płatności';

  @override
  String get cancelSubscription => 'Anuluj subskrypcję';

  @override
  String endsOnDate(String date) {
    return 'Kończy się $date';
  }

  @override
  String get active => 'Aktywny';

  @override
  String get freePlan => 'Darmowy plan';

  @override
  String get configure => 'Konfiguruj';

  @override
  String get privacyInformation => 'Informacje o prywatności';

  @override
  String get yourPrivacyMattersToUs => 'Twoja prywatność jest dla nas ważna';

  @override
  String get privacyIntroText =>
      'W Omi bardzo poważnie traktujemy Twoją prywatność. Chcemy być przejrzyści w kwestii danych, które zbieramy i jak je wykorzystujemy. Oto co musisz wiedzieć:';

  @override
  String get whatWeTrack => 'Co śledzimy';

  @override
  String get anonymityAndPrivacy => 'Anonimowość i prywatność';

  @override
  String get optInAndOptOutOptions => 'Opcje zgody i rezygnacji';

  @override
  String get ourCommitment => 'Nasze zobowiązanie';

  @override
  String get commitmentText =>
      'Zobowiązujemy się wykorzystywać zebrane dane tylko po to, aby Omi był lepszym produktem dla Ciebie. Twoja prywatność i zaufanie są dla nas najważniejsze.';

  @override
  String get thankYouText =>
      'Dziękujemy za bycie cenionym użytkownikiem Omi. Jeśli masz jakiekolwiek pytania lub wątpliwości, skontaktuj się z nami pod adresem team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Ustawienia synchronizacji WiFi';

  @override
  String get enterHotspotCredentials => 'Wprowadź dane hotspotu telefonu';

  @override
  String get wifiSyncUsesHotspot =>
      'Synchronizacja WiFi używa telefonu jako hotspota. Znajdź nazwę i hasło w Ustawienia > Hotspot osobisty.';

  @override
  String get hotspotNameSsid => 'Nazwa hotspota (SSID)';

  @override
  String get exampleIphoneHotspot => 'np. iPhone Hotspot';

  @override
  String get password => 'Hasło';

  @override
  String get enterHotspotPassword => 'Wprowadź hasło hotspota';

  @override
  String get saveCredentials => 'Zapisz dane logowania';

  @override
  String get clearCredentials => 'Wyczyść dane logowania';

  @override
  String get pleaseEnterHotspotName => 'Wprowadź nazwę hotspota';

  @override
  String get wifiCredentialsSaved => 'Dane WiFi zapisane';

  @override
  String get wifiCredentialsCleared => 'Dane WiFi wyczyszczone';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Podsumowanie wygenerowane dla $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Nie udało się wygenerować podsumowania. Upewnij się, że masz rozmowy z tego dnia.';

  @override
  String get summaryNotFound => 'Nie znaleziono podsumowania';

  @override
  String get yourDaysJourney => 'Twoja podróż dnia';

  @override
  String get highlights => 'Najważniejsze';

  @override
  String get unresolvedQuestions => 'Nierozwiązane pytania';

  @override
  String get decisions => 'Decyzje';

  @override
  String get learnings => 'Wnioski';

  @override
  String get autoDeletesAfterThreeDays => 'Automatycznie usuwane po 3 dniach.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graf wiedzy usunięty pomyślnie';

  @override
  String get exportStartedMayTakeFewSeconds => 'Eksport rozpoczęty. Może to zająć kilka sekund...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'To usunie wszystkie pochodne dane grafu wiedzy (węzły i połączenia). Twoje oryginalne wspomnienia pozostaną bezpieczne. Graf zostanie odbudowany z czasem lub przy następnym żądaniu.';

  @override
  String get configureDailySummaryDigest => 'Skonfiguruj dzienny przegląd zadań';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Dostęp do $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'wyzwalane przez $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription i jest $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Jest $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Nie skonfigurowano konkretnego dostępu do danych.';

  @override
  String get basicPlanDescription => '1200 minut premium + nieograniczone na urządzeniu';

  @override
  String get minutes => 'minut';

  @override
  String get omiHas => 'Omi ma:';

  @override
  String get premiumMinutesUsed => 'Minuty premium wykorzystane.';

  @override
  String get setupOnDevice => 'Skonfiguruj na urządzeniu';

  @override
  String get forUnlimitedFreeTranscription => 'do nieograniczonej darmowej transkrypcji.';

  @override
  String premiumMinsLeft(int count) {
    return 'Pozostało $count minut premium.';
  }

  @override
  String get alwaysAvailable => 'zawsze dostępne.';

  @override
  String get importHistory => 'Historia importu';

  @override
  String get noImportsYet => 'Brak importów';

  @override
  String get selectZipFileToImport => 'Wybierz plik .zip do importu!';

  @override
  String get otherDevicesComingSoon => 'Inne urządzenia wkrótce';

  @override
  String get deleteAllLimitlessConversations => 'Usunąć wszystkie rozmowy Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'Spowoduje to trwałe usunięcie wszystkich rozmów zaimportowanych z Limitless. Tej akcji nie można cofnąć.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Usunięto $count rozmów Limitless';
  }

  @override
  String get failedToDeleteConversations => 'Nie udało się usunąć rozmów';

  @override
  String get deleteImportedData => 'Usuń zaimportowane dane';

  @override
  String get statusPending => 'Oczekuje';

  @override
  String get statusProcessing => 'Przetwarzanie';

  @override
  String get statusCompleted => 'Ukończone';

  @override
  String get statusFailed => 'Nieudane';

  @override
  String nConversations(int count) {
    return '$count rozmów';
  }

  @override
  String get pleaseEnterName => 'Proszę wpisać imię';

  @override
  String get nameMustBeBetweenCharacters => 'Nazwa musi mieć od 2 do 40 znaków';

  @override
  String get deleteSampleQuestion => 'Usunąć próbkę?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Czy na pewno chcesz usunąć próbkę $name?';
  }

  @override
  String get confirmDeletion => 'Potwierdź usunięcie';

  @override
  String deletePersonConfirmation(String name) {
    return 'Czy na pewno chcesz usunąć $name? Spowoduje to również usunięcie wszystkich powiązanych próbek mowy.';
  }

  @override
  String get howItWorksTitle => 'Jak to działa?';

  @override
  String get howPeopleWorks =>
      'Po utworzeniu osoby możesz przejść do transkrypcji rozmowy i przypisać im odpowiednie segmenty, w ten sposób Omi będzie mógł rozpoznać również ich mowę!';

  @override
  String get tapToDelete => 'Dotknij, aby usunąć';

  @override
  String get newTag => 'NOWOŚĆ';

  @override
  String get needHelpChatWithUs => 'Potrzebujesz pomocy? Porozmawiaj z nami';

  @override
  String get localStorageEnabled => 'Pamięć lokalna włączona';

  @override
  String get localStorageDisabled => 'Pamięć lokalna wyłączona';

  @override
  String failedToUpdateSettings(String error) {
    return 'Nie udało się zaktualizować ustawień: $error';
  }

  @override
  String get privacyNotice => 'Informacja o prywatności';

  @override
  String get recordingsMayCaptureOthers =>
      'Nagrania mogą przechwytywać głosy innych osób. Przed włączeniem upewnij się, że masz zgodę wszystkich uczestników.';

  @override
  String get enable => 'Włącz';

  @override
  String get storeAudioOnPhone => 'Store Audio on Phone';

  @override
  String get on => 'Włącz';

  @override
  String get storeAudioDescription =>
      'Przechowuj wszystkie nagrania audio lokalnie na telefonie. Po wyłączeniu tylko nieudane przesyłania są zachowywane, aby zaoszczędzić miejsce.';

  @override
  String get enableLocalStorage => 'Włącz pamięć lokalną';

  @override
  String get cloudStorageEnabled => 'Pamięć w chmurze włączona';

  @override
  String get cloudStorageDisabled => 'Pamięć w chmurze wyłączona';

  @override
  String get enableCloudStorage => 'Włącz pamięć w chmurze';

  @override
  String get storeAudioOnCloud => 'Store Audio on Cloud';

  @override
  String get cloudStorageDialogMessage =>
      'Twoje nagrania w czasie rzeczywistym będą przechowywane w prywatnej chmurze podczas mówienia.';

  @override
  String get storeAudioCloudDescription =>
      'Przechowuj nagrania w czasie rzeczywistym w prywatnej chmurze podczas mówienia. Dźwięk jest przechwytywany i bezpiecznie zapisywany w czasie rzeczywistym.';

  @override
  String get downloadingFirmware => 'Pobieranie oprogramowania';

  @override
  String get installingFirmware => 'Instalowanie oprogramowania';

  @override
  String get firmwareUpdateWarning =>
      'Nie zamykaj aplikacji ani nie wyłączaj urządzenia. Może to uszkodzić urządzenie.';

  @override
  String get firmwareUpdated => 'Oprogramowanie zaktualizowane';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Uruchom ponownie $deviceName, aby zakończyć aktualizację.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Twoje urządzenie jest aktualne';

  @override
  String get currentVersion => 'Aktualna wersja';

  @override
  String get latestVersion => 'Najnowsza wersja';

  @override
  String get whatsNew => 'Co nowego';

  @override
  String get installUpdate => 'Zainstaluj aktualizację';

  @override
  String get updateNow => 'Aktualizuj teraz';

  @override
  String get updateGuide => 'Przewodnik aktualizacji';

  @override
  String get checkingForUpdates => 'Sprawdzanie aktualizacji';

  @override
  String get checkingFirmwareVersion => 'Sprawdzanie wersji oprogramowania...';

  @override
  String get firmwareUpdate => 'Aktualizacja oprogramowania';

  @override
  String get payments => 'Płatności';

  @override
  String get connectPaymentMethodInfo =>
      'Połącz metodę płatności poniżej, aby zacząć otrzymywać wypłaty za swoje aplikacje.';

  @override
  String get selectedPaymentMethod => 'Wybrana metoda płatności';

  @override
  String get availablePaymentMethods => 'Dostępne metody płatności';

  @override
  String get activeStatus => 'Aktywny';

  @override
  String get connectedStatus => 'Połączono';

  @override
  String get notConnectedStatus => 'Nie połączono';

  @override
  String get setActive => 'Ustaw jako aktywny';

  @override
  String get getPaidThroughStripe => 'Otrzymuj płatności za sprzedaż aplikacji przez Stripe';

  @override
  String get monthlyPayouts => 'Miesięczne wypłaty';

  @override
  String get monthlyPayoutsDescription =>
      'Otrzymuj miesięczne płatności bezpośrednio na konto, gdy osiągniesz 10 \$ zarobków';

  @override
  String get secureAndReliable => 'Bezpieczne i niezawodne';

  @override
  String get stripeSecureDescription => 'Stripe zapewnia bezpieczne i terminowe przelewy przychodów z aplikacji';

  @override
  String get selectYourCountry => 'Wybierz swój kraj';

  @override
  String get countrySelectionPermanent => 'Wybór kraju jest trwały i nie można go później zmienić.';

  @override
  String get byClickingConnectNow => 'Klikając \"Połącz teraz\" zgadzasz się na';

  @override
  String get stripeConnectedAccountAgreement => 'Umowa konta połączonego Stripe';

  @override
  String get errorConnectingToStripe => 'Błąd łączenia ze Stripe! Spróbuj ponownie później.';

  @override
  String get connectingYourStripeAccount => 'Łączenie konta Stripe';

  @override
  String get stripeOnboardingInstructions =>
      'Proszę ukończyć proces rejestracji Stripe w przeglądarce. Ta strona zostanie automatycznie zaktualizowana po zakończeniu.';

  @override
  String get failedTryAgain => 'Nie udało się? Spróbuj ponownie';

  @override
  String get illDoItLater => 'Zrobię to później';

  @override
  String get successfullyConnected => 'Pomyślnie połączono!';

  @override
  String get stripeReadyForPayments =>
      'Twoje konto Stripe jest teraz gotowe do przyjmowania płatności. Możesz od razu zacząć zarabiać na sprzedaży aplikacji.';

  @override
  String get updateStripeDetails => 'Zaktualizuj dane Stripe';

  @override
  String get errorUpdatingStripeDetails => 'Błąd aktualizacji danych Stripe! Spróbuj ponownie później.';

  @override
  String get updatePayPal => 'Zaktualizuj PayPal';

  @override
  String get setUpPayPal => 'Skonfiguruj PayPal';

  @override
  String get updatePayPalAccountDetails => 'Zaktualizuj dane swojego konta PayPal';

  @override
  String get connectPayPalToReceivePayments =>
      'Połącz swoje konto PayPal, aby zacząć otrzymywać płatności za swoje aplikacje';

  @override
  String get paypalEmail => 'E-mail PayPal';

  @override
  String get paypalMeLink => 'Link PayPal.me';

  @override
  String get stripeRecommendation =>
      'Jeśli Stripe jest dostępny w Twoim kraju, zdecydowanie zalecamy korzystanie z niego dla szybszych i łatwiejszych wypłat.';

  @override
  String get updatePayPalDetails => 'Zaktualizuj dane PayPal';

  @override
  String get savePayPalDetails => 'Zapisz dane PayPal';

  @override
  String get pleaseEnterPayPalEmail => 'Wprowadź swój e-mail PayPal';

  @override
  String get pleaseEnterPayPalMeLink => 'Wprowadź swój link PayPal.me';

  @override
  String get doNotIncludeHttpInLink => 'Nie dodawaj http, https ani www do linku';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Wprowadź prawidłowy link PayPal.me';

  @override
  String get pleaseEnterValidEmail => 'Proszę podać prawidłowy adres e-mail';

  @override
  String get syncingYourRecordings => 'Synchronizacja nagrań';

  @override
  String get syncYourRecordings => 'Zsynchronizuj nagrania';

  @override
  String get syncNow => 'Synchronizuj teraz';

  @override
  String get error => 'Błąd';

  @override
  String get speechSamples => 'Próbki głosowe';

  @override
  String additionalSampleIndex(String index) {
    return 'Dodatkowa próbka $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Czas trwania: $seconds sekund';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Dodatkowa próbka głosowa usunięta';

  @override
  String get consentDataMessage =>
      'Kontynuując, wszystkie dane, które udostępniasz tej aplikacji (w tym rozmowy, nagrania i dane osobowe), będą bezpiecznie przechowywane na naszych serwerach, aby zapewnić Ci spostrzeżenia oparte na AI i włączyć wszystkie funkcje aplikacji.';

  @override
  String get tasksEmptyStateMessage => 'Zadania z twoich rozmów pojawią się tutaj.\nDotknij +, aby utworzyć ręcznie.';

  @override
  String get clearChatAction => 'Wyczyść czat';

  @override
  String get enableApps => 'Włącz aplikacje';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'pokaż więcej ↓';

  @override
  String get showLess => 'pokaż mniej ↑';

  @override
  String get loadingYourRecording => 'Ładowanie nagrania...';

  @override
  String get photoDiscardedMessage => 'To zdjęcie zostało odrzucone, ponieważ nie było istotne.';

  @override
  String get analyzing => 'Analizowanie...';

  @override
  String get searchCountries => 'Szukaj krajów...';

  @override
  String get checkingAppleWatch => 'Sprawdzanie Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Zainstaluj Omi na\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Aby używać Apple Watch z Omi, musisz najpierw zainstalować aplikację Omi na zegarku.';

  @override
  String get openOmiOnAppleWatch => 'Otwórz Omi na\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Aplikacja Omi jest zainstalowana na Apple Watch. Otwórz ją i dotknij Start, aby rozpocząć.';

  @override
  String get openWatchApp => 'Otwórz aplikację Watch';

  @override
  String get iveInstalledAndOpenedTheApp => 'Zainstalowałem i otworzyłem aplikację';

  @override
  String get unableToOpenWatchApp =>
      'Nie można otworzyć aplikacji Apple Watch. Ręcznie otwórz aplikację Watch na Apple Watch i zainstaluj Omi z sekcji \"Dostępne aplikacje\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch połączony pomyślnie!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch nadal nieosiągalny. Upewnij się, że aplikacja Omi jest otwarta na zegarku.';

  @override
  String errorCheckingConnection(String error) {
    return 'Błąd sprawdzania połączenia: $error';
  }

  @override
  String get muted => 'Wyciszono';

  @override
  String get processNow => 'Przetwórz teraz';

  @override
  String get finishedConversation => 'Zakończyć rozmowę?';

  @override
  String get stopRecordingConfirmation => 'Czy na pewno chcesz zatrzymać nagrywanie i podsumować rozmowę teraz?';

  @override
  String get conversationEndsManually => 'Rozmowa zakończy się tylko ręcznie.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Rozmowa jest podsumowywana po $minutes minut$suffix ciszy.';
  }

  @override
  String get dontAskAgain => 'Nie pytaj ponownie';

  @override
  String get waitingForTranscriptOrPhotos => 'Oczekiwanie na transkrypcję lub zdjęcia...';

  @override
  String get noSummaryYet => 'Brak podsumowania';

  @override
  String hints(String text) {
    return 'Wskazówki: $text';
  }

  @override
  String get testConversationPrompt => 'Testuj prompt rozmowy';

  @override
  String get prompt => 'Polecenie';

  @override
  String get result => 'Wynik:';

  @override
  String get compareTranscripts => 'Porównaj transkrypcje';

  @override
  String get notHelpful => 'Nieprzydatne';

  @override
  String get exportTasksWithOneTap => 'Eksportuj zadania jednym dotknięciem!';

  @override
  String get inProgress => 'W trakcie';

  @override
  String get photos => 'Zdjęcia';

  @override
  String get rawData => 'Surowe dane';

  @override
  String get content => 'Zawartość';

  @override
  String get noContentToDisplay => 'Brak treści do wyświetlenia';

  @override
  String get noSummary => 'Brak podsumowania';

  @override
  String get updateOmiFirmware => 'Zaktualizuj oprogramowanie omi';

  @override
  String get anErrorOccurredTryAgain => 'Wystąpił błąd. Spróbuj ponownie.';

  @override
  String get welcomeBackSimple => 'Witaj ponownie';

  @override
  String get addVocabularyDescription => 'Dodaj słowa, które Omi powinno rozpoznawać podczas transkrypcji.';

  @override
  String get enterWordsCommaSeparated => 'Wprowadź słowa (oddzielone przecinkami)';

  @override
  String get whenToReceiveDailySummary => 'Kiedy otrzymać dzienne podsumowanie';

  @override
  String get checkingNextSevenDays => 'Sprawdzanie następnych 7 dni';

  @override
  String failedToDeleteError(String error) {
    return 'Nie udało się usunąć: $error';
  }

  @override
  String get developerApiKeys => 'Klucze API dewelopera';

  @override
  String get noApiKeysCreateOne => 'Brak kluczy API. Utwórz jeden, aby rozpocząć.';

  @override
  String get commandRequired => '⌘ wymagane';

  @override
  String get spaceKey => 'Spacja';

  @override
  String loadMoreRemaining(String count) {
    return 'Załaduj więcej ($count pozostało)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% użytkownik';
  }

  @override
  String get wrappedMinutes => 'minut';

  @override
  String get wrappedConversations => 'rozmów';

  @override
  String get wrappedDaysActive => 'aktywnych dni';

  @override
  String get wrappedYouTalkedAbout => 'Rozmawiałeś o';

  @override
  String get wrappedActionItems => 'Zadania';

  @override
  String get wrappedTasksCreated => 'utworzonych zadań';

  @override
  String get wrappedCompleted => 'ukończonych';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% wskaźnik ukończenia';
  }

  @override
  String get wrappedYourTopDays => 'Twoje najlepsze dni';

  @override
  String get wrappedBestMoments => 'Najlepsze chwile';

  @override
  String get wrappedMyBuddies => 'Moi znajomi';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Nie mogłem przestać mówić o';

  @override
  String get wrappedShow => 'SERIAL';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'KSIĄŻKA';

  @override
  String get wrappedCelebrity => 'CELEBRYTA';

  @override
  String get wrappedFood => 'JEDZENIE';

  @override
  String get wrappedMovieRecs => 'Polecenia filmów dla przyjaciół';

  @override
  String get wrappedBiggest => 'Największe';

  @override
  String get wrappedStruggle => 'Wyzwanie';

  @override
  String get wrappedButYouPushedThrough => 'Ale dałeś radę 💪';

  @override
  String get wrappedWin => 'Zwycięstwo';

  @override
  String get wrappedYouDidIt => 'Udało ci się! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 zwrotów';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'rozmów';

  @override
  String get wrappedDays => 'dni';

  @override
  String get wrappedMyBuddiesLabel => 'MOI ZNAJOMI';

  @override
  String get wrappedObsessionsLabel => 'OBSESJE';

  @override
  String get wrappedStruggleLabel => 'WYZWANIE';

  @override
  String get wrappedWinLabel => 'ZWYCIĘSTWO';

  @override
  String get wrappedTopPhrasesLabel => 'TOP ZWROTY';

  @override
  String get wrappedLetsHitRewind => 'Przewińmy twój';

  @override
  String get wrappedGenerateMyWrapped => 'Wygeneruj moje Wrapped';

  @override
  String get wrappedProcessingDefault => 'Przetwarzanie...';

  @override
  String get wrappedCreatingYourStory => 'Tworzymy twoją\nhistorię 2025...';

  @override
  String get wrappedSomethingWentWrong => 'Coś poszło\nnie tak';

  @override
  String get wrappedAnErrorOccurred => 'Wystąpił błąd';

  @override
  String get wrappedTryAgain => 'Spróbuj ponownie';

  @override
  String get wrappedNoDataAvailable => 'Brak dostępnych danych';

  @override
  String get wrappedOmiLifeRecap => 'Podsumowanie życia Omi';

  @override
  String get wrappedSwipeUpToBegin => 'Przesuń w górę, aby zacząć';

  @override
  String get wrappedShareText => 'Mój 2025, zapamiętany przez Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Udostępnianie nie powiodło się. Spróbuj ponownie.';

  @override
  String get wrappedFailedToStartGeneration => 'Nie udało się rozpocząć generowania. Spróbuj ponownie.';

  @override
  String get wrappedStarting => 'Rozpoczynanie...';

  @override
  String get wrappedShare => 'Udostępnij';

  @override
  String get wrappedShareYourWrapped => 'Udostępnij swoje Wrapped';

  @override
  String get wrappedMy2025 => 'Mój 2025';

  @override
  String get wrappedRememberedByOmi => 'zapamiętany przez Omi';

  @override
  String get wrappedMostFunDay => 'Najbardziej zabawny';

  @override
  String get wrappedMostProductiveDay => 'Najbardziej produktywny';

  @override
  String get wrappedMostIntenseDay => 'Najbardziej intensywny';

  @override
  String get wrappedFunniestMoment => 'Najzabawniejszy';

  @override
  String get wrappedMostCringeMoment => 'Najbardziej żenujący';

  @override
  String get wrappedMinutesLabel => 'minut';

  @override
  String get wrappedConversationsLabel => 'rozmów';

  @override
  String get wrappedDaysActiveLabel => 'aktywnych dni';

  @override
  String get wrappedTasksGenerated => 'zadań utworzonych';

  @override
  String get wrappedTasksCompleted => 'zadań ukończonych';

  @override
  String get wrappedTopFivePhrases => 'Top 5 fraz';

  @override
  String get wrappedAGreatDay => 'Świetny dzień';

  @override
  String get wrappedGettingItDone => 'Załatwianie spraw';

  @override
  String get wrappedAChallenge => 'Wyzwanie';

  @override
  String get wrappedAHilariousMoment => 'Zabawny moment';

  @override
  String get wrappedThatAwkwardMoment => 'Ten żenujący moment';

  @override
  String get wrappedYouHadFunnyMoments => 'Miałeś zabawne chwile w tym roku!';

  @override
  String get wrappedWeveAllBeenThere => 'Wszyscy przez to przeszliśmy!';

  @override
  String get wrappedFriend => 'Przyjaciel';

  @override
  String get wrappedYourBuddy => 'Twój kumpel!';

  @override
  String get wrappedNotMentioned => 'Nie wspomniano';

  @override
  String get wrappedTheHardPart => 'Trudna część';

  @override
  String get wrappedPersonalGrowth => 'Rozwój osobisty';

  @override
  String get wrappedFunDay => 'Zabawny';

  @override
  String get wrappedProductiveDay => 'Produktywny';

  @override
  String get wrappedIntenseDay => 'Intensywny';

  @override
  String get wrappedFunnyMomentTitle => 'Zabawny moment';

  @override
  String get wrappedCringeMomentTitle => 'Żenujący moment';

  @override
  String get wrappedYouTalkedAboutBadge => 'Rozmawiałeś o';

  @override
  String get wrappedCompletedLabel => 'Ukończono';

  @override
  String get wrappedMyBuddiesCard => 'Moi przyjaciele';

  @override
  String get wrappedBuddiesLabel => 'PRZYJACIELE';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESJE';

  @override
  String get wrappedStruggleLabelUpper => 'WALKA';

  @override
  String get wrappedWinLabelUpper => 'WYGRANA';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRAZY';

  @override
  String get wrappedYourHeader => 'Twoje';

  @override
  String get wrappedTopDaysHeader => 'Najlepsze dni';

  @override
  String get wrappedYourTopDaysBadge => 'Twoje najlepsze dni';

  @override
  String get wrappedBestHeader => 'Najlepsze';

  @override
  String get wrappedMomentsHeader => 'Chwile';

  @override
  String get wrappedBestMomentsBadge => 'Najlepsze chwile';

  @override
  String get wrappedBiggestHeader => 'Największa';

  @override
  String get wrappedStruggleHeader => 'Walka';

  @override
  String get wrappedWinHeader => 'Wygrana';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ale dałeś radę 💪';

  @override
  String get wrappedYouDidItEmoji => 'Udało ci się! 🎉';

  @override
  String get wrappedHours => 'godzin';

  @override
  String get wrappedActions => 'akcji';

  @override
  String get multipleSpeakersDetected => 'Wykryto wielu mówców';

  @override
  String get multipleSpeakersDescription =>
      'Wygląda na to, że w nagraniu jest wielu mówców. Upewnij się, że jesteś w cichym miejscu i spróbuj ponownie.';

  @override
  String get invalidRecordingDetected => 'Wykryto nieprawidłowe nagranie';

  @override
  String get notEnoughSpeechDescription =>
      'Nie wykryto wystarczającej ilości mowy. Proszę mówić więcej i spróbować ponownie.';

  @override
  String get speechDurationDescription => 'Upewnij się, że mówisz co najmniej 5 sekund i nie więcej niż 90.';

  @override
  String get connectionLostDescription =>
      'Połączenie zostało przerwane. Sprawdź połączenie internetowe i spróbuj ponownie.';

  @override
  String get howToTakeGoodSample => 'Jak zrobić dobrą próbkę?';

  @override
  String get goodSampleInstructions =>
      '1. Upewnij się, że jesteś w cichym miejscu.\n2. Mów wyraźnie i naturalnie.\n3. Upewnij się, że urządzenie jest w naturalnej pozycji na szyi.\n\nPo utworzeniu zawsze możesz je ulepszyć lub zrobić ponownie.';

  @override
  String get noDeviceConnectedUseMic => 'Brak podłączonego urządzenia. Zostanie użyty mikrofon telefonu.';

  @override
  String get doItAgain => 'Zrób ponownie';

  @override
  String get listenToSpeechProfile => 'Posłuchaj mojego profilu głosowego ➡️';

  @override
  String get recognizingOthers => 'Rozpoznawanie innych 👀';

  @override
  String get keepGoingGreat => 'Kontynuuj, świetnie ci idzie';

  @override
  String get somethingWentWrongTryAgain => 'Coś poszło nie tak! Spróbuj ponownie później.';

  @override
  String get uploadingVoiceProfile => 'Przesyłanie Twojego profilu głosowego....';

  @override
  String get memorizingYourVoice => 'Zapamiętywanie Twojego głosu...';

  @override
  String get personalizingExperience => 'Personalizowanie Twojego doświadczenia...';

  @override
  String get keepSpeakingUntil100 => 'Mów dalej, aż osiągniesz 100%.';

  @override
  String get greatJobAlmostThere => 'Świetna robota, prawie gotowe';

  @override
  String get soCloseJustLittleMore => 'Tak blisko, jeszcze trochę';

  @override
  String get notificationFrequency => 'Częstotliwość powiadomień';

  @override
  String get controlNotificationFrequency => 'Kontroluj, jak często Omi wysyła Ci proaktywne powiadomienia.';

  @override
  String get yourScore => 'Twój wynik';

  @override
  String get dailyScoreBreakdown => 'Szczegóły dziennego wyniku';

  @override
  String get todaysScore => 'Dzisiejszy wynik';

  @override
  String get tasksCompleted => 'Ukończone zadania';

  @override
  String get completionRate => 'Wskaźnik ukończenia';

  @override
  String get howItWorks => 'Jak to działa';

  @override
  String get dailyScoreExplanation =>
      'Twój dzienny wynik opiera się na ukończeniu zadań. Ukończ zadania, aby poprawić wynik!';

  @override
  String get notificationFrequencyDescription =>
      'Kontroluj, jak często Omi wysyła Ci proaktywne powiadomienia i przypomnienia.';

  @override
  String get sliderOff => 'Wył.';

  @override
  String get sliderMax => 'Maks.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Podsumowanie wygenerowane dla $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Nie udało się wygenerować podsumowania. Upewnij się, że masz rozmowy z tego dnia.';

  @override
  String get recap => 'Podsumowanie';

  @override
  String deleteQuoted(String name) {
    return 'Usuń \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Przenieś $count rozmów do:';
  }

  @override
  String get noFolder => 'Brak folderu';

  @override
  String get removeFromAllFolders => 'Usuń ze wszystkich folderów';

  @override
  String get buildAndShareYourCustomApp => 'Zbuduj i udostępnij swoją niestandardową aplikację';

  @override
  String get searchAppsPlaceholder => 'Szukaj w 1500+ aplikacjach';

  @override
  String get filters => 'Filtry';

  @override
  String get frequencyOff => 'Wyłączone';

  @override
  String get frequencyMinimal => 'Minimalna';

  @override
  String get frequencyLow => 'Niska';

  @override
  String get frequencyBalanced => 'Zrównoważona';

  @override
  String get frequencyHigh => 'Wysoka';

  @override
  String get frequencyMaximum => 'Maksymalna';

  @override
  String get frequencyDescOff => 'Brak proaktywnych powiadomień';

  @override
  String get frequencyDescMinimal => 'Tylko krytyczne przypomnienia';

  @override
  String get frequencyDescLow => 'Tylko ważne aktualizacje';

  @override
  String get frequencyDescBalanced => 'Regularne pomocne przypomnienia';

  @override
  String get frequencyDescHigh => 'Częste sprawdzenia';

  @override
  String get frequencyDescMaximum => 'Bądź stale zaangażowany';

  @override
  String get clearChatQuestion => 'Wyczyścić czat?';

  @override
  String get syncingMessages => 'Synchronizowanie wiadomości z serwerem...';

  @override
  String get chatAppsTitle => 'Aplikacje czatu';

  @override
  String get selectApp => 'Wybierz aplikację';

  @override
  String get noChatAppsEnabled => 'Brak włączonych aplikacji czatu.\nDotknij \"Włącz aplikacje\", aby dodać.';

  @override
  String get disable => 'Wyłącz';

  @override
  String get photoLibrary => 'Biblioteka zdjęć';

  @override
  String get chooseFile => 'Wybierz plik';

  @override
  String get configureAiPersona => 'Skonfiguruj swoją personę AI';

  @override
  String get connectAiAssistantsToYourData => 'Połącz asystentów AI ze swoimi danymi';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Śledź swoje cele na stronie głównej';

  @override
  String get deleteRecording => 'Usuń nagranie';

  @override
  String get thisCannotBeUndone => 'Tej operacji nie można cofnąć.';

  @override
  String get sdCard => 'Karta SD';

  @override
  String get fromSd => 'Z karty SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Szybki transfer';

  @override
  String get syncingStatus => 'Synchronizacja';

  @override
  String get failedStatus => 'Niepowodzenie';

  @override
  String etaLabel(String time) {
    return 'Szacowany czas: $time';
  }

  @override
  String get transferMethod => 'Metoda transferu';

  @override
  String get fast => 'Szybki';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Anuluj synchronizację';

  @override
  String get cancelSyncMessage => 'Już pobrane dane zostaną zachowane. Możesz wznowić później.';

  @override
  String get syncCancelled => 'Synchronizacja anulowana';

  @override
  String get deleteProcessedFiles => 'Delete Processed Files';

  @override
  String get processedFilesDeleted => 'Przetworzone pliki usunięte';

  @override
  String get wifiEnableFailed => 'Nie udało się włączyć WiFi na urządzeniu. Spróbuj ponownie.';

  @override
  String get deviceNoFastTransfer => 'Twoje urządzenie nie obsługuje szybkiego transferu. Użyj zamiast tego Bluetooth.';

  @override
  String get enableHotspotMessage => 'Włącz hotspot swojego telefonu i spróbuj ponownie.';

  @override
  String get transferStartFailed => 'Nie udało się rozpocząć transferu. Spróbuj ponownie.';

  @override
  String get deviceNotResponding => 'Urządzenie nie odpowiada. Spróbuj ponownie.';

  @override
  String get invalidWifiCredentials => 'Nieprawidłowe dane WiFi. Sprawdź ustawienia hotspotu.';

  @override
  String get wifiConnectionFailed => 'Połączenie WiFi nie powiodło się. Spróbuj ponownie.';

  @override
  String get sdCardProcessing => 'Przetwarzanie karty SD';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Przetwarzanie $count nagrań. Pliki zostaną usunięte z karty SD po zakończeniu.';
  }

  @override
  String get process => 'Przetwórz';

  @override
  String get wifiSyncFailed => 'Synchronizacja WiFi nie powiodła się';

  @override
  String get processingFailed => 'Przetwarzanie nie powiodło się';

  @override
  String get downloadingFromSdCard => 'Pobieranie z karty SD';

  @override
  String processingProgress(int current, int total) {
    return 'Przetwarzanie $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return 'Utworzono $count rozmów';
  }

  @override
  String get internetRequired => 'Wymagane połączenie internetowe';

  @override
  String get processAudio => 'Przetwórz dźwięk';

  @override
  String get start => 'Rozpocznij';

  @override
  String get noRecordings => 'Brak nagrań';

  @override
  String get audioFromOmiWillAppearHere => 'Dźwięk z Twojego urządzenia Omi pojawi się tutaj';

  @override
  String get deleteProcessed => 'Usuń przetworzone';

  @override
  String get tryDifferentFilter => 'Wypróbuj inny filtr';

  @override
  String get recordings => 'Nagrania';

  @override
  String get enableRemindersAccess => 'Włącz dostęp do Przypomnień w Ustawieniach, aby korzystać z Przypomnień Apple';

  @override
  String todayAtTime(String time) {
    return 'Dziś o $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Wczoraj o $time';
  }

  @override
  String get lessThanAMinute => 'Mniej niż minuta';

  @override
  String estimatedMinutes(int count) {
    return '~$count min.';
  }

  @override
  String estimatedHours(int count) {
    return '~$count godz.';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Szacunkowo: $time pozostało';
  }

  @override
  String get summarizingConversation => 'Podsumowywanie rozmowy...\nMoże to potrwać kilka sekund';

  @override
  String get resummarizingConversation => 'Ponowne podsumowywanie rozmowy...\nMoże to potrwać kilka sekund';

  @override
  String get nothingInterestingRetry => 'Nie znaleziono nic interesującego,\nchcesz spróbować ponownie?';

  @override
  String get noSummaryForConversation => 'Brak podsumowania\ndla tej rozmowy.';

  @override
  String get unknownLocation => 'Nieznana lokalizacja';

  @override
  String get couldNotLoadMap => 'Nie udało się załadować mapy';

  @override
  String get triggerConversationIntegration => 'Uruchom integrację tworzenia rozmowy';

  @override
  String get webhookUrlNotSet => 'URL webhooka nie ustawiony';

  @override
  String get setWebhookUrlInSettings => 'Ustaw URL webhooka w ustawieniach programisty, aby korzystać z tej funkcji.';

  @override
  String get sendWebUrl => 'Wyślij URL strony';

  @override
  String get sendTranscript => 'Wyślij transkrypcję';

  @override
  String get sendSummary => 'Wyślij podsumowanie';

  @override
  String get debugModeDetected => 'Wykryto tryb debugowania';

  @override
  String get performanceReduced => 'Wydajność może być zmniejszona';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Automatyczne zamknięcie za $seconds sekund';
  }

  @override
  String get modelRequired => 'Wymagany model';

  @override
  String get downloadWhisperModel => 'Pobierz model whisper, aby korzystać z transkrypcji na urządzeniu';

  @override
  String get deviceNotCompatible => 'Twoje urządzenie nie jest kompatybilne z transkrypcją na urządzeniu';

  @override
  String get deviceRequirements => 'Twoje urządzenie nie spełnia wymagań transkrypcji na urządzeniu.';

  @override
  String get willLikelyCrash => 'Włączenie prawdopodobnie spowoduje awarię lub zawieszenie aplikacji.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkrypcja będzie znacznie wolniejsza i mniej dokładna.';

  @override
  String get proceedAnyway => 'Kontynuuj mimo to';

  @override
  String get olderDeviceDetected => 'Wykryto starsze urządzenie';

  @override
  String get onDeviceSlower => 'Transkrypcja na urządzeniu może być wolniejsza na tym urządzeniu.';

  @override
  String get batteryUsageHigher => 'Zużycie baterii będzie wyższe niż przy transkrypcji w chmurze.';

  @override
  String get considerOmiCloud => 'Rozważ użycie Omi Cloud dla lepszej wydajności.';

  @override
  String get highResourceUsage => 'Wysokie zużycie zasobów';

  @override
  String get onDeviceIntensive => 'Transkrypcja na urządzeniu jest wymagająca obliczeniowo.';

  @override
  String get batteryDrainIncrease => 'Zużycie baterii znacznie wzrośnie.';

  @override
  String get deviceMayWarmUp => 'Urządzenie może się nagrzać podczas dłuższego użytkowania.';

  @override
  String get speedAccuracyLower => 'Szybkość i dokładność mogą być niższe niż modeli chmurowych.';

  @override
  String get cloudProvider => 'Dostawca chmury';

  @override
  String get premiumMinutesInfo =>
      '1200 minut premium/miesiąc. Zakładka Na urządzeniu oferuje nieograniczoną darmową transkrypcję.';

  @override
  String get viewUsage => 'Zobacz wykorzystanie';

  @override
  String get localProcessingInfo =>
      'Dźwięk jest przetwarzany lokalnie. Działa offline, większa prywatność, ale zużywa więcej baterii.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Ostrzeżenie o wydajności';

  @override
  String get largeModelWarning =>
      'Ten model jest duży i może powodować awarie aplikacji lub działać bardzo wolno na urządzeniach mobilnych.';

  @override
  String get usingNativeIosSpeech => 'Używanie natywnego rozpoznawania mowy iOS';

  @override
  String get noModelDownloadRequired =>
      'Zostanie użyty natywny silnik mowy urządzenia. Pobieranie modelu nie jest wymagane.';

  @override
  String get modelReady => 'Model gotowy';

  @override
  String get redownload => 'Pobierz ponownie';

  @override
  String get doNotCloseApp => 'Proszę nie zamykać aplikacji.';

  @override
  String get downloading => 'Pobieranie...';

  @override
  String get downloadModel => 'Pobierz model';

  @override
  String estimatedSize(String size) {
    return 'Szacowany rozmiar: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Dostępne miejsce: $space';
  }

  @override
  String get notEnoughSpace => 'Ostrzeżenie: Za mało miejsca!';

  @override
  String get download => 'Pobierz';

  @override
  String downloadError(String error) {
    return 'Błąd pobierania: $error';
  }

  @override
  String get cancelled => 'Anulowano';

  @override
  String get deviceNotCompatibleTitle => 'Urządzenie niekompatybilne';

  @override
  String get deviceNotMeetRequirements => 'Twoje urządzenie nie spełnia wymagań transkrypcji na urządzeniu.';

  @override
  String get transcriptionSlowerOnDevice => 'Transkrypcja na urządzeniu może być wolniejsza na tym urządzeniu.';

  @override
  String get computationallyIntensive => 'Transkrypcja na urządzeniu jest obliczeniowo intensywna.';

  @override
  String get batteryDrainSignificantly => 'Rozładowywanie baterii znacznie wzrośnie.';

  @override
  String get premiumMinutesMonth =>
      '1200 minut premium/miesiąc. Karta Na urządzeniu oferuje nieograniczoną bezpłatną transkrypcję. ';

  @override
  String get audioProcessedLocally =>
      'Dźwięk jest przetwarzany lokalnie. Działa offline, bardziej prywatnie, ale zużywa więcej baterii.';

  @override
  String get languageLabel => 'Język';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Ten model jest duży i może spowodować awarię aplikacji lub bardzo wolne działanie na urządzeniach mobilnych.\n\nZalecane jest small lub base.';

  @override
  String get nativeEngineNoDownload =>
      'Zostanie użyty natywny silnik mowy Twojego urządzenia. Pobieranie modelu nie jest wymagane.';

  @override
  String modelReadyWithName(String model) {
    return 'Model gotowy ($model)';
  }

  @override
  String get reDownload => 'Pobierz ponownie';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Pobieranie $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Przygotowywanie $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Błąd pobierania: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Szacowany rozmiar: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Dostępne miejsce: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Wbudowana transkrypcja na żywo Omi jest zoptymalizowana dla rozmów w czasie rzeczywistym z automatycznym wykrywaniem mówców i diaryzacją.';

  @override
  String get reset => 'Resetuj';

  @override
  String get useTemplateFrom => 'Użyj szablonu z';

  @override
  String get selectProviderTemplate => 'Wybierz szablon dostawcy...';

  @override
  String get quicklyPopulateResponse => 'Szybkie wypełnienie znanym formatem odpowiedzi dostawcy';

  @override
  String get quicklyPopulateRequest => 'Szybkie wypełnienie znanym formatem żądania dostawcy';

  @override
  String get invalidJsonError => 'Nieprawidłowy JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Pobierz model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Urządzenie';

  @override
  String get chatAssistantsTitle => 'Asystenci czatu';

  @override
  String get permissionReadConversations => 'Czytaj rozmowy';

  @override
  String get permissionReadMemories => 'Czytaj wspomnienia';

  @override
  String get permissionReadTasks => 'Czytaj zadania';

  @override
  String get permissionCreateConversations => 'Twórz rozmowy';

  @override
  String get permissionCreateMemories => 'Twórz wspomnienia';

  @override
  String get permissionTypeAccess => 'Dostęp';

  @override
  String get permissionTypeCreate => 'Tworzenie';

  @override
  String get permissionTypeTrigger => 'Wyzwalacz';

  @override
  String get permissionDescReadConversations => 'Ta aplikacja może uzyskać dostęp do Twoich rozmów.';

  @override
  String get permissionDescReadMemories => 'Ta aplikacja może uzyskać dostęp do Twoich wspomnień.';

  @override
  String get permissionDescReadTasks => 'Ta aplikacja może uzyskać dostęp do Twoich zadań.';

  @override
  String get permissionDescCreateConversations => 'Ta aplikacja może tworzyć nowe rozmowy.';

  @override
  String get permissionDescCreateMemories => 'Ta aplikacja może tworzyć nowe wspomnienia.';

  @override
  String get realtimeListening => 'Nasłuchiwanie w czasie rzeczywistym';

  @override
  String get setupCompleted => 'Ukończono';

  @override
  String get pleaseSelectRating => 'Wybierz ocenę';

  @override
  String get writeReviewOptional => 'Napisz recenzję (opcjonalnie)';

  @override
  String get setupQuestionsIntro => 'Pomóż nam ulepszyć Omi, odpowiadając na kilka pytań. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Czym się zajmujesz?';

  @override
  String get setupQuestionUsage => '2. Gdzie planujesz używać swojego Omi?';

  @override
  String get setupQuestionAge => '3. Jaki jest Twój przedział wiekowy?';

  @override
  String get setupAnswerAllQuestions => 'Nie odpowiedziałeś jeszcze na wszystkie pytania! 🥺';

  @override
  String get setupSkipHelp => 'Pomiń, nie chcę pomagać :C';

  @override
  String get professionEntrepreneur => 'Przedsiębiorca';

  @override
  String get professionSoftwareEngineer => 'Programista';

  @override
  String get professionProductManager => 'Menedżer produktu';

  @override
  String get professionExecutive => 'Dyrektor';

  @override
  String get professionSales => 'Sprzedaż';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'W pracy';

  @override
  String get usageIrlEvents => 'Na wydarzeniach';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'W sytuacjach towarzyskich';

  @override
  String get usageEverywhere => 'Wszędzie';

  @override
  String get customBackendUrlTitle => 'Niestandardowy URL serwera';

  @override
  String get backendUrlLabel => 'URL serwera';

  @override
  String get saveUrlButton => 'Zapisz URL';

  @override
  String get enterBackendUrlError => 'Wprowadź URL serwera';

  @override
  String get urlMustEndWithSlashError => 'URL musi kończyć się na \"/\"';

  @override
  String get invalidUrlError => 'Wprowadź prawidłowy URL';

  @override
  String get backendUrlSavedSuccess => 'URL serwera zapisany pomyślnie!';

  @override
  String get signInTitle => 'Zaloguj się';

  @override
  String get signInButton => 'Zaloguj się';

  @override
  String get enterEmailError => 'Wprowadź swój e-mail';

  @override
  String get invalidEmailError => 'Wprowadź prawidłowy e-mail';

  @override
  String get enterPasswordError => 'Wprowadź swoje hasło';

  @override
  String get passwordMinLengthError => 'Hasło musi mieć co najmniej 8 znaków';

  @override
  String get signInSuccess => 'Logowanie pomyślne!';

  @override
  String get alreadyHaveAccountLogin => 'Masz już konto? Zaloguj się';

  @override
  String get emailLabel => 'E-mail';

  @override
  String get passwordLabel => 'Hasło';

  @override
  String get createAccountTitle => 'Utwórz konto';

  @override
  String get nameLabel => 'Imię';

  @override
  String get repeatPasswordLabel => 'Powtórz hasło';

  @override
  String get signUpButton => 'Zarejestruj się';

  @override
  String get enterNameError => 'Wprowadź swoje imię';

  @override
  String get passwordsDoNotMatch => 'Hasła nie są zgodne';

  @override
  String get signUpSuccess => 'Rejestracja pomyślna!';

  @override
  String get loadingKnowledgeGraph => 'Ładowanie grafu wiedzy...';

  @override
  String get noKnowledgeGraphYet => 'Brak grafu wiedzy';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Tworzenie grafu wiedzy ze wspomnień...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Graf wiedzy zostanie utworzony automatycznie podczas tworzenia nowych wspomnień.';

  @override
  String get buildGraphButton => 'Utwórz graf';

  @override
  String get checkOutMyMemoryGraph => 'Zobacz mój graf pamięci!';

  @override
  String get getButton => 'Pobierz';

  @override
  String openingApp(String appName) {
    return 'Otwieranie $appName...';
  }

  @override
  String get writeSomething => 'Napisz coś';

  @override
  String get submitReply => 'Wyślij odpowiedź';

  @override
  String get editYourReply => 'Edytuj odpowiedź';

  @override
  String get replyToReview => 'Odpowiedz na recenzję';

  @override
  String get rateAndReviewThisApp => 'Oceń i zrecenzuj tę aplikację';

  @override
  String get noChangesInReview => 'Brak zmian w recenzji do zaktualizowania.';

  @override
  String get cantRateWithoutInternet => 'Nie można ocenić aplikacji bez połączenia z internetem.';

  @override
  String get appAnalytics => 'Analityka aplikacji';

  @override
  String get learnMoreLink => 'dowiedz się więcej';

  @override
  String get moneyEarned => 'Zarobione pieniądze';

  @override
  String get writeYourReply => 'Napisz swoją odpowiedź...';

  @override
  String get replySentSuccessfully => 'Odpowiedź wysłana pomyślnie';

  @override
  String failedToSendReply(String error) {
    return 'Nie udało się wysłać odpowiedzi: $error';
  }

  @override
  String get send => 'Wyślij';

  @override
  String starFilter(int count) {
    return '$count gwiazdka';
  }

  @override
  String get noReviewsFound => 'Nie znaleziono recenzji';

  @override
  String get editReply => 'Edytuj odpowiedź';

  @override
  String get reply => 'Odpowiedź';

  @override
  String starFilterLabel(int count) {
    return '$count gwiazdka';
  }

  @override
  String get sharePublicLink => 'Udostępnij publiczny link';

  @override
  String get makePersonaPublic => 'Upublicznij personę';

  @override
  String get connectedKnowledgeData => 'Połączone dane wiedzy';

  @override
  String get enterName => 'Wprowadź imię';

  @override
  String get disconnectTwitter => 'Odłącz Twittera';

  @override
  String get disconnectTwitterConfirmation =>
      'Czy na pewno chcesz odłączyć swoje konto Twitter? Twoja persona nie będzie już miała dostępu do danych z Twittera.';

  @override
  String get getOmiDeviceDescription => 'Stwórz dokładniejszego klona dzięki osobistym rozmowom';

  @override
  String get getOmi => 'Zdobądź Omi';

  @override
  String get iHaveOmiDevice => 'Mam urządzenie Omi';

  @override
  String get goal => 'CEL';

  @override
  String get tapToTrackThisGoal => 'Dotknij, aby śledzić ten cel';

  @override
  String get tapToSetAGoal => 'Dotknij, aby ustawić cel';

  @override
  String get processedConversations => 'Przetworzone rozmowy';

  @override
  String get updatedConversations => 'Zaktualizowane rozmowy';

  @override
  String get newConversations => 'Nowe rozmowy';

  @override
  String get summaryTemplate => 'Szablon podsumowania';

  @override
  String get suggestedTemplates => 'Sugerowane szablony';

  @override
  String get otherTemplates => 'Inne szablony';

  @override
  String get availableTemplates => 'Dostępne szablony';

  @override
  String get getCreative => 'Bądź kreatywny';

  @override
  String get defaultLabel => 'Domyślny';

  @override
  String get lastUsedLabel => 'Ostatnio używany';

  @override
  String get setDefaultApp => 'Ustaw domyślną aplikację';

  @override
  String setDefaultAppContent(String appName) {
    return 'Ustawić $appName jako domyślną aplikację do podsumowań?\\n\\nTa aplikacja będzie automatycznie używana do wszystkich przyszłych podsumowań rozmów.';
  }

  @override
  String get setDefaultButton => 'Ustaw domyślną';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName ustawiona jako domyślna aplikacja do podsumowań';
  }

  @override
  String get createCustomTemplate => 'Utwórz własny szablon';

  @override
  String get allTemplates => 'Wszystkie szablony';

  @override
  String failedToInstallApp(String appName) {
    return 'Nie udało się zainstalować $appName. Spróbuj ponownie.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Błąd podczas instalacji $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Oznacz mówcę $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Osoba o tym imieniu już istnieje.';

  @override
  String get selectYouFromList => 'Aby oznaczyć siebie, wybierz \"Ty\" z listy.';

  @override
  String get enterPersonsName => 'Wprowadź imię osoby';

  @override
  String get addPerson => 'Dodaj osobę';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Oznacz inne segmenty od tego mówcy ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Oznacz inne segmenty';

  @override
  String get managePeople => 'Zarządzaj osobami';

  @override
  String get shareViaSms => 'Udostępnij przez SMS';

  @override
  String get selectContactsToShareSummary => 'Wybierz kontakty, aby udostępnić podsumowanie rozmowy';

  @override
  String get searchContactsHint => 'Szukaj kontaktów...';

  @override
  String contactsSelectedCount(int count) {
    return '$count wybranych';
  }

  @override
  String get clearAllSelection => 'Wyczyść wszystko';

  @override
  String get selectContactsToShare => 'Wybierz kontakty do udostępnienia';

  @override
  String shareWithContactCount(int count) {
    return 'Udostępnij $count kontaktowi';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Udostępnij $count kontaktom';
  }

  @override
  String get contactsPermissionRequired => 'Wymagane uprawnienie do kontaktów';

  @override
  String get contactsPermissionRequiredForSms => 'Aby udostępniać przez SMS, wymagane jest uprawnienie do kontaktów';

  @override
  String get grantContactsPermissionForSms => 'Proszę udzielić uprawnienia do kontaktów, aby udostępniać przez SMS';

  @override
  String get noContactsWithPhoneNumbers => 'Nie znaleziono kontaktów z numerami telefonów';

  @override
  String get noContactsMatchSearch => 'Brak kontaktów pasujących do wyszukiwania';

  @override
  String get failedToLoadContacts => 'Nie udało się załadować kontaktów';

  @override
  String get failedToPrepareConversationForSharing =>
      'Nie udało się przygotować rozmowy do udostępnienia. Spróbuj ponownie.';

  @override
  String get couldNotOpenSmsApp => 'Nie można otworzyć aplikacji SMS. Spróbuj ponownie.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Oto, o czym właśnie rozmawialiśmy: $link';
  }

  @override
  String get wifiSync => 'Synchronizacja WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item skopiowano do schowka';
  }

  @override
  String get wifiConnectionFailedTitle => 'Połączenie nie powiodło się';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Łączenie z $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Włącz WiFi $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Połącz z $deviceName';
  }

  @override
  String get recordingDetails => 'Szczegóły nagrania';

  @override
  String get storageLocationSdCard => 'Karta SD';

  @override
  String get storageLocationLimitlessPendant => 'Pendant Limitless';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (pamięć)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Przechowywane na $deviceName';
  }

  @override
  String get transferring => 'Przesyłanie...';

  @override
  String get transferRequired => 'Wymagany transfer';

  @override
  String get downloadingAudioFromSdCard => 'Pobieranie dźwięku z karty SD urządzenia';

  @override
  String get transferRequiredDescription =>
      'To nagranie jest przechowywane na karcie SD urządzenia. Prześlij je na telefon, aby odtworzyć lub udostępnić.';

  @override
  String get cancelTransfer => 'Anuluj transfer';

  @override
  String get transferToPhone => 'Prześlij na telefon';

  @override
  String get privateAndSecureOnDevice => 'Prywatne i bezpieczne na urządzeniu';

  @override
  String get recordingInfo => 'Informacje o nagraniu';

  @override
  String get transferInProgress => 'Transfer w toku...';

  @override
  String get shareRecording => 'Udostępnij nagranie';

  @override
  String get deleteRecordingConfirmation =>
      'Czy na pewno chcesz trwale usunąć to nagranie? Tej operacji nie można cofnąć.';

  @override
  String get recordingIdLabel => 'ID nagrania';

  @override
  String get dateTimeLabel => 'Data i godzina';

  @override
  String get durationLabel => 'Czas trwania';

  @override
  String get audioFormatLabel => 'Format dźwięku';

  @override
  String get storageLocationLabel => 'Lokalizacja przechowywania';

  @override
  String get estimatedSizeLabel => 'Szacowany rozmiar';

  @override
  String get deviceModelLabel => 'Model urządzenia';

  @override
  String get deviceIdLabel => 'ID urządzenia';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Przetworzono';

  @override
  String get statusUnprocessed => 'Nieprzetworzone';

  @override
  String get switchedToFastTransfer => 'Przełączono na szybki transfer';

  @override
  String get transferCompleteMessage => 'Transfer zakończony! Możesz teraz odtworzyć to nagranie.';

  @override
  String transferFailedMessage(String error) {
    return 'Transfer nie powiódł się: $error';
  }

  @override
  String get transferCancelled => 'Transfer anulowany';

  @override
  String get fastTransferEnabled => 'Szybki transfer włączony';

  @override
  String get bluetoothSyncEnabled => 'Synchronizacja Bluetooth włączona';

  @override
  String get enableFastTransfer => 'Włącz szybki transfer';

  @override
  String get fastTransferDescription =>
      'Szybki transfer używa WiFi dla ~5x szybszych prędkości. Twój telefon tymczasowo połączy się z siecią WiFi urządzenia Omi podczas transferu.';

  @override
  String get internetAccessPausedDuringTransfer => 'Dostęp do internetu jest wstrzymany podczas transferu';

  @override
  String get chooseTransferMethodDescription => 'Wybierz, jak nagrania są przesyłane z urządzenia Omi na telefon.';

  @override
  String get wifiSpeed => '~150 KB/s przez WiFi';

  @override
  String get fiveTimesFaster => '5X SZYBCIEJ';

  @override
  String get fastTransferMethodDescription =>
      'Tworzy bezpośrednie połączenie WiFi z urządzeniem Omi. Telefon tymczasowo rozłącza się z normalnym WiFi podczas transferu.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s przez BLE';

  @override
  String get bluetoothMethodDescription =>
      'Używa standardowego połączenia Bluetooth Low Energy. Wolniejsze, ale nie wpływa na połączenie WiFi.';

  @override
  String get selected => 'Wybrano';

  @override
  String get selectOption => 'Wybierz';

  @override
  String get lowBatteryAlertTitle => 'Alert niskiego poziomu baterii';

  @override
  String get lowBatteryAlertBody => 'Bateria Twojego urządzenia jest na wyczerpaniu. Czas na ładowanie! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Twoje urządzenie Omi zostało rozłączone';

  @override
  String get deviceDisconnectedNotificationBody => 'Połącz się ponownie, aby kontynuować korzystanie z Omi.';

  @override
  String get firmwareUpdateAvailable => 'Dostępna aktualizacja oprogramowania';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Dostępna jest nowa aktualizacja oprogramowania ($version) dla Twojego urządzenia Omi. Czy chcesz zaktualizować teraz?';
  }

  @override
  String get later => 'Później';

  @override
  String get appDeletedSuccessfully => 'Aplikacja została pomyślnie usunięta';

  @override
  String get appDeleteFailed => 'Nie udało się usunąć aplikacji. Spróbuj ponownie później.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Widoczność aplikacji została zmieniona pomyślnie. Może to potrwać kilka minut.';

  @override
  String get errorActivatingAppIntegration =>
      'Błąd podczas aktywacji aplikacji. Jeśli to aplikacja integracyjna, upewnij się, że konfiguracja jest zakończona.';

  @override
  String get errorUpdatingAppStatus => 'Wystąpił błąd podczas aktualizacji statusu aplikacji.';

  @override
  String get calculatingETA => 'Obliczanie...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Pozostało około $minutes minut';
  }

  @override
  String get aboutAMinuteRemaining => 'Pozostała około minuta';

  @override
  String get almostDone => 'Prawie gotowe...';

  @override
  String get omiSays => 'omi mówi';

  @override
  String get analyzingYourData => 'Analizowanie Twoich danych...';

  @override
  String migratingToProtection(String level) {
    return 'Migracja do ochrony $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Brak danych do migracji. Finalizowanie...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migrowanie $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Wszystkie obiekty zmigrowane. Finalizowanie...';

  @override
  String get migrationErrorOccurred => 'Wystąpił błąd podczas migracji. Spróbuj ponownie.';

  @override
  String get migrationComplete => 'Migracja zakończona!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Twoje dane są teraz chronione nowymi ustawieniami $level.';
  }

  @override
  String get chatsLowercase => 'czaty';

  @override
  String get dataLowercase => 'dane';

  @override
  String get fallNotificationTitle => 'Auć';

  @override
  String get fallNotificationBody => 'Czy się przewróciłeś?';

  @override
  String get importantConversationTitle => 'Ważna rozmowa';

  @override
  String get importantConversationBody => 'Właśnie odbyłeś ważną rozmowę. Dotknij, aby udostępnić podsumowanie.';

  @override
  String get templateName => 'Nazwa szablonu';

  @override
  String get templateNameHint => 'np. Ekstraktor działań ze spotkania';

  @override
  String get nameMustBeAtLeast3Characters => 'Nazwa musi mieć co najmniej 3 znaki';

  @override
  String get conversationPromptHint => 'np. Wyodrębnij zadania, podjęte decyzje i kluczowe wnioski z rozmowy.';

  @override
  String get pleaseEnterAppPrompt => 'Wprowadź podpowiedź dla aplikacji';

  @override
  String get promptMustBeAtLeast10Characters => 'Podpowiedź musi mieć co najmniej 10 znaków';

  @override
  String get anyoneCanDiscoverTemplate => 'Każdy może odkryć Twój szablon';

  @override
  String get onlyYouCanUseTemplate => 'Tylko Ty możesz używać tego szablonu';

  @override
  String get generatingDescription => 'Generowanie opisu...';

  @override
  String get creatingAppIcon => 'Tworzenie ikony aplikacji...';

  @override
  String get installingApp => 'Instalowanie aplikacji...';

  @override
  String get appCreatedAndInstalled => 'Aplikacja utworzona i zainstalowana!';

  @override
  String get appCreatedSuccessfully => 'Aplikacja utworzona pomyślnie!';

  @override
  String get failedToCreateApp => 'Nie udało się utworzyć aplikacji. Spróbuj ponownie.';

  @override
  String get addAppSelectCoreCapability => 'Wybierz jeszcze jedną główną funkcję dla swojej aplikacji';

  @override
  String get addAppSelectPaymentPlan => 'Wybierz plan płatności i wprowadź cenę aplikacji';

  @override
  String get addAppSelectCapability => 'Wybierz co najmniej jedną funkcję dla swojej aplikacji';

  @override
  String get addAppSelectLogo => 'Wybierz logo dla swojej aplikacji';

  @override
  String get addAppEnterChatPrompt => 'Wprowadź podpowiedź czatu dla swojej aplikacji';

  @override
  String get addAppEnterConversationPrompt => 'Wprowadź podpowiedź rozmowy dla swojej aplikacji';

  @override
  String get addAppSelectTriggerEvent => 'Wybierz zdarzenie wyzwalające dla swojej aplikacji';

  @override
  String get addAppEnterWebhookUrl => 'Wprowadź URL webhooka dla swojej aplikacji';

  @override
  String get addAppSelectCategory => 'Wybierz kategorię dla swojej aplikacji';

  @override
  String get addAppFillRequiredFields => 'Wypełnij poprawnie wszystkie wymagane pola';

  @override
  String get addAppUpdatedSuccess => 'Aplikacja zaktualizowana pomyślnie 🚀';

  @override
  String get addAppUpdateFailed => 'Aktualizacja nie powiodła się. Spróbuj później';

  @override
  String get addAppSubmittedSuccess => 'Aplikacja przesłana pomyślnie 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Błąd otwierania wyboru plików: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Błąd wyboru obrazu: $error';
  }

  @override
  String get addAppPhotosPermissionDenied => 'Odmowa dostępu do zdjęć. Zezwól na dostęp do zdjęć';

  @override
  String get addAppErrorSelectingImageRetry => 'Błąd wyboru obrazu. Spróbuj ponownie.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Błąd wyboru miniatury: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Błąd wyboru miniatury. Spróbuj ponownie.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Inne funkcje nie mogą być wybrane z Personą';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona nie może być wybrana z innymi funkcjami';

  @override
  String get personaTwitterHandleNotFound => 'Nie znaleziono konta Twitter';

  @override
  String get personaTwitterHandleSuspended => 'Konto Twitter jest zawieszone';

  @override
  String get personaFailedToVerifyTwitter => 'Weryfikacja konta Twitter nie powiodła się';

  @override
  String get personaFailedToFetch => 'Pobieranie persony nie powiodło się';

  @override
  String get personaFailedToCreate => 'Tworzenie persony nie powiodło się';

  @override
  String get personaConnectKnowledgeSource => 'Połącz co najmniej jedno źródło danych (Omi lub Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona zaktualizowana pomyślnie';

  @override
  String get personaFailedToUpdate => 'Aktualizacja persony nie powiodła się';

  @override
  String get personaPleaseSelectImage => 'Wybierz obraz';

  @override
  String get personaFailedToCreateTryLater => 'Tworzenie persony nie powiodło się. Spróbuj później.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Tworzenie persony nie powiodło się: $error';
  }

  @override
  String get personaFailedToEnable => 'Włączenie persony nie powiodło się';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Błąd włączania persony: $error';
  }

  @override
  String get paymentFailedToFetchCountries => 'Pobieranie obsługiwanych krajów nie powiodło się. Spróbuj później.';

  @override
  String get paymentFailedToSetDefault => 'Ustawienie domyślnej metody płatności nie powiodło się. Spróbuj później.';

  @override
  String get paymentFailedToSavePaypal => 'Zapisanie danych PayPal nie powiodło się. Spróbuj później.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktywny';

  @override
  String get paymentStatusConnected => 'Połączony';

  @override
  String get paymentStatusNotConnected => 'Niepołączony';

  @override
  String get paymentAppCost => 'Koszt aplikacji';

  @override
  String get paymentEnterValidAmount => 'Wprowadź prawidłową kwotę';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Wprowadź kwotę większą niż 0';

  @override
  String get paymentPlan => 'Plan płatności';

  @override
  String get paymentNoneSelected => 'Nie wybrano';

  @override
  String get aiGenPleaseEnterDescription => 'Wprowadź opis swojej aplikacji';

  @override
  String get aiGenCreatingAppIcon => 'Tworzenie ikony aplikacji...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Wystąpił błąd: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplikacja została utworzona!';

  @override
  String get aiGenFailedToCreateApp => 'Nie udało się utworzyć aplikacji';

  @override
  String get aiGenErrorWhileCreatingApp => 'Wystąpił błąd podczas tworzenia aplikacji';

  @override
  String get aiGenFailedToGenerateApp => 'Nie udało się wygenerować aplikacji. Spróbuj ponownie.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Nie udało się ponownie wygenerować ikony';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Najpierw wygeneruj aplikację';

  @override
  String get xHandleTitle => 'Jaki jest Twój identyfikator X?';

  @override
  String get xHandleDescription => 'Wstępnie wytrenujemy Twojego klona Omi\nna podstawie aktywności Twojego konta';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Wprowadź swój identyfikator X';

  @override
  String get xHandlePleaseEnterValid => 'Wprowadź prawidłowy identyfikator X';

  @override
  String get nextButton => 'Dalej';

  @override
  String get connectOmiDevice => 'Połącz urządzenie Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Przechodzisz z planu Unlimited na $title. Czy na pewno chcesz kontynuować?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Ulepszenie zaplanowane! Twój plan miesięczny będzie kontynuowany do końca okresu rozliczeniowego, a następnie automatycznie przełączy się na roczny.';

  @override
  String get couldNotSchedulePlanChange => 'Nie udało się zaplanować zmiany planu. Spróbuj ponownie.';

  @override
  String get subscriptionReactivatedDefault =>
      'Twoja subskrypcja została reaktywowana! Bez opłat teraz - zostaniesz obciążony na koniec bieżącego okresu.';

  @override
  String get subscriptionSuccessfulCharged => 'Subskrypcja udana! Zostałeś obciążony za nowy okres rozliczeniowy.';

  @override
  String get couldNotProcessSubscription => 'Nie udało się przetworzyć subskrypcji. Spróbuj ponownie.';

  @override
  String get couldNotLaunchUpgradePage => 'Nie udało się otworzyć strony ulepszenia. Spróbuj ponownie.';

  @override
  String get transcriptionJsonPlaceholder => 'Wklej tutaj swoją konfigurację JSON...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Błąd podczas otwierania wyboru plików: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Błąd: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Rozmowy pomyślnie połączone';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count rozmów zostało pomyślnie połączonych';
  }

  @override
  String get dailyReflectionNotificationTitle => 'Czas na codzienną refleksję';

  @override
  String get dailyReflectionNotificationBody => 'Opowiedz mi o swoim dniu';

  @override
  String get actionItemReminderTitle => 'Przypomnienie Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName odłączono';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Połącz ponownie, aby kontynuować korzystanie z urządzenia $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Zaloguj się';

  @override
  String get onboardingYourName => 'Twoje imię';

  @override
  String get onboardingLanguage => 'Język';

  @override
  String get onboardingPermissions => 'Uprawnienia';

  @override
  String get onboardingComplete => 'Gotowe';

  @override
  String get onboardingWelcomeToOmi => 'Witaj w Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Opowiedz nam o sobie';

  @override
  String get onboardingChooseYourPreference => 'Wybierz swoje preferencje';

  @override
  String get onboardingGrantRequiredAccess => 'Przyznaj wymagany dostęp';

  @override
  String get onboardingYoureAllSet => 'Wszystko gotowe';

  @override
  String get searchTranscriptOrSummary => 'Szukaj w transkrypcji lub podsumowaniu...';

  @override
  String get myGoal => 'Mój cel';

  @override
  String get appNotAvailable => 'Ups! Wygląda na to, że szukana aplikacja nie jest dostępna.';

  @override
  String get failedToConnectTodoist => 'Nie udało się połączyć z Todoist';

  @override
  String get failedToConnectAsana => 'Nie udało się połączyć z Asana';

  @override
  String get failedToConnectGoogleTasks => 'Nie udało się połączyć z Google Tasks';

  @override
  String get failedToConnectClickUp => 'Nie udało się połączyć z ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Nie udało się połączyć z $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Pomyślnie połączono z Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Nie udało się połączyć z Todoist. Spróbuj ponownie.';

  @override
  String get successfullyConnectedAsana => 'Pomyślnie połączono z Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Nie udało się połączyć z Asana. Spróbuj ponownie.';

  @override
  String get successfullyConnectedGoogleTasks => 'Pomyślnie połączono z Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Nie udało się połączyć z Google Tasks. Spróbuj ponownie.';

  @override
  String get successfullyConnectedClickUp => 'Pomyślnie połączono z ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Nie udało się połączyć z ClickUp. Spróbuj ponownie.';

  @override
  String get successfullyConnectedNotion => 'Pomyślnie połączono z Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Nie udało się odświeżyć statusu połączenia Notion.';

  @override
  String get successfullyConnectedGoogle => 'Pomyślnie połączono z Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Nie udało się odświeżyć statusu połączenia Google.';

  @override
  String get successfullyConnectedWhoop => 'Pomyślnie połączono z Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Nie udało się odświeżyć statusu połączenia Whoop.';

  @override
  String get successfullyConnectedGitHub => 'Pomyślnie połączono z GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Nie udało się odświeżyć statusu połączenia GitHub.';

  @override
  String get authFailedToSignInWithGoogle => 'Nie udało się zalogować przez Google, spróbuj ponownie.';

  @override
  String get authenticationFailed => 'Uwierzytelnianie nie powiodło się. Spróbuj ponownie.';

  @override
  String get authFailedToSignInWithApple => 'Nie udało się zalogować przez Apple, spróbuj ponownie.';

  @override
  String get authFailedToRetrieveToken => 'Nie udało się pobrać tokenu Firebase, spróbuj ponownie.';

  @override
  String get authUnexpectedErrorFirebase => 'Nieoczekiwany błąd podczas logowania, błąd Firebase, spróbuj ponownie.';

  @override
  String get authUnexpectedError => 'Nieoczekiwany błąd podczas logowania, spróbuj ponownie';

  @override
  String get authFailedToLinkGoogle => 'Nie udało się połączyć z Google, spróbuj ponownie.';

  @override
  String get authFailedToLinkApple => 'Nie udało się połączyć z Apple, spróbuj ponownie.';

  @override
  String get onboardingBluetoothRequired => 'Uprawnienie Bluetooth jest wymagane do połączenia z urządzeniem.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Uprawnienie Bluetooth odrzucone. Przyznaj uprawnienie w Preferencjach systemowych.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Status uprawnienia Bluetooth: $status. Sprawdź Preferencje systemowe.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Nie udało się sprawdzić uprawnienia Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Uprawnienie powiadomień odrzucone. Przyznaj uprawnienie w Preferencjach systemowych.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Uprawnienie powiadomień odrzucone. Przyznaj uprawnienie w Preferencje systemowe > Powiadomienia.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Status uprawnienia powiadomień: $status. Sprawdź Preferencje systemowe.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Nie udało się sprawdzić uprawnienia powiadomień: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Przyznaj uprawnienie lokalizacji w Ustawienia > Prywatność i bezpieczeństwo > Usługi lokalizacyjne';

  @override
  String get onboardingMicrophoneRequired => 'Uprawnienie mikrofonu jest wymagane do nagrywania.';

  @override
  String get onboardingMicrophoneDenied =>
      'Uprawnienie mikrofonu odrzucone. Przyznaj uprawnienie w Preferencje systemowe > Prywatność i bezpieczeństwo > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Status uprawnienia mikrofonu: $status. Sprawdź Preferencje systemowe.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Nie udało się sprawdzić uprawnienia mikrofonu: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'Uprawnienie przechwytywania ekranu jest wymagane do nagrywania dźwięku systemowego.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Uprawnienie przechwytywania ekranu odrzucone. Przyznaj uprawnienie w Preferencje systemowe > Prywatność i bezpieczeństwo > Nagrywanie ekranu.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Status uprawnienia przechwytywania ekranu: $status. Sprawdź Preferencje systemowe.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Nie udało się sprawdzić uprawnienia przechwytywania ekranu: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Uprawnienie dostępności jest wymagane do wykrywania spotkań przeglądarki.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Status uprawnienia dostępności: $status. Sprawdź Preferencje systemowe.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Nie udało się sprawdzić uprawnienia dostępności: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Przechwytywanie z kamery nie jest dostępne na tej platformie';

  @override
  String get msgCameraPermissionDenied => 'Odmowa dostępu do kamery. Proszę zezwolić na dostęp do kamery';

  @override
  String msgCameraAccessError(String error) {
    return 'Błąd dostępu do kamery: $error';
  }

  @override
  String get msgPhotoError => 'Błąd podczas robienia zdjęcia. Spróbuj ponownie.';

  @override
  String get msgMaxImagesLimit => 'Możesz wybrać maksymalnie 4 obrazy';

  @override
  String msgFilePickerError(String error) {
    return 'Błąd podczas otwierania wyboru plików: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Błąd podczas wybierania obrazów: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Odmowa dostępu do zdjęć. Proszę zezwolić na dostęp do zdjęć, aby wybrać obrazy';

  @override
  String get msgSelectImagesGenericError => 'Błąd podczas wybierania obrazów. Spróbuj ponownie.';

  @override
  String get msgMaxFilesLimit => 'Możesz wybrać maksymalnie 4 pliki';

  @override
  String msgSelectFilesError(String error) {
    return 'Błąd podczas wybierania plików: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Błąd podczas wybierania plików. Spróbuj ponownie.';

  @override
  String get msgUploadFileFailed => 'Nie udało się przesłać pliku, spróbuj ponownie później';

  @override
  String get msgReadingMemories => 'Czytanie twoich wspomnień...';

  @override
  String get msgLearningMemories => 'Uczenie się z twoich wspomnień...';

  @override
  String get msgUploadAttachedFileFailed => 'Nie udało się przesłać załączonego pliku.';

  @override
  String captureRecordingError(String error) {
    return 'Wystąpił błąd podczas nagrywania: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Nagrywanie zatrzymane: $reason. Może być konieczne ponowne podłączenie zewnętrznych wyświetlaczy lub ponowne uruchomienie nagrywania.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Wymagane pozwolenie na mikrofon';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Udziel pozwolenia na mikrofon w Preferencjach systemowych';

  @override
  String get captureScreenRecordingPermissionRequired => 'Wymagane pozwolenie na nagrywanie ekranu';

  @override
  String get captureDisplayDetectionFailed => 'Wykrywanie wyświetlacza nie powiodło się. Nagrywanie zatrzymane.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Nieprawidłowy URL webhooka bajtów audio';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl =>
      'Nieprawidłowy URL webhooka transkrypcji w czasie rzeczywistym';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Nieprawidłowy URL webhooka utworzonej konwersacji';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Nieprawidłowy URL webhooka dziennego podsumowania';

  @override
  String get devModeSettingsSaved => 'Ustawienia zapisane!';

  @override
  String get voiceFailedToTranscribe => 'Nie udało się transkrybować dźwięku';

  @override
  String get locationPermissionRequired => 'Potrzebne uprawnienie do lokalizacji';

  @override
  String get locationPermissionContent =>
      'Szybki transfer wymaga uprawnienia do lokalizacji, aby zweryfikować połączenie WiFi. Proszę przyznać uprawnienie do lokalizacji, aby kontynuować.';

  @override
  String get pdfTranscriptExport => 'Eksport transkrypcji';

  @override
  String get pdfConversationExport => 'Eksport rozmowy';

  @override
  String pdfTitleLabel(String title) {
    return 'Tytuł: $title';
  }

  @override
  String get conversationNewIndicator => 'Nowe 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count zdjęć';
  }

  @override
  String get mergingStatus => 'Łączenie...';

  @override
  String timeSecsSingular(int count) {
    return '$count sek';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count sek';
  }

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count min';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins min $secs sek';
  }

  @override
  String timeHourSingular(int count) {
    return '$count godzina';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count godzin';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours godzin $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count dzień';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count dni';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dni $hours godzin';
  }

  @override
  String timeCompactSecs(int count) {
    return '${count}s';
  }

  @override
  String timeCompactMins(int count) {
    return '${count}m';
  }

  @override
  String timeCompactMinsAndSecs(int mins, int secs) {
    return '${mins}m ${secs}s';
  }

  @override
  String timeCompactHours(int count) {
    return '${count}g';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}g ${mins}m';
  }

  @override
  String get moveToFolder => 'Przenieś do folderu';

  @override
  String get noFoldersAvailable => 'Brak dostępnych folderów';

  @override
  String get newFolder => 'Nowy folder';

  @override
  String get color => 'Kolor';

  @override
  String get waitingForDevice => 'Oczekiwanie na urządzenie...';

  @override
  String get saySomething => 'Powiedz coś...';

  @override
  String get initialisingSystemAudio => 'Inicjalizacja dźwięku systemowego';

  @override
  String get stopRecording => 'Zatrzymaj nagrywanie';

  @override
  String get continueRecording => 'Kontynuuj nagrywanie';

  @override
  String get initialisingRecorder => 'Inicjalizacja rejestratora';

  @override
  String get pauseRecording => 'Wstrzymaj nagrywanie';

  @override
  String get resumeRecording => 'Wznów nagrywanie';

  @override
  String get noDailyRecapsYet => 'Brak jeszcze dziennych podsumowań';

  @override
  String get dailyRecapsDescription => 'Twoje dzienne podsumowania pojawią się tutaj po wygenerowaniu';

  @override
  String get chooseTransferMethod => 'Wybierz metodę transferu';

  @override
  String get fastTransferSpeed => '~150 KB/s przez WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Wykryto dużą przerwę czasową ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Wykryto duże przerwy czasowe ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Urządzenie nie obsługuje synchronizacji WiFi, przełączanie na Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health nie jest dostępne na tym urządzeniu';

  @override
  String get downloadAudio => 'Pobierz dźwięk';

  @override
  String get audioDownloadSuccess => 'Dźwięk został pomyślnie pobrany';

  @override
  String get audioDownloadFailed => 'Nie udało się pobrać dźwięku';

  @override
  String get downloadingAudio => 'Pobieranie dźwięku...';

  @override
  String get shareAudio => 'Udostępnij dźwięk';

  @override
  String get preparingAudio => 'Przygotowywanie dźwięku';

  @override
  String get gettingAudioFiles => 'Pobieranie plików dźwiękowych...';

  @override
  String get downloadingAudioProgress => 'Pobieranie dźwięku';

  @override
  String get processingAudio => 'Przetwarzanie dźwięku';

  @override
  String get combiningAudioFiles => 'Łączenie plików dźwiękowych...';

  @override
  String get audioReady => 'Dźwięk gotowy';

  @override
  String get openingShareSheet => 'Otwieranie arkusza udostępniania...';

  @override
  String get audioShareFailed => 'Udostępnianie nie powiodło się';

  @override
  String get dailyRecaps => 'Podsumowania Dnia';

  @override
  String get removeFilter => 'Usuń Filtr';

  @override
  String get categoryConversationAnalysis => 'Analiza rozmów';

  @override
  String get categoryPersonalityClone => 'Klon osobowości';

  @override
  String get categoryHealth => 'Zdrowie';

  @override
  String get categoryEducation => 'Edukacja';

  @override
  String get categoryCommunication => 'Komunikacja';

  @override
  String get categoryEmotionalSupport => 'Wsparcie emocjonalne';

  @override
  String get categoryProductivity => 'Produktywność';

  @override
  String get categoryEntertainment => 'Rozrywka';

  @override
  String get categoryFinancial => 'Finanse';

  @override
  String get categoryTravel => 'Podróże';

  @override
  String get categorySafety => 'Bezpieczeństwo';

  @override
  String get categoryShopping => 'Zakupy';

  @override
  String get categorySocial => 'Społeczne';

  @override
  String get categoryNews => 'Wiadomości';

  @override
  String get categoryUtilities => 'Narzędzia';

  @override
  String get categoryOther => 'Inne';

  @override
  String get capabilityChat => 'Czat';

  @override
  String get capabilityConversations => 'Rozmowy';

  @override
  String get capabilityExternalIntegration => 'Integracja zewnętrzna';

  @override
  String get capabilityNotification => 'Powiadomienie';

  @override
  String get triggerAudioBytes => 'Bajty audio';

  @override
  String get triggerConversationCreation => 'Tworzenie rozmowy';

  @override
  String get triggerTranscriptProcessed => 'Transkrypcja przetworzona';

  @override
  String get actionCreateConversations => 'Utwórz rozmowy';

  @override
  String get actionCreateMemories => 'Utwórz wspomnienia';

  @override
  String get actionReadConversations => 'Czytaj rozmowy';

  @override
  String get actionReadMemories => 'Czytaj wspomnienia';

  @override
  String get actionReadTasks => 'Czytaj zadania';

  @override
  String get scopeUserName => 'Nazwa użytkownika';

  @override
  String get scopeUserFacts => 'Fakty o użytkowniku';

  @override
  String get scopeUserConversations => 'Rozmowy użytkownika';

  @override
  String get scopeUserChat => 'Czat użytkownika';

  @override
  String get capabilitySummary => 'Podsumowanie';

  @override
  String get capabilityFeatured => 'Polecane';

  @override
  String get capabilityTasks => 'Zadania';

  @override
  String get capabilityIntegrations => 'Integracje';

  @override
  String get categoryPersonalityClones => 'Klony osobowości';

  @override
  String get categoryProductivityLifestyle => 'Produktywność i styl życia';

  @override
  String get categorySocialEntertainment => 'Społeczne i rozrywka';

  @override
  String get categoryProductivityTools => 'Narzędzia produktywności';

  @override
  String get categoryPersonalWellness => 'Osobiste samopoczucie';

  @override
  String get rating => 'Ocena';

  @override
  String get categories => 'Kategorie';

  @override
  String get sortBy => 'Sortuj';

  @override
  String get highestRating => 'Najwyższa ocena';

  @override
  String get lowestRating => 'Najniższa ocena';

  @override
  String get resetFilters => 'Resetuj filtry';

  @override
  String get applyFilters => 'Zastosuj filtry';

  @override
  String get mostInstalls => 'Najwięcej instalacji';

  @override
  String get couldNotOpenUrl => 'Nie można otworzyć adresu URL. Spróbuj ponownie.';

  @override
  String get newTask => 'Nowe zadanie';

  @override
  String get viewAll => 'Pokaż wszystko';

  @override
  String get addTask => 'Dodaj zadanie';

  @override
  String get addMcpServer => 'Dodaj serwer MCP';

  @override
  String get connectExternalAiTools => 'Połącz zewnętrzne narzędzia AI';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return 'Pomyślnie połączono $count narzędzi';
  }

  @override
  String get mcpConnectionFailed => 'Nie udało się połączyć z serwerem MCP';

  @override
  String get authorizingMcpServer => 'Autoryzacja...';

  @override
  String get whereDidYouHearAboutOmi => 'Jak nas znalazłeś?';

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
  String get friendWordOfMouth => 'Znajomy';

  @override
  String get otherSource => 'Inne';

  @override
  String get pleaseSpecify => 'Proszę określić';

  @override
  String get event => 'Wydarzenie';

  @override
  String get coworker => 'Współpracownik';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Plik audio nie jest dostępny do odtwarzania';

  @override
  String get audioPlaybackFailed => 'Nie można odtworzyć dźwięku. Plik może być uszkodzony lub brakujący.';

  @override
  String get connectionGuide => 'Przewodnik połączenia';

  @override
  String get iveDoneThis => 'Zrobiłem to';

  @override
  String get pairNewDevice => 'Sparuj nowe urządzenie';

  @override
  String get dontSeeYourDevice => 'Nie widzisz swojego urządzenia?';

  @override
  String get reportAnIssue => 'Zgłoś problem';

  @override
  String get pairingTitleOmi => 'Włącz Omi';

  @override
  String get pairingDescOmi => 'Naciśnij i przytrzymaj urządzenie, aż zawibruje, aby je włączyć.';

  @override
  String get pairingTitleOmiDevkit => 'Przełącz Omi DevKit w tryb parowania';

  @override
  String get pairingDescOmiDevkit =>
      'Naciśnij przycisk raz, aby włączyć. LED będzie migać na fioletowo w trybie parowania.';

  @override
  String get pairingTitleOmiGlass => 'Włącz Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Naciśnij i przytrzymaj boczny przycisk przez 3 sekundy, aby włączyć.';

  @override
  String get pairingTitlePlaudNote => 'Przełącz Plaud Note w tryb parowania';

  @override
  String get pairingDescPlaudNote =>
      'Naciśnij i przytrzymaj boczny przycisk przez 2 sekundy. Czerwona dioda LED zacznie migać, gdy będzie gotowy do parowania.';

  @override
  String get pairingTitleBee => 'Przełącz Bee w tryb parowania';

  @override
  String get pairingDescBee => 'Naciśnij przycisk 5 razy z rzędu. Światło zacznie migać na niebiesko i zielono.';

  @override
  String get pairingTitleLimitless => 'Przełącz Limitless w tryb parowania';

  @override
  String get pairingDescLimitless =>
      'Gdy świeci się jakakolwiek kontrolka, naciśnij raz, a następnie naciśnij i przytrzymaj, aż urządzenie pokaże różowe światło, następnie puść.';

  @override
  String get pairingTitleFriendPendant => 'Przełącz Friend Pendant w tryb parowania';

  @override
  String get pairingDescFriendPendant =>
      'Naciśnij przycisk na wisiorku, aby go włączyć. Automatycznie przejdzie w tryb parowania.';

  @override
  String get pairingTitleFieldy => 'Przełącz Fieldy w tryb parowania';

  @override
  String get pairingDescFieldy => 'Naciśnij i przytrzymaj urządzenie, aż pojawi się światło, aby je włączyć.';

  @override
  String get pairingTitleAppleWatch => 'Połącz Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Zainstaluj i otwórz aplikację Omi na swoim Apple Watch, a następnie dotknij Połącz w aplikacji.';

  @override
  String get pairingTitleNeoOne => 'Przełącz Neo One w tryb parowania';

  @override
  String get pairingDescNeoOne =>
      'Naciśnij i przytrzymaj przycisk zasilania, aż dioda LED zacznie migać. Urządzenie będzie wykrywalne.';

  @override
  String get downloadingFromDevice => 'Pobieranie z urządzenia';

  @override
  String get reconnectingToInternet => 'Ponowne łączenie z internetem...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Przesyłanie $current z $total';
  }

  @override
  String get processedStatus => 'Przetworzono';

  @override
  String get corruptedStatus => 'Uszkodzony';

  @override
  String nPending(int count) {
    return '$count oczekujących';
  }

  @override
  String nProcessed(int count) {
    return '$count przetworzonych';
  }

  @override
  String get synced => 'Zsynchronizowano';

  @override
  String get noPendingRecordings => 'Brak oczekujących nagrań';

  @override
  String get noProcessedRecordings => 'Brak przetworzonych nagrań';

  @override
  String get pending => 'Oczekujące';

  @override
  String whatsNewInVersion(String version) {
    return 'Co nowego w $version';
  }

  @override
  String get addToYourTaskList => 'Dodać do listy zadań?';

  @override
  String get failedToCreateShareLink => 'Nie udało się utworzyć linku do udostępniania';

  @override
  String get deleteGoal => 'Usuń cel';

  @override
  String get deviceUpToDate => 'Twoje urządzenie jest aktualne';

  @override
  String get wifiConfiguration => 'Konfiguracja WiFi';

  @override
  String get wifiConfigurationSubtitle => 'Wprowadź dane WiFi, aby urządzenie mogło pobrać oprogramowanie.';

  @override
  String get networkNameSsid => 'Nazwa sieci (SSID)';

  @override
  String get enterWifiNetworkName => 'Wprowadź nazwę sieci WiFi';

  @override
  String get enterWifiPassword => 'Wprowadź hasło WiFi';

  @override
  String get appIconLabel => 'App Icon';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Oto co o Tobie wiem';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Ta mapa aktualizuje się, gdy Omi uczy się z Twoich rozmów.';

  @override
  String get apiEnvironment => 'Środowisko API';

  @override
  String get apiEnvironmentDescription => 'Wybierz serwer do połączenia';

  @override
  String get production => 'Produkcja';

  @override
  String get staging => 'Środowisko testowe';

  @override
  String get switchRequiresRestart => 'Przełączenie wymaga ponownego uruchomienia aplikacji';

  @override
  String get switchApiConfirmTitle => 'Przełącz środowisko API';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Przełączyć na $environment? Aby zmiany zaczęły obowiązywać, musisz zamknąć i ponownie otworzyć aplikację.';
  }

  @override
  String get switchAndRestart => 'Przełącz';

  @override
  String get stagingDisclaimer =>
      'Środowisko testowe może być niestabilne, mieć niespójną wydajność, a dane mogą zostać utracone. Tylko do testów.';

  @override
  String get apiEnvSavedRestartRequired => 'Zapisano. Zamknij i ponownie otwórz aplikację, aby zastosować zmiany.';

  @override
  String get shared => 'Udostępniono';

  @override
  String get onlyYouCanSeeConversation => 'Tylko Ty możesz zobaczyć tę rozmowę';

  @override
  String get anyoneWithLinkCanView => 'Każdy, kto ma link, może wyświetlić';

  @override
  String get tasksCleanTodayTitle => 'Wyczyścić dzisiejsze zadania?';

  @override
  String get tasksCleanTodayMessage => 'To usunie tylko terminy';
}
