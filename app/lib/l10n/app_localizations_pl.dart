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
  String get clearChat => 'Wyczyścić czat?';

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
  String get myApps => 'Moje Aplikacje';

  @override
  String get installedApps => 'Zainstalowane Aplikacje';

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
  String get chatTools => 'Narzędzia czatu';

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
  String get off => 'Wył.';

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
  String get urlCopied => 'URL skopiowany';

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
  String get chatToolsFooter => 'Połącz swoje aplikacje, aby wyświetlać dane i metryki w czacie.';

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
  String get noUpcomingMeetings => 'Nie znaleziono nadchodzących spotkań';

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
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName używa $codecReason. Będzie używane Omi.';
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
  String get appName => 'Nazwa aplikacji';

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
  String get speechProfileIntro => 'Omi musi poznać Twoje cele i Twój głos. Będziesz mógł to później zmodyfikować.';

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
  String get retry => 'Spróbuj ponownie';

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
  String get descriptionOptional => 'Opis (opcjonalnie)';

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
  String get conversationUrlCouldNotBeShared => 'Adres URL rozmowy nie może być udostępniony.';

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
  String get generateSummary => 'Wygeneruj podsumowanie';

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
  String get unknownDevice => 'Nieznane urządzenie';

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
  String get debugAndDiagnostics => 'Debugowanie i diagnostyka';

  @override
  String get autoDeletesAfter3Days => 'Automatyczne usuwanie po 3 dniach';

  @override
  String get helpsDiagnoseIssues => 'Pomaga diagnozować problemy';

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
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Pytania uzupełniające';

  @override
  String get suggestQuestionsAfterConversations => 'Sugeruj pytania po rozmowach';

  @override
  String get goalTracker => 'Śledzenie celów';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Codzienna refleksja';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

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
  String get current => 'Bieżący';

  @override
  String get target => 'Cel';

  @override
  String get saveGoal => 'Zapisz';

  @override
  String get goals => 'Cele';

  @override
  String get tapToAddGoal => 'Dotknij, aby dodać cel';

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
  String get dailyScoreDescription => 'Wynik, który pomaga lepiej skupić się na realizacji.';

  @override
  String get searchResults => 'Wyniki wyszukiwania';

  @override
  String get actionItems => 'Zadania do wykonania';

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
  String get all => 'Wszystkie';

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
  String installsCount(String count) {
    return '$count+ instalacji';
  }

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
  String get getOmiDevice => 'Uzyskaj urządzenie Omi';

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
      'Brak dostępnego podsumowania dla tej aplikacji. Wypróbuj inną aplikację, aby uzyskać lepsze wyniki.';

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
  String get dailySummary => 'Dzienne Podsumowanie';

  @override
  String get developer => 'Deweloper';

  @override
  String get about => 'O aplikacji';

  @override
  String get selectTime => 'Wybierz Czas';

  @override
  String get accountGroup => 'Konto';

  @override
  String get signOutQuestion => 'Wylogować?';

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
  String get dailySummaryDescription => 'Otrzymuj spersonalizowane podsumowanie rozmów';

  @override
  String get deliveryTime => 'Czas Dostawy';

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
  String get upcomingMeetings => 'NADCHODZĄCE SPOTKANIA';

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
  String get dailyReflectionDescription => 'Przypomnienie o 21:00, aby zastanowić się nad swoim dniem';

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
}
