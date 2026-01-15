// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Danish (`da`).
class AppLocalizationsDa extends AppLocalizations {
  AppLocalizationsDa([String locale = 'da']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Samtale';

  @override
  String get transcriptTab => 'Udskrift';

  @override
  String get actionItemsTab => 'Handlingspunkter';

  @override
  String get deleteConversationTitle => 'Slet samtale?';

  @override
  String get deleteConversationMessage =>
      'Er du sikker på, at du vil slette denne samtale? Denne handling kan ikke fortrydes.';

  @override
  String get confirm => 'Bekræft';

  @override
  String get cancel => 'Cancel';

  @override
  String get ok => 'Ok';

  @override
  String get delete => 'Delete';

  @override
  String get add => 'Tilføj';

  @override
  String get update => 'Opdater';

  @override
  String get save => 'Gem';

  @override
  String get edit => 'Rediger';

  @override
  String get close => 'Luk';

  @override
  String get clear => 'Ryd';

  @override
  String get copyTranscript => 'Kopier udskrift';

  @override
  String get copySummary => 'Kopier sammenfatning';

  @override
  String get testPrompt => 'Test prompt';

  @override
  String get reprocessConversation => 'Genbehandl samtale';

  @override
  String get deleteConversation => 'Slet samtale';

  @override
  String get contentCopied => 'Indhold kopieret til udklipsholder';

  @override
  String get failedToUpdateStarred => 'Kunne ikke opdatere stjerne-status.';

  @override
  String get conversationUrlNotShared => 'Samtale-URL kunne ikke deles.';

  @override
  String get errorProcessingConversation => 'Fejl under behandling af samtale. Prøv venligst igen senere.';

  @override
  String get noInternetConnection => 'Tjek venligst din internetforbindelse og prøv igen.';

  @override
  String get unableToDeleteConversation => 'Kan ikke slette samtale';

  @override
  String get somethingWentWrong => 'Noget gik galt! Prøv venligst igen senere.';

  @override
  String get copyErrorMessage => 'Kopier fejlbesked';

  @override
  String get errorCopied => 'Fejlbesked kopieret til udklipsholder';

  @override
  String get remaining => 'Resterende';

  @override
  String get loading => 'Indlæser...';

  @override
  String get loadingDuration => 'Indlæser varighed...';

  @override
  String secondsCount(int count) {
    return '$count sekunder';
  }

  @override
  String get people => 'Personer';

  @override
  String get addNewPerson => 'Tilføj ny person';

  @override
  String get editPerson => 'Rediger person';

  @override
  String get createPersonHint => 'Opret en ny person og træn Omi til at genkende deres tale også!';

  @override
  String get speechProfile => 'Taleprofil';

  @override
  String sampleNumber(int number) {
    return 'Prøve $number';
  }

  @override
  String get settings => 'Indstillinger';

  @override
  String get language => 'Sprog';

  @override
  String get selectLanguage => 'Vælg sprog';

  @override
  String get deleting => 'Sletter...';

  @override
  String get pleaseCompleteAuthentication =>
      'Fuldfør venligst godkendelse i din browser. Når det er færdigt, vend tilbage til appen.';

  @override
  String get failedToStartAuthentication => 'Kunne ikke starte godkendelse';

  @override
  String get importStarted => 'Import startet! Du får besked når den er færdig.';

  @override
  String get failedToStartImport => 'Kunne ikke starte import. Prøv venligst igen.';

  @override
  String get couldNotAccessFile => 'Kunne ikke få adgang til den valgte fil';

  @override
  String get askOmi => 'Spørg Omi';

  @override
  String get done => 'Done';

  @override
  String get disconnected => 'Frakoblet';

  @override
  String get searching => 'Søger';

  @override
  String get connectDevice => 'Tilslut enhed';

  @override
  String get monthlyLimitReached => 'Du har nået din månedlige grænse.';

  @override
  String get checkUsage => 'Tjek forbrug';

  @override
  String get syncingRecordings => 'Synkroniserer optagelser';

  @override
  String get recordingsToSync => 'Optagelser til synkronisering';

  @override
  String get allCaughtUp => 'Alt er opdateret';

  @override
  String get sync => 'Synkroniser';

  @override
  String get pendantUpToDate => 'Vedhæng er opdateret';

  @override
  String get allRecordingsSynced => 'Alle optagelser er synkroniseret';

  @override
  String get syncingInProgress => 'Synkronisering i gang';

  @override
  String get readyToSync => 'Klar til synkronisering';

  @override
  String get tapSyncToStart => 'Tryk på Synkroniser for at starte';

  @override
  String get pendantNotConnected => 'Vedhæng ikke tilsluttet. Tilslut for at synkronisere.';

  @override
  String get everythingSynced => 'Alt er allerede synkroniseret.';

  @override
  String get recordingsNotSynced => 'Du har optagelser, der ikke er synkroniseret endnu.';

  @override
  String get syncingBackground => 'Vi fortsætter med at synkronisere dine optagelser i baggrunden.';

  @override
  String get noConversationsYet => 'Ingen samtaler endnu.';

  @override
  String get noStarredConversations => 'Ingen stjernemarkerede samtaler endnu.';

  @override
  String get starConversationHint =>
      'For at stjernemarkere en samtale skal du åbne den og trykke på stjerneikonet i overskriften.';

  @override
  String get searchConversations => 'Søg samtaler';

  @override
  String selectedCount(int count, Object s) {
    return '$count valgt';
  }

  @override
  String get merge => 'Flet';

  @override
  String get mergeConversations => 'Flet samtaler';

  @override
  String mergeConversationsMessage(int count) {
    return 'Dette vil kombinere $count samtaler til én. Alt indhold vil blive flettet og regenereret.';
  }

  @override
  String get mergingInBackground => 'Fletter i baggrunden. Dette kan tage et øjeblik.';

  @override
  String get failedToStartMerge => 'Kunne ikke starte fletning';

  @override
  String get askAnything => 'Spørg om hvad som helst';

  @override
  String get noMessagesYet => 'Ingen beskeder endnu!\nHvorfor starter du ikke en samtale?';

  @override
  String get deletingMessages => 'Sletter dine beskeder fra Omis hukommelse...';

  @override
  String get messageCopied => 'Besked kopieret til udklipsholder.';

  @override
  String get cannotReportOwnMessage => 'Du kan ikke rapportere dine egne beskeder.';

  @override
  String get reportMessage => 'Rapporter besked';

  @override
  String get reportMessageConfirm => 'Er du sikker på, at du vil rapportere denne besked?';

  @override
  String get messageReported => 'Besked rapporteret.';

  @override
  String get thankYouFeedback => 'Tak for din feedback!';

  @override
  String get clearChat => 'Ryd chat?';

  @override
  String get clearChatConfirm => 'Er du sikker på, at du vil rydde chatten? Denne handling kan ikke fortrydes.';

  @override
  String get maxFilesLimit => 'Du kan kun uploade 4 filer ad gangen';

  @override
  String get chatWithOmi => 'Chat med Omi';

  @override
  String get apps => 'Apps';

  @override
  String get noAppsFound => 'Ingen apps fundet';

  @override
  String get tryAdjustingSearch => 'Prøv at justere din søgning eller filtre';

  @override
  String get createYourOwnApp => 'Opret din egen app';

  @override
  String get buildAndShareApp => 'Byg og del din tilpassede app';

  @override
  String get searchApps => 'Søg i 1500+ apps';

  @override
  String get myApps => 'Mine apps';

  @override
  String get installedApps => 'Installerede apps';

  @override
  String get unableToFetchApps => 'Kan ikke hente apps :(\n\nTjek venligst din internetforbindelse og prøv igen.';

  @override
  String get aboutOmi => 'Om Omi';

  @override
  String get privacyPolicy => 'Privacy Policy';

  @override
  String get visitWebsite => 'Besøg hjemmeside';

  @override
  String get helpOrInquiries => 'Hjælp eller forespørgsler?';

  @override
  String get joinCommunity => 'Bliv en del af fællesskabet!';

  @override
  String get membersAndCounting => '8000+ medlemmer og tæller.';

  @override
  String get deleteAccountTitle => 'Slet konto';

  @override
  String get deleteAccountConfirm => 'Er du sikker på, at du vil slette din konto?';

  @override
  String get cannotBeUndone => 'Dette kan ikke fortrydes.';

  @override
  String get allDataErased => 'Alle dine minder og samtaler vil blive permanent slettet.';

  @override
  String get appsDisconnected => 'Dine apps og integrationer vil blive afbrudt øjeblikkeligt.';

  @override
  String get exportBeforeDelete =>
      'Du kan eksportere dine data før du sletter din konto, men når den er slettet, kan den ikke gendannes.';

  @override
  String get deleteAccountCheckbox =>
      'Jeg forstår, at sletning af min konto er permanent, og at alle data, inklusive minder og samtaler, vil gå tabt og ikke kan gendannes.';

  @override
  String get areYouSure => 'Er du sikker?';

  @override
  String get deleteAccountFinal =>
      'Denne handling er irreversibel og vil permanent slette din konto og alle tilknyttede data. Er du sikker på, at du vil fortsætte?';

  @override
  String get deleteNow => 'Slet nu';

  @override
  String get goBack => 'Gå tilbage';

  @override
  String get checkBoxToConfirm =>
      'Marker afkrydsningsfeltet for at bekræfte, at du forstår, at sletning af din konto er permanent og irreversibel.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Navn';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Brugerdefineret ordforråd';

  @override
  String get identifyingOthers => 'Identifikation af andre';

  @override
  String get paymentMethods => 'Betalingsmetoder';

  @override
  String get conversationDisplay => 'Samtalevisning';

  @override
  String get dataPrivacy => 'Data og privatliv';

  @override
  String get userId => 'Bruger-ID';

  @override
  String get notSet => 'Ikke angivet';

  @override
  String get userIdCopied => 'Bruger-ID kopieret til udklipsholder';

  @override
  String get systemDefault => 'Systemstandard';

  @override
  String get planAndUsage => 'Plan og forbrug';

  @override
  String get offlineSync => 'Offline synkronisering';

  @override
  String get deviceSettings => 'Enhedsindstillinger';

  @override
  String get chatTools => 'Chatværktøjer';

  @override
  String get feedbackBug => 'Feedback / Fejl';

  @override
  String get helpCenter => 'Hjælpecenter';

  @override
  String get developerSettings => 'Udviklerindstillinger';

  @override
  String get getOmiForMac => 'Få Omi til Mac';

  @override
  String get referralProgram => 'Henvisningsprogram';

  @override
  String get signOut => 'Log ud';

  @override
  String get appAndDeviceCopied => 'App- og enhedsdetaljer kopieret';

  @override
  String get wrapped2025 => 'Opsamling 2025';

  @override
  String get yourPrivacyYourControl => 'Dit privatliv, din kontrol';

  @override
  String get privacyIntro =>
      'Hos Omi er vi forpligtede til at beskytte dit privatliv. Denne side giver dig mulighed for at styre, hvordan dine data gemmes og bruges.';

  @override
  String get learnMore => 'Læs mere...';

  @override
  String get dataProtectionLevel => 'Databeskyttelsesniveau';

  @override
  String get dataProtectionDesc =>
      'Dine data er som standard sikret med stærk kryptering. Gennemgå dine indstillinger og fremtidige privatlivsindstillinger nedenfor.';

  @override
  String get appAccess => 'App-adgang';

  @override
  String get appAccessDesc =>
      'Følgende apps kan få adgang til dine data. Tryk på en app for at administrere dens tilladelser.';

  @override
  String get noAppsExternalAccess => 'Ingen installerede apps har ekstern adgang til dine data.';

  @override
  String get deviceName => 'Enhedsnavn';

  @override
  String get deviceId => 'Enheds-ID';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'SD-kort synkronisering';

  @override
  String get hardwareRevision => 'Hardware-revision';

  @override
  String get modelNumber => 'Modelnummer';

  @override
  String get manufacturer => 'Producent';

  @override
  String get doubleTap => 'Dobbelttryk';

  @override
  String get ledBrightness => 'LED-lysstyrke';

  @override
  String get micGain => 'Mikrofonforstærkning';

  @override
  String get disconnect => 'Afbryd';

  @override
  String get forgetDevice => 'Glem enhed';

  @override
  String get chargingIssues => 'Opladningsproblemer';

  @override
  String get disconnectDevice => 'Afbryd enhed';

  @override
  String get unpairDevice => 'Afpar enhed';

  @override
  String get unpairAndForget => 'Afpar og glem enhed';

  @override
  String get deviceDisconnectedMessage => 'Din Omi er blevet afbrudt 😔';

  @override
  String get deviceUnpairedMessage =>
      'Enhed afparret. Gå til Indstillinger > Bluetooth og glem enheden for at fuldføre afparringen.';

  @override
  String get unpairDialogTitle => 'Afpar enhed';

  @override
  String get unpairDialogMessage =>
      'Dette vil afparre enheden, så den kan tilsluttes en anden telefon. Du skal gå til Indstillinger > Bluetooth og glemme enheden for at fuldføre processen.';

  @override
  String get deviceNotConnected => 'Enhed ikke tilsluttet';

  @override
  String get connectDeviceMessage => 'Tilslut din Omi-enhed for at få adgang til\nenhedsindstillinger og tilpasning';

  @override
  String get deviceInfoSection => 'Enhedsinformation';

  @override
  String get customizationSection => 'Tilpasning';

  @override
  String get hardwareSection => 'Hardware';

  @override
  String get v2Undetected => 'V2 ikke opdaget';

  @override
  String get v2UndetectedMessage =>
      'Vi kan se, at du enten har en V1-enhed, eller at din enhed ikke er tilsluttet. SD-kort-funktionalitet er kun tilgængelig for V2-enheder.';

  @override
  String get endConversation => 'Afslut samtale';

  @override
  String get pauseResume => 'Pause/Genoptag';

  @override
  String get starConversation => 'Stjernemarkér samtale';

  @override
  String get doubleTapAction => 'Dobbelttryk-handling';

  @override
  String get endAndProcess => 'Afslut og behandl samtale';

  @override
  String get pauseResumeRecording => 'Pause/Genoptag optagelse';

  @override
  String get starOngoing => 'Stjernemarkér igangværende samtale';

  @override
  String get off => 'Fra';

  @override
  String get max => 'Maks';

  @override
  String get mute => 'Lydløs';

  @override
  String get quiet => 'Stille';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Høj';

  @override
  String get micGainDescMuted => 'Mikrofon er lydløs';

  @override
  String get micGainDescLow => 'Meget stille - til høje omgivelser';

  @override
  String get micGainDescModerate => 'Stille - til moderat støj';

  @override
  String get micGainDescNeutral => 'Neutral - afbalanceret optagelse';

  @override
  String get micGainDescSlightlyBoosted => 'Let forstærket - normal brug';

  @override
  String get micGainDescBoosted => 'Forstærket - til stille omgivelser';

  @override
  String get micGainDescHigh => 'Høj - til fjerne eller bløde stemmer';

  @override
  String get micGainDescVeryHigh => 'Meget høj - til meget stille kilder';

  @override
  String get micGainDescMax => 'Maksimum - brug med forsigtighed';

  @override
  String get developerSettingsTitle => 'Udviklerindstillinger';

  @override
  String get saving => 'Saving...';

  @override
  String get personaConfig => 'Konfigurer din AI-persona';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transcription';

  @override
  String get transcriptionConfig => 'Konfigurer STT-udbyder';

  @override
  String get conversationTimeout => 'Samtale timeout';

  @override
  String get conversationTimeoutConfig => 'Indstil hvornår samtaler automatisk afsluttes';

  @override
  String get importData => 'Importer data';

  @override
  String get importDataConfig => 'Importer data fra andre kilder';

  @override
  String get debugDiagnostics => 'Debug og diagnostik';

  @override
  String get endpointUrl => 'Endpoint URL';

  @override
  String get noApiKeys => 'Ingen API-nøgler endnu';

  @override
  String get createKeyToStart => 'Opret en nøgle for at komme i gang';

  @override
  String get createKey => 'Opret nøgle';

  @override
  String get docs => 'Dokumentation';

  @override
  String get yourOmiInsights => 'Dine Omi-indsigter';

  @override
  String get today => 'I dag';

  @override
  String get thisMonth => 'Denne måned';

  @override
  String get thisYear => 'Dette år';

  @override
  String get allTime => 'Altid';

  @override
  String get noActivityYet => 'Ingen aktivitet endnu';

  @override
  String get startConversationToSeeInsights => 'Start en samtale med Omi\nfor at se dine forbrugsindsigter her.';

  @override
  String get listening => 'Lytter';

  @override
  String get listeningSubtitle => 'Samlet tid Omi har lyttet aktivt.';

  @override
  String get understanding => 'Forstår';

  @override
  String get understandingSubtitle => 'Ord forstået fra dine samtaler.';

  @override
  String get providing => 'Leverer';

  @override
  String get providingSubtitle => 'Handlingspunkter og notater automatisk registreret.';

  @override
  String get remembering => 'Husker';

  @override
  String get rememberingSubtitle => 'Fakta og detaljer husket for dig.';

  @override
  String get unlimitedPlan => 'Ubegrænset plan';

  @override
  String get managePlan => 'Administrer plan';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Din plan annulleres den $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Din plan fornyes den $date.';
  }

