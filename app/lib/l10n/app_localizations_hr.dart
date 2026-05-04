// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Croatian (`hr`).
class AppLocalizationsHr extends AppLocalizations {
  AppLocalizationsHr([String locale = 'hr']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Razgovor';

  @override
  String get transcriptTab => 'Transkripcija';

  @override
  String get actionItemsTab => 'Radne stavke';

  @override
  String get deleteConversationTitle => 'Obrisati razgovor?';

  @override
  String get deleteConversationMessage =>
      'Ovo će obrisati i povezane uspomene, zadatke i audio datoteke. Ova radnja se ne može poništiti.';

  @override
  String get confirm => 'Potvrdi';

  @override
  String get cancel => 'Otkaži';

  @override
  String get ok => 'U redu';

  @override
  String get delete => 'Obriši';

  @override
  String get add => 'Dodaj';

  @override
  String get update => 'Ažuriraj';

  @override
  String get save => 'Spremi';

  @override
  String get edit => 'Uredi';

  @override
  String get close => 'Zatvori';

  @override
  String get clear => 'Obriši';

  @override
  String get copyTranscript => 'Kopiraj transkripciju';

  @override
  String get copySummary => 'Kopiraj sažetak';

  @override
  String get testPrompt => 'Testiraj upit';

  @override
  String get reprocessConversation => 'Ponovno obradi razgovor';

  @override
  String get deleteConversation => 'Obriši razgovor';

  @override
  String get contentCopied => 'Sadržaj kopiran u međuspremnik';

  @override
  String get failedToUpdateStarred => 'Nije moguće ažurirati status zvjezdice.';

  @override
  String get conversationUrlNotShared => 'URL razgovora nije moguće podijeliti.';

  @override
  String get errorProcessingConversation => 'Greška pri obradi razgovora. Pokušaj kasnije.';

  @override
  String get noInternetConnection => 'Nema internetske veze';

  @override
  String get unableToDeleteConversation => 'Nije moguće obrisati razgovor';

  @override
  String get somethingWentWrong => 'Nešto je pošlo po zlu! Pokušaj kasnije.';

  @override
  String get copyErrorMessage => 'Kopiraj poruku greške';

  @override
  String get errorCopied => 'Poruka greške kopirana u međuspremnik';

  @override
  String get remaining => 'Preostalo';

  @override
  String get loading => 'Učitavanje...';

  @override
  String get loadingDuration => 'Učitavanje trajanja...';

  @override
  String secondsCount(int count) {
    return '$count sekundi';
  }

  @override
  String get people => 'Osobe';

  @override
  String get addNewPerson => 'Dodaj novu osobu';

  @override
  String get editPerson => 'Uredi osobu';

  @override
  String get createPersonHint => 'Kreiraj novu osobu i nauči Omi da prepoznaje i njihov govor!';

  @override
  String get speechProfile => 'Profil govora';

  @override
  String sampleNumber(int number) {
    return 'Uzorak $number';
  }

  @override
  String get settings => 'Postavke';

  @override
  String get language => 'Jezik';

  @override
  String get selectLanguage => 'Odaberi jezik';

  @override
  String get deleting => 'Brisanje...';

  @override
  String get pleaseCompleteAuthentication =>
      'Završi autentifikaciju u svom pregledniku. Kada završiš, vrati se u aplikaciju.';

  @override
  String get failedToStartAuthentication => 'Nije moguće započeti autentifikaciju';

  @override
  String get importStarted => 'Uvoz je započeo! Bit ćeš obaviješten/a kada je gotov.';

  @override
  String get failedToStartImport => 'Nije moguće započeti uvoz. Pokušaj ponovno.';

  @override
  String get couldNotAccessFile => 'Nije moguće pristupiti odabranoj datoteci';

  @override
  String get askOmi => 'Pitaj Omi';

  @override
  String get done => 'Gotovo';

  @override
  String get disconnected => 'Odspojena';

  @override
  String get searching => 'Pretraga...';

  @override
  String get connectDevice => 'Spoji uređaj';

  @override
  String get monthlyLimitReached => 'Dosegao si mjesečnu granicu.';

  @override
  String get checkUsage => 'Provjeri korištenje';

  @override
  String get syncingRecordings => 'Sinkronizacija snimaka';

  @override
  String get recordingsToSync => 'Snimci za sinkronizaciju';

  @override
  String get allCaughtUp => 'Sve je u redu';

  @override
  String get sync => 'Sinkroniziraj';

  @override
  String get pendantUpToDate => 'Privjesak je ažuran';

  @override
  String get allRecordingsSynced => 'Svi su snimci sinkronizirani';

  @override
  String get syncingInProgress => 'Sinkronizacija je u tijeku';

  @override
  String get readyToSync => 'Spremno za sinkronizaciju';

  @override
  String get tapSyncToStart => 'Dodirnite Sinkroniziraj za početak';

  @override
  String get pendantNotConnected => 'Privjesak nije spojen. Spoji se za sinkronizaciju.';

  @override
  String get everythingSynced => 'Sve je već sinkronizirano.';

  @override
  String get recordingsNotSynced => 'Imaš snimke koje nisu sinkronizirane.';

  @override
  String get syncingBackground => 'Nastavit ćemo sinkronizirati tvoje snimke u pozadini.';

  @override
  String get noConversationsYet => 'Nema razgovora još';

  @override
  String get noStarredConversations => 'Nema zvjezdanih razgovora';

  @override
  String get starConversationHint =>
      'Ako želiš označiti razgovor zvjezdicom, otvori ga i dodirnite ikonu zvjezdice u zaglavlju.';

  @override
  String get searchConversations => 'Pretraži razgovore...';

  @override
  String selectedCount(int count, Object s) {
    return '$count odabrano';
  }

  @override
  String get merge => 'Spoji';

  @override
  String get mergeConversations => 'Spoji razgovore';

  @override
  String mergeConversationsMessage(int count) {
    return 'Ovo će kombinirati $count razgovora u jedan. Sav sadržaj će biti spojen i ponovno generiran.';
  }

  @override
  String get mergingInBackground => 'Spajanje u pozadini. Ovo može potrajati.';

  @override
  String get failedToStartMerge => 'Nije moguće započeti spajanje';

  @override
  String get askAnything => 'Pitaj bilo što';

  @override
  String get noMessagesYet => 'Nema poruka još!\nZašto ne započneš razgovor?';

  @override
  String get deletingMessages => 'Brisanje tvojih poruka iz Omi memorije...';

  @override
  String get messageCopied => '✨ Poruka kopirana u međuspremnik';

  @override
  String get cannotReportOwnMessage => 'Ne možeš prijaviti svoje poruke.';

  @override
  String get reportMessage => 'Prijavi poruku';

  @override
  String get reportMessageConfirm => 'Jesi li siguran/a da želiš prijaviti ovu poruku?';

  @override
  String get messageReported => 'Poruka je uspješno prijavljena.';

  @override
  String get thankYouFeedback => 'Hvala na povratnoj informaciji!';

  @override
  String get clearChat => 'Obriši razgovor';

  @override
  String get clearChatConfirm => 'Jesi li siguran/a da želiš obrisati razgovor? Ova radnja se ne može poništiti.';

  @override
  String get maxFilesLimit => 'Možeš prenijeti samo 4 datoteke odjednom';

  @override
  String get chatWithOmi => 'Razgovaraj s Omi';

  @override
  String get apps => 'Aplikacije';

  @override
  String get noAppsFound => 'Nema pronađenih aplikacija';

  @override
  String get tryAdjustingSearch => 'Pokušaj prilagoditi pretragu ili filtere';

  @override
  String get createYourOwnApp => 'Kreiraj vlastitu aplikaciju';

  @override
  String get buildAndShareApp => 'Izgradi i dijeli vlastitu aplikaciju';

  @override
  String get searchApps => 'Pretraži aplikacije...';

  @override
  String get myApps => 'Moje aplikacije';

  @override
  String get installedApps => 'Instalirane aplikacije';

  @override
  String get unableToFetchApps => 'Nije moguće preuzeti aplikacije :(\n\nProvjeri internetsku vezu i pokušaj ponovno.';

  @override
  String get aboutOmi => 'O Omi';

  @override
  String get privacyPolicy => 'Politika privatnosti';

  @override
  String get visitWebsite => 'Posjetite web stranicu';

  @override
  String get helpOrInquiries => 'Trebate pomoć ili imate pitanja?';

  @override
  String get joinCommunity => 'Pridruži se zajednici!';

  @override
  String get membersAndCounting => '8000+ članova i broj raste.';

  @override
  String get deleteAccountTitle => 'Obriši račun';

  @override
  String get deleteAccountConfirm => 'Jesi li siguran/a da želiš obrisati svoj račun?';

  @override
  String get cannotBeUndone => 'Ovo se ne može poništiti.';

  @override
  String get allDataErased => 'Sve tvoje uspomene i razgovori bit će trajno obrisani.';

  @override
  String get appsDisconnected => 'Tvoje aplikacije i integracije bit će odspojene odmah.';

  @override
  String get exportBeforeDelete =>
      'Možeš izvesti podatke prije brisanja računa, ali nakon što budeš obrisao/a, ne mogu se vratiti.';

  @override
  String get deleteAccountCheckbox =>
      'Razumijem da je brisanje mog računa trajno i svi podaci, uključujući uspomene i razgovore, bit će trajno izbrisani i ne mogu se vratiti.';

  @override
  String get areYouSure => 'Jesi li siguran/a?';

  @override
  String get deleteAccountFinal =>
      'Ova radnja je nepovratna i trajno će obrisati tvoj račun i sve povezane podatke. Jesi li siguran/a da želiš nastaviti?';

  @override
  String get deleteNow => 'Obriši sada';

  @override
  String get goBack => 'Vrati se';

  @override
  String get checkBoxToConfirm =>
      'Potvrdi polje kako bi potvrdio/a da razumiješ da je brisanje tvog računa trajno i nepovratno.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Ime';

  @override
  String get email => 'E-pošta';

  @override
  String get customVocabulary => 'Prilagođeni rječnik';

  @override
  String get identifyingOthers => 'Prepoznavanje ostalih';

  @override
  String get paymentMethods => 'Načini plaćanja';

  @override
  String get conversationDisplay => 'Prikaz razgovora';

  @override
  String get dataPrivacy => 'Privatnost podataka';

  @override
  String get userId => 'ID korisnika';

  @override
  String get notSet => 'Nije postavljeno';

  @override
  String get userIdCopied => 'ID korisnika kopiran u međuspremnik';

  @override
  String get systemDefault => 'Zadana vrijednost sustava';

  @override
  String get planAndUsage => 'Plan i korištenje';

  @override
  String get offlineSync => 'Offline sinkronizacija';

  @override
  String get deviceSettings => 'Postavke uređaja';

  @override
  String get integrations => 'Integracije';

  @override
  String get feedbackBug => 'Povratna informacija / Greška';

  @override
  String get helpCenter => 'Centar za pomoć';

  @override
  String get developerSettings => 'Razvojne postavke';

  @override
  String get getOmiForMac => 'Preuzmi Omi za Mac';

  @override
  String get referralProgram => 'Program preporuke';

  @override
  String get signOut => 'Odjavi se';

  @override
  String get appAndDeviceCopied => 'Detalji aplikacije i uređaja kopirani';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Tvoja privatnost, tvoja kontrola';

  @override
  String get privacyIntro =>
      'U Omi smo posvećeni zaštiti tvoje privatnosti. Ova stranica ti omogućava kontrolu kako se tvoji podaci spremi i koriste.';

  @override
  String get learnMore => 'Saznaj više...';

  @override
  String get dataProtectionLevel => 'Razina zaštite podataka';

  @override
  String get dataProtectionDesc =>
      'Tvoji podaci su zaštićeni po zadanoj postavci snažnom enkripcijom. Pregled svojih postavki i budućih opcija privatnosti ispod.';

  @override
  String get appAccess => 'Pristup aplikacije';

  @override
  String get appAccessDesc =>
      'Sljedeće aplikacije mogu pristupiti tvojim podacima. Dodirnite aplikaciju za upravljanje dozvolama.';

  @override
  String get noAppsExternalAccess => 'Nijedna instalirana aplikacija nema vanjski pristup tvojim podacima.';

  @override
  String get deviceName => 'Ime uređaja';

  @override
  String get deviceId => 'ID uređaja';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sinkronizacija SD kartice';

  @override
  String get hardwareRevision => 'Verzija hardvera';

  @override
  String get modelNumber => 'Broj modela';

  @override
  String get manufacturer => 'Proizvodač';

  @override
  String get doubleTap => 'Dvostruki dodir';

  @override
  String get ledBrightness => 'Svjetlina LED-a';

  @override
  String get micGain => 'Pojačanje mikrofona';

  @override
  String get disconnect => 'Odspoji';

  @override
  String get forgetDevice => 'Zaboravi uređaj';

  @override
  String get chargingIssues => 'Problemi s punjenjem';

  @override
  String get disconnectDevice => 'Odspoji uređaj';

  @override
  String get unpairDevice => 'Ukloni uređaj';

  @override
  String get unpairAndForget => 'Ukloni i zaboravi uređaj';

  @override
  String get deviceDisconnectedMessage => 'Tvoj Omi je odspojen 😔';

  @override
  String get deviceUnpairedMessage =>
      'Uređaj je uklonjen. Idi na Postavke > Bluetooth i zaboravi uređaj kako bi završio uklanjanje.';

  @override
  String get unpairDialogTitle => 'Ukloni uređaj';

  @override
  String get unpairDialogMessage =>
      'Ovo će ukloniti uređaj kako bi se mogao spajati na drugi telefon. Trebat će ti ići na Postavke > Bluetooth i zaboraviti uređaj kako bi završio proces.';

  @override
  String get deviceNotConnected => 'Uređaj nije spojen';

  @override
  String get connectDeviceMessage => 'Spoji svoj Omi uređaj za pristup\npostavkama uređaja i prilagodbi';

  @override
  String get deviceInfoSection => 'Informacije o uređaju';

  @override
  String get customizationSection => 'Prilagodba';

  @override
  String get hardwareSection => 'Hardver';

  @override
  String get v2Undetected => 'V2 nije detektiran';

  @override
  String get v2UndetectedMessage =>
      'Vidimo da imaš V1 uređaj ili da tvoj uređaj nije spojen. Funkcionalnost SD kartice dostupna je samo za V2 uređaje.';

  @override
  String get endConversation => 'Završi razgovor';

  @override
  String get pauseResume => 'Pauziraj/Nastavi';

  @override
  String get starConversation => 'Označi razgovor zvjezdicom';

  @override
  String get doubleTapAction => 'Radnja dvostrukog dodira';

  @override
  String get endAndProcess => 'Završi i obradi razgovor';

  @override
  String get pauseResumeRecording => 'Pauziraj/Nastavi snimanje';

  @override
  String get starOngoing => 'Označi trenutni razgovor zvjezdicom';

  @override
  String get off => 'Isključeno';

  @override
  String get max => 'Maks';

  @override
  String get mute => 'Isključi zvuk';

  @override
  String get quiet => 'Tiho';

  @override
  String get normal => 'Normalno';

  @override
  String get high => 'Visoko';

  @override
  String get micGainDescMuted => 'Mikrofon je isključen';

  @override
  String get micGainDescLow => 'Vrlo tiho - za glasne okoline';

  @override
  String get micGainDescModerate => 'Tiho - za umjerenu buku';

  @override
  String get micGainDescNeutral => 'Neutralno - balansirano snimanje';

  @override
  String get micGainDescSlightlyBoosted => 'Blago pojačano - normalna upotreba';

  @override
  String get micGainDescBoosted => 'Pojačano - za tihe okoline';

  @override
  String get micGainDescHigh => 'Visoko - za udaljene ili tihe glasove';

  @override
  String get micGainDescVeryHigh => 'Vrlo visoko - za vrlo tihe izvore';

  @override
  String get micGainDescMax => 'Maksimalno - koristi s oprezom';

  @override
  String get developerSettingsTitle => 'Razvojne postavke';

  @override
  String get saving => 'Spremanje...';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkripcija';

  @override
  String get transcriptionConfig => 'Konfiguriraj pružatelja STT-a';

  @override
  String get conversationTimeout => 'Vremensko ograničenje razgovora';

  @override
  String get conversationTimeoutConfig => 'Postavi kada se razgovori automatski završavaju';

  @override
  String get importData => 'Uvezi podatke';

  @override
  String get importDataConfig => 'Uvezi podatke iz drugih izvora';

  @override
  String get debugDiagnostics => 'Otklanjanje grešaka i dijagnostika';

  @override
  String get endpointUrl => 'URL krajnje točke';

  @override
  String get noApiKeys => 'Nema API ključeva još';

  @override
  String get createKeyToStart => 'Kreiraj ključ za početak';

  @override
  String get createKey => 'Kreiraj ključ';

  @override
  String get docs => 'Dokumentacija';

  @override
  String get yourOmiInsights => 'Tvoji Omi uvidi';

  @override
  String get today => 'Danas';

  @override
  String get thisMonth => 'Ovaj mjesec';

  @override
  String get thisYear => 'Ova godina';

  @override
  String get allTime => 'Sve vrijeme';

  @override
  String get noActivityYet => 'Nema aktivnosti još';

  @override
  String get startConversationToSeeInsights => 'Započni razgovor s Omi\nda vidiš svoje uvide o korištenju ovdje.';

  @override
  String get listening => 'Slušanje';

  @override
  String get listeningSubtitle => 'Ukupno vrijeme koje je Omi aktivno slušao.';

  @override
  String get understanding => 'Razumijevanje';

  @override
  String get understandingSubtitle => 'Riječi razumljene iz tvojih razgovora.';

  @override
  String get providing => 'Pružanje';

  @override
  String get providingSubtitle => 'Radne stavke i napomene automatski zabilježene.';

  @override
  String get remembering => 'Pamćenje';

  @override
  String get rememberingSubtitle => 'Činjenice i detalji zapamćeni za tebe.';

  @override
  String get unlimitedPlan => 'Neograničeni plan';

  @override
  String get managePlan => 'Upravljaj planom';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Tvoj plan će biti otkazan $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Tvoj plan se obnavlja $date.';
  }

