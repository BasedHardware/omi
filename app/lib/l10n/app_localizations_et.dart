// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Estonian (`et`).
class AppLocalizationsEt extends AppLocalizations {
  AppLocalizationsEt([String locale = 'et']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Vestlus';

  @override
  String get transcriptTab => 'Transkriptsioon';

  @override
  String get actionItemsTab => 'Tegevuspunktid';

  @override
  String get deleteConversationTitle => 'Kustuta vestlus?';

  @override
  String get deleteConversationMessage =>
      'Kas olete kindel, et soovite selle vestluse kustutada? Seda toimingut ei saa tagasi võtta.';

  @override
  String get confirm => 'Kinnita';

  @override
  String get cancel => 'Tühista';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Kustuta';

  @override
  String get add => 'Lisa';

  @override
  String get update => 'Uuenda';

  @override
  String get save => 'Salvesta';

  @override
  String get edit => 'Muuda';

  @override
  String get close => 'Sulge';

  @override
  String get clear => 'Tühjenda';

  @override
  String get copyTranscript => 'Kopeeri transkriptsioon';

  @override
  String get copySummary => 'Kopeeri kokkuvõte';

  @override
  String get testPrompt => 'Testi käsku';

  @override
  String get reprocessConversation => 'Töötle vestlust uuesti';

  @override
  String get deleteConversation => 'Kustuta vestlus';

  @override
  String get contentCopied => 'Sisu kopeeritud lõikelauale';

  @override
  String get failedToUpdateStarred => 'Tärni lisamine ebaõnnestus.';

  @override
  String get conversationUrlNotShared => 'Vestluse URL-i ei saanud jagada.';

  @override
  String get errorProcessingConversation =>
      'Viga vestluse töötlemisel. Palun proovige hiljem uuesti.';

  @override
  String get noInternetConnection => 'Internetiühendus puudub';

  @override
  String get unableToDeleteConversation => 'Vestlust ei õnnestunud kustutada';

  @override
  String get somethingWentWrong =>
      'Midagi läks valesti! Palun proovige hiljem uuesti.';

  @override
  String get copyErrorMessage => 'Kopeeri veateade';

  @override
  String get errorCopied => 'Veateade kopeeritud lõikelauale';

  @override
  String get remaining => 'Jäänud';

  @override
  String get loading => 'Laadimine...';

  @override
  String get loadingDuration => 'Kestuse laadimine...';

  @override
  String secondsCount(int count) {
    return '$count sekundit';
  }

  @override
  String get people => 'Inimesed';

  @override
  String get addNewPerson => 'Lisa uus isik';

  @override
  String get editPerson => 'Muuda isikut';

  @override
  String get createPersonHint =>
      'Looge uus isik ja õpetage Omi-le ära tundma ka tema kõnet!';

  @override
  String get speechProfile => 'Kõneprofiil';

  @override
  String sampleNumber(int number) {
    return 'Näidis $number';
  }

  @override
  String get settings => 'Seaded';

  @override
  String get language => 'Keel';

  @override
  String get selectLanguage => 'Vali keel';

  @override
  String get deleting => 'Kustutamine...';

  @override
  String get pleaseCompleteAuthentication =>
      'Palun lõpetage autentimine oma brauseris. Kui olete valmis, naasake rakendusse.';

  @override
  String get failedToStartAuthentication =>
      'Autentimise alustamine ebaõnnestus';

  @override
  String get importStarted =>
      'Import algas! Saate teate, kui see on lõpetatud.';

  @override
  String get failedToStartImport =>
      'Impordi alustamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get couldNotAccessFile => 'Valitud failile ei pääsenud ligi';

  @override
  String get askOmi => 'Küsi Omilt';

  @override
  String get done => 'Valmis';

  @override
  String get disconnected => 'Ühendus puudub';

  @override
  String get searching => 'Otsimine...';

  @override
  String get connectDevice => 'Ühenda seade';

  @override
  String get monthlyLimitReached => 'Olete jõudnud oma kuulimiidini.';

  @override
  String get checkUsage => 'Kontrolli kasutust';

  @override
  String get syncingRecordings => 'Salvestiste sünkroonimine';

  @override
  String get recordingsToSync => 'Sünkroonimist vajavad salvestised';

  @override
  String get allCaughtUp => 'Kõik on sünkroonitud';

  @override
  String get sync => 'Sünkrooni';

  @override
  String get pendantUpToDate => 'Ripats on ajakohane';

  @override
  String get allRecordingsSynced => 'Kõik salvestised on sünkroonitud';

  @override
  String get syncingInProgress => 'Sünkroonimine käib';

  @override
  String get readyToSync => 'Valmis sünkroonimiseks';

  @override
  String get tapSyncToStart => 'Alustamiseks vajutage Sünkrooni';

  @override
  String get pendantNotConnected =>
      'Ripats pole ühendatud. Sünkroonimiseks ühendage see.';

  @override
  String get everythingSynced => 'Kõik on juba sünkroonitud.';

  @override
  String get recordingsNotSynced =>
      'Teil on salvestisi, mis pole veel sünkroonitud.';

  @override
  String get syncingBackground =>
      'Jätkame teie salvestiste sünkroonimist taustal.';

  @override
  String get noConversationsYet => 'Vestlusi pole veel';

  @override
  String get noStarredConversations => 'Tärniga vestlusi pole';

  @override
  String get starConversationHint =>
      'Vestluse tärniga märkimiseks avage see ja puudutage päises tärni ikooni.';

  @override
  String get searchConversations => 'Otsi vestluseid...';

  @override
  String selectedCount(int count, Object s) {
    return '$count valitud';
  }

  @override
  String get merge => 'Ühenda';

  @override
  String get mergeConversations => 'Ühenda vestlused';

  @override
  String mergeConversationsMessage(int count) {
    return 'See ühendab $count vestlust üheks. Kogu sisu ühendatakse ja luuakse uuesti.';
  }

  @override
  String get mergingInBackground =>
      'Ühendamine käib taustal. See võib võtta hetke aega.';

  @override
  String get failedToStartMerge => 'Ühendamise alustamine ebaõnnestus';

  @override
  String get askAnything => 'Küsi mida tahes';

  @override
  String get noMessagesYet =>
      'Sõnumeid pole veel!\nMiks te ei alusta vestlust?';

  @override
  String get deletingMessages => 'Teie sõnumite kustutamine Omi mälust...';

  @override
  String get messageCopied => '✨ Sõnum kopeeritud lõikelauale';

  @override
  String get cannotReportOwnMessage => 'Te ei saa oma sõnumitest teatada.';

  @override
  String get reportMessage => 'Teata sõnumist';

  @override
  String get reportMessageConfirm =>
      'Kas olete kindel, et soovite sellest sõnumist teatada?';

  @override
  String get messageReported => 'Sõnumist teatati edukalt.';

  @override
  String get thankYouFeedback => 'Täname tagasiside eest!';

  @override
  String get clearChat => 'Kustuta vestlus';

  @override
  String get clearChatConfirm =>
      'Kas olete kindel, et soovite vestluse tühjendada? Seda toimingut ei saa tagasi võtta.';

  @override
  String get maxFilesLimit => 'Korraga saate üles laadida ainult 4 faili';

  @override
  String get chatWithOmi => 'Vestlus Omi-ga';

  @override
  String get apps => 'Rakendused';

  @override
  String get noAppsFound => 'Rakendusi ei leitud';

  @override
  String get tryAdjustingSearch => 'Proovige otsingu või filtrite muutmist';

  @override
  String get createYourOwnApp => 'Loo oma rakendus';

  @override
  String get buildAndShareApp => 'Looge ja jagage oma kohandatud rakendust';

  @override
  String get searchApps => 'Otsi rakendusi...';

  @override
  String get myApps => 'Minu rakendused';

  @override
  String get installedApps => 'Paigaldatud rakendused';

  @override
  String get unableToFetchApps =>
      'Rakenduste laadimine ebaõnnestus :(\n\nPalun kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String get aboutOmi => 'Omi kohta';

  @override
  String get privacyPolicy => 'Privaatsuspoliitikaga';

  @override
  String get visitWebsite => 'Külasta veebisaiti';

  @override
  String get helpOrInquiries => 'Abi või päringud?';

  @override
  String get joinCommunity => 'Liitu kogukonnaga!';

  @override
  String get membersAndCounting => '8000+ liiget ja arv kasvab.';

  @override
  String get deleteAccountTitle => 'Kustuta konto';

  @override
  String get deleteAccountConfirm =>
      'Kas olete kindel, et soovite oma konto kustutada?';

  @override
  String get cannotBeUndone => 'Seda ei saa tagasi võtta.';

  @override
  String get allDataErased =>
      'Kõik teie mälestused ja vestlused kustutatakse jäädavalt.';

  @override
  String get appsDisconnected =>
      'Teie rakendused ja integratsioonid katkestatakse viivitamatult.';

  @override
  String get exportBeforeDelete =>
      'Saate oma andmed enne konto kustutamist eksportida, kuid pärast kustutamist ei saa neid taastada.';

  @override
  String get deleteAccountCheckbox =>
      'Mõistan, et minu konto kustutamine on püsiv ja kõik andmed, sealhulgas mälestused ja vestlused, lähevad kaotsi ega ole taastatavad.';

  @override
  String get areYouSure => 'Kas olete kindel?';

  @override
  String get deleteAccountFinal =>
      'See toiming on pöördumatu ja kustutab jäädavalt teie konto ja kõik sellega seotud andmed. Kas olete kindel, et soovite jätkata?';

  @override
  String get deleteNow => 'Kustuta kohe';

  @override
  String get goBack => 'Mine tagasi';

  @override
  String get checkBoxToConfirm =>
      'Märkige ruut, et kinnitada, et mõistate, et teie konto kustutamine on püsiv ja pöördumatu.';

  @override
  String get profile => 'Profiil';

  @override
  String get name => 'Nimi';

  @override
  String get email => 'E-post';

  @override
  String get customVocabulary => 'Kohandatud Sõnavara';

  @override
  String get identifyingOthers => 'Teiste Tuvastamine';

  @override
  String get paymentMethods => 'Makseviisid';

  @override
  String get conversationDisplay => 'Vestluste Kuvamine';

  @override
  String get dataPrivacy => 'Andmete Privaatsus';

  @override
  String get userId => 'Kasutaja ID';

  @override
  String get notSet => 'Määramata';

  @override
  String get userIdCopied => 'Kasutaja ID kopeeritud lõikelauale';

  @override
  String get systemDefault => 'Süsteemi vaikimisi';

  @override
  String get planAndUsage => 'Plaan ja kasutus';

  @override
  String get offlineSync => 'Võrguühenduseta sünkroonimine';

  @override
  String get deviceSettings => 'Seadme seaded';

  @override
  String get integrations => 'Integratsioonid';

  @override
  String get feedbackBug => 'Tagasiside / viga';

  @override
  String get helpCenter => 'Abikeskus';

  @override
  String get developerSettings => 'Arendaja seaded';

  @override
  String get getOmiForMac => 'Hangi Omi Mac-ile';

  @override
  String get referralProgram => 'Viiteprogramm';

  @override
  String get signOut => 'Logi Välja';

  @override
  String get appAndDeviceCopied => 'Rakenduse ja seadme üksikasjad kopeeritud';

  @override
  String get wrapped2025 => 'Kokkuvõte 2025';

  @override
  String get yourPrivacyYourControl => 'Teie privaatsus, teie kontroll';

  @override
  String get privacyIntro =>
      'Omi-s oleme pühendunud teie privaatsuse kaitsmisele. See leht võimaldab teil kontrollida, kuidas teie andmeid säilitatakse ja kasutatakse.';

  @override
  String get learnMore => 'Loe lähemalt...';

  @override
  String get dataProtectionLevel => 'Andmekaitse tase';

  @override
  String get dataProtectionDesc =>
      'Teie andmed on vaikimisi kaitstud tugeva krüpteerimisega. Vaadake allpool oma seadeid ja tulevasi privaatsusvalikuid.';

  @override
  String get appAccess => 'Rakenduse juurdepääs';

  @override
  String get appAccessDesc =>
      'Järgmised rakendused pääsevad juurde teie andmetele. Puudutage rakendust selle õiguste haldamiseks.';

  @override
  String get noAppsExternalAccess =>
      'Ühelgi paigaldatud rakendusel pole välise juurdepääsu teie andmetele.';

  @override
  String get deviceName => 'Seadme nimi';

  @override
  String get deviceId => 'Seadme ID';

  @override
  String get firmware => 'Püsivara';

  @override
  String get sdCardSync => 'SD-kaardi sünkroonimine';

  @override
  String get hardwareRevision => 'Riistvara versioon';

  @override
  String get modelNumber => 'Mudeli number';

  @override
  String get manufacturer => 'Tootja';

  @override
  String get doubleTap => 'Topeltpuudutus';

  @override
  String get ledBrightness => 'LED heledus';

  @override
  String get micGain => 'Mikrofoni võimendus';

  @override
  String get disconnect => 'Katkesta ühendus';

  @override
  String get forgetDevice => 'Unusta seade';

  @override
  String get chargingIssues => 'Laadimisprobleemid';

  @override
  String get disconnectDevice => 'Katkesta seadme ühendus';

  @override
  String get unpairDevice => 'Tühista seadme sidumine';

  @override
  String get unpairAndForget => 'Tühista sidumine ja unusta seade';

  @override
  String get deviceDisconnectedMessage => 'Teie Omi on ühendus katkestatud 😔';

  @override
  String get deviceUnpairedMessage =>
      'Seadme sidumine tühistatud. Minge Seaded > Bluetooth ja unustage seade sidumise tühistamise lõpetamiseks.';

  @override
  String get unpairDialogTitle => 'Tühista seadme sidumine';

  @override
  String get unpairDialogMessage =>
      'See tühistab seadme sidumise, et seda saaks ühendada teise telefoniga. Protsessi lõpetamiseks peate minema Seaded > Bluetooth ja unustama seadme.';

  @override
  String get deviceNotConnected => 'Seade pole ühendatud';

  @override
  String get connectDeviceMessage =>
      'Ühendage oma Omi seade, et pääseda juurde\nseadme seadetele ja kohandamisele';

  @override
  String get deviceInfoSection => 'Seadme teave';

  @override
  String get customizationSection => 'Kohandamine';

  @override
  String get hardwareSection => 'Riistvara';

  @override
  String get v2Undetected => 'V2 tuvastamata';

  @override
  String get v2UndetectedMessage =>
      'Näeme, et teil on kas V1 seade või teie seade pole ühendatud. SD-kaardi funktsioon on saadaval ainult V2 seadmetele.';

  @override
  String get endConversation => 'Lõpeta vestlus';

  @override
  String get pauseResume => 'Peata/jätka';

  @override
  String get starConversation => 'Märgi vestlus tärniga';

  @override
  String get doubleTapAction => 'Topeltpuudutuse tegevus';

  @override
  String get endAndProcess => 'Lõpeta ja töötle vestlus';

  @override
  String get pauseResumeRecording => 'Peata/jätka salvestamine';

  @override
  String get starOngoing => 'Märgi käimasolev vestlus tärniga';

  @override
  String get off => 'Väljas';

  @override
  String get max => 'Maks';

  @override
  String get mute => 'Vaigista';

  @override
  String get quiet => 'Vaikne';

  @override
  String get normal => 'Tavaline';

  @override
  String get high => 'Kõrge';

  @override
  String get micGainDescMuted => 'Mikrofon on vaigistatud';

  @override
  String get micGainDescLow => 'Väga vaikne - valjude keskkondade jaoks';

  @override
  String get micGainDescModerate => 'Vaikne - mõõduka müra jaoks';

  @override
  String get micGainDescNeutral => 'Neutraalne - tasakaalustatud salvestamine';

  @override
  String get micGainDescSlightlyBoosted => 'Veidi võimendatud - tavakasutus';

  @override
  String get micGainDescBoosted => 'Võimendatud - vaiksetele keskkondadele';

  @override
  String get micGainDescHigh => 'Kõrge - kaugete või vaikste häälte jaoks';

  @override
  String get micGainDescVeryHigh => 'Väga kõrge - väga vaiksetele allikatele';

  @override
  String get micGainDescMax => 'Maksimum - kasutage ettevaatusega';

  @override
  String get developerSettingsTitle => 'Arendaja seaded';

  @override
  String get saving => 'Salvestamine...';

  @override
  String get personaConfig => 'Seadistage oma AI isiksus';

  @override
  String get beta => 'BEETA';

  @override
  String get transcription => 'Transkriptsioon';

  @override
  String get transcriptionConfig => 'Seadistage STT pakkuja';

  @override
  String get conversationTimeout => 'Vestluse aegumine';

  @override
  String get conversationTimeoutConfig =>
      'Määrake, millal vestlused automaatselt lõpevad';

  @override
  String get importData => 'Impordi andmed';

  @override
  String get importDataConfig => 'Importige andmed teistest allikatest';

  @override
  String get debugDiagnostics => 'Silumis- ja diagnostika';

  @override
  String get endpointUrl => 'Lõpp-punkti URL';

  @override
  String get noApiKeys => 'API võtmeid pole veel';

  @override
  String get createKeyToStart => 'Alustamiseks looge võti';

  @override
  String get createKey => 'Loo Võti';

  @override
  String get docs => 'Dokumentatsioon';

  @override
  String get yourOmiInsights => 'Teie Omi ülevaated';

  @override
  String get today => 'Täna';

  @override
  String get thisMonth => 'See kuu';

  @override
  String get thisYear => 'See aasta';

  @override
  String get allTime => 'Kogu aeg';

  @override
  String get noActivityYet => 'Tegevust pole veel';

  @override
  String get startConversationToSeeInsights =>
      'Alustage Omi-ga vestlust,\net näha siinkohal oma kasutuse ülevaadet.';

  @override
  String get listening => 'Kuulamine';

  @override
  String get listeningSubtitle => 'Aeg, mil Omi on aktiivselt kuulanud.';

  @override
  String get understanding => 'Mõistmine';

  @override
  String get understandingSubtitle => 'Teie vestlustest mõistetud sõnad.';

  @override
  String get providing => 'Pakkumine';

  @override
  String get providingSubtitle =>
      'Tegevuspunktid ja märkmed automaatselt salvestatud.';

  @override
  String get remembering => 'Meelde jätmine';

  @override
  String get rememberingSubtitle =>
      'Teie jaoks meeles peetud faktid ja üksikasjad.';

  @override
  String get unlimitedPlan => 'Piiramatu plaan';

  @override
  String get managePlan => 'Halda plaani';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Teie plaan tühistatakse $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Teie plaan uueneb $date.';
  }