  @override
  String get basicPlan => 'Gratis plan';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used af $limit min brugt';
  }

  @override
  String get upgrade => 'Opgrader';

  @override
  String get upgradeToUnlimited => 'Opgrader til ubegrænset';

  @override
  String basicPlanDesc(int limit) {
    return 'Din plan inkluderer $limit gratis minutter om måneden. Opgrader for at få ubegrænset.';
  }

  @override
  String get shareStatsMessage => 'Deler mine Omi-statistikker! (omi.me - din altid-aktive AI-assistent)';

  @override
  String get sharePeriodToday => 'I dag har omi:';

  @override
  String get sharePeriodMonth => 'Denne måned har omi:';

  @override
  String get sharePeriodYear => 'Dette år har omi:';

  @override
  String get sharePeriodAllTime => 'Indtil videre har omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Lyttet i $minutes minutter';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Forstået $words ord';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Leveret $count indsigter';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Husket $count minder';
  }

  @override
  String get debugLogs => 'Debug-logfiler';

  @override
  String get debugLogsAutoDelete => 'Slettes automatisk efter 3 dage.';

  @override
  String get debugLogsDesc => 'Hjælper med at diagnosticere problemer';

  @override
  String get noLogFilesFound => 'Ingen logfiler fundet.';

  @override
  String get omiDebugLog => 'Omi debug-log';

  @override
  String get logShared => 'Log delt';

  @override
  String get selectLogFile => 'Vælg logfil';

  @override
  String get shareLogs => 'Del logfiler';

  @override
  String get debugLogCleared => 'Debug-log ryddet';

  @override
  String get exportStarted => 'Eksport startet. Dette kan tage et par sekunder...';

  @override
  String get exportAllData => 'Eksporter alle data';

  @override
  String get exportDataDesc => 'Eksporter samtaler til en JSON-fil';

  @override
  String get exportedConversations => 'Eksporterede samtaler fra Omi';

  @override
  String get exportShared => 'Eksport delt';

  @override
  String get deleteKnowledgeGraphTitle => 'Slet videngraf?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Dette vil slette alle afledte videngraf-data (noder og forbindelser). Dine originale minder forbliver sikre. Grafen vil blive genopbygget over tid eller ved næste anmodning.';

  @override
  String get knowledgeGraphDeleted => 'Videngraf slettet';

  @override
  String deleteGraphFailed(String error) {
    return 'Kunne ikke slette graf: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Slet videngraf';

  @override
  String get deleteKnowledgeGraphDesc => 'Ryd alle noder og forbindelser';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP-server';

  @override
  String get mcpServerDesc => 'Forbind AI-assistenter til dine data';

  @override
  String get serverUrl => 'Server-URL';

  @override
  String get urlCopied => 'URL kopieret';

  @override
  String get apiKeyAuth => 'API-nøglegodkendelse';

  @override
  String get header => 'Header';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Klient-ID';

  @override
  String get clientSecret => 'Klient-hemmelighed';

  @override
  String get useMcpApiKey => 'Brug din MCP API-nøgle';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Samtalehændelser';

  @override
  String get newConversationCreated => 'Ny samtale oprettet';

  @override
  String get realtimeTranscript => 'Realtids-udskrift';

  @override
  String get transcriptReceived => 'Udskrift modtaget';

  @override
  String get audioBytes => 'Lyd-bytes';

  @override
  String get audioDataReceived => 'Lyddata modtaget';

  @override
  String get intervalSeconds => 'Interval (sekunder)';

  @override
  String get daySummary => 'Dagsammenfatning';

  @override
  String get summaryGenerated => 'Sammenfatning genereret';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Tilføj til claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopier konfiguration';

  @override
  String get configCopied => 'Konfiguration kopieret til udklipsholder';

  @override
  String get listeningMins => 'Lytning (min)';

  @override
  String get understandingWords => 'Forståelse (ord)';

  @override
  String get insights => 'Indsigter';

  @override
  String get memories => 'Minder';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used af $limit min brugt denne måned';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used af $limit ord brugt denne måned';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used af $limit indsigter opnået denne måned';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used af $limit minder oprettet denne måned';
  }

  @override
  String get visibility => 'Synlighed';

  @override
  String get visibilitySubtitle => 'Styr hvilke samtaler der vises i din liste';

  @override
  String get showShortConversations => 'Vis korte samtaler';

  @override
  String get showShortConversationsDesc => 'Vis samtaler kortere end tærsklen';

  @override
  String get showDiscardedConversations => 'Vis kasserede samtaler';

  @override
  String get showDiscardedConversationsDesc => 'Inkluder samtaler markeret som kasseret';

  @override
  String get shortConversationThreshold => 'Kort samtale-tærskel';

  @override
  String get shortConversationThresholdSubtitle =>
      'Samtaler kortere end denne vil blive skjult, medmindre aktiveret ovenfor';

  @override
  String get durationThreshold => 'Varighedstærskel';

  @override
  String get durationThresholdDesc => 'Skjul samtaler kortere end denne';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Brugerdefineret ordforråd';

  @override
  String get addWords => 'Tilføj ord';

  @override
  String get addWordsDesc => 'Navne, termer eller usædvanlige ord';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connect';

  @override
  String get comingSoon => 'Kommer snart';

  @override
  String get chatToolsFooter => 'Forbind dine apps for at se data og målinger i chat.';

  @override
  String get completeAuthInBrowser =>
      'Fuldfør venligst godkendelse i din browser. Når det er færdigt, vend tilbage til appen.';

  @override
  String failedToStartAuth(String appName) {
    return 'Kunne ikke starte $appName-godkendelse';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Afbryd $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Er du sikker på, at du vil afbryde forbindelsen til $appName? Du kan genoprette forbindelsen når som helst.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Afbrudt fra $appName';
  }

  @override
  String get failedToDisconnect => 'Kunne ikke afbryde';

  @override
  String connectTo(String appName) {
    return 'Tilslut til $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Du skal give Omi tilladelse til at få adgang til dine $appName-data. Dette åbner din browser til godkendelse.';
  }

  @override
  String get continueAction => 'Fortsæt';

  @override
  String get languageTitle => 'Sprog';

  @override
  String get primaryLanguage => 'Primært sprog';

  @override
  String get automaticTranslation => 'Automatisk oversættelse';

  @override
  String get detectLanguages => 'Registrer 10+ sprog';

  @override
  String get authorizeSavingRecordings => 'Godkend lagring af optagelser';

  @override
  String get thanksForAuthorizing => 'Tak for godkendelsen!';

  @override
  String get needYourPermission => 'Vi har brug for din tilladelse';

  @override
  String get alreadyGavePermission =>
      'Du har allerede givet os tilladelse til at gemme dine optagelser. Her er en påmindelse om, hvorfor vi har brug for det:';

  @override
  String get wouldLikePermission =>
      'Vi vil gerne have din tilladelse til at gemme dine stemmeoptagelser. Her er hvorfor:';

  @override
  String get improveSpeechProfile => 'Forbedr din taleprofil';

  @override
  String get improveSpeechProfileDesc =>
      'Vi bruger optagelser til yderligere at træne og forbedre din personlige taleprofil.';

  @override
  String get trainFamilyProfiles => 'Træn profiler for venner og familie';

  @override
  String get trainFamilyProfilesDesc =>
      'Dine optagelser hjælper os med at genkende og oprette profiler for dine venner og familie.';

  @override
  String get enhanceTranscriptAccuracy => 'Forbedr udskriftspræcision';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Efterhånden som vores model forbedres, kan vi levere bedre transskriptionsresultater for dine optagelser.';

  @override
  String get legalNotice =>
      'Juridisk meddelelse: Lovligheden af at optage og gemme stemmedata kan variere afhængigt af din placering og hvordan du bruger denne funktion. Det er dit ansvar at sikre overholdelse af lokale love og regler.';

  @override
  String get alreadyAuthorized => 'Allerede godkendt';

  @override
  String get authorize => 'Godkend';

  @override
  String get revokeAuthorization => 'Tilbagekald godkendelse';

  @override
  String get authorizationSuccessful => 'Godkendelse vellykket!';

  @override
  String get failedToAuthorize => 'Kunne ikke godkende. Prøv venligst igen.';

  @override
  String get authorizationRevoked => 'Godkendelse tilbagekaldt.';

  @override
  String get recordingsDeleted => 'Optagelser slettet.';

  @override
  String get failedToRevoke => 'Kunne ikke tilbagekalde godkendelse. Prøv venligst igen.';

  @override
  String get permissionRevokedTitle => 'Tilladelse tilbagekaldt';

  @override
  String get permissionRevokedMessage => 'Vil du have os til også at fjerne alle dine eksisterende optagelser?';

  @override
  String get yes => 'Ja';

  @override
  String get editName => 'Rediger navn';

  @override
  String get howShouldOmiCallYou => 'Hvad skal Omi kalde dig?';

  @override
  String get enterYourName => 'Enter your name';

  @override
  String get nameCannotBeEmpty => 'Navn kan ikke være tomt';

  @override
  String get nameUpdatedSuccessfully => 'Navn opdateret!';

  @override
  String get calendarSettings => 'Kalenderindstillinger';

  @override
  String get calendarProviders => 'Kalenderudbydere';

  @override
  String get macOsCalendar => 'macOS-kalender';

  @override
  String get connectMacOsCalendar => 'Tilslut din lokale macOS-kalender';

  @override
  String get googleCalendar => 'Google Calendar';

  @override
  String get syncGoogleAccount => 'Synkroniser med din Google-konto';

  @override
  String get showMeetingsMenuBar => 'Vis kommende møder i menulinjen';

  @override
  String get showMeetingsMenuBarDesc => 'Vis dit næste møde og tid indtil det starter i macOS-menulinjen';

  @override
  String get showEventsNoParticipants => 'Vis begivenheder uden deltagere';

  @override
  String get showEventsNoParticipantsDesc =>
      'Når aktiveret, viser Kommende begivenheder uden deltagere eller videolink.';

  @override
  String get yourMeetings => 'Dine møder';

  @override
  String get refresh => 'Opdater';

  @override
  String get noUpcomingMeetings => 'Ingen kommende møder fundet';

  @override
  String get checkingNextDays => 'Tjekker de næste 30 dage';

  @override
  String get tomorrow => 'I morgen';

  @override
  String get googleCalendarComingSoon => 'Google Calendar-integration kommer snart!';

  @override
  String connectedAsUser(String userId) {
    return 'Tilsluttet som bruger: $userId';
  }

  @override
  String get defaultWorkspace => 'Standard arbejdsområde';

  @override
  String get tasksCreatedInWorkspace => 'Opgaver oprettes i dette arbejdsområde';

  @override
  String get defaultProjectOptional => 'Standardprojekt (valgfrit)';

  @override
  String get leaveUnselectedTasks => 'Lad være uvalgt for at oprette opgaver uden projekt';

  @override
  String get noProjectsInWorkspace => 'Ingen projekter fundet i dette arbejdsområde';

  @override
  String get conversationTimeoutDesc =>
      'Vælg hvor længe der skal ventes i stilhed før automatisk afslutning af samtale:';

  @override
  String get timeout2Minutes => '2 minutter';

  @override
  String get timeout2MinutesDesc => 'Afslut samtale efter 2 minutters stilhed';

  @override
  String get timeout5Minutes => '5 minutter';

  @override
  String get timeout5MinutesDesc => 'Afslut samtale efter 5 minutters stilhed';

  @override
  String get timeout10Minutes => '10 minutter';

  @override
  String get timeout10MinutesDesc => 'Afslut samtale efter 10 minutters stilhed';

  @override
  String get timeout30Minutes => '30 minutter';

  @override
  String get timeout30MinutesDesc => 'Afslut samtale efter 30 minutters stilhed';

  @override
  String get timeout4Hours => '4 timer';

  @override
  String get timeout4HoursDesc => 'Afslut samtale efter 4 timers stilhed';

  @override
  String get conversationEndAfterHours => 'Samtaler afsluttes nu efter 4 timers stilhed';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Samtaler afsluttes nu efter $minutes minut(ter) i stilhed';
  }

  @override
  String get tellUsPrimaryLanguage => 'Fortæl os dit primære sprog';

  @override
  String get languageForTranscription => 'Indstil dit sprog for skarpere transskriptioner og en personlig oplevelse.';

  @override
  String get singleLanguageModeInfo =>
      'Enkeltsprogs-tilstand er aktiveret. Oversættelse er deaktiveret for højere nøjagtighed.';

  @override
  String get searchLanguageHint => 'Search language by name or code';

  @override
  String get noLanguagesFound => 'No languages found';

  @override
  String get skip => 'Spring over';

  @override
  String languageSetTo(String language) {
    return 'Sprog indstillet til $language';
  }

  @override
  String get failedToSetLanguage => 'Kunne ikke indstille sprog';

  @override
  String appSettings(String appName) {
    return '$appName Settings';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Disconnect from $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'This will remove your $appName authentication. You\'ll need to reconnect to use it again.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Connected to $appName';
  }

  @override
  String get account => 'Account';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Your action items will be synced to your $appName account';
  }

  @override
  String get defaultSpace => 'Default Space';

  @override
  String get selectSpaceInWorkspace => 'Select a space in your workspace';

  @override
  String get noSpacesInWorkspace => 'No spaces found in this workspace';

  @override
  String get defaultList => 'Default List';

  @override
  String get tasksAddedToList => 'Tasks will be added to this list';

  @override
  String get noListsInSpace => 'No lists found in this space';

  @override
  String failedToLoadRepos(String error) {
    return 'Failed to load repositories: $error';
  }

  @override
  String get defaultRepoSaved => 'Default repository saved';

  @override
  String get failedToSaveDefaultRepo => 'Failed to save default repository';

  @override
  String get defaultRepository => 'Default Repository';

  @override
  String get selectDefaultRepoDesc =>
      'Select a default repository for creating issues. You can still specify a different repository when creating issues.';

  @override
  String get noReposFound => 'No repositories found';

  @override
  String get private => 'Private';

  @override
  String updatedDate(String date) {
    return 'Updated $date';
  }

  @override
  String get yesterday => 'yesterday';

  @override
  String daysAgo(int count) {
    return '$count days ago';
  }

  @override
  String get oneWeekAgo => '1 week ago';

  @override
  String weeksAgo(int count) {
    return '$count weeks ago';
  }

  @override
  String get oneMonthAgo => '1 month ago';

  @override
  String monthsAgo(int count) {
    return '$count months ago';
  }

  @override
  String get issuesCreatedInRepo => 'Issues will be created in your default repository';

  @override
  String get taskIntegrations => 'Task Integrations';

  @override
  String get configureSettings => 'Configure Settings';

  @override
  String get completeAuthBrowser => 'Please complete authentication in your browser. Once done, return to the app.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Failed to start $appName authentication';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Connect to $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'You\'ll need to authorize Omi to create tasks in your $appName account. This will open your browser for authentication.';
  }

  @override
  String get continueButton => 'Continue';

  @override
  String appIntegration(String appName) {
    return '$appName Integration';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integration with $appName is coming soon! We\'re working hard to bring you more task management options.';
  }

  @override
  String get gotIt => 'Got it';

  @override
  String get tasksExportedOneApp => 'Tasks can be exported to one app at a time.';

  @override
  String get completeYourUpgrade => 'Complete Your Upgrade';

  @override
  String get importConfiguration => 'Import Configuration';

  @override
  String get exportConfiguration => 'Export configuration';

  @override
  String get bringYourOwn => 'Bring your own';

  @override
  String get payYourSttProvider => 'Freely use omi. You only pay your STT provider directly.';

  @override
  String get freeMinutesMonth => '1,200 free minutes/month included. Unlimited with ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Host is required';

  @override
  String get validPortRequired => 'Valid port is required';

  @override
  String get validWebsocketUrlRequired => 'Valid WebSocket URL is required (wss://)';

  @override
  String get apiUrlRequired => 'API URL is required';

  @override
  String get apiKeyRequired => 'API key is required';

  @override
  String get invalidJsonConfig => 'Invalid JSON configuration';

  @override
  String errorSaving(String error) {
    return 'Error saving: $error';
  }

  @override
  String get configCopiedToClipboard => 'Configuration copied to clipboard';

  @override
  String get pasteJsonConfig => 'Paste your JSON configuration below:';

  @override
  String get addApiKeyAfterImport => 'You\'ll need to add your own API key after importing';

  @override
  String get paste => 'Paste';

  @override
  String get import => 'Import';

  @override
  String get invalidProviderInConfig => 'Invalid provider in configuration';

  @override
  String importedConfig(String providerName) {
    return 'Imported $providerName configuration';
  }

  @override
  String invalidJson(String error) {
    return 'Invalid JSON: $error';
  }

  @override
  String get provider => 'Provider';

  @override
  String get live => 'Live';

  @override
  String get onDevice => 'On Device';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Enter your STT HTTP endpoint';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Enter your live STT WebSocket endpoint';

  @override
  String get apiKey => 'API Key';

  @override
  String get enterApiKey => 'Enter your API key';

  @override
  String get storedLocallyNeverShared => 'Stored locally, never shared';

  @override
  String get host => 'Host';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Advanced';

  @override
  String get configuration => 'Configuration';

  @override
  String get requestConfiguration => 'Request Configuration';

  @override
  String get responseSchema => 'Response Schema';

  @override
  String get modified => 'Modified';

  @override
  String get resetRequestConfig => 'Reset request config to default';

  @override
  String get logs => 'Logs';

  @override
  String get logsCopied => 'Logs copied';

  @override
  String get noLogsYet => 'No logs yet. Start recording to see custom STT activity.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName uses $codecReason. Omi will be used.';
  }

  @override
  String get omiTranscription => 'Omi Transcription';

  @override
  String get bestInClassTranscription => 'Best in class transcription with zero setup';

  @override
  String get instantSpeakerLabels => 'Instant speaker labels';

  @override
  String get languageTranslation => '100+ language translation';

  @override
  String get optimizedForConversation => 'Optimized for conversation';

  @override
  String get autoLanguageDetection => 'Auto language detection';

  @override
  String get highAccuracy => 'High accuracy';

  @override
  String get privacyFirst => 'Privacy first';

  @override
  String get saveChanges => 'Save Changes';

  @override
  String get resetToDefault => 'Reset to Default';

  @override
  String get viewTemplate => 'View Template';

  @override
  String get trySomethingLike => 'Try something like...';

  @override
  String get tryIt => 'Try it';

  @override
  String get creatingPlan => 'Creating plan';

  @override
  String get developingLogic => 'Developing logic';

  @override
  String get designingApp => 'Designing app';

  @override
  String get generatingIconStep => 'Generating icon';

  @override
  String get finalTouches => 'Final touches';

  @override
  String get processing => 'Processing...';

  @override
  String get features => 'Features';

  @override
  String get creatingYourApp => 'Creating your app...';

  @override
  String get generatingIcon => 'Generating icon...';

  @override
  String get whatShouldWeMake => 'What should we make?';

  @override
  String get appName => 'App Name';

  @override
  String get description => 'Description';

  @override
  String get publicLabel => 'Public';

  @override
  String get privateLabel => 'Private';

  @override
  String get free => 'Free';

  @override
  String get perMonth => '/ Month';

  @override
  String get tailoredConversationSummaries => 'Tailored Conversation Summaries';

  @override
  String get customChatbotPersonality => 'Custom Chatbot Personality';

  @override
  String get makePublic => 'Make public';

  @override
  String get anyoneCanDiscover => 'Anyone can discover your app';

  @override
  String get onlyYouCanUse => 'Only you can use this app';

  @override
  String get paidApp => 'Paid app';

  @override
  String get usersPayToUse => 'Users pay to use your app';

  @override
  String get freeForEveryone => 'Free for everyone';

  @override
  String get perMonthLabel => '/ month';

  @override
  String get creating => 'Creating...';

  @override
  String get createApp => 'Create App';

  @override
  String get searchingForDevices => 'Searching for devices...';

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
  String get pairingSuccessful => 'PAIRING SUCCESSFUL';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Error connecting to Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Don\'t show it again';

  @override
  String get iUnderstand => 'I Understand';

  @override
  String get enableBluetooth => 'Enable Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.';

  @override
  String get contactSupport => 'Contact Support?';

  @override
  String get connectLater => 'Connect Later';

  @override
  String get grantPermissions => 'Grant permissions';

  @override
  String get backgroundActivity => 'Background activity';

  @override
  String get backgroundActivityDesc => 'Let Omi run in the background for better stability';

  @override
  String get locationAccess => 'Location access';

  @override
  String get locationAccessDesc => 'Enable background location for the full experience';

  @override
  String get notifications => 'Notifications';

  @override
  String get notificationsDesc => 'Enable notifications to stay informed';

  @override
  String get locationServiceDisabled => 'Location Service Disabled';

  @override
  String get locationServiceDisabledDesc =>
      'Location Service is Disabled. Please go to Settings > Privacy & Security > Location Services and enable it';

  @override
  String get backgroundLocationDenied => 'Background Location Access Denied';

  @override
  String get backgroundLocationDeniedDesc =>
      'Please go to device settings and set location permission to \"Always Allow\"';

  @override
  String get lovingOmi => 'Loving Omi?';

  @override
  String get leaveReviewIos =>
      'Help us reach more people by leaving a review in the App Store. Your feedback means the world to us!';

  @override
  String get leaveReviewAndroid =>
      'Help us reach more people by leaving a review in the Google Play Store. Your feedback means the world to us!';

  @override
  String get rateOnAppStore => 'Rate on App Store';

  @override
  String get rateOnGooglePlay => 'Rate on Google Play';

  @override
  String get maybeLater => 'Maybe later';

  @override
  String get speechProfileIntro => 'Omi needs to learn your goals and your voice. You\'ll be able to modify it later.';

  @override
  String get getStarted => 'Get Started';

  @override
  String get allDone => 'All done!';

  @override
  String get keepGoing => 'Keep going, you are doing great';

  @override
  String get skipThisQuestion => 'Skip this question';

  @override
  String get skipForNow => 'Skip for now';

  @override
  String get connectionError => 'Connection Error';

  @override
  String get connectionErrorDesc =>
      'Failed to connect to the server. Please check your internet connection and try again.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Invalid recording detected';

  @override
  String get multipleSpeakersDesc =>
      'It seems like there are multiple speakers in the recording. Please make sure you are in a quiet location and try again.';

  @override
  String get tooShortDesc => 'There is not enough speech detected. Please speak more and try again.';

  @override
  String get invalidRecordingDesc => 'Please make sure you speak for at least 5 seconds and not more than 90.';

  @override
  String get areYouThere => 'Are you there?';

  @override
  String get noSpeechDesc =>
      'We could not detect any speech. Please make sure to speak for at least 10 seconds and not more than 3 minutes.';

  @override
  String get connectionLost => 'Connection Lost';

  @override
  String get connectionLostDesc =>
      'The connection was interrupted. Please check your internet connection and try again.';

  @override
  String get tryAgain => 'Try Again';

  @override
  String get connectOmiOmiGlass => 'Connect Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continue Without Device';

  @override
  String get permissionsRequired => 'Permissions Required';

  @override
  String get permissionsRequiredDesc =>
      'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.';

  @override
  String get openSettings => 'Open Settings';

  @override
  String get wantDifferentName => 'Want to go by something else?';

  @override
  String get whatsYourName => 'What\'s your name?';

  @override
  String get speakTranscribeSummarize => 'Speak. Transcribe. Summarize.';

  @override
  String get signInWithApple => 'Sign in with Apple';

  @override
  String get signInWithGoogle => 'Sign in with Google';

  @override
  String get byContinuingAgree => 'By continuing, you agree to our ';

  @override
  String get termsOfUse => 'Terms of Use';

  @override
  String get omiYourAiCompanion => 'Omi – Your AI Companion';

  @override
  String get captureEveryMoment => 'Capture every moment. Get AI-powered\nsummaries. Never take notes again.';

  @override
  String get appleWatchSetup => 'Apple Watch Setup';

  @override
  String get permissionRequestedExclaim => 'Permission Requested!';

  @override
  String get microphonePermission => 'Microphone Permission';

  @override
  String get permissionGrantedNow =>
      'Permission granted! Now:\n\nOpen the Omi app on your watch and tap \"Continue\" below';

  @override
  String get needMicrophonePermission =>
      'We need microphone permission.\n\n1. Tap \"Grant Permission\"\n2. Allow on your iPhone\n3. Watch app will close\n4. Reopen and tap \"Continue\"';

  @override
  String get grantPermissionButton => 'Grant Permission';

  @override
  String get needHelp => 'Need Help?';

  @override
  String get troubleshootingSteps =>
      'Troubleshooting:\n\n1. Ensure Omi is installed on your watch\n2. Open the Omi app on your watch\n3. Look for the permission popup\n4. Tap \"Allow\" when prompted\n5. App on your watch will close - reopen it\n6. Come back and tap \"Continue\" on your iPhone';

  @override
  String get recordingStartedSuccessfully => 'Recording started successfully!';

  @override
  String get permissionNotGrantedYet =>
      'Permission not granted yet. Please make sure you allowed microphone access and reopened the app on your watch.';

  @override
  String errorRequestingPermission(String error) {
    return 'Error requesting permission: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Error starting recording: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Select your primary language';

  @override
  String get languageBenefits => 'Set your language for sharper transcriptions and a personalized experience';

  @override
  String get whatsYourPrimaryLanguage => 'What\'s your primary language?';

  @override
  String get selectYourLanguage => 'Select your language';

  @override
  String get personalGrowthJourney => 'Your personal growth journey with AI that listens to your every word.';

  @override
  String get actionItemsTitle => 'To-Do\'s';

  @override
  String get actionItemsDescription => 'Tap to edit • Long press to select • Swipe for actions';

  @override
  String get tabToDo => 'To Do';

  @override
  String get tabDone => 'Done';

  @override
  String get tabOld => 'Old';

  @override
  String get emptyTodoMessage => '🎉 All caught up!\nNo pending action items';

  @override
  String get emptyDoneMessage => 'No completed items yet';

  @override
  String get emptyOldMessage => '✅ No old tasks';

  @override
  String get noItems => 'No items';

  @override
  String get actionItemMarkedIncomplete => 'Action item marked as incomplete';

  @override
  String get actionItemCompleted => 'Action item completed';

  @override
  String get deleteActionItemTitle => 'Delete Action Item';

  @override
  String get deleteActionItemMessage => 'Are you sure you want to delete this action item?';

  @override
  String get deleteSelectedItemsTitle => 'Delete Selected Items';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Are you sure you want to delete $count selected action item$s?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Action item \"$description\" deleted';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action item$s deleted';
  }

  @override
  String get failedToDeleteItem => 'Failed to delete action item';

  @override
  String get failedToDeleteItems => 'Failed to delete items';

  @override
  String get failedToDeleteSomeItems => 'Failed to delete some items';

  @override
  String get welcomeActionItemsTitle => 'Ready for Action Items';

  @override
  String get welcomeActionItemsDescription =>
      'Your AI will automatically extract tasks and to-dos from your conversations. They\'ll appear here when created.';

  @override
  String get autoExtractionFeature => 'Automatically extracted from conversations';

  @override
  String get editSwipeFeature => 'Tap to edit, swipe to complete or delete';

  @override
  String itemsSelected(int count) {
    return '$count selected';
  }

  @override
  String get selectAll => 'Select all';

  @override
  String get deleteSelected => 'Delete selected';

  @override
  String searchMemories(int count) {
    return 'Search $count Memories';
  }

  @override
  String get memoryDeleted => 'Memory Deleted.';

  @override
  String get undo => 'Undo';

  @override
  String get noMemoriesYet => 'No memories yet';

  @override
  String get noAutoMemories => 'No auto-extracted memories yet';

  @override
  String get noManualMemories => 'No manual memories yet';

  @override
  String get noMemoriesInCategories => 'No memories in these categories';

  @override
  String get noMemoriesFound => 'No memories found';

  @override
  String get addFirstMemory => 'Add your first memory';

  @override
  String get clearMemoryTitle => 'Clear Omi\'s Memory';

  @override
  String get clearMemoryMessage => 'Are you sure you want to clear Omi\'s memory? This action cannot be undone.';

  @override
  String get clearMemoryButton => 'Clear Memory';

  @override
  String get memoryClearedSuccess => 'Omi\'s memory about you has been cleared';

  @override
  String get noMemoriesToDelete => 'No memories to delete';

  @override
  String get createMemoryTooltip => 'Create new memory';

  @override
  String get createActionItemTooltip => 'Create new action item';

  @override
  String get memoryManagement => 'Memory Management';

  @override
  String get filterMemories => 'Filter Memories';

  @override
  String totalMemoriesCount(int count) {
    return 'You have $count total memories';
  }

  @override
  String get publicMemories => 'Public memories';

  @override
  String get privateMemories => 'Private memories';

  @override
  String get makeAllPrivate => 'Make All Memories Private';

  @override
  String get makeAllPublic => 'Make All Memories Public';

  @override
  String get deleteAllMemories => 'Delete All Memories';

  @override
  String get allMemoriesPrivateResult => 'All memories are now private';

  @override
  String get allMemoriesPublicResult => 'All memories are now public';

  @override
  String get newMemory => 'New Memory';

  @override
  String get editMemory => 'Edit Memory';

  @override
  String get memoryContentHint => 'I like to eat ice cream...';

  @override
  String get failedToSaveMemory => 'Failed to save. Please check your connection.';

  @override
  String get saveMemory => 'Save Memory';

  @override
  String get retry => 'Retry';

  @override
  String get createActionItem => 'Create Action Item';

  @override
  String get editActionItem => 'Edit Action Item';

  @override
  String get actionItemDescriptionHint => 'What needs to be done?';

  @override
  String get actionItemDescriptionEmpty => 'Action item description cannot be empty.';

  @override
  String get actionItemUpdated => 'Action item updated';

  @override
  String get failedToUpdateActionItem => 'Failed to update action item';

  @override
  String get actionItemCreated => 'Action item created';

  @override
  String get failedToCreateActionItem => 'Failed to create action item';

  @override
  String get dueDate => 'Due Date';

  @override
  String get time => 'Time';

  @override
  String get addDueDate => 'Add due date';

  @override
  String get pressDoneToSave => 'Press done to save';

  @override
  String get pressDoneToCreate => 'Press done to create';

  @override
  String get filterAll => 'All';

  @override
  String get filterSystem => 'About You';

  @override
  String get filterInteresting => 'Insights';

  @override
  String get filterManual => 'Manual';

  @override
  String get completed => 'Completed';

  @override
  String get markComplete => 'Mark complete';

  @override
  String get actionItemDeleted => 'Action item deleted';

  @override
  String get failedToDeleteActionItem => 'Failed to delete action item';

  @override
  String get deleteActionItemConfirmTitle => 'Delete Action Item';

  @override
  String get deleteActionItemConfirmMessage => 'Are you sure you want to delete this action item?';

  @override
  String get appLanguage => 'App Language';

  @override
  String get appInterfaceSectionTitle => 'APP-GRÆNSEFLADE';

  @override
  String get speechTranscriptionSectionTitle => 'TALE OG TRANSSKRIPTION';

  @override
  String get languageSettingsHelperText =>
      'App-sprog ændrer menuer og knapper. Talesprog påvirker, hvordan dine optagelser transskriberes.';
}
