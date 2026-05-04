// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Bosnian (`bs`).
class AppLocalizationsBs extends AppLocalizations {
  AppLocalizationsBs([String locale = 'bs']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Razgovor';

  @override
  String get transcriptTab => 'Prepis';

  @override
  String get actionItemsTab => 'Stavke za akciju';

  @override
  String get deleteConversationTitle => 'Izbrisati razgovor?';

  @override
  String get deleteConversationMessage =>
      'Ovo će takođe izbrisati povezane uspomene, zadatke i audio fajlove. Ova radnja se ne može opozvati.';

  @override
  String get confirm => 'Potvrdi';

  @override
  String get cancel => 'Otkaži';

  @override
  String get ok => 'U redu';

  @override
  String get delete => 'Izbriši';

  @override
  String get add => 'Dodaj';

  @override
  String get update => 'Ažuriraj';

  @override
  String get save => 'Sačuvaj';

  @override
  String get edit => 'Uredi';

  @override
  String get close => 'Zatvori';

  @override
  String get clear => 'Očisti';

  @override
  String get copyTranscript => 'Kopiraj prepis';

  @override
  String get copySummary => 'Kopiraj sažetak';

  @override
  String get testPrompt => 'Test upit';

  @override
  String get reprocessConversation => 'Ponovna obrada razgovora';

  @override
  String get deleteConversation => 'Izbriši razgovor';

  @override
  String get contentCopied => 'Sadržaj kopiran u međuspremnik';

  @override
  String get failedToUpdateStarred => 'Neuspelo ažuriranje označene stavke.';

  @override
  String get conversationUrlNotShared => 'URL razgovora nije mogao biti deljenje.';

  @override
  String get errorProcessingConversation => 'Greška pri obradi razgovora. Pokušajte ponovo kasnije.';

  @override
  String get noInternetConnection => 'Nema internet konekcije';

  @override
  String get unableToDeleteConversation => 'Neuspešno brisanje razgovora';

  @override
  String get somethingWentWrong => 'Nešto je pošlo po zlu! Pokušajte ponovo kasnije.';

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
  String get createPersonHint => 'Kreiraj novu osobu i trenings Omi-ja da prepozna njihov govor!';

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
  String get selectLanguage => 'Odaberite jezik';

  @override
  String get deleting => 'Brisanje...';

  @override
  String get pleaseCompleteAuthentication =>
      'Molimo vas da završite autentifikaciju u vašem pregledniku. Kada završite, vratite se u aplikaciju.';

  @override
  String get failedToStartAuthentication => 'Neuspelo pokretanje autentifikacije';

  @override
  String get importStarted => 'Uvoz je počeo! Bićete obaviješteni kada je gotov.';

  @override
  String get failedToStartImport => 'Neuspelo pokretanje uvoza. Pokušajte ponovo.';

  @override
  String get couldNotAccessFile => 'Nije moguće pristupiti odabranoj datoteci';

  @override
  String get askOmi => 'Pitaj Omija';

  @override
  String get done => 'Gotovo';

  @override
  String get disconnected => 'Iskopčano';

  @override
  String get searching => 'Pretraživanje...';

  @override
  String get connectDevice => 'Poveži uređaj';

  @override
  String get monthlyLimitReached => 'Dostigli ste svoje mesečno ograničenje.';

  @override
  String get checkUsage => 'Proverite upotrebu';

  @override
  String get syncingRecordings => 'Sinhronizovanje snimaka';

  @override
  String get recordingsToSync => 'Snimci za sinhronizovanje';

  @override
  String get allCaughtUp => 'Sve je ažurirano';

  @override
  String get sync => 'Sinhronizuj';

  @override
  String get pendantUpToDate => 'Privesak je ažuran';

  @override
  String get allRecordingsSynced => 'Svi snimci su sinhronizovani';

  @override
  String get syncingInProgress => 'Sinhronizovanje je u toku';

  @override
  String get readyToSync => 'Spremno za sinhronizovanje';

  @override
  String get tapSyncToStart => 'Dodirnite Sinhronizuj da počnete';

  @override
  String get pendantNotConnected => 'Privesak nije povezan. Povežite se za sinhronizovanje.';

  @override
  String get everythingSynced => 'Sve je već sinhronizovano.';

  @override
  String get recordingsNotSynced => 'Imate snimke koji nisu sinhronizovani.';

  @override
  String get syncingBackground => 'Nastavićemo da sinhronizujemo vaše snimke u pozadini.';

  @override
  String get noConversationsYet => 'Nema razgovora';

  @override
  String get noStarredConversations => 'Nema označenih razgovora';

  @override
  String get starConversationHint => 'Da označite razgovor, otvorite ga i dodirnite ikonu zvezdice u zaglavlje.';

  @override
  String get searchConversations => 'Pretraži razgovore...';

  @override
  String selectedCount(int count, Object s) {
    return '$count izabrano';
  }

  @override
  String get merge => 'Spoji';

  @override
  String get mergeConversations => 'Spoji razgovore';

  @override
  String mergeConversationsMessage(int count) {
    return 'Ovo će kombinovati $count razgovora u jedan. Sav sadržaj će biti spojen i regenerisan.';
  }

  @override
  String get mergingInBackground => 'Spajanje u pozadini. Ovo može potrajati trenutak.';

  @override
  String get failedToStartMerge => 'Neuspelo pokretanje spajanja';

  @override
  String get askAnything => 'Pitaj šta god';

  @override
  String get noMessagesYet => 'Nema poruka!\nZašto ne počnete razgovor?';

  @override
  String get deletingMessages => 'Brisanje vaših poruka iz Omiove memorije...';

  @override
  String get messageCopied => '✨ Poruka kopirana u međuspremnik';

  @override
  String get cannotReportOwnMessage => 'Ne možete prijaviti svoje poruke.';

  @override
  String get reportMessage => 'Prijavi poruku';

  @override
  String get reportMessageConfirm => 'Jeste li sigurni da želite da prijavite ovu poruku?';

  @override
  String get messageReported => 'Poruka je uspešno prijavljena.';

  @override
  String get thankYouFeedback => 'Hvala vam na povratnoj informaciji!';

  @override
  String get clearChat => 'Očisti čat';

  @override
  String get clearChatConfirm => 'Jeste li sigurni da želite da očistite čat? Ova radnja se ne može opozvati.';

  @override
  String get maxFilesLimit => 'Možete najednom učitati samo 4 datoteke';

  @override
  String get chatWithOmi => 'Čatujte sa Omijom';

  @override
  String get apps => 'Aplikacije';

  @override
  String get noAppsFound => 'Nema pronađenih aplikacija';

  @override
  String get tryAdjustingSearch => 'Pokušajte da prilagodite pretragu ili filtere';

  @override
  String get createYourOwnApp => 'Kreiraj svoju aplikaciju';

  @override
  String get buildAndShareApp => 'Izgradi i deli svoju prilagođenu aplikaciju';

  @override
  String get searchApps => 'Pretraži aplikacije...';

  @override
  String get myApps => 'Moje aplikacije';

  @override
  String get installedApps => 'Instalirane aplikacije';

  @override
  String get unableToFetchApps =>
      'Nije moguće preuzeti aplikacije :(\n\nMolimo proverite vašu internet konekciju i pokušajte ponovo.';

  @override
  String get aboutOmi => 'O Omiju';

  @override
  String get privacyPolicy => 'Politika privatnosti';

  @override
  String get visitWebsite => 'Poseti vebsajt';

  @override
  String get helpOrInquiries => 'Trebate li pomoć ili imate pitanja?';

  @override
  String get joinCommunity => 'Pridruži se zajednici!';

  @override
  String get membersAndCounting => '8000+ članova i raste.';

  @override
  String get deleteAccountTitle => 'Izbriši nalog';

  @override
  String get deleteAccountConfirm => 'Jeste li sigurni da želite da izbrišete svoj nalog?';

  @override
  String get cannotBeUndone => 'Ovo se ne može opozvati.';

  @override
  String get allDataErased => 'Sve vaše uspomene i razgovori će biti zauvek izbrisani.';

  @override
  String get appsDisconnected => 'Vaše aplikacije i integracije će biti odmah prekopčane.';

  @override
  String get exportBeforeDelete =>
      'Možete izvesti svoje podatke pre nego što izbrisati nalog, ali kada je izbrisano, ne može biti vraćeno.';

  @override
  String get deleteAccountCheckbox =>
      'Razumem da je brisanje mog naloga trajno i svi podaci, uključujući uspomene i razgovore, će biti izgubljeni i ne mogu biti vraćeni.';

  @override
  String get areYouSure => 'Jeste li sigurni?';

  @override
  String get deleteAccountFinal =>
      'Ova radnja je nepovratna i će zauvek izbrisati vaš nalog i sve povezane podatke. Jeste li sigurni da želite da nastavite?';

  @override
  String get deleteNow => 'Izbriši sada';

  @override
  String get goBack => 'Nazad';

  @override
  String get checkBoxToConfirm =>
      'Označite polje da potvrdite da razumete da je brisanje vašeg naloga trajno i nepovratno.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Ime';

  @override
  String get email => 'E-pošta';

  @override
  String get customVocabulary => 'Prilagođeni rečnik';

  @override
  String get identifyingOthers => 'Identifikovanje drugih';

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
  String get systemDefault => 'Podrazumevano od strane sistema';

  @override
  String get planAndUsage => 'Plan & Upotreba';

  @override
  String get offlineSync => 'Offline sinhronizovanje';

  @override
  String get deviceSettings => 'Postavke uređaja';

  @override
  String get integrations => 'Integracije';

  @override
  String get feedbackBug => 'Povratna informacija / Bug';

  @override
  String get helpCenter => 'Centar za pomoć';

  @override
  String get developerSettings => 'Postavke razvojnog inženjera';

  @override
  String get getOmiForMac => 'Nabavi Omija za Mac';

  @override
  String get referralProgram => 'Program referiranja';

  @override
  String get signOut => 'Odjava';

  @override
  String get appAndDeviceCopied => 'Detalji aplikacije i uređaja kopirani';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Vaša privatnost, vaša kontrola';

  @override
  String get privacyIntro =>
      'U Omiju smo posvećeni zaštiti vaše privatnosti. Ova stranica vam omogućava da kontrolišete kako se vaši podaci čuvaju i koriste.';

  @override
  String get learnMore => 'Saznajte više...';

  @override
  String get dataProtectionLevel => 'Nivo zaštite podataka';

  @override
  String get dataProtectionDesc =>
      'Vaši podaci su podrazumevano zaštićeni jakim šifrovanjem. Pregledajte vaše postavke i budućne opcije privatnosti ispod.';

  @override
  String get appAccess => 'Pristup aplikacije';

  @override
  String get appAccessDesc =>
      'Sledeće aplikacije mogu pristupiti vašim podacima. Dodirnite aplikaciju da upravljate njenim dozvolama.';

  @override
  String get noAppsExternalAccess => 'Nema instalirane aplikacije koje imaju spoljni pristup vašim podacima.';

  @override
  String get deviceName => 'Naziv uređaja';

  @override
  String get deviceId => 'ID uređaja';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'SD kartica sinhronizovanje';

  @override
  String get hardwareRevision => 'Revizija hardvera';

  @override
  String get modelNumber => 'Broj modela';

  @override
  String get manufacturer => 'Proizvođač';

  @override
  String get doubleTap => 'Dupli dodir';

  @override
  String get ledBrightness => 'Svetlina LED-a';

  @override
  String get micGain => 'Pojačanje mikrofona';

  @override
  String get disconnect => 'Iskopčaj';

  @override
  String get forgetDevice => 'Zaboravi uređaj';

  @override
  String get chargingIssues => 'Problemi sa punjenjem';

  @override
  String get disconnectDevice => 'Iskopčaj uređaj';

  @override
  String get unpairDevice => 'Rozpari uređaj';

  @override
  String get unpairAndForget => 'Rozpari i zaboravi uređaj';

  @override
  String get deviceDisconnectedMessage => 'Vaš Omi je iskopčan 😔';

  @override
  String get deviceUnpairedMessage =>
      'Uređaj je rozparen. Otite na Postavke > Bluetooth i zaboravite uređaj da završite rasparovanje.';

  @override
  String get unpairDialogTitle => 'Rozpari uređaj';

  @override
  String get unpairDialogMessage =>
      'Ovo će raspariti uređaj tako da može biti povezan sa drugim telefonom. Trebate otiti na Postavke > Bluetooth i zaboraviti uređaj da završite proces.';

  @override
  String get deviceNotConnected => 'Uređaj nije povezan';

  @override
  String get connectDeviceMessage => 'Povežite svoj Omi uređaj da pristupite\npostavkama uređaja i prilagođavanju';

  @override
  String get deviceInfoSection => 'Informacije o uređaju';

  @override
  String get customizationSection => 'Prilagođavanje';

  @override
  String get hardwareSection => 'Hardver';

  @override
  String get v2Undetected => 'V2 nije detektovano';

  @override
  String get v2UndetectedMessage =>
      'Vidimo da imate V1 uređaj ili vaš uređaj nije povezan. Funkcionalnost SD kartice dostupna je samo za V2 uređaje.';

  @override
  String get endConversation => 'Završi razgovor';

  @override
  String get pauseResume => 'Pauzira/Nastavi';

  @override
  String get starConversation => 'Označi razgovor';

  @override
  String get doubleTapAction => 'Akcija duplog dodira';

  @override
  String get endAndProcess => 'Završi i obradi razgovor';

  @override
  String get pauseResumeRecording => 'Pauzira/Nastavi snimanje';

  @override
  String get starOngoing => 'Označi tekući razgovor';

  @override
  String get off => 'Isključeno';

  @override
  String get max => 'Maksimalno';

  @override
  String get mute => 'Utišaj';

  @override
  String get quiet => 'Tiho';

  @override
  String get normal => 'Normalno';

  @override
  String get high => 'Visoko';

  @override
  String get micGainDescMuted => 'Mikrofon je utišan';

  @override
  String get micGainDescLow => 'Veoma tiho - za bučne okoline';

  @override
  String get micGainDescModerate => 'Tiho - za umeren buku';

  @override
  String get micGainDescNeutral => 'Neutralno - uravnoteženo snimanje';

  @override
  String get micGainDescSlightlyBoosted => 'Blago pojačano - normalna upotreba';

  @override
  String get micGainDescBoosted => 'Pojačano - za tihe okoline';

  @override
  String get micGainDescHigh => 'Visoko - za daleke ili tihe glasove';

  @override
  String get micGainDescVeryHigh => 'Veoma visoko - za veoma tihe izvore';

  @override
  String get micGainDescMax => 'Maksimalno - koristite sa pažnjom';

  @override
  String get developerSettingsTitle => 'Postavke razvojnog inženjera';

  @override
  String get saving => 'Čuvanje...';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Prepis';

  @override
  String get transcriptionConfig => 'Konfigurišite dobavljača STT-a';

  @override
  String get conversationTimeout => 'Vremensko ograničenje razgovora';

  @override
  String get conversationTimeoutConfig => 'Postavite kada se razgovori automatski završavaju';

  @override
  String get importData => 'Uvezi podatke';

  @override
  String get importDataConfig => 'Uvezite podatke iz drugih izvora';

  @override
  String get debugDiagnostics => 'Otklanjanje grešaka i dijagnostika';

  @override
  String get endpointUrl => 'URL krajnje tačke';

  @override
  String get noApiKeys => 'Nema API ključeva';

  @override
  String get createKeyToStart => 'Kreirajte ključ da počnete';

  @override
  String get createKey => 'Kreiraj ključ';

  @override
  String get docs => 'Dokumentacija';

  @override
  String get yourOmiInsights => 'Vaši Omi uvidi';

  @override
  String get today => 'Danas';

  @override
  String get thisMonth => 'Ovaj mesec';

  @override
  String get thisYear => 'Ove godine';

  @override
  String get allTime => 'Celo vreme';

  @override
  String get noActivityYet => 'Nema aktivnosti';

  @override
  String get startConversationToSeeInsights => 'Započnite razgovor sa Omijom\nda vidite vaše uvide o upotrebi ovde.';

  @override
  String get listening => 'Slušanje';

  @override
  String get listeningSubtitle => 'Ukupno vreme koje je Omi aktivno slušao.';

  @override
  String get understanding => 'Razumevanje';

  @override
  String get understandingSubtitle => 'Reči razumevene iz vaših razgovora.';

  @override
  String get providing => 'Pružanje';

  @override
  String get providingSubtitle => 'Stavke za akciju i beleške automatski snimljene.';

  @override
  String get remembering => 'Pamćenje';

  @override
  String get rememberingSubtitle => 'Činjenice i detalje zapamćene za vas.';

  @override
  String get unlimitedPlan => 'Neograničeni plan';

  @override
  String get managePlan => 'Upravljaj planom';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Vaš plan će biti otkazan na $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Vaš plan se obnavlja na $date.';
  }