  @override
  String get basicPlan => 'Tasuta plaan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used/$limit min kasutatud';
  }

  @override
  String get upgrade => 'Uuenda';

  @override
  String get upgradeToUnlimited => 'Uuenda piiramatuks';

  @override
  String basicPlanDesc(int limit) {
    return 'Teie plaan sisaldab $limit tasuta minutit kuus. Uuendage piiramatuks.';
  }

  @override
  String get shareStatsMessage =>
      'Jagan oma Omi statistikat! (omi.me - teie alati sees AI assistent)';

  @override
  String get sharePeriodToday => 'Täna on omi:';

  @override
  String get sharePeriodMonth => 'Sel kuul on omi:';

  @override
  String get sharePeriodYear => 'Sel aastal on omi:';

  @override
  String get sharePeriodAllTime => 'Seni on omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Kuulanud $minutes minutit';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Mõistnud $words sõna';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Pakkunud $count ülevaadet';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Meelde jätnud $count mälestust';
  }

  @override
  String get debugLogs => 'Silumislogid';

  @override
  String get debugLogsAutoDelete => 'Kustutatakse automaatselt 3 päeva pärast.';

  @override
  String get debugLogsDesc => 'Aitab diagnoosida probleeme';

  @override
  String get noLogFilesFound => 'Logifaile ei leitud.';

  @override
  String get omiDebugLog => 'Omi silumislogi';

  @override
  String get logShared => 'Logi jagatud';

  @override
  String get selectLogFile => 'Vali logifail';

  @override
  String get shareLogs => 'Jaga logisid';

  @override
  String get debugLogCleared => 'Silumislogi tühjendatud';

  @override
  String get exportStarted => 'Eksport algas. See võib võtta mõne sekundi...';

  @override
  String get exportAllData => 'Ekspordi kõik andmed';

  @override
  String get exportDataDesc => 'Ekspordi vestlused JSON-failina';

  @override
  String get exportedConversations => 'Omi-st eksporditud vestlused';

  @override
  String get exportShared => 'Eksport jagatud';

  @override
  String get deleteKnowledgeGraphTitle => 'Kustuta teadmiste graaf?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'See kustutab kõik tuletatud teadmiste graafi andmed (sõlmed ja ühendused). Teie algsed mälestused jäävad turvaliseks. Graaf taastatakse aja jooksul või järgmise päringu korral.';

  @override
  String get knowledgeGraphDeleted => 'Teadmiste graaf kustutatud';

  @override
  String deleteGraphFailed(String error) {
    return 'Graafi kustutamine ebaõnnestus: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Kustuta teadmiste graaf';

  @override
  String get deleteKnowledgeGraphDesc => 'Tühjenda kõik sõlmed ja ühendused';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP server';

  @override
  String get mcpServerDesc => 'Ühendage AI assistendid oma andmetega';

  @override
  String get serverUrl => 'Serveri URL';

  @override
  String get urlCopied => 'URL kopeeritud';

  @override
  String get apiKeyAuth => 'API võtme autentimine';

  @override
  String get header => 'Päis';

  @override
  String get authorizationBearer => 'Authorization: Bearer <võti>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Kliendi ID';

  @override
  String get clientSecret => 'Kliendi saladus';

  @override
  String get useMcpApiKey => 'Kasutage oma MCP API võtit';

  @override
  String get webhooks => 'Veebikongid';

  @override
  String get conversationEvents => 'Vestlussündmused';

  @override
  String get newConversationCreated => 'Uus vestlus loodud';

  @override
  String get realtimeTranscript => 'Reaalajas transkriptsioon';

  @override
  String get transcriptReceived => 'Transkriptsioon vastu võetud';

  @override
  String get audioBytes => 'Helibaite';

  @override
  String get audioDataReceived => 'Heliandmed vastu võetud';

  @override
  String get intervalSeconds => 'Intervall (sekundid)';

  @override
  String get daySummary => 'Päeva kokkuvõte';

  @override
  String get summaryGenerated => 'Kokkuvõte loodud';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Lisa claude_desktop_config.json-i';

  @override
  String get copyConfig => 'Kopeeri konfiguratsioon';

  @override
  String get configCopied => 'Konfiguratsioon kopeeritud lõikelauale';

  @override
  String get listeningMins => 'Kuulamine (min)';

  @override
  String get understandingWords => 'Mõistmine (sõnad)';

  @override
  String get insights => 'Ülevaated';

  @override
  String get memories => 'Mälestused';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used/$limit min kasutatud sel kuul';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used/$limit sõna kasutatud sel kuul';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used/$limit ülevaadet saadud sel kuul';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used/$limit mälestust loodud sel kuul';
  }

  @override
  String get visibility => 'Nähtavus';

  @override
  String get visibilitySubtitle =>
      'Kontrollige, millised vestlused teie loendis kuvatakse';

  @override
  String get showShortConversations => 'Kuva lühikesed vestlused';

  @override
  String get showShortConversationsDesc => 'Kuva künnisest lühemaid vestlusi';

  @override
  String get showDiscardedConversations => 'Kuva hüljatud vestlused';

  @override
  String get showDiscardedConversationsDesc =>
      'Kaasa hüljatuna märgitud vestlused';

  @override
  String get shortConversationThreshold => 'Lühikese vestluse künnis';

  @override
  String get shortConversationThresholdSubtitle =>
      'Sellest lühemad vestlused peidetakse, kui pole ülalpool lubatud';

  @override
  String get durationThreshold => 'Kestuse künnis';

  @override
  String get durationThresholdDesc => 'Peida sellest lühemad vestlused';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Kohandatud sõnavara';

  @override
  String get addWords => 'Lisa sõnad';

  @override
  String get addWordsDesc => 'Nimed, terminid või ebatavalised sõnad';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Tulekul';

  @override
  String get integrationsFooter =>
      'Ühendage oma rakendused, et vestluses andmeid ja mõõdikuid vaadata.';

  @override
  String get completeAuthInBrowser =>
      'Palun lõpetage autentimine oma brauseris. Kui olete valmis, naasake rakendusse.';

  @override
  String failedToStartAuth(String appName) {
    return '$appName autentimise alustamine ebaõnnestus';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Katkesta ühendus rakendusega $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Kas olete kindel, et soovite ühenduse rakendusega $appName katkestada? Saate igal ajal uuesti ühendada.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Ühendus rakendusega $appName katkestatud';
  }

  @override
  String get failedToDisconnect => 'Ühenduse katkestamine ebaõnnestus';

  @override
  String connectTo(String appName) {
    return 'Ühenda rakendusega $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Peate andma Omi-le loa juurdepääsuks teie $appName andmetele. See avab teie brauseri autentimiseks.';
  }

  @override
  String get continueAction => 'Jätka';

  @override
  String get languageTitle => 'Keel';

  @override
  String get primaryLanguage => 'Põhikeel';

  @override
  String get automaticTranslation => 'Automaatne tõlge';

  @override
  String get detectLanguages => 'Tuvasta 10+ keelt';

  @override
  String get authorizeSavingRecordings => 'Luba salvestiste salvestamine';

  @override
  String get thanksForAuthorizing => 'Täname loa andmise eest!';

  @override
  String get needYourPermission => 'Vajame teie luba';

  @override
  String get alreadyGavePermission =>
      'Olete juba andnud meile loa teie salvestiste salvestamiseks. Siin on meeldetuletus, miks me seda vajame:';

  @override
  String get wouldLikePermission =>
      'Sooviksime teie luba teie helisalvestiste salvestamiseks. Siin on põhjus:';

  @override
  String get improveSpeechProfile => 'Parandage oma kõneprofiili';

  @override
  String get improveSpeechProfileDesc =>
      'Kasutame salvestisi, et edasi treenida ja parandada teie isiklikku kõneprofiili.';

  @override
  String get trainFamilyProfiles => 'Treenige profiile sõprade ja pere jaoks';

  @override
  String get trainFamilyProfilesDesc =>
      'Teie salvestised aitavad meil ära tunda ja luua profiile teie sõprade ja pere jaoks.';

  @override
  String get enhanceTranscriptAccuracy => 'Parandage transkriptsiooni täpsust';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Kui meie mudel paraneb, saame pakkuda teie salvestiste jaoks paremaid transkriptsioone.';

  @override
  String get legalNotice =>
      'Õiguslik teade: Häälsalvestuste salvestamise ja salvestamise seaduslikkus võib sõltuvalt teie asukohast ja selle funktsiooni kasutamisest erineda. Teie kohustus on tagada kohalike seaduste ja määruste järgimine.';

  @override
  String get alreadyAuthorized => 'Juba autoriseeritud';

  @override
  String get authorize => 'Autoriseeri';

  @override
  String get revokeAuthorization => 'Tühista autoriseerimine';

  @override
  String get authorizationSuccessful => 'Autoriseerimine õnnestus!';

  @override
  String get failedToAuthorize =>
      'Autoriseerimine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get authorizationRevoked => 'Autoriseerimine tühistatud.';

  @override
  String get recordingsDeleted => 'Salvestised kustutatud.';

  @override
  String get failedToRevoke =>
      'Autoriseerimise tühistamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get permissionRevokedTitle => 'Luba tühistatud';

  @override
  String get permissionRevokedMessage =>
      'Kas soovite, et me eemaldaksime ka kõik teie olemasolevad salvestised?';

  @override
  String get yes => 'Jah';

  @override
  String get editName => 'Muuda nime';

  @override
  String get howShouldOmiCallYou => 'Kuidas peaks Omi teid kutsuma?';

  @override
  String get enterYourName => 'Sisestage oma nimi';

  @override
  String get nameCannotBeEmpty => 'Nimi ei saa olla tühi';

  @override
  String get nameUpdatedSuccessfully => 'Nimi edukalt uuendatud!';

  @override
  String get calendarSettings => 'Kalendri seaded';

  @override
  String get calendarProviders => 'Kalendri pakkujad';

  @override
  String get macOsCalendar => 'macOS kalender';

  @override
  String get connectMacOsCalendar => 'Ühendage oma kohalik macOS kalender';

  @override
  String get googleCalendar => 'Google Kalender';

  @override
  String get syncGoogleAccount => 'Sünkroonige oma Google\'i kontoga';

  @override
  String get showMeetingsMenuBar => 'Kuva tulevased koosolekud menüüribal';

  @override
  String get showMeetingsMenuBarDesc =>
      'Kuva oma järgmine koosolek ja aeg selle alguseni macOS-i menüüribal';

  @override
  String get showEventsNoParticipants => 'Kuva ilma osalejateta sündmusi';

  @override
  String get showEventsNoParticipantsDesc =>
      'Kui lubatud, näitab Coming Up sündmusi ilma osalejate või videolingita.';

  @override
  String get yourMeetings => 'Teie koosolekud';

  @override
  String get refresh => 'Värskenda';

  @override
  String get noUpcomingMeetings => 'Tulevaid kohtumisi pole';

  @override
  String get checkingNextDays => 'Kontrolli järgmist 30 päeva';

  @override
  String get tomorrow => 'Homme';

  @override
  String get googleCalendarComingSoon =>
      'Google Calendar integratsioon tuleb varsti!';

  @override
  String connectedAsUser(String userId) {
    return 'Ühendatud kasutajana: $userId';
  }

  @override
  String get defaultWorkspace => 'Vaikimisi tööala';

  @override
  String get tasksCreatedInWorkspace => 'Ülesanded luuakse sellesse tööalasse';

  @override
  String get defaultProjectOptional => 'Vaikimisi projekt (valikuline)';

  @override
  String get leaveUnselectedTasks =>
      'Jätke valimata, et luua ülesanded ilma projektita';

  @override
  String get noProjectsInWorkspace => 'Selles tööalas projekte ei leitud';

  @override
  String get conversationTimeoutDesc =>
      'Valige, kui kaua vaikuses oodatakse enne vestluse automaatset lõpetamist:';

  @override
  String get timeout2Minutes => '2 minutit';

  @override
  String get timeout2MinutesDesc =>
      'Lõpeta vestlus pärast 2-minutilist vaikust';

  @override
  String get timeout5Minutes => '5 minutit';

  @override
  String get timeout5MinutesDesc =>
      'Lõpeta vestlus pärast 5-minutilist vaikust';

  @override
  String get timeout10Minutes => '10 minutit';

  @override
  String get timeout10MinutesDesc =>
      'Lõpeta vestlus pärast 10-minutilist vaikust';

  @override
  String get timeout30Minutes => '30 minutit';

  @override
  String get timeout30MinutesDesc =>
      'Lõpeta vestlus pärast 30-minutilist vaikust';

  @override
  String get timeout4Hours => '4 tundi';

  @override
  String get timeout4HoursDesc => 'Lõpeta vestlus pärast 4-tunnist vaikust';

  @override
  String get conversationEndAfterHours =>
      'Vestlused lõpevad nüüd pärast 4-tunnist vaikust';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Vestlused lõpevad nüüd pärast $minutes minuti pikkust vaikust';
  }

  @override
  String get tellUsPrimaryLanguage => 'Öelge meile oma põhikeel';

  @override
  String get languageForTranscription =>
      'Määrake oma keel täpsemate transkriptsioonide ja isikupärastatud kogemuse saamiseks.';

  @override
  String get singleLanguageModeInfo =>
      'Ühe keele režiim on lubatud. Tõlge on keelatud suurema täpsuse jaoks.';

  @override
  String get searchLanguageHint => 'Otsige keelt nime või koodi järgi';

  @override
  String get noLanguagesFound => 'Keeli ei leitud';

  @override
  String get skip => 'Jäta vahele';

  @override
  String languageSetTo(String language) {
    return 'Keeleks määratud $language';
  }

  @override
  String get failedToSetLanguage => 'Keele määramine ebaõnnestus';

  @override
  String appSettings(String appName) {
    return '$appName seaded';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Katkesta ühendus rakendusega $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'See eemaldab teie $appName autentimise. Peate uuesti ühendama, et seda uuesti kasutada.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Ühendatud rakendusega $appName';
  }

  @override
  String get account => 'Konto';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Teie tegevuspunktid sünkroonitakse teie $appName kontoga';
  }

  @override
  String get defaultSpace => 'Vaikimisi ruum';

  @override
  String get selectSpaceInWorkspace => 'Valige ruum oma tööalast';

  @override
  String get noSpacesInWorkspace => 'Selles tööalas ruume ei leitud';

  @override
  String get defaultList => 'Vaikimisi loend';

  @override
  String get tasksAddedToList => 'Ülesanded lisatakse sellesse loendisse';

  @override
  String get noListsInSpace => 'Selles ruumis loendeid ei leitud';

  @override
  String failedToLoadRepos(String error) {
    return 'Hoidlate laadimine ebaõnnestus: $error';
  }

  @override
  String get defaultRepoSaved => 'Vaikimisi hoidla salvestatud';

  @override
  String get failedToSaveDefaultRepo =>
      'Vaikimisi hoidla salvestamine ebaõnnestus';

  @override
  String get defaultRepository => 'Vaikimisi hoidla';

  @override
  String get selectDefaultRepoDesc =>
      'Valige vaikimisi hoidla probleemide loomiseks. Probleemide loomisel saate siiski määrata teise hoidla.';

  @override
  String get noReposFound => 'Hoidlaid ei leitud';

  @override
  String get private => 'Privaatne';

  @override
  String updatedDate(String date) {
    return 'Uuendatud $date';
  }

  @override
  String get yesterday => 'Eile';

  @override
  String daysAgo(int count) {
    return '$count päeva tagasi';
  }

  @override
  String get oneWeekAgo => '1 nädal tagasi';

  @override
  String weeksAgo(int count) {
    return '$count nädalat tagasi';
  }

  @override
  String get oneMonthAgo => '1 kuu tagasi';

  @override
  String monthsAgo(int count) {
    return '$count kuud tagasi';
  }

  @override
  String get issuesCreatedInRepo =>
      'Probleemid luuakse teie vaikimisi hoidlasse';

  @override
  String get taskIntegrations => 'Ülesannete integratsioonid';

  @override
  String get configureSettings => 'Seadista seaded';

  @override
  String get completeAuthBrowser =>
      'Palun lõpetage autentimine oma brauseris. Kui olete valmis, naasake rakendusse.';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName autentimise alustamine ebaõnnestus';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Ühenda rakendusega $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Peate andma Omi-le loa ülesannete loomiseks teie $appName kontol. See avab teie brauseri autentimiseks.';
  }

  @override
  String get continueButton => 'Jätka';

  @override
  String appIntegration(String appName) {
    return '$appName integratsioon';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName integratsioon tuleb varsti! Töötame selle nimel, et tuua teile rohkem ülesannete haldamise valikuid.';
  }

  @override
  String get gotIt => 'Selge';

  @override
  String get tasksExportedOneApp =>
      'Ülesandeid saab eksportida korraga ühte rakendusse.';

  @override
  String get completeYourUpgrade => 'Viige oma uuendamine lõpule';

  @override
  String get importConfiguration => 'Impordi konfiguratsioon';

  @override
  String get exportConfiguration => 'Ekspordi konfiguratsioon';

  @override
  String get bringYourOwn => 'Tooge oma oma';

  @override
  String get payYourSttProvider =>
      'Kasutage Omi-d vabalt. Maksite ainult oma STT pakkujale otse.';

  @override
  String get freeMinutesMonth =>
      '1200 tasuta minutit kuus kaasa arvatud. Piiramatu koos ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host on nõutud';

  @override
  String get validPortRequired => 'Kehtiv port on nõutud';

  @override
  String get validWebsocketUrlRequired =>
      'Kehtiv WebSocket URL on nõutud (wss://)';

  @override
  String get apiUrlRequired => 'API URL on nõutud';

  @override
  String get apiKeyRequired => 'API võti on nõutud';

  @override
  String get invalidJsonConfig => 'Vigane JSON-konfiguratsioon';

  @override
  String errorSaving(String error) {
    return 'Salvestamise viga: $error';
  }

  @override
  String get configCopiedToClipboard =>
      'Konfiguratsioon kopeeritud lõikelauale';

  @override
  String get pasteJsonConfig => 'Kleepige oma JSON-konfiguratsioon allpool:';

  @override
  String get addApiKeyAfterImport =>
      'Peate pärast importimist lisama oma API võtme';

  @override
  String get paste => 'Kleebi';

  @override
  String get import => 'Impordi';

  @override
  String get invalidProviderInConfig => 'Vigane pakkuja konfiguratsioonis';

  @override
  String importedConfig(String providerName) {
    return 'Imporditud $providerName konfiguratsioon';
  }

  @override
  String invalidJson(String error) {
    return 'Vigane JSON: $error';
  }

  @override
  String get provider => 'Pakkuja';

  @override
  String get live => 'Otse';

  @override
  String get onDevice => 'Seadmel';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Sisestage oma STT HTTP otspunkt';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket =>
      'Sisestage oma reaalajas STT WebSocket otspunkt';

  @override
  String get apiKey => 'API võti';

  @override
  String get enterApiKey => 'Sisestage oma API võti';

  @override
  String get storedLocallyNeverShared =>
      'Salvestatud lokaalselt, ei jagata kunagi';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Täpsem';

  @override
  String get configuration => 'Konfiguratsioon';

  @override
  String get requestConfiguration => 'Päringu konfiguratsioon';

  @override
  String get responseSchema => 'Vastuse skeem';

  @override
  String get modified => 'Muudetud';

  @override
  String get resetRequestConfig => 'Lähtesta päringu konfiguratsioon vaikimisi';

  @override
  String get logs => 'Logid';

  @override
  String get logsCopied => 'Logid kopeeritud';

  @override
  String get noLogsYet =>
      'Logisid pole veel. Alustage salvestamist, et näha kohandatud STT tegevust.';

  @override
  String deviceUsesCodec(String device, String reason) {
    return '$device kasutab $reason. Kasutatakse Omi.';
  }

  @override
  String get omiTranscription => 'Omi transkriptsioon';

  @override
  String get bestInClassTranscription =>
      'Parim oma klassis transkriptsioon nullseadistusega';

  @override
  String get instantSpeakerLabels => 'Kohesed kõneleja sildid';

  @override
  String get languageTranslation => '100+ keele tõlge';

  @override
  String get optimizedForConversation => 'Optimeeritud vestluseks';

  @override
  String get autoLanguageDetection => 'Automaatne keele tuvastamine';

  @override
  String get highAccuracy => 'Kõrge täpsus';

  @override
  String get privacyFirst => 'Privaatsus esmalt';

  @override
  String get saveChanges => 'Salvesta muudatused';

  @override
  String get resetToDefault => 'Lähtesta vaikeväärtusele';

  @override
  String get viewTemplate => 'Vaata malli';

  @override
  String get trySomethingLike => 'Proovige midagi sellist nagu...';

  @override
  String get tryIt => 'Proovi seda';

  @override
  String get creatingPlan => 'Plaani loomine';

  @override
  String get developingLogic => 'Loogika arendamine';

  @override
  String get designingApp => 'Rakenduse kujundamine';

  @override
  String get generatingIconStep => 'Ikooni genereerimine';

  @override
  String get finalTouches => 'Viimased lihvid';

  @override
  String get processing => 'Töötlemine...';

  @override
  String get features => 'Funktsioonid';

  @override
  String get creatingYourApp => 'Teie rakenduse loomine...';

  @override
  String get generatingIcon => 'Ikooni genereerimine...';

  @override
  String get whatShouldWeMake => 'Mida me peaksime tegema?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Kirjeldus';

  @override
  String get publicLabel => 'Avalik';

  @override
  String get privateLabel => 'Privaatne';

  @override
  String get free => 'Tasuta';

  @override
  String get perMonth => '/ kuu';

  @override
  String get tailoredConversationSummaries =>
      'Kohandatud vestluste kokkuvõtted';

  @override
  String get customChatbotPersonality => 'Kohandatud vestlusroboti isiksus';

  @override
  String get makePublic => 'Tee avalikuks';

  @override
  String get anyoneCanDiscover => 'Igaüks saab teie rakendust avastada';

  @override
  String get onlyYouCanUse => 'Ainult teie saate seda rakendust kasutada';

  @override
  String get paidApp => 'Tasuline rakendus';

  @override
  String get usersPayToUse =>
      'Kasutajad maksavad teie rakenduse kasutamise eest';

  @override
  String get freeForEveryone => 'Tasuta kõigile';

  @override
  String get perMonthLabel => '/ kuu';

  @override
  String get creating => 'Loomine...';

  @override
  String get createApp => 'Loo rakendus';

  @override
  String get searchingForDevices => 'Seadmete otsimine...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'SEADET',
      one: 'SEADE',
    );
    return '$count $_temp0 LEITUD LÄHEDALT';
  }

  @override
  String get pairingSuccessful => 'ÜHENDAMINE ÕNNESTUS';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Viga Apple Watch\'iga ühendamisel: $error';
  }

  @override
  String get dontShowAgain => 'Ära näita uuesti';

  @override
  String get iUnderstand => 'Ma mõistan';

  @override
  String get enableBluetooth => 'Luba Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi vajab Bluetoothi, et ühenduda teie kantava seadmega. Palun lubage Bluetooth ja proovige uuesti.';

  @override
  String get contactSupport => 'Võta ühendust toega?';

  @override
  String get connectLater => 'Ühenda hiljem';

  @override
  String get grantPermissions => 'Anna load';

  @override
  String get backgroundActivity => 'Taustegevus';

  @override
  String get backgroundActivityDesc =>
      'Lubage Omil töötada taustal parema stabiilsuse tagamiseks';

  @override
  String get locationAccess => 'Asukoha juurdepääs';

  @override
  String get locationAccessDesc =>
      'Lubage tausta asukoht täieliku kogemuse saamiseks';

  @override
  String get notifications => 'Teavitused';

  @override
  String get notificationsDesc => 'Lubage teavitused, et püsida kursis';

  @override
  String get locationServiceDisabled => 'Asukohateenused keelatud';

  @override
  String get locationServiceDisabledDesc =>
      'Asukohateenused on keelatud. Palun minge Seaded > Privaatsus ja turvalisus > Asukohateenused ja lubage see';

  @override
  String get backgroundLocationDenied => 'Tausta asukoha juurdepääs keelatud';

  @override
  String get backgroundLocationDeniedDesc =>
      'Palun minge seadme seadetesse ja määrake asukoha luba väärtusele \"Luba alati\"';

  @override
  String get lovingOmi => 'Meeldib Omi?';

  @override
  String get leaveReviewIos =>
      'Aidake meil jõuda rohkemate inimesteni, jättes arvustuse App Store\'i. Teie tagasiside on meile ülimalt oluline!';

  @override
  String get leaveReviewAndroid =>
      'Aidake meil jõuda rohkemate inimesteni, jättes arvustuse Google Play poodi. Teie tagasiside on meile ülimalt oluline!';

  @override
  String get rateOnAppStore => 'Hinda App Store\'is';

  @override
  String get rateOnGooglePlay => 'Hinda Google Play\'s';

  @override
  String get maybeLater => 'Võib-olla hiljem';

  @override
  String get speechProfileIntro =>
      'Omi peab õppima teie eesmärke ja häält. Saate seda hiljem muuta.';

  @override
  String get getStarted => 'Alusta';

  @override
  String get allDone => 'Kõik tehtud!';

  @override
  String get keepGoing => 'Jätkake, teil läheb suurepäraselt';

  @override
  String get skipThisQuestion => 'Jäta see küsimus vahele';

  @override
  String get skipForNow => 'Jäta praegu vahele';

  @override
  String get connectionError => 'Ühenduse viga';

  @override
  String get connectionErrorDesc =>
      'Serveriga ühendamine ebaõnnestus. Palun kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Vigane salvestis tuvastatud';

  @override
  String get multipleSpeakersDesc =>
      'Tundub, et salvestises on mitu kõnelejat. Palun veenduge, et olete vaikses kohas ja proovige uuesti.';

  @override
  String get tooShortDesc =>
      'Kõnet ei tuvastatud piisavalt. Palun rääkige rohkem ja proovige uuesti.';

  @override
  String get invalidRecordingDesc =>
      'Palun veenduge, et räägite vähemalt 5 sekundit ja mitte rohkem kui 90.';

  @override
  String get areYouThere => 'Kas olete seal?';

  @override
  String get noSpeechDesc =>
      'Me ei suutnud kõnet tuvastada. Palun veenduge, et räägite vähemalt 10 sekundit ja mitte rohkem kui 3 minutit.';

  @override
  String get connectionLost => 'Ühendus kadus';

  @override
  String get connectionLostDesc =>
      'Ühendus katkestati. Palun kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String get tryAgain => 'Proovi uuesti';

  @override
  String get connectOmiOmiGlass => 'Ühenda Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Jätka ilma seadmeta';

  @override
  String get permissionsRequired => 'Load on nõutud';

  @override
  String get permissionsRequiredDesc =>
      'See rakendus vajab nõuetekohaseks toimimiseks Bluetoothi ja asukoha lube. Palun lubage need seadetes.';

  @override
  String get openSettings => 'Ava seaded';

  @override
  String get wantDifferentName => 'Soovite kasutada muud nime?';

  @override
  String get whatsYourName => 'Mis on teie nimi?';

  @override
  String get speakTranscribeSummarize => 'Räägi. Transkribeeri. Võta kokku.';

  @override
  String get signInWithApple => 'Logi sisse Apple\'iga';

  @override
  String get signInWithGoogle => 'Logi sisse Google\'iga';

  @override
  String get byContinuingAgree => 'Jätkates nõustute meie ';

  @override
  String get termsOfUse => 'Kasutustingimustega';

  @override
  String get omiYourAiCompanion => 'Omi – teie AI kaaslane';

  @override
  String get captureEveryMoment =>
      'Jäädvustage iga hetk. Saage AI-põhiseid\nkokkuvõtteid. Ärge tehke enam kunagi märkmeid.';

  @override
  String get appleWatchSetup => 'Apple Watch\'i seadistamine';

  @override
  String get permissionRequestedExclaim => 'Luba taotletud!';

  @override
  String get microphonePermission => 'Mikrofoni luba';

  @override
  String get permissionGrantedNow =>
      'Luba antud! Nüüd:\n\nAvage Omi rakendus oma kellal ja puudutage allpool \"Jätka\"';

  @override
  String get needMicrophonePermission =>
      'Vajame mikrofoni luba.\n\n1. Puudutage \"Anna luba\"\n2. Lubage oma iPhone\'is\n3. Kella rakendus sulgub\n4. Avage uuesti ja puudutage \"Jätka\"';

  @override
  String get grantPermissionButton => 'Anna luba';

  @override
  String get needHelp => 'Vajate abi?';

  @override
  String get troubleshootingSteps =>
      'Tõrkeotsing:\n\n1. Veenduge, et Omi on teie kellale installitud\n2. Avage Omi rakendus oma kellal\n3. Otsige loa hüpikakent\n4. Puudutage \"Luba\", kui küsitakse\n5. Rakendus teie kellal sulgub - avage see uuesti\n6. Tulge tagasi ja puudutage \"Jätka\" oma iPhone\'is';

  @override
  String get recordingStartedSuccessfully => 'Salvestamine algas edukalt!';

  @override
  String get permissionNotGrantedYet =>
      'Luba pole veel antud. Palun veenduge, et lubate mikrofoni juurdepääsu ja avasid rakenduse oma kellal uuesti.';

  @override
  String errorRequestingPermission(String error) {
    return 'Viga loa taotlemisel: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Viga salvestamise alustamisel: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Valige oma põhikeel';

  @override
  String get languageBenefits =>
      'Määrake oma keel täpsemate transkriptsioonide ja isikupärastatud kogemuse saamiseks';

  @override
  String get whatsYourPrimaryLanguage => 'Mis on teie põhikeel?';

  @override
  String get selectYourLanguage => 'Valige oma keel';

  @override
  String get personalGrowthJourney =>
      'Teie isikliku arengu teekond AI-ga, mis kuulab iga teie sõna.';

  @override
  String get actionItemsTitle => 'Tegevused';

  @override
  String get actionItemsDescription =>
      'Puudutage muutmiseks • Vajutage pikalt valimiseks • Libistage toimingute jaoks';

  @override
  String get tabToDo => 'Teha';

  @override
  String get tabDone => 'Tehtud';

  @override
  String get tabOld => 'Vanad';

  @override
  String get emptyTodoMessage => '🎉 Kõik tehtud!\nOotel tegevuspunkte pole';

  @override
  String get emptyDoneMessage => 'Lõpetatud punkte pole veel';

  @override
  String get emptyOldMessage => '✅ Vanu ülesandeid pole';

  @override
  String get noItems => 'Punkte pole';

  @override
  String get actionItemMarkedIncomplete =>
      'Tegevuspunkt märgitud mittelõpetatuks';

  @override
  String get actionItemCompleted => 'Tegevuspunkt lõpetatud';

  @override
  String get deleteActionItemTitle => 'Kustuta toiming';

  @override
  String get deleteActionItemMessage =>
      'Kas olete kindel, et soovite selle toimingu kustutada?';

  @override
  String get deleteSelectedItemsTitle => 'Kustuta valitud punktid';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Kas olete kindel, et soovite kustutada $count valitud tegevuspunkt$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Tegevuspunkt \"$description\" kustutatud';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count tegevuspunkt$s kustutatud';
  }

  @override
  String get failedToDeleteItem => 'Tegevuspunkti kustutamine ebaõnnestus';

  @override
  String get failedToDeleteItems => 'Punktide kustutamine ebaõnnestus';

  @override
  String get failedToDeleteSomeItems => 'Mõne punkti kustutamine ebaõnnestus';

  @override
  String get welcomeActionItemsTitle => 'Valmis tegevuspunktide jaoks';

  @override
  String get welcomeActionItemsDescription =>
      'Teie AI eraldab automaatselt ülesanded ja tegevused teie vestlustest. Need ilmuvad siia, kui need luuakse.';

  @override
  String get autoExtractionFeature => 'Automaatselt vestlustest eraldatud';

  @override
  String get editSwipeFeature =>
      'Puudutage muutmiseks, libistage lõpetamiseks või kustutamiseks';

  @override
  String itemsSelected(int count) {
    return '$count valitud';
  }

  @override
  String get selectAll => 'Vali kõik';

  @override
  String get deleteSelected => 'Kustuta valitud';

  @override
  String get searchMemories => 'Otsi mälestusi...';

  @override
  String get memoryDeleted => 'Mälestus kustutatud.';

  @override
  String get undo => 'Tühista';

  @override
  String get noMemoriesYet => '🧠 Mälestusi pole veel';

  @override
  String get noAutoMemories => 'Automaatselt eraldatud mälestusi pole veel';

  @override
  String get noManualMemories => 'Käsitsi lisatud mälestusi pole veel';

  @override
  String get noMemoriesInCategories => 'Neis kategooriates pole mälestusi';

  @override
  String get noMemoriesFound => '🔍 Mälestusi ei leitud';

  @override
  String get addFirstMemory => 'Lisa oma esimene mälestus';

  @override
  String get clearMemoryTitle => 'Tühjenda Omi mälu';

  @override
  String get clearMemoryMessage =>
      'Kas olete kindel, et soovite Omi mälu tühjendada? Seda tegevust ei saa tagasi võtta.';

  @override
  String get clearMemoryButton => 'Tühjenda mälu';

  @override
  String get memoryClearedSuccess => 'Omi mälu teie kohta on tühjendatud';

  @override
  String get noMemoriesToDelete => 'Pole mälestusi kustutamiseks';

  @override
  String get createMemoryTooltip => 'Loo uus mälestus';

  @override
  String get createActionItemTooltip => 'Loo uus tegevuspunkt';

  @override
  String get memoryManagement => 'Mäluhaldus';

  @override
  String get filterMemories => 'Filtreeri mälestusi';

  @override
  String totalMemoriesCount(int count) {
    return 'Teil on kokku $count mälestust';
  }

  @override
  String get publicMemories => 'Avalikud mälestused';

  @override
  String get privateMemories => 'Privaatsed mälestused';

  @override
  String get makeAllPrivate => 'Muuda kõik mälestused privaatseks';

  @override
  String get makeAllPublic => 'Muuda kõik mälestused avalikuks';

  @override
  String get deleteAllMemories => 'Kustuta kõik mälestused';

  @override
  String get allMemoriesPrivateResult => 'Kõik mälestused on nüüd privaatsed';

  @override
  String get allMemoriesPublicResult => 'Kõik mälestused on nüüd avalikud';

  @override
  String get newMemory => '✨ Uus mälestus';

  @override
  String get editMemory => '✏️ Muuda mälestust';

  @override
  String get memoryContentHint => 'Mulle meeldib süüa jäätist...';

  @override
  String get failedToSaveMemory =>
      'Salvestamine ebaõnnestus. Palun kontrollige oma ühendust.';

  @override
  String get saveMemory => 'Salvesta mälestus';

  @override
  String get retry => 'Proovi uuesti';

  @override
  String get createActionItem => 'Loo ülesanne';

  @override
  String get editActionItem => 'Muuda ülesannet';

  @override
  String get actionItemDescriptionHint => 'Mida on vaja teha?';

  @override
  String get actionItemDescriptionEmpty =>
      'Tegevuspunkti kirjeldus ei saa olla tühi.';

  @override
  String get actionItemUpdated => 'Tegevuspunkt uuendatud';

  @override
  String get failedToUpdateActionItem => 'Ülesande uuendamine ebaõnnestus';

  @override
  String get actionItemCreated => 'Tegevuspunkt loodud';

  @override
  String get failedToCreateActionItem => 'Ülesande loomine ebaõnnestus';

  @override
  String get dueDate => 'Tähtaeg';

  @override
  String get time => 'Aeg';

  @override
  String get addDueDate => 'Lisa tähtaeg';

  @override
  String get pressDoneToSave => 'Vajutage valmis salvestamiseks';

  @override
  String get pressDoneToCreate => 'Vajutage valmis loomiseks';

  @override
  String get filterAll => 'Kõik';

  @override
  String get filterSystem => 'Teie kohta';

  @override
  String get filterInteresting => 'Ülevaated';

  @override
  String get filterManual => 'Käsitsi';

  @override
  String get completed => 'Lõpetatud';

  @override
  String get markComplete => 'Märgi lõpetatuks';

  @override
  String get actionItemDeleted => 'Toiming kustutatud';

  @override
  String get failedToDeleteActionItem => 'Ülesande kustutamine ebaõnnestus';

  @override
  String get deleteActionItemConfirmTitle => 'Kustuta tegevuspunkt';

  @override
  String get deleteActionItemConfirmMessage =>
      'Kas olete kindel, et soovite selle tegevuspunkti kustutada?';

  @override
  String get appLanguage => 'Rakenduse keel';

  @override
  String get appInterfaceSectionTitle => 'RAKENDUSE LIIDES';

  @override
  String get speechTranscriptionSectionTitle => 'KÕNE JA TRANSKRIPTSIOON';

  @override
  String get languageSettingsHelperText =>
      'Rakenduse keel muudab menüüsid ja nuppe. Kõne keel mõjutab, kuidas teie salvestisi transkribeeritakse.';

  @override
  String get translationNotice => 'Tõlke teatis';

  @override
  String get translationNoticeMessage =>
      'Omi tõlgib vestlused teie põhikeelde. Värskendage seda igal ajal jaotises Seaded → Profiilid.';

  @override
  String get pleaseCheckInternetConnection =>
      'Palun kontrollige oma internetiühendust ja proovige uuesti';

  @override
  String get pleaseSelectReason => 'Palun valige põhjus';

  @override
  String get tellUsMoreWhatWentWrong =>
      'Rääkige meile rohkem sellest, mis valesti läks...';

  @override
  String get selectText => 'Vali tekst';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimaalselt $count eesmärki lubatud';
  }

  @override
  String get conversationCannotBeMerged =>
      'Seda vestlust ei saa ühendada (lukustatud või juba ühendamisel)';

  @override
  String get pleaseEnterFolderName => 'Palun sisestage kausta nimi';

  @override
  String get failedToCreateFolder => 'Kausta loomine ebaõnnestus';

  @override
  String get failedToUpdateFolder => 'Kausta värskendamine ebaõnnestus';

  @override
  String get folderName => 'Kausta nimi';

  @override
  String get descriptionOptional => 'Description (optional)';

  @override
  String get failedToDeleteFolder => 'Kausta kustutamine ebaõnnestus';

  @override
  String get editFolder => 'Muuda kausta';

  @override
  String get deleteFolder => 'Kustuta kaust';

  @override
  String get transcriptCopiedToClipboard =>
      'Transkriptsioon kopeeritud lõikelauale';

  @override
  String get summaryCopiedToClipboard => 'Kokkuvõte kopeeritud lõikelauale';

  @override
  String get conversationUrlCouldNotBeShared =>
      'Vestluse URL-i ei saanud jagada.';

  @override
  String get urlCopiedToClipboard => 'URL kopeeritud lõikelauale';

  @override
  String get exportTranscript => 'Ekspordi transkriptsioon';

  @override
  String get exportSummary => 'Ekspordi kokkuvõte';

  @override
  String get exportButton => 'Ekspordi';

  @override
  String get actionItemsCopiedToClipboard =>
      'Tegevusüksused kopeeritud lõikelauale';

  @override
  String get summarize => 'Kokkuvõte';

  @override
  String get generateSummary => 'Genereeri kokkuvõte';

  @override
  String get conversationNotFoundOrDeleted =>
      'Vestlust ei leitud või see on kustutatud';

  @override
  String get deleteMemory => 'Kustuta mälestus';

  @override
  String get thisActionCannotBeUndone => 'Seda toimingut ei saa tagasi võtta.';

  @override
  String memoriesCount(int count) {
    return '$count mälu';
  }

  @override
  String get noMemoriesInCategory => 'Selles kategoorias pole veel mälestusi';

  @override
  String get addYourFirstMemory => 'Lisa oma esimene mälestus';

  @override
  String get firmwareDisconnectUsb => 'Eemaldage USB';

  @override
  String get firmwareUsbWarning =>
      'USB-ühendus värskenduste ajal võib teie seadet kahjustada.';

  @override
  String get firmwareBatteryAbove15 => 'Aku üle 15%';

  @override
  String get firmwareEnsureBattery => 'Veenduge, et teie seadmel on 15% akut.';

  @override
  String get firmwareStableConnection => 'Stabiilne ühendus';

  @override
  String get firmwareConnectWifi => 'Ühendage WiFi-ga või mobiilsidevõrguga.';

  @override
  String failedToStartUpdate(String error) {
    return 'Värskenduse alustamine ebaõnnestus: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Enne värskendamist veenduge:';

  @override
  String get confirmed => 'Kinnitatud!';

  @override
  String get release => 'Vabastage';

  @override
  String get slideToUpdate => 'Värskendamiseks libistage';

  @override
  String copiedToClipboard(String title) {
    return '$title kopeeritud lõikelauale';
  }

  @override
  String get batteryLevel => 'Aku tase';

  @override
  String get productUpdate => 'Toote värskendus';

  @override
  String get offline => 'Ühenduseta';

  @override
  String get available => 'Saadaval';

  @override
  String get unpairDeviceDialogTitle => 'Tühista seadme sidumine';

  @override
  String get unpairDeviceDialogMessage =>
      'See tühistab seadme sidumise, et seda saaks ühendada teise telefoniga. Peate minema Seaded > Bluetooth ja unustama seadme protsessi lõpetamiseks.';

  @override
  String get unpair => 'Tühista sidumine';

  @override
  String get unpairAndForgetDevice => 'Tühista sidumine ja unusta seade';

  @override
  String get unknownDevice => 'Tundmatu';

  @override
  String get unknown => 'Tundmatu';

  @override
  String get productName => 'Toote nimi';

  @override
  String get serialNumber => 'Seerianumber';

  @override
  String get connected => 'Ühendatud';

  @override
  String get privacyPolicyTitle => 'Privaatsuspoliitika';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label kopeeritud';
  }

  @override
  String get noApiKeysYet =>
      'API võtmeid pole veel. Looge üks oma rakendusega integreerimiseks.';

  @override
  String get createKeyToGetStarted => 'Loo võti alustamiseks';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Seadista oma AI-isik';

  @override
  String get configureSttProvider => 'Seadista STT pakkuja';

  @override
  String get setWhenConversationsAutoEnd =>
      'Määra, millal vestlused automaatselt lõpevad';

  @override
  String get importDataFromOtherSources =>
      'Impordi andmeid teistest allikatest';

  @override
  String get debugAndDiagnostics => 'Silumine ja diagnostika';

  @override
  String get autoDeletesAfter3Days => 'Automaatne kustutamine 3 päeva pärast';

  @override
  String get helpsDiagnoseIssues => 'Aitab probleeme diagnoosida';

  @override
  String get exportStartedMessage =>
      'Eksport alustatud. See võib võtta mõne sekundi...';

  @override
  String get exportConversationsToJson => 'Ekspordi vestlused JSON-faili';

  @override
  String get knowledgeGraphDeletedSuccess =>
      'Teadmiste graaf edukalt kustutatud';

  @override
  String failedToDeleteGraph(String error) {
    return 'Graafi kustutamine ebaõnnestus: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Kustuta kõik sõlmed ja ühendused';

  @override
  String get addToClaudeDesktopConfig =>
      'Lisa faili claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Ühenda AI-assistendid oma andmetega';

  @override
  String get useYourMcpApiKey => 'Kasuta oma MCP API võtit';

  @override
  String get realTimeTranscript => 'Reaalajas transkriptsioon';

  @override
  String get experimental => 'Eksperimentaalne';

  @override
  String get transcriptionDiagnostics => 'Transkriptsiooni diagnostika';

  @override
  String get detailedDiagnosticMessages => 'Üksikasjalikud diagnostikasõnumid';

  @override
  String get autoCreateSpeakers => 'Loo kõnelejad automaatselt';

  @override
  String get autoCreateWhenNameDetected => 'Loo automaatselt nime tuvastamisel';

  @override
  String get followUpQuestions => 'Järgmised küsimused';

  @override
  String get suggestQuestionsAfterConversations =>
      'Soovita küsimusi pärast vestlusi';

  @override
  String get goalTracker => 'Eesmärkide jälgija';

  @override
  String get trackPersonalGoalsOnHomepage =>
      'Jälgi oma isiklikke eesmärke avalehel';

  @override
  String get dailyReflection => 'Igapäevane refleksioon';

  @override
  String get get9PmReminderToReflect =>
      'Saa kell 21 meeldetuletus oma päeva üle mõtisklemiseks';

  @override
  String get actionItemDescriptionCannotBeEmpty =>
      'Toimingu kirjeldus ei tohi olla tühi';

  @override
  String get saved => 'Salvestatud';

  @override
  String get overdue => 'Tähtaja ületanud';

  @override
  String get failedToUpdateDueDate => 'Tähtaja värskendamine ebaõnnestus';

  @override
  String get markIncomplete => 'Märgi lõpetamatuks';

  @override
  String get editDueDate => 'Muuda tähtaega';

  @override
  String get setDueDate => 'Määra tähtaeg';

  @override
  String get clearDueDate => 'Kustuta tähtaeg';

  @override
  String get failedToClearDueDate => 'Tähtaja kustutamine ebaõnnestus';

  @override
  String get mondayAbbr => 'E';

  @override
  String get tuesdayAbbr => 'T';

  @override
  String get wednesdayAbbr => 'K';

  @override
  String get thursdayAbbr => 'N';

  @override
  String get fridayAbbr => 'R';

  @override
  String get saturdayAbbr => 'L';

  @override
  String get sundayAbbr => 'P';

  @override
  String get howDoesItWork => 'Kuidas see töötab?';

  @override
  String get sdCardSyncDescription =>
      'SD-kaardi sünkroonimine impordib teie mälestused SD-kaardilt rakendusse';

  @override
  String get checksForAudioFiles => 'Kontrollib helifaile SD-kaardil';

  @override
  String get omiSyncsAudioFiles =>
      'Omi sünkroonib seejärel helifailid serveriga';

  @override
  String get serverProcessesAudio =>
      'Server töötleb helifaile ja loob mälestusi';

  @override
  String get youreAllSet => 'Oled valmis!';

  @override
  String get welcomeToOmiDescription =>
      'Tere tulemast Omi juurde! Teie AI kaaslane on valmis aitama vestluste, ülesannete ja muuga.';

  @override
  String get startUsingOmi => 'Alusta Omi kasutamist';

  @override
  String get back => 'Tagasi';

  @override
  String get keyboardShortcuts => 'Kiirklahvid';

  @override
  String get toggleControlBar => 'Lülita juhtpaneeli';

  @override
  String get pressKeys => 'Vajutage klahve...';

  @override
  String get cmdRequired => '⌘ on nõutud';

  @override
  String get invalidKey => 'Kehtetu klahv';

  @override
  String get space => 'Tühik';

  @override
  String get search => 'Otsi';

  @override
  String get searchPlaceholder => 'Otsi...';

  @override
  String get untitledConversation => 'Pealkirjata vestlus';

  @override
  String countRemaining(String count) {
    return '$count järel';
  }

  @override
  String get addGoal => 'Lisa eesmärk';

  @override
  String get editGoal => 'Muuda eesmärki';

  @override
  String get icon => 'Ikoon';

  @override
  String get goalTitle => 'Eesmärgi pealkiri';

  @override
  String get current => 'Praegune';

  @override
  String get target => 'Sihtmärk';

  @override
  String get saveGoal => 'Salvesta';

  @override
  String get goals => 'Eesmärgid';

  @override
  String get tapToAddGoal => 'Puuduta eesmärgi lisamiseks';

  @override
  String welcomeBack(String name) {
    return 'Tere tulemast tagasi, $name';
  }

  @override
  String get yourConversations => 'Teie vestlused';

  @override
  String get reviewAndManageConversations =>
      'Vaadake üle ja hallake oma salvestatud vestlusi';

  @override
  String get startCapturingConversations =>
      'Alustage vestluste salvestamist oma Omi seadmega, et neid siin näha.';

  @override
  String get useMobileAppToCapture =>
      'Kasutage heeli salvestamiseks mobiilirakendust';

  @override
  String get conversationsProcessedAutomatically =>
      'Vestlusi töödeldakse automaatselt';

  @override
  String get getInsightsInstantly => 'Saate kohe ülevaateid ja kokkuvõtteid';

  @override
  String get showAll => 'Kuva kõik →';

  @override
  String get noTasksForToday =>
      'Täna pole ülesandeid.\\nKüsi Omi käest rohkem ülesandeid või loo need käsitsi.';

  @override
  String get dailyScore => 'PÄEVA SKOOR';

  @override
  String get dailyScoreDescription =>
      'Skoor, mis aitab teil paremini\nkeskenduda täitmisele.';

  @override
  String get searchResults => 'Otsingutulemused';

  @override
  String get actionItems => 'Tegevused';

  @override
  String get tasksToday => 'Täna';

  @override
  String get tasksTomorrow => 'Homme';

  @override
  String get tasksNoDeadline => 'Tähtajata';

  @override
  String get tasksLater => 'Hiljem';

  @override
  String get loadingTasks => 'Ülesannete laadimine...';

  @override
  String get tasks => 'Ülesanded';

  @override
  String get swipeTasksToIndent =>
      'Libista ülesandeid taande jaoks, lohista kategooriate vahel';

  @override
  String get create => 'Loo';

  @override
  String get noTasksYet => 'Ülesandeid pole veel';

  @override
  String get tasksFromConversationsWillAppear =>
      'Teie vestlustest pärit ülesanded ilmuvad siia.\nKlõpsake ülesande käsitsi lisamiseks nuppu Loo.';

  @override
  String get monthJan => 'Jaan';

  @override
  String get monthFeb => 'Veebr';

  @override
  String get monthMar => 'Märts';

  @override
  String get monthApr => 'apr';

  @override
  String get monthMay => 'Mai';

  @override
  String get monthJun => 'Juuni';

  @override
  String get monthJul => 'Juuli';

  @override
  String get monthAug => 'aug';

  @override
  String get monthSep => 'Sept';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'nov';

  @override
  String get monthDec => 'Dets';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Ülesanne edukalt uuendatud';

  @override
  String get actionItemCreatedSuccessfully => 'Ülesanne edukalt loodud';

  @override
  String get actionItemDeletedSuccessfully => 'Ülesanne edukalt kustutatud';

  @override
  String get deleteActionItem => 'Kustuta ülesanne';

  @override
  String get deleteActionItemConfirmation =>
      'Kas olete kindel, et soovite selle ülesande kustutada? Seda tegevust ei saa tagasi võtta.';

  @override
  String get enterActionItemDescription => 'Sisesta ülesande kirjeldus...';

  @override
  String get markAsCompleted => 'Märgi lõpetatuks';

  @override
  String get setDueDateAndTime => 'Määra tähtaeg ja kellaaeg';

  @override
  String get reloadingApps => 'Rakenduste uuesti laadimine...';

  @override
  String get loadingApps => 'Rakenduste laadimine...';

  @override
  String get browseInstallCreateApps => 'Sirvi, installi ja loo rakendusi';

  @override
  String get all => 'Kõik';

  @override
  String get open => 'Ava';

  @override
  String get install => 'Paigalda';

  @override
  String get noAppsAvailable => 'Rakendusi pole saadaval';

  @override
  String get unableToLoadApps => 'Rakenduste laadimine ebaõnnestus';

  @override
  String get tryAdjustingSearchTermsOrFilters =>
      'Proovi otsingumõisteid või filtreid kohandada';

  @override
  String get checkBackLaterForNewApps => 'Kontrolli hiljem uusi rakendusi';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain =>
      'Palun kontrolli oma internetiühendust ja proovi uuesti';

  @override
  String get createNewApp => 'Loo uus rakendus';

  @override
  String get buildSubmitCustomOmiApp =>
      'Ehita ja esita oma kohandatud Omi rakendus';

  @override
  String get submittingYourApp => 'Sinu rakenduse esitamine...';

  @override
  String get preparingFormForYou => 'Vormi ettevalmistamine sinu jaoks...';

  @override
  String get appDetails => 'Rakenduse üksikasjad';

  @override
  String get paymentDetails => 'Makse üksikasjad';

  @override
  String get previewAndScreenshots => 'Eelvaade ja ekraanipildid';

  @override
  String get appCapabilities => 'Rakenduse võimalused';

  @override
  String get aiPrompts => 'AI vihjed';

  @override
  String get chatPrompt => 'Vestluse viip';

  @override
  String get chatPromptPlaceholder =>
      'Sa oled suurepärane rakendus, sinu töö on vastata kasutajate küsimustele ja panna nad end hästi tundma...';

  @override
  String get conversationPrompt => 'Vestluse viip';

  @override
  String get conversationPromptPlaceholder =>
      'Sa oled suurepärane rakendus, sulle antakse vestluse transkriptsioon ja kokkuvõte...';

  @override
  String get notificationScopes => 'Teavituste ulatused';

  @override
  String get appPrivacyAndTerms => 'Rakenduse privaatsus ja tingimused';

  @override
  String get makeMyAppPublic => 'Tee minu rakendus avalikuks';

  @override
  String get submitAppTermsAgreement =>
      'Selle rakenduse esitamisega nõustun Omi AI teenuse tingimuste ja privaatsuspoliitikaga';

  @override
  String get submitApp => 'Esita rakendus';

  @override
  String get needHelpGettingStarted => 'Vajad abi alustamiseks?';

  @override
  String get clickHereForAppBuildingGuides =>
      'Klõpsa siia rakenduste loomise juhiste ja dokumentatsiooni jaoks';

  @override
  String get submitAppQuestion => 'Esita rakendus?';

  @override
  String get submitAppPublicDescription =>
      'Sinu rakendust vaadatakse üle ja tehakse avalikuks. Võid seda kohe kasutada, isegi ülevaatuse ajal!';

  @override
  String get submitAppPrivateDescription =>
      'Sinu rakendust vaadatakse üle ja tehakse sulle privaatselt kättesaadavaks. Võid seda kohe kasutada, isegi ülevaatuse ajal!';

  @override
  String get startEarning => 'Alusta teenimist! 💰';

  @override
  String get connectStripeOrPayPal =>
      'Ühenda Stripe või PayPal, et saada rakenduse eest makseid.';

  @override
  String get connectNow => 'Ühenda kohe';

  @override
  String get installsCount => 'Paigaldused';

  @override
  String get uninstallApp => 'Desinstalli rakendus';

  @override
  String get subscribe => 'Telli';

  @override
  String get dataAccessNotice => 'Andmetele juurdepääsu teatis';

  @override
  String get dataAccessWarning =>
      'See rakendus pääseb ligi teie andmetele. Omi AI ei vastuta selle eest, kuidas see rakendus teie andmeid kasutab, muudab või kustutab';

  @override
  String get installApp => 'Installi rakendus';

  @override
  String get betaTesterNotice =>
      'Olete selle rakenduse beeta-testija. See ei ole veel avalik. See muutub avalikuks pärast kinnitamist.';

  @override
  String get appUnderReviewOwner =>
      'Teie rakendus on ülevaatamisel ja nähtav ainult teile. See muutub avalikuks pärast kinnitamist.';

  @override
  String get appRejectedNotice =>
      'Teie rakendus on tagasi lükatud. Palun värskendage rakenduse üksikasju ja esitage see uuesti ülevaatamiseks.';

  @override
  String get setupSteps => 'Seadistamise sammud';

  @override
  String get setupInstructions => 'Seadistusjuhised';

  @override
  String get integrationInstructions => 'Integratsiooni juhised';

  @override
  String get preview => 'Eelvaade';

  @override
  String get aboutTheApp => 'Rakendusest';

  @override
  String get aboutThePersona => 'Persoonast';

  @override
  String get chatPersonality => 'Vestluse isiksus';

  @override
  String get ratingsAndReviews => 'Hinnangud ja arvustused';

  @override
  String get noRatings => 'hinnanguid pole';

  @override
  String ratingsCount(String count) {
    return '$count+ hinnangut';
  }

  @override
  String get errorActivatingApp => 'Viga rakenduse aktiveerimisel';

  @override
  String get integrationSetupRequired =>
      'Kui see on integratsioonirakendus, veenduge, et seadistamine on lõpetatud.';

  @override
  String get installed => 'Paigaldatud';

  @override
  String get appIdLabel => 'Rakenduse ID';

  @override
  String get appNameLabel => 'Rakenduse nimi';

  @override
  String get appNamePlaceholder => 'Minu suurepärane rakendus';

  @override
  String get pleaseEnterAppName => 'Palun sisestage rakenduse nimi';

  @override
  String get categoryLabel => 'Kategooria';

  @override
  String get selectCategory => 'Valige kategooria';

  @override
  String get descriptionLabel => 'Kirjeldus';

  @override
  String get appDescriptionPlaceholder =>
      'Minu suurepärane rakendus on suurepärane rakendus, mis teeb hämmastav asju. See on parim rakendus!';

  @override
  String get pleaseProvideValidDescription => 'Palun esitage kehtiv kirjeldus';

  @override
  String get appPricingLabel => 'Rakenduse hinnakujundus';

  @override
  String get noneSelected => 'Valimata';

  @override
  String get appIdCopiedToClipboard => 'Rakenduse ID kopeeritud lõikelauale';

  @override
  String get appCategoryModalTitle => 'Rakenduse kategooria';

  @override
  String get pricingFree => 'Tasuta';

  @override
  String get pricingPaid => 'Tasuline';

  @override
  String get loadingCapabilities => 'Võimete laadimine...';

  @override
  String get filterInstalled => 'Paigaldatud';

  @override
  String get filterMyApps => 'Minu rakendused';

  @override
  String get clearSelection => 'Tühista valik';

  @override
  String get filterCategory => 'Kategooria';

  @override
  String get rating4PlusStars => '4+ tärni';

  @override
  String get rating3PlusStars => '3+ tärni';

  @override
  String get rating2PlusStars => '2+ tärni';

  @override
  String get rating1PlusStars => '1+ täht';

  @override
  String get filterRating => 'Hinnang';

  @override
  String get filterCapabilities => 'Võimed';

  @override
  String get noNotificationScopesAvailable => 'Teatiste ulatusi pole saadaval';

  @override
  String get popularApps => 'Populaarsed rakendused';

  @override
  String get pleaseProvidePrompt => 'Palun esitage viip';

  @override
  String chatWithAppName(String appName) {
    return 'Vestle rakendusega $appName';
  }

  @override
  String get defaultAiAssistant => 'Vaikimisi AI abiline';

  @override
  String get readyToChat => '✨ Valmis vestluseks!';

  @override
  String get connectionNeeded => '🌐 Vajalik ühendus';

  @override
  String get startConversation => 'Alustage vestlust ja laske maagia alata';

  @override
  String get checkInternetConnection =>
      'Palun kontrollige oma internetiühendust';

  @override
  String get wasThisHelpful => 'Kas see oli kasulik?';

  @override
  String get thankYouForFeedback => 'Täname tagasiside eest!';

  @override
  String get maxFilesUploadError => 'Saate üles laadida ainult 4 faili korraga';

  @override
  String get attachedFiles => '📎 Lisatud failid';

  @override
  String get takePhoto => 'Tee foto';

  @override
  String get captureWithCamera => 'Jäädvusta kaameraga';

  @override
  String get selectImages => 'Vali pildid';

  @override
  String get chooseFromGallery => 'Vali galeriist';

  @override
  String get selectFile => 'Vali fail';

  @override
  String get chooseAnyFileType => 'Vali mis tahes failitüüp';

  @override
  String get cannotReportOwnMessages => 'Te ei saa oma sõnumeid teatada';

  @override
  String get messageReportedSuccessfully => '✅ Sõnum edukalt teatatud';

  @override
  String get confirmReportMessage =>
      'Kas olete kindel, et soovite seda sõnumit teatada?';

  @override
  String get selectChatAssistant => 'Vali vestlusabiline';

  @override
  String get enableMoreApps => 'Luba rohkem rakendusi';

  @override
  String get chatCleared => 'Vestlus kustutatud';

  @override
  String get clearChatTitle => 'Kustuta vestlus?';

  @override
  String get confirmClearChat =>
      'Kas olete kindel, et soovite vestlust kustutada? Seda tegevust ei saa tagasi võtta.';

  @override
  String get copy => 'Kopeeri';

  @override
  String get share => 'Jaga';

  @override
  String get report => 'Teata';

  @override
  String get microphonePermissionRequired =>
      'Helisalvestuse jaoks on vajalik mikrofoni luba.';

  @override
  String get microphonePermissionDenied =>
      'Mikrofoni luba keelatud. Palun andke luba Süsteemieelistused > Privaatsus ja turvalisus > Mikrofon.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Mikrofoni loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get failedToTranscribeAudio => 'Heli transkribeerimine ebaõnnestus';

  @override
  String get transcribing => 'Transkribeerimine...';

  @override
  String get transcriptionFailed => 'Transkribeerimine ebaõnnestus';

  @override
  String get discardedConversation => 'Kustutatud vestlus';

  @override
  String get at => 'kell';

  @override
  String get from => 'alates';

  @override
  String get copied => 'Kopeeritud!';

  @override
  String get copyLink => 'Kopeeri link';

  @override
  String get hideTranscript => 'Peida transkriptsioon';

  @override
  String get viewTranscript => 'Vaata transkriptsiooni';

  @override
  String get conversationDetails => 'Vestluse üksikasjad';

  @override
  String get transcript => 'Transkriptsioon';

  @override
  String segmentsCount(int count) {
    return '$count segmenti';
  }

  @override
  String get noTranscriptAvailable => 'Transkriptsioon pole saadaval';

  @override
  String get noTranscriptMessage => 'Sellel vestlusel pole transkriptsiooni.';

  @override
  String get conversationUrlCouldNotBeGenerated =>
      'Vestluse URL-i ei saanud genereerida.';

  @override
  String get failedToGenerateConversationLink =>
      'Vestluse lingi genereerimine ebaõnnestus';

  @override
  String get failedToGenerateShareLink =>
      'Jagamislingi genereerimine ebaõnnestus';

  @override
  String get reloadingConversations => 'Vestluste ümberlaadimine...';

  @override
  String get user => 'Kasutaja';

  @override
  String get starred => 'Tärniga';

  @override
  String get date => 'Kuupäev';

  @override
  String get noResultsFound => 'Tulemusi ei leitud';

  @override
  String get tryAdjustingSearchTerms => 'Proovige kohandada otsingusõnu';

  @override
  String get starConversationsToFindQuickly =>
      'Märkige vestlused tärniga, et neid siit kiiresti leida';

  @override
  String noConversationsOnDate(String date) {
    return 'Vestlusi pole kuupäeval $date';
  }

  @override
  String get trySelectingDifferentDate => 'Proovige valida teine kuupäev';

  @override
  String get conversations => 'Vestlused';

  @override
  String get chat => 'Vestlus';

  @override
  String get actions => 'Toimingud';

  @override
  String get syncAvailable => 'Sünkroonimine saadaval';

  @override
  String get referAFriend => 'Soovita sõbrale';

  @override
  String get help => 'Abi';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Uuenda Pro-le';

  @override
  String get getOmiDevice => 'Hangi Omi seade';

  @override
  String get wearableAiCompanion => 'Kantav AI kaaslane';

  @override
  String get loadingMemories => 'Mälestuste laadimine...';

  @override
  String get allMemories => 'Kõik mälestused';

  @override
  String get aboutYou => 'Sinu kohta';

  @override
  String get manual => 'Käsitsi';

  @override
  String get loadingYourMemories => 'Teie mälestuste laadimine...';

  @override
  String get createYourFirstMemory => 'Loo alustamiseks oma esimene mälestus';

  @override
  String get tryAdjustingFilter => 'Proovige kohandada otsingut või filtrit';

  @override
  String get whatWouldYouLikeToRemember => 'Mida soovid meeles pidada?';

  @override
  String get category => 'Kategooria';

  @override
  String get public => 'Avalik';

  @override
  String get failedToSaveCheckConnection =>
      'Salvestamine ebaõnnestus. Kontrolli ühendust.';

  @override
  String get createMemory => 'Loo mälestus';

  @override
  String get deleteMemoryConfirmation =>
      'Kas oled kindel, et soovid selle mälestuse kustutada? Seda toimingut ei saa tagasi võtta.';

  @override
  String get makePrivate => 'Tee privaatseks';

  @override
  String get organizeAndControlMemories =>
      'Korraldage ja kontrollige oma mälestusi';

  @override
  String get total => 'Kokku';

  @override
  String get makeAllMemoriesPrivate => 'Tee kõik mälestused privaatseks';

  @override
  String get setAllMemoriesToPrivate => 'Määra kõik mälestused privaatseks';

  @override
  String get makeAllMemoriesPublic => 'Tee kõik mälestused avalikuks';

  @override
  String get setAllMemoriesToPublic => 'Määra kõik mälestused avalikuks';

  @override
  String get permanentlyRemoveAllMemories =>
      'Eemalda püsivalt kõik mälestused Omist';

  @override
  String get allMemoriesAreNowPrivate => 'Kõik mälestused on nüüd privaatsed';

  @override
  String get allMemoriesAreNowPublic => 'Kõik mälestused on nüüd avalikud';

  @override
  String get clearOmisMemory => 'Tühjenda Omi mälu';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Kas oled kindel, et soovid tühjendada Omi mälu? Seda toimingut ei saa tagasi võtta ja see kustutab püsivalt kõik $count mälestust.';
  }

  @override
  String get omisMemoryCleared => 'Omi mälu sinu kohta on tühjendatud';

  @override
  String get welcomeToOmi => 'Tere tulemast Omi';

  @override
  String get continueWithApple => 'Jätka Apple\'iga';

  @override
  String get continueWithGoogle => 'Jätka Google\'iga';

  @override
  String get byContinuingYouAgree => 'Jätkates nõustute meie ';

  @override
  String get termsOfService => 'Teenusetingimustega';

  @override
  String get and => ' ja ';

  @override
  String get dataAndPrivacy => 'Andmed ja privaatsus';

  @override
  String get secureAuthViaAppleId => 'Turvaline autentimine Apple ID kaudu';

  @override
  String get secureAuthViaGoogleAccount =>
      'Turvaline autentimine Google\'i konto kaudu';

  @override
  String get whatWeCollect => 'Mida me kogume';

  @override
  String get dataCollectionMessage =>
      'Jätkates salvestatakse teie vestlused, salvestused ja isikuandmed turvaliselt meie serveritesse, et pakkuda AI-põhiseid ülevaateid ja võimaldada kõiki rakenduse funktsioone.';

  @override
  String get dataProtection => 'Andmekaitse';

  @override
  String get yourDataIsProtected =>
      'Teie andmed on kaitstud ja neid reguleerib meie ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Palun valige oma põhikeel';

  @override
  String get chooseYourLanguage => 'Valige oma keel';

  @override
  String get selectPreferredLanguageForBestExperience =>
      'Valige oma eelistatud keel parima Omi kogemuse jaoks';

  @override
  String get searchLanguages => 'Otsi keeli...';

  @override
  String get selectALanguage => 'Valige keel';

  @override
  String get tryDifferentSearchTerm => 'Proovige teist otsingusõna';

  @override
  String get pleaseEnterYourName => 'Palun sisestage oma nimi';

  @override
  String get nameMustBeAtLeast2Characters =>
      'Nimi peab olema vähemalt 2 tähemärki';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed =>
      'Öelge meile, kuidas te soovite, et teid pöördutaks. See aitab isikupärastada teie Omi kogemust.';

  @override
  String charactersCount(int count) {
    return '$count tähemärki';
  }

  @override
  String get enableFeaturesForBestExperience =>
      'Lubage funktsioonid parima Omi kogemuse jaoks oma seadmes.';

  @override
  String get microphoneAccess => 'Mikrofoni juurdepääs';

  @override
  String get recordAudioConversations => 'Helisalvestiste salvestamine';

  @override
  String get microphoneAccessDescription =>
      'Omi vajab mikrofoni juurdepääsu, et salvestada teie vestlusi ja pakkuda transkriptsioone.';

  @override
  String get screenRecording => 'Ekraanisalvestus';

  @override
  String get captureSystemAudioFromMeetings =>
      'Süsteemiheli jäädvustamine koosolekutest';

  @override
  String get screenRecordingDescription =>
      'Omi vajab ekraanisalvestuse luba, et jäädvustada süsteemiheli teie brauseripõhistest koosolekutest.';

  @override
  String get accessibility => 'Juurdepääsetavus';

  @override
  String get detectBrowserBasedMeetings =>
      'Tuvastage brauseripõhised koosolekud';

  @override
  String get accessibilityDescription =>
      'Omi vajab juurdepääsetavuse luba, et tuvastada, millal te liitute Zoom, Meet või Teams koosolekutega oma brauseris.';

  @override
  String get pleaseWait => 'Palun oodake...';

  @override
  String get joinTheCommunity => 'Liitu kogukonnaga!';

  @override
  String get loadingProfile => 'Profiili laadimine...';

  @override
  String get profileSettings => 'Profiili seaded';

  @override
  String get noEmailSet => 'E-posti ei ole seatud';

  @override
  String get userIdCopiedToClipboard => 'Kasutaja ID kopeeritud';

  @override
  String get yourInformation => 'Teie Andmed';

  @override
  String get setYourName => 'Määra oma nimi';

  @override
  String get changeYourName => 'Muuda oma nime';

  @override
  String get manageYourOmiPersona => 'Halda oma Omi personat';

  @override
  String get voiceAndPeople => 'Hääl ja Inimesed';

  @override
  String get teachOmiYourVoice => 'Õpeta Omi-le oma häält';

  @override
  String get tellOmiWhoSaidIt => 'Ütle Omi-le, kes seda ütles 🗣️';

  @override
  String get payment => 'Makse';

  @override
  String get addOrChangeYourPaymentMethod => 'Lisa või muuda makseviisi';

  @override
  String get preferences => 'Eelistused';

  @override
  String get helpImproveOmiBySharing =>
      'Aita Omi-d parandada, jagades anonümiseeritud analüüsandmeid';

  @override
  String get deleteAccount => 'Kustuta Konto';

  @override
  String get deleteYourAccountAndAllData => 'Kustuta oma konto ja kõik andmed';

  @override
  String get clearLogs => 'Kustuta logid';

  @override
  String get debugLogsCleared => 'Silumislogid kustutatud';

  @override
  String get exportConversations => 'Ekspordi vestlused';

  @override
  String get exportAllConversationsToJson =>
      'Eksportige kõik oma vestlused JSON-faili.';

  @override
  String get conversationsExportStarted =>
      'Vestluste eksport algas. See võib võtta mõned sekundid, palun oodake.';

  @override
  String get mcpDescription =>
      'Omi ühendamiseks teiste rakendustega, et lugeda, otsida ja hallata oma mälestusi ja vestlusi. Alustamiseks looge võti.';

  @override
  String get apiKeys => 'API võtmed';

  @override
  String errorLabel(String error) {
    return 'Viga: $error';
  }

  @override
  String get noApiKeysFound => 'API võtmeid ei leitud. Alustamiseks looge üks.';

  @override
  String get advancedSettings => 'Täpsemad seaded';

  @override
  String get triggersWhenNewConversationCreated =>
      'Käivitatakse, kui luuakse uus vestlus.';

  @override
  String get triggersWhenNewTranscriptReceived =>
      'Käivitatakse, kui saadakse uus transkriptsioon.';

  @override
  String get realtimeAudioBytes => 'Reaalajas helibaidid';

  @override
  String get triggersWhenAudioBytesReceived =>
      'Käivitatakse, kui saadakse helibaidid.';

  @override
  String get everyXSeconds => 'Iga x sekundi järel';

  @override
  String get triggersWhenDaySummaryGenerated =>
      'Käivitatakse, kui luuakse päeva kokkuvõte.';

  @override
  String get tryLatestExperimentalFeatures =>
      'Proovige Omi meeskonna uusimaid eksperimentaalseid funktsioone.';

  @override
  String get transcriptionServiceDiagnosticStatus =>
      'Transkriptsiooni teenuse diagnostika olek';

  @override
  String get enableDetailedDiagnosticMessages =>
      'Luba üksikasjalikud diagnostikateated transkriptsiooni teenusest';

  @override
  String get autoCreateAndTagNewSpeakers =>
      'Loo ja märgista uued kõnelejad automaatselt';

  @override
  String get automaticallyCreateNewPerson =>
      'Loo automaatselt uus inimene, kui transkriptsioonis tuvastatakse nimi.';

  @override
  String get pilotFeatures => 'Pilootfunktsioonid';

  @override
  String get pilotFeaturesDescription =>
      'Need funktsioonid on testid ja toe pakkumist ei garanteerita.';

  @override
  String get suggestFollowUpQuestion => 'Soovita jätkuküsimust';

  @override
  String get saveSettings => 'Salvesta Seaded';

  @override
  String get syncingDeveloperSettings => 'Arendaja seadete sünkroonimine...';

  @override
  String get summary => 'Kokkuvõte';

  @override
  String get auto => 'Automaatne';

  @override
  String get noSummaryForApp =>
      'Selle rakenduse jaoks pole kokkuvõtet saadaval. Proovi teist rakendust paremate tulemuste saamiseks.';

  @override
  String get tryAnotherApp => 'Proovi teist rakendust';

  @override
  String generatedBy(String appName) {
    return 'Loonud $appName';
  }

  @override
  String get overview => 'Ülevaade';

  @override
  String get otherAppResults => 'Teiste rakenduste tulemused';

  @override
  String get unknownApp => 'Tundmatu rakendus';

  @override
  String get noSummaryAvailable => 'Kokkuvõte pole saadaval';

  @override
  String get conversationNoSummaryYet =>
      'Sellel vestlusel pole veel kokkuvõtet.';

  @override
  String get chooseSummarizationApp => 'Vali kokkuvõtte rakendus';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName määratud vaikerakenduseks kokkuvõtte jaoks';
  }

  @override
  String get letOmiChooseAutomatically =>
      'Lase Omil automaatselt parim rakendus valida';

  @override
  String get deleteConversationConfirmation =>
      'Kas olete kindel, et soovite selle vestluse kustutada? Seda toimingut ei saa tagasi võtta.';

  @override
  String get conversationDeleted => 'Vestlus kustutatud';

  @override
  String get generatingLink => 'Lingi genereerimine...';

  @override
  String get editConversation => 'Muuda vestlust';

  @override
  String get conversationLinkCopiedToClipboard =>
      'Vestluse link kopeeritud lõikelauale';

  @override
  String get conversationTranscriptCopiedToClipboard =>
      'Vestluse transkriptsioon kopeeritud lõikelauale';

  @override
  String get editConversationDialogTitle => 'Muuda vestlust';

  @override
  String get changeTheConversationTitle => 'Muuda vestluse pealkirja';

  @override
  String get conversationTitle => 'Vestluse pealkiri';

  @override
  String get enterConversationTitle => 'Sisesta vestluse pealkiri...';

  @override
  String get conversationTitleUpdatedSuccessfully =>
      'Vestluse pealkiri edukalt uuendatud';

  @override
  String get failedToUpdateConversationTitle =>
      'Vestluse pealkirja uuendamine ebaõnnestus';

  @override
  String get errorUpdatingConversationTitle =>
      'Viga vestluse pealkirja uuendamisel';

  @override
  String get settingUp => 'Seadistamine...';

  @override
  String get startYourFirstRecording => 'Alustage oma esimest salvestust';

  @override
  String get preparingSystemAudioCapture =>
      'Süsteemiheli salvestamise ettevalmistamine';

  @override
  String get clickTheButtonToCaptureAudio =>
      'Klõpsake nupul, et salvestada heli reaalajas transkriptsioonide, AI-teadmiste ja automaatse salvestamise jaoks.';

  @override
  String get reconnecting => 'Taasühendamine...';

  @override
  String get recordingPaused => 'Salvestamine peatatud';

  @override
  String get recordingActive => 'Salvestamine aktiivne';

  @override
  String get startRecording => 'Alusta salvestamist';

  @override
  String resumingInCountdown(String countdown) {
    return 'Jätkamine ${countdown}s pärast...';
  }

  @override
  String get tapPlayToResume => 'Puudutage esitamist jätkamiseks';

  @override
  String get listeningForAudio => 'Heli kuulamine...';

  @override
  String get preparingAudioCapture => 'Helisalvestuse ettevalmistamine';

  @override
  String get clickToBeginRecording => 'Klõpsake salvestamise alustamiseks';

  @override
  String get translated => 'tõlgitud';

  @override
  String get liveTranscript => 'Reaalajas transkriptsioon';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segmenti';
  }

  @override
  String get startRecordingToSeeTranscript =>
      'Alustage salvestamist, et näha reaalajas transkriptsiooni';

  @override
  String get paused => 'Peatatud';

  @override
  String get initializing => 'Algseadistamine...';

  @override
  String get recording => 'Salvestamine';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Mikrofon on vahetatud. Jätkamine ${countdown}s pärast';
  }

  @override
  String get clickPlayToResumeOrStop =>
      'Klõpsake esitamisel jätkamiseks või stopp lõpetamiseks';

  @override
  String get settingUpSystemAudioCapture =>
      'Süsteemiheli salvestamise seadistamine';

  @override
  String get capturingAudioAndGeneratingTranscript =>
      'Heli salvestamine ja transkriptsiooni loomine';

  @override
  String get clickToBeginRecordingSystemAudio =>
      'Klõpsake süsteemiheli salvestamise alustamiseks';

  @override
  String get you => 'Sina';

  @override
  String speakerWithId(String speakerId) {
    return 'Kõneleja $speakerId';
  }

  @override
  String get translatedByOmi => 'tõlgitud omi poolt';

  @override
  String get backToConversations => 'Tagasi vestluste juurde';

  @override
  String get systemAudio => 'Süsteem';

  @override
  String get mic => 'Mikrofon';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Helisisend määratud: $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Viga heliseadme vahetamisel: $error';
  }

  @override
  String get selectAudioInput => 'Valige helisisend';

  @override
  String get loadingDevices => 'Seadmete laadimine...';

  @override
  String get settingsHeader => 'SEADED';

  @override
  String get plansAndBilling => 'Plaanid ja Arveldus';

  @override
  String get calendarIntegration => 'Kalendri Integratsioon';

  @override
  String get dailySummary => 'Päeva kokkuvõte';

  @override
  String get developer => 'Arendaja';

  @override
  String get about => 'Teave';

  @override
  String get selectTime => 'Vali aeg';

  @override
  String get accountGroup => 'Konto';

  @override
  String get signOutQuestion => 'Logi välja?';

  @override
  String get signOutConfirmation =>
      'Kas olete kindel, et soovite välja logida?';

  @override
  String get customVocabularyHeader => 'KOHANDATUD SÕNAVARA';

  @override
  String get addWordsDescription =>
      'Lisage sõnad, mida Omi peaks transkribeerimisel ära tundma.';

  @override
  String get enterWordsHint => 'Sisestage sõnad (komaga eraldatud)';

  @override
  String get dailySummaryHeader => 'PÄEVANE KOKKUVÕTE';

  @override
  String get dailySummaryTitle => 'Päevane Kokkuvõte';

  @override
  String get dailySummaryDescription =>
      'Saa isikupärastatud kokkuvõte päeva vestlustest teavitusena.';

  @override
  String get deliveryTime => 'Edastamise aeg';

  @override
  String get deliveryTimeDescription => 'Millal saada päevast kokkuvõtet';

  @override
  String get subscription => 'Tellimus';

  @override
  String get viewPlansAndUsage => 'Vaata Plaane ja Kasutust';

  @override
  String get viewPlansDescription =>
      'Halda oma tellimust ja vaata kasutusstatistikat';

  @override
  String get addOrChangePaymentMethod => 'Lisa või muuda oma makseviisi';

  @override
  String get displayOptions => 'Kuvamisvalikud';

  @override
  String get showMeetingsInMenuBar => 'Näita kohtumisi menüüribal';

  @override
  String get displayUpcomingMeetingsDescription =>
      'Kuva tulevasi kohtumisi menüüribal';

  @override
  String get showEventsWithoutParticipants => 'Näita sündmusi ilma osalejateta';

  @override
  String get includePersonalEventsDescription =>
      'Kaasa isiklikud sündmused ilma osalejateta';

  @override
  String get upcomingMeetings => 'Tulevased kohtumised';

  @override
  String get checkingNext7Days => 'Järgmise 7 päeva kontrollimine';

  @override
  String get shortcuts => 'Kiirklahvid';

  @override
  String get shortcutChangeInstruction =>
      'Klõpsake kiirklahvil, et seda muuta. Tühistamiseks vajutage Escape.';

  @override
  String get configurePersonaDescription => 'Konfigureerige oma AI isikut';

  @override
  String get configureSTTProvider => 'Konfigureerige STT pakkuja';

  @override
  String get setConversationEndDescription =>
      'Määrake, millal vestlused automaatselt lõpevad';

  @override
  String get importDataDescription => 'Impordi andmed teistest allikatest';

  @override
  String get exportConversationsDescription =>
      'Ekspordi vestlused JSON-vormingus';

  @override
  String get exportingConversations => 'Vestluste eksportimine...';

  @override
  String get clearNodesDescription => 'Kustuta kõik sõlmed ja ühendused';

  @override
  String get deleteKnowledgeGraphQuestion => 'Kustutada teadmiste graafik?';

  @override
  String get deleteKnowledgeGraphWarning =>
      'See kustutab kõik tuletatud teadmiste graafiku andmed. Teie algse mälestused jäävad turvaliseks.';

  @override
  String get connectOmiWithAI => 'Ühenda Omi AI-assistentidega';

  @override
  String get noAPIKeys => 'API võtmed puuduvad. Looge üks alustamiseks.';

  @override
  String get autoCreateWhenDetected =>
      'Loo automaatselt, kui nimi tuvastatakse';

  @override
  String get trackPersonalGoals => 'Jälgi isiklikke eesmärke avalehel';

  @override
  String get dailyReflectionDescription =>
      'Saa meeldetuletus kell 21, et mõtiskleda oma päeva üle ja jäädvustada oma mõtted.';

  @override
  String get endpointURL => 'Lõpp-punkti URL';

  @override
  String get links => 'Lingid';

  @override
  String get discordMemberCount => 'Üle 8000 liikme Discordis';

  @override
  String get userInformation => 'Kasutajateave';

  @override
  String get capabilities => 'Võimalused';

  @override
  String get previewScreenshots => 'Ekraanipiltide eelvaade';

  @override
  String get holdOnPreparingForm => 'Oota, valmistame vormi teile ette';

  @override
  String get bySubmittingYouAgreeToOmi => 'Esitades nõustute Omi ';

  @override
  String get termsAndPrivacyPolicy => 'Tingimused ja Privaatsuspoliitika';

  @override
  String get helpsDiagnoseIssuesAutoDeletes =>
      'Aitab diagnoosida probleeme. Kustutatakse automaatselt 3 päeva pärast.';

  @override
  String get manageYourApp => 'Halda oma rakendust';

  @override
  String get updatingYourApp => 'Rakenduse värskendamine';

  @override
  String get fetchingYourAppDetails => 'Rakenduse üksikasjade hankimine';

  @override
  String get updateAppQuestion => 'Värskenda rakendust?';

  @override
  String get updateAppConfirmation =>
      'Kas olete kindel, et soovite oma rakendust värskendada? Muudatused jõustuvad pärast meie meeskonna ülevaatust.';

  @override
  String get updateApp => 'Värskenda rakendust';

  @override
  String get createAndSubmitNewApp => 'Loo ja esita uus rakendus';

  @override
  String appsCount(String count) {
    return 'Rakendused ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Privaatsed rakendused ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Avalikud rakendused ($count)';
  }

  @override
  String get newVersionAvailable => 'Uus versioon saadaval  🎉';

  @override
  String get no => 'Ei';

  @override
  String get subscriptionCancelledSuccessfully =>
      'Tellimus tühistatud edukalt. See jääb aktiivseks kuni praeguse arveldusperioodi lõpuni.';

  @override
  String get failedToCancelSubscription =>
      'Tellimuse tühistamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get invalidPaymentUrl => 'Vigane makse URL';

  @override
  String get permissionsAndTriggers => 'Load ja päästikud';

  @override
  String get chatFeatures => 'Vestluse funktsioonid';

  @override
  String get uninstall => 'Desinstalli';

  @override
  String get installs => 'PAIGALDUSED';

  @override
  String get priceLabel => 'HIND';

  @override
  String get updatedLabel => 'UUENDATUD';

  @override
  String get createdLabel => 'LOODUD';

  @override
  String get featuredLabel => 'ESILETÕSTETUD';

  @override
  String get cancelSubscriptionQuestion => 'Tühista tellimus?';

  @override
  String get cancelSubscriptionConfirmation =>
      'Kas olete kindel, et soovite tellimuse tühistada? Teil on juurdepääs praeguse arveldusperioodi lõpuni.';

  @override
  String get cancelSubscriptionButton => 'Tühista tellimus';

  @override
  String get cancelling => 'Tühistamine...';

  @override
  String get betaTesterMessage =>
      'Olete selle rakenduse beetatestija. See ei ole veel avalik. See muutub avalikuks pärast heakskiitu.';

  @override
  String get appUnderReviewMessage =>
      'Teie rakendus on läbivaatamisel ja nähtav ainult teile. See muutub avalikuks pärast heakskiitu.';

  @override
  String get appRejectedMessage =>
      'Teie rakendus lükati tagasi. Palun uuendage andmeid ja esitage uuesti läbivaatamiseks.';

  @override
  String get invalidIntegrationUrl => 'Vigane integratsiooni URL';

  @override
  String get tapToComplete => 'Puuduta lõpetamiseks';

  @override
  String get invalidSetupInstructionsUrl => 'Vigane seadistusjuhiste URL';

  @override
  String get pushToTalk => 'Vajuta rääkimiseks';

  @override
  String get summaryPrompt => 'Kokkuvõtte viip';

  @override
  String get pleaseSelectARating => 'Palun valige hinnang';

  @override
  String get reviewAddedSuccessfully => 'Arvustus edukalt lisatud 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Arvustus edukalt uuendatud 🚀';

  @override
  String get failedToSubmitReview =>
      'Arvustuse esitamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get addYourReview => 'Lisa oma arvustus';

  @override
  String get editYourReview => 'Muuda oma arvustust';

  @override
  String get writeAReviewOptional => 'Kirjuta arvustus (valikuline)';

  @override
  String get submitReview => 'Esita arvustus';

  @override
  String get updateReview => 'Uuenda arvustust';

  @override
  String get yourReview => 'Teie arvustus';

  @override
  String get anonymousUser => 'Anonüümne kasutaja';

  @override
  String get issueActivatingApp =>
      'Selle rakenduse aktiveerimisel tekkis probleem. Palun proovi uuesti.';

  @override
  String get dataAccessNoticeDescription =>
      'See rakendus pääseb ligi teie andmetele. Omi AI ei vastuta selle eest, kuidas teie andmeid kasutatakse.';

  @override
  String get copyUrl => 'Kopeeri URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Esm';

  @override
  String get weekdayTue => 'Tei';

  @override
  String get weekdayWed => 'Kol';

  @override
  String get weekdayThu => 'Nel';

  @override
  String get weekdayFri => 'Ree';

  @override
  String get weekdaySat => 'Lau';

  @override
  String get weekdaySun => 'Püh';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName integratsioon tuleb peagi';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Juba eksporditud $platform';
  }

  @override
  String get anotherPlatform => 'teise platvormiga';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Palun autentimige $serviceName kaudu Seaded > Ülesannete integratsioonid';
  }

  @override
  String addingToService(String serviceName) {
    return 'Lisamine $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Lisatud $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Lisamine $serviceName ebaõnnestus';
  }

  @override
  String get permissionDeniedForAppleReminders =>
      'Apple Reminders luba keelatud';

  @override
  String failedToCreateApiKey(String error) {
    return 'Teenusepakkuja API võtme loomine ebaõnnestus: $error';
  }

  @override
  String get createAKey => 'Loo võti';

  @override
  String get apiKeyRevokedSuccessfully => 'API võti tühistatud edukalt';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API võtme tühistamine ebaõnnestus: $error';
  }

  @override
  String get omiApiKeys => 'Omi API võtmed';

  @override
  String get apiKeysDescription =>
      'API võtmeid kasutatakse autentimiseks, kui teie rakendus suhtleb OMI serveriga. Need võimaldavad teie rakendusel luua mälestusi ja turvaliselt juurde pääseda teistele OMI teenustele.';

  @override
  String get aboutOmiApiKeys => 'Omi API võtmete kohta';

  @override
  String get yourNewKey => 'Teie uus võti:';

  @override
  String get copyToClipboard => 'Kopeeri lõikelauale';

  @override
  String get pleaseCopyKeyNow =>
      'Palun kopeerige see nüüd ja kirjutage kuhugi turvalisesse kohta. ';

  @override
  String get willNotSeeAgain => 'Te ei saa seda enam näha.';

  @override
  String get revokeKey => 'Tühista võti';

  @override
  String get revokeApiKeyQuestion => 'Tühistada API võti?';

  @override
  String get revokeApiKeyWarning =>
      'Seda toimingut ei saa tagasi võtta. Ükski rakendus, mis kasutab seda võtit, ei pääse enam API-le ligi.';

  @override
  String get revoke => 'Tühista';

  @override
  String get whatWouldYouLikeToCreate => 'Mida soovite luua?';

  @override
  String get createAnApp => 'Loo rakendus';

  @override
  String get createAndShareYourApp => 'Loo ja jaga oma rakendust';

  @override
  String get createMyClone => 'Loo minu kloon';

  @override
  String get createYourDigitalClone => 'Loo oma digitaalne kloon';

  @override
  String get itemApp => 'Rakendus';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Hoia $item avalik';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Muuta $item avalikuks?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Muuta $item privaatseks?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Kui muudate $item avalikuks, saavad kõik seda kasutada';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Kui muudate $item nüüd privaatseks, lakkab see töötamast kõigil ja on nähtav ainult teile';
  }

  @override
  String get manageApp => 'Halda rakendust';

  @override
  String get updatePersonaDetails => 'Uuenda persona üksikasju';

  @override
  String deleteItemTitle(String item) {
    return 'Kustuta $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Kustuta $item?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Kas olete kindel, et soovite seda $item kustutada? Seda toimingut ei saa tagasi võtta.';
  }

  @override
  String get revokeKeyQuestion => 'Tühista võti?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Kas olete kindel, et soovite võtme \"$keyName\" tühistada? Seda toimingut ei saa tagasi võtta.';
  }

  @override
  String get createNewKey => 'Loo uus võti';

  @override
  String get keyNameHint => 'nt Claude Desktop';

  @override
  String get pleaseEnterAName => 'Palun sisestage nimi.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Võtme loomine ebaõnnestus: $error';
  }

  @override
  String get failedToCreateKeyTryAgain =>
      'Võtme loomine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get keyCreated => 'Võti loodud';

  @override
  String get keyCreatedMessage =>
      'Teie uus võti on loodud. Palun kopeerige see nüüd. Te ei näe seda enam.';

  @override
  String get keyWord => 'Võti';

  @override
  String get externalAppAccess => 'Väliste rakenduste juurdepääs';

  @override
  String get externalAppAccessDescription =>
      'Järgmistel installitud rakendustel on välised integratsioonid ja need saavad juurdepääsu teie andmetele, nagu vestlused ja mälestused.';

  @override
  String get noExternalAppsHaveAccess =>
      'Ühelgi välisel rakendusel pole juurdepääsu teie andmetele.';

  @override
  String get maximumSecurityE2ee => 'Maksimaalne turvalisus (E2EE)';

  @override
  String get e2eeDescription =>
      'Otsast otsani krüpteerimine on privaatsuse kuldstandard. Kui see on lubatud, krüpteeritakse teie andmed teie seadmes enne nende saatmist meie serveritesse. See tähendab, et keegi, isegi mitte Omi, ei saa teie sisule juurde pääseda.';

  @override
  String get importantTradeoffs => 'Olulised kompromissid:';

  @override
  String get e2eeTradeoff1 =>
      '• Mõned funktsioonid, nagu väliste rakenduste integratsioonid, võivad olla keelatud.';

  @override
  String get e2eeTradeoff2 =>
      '• Kui kaotate oma parooli, ei saa teie andmeid taastada.';

  @override
  String get featureComingSoon => 'See funktsioon on peagi tulemas!';

  @override
  String get migrationInProgressMessage =>
      'Migreerimine käimas. Te ei saa kaitsetaset muuta enne selle lõpetamist.';

  @override
  String get migrationFailed => 'Migreerimine ebaõnnestus';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migreerimine $source kaudu $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objekti';
  }

  @override
  String get secureEncryption => 'Turvaline krüpteerimine';

  @override
  String get secureEncryptionDescription =>
      'Teie andmed on krüpteeritud teile ainulaadse võtmega meie serverites, mis asuvad Google Cloudis. See tähendab, et teie toorandmed pole kellelegi kättesaadavad, sealhulgas Omi töötajatele või Google\'ile, otse andmebaasist.';

  @override
  String get endToEndEncryption => 'Otsast otsani krüpteerimine';

  @override
  String get e2eeCardDescription =>
      'Lubab maksimaalse turvalisuse, kus ainult teie saate oma andmetele juurde pääseda. Puudutage, et rohkem teada saada.';

  @override
  String get dataAlwaysEncrypted =>
      'Olenemata tasemest on teie andmed alati krüpteeritud puhkeolekus ja edastamisel.';

  @override
  String get readOnlyScope => 'Ainult lugemine';

  @override
  String get fullAccessScope => 'Täielik juurdepääs';

  @override
  String get readScope => 'Lugemine';

  @override
  String get writeScope => 'Kirjutamine';

  @override
  String get apiKeyCreated => 'API võti loodud!';

  @override
  String get saveKeyWarning =>
      'Salvesta see võti kohe! Sa ei näe seda enam kunagi.';

  @override
  String get yourApiKey => 'TEIE API VÕTI';

  @override
  String get tapToCopy => 'Puudutage kopeerimiseks';

  @override
  String get copyKey => 'Kopeeri võti';

  @override
  String get createApiKey => 'Loo API võti';

  @override
  String get accessDataProgrammatically =>
      'Pääsete oma andmetele programmiliselt juurde';

  @override
  String get keyNameLabel => 'VÕTME NIMI';

  @override
  String get keyNamePlaceholder => 'nt. Minu rakenduse integratsioon';

  @override
  String get permissionsLabel => 'ÕIGUSED';

  @override
  String get permissionsInfoNote =>
      'R = Lugemine, W = Kirjutamine. Vaikimisi ainult lugemine, kui midagi pole valitud.';

  @override
  String get developerApi => 'Arendaja API';

  @override
  String get createAKeyToGetStarted => 'Alustamiseks loo võti';

  @override
  String errorWithMessage(String error) {
    return 'Viga: $error';
  }

  @override
  String get omiTraining => 'Omi Koolitus';

  @override
  String get trainingDataProgram => 'Treeningandmete programm';

  @override
  String get getOmiUnlimitedFree =>
      'Saage Omi Unlimited tasuta, panustades oma andmetega AI mudelite treenimisse.';

  @override
  String get trainingDataBullets =>
      '• Teie andmed aitavad parandada AI mudeleid\n• Jagatakse ainult mittetundlikke andmeid\n• Täiesti läbipaistev protsess';

  @override
  String get learnMoreAtOmiTraining => 'Lisateave omi.me/training';

  @override
  String get agreeToContributeData =>
      'Ma mõistan ja nõustun panustama oma andmetega AI treenimisse';

  @override
  String get submitRequest => 'Esita taotlus';

  @override
  String get thankYouRequestUnderReview =>
      'Aitäh! Teie taotlus on läbivaatamisel. Teavitame teid pärast kinnitamist.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Teie plaan jääb aktiivseks kuni $date. Pärast seda kaotate juurdepääsu piiramatutele funktsioonidele. Kas olete kindel?';
  }

  @override
  String get confirmCancellation => 'Kinnita tühistamine';

  @override
  String get keepMyPlan => 'Säilita minu plaan';

  @override
  String get subscriptionSetToCancel =>
      'Teie tellimus on seatud tühistuma perioodi lõpus.';

  @override
  String get switchedToOnDevice => 'Lülitatud seadme transkriptsioonile';

  @override
  String get couldNotSwitchToFreePlan =>
      'Tasuta plaanile lülitumine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get couldNotLoadPlans =>
      'Saadaolevaid plaane ei õnnestunud laadida. Palun proovi uuesti.';

  @override
  String get selectedPlanNotAvailable =>
      'Valitud plaan pole saadaval. Palun proovi uuesti.';

  @override
  String get upgradeToAnnualPlan => 'Täienda aastasele plaanile';

  @override
  String get importantBillingInfo => 'Oluline arvelduse teave:';

  @override
  String get monthlyPlanContinues =>
      'Teie praegune kuuplaan jätkub kuni arveldusperioodi lõpuni';

  @override
  String get paymentMethodCharged =>
      'Teie olemasolev makseviis debiteeritakse automaatselt, kui teie kuuplaan lõpeb';

  @override
  String get annualSubscriptionStarts =>
      'Teie 12-kuuline aastatellimus algab automaatselt pärast makse tegemist';

  @override
  String get thirteenMonthsCoverage =>
      'Saate kokku 13 kuud katvust (praegune kuu + 12 kuud aastas)';

  @override
  String get confirmUpgrade => 'Kinnita täiendus';

  @override
  String get confirmPlanChange => 'Kinnita plaani muutmine';

  @override
  String get confirmAndProceed => 'Kinnita ja jätka';

  @override
  String get upgradeScheduled => 'Täiendus planeeritud';

  @override
  String get changePlan => 'Muuda plaani';

  @override
  String get upgradeAlreadyScheduled =>
      'Teie täiendus aastasele plaanile on juba planeeritud';

  @override
  String get youAreOnUnlimitedPlan => 'Olete Piiramatul plaanil.';

  @override
  String get yourOmiUnleashed =>
      'Teie Omi, vabastatud. Minge piiramatu juurde lõputute võimaluste jaoks.';

  @override
  String planEndedOn(String date) {
    return 'Teie plaan lõppes $date.\\nTellige uuesti kohe - teilt võetakse kohe tasu uue arveldusperioodi eest.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Teie plaan on seatud tühistuma $date.\\nTellige uuesti kohe, et säilitada oma eelised - tasu ei võeta kuni $date.';
  }

  @override
  String get annualPlanStartsAutomatically =>
      'Teie aastane plaan algab automaatselt, kui teie kuuplaan lõpeb.';

  @override
  String planRenewsOn(String date) {
    return 'Teie plaan uueneb $date.';
  }

  @override
  String get unlimitedConversations => 'Piiramatult vestlusi';

  @override
  String get askOmiAnything => 'Küsige Omilt kõike oma elu kohta';

  @override
  String get unlockOmiInfiniteMemory => 'Avage Omi lõpmatu mälu';

  @override
  String get youreOnAnnualPlan => 'Olete aastasel plaanil';

  @override
  String get alreadyBestValuePlan =>
      'Teil on juba parima väärtusega plaan. Muudatusi pole vaja.';

  @override
  String get unableToLoadPlans => 'Plaane ei saa laadida';

  @override
  String get checkConnectionTryAgain =>
      'Palun kontrollige ühendust ja proovige uuesti';

  @override
  String get useFreePlan => 'Kasuta tasuta plaani';

  @override
  String get continueText => 'Jätka';

  @override
  String get resubscribe => 'Telli uuesti';

  @override
  String get couldNotOpenPaymentSettings =>
      'Makseseadeid ei saanud avada. Palun proovi uuesti.';

  @override
  String get managePaymentMethod => 'Halda makseviisi';

  @override
  String get cancelSubscription => 'Tühista tellimus';

  @override
  String endsOnDate(String date) {
    return 'Lõpeb $date';
  }

  @override
  String get active => 'Aktiivne';

  @override
  String get freePlan => 'Tasuta plaan';

  @override
  String get configure => 'Seadista';

  @override
  String get privacyInformation => 'Privaatsusinfo';

  @override
  String get yourPrivacyMattersToUs => 'Teie privaatsus on meile oluline';

  @override
  String get privacyIntroText =>
      'Omis võtame teie privaatsust väga tõsiselt. Tahame olla läbipaistvad andmete osas, mida kogume ja kuidas neid kasutame. Siin on see, mida peate teadma:';

  @override
  String get whatWeTrack => 'Mida jälgime';

  @override
  String get anonymityAndPrivacy => 'Anonüümsus ja privaatsus';

  @override
  String get optInAndOptOutOptions => 'Nõustumise ja keeldumise valikud';

  @override
  String get ourCommitment => 'Meie kohustus';

  @override
  String get commitmentText =>
      'Oleme pühendunud kasutama kogutud andmeid ainult Omi paremaks muutmiseks. Teie privaatsus ja usaldus on meile ülimalt olulised.';

  @override
  String get thankYouText =>
      'Täname, et olete Omi väärtuslik kasutaja. Kui teil on küsimusi või muresid, võtke meiega ühendust aadressil team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'WiFi sünkroonimise seaded';

  @override
  String get enterHotspotCredentials =>
      'Sisestage oma telefoni leviala mandaadid';

  @override
  String get wifiSyncUsesHotspot =>
      'WiFi sünkroonimine kasutab teie telefoni levialana. Leidke nimi ja parool menüüst Seaded > Isiklik leviala.';

  @override
  String get hotspotNameSsid => 'Leviala nimi (SSID)';

  @override
  String get exampleIphoneHotspot => 'nt iPhone Hotspot';

  @override
  String get password => 'Parool';

  @override
  String get enterHotspotPassword => 'Sisestage leviala parool';

  @override
  String get saveCredentials => 'Salvesta mandaadid';

  @override
  String get clearCredentials => 'Kustuta mandaadid';

  @override
  String get pleaseEnterHotspotName => 'Palun sisestage leviala nimi';

  @override
  String get wifiCredentialsSaved => 'WiFi mandaadid salvestatud';

  @override
  String get wifiCredentialsCleared => 'WiFi mandaadid kustutatud';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Kokkuvõte loodud kuupäevaks $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations =>
      'Kokkuvõtte loomine ebaõnnestus. Veenduge, et teil on selle päeva vestlusi.';

  @override
  String get summaryNotFound => 'Kokkuvõtet ei leitud';

  @override
  String get yourDaysJourney => 'Teie päeva teekond';

  @override
  String get highlights => 'Esiletõstetud';

  @override
  String get unresolvedQuestions => 'Lahendamata küsimused';

  @override
  String get decisions => 'Otsused';

  @override
  String get learnings => 'Õpitu';

  @override
  String get autoDeletesAfterThreeDays =>
      'Kustutatakse automaatselt 3 päeva pärast.';

  @override
  String get knowledgeGraphDeletedSuccessfully =>
      'Teadmusgraaf edukalt kustutatud';

  @override
  String get exportStartedMayTakeFewSeconds =>
      'Eksport alustatud. See võib võtta mõne sekundi...';

  @override
  String get knowledgeGraphDeleteDescription =>
      'See kustutab kõik tuletatud teadmusgraafi andmed (sõlmed ja ühendused). Teie algsed mälestused jäävad turvaliseks. Graaf ehitatakse aja jooksul või järgmise päringu korral uuesti üles.';

  @override
  String get configureDailySummaryDigest =>
      'Seadista oma igapäevane ülesannete kokkuvõte';

  @override
  String accessesDataTypes(String dataTypes) {
    return 'Juurdepääs: $dataTypes';
  }

  @override
  String triggeredByType(String triggerType) {
    return 'käivitab $triggerType';
  }

  @override
  String accessesAndTriggeredBy(
    String accessDescription,
    String triggerDescription,
  ) {
    return '$accessDescription ja on $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return 'On $triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured =>
      'Konkreetset andmetele juurdepääsu pole seadistatud.';

  @override
  String get basicPlanDescription => '1200 premium minutit + piiramatu seadmes';

  @override
  String get minutes => 'minutit';

  @override
  String get omiHas => 'Omil on:';

  @override
  String get premiumMinutesUsed => 'Premium minutid kasutatud.';

  @override
  String get setupOnDevice => 'Seadista seadmes';

  @override
  String get forUnlimitedFreeTranscription =>
      'piiramatuks tasuta transkriptsiooniks.';

  @override
  String premiumMinsLeft(int count) {
    return '$count premium minutit jäänud.';
  }

  @override
  String get alwaysAvailable => 'alati saadaval.';

  @override
  String get importHistory => 'Importimise ajalugu';

  @override
  String get noImportsYet => 'Importe pole veel';

  @override
  String get selectZipFileToImport => 'Vali importimiseks .zip fail!';

  @override
  String get otherDevicesComingSoon => 'Teised seadmed tulekul';

  @override
  String get deleteAllLimitlessConversations =>
      'Kustuta kõik Limitless vestlused?';

  @override
  String get deleteAllLimitlessWarning =>
      'See kustutab jäädavalt kõik Limitlessist imporditud vestlused. Seda toimingut ei saa tagasi võtta.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Kustutatud $count Limitless vestlust';
  }

  @override
  String get failedToDeleteConversations => 'Vestluste kustutamine ebaõnnestus';

  @override
  String get deleteImportedData => 'Kustuta imporditud andmed';

  @override
  String get statusPending => 'Ootel';

  @override
  String get statusProcessing => 'Töötlemine';

  @override
  String get statusCompleted => 'Lõpetatud';

  @override
  String get statusFailed => 'Ebaõnnestunud';

  @override
  String nConversations(int count) {
    return '$count vestlust';
  }

  @override
  String get pleaseEnterName => 'Palun sisesta nimi';

  @override
  String get nameMustBeBetweenCharacters =>
      'Nimi peab olema 2 kuni 40 tähemärki';

  @override
  String get deleteSampleQuestion => 'Kustuta näidis?';

  @override
  String deleteSampleConfirmation(String name) {
    return 'Kas olete kindel, et soovite kustutada $name näidise?';
  }

  @override
  String get confirmDeletion => 'Kinnita kustutamine';

  @override
  String deletePersonConfirmation(String name) {
    return 'Kas olete kindel, et soovite kustutada $name? See eemaldab ka kõik seotud kõnenäidised.';
  }

  @override
  String get howItWorksTitle => 'Kuidas see töötab?';

  @override
  String get howPeopleWorks =>
      'Kui inimene on loodud, võite minna vestluse transkriptsiooni juurde ja määrata talle vastavad segmendid, nii saab Omi ka tema kõnet tuvastada!';

  @override
  String get tapToDelete => 'Puuduta kustutamiseks';

  @override
  String get newTag => 'UUS';

  @override
  String get needHelpChatWithUs => 'Vajad abi? Vestle meiega';

  @override
  String get localStorageEnabled => 'Kohalik salvestus lubatud';

  @override
  String get localStorageDisabled => 'Kohalik salvestus keelatud';

  @override
  String failedToUpdateSettings(String error) {
    return 'Seadete värskendamine ebaõnnestus: $error';
  }

  @override
  String get privacyNotice => 'Privaatsusteade';

  @override
  String get recordingsMayCaptureOthers =>
      'Salvestised võivad jäädvustada teiste inimeste hääli. Enne lubamist veenduge, et teil on kõigi osalejate nõusolek.';

  @override
  String get enable => 'Luba';

  @override
  String get storeAudioOnPhone => 'Salvesta heli telefoni';

  @override
  String get on => 'On';

  @override
  String get storeAudioDescription =>
      'Hoidke kõik helisalvestised telefonis lokaalselt. Kui on keelatud, salvestatakse ainult ebaõnnestunud üleslaadimised ruumi säästmiseks.';

  @override
  String get enableLocalStorage => 'Luba kohalik salvestus';

  @override
  String get cloudStorageEnabled => 'Pilvesalvestus lubatud';

  @override
  String get cloudStorageDisabled => 'Pilvesalvestus keelatud';

  @override
  String get enableCloudStorage => 'Luba pilvesalvestus';

  @override
  String get storeAudioOnCloud => 'Salvesta heli pilve';

  @override
  String get cloudStorageDialogMessage =>
      'Teie reaalajas salvestised salvestatakse privaatsesse pilvesalvestusse, kui räägite.';

  @override
  String get storeAudioCloudDescription =>
      'Salvestage oma reaalajas salvestised privaatsesse pilvesalvestusse, kui räägite. Heli salvestatakse turvaliselt reaalajas.';

  @override
  String get downloadingFirmware => 'Püsivara allalaadimine';

  @override
  String get installingFirmware => 'Püsivara paigaldamine';

  @override
  String get firmwareUpdateWarning =>
      'Ärge sulgege rakendust ega lülitage seadet välja. See võib teie seadet kahjustada.';

  @override
  String get firmwareUpdated => 'Püsivara uuendatud';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return 'Palun taaskäivitage $deviceName värskenduse lõpuleviimiseks.';
  }

  @override
  String get yourDeviceIsUpToDate => 'Teie seade on ajakohane';

  @override
  String get currentVersion => 'Praegune versioon';

  @override
  String get latestVersion => 'Uusim versioon';

  @override
  String get whatsNew => 'Mis on uut';

  @override
  String get installUpdate => 'Installi värskendus';

  @override
  String get updateNow => 'Värskenda kohe';

  @override
  String get updateGuide => 'Värskendamise juhend';

  @override
  String get checkingForUpdates => 'Värskenduste otsimine';

  @override
  String get checkingFirmwareVersion => 'Püsivara versiooni kontrollimine...';

  @override
  String get firmwareUpdate => 'Püsivara värskendus';

  @override
  String get payments => 'Maksed';

  @override
  String get connectPaymentMethodInfo =>
      'Ühendage allpool maksemeetod, et alustada oma rakenduste eest maksete saamist.';

  @override
  String get selectedPaymentMethod => 'Valitud maksemeetod';

  @override
  String get availablePaymentMethods => 'Saadaolevad maksemeetodid';

  @override
  String get activeStatus => 'Aktiivne';

  @override
  String get connectedStatus => 'Ühendatud';

  @override
  String get notConnectedStatus => 'Pole ühendatud';

  @override
  String get setActive => 'Määra aktiivseks';

  @override
  String get getPaidThroughStripe =>
      'Saate oma rakenduste müügi eest tasu Stripe\'i kaudu';

  @override
  String get monthlyPayouts => 'Igakuised väljamaksed';

  @override
  String get monthlyPayoutsDescription =>
      'Saate igakuiseid makseid otse oma kontole, kui jõuate 10 \$ teenimiseni';

  @override
  String get secureAndReliable => 'Turvaline ja usaldusväärne';

  @override
  String get stripeSecureDescription =>
      'Stripe tagab teie rakenduse tulude turvalised ja õigeaegsed ülekanded';

  @override
  String get selectYourCountry => 'Valige oma riik';

  @override
  String get countrySelectionPermanent =>
      'Teie riigivalik on püsiv ja seda ei saa hiljem muuta.';

  @override
  String get byClickingConnectNow => 'Klõpsates \"Ühenda kohe\" nõustute';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe ühendatud konto leping';

  @override
  String get errorConnectingToStripe =>
      'Viga Stripe\'iga ühendamisel! Palun proovige hiljem uuesti.';

  @override
  String get connectingYourStripeAccount => 'Teie Stripe konto ühendamine';

  @override
  String get stripeOnboardingInstructions =>
      'Palun viige Stripe\'i registreerimisprotsess lõpule oma brauseris. See leht värskendatakse automaatselt pärast lõpetamist.';

  @override
  String get failedTryAgain => 'Ebaõnnestus? Proovi uuesti';

  @override
  String get illDoItLater => 'Teen seda hiljem';

  @override
  String get successfullyConnected => 'Edukalt ühendatud!';

  @override
  String get stripeReadyForPayments =>
      'Teie Stripe konto on nüüd valmis makseid vastu võtma. Saate kohe alustada oma rakenduste müügist teenimist.';

  @override
  String get updateStripeDetails => 'Värskenda Stripe andmeid';

  @override
  String get errorUpdatingStripeDetails =>
      'Viga Stripe andmete värskendamisel! Palun proovige hiljem uuesti.';

  @override
  String get updatePayPal => 'Värskenda PayPal';

  @override
  String get setUpPayPal => 'Seadista PayPal';

  @override
  String get updatePayPalAccountDetails =>
      'Värskendage oma PayPali konto andmeid';

  @override
  String get connectPayPalToReceivePayments =>
      'Ühendage oma PayPali konto, et alustada oma rakenduste eest maksete saamist';

  @override
  String get paypalEmail => 'PayPali e-post';

  @override
  String get paypalMeLink => 'PayPal.me link';

  @override
  String get stripeRecommendation =>
      'Kui Stripe on teie riigis saadaval, soovitame tungivalt seda kasutada kiiremate ja lihtsamate väljamaksete jaoks.';

  @override
  String get updatePayPalDetails => 'Värskenda PayPali andmeid';

  @override
  String get savePayPalDetails => 'Salvesta PayPali andmed';

  @override
  String get pleaseEnterPayPalEmail => 'Palun sisestage oma PayPali e-post';

  @override
  String get pleaseEnterPayPalMeLink => 'Palun sisestage oma PayPal.me link';

  @override
  String get doNotIncludeHttpInLink =>
      'Ärge lisage lingile http, https ega www';

  @override
  String get pleaseEnterValidPayPalMeLink =>
      'Palun sisestage kehtiv PayPal.me link';

  @override
  String get pleaseEnterValidEmail => 'Palun sisestage kehtiv e-posti aadress';

  @override
  String get syncingYourRecordings => 'Sinu salvestuste sünkroonimine';

  @override
  String get syncYourRecordings => 'Sünkrooni oma salvestused';

  @override
  String get syncNow => 'Sünkrooni kohe';

  @override
  String get error => 'Viga';

  @override
  String get speechSamples => 'Kõnenäidised';

  @override
  String additionalSampleIndex(String index) {
    return 'Lisanäidis $index';
  }

  @override
  String durationSeconds(String seconds) {
    return 'Kestus: $seconds sekundit';
  }

  @override
  String get additionalSpeechSampleRemoved => 'Lisakõnenäidis eemaldatud';

  @override
  String get consentDataMessage =>
      'Jätkates salvestatakse kõik selle rakendusega jagatud andmed (sealhulgas teie vestlused, salvestised ja isiklikud andmed) turvaliselt meie serverites, et pakkuda teile tehisintellektil põhinevaid teadmisi ja võimaldada kõiki rakenduse funktsioone.';

  @override
  String get tasksEmptyStateMessage =>
      'Teie vestlustest pärit ülesanded ilmuvad siia.\nPuudutage + käsitsi loomiseks.';

  @override
  String get clearChatAction => 'Tühjenda vestlus';

  @override
  String get enableApps => 'Luba rakendused';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => 'näita rohkem ↓';

  @override
  String get showLess => 'näita vähem ↑';

  @override
  String get loadingYourRecording => 'Salvestuse laadimine...';

  @override
  String get photoDiscardedMessage =>
      'See foto kõrvaldati, kuna see polnud oluline.';

  @override
  String get analyzing => 'Analüüsimine...';

  @override
  String get searchCountries => 'Otsi riike...';

  @override
  String get checkingAppleWatch => 'Apple Watchi kontrollimine...';

  @override
  String get installOmiOnAppleWatch => 'Installige Omi oma\nApple Watchi';

  @override
  String get installOmiOnAppleWatchDescription =>
      'Apple Watchi kasutamiseks Omiga peate esmalt installima Omi rakenduse oma kellale.';

  @override
  String get openOmiOnAppleWatch => 'Avage Omi oma\nApple Watchis';

  @override
  String get openOmiOnAppleWatchDescription =>
      'Omi rakendus on teie Apple Watchile installitud. Avage see ja puudutage käivitamiseks Start.';

  @override
  String get openWatchApp => 'Ava Watchi rakendus';

  @override
  String get iveInstalledAndOpenedTheApp =>
      'Olen rakenduse installinud ja avanud';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watchi rakendust ei saa avada. Avage Watchi rakendus käsitsi oma Apple Watchis ja installige Omi jaotisest \"Saadaolevad rakendused\".';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch ühendatud!';

  @override
  String get appleWatchNotReachable =>
      'Apple Watch pole veel kättesaadav. Veenduge, et Omi rakendus oleks teie kellas avatud.';

  @override
  String errorCheckingConnection(String error) {
    return 'Ühenduse kontrollimisel ilmnes viga: $error';
  }

  @override
  String get muted => 'Vaigistatud';

  @override
  String get processNow => 'Töötle kohe';

  @override
  String get finishedConversation => 'Vestlus lõppenud?';

  @override
  String get stopRecordingConfirmation =>
      'Kas olete kindel, et soovite salvestamise peatada ja vestluse kohe kokku võtta?';

  @override
  String get conversationEndsManually => 'Vestlus lõpeb ainult käsitsi.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return 'Vestlus võetakse kokku pärast $minutes minut$suffix vaikust.';
  }

  @override
  String get dontAskAgain => 'Ära küsi uuesti';

  @override
  String get waitingForTranscriptOrPhotos =>
      'Ootan transkriptsiooni või fotosid...';

  @override
  String get noSummaryYet => 'Kokkuvõtet veel pole';

  @override
  String hints(String text) {
    return 'Vihjed: $text';
  }

  @override
  String get testConversationPrompt => 'Testi vestluse viipa';

  @override
  String get prompt => 'Viip';

  @override
  String get result => 'Tulemus:';

  @override
  String get compareTranscripts => 'Võrdle transkriptsioone';

  @override
  String get notHelpful => 'Ei olnud kasulik';

  @override
  String get exportTasksWithOneTap => 'Ekspordi ülesanded ühe puudutusega!';

  @override
  String get inProgress => 'Töötlemisel';

  @override
  String get photos => 'Fotod';

  @override
  String get rawData => 'Töötlemata andmed';

  @override
  String get content => 'Sisu';

  @override
  String get noContentToDisplay => 'Sisu pole kuvamiseks';

  @override
  String get noSummary => 'Kokkuvõte puudub';

  @override
  String get updateOmiFirmware => 'Värskenda omi püsivara';

  @override
  String get anErrorOccurredTryAgain => 'Tekkis viga. Palun proovige uuesti.';

  @override
  String get welcomeBackSimple => 'Tere tulemast tagasi';

  @override
  String get addVocabularyDescription =>
      'Lisage sõnad, mida Omi peaks transkriptsiooni ajal ära tundma.';

  @override
  String get enterWordsCommaSeparated => 'Sisestage sõnad (komadega eraldatud)';

  @override
  String get whenToReceiveDailySummary =>
      'Millal saada oma igapäevane kokkuvõte';

  @override
  String get checkingNextSevenDays => 'Kontrollitakse järgmist 7 päeva';

  @override
  String failedToDeleteError(String error) {
    return 'Kustutamine ebaõnnestus: $error';
  }

  @override
  String get developerApiKeys => 'Arendaja API võtmed';

  @override
  String get noApiKeysCreateOne => 'API võtmeid pole. Looge üks alustamiseks.';

  @override
  String get commandRequired => '⌘ on nõutav';

  @override
  String get spaceKey => 'Tühik';

  @override
  String loadMoreRemaining(String count) {
    return 'Laadi rohkem ($count järel)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return 'Top $percentile% kasutaja';
  }

  @override
  String get wrappedMinutes => 'minutit';

  @override
  String get wrappedConversations => 'vestlust';

  @override
  String get wrappedDaysActive => 'aktiivset päeva';

  @override
  String get wrappedYouTalkedAbout => 'Sa rääkisid';

  @override
  String get wrappedActionItems => 'Ülesanded';

  @override
  String get wrappedTasksCreated => 'loodud ülesannet';

  @override
  String get wrappedCompleted => 'lõpetatud';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% lõpetamismäär';
  }

  @override
  String get wrappedYourTopDays => 'Sinu parimad päevad';

  @override
  String get wrappedBestMoments => 'Parimad hetked';

  @override
  String get wrappedMyBuddies => 'Minu sõbrad';

  @override
  String get wrappedCouldntStopTalkingAbout => 'Ei suutnud lõpetada rääkimist';

  @override
  String get wrappedShow => 'SARI';

  @override
  String get wrappedMovie => 'FILM';

  @override
  String get wrappedBook => 'RAAMAT';

  @override
  String get wrappedCelebrity => 'KUULSUS';

  @override
  String get wrappedFood => 'TOIT';

  @override
  String get wrappedMovieRecs => 'Filmisoovitused sõpradele';

  @override
  String get wrappedBiggest => 'Suurim';

  @override
  String get wrappedStruggle => 'Väljakutse';

  @override
  String get wrappedButYouPushedThrough => 'Aga sa said hakkama 💪';

  @override
  String get wrappedWin => 'Võit';

  @override
  String get wrappedYouDidIt => 'Sa tegid seda! 🎉';

  @override
  String get wrappedTopPhrases => 'Top 5 fraasi';

  @override
  String get wrappedMins => 'min';

  @override
  String get wrappedConvos => 'vestlust';

  @override
  String get wrappedDays => 'päeva';

  @override
  String get wrappedMyBuddiesLabel => 'MINU SÕBRAD';

  @override
  String get wrappedObsessionsLabel => 'KINNISIDEED';

  @override
  String get wrappedStruggleLabel => 'VÄLJAKUTSE';

  @override
  String get wrappedWinLabel => 'VÕIT';

  @override
  String get wrappedTopPhrasesLabel => 'TOP FRAASID';

  @override
  String get wrappedLetsHitRewind => 'Kerime tagasi sinu';

  @override
  String get wrappedGenerateMyWrapped => 'Genereeri minu Wrapped';

  @override
  String get wrappedProcessingDefault => 'Töötlemine...';

  @override
  String get wrappedCreatingYourStory => 'Loome sinu\n2025 aasta lugu...';

  @override
  String get wrappedSomethingWentWrong => 'Midagi läks\nvalesti';

  @override
  String get wrappedAnErrorOccurred => 'Tekkis viga';

  @override
  String get wrappedTryAgain => 'Proovi uuesti';

  @override
  String get wrappedNoDataAvailable => 'Andmed pole saadaval';

  @override
  String get wrappedOmiLifeRecap => 'Omi elu kokkuvõte';

  @override
  String get wrappedSwipeUpToBegin => 'Pühkige üles alustamiseks';

  @override
  String get wrappedShareText =>
      'Minu 2025, jäädvustatud Omi poolt ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare =>
      'Jagamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get wrappedFailedToStartGeneration =>
      'Genereerimise alustamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get wrappedStarting => 'Alustamine...';

  @override
  String get wrappedShare => 'Jaga';

  @override
  String get wrappedShareYourWrapped => 'Jaga oma Wrapped';

  @override
  String get wrappedMy2025 => 'Minu 2025';

  @override
  String get wrappedRememberedByOmi => 'jäädvustatud Omi poolt';

  @override
  String get wrappedMostFunDay => 'Kõige lõbusam';

  @override
  String get wrappedMostProductiveDay => 'Kõige produktiivsem';

  @override
  String get wrappedMostIntenseDay => 'Kõige intensiivsem';

  @override
  String get wrappedFunniestMoment => 'Naljavam';

  @override
  String get wrappedMostCringeMoment => 'Piinlikum';

  @override
  String get wrappedMinutesLabel => 'minutit';

  @override
  String get wrappedConversationsLabel => 'vestlust';

  @override
  String get wrappedDaysActiveLabel => 'aktiivset päeva';

  @override
  String get wrappedTasksGenerated => 'ülesannet loodud';

  @override
  String get wrappedTasksCompleted => 'ülesannet lõpetatud';

  @override
  String get wrappedTopFivePhrases => 'Top 5 fraasi';

  @override
  String get wrappedAGreatDay => 'Suurepärane päev';

  @override
  String get wrappedGettingItDone => 'Asjade ärategemine';

  @override
  String get wrappedAChallenge => 'Väljakutse';

  @override
  String get wrappedAHilariousMoment => 'Naljakas hetk';

  @override
  String get wrappedThatAwkwardMoment => 'See piinlik hetk';

  @override
  String get wrappedYouHadFunnyMoments => 'Sul oli sel aastal naljakaid hetki!';

  @override
  String get wrappedWeveAllBeenThere => 'Me kõik oleme seal olnud!';

  @override
  String get wrappedFriend => 'Sõber';

  @override
  String get wrappedYourBuddy => 'Sinu sõber!';

  @override
  String get wrappedNotMentioned => 'Pole mainitud';

  @override
  String get wrappedTheHardPart => 'Raske osa';

  @override
  String get wrappedPersonalGrowth => 'Isiklik areng';

  @override
  String get wrappedFunDay => 'Lõbus';

  @override
  String get wrappedProductiveDay => 'Produktiivne';

  @override
  String get wrappedIntenseDay => 'Intensiivne';

  @override
  String get wrappedFunnyMomentTitle => 'Naljakas hetk';

  @override
  String get wrappedCringeMomentTitle => 'Piinlik hetk';

  @override
  String get wrappedYouTalkedAboutBadge => 'Rääkisid';

  @override
  String get wrappedCompletedLabel => 'Lõpetatud';

  @override
  String get wrappedMyBuddiesCard => 'Minu sõbrad';

  @override
  String get wrappedBuddiesLabel => 'SÕBRAD';

  @override
  String get wrappedObsessionsLabelUpper => 'KINNISMÕTTED';

  @override
  String get wrappedStruggleLabelUpper => 'VÕITLUS';

  @override
  String get wrappedWinLabelUpper => 'VÕIT';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP FRAASID';

  @override
  String get wrappedYourHeader => 'Sinu';

  @override
  String get wrappedTopDaysHeader => 'Parimad päevad';

  @override
  String get wrappedYourTopDaysBadge => 'Sinu parimad päevad';

  @override
  String get wrappedBestHeader => 'Parimad';

  @override
  String get wrappedMomentsHeader => 'Hetked';

  @override
  String get wrappedBestMomentsBadge => 'Parimad hetked';

  @override
  String get wrappedBiggestHeader => 'Suurim';

  @override
  String get wrappedStruggleHeader => 'Võitlus';

  @override
  String get wrappedWinHeader => 'Võit';

  @override
  String get wrappedButYouPushedThroughEmoji => 'Aga sa said hakkama 💪';

  @override
  String get wrappedYouDidItEmoji => 'Sa tegid seda! 🎉';

  @override
  String get wrappedHours => 'tundi';

  @override
  String get wrappedActions => 'tegevust';

  @override
  String get multipleSpeakersDetected => 'Tuvastati mitu kõnelejat';

  @override
  String get multipleSpeakersDescription =>
      'Tundub, et salvestises on mitu kõnelejat. Veenduge, et olete vaikses kohas ja proovige uuesti.';

  @override
  String get invalidRecordingDetected => 'Tuvastati kehtetu salvestis';

  @override
  String get notEnoughSpeechDescription =>
      'Ei tuvastatud piisavalt kõnet. Palun rääkige rohkem ja proovige uuesti.';

  @override
  String get speechDurationDescription =>
      'Veenduge, et räägite vähemalt 5 sekundit ja mitte rohkem kui 90.';

  @override
  String get connectionLostDescription =>
      'Ühendus katkes. Kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String get howToTakeGoodSample => 'Kuidas teha head proovi?';

  @override
  String get goodSampleInstructions =>
      '1. Veenduge, et olete vaikses kohas.\n2. Rääkige selgelt ja loomulikult.\n3. Veenduge, et teie seade on oma loomulikus asendis kaelal.\n\nKui see on loodud, saate seda alati parandada või uuesti teha.';

  @override
  String get noDeviceConnectedUseMic =>
      'Ühendatud seadet pole. Kasutatakse telefoni mikrofoni.';

  @override
  String get doItAgain => 'Tee uuesti';

  @override
  String get listenToSpeechProfile => 'Kuula minu häälprofiili ➡️';

  @override
  String get recognizingOthers => 'Teiste tuvastamine 👀';

  @override
  String get keepGoingGreat => 'Jätka, sul läheb suurepäraselt';

  @override
  String get somethingWentWrongTryAgain =>
      'Midagi läks valesti! Palun proovi hiljem uuesti.';

  @override
  String get uploadingVoiceProfile => 'Teie hääleprofiili üleslaadimine....';

  @override
  String get memorizingYourVoice => 'Teie hääle meeldejätmine...';

  @override
  String get personalizingExperience => 'Teie kogemuse isikupärastamine...';

  @override
  String get keepSpeakingUntil100 => 'Rääkige edasi, kuni jõuate 100%-ni.';

  @override
  String get greatJobAlmostThere => 'Suurepärane töö, olete peaaegu kohal';

  @override
  String get soCloseJustLittleMore => 'Nii lähedal, veel natuke';

  @override
  String get notificationFrequency => 'Teavituste sagedus';

  @override
  String get controlNotificationFrequency =>
      'Määrake, kui sageli Omi saadab teile ennetavaid teavitusi.';

  @override
  String get yourScore => 'Teie skoor';

  @override
  String get dailyScoreBreakdown => 'Päeva skoori ülevaade';

  @override
  String get todaysScore => 'Tänane skoor';

  @override
  String get tasksCompleted => 'Ülesanded täidetud';

  @override
  String get completionRate => 'Täitmise määr';

  @override
  String get howItWorks => 'Kuidas see töötab';

  @override
  String get dailyScoreExplanation =>
      'Teie päeva skoor põhineb ülesannete täitmisel. Täitke oma ülesanded skoori parandamiseks!';

  @override
  String get notificationFrequencyDescription =>
      'Kontrolli, kui sageli Omi saadab sulle proaktiivseid teavitusi ja meeldetuletusi.';

  @override
  String get sliderOff => 'Väljas';

  @override
  String get sliderMax => 'Maks.';

  @override
  String summaryGeneratedFor(String date) {
    return 'Kokkuvõte genereeritud kuupäevale $date';
  }

  @override
  String get failedToGenerateSummary =>
      'Kokkuvõtte genereerimine ebaõnnestus. Veendu, et sul on vestlusi sellel päeval.';

  @override
  String get recap => 'Kokkuvõte';

  @override
  String deleteQuoted(String name) {
    return 'Kustuta \"$name\"';
  }

  @override
  String moveConversationsTo(int count) {
    return 'Teisalda $count vestlust kausta:';
  }

  @override
  String get noFolder => 'Kausta pole';

  @override
  String get removeFromAllFolders => 'Eemalda kõigist kaustadest';

  @override
  String get buildAndShareYourCustomApp =>
      'Ehita ja jaga oma kohandatud rakendust';

  @override
  String get searchAppsPlaceholder => 'Otsi 1500+ rakendust';

  @override
  String get filters => 'Filtrid';

  @override
  String get frequencyOff => 'Väljas';

  @override
  String get frequencyMinimal => 'Minimaalne';

  @override
  String get frequencyLow => 'Madal';

  @override
  String get frequencyBalanced => 'Tasakaalustatud';

  @override
  String get frequencyHigh => 'Kõrge';

  @override
  String get frequencyMaximum => 'Maksimaalne';

  @override
  String get frequencyDescOff => 'Pole proaktiivseid teateid';

  @override
  String get frequencyDescMinimal => 'Ainult kriitilised meeldetuletused';

  @override
  String get frequencyDescLow => 'Ainult olulised uuendused';

  @override
  String get frequencyDescBalanced => 'Regulaarsed kasulikud meeldetuletused';

  @override
  String get frequencyDescHigh => 'Sagedased kontrollid';

  @override
  String get frequencyDescMaximum => 'Püsi pidevalt kaasatud';

  @override
  String get clearChatQuestion => 'Kustuta vestlus?';

  @override
  String get syncingMessages => 'Sõnumite sünkroonimine serveriga...';

  @override
  String get chatAppsTitle => 'Vestlusrakendused';

  @override
  String get selectApp => 'Vali rakendus';

  @override
  String get noChatAppsEnabled =>
      'Vestlusrakendusi pole lubatud.\nPuudutage rakenduste lisamiseks \"Luba rakendused\".';

  @override
  String get disable => 'Keela';

  @override
  String get photoLibrary => 'Fotokogu';

  @override
  String get chooseFile => 'Vali fail';

  @override
  String get configureAiPersona => 'Seadistage oma AI-persona';

  @override
  String get connectAiAssistantsToYourData =>
      'Ühendage AI-assistendid oma andmetega';

  @override
  String get oAuth => 'OAuth';

  @override
  String get trackYourGoalsOnHomepage =>
      'Jälgi oma isiklikke eesmärke avalehel';

  @override
  String get deleteRecording => 'Kustuta salvestis';

  @override
  String get thisCannotBeUndone => 'Seda ei saa tagasi võtta.';

  @override
  String get sdCard => 'SD-kaart';

  @override
  String get fromSd => 'SD-lt';

  @override
  String get limitless => 'Limitless';

  @override
  String get fastTransfer => 'Kiire edastus';

  @override
  String get syncingStatus => 'Sünkroonimine';

  @override
  String get failedStatus => 'Ebaõnnestunud';

  @override
  String etaLabel(String time) {
    return 'Hinnanguline aeg: $time';
  }

  @override
  String get transferMethod => 'Edastusmeetod';

  @override
  String get fast => 'Kiire';

  @override
  String get ble => 'BLE';

  @override
  String get phone => 'Telefon';

  @override
  String get cancelSync => 'Tühista sünkroonimine';

  @override
  String get cancelSyncMessage =>
      'Juba allalaaditud andmed salvestatakse. Võite hiljem jätkata.';

  @override
  String get syncCancelled => 'Sünkroonimine tühistatud';

  @override
  String get deleteProcessedFiles => 'Kustuta töödeldud failid';

  @override
  String get processedFilesDeleted => 'Töödeldud failid kustutatud';

  @override
  String get wifiEnableFailed =>
      'Seadme WiFi lubamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get deviceNoFastTransfer =>
      'Teie seade ei toeta kiiret ülekannet. Kasutage selle asemel Bluetooth-i.';

  @override
  String get enableHotspotMessage =>
      'Palun lülitage oma telefoni kuumkoht sisse ja proovige uuesti.';

  @override
  String get transferStartFailed =>
      'Ülekande alustamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get deviceNotResponding => 'Seade ei vastanud. Palun proovige uuesti.';

  @override
  String get invalidWifiCredentials =>
      'Vigased WiFi andmed. Kontrollige oma kuumkoha seadeid.';

  @override
  String get wifiConnectionFailed =>
      'WiFi ühendus ebaõnnestus. Palun proovige uuesti.';

  @override
  String get sdCardProcessing => 'SD-kaardi töötlemine';

  @override
  String sdCardProcessingMessage(int count) {
    return 'Töödeldakse $count salvestis(t). Failid eemaldatakse SD-kaardilt pärast töötlemist.';
  }

  @override
  String get process => 'Töötle';

  @override
  String get wifiSyncFailed => 'WiFi sünkroonimine ebaõnnestus';

  @override
  String get processingFailed => 'Töötlemine ebaõnnestus';

  @override
  String get downloadingFromSdCard => 'Allalaadimine SD-kaardilt';

  @override
  String processingProgress(int current, int total) {
    return 'Töötlemine $current/$total';
  }

  @override
  String conversationsCreated(int count) {
    return '$count vestlust loodud';
  }

  @override
  String get internetRequired => 'Internet on vajalik';

  @override
  String get processAudio => 'Töötle heli';

  @override
  String get start => 'Alusta';

  @override
  String get noRecordings => 'Salvestisi pole';

  @override
  String get audioFromOmiWillAppearHere =>
      'Teie Omi seadmest pärinev heli ilmub siia';

  @override
  String get deleteProcessed => 'Kustuta töödeldud';

  @override
  String get tryDifferentFilter => 'Proovige teist filtrit';

  @override
  String get recordings => 'Salvestised';

  @override
  String get enableRemindersAccess =>
      'Apple meeldetuletuste kasutamiseks lubage meeldetuletuste juurdepääs seadetes';

  @override
  String todayAtTime(String time) {
    return 'Täna kell $time';
  }

  @override
  String yesterdayAtTime(String time) {
    return 'Eile kell $time';
  }

  @override
  String get lessThanAMinute => 'Vähem kui minut';

  @override
  String estimatedMinutes(int count) {
    return '~$count minut(it)';
  }

  @override
  String estimatedHours(int count) {
    return '~$count tund(i)';
  }

  @override
  String estimatedTimeRemaining(String time) {
    return 'Hinnanguline: $time jäänud';
  }

  @override
  String get summarizingConversation =>
      'Vestluse kokkuvõtte tegemine...\nSee võib võtta mõne sekundi';

  @override
  String get resummarizingConversation =>
      'Vestluse uuesti kokkuvõtte tegemine...\nSee võib võtta mõne sekundi';

  @override
  String get nothingInterestingRetry =>
      'Midagi huvitavat ei leitud,\nkas soovid uuesti proovida?';

  @override
  String get noSummaryForConversation =>
      'Selle vestluse jaoks\npole kokkuvõtet saadaval.';

  @override
  String get unknownLocation => 'Tundmatu asukoht';

  @override
  String get couldNotLoadMap => 'Kaarti ei õnnestunud laadida';

  @override
  String get triggerConversationIntegration =>
      'Käivita vestluse loomise integratsioon';

  @override
  String get webhookUrlNotSet => 'Webhooki URL pole määratud';

  @override
  String get setWebhookUrlInSettings =>
      'Selle funktsiooni kasutamiseks määra webhooki URL arendaja seadetes.';

  @override
  String get sendWebUrl => 'Saada veebi URL';

  @override
  String get sendTranscript => 'Saada transkriptsioon';

  @override
  String get sendSummary => 'Saada kokkuvõte';

  @override
  String get debugModeDetected => 'Silumisrežiim tuvastatud';

  @override
  String get performanceReduced => 'Jõudlus võib olla vähenenud';

  @override
  String autoClosingInSeconds(int seconds) {
    return 'Automaatne sulgemine $seconds sekundi pärast';
  }

  @override
  String get modelRequired => 'Mudel nõutav';

  @override
  String get downloadWhisperModel =>
      'Laadi alla whisper mudel, et kasutada seadmes transkriptsiooni';

  @override
  String get deviceNotCompatible =>
      'Sinu seade ei ühildu seadmes transkriptsiooniga';

  @override
  String get deviceRequirements =>
      'Teie seade ei vasta seadmesisese transkriptsiooni nõuetele.';

  @override
  String get willLikelyCrash =>
      'Selle lubamine põhjustab tõenäoliselt rakenduse krahhi või hangumise.';

  @override
  String get transcriptionSlowerLessAccurate =>
      'Transkriptsioon on oluliselt aeglasem ja vähem täpne.';

  @override
  String get proceedAnyway => 'Jätka siiski';

  @override
  String get olderDeviceDetected => 'Tuvastati vanem seade';

  @override
  String get onDeviceSlower =>
      'Seadmesisene transkriptsioon võib sellel seadmel olla aeglasem.';

  @override
  String get batteryUsageHigher =>
      'Akukasutus on suurem kui pilves transkriptsiooni puhul.';

  @override
  String get considerOmiCloud =>
      'Kaaluge parema jõudluse saavutamiseks Omi Cloudi kasutamist.';

  @override
  String get highResourceUsage => 'Suur ressursikasutus';

  @override
  String get onDeviceIntensive =>
      'Seadmesisene transkriptsioon on arvutuslikult intensiivne.';

  @override
  String get batteryDrainIncrease => 'Aku tarbimine suureneb märkimisväärselt.';

  @override
  String get deviceMayWarmUp =>
      'Seade võib pikaajalisel kasutamisel soojeneda.';

  @override
  String get speedAccuracyLower =>
      'Kiirus ja täpsus võivad olla pilvemudeli omadest madalamad.';

  @override
  String get cloudProvider => 'Pilveteenuse pakkuja';

  @override
  String get premiumMinutesInfo =>
      '1200 premium minutit kuus. Seadmesisene vahekaart pakub piiramatut tasuta transkriptsiooni.';

  @override
  String get viewUsage => 'Vaata kasutust';

  @override
  String get localProcessingInfo =>
      'Heli töödeldakse kohapeal. Töötab võrguühenduseta, on privaatsem, kuid kasutab rohkem akut.';

  @override
  String get model => 'Mudel';

  @override
  String get performanceWarning => 'Jõudluse hoiatus';

  @override
  String get largeModelWarning =>
      'See mudel on suur ja võib põhjustada rakenduse krahhi või väga aeglase töö mobiilseadmetes.\n\nSoovitatav on kasutada \"small\" või \"base\" mudelit.';

  @override
  String get usingNativeIosSpeech =>
      'Kasutatakse iOS-i natiivset kõnetuvastust';

  @override
  String get noModelDownloadRequired =>
      'Kasutatakse teie seadme algset kõnemootorit. Mudeli allalaadimine pole vajalik.';

  @override
  String get modelReady => 'Mudel on valmis';

  @override
  String get redownload => 'Laadi uuesti alla';

  @override
  String get doNotCloseApp => 'Palun ärge sulgege rakendust.';

  @override
  String get downloading => 'Allalaadimine...';

  @override
  String get downloadModel => 'Laadi mudel alla';

  @override
  String estimatedSize(String size) {
    return 'Hinnanguline suurus: ~$size MB';
  }

  @override
  String availableSpace(String space) {
    return 'Saadaval ruumi: $space';
  }

  @override
  String get notEnoughSpace => 'Hoiatus: Pole piisavalt ruumi!';

  @override
  String get download => 'Laadi alla';

  @override
  String downloadError(String error) {
    return 'Allalaadimise viga: $error';
  }

  @override
  String get cancelled => 'Tühistatud';

  @override
  String get deviceNotCompatibleTitle => 'Seade ei ühildu';

  @override
  String get deviceNotMeetRequirements =>
      'Teie seade ei vasta seadmes transkriptsiooni nõuetele.';

  @override
  String get transcriptionSlowerOnDevice =>
      'Seadmes transkriptsioon võib sellel seadmel olla aeglasem.';

  @override
  String get computationallyIntensive =>
      'Seadmes transkriptsioon on arvutuslikult intensiivne.';

  @override
  String get batteryDrainSignificantly =>
      'Aku tühjenemine suureneb märkimisväärselt.';

  @override
  String get premiumMinutesMonth =>
      '1200 premium minutit/kuus. Seadmes vahekaart pakub piiramatut tasuta transkriptsiooni. ';

  @override
  String get audioProcessedLocally =>
      'Heli töödeldakse kohapeal. Töötab võrguühenduseta, privaatsem, kuid kasutab rohkem akut.';

  @override
  String get languageLabel => 'Keel';

  @override
  String get modelLabel => 'Mudel';

  @override
  String get modelTooLargeWarning =>
      'See mudel on suur ja võib põhjustada rakenduse krahhi või väga aeglase töö mobiilseadmetes.\n\nSoovitatav on small või base.';

  @override
  String get nativeEngineNoDownload =>
      'Kasutatakse teie seadme natiivset kõnemootorit. Mudeli allalaadimine pole vajalik.';

  @override
  String modelReadyWithName(String model) {
    return 'Mudel valmis ($model)';
  }

  @override
  String get reDownload => 'Laadi uuesti alla';

  @override
  String downloadingModelProgress(String model, String received, String total) {
    return 'Laadin alla $model: $received / $total MB';
  }

  @override
  String preparingModel(String model) {
    return 'Valmistan ette $model...';
  }

  @override
  String downloadErrorWithMessage(String error) {
    return 'Allalaadimise viga: $error';
  }

  @override
  String estimatedSizeWithValue(String size) {
    return 'Eeldatav suurus: ~$size MB';
  }

  @override
  String availableSpaceWithValue(String space) {
    return 'Saadaolev ruum: $space';
  }

  @override
  String get omiTranscriptionOptimized =>
      'Omi sisseehitatud reaalajas transkriptsioon on optimeeritud reaalajas vestluste jaoks automaatse kõneleja tuvastamise ja diariseerimisega.';

  @override
  String get reset => 'Lähtesta';

  @override
  String get useTemplateFrom => 'Kasuta malli allikast';

  @override
  String get selectProviderTemplate => 'Valige teenusepakkuja mall...';

  @override
  String get quicklyPopulateResponse =>
      'Täida kiiresti tuntud teenusepakkuja vastuse vorminguga';

  @override
  String get quicklyPopulateRequest =>
      'Täida kiiresti tuntud teenusepakkuja päringu vorminguga';

  @override
  String get invalidJsonError => 'Vigane JSON';

  @override
  String downloadModelWithName(String model) {
    return 'Laadi mudel alla ($model)';
  }

  @override
  String modelNameWithFile(String model) {
    return 'Mudel: $model';
  }

  @override
  String get device => 'Seade';

  @override
  String get chatAssistantsTitle => 'Vestlusassistendid';

  @override
  String get permissionReadConversations => 'Loe vestlusi';

  @override
  String get permissionReadMemories => 'Loe mälestusi';

  @override
  String get permissionReadTasks => 'Loe ülesandeid';

  @override
  String get permissionCreateConversations => 'Loo vestlusi';

  @override
  String get permissionCreateMemories => 'Loo mälestusi';

  @override
  String get permissionTypeAccess => 'Juurdepääs';

  @override
  String get permissionTypeCreate => 'Loo';

  @override
  String get permissionTypeTrigger => 'Päästik';

  @override
  String get permissionDescReadConversations =>
      'See rakendus pääseb ligi sinu vestlustele.';

  @override
  String get permissionDescReadMemories =>
      'See rakendus pääseb ligi sinu mälestustele.';

  @override
  String get permissionDescReadTasks =>
      'See rakendus pääseb ligi sinu ülesannetele.';

  @override
  String get permissionDescCreateConversations =>
      'See rakendus saab luua uusi vestlusi.';

  @override
  String get permissionDescCreateMemories =>
      'See rakendus saab luua uusi mälestusi.';

  @override
  String get realtimeListening => 'Reaalajas kuulamine';

  @override
  String get setupCompleted => 'Lõpetatud';

  @override
  String get pleaseSelectRating => 'Palun vali hinnang';

  @override
  String get writeReviewOptional => 'Kirjuta arvustus (valikuline)';

  @override
  String get setupQuestionsIntro =>
      'Aidake meil Omit paremaks muuta, vastates mõnele küsimusele. 🫶 💜';

  @override
  String get setupQuestionProfession => '1. Mis on teie amet?';

  @override
  String get setupQuestionUsage => '2. Kus plaanite oma Omit kasutada?';

  @override
  String get setupQuestionAge => '3. Mis on teie vanuserühm?';

  @override
  String get setupAnswerAllQuestions =>
      'Te pole veel kõikidele küsimustele vastanud! 🥺';

  @override
  String get setupSkipHelp => 'Jäta vahele, ma ei soovi aidata :C';

  @override
  String get professionEntrepreneur => 'Ettevõtja';

  @override
  String get professionSoftwareEngineer => 'Tarkvaraarendaja';

  @override
  String get professionProductManager => 'Tootejuht';

  @override
  String get professionExecutive => 'Juht';

  @override
  String get professionSales => 'Müük';

  @override
  String get professionStudent => 'Tudeng';

  @override
  String get usageAtWork => 'Tööl';

  @override
  String get usageIrlEvents => 'Päriselus üritustel';

  @override
  String get usageOnline => 'Internetis';

  @override
  String get usageSocialSettings => 'Sotsiaalsetes olukordades';

  @override
  String get usageEverywhere => 'Kõikjal';

  @override
  String get customBackendUrlTitle => 'Kohandatud serveri URL';

  @override
  String get backendUrlLabel => 'Serveri URL';

  @override
  String get saveUrlButton => 'Salvesta URL';

  @override
  String get enterBackendUrlError => 'Palun sisestage serveri URL';

  @override
  String get urlMustEndWithSlashError => 'URL peab lõppema \"/\"';

  @override
  String get invalidUrlError => 'Palun sisestage kehtiv URL';

  @override
  String get backendUrlSavedSuccess => 'Serveri URL salvestatud!';

  @override
  String get signInTitle => 'Logi sisse';

  @override
  String get signInButton => 'Logi sisse';

  @override
  String get enterEmailError => 'Palun sisestage oma e-post';

  @override
  String get invalidEmailError => 'Palun sisestage kehtiv e-post';

  @override
  String get enterPasswordError => 'Palun sisestage oma parool';

  @override
  String get passwordMinLengthError => 'Parool peab olema vähemalt 8 tähemärki';

  @override
  String get signInSuccess => 'Sisselogimine õnnestus!';

  @override
  String get alreadyHaveAccountLogin => 'Kas teil on juba konto? Logige sisse';

  @override
  String get emailLabel => 'E-post';

  @override
  String get passwordLabel => 'Parool';

  @override
  String get createAccountTitle => 'Loo konto';

  @override
  String get nameLabel => 'Nimi';

  @override
  String get repeatPasswordLabel => 'Korda parooli';

  @override
  String get signUpButton => 'Registreeru';

  @override
  String get enterNameError => 'Palun sisestage oma nimi';

  @override
  String get passwordsDoNotMatch => 'Paroolid ei kattu';

  @override
  String get signUpSuccess => 'Registreerimine õnnestus!';

  @override
  String get loadingKnowledgeGraph => 'Teadmisgraafiku laadimine...';

  @override
  String get noKnowledgeGraphYet => 'Teadmisgraafikut pole veel';

  @override
  String get buildingKnowledgeGraphFromMemories =>
      'Teadmisgraafiku loomine mälestustest...';

  @override
  String get knowledgeGraphWillBuildAutomatically =>
      'Teie teadmisgraafik luuakse automaatselt, kui loote uusi mälestusi.';

  @override
  String get buildGraphButton => 'Loo graafik';

  @override
  String get checkOutMyMemoryGraph => 'Vaata minu mälugraafikut!';

  @override
  String get getButton => 'Hangi';

  @override
  String openingApp(String appName) {
    return 'Avan $appName...';
  }

  @override
  String get writeSomething => 'Kirjuta midagi';

  @override
  String get submitReply => 'Saada vastus';

  @override
  String get editYourReply => 'Muuda vastust';

  @override
  String get replyToReview => 'Vasta arvustusele';

  @override
  String get rateAndReviewThisApp => 'Hinda ja arvusta seda rakendust';

  @override
  String get noChangesInReview => 'Arvustuses pole muudatusi uuendamiseks.';

  @override
  String get cantRateWithoutInternet =>
      'Ei saa rakendust hinnata ilma internetiühenduseta.';

  @override
  String get appAnalytics => 'Rakenduse analüütika';

  @override
  String get learnMoreLink => 'lisateave';

  @override
  String get moneyEarned => 'Teenitud raha';

  @override
  String get writeYourReply => 'Kirjuta oma vastus...';

  @override
  String get replySentSuccessfully => 'Vastus saadeti edukalt';

  @override
  String failedToSendReply(String error) {
    return 'Vastuse saatmine ebaõnnestus: $error';
  }

  @override
  String get send => 'Saada';

  @override
  String starFilter(int count) {
    return '$count tärni';
  }

  @override
  String get noReviewsFound => 'Arvustusi ei leitud';

  @override
  String get editReply => 'Muuda vastust';

  @override
  String get reply => 'Vasta';

  @override
  String starFilterLabel(int count) {
    return '$count tärn';
  }

  @override
  String get sharePublicLink => 'Jaga avalikku linki';

  @override
  String get makePersonaPublic => 'Tee persona avalikuks';

  @override
  String get connectedKnowledgeData => 'Ühendatud teadmiste andmed';

  @override
  String get enterName => 'Sisesta nimi';

  @override
  String get disconnectTwitter => 'Katkesta Twitteri ühendus';

  @override
  String get disconnectTwitterConfirmation =>
      'Kas olete kindel, et soovite oma Twitteri konto ühenduse katkestada? Teie persona ei kasuta enam seda.';

  @override
  String get getOmiDeviceDescription =>
      'Looge täpsem kloon oma isiklike vestluste põhjal';

  @override
  String get getOmi => 'Hangi Omi';

  @override
  String get iHaveOmiDevice => 'Mul on Omi seade';

  @override
  String get goal => 'EESMÄRK';

  @override
  String get tapToTrackThisGoal => 'Puudutage selle eesmärgi jälgimiseks';

  @override
  String get tapToSetAGoal => 'Puudutage eesmärgi seadmiseks';

  @override
  String get processedConversations => 'Töödeldud vestlused';

  @override
  String get updatedConversations => 'Uuendatud vestlused';

  @override
  String get newConversations => 'Uued vestlused';

  @override
  String get summaryTemplate => 'Kokkuvõtte mall';

  @override
  String get suggestedTemplates => 'Soovitatud mallid';

  @override
  String get otherTemplates => 'Muud mallid';

  @override
  String get availableTemplates => 'Saadaolevad mallid';

  @override
  String get getCreative => 'Ole loov';

  @override
  String get defaultLabel => 'Vaikimisi';

  @override
  String get lastUsedLabel => 'Viimati kasutatud';

  @override
  String get setDefaultApp => 'Määra vaikerakendus';

  @override
  String setDefaultAppContent(String appName) {
    return 'Kas määrata $appName vaikimisi kokkuvõtte rakenduseks?\\n\\nSeda rakendust kasutatakse automaatselt kõigi tulevaste vestluste kokkuvõtete jaoks.';
  }

  @override
  String get setDefaultButton => 'Määra vaikimisi';

  @override
  String setAsDefaultSuccess(String appName) {
    return '$appName määratud vaikimisi kokkuvõtte rakenduseks';
  }

  @override
  String get createCustomTemplate => 'Loo kohandatud mall';

  @override
  String get allTemplates => 'Kõik mallid';

  @override
  String failedToInstallApp(String appName) {
    return '$appName installimine ebaõnnestus. Palun proovi uuesti.';
  }

  @override
  String errorInstallingApp(String appName, String error) {
    return 'Viga $appName installimisel: $error';
  }

  @override
  String tagSpeaker(int speakerId) {
    return 'Märgi kõneleja $speakerId';
  }

  @override
  String get personNameAlreadyExists => 'Selle nimega isik on juba olemas.';

  @override
  String get selectYouFromList =>
      'Enda märkimiseks valige nimekirjast \"Sina\".';

  @override
  String get enterPersonsName => 'Sisesta isiku nimi';

  @override
  String get addPerson => 'Lisa isik';

  @override
  String tagOtherSegmentsFromSpeaker(int selected, int total) {
    return 'Märgi teised segmendid sellelt kõnelejalt ($selected/$total)';
  }

  @override
  String get tagOtherSegments => 'Märgi teised segmendid';

  @override
  String get managePeople => 'Halda inimesi';

  @override
  String get shareViaSms => 'Jaga SMS-i kaudu';

  @override
  String get selectContactsToShareSummary =>
      'Vali kontaktid vestluse kokkuvõtte jagamiseks';

  @override
  String get searchContactsHint => 'Otsi kontakte...';

  @override
  String contactsSelectedCount(int count) {
    return '$count valitud';
  }

  @override
  String get clearAllSelection => 'Tühista kõik';

  @override
  String get selectContactsToShare => 'Vali kontaktid jagamiseks';

  @override
  String shareWithContactCount(int count) {
    return 'Jaga $count kontaktiga';
  }

  @override
  String shareWithContactsCount(int count) {
    return 'Jaga $count kontaktiga';
  }

  @override
  String get contactsPermissionRequired => 'Nõutav kontaktide luba';

  @override
  String get contactsPermissionRequiredForSms =>
      'SMS-i kaudu jagamiseks on vajalik kontaktide luba';

  @override
  String get grantContactsPermissionForSms =>
      'SMS-i kaudu jagamiseks andke palun kontaktide luba';

  @override
  String get noContactsWithPhoneNumbers =>
      'Telefoninumbritega kontakte ei leitud';

  @override
  String get noContactsMatchSearch => 'Ükski kontakt ei vasta teie otsingule';

  @override
  String get failedToLoadContacts => 'Kontaktide laadimine ebaõnnestus';

  @override
  String get failedToPrepareConversationForSharing =>
      'Vestluse jagamiseks ettevalmistamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get couldNotOpenSmsApp =>
      'SMS-i rakendust ei saanud avada. Palun proovige uuesti.';

  @override
  String heresWhatWeDiscussed(String link) {
    return 'Siin on see, millest me just rääkisime: $link';
  }

  @override
  String get wifiSync => 'WiFi sünkroonimine';

  @override
  String itemCopiedToClipboard(String item) {
    return '$item kopeeritud lõikelauale';
  }

  @override
  String get wifiConnectionFailedTitle => 'Ühendus ebaõnnestus';

  @override
  String connectingToDeviceName(String deviceName) {
    return 'Ühendamine seadmega $deviceName';
  }

  @override
  String enableDeviceWifi(String deviceName) {
    return 'Luba $deviceName WiFi';
  }

  @override
  String connectToDeviceName(String deviceName) {
    return 'Ühenda seadmega $deviceName';
  }

  @override
  String get recordingDetails => 'Salvestise üksikasjad';

  @override
  String get storageLocationSdCard => 'SD-kaart';

  @override
  String get storageLocationLimitlessPendant => 'Limitless ripats';

  @override
  String get storageLocationPhone => 'Telefon';

  @override
  String get storageLocationPhoneMemory => 'Telefon (mälu)';

  @override
  String storedOnDevice(String deviceName) {
    return 'Salvestatud seadmesse $deviceName';
  }

  @override
  String get transferring => 'Ülekandmine...';

  @override
  String get transferRequired => 'Ülekanne vajalik';

  @override
  String get downloadingAudioFromSdCard =>
      'Heli allalaadimine seadme SD-kaardilt';

  @override
  String get transferRequiredDescription =>
      'See salvestis on salvestatud teie seadme SD-kaardile. Kandke see oma telefoni, et seda esitada.';

  @override
  String get cancelTransfer => 'Tühista ülekanne';

  @override
  String get transferToPhone => 'Kanna telefoni';

  @override
  String get privateAndSecureOnDevice => 'Privaatne ja turvaline teie seadmes';

  @override
  String get recordingInfo => 'Salvestise teave';

  @override
  String get transferInProgress => 'Ülekanne käib...';

  @override
  String get shareRecording => 'Jaga salvestist';

  @override
  String get deleteRecordingConfirmation =>
      'Kas olete kindel, et soovite selle salvestise jäädavalt kustutada? Seda ei saa tagasi võtta.';

  @override
  String get recordingIdLabel => 'Salvestise ID';

  @override
  String get dateTimeLabel => 'Kuupäev ja kellaaeg';

  @override
  String get durationLabel => 'Kestus';

  @override
  String get audioFormatLabel => 'Helivorming';

  @override
  String get storageLocationLabel => 'Salvestuskoht';

  @override
  String get estimatedSizeLabel => 'Eeldatav suurus';

  @override
  String get deviceModelLabel => 'Seadme mudel';

  @override
  String get deviceIdLabel => 'Seadme ID';

  @override
  String get statusLabel => 'Olek';

  @override
  String get statusProcessed => 'Töödeldud';

  @override
  String get statusUnprocessed => 'Töötlemata';

  @override
  String get switchedToFastTransfer => 'Lülitatud kiirele ülekandele';

  @override
  String get transferCompleteMessage =>
      'Ülekanne lõpetatud! Nüüd saate seda salvestist esitada.';

  @override
  String transferFailedMessage(String error) {
    return 'Ülekanne ebaõnnestus: $error';
  }

  @override
  String get transferCancelled => 'Ülekanne tühistatud';

  @override
  String get fastTransferEnabled => 'Kiire edastus lubatud';

  @override
  String get bluetoothSyncEnabled => 'Bluetoothi sünkroonimine lubatud';

  @override
  String get enableFastTransfer => 'Luba kiire edastus';

  @override
  String get fastTransferDescription =>
      'Kiire edastus kasutab WiFi-d ~5x kiiremate kiiruste jaoks. Teie telefon ühendub ajutiselt edastuse ajal Omi seadme WiFi-võrguga.';

  @override
  String get internetAccessPausedDuringTransfer =>
      'Interneti-juurdepääs on edastuse ajal peatatud';

  @override
  String get chooseTransferMethodDescription =>
      'Valige, kuidas salvestised edastatakse Omi seadmest telefoni.';

  @override
  String get wifiSpeed => '~150 KB/s WiFi kaudu';

  @override
  String get fiveTimesFaster => '5X KIIREM';

  @override
  String get fastTransferMethodDescription =>
      'Loob otseühenduse WiFi kaudu Omi seadmega. Teie telefon katkestab ajutiselt ühenduse tavalise WiFi-ga edastuse ajal.';

  @override
  String get bluetooth => 'Bluetooth';

  @override
  String get bleSpeed => '~30 KB/s BLE kaudu';

  @override
  String get bluetoothMethodDescription =>
      'Kasutab standardset Bluetooth Low Energy ühendust. Aeglasem, kuid ei mõjuta WiFi-ühendust.';

  @override
  String get selected => 'Valitud';

  @override
  String get selectOption => 'Vali';

  @override
  String get lowBatteryAlertTitle => 'Tühja aku hoiatus';

  @override
  String get lowBatteryAlertBody => 'Teie seadme aku on tühi. Aeg laadida! 🔋';

  @override
  String get deviceDisconnectedNotificationTitle =>
      'Teie Omi seade on lahti ühendatud';

  @override
  String get deviceDisconnectedNotificationBody =>
      'Palun ühendage uuesti, et jätkata Omi kasutamist.';

  @override
  String get firmwareUpdateAvailable => 'Püsivara värskendus saadaval';

  @override
  String firmwareUpdateAvailableDescription(String version) {
    return 'Teie Omi seadme jaoks on saadaval uus püsivara värskendus ($version). Kas soovite kohe värskendada?';
  }

  @override
  String get later => 'Hiljem';

  @override
  String get appDeletedSuccessfully => 'Rakendus kustutati edukalt';

  @override
  String get appDeleteFailed =>
      'Rakenduse kustutamine ebaõnnestus. Palun proovi hiljem uuesti.';

  @override
  String get appVisibilityChangedSuccessfully =>
      'Rakenduse nähtavus muudeti edukalt. Muudatuse kajastumine võib võtta mõne minuti.';

  @override
  String get errorActivatingAppIntegration =>
      'Viga rakenduse aktiveerimisel. Kui see on integratsioonirakendus, veendu, et seadistus on lõpule viidud.';

  @override
  String get errorUpdatingAppStatus =>
      'Rakenduse oleku uuendamisel ilmnes viga.';

  @override
  String get calculatingETA => 'Arvutamine...';

  @override
  String aboutMinutesRemaining(int minutes) {
    return 'Umbes $minutes minutit jäänud';
  }

  @override
  String get aboutAMinuteRemaining => 'Umbes minut jäänud';

  @override
  String get almostDone => 'Peaaegu valmis...';

  @override
  String get omiSays => 'omi ütleb';

  @override
  String get analyzingYourData => 'Teie andmete analüüsimine...';

  @override
  String migratingToProtection(String level) {
    return '$level kaitsele migreerimine...';
  }

  @override
  String get noDataToMigrateFinalizing =>
      'Andmeid migreerida pole. Lõpetamine...';

  @override
  String migratingItemsProgress(String itemType, int percentage) {
    return '$itemType migreerimine... $percentage%';
  }

  @override
  String get allObjectsMigratedFinalizing =>
      'Kõik objektid migreeritud. Lõpetamine...';

  @override
  String get migrationErrorOccurred =>
      'Migreerimise ajal tekkis viga. Palun proovige uuesti.';

  @override
  String get migrationComplete => 'Migratsioon lõpetatud!';

  @override
  String dataProtectedWithSettings(String level) {
    return 'Teie andmed on nüüd kaitstud uute $level seadistustega.';
  }

  @override
  String get chatsLowercase => 'vestlused';

  @override
  String get dataLowercase => 'andmed';

  @override
  String get fallNotificationTitle => 'Oih';

  @override
  String get fallNotificationBody => 'Kas te kukkusite?';

  @override
  String get importantConversationTitle => 'Oluline vestlus';

  @override
  String get importantConversationBody =>
      'Teil oli just oluline vestlus. Puudutage kokkuvõtte jagamiseks.';

  @override
  String get templateName => 'Malli nimi';

  @override
  String get templateNameHint => 'nt. Koosoleku tegevuspunktide ekstraktor';

  @override
  String get nameMustBeAtLeast3Characters =>
      'Nimi peab olema vähemalt 3 tähemärki';

  @override
  String get conversationPromptHint =>
      'nt Eraldage tegevuspunktid, otsused ja põhipunktid vestlusest.';

  @override
  String get pleaseEnterAppPrompt => 'Palun sisestage oma rakenduse viip';

  @override
  String get promptMustBeAtLeast10Characters =>
      'Viip peab olema vähemalt 10 tähemärki';

  @override
  String get anyoneCanDiscoverTemplate => 'Igaüks saab teie malli avastada';

  @override
  String get onlyYouCanUseTemplate => 'Ainult teie saate seda malli kasutada';

  @override
  String get generatingDescription => 'Kirjelduse genereerimine...';

  @override
  String get creatingAppIcon => 'Rakenduse ikooni loomine...';

  @override
  String get installingApp => 'Rakenduse installimine...';

  @override
  String get appCreatedAndInstalled => 'Rakendus loodud ja installitud!';

  @override
  String get appCreatedSuccessfully => 'Rakendus edukalt loodud!';

  @override
  String get failedToCreateApp =>
      'Rakenduse loomine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get addAppSelectCoreCapability =>
      'Valige veel üks põhivõime oma rakenduse jaoks';

  @override
  String get addAppSelectPaymentPlan =>
      'Valige maksepakett ja sisestage oma rakenduse hind';

  @override
  String get addAppSelectCapability =>
      'Valige oma rakenduse jaoks vähemalt üks võime';

  @override
  String get addAppSelectLogo => 'Valige oma rakenduse jaoks logo';

  @override
  String get addAppEnterChatPrompt =>
      'Sisestage vestluse viip oma rakenduse jaoks';

  @override
  String get addAppEnterConversationPrompt =>
      'Sisestage vestluse viip oma rakenduse jaoks';

  @override
  String get addAppSelectTriggerEvent =>
      'Valige oma rakenduse jaoks käivitussündmus';

  @override
  String get addAppEnterWebhookUrl =>
      'Sisestage webhook URL oma rakenduse jaoks';

  @override
  String get addAppSelectCategory => 'Valige oma rakenduse jaoks kategooria';

  @override
  String get addAppFillRequiredFields =>
      'Täitke kõik kohustuslikud väljad õigesti';

  @override
  String get addAppUpdatedSuccess => 'Rakendus edukalt värskendatud 🚀';

  @override
  String get addAppUpdateFailed =>
      'Värskendamine ebaõnnestus. Proovige hiljem uuesti';

  @override
  String get addAppSubmittedSuccess => 'Rakendus edukalt esitatud 🚀';

  @override
  String addAppErrorOpeningFilePicker(String message) {
    return 'Viga failivalija avamisel: $message';
  }

  @override
  String addAppErrorSelectingImage(String error) {
    return 'Viga pildi valimisel: $error';
  }

  @override
  String get addAppPhotosPermissionDenied =>
      'Fotode luba keelatud. Lubage juurdepääs fotodele';

  @override
  String get addAppErrorSelectingImageRetry =>
      'Viga pildi valimisel. Proovige uuesti.';

  @override
  String addAppErrorSelectingThumbnail(String error) {
    return 'Viga pisipildi valimisel: $error';
  }

  @override
  String get addAppErrorSelectingThumbnailRetry =>
      'Viga pisipildi valimisel. Proovige uuesti.';

  @override
  String get addAppCapabilityConflictWithPersona =>
      'Teisi võimeid ei saa Personaga valida';

  @override
  String get addAppPersonaConflictWithCapabilities =>
      'Personat ei saa teiste võimetega valida';

  @override
  String get personaTwitterHandleNotFound => 'Twitteri kontot ei leitud';

  @override
  String get personaTwitterHandleSuspended => 'Twitteri konto on peatatud';

  @override
  String get personaFailedToVerifyTwitter =>
      'Twitteri konto kinnitamine ebaõnnestus';

  @override
  String get personaFailedToFetch => 'Teie persona toomine ebaõnnestus';

  @override
  String get personaFailedToCreate => 'Persona loomine ebaõnnestus';

  @override
  String get personaConnectKnowledgeSource =>
      'Ühendage vähemalt üks andmeallikas (Omi või Twitter)';

  @override
  String get personaUpdatedSuccessfully => 'Persona edukalt värskendatud';

  @override
  String get personaFailedToUpdate => 'Persona värskendamine ebaõnnestus';

  @override
  String get personaPleaseSelectImage => 'Valige pilt';

  @override
  String get personaFailedToCreateTryLater =>
      'Persona loomine ebaõnnestus. Proovige hiljem uuesti.';

  @override
  String personaFailedToCreateWithError(String error) {
    return 'Persona loomine ebaõnnestus: $error';
  }

  @override
  String get personaFailedToEnable => 'Persona lubamine ebaõnnestus';

  @override
  String personaErrorEnablingWithError(String error) {
    return 'Viga persona lubamisel: $error';
  }

  @override
  String get paymentFailedToFetchCountries =>
      'Toetatud riikide toomine ebaõnnestus. Proovige hiljem uuesti.';

  @override
  String get paymentFailedToSetDefault =>
      'Vaikimisi makseviisi määramine ebaõnnestus. Proovige hiljem uuesti.';

  @override
  String get paymentFailedToSavePaypal =>
      'PayPali andmete salvestamine ebaõnnestus. Proovige hiljem uuesti.';

  @override
  String get paypalEmailHint => 'nik@example.com';

  @override
  String get paypalMeLinkHint => 'paypal.me/nik';

  @override
  String get paymentMethodStripe => 'Stripe';

  @override
  String get paymentMethodPayPal => 'PayPal';

  @override
  String get paymentStatusActive => 'Aktiivne';

  @override
  String get paymentStatusConnected => 'Ühendatud';

  @override
  String get paymentStatusNotConnected => 'Pole ühendatud';

  @override
  String get paymentAppCost => 'Rakenduse hind';

  @override
  String get paymentEnterValidAmount => 'Sisestage kehtiv summa';

  @override
  String get paymentEnterAmountGreaterThanZero =>
      'Sisestage summa, mis on suurem kui 0';

  @override
  String get paymentPlan => 'Maksepakett';

  @override
  String get paymentNoneSelected => 'Midagi pole valitud';

  @override
  String get aiGenPleaseEnterDescription =>
      'Palun sisesta oma rakenduse kirjeldus';

  @override
  String get aiGenCreatingAppIcon => 'Rakenduse ikooni loomine...';

  @override
  String aiGenErrorOccurredWithDetails(String message) {
    return 'Tekkis viga: $message';
  }

  @override
  String get aiGenAppCreatedSuccessfully => 'Rakendus edukalt loodud!';

  @override
  String get aiGenFailedToCreateApp => 'Rakenduse loomine ebaõnnestus';

  @override
  String get aiGenErrorWhileCreatingApp => 'Rakenduse loomisel tekkis viga';

  @override
  String get aiGenFailedToGenerateApp =>
      'Rakenduse genereerimine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get aiGenFailedToRegenerateIcon =>
      'Ikooni uuesti genereerimine ebaõnnestus';

  @override
  String get aiGenPleaseGenerateAppFirst =>
      'Palun genereeri kõigepealt rakendus';

  @override
  String get xHandleTitle => 'Mis on teie X kasutajanimi?';

  @override
  String get xHandleDescription =>
      'Me eelkoolitame teie Omi klooni\nteie konto tegevuse põhjal';

  @override
  String get xHandleHint => '@nikshevchenko';

  @override
  String get xHandlePleaseEnter => 'Palun sisestage oma X kasutajanimi';

  @override
  String get xHandlePleaseEnterValid => 'Palun sisestage kehtiv X kasutajanimi';

  @override
  String get nextButton => 'Järgmine';

  @override
  String get connectOmiDevice => 'Ühenda Omi seade';

  @override
  String planSwitchingDescriptionWithTitle(String title) {
    return 'Te lähete üle oma Unlimited paketilt $title paketile. Kas olete kindel, et soovite jätkata?';
  }

  @override
  String get planUpgradeScheduledMessage =>
      'Uuendamine on ajastatud! Teie kuupakett jätkub arveldusperioodi lõpuni.';

  @override
  String get couldNotSchedulePlanChange =>
      'Paketi muutmist ei õnnestunud ajastada. Palun proovige uuesti.';

  @override
  String get subscriptionReactivatedDefault =>
      'Teie tellimus on taastatud! Praegu tasu ei võeta - arve esitatakse järgmisel arveldusperioodil.';

  @override
  String get subscriptionSuccessfulCharged =>
      'Tellimus õnnestus! Teilt on uue arveldusperioodi eest tasu võetud.';

  @override
  String get couldNotProcessSubscription =>
      'Tellimust ei õnnestunud töödelda. Palun proovige uuesti.';

  @override
  String get couldNotLaunchUpgradePage =>
      'Uuenduse lehte ei õnnestunud avada. Palun proovige uuesti.';

  @override
  String get transcriptionJsonPlaceholder =>
      'Kleepige oma JSON konfiguratsioon siia...';

  @override
  String get transcriptionSourceOmi => 'Omi';

  @override
  String get pricePlaceholder => '0.00';

  @override
  String importErrorOpeningFilePicker(String message) {
    return 'Viga failivalija avamisel: $message';
  }

  @override
  String importErrorGeneric(String error) {
    return 'Viga: $error';
  }

  @override
  String get mergeConversationsSuccessTitle => 'Vestlused ühendati edukalt';

  @override
  String mergeConversationsSuccessBody(int count) {
    return '$count vestlust ühendati edukalt';
  }

  @override
  String get dailyReflectionNotificationTitle =>
      'Aeg igapäevaseks refleksiooniks';

  @override
  String get dailyReflectionNotificationBody => 'Räägi mulle oma päevast';

  @override
  String get actionItemReminderTitle => 'Omi meeldetuletus';

  @override
  String deviceDisconnectedTitle(String deviceName) {
    return '$deviceName ühendus katkestatud';
  }

  @override
  String deviceDisconnectedBody(String deviceName) {
    return 'Palun ühenda uuesti, et jätkata oma $deviceName kasutamist.';
  }

  @override
  String get onboardingSignIn => 'Logi sisse';

  @override
  String get onboardingYourName => 'Sinu nimi';

  @override
  String get onboardingLanguage => 'Keel';

  @override
  String get onboardingPermissions => 'Õigused';

  @override
  String get onboardingComplete => 'Valmis';

  @override
  String get onboardingWelcomeToOmi => 'Tere tulemast Omi-sse';

  @override
  String get onboardingTellUsAboutYourself => 'Räägi meile endast';

  @override
  String get onboardingChooseYourPreference => 'Vali oma eelistus';

  @override
  String get onboardingGrantRequiredAccess => 'Anna nõutav juurdepääs';

  @override
  String get onboardingYoureAllSet => 'Kõik on valmis';

  @override
  String get searchTranscriptOrSummary =>
      'Otsi transkriptsioonist või kokkuvõttest...';

  @override
  String get myGoal => 'Minu eesmärk';

  @override
  String get appNotAvailable =>
      'Oih! Tundub, et otsitav rakendus pole saadaval.';

  @override
  String get failedToConnectTodoist => 'Todoistiga ühendamine ebaõnnestus';

  @override
  String get failedToConnectAsana => 'Asanaga ühendamine ebaõnnestus';

  @override
  String get failedToConnectGoogleTasks =>
      'Google Tasksiga ühendamine ebaõnnestus';

  @override
  String get failedToConnectClickUp => 'ClickUpiga ühendamine ebaõnnestus';

  @override
  String failedToConnectServiceWithError(String serviceName, String error) {
    return '$serviceName ühendamine ebaõnnestus: $error';
  }

  @override
  String get successfullyConnectedTodoist => 'Edukalt ühendatud Todoistiga!';

  @override
  String get failedToConnectTodoistRetry =>
      'Todoistiga ühendamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get successfullyConnectedAsana => 'Edukalt ühendatud Asanaga!';

  @override
  String get failedToConnectAsanaRetry =>
      'Asanaga ühendamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get successfullyConnectedGoogleTasks =>
      'Edukalt ühendatud Google Tasksiga!';

  @override
  String get failedToConnectGoogleTasksRetry =>
      'Google Tasksiga ühendamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get successfullyConnectedClickUp => 'Edukalt ühendatud ClickUpiga!';

  @override
  String get failedToConnectClickUpRetry =>
      'ClickUpiga ühendamine ebaõnnestus. Palun proovi uuesti.';

  @override
  String get successfullyConnectedNotion => 'Edukalt ühendatud Notioniga!';

  @override
  String get failedToRefreshNotionStatus =>
      'Notioni ühenduse oleku värskendamine ebaõnnestus.';

  @override
  String get successfullyConnectedGoogle => 'Edukalt ühendatud Google\'iga!';

  @override
  String get failedToRefreshGoogleStatus =>
      'Google\'i ühenduse oleku värskendamine ebaõnnestus.';

  @override
  String get successfullyConnectedWhoop => 'Edukalt ühendatud Whoopiga!';

  @override
  String get failedToRefreshWhoopStatus =>
      'Whoopi ühenduse oleku värskendamine ebaõnnestus.';

  @override
  String get successfullyConnectedGitHub => 'Edukalt ühendatud GitHubiga!';

  @override
  String get failedToRefreshGitHubStatus =>
      'GitHubi ühenduse oleku värskendamine ebaõnnestus.';

  @override
  String get authFailedToSignInWithGoogle =>
      'Google\'iga sisselogimine ebaõnnestus, palun proovige uuesti.';

  @override
  String get authenticationFailed =>
      'Autentimine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get authFailedToSignInWithApple =>
      'Apple\'iga sisselogimine ebaõnnestus, palun proovige uuesti.';

  @override
  String get authFailedToRetrieveToken =>
      'Firebase tokeni hankimine ebaõnnestus, palun proovige uuesti.';

  @override
  String get authUnexpectedErrorFirebase =>
      'Ootamatu viga sisselogimisel, Firebase viga, palun proovige uuesti.';

  @override
  String get authUnexpectedError =>
      'Ootamatu viga sisselogimisel, palun proovige uuesti';

  @override
  String get authFailedToLinkGoogle =>
      'Google\'iga sidumine ebaõnnestus, palun proovige uuesti.';

  @override
  String get authFailedToLinkApple =>
      'Apple\'iga sidumine ebaõnnestus, palun proovige uuesti.';

  @override
  String get onboardingBluetoothRequired =>
      'Seadmega ühenduse loomiseks on vajalik Bluetoothi luba.';

  @override
  String get onboardingBluetoothDeniedSystemPrefs =>
      'Bluetoothi luba keelatud. Palun andke luba Süsteemieelistustes.';

  @override
  String onboardingBluetoothStatusCheckPrefs(String status) {
    return 'Bluetoothi loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String onboardingFailedCheckBluetooth(String error) {
    return 'Bluetoothi loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get onboardingNotificationDeniedSystemPrefs =>
      'Teavituste luba keelatud. Palun andke luba Süsteemieelistustes.';

  @override
  String get onboardingNotificationDeniedNotifications =>
      'Teavituste luba keelatud. Palun andke luba Süsteemieelistused > Teavitused.';

  @override
  String onboardingNotificationStatusCheckPrefs(String status) {
    return 'Teavituste loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String onboardingFailedCheckNotification(String error) {
    return 'Teavituste loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get onboardingLocationGrantInSettings =>
      'Palun andke asukohaluba Seaded > Privaatsus ja turvalisus > Asukohateenused';

  @override
  String get onboardingMicrophoneRequired =>
      'Salvestamiseks on vajalik mikrofoni luba.';

  @override
  String get onboardingMicrophoneDenied =>
      'Mikrofoni luba keelatud. Palun andke luba Süsteemieelistused > Privaatsus ja turvalisus > Mikrofon.';

  @override
  String onboardingMicrophoneStatusCheckPrefs(String status) {
    return 'Mikrofoni loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String onboardingFailedCheckMicrophone(String error) {
    return 'Mikrofoni loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get onboardingScreenCaptureRequired =>
      'Süsteemiheli salvestamiseks on vajalik ekraanipildi luba.';

  @override
  String get onboardingScreenCaptureDenied =>
      'Ekraanipildi luba keelatud. Palun andke luba Süsteemieelistused > Privaatsus ja turvalisus > Ekraani salvestamine.';

  @override
  String onboardingScreenCaptureStatusCheckPrefs(String status) {
    return 'Ekraanipildi loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String onboardingFailedCheckScreenCapture(String error) {
    return 'Ekraanipildi loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get onboardingAccessibilityRequired =>
      'Brauseri koosolekute tuvastamiseks on vajalik ligipääsetavuse luba.';

  @override
  String onboardingAccessibilityStatusCheckPrefs(String status) {
    return 'Ligipääsetavuse loa olek: $status. Palun kontrollige Süsteemieelistusi.';
  }

  @override
  String onboardingFailedCheckAccessibility(String error) {
    return 'Ligipääsetavuse loa kontrollimine ebaõnnestus: $error';
  }

  @override
  String get msgCameraNotAvailable =>
      'Kaamera jäädvustamine pole sellel platvormil saadaval';

  @override
  String get msgCameraPermissionDenied =>
      'Kaamera luba keelatud. Palun lubage juurdepääs kaamerale';

  @override
  String msgCameraAccessError(String error) {
    return 'Viga kaamerale juurdepääsul: $error';
  }

  @override
  String get msgPhotoError => 'Viga foto tegemisel. Palun proovige uuesti.';

  @override
  String get msgMaxImagesLimit => 'Saate valida kuni 4 pilti';

  @override
  String msgFilePickerError(String error) {
    return 'Viga failivalija avamisel: $error';
  }

  @override
  String msgSelectImagesError(String error) {
    return 'Viga piltide valimisel: $error';
  }

  @override
  String get msgPhotosPermissionDenied =>
      'Fotode luba keelatud. Palun lubage juurdepääs fotodele piltide valimiseks';

  @override
  String get msgSelectImagesGenericError =>
      'Viga piltide valimisel. Palun proovige uuesti.';

  @override
  String get msgMaxFilesLimit => 'Saate valida kuni 4 faili';

  @override
  String msgSelectFilesError(String error) {
    return 'Viga failide valimisel: $error';
  }

  @override
  String get msgSelectFilesGenericError =>
      'Viga failide valimisel. Palun proovige uuesti.';

  @override
  String get msgUploadFileFailed =>
      'Faili üleslaadimine ebaõnnestus, palun proovige hiljem uuesti';

  @override
  String get msgReadingMemories => 'Loen sinu mälestusi...';

  @override
  String get msgLearningMemories => 'Õpin sinu mälestustest...';

  @override
  String get msgUploadAttachedFileFailed =>
      'Manustatud faili üleslaadimine ebaõnnestus.';

  @override
  String captureRecordingError(String error) {
    return 'Salvestamisel ilmnes viga: $error';
  }

  @override
  String captureRecordingStoppedDisplayIssue(String reason) {
    return 'Salvestamine peatatud: $reason. Võimalik, et peate välised ekraanid uuesti ühendama või salvestamise taaskäivitama.';
  }

  @override
  String get captureMicrophonePermissionRequired => 'Mikrofoni luba on vajalik';

  @override
  String get captureMicrophonePermissionInSystemPreferences =>
      'Andke mikrofoni luba Süsteemieelistustes';

  @override
  String get captureScreenRecordingPermissionRequired =>
      'Ekraani salvestamise luba on vajalik';

  @override
  String get captureDisplayDetectionFailed =>
      'Ekraani tuvastamine ebaõnnestus. Salvestamine peatatud.';

  @override
  String get devModeInvalidAudioBytesWebhookUrl =>
      'Kehtetu helibaitide veebihaagi URL';

  @override
  String get devModeInvalidRealtimeTranscriptWebhookUrl =>
      'Kehtetu reaalajas transkriptsiooni veebihaagi URL';

  @override
  String get devModeInvalidConversationCreatedWebhookUrl =>
      'Kehtetu loodud vestluse veebihaagi URL';

  @override
  String get devModeInvalidDaySummaryWebhookUrl =>
      'Kehtetu päeva kokkuvõtte veebihaagi URL';

  @override
  String get devModeSettingsSaved => 'Seaded salvestatud!';

  @override
  String get voiceFailedToTranscribe => 'Heli transkribeerimine ebaõnnestus';

  @override
  String get locationPermissionRequired => 'Asukoha luba nõutav';

  @override
  String get locationPermissionContent =>
      'Kiire edastus vajab asukoha luba WiFi-ühenduse kontrollimiseks. Jätkamiseks andke palun asukoha luba.';

  @override
  String get pdfTranscriptExport => 'Transkriptsiooni eksport';

  @override
  String get pdfConversationExport => 'Vestluse eksport';

  @override
  String pdfTitleLabel(String title) {
    return 'Pealkiri: $title';
  }

  @override
  String get conversationNewIndicator => 'Uus 🚀';

  @override
  String conversationPhotosCount(int count) {
    return '$count fotot';
  }

  @override
  String get mergingStatus => 'Ühendamine...';

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
    return '$count tund';
  }

  @override
  String timeHoursPlural(int count) {
    return '$count tundi';
  }

  @override
  String timeHoursAndMins(int hours, int mins) {
    return '$hours tundi $mins min';
  }

  @override
  String timeDaySingular(int count) {
    return '$count päev';
  }

  @override
  String timeDaysPlural(int count) {
    return '$count päeva';
  }

  @override
  String timeDaysAndHours(int days, int hours) {
    return '$days päeva $hours tundi';
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
    return '${count}t';
  }

  @override
  String timeCompactHoursAndMins(int hours, int mins) {
    return '${hours}t ${mins}m';
  }

  @override
  String get moveToFolder => 'Teisalda kausta';

  @override
  String get noFoldersAvailable => 'Kaustad pole saadaval';

  @override
  String get newFolder => 'Uus kaust';

  @override
  String get color => 'Värv';

  @override
  String get waitingForDevice => 'Ootan seadet...';

  @override
  String get saySomething => 'Ütle midagi...';

  @override
  String get initialisingSystemAudio => 'Süsteemiheli initsialiseerimine';

  @override
  String get stopRecording => 'Peata salvestus';

  @override
  String get continueRecording => 'Jätka salvestamist';

  @override
  String get initialisingRecorder => 'Salvestaja initsialiseerimine';

  @override
  String get pauseRecording => 'Peata salvestus';

  @override
  String get resumeRecording => 'Jätka salvestamist';

  @override
  String get noDailyRecapsYet => 'Päevaseid kokkuvõtteid veel pole';

  @override
  String get dailyRecapsDescription =>
      'Teie päevased kokkuvõtted ilmuvad siia pärast nende loomist';

  @override
  String get chooseTransferMethod => 'Valige ülekandemeetod';

  @override
  String get fastTransferSpeed => '~150 KB/s WiFi kaudu';

  @override
  String largeTimeGapDetected(String gap) {
    return 'Tuvastati suur ajavahe ($gap)';
  }

  @override
  String largeTimeGapsDetected(String gaps) {
    return 'Tuvastati suured ajavahed ($gaps)';
  }

  @override
  String get deviceDoesNotSupportWifiSwitchingToBle =>
      'Seade ei toeta WiFi sünkroniseerimist, lülitumine Bluetoothile';

  @override
  String get appleHealthNotAvailable =>
      'Apple Health pole selles seadmes saadaval';

  @override
  String get downloadAudio => 'Laadi heli alla';

  @override
  String get audioDownloadSuccess => 'Heli on edukalt alla laaditud';

  @override
  String get audioDownloadFailed => 'Heli allalaadimine ebaõnnestus';

  @override
  String get downloadingAudio => 'Heli allalaadimine...';

  @override
  String get shareAudio => 'Jaga heli';

  @override
  String get preparingAudio => 'Heli ettevalmistamine';

  @override
  String get gettingAudioFiles => 'Helifailide hankimine...';

  @override
  String get downloadingAudioProgress => 'Heli allalaadimine';

  @override
  String get processingAudio => 'Heli töötlemine';

  @override
  String get combiningAudioFiles => 'Helifailide ühendamine...';

  @override
  String get audioReady => 'Heli on valmis';

  @override
  String get openingShareSheet => 'Jagamislehe avamine...';

  @override
  String get audioShareFailed => 'Jagamine ebaõnnestus';

  @override
  String get dailyRecaps => 'Päevased Kokkuvõtted';

  @override
  String get removeFilter => 'Eemalda Filter';

  @override
  String get categoryConversationAnalysis => 'Vestluste analüüs';

  @override
  String get categoryPersonalityClone => 'Isiksuse kloon';

  @override
  String get categoryHealth => 'Tervis';

  @override
  String get categoryEducation => 'Haridus';

  @override
  String get categoryCommunication => 'Suhtlus';

  @override
  String get categoryEmotionalSupport => 'Emotsionaalne tugi';

  @override
  String get categoryProductivity => 'Tootlikkus';

  @override
  String get categoryEntertainment => 'Meelelahutus';

  @override
  String get categoryFinancial => 'Rahandus';

  @override
  String get categoryTravel => 'Reisimine';

  @override
  String get categorySafety => 'Turvalisus';

  @override
  String get categoryShopping => 'Ostlemine';

  @override
  String get categorySocial => 'Sotsiaalne';

  @override
  String get categoryNews => 'Uudised';

  @override
  String get categoryUtilities => 'Tööriistad';

  @override
  String get categoryOther => 'Muu';

  @override
  String get capabilityChat => 'Vestlus';

  @override
  String get capabilityConversations => 'Vestlused';

  @override
  String get capabilityExternalIntegration => 'Väline integratsioon';

  @override
  String get capabilityNotification => 'Teavitus';

  @override
  String get triggerAudioBytes => 'Heli baidid';

  @override
  String get triggerConversationCreation => 'Vestluse loomine';

  @override
  String get triggerTranscriptProcessed => 'Transkriptsioon töödeldud';

  @override
  String get actionCreateConversations => 'Loo vestlused';

  @override
  String get actionCreateMemories => 'Loo mälestused';

  @override
  String get actionReadConversations => 'Loe vestlusi';

  @override
  String get actionReadMemories => 'Loe mälestusi';

  @override
  String get actionReadTasks => 'Loe ülesandeid';

  @override
  String get scopeUserName => 'Kasutajanimi';

  @override
  String get scopeUserFacts => 'Kasutaja faktid';

  @override
  String get scopeUserConversations => 'Kasutaja vestlused';

  @override
  String get scopeUserChat => 'Kasutaja vestlus';

  @override
  String get capabilitySummary => 'Kokkuvõte';

  @override
  String get capabilityFeatured => 'Esiletõstetud';

  @override
  String get capabilityTasks => 'Ülesanded';

  @override
  String get capabilityIntegrations => 'Integratsioonid';

  @override
  String get categoryPersonalityClones => 'Isiksuse kloonid';

  @override
  String get categoryProductivityLifestyle => 'Tootlikkus ja elustiil';

  @override
  String get categorySocialEntertainment => 'Sotsiaalne ja meelelahutus';

  @override
  String get categoryProductivityTools => 'Tootlikkuse tööriistad';

  @override
  String get categoryPersonalWellness => 'Isiklik heaolu';

  @override
  String get rating => 'Hinnang';

  @override
  String get categories => 'Kategooriad';

  @override
  String get sortBy => 'Sorteeri';

  @override
  String get highestRating => 'Kõrgeim hinnang';

  @override
  String get lowestRating => 'Madalaim hinnang';

  @override
  String get resetFilters => 'Lähtesta filtrid';

  @override
  String get applyFilters => 'Rakenda filtrid';

  @override
  String get mostInstalls => 'Enim paigaldusi';

  @override
  String get couldNotOpenUrl =>
      'URL-i avamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get newTask => 'Uus ülesanne';

  @override
  String get viewAll => 'Vaata kõiki';

  @override
  String get addTask => 'Lisa ülesanne';

  @override
  String get addMcpServer => 'Add MCP Server';

  @override
  String get connectExternalAiTools => 'Connect external AI tools';

  @override
  String get mcpServerUrl => 'MCP Server URL';

  @override
  String mcpServerConnected(int count) {
    return '$count tools connected successfully';
  }

  @override
  String get mcpConnectionFailed => 'Failed to connect to MCP server';

  @override
  String get authorizingMcpServer => 'Authorizing...';

  @override
  String get whereDidYouHearAboutOmi => 'How did you find us?';

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
  String get friendWordOfMouth => 'Friend';

  @override
  String get otherSource => 'Other';

  @override
  String get pleaseSpecify => 'Please specify';

  @override
  String get event => 'Event';

  @override
  String get coworker => 'Coworker';

  @override
  String get linkedIn => 'LinkedIn';

  @override
  String get appStore => 'App Store';

  @override
  String get googleSearch => 'Google Search';

  @override
  String get audioPlaybackUnavailable => 'Helifail ei ole esitamiseks saadaval';

  @override
  String get audioPlaybackFailed =>
      'Heli esitamine ebaõnnestus. Fail võib olla rikutud või puududa.';

  @override
  String get connectionGuide => 'Ühendamisjuhend';

  @override
  String get iveDoneThis => 'Olen seda teinud';

  @override
  String get pairNewDevice => 'Sidu uus seade';

  @override
  String get dontSeeYourDevice => 'Ei näe oma seadet?';

  @override
  String get reportAnIssue => 'Teata probleemist';

  @override
  String get pairingTitleOmi => 'Lülitage Omi sisse';

  @override
  String get pairingDescOmi =>
      'Vajutage ja hoidke seadet all, kuni see vibreerib, et seda sisse lülitada.';

  @override
  String get pairingTitleOmiDevkit => 'Lülitage Omi DevKit sidumisrežiimi';

  @override
  String get pairingDescOmiDevkit =>
      'Vajutage nuppu üks kord sisselülitamiseks. LED vilgub sidumisrežiimis lillana.';

  @override
  String get pairingTitleOmiGlass => 'Lülitage Omi Glass sisse';

  @override
  String get pairingDescOmiGlass =>
      'Vajutage ja hoidke külgnuppu 3 sekundit sisselülitamiseks.';

  @override
  String get pairingTitlePlaudNote => 'Lülitage Plaud Note sidumisrežiimi';

  @override
  String get pairingDescPlaudNote =>
      'Vajutage ja hoidke külgnuppu 2 sekundit. Punane LED vilgub, kui seade on sidumiseks valmis.';

  @override
  String get pairingTitleBee => 'Lülitage Bee sidumisrežiimi';

  @override
  String get pairingDescBee =>
      'Vajutage nuppu 5 korda järjest. Tuli hakkab vilkuma siniselt ja roheliselt.';

  @override
  String get pairingTitleLimitless => 'Lülitage Limitless sidumisrežiimi';

  @override
  String get pairingDescLimitless =>
      'Kui mõni tuli põleb, vajutage üks kord ja seejärel vajutage ja hoidke all, kuni seade näitab roosat valgust, seejärel vabastage.';

  @override
  String get pairingTitleFriendPendant =>
      'Lülitage Friend Pendant sidumisrežiimi';

  @override
  String get pairingDescFriendPendant =>
      'Vajutage ripatsil olevat nuppu selle sisselülitamiseks. See lülitub automaatselt sidumisrežiimi.';

  @override
  String get pairingTitleFieldy => 'Lülitage Fieldy sidumisrežiimi';

  @override
  String get pairingDescFieldy =>
      'Vajutage ja hoidke seadet all, kuni ilmub valgus, et seda sisse lülitada.';

  @override
  String get pairingTitleAppleWatch => 'Ühendage Apple Watch';

  @override
  String get pairingDescAppleWatch =>
      'Installige ja avage Omi rakendus oma Apple Watchis, seejärel puudutage rakenduses Ühenda.';

  @override
  String get pairingTitleNeoOne => 'Lülitage Neo One sidumisrežiimi';

  @override
  String get pairingDescNeoOne =>
      'Vajutage ja hoidke toitenuppu, kuni LED vilgub. Seade on leitav.';

  @override
  String whatsNewInVersion(String version) {
    return 'Mis on uut versioonis $version';
  }

  @override
  String get addToYourTaskList => 'Lisada oma ülesannete loendisse?';

  @override
  String get failedToCreateShareLink => 'Jagamislingi loomine ebaõnnestus';

  @override
  String get deleteGoal => 'Kustuta eesmärk';

  @override
  String get deviceUpToDate => 'Teie seade on ajakohane';

  @override
  String get wifiConfiguration => 'WiFi seadistamine';

  @override
  String get wifiConfigurationSubtitle =>
      'Sisestage WiFi andmed, et seade saaks püsivara alla laadida.';

  @override
  String get networkNameSsid => 'Võrgu nimi (SSID)';

  @override
  String get enterWifiNetworkName => 'Sisestage WiFi võrgu nimi';

  @override
  String get enterWifiPassword => 'Sisestage WiFi parool';
}
