// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Slovenian (`sl`).
class AppLocalizationsSl extends AppLocalizations {
  AppLocalizationsSl([String locale = 'sl']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Pogovor';

  @override
  String get transcriptTab => 'Prepis';

  @override
  String get actionItemsTab => 'Akcijski predmeti';

  @override
  String get deleteConversationTitle => 'Izbriši pogovor?';

  @override
  String get deleteConversationMessage =>
      'To bo tudi izbrisalo povezane spomine, naloge in zvočne datoteke. To dejanje ni mogoče razveljaviti.';

  @override
  String get confirm => 'Potrdi';

  @override
  String get cancel => 'Prekliči';

  @override
  String get ok => 'V redu';

  @override
  String get delete => 'Izbriši';

  @override
  String get add => 'Dodaj';

  @override
  String get update => 'Posodobi';

  @override
  String get save => 'Shrani';

  @override
  String get edit => 'Uredi';

  @override
  String get close => 'Zapri';

  @override
  String get clear => 'Počisti';

  @override
  String get copyTranscript => 'Kopiraj prepis';

  @override
  String get copySummary => 'Kopiraj povzetek';

  @override
  String get testPrompt => 'Testiraj poziv';

  @override
  String get reprocessConversation => 'Ponovno obdelaj pogovor';

  @override
  String get deleteConversation => 'Izbriši pogovor';

  @override
  String get contentCopied => 'Vsebina kopirana v odložišče';

  @override
  String get failedToUpdateStarred => 'Posodobitev označene postavke je spodletela.';

  @override
  String get conversationUrlNotShared => 'URL pogovora ni bilo mogoče deliti.';

  @override
  String get errorProcessingConversation => 'Napaka pri obdelavi pogovora. Prosimo, poskusite ponovno pozneje.';

  @override
  String get noInternetConnection => 'Ni internetne povezave';

  @override
  String get unableToDeleteConversation => 'Pogovora ni mogoče izbrisati';

  @override
  String get somethingWentWrong => 'Kaj se je storilo narobe! Prosimo, poskusite ponovno pozneje.';

  @override
  String get copyErrorMessage => 'Kopiraj sporočilo o napaki';

  @override
  String get errorCopied => 'Sporočilo o napaki je kopirano v odložišče';

  @override
  String get remaining => 'Preostalo';

  @override
  String get loading => 'Nalaganje...';

  @override
  String get loadingDuration => 'Nalaganje trajanja...';

  @override
  String secondsCount(int count) {
    return '$count sekund';
  }

  @override
  String get people => 'Ljudje';

  @override
  String get addNewPerson => 'Dodaj novo osebo';

  @override
  String get editPerson => 'Uredi osebo';

  @override
  String get createPersonHint => 'Ustvari novo osebo in nauči Omi, da prepozna tudi njihov glas!';

  @override
  String get speechProfile => 'Profil govora';

  @override
  String sampleNumber(int number) {
    return 'Vzorec $number';
  }

  @override
  String get settings => 'Nastavitve';

  @override
  String get language => 'Jezik';

  @override
  String get selectLanguage => 'Izberi jezik';

  @override
  String get deleting => 'Brisanje...';

  @override
  String get pleaseCompleteAuthentication =>
      'Prosimo, dokončajte avtentifikacijo v brskalniku. Ko ste končali, se vrnite v aplikacijo.';

  @override
  String get failedToStartAuthentication => 'Avtentifikacija se ni mogla začeti';

  @override
  String get importStarted => 'Uvoz je začet! Obveščeni boste, ko bo zaključen.';

  @override
  String get failedToStartImport => 'Uvoz se ni mogel začeti. Prosimo, poskusite ponovno.';

  @override
  String get couldNotAccessFile => 'Izbrane datoteke ni bilo mogoče dostopiti';

  @override
  String get askOmi => 'Vprašaj Omi';

  @override
  String get done => 'Gotovo';

  @override
  String get disconnected => 'Odklopljeno';

  @override
  String get searching => 'Iskanje...';

  @override
  String get connectDevice => 'Poveži napravo';

  @override
  String get monthlyLimitReached => 'Dosegli ste mesečno omejitev.';

  @override
  String get checkUsage => 'Preverite uporabo';

  @override
  String get syncingRecordings => 'Sinhroniziranje posnetkov';

  @override
  String get recordingsToSync => 'Posnetki za sinhroniziranje';

  @override
  String get allCaughtUp => 'Vsi ujeti';

  @override
  String get sync => 'Sinhroniziraj';

  @override
  String get pendantUpToDate => 'Obesek je posodobljen';

  @override
  String get allRecordingsSynced => 'Vsi posnetki so sinhronizirani';

  @override
  String get syncingInProgress => 'Sinhroniziranje je v teku';

  @override
  String get readyToSync => 'Pripravljen za sinhroniziranje';

  @override
  String get tapSyncToStart => 'Dotakni se sinhroniziranja za začetek';

  @override
  String get pendantNotConnected => 'Obesek ni priključen. Povežite se za sinhroniziranje.';

  @override
  String get everythingSynced => 'Vse je že sinhronizirano.';

  @override
  String get recordingsNotSynced => 'Imate posnetke, ki še niso sinhronizirani.';

  @override
  String get syncingBackground => 'Posnetke boste nadaljovali s sinhroniziranjem v ozadju.';

  @override
  String get noConversationsYet => 'Še ni pogovorov';

  @override
  String get noStarredConversations => 'Ni označenih pogovorov';

  @override
  String get starConversationHint => 'Če želite označiti pogovor, ga odprite in se dotaknite ikone zvezde v glavi.';

  @override
  String get searchConversations => 'Iskanje pogovorov...';

  @override
  String selectedCount(int count, Object s) {
    return '$count izbrano';
  }

  @override
  String get merge => 'Združi';

  @override
  String get mergeConversations => 'Združi pogovore';

  @override
  String mergeConversationsMessage(int count) {
    return 'To bo $count pogovorov kombiniralo v enega. Vsa vsebina bo združena in regenerirana.';
  }

  @override
  String get mergingInBackground => 'Združevanje v ozadju. To lahko traja malo.';

  @override
  String get failedToStartMerge => 'Združevanje se ni moglo začeti';

  @override
  String get askAnything => 'Vprašaj kaj koli';

  @override
  String get noMessagesYet => 'Še ni sporočil!\nZakaj ne bi začeli pogovora?';

  @override
  String get deletingMessages => 'Brisanje vaših sporočil iz Ominega pomnenja...';

  @override
  String get messageCopied => '✨ Sporočilo kopirano v odložišče';

  @override
  String get cannotReportOwnMessage => 'Ne morete prijaviti svojih lastnih sporočil.';

  @override
  String get reportMessage => 'Prijavite sporočilo';

  @override
  String get reportMessageConfirm => 'Ali ste prepričani, da želite prijaviti to sporočilo?';

  @override
  String get messageReported => 'Sporočilo je bilo uspešno prijavljeno.';

  @override
  String get thankYouFeedback => 'Hvala za vaše povratne informacije!';

  @override
  String get clearChat => 'Počisti klepet';

  @override
  String get clearChatConfirm => 'Ali ste prepričani, da želite počistiti klepet? To dejanje ni mogoče razveljaviti.';

  @override
  String get maxFilesLimit => 'Hkrati lahko naložite samo 4 datoteke';

  @override
  String get chatWithOmi => 'Klepetaj z Omi';

  @override
  String get apps => 'Aplikacije';

  @override
  String get noAppsFound => 'Nobena aplikacija ni bila najdena';

  @override
  String get tryAdjustingSearch => 'Poskusite prilagoditi iskanje ali filtre';

  @override
  String get createYourOwnApp => 'Ustvari svojo aplikacijo';

  @override
  String get buildAndShareApp => 'Ustvari in deli svojo prilagojeno aplikacijo';

  @override
  String get searchApps => 'Iskanje aplikacij...';

  @override
  String get myApps => 'Moje aplikacije';

  @override
  String get installedApps => 'Nameščene aplikacije';

  @override
  String get unableToFetchApps =>
      'Aplikacij ni bilo mogoče pridobiti :(\n\nProsimo, preverite internetno povezavo in poskusite ponovno.';

  @override
  String get aboutOmi => 'O Omi';

  @override
  String get privacyPolicy => 'Politika zasebnosti';

  @override
  String get visitWebsite => 'Obiščite spletno mesto';

  @override
  String get helpOrInquiries => 'Pomoč ali vprašanja?';

  @override
  String get joinCommunity => 'Pridružite se skupnosti!';

  @override
  String get membersAndCounting => '8000+ članov in več.';

  @override
  String get deleteAccountTitle => 'Izbriši račun';

  @override
  String get deleteAccountConfirm => 'Ali ste prepričani, da želite izbrisati svoj račun?';

  @override
  String get cannotBeUndone => 'To ne može biti razveljaviti.';

  @override
  String get allDataErased => 'Vsi vaši spomin in pogovori bodo trajno izbrisani.';

  @override
  String get appsDisconnected => 'Vaše aplikacije in integracije bodo takoj odklopljene.';

  @override
  String get exportBeforeDelete =>
      'Podatke lahko izvozite pred brisanjem računa, vendar jih po brisanju ni mogoče obnoviti.';

  @override
  String get deleteAccountCheckbox =>
      'Razumem, da je brisanje računa trajno in da bodo vsi podatki, vključno s spomini in pogovori, izginuli in jih ni mogoče obnoviti.';

  @override
  String get areYouSure => 'Ali ste prepričani?';

  @override
  String get deleteAccountFinal =>
      'To dejanje je nepovratno in bo trajno izbrisalo vaš račun in vse povezane podatke. Ali ste prepričani, da želite nadaljevati?';

  @override
  String get deleteNow => 'Izbriši zdaj';

  @override
  String get goBack => 'Pojdi nazaj';

  @override
  String get checkBoxToConfirm => 'Potrdite polje, da potrdite, da je brisanje računa trajno in nepovratno.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Ime';

  @override
  String get email => 'E-pošta';

  @override
  String get customVocabulary => 'Prilagojena besedila';

  @override
  String get identifyingOthers => 'Identifikacija drugih';

  @override
  String get paymentMethods => 'Načini plačila';

  @override
  String get conversationDisplay => 'Prikaz pogovora';

  @override
  String get dataPrivacy => 'Zasebnost podatkov';

  @override
  String get userId => 'ID uporabnika';

  @override
  String get notSet => 'Ni nastavljeno';

  @override
  String get userIdCopied => 'ID uporabnika je kopiran v odložišče';

  @override
  String get systemDefault => 'Privzeto sistemsko';

  @override
  String get planAndUsage => 'Načrt in uporaba';

  @override
  String get offlineSync => 'Sinhroniziranje brez povezave';

  @override
  String get deviceSettings => 'Nastavitve naprave';

  @override
  String get integrations => 'Integracije';

  @override
  String get feedbackBug => 'Povratne informacije / Napaka';

  @override
  String get helpCenter => 'Центр помоћи';

  @override
  String get developerSettings => 'Nastavitve razvojnika';

  @override
  String get getOmiForMac => 'Prenesite Omi za Mac';

  @override
  String get referralProgram => 'Program priporočil';

  @override
  String get signOut => 'Odjava';

  @override
  String get appAndDeviceCopied => 'Podrobnosti aplikacije in naprave so kopirane';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Vaša zasebnost, vaš nadzor';

  @override
  String get privacyIntro =>
      'Pri Omi smo zavezani zaščiti vaše zasebnosti. Ta stran vam omogoči nadzor nad tem, kako se vaši podatki shranjevajo in uporabljajo.';

  @override
  String get learnMore => 'Izvedite več...';

  @override
  String get dataProtectionLevel => 'Raven zaščite podatkov';

  @override
  String get dataProtectionDesc =>
      'Vaši podatki so privzeto zaščiteni s krepko enkripcijo. Preglejte svoje nastavitve in prihodnje možnosti zasebnosti spodaj.';

  @override
  String get appAccess => 'Dostop aplikacije';

  @override
  String get appAccessDesc =>
      'Naslednje aplikacije lahko dostopajo do vaših podatkov. Dotaknite se aplikacije za upravljanje njenih dovoljenj.';

  @override
  String get noAppsExternalAccess => 'Nobena nameščena aplikacija nima zunanjega dostopa do vaših podatkov.';

  @override
  String get deviceName => 'Ime naprave';

  @override
  String get deviceId => 'ID naprave';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Sinhroniziranje SD kartice';

  @override
  String get hardwareRevision => 'Revizija strojne opreme';

  @override
  String get modelNumber => 'Številka modela';

  @override
  String get manufacturer => 'Proizvajalec';

  @override
  String get doubleTap => 'Dvojni dotik';

  @override
  String get ledBrightness => 'Svetlost LED';

  @override
  String get micGain => 'Povečanje mikrofona';

  @override
  String get disconnect => 'Odkloči';

  @override
  String get forgetDevice => 'Pozabi napravo';

  @override
  String get chargingIssues => 'Težave s polnjenjem';

  @override
  String get disconnectDevice => 'Odkloči napravo';

  @override
  String get unpairDevice => 'Prekinji povezavo naprave';

  @override
  String get unpairAndForget => 'Prekinji povezavo in pozabi napravo';

  @override
  String get deviceDisconnectedMessage => 'Vaš Omi je bil odklopljen 😔';

  @override
  String get deviceUnpairedMessage =>
      'Naprava je preklopljena. Pojdite v Nastavitve > Bluetooth in pozabite napravo, da dokončate preklapljanje.';

  @override
  String get unpairDialogTitle => 'Prekinji povezavo naprave';

  @override
  String get unpairDialogMessage =>
      'To bo prekinilo povezavo naprave, da se jo lahko poveže z drugim telefonom. Trebat ćete ići na Postavke > Bluetooth i zaboraviti uređaj da završite proces.';

  @override
  String get deviceNotConnected => 'Naprava ni priključena';

  @override
  String get connectDeviceMessage => 'Povežite svojo Omi napravo za dostop\ndo nastavitev naprave in prilagoditve';

  @override
  String get deviceInfoSection => 'Informacije o napravi';

  @override
  String get customizationSection => 'Prilagoditev';

  @override
  String get hardwareSection => 'Strojna oprema';

  @override
  String get v2Undetected => 'V2 ni zaznan';

  @override
  String get v2UndetectedMessage =>
      'Vidimo, da imate V1 napravo ali pa je vaša naprava nepriključena. Funkcionalnost SD kartice je dostopna samo za naprave V2.';

  @override
  String get endConversation => 'Končaj pogovor';

  @override
  String get pauseResume => 'Pause/Resume';

  @override
  String get starConversation => 'Označi pogovor';

  @override
  String get doubleTapAction => 'Dejanje dvojnega dotika';

  @override
  String get endAndProcess => 'Končaj in obdelaj pogovor';

  @override
  String get pauseResumeRecording => 'Pause/Resume snemanje';

  @override
  String get starOngoing => 'Označi potekajući pogovor';

  @override
  String get off => 'Izključeno';

  @override
  String get max => 'Maks';

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
  String get micGainDescLow => 'Zelo tiho - za glasne okolice';

  @override
  String get micGainDescModerate => 'Tiho - za zmerno hrupa';

  @override
  String get micGainDescNeutral => 'Nevtralno - uravnoteženo snemanje';

  @override
  String get micGainDescSlightlyBoosted => 'Rahlo povečano - normalna uporaba';

  @override
  String get micGainDescBoosted => 'Povečano - za tihna okolica';

  @override
  String get micGainDescHigh => 'Visoko - za oddaljene ali mehke glasove';

  @override
  String get micGainDescVeryHigh => 'Zelo visoko - za zelo tiho virom';

  @override
  String get micGainDescMax => 'Največje - uporabljajte previdno';

  @override
  String get developerSettingsTitle => 'Nastavitve razvojnika';

  @override
  String get saving => 'Shranjevanje...';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkripcija';

  @override
  String get transcriptionConfig => 'Nastavite ponudnika STT';

  @override
  String get conversationTimeout => 'Časovna omejitev pogovora';

  @override
  String get conversationTimeoutConfig => 'Nastavite, kdaj se pogovori avtomatsko končajo';

  @override
  String get importData => 'Uvozite podatke';

  @override
  String get importDataConfig => 'Uvozite podatke iz drugih virov';

  @override
  String get debugDiagnostics => 'Razhroščevanje in diagnostika';

  @override
  String get endpointUrl => 'URL končne točke';

  @override
  String get noApiKeys => 'Še ni ključev API';

  @override
  String get createKeyToStart => 'Ustvarite ključ za začetek';

  @override
  String get createKey => 'Ustvari ključ';

  @override
  String get docs => 'Dokumenti';

  @override
  String get yourOmiInsights => 'Vaši Omi uvidi';

  @override
  String get today => 'Danes';

  @override
  String get thisMonth => 'Ta mesec';

  @override
  String get thisYear => 'To leto';

  @override
  String get allTime => 'Ves čas';

  @override
  String get noActivityYet => 'Ni aktivnosti';

  @override
  String get startConversationToSeeInsights => 'Začnite pogovor z Omi\nda vidite svoje uvide v uporabi tukaj.';

  @override
  String get listening => 'Poslušanje';

  @override
  String get listeningSubtitle => 'Skupni čas, ko je Omi aktivno poslušal.';

  @override
  String get understanding => 'Razumevanje';

  @override
  String get understandingSubtitle => 'Besede razumene iz vaših pogovorov.';

  @override
  String get providing => 'Zagotavljanje';

  @override
  String get providingSubtitle => 'Akcijski predmeti in opombe samodejno zajete.';

  @override
  String get remembering => 'Pomnjenje';

  @override
  String get rememberingSubtitle => 'Dejstva in podrobnosti, ki se jih za vas spomnijo.';

  @override
  String get unlimitedPlan => 'Neomejen načrt';

  @override
  String get managePlan => 'Upravljajte načrt';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Vaš načrt bo preklican na $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Vaš načrt se obnavlja na $date.';
  }