  @override
  String get basicPlan => 'Besplatni plan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used od $limit min korišćeno';
  }

  @override
  String get upgrade => 'Nadogradi';

  @override
  String get upgradeToUnlimited => 'Nadogradi na neograničeno';

  @override
  String basicPlanDesc(int limit) {
    return 'Vaš plan uključuje $limit besplatnih minuta mesečno. Nadogradite se da postane neograničeno.';
  }

  @override
  String get shareStatsMessage => 'Dele svoje Omi statistike! (omi.me - vaš AI asistent koji je uvek dostupan)';

  @override
  String get sharePeriodToday => 'Danas, omi je:';

  @override
  String get sharePeriodMonth => 'Ovaj mesec, omi je:';

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
    return '🧠 Razumeo $words reči';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Dao $count uvida';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Zapamtio $count uspomene';
  }

  @override
  String get debugLogs => 'Logovi otklanjanja grešaka';

  @override
  String get debugLogsAutoDelete => 'Automatski se briše nakon 3 dana.';

  @override
  String get debugLogsDesc => 'Pomaže dijagnostici problema';

  @override
  String get noLogFilesFound => 'Nema pronađenih log datoteka.';

  @override
  String get omiDebugLog => 'Omi log otklanjanja grešaka';

  @override
  String get logShared => 'Log je deljenje';

  @override
  String get selectLogFile => 'Odaberi log datoteku';

  @override
  String get shareLogs => 'Deli logove';

  @override
  String get debugLogCleared => 'Log otklanjanja grešaka očišćen';

  @override
  String get exportStarted => 'Izvoz je počeo. Ovo može potrajati nekoliko sekundi...';

  @override
  String get exportAllData => 'Izvezi sve podatke';

  @override
  String get exportDataDesc => 'Izvezite razgovore u JSON datoteku';

  @override
  String get exportedConversations => 'Izveženi razgovori iz Omija';

  @override
  String get exportShared => 'Izvoz je deljenje';

  @override
  String get deleteKnowledgeGraphTitle => 'Izbrisati grafikon znanja?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Ovo će izbrisati sve izvedene podatke grafikona znanja (čvorove i veze). Vaše originalne uspomene će ostati sigurne. Grafikon će biti ponovo izgrađen tokom vremena ili na sledeći zahtev.';

  @override
  String get knowledgeGraphDeleted => 'Grafikon znanja je obrisan';

  @override
  String deleteGraphFailed(String error) {
    return 'Neuspešno brisanje grafikona: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Izbriši grafikon znanja';

  @override
  String get deleteKnowledgeGraphDesc => 'Očisti sve čvorove i veze';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP server';

  @override
  String get mcpServerDesc => 'Povežite AI asistente na vaše podatke';

  @override
  String get serverUrl => 'URL servera';

  @override
  String get urlCopied => 'URL kopiran';

  @override
  String get apiKeyAuth => 'Autentifikacija API ključa';

  @override
  String get header => 'Zaglavlje';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID klijenta';

  @override
  String get clientSecret => 'Tajna klijenta';

  @override
  String get useMcpApiKey => 'Koristite svoj MCP API ključ';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Događaji razgovora';

  @override
  String get newConversationCreated => 'Novi razgovor je kreiran';

  @override
  String get realtimeTranscript => 'Prepis u realnom vremenu';

  @override
  String get transcriptReceived => 'Prepis je primljen';

  @override
  String get audioBytes => 'Audio bajtovi';

  @override
  String get audioDataReceived => 'Audio podaci su primljeni';

  @override
  String get intervalSeconds => 'Interval (sekunde)';

  @override
  String get daySummary => 'Sažetak dana';

  @override
  String get summaryGenerated => 'Sažetak je generisan';

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
  String get understandingWords => 'Razumevanje (reči)';

  @override
  String get insights => 'Uvidi';

  @override
  String get memories => 'Uspomene';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used od $limit min korišćeno ovaj mesec';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used od $limit reči korišćene ovaj mesec';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used od $limit uvida dobijenih ovaj mesec';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used od $limit uspomene kreirane ovaj mesec';
  }

  @override
  String get visibility => 'Vidljivost';

  @override
  String get visibilitySubtitle => 'Kontrolišite koji se razgovori pojavljuju na vašoj listi';

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
      'Razgovori kraći od ovoga će biti skriveni osim ako su omogućeni iznad';

  @override
  String get durationThreshold => 'Prag trajanja';

  @override
  String get durationThresholdDesc => 'Sakrijte razgovore kraće od ovoga';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Prilagođeni rečnik';

  @override
  String get addWords => 'Dodaj reči';

  @override
  String get addWordsDesc => 'Imena, uslovi ili neuobičajne reči';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Poveži';

  @override
  String get comingSoon => 'Uskoro dolazi';

  @override
  String get integrationsFooter => 'Povežite svoje aplikacije da vidite podatke i metrike u čatu.';

  @override
  String get completeAuthInBrowser =>
      'Molimo vas da završite autentifikaciju u vašem pregledniku. Kada završite, vratite se u aplikaciju.';

  @override
  String failedToStartAuth(String appName) {
    return 'Neuspešno pokretanje $appName autentifikacije';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Iskopčaj $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Jeste li sigurni da želite da se iskopčate od $appName? Možete se ponovo povezati bilo kada.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Iskopčan od $appName';
  }

  @override
  String get failedToDisconnect => 'Neuspešno iskopčavanje';

  @override
  String connectTo(String appName) {
    return 'Poveži se sa $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Trebate da autorizujete Omija da pristupi vašim $appName podacima. Ovo će otvoriti vaš preglednika za autentifikaciju.';
  }

  @override
  String get continueAction => 'Nastavi';

  @override
  String get languageTitle => 'Jezik';

  @override
  String get primaryLanguage => 'Primarni jezik';

  @override
  String get automaticTranslation => 'Automatski prevod';

  @override
  String get detectLanguages => 'Detektuj 10+ jezika';

  @override
  String get authorizeSavingRecordings => 'Autorizuj čuvanje snimaka';

  @override
  String get thanksForAuthorizing => 'Hvala što ste autorizovali!';

  @override
  String get needYourPermission => 'Trebamo vašu dozvolu';

  @override
  String get alreadyGavePermission => 'Već ste nam dali dozvolu da čuvamo vaše snimke. Evo podsetnika zašto nam treba:';

  @override
  String get wouldLikePermission => 'Želeli bismo vašu dozvolu da čuvamo vaše govorne snimke. Evo zašto:';

  @override
  String get improveSpeechProfile => 'Poboljšaj svoj profil govora';

  @override
  String get improveSpeechProfileDesc => 'Koristimo snimke da dodatno obučimo i poboljšamo vaš lični profil govora.';

  @override
  String get trainFamilyProfiles => 'Obučite profile za prijatelje i porodicu';

  @override
  String get trainFamilyProfilesDesc =>
      'Vaši snimci nam pomažu da prepoznamo i kreiramo profile za vaše prijatelje i porodicu.';

  @override
  String get enhanceTranscriptAccuracy => 'Poboljšaj tačnost prepisa';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Kako se naš model poboljšava, možemo pružiti bolje rezultate transkripcije za vaše snimke.';

  @override
  String get legalNotice =>
      'Pravna napomena: Zakonitost snimanja i čuvanja podataka glasa može se razlikovati u zavisnosti od vaše lokacije i načina korišćenja ove funkcije. Vaša je odgovornost da osigurate poštovanje lokalnih zakona i propisa.';

  @override
  String get alreadyAuthorized => 'Već autorizovano';

  @override
  String get authorize => 'Autorizuj';

  @override
  String get revokeAuthorization => 'Opozovi autorizaciju';

  @override
  String get authorizationSuccessful => 'Autorizacija je uspešna!';

  @override
  String get failedToAuthorize => 'Nije uspelo autentifikovanje. Pokušajte ponovo.';

  @override
  String get authorizationRevoked => 'Autentifikacija je odbijena.';

  @override
  String get recordingsDeleted => 'Snimanja su obrisana.';

  @override
  String get failedToRevoke => 'Nije uspelo odbijanje autentifikacije. Pokušajte ponovo.';

  @override
  String get permissionRevokedTitle => 'Dozvola je odbijena';

  @override
  String get permissionRevokedMessage => 'Želite li da obrišemo i sva vaša postojeća snimanja?';

  @override
  String get yes => 'Da';

  @override
  String get editName => 'Izmeni ime';

  @override
  String get howShouldOmiCallYou => 'Kako treba da vas Omi naziva?';

  @override
  String get enterYourName => 'Unesite svoje ime';

  @override
  String get nameCannotBeEmpty => 'Ime ne sme biti prazno';

  @override
  String get nameUpdatedSuccessfully => 'Ime je uspešno ažurirano!';

  @override
  String get calendarSettings => 'Postavke kalendara';

  @override
  String get calendarProviders => 'Dobavljači kalendara';

  @override
  String get macOsCalendar => 'macOS Kalendar';

  @override
  String get connectMacOsCalendar => 'Povežite svoj lokalni macOS kalendar';

  @override
  String get googleCalendar => 'Google Kalendar';

  @override
  String get syncGoogleAccount => 'Sinhronizujte sa vašim Google nalogom';

  @override
  String get showMeetingsMenuBar => 'Prikaži nadolazeće sastanke u meniju';

  @override
  String get showMeetingsMenuBarDesc => 'Prikaži sledeći sastanak i vreme do početka u macOS meniju';

  @override
  String get showEventsNoParticipants => 'Prikaži događaje bez učesnika';

  @override
  String get showEventsNoParticipantsDesc =>
      'Kada je omogućeno, Dolazak prikazuje događaje bez učesnika ili video linka.';

  @override
  String get yourMeetings => 'Vaši sastanci';

  @override
  String get refresh => 'Osveži';

  @override
  String get noUpcomingMeetings => 'Nema nadolazećih sastanaka';

  @override
  String get checkingNextDays => 'Proverava se narednih 30 dana';

  @override
  String get tomorrow => 'Sutra';

  @override
  String get googleCalendarComingSoon => 'Integracija sa Google Kalendarom uskoro stiže!';

  @override
  String connectedAsUser(String userId) {
    return 'Povezan kao korisnik: $userId';
  }

  @override
  String get defaultWorkspace => 'Podrazumevana radna oblast';

  @override
  String get tasksCreatedInWorkspace => 'Zadaci će biti kreirani u ovoj radnoj oblasti';

  @override
  String get defaultProjectOptional => 'Podrazumevan projekat (opciono)';

  @override
  String get leaveUnselectedTasks => 'Ostavite neodabrano da kreirate zadatke bez projekta';

  @override
  String get noProjectsInWorkspace => 'Nema pronađenih projekata u ovoj radnoj oblasti';

  @override
  String get conversationTimeoutDesc =>
      'Izaberite koliko dugo čekati u tišini pre nego što se razgovor automatski završi:';

  @override
  String get timeout2Minutes => '2 minuta';

  @override
  String get timeout2MinutesDesc => 'Završi razgovor nakon 2 minuta tišine';

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
    return 'Razgovori će se sada završiti nakon $minutes minuta tišine';
  }

  @override
  String get tellUsPrimaryLanguage => 'Recite nam koji je vaš primarni jezik';

  @override
  String get languageForTranscription => 'Postavite jezik za precizniju transkripciju i personalizovano iskustvo.';

  @override
  String get singleLanguageModeInfo => 'Modus jedan jezik je omogućen. Prevod je onemogućen za veću preciznost.';

  @override
  String get searchLanguageHint => 'Pretražite jezik po imenu ili kodu';

  @override
  String get noLanguagesFound => 'Nijedan jezik nije pronađen';

  @override
  String get skip => 'Preskoči';

  @override
  String languageSetTo(String language) {
    return 'Jezik je postavljen na $language';
  }

  @override
  String get failedToSetLanguage => 'Nije uspelo postavljanje jezika';

  @override
  String appSettings(String appName) {
    return '$appName postavke';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Prekinuti vezu sa $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Ovo će ukloniti vašu $appName autentifikaciju. Trebalo bi da se ponovo povežete da biste je koristili.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Povezan sa $appName';
  }

  @override
  String get account => 'Nalog';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Vaši stavki za akciju biće sinhronizirani sa vašim $appName nalogom';
  }

  @override
  String get defaultSpace => 'Podrazumevani prostor';

  @override
  String get selectSpaceInWorkspace => 'Izaberite prostor u vašoj radnoj oblasti';

  @override
  String get noSpacesInWorkspace => 'Nema pronađenih prostora u ovoj radnoj oblasti';

  @override
  String get defaultList => 'Podrazumevana lista';

  @override
  String get tasksAddedToList => 'Zadaci će biti dodati na ovu listu';

  @override
  String get noListsInSpace => 'Nema pronađenih listi u ovom prostoru';

  @override
  String failedToLoadRepos(String error) {
    return 'Nije uspelo učitavanje repozitorijuma: $error';
  }

  @override
  String get defaultRepoSaved => 'Podrazumevani repozitorijum je sačuvan';

  @override
  String get failedToSaveDefaultRepo => 'Nije uspelo čuvanje podrazumevanog repozitorijuma';

  @override
  String get defaultRepository => 'Podrazumevani repozitorijum';

  @override
  String get selectDefaultRepoDesc =>
      'Izaberite podrazumevani repozitorijum za pravljenje problema. Možete i dalje naznačiti drugačiji repozitorijum pri pravljenju problema.';

  @override
  String get noReposFound => 'Nema pronađenih repozitorijuma';

  @override
  String get private => 'Privatno';

  @override
  String updatedDate(String date) {
    return 'Ažurirano $date';
  }

  @override
  String get yesterday => 'Juče';

  @override
  String daysAgo(int count) {
    return 'pre $count dana';
  }

  @override
  String get oneWeekAgo => 'pre 1 nedelje';

  @override
  String weeksAgo(int count) {
    return 'pre $count nedelja';
  }

  @override
  String get oneMonthAgo => 'pre 1 meseca';

  @override
  String monthsAgo(int count) {
    return 'pre $count meseci';
  }

  @override
  String get issuesCreatedInRepo => 'Problemi će biti kreirani u vašem podrazumevanom repozitorijumu';

  @override
  String get taskIntegrations => 'Integracije zadataka';

  @override
  String get configureSettings => 'Konfigurišite postavke';

  @override
  String get completeAuthBrowser =>
      'Molimo dovršite autentifikaciju u vašem pregledniku. Kada završite, vratite se u aplikaciju.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Nije uspelo pokretanje $appName autentifikacije';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Povežite se sa $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Trebalo bi da autentifikujete Omi da kreira zadatke u vašem $appName nalogu. Ovo će otvoriti vaš preglednik za autentifikaciju.';
  }

  @override
  String get continueButton => 'Nastavi';

  @override
  String appIntegration(String appName) {
    return '$appName integracija';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integracija sa $appName uskoro stiže! Radimo svom snagom da vam donesemo više mogućnosti za upravljanje zadacima.';
  }

  @override
  String get gotIt => 'Razumeo sam';

  @override
  String get tasksExportedOneApp => 'Zadaci se mogu izvoziti u jednu aplikaciju istovremeno.';

  @override
  String get completeYourUpgrade => 'Dovršite vašu nadogradnju';

  @override
  String get importConfiguration => 'Uvezi konfiguraciju';

  @override
  String get exportConfiguration => 'Izvezi konfiguraciju';

  @override
  String get bringYourOwn => 'Dovedite svoje';

  @override
  String get payYourSttProvider => 'Slobodno koristi omi. Plaćate samo vašem STT dobavljaču direktno.';

  @override
  String get freeMinutesMonth => '1.200 besplatnih minuta/mesec uključeno. Neograničeno sa ';

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
  String get invalidJsonConfig => 'Nevažeća JSON konfiguracija';

  @override
  String errorSaving(String error) {
    return 'Greška pri čuvanju: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfiguracija je kopirana u privremenu memoriju';

  @override
  String get pasteJsonConfig => 'Nalepite vašu JSON konfiguraciju ispod:';

  @override
  String get addApiKeyAfterImport => 'Trebalo bi da dodate vlastiti API ključ nakon uvoza';

  @override
  String get paste => 'Nalepite';

  @override
  String get import => 'Uvezi';

  @override
  String get invalidProviderInConfig => 'Nevažeći dobavljač u konfiguraciji';

  @override
  String importedConfig(String providerName) {
    return 'Uvezena $providerName konfiguracija';
  }

  @override
  String invalidJson(String error) {
    return 'Nevažeći JSON: $error';
  }

  @override
  String get provider => 'Dobavljač';

  @override
  String get live => 'Uživo';

  @override
  String get onDevice => 'Na uređaju';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Unesite vašu STT HTTP krajnju tačku';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Unesite vašu uživo STT WebSocket krajnju tačku';

  @override
  String get apiKey => 'API ključ';

  @override
  String get enterApiKey => 'Unesite vaš API ključ';

  @override
  String get storedLocallyNeverShared => 'Čuvano lokalno, nikad nije deljeno';

  @override
  String get host => 'Domaćin';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Napredniji';

  @override
  String get configuration => 'Konfiguracija';

  @override
  String get requestConfiguration => 'Konfiguracija zahteva';

  @override
  String get responseSchema => 'Šema odgovora';

  @override
  String get modified => 'Izmenjeno';

  @override
  String get resetRequestConfig => 'Vratite konfiguraciju zahteva na podrazumevanu';

  @override
  String get logs => 'Logovi';

  @override
  String get logsCopied => 'Logovi su kopirani';

  @override
  String get noLogsYet => 'Nema logova. Počnite sa snimanjem da vidite prilagođenu STT aktivnost.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device koristi $reason. Omi će biti korišćen.';
  }

  @override
  String get omiTranscription => 'Omi transkripcija';

  @override
  String get bestInClassTranscription => 'Najbolja transkripcija sa nultom konfiguracijom';

  @override
  String get instantSpeakerLabels => 'Trenutni labele govornika';

  @override
  String get languageTranslation => 'Prevod na 100+ jezika';

  @override
  String get optimizedForConversation => 'Optimizovano za razgovor';

  @override
  String get autoLanguageDetection => 'Automatsko otkrivanje jezika';

  @override
  String get highAccuracy => 'Visoka preciznost';

  @override
  String get privacyFirst => 'Privatnost na prvom mestu';

  @override
  String get saveChanges => 'Sačuva izmene';

  @override
  String get resetToDefault => 'Vratite na podrazumevano';

  @override
  String get viewTemplate => 'Pogledaj šablon';

  @override
  String get trySomethingLike => 'Pokušajte sa nečim poput...';

  @override
  String get tryIt => 'Pokušajte';

  @override
  String get creatingPlan => 'Pravljenje plana';

  @override
  String get developingLogic => 'Razvoj logike';

  @override
  String get designingApp => 'Dizajniranje aplikacije';

  @override
  String get generatingIconStep => 'Pravljenje ikone';

  @override
  String get finalTouches => 'Završne izmene';

  @override
  String get processing => 'Obrada...';

  @override
  String get features => 'Karakteristike';

  @override
  String get creatingYourApp => 'Pravljenje vaše aplikacije...';

  @override
  String get generatingIcon => 'Pravljenje ikone...';

  @override
  String get whatShouldWeMake => 'Šta bismo trebalo da napravimo?';

  @override
  String get appName => 'Naziv aplikacije';

  @override
  String get description => 'Opis';

  @override
  String get publicLabel => 'Javno';

  @override
  String get privateLabel => 'Privatno';

  @override
  String get free => 'Besplatno';

  @override
  String get perMonth => '/ Mesec';

  @override
  String get tailoredConversationSummaries => 'Prilagođena rezimea razgovora';

  @override
  String get customChatbotPersonality => 'Prilagođena ličnost chatbota';

  @override
  String get makePublic => 'Učini javnim';

  @override
  String get anyoneCanDiscover => 'Bilo ko može da otkrije vašu aplikaciju';

  @override
  String get onlyYouCanUse => 'Samo vi možete koristiti ovu aplikaciju';

  @override
  String get paidApp => 'Plaćena aplikacija';

  @override
  String get usersPayToUse => 'Korisnici plaćaju da koriste vašu aplikaciju';

  @override
  String get freeForEveryone => 'Besplatno za sve';

  @override
  String get perMonthLabel => '/ mesec';

  @override
  String get creating => 'Pravljenje...';

  @override
  String get createApp => 'Kreiraj aplikaciju';

  @override
  String get searchingForDevices => 'Pretraga uređaja...';

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
  String get pairingSuccessful => 'UPARIVANJE JE USPELO';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Greška pri povezivanju sa Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Ne prikazuj ponovo';

  @override
  String get iUnderstand => 'Razumeo sam';

  @override
  String get enableBluetooth => 'Omogući Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi koristi Bluetooth da bi se povezao sa vašim nosivim uređajem. Molimo omogućite Bluetooth i pokušajte ponovo.';

  @override
  String get contactSupport => 'Kontaktiraj podršku?';

  @override
  String get connectLater => 'Povežite se kasnije';

  @override
  String get grantPermissions => 'Dodelite dozvole';

  @override
  String get backgroundActivity => 'Aktivnost u pozadini';

  @override
  String get backgroundActivityDesc => 'Dozvolite da Omi radi u pozadini za bolju stabilnost';

  @override
  String get locationAccess => 'Pristup lokaciji';

  @override
  String get locationAccessDesc => 'Omogućite lokalnost u pozadini za puno iskustvo';

  @override
  String get notifications => 'Obaveštenja';

  @override
  String get notificationsDesc => 'Omogućite obaveštenja da budete informisani';

  @override
  String get locationServiceDisabled => 'Lokacijska usluga je onemogućena';

  @override
  String get locationServiceDisabledDesc =>
      'Lokacijska usluga je onemogućena. Molimo idite na Postavke > Privatnost i bezbednost > Usluge lokacije i omogućite je';

  @override
  String get backgroundLocationDenied => 'Pristup lokalnosti u pozadini je odbijen';

  @override
  String get backgroundLocationDeniedDesc =>
      'Molimo idite na postavke uređaja i postavite dozvolu za lokaciju na \"Uvek dozvoli\"';

  @override
  String get lovingOmi => 'Vam se sviđa Omi?';

  @override
  String get leaveReviewIos =>
      'Pomozite nam da dosegnemo više ljudi ostavljanjem recenzije u App Store-u. Vaša povratna informacija znači nam sve!';

  @override
  String get leaveReviewAndroid =>
      'Pomozite nam da dosegnemo više ljudi ostavljanjem recenzije u Google Play Store-u. Vaša povratna informacija znači nam sve!';

  @override
  String get rateOnAppStore => 'Oceni u App Store-u';

  @override
  String get rateOnGooglePlay => 'Oceni na Google Play';

  @override
  String get maybeLater => 'Možda kasnije';

  @override
  String get speechProfileIntro => 'Omi trebا da nauči vaše ciljeve i vaš glas. Moći ćete ga da izmenjujete kasnije.';

  @override
  String get getStarted => 'Početak';

  @override
  String get allDone => 'Sve je gotovo!';

  @override
  String get keepGoing => 'Nastavite, odličan ste';

  @override
  String get skipThisQuestion => 'Preskoči ovo pitanje';

  @override
  String get skipForNow => 'Preskoči za sada';

  @override
  String get connectionError => 'Greška u konekciji';

  @override
  String get connectionErrorDesc =>
      'Nije uspelo povezivanje na server. Molimo proverite vašu internet konekciju i pokušajte ponovo.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Nevažeće snimanje detektovano';

  @override
  String get multipleSpeakersDesc =>
      'Čini se da ima više govornika u snimanju. Molimo uverite se da ste u tihoj lokaciji i pokušajte ponovo.';

  @override
  String get tooShortDesc => 'Nema dovoljno govora otkrivenog. Molimo govorite više i pokušajte ponovo.';

  @override
  String get invalidRecordingDesc => 'Molimo uverite se da ste govorili najmanje 5 sekundi i ne više od 90.';

  @override
  String get areYouThere => 'Jeste li tu?';

  @override
  String get noSpeechDesc =>
      'Nismo mogli detektovati bilo kakav govor. Molimo govorite najmanje 10 sekundi i ne više od 3 minuta.';

  @override
  String get connectionLost => 'Veza je prekinuta';

  @override
  String get connectionLostDesc => 'Veza je prekinuta. Molimo proverite vašu internet konekciju i pokušajte ponovo.';

  @override
  String get tryAgain => 'Pokušajte ponovo';

  @override
  String get connectOmiOmiGlass => 'Povežite Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Nastavite bez uređaja';

  @override
  String get permissionsRequired => 'Dozvole su obavezne';

  @override
  String get permissionsRequiredDesc =>
      'Ova aplikacija koristi Bluetooth i dozvole lokacije za pravilno funkcionisanje. Molimo omogućite ih u postavkama.';

  @override
  String get openSettings => 'Otvorite postavke';

  @override
  String get wantDifferentName => 'Želite li da se zoveš nečim drugim?';

  @override
  String get whatsYourName => 'Kako se zoveš?';

  @override
  String get speakTranscribeSummarize => 'Govorite. Transkribirajte. Rezimeirajte.';

  @override
  String get signInWithApple => 'Prijavite se sa Apple';

  @override
  String get signInWithGoogle => 'Prijavite se sa Google';

  @override
  String get byContinuingAgree => 'Nastavljanjem, slažete se sa našim ';

  @override
  String get termsOfUse => 'Uslovima korišćenja';

  @override
  String get omiYourAiCompanion => 'Omi – Vaš AI pratilac';

  @override
  String get captureEveryMoment =>
      'Uhvatite svakog trenutka. Dobijte AI-powered\nrezimee. Nikada više ne pisati zabelešte.';

  @override
  String get appleWatchSetup => 'Apple Watch postavljanje';

  @override
  String get permissionRequestedExclaim => 'Dozvola je tražena!';

  @override
  String get microphonePermission => 'Dozvola za mikrofon';

  @override
  String get permissionGrantedNow =>
      'Dozvola je data! Sada:\n\nOtvorite Omi aplikaciju na svom satu i dodirnite \"Nastavi\" ispod';

  @override
  String get needMicrophonePermission =>
      'Trebamo dozvolu za mikrofon.\n\n1. Dodirnite \"Dodelite dozvolu\"\n2. Dozvolite na vašem iPhone-u\n3. Aplikacija na satu će se zatvoriti\n4. Ponovo otvorite i dodirnite \"Nastavi\"';

  @override
  String get grantPermissionButton => 'Dodelite dozvolu';

  @override
  String get needHelp => 'Trebate li pomoć?';

  @override
  String get troubleshootingSteps =>
      'Rešavanje problema:\n\n1. Uverite se da je Omi instaliran na vašem satu\n2. Otvorite Omi aplikaciju na svom satu\n3. Tražite skočni prozor dozvole\n4. Dodirnite \"Dozvoli\" kada se traži\n5. Aplikacija na vašem satu će se zatvoriti - ponovo je otvorite\n6. Vratite se i dodirnite \"Nastavi\" na vašem iPhone-u';

  @override
  String get recordingStartedSuccessfully => 'Snimanje je uspešno počelo!';

  @override
  String get permissionNotGrantedYet =>
      'Dozvola još nije data. Molimo uverite se da ste dozvolili pristup mikrofonu i ponovo otvorili aplikaciju na vašem satu.';

  @override
  String errorRequestingPermission(String error) {
    return 'Greška pri traženju dozvole: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Greška pri pokretanju snimanja: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Izaberite svoj primarni jezik';

  @override
  String get languageBenefits => 'Postavite jezik za precizniju transkripciju i personalizovano iskustvo';

  @override
  String get whatsYourPrimaryLanguage => 'Koji je vaš primarni jezik?';

  @override
  String get selectYourLanguage => 'Izaberite svoj jezik';

  @override
  String get personalGrowthJourney => 'Vaš lični put rasta sa AI koji sluša svaku vašu reč.';

  @override
  String get actionItemsTitle => 'Na- Uradi';

  @override
  String get actionItemsDescription => 'Dodirnite za izmenu • Dugo dodirnite za izbor • Pošvapite za akcije';

  @override
  String get tabToDo => 'Uradi';

  @override
  String get tabDone => 'Gotovo';

  @override
  String get tabOld => 'Staro';

  @override
  String get emptyTodoMessage => '🎉 Sve je gotovo!\nNema stavki za akciju na čekanju';

  @override
  String get emptyDoneMessage => 'Nema završenih stavki';

  @override
  String get emptyOldMessage => '✅ Nema starih zadataka';

  @override
  String get noItems => 'Nema stavki';

  @override
  String get actionItemMarkedIncomplete => 'Stavka za akciju je označena kao neukompletna';

  @override
  String get actionItemCompleted => 'Stavka za akciju je završena';

  @override
  String get deleteActionItemTitle => 'Obriši stavku za akciju';

  @override
  String get deleteActionItemMessage => 'Ste li sigurni da želite da obrišete ovu stavku za akciju?';

  @override
  String get deleteSelectedItemsTitle => 'Obriši izabrane stavke';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Stavka za akciju \"$description\" je obrisana';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'Nije uspelo brisanje stavke za akciju';

  @override
  String get failedToDeleteItems => 'Nije uspelo brisanje stavki';

  @override
  String get failedToDeleteSomeItems => 'Nije uspelo brisanje nekih stavki';

  @override
  String get welcomeActionItemsTitle => 'Spremni za stavke akcije';

  @override
  String get welcomeActionItemsDescription =>
      'Vaš AI će automatski izvlačiti zadatke i stavke za akciju iz vaših razgovora. Pojaviće se ovde kada budu kreirane.';

  @override
  String get autoExtractionFeature => 'Automatski ekstrahuje iz razgovora';

  @override
  String get editSwipeFeature => 'Dodirnite za izmenu, pošvapite da završite ili obrišete';

  @override
  String itemsSelected(int count) {
    return '$count izabrano';
  }

  @override
  String get selectAll => 'Izaberi sve';

  @override
  String get deleteSelected => 'Obriši izabrane';

  @override
  String get searchMemories => 'Pretražite uspomene...';

  @override
  String get memoryDeleted => 'Uspomena je obrisana.';

  @override
  String get undo => 'Opozovi';

  @override
  String get noMemoriesYet => '🧠 Nema uspomena';

  @override
  String get noAutoMemories => 'Nema auto-ekstrahovanих uspomena';

  @override
  String get noManualMemories => 'Nema ručno kreiranih uspomena';

  @override
  String get noMemoriesInCategories => 'Nema uspomena u ovim kategorijama';

  @override
  String get noMemoriesFound => '🔍 Nema pronađenih uspomena';

  @override
  String get addFirstMemory => 'Dodajte vašu prvu uspomenu';

  @override
  String get clearMemoryTitle => 'Obriši Omi-jevu memoriju';

  @override
  String get clearMemoryMessage =>
      'Ste li sigurni da želite da obrišete Omi-jevu memoriju? Ova akcija se ne može poništiti.';

  @override
  String get clearMemoryButton => 'Obriši memoriju';

  @override
  String get memoryClearedSuccess => 'Omi-jeva memorija o vama je obrisana';

  @override
  String get noMemoriesToDelete => 'Nema uspomena za brisanje';

  @override
  String get createMemoryTooltip => 'Kreiraj novu uspomenu';

  @override
  String get createActionItemTooltip => 'Kreiraj novu stavku za akciju';

  @override
  String get memoryManagement => 'Upravljanje uspomenama';

  @override
  String get filterMemories => 'Filtriraj uspomene';

  @override
  String totalMemoriesCount(int count) {
    return 'Imate $count ukupnih uspomena';
  }

  @override
  String get publicMemories => 'Javne uspomene';

  @override
  String get privateMemories => 'Privatne uspomene';

  @override
  String get makeAllPrivate => 'Učini sve uspomene privatne';

  @override
  String get makeAllPublic => 'Učini sve uspomene javne';

  @override
  String get deleteAllMemories => 'Obriši sve uspomene';

  @override
  String get allMemoriesPrivateResult => 'Sve uspomene su sada privatne';

  @override
  String get allMemoriesPublicResult => 'Sve uspomene su sada javne';

  @override
  String get newMemory => '✨ Nova uspomena';

  @override
  String get editMemory => '✏️ Izmeni uspomenu';

  @override
  String get memoryContentHint => 'Volim da jedem sladoled...';

  @override
  String get failedToSaveMemory => 'Nije uspelo čuvanje. Molimo proverite vašu konekciju.';

  @override
  String get saveMemory => 'Sačuvaj uspomenu';

  @override
  String get retry => 'Pokušajte ponovo';

  @override
  String get createActionItem => 'Kreiraj stavku za akciju';

  @override
  String get editActionItem => 'Izmeni stavku za akciju';

  @override
  String get actionItemDescriptionHint => 'Šta treba da se uradi?';

  @override
  String get actionItemDescriptionEmpty => 'Opis stavke za akciju ne sme biti prazan.';

  @override
  String get actionItemUpdated => 'Stavka za akciju je ažurirana';

  @override
  String get failedToUpdateActionItem => 'Nije uspelo ažuriranje stavke za akciju';

  @override
  String get actionItemCreated => 'Stavka za akciju je kreirana';

  @override
  String get failedToCreateActionItem => 'Nije uspelo pravljenje stavke za akciju';

  @override
  String get dueDate => 'Rok za završetak';

  @override
  String get time => 'Vreme';

  @override
  String get addDueDate => 'Dodaj rok';

  @override
  String get pressDoneToSave => 'Pritisnite gotovo da sačuvate';

  @override
  String get pressDoneToCreate => 'Pritisnite gotovo da kreirate';

  @override
  String get filterAll => 'Sve';

  @override
  String get filterSystem => 'O vama';

  @override
  String get filterInteresting => 'Uvidi';

  @override
  String get filterManual => 'Ručno';

  @override
  String get completed => 'Završeno';

  @override
  String get markComplete => 'Označi kao gotovo';

  @override
  String get actionItemDeleted => 'Stavka za akciju je obrisana';

  @override
  String get failedToDeleteActionItem => 'Nije uspelo brisanje stavke za akciju';

  @override
  String get deleteActionItemConfirmTitle => 'Obriši stavku za akciju';

  @override
  String get deleteActionItemConfirmMessage => 'Ste li sigurni da želite da obrišete ovu stavku za akciju?';

  @override
  String get appLanguage => 'Jezik aplikacije';

  @override
  String get appInterfaceSectionTitle => 'INTERFEJS APLIKACIJE';

  @override
  String get speechTranscriptionSectionTitle => 'GOVOR I TRANSKRIPCIJA';

  @override
  String get languageSettingsHelperText =>
      'Jezik aplikacije menja menije i dugmad. Jezik govora utiče na to kako se vaša snimanja transkribiraju.';

  @override
  String get translationNotice => 'Obaveštenje o prevodu';

  @override
  String get translationNoticeMessage =>
      'Omi prevodi razgovore na vašem primarnom jeziku. Ažurirajte ga bilo kada u Postavke → Profili.';

  @override
  String get pleaseCheckInternetConnection => 'Molimo proverite vašu internet konekciju i pokušajte ponovo';

  @override
  String get pleaseSelectReason => 'Molimo izaberite razlog';

  @override
  String get tellUsMoreWhatWentWrong => 'Recite nam više o šta je pošlo naopako...';

  @override
  String get selectText => 'Izaberite tekst';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimalno $count ciljeva je dozvoljeno';
  }

  @override
  String get conversationCannotBeMerged => 'Ovaj razgovor ne može biti spojen (zaključan ili već se spaja)';

  @override
  String get pleaseEnterFolderName => 'Molimo unesite naziv foldere';

  @override
  String get failedToCreateFolder => 'Nije uspelo pravljenje foldere';

  @override
  String get failedToUpdateFolder => 'Nije uspelo ažuriranje foldere';

  @override
  String get folderName => 'Naziv foldere';

  @override
  String get descriptionOptional => 'Opis (izbjegliv)';

  @override
  String get failedToDeleteFolder => 'Neuspješno brisanje mape';

  @override
  String get editFolder => 'Uredi mapu';

  @override
  String get deleteFolder => 'Obriši mapu';

  @override
  String get transcriptCopiedToClipboard => 'Transkripcija kopirana u clipboard';

  @override
  String get summaryCopiedToClipboard => 'Sažetak kopiran u clipboard';

  @override
  String get conversationUrlCouldNotBeShared => 'URL razgovora nije mogao biti podijeljen.';

  @override
  String get urlCopiedToClipboard => 'URL kopiran u clipboard';

  @override
  String get exportTranscript => 'Izvezi transkripciju';

  @override
  String get exportSummary => 'Izvezi sažetak';

  @override
  String get exportButton => 'Izvezi';

  @override
  String get actionItemsCopiedToClipboard => 'Elementi akcije kopirani u clipboard';

  @override
  String get summarize => 'Sumiraj';

  @override
  String get generateSummary => 'Generiši sažetak';

  @override
  String get conversationNotFoundOrDeleted => 'Razgovor nije pronađen ili je obrisan';

  @override
  String get deleteMemory => 'Obriši uspomenu';

  @override
  String get thisActionCannotBeUndone => 'Ova radnja se ne može opozvati.';

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
  String get noMemoriesInCategory => 'Nema uspomena u ovoj kategoriji';

  @override
  String get addYourFirstMemory => 'Dodaj svoju prvu uspomenu';

  @override
  String get firmwareDisconnectUsb => 'Iskopči USB';

  @override
  String get firmwareUsbWarning => 'USB veza tijekom ažuriranja može oštetiti tvoj uređaj.';

  @override
  String get firmwareBatteryAbove15 => 'Baterija iznad 15%';

  @override
  String get firmwareEnsureBattery => 'Provjeri da tvoj uređaj ima 15% baterije.';

  @override
  String get firmwareStableConnection => 'Stabilna veza';

  @override
  String get firmwareConnectWifi => 'Poveži se na WiFi ili mobilnu mrežu.';

  @override
  String failedToStartUpdate(String error) {
    return 'Neuspješan početak ažuriranja: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Prije ažuriranja, provjeri:';

  @override
  String get confirmed => 'Potvrđeno!';

  @override
  String get release => 'Objavi';

  @override
  String get slideToUpdate => 'Preskini za ažuriranje';

  @override
  String copiedToClipboard(String title) {
    return '$title kopiran u clipboard';
  }

  @override
  String get batteryLevel => 'Nivo baterije';

  @override
  String get charging => 'Punjenje';

  @override
  String get productUpdate => 'Ažuriranje proizvoda';

  @override
  String get offline => 'Offline';

  @override
  String get available => 'Dostupno';

  @override
  String get unpairDeviceDialogTitle => 'Ukloni sparivanje uređaja';

  @override
  String get unpairDeviceDialogMessage =>
      'Ovo će ukloniti sparivanje uređaja kako bi se mogao spojiti na drugi telefon. Trebat ćeš otići u Postavke > Bluetooth i zaboraviti uređaj da završiš proces.';

  @override
  String get unpair => 'Ukloni sparivanje';

  @override
  String get unpairAndForgetDevice => 'Ukloni sparivanje i zaboravi uređaj';

  @override
  String get unknownDevice => 'Nepoznat';

  @override
  String get unknown => 'Nepoznat';

  @override
  String get productName => 'Naziv proizvoda';

  @override
  String get serialNumber => 'Serijski broj';

  @override
  String get connected => 'Povezan';

  @override
  String get privacyPolicyTitle => 'Politika privatnosti';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label kopiran';
  }

  @override
  String get noApiKeysYet => 'Nema API ključeva';

  @override
  String get createKeyToGetStarted => 'Kreiraj ključ da počneš';

  @override
  String get configureSttProvider => 'Konfiguriši STT pružatelja';

  @override
  String get setWhenConversationsAutoEnd => 'Postavi kada se razgovori automatski završavaju';

  @override
  String get importDataFromOtherSources => 'Uvezi podatke iz drugih izvora';

  @override
  String get debugAndDiagnostics => 'Otklanjanje grešaka i dijagnostika';

  @override
  String get autoDeletesAfter3Days => 'Automatski briše nakon 3 dana.';

  @override
  String get helpsDiagnoseIssues => 'Pomaže u dijagnostici problema';

  @override
  String get exportStartedMessage => 'Izvoz počeo. Ovo može potrajati nekoliko sekundi...';

  @override
  String get exportConversationsToJson => 'Izvezi razgovore u JSON datoteku';

  @override
  String get knowledgeGraphDeletedSuccess => 'Grafikon znanja uspješno obrisan';

  @override
  String failedToDeleteGraph(String error) {
    return 'Neuspješno brisanje grafa: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Očisti sve čvorove i veze';

  @override
  String get addToClaudeDesktopConfig => 'Dodaj u claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Poveži AI asistente sa tvojim podacima';

  @override
  String get useYourMcpApiKey => 'Koristi svoj MCP API ključ';

  @override
  String get realTimeTranscript => 'Transkripcija u realnom vremenu';

  @override
  String get experimental => 'Eksperimentalno';

  @override
  String get transcriptionDiagnostics => 'Dijagnostika transkripcije';

  @override
  String get detailedDiagnosticMessages => 'Detaljne dijagnostičke poruke';

  @override
  String get autoCreateSpeakers => 'Automatski kreiraj govornike';

  @override
  String get autoCreateWhenNameDetected => 'Automatski kreiraj kada je ime detektovano';

  @override
  String get followUpQuestions => 'Praćenja pitanja';

  @override
  String get suggestQuestionsAfterConversations => 'Predloži pitanja nakon razgovora';

  @override
  String get goalTracker => 'Pratilac ciljeva';

  @override
  String get trackPersonalGoalsOnHomepage => 'Prati svoje lične ciljeve na početnoj stranici';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Opis elementa akcije ne može biti prazan';

  @override
  String get saved => 'Spremljeno';

  @override
  String get overdue => 'Prekoračen rok';

  @override
  String get failedToUpdateDueDate => 'Neuspješno ažuriranje roka';

  @override
  String get markIncomplete => 'Označi kao nepotpuno';

  @override
  String get editDueDate => 'Uredi rok';

  @override
  String get setDueDate => 'Postavi rok';

  @override
  String get clearDueDate => 'Obriši rok';

  @override
  String get failedToClearDueDate => 'Neuspješno brisanje roka';

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
  String get howDoesItWork => 'Kako funkcioniše?';

  @override
  String get sdCardSyncDescription => 'SD kartična sinhronizacija će uvesti tvoje uspomene sa SD kartice u aplikaciju';

  @override
  String get checksForAudioFiles => 'Provjerava audio datoteke na SD kartici';

  @override
  String get omiSyncsAudioFiles => 'Omi zatim sinhronizuje audio datoteke sa serverom';

  @override
  String get serverProcessesAudio => 'Server obrađuje audio datoteke i kreira uspomene';

  @override
  String get youreAllSet => 'Sve je spremno!';

  @override
  String get welcomeToOmiDescription =>
      'Dobrodošao u Omi! Tvoj AI asistent je spreman da ti pomogne sa razgovorima, zadacima i još mnogo toga.';

  @override
  String get startUsingOmi => 'Počni koristiti Omi';

  @override
  String get back => 'Nazad';

  @override
  String get keyboardShortcuts => 'Prečice na tipkovnici';

  @override
  String get toggleControlBar => 'Preuključi kontrolnu traku';

  @override
  String get pressKeys => 'Pritisni tipke...';

  @override
  String get cmdRequired => '⌘ obavezno';

  @override
  String get invalidKey => 'Nevažeći ključ';

  @override
  String get space => 'Razmak';

  @override
  String get search => 'Pretraga';

  @override
  String get searchPlaceholder => 'Pretraži...';

  @override
  String get untitledConversation => 'Razgovor bez naslova';

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
  String get goalTitle => 'Naslov cilja';

  @override
  String get current => 'Trenutni';

  @override
  String get target => 'Cilj';

  @override
  String get saveGoal => 'Spremi';

  @override
  String get goals => 'Ciljevi';

  @override
  String get tapToAddGoal => 'Dodirni za dodavanje cilja';

  @override
  String welcomeBack(String name) {
    return 'Dobrodošao nazad, $name';
  }

  @override
  String get yourConversations => 'Tvoji razgovori';

  @override
  String get reviewAndManageConversations => 'Pregledaj i upravljaj svojima uhvaćenim razgovorima';

  @override
  String get startCapturingConversations => 'Počni bilježenje razgovora sa Omi uređajem kako bi ih vidio ovdje.';

  @override
  String get useMobileAppToCapture => 'Koristi svoju mobilnu aplikaciju za bilježenje zvuka';

  @override
  String get conversationsProcessedAutomatically => 'Razgovori se obrađuju automatski';

  @override
  String get getInsightsInstantly => 'Dobij uvide i sažetke trenutno';

  @override
  String get showAll => 'Prikaži sve';

  @override
  String get noTasksForToday => 'Nema zadataka za danas.\nZatraži Omi za više zadataka ili kreiraj ručno.';

  @override
  String get dailyScore => 'DNEVNA OCJENA';

  @override
  String get dailyScoreDescription => 'Ocjena koja će ti pomoći da bolje\nuslijediš sa izvršavanjem.';

  @override
  String get searchResults => 'Rezultati pretrage';

  @override
  String get actionItems => 'Elementi akcije';

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
  String get swipeTasksToIndent => 'Preskini zadatke za indentaciju, vuči između kategorija';

  @override
  String get create => 'Kreiraj';

  @override
  String get noTasksYet => 'Nema zadataka';

  @override
  String get tasksFromConversationsWillAppear =>
      'Zadaci iz tvojih razgovora će se pojaviti ovdje.\nKlikni Kreiraj da dodaš jedan ručno.';

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
  String get monthAug => 'Aug';

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
  String get actionItemUpdatedSuccessfully => 'Element akcije uspješno ažuriran';

  @override
  String get actionItemCreatedSuccessfully => 'Element akcije uspješno kreiran';

  @override
  String get actionItemDeletedSuccessfully => 'Element akcije uspješno obrisan';

  @override
  String get deleteActionItem => 'Obriši element akcije';

  @override
  String get deleteActionItemConfirmation =>
      'Jesi li siguran da želiš obrisati ovaj element akcije? Ova radnja se ne može opozvati.';

  @override
  String get enterActionItemDescription => 'Uneesi opis elementa akcije...';

  @override
  String get markAsCompleted => 'Označi kao završeno';

  @override
  String get setDueDateAndTime => 'Postavi rok i vrijeme';

  @override
  String get reloadingApps => 'Ponovno učitavanje aplikacija...';

  @override
  String get loadingApps => 'Učitavanje aplikacija...';

  @override
  String get browseInstallCreateApps => 'Pregledi, instaliraj i kreiraj aplikacije';

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
  String get tryAdjustingSearchTermsOrFilters => 'Pokušaj prilagoditi svoje pojmove pretrage ili filtere';

  @override
  String get checkBackLaterForNewApps => 'Provjeri kasnije za nove aplikacije';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Molimo provjeri svoju internet vezu i pokušaj ponovno';

  @override
  String get createNewApp => 'Kreiraj novu aplikaciju';

  @override
  String get buildSubmitCustomOmiApp => 'Izgradi i pošalji svoju prilagođenu Omi aplikaciju';

  @override
  String get submittingYourApp => 'Slanje tvoje aplikacije...';

  @override
  String get preparingFormForYou => 'Priprema forme za tebe...';

  @override
  String get appDetails => 'Detalji aplikacije';

  @override
  String get paymentDetails => 'Detalji uplate';

  @override
  String get previewAndScreenshots => 'Pregled i snimci ekrana';

  @override
  String get appCapabilities => 'Mogućnosti aplikacije';

  @override
  String get aiPrompts => 'AI upiti';

  @override
  String get chatPrompt => 'Chat upit';

  @override
  String get chatPromptPlaceholder =>
      'Ti si odličan aplikacija, tvoj posao je odgovoriti na upite korisnika i učiniti da se osjećaju dobro...';

  @override
  String get conversationPrompt => 'Upit razgovora';

  @override
  String get conversationPromptPlaceholder => 'Ti si odličan aplikacija, dobićeš transkripciju i sažetak razgovora...';

  @override
  String get notificationScopes => 'Djelokruzi obavijesti';

  @override
  String get appPrivacyAndTerms => 'Privatnost i Uvjeti aplikacije';

  @override
  String get makeMyAppPublic => 'Učini mojem aplikacijom javnom';

  @override
  String get submitAppTermsAgreement =>
      'Slanjem ove aplikacije, slažem se sa Omi AI Uvjetima pružanja usluge i Politikom privatnosti';

  @override
  String get submitApp => 'Pošalji aplikaciju';

  @override
  String get needHelpGettingStarted => 'Trebam pomoć za početak?';

  @override
  String get clickHereForAppBuildingGuides => 'Klikni ovdje za vodiče i dokumentaciju za izgrađivanje aplikacija';

  @override
  String get submitAppQuestion => 'Pošalji aplikaciju?';

  @override
  String get submitAppPublicDescription =>
      'Tvoja aplikacija će biti pregledana i učinjena javnom. Možeš početi koristiti je odmah, čak i tijekom pregleda!';

  @override
  String get submitAppPrivateDescription =>
      'Tvoja aplikacija će biti pregledana i učinjena dostupnom tebi privatno. Možeš početi koristiti je odmah, čak i tijekom pregleda!';

  @override
  String get startEarning => 'Počni zarada! 💰';

  @override
  String get connectStripeOrPayPal => 'Poveži Stripe ili PayPal da primjaš uplate za svoju aplikaciju.';

  @override
  String get connectNow => 'Poveži se sada';

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
      'Ova aplikacija će pristupiti tvojim podacima. Omi AI nije odgovoran za kako se tvoji podaci koriste, mijenjaju ili brišu ovom aplikacijom';

  @override
  String get installApp => 'Instaliraj aplikaciju';

  @override
  String get betaTesterNotice =>
      'Ti si beta tester za ovu aplikaciju. Još nije javna. Bit će javna nakon što bude odobrena.';

  @override
  String get appUnderReviewOwner =>
      'Tvoja aplikacija se nalazi na pregledu i vidljiva je samo tebi. Bit će javna nakon što bude odobrena.';

  @override
  String get appRejectedNotice =>
      'Tvoja aplikacija je odbijena. Molimo ažuriraj detalje aplikacije i ponovno pošalji na pregled.';

  @override
  String get setupSteps => 'Koraci postavljanja';

  @override
  String get setupInstructions => 'Uputstva za postavljanje';

  @override
  String get integrationInstructions => 'Uputstva za integraciju';

  @override
  String get preview => 'Pregled';

  @override
  String get aboutTheApp => 'O aplikaciji';

  @override
  String get chatPersonality => 'Ličnost chata';

  @override
  String get ratingsAndReviews => 'Ocjene i recenzije';

  @override
  String get noRatings => 'nema ocjena';

  @override
  String ratingsCount(String count) {
    return '$count+ ocjena';
  }

  @override
  String get errorActivatingApp => 'Greška pri aktiviranju aplikacije';

  @override
  String get integrationSetupRequired => 'Ako je ovo aplikacija za integraciju, provjeri da je postavljanje završeno.';

  @override
  String get installed => 'Instaliran';

  @override
  String get appIdLabel => 'ID aplikacije';

  @override
  String get appNameLabel => 'Naziv aplikacije';

  @override
  String get appNamePlaceholder => 'Moja odličan aplikacija';

  @override
  String get pleaseEnterAppName => 'Molimo unesi naziv aplikacije';

  @override
  String get categoryLabel => 'Kategorija';

  @override
  String get selectCategory => 'Odaberi kategoriju';

  @override
  String get descriptionLabel => 'Opis';

  @override
  String get appDescriptionPlaceholder =>
      'Moja odličan aplikacija je odličan aplikacija koja radi nevjerojatne stvari. To je najbolja aplikacija ikad!';

  @override
  String get pleaseProvideValidDescription => 'Molimo pruži važeći opis';

  @override
  String get appPricingLabel => 'Cijenjenje aplikacije';

  @override
  String get noneSelected => 'Ništa nije odabrano';

  @override
  String get appIdCopiedToClipboard => 'ID aplikacije kopiran u clipboard';

  @override
  String get appCategoryModalTitle => 'Kategorija aplikacije';

  @override
  String get pricingFree => 'Besplatan';

  @override
  String get pricingPaid => 'Plaćen';

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
  String get rating4PlusStars => '4+ zvijezde';

  @override
  String get rating3PlusStars => '3+ zvijezde';

  @override
  String get rating2PlusStars => '2+ zvijezde';

  @override
  String get rating1PlusStars => '1+ zvijezde';

  @override
  String get filterRating => 'Ocjena';

  @override
  String get filterCapabilities => 'Mogućnosti';

  @override
  String get noNotificationScopesAvailable => 'Nema dostupnih djelokruga obavijesti';

  @override
  String get popularApps => 'Popularne aplikacije';

  @override
  String get pleaseProvidePrompt => 'Molimo pruži upit';

  @override
  String chatWithAppName(String appName) {
    return 'Razgovori sa $appName';
  }

  @override
  String get defaultAiAssistant => 'Zadani AI asistent';

  @override
  String get readyToChat => '✨ Spreman za razgovor!';

  @override
  String get connectionNeeded => '🌐 Veza je potrebna';

  @override
  String get startConversation => 'Počni razgovor i pusti magiju da počne';

  @override
  String get checkInternetConnection => 'Molimo provjeri svoju internet vezu';

  @override
  String get wasThisHelpful => 'Jeste li to smatrali korisnim?';

  @override
  String get thankYouForFeedback => 'Hvala vam na povratnoj informaciji!';

  @override
  String get maxFilesUploadError => 'Možeš učitati samo 4 datoteke odjednom';

  @override
  String get attachedFiles => '📎 Priložene datoteke';

  @override
  String get takePhoto => 'Snimi fotografiju';

  @override
  String get captureWithCamera => 'Uhvati sa kamerom';

  @override
  String get selectImages => 'Odaberi slike';

  @override
  String get chooseFromGallery => 'Odaberi iz galerije';

  @override
  String get selectFile => 'Odaberi datoteku';

  @override
  String get chooseAnyFileType => 'Odaberi bilo koju vrstu datoteke';

  @override
  String get cannotReportOwnMessages => 'Ne možeš prijaviti vlastite poruke';

  @override
  String get messageReportedSuccessfully => '✅ Poruka uspješno prijavljena';

  @override
  String get confirmReportMessage => 'Jesi li siguran da želiš prijaviti ovu poruku?';

  @override
  String get selectChatAssistant => 'Odaberi Chat asistenta';

  @override
  String get enableMoreApps => 'Omogući više aplikacija';

  @override
  String get chatCleared => 'Razgovor očišćen';

  @override
  String get clearChatTitle => 'Očisti razgovor?';

  @override
  String get confirmClearChat => 'Jesi li siguran da želiš očistiti razgovor? Ova radnja se ne može opozvati.';

  @override
  String get copy => 'Kopiraj';

  @override
  String get share => 'Dijeli';

  @override
  String get report => 'Prijavi';

  @override
  String get microphonePermissionRequired => 'Dozvola za mikrofon je potrebna za pozivanje';

  @override
  String get microphonePermissionDenied =>
      'Dozvola za mikrofon je odbijena. Molimo dozvoli dozvolu u Sistemskim postavkama > Privatnost i sigurnost > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Neuspješno provjeren dozvolu za mikrofon: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Neuspješna transkripcija zvuka';

  @override
  String get transcribing => 'Transkribovanje...';

  @override
  String get transcriptionFailed => 'Transkripcija neuspješna';

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
  String get hideTranscript => 'Sakrij transkripciju';

  @override
  String get viewTranscript => 'Pregledaj transkripciju';

  @override
  String get conversationDetails => 'Detalji razgovora';

  @override
  String get transcript => 'Transkripcija';

  @override
  String segmentsCount(int count) {
    return '$count segmenta';
  }

  @override
  String get noTranscriptAvailable => 'Nema dostupne transkripcije';

  @override
  String get noTranscriptMessage => 'Ovaj razgovor nema transkripcije.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL razgovora nije mogao biti generisan.';

  @override
  String get failedToGenerateConversationLink => 'Neuspješno generisanje veze razgovora';

  @override
  String get failedToGenerateShareLink => 'Neuspješno generisanje veze za dijeljenje';

  @override
  String get reloadingConversations => 'Ponovno učitavanje razgovora...';

  @override
  String get user => 'Korisnik';

  @override
  String get starred => 'Označeno zvjezdicom';

  @override
  String get date => 'Datum';

  @override
  String get noResultsFound => 'Nema pronađenih rezultata';

  @override
  String get tryAdjustingSearchTerms => 'Pokušaj prilagoditi svoje pojmove pretrage';

  @override
  String get starConversationsToFindQuickly => 'Označi razgovore zvjezdicom kako bi ih brzo pronašao ovdje';

  @override
  String noConversationsOnDate(String date) {
    return 'Nema razgovora na $date';
  }

  @override
  String get trySelectingDifferentDate => 'Pokušaj odabrati drugi datum';

  @override
  String get conversations => 'Razgovori';

  @override
  String get chat => 'Razgovor';

  @override
  String get actions => 'Akcije';

  @override
  String get syncAvailable => 'Sinhronizacija dostupna';

  @override
  String get referAFriend => 'Preporuči prijatelja';

  @override
  String get help => 'Pomoć';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Nadogradi na Pro';

  @override
  String get getOmiDevice => 'Nabavi Omi uređaj';

  @override
  String get wearableAiCompanion => 'Nosivi AI asistent';

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
  String get createYourFirstMemory => 'Kreiraj svoju prvu uspomenu da bi počeo';

  @override
  String get tryAdjustingFilter => 'Pokušaj prilagoditi svoju pretragu ili filtar';

  @override
  String get whatWouldYouLikeToRemember => 'Što bi htio zapamtiti?';

  @override
  String get category => 'Kategorija';

  @override
  String get public => 'Javno';

  @override
  String get failedToSaveCheckConnection => 'Neuspješno čuvanje. Molimo provjeri svoju vezu.';

  @override
  String get createMemory => 'Kreiraj uspomenu';

  @override
  String get deleteMemoryConfirmation =>
      'Jesi li siguran da želiš obrisati ovu uspomenu? Ova radnja se ne može opozvati.';

  @override
  String get makePrivate => 'Učini privatnom';

  @override
  String get organizeAndControlMemories => 'Organizuj i kontroliši svoje uspomene';

  @override
  String get total => 'Ukupno';

  @override
  String get makeAllMemoriesPrivate => 'Učini sve uspomene privatnim';

  @override
  String get setAllMemoriesToPrivate => 'Postavi sve uspomene na privatnu vidljivost';

  @override
  String get makeAllMemoriesPublic => 'Učini sve uspomene javnim';

  @override
  String get setAllMemoriesToPublic => 'Postavi sve uspomene na javnu vidljivost';

  @override
  String get permanentlyRemoveAllMemories => 'Trajno ukloni sve uspomene iz Omija';

  @override
  String get allMemoriesAreNowPrivate => 'Sve uspomene su sada privatne';

  @override
  String get allMemoriesAreNowPublic => 'Sve uspomene su sada javne';

  @override
  String get clearOmisMemory => 'Očisti Omijevu memoriju';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Jesi li siguran da želiš očistiti Omijevu memoriju? Ova radnja se ne može opozvati i trajno će obrisati sve $count uspomena.';
  }

  @override
  String get omisMemoryCleared => 'Omijeva memorija o tebi je očišćena';

  @override
  String get welcomeToOmi => 'Dobrodošao u Omi';

  @override
  String get continueWithApple => 'Nastavi sa Apple';

  @override
  String get continueWithGoogle => 'Nastavi s Google-om';

  @override
  String get byContinuingYouAgree => 'Nastavljanjem se slažeš s našim ';

  @override
  String get termsOfService => 'Uvjetima pružanja usluge';

  @override
  String get and => ' i ';

  @override
  String get dataAndPrivacy => 'Podatke i privatnost';

  @override
  String get secureAuthViaAppleId => 'Sigurna autentifikacija putem Apple ID-a';

  @override
  String get secureAuthViaGoogleAccount => 'Sigurna autentifikacija putem Google računa';

  @override
  String get whatWeCollect => 'Što prikupljamo';

  @override
  String get dataCollectionMessage =>
      'Nastavljanjem, tvoje razgovore, snimke i osobne podatke sigurno ćemo pohraniti na naše poslužitelje kako bi pružili AI-pogonske uvide i omogućili sve značajke aplikacije.';

  @override
  String get dataProtection => 'Zaštita podataka';

  @override
  String get yourDataIsProtected => 'Tvoji su podaci zaštićeni i vođeni našim ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Molimo odaberi svoj primarni jezik';

  @override
  String get chooseYourLanguage => 'Odaberi svoj jezik';

  @override
  String get selectPreferredLanguageForBestExperience => 'Odaberi svoj omiljeni jezik za najbolje Omi iskustvo';

  @override
  String get searchLanguages => 'Pretraži jezike...';

  @override
  String get selectALanguage => 'Odaberi jezik';

  @override
  String get tryDifferentSearchTerm => 'Pokušaj s drugim izrazom za pretragu';

  @override
  String get pleaseEnterYourName => 'Molimo unesi svoje ime';

  @override
  String get nameMustBeAtLeast2Characters => 'Ime mora sadržavati najmanje 2 znaka';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Reci nam kako bi se htio obraćati. To pomaže personalizirati tvoje Omi iskustvo.';

  @override
  String charactersCount(int count) {
    return '$count znakova';
  }

  @override
  String get enableFeaturesForBestExperience => 'Aktiviraj značajke za najbolje Omi iskustvo na svom uređaju.';

  @override
  String get microphoneAccess => 'Pristup mikrofonu';

  @override
  String get recordAudioConversations => 'Snimi audio razgovore';

  @override
  String get microphoneAccessDescription =>
      'Omi trebam pristup mikrofonu kako bi snimi tvoje razgovore i pružio transkripcije.';

  @override
  String get screenRecording => 'Snimanje zaslonom';

  @override
  String get captureSystemAudioFromMeetings => 'Snimaj sistemski audio sa sastanaka';

  @override
  String get screenRecordingDescription =>
      'Omi trebam dozvolu za snimanje zaslona kako bi snimio sistemski audio s tvojih web-sastanaka.';

  @override
  String get accessibility => 'Dostupnost';

  @override
  String get detectBrowserBasedMeetings => 'Otkrij web-sastanke';

  @override
  String get accessibilityDescription =>
      'Omi trebam dozvolu dostupnosti kako bi otkrio kad se priključiš Zoom, Meet ili Teams sastancima u svom pregledniku.';

  @override
  String get pleaseWait => 'Molimo čekaj...';

  @override
  String get joinTheCommunity => 'Pridruži se zajednici!';

  @override
  String get loadingProfile => 'Učitavanje profila...';

  @override
  String get profileSettings => 'Postavke profila';

  @override
  String get noEmailSet => 'Nema postavljene e-pošte';

  @override
  String get userIdCopiedToClipboard => 'ID korisnika kopiran u clipboard';

  @override
  String get yourInformation => 'Tvoje podatke';

  @override
  String get setYourName => 'Postavi svoje ime';

  @override
  String get changeYourName => 'Promijeni svoje ime';

  @override
  String get voiceAndPeople => 'Glas i ljudi';

  @override
  String get teachOmiYourVoice => 'Nauči Omi svoj glas';

  @override
  String get tellOmiWhoSaidIt => 'Reci Omi tko je to rekao 🗣️';

  @override
  String get payment => 'Plaćanje';

  @override
  String get addOrChangeYourPaymentMethod => 'Dodaj ili promijeni način plaćanja';

  @override
  String get preferences => 'Postavke';

  @override
  String get helpImproveOmiBySharing => 'Pomozi poboljšati Omi dijeljenjem anonimiziranih podataka analitike';

  @override
  String get deleteAccount => 'Obriši račun';

  @override
  String get deleteYourAccountAndAllData => 'Obriši svoj račun i sve podatke';

  @override
  String get clearLogs => 'Očisti dnevnike';

  @override
  String get debugLogsCleared => 'Dnevnici ispravljanja su očišćeni';

  @override
  String get exportConversations => 'Izvezi razgovore';

  @override
  String get exportAllConversationsToJson => 'Izvezi sve svoje razgovore u JSON datoteku.';

  @override
  String get conversationsExportStarted =>
      'Izvoz razgovora je započeo. Ovo može potrajati nekoliko sekundi, molimo čekaj.';

  @override
  String get mcpDescription =>
      'Kako bi povezao Omi s drugim aplikacijama za čitanje, pretragu i upravljanje tvojim uspomenama i razgovorima. Stvori ključ kako bi započeo.';

  @override
  String get apiKeys => 'API ključevi';

  @override
  String errorLabel(String error) {
    return 'Greška: $error';
  }

  @override
  String get noApiKeysFound => 'Nema pronađenih API ključeva. Stvori jedan kako bi započeo.';

  @override
  String get advancedSettings => 'Napredne postavke';

  @override
  String get triggersWhenNewConversationCreated => 'Pokreće se kada je stvoren novi razgovor.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Pokreće se kada je primljena nova transkripcija.';

  @override
  String get realtimeAudioBytes => 'Bajtovi zvuka u realnom vremenu';

  @override
  String get triggersWhenAudioBytesReceived => 'Pokreće se kada su primljeni bajtovi zvuka.';

  @override
  String get everyXSeconds => 'Svakih x sekundi';

  @override
  String get triggersWhenDaySummaryGenerated => 'Pokreće se kada je generiran sažetak dana.';

  @override
  String get tryLatestExperimentalFeatures => 'Pokušaj najnovije eksperimentalne značajke od Omi tima.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Status dijagnostike servisa transkripcije';

  @override
  String get enableDetailedDiagnosticMessages => 'Aktiviraj detaljne dijagnostičke poruke iz servisa transkripcije';

  @override
  String get autoCreateAndTagNewSpeakers => 'Automatski stvori i označi nove govornike';

  @override
  String get automaticallyCreateNewPerson => 'Automatski stvori novu osobu kada je ime detektirano u transkripciji.';

  @override
  String get pilotFeatures => 'Pilot karakteristike';

  @override
  String get pilotFeaturesDescription => 'Ove su karakteristike testovi i nema jamstva za podršku.';

  @override
  String get suggestFollowUpQuestion => 'Predloži pitanje praćenja';

  @override
  String get saveSettings => 'Spremi postavke';

  @override
  String get syncingDeveloperSettings => 'Sinkroniziranje postavki razvojnog programera...';

  @override
  String get summary => 'Sažetak';

  @override
  String get auto => 'Automatski';

  @override
  String get noSummaryForApp =>
      'Nema dostupnog sažetka za ovu aplikaciju. Pokušaj s drugom aplikacijom za bolje rezultate.';

  @override
  String get tryAnotherApp => 'Pokušaj drugu aplikaciju';

  @override
  String generatedBy(String appName) {
    return 'Generirano od strane $appName';
  }

  @override
  String get overview => 'Pregled';

  @override
  String get otherAppResults => 'Rezultati drugih aplikacija';

  @override
  String get unknownApp => 'Nepoznata aplikacija';

  @override
  String get noSummaryAvailable => 'Nema dostupnog sažetka';

  @override
  String get conversationNoSummaryYet => 'Ovaj razgovor nema sažetka.';

  @override
  String get chooseSummarizationApp => 'Odaberi aplikaciju za sumarizaciju';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName je postavljena kao zadana aplikacija za sumarizaciju';
  }

  @override
  String get letOmiChooseAutomatically => 'Pusti Omi da automatski odabere najbolju aplikaciju';

  @override
  String get deleteConversationConfirmation =>
      'Jesi li siguran da želiš obrisati ovaj razgovor? Ova se akcija ne može poništiti.';

  @override
  String get conversationDeleted => 'Razgovor je obrisan';

  @override
  String get generatingLink => 'Generiranje veze...';

  @override
  String get editConversation => 'Uredi razgovor';

  @override
  String get conversationLinkCopiedToClipboard => 'Veza razgovora je kopirana u clipboard';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transkripcija razgovora je kopirana u clipboard';

  @override
  String get editConversationDialogTitle => 'Uredi razgovor';

  @override
  String get changeTheConversationTitle => 'Promijeni naslov razgovora';

  @override
  String get conversationTitle => 'Naslov razgovora';

  @override
  String get enterConversationTitle => 'Unesi naslov razgovora...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Naslov razgovora je uspješno ažuriran';

  @override
  String get failedToUpdateConversationTitle => 'Ažuriranje naslova razgovora nije uspjelo';

  @override
  String get errorUpdatingConversationTitle => 'Greška pri ažuriranju naslova razgovora';

  @override
  String get settingUp => 'Postavljanje...';

  @override
  String get startYourFirstRecording => 'Započni svojom prvom snimkom';

  @override
  String get preparingSystemAudioCapture => 'Priprema snimanja sistemskog zvuka';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klikni gumb da snimiš zvuk za direktnu transkripcionu, AI uvide i automatsko spremanje.';

  @override
  String get reconnecting => 'Ponovno se povezujem...';

  @override
  String get recordingPaused => 'Snimanje je pauznirano';

  @override
  String get recordingActive => 'Snimanje je aktivno';

  @override
  String get startRecording => 'Započni snimanje';

  @override
  String resumingInCountdown(String countdown) {
    return 'Nastavljam za ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Dodirni play da nastaviš';

  @override
  String get listeningForAudio => 'Slušanje zvuka...';

  @override
  String get preparingAudioCapture => 'Priprema snimanja zvuka';

  @override
  String get clickToBeginRecording => 'Klikni da bi započeo snimanje';

  @override
  String get translated => 'prevedeno';

  @override
  String get liveTranscript => 'Direktna transkripcija';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenti';
  }

  @override
  String get startRecordingToSeeTranscript => 'Započni snimanje da vidiš direktnu transkripciju';

  @override
  String get paused => 'Pauznirano';

  @override
  String get initializing => 'Inicijalizacija...';

  @override
  String get recording => 'Snimanje';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon se promijenio. Nastavljam za ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Klikni play da nastaviš ili stop da završiš';

  @override
  String get settingUpSystemAudioCapture => 'Postavljanje snimanja sistemskog zvuka';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Snimanje zvuka i generiranje transkripcije';

  @override
  String get clickToBeginRecordingSystemAudio => 'Klikni da bi započeo snimanje sistemskog zvuka';

  @override
  String get you => 'Ti';

  @override
  String speakerWithId(String speakerId) {
    return 'Govornik $speakerId';
  }

  @override
  String get translatedByOmi => 'prevedeno od strane omi';

  @override
  String get backToConversations => 'Natrag na razgovore';

  @override
  String get systemAudio => 'Sustav';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Ulaz zvuka je postavljen na $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Greška pri prebacivanju audio uređaja: $error';
  }

  @override
  String get selectAudioInput => 'Odaberi ulaz zvuka';

  @override
  String get loadingDevices => 'Učitavanje uređaja...';

  @override
  String get settingsHeader => 'POSTAVKE';

  @override
  String get plansAndBilling => 'Planovi i naplatа';

  @override
  String get calendarIntegration => 'Integracija kalendarija';

  @override
  String get dailySummary => 'Dnevni sažetak';

  @override
  String get developer => 'Razvojni programer';

  @override
  String get about => 'O nama';

  @override
  String get selectTime => 'Odaberi vrijeme';

  @override
  String get accountGroup => 'Račun';

  @override
  String get signOutQuestion => 'Odjava?';

  @override
  String get signOutConfirmation => 'Jesi li siguran da se želiš odjaviti?';

  @override
  String get customVocabularyHeader => 'PRILAGOĐENI VOKABULAR';

  @override
  String get addWordsDescription => 'Dodaj riječi koje Omi trebam prepoznati tijekom transkripcije.';

  @override
  String get enterWordsHint => 'Unesi riječi (odvojeno zarezom)';

  @override
  String get dailySummaryHeader => 'DNEVNI SAŽETAK';

  @override
  String get dailySummaryTitle => 'Dnevni sažetak';

  @override
  String get dailySummaryDescription => 'Obavijesti s personaliziranim sažetkom razgovora tijekom dana.';

  @override
  String get deliveryTime => 'Vrijeme dostave';

  @override
  String get deliveryTimeDescription => 'Kada primiti tvoj dnevni sažetak';

  @override
  String get subscription => 'Pretplata';

  @override
  String get viewPlansAndUsage => 'Prikaži planove i korištenje';

  @override
  String get viewPlansDescription => 'Upravljaj svojom pretplatom i vidi statistiku korištenja';

  @override
  String get addOrChangePaymentMethod => 'Dodaj ili promijeni način plaćanja';

  @override
  String get displayOptions => 'Mogućnosti prikaza';

  @override
  String get showMeetingsInMenuBar => 'Prikaži sastanke u alatnoj traci';

  @override
  String get displayUpcomingMeetingsDescription => 'Prikaži nadolazeće sastanke u alatnoj traci';

  @override
  String get showEventsWithoutParticipants => 'Prikaži događaje bez sudionika';

  @override
  String get includePersonalEventsDescription => 'Uključi osobne događaje bez prisutnih';

  @override
  String get upcomingMeetings => 'Nadolazeći sastanci';

  @override
  String get checkingNext7Days => 'Provjera sljedećih 7 dana';

  @override
  String get shortcuts => 'Prečaci';

  @override
  String get shortcutChangeInstruction => 'Klikni na prečac da ga promijeniš. Pritisni Escape da otkazes.';

  @override
  String get configureSTTProvider => 'Konfiguriraj pružatelja STT-a';

  @override
  String get setConversationEndDescription => 'Postavi kada se razgovori automatski završavaju';

  @override
  String get importDataDescription => 'Uvezi podatke iz drugih izvora';

  @override
  String get exportConversationsDescription => 'Izvezi razgovore u JSON';

  @override
  String get exportingConversations => 'Izvoz razgovora...';

  @override
  String get clearNodesDescription => 'Očisti sve čvorove i veze';

  @override
  String get deleteKnowledgeGraphQuestion => 'Obriši graf znanja?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'Ovo će obrisati sve izvedene podatke grafa znanja. Tvoje originalne uspomene ostaju sigurne.';

  @override
  String get connectOmiWithAI => 'Poveži Omi s AI asistentima';

  @override
  String get noAPIKeys => 'Nema API ključeva. Stvori jedan kako bi započeo.';

  @override
  String get autoCreateWhenDetected => 'Automatski stvori kada je ime detektirano';

  @override
  String get trackPersonalGoals => 'Prati osobne ciljeve na početnoj stranici';

  @override
  String get endpointURL => 'URL krajnje točke';

  @override
  String get links => 'Veze';

  @override
  String get discordMemberCount => '8000+ članova na Discordu';

  @override
  String get userInformation => 'Korisnički podaci';

  @override
  String get capabilities => 'Mogućnosti';

  @override
  String get previewScreenshots => 'Pregled snimaka zaslona';

  @override
  String get holdOnPreparingForm => 'Čekaj, pripremamo obrazac za tebe';

  @override
  String get bySubmittingYouAgreeToOmi => 'Slanjem se slažeš s Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Uvjetima i politikom privatnosti';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Pomaže u dijagnostici problema. Automatski se briše nakon 3 dana.';

  @override
  String get manageYourApp => 'Upravljaj svojom aplikacijom';

  @override
  String get updatingYourApp => 'Ažuriranje tvoje aplikacije';

  @override
  String get fetchingYourAppDetails => 'Dohvat tvoje aplikacije detalje';

  @override
  String get updateAppQuestion => 'Ažurirati aplikaciju?';

  @override
  String get updateAppConfirmation =>
      'Jesi li siguran da želiš ažurirati svoju aplikaciju? Promjene će se odraziti kada ih odobri naš tim.';

  @override
  String get updateApp => 'Ažurira aplikaciju';

  @override
  String get createAndSubmitNewApp => 'Stvori i podnesi novu aplikaciju';

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
  String get newVersionAvailable => 'Nova verzija je dostupna 🎉';

  @override
  String get no => 'Ne';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Pretplata je uspješno otkazana. Ostaće aktivna do kraja trenutnog razdoblja naplate.';

  @override
  String get failedToCancelSubscription => 'Otkazivanje pretplate nije uspjelo. Molimo pokušaj ponovno.';

  @override
  String get invalidPaymentUrl => 'Nevaljani URL plaćanja';

  @override
  String get permissionsAndTriggers => 'Dozvole i okidači';

  @override
  String get chatFeatures => 'Svojstva razgovora';

  @override
  String get uninstall => 'Ukloniti';

  @override
  String get installs => 'INSTALACIJE';

  @override
  String get priceLabel => 'CIJENA';

  @override
  String get updatedLabel => 'AŽURIRANO';

  @override
  String get createdLabel => 'STVORENO';

  @override
  String get featuredLabel => 'ISTAKNUTO';

  @override
  String get cancelSubscriptionQuestion => 'Otkazati pretplatu?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Jesi li siguran da želiš otkazati svoju pretplatu? Nastavit ćeš imati pristup do kraja svog trenutnog razdoblja naplate.';

  @override
  String get cancelSubscriptionButton => 'Otkaži pretplatu';

  @override
  String get cancelling => 'Otkazivanje...';

  @override
  String get betaTesterMessage => 'Jesi beta tester za ovu aplikaciju. Još nije javna. Biti će javna kada se odobri.';

  @override
  String get appUnderReviewMessage =>
      'Tvoja aplikacija je u tijeku pregleda i vidljiva samo tebi. Biti će javna kada se odobri.';

  @override
  String get appRejectedMessage =>
      'Tvoja aplikacija je odbijena. Molimo ažuriraj detalje aplikacije i ponovno je podnesi na pregled.';

  @override
  String get invalidIntegrationUrl => 'Nevaljani URL integracije';

  @override
  String get tapToComplete => 'Dodirni za dovršetak';

  @override
  String get invalidSetupInstructionsUrl => 'Nevaljani URL uputa za postavljanje';

  @override
  String get pushToTalk => 'Pritisni za razgovor';

  @override
  String get summaryPrompt => 'Uputa za sažetak';

  @override
  String get pleaseSelectARating => 'Molimo odaberi procjenu';

  @override
  String get reviewAddedSuccessfully => 'Recenzija je uspješno dodana 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Recenzija je uspješno ažurirana 🚀';

  @override
  String get failedToSubmitReview => 'Slanje recenzije nije uspjelo. Molimo pokušaj ponovno.';

  @override
  String get addYourReview => 'Dodaj svoju recenziju';

  @override
  String get editYourReview => 'Uredi svoju recenziju';

  @override
  String get writeAReviewOptional => 'Napiši recenziju (opcionalno)';

  @override
  String get submitReview => 'Podnesi recenziju';

  @override
  String get updateReview => 'Ažurira recenziju';

  @override
  String get yourReview => 'Tvoja recenzija';

  @override
  String get anonymousUser => 'Anonimni korisnik';

  @override
  String get issueActivatingApp => 'Došlo je do problema pri aktiviranju ove aplikacije. Molimo pokušaj ponovno.';

  @override
  String get dataAccessNoticeDescription =>
      'Ova aplikacija će pristupiti tvojim podacima. Omi AI nije odgovorna za način na koji ova aplikacija koristi, mijenja ili briše tvoje podatke';

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
    return 'Integracija $serviceName uskoro';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Već izvezeno na $platform';
  }

  @override
  String get anotherPlatform => 'drugu platformu';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Molimo autentificiraj se s $serviceName u Postavke > Integracije zadataka';
  }

  @override
  String addingToService(String serviceName) {
    return 'Dodavanje na $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Dodano na $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Dodavanje na $serviceName nije uspjelo';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Dozvola odbijena za Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Stvaranje API ključa pružatelja nije uspjelo: $error';
  }

  @override
  String get createAKey => 'Stvori ključ';

  @override
  String get apiKeyRevokedSuccessfully => 'API ključ je uspješno opozvan';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Opozivanje API ključa nije uspjelo: $error';
  }

  @override
  String get omiApiKeys => 'Omi API ključevi';

  @override
  String get apiKeysDescription =>
      'API ključevi se koriste za autentifikaciju kada se tvoja aplikacija komunicira s OMI poslužiteljem. Omogućuju tvojoj aplikaciji sigurno stvaranje uspomena i pristup ostalim OMI uslugama.';

  @override
  String get aboutOmiApiKeys => 'O Omi API ključevima';

  @override
  String get yourNewKey => 'Tvoj novi ključ:';

  @override
  String get copyToClipboard => 'Kopira u clipboard';

  @override
  String get pleaseCopyKeyNow => 'Molimo kopira ga sada i zapiši ga negdje sigurno. ';

  @override
  String get willNotSeeAgain => 'Nećeš ga moći vidjeti ponovno.';

  @override
  String get revokeKey => 'Opozovi ključ';

  @override
  String get revokeApiKeyQuestion => 'Opozovi API ključ?';

  @override
  String get revokeApiKeyWarning =>
      'Ova se akcija ne može poništiti. Sve aplikacije koje koriste ovaj ključ neće više moći pristupiti API-ju.';

  @override
  String get revoke => 'Opozovi';

  @override
  String get whatWouldYouLikeToCreate => 'Što bi se htio stvoriti?';

  @override
  String get createAnApp => 'Stvori aplikaciju';

  @override
  String get createAndShareYourApp => 'Stvori i podijeli svoju aplikaciju';

  @override
  String get itemApp => 'Aplikacija';

  @override
  String keepItemPublic(String item) {
    return 'Čuvaj $item javnim';
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
    return 'Ako učiniš $item javnim, može ga koristiti svaki';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Ako učiniš $item privatnim sada, prestati će raditi za sve i biti će vidljiv samo tebi';
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
    return 'Jesi li siguran da želiš obrisati ovaj $item? Ova se akcija ne može poništiti.';
  }

  @override
  String get revokeKeyQuestion => 'Opozovi ključ?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Jesi li siguran da želiš opozva ključ \"$keyName\"? Ova se akcija ne može poništiti.';
  }

  @override
  String get createNewKey => 'Stvori novi ključ';

  @override
  String get keyNameHint => 'npr. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Molimo unesi ime.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Stvaranje ključa nije uspjelo: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Stvaranje ključa nije uspjelo. Molimo pokušaj ponovno.';

  @override
  String get keyCreated => 'Ključ je stvoren';

  @override
  String get keyCreatedMessage => 'Tvoj novi ključ je stvoren. Molimo kopira ga sada. Nećeš ga moći vidjeti ponovno.';

  @override
  String get keyWord => 'Ključ';

  @override
  String get externalAppAccess => 'Pristup vanjske aplikacije';

  @override
  String get externalAppAccessDescription =>
      'Slijedeće instalirane aplikacije imaju vanjske integracije i mogu pristupiti tvojim podacima, kao što su razgovori i uspomene.';

  @override
  String get noExternalAppsHaveAccess => 'Nema vanjskih aplikacija koje imaju pristup tvojim podacima.';

  @override
  String get maximumSecurityE2ee => 'Maksimalna sigurnost (E2EE)';

  @override
  String get e2eeDescription =>
      'End-to-end enkripcija je zlatni standard za privatnost. Kada je aktivirana, tvoji su podaci šifrirani na svom uređaju prije nego što se pošalju našim poslužiteljima. To znači da nitko, čak ni Omi, ne može pristupiti tvojoj sadržaju.';

  @override
  String get importantTradeoffs => 'Važni kompromisi:';

  @override
  String get e2eeTradeoff1 => '• Neke značajke kao što su integracije vanjske aplikacije mogu biti onemogućene.';

  @override
  String get e2eeTradeoff2 => '• Ako zaboraviš lozinku, tvoji podaci se ne mogu oporaviti.';

  @override
  String get featureComingSoon => 'Ova će se značajka uskoro pojaviti!';

  @override
  String get migrationInProgressMessage =>
      'Migracija je u tijeku. Ne možeš promijeniti razinu zaštite dok se ne dovrši.';

  @override
  String get migrationFailed => 'Migracija nije uspjela';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migracija s $source na $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objekata';
  }

  @override
  String get secureEncryption => 'Sigurna enkripcija';

  @override
  String get secureEncryptionDescription =>
      'Tvoji su podaci šifrirani s ključem jedinstvenim za tebe na našim poslužiteljima, hostiranom na Google Cloud-u. To znači da je tvoj sirovi sadržaj nedostupan bilo kome, uključujući Omi personale ili Google, izravno iz baze podataka.';

  @override
  String get endToEndEncryption => 'End-to-End enkripcija';

  @override
  String get e2eeCardDescription =>
      'Aktivira za maksimalnu sigurnost gdje samo ti možeš pristupiti tvojim podacima. Dodirni kako bi saznao više.';

  @override
  String get dataAlwaysEncrypted => 'Bez obzira na razinu, tvoji su podaci uvijek šifrirani u mirovanju i u prijenosu.';

  @override
  String get readOnlyScope => 'Samo čitanje';

  @override
  String get fullAccessScope => 'Potpun pristup';

  @override
  String get readScope => 'Čitaj';

  @override
  String get writeScope => 'Napiši';

  @override
  String get apiKeyCreated => 'API ključ je stvoren!';

  @override
  String get saveKeyWarning => 'Spremi ovaj ključ sada! Nećeš ga moći vidjeti ponovno.';

  @override
  String get yourApiKey => 'TVOJ API KLJUČ';

  @override
  String get tapToCopy => 'Dodirni za kopiranje';

  @override
  String get copyKey => 'Kopira ključ';

  @override
  String get createApiKey => 'Stvori API ključ';

  @override
  String get accessDataProgrammatically => 'Pristupi tvojim podacima programski';

  @override
  String get keyNameLabel => 'IME KLJUČA';

  @override
  String get keyNamePlaceholder => 'npr. Moja integracija aplikacije';

  @override
  String get permissionsLabel => 'DOZVOLE';

  @override
  String get permissionsInfoNote => 'R = Čitaj, W = Napiši. Zadano je samo čitanje ako ništa nije odabrano.';

  @override
  String get developerApi => 'API za razvojne programere';

  @override
  String get createAKeyToGetStarted => 'Stvori ključ kako bi započeo';

  @override
  String errorWithMessage(String error) {
    return 'Greška: $error';
  }

  @override
  String get omiTraining => 'Omi obuka';

  @override
  String get trainingDataProgram => 'Program podataka za obuku';

  @override
  String get getOmiUnlimitedFree =>
      'Dobij Omi Unlimited besplatno doprinošenjem svojih podataka za treniranje AI modela.';

  @override
  String get trainingDataBullets =>
      '• Tvoji podaci pomažu poboljšati AI modele\n• Samo ne-osjetljivi podaci se dijele\n• Potpuno transparentan proces';

  @override
  String get learnMoreAtOmiTraining => 'Saznaj više na omi.me/training';

  @override
  String get agreeToContributeData => 'Razumijem i slažem se doprinijeti svoje podatke za obuku AI';

  @override
  String get submitRequest => 'Podnesi zahtjev';

  @override
  String get thankYouRequestUnderReview =>
      'Hvala! Tvoj zahtjev je u tijeku pregleda. Obavijestit ćemo te kada se odobri.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Tvoj će plan ostati aktivna do $date. Nakon toga ćeš izgubiti pristup svojima neograničenim značajkama. Jesi li siguran?';
  }

  @override
  String get confirmCancellation => 'Potvrdi otkazivanje';

  @override
  String get keepMyPlan => 'Čuvi moj plan';

  @override
  String get subscriptionSetToCancel => 'Tvoja pretplata je postavljena na otkazivanje na kraju razdoblja.';

  @override
  String get switchedToOnDevice => 'Prebačeno na transkripciju na uređaju';

  @override
  String get couldNotSwitchToFreePlan => 'Nije moguće prijeći na besplatni plan. Molimo pokušajte ponovno.';

  @override
  String get couldNotLoadPlans => 'Nije moguće učitati dostupne planove. Molimo pokušajte ponovno.';

  @override
  String get selectedPlanNotAvailable => 'Odabrani plan nije dostupan. Molimo pokušajte ponovno.';

  @override
  String get upgradeToAnnualPlan => 'Nadogradnja na godišnji plan';

  @override
  String get importantBillingInfo => 'Važne informacije o naplati:';

  @override
  String get monthlyPlanContinues => 'Vaš trenutni mjesečni plan će nastaviti do kraja vašeg perioda naplate';

  @override
  String get paymentMethodCharged =>
      'Vaša postojeća metoda plaćanja će biti naplaćena automatski kada se vaš mjesečni plan završi';

  @override
  String get annualSubscriptionStarts =>
      'Vaša godišnja pretplata od 12 mjeseci će se pokrenuti automatski nakon naplate';

  @override
  String get thirteenMonthsCoverage => 'Dobit ćete 13 mjeseci pokrića ukupno (trenutni mjesec + 12 mjeseci godišnjeg)';

  @override
  String get confirmUpgrade => 'Potvrdi nadogradnju';

  @override
  String get confirmPlanChange => 'Potvrdi promjenu plana';

  @override
  String get confirmAndProceed => 'Potvrdi i nastavi';

  @override
  String get upgradeScheduled => 'Nadogradnja je zakazana';

  @override
  String get changePlan => 'Promijeni plan';

  @override
  String get upgradeAlreadyScheduled => 'Vaša nadogradnja na godišnji plan je već zakazana';

  @override
  String get youAreOnUnlimitedPlan => 'Vi ste na Neograničenom planu.';

  @override
  String get yourOmiUnleashed => 'Vaš Omi, oslobođen. Idite na neograničeno za beskonačne mogućnosti.';

  @override
  String planEndedOn(String date) {
    return 'Vaš plan je završio $date.\\nPonovno se pretplatite sada - bit ćete odmah naplaćeni za novi period naplate.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Vaš plan je postavljen da se otkaže $date.\\nPonovno se pretplatite sada da zadržite svoje benefite - nema naknade do $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Vaš godišnji plan će se pokrenuti automatski kada se vaš mjesečni plan završi.';

  @override
  String planRenewsOn(String date) {
    return 'Vaš plan se obnavlja $date.';
  }

  @override
  String get unlimitedConversations => 'Neograničeni razgovori';

  @override
  String get askOmiAnything => 'Pitajte Omija bilo što o svojoj životu';

  @override
  String get unlockOmiInfiniteMemory => 'Otključajte Omijevu beskonačnu memoriju';

  @override
  String get youreOnAnnualPlan => 'Vi ste na godišnjem planu';

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
  String get resubscribe => 'Ponovna pretplata';

  @override
  String get couldNotOpenPaymentSettings => 'Nije moguće otvoriti postavke plaćanja. Molimo pokušajte ponovno.';

  @override
  String get managePaymentMethod => 'Upravljaj metodom plaćanja';

  @override
  String get cancelSubscription => 'Otkaži pretplatu';

  @override
  String endsOnDate(String date) {
    return 'Završava se $date';
  }

  @override
  String get active => 'Aktivno';

  @override
  String get freePlan => 'Besplatni plan';

  @override
  String get configure => 'Konfiguriraj';

  @override
  String get privacyInformation => 'Informacije o privatnosti';

  @override
  String get yourPrivacyMattersToUs => 'Vaša privatnost nam je važna';

  @override
  String get privacyIntroText =>
      'U Omiju shvaćamo vašu privatnost vrlo ozbiljno. Želimo biti transparentni o podacima koje prikupljamo i kako ih koristimo da poboljšamo naš proizvod za vas. Evo što trebate znati:';

  @override
  String get whatWeTrack => 'Što pratimo';

  @override
  String get anonymityAndPrivacy => 'Anonimnost i privatnost';

  @override
  String get optInAndOptOutOptions => 'Mogućnosti pristanka i odustajanja';

  @override
  String get ourCommitment => 'Naš zahtjev';

  @override
  String get commitmentText =>
      'Obavezani smo koristiti podatke koje prikupljamo samo kako bismo Omi učinili boljim proizvodom za vas. Vaša privatnost i povjerenje su nama od prvorazrednog značaja.';

  @override
  String get thankYouText =>
      'Hvala što ste dragocjeni korisnik Omija. Ako imate bilo kakvih pitanja ili zabrinutosti, slobodno nam se obratite na team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Postavke WiFi sinhronizacije';

  @override
  String get enterHotspotCredentials => 'Unesite vjerodajnice pristupne točke vašeg telefona';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi sinhronizacija koristi vaš telefon kao pristupnu točku. Pronađite naziv pristupne točke i lozinku u Postavkama > Osobna pristupna točka.';

  @override
  String get hotspotNameSsid => 'Naziv pristupne točke (SSID)';

  @override
  String get exampleIphoneHotspot => 'npr. iPhone pristupna točka';

  @override
  String get password => 'Lozinka';

  @override
  String get enterHotspotPassword => 'Unesite lozinku pristupne točke';

  @override
  String get saveCredentials => 'Spremi vjerodajnice';

  @override
  String get clearCredentials => 'Očisti vjerodajnice';

  @override
  String get pleaseEnterHotspotName => 'Molimo unesite naziv pristupne točke';

  @override
  String get wifiCredentialsSaved => 'WiFi vjerodajnice su spremljene';

  @override
  String get wifiCredentialsCleared => 'WiFi vjerodajnice su obrisane';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Sažetak je napravljen za $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Nije moguće napraviti sažetak. Provjerite jesu li razgovori za taj dan dostupni.';

  @override
  String get summaryNotFound => 'Sažetak nije pronađen';

  @override
  String get yourDaysJourney => 'Putovanje vašeg dana';

  @override
  String get highlights => 'Ključne točke';

  @override
  String get unresolvedQuestions => 'Neriješena pitanja';

  @override
  String get decisions => 'Odluke';

  @override
  String get learnings => 'Učenja';

  @override
  String get autoDeletesAfterThreeDays => 'Automatski se briše nakon 3 dana.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Grafikon znanja je uspješno obrisan';

  @override
  String get exportStartedMayTakeFewSeconds => 'Izvoz je započet. Ovo može potrajati nekoliko sekundi...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'Ovo će obrisati sve izvedene podatke grafa znanja (čvorove i veze). Vaše originalne uspomene će ostati sigurne. Grafikon će biti ponovno izgrađen tijekom vremena ili pri sljedećem zahtjevu.';

  @override
  String get configureDailySummaryDigest => 'Konfiguriraj svoj dnevni sažetak stavki za akciju';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Pristupa $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'pokrenuto sa $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription i pokrenuto sa $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Je pokrenuto sa $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Nema specifičnog pristupa podacima konfiguriranog.';

  @override
  String get basicPlanDescription => '1.200 premium minuta + neograničeno na uređaju';

  @override
  String get minutes => 'minute';

  @override
  String get omiHas => 'Omi ima:';

  @override
  String get premiumMinutesUsed => 'Premium minute korištene.';

  @override
  String get setupOnDevice => 'Postavi na uređaj';

  @override
  String get forUnlimitedFreeTranscription => 'za neograničenu besplatnu transkripciju.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium minuta preostalo.';
  }

  @override
  String get alwaysAvailable => 'uvijek dostupno.';

  @override
  String get importHistory => 'Povijesni import';

  @override
  String get noImportsYet => 'Još nema importa';

  @override
  String get selectZipFileToImport => 'Odaberite .zip datoteku za import!';

  @override
  String get otherDevicesComingSoon => 'Drugi uređaji dolaze uskoro';

  @override
  String get deleteAllLimitlessConversations => 'Obrisati sve razgovore bez ograničenja?';

  @override
  String get deleteAllLimitlessWarning =>
      'Ovo će trajno obrisati sve razgovore uvezene iz Limitless aplikacije. Ova akcija se ne može poništiti.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Obrisano $count razgovora bez ograničenja';
  }

  @override
  String get failedToDeleteConversations => 'Nije moguće obrisati razgovore';

  @override
  String get deleteImportedData => 'Obriši importane podatke';

  @override
  String get statusPending => 'Na čekanju';

  @override
  String get statusProcessing => 'Obrada u tijeku';

  @override
  String get statusCompleted => 'Završeno';

  @override
  String get statusFailed => 'Nije uspjelo';

  @override
  String nConversations(int count) {
    return '$count razgovora';
  }

  @override
  String get pleaseEnterName => 'Molimo unesite naziv';

  @override
  String get nameMustBeBetweenCharacters => 'Naziv mora biti između 2 i 40 znakova';

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
    return 'Jeste li sigurni da želite obrisati $name? Ovo će ukloniti i sve povezane uzorke govora.';
  }

  @override
  String get howItWorksTitle => 'Kako funkcionira?';

  @override
  String get howPeopleWorks =>
      'Kada se osoba kreira, možete prijeći na transkripciju razgovora i dodijeliti im odgovarajuće segmente, tako će Omi moći prepoznati njihov govor!';

  @override
  String get tapToDelete => 'Dodirnite za brisanje';

  @override
  String get newTag => 'NOVO';

  @override
  String get needHelpChatWithUs => 'Trebate pomoć? Razgovarajte s nama';

  @override
  String get localStorageEnabled => 'Lokalna pohrana je omogućena';

  @override
  String get localStorageDisabled => 'Lokalna pohrana je onemogućena';

  @override
  String failedToUpdateSettings(String error) {
    return 'Nije moguće ažurirati postavke: $error';
  }

  @override
  String get privacyNotice => 'Obavijest o privatnosti';

  @override
  String get recordingsMayCaptureOthers =>
      'Snimke mogu uhvatiti glasove drugih osoba. Pazite da imate pristanak svih sudionika prije nego što omogućite.';

  @override
  String get enable => 'Omogući';

  @override
  String get storeAudioOnPhone => 'Spremi audio na telefon';

  @override
  String get on => 'Uključeno';

  @override
  String get storeAudioDescription =>
      'Čuvajte sve audio snimke lokalno na vašem telefonu. Kada je onemogućeno, samo neuspješna učitavanja su čuvana kako bi se uštedilo prostor za pohranu.';

  @override
  String get enableLocalStorage => 'Omogući lokalnu pohranu';

  @override
  String get cloudStorageEnabled => 'Pohrana u oblaku je omogućena';

  @override
  String get cloudStorageDisabled => 'Pohrana u oblaku je onemogućena';

  @override
  String get enableCloudStorage => 'Omogući pohranu u oblaku';

  @override
  String get storeAudioOnCloud => 'Spremi audio u oblak';

  @override
  String get cloudStorageDialogMessage =>
      'Vaše snimke u stvarnom vremenu bit će pohranjene u privatnoj pohrani u oblaku dok govorite.';

  @override
  String get storeAudioCloudDescription =>
      'Pohranite snimke u stvarnom vremenu u privatnoj pohrani u oblaku dok govorite. Audio se hvata i sigurno sprema u stvarnom vremenu.';

  @override
  String get downloadingFirmware => 'Preuzimanje firmware-a';

  @override
  String get installingFirmware => 'Instalacija firmware-a';

  @override
  String get firmwareUpdateWarning =>
      'Nemojte zatvarati aplikaciju niti isključiti uređaj. Ovo bi moglo oštetiti vaš uređaj.';

  @override
  String get firmwareUpdated => 'Firmware je ažuriran';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Molimo ponovno pokrenite vaš $deviceName da biste dovršili ažuriranje.';
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
  String get checkingFirmwareVersion => 'Provjera verzije firmware-a...';

  @override
  String get firmwareUpdate => 'Ažuriranje firmware-a';

  @override
  String get payments => 'Uplate';

  @override
  String get connectPaymentMethodInfo =>
      'Povežite metodu plaćanja ispod kako biste započeli primanje plaćanja za vaše aplikacije.';

  @override
  String get selectedPaymentMethod => 'Odabrana metoda plaćanja';

  @override
  String get availablePaymentMethods => 'Dostupne metode plaćanja';

  @override
  String get activeStatus => 'Aktivno';

  @override
  String get connectedStatus => 'Povezano';

  @override
  String get notConnectedStatus => 'Nije povezano';

  @override
  String get setActive => 'Postavi aktivno';

  @override
  String get getPaidThroughStripe => 'Dobijte plaćanje za prodaju aplikacije preko Stripea';

  @override
  String get monthlyPayouts => 'Mjesečne isplate';

  @override
  String get monthlyPayoutsDescription =>
      'Primite mjesečne isplate izravno na svoj račun kada dosegnete 10 dolara prihoda';

  @override
  String get secureAndReliable => 'Sigurno i pouzdano';

  @override
  String get stripeSecureDescription =>
      'Stripe osigurava sigurne i pravovremene prosljeđivanja vašeg prihoda od aplikacije';

  @override
  String get selectYourCountry => 'Odaberite vašu zemlju';

  @override
  String get countrySelectionPermanent => 'Vaš izbor zemlje je trajno i ne može se kasnije promijeniti.';

  @override
  String get byClickingConnectNow => 'Klikom na \"Poveži sada\" pristajete na';

  @override
  String get stripeConnectedAccountAgreement => 'Sporazum Stripe-ova povezanog računa';

  @override
  String get errorConnectingToStripe => 'Greška pri povezivanju na Stripe! Molimo pokušajte kasnije.';

  @override
  String get connectingYourStripeAccount => 'Povezivanje vašeg Stripe računa';

  @override
  String get stripeOnboardingInstructions =>
      'Molimo dovršite Stripe proces uključivanja u svom pregledniku. Ova se stranica će automatski ažurirati nakon što je dovršena.';

  @override
  String get failedTryAgain => 'Nije uspjelo? Pokušaj ponovno';

  @override
  String get illDoItLater => 'Učinit ću to kasnije';

  @override
  String get successfullyConnected => 'Uspješno povezano!';

  @override
  String get stripeReadyForPayments =>
      'Vaš Stripe račun je sada spreman za primanje plaćanja. Možete odmah početi zarađivati od prodaje aplikacije.';

  @override
  String get updateStripeDetails => 'Ažuriraj Stripe detalje';

  @override
  String get errorUpdatingStripeDetails => 'Greška pri ažuriranju Stripe detalja! Molimo pokušajte kasnije.';

  @override
  String get updatePayPal => 'Ažuriraj PayPal';

  @override
  String get setUpPayPal => 'Postavi PayPal';

  @override
  String get updatePayPalAccountDetails => 'Ažuriraj detalje svog PayPal računa';

  @override
  String get connectPayPalToReceivePayments =>
      'Povežite vaš PayPal račun kako biste započeli primanje plaćanja za vaše aplikacije';

  @override
  String get paypalEmail => 'PayPal e-mail';

  @override
  String get paypalMeLink => 'PayPal.me veza';

  @override
  String get stripeRecommendation => 'Ako je Stripe dostupan u vašoj zemlji, preporučujemo ga za brže i lakše isplate.';

  @override
  String get updatePayPalDetails => 'Ažuriraj PayPal detalje';

  @override
  String get savePayPalDetails => 'Spremi PayPal detalje';

  @override
  String get pleaseEnterPayPalEmail => 'Molimo unesite vašu PayPal e-mail adresu';

  @override
  String get pleaseEnterPayPalMeLink => 'Molimo unesite vašu PayPal.me vezu';

  @override
  String get doNotIncludeHttpInLink => 'Nemojte uključiti http ili https ili www u vezu';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Molimo unesite valjanu PayPal.me vezu';

  @override
  String get pleaseEnterValidEmail => 'Molimo unesite valjanu e-mail adresu';

  @override
  String get syncingYourRecordings => 'Sinhronizacija vaših snimki';

  @override
  String get syncYourRecordings => 'Sinhroniziraj vaše snimke';

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
      'Nastavljanjem, vaši razgovori, snimke i lični podaci bit će sigurno pohranjeni na našim serverima. Vaši audio zapisi i transkripti se obrađuju od strane AI usluga trećih strana (uključujući Deepgram za transkripciju i OpenAI za analizu) kako bi vam pružili uvide pokretane vještačkom inteligencijom i omogućili sve funkcije aplikacije.';

  @override
  String get tasksEmptyStateMessage =>
      'Zadaci iz vaših razgovora će se pojaviti ovdje.\\nDodirnite + da ga kreirate ručno.';

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
  String get loadingYourRecording => 'Učitavanje vaše snimke...';

  @override
  String get photoDiscardedMessage => 'Ova fotografija je odbijena jer nije bila signifikantna.';

  @override
  String get analyzing => 'Analiza u tijeku...';

  @override
  String get searchCountries => 'Pretraži zemlje';

  @override
  String get checkingAppleWatch => 'Provjera Apple Watch-a...';

  @override
  String get installOmiOnAppleWatch => 'Instalirajte Omi na vaš\\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Kako biste koristili Apple Watch s Omijom, trebate prvo instalirati Omi aplikaciju na svoj satnici.';

  @override
  String get openOmiOnAppleWatch => 'Otvorite Omi na vaš\\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi aplikacija je instalirana na vašoj Apple Watch satnici. Otvorite je i dodirnite Počni kako biste započeli.';

  @override
  String get openWatchApp => 'Otvori aplikaciju satnice';

  @override
  String get iveInstalledAndOpenedTheApp => 'Instalirao/a sam i otvorio/a aplikaciju';

  @override
  String get unableToOpenWatchApp =>
      'Nije moguće otvoriti Apple Watch aplikaciju. Molimo ručno otvorite Watch aplikaciju na vašoj Apple Watch satnici i instalirajte Omi iz odjeljka \"Dostupne aplikacije\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch je uspješno povezan!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch još nije dostupan. Molimo provjerite je li Omi aplikacija otvorena na vašoj satnici.';

  @override
  String errorCheckingConnection(String error) {
    return 'Greška pri provjeri konekcije: $error';
  }

  @override
  String get muted => 'Utišano';

  @override
  String get processNow => 'Obrada sada';

  @override
  String get finishedConversation => 'Završili ste razgovor?';

  @override
  String get stopRecordingConfirmation => 'Jeste li sigurni da želite zaustaviti snimanje i sažeti razgovor sada?';

  @override
  String get conversationEndsManually => 'Razgovor će se završiti samo ručno.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Razgovor je sažet nakon $minutes minuta$suffix bez govora.';
  }

  @override
  String get dontAskAgain => 'Nemoj me više pitati';

  @override
  String get waitingForTranscriptOrPhotos => 'Čekanje na transkripciju ili fotografije...';

  @override
  String get noSummaryYet => 'Nema sažetka još';

  @override
  String hints(String text) {
    return 'Savjeti: $text';
  }

  @override
  String get testConversationPrompt => 'Testiraj promptu razgovora';

  @override
  String get prompt => 'Promptu';

  @override
  String get result => 'Rezultat:';

  @override
  String get compareTranscripts => 'Usporedi transkripcije';

  @override
  String get notHelpful => 'Nije korisno';

  @override
  String get exportTasksWithOneTap => 'Izvezi zadatke s jednim dodirom!';

  @override
  String get inProgress => 'U tijeku';

  @override
  String get photos => 'Fotografije';

  @override
  String get rawData => 'Neobrađeni podaci';

  @override
  String get content => 'Sadržaj';

  @override
  String get noContentToDisplay => 'Nema sadržaja za prikaz';

  @override
  String get noSummary => 'Nema sažetka';

  @override
  String get updateOmiFirmware => 'Ažuriraj omi firmware';

  @override
  String get anErrorOccurredTryAgain => 'Došlo je do greške. Molimo pokušajte ponovno.';

  @override
  String get welcomeBackSimple => 'Dobrodošli natrag';

  @override
  String get addVocabularyDescription => 'Dodajte riječi koje bi Omi trebao prepoznati tijekom transkripcije.';

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
  String get developerApiKeys => 'Ključevi razvojnog API-ja';

  @override
  String get noApiKeysCreateOne => 'Nema API ključeva. Kreirajte jedan kako biste započeli.';

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
    return 'Korisnik Top $percentile%';
  }

  @override
  String get wrappedMinutes => 'minute';

  @override
  String get wrappedConversations => 'razgovora';

  @override
  String get wrappedDaysActive => 'dana aktivnosti';

  @override
  String get wrappedYouTalkedAbout => 'Govorili ste o';

  @override
  String get wrappedActionItems => 'Stavke za akciju';

  @override
  String get wrappedTasksCreated => 'kreirane zadatke';

  @override
  String get wrappedCompleted => 'dovršeno';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% stopa završetka';
  }

  @override
  String get wrappedYourTopDays => 'Vaši najbolji dani';

  @override
  String get wrappedBestMoments => 'Najbolji momenti';

  @override
  String get wrappedMyBuddies => 'Moji prijatelji';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Nisu mogli prestati govoriti o';

  @override
  String get wrappedShow => 'SERIJA';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'KNJIGA';

  @override
  String get wrappedCelebrity => 'POZNATA OSOBA';

  @override
  String get wrappedFood => 'HRANA';

  @override
  String get wrappedMovieRecs => 'Preporuke filmova za prijatelje';

  @override
  String get wrappedBiggest => 'Najveće';

  @override
  String get wrappedStruggle => 'Borba';

  @override
  String get wrappedButYouPushedThrough => 'Ali ste se probili 💪';

  @override
  String get wrappedWin => 'Pobjeda';

  @override
  String get wrappedYouDidIt => 'Uspjeli ste! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 fraza';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'razgovora';

  @override
  String get wrappedDays => 'dana';

  @override
  String get wrappedMyBuddiesLabel => 'MOJI PRIJATELJI';

  @override
  String get wrappedObsessionsLabel => 'OPSESIJE';

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
  String get wrappedProcessingDefault => 'Obrada u tijeku...';

  @override
  String get wrappedCreatingYourStory => 'Stvaranje vaše\\n2025 priče...';

  @override
  String get wrappedSomethingWentWrong => 'Nešto je\\npoš pošlo naopako';

  @override
  String get wrappedAnErrorOccurred => 'Došlo je do greške';

  @override
  String get wrappedTryAgain => 'Pokušaj ponovno';

  @override
  String get wrappedNoDataAvailable => 'Nema dostupnih podataka';

  @override
  String get wrappedOmiLifeRecap => 'Sažetak Omijeva života';

  @override
  String get wrappedSwipeUpToBegin => 'Prijeđite prema gore da biste započeli';

  @override
  String get wrappedShareText => 'Moja 2025, zapamćena od Omija ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Nije moguće dijeliti. Molimo pokušajte ponovno.';

  @override
  String get wrappedFailedToStartGeneration => 'Nije moguće započeti generiranje. Molimo pokušajte ponovno.';

  @override
  String get wrappedStarting => 'Pokretanje...';

  @override
  String get wrappedShare => 'Dijeli';

  @override
  String get wrappedShareYourWrapped => 'Podijeli svoj Wrapped';

  @override
  String get wrappedMy2025 => 'Moja 2025';

  @override
  String get wrappedRememberedByOmi => 'zapamćena od Omija';

  @override
  String get wrappedMostFunDay => 'Najveće zabave';

  @override
  String get wrappedMostProductiveDay => 'Najmanja produktivna';

  @override
  String get wrappedMostIntenseDay => 'Najmanja intenzivna';

  @override
  String get wrappedFunniestMoment => 'Najsmješnije';

  @override
  String get wrappedMostCringeMoment => 'Najveće cringe';

  @override
  String get wrappedMinutesLabel => 'minute';

  @override
  String get wrappedConversationsLabel => 'razgovora';

  @override
  String get wrappedDaysActiveLabel => 'dana aktivnosti';

  @override
  String get wrappedTasksGenerated => 'generirane zadatke';

  @override
  String get wrappedTasksCompleted => 'dovršene zadatke';

  @override
  String get wrappedTopFivePhrases => 'Top 5 fraza';

  @override
  String get wrappedAGreatDay => 'Odličan dan';

  @override
  String get wrappedGettingItDone => 'Postizanje cilja';

  @override
  String get wrappedAChallenge => 'Izazov';

  @override
  String get wrappedAHilariousMoment => 'Smiješan trenutak';

  @override
  String get wrappedThatAwkwardMoment => 'Taj neugodan trenutak';

  @override
  String get wrappedYouHadFunnyMoments => 'Imali ste neke smiješne trenutke ove godine!';

  @override
  String get wrappedWeveAllBeenThere => 'Svi smo bili tamo!';

  @override
  String get wrappedFriend => 'Prijatelj';

  @override
  String get wrappedYourBuddy => 'Tvoj prijatelj!';

  @override
  String get wrappedNotMentioned => 'Nije spomenuto';

  @override
  String get wrappedTheHardPart => 'Teški dio';

  @override
  String get wrappedPersonalGrowth => 'Lični rast';

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
  String get wrappedObsessionsLabelUpper => 'OPSESIJE';

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
  String get wrappedMomentsHeader => 'momenti';

  @override
  String get wrappedBestMomentsBadge => 'Najbolji momenti';

  @override
  String get wrappedBiggestHeader => 'Najveće';

  @override
  String get wrappedStruggleHeader => 'Borba';

  @override
  String get wrappedWinHeader => 'Pobjeda';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ali ste se probili 💪';

  @override
  String get wrappedYouDidItEmoji => 'Uspjeli ste! 🎉';

  @override
  String get wrappedHours => 'sati';

  @override
  String get wrappedActions => 'akcije';

  @override
  String get multipleSpeakersDetected => 'Detektirani su višestruki govornici';

  @override
  String get multipleSpeakersDescription =>
      'Čini se da ima više govornika u snimci. Molimo provjerite da ste na tihoj lokaciji i pokušajte ponovno.';

  @override
  String get invalidRecordingDetected => 'Detektirana je nevaljana snimka';

  @override
  String get notEnoughSpeechDescription =>
      'Nema dovoljno detektiranog govora. Molimo govorite više i pokušajte ponovno.';

  @override
  String get speechDurationDescription => 'Molimo osigurajte da govorite najmanje 5 sekundi i ne više od 90.';

  @override
  String get connectionLostDescription =>
      'Veza je prekinuta. Molimo proverite vašu internet konekciju i pokušajte ponovno.';

  @override
  String get howToTakeGoodSample => 'Kako napraviti dobar uzorak?';

  @override
  String get goodSampleInstructions =>
      '1. Osigurajte se da ste na mirnom mjestu.\n2. Govorite jasno i prirodno.\n3. Osigurajte se da je vaš uređaj u prirodnoj poziciji, na vašoj vratu.\n\nKada se napravi, uvijek ga možete poboljšati ili ponoviti.';

  @override
  String get noDeviceConnectedUseMic => 'Nema priključenog uređaja. Koristit će se mikrofon telefona.';

  @override
  String get doItAgain => 'Uradi to ponovno';

  @override
  String get listenToSpeechProfile => 'Čuj moj profil govora ➡️';

  @override
  String get recognizingOthers => 'Prepoznavanje ostalih 👀';

  @override
  String get keepGoingGreat => 'Nastavi dalje, odličan si';

  @override
  String get somethingWentWrongTryAgain => 'Nešto je pošlo po zlu! Molimo pokušajte ponovno kasnije.';

  @override
  String get uploadingVoiceProfile => 'Prenosim vašu profila glasa....';

  @override
  String get memorizingYourVoice => 'Memoriziram tvoj glas...';

  @override
  String get personalizingExperience => 'Personalizujem tvoje iskustvo...';

  @override
  String get keepSpeakingUntil100 => 'Nastavi da govoriš dok ne dobiješ 100%.';

  @override
  String get greatJobAlmostThere => 'Odličan posao, gotovo si tu';

  @override
  String get soCloseJustLittleMore => 'Tako blizu, samo malo još';

  @override
  String get notificationFrequency => 'Učestalost obaveštenja';

  @override
  String get controlNotificationFrequency => 'Kontroliši kako često Omi šalje proaktivna obaveštenja.';

  @override
  String get yourScore => 'Tvoj rezultat';

  @override
  String get dailyScoreBreakdown => 'Razrada dnevnog rezultata';

  @override
  String get todaysScore => 'Današnji rezultat';

  @override
  String get tasksCompleted => 'Završeni zadaci';

  @override
  String get completionRate => 'Stopa završenosti';

  @override
  String get howItWorks => 'Kako funkcioniše';

  @override
  String get dailyScoreExplanation =>
      'Tvoj dnevni rezultat je zasnovan na završetku zadataka. Završi svoje zadatke da poboljšaš rezultat!';

  @override
  String get notificationFrequencyDescription => 'Kontroliši kako često Omi šalje proaktivna obaveštenja i podsetnike.';

  @override
  String get sliderOff => 'Isključeno';

  @override
  String get sliderMax => 'Maksimalno';

  @override
  String summaryGeneratedFor(String date) {
    return 'Rezime generirano za $date';
  }

  @override
  String get failedToGenerateSummary => 'Nije moguće generisati rezime. Osigurajte se da imate razgovore za taj dan.';

  @override
  String get recap => 'Pregled';

  @override
  String deleteQuoted(String name) {
    return 'Obriši \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Pomeri $count razgovora u:';
  }

  @override
  String get noFolder => 'Bez fascikle';

  @override
  String get removeFromAllFolders => 'Ukloni iz svih fascikli';

  @override
  String get buildAndShareYourCustomApp => 'Napravi i podeli svoju prilagođenu aplikaciju';

  @override
  String get searchAppsPlaceholder => 'Pretraži 1500+ aplikacija';

  @override
  String get filters => 'Filteri';

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
  String get frequencyDescOff => 'Nema proaktivnih obaveštenja';

  @override
  String get frequencyDescMinimal => 'Samo kritični podsetnnici';

  @override
  String get frequencyDescLow => 'Samo važna ažuriranja';

  @override
  String get frequencyDescBalanced => 'Redovni korisni podsetnnici';

  @override
  String get frequencyDescHigh => 'Česti ček-inovi';

  @override
  String get frequencyDescMaximum => 'Budi neprekidno angažovan';

  @override
  String get clearChatQuestion => 'Očisti razgovor?';

  @override
  String get syncingMessages => 'Sinhronizujem poruke sa serverom...';

  @override
  String get chatAppsTitle => 'Aplikacije za razgovor';

  @override
  String get selectApp => 'Odaberi aplikaciju';

  @override
  String get noChatAppsEnabled => 'Nema aktivnih aplikacija za razgovor.\nTapni \"Omogući aplikacije\" da dodam neke.';

  @override
  String get disable => 'Onemogući';

  @override
  String get photoLibrary => 'Biblioteka fotografija';

  @override
  String get chooseFile => 'Odaberi datoteku';

  @override
  String get connectAiAssistantsToYourData => 'Poveži AI asistente sa tvojim podacima';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Prati svoje lične ciljeve na početnoj stranici';

  @override
  String get deleteRecording => 'Obriši snimak';

  @override
  String get thisCannotBeUndone => 'Ovo se ne može poništiti.';

  @override
  String get sdCard => 'SD kartica';

  @override
  String get fromSd => 'Sa SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Brzi prenos';

  @override
  String get syncingStatus => 'Sinhronizujem';

  @override
  String get failedStatus => 'Neuspješno';

  @override
  String etaLabel(String time) {
    return 'ETA: $time';
  }

  @override
  String get transferMethod => 'Način prenosa';

  @override
  String get fast => 'Brzo';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Otkaži sinhronizaciju';

  @override
  String get cancelSyncMessage => 'Podaci koji su već preuzeti biće sačuvani. Možete nastaviti kasnije.';

  @override
  String get syncCancelled => 'Sinhronizacija otkazana';

  @override
  String get deleteProcessedFiles => 'Obriši obrađene datoteke';

  @override
  String get processedFilesDeleted => 'Obrađene datoteke obrisane';

  @override
  String get wifiEnableFailed => 'Neuspješno omogućavanje WiFi-ja na uređaju. Molimo pokušajte ponovno.';

  @override
  String get deviceNoFastTransfer => 'Vaš uređaj ne podržava brzi prenos. Umjesto toga koristite Bluetooth.';

  @override
  String get enableHotspotMessage => 'Molimo omogućite hotspot vašeg telefona i pokušajte ponovno.';

  @override
  String get transferStartFailed => 'Neuspješan start prenosa. Molimo pokušajte ponovno.';

  @override
  String get deviceNotResponding => 'Uređaj nije odgovorio. Molimo pokušajte ponovno.';

  @override
  String get invalidWifiCredentials => 'Neispravne WiFi kredencijale. Provjerite postavke hotspota.';

  @override
  String get wifiConnectionFailed => 'Konekcija sa WiFi-jem neuspješna. Molimo pokušajte ponovno.';

  @override
  String get sdCardProcessing => 'Obrada SD kartice';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Obrada $count snimka(a). Datoteke će biti uklonjene sa SD kartice kasnije.';
  }

  @override
  String get process => 'Obradi';

  @override
  String get wifiSyncFailed => 'WiFi sinhronizacija nije uspjela';

  @override
  String get processingFailed => 'Obrada nije uspjela';

  @override
  String get downloadingFromSdCard => 'Preuzimanje sa SD kartice';

  @override
  String processingProgress(int current, int total) {
    return 'Obrada $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count razgovora kreirano';
  }

  @override
  String get internetRequired => 'Internet obavezan';

  @override
  String get processAudio => 'Obradi audio';

  @override
  String get start => 'Počni';

  @override
  String get noRecordings => 'Nema snimaka';

  @override
  String get audioFromOmiWillAppearHere => 'Audio sa vašeg Omi uređaja će se pojaviti ovdje';

  @override
  String get deleteProcessed => 'Obriši obrađene';

  @override
  String get tryDifferentFilter => 'Isprobaj drugi filter';

  @override
  String get recordings => 'Snimci';

  @override
  String get enableRemindersAccess =>
      'Molimo omogućite pristup podsjetnicima u postavkama da biste koristili Apple podsjetnike';

  @override
  String todayAtTime(String time) {
    return 'Danas u $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Jučer u $time';
  }

  @override
  String get lessThanAMinute => 'Manje od minut';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(e)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count sat(i)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Procijenjeno: $time preostaje';
  }

  @override
  String get summarizingConversation => 'Sažimam razgovor...\nOvo može potrajati nekoliko sekundi';

  @override
  String get resummarizingConversation => 'Ponovno sažimam razgovor...\nOvo može potrajati nekoliko sekundi';

  @override
  String get nothingInterestingRetry => 'Ništa zanimljivo nije pronađeno,\nželiš li pokušati ponovno?';

  @override
  String get noSummaryForConversation => 'Rezime nije dostupan\nza ovaj razgovor.';

  @override
  String get unknownLocation => 'Nepoznata lokacija';

  @override
  String get couldNotLoadMap => 'Nije moguće učitati mapu';

  @override
  String get triggerConversationIntegration => 'Pokretanje integracije kreirane konverzacije';

  @override
  String get webhookUrlNotSet => 'Webhook URL nije postavljen';

  @override
  String get setWebhookUrlInSettings =>
      'Molimo postavite webhook URL u postavkama za razvojnjake da biste koristili ovu funkciju.';

  @override
  String get sendWebUrl => 'Pošalji web url';

  @override
  String get sendTranscript => 'Pošalji transkripciju';

  @override
  String get sendSummary => 'Pošalji rezime';

  @override
  String get debugModeDetected => 'Detektovan režim otklanjanja grešaka';

  @override
  String get performanceReduced => 'Performanse smanjene za 5-10x. Koristi Release modu.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Automatski zatvaranje za ${seconds}s';
  }

  @override
  String get modelRequired => 'Model obavezan';

  @override
  String get downloadWhisperModel => 'Molimo preuzmite Whisper model prije nego što sačuvate.';

  @override
  String get deviceNotCompatible => 'Uređaj nije kompatibilan';

  @override
  String get deviceRequirements => 'Vaš uređaj ne ispunjava zahtjeve za transkripciju na uređaju.';

  @override
  String get willLikelyCrash => 'Omogućavanje toga će vjerovatno uzrokovati pad aplikacije ili smrzavanje.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkripcija će biti znatno sporija i manje točna.';

  @override
  String get proceedAnyway => 'Nastavi svakako';

  @override
  String get olderDeviceDetected => 'Detektovan stariji uređaj';

  @override
  String get onDeviceSlower => 'Transkripcija na uređaju može biti sporija na ovom uređaju.';

  @override
  String get batteryUsageHigher => 'Potrošnja baterije će biti veća nego pri transkripciji oblaka.';

  @override
  String get considerOmiCloud => 'Razmotri korištenje Omi Cloud-a za bolje performanse.';

  @override
  String get highResourceUsage => 'Visoka potrošnja resursa';

  @override
  String get onDeviceIntensive => 'Transkripcija na uređaju je računski intenzivna.';

  @override
  String get batteryDrainIncrease => 'Drenaža baterije će se značajno povećati.';

  @override
  String get deviceMayWarmUp => 'Uređaj može postati topao tokom dužeg korištenja.';

  @override
  String get speedAccuracyLower => 'Brzina i točnost mogu biti niže nego kod Cloud modela.';

  @override
  String get cloudProvider => 'Pružalac usluga u oblaku';

  @override
  String get premiumMinutesInfo =>
      '1.200 premium minuta/mjesec. Kartaca na uređaju nudi neограничenu besplatnu transkripciju.';

  @override
  String get viewUsage => 'Prikaži upotrebu';

  @override
  String get localProcessingInfo =>
      'Audio se obrađuje lokalno. Funkcioniše bez interneta, privatnije je, ali troši više baterije.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Upozorenje o performansama';

  @override
  String get largeModelWarning =>
      'Ovaj model je velik i može uzrokovati pad aplikacije ili vrlo sporo pokretanje na mobilnim uređajima.\n\nPreporučuje se \"small\" ili \"base\".';

  @override
  String get usingNativeIosSpeech => 'Korištenje nativnog iOS prepoznavanja govora';

  @override
  String get noModelDownloadRequired =>
      'Koristiće se ugrađeni motor za govore vašeg uređaja. Preuzimanje modela nije potrebno.';

  @override
  String get modelReady => 'Model je spreman';

  @override
  String get redownload => 'Ponovno preuzmi';

  @override
  String get doNotCloseApp => 'Molimo ne zatvarajte aplikaciju.';

  @override
  String get downloading => 'Preuzimam...';

  @override
  String get downloadModel => 'Preuzmi model';

  @override
  String estimatedSize(String size) {
    return 'Procjena veličine: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Dostupan prostor: $space';
  }

  @override
  String get notEnoughSpace => 'Upozorenje: Nema dovoljno prostora!';

  @override
  String get download => 'Preuzmi';

  @override
  String downloadError(String error) {
    return 'Greška pri preuzimanju: $error';
  }

  @override
  String get cancelled => 'Otkazano';

  @override
  String get deviceNotCompatibleTitle => 'Uređaj nije kompatibilan';

  @override
  String get deviceNotMeetRequirements => 'Vaš uređaj ne ispunjava zahtjeve za transkripciju na uređaju.';

  @override
  String get transcriptionSlowerOnDevice => 'Transkripcija na uređaju može biti sporija na ovom uređaju.';

  @override
  String get computationallyIntensive => 'Transkripcija na uređaju je računski intenzivna.';

  @override
  String get batteryDrainSignificantly => 'Drenaža baterije će se značajno povećati.';

  @override
  String get premiumMinutesMonth =>
      '1.200 premium minuta/mjesec. Kartaca na uređaju nudi neograničenu besplatnu transkripciju. ';

  @override
  String get audioProcessedLocally =>
      'Audio se obrađuje lokalno. Funkcioniše bez interneta, privatnije je, ali troši više baterije.';

  @override
  String get languageLabel => 'Jezik';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Ovaj model je velik i može uzrokovati pad aplikacije ili vrlo sporo pokretanje na mobilnim uređajima.\n\nPreporučuje se \"small\" ili \"base\".';

  @override
  String get nativeEngineNoDownload =>
      'Koristiće se ugrađeni motor za govore vašeg uređaja. Preuzimanje modela nije potrebno.';

  @override
  String modelReadyWithName(String model) {
    return 'Model je spreman ($model)';
  }

  @override
  String get reDownload => 'Ponovno preuzmi';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Preuzimam $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Priprema $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Greška pri preuzimanju: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Procjena veličine: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Dostupan prostor: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Ugrađena transkripcija u realnom vremenu tvrtke Omi je optimizovana za razgovore u realnom vremenu sa automatskim detektovanjem govornika i dijalizacijom.';

  @override
  String get reset => 'Resetuj';

  @override
  String get useTemplateFrom => 'Koristi šablon od';

  @override
  String get selectProviderTemplate => 'Odaberi šablon pružaoca...';

  @override
  String get quicklyPopulateResponse => 'Brzo popuni sa poznatim formatom odgovora pružaoca';

  @override
  String get quicklyPopulateRequest => 'Brzo popuni sa poznatim formatom zahtjeva pružaoca';

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
  String get chatAssistantsTitle => 'Chat asistenti';

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
  String get permissionTypeTrigger => 'Pokretanje';

  @override
  String get permissionDescReadConversations => 'Ova aplikacija može pristupiti tvojim razgovorima.';

  @override
  String get permissionDescReadMemories => 'Ova aplikacija može pristupiti tvojim uspomenama.';

  @override
  String get permissionDescReadTasks => 'Ova aplikacija može pristupiti tvojim zadacima.';

  @override
  String get permissionDescCreateConversations => 'Ova aplikacija može kreirati nove razgovore.';

  @override
  String get permissionDescCreateMemories => 'Ova aplikacija može kreirati nove uspomene.';

  @override
  String get realtimeListening => 'Slušanje u realnom vremenu';

  @override
  String get setupCompleted => 'Završeno';

  @override
  String get pleaseSelectRating => 'Molimo odaberi ocjenu';

  @override
  String get writeReviewOptional => 'Napiši recenziju (opcionalno)';

  @override
  String get setupQuestionsIntro => 'Pomozi nam poboljšati Omi odgovarajući na nekoliko pitanja.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. Šta radiš?';

  @override
  String get setupQuestionUsage => '2. Gdje planirate koristiti svoj Omi?';

  @override
  String get setupQuestionAge => '3. Koji je vaš raspon godina?';

  @override
  String get setupAnswerAllQuestions => 'Niste odgovorili na sva pitanja! 🥺';

  @override
  String get setupSkipHelp => 'Preskoči, ne želim da pomognem :C';

  @override
  String get professionEntrepreneur => 'Preduzetnik';

  @override
  String get professionSoftwareEngineer => 'Inženjer softvera';

  @override
  String get professionProductManager => 'Menadžer proizvoda';

  @override
  String get professionExecutive => 'Izvršni direktor';

  @override
  String get professionSales => 'Prodaja';

  @override
  String get professionStudent => 'Student';

  @override
  String get usageAtWork => 'Na poslu';

  @override
  String get usageIrlEvents => 'IRL događaji';

  @override
  String get usageOnline => 'Online';

  @override
  String get usageSocialSettings => 'U društvenim postavkama';

  @override
  String get usageEverywhere => 'Svugdje';

  @override
  String get customBackendUrlTitle => 'Prilagođeni URL servera';

  @override
  String get backendUrlLabel => 'URL servera';

  @override
  String get saveUrlButton => 'Spremi URL';

  @override
  String get enterBackendUrlError => 'Molimo unesite URL servera';

  @override
  String get urlMustEndWithSlashError => 'URL mora završiti sa \"/\"';

  @override
  String get invalidUrlError => 'Molimo unesite ispravan URL';

  @override
  String get backendUrlSavedSuccess => 'URL servera uspješno sačuvan!';

  @override
  String get signInTitle => 'Prijava';

  @override
  String get signInButton => 'Prijavi se';

  @override
  String get enterEmailError => 'Molimo unesite svoju e-poštu';

  @override
  String get invalidEmailError => 'Molimo unesite validnu e-poštu';

  @override
  String get enterPasswordError => 'Molimo unesite vašu lozinku';

  @override
  String get passwordMinLengthError => 'Lozinka mora biti najmanje 8 znakova dugačka';

  @override
  String get signInSuccess => 'Prijava uspješna!';

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
  String get signUpButton => 'Registruj se';

  @override
  String get enterNameError => 'Molimo unesite svoje ime';

  @override
  String get passwordsDoNotMatch => 'Lozinke se ne poklapaju';

  @override
  String get signUpSuccess => 'Registracija uspješna!';

  @override
  String get loadingKnowledgeGraph => 'Učitavanje grafa znanja...';

  @override
  String get noKnowledgeGraphYet => 'Nema grafa znanja';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Gradim tvoj graf znanja iz uspomena...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Tvoj graf znanja će se graditi automatski dok kreijaš nove uspomene.';

  @override
  String get buildGraphButton => 'Napravi graf';

  @override
  String get checkOutMyMemoryGraph => 'Pogledaj moj graf uspomena!';

  @override
  String get getButton => 'Uzmi';

  @override
  String openingApp(String appName) {
    return 'Otvaranje $appName...';
  }

  @override
  String get writeSomething => 'Napiši nešto';

  @override
  String get submitReply => 'Pošalji odgovor';

  @override
  String get editYourReply => 'Uredi svoj odgovor';

  @override
  String get replyToReview => 'Odgovori na recenziju';

  @override
  String get rateAndReviewThisApp => 'Ocijeni i recenziraj ovu aplikaciju';

  @override
  String get noChangesInReview => 'Nema promjena u recenziji za ažuriranje.';

  @override
  String get cantRateWithoutInternet => 'Ne možeš ocijenjivati aplikaciju bez internet konekcije.';

  @override
  String get appAnalytics => 'Analitika aplikacije';

  @override
  String get learnMoreLink => 'sazni više';

  @override
  String get moneyEarned => 'Zarada';

  @override
  String get writeYourReply => 'Napiši svoj odgovor...';

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
    return '$count zvjezdica';
  }

  @override
  String get noReviewsFound => 'Nema pronađenih recenzija';

  @override
  String get editReply => 'Uredi odgovor';

  @override
  String get reply => 'Odgovori';

  @override
  String starFilterLabel(int count) {
    return '$count zvjezdica';
  }

  @override
  String get sharePublicLink => 'Dijeli javnu vezu';

  @override
  String get connectedKnowledgeData => 'Povezani podaci znanja';

  @override
  String get enterName => 'Unesi ime';

  @override
  String get goal => 'CILJ';

  @override
  String get tapToTrackThisGoal => 'Tapni da pratišs ovaj cilj';

  @override
  String get tapToSetAGoal => 'Tapni da postaviš cilj';

  @override
  String get processedConversations => 'Obrađeni razgovori';

  @override
  String get updatedConversations => 'Ažurirani razgovori';

  @override
  String get newConversations => 'Novi razgovori';

  @override
  String get summaryTemplate => 'Šablon rezimea';

  @override
  String get suggestedTemplates => 'Predloženi šabloni';

  @override
  String get otherTemplates => 'Ostali šabloni';

  @override
  String get availableTemplates => 'Dostupni šabloni';

  @override
  String get getCreative => 'Budi kreativan';

  @override
  String get defaultLabel => 'Zadano';

  @override
  String get lastUsedLabel => 'Zadnja upotreba';

  @override
  String get setDefaultApp => 'Postavi zadanu aplikaciju';

  @override
  String setDefaultAppContent(String appName) {
    return 'Postavi $appName kao zadanu aplikaciju za sažimanje?\n\nOva aplikacija će biti automatski korištena za sve buduće rezimee razgovora.';
  }

  @override
  String get setDefaultButton => 'Postavi zadanu';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName je postavljena kao zadana aplikacija za sažimanje';
  }

  @override
  String get createCustomTemplate => 'Kreiraj prilagođeni šablon';

  @override
  String get allTemplates => 'Svi šabloni';

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
  String get personNameAlreadyExists => 'Osoba sa ovim imenom već postoji.';

  @override
  String get selectYouFromList => 'Za označavanje sebe, molimo odaberite \"Ti\" sa liste.';

  @override
  String get enterPersonsName => 'Unesi ime osobe';

  @override
  String get addPerson => 'Dodaj osobu';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Označi druge segmente od ovog govornika ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Označi druge segmente';

  @override
  String get managePeople => 'Upravljaj ljudima';

  @override
  String get shareViaSms => 'Dijeli preko SMS-a';

  @override
  String get selectContactsToShareSummary => 'Odaberi kontakte sa kojima želiš podijeliti rezime razgovora';

  @override
  String get searchContactsHint => 'Pretraži kontakte...';

  @override
  String contactsSelectedCount(int count) {
    return '$count odabrano';
  }

  @override
  String get clearAllSelection => 'Obriši sve';

  @override
  String get selectContactsToShare => 'Odaberi kontakte za dijeljenje';

  @override
  String shareWithContactCount(int count) {
    return 'Dijeli sa $count kontaktom';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Dijeli sa $count kontakata';
  }

  @override
  String get contactsPermissionRequired => 'Dozvola za kontakte obavezna';

  @override
  String get contactsPermissionRequiredForSms => 'Dozvola za kontakte obavezna za dijeljenje preko SMS-a';

  @override
  String get grantContactsPermissionForSms => 'Molimo dajte dozvolu za kontakte da biste dijelili preko SMS-a';

  @override
  String get noContactsWithPhoneNumbers => 'Nema pronađenih kontakata sa brojevima telefona';

  @override
  String get noContactsMatchSearch => 'Nema kontakata koji se poklapaju sa vašom pretragom';

  @override
  String get failedToLoadContacts => 'Neuspješno učitavanje kontakata';

  @override
  String get failedToPrepareConversationForSharing =>
      'Neuspješna priprema razgovora za dijeljenje. Molimo pokušajte ponovno.';

  @override
  String get couldNotOpenSmsApp => 'Nije moguće otvoriti SMS aplikaciju. Molimo pokušajte ponovno.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Evo što smo upravo diskutovali: $link';
  }

  @override
  String get wifiSync => 'WiFi sinhronizacija';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopiran u clipboard';
  }

  @override
  String get wifiConnectionFailedTitle => 'Konekcija nije uspjela';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Povezujem se na $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Omogući WiFi na $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Poveži se na $deviceName';
  }

  @override
  String get recordingDetails => 'Detalji snimka';

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
    return 'Sačuvano na $deviceName';
  }

  @override
  String get transferring => 'Transfer u tijeku...';

  @override
  String get transferRequired => 'Transfer obavezan';

  @override
  String get downloadingAudioFromSdCard => 'Preuzimanje audija sa SD kartice vašeg uređaja';

  @override
  String get transferRequiredDescription =>
      'Ovaj snimak je sačuvan na SD kartici vašeg uređaja. Prenesi ga na svoj telefon da bi ga mogao reproducirati ili dijeliti.';

  @override
  String get cancelTransfer => 'Otkaži transfer';

  @override
  String get transferToPhone => 'Prenesi na telefon';

  @override
  String get privateAndSecureOnDevice => 'Privatno i sigurno na vašem uređaju';

  @override
  String get recordingInfo => 'Informacije o snimku';

  @override
  String get transferInProgress => 'Prenos je u toku...';

  @override
  String get shareRecording => 'Dijeli snimak';

  @override
  String get deleteRecordingConfirmation =>
      'Jeste li sigurni da želite da trajno izbrišete ovaj snimak? Ovo se ne može poništiti.';

  @override
  String get recordingIdLabel => 'ID snimka';

  @override
  String get dateTimeLabel => 'Datum i vrijeme';

  @override
  String get durationLabel => 'Trajanje';

  @override
  String get audioFormatLabel => 'Format zvuka';

  @override
  String get storageLocationLabel => 'Lokacija pohrane';

  @override
  String get estimatedSizeLabel => 'Procijenjena veličina';

  @override
  String get deviceModelLabel => 'Model uređaja';

  @override
  String get deviceIdLabel => 'ID uređaja';

  @override
  String get statusLabel => 'Status';

  @override
  String get statusProcessed => 'Obrađeno';

  @override
  String get statusUnprocessed => 'Neobrađeno';

  @override
  String get switchedToFastTransfer => 'Prebačeno na brzi prenos';

  @override
  String get transferCompleteMessage => 'Prenos je završen! Sada možete reproducirati ovaj snimak.';

  @override
  String transferFailedMessage(String error) {
    return 'Prenos nije uspio: $error';
  }

  @override
  String get transferCancelled => 'Prenos je otkazan';

  @override
  String get fastTransferEnabled => 'Brzi prenos je omogućen';

  @override
  String get bluetoothSyncEnabled => 'Sinhronizacija preko Bluetootha je omogućena';

  @override
  String get enableFastTransfer => 'Omogući brzi prenos';

  @override
  String get fastTransferDescription =>
      'Brzi prenos koristi WiFi za ~5x brže brzine. Vaš telefon će se privremeno povezati na WiFi mrežu vašeg Omi uređaja tokom prenosa.';

  @override
  String get internetAccessPausedDuringTransfer => 'Pristup internetu je pauziran tokom prenosa';

  @override
  String get chooseTransferMethodDescription => 'Odaberite kako se snimci prenose sa vašeg Omi uređaja na vaš telefon.';

  @override
  String get wifiSpeed => '~150 KB/s preko WiFi-ja';

  @override
  String get fiveTimesFaster => '5X BRŽE';

  @override
  String get fastTransferMethodDescription =>
      'Kreira direktnu WiFi konekciju sa vašim Omi uređajem. Vaš telefon se privremeno odvaja od običnog WiFi-ja tokom prenosa.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s preko BLE-a';

  @override
  String get bluetoothMethodDescription =>
      'Koristi standardnu Bluetooth niskoenergijsku konekciju. Sporije, ali ne utiče na vašu WiFi konekciju.';

  @override
  String get selected => 'Odabrano';

  @override
  String get selectOption => 'Odaberi';

  @override
  String get lowBatteryAlertTitle => 'Upozorenje o niskoj bateriji';

  @override
  String get lowBatteryAlertBody => 'Vaš uređaj ima nisku bateriju. Vrijeme je za ponovno punjena! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Vaš Omi uređaj se odvojio';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Molimo da se ponovno povežete da biste nastavili sa korišćenjem vašeg Omi-ja.';

  @override
  String get firmwareUpdateAvailable => 'Dostupna je ažuriranja firmvera';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Nova ažuriranja firmvera ($version) je dostupna za vaš Omi uređaj. Želite li da ažurirate sada?';
  }

  @override
  String get later => 'Kasnije';

  @override
  String get appDeletedSuccessfully => 'Aplikacija je uspješno obrisana';

  @override
  String get appDeleteFailed => 'Greška pri brisanju aplikacije. Molimo pokušajte ponovo kasnije.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Vidljivost aplikacije je uspješno promijenjena. Može trebati nekoliko minuta da se promjena odrazi.';

  @override
  String get errorActivatingAppIntegration =>
      'Greška pri aktiviranju aplikacije. Ako je ovo aplikacija za integraciju, pazite da je setup završen.';

  @override
  String get errorUpdatingAppStatus => 'Greška pri ažuriranju statusa aplikacije.';

  @override
  String get calculatingETA => 'Izračunavanje...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Otprilike $minutes minuta preostaje';
  }

  @override
  String get aboutAMinuteRemaining => 'Otprilike jedna minuta preostaje';

  @override
  String get almostDone => 'Gotovo je...';

  @override
  String get omiSays => 'Omi kaže';

  @override
  String get analyzingYourData => 'Analiza vaših podataka u toku...';

  @override
  String migratingToProtection(String level) {
    return 'Migracija na $level zaštitu...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Nema podataka za migraciju. Finalizovanje...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migracija $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Svi objekti su migrirati. Finalizovanje...';

  @override
  String get migrationErrorOccurred => 'Greška je došlo do greške tokom migracije. Molimo pokušajte ponovo.';

  @override
  String get migrationComplete => 'Migracija je završena!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Vaši podaci su sada zaštićeni sa novim $level postavkama.';
  }

  @override
  String get chatsLowercase => 'razgovori';

  @override
  String get dataLowercase => 'podaci';

  @override
  String get fallNotificationTitle => 'Ups';

  @override
  String get fallNotificationBody => 'Jeste li pali?';

  @override
  String get importantConversationTitle => 'Važna razgovor';

  @override
  String get importantConversationBody => 'Upravo ste imali važnu razgovoru. Tapnite da dijeli sažetak sa ostalima.';

  @override
  String get templateName => 'Naziv šablona';

  @override
  String get templateNameHint => 'npr., Ekstraktor stavki za akciju sastanka';

  @override
  String get nameMustBeAtLeast3Characters => 'Naziv mora biti najmanje 3 karaktera';

  @override
  String get conversationPromptHint =>
      'npr., Izvucite stavke za akciju, donešene odluke i ključne zaključke iz datog razgovora.';

  @override
  String get pleaseEnterAppPrompt => 'Molimo unesite prompt za vašu aplikaciju';

  @override
  String get promptMustBeAtLeast10Characters => 'Prompt mora biti najmanje 10 karaktera';

  @override
  String get anyoneCanDiscoverTemplate => 'Bilo ko može otkriti vaš šablon';

  @override
  String get onlyYouCanUseTemplate => 'Samo vi možete koristiti ovaj šablon';

  @override
  String get generatingDescription => 'Pravljenje opisa...';

  @override
  String get creatingAppIcon => 'Pravljenje ikone aplikacije...';

  @override
  String get installingApp => 'Instalacija aplikacije...';

  @override
  String get appCreatedAndInstalled => 'Aplikacija je napravljena i instalirana!';

  @override
  String get appCreatedSuccessfully => 'Aplikacija je uspješno napravljena!';

  @override
  String get failedToCreateApp => 'Greška pri pravljenju aplikacije. Molimo pokušajte ponovo.';

  @override
  String get addAppSelectCoreCapability =>
      'Molimo odaberite jednu više osnovnu mogućnost za vašu aplikaciju da nastavite';

  @override
  String get addAppSelectPaymentPlan => 'Molimo odaberite plan plaćanja i unesite cijenu za vašu aplikaciju';

  @override
  String get addAppSelectCapability => 'Molimo odaberite najmanje jednu mogućnost za vašu aplikaciju';

  @override
  String get addAppSelectLogo => 'Molimo odaberite logotip za vašu aplikaciju';

  @override
  String get addAppEnterChatPrompt => 'Molimo unesite chat prompt za vašu aplikaciju';

  @override
  String get addAppEnterConversationPrompt => 'Molimo unesite conversation prompt za vašu aplikaciju';

  @override
  String get addAppSelectTriggerEvent => 'Molimo odaberite trigger event za vašu aplikaciju';

  @override
  String get addAppEnterWebhookUrl => 'Molimo unesite webhook URL za vašu aplikaciju';

  @override
  String get addAppSelectCategory => 'Molimo odaberite kategoriju za vašu aplikaciju';

  @override
  String get addAppFillRequiredFields => 'Molimo popunite sva obavezna polja ispravno';

  @override
  String get addAppUpdatedSuccess => 'Aplikacija je uspješno ažurirana 🚀';

  @override
  String get addAppUpdateFailed => 'Greška pri ažuriranju aplikacije. Molimo pokušajte ponovo kasnije';

  @override
  String get addAppSubmittedSuccess => 'Aplikacija je uspješno poslana 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Greška pri otvaranju file pickera: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Greška pri odabiru slike: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Dozvola za fotografije je odbijena. Molimo dozvolite pristup fotografijama da odaberete sliku';

  @override
  String get addAppErrorSelectingImageRetry => 'Greška pri odabiru slike. Molimo pokušajte ponovo.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Greška pri odabiru minijature: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Greška pri odabiru minijature. Molimo pokušajte ponovo.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Ostale mogućnosti ne mogu biti odabrane sa Persona';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Persona ne može biti odabrana sa ostalim mogućnostima';

  @override
  String get paymentFailedToFetchCountries =>
      'Greška pri učitavanju podržanih država. Molimo pokušajte ponovo kasnije.';

  @override
  String get paymentFailedToSetDefault =>
      'Greška pri postavljanju zadane metode plaćanja. Molimo pokušajte ponovo kasnije.';

  @override
  String get paymentFailedToSavePaypal => 'Greška pri čuvanju PayPal detalja. Molimo pokušajte ponovo kasnije.';

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
  String get paymentStatusNotConnected => 'Nije povezano';

  @override
  String get paymentAppCost => 'Cijena aplikacije';

  @override
  String get paymentEnterValidAmount => 'Molimo unesite važeću iznos';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Molimo unesite iznos veći od 0';

  @override
  String get paymentPlan => 'Plan plaćanja';

  @override
  String get paymentNoneSelected => 'Nije odabrano';

  @override
  String get aiGenPleaseEnterDescription => 'Molimo unesite opis za vašu aplikaciju';

  @override
  String get aiGenCreatingAppIcon => 'Pravljenje ikone aplikacije...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Greška je došla do greške: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplikacija je uspješno napravljena!';

  @override
  String get aiGenFailedToCreateApp => 'Greška pri pravljenju aplikacije';

  @override
  String get aiGenErrorWhileCreatingApp => 'Greška je došla do greške tokom pravljenja aplikacije';

  @override
  String get aiGenFailedToGenerateApp => 'Greška pri generisanju aplikacije. Molimo pokušajte ponovo.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Greška pri ponovnom generisanju ikone';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Molimo prvo generirajte aplikaciju';

  @override
  String get nextButton => 'Dalje';

  @override
  String get connectOmiDevice => 'Povežite Omi uređaj';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Prebacujete svoj Unlimited plan na $title. Jeste li sigurni da želite nastaviti?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Ažuriranja je zakazana! Vaš mjesečni plan se nastavlja do kraja vašeg perioda naplate, zatim se automatski prebacuje na godišnji.';

  @override
  String get couldNotSchedulePlanChange => 'Nije moguće zakazati promenu plana. Molimo pokušajte ponovo.';

  @override
  String get subscriptionReactivatedDefault =>
      'Vaša pretplata je reaktivirana! Nema naknade sada - biće vam naplaćeno na kraju vašeg trenutnog perioda.';

  @override
  String get subscriptionSuccessfulCharged => 'Pretplata je uspješna! Bačena vam je naplaćena za novi period naplate.';

  @override
  String get couldNotProcessSubscription => 'Nije moguće obraditi pretplatu. Molimo pokušajte ponovo.';

  @override
  String get couldNotLaunchUpgradePage => 'Nije moguće pokrenuti stranicu za ažuriranje. Molimo pokušajte ponovo.';

  @override
  String get transcriptionJsonPlaceholder => 'Zalijepite vašu JSON konfiguraciju ovdje...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Greška pri otvaranju file pickera: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Greška: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Razgovori su uspješno spojeni';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count razgovora su uspješno spojeni';
  }

  @override
  String get actionItemReminderTitle => 'Omi podsjetnik';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName je odvojen';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Molimo ponovno povežite da biste nastavili sa korišćenjem vašeg $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Prijava';

  @override
  String get onboardingYourName => 'Vaše ime';

  @override
  String get onboardingLanguage => 'Jezik';

  @override
  String get onboardingPermissions => 'Dozvole';

  @override
  String get onboardingComplete => 'Završeno';

  @override
  String get onboardingWelcomeToOmi => 'Dobrodošli u Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Reči nam o sebi';

  @override
  String get onboardingChooseYourPreference => 'Odaberite vašu preferencu';

  @override
  String get onboardingGrantRequiredAccess => 'Dozvoli potreban pristup';

  @override
  String get onboardingYoureAllSet => 'Sve je spremno';

  @override
  String get searchTranscriptOrSummary => 'Pretraži transkripciju ili sažetak...';

  @override
  String get myGoal => 'Moj cilj';

  @override
  String get appNotAvailable => 'Ups! Izgleda da aplikacija koju tražite nije dostupna.';

  @override
  String get failedToConnectTodoist => 'Greška pri povezivanju sa Todoist';

  @override
  String get failedToConnectAsana => 'Greška pri povezivanju sa Asana';

  @override
  String get failedToConnectGoogleTasks => 'Greška pri povezivanju sa Google Tasks';

  @override
  String get failedToConnectClickUp => 'Greška pri povezivanju sa ClickUp';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Greška pri povezivanju sa $serviceName: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Uspješno ste se povezali sa Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Greška pri povezivanju sa Todoist. Molimo pokušajte ponovo.';

  @override
  String get successfullyConnectedAsana => 'Uspješno ste se povezali sa Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Greška pri povezivanju sa Asana. Molimo pokušajte ponovo.';

  @override
  String get successfullyConnectedGoogleTasks => 'Uspješno ste se povezali sa Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Greška pri povezivanju sa Google Tasks. Molimo pokušajte ponovo.';

  @override
  String get successfullyConnectedClickUp => 'Uspješno ste se povezali sa ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Greška pri povezivanju sa ClickUp. Molimo pokušajte ponovo.';

  @override
  String get successfullyConnectedNotion => 'Uspješno ste se povezali sa Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Greška pri osvježavanju statusa Notion konekcije.';

  @override
  String get successfullyConnectedGoogle => 'Uspješno ste se povezali sa Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Greška pri osvježavanju statusa Google konekcije.';

  @override
  String get successfullyConnectedWhoop => 'Uspješno ste se povezali sa Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Greška pri osvježavanju statusa Whoop konekcije.';

  @override
  String get successfullyConnectedGitHub => 'Uspješno ste se povezali sa GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Greška pri osvježavanju statusa GitHub konekcije.';

  @override
  String get authFailedToSignInWithGoogle => 'Greška pri prijavi sa Google, molimo pokušajte ponovo.';

  @override
  String get authenticationFailed => 'Autentifikacija nije uspješna. Molimo pokušajte ponovo.';

  @override
  String get authFailedToSignInWithApple => 'Greška pri prijavi sa Apple, molimo pokušajte ponovo.';

  @override
  String get authFailedToRetrieveToken => 'Greška pri preuzimanju firebase token, molimo pokušajte ponovo.';

  @override
  String get authUnexpectedErrorFirebase => 'Neočekivana greška pri prijavi, Firebase greška, molimo pokušajte ponovo.';

  @override
  String get authUnexpectedError => 'Neočekivana greška pri prijavi, molimo pokušajte ponovo';

  @override
  String get authFailedToLinkGoogle => 'Greška pri povezivanju sa Google, molimo pokušajte ponovo.';

  @override
  String get authFailedToLinkApple => 'Greška pri povezivanju sa Apple, molimo pokušajte ponovo.';

  @override
  String get onboardingBluetoothRequired => 'Dozvola za Bluetooth je potrebna za povezivanje sa vašim uređajem.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Dozvola za Bluetooth je odbijena. Molimo dozvoli dozvolu u Postavkama sistema.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Status dozvole za Bluetooth: $status. Molimo provjerite Postavke sistema.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Greška pri provjeri dozvole za Bluetooth: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Dozvola za obavijesti je odbijena. Molimo dozvoli dozvolu u Postavkama sistema.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Dozvola za obavijesti je odbijena. Molimo dozvoli dozvolu u Postavkama sistema > Obavijesti.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Status dozvole za obavijesti: $status. Molimo provjerite Postavke sistema.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Greška pri provjeri dozvole za obavijesti: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Molimo dozvoli dozvolu za lokaciju u Postavkama > Privatnost i sigurnost > Lokacijske usluge';

  @override
  String get onboardingMicrophoneRequired => 'Dozvola za mikrofon je potrebna za snimanje.';

  @override
  String get onboardingMicrophoneDenied =>
      'Dozvola za mikrofon je odbijena. Molimo dozvoli dozvolu u Postavkama sistema > Privatnost i sigurnost > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Status dozvole za mikrofon: $status. Molimo provjerite Postavke sistema.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Greška pri provjeri dozvole za mikrofon: $error';
  }

  @override
  String get onboardingScreenCaptureRequired => 'Dozvola za snimanje ekrana je potrebna za snimanje sistemskog zvuka.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Dozvola za snimanje ekrana je odbijena. Molimo dozvoli dozvolu u Postavkama sistema > Privatnost i sigurnost > Snimanje ekrana.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Status dozvole za snimanje ekrana: $status. Molimo provjerite Postavke sistema.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Greška pri provjeri dozvole za snimanje ekrana: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Dozvola za pristupačnost je potrebna za detektovanje pregleda sa povezanog uređaja.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Status dozvole za pristupačnost: $status. Molimo provjerite Postavke sistema.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Greška pri provjeri dozvole za pristupačnost: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Snimanje kamerom nije dostupno na ovoj platformi';

  @override
  String get msgCameraPermissionDenied => 'Dozvola za kameru je odbijena. Molimo dozvoli pristup kameri';

  @override
  String msgCameraAccessError(String error) {
    return 'Greška pri pristupu kameri: $error';
  }

  @override
  String get msgPhotoError => 'Greška pri snimanju fotografije. Molimo pokušajte ponovo.';

  @override
  String get msgMaxImagesLimit => 'Možete odabrati samo do 4 slike';

  @override
  String msgFilePickerError(String error) {
    return 'Greška pri otvaranju file pickera: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Greška pri odabiru slika: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Dozvola za fotografije je odbijena. Molimo dozvoli pristup fotografijama da odaberete slike';

  @override
  String get msgSelectImagesGenericError => 'Greška pri odabiru slika. Molimo pokušajte ponovo.';

  @override
  String get msgMaxFilesLimit => 'Možete odabrati samo do 4 datoteke';

  @override
  String msgSelectFilesError(String error) {
    return 'Greška pri odabiru datoteka: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Greška pri odabiru datoteka. Molimo pokušajte ponovo.';

  @override
  String get msgUploadFileFailed => 'Greška pri učitavanju datoteke, molimo pokušajte ponovo kasnije';

  @override
  String get msgReadingMemories => 'Čitanje vaših uspomena u toku...';

  @override
  String get msgLearningMemories => 'Učenje iz vaših uspomena u toku...';

  @override
  String get msgUploadAttachedFileFailed => 'Greška pri učitavanju priložene datoteke.';

  @override
  String captureRecordingError(String error) {
    return 'Greška je došla do greške tokom snimanja: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Snimanje je zaustavljeno: $reason. Može biti potrebno ponovno pokrenuti vanjske prikaze ili ponovno pokrenuti snimanje.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Dozvola za mikrofon je potrebna';

  @override
  String get captureMicrophonePermissionInSystemPreferences => 'Dozvoli dozvolu za mikrofon u Postavkama sistema';

  @override
  String get captureScreenRecordingPermissionRequired => 'Dozvola za snimanje ekrana je potrebna';

  @override
  String get captureDisplayDetectionFailed => 'Detektovanje ekrana nije uspješno. Snimanje je zaustavljeno.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Nevažeći audio bytes webhook URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Nevažeći realtime transcript webhook URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Nevažeći conversation created webhook URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Nevažeći day summary webhook URL';

  @override
  String get devModeSettingsSaved => 'Postavke su čuvane!';

  @override
  String get voiceFailedToTranscribe => 'Greška pri transkribiranju zvuka';

  @override
  String get locationPermissionRequired => 'Dozvola za lokaciju je potrebna';

  @override
  String get locationPermissionContent =>
      'Brzi prenos zahtijeva dozvolu za lokaciju da provjeri WiFi konekciju. Molimo dozvoli dozvolu za lokaciju da nastavite.';

  @override
  String get pdfTranscriptExport => 'Izvoz transkripcije';

  @override
  String get pdfConversationExport => 'Izvoz razgovora';

  @override
  String pdfTitleLabel(String title) {
    return 'Naslov: $title';
  }

  @override
  String get conversationNewIndicator => 'Novo 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotografija';
  }

  @override
  String get mergingStatus => 'Spajanje u toku...';

  @override
  String timeSecsSingular(int count) {
    return '$count sek';
  }

  @override
  String timeSecsPlural(int count) {
    return '$count sekundi';
  }

  @override
  String timeMinSingular(int count) {
    return '$count min';
  }

  @override
  String timeMinsPlural(int count) {
    return '$count minuta';
  }

  @override
  String timeMinsAndSecs(int mins, int secs) {
    return '$mins minuta $secs sekundi';
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
    return '$hours sati $mins minuta';
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
  String get moveToFolder => 'Premjestite u mapu';

  @override
  String get noFoldersAvailable => 'Nema dostupnih mapa';

  @override
  String get newFolder => 'Nova mapa';

  @override
  String get color => 'Boja';

  @override
  String get waitingForDevice => 'Čekanje uređaja...';

  @override
  String get saySomething => 'Reči nešto...';

  @override
  String get initialisingSystemAudio => 'Inicijalizacija sistemskog zvuka';

  @override
  String get stopRecording => 'Zaustavi snimanje';

  @override
  String get continueRecording => 'Nastavi snimanje';

  @override
  String get initialisingRecorder => 'Inicijalizacija snimanja';

  @override
  String get pauseRecording => 'Pauziraj snimanje';

  @override
  String get resumeRecording => 'Nastavi snimanje';

  @override
  String get noDailyRecapsYet => 'Još nema dnevnih rezimea';

  @override
  String get dailyRecapsDescription => 'Vaši dnevni rezimei će se pojaviti ovdje nakon što se generiraju';

  @override
  String get chooseTransferMethod => 'Odaberite način prenosa';

  @override
  String get fastTransferSpeed => '~150 KB/s preko WiFi-ja';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Detektovan je veliki vremenski razmak ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Detektovani su veliki vremenski razmaci ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Uređaj ne podržava WiFi sinhronizaciju, prebacujem na Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health nije dostupan na ovom uređaju';

  @override
  String get downloadAudio => 'Preuzmi zvuk';

  @override
  String get audioDownloadSuccess => 'Zvuk je uspješno preuzet';

  @override
  String get audioDownloadFailed => 'Greška pri preuzimanju zvuka';

  @override
  String get downloadingAudio => 'Preuzimanje zvuka u toku...';

  @override
  String get shareAudio => 'Dijeli zvuk';

  @override
  String get preparingAudio => 'Pripremanje zvuka';

  @override
  String get gettingAudioFiles => 'Preuzimanje zvučnih datoteka u toku...';

  @override
  String get downloadingAudioProgress => 'Preuzimanje zvuka';

  @override
  String get processingAudio => 'Obrada zvuka';

  @override
  String get combiningAudioFiles => 'Kombinovanje zvučnih datoteka u toku...';

  @override
  String get audioReady => 'Zvuk je spreman';

  @override
  String get openingShareSheet => 'Otvaranje lista za dijeljenje...';

  @override
  String get audioShareFailed => 'Dijeljenje nije uspješno';

  @override
  String get dailyRecaps => 'Dnevni rezimei';

  @override
  String get removeFilter => 'Uklonite filter';

  @override
  String get categoryConversationAnalysis => 'Analiza razgovora';

  @override
  String get categoryHealth => 'Zdravlje';

  @override
  String get categoryEducation => 'Edukacija';

  @override
  String get categoryCommunication => 'Komunikacija';

  @override
  String get categoryEmotionalSupport => 'Emocionalna podrška';

  @override
  String get categoryProductivity => 'Produktivnost';

  @override
  String get categoryEntertainment => 'Zabava';

  @override
  String get categoryFinancial => 'Finansije';

  @override
  String get categoryTravel => 'Putovanje';

  @override
  String get categorySafety => 'Sigurnost';

  @override
  String get categoryShopping => 'Kupovine';

  @override
  String get categorySocial => 'Društveno';

  @override
  String get categoryNews => 'Vijesti';

  @override
  String get categoryUtilities => 'Komunalni servisi';

  @override
  String get categoryOther => 'Ostalo';

  @override
  String get capabilityChat => 'Chat';

  @override
  String get capabilityConversations => 'Razgovori';

  @override
  String get capabilityExternalIntegration => 'Vanjska integracija';

  @override
  String get capabilityNotification => 'Obavijest';

  @override
  String get triggerAudioBytes => 'Audio bajtovi';

  @override
  String get triggerConversationCreation => 'Kreiranje razgovora';

  @override
  String get triggerTranscriptProcessed => 'Transkripcija obrada';

  @override
  String get actionCreateConversations => 'Kreiraj razgovore';

  @override
  String get actionCreateMemories => 'Kreiraj uspomene';

  @override
  String get actionReadConversations => 'Pročitaj razgovore';

  @override
  String get actionReadMemories => 'Pročitaj uspomene';

  @override
  String get actionReadTasks => 'Pročitaj zadatke';

  @override
  String get scopeUserName => 'Korisničko ime';

  @override
  String get scopeUserFacts => 'Korisničke činjenice';

  @override
  String get scopeUserConversations => 'Korisni razgovori';

  @override
  String get scopeUserChat => 'Korisnički chat';

  @override
  String get capabilitySummary => 'Sažetak';

  @override
  String get capabilityFeatured => 'Istaknuto';

  @override
  String get capabilityTasks => 'Zadaci';

  @override
  String get capabilityIntegrations => 'Integracije';

  @override
  String get categoryProductivityLifestyle => 'Produktivnost i stil života';

  @override
  String get categorySocialEntertainment => 'Društveno i zabava';

  @override
  String get categoryProductivityTools => 'Produktivnost i alati';

  @override
  String get categoryPersonalWellness => 'Lično i lifestyle';

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
  String get resetFilters => 'Resetuj filtere';

  @override
  String get applyFilters => 'Primeni filtere';

  @override
  String get mostInstalls => 'Najveći broj instalacija';

  @override
  String get couldNotOpenUrl => 'Nije moguće otvoriti URL. Pokušajte ponovo.';

  @override
  String get newTask => 'Novi zadatak';

  @override
  String get viewAll => 'Prikaži sve';

  @override
  String get addTask => 'Dodaj zadatak';

  @override
  String get addMcpServer => 'Dodaj MCP server';

  @override
  String get connectExternalAiTools => 'Poveži eksterne AI alate';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return '$count alata uspešno povezano';
  }

  @override
  String get mcpConnectionFailed => 'Nije uspelo povezivanje na MCP server';

  @override
  String get authorizingMcpServer => 'Autorizacija u toku...';

  @override
  String get whereDidYouHearAboutOmi => 'Kako ste saznali za nas?';

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
  String get otherSource => 'Drugo';

  @override
  String get pleaseSpecify => 'Molim specificite';

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
  String get iveDoneThis => 'Već sam ovo završio/a';

  @override
  String get pairNewDevice => 'Upari novi uređaj';

  @override
  String get dontSeeYourDevice => 'Ne vidite vaš uređaj?';

  @override
  String get reportAnIssue => 'Prijavi problem';

  @override
  String get pairingTitleOmi => 'Uključi Omi';

  @override
  String get pairingDescOmi => 'Drži uređaj pritisnuo/a dok se ne vibrira da bi ga uključio/a.';

  @override
  String get pairingTitleOmiDevkit => 'Postavi Omi DevKit u režim uparivanja';

  @override
  String get pairingDescOmiDevkit =>
      'Pritisni dugme jednom da uključiš. LED će treperiti ljubičasto kada je u režimu uparivanja.';

  @override
  String get pairingTitleOmiGlass => 'Uključi Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Uključi pritiskivanjem bočnog dugmeta 3 sekunde.';

  @override
  String get pairingTitlePlaudNote => 'Postavi Plaud Note u režim uparivanja';

  @override
  String get pairingDescPlaudNote =>
      'Drži bočno dugme 2 sekunde. Crveni LED će treperiti kada je spreman za uparivanje.';

  @override
  String get pairingTitleBee => 'Postavi Bee u režim uparivanja';

  @override
  String get pairingDescBee => 'Pritisni dugme 5 puta bez prekida. Svetlo će početi treperitati plavo i zeleno.';

  @override
  String get pairingTitleLimitless => 'Postavi Limitless u režim uparivanja';

  @override
  String get pairingDescLimitless =>
      'Kada je neko svetlo vidljivo, pritisni jednom, a zatim drži dok uređaj ne prikaže ružičasto svetlo, zatim otpusti.';

  @override
  String get pairingTitleFriendPendant => 'Postavi Friend Pendant u režim uparivanja';

  @override
  String get pairingDescFriendPendant =>
      'Pritisni dugme na privescu da ga uključiš. Automatski će ući u režim uparivanja.';

  @override
  String get pairingTitleFieldy => 'Postavi Fieldy u režim uparivanja';

  @override
  String get pairingDescFieldy => 'Drži uređaj pritisnuo/a dok se svetlo ne pojavi da bi ga uključio/a.';

  @override
  String get pairingTitleAppleWatch => 'Poveži Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Instaliraj i otvori Omi aplikaciju na Apple Watch-u, zatim dotakni Poveži u aplikaciji.';

  @override
  String get pairingTitleNeoOne => 'Postavi Neo One u režim uparivanja';

  @override
  String get pairingDescNeoOne => 'Drži dugme za napajanje dok LED ne počne treperitati. Uređaj će biti otkrivljiv.';

  @override
  String get downloadingFromDevice => 'Preuzimanje sa uređaja';

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
  String get noPendingRecordings => 'Nema snimljenih zapisa na čekanju';

  @override
  String get noProcessedRecordings => 'Nema obrađenih snimljenih zapisa';

  @override
  String get pending => 'Na čekanju';

  @override
  String whatsNewInVersion(String version) {
    return 'Šta je novo u verziji $version';
  }

  @override
  String get addToYourTaskList => 'Dodaj u listu zadataka?';

  @override
  String get failedToCreateShareLink => 'Nije uspelo pravljenje linka za deljenje';

  @override
  String get deleteGoal => 'Obriši cilj';

  @override
  String get deviceUpToDate => 'Vaš uređaj je ažuran';

  @override
  String get wifiConfiguration => 'WiFi konfiguracija';

  @override
  String get wifiConfigurationSubtitle => 'Unesite vaše WiFi kredencijale kako bi uređaj mogao preuzeti firmware.';

  @override
  String get networkNameSsid => 'Ime mreže (SSID)';

  @override
  String get enterWifiNetworkName => 'Unesite ime WiFi mreže';

  @override
  String get enterWifiPassword => 'Unesite WiFi lozinku';

  @override
  String get appIconLabel => 'Ikona aplikacije';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Evo šta znam o vama';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Ova mapa se ažurira kako Omi uči iz vaših razgovora.';

  @override
  String get apiEnvironment => 'API okruženje';

  @override
  String get apiEnvironmentDescription => 'Odaberite koji backend da se konektuje';

  @override
  String get production => 'Produkcija';

  @override
  String get staging => 'Staging';

  @override
  String get switchRequiresRestart => 'Prebacivanje zahteva ponovno pokretanje aplikacije';

  @override
  String get switchApiConfirmTitle => 'Promeni API okruženje';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Prebaciti se na $environment? Trebate da zatvorite i ponovo otvorite aplikaciju kako bi se izmene primenile.';
  }

  @override
  String get switchAndRestart => 'Prebaci';

  @override
  String get stagingDisclaimer =>
      'Staging može biti buggy, imati neusaglašene performanse i podaci mogu biti izgubljeni. Koristite samo za testiranje.';

  @override
  String get apiEnvSavedRestartRequired => 'Sačuvano. Zatvorite i ponovo otvorite aplikaciju da se primene izmene.';

  @override
  String get shared => 'Deljeno';

  @override
  String get onlyYouCanSeeConversation => 'Samo vi možete videti ovaj razgovor';

  @override
  String get anyoneWithLinkCanView => 'Svako sa linkom može videti';

  @override
  String get tasksCleanTodayTitle => 'Očisti današnje zadatke?';

  @override
  String get tasksCleanTodayMessage => 'Ovo će samo ukloniti rokove';

  @override
  String get tasksOverdue => 'Prosječni rok';

  @override
  String get phoneCallsWithOmi => 'Pozivi sa Omi-em';

  @override
  String get phoneCallsSubtitle => 'Pozivaj sa transkribovanjem u realnom vremenu';

  @override
  String get phoneSetupStep1Title => 'Verifikuj svoj telefonski broj';

  @override
  String get phoneSetupStep1Subtitle => 'Poslacemo ti poziv da potvrdi da je tvoj';

  @override
  String get phoneSetupStep2Title => 'Unesite verifikacioni kod';

  @override
  String get phoneSetupStep2Subtitle => 'Kratak kod koji ćete uneti tokom poziva';

  @override
  String get phoneSetupStep3Title => 'Počni da poziva svoje kontakte';

  @override
  String get phoneSetupStep3Subtitle => 'Sa transkribovanjem u živo uključenim';

  @override
  String get phoneGetStarted => 'Počni';

  @override
  String get callRecordingConsentDisclaimer => 'Snimanje poziva može zahtevati pristanak u vašoj jurisdikciji';

  @override
  String get enterYourNumber => 'Unesite svoj broj';

  @override
  String get phoneNumberCallerIdHint => 'Nakon verifikacije, ovo postaje vaš caller ID';

  @override
  String get phoneNumberHint => 'Telefonski broj';

  @override
  String get failedToStartVerification => 'Nije uspelo pokretanje verifikacije';

  @override
  String get phoneContinue => 'Nastavi';

  @override
  String get verifyYourNumber => 'Verifikuj svoj broj';

  @override
  String get answerTheCallFrom => 'Odgovori na poziv sa';

  @override
  String get onTheCallEnterThisCode => 'Tokom poziva, unesite ovaj kod';

  @override
  String get followTheVoiceInstructions => 'Slijedi glasovne instrukcije';

  @override
  String get statusCalling => 'Pozivanje...';

  @override
  String get statusCallInProgress => 'Poziv u toku';

  @override
  String get statusVerifiedLabel => 'Verifikovano';

  @override
  String get statusCallMissed => 'Poziv propušten';

  @override
  String get statusTimedOut => 'Vreme je isteklo';

  @override
  String get phoneTryAgain => 'Pokušaj ponovo';

  @override
  String get phonePageTitle => 'Telefon';

  @override
  String get phoneContactsTab => 'Kontakti';

  @override
  String get phoneKeypadTab => 'Tastatura';

  @override
  String get grantContactsAccess => 'Dozvoli pristup tvojim kontaktima';

  @override
  String get phoneAllow => 'Dozvoli';

  @override
  String get phoneSearchHint => 'Pretraga';

  @override
  String get phoneNoContactsFound => 'Nisu pronađeni kontakti';

  @override
  String get phoneEnterNumber => 'Unesite broj';

  @override
  String get failedToStartCall => 'Nije uspelo pokretanje poziva';

  @override
  String get callStateConnecting => 'Povezivanje...';

  @override
  String get callStateRinging => 'Pozivanje...';

  @override
  String get callStateEnded => 'Poziv je završen';

  @override
  String get callStateFailed => 'Poziv nije uspio';

  @override
  String get transcriptPlaceholder => 'Transkript će se pojaviti ovde...';

  @override
  String get phoneUnmute => 'Uključi zvuk';

  @override
  String get phoneMute => 'Isključi zvuk';

  @override
  String get phoneSpeaker => 'Zvučnik';

  @override
  String get phoneEndCall => 'Završi';

  @override
  String get phoneCallSettingsTitle => 'Podešavanja telefonskih poziva';

  @override
  String get showPhoneCallButtonTitle => 'Prikaži dugme za pozive';

  @override
  String get showPhoneCallButtonDesc => 'Prikaži dugme za pozive na početnom ekranu';

  @override
  String get yourVerifiedNumbers => 'Tvoji verifikovani brojevi';

  @override
  String get verifiedNumbersDescription => 'Kada pozoveš nekoga, oni će videti ovaj broj na svom telefonu';

  @override
  String get noVerifiedNumbers => 'Nema verifikovanih brojeva';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Obriši $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Trebace da ponovo verifikuješ da bi pozivao/a';

  @override
  String get phoneDeleteButton => 'Obriši';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Verifikovano pre ${minutes}m';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Verifikovano pre ${hours}h';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Verifikovano pre ${days}d';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Verifikovano $date';
  }

  @override
  String get verifiedFallback => 'Verifikovano';

  @override
  String get callAlreadyInProgress => 'Poziv je već u toku';

  @override
  String get failedToGetCallToken => 'Nije uspelo dobijanje token za poziv. Prvo verifikuj svoj telefonski broj.';

  @override
  String get failedToInitializeCallService => 'Nije uspelo inicijalizovanje servisa za pozive';

  @override
  String get speakerLabelYou => 'Vi';

  @override
  String get speakerLabelUnknown => 'Nepoznato';

  @override
  String get showDailyScoreOnHomepage => 'Prikaži dnevni rezultat na početnoj strani';

  @override
  String get showTasksOnHomepage => 'Prikaži zadatke na početnoj strani';

  @override
  String get phoneCallsUnlimitedOnly => 'Pozivi preko Omi-a';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Pozivaj preko Omi-a i dobij transkribovanje u realnom vremenu, automatske rezime i još mnogo toga. Dostupno isključivo pretplatnicima Unlimited plana.';

  @override
  String get phoneCallsUpsellFeature1 => 'Transkribovanje u realnom vremenu svakog poziva';

  @override
  String get phoneCallsUpsellFeature2 => 'Automatski rezimei poziva i stavke akcije';

  @override
  String get phoneCallsUpsellFeature3 => 'Primaoci vide vaš pravi broj, ne nasumičan';

  @override
  String get phoneCallsUpsellFeature4 => 'Vaši pozivi ostaju privatni i bezbedni';

  @override
  String get phoneCallsUpgradeButton => 'Nadgradi se na Unlimited';

  @override
  String get phoneCallsMaybeLater => 'Možda kasnije';

  @override
  String get deleteSynced => 'Obriši sinhronizovano';

  @override
  String get deleteSyncedFiles => 'Obriši sinhronizovane snimke';

  @override
  String get deleteSyncedFilesMessage =>
      'Ove snimke su već sinhronizovane sa tvojim telefonom. Ovo se ne može vratiti.';

  @override
  String get syncedFilesDeleted => 'Sinhronizovane snimke su obrisane';

  @override
  String get deletePending => 'Obriši na čekanju';

  @override
  String get deletePendingFiles => 'Obriši snimke na čekanju';

  @override
  String get deletePendingFilesWarning =>
      'Ove snimke NISU sinhronizovane sa tvojim telefonom i biće zauvek izgubljene. Ovo se ne može vratiti.';

  @override
  String get pendingFilesDeleted => 'Snimke na čekanju su obrisane';

  @override
  String get deleteAllFiles => 'Obriši sve snimke';

  @override
  String get deleteAll => 'Obriši sve';

  @override
  String get deleteAllFilesWarning =>
      'Ovo će obrisati i sinhronizovane i snimke na čekanju. Snimke na čekanju NISU sinhronizovane i biće zauvek izgubljene. Ovo se ne može vratiti.';

  @override
  String get allFilesDeleted => 'Sve snimke su obrisane';

  @override
  String nFiles(int count) {
    return '$count snimaka';
  }

  @override
  String get manageStorage => 'Upravljaj memorijom';

  @override
  String get safelyBackedUp => 'Bezbedno sačuvano na vašem telefonu';

  @override
  String get notYetSynced => 'Nije još sinhronizovano sa tvojim telefonom';

  @override
  String get clearAll => 'Očisti sve';

  @override
  String get phoneKeypad => 'Tastatura';

  @override
  String get phoneHideKeypad => 'Sakrij tastaturu';

  @override
  String get fairUsePolicy => 'Fer upotreba';

  @override
  String get fairUseLoadError => 'Nije moguće učitati status fer upotrebe. Pokušajte ponovo.';

  @override
  String get fairUseStatusNormal => 'Vaša upotreba je u normalnim granicama.';

  @override
  String get fairUseStageNormal => 'Normalno';

  @override
  String get fairUseStageWarning => 'Upozorenje';

  @override
  String get fairUseStageThrottle => 'Usporeno';

  @override
  String get fairUseStageRestrict => 'Ograničeno';

  @override
  String get fairUseSpeechUsage => 'Upotreba govora';

  @override
  String get fairUseToday => 'Danas';

  @override
  String get fairUse3Day => '3-dnevna klizanja';

  @override
  String get fairUseWeekly => 'Sedmična klizanja';

  @override
  String get fairUseAboutTitle => 'O fer upotrebi';

  @override
  String get fairUseAboutBody =>
      'Omi je dizajniran za lične razgovore, sastanke i živu interakciju. Upotreba se meri vremenom stvarnog govora koji je detektovan, ne vremenom konekcije. Ako upotreba značajno prelazi normalne obrasce za ne-lični sadržaj, mogu se primeniti prilagođavanja.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef kopiran';
  }

  @override
  String get fairUseDailyTranscription => 'Dnevno transkribovanje';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'Dnevna granica transkribovanja je dostignutna';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Resetuje se $time';
  }

  @override
  String get transcriptionPaused => 'Snimanje, ponovno povezivanje';

  @override
  String get transcriptionPausedReconnecting => 'Još uvek se snima — ponovno povezivanje na transkribovanje...';

  @override
  String fairUseBannerStatus(String status) {
    return 'Fer upotreba: $status';
  }

  @override
  String get improveConnectionTitle => 'Poboljšaj konekciju';

  @override
  String get improveConnectionContent =>
      'Poboljšali smo kako Omi ostaje povezan sa vašim uređajem. Da biste ovo aktivirali, molim vas da idete na stranicu Informacije o uređaju, dodirnete \"Otkačite uređaj\", a zatim ponovo uparite vaš uređaj.';

  @override
  String get improveConnectionAction => 'Shvaćeno';

  @override
  String clockSkewWarning(int minutes) {
    return 'Sat vašeg uređaja je pogrešan za ~$minutes min. Proverite vaše podešavanja datuma i vremena.';
  }

  @override
  String get omisStorage => 'Memorija Omi-ja';

  @override
  String get phoneStorage => 'Memorija telefona';

  @override
  String get cloudStorage => 'Cloud memorija';

  @override
  String get howSyncingWorks => 'Kako sinhronizovanje funkcionira';

  @override
  String get noSyncedRecordings => 'Nema sinhronizovanih snimaka';

  @override
  String get recordingsSyncAutomatically => 'Snimke se sinhronizuju automatski — nema potrebe za akcijom.';

  @override
  String get filesDownloadedUploadedNextTime => 'Datoteke koje su već preuzete biće učitane sledeći put.';

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
  String get tapToView => 'Dodirnite da vidite';

  @override
  String get syncFailed => 'Sinhronizovanje nije uspelo';

  @override
  String get keepSyncing => 'Nastavi sinhronizovanje';

  @override
  String get cancelSyncQuestion => 'Otkaži sinhronizovanje?';

  @override
  String get omisStorageDesc =>
      'Kada vaš Omi nije povezan sa vašim telefonom, čuva audio lokalno na svojoj ugrađenoj memoriji. Nikada ne gubite snimak.';

  @override
  String get phoneStorageDesc =>
      'Kada se Omi ponovo poveže, snimke se automatski prenose na vaš telefon kao privremena oblast čuvanja pre učitavanja.';

  @override
  String get cloudStorageDesc =>
      'Nakon učitavanja, vaše snimke se obrađuju i transkribuju. Razgovori će biti dostupni u roku od minute.';

  @override
  String get tipKeepPhoneNearby => 'Čuvajte telefon blizu za brže sinhronizovanje';

  @override
  String get tipStableInternet => 'Stabilni internet ubrzava cloud učitavanja';

  @override
  String get tipAutoSync => 'Snimke se sinhronizuju automatski';

  @override
  String get storageSection => 'MEMORIJA';

  @override
  String get permissions => 'Dozvole';

  @override
  String get permissionEnabled => 'Omogućeno';

  @override
  String get permissionEnable => 'Omogući';

  @override
  String get permissionsPageDescription =>
      'Ove dozvole su jezgro kako Omi funkcionira. One omogućavaju ključne funkcije poput obaveštenja, iskustava zasnovanih na lokaciji i hvatanja zvuka.';

  @override
  String get permissionsRequiredDescription =>
      'Omi treba nekoliko dozvola da funkcionira pravilno. Molim vas da ih odobrite da biste nastavili.';

  @override
  String get permissionsSetupTitle => 'Uži najbolje iskustvo';

  @override
  String get permissionsSetupDescription => 'Omogući nekoliko dozvola kako bi Omi mogao da radi svoju magiju.';

  @override
  String get permissionsChangeAnytime => 'Možete promeniti ove dozvole bilo kada u Postavke > Dozvole';

  @override
  String get location => 'Lokacija';

  @override
  String get microphone => 'Mikrofon';

  @override
  String get whyAreYouCanceling => 'Zašto otkazuješ?';

  @override
  String get cancelReasonSubtitle => 'Možete li nam reći zašto odlazite?';

  @override
  String get cancelReasonTooExpensive => 'Preskupo';

  @override
  String get cancelReasonNotUsing => 'Nije dovoljno koristi';

  @override
  String get cancelReasonMissingFeatures => 'Nedostaju funkcije';

  @override
  String get cancelReasonAudioQuality => 'Kvaliteta zvuka/transkribovanja';

  @override
  String get cancelReasonBatteryDrain => 'Zabrinutost zbog drenaže baterije';

  @override
  String get cancelReasonFoundAlternative => 'Pronašao/a sam alternativu';

  @override
  String get cancelReasonOther => 'Drugo';

  @override
  String get tellUsMore => 'Reci nam više (opciono)';

  @override
  String get cancelReasonDetailHint => 'Cenimo svaki povratnu informaciju...';

  @override
  String get justAMoment => 'Čekaj malo';

  @override
  String get cancelConsequencesSubtitle => 'Toplo preporučujemo da umesto otkazivanja istražite druge opcije.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Vaš plan će ostati aktivan do $date. Nakon toga, biće prebačeni na besplatnu verziju sa ograničenim mogućnostima.';
  }

  @override
  String get ifYouCancel => 'Ako otkazuješ:';

  @override
  String get cancelConsequenceNoAccess => 'Više nema neograničenog pristupa na kraju vašeg perioda naplate.';

  @override
  String get cancelConsequenceBattery => '7 puta više baterije (obrada na uređaju)';

  @override
  String get cancelConsequenceQuality => '30% niža kvaliteta transkribovanja (modeli na uređaju)';

  @override
  String get cancelConsequenceDelay => 'Kašnjenje od 5-7 sekundi obrade (modeli na uređaju)';

  @override
  String get cancelConsequenceSpeakers => 'Ne mogu identificirati govornike.';

  @override
  String get confirmAndCancel => 'Potvrdi i otkaži';

  @override
  String get cancelConsequencePhoneCalls => 'Nema transkribovanja telefonskih poziva u realnom vremenu';

  @override
  String get feedbackTitleTooExpensive => 'Koja cena bi vam odgovarala?';

  @override
  String get feedbackTitleMissingFeatures => 'Koje funkcije vam nedostaju?';

  @override
  String get feedbackTitleAudioQuality => 'Kakve probleme ste iskusili?';

  @override
  String get feedbackTitleBatteryDrain => 'Reci nam o problemima sa baterijom';

  @override
  String get feedbackTitleFoundAlternative => 'Na šta prelazite?';

  @override
  String get feedbackTitleNotUsing => 'Šta bi vas učinilo da više koristite Omi?';

  @override
  String get feedbackSubtitleTooExpensive => 'Vaša povratna informacija nam pomaže da nađemo pravi balans.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Uvek gradimo — ovo nam pomaže da damo prioritet.';

  @override
  String get feedbackSubtitleAudioQuality => 'Voljeli bismo da razumemo šta je pošlo naopako.';

  @override
  String get feedbackSubtitleBatteryDrain => 'Ovo pomaže našem hardware timu da se poboljša.';

  @override
  String get feedbackSubtitleFoundAlternative => 'Voljeli bismo da saznamo šta vam se dopalo.';

  @override
  String get feedbackSubtitleNotUsing => 'Želimo da učinimo Omi korisnijim za vas.';

  @override
  String get deviceDiagnostics => 'Dijagnostika uređaja';

  @override
  String get signalStrength => 'Jačina signala';

  @override
  String get connectionUptime => 'Vreme aktivnosti';

  @override
  String get reconnections => 'Ponovno povezivanja';

  @override
  String get disconnectHistory => 'Istorija prekida veze';

  @override
  String get noDisconnectsRecorded => 'Nema zabeleženih prekida veze';

  @override
  String get diagnostics => 'Dijagnostika';

  @override
  String get waitingForData => 'Čekanja na podatke...';

  @override
  String get liveRssiOverTime => 'Live RSSI tokom vremena';

  @override
  String get noRssiDataYet => 'Nema RSSI podataka';

  @override
  String get collectingData => 'Prikupljanje podataka...';

  @override
  String get cleanDisconnect => 'Čist prekid veze';

  @override
  String get connectionTimeout => 'Timeout konekcije';

  @override
  String get remoteDeviceTerminated => 'Udaljeni uređaj prekinuo';

  @override
  String get pairedToAnotherPhone => 'Uparen sa drugim telefonom';

  @override
  String get linkKeyMismatch => 'Nepodudaranje kljuca veze';

  @override
  String get connectionFailed => 'Konekcija nije uspela';

  @override
  String get appClosed => 'Aplikacija zatvorena';

  @override
  String get manualDisconnect => 'Ručan prekid veze';

  @override
  String lastNEvents(int count) {
    return 'Poslednjih $count dogođaja';
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
  String get fair => 'Dobar';

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
  String get week => 'Sedmica';

  @override
  String get rollbackToStableFirmware => 'Vrati se na stabilnu firmware';

  @override
  String get rollbackConfirmTitle => 'Vrati firmware?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'Ovo će zameniti vašu trenutnu firmware sa najnovijom stabilnom verzijom ($version). Vaš uređaj će se ponovo pokrenuti nakon ažuriranja.';
  }

  @override
  String get stableFirmware => 'Stabilna firmware';

  @override
  String get fetchingStableFirmware => 'Preuzimanje najnovije stabilne firmware...';

  @override
  String get noStableFirmwareFound => 'Nije moguće pronaći stabilnu verziju firmware za vaš uređaj.';

  @override
  String get installStableFirmware => 'Instaliraj stabilnu firmware';

  @override
  String get alreadyOnStableFirmware => 'Već ste na najnovijoj stabilnoj verziji.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration zvuka sačuvano lokalno';
  }

  @override
  String get willSyncAutomatically => 'će se sinhronizovati automatski';

  @override
  String get enableLocationTitle => 'Omogući lokaciju';

  @override
  String get enableLocationDescription =>
      'Dozvola za lokaciju je potrebna da se pronađe obližnjim Bluetooth uređajima.';

  @override
  String get voiceRecordingFound => 'Snimak pronađen';

  @override
  String get transcriptionConnecting => 'Povezivanje transkribovanja...';

  @override
  String get transcriptionReconnecting => 'Ponovno povezivanje transkribovanja...';

  @override
  String get transcriptionUnavailable => 'Transkribovanje nije dostupno';

  @override
  String get audioOutput => 'Zvučni izlaz';

  @override
  String get firmwareWarningTitle => 'Važno: Pročitajte prije ažuriranja';

  @override
  String get firmwareFormatWarning =>
      'Ovaj firmware će formatirati SD karticu. Molimo osigurajte da su svi offline podaci sinhronizovani prije nadogradnje.\n\nAko vidite trepćuće crveno svjetlo nakon instaliranja ove verzije, ne brinite. Jednostavno povežite uređaj s aplikacijom i trebao bi postati plav. Crveno svjetlo znači da sat uređaja još nije sinhronizovan.';

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
      'Omi pristupa Apple Health-u preko Appleovog HealthKit okvira. Pristup možete opozvati u bilo kojem trenutku u iOS postavkama.';

  @override
  String get appleHealthConnectCta => 'Poveži s Apple Health';

  @override
  String get appleHealthDisconnectCta => 'Prekini vezu s Apple Health';

  @override
  String get appleHealthConnectedBadge => 'Povezano';

  @override
  String get appleHealthFeatureChatTitle => 'Razgovarajte o svom zdravlju';

  @override
  String get appleHealthFeatureChatDesc => 'Pitajte Omi o vašim koracima, snu, otkucajima srca i treninzima.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Samo za čitanje';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi nikada ne upisuje u Apple Health niti mijenja vaše podatke.';

  @override
  String get appleHealthFeatureSecureTitle => 'Sigurna sinhronizacija';

  @override
  String get appleHealthFeatureSecureDesc => 'Vaši Apple Health podaci se privatno sinhroniziraju s vašim Omi računom.';

  @override
  String get appleHealthDeniedTitle => 'Pristup Apple Health-u je odbijen';

  @override
  String get appleHealthDeniedBody =>
      'Omi nema dozvolu za čitanje vaših Apple Health podataka. Omogućite ga u iOS Postavke → Privatnost i sigurnost → Health → Omi.';

  @override
  String get deleteFlowReasonTitle => 'Zašto odlazite?';

  @override
  String get deleteFlowReasonSubtitle => 'Vaše povratne informacije pomažu nam da Omi bude bolji za sve.';

  @override
  String get deleteReasonPrivacy => 'Brige o privatnosti';

  @override
  String get deleteReasonNotUsing => 'Ne koristim dovoljno često';

  @override
  String get deleteReasonMissingFeatures => 'Nedostaju funkcije koje trebam';

  @override
  String get deleteReasonTechnicalIssues => 'Previše tehničkih problema';

  @override
  String get deleteReasonFoundAlternative => 'Koristim nešto drugo';

  @override
  String get deleteReasonTakingBreak => 'Samo pravim pauzu';

  @override
  String get deleteReasonOther => 'Ostalo';

  @override
  String get deleteFlowFeedbackTitle => 'Recite nam više';

  @override
  String get deleteFlowFeedbackSubtitle => 'Šta bi učinilo da Omi radi za vas?';

  @override
  String get deleteFlowFeedbackHint => 'Opcionalno — vaše misli nam pomažu da napravimo bolji proizvod.';

  @override
  String get deleteFlowConfirmTitle => 'Ovo je trajno';

  @override
  String get deleteFlowConfirmSubtitle => 'Nakon brisanja računa nije ga moguće vratiti.';

  @override
  String get deleteConsequenceSubscription => 'Svaka aktivna pretplata će biti otkazana.';

  @override
  String get deleteConsequenceNoRecovery => 'Vaš račun se ne može vratiti — čak ni preko podrške.';

  @override
  String get deleteTypeToConfirm => 'Upišite DELETE za potvrdu';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'Trajno obriši račun';

  @override
  String get keepMyAccount => 'Zadrži moj račun';

  @override
  String get deleteAccountFailed => 'Brisanje vašeg računa nije uspjelo. Pokušajte ponovo.';

  @override
  String get planUpdate => 'Ažuriranje plana';

  @override
  String get planDeprecationMessage =>
      'Vaš Unlimited plan se ukida. Pređite na Operator plan — iste odlične funkcije za \$49/mj. Vaš trenutni plan će nastaviti raditi u međuvremenu.';

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
    return '$used od $limit budžeta korišteno';
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
  String get chatLimitReachedUpgrade => 'Limit chata dostignut. Nadogradite za više poruka.';

  @override
  String get chatLimitReachedTitle => 'Limit chata dostignut';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Koristili ste $used od $limitDisplay na planu $plan.';
  }

  @override
  String resetsInDays(int count) {
    return 'Resetuje se za $count dana';
  }

  @override
  String resetsInHours(int count) {
    return 'Resetuje se za $count sati';
  }

  @override
  String get resetsSoon => 'Uskoro se resetuje';

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
  String get architectSubtitle => 'Napredni AI — hiljade razgovora + agentna automatizacija';

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
  String get voiceResponseAudio => 'Pročitaj Omi odgovor naglas';

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
  String get recordWithPhoneMic => 'Snimaj mikrofonom telefona';

  @override
  String get recordWithPhoneMicSubtitle => 'Snimite zvuk oko vas';

  @override
  String get phoneCall => 'Telefonski poziv';

  @override
  String get phoneCallSubtitle => 'Snimajte poziv s transkripcijom uživo';

  @override
  String get searchActionItems => 'Pretraži akcione stavke';

  @override
  String get selectActionItems => 'Odaberi više';

  @override
  String chooseExportDestination(int count) {
    return 'Izvezi $count stavku/i u…';
  }

  @override
  String get bulkExportInProgress => 'Izvoz u toku…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Izvezeno $count u $platform';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Izvezeno $success od $total u $platform';
  }

  @override
  String get showCompletedTasks => 'Prikaži završene';

  @override
  String get hideCompletedTasks => 'Sakrij završene';

  @override
  String get selectAllTasksMenu => 'Odaberi sve';

  @override
  String get connectTaskAppToExport => 'Povežite aplikaciju za zadatke u Postavkama za izvoz';

  @override
  String get connectAction => 'Poveži';

  @override
  String get deselectAllTasksMenu => 'Poništi odabir svih';
}
