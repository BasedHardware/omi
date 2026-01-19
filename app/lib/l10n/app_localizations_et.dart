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
  String get ok => 'Ok';

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
  String get errorProcessingConversation => 'Viga vestluse töötlemisel. Palun proovige hiljem uuesti.';

  @override
  String get noInternetConnection => 'Internetiühendus puudub';

  @override
  String get unableToDeleteConversation => 'Vestlust ei õnnestunud kustutada';

  @override
  String get somethingWentWrong => 'Midagi läks valesti! Palun proovige hiljem uuesti.';

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
  String get createPersonHint => 'Looge uus isik ja õpetage Omi-le ära tundma ka tema kõnet!';

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
  String get failedToStartAuthentication => 'Autentimise alustamine ebaõnnestus';

  @override
  String get importStarted => 'Import algas! Saate teate, kui see on lõpetatud.';

  @override
  String get failedToStartImport => 'Impordi alustamine ebaõnnestus. Palun proovige uuesti.';

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
  String get pendantNotConnected => 'Ripats pole ühendatud. Sünkroonimiseks ühendage see.';

  @override
  String get everythingSynced => 'Kõik on juba sünkroonitud.';

  @override
  String get recordingsNotSynced => 'Teil on salvestisi, mis pole veel sünkroonitud.';

  @override
  String get syncingBackground => 'Jätkame teie salvestiste sünkroonimist taustal.';

  @override
  String get noConversationsYet => 'Vestlusi pole veel';

  @override
  String get noStarredConversations => 'Tärniga märgitud vestlusi pole veel.';

  @override
  String get starConversationHint => 'Vestluse tärniga märkimiseks avage see ja puudutage päises tärni ikooni.';

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
  String get mergingInBackground => 'Ühendamine käib taustal. See võib võtta hetke aega.';

  @override
  String get failedToStartMerge => 'Ühendamise alustamine ebaõnnestus';

  @override
  String get askAnything => 'Küsi mida tahes';

  @override
  String get noMessagesYet => 'Sõnumeid pole veel!\nMiks te ei alusta vestlust?';

  @override
  String get deletingMessages => 'Teie sõnumite kustutamine Omi mälust...';

  @override
  String get messageCopied => 'Sõnum kopeeritud lõikelauale.';

  @override
  String get cannotReportOwnMessage => 'Te ei saa oma sõnumitest teatada.';

  @override
  String get reportMessage => 'Teata sõnumist';

  @override
  String get reportMessageConfirm => 'Kas olete kindel, et soovite sellest sõnumist teatada?';

  @override
  String get messageReported => 'Sõnumist teatati edukalt.';

  @override
  String get thankYouFeedback => 'Täname tagasiside eest!';

  @override
  String get clearChat => 'Tühjenda vestlus?';

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
  String get createYourOwnApp => 'Looge oma rakendus';

  @override
  String get buildAndShareApp => 'Looge ja jagage oma kohandatud rakendust';

  @override
  String get searchApps => 'Otsi rakendusi...';

  @override
  String get myApps => 'Minu rakendused';

  @override
  String get installedApps => 'Installitud rakendused';

  @override
  String get unableToFetchApps =>
      'Rakenduste laadimine ebaõnnestus :(\n\nPalun kontrollige oma internetiühendust ja proovige uuesti.';

  @override
  String get aboutOmi => 'Omi teave';

  @override
  String get privacyPolicy => 'Privaatsuspoliitikaga';

  @override
  String get visitWebsite => 'Külasta veebilehte';

  @override
  String get helpOrInquiries => 'Abi või päringud?';

  @override
  String get joinCommunity => 'Liitu kogukonnaga!';

  @override
  String get membersAndCounting => '8000+ liiget ja kasvab.';

  @override
  String get deleteAccountTitle => 'Kustuta konto';

  @override
  String get deleteAccountConfirm => 'Kas olete kindel, et soovite oma konto kustutada?';

  @override
  String get cannotBeUndone => 'Seda ei saa tagasi võtta.';

  @override
  String get allDataErased => 'Kõik teie mälestused ja vestlused kustutatakse jäädavalt.';

  @override
  String get appsDisconnected => 'Teie rakendused ja integratsioonid katkestatakse viivitamatult.';

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
  String get customVocabulary => 'Kohandatud sõnavara';

  @override
  String get identifyingOthers => 'Teiste tuvastamine';

  @override
  String get paymentMethods => 'Makseviisid';

  @override
  String get conversationDisplay => 'Vestluse kuvamine';

  @override
  String get dataPrivacy => 'Andmed ja privaatsus';

  @override
  String get userId => 'Kasutaja ID';

  @override
  String get notSet => 'Pole määratud';

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
  String get chatTools => 'Vestlustööriistad';

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
  String get signOut => 'Logi välja';

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
  String get noAppsExternalAccess => 'Ühelgi paigaldatud rakendusel pole välise juurdepääsu teie andmetele.';

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
  String get connectDeviceMessage => 'Ühendage oma Omi seade, et pääseda juurde\nseadme seadetele ja kohandamisele';

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
  String get conversationTimeoutConfig => 'Määrake, millal vestlused automaatselt lõpevad';

  @override
  String get importData => 'Impordi andmed';

  @override
  String get importDataConfig => 'Importige andmed teistest allikatest';

  @override
  String get debugDiagnostics => 'Silumis- ja diagnostika';

  @override
  String get endpointUrl => 'Otspunkti URL';

  @override
  String get noApiKeys => 'API võtmeid pole veel';

  @override
  String get createKeyToStart => 'Alustamiseks looge võti';

  @override
  String get createKey => 'Loo võti';

  @override
  String get docs => 'Dokumendid';

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
  String get startConversationToSeeInsights => 'Alustage Omi-ga vestlust,\net näha siinkohal oma kasutuse ülevaadet.';

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
  String get providingSubtitle => 'Tegevuspunktid ja märkmed automaatselt salvestatud.';

  @override
  String get remembering => 'Meelde jätmine';

  @override
  String get rememberingSubtitle => 'Teie jaoks meeles peetud faktid ja üksikasjad.';

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
  String get shareStatsMessage => 'Jagan oma Omi statistikat! (omi.me - teie alati sees AI assistent)';

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
  String get knowledgeGraphDeleted => 'Teadmiste graaf kustutati edukalt';

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
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Kliendi ID';

  @override
  String get clientSecret => 'Kliendi saladus';

  @override
  String get useMcpApiKey => 'Kasutage oma MCP API võtit';

  @override
  String get webhooks => 'Veebipoogid';

  @override
  String get conversationEvents => 'Vestluse sündmused';

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
  String get visibilitySubtitle => 'Kontrollige, millised vestlused teie loendis kuvatakse';

  @override
  String get showShortConversations => 'Kuva lühikesed vestlused';

  @override
  String get showShortConversationsDesc => 'Kuva künnisest lühemaid vestlusi';

  @override
  String get showDiscardedConversations => 'Kuva hüljatud vestlused';

  @override
  String get showDiscardedConversationsDesc => 'Kaasa hüljatuna märgitud vestlused';

  @override
  String get shortConversationThreshold => 'Lühikese vestluse künnis';

  @override
  String get shortConversationThresholdSubtitle => 'Sellest lühemad vestlused peidetakse, kui pole ülalpool lubatud';

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
  String get connect => 'Ühenda';

  @override
  String get comingSoon => 'Tulekul';

  @override
  String get chatToolsFooter => 'Ühendage oma rakendused, et vestluses andmeid ja mõõdikuid vaadata.';

  @override
  String get completeAuthInBrowser => 'Palun lõpetage autentimine oma brauseris. Kui olete valmis, naasake rakendusse.';

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
  String get wouldLikePermission => 'Sooviksime teie luba teie helisalvestiste salvestamiseks. Siin on põhjus:';

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
  String get failedToAuthorize => 'Autoriseerimine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get authorizationRevoked => 'Autoriseerimine tühistatud.';

  @override
  String get recordingsDeleted => 'Salvestised kustutatud.';

  @override
  String get failedToRevoke => 'Autoriseerimise tühistamine ebaõnnestus. Palun proovige uuesti.';

  @override
  String get permissionRevokedTitle => 'Luba tühistatud';

  @override
  String get permissionRevokedMessage => 'Kas soovite, et me eemaldaksime ka kõik teie olemasolevad salvestised?';

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
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Sünkroonige oma Google\'i kontoga';

  @override
  String get showMeetingsMenuBar => 'Kuva tulevased koosolekud menüüribal';

  @override
  String get showMeetingsMenuBarDesc => 'Kuva oma järgmine koosolek ja aeg selle alguseni macOS-i menüüribal';

  @override
  String get showEventsNoParticipants => 'Kuva ilma osalejateta sündmusi';

  @override
  String get showEventsNoParticipantsDesc => 'Kui lubatud, näitab Coming Up sündmusi ilma osalejate või videolingita.';

  @override
  String get yourMeetings => 'Teie koosolekud';

  @override
  String get refresh => 'Värskenda';

  @override
  String get noUpcomingMeetings => 'Tulevasi koosolekuid ei leitud';

  @override
  String get checkingNextDays => 'Kontrolli järgmist 30 päeva';

  @override
  String get tomorrow => 'Homme';

  @override
  String get googleCalendarComingSoon => 'Google Calendar integratsioon tuleb varsti!';

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
  String get leaveUnselectedTasks => 'Jätke valimata, et luua ülesanded ilma projektita';

  @override
  String get noProjectsInWorkspace => 'Selles tööalas projekte ei leitud';

  @override
  String get conversationTimeoutDesc => 'Valige, kui kaua vaikuses oodatakse enne vestluse automaatset lõpetamist:';

  @override
  String get timeout2Minutes => '2 minutit';

  @override
  String get timeout2MinutesDesc => 'Lõpeta vestlus pärast 2-minutilist vaikust';

  @override
  String get timeout5Minutes => '5 minutit';

  @override
  String get timeout5MinutesDesc => 'Lõpeta vestlus pärast 5-minutilist vaikust';

  @override
  String get timeout10Minutes => '10 minutit';

  @override
  String get timeout10MinutesDesc => 'Lõpeta vestlus pärast 10-minutilist vaikust';

  @override
  String get timeout30Minutes => '30 minutit';

  @override
  String get timeout30MinutesDesc => 'Lõpeta vestlus pärast 30-minutilist vaikust';

  @override
  String get timeout4Hours => '4 tundi';

  @override
  String get timeout4HoursDesc => 'Lõpeta vestlus pärast 4-tunnist vaikust';

  @override
  String get conversationEndAfterHours => 'Vestlused lõpevad nüüd pärast 4-tunnist vaikust';

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
  String get singleLanguageModeInfo => 'Ühe keele režiim on lubatud. Tõlge on keelatud suurema täpsuse jaoks.';

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
  String get failedToSaveDefaultRepo => 'Vaikimisi hoidla salvestamine ebaõnnestus';

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
  String get issuesCreatedInRepo => 'Probleemid luuakse teie vaikimisi hoidlasse';

  @override
  String get taskIntegrations => 'Ülesannete integratsioonid';

  @override
  String get configureSettings => 'Seadista seaded';

  @override
  String get completeAuthBrowser => 'Palun lõpetage autentimine oma brauseris. Kui olete valmis, naasake rakendusse.';

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
  String get gotIt => 'Sain aru';

  @override
  String get tasksExportedOneApp => 'Ülesandeid saab eksportida korraga ühte rakendusse.';

  @override
  String get completeYourUpgrade => 'Viige oma uuendamine lõpule';

  @override
  String get importConfiguration => 'Impordi konfiguratsioon';

  @override
  String get exportConfiguration => 'Ekspordi konfiguratsioon';

  @override
  String get bringYourOwn => 'Tooge oma oma';

  @override
  String get payYourSttProvider => 'Kasutage Omi-d vabalt. Maksite ainult oma STT pakkujale otse.';

  @override
  String get freeMinutesMonth => '1200 tasuta minutit kuus kaasa arvatud. Piiramatu koos ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host on nõutud';

  @override
  String get validPortRequired => 'Kehtiv port on nõutud';

  @override
  String get validWebsocketUrlRequired => 'Kehtiv WebSocket URL on nõutud (wss://)';

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
  String get configCopiedToClipboard => 'Konfiguratsioon kopeeritud lõikelauale';

  @override
  String get pasteJsonConfig => 'Kleepige oma JSON-konfiguratsioon allpool:';

  @override
  String get addApiKeyAfterImport => 'Peate pärast importimist lisama oma API võtme';

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
  String get enterLiveSttWebsocket => 'Sisestage oma reaalajas STT WebSocket otspunkt';

  @override
  String get apiKey => 'API võti';

  @override
  String get enterApiKey => 'Sisestage oma API võti';

  @override
  String get storedLocallyNeverShared => 'Salvestatud lokaalselt, ei jagata kunagi';

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
  String get noLogsYet => 'Logisid pole veel. Alustage salvestamist, et näha kohandatud STT tegevust.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName kasutab $codecReason. Kasutatakse Omi-d.';
  }

  @override
  String get omiTranscription => 'Omi transkriptsioon';

  @override
  String get bestInClassTranscription => 'Parim oma klassis transkriptsioon nullseadistusega';

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
  String get appName => 'Rakenduse nimi';

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
  String get tailoredConversationSummaries => 'Kohandatud vestluste kokkuvõtted';

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
  String get usersPayToUse => 'Kasutajad maksavad teie rakenduse kasutamise eest';

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
  String get iUnderstand => 'Sain aru';

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
  String get backgroundActivityDesc => 'Lubage Omil töötada taustal parema stabiilsuse tagamiseks';

  @override
  String get locationAccess => 'Asukoha juurdepääs';

  @override
  String get locationAccessDesc => 'Lubage tausta asukoht täieliku kogemuse saamiseks';

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
  String get speechProfileIntro => 'Omi peab õppima teie eesmärke ja häält. Saate seda hiljem muuta.';

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
  String get tooShortDesc => 'Kõnet ei tuvastatud piisavalt. Palun rääkige rohkem ja proovige uuesti.';

  @override
  String get invalidRecordingDesc => 'Palun veenduge, et räägite vähemalt 5 sekundit ja mitte rohkem kui 90.';

  @override
  String get areYouThere => 'Kas olete seal?';

  @override
  String get noSpeechDesc =>
      'Me ei suutnud kõnet tuvastada. Palun veenduge, et räägite vähemalt 10 sekundit ja mitte rohkem kui 3 minutit.';

  @override
  String get connectionLost => 'Ühendus kadus';

  @override
  String get connectionLostDesc => 'Ühendus katkestati. Palun kontrollige oma internetiühendust ja proovige uuesti.';

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
  String get languageBenefits => 'Määrake oma keel täpsemate transkriptsioonide ja isikupärastatud kogemuse saamiseks';

  @override
  String get whatsYourPrimaryLanguage => 'Mis on teie põhikeel?';

  @override
  String get selectYourLanguage => 'Valige oma keel';

  @override
  String get personalGrowthJourney => 'Teie isiklik kasvuteekond AI-ga, mis kuulab iga teie sõna.';

  @override
  String get actionItemsTitle => 'Tegevused';

  @override
  String get actionItemsDescription => 'Puudutage muutmiseks • Vajutage pikalt valimiseks • Libistage toimingute jaoks';

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
  String get actionItemMarkedIncomplete => 'Tegevuspunkt märgitud mittelõpetatuks';

  @override
  String get actionItemCompleted => 'Tegevuspunkt lõpetatud';

  @override
  String get deleteActionItemTitle => 'Kustuta toiming';

  @override
  String get deleteActionItemMessage => 'Kas olete kindel, et soovite selle toimingu kustutada?';

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
  String get editSwipeFeature => 'Puudutage muutmiseks, libistage lõpetamiseks või kustutamiseks';

  @override
  String itemsSelected(int count) {
    return '$count valitud';
  }

  @override
  String get selectAll => 'Vali kõik';

  @override
  String get deleteSelected => 'Kustuta valitud';

  @override
  String searchMemories(int count) {
    return 'Otsi $count mälestust';
  }

  @override
  String get memoryDeleted => 'Mälestus kustutatud.';

  @override
  String get undo => 'Tühista';

  @override
  String get noMemoriesYet => 'Mälestusi pole veel';

  @override
  String get noAutoMemories => 'Automaatselt eraldatud mälestusi pole veel';

  @override
  String get noManualMemories => 'Käsitsi lisatud mälestusi pole veel';

  @override
  String get noMemoriesInCategories => 'Neis kategooriates pole mälestusi';

  @override
  String get noMemoriesFound => 'Mälestusi ei leitud';

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
  String get noMemoriesToDelete => 'Kustutatavaid mälestusi pole';

  @override
  String get createMemoryTooltip => 'Loo uus mälestus';

  @override
  String get createActionItemTooltip => 'Loo uus tegevuspunkt';

  @override
  String get memoryManagement => 'Mälu haldamine';

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
  String get newMemory => 'Uus mälestus';

  @override
  String get editMemory => 'Muuda mälestust';

  @override
  String get memoryContentHint => 'Mulle meeldib süüa jäätist...';

  @override
  String get failedToSaveMemory => 'Salvestamine ebaõnnestus. Palun kontrollige oma ühendust.';

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
  String get actionItemDescriptionEmpty => 'Tegevuspunkti kirjeldus ei saa olla tühi.';

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
  String get deleteActionItemConfirmMessage => 'Kas olete kindel, et soovite selle tegevuspunkti kustutada?';

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
  String get pleaseCheckInternetConnection => 'Palun kontrollige oma internetiühendust ja proovige uuesti';

  @override
  String get pleaseSelectReason => 'Palun valige põhjus';

  @override
  String get tellUsMoreWhatWentWrong => 'Rääkige meile rohkem sellest, mis valesti läks...';

  @override
  String get selectText => 'Vali tekst';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimaalselt $count eesmärki lubatud';
  }

  @override
  String get conversationCannotBeMerged => 'Seda vestlust ei saa ühendada (lukustatud või juba ühendamisel)';

  @override
  String get pleaseEnterFolderName => 'Palun sisestage kausta nimi';

  @override
  String get failedToCreateFolder => 'Kausta loomine ebaõnnestus';

  @override
  String get failedToUpdateFolder => 'Kausta värskendamine ebaõnnestus';

  @override
  String get folderName => 'Kausta nimi';

  @override
  String get descriptionOptional => 'Kirjeldus (valikuline)';

  @override
  String get failedToDeleteFolder => 'Kausta kustutamine ebaõnnestus';

  @override
  String get editFolder => 'Muuda kausta';

  @override
  String get deleteFolder => 'Kustuta kaust';

  @override
  String get transcriptCopiedToClipboard => 'Transkriptsioon kopeeritud lõikelauale';

  @override
  String get summaryCopiedToClipboard => 'Kokkuvõte kopeeritud lõikelauale';

  @override
  String get conversationUrlCouldNotBeShared => 'Vestluse URL-i ei saanud jagada.';

  @override
  String get urlCopiedToClipboard => 'URL kopeeritud lõikelauale';

  @override
  String get exportTranscript => 'Ekspordi transkriptsioon';

  @override
  String get exportSummary => 'Ekspordi kokkuvõte';

  @override
  String get exportButton => 'Ekspordi';

  @override
  String get actionItemsCopiedToClipboard => 'Tegevusüksused kopeeritud lõikelauale';

  @override
  String get summarize => 'Kokkuvõte';

  @override
  String get generateSummary => 'Loo kokkuvõte';

  @override
  String get conversationNotFoundOrDeleted => 'Vestlust ei leitud või see on kustutatud';

  @override
  String get deleteMemory => 'Kustuta mälu?';

  @override
  String get thisActionCannotBeUndone => 'Seda toimingut ei saa tagasi võtta.';

  @override
  String memoriesCount(int count) {
    return '$count mälu';
  }

  @override
  String get noMemoriesInCategory => 'Selles kategoorias pole veel mälestusi';

  @override
  String get addYourFirstMemory => 'Lisa oma esimene mälu';

  @override
  String get firmwareDisconnectUsb => 'Eemaldage USB';

  @override
  String get firmwareUsbWarning => 'USB-ühendus värskenduste ajal võib teie seadet kahjustada.';

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
  String get unknownDevice => 'Tundmatu seade';

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
  String get actionItemDescriptionCannotBeEmpty => 'Toimingu kirjeldus ei tohi olla tühi';

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
  String get sdCardSyncDescription => 'SD-kaardi sünkroonimine impordib teie mälestused SD-kaardilt rakendusse';

  @override
  String get checksForAudioFiles => 'Kontrollib helifaile SD-kaardil';

  @override
  String get omiSyncsAudioFiles => 'Omi sünkroonib seejärel helifailid serveriga';

  @override
  String get serverProcessesAudio => 'Server töötleb helifaile ja loob mälestusi';

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
  String get keyboardShortcuts => 'Klaviatuuri otseteed';

  @override
  String get toggleControlBar => 'Lülita juhtpaneeli';

  @override
  String get pressKeys => 'Vajuta klahve...';

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
  String get target => 'Eesmärk';

  @override
  String get saveGoal => 'Salvesta';

  @override
  String get goals => 'Eesmärgid';

  @override
  String get tapToAddGoal => 'Puuduta eesmärgi lisamiseks';

  @override
  String get welcomeBack => 'Tere tulemast tagasi';

  @override
  String get yourConversations => 'Teie vestlused';

  @override
  String get reviewAndManageConversations => 'Vaadake üle ja hallake oma salvestatud vestlusi';

  @override
  String get startCapturingConversations => 'Alustage vestluste salvestamist oma Omi seadmega, et neid siin näha.';

  @override
  String get useMobileAppToCapture => 'Kasutage heeli salvestamiseks mobiilirakendust';

  @override
  String get conversationsProcessedAutomatically => 'Vestlusi töödeldakse automaatselt';

  @override
  String get getInsightsInstantly => 'Saate kohe ülevaateid ja kokkuvõtteid';

  @override
  String get showAll => 'Kuva kõik →';

  @override
  String get noTasksForToday => 'Täna pole ülesandeid.\\nKüsi Omi käest rohkem ülesandeid või loo need käsitsi.';

  @override
  String get dailyScore => 'PÄEVASKOOR';

  @override
  String get dailyScoreDescription => 'Skoor, mis aitab teil täitmisele paremini keskenduda.';

  @override
  String get searchResults => 'Otsingutulemused';

  @override
  String get actionItems => 'Tegevuspunktid';

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
  String get swipeTasksToIndent => 'Libista ülesandeid taande jaoks, lohista kategooriate vahel';

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
  String get monthApr => 'Apr';

  @override
  String get monthMay => 'Mai';

  @override
  String get monthJun => 'Juuni';

  @override
  String get monthJul => 'Juuli';

  @override
  String get monthAug => 'Aug';

  @override
  String get monthSep => 'Sept';

  @override
  String get monthOct => 'Okt';

  @override
  String get monthNov => 'Nov';

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
  String get install => 'Installi';

  @override
  String get noAppsAvailable => 'Rakendusi pole saadaval';

  @override
  String get unableToLoadApps => 'Rakenduste laadimine ebaõnnestus';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Proovi otsingumõisteid või filtreid kohandada';

  @override
  String get checkBackLaterForNewApps => 'Kontrolli hiljem uusi rakendusi';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Palun kontrolli oma internetiühendust ja proovi uuesti';

  @override
  String get createNewApp => 'Loo uus rakendus';

  @override
  String get buildSubmitCustomOmiApp => 'Ehita ja esita oma kohandatud Omi rakendus';

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
  String get clickHereForAppBuildingGuides => 'Klõpsa siia rakenduste loomise juhiste ja dokumentatsiooni jaoks';

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
  String get connectStripeOrPayPal => 'Ühenda Stripe või PayPal, et saada rakenduse eest makseid.';

  @override
  String get connectNow => 'Ühenda kohe';
}