  @override
  String get basicPlan => 'Brezplačni načrt';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used od $limit minut porabljenega';
  }

  @override
  String get upgrade => 'Nadgradi';

  @override
  String get upgradeToUnlimited => 'Nadgradi na neomejeno';

  @override
  String basicPlanDesc(int limit) {
    return 'Vaš načrt vključuje $limit brezplačnih minut na mesec. Nadgrajeno za neomejeno.';
  }

  @override
  String get shareStatsMessage => 'Delim Omi statistiko! (omi.me - vaš vedno dostopen AI pomočnik)';

  @override
  String get sharePeriodToday => 'Danes je omi:';

  @override
  String get sharePeriodMonth => 'Ta mesec je omi:';

  @override
  String get sharePeriodYear => 'To leto je omi:';

  @override
  String get sharePeriodAllTime => 'Doslej je omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Poslušal $minutes minut';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Razumel $words besed';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Zagotovil $count uvidov';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Spomniti se $count spominov';
  }

  @override
  String get debugLogs => 'Dnevniki razhroščevanja';

  @override
  String get debugLogsAutoDelete => 'Samodejno briše po 3 dneh.';

  @override
  String get debugLogsDesc => 'Pomaga pri diagnostiki težav';

  @override
  String get noLogFilesFound => 'Nobena dnevniška datoteka ni bila najdena.';

  @override
  String get omiDebugLog => 'Omi dnevnik razhroščevanja';

  @override
  String get logShared => 'Dnevnik deljen';

  @override
  String get selectLogFile => 'Izberite dnevniško datoteko';

  @override
  String get shareLogs => 'Delite dnevnike';

  @override
  String get debugLogCleared => 'Dnevnik razhroščevanja je počišten';

  @override
  String get exportStarted => 'Izvoz je začet. To lahko traja nekaj sekund...';

  @override
  String get exportAllData => 'Izvozi vse podatke';

  @override
  String get exportDataDesc => 'Izvozi pogovore v datoteko JSON';

  @override
  String get exportedConversations => 'Izvoženi pogovori iz Omi';

  @override
  String get exportShared => 'Izvoz deljen';

  @override
  String get deleteKnowledgeGraphTitle => 'Izbriši graf znanja?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'To bo izbrisalo vse izpeljane podatke grafa znanja (vozlišča in povezave). Vaši izvirni spomin ostanejo varni. Graf se bo sčasoma ponovno zgrajen ali ob naslednji zahtevi.';

  @override
  String get knowledgeGraphDeleted => 'Graf znanja je izbrisan';

  @override
  String deleteGraphFailed(String error) {
    return 'Brisanje grafa je spodletelo: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Izbriši graf znanja';

  @override
  String get deleteKnowledgeGraphDesc => 'Očisti vsa vozlišča in povezave';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP strežnik';

  @override
  String get mcpServerDesc => 'Povežite AI pomočnike s svojimi podatki';

  @override
  String get serverUrl => 'URL strežnika';

  @override
  String get urlCopied => 'URL kopiran';

  @override
  String get apiKeyAuth => 'Avtentifikacija ključa API';

  @override
  String get header => 'Glava';

  @override
  String get authorizationBearer => 'Avtorizacija: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID odjemalca';

  @override
  String get clientSecret => 'Skrivnost odjemalca';

  @override
  String get useMcpApiKey => 'Uporabite svoj ključ MCP API';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Dogodki pogovora';

  @override
  String get newConversationCreated => 'Nov pogovor je ustvarjen';

  @override
  String get realtimeTranscript => 'Pravi čas prepisa';

  @override
  String get transcriptReceived => 'Prepis je prejeti';

  @override
  String get audioBytes => 'Avdio bajti';

  @override
  String get audioDataReceived => 'Avdio podatki prejeti';

  @override
  String get intervalSeconds => 'Interval (sekund)';

  @override
  String get daySummary => 'Povzetek dneva';

  @override
  String get summaryGenerated => 'Povzetek je generiran';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Dodaj v claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopiraj konfigurацију';

  @override
  String get configCopied => 'Konfiguracija kopirana v odložišče';

  @override
  String get listeningMins => 'Poslušanje (min)';

  @override
  String get understandingWords => 'Razumevanje (besed)';

  @override
  String get insights => 'Uvidi';

  @override
  String get memories => 'Spomin';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used od $limit min porabljenega ta mesec';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used od $limit besed porabljenega ta mesec';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used od $limit uvidov pridobljenih ta mesec';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used od $limit spominov ustvarjenih ta mesec';
  }

  @override
  String get visibility => 'Vidljivost';

  @override
  String get visibilitySubtitle => 'Nadzor, kateri pogovori se pojavljajo na vaši seznamu';

  @override
  String get showShortConversations => 'Prikaži kratke pogovore';

  @override
  String get showShortConversationsDesc => 'Prikaži pogovore krajše od praga';

  @override
  String get showDiscardedConversations => 'Prikaži zavrnjene pogovore';

  @override
  String get showDiscardedConversationsDesc => 'Vključi pogovore označene kot zavrnjeni';

  @override
  String get shortConversationThreshold => 'Prag kratke pogovora';

  @override
  String get shortConversationThresholdSubtitle => 'Pogovori krajši od tega bodo skriti, razen če je omogočeno zgoraj';

  @override
  String get durationThreshold => 'Prag trajanja';

  @override
  String get durationThresholdDesc => 'Skrij pogovore krajše od tega';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Prilagojena besedila';

  @override
  String get addWords => 'Dodaj besede';

  @override
  String get addWordsDesc => 'Imena, pogoji ali neobičajne besede';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Povežite';

  @override
  String get comingSoon => 'Kmalu';

  @override
  String get integrationsFooter => 'Povežite svoje aplikacije za prikaz podatkov in metrike v klepetu.';

  @override
  String get completeAuthInBrowser =>
      'Prosimo, dokončajte avtentifikacijo v brskalniku. Ko ste končali, se vrnite v aplikacijo.';

  @override
  String failedToStartAuth(String appName) {
    return 'Avtentifikacija $appName se ni mogla začeti';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Prekini $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Ali ste prepričani, da se želite odklopi iz $appName? Lahko se ponovno povežete kadarkoli.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Odklopljeno iz $appName';
  }

  @override
  String get failedToDisconnect => 'Odklapljanje je spodletelo';

  @override
  String connectTo(String appName) {
    return 'Povežite se s $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Dovoljiti morate Omi dostop do podatkov $appName. To bo odpro vaš brskalnik za avtentifikacijo.';
  }

  @override
  String get continueAction => 'Nadaljuj';

  @override
  String get languageTitle => 'Jezik';

  @override
  String get primaryLanguage => 'Primarni jezik';

  @override
  String get automaticTranslation => 'Samodejni prevod';

  @override
  String get detectLanguages => 'Zaznaj 10+ jezikov';

  @override
  String get authorizeSavingRecordings => 'Avtoriziraj shranjevanje posnetkov';

  @override
  String get thanksForAuthorizing => 'Hvala, ker ste avtorizirali!';

  @override
  String get needYourPermission => 'Potrebujemo vašo dovoljenje';

  @override
  String get alreadyGavePermission =>
      'Že ste nam dali dovoljenje za shranjevanje vaših posnetkov. Tu je opomnik, zakaj ga potrebujemo:';

  @override
  String get wouldLikePermission => 'Radi bi vaše dovoljenje za shranjevanje vaših glasovnih posnetkov. Evo zakaj:';

  @override
  String get improveSpeechProfile => 'Izboljšaj svoj profil govora';

  @override
  String get improveSpeechProfileDesc =>
      'Posnetke uporabljamo za dodatno usposabljanje in izboljšanje vašega osebnega profila govora.';

  @override
  String get trainFamilyProfiles => 'Profilov usposabljanja za prijatelje in družino';

  @override
  String get trainFamilyProfilesDesc =>
      'Vaši posnetki nam pomagajo prepoznati in ustvariti profile za vaše prijatelje in družino.';

  @override
  String get enhanceTranscriptAccuracy => 'Izboljšaj natančnost prepisa';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Ko se naš model izboljša, lahko zagotovimo boljše rezultate transkripcije za vaše posnetke.';

  @override
  String get legalNotice =>
      'Pravno obvestilo: Zakonitost snemanja in shranjevanja podatkov govora se lahko razlikuje glede na vašo lokacijo in kako uporabljate to funkcijo. Vaša odgovornost je, da zagotovite skladnost z lokalnimi zakoni in predpisi.';

  @override
  String get alreadyAuthorized => 'Že avtorizirano';

  @override
  String get authorize => 'Avtoriziraj';

  @override
  String get revokeAuthorization => 'Prekliči avtorizacijo';

  @override
  String get authorizationSuccessful => 'Avtorizacija je bila uspešna!';

  @override
  String get failedToAuthorize => 'Avtorizacija ni uspela. Poskusite znova.';

  @override
  String get authorizationRevoked => 'Avtorizacija je bila preklicana.';

  @override
  String get recordingsDeleted => 'Posnetki so izbrisani.';

  @override
  String get failedToRevoke => 'Preklicanje avtorizacije ni uspelo. Poskusite znova.';

  @override
  String get permissionRevokedTitle => 'Dovoljenka je bila preklicana';

  @override
  String get permissionRevokedMessage => 'Ali želite, da izbrišemo tudi vse vaše obstoječe posnetke?';

  @override
  String get yes => 'Da';

  @override
  String get editName => 'Uredi ime';

  @override
  String get howShouldOmiCallYou => 'Kako te mora Omi oslovljati?';

  @override
  String get enterYourName => 'Vnesite svoje ime';

  @override
  String get nameCannotBeEmpty => 'Ime ne sme biti prazno';

  @override
  String get nameUpdatedSuccessfully => 'Ime je bilo uspešno posodobljeno!';

  @override
  String get calendarSettings => 'Nastavitve koledarja';

  @override
  String get calendarProviders => 'Ponudniki koledarjev';

  @override
  String get macOsCalendar => 'Koledar macOS';

  @override
  String get connectMacOsCalendar => 'Povežite svoj lokalni koledar macOS';

  @override
  String get googleCalendar => 'Google Koledar';

  @override
  String get syncGoogleAccount => 'Sinhroniziraj z Google Accounts';

  @override
  String get showMeetingsMenuBar => 'Pokaži prihajajo sestanke v menijski vrstici';

  @override
  String get showMeetingsMenuBarDesc =>
      'Prikaži svoj naslednji sestanek in čas do njegovega začetka v menijski vrstici macOS';

  @override
  String get showEventsNoParticipants => 'Pokaži dogodke brez udeležencev';

  @override
  String get showEventsNoParticipantsDesc =>
      'Če je omogočeno, »Prihajajo« prikazuje dogodke brez udeležencev ali video povezave.';

  @override
  String get yourMeetings => 'Vaši sestanki';

  @override
  String get refresh => 'Osveži';

  @override
  String get noUpcomingMeetings => 'Ni prihajajočih sestankov';

  @override
  String get checkingNextDays => 'Preverjam naslednjih 30 dni';

  @override
  String get tomorrow => 'Jutri';

  @override
  String get googleCalendarComingSoon => 'Integracija Google Koledarja - kmalu!';

  @override
  String connectedAsUser(String userId) {
    return 'Povezan kot uporabnik: $userId';
  }

  @override
  String get defaultWorkspace => 'Privzeto delovni prostor';

  @override
  String get tasksCreatedInWorkspace => 'Naloge bodo ustvarjene v tem delovnem prostoru';

  @override
  String get defaultProjectOptional => 'Privzeti projekt (neobavezno)';

  @override
  String get leaveUnselectedTasks => 'Pustite neizbranega za ustvarjanje nalog brez projekta';

  @override
  String get noProjectsInWorkspace => 'V tem delovnem prostoru ni projektov';

  @override
  String get conversationTimeoutDesc => 'Izberite, kako dolgo čakati v tišini, preden se pogovor avtomatično konča:';

  @override
  String get timeout2Minutes => '2 minuti';

  @override
  String get timeout2MinutesDesc => 'Konči pogovor po 2 minutah tišine';

  @override
  String get timeout5Minutes => '5 minut';

  @override
  String get timeout5MinutesDesc => 'Konči pogovor po 5 minutah tišine';

  @override
  String get timeout10Minutes => '10 minut';

  @override
  String get timeout10MinutesDesc => 'Konči pogovor po 10 minutah tišine';

  @override
  String get timeout30Minutes => '30 minut';

  @override
  String get timeout30MinutesDesc => 'Konči pogovor po 30 minutah tišine';

  @override
  String get timeout4Hours => '4 ure';

  @override
  String get timeout4HoursDesc => 'Konči pogovor po 4 urah tišine';

  @override
  String get conversationEndAfterHours => 'Pogovori se bodo končali po 4 urah tišine';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Pogovori se bodo končali po $minutes minuti(-ah) tišine';
  }

  @override
  String get tellUsPrimaryLanguage => 'Povejte nam svoj primarni jezik';

  @override
  String get languageForTranscription => 'Nastavite svoj jezik za boljše transkripcije in osebno izkušnjo.';

  @override
  String get singleLanguageModeInfo => 'Način enega jezika je omogočen. Prevajanje je onemogočeno za večjo natančnost.';

  @override
  String get searchLanguageHint => 'Poiščite jezik po imenu ali kodi';

  @override
  String get noLanguagesFound => 'Ni najdenih jezikov';

  @override
  String get skip => 'Preskoči';

  @override
  String languageSetTo(String language) {
    return 'Jezik je nastavljen na $language';
  }

  @override
  String get failedToSetLanguage => 'Nastavitev jezika ni uspela';

  @override
  String appSettings(String appName) {
    return '$appName Nastavitve';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Prekinite z $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'To bo odstranilo vašo avtentikacijo za $appName. Za ponovno uporabo se boste morali znova povežati.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Povezano z $appName';
  }

  @override
  String get account => 'Račun';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Vaši actionji bodo sinhronizirani z $appName računom';
  }

  @override
  String get defaultSpace => 'Privzor prostor';

  @override
  String get selectSpaceInWorkspace => 'Izberite prostor v delovnem prostoru';

  @override
  String get noSpacesInWorkspace => 'V tem delovnem prostoru ni prostorov';

  @override
  String get defaultList => 'Privzet seznam';

  @override
  String get tasksAddedToList => 'Naloge bodo dodane v ta seznam';

  @override
  String get noListsInSpace => 'V tem prostoru ni seznamov';

  @override
  String failedToLoadRepos(String error) {
    return 'Nalaganje skladišč ni uspelo: $error';
  }

  @override
  String get defaultRepoSaved => 'Privzeto skladišče je bilo shranjeno';

  @override
  String get failedToSaveDefaultRepo => 'Shranjevanje privzetega skladišča ni uspelo';

  @override
  String get defaultRepository => 'Privzeto skladišče';

  @override
  String get selectDefaultRepoDesc =>
      'Izberite privzeto skladišče za ustvarjanje težav. Pri ustvarjanju težav še vedno lahko določite drugo skladišče.';

  @override
  String get noReposFound => 'Ni najdenih skladišč';

  @override
  String get private => 'Zasebno';

  @override
  String updatedDate(String date) {
    return 'Posodobljeno $date';
  }

  @override
  String get yesterday => 'Včeraj';

  @override
  String daysAgo(int count) {
    return 'pred $count dnevi';
  }

  @override
  String get oneWeekAgo => 'pred 1 tednom';

  @override
  String weeksAgo(int count) {
    return 'pred $count tedni';
  }

  @override
  String get oneMonthAgo => 'pred 1 mesecem';

  @override
  String monthsAgo(int count) {
    return 'pred $count meseci';
  }

  @override
  String get issuesCreatedInRepo => 'Težave bodo ustvarjene v vašem privzetem skladišču';

  @override
  String get taskIntegrations => 'Integracije nalog';

  @override
  String get configureSettings => 'Nastavite nastavitve';

  @override
  String get completeAuthBrowser =>
      'Prosimo dokončajte avtentikacijo v brskalniku. Ko je to storjeno, se vrnite v aplikacijo.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Začetek avtentikacije $appName ni uspel';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Povežite se z $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Avtorizirati moramo Omi, da ustvari naloge v vašem $appName računu. To bo odprlo brskalnik za avtentikacijo.';
  }

  @override
  String get continueButton => 'Nadaljuj';

  @override
  String appIntegration(String appName) {
    return '$appName Integracija';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integracija z $appName bo kmalu na voljo! Trudimo se, da vam prinesemo več možnosti za upravljanje nalog.';
  }

  @override
  String get gotIt => 'Razumem';

  @override
  String get tasksExportedOneApp => 'Naloge je mogoče izvoziti v eno aplikacijo naenkrat.';

  @override
  String get completeYourUpgrade => 'Dokončajte nadgradnjo';

  @override
  String get importConfiguration => 'Uvozite nastavitve';

  @override
  String get exportConfiguration => 'Izvozite nastavitve';

  @override
  String get bringYourOwn => 'Prinesite svoje';

  @override
  String get payYourSttProvider => 'Prostorocno uporabite omi. Plačujete samo svojemu STT ponudniku.';

  @override
  String get freeMinutesMonth => '1.200 brezplačnih minut/mesec vključenih. Neomejeno z ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Potreben je gostitelj';

  @override
  String get validPortRequired => 'Potreben je veljaven port';

  @override
  String get validWebsocketUrlRequired => 'Potreben je veljaven WebSocket URL (wss://)';

  @override
  String get apiUrlRequired => 'Potreben je API URL';

  @override
  String get apiKeyRequired => 'Potreben je API ključ';

  @override
  String get invalidJsonConfig => 'Neveljavna JSON konfiguracija';

  @override
  String errorSaving(String error) {
    return 'Napaka pri shranjevanju: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfiguracija je bila kopirana v odložišče';

  @override
  String get pasteJsonConfig => 'Prilepite vašo JSON konfiguraciji spodaj:';

  @override
  String get addApiKeyAfterImport => 'Po uvozu boste morali dodati svoj API ključ';

  @override
  String get paste => 'Prilepite';

  @override
  String get import => 'Uvozite';

  @override
  String get invalidProviderInConfig => 'Neveljavni ponudnik v konfiguraciji';

  @override
  String importedConfig(String providerName) {
    return 'Uvozena $providerName konfiguracija';
  }

  @override
  String invalidJson(String error) {
    return 'Neveljavni JSON: $error';
  }

  @override
  String get provider => 'Ponudnik';

  @override
  String get live => 'Neposredno';

  @override
  String get onDevice => 'Na napravi';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Vnesite svoj STT HTTP končni točki';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Vnesite svoj neposredni STT WebSocket končni točki';

  @override
  String get apiKey => 'API ključ';

  @override
  String get enterApiKey => 'Vnesite svoj API ključ';

  @override
  String get storedLocallyNeverShared => 'Shranjeno lokalno, nikoli deljeno';

  @override
  String get host => 'Gostitelj';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Napredne';

  @override
  String get configuration => 'Konfiguracija';

  @override
  String get requestConfiguration => 'Konfiguriraj zahtevo';

  @override
  String get responseSchema => 'Shema odgovora';

  @override
  String get modified => 'Spremenjeno';

  @override
  String get resetRequestConfig => 'Resetuj zahtevo na privzeto';

  @override
  String get logs => 'Dnevniki';

  @override
  String get logsCopied => 'Dnevniki so kopirani';

  @override
  String get noLogsYet => 'Dnevniki še niso. Začnite snemati in vidite aktivnost po meri STT.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device uporablja $reason. Korišten bo Omi.';
  }

  @override
  String get omiTranscription => 'Omi Transkripcija';

  @override
  String get bestInClassTranscription => 'Najboljša transkripcija brez nastavitve';

  @override
  String get instantSpeakerLabels => 'Takojšnje oznake govorcev';

  @override
  String get languageTranslation => 'Prevajanje v 100+ jezikov';

  @override
  String get optimizedForConversation => 'Optimizirana za pogovor';

  @override
  String get autoLanguageDetection => 'Samodejno zaznavanje jezika';

  @override
  String get highAccuracy => 'Visoka natančnost';

  @override
  String get privacyFirst => 'Zasebnost na prvem mestu';

  @override
  String get saveChanges => 'Shrani spremembe';

  @override
  String get resetToDefault => 'Resetuj na privzeto';

  @override
  String get viewTemplate => 'Ogled predloge';

  @override
  String get trySomethingLike => 'Poskusite kaj podobnega...';

  @override
  String get tryIt => 'Poskusite';

  @override
  String get creatingPlan => 'Ustvarjam načrt';

  @override
  String get developingLogic => 'Razvijam logiko';

  @override
  String get designingApp => 'Oblikujem aplikacijo';

  @override
  String get generatingIconStep => 'Generiram ikono';

  @override
  String get finalTouches => 'Končni dotiki';

  @override
  String get processing => 'Obdelava...';

  @override
  String get features => 'Lastnosti';

  @override
  String get creatingYourApp => 'Ustvarjam vašo aplikacijo...';

  @override
  String get generatingIcon => 'Generiram ikono...';

  @override
  String get whatShouldWeMake => 'Kaj bi morali narediti?';

  @override
  String get appName => 'Ime aplikacije';

  @override
  String get description => 'Opis';

  @override
  String get publicLabel => 'Javno';

  @override
  String get privateLabel => 'Zasebno';

  @override
  String get free => 'Brezplačno';

  @override
  String get perMonth => '/ Mesec';

  @override
  String get tailoredConversationSummaries => 'Prilagojeni povzetki pogovorov';

  @override
  String get customChatbotPersonality => 'Prilagojena osebnost chatbota';

  @override
  String get makePublic => 'Objavi javno';

  @override
  String get anyoneCanDiscover => 'Kdorkoli lahko odkrije vašo aplikacijo';

  @override
  String get onlyYouCanUse => 'Samo vi lahko uporabljate to aplikacijo';

  @override
  String get paidApp => 'Plačana aplikacija';

  @override
  String get usersPayToUse => 'Uporabniki plačajo za uporabo vaše aplikacije';

  @override
  String get freeForEveryone => 'Brezplačno za vse';

  @override
  String get perMonthLabel => '/ mesec';

  @override
  String get creating => 'Ustvarjanje...';

  @override
  String get createApp => 'Ustvari aplikacijo';

  @override
  String get searchingForDevices => 'Iščem naprave...';

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
  String get pairingSuccessful => 'PARJENJE USPEŠNO';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Napaka pri povezovanju na Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Ne prikaži več';

  @override
  String get iUnderstand => 'Razumem';

  @override
  String get enableBluetooth => 'Omogočite Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi potrebuje Bluetooth za povezavo z vašo nosljivo napravo. Prosimo omogočite Bluetooth in poskusite znova.';

  @override
  String get contactSupport => 'Stopite v kontakt s podporo?';

  @override
  String get connectLater => 'Povežite se kasneje';

  @override
  String get grantPermissions => 'Dodelite dovoljenke';

  @override
  String get backgroundActivity => 'Aktivnost v ozadju';

  @override
  String get backgroundActivityDesc => 'Dovolite, da Omi teče v ozadju za boljšo stabilnost';

  @override
  String get locationAccess => 'Dostop do lokacije';

  @override
  String get locationAccessDesc => 'Omogočite lokacijo v ozadju za polno izkušnjo';

  @override
  String get notifications => 'Obvestila';

  @override
  String get notificationsDesc => 'Omogočite obvestila, da budete obveščeni';

  @override
  String get locationServiceDisabled => 'Storitev lokacije je onemogočena';

  @override
  String get locationServiceDisabledDesc =>
      'Storitev lokacije je onemogočena. Prosimo, pojdite v Nastavitve > Zasebnost in varnost > Storitve lokacije in omogočite';

  @override
  String get backgroundLocationDenied => 'Dostop do lokacije v ozadju je zavrnjen';

  @override
  String get backgroundLocationDeniedDesc =>
      'Prosimo, pojdite v nastavitve naprave in nastavite dovoljenka za lokacijo na »Vedno dovoli«';

  @override
  String get lovingOmi => 'Vam je všeč Omi?';

  @override
  String get leaveReviewIos =>
      'Pomagajte nam dosegati več ljudi s povzetkom v App Storu. Vaše povratne informacije pomenijo svet!';

  @override
  String get leaveReviewAndroid =>
      'Pomagajte nam dosegati več ljudi s povzetkom v Google Play Storu. Vaše povratne informacije pomenijo svet!';

  @override
  String get rateOnAppStore => 'Ocenite v App Storu';

  @override
  String get rateOnGooglePlay => 'Ocenite v Google Play';

  @override
  String get maybeLater => 'Morda pozneje';

  @override
  String get speechProfileIntro => 'Omi mora spoznati vaše cilje in vaš glas. Pozneje ga boste lahko spremenili.';

  @override
  String get getStarted => 'Začnite';

  @override
  String get allDone => 'Vse je storjeno!';

  @override
  String get keepGoing => 'Nadaljujte, odličko se vam dogaja';

  @override
  String get skipThisQuestion => 'Preskoči to vprašanje';

  @override
  String get skipForNow => 'Preskoči za zdaj';

  @override
  String get connectionError => 'Napaka povezave';

  @override
  String get connectionErrorDesc =>
      'Povezava na strežnik ni uspela. Prosimo preverite internet povezavo in poskusite znova.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Zaznana neveljavna snemka';

  @override
  String get multipleSpeakersDesc =>
      'Videti je, da so v snemki večje govorca. Prosimo prepričajte se, da ste na tihem mestu in poskusite znova.';

  @override
  String get tooShortDesc => 'Zaznano ni dovolj govora. Prosimo govorite več in poskusite znova.';

  @override
  String get invalidRecordingDesc => 'Prosimo prepričajte se, da govorite najmanj 5 sekund in ne več kot 90.';

  @override
  String get areYouThere => 'Ali ste tam?';

  @override
  String get noSpeechDesc => 'Nismo mogli zaznati govora. Prosimo govorite najmanj 10 sekund in ne več kot 3 minute.';

  @override
  String get connectionLost => 'Povezava je prekinjena';

  @override
  String get connectionLostDesc =>
      'Povezava je bila prekinjena. Prosimo preverite internet povezavo in poskusite znova.';

  @override
  String get tryAgain => 'Poskusite znova';

  @override
  String get connectOmiOmiGlass => 'Povežite Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Nadaljujte brez naprave';

  @override
  String get permissionsRequired => 'Potrebne so dovoljenke';

  @override
  String get permissionsRequiredDesc =>
      'Ta aplikacija potrebuje dovoljenke Bluetooth in lokacije za pravilno delovanje. Prosimo omogočite jih v nastavitvah.';

  @override
  String get openSettings => 'Odpri nastavitve';

  @override
  String get wantDifferentName => 'Želite biti znani pod drugim imenom?';

  @override
  String get whatsYourName => 'Kako se imenujete?';

  @override
  String get speakTranscribeSummarize => 'Govorite. Pretvorite v besedilo. Povzemite.';

  @override
  String get signInWithApple => 'Prijavite se s Apple';

  @override
  String get signInWithGoogle => 'Prijavite se z Google';

  @override
  String get byContinuingAgree => 'Z nadaljanjem se strinjate z našimi ';

  @override
  String get termsOfUse => 'Pogoji uporabe';

  @override
  String get omiYourAiCompanion => 'Omi – Vaš AI spremljevalec';

  @override
  String get captureEveryMoment =>
      'Zajemite vsak trenutek. Dobite povzetke na podlagi umetne inteligence.\nNikoli več ne pisujte opombk.';

  @override
  String get appleWatchSetup => 'Namestitev Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Dovoljenka je bila zahtevana!';

  @override
  String get microphonePermission => 'Dovoljenka mikrofona';

  @override
  String get permissionGrantedNow =>
      'Dovoljenka je bila odobrena! Zdaj:\n\nOdprite aplikacijo Omi na uri in tapnite »Nadaljuj« spodaj';

  @override
  String get needMicrophonePermission =>
      'Potrebujemo dovoljenka za mikrofon.\n\n1. Tapnite »Dodelite dovoljenka«\n2. Dovolite na iPhonu\n3. Aplikacija na uri se bo zaprla\n4. Ponovno jo odprite in tapnite »Nadaljuj«';

  @override
  String get grantPermissionButton => 'Dodelite dovoljenka';

  @override
  String get needHelp => 'Potrebujete pomoč?';

  @override
  String get troubleshootingSteps =>
      'Odpravljanje težav:\n\n1. Prepričajte se, da je Omi nameščen na vaši uri\n2. Odprite aplikacijo Omi na vaši uri\n3. Poiščite okno dovoljenke\n4. Tapnite »Dovoli« ko je prikazano\n5. Aplikacija na uri se bo zaprla - ponovno jo odprite\n6. Pridite nazaj in tapnite »Nadaljuj« na iPhonu';

  @override
  String get recordingStartedSuccessfully => 'Snemanje je uspešno začeto!';

  @override
  String get permissionNotGrantedYet =>
      'Dovoljenka še ni odobrena. Prosimo prepričajte se, da ste dovolili dostop do mikrofona in ponovno odprli aplikacijo na uri.';

  @override
  String errorRequestingPermission(String error) {
    return 'Napaka pri zahtevanju dovoljenke: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Napaka pri začetku snemanja: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Izberite svoj primarni jezik';

  @override
  String get languageBenefits => 'Nastavite svoj jezik za boljše transkripcije in osebno izkušnjo';

  @override
  String get whatsYourPrimaryLanguage => 'Kaj je vaš primarni jezik?';

  @override
  String get selectYourLanguage => 'Izberite svoj jezik';

  @override
  String get personalGrowthJourney => 'Vaša osebna pot rasti z AI, ki je pozorna na vsako vaše besedo.';

  @override
  String get actionItemsTitle => 'Opravila';

  @override
  String get actionItemsDescription => 'Tapnite za urejanje • Dolgo tapnite za izbiro • Plzite za dejanja';

  @override
  String get tabToDo => 'Za narediti';

  @override
  String get tabDone => 'Opravljeno';

  @override
  String get tabOld => 'Staro';

  @override
  String get emptyTodoMessage => '🎉 Vse napravljeno!\nNi pending opravil';

  @override
  String get emptyDoneMessage => 'Ni še opravljenih postavk';

  @override
  String get emptyOldMessage => '✅ Ni starih nalog';

  @override
  String get noItems => 'Ni postavk';

  @override
  String get actionItemMarkedIncomplete => 'Opravilo je označeno kot nedokončano';

  @override
  String get actionItemCompleted => 'Opravilo je završeno';

  @override
  String get deleteActionItemTitle => 'Izbriši opravilo';

  @override
  String get deleteActionItemMessage => 'Ali ste prepričani, da želite izbrisati to opravilo?';

  @override
  String get deleteSelectedItemsTitle => 'Izbriši izbrane postavke';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Ali ste prepričani, da želite izbrisati $count izbranih opravil$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Opravilo \"$description\" je izbrisano';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count opravilo$s izbrisanega';
  }

  @override
  String get failedToDeleteItem => 'Brisanje opravila ni uspelo';

  @override
  String get failedToDeleteItems => 'Brisanje postavk ni uspelo';

  @override
  String get failedToDeleteSomeItems => 'Brisanje nekaterih postavk ni uspelo';

  @override
  String get welcomeActionItemsTitle => 'Pripravljena za opravila';

  @override
  String get welcomeActionItemsDescription =>
      'Vaša umetna inteligenca bo samodejno izluščila naloge in opravila iz pogovorov. Pojavila se bodo tukaj, ko bodo ustvarjena.';

  @override
  String get autoExtractionFeature => 'Samodejno izluščeno iz pogovorov';

  @override
  String get editSwipeFeature => 'Tapnite za urejanje, plzite za končanje ali brisanje';

  @override
  String itemsSelected(int count) {
    return '$count izbrano';
  }

  @override
  String get selectAll => 'Izberite vse';

  @override
  String get deleteSelected => 'Izbriši izbrane';

  @override
  String get searchMemories => 'Poiščite spomine...';

  @override
  String get memoryDeleted => 'Spomin je izbrisan.';

  @override
  String get undo => 'Razveljavi';

  @override
  String get noMemoriesYet => '🧠 Še niso spomine';

  @override
  String get noAutoMemories => 'Nema samodejno izluščenih spomnov';

  @override
  String get noManualMemories => 'Nema ročno dodanih spomnov';

  @override
  String get noMemoriesInCategories => 'Nema spomnov v teh kategorijah';

  @override
  String get noMemoriesFound => '🔍 Ni najdenih spomnov';

  @override
  String get addFirstMemory => 'Dodajte svoj prvi spomin';

  @override
  String get clearMemoryTitle => 'Počisti Omijevo spominno';

  @override
  String get clearMemoryMessage =>
      'Ali ste prepričani, da želite počistiti Omijevo spomin? To dejanje ne moremo razveljaviti.';

  @override
  String get clearMemoryButton => 'Počisti spomin';

  @override
  String get memoryClearedSuccess => 'Omijevo spomin o vas je bila počiščena';

  @override
  String get noMemoriesToDelete => 'Nema spomnov za brisanje';

  @override
  String get createMemoryTooltip => 'Ustvari novi spomin';

  @override
  String get createActionItemTooltip => 'Ustvari novo opravilo';

  @override
  String get memoryManagement => 'Upravljanje spomnov';

  @override
  String get filterMemories => 'Filtriraj spomine';

  @override
  String totalMemoriesCount(int count) {
    return 'Imate $count skupno spomnov';
  }

  @override
  String get publicMemories => 'Javni spomine';

  @override
  String get privateMemories => 'Zasebni spomine';

  @override
  String get makeAllPrivate => 'Naredi vse spomine zasebne';

  @override
  String get makeAllPublic => 'Naredi vse spomine javne';

  @override
  String get deleteAllMemories => 'Izbriši vse spomine';

  @override
  String get allMemoriesPrivateResult => 'Vsi spomine so zdaj zasebni';

  @override
  String get allMemoriesPublicResult => 'Vsi spomine so zdaj javni';

  @override
  String get newMemory => '✨ Novi spomin';

  @override
  String get editMemory => '✏️ Uredi spomin';

  @override
  String get memoryContentHint => 'Rad imam jesti sladoled...';

  @override
  String get failedToSaveMemory => 'Shranjevanje ni uspelo. Prosimo preverite vašo povezavo.';

  @override
  String get saveMemory => 'Shrani spomin';

  @override
  String get retry => 'Poskusite znova';

  @override
  String get createActionItem => 'Ustvari opravilo';

  @override
  String get editActionItem => 'Uredi opravilo';

  @override
  String get actionItemDescriptionHint => 'Kaj je treba storiti?';

  @override
  String get actionItemDescriptionEmpty => 'Opis opravila ne sme biti prazen.';

  @override
  String get actionItemUpdated => 'Opravilo je posodobljeno';

  @override
  String get failedToUpdateActionItem => 'Posodobljenje opravila ni uspelo';

  @override
  String get actionItemCreated => 'Opravilo je ustvarjeno';

  @override
  String get failedToCreateActionItem => 'Ustvarjanje opravila ni uspelo';

  @override
  String get dueDate => 'Rok';

  @override
  String get time => 'Čas';

  @override
  String get addDueDate => 'Dodaj rok';

  @override
  String get pressDoneToSave => 'Pritisnite konec za shranjevanje';

  @override
  String get pressDoneToCreate => 'Pritisnite konec za ustvarjanje';

  @override
  String get filterAll => 'Vsi';

  @override
  String get filterSystem => 'O vas';

  @override
  String get filterInteresting => 'Spoznanja';

  @override
  String get filterManual => 'Ročno';

  @override
  String get completed => 'Završeno';

  @override
  String get markComplete => 'Označi kot završeno';

  @override
  String get actionItemDeleted => 'Opravilo je izbrisano';

  @override
  String get failedToDeleteActionItem => 'Brisanje opravila ni uspelo';

  @override
  String get deleteActionItemConfirmTitle => 'Izbriši opravilo';

  @override
  String get deleteActionItemConfirmMessage => 'Ali ste prepričani, da želite izbrisati to opravilo?';

  @override
  String get appLanguage => 'Jezik aplikacije';

  @override
  String get appInterfaceSectionTitle => 'VMESNIK APLIKACIJE';

  @override
  String get speechTranscriptionSectionTitle => 'GOVOR IN TRANSKRIPCIJA';

  @override
  String get languageSettingsHelperText =>
      'Jezik aplikacije spreminja menuje in gumbe. Jezik govora vpliva na transkripcijo svojih posnetkov.';

  @override
  String get translationNotice => 'Obvestilo o prevodu';

  @override
  String get translationNoticeMessage =>
      'Omi prevaja pogovore v svoj primarni jezik. Posodobite ga kadar koli v Nastavitve → Profili.';

  @override
  String get pleaseCheckInternetConnection => 'Prosimo preverite internet povezavo in poskusite znova';

  @override
  String get pleaseSelectReason => 'Prosimo izberite razlog';

  @override
  String get tellUsMoreWhatWentWrong => 'Povejte nam več o tem, kaj je šlo narobe...';

  @override
  String get selectText => 'Izberite besedilo';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Omogočeno je največ $count ciljev';
  }

  @override
  String get conversationCannotBeMerged => 'Ta pogovor ne moremo spojiti (zaklenjen ali že spajanje)';

  @override
  String get pleaseEnterFolderName => 'Prosimo vnesite ime mape';

  @override
  String get failedToCreateFolder => 'Ustvarjanje mape ni uspelo';

  @override
  String get failedToUpdateFolder => 'Posodobljenje mape ni uspelo';

  @override
  String get folderName => 'Ime mape';

  @override
  String get descriptionOptional => 'Opis (izbirno)';

  @override
  String get failedToDeleteFolder => 'Brisanje mape je spodletelo';

  @override
  String get editFolder => 'Uredi mapo';

  @override
  String get deleteFolder => 'Izbriši mapo';

  @override
  String get transcriptCopiedToClipboard => 'Prepis je kopiran v odložišče';

  @override
  String get summaryCopiedToClipboard => 'Povzetek je kopiran v odložišče';

  @override
  String get conversationUrlCouldNotBeShared => 'URL pogovora ni bilo mogoče deliti.';

  @override
  String get urlCopiedToClipboard => 'URL je kopiran v odložišče';

  @override
  String get exportTranscript => 'Izvozi prepis';

  @override
  String get exportSummary => 'Izvozi povzetek';

  @override
  String get exportButton => 'Izvozi';

  @override
  String get actionItemsCopiedToClipboard => 'Akcijske točke so kopirane v odložišče';

  @override
  String get summarize => 'Povzemi';

  @override
  String get generateSummary => 'Ustvari povzetek';

  @override
  String get conversationNotFoundOrDeleted => 'Pogovor ni bil najden ali je bil izbrisan';

  @override
  String get deleteMemory => 'Izbriši spomin';

  @override
  String get thisActionCannotBeUndone => 'Tega dejanja ni mogoče razveljaviti.';

  @override
  String memoriesCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count spominov',
      one: '1 spomin',
      zero: '0 spominov',
    );
    return '$_temp0';
  }

  @override
  String get noMemoriesInCategory => 'V tej kategoriji ni še spominov';

  @override
  String get addYourFirstMemory => 'Dodaj svoj prvi spomin';

  @override
  String get firmwareDisconnectUsb => 'Odklopite USB';

  @override
  String get firmwareUsbWarning => 'Povezava USB med posodobitvami lahko poškoduje vašo napravo.';

  @override
  String get firmwareBatteryAbove15 => 'Baterija nad 15%';

  @override
  String get firmwareEnsureBattery => 'Zagotovite, da ima vaša naprava 15% baterije.';

  @override
  String get firmwareStableConnection => 'Stabilna povezava';

  @override
  String get firmwareConnectWifi => 'Povežite se z WiFi ali mobilno mrežo.';

  @override
  String failedToStartUpdate(String error) {
    return 'Pričetek posodobitve je spodletel: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Pred posodobitvijo se prepričajte:';

  @override
  String get confirmed => 'Potrjeno!';

  @override
  String get release => 'Izpust';

  @override
  String get slideToUpdate => 'Drsni za posodobitev';

  @override
  String copiedToClipboard(String title) {
    return '$title je kopiran v odložišče';
  }

  @override
  String get batteryLevel => 'Raven baterije';

  @override
  String get charging => 'Polnjenje';

  @override
  String get productUpdate => 'Posodobitev proizvoda';

  @override
  String get offline => 'Brez povezave';

  @override
  String get available => 'Dostopno';

  @override
  String get unpairDeviceDialogTitle => 'Nepovežite napravo';

  @override
  String get unpairDeviceDialogMessage =>
      'To bo nepovezalo napravo, da jo je mogoče povezati z drugim telefonom. Pojdite na Nastavitve > Bluetooth in pozabite napravo, da dokončate postopek.';

  @override
  String get unpair => 'Nepoveži';

  @override
  String get unpairAndForgetDevice => 'Nepoveži in pozabi napravo';

  @override
  String get unknownDevice => 'Neznano';

  @override
  String get unknown => 'Neznano';

  @override
  String get productName => 'Ime proizvoda';

  @override
  String get serialNumber => 'Serijska številka';

  @override
  String get connected => 'Povezano';

  @override
  String get privacyPolicyTitle => 'Politika zasebnosti';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label je kopiran';
  }

  @override
  String get noApiKeysYet => 'Še ni API ključev';

  @override
  String get createKeyToGetStarted => 'Ustvarite ključ, da začnete';

  @override
  String get configureSttProvider => 'Nastavite ponudnika STT';

  @override
  String get setWhenConversationsAutoEnd => 'Nastavite, kdaj se pogovori samodejno končajo';

  @override
  String get importDataFromOtherSources => 'Uvozite podatke iz drugih virov';

  @override
  String get debugAndDiagnostics => 'Odpravljanje napak in diagnostika';

  @override
  String get autoDeletesAfter3Days => 'Samodejno izbris po 3 dneh.';

  @override
  String get helpsDiagnoseIssues => 'Pomaga pri diagnosticiranju težav';

  @override
  String get exportStartedMessage => 'Izvoz je začet. To lahko traja nekaj sekund...';

  @override
  String get exportConversationsToJson => 'Izvozite pogovore v datoteko JSON';

  @override
  String get knowledgeGraphDeletedSuccess => 'Grafikon znanja je uspešno izbrisan';

  @override
  String failedToDeleteGraph(String error) {
    return 'Brisanje grafikona je spodletelo: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Počisti vse vozlišča in povezave';

  @override
  String get addToClaudeDesktopConfig => 'Dodaj v claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Povežite AI asistente s svojimi podatki';

  @override
  String get useYourMcpApiKey => 'Uporabite svoj MCP API ključ';

  @override
  String get realTimeTranscript => 'Prepis v realnem času';

  @override
  String get experimental => 'Eksperimentalno';

  @override
  String get transcriptionDiagnostics => 'Diagnostika transkripcije';

  @override
  String get detailedDiagnosticMessages => 'Podrobna diagnostična sporočila';

  @override
  String get autoCreateSpeakers => 'Samodejno ustvari govorce';

  @override
  String get autoCreateWhenNameDetected => 'Samodejno ustvari, ko je ime zaznano';

  @override
  String get followUpQuestions => 'Nadaljujoča vprašanja';

  @override
  String get suggestQuestionsAfterConversations => 'Predlagaj vprašanja po pogovorih';

  @override
  String get goalTracker => 'Sledilnik ciljev';

  @override
  String get trackPersonalGoalsOnHomepage => 'Sledite svojim osebnim ciljem na domači strani';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Opis akcijske točke ne sme biti prazen';

  @override
  String get saved => 'Shranjeno';

  @override
  String get overdue => 'Zamujeno';

  @override
  String get failedToUpdateDueDate => 'Posodabljanje datuma roka je spodletelo';

  @override
  String get markIncomplete => 'Označi kot nepopolno';

  @override
  String get editDueDate => 'Uredi rok';

  @override
  String get setDueDate => 'Nastavi rok';

  @override
  String get clearDueDate => 'Počisti rok';

  @override
  String get failedToClearDueDate => 'Počiščevanje roka je spodletelo';

  @override
  String get mondayAbbr => 'Pon';

  @override
  String get tuesdayAbbr => 'Tor';

  @override
  String get wednesdayAbbr => 'Sre';

  @override
  String get thursdayAbbr => 'Čet';

  @override
  String get fridayAbbr => 'Pet';

  @override
  String get saturdayAbbr => 'Sob';

  @override
  String get sundayAbbr => 'Ned';

  @override
  String get howDoesItWork => 'Kako deluje?';

  @override
  String get sdCardSyncDescription => 'Sinhronizacija SD kartice bo uvozila vaše spomine s SD kartice v aplikacijo';

  @override
  String get checksForAudioFiles => 'Preveri zvočne datoteke na SD kartici';

  @override
  String get omiSyncsAudioFiles => 'Omi nato sinhronizira zvočne datoteke s strežnikom';

  @override
  String get serverProcessesAudio => 'Strežnik obdela zvočne datoteke in ustvari spomine';

  @override
  String get youreAllSet => 'Vse je pripravljeno!';

  @override
  String get welcomeToOmiDescription =>
      'Dobrodošli v Omi! Vaš AI spremljevalec je pripravljen, da vam pomaga s pogovori, nalogami in še več.';

  @override
  String get startUsingOmi => 'Začni uporabljati Omi';

  @override
  String get back => 'Nazaj';

  @override
  String get keyboardShortcuts => 'Bližnjice na tipkovnici';

  @override
  String get toggleControlBar => 'Preklopi kontrolno vrstico';

  @override
  String get pressKeys => 'Pritisni tipke...';

  @override
  String get cmdRequired => '⌘ obavezno';

  @override
  String get invalidKey => 'Neveljavna tipka';

  @override
  String get space => 'Presledek';

  @override
  String get search => 'Iskanje';

  @override
  String get searchPlaceholder => 'Iskanje...';

  @override
  String get untitledConversation => 'Neimenovan pogovor';

  @override
  String countRemaining(String count) {
    return '$count ostane';
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
  String get current => 'Trenutno';

  @override
  String get target => 'Cilj';

  @override
  String get saveGoal => 'Shrani';

  @override
  String get goals => 'Cilji';

  @override
  String get tapToAddGoal => 'Dotakni se, da dodaš cilj';

  @override
  String welcomeBack(String name) {
    return 'Dobrodošel nazaj, $name';
  }

  @override
  String get yourConversations => 'Vaši pogovori';

  @override
  String get reviewAndManageConversations => 'Preglejte in upravljajte svoje zajete pogovore';

  @override
  String get startCapturingConversations => 'Začnite zajemati pogovore s svojo napravo Omi, da jih vidite tukaj.';

  @override
  String get useMobileAppToCapture => 'Uporabite mobilno aplikacijo, da zajamete zvok';

  @override
  String get conversationsProcessedAutomatically => 'Pogovori se obdelajo samodejno';

  @override
  String get getInsightsInstantly => 'Takoj prejmi vpoglede in povzetke';

  @override
  String get showAll => 'Prikaži vse';

  @override
  String get noTasksForToday => 'Danes ni nalog.\nPoprosi Omi za več nalog ali jih ustvari ročno.';

  @override
  String get dailyScore => 'DNEVNA OCENA';

  @override
  String get dailyScoreDescription => 'Ocena, ki ti pomaga bolje\nosredotočiti se na izvajanje.';

  @override
  String get searchResults => 'Rezultati iskanja';

  @override
  String get actionItems => 'Akcijske točke';

  @override
  String get tasksToday => 'Danes';

  @override
  String get tasksTomorrow => 'Jutri';

  @override
  String get tasksNoDeadline => 'Brez roka';

  @override
  String get tasksLater => 'Kasneje';

  @override
  String get loadingTasks => 'Naloge se nalagajo...';

  @override
  String get tasks => 'Naloge';

  @override
  String get swipeTasksToIndent => 'Povlecite naloge, da jih preuredite, vlečite med kategorije';

  @override
  String get create => 'Ustvari';

  @override
  String get noTasksYet => 'Še ni nalog';

  @override
  String get tasksFromConversationsWillAppear =>
      'Naloge iz svojih pogovorov se bodo pojavile tukaj.\nKlikni Ustvari, da jo dodaš ročno.';

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
  String get actionItemUpdatedSuccessfully => 'Akcijska točka je bila uspešno posodobljena';

  @override
  String get actionItemCreatedSuccessfully => 'Akcijska točka je bila uspešno ustvarjena';

  @override
  String get actionItemDeletedSuccessfully => 'Akcijska točka je bila uspešno izbrisana';

  @override
  String get deleteActionItem => 'Izbriši akcijsko točko';

  @override
  String get deleteActionItemConfirmation =>
      'Ali ste prepričani, da želite izbrisati to akcijsko točko? Tega dejanja ni mogoče razveljaviti.';

  @override
  String get enterActionItemDescription => 'Vnesite opis akcijske točke...';

  @override
  String get markAsCompleted => 'Označi kot dokončano';

  @override
  String get setDueDateAndTime => 'Nastavi rok in čas';

  @override
  String get reloadingApps => 'Aplikacije se ponovno nalagajo...';

  @override
  String get loadingApps => 'Aplikacije se nalagajo...';

  @override
  String get browseInstallCreateApps => 'Brskajte, namestite in ustvarite aplikacije';

  @override
  String get all => 'Vse';

  @override
  String get open => 'Odpri';

  @override
  String get install => 'Namesti';

  @override
  String get noAppsAvailable => 'Ni dostopnih aplikacij';

  @override
  String get unableToLoadApps => 'Ni mogoče naložiti aplikacij';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Poskusite prilagoditi iskalne izraze ali filtre';

  @override
  String get checkBackLaterForNewApps => 'Kasneje se vrnite za nove aplikacije';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Preverite svojo internetno povezavo in poskusite znova';

  @override
  String get createNewApp => 'Ustvari novo aplikacijo';

  @override
  String get buildSubmitCustomOmiApp => 'Zgradite in pošljite svojo prilagojeno Omi aplikacijo';

  @override
  String get submittingYourApp => 'Vaša aplikacija se pošilja...';

  @override
  String get preparingFormForYou => 'Obrazec se pripravlja za vas...';

  @override
  String get appDetails => 'Podrobnosti aplikacije';

  @override
  String get paymentDetails => 'Podrobnosti plačila';

  @override
  String get previewAndScreenshots => 'Predogled in slike zaslona';

  @override
  String get appCapabilities => 'Zmožnosti aplikacije';

  @override
  String get aiPrompts => 'AI pozivi';

  @override
  String get chatPrompt => 'Poziv za klepet';

  @override
  String get chatPromptPlaceholder =>
      'Vsi ste odličan aplikacija, vaša naloga je odgovarjati na vprašanja uporabnika in jih narediti srečne...';

  @override
  String get conversationPrompt => 'Poziv za pogovor';

  @override
  String get conversationPromptPlaceholder => 'Vsi ste odličan aplikacija, dobili boste prepis in povzetek pogovora...';

  @override
  String get notificationScopes => 'Obsegi obvestil';

  @override
  String get appPrivacyAndTerms => 'Zasebnost in pogoji aplikacije';

  @override
  String get makeMyAppPublic => 'Naredi svojo aplikacijo javno';

  @override
  String get submitAppTermsAgreement =>
      'S predložitvijo te aplikacije se strinjam s pogoji storitve in politiko zasebnosti Omi AI';

  @override
  String get submitApp => 'Pošlji aplikacijo';

  @override
  String get needHelpGettingStarted => 'Potrebuješ pomoč za začetek?';

  @override
  String get clickHereForAppBuildingGuides => 'Klikni tukaj za vodnike za gradnjo aplikacij in dokumentacijo';

  @override
  String get submitAppQuestion => 'Pošlji aplikacijo?';

  @override
  String get submitAppPublicDescription =>
      'Vaša aplikacija bo pregledana in narejena javna. Lahko jo začnete uporabljati takoj, tudi med pregledom!';

  @override
  String get submitAppPrivateDescription =>
      'Vaša aplikacija bo pregledana in vam bo dostopna zasebno. Lahko jo začnete uporabljati takoj, tudi med pregledom!';

  @override
  String get startEarning => 'Začni zaslužavati! 💰';

  @override
  String get connectStripeOrPayPal => 'Povežite Stripe ali PayPal, da sprejmete plačila za svojo aplikacijo.';

  @override
  String get connectNow => 'Povežite se zdaj';

  @override
  String get installsCount => 'Namestitve';

  @override
  String get uninstallApp => 'Odnamesti aplikacijo';

  @override
  String get subscribe => 'Naroči se';

  @override
  String get dataAccessNotice => 'Obvestilo o dostopu do podatkov';

  @override
  String get dataAccessWarning =>
      'Ta aplikacija bo dostopala do vaših podatkov. Omi AI ni odgovoren za to, kako so vaši podatki uporabljeni, spremenjeni ali izbrisani s stran te aplikacije';

  @override
  String get installApp => 'Namesti aplikacijo';

  @override
  String get betaTesterNotice => 'Ste beta tester te aplikacije. Še ni javna. Javna bo, ko bo odobrena.';

  @override
  String get appUnderReviewOwner => 'Vaša aplikacija je v pregledu in vidna samo vam. Javna bo, ko bo odobrena.';

  @override
  String get appRejectedNotice =>
      'Vaša aplikacija je bila zavrnjena. Prosimo, posodobite podrobnosti aplikacije in ponovno predložite v pregled.';

  @override
  String get setupSteps => 'Koraki nastavitve';

  @override
  String get setupInstructions => 'Navodila za nastavitev';

  @override
  String get integrationInstructions => 'Navodila za integracijo';

  @override
  String get preview => 'Predogled';

  @override
  String get aboutTheApp => 'O aplikaciji';

  @override
  String get chatPersonality => 'Osebnost klepeta';

  @override
  String get ratingsAndReviews => 'Ocene in ocene';

  @override
  String get noRatings => 'brez ocen';

  @override
  String ratingsCount(String count) {
    return '$count+ ocen';
  }

  @override
  String get errorActivatingApp => 'Napaka pri aktiviranju aplikacije';

  @override
  String get integrationSetupRequired =>
      'Če je to integracijska aplikacija, se prepričajte, da je nastavitev dokončana.';

  @override
  String get installed => 'Nameščeno';

  @override
  String get appIdLabel => 'ID aplikacije';

  @override
  String get appNameLabel => 'Ime aplikacije';

  @override
  String get appNamePlaceholder => 'Moja odlična aplikacija';

  @override
  String get pleaseEnterAppName => 'Prosimo, vnesite ime aplikacije';

  @override
  String get categoryLabel => 'Kategorija';

  @override
  String get selectCategory => 'Izberite kategorijo';

  @override
  String get descriptionLabel => 'Opis';

  @override
  String get appDescriptionPlaceholder =>
      'Moja odlična aplikacija je odličen aplikacija, ki počne čudovite stvari. To je najboljša aplikacija vseh časov!';

  @override
  String get pleaseProvideValidDescription => 'Prosimo, navedite veljaven opis';

  @override
  String get appPricingLabel => 'Cena aplikacije';

  @override
  String get noneSelected => 'Nič ni izbrano';

  @override
  String get appIdCopiedToClipboard => 'ID aplikacije je kopiran v odložišče';

  @override
  String get appCategoryModalTitle => 'Kategorija aplikacije';

  @override
  String get pricingFree => 'Brezplačno';

  @override
  String get pricingPaid => 'Plačano';

  @override
  String get loadingCapabilities => 'Zmožnosti se nalagajo...';

  @override
  String get filterInstalled => 'Nameščeno';

  @override
  String get filterMyApps => 'Moje aplikacije';

  @override
  String get clearSelection => 'Počisti izbor';

  @override
  String get filterCategory => 'Kategorija';

  @override
  String get rating4PlusStars => '4+ zvezde';

  @override
  String get rating3PlusStars => '3+ zvezde';

  @override
  String get rating2PlusStars => '2+ zvezde';

  @override
  String get rating1PlusStars => '1+ zvezdica';

  @override
  String get filterRating => 'Ocena';

  @override
  String get filterCapabilities => 'Zmožnosti';

  @override
  String get noNotificationScopesAvailable => 'Ni dostopnih obsegov obvestil';

  @override
  String get popularApps => 'Priljubljene aplikacije';

  @override
  String get pleaseProvidePrompt => 'Prosimo, navedite poziv';

  @override
  String chatWithAppName(String appName) {
    return 'Pogovori se s $appName';
  }

  @override
  String get defaultAiAssistant => 'Privzeti AI pomočnik';

  @override
  String get readyToChat => '✨ Pripravljen za klepet!';

  @override
  String get connectionNeeded => '🌐 Potrebna je povezava';

  @override
  String get startConversation => 'Začni pogovor in pusti čaradi, da se dogaja';

  @override
  String get checkInternetConnection => 'Prosimo, preverite svojo internetno povezavo';

  @override
  String get wasThisHelpful => 'Je bilo to koristno?';

  @override
  String get thankYouForFeedback => 'Hvala za vašo povratno informacijo!';

  @override
  String get maxFilesUploadError => 'Naenkrat lahko naložite samo 4 datoteke';

  @override
  String get attachedFiles => '📎 Priložene datoteke';

  @override
  String get takePhoto => 'Fotkaj';

  @override
  String get captureWithCamera => 'Zajemi s kamero';

  @override
  String get selectImages => 'Izberite slike';

  @override
  String get chooseFromGallery => 'Izberite iz galerije';

  @override
  String get selectFile => 'Izberite datoteko';

  @override
  String get chooseAnyFileType => 'Izberite kateri koli tip datoteke';

  @override
  String get cannotReportOwnMessages => 'Svoje sporočila ne morete prijaviti';

  @override
  String get messageReportedSuccessfully => '✅ Sporočilo je bilo uspešno prijavljeno';

  @override
  String get confirmReportMessage => 'Ali ste prepričani, da želite prijaviti to sporočilo?';

  @override
  String get selectChatAssistant => 'Izberite pomočnika za klepet';

  @override
  String get enableMoreApps => 'Omogoči več aplikacij';

  @override
  String get chatCleared => 'Klepet je počišten';

  @override
  String get clearChatTitle => 'Počisti klepet?';

  @override
  String get confirmClearChat => 'Ali ste prepričani, da želite počistiti klepet? Tega dejanja ni mogoče razveljaviti.';

  @override
  String get copy => 'Kopiraj';

  @override
  String get share => 'Deli';

  @override
  String get report => 'Prijavi';

  @override
  String get microphonePermissionRequired => 'Dovoljenj za mikrofon je potrebno za klice';

  @override
  String get microphonePermissionDenied =>
      'Dovoljenj za mikrofon je zavrnjeno. Prosimo, dajte dovoljenje v Sistemskih nastavitvah > Zasebnost in varnost > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Preverjanje dovoljenj za mikrofon je spodletelo: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Transkripcija zvoka je spodletela';

  @override
  String get transcribing => 'Prepisovanje...';

  @override
  String get transcriptionFailed => 'Transkripcija je spodletela';

  @override
  String get discardedConversation => 'Zavrnjen pogovor';

  @override
  String get at => 'ob';

  @override
  String get from => 'od';

  @override
  String get copied => 'Kopirano!';

  @override
  String get copyLink => 'Kopiraj povezavo';

  @override
  String get hideTranscript => 'Skrij prepis';

  @override
  String get viewTranscript => 'Oglejte si prepis';

  @override
  String get conversationDetails => 'Podrobnosti pogovora';

  @override
  String get transcript => 'Prepis';

  @override
  String segmentsCount(int count) {
    return '$count segmentov';
  }

  @override
  String get noTranscriptAvailable => 'Prepis ni na voljo';

  @override
  String get noTranscriptMessage => 'Ta pogovor nima prepisa.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'URL pogovora ni bilo mogoče ustvariti.';

  @override
  String get failedToGenerateConversationLink => 'Ustvarjanje povezave pogovora je spodletelo';

  @override
  String get failedToGenerateShareLink => 'Ustvarjanje povezave za deljenje je spodletelo';

  @override
  String get reloadingConversations => 'Pogovori se ponovno nalagajo...';

  @override
  String get user => 'Uporabnik';

  @override
  String get starred => 'Označeni z zvezdico';

  @override
  String get date => 'Datum';

  @override
  String get noResultsFound => 'Ni rezultatov';

  @override
  String get tryAdjustingSearchTerms => 'Poskusite prilagoditi iskalne izraze';

  @override
  String get starConversationsToFindQuickly => 'Označite pogovore z zvezdico, da jih hitro najdete tukaj';

  @override
  String noConversationsOnDate(String date) {
    return 'Nič pogovorov na $date';
  }

  @override
  String get trySelectingDifferentDate => 'Poskusite izbrati drugačen datum';

  @override
  String get conversations => 'Pogovori';

  @override
  String get chat => 'Klepet';

  @override
  String get actions => 'Dejanja';

  @override
  String get syncAvailable => 'Sinhronizacija je dostopna';

  @override
  String get referAFriend => 'Priporočite prijatelja';

  @override
  String get help => 'Pomoč';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Nadgradi na Pro';

  @override
  String get getOmiDevice => 'Pridobi napravo Omi';

  @override
  String get wearableAiCompanion => 'Nošljiv AI spremljevalec';

  @override
  String get loadingMemories => 'Spomin se nalagajo...';

  @override
  String get allMemories => 'Vsi spomini';

  @override
  String get aboutYou => 'O tebi';

  @override
  String get manual => 'Ročno';

  @override
  String get loadingYourMemories => 'Vaši spomini se nalagajo...';

  @override
  String get createYourFirstMemory => 'Ustvari svoj prvi spomin, da začneš';

  @override
  String get tryAdjustingFilter => 'Poskusite prilagoditi iskanje ali filter';

  @override
  String get whatWouldYouLikeToRemember => 'Kaj bi se rad spomnил?';

  @override
  String get category => 'Kategorija';

  @override
  String get public => 'Javno';

  @override
  String get failedToSaveCheckConnection => 'Shranjevanje je spodletelo. Prosimo, preverite svojo povezavo.';

  @override
  String get createMemory => 'Ustvari spomin';

  @override
  String get deleteMemoryConfirmation =>
      'Ali ste prepričani, da želite izbrisati ta spomin? Tega dejanja ni mogoče razveljaviti.';

  @override
  String get makePrivate => 'Naredi zasebno';

  @override
  String get organizeAndControlMemories => 'Organizirajte in nadzorujte svoje spomine';

  @override
  String get total => 'Skupno';

  @override
  String get makeAllMemoriesPrivate => 'Naredi vse spomine zasebne';

  @override
  String get setAllMemoriesToPrivate => 'Nastavi vse spomine na zasebno vidljivost';

  @override
  String get makeAllMemoriesPublic => 'Naredi vse spomine javne';

  @override
  String get setAllMemoriesToPublic => 'Nastavi vse spomine na javno vidljivost';

  @override
  String get permanentlyRemoveAllMemories => 'Trajno odstrani vse spomine iz Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Vsi spomini so zdaj zasebni';

  @override
  String get allMemoriesAreNowPublic => 'Vsi spomini so zdaj javni';

  @override
  String get clearOmisMemory => 'Počisti Omijin spomin';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Ali ste prepričani, da želite počistiti Omijin spomin? Tega dejanja ni mogoče razveljaviti in trajno izbriše vse $count spominov.';
  }

  @override
  String get omisMemoryCleared => 'Omijin spomin o tebi je bil počišten';

  @override
  String get welcomeToOmi => 'Dobrodošli v Omi';

  @override
  String get continueWithApple => 'Nadaljuj s pomočjo Apple';

  @override
  String get continueWithGoogle => 'Nadaljuj s Google';

  @override
  String get byContinuingYouAgree => 'Z nadaljevanjem se strinjate z našimi ';

  @override
  String get termsOfService => 'Pogoji storitve';

  @override
  String get and => ' in ';

  @override
  String get dataAndPrivacy => 'Podatki in zasebnost';

  @override
  String get secureAuthViaAppleId => 'Varno avtentifikacijo prek Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Varno avtentifikacijo prek Google računa';

  @override
  String get whatWeCollect => 'Kaj zbiramo';

  @override
  String get dataCollectionMessage =>
      'Z nadaljevanjem bodo vaši pogovori, posnetki in osebni podatki varno shranjeni na naših strežnikih, da bi vam omogočili rezultate na osnovi umetne inteligence in vse funkcije aplikacije.';

  @override
  String get dataProtection => 'Zaščita podatkov';

  @override
  String get yourDataIsProtected => 'Vaši podatki so zaščiteni in vodeni s strani našega ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Prosimo, izberite svoj primarni jezik';

  @override
  String get chooseYourLanguage => 'Izberite svoj jezik';

  @override
  String get selectPreferredLanguageForBestExperience => 'Izberite svoj izbrani jezik za najboljšo izkušnjo z Omi';

  @override
  String get searchLanguages => 'Iskanje jezikov...';

  @override
  String get selectALanguage => 'Izberite jezik';

  @override
  String get tryDifferentSearchTerm => 'Poskusite z drugim iskalnim izrazom';

  @override
  String get pleaseEnterYourName => 'Prosimo, vnesite svoje ime';

  @override
  String get nameMustBeAtLeast2Characters => 'Ime mora imeti najmanj 2 znaka';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Povejte nam, kako vas želite nagovarjati. To pomaga pri personalizaciji vaše izkušnje z Omi.';

  @override
  String charactersCount(int count) {
    return '$count znakov';
  }

  @override
  String get enableFeaturesForBestExperience => 'Omogočite funkcije za najboljšo izkušnjo z Omi na vaši napravi.';

  @override
  String get microphoneAccess => 'Dostop do mikrofona';

  @override
  String get recordAudioConversations => 'Snemanje audio pogovorov';

  @override
  String get microphoneAccessDescription =>
      'Omi potrebuje dostop do mikrofona za snemanje vaših pogovorov in zagotavljanje prepisov.';

  @override
  String get screenRecording => 'Snemanje zaslona';

  @override
  String get captureSystemAudioFromMeetings => 'Zajemanje sistemskega zvoka s srečanj';

  @override
  String get screenRecordingDescription =>
      'Omi potrebuje dovoljenježe za snemanje zaslona, da bi zajel sistemski zvok iz vaših srečanj v brskalnikih.';

  @override
  String get accessibility => 'Dostopnost';

  @override
  String get detectBrowserBasedMeetings => 'Zaznavanje srečanj v brskalniku';

  @override
  String get accessibilityDescription =>
      'Omi potrebuje dovoljenje za dostopnost za zaznavanje, ko se pridružite srečanjem Zoom, Meet ali Teams v vašem brskalniku.';

  @override
  String get pleaseWait => 'Prosimo, počakajte...';

  @override
  String get joinTheCommunity => 'Pridružite se skupnosti!';

  @override
  String get loadingProfile => 'Nalaganje profila...';

  @override
  String get profileSettings => 'Nastavitve profila';

  @override
  String get noEmailSet => 'Ni nastavljene e-pošte';

  @override
  String get userIdCopiedToClipboard => 'ID uporabnika kopiran v odložišče';

  @override
  String get yourInformation => 'Vaši podatki';

  @override
  String get setYourName => 'Nastavite svoje ime';

  @override
  String get changeYourName => 'Spremenite svoje ime';

  @override
  String get voiceAndPeople => 'Glas in ljudje';

  @override
  String get teachOmiYourVoice => 'Naučite Omi vašega glasu';

  @override
  String get tellOmiWhoSaidIt => 'Povejte Omi, kdo je to rekel 🗣️';

  @override
  String get payment => 'Plačilo';

  @override
  String get addOrChangeYourPaymentMethod => 'Dodajte ali spremenite svoj način plačila';

  @override
  String get preferences => 'Preference';

  @override
  String get helpImproveOmiBySharing => 'Pomagajte izboljšati Omi z deljenjem anonimizirane analitike';

  @override
  String get deleteAccount => 'Izbris računa';

  @override
  String get deleteYourAccountAndAllData => 'Izbrišite svoj račun in vse podatke';

  @override
  String get clearLogs => 'Briši dnevnike';

  @override
  String get debugLogsCleared => 'Dnevniki za odpravljanje napak so izbrisani';

  @override
  String get exportConversations => 'Izvoz pogovorov';

  @override
  String get exportAllConversationsToJson => 'Izvozite vse svoje pogovore v JSON datoteko.';

  @override
  String get conversationsExportStarted => 'Izvoz pogovorov je začet. To lahko traja nekaj sekund, prosimo počakajte.';

  @override
  String get mcpDescription =>
      'Če želite Omi povezati z drugimi aplikacijami za branje, iskanje in upravljanje vaših spomin in pogovorov. Ustvarite ključ, da bi se začeli.';

  @override
  String get apiKeys => 'Ključi API';

  @override
  String errorLabel(String error) {
    return 'Napaka: $error';
  }

  @override
  String get noApiKeysFound => 'Nobenih ključev API ni zajetih. Ustvarite enega, da bi se začeli.';

  @override
  String get advancedSettings => 'Napredne nastavitve';

  @override
  String get triggersWhenNewConversationCreated => 'Se sproži, ko je ustvarjen nov pogovor.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Se sproži, ko je prejeta nova prepis.';

  @override
  String get realtimeAudioBytes => 'Realčasni audio bajti';

  @override
  String get triggersWhenAudioBytesReceived => 'Se sproži, ko so prejeti audio bajti.';

  @override
  String get everyXSeconds => 'Vsako x sekund';

  @override
  String get triggersWhenDaySummaryGenerated => 'Se sproži, ko je generiran povzetek dneva.';

  @override
  String get tryLatestExperimentalFeatures => 'Poskusite najnovejše eksperimentalne funkcije Omi tima.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'Diagnostični status storitve prepisa';

  @override
  String get enableDetailedDiagnosticMessages => 'Omogočite podrobna diagnostična sporočila iz storitve prepisa';

  @override
  String get autoCreateAndTagNewSpeakers => 'Samodejna ustvaritev in označevanje novih govorcev';

  @override
  String get automaticallyCreateNewPerson => 'Samodejno ustvarite novo osebo, ko je ime zaznano v prepisu.';

  @override
  String get pilotFeatures => 'Pilot funkcije';

  @override
  String get pilotFeaturesDescription => 'Te funkcije so poskusi in nobena podpora ni zagotovljena.';

  @override
  String get suggestFollowUpQuestion => 'Predlagaj vprašanje za nadaljevanje';

  @override
  String get saveSettings => 'Shrani nastavitve';

  @override
  String get syncingDeveloperSettings => 'Usklajujem nastavitve razvijalca...';

  @override
  String get summary => 'Povzetek';

  @override
  String get auto => 'Samodejno';

  @override
  String get noSummaryForApp =>
      'Za to aplikacijo ni dostopnega povzetka. Poskusite z drugo aplikacijo za boljše rezultate.';

  @override
  String get tryAnotherApp => 'Poskusite drugo aplikacijo';

  @override
  String generatedBy(String appName) {
    return 'Generirano s strani $appName';
  }

  @override
  String get overview => 'Pregled';

  @override
  String get otherAppResults => 'Rezultati drugih aplikacij';

  @override
  String get unknownApp => 'Neznana aplikacija';

  @override
  String get noSummaryAvailable => 'Povzetek ni dostopen';

  @override
  String get conversationNoSummaryYet => 'Ta pogovor še nima povzetka.';

  @override
  String get chooseSummarizationApp => 'Izberite aplikacijo za povzetke';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName je nastavljena kot privzeta aplikacija za povzetke';
  }

  @override
  String get letOmiChooseAutomatically => 'Pusti Omi, da samodejno izbere najboljšo aplikacijo';

  @override
  String get deleteConversationConfirmation =>
      'Ste prepričani, da želite izbrisati ta pogovor? Te akcije ni mogoče razveljaviti.';

  @override
  String get conversationDeleted => 'Pogovor je izbrisan';

  @override
  String get generatingLink => 'Generiranje povezave...';

  @override
  String get editConversation => 'Uredite pogovor';

  @override
  String get conversationLinkCopiedToClipboard => 'Povezava pogovora je kopirana v odložišče';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Prepis pogovora je kopiran v odložišče';

  @override
  String get editConversationDialogTitle => 'Uredi pogovor';

  @override
  String get changeTheConversationTitle => 'Spremenite naslov pogovora';

  @override
  String get conversationTitle => 'Naslov pogovora';

  @override
  String get enterConversationTitle => 'Vnesite naslov pogovora...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Naslov pogovora je uspešno posodobljen';

  @override
  String get failedToUpdateConversationTitle => 'Neuspešna posodobitev naslova pogovora';

  @override
  String get errorUpdatingConversationTitle => 'Napaka pri posodabljanju naslova pogovora';

  @override
  String get settingUp => 'Nastavljam...';

  @override
  String get startYourFirstRecording => 'Začni svoj prvi posnetek';

  @override
  String get preparingSystemAudioCapture => 'Priprava zajemanja sistemskega zvoka';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Kliknite gumb za zajemanje zvoka za žive prepise, umetne inteligence in samodejno shranjevanje.';

  @override
  String get reconnecting => 'Ponovno povezovanje...';

  @override
  String get recordingPaused => 'Snemanje je ustavljeno';

  @override
  String get recordingActive => 'Snemanje je aktivno';

  @override
  String get startRecording => 'Začni snemanje';

  @override
  String resumingInCountdown(String countdown) {
    return 'Nadaljujem v ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Tapnite predvajanje za nadaljevanje';

  @override
  String get listeningForAudio => 'Poslušanje zvoka...';

  @override
  String get preparingAudioCapture => 'Priprava zajemanja zvoka';

  @override
  String get clickToBeginRecording => 'Kliknite za začetek snemanja';

  @override
  String get translated => 'prevod';

  @override
  String get liveTranscript => 'Živi prepis';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenti';
  }

  @override
  String get startRecordingToSeeTranscript => 'Začni snemanje, da vidiš živi prepis';

  @override
  String get paused => 'Ustavljeno';

  @override
  String get initializing => 'Inicializacija...';

  @override
  String get recording => 'Snemanje';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon se je spremenil. Nadaljujem v ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Kliknite predvajanje za nadaljevanje ali stop za konec';

  @override
  String get settingUpSystemAudioCapture => 'Nastavljanje zajemanja sistemskega zvoka';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Zajemanje zvoka in generiranje prepisa';

  @override
  String get clickToBeginRecordingSystemAudio => 'Kliknite za začetek snemanja sistemskega zvoka';

  @override
  String get you => 'Ti';

  @override
  String speakerWithId(String speakerId) {
    return 'Govorec $speakerId';
  }

  @override
  String get translatedByOmi => 'prevod s strani omi';

  @override
  String get backToConversations => 'Nazaj na pogovore';

  @override
  String get systemAudio => 'Sistem';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Audio vhod je nastavljen na $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Napaka pri preklopu audio naprave: $error';
  }

  @override
  String get selectAudioInput => 'Izberite audio vhod';

  @override
  String get loadingDevices => 'Nalaganje naprav...';

  @override
  String get settingsHeader => 'NASTAVITVE';

  @override
  String get plansAndBilling => 'Načrti in obračun';

  @override
  String get calendarIntegration => 'Integracija koledarja';

  @override
  String get dailySummary => 'Dnevni povzetek';

  @override
  String get developer => 'Razvijalec';

  @override
  String get about => 'O nas';

  @override
  String get selectTime => 'Izberite čas';

  @override
  String get accountGroup => 'Račun';

  @override
  String get signOutQuestion => 'Odjava?';

  @override
  String get signOutConfirmation => 'Ste prepričani, da želite odjaviti?';

  @override
  String get customVocabularyHeader => 'VLASTNI BESEDNJAK';

  @override
  String get addWordsDescription => 'Dodajte besede, ki bi jih Omi moral prepoznati med prepisom.';

  @override
  String get enterWordsHint => 'Vnesite besede (ločene z vejicami)';

  @override
  String get dailySummaryHeader => 'DNEVNI POVZETEK';

  @override
  String get dailySummaryTitle => 'Dnevni povzetek';

  @override
  String get dailySummaryDescription =>
      'Pridobite osebni povzetek pogovorov vašega dneva, dostavljenega kot obvestilo.';

  @override
  String get deliveryTime => 'Čas dostave';

  @override
  String get deliveryTimeDescription => 'Kdaj prejeti dnevni povzetek';

  @override
  String get subscription => 'Naročnina';

  @override
  String get viewPlansAndUsage => 'Oglejte si načrte in uporabo';

  @override
  String get viewPlansDescription => 'Upravljajte s svojo naročnino in si oglejte statistiko uporabe';

  @override
  String get addOrChangePaymentMethod => 'Dodajte ali spremenite svoj način plačila';

  @override
  String get displayOptions => 'Možnosti prikaza';

  @override
  String get showMeetingsInMenuBar => 'Prikaži srečanja v menijski vrstici';

  @override
  String get displayUpcomingMeetingsDescription => 'Prikaži prihajajočegai srečanja v menijski vrstici';

  @override
  String get showEventsWithoutParticipants => 'Prikaži dogodke brez udeležencev';

  @override
  String get includePersonalEventsDescription => 'Vključi osebne dogodke brez udeležencev';

  @override
  String get upcomingMeetings => 'Prihajajočega srečanja';

  @override
  String get checkingNext7Days => 'Preverjam naslednjih 7 dni';

  @override
  String get shortcuts => 'Bljižnice';

  @override
  String get shortcutChangeInstruction => 'Kliknite na bljižnico, da jo spremenite. Pritisnite Escape za preklic.';

  @override
  String get configureSTTProvider => 'Konfigurirajte ponudnika STT';

  @override
  String get setConversationEndDescription => 'Nastavite, kdaj se pogovori samodejno končajo';

  @override
  String get importDataDescription => 'Uvozite podatke iz drugih virov';

  @override
  String get exportConversationsDescription => 'Izvozite pogovore v JSON';

  @override
  String get exportingConversations => 'Izvažam pogovore...';

  @override
  String get clearNodesDescription => 'Izbrišite vse vozlišče in povezave';

  @override
  String get deleteKnowledgeGraphQuestion => 'Izbriši graf znanja?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'To bo izbrisalo vse izpeljane podatke grafa znanja. Vaši prvotni spomini ostajajo varni.';

  @override
  String get connectOmiWithAI => 'Povežite Omi s pomočniki umetne inteligence';

  @override
  String get noAPIKeys => 'Nobenih ključev API. Ustvarite enega, da bi se začeli.';

  @override
  String get autoCreateWhenDetected => 'Samodejna ustvaritev pri zaznavi imena';

  @override
  String get trackPersonalGoals => 'Sledite osebnim ciljem na domači strani';

  @override
  String get endpointURL => 'Končna točka URL';

  @override
  String get links => 'Povezave';

  @override
  String get discordMemberCount => '8000+ članov na Discordu';

  @override
  String get userInformation => 'Informacije o uporabniku';

  @override
  String get capabilities => 'Zmogljivosti';

  @override
  String get previewScreenshots => 'Predogled zaslonskih posnetkov';

  @override
  String get holdOnPreparingForm => 'Počakajte, pripravljamo obrazec za vas';

  @override
  String get bySubmittingYouAgreeToOmi => 'Z oddajo se strinjate z Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Pogoji in politika zasebnosti';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Pomaga pri diagnostiki težav. Samodejno se briše čez 3 dni.';

  @override
  String get manageYourApp => 'Upravljajte svojo aplikacijo';

  @override
  String get updatingYourApp => 'Posodabljam vašo aplikacijo';

  @override
  String get fetchingYourAppDetails => 'Pridobivam podatke vaše aplikacije';

  @override
  String get updateAppQuestion => 'Posodobi aplikacijo?';

  @override
  String get updateAppConfirmation =>
      'Ste prepričani, da želite posodobiti svojo aplikacijo? Spremembe se bodo odražale, ko jih pregleda naš tim.';

  @override
  String get updateApp => 'Posodobi aplikacijo';

  @override
  String get createAndSubmitNewApp => 'Ustvarite in oddajte novo aplikacijo';

  @override
  String appsCount(String count) {
    return 'Aplikacije ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Zasebne aplikacije ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Javne aplikacije ($count)';
  }

  @override
  String get newVersionAvailable => 'Nova različica dostopna 🎉';

  @override
  String get no => 'Ne';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Naročnina je uspešno preklicana. Ostane aktivna do konca trenutnega obračunskega obdobja.';

  @override
  String get failedToCancelSubscription => 'Neuspešno preklicanje naročnine. Prosimo, poskusite znova.';

  @override
  String get invalidPaymentUrl => 'Neveljavna URL plačila';

  @override
  String get permissionsAndTriggers => 'Dovoljenja in sprožilci';

  @override
  String get chatFeatures => 'Funkcije klepeta';

  @override
  String get uninstall => 'Odvzemi';

  @override
  String get installs => 'NAMESTITVE';

  @override
  String get priceLabel => 'CENA';

  @override
  String get updatedLabel => 'POSODOBLJENO';

  @override
  String get createdLabel => 'USTVARJENO';

  @override
  String get featuredLabel => 'ZNAČILNO';

  @override
  String get cancelSubscriptionQuestion => 'Preklici naročnino?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Ste prepričani, da želite preklicati naročnino? Nadaljeval boste imeti dostop do konca trenutnega obračunskega obdobja.';

  @override
  String get cancelSubscriptionButton => 'Preklici naročnino';

  @override
  String get cancelling => 'Prekličem...';

  @override
  String get betaTesterMessage => 'Ste beta tester te aplikacije. Še ni javna. Javna bo, ko bo potrjena.';

  @override
  String get appUnderReviewMessage => 'Vaša aplikacija je v pregledu in vidna samo vam. Javna bo, ko bo potrjena.';

  @override
  String get appRejectedMessage =>
      'Vaša aplikacija je bila zavrnjene. Prosimo, posodobite podrobnosti aplikacije in ponovno oddajte v pregled.';

  @override
  String get invalidIntegrationUrl => 'Neveljavna URL integracije';

  @override
  String get tapToComplete => 'Tapnite za dokončanje';

  @override
  String get invalidSetupInstructionsUrl => 'Neveljavna URL navodil za nastavljanje';

  @override
  String get pushToTalk => 'Potisni za govor';

  @override
  String get summaryPrompt => 'Povzetek';

  @override
  String get pleaseSelectARating => 'Prosimo, izberite oceno';

  @override
  String get reviewAddedSuccessfully => 'Pregledni je uspešno dodan 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Pregledni je uspešno posodobljen 🚀';

  @override
  String get failedToSubmitReview => 'Neuspešna oddaja preogledu. Prosimo, poskusite znova.';

  @override
  String get addYourReview => 'Dodajte svoj pregled';

  @override
  String get editYourReview => 'Uredi svoj pregled';

  @override
  String get writeAReviewOptional => 'Napišite pregled (izbirno)';

  @override
  String get submitReview => 'Oddaj pregled';

  @override
  String get updateReview => 'Posodobi pregled';

  @override
  String get yourReview => 'Vaš pregled';

  @override
  String get anonymousUser => 'Anonimni uporabnik';

  @override
  String get issueActivatingApp => 'Prišlo je do težave pri aktiviranju te aplikacije. Prosimo, poskusite znova.';

  @override
  String get dataAccessNoticeDescription =>
      'Ta aplikacija bo dostopala do vaših podatkov. Omi AI ni odgovorna za to, kako vaši podatki se uporabljajo, spreminjajo ali brišejo s te aplikacije';

  @override
  String get copyUrl => 'Kopiraj URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Pon';

  @override
  String get weekdayTue => 'Tor';

  @override
  String get weekdayWed => 'Sre';

  @override
  String get weekdayThu => 'Čet';

  @override
  String get weekdayFri => 'Pet';

  @override
  String get weekdaySat => 'Sob';

  @override
  String get weekdaySun => 'Ned';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Integracija $serviceName je v pripravljivanju';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Že izvozeno na $platform';
  }

  @override
  String get anotherPlatform => 'drugo platformo';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Prosimo, se prijavite s $serviceName v Nastavitve > Integracije nalog';
  }

  @override
  String addingToService(String serviceName) {
    return 'Dodajam v $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Dodano v $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Neuspešna dodaja v $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Dovoljenje zavrnjeno za Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Neuspešna ustvaritev ključa API ponudnika: $error';
  }

  @override
  String get createAKey => 'Ustvari ključ';

  @override
  String get apiKeyRevokedSuccessfully => 'Ključ API je bil uspešno preklican';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Neuspešen preklic ključa API: $error';
  }

  @override
  String get omiApiKeys => 'Omi ključi API';

  @override
  String get apiKeysDescription =>
      'Ključi API se uporabljajo za avtentifikacijo, ko vaša aplikacija komunicira s strežnikom OMI. Omogočajo vaši aplikaciji, da varno ustvari spomine in dostopa do drugih storitev OMI.';

  @override
  String get aboutOmiApiKeys => 'O Omi ključih API';

  @override
  String get yourNewKey => 'Vaš novi ključ:';

  @override
  String get copyToClipboard => 'Kopiraj v odložišče';

  @override
  String get pleaseCopyKeyNow => 'Prosimo, ga kopirajte zdaj in ga napišite nekje varno. ';

  @override
  String get willNotSeeAgain => 'Ne boste ga mogli videti znova.';

  @override
  String get revokeKey => 'Preklici ključ';

  @override
  String get revokeApiKeyQuestion => 'Preklici ključ API?';

  @override
  String get revokeApiKeyWarning =>
      'Te akcije ni mogoče razveljaviti. Nobene aplikacije, ki uporabljajo ta ključ, ne bodo več imele dostopa do API.';

  @override
  String get revoke => 'Preklici';

  @override
  String get whatWouldYouLikeToCreate => 'Kaj bi radi ustvarili?';

  @override
  String get createAnApp => 'Ustvari aplikacijo';

  @override
  String get createAndShareYourApp => 'Ustvarite in delite svojo aplikacijo';

  @override
  String get itemApp => 'Aplikacija';

  @override
  String keepItemPublic(String item) {
    return 'Ohrani $item javno';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Spremi $item javno?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Spremi $item zasebno?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Če spremenite $item javno, ga lahko uporabljajo vsi';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Če spremenite $item zasebno, bo prenehala delovati za vse in bo vidna samo vam';
  }

  @override
  String get manageApp => 'Upravljajte aplikacijo';

  @override
  String deleteItemTitle(String item) {
    return 'Izbriši $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Izbriši $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Ste prepričani, da želite izbrisati ta $item? Te akcije ni mogoče razveljaviti.';
  }

  @override
  String get revokeKeyQuestion => 'Preklici ključ?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Ste prepričani, da želite preklicati ključ \"$keyName\"? Te akcije ni mogoče razveljaviti.';
  }

  @override
  String get createNewKey => 'Ustvari novi ključ';

  @override
  String get keyNameHint => 'npr. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Prosimo, vnesite ime.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Neuspešna ustvaritev ključa: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Neuspešna ustvaritev ključa. Prosimo, poskusite znova.';

  @override
  String get keyCreated => 'Ključ je ustvaren';

  @override
  String get keyCreatedMessage =>
      'Vaš novi ključ je bil ustvaren. Prosimo, ga kopirajte zdaj. Ne boste ga mogli videti znova.';

  @override
  String get keyWord => 'Ključ';

  @override
  String get externalAppAccess => 'Dostop zunanje aplikacije';

  @override
  String get externalAppAccessDescription =>
      'Naslednje nameščene aplikacije imajo zunanje integracije in imajo dostop do vaših podatkov, kot so pogovori in spomine.';

  @override
  String get noExternalAppsHaveAccess => 'Nobena zunanja aplikacija nima dostopa do vaših podatkov.';

  @override
  String get maximumSecurityE2ee => 'Največja varnost (E2EE)';

  @override
  String get e2eeDescription =>
      'Šifriranje od konca do konca je zlati standard za zasebnost. Ko je omogočeno, se vaši podatki šifrirajo na vaši napravi, preden se pošljejo na naše strežnike. To pomeni, da nihče, niti Omi, ne more dostopati do vaše vsebine.';

  @override
  String get importantTradeoffs => 'Pomembni kompromisi:';

  @override
  String get e2eeTradeoff1 => '• Nekatere funkcije, kot so eksterne integracije aplikacij, so morda onemogočene.';

  @override
  String get e2eeTradeoff2 => '• Če izgubite geslo, vaših podatkov ni mogoče obnoviti.';

  @override
  String get featureComingSoon => 'Ta funkcija bo kmalu dostopna!';

  @override
  String get migrationInProgressMessage => 'Selitev je v teku. Ravni zaščite ne morete spremeniti, dokler se ne konča.';

  @override
  String get migrationFailed => 'Selitev ni uspela';

  @override
  String migratingFromTo(String source, String target) {
    return 'Selitev iz $source v $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total predmetov';
  }

  @override
  String get secureEncryption => 'Varno šifriranje';

  @override
  String get secureEncryptionDescription =>
      'Vaši podatki so šifrirani s ključem, ki je edinstven za vas na naših strežnikih, gostovanih na Google Cloud. To pomeni, da je vaša surova vsebina nedostopna komurkoli, vključno z osebjem Omi ali Google, neposredno iz baze podatkov.';

  @override
  String get endToEndEncryption => 'Šifriranje od konca do konca';

  @override
  String get e2eeCardDescription =>
      'Omogočite za največjo varnost, kjer samo vi lahko dostopate do vaših podatkov. Tapnite, da se več naučite.';

  @override
  String get dataAlwaysEncrypted => 'Ne glede na raven so vaši podatki vedno šifrirani v mirovanju in med prenosom.';

  @override
  String get readOnlyScope => 'Samo branje';

  @override
  String get fullAccessScope => 'Polni dostop';

  @override
  String get readScope => 'Branje';

  @override
  String get writeScope => 'Pisanje';

  @override
  String get apiKeyCreated => 'Ključ API je ustvaren!';

  @override
  String get saveKeyWarning => 'Shranite ta ključ zdaj! Ga ne boste mogli videti znova.';

  @override
  String get yourApiKey => 'VAŠ KLJUČ API';

  @override
  String get tapToCopy => 'Tapnite za kopiranje';

  @override
  String get copyKey => 'Kopiraj ključ';

  @override
  String get createApiKey => 'Ustvari ključ API';

  @override
  String get accessDataProgrammatically => 'Dostopajte do podatkov programsko';

  @override
  String get keyNameLabel => 'IME KLJUČA';

  @override
  String get keyNamePlaceholder => 'npr. Moja integracija aplikacije';

  @override
  String get permissionsLabel => 'DOVOLJENJA';

  @override
  String get permissionsInfoNote => 'R = Branje, W = Pisanje. Privzeto samo za branje, če ničesar ni izbrano.';

  @override
  String get developerApi => 'API razvijalca';

  @override
  String get createAKeyToGetStarted => 'Ustvari ključ, da bi se začeli';

  @override
  String errorWithMessage(String error) {
    return 'Napaka: $error';
  }

  @override
  String get omiTraining => 'Omi usposabljanja';

  @override
  String get trainingDataProgram => 'Program podatkov usposabljanja';

  @override
  String get getOmiUnlimitedFree =>
      'Pridobite Omi Unlimited brezplačno z deljenjem podatkov za usposabljanje modelov umetne inteligence.';

  @override
  String get trainingDataBullets =>
      '• Vaši podatki pomagajo izboljšati modele umetne inteligence\n• Samo necitljivi podatki se delijo\n• Povsem transparenten proces';

  @override
  String get learnMoreAtOmiTraining => 'Več o tem na omi.me/training';

  @override
  String get agreeToContributeData =>
      'Razumem in se strinjam, da prispevam podatke za usposabljanje umetne inteligence';

  @override
  String get submitRequest => 'Oddaj zahtevo';

  @override
  String get thankYouRequestUnderReview => 'Hvala! Vaša zahteva je v pregledu. Obvestili vas bomo, ko bo potrjena.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Vaš načrt ostane aktiven do $date. Po tem boste izgubili dostop do svojih neomejenih funkcij. Ste prepričani?';
  }

  @override
  String get confirmCancellation => 'Potrdite prekliciranje';

  @override
  String get keepMyPlan => 'Obdrži moj načrt';

  @override
  String get subscriptionSetToCancel => 'Vaša naročnina je nastavljena za prekliciranje na koncu obdobja.';

  @override
  String get switchedToOnDevice => 'Prešli na prepis na napravi';

  @override
  String get couldNotSwitchToFreePlan => 'Ni mogoče preklopiti na brezplačni načrt. Prosimo, poskusite ponovno.';

  @override
  String get couldNotLoadPlans => 'Ni mogoče naložiti razpoložljivih načrtov. Prosimo, poskusite ponovno.';

  @override
  String get selectedPlanNotAvailable => 'Izbrani načrt ni na voljo. Prosimo, poskusite ponovno.';

  @override
  String get upgradeToAnnualPlan => 'Nadgradnja na letni načrt';

  @override
  String get importantBillingInfo => 'Pomembne informacije o naročnini:';

  @override
  String get monthlyPlanContinues => 'Vaš trenutni mesečni načrt se bo nadaljeval do konca vašega obračunskega obdobja';

  @override
  String get paymentMethodCharged =>
      'Vaša obstoječa način plačila bo samodejno napolnjena, ko se bo vaš mesečni načrt končal';

  @override
  String get annualSubscriptionStarts => 'Vaša 12-mesečna letna naročnina se bo samodejno začela po obračunu';

  @override
  String get thirteenMonthsCoverage => 'Boste dobili skupno 13 mesecev pokritja (trenutni mesec + 12 mesecev letnega)';

  @override
  String get confirmUpgrade => 'Potrdite nadgradnjo';

  @override
  String get confirmPlanChange => 'Potrdite spremembo načrta';

  @override
  String get confirmAndProceed => 'Potrdite in nadaljujte';

  @override
  String get upgradeScheduled => 'Nadgradnja je razporejena';

  @override
  String get changePlan => 'Spremenite načrt';

  @override
  String get upgradeAlreadyScheduled => 'Vaša nadgradnja na letni načrt je že razporejena';

  @override
  String get youAreOnUnlimitedPlan => 'Ste na načrtu Unlimited.';

  @override
  String get yourOmiUnleashed => 'Vaš Omi, osvobođen. Pojdite na unlimited za neskončne možnosti.';

  @override
  String planEndedOn(String date) {
    return 'Vaš načrt se je končal $date.\\nPrekvalificira se sedaj - obračunani boste takoj za novo obračunsko obdobje.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Vaš načrt je nastavljen na preklic $date.\\nPrekvalificira se sedaj, da obdržite prednosti - brez napolnitve do $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Vaš letni načrt se bo samodejno začel, ko se bo vaš mesečni načrt končal.';

  @override
  String planRenewsOn(String date) {
    return 'Vaš načrt se obnavlja $date.';
  }

  @override
  String get unlimitedConversations => 'Neomejeni pogovori';

  @override
  String get askOmiAnything => 'Vprašajte Omi kaj koli o svojem življenju';

  @override
  String get unlockOmiInfiniteMemory => 'Odkleni Omijev neskončni spomin';

  @override
  String get youreOnAnnualPlan => 'Ste na letnem načrtu';

  @override
  String get alreadyBestValuePlan => 'Že imate najboljši načrt z največjo vrednostjo. Nobenih sprememb ni potrebnih.';

  @override
  String get unableToLoadPlans => 'Načrtov ni mogoče naložiti';

  @override
  String get checkConnectionTryAgain => 'Preverite povezavo in poskusite znova';

  @override
  String get useFreePlan => 'Uporabite brezplačni načrt';

  @override
  String get continueText => 'Nadaljujte';

  @override
  String get resubscribe => 'Ponovno se prijavite';

  @override
  String get couldNotOpenPaymentSettings => 'Ni mogoče odpreti nastavitev plačila. Prosimo, poskusite ponovno.';

  @override
  String get managePaymentMethod => 'Upravljajte način plačila';

  @override
  String get cancelSubscription => 'Prekličite naročnino';

  @override
  String endsOnDate(String date) {
    return 'Konča se $date';
  }

  @override
  String get active => 'Aktivno';

  @override
  String get freePlan => 'Brezplačni načrt';

  @override
  String get configure => 'Nastavite';

  @override
  String get privacyInformation => 'Informacije o zasebnosti';

  @override
  String get yourPrivacyMattersToUs => 'Vaša zasebnost nam je važna';

  @override
  String get privacyIntroText =>
      'V Omi zelo resno jemljemo vašo zasebnost. Želimo biti transparentni o podatkih, ki jih zbiramo, in kako jih uporabljamo za izboljšanje našega izdelka za vas. Tukaj je, kaj morate vedeti:';

  @override
  String get whatWeTrack => 'Kaj sledimo';

  @override
  String get anonymityAndPrivacy => 'Anonimnost in zasebnost';

  @override
  String get optInAndOptOutOptions => 'Možnosti vključevanja in izključevanja';

  @override
  String get ourCommitment => 'Naše zavezanosti';

  @override
  String get commitmentText =>
      'Zavezani smo, da podatke, ki jih zbiramo, uporabljamo samo za izboljšanje Omija za vas. Vaša zasebnost in zaupanje sta nam največje.';

  @override
  String get thankYouText =>
      'Hvala, ker ste dragoceni uporabnik Omija. Če imate vprašanja ali pomisleke, se lahko obrnete na nas na team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Nastavitve WiFi sinhronizacije';

  @override
  String get enterHotspotCredentials => 'Vnesite poverilnice osebne dostopne točke vašega telefona';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi sinhronizacija uporablja vaš telefon kot dostopno točko. Poiščite ime dostopne točke in geslo v Nastavitve > Osebna dostopna točka.';

  @override
  String get hotspotNameSsid => 'Ime dostopne točke (SSID)';

  @override
  String get exampleIphoneHotspot => 'npr. iPhone Hotspot';

  @override
  String get password => 'Geslo';

  @override
  String get enterHotspotPassword => 'Vnesite geslo dostopne točke';

  @override
  String get saveCredentials => 'Shranite poverilnice';

  @override
  String get clearCredentials => 'Počistite poverilnice';

  @override
  String get pleaseEnterHotspotName => 'Prosimo, vnesite ime dostopne točke';

  @override
  String get wifiCredentialsSaved => 'WiFi poverilnice so shranjene';

  @override
  String get wifiCredentialsCleared => 'WiFi poverilnice so počiščene';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Povzetek je bil ustvarjen za $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Ni mogoče ustvariti povzetka. Prepričajte se, da imate pogovore za ta dan.';

  @override
  String get summaryNotFound => 'Povzetek ni najden';

  @override
  String get yourDaysJourney => 'Vaša dnevna pot';

  @override
  String get highlights => 'Osvetljeni trenutki';

  @override
  String get unresolvedQuestions => 'Nerešena vprašanja';

  @override
  String get decisions => 'Odločitve';

  @override
  String get learnings => 'Učenja';

  @override
  String get autoDeletesAfterThreeDays => 'Samodejno briše po 3 dneh.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graf znanja je bil uspešno izbrisan';

  @override
  String get exportStartedMayTakeFewSeconds => 'Izvoz se je začel. To lahko traja nekaj sekund...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'To bo izbrisalo vse izpeljane podatke grafa znanja (vozlišča in povezave). Vaša originalna spomina bodo ostala varna. Graf bo ponovno zgrajen s časom ali ob naslednji zahtevi.';

  @override
  String get configureDailySummaryDigest => 'Nastavite svojo dnevno povzetko akcijskih postavk';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Dostopa $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'sproženo z $triggerType';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription in je $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'Je $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => 'Noben specifičen dostop do podatkov ni nastavljen.';

  @override
  String get basicPlanDescription => '1.200 premium minut + neomejeno na naprava';

  @override
  String get minutes => 'minut';

  @override
  String get omiHas => 'Omi ima:';

  @override
  String get premiumMinutesUsed => 'Premium minute so bile uporabljene.';

  @override
  String get setupOnDevice => 'Nastavite na napravah';

  @override
  String get forUnlimitedFreeTranscription => 'za neomejeno brezplačno prepis.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium minut ostane.';
  }

  @override
  String get alwaysAvailable => 'vedno na voljo.';

  @override
  String get importHistory => 'Zgodovina uvoza';

  @override
  String get noImportsYet => 'Še ni uvoženega';

  @override
  String get selectZipFileToImport => 'Izberite .zip datoteko za uvoz!';

  @override
  String get otherDevicesComingSoon => 'Druge naprave kmalu';

  @override
  String get deleteAllLimitlessConversations => 'Izbrisati vse pogovore Limitless?';

  @override
  String get deleteAllLimitlessWarning =>
      'To bo trajno izbrisalo vse pogovore, uvožene iz Limitless. To dejanja ne moremo razveljaviti.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Izbrisano $count Limitless pogovorov';
  }

  @override
  String get failedToDeleteConversations => 'Ni mogoče izbrisati pogovorov';

  @override
  String get deleteImportedData => 'Izbrisati uvožene podatke';

  @override
  String get statusPending => 'V čakanju';

  @override
  String get statusProcessing => 'Obdelava';

  @override
  String get statusCompleted => 'Zaključeno';

  @override
  String get statusFailed => 'Ni uspelo';

  @override
  String nConversations(int count) {
    return '$count pogovorov';
  }

  @override
  String get pleaseEnterName => 'Prosimo, vnesite ime';

  @override
  String get nameMustBeBetweenCharacters => 'Ime mora biti med 2 in 40 znaki';

  @override
  String get deleteSampleQuestion => 'Izbrisati vzorec?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Ali ste prepričani, da želite izbrisati vzorec $name?';
  }

  @override
  String get confirmDeletion => 'Potrdite brisanje';

  @override
  String deletePersonConfirmation(String name) {
    return 'Ali ste prepričani, da želite izbrisati $name? To bo tudi odstranjeno vse povezane govorčeve vzorce.';
  }

  @override
  String get howItWorksTitle => 'Kako deluje?';

  @override
  String get howPeopleWorks =>
      'Ko je oseba ustvarjena, lahko greste na prepis pogovora in jim dodelite njihove pripadajoče segmente, na ta način bo Omi sposoben prepoznati tudi njihov govor!';

  @override
  String get tapToDelete => 'Tapnite za brisanje';

  @override
  String get newTag => 'NOVO';

  @override
  String get needHelpChatWithUs => 'Potrebna pomoč? Klepetajte z nami';

  @override
  String get localStorageEnabled => 'Lokalno shranjevanje je omogočeno';

  @override
  String get localStorageDisabled => 'Lokalno shranjevanje je onemogočeno';

  @override
  String failedToUpdateSettings(String error) {
    return 'Ni mogoče posodobiti nastavitve: $error';
  }

  @override
  String get privacyNotice => 'Obvestilo o zasebnosti';

  @override
  String get recordingsMayCaptureOthers =>
      'Posnetki lahko zajamejo glasove drugih. Preden omogočite, se prepričajte, da imate soglasje vseh udeležencev.';

  @override
  String get enable => 'Omogočite';

  @override
  String get storeAudioOnPhone => 'Shranite avdio na telefon';

  @override
  String get on => 'Vključeno';

  @override
  String get storeAudioDescription =>
      'Ohranite vse avdio posnetke shranjene lokalno na telefonu. Če je onemogočeno, se samo neuspeli prenosi ohranijo za varčevanje s prostorom.';

  @override
  String get enableLocalStorage => 'Omogočite lokalno shranjevanje';

  @override
  String get cloudStorageEnabled => 'Oblačno shranjevanje je omogočeno';

  @override
  String get cloudStorageDisabled => 'Oblačno shranjevanje je onemogočeno';

  @override
  String get enableCloudStorage => 'Omogočite oblačno shranjevanje';

  @override
  String get storeAudioOnCloud => 'Shranite avdio v oblak';

  @override
  String get cloudStorageDialogMessage =>
      'Vaši posnetki v realnem času bodo shranjeni v zasebnem oblačnem shranjevanju, medtem ko govorite.';

  @override
  String get storeAudioCloudDescription =>
      'Shranite svoje posnetke v realnem času v zasebno oblačno shranjevanje, medtem ko govorite. Avdio je zajeti in varno shranjen v realnem času.';

  @override
  String get downloadingFirmware => 'Prenos vdelane programske opreme';

  @override
  String get installingFirmware => 'Namestitev vdelane programske opreme';

  @override
  String get firmwareUpdateWarning =>
      'Ne zaprite aplikacije in ne izklapljajte naprave. To bi lahko pokvarilo vašo napravo.';

  @override
  String get firmwareUpdated => 'Vdelana programska oprema je posodobljena';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Prosimo, ponovno zaženite $deviceName, da dokončate posodobitev.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Vaša naprava je posodobljena';

  @override
  String get currentVersion => 'Trenutna različica';

  @override
  String get latestVersion => 'Najnovejša različica';

  @override
  String get whatsNew => 'Kaj je novo';

  @override
  String get installUpdate => 'Namestite posodobitev';

  @override
  String get updateNow => 'Posodobite zdaj';

  @override
  String get updateGuide => 'Vodnik za posodobitev';

  @override
  String get checkingForUpdates => 'Preverjanje posodobitev';

  @override
  String get checkingFirmwareVersion => 'Preverjanje različice vdelane programske opreme...';

  @override
  String get firmwareUpdate => 'Posodobitev vdelane programske opreme';

  @override
  String get payments => 'Plačila';

  @override
  String get connectPaymentMethodInfo =>
      'Spodaj povežite način plačila, da začnete prejemati izplate za svoje aplikacije.';

  @override
  String get selectedPaymentMethod => 'Izbrani način plačila';

  @override
  String get availablePaymentMethods => 'Razpoložljivi načini plačila';

  @override
  String get activeStatus => 'Aktivno';

  @override
  String get connectedStatus => 'Povezano';

  @override
  String get notConnectedStatus => 'Ni povezano';

  @override
  String get setActive => 'Nastavite kot aktivno';

  @override
  String get getPaidThroughStripe => 'Prejemajte plačila za prodajo aplikacij prek Stripe';

  @override
  String get monthlyPayouts => 'Mesečne izplate';

  @override
  String get monthlyPayoutsDescription =>
      'Prejemajte mesečna plačila neposredno na vaš račun, ko dosežete 10 \$ zaslužka';

  @override
  String get secureAndReliable => 'Varno in zanesljivo';

  @override
  String get stripeSecureDescription => 'Stripe zagotavlja varni in pravočasni prenos vaših prihodkov iz aplikacij';

  @override
  String get selectYourCountry => 'Izberite svojo državo';

  @override
  String get countrySelectionPermanent => 'Izbira države je trajna in je ne morete spremeniti kasneje.';

  @override
  String get byClickingConnectNow => 'Z klikom na \"Povežite zdaj\" se strinjate s';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe Connected Account Agreement';

  @override
  String get errorConnectingToStripe => 'Napaka pri povezovanju s Stripe! Prosimo, poskusite ponovno kasneje.';

  @override
  String get connectingYourStripeAccount => 'Povezovanje vašega Stripe računa';

  @override
  String get stripeOnboardingInstructions =>
      'Prosimo, dokončajte Stripe onboarding proces v vašem brskalniku. Ta stran se bo samodejno posodobila, ko bo končano.';

  @override
  String get failedTryAgain => 'Ni uspelo? Poskusite ponovno';

  @override
  String get illDoItLater => 'To bom naredil kasneje';

  @override
  String get successfullyConnected => 'Uspešno povezano!';

  @override
  String get stripeReadyForPayments =>
      'Vaš Stripe račun je sedaj pripravljen za prejemanje plačil. Takoj lahko začnete zaslužiti s prodajo aplikacije.';

  @override
  String get updateStripeDetails => 'Posodobite podatke Stripe';

  @override
  String get errorUpdatingStripeDetails =>
      'Napaka pri posodabljanju podatkov Stripe! Prosimo, poskusite ponovno kasneje.';

  @override
  String get updatePayPal => 'Posodobite PayPal';

  @override
  String get setUpPayPal => 'Nastavite PayPal';

  @override
  String get updatePayPalAccountDetails => 'Posodobite podatke vašega PayPal računa';

  @override
  String get connectPayPalToReceivePayments =>
      'Povežite svoj PayPal račun, da začnete prejemati plačila za svoje aplikacije';

  @override
  String get paypalEmail => 'PayPal email';

  @override
  String get paypalMeLink => 'PayPal.me povezava';

  @override
  String get stripeRecommendation =>
      'Če je Stripe dostopen v vaši državi, vam toplo priporočamo, da ga uporabljate za hitrejše in enostavnejše izplate.';

  @override
  String get updatePayPalDetails => 'Posodobite PayPal podrobnosti';

  @override
  String get savePayPalDetails => 'Shranite PayPal podrobnosti';

  @override
  String get pleaseEnterPayPalEmail => 'Prosimo, vnesite svoj PayPal email';

  @override
  String get pleaseEnterPayPalMeLink => 'Prosimo, vnesite svojo PayPal.me povezavo';

  @override
  String get doNotIncludeHttpInLink => 'Ne vključujte http ali https ali www v povezavo';

  @override
  String get pleaseEnterValidPayPalMeLink => 'Prosimo, vnesite veljavno PayPal.me povezavo';

  @override
  String get pleaseEnterValidEmail => 'Prosimo, vnesite veljaven e-poštni naslov';

  @override
  String get syncingYourRecordings => 'Sinhronizacija vaših posnetkov';

  @override
  String get syncYourRecordings => 'Sinhronizujte svoje posnetke';

  @override
  String get syncNow => 'Sinhronizujte zdaj';

  @override
  String get error => 'Napaka';

  @override
  String get speechSamples => 'Govorne vzorce';

  @override
  String additionalSampleIndex(String index) {
    return 'Dodatni vzorec $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Trajanje: $seconds sekund';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Dodatni govori vzorec je bil odstranjen';

  @override
  String get consentDataMessage =>
      'Z nadaljevanjem bodo vaši pogovori, posnetki in osebni podatki varno shranjeni na naših strežnikih. Vaši zvočni posnetki in prepisi se obdelujejo s storitvami umetne inteligence tretjih oseb (vključno z Deepgram za prepis in OpenAI za analizo), da vam zagotovimo vpoglede, ki jih poganja umetna inteligenca, in omogočimo vse funkcije aplikacije.';

  @override
  String get tasksEmptyStateMessage =>
      'Naloge iz vaših pogovorov se bodo prikazale tukaj.\\nTapnite + za ročno ustvarjanje.';

  @override
  String get clearChatAction => 'Počistite klepet';

  @override
  String get enableApps => 'Omogočite aplikacije';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'prikaži več ↓';

  @override
  String get showLess => 'prikaži manj ↑';

  @override
  String get loadingYourRecording => 'Nalaganje vašega posnetka...';

  @override
  String get photoDiscardedMessage => 'Ta fotografija je bila zavržena, ker ni bila pomembna.';

  @override
  String get analyzing => 'Analiza...';

  @override
  String get searchCountries => 'Iskanje držav';

  @override
  String get checkingAppleWatch => 'Preverjanje Apple Watch...';

  @override
  String get installOmiOnAppleWatch => 'Namestite Omi na vaš\\nApple Watch';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Za uporabo vašega Apple Watch z Omijem morali najprej namestiti aplikacijo Omi na uro.';

  @override
  String get openOmiOnAppleWatch => 'Odprite Omi na vašem\\nApple Watch';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Aplikacija Omi je nameščena na vašem Apple Watch. Odprite jo in tapnite Začni.';

  @override
  String get openWatchApp => 'Odprite Watch aplikacijo';

  @override
  String get iveInstalledAndOpenedTheApp => 'Namestil sem in odprli aplikacijo';

  @override
  String get unableToOpenWatchApp =>
      'Ni mogoče odpreti Apple Watch aplikacijo. Prosimo, ročno odprite Watch aplikacijo na svojem Apple Watch in namestite Omi iz razdelka \"Razpoložljive aplikacije\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch je bil uspešno povezan!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch je še vedno nedostopen. Prosimo, prepričajte se, da je aplikacija Omi odprta na vaši uri.';

  @override
  String errorCheckingConnection(String error) {
    return 'Napaka pri preverjanju povezave: $error';
  }

  @override
  String get muted => 'Utišano';

  @override
  String get processNow => 'Obdelaj zdaj';

  @override
  String get finishedConversation => 'Zaključen pogovor?';

  @override
  String get stopRecordingConfirmation =>
      'Ali ste prepričani, da želite prenehati s snemanjem in povzeti pogovor sedaj?';

  @override
  String get conversationEndsManually => 'Pogovor se bo končal samo ročno.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Pogovor se je povzet po $minutes minuti$suffix brez govora.';
  }

  @override
  String get dontAskAgain => 'Prosim, ne vprašajte me več';

  @override
  String get waitingForTranscriptOrPhotos => 'Čakanje na prepis ali fotografije...';

  @override
  String get noSummaryYet => 'Povzetek še ni na voljo';

  @override
  String hints(String text) {
    return 'Namigi: $text';
  }

  @override
  String get testConversationPrompt => 'Testirajte poziv pogovora';

  @override
  String get prompt => 'Poziv';

  @override
  String get result => 'Rezultat:';

  @override
  String get compareTranscripts => 'Primerjaj prepisve';

  @override
  String get notHelpful => 'Ni bilo koristno';

  @override
  String get exportTasksWithOneTap => 'Izvozite naloge z enim tapom!';

  @override
  String get inProgress => 'V teku';

  @override
  String get photos => 'Fotografije';

  @override
  String get rawData => 'Surovi podatki';

  @override
  String get content => 'Vsebina';

  @override
  String get noContentToDisplay => 'Ni vsebine za prikaz';

  @override
  String get noSummary => 'Brez povzetka';

  @override
  String get updateOmiFirmware => 'Posodobite omi vdelano programsko opremo';

  @override
  String get anErrorOccurredTryAgain => 'Prišlo je do napake. Prosimo, poskusite ponovno.';

  @override
  String get welcomeBackSimple => 'Dobrodošli nazaj';

  @override
  String get addVocabularyDescription => 'Dodajte besede, ki bi jih Omi moral prepoznati med prepisom.';

  @override
  String get enterWordsCommaSeparated => 'Vnesite besede (ločene z vejico)';

  @override
  String get whenToReceiveDailySummary => 'Kdaj prejeti dnevni povzetek';

  @override
  String get checkingNextSevenDays => 'Preverjanje naslednjih 7 dni';

  @override
  String failedToDeleteError(String error) {
    return 'Ni mogoče izbrisati: $error';
  }

  @override
  String get developerApiKeys => 'Ključi razvijalca API';

  @override
  String get noApiKeysCreateOne => 'Ni ključev API. Ustvarite enega za začetek.';

  @override
  String get commandRequired => '⌘ zahtevano';

  @override
  String get spaceKey => 'Presledek';

  @override
  String loadMoreRemaining(String count) {
    return 'Naložite več ($count ostane)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Uporabnik top $percentile%';
  }

  @override
  String get wrappedMinutes => 'minut';

  @override
  String get wrappedConversations => 'pogovori';

  @override
  String get wrappedDaysActive => 'dni aktivnosti';

  @override
  String get wrappedYouTalkedAbout => 'O čem ste govorili';

  @override
  String get wrappedActionItems => 'Akcijske postavke';

  @override
  String get wrappedTasksCreated => 'nalog ustvarjenih';

  @override
  String get wrappedCompleted => 'zaključenih';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% stotnjaak zaključka';
  }

  @override
  String get wrappedYourTopDays => 'Vaši top dnevi';

  @override
  String get wrappedBestMoments => 'Najboljši trenutki';

  @override
  String get wrappedMyBuddies => 'Moji prijatelji';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Niso mogli prenehati govoriti o';

  @override
  String get wrappedShow => 'PREDSTAVA';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'KNJIGA';

  @override
  String get wrappedCelebrity => 'SLAVNI OSEBI';

  @override
  String get wrappedFood => 'HRANa';

  @override
  String get wrappedMovieRecs => 'Filmske priporočilne za prijatelje';

  @override
  String get wrappedBiggest => 'Največji';

  @override
  String get wrappedStruggle => 'Boj';

  @override
  String get wrappedButYouPushedThrough => 'Ampak si se prebil 💪';

  @override
  String get wrappedWin => 'Zmaga';

  @override
  String get wrappedYouDidIt => 'Naredil si to! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 fraz';

  @override
  String get wrappedMins => 'minut';

  @override
  String get wrappedConvos => 'pogovorov';

  @override
  String get wrappedDays => 'dni';

  @override
  String get wrappedMyBuddiesLabel => 'MOJI PRIJATELJI';

  @override
  String get wrappedObsessionsLabel => 'OBSESIJE';

  @override
  String get wrappedStruggleLabel => 'BOJ';

  @override
  String get wrappedWinLabel => 'ZMAGA';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRAZE';

  @override
  String get wrappedLetsHitRewind => 'Gremo na ponovni zagon';

  @override
  String get wrappedGenerateMyWrapped => 'Generiraj moj wrapped';

  @override
  String get wrappedProcessingDefault => 'Obdelava...';

  @override
  String get wrappedCreatingYourStory => 'Ustvarjanje vaše\\n2025 zgodbe...';

  @override
  String get wrappedSomethingWentWrong => 'Nekaj\\nje šlo narobe';

  @override
  String get wrappedAnErrorOccurred => 'Prišlo je do napake';

  @override
  String get wrappedTryAgain => 'Poskusite ponovno';

  @override
  String get wrappedNoDataAvailable => 'Ni razpoložljivih podatkov';

  @override
  String get wrappedOmiLifeRecap => 'Omi povzetek življenja';

  @override
  String get wrappedSwipeUpToBegin => 'Potisnite navzgor za začetek';

  @override
  String get wrappedShareText => 'Moje 2025, zapomnjena po Omi ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => 'Ni mogoče deliti. Prosimo, poskusite ponovno.';

  @override
  String get wrappedFailedToStartGeneration => 'Ni mogoče začeti generiranja. Prosimo, poskusite ponovno.';

  @override
  String get wrappedStarting => 'Začenjanje...';

  @override
  String get wrappedShare => 'Delite';

  @override
  String get wrappedShareYourWrapped => 'Delite svoj wrapped';

  @override
  String get wrappedMy2025 => 'Moje 2025';

  @override
  String get wrappedRememberedByOmi => 'zapomnjena po Omi';

  @override
  String get wrappedMostFunDay => 'Najbolj zabavno';

  @override
  String get wrappedMostProductiveDay => 'Najbolj produktivno';

  @override
  String get wrappedMostIntenseDay => 'Najbolj intenzivno';

  @override
  String get wrappedFunniestMoment => 'Najbolj smešno';

  @override
  String get wrappedMostCringeMoment => 'Najbolj okorno';

  @override
  String get wrappedMinutesLabel => 'minut';

  @override
  String get wrappedConversationsLabel => 'pogovori';

  @override
  String get wrappedDaysActiveLabel => 'dni aktivnosti';

  @override
  String get wrappedTasksGenerated => 'nalog generiranih';

  @override
  String get wrappedTasksCompleted => 'nalog zaključenih';

  @override
  String get wrappedTopFivePhrases => 'Top 5 fraz';

  @override
  String get wrappedAGreatDay => 'Odličen dan';

  @override
  String get wrappedGettingItDone => 'Narediti stvari';

  @override
  String get wrappedAChallenge => 'Izziv';

  @override
  String get wrappedAHilariousMoment => 'Smešen trenutek';

  @override
  String get wrappedThatAwkwardMoment => 'Tisti okorno trenutek';

  @override
  String get wrappedYouHadFunnyMoments => 'Imeli ste nekaj smešnih trenutkov to leto!';

  @override
  String get wrappedWeveAllBeenThere => 'Vsi smo tam bili!';

  @override
  String get wrappedFriend => 'Prijatelj';

  @override
  String get wrappedYourBuddy => 'Tvoj prijatelj!';

  @override
  String get wrappedNotMentioned => 'Ni omenjena';

  @override
  String get wrappedTheHardPart => 'Težek del';

  @override
  String get wrappedPersonalGrowth => 'Osebnostna rast';

  @override
  String get wrappedFunDay => 'Zabavno';

  @override
  String get wrappedProductiveDay => 'Produktivno';

  @override
  String get wrappedIntenseDay => 'Intenzivno';

  @override
  String get wrappedFunnyMomentTitle => 'Smešen trenutek';

  @override
  String get wrappedCringeMomentTitle => 'Okorna trenutek';

  @override
  String get wrappedYouTalkedAboutBadge => 'O čem ste govorili';

  @override
  String get wrappedCompletedLabel => 'Zaključeno';

  @override
  String get wrappedMyBuddiesCard => 'Moji prijatelji';

  @override
  String get wrappedBuddiesLabel => 'PRIJATELJI';

  @override
  String get wrappedObsessionsLabelUpper => 'OBSESIJE';

  @override
  String get wrappedStruggleLabelUpper => 'BOJ';

  @override
  String get wrappedWinLabelUpper => 'ZMAGA';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRAZE';

  @override
  String get wrappedYourHeader => 'Vaš';

  @override
  String get wrappedTopDaysHeader => 'Top dnevi';

  @override
  String get wrappedYourTopDaysBadge => 'Vaši top dnevi';

  @override
  String get wrappedBestHeader => 'Najboljši';

  @override
  String get wrappedMomentsHeader => 'trenutki';

  @override
  String get wrappedBestMomentsBadge => 'Najboljši trenutki';

  @override
  String get wrappedBiggestHeader => 'Največji';

  @override
  String get wrappedStruggleHeader => 'Boj';

  @override
  String get wrappedWinHeader => 'Zmaga';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Ampak si se prebil 💪';

  @override
  String get wrappedYouDidItEmoji => 'Naredil si to! 🎉';

  @override
  String get wrappedHours => 'ur';

  @override
  String get wrappedActions => 'akcij';

  @override
  String get multipleSpeakersDetected => 'Zaznani več govorcev';

  @override
  String get multipleSpeakersDescription =>
      'Zdi se, da so v posnetku govorci. Prosimo, prepričajte se, da ste na mirnem mestu in poskusite ponovno.';

  @override
  String get invalidRecordingDetected => 'Zaznana neveljavna snemanja';

  @override
  String get notEnoughSpeechDescription => 'Zaznano je premalo govora. Prosimo, govorite več in poskusite ponovno.';

  @override
  String get speechDurationDescription => 'Prepričajte se, da govorite najmanj 5 sekund in ne več kot 90.';

  @override
  String get connectionLostDescription =>
      'Povezava je bila prekinjena. Preverite svojo internetno povezavo in poskusite znova.';

  @override
  String get howToTakeGoodSample => 'Kako narediti dobro vzorec?';

  @override
  String get goodSampleInstructions =>
      '1. Prepričajte se, da ste na mirnem mestu.\n2. Govorite jasno in naravno.\n3. Prepričajte se, da je naprava v naravnem položaju, na vratu.\n\nKo je ustvarjena, jo lahko kadar koli izboljšate ali ponovno naredite.';

  @override
  String get noDeviceConnectedUseMic => 'Nobena naprava ni povezana. Uporabil bom mikrofon telefona.';

  @override
  String get doItAgain => 'Naredite še enkrat';

  @override
  String get listenToSpeechProfile => 'Poslušajte svoj profil govora ➡️';

  @override
  String get recognizingOthers => 'Prepoznavanje drugih 👀';

  @override
  String get keepGoingGreat => 'Nadaljujte, odlično vam gre';

  @override
  String get somethingWentWrongTryAgain => 'Nekaj je šlo narobe! Poskusite še enkrat kasneje.';

  @override
  String get uploadingVoiceProfile => 'Nalagam vaš profil glasu....';

  @override
  String get memorizingYourVoice => 'Memoriziram vaš glas...';

  @override
  String get personalizingExperience => 'Osebljujem vašo izkušnjo...';

  @override
  String get keepSpeakingUntil100 => 'Govorite, dokler ne dosežete 100%.';

  @override
  String get greatJobAlmostThere => 'Odličen rezultat, skoraj ste že tam';

  @override
  String get soCloseJustLittleMore => 'Tako blizu, samo malo več';

  @override
  String get notificationFrequency => 'Pogostost obvestil';

  @override
  String get controlNotificationFrequency => 'Kontrolirajte, kako pogosto Omi pošilja proaktivna obvestila.';

  @override
  String get yourScore => 'Vaš rezultat';

  @override
  String get dailyScoreBreakdown => 'Razčlen dnevnega rezultata';

  @override
  String get todaysScore => 'Dannešnji rezultat';

  @override
  String get tasksCompleted => 'Opravljene naloge';

  @override
  String get completionRate => 'Stopnja dokončanja';

  @override
  String get howItWorks => 'Kako deluje';

  @override
  String get dailyScoreExplanation =>
      'Vaš dnevni rezultat temelji na opravljanju nalog. Opravite svoje naloge, da izboljšate svoj rezultat!';

  @override
  String get notificationFrequencyDescription =>
      'Kontrolirajte, kako pogosto Omi pošilja proaktivna obvestila in opomniki.';

  @override
  String get sliderOff => 'Izključeno';

  @override
  String get sliderMax => 'Maksimalno';

  @override
  String summaryGeneratedFor(String date) {
    return 'Povzetek ustvarjen za $date';
  }

  @override
  String get failedToGenerateSummary => 'Napaka pri ustvarjanju povzetka. Prepričajte se, da imate pogovore za ta dan.';

  @override
  String get recap => 'Povzetek';

  @override
  String deleteQuoted(String name) {
    return 'Izbriši \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Premakni $count pogovorov v:';
  }

  @override
  String get noFolder => 'Brez mape';

  @override
  String get removeFromAllFolders => 'Odstrani iz vseh map';

  @override
  String get buildAndShareYourCustomApp => 'Sestavi in deli svojo prilagojeno aplikacijo';

  @override
  String get searchAppsPlaceholder => 'Iskanje 1500+ aplikacij';

  @override
  String get filters => 'Filtri';

  @override
  String get frequencyOff => 'Izključeno';

  @override
  String get frequencyMinimal => 'Minimalno';

  @override
  String get frequencyLow => 'Nizko';

  @override
  String get frequencyBalanced => 'Uravnoteženo';

  @override
  String get frequencyHigh => 'Visoko';

  @override
  String get frequencyMaximum => 'Maksimalno';

  @override
  String get frequencyDescOff => 'Brez proaktivnih obvestil';

  @override
  String get frequencyDescMinimal => 'Samo kritični opomniki';

  @override
  String get frequencyDescLow => 'Samo pomembne posodobitve';

  @override
  String get frequencyDescBalanced => 'Redni koristni podioni';

  @override
  String get frequencyDescHigh => 'Pogosti preverjeni';

  @override
  String get frequencyDescMaximum => 'Ostanite nenehno vključeni';

  @override
  String get clearChatQuestion => 'Počistiti pogovor?';

  @override
  String get syncingMessages => 'Sinhroniziram sporočila s strežnikom...';

  @override
  String get chatAppsTitle => 'Aplikacije za klepet';

  @override
  String get selectApp => 'Izberite aplikacijo';

  @override
  String get noChatAppsEnabled =>
      'Nobena aplikacija za klepet ni omogočena.\nTapnite \"Omogoči aplikacije\", da jih dodate.';

  @override
  String get disable => 'Onemogući';

  @override
  String get photoLibrary => 'Knjižnica fotografij';

  @override
  String get chooseFile => 'Izberite datoteko';

  @override
  String get connectAiAssistantsToYourData => 'Povežite AI asistente s svojimi podatki';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage => 'Spremljajte svoje osebne cilje na domačni strani';

  @override
  String get deleteRecording => 'Izbriši snemanje';

  @override
  String get thisCannotBeUndone => 'Tega ni mogoče razveljaviti.';

  @override
  String get sdCard => 'SD kartica';

  @override
  String get fromSd => 'Iz SD';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Hitri prenos';

  @override
  String get syncingStatus => 'Sinhronizacija';

  @override
  String get failedStatus => 'Neuspešno';

  @override
  String etaLabel(String time) {
    return 'Predviden čas: $time';
  }

  @override
  String get transferMethod => 'Način prenosa';

  @override
  String get fast => 'Hitro';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Prekliči sinhronizacijo';

  @override
  String get cancelSyncMessage => 'Podatki, ki so že preneseni, bodo shranjeni. Pozneje lahko nadaljujete.';

  @override
  String get syncCancelled => 'Sinhronizacija preklicana';

  @override
  String get deleteProcessedFiles => 'Izbriši obdelane datoteke';

  @override
  String get processedFilesDeleted => 'Obdelane datoteke izbrisane';

  @override
  String get wifiEnableFailed => 'Napaka pri omogočanju WiFi na napravi. Poskusite znova.';

  @override
  String get deviceNoFastTransfer => 'Vaša naprava ne podpira hitrih prenosa. Namesto tega uporabite Bluetooth.';

  @override
  String get enableHotspotMessage => 'Prosim, omogočite osebno točko dostopa na vašem telefonu in poskusite znova.';

  @override
  String get transferStartFailed => 'Napaka pri začetku prenosa. Poskusite znova.';

  @override
  String get deviceNotResponding => 'Naprava se ni odzvala. Poskusite znova.';

  @override
  String get invalidWifiCredentials => 'Neveljavne WiFi poverila. Preverite nastavitve osebne točke dostopa.';

  @override
  String get wifiConnectionFailed => 'Povezava WiFi je neuspešna. Poskusite znova.';

  @override
  String get sdCardProcessing => 'Obdelava SD kartice';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Obdelava $count snemanja/snemanj. Datoteke bodo odstranjene iz SD kartice.';
  }

  @override
  String get process => 'Obdelaj';

  @override
  String get wifiSyncFailed => 'Sinhronizacija WiFi neuspešna';

  @override
  String get processingFailed => 'Obdelava neuspešna';

  @override
  String get downloadingFromSdCard => 'Prenašanje iz SD kartice';

  @override
  String processingProgress(int current, int total) {
    return 'Obdelava $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count pogovorov ustvarjeno';
  }

  @override
  String get internetRequired => 'Potrebna je internetna povezava';

  @override
  String get processAudio => 'Obdelaj zvok';

  @override
  String get start => 'Začni';

  @override
  String get noRecordings => 'Nobenih snemanj';

  @override
  String get audioFromOmiWillAppearHere => 'Zvok iz vaše naprave Omi se bo pojavil tukaj';

  @override
  String get deleteProcessed => 'Izbriši obdelane';

  @override
  String get tryDifferentFilter => 'Poskusite drugi filter';

  @override
  String get recordings => 'Snemanja';

  @override
  String get enableRemindersAccess =>
      'Prosim, omogočite dostop do spomnnikov v nastavitvah, da uporabite Apple Reminders';

  @override
  String todayAtTime(String time) {
    return 'Danes ob $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Včeraj ob $time';
  }

  @override
  String get lessThanAMinute => 'Manj kot minuto';

  @override
  String estimatedMinutes(int count) {
    return '~$count minuto/minut';
  }

  @override
  String estimatedHours(int count) {
    return '~$count uro/ur';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Predviden čas: $time preostane';
  }

  @override
  String get summarizingConversation => 'Sumariziranje pogovora...\nTo lahko traja nekaj sekund';

  @override
  String get resummarizingConversation => 'Ponovno sumariziranje pogovora...\nTo lahko traja nekaj sekund';

  @override
  String get nothingInterestingRetry => 'Nič zanimivega ni bilo najdeno,\nželite poskusiti znova?';

  @override
  String get noSummaryForConversation => 'Povzetek ni dostopen\nza ta pogovor.';

  @override
  String get unknownLocation => 'Neznana lokacija';

  @override
  String get couldNotLoadMap => 'Ni bilo mogoče naložiti zemljevida';

  @override
  String get triggerConversationIntegration => 'Sprožite integracijo ustvarjenega pogovora';

  @override
  String get webhookUrlNotSet => 'Spletni naslov webhook ni nastavljen';

  @override
  String get setWebhookUrlInSettings =>
      'Prosim, nastavite spletni naslov webhook v nastavitvah razvijalca, da uporabite to funkcijo.';

  @override
  String get sendWebUrl => 'Pošlji spletni naslov';

  @override
  String get sendTranscript => 'Pošlji prepis';

  @override
  String get sendSummary => 'Pošlji povzetek';

  @override
  String get debugModeDetected => 'Zaznan način razhroščevanja';

  @override
  String get performanceReduced => 'Zmogljivost je zmanjšana 5-10x. Uporabite način izdaje.';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Samodejno zapiranje v ${seconds}s';
  }

  @override
  String get modelRequired => 'Potreben je model';

  @override
  String get downloadWhisperModel => 'Prosim, prenesite model Whisper, preden ga shranite.';

  @override
  String get deviceNotCompatible => 'Naprava ni združljiva';

  @override
  String get deviceRequirements => 'Vaša naprava ne izpolnjuje zahtev za transkripcijo na napravi.';

  @override
  String get willLikelyCrash => 'Omogočanje tega bo verjetno povzročilo, da se aplikacija sesede ali zmrzne.';

  @override
  String get transcriptionSlowerLessAccurate => 'Transkripcija bo bistveno počasnejša in manj natančna.';

  @override
  String get proceedAnyway => 'Vseeno nadaljujte';

  @override
  String get olderDeviceDetected => 'Zaznana starejša naprava';

  @override
  String get onDeviceSlower => 'Transkripcija na napravi je lahko počasnejša na tej napravi.';

  @override
  String get batteryUsageHigher => 'Poraba baterije bo višja kot pri oblačni transkripciji.';

  @override
  String get considerOmiCloud => 'Razmislite o uporabi Omi Cloud za boljšo zmogljivost.';

  @override
  String get highResourceUsage => 'Visoka poraba virov';

  @override
  String get onDeviceIntensive => 'Transkripcija na napravi je računsko intenzivna.';

  @override
  String get batteryDrainIncrease => 'Poraba baterije se bo significantly povečala.';

  @override
  String get deviceMayWarmUp => 'Naprava se lahko ogreje med daljšo uporabo.';

  @override
  String get speedAccuracyLower => 'Hitrost in natančnost sta lahko nižji od modelov v oblaku.';

  @override
  String get cloudProvider => 'Ponudnik oblaka';

  @override
  String get premiumMinutesInfo =>
      '1.200 premijskih minut/mesec. Zavihek Na napravi ponuja neomejeno brezplačno transkripcijo.';

  @override
  String get viewUsage => 'Poglej uporabo';

  @override
  String get localProcessingInfo =>
      'Zvok se obdeluje lokalno. Deluje brez interneta, bolj zasebno, vendar porabi več baterije.';

  @override
  String get model => 'Model';

  @override
  String get performanceWarning => 'Opozorilo zmogljivosti';

  @override
  String get largeModelWarning =>
      'Ta model je velik in lahko sesede aplikacijo ali se izvaja zelo počasi na mobilnih napravah.\n\nPriporočljivi so \"mali\" ali \"osnovni\" modeli.';

  @override
  String get usingNativeIosSpeech => 'Uporaba nativnega prepoznavanja govora iOS';

  @override
  String get noModelDownloadRequired => 'Uporabljena bo nativna govorica naprave. Prenos modela ni potreben.';

  @override
  String get modelReady => 'Model je pripravljen';

  @override
  String get redownload => 'Ponovno prenesite';

  @override
  String get doNotCloseApp => 'Prosim, ne zaprite aplikacije.';

  @override
  String get downloading => 'Prenašanje...';

  @override
  String get downloadModel => 'Prenesite model';

  @override
  String estimatedSize(String size) {
    return 'Predvidena velikost: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Razpoložljiv prostor: $space';
  }

  @override
  String get notEnoughSpace => 'Opozorilo: Ni dovolj prostora!';

  @override
  String get download => 'Prenesite';

  @override
  String downloadError(String error) {
    return 'Napaka pri prenosu: $error';
  }

  @override
  String get cancelled => 'Preklicano';

  @override
  String get deviceNotCompatibleTitle => 'Naprava ni združljiva';

  @override
  String get deviceNotMeetRequirements => 'Vaša naprava ne izpolnjuje zahtev za transkripcijo na napravi.';

  @override
  String get transcriptionSlowerOnDevice => 'Transkripcija na napravi je lahko počasnejša na tej napravi.';

  @override
  String get computationallyIntensive => 'Transkripcija na napravi je računsko intenzivna.';

  @override
  String get batteryDrainSignificantly => 'Poraba baterije se bo significantly povečala.';

  @override
  String get premiumMinutesMonth =>
      '1.200 premijskih minut/mesec. Zavihek Na napravi ponuja neomejeno brezplačno transkripcijo. ';

  @override
  String get audioProcessedLocally =>
      'Zvok se obdeluje lokalno. Deluje brez interneta, bolj zasebno, vendar porabi več baterije.';

  @override
  String get languageLabel => 'Jezik';

  @override
  String get modelLabel => 'Model';

  @override
  String get modelTooLargeWarning =>
      'Ta model je velik in lahko sesede aplikacijo ali se izvaja zelo počasi na mobilnih napravah.\n\nPriporočljivi so \"mali\" ali \"osnovni\" modeli.';

  @override
  String get nativeEngineNoDownload => 'Uporabljena bo nativna govorica naprave. Prenos modela ni potreben.';

  @override
  String modelReadyWithName(String model) {
    return 'Model je pripravljen ($model)';
  }

  @override
  String get reDownload => 'Ponovno prenesite';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Prenašanje $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Pripravljanje $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Napaka pri prenosu: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Predvidena velikost: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Razpoložljiv prostor: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Vgrajena transkripcija Omi je optimizirana za pogovore v realnem času z avtomatskim prepoznavanjem govorcev in diarizacijo.';

  @override
  String get reset => 'Ponastavite';

  @override
  String get useTemplateFrom => 'Uporabite predlogo od';

  @override
  String get selectProviderTemplate => 'Izberite predlogo ponudnika...';

  @override
  String get quicklyPopulateResponse => 'Hitro izpolnite z znano obliko odgovora ponudnika';

  @override
  String get quicklyPopulateRequest => 'Hitro izpolnite z znano obliko zahtevka ponudnika';

  @override
  String get invalidJsonError => 'Neveljavna JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Prenesite model ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Model: $model';
  }

  @override
  String get device => 'Naprava';

  @override
  String get chatAssistantsTitle => 'Klepetalni asistenti';

  @override
  String get permissionReadConversations => 'Preberi pogovore';

  @override
  String get permissionReadMemories => 'Preberi spomine';

  @override
  String get permissionReadTasks => 'Preberi naloge';

  @override
  String get permissionCreateConversations => 'Ustvari pogovore';

  @override
  String get permissionCreateMemories => 'Ustvari spomine';

  @override
  String get permissionTypeAccess => 'Dostop';

  @override
  String get permissionTypeCreate => 'Ustvari';

  @override
  String get permissionTypeTrigger => 'Sprožilec';

  @override
  String get permissionDescReadConversations => 'Ta aplikacija ima dostop do vaših pogovorov.';

  @override
  String get permissionDescReadMemories => 'Ta aplikacija ima dostop do vaših spominov.';

  @override
  String get permissionDescReadTasks => 'Ta aplikacija ima dostop do vaših nalog.';

  @override
  String get permissionDescCreateConversations => 'Ta aplikacija lahko ustvari nove pogovore.';

  @override
  String get permissionDescCreateMemories => 'Ta aplikacija lahko ustvari nove spomine.';

  @override
  String get realtimeListening => 'Poslušanje v realnem času';

  @override
  String get setupCompleted => 'Dokončano';

  @override
  String get pleaseSelectRating => 'Prosim, izberite oceno';

  @override
  String get writeReviewOptional => 'Napišite oceno (neobvezno)';

  @override
  String get setupQuestionsIntro => 'Pomagajte nam izboljšati Omi z odgovori na nekaj vprašanj.  🫶 💜';

  @override
  String get setupQuestionProfession => '1. Kaj počneš?';

  @override
  String get setupQuestionUsage => '2. Kje nameravate uporabljati svoj Omi?';

  @override
  String get setupQuestionAge => '3. Kakšna je vaša starostna skupino?';

  @override
  String get setupAnswerAllQuestions => 'Niste odgovorili na vsa vprašanja! 🥺';

  @override
  String get setupSkipHelp => 'Preskoči, ne želim pomagati :C';

  @override
  String get professionEntrepreneur => 'Podjetnik';

  @override
  String get professionSoftwareEngineer => 'Inženir programske opreme';

  @override
  String get professionProductManager => 'Vodja proizvodov';

  @override
  String get professionExecutive => 'Direktor';

  @override
  String get professionSales => 'Prodaja';

  @override
  String get professionStudent => 'Študent';

  @override
  String get usageAtWork => 'Na delu';

  @override
  String get usageIrlEvents => 'Osebni dogodki';

  @override
  String get usageOnline => 'Spletno';

  @override
  String get usageSocialSettings => 'V družabnih nastavitvah';

  @override
  String get usageEverywhere => 'Povsod';

  @override
  String get customBackendUrlTitle => 'Prilagojeni URL hrbta';

  @override
  String get backendUrlLabel => 'URL hrbta';

  @override
  String get saveUrlButton => 'Shrani URL';

  @override
  String get enterBackendUrlError => 'Prosim, vnesite URL hrbta';

  @override
  String get urlMustEndWithSlashError => 'URL se mora končati z \"/\"';

  @override
  String get invalidUrlError => 'Prosim, vnesite veljaven URL';

  @override
  String get backendUrlSavedSuccess => 'URL hrbta je bil uspešno shranjen!';

  @override
  String get signInTitle => 'Prijava';

  @override
  String get signInButton => 'Prijava';

  @override
  String get enterEmailError => 'Prosim, vnesite svojo e-pošto';

  @override
  String get invalidEmailError => 'Prosim, vnesite veljavno e-pošto';

  @override
  String get enterPasswordError => 'Prosim, vnesite svojo geslo';

  @override
  String get passwordMinLengthError => 'Geslo mora biti dolgo najmanj 8 znakov';

  @override
  String get signInSuccess => 'Prijava uspešna!';

  @override
  String get alreadyHaveAccountLogin => 'Ste že registrirani? Prijavite se';

  @override
  String get emailLabel => 'E-pošta';

  @override
  String get passwordLabel => 'Geslo';

  @override
  String get createAccountTitle => 'Ustvari račun';

  @override
  String get nameLabel => 'Ime';

  @override
  String get repeatPasswordLabel => 'Ponovite geslo';

  @override
  String get signUpButton => 'Registracija';

  @override
  String get enterNameError => 'Prosim, vnesite svoje ime';

  @override
  String get passwordsDoNotMatch => 'Gesli se ne ujemata';

  @override
  String get signUpSuccess => 'Registracija uspešna!';

  @override
  String get loadingKnowledgeGraph => 'Nalagam grafikon znanja...';

  @override
  String get noKnowledgeGraphYet => 'Grafikon znanja še ni ustvarjen';

  @override
  String get buildingKnowledgeGraphFromMemories => 'Gradim vaš grafikon znanja iz spominov...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Vaš grafikon znanja se bo samodejno gradil, ko boste ustvarjali nove spomine.';

  @override
  String get buildGraphButton => 'Zgradite grafikon';

  @override
  String get checkOutMyMemoryGraph => 'Oglejte si moj grafikon spominov!';

  @override
  String get getButton => 'Pridobi';

  @override
  String openingApp(String appName) {
    return 'Odpiram $appName...';
  }

  @override
  String get writeSomething => 'Napišite kaj';

  @override
  String get submitReply => 'Pošlji odgovor';

  @override
  String get editYourReply => 'Uredite svoj odgovor';

  @override
  String get replyToReview => 'Odgovori na oceno';

  @override
  String get rateAndReviewThisApp => 'Ocenite in preglejte to aplikacijo';

  @override
  String get noChangesInReview => 'Ni sprememb v oceni za posodobitev.';

  @override
  String get cantRateWithoutInternet => 'Aplikacije ni mogoče oceniti brez internetne povezave.';

  @override
  String get appAnalytics => 'Analitika aplikacije';

  @override
  String get learnMoreLink => 'več informacij';

  @override
  String get moneyEarned => 'Zasluženi denar';

  @override
  String get writeYourReply => 'Napišite svoj odgovor...';

  @override
  String get replySentSuccessfully => 'Odgovor je uspešno poslan';

  @override
  String failedToSendReply(String error) {
    return 'Napaka pri pošiljanju odgovora: $error';
  }

  @override
  String get send => 'Pošlji';

  @override
  String starFilter(int count) {
    return '$count zvezda';
  }

  @override
  String get noReviewsFound => 'Nobene ocene ni bilo najdeno';

  @override
  String get editReply => 'Uredi odgovor';

  @override
  String get reply => 'Odgovori';

  @override
  String starFilterLabel(int count) {
    return '$count zvezda';
  }

  @override
  String get sharePublicLink => 'Deli javno povezavo';

  @override
  String get connectedKnowledgeData => 'Povezani podatki znanja';

  @override
  String get enterName => 'Vnesite ime';

  @override
  String get goal => 'CILJ';

  @override
  String get tapToTrackThisGoal => 'Tapnite, da spremljate ta cilj';

  @override
  String get tapToSetAGoal => 'Tapnite, da nastavite cilj';

  @override
  String get processedConversations => 'Obdelani pogovori';

  @override
  String get updatedConversations => 'Posodobljeni pogovori';

  @override
  String get newConversations => 'Novi pogovori';

  @override
  String get summaryTemplate => 'Predloga povzetka';

  @override
  String get suggestedTemplates => 'Predlagane predloge';

  @override
  String get otherTemplates => 'Druge predloge';

  @override
  String get availableTemplates => 'Razpoložljive predloge';

  @override
  String get getCreative => 'Bodite ustvarjalni';

  @override
  String get defaultLabel => 'Privzeto';

  @override
  String get lastUsedLabel => 'Zadnja uporaba';

  @override
  String get setDefaultApp => 'Nastavite privzeto aplikacijo';

  @override
  String setDefaultAppContent(String appName) {
    return 'Nastavite $appName kot privzeto aplikacijo za povzemanje?\\n\\nTa aplikacija bo samodejno uporabljena za vse prihodnje povzetke pogovorov.';
  }

  @override
  String get setDefaultButton => 'Nastavi privzeto';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName je nastavljena kot privzeta aplikacija za povzemanje';
  }

  @override
  String get createCustomTemplate => 'Ustvarite prilagojeno predlogo';

  @override
  String get allTemplates => 'Vse predloge';

  @override
  String failedToInstallApp(String appName) {
    return 'Napaka pri namestitvi $appName. Poskusite znova.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Napaka pri namestitvi $appName: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Označite govorца $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Oseba s tem imenom že obstaja.';

  @override
  String get selectYouFromList => 'Če se želite označiti, prosim izberite \"Vi\" s seznama.';

  @override
  String get enterPersonsName => 'Vnesite ime osebe';

  @override
  String get addPerson => 'Dodaj osebo';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Označite druge segmente tega govorça ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Označite druge segmente';

  @override
  String get managePeople => 'Upravljajte osebe';

  @override
  String get shareViaSms => 'Deli prek SMS-a';

  @override
  String get selectContactsToShareSummary => 'Izberite stike, s katerimi želite deliti povzetek pogovora';

  @override
  String get searchContactsHint => 'Iskanje stikov...';

  @override
  String contactsSelectedCount(int count) {
    return '$count izbranih';
  }

  @override
  String get clearAllSelection => 'Počisti vse';

  @override
  String get selectContactsToShare => 'Izberite stike, s katerimi želite deliti';

  @override
  String shareWithContactCount(int count) {
    return 'Deli z $count stikom';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Deli z $count stiki';
  }

  @override
  String get contactsPermissionRequired => 'Dovoljena dostopa do stikov';

  @override
  String get contactsPermissionRequiredForSms => 'Dovoljenje dostopa do stikov je potrebno za deljenje prek SMS-a';

  @override
  String get grantContactsPermissionForSms => 'Prosim, dodelite dovoljenje dostopa do stikov, da delite prek SMS-a';

  @override
  String get noContactsWithPhoneNumbers => 'Nobenih stikov s telefonskimi številkami ni bilo najdeno';

  @override
  String get noContactsMatchSearch => 'Noben stik se ne ujema z iskanjem';

  @override
  String get failedToLoadContacts => 'Napaka pri nalaganju stikov';

  @override
  String get failedToPrepareConversationForSharing => 'Napaka pri pripravi pogovora za deljenje. Poskusite znova.';

  @override
  String get couldNotOpenSmsApp => 'SMS aplikacije ni bilo mogoče odpreti. Poskusite znova.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Tukaj je, kaj smo pravkar razpravljali: $link';
  }

  @override
  String get wifiSync => 'Sinhronizacija WiFi';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopiran v odložišče';
  }

  @override
  String get wifiConnectionFailedTitle => 'Povezava neuspešna';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Povezovanje z $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Omogočite WiFi na $deviceName';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Povežite se z $deviceName';
  }

  @override
  String get recordingDetails => 'Podrobnosti snemanja';

  @override
  String get storageLocationSdCard => 'SD kartica';

  @override
  String get storageLocationLimitlessPendant => 'Limitless Pendant';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (spomin)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Shranjeno na $deviceName';
  }

  @override
  String get transferring => 'Prenašanje...';

  @override
  String get transferRequired => 'Prenos je potreben';

  @override
  String get downloadingAudioFromSdCard => 'Prenašanje zvoka iz SD kartice vaše naprave';

  @override
  String get transferRequiredDescription =>
      'To snemanje je shranjeno na SD kartici vaše naprave. Prenesete ga na telefon, da ga lahko predvajate ali delite.';

  @override
  String get cancelTransfer => 'Prekliči prenos';

  @override
  String get transferToPhone => 'Prenesi na telefon';

  @override
  String get privateAndSecureOnDevice => 'Zasebno in varno na vaši napravi';

  @override
  String get recordingInfo => 'Informacije o snemanju';

  @override
  String get transferInProgress => 'Prenos v teku...';

  @override
  String get shareRecording => 'Deli Snemanje';

  @override
  String get deleteRecordingConfirmation =>
      'Ali ste prepričani, da želite trajno izbrisati to snemanje? To se ne more razveljaviti.';

  @override
  String get recordingIdLabel => 'ID Snemanja';

  @override
  String get dateTimeLabel => 'Datum in Čas';

  @override
  String get durationLabel => 'Trajanje';

  @override
  String get audioFormatLabel => 'Format Zvoka';

  @override
  String get storageLocationLabel => 'Lokacija Shranjenja';

  @override
  String get estimatedSizeLabel => 'Ocenjena Velikost';

  @override
  String get deviceModelLabel => 'Model Naprave';

  @override
  String get deviceIdLabel => 'ID Naprave';

  @override
  String get statusLabel => 'Stanje';

  @override
  String get statusProcessed => 'Obdelano';

  @override
  String get statusUnprocessed => 'Neobdelano';

  @override
  String get switchedToFastTransfer => 'Prešli na Hiter Prenos';

  @override
  String get transferCompleteMessage => 'Prenos je končan! Sedaj lahko predvajate to snemanje.';

  @override
  String transferFailedMessage(String error) {
    return 'Prenos ni uspel: $error';
  }

  @override
  String get transferCancelled => 'Prenos je preklican';

  @override
  String get fastTransferEnabled => 'Hiter prenos je omogočen';

  @override
  String get bluetoothSyncEnabled => 'Bluetooth sinhronizacija je omogočena';

  @override
  String get enableFastTransfer => 'Omogoči Hiter Prenos';

  @override
  String get fastTransferDescription =>
      'Hiter prenos uporablja WiFi za približno 5-krat hitrejše hitrosti. Vaš telefon se bo med prenosom začasno povezal na WiFi omrežje naprave Omi.';

  @override
  String get internetAccessPausedDuringTransfer => 'Dostop do interneta je zaustavljen med prenosom';

  @override
  String get chooseTransferMethodDescription => 'Izberite, kako se snemanja prenašajo z naprave Omi na vaš telefon.';

  @override
  String get wifiSpeed => '~150 KB/s prek WiFi';

  @override
  String get fiveTimesFaster => '5-KRAT HITREJŠE';

  @override
  String get fastTransferMethodDescription =>
      'Ustvari neposredno WiFi povezavo z napravo Omi. Vaš telefon se med prenosom začasno odklopi od običajnega WiFi omrežja.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s prek BLE';

  @override
  String get bluetoothMethodDescription =>
      'Uporablja standardno Bluetooth Low Energy povezavo. Počasneje, vendar ne vpliva na vašo WiFi povezavo.';

  @override
  String get selected => 'Izbrano';

  @override
  String get selectOption => 'Izberi';

  @override
  String get lowBatteryAlertTitle => 'Opozorilo o Nizki Bateriji';

  @override
  String get lowBatteryAlertBody => 'Vaša naprava ima nizko baterijo. Čas je za polnjenje! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle => 'Vaša Naprava Omi je Odklopljena';

  @override
  String get deviceDisconnectedNotificationBody => 'Prosimo, ponovno se povežite, da nadaljujete z uporabo Omi.';

  @override
  String get firmwareUpdateAvailable => 'Posodobitev Vdelane Programske Opreme je Dostopna';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Nova posodobitev vdelane programske opreme ($version) je dostopna za vaš naprav Omi. Ali želite posodobiti zdaj?';
  }

  @override
  String get later => 'Kasneje';

  @override
  String get appDeletedSuccessfully => 'Aplikacija je bila uspešno izbrisana';

  @override
  String get appDeleteFailed => 'Brisanje aplikacije ni uspelo. Prosimo, poskusite ponovno pozneje.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Vidnost aplikacije se je uspešno spremenila. Morda bo potrebnih nekaj minut, da se to odraži.';

  @override
  String get errorActivatingAppIntegration =>
      'Napaka pri aktivaciji aplikacije. Če je to integrativna aplikacija, se prepričajte, da je nastavitev končana.';

  @override
  String get errorUpdatingAppStatus => 'Prišlo je do napake pri posodabljanju statusa aplikacije.';

  @override
  String get calculatingETA => 'Izračunavanje...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Približno $minutes minut preostane';
  }

  @override
  String get aboutAMinuteRemaining => 'Približno minuta preostane';

  @override
  String get almostDone => 'Skoraj končano...';

  @override
  String get omiSays => 'omi pravi';

  @override
  String get analyzingYourData => 'Analiza vaših podatkov...';

  @override
  String migratingToProtection(String level) {
    return 'Migracija na zaščito $level...';
  }

  @override
  String get noDataToMigrateFinalizing => 'Ni podatkov za migriranje. Zaključevanje...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return 'Migriranje $itemType... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing => 'Vsi predmeti so migrirani. Zaključevanje...';

  @override
  String get migrationErrorOccurred => 'Med migracijo je prišlo do napake. Prosimo, poskusite ponovno.';

  @override
  String get migrationComplete => 'Migracija je končana!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Vaši podatki so zdaj zaščiteni z novimi $level nastavitvami.';
  }

  @override
  String get chatsLowercase => 'pogovori';

  @override
  String get dataLowercase => 'podatki';

  @override
  String get fallNotificationTitle => 'Avv';

  @override
  String get fallNotificationBody => 'Ali ste padli?';

  @override
  String get importantConversationTitle => 'Pomemben Pogovor';

  @override
  String get importantConversationBody => 'Pravkar ste imeli pomemben pogovor. Tapnite, da delite povzetek z drugimi.';

  @override
  String get templateName => 'Ime Predloge';

  @override
  String get templateNameHint => 'npr. Izvleček Akcijskih Postavk na Sestanku';

  @override
  String get nameMustBeAtLeast3Characters => 'Ime mora biti dolgo najmanj 3 znake';

  @override
  String get conversationPromptHint =>
      'npr. Izvedite akcijske postavke, sprejete odločitve in ključne ugotovitve iz podanega pogovora.';

  @override
  String get pleaseEnterAppPrompt => 'Prosimo, vnesite nalogo za vašo aplikacijo';

  @override
  String get promptMustBeAtLeast10Characters => 'Naloga mora biti dolga najmanj 10 znakov';

  @override
  String get anyoneCanDiscoverTemplate => 'Kdor koli lahko odkrije vašo predlogo';

  @override
  String get onlyYouCanUseTemplate => 'Samo vi lahko uporabite to predlogo';

  @override
  String get generatingDescription => 'Ustvarjanje opisa...';

  @override
  String get creatingAppIcon => 'Ustvarjanje ikone aplikacije...';

  @override
  String get installingApp => 'Namestitev aplikacije...';

  @override
  String get appCreatedAndInstalled => 'Aplikacija je ustvarjena in nameščena!';

  @override
  String get appCreatedSuccessfully => 'Aplikacija je bila uspešno ustvarjena!';

  @override
  String get failedToCreateApp => 'Ustvarjanje aplikacije ni uspelo. Prosimo, poskusite ponovno.';

  @override
  String get addAppSelectCoreCapability =>
      'Prosimo, izberite eno dodatno temeljno sposobnost za vašo aplikacijo, da nadaljujete';

  @override
  String get addAppSelectPaymentPlan => 'Prosimo, izberite načrt plačila in vnesite ceno za vašo aplikacijo';

  @override
  String get addAppSelectCapability => 'Prosimo, izberite vsaj eno sposobnost za vašo aplikacijo';

  @override
  String get addAppSelectLogo => 'Prosimo, izberite logotip za vašo aplikacijo';

  @override
  String get addAppEnterChatPrompt => 'Prosimo, vnesite nalogo za klepet za vašo aplikacijo';

  @override
  String get addAppEnterConversationPrompt => 'Prosimo, vnesite nalogo za pogovor za vašo aplikacijo';

  @override
  String get addAppSelectTriggerEvent => 'Prosimo, izberite sprožilni dogodek za vašo aplikacijo';

  @override
  String get addAppEnterWebhookUrl => 'Prosimo, vnesite URL webhoka za vašo aplikacijo';

  @override
  String get addAppSelectCategory => 'Prosimo, izberite kategorijo za vašo aplikacijo';

  @override
  String get addAppFillRequiredFields => 'Prosimo, pravilno izpolnite vsa zahtevana polja';

  @override
  String get addAppUpdatedSuccess => 'Aplikacija je bila uspešno posodobljena 🚀';

  @override
  String get addAppUpdateFailed => 'Posodobljanje aplikacije ni uspelo. Prosimo, poskusite ponovno pozneje';

  @override
  String get addAppSubmittedSuccess => 'Aplikacija je bila uspešno poslana 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Napaka pri odpiranju izbirnika datotek: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Napaka pri izbiri slike: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Dovoljenje za dostop do fotografij je zavrnjeno. Prosimo, dovolite dostop do fotografij, da izberete sliko';

  @override
  String get addAppErrorSelectingImageRetry => 'Napaka pri izbiri slike. Prosimo, poskusite ponovno.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Napaka pri izbiri sličice: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry => 'Napaka pri izbiri sličice. Prosimo, poskusite ponovno.';

  @override
  String get addAppCapabilityConflictWithPersona => 'Ostalih sposobnosti ni mogoče izbrati s osebnostjo';

  @override
  String get addAppPersonaConflictWithCapabilities => 'Osebnosti ni mogoče izbrati z drugimi sposobnostmi';

  @override
  String get paymentFailedToFetchCountries =>
      'Pridobivanje podprtih držav ni uspelo. Prosimo, poskusite ponovno pozneje.';

  @override
  String get paymentFailedToSetDefault =>
      'Nastavitev privzete metode plačila ni uspela. Prosimo, poskusite ponovno pozneje.';

  @override
  String get paymentFailedToSavePaypal => 'Shranjevanje podatkov PayPal ni uspelo. Prosimo, poskusite ponovno pozneje.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktivna';

  @override
  String get paymentStatusConnected => 'Povezana';

  @override
  String get paymentStatusNotConnected => 'Ni Povezana';

  @override
  String get paymentAppCost => 'Cena Aplikacije';

  @override
  String get paymentEnterValidAmount => 'Prosimo, vnesite veljaven znesek';

  @override
  String get paymentEnterAmountGreaterThanZero => 'Prosimo, vnesite znesek večji od 0';

  @override
  String get paymentPlan => 'Načrt Plačila';

  @override
  String get paymentNoneSelected => 'Nobena Ni Izbrana';

  @override
  String get aiGenPleaseEnterDescription => 'Prosimo, vnesite opis za vašo aplikacijo';

  @override
  String get aiGenCreatingAppIcon => 'Ustvarjanje ikone aplikacije...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Prišlo je do napake: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Aplikacija je bila uspešno ustvarjena!';

  @override
  String get aiGenFailedToCreateApp => 'Ustvarjanje aplikacije ni uspelo';

  @override
  String get aiGenErrorWhileCreatingApp => 'Med ustvarjanjem aplikacije je prišlo do napake';

  @override
  String get aiGenFailedToGenerateApp => 'Ustvarjanje aplikacije ni uspelo. Prosimo, poskusite ponovno.';

  @override
  String get aiGenFailedToRegenerateIcon => 'Ponovno ustvarjanje ikone ni uspelo';

  @override
  String get aiGenPleaseGenerateAppFirst => 'Prosimo, najprej ustvarite aplikacijo';

  @override
  String get nextButton => 'Naprej';

  @override
  String get connectOmiDevice => 'Povežite Napravo Omi';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Vaš Neomejeni Načrt Spreminjate na $title. Ali ste prepričani, da želite nadaljevati?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Nadgradnja je zakazana! Vaš mesečni načrt se nadaljuje do konca vašega obračunskega obdobja, nato pa se samodejno spremeni na letni.';

  @override
  String get couldNotSchedulePlanChange => 'Spremembe načrta ni bilo mogoče zakazati. Prosimo, poskusite ponovno.';

  @override
  String get subscriptionReactivatedDefault =>
      'Vaša naročnina je bila ponovno aktivirana! Brez doplačila zdaj - zaračunani boste ob koncu vašega trenutnega obdobja.';

  @override
  String get subscriptionSuccessfulCharged => 'Naročnina je uspešna! Za novo obračunsko obdobje ste bili zaračunani.';

  @override
  String get couldNotProcessSubscription => 'Naročnine ni bilo mogoče obdelati. Prosimo, poskusite ponovno.';

  @override
  String get couldNotLaunchUpgradePage => 'Strani za nadgradnjo ni bilo mogoče zagnati. Prosimo, poskusite ponovno.';

  @override
  String get transcriptionJsonPlaceholder => 'Sem prilepite vašo JSON konfiguracijsko datoteko...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Napaka pri odpiranju izbirnika datotek: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Napaka: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Pogovori so bili uspešno Zusammenfasst';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count pogovorov je bilo uspešno zbivanja';
  }

  @override
  String get actionItemReminderTitle => 'Opomnik Omi';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName je Odklopljena';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Prosimo, ponovno se povežite, da nadaljujete z uporabo $deviceName.';
  }

  @override
  String get onboardingSignIn => 'Prijava';

  @override
  String get onboardingYourName => 'Vaše Ime';

  @override
  String get onboardingLanguage => 'Jezik';

  @override
  String get onboardingPermissions => 'Dovoljenja';

  @override
  String get onboardingComplete => 'Končaj';

  @override
  String get onboardingWelcomeToOmi => 'Dobrodošli v Omi';

  @override
  String get onboardingTellUsAboutYourself => 'Povejte nam o sebi';

  @override
  String get onboardingChooseYourPreference => 'Izberite svojo preference';

  @override
  String get onboardingGrantRequiredAccess => 'Dodelite potreben dostop';

  @override
  String get onboardingYoureAllSet => 'Vse ste pripravljeni';

  @override
  String get searchTranscriptOrSummary => 'Poišči prepis ali povzetek...';

  @override
  String get myGoal => 'Moj cilj';

  @override
  String get appNotAvailable => 'Ojej! Izgleda, da aplikacija, ki jo iščete, ni dostopna.';

  @override
  String get failedToConnectTodoist => 'Povezava s Todoist ni uspela';

  @override
  String get failedToConnectAsana => 'Povezava s Asana ni uspela';

  @override
  String get failedToConnectGoogleTasks => 'Povezava s Google Tasks ni uspela';

  @override
  String get failedToConnectClickUp => 'Povezava s ClickUp ni uspela';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return 'Povezava s $serviceName ni uspela: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Uspešno povezani s Todoist!';

  @override
  String get failedToConnectTodoistRetry => 'Povezava s Todoist ni uspela. Prosimo, poskusite ponovno.';

  @override
  String get successfullyConnectedAsana => 'Uspešno povezani s Asana!';

  @override
  String get failedToConnectAsanaRetry => 'Povezava s Asana ni uspela. Prosimo, poskusite ponovno.';

  @override
  String get successfullyConnectedGoogleTasks => 'Uspešno povezani s Google Tasks!';

  @override
  String get failedToConnectGoogleTasksRetry => 'Povezava s Google Tasks ni uspela. Prosimo, poskusite ponovno.';

  @override
  String get successfullyConnectedClickUp => 'Uspešno povezani s ClickUp!';

  @override
  String get failedToConnectClickUpRetry => 'Povezava s ClickUp ni uspela. Prosimo, poskusite ponovno.';

  @override
  String get successfullyConnectedNotion => 'Uspešno povezani s Notion!';

  @override
  String get failedToRefreshNotionStatus => 'Osveževanje stanja Notion povezave ni uspelo.';

  @override
  String get successfullyConnectedGoogle => 'Uspešno povezani s Google!';

  @override
  String get failedToRefreshGoogleStatus => 'Osveževanje stanja Google povezave ni uspelo.';

  @override
  String get successfullyConnectedWhoop => 'Uspešno povezani s Whoop!';

  @override
  String get failedToRefreshWhoopStatus => 'Osveževanje stanja Whoop povezave ni uspelo.';

  @override
  String get successfullyConnectedGitHub => 'Uspešno povezani s GitHub!';

  @override
  String get failedToRefreshGitHubStatus => 'Osveževanje stanja GitHub povezave ni uspelo.';

  @override
  String get authFailedToSignInWithGoogle => 'Prijava s Google ni uspela, prosimo, poskusite ponovno.';

  @override
  String get authenticationFailed => 'Avtentifikacija ni uspela. Prosimo, poskusite ponovno.';

  @override
  String get authFailedToSignInWithApple => 'Prijava s Apple ni uspela, prosimo, poskusite ponovno.';

  @override
  String get authFailedToRetrieveToken => 'Pridobivanje Firebase žetona ni uspelo, prosimo, poskusite ponovno.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Nepričakana napaka pri prijavi, napaka Firebase, prosimo, poskusite ponovno.';

  @override
  String get authUnexpectedError => 'Nepričakana napaka pri prijavi, prosimo, poskusite ponovno';

  @override
  String get authFailedToLinkGoogle => 'Povezovanje s Google ni uspelo, prosimo, poskusite ponovno.';

  @override
  String get authFailedToLinkApple => 'Povezovanje s Apple ni uspelo, prosimo, poskusite ponovno.';

  @override
  String get onboardingBluetoothRequired => 'Dovoljenječe za Bluetooth je potrebno za povezavo z napravo.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Dovoljenječe za Bluetooth je zavrnjeno. Prosimo, dovolite dostop v Sistemskih Preferencah.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Stanje dovoljenja za Bluetooth: $status. Prosimo, preverite Sistemske Preference.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Preverjanje dovoljenja za Bluetooth ni uspelo: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Dovoljenječe za Obvestila je zavrnjeno. Prosimo, dovolite dostop v Sistemskih Preferencah.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Dovoljenječe za Obvestila je zavrnjeno. Prosimo, dovolite dostop v Sistemskih Preferencah > Obvestila.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Stanje dovoljenja za Obvestila: $status. Prosimo, preverite Sistemske Preference.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Preverjanje dovoljenja za Obvestila ni uspelo: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Prosimo, dovolite dovoljenječe za lokacijo v Nastavitve > Zasebnost in Varnost > Storitve Lokacije';

  @override
  String get onboardingMicrophoneRequired => 'Dovoljenječe za Mikrofon je potrebno za snemanje.';

  @override
  String get onboardingMicrophoneDenied =>
      'Dovoljenječe za Mikrofon je zavrnjeno. Prosimo, dovolite dostop v Sistemskih Preferencah > Zasebnost in Varnost > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Stanje dovoljenja za Mikrofon: $status. Prosimo, preverite Sistemske Preference.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Preverjanje dovoljenja za Mikrofon ni uspelo: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'Dovoljenječe za Zajem Zaslona je potrebno za snemanje sistemskega zvoka.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Dovoljenječe za Zajem Zaslona je zavrnjeno. Prosimo, dovolite dostop v Sistemskih Preferencah > Zasebnost in Varnost > Snemanje Zaslona.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Stanje dovoljenja za Zajem Zaslona: $status. Prosimo, preverite Sistemske Preference.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Preverjanje dovoljenja za Zajem Zaslona ni uspelo: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Dovoljenječe za Dostopnost je potrebno za zaznavanje brskalniških sestankov.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Stanje dovoljenja za Dostopnost: $status. Prosimo, preverite Sistemske Preference.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Preverjanje dovoljenja za Dostopnost ni uspelo: $error';
  }

  @override
  String get msgCameraNotAvailable => 'Prikaz Kamere ni dostopen na tej platformi';

  @override
  String get msgCameraPermissionDenied => 'Dovoljenječe za Kamero je zavrnjeno. Prosimo, dovolite dostop do kamere';

  @override
  String msgCameraAccessError(String error) {
    return 'Napaka pri dostopu do kamere: $error';
  }

  @override
  String get msgPhotoError => 'Napaka pri zajemu slike. Prosimo, poskusite ponovno.';

  @override
  String get msgMaxImagesLimit => 'Izberete lahko samo do 4 slike';

  @override
  String msgFilePickerError(String error) {
    return 'Napaka pri odpiranju izbirnika datotek: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Napaka pri izbiri slik: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Dovoljenječe za Fotografije je zavrnjeno. Prosimo, dovolite dostop do fotografij, da izberete slike';

  @override
  String get msgSelectImagesGenericError => 'Napaka pri izbiri slik. Prosimo, poskusite ponovno.';

  @override
  String get msgMaxFilesLimit => 'Izberete lahko samo do 4 datotek';

  @override
  String msgSelectFilesError(String error) {
    return 'Napaka pri izbiri datotek: $error';
  }

  @override
  String get msgSelectFilesGenericError => 'Napaka pri izbiri datotek. Prosimo, poskusite ponovno.';

  @override
  String get msgUploadFileFailed => 'Nalaganje datoteke ni uspelo, prosimo, poskusite ponovno pozneje';

  @override
  String get msgReadingMemories => 'Branje vaših spominov...';

  @override
  String get msgLearningMemories => 'Učenje iz vaših spominov...';

  @override
  String get msgUploadAttachedFileFailed => 'Nalaganje priložene datoteke ni uspelo.';

  @override
  String captureRecordingError(String error) {
    return 'Med snemanjem je prišlo do napake: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Snemanje je zaustavljeno: $reason. Morda boste morali ponovno povezati zunanje zaslone ali ponovno zagnati snemanje.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Potrebno je dovoljenječe za Mikrofon';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Dodelite dovoljenječe za Mikrofon v Sistemskih Preferencah';

  @override
  String get captureScreenRecordingPermissionRequired => 'Potrebno je dovoljenječe za Snemanje Zaslona';

  @override
  String get captureDisplayDetectionFailed => 'Zaznava zaslona ni uspela. Snemanje je zaustavljeno.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl => 'Neveljaven URL webohoka za Zvočne Bajte';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl => 'Neveljaven URL webohoka za Prepis v Realnem Času';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl => 'Neveljaven URL webohoka za Ustvari Pogovor';

  @override
  String get devModeInvalidDaySummaryWebhookUrl => 'Neveljaven URL webohoka za Povzetek Dneva';

  @override
  String get devModeSettingsSaved => 'Nastavitve so shranjene!';

  @override
  String get voiceFailedToTranscribe => 'Prepis zvoka ni uspel';

  @override
  String get locationPermissionRequired => 'Dovoljenječe za Lokacijo je Potrebno';

  @override
  String get locationPermissionContent =>
      'Hiter prenos zahteva dovoljenječe za lokacijo za preverjanje WiFi povezave. Prosimo, dovolite dovoljenječe za lokacijo, da nadaljujete.';

  @override
  String get pdfTranscriptExport => 'Izvoz Prepisа';

  @override
  String get pdfConversationExport => 'Izvoz Pogovora';

  @override
  String pdfTitleLabel(String title) {
    return 'Naslov: $title';
  }

  @override
  String get conversationNewIndicator => 'Novo 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotografij';
  }

  @override
  String get mergingStatus => 'Zbivanje...';

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
    return '$count ura';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count ur';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours ur $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count dan';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count dni';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days dni $hours ur';
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
  String get moveToFolder => 'Premakni v Mapo';

  @override
  String get noFoldersAvailable => 'Nobena mapa ni dostopna';

  @override
  String get newFolder => 'Nova Mapa';

  @override
  String get color => 'Barva';

  @override
  String get waitingForDevice => 'Čakanje na napravo...';

  @override
  String get saySomething => 'Povejte kaj...';

  @override
  String get initialisingSystemAudio => 'Inicijalizacija Sistemskega Zvoka';

  @override
  String get stopRecording => 'Ustavi Snemanje';

  @override
  String get continueRecording => 'Nadaljuj Snemanje';

  @override
  String get initialisingRecorder => 'Inicijalizacija Snemalnika';

  @override
  String get pauseRecording => 'Pauzira Snemanje';

  @override
  String get resumeRecording => 'Nadaljuj Snemanje';

  @override
  String get noDailyRecapsYet => 'Še ni dnevnih povzetkov';

  @override
  String get dailyRecapsDescription => 'Vaši dnevni povzetki se bodo pojavili tukaj, ko bodo ustvarjeni';

  @override
  String get chooseTransferMethod => 'Izberite Način Prenosa';

  @override
  String get fastTransferSpeed => '~150 KB/s prek WiFi';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Zaznana velika časovna vrzel ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Zaznane velike časovne vrzeli ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Naprava ne podpira WiFi sinhronizacije, preklapljam na Bluetooth';

  @override
  String get appleHealthNotAvailable => 'Apple Health ni dostopen na tej napravi';

  @override
  String get downloadAudio => 'Preznesi Zvok';

  @override
  String get audioDownloadSuccess => 'Zvok je bil uspešno presnesen';

  @override
  String get audioDownloadFailed => 'Presnos zvoka ni uspel';

  @override
  String get downloadingAudio => 'Presnos zvoka...';

  @override
  String get shareAudio => 'Deli Zvok';

  @override
  String get preparingAudio => 'Priprava Zvoka';

  @override
  String get gettingAudioFiles => 'Pridobivanje zvočnih datotek...';

  @override
  String get downloadingAudioProgress => 'Presnos Zvoka';

  @override
  String get processingAudio => 'Obdelava Zvoka';

  @override
  String get combiningAudioFiles => 'Kombiniranje zvočnih datotek...';

  @override
  String get audioReady => 'Zvok je Pripravljen';

  @override
  String get openingShareSheet => 'Odpiranje lista za delovanje...';

  @override
  String get audioShareFailed => 'Delovanje Ni Uspelo';

  @override
  String get dailyRecaps => 'Dnevni Povzetki';

  @override
  String get removeFilter => 'Odstrani Filter';

  @override
  String get categoryConversationAnalysis => 'Analiza Pogovora';

  @override
  String get categoryHealth => 'Zdravje';

  @override
  String get categoryEducation => 'Izobraževanje';

  @override
  String get categoryCommunication => 'Komunikacija';

  @override
  String get categoryEmotionalSupport => 'Čustvena Podpora';

  @override
  String get categoryProductivity => 'Produktivnost';

  @override
  String get categoryEntertainment => 'Zabava';

  @override
  String get categoryFinancial => 'Finančno';

  @override
  String get categoryTravel => 'Potovanja';

  @override
  String get categorySafety => 'Varnost';

  @override
  String get categoryShopping => 'Nakupovanje';

  @override
  String get categorySocial => 'Socialno';

  @override
  String get categoryNews => 'Novice';

  @override
  String get categoryUtilities => 'Utilities';

  @override
  String get categoryOther => 'Drugo';

  @override
  String get capabilityChat => 'Klepet';

  @override
  String get capabilityConversations => 'Pogovori';

  @override
  String get capabilityExternalIntegration => 'Zunanja Integracija';

  @override
  String get capabilityNotification => 'Obvestilo';

  @override
  String get triggerAudioBytes => 'Zvočni Bajti';

  @override
  String get triggerConversationCreation => 'Ustvarjanje Pogovora';

  @override
  String get triggerTranscriptProcessed => 'Prepis je Obdelan';

  @override
  String get actionCreateConversations => 'Ustvari pogovore';

  @override
  String get actionCreateMemories => 'Ustvari spominе';

  @override
  String get actionReadConversations => 'Preberi pogovore';

  @override
  String get actionReadMemories => 'Preberi spomine';

  @override
  String get actionReadTasks => 'Preberi naloge';

  @override
  String get scopeUserName => 'Ime Uporabnika';

  @override
  String get scopeUserFacts => 'Dejstva o Uporabniku';

  @override
  String get scopeUserConversations => 'Pogovori Uporabnika';

  @override
  String get scopeUserChat => 'Klepet Uporabnika';

  @override
  String get capabilitySummary => 'Povzetek';

  @override
  String get capabilityFeatured => 'Predstavljene';

  @override
  String get capabilityTasks => 'Naloge';

  @override
  String get capabilityIntegrations => 'Integracije';

  @override
  String get categoryProductivityLifestyle => 'Produktivnost in Način Življenja';

  @override
  String get categorySocialEntertainment => 'Socialno in Zabava';

  @override
  String get categoryProductivityTools => 'Produktivnost in Orodja';

  @override
  String get categoryPersonalWellness => 'Osebno in stil';

  @override
  String get rating => 'Ocena';

  @override
  String get categories => 'Kategorije';

  @override
  String get sortBy => 'Razvrsti po';

  @override
  String get highestRating => 'Najvišja ocena';

  @override
  String get lowestRating => 'Najnižja ocena';

  @override
  String get resetFilters => 'Ponastavi filtre';

  @override
  String get applyFilters => 'Uporabi filtre';

  @override
  String get mostInstalls => 'Največ namestitev';

  @override
  String get couldNotOpenUrl => 'Spletne povezave ni bilo mogoče odpreti. Poskusi znova.';

  @override
  String get newTask => 'Nova opravila';

  @override
  String get viewAll => 'Prikaži vse';

  @override
  String get addTask => 'Dodaj opravilo';

  @override
  String get addMcpServer => 'Dodaj MCP strežnik';

  @override
  String get connectExternalAiTools => 'Poveži zunanje AI orodja';

  @override
  String get mcpServerUrl => 'URL MCP strežnika';

  @override
  String mcpServerConnected(int count) {
    return '$count orodja uspešno povezana';
  }

  @override
  String get mcpConnectionFailed => 'Napaka pri povezavi na MCP strežnik';

  @override
  String get authorizingMcpServer => 'Preverjam ...';

  @override
  String get whereDidYouHearAboutOmi => 'Kako si spoznal Omi?';

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
  String get pleaseSpecify => 'Prosimo, pojasni';

  @override
  String get event => 'Dogodek';

  @override
  String get coworker => 'Sodelavec';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google iskanje';

  @override
  String get audioPlaybackUnavailable => 'Avdio datoteka ni dostopna za predvajanje';

  @override
  String get audioPlaybackFailed => 'Avdio ni bilo mogoče predvajati. Datoteka je morda pokvarjena ali manjka.';

  @override
  String get connectionGuide => 'Vodnik za povezovanje';

  @override
  String get iveDoneThis => 'To sem storil';

  @override
  String get pairNewDevice => 'Poveži novo napravo';

  @override
  String get dontSeeYourDevice => 'Ne vidiš svoje naprave?';

  @override
  String get reportAnIssue => 'Prijavi težavo';

  @override
  String get pairingTitleOmi => 'Vključi Omi';

  @override
  String get pairingDescOmi => 'Drži in pritisni napravo, dokler se ne zatrese, da jo vključiš.';

  @override
  String get pairingTitleOmiDevkit => 'Postavi Omi DevKit v način pariranja';

  @override
  String get pairingDescOmiDevkit =>
      'Pritisni gumb enkrat, da ga vključiš. LED bo migal vijolično, ko je v načinu pariranja.';

  @override
  String get pairingTitleOmiGlass => 'Vključi Omi Glass';

  @override
  String get pairingDescOmiGlass => 'Vključi z drženjem bočnega gumba 3 sekunde.';

  @override
  String get pairingTitlePlaudNote => 'Postavi Plaud Note v način pariranja';

  @override
  String get pairingDescPlaudNote =>
      'Drži in pritisni bočni gumb 2 sekundi. Rdeči LED bo migal, ko je pripravljena za pariranje.';

  @override
  String get pairingTitleBee => 'Postavi Bee v način pariranja';

  @override
  String get pairingDescBee => 'Pritisni gumb 5-krat neprekinjeno. Luč bo začela migati modro in zeleno.';

  @override
  String get pairingTitleLimitless => 'Postavi Limitless v način pariranja';

  @override
  String get pairingDescLimitless =>
      'Ko je vidna kakšna luč, pritisni enkrat, nato pa drži, dokler naprava ne pokaže rožnate luči, nato spusti.';

  @override
  String get pairingTitleFriendPendant => 'Postavi Friend Pendant v način pariranja';

  @override
  String get pairingDescFriendPendant =>
      'Pritisni gumb na obesku, da ga vključiš. Avtomatsko bo vstopil v način pariranja.';

  @override
  String get pairingTitleFieldy => 'Postavi Fieldy v način pariranja';

  @override
  String get pairingDescFieldy => 'Drži in pritisni napravo, dokler se ne pojavi luč, da jo vključiš.';

  @override
  String get pairingTitleAppleWatch => 'Poveži Apple Watch';

  @override
  String get pairingDescAppleWatch => 'Namesti in odpri Omi aplikacijo na Apple Watch, nato v aplikaciji tapni Poveži.';

  @override
  String get pairingTitleNeoOne => 'Postavi Neo One v način pariranja';

  @override
  String get pairingDescNeoOne =>
      'Drži in pritisni gumb za napajanje, dokler LED ne začne migati. Naprava bo vidna za odkrivanje.';

  @override
  String get downloadingFromDevice => 'Prenašam z naprave';

  @override
  String get reconnectingToInternet => 'Ponovno se povezujem z internetom ...';

  @override
  String uploadingToCloud(int current, int total) {
    return 'Nalagam $current od $total';
  }

  @override
  String get processingOnServer => 'Obdelava na strežniku ...';

  @override
  String processingOnServerProgress(int current, int total) {
    return 'Obdelava ... $current/$total odsekov';
  }

  @override
  String get processedStatus => 'Obdelano';

  @override
  String get corruptedStatus => 'Poškodovano';

  @override
  String nPending(int count) {
    return '$count čakajočih';
  }

  @override
  String nProcessed(int count) {
    return '$count obdelanih';
  }

  @override
  String get synced => 'Sinhronizirano';

  @override
  String get noPendingRecordings => 'Ni čakajočih posnetkov';

  @override
  String get noProcessedRecordings => 'Še ni obdelanih posnetkov';

  @override
  String get pending => 'Čakajoče';

  @override
  String whatsNewInVersion(String version) {
    return 'Kaj je novega v $version';
  }

  @override
  String get addToYourTaskList => 'Dodaj na svoj seznam opravil?';

  @override
  String get failedToCreateShareLink => 'Napaka pri ustvarjanju povezave za deljenje';

  @override
  String get deleteGoal => 'Izbriši cilj';

  @override
  String get deviceUpToDate => 'Tvoja naprava je posodobljena';

  @override
  String get wifiConfiguration => 'Konfiguracija WiFi';

  @override
  String get wifiConfigurationSubtitle =>
      'Vneseuvoje WiFi poverilnice, da bo naprava mogla prenesti vdelano programsko opremo.';

  @override
  String get networkNameSsid => 'Ime omrežja (SSID)';

  @override
  String get enterWifiNetworkName => 'Vneseime WiFi omrežja';

  @override
  String get enterWifiPassword => 'Vnesi geslo WiFi';

  @override
  String get appIconLabel => 'Ikona aplikacije';

  @override
  String get onboardingWhatIKnowAboutYouTitle => 'Tukaj je, kaj vem o tebi';

  @override
  String get onboardingWhatIKnowAboutYouDescription => 'Ta zemljevid se posodablja, ko se Omi uči iz tvojih pogovorov.';

  @override
  String get apiEnvironment => 'API okolje';

  @override
  String get apiEnvironmentDescription => 'Izberi, s katerim zaledjem se želiš povezati';

  @override
  String get production => 'Produkcija';

  @override
  String get staging => 'Testiranje';

  @override
  String get switchRequiresRestart => 'Preklapljanje zahteva ponovno zagon aplikacije';

  @override
  String get switchApiConfirmTitle => 'Preklopi API okolje';

  @override
  String switchApiConfirmBody(String environment) {
    return 'Preklopi na $environment? Aplikacijo bo treba zapreti in znova odpreti, da se spremembe uveljavijo.';
  }

  @override
  String get switchAndRestart => 'Preklopi';

  @override
  String get stagingDisclaimer =>
      'Testiranje je lahko polno napak, zmogljivost je nestabilna, podatki pa se lahko izgubijo. Uporabi samo za preskušanje.';

  @override
  String get apiEnvSavedRestartRequired => 'Shranjeno. Zatvori in ponovno odpri aplikacijo, da se uporabijo spremembe.';

  @override
  String get shared => 'Deljeno';

  @override
  String get onlyYouCanSeeConversation => 'Samo ti lahko vidiš ta pogovor';

  @override
  String get anyoneWithLinkCanView => 'Kdor koli s povezavo ga lahko vidi';

  @override
  String get tasksCleanTodayTitle => 'Počisti današnja opravila?';

  @override
  String get tasksCleanTodayMessage => 'To bo zgolj odstranilo rok';

  @override
  String get tasksOverdue => 'Zamujeno';

  @override
  String get phoneCallsWithOmi => 'Telefonski klici z Omi';

  @override
  String get phoneCallsSubtitle => 'Kliči z živim prepisovanjem';

  @override
  String get phoneSetupStep1Title => 'Preveri svojo telefonsko številko';

  @override
  String get phoneSetupStep1Subtitle => 'Pokličemo te, da potrdimo, da je tvoja';

  @override
  String get phoneSetupStep2Title => 'Vnesi verifikacijsko kodo';

  @override
  String get phoneSetupStep2Subtitle => 'Kratka koda, ki jo vneseš med klicem';

  @override
  String get phoneSetupStep3Title => 'Začni kličati svoje stike';

  @override
  String get phoneSetupStep3Subtitle => 'Z vgrajenim živim prepisovanjem';

  @override
  String get phoneGetStarted => 'Začni';

  @override
  String get callRecordingConsentDisclaimer => 'Snemanje klicev je morda treba odobriti v tvoji državi';

  @override
  String get enterYourNumber => 'Vnesi svojo številko';

  @override
  String get phoneNumberCallerIdHint => 'Po preverjanju postane ta podana tvoj ID klicatelja';

  @override
  String get phoneNumberHint => 'Telefonska številka';

  @override
  String get failedToStartVerification => 'Napaka pri zagonu preverjanja';

  @override
  String get phoneContinue => 'Naprej';

  @override
  String get verifyYourNumber => 'Preveri svojo številko';

  @override
  String get answerTheCallFrom => 'Odgovori klicu od';

  @override
  String get onTheCallEnterThisCode => 'Med klicem vnesi to kodo';

  @override
  String get followTheVoiceInstructions => 'Sledi glasovnim navodilom';

  @override
  String get statusCalling => 'Kličem ...';

  @override
  String get statusCallInProgress => 'Klic je v teku';

  @override
  String get statusVerifiedLabel => 'Preverjeno';

  @override
  String get statusCallMissed => 'Klic je bil zameškan';

  @override
  String get statusTimedOut => 'Čas je potekel';

  @override
  String get phoneTryAgain => 'Poskusi znova';

  @override
  String get phonePageTitle => 'Telefon';

  @override
  String get phoneContactsTab => 'Stiki';

  @override
  String get phoneKeypadTab => 'Tipkovnica';

  @override
  String get grantContactsAccess => 'Odobri dostop do tvojih stikov';

  @override
  String get phoneAllow => 'Odobri';

  @override
  String get phoneSearchHint => 'Iskanje';

  @override
  String get phoneNoContactsFound => 'Stiki niso bili najdeni';

  @override
  String get phoneEnterNumber => 'Vnesi številko';

  @override
  String get failedToStartCall => 'Napaka pri zagonu klica';

  @override
  String get callStateConnecting => 'Povezujem ...';

  @override
  String get callStateRinging => 'Zvoni ...';

  @override
  String get callStateEnded => 'Klic je končan';

  @override
  String get callStateFailed => 'Klic je spodletel';

  @override
  String get transcriptPlaceholder => 'Prepis se bo pojavil tukaj ...';

  @override
  String get phoneUnmute => 'Omogući zvok';

  @override
  String get phoneMute => 'Utišaj';

  @override
  String get phoneSpeaker => 'Zvočnik';

  @override
  String get phoneEndCall => 'Konec';

  @override
  String get phoneCallSettingsTitle => 'Nastavitve telefonskih klicev';

  @override
  String get showPhoneCallButtonTitle => 'Pokaži gumb za klic';

  @override
  String get showPhoneCallButtonDesc => 'Prikaži gumb za telefonski klic na domačem zaslonu';

  @override
  String get yourVerifiedNumbers => 'Tvoje preverjene številke';

  @override
  String get verifiedNumbersDescription => 'Ko nekoga pokličeš, bo videl to številko na svojem telefonu';

  @override
  String get noVerifiedNumbers => 'Nima preverjenih številk';

  @override
  String deletePhoneNumberConfirm(String phoneNumber) {
    return 'Izbriši $phoneNumber?';
  }

  @override
  String get deletePhoneNumberWarning => 'Ponovno bo treba preverjati, da bi kličal';

  @override
  String get phoneDeleteButton => 'Izbriši';

  @override
  String verifiedMinutesAgo(int minutes) {
    return 'Preverjeno pred ${minutes}m';
  }

  @override
  String verifiedHoursAgo(int hours) {
    return 'Preverjeno pred ${hours}h';
  }

  @override
  String verifiedDaysAgo(int days) {
    return 'Preverjeno pred ${days}d';
  }

  @override
  String verifiedOnDate(String date) {
    return 'Preverjeno dne $date';
  }

  @override
  String get verifiedFallback => 'Preverjeno';

  @override
  String get callAlreadyInProgress => 'Klic je že v teku';

  @override
  String get failedToGetCallToken => 'Napaka pri pridobitvi žetona za klic. Najprej preveri svojo telefonsko številko.';

  @override
  String get failedToInitializeCallService => 'Napaka pri inicializaciji storitve klicev';

  @override
  String get speakerLabelYou => 'Ti';

  @override
  String get speakerLabelUnknown => 'Neznano';

  @override
  String get showDailyScoreOnHomepage => 'Prikaži dnevno oceno na domači strani';

  @override
  String get showTasksOnHomepage => 'Prikaži opravila na domači strani';

  @override
  String get phoneCallsUnlimitedOnly => 'Telefonski klici prek Omi';

  @override
  String get phoneCallsUpsellSubtitle =>
      'Kliči prek Omi in prejmi živo prepisovanje, samodejne povzetke in več. Na voljo izključno za naročnike načrta Unlimited.';

  @override
  String get phoneCallsUpsellFeature1 => 'Živo prepisovanje vsakega klica';

  @override
  String get phoneCallsUpsellFeature2 => 'Samodejni povzetki klicev in akcijski predmeti';

  @override
  String get phoneCallsUpsellFeature3 => 'Prejemniki vidijo tvojo pravo številko, ne naključno';

  @override
  String get phoneCallsUpsellFeature4 => 'Tvoji klici so zasebni in varni';

  @override
  String get phoneCallsUpgradeButton => 'Nadgradi na Unlimited';

  @override
  String get phoneCallsMaybeLater => 'Mogoče kasneje';

  @override
  String get deleteSynced => 'Izbriši sinhronizirano';

  @override
  String get deleteSyncedFiles => 'Izbriši sinhronizirane posnetke';

  @override
  String get deleteSyncedFilesMessage =>
      'Ti posnetki so bili že sinhronizirani s tvojim telefonom. Tega ni mogoče razveljaviti.';

  @override
  String get syncedFilesDeleted => 'Sinhronizirani posnetki so izbrisani';

  @override
  String get deletePending => 'Izbriši čakajoče';

  @override
  String get deletePendingFiles => 'Izbriši čakajoče posnetke';

  @override
  String get deletePendingFilesWarning =>
      'Ti posnetki NISO bili sinhronizirani s tvojim telefonom in bodo trajno izgubljeni. Tega ni mogoče razveljaviti.';

  @override
  String get pendingFilesDeleted => 'Čakajoči posnetki so izbrisani';

  @override
  String get deleteAllFiles => 'Izbriši vse posnetke';

  @override
  String get deleteAll => 'Izbriši vse';

  @override
  String get deleteAllFilesWarning =>
      'To bo izbrisalo tako sinhronizirane kot čakajoče posnetke. Čakajoči posnetki NISO bili sinhronizirani in bodo trajno izgubljeni. Tega ni mogoče razveljaviti.';

  @override
  String get allFilesDeleted => 'Vsi posnetki so izbrisani';

  @override
  String nFiles(int count) {
    return '$count posnetkov';
  }

  @override
  String get manageStorage => 'Upravljaj shramba';

  @override
  String get safelyBackedUp => 'Varno rezervirano na tvojem telefonu';

  @override
  String get notYetSynced => 'Še ni sinhronizirano s tvojim telefonom';

  @override
  String get clearAll => 'Počisti vse';

  @override
  String get phoneKeypad => 'Tipkovnica';

  @override
  String get phoneHideKeypad => 'Skrij tipkovnico';

  @override
  String get fairUsePolicy => 'Poštena raba';

  @override
  String get fairUseLoadError => 'Napaka pri nalaganju statusa poštene rabe. Prosimo poskusi znova.';

  @override
  String get fairUseStatusNormal => 'Tvoja poraba je v normalnih mejah.';

  @override
  String get fairUseStageNormal => 'Normalno';

  @override
  String get fairUseStageWarning => 'Opozorilo';

  @override
  String get fairUseStageThrottle => 'Omejeno';

  @override
  String get fairUseStageRestrict => 'Omejeno';

  @override
  String get fairUseSpeechUsage => 'Poraba govora';

  @override
  String get fairUseToday => 'Danes';

  @override
  String get fairUse3Day => '3-dnevni rolling';

  @override
  String get fairUseWeekly => 'Tedenski rolling';

  @override
  String get fairUseAboutTitle => 'O pošteni rabi';

  @override
  String get fairUseAboutBody =>
      'Omi je namenjen osebnim pogovorom, sestankom in živim interakcijam. Poraba se meri z detektiranim dejanskim časom govora, ne s časom povezave. Če poraba bistveno presega običajne vzorce za neprofesionalno vsebino, se lahko uporabijo prilagoditve.';

  @override
  String fairUseCaseRefCopied(String caseRef) {
    return '$caseRef kopiran';
  }

  @override
  String get fairUseDailyTranscription => 'Dnevno prepisovanje';

  @override
  String fairUseBudgetUsed(String used, String limit) {
    return '${used}m / ${limit}m';
  }

  @override
  String get fairUseBudgetExhausted => 'Dosežena dnevna meja prepisovanja';

  @override
  String fairUseBudgetResetsAt(String time) {
    return 'Ponastavi ob $time';
  }

  @override
  String get transcriptionPaused => 'Snemam, ponovno se povezujem';

  @override
  String get transcriptionPausedReconnecting => 'Še vedno snemam — ponovno se povezujem s prepisovanjem ...';

  @override
  String fairUseBannerStatus(String status) {
    return 'Poštena raba: $status';
  }

  @override
  String get improveConnectionTitle => 'Izboljšaj povezavo';

  @override
  String get improveConnectionContent =>
      'Izboljšali smo, kako se Omi ostane povezana z tvojo napravo. Če želiš to aktivirati, pojdi na stran Podatki naprave, tapni \"Prekini napravo\" in nato ponovno poveži svojo napravo.';

  @override
  String get improveConnectionAction => 'Razumem';

  @override
  String clockSkewWarning(int minutes) {
    return 'Ura na tvoji napravi je napačna za ~$minutes min. Preveridatum in čas.';
  }

  @override
  String get omisStorage => 'Omi-jeva shramba';

  @override
  String get phoneStorage => 'Shramba telefona';

  @override
  String get cloudStorage => 'Oblačna shramba';

  @override
  String get howSyncingWorks => 'Kako sinhronizacija deluje';

  @override
  String get noSyncedRecordings => 'Še ni sinhronizirano';

  @override
  String get recordingsSyncAutomatically => 'Posnetki se sinhronizirajo samodejno — ne potrebuješ ničesar početi.';

  @override
  String get filesDownloadedUploadedNextTime => 'Datoteke, ki so že prejete, bodo naložene naslednjič.';

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
  String get tapToView => 'Tapni za prikaz';

  @override
  String get syncFailed => 'Sinhronizacija je spodletela';

  @override
  String get keepSyncing => 'Nadaljuj s sinhronizacijo';

  @override
  String get cancelSyncQuestion => 'Prekini sinhronizacijo?';

  @override
  String get omisStorageDesc =>
      'Ko se tvoj Omi ne poveži s tvojim telefonom, shranja avdio lokalno v svoji vgrajeni pomnilnik. Nikoli ne izgubiš posnetka.';

  @override
  String get phoneStorageDesc =>
      'Ko se Omi znova poveži, se posnetki avtomatično prenesejo na tvoj telefon kot začasno skladišče, preden se naložijo.';

  @override
  String get cloudStorageDesc =>
      'Ko se naložijo, so tvoji posnetki obdelani in prepisani. Pogovori bodo na voljo v minuti.';

  @override
  String get tipKeepPhoneNearby => 'Drži svoj telefon blizu za hitrejšo sinhronizacijo';

  @override
  String get tipStableInternet => 'Stabilno interneto hitrejše nalaganje v oblak';

  @override
  String get tipAutoSync => 'Posnetki se sinhronizirajo samodejno';

  @override
  String get storageSection => 'SHRAMBA';

  @override
  String get permissions => 'Dovoljenja';

  @override
  String get permissionEnabled => 'Omogočeno';

  @override
  String get permissionEnable => 'Omogoči';

  @override
  String get permissionsPageDescription =>
      'Ta dovoljenja so ključna za delovanje Omi. Omogočajo ključne funkcije, kot so obvestila, izkušnje na osnovi lokacije in zajemanje avdija.';

  @override
  String get permissionsRequiredDescription =>
      'Omi potrebuje nekaj dovoljenj za pravilno delovanje. Prosimo, da jih odobriš, da nadaljuješ.';

  @override
  String get permissionsSetupTitle => 'Pridobi najboljšo izkušnjo';

  @override
  String get permissionsSetupDescription => 'Omogoči nekaj dovoljenj, da Omi deluje s polno zmogljivostjo.';

  @override
  String get permissionsChangeAnytime => 'Ta dovoljenja lahko kadarkoli spremenišv Nastavitve > Dovoljenja';

  @override
  String get location => 'Lokacija';

  @override
  String get microphone => 'Mikrofon';

  @override
  String get whyAreYouCanceling => 'Zakaj prekinjam?';

  @override
  String get cancelReasonSubtitle => 'Ali nam lahko povieš, zakaj odharjaš?';

  @override
  String get cancelReasonTooExpensive => 'Premalo';

  @override
  String get cancelReasonNotUsing => 'Nimam dovolj';

  @override
  String get cancelReasonMissingFeatures => 'Manjkajo značilnosti';

  @override
  String get cancelReasonAudioQuality => 'Kakovost avdija/prepisovanja';

  @override
  String get cancelReasonBatteryDrain => 'Skrbi glede polnjenja baterije';

  @override
  String get cancelReasonFoundAlternative => 'Našel sem alternativo';

  @override
  String get cancelReasonOther => 'Drugo';

  @override
  String get tellUsMore => 'Povej nam več (izbirno)';

  @override
  String get cancelReasonDetailHint => 'Cenimo vsak povratni odgovor ...';

  @override
  String get justAMoment => 'Počakaj malo';

  @override
  String get cancelConsequencesSubtitle => 'Toplo priporočamo, da raziščeš druge možnosti namesto preklica.';

  @override
  String cancelBillingPeriodInfo(String date) {
    return 'Tvoj načrt bo ostal aktiven do $date. Nato boš premeščen na brezplačno različico z omejenimi možnostmi.';
  }

  @override
  String get ifYouCancel => 'Če prekličeš:';

  @override
  String get cancelConsequenceNoAccess => 'Na koncu obdobja zaračunavanja ne boš več imel neomejenega dostopa.';

  @override
  String get cancelConsequenceBattery => '7-krat večja poraba baterije (obdelava na napravi)';

  @override
  String get cancelConsequenceQuality => '30 % nižja kakovost prepisovanja (modeli na napravi)';

  @override
  String get cancelConsequenceDelay => 'Zakasnitev obdelave 5-7 sekund (modeli na napravi)';

  @override
  String get cancelConsequenceSpeakers => 'Ne moreš prepoznati govorcev.';

  @override
  String get confirmAndCancel => 'Potrdi in prekliči';

  @override
  String get cancelConsequencePhoneCalls => 'Ni živega prepisovanja telefonskih klicev';

  @override
  String get feedbackTitleTooExpensive => 'Kakšna cena bi ti ustrezala?';

  @override
  String get feedbackTitleMissingFeatures => 'Katere značilnosti ti manjkajo?';

  @override
  String get feedbackTitleAudioQuality => 'Kakšne težave si izkusil?';

  @override
  String get feedbackTitleBatteryDrain => 'Povej nam o težavah z baterijo';

  @override
  String get feedbackTitleFoundAlternative => 'Na kaj se prebavljaš?';

  @override
  String get feedbackTitleNotUsing => 'Kaj bi te spodbudilo, da bi več uporabljal Omi?';

  @override
  String get feedbackSubtitleTooExpensive => 'Tvoj povratni odgovor nam pomaga najti pravo ravnovesje.';

  @override
  String get feedbackSubtitleMissingFeatures => 'Vedno gradimo — to nam pomaga pri prioritizaciji.';

  @override
  String get feedbackSubtitleAudioQuality => 'Rad bi razumel, kaj je šlo narobe.';

  @override
  String get feedbackSubtitleBatteryDrain => 'To pomaga našemu strojniškemu timu pri izboljšavah.';

  @override
  String get feedbackSubtitleFoundAlternative => 'Rad bi izvedel, kaj te je pritegnilo.';

  @override
  String get feedbackSubtitleNotUsing => 'Želimo narediti Omi bolj uporabnega zate.';

  @override
  String get deviceDiagnostics => 'Diagnostika naprave';

  @override
  String get signalStrength => 'Moč signala';

  @override
  String get connectionUptime => 'Čas delovanja';

  @override
  String get reconnections => 'Ponovno povezave';

  @override
  String get disconnectHistory => 'Zgodovina prekinjenih povezav';

  @override
  String get noDisconnectsRecorded => 'Ni zabeleženih prekinjenih povezav';

  @override
  String get diagnostics => 'Diagnostika';

  @override
  String get waitingForData => 'Čakam na podatke ...';

  @override
  String get liveRssiOverTime => 'Živo RSSI v času';

  @override
  String get noRssiDataYet => 'Še nima podatkov RSSI';

  @override
  String get collectingData => 'Zbiram podatke ...';

  @override
  String get cleanDisconnect => 'Čista prekinitev';

  @override
  String get connectionTimeout => 'Časovna omejitev povezave';

  @override
  String get remoteDeviceTerminated => 'Oddaljena naprava je prekinjena';

  @override
  String get pairedToAnotherPhone => 'Povezano z drugim telefonom';

  @override
  String get linkKeyMismatch => 'Neusklajenost ključa povezave';

  @override
  String get connectionFailed => 'Napaka pri povezavi';

  @override
  String get appClosed => 'Aplikacija je zaprta';

  @override
  String get manualDisconnect => 'Ročna prekinitev';

  @override
  String lastNEvents(int count) {
    return 'Zadnji $count dogodkov';
  }

  @override
  String get signal => 'Signal';

  @override
  String get battery => 'Baterija';

  @override
  String get excellent => 'Odličen';

  @override
  String get good => 'Dobro';

  @override
  String get fair => 'Pošteno';

  @override
  String get weak => 'Šibko';

  @override
  String gattError(String code) {
    return 'Napaka GATT ($code)';
  }

  @override
  String get batteryHistory => 'Baterija';

  @override
  String get noBatteryDataYet => 'Še ni podatkov o bateriji';

  @override
  String get day => 'Dan';

  @override
  String get week => 'Teden';

  @override
  String get rollbackToStableFirmware => 'Povrni na stabilno vdelano programsko opremo';

  @override
  String get rollbackConfirmTitle => 'Povrni vdelano programsko opremo?';

  @override
  String rollbackConfirmMessage(String version) {
    return 'To bo zamenjalo tvojo trenutno vdelano programsko opremo z najnovejšo stabilno različico ($version). Naprava se bo ponovno zagnala po posodobitvi.';
  }

  @override
  String get stableFirmware => 'Stabilna vdelana programska oprema';

  @override
  String get fetchingStableFirmware => 'Pridobivam najnovejšo stabilno vdelano programsko opremo ...';

  @override
  String get noStableFirmwareFound =>
      'Ni bilo mogoče najti stabilne različice vdelane programske opreme za tvojo napravo.';

  @override
  String get installStableFirmware => 'Namesti stabilno vdelano programsko opremo';

  @override
  String get alreadyOnStableFirmware => 'Že si na najnovejši stabilni različici.';

  @override
  String audioSavedLocally(String duration) {
    return '$duration avdija shranjenega lokalno';
  }

  @override
  String get willSyncAutomatically => 'se bo samodejno sinhroniziral';

  @override
  String get enableLocationTitle => 'Omogoči lokacijo';

  @override
  String get enableLocationDescription => 'Dovoljenje za lokacijo je potrebno za iskanje bližnjih Bluetooth naprav.';

  @override
  String get voiceRecordingFound => 'Posnetek je bil najden';

  @override
  String get transcriptionConnecting => 'Povezujem prepisovanje ...';

  @override
  String get transcriptionReconnecting => 'Ponovno se povezujem s prepisovanjem ...';

  @override
  String get transcriptionUnavailable => 'Prepisovanje ni na voljo';

  @override
  String get audioOutput => 'Avdio izhod';

  @override
  String get firmwareWarningTitle => 'Pomembno: Preberite pred posodobitvijo';

  @override
  String get firmwareFormatWarning =>
      'Ta vdelana programska oprema bo formatirala kartico SD. Pred nadgradnjo se prepričajte, da so vsi podatki brez povezave sinhronizirani.\n\nČe po namestitvi te različice vidite utripajočo rdečo lučko, ne skrbite. Preprosto povežite napravo z aplikacijo in morala bi postati modra. Rdeča lučka pomeni, da ura naprave še ni bila sinhronizirana.';

  @override
  String get continueAnyway => 'Nadaljuj';

  @override
  String get tasksClearCompleted => 'Počisti dokončane';

  @override
  String get tasksSelectAll => 'Izberi vse';

  @override
  String tasksDeleteSelected(int count) {
    return 'Izbriši $count nalogo(e)';
  }

  @override
  String get tasksMarkComplete => 'Označeno kot dokončano';

  @override
  String get appleHealthManageNote =>
      'Omi dostopa do Apple Health prek Applovega ogrodja HealthKit. Dostop lahko kadar koli prekličete v nastavitvah iOS.';

  @override
  String get appleHealthConnectCta => 'Poveži z Apple Health';

  @override
  String get appleHealthDisconnectCta => 'Prekini povezavo z Apple Health';

  @override
  String get appleHealthConnectedBadge => 'Povezano';

  @override
  String get appleHealthFeatureChatTitle => 'Pogovarjajte se o svojem zdravju';

  @override
  String get appleHealthFeatureChatDesc => 'Vprašajte Omi o vaših korakih, spanju, srčnem utripu in treningih.';

  @override
  String get appleHealthFeatureReadOnlyTitle => 'Dostop samo za branje';

  @override
  String get appleHealthFeatureReadOnlyDesc => 'Omi nikoli ne piše v Apple Health in ne spreminja vaših podatkov.';

  @override
  String get appleHealthFeatureSecureTitle => 'Varna sinhronizacija';

  @override
  String get appleHealthFeatureSecureDesc => 'Vaši podatki Apple Health se zasebno sinhronizirajo z računom Omi.';

  @override
  String get appleHealthDeniedTitle => 'Dostop do Apple Health zavrnjen';

  @override
  String get appleHealthDeniedBody =>
      'Omi nima dovoljenja za branje vaših podatkov Apple Health. Omogočite ga v Nastavitvah iOS → Zasebnost in varnost → Health → Omi.';

  @override
  String get deleteFlowReasonTitle => 'Zakaj odhajate?';

  @override
  String get deleteFlowReasonSubtitle => 'Vaše povratne informacije nam pomagajo izboljšati Omi za vse.';

  @override
  String get deleteReasonPrivacy => 'Skrbi glede zasebnosti';

  @override
  String get deleteReasonNotUsing => 'Ne uporabljam dovolj pogosto';

  @override
  String get deleteReasonMissingFeatures => 'Manjkajo funkcije, ki jih potrebujem';

  @override
  String get deleteReasonTechnicalIssues => 'Preveč tehničnih težav';

  @override
  String get deleteReasonFoundAlternative => 'Uporabljam nekaj drugega';

  @override
  String get deleteReasonTakingBreak => 'Samo si vzamem premor';

  @override
  String get deleteReasonOther => 'Drugo';

  @override
  String get deleteFlowFeedbackTitle => 'Povejte nam več';

  @override
  String get deleteFlowFeedbackSubtitle => 'Kaj bi povzročilo, da bi Omi deloval za vas?';

  @override
  String get deleteFlowFeedbackHint => 'Neobvezno — vaše misli nam pomagajo zgraditi boljši izdelek.';

  @override
  String get deleteFlowConfirmTitle => 'To je dokončno';

  @override
  String get deleteFlowConfirmSubtitle => 'Ko izbrišete račun, ga ni mogoče obnoviti.';

  @override
  String get deleteConsequenceSubscription => 'Kakršna koli aktivna naročnina bo preklicana.';

  @override
  String get deleteConsequenceNoRecovery => 'Vašega računa ni mogoče obnoviti — niti s strani podpore.';

  @override
  String get deleteTypeToConfirm => 'Vnesite DELETE za potrditev';

  @override
  String get deleteConfirmationWord => 'DELETE';

  @override
  String get deleteAccountPermanently => 'Trajno izbriši račun';

  @override
  String get keepMyAccount => 'Obdrži moj račun';

  @override
  String get deleteAccountFailed => 'Vašega računa ni bilo mogoče izbrisati. Poskusite znova.';

  @override
  String get planUpdate => 'Posodobitev načrta';

  @override
  String get planDeprecationMessage =>
      'Vaš načrt Unlimited se ukinja. Preklopite na načrt Operator — enake odlične funkcije za \$49/mesec. Vaš trenutni načrt bo medtem še naprej deloval.';

  @override
  String get upgradeYourPlan => 'Nadgradite svoj načrt';

  @override
  String get youAreOnAPaidPlan => 'Imate plačljiv načrt.';

  @override
  String get chatTitle => 'Klepet';

  @override
  String get chatMessages => 'sporočil';

  @override
  String get unlimitedChatThisMonth => 'Neomejeno število sporočil ta mesec';

  @override
  String chatUsedOfLimitCompute(String used, String limit) {
    return '$used od $limit proračuna porabljeno';
  }

  @override
  String chatUsedOfLimitMessages(String used, String limit) {
    return '$used od $limit sporočil porabljenih ta mesec';
  }

  @override
  String chatUsageProgress(String used, String limit) {
    return '$used / $limit porabljeno';
  }

  @override
  String get chatLimitReachedUpgrade => 'Dosežena omejitev klepeta. Nadgradite za več sporočil.';

  @override
  String get chatLimitReachedTitle => 'Dosežena omejitev klepeta';

  @override
  String chatUsageDescription(String used, String limitDisplay, String plan) {
    return 'Porabili ste $used od $limitDisplay na načrtu $plan.';
  }

  @override
  String resetsInDays(int count) {
    return 'Ponastavitev čez $count dni';
  }

  @override
  String resetsInHours(int count) {
    return 'Ponastavitev čez $count ur';
  }

  @override
  String get resetsSoon => 'Kmalu se ponastavi';

  @override
  String get upgradePlan => 'Nadgradi načrt';

  @override
  String get billingMonthly => 'Mesečno';

  @override
  String get billingYearly => 'Letno';

  @override
  String get savePercent => 'Prihranite ~17%';

  @override
  String get popular => 'Priljubljeno';

  @override
  String get currentPlan => 'Trenutni';

  @override
  String neoSubtitle(int count) {
    return '$count vprašanj na mesec';
  }

  @override
  String operatorSubtitle(int count) {
    return '$count vprašanj na mesec';
  }

  @override
  String get architectSubtitle => 'Napreden AI — tisoče pogovorov + agentna avtomatizacija';

  @override
  String chatUsageCost(String used, String limit) {
    return 'Klepet: \$$used / \$$limit porabljeno ta mesec';
  }

  @override
  String chatUsageCostNoLimit(String used) {
    return 'Klepet: \$$used porabljeno ta mesec';
  }

  @override
  String chatUsageMessages(String used, String limit) {
    return 'Klepet: $used / $limit sporočil ta mesec';
  }

  @override
  String chatUsageMessagesNoLimit(String used) {
    return 'Klepet: $used sporočil ta mesec';
  }

  @override
  String get chatQuotaSubtitle => 'AI chat messages used with Omi this month.';

  @override
  String get chatQuotaExceededReply =>
      'Dosegli ste svojo mesečno omejitev. Nadgradite, da nadaljujete pogovor z Omi brez omejitev.';

  @override
  String get voiceResponseAudio => 'Preberi odgovor Omi na glas';

  @override
  String get voiceResponseMode => 'Glasovni odgovor';

  @override
  String get voiceResponseModeTitle => 'Kdaj prebrati odgovore';

  @override
  String get voiceResponseOff => 'Izklop';

  @override
  String get voiceResponseHeadphonesOnly => 'Samo slušalke';

  @override
  String get voiceResponseAlways => 'Vedno';

  @override
  String get agreeAndContinue => 'Strinjam se in nadaljuj';

  @override
  String get startVoiceRecording => 'Začni glasovno snemanje';

  @override
  String get startCallRecording => 'Začni snemanje klica';

  @override
  String get mindMap => 'Mind Map';

  @override
  String get voiceMode => 'Glasovni način';

  @override
  String get quickActionAskOmi => 'Vprašajte Omi karkoli';

  @override
  String get record => 'Posnemi';

  @override
  String get stop => 'Ustavi';

  @override
  String get recordWithPhoneMic => 'Snemaj s telefonskim mikrofonom';

  @override
  String get recordWithPhoneMicSubtitle => 'Posnemite zvok okoli sebe';

  @override
  String get phoneCall => 'Telefonski klic';

  @override
  String get phoneCallSubtitle => 'Posnemite klic s prepisom v živo';

  @override
  String get searchActionItems => 'Iskanje akcijskih elementov';

  @override
  String get selectActionItems => 'Izberi več';

  @override
  String chooseExportDestination(int count) {
    return 'Izvozi $count element(ov) v…';
  }

  @override
  String get bulkExportInProgress => 'Izvažanje…';

  @override
  String bulkExportSuccess(int count, String platform) {
    return 'Izvoženo $count v $platform';
  }

  @override
  String bulkExportPartial(int success, int total, String platform) {
    return 'Izvoženo $success od $total v $platform';
  }

  @override
  String get showCompletedTasks => 'Prikaži dokončane';

  @override
  String get hideCompletedTasks => 'Skrij dokončane';

  @override
  String get selectAllTasksMenu => 'Izberi vse';

  @override
  String get connectTaskAppToExport => 'Povežite aplikacijo za naloge v Nastavitvah za izvoz';

  @override
  String get connectAction => 'Poveži';

  @override
  String get deselectAllTasksMenu => 'Prekliči izbor vseh';
}