  @override
  String get basicPlan => 'Besplatni plan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used od $limit min iskorišteno';
  }

  @override
  String get upgrade => 'Nadogradi';

  @override
  String get upgradeToUnlimited => 'Nadogradi na neograničeno';

  @override
  String basicPlanDesc(int limit) {
    return 'Tvoj plan uključuje $limit besplatnih minuta po mjesecu. Nadogradi se na neograničeno.';
  }

  @override
  String get shareStatsMessage =>
      'Dijeljenje mojih Omi statistike! (omi.me - tvoj AI asistent koji je uvijek dostupan)';

  @override
  String get sharePeriodToday => 'Danas, omi je:';

  @override
  String get sharePeriodMonth => 'Ovaj mjesec, omi je:';

  @override
  String get sharePeriodYear => 'Ove godine, omi je:';

  @override
  String get sharePeriodAllTime => 'Do sada, omi je:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Slušao $minutes minuta';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Razumio $words riječi';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Dao $count uvida';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Zapamtio $count uspomena';
  }

  @override
  String get debugLogs => 'Zapisnici otklanjanja grešaka';

  @override
  String get debugLogsAutoDelete => 'Automatski se briše nakon 3 dana.';

  @override
  String get debugLogsDesc => 'Pomaže u dijagnozi problema';

  @override
  String get noLogFilesFound => 'Nema pronađenih datoteka zapisnika.';

  @override
  String get omiDebugLog => 'Omi zapisnik otklanjanja grešaka';

  @override
  String get logShared => 'Zapisnik je dijeljen';

  @override
  String get selectLogFile => 'Odaberi datoteku zapisnika';

  @override
  String get shareLogs => 'Dijeli zapisnike';

  @override
  String get debugLogCleared => 'Zapisnik otklanjanja grešaka je obrisan';

  @override
  String get exportStarted => 'Izvoz je započeo. Ovo može potrajati nekoliko sekundi...';

  @override
  String get exportAllData => 'Izvezi sve podatke';

  @override
  String get exportDataDesc => 'Izvezi razgovore u JSON datoteku';

  @override
  String get exportedConversations => 'Izvezeni razgovori iz Omi';

  @override
  String get exportShared => 'Izvoz je dijeljen';

  @override
  String get deleteKnowledgeGraphTitle => 'Obrisati graf znanja?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Ovo će obrisati sve izvedene podatke grafa znanja (čvorove i veze). Tvoje izvorne uspomene će ostati sigurne. Graf će biti ponovno izgrađen s vremenom ili na sljedeći zahtjev.';

  @override
  String get knowledgeGraphDeleted => 'Graf znanja je obrisan';

  @override
  String deleteGraphFailed(String error) {
    return 'Nije moguće obrisati graf: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Obriši graf znanja';

  @override
  String get deleteKnowledgeGraphDesc => 'Obriši sve čvorove i veze';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCPServer';

  @override
  String get mcpServerDesc => 'Spoji AI asistente tvojim podacima';

  @override
  String get serverUrl => 'URL servera';

  @override
  String get urlCopied => 'URL kopiran';

  @override
  String get apiKeyAuth => 'API ključ autentifikacije';

  @override
  String get header => 'Zaglavlje';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID klijenta';

  @override
  String get clientSecret => 'Tajni ključ klijenta';

  @override
  String get useMcpApiKey => 'Koristi svoj MCP API ključ';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Događaji razgovora';

  @override
  String get newConversationCreated => 'Novi razgovor kreiran';

  @override
  String get realtimeTranscript => 'Transkripcija u stvarnom vremenu';

  @override
  String get transcriptReceived => 'Transkripcija primljena';

  @override
  String get audioBytes => 'Audio bajtovi';

  @override
  String get audioDataReceived => 'Audio podaci primljeni';

  @override
  String get intervalSeconds => 'Interval (sekunde)';

  @override
  String get daySummary => 'Sažetak dana';

  @override
  String get summaryGenerated => 'Sažetak generiran';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Dodaj u claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopiraj konfiguraciju';

  @override
  String get configCopied => 'Konfiguracija kopirana u međuspremnik';

  @override
  String get listeningMins => 'Slušanje (min)';

  @override
  String get understandingWords => 'Razumijevanje (riječi)';

  @override
  String get insights => 'Uvidi';

  @override
  String get memories => 'Uspomene';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used od $limit min korišteno ovaj mjesec';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used od $limit riječi korišteno ovaj mjesec';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used od $limit uvida dobiveno ovaj mjesec';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used od $limit uspomena kreirano ovaj mjesec';
  }

  @override
  String get visibility => 'Vidljivost';

  @override
  String get visibilitySubtitle => 'Kontroliraj koji razgovori se pojavljuju u tvojoj listi';

  @override
  String get showShortConversations => 'Prikaži kratke razgovore';

  @override
  String get showShortConversationsDesc => 'Prikaži razgovore kraće od praga';

  @override
  String get showDiscardedConversations => 'Prikaži odbijene razgovore';

  @override
  String get showDiscardedConversationsDesc => 'Uključi razgovore označene kao odbijeni';

  @override
  String get shortConversationThreshold => 'Prag kratkog razgovora';

  @override
  String get shortConversationThresholdSubtitle =>
      'Razgovori kraći od toga će biti skriveni osim ako nisu omogućeni gore';

  @override
  String get durationThreshold => 'Prag trajanja';

  @override
  String get durationThresholdDesc => 'Skrij razgovore kraće od toga';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Prilagođeni rječnik';

  @override
  String get addWords => 'Dodaj riječi';

  @override
  String get addWordsDesc => 'Imena, izrazi ili neobične riječi';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Spoji';

  @override
  String get comingSoon => 'Dolazak uskoro';

  @override
  String get integrationsFooter => 'Spoji tvoje aplikacije kako bi vidio podatke i metrike u razgovoru.';

  @override
  String get completeAuthInBrowser => 'Završi autentifikaciju u svom pregledniku. Kada završiš, vrati se u aplikaciju.';

  @override
  String failedToStartAuth(String appName) {
    return 'Nije moguće započeti autentifikaciju za $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Odspoji $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Jesi li siguran/a da želiš odspojiti se od $appName? Možeš se ponovno spojiti bilo kada.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Odspojen/a od $appName';
  }

  @override
  String get failedToDisconnect => 'Nije moguće odspojiti se';

  @override
  String connectTo(String appName) {
    return 'Spoji se na $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Trebat će ti autorizirati Omi da pristupi tvojim $appName podacima. Ovo će otvoriti tvoj preglednik za autentifikaciju.';
  }

  @override
  String get continueAction => 'Nastavi';

  @override
  String get languageTitle => 'Jezik';

  @override
  String get primaryLanguage => 'Primarni jezik';

  @override
  String get automaticTranslation => 'Automatski prijevod';

  @override
  String get detectLanguages => 'Detektiraj 10+ jezika';

  @override
  String get authorizeSavingRecordings => 'Autoriziraj spremanje snimaka';

  @override
  String get thanksForAuthorizing => 'Hvala što si autorizirao/a!';

  @override
  String get needYourPermission => 'Trebamo tvoju dozvolu';

  @override
  String get alreadyGavePermission =>
      'Već si nam dao/dala dozvolu da spremi tvoje snimke. Evo podsjetnika zašto trebamo:';

  @override
  String get wouldLikePermission => 'Željeli bi tvoju dozvolu da spremi tvoje snimke glasa. Evo zašto:';

  @override
  String get improveSpeechProfile => 'Poboljšaj svoj profil govora';

  @override
  String get improveSpeechProfileDesc =>
      'Koristimo snimke da dodatno treniramo i poboljšamo tvoj osobni profil govora.';

  @override
  String get trainFamilyProfiles => 'Treniraj profile za prijatelje i obitelj';

  @override
  String get trainFamilyProfilesDesc =>
      'Tvoji snimci nam pomažu da prepoznamo i kreiramo profile za tvoje prijatelje i obitelj.';

  @override
  String get enhanceTranscriptAccuracy => 'Poboljšaj točnost transkripcije';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Kako se naš model poboljšava, možemo pružiti bolje rezultate transkripcije za tvoje snimke.';

  @override
  String get legalNotice =>
      'Pravna napomena: Zakonitost snimanja i spremanja podataka o glasu može varirati ovisno o tvojoj lokaciji i kako koristiš ovu funkciju. Tvoja je odgovornost osigurati sukladnost s lokalnim zakonima i propisima.';

  @override
  String get alreadyAuthorized => 'Već autoriziran/a';

  @override
  String get authorize => 'Autoriziraj';

  @override
  String get revokeAuthorization => 'Opozovi autorizaciju';

  @override
  String get authorizationSuccessful => 'Autorizacija je uspješna!';

  @override
  String get failedToAuthorize => 'Autorizacija nije uspjela. Pokušajte ponovno.';

  @override
  String get authorizationRevoked => 'Autorizacija opozvana.';

  @override
  String get recordingsDeleted => 'Snimke obrisane.';

  @override
  String get failedToRevoke => 'Opozivanje autorizacije nije uspjelo. Pokušajte ponovno.';

  @override
  String get permissionRevokedTitle => 'Dozvola Opozvana';

  @override
  String get permissionRevokedMessage => 'Želite li da obriš sve vaše postojeće snimke?';

  @override
  String get yes => 'Da';

  @override
  String get editName => 'Uredi Ime';

  @override
  String get howShouldOmiCallYou => 'Kako vas Omi trebao/trebala zvati?';

  @override
  String get enterYourName => 'Unesite svoje ime';

  @override
  String get nameCannotBeEmpty => 'Ime ne može biti prazno';

  @override
  String get nameUpdatedSuccessfully => 'Ime uspješno ažurirano!';

  @override
  String get calendarSettings => 'Postavke kalendara';

  @override
  String get calendarProviders => 'Pružatelji Kalendara';

  @override
  String get macOsCalendar => 'macOS Kalendar';

  @override
  String get connectMacOsCalendar => 'Povežite svoj lokalni macOS kalendar';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sinkronizirajte se sa vašim Google računom';

  @override
  String get showMeetingsMenuBar => 'Prikaži nadolazeće sastanke u traci izbornika';

  @override
  String get showMeetingsMenuBarDesc =>
      'Prikazuje vaš sljedeći sastanak i vrijeme do njegovog početka u macOS traci izbornika';

  @override
  String get showEventsNoParticipants => 'Prikaži događaje bez sudionika';

  @override
  String get showEventsNoParticipantsDesc =>
      'Kada je omogućeno, Coming Up prikazuje događaje bez sudionika ili video veze.';

  @override
  String get yourMeetings => 'Vaši Sastanci';

  @override
  String get refresh => 'Osvježi';

  @override
  String get noUpcomingMeetings => 'Nema nadolazećih sastanaka';

  @override
  String get checkingNextDays => 'Provjera sljedećih 30 dana';

  @override
  String get tomorrow => 'Sutra';

  @override
  String get googleCalendarComingSoon => 'Integracija Google Calendara dolazi uskoro!';

  @override
  String connectedAsUser(String userId) {
    return 'Prijavljen kao korisnik: $userId';
  }

  @override
  String get defaultWorkspace => 'Zadana Radna Površina';

  @override
  String get tasksCreatedInWorkspace => 'Zadaci će biti stvoreni u ovoj radnoj površini';

  @override
  String get defaultProjectOptional => 'Zadani Projekt (Neobavezno)';

  @override
  String get leaveUnselectedTasks => 'Ostavite neodabrano da stvorite zadatke bez projekta';

  @override
  String get noProjectsInWorkspace => 'Nema pronađenih projekata u ovoj radnoj površini';

  @override
  String get conversationTimeoutDesc => 'Odaberite koliko dugo čekati u tišini prije automatskog završetka razgovora:';

  @override
  String get timeout2Minutes => '2 minute';

  @override
  String get timeout2MinutesDesc => 'Završi razgovor nakon 2 minute tišine';

  @override
  String get timeout5Minutes => '5 minuta';

  @override
  String get timeout5MinutesDesc => 'Završi razgovor nakon 5 minuta tišine';

  @override
  String get timeout10Minutes => '10 minuta';

  @override
  String get timeout10MinutesDesc => 'Završi razgovor nakon 10 minuta tišine';

  @override
  String get timeout30Minutes => '30 minuta';

  @override
  String get timeout30MinutesDesc => 'Završi razgovor nakon 30 minuta tišine';

  @override
  String get timeout4Hours => '4 sata';

  @override
  String get timeout4HoursDesc => 'Završi razgovor nakon 4 sata tišine';

  @override
  String get conversationEndAfterHours => 'Razgovori će se sada završiti nakon 4 sata tišine';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Razgovori će se sada završiti nakon $minutes minute(a) tišine';
  }

  @override
  String get tellUsPrimaryLanguage => 'Recite nam gdje je vaš primarni jezik';

  @override
  String get languageForTranscription => 'Postavite svoj jezik za precizniju transkripciju i personalizirano iskustvo.';

  @override
  String get singleLanguageModeInfo => 'Jednojezični način je omogućen. Prijevod je onemogućen za veću točnost.';

  @override
  String get searchLanguageHint => 'Pretraži jezik po imenu ili kodu';

  @override
  String get noLanguagesFound => 'Nema pronađenih jezika';

  @override
  String get skip => 'Preskoči';

  @override
  String languageSetTo(String language) {
    return 'Jezik postavljen na $language';
  }

  @override
  String get failedToSetLanguage => 'Postavljanje jezika nije uspjelo';

  @override
  String appSettings(String appName) {
    return 'Postavke $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Prekini vezu sa $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Ovo će ukloniti vašu $appName autentifikaciju. Trebat ćete se ponovno povezati da je koristite.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Povezano sa $appName';
  }

  @override
  String get account => 'Račun';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Vaši stavci za akciju će biti sinkronizirani sa vašim $appName računom';
  }

  @override
  String get defaultSpace => 'Zadana Površina';

  @override
  String get selectSpaceInWorkspace => 'Odaberite površinu u vašoj radnoj površini';

  @override
  String get noSpacesInWorkspace => 'Nema pronađenih površina u ovoj radnoj površini';

  @override
  String get defaultList => 'Zadana Lista';

  @override
  String get tasksAddedToList => 'Zadaci će biti dodani na ovu listu';

  @override
  String get noListsInSpace => 'Nema pronađenih lista u ovoj površini';

  @override
  String failedToLoadRepos(String error) {
    return 'Učitavanje spremišta nije uspjelo: $error';
  }

  @override
  String get defaultRepoSaved => 'Zadano spremište je spremljeno';

  @override
  String get failedToSaveDefaultRepo => 'Spremanje zadanog spremišta nije uspjelo';

  @override
  String get defaultRepository => 'Zadano Spremište';

  @override
  String get selectDefaultRepoDesc =>
      'Odaberite zadano spremište za stvaranje problema. Ipak možete navesti različito spremište pri stvaranju problema.';

  @override
  String get noReposFound => 'Nema pronađenih spremišta';

  @override
  String get private => 'Privatno';

  @override
  String updatedDate(String date) {
    return 'Ažurirano $date';
  }

  @override
  String get yesterday => ' Yesterday';

  @override
  String daysAgo(int count) {
    return 'Prije $count dana';
  }

  @override
  String get oneWeekAgo => 'Prije 1 tjedna';

  @override
  String weeksAgo(int count) {
    return 'Prije $count tjedana';
  }

  @override
  String get oneMonthAgo => 'Prije 1 mjeseca';

  @override
  String monthsAgo(int count) {
    return 'Prije $count mjeseci';
  }

  @override
  String get issuesCreatedInRepo => 'Problemi će biti stvoreni u vašem zadanom spremištu';

  @override
  String get taskIntegrations => 'Integracije Zadataka';

  @override
  String get configureSettings => 'Konfiguriranje Postavki';

  @override
  String get completeAuthBrowser =>
      'Molimo dovršite autentifikaciju u svojem pregledniku. Kada završite, vratite se u aplikaciju.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Pokretanje $appName autentifikacije nije uspjelo';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Povežite se na $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Trebat ćete autorizirati Omi da stvara zadatke u vašem $appName računu. Ovo će otvoriti vaš preglednik za autentifikaciju.';
  }

  @override
  String get continueButton => 'Nastavi';

  @override
  String appIntegration(String appName) {
    return '$appName Integracija';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integracija sa $appName dolazi uskoro! Teško radimo da vam donesemo više mogućnosti upravljanja zadacima.';
  }

  @override
  String get gotIt => 'Razumijem';

  @override
  String get tasksExportedOneApp => 'Zadaci se mogu izvoziti na jednu aplikaciju istovremeno.';

  @override
  String get completeYourUpgrade => 'Dovršite Svoje Nadogradnje';

  @override
  String get importConfiguration => 'Uvezi Konfiguraciju';

  @override
  String get exportConfiguration => 'Izvezi konfiguraciju';

  @override
  String get bringYourOwn => 'Donesi svoje';

  @override
  String get payYourSttProvider => 'Slobodno koristi omi. Direktno plaćaš samo svojem STT pružatelju.';

  @override
  String get freeMinutesMonth => '1.200 besplatnih minuta/mjesec uključeno. Neograničeno sa ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Domaćin je obavezan';

  @override
  String get validPortRequired => 'Validan port je obavezan';

  @override
  String get validWebsocketUrlRequired => 'Validan WebSocket URL je obavezan (wss://)';

  @override
  String get apiUrlRequired => 'API URL je obavezan';

  @override
  String get apiKeyRequired => 'API ključ je obavezan';

  @override
  String get invalidJsonConfig => 'Neispravna JSON konfiguracija';

  @override
  String errorSaving(String error) {
    return 'Greška pri spremanju: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfiguracija kopirana u međuspremnik';

  @override
  String get pasteJsonConfig => 'Zalijepite vašu JSON konfiguraciju ispod:';

  @override
  String get addApiKeyAfterImport => 'Trebat ćete dodati svoj vlastiti API ključ nakon uvoza';

  @override
  String get paste => 'Zalijepi';

  @override
  String get import => 'Uvezi';

  @override
  String get invalidProviderInConfig => 'Nevalidan pružatelj u konfiguraciji';

  @override
  String importedConfig(String providerName) {
    return 'Uvezena $providerName konfiguracija';
  }

  @override
  String invalidJson(String error) {
    return 'Neispravni JSON: $error';
  }

  @override
  String get provider => 'Pružatelj';

  @override
  String get live => 'Uživo';

  @override
  String get onDevice => 'Na Uređaju';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Unesite svoju STT HTTP krajnju točku';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Unesite svoju live STT WebSocket krajnju točku';

  @override
  String get apiKey => 'API ključ';

  @override
  String get enterApiKey => 'Unesite svoj API ključ';

  @override
  String get storedLocallyNeverShared => 'Pohranjena lokalno, nikada nije dijeljena';

  @override
  String get host => 'Domaćin';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Napredne';

  @override
  String get configuration => 'Konfiguracija';

  @override
  String get requestConfiguration => 'Konfiguracija Zahtjeva';

  @override
  String get responseSchema => 'Shema Odgovora';

  @override
  String get modified => 'Izmijenjeno';

  @override
  String get resetRequestConfig => 'Resetiraj konfiguraciju zahtjeva na zadanu';

  @override
  String get logs => 'Zapisnici';

  @override
  String get logsCopied => 'Zapisnici kopirani';

  @override
  String get noLogsYet => 'Nema zapisnika još. Počnite sa snimanjem da vidite prilagođenu STT aktivnost.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device koristi $reason. Koristi se Omi.';
  }

  @override
  String get omiTranscription => 'Omi Transkripcija';

  @override
  String get bestInClassTranscription => 'Najbolja transkripcija sa nultom postavkom';

  @override
  String get instantSpeakerLabels => 'Instant oznake govornika';

  @override
  String get languageTranslation => 'Prijevod za 100+ jezika';

  @override
  String get optimizedForConversation => 'Optimizirano za razgovor';

  @override
  String get autoLanguageDetection => 'Automatska detekcija jezika';

  @override
  String get highAccuracy => 'Visoka točnost';

  @override
  String get privacyFirst => 'Privatnost na prvom mjestu';

  @override
  String get saveChanges => 'Spremi Izmjene';

  @override
  String get resetToDefault => 'Resetiraj na zadanu';

  @override
  String get viewTemplate => 'Prikaži Predložak';

  @override
  String get trySomethingLike => 'Pokušajte nešto poput...';

  @override
  String get tryIt => 'Pokušaj';

  @override
  String get creatingPlan => 'Stvaranje plana';

  @override
  String get developingLogic => 'Razvoj logike';

  @override
  String get designingApp => 'Dizajniranje aplikacije';

  @override
  String get generatingIconStep => 'Stvaranje ikone';

  @override
  String get finalTouches => 'Završni dodaci';

  @override
  String get processing => 'Obrada...';

  @override
  String get features => 'Mogućnosti';

  @override
  String get creatingYourApp => 'Stvaranje vaše aplikacije...';

  @override
  String get generatingIcon => 'Stvaranje ikone...';

  @override
  String get whatShouldWeMake => 'Što bismo trebali napraviti?';

  @override
  String get appName => 'Naziv Aplikacije';

  @override
  String get description => 'Opis';

  @override
  String get publicLabel => 'Javno';

  @override
  String get privateLabel => 'Privatno';

  @override
  String get free => 'Besplatno';

  @override
  String get perMonth => '/ Mjesec';

  @override
  String get tailoredConversationSummaries => 'Prilagođeni Sažetci Razgovora';

  @override
  String get customChatbotPersonality => 'Prilagođena Ličnost Chatbota';

  @override
  String get makePublic => 'Učini Javnim';

  @override
  String get anyoneCanDiscover => 'Svako može otkriti vašu aplikaciju';

  @override
  String get onlyYouCanUse => 'Samo vi možete koristiti ovu aplikaciju';

  @override
  String get paidApp => 'Plaćena aplikacija';

  @override
  String get usersPayToUse => 'Korisnici plaćaju da koriste vašu aplikaciju';

  @override
  String get freeForEveryone => 'Besplatno za sve';

  @override
  String get perMonthLabel => '/ mjesec';

  @override
  String get creating => 'Stvaranje...';

  @override
  String get createApp => 'Stvori Aplikaciju';

  @override
  String get searchingForDevices => 'Pretraživanje uređaja...';

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
  String get pairingSuccessful => 'SPARIVANJE USPJEŠNO';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Greška pri povezivanju sa Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Nemoj pokazati ponovno';

  @override
  String get iUnderstand => 'Razumijem';

  @override
  String get enableBluetooth => 'Omogući Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi trebaju Bluetooth da bi se spojio na tvoj prijenosni uređaj. Molimo omogući Bluetooth i pokušaj ponovno.';

  @override
  String get contactSupport => 'Kontaktiraj Podršku?';

  @override
  String get connectLater => 'Poveži se Kasnije';

  @override
  String get grantPermissions => 'Dozvoli Dozvole';

  @override
  String get backgroundActivity => 'Aktivnost u pozadini';

  @override
  String get backgroundActivityDesc => 'Dozvoli Omiju da se pokreće u pozadini za bolju stabilnost';

  @override
  String get locationAccess => 'Pristup Lokaciji';

  @override
  String get locationAccessDesc => 'Omogući pozadinski pristup lokaciji za potpuno iskustvo';

  @override
  String get notifications => 'Obavijesti';

  @override
  String get notificationsDesc => 'Omogući obavijesti da ostaneš informiran';

  @override
  String get locationServiceDisabled => 'Usluga Lokacije Onemogućena';

  @override
  String get locationServiceDisabledDesc =>
      'Usluga Lokacije je Onemogućena. Molimo idi na Postavke > Privatnost i Sigurnost > Usluge Lokacije i omogući je';

  @override
  String get backgroundLocationDenied => 'Pristup Pozadinkskoj Lokaciji Odbijen';

  @override
  String get backgroundLocationDeniedDesc =>
      'Molimo idi na postavke uređaja i postavi dozvolu lokacije na \"Uvijek Dozvoli\"';

  @override
  String get lovingOmi => 'Sviđa ti se Omi?';

  @override
  String get leaveReviewIos =>
      'Pomozi nam dosegnuti više ljudi ostavljanjem recenzije u App Store. Tvoj povratni podaci su nam veoma važni!';

  @override
  String get leaveReviewAndroid =>
      'Pomozi nam dosegnuti više ljudi ostavljanjem recenzije u Google Play Storeu. Tvoj povratni podaci su nam veoma važni!';

  @override
  String get rateOnAppStore => 'Ocijeni na App Store';

  @override
  String get rateOnGooglePlay => 'Ocijeni na Google Play';

  @override
  String get maybeLater => 'Možda kasnije';

  @override
  String get speechProfileIntro => 'Omi trebalo nauči tvoje ciljeve i tvoj glas. Moći ćeš ga later promijeniti.';

  @override
  String get getStarted => 'Počni';

  @override
  String get allDone => 'Sve gotovo!';

  @override
  String get keepGoing => 'Nastavi, odličan ti je posao';

  @override
  String get skipThisQuestion => 'Preskoči ovo pitanje';

  @override
  String get skipForNow => 'Preskoči za sada';

  @override
  String get connectionError => 'Greška Veze';

  @override
  String get connectionErrorDesc =>
      'Povezivanje sa poslužiteljem nije uspjelo. Molimo provjeri svoju internetsku vezu i pokušaj ponovno.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Nevaljana snimka otkrivena';

  @override
  String get multipleSpeakersDesc =>
      'Čini se da ima više govornika u snimci. Molimo uvjeri se da si na tihem mjestu i pokušaj ponovno.';

  @override
  String get tooShortDesc => 'Nema dovoljno otkrivenog govora. Molimo govori više i pokušaj ponovno.';

  @override
  String get invalidRecordingDesc => 'Molimo uvjeri se da govorisš najmanje 5 sekundi i ne više od 90.';

  @override
  String get areYouThere => 'Jesi li tu?';

  @override
  String get noSpeechDesc =>
      'Nismo mogli otkriti nikakav govor. Molimo govori najmanje 10 sekundi i ne više od 3 minute.';

  @override
  String get connectionLost => 'Veza Izgubljena';

  @override
  String get connectionLostDesc => 'Veza je prekinuta. Molimo provjeri svoju internetsku vezu i pokušaj ponovno.';

  @override
  String get tryAgain => 'Pokušaj Ponovno';

  @override
  String get connectOmiOmiGlass => 'Poveži Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Nastavi Bez Uređaja';

  @override
  String get permissionsRequired => 'Dozvole Obavezne';

  @override
  String get permissionsRequiredDesc =>
      'Ova aplikacija trebanju Bluetooth i Lokacija dozvole da bi ispravno funkcionirala. Molimo omogući ih u postavkama.';

  @override
  String get openSettings => 'Otvori Postavke';

  @override
  String get wantDifferentName => 'Želiš li da ide sa nečim drugačijim?';

  @override
  String get whatsYourName => 'Koje je tvoje ime?';

  @override
  String get speakTranscribeSummarize => 'Govori. Transkribiraj. Sažmi.';

  @override
  String get signInWithApple => 'Prijavi se sa Apple';

  @override
  String get signInWithGoogle => 'Prijavi se sa Google';

  @override
  String get byContinuingAgree => 'Nastavljanjem, slažeš se sa našim ';

  @override
  String get termsOfUse => 'Uvjetima Korištenja';

  @override
  String get omiYourAiCompanion => 'Omi – Tvoj AI Pratilac';

  @override
  String get captureEveryMoment => 'Uhvati svaki trenutak. Dobij AI-powered\nSažetke. Nikad više ne biraj bilješke.';

  @override
  String get appleWatchSetup => 'Postava Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Dozvola Tražena!';

  @override
  String get microphonePermission => 'Dozvola za Mikrofon';

  @override
  String get permissionGrantedNow =>
      'Dozvola dana! Sada:\n\nOtvori Omi aplikaciju na svojem satu i dodirni \"Nastavi\" ispod';

  @override
  String get needMicrophonePermission =>
      'Trebamo dozvolu za mikrofon.\n\n1. Dodirni \"Dozvoli Dozvolu\"\n2. Dozvoli na svojem iPhoneu\n3. Aplikacija sata će se zatvoriti\n4. Ponovno otvori i dodirni \"Nastavi\"';

  @override
  String get grantPermissionButton => 'Dozvoli Dozvolu';

  @override
  String get needHelp => 'Trebam Pomoć?';

  @override
  String get troubleshootingSteps =>
      'Otklanjanje Problema:\n\n1. Osiguraj da je Omi instaliran na svojem satu\n2. Otvori Omi aplikaciju na svojem satu\n3. Traži popup dozvole\n4. Dodirni \"Dozvoli\" kada se pojavi\n5. Aplikacija na твом satu će se zatvoriti - ponovno je otvori\n6. Vrati se i dodirni \"Nastavi\" na svom iPhoneu';

  @override
  String get recordingStartedSuccessfully => 'Snimanje je uspješno započeto!';

  @override
  String get permissionNotGrantedYet =>
      'Dozvola još nije data. Molimo uvjeri se da si dopustio pristup mikrofonu i ponovno otvorio aplikaciju na svojem satu.';

  @override
  String errorRequestingPermission(String error) {
    return 'Greška pri traženju dozvole: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Greška pri pokretanju snimanja: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Odaberite svoj primarni jezik';

  @override
  String get languageBenefits => 'Postavite svoj jezik za precizniju transkripciju i personalizirano iskustvo';

  @override
  String get whatsYourPrimaryLanguage => 'Koji je tvoj primarni jezik?';

  @override
  String get selectYourLanguage => 'Odaberite svoj jezik';

  @override
  String get personalGrowthJourney => 'Vaš put osobnog rasta sa AI koji sluša svaku vašu riječ.';

  @override
  String get actionItemsTitle => 'Za Napraviti';

  @override
  String get actionItemsDescription => 'Dodirni za uređivanje • Dugi pritisak za odabir • Klizi za akcije';

  @override
  String get tabToDo => 'Za Napraviti';

  @override
  String get tabDone => 'Gotovo';

  @override
  String get tabOld => 'Staro';

  @override
  String get emptyTodoMessage => '🎉 Sve je gotovo!\nNema pending stavki za akciju';

  @override
  String get emptyDoneMessage => 'Nema dovršenih stavki još';

  @override
  String get emptyOldMessage => '✅ Nema starih zadataka';

  @override
  String get noItems => 'Nema stavki';

  @override
  String get actionItemMarkedIncomplete => 'Stavka za akciju označena kao nepotpuna';

  @override
  String get actionItemCompleted => 'Stavka za akciju dovršena';

  @override
  String get deleteActionItemTitle => 'Obriši Stavku za Akciju';

  @override
  String get deleteActionItemMessage => 'Jeste li sigurni da želite obrisati ovu stavku za akciju?';

  @override
  String get deleteSelectedItemsTitle => 'Obriši Odabrane Stavke';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Stavka za akciju \"$description\" obrisana';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'Brisanje stavke za akciju nije uspjelo';

  @override
  String get failedToDeleteItems => 'Brisanje stavki nije uspjelo';

  @override
  String get failedToDeleteSomeItems => 'Brisanje nekih stavki nije uspjelo';

  @override
  String get welcomeActionItemsTitle => 'Spreman/a za Stavke za Akciju';

  @override
  String get welcomeActionItemsDescription =>
      'Tvoj AI će automatski ekstrahirati zadatke i za-napraviti stavke iz tvojih razgovora. Pojavit će se ovdje kada se stvorei.';

  @override
  String get autoExtractionFeature => 'Automatski ekstrahirano iz razgovora';

  @override
  String get editSwipeFeature => 'Dodirni za uređivanje, klizi za dovršavanje ili brisanje';

  @override
  String itemsSelected(int count) {
    return '$count odabrano';
  }

  @override
  String get selectAll => 'Odaberite sve';

  @override
  String get deleteSelected => 'Obriši odabrane';

  @override
  String get searchMemories => 'Pretraži uspomene...';

  @override
  String get memoryDeleted => 'Uspomena Obrisana.';

  @override
  String get undo => 'Vrati Unazad';

  @override
  String get noMemoriesYet => '🧠 Nema uspomena još';

  @override
  String get noAutoMemories => 'Nema automatski ekstrahiranih uspomena još';

  @override
  String get noManualMemories => 'Nema ručno stvorenih uspomena još';

  @override
  String get noMemoriesInCategories => 'Nema uspomena u ovim kategorijama';

  @override
  String get noMemoriesFound => '🔍 Nema pronađenih uspomena';

  @override
  String get addFirstMemory => 'Dodaj svoju prvu uspomenu';

  @override
  String get clearMemoryTitle => 'Očisti Omijinu Uspomenu';

  @override
  String get clearMemoryMessage =>
      'Jeste li sigurni da želite očistiti Omijinu uspomenu? Ova akcija se ne može poništiti.';

  @override
  String get clearMemoryButton => 'Očisti Uspomenu';

  @override
  String get memoryClearedSuccess => 'Omijina uspomena o tebi je očišćena';

  @override
  String get noMemoriesToDelete => 'Nema uspomena za brisanje';

  @override
  String get createMemoryTooltip => 'Stvori novu uspomenu';

  @override
  String get createActionItemTooltip => 'Stvori novu stavku za akciju';

  @override
  String get memoryManagement => 'Upravljanje Uspomenama';

  @override
  String get filterMemories => 'Filtriraj Uspomene';

  @override
  String totalMemoriesCount(int count) {
    return 'Imaš $count ukupno uspomena';
  }

  @override
  String get publicMemories => 'Javne uspomene';

  @override
  String get privateMemories => 'Privatne uspomene';

  @override
  String get makeAllPrivate => 'Učini Sve Uspomene Privatne';

  @override
  String get makeAllPublic => 'Učini Sve Uspomene Javne';

  @override
  String get deleteAllMemories => 'Obriši Sve Uspomene';

  @override
  String get allMemoriesPrivateResult => 'Sve uspomene su sada privatne';

  @override
  String get allMemoriesPublicResult => 'Sve uspomene su sada javne';

  @override
  String get newMemory => '✨ Nova Uspomena';

  @override
  String get editMemory => '✏️ Uredi Uspomenu';

  @override
  String get memoryContentHint => 'Volim jesti sladoled...';

  @override
  String get failedToSaveMemory => 'Spremanje nije uspjelo. Molimo provjeri svoju vezu.';

  @override
  String get saveMemory => 'Spremi Uspomenu';

  @override
  String get retry => 'Pokušaj ponovno';

  @override
  String get createActionItem => 'Stvori Stavku za Akciju';

  @override
  String get editActionItem => 'Uredi Stavku za Akciju';

  @override
  String get actionItemDescriptionHint => 'Što trebamo napraviti?';

  @override
  String get actionItemDescriptionEmpty => 'Opis stavke za akciju ne može biti prazan.';

  @override
  String get actionItemUpdated => 'Stavka za akciju ažurirana';

  @override
  String get failedToUpdateActionItem => 'Ažuriranje stavke za akciju nije uspjelo';

  @override
  String get actionItemCreated => 'Stavka za akciju stvorena';

  @override
  String get failedToCreateActionItem => 'Stvaranje stavke za akciju nije uspjelo';

  @override
  String get dueDate => 'Datum Dospijeća';

  @override
  String get time => 'Vrijeme';

  @override
  String get addDueDate => 'Dodaj datum dospijeća';

  @override
  String get pressDoneToSave => 'Pritisni Done za spremanje';

  @override
  String get pressDoneToCreate => 'Pritisni Done za stvaranje';

  @override
  String get filterAll => 'Sve';

  @override
  String get filterSystem => 'O Tebi';

  @override
  String get filterInteresting => 'Uvidi';

  @override
  String get filterManual => 'Ručno';

  @override
  String get completed => 'Dovršeno';

  @override
  String get markComplete => 'Označi kao Dovršeno';

  @override
  String get actionItemDeleted => 'Stavka za akciju obrisana';

  @override
  String get failedToDeleteActionItem => 'Brisanje stavke za akciju nije uspjelo';

  @override
  String get deleteActionItemConfirmTitle => 'Obriši Stavku za Akciju';

  @override
  String get deleteActionItemConfirmMessage => 'Jeste li sigurni da želite obrisati ovu stavku za akciju?';

  @override
  String get appLanguage => 'Jezik Aplikacije';

  @override
  String get appInterfaceSectionTitle => 'SUČELJE APLIKACIJE';

  @override
  String get speechTranscriptionSectionTitle => 'GOVOR I TRANSKRIPCIJA';

  @override
  String get languageSettingsHelperText =>
      'Jezičke promjene Aplikacije Meniji i gumbi. Jezični Govor utječe na to kako se vaše snimke transkribiraju.';

  @override
  String get translationNotice => 'Obavijest o Prijevodu';

  @override
  String get translationNoticeMessage =>
      'Omi prevodi razgovore u tvoj primarni jezik. Ažuriraj ga bilo kada u Postavkama → Profili.';

  @override
  String get pleaseCheckInternetConnection => 'Molimo provjeri svoju internetsku vezu i pokušaj ponovno';

  @override
  String get pleaseSelectReason => 'Molimo odaberi razlog';

  @override
  String get tellUsMoreWhatWentWrong => 'Recite nam više o tome što se događa...';

  @override
  String get selectText => 'Odaberite Tekst';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimalno $count ciljeva dopušteno';
  }

  @override
  String get conversationCannotBeMerged => 'Ovaj razgovor se ne može spojiti (zaključan ili već se spaja)';

  @override
  String get pleaseEnterFolderName => 'Molimo unesite naziv mape';

  @override
  String get failedToCreateFolder => 'Stvaranje mape nije uspjelo';

  @override
  String get failedToUpdateFolder => 'Ažuriranje mape nije uspjelo';

  @override
  String get folderName => 'Naziv mape';

  @override
  String get descriptionOptional => 'Opis (opcionalno)';

  @override
  String get failedToDeleteFolder => 'Greška pri brisanju mape';

  @override
  String get editFolder => 'Uredi mapu';

  @override
  String get deleteFolder => 'Obriši mapu';

  @override
  String get transcriptCopiedToClipboard => 'Transkript kopiran u međuspremnik';

  @override
  String get summaryCopiedToClipboard => 'Sažetak kopiran u međuspremnik';

  @override
  String get conversationUrlCouldNotBeShared => 'URL razgovora nije moguće podijeliti.';

  @override
  String get urlCopiedToClipboard => 'URL kopiran u međuspremnik';

  @override
  String get exportTranscript => 'Preuzmi transkript';

  @override
  String get exportSummary => 'Preuzmi sažetak';

  @override
  String get exportButton => 'Preuzmi';

  @override
  String get actionItemsCopiedToClipboard => 'Stavke aktivnosti kopirane u međuspremnik';

  @override
  String get summarize => 'Sažmi';

  @override
  String get generateSummary => 'Generiraj sažetak';

  @override
  String get conversationNotFoundOrDeleted => 'Razgovor nije pronađen ili je obrisan';

  @override
  String get deleteMemory => 'Obriši uspomenu';

  @override
  String get thisActionCannotBeUndone => 'Ova radnja se ne može poništiti.';

  @override
  String memoriesCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count uspomena',
      one: '1 uspomena',
      zero: '0 uspomena',
    );
    return '$_temp0';
  }

  @override
  String get noMemoriesInCategory => 'U ovoj kategoriji još nema uspomena';

  @override
  String get addYourFirstMemory => 'Dodaj svoju prvu uspomenu';

  @override
  String get firmwareDisconnectUsb => 'Isključi USB';

  @override
  String get firmwareUsbWarning => 'USB veza tijekom ažuriranja može oštetiti vaš uređaj.';

  @override
  String get firmwareBatteryAbove15 => 'Baterija iznad 15%';

  @override
  String get firmwareEnsureBattery => 'Osigurajte da vaš uređaj ima 15% baterije.';

  @override
  String get firmwareStableConnection => 'Stabilna veza';

  @override
  String get firmwareConnectWifi => 'Priključite se na WiFi ili mobilnu mrežu.';

  @override
  String failedToStartUpdate(String error) {
    return 'Greška pri pokretanju ažuriranja: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Prije ažuriranja, osigurajte:';

  @override
  String get confirmed => 'Potvrđeno!';

  @override
  String get release => 'Izdanje';

  @override
  String get slideToUpdate => 'Klizi za ažuriranje';

  @override
  String copiedToClipboard(String title) {
    return '$title kopiran u međuspremnik';
  }

  @override
  String get batteryLevel => 'Razina baterije';

  @override
  String get charging => 'Punjenje';

  @override
  String get productUpdate => 'Ažuriranje proizvoda';

  @override
  String get offline => 'Bez veze';

  @override
  String get available => 'Dostupno';

  @override
  String get unpairDeviceDialogTitle => 'Ukloni uređaj';

  @override
  String get unpairDeviceDialogMessage =>
      'Ovo će ukloniti uređaj kako bi se mogao povezati sa drugim telefonom. Trebate otići na Postavke > Bluetooth i zaboraviti uređaj kako biste završili postupak.';

  @override
  String get unpair => 'Ukloni';

  @override
  String get unpairAndForgetDevice => 'Ukloni i zaboravi uređaj';

  @override
  String get unknownDevice => 'Nepoznato';

  @override
  String get unknown => 'Nepoznato';

  @override
  String get productName => 'Naziv proizvoda';

  @override
  String get serialNumber => 'Serijski broj';

  @override
  String get connected => 'Povezano';

  @override
  String get privacyPolicyTitle => 'Politika privatnosti';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label kopiran';
  }

  @override
  String get noApiKeysYet => 'Još nema API ključeva';

  @override
  String get createKeyToGetStarted => 'Kreiraj ključ za početak';

  @override
  String get configureSttProvider => 'Konfigurira davatelja STT-a';

  @override
  String get setWhenConversationsAutoEnd => 'Postavite kada se razgovori automatski završavaju';

  @override
  String get importDataFromOtherSources => 'Uvezite podatke iz drugih izvora';

  @override
  String get debugAndDiagnostics => 'Otklanjanje grešaka i dijagnostika';

  @override
  String get autoDeletesAfter3Days => 'Automatski se briše nakon 3 dana.';

  @override
  String get helpsDiagnoseIssues => 'Pomaže pri dijagnozi problema';

  @override
  String get exportStartedMessage => 'Preuzimanje započeto. Ovo može potrajati nekoliko sekundi...';

  @override
  String get exportConversationsToJson => 'Preuzmi razgovore u JSON datoteku';

  @override
  String get knowledgeGraphDeletedSuccess => 'Grafikon znanja uspješno obrisan';

  @override
  String failedToDeleteGraph(String error) {
    return 'Greška pri brisanju grafa: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Obriši sve čvorove i veze';

  @override
  String get addToClaudeDesktopConfig => 'Dodaj u claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Poveži AI asistente sa tvojim podacima';

  @override
  String get useYourMcpApiKey => 'Koristi svoj MCP API ključ';

  @override
  String get realTimeTranscript => 'Transkript u stvarnom vremenu';

  @override
  String get experimental => 'Eksperimentalno';

  @override
  String get transcriptionDiagnostics => 'Dijagnostika transkripcije';

  @override
  String get detailedDiagnosticMessages => 'Detaljne dijagnostičke poruke';

  @override
  String get autoCreateSpeakers => 'Automatski kreiraj govornika';

  @override
  String get autoCreateWhenNameDetected => 'Automatski kreiraj kada je ime detektirano';

  @override
  String get followUpQuestions => 'Pitanja za praćenje';

  @override
  String get suggestQuestionsAfterConversations => 'Predloži pitanja nakon razgovora';

  @override
  String get goalTracker => 'Praćenje ciljeva';

  @override
  String get trackPersonalGoalsOnHomepage => 'Prati svoje osobne ciljeve na početnoj stranici';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Opis stavke aktivnosti ne može biti prazan';

  @override
  String get saved => 'Spremljeno';

  @override
  String get overdue => 'Zakašnjelo';

  @override
  String get failedToUpdateDueDate => 'Greška pri ažuriranju datuma dospijeća';

  @override
  String get markIncomplete => 'Označi kao nezavršeno';

  @override
  String get editDueDate => 'Uredi datum dospijeća';

  @override
  String get setDueDate => 'Postavi datum dospijeća';

  @override
  String get clearDueDate => 'Obriši datum dospijeća';

  @override
  String get failedToClearDueDate => 'Greška pri brisanju datuma dospijeća';

  @override
  String get mondayAbbr => 'Pon';

  @override
  String get tuesdayAbbr => 'Uto';

  @override
  String get wednesdayAbbr => 'Sri';

  @override
  String get thursdayAbbr => 'Čet';

  @override
  String get fridayAbbr => 'Pet';

  @override
  String get saturdayAbbr => 'Sub';

  @override
  String get sundayAbbr => 'Ned';

  @override
  String get howDoesItWork => 'Kako funkcionira?';

  @override
  String get sdCardSyncDescription => 'SD kartična sinkronizacija će uvesti tvoje uspomene sa SD kartice u aplikaciju';

  @override
  String get checksForAudioFiles => 'Provjerava audio datoteke na SD kartici';

  @override
  String get omiSyncsAudioFiles => 'Omi zatim sinkronizira audio datoteke sa serverom';

  @override
  String get serverProcessesAudio => 'Server obrađuje audio datoteke i kreira uspomene';

  @override
  String get youreAllSet => 'Sve je spremno!';

  @override
  String get welcomeToOmiDescription =>
      'Dobrodošao u Omi! Tvoj AI suputnik je spreman da te pomogne sa razgovorima, zadacima i još mnogo toga.';

  @override
  String get startUsingOmi => 'Počni koristiti Omi';

  @override
  String get back => 'Nazad';

  @override
  String get keyboardShortcuts => 'Prečice na tipkovnici';

  @override
  String get toggleControlBar => 'Prikazi/sakrij traku kontrola';

  @override
  String get pressKeys => 'Pritisni tipke...';

  @override
  String get cmdRequired => '⌘ obavezno';

  @override
  String get invalidKey => 'Nevaljana tipka';

  @override
  String get space => 'Razmak';

  @override
  String get search => 'Pretraga';

  @override
  String get searchPlaceholder => 'Pretraži...';

  @override
  String get untitledConversation => 'Razgovor bez naziva';

  @override
  String countRemaining(String count) {
    return '$count preostalo';
  }

  @override
  String get addGoal => 'Dodaj cilj';

  @override
  String get editGoal => 'Uredi cilj';

  @override
  String get icon => 'Ikona';

  @override
  String get goalTitle => 'Naziv cilja';

  @override
  String get current => 'Trenutni';

  @override
  String get target => 'Cilj';

  @override
  String get saveGoal => 'Spremi';

  @override
  String get goals => 'Ciljevi';

  @override
  String get tapToAddGoal => 'Dodirnite da dodate cilj';

  @override
  String welcomeBack(String name) {
    return 'Dobrodošao nazad, $name';
  }

  @override
  String get yourConversations => 'Tvoji razgovori';

  @override
  String get reviewAndManageConversations => 'Pregledi i upravljaj svojimi zapisanim razgovorima';

  @override
  String get startCapturingConversations => 'Počni bilježiti razgovore sa Omi uređajem kako bi ih vidio ovdje.';

  @override
  String get useMobileAppToCapture => 'Koristi mobilnu aplikaciju za bilježenje zvuka';

  @override
  String get conversationsProcessedAutomatically => 'Razgovori se obrađuju automatski';

  @override
  String get getInsightsInstantly => 'Dobij uvide i sažetke odmah';

  @override
  String get showAll => 'Prikaži sve';

  @override
  String get noTasksForToday => 'Nema zadataka za danas.\nZatraži od Omi više zadataka ili kreiraj ručno.';

  @override
  String get dailyScore => 'DNEVNA OCJENA';

  @override
  String get dailyScoreDescription => 'Ocjena koja ti pomaže da bolje\nfokusiš se na izvršavanje.';

  @override
  String get searchResults => 'Rezultati pretrage';

  @override
  String get actionItems => 'Stavke aktivnosti';

  @override
  String get tasksToday => 'Danas';

  @override
  String get tasksTomorrow => 'Sutra';

  @override
  String get tasksNoDeadline => 'Nema roka';

  @override
  String get tasksLater => 'Kasnije';

  @override
  String get loadingTasks => 'Učitavanje zadataka...';

  @override
  String get tasks => 'Zadaci';

  @override
  String get swipeTasksToIndent => 'Povlači zadatke da ih uvučeš, vuci između kategorija';

  @override
  String get create => 'Kreiraj';

  @override
  String get noTasksYet => 'Nema zadataka';

  @override
  String get tasksFromConversationsWillAppear =>
      'Zadaci iz tvojih razgovora će se pojaviti ovdje.\nKlikni Kreiraj kako bi ručno dodao jedan.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Feb';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Maj';

  @override
  String get monthJun => 'Jun';

  @override
  String get monthJul => 'Jul';

  @override
  String get monthAug => 'Avg';

  @override
  String get monthSep => 'Sep';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Dec';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Stavka aktivnosti uspješno ažurirana';

  @override
  String get actionItemCreatedSuccessfully => 'Stavka aktivnosti uspješno kreirana';

  @override
  String get actionItemDeletedSuccessfully => 'Stavka aktivnosti uspješno obrisana';

  @override
  String get deleteActionItem => 'Obriši stavku aktivnosti';

  @override
  String get deleteActionItemConfirmation =>
      'Jeste li sigurni da želite obrisati ovu stavku aktivnosti? Ova radnja se ne može poništiti.';

  @override
  String get enterActionItemDescription => 'Unesite opis stavke aktivnosti...';

  @override
  String get markAsCompleted => 'Označi kao dovršeno';

  @override
  String get setDueDateAndTime => 'Postavi datum i vrijeme dospijeća';

  @override
  String get reloadingApps => 'Ponovno učitavanje aplikacija...';

  @override
  String get loadingApps => 'Učitavanje aplikacija...';

  @override
  String get browseInstallCreateApps => 'Pregledaj, instaliraj i kreiraj aplikacije';

  @override
  String get all => 'Sve';

  @override
  String get open => 'Otvori';

  @override
  String get install => 'Instaliraj';

  @override
  String get noAppsAvailable => 'Nema dostupnih aplikacija';

  @override
  String get unableToLoadApps => 'Nije moguće učitati aplikacije';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Pokušajte prilagoditi pojmove pretrage ili filtre';

  @override
  String get checkBackLaterForNewApps => 'Vratite se kasnije za nove aplikacije';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Provjerite vašu internetsku vezu i pokušajte ponovno';

  @override
  String get createNewApp => 'Kreiraj novu aplikaciju';

  @override
  String get buildSubmitCustomOmiApp => 'Kreiraj i podnesi svoju prilagođenu Omi aplikaciju';

  @override
  String get submittingYourApp => 'Podnošenje aplikacije...';

  @override
  String get preparingFormForYou => 'Priprema obrasca za vas...';

  @override
  String get appDetails => 'Detalji aplikacije';

  @override
  String get paymentDetails => 'Detalji uplate';

  @override
  String get previewAndScreenshots => 'Pregled i snimke ekrana';

  @override
  String get appCapabilities => 'Mogućnosti aplikacije';

  @override
  String get aiPrompts => 'AI upiti';

  @override
  String get chatPrompt => 'Upit za razgovor';

  @override
  String get chatPromptPlaceholder =>
      'Ti si odličnih aplikacija, tvoj zadatak je odgovori na upite korisnika i učini ga sretnima...';

  @override
  String get conversationPrompt => 'Upit za razgovor';

  @override
  String get conversationPromptPlaceholder =>
      'Ti si odličnih aplikacija, bit će ti dati transkript i sažetak razgovora...';

  @override
  String get notificationScopes => 'Dosezi obavijesti';

  @override
  String get appPrivacyAndTerms => 'Privatnost i uvjeti aplikacije';

  @override
  String get makeMyAppPublic => 'Učini moju aplikaciju javnom';

  @override
  String get submitAppTermsAgreement =>
      'Podnošenjem ove aplikacije, slažem se sa Omi AI Uvjetima korištenja i Politikom privatnosti';

  @override
  String get submitApp => 'Podnesi aplikaciju';

  @override
  String get needHelpGettingStarted => 'Trebate pomoć za početak?';

  @override
  String get clickHereForAppBuildingGuides => 'Kliknite ovdje za vodiče i dokumentaciju za izgradnju aplikacija';

  @override
  String get submitAppQuestion => 'Podnesti aplikaciju?';

  @override
  String get submitAppPublicDescription =>
      'Vaša aplikacija će biti pregledana i učinjena javnom. Možete je početi koristiti odmah, čak i tijekom pregleda!';

  @override
  String get submitAppPrivateDescription =>
      'Vaša aplikacija će biti pregledana i učinjena dostupnom vam privatno. Možete je početi koristiti odmah, čak i tijekom pregleda!';

  @override
  String get startEarning => 'Počni zaraditi! 💰';

  @override
  String get connectStripeOrPayPal => 'Poveži Stripe ili PayPal kako bi primio naknade za tvoju aplikaciju.';

  @override
  String get connectNow => 'Poveži sada';

  @override
  String get installsCount => 'Instalacije';

  @override
  String get uninstallApp => 'Deinstaliraj aplikaciju';

  @override
  String get subscribe => 'Pretplati se';

  @override
  String get dataAccessNotice => 'Obavijest o pristupu podacima';

  @override
  String get dataAccessWarning =>
      'Ova aplikacija će pristupiti tvojim podacima. Omi AI nije odgovorna za način na koji se tvoji podaci koriste, mijenjaju ili brišu od strane ove aplikacije';

  @override
  String get installApp => 'Instaliraj aplikaciju';

  @override
  String get betaTesterNotice =>
      'Vi ste beta tester za ovu aplikaciju. Još nije javna. Bit će javna nakon što bude odobrena.';

  @override
  String get appUnderReviewOwner =>
      'Vaša aplikacija je na pregledu i vidljiva samo vama. Bit će javna nakon što bude odobrena.';

  @override
  String get appRejectedNotice =>
      'Vaša aplikacija je odbijena. Molimo ažurirajte detalje aplikacije i ponovno podnesi za pregled.';

  @override
  String get setupSteps => 'Koraci postavljanja';

  @override
  String get setupInstructions => 'Upute za postavljanje';

  @override
  String get integrationInstructions => 'Upute za integraciju';

  @override
  String get preview => 'Pregled';

  @override
  String get aboutTheApp => 'O aplikaciji';

  @override
  String get chatPersonality => 'Osobnost razgovora';

  @override
  String get ratingsAndReviews => 'Ocjene i recenzije';

  @override
  String get noRatings => 'bez ocjena';

  @override
  String ratingsCount(String count) {
    return '$count+ ocjena';
  }

  @override
  String get errorActivatingApp => 'Greška pri aktivaciji aplikacije';

  @override
  String get integrationSetupRequired =>
      'Ako je ovo aplikacija za integraciju, provjerite da je postavljanje dovršeno.';

  @override
  String get installed => 'Instalirano';

  @override
  String get appIdLabel => 'ID aplikacije';

  @override
  String get appNameLabel => 'Naziv aplikacije';

  @override
  String get appNamePlaceholder => 'Moja odličnih aplikacija';

  @override
  String get pleaseEnterAppName => 'Molimo unesite naziv aplikacije';

  @override
  String get categoryLabel => 'Kategorija';

  @override
  String get selectCategory => 'Odaberi kategoriju';

  @override
  String get descriptionLabel => 'Opis';

  @override
  String get appDescriptionPlaceholder =>
      'Moja odličnih aplikacija je odličnih aplikacija koja radi zadivljujuće stvari. To je najbolja aplikacija ikada!';

  @override
  String get pleaseProvideValidDescription => 'Molimo navedite validan opis';

  @override
  String get appPricingLabel => 'Cijena aplikacije';

  @override
  String get noneSelected => 'Ništa odabrano';

  @override
  String get appIdCopiedToClipboard => 'ID aplikacije kopiran u međuspremnik';

  @override
  String get appCategoryModalTitle => 'Kategorija aplikacije';

  @override
  String get pricingFree => 'Besplatno';

  @override
  String get pricingPaid => 'Plaćeno';

  @override
  String get loadingCapabilities => 'Učitavanje mogućnosti...';

  @override
  String get filterInstalled => 'Instalirano';

  @override
  String get filterMyApps => 'Moje aplikacije';

  @override
  String get clearSelection => 'Obriši odabir';

  @override
  String get filterCategory => 'Kategorija';

  @override
  String get rating4PlusStars => '4+ zvjezdice';

  @override
  String get rating3PlusStars => '3+ zvjezdice';

  @override
  String get rating2PlusStars => '2+ zvjezdice';

  @override
  String get rating1PlusStars => '1+ zvjezdice';

  @override
  String get filterRating => 'Ocjena';

  @override
  String get filterCapabilities => 'Mogućnosti';

  @override
  String get noNotificationScopesAvailable => 'Nema dostupnih dosega obavijesti';

  @override
  String get popularApps => 'Popularne aplikacije';

  @override
  String get pleaseProvidePrompt => 'Molimo navedite upit';

  @override
  String chatWithAppName(String appName) {
    return 'Razgovori sa $appName';
  }

  @override
  String get defaultAiAssistant => 'Zadana AI asistentka';

  @override
  String get readyToChat => '✨ Spreman za razgovor!';

  @override
  String get connectionNeeded => '🌐 Veza je potrebna';

  @override
  String get startConversation => 'Pokreni razgovor i neka počne magija';

  @override
  String get checkInternetConnection => 'Molimo provjerite vašu internetsku vezu';

  @override
  String get wasThisHelpful => 'Je li ovo bilo od pomoći?';

  @override
  String get thankYouForFeedback => 'Hvala na vašoj povratnoj informaciji!';

  @override
  String get maxFilesUploadError => 'Možete učitati samo 4 datoteke odjednom';

  @override
  String get attachedFiles => '📎 Priložene datoteke';

  @override
  String get takePhoto => 'Fotografiraj';

  @override
  String get captureWithCamera => 'Uhvati kamerom';

  @override
  String get selectImages => 'Odaberi slike';

  @override
  String get chooseFromGallery => 'Odaberi iz galerije';

  @override
  String get selectFile => 'Odaberi datoteku';

  @override
  String get chooseAnyFileType => 'Odaberi bilo koju vrstu datoteke';

  @override
  String get cannotReportOwnMessages => 'Ne možete prijaviti vlastite poruke';

  @override
  String get messageReportedSuccessfully => '✅ Poruka uspješno prijavljena';

  @override
  String get confirmReportMessage => 'Jeste li sigurni da želite prijaviti ovu poruku?';

  @override
  String get selectChatAssistant => 'Odaberi Chat asistenta';

  @override
  String get enableMoreApps => 'Aktiviraj više aplikacija';

  @override
  String get chatCleared => 'Razgovor obrisan';

  @override
  String get clearChatTitle => 'Obriši razgovor?';

  @override
  String get confirmClearChat => 'Jeste li sigurni da želite obrisati razgovor? Ova radnja se ne može poništiti.';

  @override
  String get copy => 'Kopiraj';

  @override
  String get share => 'Dijeli';

  @override
  String get report => 'Prijavi';

  @override
  String get microphonePermissionRequired => 'Dozvola za mikrofon je potrebna za pozive';

  @override
  String get microphonePermissionDenied =>
      'Dozvola za mikrofon odbijena. Molimo dodjeli dozvolu u Postavke sustava > Privatnost i sigurnost > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Greška pri provjeri dozvole za mikrofon: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Greška pri transkripciji zvuka';

  @override
  String get transcribing => 'Transkripcija u tijeku...';

  @override
  String get transcriptionFailed => 'Transkripcija nije uspjela';

  @override
  String get discardedConversation => 'Odbačeni razgovor';

  @override
  String get at => 'u';

  @override
  String get from => 'od';

  @override
  String get copied => 'Kopirano!';

  @override
  String get copyLink => 'Kopiraj poveznicu';

  @override
  String get hideTranscript => 'Sakrij transkript';

  @override
  String get viewTranscript => 'Prikaži transkript';

  @override
  String get conversationDetails => 'Detalji razgovora';

  @override
  String get transcript => 'Transkript';

  @override
  String segmentsCount(int count) {
    return '$count segmenata';
  }

  @override
  String get noTranscriptAvailable => 'Nema dostupnog transkripta';

  @override
  String get noTranscriptMessage => 'Ovaj razgovor nema transkript.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL razgovora nije moguće generirati.';

  @override
  String get failedToGenerateConversationLink => 'Greška pri generiranju veze razgovora';

  @override
  String get failedToGenerateShareLink => 'Greška pri generiranju veze za dijeljenje';

  @override
  String get reloadingConversations => 'Ponovno učitavanje razgovora...';

  @override
  String get user => 'Korisnik';

  @override
  String get starred => 'Označeno zvijezdom';

  @override
  String get date => 'Datum';

  @override
  String get noResultsFound => 'Nema pronađenih rezultata';

  @override
  String get tryAdjustingSearchTerms => 'Pokušajte prilagoditi pojmove pretrage';

  @override
  String get starConversationsToFindQuickly => 'Označi razgovore zvijezdom kako bi ih brzo pronašao ovdje';

  @override
  String noConversationsOnDate(String date) {
    return 'Nema razgovora na datum $date';
  }

  @override
  String get trySelectingDifferentDate => 'Pokušajte odabrati drugi datum';

  @override
  String get conversations => 'Razgovori';

  @override
  String get chat => 'Razgovor';

  @override
  String get actions => 'Radnje';

  @override
  String get syncAvailable => 'Sinkronizacija dostupna';

  @override
  String get referAFriend => 'Preporuči prijatelja';

  @override
  String get help => 'Pomoć';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Nadogradi na Pro';

  @override
  String get getOmiDevice => 'Pribili Omi uređaj';

  @override
  String get wearableAiCompanion => 'AI suputnik koji se nosi';

  @override
  String get loadingMemories => 'Učitavanje uspomena...';

  @override
  String get allMemories => 'Sve uspomene';

  @override
  String get aboutYou => 'O tebi';

  @override
  String get manual => 'Ručno';

  @override
  String get loadingYourMemories => 'Učitavanje tvojih uspomena...';

  @override
  String get createYourFirstMemory => 'Kreiraj svoju prvu uspomenu za početak';

  @override
  String get tryAdjustingFilter => 'Pokušajte prilagoditi pretragu ili filter';

  @override
  String get whatWouldYouLikeToRemember => 'Što bi htio zapamtiti?';

  @override
  String get category => 'Kategorija';

  @override
  String get public => 'Javno';

  @override
  String get failedToSaveCheckConnection => 'Greška pri spremanju. Molimo provjerite vašu vezu.';

  @override
  String get createMemory => 'Kreiraj uspomenu';

  @override
  String get deleteMemoryConfirmation =>
      'Jeste li sigurni da želite obrisati ovu uspomenu? Ova radnja se ne može poništiti.';

  @override
  String get makePrivate => 'Učini privatnom';

  @override
  String get organizeAndControlMemories => 'Organiziraj i upravljaj svojima uspomenama';

  @override
  String get total => 'Ukupno';

  @override
  String get makeAllMemoriesPrivate => 'Učini sve uspomene privatnima';

  @override
  String get setAllMemoriesToPrivate => 'Postavi sve uspomene na privatnu vidljivost';

  @override
  String get makeAllMemoriesPublic => 'Učini sve uspomene javnima';

  @override
  String get setAllMemoriesToPublic => 'Postavi sve uspomene na javnu vidljivost';

  @override
  String get permanentlyRemoveAllMemories => 'Trajno ukloni sve uspomene iz Omi-ja';

  @override
  String get allMemoriesAreNowPrivate => 'Sve uspomene su sada privatne';

  @override
  String get allMemoriesAreNowPublic => 'Sve uspomene su sada javne';

  @override
  String get clearOmisMemory => 'Obriši Omi-jevu memoriju';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Jeste li sigurni da želite obrisati Omi-jevu memoriju? Ova radnja se ne može poništiti i trajno će obrisati sve $count uspomena.';
  }

  @override
  String get omisMemoryCleared => 'Omi-jeva memorija o tebi je obrisana';

  @override
  String get welcomeToOmi => 'Dobrodošao u Omi';

  @override
  String get continueWithApple => 'Nastavi sa Apple ID-om';

  @override
  String get continueWithGoogle => 'Nastavi s Google-om';

  @override
  String get byContinuingYouAgree => 'Nastavljanjem se slažete s našim ';

  @override
  String get termsOfService => 'Uvjetima korištenja';

  @override
  String get and => ' i ';

  @override
  String get dataAndPrivacy => 'Zaštita podataka i privatnost';

  @override
  String get secureAuthViaAppleId => 'Sigurna autentifikacija putem Apple ID-a';

  @override
  String get secureAuthViaGoogleAccount => 'Sigurna autentifikacija putem Google računa';

  @override
  String get whatWeCollect => 'Što prikupljamo';

  @override
  String get dataCollectionMessage =>
      'Nastavljanjem će vaši razgovori, snimke i osobni podaci biti sigurno pohranjeni na našim poslužiteljima kako bi vam pružili AI-pogonske uvide i omogućili sve značajke aplikacije.';

  @override
  String get dataProtection => 'Zaštita podataka';

  @override
  String get yourDataIsProtected => 'Vaši podaci su zaštićeni i uređeni prema našim ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Molimo odaberite svoj primarni jezik';

  @override
  String get chooseYourLanguage => 'Odaberite jezik';

  @override
  String get selectPreferredLanguageForBestExperience => 'Odaberite željeni jezik za najbolje Omi iskustvo';

  @override
  String get searchLanguages => 'Pretraži jezike...';

  @override
  String get selectALanguage => 'Odaberite jezik';

  @override
  String get tryDifferentSearchTerm => 'Pokušajte s drugom traženjem';

  @override
  String get pleaseEnterYourName => 'Molimo unesite svoje ime';

  @override
  String get nameMustBeAtLeast2Characters => 'Ime mora biti najmanje 2 znaka';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Recite nam kako biste voljeli biti obraćeni. To pomaže personalizirati vaše Omi iskustvo.';

  @override
  String charactersCount(int count) {
    return '$count znakova';
  }

  @override
  String get enableFeaturesForBestExperience => 'Omogućite značajke za najbolje Omi iskustvo na vašem uređaju.';

  @override
  String get microphoneAccess => 'Pristup mikrofonu';

  @override
  String get recordAudioConversations => 'Snimanje audio razgovora';

  @override
  String get microphoneAccessDescription =>
      'Omi trebam pristup mikrofonu kako bi snimio vaše razgovore i dao transkripcije.';

  @override
  String get screenRecording => 'Snimanje zaslona';

  @override
  String get captureSystemAudioFromMeetings => 'Hvatanje sistemskog zvuka s sastanaka';

  @override
  String get screenRecordingDescription =>
      'Omi trebam dozvolu za snimanje zaslona kako bi hvatao sistemski zvuk s vaših mrežnih sastanaka.';

  @override
  String get accessibility => 'Pristupačnost';

  @override
  String get detectBrowserBasedMeetings => 'Otkrivanje mrežnih sastanaka';

  @override
  String get accessibilityDescription =>
      'Omi trebam dozvolu za pristupačnost kako bi otkrio kada se pridružite Zoom, Meet ili Teams sastancima u vašem pregledniku.';

  @override
  String get pleaseWait => 'Molimo pričekajte...';

  @override
  String get joinTheCommunity => 'Pridružite se zajednici!';

  @override
  String get loadingProfile => 'Učitavanje profila...';

  @override
  String get profileSettings => 'Postavke profila';

  @override
  String get noEmailSet => 'Nema postavljene e-pošte';

  @override
  String get userIdCopiedToClipboard => 'Korisnički ID kopiran u međuspremnik';

  @override
  String get yourInformation => 'Vaši podaci';

  @override
  String get setYourName => 'Postavite svoje ime';

  @override
  String get changeYourName => 'Promijenite svoje ime';

  @override
  String get voiceAndPeople => 'Glas i osobe';

  @override
  String get teachOmiYourVoice => 'Učite Omi vaš glas';

  @override
  String get tellOmiWhoSaidIt => 'Recite Omi tko je to rekao 🗣️';

  @override
  String get payment => 'Plaćanje';

  @override
  String get addOrChangeYourPaymentMethod => 'Dodajte ili promijenite svoju metodu plaćanja';

  @override
  String get preferences => 'Preferences';

  @override
  String get helpImproveOmiBySharing => 'Pomozite poboljšati Omi dijeljenjem anonimizirane analitike';

  @override
  String get deleteAccount => 'Izbriši račun';

  @override
  String get deleteYourAccountAndAllData => 'Izbrišite svoj račun i sve podatke';

  @override
  String get clearLogs => 'Obriši zapisnike';

  @override
  String get debugLogsCleared => 'Zapisnici za otklanjanje grešaka izbrisani';

  @override
  String get exportConversations => 'Izvezi razgovore';

  @override
  String get exportAllConversationsToJson => 'Izvezite sve svoje razgovore u JSON datoteku.';

  @override
  String get conversationsExportStarted =>
      'Izvoz razgovora započet. To može potrajati nekoliko sekundi, molimo pričekajte.';

  @override
  String get mcpDescription =>
      'Za povezivanje Omi-ja s drugim aplikacijama kako bi čitao, pretraživao i upravljao vašim uspomenama i razgovorima. Kreirajte ključ kako bi započeli.';

  @override
  String get apiKeys => 'API ključevi';

  @override
  String errorLabel(String error) {
    return 'Greška: $error';
  }

  @override
  String get noApiKeysFound => 'Nema pronađenih API ključeva. Kreirajte jedan da biste započeli.';

  @override
  String get advancedSettings => 'Napredne postavke';

  @override
  String get triggersWhenNewConversationCreated => 'Aktivira se kada se kreira novi razgovor.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Aktivira se kada se primi nova transkripcija.';

  @override
  String get realtimeAudioBytes => 'Zvučni bajti u stvarnom vremenu';

  @override
  String get triggersWhenAudioBytesReceived => 'Aktivira se kada se primaju zvučni bajti.';

  @override
  String get everyXSeconds => 'Svakih x sekundi';

  @override
  String get triggersWhenDaySummaryGenerated => 'Aktivira se kada se generiše dnevni sažetak.';

  @override
  String get tryLatestExperimentalFeatures => 'Pokušajte najnovije eksperimentalne značajke iz Omi tima.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Status dijagnostike usluge transkripcije';

  @override
  String get enableDetailedDiagnosticMessages => 'Omogućite detaljne poruke dijagnostike iz usluge transkripcije';

  @override
  String get autoCreateAndTagNewSpeakers => 'Automatski kreiraj i označi nove govornike';

  @override
  String get automaticallyCreateNewPerson => 'Automatski kreirajte novu osobu kada se detektuje ime u transkripciji.';

  @override
  String get pilotFeatures => 'Pilot značajke';

  @override
  String get pilotFeaturesDescription => 'Ove značajke su testovi i nije zajamčena nikakva podrška.';

  @override
  String get suggestFollowUpQuestion => 'Predloži pitanje za nastavak';

  @override
  String get saveSettings => 'Spremi postavke';

  @override
  String get syncingDeveloperSettings => 'Sinkronizovanje postavki razvojnog programera...';

  @override
  String get summary => 'Sažetak';

  @override
  String get auto => 'Automatski';

  @override
  String get noSummaryForApp =>
      'Nema dostupnog sažetka za ovu aplikaciju. Pokušajte s drugom aplikacijom za bolje rezultate.';

  @override
  String get tryAnotherApp => 'Pokušaj drugu aplikaciju';

  @override
  String generatedBy(String appName) {
    return 'Generirano od $appName';
  }

  @override
  String get overview => 'Pregled';

  @override
  String get otherAppResults => 'Rezultati ostalih aplikacija';

  @override
  String get unknownApp => 'Nepoznata aplikacija';

  @override
  String get noSummaryAvailable => 'Nema dostupnog sažetka';

  @override
  String get conversationNoSummaryYet => 'Ovaj razgovor još nema sažetak.';

  @override
  String get chooseSummarizationApp => 'Odaberite aplikaciju za sažimanje';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName postavljen kao zadana aplikacija za sažimanje';
  }

  @override
  String get letOmiChooseAutomatically => 'Neka Omi automatski odabere najbolju aplikaciju';

  @override
  String get deleteConversationConfirmation =>
      'Ste li sigurni da želite izbrisati ovaj razgovor? Ova radnja se ne može poništiti.';

  @override
  String get conversationDeleted => 'Razgovor izbrisan';

  @override
  String get generatingLink => 'Generiranje linka...';

  @override
  String get editConversation => 'Uredi razgovor';

  @override
  String get conversationLinkCopiedToClipboard => 'Link razgovora kopiran u međuspremnik';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transkripcija razgovora kopirana u međuspremnik';

  @override
  String get editConversationDialogTitle => 'Uredi razgovor';

  @override
  String get changeTheConversationTitle => 'Promijenite naslov razgovora';

  @override
  String get conversationTitle => 'Naslov razgovora';

  @override
  String get enterConversationTitle => 'Unesite naslov razgovora...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Naslov razgovora uspješno ažuriran';

  @override
  String get failedToUpdateConversationTitle => 'Neuspješno ažuriranje naslova razgovora';

  @override
  String get errorUpdatingConversationTitle => 'Greška pri ažuriranju naslova razgovora';

  @override
  String get settingUp => 'Postavljanje...';

  @override
  String get startYourFirstRecording => 'Započnite s vašim prvim snimanjem';

  @override
  String get preparingSystemAudioCapture => 'Priprema hvatanja sistemskog zvuka';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Kliknite gumb kako bi hvatali zvuk za užive transkripcije, AI uvide i automatsko spremanje.';

  @override
  String get reconnecting => 'Ponovno povezivanje...';

  @override
  String get recordingPaused => 'Snimanje pauziran';

  @override
  String get recordingActive => 'Snimanje aktivno';

  @override
  String get startRecording => 'Započni snimanje';

  @override
  String resumingInCountdown(String countdown) {
    return 'Nastavlja se u ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Dodirnite play kako bi nastavili';

  @override
  String get listeningForAudio => 'Slušam zvuk...';

  @override
  String get preparingAudioCapture => 'Priprema hvatanja zvuka';

  @override
  String get clickToBeginRecording => 'Kliknite kako bi započeli snimanje';

  @override
  String get translated => 'prevedeno';

  @override
  String get liveTranscript => 'Uživna transkripcija';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenata';
  }

  @override
  String get startRecordingToSeeTranscript => 'Započnite snimanje kako bi vidjeli uživnu transkripciju';

  @override
  String get paused => 'Pauziran';

  @override
  String get initializing => 'Inicijalizacija...';

  @override
  String get recording => 'Snimanje';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon promijenjen. Nastavlja se u ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Kliknite play kako bi nastavili ili stop kako bi završili';

  @override
  String get settingUpSystemAudioCapture => 'Postavljanje hvatanja sistemskog zvuka';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Hvatanje zvuka i generiranje transkripcije';

  @override
  String get clickToBeginRecordingSystemAudio => 'Kliknite kako bi započeli snimanje sistemskog zvuka';

  @override
  String get you => 'Vi';

  @override
  String speakerWithId(String speakerId) {
    return 'Govornik $speakerId';
  }

  @override
  String get translatedByOmi => 'prevedeno od omi';

  @override
  String get backToConversations => 'Natrag na razgovore';

  @override
  String get systemAudio => 'Sustav';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Zvučni ulaz postavljen na $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Greška pri prebacivanju audio uređaja: $error';
  }

  @override
  String get selectAudioInput => 'Odaberite zvučni ulaz';

  @override
  String get loadingDevices => 'Učitavanje uređaja...';

  @override
  String get settingsHeader => 'POSTAVKE';

  @override
  String get plansAndBilling => 'Planovi i naplate';

  @override
  String get calendarIntegration => 'Integracija kalendara';

  @override
  String get dailySummary => 'Dnevni sažetak';

  @override
  String get developer => 'Razvojni programer';

  @override
  String get about => 'O aplikaciji';

  @override
  String get selectTime => 'Odaberite vrijeme';

  @override
  String get accountGroup => 'Račun';

  @override
  String get signOutQuestion => 'Odjava?';

  @override
  String get signOutConfirmation => 'Ste li sigurni da želite se odjaviti?';

  @override
  String get customVocabularyHeader => 'PRILAGOĐENI RJEČNIK';

  @override
  String get addWordsDescription => 'Dodajte riječi koje bi Omi trebao prepoznati tijekom transkripcije.';

  @override
  String get enterWordsHint => 'Unesite riječi (odvojene zarezom)';

  @override
  String get dailySummaryHeader => 'DNEVNI SAŽETAK';

  @override
  String get dailySummaryTitle => 'Dnevni sažetak';

  @override
  String get dailySummaryDescription =>
      'Dobijte personalizirani sažetak razgovora vašeg dana dostavljen kao obavijest.';

  @override
  String get deliveryTime => 'Vrijeme dostave';

  @override
  String get deliveryTimeDescription => 'Kada primiti svoj dnevni sažetak';

  @override
  String get subscription => 'Pretplata';

  @override
  String get viewPlansAndUsage => 'Pogledajte planove i korištenje';

  @override
  String get viewPlansDescription => 'Upravljajte svojom pretplatom i pogledajte statistiku korištenja';

  @override
  String get addOrChangePaymentMethod => 'Dodajte ili promijenite svoju metodu plaćanja';

  @override
  String get displayOptions => 'Mogućnosti prikaza';

  @override
  String get showMeetingsInMenuBar => 'Prikaži sastanke na menubar-u';

  @override
  String get displayUpcomingMeetingsDescription => 'Prikaži nadolazeće sastanke na menubar-u';

  @override
  String get showEventsWithoutParticipants => 'Prikaži događaje bez sudionika';

  @override
  String get includePersonalEventsDescription => 'Uključi osobne događaje bez prisutnih osoba';

  @override
  String get upcomingMeetings => 'Nadolazeći sastanci';

  @override
  String get checkingNext7Days => 'Provjera sljedećih 7 dana';

  @override
  String get shortcuts => 'Prečaci';

  @override
  String get shortcutChangeInstruction =>
      'Kliknite na prečac kako bi ga promijenili. Pritisnite Escape kako bi odustali.';

  @override
  String get configureSTTProvider => 'Konfigurirajte STT davatelja';

  @override
  String get setConversationEndDescription => 'Postavite kada se razgovori automatski završavaju';

  @override
  String get importDataDescription => 'Uvezite podatke iz drugih izvora';

  @override
  String get exportConversationsDescription => 'Izvezite razgovore u JSON';

  @override
  String get exportingConversations => 'Izvoz razgovora...';

  @override
  String get clearNodesDescription => 'Obriši sve čvorove i veze';

  @override
  String get deleteKnowledgeGraphQuestion => 'Obriši graf znanja?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Ovo će obrisati sve izvedene podatke grafa znanja. Vaše izvorne uspomene ostaju sigurne.';

  @override
  String get connectOmiWithAI => 'Povežite Omi-ja s AI asistentima';

  @override
  String get noAPIKeys => 'Nema API ključeva. Kreirajte jedan da biste započeli.';

  @override
  String get autoCreateWhenDetected => 'Automatski kreiraj kada se detektuje ime';

  @override
  String get trackPersonalGoals => 'Pratite osobne ciljeve na početnoj stranici';

  @override
  String get endpointURL => 'URL krajnje točke';

  @override
  String get links => 'Linkovi';

  @override
  String get discordMemberCount => '8000+ članova na Discordu';

  @override
  String get userInformation => 'Informacije o korisniku';

  @override
  String get capabilities => 'Mogućnosti';

  @override
  String get previewScreenshots => 'Pregledajte snimke zaslona';

  @override
  String get holdOnPreparingForm => 'Sačekajte, pripremamo obrazac za vas';

  @override
  String get bySubmittingYouAgreeToOmi => 'Slanjem se slažete s Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Uvjeti korištenja i política privatnosti';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Pomaže dijagnosticirati probleme. Automatski se briše nakon 3 dana.';

  @override
  String get manageYourApp => 'Upravljajte svojom aplikacijom';

  @override
  String get updatingYourApp => 'Ažuriranje vaše aplikacije';

  @override
  String get fetchingYourAppDetails => 'Dohvaćanje detalja vaše aplikacije';

  @override
  String get updateAppQuestion => 'Ažurirati aplikaciju?';

  @override
  String get updateAppConfirmation =>
      'Ste li sigurni da želite ažurirati vašu aplikaciju? Promjene će se odraziti kada bude pregledana od strane našeg tima.';

  @override
  String get updateApp => 'Ažurira aplikaciju';

  @override
  String get createAndSubmitNewApp => 'Kreirajte i pošaljite novu aplikaciju';

  @override
  String appsCount(String count) {
    return 'Aplikacije ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Privatne aplikacije ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Javne aplikacije ($count)';
  }

  @override
  String get newVersionAvailable => 'Nova verzija dostupna  🎉';

  @override
  String get no => 'Ne';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Pretplata uspješno otkazana. Ostaje aktivna do kraja trenutnog razdoblja naplate.';

  @override
  String get failedToCancelSubscription => 'Neuspješno otkazivanje pretplate. Molimo pokušajte ponovno.';

  @override
  String get invalidPaymentUrl => 'Nevaljani URL za plaćanje';

  @override
  String get permissionsAndTriggers => 'Dozvole i okidači';

  @override
  String get chatFeatures => 'Značajke razgovora';

  @override
  String get uninstall => 'Deinstaliraj';

  @override
  String get installs => 'INSTALACIJE';

  @override
  String get priceLabel => 'CIJENA';

  @override
  String get updatedLabel => 'AŽURIRANO';

  @override
  String get createdLabel => 'KREIRANO';

  @override
  String get featuredLabel => 'ISTAKNUTU';

  @override
  String get cancelSubscriptionQuestion => 'Otkazati pretplatu?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Ste li sigurni da želite otkazati vašu pretplatu? Nastavit ćete imati pristup do kraja vašeg trenutnog razdoblja naplate.';

  @override
  String get cancelSubscriptionButton => 'Otkaži pretplatu';

  @override
  String get cancelling => 'Otkazivanje...';

  @override
  String get betaTesterMessage =>
      'Ste beta tester za ovu aplikaciju. Nije još javna. Bit će javna nakon što bude odobrena.';

  @override
  String get appUnderReviewMessage =>
      'Vaša aplikacija je na pregledu i vidljiva je samo vama. Bit će javna nakon što bude odobrena.';

  @override
  String get appRejectedMessage =>
      'Vaša aplikacija je odbijena. Molimo ažurirajte detalje aplikacije i ponovno pošaljite na pregled.';

  @override
  String get invalidIntegrationUrl => 'Nevaljani URL integracije';

  @override
  String get tapToComplete => 'Dodirnite kako bi završili';

  @override
  String get invalidSetupInstructionsUrl => 'Nevaljani URL za upute za postavljanje';

  @override
  String get pushToTalk => 'Pritisni za govor';

  @override
  String get summaryPrompt => 'Poziv za sažetak';

  @override
  String get pleaseSelectARating => 'Molimo odaberite ocjenu';

  @override
  String get reviewAddedSuccessfully => 'Recenzija uspješno dodana 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recenzija uspješno ažurirana 🚀';

  @override
  String get failedToSubmitReview => 'Neuspješna prijava recenzije. Molimo pokušajte ponovno.';

  @override
  String get addYourReview => 'Dodajte svoju recenziju';

  @override
  String get editYourReview => 'Uredite svoju recenziju';

  @override
  String get writeAReviewOptional => 'Napišite recenziju (izbjenji)';

  @override
  String get submitReview => 'Pošalji recenziju';

  @override
  String get updateReview => 'Ažurira recenziju';

  @override
  String get yourReview => 'Vaša recenzija';

  @override
  String get anonymousUser => 'Anonimni korisnik';

  @override
  String get issueActivatingApp => 'Došlo je do problema pri aktiviranju ove aplikacije. Molimo pokušajte ponovno.';

  @override
  String get dataAccessNoticeDescription =>
      'Ova aplikacija će pristupiti vašim podacima. Omi AI nije odgovorna za kako se vaši podaci koriste, mijenjaju ili brišu od strane ove aplikacije';

  @override
  String get copyUrl => 'Kopira URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Pon';

  @override
  String get weekdayTue => 'Uto';

  @override
  String get weekdayWed => 'Sri';

  @override
  String get weekdayThu => 'Čet';

  @override
  String get weekdayFri => 'Pet';

  @override
  String get weekdaySat => 'Sub';

  @override
  String get weekdaySun => 'Ned';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName integracija uskoro stiže';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Već izvezeno na $platform';
  }

  @override
  String get anotherPlatform => 'drugu platformu';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Molimo autentificirajte se s $serviceName u Postavke > Integracije zadataka';
  }

  @override
  String addingToService(String serviceName) {
    return 'Dodavanje u $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Dodano u $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Neuspješno dodavanje u $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Dozvola odbijena za Apple podsjetnike';

  @override
  String failedToCreateApiKey(String error) {
    return 'Neuspješna kreiranja ključa API davatelja: $error';
  }

  @override
  String get createAKey => 'Kreirajte ključ';

  @override
  String get apiKeyRevokedSuccessfully => 'API ključ uspješno opozvan';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Neuspješna opozvana API ključa: $error';
  }

  @override
  String get omiApiKeys => 'Omi API ključevi';

  @override
  String get apiKeysDescription =>
      'API ključevi se koriste za autentifikaciju kada vaša aplikacija komunicira s OMI poslužiteljem. Omogućavaju vašoj aplikaciji da sigurno kreira uspomene i pristupa drugim OMI uslugama.';

  @override
  String get aboutOmiApiKeys => 'O Omi API ključevima';

  @override
  String get yourNewKey => 'Vaš novi ključ:';

  @override
  String get copyToClipboard => 'Kopira u međuspremnik';

  @override
  String get pleaseCopyKeyNow => 'Molimo kopira ga sada i zapišite ga negdje sigurno. ';

  @override
  String get willNotSeeAgain => 'Nećete ga moći vidjeti ponovno.';

  @override
  String get revokeKey => 'Opozovi ključ';

  @override
  String get revokeApiKeyQuestion => 'Opozovi API ključ?';

  @override
  String get revokeApiKeyWarning =>
      'Ova radnja se ne može poništiti. Bilo koje aplikacije koje koriste ovaj ključ više neće moći pristupiti API-ju.';

  @override
  String get revoke => 'Opozovi';

  @override
  String get whatWouldYouLikeToCreate => 'Što biste voljeli kreirati?';

  @override
  String get createAnApp => 'Kreirajte aplikaciju';

  @override
  String get createAndShareYourApp => 'Kreirajte i dijelite svoju aplikaciju';

  @override
  String get itemApp => 'Aplikacija';

  @override
  String keepItemPublic(String item) {
    return 'Čuvaj $item javno';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Učini $item javnim?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Učini $item privatnim?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Ako učinite $item javnim, može ga koristiti svatko';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Ako učinite $item privatnim sada, prestati će raditi za sve i biti će vidljiv samo vama';
  }

  @override
  String get manageApp => 'Upravljaj aplikacijom';

  @override
  String deleteItemTitle(String item) {
    return 'Obriši $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Obriši $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Ste li sigurni da želite obrisati ovaj $item? Ova radnja se ne može poništiti.';
  }

  @override
  String get revokeKeyQuestion => 'Opozovi ključ?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Ste li sigurni da želite opozvati ključ \"$keyName\"? Ova radnja se ne može poništiti.';
  }

  @override
  String get createNewKey => 'Kreirajte novi ključ';

  @override
  String get keyNameHint => 'npr. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Molimo unesite naziv.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Neuspješna kreiranja ključa: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Neuspješna kreiranja ključa. Molimo pokušajte ponovno.';

  @override
  String get keyCreated => 'Ključ kreiran';

  @override
  String get keyCreatedMessage => 'Vaš novi ključ je kreiran. Molimo kopira ga sada. Nećete ga moći vidjeti ponovno.';

  @override
  String get keyWord => 'Ključ';

  @override
  String get externalAppAccess => 'Pristup vanjskoj aplikaciji';

  @override
  String get externalAppAccessDescription =>
      'Sljedeće instalirane aplikacije imaju eksterne integracije i mogu pristupiti vašim podacima, kao što su razgovori i uspomene.';

  @override
  String get noExternalAppsHaveAccess => 'Nema vanjskih aplikacija koje imaju pristup vašim podacima.';

  @override
  String get maximumSecurityE2ee => 'Maksimalna sigurnost (E2EE)';

  @override
  String get e2eeDescription =>
      'Šifriranje od kraja do kraja je zlatni standard za privatnost. Kada je omogućeno, vaši podaci se šifriraju na vašem uređaju prije nego što se pošalju našim poslužiteljima. To znači da nitko, čak ni Omi, ne može pristupiti vašem sadržaju.';

  @override
  String get importantTradeoffs => 'Važni kompromisi:';

  @override
  String get e2eeTradeoff1 => '• Neke značajke kao što su vanjske integracije aplikacija mogu biti onemogućene.';

  @override
  String get e2eeTradeoff2 => '• Ako izgubite svoju lozinku, vaši podaci se ne mogu oporaviti.';

  @override
  String get featureComingSoon => 'Ova značajka uskoro stiže!';

  @override
  String get migrationInProgressMessage =>
      'Migracija je u tijeku. Ne možete promijeniti razinu zaštite dok se ne završi.';

  @override
  String get migrationFailed => 'Migracija neuspješna';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migracija s $source na $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objekata';
  }

  @override
  String get secureEncryption => 'Sigurna šifriranje';

  @override
  String get secureEncryptionDescription =>
      'Vaši podaci se šifriraju s ključem jedinstvenim za vas na našim poslužiteljima, hostiranim na Google Cloud-u. To znači da je vaš sadržaj u neobrađenom obliku nedostupan svima, uključujući Omi osoblje ili Google, izravno iz baze podataka.';

  @override
  String get endToEndEncryption => 'Šifriranje od kraja do kraja';

  @override
  String get e2eeCardDescription =>
      'Omogućite za maksimalnu sigurnost gdje samo vi možete pristupiti svojim podacima. Dodirnite kako bi saznali više.';

  @override
  String get dataAlwaysEncrypted =>
      'Bez obzira na razinu, vaši podaci su uvijek šifrirani tijekom mirovanju i putovanja.';

  @override
  String get readOnlyScope => 'Samo čitanje';

  @override
  String get fullAccessScope => 'Puni pristup';

  @override
  String get readScope => 'Čitanje';

  @override
  String get writeScope => 'Pisanje';

  @override
  String get apiKeyCreated => 'API ključ kreiran!';

  @override
  String get saveKeyWarning => 'Spremi ovaj ključ sada! Nećete ga moći vidjeti ponovno.';

  @override
  String get yourApiKey => 'VAŠ API KLJUČ';

  @override
  String get tapToCopy => 'Dodirnite kako bi kopirali';

  @override
  String get copyKey => 'Kopira ključ';

  @override
  String get createApiKey => 'Kreirajte API ključ';

  @override
  String get accessDataProgrammatically => 'Pristupite podacima programski';

  @override
  String get keyNameLabel => 'NAZIV KLJUČA';

  @override
  String get keyNamePlaceholder => 'npr. Moja integracija aplikacije';

  @override
  String get permissionsLabel => 'DOZVOLE';

  @override
  String get permissionsInfoNote =>
      'R = Čitanje, W = Pisanje. Zadana vrijednost je samo čitanje ako ništa nije odabrano.';

  @override
  String get developerApi => 'API za razvojne programere';

  @override
  String get createAKeyToGetStarted => 'Kreirajte ključ kako bi započeli';

  @override
  String errorWithMessage(String error) {
    return 'Greška: $error';
  }

  @override
  String get omiTraining => 'Omi obuka';

  @override
  String get trainingDataProgram => 'Program za podatke o obukama';

  @override
  String get getOmiUnlimitedFree => 'Dobijte Omi Unlimited besplatno doprinoseći svoje podatke za obuku AI modela.';

  @override
  String get trainingDataBullets =>
      '• Vaši podaci pomažu poboljšati AI modele\n• Samo neosjetan podaci se dijele\n• Potpuno transparentan proces';

  @override
  String get learnMoreAtOmiTraining => 'Saznajte više na omi.me/training';

  @override
  String get agreeToContributeData => 'Razumijem i slažem se doprinijeti svoje podatke za AI obuku';

  @override
  String get submitRequest => 'Pošalji zahtjev';

  @override
  String get thankYouRequestUnderReview =>
      'Hvala vam! Vaš zahtjev je na pregledu. Obavijestit ćemo vas nakon što bude odobren.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Vaš plan ostaje aktivan do $date. Nakon toga, izgubite pristup neograničenim značajkama. Ste li sigurni?';
  }

  @override
  String get confirmCancellation => 'Potvrdi otkazivanje';

  @override
  String get keepMyPlan => 'Čuva moj plan';

  @override
  String get subscriptionSetToCancel => 'Vaša pretplata je postavljena na otkazivanje na kraju razdoblja.';

  @override
  String get switchedToOnDevice => 'Prebačeno na transkripciju na uređaju';

  @override
  String get couldNotSwitchToFreePlan => 'Nije moguće prebaciti se na besplatni plan. Pokušajte ponovno.';

  @override
  String get couldNotLoadPlans => 'Nije moguće učitati dostupne planove. Pokušajte ponovno.';

  @override
  String get selectedPlanNotAvailable => 'Odabrani plan nije dostupan. Pokušajte ponovno.';

  @override
  String get upgradeToAnnualPlan => 'Nadograđivanje na godišnji plan';

  @override
  String get importantBillingInfo => 'Važne informacije o naplati:';

  @override
  String get monthlyPlanContinues => 'Vaš trenutni mjesečni plan će nastaviti do kraja vašeg razdoblja naplate';

  @override
  String get paymentMethodCharged =>
      'Vašoj postojećoj metodi plaćanja će biti automatski naplaćena kada se mjesečni plan završi';

  @override
  String get annualSubscriptionStarts => 'Vaša 12-mjesečna godišnja pretplata će se automatski pokrenuti nakon naplate';

  @override
  String get thirteenMonthsCoverage =>
      'Dobit ćete ukupno 13 mjeseci pokrivanja (trenutni mjesec + 12 mjeseci godišnje)';

  @override
  String get confirmUpgrade => 'Potvrdi nadogradnju';

  @override
  String get confirmPlanChange => 'Potvrdi promjenu plana';

  @override
  String get confirmAndProceed => 'Potvrdi i nastavi';

  @override
  String get upgradeScheduled => 'Nadogradnja zakazana';

  @override
  String get changePlan => 'Promijeni plan';

  @override
  String get upgradeAlreadyScheduled => 'Vaša nadogradnja na godišnji plan je već zakazana';

  @override
  String get youAreOnUnlimitedPlan => 'Nalazite se na Unlimited planu.';

  @override
  String get yourOmiUnleashed => 'Vaš Omi, oslobođen. Idite na unlimited za beskonačne mogućnosti.';

  @override
  String planEndedOn(String date) {
    return 'Vaš plan je završio $date.\\nPrenazovite se sada - bit će vam odmah naplaćeno novo razdoblje naplate.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Vaš plan je postavljen da se otkaže $date.\\nPrenazovite se sada kako biste zadržali svoju korist - bez naplate do $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Vaš godišnji plan će se automatski pokrenuti kada se mjesečni plan završi.';

  @override
  String planRenewsOn(String date) {
    return 'Vaš plan se obnavljja $date.';
  }

  @override
  String get unlimitedConversations => 'Neograničeni razgovori';

  @override
  String get askOmiAnything => 'Pitajte Omija bilo što o svojoj životu';

  @override
  String get unlockOmiInfiniteMemory => 'Otključajte Omijevu beskonačnu memoriju';

  @override
  String get youreOnAnnualPlan => 'Nalazite se na godišnjem planu';

  @override
  String get alreadyBestValuePlan => 'Već imate plan s najboljom vrijednosti. Nema potrebe za promjenama.';

  @override
  String get unableToLoadPlans => 'Nije moguće učitati planove';

  @override
  String get checkConnectionTryAgain => 'Provjerite vezu i pokušajte ponovo';

  @override
  String get useFreePlan => 'Koristi besplatni plan';

  @override
  String get continueText => 'Nastavi';

  @override
  String get resubscribe => 'Ponovo se pretplati';

  @override
  String get couldNotOpenPaymentSettings => 'Nije moguće otvoriti postavke plaćanja. Pokušajte ponovno.';

  @override
  String get managePaymentMethod => 'Upravljaj metodom plaćanja';

  @override
  String get cancelSubscription => 'Otkaži pretplatu';

  @override
  String endsOnDate(String date) {
    return 'Završava $date';
  }

  @override
  String get active => 'Aktivna';

  @override
  String get freePlan => 'Besplatni plan';

  @override
  String get configure => 'Konfigurira';

  @override
  String get privacyInformation => 'Informacije o privatnosti';

  @override
  String get yourPrivacyMattersToUs => 'Vaša privatnost je nama važna';

  @override
  String get privacyIntroText =>
      'U Omiju shvaćamo vašu privatnost vrlo ozbiljno. Želimo biti transparentni o podacima koje prikupljamo i kako ih koristimo kako bismo poboljšali naš proizvod za vas. Evo što trebate znati:';

  @override
  String get whatWeTrack => 'Što pratimo';

  @override
  String get anonymityAndPrivacy => 'Anonimnost i privatnost';

  @override
  String get optInAndOptOutOptions => 'Opcije pristanka i odustajanja';

  @override
  String get ourCommitment => 'Naš pristup';

  @override
  String get commitmentText =>
      'Posvećeni smo korištenju podataka koje prikupljamo samo da bi Omi bio bolji proizvod za vas. Vaša privatnost i povjerenje su nam najvažniji.';

  @override
  String get thankYouText =>
      'Hvala vam što ste vrijedni korisnik Omija. Ako imate bilo koja pitanja ili zabrinute, slobodno nam napišite na team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Postavke WiFi sinhronizacije';

  @override
  String get enterHotspotCredentials => 'Unesite vjerodajnice osobnog pristupnog mjesta vašeg telefona';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi sinhronizacija koristi vaš telefon kao osobno pristupno mjesto. Pronađite naziv i lozinku osobnog pristupnog mjesta u Postavkama > Osobno pristupno mjesto.';

  @override
  String get hotspotNameSsid => 'Naziv osobnog pristupnog mjesta (SSID)';

  @override
  String get exampleIphoneHotspot => 'npr. iPhone Personal Hotspot';

  @override
  String get password => 'Lozinka';

  @override
  String get enterHotspotPassword => 'Unesite lozinku osobnog pristupnog mjesta';

  @override
  String get saveCredentials => 'Spremi vjerodajnice';

  @override
  String get clearCredentials => 'Briši vjerodajnice';

  @override
  String get pleaseEnterHotspotName => 'Molimo unesite naziv osobnog pristupnog mjesta';

  @override
  String get wifiCredentialsSaved => 'WiFi vjerodajnice su spremljene';

  @override
  String get wifiCredentialsCleared => 'WiFi vjerodajnice su obrisane';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Sažetak je generiran za $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Nije moguće generirati sažetak. Provjerite da li imate razgovore za taj dan.';

  @override
  String get summaryNotFound => 'Sažetak nije pronađen';

  @override
  String get yourDaysJourney => 'Putovanje vašeg dana';

  @override
  String get highlights => 'Ključni trenutci';

  @override
  String get unresolvedQuestions => 'Neriješena pitanja';

  @override
  String get decisions => 'Odluke';

  @override
  String get learnings => 'Nauci';

  @override
  String get autoDeletesAfterThreeDays => 'Automatski se briše nakon 3 dana.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Grafikon znanja je uspješno obrisan';

  @override
  String get exportStartedMayTakeFewSeconds => 'Izvoz je počeo. To može potrajati nekoliko sekundi...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Ovo će izbrisati sve izvedene podatke grafa znanja (čvorove i veze). Vaša originalna sjećanja će ostati sigurna. Graf će se ponovno izgraditi tijekom vremena ili na sljedeći zahtjev.';

  @override
  String get configureDailySummaryDigest => 'Konfigurira svoj dnevni sažetak stavki za izvršenje';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Pristupa $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'okidano sa $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription i okidano je $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Je $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Nema konfiguriranog pristupa određenim podacima.';

  @override
  String get basicPlanDescription => '1.200 premium minuta + neograničeno na uređaju';

  @override
  String get minutes => 'minuta';

  @override
  String get omiHas => 'Omi ima:';

  @override
  String get premiumMinutesUsed => 'Korištene premium minute.';

  @override
  String get setupOnDevice => 'Postavi na uređaju';

  @override
  String get forUnlimitedFreeTranscription => 'za neograničenu besplatnu transkripciju.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium minuta preostalo.';
  }

  @override
  String get alwaysAvailable => 'uvijek dostupno.';

  @override
  String get importHistory => 'Povijest uvoza';

  @override
  String get noImportsYet => 'Nema uvoza do sada';

  @override
  String get selectZipFileToImport => 'Odaberite .zip datoteku za uvoz!';

  @override
  String get otherDevicesComingSoon => 'Ostali uređaji uskoro dolaze';

  @override
  String get deleteAllLimitlessConversations => 'Obrisati sve Limitless razgovore?';

  @override
  String get deleteAllLimitlessWarning =>
      'Ovo će trajno izbrisati sve razgovore uvezene iz Limitlessa. Ova radnja se ne može poništiti.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Obrisano $count Limitless razgovora';
  }

  @override
  String get failedToDeleteConversations => 'Nije moguće obrisati razgovore';

  @override
  String get deleteImportedData => 'Obriši uvezene podatke';

  @override
  String get statusPending => 'Čekanje';

  @override
  String get statusProcessing => 'Obrada';

  @override
  String get statusCompleted => 'Dovršeno';

  @override
  String get statusFailed => 'Neuspješno';

  @override
  String nConversations(int count) {
    return '$count razgovora';
  }

  @override
  String get pleaseEnterName => 'Molimo unesite ime';

  @override
  String get nameMustBeBetweenCharacters => 'Ime mora biti između 2 i 40 znakova';

  @override
  String get deleteSampleQuestion => 'Obrisati uzorak?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Jeste li sigurni da želite obrisati ${name}ov uzorak?';
  }

  @override
  String get confirmDeletion => 'Potvrdi brisanje';

  @override
  String deletePersonConfirmation(String name) {
    return 'Jeste li sigurni da želite obrisati $name? Ovo će također ukloniti sve povezane uzorke govora.';
  }

  @override
  String get howItWorksTitle => 'Kako funkcionira?';

  @override
  String get howPeopleWorks =>
      'Kada se osoba kreira, možete otići na transkripciju razgovora i dodijeliti joj odgovarajuće segmente, na taj način će Omi moći prepoznati i njezin govor!';

  @override
  String get tapToDelete => 'Dodirnite za brisanje';

  @override
  String get newTag => 'NOVO';

  @override
  String get needHelpChatWithUs => 'Trebate pomoć? Razgovarajte s nama';

  @override
  String get localStorageEnabled => 'Lokalno pohranjivanje je omogućeno';

  @override
  String get localStorageDisabled => 'Lokalno pohranjivanje je onemogućeno';

  @override
  String failedToUpdateSettings(String error) {
    return 'Nije moguće ažurirati postavke: $error';
  }

  @override
  String get privacyNotice => 'Obavijest o privatnosti';

  @override
  String get recordingsMayCaptureOthers =>
      'Snimanja mogu hvatiti glasove drugih. Provjerite da li imate pristanak svih sudionika prije omogućavanja.';

  @override
  String get enable => 'Omogući';

  @override
  String get storeAudioOnPhone => 'Pohrani audio na telefon';

  @override
  String get on => 'Uključeno';

  @override
  String get storeAudioDescription =>
      'Čuvajte sve audio snimke pohranjene lokalno na vašem telefonu. Kada je onemogućeno, samo neuspješna učitavanja se čuvaju kako bi se uštedjelo prostora za pohranu.';

  @override
  String get enableLocalStorage => 'Omogući lokalno pohranjivanje';

  @override
  String get cloudStorageEnabled => 'Pohrana u oblaku je omogućena';

  @override
  String get cloudStorageDisabled => 'Pohrana u oblaku je onemogućena';

  @override
  String get enableCloudStorage => 'Omogući pohranu u oblaku';

  @override
  String get storeAudioOnCloud => 'Pohrani audio u oblak';

  @override
  String get cloudStorageDialogMessage =>
      'Vaša snimanja u realnom vremenu će biti pohranjena u privatnu pohranu u oblaku dok govorite.';

  @override
  String get storeAudioCloudDescription =>
      'Pohranjujte snimanja u realnom vremenu u privatnu pohranu u oblaku dok govorite. Audio se hvaća i sigurno pohranjuje u realnom vremenu.';

  @override
  String get downloadingFirmware => 'Preuzimanje firmvera';

  @override
  String get installingFirmware => 'Instalacija firmvera';

  @override
  String get firmwareUpdateWarning =>
      'Nemojte zatvarati aplikaciju ili isključivati uređaj. Ovo bi moglo oštetiti vaš uređaj.';

  @override
  String get firmwareUpdated => 'Firmver je ažuriran';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Molimo ponovno pokrenite vaš $deviceName kako biste dovršili ažuriranje.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Vaš uređaj je ažuran';

  @override
  String get currentVersion => 'Trenutna verzija';

  @override
  String get latestVersion => 'Najnovija verzija';

  @override
  String get whatsNew => 'Što je novo';

  @override
  String get installUpdate => 'Instaliraj ažuriranje';

  @override
  String get updateNow => 'Ažuriraj sada';

  @override
  String get updateGuide => 'Vodič za ažuriranje';

  @override
  String get checkingForUpdates => 'Provjera ažuriranja';

  @override
  String get checkingFirmwareVersion => 'Provjera verzije firmvera...';

  @override
  String get firmwareUpdate => 'Ažuriranje firmvera';

  @override
  String get payments => 'Plaćanja';

  @override
  String get connectPaymentMethodInfo =>
      'Povežite metodu plaćanja dolje kako biste počeli primati isplate za vaše aplikacije.';

  @override
  String get selectedPaymentMethod => 'Odabrana metoda plaćanja';

  @override
  String get availablePaymentMethods => 'Dostupne metode plaćanja';

  @override
  String get activeStatus => 'Aktivna';

  @override
  String get connectedStatus => 'Povezano';

  @override
  String get notConnectedStatus => 'Nije povezano';

  @override
  String get setActive => 'Postavi kao aktivnu';

  @override
  String get getPaidThroughStripe => 'Dobijte plaćenu za prodaju aplikacije putem Stripea';

  @override
  String get monthlyPayouts => 'Mjesečne isplate';

  @override
  String get monthlyPayoutsDescription =>
      'Primajte mjesečna plaćanja izravno na svoj račun kada dostignete \$10 u zarađenoj';

  @override
  String get secureAndReliable => 'Sigurno i pouzdano';

  @override
  String get stripeSecureDescription => 'Stripe osigurava sigurne i pravovremene transfera vašeg prihoda od aplikacije';

  @override
  String get selectYourCountry => 'Odaberite svoju zemlju';

  @override
  String get countrySelectionPermanent => 'Odabir zemlje je trajno i ne može se promijeniti kasnije.';

  @override
  String get byClickingConnectNow => 'Klikom na \"Povežite se sada\" slažete se s';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account Agreement';

  @override
  String get errorConnectingToStripe => 'Greška pri povezivanju s Stripem! Pokušajte ponovno kasnije.';

  @override
  String get connectingYourStripeAccount => 'Povezivanje vašeg Stripe računa';

  @override
  String get stripeOnboardingInstructions =>
      'Molimo dovršite Stripe onboarding proces u vašem pregledniku. Ova se stranica automatski ažurira nakon što završite.';

  @override
  String get failedTryAgain => 'Neuspješno? Pokušajte ponovno';

  @override
  String get illDoItLater => 'Učinit ću to kasnije';

  @override
  String get successfullyConnected => 'Uspješno povezano!';

  @override
  String get stripeReadyForPayments =>
      'Vaš Stripe račun je sada spreman za primanje plaćanja. Možete odmah početi zarađivati od prodaje svoje aplikacije.';

  @override
  String get updateStripeDetails => 'Ažuriraj Stripe detalje';

  @override
  String get errorUpdatingStripeDetails => 'Greška pri ažuriranju Stripe detalja! Pokušajte ponovno kasnije.';

  @override
  String get updatePayPal => 'Ažuriraj PayPal';

  @override
  String get setUpPayPal => 'Postavi PayPal';

  @override
  String get updatePayPalAccountDetails => 'Ažurirajte detalje vašeg PayPal računa';

  @override
  String get connectPayPalToReceivePayments =>
      'Povežite svoj PayPal račun kako biste počeli primati plaćanja za vaše aplikacije';

  @override
  String get paypalEmail => 'PayPal email';

  @override
  String get paypalMeLink => 'PayPal.me veza';

  @override
  String get stripeRecommendation =>
      'Ako je Stripe dostupan u vašoj zemlji, preporučujemo vam da ga koristite za brže i lakše isplate.';

  @override
  String get updatePayPalDetails => 'Ažuriraj PayPal detalje';

  @override
  String get savePayPalDetails => 'Spremi PayPal detalje';

  @override
  String get pleaseEnterPayPalEmail => 'Molimo unesite vašu PayPal email adresu';

  @override
  String get pleaseEnterPayPalMeLink => 'Molimo unesite vašu PayPal.me vezu';

  @override
  String get doNotIncludeHttpInLink => 'Nemojte uključivati http ili https ili www u vezu';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Molimo unesite valjanu PayPal.me vezu';

  @override
  String get pleaseEnterValidEmail => 'Molimo unesite valjanu email adresu';

  @override
  String get syncingYourRecordings => 'Sinhronizacija vašeg snimanja';

  @override
  String get syncYourRecordings => 'Sinhronizirajte vaša snimanja';

  @override
  String get syncNow => 'Sinhroniziraj sada';

  @override
  String get error => 'Greška';

  @override
  String get speechSamples => 'Uzorci govora';

  @override
  String additionalSampleIndex(String index) {
    return 'Dodatni uzorak $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Trajanje: $seconds sekundi';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Dodatni uzorak govora je uklonjen';

  @override
  String get consentDataMessage =>
      'Nastavljanjem, vaši razgovori, snimke i osobni podaci bit će sigurno pohranjeni na našim poslužiteljima. Vaši audio zapisi i transkripti obrađuju se od strane AI usluga trećih strana (uključujući Deepgram za transkripciju i OpenAI za analizu) kako bi vam pružili uvide pokretane umjetnom inteligencijom i omogućili sve značajke aplikacije.';

  @override
  String get tasksEmptyStateMessage =>
      'Zadaci iz vaših razgovora će se pojavljati ovdje.\\nDodirnite + da biste ručno kreirali jedan.';

  @override
  String get clearChatAction => 'Očisti razgovor';

  @override
  String get enableApps => 'Omogući aplikacije';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'prikaži više ↓';

  @override
  String get showLess => 'prikaži manje ↑';

  @override
  String get loadingYourRecording => 'Učitavanje vašeg snimanja...';

  @override
  String get photoDiscardedMessage => 'Ova fotografija je odbačena jer nije bila značajna.';

  @override
  String get analyzing => 'Analiza...';

  @override
  String get searchCountries => 'Pretraži zemlje';

  @override
  String get checkingAppleWatch => 'Provjera Apple Watcha...';

  @override
  String get installOmiOnAppleWatch => 'Instalirajte Omi na vaš\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Kako biste koristili Apple Watch sa Omijem, morate prvo instalirati Omi aplikaciju na vaš sat.';

  @override
  String get openOmiOnAppleWatch => 'Otvorite Omi na vaš\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi aplikacija je instalirana na vaš Apple Watch. Otvorite je i dodirnite Start kako biste počeli.';

  @override
  String get openWatchApp => 'Otvori Watch aplikaciju';

  @override
  String get iveInstalledAndOpenedTheApp => 'Instalirao/la sam i otvorio/la aplikaciju';

  @override
  String get unableToOpenWatchApp =>
      'Nije moguće otvoriti Apple Watch aplikaciju. Molimo ručno otvorite Watch aplikaciju na vašem Apple Watchu i instalirajte Omi iz \"Available Apps\" sekcije.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch je uspješno povezan!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch još nije dostižan. Provjerite da li je Omi aplikacija otvorena na vašem satnom.';

  @override
  String errorCheckingConnection(String error) {
    return 'Greška pri provjeri veze: $error';
  }

  @override
  String get muted => 'Utišano';

  @override
  String get processNow => 'Obradi sada';

  @override
  String get finishedConversation => 'Završen razgovor?';

  @override
  String get stopRecordingConfirmation => 'Jeste li sigurni da želite zaustaviti snimanje i sažeti razgovor sada?';

  @override
  String get conversationEndsManually => 'Razgovor će završiti samo ručno.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Razgovor je sažet nakon $minutes minut$suffix bez govora.';
  }

  @override
  String get dontAskAgain => 'Nemoj me pitati ponovno';

  @override
  String get waitingForTranscriptOrPhotos => 'Čekanje na transkripciju ili fotografije...';

  @override
  String get noSummaryYet => 'Nema sažetka do sada';

  @override
  String hints(String text) {
    return 'Savjeti: $text';
  }

  @override
  String get testConversationPrompt => 'Testiraj upitu razgovora';

  @override
  String get prompt => 'Upit';

  @override
  String get result => 'Rezultat:';

  @override
  String get compareTranscripts => 'Usporedi transkripcije';

  @override
  String get notHelpful => 'Nije od pomoći';

  @override
  String get exportTasksWithOneTap => 'Izvezi zadatke s jednim dodirom!';

  @override
  String get inProgress => 'U tijeku';

  @override
  String get photos => 'Fotografije';

  @override
  String get rawData => 'Siroviti podaci';

  @override
  String get content => 'Sadržaj';

  @override
  String get noContentToDisplay => 'Nema sadržaja za prikaz';

  @override
  String get noSummary => 'Nema sažetka';

  @override
  String get updateOmiFirmware => 'Ažuriraj Omi firmver';

  @override
  String get anErrorOccurredTryAgain => 'Došlo je do greške. Pokušajte ponovno.';

  @override
  String get welcomeBackSimple => 'Dobrodošli natrag';

  @override
  String get addVocabularyDescription => 'Dodajte riječi koje Omi treba prepoznati tijekom transkripcije.';

  @override
  String get enterWordsCommaSeparated => 'Unesite riječi (odvojene zarezima)';

  @override
  String get whenToReceiveDailySummary => 'Kada primiti dnevni sažetak';

  @override
  String get checkingNextSevenDays => 'Provjera sljedećih 7 dana';

  @override
  String failedToDeleteError(String error) {
    return 'Nije moguće obrisati: $error';
  }

  @override
  String get developerApiKeys => 'Ključi razvojnog API-ja';

  @override
  String get noApiKeysCreateOne => 'Nema API ključeva. Kreirajte jedan kako biste počeli.';

  @override
  String get commandRequired => '⌘ obavezno';

  @override
  String get spaceKey => 'Razmak';

  @override
  String loadMoreRemaining(String count) {
    return 'Učitaj više ($count preostalo)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% korisnik';
  }

  @override
  String get wrappedMinutes => 'minuta';

  @override
  String get wrappedConversations => 'razgovora';

  @override
  String get wrappedDaysActive => 'dana aktivnosti';

  @override
  String get wrappedYouTalkedAbout => 'Govorili ste o';

  @override
  String get wrappedActionItems => 'Stavke za izvršenje';

  @override
  String get wrappedTasksCreated => 'kreiranih zadataka';

  @override
  String get wrappedCompleted => 'dovršeno';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% stopa dovršenosti';
  }

  @override
  String get wrappedYourTopDays => 'Vaši najbolji dani';

  @override
  String get wrappedBestMoments => 'Najbolji trenutci';

  @override
  String get wrappedMyBuddies => 'Moji prijatelji';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Nisu mogli smisliti stajem govoriti o';

  @override
  String get wrappedShow => 'EMISIJA';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'KNJIGA';

  @override
  String get wrappedCelebrity => 'ZVIJEZDA';

  @override
  String get wrappedFood => 'HRANA';

  @override
  String get wrappedMovieRecs => 'Preporuke filmova za prijatelje';

  @override
  String get wrappedBiggest => 'Najveći';

  @override
  String get wrappedStruggle => 'Borba';

  @override
  String get wrappedButYouPushedThrough => 'Ali prkosili ste 💪';

  @override
  String get wrappedWin => 'Pobjeda';

  @override
  String get wrappedYouDidIt => 'Učinio si to! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 fraza';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'razg';

  @override
  String get wrappedDays => 'dana';

  @override
  String get wrappedMyBuddiesLabel => 'MOJI PRIJATELJI';

  @override
  String get wrappedObsessionsLabel => 'OPSJEDNUTOSTI';

  @override
  String get wrappedStruggleLabel => 'BORBA';

  @override
  String get wrappedWinLabel => 'POBJEDA';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRAZE';

  @override
  String get wrappedLetsHitRewind => 'Vratimo se na vaš';

  @override
  String get wrappedGenerateMyWrapped => 'Generiraj moj Wrapped';

  @override
  String get wrappedProcessingDefault => 'Obrada...';

  @override
  String get wrappedCreatingYourStory => 'Kreiranje vaše\n2025 priče...';

  @override
  String get wrappedSomethingWentWrong => 'Nešto je pošlo\nnaopako';

  @override
  String get wrappedAnErrorOccurred => 'Došlo je do greške';

  @override
  String get wrappedTryAgain => 'Pokušaj ponovno';

  @override
  String get wrappedNoDataAvailable => 'Nema dostupnih podataka';

  @override
  String get wrappedOmiLifeRecap => 'Omi životni pregled';

  @override
  String get wrappedSwipeUpToBegin => 'Swipenite gore za početak';

  @override
  String get wrappedShareText => 'Moj 2025, zapamćen od Omija ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Nije moguće dijeliti. Pokušajte ponovno.';

  @override
  String get wrappedFailedToStartGeneration => 'Nije moguće pokrenuti generiranje. Pokušajte ponovno.';

  @override
  String get wrappedStarting => 'Pokretanje...';

  @override
  String get wrappedShare => 'Dijeliti';

  @override
  String get wrappedShareYourWrapped => 'Dijelite svoj Wrapped';

  @override
  String get wrappedMy2025 => 'Moj 2025';

  @override
  String get wrappedRememberedByOmi => 'zapamćen od Omija';

  @override
  String get wrappedMostFunDay => 'Najzabavniji';

  @override
  String get wrappedMostProductiveDay => 'Najprodukivniji';

  @override
  String get wrappedMostIntenseDay => 'Najintenzivniji';

  @override
  String get wrappedFunniestMoment => 'Najsmješniji';

  @override
  String get wrappedMostCringeMoment => 'Najbolji cringe trenutak';

  @override
  String get wrappedMinutesLabel => 'minuta';

  @override
  String get wrappedConversationsLabel => 'razgovora';

  @override
  String get wrappedDaysActiveLabel => 'dana aktivnosti';

  @override
  String get wrappedTasksGenerated => 'generirani zadaci';

  @override
  String get wrappedTasksCompleted => 'dovršeni zadaci';

  @override
  String get wrappedTopFivePhrases => 'Top 5 fraza';

  @override
  String get wrappedAGreatDay => 'Odličan dan';

  @override
  String get wrappedGettingItDone => 'Dobivanje toga';

  @override
  String get wrappedAChallenge => 'Izazov';

  @override
  String get wrappedAHilariousMoment => 'Smiješan trenutak';

  @override
  String get wrappedThatAwkwardMoment => 'Taj neugodni trenutak';

  @override
  String get wrappedYouHadFunnyMoments => 'Imali ste nekoliko smiješnih trenutaka ove godine!';

  @override
  String get wrappedWeveAllBeenThere => 'Svi smo bili tamo!';

  @override
  String get wrappedFriend => 'Prijatelj';

  @override
  String get wrappedYourBuddy => 'Vaš prijatelj!';

  @override
  String get wrappedNotMentioned => 'Nije spomenuto';

  @override
  String get wrappedTheHardPart => 'Teški dio';

  @override
  String get wrappedPersonalGrowth => 'Osobni rast';

  @override
  String get wrappedFunDay => 'Zabava';

  @override
  String get wrappedProductiveDay => 'Produktivno';

  @override
  String get wrappedIntenseDay => 'Intenzivno';

  @override
  String get wrappedFunnyMomentTitle => 'Smiješan trenutak';

  @override
  String get wrappedCringeMomentTitle => 'Cringe trenutak';

  @override
  String get wrappedYouTalkedAboutBadge => 'Govorili ste o';

  @override
  String get wrappedCompletedLabel => 'Dovršeno';

  @override
  String get wrappedMyBuddiesCard => 'Moji prijatelji';

  @override
  String get wrappedBuddiesLabel => 'PRIJATELJI';

  @override
  String get wrappedObsessionsLabelUpper => 'OPSJEDNUTOSTI';

  @override
  String get wrappedStruggleLabelUpper => 'BORBA';

  @override
  String get wrappedWinLabelUpper => 'POBJEDA';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRAZE';

  @override
  String get wrappedYourHeader => 'Vaš';

  @override
  String get wrappedTopDaysHeader => 'Najbolji dani';

  @override
  String get wrappedYourTopDaysBadge => 'Vaši najbolji dani';

  @override
  String get wrappedBestHeader => 'Najbolji';

  @override
  String get wrappedMomentsHeader => 'Trenutci';

  @override
  String get wrappedBestMomentsBadge => 'Najbolji trenutci';

  @override
  String get wrappedBiggestHeader => 'Najveći';

  @override
  String get wrappedStruggleHeader => 'Borba';

  @override
  String get wrappedWinHeader => 'Pobjeda';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ali prkosili ste 💪';

  @override
  String get wrappedYouDidItEmoji => 'Učinio si to! 🎉';

  @override
  String get wrappedHours => 'sati';

  @override
  String get wrappedActions => 'radnje';

  @override
  String get multipleSpeakersDetected => 'Detektirano više govornika';

  @override
  String get multipleSpeakersDescription =>
      'Čini se da u snimanju ima više govornika. Provjerite da li ste na tihoj lokaciji i pokušajte ponovno.';

  @override
  String get invalidRecordingDetected => 'Detektirano nije valjano snimanje';

  @override
  String get notEnoughSpeechDescription => 'Nije dovoljno govora detektirano. Govorite više i pokušajte ponovno.';

  @override
  String get speechDurationDescription => 'Molimo osigurajte da govorite najmanje 5 sekundi i ne više od 90.';

  @override
  String get connectionLostDescription =>
      'Veza je prekinuta. Molimo provjerite vašu internetsku vezu i pokušajte ponovno.';

  @override
  String get howToTakeGoodSample => 'Kako snimiti dobar primjer?';

  @override
  String get goodSampleInstructions =>
      '1. Osigurajte da ste na tiskom mjestu.\n2. Govorite jasno i prirodno.\n3. Osigurajte da je vaš uređaj u prirodnoj poziciji, na vašoj vratu.\n\nKad je kreiran, uvijek ga možete poboljšati ili ponoviti.';

  @override
  String get noDeviceConnectedUseMic => 'Nema povezanog uređaja. Koristit će se mikrofon telefona.';

  @override
  String get doItAgain => 'Pokušajte ponovno';

  @override
  String get listenToSpeechProfile => 'Slušajte moj profil govora ➡️';

  @override
  String get recognizingOthers => 'Prepoznavanje drugih 👀';

  @override
  String get keepGoingGreat => 'Nastavite, odličan ste';

  @override
  String get somethingWentWrongTryAgain => 'Nešto je pošlo po zlu! Molimo pokušajte ponovno kasnije.';

  @override
  String get uploadingVoiceProfile => 'Učitavanje vašeg profila glasa....';

  @override
  String get memorizingYourVoice => 'Memoriziranje vašeg glasa...';

  @override
  String get personalizingExperience => 'Prilagođavanje vašeg iskustva...';

  @override
  String get keepSpeakingUntil100 => 'Govorite dok ne postignete 100%.';

  @override
  String get greatJobAlmostThere => 'Odličan posao, gotovo ste tu';

  @override
  String get soCloseJustLittleMore => 'Vrlo blizu, trebate samo malo više';

  @override
  String get notificationFrequency => 'Učestalost obavijesti';

  @override
  String get controlNotificationFrequency => 'Kontrolirajte kako često vam Omi šalje proaktivne obavijesti.';

  @override
  String get yourScore => 'Vaš rezultat';

  @override
  String get dailyScoreBreakdown => 'Dnevni pregled rezultata';

  @override
  String get todaysScore => 'Današnji rezultat';

  @override
  String get tasksCompleted => 'Završeni zadaci';

  @override
  String get completionRate => 'Stopa završetka';

  @override
  String get howItWorks => 'Kako funkcionira';

  @override
  String get dailyScoreExplanation =>
      'Vaš dnevni rezultat temelji se na završetku zadataka. Završite svoje zadatke da poboljšate svoj rezultat!';

  @override
  String get notificationFrequencyDescription =>
      'Kontrolirajte kako često vam Omi šalje proaktivne obavijesti i podsjetnika.';

  @override
  String get sliderOff => 'Isključeno';

  @override
  String get sliderMax => 'Maksimalno';

  @override
  String summaryGeneratedFor(String date) {
    return 'Sažetak generiran za $date';
  }

  @override
  String get failedToGenerateSummary => 'Neuspješno je generiranje sažetka. Osigurajte da imate razgovore za taj dan.';

  @override
  String get recap => 'Pregled';

  @override
  String deleteQuoted(String name) {
    return 'Izbrisati \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Premjestiti $count razgovora u:';
  }

  @override
  String get noFolder => 'Nema mape';

  @override
  String get removeFromAllFolders => 'Ukloniti iz svih mapa';

  @override
  String get buildAndShareYourCustomApp => 'Izgradite i podijelite svoju prilagođenu aplikaciju';

  @override
  String get searchAppsPlaceholder => 'Pretraživanje 1500+ aplikacija';

  @override
  String get filters => 'Filtri';

  @override
  String get frequencyOff => 'Isključeno';

  @override
  String get frequencyMinimal => 'Minimalno';

  @override
  String get frequencyLow => 'Nisko';

  @override
  String get frequencyBalanced => 'Balansirano';

  @override
  String get frequencyHigh => 'Visoko';

  @override
  String get frequencyMaximum => 'Maksimalno';

  @override
  String get frequencyDescOff => 'Bez proaktivnih obavijesti';

  @override
  String get frequencyDescMinimal => 'Samo kritični podsjetnici';

  @override
  String get frequencyDescLow => 'Samo važna ažuriranja';

  @override
  String get frequencyDescBalanced => 'Redoviti korisni poticaji';

  @override
  String get frequencyDescHigh => 'Česti kontrolni pozivi';

  @override
  String get frequencyDescMaximum => 'Ostanite stalno uključeni';

  @override
  String get clearChatQuestion => 'Obrisati razgovor?';

  @override
  String get syncingMessages => 'Sinkronizacija poruka sa serverom...';

  @override
  String get chatAppsTitle => 'Aplikacije za razgovor';

  @override
  String get selectApp => 'Odaberite aplikaciju';

  @override
  String get noChatAppsEnabled =>
      'Nema omogućenih aplikacija za razgovor.\nTapnite \"Omogući aplikacije\" da dodate neke.';

  @override
  String get disable => 'Onemogući';

  @override
  String get photoLibrary => 'Biblioteka fotografija';

  @override
  String get chooseFile => 'Odaberite datoteku';

  @override
  String get connectAiAssistantsToYourData => 'Povežite AI asistente sa vašim podacima';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Pratite svoje osobne ciljeve na početnoj stranici';

  @override
  String get deleteRecording => 'Izbrisati snimku';

  @override
  String get thisCannotBeUndone => 'Ovo se ne može poništiti.';

  @override
  String get sdCard => 'SD kartica';

  @override
  String get fromSd => 'Sa SD kartice';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Brzi prijenos';

  @override
  String get syncingStatus => 'Sinkronizacija';

  @override
  String get failedStatus => 'Neuspješno';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Metoda prijenosa';

  @override
  String get fast => 'Brzo';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Otkaži sinkronizaciju';

  @override
  String get cancelSyncMessage => 'Podatci koji su već preuzeti će biti spremljeni. Možete nastaviti kasnije.';

  @override
  String get syncCancelled => 'Sinkronizacija otkazana';

  @override
  String get deleteProcessedFiles => 'Izbrisati obrađene datoteke';

  @override
  String get processedFilesDeleted => 'Obrađene datoteke obrisane';

  @override
  String get wifiEnableFailed => 'Neuspješno omogućavanje WiFi-ja na uređaju. Molimo pokušajte ponovno.';

  @override
  String get deviceNoFastTransfer => 'Vaš uređaj ne podržava brzi prijenos. Umjesto toga koristite Bluetooth.';

  @override
  String get enableHotspotMessage => 'Molimo omogućite vrelu točku vašeg telefona i pokušajte ponovno.';

  @override
  String get transferStartFailed => 'Neuspješan početak prijenosa. Molimo pokušajte ponovno.';

  @override
  String get deviceNotResponding => 'Uređaj nije odgovorio. Molimo pokušajte ponovno.';

  @override
  String get invalidWifiCredentials => 'Nevaljani WiFi kredencijali. Provjerite postavke vruće točke.';

  @override
  String get wifiConnectionFailed => 'Veza WiFi-ja nije uspjela. Molimo pokušajte ponovno.';

  @override
  String get sdCardProcessing => 'Obrada SD kartice';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Obrada $count snimke(a). Datoteke će biti uklonjene sa SD kartice nakon toga.';
  }

  @override
  String get process => 'Obrada';

  @override
  String get wifiSyncFailed => 'WiFi sinkronizacija neuspješna';

  @override
  String get processingFailed => 'Obrada neuspješna';

  @override
  String get downloadingFromSdCard => 'Preuzimanje sa SD kartice';

  @override
  String processingProgress(int current, int total) {
    return 'Obrada $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count razgovora kreiran(o)';
  }

  @override
  String get internetRequired => 'Potreban internet';

  @override
  String get processAudio => 'Obrada zvuka';

  @override
  String get start => 'Početak';

  @override
  String get noRecordings => 'Nema snimki';

  @override
  String get audioFromOmiWillAppearHere => 'Zvuk sa vašeg Omi uređaja će se pojaviti ovdje';

  @override
  String get deleteProcessed => 'Izbrisati obrađene';

  @override
  String get tryDifferentFilter => 'Pokušajte drugi filter';

  @override
  String get recordings => 'Snimke';

  @override
  String get enableRemindersAccess =>
      'Molimo omogućite pristup podsjetnicima u postavkama da koristite Apple podsjetnika';

  @override
  String todayAtTime(String time) {
    return 'Danas u $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Jučer u $time';
  }

  @override
  String get lessThanAMinute => 'Manje od minute';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(a)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count sat(a)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Procijenjeno: $time preostaje';
  }

  @override
  String get summarizingConversation => 'Sažimanje razgovora...\nOvo može potrajati nekoliko sekundi';

  @override
  String get resummarizingConversation => 'Ponovno sažimanje razgovora...\nOvo može potrajati nekoliko sekundi';

  @override
  String get nothingInterestingRetry => 'Ništa zanimljivo pronađeno,\nželite li pokušati ponovno?';

  @override
  String get noSummaryForConversation => 'Sažetak nije dostupan\nza ovaj razgovor.';

  @override
  String get unknownLocation => 'Nepoznata lokacija';

  @override
  String get couldNotLoadMap => 'Nije se mogla učitati mapa';

  @override
  String get triggerConversationIntegration => 'Pokrenite integraciju kreiranja razgovora';

  @override
  String get webhookUrlNotSet => 'URL webhook-a nije postavljen';

  @override
  String get setWebhookUrlInSettings => 'Molimo postavite URL webhook-a u postavke razvoja da koristite ovu značajku.';

  @override
  String get sendWebUrl => 'Pošalji web URL';

  @override
  String get sendTranscript => 'Pošalji transkripciju';

  @override
  String get sendSummary => 'Pošalji sažetak';

  @override
  String get debugModeDetected => 'Detektiran način rada za otklanjanje grešaka';

  @override
  String get performanceReduced => 'Performanse smanjene 5-10 puta. Koristite način rada za izdavanje.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Automatsko zatvaranje za ${seconds}s';
  }

  @override
  String get modelRequired => 'Potreban model';

  @override
  String get downloadWhisperModel => 'Molimo preuzmite Whisper model prije spremanja.';

  @override
  String get deviceNotCompatible => 'Uređaj nije kompatibilan';

  @override
  String get deviceRequirements => 'Vaš uređaj ne zadovoljava zahtjeve za transkripciju na uređaju.';

  @override
  String get willLikelyCrash => 'Omogućavanje ovoga vjerojatno će uzrokovati pad ili zamrzavanje aplikacije.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkripcija će biti značajno sporija i manje točna.';

  @override
  String get proceedAnyway => 'Nastavi svejedno';

  @override
  String get olderDeviceDetected => 'Detektiran stariji uređaj';

  @override
  String get onDeviceSlower => 'Transkripcija na uređaju može biti sporija na ovom uređaju.';

  @override
  String get batteryUsageHigher => 'Potrošnja baterije bit će veća nego u transkripciji na oblaku.';

  @override
  String get considerOmiCloud => 'Razmotriti korištenje Omi Cloud-a za bolje performanse.';

  @override
  String get highResourceUsage => 'Visoka potrošnja resursa';

  @override
  String get onDeviceIntensive => 'Transkripcija na uređaju je računski intenzivna.';

  @override
  String get batteryDrainIncrease => 'Istekovanje baterije će se značajno povećati.';

  @override
  String get deviceMayWarmUp => 'Uređaj može zagrijati se tijekom duže upotrebe.';

  @override
  String get speedAccuracyLower => 'Brzina i točnost mogu biti manje nego kod Cloud modela.';

  @override
  String get cloudProvider => 'Pružatelj usluga u oblaku';

  @override
  String get premiumMinutesInfo =>
      '1.200 premium minuta/mjesec. Kartica Na uređaju nudi neograničenu besplatnu transkripciju.';

  @override
  String get viewUsage => 'Prikaži upotrebu';

  @override
  String get localProcessingInfo => 'Zvuk se obrađuje lokalno. Radi bez veze, privatnije, ali koristi više baterije.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Upozorenje o performansama';

  @override
  String get largeModelWarning =>
      'Ovaj model je velik i može srušiti aplikaciju ili biti vrlo spora na mobilnim uređajima.\n\n\"small\" ili \"base\" se preporučuju.';

  @override
  String get usingNativeIosSpeech => 'Korištenje nativnog iOS prepoznavanja govora';

  @override
  String get noModelDownloadRequired => 'Koristit će se motor govora vašeg uređaja. Preuzimanje modela nije potrebno.';

  @override
  String get modelReady => 'Model je spreman';

  @override
  String get redownload => 'Ponovno preuzmi';

  @override
  String get doNotCloseApp => 'Molimo ne zatvarajte aplikaciju.';

  @override
  String get downloading => 'Preuzimanje...';

  @override
  String get downloadModel => 'Preuzmi model';

  @override
  String estimatedSize(String size) {
    return 'Procijenjana veličina: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Dostupno prostora: $space';
  }

  @override
  String get notEnoughSpace => 'Upozorenje: Nema dovoljno prostora!';

  @override
  String get download => 'Preuzmi';

  @override
  String downloadError(String error) {
    return 'Greška preuzimanja: $error';
  }

  @override
  String get cancelled => 'Otkazano';

  @override
  String get deviceNotCompatibleTitle => 'Uređaj nije kompatibilan';

  @override
  String get deviceNotMeetRequirements => 'Vaš uređaj ne zadovoljava zahtjeve za transkripciju na uređaju.';

  @override
  String get transcriptionSlowerOnDevice => 'Transkripcija na uređaju može biti sporija na ovom uređaju.';

  @override
  String get computationallyIntensive => 'Transkripcija na uređaju je računski intenzivna.';

  @override
  String get batteryDrainSignificantly => 'Istekovanje baterije će se značajno povećati.';

  @override
  String get premiumMinutesMonth =>
      '1.200 premium minuta/mjesec. Kartica Na uređaju nudi neograničenu besplatnu transkripciju.';

  @override
  String get audioProcessedLocally => 'Zvuk se obrađuje lokalno. Radi bez veze, privatnije, ali koristi više baterije.';

  @override
  String get languageLabel => 'Jezik';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Ovaj model je velik i može srušiti aplikaciju ili biti vrlo spora na mobilnim uređajima.\n\n\"small\" ili \"base\" se preporučuju.';

  @override
  String get nativeEngineNoDownload => 'Koristit će se motor govora vašeg uređaja. Preuzimanje modela nije potrebno.';

  @override
  String modelReadyWithName(String model) {
    return 'Model je spreman ($model)';
  }

  @override
  String get reDownload => 'Ponovno preuzmi';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Preuzimanje $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Pripremanje $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Greška preuzimanja: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Procijenjana veličina: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Dostupno prostora: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omi-jeva ugrađena transkripcija u realnom vremenu optimizirana je za razgovore u realnom vremenu sa automatskim prepoznavanjem govornika i dijalizacijom.';

  @override
  String get reset => 'Resetiraj';

  @override
  String get useTemplateFrom => 'Koristi predložak od';

  @override
  String get selectProviderTemplate => 'Odaberite predložak pružatelja...';

  @override
  String get quicklyPopulateResponse => 'Brzo popunite sa poznatim formatom odgovora pružatelja';

  @override
  String get quicklyPopulateRequest => 'Brzo popunite sa poznatim formatom zahtjeva pružatelja';

  @override
  String get invalidJsonError => 'Neispravan JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Preuzmi model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Uređaj';

  @override
  String get chatAssistantsTitle => 'Asistenti za razgovor';

  @override
  String get permissionReadConversations => 'Čitaj razgovore';

  @override
  String get permissionReadMemories => 'Čitaj uspomene';

  @override
  String get permissionReadTasks => 'Čitaj zadatke';

  @override
  String get permissionCreateConversations => 'Kreiraj razgovore';

  @override
  String get permissionCreateMemories => 'Kreiraj uspomene';

  @override
  String get permissionTypeAccess => 'Pristup';

  @override
  String get permissionTypeCreate => 'Kreiraj';

  @override
  String get permissionTypeTrigger => 'Pokrenuti';

  @override
  String get permissionDescReadConversations => 'Ova aplikacija može pristupiti vašim razgovorima.';

  @override
  String get permissionDescReadMemories => 'Ova aplikacija može pristupiti vašim uspomenama.';

  @override
  String get permissionDescReadTasks => 'Ova aplikacija može pristupiti vašim zadacima.';

  @override
  String get permissionDescCreateConversations => 'Ova aplikacija može kreirati nove razgovore.';

  @override
  String get permissionDescCreateMemories => 'Ova aplikacija može kreirati nove uspomene.';

  @override
  String get realtimeListening => 'Slušanje u realnom vremenu';

  @override
  String get setupCompleted => 'Dovršeno';

  @override
  String get pleaseSelectRating => 'Molimo odaberite ocjenu';

  @override
  String get writeReviewOptional => 'Napišite recenziju (opciono)';

  @override
  String get setupQuestionsIntro => 'Pomoći nam poboljšati Omi odgovarajući na nekoliko pitanja. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Što radite?';

  @override
  String get setupQuestionUsage => '2. Gdje planirate koristiti svoj Omi?';

  @override
  String get setupQuestionAge => '3. Koji je vaš raspon godina?';

  @override
  String get setupAnswerAllQuestions => 'Niste odgovorili na sva pitanja! 🥺';

  @override
  String get setupSkipHelp => 'Preskoči, ne želim pomoći :C';

  @override
  String get professionEntrepreneur => 'Poduzetnik';

  @override
  String get professionSoftwareEngineer => 'Softverski inženjer';

  @override
  String get professionProductManager => 'Upravitelj proizvoda';

  @override
  String get professionExecutive => 'Izvršitelj';

  @override
  String get professionSales => 'Prodaja';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'Na radu';

  @override
  String get usageIrlEvents => 'IRL događaji';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'U društvenim okruženjima';

  @override
  String get usageEverywhere => 'Svugdje';

  @override
  String get customBackendUrlTitle => 'Prilagođeni URL pozadinskog sustava';

  @override
  String get backendUrlLabel => 'URL pozadinskog sustava';

  @override
  String get saveUrlButton => 'Spremi URL';

  @override
  String get enterBackendUrlError => 'Molimo unesite URL pozadinskog sustava';

  @override
  String get urlMustEndWithSlashError => 'URL mora završiti sa \"/\"';

  @override
  String get invalidUrlError => 'Molimo unesite valjani URL';

  @override
  String get backendUrlSavedSuccess => 'URL pozadinskog sustava je uspješno spremljen!';

  @override
  String get signInTitle => 'Prijava';

  @override
  String get signInButton => 'Prijava';

  @override
  String get enterEmailError => 'Molimo unesite vašu e-poštu';

  @override
  String get invalidEmailError => 'Molimo unesite valjanu e-poštu';

  @override
  String get enterPasswordError => 'Molimo unesite vašu lozinku';

  @override
  String get passwordMinLengthError => 'Lozinka mora biti najmanje 8 znakova duga';

  @override
  String get signInSuccess => 'Prijava je uspješna!';

  @override
  String get alreadyHaveAccountLogin => 'Već imate račun? Prijavite se';

  @override
  String get emailLabel => 'E-pošta';

  @override
  String get passwordLabel => 'Lozinka';

  @override
  String get createAccountTitle => 'Kreiraj račun';

  @override
  String get nameLabel => 'Ime';

  @override
  String get repeatPasswordLabel => 'Ponovite lozinku';

  @override
  String get signUpButton => 'Registracija';

  @override
  String get enterNameError => 'Molimo unesite vaše ime';

  @override
  String get passwordsDoNotMatch => 'Lozinke se ne poklapaju';

  @override
  String get signUpSuccess => 'Registracija je uspješna!';

  @override
  String get loadingKnowledgeGraph => 'Učitavanje grafa znanja...';

  @override
  String get noKnowledgeGraphYet => 'Nema grafa znanja još';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Gradnja vašeg grafa znanja iz uspomena...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Vaš graf znanja će se automatski graditi kako kreirate nove uspomene.';

  @override
  String get buildGraphButton => 'Gradi graf';

  @override
  String get checkOutMyMemoryGraph => 'Pogledajte moj graf uspomena!';

  @override
  String get getButton => 'Preuzmi';

  @override
  String openingApp(String appName) {
    return 'Otvaranje $appName...';
  }

  @override
  String get writeSomething => 'Napišite nešto';

  @override
  String get submitReply => 'Pošalji odgovor';

  @override
  String get editYourReply => 'Uredite svoj odgovor';

  @override
  String get replyToReview => 'Odgovori na recenziju';

  @override
  String get rateAndReviewThisApp => 'Ocijenite i pregledajte ovu aplikaciju';

  @override
  String get noChangesInReview => 'Nema promjena u recenziji za ažuriranje.';

  @override
  String get cantRateWithoutInternet => 'Nije moguće ocijeniti aplikaciju bez internetske veze.';

  @override
  String get appAnalytics => 'Analitika aplikacije';

  @override
  String get learnMoreLink => 'saznajte više';

  @override
  String get moneyEarned => 'Zaradjena sredstva';

  @override
  String get writeYourReply => 'Napišite svoj odgovor...';

  @override
  String get replySentSuccessfully => 'Odgovor je uspješno poslan';

  @override
  String failedToSendReply(String error) {
    return 'Neuspješno slanje odgovora: $error';
  }

  @override
  String get send => 'Pošalji';

  @override
  String starFilter(int count) {
    return '$count zvijezda';
  }

  @override
  String get noReviewsFound => 'Nema pronađenih recenzija';

  @override
  String get editReply => 'Uredi odgovor';

  @override
  String get reply => 'Odgovori';

  @override
  String starFilterLabel(int count) {
    return '$count zvijezda';
  }

  @override
  String get sharePublicLink => 'Dijeli javnu vezu';

  @override
  String get connectedKnowledgeData => 'Povezani podaci znanja';

  @override
  String get enterName => 'Unesite ime';

  @override
  String get goal => 'CILJ';

  @override
  String get tapToTrackThisGoal => 'Tapnite da pratite ovaj cilj';

  @override
  String get tapToSetAGoal => 'Tapnite da postavite cilj';

  @override
  String get processedConversations => 'Obrađeni razgovori';

  @override
  String get updatedConversations => 'Ažurirani razgovori';

  @override
  String get newConversations => 'Novi razgovori';

  @override
  String get summaryTemplate => 'Predložak sažetka';

  @override
  String get suggestedTemplates => 'Prijedloženi predlošci';

  @override
  String get otherTemplates => 'Ostali predlošci';

  @override
  String get availableTemplates => 'Dostupni predlošci';

  @override
  String get getCreative => 'Budite kreativni';

  @override
  String get defaultLabel => 'Zadano';

  @override
  String get lastUsedLabel => 'Zadnje korišteno';

  @override
  String get setDefaultApp => 'Postavi zadanu aplikaciju';

  @override
  String setDefaultAppContent(String appName) {
    return 'Postavi $appName kao zadanu aplikaciju za sažimanje?\\n\\nOva aplikacija će biti automatski korištena za sve budućne sažetke razgovora.';
  }

  @override
  String get setDefaultButton => 'Postavi zadanu';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName postavljen kao zadana aplikacija za sažimanje';
  }

  @override
  String get createCustomTemplate => 'Kreiraj prilagođeni predložak';

  @override
  String get allTemplates => 'Svi predlošci';

  @override
  String failedToInstallApp(String appName) {
    return 'Neuspješna instalacija $appName. Molimo pokušajte ponovno.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Greška pri instalaciji $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Označi govornika $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Osoba s tim imenom već postoji.';

  @override
  String get selectYouFromList => 'Da označite sebe, molimo odaberite \"Vi\" sa popisa.';

  @override
  String get enterPersonsName => 'Unesite ime osobe';

  @override
  String get addPerson => 'Dodaj osobu';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Označi druge segmente od ovog govornika ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Označi druge segmente';

  @override
  String get managePeople => 'Upravljajte ljudima';

  @override
  String get shareViaSms => 'Dijeli putem SMS-a';

  @override
  String get selectContactsToShareSummary => 'Odaberite kontakte sa kojima ćete podijeliti sažetak razgovora';

  @override
  String get searchContactsHint => 'Pretraživanje kontakata...';

  @override
  String contactsSelectedCount(int count) {
    return '$count odabrano';
  }

  @override
  String get clearAllSelection => 'Očisti sve';

  @override
  String get selectContactsToShare => 'Odaberite kontakte za dijeljenje';

  @override
  String shareWithContactCount(int count) {
    return 'Dijeli sa $count kontaktom';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Dijeli sa $count kontakata';
  }

  @override
  String get contactsPermissionRequired => 'Potrebna dozvola za kontakte';

  @override
  String get contactsPermissionRequiredForSms => 'Dozvola za kontakte je potrebna za dijeljenje putem SMS-a';

  @override
  String get grantContactsPermissionForSms => 'Molimo dodijelite dozvolu za kontakte za dijeljenje putem SMS-a';

  @override
  String get noContactsWithPhoneNumbers => 'Nema pronađenih kontakata sa brojevima telefona';

  @override
  String get noContactsMatchSearch => 'Nema kontakata koji se poklapaju sa vašom pretragom';

  @override
  String get failedToLoadContacts => 'Neuspješno učitavanje kontakata';

  @override
  String get failedToPrepareConversationForSharing =>
      'Neuspješno pripremanje razgovora za dijeljenje. Molimo pokušajte ponovno.';

  @override
  String get couldNotOpenSmsApp => 'Nije se mogla otvoriti aplikacija za SMS. Molimo pokušajte ponovno.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Evo o čemu smo razgovarali: $link';
  }

  @override
  String get wifiSync => 'WiFi sinkronizacija';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopiran u međumemoriju';
  }

  @override
  String get wifiConnectionFailedTitle => 'Veza nije uspjela';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Povezivanje sa $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Omogući WiFi na $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Povežite se na $deviceName';
  }

  @override
  String get recordingDetails => 'Detalji snimke';

  @override
  String get storageLocationSdCard => 'SD kartica';

  @override
  String get storageLocationLimitlessPendant => 'Limitless privjesak';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (memorija)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Spremljeno na $deviceName';
  }

  @override
  String get transferring => 'Prijenos...';

  @override
  String get transferRequired => 'Potreban prijenos';

  @override
  String get downloadingAudioFromSdCard => 'Preuzimanje zvuka sa SD kartice vašeg uređaja';

  @override
  String get transferRequiredDescription =>
      'Ova snimka je spremljena na SD kartici vašeg uređaja. Prenesite je na telefon kako biste je reproducirali ili podijelili.';

  @override
  String get cancelTransfer => 'Otkaži prijenos';

  @override
  String get transferToPhone => 'Prijenos na telefon';

  @override
  String get privateAndSecureOnDevice => 'Privatno i sigurno na vašem uređaju';

  @override
  String get recordingInfo => 'Informacije o snimanju';

  @override
  String get transferInProgress => 'Prijenos u tijeku...';

  @override
  String get shareRecording => 'Dijeli Snimku';

  @override
  String get deleteRecordingConfirmation =>
      'Jeste li sigurni da želite trajno obrisati ovu snimku? To se ne može poništiti.';

  @override
  String get recordingIdLabel => 'ID Snimke';

  @override
  String get dateTimeLabel => 'Datum i Vrijeme';

  @override
  String get durationLabel => 'Trajanje';

  @override
  String get audioFormatLabel => 'Format Zvuka';

  @override
  String get storageLocationLabel => 'Lokacija Pohrane';

  @override
  String get estimatedSizeLabel => 'Procijenjena Veličina';

  @override
  String get deviceModelLabel => 'Model Uređaja';

  @override
  String get deviceIdLabel => 'ID Uređaja';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Obrađeno';

  @override
  String get statusUnprocessed => 'Neobrađeno';

  @override
  String get switchedToFastTransfer => 'Prebačeno na Brz Prijenos';

  @override
  String get transferCompleteMessage => 'Prijenos je završen! Sada možete reproducirati ovu snimku.';

  @override
  String transferFailedMessage(String error) {
    return 'Prijenos nije uspio: $error';
  }

  @override
  String get transferCancelled => 'Prijenos je otkazan';

  @override
  String get fastTransferEnabled => 'Brz Prijenos je Omogućen';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth Sinhronizacija Omogućena';

  @override
  String get enableFastTransfer => 'Omogući Brz Prijenos';

  @override
  String get fastTransferDescription =>
      'Brz Prijenos koristi WiFi za oko 5x brže brzine. Vaš telefon će se privremeno povezati na WiFi mrežu vašeg Omi uređaja tijekom prijenosa.';

  @override
  String get internetAccessPausedDuringTransfer => 'Pristup internetu je pauziran tijekom prijenosa';

  @override
  String get chooseTransferMethodDescription => 'Odaberite kako se snimke prenose s vašeg Omi uređaja na vaš telefon.';

  @override
  String get wifiSpeed => '~150 KB/s putem WiFi-ja';

  @override
  String get fiveTimesFaster => '5X BRŽE';

  @override
  String get fastTransferMethodDescription =>
      'Kreira izravnu WiFi vezu s vašim Omi uređajem. Vaš telefon će se privremeno odspojiti od vaše standardne WiFi mreže tijekom prijenosa.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s putem BLE';

  @override
  String get bluetoothMethodDescription =>
      'Koristi standardnu vezu Bluetooth Low Energy. Sporije, ali ne utječe na vašu WiFi vezu.';

  @override
  String get selected => 'Odabrano';

  @override
  String get selectOption => 'Odaberi';

  @override
  String get lowBatteryAlertTitle => 'Upozorenje o Niskoj Bateriji';

  @override
  String get lowBatteryAlertBody => 'Vaš uređaj ima nisku bateriju. Vrijeme je za puniranje! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Vaš Omi Uređaj Je Odspoj';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Molim vas da se ponovno povežete da biste nastavili koristiti vaš Omi.';

  @override
  String get firmwareUpdateAvailable => 'Dostupna Je Ažuriranja Firmwarea';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Novo ažuriranje firmwarea ($version) je dostupno za vaš Omi uređaj. Želite li ažurirati sada?';
  }

  @override
  String get later => 'Kasnije';

  @override
  String get appDeletedSuccessfully => 'Aplikacija je uspješno obrisana';

  @override
  String get appDeleteFailed => 'Brisanje aplikacije nije uspjelo. Molim vas pokušajte kasnije.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Vidljivost aplikacije je uspješno promijenjena. Mogu biti potrebne nekoliko minuta da se reflektira.';

  @override
  String get errorActivatingAppIntegration =>
      'Greška pri aktiviranju aplikacije. Ako je to integracyjska aplikacija, provjerite je li postav dovršen.';

  @override
  String get errorUpdatingAppStatus => 'Došlo je do greške pri ažuriranju statusa aplikacije.';

  @override
  String get calculatingETA => 'Izračunavanje...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Otprilike $minutes minuta preostalo';
  }

  @override
  String get aboutAMinuteRemaining => 'Otprilike minutu preostalo';

  @override
  String get almostDone => 'Gotovo je...';

  @override
  String get omiSays => 'omi kaže';

  @override
  String get analyzingYourData => 'Analiziranje tvojih podataka...';

  @override
  String migratingToProtection(String level) {
    return 'Migracija na $level zaštitu...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Nema podataka za migraciju. Završavanje...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migracija $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Svi objekti su migrirani. Završavanje...';

  @override
  String get migrationErrorOccurred => 'Došlo je do greške tijekom migracije. Molim vas pokušajte ponovno.';

  @override
  String get migrationComplete => 'Migracija je završena!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Tvoji podaci su sada zaštićeni novim $level postavama.';
  }

  @override
  String get chatsLowercase => 'razgovori';

  @override
  String get dataLowercase => 'podaci';

  @override
  String get fallNotificationTitle => 'Autš';

  @override
  String get fallNotificationBody => 'Jeste li pali?';

  @override
  String get importantConversationTitle => 'Važan Razgovor';

  @override
  String get importantConversationBody =>
      'Upravo ste imali važan razgovor. Dodirnite da biste podijelili sažetak s drugima.';

  @override
  String get templateName => 'Naziv Predloška';

  @override
  String get templateNameHint => 'npr. Ekstraktor Stavki Akcije Sastanka';

  @override
  String get nameMustBeAtLeast3Characters => 'Naziv mora biti najmanje 3 znaka';

  @override
  String get conversationPromptHint =>
      'npr. Ekstrahirajte stavke akcije, donesene odluke i ključne zaključke iz priloženog razgovora.';

  @override
  String get pleaseEnterAppPrompt => 'Molim vas unesite promptu za vašu aplikaciju';

  @override
  String get promptMustBeAtLeast10Characters => 'Promptu mora biti najmanje 10 znakova';

  @override
  String get anyoneCanDiscoverTemplate => 'Bilo tko može otkriti vaš predložak';

  @override
  String get onlyYouCanUseTemplate => 'Samo vi možete koristiti ovaj predložak';

  @override
  String get generatingDescription => 'Generiranje opisa...';

  @override
  String get creatingAppIcon => 'Stvaranje ikone aplikacije...';

  @override
  String get installingApp => 'Instalacija aplikacije...';

  @override
  String get appCreatedAndInstalled => 'Aplikacija je stvorena i instalirana!';

  @override
  String get appCreatedSuccessfully => 'Aplikacija je uspješno stvorena!';

  @override
  String get failedToCreateApp => 'Stvaranje aplikacije nije uspjelo. Molim vas pokušajte ponovno.';

  @override
  String get addAppSelectCoreCapability =>
      'Molim vas odaberite još jednu osnovnu mogućnost za vašu aplikaciju da biste nastavili';

  @override
  String get addAppSelectPaymentPlan => 'Molim vas odaberite plan plaćanja i unesite cijenu za vašu aplikaciju';

  @override
  String get addAppSelectCapability => 'Molim vas odaberite najmanje jednu mogućnost za vašu aplikaciju';

  @override
  String get addAppSelectLogo => 'Molim vas odaberite logo za vašu aplikaciju';

  @override
  String get addAppEnterChatPrompt => 'Molim vas unesite chat prompt za vašu aplikaciju';

  @override
  String get addAppEnterConversationPrompt => 'Molim vas unesite conversation prompt za vašu aplikaciju';

  @override
  String get addAppSelectTriggerEvent => 'Molim vas odaberite trigger event za vašu aplikaciju';

  @override
  String get addAppEnterWebhookUrl => 'Molim vas unesite webhook URL za vašu aplikaciju';

  @override
  String get addAppSelectCategory => 'Molim vas odaberite kategoriju za vašu aplikaciju';

  @override
  String get addAppFillRequiredFields => 'Molim vas ispunite sve obavezna polja ispravno';

  @override
  String get addAppUpdatedSuccess => 'Aplikacija je uspješno ažurirana 🚀';

  @override
  String get addAppUpdateFailed => 'Ažuriranje aplikacije nije uspjelo. Molim vas pokušajte kasnije';

  @override
  String get addAppSubmittedSuccess => 'Aplikacija je uspješno poslana 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Greška pri otvaranju biraču datoteka: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Greška pri odabiru slike: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Dozvola za fotografije odbijena. Molim vas dopustite pristup fotografijama za odabir slike';

  @override
  String get addAppErrorSelectingImageRetry => 'Greška pri odabiru slike. Molim vas pokušajte ponovno.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Greška pri odabiru minijature: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Greška pri odabiru minijature. Molim vas pokušajte ponovno.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Ostale mogućnosti se ne mogu odabrati sa Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona se ne može odabrati sa ostalim mogućnostima';

  @override
  String get paymentFailedToFetchCountries => 'Dohvaćanje podržanih zemalja nije uspjelo. Molim vas pokušajte kasnije.';

  @override
  String get paymentFailedToSetDefault =>
      'Postavljanje zadane metode plaćanja nije uspjelo. Molim vas pokušajte kasnije.';

  @override
  String get paymentFailedToSavePaypal => 'Spremanje PayPal podataka nije uspjelo. Molim vas pokušajte kasnije.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktivno';

  @override
  String get paymentStatusConnected => 'Povezano';

  @override
  String get paymentStatusNotConnected => 'Nije Povezano';

  @override
  String get paymentAppCost => 'Cijena Aplikacije';

  @override
  String get paymentEnterValidAmount => 'Molim vas unesite valjanu količinu';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Molim vas unesite količinu veću od 0';

  @override
  String get paymentPlan => 'Plan Plaćanja';

  @override
  String get paymentNoneSelected => 'Ništa Nije Odabrano';

  @override
  String get aiGenPleaseEnterDescription => 'Molim vas unesite opis za vašu aplikaciju';

  @override
  String get aiGenCreatingAppIcon => 'Stvaranje ikone aplikacije...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Došlo je do greške: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplikacija je uspješno stvorena!';

  @override
  String get aiGenFailedToCreateApp => 'Stvaranje aplikacije nije uspjelo';

  @override
  String get aiGenErrorWhileCreatingApp => 'Došlo je do greške pri stvaranju aplikacije';

  @override
  String get aiGenFailedToGenerateApp => 'Generiranje aplikacije nije uspjelo. Molim vas pokušajte ponovno.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Regeneriranje ikone nije uspjelo';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Molim vas prvo generirajte aplikaciju';

  @override
  String get nextButton => 'Dalje';

  @override
  String get connectOmiDevice => 'Povežite Omi Uređaj';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Prebacujete svoj Unlimited Plan na $title. Jeste li sigurni da želite nastaviti?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Ažuriranje je zakazano! Vaš mjesečni plan se nastavlja do kraja vašeg razdoblja naplate, zatim se automatski prebacuje na godišnji.';

  @override
  String get couldNotSchedulePlanChange => 'Zakazivanje promjene plana nije uspjelo. Molim vas pokušajte ponovno.';

  @override
  String get subscriptionReactivatedDefault =>
      'Vaša pretplata je reaktivirana! Nema naplate sada - bit ćete naplaćeni na kraju vašeg trenutnog razdoblja.';

  @override
  String get subscriptionSuccessfulCharged => 'Pretplata je uspješna! Naplaćeni ste za novo razdoblje naplate.';

  @override
  String get couldNotProcessSubscription => 'Obrada pretplate nije uspjela. Molim vas pokušajte ponovno.';

  @override
  String get couldNotLaunchUpgradePage => 'Pokretanje stranice ažuriranja nije uspjelo. Molim vas pokušajte ponovno.';

  @override
  String get transcriptionJsonPlaceholder => 'Zalijepite vašu JSON konfiguraciju ovdje...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Greška pri otvaranju biraču datoteka: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Greška: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Razgovori su Uspješno Spojeni';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count razgovora je uspješno spojeno';
  }

  @override
  String get actionItemReminderTitle => 'Omi Podsjetnik';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName Odspoj';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Molim vas ponovno se povežite da biste nastavili koristiti vaš $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Prijava';

  @override
  String get onboardingYourName => 'Vaše Ime';

  @override
  String get onboardingLanguage => 'Jezik';

  @override
  String get onboardingPermissions => 'Dozvole';

  @override
  String get onboardingComplete => 'Dovršeno';

  @override
  String get onboardingWelcomeToOmi => 'Dobrodošli na Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Recite nam nešto o sebi';

  @override
  String get onboardingChooseYourPreference => 'Odaberite vašu preferencu';

  @override
  String get onboardingGrantRequiredAccess => 'Dodijelite potreban pristup';

  @override
  String get onboardingYoureAllSet => 'Sve je spremno';

  @override
  String get searchTranscriptOrSummary => 'Pretražite transkripciju ili sažetak...';

  @override
  String get myGoal => 'Moj cilj';

  @override
  String get appNotAvailable => 'Ups! Čini se da aplikacija koju tražite nije dostupna.';

  @override
  String get failedToConnectTodoist => 'Povezivanje na Todoist nije uspjelo';

  @override
  String get failedToConnectAsana => 'Povezivanje na Asana nije uspjelo';

  @override
  String get failedToConnectGoogleTasks => 'Povezivanje na Google Tasks nije uspjelo';

  @override
  String get failedToConnectClickUp => 'Povezivanje na ClickUp nije uspjelo';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Povezivanje na $serviceName nije uspjelo: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Uspješno ste se povezali na Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Povezivanje na Todoist nije uspjelo. Molim vas pokušajte ponovno.';

  @override
  String get successfullyConnectedAsana => 'Uspješno ste se povezali na Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Povezivanje na Asana nije uspjelo. Molim vas pokušajte ponovno.';

  @override
  String get successfullyConnectedGoogleTasks => 'Uspješno ste se povezali na Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry =>
      'Povezivanje na Google Tasks nije uspjelo. Molim vas pokušajte ponovno.';

  @override
  String get successfullyConnectedClickUp => 'Uspješno ste se povezali na ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Povezivanje na ClickUp nije uspjelo. Molim vas pokušajte ponovno.';

  @override
  String get successfullyConnectedNotion => 'Uspješno ste se povezali na Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Osvježavanje statusa Notion veze nije uspjelo.';

  @override
  String get successfullyConnectedGoogle => 'Uspješno ste se povezali na Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Osvježavanje statusa Google veze nije uspjelo.';

  @override
  String get successfullyConnectedWhoop => 'Uspješno ste se povezali na Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Osvježavanje statusa Whoop veze nije uspjelo.';

  @override
  String get successfullyConnectedGitHub => 'Uspješno ste se povezali na GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Osvježavanje statusa GitHub veze nije uspjelo.';

  @override
  String get authFailedToSignInWithGoogle => 'Prijava s Google-om nije uspjela, molim vas pokušajte ponovno.';

  @override
  String get authenticationFailed => 'Autentifikacija nije uspjela. Molim vas pokušajte ponovno.';

  @override
  String get authFailedToSignInWithApple => 'Prijava s Apple-om nije uspjela, molim vas pokušajte ponovno.';

  @override
  String get authFailedToRetrieveToken => 'Dohvaćanje firebase tokena nije uspjelo, molim vas pokušajte ponovno.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Neočekivana greška pri prijavi, Firebase greška, molim vas pokušajte ponovno.';

  @override
  String get authUnexpectedError => 'Neočekivana greška pri prijavi, molim vas pokušajte ponovno';

  @override
  String get authFailedToLinkGoogle => 'Povezivanje s Google-om nije uspjelo, molim vas pokušajte ponovno.';

  @override
  String get authFailedToLinkApple => 'Povezivanje s Apple-om nije uspjelo, molim vas pokušajte ponovno.';

  @override
  String get onboardingBluetoothRequired => 'Dozvola za Bluetooth je obavezna za povezivanje s vašim uređajem.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Dozvola za Bluetooth je odbijena. Molim vas dodijelite dozvolu u Sistemskim Postavama.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Status dozvole za Bluetooth: $status. Molim vas provjerite Sistemske Postavke.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Provjera dozvole za Bluetooth nije uspjela: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Dozvola za Notifikacije je odbijena. Molim vas dodijelite dozvolu u Sistemskim Postavama.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Dozvola za Notifikacije je odbijena. Molim vas dodijelite dozvolu u Sistemskim Postavama > Notifikacije.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Status dozvole za Notifikacije: $status. Molim vas provjerite Sistemske Postavke.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Provjera dozvole za Notifikacije nije uspjela: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Molim vas dodijelite dozvolu za lokaciju u Postavke > Privatnost i Sigurnost > Usluge Lokacije';

  @override
  String get onboardingMicrophoneRequired => 'Dozvola za Mikrofon je obavezna za snimanje.';

  @override
  String get onboardingMicrophoneDenied =>
      'Dozvola za Mikrofon je odbijena. Molim vas dodijelite dozvolu u Sistemskim Postavama > Privatnost i Sigurnost > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Status dozvole za Mikrofon: $status. Molim vas provjerite Sistemske Postavke.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Provjera dozvole za Mikrofon nije uspjela: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Dozvola za Snimanje Zaslona je obavezna za snimanje sustavnog zvuka.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Dozvola za Snimanje Zaslona je odbijena. Molim vas dodijelite dozvolu u Sistemskim Postavama > Privatnost i Sigurnost > Snimanje Zaslona.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Status dozvole za Snimanje Zaslona: $status. Molim vas provjerite Sistemske Postavke.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Provjera dozvole za Snimanje Zaslona nije uspjela: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Dozvola za Pristupačnost je obavezna za detektiranje susreta u pregledniku.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Status dozvole za Pristupačnost: $status. Molim vas provjerite Sistemske Postavke.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Provjera dozvole za Pristupačnost nije uspjela: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Snimanje kamerom nije dostupno na ovoj platformi';

  @override
  String get msgCameraPermissionDenied => 'Dozvola za Kameru je odbijena. Molim vas dopustite pristup kameri';

  @override
  String msgCameraAccessError(String error) {
    return 'Greška pri pristupu kameri: $error';
  }

  @override
  String get msgPhotoError => 'Greška pri snimanju fotografije. Molim vas pokušajte ponovno.';

  @override
  String get msgMaxImagesLimit => 'Možete odabrati samo do 4 slike';

  @override
  String msgFilePickerError(String error) {
    return 'Greška pri otvaranju biraču datoteka: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Greška pri odabiru slika: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Dozvola za Fotografije je odbijena. Molim vas dopustite pristup fotografijama za odabir slika';

  @override
  String get msgSelectImagesGenericError => 'Greška pri odabiru slika. Molim vas pokušajte ponovno.';

  @override
  String get msgMaxFilesLimit => 'Možete odabrati samo do 4 datoteke';

  @override
  String msgSelectFilesError(String error) {
    return 'Greška pri odabiru datoteka: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Greška pri odabiru datoteka. Molim vas pokušajte ponovno.';

  @override
  String get msgUploadFileFailed => 'Učitavanje datoteke nije uspjelo, molim vas pokušajte kasnije';

  @override
  String get msgReadingMemories => 'Čitanje tvojih uspomena...';

  @override
  String get msgLearningMemories => 'Učenje iz tvojih uspomena...';

  @override
  String get msgUploadAttachedFileFailed => 'Učitavanje priložene datoteke nije uspjelo.';

  @override
  String captureRecordingError(String error) {
    return 'Greška tijekom snimanja: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Snimanje je zaustavljeno: $reason. Možda trebate ponovno povezati vanjske zaslone ili ponovno pokrenuti snimanje.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Dozvola za Mikrofon je obavezna';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Dodijelite dozvolu za Mikrofon u Sistemskim Postavama';

  @override
  String get captureScreenRecordingPermissionRequired => 'Dozvola za Snimanje Zaslona je obavezna';

  @override
  String get captureDisplayDetectionFailed => 'Detektiranje zaslona nije uspjelo. Snimanje je zaustavljeno.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Nevaljani audio bytes webhook URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Nevaljani realtime transcript webhook URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Nevaljani conversation created webhook URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Nevaljani day summary webhook URL';

  @override
  String get devModeSettingsSaved => 'Postavke su spremljene!';

  @override
  String get voiceFailedToTranscribe => 'Transkripcija zvuka nije uspjela';

  @override
  String get locationPermissionRequired => 'Dozvola za Lokaciju je Obavezna';

  @override
  String get locationPermissionContent =>
      'Brz Prijenos zahtijeva dozvolu za lokaciju da provjerite WiFi vezu. Molim vas dodijelite dozvolu za lokaciju da biste nastavili.';

  @override
  String get pdfTranscriptExport => 'Izvoz Transkripcije';

  @override
  String get pdfConversationExport => 'Izvoz Razgovora';

  @override
  String pdfTitleLabel(String title) {
    return 'Naslov: $title';
  }

  @override
  String get conversationNewIndicator => 'Novo 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count slika';
  }

  @override
  String get mergingStatus => 'Spajanje...';

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
    return '$count sat';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count sati';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours sati $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count dan';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count dana';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dana $hours sati';
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
    return '${count}h';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}h ${mins}m';
  }

  @override
  String get moveToFolder => 'Premjesti u Mapu';

  @override
  String get noFoldersAvailable => 'Nema dostupnih mapa';

  @override
  String get newFolder => 'Nova Mapa';

  @override
  String get color => 'Boja';

  @override
  String get waitingForDevice => 'Čekanje na uređaj...';

  @override
  String get saySomething => 'Recite nešto...';

  @override
  String get initialisingSystemAudio => 'Inicijaliziranje Sustavnog Zvuka';

  @override
  String get stopRecording => 'Zaustavi Snimanje';

  @override
  String get continueRecording => 'Nastavi Snimanje';

  @override
  String get initialisingRecorder => 'Inicijaliziranje Snimača';

  @override
  String get pauseRecording => 'Pauziraj Snimanje';

  @override
  String get resumeRecording => 'Nastavi Snimanje';

  @override
  String get noDailyRecapsYet => 'Nema dnevnih sažetaka';

  @override
  String get dailyRecapsDescription => 'Tvoji dnevni sažetci će se pojaviti ovdje nakon što budu generirani';

  @override
  String get chooseTransferMethod => 'Odaberite Metodu Prijenosa';

  @override
  String get fastTransferSpeed => '~150 KB/s putem WiFi-ja';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Otkrivena velika vremenski razmak ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Otkriveni veliki vremenski razmaci ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Uređaj ne podržava WiFi sinhronizaciju, prebacivanje na Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health nije dostupan na ovom uređaju';

  @override
  String get downloadAudio => 'Preuzmi Zvuk';

  @override
  String get audioDownloadSuccess => 'Zvuk je uspješno preuzet';

  @override
  String get audioDownloadFailed => 'Preuzimanje zvuka nije uspjelo';

  @override
  String get downloadingAudio => 'Preuzimanje zvuka...';

  @override
  String get shareAudio => 'Dijeli Zvuk';

  @override
  String get preparingAudio => 'Priprema Zvuka';

  @override
  String get gettingAudioFiles => 'Dohvaćanje audio datoteka...';

  @override
  String get downloadingAudioProgress => 'Preuzimanje Zvuka';

  @override
  String get processingAudio => 'Obrada Zvuka';

  @override
  String get combiningAudioFiles => 'Kombiniranje audio datoteka...';

  @override
  String get audioReady => 'Zvuk je Spreman';

  @override
  String get openingShareSheet => 'Otvaranje lista za dijeljenje...';

  @override
  String get audioShareFailed => 'Dijeljenje nije uspjelo';

  @override
  String get dailyRecaps => 'Dnevni Sažetci';

  @override
  String get removeFilter => 'Ukloni Filter';

  @override
  String get categoryConversationAnalysis => 'Analiza Razgovora';

  @override
  String get categoryHealth => 'Zdravlje';

  @override
  String get categoryEducation => 'Obrazovanje';

  @override
  String get categoryCommunication => 'Komunikacija';

  @override
  String get categoryEmotionalSupport => 'Emocionalna Podrška';

  @override
  String get categoryProductivity => 'Produktivnost';

  @override
  String get categoryEntertainment => 'Zabava';

  @override
  String get categoryFinancial => 'Financijski';

  @override
  String get categoryTravel => 'Putovanja';

  @override
  String get categorySafety => 'Sigurnost';

  @override
  String get categoryShopping => 'Kupovine';

  @override
  String get categorySocial => 'Društveno';

  @override
  String get categoryNews => 'Vijesti';

  @override
  String get categoryUtilities => 'Uslužni Programi';

  @override
  String get categoryOther => 'Ostalo';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Razgovori';

  @override
  String get capabilityExternalIntegration => 'Vanjska Integracija';

  @override
  String get capabilityNotification => 'Notifikacija';

  @override
  String get triggerAudioBytes => 'Audio Bytes';

  @override
  String get triggerConversationCreation => 'Stvaranje Razgovora';

  @override
  String get triggerTranscriptProcessed => 'Transkripcija Obrađena';

  @override
  String get actionCreateConversations => 'Kreiraj razgovore';

  @override
  String get actionCreateMemories => 'Kreiraj uspomene';

  @override
  String get actionReadConversations => 'Čitaj razgovore';

  @override
  String get actionReadMemories => 'Čitaj uspomene';

  @override
  String get actionReadTasks => 'Čitaj zadatke';

  @override
  String get scopeUserName => 'Korisničko Ime';

  @override
  String get scopeUserFacts => 'Korisničke Činjenice';

  @override
  String get scopeUserConversations => 'Korisničke Razgovore';

  @override
  String get scopeUserChat => 'Korisnički Chat';

  @override
  String get capabilitySummary => 'Sažetak';

  @override
  String get capabilityFeatured => 'Istaknuto';

  @override
  String get capabilityTasks => 'Zadaci';

  @override
  String get capabilityIntegrations => 'Integracije';

  @override
  String get categoryProductivityLifestyle => 'Produktivnost i Stil Života';

  @override
  String get categorySocialEntertainment => 'Društveno i Zabava';

  @override
  String get categoryProductivityTools => 'Produktivnost i Alati';

  @override
  String get categoryPersonalWellness => 'Osobni život i lifestyle';

  @override
  String get rating => 'Ocjena';

  @override
  String get categories => 'Kategorije';

  @override
  String get sortBy => 'Sortiranje';

  @override
  String get highestRating => 'Najviša ocjena';

  @override
  String get lowestRating => 'Najniža ocjena';

  @override
  String get resetFilters => 'Resetiraj filtere';

  @override
  String get applyFilters => 'Primijeni filtere';

  @override
  String get mostInstalls => 'Većina instalacija';

  @override
  String get couldNotOpenUrl => 'Nije moguće otvoriti URL. Pokušajte ponovno.';

  @override
  String get newTask => 'Novi zadatak';

  @override
  String get viewAll => 'Prikaži sve';

  @override
  String get addTask => 'Dodaj zadatak';

  @override
  String get addMcpServer => 'Dodaj MCP server';

  @override
  String get connectExternalAiTools => 'Povežite vanjske AI alate';

  @override
  String get mcpServerUrl => 'MCP server URL';

  @override
  String mcpServerConnected(int count) {
    return '$count alata uspješno povezano';
  }

  @override
  String get mcpConnectionFailed => 'Nije uspjelo povezivanje s MCP serverom';

  @override
  String get authorizingMcpServer => 'Autorizacija...';

  @override
  String get whereDidYouHearAboutOmi => 'Kako ste čuli za nas?';

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
  String get friendWordOfMouth => 'Prijatelj';

  @override
  String get otherSource => 'Ostalo';

  @override
  String get pleaseSpecify => 'Molimo specificirajte';

  @override
  String get event => 'Događaj';

  @override
  String get coworker => 'Kolega';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google pretraga';

  @override
  String get audioPlaybackUnavailable => 'Audio datoteka nije dostupna za reprodukciju';

  @override
  String get audioPlaybackFailed => 'Nije moguće reproducirati audio. Datoteka može biti oštećena ili nedostaje.';

  @override
  String get connectionGuide => 'Vodič za povezivanje';

  @override
  String get iveDoneThis => 'Već sam to učinio/a';

  @override
  String get pairNewDevice => 'Upari novi uređaj';

  @override
  String get dontSeeYourDevice => 'Vidite li svoj uređaj?';

  @override
  String get reportAnIssue => 'Prijavite problem';

  @override
  String get pairingTitleOmi => 'Uključite Omi';

  @override
  String get pairingDescOmi => 'Dugo pritisnite uređaj dok ne vibrira da ga uključite.';

  @override
  String get pairingTitleOmiDevkit => 'Stavite Omi DevKit u modus uparivanja';

  @override
  String get pairingDescOmiDevkit =>
      'Pritisnite gumb jednom da uključite. LED će bljeskati ljubičasto kada je u modu uparivanja.';

  @override
  String get pairingTitleOmiGlass => 'Uključite Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Uključite pritiskanjem bočne tipke 3 sekunde.';

  @override
  String get pairingTitlePlaudNote => 'Stavite Plaud Note u modus uparivanja';

  @override
  String get pairingDescPlaudNote =>
      'Dugo pritisnite bočnu tipku 2 sekunde. Crveni LED će bljeskati kada je spreman za uparavanje.';

  @override
  String get pairingTitleBee => 'Stavite Bee u modus uparivanja';

  @override
  String get pairingDescBee => 'Pritisnite gumb 5 puta uzastopno. Svjetlo će početi bljeskati plavo i zeleno.';

  @override
  String get pairingTitleLimitless => 'Stavite Limitless u modus uparivanja';

  @override
  String get pairingDescLimitless =>
      'Kada je bilo koje svjetlo vidljivo, pritisnite jednom, zatim pritisnite i držite dok uređaj ne pokaže ružičasto svjetlo, zatim otpustite.';

  @override
  String get pairingTitleFriendPendant => 'Stavite Friend Pendant u modus uparivanja';

  @override
  String get pairingDescFriendPendant =>
      'Pritisnite gumb na privjesku da ga uključite. Automatski će ući u modus uparivanja.';

  @override
  String get pairingTitleFieldy => 'Stavite Fieldy u modus uparivanja';

  @override
  String get pairingDescFieldy => 'Dugo pritisnite uređaj dok se ne pojavi svjetlo da ga uključite.';

  @override
  String get pairingTitleAppleWatch => 'Povežite Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Instalirajte i otvorite Omi aplikaciju na vašem Apple Watchu, zatim dodirnite Poveži u aplikaciji.';

  @override
  String get pairingTitleNeoOne => 'Stavite Neo One u modus uparivanja';

  @override
  String get pairingDescNeoOne =>
      'Pritisnite i držite gumb za napajanje dok LED ne počne bljeskati. Uređaj će biti vidljiv.';

  @override
  String get downloadingFromDevice => 'Preuzimanje s uređaja';

  @override
  String get reconnectingToInternet => 'Ponovno povezivanje na internet...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Učitavanje $current od $total';
  }

  @override
  String get processingOnServer => 'Obrada na serveru...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Obrada... $current/$total segmenata';
  }

  @override
  String get processedStatus => 'Obrađeno';

  @override
  String get corruptedStatus => 'Oštećeno';

  @override
  String nPending(int count) {
    return '$count na čekanju';
  }

  @override
  String nProcessed(int count) {
    return '$count obrađeno';
  }

  @override
  String get synced => 'Sinhronizovano';

  @override
  String get noPendingRecordings => 'Nema snimki na čekanju';

  @override
  String get noProcessedRecordings => 'Nema obrađenih snimki';

  @override
  String get pending => 'Na čekanju';

  @override
  String whatsNewInVersion(String version) {
    return 'Što je novo u verziji $version';
  }

  @override
  String get addToYourTaskList => 'Dodati na listu zadataka?';

  @override
  String get failedToCreateShareLink => 'Nije uspjelo stvaranje veze za dijeljenje';

  @override
  String get deleteGoal => 'Obriši cilj';

  @override
  String get deviceUpToDate => 'Vaš uređaj je ažuran';

  @override
  String get wifiConfiguration => 'Konfiguracija WiFi-ja';

  @override
  String get wifiConfigurationSubtitle => 'Unesite vaše WiFi kredencijale kako bi uređaj mogao preuzeti firmware.';

  @override
  String get networkNameSsid => 'Naziv mreže (SSID)';

  @override
  String get enterWifiNetworkName => 'Unesite naziv WiFi mreže';

  @override
  String get enterWifiPassword => 'Unesite WiFi lozinku';

  @override
  String get appIconLabel => 'Ikona aplikacije';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Evo što znam o vama';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Ova mapa se ažurira dok Omi uči iz vaših razgovora.';

  @override
  String get apiEnvironment => 'API okruženje';

  @override
  String get apiEnvironmentDescription => 'Odaberite kojem backend-u se želite povezati';

  @override
  String get production => 'Produkcija';

  @override
  String get staging => 'Staging';

  @override
  String get switchRequiresRestart => 'Prebacivanje zahtijeva ponovno pokretanje aplikacije';

  @override
  String get switchApiConfirmTitle => 'Prebacite API okruženje';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Prebaciti na $environment? Trebat će zatvoriti i ponovno otvoriti aplikaciju kako bi promjene stupiле na snagu.';
  }

  @override
  String get switchAndRestart => 'Prebaci';

  @override
  String get stagingDisclaimer =>
      'Staging može biti nestabilan, imati nekonzistentne performanse, a podaci mogu biti izgubljeni. Koristite samo za testiranje.';

  @override
  String get apiEnvSavedRestartRequired => 'Spremljeno. Zatvorite i ponovno otvorite aplikaciju da biste primijenili.';

  @override
  String get shared => 'Dijeljeno';

  @override
  String get onlyYouCanSeeConversation => 'Samo vi možete vidjeti ovaj razgovor';

  @override
  String get anyoneWithLinkCanView => 'Bilo tko s vezom može vidjeti';

  @override
  String get tasksCleanTodayTitle => 'Očistiti današnje zadatke?';

  @override
  String get tasksCleanTodayMessage => 'Ovo će ukloniti samo rokove';

  @override
  String get tasksOverdue => 'Isteklo';

  @override
  String get phoneCallsWithOmi => 'Telefonski razgovori s Omi';

  @override
  String get phoneCallsSubtitle => 'Pravite pozive s prijenosom u stvarnom vremenu';

  @override
  String get phoneSetupStep1Title => 'Provjerite svoj telefonski broj';

  @override
  String get phoneSetupStep1Subtitle => 'Pozivat ćemo vas da potvrdimo da je vaš';

  @override
  String get phoneSetupStep2Title => 'Unesite kod za provjeru';

  @override
  String get phoneSetupStep2Subtitle => 'Kratki kod koji ćete unijeti tijekom poziva';

  @override
  String get phoneSetupStep3Title => 'Započnite pozivati svoje kontakte';

  @override
  String get phoneSetupStep3Subtitle => 'S ugrađenim prijenosom u stvarnom vremenu';

  @override
  String get phoneGetStarted => 'Početak';

  @override
  String get callRecordingConsentDisclaimer => 'Snimanje poziva može zahtijevati pristanak u vašoj nadležnosti';

  @override
  String get enterYourNumber => 'Unesite svoj broj';

  @override
  String get phoneNumberCallerIdHint => 'Kada se provjeri, ovo postaje vaš ID pozivatelja';

  @override
  String get phoneNumberHint => 'Telefonski broj';

  @override
  String get failedToStartVerification => 'Nije uspjelo započeti provjeru';

  @override
  String get phoneContinue => 'Nastavi';

  @override
  String get verifyYourNumber => 'Provjerite svoj broj';

  @override
  String get answerTheCallFrom => 'Odgovorite na poziv od';

  @override
  String get onTheCallEnterThisCode => 'Tijekom poziva, unesite ovaj kod';

  @override
  String get followTheVoiceInstructions => 'Slijedite glasovne upute';

  @override
  String get statusCalling => 'Pozivanje...';

  @override
  String get statusCallInProgress => 'Poziv je u tijeku';

  @override
  String get statusVerifiedLabel => 'Potvrđeno';

  @override
  String get statusCallMissed => 'Poziv propušten';

  @override
  String get statusTimedOut => 'Isteklo vrijeme';

  @override
  String get phoneTryAgain => 'Pokušajte ponovno';

  @override
  String get phonePageTitle => 'Telefon';

  @override
  String get phoneContactsTab => 'Kontakti';

  @override
  String get phoneKeypadTab => 'Brojčana tipka';

  @override
  String get grantContactsAccess => 'Dodijelite pristup vašim kontaktima';

  @override
  String get phoneAllow => 'Dozvoli';

  @override
  String get phoneSearchHint => 'Pretraga';

  @override
  String get phoneNoContactsFound => 'Nema pronađenih kontakata';

  @override
  String get phoneEnterNumber => 'Unesite broj';

  @override
  String get failedToStartCall => 'Nije uspjelo započeti poziv';

  @override
  String get callStateConnecting => 'Povezivanje...';

  @override
  String get callStateRinging => 'Zvonenje...';

  @override
  String get callStateEnded => 'Poziv je završen';

  @override
  String get callStateFailed => 'Poziv nije uspio';

  @override
  String get transcriptPlaceholder => 'Transkripcija će se pojaviti ovdje...';

  @override
  String get phoneUnmute => 'Uključi zvuk';

  @override
  String get phoneMute => 'Isključi zvuk';

  @override
  String get phoneSpeaker => 'Zvučnik';

  @override
  String get phoneEndCall => 'Završi';

  @override
  String get phoneCallSettingsTitle => 'Postavke telefonskih poziva';

  @override
  String get showPhoneCallButtonTitle => 'Prikaži gumb za poziv';

  @override
  String get showPhoneCallButtonDesc => 'Prikaži gumb za telefonski poziv na početnom zaslonu';

  @override
  String get yourVerifiedNumbers => 'Vaši potvrđeni brojevi';

  @override
  String get verifiedNumbersDescription => 'Kada pozovete nekoga, on/ona će vidjeti ovaj broj na svom telefonu';

  @override
  String get noVerifiedNumbers => 'Nema potvrđenih brojeva';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Obrisati $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Trebat će ponovno provjeriti kako biste mogli pozivati';

  @override
  String get phoneDeleteButton => 'Obriši';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Potvrđeno prije ${minutes}m';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Potvrđeno prije ${hours}h';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Potvrđeno prije ${days}d';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Potvrđeno $date';
  }

  @override
  String get verifiedFallback => 'Potvrđeno';

  @override
  String get callAlreadyInProgress => 'Poziv je već u tijeku';

  @override
  String get failedToGetCallToken => 'Nije uspjelo dohvaćanje tokena za poziv. Prvo provjerite svoj telefonski broj.';

  @override
  String get failedToInitializeCallService => 'Nije uspjelo inicijaliziranje servisa poziva';

  @override
  String get speakerLabelYou => 'Vi';

  @override
  String get speakerLabelUnknown => 'Nepoznato';

  @override
  String get showDailyScoreOnHomepage => 'Prikaži dnevnu ocjenu na početnoj stranici';

  @override
  String get showTasksOnHomepage => 'Prikaži zadatke na početnoj stranici';

  @override
  String get phoneCallsUnlimitedOnly => 'Telefonski razgovori putem Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Pravite pozive kroz Omi i dobijte prenos u stvarnom vremenu, automatske sažetke i još mnogo toga. Dostupno isključivo za pretplatnike Unlimited plana.';

  @override
  String get phoneCallsUpsellFeature1 => 'Prenos svakog poziva u stvarnom vremenu';

  @override
  String get phoneCallsUpsellFeature2 => 'Automatski sažetci poziva i stavke za djelovanje';

  @override
  String get phoneCallsUpsellFeature3 => 'Primatelji vide vaš pravi broj, ne nasumičan';

  @override
  String get phoneCallsUpsellFeature4 => 'Vaši pozivi ostaju privatni i sigurni';

  @override
  String get phoneCallsUpgradeButton => 'Nadogradi na Unlimited';

  @override
  String get phoneCallsMaybeLater => 'Možda kasnije';

  @override
  String get deleteSynced => 'Obriši sinhronizovano';

  @override
  String get deleteSyncedFiles => 'Obriši sinhronizovane snimke';

  @override
  String get deleteSyncedFilesMessage =>
      'Ove snimke su već sinhronizovane s vašim telefonom. Ovo se ne može poništiti.';

  @override
  String get syncedFilesDeleted => 'Sinhronizovane snimke obrisane';

  @override
  String get deletePending => 'Obriši na čekanju';

  @override
  String get deletePendingFiles => 'Obriši snimke na čekanju';

  @override
  String get deletePendingFilesWarning =>
      'Ove snimke NISU sinhronizovane s vašim telefonom i bit će trajno izgubljene. Ovo se ne može poništiti.';

  @override
  String get pendingFilesDeleted => 'Snimke na čekanju obrisane';

  @override
  String get deleteAllFiles => 'Obriši sve snimke';

  @override
  String get deleteAll => 'Obriši sve';

  @override
  String get deleteAllFilesWarning =>
      'Ovo će obrisati i sinhronizovane i snimke na čekanju. Snimke na čekanju NISU sinhronizovane i bit će trajno izgubljene. Ovo se ne može poništiti.';

  @override
  String get allFilesDeleted => 'Sve snimke obrisane';

  @override
  String nFiles(int count) {
    return '$count snimki';
  }

  @override
  String get manageStorage => 'Upravljanje pohranom';

  @override
  String get safelyBackedUp => 'Sigurno pohranjeno na vašem telefonu';

  @override
  String get notYetSynced => 'Još nije sinhronizovano s vašim telefonom';

  @override
  String get clearAll => 'Očisti sve';

  @override
  String get phoneKeypad => 'Brojčana tipka';

  @override
  String get phoneHideKeypad => 'Sakrij brojčanu tipku';

  @override
  String get fairUsePolicy => 'Poštena upotreba';

  @override
  String get fairUseLoadError => 'Nije moguće učitati status poštene upotrebe. Pokušajte ponovno.';

  @override
  String get fairUseStatusNormal => 'Vaša upotreba je unutar normalnih granica.';

  @override
  String get fairUseStageNormal => 'Normalno';

  @override
  String get fairUseStageWarning => 'Upozorenje';

  @override
  String get fairUseStageThrottle => 'Ograničeno';

  @override
  String get fairUseStageRestrict => 'Ograničeno';

  @override
  String get fairUseSpeechUsage => 'Upotreba govora';

  @override
  String get fairUseToday => 'Danas';

  @override
  String get fairUse3Day => '3-dnevno klizno';

  @override
  String get fairUseWeekly => 'Tjedno klizno';

  @override
  String get fairUseAboutTitle => 'O poštenoj upotrebi';

  @override
  String get fairUseAboutBody =>
      'Omi je dizajniran za osobne razgovore, sastanke i žive interakcije. Upotreba se mjeri prema stvarnom vremenu detektiranog govora, ne vremenu povezivanja. Ako upotreba značajno premašuje normale obrasce za sadržaj koji nije osoban, može doći do prilagodbi.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef kopiran';
  }

  @override
  String get fairUseDailyTranscription => 'Dnevni prenos';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'Dostignut je dnevni limit prenosa';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resetira se $time';
  }

  @override
  String get transcriptionPaused => 'Snimanje, ponovno povezivanje';

  @override
  String get transcriptionPausedReconnecting => 'Još uvijek snimanje — ponovno povezivanje na prenos...';

  @override
  String fairUseBannerStatus(String status) {
    return 'Poštena upotreba: $status';
  }

  @override
  String get improveConnectionTitle => 'Poboljšajte povezivanje';

  @override
  String get improveConnectionContent =>
      'Poboljšali smo kako Omi ostaje povezan s vašim uređajem. Da biste ovo aktivirali, molimo idite na stranicu Informacije o uređaju, dodirnite \"Odvoji uređaj\", a zatim ponovno upari uređaj.';

  @override
  String get improveConnectionAction => 'Razumijem';

  @override
  String clockSkewWarning(int minutes) {
    return 'Sat na vašem uređaju je pomaknut za ~$minutes min. Provjerite postavke datuma i vremena.';
  }

  @override
  String get omisStorage => 'Pohrana Omi-ja';

  @override
  String get phoneStorage => 'Pohrana telefona';

  @override
  String get cloudStorage => 'Pohrana u oblaku';

  @override
  String get howSyncingWorks => 'Kako sinhronizacija radi';

  @override
  String get noSyncedRecordings => 'Nema sinhronizovanih snimki';

  @override
  String get recordingsSyncAutomatically => 'Snimke se sinhroniziraju automatski — nije potrebna nikakva akcija.';

  @override
  String get filesDownloadedUploadedNextTime => 'Datoteke koje su već preuzete bit će učitane sljedeće vrijeme.';

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
  String get tapToView => 'Dodirnite za pregled';

  @override
  String get syncFailed => 'Sinhronizacija nije uspjela';

  @override
  String get keepSyncing => 'Nastavi sinhronizaciju';

  @override
  String get cancelSyncQuestion => 'Poništiti sinhronizaciju?';

  @override
  String get omisStorageDesc =>
      'Kada vaš Omi nije povezan s vašim telefonom, on pohranjuje audio lokalno na svojoj ugrađenoj memoriji. Nikad ne gubite snimku.';

  @override
  String get phoneStorageDesc =>
      'Kada se Omi ponovno poveže, snimke se automatski prebacuju na vaš telefon kao privremeno skladište prije učitavanja.';

  @override
  String get cloudStorageDesc =>
      'Kada se učitaju, snimke se obrađuju i prenose. Razgovori će biti dostupni u roku minute.';

  @override
  String get tipKeepPhoneNearby => 'Čuvajte telefon blizu za bržu sinhronizaciju';

  @override
  String get tipStableInternet => 'Stabilan internet ubrzava učitavanje u oblak';

  @override
  String get tipAutoSync => 'Snimke se sinhroniziraju automatski';

  @override
  String get storageSection => 'POHRANA';

  @override
  String get permissions => 'Dozvole';

  @override
  String get permissionEnabled => 'Omogućeno';

  @override
  String get permissionEnable => 'Omogući';

  @override
  String get permissionsPageDescription =>
      'Ove dozvole su temeljne za funkcionalnost Omi-ja. One omogućavaju ključne funkcije kao obavijesti, iskustva na temelju lokacije i snimanje audio-a.';

  @override
  String get permissionsRequiredDescription =>
      'Omi trebaju nekoliko dozvola da bi radio pravilno. Molimo dodijelite ih kako biste nastavili.';

  @override
  String get permissionsSetupTitle => 'Uživajte u najboljem iskustvu';

  @override
  String get permissionsSetupDescription => 'Omogućite nekoliko dozvola kako bi Omi mogao raditi svoju magiju.';

  @override
  String get permissionsChangeAnytime => 'Možete te dozvole promijeniti bilo kada u Postavke > Dozvole';

  @override
  String get location => 'Lokacija';

  @override
  String get microphone => 'Mikrofon';

  @override
  String get whyAreYouCanceling => 'Zašto otkazujete?';

  @override
  String get cancelReasonSubtitle => 'Možete li nam reći zašto odlazite?';

  @override
  String get cancelReasonTooExpensive => 'Previše skupo';

  @override
  String get cancelReasonNotUsing => 'Ne koristim ga dovoljno';

  @override
  String get cancelReasonMissingFeatures => 'Nedostaju mogućnosti';

  @override
  String get cancelReasonAudioQuality => 'Kvaliteta audio-a/prenosa';

  @override
  String get cancelReasonBatteryDrain => 'Zabrinutost zbog trošenja baterije';

  @override
  String get cancelReasonFoundAlternative => 'Pronašao/la sam alternativu';

  @override
  String get cancelReasonOther => 'Ostalo';

  @override
  String get tellUsMore => 'Recite nam više (izbjeć)';

  @override
  String get cancelReasonDetailHint => 'Cijenimo bilo koju povratnu informaciju...';

  @override
  String get justAMoment => 'Molimo čekajte';

  @override
  String get cancelConsequencesSubtitle =>
      'Toplo vam preporučujemo da istražite svoje ostale opcije umjesto otkazivanja.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Vaš plan ostaje aktivan do $date. Nakon toga, prebačeni ćete na besplatnu verziju s ograničenim mogućnostima.';
  }

  @override
  String get ifYouCancel => 'Ako otkazujete:';

  @override
  String get cancelConsequenceNoAccess => 'Više neće biti pristupa bez ograničenja na kraju vaše razdoblja naplate.';

  @override
  String get cancelConsequenceBattery => '7x veća upotreba baterije (obrada na uređaju)';

  @override
  String get cancelConsequenceQuality => '30% niža kvaliteta prenosa (modeli na uređaju)';

  @override
  String get cancelConsequenceDelay => 'Kašnjenje obrade od 5-7 sekundi (modeli na uređaju)';

  @override
  String get cancelConsequenceSpeakers => 'Nije moguće identificirati govornike.';

  @override
  String get confirmAndCancel => 'Potvrdi i otkaži';

  @override
  String get cancelConsequencePhoneCalls => 'Nema prenosa telefonskih poziva u stvarnom vremenu';

  @override
  String get feedbackTitleTooExpensive => 'Koja bi cijena bila prihvatljiva?';

  @override
  String get feedbackTitleMissingFeatures => 'Koje mogućnosti vam nedostaju?';

  @override
  String get feedbackTitleAudioQuality => 'Koja problema ste iskusili?';

  @override
  String get feedbackTitleBatteryDrain => 'Recite nam o problemima s baterijom';

  @override
  String get feedbackTitleFoundAlternative => 'Na što prelazite?';

  @override
  String get feedbackTitleNotUsing => 'Što bi vas učinilo da više koristite Omi?';

  @override
  String get feedbackSubtitleTooExpensive => 'Vaša povratna informacija nam pomaže da pronađemo pravi balans.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Uvijek gradimo — ovo nam pomaže da postavimo prioritete.';

  @override
  String get feedbackSubtitleAudioQuality => 'Voljeli bismo razumjeti što je pošlo po zlu.';

  @override
  String get feedbackSubtitleBatteryDrain => 'Ovo pomaže našem hardverskom timu da se poboljša.';

  @override
  String get feedbackSubtitleFoundAlternative => 'Voljeli bismo saznati što vas je zainteresiralo.';

  @override
  String get feedbackSubtitleNotUsing => 'Želimo učiniti Omi korisnijim za vas.';

  @override
  String get deviceDiagnostics => 'Dijagnostika uređaja';

  @override
  String get signalStrength => 'Snaga signala';

  @override
  String get connectionUptime => 'Vrijeme rada';

  @override
  String get reconnections => 'Ponovno povezivanja';

  @override
  String get disconnectHistory => 'Povijest prekida';

  @override
  String get noDisconnectsRecorded => 'Nema zabilježenih prekida';

  @override
  String get diagnostics => 'Dijagnostika';

  @override
  String get waitingForData => 'Čekanje podataka...';

  @override
  String get liveRssiOverTime => 'Live RSSI tijekom vremena';

  @override
  String get noRssiDataYet => 'Nema RSSI podataka';

  @override
  String get collectingData => 'Prikupljanje podataka...';

  @override
  String get cleanDisconnect => 'Čist prekid';

  @override
  String get connectionTimeout => 'Isteklo vrijeme povezivanja';

  @override
  String get remoteDeviceTerminated => 'Udaljeni uređaj prekinuo';

  @override
  String get pairedToAnotherPhone => 'Uparen s drugim telefonom';

  @override
  String get linkKeyMismatch => 'Neusklađenost ključa veze';

  @override
  String get connectionFailed => 'Povezivanje nije uspjelo';

  @override
  String get appClosed => 'Aplikacija zatvorena';

  @override
  String get manualDisconnect => 'Ručni prekid';

  @override
  String lastNEvents(int count) {
    return 'Posljednjih $count događaja';
  }

  @override
  String get signal => 'Signal';

  @override
  String get battery => 'Baterija';

  @override
  String get excellent => 'Odličan';

  @override
  String get good => 'Dobar';

  @override
  String get fair => 'Zadovoljavajući';

  @override
  String get weak => 'Slab';

  @override
  String gattError(String code) {
    return 'GATT greška ($code)';
  }

  @override
  String get batteryHistory => 'Baterija';

  @override
  String get noBatteryDataYet => 'Još nema podataka o bateriji';

  @override
  String get day => 'Dan';

  @override
  String get week => 'Tjedan';

  @override
  String get rollbackToStableFirmware => 'Vrati se na stabilni firmware';

  @override
  String get rollbackConfirmTitle => 'Vratiti se na firmware?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Ovo će zamijeniti vaš trenutni firmware s najnovijom stabilnom verzijom ($version). Vaš uređaj će se ponovno pokrenuti nakon ažuriranja.';
  }

  @override
  String get stableFirmware => 'Stabilni firmware';

  @override
  String get fetchingStableFirmware => 'Dohvaćanje najnovijeg stabilnog firmware-a...';

  @override
  String get noStableFirmwareFound => 'Nije moguće pronaći stabilnu verziju firmware-a za vaš uređaj.';

  @override
  String get installStableFirmware => 'Instaliraj stabilni firmware';

  @override
  String get alreadyOnStableFirmware => 'Već ste na najnovijoj stabilnoj verziji.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration audio pohranjeno lokalno';
  }

  @override
  String get willSyncAutomatically => 'bit će sinhronizovano automatski';

  @override
  String get enableLocationTitle => 'Omogući lokaciju';

  @override
  String get enableLocationDescription => 'Dozvola lokacije je potrebna kako bi se pronašli obliski Bluetooth uređaji.';

  @override
  String get voiceRecordingFound => 'Snimka pronađena';

  @override
  String get transcriptionConnecting => 'Povezivanje prenosa...';

  @override
  String get transcriptionReconnecting => 'Ponovno povezivanje prenosa...';

  @override
  String get transcriptionUnavailable => 'Prenos nije dostupan';

  @override
  String get audioOutput => 'Izlaz audio-a';

  @override
  String get firmwareWarningTitle => 'Važno: Pročitajte prije ažuriranja';

  @override
  String get firmwareFormatWarning =>
      'Ovaj firmware će formatirati SD karticu. Molimo osigurajte da su svi offline podaci sinkronizirani prije nadogradnje.\n\nAko vidite trepćuće crveno svjetlo nakon instaliranja ove verzije, ne brinite. Jednostavno povežite uređaj s aplikacijom i trebao bi postati plav. Crveno svjetlo znači da sat uređaja još nije sinkroniziran.';

  @override
  String get continueAnyway => 'Nastavi';

  @override
  String get tasksClearCompleted => 'Obriši završene';

  @override
  String get tasksSelectAll => 'Odaberi sve';

  @override
  String tasksDeleteSelected(int count) {
    return 'Obriši $count zadatak(e)';
  }

  @override
  String get tasksMarkComplete => 'Označeno kao završeno';

  @override
  String get appleHealthManageNote =>
      'Omi pristupa Apple Health-u putem Appleovog HealthKit okvira. Pristup možete opozvati u bilo kojem trenutku u iOS postavkama.';

  @override
  String get appleHealthConnectCta => 'Poveži s Apple Health';

  @override
  String get appleHealthDisconnectCta => 'Prekini vezu s Apple Health';

  @override
  String get appleHealthConnectedBadge => 'Povezano';

  @override
  String get appleHealthFeatureChatTitle => 'Razgovarajte o svom zdravlju';

  @override
  String get appleHealthFeatureChatDesc => 'Pitajte Omi o svojim koracima, snu, otkucajima srca i treninzima.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Pristup samo za čitanje';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi nikada ne piše u Apple Health niti mijenja vaše podatke.';

  @override
  String get appleHealthFeatureSecureTitle => 'Sigurna sinkronizacija';

  @override
  String get appleHealthFeatureSecureDesc => 'Vaši Apple Health podaci sinkroniziraju se privatno s Omi računom.';

  @override
  String get appleHealthDeniedTitle => 'Pristup Apple Health-u odbijen';

  @override
  String get appleHealthDeniedBody =>
      'Omi nema dozvolu za čitanje vaših Apple Health podataka. Omogućite ga u iOS Postavke → Privatnost i sigurnost → Health → Omi.';

  @override
  String get deleteFlowReasonTitle => 'Zašto odlazite?';

  @override
  String get deleteFlowReasonSubtitle => 'Vaše povratne informacije pomažu nam poboljšati Omi za sve.';

  @override
  String get deleteReasonPrivacy => 'Brige o privatnosti';

  @override
  String get deleteReasonNotUsing => 'Ne koristim dovoljno često';

  @override
  String get deleteReasonMissingFeatures => 'Nedostaju značajke koje trebam';

  @override
  String get deleteReasonTechnicalIssues => 'Previše tehničkih problema';

  @override
  String get deleteReasonFoundAlternative => 'Koristim nešto drugo';

  @override
  String get deleteReasonTakingBreak => 'Samo uzimam pauzu';

  @override
  String get deleteReasonOther => 'Ostalo';

  @override
  String get deleteFlowFeedbackTitle => 'Recite nam više';

  @override
  String get deleteFlowFeedbackSubtitle => 'Što bi Omi učinilo prikladnim za vas?';

  @override
  String get deleteFlowFeedbackHint => 'Neobavezno — vaše misli pomažu nam izgraditi bolji proizvod.';

  @override
  String get deleteFlowConfirmTitle => 'Ovo je trajno';

  @override
  String get deleteFlowConfirmSubtitle => 'Nakon brisanja računa nije ga moguće vratiti.';

  @override
  String get deleteConsequenceSubscription => 'Bilo koja aktivna pretplata bit će otkazana.';

  @override
  String get deleteConsequenceNoRecovery => 'Vaš račun nije moguće vratiti — čak ni preko podrške.';

  @override
  String get deleteTypeToConfirm => 'Upišite DELETE za potvrdu';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'Trajno izbriši račun';

  @override
  String get keepMyAccount => 'Zadrži moj račun';

  @override
  String get deleteAccountFailed => 'Brisanje vašeg računa nije uspjelo. Pokušajte ponovno.';

  @override
  String get planUpdate => 'Ažuriranje plana';

  @override
  String get planDeprecationMessage =>
      'Vaš Unlimited plan se ukida. Prijeđite na Operator plan — iste izvrsne značajke za \$49/mj. Vaš trenutni plan će nastaviti raditi u međuvremenu.';

  @override
  String get upgradeYourPlan => 'Nadogradite svoj plan';

  @override
  String get youAreOnAPaidPlan => 'Na plaćenom ste planu.';

  @override
  String get chatTitle => 'Chat';

  @override
  String get chatMessages => 'poruka';

  @override
  String get unlimitedChatThisMonth => 'Neograničene poruke ovog mjeseca';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used od $limit proračuna korišteno';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used od $limit poruka korišteno ovog mjeseca';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit korišteno';
  }

  @override
  String get chatLimitReachedUpgrade => 'Dostignut limit chata. Nadogradite za više poruka.';

  @override
  String get chatLimitReachedTitle => 'Dostignut limit chata';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Koristili ste $used od $limitDisplay na planu $plan.';
  }

  @override
  String resetsInDays(int count) {
    return 'Resetira se za $count dana';
  }

  @override
  String resetsInHours(int count) {
    return 'Resetira se za $count sati';
  }

  @override
  String get resetsSoon => 'Uskoro se resetira';

  @override
  String get upgradePlan => 'Nadogradi plan';

  @override
  String get billingMonthly => 'Mjesečno';

  @override
  String get billingYearly => 'Godišnje';

  @override
  String get savePercent => 'Uštedite ~17%';

  @override
  String get popular => 'Popularno';

  @override
  String get currentPlan => 'Trenutni';

  @override
  String neoSubtitle(int count) {
    return '$count pitanja mjesečno';
  }

  @override
  String operatorSubtitle(int count) {
    return '$count pitanja mjesečno';
  }

  @override
  String get architectSubtitle => 'Napredni AI — tisuće razgovora + agentna automatizacija';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Chat: \$$used / \$$limit iskorišteno ovog mjeseca';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Chat: \$$used iskorišteno ovog mjeseca';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Chat: $used / $limit poruka ovog mjeseca';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Chat: $used poruka ovog mjeseca';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'Dosegli ste svoj mjesečni limit. Nadogradite da nastavite razgovarati s Omi bez ograničenja.';

  @override
  String get voiceResponseAudio => 'Pročitaj Omijev odgovor naglas';

  @override
  String get voiceResponseMode => 'Glasovni odgovor';

  @override
  String get voiceResponseModeTitle => 'Kada izgovarati odgovore';

  @override
  String get voiceResponseOff => 'Isključeno';

  @override
  String get voiceResponseHeadphonesOnly => 'Samo slušalice';

  @override
  String get voiceResponseAlways => 'Uvijek';

  @override
  String get agreeAndContinue => 'Slažem se i nastavi';

  @override
  String get startVoiceRecording => 'Pokreni glasovno snimanje';

  @override
  String get startCallRecording => 'Pokreni snimanje poziva';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'Glasovni način';

  @override
  String get quickActionAskOmi => 'Pitajte Omi bilo što';

  @override
  String get record => 'Snimi';

  @override
  String get stop => 'Zaustavi';

  @override
  String get recordWithPhoneMic => 'Snimaj telefonskim mikrofonom';

  @override
  String get recordWithPhoneMicSubtitle => 'Snimite zvuk oko vas';

  @override
  String get phoneCall => 'Telefonski poziv';

  @override
  String get phoneCallSubtitle => 'Snimajte poziv s transkripcijom uživo';

  @override
  String get searchActionItems => 'Pretraži akcijske stavke';

  @override
  String get selectActionItems => 'Odaberi više';

  @override
  String chooseExportDestination(int count) {
    return 'Izvezi $count stavku/i u…';
  }

  @override
  String get bulkExportInProgress => 'Izvoz u tijeku…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Izvezeno $count u $platform';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Izvezeno $success od $total u $platform';
  }

  @override
  String get showCompletedTasks => 'Prikaži dovršene';

  @override
  String get hideCompletedTasks => 'Sakrij dovršene';

  @override
  String get selectAllTasksMenu => 'Odaberi sve';

  @override
  String get connectTaskAppToExport => 'Povežite aplikaciju za zadatke u Postavkama za izvoz';

  @override
  String get connectAction => 'Poveži';

  @override
  String get deselectAllTasksMenu => 'Poništi odabir svih';
}
